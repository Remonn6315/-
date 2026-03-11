"""
Blackwell Dev-OS — build_pipeline.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ビルド・タイムマシン・BGMパイプライン

【機能】
  ① Godot自動ビルド（CLIで.exe/.web/.app生成）
  ② タイムマシン（Gitタグで面白かったバージョンに戻る）
  ③ 素材マップ図（networkxで依存関係を可視化）
  ④ BGM最適化提案（BPMからゲームテンポを自動調整）

【app.py から呼ばれる関数】
  build_godot(project_path, target, godot_exe) → dict
  create_snapshot(tag, message, project_path)  → str
  list_snapshots(project_path) → list[dict]
  restore_snapshot(tag, project_path) → bool
  generate_asset_map_svg(manifest, save_path) → str
  suggest_bgm_tempo(manifest, genre) → dict
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import subprocess
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

# ============================================================
# ① Godot 自動ビルド
# ============================================================

GODOT_EXPORT_PRESETS = {
    "windows": "Windows Desktop",
    "web":     "Web",
    "linux":   "Linux/X11",
    "mac":     "macOS",
    "android": "Android",
}

def find_godot_exe() -> Optional[str]:
    """Godot実行ファイルを自動検索"""
    candidates = [
        r"C:\Program Files\Godot\Godot_v4.exe",
        r"C:\Program Files\Godot Engine\Godot_v4.exe",
        r"C:\Users\%USERNAME%\Downloads\Godot.exe",
        "/usr/bin/godot4",
        "/usr/local/bin/godot4",
        "/Applications/Godot.app/Contents/MacOS/Godot",
        "godot4", "godot", "Godot",
    ]
    for c in candidates:
        expanded = os.path.expandvars(c)
        if os.path.exists(expanded):
            return expanded
        # PATH上にあるか
        try:
            result = subprocess.run(
                [c, "--version"], capture_output=True, timeout=3
            )
            if result.returncode == 0:
                return c
        except Exception:
            pass
    return None


def build_godot(
    project_path: str,
    target: str = "windows",
    output_name: str = "game",
    godot_exe: Optional[str] = None,
) -> dict:
    """
    Godot CLIでビルドを実行。
    `godot --headless --export-release "Windows Desktop" game.exe`
    """
    exe = godot_exe or find_godot_exe()
    if not exe:
        return {
            "success": False,
            "error": (
                "Godotの実行ファイルが見つかりません。\n"
                "Godot 4をインストールして PATH に追加するか、\n"
                "サイドバーでGodotのパスを指定してください。"
            ),
            "output": ""
        }

    preset = GODOT_EXPORT_PRESETS.get(target.lower(), "Windows Desktop")
    ext    = {"windows": ".exe", "web": ".html", "linux": "", "mac": ".app"}.get(target, ".exe")
    out_dir = os.path.join(project_path, "export", target)
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"{output_name}{ext}")

    cmd = [exe, "--headless", "--export-release", preset, out_file, "--path", project_path]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=project_path
        )
        success = result.returncode == 0 and os.path.exists(out_file)
        return {
            "success":    success,
            "output_file": out_file if success else "",
            "stdout":     result.stdout[-1000:],
            "stderr":     result.stderr[-500:],
            "error":      "" if success else result.stderr[-300:],
            "target":     target,
            "preset":     preset,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "ビルドタイムアウト（120秒）", "output": ""}
    except Exception as e:
        return {"success": False, "error": str(e), "output": ""}


def check_export_presets(project_path: str) -> bool:
    """export_presets.cfg が存在するか確認（ない場合はビルド不可）"""
    return os.path.exists(os.path.join(project_path, "export_presets.cfg"))


def generate_export_presets(project_path: str, project_name: str = "MyGame") -> str:
    """Godot用 export_presets.cfg を自動生成"""
    content = f"""[preset.0]

name="Windows Desktop"
platform="Windows Desktop"
runnable=true
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter=""
export_path="export/windows/{project_name}.exe"
encryption_include_filters=""
encryption_exclude_filters=""
encrypt_pck=false
encrypt_directory=false

