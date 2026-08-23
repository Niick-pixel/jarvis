"""A scripted provider, so the three test subjects run with no model and no GPU.

Everything the tests assert is about our own logic - the DAG, the token accounting, and the
interrupt/resume path - so a fake backend with a deterministic token script is the right
instrument. `make check` stays fast enough to run on every commit.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from server.db.connection import Database
from server.db.migrate import migrate
from server.models.params import SamplingParams
from server.models.provider import Capabilities, ModelInfo, ProviderInfo
from server.models.stream import Alternative
from server.providers.base import PromptMessage, ProviderError, StreamItem, Token, Usage
from server.providers.registry import ProviderRegistry
from server.settings import Settings, load_settings

MODEL_ID = "fake:scripted"


class FakeProvider:
    """Emits a fixed token script, optionally slowly, optionally failing part way through."""

    kind = "fake"

    def __init__(
        self,
        script: list[str] | None = None,
        *,
        delay_s: float = 0.0,
        fail_at: int | None = None,
        ctx_len_max: int = 4096,
        vary_by_seed: bool = False,
    ) -> None:
        self.name = "fake"
        self.base_url = "memory://fake"
        self.script = script or ["Hello", " there", ",", " world", "."]
        self.delay_s = delay_s
        self.fail_at = fail_at
        self.ctx_len_max = ctx_len_max
        self.vary_by_seed = vary_by_seed
        """When set, output depends on the seed - otherwise a replay test proves nothing."""
        self.started = asyncio.Event()
        self.prompts: list[list[PromptMessage]] = []
        self.prefixes: list[str | None] = []

    async def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            kind="fake",
            base_url=self.base_url,
            online=True,
            capabilities=Capabilities(logprobs=True, prefix_continuation=True, tokenize=True),
            models=[MODEL_ID],
        )

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id=MODEL_ID,
                provider="fake",
                display_name="scripted",
                ctx_len_max=self.ctx_len_max,
                supports_logprobs=True,
                supports_prefix=True,
            )
        ]

    async def count_tokens(self, text: str, model_id: str) -> int | None:
        """One token per whitespace-separated word: crude, but exact and reproducible."""
        return len(text.split())

    async def stream(
        self,
        messages: list[PromptMessage],
        params: SamplingParams,
        *,
        model_id: str,
        ctx_len: int,
        assistant_prefix: str | None = None,
    ) -> AsyncIterator[StreamItem]:
        self.prompts.append(messages)
        self.prefixes.append(assistant_prefix)
        self.started.set()
        script = list(self.script)
        if self.vary_by_seed:
            random.Random(params.seed).shuffle(script)
        for index, text in enumerate(script):
            if self.fail_at is not None and index == self.fail_at:
                raise ProviderError("scripted failure")
            if self.delay_s:
                await asyncio.sleep(self.delay_s)
            yield Token(
                text=text,
                logprob=-0.1 * (index + 1),
                top_alternatives=[
                    Alternative(token=text, logprob=-0.1 * (index + 1)),
                    Alternative(token=f"alt{index}", logprob=-2.0),
                ],
                timing_ms=float(index),
            )
        yield Usage(
            prompt_tokens=7,
            gen_tokens=len(script),
            prompt_eval_ms=10,
            gen_ms=20,
            stop_reason="eos",
        )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return load_settings(
        paths={"data_dir": str(tmp_path / "data"), "models_dir": str(tmp_path / "models")},
        providers={
            "llamacpp": {"enabled": False},
            "ollama": {"enabled": False},
            "lmstudio": {"enabled": False},
        },
    )


@pytest.fixture
def db(settings: Settings) -> Database:
    database = Database(settings.paths.db_path)
    with database.session() as conn:
        migrate(conn)
    return database


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def registry(provider: FakeProvider) -> ProviderRegistry:
    return ProviderRegistry([provider])
