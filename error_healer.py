"""
Blackwell Dev-OS — error_healer.py v2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⑤ エラー自動修復ループ（完全版）

【v1との違い】
  v1: Godotエラーのみ
  v2: Python traceback / ファイル監視 / 手動登録 / ログ監視 も対応

【修復フロー】
  エラーを受信 → 重複チェック → ファイル特定
  → process_task（最大2回リトライ）
  → 修正コードを保存 + Godot接続中なら自動送信
  → パターン学習（同じエラーは次回より速く直す）

【公開API】
  queue_heal(error_entry)              → None  Godotエラー
  queue_python_error(tb_str, file)     → None  Pythonエラー
  queue_manual(file, message, line)    → None  手動登録
  start_heal_loop(project_path, anchor)→ None
  start_file_watcher(project_path)     → None  ファイル監視
  stop_all()                           → None
  get_heal_stats()                     → dict
  get_heal_history(n)                  → list
  get_error_patterns()                 → list
"""

import json, os, re, threading, time
from collections import deque
from datetime import datetime
from pathlib import Path

# ─── 状態 ────────────────────────────────────────────────────
_queue         = deque(maxlen=100)
_lock          = threading.Lock()
_heal_running  = False
_watch_running = False
_recent_keys   = deque(maxlen=30)
_history       = deque(maxlen=200)
_patterns      = {}
_stats         = {"healed": 0, "failed": 0, "skipped": 0}

COOLDOWN_SEC   = 30
MAX_RETRIES    = 2
WATCH_INTERVAL = 3.0
WATCH_EXTS     = {".gd", ".py", ".cs"}
BRAIN_DIR      = "blackwell_brain"
HISTORY_FILE   = "heal_history.json"
PATTERNS_FILE  = "error_patterns.json"

_project_path  = "./"
_anchor        = ""

class ET:
    SYNTAX  = "syntax"
    RUNTIME = "runtime"
    LOGIC   = "logic"
    GODOT   = "godot"
    UNKNOWN = "unknown"

# ============================================================
# キューに積む
# ============================================================

def queue_heal(entry: dict) -> None:
    """Godotエラーをキューに追加（godot_bridge.pyから呼ぶ）"""
    msg  = entry.get("message", "")
    file = entry.get("file", "")
    line = entry.get("line", 0)
    key  = _mkey(file, line, msg)
    with _lock:
        if key in _recent_keys:
            _stats["skipped"] += 1
            return
        _recent_keys.append(key)
        _queue.append({**entry, "error_type": _classify_godot(msg),
                       "source": "godot", "queued_at": _now()})
    print(f"[healer] Godotエラー: {msg[:60]}")


def queue_python_error(traceback_str: str, file_hint: str = "") -> None:
    """Pythonのtracebackをキューに追加"""
    file, line, msg = _parse_tb(traceback_str)
    if not file and file_hint:
        file = file_hint
    key = _mkey(file, line, msg)
    with _lock:
        if key in _recent_keys:
            return
        _recent_keys.append(key)
        _queue.append({"file": file, "line": line, "message": msg,
                       "stack": traceback_str[:500],
                       "error_type": ET.RUNTIME, "source": "python",
                       "queued_at": _now()})
    print(f"[healer] Pythonエラー: {msg[:60]}")


def queue_manual(file: str, message: str,
                 line: int = 0, hint: str = "") -> None:
    """手動でエラーを登録（app.pyのボタンから）"""
    with _lock:
        _queue.append({"file": file, "line": line, "message": message,
                       "fix_hint": hint, "error_type": ET.UNKNOWN,
                       "source": "manual", "queued_at": _now()})
    print(f"[healer] 手動: {file}: {message[:40]}")


# ============================================================
# 修復ループ
# ============================================================

def start_heal_loop(project_path: str, anchor: str = "") -> None:
    global _heal_running, _project_path, _anchor
    if _heal_running:
        return
    _project_path = project_path
    _anchor       = anchor
    _heal_running = True
    _load_patterns(project_path)
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    print("[healer] 修復ループ起動")


def stop_all() -> None:
    global _heal_running, _watch_running
    _heal_running  = False
    _watch_running = False
    print("[healer] 停止")


def _loop():
    while _heal_running:
        entry = None
        with _lock:
            if _queue:
                entry = _queue.popleft()
        if entry:
            _heal_one(entry)
        else:
            time.sleep(1.5)


