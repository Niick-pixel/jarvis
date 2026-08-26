"""Spotting a document that is trying to give orders.

This never blocks anything and never edits the text. Retrieved material already reaches the model
inside a data envelope it is told not to obey; this is the other half of the same rule - the part
where *you* get told, because a page that tries this is worth knowing about even when it fails.
"""

from __future__ import annotations

import re

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "overrides your instructions",
        re.compile(
            r"\b(ignore|disregard|forget)\b[^.\n]{0,30}\b(previous|prior|above|all|your)?"
            r"[^.\n]{0,20}\b(instructions?|rules?|prompt)\b",
            re.I,
        ),
    ),
    (
        "tries to redefine the assistant",
        re.compile(
            r"\byou are now\b|\bfrom now on,? you\b|\bnew (system )?(prompt|instructions?)\b", re.I
        ),
    ),
    (
        "asks for the system prompt",
        re.compile(
            r"\b(reveal|print|repeat|show)\b[^.\n]{0,25}\b(system prompt|instructions|rules)\b",
            re.I,
        ),
    ),
    (
        "asks for credentials",
        re.compile(r"\b(api[- ]?key|password|secret|private key|token|\.env|id_rsa)\b", re.I),
    ),
    (
        "asks for data to be sent somewhere",
        re.compile(
            r"\b(email|send|upload|post|exfiltrate|forward)\b[^.\n]{0,30}\b(to|at)\b[^.\n]{0,20}"
            r"([\w.-]+@[\w.-]+|https?://)",
            re.I,
        ),
    ),
    (
        "asks for a command to be run",
        re.compile(
            r"\b(run|execute)\b[^.\n]{0,20}\b(command|shell|script|curl|bash)\b|rm\s+-rf\s+", re.I
        ),
    ),
]
QUOTE_CHARS = 90


def scan(text: str) -> list[str]:
    """Returns one short description plus the matching quote for each pattern that fires."""
    found: list[str] = []
    for label, pattern in PATTERNS:
        match = pattern.search(text)
        if match:
            quote = " ".join(match.group(0).split())[:QUOTE_CHARS]
            found.append(f"{label}: “{quote}”")
    return found
