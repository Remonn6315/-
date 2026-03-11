"""
Blackwell Dev-OS — blackwell_prediction.py v1.0  (Phase 3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 3: 人間には絶対にできない2つの能力

  【予測記憶】 — 問題が起きる前に気づく
    コードを書いた瞬間に「将来ここで壊れる」を予測して記録。
    人間は問題が起きてから気づく。AIは書く前に知っている。

    例: Player.gdに「敵が20体同時に衝突判定」という処理を書いた瞬間
        → 「ステージ3以降でフレームレート低下のリスクあり」を記録
        → 次回同じファイルを触るときに警告として注入

  【並列シミュレーション記憶】 — 選ばなかった案も記憶する
    既存の_branch_and_critique()は3案を試して1案を選ぶ。
    しかしボツになった2案の「なぜダメだったか」は今まで捨てていた。
    Phase 3ではボツ案も全て記録 → 将来「あの設計はなぜダメだったか」に答えられる。

    例: 「ジャンプをPath Bで実装しようとしたがSandbox失敗→Path Aを採用」
        → 3ヶ月後「ジャンプの非同期実装は失敗する」という知識として活きる

【保存先】
  {project_path}/blackwell_brain/prediction_store.json  ← 予測
  {project_path}/blackwell_brain/parallel_cache.json    ← 並列シミュ記録

【公開API】
  # 予測
  predict_risks(path, file, code, task, model)  → list[Risk]
  get_prediction_warning(path, file)            → str  ← engine.pyへ
  get_all_predictions(path)                     → list ← app.pyへ

  # 並列シミュレーション
  record_parallel_result(path, task, candidates, chosen) → None
  get_parallel_insight(path, task_desc)                  → str ← engine.pyへ
  get_parallel_history(path, n)                          → list ← app.pyへ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


BRAIN_DIR        = "blackwell_brain"
PREDICTION_FILE  = "prediction_store.json"
PARALLEL_FILE    = "parallel_cache.json"

MAX_PREDICTIONS  = 300
MAX_PARALLEL     = 200


# ============================================================
# 共通
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
# PREDICTION STORE — 問題が起きる前に記録する
# ============================================================

@dataclass
class Risk:
    file:        str
    description: str          # 「どんな問題が起きるか」
    trigger:     str          # 「どういう状況で起きるか」
    severity:    str          # "high" / "medium" / "low"
    suggestion:  str          # 「今のうちにすべきこと」
    predicted_at: str = ""
    resolved:    bool = False  # 解決済みフラグ


def predict_risks(project_path: str,
                  file_rel_path: str,
                  source_code: str,
                  task_desc: str,
                  model: str = "qwen2.5-coder:14b") -> list:
    """
    ファイル生成直後にAIが将来のリスクを予測して記録する。
    engine.pyのprocess_task完了後に呼ぶ。

    戻り値: list[Risk] （保存も行う）
    """
    # まずルールベースで高速に検出（AI呼び出し不要）
    rule_risks = _detect_rule_based_risks(source_code, file_rel_path)

    # AIによる深い予測（ルールでは捕捉できない問題）
    ai_risks = _predict_with_ai(source_code, task_desc, model)

    all_risks = rule_risks + ai_risks
    if not all_risks:
        return []

    # 保存
    store = _load_json(project_path, PREDICTION_FILE, {"predictions": {}})
    if file_rel_path not in store["predictions"]:
        store["predictions"][file_rel_path] = []

    for risk in all_risks:
        risk.predicted_at = datetime.now().isoformat()
        store["predictions"][file_rel_path].append({
            "file":         risk.file,
            "description":  risk.description,
            "trigger":      risk.trigger,
            "severity":     risk.severity,
            "suggestion":   risk.suggestion,
            "predicted_at": risk.predicted_at,
            "resolved":     risk.resolved,
        })

    # 上限管理
    total = sum(len(v) for v in store["predictions"].values())
    if total > MAX_PREDICTIONS:
        # 古いもの・解決済みから削除
        for key in store["predictions"]:
            store["predictions"][key] = [
                r for r in store["predictions"][key] if not r.get("resolved")
            ][-50:]

    _save_json(project_path, PREDICTION_FILE, store)
    print(f"[prediction] {len(all_risks)}件のリスク予測を記録: {file_rel_path}")
    return all_risks


def _detect_rule_based_risks(code: str, file_path: str) -> list:
    """
    ルールベースで即座にリスクを検出する（AI不要・高速）。
    よくあるアンチパターンをスキャンする。
    """
    risks = []
    lines = code.splitlines()
    fname = os.path.basename(file_path)

    # ── Python リスク ────────────────────────────────────
    if file_path.endswith(".py"):

        # 無限ループリスク
        for i, line in enumerate(lines, 1):
            if re.search(r"while\s+True", line):
                # breakがない場合
                block = "\n".join(lines[i:min(i+10, len(lines))])
                if "break" not in block and "return" not in block:
                    risks.append(Risk(
                        file=fname,
                        description="無限ループの可能性",
                        trigger="while True: の中にbreak/returnがない",
                        severity="high",
                        suggestion="脱出条件またはbreakを必ず追加する",
                    ))

        # 例外を黙って握りつぶす
        silent_excepts = len(re.findall(r"except[^:]*:\s*\n\s*pass", code))
        if silent_excepts >= 2:
            risks.append(Risk(
                file=fname,
                description="エラーが無音で消える",
                trigger=f"except: pass が{silent_excepts}箇所ある",
                severity="medium",
                suggestion="最低限 print(e) か _log(e) を入れる",
            ))

        # グローバル変数の乱用
        globals_count = len(re.findall(r"^global\s+\w+", code, re.MULTILINE))
        if globals_count >= 5:
            risks.append(Risk(
                file=fname,
                description="グローバル変数が多すぎる",
                trigger=f"global宣言が{globals_count}箇所 → 副作用が追跡困難",
                severity="medium",
                suggestion="クラスや引数で状態を管理する設計に変更を検討",
            ))

        # 再帰の深さ制限なし
        func_names = re.findall(r"def\s+(\w+)\s*\(", code)
        for fn in func_names:
            body_match = re.search(
                rf"def\s+{fn}\s*\([^)]*\).*?(?=\ndef|\Z)", code, re.DOTALL)
            if body_match and fn in body_match.group(0)[body_match.group(0).find(fn)+len(fn):]:
                if "depth" not in body_match.group(0) and "max_depth" not in body_match.group(0):
                    risks.append(Risk(
                        file=fname,
                        description=f"再帰関数 {fn}() に深さ制限がない",
                        trigger="深いデータ構造や大きな入力でスタックオーバーフロー",
                        severity="medium",
                        suggestion="max_depth引数を追加するか、反復処理に変換する",
                    ))
                    break  # 1ファイルに1件だけ

    # ── GDScript リスク ──────────────────────────────────
    elif file_path.endswith(".gd"):

        # deltaを使わない移動
        if "_process" in code or "_physics_process" in code:
            process_block = re.search(
                r"func\s+_(?:physics_)?process\s*\([^)]*\).*?(?=\nfunc|\Z)",
                code, re.DOTALL)
            if process_block:
                block = process_block.group(0)
                if ("velocity" in block or "position" in block) and "delta" not in block:
                    risks.append(Risk(
                        file=fname,
                        description="フレームレート依存の移動処理",
                        trigger="_processでdeltaを使わず直接velocityやpositionを変更している",
                        severity="high",
                        suggestion="velocity *= delta などでフレームレート非依存にする",
                    ))

        # シグナル未接続の可能性
        emit_signals = re.findall(r"emit_signal\s*\(\s*[\"'](\w+)[\"']", code)
        defined_signals = re.findall(r"signal\s+(\w+)", code)
        unregistered = [s for s in emit_signals if s not in defined_signals]
        if unregistered:
            risks.append(Risk(
                file=fname,
                description=f"シグナル {unregistered[0]} が定義されていない可能性",
                trigger="emit_signalで使っているシグナルが同ファイルに未定義",
                severity="medium",
                suggestion=f"signal {unregistered[0]} を先頭に追加するか、別ファイルで定義されているか確認",
            ))

        # get_nodeのハードコード
        hardcoded_nodes = re.findall(r'get_node\s*\(\s*["\']([^"\']+)["\']', code)
        if len(hardcoded_nodes) >= 4:
            risks.append(Risk(
                file=fname,
                description="ノードパスがハードコードされている",
                trigger=f"get_node()のパス直書きが{len(hardcoded_nodes)}箇所 → シーン構造変更で全壊",
                severity="low",
                suggestion="@onreadyとNodePath型エクスポート変数を使う",
            ))

    return risks


def _predict_with_ai(source_code: str, task_desc: str,
                     model: str) -> list:
    """AIによる深いリスク予測（ルールでは捕捉できない問題）"""
    # コードが短すぎる場合はスキップ
    if len(source_code) < 200:
        return []

    try:
        import ollama
        prompt = (
            "以下のコードの「将来起きうる問題」を予測してください。\n"
            "JSONのみ出力（前置き・説明不要）:\n"
            "[\n"
            "  {\n"
            '    "description": "どんな問題が起きるか（1行）",\n'
            '    "trigger": "どういう状況・規模で起きるか（1行）",\n'
            '    "severity": "high or medium or low",\n'
            '    "suggestion": "今のうちにすべきこと（1行）"\n'
            "  }\n"
            "]\n"
            "※ 最大3件。明らかな問題だけ。根拠のない予測は含めない。\n\n"
            f"【タスク】{task_desc[:150]}\n\n"
            f"【コード】\n{source_code[:1500]}"
        )
        res = ollama.chat(model=model,
                          messages=[{"role": "user", "content": prompt}])
        raw = res["message"]["content"]
        m   = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return []

        items = json.loads(m.group(0))
        return [
            Risk(
                file="",
                description=item.get("description", "")[:120],
                trigger=item.get("trigger", "")[:120],
                severity=item.get("severity", "medium"),
                suggestion=item.get("suggestion", "")[:120],
            )
            for item in items[:3]
            if item.get("description")
        ]
    except Exception as e:
        print(f"[prediction] AI予測失敗（スキップ）: {e}")
        return []


def get_prediction_warning(project_path: str, target_file: str) -> str:
    """
    target_fileの未解決リスクを警告として返す。
    engine.pyのprocess_task冒頭で注入する。
    """
    store = _load_json(project_path, PREDICTION_FILE, {"predictions": {}})

    # ファイル名でマッチ
    match_key = None
    for key in store["predictions"]:
        if (os.path.basename(key) == os.path.basename(target_file)
                or key == target_file):
            match_key = key
            break

    if not match_key:
        return ""

    risks = [r for r in store["predictions"][match_key]
             if not r.get("resolved")]
    if not risks:
        return ""

    # severityでソート
    order = {"high": 0, "medium": 1, "low": 2}
    risks.sort(key=lambda r: order.get(r.get("severity", "low"), 2))

    icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    lines = []
    for r in risks[:3]:
        icon = icons.get(r.get("severity", "low"), "⚪")
        lines.append(
            f"  {icon} {r['description']}\n"
            f"     発生条件: {r['trigger']}\n"
            f"     対策: {r['suggestion']}"
        )

    return (
        "\n\n【🔮 予測リスク（過去の分析から）】\n"
        + "\n".join(lines)
        + "\n→ 今回の修正でこれらを悪化させないこと"
    )


def resolve_prediction(project_path: str, target_file: str,
                       description_keyword: str):
    """リスクを解決済みにマークする（app.pyのボタンから呼ぶ）"""
    store = _load_json(project_path, PREDICTION_FILE, {"predictions": {}})
    for key in store["predictions"]:
        if os.path.basename(key) == os.path.basename(target_file):
            for r in store["predictions"][key]:
                if description_keyword.lower() in r.get("description", "").lower():
                    r["resolved"] = True
    _save_json(project_path, PREDICTION_FILE, store)


def get_all_predictions(project_path: str) -> list:
    """app.py用: 全ファイルの未解決リスク一覧"""
    store = _load_json(project_path, PREDICTION_FILE, {"predictions": {}})
    result = []
    for file_path, risks in store["predictions"].items():
        for r in risks:
            if not r.get("resolved"):
                result.append({
                    "file":        os.path.basename(file_path),
                    "description": r.get("description", ""),
                    "trigger":     r.get("trigger", ""),
                    "severity":    r.get("severity", "low"),
                    "suggestion":  r.get("suggestion", ""),
                    "predicted_at": r.get("predicted_at", "")[:16].replace("T", " "),
                })
    # severity順でソート
    order = {"high": 0, "medium": 1, "low": 2}
    result.sort(key=lambda x: order.get(x["severity"], 2))
    return result


def get_prediction_stats(project_path: str) -> dict:
    store = _load_json(project_path, PREDICTION_FILE, {"predictions": {}})
    total = resolved = high = 0
    for risks in store["predictions"].values():
        for r in risks:
            total += 1
            if r.get("resolved"):
                resolved += 1
            if r.get("severity") == "high":
                high += 1
    return {
        "total":    total,
        "resolved": resolved,
        "open":     total - resolved,
        "high":     high,
    }


# ============================================================
# PARALLEL CACHE — 選ばなかった案も全て記憶する
# ============================================================

def record_parallel_result(project_path: str,
                           task_desc: str,
                           file_name: str,
                           candidates: dict,
                           chosen_path: str,
                           reason: str = ""):
    """
    _branch_and_critique()の結果を全候補ごと記録する。
    engine.pyのBranching完了後に呼ぶ。

    candidates = {
        "A": {"code": "...", "score": {"score": 72, ...}, "sandbox_ok": True},
        "B": {"code": "...", "score": {"score": 45, ...}, "sandbox_ok": False},
        "C": {"code": "...", "score": {"score": 80, ...}, "sandbox_ok": True},
    }
    chosen_path = "C"
    """
    cache = _load_json(project_path, PARALLEL_FILE, {"records": []})

    record = {
        "timestamp":   datetime.now().isoformat(),
        "task":        task_desc[:200],
        "file":        file_name,
        "chosen":      chosen_path,
        "reason":      reason,
        "candidates":  {},
    }

    for path_name, cand in candidates.items():
        score_val = cand.get("score", {})
        if isinstance(score_val, dict):
            sc = score_val.get("score", 0)
            fb = score_val.get("feedback", "")
        else:
            sc = 0
            fb = ""

        record["candidates"][path_name] = {
            "score":      sc,
            "feedback":   fb[:200],
            "sandbox_ok": cand.get("sandbox_ok", True),
            "chosen":     path_name == chosen_path,
            # コードは先頭300文字だけ保存（容量節約）
            "code_hint":  cand.get("code", "")[:300],
        }

    cache["records"].append(record)

    # 上限管理
    if len(cache["records"]) > MAX_PARALLEL:
        cache["records"] = cache["records"][-MAX_PARALLEL:]

    _save_json(project_path, PARALLEL_FILE, cache)
    print(f"[parallel_cache] 並列結果記録: {chosen_path}採用 / {file_name}")


def get_parallel_insight(project_path: str, task_desc: str) -> str:
    """
    タスクに関連する過去の並列シミュ結果から知見を返す。
    engine.pyのBranching前に注入 → 「前回Path Bは失敗した」を活かす。
    """
    cache  = _load_json(project_path, PARALLEL_FILE, {"records": []})
    records = cache.get("records", [])
    if not records:
        return ""

    task_words = set(re.findall(r"\w+", task_desc.lower()))
    task_words -= {"する", "した", "して", "ください", "追加",
                   "実装", "修正", "変更", "this", "from"}

    # 関連レコードを検索
    scored = []
    for rec in records:
        text  = rec.get("task", "")
        words = set(re.findall(r"\w+", text.lower()))
        sim   = len(task_words & words)
        if sim >= 2:
            scored.append((sim, rec))

    if not scored:
        return ""

    scored.sort(key=lambda x: -x[0])
    top = scored[:2]

    lines = []
    for _, rec in top:
        chosen = rec.get("chosen", "?")
        for pname, cand in rec.get("candidates", {}).items():
            if pname == chosen:
                continue  # 採用案はスキップ
            reason = "Sandbox失敗" if not cand.get("sandbox_ok") else f"スコア{cand['score']}"
            lines.append(
                f"  ⚡ 類似タスク「{rec['task'][:60]}」\n"
                f"    Path{pname}は{reason}で不採用 → Path{chosen}が正解だった\n"
                f"    理由: {cand.get('feedback','')[:80]}"
            )

    if not lines:
        return ""

    return (
        "\n\n【⚡ 並列シミュ知見（過去の検討から）】\n"
        + "\n".join(lines[:3])
        + "\n→ 同じ失敗を繰り返さないこと"
    )


def get_parallel_history(project_path: str, n: int = 20) -> list:
    """app.py用: 並列シミュ履歴"""
    cache   = _load_json(project_path, PARALLEL_FILE, {"records": []})
    records = cache.get("records", [])
    result  = []
    for rec in reversed(records[-n:]):
        candidates = rec.get("candidates", {})
        chosen     = rec.get("chosen", "?")
        result.append({
            "timestamp": rec.get("timestamp", "")[:16].replace("T", " "),
            "task":      rec.get("task", "")[:60],
            "file":      rec.get("file", ""),
            "chosen":    chosen,
            "chosen_score": candidates.get(chosen, {}).get("score", 0),
            "all_scores": {
                k: v.get("score", 0)
                for k, v in candidates.items()
            },
            "rejected_reasons": {
                k: ("Sandbox失敗" if not v.get("sandbox_ok")
                    else f"スコア{v.get('score',0)}")
                for k, v in candidates.items()
                if k != chosen
            },
        })
    return result


def get_parallel_stats(project_path: str) -> dict:
    """統計情報"""
    cache   = _load_json(project_path, PARALLEL_FILE, {"records": []})
    records = cache.get("records", [])
    path_wins = {"A": 0, "B": 0, "C": 0}
    for rec in records:
        chosen = rec.get("chosen", "")
        if chosen in path_wins:
            path_wins[chosen] += 1
    total = len(records)
    return {
        "total_simulations": total,
        "path_wins":         path_wins,
        "most_reliable":     max(path_wins, key=path_wins.get) if total else "?",
    }
