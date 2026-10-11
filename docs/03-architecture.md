# WildLife — Phase 3: Architecture & Database Design

**Date:** 11 October 2026
**Status:** Draft for your review
**Builds on:** [01 Research](01-research-and-architecture.md) · [02 Product specification](02-product-specification.md)
**Companion files:**
- [`design/schema_v1.sql`](design/schema_v1.sql): the complete database schema, with comments
- [`../spikes/schema_check/check_schema.py`](../spikes/schema_check/check_schema.py): the stress test that proves it works

This document defines **how the app is put together**: the layers, every module and its job, the database, the files on disk, and how data, errors and background work flow through the app. No application code exists yet. Phase 4 designs the screens, and Phase 5 starts building.

---

## 1. Summary

- **Four layers** (UI → Services → Data, plus a shared Domain), with one rule: dependencies only point downwards.
- **Database:** 10 tables, 2 full-text search indexes, 1 view, all `STRICT`, with `CHECK` rules on every coded field. The schema is **written as real SQL and tested**.
- **Proof:** a stress test with 20,000 sightings, 40,104 species, 5,000 photos, 1,500 outings and 300 places. Every screen's query runs in **under 50 ms**, a save takes **1.3 ms**, a verified backup takes **under 0.2 s**, and **26/26 integrity checks pass**.
- **The test caught a real bug before any app code existed:** SQLite accepts `24:00` as a valid time. That is now blocked.
- **Small changes from Phase 1:** use `pi-heif` (decode-only, more permissive licence) instead of `pillow-heif`. Photo ↔ sighting is many-to-many, so a photo of two species can belong to both sightings.

---

## 2. The layers

```
┌──────────────────────────────────────────────────────────────┐
│ UI  (wildlife/ui)                                            │
│   pages, side panels, components, theme, map/chart web pages │
│   • shows data, collects input, reacts to change events      │
├──────────────────────────────────────────────────────────────┤
│ SERVICES  (wildlife/services)                                │
│   the app's verbs: save sighting, import photos, back up…    │
│   • validates, opens transactions, announces changes         │
├──────────────────────────────────────────────────────────────┤
│ DATA  (wildlife/data)                                        │
│   connection, migrations, repositories (all SQL lives here)  │
├──────────────────────────────────────────────────────────────┤
│ DOMAIN  (wildlife/domain)          used by every layer above │
│   dataclasses, codes, validation, filters, geo maths         │
│   • pure Python: no Qt, no SQL, no files                     │
└──────────────────────────────────────────────────────────────┘
```

**The rule:** a layer may use layers *below* it, never above. The UI never writes SQL, services never create widgets, and the domain depends on nothing.

**Why it matters to you:**
1. **Bugs have an address.** A wrong number on a chart → `services/stats.py` or its repository. A button in the wrong place → `ui/`.
2. **Most logic is testable without a window.** Domain, data and services are plain Python, so tests run in seconds.
3. **AI-assisted changes stay contained.** "Change how backups rotate" touches `services/backup.py`, not twelve files.

What we deliberately **don't** do: abstract base classes for everything, dependency-injection frameworks, or "interfaces" with one implementation. We use plain modules and plain classes, and add abstraction only when there are genuinely two implementations of something.

### 2.1 Example: what happens when you press Save

```
SightingPanel (UI)                 SightingService                 sightings repo / DB
──────────────────                 ───────────────                 ───────────────────
1. read form → SightingDraft ───►  2. validate(draft, today)
                                      ✗ errors → ValidationError ──► panel shows them inline
                                   3. with transaction():  ───────►  INSERT sighting
                                                                     INSERT sighting_photo …
                                                                     (FTS trigger indexes notes)
                                   4. events.publish(SightingsChanged([42]))
5. toast "Robin saved · Undo" ◄──  returns SaveResult(id=42, undo=…)
6. Qt event bridge re-emits the change:
   • the visible page refreshes now
   • hidden pages are marked "stale" and refresh when you next open them
```

Step 6 is **lazy refresh**: there's no point redrawing a hidden calendar after every save. This keeps the app fast at 20,000+ records.

---

## 3. Module map

