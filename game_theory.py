"""
Blackwell Dev-OS — game_theory.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ゲーム面白さ理論エンジン

【収録理論】
  MDA理論  : Mechanics→Dynamics→Aesthetics
  フロー理論: チャレンジ≒スキルで「ゾーン」に入る
  フィーリングスライダー: 抽象的な感覚→パラメータ自動変換
  AIプレイテスト: ヘッドレス実行でバグ・詰まりを自動発見

【engine.py / app.py から呼ばれる関数】
  get_mda_context(genre, goal) → str          ← プロンプト注入
  apply_feeling_slider(sliders, engine) → dict ← パラメータ変換
  analyze_flow(game_desc, difficulty) → str   ← フロー診断
  generate_playtest_script(code, engine) → str ← AIプレイスクリプト
  get_fun_theory_prompt(genre) → str          ← コーダーに注入
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from dataclasses import dataclass, field
from typing import Optional

# ============================================================
# MDA理論データベース
# ============================================================

MDA_DATABASE = {
    "2daction": {
        "mechanics": [
            "移動（水平・垂直）","ジャンプ（単段・二段・壁ジャンプ）",
            "攻撃（近接・遠距離・範囲）","回避・ダッシュ","衝突判定",
            "プラットフォーム着地","慣性・加速度",
        ],
        "dynamics": [
            "リズム感（ジャンプ→攻撃→着地の連鎖）",
            "緊張と解放（難しい場面→突破→爽快感）",
            "探索欲求（隠し通路・秘密エリア）",
            "コンボの連続性（攻撃が繋がり続ける快感）",
        ],
        "aesthetics": [
            "爽快感（スピード・コンボ）",
            "達成感（難所クリア）",
            "発見の喜び（隠し要素）",
            "没入感（世界観への引き込み）",
        ],
        "flow_curve": "序盤=優しく操作を覚える→中盤=スキルが試される→終盤=全要素の組み合わせ",
        "fun_principle": "「一歩の重み」— 着地の振動・ジャンプの頂点停止・攻撃時のヒットストップが爽快感の9割を決める",
    },
    "roguelike": {
        "mechanics": [
            "ターン制移動","ランダムダンジョン生成","アイテム識別",
            "空腹度","永続死（パーマデス）","スタック可能な状態異常",
        ],
        "dynamics": [
            "リスクとリターンの天秤（未識別アイテムを使うか）",
            "リソース管理の緊張感（残り食料・MP）",
            "死から学ぶ成長（次こそは）",
            "シナジーの発見（アイテム組み合わせの驚き）",
        ],
        "aesthetics": [
            "緊張感（死の恐怖）",
            "知的充実感（最適解の探索）",
            "偶然の面白さ（ドロップ運）",
            "リプレイ性（毎回違う展開）",
        ],
        "flow_curve": "慎重なプレイ→リソース枯渇→リスクを取る判断→成功か死→学習のループ",
        "fun_principle": "「知識の積み重ね」— プレイヤーが「これを知っていれば死なかった」と思い続ける設計が肝",
    },
    "simulation": {
        "mechanics": [
            "グリッド配置","資源収支計算","人口AI",
            "建物の連鎖効果","時間進行（一時停止可）","イベント発生",
        ],
        "dynamics": [
            "バランスの崩壊と再建（赤字→回復の物語）",
            "意外な連鎖（道路を引いたら人口が爆発的に増えた）",
            "長期計画と即興対応の組み合わせ",
        ],
        "aesthetics": [
            "達成感（都市が成長する様子）",
            "支配感（世界を設計する全能感）",
            "好奇心（どうなるか試したい）",
        ],
        "flow_curve": "序盤=資源確保に必死→中盤=余裕が生まれ拡張→終盤=複雑な管理との戦い",
        "fun_principle": "「小さな変化が大きな結果を生む」— 1軒の病院が周辺の地価を上げ、人口を増やし、税収を上げる連鎖",
    },
    "towerdefense": {
        "mechanics": [
            "タワー配置（コスト管理）","敵ウェーブ進行",
            "射程・攻撃速度・ダメージの三角形","アップグレードツリー",
            "ゴールドリソース管理",
        ],
        "dynamics": [
            "最適配置の発見（ここに置けば全部倒せる！）",
            "ウェーブの読み合い（次は何が来るか）",
            "タワーシナジー（スローと範囲の組み合わせ）",
        ],
        "aesthetics": [
            "戦略的充実感（完璧な配置）",
            "緊張感（拠点HPが削られていく）",
            "爽快感（大量の敵を一掃）",
        ],
        "flow_curve": "序盤=シンプルな配置→中盤=複合シナジーの発見→終盤=リソース計算との戦い",
        "fun_principle": "「一手先を読む」— プレイヤーが「次のウェーブに備えてアップグレードするか、今の配置を増やすか」で常に悩む状態を維持する",
    },
    "3daction": {
        "mechanics": [
            "三人称移動・カメラ制御","ロックオン","コンボシステム",
            "スタミナ管理","回避（無敵フレーム）","武器切替",
        ],
        "dynamics": [
            "攻防の読み合い（敵の予備動作→回避→反撃）",
            "スタミナの緊張感（使い過ぎると隙になる）",
            "ボス戦のフェーズ変化（第二形態への驚き）",
        ],
        "aesthetics": [
            "爽快感（コンボの連続）",
            "緊張と安堵（ボス討伐）",
            "没入感（3D世界の臨場感）",
            "成長実感（難ボスを倒せるようになる）",
        ],
        "flow_curve": "雑魚=コンボ練習→中ボス=本番テスト→大ボス=総決算",
        "fun_principle": "「無敵フレームと予備動作の設計」— プレイヤーが「見てから避けられる」と感じる絶妙な猶予時間が全て",
    },
}


# ============================================================
# フィーリングスライダー定義
# ============================================================

@dataclass
class FeelingSliders:
    """抽象的な感覚→具体パラメータの変換マップ"""
    # 0.0〜1.0 のスライダー値
    heaviness:    float = 0.5   # 重厚感（0=軽快 1=ズッシリ）
    excitement:   float = 0.5   # 爽快感（0=淡々 1=超爽快）
    tension:      float = 0.5   # 緊張感（0=ゆるゆる 1=ヒリヒリ）
    fantasy:      float = 0.5   # 幻想感（0=リアル 1=ファンタジー）
    difficulty:   float = 0.5   # 難易度（0=超易 1=超難）
    tempo:        float = 0.5   # テンポ（0=ゆっくり 1=高速）


def apply_feeling_slider(sliders: FeelingSliders, engine: str = "godot", genre: str = "2daction") -> dict:
    """
    フィーリングスライダーの値を具体的なゲームパラメータに変換。
    CursorやSonnetには絶対できない：「重厚感」→数値への自動変換。
    """
    h = sliders.heaviness
    e = sliders.excitement
    t = sliders.tension
    f = sliders.fantasy
    d = sliders.difficulty
    tp = sliders.tempo

    params = {
        # 物理パラメータ
        "player_speed":        _lerp(3.0, 8.0, tp) * _lerp(1.2, 0.8, h),
        "player_gravity":      _lerp(400, 1200, h),
        "player_jump_power":   _lerp(-400, -900, h * 0.3 + e * 0.7),
        "player_friction":     _lerp(0.95, 0.7, tp),    # 高テンポ=低摩擦=滑る
        "player_acceleration": _lerp(0.3, 0.9, tp),

        # 戦闘パラメータ
        "hit_stop_frames":     int(_lerp(0, 12, h * 0.5 + e * 0.5)),   # ヒットストップ
        "attack_speed_mult":   _lerp(0.6, 1.5, tp),
        "knockback_force":     _lerp(100, 600, h),
        "iframes_on_hit":      int(_lerp(10, 40, d * 0.5 + 0.2)),      # 無敵フレーム

        # カメラパラメータ
        "camera_shake_intensity": _lerp(0.0, 15.0, h * 0.4 + e * 0.6),
        "camera_zoom":            _lerp(1.2, 0.85, h),   # 重いほど寄る
        "camera_smoothing":       _lerp(0.05, 0.2, tp),  # 高テンポ=追従速い

        # エフェクト
        "particle_scale":      _lerp(0.5, 3.0, e),
        "particle_count":      int(_lerp(5, 50, e)),
        "se_pitch_variance":   _lerp(0.0, 0.3, f),       # 幻想感=音に揺らぎ

        # 難易度
        "enemy_speed_mult":    _lerp(0.6, 1.4, d),
        "enemy_damage_mult":   _lerp(0.5, 2.0, d),
        "item_spawn_rate":     _lerp(0.3, 0.05, d),      # 高難度=アイテム減

        # BGMテンポ提案
        "bgm_bpm_target":      int(_lerp(70, 180, tp * 0.6 + e * 0.4)),
        "bgm_volume":          _lerp(0.5, 0.9, t),       # 緊張感=BGM大きめ
    }

    # エンジン別コードスニペット生成
    params["code_snippet"] = _gen_feeling_code(params, engine, genre)
    params["description"]  = _describe_feeling(sliders)

    return params


def _lerp(a: float, b: float, t: float) -> float:
    """線形補間: t=0→a, t=1→b"""
    return a + (b - a) * max(0.0, min(1.0, t))


def _describe_feeling(s: FeelingSliders) -> str:
    """スライダー値を日本語で説明"""
    parts = []
    if s.heaviness > 0.7:   parts.append("ズッシリした重厚感")
    elif s.heaviness < 0.3: parts.append("軽快でキビキビした動き")
    if s.excitement > 0.7:  parts.append("爆発的な爽快感")
    elif s.excitement < 0.3:parts.append("落ち着いた渋い感触")
    if s.tension > 0.7:     parts.append("ヒリヒリする緊張感")
    if s.fantasy > 0.7:     parts.append("ファンタジー色の強い演出")
    if s.difficulty > 0.7:  parts.append("歯応えのある高難度")
    elif s.difficulty < 0.3:parts.append("誰でも楽しめる易しさ")
    if s.tempo > 0.7:       parts.append("高速テンポの展開")
    elif s.tempo < 0.3:     parts.append("ゆったりしたペース")
    return "、".join(parts) if parts else "バランスの取れた標準設定"


def _gen_feeling_code(params: dict, engine: str, genre: str) -> str:
    """フィーリングパラメータをエンジン別コードに変換"""
    if engine == "godot":
        return f"""# ── フィーリングスライダー適用値（Godot 4） ──
