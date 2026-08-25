"""The sqlite-vec table, created once the embedding dimension is known.

The dimension is a property of the model, not of the schema, so the table cannot exist until a
model has answered. Recording the dimension means a model change is detected rather than silently
comparing vectors that do not belong to the same space.
"""

from __future__ import annotations

import sqlite3
import struct

from server.db.repo import settings as settings_repo

DIMENSION_KEY = "embedding_dimension"
MODEL_KEY = "embedding_model_id"


def serialize(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def ensure_table(conn: sqlite3.Connection, dimension: int, model_id: str) -> bool:
    """Create the vector table if needed. Returns True when a reindex is required."""
    stored_dim = settings_repo.get(conn, DIMENSION_KEY)
    stored_model = settings_repo.get(conn, MODEL_KEY)

    if stored_dim is not None and int(stored_dim) != dimension:
        # A different embedding space entirely: old vectors are meaningless against new queries.
        conn.execute("DROP TABLE IF EXISTS vec_chunks")
        conn.execute("UPDATE chunks SET embedded = 0")
        stored_dim = None

    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding float[{dimension}])"
    )
    settings_repo.put(conn, DIMENSION_KEY, dimension)
    settings_repo.put(conn, MODEL_KEY, model_id)
    return stored_dim is None and stored_model is not None and stored_model != model_id


def upsert(conn: sqlite3.Connection, rowid: int, vector: list[float]) -> None:
    conn.execute("DELETE FROM vec_chunks WHERE rowid = ?", (rowid,))
    conn.execute(
        "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)", (rowid, serialize(vector))
    )


def search(conn: sqlite3.Connection, vector: list[float], limit: int) -> list[tuple[int, float]]:
    rows = conn.execute(
        "SELECT rowid, distance FROM vec_chunks WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
        (serialize(vector), limit),
    )
    return [(int(r["rowid"]), float(r["distance"])) for r in rows]


def available(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE name = 'vec_chunks'").fetchone()
    return row is not None
