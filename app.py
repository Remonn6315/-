"""
Blackwell Dev-OS - app.py (完全版 v6.0)
v6.0 変更点:
- selectbox/expander/popover のドロップダウンまで完全ダーク対応
- 会話タブ: PCスペック状況 + おすすめモデル表示
- AIVtuberタブ追加（設定・VRStudio連携・診断）
- 会話が重い原因の説明と軽量モデル提案
"""

import streamlit as st
from engine import (
    autonomous_dev, analyze_and_absorb, MODELS,
    get_execution_log, chat_with_persona, monitor_project,
    score_code, generate_image_sd, speak_voicevox,
    transcribe_whisper, aivtuber_respond, load_grand_state
)
from gitops import init_repo, get_git_log, commit_all
from memory import list_memories, delete_memory, retrieve_context, get_memory_count
import os, subprocess, sys, json, requests

try:
    import tkinter as tk
    from tkinter import filedialog
    HAS_TK = True
except ImportError:
    HAS_TK = False

# ============================================================
# 1. ページ設定
# ============================================================
st.set_page_config(
    page_title="Blackwell Dev-OS",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# 2. セッション変数初期化
# ============================================================
defaults = {
    "target_path":       os.getcwd(),
    "init":              False,
    "project_anchor":    "このプロジェクトは自律型AI OS『Blackwell』の開発を主軸とする。常に最新のライブラリと堅牢な設計パターンを優先せよ。",
    "game_anchor":       "",   # ゲームの主軸（世界観・面白さの軸・ジャンル設計方針）
    "messages":          [],
    "chat_messages":     [],
    "improve_messages":  [],
    "auto_write":        True,
    "max_cycles":        3,
    "last_log":          [],
    "monitor_result":    None,
    "last_result":       "",
    "last_suggestion":   "",
    "thinking_log":      [],
    "persona":           "あなたはBlackwellという名の頼もしいAI開発パートナーです。日本語で、テキパキと的確に答えてください。コードの質問には必ずコードブロックを使ってください。",
    "dark_mode":         False,
    # ── モデル設定（session_stateで永続管理）──
    "model_planner":     "qwen3-next:80b",
    "model_coder":       "qwen2.5-coder:32b",
    "model_refiner":     "deepseek-r1:32b",
    "model_optimizer":   "qwen2.5-coder:14b",
    "model_chat":        "qwen3-next:80b",
    # ── インターネット・GitHub ──
    "use_internet":      True,
    "github_token":      "",
    "github_repo_url":   "",
    # ── ゲーム素材マップ ──
    "asset_map":         None,
    "target_engine":     "auto",
    "genre_override":    None,
    "engine_override":   None,
    "godot_version":     "4",
    "asset_folder":      "",
    # ── 戦略会議室 新UI ──
    "pending_suggestions": [],   # チェックボックス付き改善提案リスト
    "adopted_suggestions": [],   # 導入済み提案の記録
    "quality_check_result": "",  # 品質チェック結果
    "build_log":           [],   # 何を作ったかのログ
    "crash_check_result":  "",   # バグ/クラッシュチェック結果
    # AIVtuber設定
    "vt_persona":        "あなたはVRストリーマーのAIVtuberです。明るく親しみやすい口調で短めに答えてください。",
    "vt_speaker_id":     1,
    "vt_voicevox_url":   "http://127.0.0.1:50021",
    "vt_vrstudio_url":   "http://127.0.0.1:3030",
    "vt_sd_url":         "http://127.0.0.1:7860",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── セッション自動復元（前回の続きから）──────────────────────
if not st.session_state.get("_session_restored", False):
    try:
        from session_restore import load_session, restore_to_streamlit
        loaded = load_session()
        if loaded:
            restored = restore_to_streamlit(st.session_state, loaded)
            if restored:
                st.session_state["_session_restored_keys"] = restored
        st.session_state["_session_restored"] = True
    except Exception as _sr_err:
        st.session_state["_session_restored"] = True

# ── MODELS dict を session_state から毎回同期（これが根本修正）──
MODELS["planner"]   = st.session_state.model_planner
MODELS["coder"]     = st.session_state.model_coder
MODELS["refiner"]   = st.session_state.model_refiner
MODELS["optimizer"] = st.session_state.model_optimizer
MODELS["chat"]      = st.session_state.model_chat

if not st.session_state.init:
    init_repo()
    st.session_state.init = True


# ────────────────────────────────────────────────────────────
# ⚓ 主軸統合ヘルパー
# Blackwell主軸（project_anchor）とゲーム主軸（game_anchor）を
# 全タブで一貫して使えるよう1つの文字列に結合する。
# すべての autonomous_dev / chat_with_persona 呼び出しはここを使う。
# ────────────────────────────────────────────────────────────
def get_combined_anchor() -> str:
    """Blackwell主軸 + ゲーム主軸を結合して返す"""
    bw   = st.session_state.project_anchor.strip()
    game = st.session_state.game_anchor.strip()
    if game:
        return f"{bw}\n\n【🎮 ゲームの主軸】\n{game}"
    return bw

# ============================================================
# 3. テーマCSS
# ============================================================
is_dark = st.session_state.dark_mode

# BaseWebのドロップダウン・popoverまで含む完全ダーク対応CSS
if is_dark:
    BG      = "#0a0e1a"
    BG2     = "#0d1117"
    BG3     = "#111827"
    BORDER  = "#1e2a38"
    TEXT    = "#e8eaf0"
    TEXT2   = "#7a8a9a"
    ACCENT  = "#00e5ff"
    ACCENT2 = "#0066aa"
else:
    BG      = "#f8f9fa"
    BG2     = "#f0f2f6"
    BG3     = "#ffffff"
    BORDER  = "#d0d4dc"
    TEXT    = "#1a1a2e"
    TEXT2   = "#666880"
    ACCENT  = "#0066cc"
    ACCENT2 = "#004499"

title_color  = ACCENT
sub_color    = TEXT2
panel_color  = ACCENT
border_color = BORDER

theme_css = f"""
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Noto+Sans+JP:wght@400;700&display=swap');
html, body, [class*="css"] {{ font-family: 'Noto Sans JP', sans-serif; }}

/* ── メイン背景 ── */
.stApp {{ background-color: {BG} !important; }}
[data-testid="stAppViewContainer"] {{ background-color: {BG} !important; }}
[data-testid="stHeader"] {{ background-color: {BG} !important; }}
.block-container {{ background-color: {BG} !important; padding-top: 1rem !important; }}

/* ── テキスト全般 ── */
p, span, label, div, h1, h2, h3, h4, h5, h6, li, caption, small {{
    color: {TEXT} !important;
}}

/* ── タブ ── */
.stTabs [data-baseweb="tab-list"] {{
    background: {BG2} !important;
    border-bottom: 2px solid {BORDER} !important;
    gap: 2px !important;
}}
.stTabs [data-baseweb="tab"] {{
    background: {BG2} !important;
    color: {TEXT2} !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.72rem !important;
    border: 1px solid transparent !important;
    border-radius: 6px 6px 0 0 !important;
    padding: 6px 14px !important;
}}
.stTabs [aria-selected="true"] {{
    background: {BG3} !important;
    color: {ACCENT} !important;
    border-color: {BORDER} !important;
    border-bottom-color: {BG3} !important;
    font-weight: 700 !important;
}}
[data-testid="stTabContent"] {{
    background: {BG3} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 0 8px 8px 8px !important;
    padding: 1rem !important;
}}

/* ── 入力系 ── */
.stTextInput input, .stTextArea textarea, input[type="text"] {{
    background-color: {BG2} !important;
    color: {TEXT} !important;
    border-color: {BORDER} !important;
    border-radius: 6px !important;
}}
.stTextInput input:focus, .stTextArea textarea:focus {{
    border-color: {ACCENT} !important;
    box-shadow: 0 0 0 1px {ACCENT}44 !important;
}}

/* ── selectbox 本体 ── */
.stSelectbox > div > div {{
    background-color: {BG2} !important;
    color: {TEXT} !important;
    border-color: {BORDER} !important;
}}
.stSelectbox > div > div > div {{
    color: {TEXT} !important;
}}
/* ── selectbox ドロップダウン（BaseWeb popover・body直下に描画されるため全力指定）── */
[data-baseweb="popover"],
[data-baseweb="popover"] > div,
[data-baseweb="popover"] > div > div {{
    background-color: {BG2} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 8px !important;
    color: {TEXT} !important;
}}
[data-baseweb="popover"] ul,
[data-baseweb="popover"] ul li,
[data-baseweb="popover"] [role="listbox"],
[data-baseweb="popover"] [role="option"] {{
    background-color: {BG2} !important;
    color: {TEXT} !important;
}}
[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="popover"] [aria-selected="true"],
[data-baseweb="popover"] li:hover {{
    background-color: {BG3} !important;
    color: {ACCENT} !important;
}}
[data-baseweb="menu"],
[data-baseweb="menu"] > ul,
[data-baseweb="menu"] > div {{
    background-color: {BG2} !important;
    border: 1px solid {BORDER} !important;
    color: {TEXT} !important;
}}
[data-baseweb="menu"] [role="option"],
[data-baseweb="menu"] li {{
    background-color: {BG2} !important;
    color: {TEXT} !important;
}}
[data-baseweb="menu"] [role="option"]:hover,
[data-baseweb="menu"] [aria-selected="true"],
[data-baseweb="menu"] li:hover {{
    background-color: {BG3} !important;
    color: {ACCENT} !important;
}}
/* selectbox 本体 */
[data-baseweb="select"] > div,
[data-baseweb="select"] > div > div,
[data-baseweb="select"] > div > div > div {{
    background-color: {BG2} !important;
    border-color: {BORDER} !important;
    color: {TEXT} !important;
}}
/* body 直下の portal（Streamlit がページ外に描画するドロップダウン） */
body > div[data-baseweb="popover"],
body > div[data-baseweb="tooltip"],
#portal > div,
[class*="Popover"] {{
    background-color: {BG2} !important;
    border: 1px solid {BORDER} !important;
    color: {TEXT} !important;
}}
body > div[data-baseweb="popover"] *,
body > div[data-baseweb="tooltip"] * {{
    background-color: {BG2} !important;
    color: {TEXT} !important;
}}
body > div[data-baseweb="popover"] [role="option"]:hover,
body > div[data-baseweb="popover"] [aria-selected="true"] {{
    background-color: {BG3} !important;
    color: {ACCENT} !important;
}}

/* ── expander ── */
[data-testid="stExpander"] {{
    background-color: {BG2} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 8px !important;
}}
[data-testid="stExpander"] summary {{
    background-color: {BG2} !important;
    color: {TEXT} !important;
}}
.streamlit-expanderHeader {{
    background-color: {BG2} !important;
    color: {TEXT} !important;
}}
.streamlit-expanderContent {{
    background-color: {BG2} !important;
}}

/* ── コードブロック ── */
.stCodeBlock, pre, code {{
    background-color: {BG2} !important;
    color: {"#a8d8a8" if is_dark else "#1a1a2e"} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 6px !important;
}}

/* ── info/success/warning/error ── */
[data-testid="stInfo"] {{
    background-color: {"#0a1628" if is_dark else "#e8f4fd"} !important;
    border-left: 4px solid {ACCENT} !important;
    color: {TEXT} !important;
}}
[data-testid="stSuccess"] {{
    background-color: {"#0a2010" if is_dark else "#e8f5e9"} !important;
    color: {TEXT} !important;
}}
[data-testid="stWarning"] {{
    background-color: {"#1a1200" if is_dark else "#fff8e1"} !important;
    color: {TEXT} !important;
}}
[data-testid="stError"] {{
    background-color: {"#1a0505" if is_dark else "#fce4ec"} !important;
    color: {TEXT} !important;
}}

/* ── metric ── */
[data-testid="stMetricValue"] {{ color: {ACCENT} !important; font-weight: 700 !important; }}
[data-testid="stMetricLabel"] {{ color: {TEXT2} !important; }}

/* ── container/border ── */
[data-testid="stVerticalBlockBorderWrapper"] > div {{
    background-color: {BG2} !important;
    border-color: {BORDER} !important;
    border-radius: 8px !important;
}}

/* ── チャット ── */
[data-testid="stChatMessage"] {{
    background-color: {BG2} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 10px !important;
    margin-bottom: 6px !important;
}}
[data-testid="stChatInputContainer"] {{
    background-color: {BG2} !important;
    border: 2px solid {ACCENT}88 !important;
    border-radius: 12px !important;
}}
[data-testid="stChatInputContainer"] textarea {{
    background-color: {BG2} !important;
    color: {TEXT} !important;
}}

/* ── ボタン ── */
.stButton > button {{
    border-radius: 6px !important;
    font-family: 'Noto Sans JP', sans-serif !important;
}}

/* ── slider ── */
[data-testid="stSlider"] > div > div {{
    color: {TEXT} !important;
}}
[data-baseweb="slider"] [role="slider"] {{
    background-color: {ACCENT} !important;
}}

/* ── checkbox ── */
[data-testid="stCheckbox"] label {{ color: {TEXT} !important; }}

/* ── divider ── */
hr {{ border-color: {BORDER} !important; }}

/* ── scrollbar ── */
::-webkit-scrollbar {{ width: 6px; height: 6px; }}
::-webkit-scrollbar-track {{ background: {BG}; }}
::-webkit-scrollbar-thumb {{ background: {BORDER}; border-radius: 3px; }}
::-webkit-scrollbar-thumb:hover {{ background: {ACCENT}88; }}

/* ── タイトル ── */
.bw-title {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.6rem; font-weight: 700;
    letter-spacing: 0.15em;
    padding: 0.4rem 0 0.2rem 0;
    margin-bottom: 0.4rem;
    color: {ACCENT} !important;
    border-bottom: 2px solid {ACCENT}44 !important;
}}
.bw-subtitle {{
    font-size: 0.72rem; color: {TEXT2} !important;
    font-family: 'JetBrains Mono', monospace;
    margin-bottom: 0.8rem;
}}
.bw-panel-title {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem; color: {ACCENT} !important;
    text-transform: uppercase; letter-spacing: 0.12em;
    margin-bottom: 0.5rem; padding-bottom: 0.3rem;
    border-bottom: 1px solid {BORDER} !important;
}}

/* ── サイドバー ── */
[data-testid="stSidebar"] {{
    background-color: {BG2} !important;
    border-right: 1px solid {BORDER} !important;
}}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] div,
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] small,
[data-testid="stSidebar"] li {{
    color: {TEXT} !important;
}}
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stTextArea textarea {{
    background-color: {BG3} !important;
    color: {TEXT} !important;
    border-color: {BORDER} !important;
}}
[data-testid="stSidebar"] [data-baseweb="select"] > div {{
    background-color: {BG3} !important;
    border-color: {BORDER} !important;
    color: {TEXT} !important;
}}
[data-testid="stSidebar"] [data-testid="stExpander"] {{
    background-color: {BG3} !important;
    border-color: {BORDER} !important;
}}
[data-testid="stSidebar"] .streamlit-expanderHeader {{
    background-color: {BG3} !important;
    color: {TEXT} !important;
}}
[data-testid="stSidebar"] code {{
    background-color: {BG} !important;
    color: {ACCENT} !important;
}}
[data-testid="stSidebar"] hr {{
    border-color: {BORDER} !important;
}}
"""

st.markdown(f"<style>{theme_css}</style>", unsafe_allow_html=True)

# ============================================================
# 4. PC状況チェック関数
# ============================================================
def get_pc_status():
    """PCのVRAM・RAM・CPU状況を取得してdict返す"""
    status = {
        "vram_used_gb":   0.0,
        "vram_total_gb":  16.0,
        "ram_used_gb":    0.0,
        "ram_total_gb":   64.0,
        "cpu_percent":    0.0,
        "ollama_running": False,
        "loaded_models":  [],
    }
    try:
        import psutil
        vm = psutil.virtual_memory()
        status["ram_used_gb"]  = round(vm.used / 1024**3, 1)
        status["ram_total_gb"] = round(vm.total / 1024**3, 1)
        status["cpu_percent"]  = psutil.cpu_percent(interval=0.3)
    except ImportError:
        pass

    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            line = result.stdout.strip().split("\n")[0]
            used, total = line.split(", ")
            status["vram_used_gb"]  = round(int(used.strip()) / 1024, 1)
            status["vram_total_gb"] = round(int(total.strip()) / 1024, 1)
    except Exception:
        pass

    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        if r.status_code == 200:
            status["ollama_running"] = True
            models = r.json().get("models", [])
            status["loaded_models"] = [m.get("name", "") for m in models]
    except Exception:
        pass

    return status


def recommend_model(status):
    """PC状況から最適モデルを提案"""
    vram_free = status["vram_total_gb"] - status["vram_used_gb"]
    ram_used  = status["ram_used_gb"]
    ram_total = status["ram_total_gb"]

    recs = []

    if vram_free >= 14:
        recs.append(("🟢 最高品質", "qwen2.5-coder:32b", "VRAM余裕あり。32bフル稼働OK"))
        recs.append(("🟢 最高品質", "deepseek-r1:32b",   "デバッグ・思考タスクに最適"))
    elif vram_free >= 8:
        recs.append(("🟡 バランス",  "qwen2.5-coder:14b", "VRAMやや少ない。14bが安定"))
        recs.append(("🟡 バランス",  "qwen2.5-coder:7b",  "軽量で高速"))
    else:
        recs.append(("🔴 軽量推奨",  "qwen2.5-coder:7b",  "VRAMが少ない。7bで安定動作"))
        recs.append(("🔴 軽量推奨",  "phi3.5:latest",     "最軽量。応答速度優先"))

    # 会話が重い理由
    reason = []
    if vram_free < 8:
        reason.append("⚠️ VRAMが少ない → 32bモデルがRAMにオフロード中（遅い）")
    if ram_used > ram_total * 0.8:
        reason.append("⚠️ RAM使用率が高い → モデルのロードが遅くなっている")
    if not status["ollama_running"]:
        reason.append("❌ Ollamaが起動していない可能性")

    return recs, reason


# ============================================================
# 5. VRStudio接続チェック
# ============================================================
def check_vrstudio(url):
    try:
        r = requests.get(url, timeout=2)
        return r.status_code < 500
    except requests.exceptions.ConnectionError:
        return False
    except Exception:
        return False

def check_voicevox(url):
    try:
        r = requests.get(f"{url}/version", timeout=2)
        return r.status_code == 200, r.text.strip()
    except Exception:
        return False, ""

def check_sd(url):
    try:
        r = requests.get(f"{url}/sdapi/v1/samplers", timeout=2)
        return r.status_code == 200
    except Exception:
        return False

# ============================================================
# 6. サイドバー
# ============================================================
st.sidebar.title("🛰 Blackwell 司令部")
st.sidebar.info(
    f"**稼働中** ✅\n\n"
    f"🤖 Blackwell主軸: {st.session_state.project_anchor[:35]}…\n\n"
    f"🎮 ゲーム主軸: {st.session_state.game_anchor[:35] + '…' if st.session_state.game_anchor else '（未設定）'}"
)

with st.sidebar.expander("🛠 実行・保存設定", expanded=True):
    app_mode = st.selectbox("稼働モード", ["Code特化", "画像生成", "音楽生成", "動画生成", "Game作成"])
    st.session_state.auto_write = st.checkbox(
        "自動保存 + Git Commit（推奨: ON）", value=st.session_state.auto_write
    )
    st.session_state.max_cycles = st.slider(
        "最大修正サイクル数", 1, 5, st.session_state.max_cycles
    )
    st.divider()
    st.caption("📂 保存先ワークスペース")
    col_p1, col_p2 = st.columns([2, 1])
    with col_p1:
        manual_path = st.text_input(
            "パス", value=st.session_state.target_path, label_visibility="collapsed"
        )
        if manual_path != st.session_state.target_path:
            if os.path.isdir(manual_path):
                st.session_state.target_path = os.path.abspath(manual_path)
            else:
                st.error("無効なパス")
    with col_p2:
        if st.button("📁", use_container_width=True):
            if HAS_TK:
                root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
                sel = filedialog.askdirectory(initialdir=st.session_state.target_path)
                root.destroy()
                if sel:
                    st.session_state.target_path = os.path.abspath(sel)
                    st.rerun()
    save_path = st.session_state.target_path
    st.code(save_path, wrap_lines=True)

# ── ⑬ エンジン・ジャンル設定 ─────────────────────────────
with st.sidebar.expander("🎮 エンジン・ジャンル設定", expanded=False):
    st.caption("ゲーム開発時のターゲットエンジンとジャンルを設定します。\n「自動判定」にするとプロジェクトフォルダから自動で検出します。")

    _engine_options = {
        "🔍 自動判定":          "auto",
        "🟣 Godot 4（推奨）":  "godot",
        "🐍 Pygame（2D即動作）":"pygame",
        "🎯 Unreal Engine":     "unreal",
        "🔵 Unity":             "unity",
        "🌐 Three.js（Web3D）": "threejs",
    }
    _selected_engine_label = st.selectbox(
        "ターゲットエンジン",
        list(_engine_options.keys()),
        index=0,
        key="engine_selector",
    )
    selected_engine = _engine_options[_selected_engine_label]
    if selected_engine != "auto":
        st.session_state["target_engine"] = selected_engine
        # engine.py の SPEED_MODE に反映
        try:
            import engine as _eng
            # engine_adapter でエンジンを固定（自動判定をオーバーライド）
            st.session_state["engine_override"] = selected_engine
        except Exception:
            pass
    else:
        st.session_state.pop("engine_override", None)
        st.caption("💡 保存先フォルダのファイルからエンジンを自動検出します")

    st.divider()

    _genre_options = {
        "🔍 自動判定":                    "auto",
        "⚔️ 2Dアクション・プラットフォーマー": "2daction",
        "🎲 ローグライク":                 "roguelike",
        "🏙️ シミュレーション（経営・都市）": "simulation",
        "🗼 タワーディフェンス":            "towerdefense",
        "🗡️ 3DアクションRPG":             "3daction",
    }
    _selected_genre_label = st.selectbox(
        "ゲームジャンル",
        list(_genre_options.keys()),
        index=0,
        key="genre_selector",
    )
    selected_genre = _genre_options[_selected_genre_label]
    if selected_genre != "auto":
        st.session_state["genre_override"] = selected_genre
    else:
        st.session_state.pop("genre_override", None)
        st.caption("💡 指示文からジャンルを自動判定します")

    # Godot選択時の追加オプション
    if selected_engine == "godot":
        st.divider()
        godot_ver = st.radio("Godotバージョン", ["4.x（推奨）", "3.x"], horizontal=True)
        st.session_state["godot_version"] = "4" if "4" in godot_ver else "3"
        st.caption("✅ .tscn シーンファイルをAIが直接生成できます")

    # UE選択時の注意
    if selected_engine == "unreal":
        st.warning(
            "⚠️ UE対応について\n"
            "C++コード(.h/.cpp)の生成は可能です。\n"
            "Blueprintノード(.uasset)はバイナリ形式のため\n"
            "AIによる直接操作はできません。"
        )

    # ジャンル情報表示
    if selected_genre != "auto":
        try:
            from genre_templates import get_genre_architecture
            arch = get_genre_architecture(selected_genre, selected_engine if selected_engine != "auto" else "godot")
            with st.expander(f"📋 {arch['name']} システム構成", expanded=False):
                for sys in arch["core_systems"]:
                    st.caption(f"• {sys}")
        except Exception:
            pass

    # 速度モード
    st.divider()
    st.caption("⚡ 生成速度モード")
    speed_mode = st.radio(
        "速度モード",
        ["normal（標準）", "fast（高速・検索スキップ）", "quality（最高品質）"],
        index=0,
        horizontal=False,
        label_visibility="collapsed",
        key="speed_mode_radio",
    )
    try:
        import engine as _eng
        _eng.SPEED_MODE = speed_mode.split("（")[0]
    except Exception:
        pass
    if "fast" in speed_mode:
        st.caption("⚡ ネット検索・Branching をスキップ → 大幅に速くなります")


    st.caption("各エージェントが使用するモデルを変更できます。\n※ チャットモデルは「会話」タブで変更してください。")
    model_options = [
        "qwen3-next:80b", "qwen2.5-coder:32b", "qwen2.5-coder:14b",
        "qwen2.5-coder:14b-instruct", "qwen2.5-coder:7b", "deepseek-r1:32b",
        "llama3.1:70b", "llama3.1:8b", "llama3:latest", "phi3.5:latest",
        "qwen2.5:14b-instruct",
    ]
    # chat は会話タブ専用のため除外
    role_info = {
        "planner":   ("Planner",   "戦略立案・タスク分解"),
        "coder":     ("Coder",     "実装・コード生成"),
        "refiner":   ("Refiner",   "自己修復・エラー修正"),
        "optimizer": ("Optimizer", "最適化・リファクタリング"),
    }
    for key, (label, desc) in role_info.items():
        ss_key = f"model_{key}"
        cur = st.session_state.get(ss_key, model_options[0])
        st.markdown(f"**{label}** — {desc}")
        st.info(f"現在: `{cur}`")
        idx = model_options.index(cur) if cur in model_options else 0
        sel = st.selectbox(
            label, model_options, index=idx,
            key=f"model_sel_{key}", label_visibility="collapsed"
        )
        if sel != cur:
            st.session_state[ss_key] = sel
            MODELS[key] = sel
            st.rerun()   # ← 即時反映のため再実行
        st.divider()

with st.sidebar.expander("🌐 インターネット / GitHub設定", expanded=False):
    st.session_state.use_internet = st.checkbox(
        "🌐 ネット検索を使用（コード生成・会話に自動活用）",
        value=st.session_state.use_internet
    )
    st.divider()
    st.caption("🔑 GitHub Personal Access Token")
    st.caption("作り方: GitHub → Settings → Developer settings → Tokens (classic) → Generate")
    new_token = st.text_input(
        "Token", value=st.session_state.github_token,
        type="password", label_visibility="collapsed",
        placeholder="ghp_xxxxxxxxxxxxxxxxxxxx",
        key="sidebar_github_token"
    )
    if new_token != st.session_state.github_token:
        st.session_state.github_token = new_token

    st.caption("🔗 GitHubリポジトリURL")
    new_repo = st.text_input(
        "Repo URL", value=st.session_state.github_repo_url,
        label_visibility="collapsed",
        placeholder="https://github.com/username/repo.git",
        key="sidebar_github_repo"
    )
    if new_repo != st.session_state.github_repo_url:
        st.session_state.github_repo_url = new_repo

    col_gh1, col_gh2 = st.sidebar.columns(2)
    with col_gh1:
        if st.button("🔗 リモート設定", use_container_width=True, key="sb_remote_set"):
            if st.session_state.github_repo_url:
                try:
                    from gitops import setup_github_remote
                    r = setup_github_remote(
                        st.session_state.github_repo_url,
                        token=st.session_state.github_token,
                        path=st.session_state.target_path
                    )
                    st.sidebar.success(r["message"]) if r["success"] else st.sidebar.error(r["message"])
                except Exception as e:
                    st.sidebar.error(str(e))
            else:
                st.sidebar.warning("URLを入力してください")
    with col_gh2:
        if st.button("📤 Push", use_container_width=True, key="sb_push"):
            if st.session_state.github_repo_url:
                try:
                    from gitops import push_to_github
                    commit_all("Blackwell Auto Push", path=st.session_state.target_path)
                    r = push_to_github(
                        branch="main",
                        token=st.session_state.github_token,
                        repo_url=st.session_state.github_repo_url,
                        path=st.session_state.target_path
                    )
                    st.sidebar.success(r["message"]) if r["success"] else st.sidebar.error(r["message"])
                except Exception as e:
                    st.sidebar.error(str(e))
            else:
                st.sidebar.warning("URLを入力してください")


    # ── Blackwellの主軸（AIの動き方・開発方針）──────────
    st.sidebar.markdown("**🤖 Blackwellの主軸**")
    st.sidebar.caption("AIの動き方・優先事項・開発方針")
    _bw_anchor_edit = st.sidebar.text_area(
        "Blackwell主軸",
        value=st.session_state.project_anchor,
        height=110,
        label_visibility="collapsed",
        key="sidebar_bw_anchor",
        placeholder="例: 常に最新ライブラリを使い堅牢な設計を優先する"
    )
    if st.sidebar.button("✅ Blackwell主軸を確定", use_container_width=True, key="apply_bw_anchor"):
        st.session_state.project_anchor = _bw_anchor_edit
        st.sidebar.success("✅ Blackwell主軸を更新しました")
        st.rerun()

    st.sidebar.divider()

    # ── ゲームの主軸（世界観・面白さの軸）──────────────
    st.sidebar.markdown("**🎮 ゲームの主軸**")
    st.sidebar.caption("ゲームの世界観・ジャンル・面白さの軸")
    _game_anchor_edit = st.sidebar.text_area(
        "ゲーム主軸",
        value=st.session_state.game_anchor,
        height=110,
        label_visibility="collapsed",
        key="sidebar_game_anchor",
        placeholder="例: ローグライクRPG。一歩の重みを感じる重厚な操作感。死から学ぶ成長設計。"
    )
    if st.sidebar.button("✅ ゲーム主軸を確定", use_container_width=True, key="apply_game_anchor"):
        st.session_state.game_anchor = _game_anchor_edit
        st.sidebar.success("✅ ゲーム主軸を更新しました")
        st.rerun()

st.sidebar.subheader("🧬 外部ナレッジ注入")
uploaded_files = st.sidebar.file_uploader("技術書・設計書 (PDF/MD/JSON/PY)", accept_multiple_files=True)
if st.sidebar.button("📥 学習開始", use_container_width=True):
    if uploaded_files:
        for up in uploaded_files:
            try:
                content = up.getvalue().decode("utf-8", errors="ignore")
                analyze_and_absorb(up.name, content)
                st.sidebar.write(f"✅ {up.name}")
            except Exception as e:
                st.sidebar.write(f"❌ {up.name}: {e}")
        st.sidebar.success("🎓 学習完了")
    else:
        st.sidebar.warning("ファイルを選択してください")

st.sidebar.divider()
st.sidebar.subheader("📦 パッケージ化")
pkg_target = st.sidebar.text_input("エントリーファイル", value="main.py")
if st.sidebar.button("🚀 PyInstallerでビルド", use_container_width=True):
    target_file = os.path.join(save_path, pkg_target)
    if os.path.exists(target_file):
        with st.sidebar.spinner("ビルド中..."):
            try:
                r = subprocess.run([sys.executable, "-m", "PyInstaller", "--onefile", target_file],
                                   capture_output=True, text=True, cwd=save_path)
                st.sidebar.success("✅ ビルド成功！") if r.returncode == 0 else st.sidebar.error(r.stderr[:200])
            except Exception as e:
                st.sidebar.error(str(e))
    else:
        st.sidebar.error(f"見つかりません: {target_file}")

# ダーク/ホワイトモード切替（サイドバー最下部）
st.sidebar.divider()
st.sidebar.subheader("🎨 表示モード")
st.sidebar.write(f"現在: **{'🌙 ダークモード' if is_dark else '☀️ ホワイトモード'}**")
col_dm1, col_dm2 = st.sidebar.columns(2)
with col_dm1:
    if st.button("☀️ ホワイト", use_container_width=True, key="btn_white",
                 type="primary" if not is_dark else "secondary"):
        st.session_state.dark_mode = False; st.rerun()
with col_dm2:
    if st.button("🌙 ダーク", use_container_width=True, key="btn_dark",
                 type="primary" if is_dark else "secondary"):
        st.session_state.dark_mode = True; st.rerun()

# ============================================================
# 7. タイトル & タブ
# ============================================================
_title_css = f"""
<style>
/* 全体を少し下にずらす */
.block-container {{ padding-top: 1.8rem !important; }}

.bw-hdr {{
    display:flex; align-items:center; justify-content:space-between;
    flex-wrap:wrap; gap:6px;
    margin-bottom:8px; padding-bottom:8px;
    border-bottom:2px solid {ACCENT}55;
}}
/* ロゴ：絵文字と文字を別spanで管理しletter-spacingの干渉を回避 */
.bw-logo-icon {{
    font-size:1.3rem; margin-right:6px;
    color:{ACCENT} !important;
}}
.bw-logo-text {{
    font-family:'JetBrains Mono',monospace !important;
    font-size:1.15rem; font-weight:700; letter-spacing:.12em;
    color:{ACCENT} !important;
}}
.bw-bs {{ display:flex; flex-wrap:wrap; gap:4px; align-items:center; }}
.bw-b  {{
    background:{BG3}; border:1px solid {BORDER}; border-radius:4px;
    padding:2px 8px;
    font-size:.6rem; font-family:'JetBrains Mono',monospace;
    color:{TEXT} !important; white-space:nowrap;
}}
.bw-bhi {{ border-color:{ACCENT}99 !important; color:{ACCENT} !important; }}
</style>
"""
st.markdown(_title_css, unsafe_allow_html=True)

_coder_short = st.session_state.model_coder.split(":")[0]
_chat_short  = st.session_state.model_chat.split(":")[0]
_save_badge  = "ON" if st.session_state.auto_write else "OFF"

st.markdown(
    f'<div class="bw-hdr">'
    f'  <div style="display:flex;align-items:center">'
    f'    <span class="bw-logo-icon">&#9889;</span>'
    f'    <span class="bw-logo-text">BLACKWELL DEV-OS</span>'
    f'  </div>'
    f'  <div class="bw-bs">'
    f'    <span class="bw-b bw-bhi">MODE:{app_mode}</span>'
    f'    <span class="bw-b">CODER:{_coder_short}</span>'
    f'    <span class="bw-b">CYC:{st.session_state.max_cycles}</span>'
    f'    <span class="bw-b">SAVE:{_save_badge}</span>'
    f'    <span class="bw-b bw-bhi">CHAT:{_chat_short}</span>'
    f'    <span class="bw-b bw-bhi">P2:ON</span>'
    f'  </div>'
    f'</div>',
    unsafe_allow_html=True
)

(tab_sogo, tab_main, tab_knowledge, tab_improvement,
 tab_memory_tab, tab_aivtuber,
 tab_monitor_tab, tab_preview, tab_log, tab_gamedev) = st.tabs([
    "🚀 総合",
    "💬 戦略会議室",
    "📚 知識",
    "💡 改善",
    "🧠 記憶",
    "🎭 AIVtuber",
    "🔍 監視",
    "🖼️ プレビュー",
    "📜 ログ",
    "🎮 ゲーム開発",
])

# ============================================================
# TAB 0: 🚀 総合（会話 + 検索 + 改善 + 出力）
# ============================================================
with tab_sogo:
    col_sl, col_sr = st.columns([5, 4], gap="medium")

    # ── 左: 会話（完全版）──────────────────────────────────
    with col_sl:
        st.markdown(f'<div class="bw-panel-title">🗣️ AI会話 — {st.session_state.model_chat}</div>', unsafe_allow_html=True)

        # ── 会話設定（モデル・性格・PC状況をすべてここに集約）──
        with st.expander("⚙️ 会話設定 / 性格 / PC状況", expanded=False):

            # ① モデル選択 + ネット検索 + 履歴クリア
            st.markdown("**🤖 会話モデル**")
            chat_opts_s = [
                "qwen3-next:80b","qwen2.5-coder:32b","qwen2.5-coder:14b",
                "qwen2.5-coder:7b","deepseek-r1:32b","llama3.1:70b",
                "llama3.1:8b","phi3.5:latest",
            ]
            cur_s = st.session_state.model_chat
            ci_s  = chat_opts_s.index(cur_s) if cur_s in chat_opts_s else 0
            new_s = st.selectbox("会話モデル選択", chat_opts_s, index=ci_s,
                                 key="sogo_chat_model", label_visibility="collapsed")
            if new_s != cur_s:
                st.session_state.model_chat = new_s
                MODELS["chat"] = new_s
                st.rerun()

            c_net, c_clr = st.columns(2)
            with c_net:
                st.session_state.use_internet = st.checkbox(
                    "🌐 ネット検索", value=st.session_state.use_internet, key="sogo_net"
                )
            with c_clr:
                if st.button("🗑 履歴クリア", use_container_width=True, key="sogo_clear"):
                    st.session_state.chat_messages = []; st.rerun()

            st.divider()

            # ② 性格・口調設定
            st.markdown("**🎭 AIの性格・口調設定**")
            new_persona_s = st.text_area(
                "性格", value=st.session_state.persona, height=80,
                placeholder="例: あなたは無口で的確な天才エンジニアです。",
                label_visibility="collapsed", key="sogo_persona_text"
            )
            col_pa1, col_pa2 = st.columns([1, 1])
            with col_pa1:
                if st.button("✅ 性格を適用", use_container_width=True, key="sogo_persona_apply"):
                    st.session_state.persona = new_persona_s
                    st.success("性格を更新しました")
            with col_pa2:
                preset_s = st.selectbox("プリセット", [
                    "カスタム", "天才エンジニア", "優しい先生",
                    "厳格なレビュアー", "熱血コーチ",
                ], label_visibility="collapsed", key="sogo_preset")
                preset_map_s = {
                    "天才エンジニア":   "あなたは無口で天才的なエンジニアです。余計なことは言わず、コードと最小限の説明だけで答えます。",
                    "優しい先生":     "あなたは優しくて丁寧な先生です。初心者にも分かりやすくステップごとに説明してください。",
                    "厳格なレビュアー": "あなたは厳格なコードレビュアーです。問題点を指摘し必ず改善案をコードブロックで示してください。",
                    "熱血コーチ":     "あなたは熱血な開発コーチです！全力で応援しエネルギッシュに答えてください！",
                }
                if preset_s in preset_map_s:
                    if st.button("プリセット適用", use_container_width=True, key="sogo_preset_apply"):
                        st.session_state.persona = preset_map_s[preset_s]; st.rerun()

            st.divider()

            # ③ PC状況 & おすすめモデル
            st.markdown("**🖥️ 現在のPC状況 & おすすめモデル**")
            if st.button("🔄 PC状況を取得", use_container_width=True, key="sogo_pc_refresh"):
                st.rerun()
            status = get_pc_status()
            recs_s, reasons_s = recommend_model(status)

            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            vram_pct_s = (status["vram_used_gb"] / max(status["vram_total_gb"], 1)) * 100
            ram_pct_s  = (status["ram_used_gb"]  / max(status["ram_total_gb"],  1)) * 100
            col_s1.metric("VRAM", f"{status['vram_used_gb']}/{status['vram_total_gb']}GB",
                          delta=f"{100 - vram_pct_s:.0f}%空き")
            col_s2.metric("RAM",  f"{status['ram_used_gb']}/{status['ram_total_gb']}GB",
                          delta=f"{100 - ram_pct_s:.0f}%空き")
            col_s3.metric("CPU", f"{status['cpu_percent']}%")
            col_s4.metric("Ollama", "起動中" if status["ollama_running"] else "停止")

            if reasons_s:
                for r_s in reasons_s:
                    st.warning(r_s)
            else:
                st.success("✅ PC良好。高性能モデルで動作できます。")

            st.markdown("**おすすめモデル:**")
            for badge_s, model_s, reason_s in recs_s:
                c_b, c_m, c_apply = st.columns([1, 2, 1])
                c_b.markdown(f"**{badge_s}**")
                c_m.caption(f"`{model_s}`")
                if c_apply.button("適用", key=f"sogo_apply_{model_s}"):
                    st.session_state.model_chat = model_s
                    MODELS["chat"] = model_s
                    st.rerun()

        # ── チャットログ ──
        chat_box = st.container(height=380)
        with chat_box:
            if not st.session_state.chat_messages:
                st.info("👋 コード質問・雑談・検索など何でもどうぞ。")
            for msg in st.session_state.chat_messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        if sogo_in := st.chat_input("話しかけてください", key="sogo_chat_input"):
            st.session_state.chat_messages.append({"role": "user", "content": sogo_in})
            with st.spinner("考え中..."):
                try:
                    from engine import chat_with_persona as _cwp
                    reply = _cwp(
                        message=sogo_in,
                        persona=st.session_state.persona,
                        history=st.session_state.chat_messages[-10:],
                        anchor=get_combined_anchor(),
                        use_internet=st.session_state.use_internet,
                    )
                except TypeError:
                    reply = chat_with_persona(
                        message=sogo_in,
                        persona=st.session_state.persona,
                        history=st.session_state.chat_messages[-10:],
                        anchor=get_combined_anchor(),
                    )
            st.session_state.chat_messages.append({"role": "assistant", "content": reply})
            st.rerun()

    # ── 右: 検索 / 改善 / 出力 ──────────────────────────
    with col_sr:
        right_s = st.radio("右パネル",
            ["🌐 ネット検索", "💡 改善提案", "📤 生成出力"],
            horizontal=True, label_visibility="collapsed", key="sogo_right")

        if right_s == "🌐 ネット検索":
            st.markdown('<div class="bw-panel-title">🌐 インターネット検索</div>', unsafe_allow_html=True)
            sq = st.text_input("キーワード",
                placeholder="今何時 / requests最新版 / Godot OSS / ChromaDBとは",
                key="sogo_sq")
            sm = st.selectbox("エンジン",
                ["🤖 自動", "🌐 DuckDuckGo", "📖 Wikipedia", "📦 PyPI", "🐙 GitHub"],
                key="sogo_sm")
            if st.button("🔎 検索", use_container_width=True, key="sogo_search"):
                if sq.strip():
                    with st.spinner("検索中..."):
                        try:
                            from internet import smart_search, search_duckduckgo, search_wikipedia, search_pypi, search_github
                            if "自動" in sm:
                                r = smart_search(sq, github_token=st.session_state.github_token)
                                st.info(f"エンジン: {r['source']}")
                                st.markdown(r["summary"])
                            elif "Wikipedia" in sm:
                                r = search_wikipedia(sq)
                                if r["success"]:
                                    st.subheader(r["title"])
                                    st.write(r["summary"][:500])
                                    st.markdown(f"[🔗 記事を読む]({r['url']})")
                                else:
                                    st.error(r["error"])
                            elif "PyPI" in sm:
                                r = search_pypi(sq.split()[0])
                                if r["success"]:
                                    st.metric("最新版", f"v{r['version']}")
                                    st.write(r["summary"])
                                    st.code(f"pip install {r['name']}=={r['version']}")
                                else:
                                    st.error(r["error"])
                            elif "GitHub" in sm:
                                r = search_github(sq, token=st.session_state.github_token)
                                if r["success"]:
                                    for item in r["items"][:4]:
                                        st.markdown(f"⭐{item['stars']:,} **[{item['name']}]({item['url']})**")
                                        st.caption(item["description"])
                                else:
                                    st.error(r["error"])
                            else:
                                r = search_duckduckgo(sq)
                                if r["success"]:
                                    if r["abstract"]:
                                        st.success(r["abstract"][:300])
                                    for res in r["results"][:4]:
                                        st.markdown(f"• {res['title']}")
                                        if res["url"]: st.caption(res["url"])
                                else:
                                    st.error(r["error"])
                        except ImportError:
                            st.warning("internet.py が見つかりません。同じフォルダに配置してください。")
                else:
                    st.warning("キーワードを入力してください")

            st.divider()
            try:
                from internet import get_current_datetime
                dt = get_current_datetime()
                st.caption(f"🕐 現在: **{dt['datetime_str']}**")
            except ImportError:
                from datetime import datetime
                st.caption(f"🕐 現在: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        elif right_s == "💡 改善提案":
            st.markdown('<div class="bw-panel-title">💡 改善提案</div>', unsafe_allow_html=True)
            if st.session_state.last_result:
                if st.button("🔄 改善提案を生成", use_container_width=True, key="sogo_suggest"):
                    with st.spinner("生成中..."):
                        sug = chat_with_persona(
                            message=f"以下に対して改善提案を3〜5点:\n\n{st.session_state.last_result[:3000]}",
                            persona="厳格なアーキテクト。箇条書きで的確に。",
                            anchor=get_combined_anchor(),
                        )
                        st.session_state.last_suggestion = sug
                if st.session_state.last_suggestion:
                    st.markdown(st.session_state.last_suggestion)
                    if st.button("⚡ この改善を実行", use_container_width=True,
                                 type="primary", key="sogo_fix"):
                        with st.spinner("実行中..."):
                            fix = autonomous_dev(
                                goal=f"【改善提案を反映】\n{st.session_state.last_suggestion}",
                                auto_write=st.session_state.auto_write,
                                save_path=st.session_state.target_path,
                                anchor=get_combined_anchor(), max_cycles=2
                            )
                        st.session_state.messages.append({"role": "assistant", "content": fix})
                        st.rerun()
            else:
                st.info("戦略会議室でコードを生成すると、ここで改善提案を受け取れます。")

        else:
            st.markdown('<div class="bw-panel-title">📤 最新の生成出力</div>', unsafe_allow_html=True)
            if st.session_state.last_result:
                st.markdown(st.session_state.last_result)
            else:
                st.info("戦略会議室でコードを生成すると、ここに表示されます。")

# ============================================================
# ============================================================
# TAB 1: 💬 戦略会議室（新レイアウト v2.0）
# ─────────────────────────────────────────────
#  左列: ① 主軸表示  ② 改善提案チェックリスト  ③ 品質チェック
#  中央: 会話（メイン）
#  右列: ① 生成ログ  ② バグ/クラッシュ確認  ③ 改善提案生成
# ============================================================
with tab_main:
    col_left, col_center, col_right = st.columns([3, 5, 4], gap="small")

    # ═══════════════════════════════════════════════
    # 左列
    # ═══════════════════════════════════════════════
    with col_left:

        # ── ① 主軸表示・編集 ────────────────────────
        st.markdown("#### ⚓ 主軸")

        # Blackwell主軸（表示のみ・編集はサイドバーで）
        with st.container(border=True):
            st.caption("🤖 Blackwellの主軸（司令部で編集）")
            st.info(st.session_state.project_anchor[:120] +
                    ("…" if len(st.session_state.project_anchor) > 120 else ""))

        # ゲーム主軸（ここで編集可能）
        with st.container(border=True):
            st.caption("🎮 ゲームの主軸（AIがゲームを作る際の道標）")
            _ga_edit = st.text_area(
                "ゲーム主軸",
                value=st.session_state.game_anchor,
                height=100,
                label_visibility="collapsed",
                key="main_game_anchor_edit",
                placeholder="例: ローグライクRPG。一歩の重みを感じる重厚な操作感。死から学ぶ成長設計。"
            )
            if st.button("✅ ゲーム主軸を確定", use_container_width=True, key="apply_game_anchor_main"):
                st.session_state.game_anchor = _ga_edit
                st.success("✅ ゲーム主軸を更新しました")
                st.rerun()

        st.divider()

        # ── ② 改善提案チェックリスト ──────────────────
        st.markdown("#### 💡 AIからの改善提案")
        st.caption("チェックして「導入」ボタンで即実行")

        # 新しい提案を生成するボタン
        if st.button("🔄 提案を更新", use_container_width=True, key="gen_suggestions_main"):
            if st.session_state.last_result:
                with st.spinner("提案を生成中..."):
                    try:
                        raw = chat_with_persona(
                            message=(
                                "以下のコードに対して、導入すべき改善案を正確に5個、"
                                "番号付きで1行ずつ出力してください。\n"
                                "形式: 1. [提案内容（30文字以内）]\n\n"
                                f"{st.session_state.last_result[:2000]}"
                            ),
                            persona="厳格なアーキテクト。箇条書きのみ。説明不要。",
                            anchor=get_combined_anchor()
                        )
                        import re as _re
                        items = _re.findall(r"\d+\.\s*(.+)", raw)
                        if items:
                            st.session_state.pending_suggestions = [
                                {"text": t.strip(), "checked": False}
                                for t in items[:5]
                            ]
                            st.rerun()
                    except Exception as e:
                        st.error(f"提案生成失敗: {e}")
            else:
                st.warning("先にコードを生成してください")

        # チェックボックス表示
        if st.session_state.pending_suggestions:
            updated = False
            for i, item in enumerate(st.session_state.pending_suggestions):
                checked = st.checkbox(
                    item["text"], value=item["checked"],
                    key=f"suggest_chk_{i}"
                )
                if checked != item["checked"]:
                    st.session_state.pending_suggestions[i]["checked"] = checked
                    updated = True

            # 選択した提案を一括導入
            selected = [s for s in st.session_state.pending_suggestions if s["checked"]]
            if selected:
                if st.button(
                    f"⚡ 選択した{len(selected)}件を導入",
                    use_container_width=True,
                    type="primary",
                    key="adopt_selected"
                ):
                    adopt_goal = "【選択した改善提案を導入】\n" + "\n".join(
                        f"- {s['text']}" for s in selected
                    )
                    with st.spinner("導入中..."):
                        fix = autonomous_dev(
                            goal=adopt_goal,
                            auto_write=st.session_state.auto_write,
                            save_path=st.session_state.target_path,
                            anchor=get_combined_anchor(),
                            max_cycles=2
                        )
                    # 導入済みに記録
                    st.session_state.adopted_suggestions.extend(
                        [s["text"] for s in selected]
                    )
                    # 導入済みを除去
                    st.session_state.pending_suggestions = [
                        s for s in st.session_state.pending_suggestions
                        if not s["checked"]
                    ]
                    st.session_state.messages.append({"role": "assistant", "content": fix})
                    st.session_state.last_result = fix
                    st.rerun()
        else:
            st.info("「提案を更新」でAIが改善案を出します")

        # 導入済み記録
        if st.session_state.adopted_suggestions:
            with st.expander(f"✅ 導入済み ({len(st.session_state.adopted_suggestions)}件)", expanded=False):
                for s in st.session_state.adopted_suggestions[-5:]:
                    st.caption(f"✅ {s}")

        st.divider()

        # ── ③ 品質チェック ───────────────────────────
        st.markdown("#### 🎯 最終品質チェック")
        st.caption("AIがゲームとして面白いか判断します")
        if st.button("🎮 品質チェック実行", use_container_width=True, key="quality_check_main"):
            if st.session_state.last_result:
                with st.spinner("品質を評価中..."):
                    try:
                        qc = chat_with_persona(
                            message=(
                                "以下のゲームコードを評価してください。\n"
                                "【主軸】" + get_combined_anchor() + "\n\n"
                                "【コード】\n" + st.session_state.last_result[:2000] + "\n\n"
                                "以下の形式で回答:\n"
                                "面白さ: ★★★☆☆（5段階）\n"
                                "主軸との一致: ★★★★☆\n"
                                "バグリスク: 低/中/高\n"
                                "一言評価: [30文字]\n"
                                "改善余地: あり/なし"
                            ),
                            persona="厳格なゲームディレクター。簡潔に評価のみ出力。",
                            anchor=get_combined_anchor()
                        )
                        st.session_state.quality_check_result = qc
                        # 改善余地ありなら自動で提案を更新フラグ
                        if "改善余地: あり" in qc or "あり" in qc:
                            st.session_state["quality_needs_improve"] = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"品質チェック失敗: {e}")
            else:
                st.warning("先にコードを生成してください")

        if st.session_state.quality_check_result:
            qr = st.session_state.quality_check_result
            # 色分け表示
            if "高" in qr and "バグリスク" in qr:
                st.error(qr)
            elif "改善余地: あり" in qr:
                st.warning(qr)
                st.caption("→ 左の「提案を更新」で改善案を出して再実行")
            else:
                st.success(qr)

    # ═══════════════════════════════════════════════
    # 中央列: 会話メイン
    # ═══════════════════════════════════════════════
    with col_center:
        st.markdown(f'<div class="bw-panel-title">🗣️ 開発チャット — {st.session_state.model_coder}</div>',
                    unsafe_allow_html=True)

        # 会話履歴
        chat_container = st.container(height=480)
        with chat_container:
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        # 入力
        if prompt := st.chat_input("指示を入力（例: プレイヤーのジャンプを実装して）"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            game_anchor_part = (
                f"\n\n【🎮 ゲームの主軸】\n{st.session_state.game_anchor}"
                if st.session_state.game_anchor else ""
            )
            full_prompt = (
                f"【🤖 Blackwell主軸】\n{st.session_state.project_anchor}"
                f"{game_anchor_part}\n\n"
                f"【稼働モード】\n{app_mode}\n\n"
                f"【指示】\n{prompt}"
            )

            # ── ストリーミング生成 vs 通常生成 ────────────────
            # コード生成タスク（ファイルへの書き出しが必要）→ autonomous_dev（通常）
            # 質問・相談・軽い指示 → ストリーミングで即レスポンス
            is_code_task = any(k in prompt.lower() for k in [
                "実装","作って","書いて","修正","追加","直して",
                "implement","create","fix","add","write","generate",
                ".gd",".py",".cs","class","func","def",
            ])

            if is_code_task:
                # コード生成: autonomous_dev（ファイル保存が必要なのでブロッキングのまま）
                # ただし進捗をリアルタイム表示するプログレスバーを追加
                prog_placeholder = st.empty()
                log_placeholder  = st.empty()

                prog_placeholder.info("🔄 計画中...")
                result = autonomous_dev(
                    goal=full_prompt,
                    auto_write=st.session_state.auto_write,
                    save_path=st.session_state.target_path,
                    anchor=get_combined_anchor(),
                    history=st.session_state.messages[-10:],
                    max_cycles=st.session_state.max_cycles
                )
                prog_placeholder.empty()
                log_placeholder.empty()

                st.session_state.last_result  = result
                st.session_state.last_log     = get_execution_log()
                st.session_state.thinking_log = get_execution_log()
                import re as _re2
                built_files = _re2.findall(r"\[OK\]\s+([\w./\\-]+\.\w+)", result)
                if built_files:
                    st.session_state.build_log.extend(built_files)
                    st.session_state.build_log = st.session_state.build_log[-30:]
                st.session_state.messages.append({"role": "assistant", "content": result})

            else:
                # 質問・相談: ストリーミングで即レスポンス（UIが固まらない）
                with st.chat_message("assistant"):
                    from engine import stream_generate
                    system = (
                        f"{st.session_state.persona}\n\n"
                        f"【Blackwell主軸】{st.session_state.project_anchor}"
                        f"{game_anchor_part}"
                    )
                    streamed = st.write_stream(
                        stream_generate(full_prompt, system_prompt=system,
                                        model=MODELS.get("chat", MODELS["coder"]))
                    )
                st.session_state.messages.append({"role": "assistant", "content": streamed})

            st.session_state.quality_check_result = ""
            st.session_state["quality_needs_improve"] = False
            # ── セッション自動保存 ──
            try:
                from session_restore import save_session
                save_session(dict(st.session_state))
            except Exception:
                pass
            st.rerun()

        # ボタン行
        btn1, btn2, btn3 = st.columns(3)
        with btn1:
            if st.button("🗑 会話クリア", use_container_width=True, key="clear_main"):
                st.session_state.messages = []
                st.rerun()
        with btn2:
            # 💾 保存
            slbl = "💾 保存する" if not st.session_state.auto_write else "✅ 自動保存ON"
            if st.button(slbl, use_container_width=True, key="manual_save",
                         type="primary" if not st.session_state.auto_write else "secondary"):
                if st.session_state.auto_write:
                    st.info(f"自動保存ON — 保存先: {st.session_state.target_path}")
                elif st.session_state.last_result:
                    code_blocks = _re2.findall(
                        r"```(?:python|gdscript|javascript|csharp|gd)?\n(.*?)```",
                        st.session_state.last_result, _re2.DOTALL
                    )
                    file_names = _re2.findall(
                        r"\[OK\]\s+([\w./\\-]+\.\w+)", st.session_state.last_result
                    )
                    saved = []
                    for i, code in enumerate(code_blocks):
                        fn = file_names[i] if i < len(file_names) else f"output_{i+1}.py"
                        fp = os.path.join(st.session_state.target_path, os.path.basename(fn))
                        try:
                            with open(fp, "w", encoding="utf-8") as f:
                                f.write(code)
                            saved.append(fp)
                        except Exception as e:
                            st.error(f"保存失敗: {e}")
                    if saved:
                        st.success(f"✅ {len(saved)}件保存")
                else:
                    st.warning("先にコードを生成してください")
        with btn3:
            # ▶️ 再生ボタン（生成コードを実行）
            if st.button("▶️ 実行", use_container_width=True, key="run_code_main", type="primary"):
                if st.session_state.last_result:
                    code_blocks_run = _re2.findall(
                        r"```python\n(.*?)```",
                        st.session_state.last_result, _re2.DOTALL
                    )
                    if code_blocks_run:
                        run_code = code_blocks_run[0]
                        with st.spinner("実行中..."):
                            try:
                                from sandbox import run_code as sandbox_run
                                ok, out, err = sandbox_run(run_code)
                                if ok:
                                    st.success(f"✅ 実行成功\n{out[:300]}")
                                else:
                                    st.error(f"❌ エラー\n{err[:300]}")
                                    # エラーをcrash_check_resultに記録
                                    st.session_state.crash_check_result = err
                            except Exception as e:
                                # sandboxがない場合はsubprocessで実行
                                import subprocess, tempfile
                                with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as tf:
                                    tf.write(run_code); tfname = tf.name
                                try:
                                    r = subprocess.run(
                                        ["python", tfname],
                                        capture_output=True, text=True, timeout=10
                                    )
                                    if r.returncode == 0:
                                        st.success(f"✅ 実行OK\n{r.stdout[:300]}")
                                    else:
                                        st.error(f"❌ エラー\n{r.stderr[:300]}")
                                        st.session_state.crash_check_result = r.stderr
                                except subprocess.TimeoutExpired:
                                    st.warning("⏱ タイムアウト（正常な場合も多い）")
                                finally:
                                    import os as _os; _os.unlink(tfname)
                    else:
                        st.info("Pythonコードが見つかりません（Godot/UEは直接実行不可）")
                else:
                    st.warning("先にコードを生成してください")

        st.caption(f"📂 保存先: `{st.session_state.target_path}` | 自動保存: {'✅ ON' if st.session_state.auto_write else '❌ OFF'}")

    # ═══════════════════════════════════════════════
    # 右列
    # ═══════════════════════════════════════════════
    with col_right:

        # ── 🗺️ プロジェクト地図（Phase 1） ───────────
        st.markdown("#### 🗺️ プロジェクト地図")
        try:
            from project_map import format_map_for_sidebar, scan_project, get_map_stats
            _map_path = st.session_state.get("target_path", "./")
            _map_data = format_map_for_sidebar(_map_path)

            if _map_data["total_files"] == 0:
                st.caption("地図がまだありません")
                if st.button("🔍 スキャンして地図を作る", use_container_width=True, key="scan_map_btn"):
                    with st.spinner("スキャン中..."):
                        scan_project(_map_path)
                    st.rerun()
            else:
                st.caption(get_map_stats(_map_path))
                map_box = st.container(height=200, border=True)
                with map_box:
                    for f in _map_data["files"][:10]:
                        icon = {"python":"🐍","gdscript":"🎮","csharp":"🔷"}.get(f["language"],"📄")
                        st.caption(f"{icon} **{os.path.basename(f['path'])}** — {f['lines']}行")
                        if f["func_list"]:
                            st.caption("　" + "  /  ".join(f["func_list"][:4]))
                        if f["do_not"]:
                            st.caption(f"　⚠️ {f['do_not'][:40]}")
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    if st.button("🔄 更新", use_container_width=True, key="rescan_map_btn"):
                        with st.spinner("スキャン中..."):
                            scan_project(_map_path)
                        st.rerun()
                with col_m2:
                    st.caption(f"計{_map_data['total_files']}ファイル / {_map_data['total_lines']:,}行")
        except ImportError:
            st.caption("project_map.py が見つかりません")

        st.divider()

        # ── ① 生成ログ ───────────────────────────────
        st.markdown("#### 📋 生成ログ")
        log_box = st.container(height=160, border=True)
        with log_box:
            if st.session_state.build_log:
                for fn in reversed(st.session_state.build_log[-8:]):
                    st.caption(f"📄 {fn}")
            elif st.session_state.thinking_log:
                for line in st.session_state.thinking_log[-6:]:
                    st.caption(line)
            else:
                st.caption("生成すると何を作ったかここに表示されます")

        st.divider()

        # ── ② バグ/クラッシュ確認 ─────────────────────
        st.markdown("#### 🔍 バグ・クラッシュ確認")
        if st.button("🐛 バグスキャン", use_container_width=True, key="bug_scan_main"):
            if st.session_state.last_result:
                with st.spinner("スキャン中..."):
                    try:
                        crash_check = chat_with_persona(
                            message=(
                                "以下のコードを静的解析し、バグ・クラッシュ要因を指摘してください。\n"
                                "形式:\n"
                                "リスクレベル: 低/中/高\n"
                                "問題点: [箇条書き、最大3点]\n"
                                "修正提案: [各問題に1行]\n\n"
                                f"コード:\n{st.session_state.last_result[:2500]}"
                            ),
                            persona="バグハンター。簡潔に問題点のみ報告。",
                            anchor=get_combined_anchor()
                        )
                        st.session_state.crash_check_result = crash_check
                        st.rerun()
                    except Exception as e:
                        st.error(f"スキャン失敗: {e}")
            else:
                st.warning("コードを生成してください")

        if st.session_state.crash_check_result:
            cr = st.session_state.crash_check_result
            crash_box = st.container(height=160, border=True)
            with crash_box:
                if "高" in cr and "リスクレベル" in cr:
                    st.error(cr[:400])
                elif "中" in cr and "リスクレベル" in cr:
                    st.warning(cr[:400])
                else:
                    st.success(cr[:400])

            # バグがあれば自動修正ボタン
            if "問題点" in cr and ("高" in cr or "中" in cr):
                if st.button("🔧 バグを自動修正", use_container_width=True,
                             key="auto_fix_bug", type="primary"):
                    with st.spinner("修正中..."):
                        fix = autonomous_dev(
                            goal=f"【バグ修正】以下の問題を修正せよ:\n{cr}\n\n対象:\n{st.session_state.last_result[:2000]}",
                            auto_write=st.session_state.auto_write,
                            save_path=st.session_state.target_path,
                            anchor=get_combined_anchor(),
                            max_cycles=2
                        )
                    st.session_state.messages.append({"role": "assistant", "content": fix})
                    st.session_state.last_result = fix
                    st.session_state.crash_check_result = ""
                    st.rerun()
        else:
            st.info("バグスキャンをクリックすると結果がここに出ます")

        st.divider()

        # ── ③ 改善提案（詳細） ────────────────────────
        st.markdown("#### 🚀 改善提案・詳細")
        if st.button("💡 詳細提案を生成", use_container_width=True, key="detail_suggest_main"):
            if st.session_state.last_result:
                with st.spinner("生成中..."):
                    suggestion = chat_with_persona(
                        message=(
                            f"以下のコードに対して改善提案を3点、詳しく説明してください。\n\n"
                            f"{st.session_state.last_result[:2500]}"
                        ),
                        persona="厳格なアーキテクト。箇条書きで的確に。",
                        anchor=get_combined_anchor()
                    )
                    st.session_state.last_suggestion = suggestion
                    # pending_suggestions にも追加
                    import re as _re3
                    items = _re3.findall(r"\d+\.\s*(.+?)(?:\n|$)", suggestion)
                    new_items = [{"text": t.strip()[:60], "checked": False} for t in items[:5]]
                    existing = [s["text"] for s in st.session_state.pending_suggestions]
                    for ni in new_items:
                        if ni["text"] not in existing:
                            st.session_state.pending_suggestions.append(ni)
                    st.rerun()
            else:
                st.info("コードを生成してから実行してください")

        if st.session_state.last_suggestion:
            suggest_box = st.container(height=180, border=True)
            with suggest_box:
                st.markdown(st.session_state.last_suggestion[:600])
            if st.button("⚡ この提案を全て実行", use_container_width=True,
                         key="exec_suggestion_main", type="primary"):
                with st.spinner("実行中..."):
                    fix = autonomous_dev(
                        goal=f"【改善提案を反映】\n{st.session_state.last_suggestion}",
                        auto_write=st.session_state.auto_write,
                        save_path=st.session_state.target_path,
                        anchor=get_combined_anchor(),
                        max_cycles=2
                    )
                st.session_state.messages.append({"role": "assistant", "content": fix})
                st.session_state.last_result = fix
                st.rerun()
        else:
            st.info("提案を生成するとここに詳細が表示されます")



# ============================================================
# TAB 2: 📚 知識・学習ログ
# ============================================================
with tab_knowledge:
    st.header("📚 知識・学習ログ")

    ktab1, ktab2, ktab3 = st.tabs(["🔍 記憶検索", "📂 ファイル解析・学習", "📊 統計"])

    # ── 記憶検索 ──
    with ktab1:
        col_k1, col_k2 = st.columns([3, 2])
        with col_k1:
            st.subheader("🔍 記憶を検索")
            search_q = st.text_input("キーワード", placeholder="例: エラー処理、Godot、ゲームループ...")
            search_k = st.slider("取得件数", 1, 20, 5, key="search_k")
            if st.button("🔎 検索", use_container_width=True):
                if search_q.strip():
                    ctx = retrieve_context(search_q, k=search_k)
                    if ctx:
                        for i, chunk in enumerate(ctx.split("\n\n"), 1):
                            with st.expander(f"記憶 {i}: {chunk[:50]}...", expanded=(i == 1)):
                                st.text(chunk)
                    else:
                        st.warning("見つかりませんでした。")
        with col_k2:
            st.subheader("📊 記憶統計")
            try: st.metric("総記憶件数", f"{get_memory_count()} 件")
            except: st.metric("総記憶件数", "取得失敗")
            if st.session_state.last_suggestion:
                st.subheader("💡 最新の改善提案")
                st.markdown(st.session_state.last_suggestion)

    # ── ファイル解析・学習 ──
    with ktab2:
        st.subheader("📂 ユニバーサルファイル解析 & 学習")
        st.caption(
            "形式問わずファイルを深く解析してBlackwellに学習させます。\n"
            "ゲーム/アプリ/データ/画像/音声 — 何でも対応。\n"
            "解析結果はRAGに蓄積され、今後の生成に自動活用されます。"
        )

        anal_tab1, anal_tab2 = st.tabs(["📄 単ファイル解析", "📁 プロジェクト全体吸収"])

        # 単ファイル解析
        with anal_tab1:
            uploaded_analyze = st.file_uploader(
                "解析したいファイルをドロップ",
                accept_multiple_files=False,
                key="analyzer_upload",
                help="py / gd / js / json / png / wav / mp3 / txt / md など形式問わず"
            )

            # サイドバーのアップロードファイルも選択可能
            st.divider()
            st.caption("またはパスを直接入力:")
            manual_path = st.text_input("ファイルパス", placeholder="C:/MyProject/player.py", key="anal_path")

            if st.button("🔬 解析する", use_container_width=True, key="btn_analyze_file"):
                target_path = None
                target_name = None

                if uploaded_analyze:
                    # アップロードファイルを一時保存
                    import tempfile
                    suffix = os.path.splitext(uploaded_analyze.name)[1]
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(uploaded_analyze.read())
                        target_path = tmp.name
                    target_name = uploaded_analyze.name
                elif manual_path.strip():
                    target_path = manual_path.strip()
                    target_name = os.path.basename(target_path)

                if target_path:
                    with st.spinner(f"解析中: {target_name}..."):
                        try:
                            from analyzer import analyze_any_file
                            from memory import store_memory as sm
                            result = analyze_any_file(target_path)

                            if "error" in result:
                                st.error(result["error"])
                            else:
                                # 結果表示
                                col_r1, col_r2, col_r3 = st.columns(3)
                                col_r1.metric("種別", result.get("project_type", "不明"))
                                col_r2.metric("エンジン", result.get("game_engine", "不明"))
                                col_r3.metric("次元", result.get("dimension", "不明"))

                                if result.get("game_elements"):
                                    st.info(f"🎮 ゲーム要素: {', '.join(result['game_elements'])}")
                                if result.get("patterns"):
                                    st.info(f"⚙️ 実装パターン: {', '.join(result['patterns'])}")
                                if result.get("functions"):
                                    st.caption(f"関数: {', '.join(result['functions'][:8])}")
                                if result.get("classes"):
                                    st.caption(f"クラス: {', '.join(result['classes'][:5])}")
                                if result.get("width"):
                                    st.caption(f"解像度: {result.get('resolution')} / 役割: {result.get('asset_role','不明')}")

                                # 学習ポイント表示
                                lp = result.get("learning_points", [])
                                if lp:
                                    st.subheader("📖 学習ポイント")
                                    for point in lp:
                                        st.markdown(f"- {point}")

                                # ChromaDBに保存
                                import hashlib
                                key = f"analyzed_{hashlib.md5(target_path.encode()).hexdigest()[:8]}"
                                content = (
                                    f"【解析ファイル】{target_name}\n"
                                    f"種別: {result.get('project_type','不明')}\n"
                                    f"エンジン: {result.get('game_engine','不明')}\n"
                                    f"次元: {result.get('dimension','不明')}\n"
                                    f"要素: {', '.join(result.get('game_elements',[]))}\n"
                                    f"パターン: {', '.join(result.get('patterns',[]))}\n"
                                    f"関数: {', '.join(result.get('functions',[])[:10])}\n"
                                    f"学習ポイント:\n" +
                                    "\n".join(f"  - {p}" for p in lp)
                                )
                                sm(key, content, {
                                    "type": "file_analysis",
                                    "filename": target_name,
                                    "project_type": result.get("project_type", ""),
                                    "engine": result.get("game_engine", ""),
                                })
                                st.success(f"✅ '{target_name}' の解析完了。RAGに学習しました。")
                        except Exception as e:
                            st.error(f"解析エラー: {e}")
                else:
                    st.warning("ファイルをアップロードするかパスを入力してください。")

        # プロジェクト全体吸収
        with anal_tab2:
            st.subheader("📁 プロジェクト全体を一括学習")
            st.caption(
                "指定フォルダ以下の全ファイルを解析してRAGに蓄積します。\n"
                "ゲームプロジェクト・参考コードなど何でも学習できます。\n"
                "学習後は生成時に自動的に参考パターンが活用されます。"
            )

            absorb_path = st.text_input(
                "学習させるフォルダパス",
                value=st.session_state.target_path,
                placeholder="C:/MyGameProject",
                key="absorb_path_input"
            )

            col_ab1, col_ab2 = st.columns(2)
            with col_ab1:
                absorb_type = st.selectbox(
                    "プロジェクト種別（ヒント）",
                    ["自動判定", "ゲーム（2D）", "ゲーム（3D）", "Webアプリ", "AIツール", "CLIツール"],
                    key="absorb_type"
                )
            with col_ab2:
                if st.button("🧠 一括学習開始", use_container_width=True,
                             type="primary", key="btn_absorb"):
                    if absorb_path.strip() and os.path.isdir(absorb_path.strip()):
                        with st.spinner(f"学習中: {absorb_path}... （ファイル数によっては数分かかります）"):
                            try:
                                from analyzer import absorb_project
                                from memory import store_memory as sm
                                result = absorb_project(absorb_path.strip(), store_fn=sm)

                                st.success(f"✅ 学習完了: {result['total']}ファイル吸収")
                                st.metric("主要種別", result["dominant_type"])

                                if result["game_features"]:
                                    st.subheader("🎮 検出された特徴")
                                    for feat in result["game_features"][:15]:
                                        st.markdown(f"- {feat}")

                                with st.expander("種別内訳"):
                                    for t, c in result["by_type"].items():
                                        st.caption(f"{t}: {c}ファイル")
                            except Exception as e:
                                st.error(f"学習エラー: {e}")
                    else:
                        st.warning("有効なフォルダパスを入力してください。")

            # 依存グラフ構築ボタン
            st.divider()
            st.subheader("🗺 依存グラフを構築")
            st.caption("プロジェクトの関数・クラス・import依存関係をグラフ化します。\n変更の影響範囲（Blast Radius）が自動計算されるようになります。")
            graph_target = st.text_input("グラフ化するフォルダ", value=st.session_state.target_path, key="graph_target")
            if st.button("🔗 グラフ構築", use_container_width=True, key="btn_build_graph"):
                if graph_target.strip() and os.path.isdir(graph_target.strip()):
                    with st.spinner("グラフ構築中..."):
                        try:
                            from graph import build_project_graph, save_graph, get_project_summary
                            g = build_project_graph(graph_target.strip())
                            cache = os.path.join(graph_target.strip(), ".blackwell_graph.json")
                            save_graph(g, cache)
                            summary = get_project_summary(g)
                            st.success("✅ グラフ構築完了")
                            st.code(summary, language="text")
                        except Exception as e:
                            st.error(f"グラフ構築エラー: {e}")
                else:
                    st.warning("有効なフォルダパスを入力してください。")

    # ── 統計・Negative Cache・類似提案 ──
    with ktab3:
        st.subheader("📊 記憶統計 & 学習状態")
        col_st1, col_st2, col_st3 = st.columns(3)
        try:
            total_mem = get_memory_count()
            col_st1.metric("総記憶件数", f"{total_mem} 件")
        except Exception:
            col_st1.metric("総記憶件数", "取得失敗")
        col_st2.metric("記憶エンジン", "ChromaDB")
        col_st3.metric("成長", "使うほど賢くなります")

        st.divider()

        # ── Negative Cache（失敗記録）ビューア ──
        with st.expander("🚫 Negative Cache（失敗パターン記録）", expanded=False):
            st.caption("Blackwellが記録した「失敗パターン」です。次回同じミスを犯さないために活用されます。")
            neg_q = st.text_input("Negative Cacheを検索", placeholder="ImportError / timeout / ...", key="neg_search")
            if st.button("検索", key="btn_neg_search"):
                try:
                    from memory import retrieve_context as rc
                    results = rc("negcache " + neg_q, k=5)
                    if results and "禁止パターン" in results:
                        st.warning(results[:2000])
                    else:
                        st.info("該当するNegative Cacheはありません（まだ失敗記録がないか、検索キーワードが合わない）。")
                except Exception as e:
                    st.error(str(e))

        # ── 類似プロジェクト提案 ──
        with st.expander("🎯 類似プロジェクトから学ぶ・提案生成", expanded=False):
            st.caption(
                "過去に解析・学習したプロジェクトの知識から\n"
                "現在のゴールに合った提案を生成します。\n"
                "「複数の良いものを模倣してオリジナルに染め上げる」機能です。"
            )
            sim_goal = st.text_area(
                "現在のゴールや作りたいもの",
                placeholder="例: 2Dアクションゲームの当たり判定システム\n      RPGのバトルシステム\n      プレイヤー移動とカメラ追従",
                height=80, key="sim_goal"
            )
            sim_type = st.selectbox(
                "プロジェクト種別", ["自動", "2Dゲーム", "3Dゲーム", "RPG", "WebApp", "AIツール"],
                key="sim_type"
            )
            if st.button("📚 類似知識から提案を生成", use_container_width=True, key="btn_sim"):
                if sim_goal.strip():
                    with st.spinner("類似プロジェクトの知識を検索・統合中..."):
                        try:
                            from analyzer import suggest_from_similar
                            suggestion = suggest_from_similar(
                                sim_goal,
                                project_type="" if sim_type == "自動" else sim_type
                            )
                            if suggestion:
                                st.markdown(suggestion)
                                st.session_state.last_suggestion = suggestion
                            else:
                                st.info("類似プロジェクトの知識がまだありません。\n「📂 プロジェクト全体吸収」でゲームプロジェクトを学習させると使えるようになります。")
                        except Exception as e:
                            st.error(str(e))
                else:
                    st.warning("ゴールを入力してください。")

        # ── ゲーム素材マップ ──
        with st.expander("🎮 ゲーム素材マップ（Blackwellが把握している素材一覧）", expanded=False):
            st.caption(
                "指定フォルダの素材を全スキャンして分類します。\n"
                "Blackwellはこのマップを参照してゲームコードを生成します。"
            )
            asset_folder = st.text_input(
                "素材フォルダ", value=st.session_state.target_path,
                key="asset_folder_input"
            )
            if st.button("🗺 素材スキャン", use_container_width=True, key="btn_scan_assets"):
                if asset_folder.strip() and os.path.isdir(asset_folder.strip()):
                    with st.spinner("スキャン中..."):
                        try:
                            from analyzer import analyze_game_assets_folder
                            amap = analyze_game_assets_folder(asset_folder.strip())
                            summary = amap.get("_summary", {})
                            col_a1, col_a2, col_a3, col_a4 = st.columns(4)
                            col_a1.metric("総素材数", summary.get("total_files", 0))
                            col_a2.metric("スプライト", summary.get("sprite_count", 0))
                            col_a3.metric("BGM", summary.get("bgm_count", 0))
                            col_a4.metric("SE", summary.get("se_count", 0))

                            for category, files in amap.items():
                                if category.startswith("_") or not files: continue
                                label = {
                                    "sprites": "🧍 スプライト",
                                    "tiles": "🧱 タイル",
                                    "backgrounds": "🌄 背景",
                                    "ui": "🖼 UI",
                                    "effects": "✨ エフェクト",
                                    "audio_bgm": "🎵 BGM",
                                    "audio_se": "🔊 SE",
                                    "data_json": "📄 ゲームデータ",
                                    "scripts": "📝 スクリプト",
                                    "other": "📦 その他",
                                }.get(category, category)
                                with st.expander(f"{label} ({len(files)}件)", expanded=False):
                                    for f in files[:20]:
                                        st.caption(f"• {f}")
                                    if len(files) > 20:
                                        st.caption(f"...他{len(files)-20}件")

                            # 素材マップをsession_stateに保存（生成時に活用）
                            st.session_state["asset_map"] = amap
                            st.session_state["asset_folder"] = asset_folder.strip()
                            st.success("✅ 素材マップを作成しました。次のゲーム生成時に自動的に活用されます。")
                        except Exception as e:
                            st.error(f"スキャンエラー: {e}")
                else:
                    st.warning("有効なフォルダパスを入力してください。")

        if st.session_state.last_suggestion:
            st.divider()
            st.subheader("💡 最新の改善提案")
            st.markdown(st.session_state.last_suggestion)

# ============================================================
# TAB 3: 💡 改善提案
# ============================================================
with tab_improvement:
    st.header("💡 改善提案・コードレビュー（フェーズ4）")
    try:
        py_files = []
        for root_d, dirs, files in os.walk(save_path):
            dirs[:] = [d for d in dirs if d not in [".git", "__pycache__"]]
            for f in files:
                if f.endswith((".py", ".js", ".ts", ".gd", ".cs")):
                    py_files.append(os.path.relpath(os.path.join(root_d, f), save_path))
        if py_files:
            review_file = st.selectbox("レビュー対象ファイル", sorted(py_files))
            with open(os.path.join(save_path, review_file), encoding="utf-8", errors="ignore") as f:
                review_code = f.read()
            with st.expander("📄 コード確認", expanded=False):
                st.code(review_code[:2000], language="python")
        else:
            review_code = ""; st.info("ファイルが見つかりません。")
    except Exception as e:
        review_code = ""; st.error(str(e))
    st.divider()
    for msg in st.session_state.improve_messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    if improve_input := st.chat_input("改善点・疑問点を聞いてください", key="improve_chat"):
        st.session_state.improve_messages.append({"role": "user", "content": improve_input})
        context = f"対象コード:\n```python\n{review_code[:1500]}\n```\n\n" if review_code else ""
        with st.spinner("考え中..."):
            reply = chat_with_persona(
                message=context + improve_input,
                persona="厳格なコードアーキテクト。改善提案をコードブロック付きで。",
                history=st.session_state.improve_messages[-8:],
                anchor=get_combined_anchor()
            )
        st.session_state.improve_messages.append({"role": "assistant", "content": reply})
        st.rerun()

# ============================================================
# TAB 4: 🧠 記憶ブラウザ
# ============================================================
with tab_memory_tab:
    st.header("🧠 記憶ブラウザ")
    try: total = get_memory_count()
    except: total = 0
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("総記憶件数", f"{total} 件")
    col_m2.metric("ベクトルDB", "ChromaDB")
    col_m3.metric("埋め込みモデル", "all-MiniLM-L6-v2")
    st.divider()
    if st.button("🔄 更新", key="mem_ref"): st.rerun()
    try:
        memories = list_memories(limit=100)
        if memories:
            type_filter = st.selectbox(
                "フィルター",
                ["すべて", "wisdom（学習知識）", "lesson（教訓）",
                 "negcache（失敗記録）", "project_analysis（解析結果）", "コード記憶"]
            )
            for mem in memories:
                meta = mem.get("meta", {}); key = mem.get("key", "unknown")
                preview = mem.get("preview", ""); mtype = meta.get("type", "code")
                if type_filter == "wisdom（学習知識）" and mtype != "wisdom": continue
                if type_filter == "lesson（教訓）" and mtype != "lesson": continue
                if type_filter == "negcache（失敗記録）" and mtype != "negative_cache": continue
                if type_filter == "project_analysis（解析結果）" and mtype != "project_analysis": continue
                if type_filter == "コード記憶" and mtype in {"wisdom","lesson","negative_cache","project_analysis"}: continue
                icon = {"wisdom":"📚","lesson":"📖","negative_cache":"🚫","project_analysis":"🎮"}.get(mtype,"💾")
                with st.expander(f"{icon} **{key}**", expanded=False):
                    st.text(preview)
                    if st.button("🗑 削除", key=f"del_{key}_{hash(preview)}"):
                        deleted = delete_memory(key)
                        st.success(f"✅ {deleted}件削除") if deleted else st.warning("削除対象なし")
                        st.rerun()
        else:
            st.info("記憶がまだありません。")
    except Exception as e:
        st.error(str(e))
    st.divider()
    with st.expander("⚠️ 全記憶を消去する（取り消し不可）"):
        confirm_text = st.text_input("「全削除」と入力")
        if st.button("💥 全消去", type="primary", disabled=(confirm_text != "全削除")):
            st.success(f"✅ {delete_memory('')}件消去しました。"); st.rerun()

# ============================================================
# TAB 5: 🎭 AIVtuber
# ============================================================
with tab_aivtuber:
    st.header("🎭 AIVtuber コントロールパネル")
    st.caption("配信コメント → AI返答生成 → VOICEVOX音声 → VRStudio連携")

    # ── 接続状況ダッシュボード ──────────────────────────
    st.subheader("🔌 接続状況")
    if st.button("🔄 接続チェック", use_container_width=False):
        st.rerun()

    vv_ok, vv_ver   = check_voicevox(st.session_state.vt_voicevox_url)
    vrs_ok          = check_vrstudio(st.session_state.vt_vrstudio_url)
    sd_ok           = check_sd(st.session_state.vt_sd_url)

    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        if vv_ok:
            st.success(f"✅ VOICEVOX\nv{vv_ver}")
        else:
            st.error("❌ VOICEVOX\n未起動 or 接続失敗")
            st.caption("→ VOICEVOXアプリを起動してください")

    with col_c2:
        if vrs_ok:
            st.success("✅ VRStudio\n接続OK")
        else:
            st.warning("⚠️ VRStudio\n未接続")
            st.caption("→ VRStudioのOSCを有効にしてください")

    with col_c3:
        if sd_ok:
            st.success("✅ Stable Diffusion\n起動中")
        else:
            st.warning("⚠️ Stable Diffusion\n未起動")
            st.caption("→ Automatic1111を --api オプションで起動")

    # セッティングミスの診断
    issues = []
    if not vv_ok:
        issues.append(("🔴 CRITICAL", "VOICEVOXが起動していません。音声合成ができません。",
                        "VOICEVOXアプリを起動してください。"))
    if not vrs_ok:
        issues.append(("🟡 WARNING",  "VRStudioに接続できません。リップシンク・モーション連携が無効です。",
                        f"VRStudio の OSC受信を有効にし、ポートが {st.session_state.vt_vrstudio_url.split(':')[-1]} であることを確認してください。"))
    if not sd_ok:
        issues.append(("🟡 WARNING",  "Stable Diffusionに接続できません。画像生成機能が無効です。",
                        "Automatic1111 を --api オプション付きで起動してください。"))
    if not vv_ok and not vrs_ok:
        issues.append(("🔴 CRITICAL", "主要コンポーネントがすべて未起動です。",
                        "VOICEVOX → VRStudio → app.py の順で起動してください。"))

    if issues:
        st.divider()
        st.subheader("⚠️ セッティング診断")
        for level, problem, solution in issues:
            with st.expander(f"{level}: {problem[:50]}...", expanded=True):
                st.markdown(f"**問題:** {problem}")
                st.markdown(f"**解決策:** {solution}")
    else:
        st.success("✅ すべての接続が正常です！AIVtuberを起動できます。")

    st.divider()

    # ── 設定パネル ───────────────────────────────────
    st.subheader("⚙️ AIVtuber 設定")
    col_set1, col_set2 = st.columns(2)

    with col_set1:
        st.markdown("**🎤 VOICEVOXスピーカー設定**")
        st.session_state.vt_voicevox_url = st.text_input(
            "VOICEVOX URL", value=st.session_state.vt_voicevox_url
        )
        st.session_state.vt_speaker_id = st.number_input(
            "スピーカーID", min_value=0, max_value=100,
            value=st.session_state.vt_speaker_id,
            help="0=四国めたん 1=ずんだもん 2=春日部つむぎ など"
        )
        st.caption("主なID: 0=四国めたん / 1=ずんだもん / 3=雨晴はう / 8=春日部つむぎ")

        st.markdown("**🌐 VRStudio設定**")
        st.session_state.vt_vrstudio_url = st.text_input(
            "VRStudio URL", value=st.session_state.vt_vrstudio_url,
            help="VRStudioのOSC受信アドレス"
        )

    with col_set2:
        st.markdown("**🎭 キャラクター性格設定**")
        new_vt_persona = st.text_area(
            "AIVtuberの性格", value=st.session_state.vt_persona, height=120,
            label_visibility="collapsed",
            placeholder="例: あなたはVRストリーマーのAIVtuberです..."
        )
        if st.button("✅ 性格を適用", use_container_width=True):
            st.session_state.vt_persona = new_vt_persona
            st.success("性格を更新しました")

        st.markdown("**🖼️ Stable Diffusion設定**")
        st.session_state.vt_sd_url = st.text_input(
            "SD WebUI URL", value=st.session_state.vt_sd_url
        )

    st.divider()

    # ── テスト送信 ──────────────────────────────────
    st.subheader("🧪 動作テスト")
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        test_text = st.text_input("テスト発話テキスト", value="こんにちは！テスト配信中です！")
    with col_t2:
        run_test = st.button("▶️ テスト実行", use_container_width=True, type="primary")

    if run_test and test_text:
        with st.spinner("AIVtuber応答生成中..."):
            result_vt = aivtuber_respond(
                user_text=test_text,
                persona=st.session_state.vt_persona,
                speaker_id=int(st.session_state.vt_speaker_id),
                voicevox_url=st.session_state.vt_voicevox_url,
                voice_save_dir=os.path.join(save_path, "voices"),
            )
        st.markdown(f"**AI返答:** {result_vt['reply_text']}")
        if result_vt["success"]:
            st.success(f"✅ 音声生成完了: `{result_vt['voice_path']}`")
            try:
                with open(result_vt["voice_path"], "rb") as f:
                    st.audio(f.read(), format="audio/wav")
            except Exception:
                pass
        else:
            st.error(f"❌ 音声生成失敗: {result_vt['voice_error']}")

    st.divider()

    # ── 今後の実装ロードマップ ──────────────────────
    with st.expander("🗺️ AIVtuber 実装ロードマップ", expanded=False):
        st.markdown("""
### ✅ 完了済み
- AIによる返答テキスト生成（`chat_with_persona`）
- VOICEVOX音声合成（`speak_voicevox`）
- Stable Diffusion画像生成（`generate_image_sd`）
- Whisper音声認識（`transcribe_whisper`）

### 🔜 次のステップ（実装可能）
1. **OSC連携** — VRStudioのリップシンク・表情・モーションをOSCで制御
2. **配信コメント自動取得** — YouTube/Twitchのコメントを自動取得してAIが返答
3. **感情分析** — コメントの感情をAIが判断してキャラクターの表情を変える
4. **SD画像 → VRStudio背景** — 生成した画像をリアルタイムで背景に適用

### 🎯 VRStudio連携の仕組み
```
配信コメント取得
    ↓
transcribe_whisper() / コメント取得API
    ↓
aivtuber_respond() → テキスト返答
    ↓
speak_voicevox() → WAV音声
    ↓
OSC送信 → VRStudio（リップシンク + 表情）
    ↓
配信画面に反映
```
""")

# ============================================================
# TAB 7: 🔍 自律監視
# ============================================================
with tab_monitor_tab:
    st.header("🔍 自律監視ダッシュボード")
    col_mn1, col_mn2 = st.columns([3, 1])
    with col_mn1: st.info(f"監視対象: `{save_path}`")
    with col_mn2: run_monitor = st.button("🚀 監視実行", use_container_width=True, type="primary")
    if run_monitor:
        with st.spinner("🔍 スキャン・分析中..."):
            try:
                st.session_state.monitor_result = monitor_project(
                    save_path=save_path, anchor=get_combined_anchor()
                )
            except Exception as e: st.error(str(e))
    result = st.session_state.monitor_result
    if result:
        st.divider()
        health = result.get("overall_health", "unknown")
        health_label = {"good": "✅ 健全", "warning": "⚠️ 注意あり", "critical": "🚨 重大問題あり"}.get(health, "❓ 不明")
        col_h1, col_h2, col_h3 = st.columns(3)
        col_h1.metric("プロジェクト健康度", health_label)
        col_h2.metric("スキャンファイル数", f"{result.get('files_scanned', 0)} 件")
        col_h3.metric("検出問題数", f"{len(result.get('issues', []))} 件")
        issues = result.get("issues", [])
        if issues:
            st.subheader("🚨 検出された問題")
            for issue in issues:
                sev = issue.get("severity", "info")
                icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(sev, "⚪")
                with st.expander(f"{icon} `{issue.get('file','?')}` — {issue.get('problem','')[:60]}", expanded=(sev == "critical")):
                    st.markdown(f"**問題:** {issue.get('problem','')}")
                    if st.button("🔧 自動修正", key=f"fix_{hash(str(issue))}"):
                        with st.spinner("修正中..."):
                            fix_result = autonomous_dev(
                                goal=f"以下の問題を修正: {issue.get('problem','')}",
                                auto_write=st.session_state.auto_write,
                                save_path=save_path,
                                anchor=get_combined_anchor(), max_cycles=2
                            )
                        st.markdown(fix_result)
        else:
            st.success("✅ 問題は検出されませんでした！")
        for section, title in [("suggestions", "💡 改善提案"), ("next_actions", "⚡ 次のアクション")]:
            items = result.get(section, [])
            if items:
                st.subheader(title)
                for i, item in enumerate(items, 1):
                    if section == "next_actions":
                        col_a1, col_a2 = st.columns([4, 1])
                        col_a1.markdown(f"**{i}.** {item}")
                        with col_a2:
                            if st.button("実行", key=f"act_{i}_{hash(item)}", use_container_width=True):
                                with st.spinner("実行中..."):
                                    er = autonomous_dev(
                                        goal=f"【主軸】\n{get_combined_anchor()}\n\n{item}",
                                        auto_write=st.session_state.auto_write,
                                        save_path=save_path,
                                        anchor=get_combined_anchor(),
                                        max_cycles=st.session_state.max_cycles
                                    )
                                st.markdown(er)
                    else:
                        st.markdown(f"{i}. {item}")
    else:
        st.info("「監視実行」ボタンを押すと、AIがプロジェクトを自動診断します。")

# ============================================================
# TAB 8: 🖼️ 生成物プレビュー
# ============================================================
with tab_preview:
    st.header("🖼️ 成果物ブラウザ")
    if st.button("🔄 更新", key="prev_ref"): st.rerun()
    try:
        if os.path.exists(save_path):
            all_files = []
            for root_d, dirs, files in os.walk(save_path):
                dirs[:] = [d for d in dirs if d not in [".git", "__pycache__", "node_modules"]]
                for file in files:
                    all_files.append(os.path.relpath(os.path.join(root_d, file), save_path))
            if all_files:
                selected = st.selectbox("ファイル選択", sorted(all_files))
                file_path = os.path.join(save_path, selected)
                ext = os.path.splitext(selected)[1].lower()
                st.divider()
                if os.path.exists(file_path):
                    st.caption(f"サイズ: {os.path.getsize(file_path):,} bytes")
                    with open(file_path, "rb") as f:
                        st.download_button("💾 ダウンロード", f, file_name=os.path.basename(selected))
                    lang_map = {'.py':'python','.js':'javascript','.ts':'typescript',
                                '.html':'html','.css':'css','.json':'json','.md':'markdown','.gd':'gdscript'}
                    if ext in lang_map or ext in ['.txt','.yaml','.yml','.toml','.cfg','.ini']:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            st.code(f.read(), language=lang_map.get(ext, "text"))
                    elif ext in ['.png','.jpg','.jpeg','.webp','.gif']:
                        st.image(file_path, use_container_width=True)
                    elif ext == '.wav':
                        with open(file_path, "rb") as f:
                            st.audio(f.read(), format="audio/wav")
                    else:
                        st.info(f"プレビュー非対応: `{ext}`")
            else:
                st.warning("ファイルが見つかりません。")
        else:
            st.error("パスが無効です。")
    except Exception as e:
        st.error(str(e))

# ============================================================
# TAB 9: 📜 実行ログ & Git
# ============================================================
with tab_log:
    st.header("📜 システム・トレーサビリティ")
    col1, col2, col3 = st.columns(3)
    col1.metric("自動保存", "✅ 有効" if st.session_state.auto_write else "⛔ 無効")
    col2.metric("稼働モード", app_mode)
    col3.metric("最大サイクル", f"{st.session_state.max_cycles} 回")
    st.divider()
    st.subheader("🔍 直近の実行ログ")
    if st.session_state.last_log:
        st.code("\n".join(st.session_state.last_log), language="text")
    else:
        st.info("まだ実行ログがありません。")
    st.divider()
    st.subheader("📦 Git Commit 履歴")
    try:
        git_log = get_git_log()
        st.code(git_log if git_log else "コミット履歴なし", language="text")
    except Exception as e:
        st.warning(str(e))
    st.divider()
    col_c1, col_c2 = st.columns([3, 1])
    with col_c1:
        commit_msg = st.text_input("コミットメッセージ", value="Manual commit from Blackwell UI")
    with col_c2:
        if st.button("📦 コミット", use_container_width=True):
            commit_all(commit_msg); st.success("✅ コミット完了")

# ============================================================
# TAB 🎮 ゲーム開発（全機能統合ハブ）
# ─────────────────────────────────────────────────────────────
#  サブタブ:
#   ① フィーリングスライダー  — 重厚感・爽快感をつまみで調整
#   ② タイムマシン           — 面白かったバージョンに戻る
#   ③ 素材マップ             — 何がどこで使われているか図で表示
#   ④ Godotビルド           — exe/Web書き出しボタン
#   ⑤ AIプレイテスト         — 自動テスト+弱点報告
#   ⑥ BGM最適化             — BPMからゲームテンポを自動調整
#   ⑦ 無料API               — Wikipedia/PokeAPI/天気をゲームに注入
#   ⑧ 面白さ理論             — MDA/フロー理論の説明+診断
# ============================================================
with tab_gamedev:
    gd_tabs = st.tabs([
        "🎨 フィーリング",
        "⏪ タイムマシン",
        "🗺️ 素材マップ",
        "⚡ ビルド",
        "🤖 AIテスト",
        "🎵 BGM最適化",
        "🌐 無料API",
        "📖 面白さ理論",
        "🏥 健康診断",
        "⚖️ バランスAI",
        "🐛 エラー辞書",
        "🤖 マルチエージェント",
        "🤝 ペアプログラマー",
        "🕸️ 依存グラフ",
        "📹 プレイ解析",
        "📄 ドキュメント生成",
        "📋 タスク自動分解",
        "💗 感情グラフ",
        "🔁 自己改善",
        "🖥️ Watchdog",
        "🏗️ プロジェクト生成",
        "📜 契約マップ",
        "⏱️ 開発履歴",
        "🔮 リスク予測",
        "⚡ 並列シミュ",
        "🧠 思考ログ",
        "📚 学習データ",
        "🧬 プロンプト進化",
        "🌙 夜間バッチ",
        "📋 バックログ",
        "🤖 エージェント",
        "🎮 ゲームプレイ",
        "🤔 自己モデル",
        "🔌 Godot接続",
        "🧠 プレイヤーAI",
        "🎬 動画解析",
        "🌐 知識ハブ",
        "🔧 自動修復",
        "📄 ドキュメント同期",
        "🎵 音楽・SE生成",
        "🗂️ バージョン管理AI",
    ])

    # ─────────────────────────────────────────────────────────
    # ① フィーリングスライダー
    # ─────────────────────────────────────────────────────────
    with gd_tabs[0]:
        st.markdown("### 🎨 フィーリングスライダー")
        st.caption("抽象的な「感覚」をつまみで調整 → AIが数百パラメータを自動変換してコードを出力")

        # エンジン・ジャンル選択
        fs_col1, fs_col2 = st.columns(2)
        with fs_col1:
            fs_engine = st.selectbox("エンジン", ["godot","pygame","unity","unreal"], key="fs_engine")
        with fs_col2:
            fs_genre = st.selectbox("ジャンル", list(["2daction","roguelike","simulation","towerdefense","3daction"]),
                                    format_func=lambda x: {"2daction":"2Dアクション","roguelike":"ローグライク",
                                        "simulation":"シミュレーション","towerdefense":"タワーディフェンス",
                                        "3daction":"3DアクションRPG"}.get(x,x),
                                    key="fs_genre")

        st.divider()

        # スライダー群
        sc1, sc2 = st.columns(2)
        with sc1:
            heavy = st.slider("⚖️ 重厚感", 0.0, 1.0, 0.5, 0.05, key="sl_heavy",
                              help="0=軽快でキビキビ / 1=ズッシリ重い")
            excite = st.slider("⚡ 爽快感", 0.0, 1.0, 0.5, 0.05, key="sl_excite",
                               help="0=落ち着いた渋さ / 1=爆発的爽快")
            tension = st.slider("😰 緊張感", 0.0, 1.0, 0.5, 0.05, key="sl_tension",
                                help="0=ゆるふわ / 1=ヒリヒリ")
        with sc2:
            fantasy = st.slider("✨ 幻想感", 0.0, 1.0, 0.5, 0.05, key="sl_fantasy",
                                help="0=リアル路線 / 1=ファンタジー全開")
            diff = st.slider("💀 難易度", 0.0, 1.0, 0.5, 0.05, key="sl_diff",
                             help="0=誰でも楽しめる / 1=死にゲー")
            tempo = st.slider("⏩ テンポ", 0.0, 1.0, 0.5, 0.05, key="sl_tempo",
                              help="0=ゆったり / 1=高速展開")

        if st.button("🎛️ パラメータを生成してコードに反映", use_container_width=True,
                     type="primary", key="gen_feeling"):
            try:
                from game_theory import FeelingSliders, apply_feeling_slider
                sliders = FeelingSliders(
                    heaviness=heavy, excitement=excite, tension=tension,
                    fantasy=fantasy, difficulty=diff, tempo=tempo
                )
                params = apply_feeling_slider(sliders, fs_engine, fs_genre)
                st.session_state["feeling_params"] = params

                # ── engine.pyに即時注入（次のコード生成から反映される）──
                try:
                    from engine import set_feeling_params
                    set_feeling_params(params)
                    st.success(f"✅ 設定: **{params['description']}**\n\n🤖 次のコード生成から自動的にこのパラメータが使われます")
                except Exception as fe:
                    st.success(f"✅ 設定: **{params['description']}**")
                    st.warning(f"engine注入失敗（コード生成への反映なし）: {fe}")

                # コードスニペット表示
                st.code(params["code_snippet"], language="gdscript" if fs_engine=="godot" else "python")

                # エンジンの保存先に定数ファイルとして書き出し
                if st.session_state.auto_write:
                    out_ext = ".gd" if fs_engine == "godot" else ".py"
                    out_name = f"feeling_constants{out_ext}"
                    out_path = os.path.join(st.session_state.target_path, out_name)
                    try:
                        with open(out_path, "w", encoding="utf-8") as f:
                            f.write(params["code_snippet"])
                        st.info(f"📄 {out_name} を保存しました")
                    except Exception as e:
                        st.warning(f"保存失敗: {e}")

                # BGM推奨BPMも表示
                st.caption(f"🎵 BGM推奨BPM: **{params['bgm_bpm_target']}** BPM")
                st.caption(f"📷 カメラシェイク強度: {params['camera_shake_intensity']:.1f}")
                st.caption(f"💥 ヒットストップ: {params['hit_stop_frames']}フレーム")

            except Exception as e:
                st.error(f"生成失敗: {e}")

    # ─────────────────────────────────────────────────────────
    # ② タイムマシン
    # ─────────────────────────────────────────────────────────
    with gd_tabs[1]:
        st.markdown("### ⏪ タイムマシン — バージョン分岐")
        st.caption("「このバージョン面白かった！」→ Gitタグで保存 → いつでも戻れる")

        tm_col1, tm_col2 = st.columns([3, 2])

        with tm_col1:
            st.markdown("#### 📸 今のバージョンを保存")
            snap_name = st.text_input("スナップショット名",
                                       placeholder="例: プレイヤーの移動が気持ちよかった",
                                       key="snap_name")
            if st.button("💾 スナップショット保存", use_container_width=True,
                         type="primary", key="save_snap"):
                if snap_name:
                    try:
                        from build_pipeline import create_snapshot
                        result = create_snapshot(
                            snap_name, snap_name,
                            st.session_state.target_path
                        )
                        if result.get("success"):
                            st.success(f"✅ {result['message']}")
                        else:
                            st.error(f"保存失敗: {result.get('error','')}")
                    except Exception as e:
                        st.error(f"エラー: {e}")
                else:
                    st.warning("スナップショット名を入力してください")

        with tm_col2:
            st.markdown("#### 📊 変更差分")
            if st.button("🔍 前回との差分", use_container_width=True, key="show_diff"):
                try:
                    from build_pipeline import list_snapshots, diff_from_snapshot
                    snaps = list_snapshots(st.session_state.target_path)
                    if snaps:
                        diff = diff_from_snapshot(snaps[0]["tag"], st.session_state.target_path)
                        st.code(diff, language="diff")
                    else:
                        st.info("スナップショットがまだありません")
                except Exception as e:
                    st.error(str(e))

        st.divider()
        st.markdown("#### 🕰️ 保存済みスナップショット一覧")

        try:
            from build_pipeline import list_snapshots, restore_snapshot
            snaps = list_snapshots(st.session_state.target_path)
            if snaps:
                for snap in snaps:
                    sc1, sc2, sc3 = st.columns([4, 2, 2])
                    with sc1:
                        st.caption(f"📸 **{snap['display']}**  —  {snap['date']}")
                    with sc2:
                        if snap.get("message"):
                            st.caption(snap["message"][:30])
                    with sc3:
                        if st.button(f"↩️ ここに戻る", key=f"restore_{snap['tag']}",
                                     use_container_width=True):
                            r = restore_snapshot(snap["tag"], st.session_state.target_path)
                            if r["success"]:
                                st.success(r["message"])
                                st.rerun()
                            else:
                                st.error(r["message"])
            else:
                st.info("まだスナップショットがありません。上のボタンで保存してください。")
        except Exception as e:
            st.warning(f"Gitが使用できません: {e}\n保存先フォルダでgit initが必要です。")

    # ─────────────────────────────────────────────────────────
    # ③ 素材マップ
    # ─────────────────────────────────────────────────────────
    with gd_tabs[2]:
        st.markdown("### 🗺️ プロジェクト素材マップ")
        st.caption("どの素材がどこで使われているか — 視覚的に把握する")

        if st.button("🔄 素材マップを生成", use_container_width=True,
                     type="primary", key="gen_asset_map"):
            with st.spinner("素材を解析中..."):
                try:
                    from asset_pipeline import scan_project_assets
                    from build_pipeline import generate_asset_map_svg, _text_asset_map

                    manifest = scan_project_assets(st.session_state.target_path)
                    st.session_state["asset_manifest_for_map"] = manifest

                    # SVG生成
                    svg_path = os.path.join(st.session_state.target_path, "asset_map.svg")
                    result = generate_asset_map_svg(manifest, svg_path)
                    st.session_state["asset_map_svg"] = result

                    total = (manifest.summary.get("total_sprites",0) +
                             manifest.summary.get("total_tilesets",0) +
                             manifest.summary.get("total_bgm",0) +
                             manifest.summary.get("total_se",0))
                    st.success(f"✅ {total}個の素材を検出しました")
                except Exception as e:
                    st.error(f"生成失敗: {e}")

        # マップ表示
        if "asset_map_svg" in st.session_state and st.session_state["asset_map_svg"]:
            svg_data = st.session_state["asset_map_svg"]
            if svg_data.endswith(".svg") and os.path.exists(svg_data):
                with open(svg_data, encoding="utf-8") as f:
                    svg_content = f.read()
                st.markdown(svg_content, unsafe_allow_html=True)
            else:
                # SVG文字列として直接表示
                st.markdown(svg_data, unsafe_allow_html=True)

        # テキスト版も表示
        if "asset_manifest_for_map" in st.session_state:
            manifest = st.session_state["asset_manifest_for_map"]
            with st.expander("📋 素材一覧（テキスト版）", expanded=False):
                # スプライト
                if manifest.sprites:
                    st.markdown("**🧍 スプライト**")
                    for s in manifest.sprites[:15]:
                        badge = f"シート{s.sheet_cols}×{s.sheet_rows}={s.total_frames}f" if s.is_sheet else f"{s.width}×{s.height}px"
                        st.caption(f"[{s.role}] `{s.name}` — {badge}")
                # アニメーション
                if manifest.anim_groups:
                    st.markdown("**🎬 アニメーション**")
                    for g, frames in list(manifest.anim_groups.items())[:8]:
                        st.caption(f"`{g}` — {len(frames)}フレーム")
                # 音声
                if manifest.audio_bgm or manifest.audio_se:
                    st.markdown("**🎵 音声**")
                    for a in manifest.audio_bgm[:4]:
                        st.caption(f"BGM: `{a.name}` {a.duration_s}秒" +
                                   (f" / 推定{a.bpm_estimate}BPM" if a.bpm_estimate else ""))
                    for a in manifest.audio_se[:6]:
                        st.caption(f"SE: `{a.name}`")

    # ─────────────────────────────────────────────────────────
    # ④ Godotビルド
    # ─────────────────────────────────────────────────────────
    with gd_tabs[3]:
        st.markdown("### ⚡ Godot自動ビルド")
        st.caption("ボタン1つでWindows exe / Web HTML5 を書き出す")

        bd_col1, bd_col2 = st.columns(2)
        with bd_col1:
            build_target = st.selectbox("ビルドターゲット",
                ["windows","web","linux","mac"],
                format_func=lambda x: {"windows":"🪟 Windows (.exe)",
                    "web":"🌐 Web (HTML5)","linux":"🐧 Linux","mac":"🍎 macOS"}.get(x,x),
                key="build_target")
            project_name = st.text_input("ゲーム名", value="MyGame", key="build_name")
        with bd_col2:
            godot_exe_path = st.text_input("Godot実行ファイルパス（空白=自動検索）",
                                            placeholder="例: C:\\Program Files\\Godot\\Godot.exe",
                                            key="godot_exe_path")

        # export_presets.cfg チェック
        try:
            from build_pipeline import check_export_presets, generate_export_presets, build_godot, find_godot_exe
            has_presets = check_export_presets(st.session_state.target_path)
            if not has_presets:
                st.warning("⚠️ export_presets.cfg が見つかりません")
                if st.button("📝 export_presets.cfg を自動生成", key="gen_presets"):
                    path = generate_export_presets(st.session_state.target_path, project_name)
                    st.success(f"✅ 生成しました: {path}")
        except Exception:
            has_presets = False

        # Godot検索
        godot_found = find_godot_exe() if not godot_exe_path else godot_exe_path
        if godot_found:
            st.success(f"✅ Godot検出: `{godot_found}`")
        else:
            st.error("❌ Godotが見つかりません。パスを手動で指定してください。")

        if st.button(f"🔨 {build_target.upper()}向けにビルド開始",
                     use_container_width=True, type="primary", key="start_build"):
            with st.spinner(f"{build_target}向けビルド中... (最大2分)"):
                try:
                    result = build_godot(
                        project_path=st.session_state.target_path,
                        target=build_target,
                        output_name=project_name,
                        godot_exe=godot_exe_path or None
                    )
                    if result["success"]:
                        st.success(f"✅ ビルド成功！\n出力先: `{result['output_file']}`")
                        st.balloons()
                        # スナップショット自動保存
                        try:
                            from build_pipeline import create_snapshot
                            create_snapshot(
                                f"build_{build_target}",
                                f"{build_target}向けビルド成功",
                                st.session_state.target_path
                            )
                        except Exception:
                            pass
                    else:
                        st.error(f"❌ ビルド失敗\n{result.get('error','')}")
                        if result.get("stderr"):
                            st.code(result["stderr"], language="text")
                except Exception as e:
                    st.error(f"エラー: {e}")

        with st.expander("📋 Godot CLIコマンド（手動実行用）", expanded=False):
            cmd_preview = (
                f'godot --headless --export-release "{build_target.title()} Desktop" '
                f'export/{build_target}/{project_name}.exe --path "{st.session_state.target_path}"'
            )
            st.code(cmd_preview, language="bash")

    # ─────────────────────────────────────────────────────────
    # ⑤ AIプレイテスト（完全自動化）
    # ─────────────────────────────────────────────────────────
    with gd_tabs[4]:
        st.markdown("### 🤖 AIプレイテスト（完全自動）")
        st.caption("ボタン1つ → Godotヘッドレス起動 → 結果取得 → バグ修正まで全自動")

        pt_col1, pt_col2 = st.columns(2)
        with pt_col1:
            scene_path = st.text_input("シーンパス", value="res://scenes/main.tscn", key="pt_scene")
            pt_timeout = st.slider("タイムアウト（秒）", 30, 180, 60, 10, key="pt_timeout")
        with pt_col2:
            pt_godot   = st.text_input("Godotパス（空=自動検索）", key="pt_godot_path")
            pt_auto_fix= st.checkbox("バグを自動修正する", value=True, key="pt_autofix")

        if st.button("▶️ 完全自動プレイテスト実行", use_container_width=True,
                     type="primary", key="run_full_pt"):
            with st.spinner("Godotヘッドレス実行中..."):
                try:
                    from engine import run_playtest_auto
                    result = run_playtest_auto(
                        project_path=st.session_state.target_path,
                        scene_path=scene_path,
                        godot_exe=pt_godot or None,
                        timeout=pt_timeout,
                    )
                    st.session_state["pt_result"] = result
                    st.rerun()
                except Exception as e:
                    st.error(f"実行失敗: {e}")

        if "pt_result" in st.session_state:
            r = st.session_state["pt_result"]
            if r["success"]:
                st.success(r.get("report", "✅ テスト完了"))
                if r.get("bugs"):
                    st.warning(f"⚠️ {len(r['bugs'])}件のバグを検出")
                    for b in r["bugs"][:5]:
                        st.caption(f"• {b}")
                    if pt_auto_fix:
                        if st.button("🔧 バグを自動修正", use_container_width=True,
                                     type="primary", key="auto_fix_pt"):
                            bugs_str = "\n".join(r["bugs"])
                            with st.spinner("修正中..."):
                                fix = autonomous_dev(
                                    goal=f"【AIプレイテスト検出バグを修正】\n{bugs_str}",
                                    auto_write=st.session_state.auto_write,
                                    save_path=st.session_state.target_path,
                                    anchor=get_combined_anchor(), max_cycles=2
                                )
                            st.session_state.messages.append({"role":"assistant","content":fix})
                            st.success("✅ 修正を戦略会議室に送りました")
                else:
                    st.success("✅ バグ・詰まりは検出されませんでした")
                st.caption(f"到達距離: {r.get('max_x',0):.0f}px / {r.get('steps',0)}ステップ")
            else:
                st.error(f"テスト失敗: {r.get('error','')}")
                st.caption("Godotがインストールされていないか、プロジェクトパスが違う可能性があります")



    # ─────────────────────────────────────────────────────────
    # ⑥ BGM最適化
    # ─────────────────────────────────────────────────────────
    with gd_tabs[5]:
        st.markdown("### 🎵 BGM最適化提案")
        st.caption("今ある素材のBPMを実測 → ゲームジャンルに合ったテンポに最適化")

        bgm_genre = st.selectbox("ジャンル", ["2daction","roguelike","simulation","towerdefense","3daction"],
                                  format_func=lambda x: {"2daction":"2Dアクション","roguelike":"ローグライク",
                                      "simulation":"シミュレーション","towerdefense":"タワーディフェンス",
                                      "3daction":"3DアクションRPG"}.get(x,x),
                                  key="bgm_genre")

        if st.button("🎵 BGM分析を実行", use_container_width=True, type="primary", key="analyze_bgm"):
            with st.spinner("BGMを解析中..."):
                try:
                    from asset_pipeline import scan_project_assets
                    from build_pipeline import suggest_bgm_tempo
                    manifest = scan_project_assets(st.session_state.target_path)
                    result = suggest_bgm_tempo(manifest, bgm_genre)
                    st.session_state["bgm_analysis"] = result
                    st.rerun()
                except Exception as e:
                    st.error(f"分析失敗: {e}")

        if "bgm_analysis" in st.session_state and st.session_state["bgm_analysis"]:
            r = st.session_state["bgm_analysis"]
            st.markdown(f"#### 🎯 {r['genre']}の理想BPM: **{r['ideal_bpm']}** ({r['feel']})")

            if r["bgm_analysis"]:
                st.markdown("**BGM素材の分析:**")
                for a in r["bgm_analysis"]:
                    bpm_str = f"{a['bpm']}BPM" if a['bpm'] else "BPM不明"
                    st.markdown(f"- `{a['name']}` — {bpm_str} {a['match']}")
                    if a["duration"]:
                        st.caption(f"  長さ: {a['duration']}秒")

            if r["suggestions"]:
                st.markdown("**💡 最適化提案:**")
                for s in r["suggestions"]:
                    st.info(s)

                if st.button("📝 BGM最適化コードを生成", use_container_width=True, key="gen_bgm_code"):
                    goal = f"BGM最適化: {r['genre']}のゲームに合わせてBGM再生速度を{r['ideal_bpm']}BPMに調整するコードを実装する"
                    with st.spinner("生成中..."):
                        code = autonomous_dev(
                            goal=goal,
                            auto_write=st.session_state.auto_write,
                            save_path=st.session_state.target_path,
                            anchor=get_combined_anchor(),
                            max_cycles=1
                        )
                    st.session_state.messages.append({"role": "assistant", "content": code})
                    st.success("✅ 戦略会議室に結果を送りました")

    # ─────────────────────────────────────────────────────────
    # ⑦ 無料API
    # ─────────────────────────────────────────────────────────
    with gd_tabs[6]:
        st.markdown("### 🌐 無料API連携")
        st.caption("Wikipedia・PokeAPI・天気APIなど完全無料のデータをゲームに注入")

        api_col1, api_col2 = st.columns(2)

        with api_col1:
            st.markdown("#### 🗺️ 地名生成（GeoNames風）")
            api_genre = st.selectbox("ジャンル", ["roguelike","simulation","2daction","towerdefense","3daction"],
                                      format_func=lambda x: {"roguelike":"ローグライク","simulation":"シミュレーション",
                                          "2daction":"2Dアクション","towerdefense":"タワーディフェンス","3daction":"3DアクションRPG"}.get(x,x),
                                      key="api_genre")
            if st.button("🗺️ 地名を5個生成", use_container_width=True, key="gen_places"):
                try:
                    from knowledge_api import fetch_place_names
                    places = fetch_place_names(api_genre, 5)
                    st.session_state["generated_places"] = places
                except Exception as e:
                    st.error(str(e))

            if "generated_places" in st.session_state:
                for p in st.session_state["generated_places"]:
                    st.markdown(f"• {p}")
                if st.button("📝 これをゲームマップに使う", key="use_places"):
                    places_str = "\n".join(st.session_state["generated_places"])
                    goal = f"以下の地名をゲームマップ・ダンジョン名として使ったコードを生成する:\n{places_str}"
                    with st.spinner("生成中..."):
                        code = autonomous_dev(goal=goal, auto_write=st.session_state.auto_write,
                                              save_path=st.session_state.target_path,
                                              anchor=get_combined_anchor(), max_cycles=1)
                    st.session_state.messages.append({"role": "assistant", "content": code})
                    st.success("✅ 戦略会議室に送りました")

        with api_col2:
            st.markdown("#### 👾 モンスター生成（PokeAPI）")
            monster_query = st.text_input("モンスター名/ID（空=ランダム）",
                                           value="", key="monster_q",
                                           placeholder="例: pikachu / 1〜151")
            if st.button("👾 モンスターデータ取得", use_container_width=True, key="get_monster"):
                try:
                    from knowledge_api import fetch_monster_data, generate_enemy_from_pokemon
                    name = monster_query.strip() or "random"
                    data = fetch_monster_data(name)
                    if data:
                        st.session_state["monster_data"] = data
                        code = generate_enemy_from_pokemon(
                            name, st.session_state.get("engine_override","godot")
                        )
                        st.session_state["monster_code"] = code
                    else:
                        st.error("取得失敗（PokeAPIに繋がらないか名前が違います）")
                except Exception as e:
                    st.error(str(e))

            if "monster_data" in st.session_state:
                d = st.session_state["monster_data"]
                st.markdown(f"**{d['name']}** ({'/'.join(d.get('types',[]))})")
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("HP", d["enemy_hp"])
                c2.metric("ダメージ", d["enemy_damage"])
                c3.metric("速度", f"{d['enemy_speed']:.1f}×")
                c4.metric("ドロップ", f"{d.get('drop_rate',0):.0%}")
                if d.get("sprite_url"):
                    st.image(d["sprite_url"], width=80)
            if "monster_code" in st.session_state:
                st.code(st.session_state["monster_code"],
                        language="gdscript" if "godot" in st.session_state.get("engine_override","godot") else "python")

        st.divider()

        # Wikipedia知識
        st.markdown("#### 📖 Wikipedia知識注入")
        wiki_q_col, wiki_b_col = st.columns([3,1])
        with wiki_q_col:
            wiki_query = st.text_input("検索キーワード",
                                        placeholder="例: 迷宮 / 都市計画 / 剣士",
                                        key="wiki_q")
        with wiki_b_col:
            st.write("")
            if st.button("🔍 取得", use_container_width=True, key="get_wiki"):
                try:
                    from knowledge_api import fetch_wiki_summary
                    wiki_text = fetch_wiki_summary(wiki_query, "ja", 3)
                    st.session_state["wiki_result"] = wiki_text
                except Exception as e:
                    st.error(str(e))

        if "wiki_result" in st.session_state and st.session_state["wiki_result"]:
            st.info(st.session_state["wiki_result"])
            if st.button("📝 これをゲームの世界観・セリフに使う", key="use_wiki"):
                goal = f"以下の情報をゲームの世界観・NPCセリフ・アイテム説明に組み込む:\n{st.session_state['wiki_result']}"
                with st.spinner("生成中..."):
                    code = autonomous_dev(goal=goal, auto_write=st.session_state.auto_write,
                                          save_path=st.session_state.target_path,
                                          anchor=get_combined_anchor(), max_cycles=1)
                st.session_state.messages.append({"role": "assistant", "content": code})
                st.success("✅ 戦略会議室に送りました")

        # 天気
        st.markdown("#### ⛅ リアル天気 → ゲーム内天候")
        if st.button("☁️ 現在の天気を取得してゲームに反映", use_container_width=True, key="get_weather"):
            try:
                from knowledge_api import fetch_real_weather, weather_to_game_code
                weather = fetch_real_weather(35.6895, 139.6917)  # 東京
                if weather:
                    st.info(
                        f"現在の天気: **{weather['real_weather']}** / "
                        f"気温: {weather['real_temp']}℃ / "
                        f"ゲーム効果: {weather['game_effect']}"
                    )
                    code = weather_to_game_code(
                        weather, st.session_state.get("engine_override","godot")
                    )
                    st.code(code, language="gdscript")
                else:
                    st.warning("天気取得失敗（オフライン環境の可能性）")
            except Exception as e:
                st.error(str(e))

    # ─────────────────────────────────────────────────────────
    # ⑧ 面白さ理論
    # ─────────────────────────────────────────────────────────
    with gd_tabs[7]:
        st.markdown("### 📖 ゲーム面白さ理論")
        st.caption("MDA理論・フロー理論でゲームの「面白さ」を科学する")

        theory_genre = st.selectbox("ジャンル",
            ["2daction","roguelike","simulation","towerdefense","3daction"],
            format_func=lambda x: {"2daction":"2Dアクション","roguelike":"ローグライク",
                "simulation":"シミュレーション","towerdefense":"タワーディフェンス",
                "3daction":"3DアクションRPG"}.get(x,x),
            key="theory_genre")

        try:
            from game_theory import MDA_DATABASE
            mda = MDA_DATABASE.get(theory_genre, MDA_DATABASE["2daction"])

            t1, t2 = st.columns(2)
            with t1:
                st.markdown("#### ⚙️ Mechanics（仕組み）")
                for m in mda["mechanics"]:
                    st.caption(f"• {m}")
                st.markdown("#### 🌊 Dynamics（体験）")
                for d in mda["dynamics"]:
                    st.caption(f"• {d}")

            with t2:
                st.markdown("#### 🎭 Aesthetics（感動）")
                for a in mda["aesthetics"]:
                    st.caption(f"• {a}")
                st.markdown("#### 📈 フロー曲線")
                st.info(mda["flow_curve"])

            st.divider()
            st.markdown("#### 💎 面白さの核心")
            st.success(f"**{mda['fun_principle']}**")

        except Exception as e:
            st.error(f"理論データ読み込み失敗: {e}")

        st.divider()
        st.markdown("#### 🩺 フロー診断")
        flow_desc = st.text_area("ゲームの説明（あなたのゲームについて教えてください）",
                                  height=80,
                                  placeholder="例: プレイヤーがダンジョンを探索してモンスターを倒す。チェックポイントなし。",
                                  key="flow_desc")
        flow_skill = st.select_slider("想定プレイヤー",
                                       ["初心者","中級者","上級者","変態"],
                                       value="中級者", key="flow_skill")
        if st.button("🩺 フロー診断を実行", use_container_width=True, key="run_flow"):
            if flow_desc:
                try:
                    from game_theory import analyze_flow
                    result = analyze_flow(flow_desc, flow_skill)
                    if "⚠️" in result:
                        st.warning(result)
                    else:
                        st.success(result)
                except Exception as e:
                    st.error(str(e))
            else:
                st.warning("ゲームの説明を入力してください")

    # ─────────────────────────────────────────────────────────
    # ⑨ 健康診断
    # ─────────────────────────────────────────────────────────
    with gd_tabs[8]:
        st.markdown("### 🏥 プロジェクト健康診断")
        st.caption("TODO・重複コード・Godot3 API残存・未使用素材を一括スキャン")

        if st.button("🔬 健康診断を実行", use_container_width=True,
                     type="primary", key="run_health"):
            with st.spinner("スキャン中..."):
                try:
                    from health_check import run_health_check, format_report
                    report = run_health_check(st.session_state.target_path)
                    st.session_state["health_report"] = report
                    st.rerun()
                except Exception as e:
                    st.error(f"診断失敗: {e}")

        if "health_report" in st.session_state:
            r = st.session_state["health_report"]
            try:
                from health_check import format_report
                md = format_report(r)
                grade_color = {"A":"success","B":"success","C":"warning","D":"error","F":"error"}.get(r.grade,"info")
                getattr(st, grade_color)(f"スコア: {r.score}/100  グレード: {r.grade}")
                st.markdown(md)

                # 重大問題を自動修正
                crits = [i for i in r.issues if i.severity == "critical"]
                if crits and st.button(f"🔧 重大問題 {len(crits)}件を自動修正",
                                       use_container_width=True, type="primary", key="fix_health"):
                    issues_str = "\n".join(f"- {i.message} ({i.file}:{i.line}) → {i.suggestion}" for i in crits[:5])
                    with st.spinner("修正中..."):
                        fix = autonomous_dev(
                            goal=f"【健康診断の重大問題を修正】\n{issues_str}",
                            auto_write=st.session_state.auto_write,
                            save_path=st.session_state.target_path,
                            anchor=get_combined_anchor(), max_cycles=2
                        )
                    st.session_state.messages.append({"role":"assistant","content":fix})
                    st.success("✅ 修正を戦略会議室に送りました")
            except Exception as e:
                st.error(str(e))

    # ─────────────────────────────────────────────────────────
    # ⑩ バランスAI
    # ─────────────────────────────────────────────────────────
    with gd_tabs[9]:
        st.markdown("### ⚖️ ゲームバランス自動調整AI")
        st.caption("プレイログを読んで「2面が難しすぎる」を自動検出 → パラメータ自動調整")

        ba_col1, ba_col2 = st.columns(2)
        with ba_col1:
            log_path = st.text_input("プレイログJSONパス",
                                     value=os.path.join(st.session_state.target_path, "playtest_log.json"),
                                     key="ba_log_path")
        with ba_col2:
            if st.button("📝 サンプルログ生成（テスト用）", use_container_width=True, key="ba_sample"):
                try:
                    from balance_ai import generate_sample_log
                    p = generate_sample_log(log_path)
                    st.success(f"✅ サンプルログ生成: {p}")
                except Exception as e:
                    st.error(str(e))

        if st.button("⚖️ バランス診断を実行", use_container_width=True,
                     type="primary", key="run_balance"):
            with st.spinner("ログ解析中..."):
                try:
                    from balance_ai import analyze_play_log, format_balance_report
                    report = analyze_play_log(log_path)
                    st.session_state["balance_report"] = report
                    st.rerun()
                except Exception as e:
                    st.error(f"診断失敗: {e}")

        if "balance_report" in st.session_state:
            r = st.session_state["balance_report"]
            try:
                from balance_ai import format_balance_report, apply_adjustments
                st.markdown(format_balance_report(r))

                if r.adjustments:
                    st.divider()
                    target_code = st.text_input("調整対象コードファイル",
                        value=os.path.join(st.session_state.target_path, "constants.gd"),
                        key="ba_target_code")
                    if st.button(f"🔧 {len(r.adjustments)}件のパラメータを自動調整",
                                 use_container_width=True, type="primary", key="apply_balance"):
                        result = apply_adjustments(r.adjustments, target_code)
                        if result["success"]:
                            st.success(result["message"])
                        else:
                            st.warning(result["message"])
                            # コード生成で解決
                            adj_str = "\n".join(
                                f"- {a.param}(Lv{a.level}): {a.old_value:.2f}→{a.new_value:.2f} ({a.reason})"
                                for a in r.adjustments[:5]
                            )
                            with st.spinner("コード生成で調整中..."):
                                fix = autonomous_dev(
                                    goal=f"【バランス自動調整】以下のパラメータを修正:\n{adj_str}",
                                    auto_write=st.session_state.auto_write,
                                    save_path=st.session_state.target_path,
                                    anchor=get_combined_anchor(), max_cycles=1
                                )
                            st.session_state.messages.append({"role":"assistant","content":fix})
                            st.success("✅ 調整コードを戦略会議室に送りました")
            except Exception as e:
                st.error(str(e))

    # ─────────────────────────────────────────────────────────
    # ⑪ エラー辞書（ゲームAIデバッガー）
    # ─────────────────────────────────────────────────────────
    with gd_tabs[10]:
        st.markdown("### 🐛 ゲームAIデバッガー（エラー辞書）")
        st.caption("エラーログをコピペ → 原因・修正場所・修正コードを即答")

        err_col1, err_col2 = st.columns([3, 1])
        with err_col1:
            error_text = st.text_area(
                "エラーログをここに貼り付け",
                height=130, key="err_input",
                placeholder="例:\nParse Error: Unexpected 'KinematicBody2D' in class body\nまたは\nmove_and_slide(velocity, Vector2.UP)"
            )
        with err_col2:
            err_engine = st.selectbox("エンジン", ["auto","godot4","godot3","pygame","unity","python"],
                                      key="err_engine")
            st.write("")
            diagnose_btn = st.button("🔍 診断", use_container_width=True,
                                     type="primary", key="diagnose_btn")

        if diagnose_btn and error_text.strip():
            try:
                from error_dict import diagnose, format_diagnosis
                d = diagnose(error_text, err_engine)
                st.session_state["error_diagnosis"] = d
                st.rerun()
            except Exception as e:
                st.error(str(e))

        if "error_diagnosis" in st.session_state:
            d = st.session_state["error_diagnosis"]
            try:
                from error_dict import format_diagnosis, auto_fix
                st.markdown(format_diagnosis(d))

                if d.matched and d.search_for:
                    st.divider()
                    fix_col1, fix_col2 = st.columns([3,1])
                    with fix_col1:
                        fix_target = st.text_input("修正対象ファイル",
                            placeholder="例: player.gd", key="err_fix_target")
                    with fix_col2:
                        st.write("")
                        if st.button("🔧 自動修正", use_container_width=True, key="err_autofix"):
                            if fix_target:
                                full_path = os.path.join(st.session_state.target_path, fix_target)
                                result = auto_fix(d, full_path)
                                if result["success"]:
                                    st.success(result["message"])
                                else:
                                    st.warning(result["message"])
                            else:
                                st.warning("修正対象ファイルを入力してください")
            except Exception as e:
                st.error(str(e))

        # パターン一覧
        with st.expander("📚 登録済みエラーパターン一覧", expanded=False):
            try:
                from error_dict import get_all_patterns
                patterns = get_all_patterns()
                for p in patterns:
                    icon = {"error":"🔴","warning":"🟡","info":"🟢"}.get(p.severity,"⚪")
                    st.caption(f"{icon} [{p.engine}] **{p.title}**")
            except Exception as e:
                st.error(str(e))

    # ─────────────────────────────────────────────────────────
    # ⑫ マルチエージェント
    # ─────────────────────────────────────────────────────────
    with gd_tabs[11]:
        st.markdown("### 🤖 マルチエージェント並列生成")
        st.caption("設計AI・実装AI・テストAI・ゲームデザインAIが同時並列で動く本来の自律OS")

        ma_goal = st.text_area("実装したい機能・目標",
                               height=80, key="ma_goal",
                               placeholder="例: プレイヤーが壁を滑るウォールスライド機能を実装する")

        ma_col1, ma_col2 = st.columns(2)
        with ma_col1:
            use_architect = st.checkbox("🏗️ 設計AI", value=True, key="ma_arch")
            use_tester    = st.checkbox("🧪 テストAI", value=True, key="ma_test")
        with ma_col2:
            use_coder       = st.checkbox("💻 実装AI", value=True, key="ma_code")
            use_game_design = st.checkbox("🎮 ゲームデザインAI", value=False, key="ma_game")

        if st.button("🚀 マルチエージェント起動", use_container_width=True,
                     type="primary", key="run_ma"):
            if ma_goal.strip():
                agents = []
                if use_architect: agents.append("architect")
                if use_coder:     agents.append("coder")
                if use_tester:    agents.append("tester")
                if use_game_design: agents.append("game_designer")

                with st.spinner(f"エージェント並列実行中... ({', '.join(agents)})"):
                    try:
                        from engine import multi_agent_generate
                        result = multi_agent_generate(
                            desc=ma_goal,
                            anchor=get_combined_anchor(),
                            save_path=st.session_state.target_path,
                            use_agents=tuple(agents),
                        )
                        st.session_state["ma_result"] = result
                        st.rerun()
                    except Exception as e:
                        st.error(f"マルチエージェント失敗: {e}")
            else:
                st.warning("目標を入力してください")

        if "ma_result" in st.session_state:
            r = st.session_state["ma_result"]
            st.caption(r.get("summary",""))

            if r.get("design"):
                with st.expander("🏗️ 設計AI の出力", expanded=False):
                    st.markdown(r["design"][:1500])

            if r.get("code"):
                st.markdown("#### 💻 生成コード")
                lang = "gdscript" if ".gd" in ma_goal.lower() or "godot" in ma_goal.lower() else "python"
                st.code(r["code"], language=lang)

                if st.button("⚡ このコードを保存して適用", use_container_width=True,
                             type="primary", key="apply_ma"):
                    st.session_state.messages.append({"role":"assistant","content":
                        f"## マルチエージェント生成コード\n\n```{lang}\n{r['code']}\n```"})
                    st.success("✅ 戦略会議室に送りました")

            if r.get("test_feedback"):
                with st.expander("🧪 テストAIのフィードバック", expanded=True):
                    if "重大" in r["test_feedback"] or "クラッシュ" in r["test_feedback"]:
                        st.warning(r["test_feedback"][:800])
                    else:
                        st.success(r["test_feedback"][:800])

            if r.get("game_feedback"):
                with st.expander("🎮 ゲームデザインAIの評価", expanded=False):
                    st.markdown(r["game_feedback"][:800])

            if r.get("errors"):
                with st.expander("⚠️ エラー詳細", expanded=False):
                    for agent, err in r["errors"].items():
                        st.error(f"{agent}: {err}")

    # ─────────────────────────────────────────────────────────
    # ⑬ ペアプログラマー
    # ─────────────────────────────────────────────────────────
    with gd_tabs[12]:
        st.markdown("### 🤝 AIペアプログラマーモード")
        st.caption("設計→承認→実装→レビュー→修正 の対話型開発。Cursor的な体験。")

        # セッション管理
        if "pair_session" not in st.session_state:
            st.session_state.pair_session = None
        if "pair_response" not in st.session_state:
            st.session_state.pair_response = None

        if st.session_state.pair_session is None:
            # 新規セッション開始
            pair_goal = st.text_area("実装したい機能", height=80, key="pair_goal",
                placeholder="例: プレイヤーが壁を滑るウォールスライド機能")
            if st.button("🤝 ペアプログラミング開始", use_container_width=True,
                         type="primary", key="start_pair"):
                if pair_goal.strip():
                    try:
                        from pair_programmer import PairSession
                        session = PairSession.start(
                            goal=pair_goal,
                            anchor=get_combined_anchor(),
                            save_path=st.session_state.target_path,
                            model=MODELS.get("coder","qwen2.5-coder:32b"),
                        )
                        # 最初のレスポンス（設計提案）
                        response = session.respond()
                        st.session_state.pair_session  = session
                        st.session_state.pair_response = response
                        st.rerun()
                    except Exception as e:
                        st.error(f"起動失敗: {e}")
                else:
                    st.warning("実装したい機能を入力してください")
        else:
            session  = st.session_state.pair_session
            response = st.session_state.pair_response
            state    = session.get_state()

            # フェーズ表示
            st.info(f"**{state['phase_label']}** — ターン {state['turns']} / ゴール: {state['goal'][:50]}")

            if response:
                st.markdown(response.message)
                if response.code:
                    lang = "gdscript" if ".gd" in state["goal"].lower() else "python"
                    st.code(response.code, language=lang)

            # アクションボタン
            if response and response.actions and not response.is_done:
                st.markdown("**次のアクション:**")
                act_cols = st.columns(len(response.actions))
                for i, action in enumerate(response.actions):
                    with act_cols[i]:
                        if st.button(action, use_container_width=True,
                                     key=f"pair_act_{i}_{state['turns']}"):
                            action_map = {
                                "✅ この方針で実装開始": "approve",
                                "⏭️ 直接実装して": "skip",
                                "🔍 AIレビューを実行": "review",
                                "✅ このまま保存": "save",
                                "✅ 保存して完了": "save",
                                "✅ 問題なし・このまま保存": "save",
                                "🔧 指摘を自動修正": "refine",
                                "🔍 もう一度レビュー": "review",
                            }
                            act = action_map.get(action, "")
                            new_resp = session.respond(action=act)
                            st.session_state.pair_response = new_resp
                            if new_resp.is_done and new_resp.code:
                                # 完成コードを保存
                                if st.session_state.auto_write:
                                    import re as _pre
                                    ext  = ".gd" if ".gd" in state["goal"].lower() else ".py"
                                    name = _pre.sub(r"\W+","_",state["goal"][:20]) + ext
                                    fp   = os.path.join(st.session_state.target_path, name)
                                    with open(fp,"w",encoding="utf-8") as f:
                                        f.write(new_resp.code)
                                    st.success(f"✅ 保存: {fp}")
                                st.session_state.messages.append({
                                    "role":"assistant",
                                    "content":f"ペアプログラミング完了:\n```\n{new_resp.code[:2000]}\n```"
                                })
                            st.rerun()

            # カスタム入力
            pair_input = st.text_input("カスタム入力（方針の修正など）", key="pair_input")
            if st.button("送信", key="pair_submit"):
                new_resp = session.respond(pair_input)
                st.session_state.pair_response = new_resp
                st.rerun()

            if st.button("🔄 セッションをリセット", key="pair_reset"):
                st.session_state.pair_session  = None
                st.session_state.pair_response = None
                st.rerun()

    # ─────────────────────────────────────────────────────────
    # ⑭ 依存グラフ視覚化 + コード進化タイムライン
    # ─────────────────────────────────────────────────────────
    with gd_tabs[13]:
        st.markdown("### 🕸️ 依存グラフ & コード進化")

        viz_tab1, viz_tab2 = st.tabs(["🕸️ 依存グラフ", "📈 進化タイムライン"])

        with viz_tab1:
            st.caption("ファイル間のimport/preload依存関係をグラフで表示")
            if st.button("🔄 依存グラフを生成", use_container_width=True,
                         type="primary", key="gen_dep_graph"):
                with st.spinner("解析中..."):
                    try:
                        from viz import build_dep_graph_svg
                        svg = build_dep_graph_svg(st.session_state.target_path)
                        st.session_state["dep_graph_svg"] = svg
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            if "dep_graph_svg" in st.session_state:
                st.markdown(
                    st.session_state["dep_graph_svg"],
                    unsafe_allow_html=True
                )
                # 影響範囲の説明
                st.caption("🔵 Python  🟢 GDScript  🟣 C#  → エッジはimport/preload依存")

        with viz_tab2:
            st.caption("Gitコミット履歴から追加/削除行数を可視化")
            evo_n = st.slider("表示コミット数", 10, 50, 20, key="evo_n")
            if st.button("📈 進化グラフを生成", use_container_width=True,
                         type="primary", key="gen_evo"):
                with st.spinner("Git履歴取得中..."):
                    try:
                        from viz import get_git_timeline, build_evolution_svg
                        timeline = get_git_timeline(st.session_state.target_path, evo_n)
                        if timeline:
                            svg = build_evolution_svg(timeline)
                            st.session_state["evo_svg"]      = svg
                            st.session_state["evo_timeline"] = timeline
                            st.rerun()
                        else:
                            st.warning("Gitの履歴が見つかりません")
                    except Exception as e:
                        st.error(str(e))

            if "evo_svg" in st.session_state:
                st.markdown(st.session_state["evo_svg"], unsafe_allow_html=True)

            if "evo_timeline" in st.session_state:
                tl = st.session_state["evo_timeline"]
                with st.expander(f"📋 コミット一覧 ({len(tl)}件)", expanded=False):
                    for e in tl:
                        net = e["net"]
                        sign = "+" if net >= 0 else ""
                        st.caption(
                            f"`{e['hash']}` {e['date']} {sign}{net}行 — {e['msg']}"
                        )

    # ─────────────────────────────────────────────────────────
    # ⑮ プレイ解析（スクショ/動画 → AI評価）
    # ─────────────────────────────────────────────────────────
    with gd_tabs[14]:
        st.markdown("### 📹 ゲームプレイAI解析")
        st.caption("スクリーンショットや録画を見て「はまり・いい動き・悪い動き・キャラ・アイテム・シナリオ・舞台」を総合評価")

        pa_col1, pa_col2 = st.columns([2,1])
        with pa_col1:
            uploaded_media = st.file_uploader(
                "スクリーンショット または 動画をアップロード",
                type=["png","jpg","jpeg","webp","mp4","mov","avi"],
                key="gameplay_upload"
            )
        with pa_col2:
            pa_game_type = st.text_input("ゲームタイプ", value="2Dアクション", key="pa_game_type")
            pa_engine    = st.selectbox("エンジン", ["Godot4","Godot3","Pygame","Unity"], key="pa_engine")

        if uploaded_media:
            is_video = uploaded_media.type.startswith("video/")
            label    = "🎬 動画を解析" if is_video else "🖼️ スクリーンショットを解析"
            if st.button(label, use_container_width=True, type="primary", key="run_pa"):
                with st.spinner("AIが解析中... (ビジョンモデルが必要です)"):
                    try:
                        from gameplay_analyzer import (
                            analyze_from_bytes, analyze_video_frames, format_analysis
                        )
                        context = {
                            "game_type":   pa_game_type,
                            "game_anchor": st.session_state.game_anchor,
                            "engine":      pa_engine,
                        }
                        media_bytes = uploaded_media.read()

                        if is_video:
                            # 動画: 一時保存してフレーム解析
                            import tempfile
                            ext = "." + uploaded_media.name.split(".")[-1]
                            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                                tmp.write(media_bytes)
                                tmp_path = tmp.name
                            result = analyze_video_frames(tmp_path, context)
                            try: os.unlink(tmp_path)
                            except: pass
                        else:
                            result = analyze_from_bytes(
                                media_bytes, context, uploaded_media.name
                            )

                        st.session_state["pa_result"] = result
                        st.rerun()
                    except Exception as e:
                        st.error(f"解析失敗: {e}")

        if "pa_result" in st.session_state:
            r = st.session_state["pa_result"]
            try:
                from gameplay_analyzer import format_analysis
                if r.success:
                    # スコアメトリクス
                    m1,m2,m3,m4 = st.columns(4)
                    m1.metric("面白さ",  f"{r.score_fun:.1f}/10")
                    m2.metric("操作感",  f"{r.score_feel:.1f}/10")
                    m3.metric("ビジュアル",f"{r.score_visual:.1f}/10")
                    m4.metric("バランス",f"{r.score_balance:.1f}/10")

                    st.markdown(format_analysis(r))

                    # 改善提案をBlackwellに送る
                    if r.improvements and st.button(
                        "🔧 改善提案をBlackwellに実装させる",
                        use_container_width=True, type="primary", key="pa_to_bw"
                    ):
                        imps_str = "\n".join(f"{i+1}. {p}" for i,p in enumerate(r.improvements))
                        with st.spinner("実装中..."):
                            fix = autonomous_dev(
                                goal=f"【プレイ解析の改善提案を実装】\n{imps_str}",
                                auto_write=st.session_state.auto_write,
                                save_path=st.session_state.target_path,
                                anchor=get_combined_anchor(), max_cycles=2
                            )
                        st.session_state.messages.append({"role":"assistant","content":fix})
                        st.success("✅ 戦略会議室に送りました")
                else:
                    st.error(r.error)
                    if "llava" in r.error.lower() or "ビジョン" in r.error:
                        st.code("ollama pull llava-llama3", language="bash")
            except Exception as e:
                st.error(str(e))

    # ─────────────────────────────────────────────────────────
    # ⑯ 自動ドキュメント生成
    # ─────────────────────────────────────────────────────────
    with gd_tabs[15]:
        st.markdown("### 📄 自動ドキュメント生成")
        st.caption("コードから日本語のREADME・設計書・関数説明を自動生成")

        dg_tab1, dg_tab2, dg_tab3 = st.tabs(["📝 README", "🏗️ 設計書", "🔤 関数ドキュメント"])

        with dg_tab1:
            if st.button("📝 README.md を自動生成", use_container_width=True,
                         type="primary", key="gen_readme"):
                with st.spinner("生成中..."):
                    try:
                        from doc_gen import generate_readme
                        readme = generate_readme(
                            st.session_state.target_path, st.session_state.game_anchor
                        )
                        st.session_state["generated_readme"] = readme
                        if st.session_state.auto_write:
                            rp = os.path.join(st.session_state.target_path, "README.md")
                            with open(rp,"w",encoding="utf-8") as f:
                                f.write(readme)
                            st.success(f"✅ README.md を保存しました")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            if "generated_readme" in st.session_state:
                st.markdown(st.session_state["generated_readme"])

        with dg_tab2:
            if st.button("🏗️ 設計書を自動生成", use_container_width=True,
                         type="primary", key="gen_design"):
                with st.spinner("生成中..."):
                    try:
                        from doc_gen import generate_design_doc
                        doc = generate_design_doc(
                            st.session_state.target_path, st.session_state.game_anchor
                        )
                        st.session_state["generated_design"] = doc
                        if st.session_state.auto_write:
                            dp = os.path.join(st.session_state.target_path, "DESIGN.md")
                            with open(dp,"w",encoding="utf-8") as f:
                                f.write(doc)
                            st.success("✅ DESIGN.md を保存しました")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            if "generated_design" in st.session_state:
                st.markdown(st.session_state["generated_design"])

        with dg_tab3:
            dg_file = st.text_input("ドキュメントを生成するファイル",
                placeholder="例: player.gd", key="dg_file")
            gdoc_col1, gdoc_col2 = st.columns(2)
            with gdoc_col1:
                if st.button("🔤 関数説明を生成", use_container_width=True, key="gen_funcdoc"):
                    if dg_file:
                        fp = os.path.join(st.session_state.target_path, dg_file)
                        with st.spinner("生成中..."):
                            try:
                                from doc_gen import generate_function_docs
                                doc = generate_function_docs(fp)
                                st.session_state["generated_funcdoc"] = doc
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))
            with gdoc_col2:
                if st.button("💉 GDDoc注入", use_container_width=True, key="inject_gdoc"):
                    if dg_file and dg_file.endswith(".gd"):
                        fp = os.path.join(st.session_state.target_path, dg_file)
                        with st.spinner("doc_string注入中..."):
                            try:
                                from doc_gen import inject_gdoc_strings
                                new_code = inject_gdoc_strings(fp)
                                if new_code:
                                    with open(fp,"w",encoding="utf-8") as f:
                                        f.write(new_code)
                                    st.success("✅ ## doc_stringを注入しました")
                                    st.code(new_code[:500], language="gdscript")
                            except Exception as e:
                                st.error(str(e))
            if "generated_funcdoc" in st.session_state:
                st.markdown(st.session_state["generated_funcdoc"][:2000])

    # ─────────────────────────────────────────────────────────
    # 健康診断タブに自動ループボタンを追加（gd_tabs[8]の更新版）
    # ─────────────────────────────────────────────────────────
    # ※ Streamlitではwithブロック外からタブの中身を追加できないため
    # 　 健康診断タブに自動ループは次回起動から反映

    # ─────────────────────────────────────────────────────────
    # ⑰ タスク自動分解
    # ─────────────────────────────────────────────────────────
    with gd_tabs[16]:
        st.markdown("### 📋 タスク自動分解")
        st.caption("「ローグライクを作りたい」と書くだけで実装タスクリストを自動生成・自動実行")

        plan_path = os.path.join(st.session_state.target_path, ".blackwell_taskplan.json")

        # 既存プランの読み込み
        if "task_plan" not in st.session_state:
            try:
                from task_decomposer import TaskPlan
                loaded_plan = TaskPlan.load(plan_path)
                st.session_state["task_plan"] = loaded_plan
            except Exception:
                st.session_state["task_plan"] = None

        plan = st.session_state.get("task_plan")

        if plan is None:
            td_col1, td_col2 = st.columns([3,1])
            with td_col1:
                td_goal = st.text_area("作りたいゲーム・機能を自由に書いてください",
                    height=80, key="td_goal",
                    placeholder="例: ローグライクRPGを作りたい。ランダムダンジョン・アイテム収集・ターン制戦闘が欲しい")
            with td_col2:
                td_engine = st.selectbox("エンジン", ["godot4","godot3","pygame"], key="td_engine")
                td_genre  = st.selectbox("ジャンル（空=自動判定）",
                    ["","2daction","roguelike","simulation","towerdefense","pygame_2d"], key="td_genre")

            if st.button("🧠 タスクリストを自動生成", use_container_width=True,
                         type="primary", key="gen_tasks"):
                if td_goal.strip():
                    with st.spinner("AIがタスクを分解中..."):
                        try:
                            from task_decomposer import decompose
                            new_plan = decompose(
                                goal=td_goal, anchor=get_combined_anchor(),
                                engine=td_engine, genre=td_genre, use_ai=True
                            )
                            new_plan.save(plan_path)
                            st.session_state["task_plan"] = new_plan
                            st.rerun()
                        except Exception as e:
                            st.error(f"分解失敗: {e}")
                else:
                    st.warning("ゴールを入力してください")
        else:
            # プラン表示
            st.success(f"**ゴール:** {plan.goal}")
            prog = plan.progress_pct()
            st.progress(prog / 100, text=f"{prog}% ({plan.done_count()}/{plan.total()}タスク完了)")

            # タスク一覧
            for task in sorted(plan.tasks, key=lambda t: t.priority):
                icon = {"todo":"⬜","running":"🔄","done":"✅","failed":"❌"}.get(task.status,"⬜")
                col1, col2 = st.columns([5,1])
                with col1:
                    st.markdown(f"{icon} **{task.title}** `{task.file}` (優先度:{task.priority})")
                    if task.status == "failed":
                        st.caption(f"エラー: {task.result[:100]}")
                with col2:
                    if task.status == "todo" and st.button("▶️", key=f"run_task_{task.id}"):
                        task.status = "running"
                        plan.save(plan_path)
                        with st.spinner(f"{task.title} 実装中..."):
                            try:
                                result = autonomous_dev(
                                    goal=task.desc,
                                    auto_write=st.session_state.auto_write,
                                    save_path=st.session_state.target_path,
                                    anchor=get_combined_anchor(), max_cycles=2,
                                )
                                task.status = "done"
                                task.result = result[:300]
                            except Exception as e:
                                task.status = "failed"
                                task.result = str(e)
                        plan.save(plan_path)
                        st.rerun()

            st.divider()
            auto_col1, auto_col2 = st.columns(2)
            with auto_col1:
                if st.button("🚀 未完了タスクを全て自動実行",
                             use_container_width=True, type="primary", key="run_all_tasks"):
                    nexts = plan.next_tasks()
                    if nexts:
                        for task in nexts[:3]:  # 最大3タスク同時
                            task.status = "running"
                        plan.save(plan_path)
                        st.rerun()
            with auto_col2:
                if st.button("🗑️ プランをリセット", use_container_width=True, key="reset_plan"):
                    st.session_state["task_plan"] = None
                    if os.path.exists(plan_path):
                        os.remove(plan_path)
                    st.rerun()

    # ─────────────────────────────────────────────────────────
    # ⑱ 感情グラフ
    # ─────────────────────────────────────────────────────────
    with gd_tabs[17]:
        st.markdown("### 💗 ゲームの感情グラフ")
        st.caption("プレイログから「興奮・不安・退屈・フロー」の感情曲線を時系列で可視化")

        eg_col1, eg_col2 = st.columns([3,1])
        with eg_col1:
            eg_log = st.text_input("プレイログJSONパス",
                value=os.path.join(st.session_state.target_path, "playtest_log.json"),
                key="eg_log")
        with eg_col2:
            if st.button("🎮 サンプルで試す", use_container_width=True, key="eg_sample"):
                try:
                    from emotion_graph import generate_sample_events, compute_emotion_curve, build_emotion_svg
                    events = generate_sample_events()
                    data = compute_emotion_curve(events)
                    st.session_state["emotion_data"] = data
                    st.session_state["emotion_svg"]  = build_emotion_svg(data)
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        if st.button("📊 感情グラフを生成", use_container_width=True,
                     type="primary", key="gen_emotion"):
            with st.spinner("解析中..."):
                try:
                    from emotion_graph import (
                        parse_log_to_events, compute_emotion_curve, build_emotion_svg
                    )
                    events = parse_log_to_events(eg_log)
                    if not events:
                        st.warning("イベントデータが見つかりません。サンプルで試してください。")
                    else:
                        data = compute_emotion_curve(events)
                        st.session_state["emotion_data"] = data
                        st.session_state["emotion_svg"]  = build_emotion_svg(data)
                        st.rerun()
                except Exception as e:
                    st.error(str(e))

        if "emotion_svg" in st.session_state:
            st.markdown(st.session_state["emotion_svg"], unsafe_allow_html=True)

        if "emotion_data" in st.session_state:
            data = st.session_state["emotion_data"]
            m1,m2,m3 = st.columns(3)
            m1.metric("フロー率", f"{data.flow_ratio:.0%}")
            m2.metric("感情ピーク(興奮)", f"{data.peak_excitement_t:.0f}秒")
            m3.metric("感情ピーク(不安)", f"{data.peak_anxiety_t:.0f}秒")

            if data.problem_zones:
                st.markdown("#### ⚠️ 問題ゾーン")
                for zone in data.problem_zones:
                    ztype_label = {"too_hard":"難しすぎ","too_easy":"簡単すぎ","boredom":"退屈"}.get(zone.zone_type,"問題")
                    st.warning(f"**{ztype_label}** ({zone.start_t:.0f}〜{zone.end_t:.0f}秒): {zone.suggestion}")

                if st.button("🔧 問題ゾーンをBlackwellに修正させる",
                             use_container_width=True, type="primary", key="fix_emotion"):
                    zones_str = "\n".join(
                        f"- {z.zone_type} ({z.start_t:.0f}〜{z.end_t:.0f}秒): {z.suggestion}"
                        for z in data.problem_zones
                    )
                    with st.spinner("修正中..."):
                        fix = autonomous_dev(
                            goal=f"【感情グラフが示す問題ゾーンを修正】\n{zones_str}",
                            auto_write=st.session_state.auto_write,
                            save_path=st.session_state.target_path,
                            anchor=get_combined_anchor(), max_cycles=2
                        )
                    st.session_state.messages.append({"role":"assistant","content":fix})
                    st.success("✅ 修正を戦略会議室に送りました")

    # ─────────────────────────────────────────────────────────
    # ⑲ 自己改善
    # ─────────────────────────────────────────────────────────
    with gd_tabs[18]:
        st.markdown("### 🔁 Blackwell自己改善")
        st.caption("Blackwell自身がengine.pyを分析してボトルネック・問題を発見し改善コードを生成する")

        si_engine_path = st.text_input("分析対象ファイル",
            value="./engine.py", key="si_path")

        if st.button("🔬 自己分析を実行", use_container_width=True,
                     type="primary", key="run_self_analyze"):
            with st.spinner("自己分析中..."):
                try:
                    from self_improver import analyze_self, generate_proposals
                    problems = analyze_self(si_engine_path)
                    st.session_state["si_problems"]  = problems
                    if problems:
                        with st.spinner(f"{len(problems)}件の問題から改善提案を生成中..."):
                            proposals = generate_proposals(problems, si_engine_path)
                            st.session_state["si_proposals"] = proposals
                    st.rerun()
                except Exception as e:
                    st.error(f"分析失敗: {e}")

        if "si_problems" in st.session_state:
            probs = st.session_state["si_problems"]
            if probs:
                st.warning(f"**{len(probs)}件の改善機会を検出**")
                for p in probs:
                    impact_icon = {"high":"🔴","medium":"🟡","low":"🟢"}.get(p.get("impact",""),"⚪")
                    st.caption(f"{impact_icon} {p['type']}: {str(p)[:80]}")
            else:
                st.success("✅ 問題は検出されませんでした")

        if "si_proposals" in st.session_state:
            proposals = st.session_state["si_proposals"]
            st.markdown(f"#### 🔧 改善提案 ({len(proposals)}件)")
            for i, prop in enumerate(proposals):
                with st.expander(f"{i+1}. {prop.title} [{prop.risk_level}]", expanded=i==0):
                    try:
                        from self_improver import format_proposal, apply_proposal
                        st.markdown(format_proposal(prop))
                        si_apply_col1, si_apply_col2 = st.columns(2)
                        with si_apply_col1:
                            if prop.risk_level != "high" and st.button(
                                f"✅ 適用 ({prop.risk_level}リスク)",
                                use_container_width=True, key=f"apply_si_{i}"
                            ):
                                result = apply_proposal(prop)
                                if result["success"]:
                                    st.success(result["message"])
                                else:
                                    st.error(result["reason"])
                        with si_apply_col2:
                            if st.button("❌ 却下", use_container_width=True, key=f"reject_si_{i}"):
                                prop.status = "rejected"
                                st.rerun()
                    except Exception as e:
                        st.error(str(e))

    # ─────────────────────────────────────────────────────────
    # ⑳ Watchdog（監視・夜間バッチ）
    # ─────────────────────────────────────────────────────────
    with gd_tabs[19]:
        st.markdown("### 🖥️ Watchdog 監視センター")
        st.caption("自動再起動 / システム状態 / 夜間バッチ（AIが夢を見る）")

        wd_tab1, wd_tab2, wd_tab3 = st.tabs(["📊 システム状態", "🌙 夜間バッチ", "📜 ログ"])

        with wd_tab1:
            if st.button("🔄 状態を取得", use_container_width=True, key="wd_status"):
                try:
                    from bw_watchdog import get_system_status
                    status = get_system_status()
                    st.session_state["wd_status"] = status
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
            if "wd_status" in st.session_state:
                s = st.session_state["wd_status"]
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("CPU", f"{s.get('cpu_pct','?')}%")
                c2.metric("RAM", f"{s.get('ram_pct','?')}%")
                c3.metric("空きDisk", f"{s.get('disk_free_gb',0):.1f}GB")
                c4.metric("Ollama応答", f"{s.get('ollama_ms','?')}ms" if s.get('ollama_ok') else "❌")

            st.divider()
            st.caption("自動再起動Watchdogの起動方法:")
            st.code("python bw_watchdog.py --app app.py", language="bash")

            # セッション情報
            st.markdown("#### 💾 セッション状態")
            try:
                from session_restore import get_session_info, clear_session
                info = get_session_info()
                if info["exists"]:
                    st.success(f"保存済みセッション: {info.get('saved_at','?')[:19]} / {info.get('messages',0)}メッセージ")
                    if st.button("🗑️ セッションをクリア", key="clear_session"):
                        clear_session()
                        st.success("クリアしました")
                else:
                    st.info("保存済みセッションはありません")
            except Exception as e:
                st.error(str(e))

        with wd_tab2:
            st.caption("眠っている間にBlackwellが自律的に振り返り・改善案を生成します")

            if st.button("🌙 今すぐ夜間バッチを実行", use_container_width=True,
                         type="primary", key="run_dream"):
                with st.spinner("Blackwellが夢を見ています...（1〜2分）"):
                    try:
                        from bw_watchdog import run_dream_batch
                        dreams = run_dream_batch(st.session_state.target_path)
                        st.session_state["latest_dreams"] = dreams.get("suggestions", [])
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            # 最新の夢を表示
            dreams = st.session_state.get("latest_dreams")
            if not dreams:
                try:
                    from bw_watchdog import get_latest_dreams
                    dreams = get_latest_dreams()
                    st.session_state["latest_dreams"] = dreams
                except Exception:
                    pass

            if dreams:
                st.markdown("#### 🌙 Blackwellからの提案（夜間バッチ）")
                for i, sug in enumerate(dreams, 1):
                    with st.expander(f"{i}. {sug.get('title','提案')}", expanded=i==1):
                        st.markdown(f"**理由:** {sug.get('reason','')}")
                        st.markdown(f"**アクション:** {sug.get('action','')}")
                        if st.button(f"▶️ この提案を実装", use_container_width=True,
                                     key=f"impl_dream_{i}"):
                            with st.spinner("実装中..."):
                                fix = autonomous_dev(
                                    goal=f"【夜間バッチ提案を実装】{sug.get('action','')}",
                                    auto_write=st.session_state.auto_write,
                                    save_path=st.session_state.target_path,
                                    anchor=get_combined_anchor(), max_cycles=2
                                )
                            st.session_state.messages.append({"role":"assistant","content":fix})
                            st.success("✅ 戦略会議室に送りました")

        with wd_tab3:
            try:
                from bw_watchdog import get_watchdog_log
                log_lines = get_watchdog_log(30)
                if log_lines:
                    st.code("".join(log_lines), language="text")
                else:
                    st.info("ログがありません（watchdog.pyを起動すると記録されます）")
            except Exception as e:
                st.info(f"ログ読み込み: {e}")

    # ─────────────────────────────────────────────────────────
    # ㉑ プロジェクト生成テンプレート
    # ─────────────────────────────────────────────────────────
    with gd_tabs[20]:
        st.markdown("### 🏗️ プロジェクト生成テンプレート")
        st.caption("ジャンルを選ぶだけで正しいフォルダ構成・定数ファイル・基本コードを一括生成")

        try:
            from project_templates import get_templates, create_project
            templates = get_templates()

            pt_col1, pt_col2 = st.columns([2,1])
            with pt_col1:
                pt_name = st.text_input("プロジェクト名", value="MyGame", key="pt_name")
                template_options = {t["label"]: t["key"] for t in templates}
                pt_label = st.selectbox("テンプレート", list(template_options.keys()), key="pt_label")
                pt_key   = template_options[pt_label]
            with pt_col2:
                pt_output = st.text_input("出力先フォルダ",
                    value=os.path.dirname(st.session_state.target_path) or "./",
                    key="pt_output")

            # テンプレート内容プレビュー
            selected = next((t for t in templates if t["key"] == pt_key), None)
            if selected:
                st.caption(f"生成される: {selected['file_count']}ファイル | エンジン: {selected['engine']}")

            if st.button("🏗️ プロジェクトを生成", use_container_width=True,
                         type="primary", key="create_proj"):
                if pt_name.strip():
                    with st.spinner("生成中..."):
                        result = create_project(pt_name, pt_key, pt_output)
                    if result["success"]:
                        st.success(f"✅ {result['file_count']}ファイルを生成しました: `{result['path']}`")
                        # 生成したプロジェクトをターゲットパスに設定
                        if st.button("📁 このプロジェクトをBlackwellのターゲットに設定",
                                     use_container_width=True, key="set_pt_target"):
                            st.session_state.target_path = result["path"]
                            st.rerun()
                        with st.expander("生成されたファイル一覧", expanded=False):
                            for fp in result["created_files"]:
                                st.caption(f"• {os.path.relpath(fp, result['path'])}")
                    else:
                        st.error(f"生成失敗: {result.get('error','不明')}")
                else:
                    st.warning("プロジェクト名を入力してください")

        except Exception as e:
            st.error(f"テンプレート読み込み失敗: {e}")

# ─────────────────────────────────────────────────────────
# TAB 21: 📜 契約マップ（Phase 2）
# ─────────────────────────────────────────────────────────
with gd_tabs[21]:
    st.markdown("### 📜 契約マップ")
    st.caption("ファイル間のAPI依存関係。どれを変えると何が壊れるかが一目でわかる。")

    try:
        from blackwell_history import get_all_contracts_summary, get_stats

        _bp = st.session_state.get("target_path", "./")
        _contracts = get_all_contracts_summary(_bp)
        _stats = get_stats(_bp)

        # 統計
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("総タスク", _stats.get("total_events", 0))
        c2.metric("成功率", f"{_stats.get('success_rate', 0)}%")
        c3.metric("平均スコア", f"{_stats.get('avg_score', 0)}/100")
        c4.metric("契約数", _stats.get("total_contracts", 0))

        st.divider()

        if not _contracts:
            st.info("まだ契約が記録されていません。\nコードを生成すると自動的に記録されます。")
        else:
            st.markdown(f"**{len(_contracts)}件の依存関係を検出**")
            for c in _contracts:
                consumers_str = "、".join(c["consumers"])
                risk = "🔴 高" if len(c["consumers"]) >= 3 else "🟡 中" if len(c["consumers"]) >= 2 else "🟢 低"
                with st.expander(
                    f"{risk}  `{c['provider']}` → `{c['function']}()`  "
                    f"← {len(c['consumers'])}ファイルが依存",
                    expanded=False
                ):
                    st.code(c["signature"], language="python")
                    st.caption(f"依存ファイル: {consumers_str}")
                    st.caption("⚠️ このシグネチャを変更する場合は上記全ファイルも修正が必要")

    except ImportError:
        st.error("blackwell_history.py が見つかりません")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# TAB 22: ⏱️ 開発履歴（Phase 2）
# ─────────────────────────────────────────────────────────
with gd_tabs[22]:
    st.markdown("### ⏱️ 開発履歴")
    st.caption("全ての成功・失敗・エラーを記録。同じミスを二度と繰り返さない。")

    try:
        from blackwell_history import get_timeline_summary, add_milestone

        _bp = st.session_state.get("target_path", "./")

        # 節目を記録
        with st.expander("🏆 節目を記録", expanded=False):
            _ms_title = st.text_input("タイトル", placeholder="例: ボス戦完成！", key="ms_title")
            _ms_note  = st.text_area("メモ", height=60, key="ms_note")
            if st.button("記録する", key="ms_record_btn"):
                if _ms_title.strip():
                    add_milestone(_bp, _ms_title, _ms_note)
                    st.success("✅ 節目を記録しました")
                    st.rerun()

        st.divider()

        # タイムライン表示
        _timeline = get_timeline_summary(_bp, n=30)
        if not _timeline:
            st.info("まだ履歴がありません。\nコードを生成すると自動記録されます。")
        else:
            st.markdown(f"**直近{len(_timeline)}件**")
            for ev in _timeline:
                with st.container(border=True):
                    col_i, col_d = st.columns([1, 8])
                    with col_i:
                        st.markdown(f"## {ev['icon']}")
                    with col_d:
                        st.caption(ev["timestamp"])
                        if ev["file"]:
                            st.markdown(f"**`{ev['file']}`** — {ev['task']}")
                        else:
                            st.markdown(f"**{ev['task']}**")
                        if ev["detail"]:
                            st.caption(ev["detail"])
                        if ev["score"]:
                            st.caption(f"スコア: {ev['score']}/100")

    except ImportError:
        st.error("blackwell_history.py が見つかりません")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# TAB 23: 🔮 リスク予測（Phase 3）
# ─────────────────────────────────────────────────────────
with gd_tabs[23]:
    st.markdown("### 🔮 リスク予測")
    st.caption("コードを生成するたびに将来の問題を予測・記録。問題が起きる前に気づく。")

    try:
        from blackwell_prediction import get_all_predictions, get_prediction_stats, resolve_prediction

        _bp = st.session_state.get("target_path", "./")
        _pstats = get_prediction_stats(_bp)

        # 統計
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("未解決リスク", _pstats.get("open", 0))
        c2.metric("高リスク", _pstats.get("high", 0), delta="要対応" if _pstats.get("high", 0) > 0 else None)
        c3.metric("解決済み", _pstats.get("resolved", 0))
        c4.metric("総予測数", _pstats.get("total", 0))

        st.divider()

        _preds = get_all_predictions(_bp)
        if not _preds:
            st.info("まだ予測がありません。\nコードを生成すると自動的にリスク分析が行われます。")
        else:
            icons    = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            for pred in _preds:
                icon = icons.get(pred["severity"], "⚪")
                with st.container(border=True):
                    col_i, col_d = st.columns([1, 9])
                    with col_i:
                        st.markdown(f"## {icon}")
                    with col_d:
                        st.markdown(f"**`{pred['file']}`** — {pred['description']}")
                        st.caption(f"📍 発生条件: {pred['trigger']}")
                        st.caption(f"💡 対策: {pred['suggestion']}")
                        st.caption(f"予測日時: {pred['predicted_at']}")
                        if st.button("✅ 解決済みにする",
                                     key=f"resolve_{pred['file']}_{pred['description'][:20]}"):
                            resolve_prediction(_bp, pred["file"], pred["description"][:30])
                            st.success("解決済みにしました")
                            st.rerun()

    except ImportError:
        st.error("blackwell_prediction.py が見つかりません")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# TAB 24: ⚡ 並列シミュ（Phase 3）
# ─────────────────────────────────────────────────────────
with gd_tabs[24]:
    st.markdown("### ⚡ 並列シミュレーション履歴")
    st.caption("3案並列生成のたびに「なぜその案を選んだか・他案がダメだった理由」を記録。同じ失敗を繰り返さない。")

    try:
        from blackwell_prediction import get_parallel_history, get_parallel_stats

        _bp = st.session_state.get("target_path", "./")
        _pstats = get_parallel_stats(_bp)

        # 統計
        c1, c2, c3 = st.columns(3)
        c1.metric("総シミュ回数", _pstats.get("total_simulations", 0))
        wins = _pstats.get("path_wins", {})
        c2.metric("最多採用パス", f"Path {_pstats.get('most_reliable', '?')}")
        c3.metric("各パス採用数", f"A:{wins.get('A',0)} B:{wins.get('B',0)} C:{wins.get('C',0)}")

        st.divider()

        _history = get_parallel_history(_bp, n=20)
        if not _history:
            st.info("まだ並列シミュ履歴がありません。\nBranchingが有効なタスクで自動記録されます。")
        else:
            for h in _history:
                with st.expander(
                    f"⚡ `{h['file']}` — {h['task']} "
                    f"（Path{h['chosen']} 採用 / スコア{h['chosen_score']}）",
                    expanded=False
                ):
                    st.caption(h["timestamp"])
                    cols = st.columns(len(h["all_scores"]))
                    for idx, (pname, score) in enumerate(h["all_scores"].items()):
                        chosen = pname == h["chosen"]
                        label  = f"Path {pname} {'✅採用' if chosen else '❌不採用'}"
                        cols[idx].metric(label, f"{score}/100")
                    if h["rejected_reasons"]:
                        st.caption("不採用理由: " + " / ".join(
                            f"Path{k}={v}" for k, v in h["rejected_reasons"].items()
                        ))

    except ImportError:
        st.error("blackwell_prediction.py が見つかりません")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# TAB 25: 🧠 思考ログ（Phase 4）
# ─────────────────────────────────────────────────────────
with gd_tabs[25]:
    st.markdown("### 🧠 Deep Thinking ログ")
    st.caption("AIがどのように考えてコードを生成したかを可視化。複雑さに応じて1〜5層の思考を展開。")

    if "last_thinking_log" not in st.session_state:
        st.info("まだ思考ログがありません。\n複雑さ3以上のタスクを実行するとここに表示されます。")
    else:
        log = st.session_state["last_thinking_log"]
        if not log:
            st.info("思考ログなし（単純タスクは通常生成）")
        else:
            # サマリー
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("複雑さ", f"{log.get('complexity', '?')}/5")
            c2.metric("思考の深さ", f"{log.get('depth_used', '?')}層")
            c3.metric("思考時間", f"{log.get('total_ms', 0):,}ms")
            c4.metric("最終スコア", f"{log.get('score', '?')}/100")

            if log.get("final_reasoning"):
                st.info(f"💡 **なぜこの実装にしたか:** {log['final_reasoning']}")

            st.divider()

            # 各思考ステップ
            st.markdown("#### 思考プロセス")
            for step in log.get("steps", []):
                with st.expander(
                    f"{step['icon']} 層{step['layer']}: {step['label']} ({step['duration']})",
                    expanded=step["layer"] <= 2
                ):
                    st.markdown(step["content"])

# ─────────────────────────────────────────────────────────
# TAB 26: 📚 学習データ（Phase 5）
# ─────────────────────────────────────────────────────────
with gd_tabs[26]:
    st.markdown("### 📚 学習データ & ファインチューニング")
    st.caption("Blackwellが生成した高品質コードを自動収集。100件溜まったら専用モデルを作れる。")

    try:
        from training_collector import (
            get_stats as get_training_stats,
            get_recent_samples, export_for_finetuning,
            generate_modelfile, generate_finetune_script,
            should_finetune,
        )

        _bp    = st.session_state.get("target_path", "./")
        _stats = get_training_stats(_bp)
        _total = _stats.get("total", 0)
        _ready = _stats.get("ready_for_finetune", False)
        _pct   = _stats.get("progress_pct", 0)

        # プログレスバー
        if _ready:
            st.success("🎓 ファインチューニング準備完了！専用モデルを作れます")
        else:
            st.info(f"📊 学習データ収集中... {_total}/{_stats.get('finetune_threshold', 100)}件")

        st.progress(_pct / 100)

        # 統計
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("収集済み", f"{_total}件")
        c2.metric("平均スコア", f"{_stats.get('avg_score', 0)}/100")
        c3.metric("達成率", f"{_pct}%")
        langs = _stats.get("by_language", {})
        c4.metric("言語数", f"{len(langs)}種類")

        # 言語別内訳
        if langs:
            st.caption("言語別: " + " / ".join(
                f"{k}:{v}件" for k, v in langs.items()))

        st.divider()

        # ファインチューニング設定
        st.markdown("#### 🎓 ファインチューニング設定")
        col_a, col_b = st.columns(2)
        with col_a:
            _base_model = st.selectbox(
                "ベースモデル",
                ["qwen2.5-coder:7b", "qwen2.5-coder:14b", "llama3.2:3b"],
                key="ft_base_model"
            )
        with col_b:
            _custom_name = st.text_input(
                "カスタムモデル名",
                value="blackwell-custom",
                key="ft_custom_name"
            )

        col_btn1, col_btn2, col_btn3 = st.columns(3)
        with col_btn1:
            if st.button("📦 alpaca形式でエクスポート",
                         use_container_width=True, key="ft_export"):
                with st.spinner("エクスポート中..."):
                    path = export_for_finetuning(_bp)
                if path:
                    st.success(f"✅ エクスポート完了: `{path}`")
                else:
                    st.warning("データが不足しています")

        with col_btn2:
            if st.button("📄 Modelfile生成",
                         use_container_width=True, key="ft_modelfile"):
                path = generate_modelfile(_bp, _base_model, _custom_name)
                if path:
                    st.success(f"✅ Modelfile生成: `{path}`")
                    st.code(
                        f"ollama create {_custom_name} -f {path}",
                        language="bash"
                    )

        with col_btn3:
            if st.button("🚀 学習スクリプト生成",
                         use_container_width=True, key="ft_script"):
                path = generate_finetune_script(_bp, _base_model, _custom_name)
                if path:
                    st.success(f"✅ スクリプト生成: `{path}`")
                    st.code(f"python {path}", language="bash")

        st.divider()

        # 使い方ガイド
        with st.expander("📖 ファインチューニングの手順", expanded=False):
            st.markdown("""
1. **データを100件以上収集する**（コードを生成するたびに自動収集）
2. **「alpaca形式でエクスポート」**ボタンを押す
3. **「学習スクリプト生成」**ボタンを押す
4. ターミナルで実行:
   ```bash
   pip install unsloth torch transformers datasets trl
   python blackwell_brain/run_finetune.py
   ```
5. 完了後:
   ```bash
   ollama create blackwell-custom -f blackwell_brain/Modelfile
   ```
6. app.pyの`MODELS["coder"]`を`"blackwell-custom"`に変更
7. **使えば使うほど専門化・高精度化する専用モデルの完成**
            """)

        st.divider()

        # 直近サンプル
        st.markdown("#### 📋 直近の学習データ")
        _samples = get_recent_samples(_bp, n=10)
        if not _samples:
            st.caption("まだデータがありません")
        else:
            for s in _samples:
                icon = "🧠" if s["has_thinking"] else "📄"
                tags = " ".join(f"`{t}`" for t in s["tags"][:3])
                st.caption(
                    f"{icon} **{s['file'] or '?'}** "
                    f"スコア:{s['score']} "
                    f"[{s['language']}] "
                    f"{tags} — {s['timestamp']}"
                )

    except ImportError:
        st.error("training_collector.py が見つかりません")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# TAB 27: 🧬 プロンプト進化（Phase 6）
# ─────────────────────────────────────────────────────────
with gd_tabs[27]:
    st.markdown("### 🧬 プロンプト自己進化")
    st.caption("失敗パターンを分析して自分のプロンプトを自動改善。使うほど賢くなる。")

    try:
        from prompt_evolver import (
            get_evolution_stats, get_all_improvements,
            force_evolve, should_evolve,
        )
        from engine import ROLES

        _bp    = st.session_state.get("target_path", "./")
        _stats = get_evolution_stats(_bp)

        # 統計
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("プロンプトバージョン", f"v{_stats.get('version', 0)}")
        c2.metric("累計改善数", f"{_stats.get('total_improvements', 0)}件")
        c3.metric("進化回数", f"{_stats.get('evolution_count', 0)}回")
        c4.metric("適用累計", f"{_stats.get('total_apply_count', 0)}回")

        st.divider()

        # 手動進化ボタン
        col_ev1, col_ev2 = st.columns([2, 1])
        with col_ev1:
            if st.button("🧬 今すぐ進化を実行", use_container_width=True,
                         key="force_evolve_btn"):
                with st.spinner("失敗パターンを分析中..."):
                    try:
                        result = force_evolve(_bp, ROLES)
                        if result and result.evolved:
                            st.success(
                                f"✅ 進化完了！{len(result.improvements)}件の改善を追加\n"
                                f"スコア +{result.score_delta} 向上予測"
                            )
                            for p in result.patterns_found[:3]:
                                st.info(f"🔍 パターン: **{p.get('pattern','')}** "
                                        f"（頻度{p.get('frequency',0):.0%}）")
                            st.rerun()
                        else:
                            st.info("改善が必要なパターンは見つかりませんでした")
                    except Exception as e:
                        st.error(f"進化失敗: {e}")
        with col_ev2:
            _needs = should_evolve(_bp)
            if _needs:
                st.warning("⚡ 進化推奨")
            else:
                st.success("✅ 最新状態")

        st.divider()

        # 現在の改善一覧
        st.markdown("#### 📋 蓄積された改善")
        _improvements = get_all_improvements(_bp)
        if not _improvements:
            st.info(
                "まだ改善が蓄積されていません。\n"
                "タスクを10件以上実行すると自動分析が始まります。"
            )
        else:
            icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            for imp in _improvements:
                icon = icons.get(imp["priority"], "⚪")
                with st.container(border=True):
                    st.markdown(
                        f"{icon} **{imp['pattern'] or '改善'}** "
                        f"— 適用{imp['apply_count']}回"
                    )
                    st.caption(f"📝 {imp['text']}")
                    if imp["keywords"]:
                        st.caption("🏷️ キーワード: " +
                                   " / ".join(f"`{k}`" for k in imp["keywords"][:4]))
                    st.caption(f"追加日: {imp['added_at']}")

        st.divider()

        # 進化履歴
        st.markdown("#### ⏱️ 進化履歴")
        for evo in reversed(_stats.get("recent_evolutions", [])):
            st.caption(
                f"🧬 {evo['timestamp']} — "
                f"{evo['patterns']}パターン検出 / "
                f"{evo['improvements']}件改善追加: "
                + ", ".join(evo.get("pattern_names", [])[:3])
            )

    except ImportError:
        st.error("prompt_evolver.py が見つかりません")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# TAB 28: 🌙 夜間バッチ（Phase 7）
# ─────────────────────────────────────────────────────────
with gd_tabs[28]:
    st.markdown("### 🌙 夜間バッチ")
    st.caption("バックログのタスクをBlackwellが自律実行。あなたが寝ている間に開発が進む。")

    try:
        from autonomous_scheduler import (
            run_night_batch, start_night_batch_bg,
            stop_night_batch, is_batch_running,
            get_night_status, get_morning_report,
            has_new_report, mark_report_read,
            get_backlog_stats,
        )

        _bp     = st.session_state.get("target_path", "./")
        _anchor = st.session_state.get("anchor", "")
        _status = get_night_status(_bp)
        _stats  = get_backlog_stats(_bp)
        _running = _status.get("is_running", False)

        # 朝のレポート通知
        if has_new_report(_bp):
            with st.expander("🌅 新しい夜間レポートがあります！", expanded=True):
                st.markdown(get_morning_report(_bp))
                if st.button("✅ 確認済みにする", key="mark_report_read"):
                    mark_report_read(_bp)
                    st.rerun()

        st.divider()

        # ステータス表示
        if _running:
            st.success(f"🔄 実行中: {_status.get('progress','...')}")
            st.metric("完了", _status.get("done", 0))
        else:
            st.info("待機中")

        # バックログの概要
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("未完了タスク", _stats.get("todo", 0))
        c2.metric("完了済み", _stats.get("done", 0))
        c3.metric("全体進捗", f"{_stats.get('progress_pct', 0)}%")
        c4.metric("失敗", _stats.get("failed", 0))

        st.divider()

        # 設定
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            _max_tasks = st.number_input(
                "最大タスク数", min_value=1, max_value=20,
                value=5, key="night_max_tasks"
            )
        with col_s2:
            _auto_write = st.checkbox(
                "自動ファイル書き込み", value=True,
                key="night_auto_write"
            )

        # 実行ボタン
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if not _running:
                if st.button("🌙 夜間バッチ開始",
                             use_container_width=True,
                             key="start_night_batch"):
                    if _stats.get("todo", 0) == 0:
                        st.warning("バックログにタスクがありません")
                    else:
                        _progress_placeholder = st.empty()
                        msgs = []
                        def _on_progress(msg):
                            msgs.append(msg)
                            _progress_placeholder.markdown(
                                "\n\n".join(msgs[-5:]))
                        success = start_night_batch_bg(
                            _bp, _anchor, _max_tasks,
                            _auto_write, _on_progress
                        )
                        if success:
                            st.success("バッチを開始しました")
                            st.rerun()
            else:
                if st.button("⏹️ バッチを停止",
                             use_container_width=True,
                             type="primary",
                             key="stop_night_batch"):
                    stop_night_batch()
                    st.warning("停止リクエストを送信しました")
                    st.rerun()

        with col_b2:
            if not _running:
                if st.button("▶️ 今すぐ1タスク実行",
                             use_container_width=True,
                             key="run_one_task"):
                    from autonomous_scheduler import get_next_tasks
                    from engine import process_task, load_grand_state
                    nxt = get_next_tasks(_bp, n=1)
                    if nxt:
                        t = nxt[0]
                        gs = load_grand_state(_bp)
                        with st.spinner(f"実行中: {t['title']}"):
                            res_md, ok = process_task(
                                {"file": t["file"], "desc": t["desc"]},
                                auto_write=_auto_write,
                                save_path=_bp,
                                anchor=_anchor,
                                grand_state=gs,
                            )
                        from autonomous_scheduler import mark_done as _md, mark_failed as _mf
                        if ok:
                            _md(_bp, t["task_id"], "手動実行で完了")
                            st.success(f"✅ {t['title']} 完了")
                        else:
                            _mf(_bp, t["task_id"], "手動実行で失敗")
                            st.error(f"❌ {t['title']} 失敗")
                        st.rerun()
                    else:
                        st.info("実行可能なタスクがありません")

        st.divider()

        # 実行履歴
        st.markdown("#### 📊 過去のバッチ履歴")
        for s in _status.get("recent_sessions", []):
            st.caption(
                f"🌙 {s['started_at']} — "
                f"✅{s['done']}件 ❌{s['failed']}件 "
                f"({s['duration_s']}秒)"
            )

    except ImportError:
        st.error("autonomous_scheduler.py が見つかりません")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# TAB 29: 📋 バックログ（Phase 7）
# ─────────────────────────────────────────────────────────
with gd_tabs[29]:
    st.markdown("### 📋 バックログ管理")
    st.caption("自律実行するタスクのキュー。依存関係を自動解決して順番に実行する。")

    try:
        from autonomous_scheduler import (
            add_task as scheduler_add_task,
            get_backlog, get_next_tasks,
            mark_done as _bmark_done,
            clear_done_tasks, get_backlog_stats,
        )

        _bp = st.session_state.get("target_path", "./")

        # タスク追加フォーム
        with st.expander("➕ タスクを追加", expanded=False):
            _title  = st.text_input("タスク名", key="bl_title")
            _file   = st.text_input("対象ファイル名", key="bl_file",
                                     placeholder="player.gd")
            _desc   = st.text_area("実装内容", key="bl_desc", height=80)
            _pri    = st.selectbox("優先度",
                                   ["高（1）", "中（2）", "低（3）"],
                                   index=1, key="bl_priority")
            _pri_val = {"高（1）": 1, "中（2）": 2, "低（3）": 3}[_pri]
            if st.button("追加", key="bl_add_btn"):
                if _title and _file and _desc:
                    tid = scheduler_add_task(
                        _bp, _title, _file, _desc, _pri_val)
                    st.success(f"✅ 追加: {tid}")
                    st.rerun()
                else:
                    st.warning("タスク名・ファイル名・実装内容を入力してください")

        # 次に実行されるタスク
        _next = get_next_tasks(_bp, n=3)
        if _next:
            st.markdown("#### ⚡ 次に実行されるタスク")
            for t in _next:
                icons_pri = {1: "🔴", 2: "🟡", 3: "🟢"}
                st.info(f"{icons_pri.get(t['priority'],'⚪')} **{t['title']}** "
                        f"— `{t['file']}`")

        st.divider()

        # 全タスク一覧
        _all_tasks = get_backlog(_bp)
        _filter = st.selectbox("表示フィルタ",
                                ["全て", "未完了のみ", "完了済みのみ", "失敗のみ"],
                                key="bl_filter")
        filter_map = {
            "全て": None,
            "未完了のみ": "todo",
            "完了済みのみ": "done",
            "失敗のみ": "failed",
        }
        _filter_status = filter_map[_filter]
        filtered = [t for t in _all_tasks
                    if _filter_status is None
                    or t.get("status") == _filter_status]

        status_icons = {
            "todo": "⏳", "done": "✅",
            "failed": "❌", "running": "🔄", "skipped": "⏭️"
        }
        pri_icons = {1: "🔴", 2: "🟡", 3: "🟢"}

        for t in reversed(filtered[-30:]):
            icon    = status_icons.get(t.get("status","todo"), "⏳")
            priIcon = pri_icons.get(t.get("priority", 2), "⚪")
            with st.container(border=True):
                c1, c2 = st.columns([8, 2])
                with c1:
                    st.markdown(
                        f"{icon} {priIcon} **{t['title']}** "
                        f"— `{t['file']}`"
                    )
                    if t.get("desc"):
                        st.caption(t["desc"][:80])
                    if t.get("result_summary"):
                        st.caption(f"結果: {t['result_summary'][:60]}")
                    deps = t.get("depends_on", [])
                    if deps:
                        st.caption(f"依存: {', '.join(deps)}")
                with c2:
                    if t.get("status") == "todo":
                        if st.button("✅", key=f"done_{t['task_id']}",
                                     help="完了にする"):
                            _bmark_done(_bp, t["task_id"], "手動完了")
                            st.rerun()

        if st.button("🗑️ 完了タスクをアーカイブ", key="bl_clear"):
            clear_done_tasks(_bp)
            st.success("アーカイブしました")
            st.rerun()

    except ImportError:
        st.error("autonomous_scheduler.py が見つかりません")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# TAB 30: 🤖 エージェント協調（Phase 8）
# ─────────────────────────────────────────────────────────
with gd_tabs[30]:
    st.markdown("### 🤖 エージェント協調")
    st.caption("複雑なタスクは6種のAIエージェントがチームで議論・実装・レビュー・統合する。")

    try:
        from agent_society import (
            get_agent_stats, get_coordination_history,
            get_agent_memory,
        )

        _bp    = st.session_state.get("target_path", "./")
        _stats = get_agent_stats(_bp)

        # 統計
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("協調セッション", f"{_stats.get('total_sessions', 0)}回")
        c2.metric("平均スコア", f"{_stats.get('avg_score', 0)}/100")
        c3.metric("平均ラウンド", f"{_stats.get('avg_rounds', 0):.1f}")
        c4.metric("最高スコア", f"{_stats.get('best_score', 0)}/100")

        st.divider()

        # エージェント使用数
        usage = _stats.get("agent_usage", {})
        if usage:
            st.markdown("#### 🤖 エージェント使用回数")
            agent_icons = {
                "architect": "🏛️", "coder": "💻",
                "critic": "🔍", "tester": "🧪",
                "designer": "🎮", "integrator": "🎯",
            }
            cols = st.columns(len(usage))
            for i, (agent, count) in enumerate(usage.items()):
                icon = agent_icons.get(agent, "🤖")
                cols[i].metric(f"{icon} {agent}", f"{count}回")

        st.divider()

        # 最新の協調ログ
        if "last_coord_log" in st.session_state:
            log = st.session_state["last_coord_log"]
            st.markdown("#### 📋 最新の協調ログ")
            c1, c2, c3 = st.columns(3)
            c1.metric("ラウンド数", log.get("rounds_used", "?"))
            c2.metric("スコア", f"{log.get('score', '?')}/100")
            c3.metric("総時間", f"{log.get('total_ms', 0):,}ms")

            if log.get("final_reason"):
                st.info(f"🎯 **最終判断:** {log['final_reason']}")

            for step in log.get("steps", []):
                with st.expander(
                    f"{step['icon']} Round{step['round']}: "
                    f"{step['label']} ({step['duration']})",
                    expanded=False
                ):
                    st.markdown(step["content"])

        st.divider()

        # 協調履歴
        st.markdown("#### ⏱️ 協調履歴")
        _history = get_coordination_history(_bp, n=10)
        if not _history:
            st.info(
                "まだ協調履歴がありません。\n"
                "複雑さ5のタスクで自動起動します。\n"
                "または手動で「複雑さ上限」を設定して実行できます。"
            )
        else:
            for h in _history:
                agents_str = " → ".join(h.get("agents", []))
                with st.expander(
                    f"🤖 {h['timestamp']} / "
                    f"スコア{h['score']} / {h['rounds']}ラウンド",
                    expanded=False
                ):
                    st.caption(f"タスク: {h['desc']}")
                    st.caption(f"エージェント: {agents_str}")
                    st.caption(f"最終判断: {h['reason']}")
                    st.caption(f"所要時間: {h['total_ms']:,}ms")

        st.divider()

        # エージェント記憶の確認
        st.markdown("#### 🧠 エージェントの記憶")
        for agent in ["architect", "coder", "critic", "tester"]:
            mem = get_agent_memory(_bp, agent)
            if mem:
                icons_map = {
                    "architect":"🏛️","coder":"💻",
                    "critic":"🔍","tester":"🧪"
                }
                with st.expander(
                    f"{icons_map.get(agent,'🤖')} {agent}の記憶",
                    expanded=False
                ):
                    st.text(mem)

    except ImportError:
        st.error("agent_society.py が見つかりません")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# TAB 31: 🎮 ゲームプレイ解析（Phase 9）
# ─────────────────────────────────────────────────────────
with gd_tabs[31]:
    st.markdown("### 🎮 ゲームプレイ解析 & 自動修正")
    st.caption("スクショをアップロードするとBlackwellがゲームを見て問題を検出・自動修正する。")

    try:
        from game_player import (
            analyze_and_fix_bytes, get_game_insights, get_play_history,
        )

        _bp     = st.session_state.get("target_path", "./")
        _anchor = st.session_state.get("anchor", "")

        # スクショアップロード
        uploaded = st.file_uploader(
            "ゲームのスクリーンショットをアップロード",
            type=["png", "jpg", "jpeg", "webp"],
            key="gameplay_upload"
        )

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            _auto_fix = st.checkbox("自動修正する", value=True,
                                    key="gp_auto_fix")
        with col_s2:
            _gp_model = st.selectbox(
                "ビジョンモデル",
                ["llava-llama3:latest", "llava:latest", "moondream:latest"],
                key="gp_model"
            )

        if uploaded and st.button("🎮 解析・修正開始", key="gp_analyze"):
            image_bytes = uploaded.read()
            st.image(image_bytes, caption="解析対象", width=400)

            with st.spinner("ゲームを解析中..."):
                result = analyze_and_fix_bytes(
                    image_bytes, _bp, _anchor,
                    auto_fix=_auto_fix, model=_gp_model
                )

            if result:
                st.metric("面白さスコア", f"{result.fun_score}/100")

                st.markdown("**画面の説明:**")
                st.info(result.image_desc)

                if result.issues:
                    st.markdown(f"**検出された問題 ({len(result.issues)}件):**")
                    sev_icons = {"critical": "🔴", "major": "🟡", "minor": "🟢"}
                    cat_icons = {"bug": "🐛", "balance": "⚖️",
                                 "ux": "👆", "visual": "🎨",
                                 "performance": "⚡"}
                    for issue in result.issues:
                        sev  = sev_icons.get(issue.severity, "⚪")
                        cat  = cat_icons.get(issue.category, "❓")
                        with st.container(border=True):
                            st.markdown(
                                f"{sev} {cat} **{issue.description}**")
                            st.caption(f"場所: {issue.location}")
                            st.caption(f"修正ヒント: {issue.fix_hint}")
                            if issue.target_file:
                                st.caption(f"対象ファイル: `{issue.target_file}`")

                if result.fixes_applied:
                    st.markdown(f"**自動修正結果 ({len(result.fixes_applied)}件):**")
                    for fix in result.fixes_applied:
                        icon = "✅" if fix.get("success") else "❌"
                        st.caption(
                            f"{icon} `{fix.get('file','?')}` "
                            f"— {fix.get('issue','')[:40]}"
                        )

        st.divider()

        # 知見・統計
        _insights = get_game_insights(_bp)
        if _insights.get("total_sessions", 0) > 0:
            st.markdown("#### 📊 ゲームプレイ知見")
            c1, c2, c3 = st.columns(3)
            c1.metric("解析回数", _insights.get("total_sessions", 0))
            c2.metric("平均面白さ", f"{_insights.get('avg_fun_score', 0)}/100")
            cats = _insights.get("category_counts", {})
            top_cat = max(cats, key=cats.get) if cats else "—"
            c3.metric("最多問題カテゴリ", top_cat)

            # 面白さスコアの推移
            history = _insights.get("fun_score_history", [])
            if len(history) >= 2:
                scores = [h["score"] for h in history[-10:]]
                import pandas as pd
                st.line_chart(pd.DataFrame({"面白さスコア": scores}))

            # よくある問題
            if _insights.get("common_issues"):
                st.markdown("**よくある問題:**")
                for ci in _insights["common_issues"][:5]:
                    st.caption(
                        f"🔁 **{ci['category']}**: "
                        f"{ci['desc'][:50]} （{ci['count']}回）"
                    )

        # プレイ履歴
        _ph = get_play_history(_bp, n=5)
        if _ph:
            st.markdown("#### 📋 解析履歴")
            for s in _ph:
                st.caption(
                    f"🎮 {s['timestamp']} — "
                    f"面白さ:{s['fun_score']}/100 / "
                    f"問題:{s['issues']}件 / 修正:{s['fixes']}件"
                )

    except ImportError:
        st.error("game_player.py が見つかりません")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# TAB 32: 🤔 自己モデル（Phase 10）
# ─────────────────────────────────────────────────────────
with gd_tabs[32]:
    st.markdown("### 🤔 自己モデル")
    st.caption("Blackwellが自分の得意・苦手・役割・戦略を把握して最適な行動を選択する。")

    try:
        from self_model import (
            get_self_model, get_self_report,
            rebuild_self_model, should_rebuild,
        )
        from engine import MODELS

        _bp    = st.session_state.get("target_path", "./")
        _model = get_self_model(_bp)
        _needs = should_rebuild(_bp)

        # 再構築ボタン
        col_r1, col_r2 = st.columns([3, 1])
        with col_r1:
            if _needs:
                st.warning("⚡ 自己モデルの更新を推奨（新しいタスクデータあり）")
            elif _model:
                st.success(f"✅ 自己モデル v{_model.version} — 最新")
            else:
                st.info("まだ自己モデルがありません（20タスク以上で自動構築）")

        with col_r2:
            if st.button("🔄 今すぐ再構築", key="rebuild_self_model"):
                with st.spinner("全データを分析中..."):
                    try:
                        new_model = rebuild_self_model(
                            _bp,
                            model=MODELS.get("optimizer", MODELS["coder"])
                        )
                        st.success(
                            f"✅ v{new_model.version} 構築完了\n"
                            f"成功率: {new_model.overall_success_rate:.0%}"
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"構築失敗: {e}")

        st.divider()

        # 自己レポート
        report = get_self_report(_bp)
        st.markdown(report)

        # 戦略の可視化（自己モデルがある場合）
        if _model and _model.strengths:
            st.divider()
            st.markdown("#### ⚡ 実行戦略への影響")
            st.markdown("""
| 状況 | Blackwellの行動 |
|---|---|
| 得意タスク | 複雑さ-1 / 速いモデルで自信を持って実行 |
| 苦手タスク | 複雑さ+1 / Agent Societyを推奨 |
| 苦手+失敗率50%以上 | Agent Society強制起動 |
| 信頼エージェントあり | そのエージェントを優先使用 |
            """)

    except ImportError:
        st.error("self_model.py が見つかりません")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# 🔌 Godot Plugin統合タブ
# ─────────────────────────────────────────────────────────
with gd_tabs[33]:
    st.markdown("### 🔌 Godot Editor Plugin 接続")
    st.caption("GodotエディタとBlackwellをWebSocketでリアルタイム接続。エラーを自動修正・コードを自動送信。")

    try:
        from godot_bridge import (
            start_bridge, stop_bridge, is_connected,
            get_bridge_status, get_error_log,
            send_notification, request_scene_info,
            get_last_scene_info,
        )
        from error_healer import (
            start_heal_loop, stop_heal_loop,
            get_heal_stats, get_heal_history,
        )

        _bp     = st.session_state.get("target_path", "./")
        _anchor = st.session_state.get("anchor", "")
        _status = get_bridge_status()
        _running = _status.get("running", False)
        _conn    = _status.get("connected", False)

        # ── 接続状態 ──────────────────────────────────────
        if _conn:
            st.success("🟢 Godotエディタ接続中")
        elif _running:
            st.warning("🟡 待機中（Godotからの接続を待っています）")
        else:
            st.info("⚫ ブリッジ停止中")

        # 統計
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("受信メッセージ", _status.get("total_received", 0))
        c2.metric("送信メッセージ", _status.get("total_sent", 0))
        c3.metric("未処理リクエスト", _status.get("pending_requests", 0))
        c4.metric("エラーログ", _status.get("error_log_count", 0))

        st.divider()

        # ── 起動・停止ボタン ──────────────────────────────
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            if not _running:
                if st.button("▶️ ブリッジ起動", use_container_width=True,
                             key="start_bridge"):
                    ok = start_bridge()
                    if ok:
                        start_heal_loop(_bp, _anchor)
                        st.success(f"ws://localhost:9901 で待機開始")
                        st.rerun()
                    else:
                        st.error("起動失敗（simple-websocketが必要）")
            else:
                if st.button("⏹️ ブリッジ停止", use_container_width=True,
                             key="stop_bridge"):
                    stop_bridge()
                    stop_heal_loop()
                    st.rerun()

        with col_b2:
            if _conn and st.button("📣 テスト通知送信",
                                    use_container_width=True,
                                    key="test_notify"):
                send_notification("Blackwellから接続テスト", "info")
                st.success("送信しました")

        with col_b3:
            if _conn and st.button("🗺️ シーン情報取得",
                                    use_container_width=True,
                                    key="get_scene"):
                request_scene_info()
                st.success("リクエスト送信")

        st.divider()

        # ── インストール手順 ─────────────────────────────
        with st.expander("📦 Godotプラグインのインストール方法", expanded=not _conn):
            st.markdown("""
**手順（3ステップ）**

1. `addons/blackwell/` フォルダをGodotプロジェクトにコピー
   ```
   YourGame/
   └── addons/
       └── blackwell/
           ├── plugin.cfg
           └── blackwell_plugin.gd
   ```

2. Godotエディタ → **プロジェクト → プロジェクト設定 → プラグイン**
   → `Blackwell Dev-OS` を **有効化**

3. Blackwellの「▶️ ブリッジ起動」を押す
   → エディタ右下に `🟢 接続中` が表示される

**できるようになること:**
- Godotのエラーが出た瞬間にBlackwellが自動修正
- Blackwellが書いたコードがGodotに自動保存・リロード
- 「このスクリプトを直して」ボタンがGodotエディタ内に追加
""")

        # ── シーン情報 ───────────────────────────────────
        scene = get_last_scene_info()
        if scene:
            st.markdown("#### 🎬 現在のシーン")
            st.caption(f"**{scene.get('scene_name','?')}** — "
                       f"{scene.get('node_count', 0)}ノード")

        # ── エラーログ ────────────────────────────────────
        err_log = get_error_log(n=10)
        if err_log:
            st.markdown("#### 🐛 Godotエラーログ")
            for e in reversed(err_log):
                sev_icon = "🔴" if e.get("severity") == "error" else "🟡"
                with st.container(border=True):
                    st.caption(
                        f"{sev_icon} `{e.get('file','?')}:{e.get('line',0)}`"
                    )
                    st.caption(e.get("message", "")[:120])
        else:
            if _conn:
                st.success("✅ エラーなし")

        st.divider()

        # ── 自動修復ログ ──────────────────────────────────
        st.markdown("#### ⚡ 自動修復ログ")
        heal_stats = get_heal_stats()
        c1, c2, c3 = st.columns(3)
        c1.metric("修復成功", heal_stats.get("healed", 0))
        c2.metric("修復失敗", heal_stats.get("failed", 0))
        c3.metric("スキップ", heal_stats.get("skipped", 0))

        for h in reversed(get_heal_history(n=8)):
            icon = "✅" if h.get("success") else "❌"
            st.caption(
                f"{icon} {h.get('time','')} — "
                f"`{h.get('file','?')}:{h.get('line',0)}` "
                f"{h.get('error','')[:50]}"
            )

    except ImportError as e:
        st.error(f"godot_bridge.py / error_healer.py が見つかりません: {e}")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# 🧠 プレイヤーAI強化学習タブ（Phase ②）
# ─────────────────────────────────────────────────────────
with gd_tabs[34]:
    st.markdown("### 🧠 プレイヤーAI強化学習")
    st.caption("ゲームを自分でプレイしながらQ-learningで最適な行動を学習するAIエージェント。")

    try:
        from rl_trainer import (
            setup_rl, get_rl_stats,
            export_policy_for_godot, generate_agent_script,
        )
        from godot_bridge import set_rl_project_path

        _bp = st.session_state.get("target_path", "./")
        set_rl_project_path(_bp)

        _stats = get_rl_stats(_bp)

        # ── 統計ダッシュボード ─────────────────────────────
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("エピソード数",  _stats.get("total_episodes", 0))
        c2.metric("総ステップ数",  f"{_stats.get('total_steps', 0):,}")
        c3.metric("探索率 ε",      f"{_stats.get('epsilon', 1.0):.3f}")
        c4.metric("学習済み状態数", f"{_stats.get('qtable_states', 0):,}")

        c5, c6 = st.columns(2)
        c5.metric("最高報酬",   _stats.get("best_reward", 0))
        c6.metric("直近20話平均", _stats.get("recent_avg", 0))

        # 学習曲線
        curve = _stats.get("learning_curve", [])
        if len(curve) >= 2:
            import pandas as pd
            df = pd.DataFrame(curve).set_index("ep")
            st.line_chart(df["avg"], use_container_width=True,
                          height=150)
            st.caption("📈 学習曲線（10エピソードごとの平均報酬）")

        st.divider()

        # ── セットアップ ──────────────────────────────────
        with st.expander("⚙️ エージェント設定", expanded=_stats.get("total_episodes", 0) == 0):
            st.caption("アクションと状態変数をカンマ区切りで入力してください")

            _default_actions = "move_left,move_right,jump,attack,dodge,use_item"
            _default_states  = "hp_ratio,pos_x_norm,pos_y_norm,nearest_enemy_dist,nearest_enemy_dir,on_ground"

            _actions_in = st.text_input(
                "アクション一覧", value=_default_actions, key="rl_actions")
            _states_in  = st.text_input(
                "状態変数一覧", value=_default_states, key="rl_states")

            st.caption("報酬設定")
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                r_kill  = st.number_input("敵を倒す",    value=10.0, key="r_kill")
                r_dmg   = st.number_input("ダメージを受ける", value=-5.0, key="r_dmg")
                r_item  = st.number_input("アイテム取得",  value=3.0, key="r_item")
            with col_r2:
                r_goal  = st.number_input("ゴール達成",  value=50.0, key="r_goal")
                r_over  = st.number_input("ゲームオーバー", value=-20.0, key="r_over")
                r_surv  = st.number_input("生存ボーナス",  value=0.2,  key="r_surv")

            if st.button("✅ 設定を保存", key="rl_setup"):
                actions_list = [a.strip() for a in _actions_in.split(",") if a.strip()]
                states_list  = [s.strip() for s in _states_in.split(",")  if s.strip()]
                rewards_cfg  = {
                    "kill_enemy":   r_kill,
                    "take_damage":  r_dmg,
                    "pick_item":    r_item,
                    "reach_goal":   r_goal,
                    "game_over":    r_over,
                    "survive_bonus": r_surv,
                }
                setup_rl(_bp, actions_list, states_list, rewards_cfg)
                st.success("✅ 設定を保存しました")
                st.rerun()

        st.divider()

        # ── コード生成 ────────────────────────────────────
        st.markdown("#### 📄 Godotコード生成")
        col_g1, col_g2 = st.columns(2)

        with col_g1:
            if st.button("🎮 エージェントひな形を生成",
                         use_container_width=True, key="gen_agent"):
                code = generate_agent_script(_bp)
                st.session_state["rl_agent_code"] = code
                # ファイルに保存
                import os
                out_path = os.path.join(_bp, "rl_agent.gd")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(code)
                st.success(f"✅ {out_path} に保存しました")

        with col_g2:
            if st.button("📤 学習済み方策をエクスポート",
                         use_container_width=True, key="export_policy"):
                if _stats.get("qtable_states", 0) == 0:
                    st.warning("まだ学習データがありません")
                else:
                    policy_gd = export_policy_for_godot(_bp)
                    import os
                    out_path  = os.path.join(_bp, "addons", "blackwell", "rl_policy.gd")
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write(policy_gd)
                    # Godotにも送信
                    try:
                        from godot_bridge import send_code, is_connected
                        if is_connected():
                            send_code("addons/blackwell/rl_policy.gd", policy_gd)
                            st.success("✅ Godotに送信しました")
                        else:
                            st.success(f"✅ {out_path} に保存しました")
                    except Exception:
                        st.success(f"✅ {out_path} に保存しました")

        # コードプレビュー
        if "rl_agent_code" in st.session_state:
            with st.expander("📄 生成されたエージェントコード", expanded=False):
                st.code(st.session_state["rl_agent_code"][:2000],
                        language="gdscript")

        st.divider()

        # ── 直近エピソード ────────────────────────────────
        st.markdown("#### 📊 直近エピソード")
        last_eps = _stats.get("last_episodes", [])
        if not last_eps:
            st.info(
                "まだ学習データがありません。\n\n"
                "**使い方:**\n"
                "1. エージェント設定を入力して保存\n"
                "2. 「エージェントひな形を生成」でGDScriptを取得\n"
                "3. GodotプロジェクトにGDScriptを追加\n"
                "4. Godot接続タブでブリッジを起動\n"
                "5. ゲームを実行するとAIが自動学習開始"
            )
        else:
            for ep in reversed(last_eps[-5:]):
                bar_len  = min(20, max(1, int(ep["total_reward"] / 5)))
                bar      = "█" * bar_len
                ep_color = "✅" if ep["total_reward"] > 0 else "❌"
                st.caption(
                    f"{ep_color} Ep{ep['episode_id']:>4} "
                    f"| 報酬: {ep['total_reward']:>7.1f} {bar} "
                    f"| ステップ: {ep['steps']:>5} "
                    f"| ε={ep['epsilon']:.3f}"
                )

    except ImportError as e:
        st.error(f"rl_trainer.py が見つかりません: {e}")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# 🎬 動画解析タブ（⑧）
# ─────────────────────────────────────────────────────────
with gd_tabs[35]:
    st.markdown("### 🎬 プレイ動画解析")
    st.caption("動画をアップロードするとBlackwellが時系列でバグ・問題・面白さを解析する。")

    try:
        from video_analyzer import (
            analyze_frames, get_video_history,
            get_video_insights,
        )

        _bp     = st.session_state.get("target_path", "./")
        _anchor = st.session_state.get("anchor", "")
        _ins    = get_video_insights(_bp)

        # 統計
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("解析本数",     _ins.get("total_analyses", 0))
        c2.metric("自分のゲーム", _ins.get("own_analyses", 0))
        c3.metric("参考ゲーム",   _ins.get("reference_analyses", 0))
        c4.metric("検出問題数",   _ins.get("total_issues_found", 0))

        if not _ins.get("has_ffmpeg"):
            st.warning("⚠️ ffmpegがインストールされていません。GIF以外の動画はffmpegが必要です。")

        st.divider()

        # アップロード
        uploaded_video = st.file_uploader(
            "動画または連続スクショをアップロード",
            type=["mp4", "webm", "gif", "avi", "mov"],
            key="video_upload",
        )

        col_v1, col_v2, col_v3 = st.columns(3)
        with col_v1:
            _mode = st.selectbox(
                "モード",
                ["own: 自分のゲームの問題検出",
                 "reference: 参考ゲームの面白さ学習"],
                key="video_mode"
            )
            _mode_key = "own" if _mode.startswith("own") else "reference"
        with col_v2:
            _vision_model = st.selectbox(
                "ビジョンモデル",
                ["llava-llama3:latest", "llava:latest", "moondream:latest"],
                key="vid_model"
            )
        with col_v3:
            _add_backlog = st.checkbox(
                "問題をバックログに追加", value=True,
                key="vid_backlog"
            )

        if uploaded_video and st.button("🎬 解析開始", key="start_video_analysis"):
            import tempfile, os

            # 一時ファイルに保存
            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=os.path.splitext(uploaded_video.name)[1]
            ) as tmp:
                tmp.write(uploaded_video.read())
                tmp_path = tmp.name

            with st.spinner(f"フレームを解析中... (最大{30}フレーム)"):
                try:
                    from video_analyzer import _extract_frames
                    frames = _extract_frames(tmp_path, max_frames=30)

                    if not frames:
                        st.error("フレームを抽出できませんでした（ffmpegが必要かもしれません）")
                    else:
                        result = analyze_frames(
                            frames,
                            mode=_mode_key,
                            project_path=_bp,
                            anchor=_anchor,
                            model=_vision_model,
                            video_name=uploaded_video.name,
                            duration_sec=frames[-1][0] if frames else 0,
                        )

                        st.success(
                            f"✅ 解析完了: {result.frames_analyzed}フレーム分析"
                        )

                        # サマリー
                        if result.summary:
                            st.info(f"**総評:** {result.summary}")

                        # 問題一覧
                        if result.issues:
                            st.markdown(f"#### ⚠️ 検出された問題 ({len(result.issues)}件)")
                            for iss in result.issues:
                                pri_icon = {"high":"🔴","medium":"🟡","low":"🟢"}.get(
                                    iss.get("priority","medium"), "⚪")
                                with st.container(border=True):
                                    st.markdown(
                                        f"{pri_icon} **[{iss.get('time','')}]** "
                                        f"{iss.get('problem','')}")
                                    if iss.get("fix_hint"):
                                        st.caption(f"修正ヒント: {iss['fix_hint']}")
                                    if iss.get("target_file"):
                                        st.caption(f"対象: `{iss['target_file']}`")

                            if result.backlog_tasks:
                                st.success(
                                    f"📋 {len(result.backlog_tasks)}件のタスクをバックログに追加しました")

                        # 面白要素
                        if result.fun_elements:
                            st.markdown(f"#### 🎯 面白い要素 ({len(result.fun_elements)}件)")
                            for fe in result.fun_elements:
                                with st.container(border=True):
                                    st.markdown(f"**{fe.get('element','')}**")
                                    st.caption(fe.get("description",""))
                                    if fe.get("how_to_apply"):
                                        st.caption(f"💡 応用方法: {fe['how_to_apply']}")

                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

        st.divider()

        # 参考ゲームから学んだ要素
        ref_insights = _ins.get("reference_insights", [])
        if ref_insights:
            st.markdown("#### 💡 参考ゲームから学んだ要素")
            for ri in ref_insights:
                with st.expander(
                    f"🎮 {ri.get('element','')} — {ri.get('source','')}",
                    expanded=False
                ):
                    st.caption(ri.get("description",""))
                    if ri.get("how_to_apply"):
                        st.info(f"**応用:** {ri['how_to_apply']}")

        st.divider()

        # 解析履歴
        st.markdown("#### 📋 解析履歴")
        _hist = get_video_history(_bp, n=8)
        if not _hist:
            st.info(
                "まだ解析履歴がありません。\n\n"
                "**使い方:**\n"
                "- 自分のゲームを録画してアップロード → 問題を自動検出\n"
                "- 参考にしたいゲームをアップロード → 面白さを学習"
            )
        else:
            for h in _hist:
                mode_icon = "🎮" if h["mode"] == "own" else "📺"
                st.caption(
                    f"{mode_icon} {h['timestamp']} — **{h['video_name']}** "
                    f"| 問題:{h['issues']}件 | 面白要素:{h['fun_elements']}件 "
                    f"| バックログ追加:{h['backlog']}件"
                )

    except ImportError as e:
        st.error(f"video_analyzer.py が見つかりません: {e}")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# 🌐 知識ハブタブ（④ マルチプロジェクト知識共有）
