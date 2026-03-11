"""
AIVtuber — tts_engine.py
TTS抽象レイヤー（差し替え対応）

現在対応:
  voicevox   ← 今はこれ
  mock       ← テスト用（音なし）

将来追加予定（差し替えるだけ）:
  stylebert_vits2
  rvc
  elevenlabs
  coeiroink
"""

import asyncio, os, re, subprocess, tempfile
from abc import ABC, abstractmethod


class BaseTTS(ABC):
    @abstractmethod
    async def speak(self, text: str, emotion: str = "neutral"): ...


# ── VOICEVOX ────────────────────────────────────────

class VoicevoxTTS(BaseTTS):
    """
    VOICEVOXがローカルで起動していること前提。
    http://127.0.0.1:50021
    """
    SPEAKER_MAP = {
        # emotion → VOICEVOXのspeaker_id
        # ずんだもん系で感情別に声を変える例
        "joy":      3,   # ずんだもん（ノーマル）
        "excited":  1,   # ずんだもん（テンション高め相当）
        "sadness":  4,   # ずんだもん（悲しみ）
        "anger":    5,   # ずんだもん（怒り）
        "shy":      22,  # 春日部つむぎ
        "surprise": 3,
        "bored":    4,
        "neutral":  3,
    }
    BASE_URL = "http://127.0.0.1:50021"

    def __init__(self, default_speaker: int = 3):
        self.default_speaker = default_speaker

    async def speak(self, text: str, emotion: str = "neutral"):
        if not text.strip():
            return
        speaker = self.SPEAKER_MAP.get(emotion, self.default_speaker)
        loop    = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._speak_sync, text, speaker)

    def _speak_sync(self, text: str, speaker: int):
        try:
            import urllib.request, json as _json, wave

            # 1. audio_query
            encoded = urllib.parse.quote(text)
            url1    = f"{self.BASE_URL}/audio_query?text={encoded}&speaker={speaker}"
            req1    = urllib.request.Request(url1, method="POST")
            with urllib.request.urlopen(req1, timeout=10) as r:
                query = _json.loads(r.read())

            # 感情に合わせてパラメータ調整
            if emotion == "excited":
                query["speedScale"]  = 1.2
                query["pitchScale"]  = 0.05
            elif emotion == "sadness":
                query["speedScale"]  = 0.9
                query["pitchScale"]  = -0.05
            elif emotion == "anger":
                query["speedScale"]  = 1.1
                query["volumeScale"] = 1.2

            # 2. synthesis
            url2     = f"{self.BASE_URL}/synthesis?speaker={speaker}"
            body     = _json.dumps(query).encode()
            req2     = urllib.request.Request(
                url2, data=body, method="POST",
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req2, timeout=15) as r:
                wav_data = r.read()

            # 3. 再生
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_data)
                tmp_path = f.name
            _play_wav(tmp_path)
            os.unlink(tmp_path)

        except Exception as e:
            print(f"[tts] VOICEVOX失敗: {e}")


import urllib.parse  # noqa: E402


def _play_wav(path: str):
    """OS別wav再生"""
    import platform
    sys = platform.system()
    try:
        if sys == "Windows":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
        elif sys == "Darwin":
            subprocess.run(["afplay", path], check=True)
        else:
            # Linux: paplay or aplay
            for cmd in [["paplay", path], ["aplay", path]]:
                if subprocess.run(cmd, capture_output=True).returncode == 0:
                    break
    except Exception as e:
        print(f"[tts] 再生失敗: {e}")


# ── Mock TTS（テスト用）──────────────────────────────

class MockTTS(BaseTTS):
    async def speak(self, text: str, emotion: str = "neutral"):
        print(f"[TTS-mock] ({emotion}) {text}")


# ── ファクトリー ──────────────────────────────────────

def create_tts(engine: str = "voicevox", **kwargs) -> BaseTTS:
    """
    engine="voicevox"  → VoicevoxTTS
    engine="mock"      → MockTTS
    将来: engine="stylebert" など
    """
    engines = {
        "voicevox": VoicevoxTTS,
        "mock":     MockTTS,
    }
    cls = engines.get(engine, MockTTS)
    return cls(**kwargs)
