"""Pure conversation-DAG logic. No I/O, no SQL - which is what makes it testable (rule 0.7).

Every function takes the conversation's full message list and derives what it needs. The lists are
small (a long conversation is hundreds of nodes) and purity is worth more here than cleverness.
"""

from __future__ import annotations

from collections import defaultdict

from server.models.message import Message, SiblingSet

MAX_DEPTH = 100_000
"""Defensive bound. The schema makes cycles impossible; this makes a corrupt DB fail loudly."""


class CycleError(RuntimeError):
    """Raised if the message graph is not a tree. Should be unreachable outside a corrupt DB."""


def by_id(messages: list[Message]) -> dict[str, Message]:
    return {m.id: m for m in messages}


def children_map(messages: list[Message]) -> dict[str | None, list[Message]]:
    """Parent id -> children, in stable sibling order (created_at, id)."""
    out: dict[str | None, list[Message]] = defaultdict(list)
    for m in sorted(messages, key=lambda m: (m.created_at, m.id)):
        out[m.parent_id].append(m)
    return out


def children(messages: list[Message], parent_id: str | None) -> list[Message]:
    return children_map(messages).get(parent_id, [])


def roots(messages: list[Message]) -> list[Message]:
    return children(messages, None)


def ancestors(messages: list[Message], node_id: str) -> list[Message]:
    """Root-to-node path, inclusive. This is the prompt's message order."""
    index = by_id(messages)
    chain: list[Message] = []
    seen: set[str] = set()
    cursor: str | None = node_id
    depth = 0
    while cursor is not None:
        node = index.get(cursor)
        if node is None:
            break
        if node.id in seen:
            raise CycleError(f"cycle at {node.id}")
        seen.add(node.id)
        chain.append(node)
        cursor = node.parent_id
        depth += 1
        if depth > MAX_DEPTH:
            raise CycleError("max depth exceeded")
    chain.reverse()
    return chain


def path_to_leaf(messages: list[Message], leaf_id: str | None) -> list[Message]:
    """The active path. With no leaf pointer, follow the newest branch down from the newest root."""
    if leaf_id is not None and leaf_id in by_id(messages):
        return ancestors(messages, leaf_id)
    start = roots(messages)
    if not start:
        return []
    return ancestors(messages, descend(messages, start[-1].id).id)


def descend(messages: list[Message], node_id: str) -> Message:
    """Follow the newest child repeatedly until a leaf. Used when a fork needs a default leaf."""
    kids = children_map(messages)
    index = by_id(messages)
    node = index[node_id]
    depth = 0
    while True:
        next_kids = kids.get(node.id, [])
        if not next_kids:
            return node
        node = next_kids[-1]
        depth += 1
        if depth > MAX_DEPTH:
            raise CycleError("max depth exceeded")


def leaves(messages: list[Message]) -> list[Message]:
    kids = children_map(messages)
    return [m for m in messages if not kids.get(m.id)]


def siblings(messages: list[Message], node_id: str) -> SiblingSet:
    """Powers the inline `< 2/4 >` switcher; ordering is stable across renders."""
    index = by_id(messages)
    node = index.get(node_id)
    if node is None:
        return SiblingSet(ids=[], index=0)
    group = children(messages, node.parent_id)
    ids = [m.id for m in group]
    return SiblingSet(ids=ids, index=ids.index(node_id) if node_id in ids else 0)


def subtree_ids(messages: list[Message], node_id: str) -> set[str]:
    """Every node at or below `node_id`."""
    kids = children_map(messages)
    out: set[str] = set()
    stack = [node_id]
    while stack:
        current = stack.pop()
        if current in out:
            raise CycleError(f"cycle at {current}")
        out.add(current)
        stack.extend(child.id for child in kids.get(current, []))
    return out
