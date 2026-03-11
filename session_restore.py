"""
Blackwell Dev-OS — session_restore.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
「前回の続きから」セッション永続化

Streamlitのリロード/再起動でも状態を完全復元:
  - 会話履歴
  - Blackwell主軸 + ゲーム主軸
  - 設定（パス・モデル・モード）
  - 作りかけのタスクプラン
  - フィーリングパラメータ
  - 最後の生成結果

保存先: ~/.blackwell_session.json (ホームディレクトリ)
"""
import json, os
from datetime import datetime
from pathlib import Path

SESSION_PATH = os.path.join(Path.home(), ".blackwell_session.json")
BACKUP_PATH  = SESSION_PATH + ".bak"

# 保存するsession_stateのキー一覧
PERSIST_KEYS = [
    "project_anchor", "game_anchor",
    "target_path", "max_cycles", "auto_write",
    "dark_mode", "persona",
    "messages",           # 会話履歴（直近50件）
    "feeling_params",
    "last_result",
    "build_log",
    "quality_check_result",
]


def save_session(state: dict) -> bool:
    """Streamlitのst.session_stateを永続化する"""
    try:
        data = {"saved_at": datetime.now().isoformat(), "version": "1.0"}
        for key in PERSIST_KEYS:
            if key in state:
                val = state[key]
                # 会話履歴は直近50件のみ保存
                if key == "messages" and isinstance(val, list):
                    val = val[-50:]
                # JSON serializable かチェック
                try:
                    json.dumps(val, ensure_ascii=False)
                    data[key] = val
                except (TypeError, ValueError):
                    data[key] = str(val)[:500]

        # バックアップ
        if os.path.exists(SESSION_PATH):
            import shutil
            shutil.copy2(SESSION_PATH, BACKUP_PATH)

        with open(SESSION_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[session_restore] 保存失敗: {e}")
        return False


def load_session() -> dict:
    """
    保存済みセッションを読み込んで辞書で返す。
    セッションファイルがなければ空辞書を返す。
    """
    for path in (SESSION_PATH, BACKUP_PATH):
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                saved_at = data.pop("saved_at", "不明")
                data.pop("version", None)
                print(f"[session_restore] セッション復元: {saved_at}")
                return data
            except Exception as e:
                print(f"[session_restore] 読み込み失敗 ({path}): {e}")
    return {}


def restore_to_streamlit(state, loaded: dict):
    """
    load_session()の結果をStreamlitのsession_stateに適用する。
    既に値がある場合は上書きしない（初回のみ復元）。
    """
    restored = []
    for key, val in loaded.items():
        if key not in state:
            state[key] = val
            restored.append(key)
    if restored:
        print(f"[session_restore] 復元したキー: {restored}")
    return restored


def get_session_info() -> dict:
    """セッションファイルの情報を返す（UI表示用）"""
    if not os.path.exists(SESSION_PATH):
        return {"exists": False}
    try:
        stat = os.stat(SESSION_PATH)
        with open(SESSION_PATH, encoding="utf-8") as f:
            data = json.load(f)
        msg_count = len(data.get("messages", []))
        return {
            "exists":    True,
            "saved_at":  data.get("saved_at", "不明"),
            "size_kb":   stat.st_size // 1024,
            "messages":  msg_count,
            "anchor":    data.get("project_anchor", "")[:40],
            "path":      data.get("target_path", "不明"),
        }
    except Exception:
        return {"exists": True, "saved_at": "読み込み失敗"}


def clear_session():
    """セッションファイルを削除"""
    for p in (SESSION_PATH, BACKUP_PATH):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
