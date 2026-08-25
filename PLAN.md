# PLAN.md — Jarvis, a local-first AI workspace

Plan of record for `BRIEF.md`. **No application code has been written.** This document is the thing
you approve; section 5 (dependencies) doubles as the approved-dependency list that rule 0.4 binds me
to for the rest of the project.

Read in this order if you're short on time: §1 (what your hardware forces), §7 (milestones), §5
(deps). Everything else is reference.

---

## 0. Where the code lives

Its own repository, `jarvis`, with the project at the root:

```
jarvis/
├── BRIEF.md          ← the spec, section 2 filled in from your answers
├── PLAN.md           ← this file
├── server/ web/ …    ← everything in section 3
```

The plan was originally drafted as a `sovereign/` subtree inside the `tico-market` iOS repo; it
now stands alone, so that nesting is gone and the paths in section 3 are repo-root-relative.
`BRIEF.md` and `PLAN.md` stay at the root so a fresh session can start with `cat BRIEF.md`.

**Still in `tico-market`:** the branch `claude/local-first-ai-workspace-1bct5q` and its PR #1 carry
an early copy of these two files. They are superseded by this repo — close the PR and delete the
branch when convenient.

---

## 1. What your hardware actually forces

Recorded in `BRIEF.md` §2: **8–12GB NVIDIA VRAM, Windows 11 + WSL2, no container runtime at all.**
Six decisions fall straight out of that, and they are not negotiable-by-preference — they're
arithmetic.

### 1.1 The VRAM budget is the whole design constraint

On a 24GB machine the shader background is free. On yours, the browser's GPU process and the model
are roommates in the same 8–12GB. So the VRAM accounting the brief asks to "surface in the UI"
(§2, §4.10) is not a vanity readout here — it's the thing that decides whether the app works.

The budget the app computes and shows, for a 10GB card running an 8B model at Q4_K_M:

| Consumer | Cost | Notes |
|---|---|---|
| Model weights (8B, Q4_K_M) | ~4.7–5.0 GB | from the GGUF file size, not an estimate |
| KV cache @ 32K ctx | ~1.0–2.0 GB | computed from GGUF metadata, see formula below |
| llama.cpp compute buffers | ~0.4–0.8 GB | batch-size dependent |
| Chromium GPU process (on Windows, same card) | ~0.3–0.8 GB | **the one everybody forgets** |
| Background shader + edge glow | ~0.05–0.15 GB | half-res FBO, one draw call |
| Windows desktop compositor | ~0.3–0.6 GB | already spent before you start |

That lands at roughly 7–9.5 GB. On a 12GB card it fits at 32K context with headroom; on an 8GB card
it does not, and the app must say so in words rather than dying inside `ggml_backend_alloc`.

KV cache is computed, not guessed:

```
kv_bytes ≈ 2 × n_layers × n_kv_heads × head_dim × ctx_len × dtype_bytes
```

All four model terms come from the GGUF header. `dtype_bytes` is 2 for f16, 1 for the `q8_0` KV
cache we default to on this hardware (halves the cost, costs almost nothing in quality). This
formula is implemented once, in `server/hardware/recommend.py`, and the same numbers drive both
`make models` and the HUD — no second copy in the frontend.

**Preflight, not postmortem.** Before any generation the server checks
`free_vram ≥ weights + kv(requested_ctx) + compute_buffers + browser_reserve`. If it fails you get a
sentence — "32K context needs 1.8GB of KV cache; 1.1GB free. Drop to 16K, or enable Performance mode
to hand back ~150MB" — and a button that applies the fix. Rule 2.x of the brief ("never crash with
an OOM I have to decode from a stack trace") is enforced here and tested here.

### 1.2 The model shortlist is resolved at runtime, never hardcoded

