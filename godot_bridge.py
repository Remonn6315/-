"""
Blackwell Dev-OS — godot_bridge.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
① Godot Plugin統合 — Python側WebSocketサーバー

【仕組み】
  Python(Blackwell) ←→ WebSocket ←→ GDScript(Godotプラグイン)

  Godot側のプラグインが起動すると ws://localhost:9901 に接続。
  以降はJSON メッセージで双方向リアルタイム通信。

【できること】
  Godot → Blackwell:
    エラーログをリアルタイム送信
    シーン情報・ノード構造を送信
    「このコード直して」リクエスト

  Blackwell → Godot:
    修正済みコードを送信 → プラグインが自動保存
    ファイルリロード命令
    タスク完了通知

【公開API】
  start_bridge()          → スレッドでサーバー起動
  stop_bridge()           → サーバー停止
  is_connected()          → Godotが接続中か
  send_to_godot(msg)      → Godotにメッセージ送信
  get_pending_requests()  → Godotからの未処理リクエスト一覧
  get_bridge_status()     → 状態辞書（app.py用）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import threading
import time
import queue
from datetime import datetime
from typing import Optional

BRIDGE_PORT    = 9901
BRIDGE_HOST    = "localhost"
MAX_LOG_LINES  = 200
MAX_REQUESTS   = 50


# ============================================================
# 状態管理（スレッドセーフ）
# ============================================================

_lock            = threading.Lock()
_clients         = []          # 接続中のWebSocketクライアント
_error_log       = []          # Godotから受信したエラーログ
_pending_req     = []          # 未処理のリクエスト（コード修正依頼等）
_sent_log        = []          # Blackwell→Godotの送信履歴
_server_thread   = None
_server_running  = False
_last_scene_info = {}          # 最後に受信したシーン情報
_stats = {
    "connected_at":  "",
    "total_received": 0,
    "total_sent":     0,
    "last_error":     "",
}


# ============================================================
# WebSocketサーバー（simple_websocketを使用）
# ============================================================

def start_bridge() -> bool:
    """
    WebSocketサーバーをバックグラウンドスレッドで起動する。
    app.pyの起動時に呼ぶ。
    """
    global _server_thread, _server_running

    if _server_running:
        print("[bridge] 既に起動中")
        return True

    try:
        import simple_websocket  # noqa — importチェックのみ
    except ImportError:
        try:
            import subprocess, sys
            subprocess.run(
                [sys.executable, "-m", "pip", "install",
                 "simple-websocket", "--break-system-packages", "-q"],
                check=True
            )
        except Exception as e:
            print(f"[bridge] simple-websocket インストール失敗: {e}")
            return False

    _server_running = True
    _server_thread  = threading.Thread(target=_run_server, daemon=True)
    _server_thread.start()
    print(f"[bridge] WebSocketサーバー起動: ws://{BRIDGE_HOST}:{BRIDGE_PORT}")
    return True


def stop_bridge():
    global _server_running
    _server_running = False
    print("[bridge] サーバー停止")


def is_connected() -> bool:
    with _lock:
        return len(_clients) > 0


def send_to_godot(message: dict) -> bool:
    """Godotに接続中の全クライアントにメッセージを送る"""
    global _stats
    with _lock:
        if not _clients:
            return False
        payload = json.dumps(message, ensure_ascii=False)
        dead = []
        for ws in _clients:
            try:
                ws.send(payload)
                _stats["total_sent"] += 1
                _sent_log.append({
                    "time": _now(), "type": message.get("type", ""),
                    "data": str(message)[:80],
                })
            except Exception:
                dead.append(ws)
        for ws in dead:
            _clients.remove(ws)
    return True


def get_pending_requests() -> list:
    """未処理のコード修正リクエストを返す（消費型）"""
    with _lock:
        result = list(_pending_req)
        _pending_req.clear()
    return result


def get_error_log(n: int = 20) -> list:
    with _lock:
        return list(_error_log[-n:])


def get_bridge_status() -> dict:
    with _lock:
        return {
            "running":         _server_running,
            "connected":       len(_clients) > 0,
            "client_count":    len(_clients),
            "port":            BRIDGE_PORT,
            "host":            BRIDGE_HOST,
            "total_received":  _stats["total_received"],
            "total_sent":      _stats["total_sent"],
            "connected_at":    _stats["connected_at"],
            "last_error":      _stats["last_error"],
            "pending_requests": len(_pending_req),
            "error_log_count": len(_error_log),
            "last_scene":      _last_scene_info.get("scene_name", ""),
        }


# ============================================================
# サーバーループ（スレッド内）
# ============================================================

def _run_server():
    """simple_websocketでサーバーを動かす"""
    global _server_running
    try:
        from simple_websocket import Server as WSServer
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((BRIDGE_HOST, BRIDGE_PORT))
        sock.listen(5)
        sock.settimeout(1.0)
        print(f"[bridge] リッスン開始: {BRIDGE_HOST}:{BRIDGE_PORT}")

        while _server_running:
            try:
                conn, addr = sock.accept()
                ws = WSServer(conn)
                print(f"[bridge] Godot接続: {addr}")
                t = threading.Thread(
                    target=_handle_client, args=(ws,), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except Exception as e:
                if _server_running:
                    print(f"[bridge] accept error: {e}")

        sock.close()
    except Exception as e:
        print(f"[bridge] サーバーエラー: {e}")
    finally:
        _server_running = False  # noqa: global already declared at function scope above


def _handle_client(ws):
    """1つのGodotクライアントを処理するスレッド"""
    global _stats, _last_scene_info

    with _lock:
        _clients.append(ws)
        _stats["connected_at"] = _now()

    # 接続確認メッセージ送信
    try:
        ws.send(json.dumps({
            "type":    "connected",
            "version": "1.0",
            "message": "Blackwell Bridge接続完了",
        }))
    except Exception:
        pass

    print("[bridge] クライアントハンドラ開始")

    try:
        while _server_running:
            try:
                raw = ws.receive(timeout=30)
                if raw is None:
                    break
                _process_message(raw)
            except Exception as e:
                if "timeout" not in str(e).lower():
                    print(f"[bridge] receive error: {e}")
                    break
    finally:
        with _lock:
            if ws in _clients:
                _clients.remove(ws)
        print("[bridge] クライアント切断")


def _process_message(raw: str):
    """Godotから受信したメッセージを処理する"""
    global _stats, _last_scene_info

    try:
        msg = json.loads(raw)
    except Exception:
        return

    with _lock:
        _stats["total_received"] += 1

    msg_type = msg.get("type", "")
    print(f"[bridge] 受信: {msg_type}")

    if msg_type == "error":
        # Godotのエラーログ
        entry = {
            "time":     _now(),
            "file":     msg.get("file", ""),
            "line":     msg.get("line", 0),
            "message":  msg.get("message", ""),
            "stack":    msg.get("stack", ""),
            "severity": msg.get("severity", "error"),
        }
        with _lock:
            _error_log.append(entry)
            if len(_error_log) > MAX_LOG_LINES:
                _error_log.pop(0)
            _stats["last_error"] = entry["message"][:80]

        # エラー自動修復（後述のerror_healer.pyと連携）
        _auto_heal_error(entry)

    elif msg_type == "fix_request":
        # 「このコードを直して」リクエスト
        with _lock:
            _pending_req.append({
                "time":    _now(),
                "file":    msg.get("file", ""),
                "code":    msg.get("code", ""),
                "problem": msg.get("problem", ""),
                "anchor":  msg.get("anchor", ""),
            })
            if len(_pending_req) > MAX_REQUESTS:
                _pending_req.pop(0)

    elif msg_type == "scene_info":
        # シーン構造の送信
        with _lock:
            _last_scene_info = msg.get("data", {})

    elif msg_type == "ping":
        send_to_godot({"type": "pong", "time": _now()})

    elif msg_type == "rl_step":
        # 強化学習: 1ステップの学習と次の行動を返す
        _handle_rl_step(msg)

    elif msg_type == "episode_start":
        try:
            from rl_trainer import start_episode
            ep_id = start_episode(_rl_project_path)
            send_to_godot({"type": "episode_ack", "episode": ep_id})
        except Exception as e:
            print(f"[bridge] episode_start失敗: {e}")

    elif msg_type == "file_saved":
        print(f"[bridge] Godotがファイル保存: {msg.get('file','')}")

    elif msg_type == "code_applied":
        print(f"[bridge] Godotがコード適用: {msg.get('file','')} "
              f"{'✅' if msg.get('success') else '❌'}")


def _auto_heal_error(error_entry: dict):
    """エラーを受信したら自動修復キューに積む"""
    try:
        from error_healer import queue_heal
        queue_heal(error_entry)
    except ImportError:
        pass
    except Exception as e:
        print(f"[bridge] auto_heal失敗: {e}")


# RLトレーニング用プロジェクトパス（start_bridge時に設定）
_rl_project_path = "./"

def set_rl_project_path(path: str):
    global _rl_project_path
    _rl_project_path = path


def _handle_rl_step(msg: dict):
    """RLステップを処理して次の行動を返す"""
    try:
        from rl_trainer import step, end_episode
        state      = msg.get("state", {})
        action     = msg.get("action", "idle")
        reward     = float(msg.get("reward", 0))
        next_state = msg.get("next_state", state)
        done       = bool(msg.get("done", False))

        next_action = step(
            _rl_project_path, state, action, reward, next_state, done)

        send_to_godot({"type": "rl_action", "action": next_action})

        if done:
            total_reward = float(msg.get("total_reward", reward))
            steps        = int(msg.get("steps", 1))
            result = end_episode(_rl_project_path, total_reward, steps)
            send_to_godot({
                "type":    "episode_end",
                "episode": result.episode_id,
                "reward":  result.total_reward,
                "epsilon": result.epsilon,
            })
    except Exception as e:
        print(f"[bridge] RL step失敗: {e}")


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ============================================================
# Blackwell → Godot: 便利な送信ヘルパー
# ============================================================

def send_code(file_name: str, code: str, auto_save: bool = True) -> bool:
    """修正済みコードをGodotに送る → プラグインが自動保存"""
    return send_to_godot({
        "type":      "write_file",
        "file":      file_name,
        "code":      code,
        "auto_save": auto_save,
        "time":      _now(),
    })


def send_reload(file_name: str = "") -> bool:
    """ファイルのリロードをGodotに指示"""
    return send_to_godot({
        "type": "reload",
        "file": file_name,
        "time": _now(),
    })


def send_notification(message: str, level: str = "info") -> bool:
    """Godotのエディタにトースト通知を送る"""
    return send_to_godot({
        "type":    "notify",
        "message": message,
        "level":   level,
        "time":    _now(),
    })


def request_scene_info() -> bool:
    """現在のシーン情報をGodotに要求"""
    return send_to_godot({"type": "get_scene_info"})


def get_last_scene_info() -> dict:
    with _lock:
        return dict(_last_scene_info)
