"""
AIVtuber — settings_ui.py
Streamlit設定画面

起動: streamlit run settings_ui.py
"""

import json, sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from character import CharacterManager
from memory    import MemorySystem, INTIMACY_THRESHOLDS

st.set_page_config(
    page_title="AIVtuber 設定",
    page_icon="🎭",
    layout="wide",
)

# ── 初期化 ────────────────────────────────────────
@st.cache_resource
def get_managers():
    return CharacterManager(), MemorySystem()

chara, memory = get_managers()

st.title("🎭 AIVtuber 設定パネル")
st.caption("設定はリアルタイムで保存されます")

tabs = st.tabs([
    "🎭 キャラ設定",
    "💬 挨拶・反応",
    "💰 スパチャ設定",
    "🔤 ワード反応",
    "🚫 NGワード",
    "👥 視聴者管理",
    "📊 記憶・統計",
    "⚙️ システム設定",
])

# ══════════════════════════════════════════
# Tab 0: キャラ設定
# ══════════════════════════════════════════
with tabs[0]:
    st.markdown("### 🎭 キャラクター設定")
    st.caption("おおざっぱに決めてOK。細かい言い回しはAIが毎回変えてくれます。")

    c = chara.all()
    col1, col2 = st.columns(2)

    with col1:
        name = st.text_input("キャラ名", c["name"], key="name")
        age  = st.text_input("見た目・年齢感", c["age_image"], key="age")
        app  = st.text_input("外見の説明", c["appearance"], key="app")

    with col2:
        core = st.text_area("性格の核心（2〜3行）",
                             c["personality_core"], height=80, key="core")
        sub  = st.text_area("性格のサブ（追加の特徴）",
                             c["personality_sub"], height=80, key="sub")

    st.divider()
    col3, col4 = st.columns(2)
    with col3:
        speech = st.text_area("話し方・語尾の癖",
                               c["speech_style"], height=80, key="speech")
        laugh  = st.text_input("笑い方のスタイル",
                                c.get("laugh_style",""), key="laugh")
        fillers = st.text_input(
            "間投詞（カンマ区切り）",
            ", ".join(c.get("filler_words",[])), key="fillers")

    with col4:
        likes    = st.text_area("好きなもの（1行1項目）",
                                 "\n".join(c.get("likes",[])), height=80, key="likes")
        dislikes = st.text_area("嫌いなもの（1行1項目）",
                                 "\n".join(c.get("dislikes",[])), height=60, key="dislikes")

    st.divider()
    tease_style = st.text_area("いじりスタンス",
                                c.get("tease_style",""), height=60, key="tease")
    tease_limit = st.text_input("いじりの限界ライン",
                                 c.get("tease_limit",""), key="tease_limit")

    st.markdown("**絶対やらないこと（1行1項目）**")
    never = st.text_area("", "\n".join(c.get("never_do",[])),
                          height=100, key="never")

    if st.button("💾 キャラ設定を保存", key="save_chara",
                  use_container_width=True):
        chara.update({
            "name":            name,
            "age_image":       age,
            "appearance":      app,
            "personality_core": core,
            "personality_sub": sub,
            "speech_style":    speech,
            "laugh_style":     laugh,
            "filler_words":    [f.strip() for f in fillers.split(",") if f.strip()],
            "likes":           [l.strip() for l in likes.splitlines() if l.strip()],
            "dislikes":        [l.strip() for l in dislikes.splitlines() if l.strip()],
            "tease_style":     tease_style,
            "tease_limit":     tease_limit,
            "never_do":        [l.strip() for l in never.splitlines() if l.strip()],
        })
        st.success("✅ 保存しました")

    with st.expander("📋 現在のシステムプロンプトをプレビュー"):
        st.code(chara.build_system_prompt(), language="markdown")


