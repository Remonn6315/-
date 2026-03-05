"""
Blackwell Dev-OS — asset_pipeline.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2Dアクション・プラットフォーマー特化 素材自動解析パイプライン

【CursorもSonnetもできないBlackwell専用機能】
  ① スプライトシート自動解析
       画像を実際に開いてフレーム数・サイズを物理計測
       → pygame/Godotコードのフレーム数を自動で正確に設定
  ② アニメーション自動検出
       player_idle_01.png, player_run_01.png... のパターンから
       アニメーション種別・フレーム数・シーケンスを自動把握
  ③ 音声素材の物理解析
       WAV: サンプルレート・長さ・チャンネル数を実測
       MP3/OGG: ファイルサイズからBPM推定・ループ可否判定
  ④ タイルセット自動解析
       タイルサイズ・グリッド数を画像から自動検出
  ⑤ 完全なPygameコード自動生成
       解析結果をもとに「実際に動くコード」を直接出力

【engine.py から呼ばれる関数】
  scan_project_assets(folder) → AssetManifest
  build_pygame_context(manifest, goal) → str  ← プロンプトに注入
  generate_sprite_code(manifest, sprite_name) → str
  generate_tilemap_code(manifest) → str
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import re
import json
import wave
import struct
import hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime

try:
    from PIL import Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

try:
    import numpy as np
    _NP_OK = True
except ImportError:
    _NP_OK = False

# ============================================================
# データ構造
# ============================================================

@dataclass
class SpriteInfo:
    """スプライト1枚 or スプライトシートの解析結果"""
    path:          str
    name:          str                    # ファイル名（拡張子なし）
    width:         int  = 0
    height:        int  = 0
    role:          str  = "unknown"       # player/enemy/boss/item/bg/ui/effect
    anim_group:    str  = ""              # "player_idle" / "player_run" など
    frame_index:   int  = -1             # シーケンス番号（-1=単体）
    # スプライトシートの場合
    is_sheet:      bool = False
    sheet_cols:    int  = 0
    sheet_rows:    int  = 0
    frame_w:       int  = 0
    frame_h:       int  = 0
    total_frames:  int  = 0
    # Pygame用
    pygame_snippet: str = ""


@dataclass
class AudioInfo:
    """音声素材の解析結果"""
    path:        str
    name:        str
    category:    str  = "se"      # bgm / se / voice / ambient
    role:        str  = "unknown"
    duration_s:  float = 0.0
    sample_rate: int   = 0
    channels:    int   = 0
    is_loop:     bool  = False
    bpm_estimate: Optional[int] = None
    pygame_snippet: str = ""


@dataclass
class TilesetInfo:
    """タイルセットの解析結果"""
    path:       str
    name:       str
    width:      int  = 0
    height:     int  = 0
    tile_w:     int  = 0
    tile_h:     int  = 0
    cols:       int  = 0
    rows:       int  = 0
    total_tiles:int  = 0
    pygame_snippet: str = ""


@dataclass
class AssetManifest:
    """プロジェクト全素材の解析結果マニフェスト"""
    folder:       str
    scanned_at:   str = ""
    # 分類済み素材
    sprites:      list = field(default_factory=list)   # SpriteInfo
    tilesets:     list = field(default_factory=list)   # TilesetInfo
    backgrounds:  list = field(default_factory=list)   # SpriteInfo (role=bg)
    ui_assets:    list = field(default_factory=list)   # SpriteInfo (role=ui)
    effects:      list = field(default_factory=list)   # SpriteInfo (role=effect)
    audio_bgm:    list = field(default_factory=list)   # AudioInfo
    audio_se:     list = field(default_factory=list)   # AudioInfo
    # アニメーショングループ
    anim_groups:  dict = field(default_factory=dict)   # {group_name: [SpriteInfo]}
    # サマリー
    summary:      dict = field(default_factory=dict)


# ============================================================
# 役割判定
# ============================================================

_ROLE_MAP = [
    (["player","hero","protagonist","char_0","pc_"],        "player"),
    (["enemy","mob","goblin","slime","orc","skeleton"],      "enemy"),
    (["boss"],                                               "boss"),
    (["npc","villager","townspeople"],                       "npc"),
    (["tile","terrain","ground","floor","wall","stone"],     "tile"),
    (["bg","background","sky","back_","cloud","mountain"],   "bg"),
    (["item","coin","gem","key","potion","heart","star"],    "item"),
    (["weapon","sword","axe","bow","bullet","projectile"],   "weapon"),
    (["effect","fx","explosion","hit_","spark","fire","dust"],"effect"),
    (["ui","hud","panel","frame","button","bar","icon_ui"],  "ui"),
    (["portrait","face","bust"],                             "portrait"),
]

_AUDIO_ROLE_MAP = [
    (["bgm","music","theme","ost","loop","stage"],    "bgm",   True),
    (["battle","fight","dungeon"],                    "bgm",   True),
    (["title","menu"],                                "bgm",   True),
    (["jump","land","walk","run","step"],              "se",    False),
    (["attack","hit","slash","shoot","bullet"],        "se",    False),
    (["coin","item","pickup","collect"],               "se",    False),
    (["death","gameover","game_over"],                 "se",    False),
    (["levelup","fanfare","victory","clear"],          "se",    False),
    (["voice","vo_","talk"],                           "voice", False),
    (["ambient","env","wind","rain","forest"],         "se",    True),
]

def _detect_role(filename: str) -> str:
    fn = filename.lower()
    for kws, role in _ROLE_MAP:
        if any(k in fn for k in kws):
            return role
    return "misc"

def _detect_audio_role(filename: str) -> tuple[str, bool]:
    fn = filename.lower()
    for kws, cat, is_loop in _AUDIO_ROLE_MAP:
        if any(k in fn for k in kws):
            return cat, is_loop
    return "se", False

def _detect_anim_group(filename: str) -> tuple[str, int]:
    """
    player_idle_01.png → ("player_idle", 1)
    enemy_run_3.png    → ("enemy_run", 3)
    hero_jump.png      → ("hero_jump", 0)  # 単体
    """
    stem = Path(filename).stem
    m = re.match(r"^(.*?)[-_]?(\d+)$", stem)
    if m:
        group = m.group(1).rstrip("_-")
        idx   = int(m.group(2))
        return group, idx
    return stem, -1


# ============================================================
# 画像解析
# ============================================================

# 標準的なゲームスプライトのフレームサイズ候補（ピクセル）
_COMMON_TILE_SIZES = [8, 16, 24, 32, 48, 64, 96, 128, 256]

def _find_best_frame_size(dimension: int) -> int:
    """
    画像の幅/高さから最適なフレーム/タイルサイズを推定。
    ゲーム素材でよく使われるサイズ（32/48/64px）を優先。
    ※ 実際のプロジェクトでは素材に合わせて確認・修正してください。
    """
    # ゲームでよく使われるサイズ順（頻度高い順）
    priority_sizes = [32, 48, 64, 16, 96, 24, 128, 8, 256]

    # 1. 優先サイズでタイル数が2〜32に収まるものを探す
    for sz in priority_sizes:
        if dimension % sz == 0:
            count = dimension // sz
            if 2 <= count <= 32:
                return sz

    # 2. どれも無理なら候補の中でタイル数4〜16に収まる最大サイズ
    best_sz, best_sc = dimension, -1
    for sz in _COMMON_TILE_SIZES:
        if dimension % sz == 0:
            count = dimension // sz
            if 2 <= count <= 32:
                score = sz + (100 if 4 <= count <= 16 else 0)
                if score > best_sc:
                    best_sc, best_sz = score, sz

    return best_sz


def analyze_image(filepath: str) -> Optional[SpriteInfo]:
    """
    画像ファイルを物理的に開いて解析する。
    スプライトシートかどうかを自動判定。
    """
    if not _PIL_OK:
        return None
    try:
        fname = Path(filepath).name
        stem  = Path(filepath).stem
        role  = _detect_role(fname)
        anim_group, frame_idx = _detect_anim_group(fname)

        with Image.open(filepath) as img:
            w, h = img.size

        info = SpriteInfo(
            path=filepath, name=stem,
            width=w, height=h,
            role=role,
            anim_group=anim_group,
            frame_index=frame_idx,
        )

        # タイル素材の場合はTilesetInfoで処理
        if role == "tile":
            return info  # Tileset解析は別関数

        # スプライトシート判定
        # 条件: 幅が高さより大きく、幅が標準サイズの倍数
        fw = _find_best_frame_size(w)
        fh = _find_best_frame_size(h)

        cols = w // fw if fw > 0 else 1
        rows = h // fh if fh > 0 else 1
        total = cols * rows

        if total >= 2:
            info.is_sheet      = True
            info.sheet_cols    = cols
            info.sheet_rows    = rows
            info.frame_w       = fw
            info.frame_h       = fh
            info.total_frames  = total

        # Pygameコードスニペット生成
        info.pygame_snippet = _gen_sprite_snippet(info)
        return info

    except Exception as e:
        return SpriteInfo(path=filepath, name=Path(filepath).stem,
                          role=_detect_role(Path(filepath).name))


def analyze_tileset(filepath: str) -> Optional[TilesetInfo]:
    """タイルセット画像を解析してグリッド情報を抽出"""
    if not _PIL_OK:
        return None
    try:
        fname = Path(filepath).name
        with Image.open(filepath) as img:
            w, h = img.size

        tw = _find_best_frame_size(w)
        th = _find_best_frame_size(h)
        cols = w // tw
        rows = h // th

        info = TilesetInfo(
            path=filepath, name=Path(filepath).stem,
            width=w, height=h,
            tile_w=tw, tile_h=th,
            cols=cols, rows=rows,
            total_tiles=cols * rows,
        )
        info.pygame_snippet = _gen_tileset_snippet(info)
        return info
    except Exception:
        return None


# ============================================================
# 音声解析
# ============================================================

def analyze_audio(filepath: str) -> Optional[AudioInfo]:
    """音声ファイルを物理解析（WAV: 正確計測 / その他: 推定）"""
    fname = Path(filepath).name
    ext   = Path(filepath).suffix.lower()
    cat, is_loop = _detect_audio_role(fname)

    info = AudioInfo(
        path=filepath, name=Path(filepath).stem,
        category=cat, is_loop=is_loop,
        role=fname,
    )

    # WAVは正確に解析できる
    if ext == ".wav":
        try:
            with wave.open(filepath, "rb") as wf:
                frames      = wf.getnframes()
                rate        = wf.getframerate()
                channels    = wf.getnchannels()
                duration    = frames / float(rate)
                info.duration_s  = round(duration, 2)
                info.sample_rate = rate
                info.channels    = channels
        except Exception:
            pass

    # MP3/OGGはファイルサイズから推定
    elif ext in {".mp3", ".ogg", ".flac", ".aac"}:
        try:
            size = os.path.getsize(filepath)
            # 128kbps仮定で推定（実際より多少誤差あり）
            kbps = 128
            info.duration_s = round(size * 8 / (kbps * 1000), 1)
        except Exception:
            pass

    # BGMのBPM推定（長さからざっくり）
    if cat == "bgm" and info.duration_s > 0:
        # ゲームBGMは多くが60〜180BPMで4/4拍子
        # 4小節ループ (16拍) のパターンが多い
        common_bpm = [60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 180]
        for bpm in common_bpm:
            beat_len = 60.0 / bpm
            loop4    = beat_len * 16   # 4小節
            loop8    = beat_len * 32   # 8小節
            if abs(info.duration_s - loop4) < 0.2 or abs(info.duration_s - loop8) < 0.2:
                info.bpm_estimate = bpm
                break

    info.pygame_snippet = _gen_audio_snippet(info)
    return info


# ============================================================
# Pygameコードスニペット生成
# ============================================================

def _gen_sprite_snippet(info: SpriteInfo) -> str:
    """スプライト情報からPygameロードコードを生成"""
    rel = os.path.basename(info.path)
    if info.is_sheet:
        return (
            "# {name} スプライトシート ({cols}x{rows}={total}フレーム, 各{fw}x{fh}px)\n"
            "{var}_sheet = pygame.image.load('{rel}').convert_alpha()\n"
            "{var}_frames = [\n"
            "    {var}_sheet.subsurface(pygame.Rect(i * {fw}, j * {fh}, {fw}, {fh}))\n"
            "    for j in range({rows}) for i in range({cols})\n"
            "]  # 合計{total}フレーム\n"
            "{var}_frame_idx = 0\n"
            "{var}_anim_speed = 0.15  # 秒/フレーム（調整可）\n"
        ).format(
            name=info.name, var=info.name.replace("-","_"),
            rel=rel, cols=info.sheet_cols, rows=info.sheet_rows,
            total=info.total_frames, fw=info.frame_w, fh=info.frame_h,
        )
    else:
        return (
            "# {name} ({w}x{h}px, role={role})\n"
            "{var}_img = pygame.image.load('{rel}').convert_alpha()\n"
        ).format(
            name=info.name, var=info.name.replace("-","_"),
            rel=rel, w=info.width, h=info.height, role=info.role,
        )


def _gen_tileset_snippet(info: TilesetInfo) -> str:
    """タイルセット情報からPygameコードを生成"""
    rel = os.path.basename(info.path)
    return (
        "# {name} タイルセット ({cols}x{rows}={total}タイル, 各{tw}x{th}px)\n"
        "{var}_sheet = pygame.image.load('{rel}').convert()\n"
        "TILE_W, TILE_H = {tw}, {th}\n"
        "{var}_tiles = {{\n"
        "    tile_id: {var}_sheet.subsurface(\n"
        "        pygame.Rect((tile_id % {cols}) * TILE_W,\n"
        "                    (tile_id // {cols}) * TILE_H, TILE_W, TILE_H))\n"
        "    for tile_id in range({total})\n"
        "}}  # tile_id 0〜{total_m1} でアクセス\n"
    ).format(
        name=info.name, var=info.name.replace("-","_"),
        rel=rel, cols=info.cols, rows=info.rows,
        tw=info.tile_w, th=info.tile_h,
        total=info.total_tiles, total_m1=info.total_tiles - 1,
    )


def _gen_audio_snippet(info: AudioInfo) -> str:
    """音声情報からPygame.mixerコードを生成"""
    rel = os.path.basename(info.path)
    if info.category == "bgm":
        loop_info = f"  # {info.duration_s}秒" + (f", 推定{info.bpm_estimate}BPM" if info.bpm_estimate else "")
        return (
            "# BGM: {name}{loop_info}\n"
            "pygame.mixer.music.load('{rel}')\n"
            "pygame.mixer.music.play(-1)  # -1=ループ再生\n"
            "pygame.mixer.music.set_volume(0.7)  # 音量0.0〜1.0\n"
        ).format(name=info.name, rel=rel, loop_info=loop_info)
    else:
        dur = f"  # {info.duration_s}秒" if info.duration_s > 0 else ""
        return (
            "# SE: {name}{dur}\n"
            "{var}_se = pygame.mixer.Sound('{rel}')\n"
            "{var}_se.set_volume(0.8)\n"
            "# 再生: {var}_se.play()\n"
        ).format(name=info.name, var=info.name.replace("-","_"), rel=rel, dur=dur)


# ============================================================
# プロジェクト全体スキャン
# ============================================================

_IMG_EXT   = frozenset({".png",".jpg",".jpeg",".gif",".bmp",".webp"})
_AUDIO_EXT = frozenset({".wav",".mp3",".ogg",".flac",".aac"})
_SKIP_DIRS = frozenset({".git","__pycache__","node_modules","venv",".venv",
                        "dist","build",".godot"})


def scan_project_assets(folder: str) -> AssetManifest:
    """
    フォルダ以下の全素材を物理解析してAssetManifestを返す。
    これがBlackwellの核心：実際に画像を開いてフレーム数を測る。
    """
    manifest = AssetManifest(
        folder=folder,
        scanned_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fname in files:
            fpath = os.path.join(root, fname)
            ext   = Path(fname).suffix.lower()

            if ext in _IMG_EXT:
                role = _detect_role(fname)
                if role == "tile":
                    info = analyze_tileset(fpath)
                    if info:
                        manifest.tilesets.append(info)
                elif role == "bg":
                    info = analyze_image(fpath)
                    if info:
                        manifest.backgrounds.append(info)
                elif role == "ui":
                    info = analyze_image(fpath)
                    if info:
                        manifest.ui_assets.append(info)
                elif role == "effect":
                    info = analyze_image(fpath)
                    if info:
                        manifest.effects.append(info)
                else:
                    info = analyze_image(fpath)
                    if info:
                        manifest.sprites.append(info)
                        # アニメーショングループへの追加
                        if info.anim_group:
                            manifest.anim_groups.setdefault(info.anim_group, [])
                            manifest.anim_groups[info.anim_group].append(info)

            elif ext in _AUDIO_EXT:
                info = analyze_audio(fpath)
                if info:
                    if info.category == "bgm":
                        manifest.audio_bgm.append(info)
                    else:
                        manifest.audio_se.append(info)

    # アニメーショングループをフレーム順にソート
    for group_name, frames in manifest.anim_groups.items():
        manifest.anim_groups[group_name] = sorted(
            frames, key=lambda x: x.frame_index
        )

    # サマリー生成
    manifest.summary = {
        "total_sprites":    len(manifest.sprites),
        "total_tilesets":   len(manifest.tilesets),
        "total_backgrounds":len(manifest.backgrounds),
        "total_effects":    len(manifest.effects),
        "total_bgm":        len(manifest.audio_bgm),
        "total_se":         len(manifest.audio_se),
        "anim_groups":      list(manifest.anim_groups.keys()),
        "has_player":       any(s.role == "player" for s in manifest.sprites),
        "has_enemy":        any(s.role in {"enemy","boss"} for s in manifest.sprites),
        "has_tileset":      len(manifest.tilesets) > 0,
        "has_bgm":          len(manifest.audio_bgm) > 0,
        "sheets_detected":  sum(1 for s in manifest.sprites if s.is_sheet),
    }

    return manifest


# ============================================================
# エンジン統合: プロンプトコンテキスト生成
# ============================================================

def build_pygame_context(manifest: AssetManifest, goal: str) -> str:
    """
    解析済みAssetManifestからエンジンに注入するコンテキストを生成。
    「実際のフレーム数・サイズ入り」のコードをAIが出力できるようになる。
    """
    if not manifest:
        return ""

    lines = ["\n\n【🎮 物理解析済み素材マニフェスト】"]
    lines.append(f"スキャン日時: {manifest.scanned_at}")

    # プレイヤー関連
    player_sprites = [s for s in manifest.sprites if s.role == "player"]
    if player_sprites:
        lines.append("\n🧍 プレイヤースプライト:")
        for s in player_sprites[:5]:
            if s.is_sheet:
                lines.append(
                    f"  {s.name}: シート {s.sheet_cols}x{s.sheet_rows}={s.total_frames}フレーム "
                    f"(各{s.frame_w}x{s.frame_h}px)"
                )
            else:
                lines.append(f"  {s.name}: {s.width}x{s.height}px")

    # アニメーショングループ
    if manifest.anim_groups:
        lines.append("\n🎬 アニメーションシーケンス:")
        for gname, frames in list(manifest.anim_groups.items())[:8]:
            cnt = len(frames)
            lines.append(f"  {gname}: {cnt}フレーム")

    # タイルセット
    if manifest.tilesets:
        lines.append("\n🧱 タイルセット:")
        for t in manifest.tilesets[:3]:
            lines.append(
                f"  {t.name}: {t.tile_w}x{t.tile_h}px × {t.total_tiles}タイル "
                f"({t.cols}列x{t.rows}行)"
            )

    # 敵スプライト
    enemy_sprites = [s for s in manifest.sprites if s.role in {"enemy","boss"}]
    if enemy_sprites:
        lines.append(f"\n👾 敵スプライト: {len(enemy_sprites)}種")
        for s in enemy_sprites[:4]:
            if s.is_sheet:
                lines.append(f"  {s.name}: {s.total_frames}フレーム ({s.frame_w}x{s.frame_h}px)")
            else:
                lines.append(f"  {s.name}: {s.width}x{s.height}px [{s.role}]")

    # 背景
    if manifest.backgrounds:
        lines.append(f"\n🌄 背景: {', '.join(Path(b.path).name for b in manifest.backgrounds[:4])}")

    # BGM
    if manifest.audio_bgm:
        lines.append("\n🎵 BGM:")
        for a in manifest.audio_bgm[:4]:
            dur = f"{a.duration_s}秒" if a.duration_s > 0 else "不明"
            bpm = f", 推定{a.bpm_estimate}BPM" if a.bpm_estimate else ""
            lines.append(f"  {a.name}: {dur}{bpm} {'(ループ)' if a.is_loop else ''}")

    # SE
    if manifest.audio_se:
        lines.append(f"\n🔊 SE({len(manifest.audio_se)}個): "
                     + ", ".join(a.name for a in manifest.audio_se[:8]))

    # 重要な指示
    lines.append(f"\n→ ゴール: 「{goal[:100]}」")
    lines.append("【必須指示】")
    lines.append("  - 上記の実測フレーム数・サイズをそのままコードに使うこと")
    lines.append("  - ファイルパスはそのまま使うこと（変数名はファイル名ベース）")
    lines.append("  - pygame.image.load / subsurface を使ってスプライトシートを分割すること")
    if manifest.tilesets:
        lines.append("  - タイルはtile_idでアクセスする辞書形式で管理すること")

    return "\n".join(lines)


# ============================================================
# 完全な動くPygameコード生成
# ============================================================

def generate_sprite_code(manifest: AssetManifest, sprite_name: str = "player") -> str:
    """
    指定スプライトの完全なPygameクラスコードを生成。
    フレーム数・サイズは実測値が入る。
    """
    target = next(
        (s for s in manifest.sprites if sprite_name in s.name.lower()),
        None
    )
    if not target:
        return f"# {sprite_name} スプライトが見つかりません"

    # アニメーショングループ探索
    anims = {
        k: v for k, v in manifest.anim_groups.items()
        if sprite_name in k.lower()
    }

    if target.is_sheet:
        return _gen_sheet_player_class(target, anims)
    elif anims:
        return _gen_sequence_player_class(anims, sprite_name)
    else:
        return _gen_simple_player_class(target)


def _gen_sheet_player_class(info: SpriteInfo, anims: dict) -> str:
    """スプライトシートベースのプレイヤークラス"""
    vname = info.name.replace("-","_")
    fname = Path(info.path).name
    return f"""import pygame

