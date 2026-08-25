"""The memory directory: plain Markdown files with a small front-matter header.

One file per fact. It makes git diffs readable, makes "forget this" an `rm`, and means the whole
store is inspectable with `cat` and `grep` - which is the difference between memory you own and
memory a product keeps about you.

Front-matter is parsed by hand rather than with a YAML dependency: the format is six known keys,
and a parser you can read in one screen is worth more here than generality.
"""

from __future__ import annotations

import hashlib
import re
from contextlib import suppress
from pathlib import Path

from server.ids import new_id, now_ms
from server.models.memory import MemoryEntry, MemoryScope

FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)
SLUG = re.compile(r"[^a-z0-9]+")


def content_hash(text: str) -> str:
    return hashlib.blake2b(text.encode(), digest_size=16).hexdigest()


def scope_dir(root: Path, scope: MemoryScope, scope_ref: str | None) -> Path:
    if scope == "global":
        return root / "global"
    if scope == "project":
        return root / "projects" / (scope_ref or "unscoped")
    return root / "conversations" / (scope_ref or "unscoped")


def slugify(title: str, fallback: str) -> str:
    slug = SLUG.sub("-", title.strip().lower()).strip("-")
    return (slug or fallback)[:60]


def serialize(entry: MemoryEntry) -> str:
    header = "\n".join(
        [
            "---",
            f"id: {entry.id}",
            f"title: {entry.title}",
            f"always: {'true' if entry.always else 'false'}",
            f"source: {entry.source}",
            f"batch: {entry.batch_id or ''}",
            f"created: {entry.created_at}",
            "---",
        ]
    )
    return f"{header}\n{entry.content.strip()}\n"


def parse(path: Path, root: Path) -> MemoryEntry | None:
    """Read one file. A file without front-matter is still memory - it just gets defaults."""
    try:
        raw = path.read_text()
    except OSError:
        return None

    fields: dict[str, str] = {}
    body = raw
    if match := FRONT_MATTER.match(raw):
        for line in match.group(1).splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                fields[key.strip()] = value.strip()
        body = match.group(2)

    relative = path.relative_to(root).as_posix()
    scope, scope_ref = scope_of(relative)
    created = int(fields.get("created") or now_ms())
    return MemoryEntry(
        id=fields.get("id") or new_id("mem"),
        path=relative,
        scope=scope,
        scope_ref=scope_ref,
        title=fields.get("title") or path.stem.replace("-", " "),
        content=body.strip(),
        always=fields.get("always", "false").lower() == "true",
        source="auto" if fields.get("source") == "auto" else "manual",
        batch_id=fields.get("batch") or None,
        created_at=created,
        updated_at=int(path.stat().st_mtime * 1000),
    )


def scope_of(relative: str) -> tuple[MemoryScope, str | None]:
    parts = relative.split("/")
    if parts[0] == "projects" and len(parts) >= 3:
        return "project", parts[1]
    if parts[0] == "conversations" and len(parts) >= 3:
        return "conversation", parts[1]
    return "global", None


def scan(root: Path) -> list[MemoryEntry]:
    if not root.is_dir():
        return []
    found = [parse(path, root) for path in sorted(root.rglob("*.md"))]
    return [entry for entry in found if entry is not None]


def write(root: Path, entry: MemoryEntry) -> Path:
    directory = scope_dir(root, entry.scope, entry.scope_ref)
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{slugify(entry.title, entry.id)}.md"
    path = directory / name
    # Never silently overwrite a different fact that happens to share a title.
    if path.exists():
        existing = parse(path, root)
        if existing and existing.id != entry.id:
            path = directory / f"{slugify(entry.title, entry.id)}-{entry.id[-6:]}.md"
    path.write_text(serialize(entry))
    return path


def delete(root: Path, relative: str) -> bool:
    """A hard delete, per BRIEF.md 4.7: not a tombstone, not a soft flag."""
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        return False
    path.unlink()
    # Tidy away scope directories the delete just emptied.
    for parent in (path.parent, path.parent.parent):
        with suppress(OSError):
            if parent.is_dir() and parent != root and not any(parent.iterdir()):
                parent.rmdir()
    return True
