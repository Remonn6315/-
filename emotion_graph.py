"""
Blackwell Dev-OS — emotion_graph.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ゲームの「感情グラフ」

プレイログの死亡・アイテム取得・到達距離を時系列で追って
「この瞬間プレイヤーは興奮/絶望/フロー状態だった」を
感情曲線として可視化。MDA理論のAffect直結。

感情モデル:
  excitement  = (速度+コンボ+アイテム取得) ↑
  anxiety     = (HP低+強敵+時間切れ近い) ↑
  boredom     = (長時間無イベント+易しすぎ) ↑
  flow        = anxiety と boredom のバランスゾーン

【公開API】
  compute_emotion_curve(play_events) → EmotionData
  build_emotion_svg(emotion_data)    → str (SVG)
  detect_problem_zones(emotion_data) → list[ProblemZone]
"""
import os, json, math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PlayEvent:
    """1プレイイベント"""
    t:          float   # タイムスタンプ（秒）
    event_type: str     # death / item_get / damage / combo / clear / idle / boss
    value:      float   # イベントの強度（ダメージ量・コンボ数 etc）
    x:          float = 0.0
    y:          float = 0.0


@dataclass
class EmotionPoint:
    t:          float
    excitement: float   # 0〜1
    anxiety:    float   # 0〜1
    boredom:    float   # 0〜1
    flow:       float   # 0〜1 (excitementとanxietyのバランス)
    hp:         float = 1.0
    label:      str = ""


@dataclass
class ProblemZone:
    start_t:    float
    end_t:      float
    zone_type:  str    # too_hard / too_easy / boredom / spike
    description:str
    suggestion: str


@dataclass
class EmotionData:
    points:       list = field(default_factory=list)   # EmotionPoint list
    problem_zones:list = field(default_factory=list)
    peak_excitement_t: float = 0.0
    peak_anxiety_t:    float = 0.0
    flow_ratio:        float = 0.0   # 0〜1 (フロー状態の割合)
    total_duration:    float = 0.0


# 感情係数テーブル
EMOTION_WEIGHTS = {
    "death":    {"excitement": -0.3, "anxiety": +0.5, "boredom": -0.2},
    "item_get": {"excitement": +0.4, "anxiety": -0.1, "boredom": -0.3},
    "damage":   {"excitement": +0.1, "anxiety": +0.3, "boredom": -0.1},
    "combo":    {"excitement": +0.5, "anxiety": -0.1, "boredom": -0.4},
    "clear":    {"excitement": +0.6, "anxiety": -0.4, "boredom": -0.2},
    "idle":     {"excitement": -0.1, "anxiety": -0.1, "boredom": +0.3},
    "boss":     {"excitement": +0.3, "anxiety": +0.4, "boredom": -0.5},
}

FLOW_ZONE_LOW  = 0.25  # これ以下はboredom
FLOW_ZONE_HIGH = 0.75  # これ以上はanxiety


