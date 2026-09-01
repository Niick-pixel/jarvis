"""Reranking: a cross-encoder reading the question and one chunk together, and scoring the pair.

Retrieval fuses two rankings that never saw each other's results; a reranker is the first thing in
the pipeline that reads the question and the passage at the same time, which is why it fixes the
"right file, wrong paragraph" case that RRF cannot.

It is a separate llama.cpp server on loopback started with `--reranking`, not a Python dependency:
a cross-encoder is a model, and this project already knows how to talk to a model over a port.
Two paths are tried - `/v1/rerank` and llama.cpp's `/rerank` - and whichever answers is remembered.
"""

from __future__ import annotations

import httpx

from server.providers.base import ProviderError

PATHS = ("/v1/rerank", "/rerank")


class RerankClient:
    def __init__(self, base_url: str, model_id: str, timeout: float = 20.0) -> None:
        self.base_url = base_url
        self.model_name = model_id.split(":", 1)[-1]
        self._timeout = timeout
        self._path: str | None = None

    async def scores(self, query: str, documents: list[str]) -> list[float]:
        """One score per document, in the order given. Raises rather than guessing on failure."""
        if not documents:
            return []
        body = {"model": self.model_name, "query": query, "documents": documents}
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self._timeout) as client:
            for path in [self._path] if self._path else PATHS:
                assert path is not None
                try:
                    response = await client.post(path, json=body)
                except httpx.HTTPError as exc:
                    raise ProviderError(f"reranker unreachable: {exc}") from exc
                if response.status_code == 404:
                    continue
                if response.status_code != 200:
                    raise ProviderError(f"reranker returned {response.status_code}")
                self._path = path
                return _read_scores(response.json(), len(documents))
        raise ProviderError(f"no rerank endpoint at {self.base_url} (tried {', '.join(PATHS)})")

    async def reachable(self) -> tuple[bool, str]:
        """Used by the status endpoint, so "reranking is on" is a fact rather than a setting."""
        try:
            await self.scores("ping", ["a probe document"])
        except ProviderError as exc:
            return False, str(exc)
        return True, f"{self.model_name} at {self.base_url}"


def _read_scores(payload: object, expected: int) -> list[float]:
    """`relevance_score` is llama.cpp's field name; `score` is what several others emit."""
    if not isinstance(payload, dict):
        raise ProviderError("the reranker returned something that was not an object")
    results = payload.get("results")
    if not isinstance(results, list):
        raise ProviderError("the reranker's response had no results")
    scores = [0.0] * expected
    for row in results:
        if not isinstance(row, dict):
            continue
        index = row.get("index")
        value = row.get("relevance_score", row.get("score"))
        if isinstance(index, int) and 0 <= index < expected and isinstance(value, int | float):
            scores[index] = float(value)
    return scores
