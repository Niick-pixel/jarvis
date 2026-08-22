"""Shared SSE line parsing for the HTTP-based providers.

Not in the PLAN.md tree: llama.cpp and every OpenAI-compatible backend both stream `data:` lines,
and one parser read in one place beats the same ten lines in two adapters.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


async def iter_sse_json(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    """Yield decoded JSON payloads from an SSE body, stopping at the `[DONE]` sentinel."""
    async for raw in response.aiter_lines():
        line = raw.strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if line == "[DONE]":
            return
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            yield payload
