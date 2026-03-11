"""
AIVtuber — memory.py v2.0
━━━━━━━━━━━━━━━━━━━━━━━━━
永久記憶システム（配信をまたいで蓄積）

【4層構造】
  Layer 1: viewers.json     視聴者DB（永久）
  Layer 2: sessions.json    配信履歴（永久）
  Layer 3: episodes.json    思い出エピソード（永久）
  Layer 4: self_growth.json 自己成長ログ（永久）

【設計思想】
  - 全記憶は感情タグ付きで保存
  - LLMに渡すコンテキストを自動生成
  - 視聴者ごとに「この人だからこそ」の返答が可能
  - 自動計算 + 手動上書きの両方に対応

【公開API】
  get_viewer(username)              → ViewerProfile
  update_viewer(username, comment, emotion) → None
  record_session_start()            → str  (session_id)
  record_session_end(session_id, highlights) → None
  record_episode(username, text, emotion, memorable) → None
  get_llm_context(username)         → str  LLMに渡す文字列
  get_stream_context()              → str  今の配信コンテキスト
  add_peak_moment(text)             → None
  get_viewer_list(rank)             → list
  set_viewer_rank(username, rank)   → None  手動上書き
  get_stats()                       → dict
"""

import json, os, time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


MEMORY_DIR = Path("./vtuber_memory")

# 仲良し度スコアのしきい値
INTIMACY_THRESHOLDS = {
    "新規":   0.0,
    "常連":   0.3,
    "親友":   0.6,
    "VIP":    0.85,
}


@dataclass
class ViewerProfile:
    username:         str
    visits:           int   = 0
    total_comments:   int   = 0
    first_seen:       str   = ""
    last_seen:        str   = ""
    rank:             str   = "新規"        # 自動 or 手動上書き
    rank_manual:      bool  = False          # 手動上書きフラグ
    intimacy:         float = 0.0           # 0.0〜1.0
    known_topics:     list  = field(default_factory=list)
    notable_comments: list  = field(default_factory=list)
    nickname:         str   = ""            # 手動設定
    can_tease:        bool  = False         # いじっていいか
    notes:            str   = ""            # 手動メモ
    superchat_total:  int   = 0             # スパチャ累計回数
    last_emotions:    list  = field(default_factory=list)  # 直近5感情
    peak_moments:     list  = field(default_factory=list)  # 盛り上がり記録

    def display_name(self) -> str:
        return self.nickname if self.nickname else self.username

    def to_dict(self):
        return asdict(self)


@dataclass
class SessionRecord:
    session_id:   str
    start_time:   str
    end_time:     str   = ""
    duration_min: float = 0.0
    peak_moments: list  = field(default_factory=list)
    top_viewers:  list  = field(default_factory=list)
    hot_topics:   list  = field(default_factory=list)
    total_comments: int = 0
    mood_summary: str   = ""

    def to_dict(self):
        return asdict(self)