def _heal_one(entry: dict) -> None:
    file    = entry.get("file", "")
    line    = int(entry.get("line", 0))
    message = entry.get("message", "")
    stack   = entry.get("stack", "")
    hint    = entry.get("fix_hint", "")
    etype   = entry.get("error_type", ET.UNKNOWN)
    source  = entry.get("source", "?")

    print(f"[healer] 修復開始 [{source}] {file}:{line} — {message[:50]}")

    target = _resolve_file(file, _project_path)
    if not target:
        _record(entry, False, "ファイル解決失敗")
        with _lock:
            _stats["skipped"] += 1
        return

    pat_hint = _lookup_pattern(message)
    if pat_hint:
        hint = f"{hint}\n既知の修正方法: {pat_hint}" if hint else pat_hint

    type_label = {"syntax":"構文エラー","runtime":"実行時エラー",
                  "logic":"ロジックエラー","godot":"Godotエラー"}.get(etype,"エラー")
    task_parts = [
        f"【{type_label}を自動修正してください】",
        f"エラーメッセージ: {message}",
        f"発生ファイル: {file}",
    ]
    if line:
        task_parts.append(f"発生行: {line}")
    if stack:
        task_parts.append(f"スタックトレース:\n{stack[:400]}")
    if hint:
        task_parts.append(f"修正ヒント: {hint}")
    task_parts.append("エラーを修正した完全なコードを出力してください。")
    task_desc = "\n".join(task_parts)

    success = False
    result_md = ""
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"[healer]   試行 {attempt}/{MAX_RETRIES}")
        try:
            from engine import process_task, load_grand_state
            gs = load_grand_state(_project_path)
            result_md, success = process_task(
                {"file": target, "desc": task_desc},
                auto_write=True, save_path=_project_path,
                anchor=_anchor, grand_state=gs,
            )
            if success:
                break
            task_desc += f"\n\n※{attempt}回目失敗。別アプローチを試みてください。"
        except Exception as e:
            result_md = str(e)
            print(f"[healer]   例外: {e}")

    if success:
        _push_godot(target, _project_path)
        _learn_pattern(message, target, result_md)
        with _lock:
            _stats["healed"] += 1
        print(f"[healer] ✅ 修復成功: {target}")
    else:
        with _lock:
            _stats["failed"] += 1
        print(f"[healer] ❌ 修復失敗: {target}")

    _record(entry, success, result_md[:120])


# ============================================================
# ファイル監視
# ============================================================

def start_file_watcher(project_path: str) -> None:
    global _watch_running
    if _watch_running:
        return
    _watch_running = True
    t = threading.Thread(target=_watch_loop, args=(project_path,), daemon=True)
    t.start()
    print(f"[healer] ファイル監視開始: {project_path}")


def _watch_loop(project_path: str) -> None:
    mtimes: dict = {}
    while _watch_running:
        try:
            for root, _, files in os.walk(project_path):
                if any(s in root for s in [".git","blackwell_brain","__pycache__",".godot"]):
                    continue
                for fname in files:
                    if Path(fname).suffix.lower() not in WATCH_EXTS:
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        mtime = os.path.getmtime(fpath)
                    except OSError:
                        continue
                    if fpath in mtimes and mtime != mtimes[fpath]:
                        print(f"[healer] 変更検知: {fname}")
                        _check_syntax(fpath)
                    mtimes[fpath] = mtime
        except Exception as e:
            print(f"[healer] ウォッチャーエラー: {e}")
        time.sleep(WATCH_INTERVAL)


def _check_syntax(fpath: str) -> None:
    ext = Path(fpath).suffix.lower()
    if ext == ".py":
        try:
            import ast
            with open(fpath, encoding="utf-8") as f:
                src = f.read()
            ast.parse(src)
        except SyntaxError as e:
            queue_manual(fpath, f"SyntaxError: {e.msg}",
                         e.lineno or 0, hint=str(e.text or ""))
    elif ext == ".gd":
        try:
            with open(fpath, encoding="utf-8") as f:
                lines = f.readlines()
            checks = [
                (r'print\s+[^(]', "print()の括弧が不足（GDScript4では関数）"),
            ]
            for i, line in enumerate(lines, 1):
                for pat, msg in checks:
                    if re.search(pat, line.rstrip()):
                        queue_manual(os.path.basename(fpath), msg, i,
                                     hint=line.strip()[:60])
        except Exception:
            pass


# ============================================================
# パターン学習
# ============================================================

def _learn_pattern(msg: str, fixed_file: str, summary: str) -> None:
    key = _norm_err(msg)
    with _lock:
        if key not in _patterns:
            _patterns[key] = {"count": 0, "hint": "", "file": ""}
        _patterns[key]["count"] += 1
        _patterns[key]["file"]   = os.path.basename(fixed_file)
        if summary:
            _patterns[key]["hint"] = summary[:100]
    _save_patterns(_project_path)