# ══════════════════════════════════════════
# Tab 1: 挨拶・反応
# ══════════════════════════════════════════
with tabs[1]:
    st.markdown("### 💬 挨拶・配信中の反応設定")
    st.caption("雰囲気だけ決めればOK。毎回AIが違う表現で言ってくれます。")

    c = chara.all()
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 配信開始挨拶")
        g_vibe = st.text_area(
            "挨拶の雰囲気（おおざっぱに）",
            c.get("greeting_vibe",""), height=80, key="g_vibe",
            help="例: 元気よく、今日の気分を少し添える"
        )
        g_ex = st.text_area(
            "例文（参考用・AIはこれを参考にして毎回変える）",
            "\n".join(c.get("greeting_examples",[])), height=100, key="g_ex"
        )

    with col2:
        st.markdown("#### 配信終了挨拶")
        f_vibe = st.text_area(
            "締めの雰囲気（おおざっぱに）",
            c.get("farewell_vibe",""), height=80, key="f_vibe"
        )
        f_ex = st.text_area(
            "例文（参考用）",
            "\n".join(c.get("farewell_examples",[])), height=100, key="f_ex"
        )

    st.divider()
    st.markdown("#### 人間らしさ調整")
    col3, col4 = st.columns(2)
    with col3:
        delay_min = st.slider("返答最小遅延（秒）", 0.0, 3.0,
                               c.get("human_delay_min", 0.3), 0.1, key="dmin")
        delay_max = st.slider("返答最大遅延（秒）", 0.5, 5.0,
                               c.get("human_delay_max", 1.8), 0.1, key="dmax")
    with col4:
        skip_rate  = st.slider("コメント読み飛ばし率", 0.0, 0.5,
                                c.get("skip_comment_rate", 0.08), 0.01, key="skip")
        filler_rate = st.slider("フィラー返答率（「そうだね〜」系）", 0.0, 0.4,
                                 c.get("filler_rate", 0.12), 0.01, key="frate")

    t_min, t_max = c.get("tangent_interval", [8, 20])
    tangent = st.slider("革新（話題転換）の間隔（コメント数）",
                         3, 50, (t_min, t_max), key="tangent")

    if st.button("💾 挨拶・反応設定を保存", key="save_greet",
                  use_container_width=True):
        chara.update({
            "greeting_vibe":     g_vibe,
            "farewell_vibe":     f_vibe,
            "greeting_examples": [l.strip() for l in g_ex.splitlines() if l.strip()],
            "farewell_examples": [l.strip() for l in f_ex.splitlines() if l.strip()],
            "human_delay_min":   delay_min,
            "human_delay_max":   delay_max,
            "skip_comment_rate": skip_rate,
            "filler_rate":       filler_rate,
            "tangent_interval":  list(tangent),
        })
        st.success("✅ 保存しました")


# ══════════════════════════════════════════
# Tab 2: スパチャ設定
# ══════════════════════════════════════════
with tabs[2]:
    st.markdown("### 💰 スパチャ・投げ銭対応設定")
    c = chara.all()

    level = st.slider(
        "リアクションの大げさ度",
        0.0, 1.0, c.get("superchat_reaction_level", 0.8), 0.05,
        key="sc_level",
        help="0=さらっと感謝 / 1=めちゃくちゃ大げさに喜ぶ"
    )

    st.caption(f"現在の設定: {'😭 めちゃ大げさ' if level > 0.7 else '😊 普通に喜ぶ' if level > 0.4 else '🙂 さらっと感謝'}")

    style = st.text_area(
        "スパチャ時の反応スタイル（おおざっぱに）",
        c.get("superchat_style",""),
        height=80, key="sc_style",
        help="例: 名前を呼んで大げさに喜ぶ。何に使うか妄想する。"
    )

    st.divider()
    st.markdown("**金額別リアクション（任意）**")
    col1, col2, col3 = st.columns(3)
    sc_tiers = c.get("superchat_tiers", {
        "small":  "ありがとう！うれしい！",
        "medium": "えっ！？ありがとう！！泣く",
        "large":  "え！？！？こんなに！？！？配信やめていいですか！？（やめない）",
    })
    with col1:
        st.caption("少額（〜500円）")
        sc_small = st.text_area("", sc_tiers.get("small",""), height=80, key="sc_s")
    with col2:
        st.caption("中額（500〜5000円）")
        sc_med   = st.text_area("", sc_tiers.get("medium",""), height=80, key="sc_m")
    with col3:
        st.caption("高額（5000円〜）")
        sc_large = st.text_area("", sc_tiers.get("large",""), height=80, key="sc_l")

    if st.button("💾 スパチャ設定を保存", key="save_sc",
                  use_container_width=True):
        chara.update({
            "superchat_reaction_level": level,
            "superchat_style":          style,
            "superchat_tiers": {
                "small": sc_small, "medium": sc_med, "large": sc_large
            },
        })
        st.success("✅ 保存しました")


