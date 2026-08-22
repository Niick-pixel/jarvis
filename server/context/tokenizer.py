"""Token counting, memoised.

Counts come from the backend's own tokenizer whenever it has one. When it does not, we estimate
and the estimate is flagged all the way to the UI - a number that looks exact but is not is worse
than a number labelled approximate.
"""

from __future__ import annotations

import hashlib

from server.providers.base import ModelProvider, estimate_tokens

MAX_CACHE = 4096


class TokenCounter:
    def __init__(self, provider: ModelProvider, model_id: str) -> None:
        self._provider = provider
        self._model_id = model_id
        self._cache: dict[str, int] = {}
        self.exact = True
        """Flips to False the first time the backend cannot give us a real count."""

    async def count(self, text: str) -> int:
        if not text:
            return 0
        key = hashlib.blake2b(text.encode(), digest_size=16).hexdigest()
        if (hit := self._cache.get(key)) is not None:
            return hit
        value = await self._provider.count_tokens(text, self._model_id)
        if value is None:
            self.exact = False
            value = estimate_tokens(text)
        if len(self._cache) >= MAX_CACHE:
            self._cache.clear()
        self._cache[key] = value
        return value
