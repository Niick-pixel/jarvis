"""Building the embedding client, and fetching the chunks a question deserves.

Vector search needs an embedding model resident somewhere. When none is configured, retrieval is
keyword-only and says so - it never quietly returns worse results while looking the same.
"""

from __future__ import annotations

import sqlite3

from server.knowledge import hybrid
from server.models.knowledge import RetrievedChunk
from server.providers.embeddings import EmbeddingClient
from server.providers.llamacpp import LlamaCppProvider
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


async def for_query(
    conn: sqlite3.Connection, query: str, settings: Settings
) -> list[RetrievedChunk]:
    if not query.strip():
        return []
    return await hybrid.retrieve(
        conn,
        query,
        embedder=embedder_for(settings),
        limit=settings.knowledge.rag_results,
    )


def citation(chunk: RetrievedChunk) -> str:
    """A citation you can act on: the file, and where in it to look."""
    return f"{chunk.document_path}#{chunk.byte_start}-{chunk.byte_end}"
