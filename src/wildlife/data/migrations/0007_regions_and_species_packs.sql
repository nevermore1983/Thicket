-- Migration 0007 (regions, version 1.1): species packs for more than the UK.
-- Plan: docs/16-regions-plan.md.
--
-- A species pack is a list of species for one region ("uk", "us-ca"...): the UK
-- Species Inventory built in, or a downloaded pack from GBIF for a US state. Packs only
-- add. A species already in your list (same accepted scientific name) is linked, never
-- copied, so a life list can't count it twice. Each region keeps its own common names
-- and suggestion order; choosing a region copies its ones into `taxon` (so every screen
-- shows them without changing).

-- The key a species was first added with: a UKSI key as before ("NHMSYS0000530674"),
-- or a GBIF key ("gbif:2490384"). Renaming keeps the rule that every catalogue species
-- has one (the CHECK constraint follows the rename).
ALTER TABLE taxon RENAME COLUMN uksi_key TO catalogue_key;

-- Every key a species is known by, from every pack: Red Fox has its UKSI key and its
-- GBIF key here, both pointing at the one species.
CREATE TABLE taxon_key (
    key       TEXT    PRIMARY KEY,                -- 'NHMSYS…' (UKSI) or 'gbif:2490384'
    taxon_id  INTEGER NOT NULL REFERENCES taxon (id) ON DELETE CASCADE
) STRICT, WITHOUT ROWID;
CREATE INDEX taxon_key_taxon ON taxon_key (taxon_id);
INSERT INTO taxon_key (key, taxon_id)
    SELECT catalogue_key, id FROM taxon WHERE catalogue_key IS NOT NULL;

-- Per region: how commonly a species is recorded there (suggestion order) and its
-- common name there ("Starling" in the UK, "European Starling" in the US).
CREATE TABLE taxon_region (
    region       TEXT    NOT NULL,                -- 'uk', 'us-ca', ...
    taxon_id     INTEGER NOT NULL REFERENCES taxon (id) ON DELETE CASCADE,
    priority     INTEGER NOT NULL DEFAULT 0,
    common_name  TEXT,
    PRIMARY KEY (region, taxon_id)
) STRICT, WITHOUT ROWID;
CREATE INDEX taxon_region_taxon ON taxon_region (taxon_id);
INSERT INTO taxon_region (region, taxon_id, priority, common_name)
    SELECT 'uk', id, priority, common_name FROM taxon WHERE catalogue_key IS NOT NULL;

-- The packs installed.
CREATE TABLE species_pack (
    region        TEXT    PRIMARY KEY,            -- 'uk', 'us-ca'
    name          TEXT    NOT NULL,               -- 'United Kingdom', 'California'
    source        TEXT    NOT NULL,               -- 'uksi', 'gbif'
    version       TEXT    NOT NULL,
    taxa          INTEGER NOT NULL DEFAULT 0,
    installed_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
) STRICT;
INSERT INTO species_pack (region, name, source, version, taxa)
    SELECT 'uk', 'United Kingdom', 'uksi', value,
           (SELECT COUNT(*) FROM taxon WHERE catalogue_key IS NOT NULL)
    FROM app_meta WHERE key = 'catalogue_version';

-- Which pack each searchable name came from, so updating one pack replaces only its
-- own names (NULL: a name you added, on a species you created).
ALTER TABLE taxon_name ADD COLUMN pack TEXT;
UPDATE taxon_name SET pack = 'uk'
    WHERE taxon_id IN (SELECT id FROM taxon WHERE catalogue_key IS NOT NULL);

-- The region whose names and suggestion order `taxon` shows now
INSERT OR IGNORE INTO app_meta (key, value) VALUES ('region', 'uk');
