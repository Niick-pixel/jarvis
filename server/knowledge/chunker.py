"""Turning a file into chunks that remember where they came from.

Byte offsets are the point. A citation that says "this came from notes.md" is a claim; one that
opens the file at byte 4,182 is checkable, which is the difference between a retrieval system you
trust and one you hope about.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

TEXT_SUFFIXES = {
    ".md",
    ".markdown",
    ".txt",
    ".rst",
    ".org",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".swift",
    ".kt",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".sh",
    ".sql",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".html",
    ".css",
}
PDF_SUFFIXES = {".pdf"}
SUPPORTED = TEXT_SUFFIXES | PDF_SUFFIXES

TARGET_CHARS = 1100
OVERLAP_CHARS = 150
MIN_CHARS = 80
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class Chunk:
    ord: int
    heading: str
    text: str
    byte_start: int
    byte_end: int


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED


def read_text(path: Path) -> str | None:
    """Extract text. PDFs go through PyMuPDF; anything else is decoded as UTF-8."""
    suffix = path.suffix.lower()
    try:
        if suffix in PDF_SUFFIXES:
            import pymupdf

            with pymupdf.open(path) as document:
                return "\n\n".join(page.get_text() for page in document)
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - an unreadable file is skipped, never fatal
        return None


def _sections(text: str) -> list[tuple[str, int, int]]:
    """Split on Markdown headings, returning (heading, start, end) character spans.

    Chunking across a heading boundary mixes two topics into one embedding, which is the most
    common reason a retrieval hit looks relevant and is not.
    """
    lines = text.splitlines(keepends=True)
    spans: list[tuple[str, int, int]] = []
    heading = ""
    start = 0
    cursor = 0
    for line in lines:
        match = HEADING.match(line.rstrip("\n"))
        if match and cursor > start:
            spans.append((heading, start, cursor))
            heading = match.group(2).strip()
            start = cursor
        elif match:
            heading = match.group(2).strip()
        cursor += len(line)
    spans.append((heading, start, len(text)))
    return [s for s in spans if s[2] > s[1]]


def _split_span(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Break one section into overlapping windows, preferring paragraph boundaries."""
    windows: list[tuple[int, int]] = []
    cursor = start
    while cursor < end:
        stop = min(cursor + TARGET_CHARS, end)
        if stop < end:
            paragraph = text.rfind("\n\n", cursor + MIN_CHARS, stop)
            sentence = text.rfind(". ", cursor + MIN_CHARS, stop)
            boundary = max(paragraph, sentence)
            if boundary > cursor:
                stop = boundary + (2 if boundary == paragraph else 2)
        windows.append((cursor, stop))
        if stop >= end:
            break
        cursor = max(cursor + MIN_CHARS, stop - OVERLAP_CHARS)
    return windows


def chunk_text(text: str) -> list[Chunk]:
    """Chunks with byte offsets into the UTF-8 encoding of `text`.

    Short sections are merged forward rather than dropped. Dropping them loses them from the index
    entirely - a file of brief notes would simply not be searchable, and nothing would say so.
    """
    encoded_prefix = _prefix_lengths(text)
    spans: list[tuple[str, int, int]] = []
    for heading, span_start, span_end in _sections(text):
        for char_start, char_end in _split_span(text, span_start, span_end):
            if text[char_start:char_end].strip():
                spans.append((heading, char_start, char_end))

    merged = _coalesce_short(text, spans)
    return [
        Chunk(
            ord=index,
            heading=heading,
            text=text[char_start:char_end].strip(),
            byte_start=encoded_prefix[char_start],
            byte_end=encoded_prefix[char_end],
        )
        for index, (heading, char_start, char_end) in enumerate(merged)
    ]


def _coalesce_short(text: str, spans: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    """Fold spans below the floor into their neighbour, keeping the earlier heading."""
    out: list[tuple[str, int, int]] = []
    for heading, start, end in spans:
        if out and len(text[start:end].strip()) < MIN_CHARS:
            previous_heading, previous_start, _ = out[-1]
            out[-1] = (previous_heading, previous_start, end)
            continue
        out.append((heading, start, end))
    # A short leading span has no previous neighbour, so fold it into the one that follows.
    while len(out) > 1 and len(text[out[0][1] : out[0][2]].strip()) < MIN_CHARS:
        heading, start, _ = out[0]
        _, _, next_end = out[1]
        out[0:2] = [(heading, start, next_end)]
    return out


def _prefix_lengths(text: str) -> list[int]:
    """Character index -> byte offset, so offsets survive non-ASCII content."""
    lengths = [0] * (len(text) + 1)
    total = 0
    for index, character in enumerate(text):
        lengths[index] = total
        total += len(character.encode())
    lengths[len(text)] = total
    return lengths


def chunk_file(path: Path) -> list[Chunk]:
    text = read_text(path)
    return chunk_text(text) if text else []