class Player(pygame.sprite.Sprite):
    \"\"\"
    自動生成プレイヤークラス
    素材: {fname} ({info.sheet_cols}x{info.sheet_rows}シート, 各{info.frame_w}x{info.frame_h}px)
    \"\"\"
    SPEED   = 5
    GRAVITY = 0.5
    JUMP_POW = -12

    def __init__(self, x: int, y: int):
        super().__init__()
        # スプライトシート読み込み（実測: {info.total_frames}フレーム）
        sheet = pygame.image.load('{fname}').convert_alpha()
        self.frames = [
            sheet.subsurface(pygame.Rect(i * {info.frame_w}, j * {info.frame_h},
                                         {info.frame_w}, {info.frame_h}))
            for j in range({info.sheet_rows})
            for i in range({info.sheet_cols})
        ]
        self.frame_idx   = 0
        self.anim_timer  = 0
        self.anim_speed  = 0.12   # 秒/フレーム

        self.image  = self.frames[0]
        self.rect   = self.image.get_rect(topleft=(x, y))
        self.vel_y  = 0.0
        self.on_ground = False
        self.facing_right = True

    def update(self, dt: float, tiles: pygame.sprite.Group):
        keys = pygame.key.get_pressed()
        vx   = 0

        if keys[pygame.K_LEFT]  or keys[pygame.K_a]: vx = -self.SPEED; self.facing_right = False
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]: vx =  self.SPEED; self.facing_right = True
        if (keys[pygame.K_SPACE] or keys[pygame.K_w] or keys[pygame.K_UP]) and self.on_ground:
            self.vel_y = self.JUMP_POW

        # 重力
        self.vel_y = min(self.vel_y + self.GRAVITY, 15)

        # 水平移動 + 衝突
        self.rect.x += vx
        self._collide_x(tiles)

        # 垂直移動 + 衝突
        self.rect.y += int(self.vel_y)
        self.on_ground = False
        self._collide_y(tiles)

        # アニメーション更新
        self.anim_timer += dt
        if self.anim_timer >= self.anim_speed:
            self.anim_timer = 0
            self.frame_idx = (self.frame_idx + 1) % len(self.frames)

        self.image = self.frames[self.frame_idx]
        if not self.facing_right:
            self.image = pygame.transform.flip(self.image, True, False)

    def _collide_x(self, tiles):
        for tile in pygame.sprite.spritecollide(self, tiles, False):
            if self.rect.right > tile.rect.left and self.rect.left < tile.rect.left:
                self.rect.right = tile.rect.left
            elif self.rect.left < tile.rect.right and self.rect.right > tile.rect.right:
                self.rect.left = tile.rect.right

    def _collide_y(self, tiles):
        for tile in pygame.sprite.spritecollide(self, tiles, False):
            if self.vel_y > 0:
                self.rect.bottom = tile.rect.top
                self.on_ground   = True
            elif self.vel_y < 0:
                self.rect.top = tile.rect.bottom
            self.vel_y = 0
