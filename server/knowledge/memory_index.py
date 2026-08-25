"""Indexing the memory directory, and retrieving from it.

The index is derived: `sync` rescans the files and rebuilds rows to match. If the database and the
directory ever disagree, the directory wins.

Retrieval is FTS5 keyword matching plus every entry marked `always`. Vector search joins this in
the RAG slice; keyword-only is honest, needs no model resident in VRAM, and on a store of a few
hundred facts it is genuinely good.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from server.knowledge import memory
from server.models.memory import MemoryEntry

FTS_UNSAFE = re.compile(r"[^\w\s]")
MAX_TERMS = 24
# Without this a question matches any entry sharing a filler word - "with" pulled in an
# unrelated fact about the GPU during testing. Small list, real precision win, no dependency.
STOPWORDS = frozenset(
    [
        "about",
        "after",
        "also",
        "and",
        "any",
        "are",
        "because",
        "been",
        "before",
        "being",
        "but",
        "can",
        "could",
        "did",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "into",
        "its",
        "just",
        "like",
        "made",
        "make",
        "many",
        "may",
        "more",
        "most",
        "much",
        "must",
        "not",
        "now",
        "only",
        "other",
        "our",
        "out",
        "over",
        "said",
        "same",
        "should",
        "since",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "too",
        "under",
        "use",
        "used",
        "using",
        "very",
        "was",
        "way",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
    ]
)
# Without this, a question matches any entry sharing a filler word - "with" pulled in an
# unrelated fact about the GPU in testing. Small list, big precision win, no dependency.


def sync(conn: sqlite3.Connection, root: Path) -> int:
    """Make the index match the files. Returns the number of entries indexed."""
    entries = memory.scan(root)
    seen = {entry.path for entry in entries}

    for entry in entries:
        conn.execute(
            "INSERT INTO memory_entries (id, path, scope, scope_ref, title, content, content_hash,"
            " always, source, batch_id, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(path) DO UPDATE SET title=excluded.title, content=excluded.content,"
            " content_hash=excluded.content_hash, always=excluded.always, scope=excluded.scope,"
            " scope_ref=excluded.scope_ref, updated_at=excluded.updated_at",
            (
                entry.id,
                entry.path,
                entry.scope,
                entry.scope_ref,
                entry.title,
                entry.content,
                memory.content_hash(entry.content),
                int(entry.always),
                entry.source,
                entry.batch_id,
                entry.created_at,
                entry.updated_at,
            ),
        )

    stale = [
        row["path"]
        for row in conn.execute("SELECT path FROM memory_entries")
        if row["path"] not in seen
    ]
    for path in stale:
        conn.execute("DELETE FROM memory_entries WHERE path = ?", (path,))
    return len(entries)


def _row(row: sqlite3.Row) -> MemoryEntry:
    data = dict(row)
    data["always"] = bool(data.get("always"))
    data.pop("content_hash", None)
    data.pop("rank", None)
    return MemoryEntry(**data)


COLUMNS = (
    "e.id, e.path, e.scope, e.scope_ref, e.title, e.content, e.always, e.source, e.batch_id,"
    " e.created_at, e.updated_at,"
    " (SELECT COUNT(*) FROM memory_usage u WHERE u.entry_id = e.id) AS retrieved_count,"
    " (SELECT MAX(used_at) FROM memory_usage u WHERE u.entry_id = e.id) AS last_used_at"
)


def list_all(conn: sqlite3.Connection) -> list[MemoryEntry]:
    return [
        _row(r)
        for r in conn.execute(f"SELECT {COLUMNS} FROM memory_entries e ORDER BY e.updated_at DESC")
    ]


def get(conn: sqlite3.Connection, entry_id: str) -> MemoryEntry | None:
    sql = f"SELECT {COLUMNS} FROM memory_entries e WHERE e.id = ?"
    row = conn.execute(sql, (entry_id,)).fetchone()
    return _row(row) if row else None


def in_batch(conn: sqlite3.Connection, batch_id: str) -> list[MemoryEntry]:
    rows = conn.execute(f"SELECT {COLUMNS} FROM memory_entries e WHERE e.batch_id = ?", (batch_id,))
    return [_row(r) for r in rows]


def _fts_query(text: str) -> str:
    """FTS5 has its own syntax; user text is data, so strip operators rather than interpret them."""
    terms = [
        term
        for term in FTS_UNSAFE.sub(" ", text.lower()).split()
        if len(term) > 2 and term not in STOPWORDS
    ][:MAX_TERMS]
    return " OR ".join(terms)


def retrieve(
    conn: sqlite3.Connection,
    query: str,
    *,
    conversation_id: str | None = None,
    project_id: str | None = None,
    limit: int = 6,
) -> list[MemoryEntry]:
    """Entries worth injecting: everything marked `always`, plus keyword matches in scope."""
    scoped = (
        "(e.scope = 'global' OR (e.scope = 'conversation' AND e.scope_ref = ?)"
        " OR (e.scope = 'project' AND e.scope_ref = ?))"
    )
    args = (conversation_id, project_id)

    always = [
        _row(r)
        for r in conn.execute(
            f"SELECT {COLUMNS} FROM memory_entries e WHERE e.always = 1 AND {scoped}", args
        )
    ]

    matches: list[MemoryEntry] = []
    if expression := _fts_query(query):
        rows = conn.execute(
            f"SELECT {COLUMNS} FROM memory_fts f JOIN memory_entries e ON e.rowid = f.rowid"
            f" WHERE memory_fts MATCH ? AND {scoped} ORDER BY rank LIMIT ?",
            (expression, *args, limit),
        )
        matches = [_row(r) for r in rows]

    seen = {entry.id for entry in always}
    return always + [entry for entry in matches if entry.id not in seen]


def record_usage(
    conn: sqlite3.Connection, entry_ids: list[str], message_id: str, used_at: int
) -> None:
    """Counted, not estimated: this is what makes 'retrieved 14 times' a fact."""
    conn.executemany(
        "INSERT INTO memory_usage (entry_id, message_id, used_at) VALUES (?,?,?)",
        [(entry_id, message_id, used_at) for entry_id in entry_ids],
    )
