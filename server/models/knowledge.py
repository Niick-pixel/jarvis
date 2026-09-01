"""RAG over your own disk (BRIEF.md 4.8)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

SourceKind = Literal["folder", "file"]
Observer = Literal["native", "polling"]
IndexState = Literal["idle", "scanning", "chunking", "embedding", "paused", "done", "error"]


class Source(BaseModel):
    id: str
    path: str
    kind: SourceKind = "folder"
    observer: Observer = "native"
    """Windows drives under /mnt/c do not deliver inotify events, so those are polled."""
    enabled: bool = True
    file_count: int = 0
    chunk_count: int = 0
    last_indexed: int | None = None
    created_at: int = 0


class SourceCreate(BaseModel):
    path: str


class IndexProgress(BaseModel):
    source_id: str
    state: IndexState = "idle"
    files_total: int = 0
    files_done: int = 0
    chunks_indexed: int = 0
    chunks_embedded: int = 0
    chunks_pending: int = 0
    detail: str = ""
    """Plain sentence: what it is doing, or why it stopped."""


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_path: str
    heading: str
    text: str
    byte_start: int
    byte_end: int
    score: float
    matched_by: list[str] = []
    """Which retrievers found it - 'keyword', 'vector', or both. Fusion is not a black box."""
    rerank_score: float | None = None
    """The cross-encoder's score for this chunk against this question. None when reranking is off
    or unreachable, which is the difference between "scored badly" and "never scored"."""
