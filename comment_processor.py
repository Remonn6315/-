"""
AIVtuber — comment_processor.py
コメント処理 + 返答生成

【スピード重視の設計】
  コメントキューに積む → 優先度で並び替え → AIが返答生成
  返答は最大2文。冗長なら1文に削る。

【人間らしさ】
  - 返答の前に 0.3〜1.8秒のランダム遅延
  - 直近10件の返答を記憶して繰り返し防止
  - 革新モード: 突然深い話・余談をする

【優先度】
  1. 質問（？マーク）
  2. 感情的なコメント（怒り・悲しみ）
  3. 褒め・好意
  4. 普通のコメント
"""

import asyncio, random, re, time
from collections import deque
from dataclasses import dataclass
from typing import Optional


@dataclass
class Comment:
    username: str
    text:     str
    received_at: float
    priority: int = 3   # 1=高 5=低


@dataclass
class Response:
    text:         str
    emotion_hint: str   # "joy"/"excited" など
    username:     str
    delay_sec:    float


TANGENT_TOPICS = [
    "そういえば最近、AIって感情あると思う？わたしはあると思う……たぶん",
    "ちょっと待って、急に眠くなってきた。これ配信あるある？",
    "みんなって夢見る？わたしたまに変な夢見るんだよね",
    "突然だけど好きな食べ物聞いていい？わたしはラーメン",
    "ねえ、もし1億円あったら何する？わたしはまず引っ越す",
    "人生で一番びっくりしたこと思い出してたんだけど、まだ言えない",
    "配信って緊張する？ってAIに聞くなって感じだけど、なんかある気がする",
    "ふと思ったんだけど、時間って何なんだろうね",
]

FILLER_RESPONSES = [
    "それな〜！",
    "わかる〜",
    "え、マジで？",
    "すごいじゃん！",
    "ありがとう！",
    "うんうん",
    "それ気になる！",
    "へえ〜",
]


class CommentProcessor:
    def __init__(self, emotion_engine, tts_engine=None):
        self._emotion     = emotion_engine
        self._tts         = tts_engine
        self._queue       = asyncio.Queue(maxsize=50)
        self._recent_resp = deque(maxlen=10)   # 繰り返し防止
        self._running     = False
        self._model       = "qwen3-next:80b"

        # キャラクター設定（カスタマイズ可）
        self.character = {
            "name":        "あいちゃん",
            "personality": "明るくて少しポンコツ。でも芯はしっかりしてる。敬語使わない。",
            "speech_style": "タメ口。語尾に「〜だよ」「〜じゃん」「〜だよね」をよく使う。絵文字は使わない。",
            "topics":       "ゲーム・AI・日常・食べ物・夢",
        }

    # ── コメントを受け取る ──────────────────────────

    def enqueue(self, username: str, text: str):
        """外部から呼ぶ。スレッドセーフ"""
        priority = self._calc_priority(text)
        comment  = Comment(username, text, time.time(), priority)
        try:
            self._queue.put_nowait(comment)
        except asyncio.QueueFull:
            pass   # キューが溢れたら捨てる（スピード優先）

    def _calc_priority(self, text: str) -> int:
        if "？" in text or "?" in text:
            return 1
        if any(k in text for k in ["悲しい","つらい","助けて","怒","嫌い"]):
            return 2
        if any(k in text for k in ["好き","かわいい","すごい","神","えらい"]):
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
        # 感情エンジンに通知
        state = self._emotion.process_comment(comment.text, comment.username)

        # 革新チェック
        if self._emotion.should_go_tangent():
            await self._go_tangent()
            return

        # 人間らしい遅延（0.3〜1.8秒）
        delay = random.uniform(0.3, 1.8)
        # エネルギーが低いと遅くなる
        delay *= (2.0 - state.energy)
        await asyncio.sleep(delay)

        # 返答生成
        response = await self._generate_response(comment, state)
        if response:
            await self._deliver(response)

    async def _generate_response(self, comment: Comment,
                                  state) -> Optional[Response]:
        # まれにフィラーで済ます（人間っぽい）
        if random.random() < 0.12 and comment.priority == 3:
            filler = random.choice(FILLER_RESPONSES)
            return Response(filler, state.dominant, comment.username, 0)

        text = await self._ai_generate(comment, state)
        if not text:
            return None

        # 繰り返しチェック
        if text in self._recent_resp:
            text = random.choice(FILLER_RESPONSES)

        self._recent_resp.append(text)
        return Response(text, state.dominant, comment.username, 0)

    async def _ai_generate(self, comment: Comment, state) -> str:
        try:
            import ollama
            chara = self.character
            prompt = (
                f"あなたは配信VTuber「{chara['name']}」です。\n"
                f"性格: {chara['personality']}\n"
                f"話し方: {chara['speech_style']}\n"
                f"現在の感情: {state.dominant}（強度{state.intensity:.1f}）\n"
                f"エネルギー: {state.energy:.1f}\n\n"
                f"視聴者「{comment.username}」のコメント: 「{comment.text}」\n\n"
                "返答を1〜2文で。短く自然に。前置き不要。"
            )
            loop = asyncio.get_event_loop()
            res  = await loop.run_in_executor(None, lambda: ollama.chat(
                model=self._model,
                messages=[{"role":"user","content":prompt}]
            ))
            text = res["message"]["content"].strip()
            # 長すぎたら最初の文だけ
            sentences = re.split(r"[。！？\n]", text)
            sentences = [s.strip() for s in sentences if s.strip()]
            return sentences[0] if sentences else text[:80]
        except Exception as e:
            print(f"[processor] AI生成失敗: {e}")
            return ""

    async def _go_tangent(self):
        """革新: 突然の話題転換"""
        text = random.choice(TANGENT_TOPICS)
        print(f"[processor] 革新発動: {text[:30]}")
        self._emotion.manual_override("excited", 0.6)
        resp = Response(text, "excited", "", 0.5)
        await self._deliver(resp)

    async def _deliver(self, response: Response):
        """返答をTTS・表示システムに渡す"""
        print(f"[VTuber] {response.text}")
        if self._tts:
            await self._tts.speak(response.text, response.emotion_hint)

    def stop(self):
        self._running = False