const PLAYER_SPEED      = {params['player_speed']:.1f}
const GRAVITY           = {params['player_gravity']:.0f}
const JUMP_VELOCITY     = {params['player_jump_power']:.0f}
const FRICTION          = {params['player_friction']:.2f}
const HIT_STOP_FRAMES   = {params['hit_stop_frames']}     # ヒットストップ（0=なし）
const KNOCKBACK_FORCE   = {params['knockback_force']:.0f}
const CAMERA_SHAKE      = {params['camera_shake_intensity']:.1f}
const PARTICLE_COUNT    = {params['particle_count']}
# 敵パラメータ（難易度: {params['enemy_speed_mult']:.1f}倍速）
const ENEMY_SPEED_MULT  = {params['enemy_speed_mult']:.2f}
const ENEMY_DAMAGE_MULT = {params['enemy_damage_mult']:.2f}
# BGM推奨BPM: {params['bgm_bpm_target']}"""

    elif engine == "pygame":
        return f"""# ── フィーリングスライダー適用値（Pygame） ──
PLAYER_SPEED      = {params['player_speed']:.1f}
GRAVITY           = {params['player_gravity']:.1f}
JUMP_POWER        = {params['player_jump_power']:.0f}
FRICTION          = {params['player_friction']:.2f}
HIT_STOP_FRAMES   = {params['hit_stop_frames']}
KNOCKBACK         = {params['knockback_force']:.0f}
CAMERA_SHAKE      = {params['camera_shake_intensity']:.1f}
PARTICLE_COUNT    = {params['particle_count']}
ENEMY_SPEED_MULT  = {params['enemy_speed_mult']:.2f}
ENEMY_DAMAGE_MULT = {params['enemy_damage_mult']:.2f}
BGM_BPM_TARGET    = {params['bgm_bpm_target']}"""
    else:
        return f"// SPEED={params['player_speed']:.1f}, GRAVITY={params['player_gravity']:.0f}, JUMP={params['player_jump_power']:.0f}"


