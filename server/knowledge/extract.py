"""Proposing facts worth remembering, after a turn finishes (BRIEF.md 4.7).

Capture is automatic but never silent: everything written lands in one batch, the UI says how many
and shows them, and undo removes exactly that batch. The files are plain Markdown either way, so
the worst case is you delete a file.

It runs after the answer is complete rather than before, and off the streaming path, so it never
delays a token. It still costs a short generation, which on a small card is real - hence the
`enabled` switch and the length floor.
"""

from __future__ import annotations

import logging
import re

from server.models.params import SamplingParams
from server.providers.base import ModelProvider, PromptMessage, Token

log = logging.getLogger(__name__)

PROMPT = """From the exchange below, list any durable facts about the user worth remembering for
future conversations: preferences, their hardware, projects they work on, how they want replies
written. Only things that stay true beyond this conversation.

Rules:
- One fact per line, written as a short standalone sentence.
- No preamble, no numbering, no commentary.
- If there is nothing durable, reply with exactly: NONE

Exchange:
user: {question}
assistant: {answer}
"""

BULLET = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s*")
MAX_FACT_CHARS = 240


def parse_facts(raw: str, limit: int) -> list[str]:
    """Line-delimited, defensively parsed: a model that ignores the format yields nothing."""
    if "NONE" in raw.upper()[:40]:
        return []
    facts: list[str] = []
    for line in raw.splitlines():
        candidate = BULLET.sub("", line).strip().strip('"')
        if len(candidate) < 12 or len(candidate) > MAX_FACT_CHARS:
            continue
        if candidate.upper() == "NONE" or candidate.endswith(":"):
            continue
        facts.append(candidate)
        if len(facts) >= limit:
            break
    return facts


async def propose(
    provider: ModelProvider,
    *,
    model_id: str,
    ctx_len: int,
    question: str,
    answer: str,
    limit: int,
) -> list[str]:
    params = SamplingParams(seed=7, temperature=0.2, max_tokens=200, n_probs=0)
    messages = [PromptMessage(role="user", content=PROMPT.format(question=question, answer=answer))]
    chunks: list[str] = []
    try:
        async for item in provider.stream(messages, params, model_id=model_id, ctx_len=ctx_len):
            if isinstance(item, Token):
                chunks.append(item.text)
    except Exception as exc:  # noqa: BLE001 - extraction failing must never fail the turn
        log.warning("memory: extraction failed: %s", exc)
        return []
    return parse_facts("".join(chunks), limit)
