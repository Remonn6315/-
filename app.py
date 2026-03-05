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
    "dark_mode":         True,
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

# ── MODELS dict を session_state から毎回同期（これが根本修正）──
MODELS["planner"]   = st.session_state.model_planner
MODELS["coder"]     = st.session_state.model_coder
MODELS["refiner"]   = st.session_state.model_refiner
MODELS["optimizer"] = st.session_state.model_optimizer
MODELS["chat"]      = st.session_state.model_chat

if not st.session_state.init:
    init_repo()
    st.session_state.init = True

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
    f"⚓ 主軸: {st.session_state.project_anchor[:40]}..."
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


    new_anchor = st.text_area(
        "AIへの絶対命令セット", value=st.session_state.project_anchor, height=150
    )
    if st.sidebar.button("🧠 主軸を固定する", use_container_width=True):
        st.session_state.project_anchor = new_anchor
        st.sidebar.success("✅ 記憶基盤を更新しました")

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
    if st.button("🌙 ダーク", use_container_width=True, key="btn_dark",
                 type="primary" if is_dark else "secondary"):
        st.session_state.dark_mode = True; st.rerun()
with col_dm2:
    if st.button("☀️ ホワイト", use_container_width=True, key="btn_white",
                 type="primary" if not is_dark else "secondary"):
        st.session_state.dark_mode = False; st.rerun()

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
 tab_monitor_tab, tab_preview, tab_log) = st.tabs([
    "🚀 総合",
    "💬 戦略会議室",
    "📚 知識",
    "💡 改善",
    "🧠 記憶",
    "🎭 AIVtuber",
    "🔍 監視",
    "🖼️ プレビュー",
    "📜 ログ",
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
                        anchor=st.session_state.project_anchor,
                        use_internet=st.session_state.use_internet,
                    )
                except TypeError:
                    reply = chat_with_persona(
                        message=sogo_in,
                        persona=st.session_state.persona,
                        history=st.session_state.chat_messages[-10:],
                        anchor=st.session_state.project_anchor,
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
                            anchor=st.session_state.project_anchor,
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
                                anchor=st.session_state.project_anchor, max_cycles=2
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

        # ── ① プロジェクト主軸 ──────────────────────
        st.markdown("#### ⚓ ゲーム主軸")
        anchor_box = st.container(border=True)
        with anchor_box:
            st.caption("AIがこの主軸に従いながら作ります")
            new_anchor = st.text_area(
                "主軸",
                value=st.session_state.project_anchor,
                height=120,
                label_visibility="collapsed",
                key="main_anchor_edit",
                placeholder="例: ローグライクRPG。プレイヤーは一歩の重みを感じる重厚な操作感。"
            )
            if new_anchor != st.session_state.project_anchor:
                if st.button("✅ 主軸を更新", use_container_width=True, key="anchor_update_main"):
                    st.session_state.project_anchor = new_anchor
                    st.success("主軸を更新しました")
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
                            anchor=st.session_state.project_anchor
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
                            anchor=st.session_state.project_anchor,
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
                                "【主軸】" + st.session_state.project_anchor + "\n\n"
                                "【コード】\n" + st.session_state.last_result[:2000] + "\n\n"
                                "以下の形式で回答:\n"
                                "面白さ: ★★★☆☆（5段階）\n"
                                "主軸との一致: ★★★★☆\n"
                                "バグリスク: 低/中/高\n"
                                "一言評価: [30文字]\n"
                                "改善余地: あり/なし"
                            ),
                            persona="厳格なゲームディレクター。簡潔に評価のみ出力。",
                            anchor=st.session_state.project_anchor
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
            full_prompt = (
                f"【プロジェクト主軸】\n{st.session_state.project_anchor}\n\n"
                f"【稼働モード】\n{app_mode}\n\n"
                f"【指示】\n{prompt}"
            )
            with st.spinner(f"🔄 生成中... (最大{st.session_state.max_cycles}サイクル)"):
                result = autonomous_dev(
                    goal=full_prompt,
                    auto_write=st.session_state.auto_write,
                    save_path=st.session_state.target_path,
                    anchor=st.session_state.project_anchor,
                    history=st.session_state.messages[-10:],
                    max_cycles=st.session_state.max_cycles
                )
                st.session_state.last_result  = result
                st.session_state.last_log     = get_execution_log()
                st.session_state.thinking_log = get_execution_log()
                # 生成ログに追加
                import re as _re2
                built_files = _re2.findall(r"\[OK\]\s+([\w./\\-]+\.\w+)", result)
                if built_files:
                    st.session_state.build_log.extend(built_files)
                    st.session_state.build_log = st.session_state.build_log[-30:]  # 直近30件

            st.session_state.messages.append({"role": "assistant", "content": result})
            # 品質チェックフラグをリセット
            st.session_state.quality_check_result = ""
            st.session_state["quality_needs_improve"] = False
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
                            anchor=st.session_state.project_anchor
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
                            anchor=st.session_state.project_anchor,
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
                        anchor=st.session_state.project_anchor
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
                        anchor=st.session_state.project_anchor,
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
                anchor=st.session_state.project_anchor
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
                    save_path=save_path, anchor=st.session_state.project_anchor
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
                                anchor=st.session_state.project_anchor, max_cycles=2
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
                                        goal=f"【主軸】\n{st.session_state.project_anchor}\n\n{item}",
                                        auto_write=st.session_state.auto_write,
                                        save_path=save_path,
                                        anchor=st.session_state.project_anchor,
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
