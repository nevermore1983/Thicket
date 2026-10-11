-- Migration 0002: app metadata and species-catalogue details.
-- (Written in Phase 6 once the real UK Species Inventory had been examined.)

-- Small key/value store for app-managed facts (not user preferences),
-- e.g. which species-catalogue version is installed.
CREATE TABLE app_meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
) STRICT, WITHOUT ROWID;

-- UKSI's informal group ("bird", "insect - moth", ...) and non-native flag.
ALTER TABLE taxon ADD COLUMN informal_group TEXT;
ALTER TABLE taxon ADD COLUMN is_non_native INTEGER NOT NULL DEFAULT 0 CHECK (is_non_native IN (0, 1));

-- The picker looks species up by name prefix (1-2 letters) without the trigram index.
CREATE INDEX taxon_common ON taxon (common_name COLLATE NOCASE);
