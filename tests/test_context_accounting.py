"""Context assembler token accounting (rule 0.7).

The expensive silent bug here is a total that disagrees with what the model actually receives:
the prompt overflows, the backend truncates from the front, and the conversation loses its
beginning without anyone being told. These tests pin the total to the real prompt.
"""

from __future__ import annotations

from server.context.assembler import RESERVED_TEMPLATE_TOKENS, assemble, to_prompt_messages
from server.db.repo.blocks import BlockPref
from server.ids import now_ms
from server.models.conversation import Conversation
from server.models.message import Message, Role
from tests.conftest import MODEL_ID, FakeProvider


def conversation(system_prompt: str = "") -> Conversation:
    ts = now_ms()
    return Conversation(id="c1", system_prompt=system_prompt, created_at=ts, updated_at=ts)


def turn(mid: str, role: Role, content: str, parent: str | None, ts: int) -> Message:
    return Message(
        id=mid, conversation_id="c1", parent_id=parent, role=role, content=content, created_at=ts
    )


def path(*pairs: tuple[str, str]) -> list[Message]:
    out: list[Message] = []
    parent: str | None = None
    for index, (role, content) in enumerate(pairs):
        mid = f"m{index}"
        out.append(turn(mid, role, content, parent, index + 1))  # type: ignore[arg-type]
        parent = mid
    return out


async def test_total_matches_the_sum_of_included_blocks() -> None:
    provider = FakeProvider()
    assembly = await assemble(
        conversation=conversation("you are terse"),
        path=path(("user", "one two three"), ("assistant", "four five")),
        provider=provider,
        model_id=MODEL_ID,
        ctx_len=4096,
        max_gen_tokens=256,
    )
    assert assembly.total_tokens == sum(b.token_count for b in assembly.blocks if b.included)
    assert assembly.estimated is False


async def test_counts_come_from_the_backends_own_tokenizer() -> None:
    """Every history block carries its own text plus the template overhead we reserve for it."""
    provider = FakeProvider()
    assembly = await assemble(
        conversation=conversation(),
        path=path(("user", "one two three")),
        provider=provider,
        model_id=MODEL_ID,
        ctx_len=4096,
        max_gen_tokens=64,
    )
    block = assembly.blocks[0]
    assert block.token_count == 3 + RESERVED_TEMPLATE_TOKENS


async def test_missing_tokenizer_is_labelled_not_hidden() -> None:
    provider = FakeProvider()

    async def no_tokenizer(text: str, model_id: str) -> int | None:
        return None

    provider.count_tokens = no_tokenizer  # type: ignore[assignment]
    assembly = await assemble(
        conversation=conversation(),
        path=path(("user", "a b c")),
        provider=provider,
        model_id=MODEL_ID,
        ctx_len=4096,
        max_gen_tokens=64,
    )
    assert assembly.estimated is True, "an approximate count must never look exact"


async def test_eviction_is_reported_for_every_dropped_block() -> None:
    turns = tuple(("user", f"word{i} filler filler filler") for i in range(30))
    assembly = await assemble(
        conversation=conversation(),
        path=path(*turns),  # type: ignore[arg-type]
        provider=FakeProvider(),
        model_id=MODEL_ID,
        ctx_len=100,
        max_gen_tokens=20,
    )
    dropped = [b for b in assembly.blocks if not b.included]
    assert dropped, "this context cannot fit; something must have been evicted"
    assert len(assembly.evictions) == len(dropped)
    assert {n.block_id for n in assembly.evictions} == {b.id for b in dropped}
    assert all(b.eviction == "budget" for b in dropped)


async def test_eviction_brings_the_total_under_budget() -> None:
    turns = tuple(("user", f"word{i} filler filler filler") for i in range(30))
    assembly = await assemble(
        conversation=conversation(),
        path=path(*turns),  # type: ignore[arg-type]
        provider=FakeProvider(),
        model_id=MODEL_ID,
        ctx_len=100,
        max_gen_tokens=20,
    )
    assert assembly.total_tokens <= assembly.ctx_len - assembly.max_gen_tokens


