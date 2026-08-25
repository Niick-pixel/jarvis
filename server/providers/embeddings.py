"""Embeddings, reached through the same provider the chat model comes from.

Two wire shapes exist in the wild: the OpenAI `/v1/embeddings` body, and llama.cpp's older
`/embedding`. Both are tried, in that order, and which one answered is remembered so the next call
does not pay for the discovery again.
"""

from __future__ import annotations

import httpx

from server.providers.base import ModelProvider, ProviderError

BATCH = 16


class EmbeddingClient:
    def __init__(self, provider: ModelProvider, model_id: str, timeout: float = 120.0) -> None:
        self.provider = provider
        self.model_name = model_id.split(":", 1)[-1]
        self._timeout = timeout
        self._shape: str | None = None

    def _client(self) -> httpx.AsyncClient:
        key = getattr(self.provider, "api_key", "")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        return httpx.AsyncClient(
            base_url=self.provider.base_url, timeout=self._timeout, headers=headers
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        async with self._client() as client:
            for start in range(0, len(texts), BATCH):
                batch = texts[start : start + BATCH]
                vectors.extend(await self._embed_batch(client, batch))
        return vectors

    async def _embed_batch(self, client: httpx.AsyncClient, batch: list[str]) -> list[list[float]]:
        if self._shape in (None, "openai"):
            try:
                response = await client.post(
                    "/v1/embeddings", json={"model": self.model_name, "input": batch}
                )
                if response.status_code == 200:
                    self._shape = "openai"
                    return [row["embedding"] for row in response.json()["data"]]
            except (httpx.HTTPError, KeyError, TypeError):
                pass

        try:
            response = await client.post("/embedding", json={"content": batch})
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"embedding request failed: {exc}") from exc

        self._shape = "llamacpp"
        return _llamacpp_vectors(payload, len(batch))

    async def dimension(self) -> int:
        vectors = await self.embed(["dimension probe"])
        if not vectors or not vectors[0]:
            raise ProviderError("the embedding backend returned an empty vector")
        return len(vectors[0])


def _llamacpp_vectors(payload: object, expected: int) -> list[list[float]]:
    """llama.cpp has returned this as a dict, a list of dicts, and a nested list across versions."""
    if isinstance(payload, dict):
        payload = payload.get("data", payload.get("embedding", []))
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return [row.get("embedding", row.get("data", [])) for row in payload]
    if isinstance(payload, list) and payload and isinstance(payload[0], list):
        return [list(map(float, row)) for row in payload]
    if isinstance(payload, list) and expected == 1:
        return [list(map(float, payload))]
    raise ProviderError("could not read embeddings from the backend's response")
