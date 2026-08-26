"""Asking several models the same question at once - as far as the hardware allows.

On an 8-12GB card three local models do not fit side by side, so local members are gated to one at
a time by a semaphore while remote endpoints run freely. The UI shows which mode is in play; the
alternative - pretending to fan out and then thrashing or OOMing - is worse than a visible queue.
"""

from __future__ import annotations

import asyncio
import string
import time
from collections.abc import AsyncIterator

from server.models.council import (
    AnswerDoneEvent,
    AnswerStartEvent,
    AnswerTokenEvent,
    CouncilAnswer,
    CouncilEvent,
    CouncilMember,
    CouncilMode,
)
from server.models.params import SamplingParams
from server.models.provider import ModelInfo
from server.providers.base import PromptMessage, Token, Usage
from server.providers.registry import ProviderRegistry

REMOTE_KINDS = {"openai", "vllm"}
BASE_SEED = 1000


def plan(
    available: list[ModelInfo], requested: list[str]
) -> tuple[list[CouncilMember], CouncilMode, str]:
    """Assign blind labels, and decide how much can actually run at once."""
    by_id = {m.id: m for m in available}
    chosen = [by_id[i] for i in requested if i in by_id] or available

    members = [
        CouncilMember(
            label=string.ascii_uppercase[index],
            model_id=model.id,
            seed=BASE_SEED + index,
        )
        for index, model in enumerate(chosen[: len(string.ascii_uppercase)])
    ]
    local = [m for m in members if by_id[m.model_id].provider not in REMOTE_KINDS]
    remote = [m for m in members if by_id[m.model_id].provider in REMOTE_KINDS]

    if remote and local:
        mode: CouncilMode = "mixed"
        detail = (
            f"{len(local)} local model{'s' if len(local) != 1 else ''} run one at a time - they "
            f"share one card - while {len(remote)} remote one{'s' if len(remote) != 1 else ''} run "
            "alongside."
        )
    elif remote:
        mode = "mixed"
        detail = f"{len(remote)} remote models, running concurrently. No local VRAM is used."
    else:
        mode = "sequential"
        detail = (
            f"{len(local)} local models, queued one at a time. Three 8B models do not fit in "
            "this card at once, so the Council takes turns rather than thrashing."
        )
    return members, mode, detail


async def _run_member(
    registry: ProviderRegistry,
    member: CouncilMember,
    question: str,
    queue: asyncio.Queue[CouncilEvent | None],
    gate: asyncio.Semaphore | None,
) -> CouncilAnswer:
    answer = CouncilAnswer(label=member.label, model_id=member.model_id)
    started = time.perf_counter()
    try:
        provider, model = await registry.resolve(member.model_id)
    except Exception as exc:  # noqa: BLE001 - one member failing must not sink the council
        answer.error = f"{type(exc).__name__}: {exc}"
        await queue.put(AnswerDoneEvent(answer=answer))
        return answer

    async with _maybe(gate):
        await queue.put(AnswerStartEvent(label=member.label, model_id=member.model_id))
        params = SamplingParams(seed=member.seed or 0, temperature=0.7, max_tokens=512, n_probs=0)
        try:
            async for item in provider.stream(
                [PromptMessage(role="user", content=question)],
                params,
                model_id=model.id,
                ctx_len=min(model.ctx_len_max or 4096, 8192),
            ):
                if isinstance(item, Token):
                    answer.content += item.text
                    await queue.put(AnswerTokenEvent(label=member.label, text=item.text))
                elif isinstance(item, Usage):
                    answer.gen_tokens = item.gen_tokens
        except Exception as exc:  # noqa: BLE001
            answer.error = f"{type(exc).__name__}: {exc}"

    answer.gen_ms = int((time.perf_counter() - started) * 1000)
    await queue.put(AnswerDoneEvent(answer=answer))
    return answer


class _maybe:
    """`async with` a semaphore that may be None."""

    def __init__(self, gate: asyncio.Semaphore | None) -> None:
        self._gate = gate

    async def __aenter__(self) -> None:
        if self._gate is not None:
            await self._gate.acquire()

    async def __aexit__(self, *_: object) -> None:
        if self._gate is not None:
            self._gate.release()


async def fanout(
    registry: ProviderRegistry,
    members: list[CouncilMember],
    question: str,
    available: list[ModelInfo],
) -> AsyncIterator[CouncilEvent | list[CouncilAnswer]]:
    """Stream every member's tokens as they arrive; finish by yielding the collected answers."""
    by_id = {m.id: m for m in available}
    gate = asyncio.Semaphore(1)
    queue: asyncio.Queue[CouncilEvent | None] = asyncio.Queue()

    tasks = [
        asyncio.create_task(
            _run_member(
                registry,
                member,
                question,
                queue,
                None
                if by_id.get(member.model_id) and by_id[member.model_id].provider in REMOTE_KINDS
                else gate,
            )
        )
        for member in members
    ]

    async def close() -> None:
        await asyncio.gather(*tasks, return_exceptions=True)
        await queue.put(None)

    closer = asyncio.create_task(close())
    while True:
        event = await queue.get()
        if event is None:
            break
        yield event

    await closer
    yield [task.result() for task in tasks if not task.cancelled() and task.exception() is None]
