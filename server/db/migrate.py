"""Forward-only numbered migrations. No downgrades: a mistake is a new migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at INTEGER NOT NULL)"
    )
    return {int(r["version"]) for r in conn.execute("SELECT version FROM schema_migrations")}


def pending(conn: sqlite3.Connection) -> list[Path]:
    done = applied_versions(conn)
    files = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: int(p.name.split("_", 1)[0]))
    return [p for p in files if int(p.name.split("_", 1)[0]) not in done]


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply every pending migration in order. Returns the names applied."""
    import time

    applied: list[str] = []
    for path in pending(conn):
        version = int(path.name.split("_", 1)[0])
        conn.executescript(path.read_text())
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (version, path.name, int(time.time() * 1000)),
        )
        applied.append(path.name)
    return applied
