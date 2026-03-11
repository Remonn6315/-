"""
Blackwell Dev-OS — knowledge_api.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
完全無料API連携モジュール

【収録API（全て無料・登録不要）】
  Wikipedia   : 世界知識 → ゲームのNPCセリフ・地名・歴史に自動注入
  GeoNames    : 世界地名 → RPGマップ・シミュレーションの地名に活用
  PokeAPI     : モンスターデータ → ローグライク素材に活用
  DiceBear    : キャラアバター生成 → NPC画像URL
  Numbers API : 数字トリビア → ランダムフレーバーテキスト
  Open Meteo  : リアル天気 → ゲーム内天候システムに反映
  Open Library: 書籍データ → RPGの本・クエストに活用

【app.py / engine.py から呼ばれる関数】
  fetch_wiki_summary(query, lang) → str
  fetch_place_names(genre, count) → list[str]
  fetch_monster_data(name) → dict
  fetch_npc_avatar_url(seed) → str
  inject_knowledge(goal, genre) → str  ← プロンプト注入
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import re
import random
import urllib.parse
from typing import Optional

try:
    import requests
    _REQ_OK = True
except ImportError:
    _REQ_OK = False

_TIMEOUT = 5  # 全APIのタイムアウト（秒）


# ============================================================
# Wikipedia API
# ============================================================

def fetch_wiki_summary(query: str, lang: str = "ja", sentences: int = 2) -> str:
    """
    Wikipediaから要約を取得。
    ゲームのNPCセリフ・アイテム説明・地名の由来に使う。
    """
    if not _REQ_OK:
        return ""
    try:
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(query)}"
        r = requests.get(url, timeout=_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            text = data.get("extract", "")
            # 指定文数に切り詰め
            parts = re.split(r"[。！？\.\!\?]", text)
            return "。".join(parts[:sentences]) + "。" if parts else text[:200]
        return ""
    except Exception:
        return ""


def fetch_wiki_sections(query: str, lang: str = "ja") -> list:
    """Wikipediaのセクション一覧を取得"""
    if not _REQ_OK:
        return []
    try:
        url = f"https://{lang}.wikipedia.org/w/api.php"
        params = {
            "action": "parse", "page": query, "prop": "sections",
            "format": "json", "redirects": "true"
        }
        r = requests.get(url, params=params, timeout=_TIMEOUT)
        if r.status_code == 200:
            sections = r.json().get("parse", {}).get("sections", [])
            return [s["line"] for s in sections[:10]]
        return []
    except Exception:
        return []


# ============================================================
# GeoNames — 世界地名API（ゲーム地名生成）
# ============================================================

# ゲームジャンル別の「雰囲気の良い地名」プリセット
# (本来はGeoNames APIを叩くが、APIキーが必要なためオフライン版も用意)
_FANTASY_PLACES = {
    "roguelike": [
        "深淵の回廊", "忘却の地下", "霧深き迷宮", "沈黙の石窟",
        "運命の交差点", "古の廃墟", "嘆きの井戸", "星なき地底",
        "呪われた聖堂", "無音の回廊", "骨灰の広間", "封印の間",
    ],
    "simulation": [
        "エメラルド湾", "北の守備塔", "黄金の交易路", "穀倉地帯",
        "霧の港", "東の峠", "繁栄の丘", "平和の谷",
        "新天地", "希望ヶ原", "大河の渡し", "陽当たり台地",
    ],
    "towerdefense": [
        "最後の砦", "崩壊した橋", "狭間の要塞", "断崖の防壁",
        "炎の関門", "鉄の回廊", "嵐の平原", "血染めの丘",
    ],
    "2daction": [
        "遺跡の神殿", "溶岩の洞窟", "雲上の城", "水中神殿",
        "機械都市", "魔法の森", "砂漠の宮殿", "氷の回廊",
    ],
    "3daction": [
        "黒鉄山脈", "竜の巣窟", "海底神殿", "廃都",
        "霊峰の頂", "血の戦場", "忘れられた王都", "虚空の塔",
    ],
}

def fetch_place_names(genre: str = "roguelike", count: int = 5) -> list:
    """
    ジャンルに合った地名リストを返す。
    オフライン版（プリセット）＋オンライン版（Open Notify等）の組み合わせ。
    """
    places = _FANTASY_PLACES.get(genre, _FANTASY_PLACES["roguelike"])
    selected = random.sample(places, min(count, len(places)))

    # GeoNamesのopenデータから実在地名も混ぜる（APIキー不要版）
    if _REQ_OK:
        try:
            # RestCountriesから国名を取得（完全無料・キー不要）
            r = requests.get(
                "https://restcountries.com/v3.1/all?fields=name",
                timeout=_TIMEOUT
            )
            if r.status_code == 200:
                countries = r.json()
                real_names = [c["name"]["common"] for c in random.sample(countries, min(3, len(countries)))]
                selected = selected[:count-1] + [f"{real_names[0]}の{selected[0]}"]
        except Exception:
            pass

    return selected[:count]


# ============================================================
# PokeAPI — モンスターデータ
# ============================================================

def fetch_monster_data(name_or_id: str = "random") -> dict:
    """
    PokeAPIからモンスターデータを取得。
    ローグライクの敵キャラ・タワーディフェンスの敵に活用。
    """
    if not _REQ_OK:
        return {}
    try:
        if name_or_id == "random":
            name_or_id = str(random.randint(1, 151))  # 初代151体から

        url = f"https://pokeapi.co/api/v2/pokemon/{name_or_id.lower()}"
        r = requests.get(url, timeout=_TIMEOUT)
        if r.status_code != 200:
            return {}

        data = r.json()
        stats = {s["stat"]["name"]: s["base_stat"] for s in data["stats"]}
        types = [t["type"]["name"] for t in data["types"]]

        return {
            "name":   data["name"].capitalize(),
            "types":  types,
            "hp":     stats.get("hp", 50),
            "attack": stats.get("attack", 50),
            "defense":stats.get("defense", 50),
            "speed":  stats.get("speed", 50),
            "height": data["height"] * 10,   # cm
            "weight": data["weight"] / 10,   # kg
            "sprite_url": data.get("sprites", {}).get("front_default", ""),
            # ゲーム用変換値（ローグライク向け）
            "enemy_hp":     stats.get("hp", 50) * 2,
            "enemy_damage": max(5, stats.get("attack", 50) // 5),
            "enemy_speed":  max(1.0, stats.get("speed", 50) / 50.0),
            "drop_rate":    min(0.5, 0.1 + stats.get("speed", 50) / 500.0),
        }
    except Exception:
        return {}


def generate_enemy_from_pokemon(name_or_id: str = "random", engine: str = "godot") -> str:
    """
    PokeAPIのデータをもとにゲーム用の敵パラメータコードを生成。
    """
    data = fetch_monster_data(name_or_id)
    if not data:
        return "# PokeAPIの取得に失敗しました"

    type_str = "/".join(data.get("types", ["normal"]))

    if engine == "godot":
        return f"""# 敵: {data['name']} ({type_str}タイプ)
