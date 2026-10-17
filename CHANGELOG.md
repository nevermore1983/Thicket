# Changes

Each version's notes are used for its download page on GitHub (`scripts/release_notes.py`).

## 1.0.3

The first version available to download from GitHub. Nothing changes in use.

- The third-party notices now state that WildLife's terms don't restrict modifying the Qt libraries it includes, as Qt's licence (the LGPL) requires for a public download.

## 1.0.2

- Rotating a photo removes its old thumbnails.
- Backups tidy their photo folder. A photo copy is removed only when neither your library nor any backup still kept needs it.
- Spreadsheet exports are safe to open in Excel: text starting with `=`, `+`, `-` or `@` is kept as text, not run as a formula.
- Pages showing "today" are redrawn just after midnight.
- Fixed: a backup folder with `#` or `%` in its name showed its backups as empty in the restore list.

## 1.0.1

Fixes from a full code audit (see `docs/15-code-audit.md`).

- Importing a photo that's in the recycle bin brings it back, instead of leaving it hidden there.
- Deleting a place that an outing uses explains why it can't be deleted.
- One backup runs at a time, so two can't spoil each other.
- Saving a sighting waits for photos still being added.
- Undoing an edit also brings back the photos it had.
- "Empty now" empties photos too.
- `_` and `%` in a search match only themselves. Bulk changes work on any number of sightings.

## 1.0.0

The first release: recording sightings, photos (including RAW and HEIC), calendar, map, statistics, outings, places, iNaturalist and spreadsheet import, exports, automatic verified backups, restore and a health check.
