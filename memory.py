"""
Blackwell Dev-OS - memory.py v5.0（ChromaDB非依存フォールバック付き）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
修正前: ChromaDB + sentence_transformers が必須
        → 未インストールだとimport時に即クラッシュ
        → 教訓機能がサイレントに全滅していた

修正後: 3段階フォールバック
  優先① ChromaDB + SentenceTransformer（最高品質・ベクトル検索）
  優先② ChromaDB + TF-IDF検索（sentence_transformersなし）
  優先③ JSONファイル + キーワード検索（何もなくても動く）

公開API（全ファイルから呼ばれる5関数）:
  store_memory(key, text, meta)  → bool
  retrieve_context(query, k)     → str
  list_memories(limit)           → list
  delete_memory(key_prefix)      → int
  get_memory_count()             → int
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

# ============================================================
# バックエンド自動選択
# ============================================================

_BACKEND   = "none"   # "chroma_full" / "chroma_tfidf" / "json"
_embed     = None
_client    = None
_collection= None
_JSON_PATH = "./blackwell_memory.json"


def _init_backend():
    """利用可能な最良のバックエンドを初期化する"""
    global _BACKEND, _embed, _client, _collection

    # 優先①: ChromaDB + SentenceTransformer
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
        _embed      = SentenceTransformer("all-MiniLM-L6-v2")
        _client     = chromadb.PersistentClient(path="./chroma_db")
        _collection = _client.get_or_create_collection("blackwell_ultimate")
        _BACKEND    = "chroma_full"
        print("[memory] ✅ バックエンド: ChromaDB + SentenceTransformer（最高品質）")
        return
    except ImportError:
        pass
    except Exception as e:
        print(f"[memory] ChromaDB+ST初期化失敗: {e}")

    # 優先②: ChromaDB のみ（TF-IDFで代替）
    try:
        import chromadb
        _client     = chromadb.PersistentClient(path="./chroma_db")
        _collection = _client.get_or_create_collection("blackwell_ultimate")
        _BACKEND    = "chroma_tfidf"
        print("[memory] ⚠️  バックエンド: ChromaDB + TF-IDF（sentence_transformers未インストール）")
        return
    except ImportError:
        pass
    except Exception as e:
        print(f"[memory] ChromaDB初期化失敗: {e}")

    # 優先③: JSONファイル（何もインストールされていなくても動く）
    _BACKEND = "json"
    print("[memory] ⚠️  バックエンド: JSONファイル（ChromaDB未インストール）\n"
          "         → pip install chromadb sentence-transformers で高品質になります")


_init_backend()


# ============================================================
# ユーティリティ
# ============================================================

def _make_id(key: str, content: str) -> str:
    return "{}_{}".format(key, hashlib.sha256(content.encode()).hexdigest()[:12])


def _tfidf_score(query: str, text: str) -> float:
    """TF-IDFの超簡易版キーワードマッチスコア"""
    q_words = set(re.findall(r"\w+", query.lower()))
    t_words = re.findall(r"\w+", text.lower())
    if not q_words or not t_words:
        return 0.0
    matches = sum(1 for w in t_words if w in q_words)
    return matches / (len(t_words) + 1)


def _vec_encode(text: str):
    """ベクトル化（SentenceTransformerがない場合はNone）"""
    if _embed is not None:
        try:
            return _embed.encode(text).tolist()
        except Exception:
            pass
    return None


# ============================================================
# JSONバックエンド実装
# ============================================================

def _json_load() -> dict:
    """JSONファイルからメモリを読み込む"""
    if not os.path.exists(_JSON_PATH):
        return {}
    try:
        with open(_JSON_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _json_save(data: dict):
    """メモリをJSONファイルに保存する"""
    try:
        with open(_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[memory] JSON保存失敗: {e}")


# ============================================================
# 公開API: store_memory
# ============================================================

def store_memory(key: str, text: str, meta: dict = None) -> bool:
    """テキストをメモリに保存（upsert）"""
    if not text or not text.strip():
        return False
    meta = meta or {}

    if _BACKEND == "chroma_full":
        try:
            vec    = _vec_encode(text)
            doc_id = _make_id(key, text)
            safe   = {str(k): str(v) for k, v in meta.items()}
            safe["key"] = key
            _collection.upsert(
                embeddings=[vec], documents=[text],
                ids=[doc_id], metadatas=[safe]
            )
            return True
        except Exception as e:
            print(f"[memory] store_memory(chroma_full) error: {e}")
            # フォールバック: JSONにも保存
            _json_fallback_store(key, text, meta)
            return False

    elif _BACKEND == "chroma_tfidf":
        try:
            doc_id = _make_id(key, text)
            safe   = {str(k): str(v) for k, v in meta.items()}
            safe["key"] = key
            # ベクトルなしで保存（ChromaDBはベクトルなしでも保存可能）
            _collection.upsert(
                documents=[text], ids=[doc_id], metadatas=[safe]
            )
            return True
        except Exception as e:
            print(f"[memory] store_memory(chroma_tfidf) error: {e}")
            _json_fallback_store(key, text, meta)
            return False

    else:  # json
        return _json_fallback_store(key, text, meta)


def _json_fallback_store(key: str, text: str, meta: dict) -> bool:
    """JSONファイルへのフォールバック保存"""
    try:
        data   = _json_load()
        doc_id = _make_id(key, text)
        data[doc_id] = {
            "key":       key,
            "text":      text,
            "meta":      {str(k): str(v) for k, v in (meta or {}).items()},
            "timestamp": datetime.now().isoformat(),
        }
        # 最大5000件を上限にする（容量管理）
        if len(data) > 5000:
            oldest_keys = sorted(data.keys(),
                                  key=lambda k: data[k].get("timestamp",""))[:500]
            for k in oldest_keys:
                del data[k]
        _json_save(data)
        return True
    except Exception as e:
        print(f"[memory] JSON保存失敗: {e}")
        return False


# ============================================================
# 公開API: retrieve_context
# ============================================================

def retrieve_context(query: str, k: int = 5) -> str:
    """クエリに近い記憶を取得して結合して返す"""
    if not query or not query.strip():
        return ""

    if _BACKEND == "chroma_full":
        try:
            count = _collection.count()
            if count == 0:
                return _json_retrieve(query, k)
            vec = _vec_encode(query)
            res = _collection.query(query_embeddings=[vec], n_results=min(k, count))
            docs = res.get("documents", [[]])[0]
            return "\n\n".join(docs) if docs else _json_retrieve(query, k)
        except Exception as e:
            print(f"[memory] retrieve_context(chroma_full) error: {e}")
            return _json_retrieve(query, k)

    elif _BACKEND == "chroma_tfidf":
        try:
            count = _collection.count()
            if count == 0:
                return _json_retrieve(query, k)
            # ベクトルなしクエリ（ChromaDB 0.4以降はテキスト検索可能）
            res   = _collection.get(include=["documents", "metadatas"], limit=min(200, count))
            docs  = res.get("documents", [])
            # TF-IDFでスコアリング
            scored = sorted(
                [(doc, _tfidf_score(query, doc)) for doc in docs],
                key=lambda x: -x[1]
            )
            top = [d for d, _ in scored[:k] if _ > 0]
            return "\n\n".join(top) if top else _json_retrieve(query, k)
        except Exception as e:
            print(f"[memory] retrieve_context(chroma_tfidf) error: {e}")
            return _json_retrieve(query, k)

    else:  # json
        return _json_retrieve(query, k)


def _json_retrieve(query: str, k: int) -> str:
    """JSONバックエンドでのキーワード検索"""
    try:
        data = _json_load()
        if not data:
            return ""
        scored = sorted(
            [(item["text"], _tfidf_score(query, item["text"]))
             for item in data.values()],
            key=lambda x: -x[1]
        )
        top = [text for text, score in scored[:k] if score > 0]
        return "\n\n".join(top) if top else ""
    except Exception:
        return ""


# ============================================================
# 公開API: list_memories / delete_memory / get_memory_count
# ============================================================

def list_memories(limit: int = 50) -> list:
    """保存されている記憶の一覧を返す"""
    if _BACKEND in ("chroma_full", "chroma_tfidf"):
        try:
            count = _collection.count()
            if count == 0:
                return _json_list(limit)
            result = _collection.get(
                limit=min(limit, count),
                include=["metadatas", "documents"]
            )
            memories = []
            for doc, meta in zip(result.get("documents",[]), result.get("metadatas",[])):
                memories.append({
                    "key":     meta.get("key", "unknown"),
                    "preview": doc[:100] + ("…" if len(doc) > 100 else ""),
                    "meta":    meta,
                })
            return memories
        except Exception:
            return _json_list(limit)
    return _json_list(limit)


def _json_list(limit: int) -> list:
    data = _json_load()
    result = []
    for item in list(data.values())[-limit:]:
        result.append({
            "key":     item.get("key", "unknown"),
            "preview": item["text"][:100] + ("…" if len(item["text"]) > 100 else ""),
            "meta":    item.get("meta", {}),
        })
    return result


def delete_memory(key_prefix: str) -> int:
    """指定キープレフィックスの記憶を削除（空文字=""で全削除）"""
    count = 0
    if _BACKEND in ("chroma_full", "chroma_tfidf"):
        try:
            result = _collection.get(include=["metadatas"])
            ids_to_del = [
                doc_id for doc_id, meta in
                zip(result.get("ids",[]), result.get("metadatas",[]))
                if key_prefix == "" or meta.get("key","").startswith(key_prefix)
            ]
            if ids_to_del:
                _collection.delete(ids=ids_to_del)
            count += len(ids_to_del)
        except Exception as e:
            print(f"[memory] delete_memory error: {e}")

    # JSONからも削除
    try:
        data    = _json_load()
        to_del  = [k for k, v in data.items()
                   if key_prefix == "" or v.get("key","").startswith(key_prefix)]
        for k in to_del:
            del data[k]
            count += 1
        if to_del:
            _json_save(data)
    except Exception:
        pass
    return count


def get_memory_count() -> int:
    """保存されている記憶の総件数"""
    total = 0
    if _BACKEND in ("chroma_full", "chroma_tfidf"):
        try:
            total += _collection.count()
        except Exception:
            pass
    try:
        total += len(_json_load())
    except Exception:
        pass
    return total


def get_backend_status() -> str:
    """現在のバックエンド状態を返す（UIの診断表示用）"""
    status_map = {
        "chroma_full":  "✅ ChromaDB + ベクトル検索（最高品質）",
        "chroma_tfidf": "⚠️ ChromaDB + TF-IDF検索（sentence_transformers未インストール）",
        "json":         "⚠️ JSONファイル検索（ChromaDB未インストール）\n"
                        "  → pip install chromadb sentence-transformers で高品質になります",
        "none":         "❌ メモリバックエンドなし",
    }
    return status_map.get(_BACKEND, "不明")
