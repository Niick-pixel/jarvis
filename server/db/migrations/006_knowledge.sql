-- M4: RAG over your own disk.
--
-- The vector table is NOT created here. sqlite-vec needs the embedding dimension up front, and the
-- dimension depends on which model you run - so it is created on first index and recorded in
-- settings. Changing embedding model changes the dimension, which forces a reindex, and the code
-- says so rather than silently comparing incompatible vectors.

CREATE TABLE sources (
  id            TEXT PRIMARY KEY,
  path          TEXT NOT NULL UNIQUE,   -- absolute path to a watched folder or file
  kind          TEXT NOT NULL CHECK (kind IN ('folder','file')),
  observer      TEXT NOT NULL DEFAULT 'native' CHECK (observer IN ('native','polling')),
  -- Windows drives under /mnt/c do not deliver inotify events; those get polled instead.
  enabled       INTEGER NOT NULL DEFAULT 1,
  file_count    INTEGER NOT NULL DEFAULT 0,
  chunk_count   INTEGER NOT NULL DEFAULT 0,
  last_indexed  INTEGER,
  created_at    INTEGER NOT NULL
);

CREATE TABLE documents (
  id           TEXT PRIMARY KEY,
  source_id    TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  path         TEXT NOT NULL UNIQUE,
  content_hash TEXT NOT NULL,   -- skip re-chunking a file that has not changed
  mtime_ms     INTEGER NOT NULL,
  size_bytes   INTEGER NOT NULL,
  indexed_at   INTEGER
);
CREATE INDEX idx_documents_source ON documents(source_id);

CREATE TABLE chunks (
  id          TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  ord         INTEGER NOT NULL,
  heading     TEXT NOT NULL DEFAULT '',
  text        TEXT NOT NULL,
  byte_start  INTEGER NOT NULL,   -- so a citation opens the file at the right place
  byte_end    INTEGER NOT NULL,
  token_count INTEGER NOT NULL DEFAULT 0,
  embedded    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_chunks_document ON chunks(document_id, ord);
CREATE INDEX idx_chunks_embedded ON chunks(embedded);

CREATE VIRTUAL TABLE chunks_fts USING fts5(
  heading, text, content=chunks, content_rowid=rowid, tokenize='porter unicode61'
);
CREATE TRIGGER chunks_fts_insert AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, heading, text) VALUES (new.rowid, new.heading, new.text);
END;
CREATE TRIGGER chunks_fts_delete AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, heading, text)
    VALUES('delete', old.rowid, old.heading, old.text);
END;
CREATE TRIGGER chunks_fts_update AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, heading, text)
    VALUES('delete', old.rowid, old.heading, old.text);
  INSERT INTO chunks_fts(rowid, heading, text) VALUES (new.rowid, new.heading, new.text);
END;