# ══════════════════════════════════════════
# Tab 3: ワード反応
# ══════════════════════════════════════════
with tabs[3]:
    st.markdown("### 🔤 特定ワード反応設定")
    st.caption("特定のゲーム名・話題が出たときの反応を設定できます。")

    reactions = chara.get_word_reactions()

    # 既存の反応一覧
    for i, r in enumerate(reactions):
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([2, 3, 2, 1])
            with col1:
                w = st.text_input("ワード", r.get("word",""), key=f"w_{i}")
            with col2:
                rx = st.text_input("反応スタイル", r.get("reaction",""), key=f"rx_{i}")
            with col3:
                em = st.selectbox("感情", ["excited","joy","surprise","shy","angry"],
                                   index=["excited","joy","surprise","shy","angry"].index(
                                       r.get("emotion","excited")), key=f"em_{i}")
            with col4:
                if st.button("🗑️", key=f"del_{i}"):
                    reactions.pop(i)
                    chara.update({"word_reactions": reactions})
                    st.rerun()
            reactions[i] = {"word": w, "reaction": rx, "emotion": em}

    st.divider()
    st.markdown("**新しいワード反応を追加**")
    col1, col2, col3 = st.columns([2, 3, 2])
    with col1:
        new_w  = st.text_input("ワード", placeholder="例: ポケモン", key="new_w")
    with col2:
        new_rx = st.text_input("反応スタイル",
                                placeholder="例: テンションが急上昇する", key="new_rx")
    with col3:
        new_em = st.selectbox("感情", ["excited","joy","surprise","shy"],
                               key="new_em")

    if st.button("➕ 追加して保存", key="add_word", use_container_width=True):
        if new_w and new_rx:
            reactions.append({"word": new_w, "reaction": new_rx, "emotion": new_em})
            chara.update({"word_reactions": reactions})
            st.success(f"✅ 「{new_w}」の反応を追加しました")
            st.rerun()

    if st.button("💾 一括保存", key="save_words", use_container_width=True):
        chara.update({"word_reactions": reactions})
        st.success("✅ 保存しました")


# ══════════════════════════════════════════
# Tab 4: NGワード
# ══════════════════════════════════════════
with tabs[4]:
    st.markdown("### 🚫 NGワード・荒らし対策")

    ng = chara.get("ng_words", [])
    ng_text = st.text_area(
        "NGワード（1行1ワード）\n含まれるコメントは自動スキップ",
        "\n".join(ng), height=200, key="ng_words"
    )

    st.divider()
    st.markdown("**荒らし自動検出**")
    col1, col2 = st.columns(2)
    with col1:
        spam_threshold = st.slider(
            "同一ユーザーの連投検出（N回/10秒）",
            2, 20, chara.get("spam_threshold", 5), key="spam"
        )
    with col2:
        auto_block = st.checkbox(
            "NGワード検出時に自動ブロック",
            chara.get("auto_block_ng", False), key="auto_block"
        )

    if st.button("💾 NG設定を保存", key="save_ng", use_container_width=True):
        chara.update({
            "ng_words": [w.strip() for w in ng_text.splitlines() if w.strip()],
            "spam_threshold": spam_threshold,
            "auto_block_ng":  auto_block,
        })
        st.success("✅ 保存しました")


# ══════════════════════════════════════════
# Tab 5: 視聴者管理
# ══════════════════════════════════════════
with tabs[5]:
    st.markdown("### 👥 視聴者管理")

    stats = memory.get_stats()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("総視聴者数",    stats["total_viewers"])
    col2.metric("VIP",          stats["vip_count"])
    col3.metric("常連",         stats["regular_count"])
    col4.metric("総配信回数",    stats["total_sessions"])

    st.divider()

    # 視聴者一覧
    rank_filter = st.selectbox(
        "ランクで絞り込み",
        ["全員", "VIP", "親友", "常連", "新規"], key="rank_filter")

    viewers = memory.get_viewer_list(
        None if rank_filter == "全員" else rank_filter)

    if not viewers:
        st.info("まだ視聴者データがありません。配信を始めると自動で蓄積されます。")
    else:
        for v in viewers[:30]:
            with st.expander(
                f"{v.rank} | **{v.display_name()}** "
                f"（来場{v.visits}回 / コメント{v.total_comments}件）"
            ):
                col1, col2 = st.columns(2)
                with col1:
                    new_nick = st.text_input(
                        "ニックネーム", v.nickname, key=f"nick_{v.username}")
                    new_rank = st.selectbox(
                        "ランク（手動）",
                        ["新規","常連","親友","VIP"],
                        index=["新規","常連","親友","VIP"].index(
                            v.rank if v.rank in ["新規","常連","親友","VIP"] else "新規"),
                        key=f"rank_{v.username}"
                    )
                    can_tease = st.checkbox(
                        "いじりOK", v.can_tease, key=f"tease_{v.username}")
                with col2:
                    notes = st.text_area(
                        "メモ", v.notes, height=80, key=f"notes_{v.username}")
                    st.caption(f"初来場: {v.first_seen} / 最終: {v.last_seen}")
                    if v.known_topics:
                        st.caption(f"話題: {', '.join(v.known_topics[:5])}")
                    if v.superchat_total > 0:
                        st.caption(f"💰 スパチャ: {v.superchat_total}回")

                if st.button("💾 保存", key=f"save_v_{v.username}"):
                    memory.set_viewer_rank(
                        v.username, new_rank,
                        nickname=new_nick,
                        notes=notes,
                        can_tease=can_tease
                    )
                    st.success("✅ 保存しました")


