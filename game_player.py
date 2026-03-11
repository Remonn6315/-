"""
Blackwell Dev-OS — game_player.py v1.0  (Phase 9)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 9: ゲームを自分でプレイして学習

【今までとの違い】
  gameplay_analyzer.py（既存）:
    1枚のスクショを見て「問題がある」と指摘する
    → 人間が修正する

  Phase 9（game_player.py）:
    スクショを見て「問題がある」→ 自分でコードを修正する
    また見る → まだ問題がある → また修正する
    これをループして「良いゲーム」に近づける
    全ての観察・修正を記憶して学習データにする

【プレイサイクル】
  Step 1: スクショを受け取る（人間がアップロードまたは自動キャプチャ）
  Step 2: ビジョンAIで「何が問題か」を検出
  Step 3: 問題を「修正タスク」に変換
  Step 4: engine.pyのprocess_taskで自律修正
  Step 5: 結果を記録して学習データに追加
  Step 6: Step 1に戻る

【学習の蓄積】
  - 「このシーンでこの問題が多い」というパターンを記憶
  - 修正したコードの前後を比較して何が改善されたかを学習
  - 「面白さスコア」を独自に定義して追跡

【保存先】
  {project}/blackwell_brain/play_sessions.json  ← プレイセッション
  {project}/blackwell_brain/game_insights.json  ← 学習した知見

【公開API】
  analyze_and_fix(image_path, project_path, anchor, auto_fix) → PlayResult
  analyze_and_fix_bytes(image_bytes, ...) → PlayResult
  run_play_loop(screenshots, project_path, anchor, max_fixes)  → list[PlayResult]
  get_game_insights(project_path)         → dict
  get_play_history(project_path, n)       → list
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import os
import re
import base64
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


BRAIN_DIR     = "blackwell_brain"
SESSIONS_FILE = "play_sessions.json"
INSIGHTS_FILE = "game_insights.json"

MAX_SESSIONS  = 100


# ============================================================
# データ構造
# ============================================================

@dataclass
class PlayIssue:
    """ビジョンAIが検出した問題1件"""
    category:    str   # "bug" / "balance" / "ux" / "visual" / "performance"
    description: str   # 何が問題か
    location:    str   # どこで発生しているか（画面の説明）
    severity:    str   # "critical" / "major" / "minor"
    fix_hint:    str   # どう修正すべきか（ヒント）
    target_file: str   # 修正すべきファイル（推定）


@dataclass
class PlayResult:
    """analyze_and_fix()の返り値"""
    session_id:   str
    image_desc:   str     # ビジョンAIの画面説明
    issues:       list    # list[PlayIssue]
    fixes_applied: list   # 実際に修正したファイルと結果
    fun_score:    int     # 面白さスコア（0-100、AIによる主観評価）
    timestamp:    str


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


def _get_vision_model() -> str:
    """利用可能なビジョンモデルを返す"""
    try:
        import ollama
        models = ollama.list()
        names  = [m["name"] for m in models.get("models", [])]
        for preferred in ["llava-llama3:latest", "llava:latest",
                          "llava:13b", "moondream:latest"]:
            if preferred in names:
                return preferred
        # フォールバック
        for n in names:
            if "llava" in n or "vision" in n or "moondream" in n:
                return n
    except Exception:
        pass
    return "llava:latest"


def _image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ============================================================
# Phase 9 コア: 見る → 問題発見 → 修正
# ============================================================

def analyze_and_fix(image_path: str,
                    project_path: str = "./",
                    anchor: str = "",
                    auto_fix: bool = True,
                    model: str = "") -> PlayResult:
    """
    スクショを見て問題を検出し、自動修正する。

    auto_fix=True: 検出した問題を自律的にprocess_taskで修正
    auto_fix=False: 問題の検出だけ行う（確認用）
    """
    image_bytes = open(image_path, "rb").read()
    return analyze_and_fix_bytes(
        image_bytes, project_path, anchor, auto_fix, model)


def analyze_and_fix_bytes(image_bytes: bytes,
                           project_path: str = "./",
                           anchor: str = "",
                           auto_fix: bool = True,
                           model: str = "") -> PlayResult:
    """バイト列から解析・修正する（app.pyのst.file_uploader用）"""
    session_id = f"play_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    model = model or _get_vision_model()
    b64   = base64.b64encode(image_bytes).decode("utf-8")

    print(f"[game_player] 解析開始: {session_id} / モデル={model}")

    # ── Step 1: 画面全体の説明 ────────────────────────────
    image_desc = _describe_screen(b64, model, anchor)
    print(f"[game_player] 画面説明: {image_desc[:60]}")

    # ── Step 2: 問題の検出 ────────────────────────────────
    issues, fun_score = _detect_issues(b64, model, anchor, image_desc)
    print(f"[game_player] 問題検出: {len(issues)}件 / 面白さスコア: {fun_score}")

    fixes_applied = []

    # ── Step 3: 自動修正 ──────────────────────────────────
    if auto_fix and issues:
        critical = [i for i in issues if i.severity == "critical"]
        major    = [i for i in issues if i.severity == "major"]
        targets  = (critical + major)[:3]  # 最大3件修正

        for issue in targets:
            fix_result = _apply_fix(issue, project_path, anchor, image_desc)
            fixes_applied.append(fix_result)
            print(f"[game_player]   修正: {issue.description[:40]} "
                  f"→ {'✅' if fix_result.get('success') else '❌'}")

    # ── Step 4: 記録 ──────────────────────────────────────
    result = PlayResult(
        session_id=session_id,
        image_desc=image_desc,
        issues=issues,
        fixes_applied=fixes_applied,
        fun_score=fun_score,
        timestamp=datetime.now().isoformat(),
    )
    _save_session(project_path, result)
    _update_insights(project_path, result)

    return result


def _describe_screen(b64: str, model: str, anchor: str) -> str:
    """ビジョンAIにゲーム画面を説明させる"""
    try:
        import ollama
        prompt = (
            f"このゲーム画面を説明してください。\n"
            f"ゲームの種類: {anchor[:100] if anchor else '不明'}\n\n"
            "以下を日本語で答えてください:\n"
            "1. 現在の画面状況（何が表示されているか）\n"
            "2. プレイヤーキャラクターの状態\n"
            "3. UI要素（HP/スコア/アイテムなど）\n"
            "4. 全体的な雰囲気・完成度\n"
            "4行以内で簡潔に。"
        )
        res = ollama.chat(
            model=model,
            messages=[{
                "role": "user",
                "content": prompt,
                "images": [b64],
            }]
        )
        return res["message"]["content"][:500]
    except Exception as e:
        return f"画面説明失敗: {e}"


def _detect_issues(b64: str, model: str, anchor: str,
                   image_desc: str) -> tuple:
    """問題を検出してPlayIssueのリストと面白さスコアを返す"""
    try:
        import ollama
        prompt = (
            "このゲーム画面を見て、問題点と面白さを評価してください。\n\n"
            f"ゲーム概要: {anchor[:150] if anchor else '不明'}\n"
            f"画面状況: {image_desc[:200]}\n\n"
            "JSONのみ出力（前置き不要）:\n"
            "{\n"
            '  "fun_score": 0から100の整数（100=非常に面白い）,\n'
            '  "issues": [\n'
            "    {\n"
            '      "category": "bug/balance/ux/visual/performance のいずれか",\n'
            '      "description": "問題の説明（1行）",\n'
            '      "location": "画面のどこで発生しているか",\n'
            '      "severity": "critical/major/minor のいずれか",\n'
            '      "fix_hint": "修正のヒント（1行）",\n'
            '      "target_file": "修正すべきGDScript/Pythonファイル名（推定）"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "※ 問題は最大5件。根拠のある問題のみ。"
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
        if not m:
            return [], 50

        data       = json.loads(m.group(0))
        fun_score  = min(100, max(0, int(data.get("fun_score", 50))))
        raw_issues = data.get("issues", [])

        issues = []
        for item in raw_issues[:5]:
            issues.append(PlayIssue(
                category=item.get("category", "bug"),
                description=item.get("description", "")[:100],
                location=item.get("location", "")[:80],
                severity=item.get("severity", "minor"),
                fix_hint=item.get("fix_hint", "")[:100],
                target_file=item.get("target_file", ""),
            ))
        return issues, fun_score

    except Exception as e:
        print(f"[game_player] 問題検出失敗: {e}")
        return [], 50


def _apply_fix(issue: PlayIssue, project_path: str,
               anchor: str, screen_context: str) -> dict:
    """
    問題をprocess_taskで自動修正する。
    """
    try:
        from engine import process_task, load_grand_state

        # ファイル名の推定（target_fileが空の場合）
        target_file = issue.target_file or _guess_target_file(
            issue, project_path)

        task_desc = (
            f"【ゲーム画面で検出された問題を修正してください】\n"
            f"問題: {issue.description}\n"
            f"カテゴリ: {issue.category}\n"
            f"場所: {issue.location}\n"
            f"深刻度: {issue.severity}\n"
            f"修正ヒント: {issue.fix_hint}\n"
            f"画面状況: {screen_context[:200]}"
        )

        grand_state = load_grand_state(project_path)
        result_md, success = process_task(
            {"file": target_file, "desc": task_desc},
            auto_write=True,
            save_path=project_path,
            anchor=anchor,
            grand_state=grand_state,
        )

        return {
            "issue":   issue.description,
            "file":    target_file,
            "success": success,
            "summary": result_md[:100] if result_md else "",
        }
    except Exception as e:
        return {
            "issue":   issue.description,
            "file":    issue.target_file,
            "success": False,
            "summary": f"修正失敗: {e}",
        }


def _guess_target_file(issue: PlayIssue,
                        project_path: str) -> str:
    """target_fileが不明な場合にカテゴリから推定する"""
    category_map = {
        "bug":         "Player.gd",
        "balance":     "GameManager.gd",
        "ux":          "HUD.gd",
        "visual":      "Player.gd",
        "performance": "GameManager.gd",
    }
    # プロジェクトに実際に存在するファイルを探す
    candidate = category_map.get(issue.category, "GameManager.gd")
    for root, _, files in os.walk(project_path):
        if ".git" in root or "blackwell_brain" in root:
            continue
        for f in files:
            if f.endswith(".gd") and (
                "player" in f.lower() and issue.category in ("bug", "visual")
                or "manager" in f.lower() and issue.category in ("balance", "performance")
                or "hud" in f.lower() and issue.category == "ux"
            ):
                return f
    return candidate


# ============================================================
# 連続プレイループ
# ============================================================

def run_play_loop(screenshots: list,
                  project_path: str = "./",
                  anchor: str = "",
                  max_fixes: int = 5,
                  on_progress=None) -> list:
    """
    複数のスクショを順番に解析・修正するループ。
    夜間バッチと組み合わせて自律的に動かす。

    screenshots: list of (image_bytes or image_path)
    """
    results = []
    total_fixes = 0

    for i, img in enumerate(screenshots):
        if total_fixes >= max_fixes:
            _prog(on_progress, f"最大修正数({max_fixes})に達しました")
            break

        _prog(on_progress,
              f"🎮 [{i+1}/{len(screenshots)}] スクショを解析中...")

        if isinstance(img, str):
            result = analyze_and_fix(
                img, project_path, anchor,
                auto_fix=True,
            )
        else:
            result = analyze_and_fix_bytes(
                img, project_path, anchor,
                auto_fix=True,
            )

        results.append(result)
        total_fixes += len(result.fixes_applied)

        _prog(on_progress,
              f"  面白さ: {result.fun_score}/100 / "
              f"問題: {len(result.issues)}件 / "
              f"修正: {len(result.fixes_applied)}件")

    return results


def _prog(callback, msg: str):
    print(f"[game_player] {msg}")
    if callback:
        try:
            callback(msg)
        except Exception:
            pass


# ============================================================
# 記録・学習
# ============================================================

def _save_session(project_path: str, result: PlayResult):
    sessions = _load_json(project_path, SESSIONS_FILE,
                          {"sessions": []})
    sessions["sessions"].append({
        "session_id":   result.session_id,
        "timestamp":    result.timestamp,
        "image_desc":   result.image_desc[:200],
        "issues_count": len(result.issues),
        "fixes_count":  len(result.fixes_applied),
        "fun_score":    result.fun_score,
        "issues": [
            {
                "category":  i.category,
                "desc":      i.description,
                "severity":  i.severity,
                "file":      i.target_file,
            }
            for i in result.issues
        ],
        "fixes": result.fixes_applied,
    })
    sessions["sessions"] = sessions["sessions"][-MAX_SESSIONS:]
    _save_json(project_path, SESSIONS_FILE, sessions)


def _update_insights(project_path: str, result: PlayResult):
    """
    プレイセッションから知見を抽出・蓄積する。
    「このカテゴリの問題が多い」というパターンを学習。
    """
    insights = _load_json(project_path, INSIGHTS_FILE, {
        "total_sessions": 0,
        "avg_fun_score":  0,
        "category_counts": {},
        "severity_counts": {},
        "fun_score_history": [],
        "common_issues": [],
        "most_fixed_files": {},
    })

    n = insights["total_sessions"]
    old_avg = insights["avg_fun_score"]
    insights["total_sessions"] = n + 1
    insights["avg_fun_score"]  = int((old_avg * n + result.fun_score) / (n + 1))
    insights["fun_score_history"].append({
        "score": result.fun_score,
        "time":  result.timestamp[:16],
    })
    insights["fun_score_history"] = insights["fun_score_history"][-30:]

    for issue in result.issues:
        c = issue.category
        s = issue.severity
        insights["category_counts"][c] = \
            insights["category_counts"].get(c, 0) + 1
        insights["severity_counts"][s] = \
            insights["severity_counts"].get(s, 0) + 1
        # よく出る問題を記録
        desc = issue.description
        found = False
        for ci in insights["common_issues"]:
            if ci["desc"][:40] == desc[:40]:
                ci["count"] += 1
                found = True
                break
        if not found:
            insights["common_issues"].append({
                "desc":     desc,
                "category": c,
                "count":    1,
            })
        insights["common_issues"].sort(key=lambda x: -x["count"])
        insights["common_issues"] = insights["common_issues"][:20]

    for fix in result.fixes_applied:
        f = fix.get("file", "")
        if f:
            insights["most_fixed_files"][f] = \
                insights["most_fixed_files"].get(f, 0) + 1

    _save_json(project_path, INSIGHTS_FILE, insights)


# ============================================================
# app.py用
# ============================================================

def get_game_insights(project_path: str) -> dict:
    return _load_json(project_path, INSIGHTS_FILE, {
        "total_sessions": 0,
        "avg_fun_score":  0,
        "category_counts": {},
        "fun_score_history": [],
        "common_issues": [],
        "most_fixed_files": {},
    })


def get_play_history(project_path: str, n: int = 10) -> list:
    sessions = _load_json(project_path, SESSIONS_FILE,
                          {"sessions": []})
    result = []
    for s in reversed(sessions["sessions"][-n:]):
        result.append({
            "session_id":  s.get("session_id", ""),
            "timestamp":   s.get("timestamp", "")[:16].replace("T", " "),
            "fun_score":   s.get("fun_score", 0),
            "issues":      s.get("issues_count", 0),
            "fixes":       s.get("fixes_count", 0),
            "image_desc":  s.get("image_desc", "")[:60],
        })
    return result