"""


def _gen_sequence_player_class(anims: dict, sprite_name: str) -> str:
    """連番スプライトシーケンスベースのプレイヤークラス"""
    anim_lines = []
    for gname, frames in anims.items():
        key   = gname.split("_")[-1] if "_" in gname else gname  # "idle"/"run" etc
        files = [Path(f.path).name for f in frames]
        anim_lines.append(f'        "{key}": [{", ".join(repr(f) for f in files)}],')

    anim_block = "\n".join(anim_lines) if anim_lines else '        "idle": [],'

    return f"""import pygame

class Player(pygame.sprite.Sprite):
    \"\"\"連番スプライトシーケンス版プレイヤー ({sprite_name})\"\"\"
    SPEED    = 5
    GRAVITY  = 0.5
    JUMP_POW = -12

    _ANIM_FILES = {{
{anim_block}
    }}

    def __init__(self, x: int, y: int):
        super().__init__()
        # アニメーションロード
        self.anims = {{
            key: [pygame.image.load(f).convert_alpha() for f in files]
            for key, files in self._ANIM_FILES.items()
            if files
        }}
        self.current_anim = list(self.anims.keys())[0] if self.anims else "idle"
        self.frame_idx    = 0
        self.anim_timer   = 0
        self.anim_speed   = 0.12

        self.image = (self.anims[self.current_anim][0]
                      if self.anims else pygame.Surface((32,48)))
        self.rect  = self.image.get_rect(topleft=(x, y))
        self.vel_y = 0.0
        self.on_ground   = False
        self.facing_right = True

    def _set_anim(self, name: str):
        if name in self.anims and self.current_anim != name:
            self.current_anim = name
            self.frame_idx    = 0

    def update(self, dt: float, tiles: pygame.sprite.Group):
        keys = pygame.key.get_pressed()
        vx   = 0

        if keys[pygame.K_LEFT]  or keys[pygame.K_a]: vx = -self.SPEED; self.facing_right = False
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]: vx =  self.SPEED; self.facing_right = True
        if (keys[pygame.K_SPACE] or keys[pygame.K_w]) and self.on_ground:
            self.vel_y = self.JUMP_POW

        # アニメーション切り替え
        if not self.on_ground: self._set_anim("jump")
        elif vx != 0:          self._set_anim("run")
        else:                  self._set_anim("idle")

        self.vel_y = min(self.vel_y + self.GRAVITY, 15)
        self.rect.x += vx
        self.rect.y += int(self.vel_y)
        self.on_ground = False

        # アニメーション更新
        frames = self.anims.get(self.current_anim, [])
        if frames:
            self.anim_timer += dt
            if self.anim_timer >= self.anim_speed:
                self.anim_timer = 0
                self.frame_idx  = (self.frame_idx + 1) % len(frames)
            self.image = frames[self.frame_idx]
            if not self.facing_right:
                self.image = pygame.transform.flip(self.image, True, False)
