"""Turning a chat request into rows, then into tokens.

The order matters: the assistant message and its run row are written *before* the first token, so
an interrupted generation is a real object on disk rather than lost client state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from server.context.assembler import assemble, to_prompt_messages
from server.db import repo
from server.db.connection import Database
from server.errors import NotFound, SovereignError
from server.hardware import probe, recommend
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


async def prepare(
    db: Database,
    registry: ProviderRegistry,
    settings: Settings,
    request: ChatRequest,
) -> PreparedRun:
    from server.graph import dag

    provider, model = await registry.resolve(request.model_id)
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

        path = dag.ancestors(messages, parent_id)
        assembly = await assemble(
            conversation=conversation,
            path=path,
            provider=provider,
            model_id=model.id,
            ctx_len=ctx_len,
            max_gen_tokens=params.max_tokens,
        )
        prompt = to_prompt_messages(assembly, path)

        assistant = repo.messages.create(
            conn,
            conversation_id=conversation.id,
            role="assistant",
            content="",
            parent_id=parent_id,
            model_id=model.id,
            params=params,
            status="streaming",
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
