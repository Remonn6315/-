"""
Blackwell Dev-OS — gameplay_analyzer.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ゲームプレイ動画/スクショ解析AI

スクリーンショット or 動画フレーム列を受け取り:
  - はまっている箇所の検出
  - いい動きの評価
  - 動きの悪いところの指摘
  - キャラ・アイテム・シナリオ・舞台の総合評価
  - 改善提案（コード修正案つき）

Ollamaのビジョンモデル（llava / llava-llama3 等）を使用。

【公開API】
  analyze_screenshot(image_path, context)       → AnalysisResult
  analyze_video_frames(video_path, context)     → AnalysisResult
  analyze_from_bytes(image_bytes, context)      → AnalysisResult
  format_analysis(result)                       → str (Markdown)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import re
import base64
import json
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


# ビジョンモデルの優先順位（インストールされていれば使う）
VISION_MODELS = [
    "llava-llama3:latest",
    "llava:latest",
    "llava:13b",
    "moondream:latest",
    "bakllava:latest",
]


@dataclass
class GameplayIssue:
    category:   str    # stuck / visual_bug / ux_problem / balance / scenario / etc
    severity:   str    # critical / warning / info
    description:str
    timestamp:  str = ""   # 動画の場合: フレーム番号 or 時刻
    suggestion: str = ""
    code_fix:   str = ""   # 具体的なコード修正案


@dataclass
class AnalysisResult:
    success:       bool
    error:         str = ""
    # 評価スコア（0-10）
    score_fun:     float = 0.0   # 面白さ
    score_feel:    float = 0.0   # 操作感
    score_visual:  float = 0.0   # ビジュアル
    score_balance: float = 0.0   # バランス
    # 詳細評価
    good_points:   list  = field(default_factory=list)
    bad_points:    list  = field(default_factory=list)
    issues:        list  = field(default_factory=list)   # GameplayIssue list
    # 評価カテゴリ別コメント
    character_eval:  str = ""
    item_eval:       str = ""
    scenario_eval:   str = ""
    stage_eval:      str = ""
    overall_comment: str = ""
    # 改善提案
    improvements:    list = field(default_factory=list)
    # 生データ
    raw_response:    str = ""


def _find_vision_model() -> Optional[str]:
    """利用可能なビジョンモデルを探す"""
    try:
        import ollama
        models = ollama.list()
        available = [m["name"] for m in models.get("models", [])]
        for vm in VISION_MODELS:
            for a in available:
                if vm.split(":")[0] in a.lower():
                    return a
    except Exception:
        pass
    return None


def _encode_image(image_path: str) -> tuple[str, str]:
    """画像をbase64エンコードして (base64_str, media_type) を返す"""
    ext = os.path.splitext(image_path)[1].lower()
    media_type_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
        ".gif": "image/gif",
    }
    media_type = media_type_map.get(ext, "image/png")
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return b64, media_type


def _build_analysis_prompt(context: dict) -> str:
    """ゲームプレイ解析用プロンプトを組み立てる"""
    game_type   = context.get("game_type", "ゲーム")
    game_anchor = context.get("game_anchor", "")
    engine      = context.get("engine", "Godot4")

    anchor_line = f"\n【ゲームの主軸】\n{game_anchor}\n" if game_anchor else ""

    return f"""あなたはゲームデザイナーとプレイヤー体験の専門家AIです。
このゲームプレイのスクリーンショットを見て、以下の全項目を詳細に日本語で評価してください。
{anchor_line}
【ゲーム情報】
- ゲームタイプ: {game_type}
- エンジン: {engine}

【評価してほしい項目】

## 1. 総合スコア（各0〜10点）
- 面白さ: X/10
- 操作感: X/10
- ビジュアル: X/10
- バランス: X/10

## 2. 良いところ（具体的に3点）
- ...

## 3. 悪いところ・問題点（具体的に）
- ...

## 4. はまっていそうな箇所
（プレイヤーが詰まりそうな場所・理由を画面から読み取る）

## 5. カテゴリ別評価
### キャラクター
（動き・表情・わかりやすさ）

### アイテム
（視認性・効果の明確さ・バランス）

### シナリオ・UI
（情報の伝わり方・誘導・テキスト）

### 舞台・ステージ
（レイアウト・敵配置・難易度曲線）

## 6. 具体的な改善提案（優先度順に3〜5点）
1. [優先度:高] ...
2. [優先度:中] ...
3. [優先度:低] ...

## 7. コード修正案（該当する場合）
```gdscript
# または python
# 改善すべき具体的なコード例
```