[preset.0.options]

custom_template/debug=""
custom_template/release=""

[preset.1]

name="Web"
platform="Web"
runnable=true
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter=""
export_path="export/web/index.html"
"""
    cfg_path = os.path.join(project_path, "export_presets.cfg")
    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(content)
        return cfg_path
    except Exception as e:
        return f"ERROR: {e}"


# ============================================================
# ② タイムマシン（Gitスナップショット）
# ============================================================

def create_snapshot(
    tag: str,
    message: str,
    project_path: str,
    auto_tag: bool = True,
) -> dict:
    """
    現在の状態をGitタグでスナップショット保存。
    「この面白かったバージョン」ボタンで呼ばれる。
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_tag  = re.sub(r"[^\w\-]", "_", tag)[:30]
    full_tag  = f"blackwell_{safe_tag}_{timestamp}"

    results = {}
    try:
        # ステージング
        r1 = subprocess.run(
            ["git", "add", "-A"], cwd=project_path,
            capture_output=True, text=True
        )
        results["add"] = r1.returncode == 0

        # コミット
        r2 = subprocess.run(
            ["git", "commit", "-m", f"[Blackwell Snapshot] {message}"],
            cwd=project_path, capture_output=True, text=True
        )
        results["commit"] = r2.returncode == 0

        # タグ
        r3 = subprocess.run(
            ["git", "tag", "-a", full_tag, "-m", message],
            cwd=project_path, capture_output=True, text=True
        )
        results["tag"] = r3.returncode == 0
        results["tag_name"] = full_tag
        results["success"] = results["commit"] or results["tag"]
        results["message"] = f"スナップショット「{safe_tag}」を保存しました\nタグ: {full_tag}"

    except Exception as e:
        results["success"] = False
        results["error"] = str(e)

    return results


def list_snapshots(project_path: str) -> list:
    """保存済みスナップショット一覧を取得"""
    try:
        r = subprocess.run(
            ["git", "tag", "-l", "blackwell_*", "--sort=-creatordate",
             "--format=%(refname:short)|%(subject)|%(creatordate:short)"],
            cwd=project_path, capture_output=True, text=True
        )
        if r.returncode != 0:
            return []
        snapshots = []
        for line in r.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("|")
            snapshots.append({
                "tag":     parts[0] if len(parts) > 0 else "",
                "message": parts[1] if len(parts) > 1 else "",
                "date":    parts[2] if len(parts) > 2 else "",
                "display": parts[0].replace("blackwell_", "").rsplit("_", 2)[0],
            })
        return snapshots[:20]  # 最新20件
    except Exception:
        return []


