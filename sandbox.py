"""
Blackwell Dev-OS - sandbox.py (完全版 v4.0)
engine.py からインポートされる関数:
  - run_safe(code) : コードを安全なサブプロセスで実行し、エラーがあれば文字列で返す
"""

import subprocess
import tempfile
import os
import sys
import ast

# Windows 互換のためのインポート処理
try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False


def _check_syntax(code):
    """構文チェック。エラーがあればエラーメッセージを返す。なければ None。"""
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return "SyntaxError: {} (line {})".format(e.msg, e.lineno)


def _generate_wrapped_code(original_code):
    """実行コードをラップしてリソース制限を内側からかける。"""
    if HAS_RESOURCE:
        wrapper = (
            "import resource\n"
            "resource.setrlimit(resource.RLIMIT_CPU, (5, 5))\n"
            "resource.setrlimit(resource.RLIMIT_AS, (300 * 1024 * 1024, 300 * 1024 * 1024))\n"
            + original_code
        )
    else:
        # Windows: リソース制限は使えないがそのまま実行
        wrapper = original_code
    return wrapper


def _limits():
    """Linux/macOS 用プロセスレベルリソース制限（preexec_fn 用）。"""
    if HAS_RESOURCE:
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        resource.setrlimit(resource.RLIMIT_AS, (300 * 1024 * 1024, 300 * 1024 * 1024))


def run_safe(code, timeout=10):
    """
    コードを安全なサブプロセスで実行する。

    処理フロー:
      1. 構文チェック（ast.parse）
      2. 一時ファイルに書き込み
      3. タイムアウト付きサブプロセスで実行
      4. エラーがあれば文字列で返す。成功なら None。

    引数:
      code    : 実行する Python コード文字列
      timeout : 実行タイムアウト秒数（デフォルト 10 秒）
    戻り値:
      None : 成功
      str  : エラーメッセージ
    """
    if not code or not code.strip():
        return "エラー: 空のコードです"

    # Step 1: 構文チェック（高速・サブプロセス不要）
    syntax_err = _check_syntax(code)
    if syntax_err:
        return syntax_err

    # Step 2: ラップして一時ファイルに書き込み
    safe_code = _generate_wrapped_code(code)
    tmp_path  = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".py", delete=False, mode="w", encoding="utf-8"
        ) as tmp:
            tmp.write(safe_code)
            tmp_path = tmp.name

        # Step 3: サブプロセスで実行
        result = subprocess.run(
            [sys.executable, "-I", tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            preexec_fn=_limits if HAS_RESOURCE else None,
        )

        # Step 4: 結果チェック
        if result.returncode != 0:
            error_output = result.stderr.strip() or result.stdout.strip()
            lines = error_output.splitlines()
            if len(lines) > 20:
                error_output = "\n".join(lines[-20:])
            return "RuntimeError:\n{}".format(error_output)

        return None  # 成功

    except subprocess.TimeoutExpired:
        return "タイムアウト: {}秒を超えました。無限ループの可能性があります。".format(timeout)
    except Exception as e:
        return "システムエラー: {}".format(e)
    finally:
        # 一時ファイルを確実に削除
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