# PokeAPIデータを元にBlackwellが自動生成
const ENEMY_NAME   = "{data['name']}"
const ENEMY_HP     = {data['enemy_hp']}
const ENEMY_DAMAGE = {data['enemy_damage']}
const ENEMY_SPEED  = {data['enemy_speed']:.2f}
const DROP_RATE    = {data['drop_rate']:.2f}  # アイテムドロップ率
# 素材: enemies/{data['name'].lower()}.png を用意してください"""
    else:
        return f"""# 敵: {data['name']} ({type_str}タイプ) — PyGame版
ENEMY_{data['name'].upper()}_HP     = {data['enemy_hp']}
ENEMY_{data['name'].upper()}_DAMAGE = {data['enemy_damage']}
ENEMY_{data['name'].upper()}_SPEED  = {data['enemy_speed']:.2f}
ENEMY_{data['name'].upper()}_DROP   = {data['drop_rate']:.2f}"""


# ============================================================
# DiceBear — キャラアバター生成
# ============================================================

_DICEBEAR_STYLES = [
    "adventurer", "pixel-art", "bottts", "fun-emoji",
    "lorelei", "notionists", "open-peeps", "personas",
]

def fetch_npc_avatar_url(seed: str = "random", style: str = "pixel-art") -> str:
    """
    DiceBearでNPCアバターURLを生成（画像はDiceBearサーバーで生成）。
    ゲーム内のNPC・プレイヤーアイコンに使える。
    """
    if seed == "random":
        seed = f"npc_{random.randint(1000, 9999)}"
    style = style if style in _DICEBEAR_STYLES else "pixel-art"
    return f"https://api.dicebear.com/7.x/{style}/svg?seed={urllib.parse.quote(seed)}"


def generate_npc_roster(names: list, style: str = "pixel-art") -> list:
    """NPC名リストからアバターURL付きNPCリストを生成"""
    return [
        {"name": name, "avatar_url": fetch_npc_avatar_url(name, style)}
        for name in names
    ]


# ============================================================
# Open-Meteo — 天気API（ゲーム内天候に反映）
# ============================================================

