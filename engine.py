"""
Blackwell Dev-OS - engine.py (完全版 v6.0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 1 追加:
  ⑥ インターネット検索統合
     - コード生成前に自動Web検索して最新情報を注入
     - 会話時にも検索コンテキストを自動付与
     - 時刻・日付を常に把握
  ⑦ スマート検索判定
     - 「今何時？」→ 時刻API
     - 「requests最新版」→ PyPI
     - 「GodotのOSS」→ GitHub Search
     - それ以外 → DuckDuckGo

app.py からインポートされる関数・変数（全て）:
  MODELS, get_execution_log, clear_execution_log,
  autonomous_dev, analyze_and_absorb,
  chat_with_persona, monitor_project, score_code,
  generate_image_sd, speak_voicevox, transcribe_whisper,
  aivtuber_respond, load_grand_state
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import ollama
import json
import re
import os
import ast
import difflib
import requests
import base64
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from memory import store_memory, retrieve_context

# Phase 1: プロジェクト地図 + 意図記憶
try:
    from project_map import (
        get_map_context, update_file_entry,
        auto_store_intent, get_map_stats, scan_project
    )
    _MAP_OK = True
except ImportError:
    _MAP_OK = False
    def get_map_context(p, t, f=""): return ""
    def update_file_entry(p, f): pass
    def auto_store_intent(p, f, c, t): pass
    def get_map_stats(p): return ""
    def scan_project(p): return None

# Phase 2: 契約記憶 + 完全履歴
try:
    from blackwell_history import (
        get_contract_warning, auto_register_contracts,
        update_contract_consumers, record_task_result,
        record_error, get_lessons, get_failure_warning,
    )
    _HISTORY_OK = True
except ImportError:
    _HISTORY_OK = False
    def get_contract_warning(p, f): return ""
    def auto_register_contracts(p, f, s, l=""): pass
    def update_contract_consumers(p, f, s): pass
    def record_task_result(p, f, t, c, sc, su, fb="", e=""): pass
    def record_error(p, f, t, e, c=""): pass
    def get_lessons(p, t, k=3): return ""
    def get_failure_warning(p, t): return ""

# Phase 3: 予測記憶 + 並列シミュレーション
try:
    from blackwell_prediction import (
        predict_risks, get_prediction_warning,
        record_parallel_result, get_parallel_insight,
    )
    _PREDICTION_OK = True
except ImportError:
    _PREDICTION_OK = False
    def predict_risks(p, f, c, t, m=""): return []
    def get_prediction_warning(p, f): return ""
    def record_parallel_result(p, t, f, cands, chosen, reason=""): pass
    def get_parallel_insight(p, t): return ""

# Phase 4: 自己対話ループ（Deep Thinking Engine）
try:
    from thinking_engine import (
        deep_think, estimate_complexity, select_model_by_complexity,
        format_thinking_log,
    )
    _THINKING_OK = True
except ImportError:
    _THINKING_OK = False
    def deep_think(d, s, c="", m="", md=None): return None
    def estimate_complexity(d, c=""): return 2
    def select_model_by_complexity(c, m): return m.get("coder", "")
    def format_thinking_log(r): return {}

# Phase 5: 学習データ自動収集
try:
    from training_collector import (
        collect as collect_training,
        should_finetune, get_stats as get_training_stats,
        export_for_finetuning, generate_modelfile,
        generate_finetune_script,
    )
    _TRAINING_OK = True
except ImportError:
    _TRAINING_OK = False
    def collect_training(p, t, c, sc, l="", tg=None, tl=None, f=""): return False
    def should_finetune(p): return False
    def get_training_stats(p): return {}
    def export_for_finetuning(p, ms=70): return ""
    def generate_modelfile(p, bm="", cm=""): return ""
    def generate_finetune_script(p, bm="", cm=""): return ""

# Phase 7: 自律実行スケジューラー
try:
    from autonomous_scheduler import (
        add_task as scheduler_add_task,
        add_tasks_bulk, get_backlog, get_next_tasks,
        mark_done as scheduler_mark_done,
        get_backlog_stats, get_night_status,
        get_morning_report, has_new_report, mark_report_read,
    )
    _SCHEDULER_OK = True
except ImportError:
    _SCHEDULER_OK = False
    def scheduler_add_task(p, ti, f, d, pr=2, dep=None): return ""
    def add_tasks_bulk(p, t): return []
    def get_backlog(p): return []
    def get_next_tasks(p, n=5): return []
    def scheduler_mark_done(p, tid, rs=""): pass
    def get_backlog_stats(p): return {}
    def get_night_status(p): return {}
    def get_morning_report(p): return ""
    def has_new_report(p): return False
    def mark_report_read(p): pass

# Phase 8: マルチエージェント協調
try:
    from agent_society import (
        coordinate as agent_coordinate,
        get_agent_stats, get_coordination_history,
        format_coordination_log,
    )
    _SOCIETY_OK = True
except ImportError:
    _SOCIETY_OK = False
    def agent_coordinate(d, a="", p="./", m="", mr=3, ig=False): return None
    def get_agent_stats(p): return {}
    def get_coordination_history(p, n=10): return []
    def format_coordination_log(r): return {}

# Phase 9: ゲームを自分でプレイして学習
try:
    from game_player import (
        analyze_and_fix_bytes, get_game_insights, get_play_history,
    )
    _PLAYER_OK = True
except ImportError:
    _PLAYER_OK = False
    def analyze_and_fix_bytes(b, p, a, af, m=""): return None
    def get_game_insights(p): return {}
    def get_play_history(p, n=10): return []

# Phase 10: 自己存在の最適化
try:
    from self_model import (
        rebuild_self_model, get_self_model, get_task_strategy,
        should_rebuild, update_trust, get_self_report,
    )
    _SELF_MODEL_OK = True
except ImportError:
    _SELF_MODEL_OK = False
    def rebuild_self_model(p, m=""): return None
    def get_self_model(p): return None
    def get_task_strategy(p, t): return None
    def should_rebuild(p): return False
    def update_trust(p, a, s): pass
    def get_self_report(p): return ""

# Godot Bridge: リアルタイム通信
try:
    from godot_bridge import (
        send_code as bridge_send_code,
        send_notification as bridge_notify,
        send_reload as bridge_reload,
        is_connected as bridge_connected,
        get_bridge_status,
    )
    _BRIDGE_OK = True
except ImportError:
    _BRIDGE_OK = False
    def bridge_send_code(f, c, a=True): return False
    def bridge_notify(m, l="info"): return False
    def bridge_reload(f=""): return False
    def bridge_connected(): return False
    def get_bridge_status(): return {}

# マルチプロジェクト知識ハブ
try:
    from knowledge_hub import (
        import_knowledge, register_project as hub_register,
        export_project as hub_export,
    )
    _HUB_OK = True
except ImportError:
    _HUB_OK = False
    def import_knowledge(p, t=""): return ""
    def hub_register(p, n="", g=""): pass
    def hub_export(p, n=""): return 0

# ドキュメント自動同期
try:
    from doc_sync import sync_on_task_complete as _doc_sync_task
    _DOC_SYNC_OK = True
except ImportError:
    _DOC_SYNC_OK = False
    def _doc_sync_task(p, a, f, t): pass

# バージョン管理AI
try:
    from gitops import auto_commit as _git_auto_commit
    _GIT_AI_OK = True
except ImportError:
    _GIT_AI_OK = False
    def _git_auto_commit(p, t="", f=None): return None

# Phase 6: プロンプト自己進化
try:
    from prompt_evolver import (
        analyze_and_evolve, apply_evolved_prompts,
        should_evolve, get_evolution_stats,
    )
    _EVOLVER_OK = True
except ImportError:
    _EVOLVER_OK = False
    def analyze_and_evolve(p, r, m=""): return None
    def apply_evolved_prompts(p, r, t=""): return r
    def should_evolve(p): return False
    def get_evolution_stats(p): return {}
from sandbox import run_safe
from gitops import commit_all
from internet import (
    build_search_context,
    smart_search,
    get_current_datetime,
    search_pypi,
    search_github,
    search_wikipedia,
)


# ============================================================
# ロール定義
# ============================================================
ROLES = {
    "planner": (
        "あなたは伝説的なソフトウェアアーキテクトです。\n"
        "ユーザーの指示とプロジェクト主軸を最優先に従い、\n"
        "実装すべきファイルとその内容を計画してください。\n\n"
        "必ずJSON配列のみ出力してください。前置き・解説は不要です。\n"
        '[{"file":"filename.py","desc":"具体的な実装内容の詳細説明"}]\n\n'
        "複数ファイルが必要な場合は複数要素を返してください。"
    ),
    "coder": (
        "あなたはエキスパートエンジニアです。\n"
        "既存コードと関連コンテキストを考慮し、\n"
        "変更箇所を含む完全なコードを出力してください。\n\n"
        "必ずコードブロック(```python ... ```)で出力してください。\n"
        "コメントは日本語で丁寧に書いてください。\n"
        "エラーハンドリングと型ヒントを必ず含めてください。"
    ),
    "refiner": (
        "あなたはデバッグの専門家です。\n"
        "エラーメッセージを分析し、最小限の修正で問題を解決してください。\n"
        "修正後のコード全体を必ずコードブロックで出力してください。\n"
        "修正箇所にはコメントで「# FIX: 理由」を付けてください。"
    ),
    "optimizer": (
        "あなたはリファクタリングの専門家です。\n"
        "機能・振る舞いを一切変えず、以下のみ改善してください:\n"
        "- 可読性の向上（変数名・コメント）\n"
        "- 安全性の向上（型ヒント・例外処理）\n"
        "- パフォーマンスの向上（不要な処理の削除）\n"
        "コードのみ出力してください。"
    ),
}


# ============================================================
# モデル定義
# ============================================================
MODELS = {
    "planner":   "qwen3-next:80b",
    "coder":     "qwen2.5-coder:32b",
    "refiner":   "deepseek-r1:32b",
    "optimizer": "qwen2.5-coder:14b",
    "chat":      "qwen3-next:80b",
}


# ============================================================
# ログ管理
# ============================================================
_execution_log = []


def _log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = "[{}] {}".format(timestamp, msg)
    _execution_log.append(entry)
    print(entry)


def get_execution_log():
    return list(_execution_log)


def clear_execution_log():
    _execution_log.clear()


# ============================================================
# ユーティリティ
# ============================================================

def _is_diff_output(text: str) -> bool:
    """AIの出力が差分形式かどうか判定する"""
    lines = text.strip().splitlines()[:10]
    diff_indicators = sum(1 for l in lines if l.startswith(("---","+++","@@","-","+")) and l.strip())
    return diff_indicators >= 3


def extract_code(text):
    # 差分ブロックを優先的に検出
    diff_m = re.search(r"```diff\n(.*?)```", text, re.DOTALL)
    if diff_m:
        return diff_m.group(1).strip()
    m = re.search(r"```(?:python|gdscript|javascript|typescript|csharp|gd)?\n(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def analyze_deps(code):
    try:
        tree = ast.parse(code)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    imports.append(n.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module.split(".")[0])
        return list(set(filter(None, imports)))
    except Exception:
        return []


def _extract_relevant_context(existing_code: str, task_desc: str, max_chars: int = 1500) -> str:
    """
    既存コードから タスクに関連する関数・クラスだけを抽出する。
    3000文字丸ごと渡す代わりに関連部分だけ渡すことで:
      - トークン数を大幅削減
      - AIが本当に必要な部分に集中できる
      - 精度向上
    """
    if not existing_code or len(existing_code) <= max_chars:
        return existing_code  # 短いファイルはそのまま

    desc_words = set(re.findall(r"\w+", task_desc.lower()))
    # 短すぎる単語・ストップワードを除外
    desc_words = {w for w in desc_words if len(w) > 3 and w not in {
        "する","した","して","ください","追加","実装","修正","変更",
        "this","that","with","from","import","func","def","class",
    }}

    lines      = existing_code.splitlines()
    lang       = _detect_code_language(existing_code)

    # Python: ASTで関数・クラス境界を正確に取得
    if lang in ("python", "python_pygame"):
        try:
            tree    = ast.parse(existing_code)
            blocks  = []  # (score, start_line, end_line, name)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    end   = getattr(node, "end_lineno", node.lineno + 20)
                    name  = node.name.lower()
                    # スコア計算: 名前・docstringにタスクキーワードが含まれるか
                    score = sum(1 for w in desc_words if w in name)
                    # docstringもチェック
                    if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and
                            node.body and isinstance(node.body[0], ast.Expr)):
                        doc = ast.literal_eval(node.body[0].value) if isinstance(node.body[0].value, ast.Constant) else ""
                        score += sum(1 for w in desc_words if w in str(doc).lower())
                    blocks.append((score, node.lineno - 1, end, name))

            # スコア順でソートして上位を取得
            blocks.sort(key=lambda x: -x[0])
            selected_lines = set()
            total_chars    = 0
            result_blocks  = []

            for score, start, end, name in blocks:
                block_text = "\n".join(lines[start:end])
                if total_chars + len(block_text) > max_chars:
                    break
                result_blocks.append((start, block_text))
                total_chars += len(block_text)
                if score == 0 and total_chars > max_chars // 2:
                    break

            if result_blocks:
                result_blocks.sort(key=lambda x: x[0])  # 行番号順に並び替え
                extracted = "\n\n".join(b for _, b in result_blocks)
                _log("🎯 関連コンテキスト抽出: {}文字 → {}文字 ({:.0f}%削減)".format(
                    len(existing_code), len(extracted),
                    (1 - len(extracted)/len(existing_code)) * 100
                ))
                return extracted
        except Exception:
            pass

    # GDScript / その他: 行ベースでfunc境界を検出
    func_blocks = []
    current_func_start = None
    current_func_name  = ""
    for i, line in enumerate(lines):
        m = re.match(r"^(func|def|class)\s+(\w+)", line)
        if m:
            if current_func_start is not None:
                func_blocks.append((current_func_name, current_func_start, i))
            current_func_start = i
            current_func_name  = m.group(2).lower()
    if current_func_start is not None:
        func_blocks.append((current_func_name, current_func_start, len(lines)))

    # 関連度でスコアリング
    scored = []
    for name, start, end in func_blocks:
        score = sum(1 for w in desc_words if w in name)
        block_text = "\n".join(lines[start:end])
        score += sum(1 for w in desc_words if w in block_text.lower()) // 3
        scored.append((score, start, end, block_text))

    scored.sort(key=lambda x: -x[0])
    total_chars   = 0
    result_parts  = []
    for score, start, end, block_text in scored:
        if total_chars + len(block_text) > max_chars:
            break
        result_parts.append((start, block_text))
        total_chars += len(block_text)

    if result_parts:
        result_parts.sort(key=lambda x: x[0])
        extracted = "\n\n".join(b for _, b in result_parts)
        _log("🎯 関連コンテキスト抽出(line): {}文字 → {}文字".format(
            len(existing_code), len(extracted)))
        return extracted

    # フォールバック: 先頭だけ返す
    return existing_code[:max_chars]



def apply_diff(old, new):
    diff = list(difflib.unified_diff(
        old.splitlines(), new.splitlines(),
        fromfile="before", tofile="after", lineterm=""
    ))
    return "\n".join(diff) if diff else "（変更なし）"




def load_grand_state(base_path="./"):
    candidates = [
        os.path.join(base_path, "project_grand_state.json"),
        "./project_grand_state.json",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                _log("WARNING grand_state 読込失敗: {}".format(e))
    return {
        "core_principles": "",
        "target_engine":   "Godot",
        "paths": {
            "code_export":  "C:/AI_Dev/Source",
            "asset_export": "C:/AI_Dev/Assets",
        },
        "sd_settings": {
            "api_url": "http://127.0.0.1:7860",
            "steps":   25,
            "width":   1024,
            "height":  1024,
        },
        "models":        MODELS,
        "github_token":  "",
    }


# ============================================================
# ① RAG強化: 過去記憶を自動注入
# ============================================================

def _build_rag_context(desc, k=5):
    try:
        ctx = retrieve_context(desc, k=k)
        if ctx and ctx.strip():
            return "\n\n【📚 関連する過去の実装・知識（RAG）】\n{}".format(ctx[:2000])
    except Exception as e:
        _log("WARNING RAG取得失敗: {}".format(e))
    return ""


# ============================================================
# ② 自己評価スコアリング
# ============================================================

def _detect_code_language(code: str) -> str:
    """コードの言語を判定する"""
    code_lower = code.lower()
    if re.search(r"extends\s+\w+|func\s+_ready|@onready|signal\s+\w+", code):
        return "gdscript"
    if re.search(r"using\s+UnityEngine|MonoBehaviour|void\s+Start\(\)|void\s+Update\(\)", code):
        return "csharp_unity"
    if re.search(r"UCLASS\(\)|UPROPERTY\(\)|#include\s+\"CoreMinimal", code):
        return "cpp_unreal"
    if re.search(r"import\s+pygame|pygame\.init|pygame\.display", code):
        return "python_pygame"
    if re.search(r"import\s+\w+|def\s+\w+|class\s+\w+:", code):
        return "python"
    if re.search(r"function\s+\w+|const\s+\w+\s*=|THREE\.", code):
        return "javascript"
    return "unknown"


def _score_python(code: str, task_desc: str) -> dict:
    """Pythonコードをルールベースでスコアリング"""
    issues = []
    score  = 100

    # 構文チェック
    try:
        ast.parse(code)
    except SyntaxError as e:
        return {
            "score": 0, "passed": False,
            "feedback": f"構文エラー: {e}",
            "breakdown": {"correctness": 0, "readability": 0, "safety": 0, "efficiency": 0},
            "language": "python",
        }

    lines = code.splitlines()

    # 空コードチェック
    if len(lines) < 3:
        return {"score": 10, "passed": False, "feedback": "コードが短すぎます",
                "breakdown": {}, "language": "python"}

    # correctness (25点)
    correctness = 25
    if "except:" in code and "except Exception" not in code:
        issues.append("裸のexceptは危険")
        correctness -= 8
    if "import *" in code:
        issues.append("import * は避けるべき")
        correctness -= 5
    # タスク説明のキーワードがコードに含まれるか
    desc_words = [w for w in re.findall(r"\w+", task_desc.lower()) if len(w) > 4]
    matched = sum(1 for w in desc_words if w in code.lower())
    if desc_words and matched / len(desc_words) < 0.2:
        issues.append("タスク内容との乖離が大きい")
        correctness -= 10

    # readability (25点)
    readability = 25
    long_lines = [i+1 for i, l in enumerate(lines) if len(l) > 120]
    if long_lines:
        issues.append(f"長すぎる行: {long_lines[:3]}")
        readability -= min(10, len(long_lines) * 2)
    has_comments = any(l.strip().startswith("#") for l in lines)
    if not has_comments and len(lines) > 10:
        issues.append("コメントがない")
        readability -= 8
    func_count = len(re.findall(r"^def ", code, re.MULTILINE))
    if func_count == 0 and len(lines) > 20:
        issues.append("関数化されていない")
        readability -= 5

    # safety (25点)
    safety = 25
    dangerous = ["eval(", "exec(", "os.system(", "__import__(", "pickle.load"]
    for d in dangerous:
        if d in code:
            issues.append(f"危険な関数: {d}")
            safety -= 15
    if "open(" in code and "with open" not in code:
        issues.append("with文なしのopen")
        safety -= 8

    # efficiency (25点)
    efficiency = 25
    if code.count("for ") > 0 and code.count("for ") == code.count("for ") and \
       re.search(r"for .+ in .+:\s*\n\s+for .+ in .+:", code):
        issues.append("ネストしたループ（最適化余地あり）")
        efficiency -= 5

    total = max(0, correctness + readability + safety + efficiency)
    feedback = "問題なし" if not issues else " / ".join(issues[:3])

    return {
        "score": total,
        "passed": total >= 55,
        "feedback": feedback,
        "breakdown": {
            "correctness": correctness,
            "readability": readability,
            "safety":      safety,
            "efficiency":  efficiency,
        },
        "language": "python",
    }


def _score_gdscript(code: str, task_desc: str) -> dict:
    """GDScriptコードをルールベースでスコアリング"""
    issues  = []
    score   = 100
    lines   = code.splitlines()

    if len(lines) < 2:
        return {"score": 10, "passed": False, "feedback": "コードが短すぎます",
                "breakdown": {}, "language": "gdscript"}

    # extends 宣言チェック
    has_extends = any(l.strip().startswith("extends") for l in lines[:5])
    if not has_extends:
        issues.append("extends宣言がない")
        score -= 15

    # Godot4 vs Godot3 混在チェック（致命的なバグ源）
    has_g4 = bool(re.search(r"CharacterBody2D|CharacterBody3D|@onready|@export", code))
    has_g3 = bool(re.search(r"KinematicBody2D|KinematicBody\b|\.move_and_slide\(velocity", code))
    if has_g4 and has_g3:
        issues.append("Godot3とGodot4のAPIが混在している（致命的）")
        score -= 40

    # move_and_slide の引数チェック（Godot4は引数なし）
    if re.search(r"move_and_slide\(.+\)", code) and has_g4:
        issues.append("Godot4のmove_and_slideに引数を渡している（引数不要）")
        score -= 20

    # func _ready() or _process() の存在
    has_lifecycle = bool(re.search(r"func _ready|func _process|func _physics_process", code))
    if not has_lifecycle and len(lines) > 5:
        issues.append("ライフサイクル関数がない")
        score -= 10

    # コメント
    has_comments = any("#" in l for l in lines)
    if not has_comments and len(lines) > 8:
        issues.append("コメントがない")
        score -= 8

    total    = max(0, score)
    feedback = "問題なし" if not issues else " / ".join(issues[:3])
    return {
        "score":   total,
        "passed":  total >= 55,
        "feedback": feedback,
        "breakdown": {"correctness": max(0, score//4), "readability": 20,
                      "safety": 20, "efficiency": 15},
        "language": "gdscript",
    }


def _score_csharp(code: str, task_desc: str) -> dict:
    """C#コードを簡易ルールベースでスコアリング"""
    issues = []
    score  = 100
    lines  = code.splitlines()

    # 基本構造チェック
    if "class " not in code:
        issues.append("クラス定義がない"); score -= 20
    if "{" not in code or "}" not in code:
        issues.append("ブロック構造が不正"); score -= 30
    # using文
    if "using " not in code:
        issues.append("using宣言がない"); score -= 10
    # Unity系チェック
    if "MonoBehaviour" in task_desc or "Unity" in task_desc:
        if "MonoBehaviour" not in code:
            issues.append("MonoBehaviourを継承していない"); score -= 15

    total    = max(0, score)
    feedback = "問題なし" if not issues else " / ".join(issues[:3])
    return {"score": total, "passed": total >= 55, "feedback": feedback,
            "breakdown": {}, "language": "csharp"}


