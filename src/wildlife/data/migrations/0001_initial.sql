-- WildLife database schema, version 1 (migration 0001)
-- ---------------------------------------------------------------------------
-- Never edit this file once released: change the schema with a new numbered
-- migration (0002_....sql) instead. The migration runner wraps each file in a
-- transaction and sets PRAGMA user_version.
--
-- Conventions
--   * Every table is STRICT: SQLite refuses values of the wrong type.
--   * Codes are lower_snake_case text (e.g. 'seen_heard'); the UI maps them to
--     friendly labels. CHECK constraints list the allowed codes.
--   * Observation dates/times are local UK wall-clock values:
--       observed_date 'YYYY-MM-DD', observed_time 'HH:MM' (nullable).
--   * System timestamps (created_at, updated_at, deleted_at, imported_at) are
--     UTC ISO-8601: 'YYYY-MM-DDTHH:MM:SSZ'.
--   * Coordinates are WGS84 decimal degrees.
--   * deleted_at IS NOT NULL means "in the recycle bin" (soft delete).
--   * Booleans are INTEGER 0/1.
--
-- The database enforces *structure* (types, allowed codes, relationships).
-- The Python domain layer enforces *business rules* that need context,
-- such as "date is not in the future".
-- ---------------------------------------------------------------------------

-- ===========================================================================
-- Categories: user-facing groups (Bird, Mammal, ...)
-- ===========================================================================
CREATE TABLE category (
    id            INTEGER PRIMARY KEY,
    name          TEXT    NOT NULL COLLATE NOCASE UNIQUE,
    colour        TEXT    NOT NULL CHECK (colour GLOB '#[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]'),
    icon          TEXT    NOT NULL,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    is_fallback   INTEGER NOT NULL DEFAULT 0 CHECK (is_fallback IN (0, 1))
) STRICT;

-- Only one category can be the fallback ("Other").
CREATE UNIQUE INDEX category_one_fallback ON category (is_fallback) WHERE is_fallback = 1;

-- Taxonomic group name -> category. A rule matches a taxon when the name
-- appears anywhere in its lineage; the most specific match wins
-- (family > order > class > phylum > kingdom). Rules match by name rather
-- than by rank because the UK Species Inventory sometimes files an order
-- (e.g. Odonata) in the "class" field.
CREATE TABLE category_rule (
    id            INTEGER PRIMARY KEY,
    category_id   INTEGER NOT NULL REFERENCES category (id) ON DELETE CASCADE,
    taxon_name    TEXT    NOT NULL COLLATE NOCASE UNIQUE
) STRICT;

-- ===========================================================================
-- Taxa: the species catalogue (UKSI reference names + custom species)
-- ===========================================================================
CREATE TABLE taxon (
    id                  INTEGER PRIMARY KEY,
    uksi_key            TEXT    UNIQUE,              -- NULL for custom species
    scientific_name     TEXT    NOT NULL,
    authority           TEXT,                        -- e.g. '(Linnaeus, 1758)'
    common_name         TEXT,                        -- preferred English name, if any
    rank                TEXT    NOT NULL CHECK (rank IN (
                            'kingdom', 'phylum', 'class', 'order', 'family', 'genus',
                            'species_group', 'species', 'subspecies', 'other')),
    parent_id           INTEGER REFERENCES taxon (id),
    -- The species-rank taxon this one "counts as" for lists:
    -- itself for a species, its parent species for a subspecies,
    -- NULL for anything broader (genus, "gull species", ...).
    species_id          INTEGER REFERENCES taxon (id),
    -- Lineage copied in for fast category rules and filtering.
    tax_kingdom         TEXT,
    tax_phylum          TEXT,
    tax_class           TEXT,
    tax_order           TEXT,
    tax_family          TEXT,
    category_id         INTEGER NOT NULL REFERENCES category (id),
    category_is_manual  INTEGER NOT NULL DEFAULT 0 CHECK (category_is_manual IN (0, 1)),
    is_custom           INTEGER NOT NULL DEFAULT 0 CHECK (is_custom IN (0, 1)),
    is_hidden           INTEGER NOT NULL DEFAULT 0 CHECK (is_hidden IN (0, 1)),
    priority            INTEGER NOT NULL DEFAULT 0,  -- "commonly recorded" boost for the picker
    created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (is_custom = 1 OR uksi_key IS NOT NULL)
) STRICT;

CREATE INDEX taxon_category ON taxon (category_id);
CREATE INDEX taxon_species  ON taxon (species_id);
CREATE INDEX taxon_parent   ON taxon (parent_id);
CREATE INDEX taxon_order    ON taxon (tax_order);