```
src/wildlife/
├─ __main__.py              python -m wildlife → app.main()
├─ app.py                   startup sequence (section 9)
├─ context.py               AppContext: builds and holds paths, database, services, events
│
├─ config/
│  ├─ paths.py              DataPaths: where db, photos, thumbnails, logs, maps live
│  └─ defaults.py           every user setting with its default value (one source of truth)
│
├─ domain/                  pure Python
│  ├─ models.py             Sighting, SightingDraft, Taxon, Category, Place, Outing, Photo, PhotoMeta
│  ├─ codes.py              Evidence, Identification, Sex, LifeStage, Habitat, Weather… (+ UI labels)
│  ├─ filters.py            SightingFilter (the shared filter)
│  ├─ validation.py         rules needing context: "not in the future", swapped lat/lon…
│  ├─ geo.py                lat/lon ↔ OS grid ref, coordinate parsing, distances, uncertainty
│  ├─ counting.py           "c. 200" / "50+" parsing
│  └─ errors.py             WildlifeError → ValidationError, NotFoundError, ImportFileError, BackupError…
│
├─ data/
│  ├─ db.py                 Database: per-thread connections, PRAGMAs, transaction()
│  ├─ migrate.py            applies migrations/NNNN_*.sql atomically, backup first
│  ├─ migrations/0001_initial.sql   (= docs/design/schema_v1.sql)
│  ├─ sql_filters.py        SightingFilter → (WHERE clause, parameters); COUNTABLE rule
│  └─ repositories/         one module per table group; functions take a connection
│     ├─ sightings.py   taxa.py   categories.py   places.py
│     ├─ outings.py     photos.py settings.py     stats.py (read-only aggregates)
│
├─ services/
│  ├─ events.py             EventHub: services publish "X changed"; listeners subscribe
│  ├─ sightings.py          create / update / bulk edit / delete / restore / purge
│  ├─ outings.py   places.py   settings.py
│  ├─ species_catalogue.py  UKSI import/update, category rules, picker ranking, custom species
│  ├─ search.py             global search (species, places, notes, outings, dates)
│  ├─ stats.py              dashboard tiles, statistics page, life/year lists
│  ├─ photos.py             import (copy, hash, EXIF), attach/detach, rotate, health check
│  ├─ thumbnails.py         generate/load thumbnail cache
│  ├─ backup.py             snapshot, verify, rotate, photo mirror, restore
│  ├─ exchange.py           export CSV/JSON/Darwin Core/GeoJSON/archive; CSV/JSON import
│  └─ online.py             optional weather lookup; fails gracefully
│
├─ ui/
│  ├─ main_window.py        shell: sidebar, top bar, page stack, side panel host, toasts
│  ├─ qt_events.py          bridges EventHub → Qt signals (thread-safe)
│  ├─ workers.py            run a function in the background, get the result as a signal
│  ├─ error_handler.py      global exception hook → friendly dialog + log
│  ├─ theme/                tokens.py · stylesheet.py · icons.py (+ icons/*.svg)
│  ├─ components/           Card, StatTile, EmptyState, Toast, SearchField, FilterBar,
│  │                        SpeciesPicker, PlacePicker, CoordinateField, PhotoStrip, …
│  ├─ pages/                dashboard · sightings · calendar · map · photos · statistics ·
│  │                        species · places · settings
│  ├─ panels/               sighting_panel · outing_panel · place_panel · photo_viewer
│  ├─ dialogs/              first_run · import_wizard · restore (only where a dialog is right)
│  └─ web/                  bridge.py + assets/ (map.html, map.js, charts.html, charts.js, vendor/)
│
└─ resources/               species catalogue file, app icon, LICENSES/
```

### 3.1 What each kind of module looks like

| Kind | Shape | Example |
|---|---|---|
| **Domain model** | `@dataclass(frozen=True, slots=True)`, no behaviour beyond small helpers | `Sighting(id, uuid, taxon_id, observed_date, …)` |
| **Repository** | Plain functions; first argument is a connection; only SQL + row mapping | `def insert(conn, draft) -> int`, `def page(conn, flt, sort, offset, limit) -> list[SightingRow]` |
| **Service** | A small class created once in `AppContext`, holding the `Database` and `EventHub` | `SightingService.save(draft) -> SaveResult` |
| **Page** | A `QWidget` that asks services for data and refreshes on events | `CalendarPage.refresh()` |
| **Component** | A reusable `QWidget` with no knowledge of services | `StatTile(title, value, delta)` |