# ============================================================
# MDA / フロー理論 → プロンプト注入
# ============================================================

def get_mda_context(genre: str, goal: str) -> str:
    """
    MDA理論をベースにしたコード生成コンテキスト。
    「なぜそのパラメータにするか」をAIが理解してコードを書く。
    """
    mda = MDA_DATABASE.get(genre, MDA_DATABASE["2daction"])
    return f"""
【🎮 ゲーム面白さ理論（MDA）— {genre}】
■ Mechanics（仕組み）: {', '.join(mda['mechanics'][:4])}
■ Dynamics（体験）: {', '.join(mda['dynamics'][:3])}
■ Aesthetics（感動）: {', '.join(mda['aesthetics'][:3])}
■ フロー曲線: {mda['flow_curve']}
■ 面白さの核心: {mda['fun_principle']}

→ 上記の理論に基づき、「{goal[:60]}」を実装すること。
  単なる機能実装ではなく「なぜそのパラメータか」を意識して設計せよ。
  ヒットストップ・カメラシェイク・効果音のタイミングが「面白さ」を左右する。"""


def analyze_flow(game_desc: str, player_skill: str = "初心者") -> str:
    """フロー理論でゲームのバランスを診断"""
    skill_map = {"初心者": 0.2, "中級者": 0.5, "上級者": 0.8, "変態": 1.0}
    skill = skill_map.get(player_skill, 0.5)

    warnings = []
    suggestions = []

    # 簡易診断（キーワードベース）
    desc_lower = game_desc.lower()
    if "instant death" in desc_lower or "即死" in desc_lower:
        if skill < 0.7:
            warnings.append("⚠️ 即死要素が多い → 初心者・中級者がフロー状態に入れない可能性")
            suggestions.append("→ 最初の数回は無敵時間を長くする「慈悲モード」を追加")

    if "checkpoint" not in desc_lower and "チェックポイント" not in desc_lower:
        warnings.append("⚠️ チェックポイントなし → ストレスゾーンに落ちやすい")
        suggestions.append("→ 難しい場所の直前にセーブポイントを置く")

    result = "【📊 フロー理論診断】\n"
    result += f"対象プレイヤー: {player_skill}（スキル推定: {skill:.0%}）\n\n"
    if warnings:
        result += "発見した問題:\n" + "\n".join(warnings) + "\n\n"
        result += "改善提案:\n" + "\n".join(suggestions)
    else:
        result += "✅ フロー設計に大きな問題は見当たりません"
    return result


