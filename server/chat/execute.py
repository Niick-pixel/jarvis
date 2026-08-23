"""The generation loop: provider tokens in, database rows and published events out."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from server.chat.live import LiveRun, LiveRuns
from server.chat.run import PreparedRun
from server.db import repo
from server.db.connection import Database
from server.errors import ErrorBody, ErrorCode
from server.models.message import MessageStatus
from server.models.stream import (
    DoneEvent,
    ErrorEvent,
    StopReason,
    TokenEvent,
    UsageEvent,
)
from server.providers.base import ProviderError, StreamItem, Usage


async def execute(db: Database, live: LiveRuns, prepared: PreparedRun) -> None:
    """Run to completion. Never raises: failures are published as an error event and recorded."""
    run = live.get(prepared.run_id)
    if run is None:
        return
    index = 0
    # Offsets are into the message's content, which already holds the prefix when continuing.
    byte_offset = len((prepared.assistant_prefix or "").encode())
    usage = Usage()
    stop_reason: StopReason = "eos"
    error: ErrorEvent | None = None

    with db.session() as conn:
        try:
            stream = prepared.provider.stream(
                prepared.prompt,
                prepared.params,
                model_id=prepared.model.id,
                ctx_len=prepared.ctx_len,
                assistant_prefix=prepared.assistant_prefix,
            )
            async for item in _with_cancellation(stream, run):
                if isinstance(item, Usage):
                    usage = item
                    stop_reason = _as_stop_reason(item.stop_reason)
                    continue
                repo.messages.append_content(conn, prepared.message_id, item.text)
                repo.runs.append_token(
                    conn,
                    prepared.run_id,
                    idx=index,
                    text=item.text,
                    byte_start=byte_offset,
                    logprob=item.logprob,
                    top=item.top_alternatives,
                    timing_ms=item.timing_ms,
                )
                event = TokenEvent(
                    i=index,
                    text=item.text,
                    logprob=item.logprob,
                    top=item.top_alternatives,
                    t_ms=item.timing_ms,
                )
                run.last_index = index
                run.publish(event)
                index += 1
                byte_offset += len(item.text.encode())
        except ProviderError as exc:
            stop_reason = "error"
            error = ErrorEvent(
                error=_error_body("provider_unavailable", str(exc)),
            )
        except Exception as exc:  # noqa: BLE001 - a crash must still leave a consistent row
            stop_reason = "error"
            error = ErrorEvent(error=_error_body("internal", f"{type(exc).__name__}: {exc}"))

        if run.cancelled.is_set():
            stop_reason = run.stop_reason

        gen_tokens = usage.gen_tokens or index
        repo.messages.finish(
            conn,
            prepared.message_id,
            status="error" if stop_reason == "error" else _message_status(stop_reason),
            token_count=gen_tokens,
        )
        repo.runs.finish(
            conn,
            prepared.run_id,
            stop_reason=stop_reason,
            prompt_tokens=usage.prompt_tokens or prepared.assembly.total_tokens,
            gen_tokens=gen_tokens,
            prompt_eval_ms=usage.prompt_eval_ms,
            gen_ms=usage.gen_ms,
        )
        repo.runs.bump_counter(conn, "tokens_generated", gen_tokens)
        repo.runs.bump_counter(conn, "runs_completed", 1)

    if error is not None:
        run.publish(error)
    else:
        run.publish(
            UsageEvent(
                prompt_tokens=usage.prompt_tokens or prepared.assembly.total_tokens,
                gen_tokens=gen_tokens,
                prompt_eval_ms=usage.prompt_eval_ms,
                gen_ms=usage.gen_ms,
                tps=(gen_tokens / (usage.gen_ms / 1000)) if usage.gen_ms else 0.0,
            )
        )
    run.publish(DoneEvent(stop_reason=stop_reason, message_id=prepared.message_id))
    live.finish(prepared.run_id)


async def _with_cancellation(
    stream: AsyncIterator[StreamItem], run: LiveRun
) -> AsyncIterator[StreamItem]:
    """Yield until the stream ends or the run is cancelled, whichever comes first.

    Racing the cancel event against each `__anext__` is what makes Esc feel instant instead of
    waiting for the next token to arrive from the backend.
    """
    iterator = stream.__aiter__()
    waiter = asyncio.ensure_future(run.cancelled.wait())
    try:
        while True:
            step = asyncio.ensure_future(iterator.__anext__())
            done, _ = await asyncio.wait({step, waiter}, return_when=asyncio.FIRST_COMPLETED)
            if waiter in done:
                step.cancel()
                return
            try:
                yield step.result()
            except StopAsyncIteration:
                return
    finally:
        waiter.cancel()
        if closer := getattr(iterator, "aclose", None):
            await closer()


def _message_status(stop_reason: StopReason) -> MessageStatus:
    return "stopped" if stop_reason in ("user_stop", "nudge") else "complete"


def _as_stop_reason(raw: str) -> StopReason:
    known: tuple[StopReason, ...] = ("eos", "length", "user_stop", "nudge", "error")
    return raw if raw in known else "eos"  # type: ignore[return-value]


def _error_body(code: ErrorCode, message: str) -> ErrorBody:
    return ErrorBody(code=code, message=message)
