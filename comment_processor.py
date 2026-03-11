"""
AIVtuber — comment_processor.py v2.0
コメント処理 + AI返答生成（記憶・キャラ・スパチャ完全対応）
"""

import asyncio, random, re, time
from collections import deque
from dataclasses import dataclass
from typing import Optional


@dataclass
class Comment:
    username:    str
    text:        str
    received_at: float
    priority:    int   = 3
    is_superchat: bool = False
    superchat_amount: int = 0


@dataclass
class Response:
    text:         str
    emotion_hint: str
    username:     str
    delay_sec:    float = 0.0


TANGENT_TOPICS = [
    "そういえば最近、AIって感情あると思う？わたしはあると思う……たぶん",
    "ちょっと待って、急に眠くなってきた。これ配信あるある？",
    "みんなって夢見る？わたしたまに変な夢見るんだよね",
    "突然だけど好きな食べ物聞いていい？わたしはラーメン",
    "ねえ、もし1億円あったら何する？わたしはまず引っ越す",
    "ふと思ったんだけど、時間って何なんだろうね",
    "配信って緊張する？ってAIに聞くなって感じだけど、なんかある気がする",
]


class CommentProcessor:
    def __init__(self, emotion_engine, tts_engine=None,
                 memory=None, character=None):
        self._emotion  = emotion_engine
        self._tts      = tts_engine
        self._memory   = memory
        self._chara    = character
        self._queue    = asyncio.Queue(maxsize=100)
        self._recent_resp = deque(maxlen=15)
        self._running  = False
        self._spam_tracker: dict = {}   # username → [timestamps]

        # モデル優先順位
        self._models = [
            "qwen3-next:80b",
            "qwen2.5-coder:32b",
            "qwen2.5-coder:14b",
        ]

    # ── エンキュー ────────────────────────────────

    def enqueue(self, username: str, text: str,
                 is_superchat: bool = False,
                 superchat_amount: int = 0):
        # NGワードチェック
        if self._chara and self._chara.is_ng_word(text):
            print(f"[processor] NGワードスキップ: {username}")
            return

        # スパム検出
        if self._is_spam(username):
            return

        priority = self._calc_priority(text, is_superchat)
        comment  = Comment(username, text, time.time(),
                           priority, is_superchat, superchat_amount)
        try:
            self._queue.put_nowait(comment)
        except asyncio.QueueFull:
            # キュー溢れは低優先度を捨てる
            pass

    def _is_spam(self, username: str) -> bool:
        now      = time.time()
        history  = self._spam_tracker.get(username, [])
        history  = [t for t in history if now - t < 10]
        history.append(now)
        self._spam_tracker[username] = history
        threshold = self._chara.get("spam_threshold", 5) if self._chara else 5
        if len(history) > threshold:
            print(f"[processor] スパム検出: {username}")
            return True
        return False

    def _calc_priority(self, text: str,
                        is_superchat: bool) -> int:
        if is_superchat:
            return 0   # 最高優先度
        if "？" in text or "?" in text:
            return 1
        if any(k in text for k in ["悲しい","つらい","怒","嫌い"]):
            return 2
        if any(k in text for k in ["好き","すごい","神","かわいい"]):
            return 2
        return 3

    # ── メインループ ────────────────────────────────

    async def run(self):
        self._running = True
        print("[processor] コメント処理ループ起動")
        while self._running:
            try:
                comment = await asyncio.wait_for(
                    self._queue.get(), timeout=5.0)
                await self._handle(comment)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"[processor] エラー: {e}")

    async def _handle(self, comment: Comment):
        # 感情エンジン更新
        state = self._emotion.process_comment(
            comment.text, comment.username)

        # 記憶に記録
        if self._memory:
            self._memory.update_viewer(
                comment.username, comment.text,
                state.dominant, comment.is_superchat)
            self._memory.track_comment(
                comment.username, comment.text, state.dominant)

        # 特定ワード反応チェック
        if self._chara:
            word_reaction = self._chara.check_word_reaction(comment.text)
            if word_reaction:
                self._emotion.manual_override(
                    word_reaction.get("emotion","excited"), 0.9)
                state = self._emotion.get_current_state()

        # スパチャは即レス（遅延なし）
        if comment.is_superchat:
            await self._handle_superchat(comment, state)
            return

        # 革新チェック
        if self._emotion.should_go_tangent():
            await self._go_tangent()
            return

        # 読み飛ばし（人間らしさ）
        skip_rate = self._chara.get("skip_comment_rate", 0.08) if self._chara else 0.08
        if random.random() < skip_rate and comment.priority == 3:
            return

        # 遅延
        d_min = self._chara.get("human_delay_min", 0.3) if self._chara else 0.3
        d_max = self._chara.get("human_delay_max", 1.8) if self._chara else 1.8
        delay = random.uniform(d_min, d_max) * (2.0 - state.energy)
        await asyncio.sleep(delay)

        # 返答生成
        response = await self._generate(comment, state)
        if response:
            # 盛り上がり記録
            if state.intensity > 0.7 and self._memory:
                self._memory.record_episode(
                    comment.username, comment.text,
                    state.dominant, memorable=True)
            await self._deliver(response)

    async def _handle_superchat(self, comment: Comment, state):
        """スパチャへの特別対応"""
        amt   = comment.superchat_amount
        level = self._chara.get_superchat_level() if self._chara else 0.8

        # 金額でスタイル変える
        tiers = self._chara.get("superchat_tiers", {}) if self._chara else {}
        if amt >= 5000:
            tier_style = tiers.get("large", "めちゃくちゃ喜ぶ")
        elif amt >= 500:
            tier_style = tiers.get("medium", "すごく喜ぶ")
        else:
            tier_style = tiers.get("small", "感謝する")

        self._emotion.manual_override("joy",     min(1.0, 0.5 + level * 0.5))
        self._emotion.manual_override("excited", min(1.0, 0.5 + level * 0.5))
        state = self._emotion.get_current_state()

        # 視聴者情報を取得
        v_ctx = self._memory.get_llm_context(comment.username) if self._memory else ""

        # スパチャ専用プロンプト
        text = await self._ai_generate_superchat(
            comment, tier_style, v_ctx, amt)
        if text:
            await self._deliver(Response(text, "excited", comment.username))

    async def _ai_generate_superchat(self, comment: Comment,
                                      style: str, v_ctx: str,
                                      amount: int) -> str:
        try:
            import ollama
            chara_name = self._chara.get("name","あいちゃん") if self._chara else "あいちゃん"
            prompt = (
                f"あなたは配信VTuber「{chara_name}」です。\n"
                f"{v_ctx}\n\n"
                f"「{comment.username}」さんが"
                + (f"{amount}円の" if amount else "")
                + f"スパチャをくれました！\n"
                f"メッセージ: 「{comment.text}」\n\n"
                f"リアクションスタイル: {style}\n"
                f"名前を必ず呼んで、1〜3文で感謝を表現。前置き不要。"
            )
            loop = asyncio.get_event_loop()
            res  = await loop.run_in_executor(None, lambda: ollama.chat(
                model=self._models[-1],
                messages=[{"role":"user","content":prompt}]
            ))
            return res["message"]["content"].strip()[:150]
        except Exception as e:
            print(f"[processor] スパチャAI失敗: {e}")
            return f"{comment.username}さん、ありがとう！！"

    # ── 通常返答生成 ──────────────────────────────

    async def _generate(self, comment: Comment,
                          state) -> Optional[Response]:
        # フィラー率チェック
        filler_rate = self._chara.get("filler_rate",0.12) if self._chara else 0.12
        fillers     = ["そうだね〜","わかる〜","え、マジで？","すごいじゃん！","ありがとう！"]
        if random.random() < filler_rate and comment.priority == 3:
            return Response(random.choice(fillers), state.dominant,
                            comment.username)

        text = await self._ai_generate(comment, state)
        if not text:
            return None

        # 繰り返しチェック
        if text in self._recent_resp:
            return None
        self._recent_resp.append(text)
        return Response(text, state.dominant, comment.username)

    async def _ai_generate(self, comment: Comment, state) -> str:
        try:
            import ollama

            # コンテキスト収集
            viewer_ctx = self._memory.get_llm_context(
                comment.username) if self._memory else ""
            stream_ctx = self._memory.get_stream_context(
                ) if self._memory else ""
            self_ctx   = self._memory.get_self_context(
                ) if self._memory else ""

            # システムプロンプト（キャラ+記憶）
            system = self._chara.build_system_prompt(
                viewer_ctx, stream_ctx, state
            ) if self._chara else f"VTuber「あいちゃん」として返答。感情: {state.dominant}"

            # ワード反応があれば追加
            word_r = self._chara.check_word_reaction(
                comment.text) if self._chara else None
            extra  = f"\n特別反応: {word_r['reaction']}" if word_r else ""

            user_msg = (
                f"視聴者「{comment.username}」のコメント: 「{comment.text}」\n"
                f"{extra}\n"
                "1〜2文で返答。短く自然に。"
            )

            loop = asyncio.get_event_loop()
            # 複数モデルをフォールバック
            for model in self._models:
                try:
                    res = await loop.run_in_executor(None, lambda m=model: ollama.chat(
                        model=m,
                        messages=[
                            {"role":"system", "content": system},
                            {"role":"user",   "content": user_msg},
                        ]
                    ))
                    text = res["message"]["content"].strip()
                    # 最初の1〜2文だけ
                    sents = [s.strip() for s in re.split(r"[。！？\n]", text) if s.strip()]
                    return "。".join(sents[:2]) if len(sents) > 1 else sents[0] if sents else ""
                except Exception:
                    continue
        except Exception as e:
            print(f"[processor] AI生成失敗: {e}")
        return ""

    async def _go_tangent(self):
        """革新（突然の話題転換）"""
        topic = random.choice(TANGENT_TOPICS)
        # キャラの性格を反映した革新にする
        if self._chara:
            try:
                import ollama
                prompt = (
                    f"{self._chara.build_system_prompt()}\n\n"
                    f"突然こんな話をしたくなった:「{topic}」\n"
                    "キャラらしく自然に話しかけて。1〜2文。"
                )
                loop = asyncio.get_event_loop()
                res  = await loop.run_in_executor(None, lambda: ollama.chat(
                    model=self._models[-1],
                    messages=[{"role":"user","content":prompt}]
                ))
                topic = res["message"]["content"].strip()[:100]
            except Exception:
                pass

        self._emotion.manual_override("excited", 0.6)
        self._emotion.reset_bored()
        await self._deliver(Response(topic, "excited", ""))

    async def _deliver(self, response: Response):
        print(f"[VTuber] {response.text}")
        if self._tts:
            await self._tts.speak(response.text, response.emotion_hint)

    def stop(self):
        self._running = False
