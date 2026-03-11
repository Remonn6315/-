"""
AIVtuber — main.py v2.0

使い方:
  python main.py                          # モック（テスト）
  python main.py --platform youtube --video-id xxxxx
  python main.py --tts mock               # 音声なし
  streamlit run settings_ui.py           # 設定画面
"""

import asyncio, argparse, signal, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from emotion_engine      import EmotionEngine
from comment_processor   import CommentProcessor
from tts_engine          import create_tts
from avatar_controller   import AvatarController
from keyboard_controller import KeyboardController
from chat_listener       import create_listener
from memory              import MemorySystem
from character           import CharacterManager


class AIVtuber:
    def __init__(self, args):
        print("="*50)
        print("  AIVtuber v2.0 起動中...")
        print("="*50)

        # 設定・記憶を読み込む
        self.chara   = CharacterManager()
        self.memory  = MemorySystem()

        # コア
        self.emotion   = EmotionEngine()
        self.tts       = create_tts(args.tts)
        self.avatar    = AvatarController(
            avatar_dir   = args.avatar_dir,
            obs_password = args.obs_password,
        )
        self.processor = CommentProcessor(
            emotion_engine = self.emotion,
            tts_engine     = self.tts,
            memory         = self.memory,
            character      = self.chara,
        )
        self.keyboard  = KeyboardController(self.emotion, self.processor)
        self.listener  = create_listener(
            platform       = args.platform,
            video_id       = getattr(args, "video_id", ""),
            channel        = getattr(args, "channel", ""),
            token          = getattr(args, "token", ""),
            interval_range = (args.comment_min, args.comment_max),
        )

        # キーボード → アバター連動
        self.keyboard.add_callback(self.avatar.update_emotion)
        self._args    = args
        self._running = False
        self._session_id = ""

    async def start(self):
        self._running = True

        # 配信開始を記録
        self._session_id = self.memory.record_session_start()

        # OBS接続
        if not self._args.no_obs and self._args.obs_password:
            await self.avatar.connect_obs(self._args.obs_password)

        # キーボード起動
        self.keyboard.start()

        # Tickループ
        asyncio.create_task(self._tick_loop())

        # コメント処理
        asyncio.create_task(self.processor.run())

        # 配信開始挨拶
        await self._greet_start()

        print(f"\n[main] プラットフォーム : {self._args.platform}")
        print(f"[main] TTS             : {self._args.tts}")
        print(f"[main] キャラ           : {self.chara.get('name')}")
        print("[main] 起動完了！\n")

        await self.listener.listen(self._on_comment)

    async def _on_comment(self, msg):
        print(f"[chat] {msg.username}: {msg.text}")

        # 初来場チェック
        v = self.memory.get_viewer(msg.username)
        if v.visits == 0:
            self.memory.record_visit(msg.username)

        # スパチャ判定（プラットフォームによって実装）
        is_sc = getattr(msg, "is_superchat", False)
        sc_amount = getattr(msg, "superchat_amount", 0)

        self.processor.enqueue(
            msg.username, msg.text,
            is_superchat=is_sc,
            superchat_amount=sc_amount,
        )
        self.avatar.update_emotion(self.emotion.get_current_state())

    async def _tick_loop(self):
        last = time.time()
        while self._running:
            await asyncio.sleep(1.0)
            now   = time.time()
            delta = now - last
            last  = now
            self.emotion.tick(delta)
            self.avatar.update_emotion(self.emotion.get_current_state())

    async def _greet_start(self):
        """配信開始挨拶をAIで生成"""
        vibe  = self.chara.get("greeting_vibe", "元気よく挨拶")
        exs   = self.chara.get("greeting_examples", [])
        name  = self.chara.get("name", "あいちゃん")
        stats = self.memory.get_stats()

        try:
            import ollama
            prompt = (
                f"VTuber「{name}」として配信を始めます。\n"
                f"挨拶の雰囲気: {vibe}\n"
                f"参考例: {exs[0] if exs else ''}\n"
                f"配信回数: {stats['total_sessions']}回目\n"
                "今日の挨拶を1〜2文で。毎回違う表現で。前置き不要。"
            )
            res = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ollama.chat(
                    model="qwen2.5-coder:14b",
                    messages=[{"role":"user","content":prompt}]
                ))
            greeting = res["message"]["content"].strip()[:120]
        except Exception:
            greeting = f"こんにちは！今日も始めるよ！"

        print(f"[VTuber] {greeting}")
        if self.tts:
            await self.tts.speak(greeting, "excited")
        self.emotion.manual_override("excited", 0.7)

    async def _farewell(self):
        """配信終了挨拶"""
        vibe = self.chara.get("farewell_vibe","感謝して締める")
        name = self.chara.get("name","あいちゃん")
        try:
            import ollama
            prompt = (
                f"VTuber「{name}」として配信を終わります。\n"
                f"締めの雰囲気: {vibe}\n"
                "締めの言葉を1〜2文で。前置き不要。"
            )
            res = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ollama.chat(
                    model="qwen2.5-coder:14b",
                    messages=[{"role":"user","content":prompt}]
                ))
            farewell = res["message"]["content"].strip()[:120]
        except Exception:
            farewell = "今日もありがとう！またね！"

        print(f"[VTuber] {farewell}")
        if self.tts:
            await self.tts.speak(farewell, "joy")

    def stop(self):
        self._running = False
        self.listener.stop()
        self.processor.stop()
        self.keyboard.stop()
        # 配信終了を記録
        self.memory.record_session_end()
        print("\n[main] 停止しました")
        asyncio.create_task(self._farewell())


async def main():
    parser = argparse.ArgumentParser(description="AIVtuber v2.0")
    parser.add_argument("--platform",     default="mock",
                        choices=["mock","youtube","twitch"])
    parser.add_argument("--video-id",     default="")
    parser.add_argument("--channel",      default="")
    parser.add_argument("--token",        default="")
    parser.add_argument("--tts",          default="voicevox",
                        choices=["voicevox","mock"])
    parser.add_argument("--avatar-dir",   default="./emotions")
    parser.add_argument("--no-obs",       action="store_true")
    parser.add_argument("--obs-password", default="")
    parser.add_argument("--comment-min",  type=float, default=2.0)
    parser.add_argument("--comment-max",  type=float, default=6.0)

    args   = parser.parse_args()
    vtuber = AIVtuber(args)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, vtuber.stop)

    try:
        await vtuber.start()
    except KeyboardInterrupt:
        vtuber.stop()


if __name__ == "__main__":
    asyncio.run(main())
