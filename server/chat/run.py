"""Turning a chat request into rows, then into tokens.

The order matters: the assistant message and its run row are written *before* the first token, so
an interrupted generation is a real object on disk rather than lost client state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from server.chat.steering import resolve_steering
from server.context.assembler import assemble, to_prompt_messages
from server.db import repo
from server.db.connection import Database
from server.errors import NotFound, SovereignError
from server.hardware import probe, recommend, selection
from server.ids import now_ms
from server.knowledge import memory_index
from server.models.context import ContextAssembly
from server.models.params import SamplingParams
from server.models.provider import ModelInfo
from server.models.stream import ChatRequest
from server.providers.base import ModelProvider, PromptMessage
from server.providers.registry import ProviderRegistry
from server.settings import Settings

DEFAULT_CTX_FALLBACK = 4096


@dataclass
class PreparedRun:
    run_id: str
    message_id: str
    conversation_id: str
    assembly: ContextAssembly
    prompt: list[PromptMessage]
    params: SamplingParams
    provider: ModelProvider
    model: ModelInfo
    ctx_len: int
    assistant_prefix: str | None = None
    """Set when continuing an edited assistant turn: generation resumes from this text."""


async def resolve_model_id(
    db: Database, registry: ProviderRegistry, settings: Settings, requested: str | None
) -> str | None:
    """Which model to use, in order: what the request asked for, what you pinned, what fits.

    A pinned model that is no longer reachable - you closed LM Studio, llama.cpp is serving
    something else - silently falls back to the automatic choice rather than failing the request.
    Switching backends should not mean editing settings.
    """
    if requested:
        return requested

    available = await registry.models()
    with db.session() as conn:
        pinned = repo.settings.get(conn, repo.settings.SELECTED_MODEL)
    if pinned and any(m.id == pinned for m in available):
        return str(pinned)

    gpus, _ = probe.probe_gpus()
    ranked = selection.rank(
        available,
        gpu=gpus[0] if gpus else None,
        browser_reserve_mb=settings.hardware.browser_vram_reserve_mb,
        kv_dtype=settings.hardware.kv_cache_dtype,
    )
    choice = selection.best(ranked)
    return choice.model.id if choice else None


async def prepare(
    db: Database,
    registry: ProviderRegistry,
    settings: Settings,
    request: ChatRequest,
) -> PreparedRun:
    from server.graph import dag

    model_id = await resolve_model_id(db, registry, settings, request.model_id)
    provider, model = await registry.resolve(model_id)
    with db.session() as conn:
        conversation = repo.conversations.get(conn, request.conversation_id)
        if conversation is None:
            raise NotFound("Conversation")

        messages = repo.messages.list_for_conversation(conn, conversation.id)
        parent_id = request.parent_id or conversation.active_leaf_id
        if request.content is not None:
            user_message = repo.messages.create(
                conn,
                conversation_id=conversation.id,
                role="user",
                content=request.content,
                parent_id=parent_id,
            )
            messages.append(user_message)
            parent_id = user_message.id
        if parent_id is None:
            raise SovereignError("invalid_request", "Nothing to generate from: send a message.")

        ctx_len = _resolve_ctx_len(request, model, settings)
        params = request.params.resolved()
        _preflight_vram(model, ctx_len, settings, provider)

        steering = resolve_steering(conn, request)
        prefix = steering.prefix
        if steering.source_id:
            parent_id = steering.parent_id
        if steering.params is not None:
            params = steering.params

        path = dag.ancestors(messages, parent_id) if parent_id else []

        # Memory is retrieved against the turn being answered, and every entry that lands is
        # recorded below - which is what makes "retrieved 14 times" a count rather than a guess.
        query = request.content or next((m.content for m in reversed(path) if m.role == "user"), "")
        memories = memory_index.retrieve(
            conn,
            query,
            conversation_id=conversation.id,
            project_id=conversation.project_id,
        )
        assembly = await assemble(
            conversation=conversation,
            path=path,
            provider=provider,
            model_id=model.id,
            ctx_len=ctx_len,
            max_gen_tokens=params.max_tokens,
            prefs=repo.blocks.for_conversation(conn, conversation.id),
            assistant_prefix=prefix,
            prefix_source_id=steering.source_id,
            nudge=request.nudge,
            memories=memories,
        )
        prompt = to_prompt_messages(assembly, path)

        assistant = repo.messages.create(
            conn,
            conversation_id=conversation.id,
            role="assistant",
            content=prefix or "",
            parent_id=parent_id,
            model_id=model.id,
            params=params,
            status="streaming",
            edited_from_id=steering.source_id,
            forked_reason=steering.reason,
        )
        run_id = repo.runs.create(
            conn,
            message_id=assistant.id,
            model_id=model.id,
            params=params,
            ctx_len=ctx_len,
            model_sha256=model.sha256 or "",
        )
        conn.execute(
            "UPDATE runs SET assembly_json = ? WHERE id = ?",
            (assembly.model_dump_json(), run_id),
        )
        used = [b.source_ref for b in assembly.blocks if b.kind == "memory" and b.included]
        memory_index.record_usage(conn, [r for r in used if r], assistant.id, now_ms())
        repo.conversations.touch(conn, conversation.id, active_leaf_id=assistant.id)

    return PreparedRun(
        run_id=run_id,
        message_id=assistant.id,
        conversation_id=conversation.id,
        assembly=assembly,
        prompt=prompt,
        params=params,
        provider=provider,
        model=model,
        ctx_len=ctx_len,
        assistant_prefix=prefix,
    )


def _resolve_ctx_len(request: ChatRequest, model: ModelInfo, settings: Settings) -> int:
    if request.ctx_len:
        return min(request.ctx_len, model.ctx_len_max or request.ctx_len)
    gpus, _ = probe.probe_gpus()
    gpu = gpus[0] if gpus else None
    if gpu is None:
        return model.ctx_len_max or DEFAULT_CTX_FALLBACK
    return recommend.max_ctx_for(
        model,
        gpu=gpu,
        browser_reserve_mb=settings.hardware.browser_vram_reserve_mb,
        kv_dtype=settings.hardware.kv_cache_dtype,
    )


def _preflight_vram(
    model: ModelInfo, ctx_len: int, settings: Settings, provider: ModelProvider
) -> None:
    """Refuse before the backend OOMs, and hand back the fix (BRIEF.md section 2)."""
    if provider.kind not in ("llamacpp", "ollama", "lmstudio"):
        return
    gpus, _ = probe.probe_gpus()
    if not gpus:
        return
    budget = recommend.budget_for(
        model,
        ctx_len=ctx_len,
        gpu=gpus[0],
        browser_reserve_mb=settings.hardware.browser_vram_reserve_mb,
        kv_dtype=settings.hardware.kv_cache_dtype,
    )
    if budget.fits or model.size_bytes is None:
        # Without a real file size the estimate is too rough to refuse on; the backend decides.
        return
    raise SovereignError(
        "vram_insufficient",
        budget.explanation,
        remedy=budget.remedy,
        status_code=507,
    )


def stored_assembly(db: Database, run_id: str) -> ContextAssembly | None:
    with db.session() as conn:
        row = conn.execute("SELECT assembly_json FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None or not row["assembly_json"]:
        return None
    return ContextAssembly(**json.loads(row["assembly_json"]))
