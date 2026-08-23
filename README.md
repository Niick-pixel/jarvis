# Jarvis

A local-first AI workspace. No subscription, no token limits, nothing leaves the machine.

The point is not that it runs a model locally — LM Studio and Open WebUI already do that. The point
is the set of things you can only do when you own the inference server: edit the assistant's own
messages and continue from your version, see exactly what went into the context window, watch the
model's per-token uncertainty and steer it, and reproduce any answer exactly. The full spec is in
[`BRIEF.md`](BRIEF.md); the plan of record and its milestones are in [`PLAN.md`](PLAN.md).

**Status: M1 (the spine) is complete.** Working chat over SSE, the message DAG on disk, real context
accounting, the shader background with its state machine, and stop-and-keep. M2 turns the DAG into
a branching UI; M3 adds the token x-ray and live steering.

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/), Node 20+
- A backend: llama.cpp (recommended), Ollama, LM Studio, or any OpenAI-compatible endpoint
- An NVIDIA GPU helps, but the app starts, explains what it can run, and works without one

## Getting started

```bash
make models   # reads your card, ranks what fits, downloads it, registers it
make dev      # backend on 127.0.0.1:8080, frontend on 127.0.0.1:5173
```

`make models` prints the arithmetic rather than a recommendation you have to trust: weights, KV
cache at each context length, compute buffers, and the VRAM your browser's GPU process takes —
because on an 8-12GB card the browser and the model share the same card.

To try the interface before downloading several gigabytes of weights:

```bash
python scripts/dev_stub_server.py --port 8081   # speaks llama.cpp's protocol; generates nothing real
make dev
```

## What M1 actually does

- **Chat over SSE**, resumable. Every token is written to the database as it arrives, so a browser
  refresh mid-answer reattaches with `Last-Event-ID` and misses nothing. Closing the tab does not
  kill the generation.
- **Esc stops and keeps.** The partial answer stays, marked as stopped. Cancellation races the stop
  signal against each token, so it does not wait on a slow backend.
- **Every message is a DAG node** with its parent, model, sampling params and seed recorded. The
  branching UI arrives in M2; the data it needs is already being written.
- **Context accounting** using the backend's own tokenizer. If a backend has no tokenizer the
  numbers are labelled estimated instead of looking exact, and anything evicted is announced.
- **Honest capability negotiation.** A backend without logprobs hides the x-ray rather than faking
  it; a backend without a raw completion endpoint reports that live steering will not reuse the KV
  cache.
- **VRAM preflight.** If a request will not fit you get a sentence and a button that fixes it, not
  an OOM stack trace.
- **Automatic model selection.** The app ranks every model it can reach against your actual card
  and runs the largest local one that genuinely fits. The picker shows the same ranking with the
  arithmetic behind each verdict — weights, KV cache, browser reserve, headroom — so "too big" is
  a number, not an opinion. Pin one if you prefer; if a pinned model stops being reachable the app
  falls back to the automatic choice rather than failing the request. A remote OpenAI-compatible
  endpoint is listed, labelled as leaving the machine, and never selected automatically.
- **Every conversation saved locally**, browsable and switchable from the sidebar. Rows in SQLite,
  not browser storage: they survive reboots, and deleting one is a hard delete.

## Development

```bash
make check    # ruff, mypy, pytest, schema drift, file length, contrast, no-phone-home
make bench    # model tok/s, and the background's GPU cost against the 3% budget
make types    # regenerate the TypeScript types from the OpenAPI schema
```

`make check` enforces the rules that are easy to claim and hard to keep: TypeScript types must be
regenerated from the Pydantic models, no source file may exceed 250 lines, body text must clear
4.5:1 against the brightest frame the shader can produce, and the built bundle must not reference
any external origin.

Tests cover exactly three things — the conversation DAG, the context assembler's token accounting,
and the streaming interrupt/resume path — because those are where a bug is silent and expensive.

## Privacy and safety

Everything binds `127.0.0.1`. A non-loopback bind without an auth token is a startup failure, not a
warning, and the registry refuses to talk to a non-loopback inference port. There is no telemetry,
and `make check` verifies the built frontend contains no external origins. Retrieved text is wrapped
as data with its provenance and never treated as instructions.
