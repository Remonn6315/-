"""
Blackwell Dev-OS — health_check.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
プロジェクト健康診断

ボタン1つでプロジェクト全体をスキャン:
  • 未使用素材  • 重複コード  • TODO未処理
  • Godot3 API残存  • 循環import  • 空ファイル
  • 長すぎる関数  • マジックナンバー  • デッドコード

【公開API】
  run_health_check(project_path) → HealthReport
  format_report(report) → str (Markdown)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os, re, ast, hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class HealthIssue:
    severity:   str        # critical / warning / info
    category:   str
    message:    str
    file:       str = ""
    line:       int = 0
    suggestion: str = ""


@dataclass
class HealthReport:
    project_path: str
    issues:       list = field(default_factory=list)
    stats:        dict = field(default_factory=dict)
    score:        int  = 100   # 0〜100
    grade:        str  = "A"


# ── Godot3 残存APIパターン ─────────────────────────────────
GODOT3_PATTERNS = [
    (r"\bKinematicBody2D\b",              "KinematicBody2D → CharacterBody2D"),
    (r"\bKinematicBody\b",               "KinematicBody → CharacterBody3D"),
    (r"\bmove_and_slide\s*\(\s*\w",      "move_and_slide(vel) → velocity=vel; move_and_slide()"),
    (r"\byield\s*\(",                     "yield() → await"),
    (r"onready\s+var\b",                 "onready var → @onready var"),
    (r"export\s+var\b",                  "export var → @export var"),
    (r'\.connect\s*\(\s*"[^"]+"\s*,\s*self', "古いconnect() → シグナル.connect(callable)"),
    (r"\brand_range\s*\(",               "rand_range() → randf_range() / randi_range()"),
    (r"OS\.get_ticks_msec",              "OS.get_ticks_msec() → Time.get_ticks_msec()"),
    (r"get_tree\(\)\.change_scene\b",    "change_scene() → change_scene_to_file()"),
    (r"\bSprite\b(?!2D|3D|Base|Frames)", "Sprite → Sprite2D"),
    (r"set_fixed_process\s*\(",          "set_fixed_process() は不要（_physics_processが自動実行）"),
]

# ── 長すぎる関数の閾値 ────────────────────────────────────
LONG_FUNC_LINES = 80

# ── マジックナンバーのしきい値 ────────────────────────────
MAGIC_NUMBER_THRESHOLD = 5  # 同じリテラルが5回以上


def _get_files(project_path: str, exts: tuple) -> list:
    """指定拡張子のファイル一覧を取得"""
    files = []
    for root, dirs, filenames in os.walk(project_path):
        # 不要なディレクトリをスキップ
        dirs[:] = [d for d in dirs if d not in {
            ".git", ".godot", "__pycache__", "node_modules",
            "chroma_db", "export", ".blackwell_cache"
        }]
        for fn in filenames:
            if fn.endswith(exts):
                files.append(os.path.join(root, fn))
    return files


# ============================================================
# チェック関数群
# ============================================================

def _check_todos(project_path: str) -> list[HealthIssue]:
    """TODO / FIXME / HACK / XXX を検出"""
    issues = []
    todo_pattern = re.compile(r"#\s*(TODO|FIXME|HACK|XXX|BUG|TEMP)\s*[:\s]*(.*)", re.IGNORECASE)

    for fp in _get_files(project_path, (".py", ".gd", ".cs", ".cpp", ".h")):
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    m = todo_pattern.search(line)
                    if m:
                        tag  = m.group(1).upper()
                        text = m.group(2).strip()[:60]
                        sev  = "critical" if tag in ("FIXME","BUG") else "warning"
                        issues.append(HealthIssue(
                            severity=sev, category="todo",
                            message=f"{tag}: {text or '（説明なし）'}",
                            file=os.path.relpath(fp, project_path), line=i,
                            suggestion="対応してからコメントを削除してください"
                        ))
        except Exception:
            pass
    return issues


def _check_duplicate_code(project_path: str) -> list[HealthIssue]:
    """ハッシュベースの重複コードブロック検出（10行以上）"""
    issues = []
    block_map: dict[str, list] = {}
    BLOCK_SIZE = 10

    for fp in _get_files(project_path, (".py", ".gd")):
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                lines = [l.strip() for l in f.readlines() if l.strip() and not l.strip().startswith("#")]

            for i in range(len(lines) - BLOCK_SIZE):
                block = "\n".join(lines[i:i+BLOCK_SIZE])
                h = hashlib.md5(block.encode()).hexdigest()
                rel = os.path.relpath(fp, project_path)
                if h not in block_map:
                    block_map[h] = []
                block_map[h].append((rel, i+1))
        except Exception:
            pass

    for h, locations in block_map.items():
        if len(locations) >= 2:
            loc_str = " / ".join(f"{f}:{l}" for f, l in locations[:3])
            issues.append(HealthIssue(
                severity="warning", category="duplicate",
                message=f"重複コードブロック（{BLOCK_SIZE}行）: {loc_str}",
                suggestion="共通関数に抽出してDRY原則を適用してください"
            ))
    return issues[:10]  # 最大10件


def _check_godot3_api(project_path: str) -> list[HealthIssue]:
    """Godot3のAPI残存チェック"""
    issues = []
    for fp in _get_files(project_path, (".gd",)):
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    for pattern, suggestion in GODOT3_PATTERNS:
                        if re.search(pattern, line):
                            issues.append(HealthIssue(
                                severity="critical", category="godot3_api",
                                message=f"Godot3 API残存: {line.strip()[:60]}",
                                file=os.path.relpath(fp, project_path), line=i,
                                suggestion=suggestion
                            ))
        except Exception:
            pass
    return issues


def _check_long_functions(project_path: str) -> list[HealthIssue]:
    """長すぎる関数の検出"""
    issues = []

    # Python
    for fp in _get_files(project_path, (".py",)):
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                src = f.read()
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    end = getattr(node, "end_lineno", node.lineno + 1)
                    length = end - node.lineno
                    if length > LONG_FUNC_LINES:
                        issues.append(HealthIssue(
                            severity="warning", category="long_function",
                            message=f"長すぎる関数: {node.name}() ({length}行)",
                            file=os.path.relpath(fp, project_path), line=node.lineno,
                            suggestion=f"80行以下に分割してください（現在{length}行）"
                        ))
        except Exception:
            pass

    # GDScript (funcキーワードで判定)
    for fp in _get_files(project_path, (".gd",)):
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            func_start = None
            func_name  = ""
            indent_lvl = 0
            for i, line in enumerate(lines):
                m = re.match(r"^(func\s+(\w+)\s*\()", line)
                if m:
                    func_start = i
                    func_name  = m.group(2)
                elif func_start is not None:
                    # 次のfuncまたはファイル終端で長さ計算
                    if re.match(r"^func\s+", line) or i == len(lines)-1:
                        length = i - func_start
                        if length > LONG_FUNC_LINES:
                            issues.append(HealthIssue(
                                severity="warning", category="long_function",
                                message=f"長すぎる関数: {func_name}() ({length}行)",
                                file=os.path.relpath(fp, project_path), line=func_start+1,
                                suggestion=f"80行以下に分割してください"
                            ))
                        func_start = i
                        func_name  = re.match(r"func\s+(\w+)", line).group(1) if re.match(r"func\s+(\w+)", line) else ""
        except Exception:
            pass

    return issues


def _check_unused_assets(project_path: str) -> list[HealthIssue]:
    """未使用素材の検出（コード内での参照チェック）"""
    issues = []
    asset_exts = (".png", ".jpg", ".jpeg", ".webp", ".svg",
                  ".wav", ".mp3", ".ogg", ".flac")
    code_exts  = (".gd", ".py", ".cs", ".tscn", ".tres", ".json")

    # 全素材ファイルを収集
    assets = []
    for fp in _get_files(project_path, asset_exts):
        assets.append((os.path.basename(fp), fp))

    if not assets:
        return []

    # コードファイルの全テキストを結合
    code_text = ""
    for fp in _get_files(project_path, code_exts):
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                code_text += f.read() + "\n"
        except Exception:
            pass

    # 参照チェック
    for name, full_path in assets:
        stem = os.path.splitext(name)[0]  # 拡張子なし
        if name not in code_text and stem not in code_text:
            size_kb = os.path.getsize(full_path) // 1024
            issues.append(HealthIssue(
                severity="info", category="unused_asset",
                message=f"未使用素材: {name} ({size_kb}KB)",
                file=os.path.relpath(full_path, project_path),
                suggestion="不要であれば削除してプロジェクトをスリムにしてください"
            ))

    return issues[:20]  # 最大20件


def _check_empty_files(project_path: str) -> list[HealthIssue]:
    """空ファイル・ほぼ空のファイルを検出"""
    issues = []
    for fp in _get_files(project_path, (".py", ".gd", ".cs")):
        try:
            size = os.path.getsize(fp)
            if size == 0:
                issues.append(HealthIssue(
                    severity="info", category="empty_file",
                    message=f"空ファイル: {os.path.relpath(fp, project_path)}",
                    file=os.path.relpath(fp, project_path),
                    suggestion="不要なら削除してください"
                ))
            elif size < 50:
                with open(fp, encoding="utf-8", errors="ignore") as f:
                    content = f.read().strip()
                if len(content) < 30 and content not in ("pass", ""):
                    issues.append(HealthIssue(
                        severity="info", category="empty_file",
                        message=f"ほぼ空ファイル ({size}bytes): {os.path.relpath(fp, project_path)}",
                        file=os.path.relpath(fp, project_path),
                    ))
        except Exception:
            pass
    return issues


def _check_magic_numbers(project_path: str) -> list[HealthIssue]:
    """マジックナンバーの検出（定数化を推奨）"""
    issues = []
    # ゲーム開発でよく問題になる具体的な数値
    magic_pattern = re.compile(r"\b([2-9][0-9]{2,}|[1-9][0-9]{3,})\b")  # 200以上の数値

    for fp in _get_files(project_path, (".py", ".gd")):
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                content = f.read()
            counts: dict[str, int] = {}
            for m in magic_pattern.finditer(content):
                n = m.group(1)
                counts[n] = counts.get(n, 0) + 1

            for num, count in counts.items():
                if count >= MAGIC_NUMBER_THRESHOLD:
                    issues.append(HealthIssue(
                        severity="info", category="magic_number",
                        message=f"マジックナンバー {num} が{count}回登場",
                        file=os.path.relpath(fp, project_path),
                        suggestion=f"const SPEED = {num} のように定数化してください"
                    ))
        except Exception:
            pass
    return issues[:10]


# ============================================================
# メイン診断関数
# ============================================================

def run_health_check(project_path: str) -> HealthReport:
    """プロジェクト全体の健康診断を実行"""
    report = HealthReport(project_path=project_path)

    checkers = [
        ("TODO/FIXME検出",      _check_todos),
        ("Godot3 API残存チェック", _check_godot3_api),
        ("重複コード検出",        _check_duplicate_code),
        ("長すぎる関数",          _check_long_functions),
        ("未使用素材",            _check_unused_assets),
        ("空ファイル",            _check_empty_files),
        ("マジックナンバー",       _check_magic_numbers),
    ]

    all_issues = []
    for name, checker in checkers:
        try:
            found = checker(project_path)
            all_issues.extend(found)
        except Exception as e:
            all_issues.append(HealthIssue(
                severity="info", category="check_error",
                message=f"チェック失敗({name}): {e}"
            ))

    report.issues = all_issues

    # 統計
    critical = sum(1 for i in all_issues if i.severity == "critical")
    warnings  = sum(1 for i in all_issues if i.severity == "warning")
    infos     = sum(1 for i in all_issues if i.severity == "info")

    # ファイル数カウント
    total_code  = len(_get_files(project_path, (".py",".gd",".cs",".cpp")))
    total_assets= len(_get_files(project_path, (".png",".jpg",".wav",".mp3",".ogg")))

    report.stats = {
        "critical": critical, "warnings": warnings, "info": infos,
        "total_issues": len(all_issues),
        "code_files": total_code, "asset_files": total_assets,
    }

    # スコア計算
    score = 100
    score -= critical * 15
    score -= warnings * 5
    score -= infos * 1
    score = max(0, min(100, score))
    report.score = score

    if score >= 90:   report.grade = "A"
    elif score >= 75: report.grade = "B"
    elif score >= 60: report.grade = "C"
    elif score >= 40: report.grade = "D"
    else:             report.grade = "F"

    return report


def format_report(report: HealthReport) -> str:
    """診断レポートをMarkdownで出力"""
    grade_emoji = {"A": "🏆", "B": "✅", "C": "⚠️", "D": "🔴", "F": "💀"}.get(report.grade, "❓")
    s = report.stats

    lines = [
        f"## {grade_emoji} プロジェクト健康診断 — スコア: **{report.score}/100** (グレード: {report.grade})",
        "",
        f"| コードファイル | 素材ファイル | 重大問題 | 警告 | 情報 |",
        f"|---|---|---|---|---|",
        f"| {s.get('code_files',0)} | {s.get('asset_files',0)} | 🔴{s.get('critical',0)} | 🟡{s.get('warnings',0)} | 🟢{s.get('info',0)} |",
        "",
    ]

    # 重大問題
    crits = [i for i in report.issues if i.severity == "critical"]
    if crits:
        lines.append("### 🔴 重大問題（今すぐ修正）")
        for i in crits[:10]:
            loc = f" `{i.file}:{i.line}`" if i.file else ""
            lines.append(f"- **{i.message}**{loc}")
            if i.suggestion:
                lines.append(f"  → {i.suggestion}")
        lines.append("")

    # 警告
    warns = [i for i in report.issues if i.severity == "warning"]
    if warns:
        lines.append("### 🟡 警告（できれば修正）")
        cats: dict[str, list] = {}
        for i in warns:
            cats.setdefault(i.category, []).append(i)
        for cat, items in cats.items():
            lines.append(f"**{cat}** ({len(items)}件)")
            for i in items[:4]:
                loc = f" `{i.file}:{i.line}`" if i.file else ""
                lines.append(f"  - {i.message}{loc}")
        lines.append("")

    # 情報
    infos = [i for i in report.issues if i.severity == "info"]
    if infos:
        lines.append("### 🟢 情報（余裕があれば）")
        cats: dict[str, list] = {}
        for i in infos:
            cats.setdefault(i.category, []).append(i)
        for cat, items in cats.items():
            lines.append(f"**{cat}** ({len(items)}件)")
            for i in items[:3]:
                lines.append(f"  - {i.message}")
        lines.append("")

    if not report.issues:
        lines.append("### 🏆 問題なし！プロジェクトは健全です。")

    return "\n".join(lines)


# ============================================================
# 健康診断自動ループ（修正 → 再診断 → 収束するまで繰り返す）
# ============================================================

def run_health_loop(
    project_path: str,
    max_rounds: int = 3,
    auto_fix_fn=None,   # autonomous_dev を渡す
    anchor: str = "",
) -> list:
    """
    健康診断 → 自動修正 → 再診断 を最大 max_rounds 回繰り返す。
    重大問題がなくなるか max_rounds に達したら停止。

    auto_fix_fn: callable(goal, anchor, save_path) → str
                 app.py の autonomous_dev を渡す

    戻り値: [{"round": int, "score": int, "grade": str, "issues": int, "report": str}]
    """
    history = []

    for round_n in range(1, max_rounds + 1):
        report = run_health_check(project_path)
        crits  = [i for i in report.issues if i.severity == "critical"]
        warns  = [i for i in report.issues if i.severity == "warning"]

        history.append({
            "round":  round_n,
            "score":  report.score,
            "grade":  report.grade,
            "critical": len(crits),
            "warnings": len(warns),
            "report": format_report(report),
        })

        if not crits:
            break  # 重大問題なし → 収束

        if auto_fix_fn is None:
            break  # 修正関数がなければ診断のみで終了

        # 重大問題を自動修正
        issues_str = "\n".join(
            f"- {i.message} ({i.file}:{i.line}) → {i.suggestion}"
            for i in crits[:5]
        )
        try:
            auto_fix_fn(
                goal=f"【健康診断 Round{round_n}】以下の重大問題を修正:\n{issues_str}",
                anchor=anchor,
                save_path=project_path,
            )
        except Exception as e:
            history[-1]["fix_error"] = str(e)
            break

    return history


def format_health_loop_report(history: list) -> str:
    """ループ診断の履歴をMarkdownで出力"""
    if not history:
        return "診断履歴がありません"

    lines = [
        "## 🔄 健康診断自動ループ結果",
        "",
        "| Round | スコア | グレード | 重大問題 | 警告 |",
        "|---|---|---|---|---|",
    ]
    for h in history:
        lines.append(
            f"| {h['round']} | {h['score']} | {h['grade']} "
            f"| {h['critical']} | {h['warnings']} |"
        )

    lines.append("")
    first = history[0]
    last  = history[-1]
    delta = last["score"] - first["score"]
    sign  = "+" if delta >= 0 else ""
    lines.append(f"**改善幅: {sign}{delta}点** ({first['score']} → {last['score']})")

    if last["critical"] == 0:
        lines.append("\n✅ 重大問題は全て解消されました")
    else:
        lines.append(f"\n⚠️ {last['critical']}件の重大問題が残っています")

    return "\n".join(lines)
