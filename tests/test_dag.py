"""Conversation-DAG invariants (rule 0.7).

These are the bugs that would be silent: a fork that quietly overwrites its origin, a sibling
order that shuffles between renders, an ancestor walk that drops a turn from the prompt.
"""

from __future__ import annotations

import pytest

from server.errors import SovereignError
from server.graph import dag, merge
from server.models.message import Message


def node(mid: str, parent: str | None, created_at: int, role: str = "user") -> Message:
    return Message(
        id=mid,
        conversation_id="c1",
        parent_id=parent,
        role=role,  # type: ignore[arg-type]
        content=mid,
        created_at=created_at,
    )


@pytest.fixture
def tree() -> list[Message]:
    #   a - b - d
    #     \ c - e
    return [
        node("a", None, 1),
        node("b", "a", 2),
        node("c", "a", 3),
        node("d", "b", 4),
        node("e", "c", 5),
    ]


def test_ancestors_is_the_prompt_order(tree: list[Message]) -> None:
    assert [m.id for m in dag.ancestors(tree, "d")] == ["a", "b", "d"]
    assert [m.id for m in dag.ancestors(tree, "e")] == ["a", "c", "e"]


def test_path_to_leaf_follows_the_active_pointer(tree: list[Message]) -> None:
    assert [m.id for m in dag.path_to_leaf(tree, "b")] == ["a", "b"]


def test_path_to_leaf_without_a_pointer_takes_the_newest_branch(tree: list[Message]) -> None:
    assert [m.id for m in dag.path_to_leaf(tree, None)] == ["a", "c", "e"]


def test_path_to_leaf_ignores_a_stale_pointer(tree: list[Message]) -> None:
    """A leaf id that no longer exists must not blank the conversation."""
    assert [m.id for m in dag.path_to_leaf(tree, "deleted")] == ["a", "c", "e"]


def test_empty_conversation_has_an_empty_path() -> None:
    assert dag.path_to_leaf([], None) == []


def test_siblings_are_stable_and_ordered(tree: list[Message]) -> None:
    assert dag.siblings(tree, "b").ids == ["b", "c"]
    assert dag.siblings(tree, "c").index == 1
    shuffled = list(reversed(tree))
    assert dag.siblings(shuffled, "b").ids == ["b", "c"], "order must not depend on input order"


def test_forking_an_edit_adds_a_sibling_and_destroys_nothing(tree: list[Message]) -> None:
    """The whole point of 4.1: editing never mutates the original node."""
    forked = node("b2", "a", 6)
    forked.edited_from_id = "b"
    forked.forked_reason = "edit"
    after = [*tree, forked]

    assert {m.id for m in tree} <= {m.id for m in after}
    assert dag.siblings(after, "b").ids == ["b", "c", "b2"]
    assert [m.id for m in dag.ancestors(after, "b2")] == ["a", "b2"]
    original = next(m for m in after if m.id == "b")
    assert original.content == "b" and original.edited_from_id is None


def test_leaves_are_the_branch_tips(tree: list[Message]) -> None:
    assert sorted(m.id for m in dag.leaves(tree)) == ["d", "e"]


def test_subtree_collects_descendants(tree: list[Message]) -> None:
    assert dag.subtree_ids(tree, "a") == {"a", "b", "c", "d", "e"}
    assert dag.subtree_ids(tree, "c") == {"c", "e"}


def test_deep_chain_does_not_blow_the_stack() -> None:
    chain = [node("n0", None, 0)] + [node(f"n{i}", f"n{i - 1}", i) for i in range(1, 5000)]
    assert len(dag.ancestors(chain, "n4999")) == 5000


def test_a_cycle_raises_instead_of_hanging() -> None:
    """Unreachable through the schema; a corrupt database must fail loudly, not spin."""
    corrupt = [node("x", "y", 1), node("y", "x", 2)]
    with pytest.raises(dag.CycleError):
        dag.ancestors(corrupt, "x")


# --- merge: composing a new leaf from spans of sibling branches (BRIEF.md 4.1) ---


def sibling(mid: str, content: str, parent: str | None = "a", created_at: int = 9) -> Message:
    return Message(
        id=mid,
        conversation_id="c1",
        parent_id=parent,
        role="assistant",
        content=content,
        created_at=created_at,
    )


def test_merge_composes_from_the_sources_not_from_client_text() -> None:
    """The server slices the sources itself, so recorded provenance is true by construction."""
    left = sibling("L", "the quick brown fox")
    right = sibling("R", "jumps over the lazy dog")
    request = merge.MergeRequest(
        spans=[
            merge.MergeSpan(source_id="L", start=0, end=9),
            merge.MergeSpan(source_id="R", start=0, end=10),
        ],
        separator=" ",
    )
    result = merge.compose(request, {"L": left, "R": right})
    assert result.content == "the quick jumps over"
    assert result.parent_id == "a"
    assert result.role == "assistant"
    assert [s.source_id for s in result.provenance] == ["L", "R"]


def test_merge_refuses_spans_outside_the_source() -> None:
    left = sibling("L", "short")
    request = merge.MergeRequest(spans=[merge.MergeSpan(source_id="L", start=0, end=99)])
    with pytest.raises(SovereignError, match="does not fit"):
        merge.compose(request, {"L": left})


def test_merge_refuses_branches_that_are_not_siblings() -> None:
    """Merging across depths would produce a node whose parent is ambiguous."""
    left = sibling("L", "one", parent="a")
    right = sibling("R", "two", parent="b")
    request = merge.MergeRequest(
        spans=[
            merge.MergeSpan(source_id="L", start=0, end=3),
            merge.MergeSpan(source_id="R", start=0, end=3),
        ]
    )
    with pytest.raises(SovereignError, match="sibling"):
        merge.compose(request, {"L": left, "R": right})


def test_merge_leaves_its_sources_untouched() -> None:
    left = sibling("L", "keep me exactly")
    right = sibling("R", "and me")
    merge.compose(
        merge.MergeRequest(spans=[merge.MergeSpan(source_id="L", start=0, end=4)]),
        {"L": left, "R": right},
    )
    assert left.content == "keep me exactly" and right.content == "and me"
