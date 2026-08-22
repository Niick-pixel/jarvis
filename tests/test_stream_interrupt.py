"""Streaming interrupt and resume (rule 0.7).

This path is where losing work is silent and expensive: a stop that discards 900 tokens, a
reconnect that replays a token twice or skips one, a backend that dies and leaves a message row
stuck in `streaming` forever.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from tests.conftest import FakeProvider

from server.chat import sse
from server.chat.execute import execute
from server.chat.live import LiveRuns
from server.chat.run import prepare
from server.db import repo
from server.db.connection import Database
from server.models.conversation import ConversationCreate
from server.models.stream import ChatRequest
from server.providers.registry import ProviderRegistry
from server.settings import Settings

SCRIPT = [f"t{i} " for i in range(10)]


async def start_run(
    db: Database, registry: ProviderRegistry, settings: Settings, live: LiveRuns
) -> tuple[Any, asyncio.Task[None]]:
    with db.session() as conn:
        conversation = repo.conversations.create(conn, ConversationCreate(title="t"))
    prepared = await prepare(
        db, registry, settings, ChatRequest(conversation_id=conversation.id, content="hi")
    )
    live.start(prepared.run_id, prepared.message_id, prepared.conversation_id)
    task = asyncio.create_task(execute(db, live, prepared))
    return prepared, task


async def wait_for_tokens(db: Database, run_id: str, count: int, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        with db.session() as conn:
            if repo.runs.token_count(conn, run_id) >= count:
                return
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} never reached {count} tokens")


def token_indices(payloads: list[dict[str, Any]]) -> list[int]:
    return [json.loads(p["data"])["i"] for p in payloads if p["event"] == "token"]


async def test_stop_keeps_the_partial_answer(db: Database, settings: Settings) -> None:
    provider = FakeProvider(SCRIPT, delay_s=0.02)
    live = LiveRuns()
    prepared, task = await start_run(db, ProviderRegistry([provider]), settings, live)

    await wait_for_tokens(db, prepared.run_id, 3)
    assert live.stop(prepared.run_id) is True
    await asyncio.wait_for(task, timeout=5)

    with db.session() as conn:
        message = repo.messages.get(conn, prepared.message_id)
        written = repo.runs.token_count(conn, prepared.run_id)
        run = conn.execute(
            "SELECT stop_reason, gen_tokens FROM runs WHERE id = ?", (prepared.run_id,)
        ).fetchone()

    assert message is not None
    assert message.status == "stopped"
    assert message.content == "".join(SCRIPT[:written]), "the partial must be kept verbatim"
    assert 0 < written < len(SCRIPT), "stop should land mid-generation"
    assert run["stop_reason"] == "user_stop"
    assert run["gen_tokens"] == written


async def test_stop_does_not_wait_for_the_next_token(db: Database, settings: Settings) -> None:
    """Esc must feel instant even when the backend is slow between tokens."""
    provider = FakeProvider(SCRIPT, delay_s=1.5)
    live = LiveRuns()
    prepared, task = await start_run(db, ProviderRegistry([provider]), settings, live)
    await provider.started.wait()

    started = asyncio.get_running_loop().time()
    live.stop(prepared.run_id)
    await asyncio.wait_for(task, timeout=5)
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 1.0, f"cancellation waited {elapsed:.2f}s for the in-flight token"


async def test_finished_run_replays_exactly_the_missing_tokens(
    db: Database, settings: Settings
) -> None:
    live = LiveRuns()
    prepared, task = await start_run(db, ProviderRegistry([FakeProvider(SCRIPT)]), settings, live)
    await asyncio.wait_for(task, timeout=5)

    payloads = [
        p async for p in sse.stream_resume(db, live, prepared.run_id, f"{prepared.run_id}:4")
    ]
    assert token_indices(payloads) == [5, 6, 7, 8, 9], "no duplicates, no gaps"
    assert payloads[-1]["event"] == "done"
    assert payloads[0]["event"] == "assembly", "a reconnect still learns what was in context"


async def test_resume_from_scratch_replays_the_whole_answer(
    db: Database, settings: Settings
) -> None:
    live = LiveRuns()
    prepared, task = await start_run(db, ProviderRegistry([FakeProvider(SCRIPT)]), settings, live)
    await asyncio.wait_for(task, timeout=5)

    payloads = [p async for p in sse.stream_resume(db, live, prepared.run_id, None)]
    assert token_indices(payloads) == list(range(len(SCRIPT)))


async def test_reconnect_midflight_has_no_gap_and_no_duplicate(
    db: Database, settings: Settings
) -> None:
    """The race this guards: a token produced between the replay query and the subscription."""
    provider = FakeProvider(SCRIPT, delay_s=0.02)
    live = LiveRuns()
    prepared, task = await start_run(db, ProviderRegistry([provider]), settings, live)

    await wait_for_tokens(db, prepared.run_id, 3)
    payloads = [p async for p in sse.stream_resume(db, live, prepared.run_id, None)]
    await asyncio.wait_for(task, timeout=5)

    indices = token_indices(payloads)
    assert indices == list(range(len(SCRIPT))), f"expected a clean 0..9, got {indices}"
    assert payloads[-1]["event"] == "done"


async def test_a_dropped_client_does_not_kill_the_generation(
    db: Database, settings: Settings
) -> None:
    """Closing the browser must not cost you the answer."""
    provider = FakeProvider(SCRIPT, delay_s=0.02)
    live = LiveRuns()
    prepared, task = await start_run(db, ProviderRegistry([provider]), settings, live)

    subscription = live.subscribe(prepared.run_id)
    assert subscription is not None
    _, queue = subscription
    await wait_for_tokens(db, prepared.run_id, 2)
    live.unsubscribe(prepared.run_id, queue)

    await asyncio.wait_for(task, timeout=5)
    with db.session() as conn:
        message = repo.messages.get(conn, prepared.message_id)
    assert message is not None
    assert message.status == "complete"
    assert message.content == "".join(SCRIPT)


async def test_provider_failure_leaves_a_consistent_row(db: Database, settings: Settings) -> None:
    provider = FakeProvider(SCRIPT, fail_at=4)
    live = LiveRuns()
    prepared, task = await start_run(db, ProviderRegistry([provider]), settings, live)
    await asyncio.wait_for(task, timeout=5)

    with db.session() as conn:
        message = repo.messages.get(conn, prepared.message_id)
        run = conn.execute(
            "SELECT stop_reason FROM runs WHERE id = ?", (prepared.run_id,)
        ).fetchone()

    assert message is not None
    assert message.status == "error", "a dead backend must not leave a row stuck in 'streaming'"
    assert message.content == "".join(SCRIPT[:4]), "whatever arrived before the failure is kept"
    assert run["stop_reason"] == "error"


async def test_error_is_published_to_attached_clients(db: Database, settings: Settings) -> None:
    provider = FakeProvider(SCRIPT, delay_s=0.01, fail_at=2)
    live = LiveRuns()
    with db.session() as conn:
        conversation = repo.conversations.create(conn, ConversationCreate(title="t"))
    prepared = await prepare(
        db,
        ProviderRegistry([provider]),
        settings,
        ChatRequest(conversation_id=conversation.id, content="hi"),
    )
    live.start(prepared.run_id, prepared.message_id, prepared.conversation_id)
    subscription = live.subscribe(prepared.run_id)
    assert subscription is not None
    _, queue = subscription
    task = asyncio.create_task(execute(db, live, prepared))

    payloads = [p async for p in sse._drain(queue, prepared.run_id)]
    await asyncio.wait_for(task, timeout=5)
    assert [p["event"] for p in payloads][-2:] == ["error", "done"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("run_abc:41", 41), ("run_abc:0", 0), (None, -1), ("garbage", -1), ("run_abc:x", -1)],
)
def test_last_event_id_parsing(raw: str | None, expected: int) -> None:
    assert sse.parse_last_event_id(raw) == expected
