"""
Blackwell Dev-OS — video_analyzer.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⑧ プレイ動画解析

【何をするか】
  プレイ動画（mp4/webm/gif）または連続スクショを解析して:
  1. 「このゲームのどこが面白いか」を学習
  2. 「このゲームの問題点」を時系列で検出
  3. 「自分のゲームに取り入れるべき点」を提案
  4. 重要シーンを自動抽出してBlackwellの記憶に追加

【2つのモード】
  自分のゲームの動画:
    → バグ・バランス問題を時系列で検出
    → 「〇〇秒で詰まっている」を発見
    → 修正タスクとしてバックログに自動追加

  参考にしたいゲームの動画:
    → 「なぜ面白いか」をMDA理論で分析
    → 自分のゲームに取り入れるべき要素を抽出
    → game_insightsに学習データとして保存

【技術】
  - ffmpegで動画からフレームを抽出（1秒ごと）
  - ビジョンAIで各フレームを解析
  - フレーム間の変化を検出して「重要シーン」を特定
  - 連続解析で時系列パターンを発見

【保存先】
  {project}/blackwell_brain/video_analyses.json

【公開API】
  analyze_video(video_path, mode, project_path, anchor) → VideoAnalysis
  analyze_frames(frame_list, mode, project_path, anchor) → VideoAnalysis
  get_video_history(project_path, n)                    → list
  get_video_insights(project_path)                      → dict
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import os
import base64
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


BRAIN_DIR      = "blackwell_brain"
ANALYSES_FILE  = "video_analyses.json"
MAX_ANALYSES   = 50
MAX_FRAMES     = 30   # 1動画から最大フレーム数（負荷軽減）
SAMPLE_FPS     = 0.5  # 2秒に1フレーム抽出


# ============================================================
# データ構造
# ============================================================

@dataclass
class FrameInsight:
    timestamp:  float   # 動画内の秒数
    description: str    # このフレームの状況
    issue:       str    # 検出された問題（なければ空）
    fun_moment:  str    # 面白い瞬間の説明（なければ空）
    importance:  int    # 重要度 1-5


@dataclass
class VideoAnalysis:
    video_name:    str
    mode:          str      # "own" or "reference"
    duration_sec:  float
    frames_analyzed: int
    frame_insights: list    # list[FrameInsight]
    summary:       str      # 全体サマリー
    issues:        list     # 問題点一覧（own モード）
    fun_elements:  list     # 面白い要素（reference モード）
    backlog_tasks: list     # バックログに追加したタスク
    timestamp:     str


# ============================================================
# ユーティリティ
# ============================================================

def _brain_dir(project_path: str) -> str:
    d = os.path.join(project_path, BRAIN_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _load(project_path: str, filename: str, default):
    path = os.path.join(_brain_dir(project_path), filename)
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(project_path: str, filename: str, data):
    path = os.path.join(_brain_dir(project_path), filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_vision_model() -> str:
    try:
        import ollama
        models = ollama.list()
        names  = [m["name"] for m in models.get("models", [])]
        for pref in ["llava-llama3:latest", "llava:latest", "moondream:latest"]:
            if pref in names:
                return pref
        for n in names:
            if any(k in n for k in ["llava", "vision", "moondream"]):
                return n
    except Exception:
        pass
    return "llava:latest"


def _has_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"],
                       capture_output=True, timeout=3)
        return True
    except Exception:
        return False


# ============================================================
# 動画からフレーム抽出
# ============================================================

def _extract_frames(video_path: str,
                    max_frames: int = MAX_FRAMES) -> list:
    """
    ffmpegで動画からフレームをbase64リストとして抽出する。
    ffmpegがない場合はgifをPillowで処理するフォールバック。
    返り値: [(timestamp_sec, base64_str), ...]
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"動画ファイルが見つかりません: {video_path}")

    ext = os.path.splitext(video_path)[1].lower()

    # GIF: Pillowで処理
    if ext == ".gif":
        return _extract_gif_frames(video_path, max_frames)

    # mp4/webm: ffmpegで処理
    if not _has_ffmpeg():
        return _extract_fallback(video_path)

    frames = []
    with tempfile.TemporaryDirectory() as tmpdir:
        out_pattern = os.path.join(tmpdir, "frame_%04d.jpg")
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vf", f"fps={SAMPLE_FPS}",
            "-vframes", str(max_frames),
            "-q:v", "5",
            out_pattern,
            "-y", "-loglevel", "quiet"
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=60, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[video_analyzer] ffmpeg失敗: {e}")
            return []

        frame_files = sorted([
            f for f in os.listdir(tmpdir) if f.endswith(".jpg")
        ])
        interval = 1.0 / SAMPLE_FPS
        for i, fname in enumerate(frame_files[:max_frames]):
            fpath = os.path.join(tmpdir, fname)
            with open(fpath, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            frames.append((i * interval, b64))

    return frames


def _extract_gif_frames(gif_path: str, max_frames: int) -> list:
    """GIFフレームをPillowで抽出"""
    try:
        from PIL import Image
        import io
        frames = []
        img    = Image.open(gif_path)
        step   = max(1, img.n_frames // max_frames)
        for i in range(0, img.n_frames, step):
            img.seek(i)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=70)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            frames.append((i * 0.1, b64))
            if len(frames) >= max_frames:
                break
        return frames
    except ImportError:
        print("[video_analyzer] Pillowがインストールされていません")
        return []
    except Exception as e:
        print(f"[video_analyzer] GIF解析失敗: {e}")
        return []


def _extract_fallback(video_path: str) -> list:
    """ffmpegなし・GIF以外のフォールバック: 先頭バイトをそのまま1フレームとして返す"""
    print("[video_analyzer] ffmpegなし → 先頭フレームのみ解析")
    with open(video_path, "rb") as f:
        data = f.read(500_000)  # 最大500KB
    b64 = base64.b64encode(data).decode("utf-8")
    return [(0.0, b64)]


# ============================================================
# メイン解析
# ============================================================

def analyze_video(video_path: str,
                  mode: str = "own",
                  project_path: str = "./",
                  anchor: str = "",
                  model: str = "") -> VideoAnalysis:
    """
    動画ファイルを解析する。

    mode="own"       : 自分のゲームのバグ・問題を検出
    mode="reference" : 参考ゲームの面白さを学習
    """
    model  = model or _get_vision_model()
    frames = _extract_frames(video_path)

    if not frames:
        raise ValueError("フレームを抽出できませんでした")

    video_name   = os.path.basename(video_path)
    duration_sec = frames[-1][0] if frames else 0

    return analyze_frames(
        frames, mode, project_path, anchor, model,
        video_name=video_name, duration_sec=duration_sec
    )


def analyze_frames(frames: list,
                   mode: str = "own",
                   project_path: str = "./",
                   anchor: str = "",
                   model: str = "",
                   video_name: str = "upload",
                   duration_sec: float = 0) -> VideoAnalysis:
    """
    フレームリスト [(timestamp, base64), ...] を解析する。
    app.pyのファイルアップローダーから直接呼ぶ場合はこちら。
    """
    model = model or _get_vision_model()
    print(f"[video_analyzer] 解析開始: {len(frames)}フレーム / モード={mode}")

    # ── フレームごとの解析 ────────────────────────────────
    frame_insights = []
    important_frames = _select_important_frames(frames)

    for ts, b64 in important_frames:
        insight = _analyze_frame(b64, ts, mode, anchor, model)
        frame_insights.append(insight)
        print(f"[video_analyzer]  {ts:.1f}秒: {insight.description[:40]}")

    # ── 全体サマリー ──────────────────────────────────────
    summary, issues, fun_elements = _generate_summary(
        frame_insights, mode, anchor, model)

    # ── バックログに問題を追加（own モードのみ）────────────
    backlog_tasks = []
    if mode == "own" and issues:
        backlog_tasks = _add_issues_to_backlog(
            issues, project_path, anchor)

    result = VideoAnalysis(
        video_name=video_name,
        mode=mode,
        duration_sec=duration_sec,
        frames_analyzed=len(frame_insights),
        frame_insights=frame_insights,
        summary=summary,
        issues=issues,
        fun_elements=fun_elements,
        backlog_tasks=backlog_tasks,
        timestamp=datetime.now().isoformat(),
    )

    # 保存
    _save_analysis(project_path, result)

    # referenceモードの学習内容をgame_insightsにも保存
    if mode == "reference" and fun_elements:
        _save_reference_insights(project_path, fun_elements, video_name)

    print(f"[video_analyzer] 完了: 問題{len(issues)}件 / "
          f"面白要素{len(fun_elements)}件")
    return result


def _select_important_frames(frames: list,
                              max_frames: int = 15) -> list:
    """
    全フレームから重要なフレームを選択する。
    均等サンプリング + 最初・最後は必ず含む。
    """
    if len(frames) <= max_frames:
        return frames

    step = len(frames) / max_frames
    selected = []
    for i in range(max_frames):
        idx = min(int(i * step), len(frames) - 1)
        selected.append(frames[idx])

    # 最初と最後を必ず含む
    if frames[0] not in selected:
        selected[0] = frames[0]
    if frames[-1] not in selected:
        selected[-1] = frames[-1]

    return selected


def _analyze_frame(b64: str, timestamp: float,
                   mode: str, anchor: str, model: str) -> FrameInsight:
    """1フレームをビジョンAIで解析"""
    try:
        import ollama

        if mode == "own":
            prompt = (
                f"ゲームのプレイ動画のフレーム（{timestamp:.1f}秒）です。\n"
                f"ゲーム概要: {anchor[:100]}\n\n"
                "JSONのみ出力（前置き不要）:\n"
                "{\n"
                '  "description": "画面の状況（1行）",\n'
                '  "issue": "問題点があれば（なければ空文字）",\n'
                '  "fun_moment": "",\n'
                '  "importance": 1から5の整数\n'
                "}"
            )
        else:
            prompt = (
                f"参考ゲームの動画フレーム（{timestamp:.1f}秒）です。\n\n"
                "JSONのみ出力（前置き不要）:\n"
                "{\n"
                '  "description": "画面の状況（1行）",\n'
                '  "issue": "",\n'
                '  "fun_moment": "面白い要素があれば（なければ空）",\n'
                '  "importance": 1から5の整数\n'
                "}"
            )

        res = ollama.chat(
            model=model,
            messages=[{
                "role": "user",
                "content": prompt,
                "images": [b64],
            }]
        )
        raw = res["message"]["content"]
        m   = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            d = json.loads(m.group(0))
            return FrameInsight(
                timestamp=timestamp,
                description=d.get("description", "")[:100],
                issue=d.get("issue", "")[:100],
                fun_moment=d.get("fun_moment", "")[:100],
                importance=min(5, max(1, int(d.get("importance", 3)))),
            )
    except Exception as e:
        print(f"[video_analyzer] フレーム解析失敗: {e}")

    return FrameInsight(
        timestamp=timestamp,
        description="解析失敗",
        issue="", fun_moment="", importance=1,
    )


def _generate_summary(frame_insights: list, mode: str,
                       anchor: str, model: str) -> tuple:
    """フレーム解析結果から全体サマリーと問題・面白要素を生成"""
    try:
        import ollama

        insights_text = "\n".join([
            f"[{fi.timestamp:.1f}秒] {fi.description}"
            + (f" ⚠️{fi.issue}" if fi.issue else "")
            + (f" 🎯{fi.fun_moment}" if fi.fun_moment else "")
            for fi in frame_insights
        ])

        if mode == "own":
            prompt = (
                f"ゲームプレイ動画の時系列解析結果です:\n{insights_text}\n\n"
                f"ゲーム概要: {anchor[:150]}\n\n"
                "JSONのみ出力:\n"
                "{\n"
                '  "summary": "全体的な評価（2〜3文）",\n'
                '  "issues": [\n'
                '    {"time": "〇〇秒", "problem": "問題の説明", "priority": "high/medium/low",\n'
                '     "fix_hint": "修正ヒント", "target_file": "推定ファイル名"}\n'
                "  ],\n"
                '  "fun_elements": []\n'
                "}"
            )
        else:
            prompt = (
                f"参考ゲームの時系列解析結果です:\n{insights_text}\n\n"
                "JSONのみ出力:\n"
                "{\n"
                '  "summary": "このゲームの面白さの本質（2〜3文）",\n'
                '  "issues": [],\n'
                '  "fun_elements": [\n'
                '    {"element": "面白い要素の名前", "description": "説明",\n'
                '     "how_to_apply": "自分のゲームへの応用方法"}\n'
                "  ]\n"
                "}"
            )

        res = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = res["message"]["content"]
        m   = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            d = json.loads(m.group(0))
            return (
                d.get("summary", ""),
                d.get("issues", []),
                d.get("fun_elements", []),
            )
    except Exception as e:
        print(f"[video_analyzer] サマリー生成失敗: {e}")

    return "解析完了", [], []


def _add_issues_to_backlog(issues: list,
                            project_path: str,
                            anchor: str) -> list:
    """検出した問題をバックログに自動追加"""
    added = []
    try:
        from autonomous_scheduler import add_task
        priority_map = {"high": 1, "medium": 2, "low": 3}

        for issue in issues[:5]:
            problem   = issue.get("problem", "")
            fix_hint  = issue.get("fix_hint", "")
            time_str  = issue.get("time", "")
            target    = issue.get("target_file", "")
            priority  = priority_map.get(issue.get("priority", "medium"), 2)

            if not problem:
                continue

            title = f"[動画{time_str}] {problem[:50]}"
            desc  = (
                f"プレイ動画で検出された問題:\n"
                f"問題: {problem}\n"
                f"修正ヒント: {fix_hint}\n"
                f"発生時刻: {time_str}"
            )
            tid = add_task(project_path, title, target or "fix.gd",
                           desc, priority)
            added.append({"task_id": tid, "title": title})

    except Exception as e:
        print(f"[video_analyzer] バックログ追加失敗: {e}")

    return added


def _save_reference_insights(project_path: str,
                               fun_elements: list,
                               video_name: str):
    """参考ゲームの学習内容をgame_insightsに追加"""
    try:
        insights = _load(project_path, "game_insights.json", {})
        refs = insights.get("reference_insights", [])
        for fe in fun_elements:
            refs.append({
                "source":       video_name,
                "element":      fe.get("element", ""),
                "description":  fe.get("description", ""),
                "how_to_apply": fe.get("how_to_apply", ""),
                "added_at":     datetime.now().isoformat()[:16],
            })
        insights["reference_insights"] = refs[-50:]
        _save(project_path, "game_insights.json", insights)
    except Exception as e:
        print(f"[video_analyzer] insights保存失敗: {e}")


def _save_analysis(project_path: str, result: VideoAnalysis):
    data = _load(project_path, ANALYSES_FILE, {"analyses": []})
    data["analyses"].append({
        "timestamp":      result.timestamp,
        "video_name":     result.video_name,
        "mode":           result.mode,
        "duration_sec":   result.duration_sec,
        "frames_analyzed": result.frames_analyzed,
        "summary":        result.summary,
        "issues_count":   len(result.issues),
        "fun_elements_count": len(result.fun_elements),
        "backlog_added":  len(result.backlog_tasks),
        "issues":         result.issues[:10],
        "fun_elements":   result.fun_elements[:10],
    })
    data["analyses"] = data["analyses"][-MAX_ANALYSES:]
    _save(project_path, ANALYSES_FILE, data)


# ============================================================
# app.py用
# ============================================================

def get_video_history(project_path: str, n: int = 10) -> list:
    data = _load(project_path, ANALYSES_FILE, {"analyses": []})
    result = []
    for a in reversed(data["analyses"][-n:]):
        result.append({
            "timestamp":    a.get("timestamp", "")[:16].replace("T", " "),
            "video_name":   a.get("video_name", ""),
            "mode":         a.get("mode", ""),
            "frames":       a.get("frames_analyzed", 0),
            "issues":       a.get("issues_count", 0),
            "fun_elements": a.get("fun_elements_count", 0),
            "backlog":      a.get("backlog_added", 0),
            "summary":      a.get("summary", "")[:80],
            "issues_detail":    a.get("issues", []),
            "fun_elements_detail": a.get("fun_elements", []),
        })
    return result


def get_video_insights(project_path: str) -> dict:
    data     = _load(project_path, ANALYSES_FILE, {"analyses": []})
    game_ins = _load(project_path, "game_insights.json", {})
    analyses = data.get("analyses", [])

    own_count = sum(1 for a in analyses if a.get("mode") == "own")
    ref_count = sum(1 for a in analyses if a.get("mode") == "reference")

    all_issues = []
    for a in analyses:
        all_issues.extend(a.get("issues", []))

    return {
        "total_analyses":    len(analyses),
        "own_analyses":      own_count,
        "reference_analyses": ref_count,
        "total_issues_found": sum(a.get("issues_count", 0) for a in analyses),
        "reference_insights": game_ins.get("reference_insights", [])[-5:],
        "has_ffmpeg":        _has_ffmpeg(),
    }
