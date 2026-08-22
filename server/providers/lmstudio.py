"""LM Studio. Autodetected on its default port; OpenAI-compatible including logprobs."""

from __future__ import annotations

from server.models.provider import ProviderKind
from server.providers.openai_compat import OpenAICompatProvider


class LMStudioProvider(OpenAICompatProvider):
    kind: ProviderKind = "lmstudio"

    def __init__(self, base_url: str = "http://127.0.0.1:1234", timeout: float = 600.0) -> None:
        super().__init__(base_url, name="lm studio", kind="lmstudio", timeout=timeout)
