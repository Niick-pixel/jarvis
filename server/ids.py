"""Time-ordered ids: k-sortable like uuid7, so `ORDER BY id` matches creation order."""

from __future__ import annotations

import secrets
import time


def new_id(prefix: str = "") -> str:
    stamp = format(int(time.time() * 1000), "012x")
    body = f"{stamp}{secrets.token_hex(8)}"
    return f"{prefix}_{body}" if prefix else body


def now_ms() -> int:
    return int(time.time() * 1000)