def get_fun_theory_prompt(genre: str) -> str:
    """コーダーへの注入用プロンプト（簡易版）"""
    mda = MDA_DATABASE.get(genre, MDA_DATABASE["2daction"])
    return (
        f"\n\n【面白さの核心】{mda['fun_principle']}\n"
        f"この原則を実装に反映させること。数値はただの数字ではなく「体験」である。"
    )


# ============================================================
# AIプレイテスト生成（Godotヘッドレス向け）
# ============================================================

_PLAYTEST_TEMPLATE_GODOT = '''# ai_playtest.gd — Blackwell自動生成AIプレイヤー
# Godot --headless --script ai_playtest.gd で実行
extends SceneTree

const MAX_STEPS = 500     # テストするステップ数
const LOG_FILE  = "playtest_result.json"

var results = {{
    "steps": 0,
    "deaths": 0,
    "stuck_count": 0,
    "max_x_reached": 0.0,
    "items_collected": 0,
    "bugs": [],
}}

func _initialize():
    var scene = load("{scene_path}").instantiate()
    get_root().add_child(scene)
    print("[Blackwell AIPlaytest] 開始")

func _process(delta):
    results["steps"] += 1
    if results["steps"] > MAX_STEPS:
        _finish()
        return

    # AI行動: ランダム探索 + 右方向バイアス
    var player = get_root().find_child("Player", true, false)
    if not player:
        results["bugs"].append("Player ノードが見つからない")
        _finish()
        return

    # 擬似入力（右移動 + 定期的にジャンプ）
    if results["steps"] % 30 == 0:
        # ジャンプを試みる
        if player.has_method("jump"):
            player.jump()

    # 最大到達X座標を記録（詰まり検出）
    if player.global_position.x > results["max_x_reached"]:
        results["max_x_reached"] = player.global_position.x
        results["stuck_count"] = 0
    else:
        results["stuck_count"] += 1
        if results["stuck_count"] > 60:
            results["bugs"].append("プレイヤーが詰まっている (step=%d, pos=%s)" % [
                results["steps"], str(player.global_position)
            ])
            results["stuck_count"] = 0

func _finish():
    var file = FileAccess.open(LOG_FILE, FileAccess.WRITE)
    file.store_string(JSON.stringify(results, "  "))
    file.close()
    print("[Blackwell AIPlaytest] 完了 → ", LOG_FILE)
    quit()
'''

def generate_playtest_script(scene_path: str = "res://scenes/main.tscn") -> str:
    """AIプレイテストスクリプト（Godot GDScript）を生成"""
    return _PLAYTEST_TEMPLATE_GODOT.format(scene_path=scene_path)


def parse_playtest_result(result_json: dict) -> str:
    """プレイテスト結果をレポートに変換"""
    lines = ["【🎮 AIプレイテスト結果】"]
    lines.append(f"実行ステップ: {result_json.get('steps', '?')}")
    lines.append(f"死亡回数: {result_json.get('deaths', 0)}")
    lines.append(f"最大到達X: {result_json.get('max_x_reached', 0):.0f}px")
    bugs = result_json.get("bugs", [])
    if bugs:
        lines.append(f"\n⚠️ 検出された問題 ({len(bugs)}件):")
        for b in bugs[:5]:
            lines.append(f"  • {b}")
    else:
        lines.append("\n✅ バグ・詰まりは検出されませんでした")
    return "\n".join(lines)