def restore_snapshot(tag: str, project_path: str) -> dict:
    """指定タグの状態に戻す"""
    try:
        # 現在の状態を自動バックアップ
        create_snapshot("auto_backup_before_restore", "復元前の自動バックアップ", project_path)

        r = subprocess.run(
            ["git", "checkout", tag, "--", "."],
            cwd=project_path, capture_output=True, text=True
        )
        return {
            "success": r.returncode == 0,
            "message": f"✅ 「{tag}」に戻しました" if r.returncode == 0 else r.stderr,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


def diff_from_snapshot(tag: str, project_path: str) -> str:
    """スナップショットからの変更差分を取得"""
    try:
        r = subprocess.run(
            ["git", "diff", tag, "--stat"],
            cwd=project_path, capture_output=True, text=True
        )
        return r.stdout[:2000] if r.returncode == 0 else "差分取得失敗"
    except Exception:
        return "Gitが使用できません"


# ============================================================
# ③ 素材マップ図（networkx SVG出力）
# ============================================================

def generate_asset_map_svg(manifest, output_path: str = "./asset_map.svg") -> str:
    """
    プロジェクトの素材依存関係をSVGで出力。
    「何がどこで使われているか」を視覚化。
    """
    try:
        import networkx as nx

        G = nx.DiGraph()

        # スプライト→役割ノード
        roles_seen = set()
        for sprite in manifest.sprites[:20]:  # 最大20件
            role_node = f"[{sprite.role}]"
            G.add_node(role_node, type="role")
            G.add_node(sprite.name, type="sprite")
            G.add_edge(role_node, sprite.name)
            roles_seen.add(role_node)

        # BGM・SE
        for audio in manifest.audio_bgm[:5]:
            G.add_node(audio.name, type="bgm")
            G.add_edge("[BGM]", audio.name)
        for audio in manifest.audio_se[:8]:
            G.add_node(audio.name, type="se")
            G.add_edge("[SE]", audio.name)

        # タイルセット
        for ts in manifest.tilesets[:3]:
            G.add_node(ts.name, type="tileset")
            G.add_edge("[Tileset]", ts.name)

        # アニメーショングループ
        for group, frames in list(manifest.anim_groups.items())[:6]:
            G.add_node(f"🎬{group}", type="anim")
            for frame in frames[:3]:
                G.add_edge(f"🎬{group}", frame.name)

        # SVG生成（graphvizがあれば使う、なければシンプルSVG）
        try:
            from networkx.drawing.nx_agraph import to_agraph
            A = to_agraph(G)
            A.layout("dot")
            A.draw(output_path, format="svg")
            return output_path
        except Exception:
            # fallbackでシンプルなSVGを手書き
            return _simple_svg(G, output_path, manifest)

    except ImportError:
        return _text_asset_map(manifest)
    except Exception as e:
        return f"ERROR: {e}"


def _simple_svg(G, output_path: str, manifest) -> str:
    """graphvizなしでシンプルなSVGを生成"""
    import math

    nodes = list(G.nodes(data=True))
    edges = list(G.edges())
    n = len(nodes)
    if n == 0:
        return ""

    W, H = 900, 600
    # 円形配置
    positions = {}
    for i, (node, data) in enumerate(nodes):
        angle = 2 * math.pi * i / n
        r = 220 if data.get("type") in {"role","bgm","se","tileset"} else 380
        x = W // 2 + int(r * math.cos(angle))
        y = H // 2 + int(r * math.sin(angle))
        positions[node] = (x, y)

    color_map = {
        "role":    "#4a90e2", "sprite": "#7ed321",
        "bgm":     "#f5a623", "se":     "#f8e71c",
        "tileset": "#9b59b6", "anim":   "#e74c3c",
    }

    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'style="background:#1a1a2e;font-family:sans-serif">',
        f'<text x="10" y="20" fill="#aaa" font-size="12">Blackwell 素材マップ — '
        f'{manifest.summary.get("total_sprites",0)}スプライト / '
        f'{manifest.summary.get("total_bgm",0)}BGM / '
        f'{manifest.summary.get("total_se",0)}SE</text>',
    ]

    # エッジ
    for src, dst in edges:
        if src in positions and dst in positions:
            x1,y1 = positions[src]; x2,y2 = positions[dst]
            svg_lines.append(
                f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                f'stroke="#444" stroke-width="1" stroke-dasharray="4,2"/>'
            )

    # ノード
    for node, data in nodes:
        if node not in positions: continue
        x, y = positions[node]
        color = color_map.get(data.get("type", ""), "#888")
        r = 30 if data.get("type") in {"role","bgm","se","tileset","anim"} else 22
        label = node[:12] + ("…" if len(node) > 12 else "")
        svg_lines.append(
            f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}" opacity="0.85"/>'
        )
        svg_lines.append(
            f'<text x="{x}" y="{y+4}" text-anchor="middle" '
            f'fill="white" font-size="9">{label}</text>'
        )

    svg_lines.append("</svg>")
    svg_str = "\n".join(svg_lines)

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(svg_str)
        return output_path
    except Exception:
        return svg_str  # パスに書けない場合はSVG文字列を返す