# ─────────────────────────────────────────────────────────
with gd_tabs[36]:
    st.markdown("### 🌐 マルチプロジェクト知識ハブ")
    st.caption("複数プロジェクトをまたいで成功パターン・失敗・教訓を蓄積・共有する。")

    try:
        from knowledge_hub import (
            register_project, export_project,
            get_hub_stats, search_knowledge,
            get_cross_lessons,
        )

        _bp   = st.session_state.get("target_path", "./")
        _stats = get_hub_stats()

        # ── 統計 ──────────────────────────────────────────
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("登録プロジェクト", _stats.get("total_projects", 0))
        c2.metric("成功パターン",     _stats.get("successes", 0))
        c3.metric("失敗パターン",     _stats.get("failures", 0))
        c4.metric("教訓",             _stats.get("lessons", 0))

        st.caption(f"📂 ハブ保存先: `{_stats.get('hub_path','')}`")
        if _stats.get("last_updated"):
            st.caption(f"最終更新: {_stats['last_updated']}")

        st.divider()

        # ── 操作ボタン ────────────────────────────────────
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            if st.button("📥 現プロジェクトを登録",
                         use_container_width=True, key="hub_register"):
                import os
                name = os.path.basename(_bp)
                register_project(_bp, name)
                st.success(f"✅ 登録: {name}")
                st.rerun()

        with col_b2:
            if st.button("📤 知識をエクスポート",
                         use_container_width=True, key="hub_export"):
                with st.spinner("エクスポート中..."):
                    import os
                    n = export_project(_bp, os.path.basename(_bp))
                st.success(f"✅ {n}件をハブに追加しました")
                st.rerun()

        with col_b3:
            _search_q = st.text_input(
                "🔍 知識を検索", placeholder="例: シェーダー",
                key="hub_search", label_visibility="collapsed")

        st.divider()

        # ── 検索結果 ──────────────────────────────────────
        if _search_q:
            results = search_knowledge(_search_q, n=10)
            st.markdown(f"#### 🔍 「{_search_q}」の検索結果 ({len(results)}件)")
            if results:
                for r in results:
                    st.caption(f"{r['category']} [{r['source']}] {r['text']}")
            else:
                st.info("一致する知識がありません")

        # ── 登録プロジェクト一覧 ──────────────────────────
        projects = _stats.get("projects", [])
        if projects:
            st.markdown("#### 📁 登録プロジェクト")
            for p in projects:
                exported = p.get("exported_at", "")
                with st.container(border=True):
                    col_p1, col_p2 = st.columns([3, 1])
                    with col_p1:
                        st.markdown(f"**{p['name']}**"
                                    + (f"  `{p.get('genre','')}`" if p.get('genre') else ""))
                        st.caption(f"📂 {p['path']}")
                        st.caption(f"最終アクティブ: {p.get('last_active','')}"
                                   + (f" / エクスポート: {exported}" if exported else " / 未エクスポート"))
                    with col_p2:
                        if st.button("📤", key=f"export_{p['path']}",
                                     help="この プロジェクトをエクスポート"):
                            n = export_project(p["path"], p["name"])
                            st.success(f"{n}件")
                            st.rerun()

        # ── ジャンル別知見 ────────────────────────────────
        genre_ins = _stats.get("genre_insights", {})
        if genre_ins:
            st.markdown("#### 🎮 ジャンル別知見")
            for genre, count in genre_ins.items():
                st.caption(f"**{genre}**: {count}件")

        # ── エージェント信頼スコア（全プロジェクト平均） ──
        trust = _stats.get("agent_trust", {})
        if trust:
            st.markdown("#### 🤖 エージェント信頼スコア（全プロジェクト平均）")
            icons = {"architect":"🏛️","coder":"💻","critic":"🔍",
                     "tester":"🧪","designer":"🎮","integrator":"🎯"}
            for agent, score in sorted(trust.items(), key=lambda x: -x[1]):
                bar = "█" * (score // 10) + "░" * (10 - score // 10)
                st.caption(
                    f"{icons.get(agent,'🤖')} **{agent}**: `{bar}` {score}/100")

        # ── 直近の教訓 ────────────────────────────────────
        st.divider()
        st.markdown("#### 📖 最近の教訓")
        lessons = get_cross_lessons(n=8)
        if lessons:
            for l in lessons:
                icon = {"success":"✅","failure":"❌","lesson":"📖"}.get(
                    l["category"], "📌")
                st.caption(f"{icon} [{l['source']}] {l['text']}")
        else:
            st.info(
                "まだ知識がありません。\n\n"
                "**使い方:**\n"
                "1. 「現プロジェクトを登録」でハブに登録\n"
                "2. タスクを実行するたびに知識が蓄積される\n"
                "3. 「知識をエクスポート」でハブに共有\n"
                "4. 次のプロジェクトで自動的に活用される"
            )

    except ImportError as e:
        st.error(f"knowledge_hub.py が見つかりません: {e}")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# 🔧 エラー自動修復ループ（⑤）
# ─────────────────────────────────────────────────────────
with gd_tabs[37]:
    st.markdown("### 🔧 エラー自動修復ループ")
    st.caption("Python / Godot / ファイル保存時のエラーを常時監視して自動修復する。")

    try:
        from error_healer import (
            start_heal_loop, start_file_watcher, stop_all,
            get_heal_stats, get_heal_history, get_error_patterns,
            queue_manual,
        )

        _bp     = st.session_state.get("target_path", "./")
        _anchor = st.session_state.get("anchor", "")
        _stats  = get_heal_stats()

        # ── 状態 ──────────────────────────────────────────
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            if _stats.get("running"):
                st.success("🟢 修復ループ: 稼働中")
            else:
                st.info("⚫ 修復ループ: 停止中")
        with col_s2:
            if _stats.get("watching"):
                st.success("🟢 ファイル監視: 稼働中")
            else:
                st.info("⚫ ファイル監視: 停止中")

        # 統計
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("修復成功",          _stats.get("healed", 0))
        c2.metric("修復失敗",          _stats.get("failed", 0))
        c3.metric("スキップ",          _stats.get("skipped", 0))
        c4.metric("学習済みパターン",  _stats.get("patterns_learned", 0))

        if _stats.get("queue_size", 0) > 0:
            st.warning(f"⏳ 修復キュー: {_stats['queue_size']}件待機中")

        st.divider()

        # ── 操作ボタン ────────────────────────────────────
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            if not _stats.get("running"):
                if st.button("▶️ 修復ループ起動",
                             use_container_width=True, key="start_heal"):
                    start_heal_loop(_bp, _anchor)
                    st.success("起動しました")
                    st.rerun()
            else:
                if st.button("⏹️ 停止", use_container_width=True,
                             key="stop_heal"):
                    stop_all()
                    st.rerun()

        with col_b2:
            if not _stats.get("watching"):
                if st.button("👁️ ファイル監視開始",
                             use_container_width=True, key="start_watch"):
                    start_file_watcher(_bp)
                    st.success("監視開始")
                    st.rerun()

        with col_b3:
            st.caption("")   # spacer

        st.divider()

        # ── 手動エラー登録 ────────────────────────────────
        with st.expander("✏️ 手動でエラーを登録", expanded=False):
            col_m1, col_m2 = st.columns([3, 1])
            with col_m1:
                _m_file = st.text_input("ファイル名", placeholder="Player.gd",
                                         key="m_file")
                _m_msg  = st.text_input("エラーメッセージ",
                                         placeholder="Invalid get index 'position' on base 'null'",
                                         key="m_msg")
            with col_m2:
                _m_line = st.number_input("行番号", min_value=0,
                                           value=0, key="m_line")
            _m_hint = st.text_input("修正ヒント（任意）", key="m_hint")

            if st.button("📥 キューに追加", key="manual_queue"):
                if _m_file and _m_msg:
                    queue_manual(_m_file, _m_msg, int(_m_line), _m_hint)
                    st.success("キューに追加しました")
                else:
                    st.warning("ファイル名とエラーメッセージは必須です")

        st.divider()

        # ── 修復履歴 ──────────────────────────────────────
        st.markdown("#### 📋 修復履歴")
        history = get_heal_history(n=15)
        if not history:
            st.info(
                "まだ修復履歴がありません。\n\n"
                "**使い方:**\n"
                "1. 「▶️ 修復ループ起動」でバックグラウンド起動\n"
                "2. 「👁️ ファイル監視」で保存時に自動チェック\n"
                "3. Godot接続タブと組み合わせると\n"
                "   ランタイムエラーを即座に自動修復"
            )
        else:
            for h in history:
                icon   = "✅" if h.get("success") else "❌"
                src    = {"godot":"🎮","python":"🐍","manual":"✏️",
                          "watcher":"👁️"}.get(h.get("source",""), "❓")
                st.caption(
                    f"{icon} {src} {h.get('time','')} — "
                    f"`{h.get('file','?')}:{h.get('line',0)}` "
                    f"{h.get('error','')[:60]}"
                )

        st.divider()

        # ── 学習済みパターン ──────────────────────────────
        patterns = get_error_patterns()
        if patterns:
            st.markdown("#### 🧠 学習済みエラーパターン")
            st.caption("過去の修復から学習した「よく起きるエラーとその修正方法」")
            for p in patterns[:8]:
                with st.container(border=True):
                    st.caption(
                        f"🔁 **{p['count']}回** — `{p['pattern'][:60]}`")
                    if p.get("hint"):
                        st.caption(f"💡 {p['hint'][:80]}")

    except ImportError as e:
        st.error(f"error_healer.py が見つかりません: {e}")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# 📄 ドキュメント自動同期タブ（⑥）
# ─────────────────────────────────────────────────────────
with gd_tabs[38]:
    st.markdown("### 📄 ドキュメント自動生成・同期")
    st.caption("コードが変わるたびに README / 設計書 / API仕様 / CHANGELOG / TODO を自動更新。")

    try:
        from doc_sync import (
            sync_docs, get_doc_status, get_changelog, DOC_FILES,
        )
        import os

        _bp     = st.session_state.get("target_path", "./")
        _anchor = st.session_state.get("anchor", "")
        _status = get_doc_status(_bp)

        # ── ドキュメント状態一覧 ──────────────────────────
        st.markdown("#### 📋 ドキュメント状態")

        doc_labels = {
            "readme":    ("📖", "README.md",    "プロジェクト概要・使い方"),
            "design":    ("🏛️", "DESIGN.md",   "設計書・アーキテクチャ"),
            "api":       ("⚙️", "API.md",       "全関数リファレンス"),
            "changelog": ("📝", "CHANGELOG.md", "変更履歴（自動追記）"),
            "todo":      ("✅", "TODO.md",      "バックログ連動TODO"),
        }

        for key, (icon, fname, desc_text) in doc_labels.items():
            s = _status.get(key, {})
            exists  = s.get("exists", False)
            updated = s.get("updated", "未生成")
            size    = s.get("size_kb", 0)
            needs   = s.get("needs_update", True)

            with st.container(border=True):
                col_d1, col_d2, col_d3 = st.columns([3, 2, 1])
                with col_d1:
                    status_icon = "🟡" if needs else "🟢" if exists else "⚫"
                    st.markdown(f"{status_icon} {icon} **{fname}**")
                    st.caption(desc_text)
                with col_d2:
                    if exists:
                        st.caption(f"更新: {updated}")
                        st.caption(f"サイズ: {size} KB")
                    else:
                        st.caption("未生成")
                with col_d3:
                    if exists:
                        doc_path = os.path.join(_bp, fname)
                        try:
                            with open(doc_path, encoding="utf-8") as f:
                                doc_text = f.read()
                            st.download_button(
                                "⬇️",
                                data=doc_text,
                                file_name=fname,
                                mime="text/markdown",
                                key=f"dl_{key}",
                            )
                        except Exception:
                            pass

        st.divider()

        # ── 同期ボタン ────────────────────────────────────
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            if st.button("🔄 変更分だけ同期",
                         use_container_width=True, key="sync_docs"):
                with st.spinner("ドキュメント生成中..."):
                    result = sync_docs(_bp, _anchor, force=False)
                if result.updated:
                    st.success(
                        f"✅ 更新: {', '.join(result.updated)}\n"
                        + (f"スキップ: {', '.join(result.skipped)}" if result.skipped else "")
                    )
                else:
                    st.info("変更なし（全てスキップ）")
                if result.failed:
                    st.warning(f"❌ 失敗: {', '.join(result.failed)}")
                st.rerun()

        with col_s2:
            if st.button("⚡ 全ドキュメントを強制再生成",
                         use_container_width=True, key="force_sync_docs"):
                with st.spinner("全ドキュメントを生成中（時間がかかります）..."):
                    result = sync_docs(_bp, _anchor, force=True)
                st.success(
                    f"✅ 完了: 更新{len(result.updated)} / 失敗{len(result.failed)}")
                st.rerun()

        st.divider()

        # ── ドキュメントプレビュー ─────────────────────────
        _preview_key = st.selectbox(
            "プレビュー",
            options=list(doc_labels.keys()),
            format_func=lambda k: doc_labels[k][1],
            key="doc_preview_sel",
        )
        _preview_path = os.path.join(_bp, DOC_FILES[_preview_key])
        if os.path.exists(_preview_path):
            with open(_preview_path, encoding="utf-8") as f:
                preview_text = f.read()
            with st.expander(
                f"📄 {DOC_FILES[_preview_key]} プレビュー",
                expanded=True
            ):
                st.markdown(preview_text[:3000]
                            + ("\n\n*（省略）*" if len(preview_text) > 3000 else ""))
        else:
            st.info(f"{DOC_FILES[_preview_key]} はまだ生成されていません")

        st.divider()

        # ── CHANGELOG ─────────────────────────────────────
        st.markdown("#### 📝 変更履歴（直近）")
        cl = get_changelog(_bp, n=15)
        if not cl:
            st.info(
                "まだ変更履歴がありません。\n\n"
                "タスクを実行するたびに自動で追記されます。"
            )
        else:
            for entry in cl:
                st.caption(
                    f"📌 `{entry.get('date','')}` "
                    f"**{entry.get('file','')}** — "
                    f"{entry.get('task','')[:70]}"
                )

    except ImportError as e:
        st.error(f"doc_sync.py が見つかりません: {e}")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# 🎵 音楽・SE自動生成タブ（⑦）
# ─────────────────────────────────────────────────────────
with gd_tabs[39]:
    st.markdown("### 🎵 音楽・SE自動生成")
    st.caption("プロシージャル生成（追加インストール不要）またはAudioCraftでBGM・SEを生成してGodotに配置。")

    try:
        from music_gen import (
            generate_bgm, generate_se, generate_batch,
            list_generated, generate_gdscript,
            HAS_AUDIOCRAFT, SE_GENERATORS, SCENE_PARAMS,
        )
        import os

        _bp = st.session_state.get("target_path", "./")

        # エンジン状態
        if HAS_AUDIOCRAFT:
            st.success("✅ AudioCraft 利用可能（高品質生成）")
        else:
            st.info("🔧 プロシージャル生成モード（numpy+scipy）— "
                    "AudioCraftを使うには `pip install audiocraft` が必要")

        st.divider()

        tab_bgm, tab_se, tab_batch, tab_list = st.tabs(
            ["🎼 BGM生成", "🔔 SE生成", "📦 一括生成", "📁 生成済み"])

        # ── BGM生成 ────────────────────────────────────────
        with tab_bgm:
            st.markdown("#### 🎼 BGM生成")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                _scene = st.selectbox(
                    "シーンタイプ",
                    list(SCENE_PARAMS.keys()),
                    format_func=lambda k: {
                        "title":"タイトル画面","field":"フィールド",
                        "battle":"通常戦闘","boss":"ボス戦",
                        "dungeon":"ダンジョン","victory":"勝利",
                        "gameover":"ゲームオーバー","ending":"エンディング",
                        "shop":"ショップ","mystery":"謎・不思議",
                    }.get(k, k),
                    key="bgm_scene"
                )
            with col_b2:
                _dur = st.slider("長さ（秒）", 5, 120,
                                  SCENE_PARAMS[_scene]["dur"],
                                  key="bgm_dur")

            _desc = st.text_input(
                "シーンの説明（任意・AIが自動でパラメータを調整）",
                placeholder="例：ラスボスとの決戦、絶望的だが希望もある壮大な戦闘BGM",
                key="bgm_desc"
            )

            if st.button("🎵 BGM生成", use_container_width=True,
                         key="gen_bgm"):
                with st.spinner(f"{_dur}秒のBGMを生成中..."):
                    result = generate_bgm(
                        _desc, _scene, _bp, float(_dur))
                if result.success:
                    st.success(f"✅ 生成完了: `{result.name}` ({result.engine})")
                    st.caption(f"保存先: {result.path}")
                    # 再生プレビュー
                    if os.path.exists(result.path):
                        with open(result.path, "rb") as f:
                            st.audio(f.read(), format="audio/wav")
                else:
                    st.error(f"❌ 生成失敗: {result.error}")

        # ── SE生成 ─────────────────────────────────────────
        with tab_se:
            st.markdown("#### 🔔 SE（効果音）生成")

            se_labels = {
                "attack":"⚔️ 攻撃","damage":"💥 ダメージ",
                "jump":"🦘 ジャンプ","land":"🏃 着地",
                "item":"✨ アイテム取得","coin":"🪙 コイン",
                "explosion":"💣 爆発","magic":"🔮 魔法",
                "door":"🚪 扉","ui_ok":"✅ UI決定",
                "ui_cancel":"❌ UIキャンセル","levelup":"⬆️ レベルアップ",
                "gameover_se":"💀 ゲームオーバー",
            }

            # グリッドレイアウトで全SE表示
            se_types = list(se_labels.keys())
            cols_per_row = 3
            for row_start in range(0, len(se_types), cols_per_row):
                row_types = se_types[row_start:row_start+cols_per_row]
                cols = st.columns(cols_per_row)
                for i, se_type in enumerate(row_types):
                    with cols[i]:
                        label = se_labels.get(se_type, se_type)
                        if st.button(label, key=f"se_{se_type}",
                                     use_container_width=True):
                            with st.spinner("生成中..."):
                                r = generate_se(se_type, _bp)
                            if r.success and os.path.exists(r.path):
                                with open(r.path, "rb") as f:
                                    st.audio(f.read(), format="audio/wav")
                                st.caption(f"✅ {r.name}")
                            else:
                                st.error(f"❌ {r.error}")

        # ── 一括生成 ────────────────────────────────────────
        with tab_batch:
            st.markdown("#### 📦 一括生成")
            st.caption("ゲームに必要な音声を一括で生成します")

            col_p1, col_p2 = st.columns(2)
            with col_p1:
                gen_all_se = st.checkbox("全SE（13種類）", value=True,
                                          key="batch_se")
            with col_p2:
                sel_bgms = st.multiselect(
                    "BGMシーン選択",
                    list(SCENE_PARAMS.keys()),
                    default=["title","field","battle","boss","gameover"],
                    format_func=lambda k: {
                        "title":"タイトル","field":"フィールド",
                        "battle":"戦闘","boss":"ボス",
                        "dungeon":"ダンジョン","victory":"勝利",
                        "gameover":"ゲームオーバー","ending":"エンディング",
                        "shop":"ショップ","mystery":"謎",
                    }.get(k, k),
                    key="batch_bgms"
                )

            total = (len(SE_GENERATORS) if gen_all_se else 0) + len(sel_bgms)
            st.caption(f"生成予定: {total}ファイル")

            if st.button(f"⚡ {total}ファイルを一括生成",
                         use_container_width=True, key="batch_gen"):
                requests = []
                if gen_all_se:
                    for se_type in SE_GENERATORS.keys():
                        requests.append({"type":"se","se_type":se_type})
                for scene in sel_bgms:
                    requests.append({"type":"bgm","scene":scene,"desc":""})

                progress = st.progress(0)
                status   = st.empty()
                results  = []
                for i, req in enumerate(requests):
                    status.caption(f"生成中 {i+1}/{len(requests)}...")
                    if req["type"] == "bgm":
                        r = generate_bgm("", req["scene"], _bp)
                    else:
                        r = generate_se(req["se_type"], _bp)
                    results.append(r)
                    progress.progress((i+1)/len(requests))

                ok = sum(1 for r in results if r.success)
                st.success(f"✅ 完了: {ok}/{len(results)}件成功")
                progress.empty()

        # ── 生成済み一覧 ────────────────────────────────────
        with tab_list:
            st.markdown("#### 📁 生成済みファイル")

            files = list_generated(_bp)
            if not files:
                st.info("まだ生成されたファイルがありません")
            else:
                st.caption(f"合計 {len(files)} ファイル")

                # GDScript生成ボタン
                if st.button("📄 AudioManager.gd を生成",
                             key="gen_audiomanager"):
                    gd_code = generate_gdscript(_bp)
                    am_path = os.path.join(_bp, "AudioManager.gd")
                    with open(am_path, "w", encoding="utf-8") as f:
                        f.write(gd_code)
                    st.success(f"✅ {am_path} を生成しました")
                    with st.expander("プレビュー"):
                        st.code(gd_code[:1500], language="gdscript")

                st.divider()

                for finfo in files[:20]:
                    fname = finfo.get("name","")
                    fpath = finfo.get("path","")
                    eng   = finfo.get("engine","")
                    desc  = finfo.get("desc","")
                    ts    = finfo.get("timestamp","")
                    icon  = "🎼" if fname.startswith("bgm_") else "🔔"
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.caption(
                                f"{icon} **{fname}** `{eng}` — {ts}")
                            if desc:
                                st.caption(f"　{desc[:60]}")
                        with c2:
                            if fpath and os.path.exists(fpath):
                                with open(fpath, "rb") as f:
                                    st.audio(f.read(), format="audio/wav")

    except ImportError as e:
        st.error(f"music_gen.py が見つかりません: {e}")
    except Exception as e:
        st.error(f"エラー: {e}")

# ─────────────────────────────────────────────────────────
# 🗂️ バージョン管理AIタブ（⑧）
# ─────────────────────────────────────────────────────────
with gd_tabs[40]:
    st.markdown("### 🗂️ バージョン管理AI")
    st.caption("タスク完了時に自動コミット。AIがメッセージを生成し、問題発生時は最適なロールバック先を提案する。")

    try:
        from gitops import (
            init_repo, commit_all, auto_commit,
            ai_commit_message, suggest_rollback, do_rollback,
            create_branch, merge_branch, get_branch_list,
            smart_tag, get_git_status, get_commit_log_rich,
            get_diff_summary, push_to_github, setup_github_remote,
        )
        import os

        _bp = st.session_state.get("target_path", "./")

        # ── 現在の状態 ───────────────────────────────────
        try:
            _git_status = get_git_status(_bp)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("ブランチ",       _git_status.get("branch","?"))
            c2.metric("未コミット変更",  len(_git_status.get("changed_files",[])))
            c3.metric("Push待ちコミット",_git_status.get("ahead",0))
            c4.metric("最新タグ",        _git_status.get("latest_tag","なし"))

            if _git_status.get("is_clean"):
                st.success("✅ 作業ツリーはクリーンです")
            else:
                changed = _git_status.get("changed_files",[])
                with st.expander(f"⚠️ {len(changed)}件の未コミット変更", expanded=False):
                    for f in changed[:20]:
                        icon = {"M":"✏️","A":"✅","D":"🗑️","?":"❓"}.get(
                            f.get("state","?")[:1], "📄")
                        st.caption(f"{icon} `{f['file']}`")
        except Exception as e:
            st.warning(f"Git状態取得失敗（初期化が必要かもしれません）: {e}")
            if st.button("🔧 Gitリポジトリを初期化", key="git_init"):
                init_repo(_bp)
                st.success("✅ 初期化しました")
                st.rerun()

        st.divider()

        tab_commit, tab_rollback, tab_branch, tab_tag, tab_remote = st.tabs([
            "📝 コミット", "⏪ ロールバック",
            "🌿 ブランチ", "🏷️ タグ", "☁️ リモート"
        ])

        # ── コミットタブ ────────────────────────────────
        with tab_commit:
            st.markdown("#### 📝 AIコミット")

            col_cm1, col_cm2 = st.columns([3, 1])
            with col_cm1:
                _task_hint = st.text_input(
                    "タスクの説明（任意・AIがメッセージを生成）",
                    placeholder="例：プレイヤーのジャンプ力を調整してゲームバランスを改善",
                    key="commit_hint"
                )
            with col_cm2:
                if st.button("🤖 メッセージ生成", key="gen_msg"):
                    with st.spinner("生成中..."):
                        msg = ai_commit_message(task_desc=_task_hint, path=_bp)
                    st.session_state["commit_msg"] = msg

            _msg = st.text_input(
                "コミットメッセージ",
                value=st.session_state.get("commit_msg", ""),
                key="commit_msg_input"
            )

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                if st.button("✅ コミット", use_container_width=True,
                             key="do_commit"):
                    msg_final = _msg or ai_commit_message(
                        task_desc=_task_hint, path=_bp)
                    result = auto_commit(_bp, task_desc=msg_final)
                    if result and result.success:
                        st.success(f"✅ `{result.hash}` — {result.message}")
                    elif result and result.error == "no_changes":
                        st.info("変更はありません")
                    else:
                        st.error(f"❌ {result.error if result else '失敗'}")
                    st.rerun()
            with col_c2:
                if st.button("🔄 git add . してコミット",
                             use_container_width=True, key="quick_commit"):
                    result = auto_commit(_bp, task_desc=_task_hint or "クイックセーブ")
                    if result and result.success:
                        st.success(f"✅ {result.message}")
                    else:
                        st.info("変更なし")

            st.divider()

            # コミット履歴
            st.markdown("#### 📋 コミット履歴")
            _log = get_commit_log_rich(_bp, n=20)
            if not _log:
                st.info("コミット履歴がありません")
            else:
                for entry in _log[:15]:
                    msg_icon = "✨" if "feat" in entry["message"] else \
                               "🔧" if "fix" in entry["message"] else \
                               "♻️" if "refactor" in entry["message"] else "🔨"
                    st.caption(
                        f"`{entry['hash']}` {entry['date']} "
                        f"{msg_icon} {entry['message'][:60]}"
                    )

        # ── ロールバックタブ ─────────────────────────────
        with tab_rollback:
            st.markdown("#### ⏪ AI ロールバック提案")
            st.caption("問題の説明を入力すると、AIがどのコミットに戻すべきかを提案します。")

            _problem = st.text_area(
                "現在の問題を説明してください",
                placeholder="例：昨日からプレイヤーが壁をすり抜けるようになった。おそらく当たり判定の変更が原因。",
                height=80, key="rollback_problem"
            )

            if st.button("🔍 ロールバック先を提案", key="suggest_rb",
                         use_container_width=True):
                with st.spinner("コミット履歴を分析中..."):
                    options = suggest_rollback(_bp, _problem)
                st.session_state["rb_options"] = options

            options = st.session_state.get("rb_options", [])
            if options:
                st.markdown("**AIの提案：**")
                for opt in options:
                    risk_color = {"low":"🟢","medium":"🟡","high":"🔴"}.get(
                        opt.get("risk","medium"), "⚪")
                    with st.container(border=True):
                        col_r1, col_r2 = st.columns([4, 1])
                        with col_r1:
                            st.markdown(
                                f"{risk_color} `{opt['hash']}` "
                                f"**{opt['date']}** — {opt['message'][:50]}"
                            )
                            st.caption(f"💡 理由: {opt.get('reason','')[:80]}")
                            st.caption(f"リスク: {opt.get('risk','?')}")
                        with col_r2:
                            if st.button("↩️ ここへ戻す",
                                         key=f"rb_{opt['hash']}"):
                                result = do_rollback(_bp, opt["hash"], soft=True)
                                if result["success"]:
                                    st.success("✅ ロールバック完了（softモード）")
                                else:
                                    st.error(f"❌ {result['message'][:60]}")
                                st.rerun()
            elif _problem:
                st.info("まず「ロールバック先を提案」ボタンを押してください")

            st.warning(
                "⚠️ ロールバックは**softモード**（変更をステージに残す）で実行されます。"
                "ファイルを完全に元に戻す場合はhardモードが必要です。"
            )

        # ── ブランチタブ ─────────────────────────────────
        with tab_branch:
            st.markdown("#### 🌿 ブランチ管理")

            _branches = get_branch_list(_bp)
            if _branches:
                st.markdown("**ブランチ一覧:**")
                for b in _branches[:10]:
                    icon = "▶️" if b.get("current") else "  "
                    st.caption(f"{icon} `{b['name']}`")
            else:
                st.info("ブランチ情報なし")

            st.divider()

            col_br1, col_br2 = st.columns(2)
            with col_br1:
                _feature_name = st.text_input(
                    "新機能名", placeholder="inventory-system",
                    key="new_branch")
                if st.button("🌿 ブランチ作成", key="create_branch",
                             use_container_width=True):
                    if _feature_name:
                        branch = create_branch(_bp, _feature_name)
                        st.success(f"✅ `{branch}` を作成・チェックアウト")
                        st.rerun()

            with col_br2:
                feature_branches = [
                    b["name"] for b in _branches
                    if b["name"].startswith("feature/")
                ]
                if feature_branches:
                    _merge_src = st.selectbox(
                        "マージするブランチ", feature_branches,
                        key="merge_branch_sel")
                    if st.button("🔀 mainにマージ", key="do_merge",
                                 use_container_width=True):
                        result = merge_branch(_bp, _merge_src)
                        if result["success"]:
                            st.success(f"✅ マージ完了")
                        else:
                            st.error(f"❌ {result['message'][:60]}")
                        st.rerun()

        # ── タグタブ ─────────────────────────────────────
        with tab_tag:
            st.markdown("#### 🏷️ バージョンタグ")
            st.caption("セマンティックバージョニング（v1.2.3）で自動管理")

            col_t1, col_t2, col_t3 = st.columns(3)
            with col_t1:
                if st.button("🔼 パッチ（バグ修正）\n+0.0.1",
                             key="tag_patch", use_container_width=True):
                    tag = smart_tag(_bp, "patch")
                    st.success(f"✅ タグ `{tag}` を作成") if tag else st.error("失敗")
                    st.rerun()
            with col_t2:
                if st.button("⬆️ マイナー（機能追加）\n+0.1.0",
                             key="tag_minor", use_container_width=True):
                    tag = smart_tag(_bp, "minor")
                    st.success(f"✅ タグ `{tag}` を作成") if tag else st.error("失敗")
                    st.rerun()
            with col_t3:
                if st.button("🚀 メジャー（大型更新）\n+1.0.0",
                             key="tag_major", use_container_width=True):
                    tag = smart_tag(_bp, "major")
                    st.success(f"✅ タグ `{tag}` を作成") if tag else st.error("失敗")
                    st.rerun()

        # ── リモートタブ ──────────────────────────────────
        with tab_remote:
            st.markdown("#### ☁️ GitHub 連携")
            grand = st.session_state.get("grand_state", {})

            _gh_url = st.text_input(
                "GitHub リポジトリURL",
                value=grand.get("github_url",""),
                placeholder="https://github.com/yourname/yourrepo.git",
                key="git_url"
            )
            _gh_token = st.text_input(
                "GitHub Personal Access Token",
                value=grand.get("github_token",""),
                type="password", key="git_token"
            )
            _gh_branch = st.text_input(
                "ブランチ", value="main", key="git_branch")

            col_gh1, col_gh2 = st.columns(2)
            with col_gh1:
                if st.button("🔗 リモートを設定", key="set_remote",
                             use_container_width=True):
                    if _gh_url:
                        res = setup_github_remote(
                            _gh_url, _gh_token, path=_bp)
                        if res["success"]:
                            st.success(res["message"])
                        else:
                            st.error(res["message"])
            with col_gh2:
                if st.button("☁️ GitHubへPush", key="do_push",
                             use_container_width=True):
                    with st.spinner("Push中..."):
                        res = push_to_github(
                            _gh_branch, _gh_token, _gh_url, path=_bp)
                    if res["success"]:
                        st.success(res["message"])
                    else:
                        st.error(res["message"])

    except ImportError as e:
        st.error(f"gitops.py が見つかりません: {e}")
    except Exception as e:
        st.error(f"エラー: {e}")