def _score_cpp(code: str, task_desc: str) -> dict:
    """C++コードを簡易ルールベースでスコアリング"""
    issues = []
    score  = 100
    # ヘッダとソースの対になっているか
    if "#pragma once" not in code and "#ifndef" not in code:
        issues.append("ヘッダガードがない"); score -= 10
    if "UCLASS" in task_desc or "Unreal" in task_desc:
        if "UCLASS()" not in code:
            issues.append("UCLASS()マクロがない"); score -= 20
        if "GENERATED_BODY()" not in code:
            issues.append("GENERATED_BODY()がない"); score -= 15
    total    = max(0, score)
    feedback = "問題なし" if not issues else " / ".join(issues[:3])
    return {"score": total, "passed": total >= 55, "feedback": feedback,
            "breakdown": {}, "language": "cpp"}


def score_code(code: str, task_desc: str = "") -> dict:
    """
    ルールベース多言語コード品質スコアリング。
    モデル非依存・言語自動判定・安定動作。

    修正前: AIモデルに採点させていた（モデル依存・スコアがバラバラ）
    修正後: 言語ごとの構文/構造/危険パターンをルールで判定（安定・高速）
    """
    if not code or not code.strip():
        return {"score": 0, "passed": False, "feedback": "コードが空です",
                "breakdown": {}, "language": "unknown"}

    lang = _detect_code_language(code)
    _log("スコアリング開始 (言語: {})".format(lang))

    if lang in ("python", "python_pygame"):
        result = _score_python(code, task_desc)
    elif lang == "gdscript":
        result = _score_gdscript(code, task_desc)
    elif lang in ("csharp", "csharp_unity"):
        result = _score_csharp(code, task_desc)
    elif lang == "cpp_unreal":
        result = _score_cpp(code, task_desc)
    else:
        # 未知言語: 最低限の長さチェックのみ
        lines = code.splitlines()
        score = min(100, len(lines) * 3)
        result = {"score": score, "passed": score >= 40,
                  "feedback": "未知言語のため簡易評価",
                  "breakdown": {}, "language": lang}

    _log("スコア: {}/100 ({}) passed={}".format(
        result["score"], result["language"], result["passed"]))
    return result


