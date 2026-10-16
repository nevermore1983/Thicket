# WildLife — Phase 11, part 2: spreadsheets, export, restore and the health check

**Date:** 12 October 2026
**Status:** Complete, awaiting review (part 1 is in [11-import-inaturalist.md](11-import-inaturalist.md))

Your records can now leave WildLife in every useful form and come back again. A backup can be restored from inside the app, and a health check tells you if anything is missing.

---

## 1. What was built

| Area | What you get |
|---|---|
| **Import a spreadsheet** | Settings › Import & export › From a spreadsheet. Any CSV (Excel, Google Sheets, other apps, iRecord-style, Darwin Core, WildLife's own). WildLife **guesses which column is which** ("Date seen", "Latin name", "Grid ref", "Site", "How many"...), you check the guesses with example values from the file, then see the same check page as for iNaturalist before anything is imported. |
| **Reading values** | Dates the UK way (03/05/2026 = 3 May), also "3rd May 2026" and ISO. Times like 7.40 or 7:05 pm. Grid references become positions with an uncertainty covering the square. Counts like "c. 20" or "20+" keep their meaning. "Present" or an empty count means *not counted*: nothing is invented. A file that looks American (month first) gets a warning. An Excel workbook (.xlsx) gets told how to save it as CSV. |
| **Duplicates** | A row with the same species, date, time and spot (to ~100 m) as a sighting you have is left out, and so is the same row twice in one file. |
| **Import a WildLife export** | The .zip (with photos, RAW originals included) or the .json. Places, outings, photos, turns and captions come back. Everything is matched by its permanent id, so importing twice adds nothing. A species the library doesn't know is added as your own species. |
| **Import history** | Settings lists recent imports: when, from where, how many. **Show** lists that import's sightings; **Remove…** moves them to the recycle bin (with Undo). |
| **Export** | Settings › Export…, or **Export…** on the Sightings page, which exports exactly what the page shows. Five formats: **Spreadsheet**; **Darwin Core** (for iRecord, the NBN Atlas, GBIF); **Map data** (GeoJSON); **WildLife data** (JSON); and **Everything, with photos** (.zip with the JSON, both CSVs, every photo file and a README). |
| **Sharing safely** | For the sharing formats: **blur locations** to the centre of a 1 km or 10 km grid square (place names and descriptions left out, a grid reference given, Darwin Core says so in `dataGeneralizations`). **Include photos** makes a .zip, and **remove where the photos were taken** strips GPS from the shared copies *without re-compressing the picture*. Your library is never changed. |
| **Restore a backup** | Settings › Backup › Restore…: pick a backup (newest first, with its date and size) or any backup file. WildLife checks it, restarts, keeps your current data as a safety copy, puts the backup in place, and copies back photo files the library is missing from the backup. |
| **Health check** | Settings › Data › Health check: the data file, every photo file, unknown or half-copied files in the photo folder, thumbnails, backups and the species list, each in plain words with a fix where one is safe (e.g. **Bring back from backup** for missing photos). It never deletes your photos. |

---

## 2. Decisions

| Decision | Why |
|---|---|
| **One import pipeline for every format** | iNaturalist, spreadsheets and Darwin Core all become the same kind of record, then share the same name matching, duplicate check, preview, one-step import and Undo. A fix in one helps all. |
| Restoring happens **at the next start**, not while WildLife runs | The database can't safely be swapped while it's open. WildLife leaves a note, restarts, and does it before anything opens the data. If the backup has gone missing by then (e.g. a drive was unplugged), nothing changes and you're told why. |
| Complete exports are **always exact**; sharing exports can be blurred | A complete export is for keeping or moving your data, so it must come back identical. Blurring is for records you send to someone else. |
| GPS removal edits only the photo's **metadata** | Removing the location from the EXIF block (and dropping XMP, which can also hold one) leaves the picture byte-for-byte identical. Photos turned in WildLife, and non-JPEG files, are saved as a fresh JPEG, which carries no location at all. |
| Places got a **permanent id** (migration 0005) | Sightings, outings and photos already had one. Without it, importing an export twice would have duplicated places. |
| Backups are now **single files** | Each backup was in the database's write-ahead mode, so verifying it left two side files behind, and rotation never removed them. They are now saved as one self-contained file, and rotation removes any side files. *(A problem from Phase 6, found by this phase's end-to-end check.)* |

---

## 3. Checks

- **Tests:** 425 automated (54 new in part 2), all passing. New tests cover:
  - every export format;
  - blurring;
  - GPS removal, with the picture data unchanged;
  - nothing half-written left behind after an error;
  - spreadsheet reading (dates, counts, grid references, column guessing);
  - duplicates;
  - **round trips**: spreadsheet export → import, Darwin Core export → import, and full archive → an empty library, which gives **identical** sightings, places, outings and photos, RAW originals included;
  - a doctored archive trying to write outside the library;
  - restore, including a restore whose backup has disappeared;
  - the health check and its fixes;
  - import history;
  - all the new windows.
- **A "hygiene" test** now fails the build if a placeholder function, an SQL alias string hack, or `@dataclass` on a Qt class creeps in. These slips happened often enough during development that checking for them by hand wasn't enough.
- **End-to-end in the packaged app:** a restore was requested on a test library, then `WildLife.exe` was started. The backup was restored before the window opened, and a safety copy was kept.
- **Performance** with 20,000 sightings:

  | Action | Time |
  |---|---|
  | Spreadsheet export | 0.5 s |
  | Darwin Core export, blurred | 0.65 s |
  | Map data | 0.5 s |
  | WildLife JSON | 0.4 s |
  | Everything with 400 photos | 2.6 s |
  | Spreadsheet import (preview, then import) | 0.6 s, then 1.2 s |
  | WildLife archive import | 1.1 s |
  | Health check (418 photos) | 1.0 s |

- **Visual checks:** the column-matching step, the export, health check and restore windows, and the new Settings section.

---

## 4. Problems found and fixed

| Problem | Fix / lesson |
|---|---|
| A spreadsheet's "Count type" (Approximate / At least) was exported but not read back | Found by the round-trip test; now read |
| The import window's `result` hid `QDialog.result()` | Renamed to `outcome`; the screenshot run crashed on it, so it was caught before you saw it |
| The export window enabled a format before its options existed | Built in the right order |
| Backups left `-wal`/`-shm` side files that were never cleaned up | Single-file backups, and rotation removes side files |
| `\n` in shell-written code became real line breaks, twice more | Text containing backslashes is now always written with the Edit tool |
| Placeholder functions slipped into new files twice more | The new hygiene test catches them automatically |
| "1 photo files are missing" | Counts now read naturally |

---

## 5. Deferred

| Item | Where |
|---|---|
| ~~A real download of your iNaturalist photos~~ | **Done 16 Oct 2026:** you downloaded all your photos in the app; it worked |
| KML export for Google Earth (a "Could") | Phase 12 if wanted |
| Offering "Restore latest backup" when the data file can't be opened at start-up | Phase 12 |
| Locating missing photos one by one (the service exists; the health check brings them back from backup) | Phase 12 |
