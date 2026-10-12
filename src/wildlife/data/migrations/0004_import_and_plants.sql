-- Migration 0004 (Phase 11): plants and fungi, merged categories, and imports.

-- ---------------------------------------------------------------------------
-- Categories: the catalogue now covers plants and fungi as well as animals.
-- There are still 8 colour slots (the validated, colour-blind-safe set), so
-- groups were merged rather than adding a 9th colour. Colours stay with
-- their slot; only the names, icons and rules change.
-- ---------------------------------------------------------------------------
UPDATE category SET name = 'Reptile, amphibian & fish', icon = 'frog'   WHERE id = 3;
UPDATE category SET name = 'Plant',                     icon = 'sprout' WHERE id = 6;
UPDATE category SET name = 'Insect & other invertebrate', icon = 'bug'  WHERE id = 7;
UPDATE category SET name = 'Fungus & lichen',           icon = 'mushroom' WHERE id = 8;

DELETE FROM category_rule;
INSERT INTO category_rule (category_id, taxon_name) VALUES
    (7, 'Animalia'),            -- any animal not matched below
    (9, 'Chordata'),            -- vertebrates and relatives not matched below
    (1, 'Aves'),
    (2, 'Mammalia'),
    (3, 'Reptilia'), (3, 'Amphibia'),
    (3, 'Actinopterygii'), (3, 'Actinopteri'), (3, 'Chondrichthyes'), (3, 'Elasmobranchii'),
    (3, 'Holocephali'), (3, 'Cephalaspidomorphi'), (3, 'Petromyzonti'), (3, 'Myxini'), (3, 'Pisces'),
    (4, 'Lepidoptera'),
    (5, 'Odonata'),
    (6, 'Plantae'),
    (8, 'Fungi');

-- Re-sort every species the user hasn't placed by hand (same rule as the catalogue install).
UPDATE taxon SET category_id = COALESCE(
    (SELECT category_id FROM category_rule WHERE taxon_name = taxon.tax_family),
    (SELECT category_id FROM category_rule WHERE taxon_name = taxon.tax_order),
    (SELECT category_id FROM category_rule WHERE taxon_name = taxon.tax_class),
    (SELECT category_id FROM category_rule WHERE taxon_name = taxon.tax_phylum),
    (SELECT category_id FROM category_rule WHERE taxon_name = taxon.tax_kingdom),
    (SELECT id FROM category WHERE is_fallback = 1))
WHERE category_is_manual = 0;

-- ---------------------------------------------------------------------------
-- Imports: each run of an import is a batch, so it can be undone as a whole,
-- and each imported sighting remembers where it came from, so importing the
-- same file again never creates duplicates.
-- ---------------------------------------------------------------------------
CREATE TABLE import_batch (
    id            INTEGER PRIMARY KEY,
    source        TEXT    NOT NULL,                 -- 'inaturalist', 'csv', ...
    file_name     TEXT,
    imported_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    added         INTEGER NOT NULL DEFAULT 0,
    updated       INTEGER NOT NULL DEFAULT 0,
    skipped       INTEGER NOT NULL DEFAULT 0
) STRICT;

ALTER TABLE sighting ADD COLUMN source            TEXT;   -- NULL = recorded in WildLife
ALTER TABLE sighting ADD COLUMN source_id         TEXT;   -- e.g. the iNaturalist observation id
ALTER TABLE sighting ADD COLUMN source_updated_at TEXT;   -- the source's own "last changed"
ALTER TABLE sighting ADD COLUMN import_batch_id   INTEGER REFERENCES import_batch (id) ON DELETE SET NULL;

-- 1 once you change an imported sighting in WildLife: a later import then never overwrites it.
ALTER TABLE sighting ADD COLUMN source_edited     INTEGER NOT NULL DEFAULT 0 CHECK (source_edited IN (0, 1));

CREATE UNIQUE INDEX sighting_source ON sighting (source, source_id) WHERE source_id IS NOT NULL;
CREATE INDEX sighting_batch ON sighting (import_batch_id) WHERE import_batch_id IS NOT NULL;

-- Any real change to an imported sighting's details marks it as edited. (The importer
-- clears the mark again after it updates a sighting itself.)
CREATE TRIGGER sighting_source_edited AFTER UPDATE ON sighting
WHEN new.source IS NOT NULL AND new.source_edited = 0 AND (
       old.taxon_id IS NOT new.taxon_id OR old.observed_date IS NOT new.observed_date
    OR old.observed_time IS NOT new.observed_time OR old.place_id IS NOT new.place_id
    OR old.latitude IS NOT new.latitude OR old.longitude IS NOT new.longitude
    OR old.uncertainty_m IS NOT new.uncertainty_m OR old.location_text IS NOT new.location_text
    OR old.count IS NOT new.count OR old.count_qualifier IS NOT new.count_qualifier
    OR old.evidence IS NOT new.evidence OR old.identification IS NOT new.identification
    OR old.sex IS NOT new.sex OR old.life_stage IS NOT new.life_stage
    OR old.habitat IS NOT new.habitat OR old.is_not_wild IS NOT new.is_not_wild
    OR old.outing_id IS NOT new.outing_id OR old.notes IS NOT new.notes)
BEGIN
    UPDATE sighting SET source_edited = 1 WHERE id = new.id;
END;

-- Photos fetched from a website remember which photo they were, so they aren't fetched twice.
ALTER TABLE photo ADD COLUMN source    TEXT;
ALTER TABLE photo ADD COLUMN source_id TEXT;
CREATE UNIQUE INDEX photo_source ON photo (source, source_id) WHERE source_id IS NOT NULL;

-- Names from another app that the user matched to a species by hand, remembered
-- for next time (e.g. iNaturalist's "Argentina anserina" -> Silverweed).
CREATE TABLE name_match (
    source        TEXT    NOT NULL,
    name          TEXT    NOT NULL COLLATE NOCASE,
    taxon_id      INTEGER NOT NULL REFERENCES taxon (id) ON DELETE CASCADE,
    PRIMARY KEY (source, name)
) STRICT, WITHOUT ROWID;

-- The view gains where a sighting came from.
DROP VIEW sighting_v;
CREATE VIEW sighting_v AS
SELECT
    s.id, s.uuid, s.taxon_id, s.observed_date, s.observed_time,
    s.place_id, s.latitude, s.longitude, s.uncertainty_m, s.location_method, s.location_text,
    s.count, s.count_qualifier, s.evidence, s.identification, s.sex, s.life_stage,
    s.habitat, s.is_not_wild, s.outing_id, s.notes, s.created_at, s.updated_at,
    s.source, s.source_id, s.import_batch_id,
    t.common_name, t.scientific_name, t.rank, t.species_id, t.category_id,
    p.name                                   AS place_name,
    COALESCE(s.latitude,  p.latitude)        AS eff_latitude,
    COALESCE(s.longitude, p.longitude)       AS eff_longitude,
    CASE WHEN s.latitude IS NOT NULL THEN s.uncertainty_m ELSE p.radius_m END AS eff_uncertainty_m
FROM sighting s
JOIN taxon t      ON t.id = s.taxon_id
LEFT JOIN place p ON p.id = s.place_id
WHERE s.deleted_at IS NULL;
