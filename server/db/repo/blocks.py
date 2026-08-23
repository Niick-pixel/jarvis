"""Per-conversation context block preferences: what you pinned, what you switched off."""

from __future__ import annotations

import sqlite3

from pydantic import BaseModel


class BlockPref(BaseModel):
    source_ref: str
    pinned: bool = False
    disabled: bool = False
    ord: int | None = None


def for_conversation(conn: sqlite3.Connection, conversation_id: str) -> dict[str, BlockPref]:
    rows = conn.execute(
        "SELECT source_ref, pinned, disabled, ord FROM block_prefs WHERE conversation_id = ?",
        (conversation_id,),
    )
    return {
        row["source_ref"]: BlockPref(
            source_ref=row["source_ref"],
            pinned=bool(row["pinned"]),
            disabled=bool(row["disabled"]),
            ord=row["ord"],
        )
        for row in rows
    }


def put(conn: sqlite3.Connection, conversation_id: str, pref: BlockPref) -> None:
    if not pref.pinned and not pref.disabled and pref.ord is None:
        # Nothing to remember: drop the row rather than keeping an all-default record.
        conn.execute(
            "DELETE FROM block_prefs WHERE conversation_id = ? AND source_ref = ?",
            (conversation_id, pref.source_ref),
        )
        return
    conn.execute(
        "INSERT INTO block_prefs (conversation_id, source_ref, pinned, disabled, ord)"
        " VALUES (?,?,?,?,?) ON CONFLICT(conversation_id, source_ref) DO UPDATE SET"
        " pinned = excluded.pinned, disabled = excluded.disabled, ord = excluded.ord",
        (conversation_id, pref.source_ref, int(pref.pinned), int(pref.disabled), pref.ord),
    )