### 3.2 Coding conventions

- Type hints everywhere. `ruff` formats and lints. Files stay under about 400 lines; anything bigger gets split.
- Names say what things *are*: `observed_date`, not `d`. Functions are verbs: `save`, `soft_delete`, `restore`.
- Comments explain *why*, not *what*.
- No SQL string building from user input. Always parameters (`?` / `:name`).

---

## 4. Database design

The full schema with comments is in [`design/schema_v1.sql`](design/schema_v1.sql). Here's the overview.

### 4.1 Tables and relationships

```
             category ◄── category_rule
                 ▲
                 │ category_id
   taxon ◄───────┘          taxon_name ──► taxon_name_fts (search index)
   ▲  ▲ parent_id / species_id (self-references)
   │
   │ taxon_id
 sighting ───────► place ◄─────── outing
   │  │   place_id        place_id  ▲
   │  └──────────────── outing_id ──┘
   │
   └──► sighting_text_fts (search index over notes/location text)
 sighting ◄──── sighting_photo ────► photo
 setting (key → JSON value)
```

| Table | Rows at stress scale | Purpose |
|---|---|---|
| `category` | 11 | Bird, Mammal… colour, icon, order |
| `category_rule` | 15 | "class Aves → Bird", most specific rule wins |
| `taxon` | ~40,000 | Species catalogue (UKSI + custom) |
| `taxon_name` | ~50,000 | Every searchable name (scientific, common, synonyms) |
| `place` | 300 | Saved places |
| `outing` | 1,500 | Optional trips |
| `sighting` | 20,000 | The records |
| `photo` | 5,000 | Library files (one row per unique image) |
| `sighting_photo` | ~4,700 | Which photos belong to which sightings |
| `setting` | a few | Only settings you changed |

### 4.2 Key decisions, and why

| Decision | Why |
|---|---|
| **`STRICT` tables + `CHECK` on every code** | The database refuses bad data even if the Python code has a bug. There are two lines of defence. |
| **Codes stored as text** (`'seen_heard'`), labels in Python | Readable in any SQLite tool and in exports. Labels can be reworded without touching data. |
| **Integer `id` + `uuid`** on sightings, outings, photos | Integers are fast for joins. UUIDs make export/import and future merging collision-free. |
| **`species_id` on taxon** | Life lists become `COUNT(DISTINCT species_id)`. Subspecies roll up to their species automatically, and broad groups ("Gull species") are `NULL` so they don't count. Proven by the stress test. |
| **Lineage columns** (`tax_class`, `tax_order`…) on taxon | Category rules and filters like "all moths" are simple and fast, with no recursive tree walking. |
| **Soft delete** (`deleted_at`) on sightings, outings, photos | Recycle bin and undo. **Partial indexes** (`WHERE deleted_at IS NULL`) keep deleted rows out of the indexes. |
| **`sighting_photo` link table** | A photo can belong to two sightings (two species in one shot). A photo with no links *is* the Photo Inbox, so no extra "status" column is needed. |
| **Places can't be deleted while used** (foreign key) | Enforced by the database itself, which pushes the UI towards "Archive" or "Merge". |
| **`setting` stores only changed values, as JSON** | Defaults live in one place (Python). Settings travel with backups. |
| **`sighting_v` view** | One definition of "a live sighting with its species and effective location", reused by every query. SQLite folds the view into each query, so it costs nothing (indexes were still used in the tests). |
| **Trigram full-text search** with `remove_diacritics` | "finch" finds Goldfinch and Chaffinch. Accents don't matter. 3+ letters use the index; 1–2 letters use a fast prefix match. |
| **Time checked as `HH:MM` and `< '24:00'`** | The stress test showed SQLite otherwise accepts `24:00` |

### 4.3 Rules written once, in SQL

**Countable for lists** (spec section 7.1), in `data/sql_filters.py`:
```sql
species_id IS NOT NULL            -- species rank or below
AND is_not_wild = 0               -- excludes captive/escaped
AND identification IN (:allowed)  -- 'certain', plus 'probable' if the setting is on
```

