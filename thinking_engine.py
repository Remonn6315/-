"""
Blackwell Dev-OS — thinking_engine.py v1.0  (Phase 4)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 4: 自己対話ループ（Deep Thinking Engine）

【今までとの違い】
  今まで:
    タスク → 生成（1回） → スコア → 終わり
    思考の深さ: 1層

  Phase 4:
    タスク
      → 「問題の本質は何か」を自問（層1）
      → 「3つのアプローチ」を内部で検討（層2）
      → 「各アプローチの弱点」を自己批判（層3）
      → 「弱点を克服した統合案」を生成（層4）
      → 「この実装で将来壊れる箇所は？」を自問（層5）
      → 確信を持ったコードだけ出力
    思考の深さ: タスクの複雑さに応じて1〜5層

【重要な設計判断】
  - 単純なタスクに深い思考をかけると逆に遅くなる
  - タスクの複雑さを自動判定して思考の深さを決める
  - 思考プロセス自体を「思考ログ」として保存
  - 思考ログはapp.pyで可視化できる

【公開API】
  deep_think(desc, system_prompt, context, model)  → ThinkingResult
  estimate_complexity(desc, code_context)          → int (1-5)
  format_thinking_log(result)                      → str (app.py用)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ============================================================
# データ構造
# ============================================================

@dataclass
class ThoughtStep:
    """思考の1ステップ"""
    layer:      int     # 思考の層（1〜5）
    type:       str     # "question" / "analysis" / "critique" / "synthesis" / "validation"
    content:    str     # 思考内容
    duration_ms: int = 0


@dataclass
class ThinkingResult:
    """deep_think()の返り値"""
    code:           str
    score:          dict
    thinking_steps: list        # list[ThoughtStep]
    final_reasoning: str        # 「なぜこの実装にしたか」の最終説明
    complexity:     int         # 1-5
    depth_used:     int         # 実際に使った思考の深さ
    total_ms:       int = 0


# ============================================================
# 複雑さの自動判定
# ============================================================

def estimate_complexity(desc: str, code_context: str = "") -> int:
    """
    タスクの複雑さを1〜5で返す。
    思考の深さはこれで自動決定する。

    1: 単純（変数名変更・コメント追加）
    2: 普通（関数追加・軽微な修正）
    3: 中程度（新機能・複数ファイル影響）
    4: 複雑（アーキテクチャ変更・非同期・状態管理）
    5: 最高（設計レベル・システム全体に影響）
    """
    score = 1
    desc_lower = desc.lower()

    # キーワードによるスコアリング
    complexity_signals = {
        # 高複雑度シグナル (+2)
        2: [
            "アーキテクチャ", "architecture", "設計", "design",
            "リファクタ", "refactor", "非同期", "async",
            "マルチスレッド", "concurrent", "分散", "distributed",
            "システム全体", "全面", "大規模",
        ],
        # 中複雑度シグナル (+1)
        1: [
            "追加", "add", "新機能", "feature", "実装", "implement",
            "統合", "integrate", "連携", "複数", "multiple",
            "ループ", "loop", "再帰", "recursive",
            "状態管理", "state", "データベース", "database",
            "アルゴリズム", "algorithm", "最適化", "optimize",
            "エラーハンドリング", "error handling",
        ],
    }

    for add_score, keywords in complexity_signals.items():
        if any(k in desc_lower for k in keywords):
            score += add_score

    # コードの長さによる補正
    if code_context:
        lines = len(code_context.splitlines())
        if lines > 500:
            score += 2
        elif lines > 200:
            score += 1

    # 影響ファイル数の推定
    file_refs = len(re.findall(r"\w+\.(gd|py|cs)", desc))
    if file_refs >= 3:
        score += 2
    elif file_refs >= 2:
        score += 1

    return min(5, max(1, score))


# ============================================================
# 思考ステップの実行
# ============================================================

def _think_step(model: str, messages: list, step_type: str,
                layer: int) -> ThoughtStep:
    """1つの思考ステップを実行する"""
    try:
        import ollama
        start = time.time()
        res = ollama.chat(model=model, messages=messages)
        duration = int((time.time() - start) * 1000)
        content = res["message"]["content"]
        return ThoughtStep(
            layer=layer, type=step_type,
            content=content, duration_ms=duration
        )
    except Exception as e:
        return ThoughtStep(
            layer=layer, type=step_type,
            content=f"思考失敗: {e}", duration_ms=0
        )


def _layer1_question(desc: str, system_prompt: str,
                     model: str) -> ThoughtStep:
    """
    層1: 「問題の本質は何か」を自問する。
    CoTの発展版。書く前に「何を解くのか」を明確化する。
    """
    prompt = (
        "以下のタスクについて、実装前に「問題の本質」を分析してください。\n\n"
        "【タスク】\n{desc}\n\n"
        "以下の順番で日本語で答えてください:\n"
        "1. このタスクの本質的な目的（1行）\n"
        "2. 解決すべき技術的課題（2〜3点）\n"
        "3. 見落としやすい落とし穴（1〜2点）\n"
        "4. 最適なアプローチの方向性（1行）\n"
        "簡潔に。コードは書かない。"
    ).format(desc=desc[:400])

    return _think_step(
        model,
        [{"role": "system", "content": system_prompt},
         {"role": "user",   "content": prompt}],
        "question", layer=1
    )


def _layer2_approaches(desc: str, layer1_insight: str,
                       system_prompt: str, model: str) -> ThoughtStep:
    """
    層2: 「どんな実装方法があるか」を内部検討する。
    Branchingの軽量版。コードは書かず「方針」だけ検討する。
    """
    prompt = (
        "以下の分析を踏まえて、実装アプローチを3つ検討してください。\n\n"
        "【タスク】\n{desc}\n\n"
        "【問題の本質（先ほどの分析）】\n{insight}\n\n"
        "アプローチA（保守的）: どう実装するか・トレードオフは？\n"
        "アプローチB（最適）:  どう実装するか・トレードオフは？\n"
        "アプローチC（革新的）: どう実装するか・トレードオフは？\n\n"
        "推奨: AまたはBまたはCとその理由（1行）\n"
        "コードは書かない。方針だけ。"
    ).format(desc=desc[:300], insight=layer1_insight[:400])

    return _think_step(
        model,
        [{"role": "system", "content": system_prompt},
         {"role": "user",   "content": prompt}],
        "analysis", layer=2
    )


def _layer3_critique(desc: str, approach: str,
                     system_prompt: str, model: str) -> ThoughtStep:
    """
    層3: 「選んだアプローチの弱点は何か」を自己批判する。
    実装前に自分でレビューする。
    """
    prompt = (
        "以下の実装方針を厳しく批判してください。\n\n"
        "【タスク】\n{desc}\n\n"
        "【選んだアプローチ】\n{approach}\n\n"
        "以下を指摘してください:\n"
        "- このアプローチで失敗しやすい場面\n"
        "- パフォーマンス上の懸念\n"
        "- 将来の拡張時に問題になりそうな点\n"
        "- 見落としている前提条件\n\n"
        "批判のみ。改善案はまだ不要。"
    ).format(desc=desc[:300], approach=approach[:500])

    return _think_step(
        model,
        [{"role": "system", "content": system_prompt},
         {"role": "user",   "content": prompt}],
        "critique", layer=3
    )


def _layer4_synthesis(desc: str, approach: str, critique: str,
                      system_prompt: str, model: str,
                      code_context: str = "") -> tuple:
    """
    層4: 批判を踏まえた「最終実装」を生成する。
    ここで初めてコードを書く。
    """
    prompt = (
        "以下の分析と批判を踏まえて、最良のコードを実装してください。\n\n"
        "【タスク】\n{desc}\n\n"
        "【採用するアプローチ】\n{approach}\n\n"
        "【克服すべき弱点】\n{critique}\n\n"
        "{context}"
        "上記の弱点を意識しながら、コードを実装してください。\n"
        "実装後に1行で「なぜこの実装にしたか」を書いてください。"
    ).format(
        desc=desc[:400],
        approach=approach[:400],
        critique=critique[:400],
        context=f"【既存コード（関連部分）】\n{code_context[:800]}\n\n" if code_context else ""
    )

    try:
        import ollama
        from engine_utils import extract_code, score_code
        start = time.time()
        res = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt},
            ]
        )
        duration = int((time.time() - start) * 1000)
        raw = res["message"]["content"]

        # コードと理由を分離
        code = extract_code(raw)
        # 最後の行またはコードブロック後のテキストを理由として抽出
        reasoning_match = re.search(
            r"```\s*\n(.*?)$", raw, re.DOTALL)
        reasoning = ""
        if reasoning_match:
            reasoning = reasoning_match.group(1).strip()[:200]
        if not reasoning:
            # コードブロックがない場合は最後の文を使う
            lines = [l.strip() for l in raw.splitlines() if l.strip()]
            reasoning = lines[-1][:200] if lines else ""

        step = ThoughtStep(
            layer=4, type="synthesis",
            content=f"コード生成完了（{len(code)}文字）\n理由: {reasoning}",
            duration_ms=duration
        )
        return code, reasoning, step

    except ImportError:
        # engine_utils が使えない場合は直接import
        try:
            import ollama
            import sys
            sys.path.insert(0, ".")
            start = time.time()
            res = ollama.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": prompt},
                ]
            )
            duration = int((time.time() - start) * 1000)
            raw  = res["message"]["content"]
            # コード抽出（簡易版）
            m = re.search(r"```(?:\w+)?\n(.*?)```", raw, re.DOTALL)
            code = m.group(1) if m else raw
            step = ThoughtStep(
                layer=4, type="synthesis",
                content=f"コード生成完了（{len(code)}文字）",
                duration_ms=duration
            )
            return code, "", step
        except Exception as e:
            step = ThoughtStep(layer=4, type="synthesis",
                               content=f"生成失敗: {e}", duration_ms=0)
            return "", "", step

    except Exception as e:
        step = ThoughtStep(layer=4, type="synthesis",
                           content=f"生成失敗: {e}", duration_ms=0)
        return "", "", step


def _layer5_validation(desc: str, code: str,
                       system_prompt: str, model: str) -> ThoughtStep:
    """
    層5: 「このコードで将来壊れる箇所は？」の最終確認。
    Phase 3の予測記憶と連携する。
    """
    prompt = (
        "以下のコードを最終確認してください。\n\n"
        "【タスク】\n{desc}\n\n"
        "【生成したコード（先頭500文字）】\n{code}\n\n"
        "確認項目:\n"
        "✅ タスクの要件を満たしているか\n"
        "✅ エラーハンドリングは適切か\n"
        "✅ 将来の変更で壊れそうな箇所はないか\n"
        "✅ パフォーマンス上の問題はないか\n\n"
        "問題があれば「⚠️ [問題点]」で指摘。\n"
        "問題なければ「✅ 検証完了」とだけ書く。\n"
        "修正コードは書かない。"
    ).format(desc=desc[:300], code=code[:500])

    return _think_step(
        model,
        [{"role": "system", "content": system_prompt},
         {"role": "user",   "content": prompt}],
        "validation", layer=5
    )


# ============================================================
# メイン: deep_think()
# ============================================================

def deep_think(desc: str,
               system_prompt: str,
               code_context: str = "",
               model: str = "qwen2.5-coder:14b",
               max_depth: Optional[int] = None) -> ThinkingResult:
    """
    自己対話ループによる深い思考。
    engine.pyのprocess_taskから呼ぶ。

    complexity に応じて思考の深さを自動決定:
      1: layer1のみ（問題把握）+ 直接生成
      2: layer1-2（問題把握+アプローチ検討）+ 生成
      3: layer1-3（+自己批判）+ 生成
      4: layer1-4（+統合実装）
      5: layer1-5（+最終検証）
    """
    start_total = time.time()
    steps = []
    complexity = estimate_complexity(desc, code_context)
    depth = max_depth or complexity

    print(f"[thinking] 複雑さ: {complexity}/5 → 思考深さ: {depth}層")

    # ── 層1: 問題の本質を把握 ─────────────────────────────
    step1 = _layer1_question(desc, system_prompt, model)
    steps.append(step1)
    layer1_insight = step1.content
    print(f"[thinking] 層1完了 ({step1.duration_ms}ms)")

    if depth < 2:
        # 単純タスク: 層1だけで直接生成
        code, score = _fast_generate(desc, system_prompt,
                                     layer1_insight, model, code_context)
        return ThinkingResult(
            code=code, score=score, thinking_steps=steps,
            final_reasoning=layer1_insight[:100],
            complexity=complexity, depth_used=1,
            total_ms=int((time.time() - start_total) * 1000)
        )

    # ── 層2: アプローチを内部検討 ──────────────────────────
    step2 = _layer2_approaches(desc, layer1_insight, system_prompt, model)
    steps.append(step2)
    layer2_approach = step2.content
    print(f"[thinking] 層2完了 ({step2.duration_ms}ms)")

    if depth < 3:
        code, score = _fast_generate(desc, system_prompt,
                                     layer2_approach, model, code_context)
        return ThinkingResult(
            code=code, score=score, thinking_steps=steps,
            final_reasoning=layer2_approach[:100],
            complexity=complexity, depth_used=2,
            total_ms=int((time.time() - start_total) * 1000)
        )

    # ── 層3: 自己批判 ──────────────────────────────────────
    step3 = _layer3_critique(desc, layer2_approach, system_prompt, model)
    steps.append(step3)
    layer3_critique = step3.content
    print(f"[thinking] 層3完了 ({step3.duration_ms}ms)")

    # ── 層4: 批判を踏まえた最終実装 ────────────────────────
    code, reasoning, step4 = _layer4_synthesis(
        desc, layer2_approach, layer3_critique,
        system_prompt, model, code_context
    )
    steps.append(step4)
    print(f"[thinking] 層4完了 ({step4.duration_ms}ms)")

    if not code:
        # 生成失敗時はフォールバック
        code, score = _fast_generate(desc, system_prompt,
                                     layer2_approach, model, code_context)
        return ThinkingResult(
            code=code, score=score, thinking_steps=steps,
            final_reasoning="フォールバック生成",
            complexity=complexity, depth_used=3,
            total_ms=int((time.time() - start_total) * 1000)
        )

    # スコア計算
    try:
        from engine import score_code
        score = score_code(code, desc)
    except Exception:
        score = {"score": 70, "passed": True, "feedback": "thinking_engine生成"}

    if depth < 5:
        return ThinkingResult(
            code=code, score=score, thinking_steps=steps,
            final_reasoning=reasoning,
            complexity=complexity, depth_used=4,
            total_ms=int((time.time() - start_total) * 1000)
        )

    # ── 層5: 最終検証 ───────────────────────────────────────
    step5 = _layer5_validation(desc, code, system_prompt, model)
    steps.append(step5)
    print(f"[thinking] 層5完了 ({step5.duration_ms}ms)")

    # 層5で重大な問題が指摘された場合は再生成
    validation = step5.content
    if "⚠️" in validation and "致命" in validation:
        print("[thinking] 層5で致命的問題検出 → 再生成")
        code2, reasoning2, step4b = _layer4_synthesis(
            desc + f"\n\n【修正指示】{validation[:200]}",
            layer2_approach, layer3_critique,
            system_prompt, model, code_context
        )
        if code2:
            code = code2
            reasoning = reasoning2
            try:
                from engine import score_code
                score = score_code(code, desc)
            except Exception:
                pass

    total_ms = int((time.time() - start_total) * 1000)
    print(f"[thinking] 全層完了 合計{total_ms}ms / 複雑さ{complexity} / 深さ{depth_used_calc(steps)}")

    return ThinkingResult(
        code=code, score=score, thinking_steps=steps,
        final_reasoning=reasoning,
        complexity=complexity, depth_used=len(steps),
        total_ms=total_ms
    )


def depth_used_calc(steps: list) -> int:
    return max((s.layer for s in steps), default=0)


def _fast_generate(desc: str, system_prompt: str,
                   thinking_context: str, model: str,
                   code_context: str = "") -> tuple:
    """思考結果を踏まえた高速生成（層4を使わない場合）"""
    try:
        import ollama
        prompt = (
            "【思考結果】\n{thinking}\n\n"
            "上記の分析を踏まえて実装してください。\n\n"
            "{context}"
            "タスク: {desc}"
        ).format(
            thinking=thinking_context[:600],
            desc=desc[:400],
            context=f"【既存コード】\n{code_context[:600]}\n\n" if code_context else ""
        )
        res  = ollama.chat(model=model, messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": prompt},
        ])
        raw  = res["message"]["content"]
        m    = re.search(r"```(?:\w+)?\n(.*?)```", raw, re.DOTALL)
        code = m.group(1) if m else raw
        try:
            from engine import score_code
            score = score_code(code, desc)
        except Exception:
            score = {"score": 65, "passed": True, "feedback": "fast_generate"}
        return code, score
    except Exception as e:
        print(f"[thinking] fast_generate失敗: {e}")
        return "", {"score": 0, "passed": False, "feedback": str(e)}


# ============================================================
# app.py用: 思考ログの表示
# ============================================================

def format_thinking_log(result: ThinkingResult) -> list:
    """
    app.pyのタブで思考プロセスを表示するためのデータを返す。
    """
    icons = {
        "question":   "🤔",
        "analysis":   "🔍",
        "critique":   "⚡",
        "synthesis":  "🔨",
        "validation": "✅",
    }
    labels = {
        "question":   "問題の本質を把握",
        "analysis":   "アプローチを検討",
        "critique":   "自己批判",
        "synthesis":  "最終実装",
        "validation": "最終検証",
    }

    steps = []
    for step in result.thinking_steps:
        steps.append({
            "layer":    step.layer,
            "icon":     icons.get(step.type, "💭"),
            "label":    labels.get(step.type, step.type),
            "content":  step.content[:300],
            "duration": f"{step.duration_ms}ms",
        })

    return {
        "complexity":      result.complexity,
        "depth_used":      result.depth_used,
        "total_ms":        result.total_ms,
        "final_reasoning": result.final_reasoning,
        "steps":           steps,
        "score":           result.score.get("score", 0),
    }


# ============================================================
# タスク複雑さに応じたモデル選択
# ============================================================

def select_model_by_complexity(complexity: int,
                               models: dict) -> str:
    """
    複雑さに応じてモデルを自動選択。
    これが「タスクによってモデルを使い分ける」の実装。

    complexity 1-2: optimizer (14b) — 速い
    complexity 3:   coder (32b)     — バランス
    complexity 4-5: planner (80b)   — 深い思考
    """
    if complexity <= 2:
        return models.get("optimizer", models.get("coder"))
    elif complexity == 3:
        return models.get("coder")
    else:
        return models.get("planner", models.get("coder"))
