"""Sources, indexing, and opening a citation (BRIEF.md 4.8)."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from server.deps import State
from server.errors import NotFound, SovereignError
from server.ids import new_id, now_ms
from server.knowledge import retrieval, vectors, watcher
from server.models.knowledge import IndexProgress, Source, SourceCreate
from server.settings import Settings

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
CONTEXT_BYTES = 400


class OpenedChunk(BaseModel):
    path: str
    byte_start: int
    byte_end: int
    line_number: int
    """1-indexed, so the path and line can be pasted straight into an editor."""
    before: str
    text: str
    after: str


class RetrievalStatus(BaseModel):
    keyword: bool = True
    vector: bool
    rerank: bool = False
    """True only when a reranker answered a probe just now, not when one is merely configured."""
    detail: str
    rerank_detail: str = ""


def _row(row: sqlite3.Row) -> Source:
    data = dict(row)
    data["enabled"] = bool(data["enabled"])
    return Source(**data)


@router.get("/sources")
def list_sources(state: State) -> list[Source]:
    with state.db.session() as conn:
        return [_row(r) for r in conn.execute("SELECT * FROM sources ORDER BY created_at")]


@router.post("/sources")
def add_source(body: SourceCreate, state: State) -> Source:
    path = Path(body.path).expanduser()
    if not path.exists():
        raise SovereignError("invalid_request", f"{path} does not exist on this machine.")
    source_id = new_id("src")
    kind = "folder" if path.is_dir() else "file"
    with state.db.session() as conn:
        conn.execute(
            "INSERT INTO sources (id, path, kind, observer, created_at) VALUES (?,?,?,?,?)"
            " ON CONFLICT(path) DO NOTHING",
            (source_id, str(path), kind, watcher.observer_for(path), now_ms()),
        )
        row = conn.execute("SELECT * FROM sources WHERE path = ?", (str(path),)).fetchone()
    return _row(row)


@router.delete("/sources/{source_id}")
def remove_source(source_id: str, state: State) -> dict[str, str]:
    state.watcher.stop(source_id)
    with state.db.session() as conn:
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    return {"status": "removed"}


@router.post("/sources/{source_id}/index")
async def index_source(source_id: str, state: State) -> IndexProgress:
    with state.db.session() as conn:
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    if row is None:
        raise NotFound("Source")

    source = _row(row)
    embedder = retrieval.embedder_for(state.settings)
    if embedder is not None:
        dimension = await embedder.dimension()
        with state.db.session() as conn:
            vectors.ensure_table(conn, dimension, state.settings.knowledge.embeddings_model_id)

    path = Path(source.path)
    state.watcher.start(source_id, path, source.observer)
    asyncio.create_task(state.indexer.index(source_id, path, embedder))
    return state.indexer.progress.get(source_id) or IndexProgress(
        source_id=source_id, state="scanning", detail="starting"
    )


@router.get("/progress")
def progress(state: State) -> list[IndexProgress]:
    return list(state.indexer.progress.values())


@router.post("/pause")
def pause(state: State) -> dict[str, bool]:
    state.indexer.pause()
    return {"paused": True}


@router.post("/resume")
def resume(state: State) -> dict[str, bool]:
    state.indexer.resume()
    return {"paused": False}


@router.get("/status")
async def status(state: State) -> RetrievalStatus:
    """Which retrievers are actually running, so nothing quietly degrades."""
    has_embedder = retrieval.embedder_for(state.settings) is not None
    with state.db.session() as conn:
        built = vectors.available(conn)
    rerank_ok, rerank_detail = await _rerank_status(state.settings)
    if has_embedder and built:
        detail = "keyword and vector search, fused by RRF"
    elif has_embedder:
        detail = "embedding model configured, but nothing indexed yet"
    else:
        detail = "keyword search only - set knowledge.embeddings_base_url to add vector search"
    return RetrievalStatus(
        vector=has_embedder and built,
        rerank=rerank_ok,
        detail=detail,
        rerank_detail=rerank_detail,
    )


async def _rerank_status(settings: Settings) -> tuple[bool, str]:
    """Probed, not assumed: a configured reranker that is not running is worth saying out loud."""
    client = retrieval.reranker_for(settings)
    if client is None:
        configured = bool(settings.knowledge.rerank_base_url.strip())
        return False, (
            "rerank_base_url is not loopback, so it is ignored"
            if configured
            else "no reranker - fusion order is final"
        )
    return await client.reachable()


@router.get("/open")
def open_citation(ref: str, state: State) -> OpenedChunk:
    """Resolve `path#start-end` back to the file, with surrounding text for orientation."""
    path_text, _, span = ref.rpartition("#")
    start_text, _, end_text = span.partition("-")
    try:
        start, end = int(start_text), int(end_text)
    except ValueError as exc:
        raise SovereignError("invalid_request", f"{ref!r} is not a citation reference") from exc

    path = Path(path_text)
    with state.db.session() as conn:
        known = conn.execute("SELECT 1 FROM documents WHERE path = ?", (str(path),)).fetchone()
    if known is None:
        # Only files this app indexed can be read back, so a crafted ref cannot read the disk.
        raise NotFound("Indexed document")

    raw = path.read_bytes()
    return OpenedChunk(
        path=str(path),
        byte_start=start,
        byte_end=end,
        line_number=raw[:start].count(b"\n") + 1,
        before=raw[max(0, start - CONTEXT_BYTES) : start].decode(errors="replace"),
        text=raw[start:end].decode(errors="replace"),
        after=raw[end : end + CONTEXT_BYTES].decode(errors="replace"),
    )
