"""The Council (BRIEF.md 4.6): one prompt, several models, a judge that cannot see the names."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel

CouncilMode = Literal["sequential", "mixed"]


class CouncilMember(BaseModel):
    label: str
    model_id: str
    seed: int | None = None
    """Different seeds make "the same model twice" a real comparison rather than a duplicate."""


class CouncilAnswer(BaseModel):
    label: str
    model_id: str
    content: str = ""
    gen_tokens: int = 0
    gen_ms: int = 0
    error: str | None = None


class Ranking(BaseModel):
    label: str
    rank: int
    reason: str = ""


class AgreementCell(BaseModel):
    a: str
    b: str
    similarity: float


class CouncilVerdict(BaseModel):
    ranking: list[Ranking] = []
    synthesis: str = ""
    disagreements: str = ""
    """Where the answers actually differ - the interesting part, not just who won."""
    judge_model_id: str | None = None
    blind: bool = True


class ScoreboardRow(BaseModel):
    model_id: str
    category: str
    wins: int
    appearances: int

    @property
    def win_rate(self) -> float:
        return self.wins / self.appearances if self.appearances else 0.0


class CouncilRequest(BaseModel):
    question: str
    model_ids: list[str] = []
    """Empty means every model this machine can reach."""
    rubric: str = ""
    category: str = "general"
    judge_model_id: str | None = None
    conversation_id: str | None = None


class CouncilReport(BaseModel):
    run_id: str
    question: str
    mode: CouncilMode
    answers: list[CouncilAnswer] = []
    agreement: list[AgreementCell] = []
    agreement_detail: str = ""
    verdict: CouncilVerdict | None = None


# --- streamed events ---


class PlanEvent(BaseModel):
    type: Literal["plan"] = "plan"
    run_id: str
    members: list[CouncilMember]
    mode: CouncilMode
    detail: str


class AnswerStartEvent(BaseModel):
    type: Literal["answer_start"] = "answer_start"
    label: str
    model_id: str


class AnswerTokenEvent(BaseModel):
    type: Literal["answer_token"] = "answer_token"
    label: str
    text: str


class AnswerDoneEvent(BaseModel):
    type: Literal["answer_done"] = "answer_done"
    answer: CouncilAnswer


class AgreementEvent(BaseModel):
    type: Literal["agreement"] = "agreement"
    cells: list[AgreementCell]
    detail: str


class VerdictEvent(BaseModel):
    type: Literal["verdict"] = "verdict"
    verdict: CouncilVerdict


class CouncilDoneEvent(BaseModel):
    type: Literal["council_done"] = "council_done"
    run_id: str


CouncilEvent = Annotated[
    PlanEvent
    | AnswerStartEvent
    | AnswerTokenEvent
    | AnswerDoneEvent
    | AgreementEvent
    | VerdictEvent
    | CouncilDoneEvent,
    Field(discriminator="type"),
]


class CouncilEnvelope(RootModel[CouncilEvent]):
    """Declared as a response model so every event shape reaches the generated TypeScript."""
