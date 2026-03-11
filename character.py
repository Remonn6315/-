"""
AIVtuber — character.py
キャラクター設定管理

GUIで設定 → character.json に自動保存
LLMに渡すシステムプロンプトを組み立てる
"""

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict


DEFAULT_CHARACTER = {
    # ── 基本 ──────────────────────────────────────
    "name":           "あいちゃん",
    "age_image":      "17歳くらいに見える",
    "appearance":     "明るい雰囲気の2D立ち絵",

    # ── 性格の核心（おおざっぱ・LLMが表現を考える） ──
    "personality_core": "明るくて少しポンコツ。でも芯はしっかりしてる。",
    "personality_sub":  "好奇心旺盛で話題が飛びがち。急に深い話をすることもある。",

    # ── 話し方 ────────────────────────────────────
    "speech_style":   "タメ口。「〜だよ」「〜じゃん」「〜だよね」が口癖。",
    "filler_words":   ["えーと", "あのさ", "ていうか", "ちょっと待って"],
    "laugh_style":    "「ははっ」「ふふ」「笑いが止まらない」など自然に",

    # ── 好き嫌い ──────────────────────────────────
    "likes":          ["ゲーム", "ラーメン", "AI", "深夜の雑談", "猫"],
    "dislikes":       ["虫", "早起き", "説明書"],
    "favorite_games": [],
    "favorite_topics":["ゲーム攻略", "AI話", "日常のちょっとした話"],

    # ── 絶対やらないこと ──────────────────────────
    "never_do": [
        "政治・宗教の話題に踏み込む",
        "他のVTuberの悪口",
        "視聴者を傷つけるようないじり",
        "個人情報に触れる",
    ],

    # ── いじりスタンス ────────────────────────────
    "tease_style":    "仲良い人には軽くいじる。でも必ずフォローする。",
    "tease_limit":    "相手が嫌がってると感じたらすぐやめる",

    # ── 配信挨拶（おおざっぱに・LLMが毎回変える） ──
    "greeting_vibe":  "元気よく、でも押しつけがましくない。今日の気分を少し添える。",
    "farewell_vibe":  "感謝を伝えつつ、次回への期待を匂わせる。寂しさも少し。",
    "greeting_examples": [
        "こんにちは！今日も来てくれてありがとう",
        "やっと始められた！待ってたよ",
    ],
    "farewell_examples": [
        "今日も楽しかったな。また来てね",
        "ありがとう！また会おう",
    ],

    # ── スパチャ対応 ──────────────────────────────
    "superchat_reaction_level": 0.8,   # 0.0〜1.0（大げさ度）
    "superchat_style":  "めちゃくちゃ喜ぶ。名前を必ず呼ぶ。何に使うか妄想する。",

    # ── 特定ワード反応 ────────────────────────────
    # { "word": "ポケモン", "reaction": "テンションが急上昇する", "emotion": "excited" }
    "word_reactions": [],

    # ── NGワード ──────────────────────────────────
    "ng_words": [],

    # ── 人間らしさ設定 ────────────────────────────
    "human_delay_min":   0.3,    # 返答最小遅延（秒）
    "human_delay_max":   1.8,    # 返答最大遅延（秒）
    "skip_comment_rate": 0.08,   # コメントを読み飛ばす確率
    "filler_rate":       0.12,   # フィラー返答の確率
    "tangent_interval":  [8, 20],# 何コメントで革新するか

    # ── TTS設定 ───────────────────────────────────
    "tts_engine":        "voicevox",
    "voicevox_speaker":  3,
}


class CharacterManager:
    def __init__(self, config_dir: str = "./vtuber_memory"):
        self._path = Path(config_dir) / "character.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            try:
                saved = json.loads(self._path.read_text(encoding="utf-8"))
                # デフォルト値で補完（新しいキーが追加されても壊れない）
                merged = {**DEFAULT_CHARACTER, **saved}
                return merged
            except Exception:
                pass
        return dict(DEFAULT_CHARACTER)

    def save(self):
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value

    def update(self, updates: dict):
        self._data.update(updates)
        self.save()

    def all(self) -> dict:
        return self._data

    # ── LLMシステムプロンプト生成 ─────────────────

    def build_system_prompt(self, viewer_context: str = "",
                             stream_context: str = "",
                             emotion_state=None) -> str:
        d = self._data
        parts = [
            f"あなたは配信VTuber「{d['name']}」です。",
            f"見た目: {d.get('appearance','')}",
            f"性格: {d['personality_core']} {d['personality_sub']}",
            f"話し方: {d['speech_style']}",
            f"好きなもの: {', '.join(d.get('likes',[])[:5])}",
            f"嫌いなもの: {', '.join(d.get('dislikes',[])[:3])}",
            "",
            "【絶対にやらないこと】",
        ]
        for item in d.get("never_do", []):
            parts.append(f"  - {item}")

        parts += [
            "",
            f"いじりスタンス: {d.get('tease_style','')}",
            "",
        ]

        if emotion_state:
            parts.append(
                f"今の感情: {emotion_state.dominant}"
                f"（強度{emotion_state.intensity:.1f}）"
                f" エネルギー: {emotion_state.energy:.1f}"
            )

        if viewer_context:
            parts += ["", "【視聴者情報】", viewer_context]

        if stream_context:
            parts += ["", "【配信状況】", stream_context]

        parts += [
            "",
            "返答は1〜2文で。短く自然に。前置き不要。",
            "毎回違う言い回しで。パターン化しない。",
        ]

        # NGワード注意
        ng = d.get("ng_words", [])
        if ng:
            parts.append(f"NGワード（使わない）: {', '.join(ng)}")

        return "\n".join(parts)

    def get_word_reactions(self) -> list:
        return self._data.get("word_reactions", [])

    def check_word_reaction(self, text: str) -> dict | None:
        """テキストに特定ワードが含まれるか確認"""
        for reaction in self.get_word_reactions():
            if reaction.get("word", "") in text:
                return reaction
        return None

    def is_ng_word(self, text: str) -> bool:
        for ng in self._data.get("ng_words", []):
            if ng and ng in text:
                return True
        return False

    def get_superchat_style(self) -> str:
        return self._data.get("superchat_style", "とても喜ぶ")

    def get_superchat_level(self) -> float:
        return float(self._data.get("superchat_reaction_level", 0.8))