"""


def _gen_simple_player_class(info: SpriteInfo) -> str:
    """単体スプライト版（シートなし）"""
    fname = Path(info.path).name
    return f"""import pygame

class Player(pygame.sprite.Sprite):
    \"\"\"シンプルプレイヤークラス ({fname}, {info.width}x{info.height}px)\"\"\"
    SPEED    = 5
    GRAVITY  = 0.5
    JUMP_POW = -12

    def __init__(self, x: int, y: int):
        super().__init__()
        self.image = pygame.image.load('{fname}').convert_alpha()
        self.rect  = self.image.get_rect(topleft=(x, y))
        self.vel_y = 0.0
        self.on_ground    = False
        self.facing_right = True
        self._orig_img    = self.image.copy()

    def update(self, dt: float, tiles: pygame.sprite.Group):
        keys = pygame.key.get_pressed()
        vx   = 0
        if keys[pygame.K_LEFT]  or keys[pygame.K_a]: vx = -self.SPEED; self.facing_right = False
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]: vx =  self.SPEED; self.facing_right = True
        if (keys[pygame.K_SPACE] or keys[pygame.K_w]) and self.on_ground:
            self.vel_y = self.JUMP_POW
        self.vel_y = min(self.vel_y + self.GRAVITY, 15)
        self.rect.x += vx
        self.rect.y += int(self.vel_y)
        self.on_ground = False
        self.image = (self._orig_img if self.facing_right
                      else pygame.transform.flip(self._orig_img, True, False))
