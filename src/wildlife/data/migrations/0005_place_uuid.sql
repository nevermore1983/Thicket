-- Migration 0005 (Phase 11): places get a uuid, like sightings, outings and photos,
-- so an export can be imported again (or into another library) without duplicating them.
ALTER TABLE place ADD COLUMN uuid TEXT;
UPDATE place SET uuid =
    lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' ||
    substr(lower(hex(randomblob(2))), 2) || '-' ||
    substr('89ab', 1 + abs(random()) % 4, 1) || substr(lower(hex(randomblob(2))), 2) || '-' ||
    lower(hex(randomblob(6)));
CREATE UNIQUE INDEX place_uuid ON place (uuid);