def _text_asset_map(manifest) -> str:
    """networkxもない場合のテキスト版マップ"""
    lines = ["【🗺️ 素材マップ（テキスト版）】"]
    if manifest.sprites:
        lines.append(f"\n🧍 スプライト ({len(manifest.sprites)}件):")
        for s in manifest.sprites[:8]:
            lines.append(f"  [{s.role}] {s.name}" + (f" → {s.total_frames}フレームシート" if s.is_sheet else ""))
    if manifest.audio_bgm:
        lines.append(f"\n🎵 BGM: " + ", ".join(a.name for a in manifest.audio_bgm[:5]))
    if manifest.audio_se:
        lines.append(f"🔊 SE ({len(manifest.audio_se)}件): " + ", ".join(a.name for a in manifest.audio_se[:6]))
    if manifest.tilesets:
        lines.append(f"\n🧱 タイルセット: " + ", ".join(t.name for t in manifest.tilesets))
    if manifest.anim_groups:
        lines.append(f"\n🎬 アニメーション: " + ", ".join(f"{k}({len(v)}f)" for k,v in list(manifest.anim_groups.items())[:5]))
    return "\n".join(lines)


# ============================================================
# ④ BGM最適化提案
# ============================================================

def suggest_bgm_tempo(manifest, genre: str = "2daction") -> dict:
    """
    既存のBGM素材のBPMを分析して最適なゲームテンポを提案。
    asset_pipeline.py で測定したBPM推定値を活用。
    """
    genre_bpm = {
        "2daction":   {"ideal": 130, "range": (110, 160), "feel": "疾走感・爽快感"},
        "roguelike":  {"ideal": 90,  "range": (70, 110),  "feel": "緊張感・探索感"},
        "simulation": {"ideal": 80,  "range": (60, 100),  "feel": "落ち着き・集中感"},
        "towerdefense":{"ideal": 110,"range": (90, 135),  "feel": "戦略的緊張感"},
        "3daction":   {"ideal": 140, "range": (120, 170), "feel": "迫力・没入感"},
    }
    target = genre_bpm.get(genre, genre_bpm["2daction"])

    result = {
        "genre":      genre,
        "ideal_bpm":  target["ideal"],
        "feel":       target["feel"],
        "bgm_analysis": [],
        "suggestions": [],
    }

    # 既存BGM分析
    for audio in manifest.audio_bgm:
        bpm = audio.bpm_estimate
        analysis = {
            "name":     audio.name,
            "bpm":      bpm,
            "duration": audio.duration_s,
            "match":    "✅ 最適" if bpm and target["range"][0] <= bpm <= target["range"][1]
                        else ("⚠️ やや速い" if bpm and bpm > target["range"][1]
                              else ("⚠️ やや遅い" if bpm and bpm < target["range"][0]
                                    else "❓ BPM不明")),
        }
        result["bgm_analysis"].append(analysis)

    # 提案生成
    matched = [a for a in result["bgm_analysis"] if "✅" in a["match"]]
    too_fast = [a for a in result["bgm_analysis"] if "速い" in a["match"]]
    too_slow = [a for a in result["bgm_analysis"] if "遅い" in a["match"]]

    if not manifest.audio_bgm:
        result["suggestions"].append(
            f"BGM素材が見つかりません。{genre}には{target['ideal']}BPM前後の楽曲が最適です（{target['feel']}）"
        )
    if too_fast:
        result["suggestions"].append(
            f"「{'、'.join(a['name'] for a in too_fast[:3])}」は速すぎます。"
            f"Pygameなら `pygame.mixer.music.set_pos()` で再生速度を調整、"
            f"Godotなら `$AudioStreamPlayer.pitch_scale = {target['ideal']/too_fast[0]['bpm']:.2f}` で調整できます"
        )
    if too_slow:
        result["suggestions"].append(
            f"「{'、'.join(a['name'] for a in too_slow[:3])}」は遅めです。"
            f"探索シーンや拠点シーンに適しています"
        )
    if matched:
        result["suggestions"].append(
            f"「{'、'.join(a['name'] for a in matched[:3])}」はこのジャンルに最適なBPMです！"
        )

    return result
