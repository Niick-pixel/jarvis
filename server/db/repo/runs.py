from __future__ import annotations

import json
import sqlite3

from server.ids import new_id, now_ms
from server.models.params import SamplingParams
from server.models.stream import Alternative, StopReason, TokenEvent


def create(
    conn: sqlite3.Connection,
    *,
    message_id: str,
    model_id: str,
    params: SamplingParams,
    ctx_len: int,
    model_sha256: str = "",
    parent_run_id: str | None = None,
) -> str:
    rid = new_id("run")
    conn.execute(
        "INSERT INTO runs (id, message_id, model_id, model_sha256, seed, temperature, top_p,"
        " top_k, repeat_penalty, ctx_len, parent_run_id, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            rid,
            message_id,
            model_id,
            model_sha256,
            params.seed,
            params.temperature,
            params.top_p,
            params.top_k,
            params.repeat_penalty,
            ctx_len,
            parent_run_id,
            now_ms(),
        ),
    )
    return rid


def append_token(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    idx: int,
    text: str,
    byte_start: int,
    logprob: float | None = None,
    top: list[Alternative] | None = None,
    timing_ms: float = 0.0,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO run_tokens (run_id, idx, text, logprob, top_json, byte_start,"
        " byte_end, timing_ms) VALUES (?,?,?,?,?,?,?,?)",
        (
            run_id,
            idx,
            text,
            logprob,
            json.dumps([a.model_dump() for a in top]) if top else None,
            byte_start,
            byte_start + len(text.encode()),
            timing_ms,
        ),
    )


def tokens_after(conn: sqlite3.Connection, run_id: str, after_idx: int) -> list[TokenEvent]:
    """Replay for a reconnect: exactly the tokens the client has not seen."""
    rows = conn.execute(
        "SELECT idx, text, logprob, top_json, timing_ms FROM run_tokens"
        " WHERE run_id = ? AND idx > ? ORDER BY idx",
        (run_id, after_idx),
    )
    events: list[TokenEvent] = []
    for r in rows:
        top = [Alternative(**a) for a in json.loads(r["top_json"])] if r["top_json"] else None
        events.append(
            TokenEvent(
                i=r["idx"],
                text=r["text"],
                logprob=r["logprob"],
                top=top,
                t_ms=r["timing_ms"] or 0.0,
            )
        )
    return events


def token_count(conn: sqlite3.Connection, run_id: str) -> int:
    sql = "SELECT COUNT(*) AS n FROM run_tokens WHERE run_id = ?"
    return int(conn.execute(sql, (run_id,)).fetchone()["n"])


def finish(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    stop_reason: StopReason,
    prompt_tokens: int = 0,
    gen_tokens: int = 0,
    prompt_eval_ms: int = 0,
    gen_ms: int = 0,
) -> None:
    conn.execute(
        "UPDATE runs SET stop_reason = ?, prompt_tokens = ?, gen_tokens = ?, prompt_eval_ms = ?,"
        " gen_ms = ? WHERE id = ?",
        (stop_reason, prompt_tokens, gen_tokens, prompt_eval_ms, gen_ms, run_id),
    )


def message_id_for(conn: sqlite3.Connection, run_id: str) -> str | None:
    row = conn.execute("SELECT message_id FROM runs WHERE id = ?", (run_id,)).fetchone()
    return row["message_id"] if row else None


def bump_counter(conn: sqlite3.Connection, key: str, amount: float) -> None:
    conn.execute(
        "INSERT INTO counters (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = value + excluded.value",
        (key, amount),
    )


def latest_run_id(conn: sqlite3.Connection, message_id: str) -> str | None:
    row = conn.execute(
        "SELECT id FROM runs WHERE message_id = ? ORDER BY created_at DESC LIMIT 1", (message_id,)
    ).fetchone()
    return row["id"] if row else None


def all_tokens(conn: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT idx, text, logprob, top_json, byte_start, byte_end, timing_ms"
            " FROM run_tokens WHERE run_id = ? ORDER BY idx",
            (run_id,),
        )
    )


def byte_start(conn: sqlite3.Connection, run_id: str, idx: int) -> int | None:
    row = conn.execute(
        "SELECT byte_start FROM run_tokens WHERE run_id = ? AND idx = ?", (run_id, idx)
    ).fetchone()
    return int(row["byte_start"]) if row else None


def params_for(conn: sqlite3.Connection, message_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT model_id, seed, temperature, top_p, top_k, repeat_penalty, ctx_len"
        " FROM runs WHERE message_id = ? ORDER BY created_at DESC LIMIT 1",
        (message_id,),
    ).fetchone()


def add_nudge(conn: sqlite3.Connection, *, message_id: str, token_idx: int, text: str) -> None:
    conn.execute(
        "INSERT INTO nudges (id, message_id, token_idx, text, created_at) VALUES (?,?,?,?,?)",
        (new_id("ndg"), message_id, token_idx, text, now_ms()),
    )


def nudges_for(conn: sqlite3.Connection, message_id: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT token_idx, text, created_at FROM nudges WHERE message_id = ?"
            " ORDER BY token_idx",
            (message_id,),
        )
    )