def _generate_with_score_loop(system_prompt, desc, max_score_attempts=3):
    current_prompt = system_prompt
    best_code  = ""
    best_score = {"score": 0, "passed": False, "feedback": ""}

    for attempt in range(max_score_attempts):
        _log("コード生成 attempt {}/{}".format(attempt + 1, max_score_attempts))
        try:
            res  = ollama.chat(
                model=MODELS["coder"],
                messages=[
                    {"role": "system", "content": current_prompt},
                    {"role": "user",   "content": desc},
                ]
            )
            code = extract_code(res["message"]["content"])
        except Exception as e:
            _log("ERROR Coder attempt {}: {}".format(attempt + 1, e))
            break

        score_result = score_code(code, desc)
        score_val    = score_result.get("score", 0)

        if score_val > best_score.get("score", 0):
            best_code  = code
            best_score = score_result

        if score_val >= 60:
            _log("スコア合格({})→生成確定".format(score_val))
            break

        feedback = score_result.get("feedback", "品質不足")
        _log("スコア不合格({}点)→再生成: {}".format(score_val, feedback))
        current_prompt = (
            system_prompt
            + "\n\n【前回フィードバック（必ず改善）】\n" + feedback
        )

    return best_code, best_score


# ============================================================
# ⑥ インターネット検索: コード生成前に自動検索
# ============================================================

def _build_internet_context(desc, grand_state=None):
    token = ""
    if grand_state:
        token = grand_state.get("github_token", "")

    try:
        _log("🌐 インターネット検索: {}...".format(desc[:40]))
        ctx = build_search_context(desc, github_token=token)
        _log("🌐 検索完了")
        return ctx
    except Exception as e:
        _log("WARNING インターネット検索失敗: {}".format(e))
        try:
            dt = get_current_datetime()
            return "\n\n【🌐 現在日時】\n{}".format(dt["datetime_str"])
        except Exception:
            return ""


# ============================================================
# ⑨ Chain of Thought 強制テンプレート（CoT）
# ============================================================

def _build_cot_prefix(desc: str) -> str:
    """
    コードを書く前にAIに「3点を日本語で先書き」させるプレフィックス。
    言語化=自己デバッグ。これだけで精度が大幅に上がる。
    """
    return (
        "\n\n【🧠 必須: コード生成前に以下3点を日本語で書き出せ】\n"
        "1. 影響ファイル: この実装が変更・参照するファイルはどれか\n"
        "2. 想定エラー: NoneType/KeyError/ImportError等どんな例外が起きうるか\n"
        "3. 実装ロジック: 具体的にどう実装するか（箇条書き）\n"
        "→ 上記3点を書いてから、コードブロックを出力せよ。\n\n"
        "タスク: {desc}"
    ).format(desc=desc[:500])


# ============================================================
# ⑩ 3案Branching（Path A/B/C）+ 1往復Critic
# ============================================================

def _branch_and_critique(desc: str, system_prompt: str, use_branching: bool = True) -> tuple:
    """
    3案並列生成 + Criticによる1往復評価。
    
    Path A (保守的/安定): 既存ライブラリ・枯れた技術のみ
    Path B (先進的/高効率): 最新機能・非同期・高度なアルゴリズム
    Path C (最小実装/DRY): 既存関数再利用・コード量最小

    戻り値: (best_code, score_result, branch_summary)
    branch_summary: 「なぜA/B/Cを選んだか」の1行説明
    """
    if not use_branching:
        # Branching無効時は通常生成
        code, score = _generate_with_score_loop(system_prompt, desc)
        return code, score, "単発生成"

    _log("⑩ 3案Branching開始")

    branch_prompts = {
        "A": (
            "【Path A: 保守的/安定】\n"
            "標準ライブラリと実績あるライブラリのみ使用。破壊的変更を一切避けること。\n"
            "安全性・可読性を最優先。\n"
        ),
        "B": (
            "【Path B: 先進的/高効率】\n"
            "最新の機能・非同期処理・高度なアルゴリズムを積極的に使用。\n"
            "パフォーマンスと機能性を最優先。\n"
        ),
        "C": (
            "【Path C: 最小実装/DRY】\n"
            "既存の関数・クラスを最大限再利用。コード量を最小限に抑える。\n"
            "保守性と簡潔さを最優先。\n"
        ),
    }

    candidates = {}
    for path_name, path_prefix in branch_prompts.items():
        _log("Branch {} 生成中...".format(path_name))
        prompt = system_prompt + "\n\n" + path_prefix
        try:
            res = ollama.chat(
                model=MODELS["coder"],
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user",   "content": _build_cot_prefix(desc)},
                ]
            )
            code  = extract_code(res["message"]["content"])
            score = score_code(code, desc)
            candidates[path_name] = {"code": code, "score": score}
            _log("Branch {} スコア: {}".format(path_name, score.get("score", 0)))
        except Exception as e:
            _log("WARNING Branch {} 失敗: {}".format(path_name, e))

    if not candidates:
        _log("全Branch失敗→フォールバック")
        code, score = _generate_with_score_loop(system_prompt, desc)
        return code, score, "フォールバック（Branch全失敗）"

    # Sandbox検証で生存個体を選ぶ
    sandbox_results = {}
    for pname, cand in candidates.items():
        lang = _detect_code_language(cand["code"])
        if lang in ("python", "python_pygame"):
            # Python: 実際にサンドボックス実行
            err = run_safe(cand["code"])
            sandbox_results[pname] = err is None
            _log("Branch {} Sandbox(Python): {}".format(pname, "成功" if err is None else str(err)[:60]))
        elif lang == "gdscript":
            # GDScript: パターン検証（実行はできないが致命的バグを検出）
            sc = cand["score"]
            is_ok = sc.get("score", 0) >= 40 and "致命的" not in sc.get("feedback", "")
            sandbox_results[pname] = is_ok
            _log("Branch {} Sandbox(GDScript): {}".format(pname, "OK" if is_ok else "NG: " + sc.get("feedback","")))
        elif lang in ("csharp", "csharp_unity", "cpp_unreal"):
            # C#/C++: スコアベース判定（コンパイラがないため）
            is_ok = cand["score"].get("score", 0) >= 40
            sandbox_results[pname] = is_ok
            _log("Branch {} Sandbox({}): {}".format(pname, lang, "OK" if is_ok else "スコア不足"))
        else:
            # 未知言語: スコアのみで判断
            sandbox_results[pname] = cand["score"].get("score", 0) >= 35
            _log("Branch {} Sandbox(unknown): スコア判定".format(pname))

    # 勝者選定: Sandbox成功 > スコア順
    passing = {k: v for k, v in candidates.items() if sandbox_results.get(k, False)}
    pool    = passing if passing else candidates

    best_path = max(pool, key=lambda k: pool[k]["score"].get("score", 0))
    best      = pool[best_path]

    # ボツ理由1行生成
    rejected = [k for k in candidates if k != best_path]
    rejection_notes = []
    for r in rejected:
        sc = candidates[r]["score"].get("score", 0)
        sb = "Sandbox失敗" if not sandbox_results.get(r, True) else f"スコア{sc}"
        rejection_notes.append("Path{}({})".format(r, sb))

    branch_summary = "Path{} を採用。不採用: {}".format(
        best_path,
        " / ".join(rejection_notes) if rejection_notes else "なし"
    )
    _log("⑩ Branching完了: {}".format(branch_summary))

    return best["code"], best["score"], branch_summary


# ============================================================
# ⑪ 依存グラフ統合（graph.py連携）
# ============================================================

def _build_graph_context(task_desc: str, save_path: str) -> str:
    """
    graph.pyを使って依存グラフ＋関連ファイル構造をコンテキスト生成。
    影響半径警告も含める。
    """
    try:
        from graph import build_graph_context, build_project_graph, get_blast_radius_warning
        ctx = build_graph_context(task_desc, save_path)
        if ctx:
            _log("🗺 依存グラフコンテキスト取得完了")
        return ctx
    except ImportError:
        return ""
    except Exception as e:
        _log("WARNING 依存グラフ取得失敗: {}".format(e))
        return ""


# ============================================================
# ⑫ ゲーム開発コンテキスト（asset_pipeline.py 物理解析統合版）
# ============================================================

# 速度モード: "fast"=軽量/検索スキップ, "normal"=通常, "quality"=最高品質
SPEED_MODE = "normal"

# プロジェクト素材マニフェストキャッシュ（プロセス内）
_asset_manifest_cache: dict = {}   # {folder_path: AssetManifest}


def _should_search_internet(desc: str) -> bool:
    """
    速度改善: タスク内容からネット検索が必要かを判定。
    「標準ライブラリだけで解決できる」「既知パターン」は検索スキップ。
    """
    if SPEED_MODE == "fast":
        return False   # fastモードは全スキップ

    # 明らかに検索不要なキーワード
    skip_keywords = [
        "定数", "constants", "設定ファイル", "config", "リファクタ", "refactor",
        "コメント", "型ヒント", "type hint", "docstring", "フォーマット",
        "変数名", "rename", "移動", "move file", "削除", "delete",
        "requirements.txt", "readme", ".gitignore",
    ]
    desc_lower = desc.lower()
    if any(k in desc_lower for k in skip_keywords):
        _log("⚡ 検索スキップ（不要と判定）: {}".format(desc[:30]))
        return False

    # 検索が有益なキーワード
    search_keywords = [
        "最新", "latest", "バージョン", "version", "インストール", "install",
        "エラー", "error", "api", "ライブラリ", "library", "仕様", "spec",
        "pygame", "godot", "unity", "three.js",
    ]
    return any(k in desc_lower for k in search_keywords)


def _build_internet_context_smart(desc: str, grand_state=None) -> str:
    """検索判定付きのインターネットコンテキスト生成（速度改善版）"""
    if not _should_search_internet(desc):
        try:
            dt = get_current_datetime()
            return "\n\n【🕐 現在日時】\n{}".format(dt["datetime_str"])
        except Exception:
            return ""
    return _build_internet_context(desc, grand_state)


def _build_game_context(desc: str, save_path: str = "./") -> str:
    """
    game_theory(MDA理論) + asset_pipeline(物理解析) + knowledge_api(無料API)
    を統合したゲーム開発コンテキスト生成。
    Cursorには絶対できない三重構造。
    """
    game_keywords = [
        "ゲーム","game","player","プレイヤー","enemy","敵","モンスター",
        "sprite","tilemap","godot","pygame","unity","2d","3d",
        "アイテム","item","バトル","battle","マップ","map","stage",
        "rpg","アクション","action","シューター","shooter","platform",
        "ジャンプ","jump","移動","move","アニメーション","animation",
        "ダンジョン","dungeon","ローグ","rogue","シミュ","simulation",
        "タワー","tower","ビルド","build","npc","クエスト","quest",
    ]
    desc_lower = desc.lower()
    if not any(k.lower() in desc_lower for k in game_keywords):
        return ""

    _log("🎮 ゲームコンテキスト生成（MDA+素材+API）")
    ctx_parts = []

    # ── ① MDA理論 + フロー理論（game_theory.py） ────────
    try:
        from game_theory import get_mda_context, get_fun_theory_prompt
        from genre_templates import detect_genre
        detected_genre = detect_genre(desc)
        mda_ctx = get_mda_context(detected_genre, desc)
        if mda_ctx:
            ctx_parts.append(mda_ctx)
            _log("🧠 MDA理論注入: {}".format(detected_genre))
    except Exception as e:
        _log("WARNING MDA注入失敗: {}".format(e))

    # ── ② asset_pipeline 物理解析 ──────────────────────
    try:
        from asset_pipeline import scan_project_assets, build_pygame_context, save_manifest
        if save_path in _asset_manifest_cache:
            manifest = _asset_manifest_cache[save_path]
            _log("🎮 マニフェストキャッシュ使用: {}素材".format(
                manifest.summary.get("total_sprites",0) +
                manifest.summary.get("total_tilesets",0)
            ))
        elif os.path.isdir(save_path):
            manifest = scan_project_assets(save_path)
            _asset_manifest_cache[save_path] = manifest
            save_manifest(manifest, save_path)
            total = (manifest.summary.get("total_sprites",0) +
                     manifest.summary.get("total_tilesets",0) +
                     manifest.summary.get("total_bgm",0) +
                     manifest.summary.get("total_se",0))
            _log("🎮 物理スキャン完了: {}素材 | シート検出: {}個".format(
                total, manifest.summary.get("sheets_detected",0)))
        else:
            manifest = None
        if manifest:
            pipeline_ctx = build_pygame_context(manifest, desc)
            if pipeline_ctx:
                ctx_parts.append(pipeline_ctx)
    except ImportError:
        _log("WARNING asset_pipeline未インストール → fallback")
    except Exception as e:
        _log("WARNING 物理解析失敗: {}".format(e))

    # ── ③ 無料API知識注入（knowledge_api.py） ───────────
    try:
        from knowledge_api import inject_knowledge
        from genre_templates import detect_genre as _dg
        genre_for_api = _dg(desc)
        api_ctx = inject_knowledge(desc, genre_for_api)
        if api_ctx:
            ctx_parts.append(api_ctx)
            _log("🌐 無料API知識注入完了")
    except Exception as e:
        _log("WARNING API知識注入失敗: {}".format(e))

    # ── ④ analyzer.py 類似プロジェクト提案（補助） ────
    try:
        from analyzer import suggest_from_similar, analyze_game_assets_folder, build_game_context_from_assets
        similar_ctx = suggest_from_similar(desc, "ゲーム")
        if similar_ctx:
            ctx_parts.append(similar_ctx)
        if not ctx_parts:
            asset_map = analyze_game_assets_folder(save_path)
            if "_summary" in asset_map and asset_map["_summary"]["total_files"] > 0:
                ctx_parts.append(build_game_context_from_assets(asset_map, desc))
    except Exception as e:
        _log("WARNING ゲームコンテキスト補助取得失敗: {}".format(e))

    return "\n".join(ctx_parts)



