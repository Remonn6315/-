"""
Blackwell Dev-OS — watchdog.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
自己監視 + 自動再起動 + 夜間バッチ（AIが夢を見る）

機能:
  1. Streamlitプロセス監視 → クラッシュで自動再起動
  2. 夜間バッチ: 眠っている間に過去ログを再学習して「明日の改善案」を生成
  3. システム状態（RAM・CPU・Ollama応答時間）の監視ログ

使い方:
  python watchdog.py --app app.py        # 監視デーモン起動
  python watchdog.py --dream             # 夜間バッチのみ実行

起動方法（推奨）:
  python watchdog.py --app app.py &      # バックグラウンドで起動
"""
import os, sys, time, json, subprocess, argparse, signal
from datetime import datetime
from pathlib import Path

LOG_PATH    = "./blackwell_watchdog.log"
DREAM_PATH  = "./blackwell_dreams.json"
PID_PATH    = "./blackwell_streamlit.pid"


def _log(msg: str):
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ============================================================
# Streamlit 自動再起動
# ============================================================

def start_streamlit(app_path: str = "app.py", port: int = 8501) -> subprocess.Popen:
    """Streamlitを起動してプロセスを返す"""
    cmd = [sys.executable, "-m", "streamlit", "run", app_path,
           "--server.port", str(port), "--server.headless", "true"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    _log(f"🚀 Streamlit起動: PID={proc.pid} port={port}")
    # PIDファイルに保存
    with open(PID_PATH, "w") as f:
        f.write(str(proc.pid))
    return proc


def watch_and_restart(app_path: str = "app.py", port: int = 8501,
                      max_restarts: int = 10, check_interval: int = 5):
    """Streamlitが落ちたら自動再起動するメインループ"""
    restart_count = 0
    proc = start_streamlit(app_path, port)

    def shutdown(signum, frame):
        _log("🛑 Watchdog終了シグナル受信")
        proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT,  shutdown)

    while True:
        time.sleep(check_interval)
        if proc.poll() is not None:
            restart_count += 1
            _log(f"💥 Streamlitがクラッシュ (終了コード={proc.returncode}) → 再起動 {restart_count}/{max_restarts}")
            if restart_count > max_restarts:
                _log("❌ 最大再起動回数に達しました。手動で確認してください。")
                break
            time.sleep(3)  # クールダウン
            proc = start_streamlit(app_path, port)
        else:
            # 生存確認
            if restart_count > 0:
                _log(f"✅ Streamlit稼働中 (PID={proc.pid}, 再起動={restart_count}回)")


# ============================================================
# システム状態監視
# ============================================================

def get_system_status() -> dict:
    """CPU・RAM・Ollama応答時間を取得"""
    status = {"timestamp": datetime.now().isoformat()}

    try:
        import psutil
        status["cpu_pct"]    = psutil.cpu_percent(interval=1)
        status["ram_pct"]    = psutil.virtual_memory().percent
        status["ram_gb"]     = psutil.virtual_memory().used / 1e9
        status["disk_free_gb"] = psutil.disk_usage(".").free / 1e9
    except ImportError:
        status["psutil"] = "未インストール（pip install psutil）"

    # Ollama応答時間チェック
    try:
        import ollama, time as _time
        t0  = _time.time()
        res = ollama.chat(model="qwen2.5-coder:7b",
                          messages=[{"role":"user","content":"ping"}])
        status["ollama_ms"] = int((_time.time() - t0) * 1000)
        status["ollama_ok"] = True
    except Exception as e:
        status["ollama_ok"] = False
        status["ollama_err"] = str(e)[:100]

    return status


# ============================================================
# 夜間バッチ（AIが夢を見る）
# ============================================================

