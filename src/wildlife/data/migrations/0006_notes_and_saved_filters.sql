-- Migration 0006 (Phase 12): your notes on a species, and filters you've saved by name.

-- Notes about a species as a whole ("Nests in the ivy by the shed every year").
CREATE TABLE species_note (
    taxon_id    INTEGER PRIMARY KEY REFERENCES taxon (id) ON DELETE CASCADE,
    notes       TEXT    NOT NULL CHECK (length(notes) <= 10000),
    updated_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
) STRICT, WITHOUT ROWID;

-- A filter saved under a name ("My moth-trap nights"), stored as JSON so new filter
-- options don't need a new column.
CREATE TABLE saved_filter (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL COLLATE NOCASE UNIQUE CHECK (length(name) BETWEEN 1 AND 80),
    filter      TEXT    NOT NULL CHECK (json_valid(filter)),
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
) STRICT;