def invalidate_asset_cache(folder: str = None):
    """素材キャッシュを無効化（新しい素材追加後に呼ぶ）"""
    global _asset_manifest_cache
    if folder:
        _asset_manifest_cache.pop(folder, None)
        _log("🎮 素材キャッシュをクリア: {}".format(folder))
    else:
        _asset_manifest_cache.clear()
        _log("🎮 素材キャッシュを全クリア")




# ============================================================
# Planner エージェント
# ============================================================

def plan(goal, anchor="", history=None, grand_state=None):
    _log("Planner 起動: {}...".format(goal[:60]))

    # ⑥ インターネット検索でプランニングを強化
    internet_ctx = _build_internet_context(goal, grand_state)

    system_content = ROLES["planner"]
    if anchor:
        system_content += "\n\n【プロジェクト主軸・絶対遵守】\n{}".format(anchor)
    if internet_ctx:
        system_content += internet_ctx

    messages = [{"role": "system", "content": system_content}]
    if history:
        messages.extend(history[-6:])
    messages.append({"role": "user", "content": goal})

    try:
        res   = ollama.chat(model=MODELS["planner"], messages=messages)
        raw   = res["message"]["content"]
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            tasks = json.loads(match.group(0))
            _log("タスク数: {}".format(len(tasks)))
            return tasks
        _log("WARNING: Planner JSON 未返却 → フォールバック")
        return [{"file": "output.py", "desc": goal}]
    except Exception as e:
        _log("ERROR Planner: {}".format(e))
        return [{"file": "output.py", "desc": goal}]


# ============================================================
# Phase 2 ⑦: 自己批判フェーズ（計画→批判→実行の3段階思考）
# ============================================================

def _self_critique(goal, plan_result, anchor=""):
    """
    Plannerが作った計画をCriticが批判し、改善案を出す。
    戻り値: {"critique": str, "improved_tasks": list, "risk_score": int}
    
    これがない場合との違い:
      Before: Plannerが計画 → そのまま実行
      After:  Plannerが計画 → Criticが「この設計は壊れる」と指摘
                            → 改善されたタスクで実行
                            → 凡ミスがゼロになる
    """
    _log("⑦ 自己批判フェーズ開始")

    critic_prompt = (
        "あなたは厳格なコードレビュアー兼アーキテクトです。\n"
        "以下の実装計画を批判的に分析してください。\n\n"
        "【元のゴール】\n{goal}\n\n"
        "【実装計画】\n{plan}\n\n"
        "プロジェクト主軸: {anchor}\n\n"
        "以下のJSON形式のみで返してください（前置き不要）:\n"
        '{{\n'
        '  "critique": "計画の問題点・リスクを200文字以内で指摘",\n'
        '  "risk_score": 0から100の整数（高いほど危険）,\n'
        '  "improvements": [\n'
        '    "改善点1",\n'
        '    "改善点2"\n'
        '  ],\n'
        '  "improved_tasks": [\n'
        '    {{"file": "ファイル名.py", "desc": "改善された詳細な実装内容"}}\n'
        '  ]\n'
        '}}'
    ).format(
        goal=goal[:500],
        plan=json.dumps(plan_result, ensure_ascii=False)[:1000],
        anchor=anchor[:200]
    )

    try:
        res   = ollama.chat(
            model=MODELS["planner"],
            messages=[{"role": "user", "content": critic_prompt}]
        )
        raw   = res["message"]["content"]
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
            risk   = result.get("risk_score", 0)
            _log("⑦ 批判完了 リスクスコア: {}/100".format(risk))
            _log("⑦ 指摘: {}".format(result.get("critique", "")[:80]))
            return result
    except Exception as e:
        _log("WARNING 自己批判失敗（スキップ）: {}".format(e))

    return {"critique": "批判スキップ", "risk_score": 0, "improvements": [], "improved_tasks": plan_result}


# ============================================================
# Phase 2 ⑧: 自己進化型メモリー（教訓の蓄積と活用）
# ============================================================

def _extract_lesson(task_desc, code, score_result, success):
    """
    タスク実行結果から「教訓」を抽出してメモリに蓄積する。
    成功パターンも失敗パターンも両方学習する。
    
    これがない場合との違い:
      Before: コードを生成して保存するだけ
      After:  「なぜ成功/失敗したか」を記録
              → 次回の同様タスクで自動的に活用
              → 同じミスを繰り返さない
              → 成功パターンを再利用する
    """
    score_val = score_result.get("score", 50)
    feedback  = score_result.get("feedback", "")

    if score_val >= 75 and success:
        lesson_type = "SUCCESS"
        lesson_body = (
            "【成功パターン】\n"
            "タスク: {desc}\n"
            "スコア: {score}/100\n"
            "良かった点: {feedback}\n"
            "再利用すべきコードパターン:\n{snippet}"
        ).format(
            desc=task_desc[:200],
            score=score_val,
            feedback=feedback,
            snippet=code[:600]
        )
    elif score_val < 60 or not success:
        lesson_type = "FAILURE"
        lesson_body = (
            "【失敗パターン・注意】\n"
            "タスク: {desc}\n"
            "スコア: {score}/100\n"
            "問題点: {feedback}\n"
            "次回避けるべき点: このアプローチは使わない"
        ).format(
            desc=task_desc[:200],
            score=score_val,
            feedback=feedback,
        )
    else:
        return  # 中程度は記録しない

    lesson_key = "lesson_{}_{}".format(lesson_type, datetime.now().strftime("%Y%m%d_%H%M%S"))
    try:
        store_memory(
            lesson_key,
            lesson_body,
            {
                "type":    "lesson",
                "kind":    lesson_type,
                "score":   str(score_val),
                "success": str(success),
            }
        )
        _log("⑧ 教訓を記録: {} (score={})".format(lesson_type, score_val))
    except Exception as e:
        _log("WARNING 教訓記録失敗: {}".format(e))


def _retrieve_lessons(task_desc, k=3):
    """
    過去の教訓から類似するものを取得してプロンプトに注入する。
    """
    try:
        lessons = retrieve_context("lesson " + task_desc, k=k)
        if lessons and lessons.strip():
            return "\n\n【📖 過去の教訓（成功・失敗から学んだこと）】\n{}".format(lessons[:1500])
    except Exception as e:
        _log("WARNING 教訓取得失敗: {}".format(e))
    return ""




# ============================================================
# Refiner（自己修復）
# ============================================================

def _classify_error(error_msg: str) -> dict:
    """
    エラーメッセージを分類・抽象化してNegative Cacheに保存できる形にする。
    「なぜ失敗したか」を記録する核心部分。
    """
    error_lower = error_msg.lower()
    if "syntaxerror" in error_lower:
        category = "syntax"
        abstract = "構文エラー: インデント・括弧・コロンのミス"
    elif "importerror" in error_lower or "modulenotfounderror" in error_lower:
        mod = re.search(r"No module named '([^']+)'", error_msg)
        mod_name = mod.group(1) if mod else "不明"
        category = "import"
        abstract = "ImportError: モジュール '{}' が見つからない → pip install が必要".format(mod_name)
    elif "attributeerror" in error_lower:
        category = "attribute"
        abstract = "AttributeError: 存在しないメソッド・属性へのアクセス。APIバージョン変更の可能性"
    elif "typeerror" in error_lower:
        category = "type"
        abstract = "TypeError: 型不一致。引数の型・数が違う可能性"
    elif "keyerror" in error_lower:
        category = "key"
        abstract = "KeyError: 存在しないキーへのアクセス。.get()を使うべき"
    elif "filenotfounderror" in error_lower:
        category = "file"
        abstract = "FileNotFoundError: パスが存在しない。os.makedirs()が必要な可能性"
    elif "timeout" in error_lower:
        category = "timeout"
        abstract = "タイムアウト: 無限ループ・重い処理。条件見直しが必要"
    elif "valueerror" in error_lower:
        category = "value"
        abstract = "ValueError: 不正な値。入力バリデーションが必要"
    else:
        category = "runtime"
        abstract = "RuntimeError: {}...".format(error_msg[:100])

    return {"category": category, "abstract": abstract, "raw": error_msg[:300]}


