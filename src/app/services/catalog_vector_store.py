"""Vector index over store catalogues for intent-classification menu context."""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import threading
from pathlib import Path

import httpx

from app.config import settings
from app.domain.models import Product
from app.services.inventory_service import InventoryService

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _db_path() -> Path:
    base = Path(settings.catalog_vector_db_path or "data/catalog_vectors.db")
    if not base.is_absolute():
        base = Path.cwd() / base
    base.parent.mkdir(parents=True, exist_ok=True)
    return base


def _connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS product_embeddings (
                store_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                document TEXT NOT NULL,
                embedding TEXT NOT NULL,
                PRIMARY KEY (store_id, sku)
            )
            """
        )
        _conn.commit()
    return _conn


def _product_document(p: Product) -> str:
    return f"{p.name} | SKU {p.sku} | {p.price:.2f} {settings.default_currency} | stock {p.quantity_available}"


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return -1.0
    return dot / (na * nb)


def _embed_texts(texts: list[str], api_key: str) -> list[list[float]]:
    if not texts:
        return []
    response = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": settings.catalog_embedding_model, "input": texts},
        timeout=60.0,
    )
    response.raise_for_status()
    body = response.json()
    data = sorted(body["data"], key=lambda row: row["index"])
    return [row["embedding"] for row in data]


def _keyword_fallback(products: list[Product], query: str, top_k: int) -> list[Product]:
    q = (query or "").lower()
    tokens = [t for t in q.split() if len(t) >= 2]
    if not tokens:
        return products[:top_k]

    scored: list[tuple[int, Product]] = []
    for p in products:
        hay = f"{p.name} {p.sku}".lower()
        score = sum(1 for t in tokens if t in hay)
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: (-x[0], x[1].name))
    return [p for _, p in scored[:top_k]]


def ensure_store_indexed(inventory: InventoryService, store_id: str) -> int:
    """Embed all products for a store if missing or catalogue changed. Returns row count."""
    products = inventory.list_all_products(store_id)
    if not products:
        return 0

    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        return 0

    conn = _connection()
    existing = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT sku, document FROM product_embeddings WHERE store_id = ?",
            (store_id,),
        ).fetchall()
    }
    to_index: list[Product] = []
    for p in products:
        doc = _product_document(p)
        if existing.get(p.sku) != doc:
            to_index.append(p)

    if not to_index:
        return len(existing)

    batch_size = 64
    indexed = 0
    with _lock:
        for start in range(0, len(to_index), batch_size):
            chunk = to_index[start : start + batch_size]
            docs = [_product_document(p) for p in chunk]
            vectors = _embed_texts(docs, api_key)
            for p, doc, vec in zip(chunk, docs, vectors):
                conn.execute(
                    """
                    INSERT INTO product_embeddings (store_id, sku, document, embedding)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(store_id, sku) DO UPDATE SET
                        document = excluded.document,
                        embedding = excluded.embedding
                    """,
                    (store_id, p.sku, doc, json.dumps(vec)),
                )
                indexed += 1
            conn.commit()

        stale = set(existing) - {p.sku for p in products}
        for sku in stale:
            conn.execute(
                "DELETE FROM product_embeddings WHERE store_id = ? AND sku = ?",
                (store_id, sku),
            )
        conn.commit()

    logger.info(
        "Catalog vector index store=%s products=%s newly_indexed=%s",
        store_id,
        len(products),
        indexed,
    )
    return len(products)


def search_catalog_context(
    inventory: InventoryService,
    store_id: str,
    query: str,
    *,
    top_k: int | None = None,
) -> str:
    """Relevant menu lines for the intent prompt (vector search + keyword fallback)."""
    k = top_k or settings.catalog_vector_top_k
    products = inventory.list_all_products(store_id)
    if not products:
        return "(no products in catalogue)"

    q = (query or "").strip()
    api_key = (settings.openai_api_key or "").strip()

    if api_key and settings.catalog_vector_enabled:
        try:
            ensure_store_indexed(inventory, store_id)
            conn = _connection()
            rows = conn.execute(
                "SELECT sku, document, embedding FROM product_embeddings WHERE store_id = ?",
                (store_id,),
            ).fetchall()
            if rows and q:
                q_vec = _embed_texts([q], api_key)[0]
                ranked: list[tuple[float, str, str]] = []
                for sku, doc, emb_json in rows:
                    vec = json.loads(emb_json)
                    ranked.append((_cosine(q_vec, vec), sku, doc))
                ranked.sort(key=lambda x: -x[0])
                lines = [
                    f"- {doc}"
                    for score, _, doc in ranked[:k]
                    if score > 0.05
                ]
                if lines:
                    return "Relevant catalogue items (semantic search):\n" + "\n".join(lines)
        except Exception:
            logger.exception("Vector catalog search failed store=%s", store_id)

    # Fallback: compact menu slice + keyword hits
    hits = _keyword_fallback(products, q, k) if q else products[:k]
    header = f"Store catalogue sample ({len(products)} items total):"
    lines = [f"- {_product_document(p)}" for p in hits]
    return header + "\n" + "\n".join(lines)
