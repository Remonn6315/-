"""
AIVtuber — avatar_controller.py
立ち絵PNG制御 + OBS WebSocket連携

【立ち絵管理】
  emotions/ フォルダに感情別PNGを置く:
    emotions/joy.png
    emotions/anger.png
    emotions/sadness.png
    emotions/surprise.png
    emotions/shy.png
    emotions/excited.png
    emotions/bored.png
    emotions/neutral.png
    emotions/talking.png   ← 口パク用（話してる状態）

  PNGがなければ自動でサンプル画像を生成する

【OBS WebSocket】
  OBS 28以上 + obs-websocket v5 が必要
  ポート: 4455（デフォルト）

【公開API】
  update_emotion(state)     → None  感情に合わせて立ち絵切り替え
  set_talking(is_talking)   → None  口パク
  connect_obs(password)     → bool
  send_obs_command(cmd)     → None
"""

import asyncio, base64, json, os, time
from pathlib import Path


EMOTION_TO_FACE = {
    "joy":      "joy",
    "anger":    "anger",
    "sadness":  "sadness",
    "surprise": "surprise",
    "shy":      "shy",
    "excited":  "excited",
    "bored":    "bored",
    "neutral":  "neutral",
}


class AvatarController:
    def __init__(self, avatar_dir: str = "./emotions",
                 obs_host: str = "localhost",
                 obs_port: int = 4455,
                 obs_password: str = ""):
        self._avatar_dir   = Path(avatar_dir)
        self._obs_host     = obs_host
        self._obs_port     = obs_port
        self._obs_password = obs_password
        self._obs_ws       = None
        self._obs_connected = False
        self._current_face = "neutral"
        self._is_talking   = False
        self._talk_timer   = 0.0
        self._msg_id       = 1

        # OBSのソース名（自分の環境に合わせて変更）
        self.avatar_source_name = "AIVtuber_Avatar"

        self._avatar_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_sample_images()

    # ── 感情更新 ────────────────────────────────────

    def update_emotion(self, state):
        """EmotionStateに合わせて立ち絵を切り替える"""
        face = EMOTION_TO_FACE.get(state.dominant, "neutral")

        # 変化があるときだけ更新
        if face != self._current_face:
            self._current_face = face
            print(f"[avatar] 表情: {face} (intensity={state.intensity:.2f})")
            if self._obs_connected:
                asyncio.create_task(self._obs_set_avatar(face))

    def set_talking(self, is_talking: bool):
        """口パク状態を切り替える"""
        if is_talking != self._is_talking:
            self._is_talking = is_talking
            face = "talking" if is_talking else self._current_face
            if self._obs_connected:
                asyncio.create_task(self._obs_set_avatar(face))

    def get_image_path(self, emotion: str = None) -> str:
        em   = emotion or self._current_face
        face = "talking" if self._is_talking else em
        path = self._avatar_dir / f"{face}.png"
        if not path.exists():
            path = self._avatar_dir / "neutral.png"
        return str(path)

    # ── OBS WebSocket ────────────────────────────────

    async def connect_obs(self, password: str = "") -> bool:
        if password:
            self._obs_password = password
        try:
            import websockets
            uri = f"ws://{self._obs_host}:{self._obs_port}"
            self._obs_ws = await websockets.connect(uri)

            # Hello / Identify ハンドシェイク
            hello = json.loads(await self._obs_ws.recv())
            if hello.get("op") == 0:
                auth = self._make_auth(hello["d"], self._obs_password)
                await self._obs_ws.send(json.dumps({
                    "op": 1,
                    "d": {"rpcVersion": 1, "authentication": auth,
                          "eventSubscriptions": 0}
                }))
                identified = json.loads(await self._obs_ws.recv())
                if identified.get("op") == 2:
                    self._obs_connected = True
                    print("[avatar] OBS接続成功")
                    return True
        except Exception as e:
            print(f"[avatar] OBS接続失敗: {e}")
        return False

    def _make_auth(self, hello_data: dict, password: str) -> str:
        import hashlib, base64
        if "authentication" not in hello_data:
            return ""
        challenge = hello_data["authentication"]["challenge"]
        salt      = hello_data["authentication"]["salt"]
        secret    = base64.b64encode(
            hashlib.sha256((password + salt).encode()).digest()
        ).decode()
        return base64.b64encode(
            hashlib.sha256((secret + challenge).encode()).digest()
        ).decode()

    async def _obs_set_avatar(self, face: str):
        """OBSの画像ソースを切り替える"""
        path = str((self._avatar_dir / f"{face}.png").resolve())
        if not os.path.exists(path):
            path = str((self._avatar_dir / "neutral.png").resolve())
        await self._obs_request("SetInputSettings", {
            "inputName": self.avatar_source_name,
            "inputSettings": {"file": path}
        })

    async def _obs_request(self, request_type: str, data: dict = None):
        if not self._obs_ws or not self._obs_connected:
            return
        msg = {
            "op": 6,
            "d": {
                "requestType": request_type,
                "requestId":   str(self._msg_id),
                "requestData": data or {}
            }
        }
        self._msg_id += 1
        try:
            await self._obs_ws.send(json.dumps(msg))
        except Exception as e:
            print(f"[avatar] OBS送信失敗: {e}")
            self._obs_connected = False

    async def obs_scene_change(self, scene_name: str):
        await self._obs_request("SetCurrentProgramScene",
                                 {"sceneName": scene_name})

    async def obs_show_text(self, source_name: str, text: str):
        """OBSのテキストソースを更新（字幕・コメント表示用）"""
        await self._obs_request("SetInputSettings", {
            "inputName":     source_name,
            "inputSettings": {"text": text}
        })

    # ── サンプル画像生成 ──────────────────────────────

    def _ensure_sample_images(self):
        """立ち絵がない場合にシンプルなサンプルPNGを生成"""
        emotions = ["neutral","joy","anger","sadness","surprise",
                    "shy","excited","bored","talking"]
        colors = {
            "neutral":  (180, 180, 200),
            "joy":      (255, 220, 100),
            "anger":    (255, 100, 100),
            "sadness":  (100, 150, 255),
            "surprise": (255, 180, 50),
            "shy":      (255, 150, 180),
            "excited":  (255, 130, 50),
            "bored":    (150, 150, 150),
            "talking":  (200, 230, 200),
        }
        for em in emotions:
            path = self._avatar_dir / f"{em}.png"
            if not path.exists():
                self._create_sample_png(path, em, colors.get(em,(180,180,180)))

    def _create_sample_png(self, path: Path, label: str, color: tuple):
        try:
            import numpy as np
            W, H = 400, 600
            img  = np.zeros((H, W, 4), dtype=np.uint8)
            r, g, b = color
            # 背景（透明）
            img[:, :, 3] = 0
            # 体（楕円もどき）
            cx, cy = W//2, H//2
            for y in range(H):
                for x in range(W):
                    dx = (x - cx) / (W * 0.35)
                    dy = (y - cy) / (H * 0.45)
                    if dx*dx + dy*dy < 1.0:
                        img[y, x] = [r, g, b, 220]
            # ラベル文字は書けないが色で区別

            # PNG保存（numpyだけで最低限）
            self._write_png(path, img)
            print(f"[avatar] サンプル画像生成: {path.name}")
        except Exception as e:
            print(f"[avatar] サンプル画像生成スキップ: {e}")

    @staticmethod
    def _write_png(path: Path, rgba: "np.ndarray"):
        """numpyだけで最小限のPNGを書く"""
        import struct, zlib
        import numpy as np
        H, W = rgba.shape[:2]

        def chunk(name: bytes, data: bytes) -> bytes:
            c = name + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

        raw = b""
        for row in rgba:
            raw += b"\x00" + row.tobytes()

        png  = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(raw))
        png += chunk(b"IEND", b"")
        path.write_bytes(png)
