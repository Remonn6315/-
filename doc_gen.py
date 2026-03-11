"""
Blackwell Dev-OS — doc_gen.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
自動ドキュメント生成

コードから日本語の説明・README・設計書を自動生成。
GDScript → @doc_string 形式でファイルに書き出し。

【公開API】
  generate_readme(project_path, anchor) → str
  generate_function_docs(code_path)    → str
  generate_design_doc(project_path)    → str
  inject_gdoc_strings(gd_path)         → str (修正済みコード)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os, re, ast
from pathlib import Path


def _call_ollama(prompt: str, model: str = "qwen2.5-coder:14b") -> str:
    try:
        import ollama
        res = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return res["message"]["content"]
    except Exception as e:
        return f"[生成失敗: {e}]"


def generate_readme(project_path: str, anchor: str = "") -> str:
    """プロジェクト全体のREADME.mdを自動生成"""
    # ファイル一覧を収集
    files = []
    for root, dirs, fnames in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in {".git",".godot","__pycache__"}]
        for fn in fnames:
            if fn.endswith((".py",".gd",".cs",".json")):
                rel = os.path.relpath(os.path.join(root, fn), project_path)
                try:
                    size = os.path.getsize(os.path.join(root, fn))
                    files.append(f"{rel} ({size//1024}KB)")
                except Exception:
                    files.append(rel)

    file_list = "\n".join(files[:20])
    anchor_line = f"【ゲーム主軸】{anchor}\n" if anchor else ""

    prompt = (
        f"{anchor_line}"
        f"以下のファイル構成を持つゲームプロジェクトのREADME.mdを日本語で生成してください。\n\n"
        f"【ファイル一覧】\n{file_list}\n\n"
        "以下の構成で書いてください:\n"
        "# プロジェクト名\n"
        "## 概要\n"
        "## ゲームの特徴\n"
        "## 技術スタック\n"
        "## ファイル構成\n"
        "## セットアップ方法\n"
        "## 開発状況\n\n"
        "Markdownで出力してください。"
    )
    return _call_ollama(prompt)


def generate_function_docs(code_path: str) -> str:
    """コードファイルの全関数に日本語ドキュメントを生成"""
    if not os.path.exists(code_path):
        return f"ファイルが見つかりません: {code_path}"

    with open(code_path, encoding="utf-8", errors="ignore") as f:
        code = f.read()

    ext = os.path.splitext(code_path)[1]
    lang = "gdscript" if ext == ".gd" else "python" if ext == ".py" else "csharp"

    prompt = (
        f"以下の{lang}コードの全ての関数に、\n"
        "日本語で簡潔なdocstringを追加してください。\n"
        "既存のコードは変更せず、docstringのみ追加してください。\n"
        "完全なコードを出力してください。\n\n"
        f"```{lang}\n{code[:4000]}\n```"
    )
    return _call_ollama(prompt)


def generate_design_doc(project_path: str, anchor: str = "") -> str:
    """プロジェクトの設計書（技術仕様書）を自動生成"""
    # 主要ファイルのコードを収集
    snippets = []
    for root, dirs, fnames in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in {".git",".godot","__pycache__"}]
        for fn in sorted(fnames):
            if fn.endswith((".py",".gd")) and not fn.startswith("_"):
                fp = os.path.join(root, fn)
                try:
                    with open(fp, encoding="utf-8", errors="ignore") as f:
                        code = f.read()
                    snippets.append(f"## {fn}\n```\n{code[:800]}\n```")
                except Exception:
                    pass
        if len(snippets) >= 5:
            break

    anchor_line = f"【ゲーム主軸】{anchor}\n\n" if anchor else ""
    prompt = (
        f"{anchor_line}"
        "以下のコードから技術設計書を日本語で生成してください。\n\n"
        + "\n\n".join(snippets[:5]) +
        "\n\n"
        "以下の構成で出力:\n"
        "# 技術設計書\n"
        "## アーキテクチャ概要\n"
        "## クラス/モジュール設計\n"
        "## データフロー\n"
        "## 主要アルゴリズム\n"
        "## 今後の拡張ポイント"
    )
    return _call_ollama(prompt)


def inject_gdoc_strings(gd_path: str) -> str:
    """
    GDScriptファイルにdoc_stringを自動注入して返す。
    Godot4の ## コメント形式で各関数の上に追加。
    """
    if not os.path.exists(gd_path):
        return ""

    with open(gd_path, encoding="utf-8", errors="ignore") as f:
        code = f.read()

    prompt = (
        "以下のGDScript4コードの各func定義の直前に、\n"
        "Godot4の ## doc_string形式（##で始まるコメント）で\n"
        "日本語の説明を1行追加してください。\n"
        "それ以外のコードは一切変更しないでください。\n\n"
        f"```gdscript\n{code[:3000]}\n```\n\n"
        "完全なGDScriptコードのみ出力（```ブロック内に）。"
    )
    result = _call_ollama(prompt)
    # コードブロックだけ抽出
    m = re.search(r"```(?:gdscript|gd)?\n(.*?)```", result, re.DOTALL)
    return m.group(1).strip() if m else result
