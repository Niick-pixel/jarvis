-- M2: the interactive parts of the graph and the context inspector.
--
-- There is no per-block snapshot table here: M1 already stores the exact assembly as JSON on the
-- run, because a reconnect needed to replay it. Exploding the same data into rows would give two
-- records of one truth. What M2 does need is the *preferences* - which blocks you pinned or
-- switched off - because those outlive any single request.

CREATE TABLE block_prefs (
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  source_ref      TEXT NOT NULL,   -- message id, memory entry, file:offset
  pinned          INTEGER NOT NULL DEFAULT 0,
  disabled        INTEGER NOT NULL DEFAULT 0,
  ord             INTEGER,         -- NULL keeps natural conversation order
  PRIMARY KEY (conversation_id, source_ref)
) WITHOUT ROWID;

-- Where a merged message's spans came from, so a composed leaf can say what it is made of.
ALTER TABLE messages ADD COLUMN provenance_json TEXT;