-- Every searchable name for a taxon: scientific, preferred common, synonyms.
CREATE TABLE taxon_name (
    id          INTEGER PRIMARY KEY,
    taxon_id    INTEGER NOT NULL REFERENCES taxon (id) ON DELETE CASCADE,
    name        TEXT    NOT NULL COLLATE NOCASE,
    kind        TEXT    NOT NULL CHECK (kind IN ('scientific', 'common', 'synonym')),
    UNIQUE (taxon_id, name)
) STRICT;

CREATE INDEX taxon_name_name ON taxon_name (name);

-- Full-text index over names. Trigram = matches any 3+ letter fragment,
-- so "finch" finds "Goldfinch". Kept in sync by the triggers below.
CREATE VIRTUAL TABLE taxon_name_fts USING fts5 (
    name,
    content = 'taxon_name',
    content_rowid = 'id',
    tokenize = 'trigram remove_diacritics 1'
);

CREATE TRIGGER taxon_name_ai AFTER INSERT ON taxon_name BEGIN
    INSERT INTO taxon_name_fts (rowid, name) VALUES (new.id, new.name);
END;
CREATE TRIGGER taxon_name_ad AFTER DELETE ON taxon_name BEGIN
    INSERT INTO taxon_name_fts (taxon_name_fts, rowid, name) VALUES ('delete', old.id, old.name);
END;
CREATE TRIGGER taxon_name_au AFTER UPDATE OF name ON taxon_name BEGIN
    INSERT INTO taxon_name_fts (taxon_name_fts, rowid, name) VALUES ('delete', old.id, old.name);
    INSERT INTO taxon_name_fts (rowid, name) VALUES (new.id, new.name);
END;

-- ===========================================================================
-- Places: saved, reusable locations
-- ===========================================================================
CREATE TABLE place (
    id            INTEGER PRIMARY KEY,
    name          TEXT    NOT NULL COLLATE NOCASE,
    latitude      REAL    NOT NULL CHECK (latitude  BETWEEN -90  AND 90),
    longitude     REAL    NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    radius_m      INTEGER NOT NULL DEFAULT 250 CHECK (radius_m BETWEEN 1 AND 100000),
    habitat       TEXT    CHECK (habitat IN (
                      'woodland', 'grassland', 'farmland', 'heath_moorland', 'wetland',
                      'freshwater', 'coastal', 'marine', 'garden_urban', 'upland', 'other')),
    notes         TEXT,
    is_favourite  INTEGER NOT NULL DEFAULT 0 CHECK (is_favourite IN (0, 1)),
    is_archived   INTEGER NOT NULL DEFAULT 0 CHECK (is_archived IN (0, 1)),
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
) STRICT;

-- ===========================================================================
-- Outings: optional trip/visit grouping, holds the weather
-- ===========================================================================
CREATE TABLE outing (
    id                INTEGER PRIMARY KEY,
    uuid              TEXT    NOT NULL UNIQUE,
    outing_date       TEXT    NOT NULL CHECK (date(outing_date) IS outing_date),
    -- '24:00' is accepted by strftime(), so it is excluded explicitly.
    start_time        TEXT    CHECK (start_time IS NULL OR (strftime('%H:%M', start_time) IS start_time AND start_time < '24:00')),
    end_time          TEXT    CHECK (end_time   IS NULL OR (strftime('%H:%M', end_time)   IS end_time   AND end_time   < '24:00')),
    place_id          INTEGER REFERENCES place (id),
    title             TEXT,
    weather           TEXT    CHECK (weather IN ('sunny', 'partly_cloudy', 'overcast', 'rain', 'drizzle', 'snow', 'fog')),
    temperature_c     REAL    CHECK (temperature_c BETWEEN -50 AND 60),
    wind              TEXT    CHECK (wind IN ('calm', 'light', 'moderate', 'strong', 'gale')),
    visibility        TEXT    CHECK (visibility IN ('good', 'moderate', 'poor')),
    is_complete_list  INTEGER NOT NULL DEFAULT 0 CHECK (is_complete_list IN (0, 1)),
    notes             TEXT,
    created_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at        TEXT
) STRICT;

CREATE INDEX outing_date ON outing (outing_date) WHERE deleted_at IS NULL;

