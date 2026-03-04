"""
Blackwell Dev-OS - memory.py (完全版 v4.0)
app.py からインポートされる関数（全5つ）:
  - store_memory(key, text, meta)  : 記憶を保存
  - retrieve_context(query, k)     : 関連記憶を検索して返す
  - list_memories(limit)           : 記憶一覧を返す
  - delete_memory(key_prefix)      : 指定キーの記憶を削除
  - get_memory_count()             : 記憶の総件数を返す
"""

import chromadb
import hashlib
from sentence_transformers import SentenceTransformer

# ============================================================
# 初期化（モジュール読み込み時に1度だけ実行）
# ============================================================
_embed      = SentenceTransformer("all-MiniLM-L6-v2")
_client     = chromadb.PersistentClient(path="./chroma_db")
_collection = _client.get_or_create_collection("blackwell_ultimate")


def _make_id(key, content):
    """ユニーク ID を生成する。"""
    return "{}_{}".format(key, hashlib.sha256(content.encode()).hexdigest()[:12])


# ============================================================
# 記憶の保存
# ============================================================
def store_memory(key, text, meta=None):
    """テキストをベクトル化して記憶に保存（upsert）。"""
    try:
        if not text or not text.strip():
            return False
        vec    = _embed.encode(text).tolist()
        doc_id = _make_id(key, text)
        safe_meta = {str(k): str(v) for k, v in (meta or {}).items()}
        safe_meta["key"] = key
        _collection.upsert(
            embeddings=[vec],
            documents=[text],
            ids=[doc_id],
            metadatas=[safe_meta],
        )
        return True
    except Exception as e:
        print("[memory] store_memory error: {}".format(e))
        return False


# ============================================================
# 記憶の検索
# ============================================================
def retrieve_context(query, k=5):
    """クエリに近い記憶を取得して結合して返す。"""
    try:
        if not query or not query.strip():
            return ""
        count = _collection.count()
        if count == 0:
            return ""
        vec = _embed.encode(query).tolist()
        res = _collection.query(
            query_embeddings=[vec],
            n_results=min(k, count),
        )
        docs = res.get("documents", [[]])[0]
        return "\n\n".join(docs) if docs else ""
    except Exception as e:
        print("[memory] retrieve_context error: {}".format(e))
        return ""


# ============================================================
# 記憶の一覧取得
# ============================================================
def list_memories(limit=50):
    """
    保存されている記憶の一覧を返す。
    戻り値: [{"key": str, "preview": str, "meta": dict}, ...]
    """
    try:
        count = _collection.count()
        if count == 0:
            return []
        result = _collection.get(
            limit=min(limit, count),
            include=["metadatas", "documents"],
        )
        memories = []
        for doc, meta in zip(
            result.get("documents", []),
            result.get("metadatas", []),
        ):
            memories.append({
                "key":     meta.get("key", "unknown"),
                "preview": doc[:100] + "..." if len(doc) > 100 else doc,
                "meta":    meta,
            })
        return memories
    except Exception as e:
        print("[memory] list_memories error: {}".format(e))
        return []


# ============================================================
# 記憶の削除
# ============================================================
def delete_memory(key_prefix):
    """
    指定キープレフィックスに一致する記憶を削除する。
    key_prefix が空文字 "" の場合は全件削除。
    戻り値: 削除した件数
    """
    try:
        result = _collection.get(include=["metadatas"])
        ids_to_delete = []
        for doc_id, meta in zip(
            result.get("ids", []),
            result.get("metadatas", []),
        ):
            key = meta.get("key", "")
            if key_prefix == "" or key.startswith(key_prefix):
                ids_to_delete.append(doc_id)
        if ids_to_delete:
            _collection.delete(ids=ids_to_delete)
        return len(ids_to_delete)
    except Exception as e:
        print("[memory] delete_memory error: {}".format(e))
        return 0


# ============================================================
# 記憶件数の取得
# ============================================================
def get_memory_count():
    """保存されている記憶の総件数を返す。"""
    try:
        return _collection.count()
    except Exception:
        return 0
