"""
AIVtuber — chat_listener.py
YouTube/Twitch チャット取得

YouTube Live: pytchat ライブラリ使用
Twitch:       TwitchIO ライブラリ使用
テスト用:     ランダムコメント生成モック
"""

import asyncio, random, time
from dataclasses import dataclass


@dataclass
class ChatMessage:
    platform: str
    username: str
    text:     str
    timestamp: float


MOCK_COMMENTS = [
    ("視聴者A", "こんにちは！"),
    ("視聴者B", "すごいじゃん！"),
    ("視聴者C", "え、マジで？"),
    ("Remon", "かわいい！"),
    ("視聴者D", "w w w"),
    ("視聴者E", "草"),
    ("視聴者F", "応援してるよ！"),
    ("視聴者G", "それ好き"),
    ("視聴者H", "今日も来たよ！"),
    ("視聴者I", "一緒にがんばろう"),
    ("視聴者J", "神回だ"),
    ("視聴者K", "おつかれ！"),
    ("視聴者L", "もっとやって！"),
    ("視聴者M", "え、それ本当に？"),
    ("視聴者N", "ありがとう！"),
]


class MockChatListener:
    """開発・テスト用のモックチャット"""
    def __init__(self, interval_range=(2.0, 6.0)):
        self._min, self._max = interval_range
        self._running = False

    async def listen(self, callback):
        self._running = True
        print("[chat] モックチャット起動（テスト用）")
        while self._running:
            await asyncio.sleep(random.uniform(self._min, self._max))
            username, text = random.choice(MOCK_COMMENTS)
            msg = ChatMessage("mock", username, text, time.time())
            await callback(msg)

    def stop(self):
        self._running = False


class YouTubeChatListener:
    """YouTube Live チャット取得"""
    def __init__(self, video_id: str):
        self._video_id = video_id
        self._running  = False

    async def listen(self, callback):
        try:
            import pytchat
        except ImportError:
            print("[chat] pytchat未インストール。pip install pytchat")
            print("[chat] モックに切り替え")
            await MockChatListener().listen(callback)
            return

        self._running = True
        chat = pytchat.create(video_id=self._video_id)
        print(f"[chat] YouTube Live チャット取得開始: {self._video_id}")

        while self._running and chat.is_alive():
            async for c in chat.get().async_items():
                if not self._running:
                    break
                msg = ChatMessage(
                    "youtube", c.author.name, c.message,
                    c.timestamp.timestamp()
                )
                await callback(msg)
            await asyncio.sleep(0.5)

    def stop(self):
        self._running = False


class TwitchChatListener:
    """Twitch チャット取得"""
    def __init__(self, channel: str, token: str, bot_name: str = "aivtuber_bot"):
        self._channel  = channel
        self._token    = token
        self._bot_name = bot_name
        self._callback = None
        self._running  = False

    async def listen(self, callback):
        try:
            from twitchio.ext import commands
        except ImportError:
            print("[chat] twitchio未インストール。pip install twitchio")
            await MockChatListener().listen(callback)
            return

        self._callback = callback
        self._running  = True
        print(f"[chat] Twitch チャット取得開始: {self._channel}")

        import twitchio
        client = twitchio.Client(token=self._token)

        @client.event()
        async def event_message(message):
            if not self._running:
                return
            msg = ChatMessage(
                "twitch", message.author.name,
                message.content, time.time()
            )
            await callback(msg)

        await client.connect()

    def stop(self):
        self._running = False


def create_listener(platform: str = "mock", **kwargs):
    if platform == "youtube":
        return YouTubeChatListener(kwargs["video_id"])
    elif platform == "twitch":
        return TwitchChatListener(
            kwargs["channel"], kwargs["token"])
    else:
        return MockChatListener(
            kwargs.get("interval_range", (2.0, 6.0)))