async def test_the_system_prompt_and_latest_turn_survive_eviction() -> None:
    """Forgetting the question you just asked is the failure this project exists to prevent."""
    turns = tuple(("user", f"word{i} filler filler filler") for i in range(30))
    assembly = await assemble(
        conversation=conversation("never drop me"),
        path=path(*turns),  # type: ignore[arg-type]
        provider=FakeProvider(),
        model_id=MODEL_ID,
        ctx_len=100,
        max_gen_tokens=20,
    )
    system = next(b for b in assembly.blocks if b.kind == "system")
    history = [b for b in assembly.blocks if b.kind == "history"]
    assert system.included and system.pinned
    assert history[-1].included, "the most recent turn is never evicted"


async def test_prompt_contains_exactly_the_included_blocks() -> None:
    """The bridge between accounting and reality: what we counted is what we send."""
    turns = tuple(("user", f"word{i} filler filler filler") for i in range(30))
    messages = path(*turns)  # type: ignore[arg-type]
    assembly = await assemble(
        conversation=conversation("sys"),
        path=messages,
        provider=FakeProvider(),
        model_id=MODEL_ID,
        ctx_len=100,
        max_gen_tokens=20,
    )
    prompt = to_prompt_messages(assembly, messages)
    included = [b for b in assembly.blocks if b.included]
    assert len(prompt) == len(included)
    assert [p.content for p in prompt] == [b.content for b in included]
    assert all(
        b.content not in [p.content for p in prompt] for b in assembly.blocks if not b.included
    )


async def test_roles_survive_the_round_trip() -> None:
    messages = path(("user", "hi"), ("assistant", "hello"), ("user", "again"))
    assembly = await assemble(
        conversation=conversation("sys"),
        path=messages,
        provider=FakeProvider(),
        model_id=MODEL_ID,
        ctx_len=4096,
        max_gen_tokens=64,
    )
    prompt = to_prompt_messages(assembly, messages)
    assert [p.role for p in prompt] == ["system", "user", "assistant", "user"]


# --- block preferences: pinning, disabling and reordering (BRIEF.md 4.2) ---


async def test_disabling_a_block_removes_it_and_says_so() -> None:
    messages = path(("user", "keep this"), ("assistant", "drop this"), ("user", "and this"))
    assembly = await assemble(
        conversation=conversation(),
        path=messages,
        provider=FakeProvider(),
        model_id=MODEL_ID,
        ctx_len=4096,
        max_gen_tokens=64,
        prefs={"m1": BlockPref(source_ref="m1", disabled=True)},
    )
    dropped = [b for b in assembly.blocks if not b.included]
    assert [b.source_ref for b in dropped] == ["m1"]
    assert [n.reason for n in assembly.evictions] == ["user_disabled"]
    assert "drop this" not in [p.content for p in to_prompt_messages(assembly, messages)]


async def test_a_pinned_block_survives_a_budget_that_would_evict_it() -> None:
    turns = tuple(("user", f"word{i} filler filler filler") for i in range(30))
    messages = path(*turns)  # type: ignore[arg-type]
    assembly = await assemble(
        conversation=conversation(),
        path=messages,
        provider=FakeProvider(),
        model_id=MODEL_ID,
        ctx_len=100,
        max_gen_tokens=20,
        prefs={"m0": BlockPref(source_ref="m0", pinned=True)},
    )
    first = next(b for b in assembly.blocks if b.source_ref == "m0")
    assert first.included, "the oldest turn is normally evicted first; pinning must protect it"
    assert assembly.total_tokens <= assembly.ctx_len - assembly.max_gen_tokens


async def test_reordering_changes_the_prompt_order_not_the_total() -> None:
    messages = path(("user", "one"), ("assistant", "two"), ("user", "three"))
    plain = await assemble(
        conversation=conversation(),
        path=messages,
        provider=FakeProvider(),
        model_id=MODEL_ID,
        ctx_len=4096,
        max_gen_tokens=64,
    )
    moved = await assemble(
        conversation=conversation(),
        path=messages,
        provider=FakeProvider(),
        model_id=MODEL_ID,
        ctx_len=4096,
        max_gen_tokens=64,
        prefs={"m2": BlockPref(source_ref="m2", ord=-1)},
    )
    assert moved.total_tokens == plain.total_tokens
    assert [b.source_ref for b in moved.blocks][0] == "m2"