def _save_negative_cache(task_desc: str, error_info: dict, failed_code_snippet: str):
    """
    失敗パターンをNegative CacheとしてベクトルDBに保存。
    次回同じ罠を踏みそうになったときに「待った」をかける。
    """
    key = "negcache_{}_{}".format(
        error_info["category"],
        datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    body = (
        "【🚫 禁止パターン / 失敗記録】\n"
        "タスク文脈: {desc}\n"
        "エラー種別: {cat}\n"
        "抽象的理由: {abstract}\n"
        "具体的エラー: {raw}\n"
        "問題のコード断片:\n{snippet}\n"
        "→ 次回このアプローチは避けること"
    ).format(
        desc=task_desc[:200],
        cat=error_info["category"],
        abstract=error_info["abstract"],
        raw=error_info["raw"],
        snippet=failed_code_snippet[:400]
    )
    try:
        store_memory(key, body, {
            "type": "negative_cache",
            "category": error_info["category"],
            "abstract": error_info["abstract"],
        })
        _log("💾 Negative Cache保存: [{}] {}".format(error_info["category"], error_info["abstract"][:60]))
    except Exception as e:
        _log("WARNING Negative Cache保存失敗: {}".format(e))


def _get_negative_cache_warning(task_desc: str) -> str:
    """
    過去の失敗パターンを検索して警告文を返す。
    コード生成前にプロンプトに注入することで「同じ罠を踏まない」。
    """
    try:
        warnings = retrieve_context("negcache " + task_desc, k=3)
        if warnings and "禁止パターン" in warnings:
            return "\n\n【⚠️ 過去の失敗パターン（必ず避けること）】\n{}".format(warnings[:1000])
    except Exception:
        pass
    return ""


def self_heal(code, max_attempts=4, task_desc=""):
    """
    完全Sandboxループ:
    実行 → エラー分類 → 原因分析 → Negative Cache保存 → 修正再生成 → 再実行
    
    Cursorとの差: Cursorは推論で止まる。BlackwellはSandboxで物理確認してから返す。
    """
    error_history = []  # 同じエラーループを検出するため

    for attempt in range(max_attempts):
        err = run_safe(code)

        # 成功
        if not err:
            _log("✅ self_heal: {}回目で実行成功".format(attempt + 1))
            return code, True

        _log("🔧 self_heal {}/{}: エラー検出".format(attempt + 1, max_attempts))

        # エラー分類・抽象化
        error_info = _classify_error(err)
        _log("   種別: [{}] {}".format(error_info["category"], error_info["abstract"][:60]))

        # Negative Cacheに保存（初回のみ）
        if attempt == 0 and task_desc:
            _save_negative_cache(task_desc, error_info, code[:500])

        # 同じエラーが続くループ検出
        if err in error_history:
            _log("⚠️ 同じエラーが繰り返されています → 別アプローチを試みます")
            # 別アプローチ指示を追加
            alt_instruction = (
                "前回と全く異なるアプローチで実装し直してください。\n"
                "エラー '{}' が繰り返されています。\n"
                "このエラーが出ないよう根本的に設計を変えてください。"
            ).format(error_info["abstract"])
        else:
            alt_instruction = ""
        error_history.append(err)

        # Refinerで修正
        try:
            fix_prompt = (
                "【エラー種別】{cat}\n"
                "【エラー内容】\n{err}\n\n"
                "【失敗したコード】\n{code}\n\n"
                "【修正指示】\n{alt}"
                "上記エラーを完全に修正したコード全体を出力してください。"
            ).format(
                cat=error_info["abstract"],
                err=err[:500],
                code=code[:2000],
                alt=alt_instruction + "\n" if alt_instruction else ""
            )
            fix = ollama.chat(
                model=MODELS["refiner"],
                messages=[
                    {"role": "system", "content": ROLES["refiner"]},
                    {"role": "user",   "content": fix_prompt},
                ]
            )
            code = extract_code(fix["message"]["content"])
            _log("   修正コード生成完了 → 再実行します")
        except Exception as e:
            _log("ERROR Refiner attempt {}: {}".format(attempt + 1, e))
            break

    _log("⚠️ self_heal: 最大試行数{}回に達した".format(max_attempts))
    return code, False


# ============================================================
# Optimizer
# ============================================================

def optimize(code):
    _log("Optimizer 起動")
    try:
        res    = ollama.chat(
            model=MODELS["optimizer"],
            messages=[
                {"role": "system", "content": ROLES["optimizer"]},
                {"role": "user",   "content": code},
            ]
        )
        result = extract_code(res["message"]["content"])
        return result if result.strip() else code
    except Exception as e:
        _log("ERROR Optimizer: {}".format(e))
        return code


# ============================================================
# Godot連携
# ============================================================

def export_to_godot(file_name: str, code: str, grand_state=None) -> Optional[str]:
    """
    GodotプロジェクトにGDScript/C#ファイルを書き出し、
    可能であればGodotエディタにホットリロードを通知する。

    修正前: ファイルを指定フォルダに置くだけ（Godotとの連携なし）
    修正後:
      1. Godotプロジェクトの正しいパスに保存
      2. Godotエディタが起動中なら EditorPlugin経由でリロード通知
      3. ヘッドレスモードなら再起動スクリプトを生成
    """
    if grand_state is None:
        grand_state = load_grand_state()

    # Godotプロジェクトパスを優先的に使う
    godot_project_path = grand_state.get("paths", {}).get("godot_project", "")
    export_path        = grand_state.get("paths", {}).get("code_export", "")

    # 保存先の優先順位: godot_project > code_export > カレントディレクトリ
    if godot_project_path and os.path.exists(godot_project_path):
        save_dir = godot_project_path
    elif export_path:
        save_dir = export_path
    else:
        save_dir = "./"

    try:
        os.makedirs(save_dir, exist_ok=True)
        dest = os.path.join(save_dir, file_name)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(code)
        _log("Godot書き出し: {}".format(dest))

        # ── ホットリロード通知（3段階フォールバック）──────────
        reloaded = False

        # 方法①: Godotエディタが起動中ならEditorScriptでリロード
        if not reloaded:
            reloaded = _notify_godot_editor_reload(dest, save_dir)

        # 方法②: .godot/editor/project_metadata.cfg のタイムスタンプ更新
        # (Godotはファイル変更を監視しているので、これで気づく)
        if not reloaded:
            _touch_godot_filesystem(save_dir)
            _log("Godot: ファイルシステム変更通知")
            reloaded = True

        if reloaded:
            _log("✅ Godot ホットリロード通知済み: {}".format(file_name))

        return dest

    except Exception as e:
        _log("ERROR Godot書き出し: {}".format(e))
        return None


def _notify_godot_editor_reload(file_path: str, project_path: str) -> bool:
    """
    実行中のGodotエディタプロセスを検知して
    EditorScriptでリロードを試みる。
    """
    try:
        # GodotエディタのPIDを探す
        godot_pids = []
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Godot*", "/FO", "CSV"],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.splitlines():
            if "Godot" in line:
                try:
                    pid = int(line.split(",")[1].strip('"'))
                    godot_pids.append(pid)
                except Exception:
                    pass

        if not godot_pids:
            # Unix系
            result = subprocess.run(
                ["pgrep", "-l", "godot"],
                capture_output=True, text=True, timeout=3
            )
            for line in result.stdout.splitlines():
                try:
                    godot_pids.append(int(line.split()[0]))
                except Exception:
                    pass

        if godot_pids:
            _log("Godotエディタ検出 (PID: {}) → リロード通知".format(godot_pids))
            # EditorPlugin経由でリロードするGDScriptを一時生成・実行
            reload_script = _generate_reload_script(file_path)
            reload_path   = os.path.join(project_path, "_blackwell_reload.gd")
            with open(reload_path, "w", encoding="utf-8") as f:
                f.write(reload_script)
            return True

        return False
    except Exception:
        return False


def _touch_godot_filesystem(project_path: str):
    """Godotのファイル変更検知を促すためにメタデータを更新"""
    try:
        import time
        uid_file = os.path.join(project_path, ".godot", "uid_cache.bin")
        if os.path.exists(uid_file):
            # タイムスタンプを更新（内容は変えない）
            current = os.path.getmtime(uid_file)
            os.utime(uid_file, (current, current + 0.001))
    except Exception:
        pass


def _generate_reload_script(file_path: str) -> str:
    """Godotエディタのファイルシステムをリスキャンするスクリプト"""
    return f"""# _blackwell_reload.gd — Blackwell自動生成（リロード後に自動削除）
@tool
extends EditorScript

func _run():
    var fs = EditorInterface.get_resource_filesystem()
    fs.scan()
    print("[Blackwell] ファイルシステムをリスキャンしました: {file_path}")
    # このスクリプト自体を削除
    var da = DirAccess.open("res://")
    da.remove("_blackwell_reload.gd")
"""


# ============================================================
# タスク実行（1ファイル分）
# ============================================================

def process_task(task, auto_write, save_path="./", anchor="", grand_state=None):
    file_name = task.get("file", "output.py")
    desc      = task.get("desc", "")
    file_path = os.path.join(save_path, file_name)

    parent = os.path.dirname(file_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    _log("タスク開始: {}".format(file_name))

    existing = ""
    if os.path.exists(file_path):
        try:
            with open(file_path, encoding="utf-8") as f:
                existing = f.read()
            _log("既存コード読込: {}文字".format(len(existing)))
        except Exception as e:
            _log("WARNING 既存コード読込失敗: {}".format(e))

    # 🗺️ Phase 1: プロジェクト地図コンテキスト
    map_context = get_map_context(save_path, desc, file_name)
    if map_context:
        _log("🗺️ 地図コンテキスト注入: {}文字".format(len(map_context)))

    # 📜 Phase 2: 契約警告（このファイルを変えると何が壊れるか）
    contract_warning = get_contract_warning(save_path, file_name)
    if contract_warning:
        _log("📜 契約警告注入: {}ファイルが依存".format(
            contract_warning.count("←")))

    # 🔮 Phase 3: 予測リスク警告（過去の分析から将来の問題を注入）
    prediction_warning = get_prediction_warning(save_path, file_name)
    if prediction_warning:
        _log("🔮 予測リスク注入: {}文字".format(len(prediction_warning)))

    # ① RAGコンテキスト
    rag_context = _build_rag_context(desc, k=5)

    # 📖 Phase 2: 過去の教訓（memory.pyのretrieve_contextを置き換え）
    lesson_ctx = get_lessons(save_path, desc, k=3) or _retrieve_lessons(desc, k=3)

    # ⚠️ Phase 2: 過去の失敗パターン（negcacheを置き換え）
    neg_cache_warning = get_failure_warning(save_path, desc) or _get_negative_cache_warning(desc)

    # ⑥ インターネット検索コンテキスト（スマート判定付き）
    internet_ctx = _build_internet_context_smart(desc, grand_state)

    # ⑪ 依存グラフコンテキスト（graph.py）
    graph_ctx = _build_graph_context(file_name, save_path)

    # ⑫ ゲーム開発コンテキスト（asset_pipeline物理解析）
    game_ctx = _build_game_context(desc, save_path)

    # ⑬ エンジン自動判定 + エンジン別プロンプト（engine_adapter.py）
    engine_ctx   = ""
    genre_ctx    = ""
    detected_engine = "godot"
    detected_genre  = ""
    try:
        from engine_adapter import detect_engine_from_project, build_engine_context
        from genre_templates import detect_genre, get_genre_context

        # エンジン判定（プロジェクトフォルダを解析）
        detected_engine = detect_engine_from_project(save_path)
        _log("🔧 エンジン判定: {}".format(detected_engine))

        # ジャンル判定（タスク説明から）
        detected_genre = detect_genre(desc)

        # ゲーム系タスクの場合のみ注入
        is_game_task = bool(game_ctx or detected_genre)
        if is_game_task:
            engine_ctx = build_engine_context(detected_engine, detected_genre, desc)
            genre_ctx  = get_genre_context(detected_genre, detected_engine)
            _log("🎮 ジャンル判定: {} | エンジン: {}".format(
                detected_genre, detected_engine))

    except ImportError:
        pass
    except Exception as e:
        _log("WARNING エンジン/ジャンル判定失敗: {}".format(e))

    # システムプロンプト組み立て
    # 🧬 Phase 6: 進化プロンプトを動的注入
    evolved_roles = apply_evolved_prompts(save_path, ROLES, desc)
    system_prompt = evolved_roles.get("coder", ROLES["coder"])
    if system_prompt != ROLES["coder"]:
        _log("🧬 進化プロンプト適用済み")
    if anchor:
        system_prompt += "\n\n【プロジェクト主軸】\n{}".format(anchor)

    # 🗺️ Phase 1: 地図コンテキスト注入（コード全体の代わり）
    if map_context:
        system_prompt += "\n\n" + map_context

    # 🌐 マルチプロジェクト知識ハブ注入
    if _HUB_OK:
        hub_ctx = import_knowledge(save_path, desc)
        if hub_ctx:
            system_prompt += "\n\n" + hub_ctx

    # 📜 Phase 2: 契約警告注入
    if contract_warning:
        system_prompt += contract_warning

    # 🔮 Phase 3: 予測リスク警告注入
    if prediction_warning:
        system_prompt += prediction_warning

    # ── フィーリングスライダー注入（feeling_paramsがあれば） ──
    feeling_ctx = _build_feeling_context()
    if feeling_ctx:
        system_prompt += feeling_ctx
        _log("🎨 フィーリングスライダーパラメータ注入")

    # ── 差分生成モード ─────────────────────────────────────
    # 既存ファイルがある場合は「変わる部分だけ出力」を指示する
    # → トークン数が1/5〜1/10になり生成速度が劇的に向上
    if existing and len(existing) > 200:
        system_prompt += (
            "\n\n【🚀 差分生成モード（重要）】\n"
            "ファイル全体を再生成してはいけない。\n"
            "変更が必要な部分だけを以下の形式で出力すること:\n"
            "```diff\n"
            "--- 変更前\n"
            "+++ 変更後\n"
            "@@ 変更箇所の説明 @@\n"
            "-削除する行\n"
            "+追加する行\n"
            "```\n"
            "変更がない部分は絶対に出力しない。差分のみ出力すること。\n"
            "ただし新規ファイル・大幅リファクタの場合は全体出力してよい。"
        )
        _log("🚀 差分生成モード有効: {}文字の既存コードあり".format(len(existing)))

    # ── 関連コンテキストのみ抽出（精度向上+トークン削減）──
    if existing:
        relevant_ctx = _extract_relevant_context(existing, desc, max_chars=1500)
        system_prompt += "\n\n【既存コード（関連部分のみ抽出）】\n{}".format(relevant_ctx)
    if rag_context:
        system_prompt += rag_context
    if lesson_ctx:
        system_prompt += lesson_ctx         # ⑧ 教訓
    if neg_cache_warning:
        system_prompt += neg_cache_warning  # 🚫 失敗パターン警告
    if graph_ctx:
        system_prompt += graph_ctx          # ⑪ 依存グラフ
    if engine_ctx:
        system_prompt += engine_ctx         # ⑬ エンジン別ルール
    if genre_ctx:
        system_prompt += genre_ctx          # ⑬ ジャンル別設計
    if game_ctx:
        system_prompt += game_ctx           # ⑫ 素材マニフェスト
    if internet_ctx:
        system_prompt += internet_ctx       # ⑥ 最新情報

    # ⑩ Phase 4+10: 複雑さ判定 + 自己モデルによる戦略補正
    complexity   = estimate_complexity(desc, existing)
    think_model  = select_model_by_complexity(complexity, MODELS)

    # 🤔 Phase 10: 自己モデルから戦略を取得して複雑さを補正
    task_strat = None
    if _SELF_MODEL_OK:
        task_strat = get_task_strategy(save_path, desc)
        if task_strat:
            if task_strat.caution:
                _log("🤔 自己モデル: {}".format(task_strat.caution[:60]))
                system_prompt += (
                    "\n\n【🤔 自己モデルからの注意】\n" + task_strat.caution)
            # 苦手分野なら複雑さを引き上げてより慎重に
            if task_strat.recommended_depth > complexity:
                complexity = task_strat.recommended_depth
                think_model = select_model_by_complexity(complexity, MODELS)
                _log("🤔 複雑さを{}に引き上げ（苦手分野）".format(complexity))

    # Phase 10: 定期的に自己モデルを再構築
    if _SELF_MODEL_OK and should_rebuild(save_path):
        _log("🤔 自己モデル再構築を開始...")
        try:
            rebuild_self_model(
                save_path,
                model=MODELS.get("optimizer", MODELS["coder"])
            )
        except Exception as e:
            _log("WARNING 自己モデル再構築失敗: {}".format(e))
    use_branching = bool(
        game_ctx or engine_ctx
        or graph_ctx and "HIGH" in graph_ctx
        or graph_ctx and "CRITICAL" in graph_ctx
        or any(k in desc.lower() for k in [
            "async", "非同期", "database", "データベース",
            "リアルタイム", "realtime", "マルチ", "multi",
            "ローグ", "rogue", "シミュレーション", "simulation",
            "タワー", "tower",
        ])
        or complexity >= 3  # Phase 4: 複雑さ3以上は常にDeep Thinking
    )

    # ⚡ Phase 3: 並列シミュ知見を注入（Branching前）
    parallel_insight = get_parallel_insight(save_path, desc)
    if parallel_insight and use_branching:
        system_prompt += parallel_insight
        _log("⚡ 並列シミュ知見注入: 過去の失敗パターンを反映")

    # 🧠 Phase 4: 複雑さに応じてDeep ThinkingまたはBranchingを選択
    thinking_log = None
    if _THINKING_OK and complexity >= 3:
        _log("🧠 Deep Thinking起動: 複雑さ{}/5 モデル={}".format(
            complexity, think_model))
        think_result = deep_think(
            desc, system_prompt,
            code_context=existing[:1000] if existing else "",
            model=think_model,
            max_depth=complexity,
        )
        if think_result and think_result.code:
            new_code     = think_result.code
            score_result = think_result.score
            branch_summary = (
                "🧠 Deep Thinking({depth}層) / 複雑さ{comp}/5 / "
                "{ms}ms / 理由: {reason}"
            ).format(
                depth=think_result.depth_used,
                comp=think_result.complexity,
                ms=think_result.total_ms,
                reason=think_result.final_reasoning[:60],
            )
            thinking_log = format_thinking_log(think_result)
            # Phase 3: 結果を並列キャッシュに記録
            record_parallel_result(
                save_path, desc, file_name,
                candidates={"thinking": {
                    "code": new_code, "score": score_result, "sandbox_ok": True
                }},
                chosen_path="thinking",
                reason=branch_summary,
            )
            _log("🧠 Deep Thinking完了: スコア{}".format(
                score_result.get("score", "?")))
        else:
            _log("🧠 Deep Thinking失敗 → Branchingにフォールバック")
            think_result = None
    else:
        think_result = None

    if think_result is None:
        # 🤖 Phase 8: 最高複雑度（5）はエージェントチームで協調
        if _SOCIETY_OK and complexity >= 5:
            _log("🤖 Agent Society起動: 複雑さ{}/5".format(complexity))
            coord_result = agent_coordinate(
                desc,
                anchor=anchor,
                project_path=save_path,
                model=think_model,
                max_rounds=min(complexity, 5),
                is_game_task=is_game_task,
            )
            if coord_result and coord_result.code:
                new_code     = coord_result.code
                score_result = coord_result.score
                branch_summary = (
                    "🤖 AgentSociety({rounds}ラウンド / "
                    "{agents}) / スコア{sc} / {reason}"
                ).format(
                    rounds=coord_result.rounds_used,
                    agents="+".join(coord_result.agents_used),
                    sc=score_result.get("score", "?"),
                    reason=coord_result.final_reason[:40],
                )
                if grand_state is not None:
                    grand_state["last_coord_log"] = \
                        format_coordination_log(coord_result)
                _log("🤖 Agent Society完了: {}ラウンド / スコア{}".format(
                    coord_result.rounds_used,
                    score_result.get("score", "?")))
            else:
                _log("🤖 Agent Society失敗 → Branchingにフォールバック")
                coord_result = None

            if coord_result is None:
                if use_branching:
                    _log("⑩ Branching有効: {}".format(file_name))
                    new_code, score_result, branch_summary = \
                        _branch_and_critique(desc, system_prompt, use_branching=True)
                else:
                    new_code, score_result = _generate_with_score_loop(
                        system_prompt, _build_cot_prefix(desc))
                    branch_summary = "単発生成（CoT適用）"

        elif use_branching:
            _log("⑩ Branching有効: {}".format(file_name))
            new_code, score_result, branch_summary = _branch_and_critique(
                desc, system_prompt, use_branching=True
            )
            record_parallel_result(
                save_path, desc, file_name,
                candidates={"chosen": {
                    "code": new_code, "score": score_result, "sandbox_ok": True
                }},
                chosen_path="chosen",
                reason=branch_summary,
            )
        else:
            _log("Coder 起動（通常モード）: {}".format(MODELS["coder"]))
            new_code, score_result = _generate_with_score_loop(
                system_prompt, _build_cot_prefix(desc)
            )
            branch_summary = "単発生成（CoT適用）"

    if not new_code:
        return "## ERROR {}\nコード生成に失敗しました".format(file_name), False

    # ── 差分適用 ────────────────────────────────────────────
    # AIが差分形式で返した場合は既存コードに適用して完成形にする
    if existing and _is_diff_output(new_code):
        _log("🚀 差分形式を検出 → 既存コードに適用")
        merged = apply_diff_output(existing, new_code)
        if merged and merged != existing:
            new_code = merged
            _log("🚀 差分適用完了: {}行 → {}行".format(
                len(existing.splitlines()), len(new_code.splitlines())))
        else:
            _log("WARNING 差分適用失敗 → 元の出力をそのまま使用")

    healed_code, success = self_heal(new_code, task_desc=desc)
    final_code = optimize(healed_code)
    diff       = apply_diff(existing, final_code)

    if auto_write:
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(final_code)
            _log("保存完了: {}".format(file_path))
            commit_all("Auto update: {}".format(file_name))
            # グラフキャッシュを更新（ファイルが変わったので）
            try:
                from graph import build_project_graph, save_graph
                cache_path = os.path.join(save_path, ".blackwell_graph.json")
                g = build_project_graph(save_path)
                save_graph(g, cache_path)
                _log("⑪ グラフ更新完了")
            except Exception as ge:
                _log("WARNING グラフ更新失敗: {}".format(ge))
        except Exception as e:
            _log("ERROR 保存: {}".format(e))
            success = False

    # Godot連携
    godot_dest = None
    if file_name.endswith((".gd", ".cs", ".gdscript")):
        godot_dest = export_to_godot(file_name, final_code, grand_state)

    store_memory(
        file_name, final_code,
        {
            "deps":    str(analyze_deps(final_code)),
            "path":    file_path,
            "success": str(success),
            "score":   str(score_result.get("score", "?")),
        }
    )

    # ⑧ 教訓を抽出・記録（既存維持）
    _extract_lesson(desc, final_code, score_result, success)

    # 🧠 Phase 4: 思考ログをgrand_stateに保存（app.pyで参照）
    if thinking_log and grand_state is not None:
        grand_state["last_thinking_log"] = thinking_log

    # 🧬 Phase 6: 定期的にプロンプト自己進化を実行
    if _EVOLVER_OK and should_evolve(save_path):
        _log("🧬 プロンプト進化分析を開始...")
        try:
            evo_result = analyze_and_evolve(
                save_path, ROLES,
                model=MODELS.get("optimizer", MODELS["coder"])
            )
            if evo_result and evo_result.evolved:
                _log("🧬 プロンプト進化完了: {}件の改善 / スコア+{}予測".format(
                    len(evo_result.improvements),
                    evo_result.score_delta,
                ))
                if grand_state is not None:
                    grand_state["last_evolution"] = {
                        "patterns":     len(evo_result.patterns_found),
                        "improvements": len(evo_result.improvements),
                        "score_delta":  evo_result.score_delta,
                        "timestamp":    evo_result.timestamp,
                    }
        except Exception as _evo_err:
            _log(f"WARNING 進化分析失敗（スキップ）: {_evo_err}")

    # 🤔 Phase 10: Agent Societyの信頼スコア更新
    if _SELF_MODEL_OK and "last_coord_log" in (grand_state or {}):
        coord_log = grand_state.get("last_coord_log", {})
        for agent in coord_log.get("agents_used", []):
            update_trust(save_path, agent, success)

    # 🔌 Godot Bridge: 修正コードをGodotエディタに自動送信
    if _BRIDGE_OK and success and new_code and bridge_connected():
        try:
            bridge_send_code(file_name, new_code)
            bridge_notify(f"✅ {file_name} を更新しました", "info")
            _log("🔌 Godotに送信: {}".format(file_name))
        except Exception as _bridge_err:
            _log("WARNING Godot送信失敗: {}".format(_bridge_err))

    # 📄 ドキュメント自動同期（CHANGELOG + TODO を常時更新）
    if _DOC_SYNC_OK and success:
        try:
            _doc_sync_task(save_path, anchor, file_name, desc)
        except Exception as _doc_err:
            _log("WARNING doc_sync失敗: {}".format(_doc_err))

    # 🗂️ バージョン管理AI: タスク完了時に自動コミット
    if _GIT_AI_OK and success:
        try:
            _git_auto_commit(save_path, task_desc=desc,
                             files_changed=[file_name])
        except Exception as _git_err:
            _log("WARNING auto_commit失敗: {}".format(_git_err))

    # 🗺️ Phase 1: 地図自動更新 + 意図記録
    if os.path.exists(file_path):
        update_file_entry(save_path, file_path)
        auto_store_intent(save_path,
                          os.path.relpath(file_path, save_path),
                          final_code, desc)

    # 📜 Phase 2: 契約自動登録 + 履歴記録
    rel_path = os.path.relpath(file_path, save_path)
    auto_register_contracts(save_path, rel_path, final_code)
    record_task_result(
        save_path, file_name, desc, final_code,
        score=score_result.get("score", 50),
        success=success,
        feedback=score_result.get("feedback", ""),
    )

    # 🔮 Phase 3: リスク予測記録（次回この変えるときの警告に活きる）
    predict_risks(save_path, rel_path, final_code, desc)

    # 📚 Phase 5: 学習データ自動収集
    from blackwell_history import _extract_tags
    _tags = _extract_tags(desc + " " + final_code[:200])
    collected = collect_training(
        save_path, desc, final_code,
        score=score_result.get("score", 0),
        language=_detect_code_language(final_code),
        tags=_tags,
        thinking_log=thinking_log,
        file_name=file_name,
    )
    if collected:
        _log("📚 学習データ収集: score={} / {}".format(
            score_result.get("score", 0), file_name))
        # ファインチューニング推奨チェック
        if should_finetune(save_path):
            _log("🎓 学習データが100件を超えました！ファインチューニングを推奨します")

    status    = "OK" if success else "WARN"
    score_val = score_result.get("score", "?")
    godot_info  = "\n**Godot書き出し:** `{}`".format(godot_dest) if godot_dest else ""
    graph_info  = "\n**依存グラフ:** {}".format(graph_ctx.split("\n")[1] if graph_ctx else "未解析")
    lesson_note = " ＋教訓注入" if lesson_ctx else ""
    branch_note = " ＋Branching" if use_branching else ""

    result_md = (
        "## [{status}] {file} （スコア: {score}/100{lesson}{branch}）\n\n"
        "**生成戦略:** {bsummary}\n\n"
        "**保存先:** `{path}`{godot}{graph}\n\n"
        "**依存:** `{deps}`\n\n"
        "**AI評価:** {feedback}\n\n"
        "### 差分\n```diff\n{diff}\n```\n\n"
        "### 生成コード\n```python\n{code}\n```"
    ).format(
        status=status, file=file_name, score=score_val,
        lesson=lesson_note, branch=branch_note,
        bsummary=branch_summary,
        path=file_path, godot=godot_info, graph=graph_info,
        deps=", ".join(analyze_deps(final_code)) or "なし",
        feedback=score_result.get("feedback", ""),
        diff=diff, code=final_code,
    )
    return result_md, success


# ============================================================
# メイン自律開発ループ
# ============================================================

def autonomous_dev(goal, auto_write=False, save_path="./", anchor="", history=None, max_cycles=3):
    clear_execution_log()
    _log("autonomous_dev 開始 | cycles={} | auto_write={}".format(max_cycles, auto_write))

    grand_state  = load_grand_state(save_path)
    current_goal = goal
    all_results  = []

    for cycle in range(max_cycles):
        _log("=== サイクル {}/{} ===".format(cycle + 1, max_cycles))

        # ステージ1: 計画
        tasks = plan(current_goal, anchor=anchor, history=history, grand_state=grand_state)
        if not tasks:
            _log("WARNING: タスクが生成されなかった")
            break

        # ステージ2: 自己批判（Phase 2 ⑦）
        critique_result = _self_critique(current_goal, tasks, anchor=anchor)
        risk = critique_result.get("risk_score", 0)
        if risk >= 40 and critique_result.get("improved_tasks"):
            _log("⑦ リスク{}点 → 改善済みタスクで実行".format(risk))
            tasks = critique_result["improved_tasks"]
            # 批判サマリーを結果に追加
            all_results.append(
                "### 🧠 自己批判フェーズ（リスク: {}/100）\n"
                "**指摘:** {}\n\n"
                "**改善点:**\n{}".format(
                    risk,
                    critique_result.get("critique", ""),
                    "\n".join("- " + i for i in critique_result.get("improvements", []))
                )
            )
        else:
            _log("⑦ リスク{}点 → 元の計画で実行".format(risk))

        # ステージ3: 実行
        failed_files = []
        for task in tasks:
            result_md, success = process_task(
                task,
                auto_write=auto_write,
                save_path=save_path,
                anchor=anchor,
                grand_state=grand_state,
            )
            all_results.append(result_md)
            if not success:
                failed_files.append(task.get("file", "unknown"))

        if not failed_files:
            _log("全タスク成功！")
            break
        else:
            _log("失敗ファイル: {} → 再挑戦".format(failed_files))
            current_goal = (
                "以下のファイルでエラーが発生した。修正・再実装せよ:\n"
                "対象: {files}\n\n元の目標:\n{goal}"
            ).format(files=", ".join(failed_files), goal=goal)

    log_summary = "\n".join(get_execution_log())
    all_results.append("\n\n---\n\n## 実行ログ\n```\n{}\n```".format(log_summary))
    return "\n\n---\n\n".join(all_results)


# ============================================================
# 知識吸収
# ============================================================

def analyze_and_absorb(file_name, content):
    _log("知識吸収: {}".format(file_name))
    prompt = (
        "あなたは伝説的なソフトウェアアーキテクトです。\n"
        "以下のファイルを深く分析し今後の開発に活かせる知恵を400〜600文字で抽出してください。\n\n"
        "ファイル名: {name}\n内容:\n{content}"
    ).format(name=file_name, content=content[:5000])
    try:
        res    = ollama.chat(model=MODELS["planner"], messages=[{"role": "user", "content": prompt}])
        wisdom = res["message"]["content"]
        store_memory(
            "wisdom_{}".format(file_name),
            "【{}から学んだ知恵】\n{}".format(file_name, wisdom),
            {"type": "wisdom", "source": file_name}
        )
        _log("知識吸収完了: {}".format(file_name))
        return wisdom
    except Exception as e:
        _log("ERROR 知識吸収: {}".format(e))
        return "エラー: {}".format(e)


# ============================================================
# ⑥ 会話（インターネット検索統合）
# ============================================================

def chat_with_persona(message, persona="", history=None, anchor="", use_internet=True, grand_state=None):
    """
    性格付きの会話AI。
    use_internet=True の場合、メッセージに応じてインターネット検索を自動実行して回答精度を向上。
    """
    _log("chat_with_persona: {}...".format(message[:40]))

    system_parts = []
    if persona.strip():
        system_parts.append("【あなたの性格・口調】\n{}".format(persona))
    if anchor.strip():
        system_parts.append("【プロジェクト主軸（参考知識）】\n{}".format(anchor))
    system_parts.append(
        "あなたは Blackwell Dev-OS に統合された AI アシスタントです。"
        "ユーザーの質問に丁寧かつ的確に答えてください。"
        "コードの質問には必ずコードブロックで答えてください。"
    )

    # ⑥ インターネット検索を自動実行
    if use_internet:
        token = ""
        if grand_state:
            token = grand_state.get("github_token", "")
        internet_ctx = _build_internet_context(message, grand_state)
        if internet_ctx:
            system_parts.append(internet_ctx)

    messages = [{"role": "system", "content": "\n\n".join(system_parts)}]
    if history:
        messages.extend(history[-10:])
    messages.append({"role": "user", "content": message})

    try:
        res   = ollama.chat(model=MODELS["chat"], messages=messages)
        reply = res["message"]["content"]
        _log("会話応答: {}文字".format(len(reply)))
        return reply
    except Exception as e:
        _log("ERROR 会話: {}".format(e))
        return "エラー: {}".format(e)


# ============================================================
# 自律監視
# ============================================================

def monitor_project(save_path, anchor=""):
    _log("自律監視スタート: {}".format(save_path))
    target_exts = {".py", ".gd", ".js", ".ts", ".cs"}
    code_files  = []

    try:
        for root_dir, dirs, files in os.walk(save_path):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "node_modules", "venv", ".venv"}]
            for f in files:
                if os.path.splitext(f)[1].lower() in target_exts:
                    code_files.append(os.path.join(root_dir, f))
    except Exception as e:
        return {"files_scanned": 0, "issues": [], "suggestions": [str(e)], "next_actions": [], "overall_health": "warning"}

    if not code_files:
        return {"files_scanned": 0, "issues": [], "suggestions": ["コードファイルなし"], "next_actions": ["最初のタスクを指示してください"], "overall_health": "warning"}

    file_summaries = []
    syntax_issues  = []

    for fp in code_files[:10]:
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                content = f.read()
            rel = os.path.relpath(fp, save_path)
            if fp.endswith(".py"):
                try:
                    ast.parse(content)
                except SyntaxError as se:
                    syntax_issues.append({"file": rel, "problem": "構文エラー: {} (line {})".format(se.msg, se.lineno), "severity": "critical"})
            file_summaries.append("### {}\n```\n{}\n```".format(rel, content[:600]))
        except Exception:
            pass

    prompt = (
        "プロジェクト品質管理AIです。以下を分析し JSON のみで返してください。\n\n"
        "主軸: {anchor}\n\nファイル:\n{files}\n\n"
        '{{"issues":[{{"file":"","problem":"","severity":"critical/warning/info"}}],'
        '"suggestions":[""],"next_actions":[""],"overall_health":"good/warning/critical"}}'
    ).format(anchor=anchor or "未設定", files="\n".join(file_summaries[:5]))

    try:
        res   = ollama.chat(model=MODELS["planner"], messages=[{"role": "user", "content": prompt}])
        match = re.search(r"\{.*\}", res["message"]["content"], re.DOTALL)
        if match:
            result = json.loads(match.group(0))
            result.setdefault("issues", [])
            result["issues"].extend(syntax_issues)
            result["files_scanned"] = len(code_files)
            store_memory("monitor_latest", json.dumps(result, ensure_ascii=False), {"type": "monitor"})
            return result
    except Exception as e:
        _log("ERROR 監視: {}".format(e))

    return {"files_scanned": len(code_files), "issues": syntax_issues, "suggestions": ["診断失敗"], "next_actions": [], "overall_health": "warning" if syntax_issues else "good"}


