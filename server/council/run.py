"""Orchestrating one Council run: fan out, embed, judge, record, stream.

The judge is invoked with (label, answer) pairs only. Model identity is re-attached afterwards,
here, once the verdict exists - so nothing upstream can carry a name into the judging prompt.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from server.council import agreement, fanout, judge, scoreboard
from server.db.connection import Database
from server.ids import new_id, now_ms
from server.knowledge.retrieval import embedder_for
from server.models.council import (
    AgreementEvent,
    CouncilAnswer,
    CouncilDoneEvent,
    CouncilEvent,
    CouncilRequest,
    PlanEvent,
    VerdictEvent,
)
from server.providers.registry import ProviderRegistry
from server.settings import Settings

JUDGE_CTX = 8192


async def run(
    db: Database, registry: ProviderRegistry, settings: Settings, request: CouncilRequest
) -> AsyncIterator[CouncilEvent]:
    available = await registry.models()
    members, mode, detail = fanout.plan(available, request.model_ids)
    run_id = new_id("cnc")

    with db.session() as conn:
        conn.execute(
            "INSERT INTO council_runs (id, conversation_id, question, rubric, category, mode,"
            " created_at) VALUES (?,?,?,?,?,?,?)",
            (
                run_id,
                request.conversation_id,
                request.question,
                request.rubric,
                request.category,
                mode,
                now_ms(),
            ),
        )
    yield PlanEvent(run_id=run_id, members=members, mode=mode, detail=detail)

    answers: list[CouncilAnswer] = []
    async for item in fanout.fanout(registry, members, request.question, available):
        if isinstance(item, list):
            answers = item
        else:
            yield item

    with db.session() as conn:
        for index, answer in enumerate(answers):
            conn.execute(
                "INSERT INTO council_answers (id, run_id, label, model_id, ord, content,"
                " gen_tokens, gen_ms, error) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    new_id("ans"),
                    run_id,
                    answer.label,
                    answer.model_id,
                    index,
                    answer.content,
                    answer.gen_tokens,
                    answer.gen_ms,
                    answer.error,
                ),
            )

    # From here the judge sees labels and text. Nothing else is passed along.
    blind = [(a.label, a.content) for a in answers if a.content.strip() and not a.error]

    cells, note = await agreement.matrix(embedder_for(settings), blind)
    with db.session() as conn:
        for cell in cells:
            conn.execute(
                "INSERT INTO council_agreement (run_id, a_label, b_label, similarity)"
                " VALUES (?,?,?,?)",
                (run_id, cell.a, cell.b, cell.similarity),
            )
    yield AgreementEvent(cells=cells, detail=note)

    judge_provider, judge_model = await registry.resolve(request.judge_model_id)
    verdict = await judge.judge(
        judge_provider,
        model_id=judge_model.id,
        ctx_len=JUDGE_CTX,
        question=request.question,
        rubric=request.rubric,
        answers=blind,
    )

    winner_label = next((r.label for r in verdict.ranking if r.rank == 1), None)
    by_label = {a.label: a for a in answers}
    winner = by_label.get(winner_label or "")

    with db.session() as conn:
        for ranking in verdict.ranking:
            conn.execute(
                "INSERT INTO council_ranking (run_id, label, rank, reason) VALUES (?,?,?,?)",
                (run_id, ranking.label, ranking.rank, ranking.reason),
            )
        conn.execute(
            "UPDATE council_runs SET judge_model_id = ?, synthesis = ?, disagreements = ?,"
            " finished_at = ? WHERE id = ?",
            (judge_model.id, verdict.synthesis, verdict.disagreements, now_ms(), run_id),
        )
        scoreboard.record(
            conn,
            category=request.category,
            appearances=[a.model_id for a in answers],
            winner_model_id=winner.model_id if winner else None,
        )

    yield VerdictEvent(verdict=verdict)
    yield CouncilDoneEvent(run_id=run_id)
