"""Synthetic content for the development stand-in.

Split out of dev_stub_server.py, which owns the protocol surfaces; this owns what it says. None of
it means anything - the point is to exercise shapes: line-delimited replies, seeded variation
between council members, and vectors of the right length.
"""

from __future__ import annotations

import hashlib
import math
import random
import re

WORDS = [
    "the",
    "local",
    "model",
    "runs",
    "on",
    "your",
    "own",
    "hardware",
    "which",
    "means",
    "every",
    "token",
    "you",
    "generate",
    "is",
    "yours",
    "and",
    "nothing",
    "leaves",
    "this",
    "machine",
    "you",
    "can",
    "edit",
    "what",
    "i",
    "just",
    "said",
    "fork",
    "the",
    "conversation",
    "and",
    "continue",
    "from",
    "your",
    "own",
    "version",
]


def lines_for(prompt: str) -> list[str] | None:
    """Synthetic line-delimited replies for the two prompts that require that shape."""
    if "One query per line" in prompt:
        return [
            "vram budget local llm\n",
            "kv cache size 32k context\n",
            "gguf quantisation sizes\n",
        ]
    if "RANKING:" in prompt:
        # The judge's reply shape, so the verdict path can be exercised. The ranking is arbitrary:
        # this stand-in has no opinion about answers it did not read.
        labels = re.findall(r"^\[([A-Z])\]$", prompt, re.MULTILINE)
        order = " > ".join(labels) if labels else "A"
        return [
            f"RANKING: {order}\n",
            "DISAGREEMENT: The answers cover different ground; none contradicts another "
            "outright.\n",
            "SYNTHESIS: A synthetic verdict from the development stand-in. It read labels, "
            "not names.\n",
        ]
    if "You can use tools." in prompt:
        return _agent_reply(prompt)
    if "One fact per line" in prompt:
        return [
            "The user runs an 8GB NVIDIA card under WSL2.\n",
            "The user prefers short answers.\n",
        ]
    return None


def _agent_reply(prompt: str) -> list[str]:
    """The agent loop's shape, driven by the job prompt rather than by any intelligence.

    A job prompt containing `CALL: {json}` lines makes this stand-in emit exactly those tool
    blocks on its first turn - which is how the approval gate, the sandbox and the injection
    boundary get exercised without a model that can decide anything. Once tool results come back
    it writes a closing report, because the loop ends on a turn with no tool block in it.
    """
    if '<context source="tool:' in prompt:
        return [
            "Run complete. ",
            "The tool results are above; nothing in them was treated as an instruction.\n",
        ]
    scripted = re.findall(r"^CALL: (.+)$", prompt, re.MULTILINE)
    if not scripted:
        return ["This stand-in only calls tools that the job prompt scripts with CALL: lines.\n"]
    blocks = ["Working on it.\n\n"]
    for call in scripted:
        blocks.append("```tool\n" + call.strip() + "\n```\n")
    return blocks


def shuffled_words(rng: random.Random) -> list[str]:
    words = list(WORDS)
    rng.shuffle(words)
    return [w + " " for w in words]


def overlap_score(query: str, document: str) -> float:
    """A stand-in for a cross-encoder: how much of the question appears in the passage.

    A real reranker reads the pair and judges meaning; this counts words. It is enough to prove
    that scores come back, that the order actually changes, and that a failure degrades to fusion
    order - and it is never enough to mistake for retrieval quality.
    """
    terms = {w for w in re.findall(r"\w+", query.lower()) if len(w) > 2}
    if not terms:
        return 0.0
    words = re.findall(r"\w+", document.lower())
    hits = sum(1 for w in set(words) if w in terms)
    return round(hits / len(terms), 4)


def fake_vector(text: str, dimension: int = 64) -> list[float]:
    seed = int(hashlib.blake2b(text.encode(), digest_size=8).hexdigest(), 16)
    rng = random.Random(seed)
    raw = [rng.uniform(-1.0, 1.0) for _ in range(dimension)]
    norm = math.sqrt(sum(v * v for v in raw)) or 1.0
    return [v / norm for v in raw]
