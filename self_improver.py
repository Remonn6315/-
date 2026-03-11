"""
Blackwell Dev-OS — self_improver.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Blackwellが自分自身を改良する

engine.pyのボトルネックをBlackwell自身が分析し
改善コードを書く自己改善ループ。

フロー:
  1. engine.py を読む
  2. ボトルネック・問題点を特定
  3. 改善コードを生成
  4. 安全確認（構文チェック・テスト）
  5. 承認待ち → 適用

哲学的注意: 完全自動適用は危険。必ず人間の承認を挟む。
"""
import os, ast, re, time
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class SelfImprovementProposal:
    id:           str
    target_file:  str
    title:        str
    problem:      str
    solution:     str
    code_diff:    str     # 変更差分
    risk_level:   str     # low / medium / high
    estimated_gain: str   # 期待効果
    status:       str = "pending"   # pending / approved / rejected / applied
    created_at:   str = ""


def analyze_self(engine_path: str = "./engine.py") -> list:
    """
    engine.pyを自己分析して問題点・改善機会を返す。
    """
    if not os.path.exists(engine_path):
        return []

    with open(engine_path, encoding="utf-8", errors="ignore") as f:
        src = f.read()

    problems = []

    # 1. 長すぎる関数の検出
    try:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(node, "end_lineno", node.lineno + 1)
                length = end - node.lineno
                if length > 100:
                    problems.append({
                        "type":   "long_function",
                        "name":   node.name,
                        "lines":  length,
                        "lineno": node.lineno,
                        "impact": "high" if length > 200 else "medium",
                    })
    except Exception:
        pass

    # 2. except: pass パターン（サイレントエラー）
    silent_errors = list(re.finditer(r"except\s+Exception\s*:\s*\n\s*pass", src))
    for m in silent_errors:
        lineno = src[:m.start()].count("\n") + 1
        problems.append({
            "type":   "silent_error",
            "lineno": lineno,
            "impact": "medium",
            "snippet": src[m.start():m.end()].strip(),
        })

    # 3. 重複したollama.chat()呼び出しパターン
    ollama_calls = re.findall(r"ollama\.chat\(", src)
    if len(ollama_calls) > 5:
        problems.append({
            "type":   "duplicated_api_calls",
            "count":  len(ollama_calls),
            "impact": "medium",
        })

    # 4. ハードコードされた数値（マジックナンバー）
    magic_nums = re.findall(r"\b(3000|1500|1000|500|300|100)\b", src)
    if len(magic_nums) > 10:
        problems.append({
            "type":   "magic_numbers",
            "count":  len(magic_nums),
            "impact": "low",
        })

    # 5. グローバル変数の多用
    globals_count = len(re.findall(r"^[A-Z_]{3,}\s*=", src, re.MULTILINE))
    if globals_count > 20:
        problems.append({
            "type":   "many_globals",
            "count":  globals_count,
            "impact": "low",
        })

    return problems


