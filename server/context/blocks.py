"""Building one context block of each kind.

Split out of assembler.py, which owns ordering, budget and accounting; this owns what a block of
each kind looks like. Keeping them apart means adding a new source of context is a new builder
rather than another branch inside the assembler.
"""

from __future__ import annotations

from pathlib import Path

from server.ids import new_id
from server.models.context import ContextBlock
from server.models.conversation import Conversation
from server.models.knowledge import RetrievedChunk
from server.models.memory import MemoryEntry
from server.models.message import Message
from server.models.search import SearchResult


def preview(text: str, width: int = 48) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"


def system(conversation: Conversation, tokens: int, ord: int) -> ContextBlock:
    return ContextBlock(
        id=new_id("blk"),
        ord=ord,
        kind="system",
        label="System prompt",
        content=conversation.system_prompt,
        token_count=tokens,
        pinned=True,
        source_ref=conversation.id,
    )


def memory(entry: MemoryEntry, tokens: int, ord: int) -> ContextBlock:
    """Carries the entry id, which is what lets an answer say which facts shaped it."""
    return ContextBlock(
        id=new_id("blk"),
        ord=ord,
        kind="memory",
        label=f"memory: {entry.title or preview(entry.content)}",
        content=entry.content,
        token_count=tokens,
        pinned=entry.always,
        source_ref=entry.id,
    )


def rag(chunk: RetrievedChunk, tokens: int, ord: int) -> ContextBlock:
    """source_ref is file#start-end, so the citation opens the exact span that was quoted."""
    return ContextBlock(
        id=new_id("blk"),
        ord=ord,
        kind="rag",
        label=Path(chunk.document_path).name + (f" · {chunk.heading}" if chunk.heading else ""),
        content=chunk.text,
        token_count=tokens,
        source_ref=f"{chunk.document_path}#{chunk.byte_start}-{chunk.byte_end}",
    )


def web(result: SearchResult, tokens: int, ord: int) -> ContextBlock:
    """A search snippet. source_ref is the URL, and it reaches the model as data, never as text
    to obey - the open web is the least trustworthy input this app has."""
    return ContextBlock(
        id=new_id("blk"),
        ord=ord,
        kind="web",
        label=f"{result.title[:60]} ({result.engine})" if result.engine else result.title[:60],
        content=f"{result.title}\n{result.snippet}",
        token_count=tokens,
        source_ref=result.url,
    )


def history(message: Message, tokens: int, ord: int) -> ContextBlock:
    return ContextBlock(
        id=new_id("blk"),
        ord=ord,
        kind="history",
        label=f"{message.role}: {preview(message.content)}",
        content=message.content,
        token_count=tokens,
        source_ref=message.id,
    )


def nudge(text: str, tokens: int, ord: int) -> ContextBlock:
    """A nudge changed what the model was told, so it belongs in the list like anything else."""
    return ContextBlock(
        id=new_id("blk"),
        ord=ord,
        kind="nudge",
        label=f"nudge: {preview(text)}",
        content=text,
        token_count=tokens,
        pinned=True,
    )


def prefix(text: str, tokens: int, ord: int, source_id: str | None) -> ContextBlock:
    """The partial being continued. It reaches the model through the completion endpoint rather
    than as a message, but it occupies context exactly like one - so it is listed."""
    return ContextBlock(
        id=new_id("blk"),
        ord=ord,
        kind="prefix",
        label=f"assistant (continuing): {preview(text)}",
        content=text,
        token_count=tokens,
        pinned=True,
        source_ref=source_id,
    )
