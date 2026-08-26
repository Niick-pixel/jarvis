"""The SSE event union. One definition, exhaustively switchable on the TypeScript side."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel

from server.errors import ErrorBody
from server.models.context import ContextAssembly
from server.models.params import SamplingParams

StopReason = Literal["eos", "length", "user_stop", "nudge", "error", "provider_closed"]


class Alternative(BaseModel):
    token: str
    logprob: float


class AssemblyEvent(BaseModel):
    type: Literal["assembly"] = "assembly"
    assembly: ContextAssembly


class RunEvent(BaseModel):
    type: Literal["run"] = "run"
    run_id: str
    message_id: str
    seed: int
    model_id: str


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    i: int
    text: str
    logprob: float | None = None
    top: list[Alternative] | None = None
    t_ms: float = 0.0


class NudgeEvent(BaseModel):
    type: Literal["nudge"] = "nudge"
    token_idx: int
    text: str


class UsageEvent(BaseModel):
    type: Literal["usage"] = "usage"
    prompt_tokens: int
    gen_tokens: int
    prompt_eval_ms: int
    gen_ms: int
    tps: float


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    stop_reason: StopReason
    message_id: str


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    error: ErrorBody


StreamEvent = Annotated[
    AssemblyEvent | RunEvent | TokenEvent | NudgeEvent | UsageEvent | DoneEvent | ErrorEvent,
    Field(discriminator="type"),
]


class ForceToken(BaseModel):
    """Truncate a message at one token and force a different one in its place."""

    message_id: str
    token_idx: int
    token: str


class StreamEnvelope(RootModel[StreamEvent]):
    """The `data` payload of one SSE frame.

    Declared as a response model purely so every event shape reaches the OpenAPI schema, and from
    there the generated TypeScript. Without this the SSE union would be the one part of the API
    the frontend had to describe by hand - exactly the duplication rule 0.5 forbids.
    """


class ChatRequest(BaseModel):
    conversation_id: str
    parent_id: str | None = None
    """Where to attach. None continues from the conversation's active leaf."""
    content: str | None = None
    """The user turn to append first. None resumes/regenerates from an existing parent."""
    continue_from: str | None = None
    """Continue an assistant message you edited: its text becomes the prefix for generation."""
    force_token: ForceToken | None = None
    """Rewrite the model's choice at one token and carry on from there (BRIEF.md 4.3)."""
    nudge: str | None = None
    """A system-level interjection delivered with a continuation (BRIEF.md 4.4)."""
    research: bool = False
    """Search the web first, in rounds, and inject what comes back as citable blocks."""
    rerun_of: str | None = None
    """Reproduce a message with its own recorded params, as a sibling (BRIEF.md 4.5)."""
    model_id: str | None = None
    params: SamplingParams = SamplingParams()
    ctx_len: int | None = None


class StopRequest(BaseModel):
    run_id: str
