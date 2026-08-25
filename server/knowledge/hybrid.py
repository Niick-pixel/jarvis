"""Hybrid retrieval: keyword and vector, fused by reciprocal rank fusion.

RRF is used rather than blending scores because BM25 and cosine distance are not on the same
scale and never will be - normalising them means inventing a conversion. Ranks are comparable by
construction, which is why RRF works without tuning.

Every result records which retrievers found it, so fusion is inspectable rather than a number that
appears from nowhere.
"""

from __future__ import annotations

import re
import sqlite3

from server.knowledge import vectors
from server.knowledge.memory_index import STOPWORDS
from server.models.knowledge import RetrievedChunk
from server.providers.embeddings import EmbeddingClient

RRF_K = 60
"""The standard damping constant. Higher means deeper ranks still contribute."""
CANDIDATES = 40
FTS_UNSAFE = re.compile(r"[^\w\s]")


def fts_query(text: str) -> str:
    terms = [
        term
        for term in FTS_UNSAFE.sub(" ", text.lower()).split()
        if len(term) > 2 and term not in STOPWORDS
    ][:24]
    return " OR ".join(terms)


def keyword_search(conn: sqlite3.Connection, query: str, limit: int) -> list[str]:
    expression = fts_query(query)
    if not expression:
        return []
    rows = conn.execute(
        "SELECT c.id FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid"
        " WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
        (expression, limit),
    )
    return [row["id"] for row in rows]


def vector_search(conn: sqlite3.Connection, vector: list[float], limit: int) -> list[str]:
    if not vectors.available(conn):
        return []
    hits = vectors.search(conn, vector, limit)
    if not hits:
        return []
    placeholders = ",".join("?" for _ in hits)
    rows = conn.execute(
        f"SELECT rowid, id FROM chunks WHERE rowid IN ({placeholders})",
        [rowid for rowid, _ in hits],
    )
    by_rowid = {int(row["rowid"]): row["id"] for row in rows}
    return [by_rowid[rowid] for rowid, _ in hits if rowid in by_rowid]


def fuse(ranked_lists: dict[str, list[str]]) -> list[tuple[str, float, list[str]]]:
    """Reciprocal rank fusion. Returns (chunk_id, score, which retrievers found it)."""
    scores: dict[str, float] = {}
    sources: dict[str, list[str]] = {}
    for name, ids in ranked_lists.items():
        for rank, chunk_id in enumerate(ids, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
            sources.setdefault(chunk_id, []).append(name)
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [(chunk_id, score, sources[chunk_id]) for chunk_id, score in ordered]


def hydrate(
    conn: sqlite3.Connection, fused: list[tuple[str, float, list[str]]], limit: int
) -> list[RetrievedChunk]:
    top = fused[:limit]
    if not top:
        return []
    placeholders = ",".join("?" for _ in top)
    rows = {
        row["id"]: row
        for row in conn.execute(
            "SELECT c.id, c.heading, c.text, c.byte_start, c.byte_end, d.path"
            " FROM chunks c JOIN documents d ON d.id = c.document_id"
            f" WHERE c.id IN ({placeholders})",
            [chunk_id for chunk_id, _, _ in top],
        )
    }
    out: list[RetrievedChunk] = []
    for chunk_id, score, matched in top:
        row = rows.get(chunk_id)
        if row is None:
            continue
        out.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                document_path=row["path"],
                heading=row["heading"],
                text=row["text"],
                byte_start=row["byte_start"],
                byte_end=row["byte_end"],
                score=score,
                matched_by=matched,
            )
        )
    return out


async def retrieve(
    conn: sqlite3.Connection,
    query: str,
    *,
    embedder: EmbeddingClient | None = None,
    limit: int = 5,
) -> list[RetrievedChunk]:
    """Keyword always; vectors when an embedding model is configured and the index is built."""
    ranked: dict[str, list[str]] = {"keyword": keyword_search(conn, query, CANDIDATES)}

    if embedder is not None and vectors.available(conn):
        try:
            vector = (await embedder.embed([query]))[0]
            ranked["vector"] = vector_search(conn, vector, CANDIDATES)
        except Exception:  # noqa: BLE001 - degrade to keyword rather than fail the request
            ranked.pop("vector", None)

    return hydrate(conn, fuse(ranked), limit)
