"""
Blackwell Dev-OS — analyzer.py v2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
万能ファイル解析・外部ナレッジ注入エンジン

【何ができるか】
  ① 形式問わずファイル解析
       py/gd/js/ts/cs/json/csv/yaml/toml/txt/md/xml/html
       png/jpg/mp3/wav/ogg/glb/gltf（メタ情報・役割判定）
  ② プロジェクト種別 & エンジン自動判定
       2Dゲーム/3Dゲーム/RPG/アクション/Webアプリ/AIツール...
       Pygame/Godot/Unity/Phaser/Three.js/RPGMaker
  ③ ゲーム素材の用途自動分類
       スプライト/タイル/背景/UI/エフェクト/BGM/SE
       主人公/敵/ボス/アイテム/武器/魔法/3Dモデル
  ④ プロジェクト全体一括吸収（absorb_project）→RAGに蓄積
  ⑤ 類似プロジェクト模倣→オリジナル提案（suggest_from_similar）
  ⑥ AI自己強化: 解析→学習→次の生成で自動活用のループ

【app.py/engine.py から呼ばれる関数】
  analyze_any_file(filepath, file_obj=None, filename="") -> dict
  absorb_project(folder_path, store_fn=None) -> dict
  suggest_from_similar(goal, project_type="") -> str
  analyze_game_assets_folder(folder_path) -> dict
  build_game_context_from_assets(asset_map, goal) -> str
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import re
import json
import csv
import io
import ast as _ast
import hashlib
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime

try:
    import ollama as _ollama
    _OLLAMA_OK = True
except ImportError:
    _OLLAMA_OK = False

try:
    from memory import store_memory, retrieve_context
    _MEMORY_OK = True
except ImportError:
    _MEMORY_OK = False

_ANALYZER_MODEL = "qwen2.5-coder:14b"

# ============================================================
# 分類定義
# ============================================================

_PROJECT_PATTERNS = {
    "2Dゲーム":    ["pygame", "arcade", "phaser", "godot", "tilemap", "sprite", "player",
                    "enemy", "collision", "pygame_ce", "cocos2d", "love2d",
                    "tileset", "spritesheet", "scrolling", "platformer"],
    "3Dゲーム":    ["three.js", "unity", "unreal", "mesh", "shader", "rigidbody",
                    "physics3d", "blender", "opengl", "vulkan", "directx", "godot4",
                    "babylon.js", "playcanvas", "glb", "gltf", "collider3d"],
    "RPG":         ["rpgmaker", "encounter", "battle_system", "level_up",
                    "inventory", "quest", "npc_dialogue", "skill_tree", "party",
                    "savedata", "worldmap", "dungeon", "turn_based"],
    "アクション":  ["hitbox", "hurtbox", "knockback", "combo", "dash", "dodge",
                    "attack_animation", "boss_fight", "health_bar", "cooldown"],
    "パズル":      ["grid", "match3", "tetris", "puzzle", "hint_system",
                    "block", "rotate", "swap", "clear_condition"],
    "WebApp":      ["flask", "fastapi", "django", "express", "react", "vue", "router",
                    "api", "endpoint", "http", "rest", "graphql", "websocket"],
    "CLI":         ["argparse", "click", "typer", "sys.argv", "subprocess", "terminal"],
    "AIツール":    ["ollama", "openai", "anthropic", "langchain", "vector", "embedding",
                    "llm", "prompt", "chromadb", "rag", "transformer"],
    "データ処理":  ["pandas", "numpy", "dataframe", "matplotlib", "sklearn", "analysis"],
    "ライブラリ":  ["setup.py", "pyproject.toml", "__init__", "module", "package"],
}

_ENGINE_PATTERNS = {
    "Godot":    ["extends", "func _ready", "func _process", "@onready", "gdscript",
                 "node2d", "characterbody2d", "rigidbody", "area2d", "export var",
                 "signal", "emit_signal", "get_node"],
    "Pygame":   ["pygame.init", "pygame.display", "pygame.event", "pygame.draw",
                 "pygame.sprite", "pygame.mixer", "pygame.image", "pg.init",
                 "surface", "pygame.rect"],
    "Unity":    ["using unityengine", "monobehaviour", "getcomponent",
                 "gameobject", "transform", "instantiate"],
    "Phaser":   ["phaser.game", "this.physics", "this.add.sprite", "phaser.scene",
                 "preload()", "create()", "phaser.js"],
    "Three.js": ["three.scene", "three.camera", "three.renderer", "three.mesh",
                 "webglrenderer", "animationmixer"],
    "RPGMaker": ["game_actor", "game_map", "scene_", "$gamemap", "$gameparty",
                 "datamanager", "window_"],
}

_BINARY_EXT = frozenset({
    ".png",".jpg",".jpeg",".gif",".bmp",".webp",".svg",
    ".mp3",".wav",".ogg",".flac",".aac",".m4a",
    ".ttf",".otf",".woff",".woff2",
    ".zip",".tar",".gz",".7z",".rar",
    ".exe",".dll",".so",".dylib",
    ".mp4",".avi",".mov",
    ".blend",".fbx",".obj",".glb",".gltf",
})

_TEXT_EXT = frozenset({
    ".py",".gd",".js",".ts",".cs",".java",".cpp",".c",".h",".hpp",
    ".txt",".md",".rst",".log",
    ".json",".yaml",".yml",".toml",".ini",".cfg",".env",
    ".html",".css",".xml",".csv",".tsv",
    ".gdshader",".glsl",".hlsl",".vert",".frag",
    ".sh",".bat",".ps1",
    ".tscn",".tres",".res",
    ".tmx",".tsx",
})

_SKIP_DIRS = frozenset({
    ".git","__pycache__","node_modules","venv",".venv",
    "dist","build",".blackwell_cache",".godot","addons",
    "bin","obj",".vs",
})

_MAX_READ = 60_000


# ============================================================
# ファイル読み込み
# ============================================================

def _read_file(filepath):
    ext  = Path(filepath).suffix.lower()
    fname = Path(filepath).name
    if ext in _BINARY_EXT:
        try:
            size = os.path.getsize(filepath)
            return ("[バイナリ: {} / {:.1f}KB]".format(fname, size/1024), ext.lstrip("."), True)
        except Exception:
            return ("[バイナリ: {}]".format(fname), ext.lstrip("."), True)
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            return (f.read(_MAX_READ), ext.lstrip("."), False)
    except Exception as e:
        return ("[読み込み失敗: {}]".format(e), ext.lstrip("."), False)


def _read_upload(file_obj, filename):
    ext = Path(filename).suffix.lower()
    if ext in _BINARY_EXT:
        try:
            size = len(file_obj.getvalue())
            return ("[バイナリ: {} / {:.1f}KB]".format(filename, size/1024), ext.lstrip("."), True)
        except Exception:
            return ("[バイナリ: {}]".format(filename), ext.lstrip("."), True)
    try:
        raw = file_obj.read(_MAX_READ)
        content = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        return (content, ext.lstrip("."), False)
    except Exception as e:
        return ("[読み込み失敗: {}]".format(e), ext.lstrip("."), False)


# ============================================================
# 判定ロジック
# ============================================================

def detect_project_type(content, filename=""):
    haystack = content.lower() + " " + filename.lower()
    scores = {}
    matched = {}
    for ptype, kws in _PROJECT_PATTERNS.items():
        hits = [kw for kw in kws if kw in haystack]
        if hits:
            scores[ptype] = len(hits) * 10
            matched[ptype] = hits
    if not scores:
        return {"type": "汎用/不明", "confidence": 0, "keywords": [], "all_scores": {}}
    best  = max(scores, key=lambda k: scores[k])
    total = sum(scores.values())
    conf  = min(int(scores[best] / max(total, 1) * 100 + scores[best]), 99)
    return {"type": best, "confidence": conf, "keywords": matched[best], "all_scores": scores}


def detect_engine(content, filename=""):
    haystack = content.lower() + " " + filename.lower()
    best_e, best_s = "不明", 0
    for engine, patterns in _ENGINE_PATTERNS.items():
        score = sum(1 for p in patterns if p.lower() in haystack)
        if score > best_s:
            best_s, best_e = score, engine
    return best_e if best_s >= 2 else "不明"


def detect_dimension(content, filename=""):
    h = content.lower()
    s3 = sum(1 for k in ["3d","mesh","rigidbody3d","camera3d","vector3","glb","gltf",
                           "opengl","directx","three.js","babylon","unreal"] if k in h)
    s2 = sum(1 for k in ["2d","sprite","tilemap","characterbody2d","area2d","node2d",
                           "pygame","phaser","surface"] if k in h)
    if s3 > s2:   return "3D"
    if s2 > 0:    return "2D"
    return "不明"


def detect_game_elements(content):
    h = content.lower()
    element_map = {
        "プレイヤー":           ["player","hero","character","protagonist"],
        "敵・モンスター":        ["enemy","monster","mob","boss","creature"],
        "アイテム・武器":        ["item","weapon","sword","shield","potion","equip"],
        "マップ・ステージ":      ["tilemap","stage","level","dungeon","worldmap"],
        "バトルシステム":        ["battle","combat","attack","damage","hp","health"],
        "インベントリ":          ["inventory","bag","backpack","slot"],
        "クエスト・ストーリー":  ["quest","mission","story","dialogue","npc"],
        "スキル・魔法":          ["skill","magic","spell","ability","cast"],
        "セーブ・ロード":        ["save","load","savefile","savedata","checkpoint"],
        "スコア・実績":          ["score","achievement","highscore","ranking"],
        "物理エンジン":          ["physics","collision","gravity","velocity","force"],
        "アニメーション":        ["animation","animate","frame","keyframe","tween"],
        "UI・HUD":              ["hud","healthbar","minimap","_ui","ui_","interface"],
        "サウンド":              ["bgm","sfx","sound","audio","music","se_"],
        "パーティクル":          ["particle","effect","explosion","spark","trail"],
        "カメラ制御":            ["camera","viewport","follow","zoom"],
        "AI・行動制御":          ["pathfinding","state_machine","behavior_tree","patrol","chase"],
        "マルチプレイ":          ["multiplayer","network","sync","peer","host"],
    }
    return [elem for elem, kws in element_map.items() if any(kw in h for kw in kws)]


def detect_impl_patterns(content):
    h = content.lower()
    patterns = []
    if "state_machine" in h or ("state" in h and "transition" in h):
        patterns.append("ステートマシン")
    if "singleton" in h or "instance()" in h:
        patterns.append("シングルトン")
    if "signal" in h or "event_bus" in h or "observer" in h:
        patterns.append("イベント駆動/シグナル")
    if "async" in h or "await" in h or "coroutine" in h:
        patterns.append("非同期/コルーチン")
    if "pool" in h or "object_pool" in h:
        patterns.append("オブジェクトプール")
    if "a_star" in h or "astar" in h or "pathfind" in h:
        patterns.append("A*経路探索")
    if "shader" in h or "glsl" in h:
        patterns.append("カスタムシェーダー")
    if "ecs" in h or "entity_component" in h:
        patterns.append("ECSアーキテクチャ")
    if "tween" in h or "lerp" in h or "ease" in h:
        patterns.append("トゥイーンアニメーション")
    if "factory" in h or "create_" in h:
        patterns.append("ファクトリーパターン")
    return patterns


# ============================================================
# 構造解析
# ============================================================

def _parse_python(content):
    r = {"functions":[], "classes":[], "imports":[], "todos":[]}
    try:
        tree = _ast.parse(content)
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                r["functions"].append(node.name)
            elif isinstance(node, _ast.ClassDef):
                r["classes"].append(node.name)
            elif isinstance(node, _ast.Import):
                for a in node.names: r["imports"].append(a.name.split(".")[0])
            elif isinstance(node, _ast.ImportFrom):
                if node.module: r["imports"].append(node.module.split(".")[0])
    except SyntaxError:
        pass
    for m in re.finditer(r"#\s*(TODO|FIXME|HACK|NOTE|BUG)[:\s]+(.*)", content, re.I):
        r["todos"].append({"type": m.group(1).upper(), "text": m.group(2)[:80]})
    r["imports"] = list(set(r["imports"]))
    return r


def _parse_generic(content):
    r = {"functions":[], "classes":[], "imports":[], "todos":[]}
    seen = set()
    for pat in [r"func\s+(\w+)\s*\(", r"function\s+(\w+)\s*\(", r"def\s+(\w+)\s*\(",
                r"(?:public|private|protected|static)[\w\s]+\s+(\w+)\s*\("]:
        for m in re.finditer(pat, content):
            n = m.group(1)
            if n not in seen and len(n) > 1:
                r["functions"].append(n); seen.add(n)
    for m in re.finditer(r"(?:class|struct|interface)\s+(\w+)", content):
        r["classes"].append(m.group(1))
    for m in re.finditer(r"#\s*(TODO|FIXME|HACK|NOTE|BUG)[:\s]+(.*)", content, re.I):
        r["todos"].append({"type": m.group(1).upper(), "text": m.group(2)[:80]})
    return r


def _parse_json(content, filename):
    try:
        data = json.loads(content)
    except Exception:
        return {"json_type": "無効なJSON"}
    result = {"json_type": "汎用JSON"}
    if isinstance(data, dict):
        kl = {k.lower() for k in data}
        if kl & {"hp","mp","atk","def","level","exp","speed"}:
            result["json_type"] = "キャラクターパラメータ"
        elif kl & {"width","height","layers","tilesets","tilewidth"}:
            result["json_type"] = "マップデータ（Tiled）"
        elif kl & {"frames","animations","duration","framerate"}:
            result["json_type"] = "アニメーションデータ"
        elif kl & {"items","weapons","equipment","loot"}:
            result["json_type"] = "アイテムデータ"
        elif kl & {"dialogue","text","npc","story","lines"}:
            result["json_type"] = "ダイアログ/ストーリー"
        elif kl & {"config","settings","options","preferences"}:
            result["json_type"] = "設定ファイル"
        result["top_keys"] = list(data.keys())[:10]
    elif isinstance(data, list):
        result["array_length"] = len(data)
        if data and isinstance(data[0], dict):
            result["item_keys"] = list(data[0].keys())[:8]
    return result


def _parse_csv(content):
    try:
        rows = list(csv.reader(io.StringIO(content)))
        if not rows: return {}
        return {"headers": rows[0], "row_count": len(rows)-1,
                "col_count": len(rows[0]), "sample": rows[1:4]}
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# 素材分類
# ============================================================

def _classify_image_role(filename):
    fn = filename.lower()
    role_map = [
        (["player","hero","protagonist","char_0","pc_"],        "プレイヤースプライト"),
        (["enemy","mob","monster"],                              "敵スプライト"),
        (["boss"],                                               "ボススプライト"),
        (["npc","villager","townspeople"],                       "NPCスプライト"),
        (["tile","terrain","ground","floor","wall"],             "マップタイル"),
        (["bg","background","sky","back_","back0"],              "背景画像"),
        (["item","potion","sword","shield","weapon","armor"],    "アイテムアイコン"),
        (["skill","magic","spell","ability"],                    "スキルアイコン"),
        (["effect","fx","particle","explosion","hit_","spark"],  "エフェクト"),
        (["ui","hud","panel","frame","button","icon_ui"],        "UIパーツ"),
        (["portrait","face","bust"],                             "立ち絵・顔グラ"),
        (["map","worldmap","minimap"],                           "マップ画像"),
        (["logo","title","splash"],                              "タイトル・ロゴ"),
        (["cursor","pointer"],                                   "カーソル"),
        (["font","text"],                                        "フォント画像"),
    ]
    for kws, role in role_map:
        if any(k in fn for k in kws):
            return {"role": role, "category": "image"}
    return {"role": "汎用グラフィック", "category": "image"}


def _classify_audio_role(filename):
    fn = filename.lower()
    role_map = [
        (["bgm","music","theme","ost","loop"],              "BGM（ループ音楽）",  "audio_bgm"),
        (["battle","dungeon","boss_bgm"],                   "バトルBGM",          "audio_bgm"),
        (["title","menu_bgm"],                              "タイトルBGM",         "audio_bgm"),
        (["se_","sfx_","effect","hit","jump","shoot","swing"], "効果音（SE）",     "audio_se"),
        (["voice","vo_","talk","speech"],                   "ボイス",              "audio_se"),
        (["ambient","env","room","nature"],                  "環境音",              "audio_se"),
        (["jingle","fanfare","sting"],                       "ジングル",            "audio_se"),
    ]
    for kws, role, cat in role_map:
        if any(k in fn for k in kws):
            return {"role": role, "category": cat}
    return {"role": "汎用サウンド", "category": "audio_se"}


# ============================================================
# 学習ポイント生成
# ============================================================

def _generate_learning_points(ptype, engine, dimension, elements, patterns, struct, filename):
    pts = []
    if any(k in ptype for k in ["ゲーム", "RPG", "アクション", "パズル"]):
        if "プレイヤー" in elements:      pts.append("プレイヤー制御パターンを学習（{}）".format(engine))
        if "物理エンジン" in elements:    pts.append("物理演算・衝突検出の実装パターンを吸収")
        if "バトルシステム" in elements:  pts.append("バトルシステム設計を学習（ターン制/リアルタイム）")
        if "AI・行動制御" in elements:    pts.append("敵AIパターン（ステートマシン/経路探索）を習得")
        if "セーブ・ロード" in elements:  pts.append("セーブ/ロードシステムの設計を吸収")
    if engine == "Godot":   pts.append("GDScriptのシグナル・ノード構造を学習")
    elif engine == "Pygame": pts.append("Pygameのゲームループ・スプライトグループ管理を習得")
    elif engine == "Unity":  pts.append("C#/Unityコンポーネント設計を学習")
    elif engine == "Phaser": pts.append("Phaser3の物理エンジン統合パターンを習得")
    for p in patterns:       pts.append("実装パターン「{}」を知識DBに蓄積".format(p))
    if ptype == "WebApp":    pts.append("APIエンドポイント・ルーティング設計を習得")
    funcs = struct.get("functions", [])
    if len(funcs) > 10:      pts.append("大規模モジュール（関数{}個）のアーキテクチャを学習".format(len(funcs)))
    todos = struct.get("todos", [])
    if todos:                pts.append("TODO{}件: 未実装機能リストとして記録".format(len(todos)))
    if not pts:              pts.append("汎用コードパターンとして知識DBに蓄積")
    return pts


# ============================================================
# LLM深層解析
# ============================================================

def _llm_analyze(content, filename, ptype, engine):
    if not _OLLAMA_OK or len(content) < 50:
        return ""
    prompt = (
        "ファイル: {fname}  種別: {ptype}  エンジン: {engine}\n\n"
        "内容（先頭4000文字）:\n{content}\n\n"
        "以下を日本語・300文字以内で答えてください:\n"
        "1. このファイルが実装している機能（1行）\n"
        "2. 優れた設計・パターン（あれば1〜2点）\n"
        "3. 改善・追加できること（1〜2点）\n"
        "4. 類似プロジェクトに再利用できる知恵（1行）"
    ).format(fname=filename, ptype=ptype, engine=engine, content=content[:4000])
    try:
        res = _ollama.chat(model=_ANALYZER_MODEL,
                           messages=[{"role":"user","content":prompt}])
        return res["message"]["content"]
    except Exception as e:
        return "LLM解析スキップ: {}".format(e)


def _generate_suggestions(llm_summary, elements, patterns):
    suggestions = []
    if llm_summary:
        for line in llm_summary.splitlines():
            line = line.strip()
            if any(k in line for k in ["改善","追加","3.","4.","できる","すべき"]):
                suggestions.append(line)
    if "AI・行動制御" not in elements and "敵・モンスター" in elements:
        suggestions.append("💡 敵AIにステートマシンを追加するとリアルな挙動になります")
    if "セーブ・ロード" not in elements and "バトルシステム" in elements:
        suggestions.append("💡 セーブ/ロードシステムの追加を検討してください")
    if "オブジェクトプール" not in patterns and "パーティクル" in elements:
        suggestions.append("💡 パーティクルにオブジェクトプール適用でパフォーマンス改善")
    return suggestions[:5]


# ============================================================
# メイン解析関数 — analyze_any_file
# ============================================================

def analyze_any_file(filepath=None, file_obj=None, filename=""):
    """
    形式問わずファイルを解析して構造化された情報を返す。
    app.py から呼ばれるメイン関数。
    """
    if filepath:
        filename = filename or Path(filepath).name
        content, ext, is_binary = _read_file(filepath)
    elif file_obj is not None:
        content, ext, is_binary = _read_upload(file_obj, filename)
    else:
        return {"error": "ファイルが指定されていません"}

    result = {
        "filename":       filename,
        "extension":      ext,
        "is_binary":      is_binary,
        "project_type":   "不明",
        "engine":         "不明",
        "dimension":      "不明",
        "game_elements":  [],
        "patterns":       [],
        "functions":      [],
        "classes":        [],
        "imports":        [],
        "todos":          [],
        "json_analysis":  {},
        "csv_analysis":   {},
        "asset_info":     {},
        "learning_points":[],
        "suggestions":    [],
        "llm_summary":    "",
        "analyzed_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # バイナリ素材
    if is_binary:
        if ext in {"png","jpg","jpeg","gif","bmp","webp","svg"}:
            result["asset_info"] = _classify_image_role(filename)
        elif ext in {"mp3","wav","ogg","flac","aac","m4a"}:
            result["asset_info"] = _classify_audio_role(filename)
        elif ext in {"ttf","otf","woff","woff2"}:
            result["asset_info"] = {"role":"フォント素材","category":"font"}
        elif ext in {"glb","gltf","fbx","obj","blend"}:
            result["asset_info"] = {"role":"3Dモデル","category":"3d_model"}
            result["dimension"]  = "3D"
        else:
            result["asset_info"] = {"role":"バイナリ素材","category":"other"}
        result["learning_points"] = [
            "{}として認識・ゲーム生成時に素材候補として自動提案".format(
                result["asset_info"].get("role","素材"))
        ]
        return result

    # テキスト解析
    ptype_info = detect_project_type(content, filename)
    result["project_type"]  = ptype_info["type"]
    result["engine"]        = detect_engine(content, filename)
    result["dimension"]     = detect_dimension(content, filename)
    result["game_elements"] = detect_game_elements(content)
    result["patterns"]      = detect_impl_patterns(content)

    if ext == "py":
        struct = _parse_python(content)
    elif ext in {"gd","js","ts","cs","java","cpp","c","h"}:
        struct = _parse_generic(content)
    else:
        struct = {"functions":[],"classes":[],"imports":[],"todos":[]}

    result["functions"] = struct["functions"]
    result["classes"]   = struct["classes"]
    result["imports"]   = struct["imports"]
    result["todos"]     = struct["todos"]

    if ext == "json":
        result["json_analysis"] = _parse_json(content, filename)
        jt = result["json_analysis"].get("json_type","")
        if jt and result["project_type"] == "汎用/不明":
            result["project_type"] = "ゲームデータ"

    if ext in {"csv","tsv"}:
        result["csv_analysis"] = _parse_csv(content)

    if ext == "gd":
        result["engine"] = "Godot"

    if ext == "tscn":
        result["project_type"] = "Godotシーン"
        result["engine"] = "Godot"
        result["game_elements"] = list(set(re.findall(r'type="(\w+)"', content)[:10]))

    result["learning_points"] = _generate_learning_points(
        result["project_type"], result["engine"], result["dimension"],
        result["game_elements"], result["patterns"], struct, filename
    )

    if _OLLAMA_OK and len(content) > 100 and ext not in {"json","csv","tsv","yaml","yml"}:
        result["llm_summary"] = _llm_analyze(
            content, filename, result["project_type"], result["engine"])

    result["suggestions"] = _generate_suggestions(
        result["llm_summary"], result["game_elements"], result["patterns"])

    return result


# 後方互換
def analyze_file(filepath=None, file_obj=None, filename=""):
    return analyze_any_file(filepath=filepath, file_obj=file_obj, filename=filename)


# ============================================================
# 知識吸収
# ============================================================

def absorb_project_knowledge(analysis_result, project_name="", store_fn=None):
    _store = store_fn or (store_memory if _MEMORY_OK else None)
    if not _store:
        return "メモリシステム未接続"

    fname    = analysis_result.get("filename", "unknown")
    ptype    = analysis_result.get("project_type", "不明")
    engine   = analysis_result.get("engine", "不明")
    dim      = analysis_result.get("dimension", "不明")
    elements = analysis_result.get("game_elements", [])
    patterns = analysis_result.get("patterns", [])
    lp       = analysis_result.get("learning_points", [])
    summary  = analysis_result.get("llm_summary", "")
    asset    = analysis_result.get("asset_info", {})

    key = "analyzed_{}_{}".format(
        ptype.replace(" ","_"),
        hashlib.md5(fname.encode()).hexdigest()[:8]
    )
    body = (
        "【解析ファイル】{fname}\n"
        "【プロジェクト名】{pname}\n"
        "【種別】{ptype}  エンジン:{engine}  次元:{dim}\n"
        "【ゲーム要素】{elements}\n"
        "【実装パターン】{patterns}\n"
        "【学習ポイント】\n{lp}\n"
        "【素材情報】{asset}\n"
        "【AI分析】{summary}\n"
        "【記録日時】{ts}"
    ).format(
        fname=fname, pname=project_name or "不明",
        ptype=ptype, engine=engine, dim=dim,
        elements=", ".join(elements) if elements else "なし",
        patterns=", ".join(patterns) if patterns else "なし",
        lp="\n".join("  - "+p for p in lp),
        asset=json.dumps(asset, ensure_ascii=False) if asset else "なし",
        summary=summary[:500] if summary else "なし",
        ts=analysis_result.get("analyzed_at",""),
    )
    try:
        _store(key, body, {
            "type":"project_analysis", "project_type":ptype,
            "engine":engine, "filename":fname, "project_name":project_name,
        })
        return "✅ 知識を吸収: {} ({}/{})".format(fname, ptype, engine)
    except Exception as e:
        return "❌ 吸収失敗: {}".format(e)


# ============================================================
# プロジェクト全体一括吸収 — absorb_project
# ============================================================

def absorb_project(folder_path, store_fn=None, max_files=200):
    """
    フォルダ以下の全ファイルを解析して一括吸収。
    app.py の「一括学習」ボタンから呼ばれる。
    """
    _store = store_fn or (store_memory if _MEMORY_OK else None)

    result = {
        "total": 0,
        "dominant_type": "不明",
        "dominant_engine": "不明",
        "by_type": {},
        "by_engine": {},
        "game_features": [],
        "asset_map": {},
        "errors": [],
    }

    type_cnt    = {}
    engine_cnt  = {}
    all_features = set()
    amap = {
        "sprites":[], "tiles":[], "backgrounds":[], "ui":[],
        "effects":[], "audio_bgm":[], "audio_se":[],
        "data_json":[], "scripts":[], "3d_models":[], "other":[],
    }
    count = 0

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fname in files:
            if count >= max_files:
                break
            fpath = os.path.join(root, fname)
            rel   = os.path.relpath(fpath, folder_path)
            ext   = Path(fname).suffix.lower()
            if ext not in _TEXT_EXT and ext not in _BINARY_EXT:
                continue
            try:
                a = analyze_any_file(filepath=fpath, filename=fname)
                count += 1
                ptype  = a.get("project_type","不明")
                engine = a.get("engine","不明")
                type_cnt[ptype]     = type_cnt.get(ptype, 0) + 1
                engine_cnt[engine]  = engine_cnt.get(engine, 0) + 1
                all_features.update(a.get("game_elements",[]))
                all_features.update(a.get("patterns",[]))

                asset = a.get("asset_info",{})
                cat   = asset.get("category","")
                role  = asset.get("role","")
                if ext in {".py",".gd",".js",".ts",".cs"}:
                    amap["scripts"].append(rel)
                elif ext == ".json":
                    amap["data_json"].append(rel)
                elif cat == "image":
                    if any(k in role for k in ["プレイヤー","敵","ボス","NPC"]):
                        amap["sprites"].append(rel)
                    elif "タイル" in role:  amap["tiles"].append(rel)
                    elif "背景" in role:    amap["backgrounds"].append(rel)
                    elif "UI" in role:      amap["ui"].append(rel)
                    elif "エフェクト" in role: amap["effects"].append(rel)
                    else:                   amap["other"].append(rel)
                elif cat == "audio_bgm":   amap["audio_bgm"].append(rel)
                elif cat == "audio_se":    amap["audio_se"].append(rel)
                elif cat == "3d_model":    amap["3d_models"].append(rel)

                if _store and ptype not in ("不明","汎用/不明"):
                    absorb_project_knowledge(a, store_fn=_store)

            except Exception as e:
                result["errors"].append("{}: {}".format(rel, e))

    result["total"]         = count
    result["by_type"]       = type_cnt
    result["by_engine"]     = {k:v for k,v in engine_cnt.items() if k != "不明"}
    result["game_features"] = sorted(all_features)
    result["asset_map"]     = amap

    if type_cnt:
        result["dominant_type"]   = max(type_cnt,   key=lambda k: type_cnt[k])
    no_unk = {k:v for k,v in engine_cnt.items() if k != "不明"}
    if no_unk:
        result["dominant_engine"] = max(no_unk, key=lambda k: no_unk[k])

    # プロジェクトサマリーを保存
    if _store and count > 0:
        body = (
            "【プロジェクト全体解析】フォルダ: {folder}\n"
            "総ファイル数: {total}\n"
            "主要種別: {dt}  主要エンジン: {de}\n"
            "種別内訳: {bt}\n"
            "検出特徴: {feat}\n"
            "素材: スプライト{sp}個 BGM{bgm}個 SE{se}個 3Dモデル{m3}個"
        ).format(
            folder=folder_path, total=count,
            dt=result["dominant_type"], de=result["dominant_engine"],
            bt=json.dumps(type_cnt, ensure_ascii=False),
            feat=", ".join(sorted(all_features)[:20]),
            sp=len(amap["sprites"]), bgm=len(amap["audio_bgm"]),
            se=len(amap["audio_se"]), m3=len(amap["3d_models"]),
        )
        try:
            _store(
                "project_summary_{}".format(
                    hashlib.md5(folder_path.encode()).hexdigest()[:8]),
                body,
                {"type":"project_summary","folder":folder_path,
                 "dominant_type":result["dominant_type"]},
            )
        except Exception:
            pass

    return result


# ============================================================
# 類似プロジェクト参照 → オリジナル提案
# ============================================================

def suggest_from_similar(current_goal, project_type=""):
    """
    過去に学習した類似プロジェクトの知識から改善提案を生成。
    複数の良いパターンを統合してオリジナルに染め上げる。
    """
    if not _MEMORY_OK:
        return ""
    query = "{} {}".format(project_type, current_goal).strip()
    try:
        similar = retrieve_context(query, k=5)
        if not similar or not similar.strip():
            return ""
        if not _OLLAMA_OK:
            return "\n\n【📚 類似プロジェクトの知識】\n{}".format(similar[:1200])
        prompt = (
            "あなたはゲームおよびソフトウェア開発の専門家です。\n\n"
            "【現在のゴール】\n{goal}\n\n"
            "【過去に学習した類似プロジェクトの知識】\n{similar}\n\n"
            "これらを参考に日本語・箇条書きで答えてください（250文字以内）:\n"
            "✅ 採用すべき優れたパターン（2つ）\n"
            "❌ 避けるべき失敗・落とし穴（1つ）\n"
            "🔥 オリジナルに発展させるアイデア（1つ）\n"
            "→ 複数の良いものを融合してオリジナルに染め上げることを意識してください。"
        ).format(goal=current_goal[:400], similar=similar[:2500])
        res = _ollama.chat(model=_ANALYZER_MODEL,
                           messages=[{"role":"user","content":prompt}])
        return "\n\n【📚 類似プロジェクトからの学び・提案】\n{}".format(
            res["message"]["content"])
    except Exception:
        return ""


# ============================================================
# ゲーム素材フォルダスキャン
# ============================================================

def analyze_game_assets_folder(folder_path):
    """
    ゲーム素材フォルダを全スキャンして素材マップを生成。
    Blackwell がゲーム生成時に「どんな素材があるか」を把握するために使う。
    """
    amap = {
        "sprites":[], "tiles":[], "backgrounds":[], "ui":[],
        "effects":[], "audio_bgm":[], "audio_se":[],
        "data_json":[], "scripts":[], "3d_models":[], "other":[],
    }
    if not os.path.exists(folder_path):
        return {"error": "フォルダが見つかりません: {}".format(folder_path)}

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            fpath = os.path.join(root, fname)
            rel   = os.path.relpath(fpath, folder_path)
            ext   = Path(fname).suffix.lower()
            fnl   = fname.lower()

            if ext in {".png",".jpg",".jpeg",".gif",".bmp",".webp"}:
                info = _classify_image_role(fnl)
                role = info["role"]
                if any(k in role for k in ["プレイヤー","敵","ボス","NPC","スプライト"]):
                    amap["sprites"].append(rel)
                elif "タイル" in role:   amap["tiles"].append(rel)
                elif "背景" in role:     amap["backgrounds"].append(rel)
                elif "UI" in role:       amap["ui"].append(rel)
                elif "エフェクト" in role: amap["effects"].append(rel)
                else:                    amap["other"].append(rel)
            elif ext in {".mp3",".wav",".ogg",".flac",".aac"}:
                info = _classify_audio_role(fnl)
                if info["category"] == "audio_bgm": amap["audio_bgm"].append(rel)
                else:                               amap["audio_se"].append(rel)
            elif ext == ".json":   amap["data_json"].append(rel)
            elif ext in {".py",".gd",".js",".ts",".cs"}: amap["scripts"].append(rel)
            elif ext in {".glb",".gltf",".fbx",".obj",".blend"}: amap["3d_models"].append(rel)

    total = sum(len(v) for v in amap.values())
    amap["_summary"] = {
        "total_files":  total,
        "has_sprites":  len(amap["sprites"]) > 0,
        "has_audio":    (len(amap["audio_bgm"]) + len(amap["audio_se"])) > 0,
        "has_3d":       len(amap["3d_models"]) > 0,
        "has_game_data":len(amap["data_json"]) > 0,
        "sprite_count": len(amap["sprites"]),
        "bgm_count":    len(amap["audio_bgm"]),
        "se_count":     len(amap["audio_se"]),
        "model_count":  len(amap["3d_models"]),
    }
    return amap


# ============================================================
# 素材マップ → LLMコンテキスト生成
# ============================================================

def build_game_context_from_assets(asset_map, goal):
    """
    素材マップからゲーム生成用LLMコンテキストを生成。
    engine.py の _build_game_context() から呼ばれる。
    """
    if not asset_map or "error" in asset_map:
        return ""
    summary = asset_map.get("_summary", {})
    lines   = ["\n\n【🎮 利用可能なゲーム素材マップ】"]
    labels  = {
        "sprites":"🧍 スプライト", "tiles":"🧱 タイル",
        "backgrounds":"🌄 背景", "ui":"🖼 UI", "effects":"✨ エフェクト",
        "audio_bgm":"🎵 BGM", "audio_se":"🔊 SE",
        "data_json":"📄 ゲームデータ", "scripts":"📝 既存スクリプト",
        "3d_models":"🧊 3Dモデル",
    }
    for key, label in labels.items():
        files = asset_map.get(key, [])
        if not files: continue
        sample = ", ".join(Path(f).name for f in files[:6])
        suf    = " ...他{}件".format(len(files)-6) if len(files) > 6 else ""
        lines.append("  {}({}): {}{}".format(label, len(files), sample, suf))
    if summary.get("has_3d"):
        lines.append("  ⚠️ 3Dモデルあり → 3D対応コードを生成すること")
    lines.append("\n→ 上記の素材を最大限活用して「{}」を実装してください。".format(goal[:120]))
    lines.append("  素材ファイルのパスは相対パスをそのまま使用すること。")
    return "\n".join(lines)
