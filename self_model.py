"""
Blackwell Dev-OS — self_model.py v1.0  (Phase 10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 10: 自己存在の最適化（Self-Model）

【何をするか】
  Blackwellが自分自身を分析して「自己モデル」を構築する。

  人間のトップエンジニアは:
    「自分はアーキテクチャ設計が得意だが、細かいUIは苦手」
    「疲れているときはエラーハンドリングを忘れやすい」
    「このプロジェクトに対して自分が果たすべき役割は何か」
    を明確に把握して行動する。

  Phase 10のBlackwell:
    全フェーズのデータを横断的に分析して:
    - 何が得意か（タスク種別 × 成功率）
    - 何が苦手か（タスク種別 × 失敗率）
    - どんなプロンプトが効くか（Phase 6の成果）
    - どのエージェントが信頼できるか（Phase 8の成果）
    - このプロジェクトのゴールに対して今何が必要か
    を統合して「自分の戦略」を自律的に決定する

【自己モデルの構造】
  strengths:    得意なタスク種別と成功率
  weaknesses:   苦手なタスク種別と失敗率
  best_models:  タスク種別ごとの最適モデル
  trust_agents: エージェントごとの信頼スコア
  project_role: このプロジェクトにおける自分の役割
  strategy:     今何に集中すべきか（週次で更新）

【何が変わるか】
  Before:
    全タスクに同じモデル・同じ戦略
  After:
    得意なタスク → 速いモデルで自信を持って実行
    苦手なタスク → Agent Societyを使って慎重に実行
    ゲームバランス → 「自分は苦手」と判断したらDesignerを優先
    大規模リファクタ → 「過去3回失敗」と知っているので準備を増やす

【保存先】
  {project}/blackwell_brain/self_model.json  ← 自己モデル
  {project}/blackwell_brain/strategy.json   ← 現在の戦略

【公開API】
  rebuild_self_model(path, model)      → SelfModel
  get_self_model(path)                 → SelfModel
  get_task_strategy(path, task_desc)   → TaskStrategy
  get_self_report(path)                → str  (app.py用)
  update_trust(path, agent, success)   → None
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


BRAIN_DIR    = "blackwell_brain"
MODEL_FILE   = "self_model.json"
STRATEGY_FILE = "strategy.json"

REBUILD_INTERVAL = 20  # 何タスクごとに自己モデルを再構築するか


# ============================================================
# データ構造
# ============================================================

@dataclass
class TaskStrategy:
    """get_task_strategy()の返り値: タスク1件の最適戦略"""
    task_desc:     str
    recommended_depth: int      # 思考の深さ（1-5）
    use_agents:    bool          # Agent Societyを使うか
    model_hint:    str           # 推奨モデル
    caution:       str           # 注意事項（自己モデルから）
    confidence:    float         # この戦略への自信（0.0-1.0）


@dataclass
class SelfModel:
    """Blackwellの自己モデル"""
    version:       int
    built_at:      str
    strengths:     list          # [{"category": str, "success_rate": float}]
    weaknesses:    list          # [{"category": str, "fail_rate": float}]
    best_models:   dict          # {task_category: model_name}
    trust_agents:  dict          # {agent_name: trust_score 0-100}
    project_role:  str           # このプロジェクトにおける自分の役割
    strategy:      str           # 現在の重点戦略
    total_tasks:   int
    overall_success_rate: float


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


# ============================================================
# 自己モデル構築: 全フェーズのデータを横断分析
# ============================================================

def rebuild_self_model(project_path: str,
                       model: str = "qwen2.5-coder:14b") -> SelfModel:
    """
    全フェーズのデータを横断的に分析して自己モデルを再構築する。
    should_rebuild()がTrueのときengine.pyから呼ぶ。
    """
    print("[self_model] 自己モデル再構築を開始...")

    # ── データ収集: 全フェーズから ────────────────────────
    raw = _collect_all_data(project_path)

    # ── 統計分析 ──────────────────────────────────────────
    strengths, weaknesses = _analyze_skill_profile(raw["timeline"])
    best_models           = _analyze_model_performance(raw["parallel"])
    trust_agents          = _analyze_agent_trust(raw["agent_sessions"])
    overall_success       = _calc_overall_success(raw["timeline"])
    total_tasks           = len(raw["timeline"])

    # ── AIによる役割・戦略の言語化 ────────────────────────
    project_role, strategy = _generate_role_and_strategy(
        raw, strengths, weaknesses, model, project_path
    )

    self_model_data = {
        "version":    _get_current_version(project_path) + 1,
        "built_at":   datetime.now().isoformat(),
        "strengths":  strengths,
        "weaknesses": weaknesses,
        "best_models": best_models,
        "trust_agents": trust_agents,
        "project_role": project_role,
        "strategy":   strategy,
        "total_tasks": total_tasks,
        "overall_success_rate": overall_success,
    }
    _save_json(project_path, MODEL_FILE, self_model_data)

    print(f"[self_model] 自己モデル v{self_model_data['version']} 構築完了")
    print(f"[self_model]   得意: {[s['category'] for s in strengths[:2]]}")
    print(f"[self_model]   苦手: {[w['category'] for w in weaknesses[:2]]}")
    print(f"[self_model]   総合成功率: {overall_success:.0%}")

    return _dict_to_model(self_model_data)


def _collect_all_data(project_path: str) -> dict:
    """全フェーズのJSONから生データを収集"""
    brain = _brain_dir(project_path)

    def load(filename):
        p = os.path.join(brain, filename)
        if not os.path.exists(p):
            return {}
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    timeline_data = load("timeline.json")
    return {
        "timeline":      timeline_data.get("events", []),
        "lessons":       timeline_data.get("lessons", []),
        "parallel":      load("parallel_cache.json").get("records", []),
        "predictions":   load("prediction_store.json").get("predictions", {}),
        "agent_sessions": load("agent_sessions.json").get("sessions", []),
        "play_sessions": load("play_sessions.json").get("sessions", []),
        "training":      load("training_stats.json"),
        "evolved":       load("evolved_prompts.json"),
        "contracts":     load("contract_store.json"),
    }


def _analyze_skill_profile(events: list) -> tuple:
    """タスク種別ごとの成功率を分析して得意・苦手を特定"""
    category_stats = {}

    for e in events:
        if e.get("type") not in ("task_success", "task_failure"):
            continue
        tags = e.get("tags", [])
        success = e.get("type") == "task_success"
        score   = e.get("score", 50)

        for tag in tags[:3]:  # 最大3タグ
            if tag not in category_stats:
                category_stats[tag] = {"success": 0, "fail": 0, "scores": []}
            if success:
                category_stats[tag]["success"] += 1
            else:
                category_stats[tag]["fail"] += 1
            category_stats[tag]["scores"].append(score)

    strengths  = []
    weaknesses = []

    for cat, stats in category_stats.items():
        total = stats["success"] + stats["fail"]
        if total < 3:  # サンプル不足は除外
            continue
        success_rate = stats["success"] / total
        avg_score    = sum(stats["scores"]) / len(stats["scores"])

        if success_rate >= 0.75:
            strengths.append({
                "category":    cat,
                "success_rate": round(success_rate, 2),
                "avg_score":   int(avg_score),
                "samples":     total,
            })
        elif success_rate <= 0.45:
            weaknesses.append({
                "category":  cat,
                "fail_rate": round(1 - success_rate, 2),
                "avg_score": int(avg_score),
                "samples":   total,
            })

    strengths.sort(key=lambda x: -x["success_rate"])
    weaknesses.sort(key=lambda x: -x["fail_rate"])
    return strengths[:5], weaknesses[:5]


def _analyze_model_performance(parallel_records: list) -> dict:
    """並列シミュのキャッシュからモデルごとのパフォーマンスを分析"""
    # 現時点ではPathA/B/Cの採用率で代替
    path_scores = {"A": [], "B": [], "C": []}
    for rec in parallel_records:
        for pname, cand in rec.get("candidates", {}).items():
            score = cand.get("score", 0)
            if pname in path_scores:
                path_scores[pname].append(score)

    best = {}
    for pname, scores in path_scores.items():
        if scores:
            avg = sum(scores) / len(scores)
            if avg >= 70:
                best[f"path_{pname}_style"] = avg

    return best


def _analyze_agent_trust(agent_sessions: list) -> dict:
    """エージェントセッションからエージェントへの信頼スコアを計算"""
    agent_scores = {}
    for session in agent_sessions:
        score  = session.get("score", 0)
        agents = session.get("agents", [])
        for agent in agents:
            if agent not in agent_scores:
                agent_scores[agent] = []
            agent_scores[agent].append(score)

    trust = {}
    for agent, scores in agent_scores.items():
        if scores:
            trust[agent] = int(sum(scores) / len(scores))

    return trust


def _calc_overall_success(events: list) -> float:
    successes = sum(1 for e in events if e.get("type") == "task_success")
    failures  = sum(1 for e in events if e.get("type") == "task_failure")
    total = successes + failures
    return successes / total if total > 0 else 0.5


def _generate_role_and_strategy(raw: dict,
                                 strengths: list,
                                 weaknesses: list,
                                 model: str,
                                 project_path: str) -> tuple:
    """AIがプロジェクトにおける役割と戦略を言語化する"""
    try:
        import ollama

        # プロジェクト情報を集める
        map_path = os.path.join(_brain_dir(project_path), "project_map.json")
        project_summary = ""
        if os.path.exists(map_path):
            try:
                with open(map_path, encoding="utf-8") as f:
                    pmap = json.load(f)
                files = list(pmap.keys())[:10]
                project_summary = f"ファイル: {', '.join(files)}"
            except Exception:
                pass

        strength_names  = [s["category"] for s in strengths[:3]]
        weakness_names  = [w["category"] for w in weaknesses[:3]]
        total_tasks     = len(raw["timeline"])
        play_sessions   = len(raw["play_sessions"])
        training_total  = raw["training"].get("total", 0)
        evolution_ver   = raw["evolved"].get("version", 0)

        prompt = (
            "あなたはゲーム開発AIです。以下の自己分析データをもとに、\n"
            "自分の役割と戦略を1〜2文で言語化してください。\n\n"
            f"プロジェクト: {project_summary[:200]}\n"
            f"総タスク数: {total_tasks}\n"
            f"得意分野: {strength_names}\n"
            f"苦手分野: {weakness_names}\n"
            f"学習データ: {training_total}件\n"
            f"プロンプト進化: v{evolution_ver}\n"
            f"ゲームプレイ分析: {play_sessions}回\n\n"
            "以下のJSON形式のみで出力（前置き不要）:\n"
            "{\n"
            '  "role": "このプロジェクトにおける自分の役割（1文）",\n'
            '  "strategy": "今集中すべき戦略（1文・具体的に）"\n'
            "}"
        )

        res = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        raw_txt = res["message"]["content"]
        m = re.search(r"\{.*\}", raw_txt, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            return (
                data.get("role", "ゲーム開発の自律的パートナー"),
                data.get("strategy", "苦手分野の改善と得意分野の深化"),
            )
    except Exception as e:
        print(f"[self_model] 役割生成失敗: {e}")

    return "ゲーム開発の自律的パートナー", "品質向上と自律化の継続"


def _get_current_version(project_path: str) -> int:
    data = _load_json(project_path, MODEL_FILE, {})
    return data.get("version", 0)


def _dict_to_model(d: dict) -> SelfModel:
    return SelfModel(
        version=d.get("version", 1),
        built_at=d.get("built_at", ""),
        strengths=d.get("strengths", []),
        weaknesses=d.get("weaknesses", []),
        best_models=d.get("best_models", {}),
        trust_agents=d.get("trust_agents", {}),
        project_role=d.get("project_role", ""),
        strategy=d.get("strategy", ""),
        total_tasks=d.get("total_tasks", 0),
        overall_success_rate=d.get("overall_success_rate", 0.5),
    )


# ============================================================
# タスク戦略: 自己モデルに基づいて最適な実行戦略を返す
# ============================================================

def get_task_strategy(project_path: str,
                      task_desc: str) -> TaskStrategy:
    """
    タスクの説明を受け取り、自己モデルに基づいた
    最適な実行戦略を返す。

    engine.pyのprocess_task冒頭で呼ぶ。
    """
    model_data = _load_json(project_path, MODEL_FILE, {})
    if not model_data:
        # 自己モデルがなければデフォルト戦略
        return TaskStrategy(
            task_desc=task_desc,
            recommended_depth=3,
            use_agents=False,
            model_hint="",
            caution="",
            confidence=0.5,
        )

    task_lower    = task_desc.lower()
    weaknesses    = model_data.get("weaknesses", [])
    strengths     = model_data.get("strengths", [])
    trust_agents  = model_data.get("trust_agents", {})

    # タスクが苦手分野にマッチするか確認
    caution_parts = []
    recommended_depth = 3
    use_agents = False
    confidence = 0.7

    for w in weaknesses:
        cat = w.get("category", "")
        if cat and cat.lower() in task_lower:
            fail_rate = w.get("fail_rate", 0)
            caution_parts.append(
                f"「{cat}」は過去の失敗率{fail_rate:.0%} → 慎重に実行")
            recommended_depth = min(5, recommended_depth + 1)
            if fail_rate >= 0.5:
                use_agents = True  # 失敗率50%以上はAgent Societyを推奨
            confidence -= 0.2

    # 得意分野なら自信を持って速く
    for s in strengths:
        cat = s.get("category", "")
        if cat and cat.lower() in task_lower:
            recommended_depth = max(2, recommended_depth - 1)
            confidence = min(1.0, confidence + 0.2)

    # 信頼できるエージェントを確認
    best_agent = max(trust_agents.items(),
                     key=lambda x: x[1]) if trust_agents else None
    model_hint = ""
    if best_agent and best_agent[1] >= 80:
        caution_parts.append(
            f"信頼エージェント「{best_agent[0]}」を優先的に使用")

    caution = " / ".join(caution_parts) if caution_parts else ""

    return TaskStrategy(
        task_desc=task_desc,
        recommended_depth=recommended_depth,
        use_agents=use_agents,
        model_hint=model_hint,
        caution=caution,
        confidence=max(0.1, min(1.0, confidence)),
    )


def should_rebuild(project_path: str) -> bool:
    """自己モデルの再構築が必要かどうか"""
    model_data = _load_json(project_path, MODEL_FILE, {})
    if not model_data:
        return True

    # timeline.jsonのタスク数と最後の構築時のタスク数を比較
    brain = _brain_dir(project_path)
    tl_path = os.path.join(brain, "timeline.json")
    if not os.path.exists(tl_path):
        return False

    try:
        with open(tl_path, encoding="utf-8") as f:
            tl = json.load(f)
        current_total = len(tl.get("events", []))
        last_total    = model_data.get("total_tasks", 0)
        return (current_total - last_total) >= REBUILD_INTERVAL
    except Exception:
        return False


def update_trust(project_path: str, agent: str, success: bool):
    """エージェントへの信頼スコアを更新する（タスク完了後）"""
    model_data = _load_json(project_path, MODEL_FILE, {})
    if not model_data:
        return

    trust = model_data.get("trust_agents", {})
    current = trust.get(agent, 70)
    # 成功+3 / 失敗-5（失敗は厳しめに評価）
    delta = 3 if success else -5
    trust[agent] = max(0, min(100, current + delta))
    model_data["trust_agents"] = trust
    _save_json(project_path, MODEL_FILE, model_data)


# ============================================================
# app.py用: 自己レポート生成
# ============================================================

def get_self_model(project_path: str) -> Optional[SelfModel]:
    data = _load_json(project_path, MODEL_FILE, {})
    if not data:
        return None
    return _dict_to_model(data)


def get_self_report(project_path: str) -> str:
    """人間が読める自己分析レポートを生成する"""
    model = get_self_model(project_path)
    if not model:
        return "まだ自己モデルが構築されていません。\n20タスク以上実行すると自動構築されます。"

    lines = [
        f"# 🤔 Blackwell 自己分析レポート v{model.version}",
        f"**構築日時:** {model.built_at[:16].replace('T', ' ')}",
        f"**総タスク:** {model.total_tasks}件",
        f"**総合成功率:** {model.overall_success_rate:.0%}",
        "",
        f"## 🎯 このプロジェクトでの役割",
        f"> {model.project_role}",
        "",
        f"## 🔥 現在の戦略",
        f"> {model.strategy}",
        "",
    ]

    if model.strengths:
        lines += ["## ✅ 得意なこと", ""]
        for s in model.strengths[:3]:
            lines.append(
                f"- **{s['category']}** "
                f"（成功率 {s['success_rate']:.0%} / "
                f"平均スコア {s.get('avg_score', 0)}）"
            )
        lines.append("")

    if model.weaknesses:
        lines += ["## ⚠️ 苦手なこと（対策中）", ""]
        for w in model.weaknesses[:3]:
            lines.append(
                f"- **{w['category']}** "
                f"（失敗率 {w['fail_rate']:.0%} / "
                f"→ 複雑さ+1・Agent Society推奨）"
            )
        lines.append("")

    if model.trust_agents:
        lines += ["## 🤖 エージェント信頼スコア", ""]
        icons = {"architect": "🏛️", "coder": "💻", "critic": "🔍",
                 "tester": "🧪", "designer": "🎮", "integrator": "🎯"}
        for agent, score in sorted(model.trust_agents.items(),
                                   key=lambda x: -x[1]):
            bar = "█" * (score // 10) + "░" * (10 - score // 10)
            lines.append(
                f"- {icons.get(agent,'🤖')} **{agent}**: "
                f"`{bar}` {score}/100"
            )
        lines.append("")

    return "\n".join(lines)
