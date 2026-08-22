-- M1 core: conversations, the message DAG, reproducible runs, known models, settings.

CREATE TABLE conversations (
  id             TEXT PRIMARY KEY,
  title          TEXT NOT NULL DEFAULT '',
  project_id     TEXT,
  active_leaf_id TEXT,
  system_prompt  TEXT NOT NULL DEFAULT '',
  visual_preset  TEXT NOT NULL DEFAULT 'aurora',
  created_at     INTEGER NOT NULL,
  updated_at     INTEGER NOT NULL
);

-- Insert-only, apart from streaming content/status on a run in flight.
-- Edits never mutate: they insert a sibling. Nothing is ever destroyed (BRIEF.md 4.1).
CREATE TABLE messages (
  id              TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  parent_id       TEXT REFERENCES messages(id) ON DELETE CASCADE,
  role            TEXT NOT NULL CHECK (role IN ('system','user','assistant','tool')),
  content         TEXT NOT NULL,
  model_id        TEXT,
  params_json     TEXT,
  token_count     INTEGER NOT NULL DEFAULT 0,
  status          TEXT NOT NULL DEFAULT 'complete'
                  CHECK (status IN ('streaming','complete','stopped','error')),
  edited_from_id  TEXT REFERENCES messages(id),
  forked_reason   TEXT CHECK (forked_reason IN ('edit','rerun','forced_token','merge')),
  created_at      INTEGER NOT NULL
);
CREATE INDEX idx_messages_conv   ON messages(conversation_id, created_at);
CREATE INDEX idx_messages_parent ON messages(parent_id);

-- Everything needed to reproduce an assistant message exactly (BRIEF.md 4.5).
CREATE TABLE runs (
  id             TEXT PRIMARY KEY,
  message_id     TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  model_id       TEXT NOT NULL,
  model_sha256   TEXT NOT NULL DEFAULT '',
  seed           INTEGER NOT NULL,
  temperature    REAL NOT NULL,
  top_p          REAL NOT NULL,
  top_k          INTEGER NOT NULL,
  repeat_penalty REAL NOT NULL,
  ctx_len        INTEGER NOT NULL,
  prompt_tokens  INTEGER,
  gen_tokens     INTEGER,
  prompt_eval_ms INTEGER,
  gen_ms         INTEGER,
  stop_reason    TEXT,
  parent_run_id  TEXT REFERENCES runs(id),
  created_at     INTEGER NOT NULL
);
CREATE INDEX idx_runs_message ON runs(message_id);

-- Token log. Written as tokens arrive so an interrupted run is resumable and inspectable,
-- and so the M3 x-ray can tint a message generated weeks ago.
CREATE TABLE run_tokens (
  run_id     TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  idx        INTEGER NOT NULL,
  text       TEXT NOT NULL,
  logprob    REAL,
  top_json   TEXT,
  byte_start INTEGER NOT NULL,
  byte_end   INTEGER NOT NULL,
  timing_ms  REAL,
  PRIMARY KEY (run_id, idx)
) WITHOUT ROWID;

CREATE TABLE models (
  id                TEXT PRIMARY KEY,
  provider          TEXT NOT NULL,
  display_name      TEXT NOT NULL,
  file_path         TEXT,
  sha256            TEXT,
  quant             TEXT,
  size_bytes        INTEGER,
  ctx_len_max       INTEGER NOT NULL,
  n_layers          INTEGER,
  n_kv_heads        INTEGER,
  head_dim          INTEGER,
  supports_logprobs INTEGER NOT NULL DEFAULT 0,
  supports_prefix   INTEGER NOT NULL DEFAULT 0,
  bench_gen_tps     REAL,
  bench_prompt_tps  REAL,
  last_seen_at      INTEGER
);

CREATE TABLE settings (
  key        TEXT PRIMARY KEY,
  value_json TEXT NOT NULL
);

-- Lifetime counters for the Sovereign HUD (BRIEF.md 4.10). Incremented per completed run.
CREATE TABLE counters (
  key   TEXT PRIMARY KEY,
  value REAL NOT NULL DEFAULT 0
);
