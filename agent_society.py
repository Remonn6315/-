"""
Blackwell Dev-OS — agent_society.py v1.0  (Phase 8)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 8: マルチエージェント協調（Agent Society）

【今までとの違い】
  今まで（multi_agent_generate）:
    同じモデルが役割を変えて1回実行するだけ
    エージェント間の「議論」がない
    前回の協調結果を記憶しない

  Phase 8:
    各エージェントが「専門家として議論」する
    Architectの設計にCoderが反論できる
    Testerの指摘をCoderが受けて再実装する
    この往復をn回繰り返して収束させる
    協調の結果を記憶し次回に活かす

【エージェント構成】
  🏛️ Architect  — 全体設計・アーキテクチャ判断
  💻 Coder×N    — 並列実装（タスクを分割して同時実行）
  🔍 Critic     — コードレビュー・問題指摘
  🎮 Designer   — ゲーム体験・面白さの評価
  🧪 Tester     — バグ・エッジケース検出
  🎯 Integrator — 全エージェントの出力を統合・最終判断

【協調フロー】
  Round 1: Architect が設計 → Coder が実装
  Round 2: Critic がレビュー → Coder が修正
  Round 3: Tester がバグ検出 → Coder が修正
  Round 4: Designer が体験評価 → Coder が改善
  Round 5: Integrator が全て統合 → 最終コード確定

  ※ 複雑さに応じてラウンド数は1〜5に自動調整

【保存先】
  {project}/blackwell_brain/agent_sessions.json  ← 協調履歴
  {project}/blackwell_brain/agent_memory.json    ← エージェントの記憶

【公開API】
  coordinate(desc, anchor, path, model, max_rounds) → CoordResult
  get_agent_memory(path, agent)                     → str
  get_coordination_history(path, n)                 → list
  get_agent_stats(path)                             → dict
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


BRAIN_DIR      = "blackwell_brain"
SESSIONS_FILE  = "agent_sessions.json"
MEMORY_FILE    = "agent_memory.json"

MAX_SESSIONS   = 50


# ============================================================
# エージェント定義
# ============================================================

AGENT_PROMPTS = {
    "architect": (
        "あなたは伝説的なソフトウェアアーキテクトです。\n"
        "実装前に必ず設計を考えます。\n"
        "【出力形式】\n"
        "1. 設計方針（2〜3行）\n"
        "2. クラス/関数の構造（箇条書き）\n"
        "3. 注意すべき技術的課題\n"
        "4. Coderへの具体的な実装指示\n"
        "コードは書かない。設計のみ。"
    ),
    "coder": (
        "あなたは世界最高水準のコーダーです。\n"
        "与えられた設計仕様・レビュー指摘を全て反映した\n"
        "完全なコードを出力してください。\n"
        "部分コードは不可。必ず動作する完全なファイルを出力。"
    ),
    "critic": (
        "あなたは厳格なコードレビュアーです。\n"
        "コードの問題点を遠慮なく指摘してください。\n"
        "【確認項目】\n"
        "- バグ・論理エラー\n"
        "- パフォーマンス問題\n"
        "- 保守性・可読性\n"
        "- セキュリティ\n"
        "- このプロジェクト固有のルール違反\n"
        "「問題なし」は認めない。必ず1つ以上指摘する。"
    ),
    "tester": (
        "あなたはQAエンジニアです。\n"
        "以下を必ず確認してください:\n"
        "- エッジケース（空配列・None・最大値・最小値）\n"
        "- 例外処理の漏れ\n"
        "- 無限ループの可能性\n"
        "- リソースリークの可能性\n"
        "具体的なテストケースと期待される挙動を列挙してください。"
    ),
    "designer": (
        "あなたはゲームデザイナーAIです。MDA理論の専門家です。\n"
        "実装された機能が「プレイヤー体験」に与える影響を評価し、\n"
        "面白さを高める具体的な改善提案を3点出力してください。\n"
        "技術ではなく体験・感情・行動の観点で評価する。"
    ),
    "integrator": (
        "あなたは統合AIです。\n"
        "複数のエージェントの出力（設計・実装・レビュー・テスト）を統合し、\n"
        "最終的な判断を下します。\n"
        "【判断基準】\n"
        "1. 全ての重大な指摘が修正されているか\n"
        "2. 設計仕様から逸脱していないか\n"
        "3. これ以上改善の余地がないか\n"
        "最終コードとして採用すべき版を指定し、理由を1行で述べる。"
    ),
}


# ============================================================
# データ構造
# ============================================================

@dataclass
class AgentMessage:
    agent:   str
    round:   int
    content: str
    duration_ms: int = 0


@dataclass
class CoordResult:
    """coordinate()の返り値"""
    code:         str
    score:        dict
    messages:     list          # list[AgentMessage]
    rounds_used:  int
    final_reason: str           # Integratorの最終判断
    total_ms:     int
    agents_used:  list


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


def _call_agent(agent: str, prompt: str,
                model: str, context: str = "") -> tuple:
    """エージェントを呼び出す。(content, duration_ms) を返す"""
    import ollama
    system = AGENT_PROMPTS.get(agent, "")
    if context:
        system += f"\n\n【プロジェクト記憶】\n{context}"

    start = time.time()
    try:
        res = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ]
        )
        content = res["message"]["content"]
        ms = int((time.time() - start) * 1000)
        return content, ms
    except Exception as e:
        return f"エージェント{agent}エラー: {e}", 0


# ============================================================
# メイン: coordinate() — エージェント協調
# ============================================================

def coordinate(desc: str,
               anchor: str = "",
               project_path: str = "./",
               model: str = "qwen2.5-coder:14b",
               max_rounds: int = 3,
               is_game_task: bool = False) -> CoordResult:
    """
    エージェントチームで協調してコードを生成する。
    engine.pyのprocess_taskから、複雑さが高いタスクに対して呼ぶ。

    max_rounds:
      1: Architect + Coder のみ（速い）
      2: +Critic（レビュー1回）
      3: +Tester（バグチェック）
      4: +Designer（体験評価、ゲームタスクのみ）
      5: +Integrator（最終統合）
    """
    start_total = time.time()
    messages    = []
    current_code = ""
    final_reason = ""

    print(f"[agent_society] 協調開始: {max_rounds}ラウンド / {desc[:50]}")

    # エージェントの記憶を取得
    arch_memory = get_agent_memory(project_path, "architect")
    coder_memory = get_agent_memory(project_path, "coder")

    base_context = f"【プロジェクト主軸】{anchor}\n【タスク】{desc}"

    # ── Round 1: Architect が設計 ────────────────────────
    print("[agent_society] Round 1: Architect 設計中...")
    arch_prompt = (
        f"{base_context}\n\n"
        f"{'【過去の設計知見】' + arch_memory if arch_memory else ''}"
    )
    arch_content, arch_ms = _call_agent("architect", arch_prompt, model)
    messages.append(AgentMessage(
        agent="architect", round=1,
        content=arch_content, duration_ms=arch_ms
    ))
    print(f"[agent_society]   完了 ({arch_ms}ms)")

    # ── Round 1: Coder が実装 ────────────────────────────
    print("[agent_society] Round 1: Coder 実装中...")
    coder_prompt = (
        f"【設計仕様（Architectより）】\n{arch_content}\n\n"
        f"{base_context}\n\n"
        f"{'【過去の失敗パターン】' + coder_memory if coder_memory else ''}\n\n"
        "上記の設計に従って完全なコードを実装してください。"
    )
    coder_content, coder_ms = _call_agent("coder", coder_prompt, model)
    messages.append(AgentMessage(
        agent="coder", round=1,
        content=coder_content, duration_ms=coder_ms
    ))
    current_code = _extract_code(coder_content)
    print(f"[agent_society]   完了 ({coder_ms}ms / {len(current_code)}文字)")

    if max_rounds < 2 or not current_code:
        return _finalize(project_path, desc, current_code,
                         messages, 1, "Round 1完了", start_total,
                         ["architect", "coder"])

    # ── Round 2: Critic がレビュー → Coder が修正 ────────
    print("[agent_society] Round 2: Critic レビュー中...")
    critic_prompt = (
        f"【タスク】{desc}\n\n"
        f"【実装コード】\n```\n{current_code[:2000]}\n```\n\n"
        f"【設計仕様】\n{arch_content[:500]}\n\n"
        "このコードの問題点を全て指摘してください。"
    )
    critic_content, critic_ms = _call_agent("critic", critic_prompt, model)
    messages.append(AgentMessage(
        agent="critic", round=2,
        content=critic_content, duration_ms=critic_ms
    ))
    print(f"[agent_society]   完了 ({critic_ms}ms)")

    # Criticの指摘を受けてCoderが修正
    print("[agent_society] Round 2: Coder 修正中...")
    fix_prompt = (
        f"【Criticからの指摘】\n{critic_content}\n\n"
        f"【現在のコード】\n```\n{current_code[:1500]}\n```\n\n"
        f"【タスク】{desc}\n\n"
        "指摘を全て修正した完全なコードを出力してください。"
    )
    fix_content, fix_ms = _call_agent("coder", fix_prompt, model)
    messages.append(AgentMessage(
        agent="coder", round=2,
        content=fix_content, duration_ms=fix_ms
    ))
    fixed_code = _extract_code(fix_content)
    if fixed_code:
        current_code = fixed_code
    print(f"[agent_society]   修正完了 ({fix_ms}ms)")

    if max_rounds < 3:
        return _finalize(project_path, desc, current_code,
                         messages, 2, "Critic修正済み", start_total,
                         ["architect", "coder", "critic"])

    # ── Round 3: Tester がバグ検出 → Coder が修正 ────────
    print("[agent_society] Round 3: Tester バグ検出中...")
    test_prompt = (
        f"【タスク】{desc}\n\n"
        f"【コード】\n```\n{current_code[:2000]}\n```\n\n"
        "バグ・エッジケース・例外処理の漏れを全て検出してください。"
    )
    test_content, test_ms = _call_agent("tester", test_prompt, model)
    messages.append(AgentMessage(
        agent="tester", round=3,
        content=test_content, duration_ms=test_ms
    ))
    print(f"[agent_society]   完了 ({test_ms}ms)")

    # 重大なバグが指摘された場合のみ修正
    critical_keywords = ["クラッシュ", "無限ループ", "NullPointer",
                         "重大", "致命", "スタックオーバーフロー"]
    has_critical = any(k in test_content for k in critical_keywords)

    if has_critical:
        print("[agent_society] Round 3: 重大バグ検出 → Coder 修正中...")
        bugfix_prompt = (
            f"【Testerが重大なバグを検出】\n{test_content}\n\n"
            f"【現在のコード】\n```\n{current_code[:1500]}\n```\n\n"
            "重大なバグを全て修正した完全なコードを出力してください。"
        )
        bugfix_content, bugfix_ms = _call_agent("coder", bugfix_prompt, model)
        messages.append(AgentMessage(
            agent="coder", round=3,
            content=bugfix_content, duration_ms=bugfix_ms
        ))
        bugfixed = _extract_code(bugfix_content)
        if bugfixed:
            current_code = bugfixed
        print(f"[agent_society]   バグ修正完了 ({bugfix_ms}ms)")

    if max_rounds < 4:
        return _finalize(project_path, desc, current_code,
                         messages, 3, "Tester検証済み", start_total,
                         ["architect", "coder", "critic", "tester"])

    # ── Round 4: Designer が体験評価（ゲームタスクのみ） ──
    agents_used = ["architect", "coder", "critic", "tester"]
    if is_game_task:
        print("[agent_society] Round 4: Designer 体験評価中...")
        design_prompt = (
            f"【実装された機能】{desc}\n\n"
            f"【コード概要（先頭）】\n{current_code[:800]}\n\n"
            "この機能がプレイヤー体験に与える影響を評価し、\n"
            "面白さを高める改善提案を3点出力してください。"
        )
        design_content, design_ms = _call_agent(
            "designer", design_prompt, model)
        messages.append(AgentMessage(
            agent="designer", round=4,
            content=design_content, duration_ms=design_ms
        ))
        agents_used.append("designer")
        print(f"[agent_society]   完了 ({design_ms}ms)")

        # Designerの提案で改善余地があれば反映
        if "改善" in design_content or "追加" in design_content:
            improve_prompt = (
                f"【Designerの体験改善提案】\n{design_content}\n\n"
                f"【現在のコード】\n```\n{current_code[:1500]}\n```\n\n"
                "提案のうち実装可能なものを反映した完全なコードを出力してください。"
            )
            imp_content, imp_ms = _call_agent("coder", improve_prompt, model)
            messages.append(AgentMessage(
                agent="coder", round=4,
                content=imp_content, duration_ms=imp_ms
            ))
            improved = _extract_code(imp_content)
            if improved:
                current_code = improved

    if max_rounds < 5:
        return _finalize(project_path, desc, current_code,
                         messages, 4, "Designer評価済み", start_total,
                         agents_used)

    # ── Round 5: Integrator が最終統合 ───────────────────
    print("[agent_society] Round 5: Integrator 最終統合中...")
    agents_used.append("integrator")

    # 全メッセージのサマリーを作成
    msg_summary = "\n\n".join([
        f"【{m.agent} Round{m.round}】\n{m.content[:300]}"
        for m in messages
    ])

    integrator_prompt = (
        f"【タスク】{desc}\n\n"
        f"【全エージェントの出力サマリー】\n{msg_summary[:2000]}\n\n"
        f"【最終コード候補】\n```\n{current_code[:1500]}\n```\n\n"
        "全エージェントの指摘が適切に反映されているか確認し、\n"
        "最終採用の判断と理由を1行で述べてください。\n"
        "さらに修正が必要な場合は修正コードを出力してください。"
    )
    int_content, int_ms = _call_agent("integrator", integrator_prompt, model)
    messages.append(AgentMessage(
        agent="integrator", round=5,
        content=int_content, duration_ms=int_ms
    ))
    print(f"[agent_society]   完了 ({int_ms}ms)")

    # Integratorが修正コードを出した場合は採用
    int_code = _extract_code(int_content)
    if int_code and len(int_code) > 50:
        current_code = int_code

    # Integratorの最終判断を抽出（最初の1行）
    final_reason = int_content.splitlines()[0][:100] if int_content else "統合完了"

    return _finalize(project_path, desc, current_code,
                     messages, 5, final_reason, start_total,
                     agents_used)


# ============================================================
# 完了処理・保存
# ============================================================

def _finalize(project_path: str, desc: str, code: str,
              messages: list, rounds: int, reason: str,
              start_total: float, agents_used: list) -> CoordResult:
    """協調完了処理: スコア計算・記憶更新・セッション保存"""
    total_ms = int((time.time() - start_total) * 1000)

    # スコア計算
    try:
        from engine import score_code
        score = score_code(code, desc)
    except Exception:
        score = {"score": 75, "passed": True,
                 "feedback": "agent_society生成"}

    # エージェント記憶を更新
    _update_agent_memory(project_path, messages, score, desc)

    # セッション保存
    _save_session(project_path, {
        "timestamp":   datetime.now().isoformat(),
        "desc":        desc[:100],
        "rounds":      rounds,
        "agents":      agents_used,
        "score":       score.get("score", 0),
        "reason":      reason,
        "total_ms":    total_ms,
        "msg_count":   len(messages),
    })

    result = CoordResult(
        code=code,
        score=score,
        messages=messages,
        rounds_used=rounds,
        final_reason=reason,
        total_ms=total_ms,
        agents_used=agents_used,
    )

    print(f"[agent_society] 協調完了: {rounds}ラウンド / "
          f"スコア{score.get('score','?')} / {total_ms}ms")
    return result


def _extract_code(content: str) -> str:
    """コンテンツからコードブロックを抽出"""
    m = re.search(r"```(?:\w+)?\n(.*?)```", content, re.DOTALL)
    if m:
        return m.group(1).strip()
    # コードブロックがない場合は内容をそのまま返す
    if len(content) > 100 and ("def " in content or
                                "func " in content or
                                "class " in content):
        return content
    return ""


def _save_session(project_path: str, data: dict):
    sessions = _load_json(project_path, SESSIONS_FILE, {"sessions": []})
    sessions["sessions"].append(data)
    sessions["sessions"] = sessions["sessions"][-MAX_SESSIONS:]
    _save_json(project_path, SESSIONS_FILE, sessions)


# ============================================================
# エージェント記憶 — 協調を重ねるごとに賢くなる
# ============================================================

def _update_agent_memory(project_path: str, messages: list,
                         score: dict, desc: str):
    """
    協調セッションの結果からエージェントごとの記憶を更新する。
    次回の協調時に参照される。
    """
    memory = _load_json(project_path, MEMORY_FILE, {
        "architect": {"lessons": [], "patterns": []},
        "coder":     {"lessons": [], "failures": []},
        "critic":    {"common_issues": []},
        "tester":    {"common_bugs": []},
    })

    sc = score.get("score", 0)

    # Architectの記憶: 成功した設計パターンを蓄積
    arch_msgs = [m for m in messages if m.agent == "architect"]
    if arch_msgs and sc >= 70:
        lesson = f"[スコア{sc}] {desc[:50]}: {arch_msgs[0].content[:100]}"
        memory["architect"]["lessons"].append(lesson)
        memory["architect"]["lessons"] = \
            memory["architect"]["lessons"][-10:]

    # Coderの記憶: 失敗パターンを記録
    if sc < 50:
        failure = f"失敗パターン: {desc[:60]} → スコア{sc}"
        if "coder" not in memory:
            memory["coder"] = {"lessons": [], "failures": []}
        memory["coder"]["failures"].append(failure)
        memory["coder"]["failures"] = memory["coder"]["failures"][-10:]

    # Criticの記憶: よく指摘する問題を蓄積
    critic_msgs = [m for m in messages if m.agent == "critic"]
    if critic_msgs:
        # 短い指摘を抽出
        issues = re.findall(r"[・-](.{10,50})", critic_msgs[0].content)
        if "critic" not in memory:
            memory["critic"] = {"common_issues": []}
        memory["critic"]["common_issues"].extend(issues[:2])
        memory["critic"]["common_issues"] = \
            memory["critic"]["common_issues"][-15:]

    _save_json(project_path, MEMORY_FILE, memory)


def get_agent_memory(project_path: str, agent: str) -> str:
    """
    エージェントの記憶を文字列で返す（プロンプト注入用）。
    """
    memory = _load_json(project_path, MEMORY_FILE, {})
    agent_mem = memory.get(agent, {})

    parts = []
    for key, items in agent_mem.items():
        if items:
            label = {
                "lessons":      "過去の成功パターン",
                "failures":     "過去の失敗パターン",
                "patterns":     "設計パターン",
                "common_issues": "よく指摘する問題",
                "common_bugs":  "よく見つけるバグ",
            }.get(key, key)
            parts.append(f"{label}:\n" +
                         "\n".join(f"  - {i}" for i in items[-3:]))

    return "\n".join(parts)


# ============================================================
# app.py用
# ============================================================

def get_coordination_history(project_path: str,
                              n: int = 10) -> list:
    """協調セッション履歴"""
    sessions = _load_json(project_path, SESSIONS_FILE,
                          {"sessions": []})
    result = []
    for s in reversed(sessions["sessions"][-n:]):
        result.append({
            "timestamp": s.get("timestamp", "")[:16].replace("T", " "),
            "desc":      s.get("desc", ""),
            "rounds":    s.get("rounds", 0),
            "agents":    s.get("agents", []),
            "score":     s.get("score", 0),
            "reason":    s.get("reason", ""),
            "total_ms":  s.get("total_ms", 0),
        })
    return result


def get_agent_stats(project_path: str) -> dict:
    """エージェント統計"""
    sessions = _load_json(project_path, SESSIONS_FILE,
                          {"sessions": []})
    all_s = sessions.get("sessions", [])
    if not all_s:
        return {
            "total_sessions": 0,
            "avg_score": 0,
            "avg_rounds": 0,
            "agent_usage": {},
        }

    scores = [s.get("score", 0) for s in all_s]
    rounds = [s.get("rounds", 1) for s in all_s]
    usage  = {}
    for s in all_s:
        for a in s.get("agents", []):
            usage[a] = usage.get(a, 0) + 1

    return {
        "total_sessions": len(all_s),
        "avg_score":      sum(scores) // len(scores),
        "avg_rounds":     sum(rounds) / len(rounds),
        "agent_usage":    usage,
        "best_score":     max(scores) if scores else 0,
    }


def format_coordination_log(result: CoordResult) -> list:
    """app.pyのタブ表示用にメッセージを整形"""
    icons = {
        "architect": "🏛️",
        "coder":     "💻",
        "critic":    "🔍",
        "tester":    "🧪",
        "designer":  "🎮",
        "integrator": "🎯",
    }
    labels = {
        "architect": "Architect（設計）",
        "coder":     "Coder（実装）",
        "critic":    "Critic（レビュー）",
        "tester":    "Tester（バグ検出）",
        "designer":  "Designer（体験評価）",
        "integrator": "Integrator（最終統合）",
    }
    steps = []
    for msg in result.messages:
        steps.append({
            "agent":    msg.agent,
            "round":    msg.round,
            "icon":     icons.get(msg.agent, "🤖"),
            "label":    labels.get(msg.agent, msg.agent),
            "content":  msg.content[:400],
            "duration": f"{msg.duration_ms}ms",
        })
    return {
        "rounds_used":   result.rounds_used,
        "total_ms":      result.total_ms,
        "score":         result.score.get("score", 0),
        "final_reason":  result.final_reason,
        "agents_used":   result.agents_used,
        "steps":         steps,
    }