できるだけ具体的に、開発者が即座に行動できる提案をしてください。"""


def _parse_analysis_response(raw: str) -> dict:
    """AIの応答をパースして構造化データにする"""
    result = {
        "score_fun":      0.0, "score_feel":    0.0,
        "score_visual":   0.0, "score_balance": 0.0,
        "good_points": [], "bad_points": [],
        "character_eval": "", "item_eval": "",
        "scenario_eval":  "", "stage_eval": "",
        "improvements":   [], "code_fix": "",
        "stuck_areas":    "",
        "overall_comment": "",
    }

    # スコア抽出
    score_patterns = {
        "score_fun":     r"面白さ[:\s]+(\d+(?:\.\d+)?)/10",
        "score_feel":    r"操作感[:\s]+(\d+(?:\.\d+)?)/10",
        "score_visual":  r"ビジュアル[:\s]+(\d+(?:\.\d+)?)/10",
        "score_balance": r"バランス[:\s]+(\d+(?:\.\d+)?)/10",
    }
    for key, pat in score_patterns.items():
        m = re.search(pat, raw)
        if m:
            result[key] = float(m.group(1))

    # セクション抽出ヘルパー
    def extract_section(header_pattern: str, next_header: str = "##") -> str:
        m = re.search(header_pattern + r"(.*?)(?=" + next_header + r"|\Z)", raw, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else ""

    # 良いところ
    good_sec = extract_section(r"##\s*2\..*良いところ")
    result["good_points"] = [
        l.lstrip("-・ ").strip() for l in good_sec.splitlines()
        if l.strip() and l.strip() not in ("", "...")
    ][:5]

    # 悪いところ
    bad_sec = extract_section(r"##\s*3\..*悪いところ")
    result["bad_points"] = [
        l.lstrip("-・ ").strip() for l in bad_sec.splitlines()
        if l.strip() and l.strip() not in ("", "...")
    ][:5]

    # はまり箇所
    result["stuck_areas"] = extract_section(r"##\s*4\..*はまっ")

    # カテゴリ別
    result["character_eval"] = extract_section(r"###\s*キャラクター")
    result["item_eval"]       = extract_section(r"###\s*アイテム")
    result["scenario_eval"]   = extract_section(r"###\s*シナリオ")
    result["stage_eval"]      = extract_section(r"###\s*舞台")

    # 改善提案
    imp_sec = extract_section(r"##\s*6\..*改善提案")
    result["improvements"] = [
        l.lstrip("0123456789. ").strip() for l in imp_sec.splitlines()
        if l.strip() and re.match(r"^\d+\.", l.strip())
    ][:5]

    # コード修正案
    code_m = re.search(r"```(?:gdscript|python|gd)?\n(.*?)```", raw, re.DOTALL)
    result["code_fix"] = code_m.group(1).strip() if code_m else ""

    # 総合コメント（最初の段落）
    first_para = raw.strip().split("\n\n")[0]
    result["overall_comment"] = first_para[:200] if first_para else ""

    return result


def analyze_screenshot(
    image_path: str,
    context: Optional[dict] = None,
) -> AnalysisResult:
    """
    スクリーンショットを解析してゲームプレイ評価を返す。

    context: {
      "game_type": "2Dアクション",
      "game_anchor": "ローグライクRPG...",
      "engine": "Godot4",
    }
    """
    context = context or {}

    if not os.path.exists(image_path):
        return AnalysisResult(success=False, error=f"画像が見つかりません: {image_path}")

    model = _find_vision_model()
    if not model:
        return AnalysisResult(
            success=False,
            error=(
                "ビジョンモデルが見つかりません。\n"
                "以下のコマンドでインストールしてください:\n"
                "  ollama pull llava-llama3\n"
                "または: ollama pull llava"
            )
        )

    try:
        import ollama as _ollama
        b64, media_type = _encode_image(image_path)
        prompt = _build_analysis_prompt(context)

        res = _ollama.chat(
            model=model,
            messages=[{
                "role": "user",
                "content": prompt,
                "images": [b64],
            }]
        )
        raw = res["message"]["content"]
        parsed = _parse_analysis_response(raw)

        return AnalysisResult(
            success=True,
            raw_response=raw,
            score_fun=parsed["score_fun"],
            score_feel=parsed["score_feel"],
            score_visual=parsed["score_visual"],
            score_balance=parsed["score_balance"],
            good_points=parsed["good_points"],
            bad_points=parsed["bad_points"],
            character_eval=parsed["character_eval"],
            item_eval=parsed["item_eval"],
            scenario_eval=parsed["scenario_eval"],
            stage_eval=parsed["stage_eval"],
            improvements=parsed["improvements"],
            overall_comment=parsed["overall_comment"] or raw[:200],
        )

    except Exception as e:
        return AnalysisResult(success=False, error=str(e))


def analyze_from_bytes(
    image_bytes: bytes,
    context: Optional[dict] = None,
    filename: str = "screenshot.png",
) -> AnalysisResult:
    """
    バイト列から直接解析（Streamlitのfile_uploaderと組み合わせる）。
    """
    import tempfile
    context = context or {}
    with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1],
                                     delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name
    try:
        return analyze_screenshot(tmp_path, context)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def analyze_video_frames(
    video_path: str,
    context: Optional[dict] = None,
    max_frames: int = 8,
) -> AnalysisResult:
    """
    動画ファイルからフレームを抽出して複数枚解析する。
    ffmpegが必要。
    """
    context = context or {}

    if not os.path.exists(video_path):
        return AnalysisResult(success=False, error=f"動画が見つかりません: {video_path}")

    # ffmpegでフレーム抽出
    import tempfile, subprocess
    frame_dir = tempfile.mkdtemp()
    try:
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vf", f"fps=1/3",  # 3秒に1フレーム
            "-frames:v", str(max_frames),
            os.path.join(frame_dir, "frame_%03d.png"),
            "-y", "-loglevel", "quiet"
        ]
        subprocess.run(cmd, timeout=60, check=True)
        frames = sorted([
            os.path.join(frame_dir, f)
            for f in os.listdir(frame_dir)
            if f.endswith(".png")
        ])
    except FileNotFoundError:
        return AnalysisResult(
            success=False,
            error="ffmpegが見つかりません。インストールしてください: https://ffmpeg.org/"
        )
    except Exception as e:
        return AnalysisResult(success=False, error=f"フレーム抽出失敗: {e}")

    if not frames:
        return AnalysisResult(success=False, error="フレームの抽出に失敗しました")

    # 各フレームを解析して集約
    all_results = []
    for fp in frames[:max_frames]:
        r = analyze_screenshot(fp, context)
        if r.success:
            all_results.append(r)

    if not all_results:
        return AnalysisResult(success=False, error="どのフレームも解析できませんでした")

    # 平均スコア・コメント集約
    avg = lambda key: sum(getattr(r, key) for r in all_results) / len(all_results)
    good = []
    bad  = []
    imps = []
    for r in all_results:
        good.extend(r.good_points)
        bad.extend(r.bad_points)
        imps.extend(r.improvements)

    # 重複排除
    def dedup(lst):
        seen = set()
        out  = []
        for item in lst:
            if item and item not in seen:
                seen.add(item)
                out.append(item)
        return out[:5]

    return AnalysisResult(
        success=True,
        score_fun=avg("score_fun"),
        score_feel=avg("score_feel"),
        score_visual=avg("score_visual"),
        score_balance=avg("score_balance"),
        good_points=dedup(good),
        bad_points=dedup(bad),
        character_eval=all_results[0].character_eval,
        item_eval=all_results[0].item_eval,
        scenario_eval=all_results[0].scenario_eval,
        stage_eval=all_results[0].stage_eval,
        improvements=dedup(imps),
        overall_comment=f"{len(all_results)}フレームを解析しました。\n" + all_results[0].overall_comment,
    )


def format_analysis(result: AnalysisResult) -> str:
    """解析結果をMarkdownで出力"""
    if not result.success:
        return f"### ❌ 解析失敗\n{result.error}"

    def stars(score: float) -> str:
        filled = round(score / 2)
        return "★" * filled + "☆" * (5 - filled) + f" ({score:.1f}/10)"

    lines = [
        "## 🎮 ゲームプレイ解析レポート",
        "",
        "### 📊 総合スコア",
        f"| 面白さ | 操作感 | ビジュアル | バランス |",
        f"|---|---|---|---|",
        f"| {stars(result.score_fun)} | {stars(result.score_feel)} | {stars(result.score_visual)} | {stars(result.score_balance)} |",
        "",
    ]

    if result.overall_comment:
        lines += ["### 💬 総評", result.overall_comment, ""]

    if result.good_points:
        lines += ["### ✅ 良いところ"]
        lines += [f"- {p}" for p in result.good_points]
        lines.append("")

    if result.bad_points:
        lines += ["### ⚠️ 問題点"]
        lines += [f"- {p}" for p in result.bad_points]
        lines.append("")

    categories = [
        ("👤 キャラクター", result.character_eval),
        ("🎁 アイテム",     result.item_eval),
        ("📖 シナリオ・UI", result.scenario_eval),
        ("🗺️ 舞台・ステージ", result.stage_eval),
    ]
    has_cats = any(v for _, v in categories)
    if has_cats:
        lines.append("### 🔍 カテゴリ別評価")
        for label, text in categories:
            if text:
                lines += [f"**{label}**", text[:300], ""]

    if result.improvements:
        lines += ["### 🔧 改善提案（優先度順）"]
        for i, imp in enumerate(result.improvements, 1):
            lines.append(f"{i}. {imp}")
        lines.append("")

    return "\n".join(lines)
