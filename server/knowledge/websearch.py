"""Talking to a local SearXNG instance.

SearXNG runs as its own process, never imported: it is AGPL-3.0, and keeping it at arm's length
keeps that licence off our code. It is also the reason search is private - queries go to your
instance, which fans them out, rather than to a search API that logs you.

Only snippets are read. Fetching the pages themselves would contact each site directly and undo
the privacy the whole arrangement buys, so that is opt-in and says what it costs.
"""

from __future__ import annotations

import logging

import httpx

from server.models.search import SearchResult
from server.settings import Settings, is_loopback

log = logging.getLogger(__name__)
TIMEOUT_S = 20.0


class SearchUnavailable(RuntimeError):
    """Raised with the reason, so the UI can say why rather than showing nothing."""


def configured(settings: Settings) -> bool:
    return bool(settings.search.base_url.strip())


def _check_loopback(url: str) -> None:
    host = url.split("//", 1)[-1].split("/", 1)[0].split(":")[0]
    if not is_loopback(host):
        raise SearchUnavailable(
            f"{url} is not loopback. The point of running SearXNG yourself is that queries stay "
            "on this machine; pointing at a remote instance gives that away."
        )


async def search(settings: Settings, query: str, limit: int | None = None) -> list[SearchResult]:
    url = settings.search.base_url.strip()
    if not url:
        raise SearchUnavailable(
            "No SearXNG instance configured. Run `make searxng` to set one up locally, then set "
            "search.base_url."
        )
    _check_loopback(url)
    limit = limit or settings.search.max_results

    params = {"q": query, "format": "json", "safesearch": "0"}
    if settings.search.categories:
        params["categories"] = settings.search.categories
    try:
        async with httpx.AsyncClient(base_url=url, timeout=TIMEOUT_S) as client:
            response = await client.get("/search", params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise SearchUnavailable(f"SearXNG at {url} did not answer: {exc}") from exc
    except ValueError as exc:
        raise SearchUnavailable(
            f"SearXNG at {url} did not return JSON. Enable the json format in its settings.yml."
        ) from exc

    return _parse(payload, limit)


def _parse(payload: object, limit: int) -> list[SearchResult]:
    rows = payload.get("results", []) if isinstance(payload, dict) else []
    out: list[SearchResult] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "")
        if not url:
            continue
        out.append(
            SearchResult(
                title=str(row.get("title") or url),
                url=url,
                snippet=str(row.get("content") or "")[:600],
                engine=str(row.get("engine") or ""),
            )
        )
        if len(out) >= limit:
            break
    return out


async def reachable(settings: Settings) -> tuple[bool, str]:
    if not configured(settings):
        return False, "not configured"
    try:
        results = await search(settings, "ping", limit=1)
    except SearchUnavailable as exc:
        return False, str(exc)
    return True, f"answering ({len(results)} result for a probe query)"
