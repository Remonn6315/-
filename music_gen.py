"""
Blackwell Dev-OS — music_gen.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
② 音楽・SE自動生成

【2つのエンジン】
  A. AudioCraft（Meta）
     torchとaudiocraftがインストールされていれば使用。
     「ボス戦のBGM」などの説明から本物の音楽を生成。
     GPU推奨。初回モデルダウンロードに数分かかる。

  B. プロシージャル生成（フォールバック）
     numpy + scipy だけで動く。追加インストール不要。
     サイン波・ノイズ・エンベロープで
     ゲームで使えるBGMとSEを生成する。
     AudioCraftより品質は低いが今すぐ動く。

【生成できるもの】
  BGM:
    タイトル画面 / フィールド / 戦闘 / ボス / ダンジョン
    勝利 / ゲームオーバー / エンディング

  SE（効果音）:
    攻撃 / 被ダメージ / ジャンプ / アイテム取得
    扉開閉 / 爆発 / 魔法 / コイン / UI決定 / UIキャンセル

【Godot連携】
  生成したwavファイルをGodotプロジェクトに自動配置。
  AudioStreamPlayer用のGDScriptひな形も生成。

【公開API】
  generate_bgm(desc, scene_type, project_path) → AudioResult
  generate_se(se_type, project_path)           → AudioResult
  generate_batch(requests, project_path)       → list[AudioResult]
  list_generated(project_path)                 → list
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import math
import os
import struct
import time
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

# scipy は任意（エフェクト品質向上）
try:
    from scipy import signal as _sig
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# AudioCraft は任意（高品質生成）
try:
    from audiocraft.models import MusicGen
    from audiocraft.data.audio import audio_write
    HAS_AUDIOCRAFT = True
except ImportError:
    HAS_AUDIOCRAFT = False

BRAIN_DIR  = "blackwell_brain"
AUDIO_DIR  = "audio"           # プロジェクト内の音声フォルダ
SAMPLE_RATE = 44100
META_FILE  = "audio_meta.json"


# ============================================================
# データ構造
# ============================================================

@dataclass
class AudioResult:
    name:        str
    path:        str        # 保存先フルパス
    duration:    float      # 秒
    engine:      str        # "audiocraft" / "procedural"
    desc:        str
    timestamp:   str
    success:     bool
    error:       str = ""


# ============================================================
# ユーティリティ
# ============================================================

def _audio_dir(project_path: str) -> str:
    d = os.path.join(project_path, AUDIO_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _brain(project_path: str) -> str:
    d = os.path.join(project_path, BRAIN_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _now() -> str:
    return datetime.now().isoformat()[:16]


def _save_meta(project_path: str, result: AudioResult):
    path = os.path.join(_brain(project_path), META_FILE)
    existing = []
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                existing = json.load(f).get("files", [])
        except Exception:
            pass
    existing.append({
        "name":      result.name,
        "path":      result.path,
        "duration":  result.duration,
        "engine":    result.engine,
        "desc":      result.desc,
        "timestamp": result.timestamp,
    })
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"files": existing[-200:]}, f,
                  ensure_ascii=False, indent=2)


def _write_wav(path: str, samples: np.ndarray,
               sr: int = SAMPLE_RATE):
    """numpy配列をwavファイルに書き出す"""
    # -1.0〜1.0 → 16bit int
    samples = np.clip(samples, -1.0, 1.0)
    data    = (samples * 32767).astype(np.int16)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(data.tobytes())


# ============================================================
# AudioCraft エンジン
# ============================================================

def _gen_audiocraft(desc: str, duration: float,
                     output_path: str) -> bool:
    """AudioCraftでBGMを生成する"""
    try:
        print(f"[music_gen] AudioCraft生成: {desc[:40]}")
        model = MusicGen.get_pretrained("facebook/musicgen-small")
        model.set_generation_params(duration=duration)
        wav   = model.generate([desc])
        # audio_writeはtorchテンソルを受け取る
        audio_write(
            output_path.replace(".wav", ""),
            wav[0].cpu(), model.sample_rate,
            strategy="loudness",
        )
        return True
    except Exception as e:
        print(f"[music_gen] AudioCraft失敗: {e}")
        return False


# ============================================================
# プロシージャル生成エンジン
# ============================================================

# シーンタイプ別パラメータ
SCENE_PARAMS = {
    "title":     {"bpm":80, "scale":"major", "mood":"calm",    "dur":30},
    "field":     {"bpm":90, "scale":"major", "mood":"bright",  "dur":60},
    "battle":    {"bpm":140,"scale":"minor", "mood":"tense",   "dur":30},
    "boss":      {"bpm":160,"scale":"minor", "mood":"intense", "dur":45},
    "dungeon":   {"bpm":70, "scale":"minor", "mood":"dark",    "dur":45},
    "victory":   {"bpm":120,"scale":"major", "mood":"joyful",  "dur":8},
    "gameover":  {"bpm":60, "scale":"minor", "mood":"sad",     "dur":6},
    "ending":    {"bpm":75, "scale":"major", "mood":"epic",    "dur":60},
    "shop":      {"bpm":100,"scale":"major", "mood":"cheerful","dur":30},
    "mystery":   {"bpm":65, "scale":"minor", "mood":"eerie",   "dur":40},
}

# スケール定義（ルートからの半音数）
SCALES = {
    "major":       [0, 2, 4, 5, 7, 9, 11],
    "minor":       [0, 2, 3, 5, 7, 8, 10],
    "pentatonic":  [0, 2, 4, 7, 9],
    "dorian":      [0, 2, 3, 5, 7, 9, 10],
    "phrygian":    [0, 1, 3, 5, 7, 8, 10],
}

def _midi_to_hz(midi: int) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))

def _scale_notes(root_midi: int, scale_name: str,
                  octaves: int = 2) -> list:
    """スケール上の音をMIDIノート番号で返す"""
    intervals = SCALES.get(scale_name, SCALES["major"])
    notes = []
    for oct in range(octaves):
        for iv in intervals:
            notes.append(root_midi + oct * 12 + iv)
    return notes

def _envelope(n: int, attack: float = 0.01,
               decay: float = 0.1,
               sustain: float = 0.7,
               release: float = 0.2,
               sr: int = SAMPLE_RATE) -> np.ndarray:
    """ADSRエンベロープ"""
    env   = np.ones(n)
    a_end = int(attack  * sr)
    d_end = int((attack + decay) * sr)
    r_start = max(0, n - int(release * sr))

    if a_end > 0:
        env[:a_end] = np.linspace(0, 1, a_end)
    if d_end > a_end:
        env[a_end:d_end] = np.linspace(1, sustain, d_end - a_end)
    env[d_end:r_start] = sustain
    if r_start < n:
        env[r_start:] = np.linspace(sustain, 0, n - r_start)
    return env

def _sine(freq: float, duration: float,
           sr: int = SAMPLE_RATE) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return np.sin(2 * np.pi * freq * t)

def _square(freq: float, duration: float,
             sr: int = SAMPLE_RATE) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return np.sign(np.sin(2 * np.pi * freq * t)) * 0.5

def _sawtooth(freq: float, duration: float,
               sr: int = SAMPLE_RATE) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return (2.0 * (t * freq - np.floor(t * freq + 0.5))) * 0.5

def _noise(duration: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    n = int(sr * duration)
    return np.random.uniform(-1, 1, n) * 0.3

def _lowpass(samples: np.ndarray, cutoff: float,
              sr: int = SAMPLE_RATE) -> np.ndarray:
    if not HAS_SCIPY:
        # 簡易移動平均フィルタ
        k = max(1, int(sr / cutoff / 4))
        return np.convolve(samples, np.ones(k)/k, mode="same")
    sos = _sig.butter(4, cutoff / (sr/2), btype="low", output="sos")
    return _sig.sosfilt(sos, samples)

def _reverb(samples: np.ndarray, room: float = 0.3,
             sr: int = SAMPLE_RATE) -> np.ndarray:
    """簡易リバーブ（遅延+減衰の重ね合わせ）"""
    result = samples.copy().astype(float)
    delays = [int(0.03 * sr), int(0.05 * sr), int(0.08 * sr)]
    gains  = [0.4 * room, 0.25 * room, 0.15 * room]
    for d, g in zip(delays, gains):
        if d < len(samples):
            result[d:] += samples[:-d] * g
    return result


def _gen_bgm_procedural(scene_type: str,
                          duration: float,
                          output_path: str) -> bool:
    """プロシージャルにBGMを生成する"""
    params = SCENE_PARAMS.get(scene_type, SCENE_PARAMS["field"])
    bpm    = params["bpm"]
    scale  = params["scale"]
    mood   = params["mood"]
    sr     = SAMPLE_RATE

    # テンポ
    beat_sec   = 60.0 / bpm
    bar_sec    = beat_sec * 4
    total_n    = int(sr * duration)
    result     = np.zeros(total_n, dtype=float)

    # ルートノートとスケール
    root  = 48  # C3
    notes = _scale_notes(root, scale, octaves=2)

    rng = np.random.default_rng(hash(scene_type) % 2**32)

    # ── メロディーレイヤー ──────────────────────────
    mel_wave_fn = _square if mood in ("tense","intense","dark") else _sine
    note_dur    = beat_sec * (0.5 if bpm >= 140 else 1.0)
    pos = 0.0
    while pos < duration:
        note = rng.choice(notes)
        freq = _midi_to_hz(note)
        nd   = min(note_dur, duration - pos)
        seg  = mel_wave_fn(freq, nd, sr)
        seg  *= _envelope(len(seg), attack=0.01, decay=0.05,
                          sustain=0.6, release=0.1, sr=sr)
        seg  *= 0.35
        s, e = int(pos * sr), int(pos * sr) + len(seg)
        if e <= total_n:
            result[s:e] += seg
        pos += note_dur

    # ── ベースラインレイヤー ────────────────────────
    bass_notes = [root, root + 5, root + 7, root + 3]
    pos = 0.0
    bi  = 0
    while pos < duration:
        bn   = bass_notes[bi % len(bass_notes)]
        freq = _midi_to_hz(bn)
        seg  = _sawtooth(freq, bar_sec * 0.9, sr)
        seg  *= _envelope(len(seg), attack=0.02, decay=0.1,
                          sustain=0.5, release=0.2, sr=sr)
        seg  = _lowpass(seg, 800, sr)
        seg  *= 0.3
        s, e = int(pos * sr), int(pos * sr) + len(seg)
        if e <= total_n:
            result[s:e] += seg
        pos += bar_sec
        bi  += 1

    # ── パーカッションレイヤー ──────────────────────
    if mood in ("tense", "intense", "bright", "cheerful"):
        pos = 0.0
        while pos < duration:
            # キック（低域ノイズ）
            kick_n = int(0.05 * sr)
            kick   = _noise(0.05, sr)
            kick   *= _envelope(kick_n, attack=0.001, decay=0.04,
                                sustain=0, release=0.01, sr=sr)
            kick   = _lowpass(kick, 200, sr) * 0.6
            s = int(pos * sr)
            if s + kick_n <= total_n:
                result[s:s+kick_n] += kick

            # スネア（広域ノイズ）
            snare_pos = pos + beat_sec * 2
            snare_n   = int(0.04 * sr)
            snare     = _noise(0.04, sr)
            snare     *= _envelope(snare_n, attack=0.001, decay=0.03,
                                   sustain=0, release=0.01, sr=sr)
            snare     *= 0.35
            s2 = int(snare_pos * sr)
            if s2 + snare_n <= total_n:
                result[s2:s2+snare_n] += snare

            pos += bar_sec

    # ── エフェクト ──────────────────────────────────
    result = _reverb(result, room=0.2 if mood == "dark" else 0.1, sr=sr)

    # フェードイン・フェードアウト
    fade = int(sr * 1.5)
    if fade < total_n:
        result[:fade]  *= np.linspace(0, 1, fade)
        result[-fade:] *= np.linspace(1, 0, fade)

    # 正規化
    peak = np.max(np.abs(result))
    if peak > 0:
        result /= peak
    result *= 0.85

    _write_wav(output_path, result, sr)
    return True


# SE生成パラメータ
SE_GENERATORS = {
    "attack":     {"type":"noise_sweep",  "freq_start":800,  "freq_end":200, "dur":0.15, "amp":0.8},
    "damage":     {"type":"noise_drop",   "freq_start":400,  "freq_end":100, "dur":0.25, "amp":0.7},
    "jump":       {"type":"sine_up",      "freq_start":300,  "freq_end":600, "dur":0.18, "amp":0.6},
    "land":       {"type":"noise_burst",  "freq":200,        "dur":0.12,     "amp":0.65},
    "item":       {"type":"arpeggio",     "notes":[60,64,67,72],"dur":0.5,   "amp":0.55},
    "coin":       {"type":"arpeggio",     "notes":[72,76,79],   "dur":0.3,   "amp":0.55},
    "explosion":  {"type":"noise_long",   "dur":0.6,            "amp":0.9},
    "magic":      {"type":"sine_sweep",   "freq_start":200,  "freq_end":2000,"dur":0.5,  "amp":0.6},
    "door":       {"type":"noise_mid",    "freq":300,        "dur":0.4,      "amp":0.5},
    "ui_ok":      {"type":"arpeggio",     "notes":[67,71,74],   "dur":0.2,   "amp":0.45},
    "ui_cancel":  {"type":"sine_down",    "freq_start":500,  "freq_end":300, "dur":0.15, "amp":0.45},
    "levelup":    {"type":"arpeggio",     "notes":[60,64,67,72,76],"dur":0.7,"amp":0.6},
    "gameover_se":{"type":"sine_down",    "freq_start":440,  "freq_end":110, "dur":1.0,  "amp":0.7},
}


def _gen_se(se_type: str, output_path: str) -> bool:
    """効果音をプロシージャルに生成"""
    params = SE_GENERATORS.get(se_type)
    if not params:
        # 未知のタイプはデフォルトを使う
        params = SE_GENERATORS["ui_ok"]

    sr     = SAMPLE_RATE
    t_type = params["type"]
    dur    = params.get("dur", 0.2)
    amp    = params.get("amp", 0.6)
    n      = int(sr * dur)
    result = np.zeros(n, dtype=float)

    if t_type == "noise_sweep":
        f0, f1 = params["freq_start"], params["freq_end"]
        t  = np.linspace(0, dur, n)
        ph = 2 * np.pi * np.cumsum(np.linspace(f0, f1, n)) / sr
        result = np.sin(ph) * 0.5 + np.random.uniform(-0.5, 0.5, n) * 0.5

    elif t_type in ("noise_drop", "noise_burst", "noise_long", "noise_mid"):
        result = np.random.uniform(-1, 1, n)
        fc = params.get("freq", 500)
        result = _lowpass(result, fc, sr)

    elif t_type in ("sine_up", "sine_down", "sine_sweep"):
        f0 = params.get("freq_start", 300)
        f1 = params.get("freq_end",   600)
        ph = 2 * np.pi * np.cumsum(np.linspace(f0, f1, n)) / sr
        result = np.sin(ph)

    elif t_type == "arpeggio":
        notes    = params.get("notes", [60, 64, 67])
        note_dur = dur / len(notes)
        for i, m in enumerate(notes):
            freq = _midi_to_hz(m)
            nd   = int(note_dur * sr)
            seg  = _sine(freq, note_dur, sr)
            seg  *= _envelope(len(seg), attack=0.01, decay=0.05,
                              sustain=0.6, release=0.1, sr=sr)
            s = i * nd
            if s + nd <= n:
                result[s:s+nd] += seg

    # エンベロープ適用
    env = _envelope(n, attack=0.005, decay=0.1,
                    sustain=0.5, release=0.15, sr=sr)
    result *= env * amp

    # 正規化
    peak = np.max(np.abs(result))
    if peak > 0:
        result = result / peak * amp

    _write_wav(output_path, result, sr)
    return True


# ============================================================
# Ollama でシーンパラメータを自動設定
# ============================================================

def _ai_guess_params(desc: str) -> dict:
    """
    自然言語の説明からBGMパラメータをAIに推測させる
    """
    try:
        import ollama
        prompt = (
            f"以下のゲームシーンのBGMパラメータをJSONで出力してください。\n"
            f"シーン説明: {desc}\n\n"
            "JSONのみ（前置き不要）:\n"
            "{\n"
            '  "scene_type": "battle/boss/field/title/dungeon/victory/gameover/shop/mystery/ending のいずれか",\n'
            '  "bpm": 60から200の整数,\n'
            '  "scale": "major/minor/pentatonic/dorian/phrygian のいずれか",\n'
            '  "duration": 秒数（整数）\n'
            "}"
        )
        res = ollama.chat(
            model="qwen2.5-coder:14b",
            messages=[{"role": "user", "content": prompt}]
        )
        import re
        m = re.search(r"\{.*\}", res["message"]["content"], re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return {}


# ============================================================
# 公開API
# ============================================================

def generate_bgm(desc: str,
                  scene_type: str = "field",
                  project_path: str = "./",
                  duration: float = 0,
                  use_ai_params: bool = True) -> AudioResult:
    """
    BGMを生成してプロジェクトのaudioフォルダに保存する。

    desc: 「ボスとの最終決戦、壮大でダークな音楽」など
    scene_type: SCENE_PARAMS のキー
    duration: 0の場合はシーンタイプのデフォルト値を使う
    """
    # AIでパラメータを補完
    if use_ai_params and desc:
        ai_params = _ai_guess_params(desc)
        if ai_params.get("scene_type"):
            scene_type = ai_params["scene_type"]
        if ai_params.get("bpm") and scene_type in SCENE_PARAMS:
            SCENE_PARAMS[scene_type] = {
                **SCENE_PARAMS[scene_type],
                "bpm":   int(ai_params["bpm"]),
                "scale": ai_params.get("scale", SCENE_PARAMS[scene_type]["scale"]),
            }
        if ai_params.get("duration"):
            duration = float(ai_params["duration"])

    if not duration:
        duration = float(SCENE_PARAMS.get(scene_type, SCENE_PARAMS["field"])["dur"])

    name       = f"bgm_{scene_type}_{datetime.now().strftime('%H%M%S')}.wav"
    out_path   = os.path.join(_audio_dir(project_path), name)
    engine     = "audiocraft"
    success    = False
    error      = ""

    # AudioCraft → プロシージャルの順で試行
    if HAS_AUDIOCRAFT:
        success = _gen_audiocraft(desc or scene_type, duration, out_path)

    if not success:
        engine  = "procedural"
        try:
            success = _gen_bgm_procedural(scene_type, duration, out_path)
        except Exception as e:
            error   = str(e)
            success = False

    result = AudioResult(
        name=name, path=out_path, duration=duration,
        engine=engine, desc=desc or scene_type,
        timestamp=_now(), success=success, error=error,
    )
    if success:
        _save_meta(project_path, result)
        print(f"[music_gen] ✅ BGM生成: {name} ({engine})")
    else:
        print(f"[music_gen] ❌ BGM生成失敗: {error}")
    return result


def generate_se(se_type: str,
                 project_path: str = "./") -> AudioResult:
    """効果音を生成する"""
    name     = f"se_{se_type}.wav"
    out_path = os.path.join(_audio_dir(project_path), name)
    error    = ""
    try:
        success = _gen_se(se_type, out_path)
    except Exception as e:
        success = False
        error   = str(e)

    result = AudioResult(
        name=name, path=out_path, duration=0.5,
        engine="procedural", desc=f"SE: {se_type}",
        timestamp=_now(), success=success, error=error,
    )
    if success:
        _save_meta(project_path, result)
        print(f"[music_gen] ✅ SE生成: {name}")
    return result


def generate_batch(requests: list,
                    project_path: str = "./") -> list:
    """
    複数の音声を一括生成する。
    requests: [{"type": "bgm", "scene": "battle", "desc": "..."},
               {"type": "se",  "se_type": "jump"}, ...]
    """
    results = []
    for req in requests:
        if req.get("type") == "bgm":
            r = generate_bgm(
                req.get("desc", ""),
                req.get("scene", "field"),
                project_path,
            )
        else:
            r = generate_se(req.get("se_type", "ui_ok"), project_path)
        results.append(r)
        time.sleep(0.1)   # 連続生成の間隔
    return results


def list_generated(project_path: str) -> list:
    """生成済み音声ファイルの一覧を返す"""
    brain = _brain(project_path)
    path  = os.path.join(brain, META_FILE)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return list(reversed(json.load(f).get("files", [])))
    except Exception:
        return []


def generate_gdscript(project_path: str) -> str:
    """
    生成済み音声ファイルを使うGDScriptを生成する
    """
    files = list_generated(project_path)
    bgms  = [f for f in files if f["name"].startswith("bgm_")]
    ses   = [f for f in files if f["name"].startswith("se_")]

    bgm_preloads_lines = []
    for f in bgms[:10]:
        var_name = f["name"].replace(".wav","").replace("bgm_","")
        bgm_preloads_lines.append(
            f'\t@onready var bgm_{var_name} = preload("res://audio/{f["name"]}")')
    bgm_preloads = "\n".join(bgm_preloads_lines)

    se_preloads_lines = []
    for f in ses[:20]:
        var_name = f["name"].replace(".wav","").replace("se_","")
        se_preloads_lines.append(
            f'\t@onready var se_{var_name} = preload("res://audio/{f["name"]}")')
    se_preloads = "\n".join(se_preloads_lines)

    return f'''## Blackwell 自動生成 — AudioManager.gd
## {_now()} に生成
extends Node

@onready var bgm_player := AudioStreamPlayer.new()
@onready var se_player  := AudioStreamPlayer.new()

## 生成済みBGM
{bgm_preloads}

## 生成済みSE
{se_preloads}

func _ready() -> void:
\tadd_child(bgm_player)
\tadd_child(se_player)
\tbgm_player.volume_db = -6.0


func play_bgm(stream: AudioStream, fade_in: bool = true) -> void:
\tif bgm_player.playing:
\t\tbgm_player.stop()
\tbgm_player.stream = stream
\tbgm_player.play()


func play_se(stream: AudioStream) -> void:
\tse_player.stream = stream
\tse_player.play()


func stop_bgm() -> void:
\tbgm_player.stop()
'''
