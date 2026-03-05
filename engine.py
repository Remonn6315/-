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

from memory import store_memory, retrieve_context
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

def extract_code(text):
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


def apply_diff(old, new):
    diff = list(difflib.unified_diff(
        old.splitlines(), new.splitlines(),
        fromfile="before", tofile="after", lineterm=""
    ))
    return "\n".join(diff) if diff else "（変更なし）"


# ============================================================
# project_grand_state.json 読み込み
# ============================================================

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

def score_code(code, task_desc=""):
    _log("スコアリング開始")
    prompt = (
        "あなたはコードレビューの専門家です。\n"
        "以下のコードを厳格に評価し、必ず JSON のみで返してください。\n\n"
        "タスク説明: {desc}\n\nコード:\n{code}\n\n"
        "JSON形式（前置き不要）:\n"
        '{{"score":整数0-100,'
        '"breakdown":{{"correctness":0-25,"readability":0-25,"safety":0-25,"efficiency":0-25}},'
        '"feedback":"200文字以内","passed":true/false}}'
    ).format(desc=task_desc, code=code[:3000])

    try:
        res   = ollama.chat(model=MODELS["optimizer"], messages=[{"role": "user", "content": prompt}])
        match = re.search(r"\{.*\}", res["message"]["content"], re.DOTALL)
        if match:
            result = json.loads(match.group(0))
            _log("スコア: {}/100".format(result.get("score", "?")))
            return result
    except Exception as e:
        _log("ERROR スコアリング: {}".format(e))
    return {"score": 50, "breakdown": {}, "feedback": "評価失敗", "passed": True}


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
        err = run_safe(cand["code"])
        sandbox_results[pname] = err is None  # Trueなら成功
        if err is None:
            _log("Branch {} Sandbox: 成功".format(pname))
        else:
            _log("Branch {} Sandbox: 失敗 - {}".format(pname, str(err)[:60]))

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
    asset_pipeline.py の物理解析を使ってゲーム開発コンテキストを生成。
    実際に画像を開いてフレーム数・サイズを測定した結果を注入する。
    Cursorにはできない: 「player_sheet.pngは4x3=12フレーム、各32x48px」が正確に入る。
    """
    game_keywords = [
        "ゲーム","game","player","プレイヤー","enemy","敵","モンスター",
        "sprite","tilemap","godot","pygame","unity","2d","3d",
        "アイテム","item","バトル","battle","マップ","map","stage",
        "rpg","アクション","action","シューター","shooter","platform",
        "ジャンプ","jump","移動","move","アニメーション","animation",
    ]
    desc_lower = desc.lower()
    if not any(k.lower() in desc_lower for k in game_keywords):
        return ""

    _log("🎮 素材パイプライン起動（物理解析）")
    ctx_parts = []

    # ── asset_pipeline による物理解析 ──────────────
    try:
        from asset_pipeline import scan_project_assets, build_pygame_context, save_manifest

        # キャッシュ確認（同じフォルダは再スキャンしない）
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

    # ── analyzer.py の類似プロジェクト提案（fallback兼用） ──
    try:
        from analyzer import suggest_from_similar, analyze_game_assets_folder, build_game_context_from_assets
        similar_ctx = suggest_from_similar(desc, "ゲーム")
        if similar_ctx:
            ctx_parts.append(similar_ctx)

        # asset_pipeline が使えなかった場合のfallback
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

def export_to_godot(file_name, code, grand_state=None):
    if grand_state is None:
        grand_state = load_grand_state()
    export_path = grand_state.get("paths", {}).get("code_export", "C:/AI_Dev/Source")
    try:
        os.makedirs(export_path, exist_ok=True)
        dest = os.path.join(export_path, file_name)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(code)
        _log("Godot書き出し: {}".format(dest))
        return dest
    except Exception as e:
        _log("ERROR Godot書き出し: {}".format(e))
        return None


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

    # ① RAGコンテキスト
    rag_context = _build_rag_context(desc, k=5)

    # ⑧ 過去の教訓を取得（Phase 2）
    lesson_ctx = _retrieve_lessons(desc, k=3)

    # 🚫 Negative Cache警告（失敗パターン）
    neg_cache_warning = _get_negative_cache_warning(desc)

    # ⑥ インターネット検索コンテキスト（スマート判定付き）
    internet_ctx = _build_internet_context_smart(desc, grand_state)

    # ⑪ 依存グラフコンテキスト（graph.py）
    graph_ctx = _build_graph_context(file_name, save_path)

    # ⑫ ゲーム開発コンテキスト（analyzer.py）
    game_ctx = _build_game_context(desc, save_path)

    # システムプロンプト組み立て
    system_prompt = ROLES["coder"]
    if anchor:
        system_prompt += "\n\n【プロジェクト主軸】\n{}".format(anchor)
    if existing:
        system_prompt += "\n\n【既存コード】\n{}".format(existing[:3000])
    if rag_context:
        system_prompt += rag_context
    if lesson_ctx:
        system_prompt += lesson_ctx       # ⑧ 教訓
    if neg_cache_warning:
        system_prompt += neg_cache_warning  # 🚫 失敗パターン警告
    if graph_ctx:
        system_prompt += graph_ctx        # ⑪ 依存グラフ
    if game_ctx:
        system_prompt += game_ctx         # ⑫ ゲーム知識
    if internet_ctx:
        system_prompt += internet_ctx     # ⑥ 最新情報

    # ⑩ 3案Branching判定
    # ゲーム開発・複雑タスク・複数ファイル波及時はBranching有効
    use_branching = bool(
        game_ctx                                       # ゲーム開発
        or graph_ctx and "HIGH" in graph_ctx           # 影響大
        or graph_ctx and "CRITICAL" in graph_ctx
        or any(k in desc.lower() for k in [            # 複雑系キーワード
            "async", "非同期", "database", "データベース",
            "リアルタイム", "realtime", "マルチ", "multi"
        ])
    )

    if use_branching:
        _log("⑩ Branching有効: {}".format(file_name))
        new_code, score_result, branch_summary = _branch_and_critique(
            desc, system_prompt, use_branching=True
        )
    else:
        _log("Coder 起動（通常モード）: {}".format(MODELS["coder"]))
        new_code, score_result = _generate_with_score_loop(
            system_prompt, _build_cot_prefix(desc)  # ⑨ CoT必須
        )
        branch_summary = "単発生成（CoT適用）"

    if not new_code:
        return "## ERROR {}\nコード生成に失敗しました".format(file_name), False

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

    # ⑧ 教訓を抽出・記録（Phase 2）
    _extract_lesson(desc, final_code, score_result, success)

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
