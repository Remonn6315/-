"""
AIVtuber — emotion_engine.py
感情エンジン + 人格コア

8感情: joy / anger / sadness / surprise / shy / excited / bored / neutral
内部状態: energy（配信時間で減衰）/ tension（コメント量で変動）/ mood_bias（今日の気分）
"""

import random, time, json, re
from dataclasses import dataclass


@dataclass
class EmotionState:
    joy:       float = 0.3
    anger:     float = 0.0
    sadness:   float = 0.0
    surprise:  float = 0.0
    shy:       float = 0.0
    excited:   float = 0.5
    bored:     float = 0.0
    neutral:   float = 0.5
    energy:    float = 1.0
    tension:   float = 0.5
    mood_bias: float = 0.0
    dominant:  str   = "neutral"
    intensity: float = 0.5

    def to_dict(self):
        return {k: round(v, 2) if isinstance(v, float) else v
                for k, v in self.__dict__.items()}


class EmotionEngine:
    KEYWORDS = {
        "joy":      ["笑","w","草","ｗ","ワロタ","面白","すごい","最高","好き","かわいい","えらい","神","うれしい","ありがとう"],
        "anger":    ["嫌い","うざ","むかつく","最悪","クソ","バカ"],
        "sadness":  ["かわいそう","悲しい","つらい","泣","；；",";;","寂しい"],
        "surprise": ["え","!?","！？","マジ","うそ","びっくり","初めて","えっ"],
        "shy":      ["かわいい","好き","推し","結婚","照れ","ドキ"],
        "excited":  ["やばい","最強","テンション","アツい","待ってた","盛り上"],
    }

    def __init__(self):
        self.state              = EmotionState()
        self._start_time        = time.time()
        self._comment_count     = 0
        self._tangent_counter   = 0
        self._tangent_threshold = random.randint(8, 15)
        self.state.mood_bias    = random.uniform(-0.2, 0.7)

    # ── コメント処理 ────────────────────────────────

    def process_comment(self, text: str, username: str = "") -> EmotionState:
        self._comment_count   += 1
        self._tangent_counter += 1
        self.state.tension     = min(1.0, self.state.tension + 0.06)

        scores = self._kw_scores(text)
        ai     = self._ai_scores(text)
        for k in scores:
            scores[k] = max(scores[k], ai.get(k, 0))

        iner = 0.68
        em   = self.state.energy
        self.state.joy      = self._blend(self.state.joy,      scores["joy"],      iner, em)
        self.state.anger    = self._blend(self.state.anger,    scores["anger"],    iner, em)
        self.state.sadness  = self._blend(self.state.sadness,  scores["sadness"],  iner, em)
        self.state.surprise = self._blend(self.state.surprise, scores["surprise"], 0.35, em)
        self.state.shy      = self._blend(self.state.shy,      scores["shy"],      iner, em)
        self.state.excited  = self._blend(self.state.excited,  scores["excited"],  iner, em)

        # 気まぐれスパイク 1%
        if random.random() < 0.01:
            em2 = random.choice(["joy","surprise","excited"])
            setattr(self.state, em2, min(1.0, getattr(self.state, em2) + 0.4))

        self.state.joy = min(1.0, self.state.joy + max(0, self.state.mood_bias * 0.08))
        self._update_dominant()
        return self.state

    def _kw_scores(self, text: str) -> dict:
        s = {k: 0.0 for k in self.KEYWORDS}
        for emotion, kws in self.KEYWORDS.items():
            for kw in kws:
                if kw in text:
                    s[emotion] = min(1.0, s[emotion] + 0.35)
        return s

    def _ai_scores(self, text: str) -> dict:
        try:
            import ollama
            res = ollama.chat(
                model="qwen2.5-coder:14b",
                messages=[{"role":"user","content":
                    f"コメント「{text[:60]}」の感情スコアをJSONのみ出力:\n"
                    '{"joy":0.0,"anger":0.0,"sadness":0.0,"surprise":0.0,"shy":0.0,"excited":0.0}'}]
            )
            m = re.search(r"\{.*\}", res["message"]["content"], re.DOTALL)
            return json.loads(m.group(0)) if m else {}
        except Exception:
            return {}

    @staticmethod
    def _blend(cur, tgt, inertia, mult):
        return round(max(0.0, min(1.0, cur * inertia + tgt * (1 - inertia) * mult)), 3)

    # ── Tick（毎秒）────────────────────────────────

    def tick(self, delta: float = 1.0):
        d = 0.98 ** delta
        self.state.joy      *= d
        self.state.anger    *= d
        self.state.sadness  *= d
        self.state.surprise *= 0.82 ** delta
        self.state.shy      *= d
        self.state.excited  *= d
        self.state.tension   = max(0.1, self.state.tension * 0.995 ** delta)

        elapsed_h            = (time.time() - self._start_time) / 3600
        self.state.energy    = max(0.2, 1.0 - elapsed_h * 0.15)

        if self.state.tension < 0.3:
            self.state.bored = min(0.8, self.state.bored + 0.001 * delta)
        else:
            self.state.bored *= 0.99

        total = sum([self.state.joy, self.state.anger, self.state.sadness,
                     self.state.excited, self.state.shy])
        self.state.neutral = round(max(0.0, 1.0 - total), 3)
        self._update_dominant()

    def _update_dominant(self):
        ems = {k: getattr(self.state, k)
               for k in ["joy","anger","sadness","surprise","shy","excited","bored","neutral"]}
        self.state.dominant  = max(ems, key=ems.get)
        self.state.intensity = round(max(ems.values()), 3)

    # ── 手動オーバーライド ──────────────────────────

    def manual_override(self, emotion: str, value: float = 0.9):
        if hasattr(self.state, emotion):
            setattr(self.state, emotion, min(1.0, max(0.0, value)))
            self._update_dominant()

    def should_go_tangent(self) -> bool:
        if self._tangent_counter >= self._tangent_threshold:
            self._tangent_counter   = 0
            self._tangent_threshold = random.randint(8, 20)
            return True
        return self.state.bored > 0.6 and random.random() < 0.08

    def get_current_state(self) -> EmotionState:
        return self.state
