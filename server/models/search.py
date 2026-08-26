"""Private web search and multi-step research (BRIEF.md 4.8, 3)."""

from __future__ import annotations

from pydantic import BaseModel


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""
    engine: str = ""
    """Which upstream engine SearXNG got this from - useful when results look odd."""


class ResearchStep(BaseModel):
    round: int
    query: str
    results: list[SearchResult] = []
    reason: str = ""
    """Why this query was run: the opening question, or the gap a later round was chasing."""


class ResearchReport(BaseModel):
    question: str
    steps: list[ResearchStep] = []
    results: list[SearchResult] = []
    """Deduplicated by URL, in the order they will be injected."""
    detail: str = ""


class SearchStatus(BaseModel):
    configured: bool
    reachable: bool
    base_url: str
    detail: str