def run_dream_batch(project_path: str = "./", model: str = "qwen2.5-coder:14b"):
    """
    Blackwellが「眠っている間」に自律的に振り返りと改善案生成を行う。

    処理内容:
      1. 過去の会話履歴・生成ログを読む
      2. エラーパターン・失敗記録を分析
      3. 「明日やるべき改善提案リスト」を生成
      4. blackwell_dreams.json に保存
    """
    _log("🌙 夜間バッチ開始（AIが夢を見る）")
    dreams = {"generated_at": datetime.now().isoformat(), "suggestions": []}

    # --- コンテキスト収集 ---
    context_parts = []

    # watchdogログ
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        crash_count = sum(1 for l in lines if "クラッシュ" in l)
        error_count = sum(1 for l in lines if "ERROR" in l)
        context_parts.append(
            f"システムログ: クラッシュ{crash_count}回, エラー{error_count}件（直近{len(lines)}行）"
        )

    # 学習済みエラーパターン
    learned_path = "./blackwell_learned_errors.json"
    if os.path.exists(learned_path):
        with open(learned_path, encoding="utf-8") as f:
            learned = json.load(f)
        context_parts.append(f"学習済みエラー: {len(learned)}パターン")
        top = sorted(learned, key=lambda x: -x.get("encounter_count",0))[:3]
        for p in top:
            context_parts.append(f"  頻出エラー: {p['title']} ({p.get('encounter_count',0)}回)")

    # 健康診断履歴（あれば）
    health_path = os.path.join(project_path, ".blackwell_health_history.json")
    if os.path.exists(health_path):
        with open(health_path, encoding="utf-8") as f:
            health_hist = json.load(f)
        if health_hist:
            last = health_hist[-1]
            context_parts.append(
                f"最新健康診断: スコア{last.get('score',0)} 重大{last.get('critical',0)}件"
            )

    context = "\n".join(context_parts) or "（初回実行: 履歴なし）"

    # --- AI に改善提案を生成させる ---
    try:
        import ollama
        prompt = (
            "あなたはBlackwell Dev-OSの自己改善AIです。\n"
            "以下のシステム状況を読んで、明日の開発で優先すべき改善提案を5件生成してください。\n\n"
            f"【システム状況】\n{context}\n\n"
            "出力形式（JSONのみ）:\n"
            '[\n  {"priority": 1, "title": "改善タイトル", '
            '"reason": "なぜ必要か", "action": "具体的なアクション"},\n  ...\n]\n'
            "JSON のみ出力。前置きや説明は不要。"
        )
        res = ollama.chat(model=model, messages=[{"role":"user","content":prompt}])
        raw = res["message"]["content"]

        import re
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            suggestions = json.loads(m.group(0))
            dreams["suggestions"] = suggestions
            _log(f"🌙 改善提案 {len(suggestions)}件を生成")
        else:
            dreams["raw"] = raw[:500]
            _log("🌙 JSON抽出失敗 → rawで保存")
    except Exception as e:
        dreams["error"] = str(e)
        _log(f"🌙 AI生成失敗: {e}")

    # --- 保存 ---
    # 履歴として蓄積
    all_dreams = []
    if os.path.exists(DREAM_PATH):
        try:
            with open(DREAM_PATH, encoding="utf-8") as f:
                all_dreams = json.load(f)
            if not isinstance(all_dreams, list):
                all_dreams = [all_dreams]
        except Exception:
            all_dreams = []

    all_dreams.append(dreams)
    all_dreams = all_dreams[-30:]  # 直近30回分

    with open(DREAM_PATH, "w", encoding="utf-8") as f:
        json.dump(all_dreams, f, ensure_ascii=False, indent=2)

    _log(f"🌙 夜間バッチ完了 → {DREAM_PATH}")
    return dreams


def get_latest_dreams() -> list:
    """最新の夜間バッチ結果を返す（UI表示用）"""
    if not os.path.exists(DREAM_PATH):
        return []
    try:
        with open(DREAM_PATH, encoding="utf-8") as f:
            all_dreams = json.load(f)
        if all_dreams:
            latest = all_dreams[-1]
            return latest.get("suggestions", [])
    except Exception:
        pass
    return []


def get_watchdog_log(n: int = 50) -> list:
    """Watchdogログの直近n行を返す"""
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, encoding="utf-8", errors="ignore") as f:
        return f.readlines()[-n:]


# ============================================================
# CLI エントリポイント
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Blackwell Watchdog")
    parser.add_argument("--app",    default="app.py", help="Streamlitアプリのパス")
    parser.add_argument("--port",   default=8501, type=int)
    parser.add_argument("--dream",  action="store_true", help="夜間バッチのみ実行")
    parser.add_argument("--status", action="store_true", help="システム状態を表示")
    args = parser.parse_args()

    if args.dream:
        run_dream_batch()
    elif args.status:
        s = get_system_status()
        print(json.dumps(s, ensure_ascii=False, indent=2))
    else:
        watch_and_restart(args.app, args.port)
