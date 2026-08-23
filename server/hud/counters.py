"""Lifetime totals, and the equivalent API spend avoided."""

from __future__ import annotations

import sqlite3

from server.models.hud import LifetimeCounters

DEFAULT_RATE_PER_MILLION_USD = 10.0
"""A blended output-token price for a mid-tier hosted model. Deliberately visible in the response
rather than buried: it is an assumption, and a different one changes the number."""


def read(
    conn: sqlite3.Connection, rate_per_million: float = DEFAULT_RATE_PER_MILLION_USD
) -> LifetimeCounters:
    values = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM counters")}
    tokens = values.get("tokens_generated", 0.0)
    return LifetimeCounters(
        tokens_generated=tokens,
        runs_completed=values.get("runs_completed", 0.0),
        cost_avoided_usd=tokens / 1_000_000 * rate_per_million,
        rate_per_million_usd=rate_per_million,
    )