def _lookup_pattern(msg: str) -> str:
    key = _norm_err(msg)
    with _lock:
        if key in _patterns:
            return _patterns[key].get("hint", "")
        words = set(key.split())
        best, hint = 0, ""
        for pk, pv in _patterns.items():
            ov = len(words & set(pk.split()))
            if ov > best:
                best, hint = ov, pv.get("hint","")
    return hint if best >= 2 else ""


def _norm_err(msg: str) -> str:
    s = re.sub(r"line\s+\d+", "line N", msg.lower())
    s = re.sub(r"'[^']*'", "'X'", s)
    s = re.sub(r'"[^"]*"', '"X"', s)
    s = re.sub(r"\b\d+\b", "N", s)
    return s[:80]


def _save_patterns(project_path: str) -> None:
    try:
        brain = os.path.join(project_path, BRAIN_DIR)
        os.makedirs(brain, exist_ok=True)
        with _lock:
            data = dict(_patterns)
        with open(os.path.join(brain, PATTERNS_FILE), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_patterns(project_path: str) -> None:
    try:
        path = os.path.join(project_path, BRAIN_DIR, PATTERNS_FILE)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            with _lock:
                _patterns.update(data)
            print(f"[healer] パターン読み込み: {len(data)}件")
    except Exception:
        pass


def get_error_patterns() -> list:
    with _lock:
        return [{"pattern": k, **v}
                for k, v in sorted(_patterns.items(),
                                    key=lambda x: -x[1].get("count",0))][:20]


# ============================================================
# Godotへ送信
# ============================================================

def _push_godot(target_file: str, project_path: str) -> None:
    try:
        from godot_bridge import send_code, is_connected, send_notification
        if not is_connected():
            return
        fp = os.path.join(project_path, target_file)
        if os.path.exists(fp):
            with open(fp, encoding="utf-8") as f:
                code = f.read()
            send_code(target_file, code)
            send_notification(f"✅ 自動修復: {target_file}", "info")
    except Exception:
        pass


# ============================================================
# 統計・履歴
# ============================================================

def _record(entry: dict, success: bool, summary: str) -> None:
    rec = {"time": _now(), "source": entry.get("source","?"),
           "file": entry.get("file",""), "line": entry.get("line",0),
           "error": entry.get("message","")[:80],
           "type": entry.get("error_type","?"),
           "success": success, "summary": summary}
    with _lock:
        _history.append(rec)
    try:
        brain = os.path.join(_project_path, BRAIN_DIR)
        os.makedirs(brain, exist_ok=True)
        path = os.path.join(brain, HISTORY_FILE)
        existing = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                existing = json.load(f).get("history", [])
        existing.append(rec)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"history": existing[-200:]}, f,
                      ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_heal_stats() -> dict:
    with _lock:
        return {**_stats, "running": _heal_running,
                "watching": _watch_running, "queue_size": len(_queue),
                "patterns_learned": len(_patterns)}


def get_heal_history(n: int = 20) -> list:
    try:
        path = os.path.join(_project_path, BRAIN_DIR, HISTORY_FILE)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return list(reversed(json.load(f).get("history",[])[-n:]))
    except Exception:
        pass
    with _lock:
        return list(reversed(list(_history)[-n:]))


# ============================================================
# ユーティリティ
# ============================================================

def _now() -> str:
    return datetime.now().strftime("%m/%d %H:%M:%S")

def _mkey(file: str, line: int, msg: str) -> str:
    return f"{os.path.basename(file)}:{line}:{msg[:40]}"

def _classify_godot(msg: str) -> str:
    m = msg.lower()
    if any(k in m for k in ["parse error","syntax error","unexpected token"]):
        return ET.SYNTAX
    if any(k in m for k in ["null instance","invalid get index","nonexistent function"]):
        return ET.LOGIC
    return ET.GODOT

def _parse_tb(tb: str) -> tuple:
    file = line = msg = ""
    m = re.search(r'File "([^"]+)", line (\d+)', tb)
    if m:
        file = m.group(1)
        line = int(m.group(2))
    lines = [l.strip() for l in tb.strip().splitlines() if l.strip()]
    if lines:
        msg = lines[-1]
    return file, line, msg

def _resolve_file(file_name: str, project_path: str) -> str:
    clean = file_name
    for prefix in ("res://", "user://"):
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
            break
    if os.path.isabs(clean) and os.path.exists(clean):
        return os.path.basename(clean)
    base = os.path.basename(clean)
    for root, _, files in os.walk(project_path):
        if any(s in root for s in [".git","blackwell_brain","__pycache__"]):
            continue
        for f in files:
            if f == base or f == clean:
                return f
    return base if base else ""
