-- M5: the Council. One question, several models, a blind judge.
--
-- `label` lives on the answer, separate from `model_id`, because the judge must never see who
-- wrote what. Keeping them in different columns is what makes blindness structural rather than a
-- promise: the judge query selects label and content, and cannot select a name it never joined to.

CREATE TABLE council_runs (
  id              TEXT PRIMARY KEY,
  conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
  question        TEXT NOT NULL,
  rubric          TEXT NOT NULL DEFAULT '',
  category        TEXT NOT NULL DEFAULT 'general',
  judge_model_id  TEXT,
  mode            TEXT NOT NULL DEFAULT 'sequential' CHECK (mode IN ('sequential','mixed')),
  synthesis       TEXT NOT NULL DEFAULT '',
  disagreements   TEXT NOT NULL DEFAULT '',
  created_at      INTEGER NOT NULL,
  finished_at     INTEGER
);

CREATE TABLE council_answers (
  id         TEXT PRIMARY KEY,
  run_id     TEXT NOT NULL REFERENCES council_runs(id) ON DELETE CASCADE,
  label      TEXT NOT NULL,           -- A, B, C ... all the judge ever sees
  model_id   TEXT NOT NULL,
  ord        INTEGER NOT NULL,
  content    TEXT NOT NULL DEFAULT '',
  gen_tokens INTEGER NOT NULL DEFAULT 0,
  gen_ms     INTEGER NOT NULL DEFAULT 0,
  error      TEXT
);
CREATE INDEX idx_council_answers_run ON council_answers(run_id, ord);

CREATE TABLE council_ranking (
  run_id TEXT NOT NULL REFERENCES council_runs(id) ON DELETE CASCADE,
  label  TEXT NOT NULL,
  rank   INTEGER NOT NULL,
  reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_council_ranking_run ON council_ranking(run_id);

-- Pairwise cosine similarity between answers. Unanimity is a weak signal; a split is the
-- interesting case, so the numbers are stored rather than recomputed for display.
CREATE TABLE council_agreement (
  run_id     TEXT NOT NULL REFERENCES council_runs(id) ON DELETE CASCADE,
  a_label    TEXT NOT NULL,
  b_label    TEXT NOT NULL,
  similarity REAL NOT NULL
);
CREATE INDEX idx_council_agreement_run ON council_agreement(run_id);

CREATE TABLE model_scores (
  model_id    TEXT NOT NULL,
  category    TEXT NOT NULL,
  wins        INTEGER NOT NULL DEFAULT 0,
  appearances INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (model_id, category)
) WITHOUT ROWID;
