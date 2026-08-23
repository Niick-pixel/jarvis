-- M3: the instrument panel. Nudges land on a message, and forked_reason gains 'nudge'.
--
-- SQLite cannot alter a CHECK constraint, so the messages table is rebuilt by the documented
-- procedure. Foreign keys are disabled for the swap and re-enabled after; the copy is verified by
-- the migration runner, which fails loudly rather than leaving a half-migrated table.

PRAGMA foreign_keys=off;

CREATE TABLE messages_new (
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
  forked_reason   TEXT CHECK (forked_reason IN ('edit','rerun','forced_token','merge','nudge')),
  created_at      INTEGER NOT NULL,
  provenance_json TEXT
);

INSERT INTO messages_new
  SELECT id, conversation_id, parent_id, role, content, model_id, params_json, token_count,
         status, edited_from_id, forked_reason, created_at, provenance_json
  FROM messages;

DROP TABLE messages;
ALTER TABLE messages_new RENAME TO messages;

CREATE INDEX idx_messages_conv   ON messages(conversation_id, created_at);
CREATE INDEX idx_messages_parent ON messages(parent_id);

PRAGMA foreign_keys=on;

-- Where an interjection landed, so the transcript stays honest about what happened mid-answer.
CREATE TABLE nudges (
  id         TEXT PRIMARY KEY,
  message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  token_idx  INTEGER NOT NULL,
  text       TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX idx_nudges_message ON nudges(message_id);
