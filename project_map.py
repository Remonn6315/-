"""
Blackwell Dev-OS — project_map.py v1.0  (Phase 1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
プロジェクト地図 + 意図記憶

【Phase 1が解決する問題】
  ・1000行でも10000行でも壊さない
  ・AIはコード全体を読まず「地図」を見て作業する
  ・ファイルを修正するたびに地図が自動更新される

【保存先】
  {project_path}/blackwell_brain/project_map.json
  {project_path}/blackwell_brain/intent_store.json

【公開API】
  scan_project(path)                    → ProjectMap
  get_map_context(path, task_desc)      → str  ← engine.pyから呼ぶ
  update_file_entry(path, file_path)    → None ← ファイル書き込み後に呼ぶ
  store_intent(path, file, intent)      → None ← 意図を記録
  get_intent(path, file)                → str
  format_map_for_sidebar(path)          → str  ← app.pyサイドバー用
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import ast
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


BRAIN_DIR   = "blackwell_brain"
MAP_FILE    = "project_map.json"
INTENT_FILE = "intent_store.json"


# ============================================================
# データ構造
# ============================================================

@dataclass
class FunctionEntry:
    name:       str
    start_line: int
    end_line:   int
    args:       list = field(default_factory=list)
    docstring:  str  = ""


@dataclass
class FileEntry:
    path:         str          # プロジェクト相対パス
    role:         str  = ""    # このファイルの役割（1行）
    functions:    list = field(default_factory=list)   # FunctionEntry list
    dependencies: list = field(default_factory=list)   # 依存ファイル名リスト
    line_count:   int  = 0
    updated_at:   str  = ""
    language:     str  = ""    # python / gdscript / csharp


@dataclass
class ProjectMap:
    project_path: str
    files:        dict = field(default_factory=dict)   # rel_path → FileEntry
    scanned_at:   str  = ""
    total_lines:  int  = 0


# ============================================================
# スキャン
# ============================================================

_SUPPORTED_EXT = {".py", ".gd", ".cs", ".gd"}
_IGNORE_DIRS   = {".git", ".godot", "__pycache__", "chroma_db",
                  "blackwell_brain", "node_modules", ".venv"}


def scan_project(project_path: str) -> ProjectMap:
    """
    プロジェクト全体をスキャンして地図を生成・保存する。
    """
    pmap = ProjectMap(
        project_path=project_path,
        scanned_at=datetime.now().isoformat(),
    )

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in _SUPPORTED_EXT:
                continue
            full_path = os.path.join(root, fname)
            rel_path  = os.path.relpath(full_path, project_path)
            try:
                entry = _scan_file(full_path, rel_path)
                pmap.files[rel_path] = entry
                pmap.total_lines += entry.line_count
            except Exception as e:
                print(f"[project_map] スキャン失敗 {rel_path}: {e}")

    _save_map(project_path, pmap)
    print(f"[project_map] スキャン完了: {len(pmap.files)}ファイル / {pmap.total_lines}行")
    return pmap


def _scan_file(full_path: str, rel_path: str) -> FileEntry:
    """1ファイルをスキャンしてFileEntryを返す"""
    with open(full_path, encoding="utf-8", errors="ignore") as f:
        src = f.read()

    lines    = src.splitlines()
    ext      = os.path.splitext(full_path)[1].lower()
    lang     = _detect_lang(ext)
    funcs    = _extract_functions(src, lang)
    deps     = _extract_dependencies(src, lang, rel_path)
    role     = _infer_role(rel_path, funcs, src)

    return FileEntry(
        path=rel_path,
        role=role,
        functions=funcs,
        dependencies=deps,
        line_count=len(lines),
        updated_at=datetime.now().isoformat(),
        language=lang,
    )


def _detect_lang(ext: str) -> str:
    return {"py": "python", "gd": "gdscript", "cs": "csharp"}.get(ext.lstrip("."), "unknown")


def _extract_functions(src: str, lang: str) -> list:
    """関数一覧を抽出する"""
    funcs = []

    if lang == "python":
        try:
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = [a.arg for a in node.args.args]
                    doc  = ""
                    if (node.body and isinstance(node.body[0], ast.Expr)
                            and isinstance(node.body[0].value, ast.Constant)):
                        doc = str(node.body[0].value.value)[:80]
                    end = getattr(node, "end_lineno", node.lineno + 1)
                    funcs.append(FunctionEntry(
                        name=node.name, start_line=node.lineno,
                        end_line=end, args=args, docstring=doc
                    ))
        except Exception:
            pass

    elif lang in ("gdscript", "unknown"):
        # GDScript: func キーワードで検出
        func_starts = []
        for i, line in enumerate(src.splitlines(), 1):
            m = re.match(r"^(?:static\s+)?func\s+(\w+)\s*\(([^)]*)\)", line)
            if m:
                args = [a.strip().split(":")[0].strip()
                        for a in m.group(2).split(",") if a.strip()]
                func_starts.append((i, m.group(1), args))

        for idx, (lineno, name, args) in enumerate(func_starts):
            end = func_starts[idx+1][0] - 1 if idx+1 < len(func_starts) else lineno + 30
            funcs.append(FunctionEntry(
                name=name, start_line=lineno, end_line=end, args=args
            ))

    return funcs


def _extract_dependencies(src: str, lang: str, rel_path: str) -> list:
    """依存ファイルを抽出する"""
    deps = set()
    if lang == "python":
        for m in re.finditer(r"^(?:from|import)\s+([\w.]+)", src, re.MULTILINE):
            mod = m.group(1).split(".")[0]
            if not mod.startswith("_") and len(mod) > 2:
                deps.add(mod + ".py")
    elif lang == "gdscript":
        for m in re.finditer(r'(?:preload|load)\s*\(\s*["\']([^"\']+)["\']', src):
            deps.add(os.path.basename(m.group(1)))
        for m in re.finditer(r"extends\s+(\w+)", src):
            name = m.group(1)
            if name not in {"Node", "Node2D", "Node3D", "CharacterBody2D",
                            "CharacterBody3D", "Area2D", "RigidBody2D",
                            "Control", "CanvasLayer", "RefCounted", "Resource"}:
                deps.add(name + ".gd")
    return list(deps)


def _infer_role(rel_path: str, funcs: list, src: str) -> str:
    """ファイルの役割を1行で推測する"""
    name = os.path.splitext(os.path.basename(rel_path))[0].lower()
    func_names = [f.name for f in funcs]

    # 名前ベースの推測
    role_hints = {
        "player":      "プレイヤーキャラクター制御",
        "enemy":       "敵キャラクターAI",
        "game_manager":"ゲーム全体の状態管理",
        "gamemanager": "ゲーム全体の状態管理",
        "hud":         "UI・ヘッドアップディスプレイ",
        "ui":          "UIコンポーネント",
        "save":        "セーブ・ロードシステム",
        "dungeon":     "ダンジョン生成",
        "item":        "アイテムシステム",
        "camera":      "カメラ制御",
        "main":        "メインエントリポイント",
        "constants":   "定数定義",
        "manager":     "マネージャー",
        "engine":      "AIエンジン中枢",
        "memory":      "記憶システム",
        "app":         "UIアプリケーション本体",
    }
    for key, role in role_hints.items():
        if key in name:
            return role

    # 関数名ベースの推測
    if "_ready" in func_names or "_process" in func_names:
        return "Godotノードスクリプト"
    if "main" in func_names:
        return "メイン処理"
    if any(f in func_names for f in ["store", "save", "load", "get", "set"]):
        return "データ管理"

    return f"{os.path.basename(rel_path)} ({len(funcs)}関数)"


# ============================================================
# 保存・読み込み
# ============================================================

def _brain_dir(project_path: str) -> str:
    d = os.path.join(project_path, BRAIN_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _save_map(project_path: str, pmap: ProjectMap):
    path = os.path.join(_brain_dir(project_path), MAP_FILE)
    data = {
        "project_path": pmap.project_path,
        "scanned_at":   pmap.scanned_at,
        "total_lines":  pmap.total_lines,
        "files": {
            rel: {
                "path":         e.path,
                "role":         e.role,
                "language":     e.language,
                "line_count":   e.line_count,
                "updated_at":   e.updated_at,
                "dependencies": e.dependencies,
                "functions": [
                    {"name": f.name, "start": f.start_line,
                     "end": f.end_line, "args": f.args,
                     "doc": f.docstring}
                    for f in e.functions
                ],
            }
            for rel, e in pmap.files.items()
        }
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_map(project_path: str) -> Optional[ProjectMap]:
    path = os.path.join(_brain_dir(project_path), MAP_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        pmap = ProjectMap(
            project_path=data["project_path"],
            scanned_at=data.get("scanned_at", ""),
            total_lines=data.get("total_lines", 0),
        )
        for rel, ed in data.get("files", {}).items():
            funcs = [
                FunctionEntry(
                    name=fd["name"], start_line=fd["start"],
                    end_line=fd["end"], args=fd.get("args", []),
                    docstring=fd.get("doc", "")
                )
                for fd in ed.get("functions", [])
            ]
            pmap.files[rel] = FileEntry(
                path=ed["path"], role=ed.get("role", ""),
                functions=funcs,
                dependencies=ed.get("dependencies", []),
                line_count=ed.get("line_count", 0),
                updated_at=ed.get("updated_at", ""),
                language=ed.get("language", ""),
            )
        return pmap
    except Exception as e:
        print(f"[project_map] 地図読み込み失敗: {e}")
        return None


# ============================================================
# 単ファイル更新（engine.pyから呼ぶ）
# ============================================================

def update_file_entry(project_path: str, file_full_path: str):
    """
    1ファイルが書き換えられたときに地図を部分更新する。
    フルスキャンより高速。engine.pyのファイル書き込み直後に呼ぶ。
    """
    try:
        pmap = _load_map(project_path) or ProjectMap(project_path=project_path)
        rel_path = os.path.relpath(file_full_path, project_path)
        entry = _scan_file(file_full_path, rel_path)
        pmap.files[rel_path] = entry
        # total_lines再計算
        pmap.total_lines = sum(e.line_count for e in pmap.files.values())
        pmap.scanned_at  = datetime.now().isoformat()
        _save_map(project_path, pmap)
        print(f"[project_map] 地図更新: {rel_path} ({entry.line_count}行, {len(entry.functions)}関数)")
    except Exception as e:
        print(f"[project_map] update_file_entry失敗: {e}")


# ============================================================
# 意図記憶（intent_store）
# ============================================================

def store_intent(project_path: str, file_rel_path: str, intent: dict):
    """
    ファイルの「意図」を記録する。
    intent = {
        "role":        "このファイルが何をするか",
        "why":         "なぜこう設計したか",
        "do_not":      "触ってはいけないこと・やってはいけないこと",
        "depends_on":  "依存している重要な前提",
        "last_change": "最後の変更内容",
    }
    """
    path  = os.path.join(_brain_dir(project_path), INTENT_FILE)
    store = _load_intent_store(project_path)

    intent["updated_at"] = datetime.now().isoformat()
    store[file_rel_path] = intent

    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    print(f"[project_map] 意図記録: {file_rel_path}")


def get_intent(project_path: str, file_rel_path: str) -> dict:
    """ファイルの意図を取得する"""
    store = _load_intent_store(project_path)
    return store.get(file_rel_path, {})


def _load_intent_store(project_path: str) -> dict:
    path = os.path.join(_brain_dir(project_path), INTENT_FILE)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def auto_store_intent(project_path: str, file_rel_path: str,
                      code: str, task_desc: str, model: str = "qwen2.5-coder:14b"):
    """
    ファイル生成直後にAIが意図を自動抽出して記録する。
    engine.pyのprocess_task完了後に呼ぶ。
    """
    try:
        import ollama
        prompt = (
            "以下のコードを読んで、このファイルの「意図」をJSONで返してください。\n"
            "JSONのみ出力（前置き不要）:\n"
            "{\n"
            '  "role": "このファイルが何をするか（1行）",\n'
            '  "why": "なぜこう設計したか（1〜2行）",\n'
            '  "do_not": "触ってはいけないこと・注意点（箇条書き）",\n'
            '  "depends_on": "依存している重要な前提（1行）",\n'
            '  "last_change": "今回の変更内容（1行）"\n'
            "}\n\n"
            f"【タスク】{task_desc[:200]}\n\n"
            f"【コード】\n{code[:2000]}"
        )
        res  = ollama.chat(model=model,
                           messages=[{"role": "user", "content": prompt}])
        raw  = res["message"]["content"]
        m    = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            intent = json.loads(m.group(0))
            store_intent(project_path, file_rel_path, intent)
    except Exception as e:
        # 失敗しても最低限の意図を保存
        store_intent(project_path, file_rel_path, {
            "role":        os.path.basename(file_rel_path),
            "why":         task_desc[:100],
            "do_not":      "",
            "depends_on":  "",
            "last_change": task_desc[:100],
        })
        print(f"[project_map] 意図自動抽出失敗（最低限保存）: {e}")


# ============================================================
# engine.py用: AIへのコンテキスト生成
# ============================================================

def get_map_context(project_path: str, task_desc: str,
                    target_file: str = "") -> str:
    """
    タスクに関連する地図情報をAIへのコンテキストとして返す。
    engine.pyのprocess_task冒頭で呼ぶ。
    これにより「コード全体を渡す」必要がなくなる。
    """
    pmap = _load_map(project_path)
    if not pmap or not pmap.files:
        return ""

    parts = []

    # ① プロジェクト概要
    parts.append(
        f"【🗺️ プロジェクト地図】\n"
        f"総ファイル数: {len(pmap.files)} / 総行数: {pmap.total_lines:,}行"
    )

    # ② 全ファイルのサマリー（役割だけ・軽量）
    file_summary = []
    for rel, entry in sorted(pmap.files.items()):
        icon = {"python":"🐍","gdscript":"🎮","csharp":"🔷"}.get(entry.language, "📄")
        file_summary.append(f"  {icon} {rel} ({entry.line_count}行) — {entry.role}")
    parts.append("【ファイル一覧】\n" + "\n".join(file_summary[:20]))

    # ③ 対象ファイルの詳細（関数一覧・依存）
    if target_file:
        # target_fileに一致するエントリを探す
        rel_match = None
        for rel in pmap.files:
            if os.path.basename(rel) == os.path.basename(target_file) or rel == target_file:
                rel_match = rel
                break

        if rel_match:
            entry  = pmap.files[rel_match]
            intent = get_intent(project_path, rel_match)

            func_lines = []
            for f in entry.functions:
                sig = f"{f.name}({', '.join(f.args)})"
                doc = f" # {f.docstring}" if f.docstring else ""
                func_lines.append(f"    L{f.start_line}: {sig}{doc}")

            dep_str = "、".join(entry.dependencies) if entry.dependencies else "なし"

            detail = (
                f"【📄 対象ファイル詳細: {rel_match}】\n"
                f"役割: {entry.role}\n"
                f"行数: {entry.line_count}行 / 関数数: {len(entry.functions)}個\n"
                f"依存: {dep_str}\n"
                f"関数一覧:\n" + "\n".join(func_lines[:30])
            )
            if intent:
                do_not = intent.get("do_not", "")
                why    = intent.get("why", "")
                last   = intent.get("last_change", "")
                if do_not:
                    detail += f"\n\n⚠️ 触ってはいけないこと: {do_not}"
                if why:
                    detail += f"\n設計の理由: {why}"
                if last:
                    detail += f"\n前回の変更: {last}"
            parts.append(detail)

    # ④ 依存ファイルの関数シグネチャ（影響範囲の把握）
    if target_file and rel_match:
        entry = pmap.files.get(rel_match)
        if entry and entry.dependencies:
            dep_details = []
            for dep_name in entry.dependencies[:3]:
                for rel, dep_entry in pmap.files.items():
                    if os.path.basename(rel) == dep_name:
                        sigs = [f"{f.name}({', '.join(f.args)})"
                                for f in dep_entry.functions[:5]]
                        dep_details.append(
                            f"  {dep_name}: {', '.join(sigs)}"
                        )
                        break
            if dep_details:
                parts.append("【依存ファイルのAPI（壊さないために確認）】\n"
                              + "\n".join(dep_details))

    return "\n\n".join(parts)


# ============================================================
# app.py用: サイドバー表示
# ============================================================

def format_map_for_sidebar(project_path: str) -> dict:
    """
    サイドバー表示用のデータを返す。
    戻り値: {"files": [...], "total_lines": int, "total_files": int}
    """
    pmap = _load_map(project_path)
    if not pmap:
        return {"files": [], "total_lines": 0, "total_files": 0}

    files = []
    for rel, entry in sorted(pmap.files.items(),
                              key=lambda x: x[1].line_count, reverse=True):
        intent = get_intent(project_path, rel)
        files.append({
            "path":      rel,
            "role":      entry.role,
            "lines":     entry.line_count,
            "functions": len(entry.functions),
            "language":  entry.language,
            "deps":      entry.dependencies,
            "do_not":    intent.get("do_not", ""),
            "func_list": [f.name for f in entry.functions[:8]],
        })

    return {
        "files":       files,
        "total_lines": pmap.total_lines,
        "total_files": len(pmap.files),
        "scanned_at":  pmap.scanned_at,
    }


def get_map_stats(project_path: str) -> str:
    """地図の統計情報を1行で返す（ヘッダー表示用）"""
    pmap = _load_map(project_path)
    if not pmap:
        return "地図なし（スキャンしてください）"
    return (f"{len(pmap.files)}ファイル / "
            f"{pmap.total_lines:,}行 / "
            f"更新: {pmap.scanned_at[:16].replace('T',' ')}")