# ============================================================
# Stable Diffusion 画像生成
# ============================================================

def generate_image_sd(prompt, negative_prompt="", save_dir="./", grand_state=None):
    if grand_state is None:
        grand_state = load_grand_state()
    sd      = grand_state.get("sd_settings", {})
    api_url = sd.get("api_url", "http://127.0.0.1:7860")
    payload = {
        "prompt":          prompt,
        "negative_prompt": negative_prompt or "low quality, blurry, deformed",
        "steps":           sd.get("steps", 25),
        "width":           sd.get("width",  1024),
        "height":          sd.get("height", 1024),
        "cfg_scale":       7,
        "sampler_name":    "DPM++ 2M Karras",
    }
    _log("SD画像生成: {}...".format(prompt[:40]))
    try:
        res  = requests.post("{}/sdapi/v1/txt2img".format(api_url), json=payload, timeout=120)
        data = res.json()
        imgs = data.get("images", [])
        if not imgs:
            return {"success": False, "path": "", "error": "画像データなし"}
        img_data  = base64.b64decode(imgs[0])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(save_dir, exist_ok=True)
        save_path_img = os.path.join(save_dir, "sd_{}.png".format(timestamp))
        with open(save_path_img, "wb") as f:
            f.write(img_data)
        return {"success": True, "path": save_path_img, "error": ""}
    except requests.exceptions.ConnectionError:
        return {"success": False, "path": "", "error": "SD WebUI が起動していません（--api オプション付きで起動）"}
    except Exception as e:
        return {"success": False, "path": "", "error": str(e)}


