"""Steering the model mid-flight, and reproducing it afterwards.

The same rule 0.7 subject as test_stream_interrupt.py - the streaming interrupt/resume path - split
out because forcing a token, nudging and replaying are a different responsibility from stopping and
reconnecting, and one file covering both outgrew what anyone wants to read.
"""

from __future__ import annotations

import asyncio
from typing import Any

from server.chat.execute import execute
from server.chat.live import LiveRuns
from server.chat.run import prepare
from server.db import repo
from server.db.connection import Database
from server.models.conversation import ConversationCreate
from server.models.params import SamplingParams
from server.models.stream import ChatRequest
from server.providers.registry import ProviderRegistry
from server.settings import Settings
from tests.conftest import FakeProvider
from tests.test_stream_interrupt import SCRIPT, start_run, wait_for_tokens


async def run_to_completion(
    db: Database, registry: ProviderRegistry, settings: Settings, live: LiveRuns, **overrides: Any
) -> Any:
    with db.session() as conn:
        conversation = repo.conversations.create(conn, ConversationCreate(title="t"))
    prepared = await prepare(
        db,
        registry,
        settings,
        ChatRequest(conversation_id=conversation.id, content="hi", **overrides),
    )
    live.start(prepared.run_id, prepared.message_id, prepared.conversation_id)
    await execute(db, live, prepared)
    return prepared


async def test_forced_token_truncates_at_the_right_place(db: Database, settings: Settings) -> None:
    """Click a token, pick another, and the message restarts from exactly that byte offset."""
    live = LiveRuns()
    registry = ProviderRegistry([FakeProvider(SCRIPT)])
    first = await run_to_completion(db, registry, settings, live)

    with db.session() as conn:
        conversation_id = repo.messages.get(conn, first.message_id).conversation_id  # type: ignore[union-attr]
    steered = await prepare(
        db,
        registry,
        settings,
        ChatRequest(
            conversation_id=conversation_id,
            force_token={"message_id": first.message_id, "token_idx": 3, "token": "DIFFERENT"},
        ),
    )

    # SCRIPT is ["t0 ", "t1 ", ...]; truncating before index 3 keeps the first three tokens.
    assert steered.assistant_prefix == "".join(SCRIPT[:3]) + "DIFFERENT"
    with db.session() as conn:
        created = repo.messages.get(conn, steered.message_id)
    assert created is not None
    assert created.forked_reason == "forced_token"
    assert created.edited_from_id == first.message_id
    assert created.content == steered.assistant_prefix, "the prefix is already on disk"


async def test_the_original_survives_being_steered(db: Database, settings: Settings) -> None:
    live = LiveRuns()
    registry = ProviderRegistry([FakeProvider(SCRIPT)])
    first = await run_to_completion(db, registry, settings, live)
    with db.session() as conn:
        before = repo.messages.get(conn, first.message_id)
        conversation_id = before.conversation_id  # type: ignore[union-attr]
    await prepare(
        db,
        registry,
        settings,
        ChatRequest(
            conversation_id=conversation_id,
            force_token={"message_id": first.message_id, "token_idx": 2, "token": "X"},
        ),
    )
    with db.session() as conn:
        after = repo.messages.get(conn, first.message_id)
    assert after is not None and before is not None
    assert after.content == before.content, "steering forks; it never rewrites the original"


async def test_rerun_with_the_same_seed_reproduces_the_answer(
    db: Database, settings: Settings
) -> None:
    """The point of recording seed and params: replay is exact, so a diff means something."""
    live = LiveRuns()
    registry = ProviderRegistry([FakeProvider(SCRIPT, vary_by_seed=True)])
    first = await run_to_completion(db, registry, settings, live)
    with db.session() as conn:
        original = repo.messages.get(conn, first.message_id)
    assert original is not None

    replay = await prepare(
        db,
        registry,
        settings,
        ChatRequest(conversation_id=original.conversation_id, rerun_of=original.id),
    )
    live.start(replay.run_id, replay.message_id, replay.conversation_id)
    await execute(db, live, replay)

    with db.session() as conn:
        replayed = repo.messages.get(conn, replay.message_id)
    assert replayed is not None
    assert replay.params.seed == first.params.seed, "replay must reuse the recorded seed"
    assert replayed.content == original.content, "same seed, same output"
    assert replayed.forked_reason == "rerun"
    assert replayed.parent_id == original.parent_id, "a replay is a sibling, not a child"


async def test_rerun_with_a_different_seed_diverges(db: Database, settings: Settings) -> None:
    """Guards the test above: if output ignored the seed, equality would prove nothing."""
    live = LiveRuns()
    registry = ProviderRegistry([FakeProvider(SCRIPT, vary_by_seed=True)])
    first = await run_to_completion(db, registry, settings, live)
    with db.session() as conn:
        original = repo.messages.get(conn, first.message_id)
    assert original is not None

    replay = await prepare(
        db,
        registry,
        settings,
        ChatRequest(
            conversation_id=original.conversation_id,
            rerun_of=original.id,
            params=SamplingParams(seed=first.params.seed + 1),
        ),
    )
    live.start(replay.run_id, replay.message_id, replay.conversation_id)
    await execute(db, live, replay)
    with db.session() as conn:
        replayed = repo.messages.get(conn, replay.message_id)
    assert replayed is not None and replayed.content != original.content


async def test_a_nudge_lands_as_a_context_block_and_keeps_the_partial(
    db: Database, settings: Settings
) -> None:
    """A nudge changes what the model was told, so it must be visible in the block list."""
    live = LiveRuns()
    registry = ProviderRegistry([FakeProvider(SCRIPT, delay_s=0.02)])
    prepared, task = await start_run(db, registry, settings, live)
    await wait_for_tokens(db, prepared.run_id, 3)
    live.stop(prepared.run_id, "nudge")
    await asyncio.wait_for(task, timeout=5)

    with db.session() as conn:
        partial = repo.messages.get(conn, prepared.message_id)
    assert partial is not None and partial.status == "stopped"

    continued = await prepare(
        db,
        registry,
        settings,
        ChatRequest(
            conversation_id=partial.conversation_id,
            continue_from=partial.id,
            nudge="Be much more concise.",
        ),
    )
    kinds = [b.kind for b in continued.assembly.blocks]
    assert "nudge" in kinds, "the interjection must appear in the context inspector"
    assert "prefix" in kinds, "so must the partial it resumes from"
    assert continued.assistant_prefix == partial.content
    with db.session() as conn:
        created = repo.messages.get(conn, continued.message_id)
    assert created is not None and created.forked_reason == "nudge"
