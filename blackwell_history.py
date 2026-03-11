"""
Blackwell Dev-OS — blackwell_history.py v1.0  (Phase 2)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 2 が解決する2つの問題:

  問題A: 「修正したら他が壊れる」
    → contract_store: ファイル間の「約束」を記録
      「Player.gdのtake_damage(hp)を変えたら
       Enemy.gd・HUD.gd・GameManager.gdも壊れる」
      を事前に警告する

  問題B: 「同じミスを繰り返す」
    → timeline: 全開発履歴を完全記録
      成功パターン・失敗パターン・エラーの根本原因を
      蓄積して次回に活かす

【保存先】
  {project_path}/blackwell_brain/contract_store.json  ← API契約
  {project_path}/blackwell_brain/timeline.json        ← 完全履歴

【公開API】
  # 契約
  register_contract(path, provider_file, func_sig, consumers)
  get_contract_warning(path, target_file)   → str  ← engine.pyへ
  update_contract_consumers(path, file, src)

  # 履歴
  record_event(path, event)                 → None
  get_lessons(path, task_desc, k)           → str  ← engine.pyへ
  get_failure_warning(path, task_desc)      → str  ← engine.pyへ
  get_timeline_summary(path, n)             → list ← app.pyへ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import os
import re
from datetime import datetime
from typing import Optional


BRAIN_DIR       = "blackwell_brain"
CONTRACT_FILE   = "contract_store.json"
TIMELINE_FILE   = "timeline.json"

MAX_TIMELINE    = 500   # 最大保持イベント数
MAX_LESSONS     = 200   # 教訓の最大保持数


# ============================================================
# 共通: ファイルI/O
# ============================================================

def _brain_dir(project_path: str) -> str:
    d = os.path.join(project_path, BRAIN_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _load_json(project_path: str, filename: str, default) -> dict:
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
# CONTRACT STORE — ファイル間のAPI約束を記録
# ============================================================
#
# 「契約」= あるファイルが公開している関数シグネチャと、
#           それを使っているファイルのリスト。
#
# 例:
#   contract_store["Player.gd"]["take_damage"] = {
#     "signature": "take_damage(amount: int) -> void",
#     "consumers": ["Enemy.gd", "HUD.gd", "GameManager.gd"],
#     "registered_at": "2026-03-11T...",
#     "description": "プレイヤーにダメージを与える。HPが0になるとdie()を呼ぶ"
#   }
# ============================================================

def register_contract(project_path: str,
                      provider_file: str,
                      func_name: str,
                      signature: str,
                      consumers: list,
                      description: str = ""):
    """
    ファイルが公開する関数の「契約」を登録する。
    engine.pyがファイルを生成したあとに自動呼び出し。
    """
    store = _load_json(project_path, CONTRACT_FILE, {})
    if provider_file not in store:
        store[provider_file] = {}

    existing = store[provider_file].get(func_name, {})
    # 既存のconsumersとマージ（重複排除）
    merged_consumers = list(set(existing.get("consumers", []) + consumers))

    store[provider_file][func_name] = {
        "signature":     signature,
        "consumers":     merged_consumers,
        "registered_at": datetime.now().isoformat(),
        "description":   description or existing.get("description", ""),
    }
    _save_json(project_path, CONTRACT_FILE, store)


def update_contract_consumers(project_path: str,
                               consumer_file: str,
                               source_code: str):
    """
    consumer_fileのソースコードを解析して、
    他ファイルの関数を呼んでいる箇所を検出 → 契約に登録。
    engine.pyのファイル書き込み後に自動呼び出し。
    """
    store = _load_json(project_path, CONTRACT_FILE, {})

    # 全providerの関数名をフラットに持つ
    # {func_name: provider_file}
    all_funcs = {}
    for provider, funcs in store.items():
        for fname in funcs:
            all_funcs[fname] = provider

    # ソースコードから関数呼び出しを検出
    called = set(re.findall(r"\b(\w+)\s*\(", source_code))
    updated = False

    for func_name in called:
        if func_name in all_funcs:
            provider = all_funcs[func_name]
            if provider == consumer_file:
                continue  # 自己参照は無視
            entry = store[provider][func_name]
            if consumer_file not in entry["consumers"]:
                entry["consumers"].append(consumer_file)
                updated = True

    if updated:
        _save_json(project_path, CONTRACT_FILE, store)
        print(f"[blackwell_history] 契約更新: {consumer_file}の依存関係を記録")


def auto_register_contracts(project_path: str,
                             file_rel_path: str,
                             source_code: str,
                             language: str = ""):
    """
    ファイルの公開関数を全て契約として登録する。
    意図記録と同様に、ファイル生成直後に呼ぶ。
    """
    store = _load_json(project_path, CONTRACT_FILE, {})
    if file_rel_path not in store:
        store[file_rel_path] = {}

    # Python
    if language == "python" or file_rel_path.endswith(".py"):
        for m in re.finditer(
            r"^def\s+(\w+)\s*\(([^)]*)\)",
            source_code, re.MULTILINE
        ):
            fname = m.group(1)
            if fname.startswith("_"):
                continue  # プライベートは除外
            args  = m.group(2).strip()
            sig   = f"{fname}({args})"
            if fname not in store[file_rel_path]:
                store[file_rel_path][fname] = {
                    "signature":     sig,
                    "consumers":     [],
                    "registered_at": datetime.now().isoformat(),
                    "description":   "",
                }

    # GDScript
    elif language == "gdscript" or file_rel_path.endswith(".gd"):
        for m in re.finditer(
            r"^(?:static\s+)?func\s+(\w+)\s*\(([^)]*)\)",
            source_code, re.MULTILINE
        ):
            fname = m.group(1)
            if fname.startswith("_") and fname not in (
                "_ready", "_process", "_physics_process",
                "_input", "_unhandled_input"
            ):
                continue
            args = m.group(2).strip()
            sig  = f"{fname}({args})"
            if fname not in store[file_rel_path]:
                store[file_rel_path][fname] = {
                    "signature":     sig,
                    "consumers":     [],
                    "registered_at": datetime.now().isoformat(),
                    "description":   "",
                }

    _save_json(project_path, CONTRACT_FILE, store)

    # 他ファイルがこのファイルの関数を使っているか検索
    update_contract_consumers(project_path, file_rel_path, source_code)


def get_contract_warning(project_path: str, target_file: str) -> str:
    """
    target_fileを修正するときの「影響範囲」警告を返す。
    engine.pyのprocess_task冒頭で地図コンテキストと一緒に注入する。
    """
    store = _load_json(project_path, CONTRACT_FILE, {})

    # target_fileに一致するエントリを探す
    match_key = None
    for key in store:
        if (os.path.basename(key) == os.path.basename(target_file)
                or key == target_file):
            match_key = key
            break

    if not match_key:
        return ""

    funcs = store[match_key]
    if not funcs:
        return ""

    warnings = []
    for fname, info in funcs.items():
        consumers = info.get("consumers", [])
        if consumers:
            consumer_names = [os.path.basename(c) for c in consumers]
            warnings.append(
                f"  {info['signature']} "
                f"← {', '.join(consumer_names)} が依存"
            )

    if not warnings:
        return ""

    return (
        "\n\n【⚠️ 契約警告: このファイルを修正すると以下が壊れる可能性】\n"
        + "\n".join(warnings[:10])
        + "\n→ シグネチャ変更時は依存ファイルも同時に修正すること"
    )


def get_all_contracts_summary(project_path: str) -> list:
    """app.py用: 全契約の概要リストを返す"""
    store = _load_json(project_path, CONTRACT_FILE, {})
    result = []
    for provider, funcs in store.items():
        for fname, info in funcs.items():
            consumers = info.get("consumers", [])
            if consumers:
                result.append({
                    "provider":  os.path.basename(provider),
                    "function":  fname,
                    "signature": info.get("signature", fname),
                    "consumers": [os.path.basename(c) for c in consumers],
                })
    return result


# ============================================================
# TIMELINE — 全開発履歴の完全記録
# ============================================================
#
# イベントタイプ:
#   "task_success"  : タスク成功
#   "task_failure"  : タスク失敗
#   "lesson"        : 教訓（成功/失敗から抽出）
#   "error"         : エラー詳細
#   "milestone"     : 節目（ユーザーが手動で記録）
# ============================================================

def record_event(project_path: str, event: dict):
    """
    開発イベントをタイムラインに追記する。
    engine.pyから自動呼び出し。

    event = {
        "type":      "task_success" | "task_failure" | "lesson" | "error",
        "file":      "Player.gd",
        "task":      "タスクの説明",
        "detail":    "詳細（エラーメッセージ・成功理由など）",
        "score":     75,          # オプション
        "tags":      ["jump", "collision"],  # オプション
    }
    """
    timeline = _load_json(project_path, TIMELINE_FILE,
                          {"events": [], "lessons": []})

    event["timestamp"] = datetime.now().isoformat()

    # 教訓はlessonsにも追加（高速検索用）
    if event["type"] in ("task_success", "task_failure", "lesson"):
        lesson = {
            "type":      event["type"],
            "task":      event.get("task", "")[:200],
            "detail":    event.get("detail", "")[:400],
            "file":      event.get("file", ""),
            "score":     event.get("score", 0),
            "tags":      event.get("tags", []),
            "timestamp": event["timestamp"],
        }
        timeline["lessons"].append(lesson)
        # 上限管理
        if len(timeline["lessons"]) > MAX_LESSONS:
            timeline["lessons"] = timeline["lessons"][-MAX_LESSONS:]

    # 全イベントをeventsに追加
    timeline["events"].append(event)
    if len(timeline["events"]) > MAX_TIMELINE:
        timeline["events"] = timeline["events"][-MAX_TIMELINE:]

    _save_json(project_path, TIMELINE_FILE, timeline)


def record_task_result(project_path: str,
                       file_name: str,
                       task_desc: str,
                       code: str,
                       score: int,
                       success: bool,
                       feedback: str = "",
                       error_msg: str = ""):
    """
    process_taskの完了後に呼ぶ。成功/失敗を記録する。
    engine.pyの_extract_lessonを置き換える。
    """
    if score >= 75 and success:
        event_type = "task_success"
        detail = (
            f"スコア: {score}/100\n"
            f"良かった点: {feedback}\n"
            f"再利用パターン:\n{code[:400]}"
        )
        tags = _extract_tags(task_desc + " " + code[:200])

    elif score < 60 or not success:
        event_type = "task_failure"
        detail = (
            f"スコア: {score}/100\n"
            f"問題点: {feedback}\n"
            f"エラー: {error_msg[:200]}\n"
            f"→ 次回このアプローチは避ける"
        )
        tags = _extract_tags(task_desc) + ["failure"]

    else:
        return  # 中程度は記録しない

    record_event(project_path, {
        "type":   event_type,
        "file":   file_name,
        "task":   task_desc[:200],
        "detail": detail,
        "score":  score,
        "tags":   tags,
    })


def record_error(project_path: str,
                 file_name: str,
                 task_desc: str,
                 error_msg: str,
                 failed_code: str = ""):
    """
    エラー発生時に記録する。engine.pyの_save_negative_cacheを置き換える。
    """
    error_type, abstract = _classify_error(error_msg)
    record_event(project_path, {
        "type":       "error",
        "file":       file_name,
        "task":       task_desc[:200],
        "detail":     abstract,
        "error_type": error_type,
        "raw_error":  error_msg[:300],
        "snippet":    failed_code[:300],
        "tags":       [error_type, "error"],
    })


def _classify_error(error_msg: str) -> tuple:
    """エラーを分類して (type, abstract) を返す"""
    e = error_msg.lower()
    if "syntaxerror" in e:
        return "syntax", "構文エラー: インデント・括弧・コロンのミス"
    if "importerror" in e or "modulenotfounderror" in e:
        m = re.search(r"No module named '([^']+)'", error_msg)
        mod = m.group(1) if m else "不明"
        return "import", f"ImportError: '{mod}' が見つからない → pip install が必要"
    if "attributeerror" in e:
        return "attribute", "AttributeError: 存在しないメソッド・属性へのアクセス"
    if "typeerror" in e:
        return "type", "TypeError: 型不一致・引数の数が違う"
    if "keyerror" in e:
        return "key", "KeyError: 存在しないキーへのアクセス → .get()を使う"
    if "filenotfounderror" in e:
        return "file", "FileNotFoundError: パスが存在しない → makedirs()が必要"
    if "timeout" in e:
        return "timeout", "タイムアウト: 無限ループ・重い処理"
    if "valueerror" in e:
        return "value", "ValueError: 不正な値 → バリデーションが必要"
    if "indentationerror" in e:
        return "indent", "IndentationError: インデントが崩れている"
    return "runtime", f"RuntimeError: {error_msg[:120]}"


def _extract_tags(text: str) -> list:
    """テキストからタグを自動抽出"""
    keywords = {
        "jump": ["jump", "ジャンプ"],
        "collision": ["collision", "衝突", "当たり判定"],
        "damage": ["damage", "ダメージ", "hp", "health"],
        "movement": ["move", "移動", "velocity", "speed"],
        "animation": ["animation", "アニメーション", "sprite"],
        "save": ["save", "load", "セーブ", "ロード"],
        "enemy": ["enemy", "敵", "モンスター", "ai"],
        "item": ["item", "アイテム", "pickup"],
        "ui": ["ui", "hud", "menu", "画面"],
        "dungeon": ["dungeon", "ダンジョン", "map", "マップ"],
    }
    text_lower = text.lower()
    return [tag for tag, words in keywords.items()
            if any(w in text_lower for w in words)]


# ============================================================
# 教訓・警告の取得（engine.pyから呼ぶ）
# ============================================================

def get_lessons(project_path: str, task_desc: str, k: int = 3) -> str:
    """
    タスクに関連する過去の教訓を返す。
    engine.pyの_retrieve_lessons()を置き換える。
    """
    timeline = _load_json(project_path, TIMELINE_FILE,
                          {"events": [], "lessons": []})
    lessons = timeline.get("lessons", [])
    if not lessons:
        return ""

    # タスク説明との類似度でスコアリング
    task_words = set(re.findall(r"\w+", task_desc.lower()))
    task_words -= {"する", "した", "して", "ください", "追加", "実装",
                   "修正", "変更", "this", "that", "with", "from"}

    scored = []
    for lesson in lessons:
        text  = lesson.get("task", "") + " " + lesson.get("detail", "")
        words = set(re.findall(r"\w+", text.lower()))
        score = len(task_words & words)
        # 成功パターンは優先
        if lesson.get("type") == "task_success":
            score += 1
        if score > 0:
            scored.append((score, lesson))

    scored.sort(key=lambda x: -x[0])
    top = [l for _, l in scored[:k]]

    if not top:
        return ""

    lines = []
    for l in top:
        icon = "✅" if l["type"] == "task_success" else "❌"
        lines.append(
            f"{icon} [{l.get('file','?')}] {l.get('task','')[:80]}\n"
            f"   → {l.get('detail','')[:120]}"
        )

    return "\n\n【📖 過去の教訓（失敗しないために）】\n" + "\n".join(lines)


def get_failure_warning(project_path: str, task_desc: str) -> str:
    """
    タスクに関連する過去の失敗・エラーパターンを警告として返す。
    engine.pyの_get_negative_cache_warning()を置き換える。
    """
    timeline = _load_json(project_path, TIMELINE_FILE,
                          {"events": [], "lessons": []})
    lessons = timeline.get("lessons", [])

    task_words = set(re.findall(r"\w+", task_desc.lower()))

    failures = []
    for lesson in lessons:
        if lesson.get("type") not in ("task_failure", "error"):
            continue
        text  = lesson.get("task", "") + " " + lesson.get("detail", "")
        words = set(re.findall(r"\w+", text.lower()))
        if len(task_words & words) >= 2:
            failures.append(lesson)

    if not failures:
        return ""

    # 直近3件
    lines = []
    for f in failures[-3:]:
        lines.append(f"  ⛔ {f.get('detail','')[:120]}")

    return "\n\n【⚠️ 過去の失敗パターン（必ず避けること）】\n" + "\n".join(lines)


# ============================================================
# app.py用: 表示データ
# ============================================================

def get_timeline_summary(project_path: str, n: int = 20) -> list:
    """直近nイベントをapp.py表示用に返す"""
    timeline = _load_json(project_path, TIMELINE_FILE,
                          {"events": [], "lessons": []})
    events = timeline.get("events", [])
    result = []
    for ev in reversed(events[-n:]):
        icon = {
            "task_success": "✅",
            "task_failure": "❌",
            "error":        "🔴",
            "lesson":       "📖",
            "milestone":    "🏆",
        }.get(ev.get("type", ""), "📌")
        result.append({
            "icon":      icon,
            "type":      ev.get("type", ""),
            "file":      ev.get("file", ""),
            "task":      ev.get("task", "")[:60],
            "detail":    ev.get("detail", "")[:80],
            "score":     ev.get("score", ""),
            "timestamp": ev.get("timestamp", "")[:16].replace("T", " "),
        })
    return result


def get_stats(project_path: str) -> dict:
    """統計情報を返す（app.py用）"""
    timeline = _load_json(project_path, TIMELINE_FILE,
                          {"events": [], "lessons": []})
    events  = timeline.get("events", [])
    lessons = timeline.get("lessons", [])

    success = sum(1 for e in lessons if e.get("type") == "task_success")
    failure = sum(1 for e in lessons if e.get("type") == "task_failure")
    errors  = sum(1 for e in events  if e.get("type") == "error")
    scores  = [e.get("score", 0) for e in lessons if e.get("score")]
    avg_score = sum(scores) // len(scores) if scores else 0

    contracts = _load_json(project_path, CONTRACT_FILE, {})
    total_contracts = sum(len(v) for v in contracts.values())

    return {
        "total_events":     len(events),
        "success_count":    success,
        "failure_count":    failure,
        "error_count":      errors,
        "avg_score":        avg_score,
        "total_contracts":  total_contracts,
        "success_rate":     int(success / (success + failure) * 100)
                            if (success + failure) > 0 else 0,
    }


def add_milestone(project_path: str, title: str, note: str = ""):
    """節目を手動記録（app.pyのボタンから呼ぶ）"""
    record_event(project_path, {
        "type":   "milestone",
        "file":   "",
        "task":   title,
        "detail": note,
        "tags":   ["milestone"],
    })
