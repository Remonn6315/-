"""
AIVtuber — main.py
メインエントリーポイント

使い方:
  python main.py                    # モック（テスト）
  python main.py --platform youtube --video-id xxxxx
  python main.py --platform twitch  --channel yourname --token oauth:xxx
  python main.py --tts mock         # 音声なし（テキストだけ）
  python main.py --no-obs           # OBS連携なし
"""

import asyncio, argparse, signal, sys, time, threading
from emotion_engine    import EmotionEngine
from comment_processor import CommentProcessor
from tts_engine        import create_tts
from avatar_controller import AvatarController
from keyboard_controller import KeyboardController
from chat_listener     import create_listener


class AIVtuber:
    def __init__(self, args):
        print("="*50)
        print("  AIVtuber 起動中...")
        print("="*50)

        # コア
        self.emotion    = EmotionEngine()
        self.tts        = create_tts(args.tts)
        self.avatar     = AvatarController(
            avatar_dir   = args.avatar_dir,
            obs_password = args.obs_password,
        )
        self.processor  = CommentProcessor(self.emotion, self.tts)
        self.keyboard   = KeyboardController(self.emotion, self.processor)
        self.listener   = create_listener(
            platform     = args.platform,
            video_id     = getattr(args, "video_id", ""),
            channel      = getattr(args, "channel", ""),
            token        = getattr(args, "token", ""),
            interval_range = (args.comment_min, args.comment_max),
        )

        # キーボードのコールバック → アバター更新
        self.keyboard.add_callback(self.avatar.update_emotion)

        self._args    = args
        self._running = False

    async def start(self):
        self._running = True

        # OBS接続（オプション）
        if not self._args.no_obs and self._args.obs_password:
            await self.avatar.connect_obs(self._args.obs_password)

        # キーボード起動（別スレッド）
        self.keyboard.start()

        # Tickループ（感情の時間経過）
        asyncio.create_task(self._tick_loop())

        # コメント処理ループ
        asyncio.create_task(self.processor.run())

        # チャット受信ループ
        print(f"\n[main] プラットフォーム: {self._args.platform}")
        print(f"[main] TTS: {self._args.tts}")
        print("[main] 起動完了！コメントを待っています...\n")

        await self.listener.listen(self._on_comment)

    async def _on_comment(self, msg):
        """チャットメッセージを受け取ってプロセッサに渡す"""
        print(f"[chat] {msg.username}: {msg.text}")
        self.processor.enqueue(msg.username, msg.text)
        self.avatar.update_emotion(self.emotion.get_current_state())

    async def _tick_loop(self):
        """毎秒感情を自然に変化させる"""
        last = time.time()
        while self._running:
            await asyncio.sleep(1.0)
            now   = time.time()
            delta = now - last
            last  = now
            self.emotion.tick(delta)
            self.avatar.update_emotion(self.emotion.get_current_state())

    def stop(self):
        self._running = False
        self.listener.stop()
        self.processor.stop()
        self.keyboard.stop()
        print("\n[main] 停止しました")


async def main():
    parser = argparse.ArgumentParser(description="AIVtuber")
    parser.add_argument("--platform",     default="mock",
                        choices=["mock","youtube","twitch"])
    parser.add_argument("--video-id",     default="",     help="YouTube動画ID")
    parser.add_argument("--channel",      default="",     help="Twitchチャンネル名")
    parser.add_argument("--token",        default="",     help="Twitchトークン")
    parser.add_argument("--tts",          default="voicevox",
                        choices=["voicevox","mock"])
    parser.add_argument("--avatar-dir",   default="./emotions")
    parser.add_argument("--no-obs",       action="store_true")
    parser.add_argument("--obs-password", default="")
    parser.add_argument("--comment-min",  type=float, default=2.0)
    parser.add_argument("--comment-max",  type=float, default=6.0)

    args   = parser.parse_args()
    vtuber = AIVtuber(args)

    # Ctrl+C で綺麗に終了
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, vtuber.stop)

    try:
        await vtuber.start()
    except KeyboardInterrupt:
        vtuber.stop()


if __name__ == "__main__":
    asyncio.run(main())
