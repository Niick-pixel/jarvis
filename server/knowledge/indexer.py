"""Walking a folder, chunking what changed, and embedding it without starving the model.

Section 4.8 requires indexing to be visible, pausable, and to keep out of inference's way. The
last one is not a nicety on a small card: an embedding pass and a generation competing for the same
8GB is how you get an OOM in the middle of an answer. Before every batch this yields while any run
is active.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import sqlite3
from pathlib import Path

from server.chat.live import LiveRuns
from server.db.connection import Database
from server.ids import new_id, now_ms
from server.knowledge import chunker, vectors
from server.models.knowledge import IndexProgress
from server.providers.embeddings import EmbeddingClient

log = logging.getLogger(__name__)
EMBED_BATCH = 16
YIELD_POLL_S = 0.4


class Indexer:
    def __init__(self, db: Database, live: LiveRuns) -> None:
        self.db = db
        self.live = live
        self.progress: dict[str, IndexProgress] = {}
        self._paused = asyncio.Event()
        self._paused.set()  # set == running

    @property
    def paused(self) -> bool:
        return not self._paused.is_set()

    def pause(self) -> None:
        self._paused.clear()

    def resume(self) -> None:
        self._paused.set()

    async def _breathe(self, source_id: str) -> None:
        """Wait out a pause, and stand aside while the model is generating."""
        if self.paused:
            self._set(source_id, state="paused", detail="paused")
            await self._paused.wait()
        while self.live.active_ids():
            self._set(
                source_id,
                state="embedding",
                detail="waiting for generation to finish - indexing never competes for the GPU",
            )
            await asyncio.sleep(YIELD_POLL_S)

    def _set(self, source_id: str, **fields: object) -> IndexProgress:
        current = self.progress.get(source_id) or IndexProgress(source_id=source_id)
        updated = current.model_copy(update=fields)
        self.progress[source_id] = updated
        return updated

    def scan(self, root: Path) -> list[Path]:
        if root.is_file():
            return [root] if chunker.is_supported(root) else []
        return [
            path
            for path in sorted(root.rglob("*"))
            if path.is_file() and chunker.is_supported(path) and not _hidden(path)
        ]

    async def index(
        self, source_id: str, root: Path, embedder: EmbeddingClient | None
    ) -> IndexProgress:
        try:
            return await self._index(source_id, root, embedder)
        except Exception as exc:  # noqa: BLE001 - a bad file must not kill the indexer
            log.warning("index of %s failed: %s", root, exc)
            return self._set(source_id, state="error", detail=f"{type(exc).__name__}: {exc}")

    async def _index(
        self, source_id: str, root: Path, embedder: EmbeddingClient | None
    ) -> IndexProgress:
        self._set(source_id, state="scanning", detail=f"scanning {root}")
        files = self.scan(root)
        self._set(source_id, files_total=len(files), files_done=0, state="chunking")

        indexed = 0
        with self.db.session() as conn:
            for done, path in enumerate(files, start=1):
                indexed += self._index_file(conn, source_id, path)
                self._set(
                    source_id,
                    files_done=done,
                    chunks_indexed=indexed,
                    detail=f"chunking {path.name}",
                )
            conn.execute(
                "UPDATE sources SET file_count = ?, chunk_count ="
                " (SELECT COUNT(*) FROM chunks c JOIN documents d ON d.id = c.document_id"
                "  WHERE d.source_id = ?), last_indexed = ? WHERE id = ?",
                (len(files), source_id, now_ms(), source_id),
            )

        if embedder is None:
            return self._set(
                source_id,
                state="done",
                detail="indexed for keyword search. No embedding model is configured, so vector "
                "search is off and retrieval says so rather than pretending.",
            )
        return await self._embed_pending(source_id, embedder)

    def _index_file(self, conn: sqlite3.Connection, source_id: str, path: Path) -> int:
        try:
            stat = path.stat()
        except OSError:
            return 0
        text = chunker.read_text(path)
        if text is None:
            return 0
        content_hash = hashlib.blake2b(text.encode(), digest_size=16).hexdigest()

        row = conn.execute(
            "SELECT id, content_hash FROM documents WHERE path = ?", (str(path),)
        ).fetchone()
        if row and row["content_hash"] == content_hash:
            return 0  # unchanged since last time

        document_id = row["id"] if row else new_id("doc")
        if row:
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        conn.execute(
            "INSERT INTO documents (id, source_id, path, content_hash, mtime_ms, size_bytes,"
            " indexed_at) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(path) DO UPDATE SET content_hash=excluded.content_hash,"
            " mtime_ms=excluded.mtime_ms, size_bytes=excluded.size_bytes,"
            " indexed_at=excluded.indexed_at",
            (
                document_id,
                source_id,
                str(path),
                content_hash,
                int(stat.st_mtime * 1000),
                stat.st_size,
                now_ms(),
            ),
        )
        chunks = chunker.chunk_text(text)
        conn.executemany(
            "INSERT INTO chunks (id, document_id, ord, heading, text, byte_start, byte_end)"
            " VALUES (?,?,?,?,?,?,?)",
            [
                (
                    new_id("chk"),
                    document_id,
                    chunk.ord,
                    chunk.heading,
                    chunk.text,
                    chunk.byte_start,
                    chunk.byte_end,
                )
                for chunk in chunks
            ],
        )
        return len(chunks)

    async def _embed_pending(self, source_id: str, embedder: EmbeddingClient) -> IndexProgress:
        with self.db.session() as conn:
            pending = list(
                conn.execute(
                    "SELECT c.rowid AS rid, c.id, c.text FROM chunks c"
                    " JOIN documents d ON d.id = c.document_id"
                    " WHERE d.source_id = ? AND c.embedded = 0",
                    (source_id,),
                )
            )
        self._set(source_id, state="embedding", chunks_pending=len(pending))
        embedded = 0

        for start in range(0, len(pending), EMBED_BATCH):
            await self._breathe(source_id)
            batch = pending[start : start + EMBED_BATCH]
            vectorised = await embedder.embed([row["text"] for row in batch])
            with self.db.session() as conn:
                for row, vector in zip(batch, vectorised, strict=False):
                    vectors.upsert(conn, int(row["rid"]), vector)
                    conn.execute("UPDATE chunks SET embedded = 1 WHERE id = ?", (row["id"],))
            embedded += len(batch)
            self._set(
                source_id,
                chunks_embedded=embedded,
                chunks_pending=max(0, len(pending) - embedded),
                detail=f"embedded {embedded} of {len(pending)} chunks",
            )

        return self._set(source_id, state="done", detail="indexed and embedded")


def _hidden(path: Path) -> bool:
    return any(part.startswith(".") or part == "node_modules" for part in path.parts)
