"""
Blackwell Dev-OS — project_templates.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
プロジェクトテンプレート

ジャンルを選ぶだけで正しいディレクトリ構造・
定数ファイル・基本シーン構成を一括生成。

対応ジャンル:
  2daction / roguelike / simulation / towerdefense / pygame_2d
"""
import os, json
from pathlib import Path
from datetime import datetime


# ── テンプレート定義 ──────────────────────────────────────
TEMPLATES = {
    "2daction_godot4": {
        "label": "2Dアクション (Godot4)",
        "engine": "godot4",
        "dirs": ["scenes", "scripts", "assets/sprites", "assets/audio",
                 "assets/ui", "data", "addons"],
        "files": {
            "project.godot": '''[gd_resource type="ProjectSettings" format=3]
[application]
config/name="{project_name}"
run/main_scene="res://scenes/Main.tscn"
config/features=PackedStringArray("4.2")
''',
            "scripts/constants.gd": '''# {project_name} — 定数定義
extends Node

# プレイヤー
const PLAYER_SPEED        = 250.0
const PLAYER_JUMP_POWER   = -550.0
const PLAYER_GRAVITY      = 900.0
const PLAYER_MAX_HP       = 100
const INVINCIBLE_FRAMES   = 30

# 敵
const ENEMY_SPEED_BASE    = 120.0
const ENEMY_DAMAGE_BASE   = 10
const ENEMY_HP_BASE       = 30

# ゲーム
const TILE_SIZE           = 32
const SCREEN_W            = 1280
const SCREEN_H            = 720
const SAVE_PATH           = "user://save.json"
''',
            "scripts/Player.gd": '''extends CharacterBody2D
class_name Player

signal died
signal hp_changed(new_hp: int)

@export var speed: float = 250.0
@export var jump_power: float = -550.0
@onready var sprite: Sprite2D = $Sprite2D
@onready var hitbox: Area2D  = $Hitbox

var max_hp: int = 100
var current_hp: int = 100
var invincible_frames: int = 0
var facing_right: bool = true

func _physics_process(delta: float) -> void:
    # 重力
    if not is_on_floor():
        velocity.y += 900.0 * delta

    # 左右移動
    var dir = Input.get_axis("ui_left", "ui_right")
    velocity.x = dir * speed
    if dir != 0:
        facing_right = dir > 0
        sprite.flip_h = !facing_right

    # ジャンプ
    if Input.is_action_just_pressed("ui_accept") and is_on_floor():
        velocity.y = jump_power

    # 無敵フレーム
    if invincible_frames > 0:
        invincible_frames -= 1

    move_and_slide()

func take_damage(amount: int) -> void:
    if invincible_frames > 0:
        return
    current_hp -= amount
    hp_changed.emit(current_hp)
    invincible_frames = 30
    if current_hp <= 0:
        died.emit()

func heal(amount: int) -> void:
    current_hp = min(current_hp + amount, max_hp)
    hp_changed.emit(current_hp)
''',
            "scripts/Enemy.gd": '''extends CharacterBody2D
class_name Enemy

signal died(enemy: Enemy)

@export var speed: float = 120.0
@export var hp: int = 30
@export var damage: int = 10
@export var detection_range: float = 300.0

var player: Player = null
var facing_right: bool = true

func _ready() -> void:
    player = get_tree().get_first_node_in_group("player")

func _physics_process(delta: float) -> void:
    if not is_on_floor():
        velocity.y += 900.0 * delta

    if player and global_position.distance_to(player.global_position) < detection_range:
        var dir = sign(player.global_position.x - global_position.x)
        velocity.x = dir * speed
        facing_right = dir > 0
    else:
        velocity.x = 0

    move_and_slide()

func take_damage(amount: int) -> void:
    hp -= amount
    if hp <= 0:
        died.emit(self)
        queue_free()
''',
            "scripts/GameManager.gd": '''extends Node
class_name GameManager

signal game_over
signal stage_clear

var score: int = 0
var lives: int = 3
var current_stage: int = 1

func add_score(points: int) -> void:
    score += points

func lose_life() -> void:
    lives -= 1
    if lives <= 0:
        game_over.emit()

func next_stage() -> void:
    current_stage += 1
    get_tree().change_scene_to_file(
        "res://scenes/Stage%d.tscn" % current_stage
    )

func restart() -> void:
    score = 0
    lives = 3
    current_stage = 1
    get_tree().change_scene_to_file("res://scenes/Main.tscn")
''',
            "data/game_config.json": '''{
  "version": "1.0",
  "title": "{project_name}",
  "stages": 5,
  "difficulty_curve": [1.0, 1.2, 1.5, 1.8, 2.2]
}
''',
        },
    },

    "roguelike_godot4": {
        "label": "ローグライク (Godot4)",
        "engine": "godot4",
        "dirs": ["scenes", "scripts", "scripts/systems", "scripts/entities",
                 "assets/tiles", "assets/items", "assets/enemies", "data"],
        "files": {
            "scripts/constants.gd": '''# {project_name} — 定数定義
const TILE_SIZE = 16
const DUNGEON_W = 50
const DUNGEON_H = 40
const MIN_ROOM_SIZE = 4
const MAX_ROOM_SIZE = 10
const MAX_ROOMS = 15
const FLOOR_COUNT = 10

# プレイヤー初期値
const PLAYER_BASE_HP  = 50
const PLAYER_BASE_ATK = 8
const PLAYER_BASE_DEF = 3
const PLAYER_BASE_SPD = 1

const SAVE_PATH = "user://roguelike_save.json"
''',
            "scripts/systems/DungeonGenerator.gd": '''extends Node
class_name DungeonGenerator

const TILE_WALL  = 0
const TILE_FLOOR = 1
const TILE_STAIR = 2

var grid: Array = []
var rooms: Array = []
var width: int
var height: int

func generate(w: int, h: int, max_rooms: int) -> Array:
    width  = w
    height = h
    grid   = []
    rooms  = []

    # 壁で埋める
    for y in h:
        grid.append([])
        for x in w:
            grid[y].append(TILE_WALL)

    # 部屋を配置
    for _i in max_rooms:
        var rw = randi_range(4, 10)
        var rh = randi_range(4, 8)
        var rx = randi_range(1, w - rw - 1)
        var ry = randi_range(1, h - rh - 1)
        _carve_room(rx, ry, rw, rh)

    # 廊下で接続
    for i in range(1, rooms.size()):
        _connect_rooms(rooms[i-1], rooms[i])

    # 階段を最後の部屋に配置
    if rooms.size() > 0:
        var last = rooms[-1]
        grid[last.y + last.h/2][last.x + last.w/2] = TILE_STAIR

    return grid

func _carve_room(x, y, w, h) -> void:
    for ry in range(y, y + h):
        for rx in range(x, x + w):
            grid[ry][rx] = TILE_FLOOR
    rooms.append(Rect2i(x, y, w, h))

func _connect_rooms(a: Rect2i, b: Rect2i) -> void:
    var ax = a.x + a.size.x / 2
    var ay = a.y + a.size.y / 2
    var bx = b.x + b.size.x / 2
    var by = b.y + b.size.y / 2
    while ax != bx:
        grid[ay][ax] = TILE_FLOOR
        ax += sign(bx - ax)
    while ay != by:
        grid[ay][ax] = TILE_FLOOR
        ay += sign(by - ay)

func get_player_start() -> Vector2i:
    if rooms.is_empty(): return Vector2i(1,1)
    var r = rooms[0]
    return Vector2i(r.x + r.size.x/2, r.y + r.size.y/2)
''',
        },
    },

    "pygame_2d": {
        "label": "2Dアクション (Pygame)",
        "engine": "pygame",
        "dirs": ["assets/images", "assets/sounds", "src", "data", "saves"],
        "files": {
            "main.py": '''"""
{project_name} — メインエントリポイント
"""
import pygame, sys, os
from src.game import Game

def main():
    pygame.init()
    pygame.mixer.init()
    screen = pygame.display.set_mode((1280, 720))
    pygame.display.set_caption("{project_name}")
    clock  = pygame.time.Clock()
    game   = Game(screen)

    while True:
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            game.handle_event(event)
        game.update(dt)
        game.draw()
        pygame.display.flip()

if __name__ == "__main__":
    main()
''',
            "src/constants.py": '''# {project_name} 定数
SCREEN_W, SCREEN_H = 1280, 720
FPS         = 60
TITLE       = "{project_name}"

# プレイヤー
PLAYER_SPEED       = 250
PLAYER_JUMP_POWER  = -600
GRAVITY            = 900
PLAYER_MAX_HP      = 100
INVINCIBLE_FRAMES  = 60

# 色
WHITE = (255,255,255)
BLACK = (0,0,0)
RED   = (220,60,60)
GREEN = (60,200,60)
BLUE  = (60,120,220)

# パス
SAVE_PATH = "saves/save.json"
''',
            "src/game.py": '''import pygame
from .constants import *

class Game:
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.state  = "menu"   # menu / playing / gameover
        self.score  = 0
        self.font   = pygame.font.SysFont(None, 36)

    def handle_event(self, event: pygame.event.Event):
        if self.state == "menu":
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                self.state = "playing"
        elif self.state == "gameover":
            if event.type == pygame.KEYDOWN:
                self.state = "menu"

    def update(self, dt: float):
        if self.state != "playing":
            return
        # TODO: ゲームロジック更新

    def draw(self):
        self.screen.fill(BLACK)
        if self.state == "menu":
            self._draw_text("{project_name}", WHITE, SCREEN_W//2, SCREEN_H//2-40, 64)
            self._draw_text("Press ENTER to Start", WHITE, SCREEN_W//2, SCREEN_H//2+40)
        elif self.state == "playing":
            self._draw_text(f"Score: {self.score}", WHITE, 80, 30)
        elif self.state == "gameover":
            self._draw_text("GAME OVER", RED, SCREEN_W//2, SCREEN_H//2-40, 64)
            self._draw_text("Press any key to continue", WHITE, SCREEN_W//2, SCREEN_H//2+40)

    def _draw_text(self, text, color, x, y, size=36):
        font = pygame.font.SysFont(None, size)
        surf = font.render(text, True, color)
        rect = surf.get_rect(center=(x, y))
        self.screen.blit(surf, rect)
''',
            "requirements.txt": "pygame>=2.5.0\n",
        },
    },
}


