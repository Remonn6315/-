"""
Blackwell Dev-OS — autonomous_scheduler.py v1.0  (Phase 7)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 7: 自律実行エンジン（Autonomous Loop）

【何をするか】
  あなたが寝ている間にBlackwellが開発を進める。

  今まで:
    あなた → 指示 → Blackwell → コード → あなたが確認

  Phase 7:
    あなた: 「ローグライクゲームを完成させたい」
    Blackwell: 「わかりました。夜中に進めます」
         ↓ あなたが寝る
    深夜0時: バックログを確認 → 依存順序を解決 → 実行開始
    タスク1完了 → タスク2へ → ...
    問題発生 → 自己修正 → 継続
         ↓ 朝起きる
    Blackwell: 「昨夜5タスク完了。1タスク失敗。レポートがあります」

【4つのコンポーネント】
  1. BacklogManager  — タスクの追加・管理・優先順位
  2. DependencyResolver — 実行順序の自動解決
  3. NightBatch      — 夜間バッチ実行エンジン
  4. MorningReport   — 朝のサマリーレポート生成

【保存先】
  {project}/blackwell_brain/backlog.json      ← タスクキュー
  {project}/blackwell_brain/night_sessions.json ← 実行履歴
  {project}/blackwell_brain/morning_report.json ← 朝のレポート

【公開API】
  # バックログ管理
  add_task(path, title, file, desc, priority, depends_on) → str (task_id)
  get_backlog(path)          → list
  mark_done(path, task_id)   → None
  get_next_tasks(path, n)    → list  ← 依存関係を解決した実行順序

  # 夜間バッチ
  run_night_batch(path, anchor, max_tasks, auto_write) → NightResult
  get_night_status(path)     → dict

  # 朝のレポート
  get_morning_report(path)   → str
  has_new_report(path)       → bool
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


BRAIN_DIR       = "blackwell_brain"
BACKLOG_FILE    = "backlog.json"
SESSIONS_FILE   = "night_sessions.json"
REPORT_FILE     = "morning_report.json"
STATUS_FILE     = "batch_status.json"

MAX_NIGHT_TASKS = 10   # 1夜の最大タスク数（暴走防止）
MAX_RETRY       = 2    # タスク失敗時の最大リトライ数


# ============================================================
# データ構造
# ============================================================

@dataclass
class BacklogTask:
    task_id:    str
    title:      str
    file:       str
    desc:       str
    priority:   int      # 1=高 2=中 3=低
    depends_on: list     # 他のtask_idのリスト
    status:     str      # todo / running / done / failed / skipped
    added_at:   str
    done_at:    str = ""
    retry_count: int = 0
    result_summary: str = ""


@dataclass
class NightResult:
    session_id:   str
    started_at:   str
    finished_at:  str
    tasks_done:   int
    tasks_failed: int
    tasks_skipped: int
    summaries:    list    # 各タスクの結果サマリー
    total_ms:     int


# ============================================================
# 共通ユーティリティ
# ============================================================

def _brain_dir(project_path: str) -> str:
    d = os.path.join(project_path, BRAIN_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _load_json(project_path: str, filename: str, default):
    path = os.path.join(_brain_dir(project_path), filename)
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(project_path: str, filename: str, data):
    path = os.path.join(_brain_dir(project_path), filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _now() -> str:
    return datetime.now().isoformat()


def _task_id() -> str:
    return f"task_{datetime.now().strftime('%m%d_%H%M%S')}"


# ============================================================
# BacklogManager — タスクの追加・管理
# ============================================================

def add_task(project_path: str,
             title: str,
             file: str,
             desc: str,
             priority: int = 2,
             depends_on: list = None) -> str:
    """
    バックログにタスクを追加する。
    app.pyのUI・task_decomposer・手動で呼ぶ。

    Returns: task_id
    """
    backlog = _load_json(project_path, BACKLOG_FILE,
                         {"tasks": [], "version": 1})
    tid = _task_id()
    task = {
        "task_id":    tid,
        "title":      title[:100],
        "file":       file,
        "desc":       desc,
        "priority":   priority,
        "depends_on": depends_on or [],
        "status":     "todo",
        "added_at":   _now(),
        "done_at":    "",
        "retry_count": 0,
        "result_summary": "",
    }
    backlog["tasks"].append(task)
    _save_json(project_path, BACKLOG_FILE, backlog)
    print(f"[scheduler] タスク追加: {tid} / {title}")
    return tid


def add_tasks_bulk(project_path: str, tasks: list) -> list:
    """
    task_decomposerのTaskPlanから一括追加する。
    tasks = [{"title":..., "file":..., "desc":..., "priority":..., "depends_on":...}]
    """
    ids = []
    for t in tasks:
        tid = add_task(
            project_path,
            title=t.get("title", t.get("desc", "")[:40]),
            file=t.get("file", ""),
            desc=t.get("desc", ""),
            priority=t.get("priority", 2),
            depends_on=t.get("depends_on", []),
        )
        ids.append(tid)
    return ids


def get_backlog(project_path: str) -> list:
    """全バックログタスクを返す"""
    backlog = _load_json(project_path, BACKLOG_FILE, {"tasks": []})
    return backlog.get("tasks", [])


def mark_done(project_path: str, task_id: str,
              result_summary: str = ""):
    """タスクを完了マークする"""
    backlog = _load_json(project_path, BACKLOG_FILE, {"tasks": []})
    for t in backlog["tasks"]:
        if t["task_id"] == task_id:
            t["status"]         = "done"
            t["done_at"]        = _now()
            t["result_summary"] = result_summary[:200]
            break
    _save_json(project_path, BACKLOG_FILE, backlog)


def mark_failed(project_path: str, task_id: str, reason: str = ""):
    """タスクを失敗マークする"""
    backlog = _load_json(project_path, BACKLOG_FILE, {"tasks": []})
    for t in backlog["tasks"]:
        if t["task_id"] == task_id:
            t["status"]         = "failed"
            t["result_summary"] = reason[:200]
            break
    _save_json(project_path, BACKLOG_FILE, backlog)


def clear_done_tasks(project_path: str):
    """完了済みタスクをアーカイブする"""
    backlog = _load_json(project_path, BACKLOG_FILE, {"tasks": []})
    active  = [t for t in backlog["tasks"]
               if t["status"] not in ("done", "skipped")]
    done    = [t for t in backlog["tasks"]
               if t["status"] in ("done", "skipped")]
    backlog["tasks"]    = active
    backlog["archived"] = backlog.get("archived", []) + done
    _save_json(project_path, BACKLOG_FILE, backlog)
    print(f"[scheduler] {len(done)}件をアーカイブ")


# ============================================================
# DependencyResolver — 実行順序の自動解決
# ============================================================

def get_next_tasks(project_path: str, n: int = 5) -> list:
    """
    依存関係を解決して、今実行できるタスクをn件返す。

    ルール:
      - statusがtodoのタスクのみ
      - depends_onが全て"done"になっているタスクのみ
      - priority順（1が最高）でソート
      - 同優先度は追加日時が古い順
    """
    backlog = _load_json(project_path, BACKLOG_FILE, {"tasks": []})
    tasks   = backlog.get("tasks", [])

    # 完了済みIDのセット
    done_ids = {t["task_id"] for t in tasks
                if t["status"] == "done"}

    # 実行可能なタスクを抽出
    ready = []
    for t in tasks:
        if t["status"] != "todo":
            continue
        # 依存が全て完了しているか
        deps = t.get("depends_on", [])
        if all(d in done_ids for d in deps):
            ready.append(t)

    # priority昇順 → added_at昇順
    ready.sort(key=lambda x: (x.get("priority", 2),
                               x.get("added_at", "")))
    return ready[:n]


def get_backlog_stats(project_path: str) -> dict:
    """バックログの統計"""
    tasks = get_backlog(project_path)
    by_status = {}
    by_priority = {1: 0, 2: 0, 3: 0}
    for t in tasks:
        s = t.get("status", "todo")
        by_status[s] = by_status.get(s, 0) + 1
        p = t.get("priority", 2)
        if p in by_priority:
            by_priority[p] += 1

    todo  = by_status.get("todo", 0)
    done  = by_status.get("done", 0)
    total = len(tasks)

    return {
        "total":       total,
        "todo":        todo,
        "done":        done,
        "failed":      by_status.get("failed", 0),
        "running":     by_status.get("running", 0),
        "progress_pct": int(done / total * 100) if total else 0,
        "by_priority": by_priority,
        "next_tasks":  get_next_tasks(project_path, n=3),
    }


# ============================================================
# NightBatch — 夜間自律実行エンジン
# ============================================================

def run_night_batch(project_path: str,
                    anchor: str = "",
                    max_tasks: int = MAX_NIGHT_TASKS,
                    auto_write: bool = True,
                    on_progress=None) -> NightResult:
    """
    夜間バッチ実行。バックログのタスクを順番に自律実行する。

    on_progress: 進捗コールバック fn(msg: str) → app.pyのst.empty()更新用
    """
    session_id  = f"night_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    started_at  = _now()
    start_time  = time.time()
    summaries   = []
    done_count  = 0
    fail_count  = 0
    skip_count  = 0

    _set_status(project_path, {
        "running":    True,
        "session_id": session_id,
        "started_at": started_at,
        "progress":   "初期化中...",
        "done":       0,
        "failed":     0,
        "total":      max_tasks,
    })

    _progress(on_progress, f"🌙 夜間バッチ開始: {session_id}")

    # engine.pyの関数を動的import（循環import回避）
    try:
        from engine import process_task, plan, load_grand_state
        grand_state = load_grand_state(project_path)
    except Exception as e:
        _progress(on_progress, f"❌ engine.py import失敗: {e}")
        _set_status(project_path, {"running": False, "error": str(e)})
        return NightResult(
            session_id=session_id, started_at=started_at,
            finished_at=_now(), tasks_done=0, tasks_failed=1,
            tasks_skipped=0, summaries=[f"起動失敗: {e}"],
            total_ms=0,
        )

    executed = 0
    while executed < max_tasks:
        # 実行可能なタスクを取得
        next_tasks = get_next_tasks(project_path, n=1)
        if not next_tasks:
            _progress(on_progress, "✅ 実行可能なタスクがなくなりました")
            break

        task = next_tasks[0]
        tid  = task["task_id"]
        title = task.get("title", "")
        executed += 1

        _progress(on_progress,
                  f"⚡ [{executed}/{max_tasks}] 実行中: {title}")
        _set_status(project_path, {
            "running":  True,
            "progress": f"実行中: {title}",
            "done":     done_count,
            "failed":   fail_count,
        })

        # タスクをrunningにマーク
        _mark_running(project_path, tid)

        # 実行
        result_md, success = _execute_task_with_retry(
            task, project_path, anchor, auto_write,
            grand_state, on_progress
        )

        if success:
            done_count += 1
            mark_done(project_path, tid,
                      result_summary=_extract_summary(result_md))
            summaries.append({
                "task_id": tid,
                "title":   title,
                "status":  "done",
                "summary": _extract_summary(result_md),
            })
            _progress(on_progress, f"  ✅ 完了: {title}")
        else:
            fail_count += 1
            mark_failed(project_path, tid, reason=_extract_error(result_md))
            summaries.append({
                "task_id": tid,
                "title":   title,
                "status":  "failed",
                "summary": _extract_error(result_md),
            })
            _progress(on_progress, f"  ❌ 失敗: {title}")

        # 連続失敗で中断（3回連続失敗）
        recent_fails = sum(1 for s in summaries[-3:]
                           if s["status"] == "failed")
        if recent_fails >= 3:
            _progress(on_progress,
                      "⚠️ 連続3回失敗 → 安全のため中断")
            break

        # 少し休憩（モデルへの負荷軽減）
        time.sleep(2)

    finished_at = _now()
    total_ms    = int((time.time() - start_time) * 1000)

    # セッション履歴に保存
    result = NightResult(
        session_id=session_id,
        started_at=started_at,
        finished_at=finished_at,
        tasks_done=done_count,
        tasks_failed=fail_count,
        tasks_skipped=skip_count,
        summaries=summaries,
        total_ms=total_ms,
    )
    _save_session(project_path, result)

    # 朝のレポートを生成
    _generate_morning_report(project_path, result)

    _set_status(project_path, {
        "running":     False,
        "last_session": session_id,
        "done":        done_count,
        "failed":      fail_count,
        "finished_at": finished_at,
        "has_report":  True,
    })

    _progress(on_progress,
              f"🌅 夜間バッチ完了: {done_count}件成功 / {fail_count}件失敗 "
              f"/ {total_ms//1000}秒")
    return result


def _execute_task_with_retry(task: dict, project_path: str,
                              anchor: str, auto_write: bool,
                              grand_state: dict,
                              on_progress) -> tuple:
    """リトライ付きタスク実行"""
    from engine import process_task

    engine_task = {
        "file": task.get("file", "output.py"),
        "desc": task.get("desc", ""),
    }

    for attempt in range(MAX_RETRY + 1):
        if attempt > 0:
            _progress(on_progress,
                      f"  🔄 リトライ {attempt}/{MAX_RETRY}: {task.get('title','')}")
            time.sleep(3)

        try:
            result_md, success = process_task(
                engine_task,
                auto_write=auto_write,
                save_path=project_path,
                anchor=anchor,
                grand_state=grand_state,
            )
            if success:
                return result_md, True
        except Exception as e:
            result_md = f"例外発生: {e}"
            success   = False

    return result_md, False


def _mark_running(project_path: str, task_id: str):
    backlog = _load_json(project_path, BACKLOG_FILE, {"tasks": []})
    for t in backlog["tasks"]:
        if t["task_id"] == task_id:
            t["status"] = "running"
            break
    _save_json(project_path, BACKLOG_FILE, backlog)


def _extract_summary(result_md: str) -> str:
    """result_mdから1行サマリーを抽出"""
    lines = [l.strip() for l in result_md.splitlines()
             if l.strip() and not l.startswith("```")]
    return lines[0][:100] if lines else "完了"


def _extract_error(result_md: str) -> str:
    """result_mdからエラー内容を抽出"""
    m = re.search(r"ERROR[:\s]+(.+)", result_md)
    if m:
        return m.group(1)[:100]
    return result_md[:100]


def _progress(callback, msg: str):
    print(f"[scheduler] {msg}")
    if callback:
        try:
            callback(msg)
        except Exception:
            pass


def _set_status(project_path: str, updates: dict):
    status = _load_json(project_path, STATUS_FILE, {})
    status.update(updates)
    status["updated_at"] = _now()
    _save_json(project_path, STATUS_FILE, status)


def _save_session(project_path: str, result: NightResult):
    sessions = _load_json(project_path, SESSIONS_FILE,
                          {"sessions": []})
    sessions["sessions"].append({
        "session_id":    result.session_id,
        "started_at":    result.started_at,
        "finished_at":   result.finished_at,
        "tasks_done":    result.tasks_done,
        "tasks_failed":  result.tasks_failed,
        "total_ms":      result.total_ms,
        "summaries":     result.summaries[:20],
    })
    # 直近20セッションだけ保持
    sessions["sessions"] = sessions["sessions"][-20:]
    _save_json(project_path, SESSIONS_FILE, sessions)


# ============================================================
# MorningReport — 朝のサマリーレポート
# ============================================================

def _generate_morning_report(project_path: str,
                              result: NightResult):
    """夜間バッチ後に朝のレポートを生成する"""
    stats = get_backlog_stats(project_path)

    done_list  = [s for s in result.summaries if s["status"] == "done"]
    fail_list  = [s for s in result.summaries if s["status"] == "failed"]

    lines = [
        f"# 🌅 夜間バッチ完了レポート",
        f"**実行日時:** {result.started_at[:16].replace('T',' ')} 〜 "
        f"{result.finished_at[:16].replace('T',' ')}",
        f"**所要時間:** {result.total_ms // 1000}秒",
        "",
        "---",
        "",
        f"## 📊 サマリー",
        f"- ✅ 完了: **{result.tasks_done}件**",
        f"- ❌ 失敗: **{result.tasks_failed}件**",
        f"- 📋 残りバックログ: **{stats['todo']}件**",
        f"- 🏁 全体進捗: **{stats['progress_pct']}%**",
        "",
    ]

    if done_list:
        lines += ["## ✅ 完了したタスク", ""]
        for s in done_list:
            lines.append(f"- **{s['title']}**")
            if s.get("summary"):
                lines.append(f"  → {s['summary']}")
        lines.append("")

    if fail_list:
        lines += ["## ❌ 失敗したタスク（要確認）", ""]
        for s in fail_list:
            lines.append(f"- **{s['title']}**")
            if s.get("summary"):
                lines.append(f"  → エラー: {s['summary']}")
        lines.append("")

    next_tasks = get_next_tasks(project_path, n=3)
    if next_tasks:
        lines += ["## 📋 次に実行される予定のタスク", ""]
        for t in next_tasks:
            pri = ["", "🔴高", "🟡中", "🟢低"][t.get("priority", 2)]
            lines.append(f"- {pri} **{t['title']}** (`{t['file']}`)")
        lines.append("")

    report_text = "\n".join(lines)

    _save_json(project_path, REPORT_FILE, {
        "generated_at": _now(),
        "session_id":   result.session_id,
        "report":       report_text,
        "read":         False,
        "tasks_done":   result.tasks_done,
        "tasks_failed": result.tasks_failed,
    })
    print(f"[scheduler] 朝のレポートを生成しました")


def get_morning_report(project_path: str) -> str:
    data = _load_json(project_path, REPORT_FILE, {})
    return data.get("report", "レポートがありません")


def has_new_report(project_path: str) -> bool:
    data = _load_json(project_path, REPORT_FILE, {})
    return bool(data) and not data.get("read", True)


def mark_report_read(project_path: str):
    data = _load_json(project_path, REPORT_FILE, {})
    data["read"] = True
    _save_json(project_path, REPORT_FILE, data)


def get_night_status(project_path: str) -> dict:
    status   = _load_json(project_path, STATUS_FILE, {})
    sessions = _load_json(project_path, SESSIONS_FILE, {"sessions": []})
    recent   = sessions["sessions"][-3:] if sessions["sessions"] else []
    return {
        "is_running":    status.get("running", False),
        "progress":      status.get("progress", "待機中"),
        "last_session":  status.get("last_session", ""),
        "done":          status.get("done", 0),
        "failed":        status.get("failed", 0),
        "has_report":    status.get("has_report", False),
        "updated_at":    status.get("updated_at", ""),
        "recent_sessions": [
            {
                "session_id": s["session_id"],
                "started_at": s["started_at"][:16].replace("T", " "),
                "done":       s["tasks_done"],
                "failed":     s["tasks_failed"],
                "duration_s": s["total_ms"] // 1000,
            }
            for s in reversed(recent)
        ],
    }


# ============================================================
# バックグラウンドスレッド実行
# ============================================================

_batch_thread: Optional[threading.Thread] = None
_batch_running = False


def start_night_batch_bg(project_path: str,
                          anchor: str = "",
                          max_tasks: int = MAX_NIGHT_TASKS,
                          auto_write: bool = True,
                          on_progress=None):
    """
    バックグラウンドスレッドで夜間バッチを実行する。
    app.pyのボタンから呼ぶ。ブロッキングしない。
    """
    global _batch_thread, _batch_running

    if _batch_running:
        print("[scheduler] バッチ既に実行中")
        return False

    def _run():
        global _batch_running
        _batch_running = True
        try:
            run_night_batch(project_path, anchor, max_tasks,
                            auto_write, on_progress)
        finally:
            _batch_running = False

    _batch_thread = threading.Thread(target=_run, daemon=True)
    _batch_thread.start()
    print("[scheduler] バックグラウンドバッチ開始")
    return True


def stop_night_batch():
    """実行中のバッチを停止フラグで止める（次タスクの前に停止）"""
    global _batch_running
    _batch_running = False
    _set_status(".", {"running": False, "stopped": True})
    print("[scheduler] バッチ停止リクエスト")


def is_batch_running() -> bool:
    return _batch_running
