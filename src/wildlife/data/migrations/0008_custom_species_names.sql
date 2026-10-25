-- Migration 0008 (version 1.4.2): searchable names for species brought in by an import.
--
-- Importing a Thicket export adds any species this library's list doesn't have (one from
-- a US state's pack you haven't added, say) as your own. Up to 1.4.1 those species got
-- no searchable names, so the species picker, search and later imports couldn't find
-- them. Their scientific and common names are added now (pack NULL: names of a species
-- of your own, as in migration 0007).
INSERT OR IGNORE INTO taxon_name (taxon_id, name, kind)
    SELECT id, scientific_name, 'scientific' FROM taxon WHERE is_custom = 1;
INSERT OR IGNORE INTO taxon_name (taxon_id, name, kind)
    SELECT id, common_name, 'common' FROM taxon WHERE is_custom = 1 AND common_name IS NOT NULL;