-- ===========================================================================
-- Sightings: the heart of the app
-- ===========================================================================
CREATE TABLE sighting (
    id                INTEGER PRIMARY KEY,
    uuid              TEXT    NOT NULL UNIQUE,
    taxon_id          INTEGER NOT NULL REFERENCES taxon (id),
    observed_date     TEXT    NOT NULL CHECK (date(observed_date) IS observed_date),
    observed_time     TEXT    CHECK (observed_time IS NULL OR (strftime('%H:%M', observed_time) IS observed_time AND observed_time < '24:00')),
    place_id          INTEGER REFERENCES place (id),
    latitude          REAL    CHECK (latitude  BETWEEN -90  AND 90),
    longitude         REAL    CHECK (longitude BETWEEN -180 AND 180),
    uncertainty_m     INTEGER CHECK (uncertainty_m BETWEEN 1 AND 100000),
    location_method   TEXT    CHECK (location_method IN ('place', 'grid_ref', 'map', 'photo', 'typed', 'device', 'import')),
    location_text     TEXT    CHECK (length(location_text) <= 200),
    count             INTEGER CHECK (count >= 1),               -- NULL = present, not counted
    count_qualifier   TEXT    NOT NULL DEFAULT 'exact' CHECK (count_qualifier IN ('exact', 'approx', 'at_least')),
    evidence          TEXT    NOT NULL DEFAULT 'seen' CHECK (evidence IN ('seen', 'heard', 'seen_heard', 'signs', 'dead', 'trapped')),
    identification    TEXT    NOT NULL DEFAULT 'certain' CHECK (identification IN ('certain', 'probable', 'possible')),
    sex               TEXT    CHECK (sex IN ('male', 'female', 'mixed', 'unknown')),
    life_stage        TEXT    CHECK (life_stage IN ('adult', 'juvenile', 'immature', 'egg', 'larva', 'pupa', 'nymph', 'other')),
    habitat           TEXT    CHECK (habitat IN (
                          'woodland', 'grassland', 'farmland', 'heath_moorland', 'wetland',
                          'freshwater', 'coastal', 'marine', 'garden_urban', 'upland', 'other')),
    is_not_wild       INTEGER NOT NULL DEFAULT 0 CHECK (is_not_wild IN (0, 1)),
    outing_id         INTEGER REFERENCES outing (id) ON DELETE SET NULL,
    notes             TEXT    CHECK (length(notes) <= 10000),
    created_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at        TEXT,
    -- Latitude and longitude come as a pair.
    CHECK ((latitude IS NULL) = (longitude IS NULL))
) STRICT;

-- Partial indexes only cover live (not deleted) sightings: smaller and faster.
CREATE INDEX sighting_date        ON sighting (observed_date, observed_time) WHERE deleted_at IS NULL;
CREATE INDEX sighting_taxon_date  ON sighting (taxon_id, observed_date)      WHERE deleted_at IS NULL;
CREATE INDEX sighting_place       ON sighting (place_id)                     WHERE deleted_at IS NULL;
CREATE INDEX sighting_outing      ON sighting (outing_id)                    WHERE deleted_at IS NULL;
CREATE INDEX sighting_bin         ON sighting (deleted_at)                   WHERE deleted_at IS NOT NULL;

-- Full-text index over the free-text fields of a sighting.
CREATE VIRTUAL TABLE sighting_text_fts USING fts5 (
    notes,
    location_text,
    content = 'sighting',
    content_rowid = 'id',
    tokenize = 'trigram remove_diacritics 1'
);

CREATE TRIGGER sighting_ai AFTER INSERT ON sighting BEGIN
    INSERT INTO sighting_text_fts (rowid, notes, location_text)
    VALUES (new.id, new.notes, new.location_text);
END;
CREATE TRIGGER sighting_ad AFTER DELETE ON sighting BEGIN
    INSERT INTO sighting_text_fts (sighting_text_fts, rowid, notes, location_text)
    VALUES ('delete', old.id, old.notes, old.location_text);
END;
CREATE TRIGGER sighting_au AFTER UPDATE OF notes, location_text ON sighting BEGIN
    INSERT INTO sighting_text_fts (sighting_text_fts, rowid, notes, location_text)
    VALUES ('delete', old.id, old.notes, old.location_text);
    INSERT INTO sighting_text_fts (rowid, notes, location_text)
    VALUES (new.id, new.notes, new.location_text);
END;

-- ===========================================================================
-- Photos: one row per image file in the library
-- ===========================================================================
CREATE TABLE photo (
    id              INTEGER PRIMARY KEY,
    uuid            TEXT    NOT NULL UNIQUE,
    sha256          TEXT    NOT NULL UNIQUE CHECK (length(sha256) = 64),
    rel_path        TEXT    NOT NULL UNIQUE,   -- relative to the data folder, '/' separators
    original_name   TEXT    NOT NULL,
    file_size       INTEGER NOT NULL CHECK (file_size > 0),
    width           INTEGER CHECK (width  > 0),
    height          INTEGER CHECK (height > 0),
    taken_at        TEXT,                      -- local 'YYYY-MM-DD HH:MM:SS' from EXIF
    gps_latitude    REAL    CHECK (gps_latitude  BETWEEN -90  AND 90),
    gps_longitude   REAL    CHECK (gps_longitude BETWEEN -180 AND 180),
    rotation        INTEGER NOT NULL DEFAULT 0 CHECK (rotation IN (0, 90, 180, 270)),
    caption         TEXT,
    imported_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at      TEXT,
    CHECK ((gps_latitude IS NULL) = (gps_longitude IS NULL))
) STRICT;