**Category from taxonomy.** The most specific rule wins, otherwise the fallback category ("Other"). Manual overrides are kept:
```sql
UPDATE taxon SET category_id = COALESCE(
  (rule for family), (rule for order), (rule for class), (rule for phylum), (rule for kingdom),
  (SELECT id FROM category WHERE is_fallback = 1))
WHERE category_is_manual = 0;
```
At stress scale this sorted 40,104 taxa in one statement, e.g. Lepidoptera → Butterfly & Moth, Ascidiacea (a sea squirt, phylum Chordata) → Other.

**Effective location** is the sighting's own coordinates, otherwise its place's centre (the `eff_latitude` / `eff_longitude` columns in `sighting_v`).

### 4.4 The shared filter

```python
@dataclass(frozen=True)
class SightingFilter:
    text: str | None = None              # global search text
    category_ids: frozenset[int] = frozenset()
    taxon_ids: frozenset[int] = frozenset()   # includes subspecies of chosen species
    date_from: date | None = None
    date_to: date | None = None
    place_ids: frozenset[int] = frozenset()
    outing_id: int | None = None
    evidence: frozenset[Evidence] = frozenset()
    has_photos: bool | None = None
    needs_location: bool = False
    include_not_wild: bool = True
```

`sql_filters.where(flt)` turns it into a parameterised `WHERE` clause. **Every** screen (list, calendar, map, statistics, export) calls this one function, which is how "a filter means the same thing everywhere" is guaranteed. It's tested once, thoroughly.

### 4.5 Connections, transactions and threads

- `Database` opens **one connection per thread**, because SQLite connections shouldn't be shared between threads. Each connection is opened with `autocommit=True`, so Python never starts transactions behind our back, and then gets `foreign_keys=ON`, `synchronous=FULL` and `busy_timeout=5000`. WAL mode is set once on the database file.
- **`with db.transaction():`** runs `BEGIN IMMEDIATE … COMMIT`, or `ROLLBACK` on any error. **Services** own transactions. Repositories never commit.
- **One writer at a time** (a SQLite rule). Saves take about 1 ms, so this is invisible. Data imports are a single all-or-nothing transaction lasting a few seconds; during one, a progress dialog is shown and editing waits.
- *Gotcha found in the spike:* with `autocommit=True`, `conn.rollback()` does nothing. We always run `ROLLBACK` explicitly.

### 4.6 Migrations (changing the schema later)

1. On startup, read `PRAGMA user_version` (0 = new database).
2. If any `migrations/NNNN_*.sql` file is newer, **take a pre-migration backup** first (when the database already contains data).
3. Run each script as **one atomic transaction** that also sets the new `user_version`.
4. Run `PRAGMA foreign_key_check` and `quick_check`. If anything fails, the app shows a clear message and offers to restore the pre-migration backup.
5. Tests check that **every** past version upgrades cleanly to the latest.

The spike proved that a broken migration leaves **no** half-applied changes and the version number untouched.

---

## 5. Proof: stress-test results

Machine: your PC. Python 3.13.14, SQLite 3.53.1. Dataset: 20,000 sightings (15 years, seasonal pattern), 40,104 taxa, 5,000 photos, 1,500 outings, 300 places. Run it yourself:

```bash
uv run --no-project --python 3.13 spikes/schema_check/check_schema.py
```

| Screen / operation | Time | Target (spec §9) |
|---|---|---|
| Dashboard: headline tiles | 41 ms | — |
| Dashboard: 10 recent + cover photo | < 1 ms | — |
| Dashboard: needs attention | 18 ms | — |
| Sightings list: filtered page + footer totals | 22 + 30 ms | ≤ 300 ms ✅ |
| Species picker per keystroke ('ro' / 'gold' / 'finch' / 'erith') | 22 / 5 / 5 / 5 ms | ≤ 200 ms ✅ |
| Global search in notes | 3 ms | ≤ 200 ms ✅ |
| Calendar month / year / week | < 1 / 5 / < 1 ms | ≤ 300 ms ✅ |
| Map: 18,784 points + GeoJSON (2.8 MB) | 38 + 42 ms | ≤ 2 s ✅ (browser drawing time measured in Phase 8) |
| Map: species per 1 km square | 5 ms | — |
| Statistics: all 7 queries combined | ~130 ms | ≤ 1.5 s ✅ |
| Life list table (3,103 species) | 24 ms | — |
| Photo library page / inbox | < 1 ms | — |
| Export every sighting | 81 ms | — |
| **Save one sighting** (full disk sync) | **1.3 ms** | ≤ 100 ms ✅ |
| Bulk change species | 2 ms | — |
| **Backup + verify** (29 MB database) | **~0.15 s** | ≤ 10 s ✅ |

