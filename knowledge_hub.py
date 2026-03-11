"""
Blackwell Dev-OS — knowledge_hub.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⑦ マルチプロジェクト知識共有

【何をするか】
  今まで: プロジェクトAで学んだことはプロジェクトAだけのもの
           プロジェクトBを始めると0からやり直し

  After:  「前のゲームでこのパターンは失敗した」
           「ローグライクを3本作った。ローグライクは得意」
           「シェーダーは毎回手こずる。慎重にやる」
           が全プロジェクトをまたいで自動的に蓄積される

【仕組み】
  各プロジェクトのblackwell_brainから知識を「エクスポート」して
  共有ナレッジベース（~/.blackwell/knowledge_hub.json）に統合する。

  新プロジェクト開始時に「インポート」して
  過去の知恵をシステムプロンプトに注入する。

【共有される知識の種類】
  ✅ 成功パターン  — 「この構造でローグライクが動いた」
  ✅ 失敗パターン  — 「グローバル変数でバグった」
  ✅ 技術スニペット — 「Godotでインベントリを実装する定番コード」
  ✅ ゲームジャンル別の知見 — 「横スクロールの当たり判定はこれが安定」
  ✅ エージェント信頼スコア — 「Criticは信頼度90」

【保存先】
  共有ハブ: ~/.blackwell/knowledge_hub.json  ← 全プロジェクト共通
  インデックス: ~/.blackwell/projects.json   ← 登録プロジェクト一覧

【公開API】
  export_project(project_path, project_name) → int  件数
  import_knowledge(project_path, topic)      → str  注入テキスト
  register_project(path, name, genre)        → None
  get_hub_stats()                            → dict
  get_cross_lessons(topic, n)                → list
  search_knowledge(query)                    → list
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path


# 共有ハブの保存先（ユーザーホームディレクトリ）
HUB_DIR      = os.path.join(Path.home(), ".blackwell")
HUB_FILE     = os.path.join(HUB_DIR, "knowledge_hub.json")
PROJECTS_FILE = os.path.join(HUB_DIR, "projects.json")

MAX_ENTRIES_PER_TYPE = 200


# ============================================================
# ユーティリティ
# ============================================================

def _ensure_hub_dir():
    os.makedirs(HUB_DIR, exist_ok=True)


def _load_hub() -> dict:
    _ensure_hub_dir()
    if not os.path.exists(HUB_FILE):
        return _empty_hub()
    try:
        with open(HUB_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _empty_hub()


def _save_hub(data: dict):
    _ensure_hub_dir()
    with open(HUB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_projects() -> dict:
    _ensure_hub_dir()
    if not os.path.exists(PROJECTS_FILE):
        return {"projects": []}
    try:
        with open(PROJECTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"projects": []}


def _save_projects(data: dict):
    _ensure_hub_dir()
    with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _empty_hub() -> dict:
    return {
        "version":       1,
        "last_updated":  "",
        "successes":     [],   # 成功パターン
        "failures":      [],   # 失敗パターン
        "snippets":      [],   # 技術スニペット
        "genre_insights": {},  # ジャンル別知見
        "agent_trust":   {},   # エージェント信頼スコア（全プロジェクト平均）
        "lessons":       [],   # 汎用教訓
    }


def _now() -> str:
    return datetime.now().isoformat()[:16]


def _brain_path(project_path: str) -> str:
    return os.path.join(project_path, "blackwell_brain")


def _load_brain(project_path: str, filename: str) -> dict:
    path = os.path.join(_brain_path(project_path), filename)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ============================================================
# プロジェクト登録
# ============================================================

def register_project(project_path: str,
                     project_name: str = "",
                     genre: str = "") -> None:
    """プロジェクトをハブに登録する"""
    projects = _load_projects()
    abs_path = os.path.abspath(project_path)

    # 既存チェック
    for p in projects["projects"]:
        if p["path"] == abs_path:
            p["last_active"] = _now()
            _save_projects(projects)
            return

    name = project_name or os.path.basename(abs_path)
    projects["projects"].append({
        "path":        abs_path,
        "name":        name,
        "genre":       genre,
        "registered":  _now(),
        "last_active": _now(),
        "exported_at": "",
    })
    _save_projects(projects)
    print(f"[knowledge_hub] プロジェクト登録: {name}")


# ============================================================
# エクスポート: プロジェクト → ハブ
# ============================================================

def export_project(project_path: str,
                   project_name: str = "") -> int:
    """
    プロジェクトの blackwell_brain から知識をハブに統合する。
    プロジェクト完了時・定期的に呼ぶ。

    Returns: 追加したエントリ数
    """
    hub  = _load_hub()
    name = project_name or os.path.basename(os.path.abspath(project_path))
    added = 0

    print(f"[knowledge_hub] エクスポート開始: {name}")

    # ── timeline.jsonから成功・失敗パターン ────────────────
    timeline = _load_brain(project_path, "timeline.json")
    events   = timeline.get("events", [])
    lessons  = timeline.get("lessons", [])

    for event in events:
        etype = event.get("type", "")
        score = event.get("score", 0)
        task  = event.get("task", "")[:80]
        tags  = event.get("tags", [])

        if not task:
            continue

        entry = {
            "source":    name,
            "task":      task,
            "tags":      tags,
            "added_at":  _now(),
        }

        if etype == "task_success" and score >= 75:
            entry["score"] = score
            if not _is_duplicate(task, [s["task"] for s in hub["successes"]]):
                hub["successes"].append(entry)
                added += 1

        elif etype == "task_failure":
            detail = event.get("detail", "")[:100]
            entry["detail"] = detail
            if not _is_duplicate(task, [f["task"] for f in hub["failures"]]):
                hub["failures"].append(entry)
                added += 1

    # 上限管理
    hub["successes"] = hub["successes"][-MAX_ENTRIES_PER_TYPE:]
    hub["failures"]  = hub["failures"][-MAX_ENTRIES_PER_TYPE:]

    # ── lessons（教訓）────────────────────────────────────
    for lesson in lessons:
        text = lesson.get("lesson", "") if isinstance(lesson, dict) \
               else str(lesson)
        text = text[:150]
        if text and not _is_duplicate(text, [l.get("text","") for l in hub["lessons"]]):
            hub["lessons"].append({
                "text":     text,
                "source":   name,
                "added_at": _now(),
            })
            added += 1
    hub["lessons"] = hub["lessons"][-MAX_ENTRIES_PER_TYPE:]

    # ── evolved_prompts.jsonから改善パターン ───────────────
    evolved = _load_brain(project_path, "evolved_prompts.json")
    for addition in evolved.get("additions", []):
        text    = addition.get("text", "")
        pattern = addition.get("pattern", "")
        if text and addition.get("priority") == "high":
            kws = addition.get("task_keywords", [])
            entry = {
                "text":     text,
                "pattern":  pattern,
                "keywords": kws,
                "source":   name,
                "added_at": _now(),
            }
            if not _is_duplicate(text, [s.get("text","") for s in hub["snippets"]]):
                hub["snippets"].append(entry)
                added += 1
    hub["snippets"] = hub["snippets"][-MAX_ENTRIES_PER_TYPE:]

    # ── agent_sessions.jsonからエージェント信頼スコア ───────
    agent_sessions = _load_brain(project_path, "agent_sessions.json")
    for session in agent_sessions.get("sessions", []):
        score  = session.get("score", 0)
        agents = session.get("agents", [])
        for agent in agents:
            existing = hub["agent_trust"].get(agent, {"scores": [], "avg": 0})
            existing["scores"].append(score)
            existing["scores"] = existing["scores"][-50:]
            scores = existing["scores"]
            existing["avg"] = int(sum(scores) / len(scores))
            hub["agent_trust"][agent] = existing

    # ── ジャンル別知見（game_insightsから） ────────────────
    game_insights = _load_brain(project_path, "game_insights.json")
    ref_insights  = game_insights.get("reference_insights", [])
    for ri in ref_insights:
        genre = _detect_genre(project_path)
        if genre:
            if genre not in hub["genre_insights"]:
                hub["genre_insights"][genre] = []
            text = ri.get("how_to_apply", "")
            if text and not _is_duplicate(
                text, [g.get("text","") for g in hub["genre_insights"][genre]]
            ):
                hub["genre_insights"][genre].append({
                    "text":     text,
                    "element":  ri.get("element",""),
                    "source":   name,
                    "added_at": _now(),
                })
        hub["genre_insights"][genre] = hub["genre_insights"].get(genre, [])[-50:]

    hub["version"]      += 1
    hub["last_updated"]  = _now()
    _save_hub(hub)

    # プロジェクトのexport_atを更新
    projects = _load_projects()
    for p in projects["projects"]:
        if os.path.abspath(project_path) == p["path"]:
            p["exported_at"] = _now()
    _save_projects(projects)

    print(f"[knowledge_hub] エクスポート完了: {added}件追加 / "
          f"合計: 成功{len(hub['successes'])} 失敗{len(hub['failures'])} "
          f"教訓{len(hub['lessons'])}")
    return added


# ============================================================
# インポート: ハブ → 現在のプロジェクト
# ============================================================

def import_knowledge(project_path: str,
                     topic: str = "",
                     n: int = 5) -> str:
    """
    ハブから現在のプロジェクトに関連する知識を取得する。
    engine.pyのシステムプロンプト注入に使う。

    Returns: プロンプトに追加するテキスト
    """
    hub  = _load_hub()
    name = os.path.basename(os.path.abspath(project_path))
    topic_lower = topic.lower()

    parts = []

    # ── 関連する成功パターン ──────────────────────────────
    related_successes = _find_related(
        topic_lower, hub["successes"],
        key_fn=lambda x: x.get("task","") + " ".join(x.get("tags",[])),
        n=3
    )
    if related_successes:
        parts.append("【過去の成功パターン（他プロジェクト）】")
        for s in related_successes:
            parts.append(f"  ✅ [{s['source']}] {s['task']}")

    # ── 関連する失敗パターン ──────────────────────────────
    related_failures = _find_related(
        topic_lower, hub["failures"],
        key_fn=lambda x: x.get("task","") + x.get("detail",""),
        n=3
    )
    if related_failures:
        parts.append("【過去の失敗パターン（他プロジェクト）】")
        for f in related_failures:
            parts.append(f"  ❌ [{f['source']}] {f['task']}"
                         + (f" → {f['detail']}" if f.get('detail') else ""))

    # ── 関連する教訓 ──────────────────────────────────────
    related_lessons = _find_related(
        topic_lower, hub["lessons"],
        key_fn=lambda x: x.get("text",""),
        n=3
    )
    if related_lessons:
        parts.append("【他プロジェクトからの教訓】")
        for l in related_lessons:
            parts.append(f"  📖 [{l['source']}] {l['text']}")

    # ── ジャンル別知見 ────────────────────────────────────
    genre = _detect_genre(project_path)
    if genre and genre in hub["genre_insights"]:
        genre_tips = hub["genre_insights"][genre][:2]
        if genre_tips:
            parts.append(f"【{genre}ジャンルの知見】")
            for tip in genre_tips:
                parts.append(f"  🎮 {tip.get('text','')}")

    # ── プロンプト改善（高優先度） ────────────────────────
    related_snippets = _find_related(
        topic_lower, hub["snippets"],
        key_fn=lambda x: x.get("text","") + " ".join(x.get("keywords",[])),
        n=2
    )
    if related_snippets:
        parts.append("【他プロジェクトで有効だったプロンプト改善】")
        for s in related_snippets:
            parts.append(f"  🧬 {s['text']}")

    if not parts:
        return ""

    return "\n".join(["【🌐 マルチプロジェクト知識ベース】"] + parts)


def get_cross_lessons(topic: str = "", n: int = 5) -> list:
    """トピックに関連する教訓を返す（app.py表示用）"""
    hub = _load_hub()
    topic_lower = topic.lower()
    results = []

    for category, items in [
        ("success", hub["successes"]),
        ("failure", hub["failures"]),
        ("lesson",  hub["lessons"]),
    ]:
        for item in items:
            text = item.get("task", item.get("text", ""))
            if not topic_lower or topic_lower in text.lower():
                results.append({
                    "category": category,
                    "text":     text[:100],
                    "source":   item.get("source", ""),
                    "added_at": item.get("added_at", ""),
                })

    results.sort(key=lambda x: x["added_at"], reverse=True)
    return results[:n]


def search_knowledge(query: str, n: int = 10) -> list:
    """キーワード検索（app.pyの検索ボックス用）"""
    hub = _load_hub()
    q   = query.lower()
    results = []

    for category, items, text_fn in [
        ("✅ 成功", hub["successes"], lambda x: x.get("task","")),
        ("❌ 失敗", hub["failures"],  lambda x: x.get("task","") + x.get("detail","")),
        ("📖 教訓", hub["lessons"],   lambda x: x.get("text","")),
        ("🧬 改善", hub["snippets"],  lambda x: x.get("text","")),
    ]:
        for item in items:
            text = text_fn(item)
            if q in text.lower():
                results.append({
                    "category": category,
                    "text":     text[:120],
                    "source":   item.get("source",""),
                })
    return results[:n]


# ============================================================
# 統計
# ============================================================

def get_hub_stats() -> dict:
    hub      = _load_hub()
    projects = _load_projects()
    proj_list = projects.get("projects", [])

    genre_counts = {g: len(v) for g, v in hub["genre_insights"].items()}

    agent_trust_summary = {
        a: v.get("avg", 0)
        for a, v in hub["agent_trust"].items()
    }

    return {
        "hub_path":          HUB_FILE,
        "version":           hub.get("version", 0),
        "last_updated":      hub.get("last_updated", ""),
        "total_projects":    len(proj_list),
        "projects":          [
            {
                "name":        p["name"],
                "path":        p["path"],
                "genre":       p.get("genre",""),
                "last_active": p.get("last_active",""),
                "exported_at": p.get("exported_at",""),
            }
            for p in proj_list
        ],
        "successes":         len(hub["successes"]),
        "failures":          len(hub["failures"]),
        "lessons":           len(hub["lessons"]),
        "snippets":          len(hub["snippets"]),
        "genre_insights":    genre_counts,
        "agent_trust":       agent_trust_summary,
    }


# ============================================================
# ヘルパー
# ============================================================

def _find_related(topic: str, items: list,
                   key_fn, n: int) -> list:
    """トピックに関連するアイテムを返す"""
    if not topic:
        return items[-n:]

    scored = []
    words  = set(re.findall(r"\w+", topic))
    for item in items:
        text       = key_fn(item).lower()
        item_words = set(re.findall(r"\w+", text))
        overlap    = len(words & item_words)
        if overlap > 0:
            scored.append((overlap, item))

    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:n]]


def _is_duplicate(text: str, existing: list,
                   threshold: float = 0.7) -> bool:
    """簡易重複チェック"""
    words_new = set(re.findall(r"\w+", text.lower()))
    for ex in existing[-20:]:  # 直近20件だけチェック
        words_ex = set(re.findall(r"\w+", ex.lower()))
        if not words_new or not words_ex:
            continue
        overlap = len(words_new & words_ex) / max(len(words_new), len(words_ex))
        if overlap >= threshold:
            return True
    return False


def _detect_genre(project_path: str) -> str:
    """プロジェクトのジャンルをproject_map.jsonから推定"""
    try:
        path = os.path.join(project_path, "blackwell_brain", "project_map.json")
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # ファイル名・関数名からジャンル推定
        all_text = json.dumps(data).lower()
        genre_keywords = {
            "roguelike": ["roguelike", "rogue", "procedural", "dungeon"],
            "platformer": ["platformer", "jump", "platform", "side_scroll"],
            "rpg":        ["rpg", "quest", "level_up", "inventory", "stats"],
            "shooter":    ["shoot", "bullet", "projectile", "enemy_spawn"],
            "puzzle":     ["puzzle", "grid", "tile", "match"],
        }
        for genre, keywords in genre_keywords.items():
            if any(kw in all_text for kw in keywords):
                return genre
    except Exception:
        pass
    return "general"
