"""
Blackwell Dev-OS — balance_ai.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ゲームバランス自動調整AI

プレイログを読んで「2面が難しすぎる」を自動検出
→ パラメータを自動調整 → ゲームコードに反映。
MDA理論 × フロー理論で科学的に調整する。

【ログ形式】
  JSON: {"level": 1, "deaths": 3, "time_s": 120, "reached_x": 450, "items": 2}

【公開API】
  analyze_play_log(log_path)         → BalanceReport
  generate_adjustments(report)       → list[Adjustment]
  apply_adjustments(adj, code_path)  → dict
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json, os, re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LevelStats:
    level:       int
    deaths:      int   = 0
    time_s:      float = 0.0
    reached_x:   float = 0.0
    items_got:   int   = 0
    completions: int   = 0
    attempts:    int   = 0

    @property
    def death_rate(self) -> float:
        return self.deaths / max(self.attempts, 1)

    @property
    def completion_rate(self) -> float:
        return self.completions / max(self.attempts, 1)


@dataclass
class Adjustment:
    level:       int
    param:       str    # "enemy_speed", "player_hp", "item_spawn", etc.
    old_value:   float
    new_value:   float
    reason:      str
    code_pattern:str = ""   # 置換対象の正規表現
    code_replace: str = ""  # 置換後の文字列
    severity:    str = "medium"  # critical/high/medium/low


@dataclass
class BalanceReport:
    issues:      list = field(default_factory=list)   # (level, issue_type, msg)
    adjustments: list = field(default_factory=list)   # Adjustment list
    stats:       list = field(default_factory=list)   # LevelStats list
    summary:     str  = ""


# ── バランス判定閾値 ───────────────────────────────────────
THRESHOLDS = {
    "death_rate_too_hard":    0.7,   # 70%以上の試行で死んでいる → 難しすぎ
    "death_rate_too_easy":    0.05,  # 5%未満 → 簡単すぎ
    "completion_rate_low":    0.3,   # クリア率30%未満 → 詰まっている
    "time_too_long":          300,   # 300秒超 → ステージが長すぎ
    "time_too_short":         20,    # 20秒未満 → 短すぎ
    "items_zero_ratio":       0.4,   # 40%以上がアイテム0個取得 → 気づかれていない
}

# ── 調整値の変化量 ─────────────────────────────────────────
ADJUSTMENT_DELTA = {
    "enemy_speed":  {"too_hard": 0.85, "too_easy": 1.15},
    "enemy_damage": {"too_hard": 0.80, "too_easy": 1.20},
    "player_hp":    {"too_hard": 1.20, "too_easy": 0.90},
    "item_spawn":   {"too_hard": 1.30, "too_easy": 0.80},
    "invincible_frames": {"too_hard": 1.25, "too_easy": 0.90},
}


def analyze_play_log(log_path: str) -> BalanceReport:
    """
    プレイログJSONを読んでバランスレポートを生成。

    ログ形式（1プレイ=1エントリ）:
    [
      {"level": 1, "deaths": 0, "time_s": 45, "reached_x": 800, "items": 3, "cleared": true},
      {"level": 2, "deaths": 5, "time_s": 240, "reached_x": 300, "items": 0, "cleared": false},
    ]
    """
    report = BalanceReport()

    # ログ読み込み
    entries = []
    if os.path.exists(log_path):
        try:
            with open(log_path, encoding="utf-8") as f:
                entries = json.load(f)
            if isinstance(entries, dict):
                entries = [entries]
        except Exception as e:
            report.summary = f"ログ読み込み失敗: {e}"
            return report
    else:
        report.summary = "ログファイルが見つかりません"
        return report

    # レベル別に集計
    level_map: dict[int, LevelStats] = {}
    for entry in entries:
        lv = entry.get("level", 1)
        if lv not in level_map:
            level_map[lv] = LevelStats(level=lv)
        s = level_map[lv]
        s.deaths      += entry.get("deaths", 0)
        s.time_s      += entry.get("time_s", 0)
        s.reached_x    = max(s.reached_x, entry.get("reached_x", 0))
        s.items_got   += entry.get("items", 0)
        s.attempts    += 1
        if entry.get("cleared", False):
            s.completions += 1

    report.stats = list(level_map.values())

    # 問題検出
    issues = []
    for lv, s in sorted(level_map.items()):
        avg_time = s.time_s / max(s.attempts, 1)

        if s.death_rate >= THRESHOLDS["death_rate_too_hard"]:
            issues.append((lv, "too_hard",
                f"Lv{lv}: 死亡率{s.death_rate:.0%}（難しすぎる）"))
        elif s.death_rate <= THRESHOLDS["death_rate_too_easy"] and s.attempts >= 5:
            issues.append((lv, "too_easy",
                f"Lv{lv}: 死亡率{s.death_rate:.0%}（簡単すぎる）"))

        if s.completion_rate < THRESHOLDS["completion_rate_low"] and s.attempts >= 3:
            issues.append((lv, "stuck",
                f"Lv{lv}: クリア率{s.completion_rate:.0%}（詰まっている）"))

        if avg_time > THRESHOLDS["time_too_long"]:
            issues.append((lv, "too_long",
                f"Lv{lv}: 平均プレイ時間{avg_time:.0f}秒（ステージが長すぎる）"))

        if avg_time < THRESHOLDS["time_too_short"] and s.attempts >= 3:
            issues.append((lv, "too_short",
                f"Lv{lv}: 平均プレイ時間{avg_time:.0f}秒（短すぎる）"))

        if s.attempts >= 5 and s.items_got / max(s.attempts, 1) < 0.5:
            issues.append((lv, "items_ignored",
                f"Lv{lv}: アイテム取得率が低い（配置を見直すべき）"))

    report.issues = issues

    # 調整提案生成
    report.adjustments = _generate_adjustments_from_issues(issues, level_map)

    # サマリー生成
    if not issues:
        report.summary = "✅ バランスに大きな問題は検出されませんでした。"
    else:
        hard = [i for i in issues if i[1] in ("too_hard", "stuck")]
        easy = [i for i in issues if i[1] == "too_easy"]
        report.summary = (
            f"検出: {len(issues)}件の問題 "
            f"（難しすぎる: {len(hard)}件 / 簡単すぎる: {len(easy)}件 / その他: {len(issues)-len(hard)-len(easy)}件）"
        )

    return report


def _generate_adjustments_from_issues(
    issues: list, level_map: dict[int, LevelStats]
) -> list[Adjustment]:
    """問題リストから具体的な調整パラメータを生成"""
    adjustments = []

    for lv, issue_type, msg in issues:
        if issue_type in ("too_hard", "stuck"):
            # 難しすぎ → 敵を弱く、プレイヤーを強く
            adjustments.append(Adjustment(
                level=lv, param="enemy_speed",
                old_value=1.0,
                new_value=ADJUSTMENT_DELTA["enemy_speed"]["too_hard"],
                reason=f"Lv{lv}が難しすぎる → 敵速度を15%低下",
                code_pattern=f"ENEMY_SPEED_LV{lv}\\s*=\\s*([0-9.]+)",
                code_replace=f"ENEMY_SPEED_LV{lv} = {{new_val}}",
                severity="high",
            ))
            adjustments.append(Adjustment(
                level=lv, param="player_hp",
                old_value=100.0,
                new_value=100.0 * ADJUSTMENT_DELTA["player_hp"]["too_hard"],
                reason=f"Lv{lv}が難しすぎる → プレイヤーHP20%増加",
                code_pattern=f"PLAYER_HP\\s*=\\s*([0-9.]+)",
                code_replace=f"PLAYER_HP = {{new_val}}",
                severity="medium",
            ))
            adjustments.append(Adjustment(
                level=lv, param="invincible_frames",
                old_value=20.0,
                new_value=20.0 * ADJUSTMENT_DELTA["invincible_frames"]["too_hard"],
                reason=f"Lv{lv}が難しすぎる → 被弾後の無敵フレームを増やす",
                severity="medium",
            ))

        elif issue_type == "too_easy":
            # 簡単すぎ → 敵を強く
            adjustments.append(Adjustment(
                level=lv, param="enemy_speed",
                old_value=1.0,
                new_value=ADJUSTMENT_DELTA["enemy_speed"]["too_easy"],
                reason=f"Lv{lv}が簡単すぎる → 敵速度を15%増加",
                severity="low",
            ))

        elif issue_type == "too_long":
            # ステージが長すぎ → 敵数を減らすか敵速度下げる
            adjustments.append(Adjustment(
                level=lv, param="enemy_count",
                old_value=10.0, new_value=8.0,
                reason=f"Lv{lv}が長すぎる → 敵の数を20%削減",
                severity="medium",
            ))

        elif issue_type == "items_ignored":
            # アイテムが取られていない → 配置を目立つ場所に
            adjustments.append(Adjustment(
                level=lv, param="item_spawn_rate",
                old_value=1.0,
                new_value=ADJUSTMENT_DELTA["item_spawn"]["too_hard"],
                reason=f"Lv{lv}のアイテムが取られていない → スポーン率を30%増加",
                severity="low",
            ))

    return adjustments


def apply_adjustments(adjustments: list, code_path: str) -> dict:
    """
    調整パラメータをコードファイルに適用する。
    定数パターン (CONST_NAME = value) を自動置換。
    """
    if not os.path.exists(code_path):
        return {"success": False, "message": f"ファイルが見つかりません: {code_path}"}

    try:
        with open(code_path, encoding="utf-8") as f:
            code = f.read()

        backup_path = code_path + ".balance_backup"
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(code)

        applied = 0
        for adj in adjustments:
            if not adj.code_pattern:
                continue
            try:
                pattern = re.compile(adj.code_pattern, re.IGNORECASE)
                m = pattern.search(code)
                if m:
                    replacement = adj.code_replace.format(new_val=round(adj.new_value, 3))
                    code = pattern.sub(replacement, code)
                    applied += 1
            except Exception:
                pass

        with open(code_path, "w", encoding="utf-8") as f:
            f.write(code)

        return {
            "success": True,
            "applied": applied,
            "backup":  backup_path,
            "message": f"✅ {applied}件のパラメータを自動調整しました（バックアップ: {backup_path}）",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


def format_balance_report(report: BalanceReport) -> str:
    """バランスレポートをMarkdownで出力"""
    lines = ["## ⚖️ ゲームバランス診断レポート", "", f"**{report.summary}**", ""]

    if report.stats:
        lines += ["### 📊 レベル別統計",
                  "| Lv | 試行 | 死亡率 | クリア率 | 平均時間 |",
                  "|---|---|---|---|---|"]
        for s in sorted(report.stats, key=lambda x: x.level):
            avg_t = s.time_s / max(s.attempts, 1)
            lines.append(
                f"| {s.level} | {s.attempts} | {s.death_rate:.0%} "
                f"| {s.completion_rate:.0%} | {avg_t:.0f}s |"
            )
        lines.append("")

    if report.issues:
        lines += ["### 🔍 検出された問題"]
        for lv, itype, msg in report.issues:
            icon = {"too_hard":"🔴","too_easy":"🟡","stuck":"🔴",
                    "too_long":"🟡","too_short":"🟢","items_ignored":"🟢"}.get(itype,"⚪")
            lines.append(f"- {icon} {msg}")
        lines.append("")

    if report.adjustments:
        lines += ["### 🔧 推奨調整パラメータ"]
        for adj in report.adjustments:
            sev_icon = {"critical":"🔴","high":"🟠","medium":"🟡","low":"🟢"}.get(adj.severity,"⚪")
            lines.append(
                f"- {sev_icon} **{adj.param}** (Lv{adj.level}): "
                f"{adj.old_value:.2f} → **{adj.new_value:.2f}**\n"
                f"  理由: {adj.reason}"
            )

    return "\n".join(lines)


def generate_sample_log(path: str = "./playtest_log.json"):
    """テスト用サンプルログを生成"""
    sample = [
        {"level": 1, "deaths": 0, "time_s": 35, "reached_x": 900, "items": 3, "cleared": True},
        {"level": 1, "deaths": 1, "time_s": 40, "reached_x": 900, "items": 2, "cleared": True},
        {"level": 2, "deaths": 8, "time_s": 280, "reached_x": 200, "items": 0, "cleared": False},
        {"level": 2, "deaths": 6, "time_s": 310, "reached_x": 180, "items": 0, "cleared": False},
        {"level": 2, "deaths": 9, "time_s": 290, "reached_x": 220, "items": 0, "cleared": False},
        {"level": 3, "deaths": 1, "time_s": 12, "reached_x": 1200, "items": 5, "cleared": True},
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    return path


# ============================================================
# バランスAI ログ形式柔軟化
# テキスト形式・Godotデフォルト出力・Pygame printも読める
# ============================================================

def parse_flexible_log(log_path: str) -> list:
    """
    複数形式のプレイログを読んで統一フォーマットに変換する。

    対応形式:
      A) JSON配列 (既存)
      B) 1行1エントリのCSV: level,deaths,time,cleared
      C) Godotのprint出力: [PLAYLOG] level=2 deaths=5 time=120 cleared=false
      D) Pygame/Python print: LEVEL:2 DEATHS:5 TIME:120 CLEARED:False
      E) キーワード混在テキスト: 適当なテキストからも値を拾う
    """
    if not os.path.exists(log_path):
        return []

    with open(log_path, encoding="utf-8", errors="ignore") as f:
        content = f.read().strip()

    if not content:
        return []

    # A) JSON
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except Exception:
        pass

    # B) CSV（ヘッダー付き or なし）
    lines = content.splitlines()
    if "," in lines[0]:
        try:
            import csv, io
            reader = csv.DictReader(io.StringIO(content))
            rows = list(reader)
            if rows and "level" in rows[0]:
                result = []
                for row in rows:
                    entry = {
                        "level":   int(row.get("level", 1)),
                        "deaths":  int(row.get("deaths", 0)),
                        "time_s":  float(row.get("time", row.get("time_s", 0))),
                        "cleared": str(row.get("cleared","false")).lower() == "true",
                        "items":   int(row.get("items", 0)),
                    }
                    result.append(entry)
                return result
        except Exception:
            pass

    # C) Godot print形式: [PLAYLOG] key=value key=value
    # D) KEYWORD:value形式
    # E) テキストから値を拾う
    result = []
    pat_godot  = re.compile(r"\[PLAYLOG\](.*)", re.IGNORECASE)
    pat_kv     = re.compile(r"(\w+)[=:](\S+)")

    def parse_kv_line(line: str) -> Optional[dict]:
        kvs = dict(pat_kv.findall(line.lower()))
        if not kvs:
            return None
        # level と deaths があれば有効なエントリ
        if "level" not in kvs and "lv" not in kvs:
            return None
        return {
            "level":   int(kvs.get("level", kvs.get("lv", 1))),
            "deaths":  int(kvs.get("deaths", kvs.get("death", 0))),
            "time_s":  float(kvs.get("time", kvs.get("time_s", kvs.get("sec", 0)))),
            "cleared": kvs.get("cleared", kvs.get("clear", "false")).lower() in ("true","1","yes"),
            "items":   int(kvs.get("items", kvs.get("item", 0))),
            "reached_x": float(kvs.get("reached_x", kvs.get("x", 0))),
        }

    for line in lines:
        # Godot形式
        m = pat_godot.search(line)
        if m:
            entry = parse_kv_line(m.group(1))
            if entry:
                result.append(entry)
            continue
        # 汎用KV形式
        entry = parse_kv_line(line)
        if entry:
            result.append(entry)

    return result


def analyze_play_log_flexible(log_path: str) -> BalanceReport:
    """
    形式を問わずログを読んでバランスレポートを返す。
    JSON・CSV・テキスト・Godotプリント全て対応。
    """
    entries = parse_flexible_log(log_path)

    if not entries:
        report = BalanceReport()
        report.summary = f"ログを読み込めませんでした: {log_path}\n対応形式: JSON / CSV / Godot print / KV形式テキスト"
        return report

    # 一時ファイルにJSONとして保存して既存の analyze_play_log に渡す
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                      delete=False, encoding="utf-8") as tmp:
        json.dump(entries, tmp, ensure_ascii=False)
        tmp_path = tmp.name

    try:
        return analyze_play_log(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