CREATE INDEX photo_taken ON photo (taken_at) WHERE deleted_at IS NULL;

-- Which photos belong to which sightings (a photo of two species can be
-- attached to both). A photo with no links at all is in the Photo Inbox.
CREATE TABLE sighting_photo (
    sighting_id  INTEGER NOT NULL REFERENCES sighting (id) ON DELETE CASCADE,
    photo_id     INTEGER NOT NULL REFERENCES photo (id)    ON DELETE CASCADE,
    sort_order   INTEGER NOT NULL DEFAULT 0,               -- lowest = cover photo
    PRIMARY KEY (sighting_id, photo_id)
) STRICT, WITHOUT ROWID;

CREATE INDEX sighting_photo_photo ON sighting_photo (photo_id);

-- ===========================================================================
-- Settings: user preferences that changed from their defaults.
-- Defaults live in Python (one source of truth); values are JSON text.
-- ===========================================================================
CREATE TABLE setting (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL CHECK (json_valid(value))
) STRICT, WITHOUT ROWID;

-- ===========================================================================
-- Views: one readable definition of "a live sighting", reused everywhere
-- ===========================================================================
CREATE VIEW sighting_v AS
SELECT
    s.id, s.uuid, s.taxon_id, s.observed_date, s.observed_time,
    s.place_id, s.latitude, s.longitude, s.uncertainty_m, s.location_method, s.location_text,
    s.count, s.count_qualifier, s.evidence, s.identification, s.sex, s.life_stage,
    s.habitat, s.is_not_wild, s.outing_id, s.notes, s.created_at, s.updated_at,
    t.common_name, t.scientific_name, t.rank, t.species_id, t.category_id,
    p.name                                   AS place_name,
    COALESCE(s.latitude,  p.latitude)        AS eff_latitude,
    COALESCE(s.longitude, p.longitude)       AS eff_longitude,
    CASE WHEN s.latitude IS NOT NULL THEN s.uncertainty_m ELSE p.radius_m END AS eff_uncertainty_m
FROM sighting s
JOIN taxon t      ON t.id = s.taxon_id
LEFT JOIN place p ON p.id = s.place_id
WHERE s.deleted_at IS NULL;

-- ===========================================================================
-- Starter data: default categories and taxonomy rules
-- ===========================================================================
INSERT INTO category (id, name, colour, icon, sort_order, is_fallback) VALUES
    -- Colours are the 8 validated categorical slots, in their fixed order
    -- (colour-blind safe for neighbours; see docs/04-ui-ux-design.md).
    -- The UI picks the dark-theme step of each slot automatically.
    (1, 'Bird',                    '#2a78d6', 'bird',       10, 0),
    (2, 'Mammal',                  '#eb6834', 'rabbit',     20, 0),
    (3, 'Fish',                    '#1baf7a', 'fish',       30, 0),
    (4, 'Butterfly & Moth',        '#eda100', 'butterfly',  40, 0),
    (5, 'Dragonfly & Damselfly',   '#e87ba4', 'dragonfly',  50, 0),
    (6, 'Reptile & Amphibian',     '#008300', 'frog',       60, 0),
    (7, 'Other insect',            '#4a3aa7', 'bug',        70, 0),
    (8, 'Other invertebrate',      '#e34948', 'snail',      80, 0),
    (9, 'Other',                   '#7d847e', 'paw-print',  90, 1);

INSERT INTO category_rule (category_id, taxon_name) VALUES
    (8, 'Animalia'),            -- any animal not matched below
    (9, 'Chordata'),            -- vertebrates and relatives not matched below
    (1, 'Aves'),
    (2, 'Mammalia'),
    (3, 'Actinopterygii'), (3, 'Actinopteri'), (3, 'Chondrichthyes'), (3, 'Elasmobranchii'),
    (3, 'Holocephali'), (3, 'Cephalaspidomorphi'), (3, 'Petromyzonti'), (3, 'Myxini'), (3, 'Pisces'),
    (6, 'Reptilia'), (6, 'Amphibia'),
    (7, 'Insecta'), (7, 'Coleoptera'), (7, 'Diptera'), (7, 'Hymenoptera'), (7, 'Hemiptera'),
    (7, 'Trichoptera'), (7, 'Neuroptera'), (7, 'Orthoptera'), (7, 'Ephemeroptera'), (7, 'Plecoptera'),
    (4, 'Lepidoptera'),
    (5, 'Odonata');