**Picker quality check:** "ro" → Robin, Roe Deer first (species you've recorded rank first). "finch" → Goldfinch, Chaffinch (word-middle match). "erith" → Robin (scientific name *Erithacus*).

**26/26 integrity checks pass:** valid minimal sightings are accepted. Rejected: impossible dates, UK-style dates (`11/10/2026`), `9:30` and `24:00`, latitude 200, half coordinates, count 0, text in number columns, unknown codes, missing species, duplicate IDs, non-JSON settings, a second fallback category, a bad colour, and deleting a species or place that's in use. Also passing: failed migrations roll back completely, subspecies count as their species, genus-level records don't count, and the backup copy passes integrity and foreign-key checks with identical row counts.

**Conclusions:**
- The schema comfortably meets every performance target at 20,000 sightings. There is roughly 10× headroom before anything needs optimising.
- The database is 29 MB, mostly the 40k-species catalogue and its search index. Your own records add only about 1 MB per 10,000 sightings.
- The picker's slowest case (2 letters, 22 ms) is fine, but we'll cache "how often you've recorded each species" in memory, which is cheap, and wait 80 ms after typing stops before searching (debouncing).
- Full-table scans appear only in whole-history statistics, where they're expected and fast.

---

## 6. Files on disk

### 6.1 Data folder (default `%LOCALAPPDATA%\WildLife`, movable)

```
WildLife\
├─ wildlife.db                      the database (+ -wal / -shm while open)
├─ photos\2026\10\<sha256>.jpg      originals, by date taken (import date if unknown)
├─ thumbnails\256\ab\<sha256>.webp  grid thumbnails   ┐ cache: safe to delete,
├─ thumbnails\1024\ab\<sha256>.webp viewer previews   ┘ rebuilt automatically
├─ maps\uk.pmtiles                  optional offline map pack
└─ logs\wildlife.log (+ .1 … .5)    rotating logs, 1 MB each, UTF-8
```

- Photo paths in the database are **relative** (`photos/2026/10/…`), so the whole folder can be moved or restored elsewhere.
- Thumbnails are grouped into sub-folders by the first two hash characters (`ab\`), which keeps any one folder from holding thousands of files.
- Rotation is applied when *displaying* and when *making thumbnails*. The original is never rewritten.

### 6.2 Backup folder (chosen by you; another drive or a cloud-synced folder recommended)

```
WildLife Backups\
├─ snapshots\
│  ├─ 2026-10-11_093012_daily.db
│  ├─ 2026-10-11_093012_daily.json   manifest: app & schema version, created, SHA-256 of
│  │                                 the .db, row counts, kind, verification result
│  └─ …_weekly / _monthly / _manual / _pre-migration / _pre-restore
└─ photos\…                          mirror of the library: add-only, same relative paths
```

**Rotation** is "grandfather-father-son": keep the newest **7 daily, 4 weekly, 12 monthly** snapshots, **all manual** ones, and the last **5 pre-migration/pre-restore** ones.

**Restore:**
1. Verify the chosen snapshot against its manifest, then integrity and foreign-key checks.
2. Snapshot the current database as `_pre-restore`.
3. Copy the snapshot in.
4. Copy any photos missing from the library back from the mirror.
5. Restart the app and run a health check.

### 6.3 Export formats

**Full JSON** (`wildlife-export.json`, re-importable):
```json
{
  "format": "wildlife-export", "format_version": 1,
  "exported_at": "2026-10-11T09:30:00Z", "app_version": "1.0.0", "recorder": "…",
  "categories": [...], "taxa": [...only those used + all custom...],
  "places": [...], "outings": [...], "sightings": [...], "photos": [...metadata only...]
}
```
Records refer to each other by `uuid`. Species are referenced by UKSI key, with scientific name as a fallback, so an export can be imported into a library whose catalogue version is different.

**Full archive (.zip):** `wildlife-export.json` + `photos/` + `README.txt` explaining every file.

**Darwin Core CSV** (international biodiversity standard, accepted by iRecord, GBIF and NBN):

| Darwin Core term | From |
|---|---|
| `occurrenceID` | sighting `uuid` |
| `eventID` | outing `uuid` |
| `eventDate` | `observed_date` + `T` + `observed_time` (if known) |
| `scientificName`, `vernacularName`, `taxonRank` | taxon |
| `individualCount` | `count` (blank if not counted) |
| `decimalLatitude`, `decimalLongitude`, `coordinateUncertaintyInMeters` | effective location (optionally blurred) |
| `geodeticDatum` | `WGS84` |
| `locality` | place name + location description |
| `habitat`, `sex`, `lifeStage` | sighting fields |
| `basisOfRecord` | `HumanObservation` (or `MachineObservation` for trapped) |
| `identificationQualifier` | blank / "cf." for probable / possible |
| `degreeOfEstablishment` | `captive` when not wild |
| `recordedBy` | your name (Settings) |
| `occurrenceRemarks` | notes |
| `associatedMedia` | photo file names (archive export) |

---

## 7. Background work and the web pages

### 7.1 Threading model

| Runs on the UI thread | Runs on background workers (`QThreadPool`) |
|---|---|
| Quick queries (< ~50 ms): picker, lists, calendar, dashboard | Statistics page, map data, photo import, thumbnails, backups, export/import, catalogue install, network calls |

- `ui/workers.py` provides one helper: *run this function in the background, then call me back on the UI thread with the result or the error*. Every background task uses it, so there's one pattern to learn.
- Each worker thread gets its **own** database connection (section 4.5).
- Services publish change events from any thread. `ui/qt_events.py` turns them into Qt signals, and Qt delivers them safely to the UI thread.

### 7.2 Map and chart pages (Python ↔ JavaScript contract)

The web pages are **renderers only**. All data and decisions come from Python, and the bridge is a small, fixed list of messages:

| Direction | Message | Purpose |
|---|---|---|
| Py → Map | `setSightings(geojson)` | Pins / clusters / heat data for the current filter |
| Py → Map | `setGridSquares(geojson)` | Species-per-square layer (squares computed in Python) |
| Py → Map | `setPlaces(geojson)` | Saved place circles |
| Py → Map | `setView(mode)` · `setBasemap(id)` · `setTheme(light/dark)` | Display options |
| Py → Map | `flyTo(lat, lon, zoom)` · `fitTo(bounds)` · `highlight(id)` | Navigation |
| Map → Py | `ready()` · `error(code, message)` | Lifecycle, e.g. `no_webgl` |
| Map → Py | `sightingClicked(id)` | Open the sighting panel |
| Map → Py | `contextMenu(lat, lon, zoom)` | "Add sighting here" / "Create place here" |
| Py → Charts | `render(chartId, spec)` · `setTheme(…)` | Draw a chart from prepared data |
| Charts → Py | `chartClicked(chartId, key)` | Open matching sightings |

All JavaScript libraries are **bundled** in `ui/web/assets/vendor/`, so nothing loads from the internet. Offline map tiles are served by a custom `wildlife-tiles://` URL handler in Python, with no local web server and no open ports.

---

## 8. Errors, logging, undo and settings

### 8.1 Errors

```
WildlifeError                     base class: always has a user-friendly message
├─ ValidationError                carries field → message pairs, shown inline
├─ NotFoundError                  e.g. sighting deleted in another window
├─ ConflictError                  e.g. "this place is used by 34 sightings"
├─ PhotoError                     missing / unreadable / unsupported file
├─ ImportFileError                malformed file, with a row-by-row report
├─ BackupError / RestoreError     with what was attempted and what's safe
└─ OnlineServiceError             network unavailable / service failed
```

- Services raise these, and the UI shows `error.user_message` in the right place (inline, toast or dialog).
- **Anything else** (a genuine bug) is caught by `ui/error_handler.py`. It writes the full traceback to the log and shows "Something went wrong. Your data is safe." with [Copy details] [Open log folder]. The user never sees a traceback.
- Because every write is a transaction, an unexpected error mid-save rolls back cleanly. "Your data is safe" is literally true.

### 8.2 Logging

Python's standard `logging` writes to `logs/wildlife.log`: rotating, 1 MB × 5 files, **UTF-8 explicitly**. The spike showed the Windows console mangles non-ASCII characters by default. Normal runs log at INFO level, and a `--debug` flag switches to DEBUG. Personal data such as notes text is never logged, only IDs.

### 8.3 Undo

Each undoable service call returns an **undo action**: a small object with a description ("Delete 3 sightings") and a function that reverses it. The toast keeps the latest undo for 10 seconds (Ctrl+Z also triggers it). Longer-term safety is the recycle bin. Deliberately, there's no unlimited multi-step undo history. That's complex and error-prone, and the recycle bin covers the real risk.

### 8.4 Settings

- `config/defaults.py` defines every setting, its type and its default **in one place**.
- The `setting` table holds only values you've changed, so changing a default in a future version updates everyone who never touched it.
- Window size, position and splitter sizes are per-PC trivia, so they live in Qt's `QSettings` rather than in backups.

---

## 9. Startup sequence

1. **Single instance:** if WildLife is already running, bring that window to the front and exit.
2. Set up logging and the global error handler.
3. Resolve the data folder (first run → welcome screens).
4. Open the database → `quick_check` → migrate if needed (with backup first).
5. Load settings → apply theme → show the main window with the start page. **Target: usable within 3 s.**
6. Then, in the background: automatic backup if due, missing-photo scan, thumbnail top-up.
7. Map and chart web pages initialise **on first visit**, so the browser engine's start-up cost isn't paid at launch.

---

## 10. Testing architecture

```
tests/
├─ conftest.py           fixtures: empty_db, demo_db (built by the same generator as the
│                        spike, smaller), tmp data folder, sample photos
├─ unit/                 domain: geo, counting, validation, filters → SQL
├─ integration/          repositories + services against real temporary SQLite files:
│                        CRUD, list rules, search, stats, backup→restore, export→import,
│                        migrations from every version, photo import with EXIF fixtures
├─ ui/                   pytest-qt smoke tests: pages open (empty + full), keyboard-only add
└─ fixtures/             photos (JPEG/HEIC with/without GPS, rotated, corrupt), CSVs (good/bad)
```

The stress-test generator from the spike moves into `scripts/make_demo_data.py`. Tests use it, Phase 13 uses it at full scale, and you can use it to explore the app with realistic data.

---

## 11. Dependencies

| Package | Purpose | Licence |
|---|---|---|
| PySide6 6.12.x | UI, web engine, positioning | LGPL-3.0 |
| Pillow | Image reading, EXIF, thumbnails | MIT-CMU |
| **pi-heif** | HEIC/HEIF **decoding** (iPhone photos) | BSD-3 / LGPL wheels. Decode-only, so no GPL encoder is bundled. |
| MapLibre GL JS 5.x, pmtiles.js | Map (bundled JS) | BSD-3 |
| Apache ECharts | Charts (bundled JS) | Apache-2.0 |
| Lucide icons | Icons (bundled SVG) | ISC |
| *Dev:* pytest, pytest-qt, ruff | Tests, lint, format | MIT |
| *Build:* PyInstaller or pyside6-deploy/Nuitka, Inno Setup 6 | Packaging | GPL with a bootloader exception / Apache-2.0, LGPL / free |

Everything else (SQLite, `json`, `csv`, `zipfile`, `hashlib`, `logging`, `uuid`) comes with Python. **Not needed:** an ORM, a web server, `requests` (Qt's network access is enough), or `platformdirs` (Qt's `QStandardPaths` is enough).

---

## 12. Remaining risks → Phase 5 spikes

| Risk | Spike | If it fails |
|---|---|---|
| WebGL unavailable in QtWebEngine on your PC | Minimal MapLibre page in a `QWebEngineView` | Leaflet fallback page (same bridge messages) |
| Packaging QtWebEngine | Package "hello world + map" with PyInstaller *and* pyside6-deploy | Use whichever works; document the recipe |
| Real UKSI format: rank names, class names (e.g. Actinopteri vs Actinopterygii), size | Download UKSI, run the import into this schema | Adjust category rules and the rank mapping (data only, not schema) |
| HEIC orientation/EXIF via pi-heif | Read sample iPhone photos | Fall back to Pillow's EXIF on the converted image |
| OS grid conversion accuracy | Test `domain/geo.py` against Ordnance Survey's published test points | Use `pyproj` (larger, survey-grade) |
