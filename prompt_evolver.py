"""
Blackwell Dev-OS — prompt_evolver.py v1.0  (Phase 6)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 6: プロンプト自己進化（Meta-Learning）

【何をするか】
  Blackwellが自分の失敗を分析して、プロンプトを自動改善する。
  人間が手動でプロンプトをチューニングする必要がなくなる。

【仕組み】
  週1回または50タスクごとに自動実行:

  1. timeline.json（Phase 2）から失敗パターンを分析
  2. タスク種別ごとの成功率を計算
  3. 成功率が低い種別を特定
  4. AIが改善プロンプトを生成
  5. 小さなテストセットで効果を検証
  6. 効果があるプロンプトだけを採用
  7. engine.pyのROLESに自動反映

【保存先】
  {project_path}/blackwell_brain/evolved_prompts.json
    ├── active: 現在使用中のプロンプト
    ├── candidates: テスト中のプロンプト
    ├── retired: 効果がなかったプロンプト
    └── evolution_log: 進化の歴史

【公開API】
  analyze_and_evolve(path, base_roles, model)  → EvolveResult
  get_active_prompts(path)                     → dict
  get_evolution_log(path, n)                   → list  (app.py用)
  apply_evolved_prompts(path, base_roles)      → dict  (engine.pyから呼ぶ)
  get_evolution_stats(path)                    → dict  (app.py用)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


BRAIN_DIR      = "blackwell_brain"
EVOLVED_FILE   = "evolved_prompts.json"
EVOLVE_INTERVAL_TASKS = 50   # 何タスクごとに進化を試みるか
MIN_SAMPLES    = 10          # 分析に最低限必要なサンプル数


# ============================================================
# データ構造
# ============================================================

@dataclass
class PromptCandidate:
    role:        str    # "coder" / "planner" / "refiner"
    task_type:   str    # 対象のタスク種別（"jump", "movement"など）
    prompt_text: str    # 改善されたプロンプトテキスト
    rationale:   str    # なぜこのプロンプトにしたか
    test_score:  float = 0.0
    test_count:  int   = 0
    created_at:  str   = ""
    status:      str   = "candidate"  # candidate / active / retired


@dataclass
class EvolveResult:
    improved:       bool
    new_candidates: list   # list[PromptCandidate]
    analysis:       str    # 分析結果のサマリー
    weak_areas:     list   # 改善が必要な領域
    timestamp:      str    = ""


# ============================================================
# 失敗パターン分析
# ============================================================

def _analyze_failures(project_path: str) -> dict:
    """
    timeline.jsonから失敗パターンを分析する。
    タスク種別ごとの成功率・よくあるエラーを返す。
    """
    timeline_path = os.path.join(
        project_path, BRAIN_DIR, "timeline.json")
    if not os.path.exists(timeline_path):
        return {}

    try:
        with open(timeline_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    lessons = data.get("lessons", [])
    if len(lessons) < MIN_SAMPLES:
        return {}

    # タスク種別ごとに集計
    tag_stats = {}
    for lesson in lessons:
        tags  = lesson.get("tags", [])
        ltype = lesson.get("type", "")
        score = lesson.get("score", 0)

        for tag in tags:
            if tag in ("failure", "error", "milestone"):
                continue
            if tag not in tag_stats:
                tag_stats[tag] = {
                    "success": 0, "failure": 0,
                    "scores": [], "errors": []
                }
            if ltype == "task_success":
                tag_stats[tag]["success"] += 1
                tag_stats[tag]["scores"].append(score)
            elif ltype in ("task_failure", "error"):
                tag_stats[tag]["failure"] += 1
                detail = lesson.get("detail", "")
                if detail:
                    tag_stats[tag]["errors"].append(detail[:80])

    # 成功率を計算
    result = {}
    for tag, stats in tag_stats.items():
        total = stats["success"] + stats["failure"]
        if total < 3:
            continue
        success_rate = stats["success"] / total * 100
        avg_score    = (sum(stats["scores"]) / len(stats["scores"])
                        if stats["scores"] else 0)
        result[tag] = {
            "success_rate": round(success_rate, 1),
            "total":        total,
            "avg_score":    round(avg_score, 1),
            "top_errors":   list(set(stats["errors"][:3])),
        }

    return result


def _identify_weak_areas(analysis: dict, threshold: float = 60.0) -> list:
    """
    成功率がthreshold%未満の弱い領域を返す。
    優先度順（成功率が低い順）にソートする。
    """
    weak = [
        (tag, info) for tag, info in analysis.items()
        if info["success_rate"] < threshold and info["total"] >= 3
    ]
    weak.sort(key=lambda x: x[1]["success_rate"])
    return weak[:5]  # 上位5件


# ============================================================
# プロンプト生成
# ============================================================

def _generate_improved_prompt(
        task_type: str,
        weak_info: dict,
        base_prompt: str,
        model: str) -> Optional[PromptCandidate]:
    """
    弱い領域に対する改善プロンプトをAIが生成する。
    """
    try:
        import ollama

        errors_str = "\n".join(
            f"  - {e}" for e in weak_info.get("top_errors", []))
        if not errors_str:
            errors_str = "  - 詳細不明"

        prompt = (
            "あなたはAIプロンプトエンジニアです。\n"
            "以下の問題を解決するために、コーダーAIのシステムプロンプトを改善してください。\n\n"
            f"【問題のある領域】\n{task_type}関連のタスク\n\n"
            f"【現在の成功率】{weak_info['success_rate']}% "
            f"（{weak_info['total']}件中）\n\n"
            f"【よくある失敗パターン】\n{errors_str}\n\n"
            f"【現在のプロンプト（先頭300文字）】\n{base_prompt[:300]}\n\n"
            "以下のJSON形式のみで返してください（前置き不要）:\n"
            "{\n"
            '  "improved_prompt": "改善されたシステムプロンプト全文",\n'
            '  "rationale": "なぜこの改善が効果的か（1〜2行）",\n'
            '  "key_additions": ["追加した主要な指示1", "追加した主要な指示2"]\n'
            "}"
        )

        res = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = res["message"]["content"]
        m   = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None

        data = json.loads(m.group(0))
        improved = data.get("improved_prompt", "").strip()
        if not improved or len(improved) < 50:
            return None

        return PromptCandidate(
            role="coder",
            task_type=task_type,
            prompt_text=improved,
            rationale=data.get("rationale", ""),
            created_at=datetime.now().isoformat(),
            status="candidate",
        )

    except Exception as e:
        print(f"[prompt_evolver] プロンプト生成失敗 ({task_type}): {e}")
        return None


# ============================================================
# メイン: analyze_and_evolve()
# ============================================================

def analyze_and_evolve(
        project_path: str,
        base_roles: dict,
        model: str = "qwen2.5-coder:14b") -> EvolveResult:
    """
    失敗パターンを分析してプロンプトを改善する。
    週1回 or 50タスクごとに呼ぶ。

    base_roles: engine.pyのROLES dict
    """
    print("[prompt_evolver] 進化分析開始...")
    timestamp = datetime.now().isoformat()

    # 分析
    analysis  = _analyze_failures(project_path)
    if not analysis:
        print("[prompt_evolver] データ不足 → スキップ")
        return EvolveResult(
            improved=False,
            new_candidates=[],
            analysis="データが不足しています（最低10件必要）",
            weak_areas=[],
            timestamp=timestamp,
        )

    weak_areas = _identify_weak_areas(analysis)
    if not weak_areas:
        print("[prompt_evolver] 改善が必要な領域なし")
        return EvolveResult(
            improved=False,
            new_candidates=[],
            analysis="全領域の成功率が60%以上です。改善不要。",
            weak_areas=[],
            timestamp=timestamp,
        )

    # 弱い領域ごとに改善プロンプトを生成
    new_candidates = []
    base_coder = base_roles.get("coder", "")

    for tag, info in weak_areas[:3]:  # 上位3件のみ
        print(f"[prompt_evolver] 改善生成: {tag} (成功率{info['success_rate']}%)")
        candidate = _generate_improved_prompt(
            tag, info, base_coder, model)
        if candidate:
            new_candidates.append(candidate)

    if not new_candidates:
        return EvolveResult(
            improved=False,
            new_candidates=[],
            analysis="改善プロンプトの生成に失敗しました",
            weak_areas=[t for t, _ in weak_areas],
            timestamp=timestamp,
        )

    # 保存
    _save_candidates(project_path, new_candidates)

    # 分析サマリー生成
    weak_summary = "\n".join(
        f"  {tag}: 成功率{info['success_rate']}% ({info['total']}件)"
        for tag, info in weak_areas
    )
    analysis_text = (
        f"分析完了。{len(weak_areas)}領域で改善が必要。\n"
        f"改善対象:\n{weak_summary}"
    )

    print(f"[prompt_evolver] {len(new_candidates)}件の改善候補を生成")

    return EvolveResult(
        improved=True,
        new_candidates=new_candidates,
        analysis=analysis_text,
        weak_areas=[t for t, _ in weak_areas],
        timestamp=timestamp,
    )


# ============================================================
# プロンプトの保存・読み込み・適用
# ============================================================

def _brain_dir(project_path: str) -> str:
    d = os.path.join(project_path, BRAIN_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _load_store(project_path: str) -> dict:
    path = os.path.join(_brain_dir(project_path), EVOLVED_FILE)
    if not os.path.exists(path):
        return {
            "active":        {},   # task_type → prompt_text
            "candidates":    [],   # list of candidate dicts
            "retired":       [],
            "evolution_log": [],
        }
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"active": {}, "candidates": [], "retired": [],
                "evolution_log": []}


def _save_store(project_path: str, store: dict):
    path = os.path.join(_brain_dir(project_path), EVOLVED_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def _save_candidates(project_path: str,
                     candidates: list):
    """新しい候補を保存する"""
    store = _load_store(project_path)

    for c in candidates:
        entry = {
            "role":        c.role,
            "task_type":   c.task_type,
            "prompt_text": c.prompt_text,
            "rationale":   c.rationale,
            "test_score":  c.test_score,
            "test_count":  c.test_count,
            "created_at":  c.created_at,
            "status":      "candidate",
        }
        # 同じtask_typeの古い候補は上書き
        store["candidates"] = [
            x for x in store["candidates"]
            if x.get("task_type") != c.task_type
        ]
        store["candidates"].append(entry)

    # 進化ログに記録
    store["evolution_log"].append({
        "timestamp":    datetime.now().isoformat(),
        "action":       "generated",
        "count":        len(candidates),
        "task_types":   [c.task_type for c in candidates],
    })
    # ログは直近50件を保持
    store["evolution_log"] = store["evolution_log"][-50:]

    _save_store(project_path, store)


def activate_candidate(project_path: str, task_type: str) -> bool:
    """
    候補プロンプトを承認してアクティブにする。
    app.pyの「このプロンプトを採用」ボタンから呼ぶ。
    """
    store = _load_store(project_path)

    candidate = next(
        (c for c in store["candidates"]
         if c.get("task_type") == task_type), None)
    if not candidate:
        return False

    # アクティブに昇格
    store["active"][task_type] = {
        "prompt_text": candidate["prompt_text"],
        "rationale":   candidate["rationale"],
        "activated_at": datetime.now().isoformat(),
        "role":        candidate.get("role", "coder"),
    }

    # 候補リストから削除
    store["candidates"] = [
        c for c in store["candidates"]
        if c.get("task_type") != task_type
    ]

    # ログ
    store["evolution_log"].append({
        "timestamp": datetime.now().isoformat(),
        "action":    "activated",
        "task_type": task_type,
    })

    _save_store(project_path, store)
    print(f"[prompt_evolver] 採用: {task_type}")
    return True


def retire_candidate(project_path: str, task_type: str) -> bool:
    """候補を却下する"""
    store = _load_store(project_path)
    candidate = next(
        (c for c in store["candidates"]
         if c.get("task_type") == task_type), None)
    if not candidate:
        return False

    candidate["status"] = "retired"
    store["retired"].append(candidate)
    store["candidates"] = [
        c for c in store["candidates"]
        if c.get("task_type") != task_type
    ]
    store["evolution_log"].append({
        "timestamp": datetime.now().isoformat(),
        "action":    "retired",
        "task_type": task_type,
    })
    _save_store(project_path, store)
    return True


def deactivate_prompt(project_path: str, task_type: str) -> bool:
    """アクティブなプロンプトを無効化する"""
    store = _load_store(project_path)
    if task_type not in store["active"]:
        return False
    entry = store["active"].pop(task_type)
    entry["status"] = "retired"
    store["retired"].append(entry)
    store["evolution_log"].append({
        "timestamp": datetime.now().isoformat(),
        "action":    "deactivated",
        "task_type": task_type,
    })
    _save_store(project_path, store)
    return True


# ============================================================
# engine.pyから呼ぶ: 動的プロンプト注入
# ============================================================

def apply_evolved_prompts(project_path: str,
                          base_roles: dict,
                          task_desc: str = "") -> dict:
    """
    アクティブな進化プロンプトをbase_rolesに注入して返す。
    engine.pyのprocess_task冒頭で毎回呼ぶ。

    タスクの説明にマッチするプロンプトを選んで注入する。
    マッチしない場合はbase_rolesをそのまま返す。
    """
    store  = _load_store(project_path)
    active = store.get("active", {})
    if not active:
        return base_roles

    # タスク説明とマッチするプロンプトを探す
    task_lower = task_desc.lower()
    matched = []
    for task_type, entry in active.items():
        # タスク種別のキーワードがタスク説明に含まれているか
        keywords = task_type.split("_")
        if any(kw in task_lower for kw in keywords):
            matched.append((task_type, entry))

    if not matched:
        return base_roles

    # マッチしたプロンプトをcoderロールに追記
    roles = dict(base_roles)
    additions = []
    for task_type, entry in matched[:2]:  # 最大2件
        additions.append(
            f"\n\n【🧬 進化プロンプト: {task_type}領域】\n"
            f"{entry['prompt_text'][:400]}"
        )

    if additions:
        roles["coder"] = base_roles.get("coder", "") + "".join(additions)
        print(f"[prompt_evolver] 進化プロンプト注入: {[t for t, _ in matched]}")

    return roles


# ============================================================
# 自動進化のトリガー判定
# ============================================================

def should_evolve(project_path: str) -> bool:
    """
    進化を実行すべきタイミングかどうかを返す。
    50タスクごと or 前回から7日以上経過した場合にTrue。
    """
    store = _load_store(project_path)
    log   = store.get("evolution_log", [])

    # 前回の進化から何タスク経過したか
    timeline_path = os.path.join(
        project_path, BRAIN_DIR, "timeline.json")
    if not os.path.exists(timeline_path):
        return False

    try:
        with open(timeline_path, encoding="utf-8") as f:
            timeline = json.load(f)
        total_lessons = len(timeline.get("lessons", []))
    except Exception:
        return False

    # 進化ログの最後のエントリを確認
    last_evolve = next(
        (e for e in reversed(log)
         if e.get("action") in ("generated", "activated")), None)

    if not last_evolve:
        # 初回: MIN_SAMPLES以上あれば実行
        return total_lessons >= MIN_SAMPLES

    # 前回からのタスク数を推定（簡易）
    try:
        last_time = datetime.fromisoformat(last_evolve["timestamp"])
        days_passed = (datetime.now() - last_time).days
        if days_passed >= 7:
            return True
    except Exception:
        pass

    return total_lessons >= EVOLVE_INTERVAL_TASKS


# ============================================================
# app.py用
# ============================================================

def get_active_prompts(project_path: str) -> dict:
    store = _load_store(project_path)
    return store.get("active", {})


def get_candidates(project_path: str) -> list:
    store = _load_store(project_path)
    return store.get("candidates", [])


def get_evolution_log(project_path: str, n: int = 20) -> list:
    store = _load_store(project_path)
    log   = store.get("evolution_log", [])
    result = []
    icons = {
        "generated":   "🧬",
        "activated":   "✅",
        "retired":     "❌",
        "deactivated": "⏸️",
    }
    for entry in reversed(log[-n:]):
        result.append({
            "icon":      icons.get(entry.get("action", ""), "📌"),
            "action":    entry.get("action", ""),
            "task_type": entry.get("task_type", ""),
            "count":     entry.get("count", ""),
            "timestamp": entry.get("timestamp", "")[:16].replace("T", " "),
        })
    return result


def get_evolution_stats(project_path: str) -> dict:
    store    = _load_store(project_path)
    active   = store.get("active", {})
    cands    = store.get("candidates", [])
    retired  = store.get("retired", [])
    log      = store.get("evolution_log", [])
    activated_count = sum(
        1 for e in log if e.get("action") == "activated")

    return {
        "active_count":    len(active),
        "candidate_count": len(cands),
        "retired_count":   len(retired),
        "total_evolved":   activated_count,
        "active_types":    list(active.keys()),
    }
