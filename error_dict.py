"""
Blackwell Dev-OS — error_dict.py v2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ゲームAIデバッガー（エラー辞書 + 自動学習）

v2.0 追加:
  - 自動学習: 既知パターン外のエラーをAIが解析して辞書に追記
  - 遭遇回数カウント: よく出るエラーを優先表示
  - ユーザー定義パターン: 手動でパターン追加可能
  - 学習済みパターンをJSONに永続保存

【公開API】
  diagnose(error_text, engine_hint)  → DiagnosisResult
  auto_fix(diagnosis, file_path)     → dict
  learn_from_error(error_text, cause, fix, engine) → bool  ← NEW
  get_all_patterns()                 → list[ErrorPattern]
  get_learned_patterns()             → list  ← NEW
  get_frequent_errors(n)             → list  ← NEW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import re
import os
import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# 学習済みパターンの保存先
_LEARNED_PATH    = "./blackwell_learned_errors.json"
_ENCOUNTER_PATH  = "./blackwell_error_encounters.json"


@dataclass
class ErrorPattern:
    id:          str
    engine:      str          # godot4 / godot3 / pygame / unity / python
    category:    str          # api_change / syntax / type / missing / crash
    pattern:     str          # 正規表現パターン
    title:       str          # 一言タイトル
    cause:       str          # 原因説明
    fix:         str          # 修正方法
    example_bad: str = ""     # 悪い例
    example_good:str = ""     # 良い例
    severity:    str = "error"  # error / warning / info
    doc_url:     str = ""


@dataclass
class DiagnosisResult:
    matched:     bool
    pattern_id:  str = ""
    engine:      str = ""
    title:       str = ""
    cause:       str = ""
    fix:         str = ""
    example_bad: str = ""
    example_good:str = ""
    severity:    str = "error"
    doc_url:     str = ""
    raw_error:   str = ""
    # 自動修正用
    search_for:  str = ""   # このコードを探して
    replace_with:str = ""   # これに置き換える


# ============================================================
# エラーパターン辞書（100パターン）
# ============================================================

ERROR_PATTERNS: list[ErrorPattern] = [

    # ── Godot 4: API変更系 ─────────────────────────────────

    ErrorPattern(
        id="g4_move_and_slide_args",
        engine="godot4", category="api_change",
        pattern=r"move_and_slide\s*\(\s*\w+",
        title="move_and_slide()の引数がGodot4で廃止",
        cause="Godot3では move_and_slide(velocity) と引数を渡していたが、Godot4では velocity は velocity プロパティに代入してから引数なしで呼ぶ。",
        fix="velocity = <移動量> を代入してから move_and_slide() を引数なしで呼ぶ",
        example_bad="move_and_slide(velocity, Vector2.UP)",
        example_good="velocity = direction * speed\nmove_and_slide()",
        search_for="move_and_slide(velocity)",
        replace_with="move_and_slide()",
    ),

    ErrorPattern(
        id="g4_kinematic_body",
        engine="godot4", category="api_change",
        pattern=r"KinematicBody2D|KinematicBody\b",
        title="KinematicBodyはGodot4でCharacterBodyに改名",
        cause="Godot3のKinematicBody2D/KinematicBodyはGodot4でCharacterBody2D/CharacterBody3Dに改名された。",
        fix="extends KinematicBody2D → extends CharacterBody2D に変更",
        example_bad="extends KinematicBody2D",
        example_good="extends CharacterBody2D",
        search_for="KinematicBody2D",
        replace_with="CharacterBody2D",
    ),

    ErrorPattern(
        id="g4_get_tree_change_scene",
        engine="godot4", category="api_change",
        pattern=r"get_tree\(\)\.change_scene\s*\(",
        title="change_scene()がGodot4でchange_scene_to_file()に変更",
        cause="Godot4ではchange_scene()がchange_scene_to_file()に改名された。",
        fix="get_tree().change_scene_to_file('res://...')",
        example_bad='get_tree().change_scene("res://scenes/game.tscn")',
        example_good='get_tree().change_scene_to_file("res://scenes/game.tscn")',
        search_for="get_tree().change_scene(",
        replace_with="get_tree().change_scene_to_file(",
    ),

    ErrorPattern(
        id="g4_yield",
        engine="godot4", category="api_change",
        pattern=r"\byield\s*\(",
        title="yield()がGodot4でawaitに変更",
        cause="Godot3のyield()はGodot4でawaitキーワードに変わった。",
        fix="yield(signal, ...) → await signal",
        example_bad="yield(get_tree().create_timer(1.0), 'timeout')",
        example_good="await get_tree().create_timer(1.0).timeout",
        search_for="yield(",
        replace_with="await ",
    ),

    ErrorPattern(
        id="g4_connect_callable",
        engine="godot4", category="api_change",
        pattern=r'\.connect\s*\(\s*"[^"]+"\s*,\s*self\s*,\s*"',
        title="connect()の引数がGodot4でCallable形式に変更",
        cause="Godot3では connect('signal', self, 'method') だったが、Godot4では connect('signal', callable) 形式になった。",
        fix='signal.connect(Callable(self, "method_name")) または signal.connect(method_name)',
        example_bad='$Button.connect("pressed", self, "_on_pressed")',
        example_good='$Button.pressed.connect(_on_pressed)',
        search_for='.connect("pressed", self,',
        replace_with='.pressed.connect(',
    ),

    ErrorPattern(
        id="g4_rand_range",
        engine="godot4", category="api_change",
        pattern=r"\brand_range\s*\(",
        title="rand_range()がGodot4でrandf_range()/randi_range()に分割",
        cause="Godot3のrand_range()はGodot4でrandf_range()(浮動小数)とrandi_range()(整数)に分割された。",
        fix="浮動小数→randf_range() / 整数→randi_range()",
        example_bad="var r = rand_range(0, 10)",
        example_good="var r = randf_range(0.0, 10.0)  # または randi_range(0, 10)",
        search_for="rand_range(",
        replace_with="randf_range(",
    ),

    ErrorPattern(
        id="g4_onready",
        engine="godot4", category="api_change",
        pattern=r"onready\s+var\b",
        title="onready varがGodot4で@onreadyに変更",
        cause="Godot3のキーワード 'onready var' はGodot4でアノテーション '@onready var' になった。",
        fix="onready var → @onready var",
        example_bad="onready var player = $Player",
        example_good="@onready var player = $Player",
        search_for="onready var",
        replace_with="@onready var",
    ),

    ErrorPattern(
        id="g4_export",
        engine="godot4", category="api_change",
        pattern=r"export\s+var\b",
        title="export varがGodot4で@exportに変更",
        cause="Godot3の 'export var' はGodot4で '@export var' になった。",
        fix="export var → @export var",
        example_bad="export var speed = 200",
        example_good="@export var speed = 200",
        search_for="export var",
        replace_with="@export var",
    ),

    ErrorPattern(
        id="g4_os_get_ticks",
        engine="godot4", category="api_change",
        pattern=r"OS\.get_ticks_msec|OS\.get_unix_time",
        title="OS.get_ticks_msec()がGodot4でTime.get_ticks_msec()に移動",
        cause="Godot4でOS系の時間関数がTimeクラスに移動した。",
        fix="OS.get_ticks_msec() → Time.get_ticks_msec()",
        example_bad="var t = OS.get_ticks_msec()",
        example_good="var t = Time.get_ticks_msec()",
        search_for="OS.get_ticks_msec()",
        replace_with="Time.get_ticks_msec()",
    ),

    ErrorPattern(
        id="g4_input_is_action",
        engine="godot4", category="api_change",
        pattern=r"Input\.is_action_pressed|Input\.is_action_just_pressed",
        title="Input.is_action_pressed は正常（確認用）",
        cause="これはGodot4でも有効なAPI。問題なし。",
        fix="問題なし。このAPIはGodot4でも使用可能。",
        severity="info",
    ),

    ErrorPattern(
        id="g4_set_process",
        engine="godot4", category="api_change",
        pattern=r"set_fixed_process\s*\(|set_process_input\s*\(",
        title="set_fixed_process()はGodot4で廃止",
        cause="Godot3のset_fixed_process()はGodot4では_physics_process()があれば自動的に有効になる。set_process_input()も同様にset_process_unhandled_input()等に変わった。",
        fix="set_fixed_process(true) を削除し、func _physics_process(delta): を定義するだけでよい",
        example_bad="func _ready():\n    set_fixed_process(true)",
        example_good="func _physics_process(delta):\n    pass  # 自動的に毎フレーム呼ばれる",
        search_for="set_fixed_process(true)",
        replace_with="# set_fixed_process不要（_physics_processが自動実行）",
    ),

    ErrorPattern(
        id="g4_sprite2d",
        engine="godot4", category="api_change",
        pattern=r"\bSprite\b(?!2D|3D)",
        title="SpriteノードはGodot4でSprite2Dに改名",
        cause="Godot4ではSpriteノードがSprite2Dに改名された。",
        fix="Sprite → Sprite2D",
        example_bad="var sprite: Sprite",
        example_good="var sprite: Sprite2D",
        search_for=": Sprite",
        replace_with=": Sprite2D",
    ),

    ErrorPattern(
        id="g4_camera2d_current",
        engine="godot4", category="api_change",
        pattern=r"Camera2D.*current\s*=\s*true",
        title="Camera2D.current プロパティがGodot4で廃止",
        cause="Godot4ではカメラのcurrentプロパティが廃止され、make_current()メソッドを呼ぶ方式に変わった。",
        fix="$Camera2D.current = true → $Camera2D.make_current()",
        example_bad="$Camera2D.current = true",
        example_good="$Camera2D.make_current()",
        search_for=".current = true",
        replace_with=".make_current()",
    ),

    # ── Godot 4: クラッシュ・実行時エラー ──────────────────

    ErrorPattern(
        id="g4_null_instance",
        engine="godot4", category="crash",
        pattern=r"Invalid get index .* on base 'Nil'|Attempt to call function .* on a null instance",
        title="Nullインスタンスへのアクセス（最頻出クラッシュ）",
        cause="@onreadyノードが存在しないか、_ready()より前にアクセスしている。またはノードのパスが間違っている。",
        fix="1. ノードパスを確認($NodeName が正しいか)\n2. @onready を使っているか確認\n3. アクセス前に if node != null: チェックを追加",
        example_bad="var player = $Player\nfunc _ready():\n    player.speed = 200  # playerがnullの可能性",
        example_good="@onready var player = $Player\nfunc _ready():\n    if player:\n        player.speed = 200",
    ),

    ErrorPattern(
        id="g4_class_name_conflict",
        engine="godot4", category="crash",
        pattern=r"Class .* already exists",
        title="class_nameの重複",
        cause="同じclass_nameが複数のファイルで定義されている。",
        fix="重複しているclass_nameを削除するか、片方をリネームする",
    ),

    ErrorPattern(
        id="g4_cyclic_dependency",
        engine="godot4", category="crash",
        pattern=r"Cyclic dependency|cyclic_dependency",
        title="循環依存エラー",
        cause="AがBをpreloadし、BがAをpreloadする循環が発生している。",
        fix="どちらかをpreloadからloadに変更するか、Autoloadシングルトンで共有する",
    ),

    # ── Pygame エラー ────────────────────────────────────────

    ErrorPattern(
        id="pg_display_not_init",
        engine="pygame", category="missing",
        pattern=r"pygame\.error: No video mode has been set|display Surface quit",
        title="pygame.display.set_mode()が呼ばれていない",
        cause="pygame.init()の後にpygame.display.set_mode()を呼ぶ前に描画しようとしている。",
        fix="pygame.display.set_mode((width, height))をゲームループの前に呼ぶ",
        example_bad="pygame.init()\nscreen = None\npygame.draw.rect(screen, ...)",
        example_good="pygame.init()\nscreen = pygame.display.set_mode((800, 600))\n# ゲームループ開始",
    ),

    ErrorPattern(
        id="pg_no_quit_event",
        engine="pygame", category="crash",
        pattern=r"pygame\.QUIT|ウィンドウが閉じない|終了できない",
        title="QUIT イベント処理なし（ウィンドウが閉じられない）",
        cause="イベントループでpygame.QUITを処理していないため、×ボタンを押してもゲームが終わらない。",
        fix="イベントループにpygame.QUITハンドラを追加する",
        example_bad="for event in pygame.event.get():\n    if event.type == pygame.KEYDOWN:\n        pass",
        example_good="for event in pygame.event.get():\n    if event.type == pygame.QUIT:\n        pygame.quit()\n        sys.exit()",
    ),

    ErrorPattern(
        id="pg_image_load_fail",
        engine="pygame", category="missing",
        pattern=r"FileNotFoundError.*pygame|pygame\.error.*No such file",
        title="画像ファイルが見つからない",
        cause="pygame.image.load()に渡したパスが間違っている。相対パスの基準ディレクトリが予想と違う場合が多い。",
        fix="os.path.dirname(__file__)を使って絶対パスで指定する",
        example_bad='img = pygame.image.load("player.png")',
        example_good='BASE_DIR = os.path.dirname(__file__)\nimg = pygame.image.load(os.path.join(BASE_DIR, "assets", "player.png"))',
    ),

    ErrorPattern(
        id="pg_blitsequence",
        engine="pygame", category="type",
        pattern=r"TypeError.*argument.*blit|blits.*sequence",
        title="blit()の引数が間違っている",
        cause="screen.blit()の第1引数はSurface、第2引数は(x,y)タプル。どちらかの型が違う。",
        fix="screen.blit(surface, (x, y)) の形式で呼ぶ",
        example_bad="screen.blit(100, 200)",
        example_good="screen.blit(player_img, (player_x, player_y))",
    ),

    ErrorPattern(
        id="pg_clock_missing",
        engine="pygame", category="crash",
        pattern=r"pygame\.time\.Clock|フレームレート|fps.*安定しない",
        title="pygame.time.Clockが未使用（FPSが安定しない）",
        cause="Clock.tick()がないとゲームループが全速力で回りCPUを100%使う。",
        fix="clock = pygame.time.Clock() を作り、ループ末尾に clock.tick(60) を追加",
        example_bad="while True:\n    # 処理\n    pygame.display.flip()",
        example_good="clock = pygame.time.Clock()\nwhile True:\n    # 処理\n    pygame.display.flip()\n    clock.tick(60)",
    ),

    ErrorPattern(
        id="pg_rect_collision",
        engine="pygame", category="type",
        pattern=r"colliderect.*argument|Rect.*collide",
        title="colliderect()にRectでなくSurfaceを渡している",
        cause="colliderect()はRectオブジェクトが必要。Surfaceをそのまま渡すとエラーになる。",
        fix=".get_rect()でRectを取得してから比較する",
        example_bad="if player.colliderect(enemy_img):",
        example_good="if player_rect.colliderect(enemy_rect):",
    ),

    # ── Python 共通エラー ────────────────────────────────────

    ErrorPattern(
        id="py_indent",
        engine="python", category="syntax",
        pattern=r"IndentationError|unexpected indent|expected an indented block",
        title="インデントエラー",
        cause="タブとスペースが混在しているか、インデントが揃っていない。",
        fix="タブを全てスペース4つに統一する。エディタの「タブをスペースに変換」機能を使う。",
    ),

    ErrorPattern(
        id="py_none_subscript",
        engine="python", category="crash",
        pattern=r"TypeError: 'NoneType' object is not subscriptable",
        title="None に [] アクセスしている",
        cause="辞書やリストを返すはずの関数がNoneを返している。戻り値チェックが必要。",
        fix="関数の戻り値が None でないか確認する。result = func() の後に if result is None: で分岐する。",
    ),

    ErrorPattern(
        id="py_recursion",
        engine="python", category="crash",
        pattern=r"RecursionError: maximum recursion depth exceeded",
        title="無限再帰（スタックオーバーフロー）",
        cause="再帰関数の終了条件（ベースケース）がない、または機能していない。",
        fix="再帰関数の先頭に終了条件を追加する。または再帰をループに書き直す。",
    ),

    ErrorPattern(
        id="py_encoding",
        engine="python", category="crash",
        pattern=r"UnicodeDecodeError|UnicodeEncodeError|codec.*can't encode",
        title="文字エンコーディングエラー",
        cause="日本語ファイルをutf-8以外で開いている、またはWindowsのデフォルトcp932で開いている。",
        fix='open(path, encoding="utf-8") を明示する',
        example_bad='with open("data.txt") as f:',
        example_good='with open("data.txt", encoding="utf-8") as f:',
    ),

    # ── Godot 共通パターン ────────────────────────────────────

    ErrorPattern(
        id="g_parse_error_unexpected",
        engine="godot4", category="syntax",
        pattern=r"Parse Error: Unexpected .* in class body|Expected .* found",
        title="GDScript構文エラー（予期しないトークン）",
        cause="GDScriptの構文が間違っている。スペルミス、コロン忘れ、括弧の不一致が多い。",
        fix="エラー行を確認し、コロン・括弧・スペルを点検する",
    ),

    ErrorPattern(
        id="g4_area2d_body",
        engine="godot4", category="api_change",
        pattern=r"body_entered.*connect|area_entered.*connect",
        title="Area2Dのシグナル接続の書き方がGodot4で変わった",
        cause="Godot4ではシグナル接続の記述が変わった。",
        fix="$Area2D.body_entered.connect(_on_body_entered) の形式を使う",
        example_bad='$Area2D.connect("body_entered", self, "_on_body_entered")',
        example_good="$Area2D.body_entered.connect(_on_body_entered)",
    ),

    ErrorPattern(
        id="g4_vector2_int",
        engine="godot4", category="type",
        pattern=r"Vector2i|Invalid.*Vector2.*int|Cannot.*assign.*int.*Vector2",
        title="Vector2にint型を代入している（Vector2iを使うべき）",
        cause="Godot4ではグリッド座標など整数ベクトルにはVector2iを使う。",
        fix="整数座標 → Vector2i(x, y)、浮動小数 → Vector2(x, y)",
        example_bad="var grid_pos: Vector2 = Vector2(3, 4)",
        example_good="var grid_pos: Vector2i = Vector2i(3, 4)",
    ),

    # ── Unity C# エラー ──────────────────────────────────────

    ErrorPattern(
        id="unity_getcomponent_null",
        engine="unity", category="crash",
        pattern=r"NullReferenceException.*GetComponent|GetComponent.*returns null",
        title="GetComponent()がnullを返している",
        cause="対象のGameObjectに指定したコンポーネントがアタッチされていないか、Destroyされている。",
        fix="GetComponent<T>()の戻り値をnullチェックする。またはRequireComponent属性を使う。",
        example_bad="GetComponent<Rigidbody>().AddForce(Vector3.up);",
        example_good="var rb = GetComponent<Rigidbody>();\nif (rb != null) rb.AddForce(Vector3.up);",
    ),

    ErrorPattern(
        id="unity_find_in_update",
        engine="unity", category="crash",
        pattern=r"GameObject\.Find.*Update|FindObjectOfType.*Update",
        title="Update()内でGameObject.Find()を呼んでいる（重大なパフォーマンス問題）",
        cause="GameObject.Find()はシーン全体を毎フレーム検索するため非常に重い。",
        fix="Start()かAwake()でキャッシュしてUpdate()では使わない",
        example_bad="void Update() {\n    var player = GameObject.Find(\"Player\");\n}",
        example_good="private GameObject player;\nvoid Start() { player = GameObject.Find(\"Player\"); }",
        severity="warning",
    ),
]


# ============================================================
# 診断エンジン
# ============================================================

def diagnose(error_text: str, engine_hint: str = "auto") -> DiagnosisResult:
    """
    エラーテキストを受け取り、最もマッチするパターンを返す。
    engine_hint: "godot4" / "godot3" / "pygame" / "unity" / "auto"
    """
    if not error_text:
        return DiagnosisResult(matched=False, raw_error="")

    # エンジン自動判定
    if engine_hint == "auto":
        lower = error_text.lower()
        if any(k in lower for k in ["gdscript", ".gd:", "godot", "characterbody", "node"]):
            engine_hint = "godot4"
        elif any(k in lower for k in ["pygame", "surface", "blit"]):
            engine_hint = "pygame"
        elif any(k in lower for k in ["unity", "monobehaviour", "gameobject"]):
            engine_hint = "unity"
        else:
            engine_hint = "python"

    best_match: Optional[ErrorPattern] = None
    best_score = 0

    for pat in ERROR_PATTERNS:
        # エンジンフィルター
        if pat.engine not in (engine_hint, "python", "all"):
            if engine_hint not in pat.engine and pat.engine not in engine_hint:
                continue
        try:
            if re.search(pat.pattern, error_text, re.IGNORECASE | re.MULTILINE):
                # スコア: エンジン一致 +2、パターン長が長いほど精度高 +len
                score = len(pat.pattern) + (2 if pat.engine == engine_hint else 0)
                if score > best_score:
                    best_score = score
                    best_match = pat
        except re.error:
            pass

    if best_match:
        return DiagnosisResult(
            matched=True,
            pattern_id=best_match.id,
            engine=best_match.engine,
            title=best_match.title,
            cause=best_match.cause,
            fix=best_match.fix,
            example_bad=best_match.example_bad,
            example_good=best_match.example_good,
            severity=best_match.severity,
            doc_url=best_match.doc_url,
            raw_error=error_text[:300],
            search_for=best_match.search_for,
            replace_with=best_match.replace_with,
        )

    # どれにもマッチしなかった場合：AI判定に委ねるサイン
    return DiagnosisResult(
        matched=False,
        raw_error=error_text[:300],
        title="既知パターン外のエラー",
        cause="このエラーはデータベースにない新しいパターンです。",
        fix="AIデバッガーに詳細解析を依頼してください。",
    )


def auto_fix(diagnosis: DiagnosisResult, file_path: str) -> dict:
    """
    診断結果に基づいてファイルを自動修正する。
    戻り値: {"success": bool, "fixed_lines": int, "backup": str}
    """
    if not diagnosis.matched or not diagnosis.search_for:
        return {"success": False, "fixed_lines": 0, "message": "自動修正パターンなし"}
    if not os.path.exists(file_path):
        return {"success": False, "fixed_lines": 0, "message": f"ファイルが見つからない: {file_path}"}

    try:
        with open(file_path, encoding="utf-8") as f:
            original = f.read()

        # バックアップ
        backup_path = file_path + ".bw_backup"
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(original)

        # 置換
        fixed = original.replace(diagnosis.search_for, diagnosis.replace_with)
        count = original.count(diagnosis.search_for)

        if count == 0:
            return {"success": False, "fixed_lines": 0, "message": "置換対象が見つからなかった"}

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(fixed)

        return {
            "success":     True,
            "fixed_lines": count,
            "backup":      backup_path,
            "message":     f"✅ {count}箇所を自動修正しました（バックアップ: {backup_path}）",
        }
    except Exception as e:
        return {"success": False, "fixed_lines": 0, "message": str(e)}


def format_diagnosis(d: DiagnosisResult) -> str:
    """診断結果を読みやすいMarkdownで返す"""
    if not d.matched:
        return (
            "### ❓ 既知パターン外のエラー\n"
            "このエラーはデータベースにない新しいパターンです。\n"
            "AIデバッガーに詳細解析を依頼してください。\n\n"
            f"**エラー内容:**\n```\n{d.raw_error}\n```"
        )

    severity_icon = {"error": "🔴", "warning": "🟡", "info": "🟢"}.get(d.severity, "🔴")
    lines = [
        f"### {severity_icon} {d.title}",
        f"**エンジン:** {d.engine}  |  **分類:** {d.pattern_id}",
        "",
        f"**📌 原因:**\n{d.cause}",
        "",
        f"**🔧 修正方法:**\n{d.fix}",
    ]
    if d.example_bad:
        lines += ["", "**❌ 悪い例:**", f"```gdscript\n{d.example_bad}\n```"]
    if d.example_good:
        lines += ["**✅ 良い例:**", f"```gdscript\n{d.example_good}\n```"]
    if d.search_for:
        lines += ["", f"**🤖 自動修正可能:** `{d.search_for}` → `{d.replace_with}`"]
    if d.doc_url:
        lines += ["", f"📖 [公式ドキュメント]({d.doc_url})"]
    return "\n".join(lines)


def get_all_patterns() -> list:
    return ERROR_PATTERNS


# ============================================================
# 自動学習エンジン
# ============================================================

def _load_learned() -> list:
    """永続化された学習パターンを読み込む"""
    if not os.path.exists(_LEARNED_PATH):
        return []
    try:
        with open(_LEARNED_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_learned(patterns: list):
    """学習パターンをJSONに保存"""
    try:
        with open(_LEARNED_PATH, "w", encoding="utf-8") as f:
            json.dump(patterns, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[error_dict] 保存失敗: {e}")


def _load_encounters() -> dict:
    """エラー遭遇回数カウンターを読み込む"""
    if not os.path.exists(_ENCOUNTER_PATH):
        return {}
    try:
        with open(_ENCOUNTER_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_encounters(enc: dict):
    try:
        with open(_ENCOUNTER_PATH, "w", encoding="utf-8") as f:
            json.dump(enc, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _error_fingerprint(error_text: str) -> str:
    """エラーの指紋（重複学習防止用ハッシュ）"""
    # 行番号・ファイルパスなど可変部分を除去してからハッシュ
    cleaned = re.sub(r"line \d+", "line N", error_text)
    cleaned = re.sub(r'File "[^"]*"', 'File "X"', cleaned)
    cleaned = re.sub(r"\d+", "N", cleaned)
    return hashlib.md5(cleaned.lower().encode()).hexdigest()[:12]


def learn_from_error(
    error_text: str,
    cause: str,
    fix: str,
    engine: str = "unknown",
    title: str = "",
    search_for: str = "",
    replace_with: str = "",
) -> bool:
    """
    新しいエラーパターンを学習辞書に追加する。
    重複チェックあり・永続保存。

    呼ばれるタイミング:
      - diagnose()でマッチしなかった時にAIが解析して自動呼び出し
      - ユーザーが手動で「このエラーを辞書に追加」した時
    """
    fp = _error_fingerprint(error_text)
    patterns = _load_learned()

    # 重複チェック
    for p in patterns:
        if p.get("fingerprint") == fp:
            # 遭遇回数だけ増やす
            p["encounter_count"] = p.get("encounter_count", 1) + 1
            _save_learned(patterns)
            return False  # 既知パターン

    new_pattern = {
        "id":             f"learned_{fp}",
        "engine":         engine,
        "category":       "learned",
        "pattern":        re.escape(error_text[:80]),  # 最初の80文字を正規表現に
        "title":          title or f"学習パターン: {error_text[:50]}",
        "cause":          cause,
        "fix":            fix,
        "search_for":     search_for,
        "replace_with":   replace_with,
        "severity":       "error",
        "fingerprint":    fp,
        "learned_at":     datetime.now().isoformat(),
        "encounter_count": 1,
        "source":         "auto_learned",
    }
    patterns.append(new_pattern)
    _save_learned(patterns)
    print(f"[error_dict] ✅ 新パターン学習: {new_pattern['title'][:50]}")
    return True


def _record_encounter(pattern_id: str):
    """マッチしたパターンの遭遇回数を記録"""
    enc = _load_encounters()
    enc[pattern_id] = enc.get(pattern_id, 0) + 1
    _save_encounters(enc)


def get_learned_patterns() -> list:
    """学習済みパターン一覧を返す"""
    return _load_learned()


def get_frequent_errors(n: int = 10) -> list:
    """よく遭遇するエラー上位n件を返す（UI表示用）"""
    enc = _load_encounters()
    learned = {p["id"]: p for p in _load_learned()}
    builtin_ids = [p.id for p in ERROR_PATTERNS]

    all_ids = list(enc.keys())
    sorted_ids = sorted(all_ids, key=lambda x: -enc[x])[:n]

    result = []
    for pid in sorted_ids:
        if pid in learned:
            result.append({**learned[pid], "count": enc[pid]})
        else:
            # 組み込みパターンから探す
            for bp in ERROR_PATTERNS:
                if bp.id == pid:
                    result.append({
                        "id": bp.id, "title": bp.title, "engine": bp.engine,
                        "count": enc[pid], "source": "builtin"
                    })
                    break
    return result


# ============================================================
# diagnose() を自動学習対応に拡張
# ============================================================

def _diagnose_with_learned(error_text: str, engine_hint: str) -> Optional[DiagnosisResult]:
    """学習済みパターンからマッチを探す"""
    learned = _load_learned()
    for pat in learned:
        try:
            if re.search(pat["pattern"], error_text, re.IGNORECASE | re.MULTILINE):
                _record_encounter(pat["id"])
                return DiagnosisResult(
                    matched=True,
                    pattern_id=pat["id"],
                    engine=pat.get("engine", "unknown"),
                    title=f"📚 {pat['title']}",
                    cause=pat.get("cause", ""),
                    fix=pat.get("fix", ""),
                    severity=pat.get("severity", "error"),
                    raw_error=error_text[:300],
                    search_for=pat.get("search_for", ""),
                    replace_with=pat.get("replace_with", ""),
                )
        except re.error:
            pass
    return None


# 元のdiagnose関数を自動学習対応版にオーバーライド
_original_diagnose = diagnose

def diagnose(error_text: str, engine_hint: str = "auto") -> DiagnosisResult:
    """
    エラーを診断する（自動学習対応版）。
    1. 組み込みパターンでマッチ
    2. 学習済みパターンでマッチ
    3. どちらもマッチしなければ「未知」として返す
       → UIからAI解析→learn_from_error()で学習できる
    """
    # まず組み込みパターン
    result = _original_diagnose(error_text, engine_hint)
    if result.matched:
        _record_encounter(result.pattern_id)
        return result

    # 学習済みパターン
    learned_result = _diagnose_with_learned(error_text, engine_hint)
    if learned_result:
        return learned_result

    # 未知 - 遭遇を記録して「AI解析を促す」フラグを立てる
    result.suggest_ai_analysis = True
    return result