def create_project(
    project_name: str,
    template_key: str,
    output_path: str,
) -> dict:
    """
    テンプレートからプロジェクトを生成する。
    戻り値: {"success": bool, "created_files": list, "path": str}
    """
    tmpl = TEMPLATES.get(template_key)
    if not tmpl:
        return {"success": False, "error": f"テンプレート '{template_key}' が見つかりません"}

    project_path = os.path.join(output_path, project_name)
    created = []

    try:
        # ディレクトリ作成
        for d in tmpl["dirs"]:
            dp = os.path.join(project_path, d)
            os.makedirs(dp, exist_ok=True)
            # .gitkeep で空ディレクトリを保持
            gk = os.path.join(dp, ".gitkeep")
            if not os.listdir(dp):
                open(gk, "w").close()
                created.append(gk)

        # ファイル生成
        for rel_path, content in tmpl["files"].items():
            fp = os.path.join(project_path, rel_path)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            filled = content.replace("{project_name}", project_name)
            with open(fp, "w", encoding="utf-8") as f:
                f.write(filled)
            created.append(fp)

        # .gitignore
        gi_path = os.path.join(project_path, ".gitignore")
        with open(gi_path, "w", encoding="utf-8") as f:
            f.write("# Blackwell Dev-OS\n.godot/\n__pycache__/\n*.pyc\n"
                    "chroma_db/\n*.bw_backup\nplaytest_result.json\n"
                    "blackwell_learned_errors.json\n.blackwell_session.json\n")
        created.append(gi_path)

        # metadata
        meta = {
            "project_name": project_name,
            "template":     template_key,
            "engine":       tmpl["engine"],
            "created":      datetime.now().isoformat(),
            "blackwell_version": "v7.6",
        }
        meta_path = os.path.join(project_path, ".blackwell_meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        created.append(meta_path)

        return {
            "success":       True,
            "path":          project_path,
            "created_files": created,
            "template_label": tmpl["label"],
            "file_count":    len(created),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "path": project_path}


def get_templates() -> list:
    """テンプレート一覧を返す（UI表示用）"""
    return [
        {"key": k, "label": v["label"], "engine": v["engine"],
         "file_count": len(v["files"])}
        for k, v in TEMPLATES.items()
    ]
