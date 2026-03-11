"""
Blackwell Dev-OS — doc_sync.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⑥ ドキュメント自動生成・自動同期

【既存 doc_gen.py との違い】
  doc_gen.py  : 手動で呼んだときだけ生成する
  doc_sync.py : コードが変わったら自動で更新する

【管理するドキュメント】
  README.md        プロジェクト全体の説明・使い方
  DESIGN.md        設計書（アーキテクチャ・クラス図）
  API.md           全関数の説明（GDScript + Python）
  CHANGELOG.md     変更履歴（タスク完了のたびに自動追記）
  TODO.md          バックログと連動した TODO リスト

【自動同期トリガー】
  A. コードファイル保存時（error_healer の watcher と連動）
  B. タスク完了後（engine.py の process_task 完了後）
  C. 手動（app.py のボタン）

【差分検知】
  前回のドキュメント生成時のファイルハッシュを記録。
  変更されたファイルだけ再生成して無駄なAI呼び出しを減らす。

【公開API】
  sync_docs(project_path, anchor, force)    → SyncResult
  sync_on_task_complete(project_path, anchor, file_name, task_desc) → None
  get_doc_status(project_path)              → dict
  get_changelog(project_path, n)            → list
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


BRAIN_DIR    = "blackwell_brain"
DOC_META     = "doc_meta.json"      # ハッシュ・最終生成時刻
CHANGELOG_DB = "changelog.json"     # 変更履歴DB

# 生成するドキュメントファイル
DOC_FILES = {
    "readme":    "README.md",
    "design":    "DESIGN.md",
    "api":       "API.md",
    "changelog": "CHANGELOG.md",
    "todo":      "TODO.md",
}

MODEL = "qwen2.5-coder:14b"


# ============================================================
# データ構造
# ============================================================

@dataclass
class SyncResult:
    updated:  list   # 更新されたドキュメント名
    skipped:  list   # 変更なしでスキップ
    failed:   list   # 生成失敗
    timestamp: str


# ============================================================
# ユーティリティ
# ============================================================

def _brain(project_path: str) -> str:
    d = os.path.join(project_path, BRAIN_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _load(project_path: str, filename: str, default):
    path = os.path.join(_brain(project_path), filename)
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(project_path: str, filename: str, data):
    path = os.path.join(_brain(project_path), filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _now() -> str:
    return datetime.now().isoformat()[:16].replace("T", " ")


def _ai(prompt: str, model: str = MODEL) -> str:
    try:
        import ollama
        res = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return res["message"]["content"]
    except Exception as e:
        return f"[生成失敗: {e}]"


def _write_doc(project_path: str, doc_key: str, content: str) -> str:
    """ドキュメントをプロジェクトルートに書き込む"""
    fname = DOC_FILES[doc_key]
    path  = os.path.join(project_path, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _read_doc(project_path: str, doc_key: str) -> str:
    fname = DOC_FILES[doc_key]
    path  = os.path.join(project_path, fname)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


# ============================================================
# ファイルハッシュ差分検知
# ============================================================

def _hash_project(project_path: str) -> dict:
    """プロジェクトのコードファイルのハッシュを計算"""
    hashes = {}
    for root, _, files in os.walk(project_path):
        if any(s in root for s in [".git", "blackwell_brain",
                                    "__pycache__", ".godot"]):
            continue
        for fname in files:
            if Path(fname).suffix.lower() not in {".gd", ".py", ".cs", ".json"}:
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "rb") as f:
                    h = hashlib.md5(f.read()).hexdigest()[:8]
                hashes[os.path.relpath(fpath, project_path)] = h
            except Exception:
                pass
    return hashes


def _has_changed(project_path: str, doc_key: str) -> bool:
    """前回の生成後にコードが変わったか"""
    meta    = _load(project_path, DOC_META, {})
    current = _hash_project(project_path)
    stored  = meta.get(f"{doc_key}_hashes", {})
    return current != stored


def _save_hashes(project_path: str, doc_key: str):
    meta = _load(project_path, DOC_META, {})
    meta[f"{doc_key}_hashes"]   = _hash_project(project_path)
    meta[f"{doc_key}_updated"]  = _now()
    _save(project_path, DOC_META, meta)


# ============================================================
# ドキュメント生成
# ============================================================

def _collect_code_summary(project_path: str,
                           max_files: int = 20) -> str:
    """プロジェクトのコードを収集してサマリーテキストを作る"""
    lines = []
    for root, _, files in os.walk(project_path):
        if any(s in root for s in [".git", "blackwell_brain",
                                    "__pycache__", ".godot"]):
            continue
        for fname in sorted(files):
            if Path(fname).suffix.lower() not in {".gd", ".py", ".cs"}:
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    code = f.read(3000)   # 先頭3000文字
                rel  = os.path.relpath(fpath, project_path)
                lines.append(f"\n### {rel}\n```\n{code[:1500]}\n```")
            except Exception:
                pass
            if len(lines) >= max_files:
                break
        if len(lines) >= max_files:
            break
    return "\n".join(lines)


def _gen_readme(project_path: str, anchor: str) -> str:
    code_summary = _collect_code_summary(project_path, max_files=10)
    prompt = (
        f"以下のゲームプロジェクトのコードを見て、README.mdを日本語で作成してください。\n"
        f"ゲーム概要: {anchor[:200] if anchor else '不明'}\n\n"
        f"コード:\n{code_summary[:3000]}\n\n"
        "以下のセクションを含めてください:\n"
        "# プロジェクト名\n"
        "## 概要\n"
        "## ゲームの特徴\n"
        "## ファイル構成\n"
        "## 実行方法\n"
        "## 開発状況\n\n"
        "Markdownで出力してください。"
    )
    return _ai(prompt)


def _gen_design(project_path: str, anchor: str) -> str:
    code_summary = _collect_code_summary(project_path, max_files=15)

    # project_map.jsonがあれば使う
    map_info = ""
    try:
        map_path = os.path.join(_brain(project_path), "project_map.json")
        if os.path.exists(map_path):
            with open(map_path, encoding="utf-8") as f:
                pmap = json.load(f)
            files = list(pmap.keys())[:15]
            map_info = "ファイル一覧: " + ", ".join(files)
    except Exception:
        pass

    prompt = (
        "このゲームプロジェクトの設計書（DESIGN.md）を日本語で作成してください。\n\n"
        f"ゲーム概要: {anchor[:200] if anchor else '不明'}\n"
        f"{map_info}\n\n"
        f"コード:\n{code_summary[:3000]}\n\n"
        "以下のセクションを含めてください:\n"
        "# 設計書\n"
        "## アーキテクチャ概要\n"
        "## クラス・ノード構成\n"
        "## データフロー\n"
        "## 重要な設計判断\n"
        "## 既知の制約・注意事項\n\n"
        "Markdownで出力してください。"
    )
    return _ai(prompt)


def _gen_api(project_path: str) -> str:
    """全関数の説明を生成"""
    func_list = []
    for root, _, files in os.walk(project_path):
        if any(s in root for s in [".git", "blackwell_brain",
                                    "__pycache__", ".godot"]):
            continue
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext not in {".gd", ".py"}:
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    code = f.read()
                rel = os.path.relpath(fpath, project_path)

                # 関数名を抽出
                if ext == ".py":
                    funcs = re.findall(r"^def (\w+)\(", code, re.MULTILINE)
                else:
                    funcs = re.findall(r"^func (\w+)\(", code, re.MULTILINE)

                if funcs:
                    func_list.append(
                        f"**{rel}**: " + ", ".join(f"`{f}()`" for f in funcs[:10]))
            except Exception:
                pass

    if not func_list:
        return "# API リファレンス\n\nまだ関数がありません。"

    func_text = "\n".join(func_list[:30])
    prompt = (
        "以下のゲームプロジェクトの関数一覧から、API.mdを日本語で作成してください。\n\n"
        f"{func_text}\n\n"
        "各関数について:\n"
        "- 何をする関数か\n"
        "- 引数・返り値\n"
        "- 使い方の例\n\n"
        "Markdownの表形式で出力してください。"
    )
    return _ai(prompt)


def _gen_todo(project_path: str) -> str:
    """バックログと連動したTODO.md"""
    lines = ["# TODO リスト", f"\n> 最終更新: {_now()}\n"]

    # バックログから取得
    try:
        from autonomous_scheduler import get_backlog
        backlog = get_backlog(project_path)
        pending = [t for t in backlog if t.get("status") == "pending"]
        done    = [t for t in backlog if t.get("status") == "done"]

        if pending:
            lines.append("## 未完了")
            for t in pending[:20]:
                pri_mark = {1:"🔴", 2:"🟡", 3:"🟢"}.get(
                    t.get("priority", 2), "⚪")
                lines.append(
                    f"- {pri_mark} **{t.get('title','')}**"
                    + (f"\n  - {t.get('desc','')[:80]}" if t.get("desc") else "")
                )

        if done:
            lines.append("\n## 完了済み（直近10件）")
            for t in done[-10:]:
                lines.append(f"- ~~{t.get('title','')}~~")

    except Exception:
        lines.append("バックログデータなし")

    return "\n".join(lines)


def _append_changelog(project_path: str,
                       task_desc: str,
                       file_name: str) -> None:
    """CHANGELOG.md と changelog.json に変更を追記する"""
    entry = {
        "date":  _now(),
        "file":  file_name,
        "task":  task_desc[:100],
    }

    # JSON DB に保存
    db = _load(project_path, CHANGELOG_DB, {"entries": []})
    db["entries"].append(entry)
    db["entries"] = db["entries"][-500:]
    _save(project_path, CHANGELOG_DB, db)

    # CHANGELOG.md に追記
    path    = os.path.join(project_path, DOC_FILES["changelog"])
    new_line = f"- `{entry['date']}` **{file_name}** — {entry['task']}\n"

    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            existing = f.read()
        # ヘッダーの直後に挿入
        if "## 変更履歴" in existing:
            existing = existing.replace(
                "## 変更履歴\n",
                f"## 変更履歴\n{new_line}"
            )
        else:
            existing = new_line + existing
    else:
        existing = (
            "# 変更履歴\n\n"
            f"> Blackwell Dev-OS が自動管理します\n\n"
            "## 変更履歴\n"
            + new_line
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write(existing)


# ============================================================
# 公開API
# ============================================================

def sync_docs(project_path: str,
              anchor: str = "",
              force: bool = False) -> SyncResult:
    """
    変更されたファイルに対応するドキュメントを再生成する。
    force=True で全ドキュメントを強制再生成。
    """
    updated = []
    skipped = []
    failed  = []

    print(f"[doc_sync] ドキュメント同期開始 (force={force})")

    generators = {
        "readme":    lambda: _gen_readme(project_path, anchor),
        "design":    lambda: _gen_design(project_path, anchor),
        "api":       lambda: _gen_api(project_path),
        "todo":      lambda: _gen_todo(project_path),
    }

    for key, gen_fn in generators.items():
        if not force and not _has_changed(project_path, key):
            skipped.append(key)
            print(f"[doc_sync] スキップ: {DOC_FILES[key]} (変更なし)")
            continue

        print(f"[doc_sync] 生成中: {DOC_FILES[key]}")
        try:
            content = gen_fn()
            if content and not content.startswith("[生成失敗"):
                _write_doc(project_path, key, content)
                _save_hashes(project_path, key)
                updated.append(key)
                print(f"[doc_sync] ✅ 更新: {DOC_FILES[key]}")
            else:
                failed.append(key)
                print(f"[doc_sync] ❌ 失敗: {DOC_FILES[key]}: {content[:50]}")
        except Exception as e:
            failed.append(key)
            print(f"[doc_sync] ❌ 例外: {DOC_FILES[key]}: {e}")

    result = SyncResult(
        updated=updated,
        skipped=skipped,
        failed=failed,
        timestamp=_now(),
    )
    print(f"[doc_sync] 完了: 更新{len(updated)} / スキップ{len(skipped)} / 失敗{len(failed)}")
    return result


def sync_on_task_complete(project_path: str,
                           anchor: str,
                           file_name: str,
                           task_desc: str) -> None:
    """
    engine.py の process_task 完了後に呼ぶ。
    CHANGELOG を自動更新し、差分があれば他ドキュメントも更新。
    """
    # 常にCHANGELOGは更新
    _append_changelog(project_path, task_desc, file_name)

    # TODO.mdはバックログと連動するので毎回更新
    try:
        content = _gen_todo(project_path)
        _write_doc(project_path, "todo", content)
    except Exception:
        pass

    print(f"[doc_sync] CHANGELOG・TODO 更新: {file_name}")


def get_doc_status(project_path: str) -> dict:
    """各ドキュメントの存在・最終更新日時を返す"""
    meta   = _load(project_path, DOC_META, {})
    status = {}
    for key, fname in DOC_FILES.items():
        path    = os.path.join(project_path, fname)
        exists  = os.path.exists(path)
        updated = meta.get(f"{key}_updated", "")
        size    = os.path.getsize(path) if exists else 0
        changed = _has_changed(project_path, key) if exists else True
        status[key] = {
            "filename":    fname,
            "exists":      exists,
            "updated":     updated,
            "size_kb":     round(size / 1024, 1),
            "needs_update": changed,
        }
    return status


def get_changelog(project_path: str, n: int = 20) -> list:
    db = _load(project_path, CHANGELOG_DB, {"entries": []})
    return list(reversed(db.get("entries", [])[-n:]))