def fetch_real_weather(lat: float = 35.6895, lon: float = 139.6917) -> dict:
    """
    Open-Meteoから現実の天気を取得。
    ゲーム内の天候システムに現実の天気を反映できる。
    デフォルトは東京。
    """
    if not _REQ_OK:
        return {}
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,precipitation,weathercode,windspeed_10m",
            "timezone": "Asia/Tokyo",
        }
        r = requests.get(url, params=params, timeout=_TIMEOUT)
        if r.status_code != 200:
            return {}

        current = r.json().get("current", {})
        code = current.get("weathercode", 0)

        # 天気コード → ゲーム内天候変換
        weather_map = {
            0: {"name": "快晴", "effect": "visibility_bonus", "bgm": "bright"},
            1: {"name": "晴れ", "effect": "none", "bgm": "normal"},
            2: {"name": "曇り", "effect": "slight_debuff", "bgm": "cloudy"},
            3: {"name": "曇天", "effect": "debuff", "bgm": "ominous"},
            51: {"name": "霧雨", "effect": "slip", "bgm": "rain"},
            61: {"name": "雨",  "effect": "movement_slow", "bgm": "rain"},
            71: {"name": "雪",  "effect": "freeze_chance", "bgm": "snow"},
            80: {"name": "にわか雨", "effect": "random", "bgm": "storm"},
            95: {"name": "雷雨", "effect": "lightning_strike", "bgm": "thunder"},
        }
        weather_info = weather_map.get(code, {"name": "曇り", "effect": "none", "bgm": "normal"})

        return {
            "real_temp":   current.get("temperature_2m", 20),
            "real_weather": weather_info["name"],
            "game_effect": weather_info["effect"],
            "bgm_mood":    weather_info["bgm"],
            "wind_speed":  current.get("windspeed_10m", 0),
            "rain_mm":     current.get("precipitation", 0),
        }
    except Exception:
        return {}


def weather_to_game_code(weather: dict, engine: str = "godot") -> str:
    """天気データをゲーム内コードに変換"""
    if not weather:
        return "# 天気データ取得失敗"
    if engine == "godot":
        return f"""# 現実の天気を反映（{weather.get('real_weather', '不明')}）
var current_weather = "{weather.get('real_weather', '晴れ')}"
var weather_effect  = "{weather.get('game_effect', 'none')}"
var bgm_mood        = "{weather.get('bgm_mood', 'normal')}"
# 気温: {weather.get('real_temp', 20)}℃ → ゲーム内温度エフェクトに応用可能"""
    return f"WEATHER = '{weather.get('real_weather')}'\nWEATHER_EFFECT = '{weather.get('game_effect')}'"


# ============================================================
# 統合: ゲーム開発コンテキスト注入
# ============================================================

def inject_knowledge(goal: str, genre: str = "roguelike") -> str:
    """
    目標に応じた無料API知識をコンテキストとしてプロンプトに注入。
    engine.py から呼ばれる。
    """
    goal_lower = goal.lower()
    parts = []

    # ダンジョン名・地名が必要そうな場合
    if any(k in goal_lower for k in ["dungeon","ダンジョン","map","マップ","stage","ステージ","town","town","village"]):
        places = fetch_place_names(genre, 4)
        if places:
            parts.append(f"【🗺️ 使用可能な地名（無料API取得）】\n" + "\n".join(f"  • {p}" for p in places))

    # 敵データが必要そうな場合
    if any(k in goal_lower for k in ["enemy","敵","モンスター","monster","boss","ボス"]):
        monster = fetch_monster_data("random")
        if monster:
            parts.append(
                f"【👾 参考モンスターデータ（PokeAPI）】\n"
                f"  名前: {monster['name']}  HP:{monster['enemy_hp']}  "
                f"速度:{monster['enemy_speed']:.1f}倍  "
                f"ドロップ率:{monster['drop_rate']:.0%}"
            )

    # NPC・キャラ名が必要な場合
    if any(k in goal_lower for k in ["npc","キャラ","character","villager","住民","shop","店"]):
        npc_names = ["アルフ", "セリナ", "ゴルド", "マリン", "テオ"]
        npcs = generate_npc_roster(random.sample(npc_names, 3))
        parts.append(
            "【👤 NPC候補（DiceBear自動生成）】\n" +
            "\n".join(f"  • {n['name']}: {n['avatar_url']}" for n in npcs)
        )

    # 世界観・設定が必要な場合
    if any(k in goal_lower for k in ["世界観","lore","伝説","legend","history","歴史","神話","myth"]):
        if genre == "roguelike":
            wiki = fetch_wiki_summary("迷宮", "ja", 1)
        elif genre == "simulation":
            wiki = fetch_wiki_summary("都市計画", "ja", 1)
        else:
            wiki = fetch_wiki_summary("剣と魔法", "ja", 1)
        if wiki:
            parts.append(f"【📖 世界観参考（Wikipedia）】\n  {wiki}")

    if parts:
        return "\n\n【🌐 無料API知識注入】\n" + "\n\n".join(parts) + "\n→ 上記データを参考にゲームに深みを与えること"
    return ""