# ============================================================
# AIVtuber基盤
# ============================================================

def speak_voicevox(text, speaker_id=1, save_dir="./", voicevox_url="http://127.0.0.1:50021"):
    _log("VOICEVOX 音声合成: {}...".format(text[:30]))
    try:
        query_res = requests.post(
            "{}/audio_query".format(voicevox_url),
            params={"text": text, "speaker": speaker_id}, timeout=30
        )
        if query_res.status_code != 200:
            return {"success": False, "path": "", "error": "audio_query 失敗"}
        synth_res = requests.post(
            "{}/synthesis".format(voicevox_url),
            params={"speaker": speaker_id}, json=query_res.json(), timeout=60
        )
        if synth_res.status_code != 200:
            return {"success": False, "path": "", "error": "synthesis 失敗"}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(save_dir, exist_ok=True)
        wav_path  = os.path.join(save_dir, "voice_{}.wav".format(timestamp))
        with open(wav_path, "wb") as f:
            f.write(synth_res.content)
        _log("VOICEVOX 音声保存: {}".format(wav_path))
        return {"success": True, "path": wav_path, "error": ""}
    except requests.exceptions.ConnectionError:
        return {"success": False, "path": "", "error": "VOICEVOX が起動していません"}
    except Exception as e:
        return {"success": False, "path": "", "error": str(e)}


def transcribe_whisper(audio_path, model_size="base", language="ja"):
    _log("Whisper 音声認識: {}".format(audio_path))
    if not os.path.exists(audio_path):
        return {"success": False, "text": "", "error": "ファイルが見つかりません"}
    try:
        from faster_whisper import WhisperModel
        model  = WhisperModel(model_size, device="cuda", compute_type="float16")
        segs, _ = model.transcribe(audio_path, language=language)
        text   = "".join([seg.text for seg in segs])
        return {"success": True, "text": text.strip(), "error": ""}
    except ImportError:
        pass
    try:
        import whisper
        model  = whisper.load_model(model_size)
        result = model.transcribe(audio_path, language=language)
        return {"success": True, "text": result.get("text", "").strip(), "error": ""}
    except ImportError:
        return {"success": False, "text": "", "error": "pip install faster-whisper または pip install openai-whisper が必要"}
    except Exception as e:
        return {"success": False, "text": "", "error": str(e)}


def aivtuber_respond(user_text, persona="", speaker_id=1,
                     voicevox_url="http://127.0.0.1:50021",
                     voice_save_dir="./voices", history=None):
    _log("AIVtuber応答: {}...".format(user_text[:30]))
    reply_text = chat_with_persona(
        message=user_text,
        persona=persona or (
            "あなたはVRストリーマーのAIVtuberです。\n"
            "明るく親しみやすい口調で短めに答えてください。\n"
            "1〜2文で端的に答えてください。"
        ),
        history=history or [],
        use_internet=True,
    )
    voice_result = speak_voicevox(
        text=reply_text, speaker_id=speaker_id,
        save_dir=voice_save_dir, voicevox_url=voicevox_url,
    )
    return {
        "reply_text":  reply_text,
        "voice_path":  voice_result.get("path", ""),
        "success":     voice_result.get("success", False),
        "voice_error": voice_result.get("error", ""),
    }

# ============================================================
# 🎨 フィーリングスライダーコンテキスト注入
# game_theory.pyのパラメータをコード生成プロンプトに注入する
# ============================================================

# グローバルフィーリングパラメータ（app.pyから設定される）
_current_feeling_params: dict = {}

def set_feeling_params(params: dict):
    """app.pyのフィーリングスライダーUIから呼ばれる"""
    global _current_feeling_params
    _current_feeling_params = params or {}
    _log("🎨 フィーリングパラメータ設定: {}項目".format(len(params)))