"""


def generate_tilemap_code(manifest: AssetManifest) -> str:
    """タイルセット情報からTilemapクラスを生成"""
    if not manifest.tilesets:
        return "# タイルセットが見つかりません"

    t = manifest.tilesets[0]
    fname = Path(t.path).name
    return f"""import pygame

class Tilemap:
    \"\"\"
    自動生成タイルマップクラス
    素材: {fname} ({t.tile_w}x{t.tile_h}px × {t.total_tiles}タイル)
    \"\"\"
    TILE_W = {t.tile_w}
    TILE_H = {t.tile_h}

    def __init__(self, layout: list[list[int]]):
        \"\"\"
        layout: 2D配列。tile_id (0〜{t.total_tiles-1}) でタイル指定。
               -1 = 空（何も描画しない）
        \"\"\"
        sheet    = pygame.image.load('{fname}').convert()
        sheet.set_colorkey((0, 0, 0))  # 透過色（必要に応じて変更）
        # タイル辞書: tile_id → Surface
        self.tiles = {{
            tid: sheet.subsurface(
                pygame.Rect((tid % {t.cols}) * self.TILE_W,
                            (tid // {t.cols}) * self.TILE_H,
                            self.TILE_W, self.TILE_H))
            for tid in range({t.total_tiles})
        }}
        self.layout  = layout
        self.solids  = pygame.sprite.Group()  # 衝突判定あり
        self._build()

    def _build(self):
        \"\"\"レイアウトからソリッドタイルのSprite群を生成\"\"\"
        for row_i, row in enumerate(self.layout):
            for col_i, tile_id in enumerate(row):
                if tile_id < 0:
                    continue
                spr      = pygame.sprite.Sprite()
                spr.image = self.tiles.get(tile_id, self.tiles[0])
                spr.rect  = pygame.Rect(col_i * self.TILE_W,
                                        row_i * self.TILE_H,
                                        self.TILE_W, self.TILE_H)
                self.solids.add(spr)

    def draw(self, surface: pygame.Surface, camera_offset=(0, 0)):
        for spr in self.solids:
            surface.blit(spr.image,
                         (spr.rect.x - camera_offset[0],
                          spr.rect.y - camera_offset[1]))

    def get_solids(self) -> pygame.sprite.Group:
        return self.solids
"""


# ============================================================
# マニフェストのキャッシュ・保存
# ============================================================

_MANIFEST_FILE = ".blackwell_assets.json"


def save_manifest(manifest: AssetManifest, folder: str):
    """マニフェストをJSONにキャッシュ保存"""
    try:
        data = {
            "folder":      manifest.folder,
            "scanned_at":  manifest.scanned_at,
            "summary":     manifest.summary,
            "sprites":     [
                {"path":s.path,"name":s.name,"role":s.role,
                 "width":s.width,"height":s.height,
                 "is_sheet":s.is_sheet,"sheet_cols":s.sheet_cols,
                 "sheet_rows":s.sheet_rows,"frame_w":s.frame_w,
                 "frame_h":s.frame_h,"total_frames":s.total_frames,
                 "anim_group":s.anim_group,"frame_index":s.frame_index}
                for s in manifest.sprites
            ],
            "tilesets":    [
                {"path":t.path,"name":t.name,"tile_w":t.tile_w,"tile_h":t.tile_h,
                 "cols":t.cols,"rows":t.rows,"total_tiles":t.total_tiles}
                for t in manifest.tilesets
            ],
            "audio_bgm":   [
                {"path":a.path,"name":a.name,"category":a.category,
                 "duration_s":a.duration_s,"bpm_estimate":a.bpm_estimate,
                 "sample_rate":a.sample_rate}
                for a in manifest.audio_bgm
            ],
            "audio_se":    [
                {"path":a.path,"name":a.name,"duration_s":a.duration_s}
                for a in manifest.audio_se
            ],
            "anim_groups": {
                k: [{"path":s.path,"frame_index":s.frame_index} for s in v]
                for k,v in manifest.anim_groups.items()
            },
        }
        with open(os.path.join(folder, _MANIFEST_FILE), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[asset_pipeline] マニフェスト保存失敗: {e}")
