"""
AIVtuber パッケージ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
フォルダ構成:
  aivtuber/
    __init__.py         このファイル（パッケージ化・将来の拡張用）
    main.py             メインエントリーポイント
    emotion_engine.py   感情エンジン
    comment_processor.py コメント処理・AI返答
    vtuber_memory.py    永久記憶システム  ← memory.pyとは別物
    character.py        キャラ設定管理
    tts_engine.py       TTS抽象レイヤー（差し替え対応）
    avatar_controller.py 立ち絵・OBS制御
    keyboard_controller.py キーボードショートカット
    chat_listener.py    YouTube/Twitch/モック
    settings_ui.py      Streamlit設定画面

  vtuber_memory/        ← 永久記憶データ（自動生成）
    viewers.json        視聴者DB
    sessions.json       配信履歴
    episodes.json       思い出エピソード
    self_growth.json    自己成長ログ
    character.json      キャラ設定

【Blackwellのmemory.pyとは完全に別物】
  Blackwell memory.py  → コード・タスクのベクトル検索DB
  AIVtuber vtuber_memory.py → 視聴者・配信の感情付き永久記憶
"""

# バージョン管理
__version__ = "2.0.0"
__author__  = "Blackwell Dev-OS"