# ══════════════════════════════════════════
# Tab 6: 記憶・統計
# ══════════════════════════════════════════
with tabs[6]:
    st.markdown("### 📊 記憶・配信統計")

    stats = memory.get_stats()
    col1, col2 = st.columns(2)
    with col1:
        st.metric("総コメント数", f"{stats['total_comments']:,}")
        if stats["favorite_topics"]:
            st.markdown("**よく盛り上がる話題:**")
            for t in stats["favorite_topics"]:
                st.caption(f"  • {t}")
    with col2:
        sg = memory._self_growth
        if sg.get("peak_moments"):
            st.markdown("**思い出の名シーン:**")
            for m in sg["peak_moments"][-5:]:
                st.caption(f"  📌 {m}")

    st.divider()

    # 配信履歴
    st.markdown("**配信履歴（直近）**")
    sessions = memory._sessions[-10:]
    if not sessions:
        st.info("配信履歴がまだありません")
    else:
        for s in reversed(sessions):
            with st.container(border=True):
                st.caption(
                    f"📅 {s.get('start_time','')} "
                    f"({s.get('duration_min',0):.0f}分) "
                    f"💬 {s.get('total_comments',0)}件"
                )
                if s.get("mood_summary"):
                    st.caption(f"雰囲気: {s['mood_summary']}")
                if s.get("hot_topics"):
                    st.caption(f"話題: {', '.join(s['hot_topics'][:3])}")

    st.divider()
    st.markdown("**自己成長メモ**")
    personality_note = st.text_area(
        "最近の自分の傾向・変化（自由記述）",
        memory._self_growth.get("personality_notes",""),
        height=80, key="p_note"
    )
    if st.button("💾 メモを保存", key="save_note"):
        memory._self_growth["personality_notes"] = personality_note
        memory._save("self_growth.json", memory._self_growth)
        st.success("✅ 保存しました")

    if st.button("📌 今の盛り上がりを記録", key="record_peak"):
        peak_text = st.text_input("内容", key="peak_text")
        if peak_text:
            memory.add_peak_moment(peak_text)
            st.success("✅ 記録しました")


# ══════════════════════════════════════════
# Tab 7: システム設定
# ══════════════════════════════════════════
with tabs[7]:
    st.markdown("### ⚙️ システム設定")
    c = chara.all()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**TTS設定**")
        tts = st.selectbox("TTSエンジン",
                            ["voicevox","mock"],
                            index=0 if c.get("tts_engine","voicevox")=="voicevox" else 1,
                            key="tts_eng")
        spk = st.number_input("VOICEVOXスピーカーID",
                               0, 100, c.get("voicevox_speaker",3), key="vv_spk")

    with col2:
        st.markdown("**OBS設定**")
        obs_pw  = st.text_input("OBSパスワード", type="password", key="obs_pw")
        obs_src = st.text_input("アバターソース名",
                                 c.get("obs_avatar_source","AIVtuber_Avatar"),
                                 key="obs_src")

    st.divider()
    st.markdown("**チャット設定**")
    platform = st.selectbox("プラットフォーム",
                              ["mock","youtube","twitch"], key="platform")
    if platform == "youtube":
        yt_id = st.text_input("YouTube動画ID", key="yt_id")
    elif platform == "twitch":
        tw_ch  = st.text_input("Twitchチャンネル名", key="tw_ch")
        tw_tok = st.text_input("Twitchトークン", type="password", key="tw_tok")

    if st.button("💾 システム設定を保存", key="save_sys",
                  use_container_width=True):
        chara.update({
            "tts_engine":         tts,
            "voicevox_speaker":   int(spk),
            "obs_avatar_source":  obs_src,
            "platform":           platform,
        })
        st.success("✅ 保存しました")

    st.divider()
    st.markdown("**起動コマンド**")
    cmd = f"python main.py --platform {c.get('platform','mock')} --tts {c.get('tts_engine','voicevox')}"
    st.code(cmd, language="bash")
    st.caption("この設定で起動するコマンドです")
