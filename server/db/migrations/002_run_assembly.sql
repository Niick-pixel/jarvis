-- The exact context assembly that produced a run, stored so a reconnect can replay it and so
-- "what went into this answer" survives a restart. M2 explodes this into per-block rows for the
-- interactive inspector; the snapshot on the run is what makes resume honest in the meantime.
ALTER TABLE runs ADD COLUMN assembly_json TEXT;
