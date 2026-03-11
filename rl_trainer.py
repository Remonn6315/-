"""
Blackwell Dev-OS — rl_trainer.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
② プレイヤーAI強化学習

【仕組み】
  Godot側に「RLエージェント」を埋め込む（GDScript）。
  エージェントはゲームをプレイしながら行動を選択する。
  各ステップの「状態・行動・報酬」をBlackwellに送信。
  BlackwellがQ-tableを更新して最適な方策を学習する。
  学習した方策をGodotに送り返す → エージェントが賢くなる。

【強化学習の構造】
  状態 (State):
    プレイヤーのHP / 位置 / 向き / 近くの敵 / アイテム距離 など
    ゲームごとにカスタマイズ可能

  行動 (Action):
    移動（上下左右）/ 攻撃 / ジャンプ / アイテム使用 など
    最大16アクションに対応

  報酬 (Reward):
    敵を倒す +10 / ダメージを受ける -5 / アイテム取得 +3
    ゲームオーバー -20 / ゴール達成 +50 など

  学習アルゴリズム:
    Q-learning（シンプル・安定・追加ライブラリ不要）
    + ε-greedy探索（最初はランダム、徐々に最適行動へ）

【2段階の学習】
  Phase A: シミュレーション学習
    Blackwellが「もしこう動いたら」をシミュレートして
    ゲームコードなしで基礎的な戦略を事前学習

  Phase B: 実プレイ学習
    実際にGodotでゲームをプレイしながらリアルタイムで更新
    godot_bridge経由でステップごとに通信

【保存先】
  {project}/blackwell_brain/rl_qtable.json      ← Q-table
  {project}/blackwell_brain/rl_episodes.json    ← エピソード履歴
  {project}/blackwell_brain/rl_config.json      ← 設定

【公開API】
  setup_rl(path, actions, state_keys, rewards)   → RLConfig
  step(path, state, action, reward, done)        → str  (次の行動)
  get_action(path, state)                        → str  (最適行動)
  start_episode(path)                            → int  (episode_id)
  end_episode(path, total_reward)                → EpisodeResult
  get_rl_stats(path)                             → dict
  export_policy_for_godot(path)                  → str  (GDScript)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import os
import math
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


BRAIN_DIR      = "blackwell_brain"
QTABLE_FILE    = "rl_qtable.json"
EPISODES_FILE  = "rl_episodes.json"
CONFIG_FILE    = "rl_config.json"

# デフォルトのハイパーパラメータ
DEFAULT_LR      = 0.1    # 学習率
DEFAULT_GAMMA   = 0.95   # 割引率
DEFAULT_EPSILON = 1.0    # 初期探索率
EPSILON_DECAY   = 0.995  # 探索率の減衰
EPSILON_MIN     = 0.05   # 最小探索率
MAX_EPISODES    = 500    # 保存する最大エピソード数


# ============================================================
# データ構造
# ============================================================

@dataclass
class RLConfig:
    actions:     list    # ["move_left", "move_right", "jump", "attack", ...]
    state_keys:  list    # ["hp", "pos_x", "pos_y", "enemy_dist", ...]
    rewards:     dict    # {"kill_enemy": 10, "take_damage": -5, ...}
    lr:          float   = DEFAULT_LR
    gamma:       float   = DEFAULT_GAMMA
    epsilon:     float   = DEFAULT_EPSILON
    episode:     int     = 0
    total_steps: int     = 0


@dataclass
class EpisodeResult:
    episode_id:   int
    total_reward: float
    steps:        int
    epsilon:      float
    avg_q:        float


# ============================================================
# ユーティリティ
# ============================================================

def _brain_dir(project_path: str) -> str:
    d = os.path.join(project_path, BRAIN_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _load(project_path: str, filename: str, default):
    path = os.path.join(_brain_dir(project_path), filename)
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(project_path: str, filename: str, data):
    path = os.path.join(_brain_dir(project_path), filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _now() -> str:
    return datetime.now().isoformat()[:16]


# ============================================================
# セットアップ
# ============================================================

def setup_rl(project_path: str,
             actions: list = None,
             state_keys: list = None,
             rewards: dict = None) -> RLConfig:
    """
    RLエージェントを初期化する。
    app.pyで最初に1回呼ぶ。
    """
    default_actions = [
        "move_left", "move_right", "move_up", "move_down",
        "jump", "attack", "dodge", "use_item",
    ]
    default_state_keys = [
        "hp_ratio", "pos_x_norm", "pos_y_norm",
        "nearest_enemy_dist", "nearest_enemy_dir",
        "nearest_item_dist", "on_ground", "stamina_ratio",
    ]
    default_rewards = {
        "kill_enemy":    10.0,
        "take_damage":   -5.0,
        "pick_item":      3.0,
        "reach_goal":    50.0,
        "game_over":    -20.0,
        "idle_penalty":  -0.1,
        "survive_bonus":  0.2,
    }

    cfg_data = _load(project_path, CONFIG_FILE, {})
    config = RLConfig(
        actions=actions   or cfg_data.get("actions",    default_actions),
        state_keys=state_keys or cfg_data.get("state_keys", default_state_keys),
        rewards=rewards   or cfg_data.get("rewards",    default_rewards),
        lr=cfg_data.get("lr", DEFAULT_LR),
        gamma=cfg_data.get("gamma", DEFAULT_GAMMA),
        epsilon=cfg_data.get("epsilon", DEFAULT_EPSILON),
        episode=cfg_data.get("episode", 0),
        total_steps=cfg_data.get("total_steps", 0),
    )
    _save_config(project_path, config)
    print(f"[rl_trainer] セットアップ完了: "
          f"{len(config.actions)}アクション / "
          f"{len(config.state_keys)}状態変数")
    return config


def _save_config(project_path: str, cfg: RLConfig):
    _save(project_path, CONFIG_FILE, {
        "actions":     cfg.actions,
        "state_keys":  cfg.state_keys,
        "rewards":     cfg.rewards,
        "lr":          cfg.lr,
        "gamma":       cfg.gamma,
        "epsilon":     cfg.epsilon,
        "episode":     cfg.episode,
        "total_steps": cfg.total_steps,
    })


# ============================================================
# Q-learning コア
# ============================================================

def _state_to_key(state: dict, state_keys: list) -> str:
    """状態dictを離散化してQ-tableのキーにする"""
    parts = []
    for k in state_keys:
        v = state.get(k, 0.0)
        # 連続値を10段階に離散化
        if isinstance(v, float):
            bucket = min(9, max(0, int(v * 10)))
        elif isinstance(v, bool):
            bucket = 1 if v else 0
        else:
            bucket = int(v) % 10
        parts.append(str(bucket))
    return "|".join(parts)


def get_action(project_path: str, state: dict) -> str:
    """
    現在の状態から次の行動を選択する。
    Godotのエージェントから毎フレーム呼ばれる想定。

    ε-greedy: epsilonの確率でランダム探索、それ以外は最適行動
    """
    cfg = _load_config(project_path)
    if not cfg:
        return "idle"

    # ε-greedy
    if random.random() < cfg["epsilon"]:
        return random.choice(cfg["actions"])

    qtable  = _load(project_path, QTABLE_FILE, {})
    s_key   = _state_to_key(state, cfg["state_keys"])
    q_vals  = qtable.get(s_key, {})

    if not q_vals:
        return random.choice(cfg["actions"])

    return max(q_vals, key=q_vals.get)


def step(project_path: str,
         state: dict,
         action: str,
         reward: float,
         next_state: dict,
         done: bool) -> str:
    """
    1ステップ分の学習を行い、次の行動を返す。
    Godotからの step メッセージで呼ぶ。

    Returns: 次の行動名
    """
    cfg = _load_config(project_path)
    if not cfg:
        return "idle"

    qtable  = _load(project_path, QTABLE_FILE, {})
    s_key   = _state_to_key(state,      cfg["state_keys"])
    ns_key  = _state_to_key(next_state, cfg["state_keys"])

    # Q値の初期化
    if s_key not in qtable:
        qtable[s_key]  = {a: 0.0 for a in cfg["actions"]}
    if ns_key not in qtable:
        qtable[ns_key] = {a: 0.0 for a in cfg["actions"]}

    # Q-learning更新式
    # Q(s,a) ← Q(s,a) + lr * [r + γ * max_a'Q(s',a') - Q(s,a)]
    current_q  = qtable[s_key].get(action, 0.0)
    max_next_q = max(qtable[ns_key].values()) if not done else 0.0
    new_q = current_q + cfg["lr"] * (
        reward + cfg["gamma"] * max_next_q - current_q
    )
    qtable[s_key][action] = new_q

    # Q-tableが大きくなりすぎたら古いエントリを削除
    if len(qtable) > 50000:
        keys_to_del = list(qtable.keys())[:5000]
        for k in keys_to_del:
            del qtable[k]

    _save(project_path, QTABLE_FILE, qtable)

    # ステップカウント更新
    cfg["total_steps"] = cfg.get("total_steps", 0) + 1
    _save(project_path, CONFIG_FILE, cfg)

    # 次の行動を選択して返す
    if done:
        return "idle"

    if random.random() < cfg["epsilon"]:
        return random.choice(cfg["actions"])
    return max(qtable[ns_key], key=qtable[ns_key].get)


def start_episode(project_path: str) -> int:
    """新しいエピソードを開始する"""
    cfg = _load_config(project_path)
    if not cfg:
        return 0
    ep_id = cfg.get("episode", 0) + 1
    cfg["episode"] = ep_id
    _save(project_path, CONFIG_FILE, cfg)
    print(f"[rl_trainer] エピソード {ep_id} 開始")
    return ep_id


def end_episode(project_path: str,
                total_reward: float,
                steps: int) -> EpisodeResult:
    """エピソード終了処理: εを減衰・履歴を保存"""
    cfg = _load_config(project_path)
    if not cfg:
        return EpisodeResult(0, 0, 0, 1.0, 0.0)

    ep_id   = cfg.get("episode", 0)
    epsilon = cfg.get("epsilon", DEFAULT_EPSILON)

    # ε減衰
    new_epsilon = max(EPSILON_MIN, epsilon * EPSILON_DECAY)
    cfg["epsilon"] = new_epsilon
    _save(project_path, CONFIG_FILE, cfg)

    # Q値の平均を計算
    qtable  = _load(project_path, QTABLE_FILE, {})
    all_q   = [v for row in qtable.values() for v in row.values()]
    avg_q   = sum(all_q) / len(all_q) if all_q else 0.0

    result = EpisodeResult(
        episode_id=ep_id,
        total_reward=total_reward,
        steps=steps,
        epsilon=new_epsilon,
        avg_q=round(avg_q, 3),
    )

    # 履歴に保存
    episodes = _load(project_path, EPISODES_FILE, {"episodes": []})
    episodes["episodes"].append({
        "episode_id":   ep_id,
        "total_reward": round(total_reward, 2),
        "steps":        steps,
        "epsilon":      round(new_epsilon, 4),
        "avg_q":        result.avg_q,
        "time":         _now(),
    })
    episodes["episodes"] = episodes["episodes"][-MAX_EPISODES:]
    _save(project_path, EPISODES_FILE, episodes)

    print(f"[rl_trainer] エピソード{ep_id}終了: "
          f"報酬={total_reward:.1f} / ε={new_epsilon:.3f} / "
          f"Q平均={avg_q:.3f}")
    return result


def _load_config(project_path: str) -> Optional[dict]:
    cfg = _load(project_path, CONFIG_FILE, {})
    if not cfg:
        return None
    if "actions" not in cfg:
        return None
    return cfg


# ============================================================
# 統計
# ============================================================

def get_rl_stats(project_path: str) -> dict:
    cfg      = _load_config(project_path) or {}
    episodes = _load(project_path, EPISODES_FILE, {"episodes": []})
    qtable   = _load(project_path, QTABLE_FILE, {})

    ep_list = episodes.get("episodes", [])
    rewards = [e["total_reward"] for e in ep_list]
    recent  = rewards[-20:] if rewards else []

    # 学習曲線: 10エピソードごとの平均報酬
    curve = []
    chunk = 10
    for i in range(0, len(rewards), chunk):
        chunk_r = rewards[i:i+chunk]
        curve.append({
            "ep":  i + chunk,
            "avg": round(sum(chunk_r)/len(chunk_r), 1),
        })

    return {
        "total_episodes":  cfg.get("episode", 0),
        "total_steps":     cfg.get("total_steps", 0),
        "epsilon":         round(cfg.get("epsilon", 1.0), 4),
        "qtable_states":   len(qtable),
        "best_reward":     max(rewards) if rewards else 0,
        "recent_avg":      round(sum(recent)/len(recent), 1) if recent else 0,
        "actions":         cfg.get("actions", []),
        "learning_curve":  curve[-20:],
        "last_episodes":   ep_list[-10:],
    }


# ============================================================
# Godot向けGDScript出力
# ============================================================

def export_policy_for_godot(project_path: str) -> str:
    """
    学習済みQ-tableをGodotが読み込めるGDScriptとして出力する。
    「最適方策の埋め込み」モード: もうランダム探索しない。

    使い方:
      export_policy_for_godot() の結果を
      res://addons/blackwell/rl_policy.gd として保存
    """
    cfg    = _load_config(project_path) or {}
    qtable = _load(project_path, QTABLE_FILE, {})

    if not qtable:
        return "# Q-tableが空です。先にトレーニングを実行してください。"

    actions    = cfg.get("actions", [])
    state_keys = cfg.get("state_keys", [])
    epsilon    = cfg.get("epsilon", 1.0)

    # 上位1000エントリだけ埋め込む（ファイルサイズ制限）
    top_entries = sorted(
        qtable.items(),
        key=lambda x: max(x[1].values()) if x[1] else 0,
        reverse=True
    )[:1000]

    q_dict_lines = []
    for state_key, q_vals in top_entries:
        best_action = max(q_vals, key=q_vals.get)
        q_dict_lines.append(
            f'\t\t"{state_key}": "{best_action}"'
        )

    gd = f'''## Blackwell RL Policy — 自動生成 ({_now()})
## エピソード数: {cfg.get("episode", 0)} / ε={epsilon:.4f}
## 状態数: {len(qtable)} / アクション: {actions}
## このファイルは自動更新されます。手動編集しないでください。
extends Node

const ACTIONS = {json.dumps(actions)}
const STATE_KEYS = {json.dumps(state_keys)}

## 学習済み方策テーブル (状態キー → 最適アクション)
const POLICY : Dictionary = {{
{chr(10).join(q_dict_lines)}
}}

## 状態を離散化してキーを生成
func state_to_key(state: Dictionary) -> String:
\tvar parts := []
\tfor k in STATE_KEYS:
\t\tvar v = state.get(k, 0.0)
\t\tvar bucket := clamp(int(v * 10.0), 0, 9)
\t\tparts.append(str(bucket))
\treturn "|".join(parts)

## 最適アクションを返す（学習済み方策）
func get_best_action(state: Dictionary) -> String:
\tvar key := state_to_key(state)
\tif POLICY.has(key):
\t\treturn POLICY[key]
\treturn ACTIONS[randi() % ACTIONS.size()]  ## 未知の状態はランダム

## 探索率 (0=完全活用, 1=完全探索)
var epsilon : float = {max(0.05, epsilon):.4f}

func get_action(state: Dictionary) -> String:
\tif randf() < epsilon:
\t\treturn ACTIONS[randi() % ACTIONS.size()]
\treturn get_best_action(state)
'''
    return gd


# ============================================================
# GodotエージェントのGDScriptひな形を生成
# ============================================================

def generate_agent_script(project_path: str,
                           node_name: str = "RLAgent") -> str:
    """
    Godot側のRLエージェントGDScriptひな形を生成する。
    プロジェクトに合わせてカスタマイズしてから使う。
    """
    cfg     = _load_config(project_path) or {}
    actions = cfg.get("actions", ["move_left", "move_right", "jump", "attack"])

    action_cases = "\n".join([
        f'\t\t"{a}":\n\t\t\t_do_{a.replace("-","_")}()'
        for a in actions
    ])

    action_funcs = "\n\n".join([
        f"func _do_{a.replace('-','_')}() -> void:\n\tpass  ## TODO: 実装する"
        for a in actions
    ])

    return f'''## Blackwell RLエージェント — 自動生成ひな形
## {_now()} に生成
## TODO: 各関数を実際のゲームロジックに合わせて実装してください
extends CharacterBody2D  ## または CharacterBody3D / Node2D など

const BRIDGE_URL = "ws://127.0.0.1:9901"
const STEP_INTERVAL = 0.1  ## 何秒ごとに行動するか

var _ws      : WebSocketPeer = WebSocketPeer.new()
var _timer   : float = 0.0
var _episode : int   = 0
var _steps   : int   = 0
var _total_reward : float = 0.0
var _current_action : String = "idle"
var _prev_state : Dictionary = {{}}


func _ready() -> void:
\t_ws.connect_to_url(BRIDGE_URL)
\t_start_episode()


func _process(delta: float) -> void:
\t_ws.poll()
\t_handle_messages()

\t_timer += delta
\tif _timer >= STEP_INTERVAL:
\t\t_timer = 0.0
\t\t_do_step()


func _start_episode() -> void:
\t_episode += 1
\t_steps = 0
\t_total_reward = 0.0
\t_send({{"type": "episode_start", "episode": _episode}})


func _do_step() -> void:
\t## 1. 現在の状態を取得
\tvar state := _get_state()

\t## 2. Blackwellに「状態・前回行動・報酬」を送信
\tvar reward := _calc_reward()
\t_total_reward += reward
\t_steps += 1

\t_send({{
\t\t"type":       "rl_step",
\t\t"state":      state,
\t\t"action":     _current_action,
\t\t"reward":     reward,
\t\t"next_state": state,
\t\t"done":       _is_done(),
\t}})


func _handle_messages() -> void:
\twhile _ws.get_available_packet_count() > 0:
\t\tvar raw := _ws.get_packet().get_string_from_utf8()
\t\tvar msg = JSON.parse_string(raw)
\t\tif not msg:
\t\t\tcontinue
\t\tif msg.get("type") == "rl_action":
\t\t\t_current_action = msg.get("action", "idle")
\t\t\t_execute_action(_current_action)
\t\telif msg.get("type") == "episode_end":
\t\t\t_start_episode()


func _execute_action(action: String) -> void:
\tmatch action:
{action_cases}
\t\t_:
\t\t\tpass  ## idle


## ─── カスタマイズが必要な関数 ───────────────────────────

func _get_state() -> Dictionary:
\t## TODO: ゲームの状態を返す
\treturn {{
\t\t"hp_ratio":           1.0,   ## 例: float(hp) / float(max_hp)
\t\t"pos_x_norm":         position.x / 1920.0,
\t\t"pos_y_norm":         position.y / 1080.0,
\t\t"nearest_enemy_dist": 1.0,   ## 敵との距離（正規化済み）
\t\t"nearest_enemy_dir":  0.0,   ## 敵の方向（-1〜1）
\t\t"nearest_item_dist":  1.0,
\t\t"on_ground":          is_on_floor(),
\t\t"stamina_ratio":      1.0,
\t}}


func _calc_reward() -> float:
\t## TODO: 報酬を計算する
\t## ヒント: 敵を倒した +10, ダメージを受けた -5, 生存 +0.2
\treturn 0.2  ## 仮: 毎ステップ生存ボーナス


func _is_done() -> bool:
\t## TODO: エピソード終了条件
\treturn false  ## 例: hp <= 0 or reached_goal


## ─── アクション実装 ──────────────────────────────────────

{action_funcs}


## ─── WebSocket送信 ───────────────────────────────────────

func _send(data: Dictionary) -> void:
\tif _ws.get_ready_state() == WebSocketPeer.STATE_OPEN:
\t\t_ws.send_text(JSON.stringify(data))
'''
