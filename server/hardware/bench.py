"""Measure what this machine actually does, so no number in the UI is copied from elsewhere."""

from __future__ import annotations

import time
from dataclasses import dataclass

from server.models.params import SamplingParams
from server.providers.base import ModelProvider, PromptMessage, Token, Usage

BENCH_PROMPT = (
    "Summarise, in one paragraph, why running a language model on your own hardware changes "
    "what you are allowed to do with it. Be specific and concrete."
)


@dataclass
class BenchResult:
    model_id: str
    prompt_tokens: int
    gen_tokens: int
    time_to_first_token_ms: float
    gen_tps: float
    prompt_tps: float

    def describe(self) -> str:
        return (
            f"{self.model_id}: {self.gen_tps:.1f} tok/s generation, "
            f"{self.prompt_tps:.0f} tok/s prompt eval, "
            f"{self.time_to_first_token_ms:.0f} ms to first token"
        )


async def bench(
    provider: ModelProvider, *, model_id: str, ctx_len: int, max_tokens: int = 128
) -> BenchResult:
    params = SamplingParams(seed=1, temperature=0.0, max_tokens=max_tokens, n_probs=0)
    messages = [PromptMessage(role="user", content=BENCH_PROMPT)]

    started = time.perf_counter()
    first_token_at: float | None = None
    generated = 0
    usage = Usage()

    async for item in provider.stream(messages, params, model_id=model_id, ctx_len=ctx_len):
        if isinstance(item, Token):
            if first_token_at is None:
                first_token_at = time.perf_counter()
            generated += 1
        else:
            usage = item

    finished = time.perf_counter()
    ttft_ms = ((first_token_at or finished) - started) * 1000
    gen_seconds = max(finished - (first_token_at or started), 1e-6)
    gen_tokens = usage.gen_tokens or generated
    prompt_tokens = usage.prompt_tokens or 0
    prompt_tps = (prompt_tokens / (usage.prompt_eval_ms / 1000)) if usage.prompt_eval_ms else 0.0

    return BenchResult(
        model_id=model_id,
        prompt_tokens=prompt_tokens,
        gen_tokens=gen_tokens,
        time_to_first_token_ms=ttft_ms,
        gen_tps=gen_tokens / gen_seconds,
        prompt_tps=prompt_tps,
    )
