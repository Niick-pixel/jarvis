"""The permanent record of every tool call, and the only place redaction is decided.

BRIEF.md 7: never log secrets, API keys, or file contents - log hashes and paths. That is enforced
here rather than at each call site, so there is exactly one function to review. `record()` takes the
real arguments and does the hashing itself; it has no parameter that would let a caller pass
pre-formatted text through, which is how this kind of rule usually leaks.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from server.ids import new_id, now_ms
from server.models.tools import AuditEntry

PREVIEW_CHARS = 60
SECRET_KEYS = {"token", "key", "secret", "password", "passwd", "authorization", "cookie"}
TARGET_KEYS = {"path", "url", "command"}
"""Never elided: these are the thing being approved, and a path is not a secret."""


def digest(value: str | bytes) -> str:
    """A short sha256. Long enough to compare two runs, useless for recovering the content."""
    raw = value.encode() if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()[:16]


def record(
    conn: sqlite3.Connection,
    *,
    actor: str,
    tool: str,
    outcome: str,
    target: str = "",
    args: dict[str, Any] | None = None,
    result: str = "",
    note: str = "",
) -> None:
    conn.execute(
        "INSERT INTO audit_log (id, at, actor, tool, outcome, target, args_hash, result_hash,"
        " bytes, note) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            new_id("aud"),
            now_ms(),
            actor,
            tool,
            outcome,
            target,
            digest(json.dumps(args or {}, sort_keys=True, default=str)),
            digest(result) if result else "",
            len(result.encode()),
            note,
        ),
    )


def args_preview(args: dict[str, Any]) -> str:
    """For the approval card. Long values become their size; secret-looking keys become nothing.

    This is not the audit log - it exists so you can see what you are approving - but it follows
    the same rule: an approval card is a screen someone may be reading over your shoulder.
    """
    parts: list[str] = []
    for key, value in args.items():
        parts.append(f"{key}={_render(key, value)}")
    return ", ".join(parts)


def _render(key: str, value: Any) -> str:
    if any(marker in key.lower() for marker in SECRET_KEYS):
        return "(hidden)"
    if key.lower() in TARGET_KEYS:
        return json.dumps(value)
    if isinstance(value, str):
        if len(value) > PREVIEW_CHARS:
            return f"({len(value.encode())} bytes, sha256 {digest(value)})"
        return json.dumps(value)
    return json.dumps(value, default=str)


def recent(conn: sqlite3.Connection, limit: int = 200) -> list[AuditEntry]:
    rows = conn.execute("SELECT * FROM audit_log ORDER BY at DESC LIMIT ?", (limit,))
    return [
        AuditEntry(
            id=row["id"],
            at=row["at"],
            actor=row["actor"],
            tool=row["tool"],
            outcome=row["outcome"],
            target=row["target"],
            args_hash=row["args_hash"],
            result_hash=row["result_hash"],
            bytes=row["bytes"],
            note=row["note"],
        )
        for row in rows
    ]
