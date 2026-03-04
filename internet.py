"""
Blackwell Dev-OS - internet.py (Phase 1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
完全無料・登録不要のインターネット機能モジュール

提供する関数:
  get_current_datetime()       - 現在の日時・曜日・時刻
  search_duckduckgo(query, k)  - DuckDuckGo Web検索
  search_wikipedia(query)      - Wikipedia 詳細説明
  search_pypi(package)         - PyPI パッケージ最新バージョン確認
  search_github(query, lang)   - GitHub コード・リポジトリ検索
  web_fetch(url)               - 指定URLのテキスト取得
  smart_search(query)          - クエリを解析して最適なAPIを自動選択
  build_search_context(query)  - AIプロンプト用の検索コンテキスト文字列生成
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import requests
import json
import re
import urllib.parse
from datetime import datetime, timezone, timedelta


# ============================================================
# 定数設定
# ============================================================
JST = timezone(timedelta(hours=9), "JST")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 8  # 秒


# ============================================================
# 時刻・日付
# ============================================================

def get_current_datetime():
    """
    現在の日時情報を返す。
    戻り値:
    {
        "datetime_str": "2026年3月4日（水）午後3時45分",
        "date":         "2026-03-04",
        "time":         "15:45:32",
        "weekday":      "水曜日",
        "timestamp":    1234567890,
        "year": int, "month": int, "day": int,
        "hour": int, "minute": int,
    }
    """
    now = datetime.now(JST)
    weekdays = ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"]
    hour_str = f"午前{now.hour}時" if now.hour < 12 else (
        "正午" if now.hour == 12 else f"午後{now.hour - 12}時"
    )
    return {
        "datetime_str": f"{now.year}年{now.month}月{now.day}日（{weekdays[now.weekday()]}）{hour_str}{now.minute}分",
        "date":         now.strftime("%Y-%m-%d"),
        "time":         now.strftime("%H:%M:%S"),
        "weekday":      weekdays[now.weekday()],
        "timestamp":    int(now.timestamp()),
        "year":         now.year,
        "month":        now.month,
        "day":          now.day,
        "hour":         now.hour,
        "minute":       now.minute,
    }


# ============================================================
# DuckDuckGo 検索
# ============================================================

def search_duckduckgo(query, k=5):
    """
    DuckDuckGo Instant Answer API で検索する（無料・登録不要）。
    戻り値:
    {
        "success": bool,
        "results": [{"title": str, "url": str, "snippet": str}],
        "abstract": str,  # トピックの概要（あれば）
        "error": str,
    }
    """
    try:
        params = {
            "q":              query,
            "format":         "json",
            "no_html":        1,
            "skip_disambig":  1,
        }
        url = "https://api.duckduckgo.com/"
        res = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        data = res.json()

        results  = []
        abstract = data.get("AbstractText", "") or data.get("Answer", "")

        # RelatedTopics から結果を抽出
        for topic in data.get("RelatedTopics", [])[:k]:
            if isinstance(topic, dict) and "Text" in topic:
                first_url = topic.get("FirstURL", "")
                results.append({
                    "title":   topic.get("Text", "")[:80],
                    "url":     first_url,
                    "snippet": topic.get("Text", ""),
                })

        # Instant Answer 形式の結果も追加
        if data.get("Results"):
            for r in data["Results"][:k]:
                results.append({
                    "title":   r.get("Text", "")[:80],
                    "url":     r.get("FirstURL", ""),
                    "snippet": r.get("Text", ""),
                })

        return {
            "success":  True,
            "results":  results[:k],
            "abstract": abstract,
            "error":    "",
        }

    except requests.exceptions.Timeout:
        return {"success": False, "results": [], "abstract": "", "error": "タイムアウト"}
    except Exception as e:
        return {"success": False, "results": [], "abstract": "", "error": str(e)}


# ============================================================
# Wikipedia 検索
# ============================================================

def search_wikipedia(query, lang="ja", sentences=5):
    """
    Wikipedia API で概要を取得する（無料・登録不要）。
    lang: "ja"=日本語, "en"=英語
    戻り値:
    {
        "success": bool,
        "title":   str,
        "summary": str,
        "url":     str,
        "error":   str,
    }
    """
    try:
        # 検索してページタイトルを取得
        search_url = f"https://{lang}.wikipedia.org/w/api.php"
        search_params = {
            "action":  "query",
            "list":    "search",
            "srsearch": query,
            "format":  "json",
            "srlimit": 1,
        }
        search_res = requests.get(
            search_url, params=search_params,
            headers=HEADERS, timeout=REQUEST_TIMEOUT
        )
        search_data = search_res.json()
        hits = search_data.get("query", {}).get("search", [])
        if not hits:
            # 日本語で見つからなければ英語で再検索
            if lang == "ja":
                return search_wikipedia(query, lang="en", sentences=sentences)
            return {"success": False, "title": "", "summary": "", "url": "", "error": "記事が見つかりません"}

        title = hits[0]["title"]

        # 本文サマリー取得
        extract_params = {
            "action":       "query",
            "prop":         "extracts",
            "exintro":      True,
            "explaintext":  True,
            "titles":       title,
            "format":       "json",
            "exsentences":  sentences,
        }
        extract_res  = requests.get(
            search_url, params=extract_params,
            headers=HEADERS, timeout=REQUEST_TIMEOUT
        )
        extract_data = extract_res.json()
        pages        = extract_data.get("query", {}).get("pages", {})
        page         = next(iter(pages.values()))
        summary      = page.get("extract", "")

        wiki_url = f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title)}"
        return {
            "success": True,
            "title":   title,
            "summary": summary[:1500],
            "url":     wiki_url,
            "error":   "",
        }

    except requests.exceptions.Timeout:
        return {"success": False, "title": "", "summary": "", "url": "", "error": "タイムアウト"}
    except Exception as e:
        return {"success": False, "title": "", "summary": "", "url": "", "error": str(e)}


# ============================================================
# PyPI パッケージ情報
# ============================================================

def search_pypi(package_name):
    """
    PyPI JSON API でパッケージの最新バージョン・概要を取得する。
    戻り値:
    {
        "success":     bool,
        "name":        str,
        "version":     str,
        "summary":     str,
        "home_page":   str,
        "license":     str,
        "requires_python": str,
        "error":       str,
    }
    """
    try:
        url = f"https://pypi.org/pypi/{package_name}/json"
        res = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if res.status_code == 404:
            return {"success": False, "name": package_name, "version": "", "summary": "",
                    "home_page": "", "license": "", "requires_python": "", "error": "パッケージが見つかりません"}
        data    = res.json()
        info    = data.get("info", {})
        return {
            "success":         True,
            "name":            info.get("name", package_name),
            "version":         info.get("version", "?"),
            "summary":         info.get("summary", ""),
            "home_page":       info.get("home_page", "") or info.get("project_url", ""),
            "license":         info.get("license", ""),
            "requires_python": info.get("requires_python", ""),
            "error":           "",
        }
    except requests.exceptions.Timeout:
        return {"success": False, "name": package_name, "version": "", "summary": "",
                "home_page": "", "license": "", "requires_python": "", "error": "タイムアウト"}
    except Exception as e:
        return {"success": False, "name": package_name, "version": "", "summary": "",
                "home_page": "", "license": "", "requires_python": "", "error": str(e)}


# ============================================================
# GitHub 検索
# ============================================================

def search_github(query, language="", kind="repositories", limit=5, token=""):
    """
    GitHub Search API でリポジトリ・コードを検索する。
    無料枠: 未認証=10回/分, token指定=30回/分

    引数:
        query:    検索クエリ
        language: "Python" / "GDScript" など（空文字で絞り込みなし）
        kind:     "repositories" / "code"
        limit:    取得件数
        token:    GitHub Personal Access Token（任意・なしでも動作）

    戻り値:
    {
        "success": bool,
        "items":   [{"name": str, "url": str, "description": str, "stars": int}],
        "total":   int,
        "error":   str,
    }
    """
    try:
        q = query
        if language:
            q += f" language:{language}"

        headers = dict(HEADERS)
        headers["Accept"] = "application/vnd.github.v3+json"
        if token:
            headers["Authorization"] = f"token {token}"

        url    = f"https://api.github.com/search/{kind}"
        params = {"q": q, "sort": "stars", "order": "desc", "per_page": limit}
        res    = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)

        if res.status_code == 403:
            return {"success": False, "items": [], "total": 0,
                    "error": "GitHub APIレート制限。少し待つか、tokenを設定してください。"}
        if res.status_code != 200:
            return {"success": False, "items": [], "total": 0,
                    "error": f"GitHub API エラー: {res.status_code}"}

        data  = res.json()
        items = []
        for item in data.get("items", [])[:limit]:
            items.append({
                "name":        item.get("full_name", item.get("name", "")),
                "url":         item.get("html_url", ""),
                "description": (item.get("description", "") or "")[:120],
                "stars":       item.get("stargazers_count", 0),
                "language":    item.get("language", ""),
            })

        return {
            "success": True,
            "items":   items,
            "total":   data.get("total_count", 0),
            "error":   "",
        }

    except requests.exceptions.Timeout:
        return {"success": False, "items": [], "total": 0, "error": "タイムアウト"}
    except Exception as e:
        return {"success": False, "items": [], "total": 0, "error": str(e)}


# ============================================================
# URL直接取得
# ============================================================

def web_fetch(url, max_chars=3000):
    """
    指定URLのHTMLをプレーンテキストに変換して返す。
    戻り値:
    {
        "success": bool,
        "text":    str,
        "url":     str,
        "error":   str,
    }
    """
    try:
        res  = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        res.encoding = res.apparent_encoding or "utf-8"
        html = res.text

        # HTMLタグを除去して読みやすいテキストに
        text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>",  " ", text,  flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;",  "&", text)
        text = re.sub(r"&lt;",   "<", text)
        text = re.sub(r"&gt;",   ">", text)
        text = re.sub(r"\s{3,}", "\n", text)
        text = text.strip()

        return {
            "success": True,
            "text":    text[:max_chars],
            "url":     url,
            "error":   "",
        }
    except requests.exceptions.Timeout:
        return {"success": False, "text": "", "url": url, "error": "タイムアウト"}
    except Exception as e:
        return {"success": False, "text": "", "url": url, "error": str(e)}


# ============================================================
# スマート検索（クエリを解析して最適APIを自動選択）
# ============================================================

_TIME_PATTERNS  = re.compile(r"(今何時|今日|今|現在.*時|何時|何日|何曜|日付|時刻|時間)", re.I)
_PYPI_PATTERNS  = re.compile(r"(pip|pypi|パッケージ|ライブラリ|バージョン|install|インストール)\s*(.*)", re.I)
_GITHUB_PATTERNS = re.compile(r"(github|リポジトリ|oss|オープンソース|コード例|サンプル)", re.I)
_WIKI_PATTERNS  = re.compile(r"(とは|what is|意味|概要|仕組み|アルゴリズム|歴史|解説)", re.I)


def smart_search(query, github_token=""):
    """
    クエリの内容を分析して最適な検索APIを自動選択して実行する。

    戻り値:
    {
        "source":   str,   # "datetime" / "wikipedia" / "pypi" / "github" / "duckduckgo"
        "query":    str,
        "result":   dict,  # 各APIの戻り値
        "summary":  str,   # 人間が読みやすい要約テキスト
    }
    """
    # 時刻・日付
    if _TIME_PATTERNS.search(query):
        dt     = get_current_datetime()
        summary = f"現在の日時: {dt['datetime_str']}"
        return {"source": "datetime", "query": query, "result": dt, "summary": summary}

    # PyPI パッケージ
    pypi_match = _PYPI_PATTERNS.search(query)
    if pypi_match:
        pkg_name = pypi_match.group(2).strip().split()[0] if pypi_match.group(2).strip() else query
        result   = search_pypi(pkg_name)
        if result["success"]:
            summary = (
                f"📦 {result['name']} 最新版: v{result['version']}\n"
                f"概要: {result['summary']}\n"
                f"Python要件: {result['requires_python']}"
            )
        else:
            summary = f"PyPI検索失敗: {result['error']}"
        return {"source": "pypi", "query": query, "result": result, "summary": summary}

    # GitHub
    if _GITHUB_PATTERNS.search(query):
        result  = search_github(query, token=github_token)
        if result["success"] and result["items"]:
            lines   = [f"🔍 GitHub検索結果（{result['total']}件中上位）:"]
            for item in result["items"][:3]:
                lines.append(f"  ⭐{item['stars']:,} {item['name']}: {item['description']}")
                lines.append(f"       {item['url']}")
            summary = "\n".join(lines)
        else:
            summary = f"GitHub検索失敗: {result.get('error','')}"
        return {"source": "github", "query": query, "result": result, "summary": summary}

    # Wikipedia（概念・解説系）
    if _WIKI_PATTERNS.search(query):
        result  = search_wikipedia(query)
        if result["success"]:
            summary = f"📖 {result['title']}\n{result['summary'][:400]}\n🔗 {result['url']}"
        else:
            summary = f"Wikipedia検索失敗: {result['error']}"
        return {"source": "wikipedia", "query": query, "result": result, "summary": summary}

    # デフォルト: DuckDuckGo
    result = search_duckduckgo(query)
    if result["success"]:
        lines = ["🌐 Web検索結果:"]
        if result["abstract"]:
            lines.append(result["abstract"][:300])
        for r in result["results"][:3]:
            lines.append(f"  • {r['title']}")
            if r["url"]:
                lines.append(f"    {r['url']}")
        summary = "\n".join(lines) if len(lines) > 1 else "検索結果が見つかりませんでした。"
    else:
        summary = f"Web検索失敗: {result['error']}"

    return {"source": "duckduckgo", "query": query, "result": result, "summary": summary}


# ============================================================
# AIプロンプト用コンテキスト文字列生成
# ============================================================

def build_search_context(query, github_token=""):
    """
    AIのプロンプトに注入するための検索コンテキスト文字列を生成する。
    engine.py の autonomous_dev / chat_with_persona から呼ばれる。

    戻り値: str（AIプロンプトにそのまま追記できる文字列）
    """
    # まず時刻情報を必ず含める
    dt = get_current_datetime()
    dt_line = f"現在日時: {dt['datetime_str']}"

    # スマート検索実行
    search_result = smart_search(query, github_token=github_token)
    summary = search_result.get("summary", "")

    if not summary or "失敗" in summary:
        return f"\n\n【🌐 現在情報】\n{dt_line}\n"

    context = (
        f"\n\n【🌐 インターネット検索結果（{search_result['source']}）】\n"
        f"{dt_line}\n"
        f"{summary}\n"
        f"※ この情報をコード生成・回答の参考にしてください。"
    )
    return context