Your brief warns that the Aug-2026 tags move fast, and I can't verify them from here. So
`make models` does not ship a table of tags — it ships a table of *requirements*
(`models.toml`: family, param count, quant, min VRAM, context ceiling, why-you'd-pick-it)
and resolves live tags against the Ollama library / HuggingFace at run time, showing the real
download size returned by the registry. A tag that no longer exists shows as unavailable instead of
downloading something surprising.

For your tier the shortlist it will rank:

- **`qwen3:8b` @ Q4_K_M** — default. General reasoning, ~5GB, 32K native context. This is the pick.
- **`qwen2.5-coder:7b` @ Q4_K_M** — if the workload is mostly code.
- **A 12–14B at Q4** — only on the 12GB card, and only at ≤16K context. `make models` shows it as
  fitting-but-tight and tells you what it costs you in context.
- **`gpt-oss:20b` and everything above it in the brief's shortlist** — listed as *not runnable
  fully-offloaded on this machine*, with the number that proves it, rather than silently omitted.
  Partial CPU offload is offered with an honest tok/s estimate from a 30-second bench, not a
  marketing number.

Expected tokens/sec is **measured, not printed from a table**: `make models` runs a short
prompt-eval + generation bench after download and stores the real number for your card in the DB,
which is also what the HUD's baseline compares against.

### 1.3 WSL2 changes four implementation details

1. **NVML works, but partially.** `pynvml` loads `/usr/lib/wsl/lib/libnvidia-ml.so.1` and reports
   VRAM and utilization; **power draw and temperature are frequently unavailable through the WSL
   passthrough**. The HUD (§4.10) shows `—` with a tooltip explaining why, and never invents a
   number. This is a real, visible degradation of a P1 feature and I'd rather you hear it now.
2. **`watchdog` inotify does not fire on `/mnt/c`.** Windows-drive paths need `PollingObserver`
   (higher latency, more CPU). The indexer picks the observer per-path automatically and the RAG
   settings page labels Windows paths as "polled every N seconds" so the behavior isn't mysterious.
   Recommendation surfaced in the UI: keep indexed folders on the WSL ext4 side.
3. **Two hosts, one localhost.** The backend binds `127.0.0.1` *inside WSL2*; Windows' localhost
   forwarding makes `http://localhost:8080` reachable from the Windows browser. That is still a
   loopback-only bind — nothing is exposed to the LAN — and the bind guard in §8 treats a
   non-loopback bind exactly as the brief demands.
4. **WSL2 RAM ceiling.** WSL2 defaults to ~50% of host RAM, which caps CPU-offload and the
   embedding/rerank models. The hardware page reads the actual cgroup limit and shows it next to a
   one-line `.wslconfig` snippet if it's the binding constraint.

### 1.4 No Docker ⇒ two things move

- **SearXNG (M4)** runs native: its own `uv` venv under `services/searxng/`, launched by
  `make dev` as a child process bound to `127.0.0.1`. Note it is AGPL-3.0 — it stays a **separate
  process we never link into**, which keeps the brief's "permissively licensed" preference intact
  for anything we actually import.
- **vLLM / SGLang (§3)** is planned as an adapter only, and honestly deprioritized to M5+: vLLM
  needs more VRAM headroom than this machine has, and without Docker it's a heavy native install.
  The adapter is ~80 lines against the OpenAI-compatible base, so it costs nothing to keep and it's
  there the day you add a bigger card. The **OpenAI-compatible adapter is built in M1** regardless —
  that's your "borrow a frontier model" path and it needs no local VRAM.

### 1.5 Embeddings and voice get downgraded, on purpose

`bge-m3` (568M, ~2.2GB f16) plus a reranker plus an 8B model does not fit next to the browser on
this card. M4 defaults instead to **`nomic-embed-text` (137M) on GPU** or bge-small, and runs
**`bge-reranker-v2-m3` on CPU** where its latency is acceptable for top-20 reranking. Same for M5:
`faster-whisper` at `small`/`int8_float16` (~0.5–1GB), Piper TTS on CPU. Every one of these is a
settings-page choice with its VRAM cost printed next to it — you can spend the memory differently
if you want, you just can't spend it twice.

---

## 2. Design tradeoffs, one sentence each (brief rule 0.10)

Each of these picks the inspectable option over the clever one.

1. **Context blocks are snapshotted in full, per assistant message** — the DB grows faster, but
   "what exactly was in context for this answer" stays answerable a year later instead of being
   re-derived from code that has since changed.
2. **Logprobs live in a side table, capped at top-5** — roughly 5–10× the storage of the message
   text, so there's a "purge logprobs older than N days" action; keeping them is what makes §4.3
   work on old messages.
3. **SSE with a DB-backed token log, not WebSockets** — one extra write per token batch, in exchange
   for resume-after-refresh, `curl`-able streams, and a transcript that survives a crash mid-answer.
4. **Token counts come from the inference server's own tokenizer** (`/tokenize` on llama.cpp), not a
   local estimator — one round-trip per assembly, but the Context Inspector's numbers are the real
   ones rather than a plausible-looking lie.
5. **Nudge resume uses raw completion with the partial as prefix** — requires a provider that
   exposes `/completion`; chat-only backends fall back to re-sending the partial as an assistant
   turn and the UI says "KV cache not reused on this backend" instead of pretending.
6. **`sqlite-vec` brute-force scan, no ANN index** — linear in chunk count (fine to ~100k chunks on
   this machine), and there is no index structure that can silently corrupt or go stale.
7. **The shader ships on by default, with an automatic, announced fallback** — on a card this size
   the app measures the VRAM cost at startup and drops to the CSS mesh gradient if the model needs
   the memory, telling you it did so; the alternative (silently degrading) is exactly the behavior
   the brief hates.
8. **Every generation is a row before it is a stream** — the assistant message row and its `run` row
   are written *before* the first token, so an interrupted generation is a real, inspectable,
   resumable object rather than lost client state.

---

## 3. File and folder tree

`(M1)`…`(M6)` marks the milestone that creates the file. Nothing is created before its milestone —
no empty stubs, per rule 0.3. Every file listed is projected under ~250 lines; the ones at risk are
called out.

```
jarvis/
├── Makefile                          (M1) dev / check / models  + bench, types, contrast
├── README.md                         (M1) how to run it on WSL2, in ~40 lines
├── pyproject.toml                    (M1) uv-managed, deps pinned, milestone extras
├── config.toml.example               (M1) bind, providers, paths, visual preset
├── models.toml                       (M1) requirement table for `make models` (no hardcoded tags)
├── .env.example                      (M1) only for OpenAI-compatible keys; never committed
│
├── server/
│   ├── main.py                       (M1) app factory, lifespan, router mount, SPA serve
│   ├── settings.py                   (M1) pydantic-settings + the bind/auth invariant (§8)
│   ├── errors.py                     (M1) typed error envelope shared with the frontend
│   │
│   ├── models/                       ← Pydantic = single source of truth (rule 0.5)
│   │   ├── message.py                (M1) Message, Role, MessageCreate, MessageEdit
│   │   ├── conversation.py           (M1) Conversation, TreeNode, ActivePath
│   │   ├── params.py                 (M1) SamplingParams (seed, temp, top_p, top_k, repeat_penalty)
│   │   ├── stream.py                 (M1) SSE event union: Assembly|Token|Nudge|Usage|Done|Error
│   │   ├── context.py                (M2) ContextBlock, ContextAssembly, EvictionNotice
│   │   ├── provider.py               (M1) ProviderInfo, Capabilities, ModelInfo
│   │   ├── logprob.py                (M3) TokenLogprob, Alternative
│   │   ├── hardware.py               (M1) GpuInfo, VramBudget, ModelRecommendation
│   │   └── hud.py                    (M3) HudSample, LifetimeCounters
│   │
│   ├── db/
│   │   ├── connection.py             (M1) WAL pragmas, sqlite-vec load, connection per request
│   │   ├── migrate.py                (M1) forward-only numbered SQL migrations, no ORM
│   │   ├── migrations/
│   │   │   ├── 001_core.sql          (M1) conversations, messages, runs, models, settings
│   │   │   ├── 002_context.sql       (M2) context_blocks
│   │   │   ├── 003_xray.sql          (M3) message_tokens, nudges
│   │   │   ├── 004_knowledge.sql     (M4) sources, chunks, vec_chunks, fts_chunks, memory_*
│   │   │   ├── 005_council.sql       (M5) council_runs, council_answers, scores
│   │   │   └── 006_agents.sql        (M6) jobs, job_runs, audit_log, tool_grants
│   │   └── repo/                     ← thin, typed data access; one module per aggregate
│   │       ├── conversations.py      (M1)
│   │       ├── messages.py           (M1)
│   │       ├── runs.py               (M1)
│   │       ├── blocks.py             (M2)
│   │       └── tokens.py             (M3)
│   │
│   ├── providers/
│   │   ├── base.py                   (M1) ModelProvider protocol, Token, Capabilities
│   │   ├── llamacpp.py               (M1) primary: /completion, /tokenize, n_probs, prefix resume
│   │   ├── openai_compat.py          (M1) any OpenAI-compatible URL + key
│   │   ├── ollama.py                 (M1) autodetect :11434, wraps openai_compat + /api/show
│   │   ├── lmstudio.py               (M1) autodetect :1234, openai_compat subclass
│   │   ├── registry.py               (M1) discovery, health, capability negotiation
│   │   ├── embeddings.py             (M4) same interface, embed() instead of stream()
│   │   └── vllm.py                   (M5) throughput adapter; see §1.4 for why it's late
│   │
│   ├── context/
│   │   ├── assembler.py              (M2) ordered blocks → prompt + exact accounting  ⚠ watch 250
│   │   ├── blocks.py                 (M2) block kinds, priorities, pin/enable semantics
│   │   ├── budget.py                 (M2) eviction policy + loud EvictionNotice
│   │   └── tokenizer.py              (M2) provider /tokenize with a per-model memo cache
│   │
│   ├── graph/
│   │   ├── dag.py                    (M2) pure: path_to_leaf, siblings, fork, ancestors  ← tested
│   │   └── merge.py                  (M2) span-merge of two sibling branches (§4.1)
│   │
│   ├── chat/
│   │   ├── run.py                    (M1) create message+run rows, then stream (tradeoff #8)
│   │   ├── sse.py                    (M1) event framing, Last-Event-ID resume, disconnect
│   │   ├── cancel.py                 (M1) cancel scopes; Esc = stop-and-keep     ← tested
│   │   ├── steering.py               (M3) nudge → abort → prefix continuation    ← tested
│   │   ├── forced_token.py           (M3) truncate at index, force token, resume
│   │   └── replay.py                 (M3) rerun / rerun-with → sibling branch
│   │
│   ├── hardware/
│   │   ├── probe.py                  (M1) pynvml via WSL lib path, cgroup RAM, disk free
│   │   ├── recommend.py              (M1) the KV formula + shortlist ranking (§1.1)
│   │   └── bench.py                  (M1) measured prompt-eval / gen tok/s
│   │
│   ├── hud/
│   │   ├── telemetry.py              (M3) 1Hz sampler, graceful `—` for missing NVML fields
│   │   └── counters.py               (M3) lifetime tokens + local price table → cost avoided
│   │
│   ├── knowledge/                    (M4) watcher.py, chunker.py, index.py, hybrid.py,
│   │                                      rerank.py, memory.py, memory_git.py
│   ├── council/                      (M5) fanout.py, judge.py (blind), agreement.py, scoreboard.py
│   ├── voice/                        (M5) stt.py (faster-whisper), tts.py (Piper)
│   ├── agents/                       (M6) scheduler.py, loop.py, inbox.py
│   ├── tools/                        (M6) registry.py, gate.py, audit.py, sandbox.py  ← §8 boundary
│   ├── export/obsidian.py            (M6) branch → Markdown + front-matter + [[wikilinks]]
│   │
│   └── api/                          ← thin routers; all logic lives in the modules above
│       ├── conversations.py  (M1)   ├── messages.py   (M1)   ├── chat.py       (M1)
│       ├── models_api.py     (M1)   ├── hardware.py   (M1)   ├── context.py    (M2)
│       ├── xray.py           (M3)   ├── hud.py        (M3)   ├── knowledge.py  (M4)
│       ├── council.py        (M5)   ├── voice.py      (M5)   └── agents.py     (M6)
│
├── tests/                            ← exactly three subjects, per rule 0.7
│   ├── test_dag.py                   (M2) fork/sibling/path/merge invariants
│   ├── test_context_accounting.py    (M2) token math, pinning, eviction notices
│   ├── test_stream_interrupt.py      (M1→M3) cancel, resume, nudge, forced token
│   └── conftest.py                   (M1) in-memory DB + a fake provider with scripted tokens
│
├── scripts/
│   ├── models_cli.py                 (M1) `make models`: probe → rank → download → bench
│   ├── gen_types.py                  (M1) OpenAPI → web/src/api/schema.gen.ts, fails on drift
│   ├── contrast_check.py             (M1) renders shader extremes headless, asserts ≥4.5:1 (§5.5)
│   └── gpu_budget.py                 (M1) `make bench`: measures background GPU cost vs the 3% cap
│
├── services/searxng/                 (M4) native venv + config, 127.0.0.1 only
├── memory/                           (M4) your Markdown, its own auto-committing git repo
├── data/jarvis.db                 (M1) the entire application state, one file (gitignored)
│
└── web/
    ├── index.html, vite.config.ts, tailwind.config.ts, tsconfig.json      (M1)
    └── src/
        ├── main.tsx, App.tsx, routes.tsx                                  (M1)
        ├── api/
        │   ├── schema.gen.ts         (M1) GENERATED from OpenAPI — never hand-edited
        │   ├── client.ts             (M1) typed fetch wrapper
        │   └── stream.ts             (M1) SSE client with resume + typed event union
        ├── store/                    (M1→) conversation.ts, stream.ts, context.ts,
        │                                   visual.ts, hud.ts, settings.ts   (zustand slices)
        ├── scene/
        │   ├── Background.tsx        (M1) r3f canvas, half-res FBO, demand loop
        │   ├── shaders/warp.frag     (M1) domain-warped fBm + smoothstep stops
        │   ├── shaders/warp.vert     (M1)
        │   ├── EdgeGlow.tsx          (M1) conic ring, masked, blurred, spring opacity
        │   ├── energy.ts             (M1) state machine → spring-driven uEnergy/uPulse
        │   ├── presets.ts            (M1) Aurora / Solar / Deep
        │   ├── perf.ts               (M1) 30fps streaming cap, idle demote, perf-mode swap
        │   ├── FallbackGradient.tsx  (M1) CSS mesh gradient for Performance mode
        │   └── Orb.tsx               (M5) metaball SDF driven by mic RMS / token rate
        ├── chat/
        │   ├── MessageList.tsx, Message.tsx, Composer.tsx                  (M1)
        │   ├── StreamingText.tsx     (M1) per-word fade-in, not per-character
        │   ├── SiblingNav.tsx        (M2) inline ‹ 2/4 › switcher
        │   ├── EditMessage.tsx       (M2) edit any role, including assistant → forks
        │   ├── Nudge.tsx             (M3) stays enabled during generation
        │   ├── XRay.tsx              (M3) probability tint layer
        │   ├── TokenPopover.tsx      (M3) top-5 alternatives → force + resume
        │   └── ReplayDiff.tsx        (M3) word-level diff between siblings
        ├── context/ContextBar.tsx, BlockSheet.tsx, EvictionBanner.tsx      (M2)
        ├── graph/Minimap.tsx, layout.ts                                    (M2) d3-hierarchy
        ├── hud/Hud.tsx, VramGauge.tsx, Counters.tsx                        (M3)
        ├── knowledge/ (M4)  council/ (M5)  agents/ (M6)
        └── ui/                       (M1) Button, Sheet, Popover, Toggle — bespoke, spring-pressed
```

---

## 4. Database schema

One SQLite file, WAL mode, `foreign_keys=ON`, `synchronous=NORMAL`. Forward-only numbered
migrations, no ORM — the schema is readable in a text editor and greppable, which is the point.

### 4.1 Core (migration 001, M1)

```sql
CREATE TABLE conversations (
  id             TEXT PRIMARY KEY,          -- uuid7, sorts by time
  title          TEXT NOT NULL DEFAULT '',
  project_id     TEXT,                      -- memory/tool scoping (§4.7, §4.9)
  active_leaf_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
  system_prompt  TEXT NOT NULL DEFAULT '',
  visual_preset  TEXT NOT NULL DEFAULT 'aurora',
  created_at     INTEGER NOT NULL,          -- epoch ms
  updated_at     INTEGER NOT NULL
);

-- The DAG. Insert-only: nothing here is ever UPDATEd except `content` on a draft
-- and `status` on a completed run. Edits create new rows.
CREATE TABLE messages (
  id              TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  parent_id       TEXT REFERENCES messages(id) ON DELETE CASCADE,  -- NULL = root
  role            TEXT NOT NULL CHECK (role IN ('system','user','assistant','tool')),
  content         TEXT NOT NULL,
  model_id        TEXT REFERENCES models(id),
  params_json     TEXT,                     -- SamplingParams, serialized Pydantic
  token_count     INTEGER NOT NULL DEFAULT 0,
  status          TEXT NOT NULL DEFAULT 'complete'
                  CHECK (status IN ('streaming','complete','stopped','error')),
  edited_from_id  TEXT REFERENCES messages(id),  -- provenance of a fork (§4.1)
  forked_reason   TEXT,                     -- 'edit' | 'rerun' | 'forced_token' | 'merge'
  created_at      INTEGER NOT NULL
);
CREATE INDEX idx_messages_conv   ON messages(conversation_id, created_at);
CREATE INDEX idx_messages_parent ON messages(parent_id);

-- Everything needed to reproduce an assistant message exactly (§4.5).
CREATE TABLE runs (
  id               TEXT PRIMARY KEY,
  message_id       TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  model_id         TEXT NOT NULL REFERENCES models(id),
  model_sha256     TEXT NOT NULL,           -- the file's hash, not the tag
  seed             INTEGER NOT NULL,        -- always concrete; -1 is resolved before the call
  temperature      REAL NOT NULL,
  top_p            REAL NOT NULL,
  top_k            INTEGER NOT NULL,
  repeat_penalty   REAL NOT NULL,
  ctx_len          INTEGER NOT NULL,
  prompt_tokens    INTEGER,
  gen_tokens       INTEGER,
  prompt_eval_ms   INTEGER,
  gen_ms           INTEGER,
  stop_reason      TEXT,                    -- 'eos'|'length'|'user_stop'|'nudge'|'error'
  parent_run_id    TEXT REFERENCES runs(id),-- resume chains keep their lineage
  created_at       INTEGER NOT NULL
);
CREATE INDEX idx_runs_message ON runs(message_id);

CREATE TABLE models (
  id                TEXT PRIMARY KEY,       -- 'llamacpp:qwen3-8b-q4km'
  provider          TEXT NOT NULL,
  display_name      TEXT NOT NULL,
  file_path         TEXT,
  sha256            TEXT,
  quant             TEXT,
  size_bytes        INTEGER,
  ctx_len_max       INTEGER NOT NULL,
  n_layers          INTEGER, n_kv_heads INTEGER, head_dim INTEGER,  -- KV math inputs (§1.1)
  supports_logprobs INTEGER NOT NULL DEFAULT 0,
  supports_prefix   INTEGER NOT NULL DEFAULT 0,   -- raw completion → real nudge resume
  bench_gen_tps     REAL, bench_prompt_tps REAL,  -- measured, never assumed
  last_seen_at      INTEGER
);

CREATE TABLE settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
```

### 4.2 Context blocks (migration 002, M2)

```sql
-- A snapshot of exactly what went into one request. Written before the first token.
CREATE TABLE context_blocks (
  id           TEXT PRIMARY KEY,
  message_id   TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  ord          INTEGER NOT NULL,            -- final order after user reordering
  kind         TEXT NOT NULL,               -- system|memory|rag|pinned|history|tool|nudge
  label        TEXT NOT NULL,
  content      TEXT NOT NULL,               -- the literal text (tradeoff #1)
  token_count  INTEGER NOT NULL,
  pinned       INTEGER NOT NULL DEFAULT 0,
  included     INTEGER NOT NULL DEFAULT 1,  -- 0 = user toggled off, or evicted
  eviction     TEXT,                        -- NULL | 'budget' | 'summarized'
  source_ref   TEXT                         -- file:offset, memory id, message id
);
CREATE INDEX idx_blocks_message ON context_blocks(message_id, ord);
```

### 4.3 X-ray and steering (migration 003, M3)

```sql
CREATE TABLE message_tokens (
  message_id   TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  idx          INTEGER NOT NULL,            -- 0-based position within the message
  text         TEXT NOT NULL,
  logprob      REAL,
  top_json     TEXT,                        -- [{token, logprob}] × 5, NULL if unsupported
  byte_start   INTEGER NOT NULL,            -- offsets into content: tint + truncate without re-tokenizing
  byte_end     INTEGER NOT NULL,
  timing_ms    REAL,
  PRIMARY KEY (message_id, idx)
) WITHOUT ROWID;

CREATE TABLE nudges (
  id          TEXT PRIMARY KEY,
  message_id  TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  token_idx   INTEGER NOT NULL,             -- where it landed, for the inline marker (§4.4)
  text        TEXT NOT NULL,
  created_at  INTEGER NOT NULL
);
```

### 4.4 Later migrations (sketch — finalized at their milestone)

- **004 knowledge (M4):** `sources(path, kind, observer)`, `chunks(source_id, offset, text, hash)`,
  `vec_chunks` (`sqlite-vec` vec0 virtual table), `fts_chunks` (FTS5 external-content over
  `chunks`), `memory_entries(path, scope, project_id, hash)`,
  `memory_usage(entry_id, message_id, used_at)` — that last table is what makes "retrieved 14 times,
  last used 3 days ago" real rather than approximate.
- **005 council (M5):** `council_runs`, `council_answers(run_id, model_id, label, content)` with the
  A/B/C label stored separately from `model_id` so the judge query can be built blind by
  construction, and `model_scores(model_id, category, wins, n)`.
- **006 agents (M6):** `jobs(cron, prompt, project_id, enabled)`, `job_runs`,
  `tool_grants(project_id, tool, granted_at)`, `audit_log(tool, args_hash, path, result_hash, ...)`
  — hashes and paths only, never contents (brief §7).

### 4.5 DAG invariants, enforced and tested

1. `parent_id` is NULL or refers to a row in the same conversation created earlier ⇒ acyclic by
   construction; no cycle check needed at read time.
2. An edit never mutates: it inserts a sibling with the same `parent_id` and `edited_from_id` set.
   **Nothing is ever destroyed** (§4.1).
3. `active_leaf_id` must be a leaf-or-any node in the same conversation; the active path is
   `ancestors(active_leaf)` reversed.
4. Sibling order is `created_at, id` — stable, so `‹ 2/4 ›` doesn't shuffle between renders.
5. A `merge` (§4.1) creates a new node whose `parent_id` is the common ancestor, with the two source
   ids recorded in `forked_reason` provenance — the tree stays a tree; merges are recorded, not
   structural.

---

## 5. API surface

All request/response bodies are Pydantic models from `server/models/` — that is the only definition
of these shapes anywhere in the system. `make types` regenerates `web/src/api/schema.gen.ts` from
`/openapi.json`; `make check` regenerates and **fails if the file changed**, so a backend model
edit that isn't reflected in the frontend types breaks the build rather than production.

### 5.1 M1 — spine

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | version, db ok, providers up |
| `GET` | `/api/hardware` | GPU, VRAM free/total, RAM cgroup limit, disk, NVML field availability |
| `GET` | `/api/hardware/budget?model_id&ctx_len` | the §1.1 table, computed — powers preflight + UI |
| `GET` | `/api/providers` | discovered providers + `Capabilities{logprobs, prefix, embeddings}` |
| `GET` | `/api/models` | known models incl. bench numbers |
| `POST` | `/api/models/pull` | SSE download progress (used by `make models` and the UI) |
| `GET`/`POST` | `/api/conversations` | list / create |
| `GET` | `/api/conversations/{id}` | full tree + active path |
| `PATCH` | `/api/conversations/{id}` | title, `active_leaf_id`, system prompt, preset |
| `DELETE` | `/api/conversations/{id}` | hard delete, cascades |
| `POST` | `/api/conversations/{id}/messages` | append a message under a parent |
| `POST` | `/api/chat/stream` | **the main event** — see 5.4 |
| `POST` | `/api/chat/runs/{run_id}/stop` | Esc: stop and keep the partial |
| `GET` | `/api/chat/runs/{run_id}/events` | reconnect/resume a live or finished run |

### 5.2 M2 — graph and context

| Method | Path | Purpose |
|---|---|---|
| `PATCH` | `/api/messages/{id}` | edit **any role incl. assistant** → returns the new sibling |
| `GET` | `/api/messages/{id}/siblings` | for `‹ 2/4 ›` |
| `POST` | `/api/messages/merge` | span-merge two siblings → new leaf |
| `POST` | `/api/context/preview` | assemble **without generating** → `ContextAssembly` |
| `PATCH` | `/api/context/blocks` | toggle / pin / reorder before sending |
| `GET` | `/api/messages/{id}/context` | what actually went in, after the fact |

### 5.3 M3+ — instrument panel and beyond

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/messages/{id}/tokens` | logprobs + top-5 alternatives for the x-ray layer |
| `POST` | `/api/chat/force_token` | `{message_id, token_idx, token}` → truncate, force, resume |
| `POST` | `/api/chat/runs/{run_id}/nudge` | abort, keep partial, resume as prefix continuation |
| `POST` | `/api/chat/rerun` | `{message_id, params?}` → sibling branch (+ diff on the client) |
| `GET` | `/api/hud/stream` | SSE, 1Hz telemetry samples |
| `GET` | `/api/hud/counters` | lifetime tokens + cost-avoided |
| M4 | `/api/knowledge/*`, `/api/memory/*`, `/api/search` | index control, memory CRUD, private web search |
| M5 | `/api/council/*`, `/api/voice/*` | fan-out + blind judge; STT/TTS streams |
| M6 | `/api/agents/*`, `/api/tools/approvals`, `/api/audit` | jobs, approval gate, audit log |

### 5.4 The streaming contract

`POST /api/chat/stream` returns `text/event-stream`. Events are a discriminated union
(`server/models/stream.py`), so the TypeScript side gets an exhaustive `switch`:

```
event: assembly     data: ContextAssembly       ← first, always: blocks + token counts + evictions
event: run          data: {run_id, message_id, seed, model_id}
event: token        data: {i, text, logprob?, top?, t_ms}   ← id: <run_id>:<i>
event: nudge        data: {token_idx, text}                 ← a nudge landed here
event: usage        data: {prompt_tokens, gen_tokens, prompt_eval_ms, gen_ms, tps}
event: done         data: {stop_reason}
event: error        data: {code, message, remedy?}          ← e.g. VRAM preflight with a fix button
```

Three properties this buys, all of which are tested (`tests/test_stream_interrupt.py`):

- **Resumable.** Each `token` event carries `id: <run_id>:<i>`. A reconnect with `Last-Event-ID`
  replays from `i+1` out of `message_tokens`, so a browser refresh mid-answer loses nothing.
- **Interruptible without loss.** `stop` and `nudge` both close the upstream request, flush the
  partial into `messages.content`, and mark the run — the partial is a first-class row, not
  client state (tradeoff #8).
- **`curl`-able.** `curl -N localhost:8080/api/chat/stream -d @body.json` is a supported debugging
  path, which is most of why the brief chose SSE.

**Prompt-injection boundary (brief §7):** every block of kind `rag`, `tool`, or `web` is wrapped by
the assembler in an explicit data envelope with its provenance, and the tool layer (M6) will only
ever dispatch tools from calls parsed out of the *model's* output channel — never from text that
arrived inside a retrieved document. That's an architectural boundary in `context/blocks.py` and
`tools/gate.py`, not a sentence in a system prompt.

---

## 6. Dependencies — the approved list

One line of justification each, as required. **This list is what rule 0.4 binds me to**: after you
approve it, I ask before adding anything not here. Everything is permissively licensed (MIT / BSD /
Apache-2.0) except the two separate-process services noted at the end.

### 6.1 Backend, installed at M1

| Package | Why |
|---|---|
| `fastapi` | The brief picked it; also gives us the OpenAPI schema that generates the TS types for free. |
| `uvicorn[standard]` | ASGI server; `--host 127.0.0.1` by default and no phone-home. |
| `pydantic` (v2) | Single source of truth for every shape in the system (rule 0.5). |
| `pydantic-settings` | Typed config from `config.toml` + env, and the place the bind/auth invariant lives. |
| `sse-starlette` | Correct SSE framing plus client-disconnect propagation, which is what makes cancel work. |
| `httpx` | One async HTTP client for every provider adapter, with streaming response support. |
| `sqlite-vec` | Vector search inside the same SQLite file — the brief's "no separate vector service". |
| `nvidia-ml-py` | The maintained `pynvml` package; reads VRAM/util through the WSL2 NVML shim (§1.3). |
| `huggingface-hub` | Resolves and downloads GGUF files with resume + hash verification for `make models`. |
| `psutil` | System RAM / CPU for the HUD, and the WSL cgroup memory ceiling. |
| `uv` (tool) | Fast, lockfile-based env management; no daemon, no telemetry. |

### 6.2 Backend, added at their milestone

| Package | Milestone | Why |
|---|---|---|
| `watchdog` | M4 | Filesystem events, with the `PollingObserver` fallback `/mnt/c` requires. |
| `pymupdf` | M4 | Fast, dependency-light text+offset extraction so RAG citations can point at a real offset. |
| `markdown-it-py` | M4 | Structure-aware Markdown chunking for `./memory/` and notes. |
| `GitPython` | M4 | Auto-commit the memory repo so "diff history" in §4.7 is real git history. |
| `numpy` | M4 | Cosine similarity, RRF fusion, and the agreement matrix — nothing heavier needed. |
| `faster-whisper` | M5 | Streaming local STT that runs at `small`/int8 inside our VRAM budget. |
| `piper-tts` | M5 | CPU-only streaming TTS; leaves the GPU for tokens. |
| `apscheduler` | M6 | Cron-syntax jobs persisted into the same SQLite file, per the brief. |

### 6.3 Dev / test

| Package | Why |
|---|---|
| `pytest`, `pytest-asyncio` | The three test subjects in rule 0.7 are all async-adjacent backend logic. |
| `ruff` | Lint + format in one fast tool, so `make check` stays quick. |
| `mypy` | The Pydantic-as-truth rule is only real if the server side is actually checked. |

### 6.4 Frontend

| Package | Why |
|---|---|
| `react`, `react-dom`, `typescript`, `vite` | The stack the brief specified. |
| `tailwindcss` | Utility CSS; no component library, since §5 is bespoke. |
| `framer-motion` | Spring physics — the only motion primitive §5.4 allows. |
| `three`, `@react-three/fiber` | The GLSL background plane and its half-res render target. |
| `zustand` | Small, un-opinionated store; slices map cleanly onto §5's state machine. |
| `d3-hierarchy` | Tree layout math for the minimap; we render the SVG ourselves. |
| `diff` | Word-level diff for "rerun with…" sibling comparison (§4.5). |
| `openapi-typescript` (dev) | Generates `schema.gen.ts` from OpenAPI — the other half of rule 0.5. |

**Deliberately not included:** no component library, no `axios` (fetch is enough), no charting
library (the HUD and the agreement heatmap are small bespoke SVG), **no frontend test runner** —
rule 0.7 names three test subjects and all three live in the backend, so adding Vitest would be
adding a dependency to test things the brief told me not to test.

**Separate processes, not imports:** `llama.cpp` (MIT, built from source in WSL2 with
`-DGGML_CUDA=ON`) and `SearXNG` (AGPL-3.0, M4, its own venv). Neither is linked into our code, so the
AGPL stays contained to the service; both bind loopback only.

**Telemetry audit (rule 0.11):** at M1 I verify and pin the no-phone-home posture —
`HF_HUB_DISABLE_TELEMETRY=1`, `DO_NOT_TRACK=1`, Vite with no remote fonts or CDN assets, SearXNG
configured with no external metrics. `make check` greps the built frontend bundle for absolute
external URLs and fails if any appear.

---

## 7. Milestones

Every milestone ends with an app you can open at `http://localhost:5173` and actually use (rule
0.2). "Done when" is written as something you can perform, not something I can claim. Each bullet
inside a milestone is a green checkpoint and a commit (rule 0.8).

### M1 — Spine
FastAPI + SSE, llama.cpp provider (+ OpenAI-compatible, Ollama, LM Studio autodetect), migration
001, hardware probe and the VRAM budget math, `make models` end to end, React shell, the shader
background with the idle → thinking → streaming state machine, the edge glow, per-word streaming
text, Performance mode, and the interrupt half of `test_stream_interrupt.py` (stop-and-keep +
reconnect resume).

- **Done when:** you run `make models`, it reads your real VRAM, ranks a shortlist that fits,
  downloads `qwen3:8b`, benches it, and you hold a full conversation while the background sits at
  idle 0.12, springs to thinking, pulses per token during streaming, and Esc stops a generation
  leaving the partial text in place. Refreshing mid-answer reattaches to the live stream.
- **Also done when:** on a deliberately over-committed context you get the preflight sentence with a
  fix button, not an OOM trace.

### M2 — The graph
Migrations 002, DAG module + `test_dag.py`, edit-any-message-including-the-assistant's, sibling
navigation, the minimap, the `ContextAssembler` with real `/tokenize` counts, block toggle / pin /
reorder, loud eviction notices, and `test_context_accounting.py`.

- **Done when:** you fork one conversation three ways — including by editing what the assistant
  said and continuing from your version — switch between branches from the minimap and the
  `‹ 2/4 ›` arrows, and for each branch open the context bar and see the exact block list with real
  token counts, pin one block, drop another, and watch the numbers change before you send.

### M3 — The instrument panel
Migration 003, logprob capture and storage, the x-ray tint layer, the token popover with top-5
alternatives, forced-token truncate-and-resume, live nudge with prefix continuation + inline
markers, deterministic rerun and rerun-with + word diff, the Sovereign HUD, and the nudge/forced-
token half of `test_stream_interrupt.py`.

- **Done when:** you click a token mid-answer, pick the second-most-likely alternative, and watch
  the answer take a different path from that token — and separately, you nudge a running generation
  and it continues from the partial text rather than restarting. Rerun with the same seed produces
  a byte-identical sibling; that's the assertion.
- **Honest note:** on providers reporting `supports_logprobs=False` the x-ray toggle is absent, not
  greyed-out-and-lying. The HUD shows `—` for power/temp if WSL's NVML doesn't expose them (§1.3).

### M4 — Knowledge

**Memory capture mode: settled — auto-extract with visible undo.** Facts are captured after a turn,
written immediately, and reported in a toast that names each one and offers a single click to remove
exactly that batch. Nothing is written unseen. Superseded discussion: §4.7 describes memory as browsable, editable files; it
does not say whether facts are captured automatically. Three options, to settle before M4 starts:
auto-extract with a visible "saved 2 things" marker and one-click undo (recommended); auto-extract
into a review queue that writes nothing unseen; or explicit "remember this" only. Memory is
model-agnostic either way — it enters through the ContextAssembler, so every provider gets it.

Migration 004, watcher (with the `/mnt/c` polling path), chunking with byte offsets, embeddings via
the provider layer, hybrid FTS5 + `sqlite-vec` retrieval with RRF, CPU reranking, memory as
git-backed Markdown with per-entry retrieval stats, retrieval attribution in every answer, native
SearXNG, multi-step research mode.

- **Done when:** you point it at a folder, watch indexing progress (pausable, and it yields to
  generation), ask a question, and click a citation that opens the source file at the right offset —
  and the Memory page lets you edit a fact, see the git diff, and hard-delete one with "Forget this".

### M5 — Plurality and voice
Migration 005, Council fan-out into parallel columns, blind judging (labels A/B/C, model names
stripped before the judge sees anything), agreement matrix heatmap, per-category scoreboard,
faster-whisper STT, Piper TTS, the orb.

- **Reality check for your hardware:** running 3 models concurrently on 8–12GB is not possible.
  The Council on this machine runs **sequentially by default** with a visible queue, and offers
  true concurrency only for providers that don't consume local VRAM (an OpenAI-compatible endpoint,
  or a second machine). The UI is the same; the honesty is in the queue indicator.

### M6 — Autonomy
Migration 006, APScheduler jobs, the agent loop, inbox, the approval-gated tool registry, the
injection boundary in `tools/gate.py`, hash-and-path-only audit log, Obsidian export.

- **Done when:** a scheduled job runs, asks for approval before its first file write, appears in the
  audit log with hashes and paths only, and drops a result into the inbox — and a document
  containing "ignore your instructions" is surfaced to you as flagged data rather than acted on.

---

## 7a. M1 as built: where it diverged from this plan

The plan survived contact, with five changes worth recording.

1. **`chat/run.py` split into `run.py` + `execute.py`, and `cancel.py` became `live.py`.** Generation
   runs as a background task publishing to a subscriber registry rather than inside the HTTP
   handler, so closing the browser does not kill an answer and a reconnect can reattach. Cancellation
   and fan-out need the same registry, so they live in one module instead of sharing state across two.
2. **`providers/httpsse.py` added.** llama.cpp and every OpenAI-compatible backend both parse `data:`
   frames; one parser beats the same ten lines in two adapters.
3. **The context assembler landed in M1, not M2.** The streaming contract says the assembly event
   comes first, always. Shipping M1 without it would have meant a placeholder, which rule 0.3
   forbids. M2 still owns the interactive part: pinning, toggling, reordering and the stacked bar.
   Migration `002_run_assembly.sql` stores the assembly on the run so a reconnect can replay it;
   M2's per-block table becomes migration 003.
4. **`hardware/recommend.py` split into `recommend.py` + `catalog.py`** when `make check` caught it
   at 286 lines, over the 250 limit.
5. **The SSE union is declared in the OpenAPI schema** via a `StreamEnvelope` root model. Without it
   the event shapes never reach the generated TypeScript, and the frontend would have to hand-write
   the one part of the API rule 0.5 most cares about.

### M2 as built

Four more deviations, all recorded rather than quietly taken.

1. **Migration 003 adds no `context_blocks` snapshot table.** M1 already stores the exact assembly
   as JSON on the run, because resume needed it. Exploding the same data into rows would be two
   records of one truth. 003 adds what M2 actually needed: `block_prefs`, because a pin should
   outlive the request that set it.
2. **A new `prefix` block kind.** Continuing an edited turn sends that text through the provider's
   completion endpoint rather than as a chat message, so it never appeared in the block list while
   occupying context exactly like one. The inspector was lying by omission; the prefix is now a
   block with its real token count.
3. **`assemble_preview` moved to `context/preview.py`** when the file-length check caught
   `chat/run.py` at 252 lines.
4. **Continue-from composes a new sibling** holding prefix + continuation, rather than appending to
   the edited node. The edited node survives as "just my edit, no continuation", and the insert-only
   invariant holds. This is why editing then continuing leaves three siblings, not two.

### M3 as built

1. **`chat/steering.py` did not exist in the plan.** Continue, force-token and rerun turned out to
   be one move with three faces — take an existing message, decide how much of its text to keep,
   generate a sibling from there — so they share one resolver instead of three near-identical paths
   through `run.py`.
2. **A nudge is a context block.** It changes what the model was told, so the inspector shows it
   with its token count rather than slipping it in invisibly.
3. **Migration 004 rebuilds the `messages` table** to widen a CHECK constraint, which SQLite cannot
   alter in place. The migration runner now compares row counts before and after every migration
   and fails loudly on loss, because a botched table rebuild is silent and permanent.
4. **`HudSample` and the SSE union are declared as OpenAPI responses** even though both are
   delivered over `text/event-stream`. Without that they never reach the generated TypeScript, and
   the frontend would hand-type the one part of the API rule 0.5 cares most about.
5. **`test_stream_interrupt.py` split into two files** at the 250-line limit. Still one rule 0.7
   subject; stopping/reconnecting and steering/replaying are different responsibilities.

### M4 as built (memory slice)

1. **Migration 005 indexes the files; it is not the store.** `sync()` rescans `./memory/` and makes
   the rows match. If the two ever disagree the directory wins, because memory you cannot read with
   `cat` and delete with `rm` is not memory you own.
2. **Retrieval is FTS5 keyword matching plus everything marked `always`,** not embeddings. That
   needs no model resident in VRAM — which matters on an 8GB card — and is genuinely good over a
   few hundred facts. Its limitation is real and visible: asking "how much VRAM do I have" does not
   match a fact that says "8-12GB NVIDIA card". Vector search joins it in the RAG slice.
3. **A stopword list was necessary.** Without it a question matched any entry sharing a filler
   word; "with" pulled in an unrelated GPU fact during testing.
4. **The capture task is registered before generation, not after.** An earlier version registered
   it once `execute()` returned, which raced the `done` event the client waits on: the client could
   ask for its batch before the entry existed and be told, wrongly, that nothing was captured.
5. **Captured facts are deduplicated by content hash.** Facts recur across turns, so without it the
   store fills with near-duplicates of the same preference.
6. **Memory crosses the prompt-injection boundary like any retrieved text.** Auto-captured facts are
   derived from model output, which a poisoned document can influence, so they are wrapped as data
   with provenance rather than trusted as instructions. There is a test for exactly this.

### M4 as built (RAG slice)

1. **The vector table is created on first index, not by a migration.** sqlite-vec needs the
   embedding dimension up front and that is a property of the model, not the schema. The dimension
   and model id are recorded, so switching embedding model is *detected* and forces a reindex
   rather than silently comparing vectors from two different spaces.
2. **RRF rather than blended scores.** BM25 and cosine distance are not on the same scale, and
   normalising them means inventing a conversion. Ranks are comparable by construction. Every hit
   records which retrievers found it, so fusion stays inspectable.
3. **Short sections are merged forward, never dropped.** The first chunker dropped anything under
   the size floor, which silently made a file of brief notes unsearchable. Caught by running it on
   a three-section document and getting one chunk back.
4. **`context/blocks.py` was split out of the assembler** at the 250-line limit: the assembler owns
   ordering, budget and accounting; the builders own what a block of each kind looks like.
5. **`/api/knowledge/open` only reads files this app indexed.** It resolves `path#start-end` back
   to bytes on disk, so it is checked against the `documents` table first - otherwise a crafted
   reference would be an arbitrary file read.

### M4 as built (search slice)

1. **SearXNG runs native, never imported.** `make searxng` clones it into `services/searxng/` with
   its own venv and writes a `settings.yml` that enables the JSON format (off upstream, and this
   app needs it). Keeping it at arm's length keeps its AGPL-3.0 licence off our code, and a
   non-loopback search URL is refused for the same reason the inference port is.
2. **Snippets only, by default.** Fetching a result would contact that site directly and undo the
   privacy running your own SearXNG buys. `search.fetch_pages` exists, is off, and says what it
   costs.
3. **Queries are deduplicated across rounds.** Models repeat themselves; without this a later round
   re-runs earlier queries and spends itself on results already in hand. Caught by watching round
   two search exactly what round one had.
4. **Web results are their own block kind.** Not `rag`: the provenance and the trust boundary both
   differ, and the open web is the least trustworthy input this app has. They reach the model
   wrapped as data with their URL, and there is a test asserting a hostile snippet never arrives as
   a system instruction.

**Not done, and not pretended: reranking.** §4.8 calls for `bge-reranker` after fusion. It needs a
cross-encoder resident in memory, and shipping an adapter I cannot exercise here would be exactly
the half-wired path rule 0.3 forbids. Fusion works without it; this is a quality improvement for
when there is a model to test against.

**One known gap.** The frontend's SSE frame parser is part of the streaming path that rule 0.7 says
to test, but there is no frontend test runner — deliberately, since all three test subjects were
meant to be backend logic. A CRLF bug in that parser got through to a browser and was caught by
hand: every live event silently failed to parse while the app still looked correct, because the
transcript refreshes from the database when a stream closes. `test_stream_interrupt.py` now pins the
wire format from the backend side, but that would not have caught this. Adding Vitest for that one
pure function needs your approval under rule 0.4 — I recommend it.

---

## 8. Tests, checks, and the Makefile

### 8.1 Exactly three test subjects (rule 0.7)

| File | What it pins down |
|---|---|
| `tests/test_dag.py` | fork-on-edit creates a sibling and destroys nothing; `path_to_leaf` is the reversed ancestor chain; sibling ordering is stable; deep chains don't recurse to death; merge records provenance and keeps the tree acyclic. |
| `tests/test_context_accounting.py` | assembled token total equals the provider's own count of the final prompt (the bug that otherwise silently truncates); pinned blocks survive eviction and unpinned ones don't; every eviction emits a notice; toggling and reordering change the total in the expected direction. |
| `tests/test_stream_interrupt.py` | stop keeps the partial and marks `stop_reason`; reconnect with `Last-Event-ID` replays exactly the missing tokens with no duplicates or gaps; a nudge aborts, persists the partial, and resumes with the partial as prefix; forced-token truncates at the byte offset and continues; a provider dying mid-stream leaves a `stopped` row, never a half-written one. |

All three run against a **fake provider with a scripted token stream** (`tests/conftest.py`) — no
model, no GPU, so `make check` is fast and runs in CI on this repo's existing runners.

### 8.2 `make check` also enforces the non-code requirements

- `ruff` + `mypy` + `pytest`.
- **Type drift:** regenerate `schema.gen.ts` from OpenAPI; fail if it differs (rule 0.5).
- **File length:** fail on any source file over 250 lines (rule 0.6) — a lint rule, not a habit.
- **Contrast:** `scripts/contrast_check.py` renders the shader's extreme frames headless and asserts
  body text ≥ 4.5:1 against the brightest pixel it can actually produce (§5.5) — testing the
  shader's real extremes, not a screenshot.
- **No phone-home:** grep the built bundle for external absolute URLs (rule 0.11).

### 8.3 Makefile

```
make dev      # migrate → start llama.cpp (if configured) → uvicorn on 127.0.0.1:8080 → vite
make check    # ruff, mypy, pytest, type-drift, file-length, contrast, no-phone-home
make models   # probe VRAM → ranked shortlist with real sizes → download → bench → register
make bench    # measure background+glow GPU cost against the 3% cap (§5.6); prints pass/fail
make types    # regenerate schema.gen.ts (make check verifies it, this writes it)
```

`make dev`, `make check`, `make models` are the three the brief requires; `bench` and `types` exist
because §5.6 and rule 0.5 need a command you can run, not a paragraph you can read.

### 8.4 Section 5 acceptance criteria (it's a requirement, so it gets tested like one)

| Criterion | How it's verified |
|---|---|
| Background + glow < 3% GPU while generating | `make bench` samples `nvidia-smi dmon` with generation running, shader on then off; the delta is the number, and it's printed in the README. |
| 30fps cap while streaming, 60 idle, demand after 20s | Frame counter asserted in `perf.ts` and shown in a dev overlay. |
| Half-res FBO | Render target size assertion in the dev overlay. |
| Energy transitions are springs, never steps | `energy.ts` exposes the spring; a step change is a lint-level mistake, and the dev overlay plots `uEnergy` so you can see it settle. |
| `prefers-reduced-motion` | Static gradient, instant transitions, orb → pulse dot; checked with the media query forced on. |
| Contrast ≥ 4.5:1 | `scripts/contrast_check.py` in `make check`. |
| VRAM cost of the shader | Measured at startup and shown in the HUD next to the model's usage — the two roommates, side by side. |

---

## 9. Security posture (brief §7), as concrete invariants

1. **Bind guard.** `settings.py` refuses to start if `host` is non-loopback and no auth is
   configured. Not a warning — a startup failure with the reason printed.
2. **Inference ports stay loopback.** `make dev` starts llama.cpp with `--host 127.0.0.1`; the
   registry refuses to register a local provider URL that isn't loopback unless you set an explicit
   override flag.
3. **Tools are gated by default (M6).** Shell, file write, and network POST require per-call
   approval until you allowlist them per project; grants live in `tool_grants` and are visible and
   revocable in the UI.
4. **Audit log stores hashes and paths, never contents or secrets.** Enforced at the writer, so
   there's one place to review.
5. **Retrieved text is data.** Wrapped with provenance in the assembler; tool dispatch only ever
   reads the model's output channel. A document that tries to give instructions gets flagged and
   shown to you.
6. **No telemetry, verified by `make check`,** not by assumption.

---

## 10. What I need from you

1. **Approve or amend §6 (dependencies).** That list is the contract for the rest of the project.
2. **Placement (settled):** the repo layout in section 0 (now standalone, code at root).
3. **One number would sharpen §1:** is the card 8GB or 12GB? Both work, but 8GB means 16K context by
   default and Performance mode on by default, while 12GB means 32K and the full shader. I'll build
   the runtime detection either way — this only changes which defaults ship.

Nothing else is blocking. On approval I start M1 and stop at the first green checkpoint.
