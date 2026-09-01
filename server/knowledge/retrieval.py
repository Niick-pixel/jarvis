"""Building the embedding client, and fetching the chunks a question deserves.

Vector search needs an embedding model resident somewhere. When none is configured, retrieval is
keyword-only and says so - it never quietly returns worse results while looking the same.
"""

from __future__ import annotations

import sqlite3

from server.knowledge import hybrid
from server.models.knowledge import RetrievedChunk
from server.providers.base import ProviderError
from server.providers.embeddings import EmbeddingClient
from server.providers.llamacpp import LlamaCppProvider
from server.providers.reranker import RerankClient
from server.settings import Settings, is_loopback


def embedder_for(settings: Settings) -> EmbeddingClient | None:
    url = settings.knowledge.embeddings_base_url.strip()
    if not url:
        return None
    host = url.split("//", 1)[-1].split("/", 1)[0].split(":")[0]
    if not is_loopback(host):
        # Same rule as the inference port: an embedding endpoint is a local model, not a service.
        return None
    provider = LlamaCppProvider(url, name="embeddings")
    return EmbeddingClient(provider, settings.knowledge.embeddings_model_id)


def reranker_for(settings: Settings) -> RerankClient | None:
    url = settings.knowledge.rerank_base_url.strip()
    if not url:
        return None
    host = url.split("//", 1)[-1].split("/", 1)[0].split(":")[0]
    if not is_loopback(host):
        # Same rule as the inference and embedding ports: a cross-encoder is a local model.
        return None
    return RerankClient(
        url, settings.knowledge.rerank_model_id, settings.knowledge.rerank_timeout_s
    )


async def for_query(
    conn: sqlite3.Connection, query: str, settings: Settings
) -> list[RetrievedChunk]:
    """Fuse first, then let a cross-encoder read the question and each candidate together.

    Fusion decides what is worth reading; the reranker decides what is worth injecting. Without one
    configured, fusion order is final and the chunks arrive with no rerank score - which is how the
    Context Inspector shows the difference between "scored badly" and "never scored".
    """
    if not query.strip():
        return []
    reranker = reranker_for(settings)
    keep = settings.knowledge.rag_results
    chunks = await hybrid.retrieve(
        conn,
        query,
        embedder=embedder_for(settings),
        limit=max(settings.knowledge.rerank_candidates, keep) if reranker else keep,
    )
    if reranker is None or len(chunks) <= 1:
        return chunks[:keep]
    return await rerank(reranker, query, chunks, keep)


async def rerank(
    client: RerankClient, query: str, chunks: list[RetrievedChunk], keep: int
) -> list[RetrievedChunk]:
    """Reorder by cross-encoder score. A reranker that fails leaves the fusion order untouched."""
    try:
        scores = await client.scores(query, [chunk.text for chunk in chunks])
    except ProviderError:
        return chunks[:keep]
    scored = [
        chunk.model_copy(update={"rerank_score": score})
        for chunk, score in zip(chunks, scores, strict=False)
    ]
    scored.sort(key=lambda chunk: chunk.rerank_score or 0.0, reverse=True)
    return scored[:keep]


def citation(chunk: RetrievedChunk) -> str:
    """A citation you can act on: the file, and where in it to look."""
    return f"{chunk.document_path}#{chunk.byte_start}-{chunk.byte_end}"
