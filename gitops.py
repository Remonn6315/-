"""
Blackwell Dev-OS - gitops.py (完全版 v2.0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 1 追加:
  - GitHub リモートリポジトリへのpush
  - GitHub からのclone
  - GitHub Personal Access Token による認証
  - リモートURL設定

app.py / engine.py からインポートされる関数（全5つ）:
  init_repo()                    - ローカルGit初期化
  commit_all(message)            - ステージング & コミット
  get_git_log(max_entries)       - コミット履歴取得
  setup_github_remote(url, token)- GitHub リモート設定
  push_to_github(branch, token)  - GitHubへpush
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import subprocess
import os


def _run(cmd, cwd=None):
    """コマンドを実行して (returncode, stdout, stderr) を返す。"""
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=cwd
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def init_repo(path=None):
    """Git リポジトリを初期化する。すでに存在する場合は何もしない。"""
    subprocess.run(["git", "init"], capture_output=True, cwd=path)


def commit_all(message, path=None):
    """すべての変更をステージングしてコミットする。"""
    subprocess.run(["git", "add", "."],          capture_output=True, cwd=path)
    subprocess.run(["git", "commit", "-m", message], capture_output=True, cwd=path)


def get_git_log(max_entries=20, path=None):
    """
    Git のコミット履歴を返す。
    戻り値: "ハッシュ | 日付 | メッセージ" 形式の文字列
    """
    try:
        code, out, err = _run([
            "git", "log",
            f"--max-count={max_entries}",
            "--pretty=format:%h | %ad | %s",
            "--date=short",
        ], cwd=path)
        return out if out else "コミット履歴なし"
    except Exception as e:
        return f"Git 履歴取得エラー: {e}"


def setup_github_remote(repo_url, token="", path=None):
    """
    GitHub リモートリポジトリを設定する。

    引数:
        repo_url : https://github.com/username/repo.git
        token    : GitHub Personal Access Token（HTTPS認証用）
        path     : Gitリポジトリのパス

    戻り値: {"success": bool, "message": str}
    """
    try:
        # tokenがある場合はURL埋め込み認証形式に変換
        if token and "github.com" in repo_url:
            # https://github.com/... → https://token@github.com/...
            auth_url = repo_url.replace("https://", f"https://{token}@")
        else:
            auth_url = repo_url

        # 既存のoriginを削除して再設定
        _run(["git", "remote", "remove", "origin"], cwd=path)
        code, out, err = _run(
            ["git", "remote", "add", "origin", auth_url], cwd=path
        )
        if code != 0:
            return {"success": False, "message": f"リモート設定失敗: {err}"}

        return {"success": True, "message": f"✅ GitHubリモート設定完了: {repo_url}"}

    except Exception as e:
        return {"success": False, "message": f"エラー: {e}"}


def push_to_github(branch="main", token="", repo_url="", path=None):
    """
    GitHubへ push する。

    引数:
        branch   : プッシュするブランチ名（デフォルト: main）
        token    : GitHub Personal Access Token
        repo_url : リポジトリURL（新規設定する場合）
        path     : Gitリポジトリのパス

    戻り値: {"success": bool, "message": str}
    """
    try:
        # リモートURLが指定されていれば先に設定
        if repo_url:
            setup_result = setup_github_remote(repo_url, token=token, path=path)
            if not setup_result["success"]:
                return setup_result

        # まず現在のブランチを確認・main に設定
        _run(["git", "branch", "-M", branch], cwd=path)

        # push実行
        code, out, err = _run(
            ["git", "push", "-u", "origin", branch], cwd=path
        )

        if code == 0:
            return {"success": True, "message": f"✅ GitHubへのpush成功 (branch: {branch})"}
        else:
            # よくあるエラーをわかりやすく説明
            if "rejected" in err:
                return {"success": False, "message": "❌ push拒否。リモートの変更をpullしてから再試行してください。"}
            if "Authentication" in err or "403" in err:
                return {"success": False, "message": "❌ 認証失敗。GitHub Personal Access Tokenを確認してください。"}
            if "Repository not found" in err:
                return {"success": False, "message": "❌ リポジトリが見つかりません。URLを確認してください。"}
            return {"success": False, "message": f"❌ push失敗: {err[:200]}"}

    except Exception as e:
        return {"success": False, "message": f"エラー: {e}"}


def get_remote_url(path=None):
    """現在設定されているリモートURLを返す。未設定なら空文字。"""
    try:
        code, out, err = _run(["git", "remote", "get-url", "origin"], cwd=path)
        if code == 0:
            # tokenを含むURLからtokenを除去して表示
            return re.sub(r"https://[^@]+@", "https://", out) if out else ""
        return ""
    except Exception:
        return ""


# re をインポート（get_remote_url で使用）
import re


# ================================================================
# ⑧ バージョン管理AI — gitops.py v3.0 追加分
# ================================================================
# 追加機能:
#   auto_commit(path, task_desc, files_changed) → CommitResult
#   ai_commit_message(diff_text, task_desc)     → str
#   suggest_rollback(path, problem_desc)        → list[RollbackOption]
#   create_branch(path, feature, anchor)        → str
#   smart_tag(path, version_type)              → str
#   get_diff_summary(path, commit_a, commit_b) → str
#   get_branch_list(path)                      → list
#   get_commit_detail(path, hash)              → dict
# ================================================================

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class CommitResult:
    hash:      str
    message:   str
    files:     list
    success:   bool
    error:     str = ""


@dataclass
class RollbackOption:
    hash:      str
    date:      str
    message:   str
    reason:    str      # なぜここに戻すべきか
    risk:      str      # "low" / "medium" / "high"


# ─── AIコミットメッセージ生成 ────────────────────────────────

def ai_commit_message(diff_text: str = "",
                       task_desc: str = "",
                       path: str = None) -> str:
    """
    AIがdiffとタスク説明から適切なコミットメッセージを生成する。
    Ollamaが使えない場合は自動生成のフォールバック。
    """
    if not diff_text and path:
        _, diff_text, _ = _run(["git", "diff", "--cached", "--stat"], cwd=path)
        if not diff_text:
            _, diff_text, _ = _run(["git", "diff", "--stat"], cwd=path)

    # Ollamaで生成
    try:
        import ollama
        prompt = (
            "以下の情報から、Gitコミットメッセージを1行で生成してください。\n"
            "フォーマット: <絵文字> <種別>: <内容>\n"
            "種別例: feat(機能追加) fix(バグ修正) refactor(整理) docs(ドキュメント) style(見た目)\n\n"
        )
        if task_desc:
            prompt += f"タスク説明: {task_desc[:200]}\n"
        if diff_text:
            prompt += f"変更内容:\n{diff_text[:800]}\n"
        prompt += "\n1行のコミットメッセージのみ出力してください（前置き不要）。"

        res = ollama.chat(
            model="qwen2.5-coder:14b",
            messages=[{"role": "user", "content": prompt}]
        )
        msg = res["message"]["content"].strip()
        # 複数行になった場合は最初の1行だけ
        msg = msg.splitlines()[0].strip('"\'')
        return msg[:100] if msg else _fallback_message(task_desc, diff_text)
    except Exception:
        return _fallback_message(task_desc, diff_text)


def _fallback_message(task_desc: str, diff_text: str) -> str:
    """Ollama不使用時の自動コミットメッセージ"""
    if task_desc:
        # タスク説明から自動生成
        desc = task_desc[:60].strip()
        if any(k in desc for k in ["fix","修正","バグ","error","エラー"]):
            return f"🔧 fix: {desc}"
        if any(k in desc for k in ["add","追加","新しい","新機能","implement"]):
            return f"✨ feat: {desc}"
        if any(k in desc for k in ["refactor","整理","clean","リファクタ"]):
            return f"♻️ refactor: {desc}"
        if any(k in desc for k in ["doc","ドキュメント","readme","README"]):
            return f"📝 docs: {desc}"
        return f"🔨 update: {desc}"
    return f"🤖 auto: Blackwell自動コミット {datetime.now().strftime('%H:%M')}"


# ─── 自動コミット ────────────────────────────────────────────

def auto_commit(path: str,
                task_desc: str = "",
                files_changed: list = None) -> CommitResult:
    """
    タスク完了後に自動でステージング→AIメッセージ生成→コミット。
    engine.py の process_task 完了後に呼ぶ。
    """
    # 変更があるか確認
    rc, status, _ = _run(["git", "status", "--short"], cwd=path)
    if rc != 0:
        # git管理されていない → 初期化してからコミット
        init_repo(path)
        _run(["git", "status", "--short"], cwd=path)

    if not status:
        return CommitResult(hash="", message="変更なし",
                            files=[], success=False,
                            error="no_changes")

    # 特定ファイルのみステージング（指定があれば）
    if files_changed:
        for f in files_changed:
            _run(["git", "add", f], cwd=path)
    else:
        _run(["git", "add", "."], cwd=path)

    # AIでコミットメッセージ生成
    message = ai_commit_message(task_desc=task_desc, path=path)

    # コミット実行
    rc, out, err = _run(["git", "commit", "-m", message], cwd=path)
    if rc != 0:
        # コミット失敗（名前・メールが未設定の可能性）
        _run(["git", "config", "user.email", "blackwell@local"], cwd=path)
        _run(["git", "config", "user.name",  "Blackwell Dev-OS"], cwd=path)
        rc, out, err = _run(["git", "commit", "-m", message], cwd=path)

    # コミットハッシュを取得
    _, commit_hash, _ = _run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=path)

    # 変更されたファイル一覧
    _, files_out, _ = _run(
        ["git", "diff-tree", "--no-commit-id", "-r",
         "--name-only", commit_hash],
        cwd=path)
    changed = [f for f in files_out.splitlines() if f]

    success = rc == 0
    if success:
        print(f"[gitops] ✅ コミット: {commit_hash} — {message}")
    else:
        print(f"[gitops] ❌ コミット失敗: {err[:80]}")

    return CommitResult(
        hash=commit_hash, message=message,
        files=changed, success=success,
        error=err[:100] if not success else "",
    )


# ─── ロールバック提案 ────────────────────────────────────────

def suggest_rollback(path: str,
                      problem_desc: str = "") -> list:
    """
    問題の説明から、最適なロールバック先をAIが提案する。

    Returns: list[dict] — 提案一覧（理由・リスク付き）
    """
    # 直近20コミットを取得
    rc, log_out, _ = _run([
        "git", "log",
        "--max-count=20",
        "--pretty=format:%h|%ad|%s",
        "--date=short",
    ], cwd=path)

    if rc != 0 or not log_out:
        return []

    commits = []
    for line in log_out.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({
                "hash": parts[0], "date": parts[1], "message": parts[2]})

    if not commits:
        return []

    # Ollamaで最適なロールバック先を提案
    try:
        import ollama
        commit_list = "\n".join([
            f"{i+1}. [{c['hash']}] {c['date']} — {c['message']}"
            for i, c in enumerate(commits)
        ])
        prompt = (
            f"現在のゲーム開発プロジェクトで以下の問題が起きています:\n"
            f"問題: {problem_desc or '動作がおかしい'}\n\n"
            f"コミット履歴（新しい順）:\n{commit_list}\n\n"
            "どのコミットにロールバックすると問題が解決しそうか、上位3件を提案してください。\n"
            "JSONのみ出力:\n"
            '[\n'
            '  {"index": 1から始まる番号, "reason": "なぜここに戻すべきか", "risk": "low/medium/high"}\n'
            ']\n'
        )
        res = ollama.chat(
            model="qwen2.5-coder:14b",
            messages=[{"role": "user", "content": prompt}]
        )
        raw = res["message"]["content"]
        m   = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            suggestions = json.loads(m.group(0))
            result = []
            for s in suggestions[:3]:
                idx = int(s.get("index", 1)) - 1
                if 0 <= idx < len(commits):
                    c = commits[idx]
                    result.append({
                        "hash":    c["hash"],
                        "date":    c["date"],
                        "message": c["message"],
                        "reason":  s.get("reason", ""),
                        "risk":    s.get("risk", "medium"),
                    })
            return result
    except Exception:
        pass

    # フォールバック: 直近3件をそのまま返す
    return [
        {"hash": c["hash"], "date": c["date"],
         "message": c["message"],
         "reason": f"{i+1}つ前のコミット",
         "risk": "low" if i == 0 else "medium"}
        for i, c in enumerate(commits[1:4])
    ]


def do_rollback(path: str, commit_hash: str,
                 soft: bool = True) -> dict:
    """
    指定コミットにロールバックする。
    soft=True: ファイルを戻してステージングに残す（安全）
    soft=False: ハードリセット（破壊的）
    """
    mode = "--soft" if soft else "--hard"
    rc, out, err = _run(
        ["git", "reset", mode, commit_hash], cwd=path)
    return {
        "success": rc == 0,
        "message": out or err,
        "mode":    "soft" if soft else "hard",
    }


# ─── ブランチ管理 ────────────────────────────────────────────

def create_branch(path: str,
                   feature: str,
                   anchor: str = "") -> str:
    """
    機能名から適切なブランチ名を生成して作成する。
    Returns: 作成したブランチ名
    """
    # ブランチ名を安全な文字列に変換
    branch_name = re.sub(r"[^\w\-]", "-",
                          feature.lower().replace(" ", "-"))
    branch_name = re.sub(r"-+", "-", branch_name).strip("-")
    branch_name = f"feature/{branch_name[:40]}"

    rc, _, err = _run(
        ["git", "checkout", "-b", branch_name], cwd=path)
    if rc != 0:
        # すでに存在する場合はチェックアウトだけ
        _run(["git", "checkout", branch_name], cwd=path)
    print(f"[gitops] ブランチ作成/切替: {branch_name}")
    return branch_name


def merge_branch(path: str, branch: str,
                  delete_after: bool = True) -> dict:
    """ブランチをmainにマージする"""
    _run(["git", "checkout", "main"], cwd=path)
    rc, out, err = _run(
        ["git", "merge", "--no-ff", branch,
         "-m", f"🔀 merge: {branch}"], cwd=path)
    if rc == 0 and delete_after:
        _run(["git", "branch", "-d", branch], cwd=path)
    return {"success": rc == 0, "message": out or err}


def get_branch_list(path: str) -> list:
    """ブランチ一覧を返す"""
    rc, out, _ = _run(["git", "branch", "-a"], cwd=path)
    if rc != 0:
        return []
    branches = []
    for line in out.splitlines():
        name    = line.strip().lstrip("* ")
        current = line.startswith("*")
        branches.append({"name": name, "current": current})
    return branches


# ─── タグ・バージョン ────────────────────────────────────────

def smart_tag(path: str, version_type: str = "patch") -> str:
    """
    直近のタグから次のバージョンを自動計算してタグを打つ。
    version_type: "major" / "minor" / "patch"
    Returns: 新しいタグ名
    """
    rc, last_tag, _ = _run(
        ["git", "describe", "--tags", "--abbrev=0"], cwd=path)

    if rc != 0 or not last_tag:
        new_tag = "v0.1.0"
    else:
        # v1.2.3 形式をパース
        m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", last_tag.strip())
        if m:
            major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if version_type == "major":
                major += 1; minor = 0; patch = 0
            elif version_type == "minor":
                minor += 1; patch = 0
            else:
                patch += 1
            new_tag = f"v{major}.{minor}.{patch}"
        else:
            new_tag = "v0.1.0"

    _, _, commit_hash = _run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=path)

    rc, _, err = _run(
        ["git", "tag", "-a", new_tag,
         "-m", f"Version {new_tag} — Blackwell Dev-OS"],
        cwd=path)

    if rc == 0:
        print(f"[gitops] タグ作成: {new_tag}")
        return new_tag
    print(f"[gitops] タグ作成失敗: {err}")
    return ""


def get_latest_tag(path: str) -> str:
    rc, tag, _ = _run(
        ["git", "describe", "--tags", "--abbrev=0"], cwd=path)
    return tag.strip() if rc == 0 else ""


# ─── 差分・詳細 ─────────────────────────────────────────────

def get_diff_summary(path: str,
                      commit_a: str = "HEAD~1",
                      commit_b: str = "HEAD") -> str:
    """2つのコミット間の差分サマリーを返す"""
    rc, diff, _ = _run(
        ["git", "diff", "--stat", commit_a, commit_b], cwd=path)
    return diff if rc == 0 else ""


def get_commit_detail(path: str, commit_hash: str) -> dict:
    """コミットの詳細情報を返す"""
    rc, out, _ = _run([
        "git", "show",
        "--stat",
        f"--pretty=format:hash=%H%nmessage=%s%nauthor=%an%ndate=%ad",
        "--date=iso",
        commit_hash,
    ], cwd=path)
    if rc != 0:
        return {}
    info = {}
    for line in out.splitlines():
        if "=" in line and not line.startswith(" "):
            k, _, v = line.partition("=")
            info[k.strip()] = v.strip()
    return info


def get_git_status(path: str) -> dict:
    """現在のgit状態を構造化して返す"""
    rc, status, _ = _run(["git", "status", "--short"], cwd=path)
    rc2, branch, _ = _run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path)
    rc3, ahead, _ = _run(
        ["git", "rev-list", "--count", "HEAD@{u}..HEAD"], cwd=path)

    files = []
    for line in (status or "").splitlines():
        if len(line) >= 2:
            state = line[:2].strip()
            fname = line[3:].strip()
            files.append({"state": state, "file": fname})

    return {
        "branch":       branch.strip() if rc2 == 0 else "unknown",
        "changed_files": files,
        "ahead":        int(ahead.strip()) if rc3 == 0 and ahead.strip().isdigit() else 0,
        "is_clean":     len(files) == 0,
        "latest_tag":   get_latest_tag(path),
    }


def get_commit_log_rich(path: str, n: int = 30) -> list:
    """構造化されたコミット履歴を返す（app.pyの表示用）"""
    rc, out, _ = _run([
        "git", "log",
        f"--max-count={n}",
        "--pretty=format:%h|%ad|%s|%an",
        "--date=short",
    ], cwd=path)
    if rc != 0 or not out:
        return []
    result = []
    for line in out.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            result.append({
                "hash":    parts[0],
                "date":    parts[1],
                "message": parts[2],
                "author":  parts[3],
            })
    return result
