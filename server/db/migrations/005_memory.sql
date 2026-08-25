-- M4: memory. The Markdown files under ./memory/ are the truth; this is an index over them.
--
-- Everything here can be rebuilt by rescanning the directory, which is the point: if this table
-- and the files ever disagree, the files win and the index is regenerated. Memory you cannot read
-- with `cat` and delete with `rm` is not memory you own.

CREATE TABLE memory_entries (
  id           TEXT PRIMARY KEY,
  path         TEXT NOT NULL UNIQUE,   -- relative to ./memory/
  scope        TEXT NOT NULL CHECK (scope IN ('global','project','conversation')),
  scope_ref    TEXT,                   -- project id or conversation id; NULL for global
  title        TEXT NOT NULL DEFAULT '',
  content      TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  always       INTEGER NOT NULL DEFAULT 0,  -- injected regardless of relevance
  source       TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','auto')),
  batch_id     TEXT,                   -- groups one auto-extraction, so undo removes exactly it
  created_at   INTEGER NOT NULL,
  updated_at   INTEGER NOT NULL
);
CREATE INDEX idx_memory_scope ON memory_entries(scope, scope_ref);
CREATE INDEX idx_memory_batch ON memory_entries(batch_id);

-- Keyword retrieval without loading an embedding model. Vector search joins it in the RAG slice.
CREATE VIRTUAL TABLE memory_fts USING fts5(
  title, content, content=memory_entries, content_rowid=rowid, tokenize='porter unicode61'
);

CREATE TRIGGER memory_fts_insert AFTER INSERT ON memory_entries BEGIN
  INSERT INTO memory_fts(rowid, title, content) VALUES (new.rowid, new.title, new.content);
END;
CREATE TRIGGER memory_fts_delete AFTER DELETE ON memory_entries BEGIN
  INSERT INTO memory_fts(memory_fts, rowid, title, content)
    VALUES('delete', old.rowid, old.title, old.content);
END;
CREATE TRIGGER memory_fts_update AFTER UPDATE ON memory_entries BEGIN
  INSERT INTO memory_fts(memory_fts, rowid, title, content)
    VALUES('delete', old.rowid, old.title, old.content);
  INSERT INTO memory_fts(rowid, title, content) VALUES (new.rowid, new.title, new.content);
END;

-- Every injection, so "retrieved 14 times, last used 3 days ago" is counted rather than guessed.
CREATE TABLE memory_usage (
  entry_id   TEXT NOT NULL REFERENCES memory_entries(id) ON DELETE CASCADE,
  message_id TEXT NOT NULL,
  used_at    INTEGER NOT NULL
);
CREATE INDEX idx_memory_usage_entry ON memory_usage(entry_id, used_at);
