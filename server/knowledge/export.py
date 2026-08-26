"""One conversation branch, as a note you would have written yourself (BRIEF.md 4.11).

Front-matter, headings, and `[[wikilinks]]` to whatever the answer actually drew on - the memory
entries that were retrieved and the files that were cited, taken from the recorded context
assembly rather than guessed from the text. A conversation should compost into notes rather than
die in a sidebar, and a note full of JSON is not a note.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from server.db import repo
from server.models.conversation import Conversation
from server.models.export import ExportResult
from server.models.message import Message

SLUG = re.compile(r"[^a-z0-9]+")
ROLE_HEADING = {"user": "You", "assistant": "Jarvis", "system": "System", "nudge": "Interjection"}


def slugify(title: str, fallback: str) -> str:
    slug = SLUG.sub("-", title.lower()).strip("-")
    return slug[:60] or fallback


def _stamp(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat(timespec="seconds")


def links_for(conn: sqlite3.Connection, messages: list[Message]) -> list[str]:
    """Every memory entry and file the recorded assemblies say went into these answers."""
    links: list[str] = []
    ids = [m.id for m in messages if m.role == "assistant"]
    if not ids:
        return links
    rows = conn.execute(
        f"SELECT assembly_json FROM runs WHERE message_id IN ({','.join('?' * len(ids))})", ids
    )
    for row in rows:
        if not row["assembly_json"]:
            continue
        for block in json.loads(row["assembly_json"]).get("blocks", []):
            link = _link_for(conn, block)
            if link and link not in links:
                links.append(link)
    return links


def _link_for(conn: sqlite3.Connection, block: dict[str, object]) -> str:
    ref = str(block.get("source_ref") or "")
    kind = block.get("kind")
    if not ref or not block.get("included"):
        return ""
    if kind == "rag":
        return f"[[{Path(ref.split('#')[0]).stem}]]"
    if kind == "memory":
        row = conn.execute("SELECT title FROM memory_entries WHERE id = ?", (ref,)).fetchone()
        return f"[[{row['title']}]]" if row and row["title"] else ""
    if kind == "web":
        return f"<{ref}>"
    return ""


def render(conversation: Conversation, messages: list[Message], links: list[str]) -> str:
    models = sorted({m.model_id for m in messages if m.model_id})
    title = conversation.title or "Untitled conversation"
    front = [
        "---",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"created: {_stamp(conversation.created_at)}",
        f"updated: {_stamp(conversation.updated_at)}",
        f"models: [{', '.join(models)}]",
        f"conversation: {conversation.id}",
        "tags: [jarvis]",
        "---",
        "",
        f"# {title}",
        "",
        "",
    ]
    body: list[str] = []
    for message in messages:
        if message.role == "system" or not message.content.strip():
            continue
        heading = ROLE_HEADING.get(message.role, message.role)
        suffix = (
            f" · {message.model_id}" if message.role == "assistant" and message.model_id else ""
        )
        body.append(f"## {heading}{suffix}\n\n{message.content.strip()}\n")
    if links:
        body.append("## Sources\n\n" + "\n".join(f"- {link}" for link in links) + "\n")
    return "\n".join(front) + "\n".join(body)


def export(conn: sqlite3.Connection, conversation_id: str, vault_dir: Path) -> ExportResult | None:
    """Write the active branch into the vault. Returns None when there is no such conversation."""
    conversation = repo.conversations.get(conn, conversation_id)
    if conversation is None:
        return None
    tree = repo.messages.list_for_conversation(conn, conversation_id)
    messages = [m for m in tree if m.id in _active_ids(tree, conversation.active_leaf_id)]
    links = links_for(conn, messages)
    note = render(conversation, messages, links)
    vault_dir.mkdir(parents=True, exist_ok=True)
    target = vault_dir / f"{slugify(conversation.title, conversation.id)}.md"
    target.write_text(note)
    return ExportResult(
        path=str(target.resolve()),
        bytes=len(note.encode()),
        messages=len(messages),
        links=links,
    )


def _active_ids(tree: list[Message], leaf_id: str | None) -> set[str]:
    """The branch you are looking at, root to leaf - not every fork you tried on the way."""
    by_id = {m.id: m for m in tree}
    current = leaf_id or (tree[-1].id if tree else None)
    ids: set[str] = set()
    while current and current in by_id:
        ids.add(current)
        current = by_id[current].parent_id
    return ids
