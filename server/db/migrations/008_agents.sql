-- M6: ambient agents, and the gate every side effect passes through.
--
-- Two records of a tool call exist here on purpose, and they are not duplicates:
--   tool_calls  is operational state - it holds the real arguments, because a call approved now
--               has to be executed later, and you cannot execute a hash.
--   audit_log   is the permanent record, written by one function that hashes arguments and keeps
--               only paths and hosts (BRIEF.md 7). Contents never reach it.
-- The first is deleted with its job run; the second outlives everything.

CREATE TABLE jobs (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  cron        TEXT NOT NULL,
  prompt      TEXT NOT NULL,
  tools       TEXT NOT NULL DEFAULT '[]',
  -- The tools this job may ask for. A job cannot widen its own set at runtime.
  workspace   TEXT NOT NULL DEFAULT '',
  -- The one directory its file writes may touch. Empty means the job cannot write at all.
  enabled     INTEGER NOT NULL DEFAULT 1,
  created_at  INTEGER NOT NULL,
  last_run_at INTEGER
);

CREATE TABLE job_runs (
  id          TEXT PRIMARY KEY,
  job_id      TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
  -- Every job run is an ordinary conversation, so the transcript, the x-ray and the context
  -- inspector all work on it. An agent you cannot read is an agent you cannot trust.
  status      TEXT NOT NULL CHECK (status IN
                ('running','waiting_approval','done','failed','cancelled')),
  started_at  INTEGER NOT NULL,
  finished_at INTEGER,
  steps       INTEGER NOT NULL DEFAULT 0,
  summary     TEXT NOT NULL DEFAULT '',
  error       TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_job_runs_job ON job_runs(job_id, started_at DESC);

CREATE TABLE tool_calls (
  id          TEXT PRIMARY KEY,
  job_run_id  TEXT REFERENCES job_runs(id) ON DELETE CASCADE,
  tool        TEXT NOT NULL,
  args_json   TEXT NOT NULL,
  target      TEXT NOT NULL DEFAULT '',
  -- The path or host this call touches: the one thing the approval card must show plainly.
  status      TEXT NOT NULL CHECK (status IN ('pending','approved','denied','ran','failed')),
  delivered   INTEGER NOT NULL DEFAULT 0,
  -- Whether this call's outcome has been handed back to the model yet. The whole loop is
  -- resumable because of this column: after a restart, the rows say exactly what is outstanding.
  created_at  INTEGER NOT NULL,
  decided_at  INTEGER,
  result      TEXT NOT NULL DEFAULT '',
  error       TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_tool_calls_status ON tool_calls(status, created_at);

CREATE TABLE tool_grants (
  tool       TEXT NOT NULL,
  scope      TEXT NOT NULL,
  -- A path prefix. Grants are always scoped: "always allow" means "here", never "everywhere".
  created_at INTEGER NOT NULL,
  PRIMARY KEY (tool, scope)
) WITHOUT ROWID;

CREATE TABLE audit_log (
  id          TEXT PRIMARY KEY,
  at          INTEGER NOT NULL,
  actor       TEXT NOT NULL,
  tool        TEXT NOT NULL,
  outcome     TEXT NOT NULL,
  target      TEXT NOT NULL DEFAULT '',
  args_hash   TEXT NOT NULL DEFAULT '',
  result_hash TEXT NOT NULL DEFAULT '',
  bytes       INTEGER NOT NULL DEFAULT 0,
  note        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_audit_at ON audit_log(at DESC);

CREATE TABLE inbox (
  id         TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL,
  job_run_id TEXT REFERENCES job_runs(id) ON DELETE CASCADE,
  title      TEXT NOT NULL,
  body       TEXT NOT NULL,
  flags      TEXT NOT NULL DEFAULT '[]',
  -- Why this item wants your eyes: ["injection"] when a document tried to give instructions.
  read_at    INTEGER
);
CREATE INDEX idx_inbox_created ON inbox(created_at DESC);
