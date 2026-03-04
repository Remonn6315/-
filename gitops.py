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
