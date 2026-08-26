"""A running per-model record, by task category (BRIEF.md 4.6)."""

from __future__ import annotations

import sqlite3

from server.models.council import ScoreboardRow


def record(
    conn: sqlite3.Connection,
    *,
    category: str,
    appearances: list[str],
    winner_model_id: str | None,
) -> None:
    """Every member appeared; at most one won. Recording both is what makes a rate mean
    anything - wins alone just favour whichever model is asked most often."""
    for model_id in appearances:
        conn.execute(
            "INSERT INTO model_scores (model_id, category, wins, appearances) VALUES (?,?,0,1)"
            " ON CONFLICT(model_id, category) DO UPDATE SET appearances = appearances + 1",
            (model_id, category),
        )
    if winner_model_id:
        conn.execute(
            "UPDATE model_scores SET wins = wins + 1 WHERE model_id = ? AND category = ?",
            (winner_model_id, category),
        )


def read(conn: sqlite3.Connection) -> list[ScoreboardRow]:
    rows = conn.execute(
        "SELECT model_id, category, wins, appearances FROM model_scores"
        " ORDER BY category, CAST(wins AS REAL) / MAX(appearances, 1) DESC"
    )
    return [ScoreboardRow(**dict(row)) for row in rows]