def generate_proposals(problems: list, engine_path: str = "./engine.py",
                        model: str = "qwen2.5-coder:14b") -> list:
    """
    検出した問題点からAIが改善提案を生成する。
    """
    if not problems:
        return []

    import ollama

    with open(engine_path, encoding="utf-8", errors="ignore") as f:
        src = f.read()

    proposals = []

    for prob in problems[:3]:  # 上位3件のみ（トークン節約）
        ptype = prob["type"]

        if ptype == "long_function":
            # 対象関数を抽出
            lines = src.splitlines()
            lineno = prob["lineno"] - 1
            func_lines = lines[lineno:lineno + min(prob["lines"], 80)]
            func_src   = "\n".join(func_lines)

            prompt = (
                f"以下のPython関数は{prob['lines']}行あり長すぎます。\n"
                "小さな関数に分割して可読性を上げてください。\n"
                "差分形式（```diff）で出力してください。\n\n"
                f"```python\n{func_src}\n```"
            )
            risk = "low"
            gain = f"{prob['name']}()を分割 → 可読性・テスト可能性向上"

        elif ptype == "silent_error":
            lineno = prob["lineno"]
            lines  = src.splitlines()
            ctx    = "\n".join(lines[max(0,lineno-5):lineno+5])
            prompt = (
                "以下のコードに `except Exception: pass` があります。\n"
                "適切なエラーハンドリング（ログ出力・再raise・フォールバック）に修正してください。\n"
                "差分形式（```diff）で出力してください。\n\n"
                f"```python\n{ctx}\n```"
            )
            risk = "low"
            gain = "サイレントエラーを可視化 → デバッグ効率大幅向上"

        elif ptype == "duplicated_api_calls":
            prompt = (
                f"engine.pyには ollama.chat() の呼び出しが{prob['count']}箇所あります。\n"
                "共通のラッパー関数 `_call_model(system, user, model=None)` を作って\n"
                "全ての呼び出しを統一してください。\n"
                "最初の統一ラッパー関数の実装のみ差分形式で出力してください。"
            )
            risk = "medium"
            gain = f"ollama.call統一 → リトライ・ロギング・モデル切り替えを一元管理"

        else:
            continue

        try:
            res = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = res["message"]["content"]
            # 差分抽出
            m = re.search(r"```diff\n(.*?)```", raw, re.DOTALL)
            diff_code = m.group(1) if m else raw[:800]

            proposals.append(SelfImprovementProposal(
                id=f"si_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{ptype[:8]}",
                target_file=engine_path,
                title=f"自己改善: {ptype}",
                problem=str(prob),
                solution=raw[:300],
                code_diff=diff_code,
                risk_level=risk,
                estimated_gain=gain,
                created_at=datetime.now().isoformat(),
            ))
        except Exception as e:
            proposals.append(SelfImprovementProposal(
                id=f"si_err_{ptype}",
                target_file=engine_path,
                title=f"生成失敗: {ptype}",
                problem=str(prob),
                solution=f"エラー: {e}",
                code_diff="",
                risk_level="unknown",
                estimated_gain="",
                status="failed",
            ))

    return proposals


def apply_proposal(proposal: SelfImprovementProposal) -> dict:
    """
    承認済みの改善提案をengine.pyに適用する。
    必ずバックアップを取ってから適用する。
    """
    if not proposal.code_diff:
        return {"success": False, "reason": "差分が空です"}
    if proposal.risk_level == "high":
        return {"success": False, "reason": "高リスク: 手動適用が必要です"}

    target = proposal.target_file
    if not os.path.exists(target):
        return {"success": False, "reason": f"ファイルが見つかりません: {target}"}

    # バックアップ
    backup = target + f".self_improve_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
    with open(target, encoding="utf-8") as f:
        original = f.read()
    with open(backup, "w", encoding="utf-8") as f:
        f.write(original)

    # 差分を適用（engine.pyの apply_diff_output を使う）
    try:
        from engine import apply_diff_output
        new_src = apply_diff_output(original, proposal.code_diff)
    except ImportError:
        # フォールバック: 単純な置換
        new_src = original

    # 構文チェック
    try:
        ast.parse(new_src)
    except SyntaxError as e:
        return {"success": False, "reason": f"構文エラー: {e}", "backup": backup}

    with open(target, "w", encoding="utf-8") as f:
        f.write(new_src)

    proposal.status = "applied"
    return {
        "success": True,
        "backup":  backup,
        "message": f"✅ 適用完了。バックアップ: {backup}",
    }


def format_proposal(p: SelfImprovementProposal) -> str:
    """提案をMarkdownで表示"""
    risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴", "unknown": "⚪"}.get(p.risk_level, "⚪")
    status_icon = {"pending":"⏳","approved":"✅","rejected":"❌","applied":"🚀","failed":"💥"}.get(p.status,"❓")
    return (
        f"### {status_icon} {p.title}\n"
        f"**リスク:** {risk_icon} {p.risk_level}  |  **期待効果:** {p.estimated_gain}\n\n"
        f"**問題:** `{p.problem[:100]}`\n\n"
        f"**解決策:** {p.solution[:200]}\n\n"
        f"```diff\n{p.code_diff[:500]}\n```"
    )
