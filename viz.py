"""
Blackwell Dev-OS — viz.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
依存グラフ視覚化 & コード進化タイムライン

【公開API】
  build_dep_graph_svg(project_path) → str (SVG)
  build_evolution_data(project_path) → dict
  get_git_timeline(project_path, n)  → list
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os, re, ast, json, subprocess
from pathlib import Path
from datetime import datetime


# ============================================================
# 依存グラフ SVG 生成
# ============================================================

def _get_py_imports(filepath: str) -> list[str]:
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            src = f.read()
        tree = ast.parse(src)
        deps = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    deps.append(n.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                deps.append(node.module.split(".")[0])
        return list(set(deps))
    except Exception:
        return []


def _get_gd_imports(filepath: str) -> list[str]:
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            src = f.read()
        deps = re.findall(r'(?:preload|load)\s*\(\s*"([^"]+)"', src)
        # res://path/to/file.gd → ファイル名だけ取る
        return [os.path.splitext(os.path.basename(d))[0] for d in deps]
    except Exception:
        return []


def build_dep_graph_svg(project_path: str, max_nodes: int = 30) -> str:
    """
    プロジェクトの依存グラフをSVGで返す。
    ノード: ファイル
    エッジ: import/preload の依存関係
    色分け: py=青 / gd=緑 / cs=紫 / 外部=グレー
    """
    files = []
    for root, dirs, fnames in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in {".git",".godot","__pycache__","node_modules"}]
        for fn in fnames:
            if fn.endswith((".py",".gd",".cs")):
                files.append(os.path.join(root, fn))

    files = files[:max_nodes]
    if not files:
        return _svg_message("プロジェクトにコードファイルがありません")

    # ノード情報
    nodes = {}
    for fp in files:
        name = os.path.relpath(fp, project_path)
        ext  = os.path.splitext(fp)[1]
        if ext == ".py":
            deps = _get_py_imports(fp)
            color = "#4A90D9"
        elif ext == ".gd":
            deps = _get_gd_imports(fp)
            color = "#5CB85C"
        elif ext == ".cs":
            deps = []
            color = "#9B59B6"
        else:
            deps = []
            color = "#95A5A6"
        size = max(20, min(50, os.path.getsize(fp) // 200))
        nodes[name] = {"deps": deps, "color": color, "size": size,
                       "short": os.path.basename(fp)}

    # 簡易力学レイアウト（円配置）
    import math
    n = len(nodes)
    positions = {}
    W, H = 800, 600
    cx, cy = W//2, H//2
    r = min(cx, cy) - 80
    for i, name in enumerate(nodes):
        angle = 2 * math.pi * i / max(n, 1)
        positions[name] = (
            int(cx + r * math.cos(angle)),
            int(cy + r * math.sin(angle))
        )

    # SVG 生成
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'style="background:#1a1a2e;border-radius:8px">',
        '<defs><marker id="arr" markerWidth="6" markerHeight="6" refX="5" refY="3" '
        'orient="auto"><path d="M0,0 L6,3 L0,6 z" fill="#666"/></marker></defs>',
    ]

    # エッジ
    name_to_short = {n: d["short"] for n, d in nodes.items()}
    short_to_name = {v: k for k, v in name_to_short.items()}
    for name, info in nodes.items():
        x1, y1 = positions[name]
        for dep in info["deps"]:
            # 依存先を探す
            target = short_to_name.get(dep + ".py") or short_to_name.get(dep + ".gd") or \
                     short_to_name.get(dep)
            if target and target in positions:
                x2, y2 = positions[target]
                lines.append(
                    f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                    f'stroke="#555" stroke-width="1.5" '
                    f'marker-end="url(#arr)" opacity="0.7"/>'
                )

    # ノード
    for name, info in nodes.items():
        x, y = positions[name]
        r2 = info["size"]
        color = info["color"]
        short = info["short"]
        # 円
        lines.append(
            f'<circle cx="{x}" cy="{y}" r="{r2}" fill="{color}" '
            f'opacity="0.85" stroke="white" stroke-width="1.5">'
            f'<title>{name}</title></circle>'
        )
        # ラベル（短いファイル名）
        fs = max(8, min(11, 100 // max(len(short), 1)))
        lines.append(
            f'<text x="{x}" y="{y+r2+14}" text-anchor="middle" '
            f'fill="white" font-size="{fs}" font-family="monospace">{short[:20]}</text>'
        )

    # 凡例
    legend = [("Python", "#4A90D9", 20), ("GDScript", "#5CB85C", 80), ("C#", "#9B59B6", 140)]
    for lname, lcolor, lx in legend:
        lines.append(f'<circle cx="{lx+10}" cy="20" r="7" fill="{lcolor}"/>')
        lines.append(f'<text x="{lx+22}" y="24" fill="white" font-size="10">{lname}</text>')

    lines.append("</svg>")
    return "\n".join(lines)


def _svg_message(msg: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="100" '
            f'style="background:#1a1a2e">'
            f'<text x="200" y="55" text-anchor="middle" fill="#aaa" font-size="14">{msg}</text>'
            f'</svg>')


# ============================================================
# コード進化タイムライン（Git履歴）
# ============================================================

def get_git_timeline(project_path: str, n: int = 30) -> list:
    """
    Gitのコミット履歴を取得してタイムラインデータを返す。
    戻り値: [{"hash": str, "date": str, "msg": str, "files": int, "insertions": int, "deletions": int}]
    """
    timeline = []
    try:
        # コミット一覧
        log_result = subprocess.run(
            ["git", "log", f"-{n}", "--format=%H|||%ai|||%s"],
            capture_output=True, text=True, cwd=project_path, timeout=10
        )
        if log_result.returncode != 0:
            return []

        for line in log_result.stdout.strip().splitlines():
            parts = line.split("|||")
            if len(parts) < 3:
                continue
            commit_hash, date_str, msg = parts[0], parts[1], parts[2]

            # 変更統計
            stat_result = subprocess.run(
                ["git", "show", "--stat", "--format=", commit_hash],
                capture_output=True, text=True, cwd=project_path, timeout=5
            )
            insertions = deletions = files_changed = 0
            for sline in stat_result.stdout.splitlines():
                m = re.search(r"(\d+) file", sline)
                if m: files_changed = int(m.group(1))
                m = re.search(r"(\d+) insertion", sline)
                if m: insertions = int(m.group(1))
                m = re.search(r"(\d+) deletion", sline)
                if m: deletions = int(m.group(1))

            timeline.append({
                "hash":       commit_hash[:8],
                "date":       date_str[:10],
                "msg":        msg[:60],
                "files":      files_changed,
                "insertions": insertions,
                "deletions":  deletions,
                "net":        insertions - deletions,
            })

    except Exception as e:
        print(f"[viz] git timeline error: {e}")

    return timeline


def build_evolution_svg(timeline: list) -> str:
    """
    コード進化タイムラインをSVGバーチャートで返す。
    横軸: 時系列 / 縦軸: 追加行数（緑）削除行数（赤）
    """
    if not timeline:
        return _svg_message("Gitコミット履歴がありません")

    W, H   = 900, 300
    PAD    = 50
    chart_w = W - PAD * 2
    chart_h = H - PAD * 2
    n       = len(timeline)
    bar_w   = max(4, chart_w // max(n, 1) - 2)

    max_val = max((max(e["insertions"], e["deletions"]) for e in timeline), default=1)
    if max_val == 0:
        max_val = 1

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'style="background:#1a1a2e;border-radius:8px">',
        f'<text x="{W//2}" y="22" text-anchor="middle" fill="white" '
        f'font-size="14" font-family="sans-serif">コード進化タイムライン ({n}コミット)</text>',
        f'<line x1="{PAD}" y1="{H-PAD}" x2="{W-PAD}" y2="{H-PAD}" stroke="#444" stroke-width="1"/>',
    ]

    for i, entry in enumerate(reversed(timeline)):  # 古い順に表示
        x = PAD + i * (chart_w // max(n, 1))

        # 追加行（緑）
        ins_h = int(entry["insertions"] / max_val * chart_h * 0.85)
        if ins_h > 0:
            lines.append(
                f'<rect x="{x}" y="{H-PAD-ins_h}" width="{bar_w}" height="{ins_h}" '
                f'fill="#2ECC71" opacity="0.8">'
                f'<title>{entry["date"]}: +{entry["insertions"]} -{entry["deletions"]}\n{entry["msg"]}</title>'
                f'</rect>'
            )

        # 削除行（赤）
        del_h = int(entry["deletions"] / max_val * chart_h * 0.85)
        if del_h > 0:
            lines.append(
                f'<rect x="{x+bar_w//2}" y="{H-PAD-del_h}" width="{bar_w//2}" height="{del_h}" '
                f'fill="#E74C3C" opacity="0.6">'
                f'<title>削除: {entry["deletions"]}行</title>'
                f'</rect>'
            )

        # 日付ラベル（間引き表示）
        if i % max(1, n // 8) == 0:
            lines.append(
                f'<text x="{x}" y="{H-8}" fill="#888" font-size="9" '
                f'transform="rotate(-30,{x},{H-8})">{entry["date"]}</text>'
            )

    # 凡例
    lines += [
        '<rect x="20" y="40" width="12" height="12" fill="#2ECC71" opacity="0.8"/>',
        '<text x="36" y="51" fill="white" font-size="11">追加行</text>',
        '<rect x="90" y="40" width="12" height="12" fill="#E74C3C" opacity="0.6"/>',
        '<text x="106" y="51" fill="white" font-size="11">削除行</text>',
    ]
    lines.append("</svg>")
    return "\n".join(lines)
