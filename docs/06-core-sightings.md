# WildLife — Phase 6: Core Sightings

**Date:** 11 October 2026
**Status:** Complete, awaiting review

WildLife can now be used for real. You can record, view, edit, delete, search and filter sightings, attach photos, and manage places. Your data is backed up automatically.

---

## 1. What was built

| Area | What you get |
|---|---|
| **Species list** | The full UK Species Inventory for animals (65,499 names, 43,450 species, 8,030 English names), bundled in the app at 1.8 MB and installed on first run in about 5 s. It is built by `scripts/build_species_catalogue.py` from the NHM file. |
| **Species picker** | Ranked as you type: your own species first, then the best name match, then commonly recorded UK species (281 hand-picked boosts in `scripts/data/common_species.txt`). Old and alternative names work, e.g. "Redbreast" finds Robin and "Seagull" finds Larus. Under 15 ms per keystroke. |
| **Add / edit panel** | Only the species is required. Date and time default to now, and the last place used is remembered. It accepts OS grid references, coordinates and map links, with live checking and a swapped lat/lon warning. Counts take "c. 200" and "50+". Photos can be dropped in and fill date, time and position. "More details" holds the extra fields. Enter saves, Ctrl+Enter is "Save & add another", and Esc asks before discarding changes. |
| **Sighting detail** | Name, Lifer and confidence badges, photos, all facts including the grid reference with uncertainty, plus Edit (E) and Delete (Delete key). |
| **Sightings page** | A table that only loads the rows on screen (copes with 100k+ sightings). Sortable columns, a filter bar (category, date presets or custom, place, species, text), multi-select with Change species and Delete, and a totals footer. Empty states for "no sightings" and "nothing matches". |
| **Undo everywhere** | Every save, edit, delete and bulk change shows a toast with Undo (and Ctrl+Z). |
| **Recycle bin** | Deleted sightings are kept for 30 days and can be restored from Settings › Data. Older ones are removed automatically. |
| **Dashboard** | Totals, life list, species this year compared with this date last year, this month, recent sightings, and "Needs attention" (no location, unattached photos, backup status). |
| **Places** | Create, edit, archive and delete (blocked while in use). Sightings inside a place's radius suggest it. |
| **My species** | Your life list, with first and last seen. Double-click shows that species' sightings. |
| **Photos** | Copied into the library under their content hash (duplicates are detected), EXIF date/GPS/rotation read (including iPhone HEIC), thumbnails cached. |
| **Backups** | Automatic daily backup and on close after changes, plus "Back up now". Each one is a verified snapshot with a photo mirror, kept on a 7-daily / 4-weekly / 12-monthly rotation. Settings warns if backups are on the same drive as the data. |
| **Global search** | Ctrl+K suggests species you've recorded and places. Enter shows all matching sightings. |
| **First run** | Welcome, your name, species-list install with progress, and a note about backups. |

---

## 2. Checks

- **Tests:** 134 automated, all passing in about 16 s. They cover:
  - domain rules;
  - the database and catalogue;
  - sightings, places, photos (HEIC and JPEG fixtures) and backups;
  - UI flows driven by pytest-qt: keyboard-only add, validation, Save & add another, edit with undo, delete with undo, search, filters, bulk delete, places, backup, recycle bin.
- **Performance** with 20,000 sightings:

  | Action | Time |
  |---|---|
  | First page of sightings | 2 ms |
  | Filtered page | 4 ms |
  | Text search | 9 ms |
  | Totals | 7 ms |
  | Dashboard numbers | 12 ms |
  | Species picker | ≤ 14 ms |
  | Window ready with all pages | 0.5 s |
  | Verified backup of a 46 MB database | 0.8 s |

- **Packaged build:** 111 MB, starts in about 2.5 s, and its smoke test confirms it can read the bundled species list.
- **Visual checks:** screenshots of the dashboard, sightings, detail, add and edit panels, and the first-run steps, in light and dark.

---

## 3. Problems found and fixed

| Problem | Fix / lesson |
|---|---|
| The picker ranked exotic finches above Goldfinch, and family names ("Finches") at the top | A common-species boost, groups ranked down, and matches on a species' main name ranked above synonyms |
| Some well-known species have no recommended English name in UKSI (e.g. Drone Fly) | Fall back to the best well-formed English synonym (686 species) |
| Recycle bin "empty now" missed items deleted in the same second | The comparison was "strictly before now" and is now "at or before" |
| Two backups in the same second collided | Snapshot names get a suffix |
| Dropdowns returned plain text instead of codes, so saving crashed (caught by a UI test) | Values are converted when the form is read, and the database layer accepts either form |
| Dashboard rows overlapped | A Qt button doesn't grow to fit a layout inside it, so rows are now clickable frames with keyboard support |
| The add panel was wider than the panel (chips didn't wrap) | New `FlowLayout`, and no horizontal scrolling in panels |
| Chip text clipped when selected | Bold text is wider than the size Qt measured; selection is now shown by colour only |
| The UI test suite hung on failure | pytest-qt closed the window before cleanup, so "Discard changes?" waited forever. The fixture now closes its own window. |
| Focus-dependent tests were flaky | Windows won't focus a test window while you use another app, so tests tolerate that |
| Screenshots showed phantom outlines | The screenshot script applied the theme after building the window; it now matches the real startup |

---

## 4. Deferred (deliberately)

| Item | Where |
|---|---|
| Outings (trips with weather) | Phase 7, with the calendar's day view |
| Bulk change of place/date (species is done) | Phase 12 polish |
| Dates in global search ("May 2025") | Phase 7 (calendar) |
| Photo Inbox page, gallery, full viewer, rotate | Phase 9 |
| Restoring a backup from the app | Phase 11 (the backups already exist and are verified) |
| Bundling the Source Serif 4 font (scientific names currently fall back to Georgia) | Phase 12 |