def compute_emotion_curve(
    events: list,
    window: float = 15.0,
    smoothing: float = 0.7,
) -> EmotionData:
    """
    イベントリストから感情曲線を計算する。

    events: list of dicts or PlayEvent
      [{"t": 10.5, "type": "damage", "value": 15}, ...]

    window: 感情計算の時間窓（秒）
    smoothing: 指数移動平均の係数（0〜1, 大きいほど滑らか）
    """
    # 正規化
    play_events = []
    for e in events:
        if isinstance(e, dict):
            play_events.append(PlayEvent(
                t=float(e.get("t", e.get("time", 0))),
                event_type=e.get("type", e.get("event_type", "idle")),
                value=float(e.get("value", 1.0)),
                x=float(e.get("x", 0)), y=float(e.get("y", 0)),
            ))
        elif isinstance(e, PlayEvent):
            play_events.append(e)

    if not play_events:
        return EmotionData()

    play_events.sort(key=lambda e: e.t)
    total_t = play_events[-1].t

    # 1秒ごとにサンプリング
    sample_ts = list(range(0, int(total_t) + 1, max(1, int(total_t // 100))))
    if not sample_ts:
        return EmotionData()

    # 初期値
    exc  = 0.3
    anx  = 0.2
    bor  = 0.1
    hp   = 1.0
    points = []

    peak_exc_t  = 0.0
    peak_anx_t  = 0.0
    peak_exc    = 0.0
    peak_anx    = 0.0
    flow_frames = 0

    for ts in sample_ts:
        # 時間窓内のイベントを集約
        window_events = [e for e in play_events if ts - window <= e.t <= ts]

        delta_exc = 0.0
        delta_anx = 0.0
        delta_bor = 0.0

        for ev in window_events:
            w = EMOTION_WEIGHTS.get(ev.event_type, {})
            intensity = min(ev.value / 100.0, 1.0)  # 正規化
            delta_exc += w.get("excitement", 0) * intensity
            delta_anx += w.get("anxiety",    0) * intensity
            delta_bor += w.get("boredom",    0) * intensity
            if ev.event_type == "death":
                hp = max(0.0, hp - 0.3)
            elif ev.event_type == "item_get" and "hp" in str(ev.value).lower():
                hp = min(1.0, hp + 0.2)

        # 指数移動平均で滑らか
        alpha = 1 - smoothing
        exc  = max(0, min(1, exc * smoothing + (exc + delta_exc) * alpha))
        anx  = max(0, min(1, anx * smoothing + (anx + delta_anx) * alpha))
        bor  = max(0, min(1, bor * smoothing + (bor + delta_bor) * alpha))

        # イベントがなければ退屈が増加
        if not window_events:
            bor = min(1, bor + 0.02)
            exc = max(0, exc - 0.01)

        # フロー計算: anxiety と excitement のバランスゾーン
        diff = abs(exc - anx)
        flow = max(0, 1.0 - diff * 2) * (1 - bor)

        if exc > peak_exc:
            peak_exc   = exc
            peak_exc_t = ts
        if anx > peak_anx:
            peak_anx   = anx
            peak_anx_t = ts
        if flow > 0.5:
            flow_frames += 1

        points.append(EmotionPoint(
            t=ts, excitement=exc, anxiety=anx, boredom=bor, flow=flow, hp=hp
        ))

    # 問題ゾーン検出
    problem_zones = _detect_problem_zones(points)

    return EmotionData(
        points=points,
        problem_zones=problem_zones,
        peak_excitement_t=peak_exc_t,
        peak_anxiety_t=peak_anx_t,
        flow_ratio=flow_frames / max(len(sample_ts), 1),
        total_duration=total_t,
    )


def _detect_problem_zones(points: list) -> list:
    """感情曲線から問題ゾーンを検出"""
    zones = []
    zone_start = None
    zone_type  = None
    THRESHOLD_SEC = 10  # 10秒以上続いたら問題ゾーン

    for pt in points:
        ptype = None
        if pt.anxiety > 0.8:
            ptype = "too_hard"
        elif pt.boredom > 0.7:
            ptype = "too_easy"
        elif pt.flow < 0.2 and pt.excitement < 0.3 and pt.anxiety < 0.3:
            ptype = "boredom"

        if ptype:
            if zone_type == ptype:
                pass  # 継続
            else:
                if zone_start and zone_type:
                    dur = pt.t - zone_start
                    if dur >= THRESHOLD_SEC:
                        zones.append(_make_zone(zone_type, zone_start, pt.t))
                zone_start = pt.t
                zone_type  = ptype
        else:
            if zone_start and zone_type:
                dur = pt.t - zone_start
                if dur >= THRESHOLD_SEC:
                    zones.append(_make_zone(zone_type, zone_start, pt.t))
            zone_start = None
            zone_type  = None

    return zones


def _make_zone(ztype: str, start: float, end: float) -> ProblemZone:
    desc_map = {
        "too_hard": f"{start:.0f}〜{end:.0f}秒: プレイヤーが強すぎるプレッシャーを受けている",
        "too_easy": f"{start:.0f}〜{end:.0f}秒: 刺激が少なく退屈している",
        "boredom":  f"{start:.0f}〜{end:.0f}秒: 何も起きていない（デッドゾーン）",
    }
    sug_map = {
        "too_hard": "敵の強さを下げる・チェックポイントを追加・ヒント表示",
        "too_easy": "敵を増やす・速度UP・新しいギミックを配置",
        "boredom":  "イベント・アイテム・敵を配置してテンポを上げる",
    }
    return ProblemZone(
        start_t=start, end_t=end, zone_type=ztype,
        description=desc_map.get(ztype, ""),
        suggestion=sug_map.get(ztype, ""),
    )


def build_emotion_svg(data: EmotionData, width: int = 900, height: int = 300) -> str:
    """感情曲線をSVGで描画"""
    if not data.points:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="100" style="background:#1a1a2e"><text x="200" y="55" text-anchor="middle" fill="#aaa" font-size="14">データなし</text></svg>'

    PAD    = 50
    W      = width  - PAD * 2
    H      = height - PAD * 2
    total  = data.total_duration or 1
    n      = len(data.points)

    def px(t):  return PAD + int(t / total * W)
    def py(v):  return PAD + int((1 - v) * H)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'style="background:#1a1a2e;border-radius:8px">',
        # タイトル
        f'<text x="{width//2}" y="22" text-anchor="middle" fill="white" '
        f'font-size="13" font-family="sans-serif">感情曲線 '
        f'(フロー率: {data.flow_ratio:.0%})</text>',
        # 軸
        f'<line x1="{PAD}" y1="{PAD}" x2="{PAD}" y2="{PAD+H}" stroke="#444" stroke-width="1"/>',
        f'<line x1="{PAD}" y1="{PAD+H}" x2="{PAD+W}" y2="{PAD+H}" stroke="#444" stroke-width="1"/>',
        # フロー帯（薄い緑の帯）
        f'<rect x="{PAD}" y="{py(FLOW_ZONE_HIGH)}" '
        f'width="{W}" height="{py(FLOW_ZONE_LOW)-py(FLOW_ZONE_HIGH)}" '
        f'fill="#2ECC71" opacity="0.08"/>',
        f'<text x="{PAD+4}" y="{py(0.5)+4}" fill="#2ECC71" font-size="9" opacity="0.6">フローゾーン</text>',
    ]

    # 問題ゾーン（背景色）
    zone_colors = {"too_hard":"#E74C3C","too_easy":"#3498DB","boredom":"#95A5A6"}
    for zone in data.problem_zones:
        x1 = px(zone.start_t)
        x2 = px(zone.end_t)
        color = zone_colors.get(zone.zone_type, "#888")
        lines.append(
            f'<rect x="{x1}" y="{PAD}" width="{x2-x1}" height="{H}" '
            f'fill="{color}" opacity="0.12">'
            f'<title>{zone.description}</title></rect>'
        )

    # 曲線を折れ線で描画
    def polyline(key, color, stroke_w=2):
        pts = " ".join(f"{px(p.t)},{py(getattr(p, key))}" for p in data.points)
        return (f'<polyline points="{pts}" fill="none" stroke="{color}" '
                f'stroke-width="{stroke_w}" stroke-linejoin="round" opacity="0.9"/>')

    lines += [
        polyline("boredom",    "#95A5A6", 1),  # グレー（薄く）
        polyline("anxiety",    "#E74C3C", 2),  # 赤
        polyline("excitement", "#F39C12", 2),  # オレンジ
        polyline("flow",       "#2ECC71", 2.5),# 緑（太く）
        polyline("hp",         "#3498DB", 1.5),# 青
    ]

    # 凡例
    legend = [
        ("興奮", "#F39C12", 20), ("不安", "#E74C3C", 80),
        ("フロー", "#2ECC71", 140), ("HP", "#3498DB", 210),
        ("退屈", "#95A5A6", 270),
    ]
    for label, color, lx in legend:
        ly = height - 18
        lines += [
            f'<rect x="{lx}" y="{ly-8}" width="14" height="8" fill="{color}" rx="2"/>',
            f'<text x="{lx+16}" y="{ly}" fill="white" font-size="10">{label}</text>',
        ]

    lines.append("</svg>")
    return "\n".join(lines)


def parse_log_to_events(log_path: str) -> list:
    """
    プレイログJSONからPlayEvent形式に変換するヘルパー。
    balance_ai.py の parse_flexible_log と組み合わせる。
    """
    if not os.path.exists(log_path):
        return []
    try:
        with open(log_path, encoding="utf-8") as f:
            entries = json.load(f)
        events = []
        t = 0.0
        for entry in entries:
            t += entry.get("time_s", 30)
            deaths = entry.get("deaths", 0)
            for _ in range(deaths):
                events.append({"t": t - deaths * 5, "type": "death", "value": 100})
            items = entry.get("items", 0)
            if items > 0:
                events.append({"t": t - 5, "type": "item_get", "value": items * 20})
            if entry.get("cleared", False):
                events.append({"t": t, "type": "clear", "value": 100})
        return events
    except Exception:
        return []


def generate_sample_events() -> list:
    """テスト用サンプルイベント"""
    return [
        {"t":  5, "type":"item_get","value":30},
        {"t": 15, "type":"damage",  "value":25},
        {"t": 20, "type":"combo",   "value":50},
        {"t": 30, "type":"damage",  "value":40},
        {"t": 35, "type":"death",   "value":100},
        {"t": 50, "type":"idle",    "value":10},
        {"t": 65, "type":"idle",    "value":10},
        {"t": 70, "type":"boss",    "value":80},
        {"t": 75, "type":"damage",  "value":60},
        {"t": 80, "type":"death",   "value":100},
        {"t": 95, "type":"item_get","value":50},
        {"t":100, "type":"combo",   "value":80},
        {"t":110, "type":"clear",   "value":100},
    ]
