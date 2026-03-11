"""
Blackwell Dev-OS — task_decomposer.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
「やりたいこと」→ タスクリスト自動分解

「ローグライクを作りたい」と書くだけで
実装すべきファイル・タスク・依存順序を自動生成。
チェックリスト・自動実行キュー・優先度付きで出力。

【公開API】
  decompose(goal, anchor, engine, genre) → TaskPlan
  auto_queue(plan, autonomous_dev_fn)    → generator (進捗)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import json, re, os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Task:
    id:          str
    title:       str
    file:        str          # 生成するファイル名
    desc:        str          # Blackwellへの実装指示
    priority:    int          # 1=高 2=中 3=低
    depends_on:  list = field(default_factory=list)   # task id リスト
    status:      str  = "todo"   # todo / running / done / failed
    result:      str  = ""
    created_at:  str  = ""


@dataclass
class TaskPlan:
    goal:     str
    tasks:    list = field(default_factory=list)   # Task list
    engine:   str  = "godot4"
    genre:    str  = ""
    created:  str  = ""

    def done_count(self):
        return sum(1 for t in self.tasks if t.status == "done")

    def total(self):
        return len(self.tasks)

    def progress_pct(self):
        return int(self.done_count() / max(self.total(), 1) * 100)

    def next_tasks(self):
        """依存が全て完了している未着手タスクを返す"""
        done_ids = {t.id for t in self.tasks if t.status == "done"}
        return [
            t for t in self.tasks
            if t.status == "todo"
            and all(dep in done_ids for dep in t.depends_on)
        ]

    def to_dict(self):
        return {
            "goal": self.goal, "engine": self.engine, "genre": self.genre,
            "created": self.created,
            "tasks": [
                {"id": t.id, "title": t.title, "file": t.file,
                 "desc": t.desc, "priority": t.priority,
                 "depends_on": t.depends_on, "status": t.status,
                 "result": t.result[:200] if t.result else ""}
                for t in self.tasks
            ]
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TaskPlan":
        plan = cls(goal=d["goal"], engine=d.get("engine","godot4"),
                   genre=d.get("genre",""), created=d.get("created",""))
        for td in d.get("tasks", []):
            plan.tasks.append(Task(
                id=td["id"], title=td["title"], file=td["file"],
                desc=td["desc"], priority=td["priority"],
                depends_on=td.get("depends_on",[]),
                status=td.get("status","todo"), result=td.get("result","")
            ))
        return plan

    def save(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> Optional["TaskPlan"]:
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


# ── ジャンル別テンプレート（AIが使えないときのフォールバック）──
GENRE_TEMPLATES = {
    "2daction": [
        ("player",    "Player.gd",         "プレイヤーキャラクター（移動・ジャンプ・攻撃）を実装", 1, []),
        ("enemy",     "Enemy.gd",           "基本的な敵AI（巡回・プレイヤー追跡・攻撃）を実装",   1, []),
        ("camera",    "GameCamera.gd",      "プレイヤーを追いかけるカメラ（スムーズ追従）を実装",  2, ["player"]),
        ("hitbox",    "Hitbox.gd",          "攻撃判定・ダメージ処理の共通システムを実装",          1, ["player","enemy"]),
        ("ui",        "HUD.gd",             "HP・スコア・残機表示のHUDを実装",                    2, ["player"]),
        ("save",      "SaveSystem.gd",      "スコアとセーブデータの保存・読み込みを実装",          3, []),
        ("gamemgr",   "GameManager.gd",     "ゲーム状態管理（開始・ゲームオーバー・クリア）",     2, ["player","ui"]),
        ("effect",    "EffectManager.gd",   "ヒットエフェクト・パーティクルの管理を実装",         3, ["hitbox"]),
    ],
    "roguelike": [
        ("dungeon",   "DungeonGenerator.gd","ランダムダンジョン生成（部屋・廊下・配置）を実装",   1, []),
        ("player",    "Player.gd",          "ターン制プレイヤー（移動・攻撃・スタッツ）を実装",   1, []),
        ("enemy",     "EnemyAI.gd",         "ターン制敵AI（経路探索・行動パターン）を実装",        1, ["dungeon"]),
        ("item",      "ItemSystem.gd",      "アイテムシステム（生成・拾得・効果・識別）を実装",   1, []),
        ("fov",       "FieldOfView.gd",     "視野計算（FOV・霧戦争）を実装",                      2, ["dungeon"]),
        ("stats",     "StatsSystem.gd",     "ステータス（HP・攻撃・防御・経験値・レベル）を実装", 1, []),
        ("ui",        "RogueHUD.gd",        "メッセージログ・ステータス表示・インベントリUIを実装",2, ["stats","item"]),
        ("save",      "SaveSystem.gd",      "ローグライクセーブ（死亡時削除・継続プレイ）を実装", 2, []),
        ("floor",     "FloorManager.gd",    "階層管理（階段・フロア遷移・難易度スケール）を実装", 2, ["dungeon"]),
    ],
    "simulation": [
        ("world",     "WorldGrid.gd",       "グリッドベースのワールドシミュレーション基盤を実装", 1, []),
        ("agent",     "AgentBase.gd",       "エージェントAI（自律行動・ニーズ・状態機械）を実装", 1, ["world"]),
        ("economy",   "EconomySystem.gd",   "リソース生産・消費・取引システムを実装",              1, ["agent"]),
        ("ui",        "SimUI.gd",           "情報パネル・グラフ・コントロールUIを実装",            2, ["world"]),
        ("time",      "TimeSystem.gd",      "ゲーム内時間・昼夜サイクル・速度制御を実装",          2, []),
        ("event",     "EventSystem.gd",     "ランダムイベント・災害・チュートリアルを実装",        3, ["economy"]),
        ("save",      "SaveSystem.gd",      "シミュレーション状態の完全保存・復元を実装",          2, []),
    ],
    "towerdefense": [
        ("path",      "PathSystem.gd",      "敵の経路（ウェイポイント・A*パス）を実装",            1, []),
        ("enemy",     "EnemyWave.gd",       "ウェーブシステム（敵の種類・タイミング・強化）を実装",1, ["path"]),
        ("tower",     "TowerBase.gd",       "タワー基底クラス（攻撃・範囲・ターゲティング）を実装",1, []),
        ("towers",    "TowerTypes.gd",      "具体的なタワー種類（基本・狙撃・爆発・毒）を実装",   1, ["tower"]),
        ("economy",   "CurrencySystem.gd",  "コスト・報酬・アップグレードシステムを実装",          1, []),
        ("ui",        "TowerUI.gd",         "タワー設置パネル・ウェーブ情報・スコアUIを実装",      2, ["economy"]),
        ("gamemgr",   "GameManager.gd",     "ゲーム進行・ウェーブクリア・ゲームオーバー管理",     2, ["enemy","ui"]),
    ],
    "pygame_2d": [
        ("main",      "main.py",            "Pygameのメインループ（初期化・イベント・描画）を実装",1, []),
        ("player",    "player.py",          "プレイヤークラス（スプライト・移動・衝突）を実装",   1, ["main"]),
        ("enemy",     "enemy.py",           "敵クラス（AI・スポーン・スプライト）を実装",          1, ["main"]),
        ("level",     "level.py",           "レベル管理（タイルマップ・オブジェクト配置）を実装", 2, ["main"]),
        ("ui",        "ui.py",              "スコア・HP・ゲームオーバー画面UIを実装",              2, ["main"]),
        ("sound",     "sound_manager.py",   "BGM・SE管理（pygame.mixer活用）を実装",              3, []),
        ("save",      "save_system.py",     "スコアとプログレスのJSON保存・読み込みを実装",        3, []),
    ],
}

def decompose(
    goal: str,
    anchor: str = "",
    engine: str = "godot4",
    genre: str = "",
    use_ai: bool = True,
) -> TaskPlan:
    """
    ゴール文字列からタスクリストを自動生成する。
    use_ai=True の場合 Ollama で動的生成、False の場合テンプレートを使う。
    """
    plan = TaskPlan(goal=goal, engine=engine, genre=genre,
                    created=datetime.now().isoformat())

    if use_ai:
        try:
            plan = _decompose_with_ai(goal, anchor, engine, genre)
            if plan.tasks:
                return plan
        except Exception as e:
            print(f"[task_decomposer] AI分解失敗、テンプレートを使用: {e}")

    # テンプレートフォールバック
    return _decompose_with_template(goal, engine, genre, plan)


def _decompose_with_ai(goal: str, anchor: str, engine: str, genre: str) -> TaskPlan:
    """Ollamaを使ってタスクリストを動的生成"""
    import ollama

    ext = ".gd" if "godot" in engine else ".py" if "pygame" in engine else ".cs"
    anchor_line = f"【主軸】{anchor}\n" if anchor else ""
    genre_line  = f"【ジャンル】{genre}\n" if genre else ""

    prompt = (
        f"{anchor_line}{genre_line}"
        f"【ゴール】{goal}\n"
        f"【エンジン】{engine}\n\n"
        "このゲーム開発ゴールを達成するために必要なファイルとタスクを列挙してください。\n"
        "必ずJSON配列のみ出力してください（前置き・後付け・説明文は一切不要）:\n\n"
        "[\n"
        "  {\n"
        f'    "id": "task_001",\n'
        f'    "title": "タスクの短い名前",\n'
        f'    "file": "FileName{ext}",\n'
        f'    "desc": "Blackwellへの具体的な実装指示（日本語・詳細に）",\n'
        f'    "priority": 1,\n'
        f'    "depends_on": []\n'
        "  }\n"
        "]\n\n"
        "priority: 1=最優先(基盤) 2=中 3=後回し可\n"
        "depends_on: このタスクより先に完了すべきタスクのidリスト\n"
        "ファイルは5〜12個が適切。必ずJSONのみ。"
    )

    res = ollama.chat(
        model="qwen2.5-coder:14b",
        messages=[{"role": "user", "content": prompt}]
    )
    raw = res["message"]["content"]

    # JSON抽出
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        raise ValueError("JSONが見つかりません")

    tasks_data = json.loads(m.group(0))
    plan = TaskPlan(goal=goal, engine=engine, genre=genre,
                    created=datetime.now().isoformat())
    for i, td in enumerate(tasks_data):
        plan.tasks.append(Task(
            id=td.get("id", f"task_{i+1:03d}"),
            title=td.get("title", f"タスク{i+1}"),
            file=td.get("file", f"file_{i+1}{ext}"),
            desc=td.get("desc", ""),
            priority=int(td.get("priority", 2)),
            depends_on=td.get("depends_on", []),
            created_at=datetime.now().isoformat(),
        ))
    return plan


def _decompose_with_template(goal: str, engine: str, genre: str, plan: TaskPlan) -> TaskPlan:
    """テンプレートからタスクリストを生成"""
    # ジャンル自動判定
    if not genre:
        goal_lower = goal.lower()
        if any(k in goal_lower for k in ["ローグ","rogue","ダンジョン","dungeon"]):
            genre = "roguelike"
        elif any(k in goal_lower for k in ["タワー","tower","defense"]):
            genre = "towerdefense"
        elif any(k in goal_lower for k in ["シミュ","simu","経営","街"]):
            genre = "simulation"
        elif "pygame" in goal_lower or "pygame" in engine:
            genre = "pygame_2d"
        else:
            genre = "2daction"

    template = GENRE_TEMPLATES.get(genre, GENRE_TEMPLATES["2daction"])
    for tid, file, desc, priority, depends in template:
        plan.tasks.append(Task(
            id=tid, title=file.replace(".gd","").replace(".py",""),
            file=file, desc=f"【{goal}の一部として】{desc}",
            priority=priority, depends_on=depends,
            created_at=datetime.now().isoformat(),
        ))
    plan.genre = genre
    return plan


def auto_queue(plan: TaskPlan, autonomous_dev_fn, save_path: str = "./",
               anchor: str = "", max_parallel: int = 1):
    """
    タスクを依存順に自動実行するジェネレータ。
    各ステップで (task, result) を yield する。
    Streamlit の for ループで使う。
    """
    import threading

    task_plan_path = os.path.join(save_path, ".blackwell_taskplan.json")

    while True:
        nexts = plan.next_tasks()
        if not nexts:
            break

        # 優先度順に実行
        nexts.sort(key=lambda t: t.priority)
        task = nexts[0]
        task.status = "running"
        plan.save(task_plan_path)

        yield ("start", task, None)

        try:
            result = autonomous_dev_fn(
                goal=task.desc,
                auto_write=True,
                save_path=save_path,
                anchor=anchor,
                max_cycles=2,
            )
            task.status = "done"
            task.result = result[:500]
        except Exception as e:
            task.status = "failed"
            task.result = str(e)

        plan.save(task_plan_path)
        yield ("done", task, task.result)

    yield ("complete", None, f"全{plan.done_count()}/{plan.total()}タスク完了")
