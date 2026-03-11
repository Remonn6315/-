# AIVtuber v2.0

AIが自律的にコメントを読んで感情表現するVTuberシステム。

---

## フォルダ構成（重要）

```
MyAI_Project/              ← Blackwellのルート
  ├── engine.py            ← Blackwell（触らない）
  ├── app.py               ← Blackwell（触らない）
  ├── memory.py            ← Blackwell用（触らない）
  │
  └── aivtuber/            ← AIVtuberはここに全部入ってる
        ├── __init__.py
        ├── main.py
        ├── vtuber_memory.py   ← AIVtuber用記憶（memory.pyとは別物）
        ├── character.py
        ├── emotion_engine.py
        ├── comment_processor.py
        ├── tts_engine.py
        ├── avatar_controller.py
        ├── keyboard_controller.py
        ├── chat_listener.py
        ├── settings_ui.py
        └── emotions/          ← 立ち絵PNG置き場
              neutral.png
              joy.png
              ...

        vtuber_memory/         ← 自動生成される記憶データ
              viewers.json
              sessions.json
              episodes.json
              self_growth.json
              character.json
```

---

## クイックスタート

```bash
# aivtuberフォルダに移動
cd aivtuber

# 設定画面（最初にキャラを作る）
streamlit run settings_ui.py

# テスト起動（音なし・モックコメント）
python main.py --tts mock

# VOICEVOX使う場合（先にVOICEVOXアプリを起動）
python main.py

# YouTube Live
python main.py --platform youtube --video-id あなたの動画ID

# OBS連携あり
python main.py --obs-password あなたのOBSパスワード
```

---

## キーボードショートカット

| キー | 効果 |
|------|------|
| F1 | 喜び |
| F2 | 怒り |
| F3 | 悲しみ |
| F4 | 驚き |
| F5 | 照れ |
| F6 | テンション高め |
| F7 | だるい |
| F8 | ニュートラル |
| F9 | 革新（話題転換） |
| F10 | 笑い |
| F12 | エネルギー回復 |
| + / - | テンション調整 |

---

## TTS差し替え

`tts_engine.py` の `create_tts()` に新しいエンジンを追加するだけ。
現在: voicevox / mock
将来: stylebert-vits2 / rvc / elevenlabs など

---

## OBS設定

1. OBSの設定 → WebServer → 有効化
2. パスワードを設定
3. `--obs-password yourpassword` で起動
4. OBSに「AIVtuber_Avatar」という名前の画像ソースを追加