class MemorySystem:
    def __init__(self, memory_dir: str = "./vtuber_memory"):
        self._dir = Path(memory_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

        self._viewers:     dict = self._load("viewers.json",     {})
        self._sessions:    list = self._load("sessions.json",    [])
        self._episodes:    list = self._load("episodes.json",    [])
        self._self_growth: dict = self._load("self_growth.json", {
            "total_sessions":    0,
            "total_comments":    0,
            "favorite_topics":   [],
            "avoid_patterns":    [],
            "peak_moments":      [],
            "personality_notes": "",
            "created_at":        self._now(),
        })

        # 今の配信の一時記憶
        self._current_session_id:  str  = ""
        self._current_comments:    list = []
        self._current_hot_topics:  dict = {}
        self._session_start_time:  float = 0.0

    # ── ファイルIO ────────────────────────────────

    def _load(self, filename: str, default):
        path = self._dir / filename
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return default

    def _save_all(self):
        self._save("viewers.json",     self._viewers)
        self._save("sessions.json",    self._sessions[-200:])  # 最新200配信
        self._save("episodes.json",    self._episodes[-500:])  # 最新500エピソード
        self._save("self_growth.json", self._self_growth)

    def _save(self, filename: str, data):
        path = self._dir / filename
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _today() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    # ── 視聴者管理 ────────────────────────────────

    def get_viewer(self, username: str) -> ViewerProfile:
        data = self._viewers.get(username)
        if data:
            return ViewerProfile(**{
                k: v for k, v in data.items()
                if k in ViewerProfile.__dataclass_fields__
            })
        return ViewerProfile(username=username)

    def update_viewer(self, username: str, comment: str,
                       emotion: str = "neutral",
                       is_superchat: bool = False):
        """コメントを受け取るたびに視聴者情報を更新"""
        v = self.get_viewer(username)

        # 基本カウント
        v.total_comments += 1
        v.last_seen       = self._today()
        if not v.first_seen:
            v.first_seen  = self._today()
            v.visits      = 1
        if is_superchat:
            v.superchat_total += 1

        # 感情履歴（直近5件）
        v.last_emotions.append(emotion)
        v.last_emotions = v.last_emotions[-5:]

        # 注目コメント（驚き・感動・盛り上がりのもの）
        if emotion in ("joy","excited","surprise") and len(comment) > 5:
            v.notable_comments.append(comment[:60])
            v.notable_comments = v.notable_comments[-10:]

        # トピック抽出（簡易）
        topics = self._extract_topics(comment)
        for t in topics:
            if t not in v.known_topics:
                v.known_topics.append(t)
        v.known_topics = v.known_topics[-15:]

        # 仲良し度を自動計算（手動上書きがなければ）
        if not v.rank_manual:
            v.intimacy = self._calc_intimacy(v)
            v.rank     = self._calc_rank(v.intimacy)

        # いじっていいか自動判定（仲良し度0.5以上で初期ON）
        if v.intimacy >= 0.5 and not v.can_tease:
            v.can_tease = True

        self._viewers[username] = v.to_dict()
        self._auto_save_debounced()

    def _calc_intimacy(self, v: ViewerProfile) -> float:
        """来た回数・コメント数・スパチャから仲良し度を計算"""
        score  = 0.0
        score += min(0.4, v.visits        * 0.02)   # 最大0.4
        score += min(0.3, v.total_comments * 0.001)  # 最大0.3
        score += min(0.3, v.superchat_total * 0.1)   # 最大0.3
        return round(min(1.0, score), 3)

    def _calc_rank(self, intimacy: float) -> str:
        rank = "新規"
        for r, threshold in sorted(
                INTIMACY_THRESHOLDS.items(), key=lambda x: x[1]):
            if intimacy >= threshold:
                rank = r
        return rank

    def set_viewer_rank(self, username: str, rank: str,
                         nickname: str = "", notes: str = "",
                         can_tease: bool = None):
        """手動でランク・ニックネーム・メモを設定"""
        v = self.get_viewer(username)
        v.rank        = rank
        v.rank_manual = True
        if nickname:
            v.nickname = nickname
        if notes:
            v.notes = notes
        if can_tease is not None:
            v.can_tease = can_tease
        self._viewers[username] = v.to_dict()
        self._save("viewers.json", self._viewers)

    def record_visit(self, username: str):
        """配信開始時・新規入場時に訪問回数を加算"""
        v = self.get_viewer(username)
        v.visits += 1
        self._viewers[username] = v.to_dict()

    # ── 配信セッション ────────────────────────────

    def record_session_start(self) -> str:
        session_id = datetime.now().strftime("session_%Y%m%d_%H%M%S")
        self._current_session_id = session_id
        self._current_comments   = []
        self._current_hot_topics = {}
        self._session_start_time = time.time()
        print(f"[memory] 配信開始: {session_id}")
        return session_id

    def record_session_end(self, highlights: list = None):
        if not self._current_session_id:
            return
        duration = (time.time() - self._session_start_time) / 60
        top_viewers = self._get_top_viewers_this_session()
        hot_topics  = sorted(self._current_hot_topics.items(),
                              key=lambda x: x[1], reverse=True)[:5]

        # AIで配信サマリーを生成
        mood = self._ai_mood_summary()

        record = SessionRecord(
            session_id    = self._current_session_id,
            start_time    = datetime.fromtimestamp(
                self._session_start_time).strftime("%Y-%m-%d %H:%M"),
            end_time      = self._now(),
            duration_min  = round(duration, 1),
            peak_moments  = highlights or [],
            top_viewers   = top_viewers,
            hot_topics    = [t for t, _ in hot_topics],
            total_comments= len(self._current_comments),
            mood_summary  = mood,
        )
        self._sessions.append(record.to_dict())

        # self_growthに反映
        self._self_growth["total_sessions"] += 1
        self._self_growth["total_comments"] += len(self._current_comments)
        for topic, count in hot_topics[:3]:
            favs = self._self_growth.get("favorite_topics", [])
            if topic not in favs:
                favs.append(topic)
            self._self_growth["favorite_topics"] = favs[-20:]

        self._save_all()
        print(f"[memory] 配信終了: {duration:.0f}分 / {len(self._current_comments)}コメント")

    def _get_top_viewers_this_session(self) -> list:
        counts = {}
        for c in self._current_comments:
            counts[c["username"]] = counts.get(c["username"], 0) + 1
        return sorted(counts.keys(), key=lambda u: counts[u], reverse=True)[:5]

    def _ai_mood_summary(self) -> str:
        """今日の配信の雰囲気をAIに一言でまとめてもらう"""
        try:
            import ollama
            recent = self._current_comments[-20:]
            texts  = [f"{c['username']}: {c['text']}" for c in recent]
            res = ollama.chat(
                model="qwen2.5-coder:14b",
                messages=[{"role":"user","content":
                    f"この配信の雰囲気を15文字以内で:\n" + "\n".join(texts)}]
            )
            return res["message"]["content"].strip()[:30]
        except Exception:
            return ""

    # ── エピソード記録 ────────────────────────────

    def record_episode(self, username: str, text: str,
                        emotion: str, memorable: bool = False):
        """盛り上がった瞬間・思い出になりそうな会話を記録"""
        episode = {
            "date":      self._today(),
            "session":   self._current_session_id,
            "username":  username,
            "text":      text[:100],
            "emotion":   emotion,
            "memorable": memorable,
        }
        self._episodes.append(episode)

        # 視聴者のpeak_momentsにも追加
        if memorable and username in self._viewers:
            v = self.get_viewer(username)
            v.peak_moments.append(f"{self._today()}: {text[:40]}")
            v.peak_moments = v.peak_moments[-5:]
            self._viewers[username] = v.to_dict()

        # self_growthのpeak_momentsにも
        if memorable:
            self._self_growth.setdefault("peak_moments", [])
            self._self_growth["peak_moments"].append(
                f"{self._today()} {username}: {text[:40]}")
            self._self_growth["peak_moments"] = \
                self._self_growth["peak_moments"][-30:]

    def add_peak_moment(self, text: str):
        """配信中の盛り上がりを手動で記録"""
        self._self_growth.setdefault("peak_moments", [])
        self._self_growth["peak_moments"].append(
            f"{self._now()}: {text[:60]}")
        self._self_growth["peak_moments"] = \
            self._self_growth["peak_moments"][-30:]

    # ── トピック管理 ──────────────────────────────

    def _extract_topics(self, text: str) -> list:
        """コメントから話題キーワードを簡易抽出"""
        TOPIC_KEYWORDS = {
            "ゲーム":   ["ゲーム","プレイ","クリア","レベル","ボス","RPG"],
            "食べ物":   ["ラーメン","ご飯","食べ","うまい","美味","おいしい"],
            "AI":       ["AI","人工知能","ChatGPT","Ollama","LLM"],
            "音楽":     ["音楽","歌","曲","BGM","ライブ"],
            "アニメ":   ["アニメ","漫画","マンガ","推し","キャラ"],
            "雑談":     ["今日","最近","ところで","そういえば"],
        }
        found = []
        for topic, kws in TOPIC_KEYWORDS.items():
            if any(kw in text for kw in kws):
                found.append(topic)
                self._current_hot_topics[topic] = \
                    self._current_hot_topics.get(topic, 0) + 1
        return found

    def track_comment(self, username: str, text: str, emotion: str):
        """配信内コメントをトラッキング"""
        self._current_comments.append({
            "username": username,
            "text":     text[:80],
            "emotion":  emotion,
            "time":     self._now(),
        })
        self._extract_topics(text)

    # ── LLMコンテキスト生成 ───────────────────────

    def get_llm_context(self, username: str) -> str:
        """
        LLMに渡す視聴者コンテキストを自動生成。
        「この人だからこそ」の返答を引き出す。
        """
        v = self.get_viewer(username)
        lines = []

        # 視聴者情報
        if v.visits > 0:
            name = v.display_name()
            lines.append(f"視聴者「{name}」の情報:")
            lines.append(f"  ランク: {v.rank} / 仲良し度: {v.intimacy:.0%}")
            lines.append(f"  来場回数: {v.visits}回 / 総コメント: {v.total_comments}件")
            if v.first_seen:
                lines.append(f"  初来場: {v.first_seen}")
            if v.known_topics:
                lines.append(f"  話題にする傾向: {', '.join(v.known_topics[:5])}")
            if v.notable_comments:
                lines.append(f"  印象的なコメント: 「{v.notable_comments[-1]}」")
            if v.peak_moments:
                lines.append(f"  思い出: {v.peak_moments[-1]}")
            if v.notes:
                lines.append(f"  メモ: {v.notes}")
            if v.can_tease:
                lines.append("  ※この人とはいじり合いOK")
            if v.superchat_total > 0:
                lines.append(f"  スパチャ累計: {v.superchat_total}回（感謝！）")
        else:
            lines.append(f"「{username}」は今日初めて来た新規視聴者。")

        return "\n".join(lines)

    def get_stream_context(self) -> str:
        """今の配信の状況コンテキスト"""
        lines = []
        if self._current_hot_topics:
            hot = sorted(self._current_hot_topics.items(),
                          key=lambda x: x[1], reverse=True)[:3]
            lines.append(f"今の配信で盛り上がってる話題: {', '.join(t for t,_ in hot)}")
        if self._current_comments:
            recent = self._current_comments[-3:]
            lines.append("直近の会話:")
            for c in recent:
                lines.append(f"  {c['username']}: {c['text']}")
        if self._self_growth.get("peak_moments"):
            lines.append(f"過去の名シーン: {self._self_growth['peak_moments'][-1]}")
        return "\n".join(lines)

    def get_self_context(self) -> str:
        """自分自身の成長・傾向コンテキスト"""
        sg = self._self_growth
        lines = [
            f"配信歴: {sg.get('total_sessions',0)}回",
            f"好きな話題: {', '.join(sg.get('favorite_topics',[])[:5])}",
        ]
        if sg.get("personality_notes"):
            lines.append(f"最近の自分: {sg['personality_notes']}")
        return "\n".join(lines)

    # ── 統計 ─────────────────────────────────────

    def get_viewer_list(self, rank: str = None) -> list:
        viewers = []
        for username, data in self._viewers.items():
            v = ViewerProfile(**{
                k: v for k, v in data.items()
                if k in ViewerProfile.__dataclass_fields__
            })
            if rank is None or v.rank == rank:
                viewers.append(v)
        return sorted(viewers, key=lambda v: v.intimacy, reverse=True)

    def get_stats(self) -> dict:
        sg = self._self_growth
        return {
            "total_viewers":  len(self._viewers),
            "total_sessions": sg.get("total_sessions", 0),
            "total_comments": sg.get("total_comments", 0),
            "vip_count":      sum(1 for v in self._viewers.values()
                                   if v.get("rank") == "VIP"),
            "regular_count":  sum(1 for v in self._viewers.values()
                                   if v.get("rank") == "常連"),
            "favorite_topics": sg.get("favorite_topics", [])[:5],
        }

    # ── 自動保存（デバウンス）────────────────────

    _save_counter = 0

    def _auto_save_debounced(self):
        self._save_counter += 1
        if self._save_counter >= 10:
            self._save_counter = 0
            self._save("viewers.json", self._viewers)