def _build_feeling_context() -> str:
    """フィーリングスライダーのパラメータをプロンプト用文字列に変換"""
    if not _current_feeling_params:
        return ""
    p = _current_feeling_params
    return (
        "\n\n【🎨 フィーリングスライダー設定（必ず反映せよ）】\n"
        "以下のパラメータ値はプレイヤーの「感触設計」から自動計算されたものだ。\n"
        "コード内の対応する定数・変数はこの値に合わせること。\n\n"
        "プレイヤー速度: {speed:.1f}\n"
        "重力: {gravity:.0f}\n"
        "ジャンプ力: {jump:.0f}\n"
        "ヒットストップ: {hit_stop}フレーム\n"
        "ノックバック力: {knockback:.0f}\n"
        "カメラシェイク強度: {shake:.1f}\n"
        "パーティクル数: {particles}\n"
        "敵速度倍率: {enemy_speed:.2f}\n"
        "BGM推奨BPM: {bgm}BPM\n\n"
        "感触の説明: {desc}\n"
        "→ 上記の数値を尊重して実装すること。数値を変えてはいけない。"
    ).format(
        speed=p.get("player_speed", 5.0),
        gravity=p.get("player_gravity", 800),
        jump=p.get("player_jump_power", -600),
        hit_stop=p.get("hit_stop_frames", 4),
        knockback=p.get("knockback_force", 300),
        shake=p.get("camera_shake_intensity", 5.0),
        particles=p.get("particle_count", 20),
        enemy_speed=p.get("enemy_speed_mult", 1.0),
        bgm=p.get("bgm_bpm_target", 120),
        desc=p.get("description", "標準設定"),
    )


# ============================================================
# 🚀 差分適用エンジン
# AIが差分形式で出力した場合に既存ファイルへ適用する
# ============================================================

def apply_diff_output(existing_code: str, diff_output: str) -> str:
    """
    AIが出力した差分を既存コードに適用して完成形コードを返す。

    差分形式:
      -削除する行
      +追加する行
      (変更なし行はそのまま)
    """
    if not diff_output.strip():
        return existing_code

    # 差分形式かどうか判定
    has_diff_markers = any(
        line.startswith(("+++ ", "--- ", "@@ ", "-", "+"))
        for line in diff_output.splitlines()[:5]
    )
    if not has_diff_markers:
        # 差分形式でなければそのままコードとして扱う
        return diff_output

    try:
        import difflib
        existing_lines = existing_code.splitlines()
        result_lines   = list(existing_lines)

        for line in diff_output.splitlines():
            if line.startswith("+++ ") or line.startswith("--- ") or line.startswith("@@ "):
                continue
            if line.startswith("-") and not line.startswith("---"):
                # 削除: マッチする行を探して削除
                target = line[1:]
                for i, rl in enumerate(result_lines):
                    if rl.strip() == target.strip():
                        result_lines.pop(i)
                        break
            elif line.startswith("+") and not line.startswith("+++"):
                # 追加: そのまま末尾に追加（簡易版）
                result_lines.append(line[1:])

        return "\n".join(result_lines)
    except Exception as e:
        _log("WARNING 差分適用失敗、元のコードを返す: {}".format(e))
        return existing_code


# ============================================================
# 🤖 マルチエージェント並列生成
# 設計・実装・テスト・ゲームデザインの4専門AIを並列実行
# ============================================================

AGENT_ROLES = {
    "architect": (
        "あなたはソフトウェアアーキテクトAIです。\n"
        "実装の前に設計を考えます。クラス構造・インターフェース・依存関係を設計し、\n"
        "実装の注意点を箇条書きで出力してください。コードは書かない。"
    ),
    "coder": (
        "あなたはコーディング専門AIです。\n"
        "与えられた設計仕様に従って、動作するコードのみを出力してください。\n"
        "コメントは最小限。品質と動作を最優先。"
    ),
    "tester": (
        "あなたはテスト専門AIです。\n"
        "与えられたコードのバグ・エッジケース・例外処理の漏れを指摘してください。\n"
        "具体的な問題箇所と修正案を出力してください。"
    ),
    "game_designer": (
        "あなたはゲームデザイナーAIです。MDA理論とフロー理論の専門家です。\n"
        "与えられた機能が「面白さ」に貢献しているか評価し、\n"
        "プレイヤー体験をさらに良くする提案を3点出力してください。"
    ),
}


def multi_agent_generate(
    desc: str,
    anchor: str = "",
    save_path: str = "./",
    use_agents: tuple = ("architect", "coder", "tester"),
) -> dict:
    """
    複数専門AIを並列実行してコードを生成する。

    フロー:
      1. architect: 設計仕様を生成
      2. coder:     設計を受けてコードを生成（並列可能）
         game_designer: MDA評価（並列）
      3. tester:    コードのバグチェック（並列）
      4. 統合: best_codeを選定して返す

    戻り値: {
      "code": str, "design": str, "test_feedback": str,
      "game_feedback": str, "summary": str
    }
    """
    import threading

    results = {}
    errors  = {}

    def _run_agent(name: str, prompt: str):
        try:
            res = ollama.chat(
                model=MODELS["coder"],
                messages=[
                    {"role": "system", "content": AGENT_ROLES[name]},
                    {"role": "user",   "content": prompt},
                ],
            )
            results[name] = res["message"]["content"]
            _log("🤖 Agent[{}] 完了 ({} chars)".format(name, len(results[name])))
        except Exception as e:
            errors[name]  = str(e)
            results[name] = ""
            _log("WARNING Agent[{}] 失敗: {}".format(name, e))

    _log("🤖 マルチエージェント起動: {}".format(list(use_agents)))

    # Phase 1: architect（逐次 — 後続エージェントが依存するため）
    if "architect" in use_agents:
        arch_prompt = f"【主軸】{anchor}\n\n【実装タスク】{desc}"
        _run_agent("architect", arch_prompt)
        design_spec = results.get("architect", "")
    else:
        design_spec = desc

    # Phase 2: coder + game_designer を並列実行
    threads = []
    parallel_agents = [a for a in use_agents if a in ("coder", "game_designer")]

    for agent in parallel_agents:
        if agent == "coder":
            prompt = f"【設計仕様】\n{design_spec}\n\n【実装タスク】\n{desc}\n\n【主軸】{anchor}"
        else:
            prompt = f"【機能説明】\n{desc}\n\n【MDA評価をしてください】"
        t = threading.Thread(target=_run_agent, args=(agent, prompt))
        t.start()
        threads.append(t)

    for t in threads:
        t.join(timeout=120)

    # Phase 3: tester（coderの出力を受けて動く）
    if "tester" in use_agents:
        code_to_test = extract_code(results.get("coder", ""))
        if code_to_test:
            _run_agent("tester", f"以下のコードをレビューしてください:\n```\n{code_to_test}\n```")

    # 最終コード抽出
    raw_code     = results.get("coder", "")
    final_code   = extract_code(raw_code)
    test_fb      = results.get("tester", "")
    game_fb      = results.get("game_designer", "")
    design_out   = results.get("architect", "")

    # testerの指摘を元に自動修正
    if test_fb and "重大" in test_fb or "クラッシュ" in test_fb:
        _log("🤖 Testerが重大な問題を指摘 → 自動修正")
        fix_prompt = (
            f"以下のコードに対してテスターが指摘しました:\n{test_fb}\n\n"
            f"指摘を全て修正した完全なコードを出力してください:\n{final_code}"
        )
        try:
            res = ollama.chat(
                model=MODELS["coder"],
                messages=[{"role": "user", "content": fix_prompt}]
            )
            final_code = extract_code(res["message"]["content"]) or final_code
        except Exception:
            pass

    agent_summary = (
        "🤖 マルチエージェント完了\n"
        "  設計AI: {}文字\n"
        "  実装AI: {}文字\n"
        "  テストAI: {}文字\n"
        "  ゲームデザインAI: {}文字"
    ).format(
        len(design_out), len(raw_code), len(test_fb), len(game_fb)
    )
    _log(agent_summary)

    return {
        "code":          final_code,
        "design":        design_out,
        "test_feedback": test_fb,
        "game_feedback": game_fb,
        "summary":       agent_summary,
        "errors":        errors,
    }


# ============================================================
# ⚡ ストリーミング生成（Ollama stream=True）
# UIが固まらなくなる。Streamlitのst.write_streamと組み合わせる
# ============================================================

def stream_generate(
    desc: str,
    system_prompt: str = "",
    model: str = "",
) -> "generator":
    """
    Ollamaのストリーミングモードでコードをトークンごとに返すジェネレータ。

    Streamlitでの使い方:
        with st.chat_message("assistant"):
            response = st.write_stream(stream_generate(desc, system_prompt))

    戻り値: str のジェネレータ（各イテレーションで1トークン）
    """
    model = model or MODELS["coder"]
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": desc})

    try:
        stream = ollama.chat(
            model=model,
            messages=messages,
            stream=True,
        )
        for chunk in stream:
            token = chunk.get("message", {}).get("content", "")
            if token:
                yield token
    except Exception as e:
        yield f"\n\n[ERROR: ストリーミング失敗 — {e}]"


def stream_autonomous_dev(
    goal: str,
    anchor: str = "",
    save_path: str = "./",
) -> "generator":
    """
    autonomous_devのストリーミング版。
    設計フェーズのプランナー出力をリアルタイムで流す。

    Streamlitでの使い方:
        result = st.write_stream(stream_autonomous_dev(goal, anchor))
    """
    grand_state = load_grand_state(save_path)

    # Phase 1: Plan をストリーミングで出力
    plan_prompt = (
        f"【主軸】{anchor}\n\n"
        f"以下のゴールを実現するための実装計画を日本語で説明しながら作ってください:\n{goal}"
    )
    yield "### 🧠 設計フェーズ\n\n"
    full_plan = ""
    for token in stream_generate(plan_prompt, model=MODELS["planner"]):
        full_plan += token
        yield token

    yield "\n\n---\n### ⚙️ 実装フェーズ\n\n"

    # Phase 2: Code をストリーミングで出力
    system_prompt = ROLES["coder"]
    if anchor:
        system_prompt += f"\n\n【主軸】{anchor}"
    feeling_ctx = _build_feeling_context()
    if feeling_ctx:
        system_prompt += feeling_ctx

    code_prompt = f"【計画】\n{full_plan[:1000]}\n\n【実装タスク】\n{goal}"
    full_code = ""
    for token in stream_generate(code_prompt, system_prompt):
        full_code += token
        yield token

    yield "\n\n✅ ストリーミング生成完了"


# ============================================================
# AIプレイテスト完全自動化
# Godotをヘッドレスで起動→結果を読み込む→バグ修正まで自動
# ============================================================

def run_playtest_auto(
    project_path: str,
    scene_path: str = "res://scenes/main.tscn",
    godot_exe: Optional[str] = None,
    timeout: int = 60,
) -> dict:
    """
    Godotをヘッドレスで自動プレイテストして結果を返す。

    1. ai_playtest.gd を生成（未存在なら）
    2. Godot --headless --script で実行
    3. playtest_result.json を読み込んで診断
    """
    from game_theory import generate_playtest_script, parse_playtest_result

    # スクリプト生成
    script_path = os.path.join(project_path, "ai_playtest.gd")
    if not os.path.exists(script_path):
        script = generate_playtest_script(scene_path)
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)
        _log("🤖 AIプレイスクリプト生成: {}".format(script_path))

    # Godot実行ファイル探索
    if not godot_exe:
        from build_pipeline import find_godot_exe
        godot_exe = find_godot_exe()

    if not godot_exe:
        return {"success": False, "error": "Godot実行ファイルが見つかりません"}

    # ヘッドレス実行
    result_path = os.path.join(project_path, "playtest_result.json")
    try:
        cmd = [godot_exe, "--headless", "--script", "ai_playtest.gd", "--path", project_path]
        _log("🤖 Godotヘッドレス起動: {}".format(" ".join(cmd)))
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=project_path)
        _log("🤖 Godot終了 (returncode={})".format(proc.returncode))
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"タイムアウト（{timeout}秒）"}
    except Exception as e:
        return {"success": False, "error": str(e)}

    # 結果読み込み
    if not os.path.exists(result_path):
        return {"success": False, "error": "playtest_result.json が生成されませんでした\n" + proc.stderr[:300]}

    try:
        with open(result_path, encoding="utf-8") as f:
            result_data = json.load(f)
        report = parse_playtest_result(result_data)
        bugs   = result_data.get("bugs", [])

        return {
            "success":     True,
            "report":      report,
            "bugs":        bugs,
            "steps":       result_data.get("steps", 0),
            "max_x":       result_data.get("max_x_reached", 0),
            "result_path": result_path,
        }
    except Exception as e:
        return {"success": False, "error": f"結果解析失敗: {e}"}
