-- Migration 0009 (version 1.5.0): outings made by an import remember where they came from.
--
-- An eBird checklist becomes an outing (its date, times, place and comments), and the
-- checklist's id is kept here, so importing a newer download later uses the same outing
-- instead of making a second one. NULL for outings you made yourself.
ALTER TABLE outing ADD COLUMN source TEXT;     -- 'ebird'
ALTER TABLE outing ADD COLUMN source_id TEXT;  -- the checklist's id, 'S340879334'
CREATE UNIQUE INDEX outing_source ON outing (source, source_id) WHERE source_id IS NOT NULL;
