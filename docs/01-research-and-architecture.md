# WildLife — Phase 1: Research, Recommended Stack & Architecture

**Date:** 11 October 2026
**Status:** Draft for your review. Nothing has been built yet.
**Next step:** You confirm or change the decisions in [section 25](#25-decisions-i-need-from-you). Then we write the product specification (Phase 2).

---

## 0. Summary

| Area | Recommendation | One-line reason |
|---|---|---|
| Language | **Python 3.13** | Every library we need fully supports it. We can move to 3.14 later with little effort. |
| UI framework | **PySide6 6.12 (Qt Widgets)** | Still the most mature and complete Python desktop toolkit. 6.12 is a Long-Term-Support release (9 Oct 2026). |
| Look and feel | Fusion style, our own **design system** (colour/spacing tokens, stylesheet, reusable components), light/dark themes, Lucide icons | Avoids the "forms placed next to each other" look of previous apps. |
| Database | **SQLite** via Python's built-in `sqlite3`, numbered SQL migrations, FTS5 full-text search | Single file, very reliable, fast at this size, and readable by other tools for decades. |
| Map | **MapLibre GL JS 5** inside a `QWebEngineView` | Built-in clustering and heat maps, handles 10,000+ points, and can work fully offline. |
| Basemap | Online: OpenFreeMap (no key needed). Offline: optional downloadable UK map pack. | Never bulk-download from openstreetmap.org, which is banned. |
| Charts | **Apache ECharts** in the same web engine. The Python side computes the numbers; the page only draws them. | Qt Charts is deprecated (Qt 6.10+). ECharts looks polished and has tooltips and dark mode. |
| Calendar | **Custom-painted Qt widgets** | No off-the-shelf Qt calendar does day/week/month/year views for this kind of data. |
| Species list | Import the **UK Species Inventory (UKSI)** (animals) as an updatable reference catalogue, plus your own species | UKSI is the authoritative UK list and the same one iRecord and the NBN use. |
| Photos | Copied into a managed library folder, named by content hash, originals never altered, thumbnail cache, HEIC support | Robust, de-duplicated, fast and easy to back up. |
| Backups | Automatic rotating snapshots using SQLite's backup API, incremental photo mirror, verified after every run | Years of records should never depend on remembering to click "Backup". |
| Tooling | `uv` (environments), `ruff` (lint/format), `pytest` + `pytest-qt`, **git** | Repeatable setup, consistent code style, tests from day one, and an "undo" for every change. |
| Packaging | One-folder build (PyInstaller **or** pyside6-deploy/Nuitka, chosen by an early test) plus an **Inno Setup** installer | Both tools are viable. QtWebEngine is the tricky part, so we test it early instead of at the end. |

The biggest design issue I found is in section 20.1: **a Windows desktop app is usually not with you when you see the animal.** The answer changes what "quick add" should be optimised for.

---

## 1. How to read this

Each section follows the same pattern: **options → trade-offs → recommendation → why**. Terms you might not know are explained the first time they appear. Sources are listed at the end.

A **spike** is a tiny throwaway experiment that answers one risky question before we depend on the answer. Several spikes are planned at the start of Phase 5.

---

## 2. Desktop framework

### 2.1 Options compared

| Option | What it is | Strengths | Weaknesses for *this* app | Verdict |
|---|---|---|---|---|
| **PySide6 – Qt Widgets** | Official Python bindings for Qt, maintained by The Qt Company. LGPL licence. | Very mature. Full desktop toolkit: tables, keyboard handling, dialogs, threading, embedded browser. 6.12 is an LTS release. Supports Python 3.10–3.15. | Large downloads (~150–250 MB with the web engine). Looks dated **unless you style it deliberately**. | ✅ **Recommended** |
| PySide6 – Qt Quick/QML | Same Qt, but the UI is written in QML, a separate declarative language. | Smoother animations and a more "app-like" feel. | You would maintain two languages (QML + Python). AI-written QML is less reliable. Harder to debug for a beginner. | Not now |
| Flet 1.0 | Python driving a Flutter UI. First stable release 15 Sept 2026. | Modern look by default. Same code can target mobile. | 1.0 is about four weeks old. Its mapping is weaker (no built-in heat map). Builds need Visual Studio and the Flutter SDK. | Interesting for a **future phone companion** |
| pywebview / NiceGUI (web UI in a desktop window) | Python backend, HTML/CSS/JS frontend, shown in Windows' built-in Edge WebView2 | Small installers. Web maps and charts are native to the browser. Good-looking. | The whole UI becomes a JavaScript project with its own build tools, so the app is two codebases in two languages. Desktop behaviours (keyboard, file dialogs, drag-drop) take more work. | Viable, but more for a beginner to maintain |
| Tauri / Electron | Rust or JavaScript desktop shells | Polished results | Not Python | ❌ |
| Toga (BeeWare) | Native widgets, BSD licence | Truly native controls | Too limited for maps, galleries and custom calendars | ❌ |
| tkinter / CustomTkinter | Built into Python | Zero install | No embedded browser for maps, weak table and image handling, hard to make look professional | ❌ |
| WinUI 3 / .NET (C#) | Microsoft's own native stack | The most "Windows-native" result | Not Python, so you would be learning a new language | ❌ (mentioned for honesty) |

### 2.2 Is PySide6 still the best choice? Yes, with conditions.

**Why it still wins:**
- It is the only Python option with a mature widget toolkit, a fast virtualised table and list framework (needed for 10,000+ rows), an embedded Chromium browser (needed for the map), good threading, and long-term vendor backing.
- **Qt 6.12 is an LTS release** (released 9 Oct 2026), so we can stay on one version for years.
- The LGPL licence is fine for personal use, and even for selling, provided we ship it as a normal folder of files (which we will).

**What went wrong before was not Qt itself; it was how Qt was used:**
- Default widgets with no design system produce "form soup".
- `QTableWidget` with thousands of rows gets slow. We'll use `QTableView` + a model, which only draws the visible rows.
- Long tasks (imports, thumbnails, backups) run on the UI thread freeze the window. We'll use background workers.

**Things that changed in Qt recently and affect us:**
- **Qt Charts is deprecated since Qt 6.10.** Its replacement (Qt Graphs) only works properly in QML, which is why charts go through the web engine instead (section 10).
- **Qt 6.8+** can switch light/dark mode per app (`styleHints().setColorScheme`), which makes theming much cleaner.
- **6.12** removed the copy constructors of `QTableWidgetItem` and similar classes, and the web engine now ships on its own release schedule. These matter only if old snippets are copied in.

### 2.3 Widgets vs QML: decided as Widgets

We get a modern look from a **design system**:

- **Design tokens.** One Python file defines colours, spacing (4/8/12/16/24/32 px), corner radius and type sizes. Every screen uses these names instead of raw numbers, so the whole app stays consistent and themes become a token swap.
- **One stylesheet (QSS)** generated from the tokens for light and dark.
- **A small component kit:** `Card`, `StatTile`, `EmptyState`, `Toast` (non-blocking message with **Undo**), `SearchField`, `FilterBar`, `SpeciesPicker`, `PhotoStrip`, `SidePanel`. Screens are built from these rather than raw widgets.
- **Icons:** Lucide SVG icons (ISC licence, consistent line style), recoloured automatically for the theme.
- **Font:** Segoe UI Variable, Windows 11's system font, so no font bundling is needed.

I deliberately **don't** recommend third-party "Fluent" widget kits. The main one (PyQt-Fluent-Widgets) is GPL-licensed, which would restrict you if you ever wanted to sell or share the app commercially, and it ties our look to someone else's release schedule.

---

## 3. UI/UX approach

### 3.1 Navigation (application shell)

```
┌───────────────────────────────────────────────────────────────────┐
│  🔍 Search sightings, species, places…  (Ctrl+K)     [+ Add  Ctrl+N]│
├────────────┬──────────────────────────────────────────────────────┤
│ ◉ Dashboard│                                                      │
│ ☰ Sightings│                 current page                         │
│ ▦ Calendar │                                                      │
│ ⌖ Map      │                                     ┌──────────────┐ │
│ ▥ Statistics│                                    │ side panel:  │ │
│ ❦ Species  │                                     │ sighting     │ │
│ ⌂ Places   │                                     │ details/edit │ │
│            │                                     └──────────────┘ │
│ ⚙ Settings │                                                      │
└────────────┴──────────────────────────────────────────────────────┘
```

- **Left sidebar** for the main areas, collapsible to icons only.
- **Global search** at the top is always available (Ctrl+K).
- **Add Sighting** is always one click or one shortcut away (Ctrl+N), from any page.
- **Side panel instead of pop-up dialogs.** Opening or editing a sighting slides in a panel on the right, so the calendar or map stays visible behind it. This fixes the "dialog stacked on dialog" problem common in previous apps.

### 3.2 The Add Sighting workflow (the most important screen)

The rule is that **only the species is required.** Everything else has a sensible default or can be filled in later.

1. Press **Ctrl+N** (or **+ Add**, or "Add on this date" from the calendar, or right-click the map and choose "Add sighting here").
2. **Species field has focus.** Type "robi" and *Robin (Erithacus rubecula)* appears first, because ranking is: species you record often → species seen recently → common UK species → everything else. Common and scientific names both match.
3. **Date and time** default to now. The time can be cleared, because "time unknown" is common.
4. **Location** defaults to the last place used today, with chips for recent places. You can also click the mini-map, type coordinates, an **OS grid reference** (e.g. `TQ 3080 8080`), or paste a Google Maps link.
5. **Count** defaults to 1, and you can type "c. 200" for an approximate count.
6. **Drop photos** on the panel. Their date, time and GPS can fill in the empty fields automatically.
7. **"More details ▸"** reveals the optional fields (sex, life stage, behaviour, evidence such as heard only, identification confidence, weather, habitat). This is called *progressive disclosure*: advanced fields exist but don't get in the way.
8. **Enter** saves, and **Ctrl+Enter** saves and starts another sighting with the same place and time. A toast appears: "Robin saved · Undo · Open".

### 3.3 UX rules we'll hold ourselves to

- Validate fields as you type, with plain-English messages next to the field ("Latitude must be between 49 and 61 for the UK — did you swap latitude and longitude?"), not after pressing Save.
- Every list or chart has a useful **empty state**: an explanation plus an action button, never a blank grey box.
- Anything that takes longer than about 300 ms shows a **loading state**.
- Destructive actions are **undoable** where possible, rather than "Are you sure?" pop-ups.
- Every action is reachable by keyboard and focus is always visible. A "Keyboard shortcuts" sheet opens with `?`.
- The same words are used everywhere: "Sighting" (never sometimes "Record" or "Observation"), "Place", "Species".

---

## 4. Mapping and heat maps

### 4.1 Options compared

| Option | How it works | Pros | Cons | Verdict |
|---|---|---|---|---|
| **MapLibre GL JS in QWebEngineView** | Open-source WebGL map library running in Qt's embedded Chromium. Python talks to it through `QWebChannel`. | Native **clustering** and **heat map** layers. Smooth with 10k+ points. Vector maps look crisp at every zoom. Can work fully offline. Actively maintained (v5.x). | Needs WebGL (see risk below). Some JavaScript to maintain. | ✅ **Recommended** |
| Leaflet in QWebEngineView | Older, simpler JavaScript map library (stable 1.9.4; 2.0 still alpha after more than a year) | Simple, no WebGL needed | Clustering and heat maps come from old plugins. Slower with very many points. Its 2.0 future is unclear. | Fallback option |
| Qt Location (QML Map) | Qt's own map item | Native Qt | QML only. Fewer map styles. Heat maps would need custom work. | ❌ |
| MapLibre Native for Qt | Native C++ MapLibre build | No browser engine needed | Hard to get working from Python, with few Python examples | ❌ for a beginner |
| folium (Python to static HTML) | Generates a one-off HTML map | Very easy | One-way only: clicking a pin can't open the sighting in the app | ❌ |

### 4.2 How the map will work

- One HTML page (`map.html`) plus `map.js`, with **MapLibre and all its files bundled inside the app**, so no internet connection is needed to load them.
- Python sends sightings as GeoJSON (a standard map-data format) together with the current filter. JavaScript draws them. Clicking a pin calls back into Python, which opens the sighting in the side panel.
- **Pins are coloured and iconed by category.** Categories are user-editable, so pin colours come from the category settings.
- **Clustering:** at low zoom, nearby pins merge into numbered circles, so 10,000 pins stay readable and fast.
- **Manual pin placement:** right-click → "Add sighting here", or drag the pin while editing.
- **Map views:** Map / Clusters / Heat / Grid squares (see 4.4), plus a choice of basemap style.

### 4.3 Basemaps (the background map)

| Source | Needs internet? | Terms | Use |
|---|---|---|---|
| **OpenFreeMap** | Yes | Free, no API key, no stated limits, donation-funded. Provided "as is" and may change. | Default online map |
| **Offline UK map pack** (Protomaps extract of OpenStreetMap, or OS Open Zoomstack) | No, once downloaded | Open data. OS Open Zoomstack covers Great Britain only and is about 2.6 GB. A Protomaps UK extract covers Northern Ireland as well, and its size depends on the maximum zoom. | Optional download in Settings → Maps |
| tile.openstreetmap.org | Yes | **Bulk/offline downloading is forbidden** and blocked without notice. Apps must identify themselves. | ❌ We won't use it |
| Satellite imagery | Yes | Most free satellite sources restrict app use | Out of scope for v1; revisit later |

The offline map pack is served to the map page by a small **custom URL handler** in Python, so the page asks for `wildlife-tiles://…` and Python reads the tile from the local file. This needs no local web server and opens no network ports.

**If there is no internet and no map pack,** the map still shows your pins on a plain background with a friendly banner: "Map background unavailable offline — download the UK map pack in Settings."

### 4.4 Heat maps: what question are we answering?

A plain heat map answers "where do I *go* most", not "where is the *wildlife* richest". The places you visit most will always glow brightest; ecologists call this *observer effort bias*. So we'll offer three honest views, all of which respect the active filters:

1. **Sighting density:** the classic heat map, weighted either per sighting or by number of animals.
2. **Species richness by grid square:** count of *different* species in each 1 km OS grid square (or 2 km "tetrad", the standard UK recording unit). This is the best answer to "where have I seen the most wildlife".
3. **Visits vs richness:** squares coloured by species per visit, which points to underrated spots.

### 4.5 Risk: WebGL availability

MapLibre needs WebGL. On a few machines (old GPU drivers, remote desktop, some VMs), Chromium disables WebGL, and its old software fallback is being removed. The result is a **blank map**.

**Mitigation:**
- **Spike** in Phase 5 to confirm WebGL works on your PC inside QWebEngine.
- The map page detects WebGL failure and shows a clear message instead of a blank box.
- A Leaflet-based fallback can be added later if it is ever needed.

---

## 5. Data storage

### 5.1 Why SQLite (and not alternatives)

| Option | Verdict | Why |
|---|---|---|
| **SQLite** | ✅ | Single file, no server, transactional (all-or-nothing writes), extremely well tested, and readable by many tools for decades. 10,000 sightings is tiny for it (a few MB). |
| PostgreSQL / MySQL | ❌ | Server software to install and maintain, for no benefit to a single user |
| JSON/CSV files | ❌ | No transactions, no indexes, and they become corrupt and slow at scale |
| DuckDB | ❌ | Excellent for analytics, but designed for read-heavy use, not everyday editing |

### 5.2 SQLite settings we'll use (and what they mean)

| Setting | What it does |
|---|---|
| `journal_mode=WAL` | Write-Ahead Logging. Reading doesn't block writing, and a crash mid-write can't corrupt the database. |
| `synchronous=FULL` | Waits until data is really on disk. This is slightly slower, but at our write rate (a few saves a minute) the cost is unnoticeable, and it also protects against power cuts. **Data safety over microseconds.** |
| `foreign_keys=ON` | Enforces relationships, so a photo can't point to a sighting that doesn't exist. **It is off by default in SQLite and must be set on every connection.** |
| `STRICT` tables | Stops SQLite storing text in a number column, which it otherwise silently allows. |
| `busy_timeout=5000` | If two things try to write at once, the second waits instead of crashing. |

### 5.3 How the Python code talks to the database

| Option | Verdict |
|---|---|
| **Built-in `sqlite3` + small "repository" modules + plain SQL** | ✅ **Recommended** |
| SQLAlchemy 2.0 + Alembic | Powerful but heavy. Two big libraries to learn, and SQLite migrations still need workarounds ("batch mode"). |
| Peewee ORM | Simpler, but a third-party abstraction you'd have to learn, and statistics queries end up in SQL anyway |

**Why plain SQL:** the schema is moderate (about 10 tables), and statistics are naturally SQL. SQL is a skill that transfers to every other project. Debugging means "look at the query", not "look at what the ORM generated". A **repository** is simply one Python module per table group (e.g. `sightings_repo.py`) that holds all the SQL for it, so SQL never leaks into UI code.

**Migrations** (schema changes over time) work as numbered files: `0001_initial.sql`, `0002_add_outings.sql`, and so on. The database remembers its version (`PRAGMA user_version`). On startup the app **backs up the database first**, then applies any newer files inside a transaction. Tests then check that upgrading from *every* old version works.

### 5.4 Draft data model

```
category ──< taxon ──< sighting >── place
                         │  │
                         │  └──< photo
                         └── outing (optional)
```

| Table | Purpose | Key columns (draft) |
|---|---|---|
| `category` | User-facing groups (Bird, Mammal, Butterfly…). **Editable, not hard-coded.** | name, colour, icon, sort_order |
| `taxon` | Species catalogue: UKSI reference names plus your custom species. Covers species, subspecies and higher ranks (so "gull sp." is possible). | uksi_key (TVK), scientific_name, common_name, rank, parent_id, category_id, is_custom, is_hidden |
| `taxon_name` | Extra common names and synonyms, for search | taxon_id, name, kind |
| `place` | Saved, reusable sites ("Rainham Marshes") | name, lat, lon, uncertainty_m, notes |
| `outing` | *Optional* trip or visit grouping sightings (date, place, weather, start/end time, notes) | **Decision needed, see section 25** |
| `sighting` | One species seen at one time and place | uuid, taxon_id, date, time (nullable), lat, lon, uncertainty_m, place_id, location_text, count, count_type (exact/approx/min), sex, life_stage, evidence (seen/heard/signs…), confidence, notes, created/updated/**deleted_at** |
| `photo` | Photos attached to a sighting | uuid, sighting_id, file_name (hash), original_name, taken_at, gps lat/lon, width, height, rotation, caption, sort_order |
| `sighting_fts` | Full-text search index (maintained automatically) | species names, place, notes |
| `setting` | User preferences (lives in the DB, so it is included in backups) | key, value |

**Important choices in this model:**
- **Integer IDs inside the database, plus a UUID** (a globally unique ID) on sightings and photos. The UUID makes future import, merging or phone sync safe without ID collisions.
- **Dates are stored as ISO text** (`2026-10-11`), and **time is a separate nullable column**, because "date known, time unknown" is real.
- **UK local time** (BST/GMT) is what you saw on your watch, and is what time-of-day statistics need.
- **Soft delete:** deleting sets `deleted_at` instead of erasing. A "Recently deleted" bin allows restore, and items are purged after 30 days.
- **Indexes** on date, species + date, place, and photo → sighting, so filtered queries stay fast at 100k+ rows.
- **Categories map from taxonomy by default** (class Aves → Bird, order Lepidoptera → Butterflies & Moths), but you can override them per species. This avoids keeping two competing classification systems.

### 5.5 Search

- **SQLite FTS5** (full-text search) over species names, scientific names, place names and notes. It returns results in milliseconds even at 100k+ rows. A *trigram* index also allows "middle of the word" matches (e.g. "finch" finds "Goldfinch").
- The search box understands simple dates such as "May 2025" and "2024".
- **One shared filter object** (`SightingFilter`: species, category, date range, place or area, count, has photos, evidence…) is used by the Sightings list, Map, Calendar, Statistics *and* Export. That means a filter means the same thing everywhere, "Export what I'm looking at" comes for free, and saved filters become possible later.

---

## 6. Species database

### 6.1 Should the app have its own species database? Yes, but don't hand-build it.

The **UK Species Inventory (UKSI)**, run by the Natural History Museum, is the authoritative list of UK species. iRecord and the NBN Atlas use it. It is published via GBIF as a Darwin Core Archive under **CC BY 4.0**, which allows reuse with attribution. One NHM portal copy says "licence not specified", so we'll confirm and attribute before distributing anything.

### 6.2 Recommended approach

1. A **build-time script** (`scripts/build_species_catalogue.py`) downloads UKSI, keeps **animals only** (birds, mammals, reptiles, amphibians, fish, insects, arachnids, molluscs and so on), and writes a compact reference file that ships with the app.
2. On first run, or when you choose to update, it's imported into `taxon`. Each row keeps its **UKSI key (TVK)**, so later updates can rename species (taxonomy changes over time) **without breaking your sightings**.
3. **Your own species** (e.g. "Unidentified bat", or a local form) are `is_custom = 1` and are never overwritten by updates.
4. **Smart autocomplete ranking** keeps tens of thousands of obscure beetles out of your way. The order is: your frequently recorded species → species you've recorded → a "commonly recorded UK animals" priority list → everything else. You can also **hide** taxa you'll never want.

*Why not a hand-curated list?* It would be incomplete, contain errors, and go out of date as names change. *Why not query an online service?* Online lookups break offline-first. UKSI gives a complete, authoritative, offline list that can still be updated.

---

## 7. Photo management

| Decision | Recommendation | Why |
|---|---|---|
| Where photos live | **Copied into the app's photo library folder** (`photos/2026/10/…`) | Linking to wherever the file happens to be breaks the moment you tidy your Pictures folder |
| File naming | **Content hash** (SHA-256) + original extension, with the original name kept in the DB | Automatic duplicate detection. A file never changes once stored, which makes backups simple and incremental. |
| Stored in the database? | **No.** Only metadata goes in the DB. | Image data inside SQLite bloats the DB and makes every backup copy every photo again |
| Originals | **Never modified.** Rotation is stored as a setting and applied when displayed. | Non-destructive and reversible |
| Thumbnails | Two sizes (grid and preview) in a `thumbnails/` cache, generated in the background | Fast galleries. The cache can be deleted and rebuilt, so it isn't backed up. |
| Formats | JPEG, PNG, WebP, plus **HEIC** (iPhone) via `pillow-heif` | iPhone photos are HEIC by default |
| Metadata | Read EXIF date taken, GPS and orientation with Pillow, and offer them to fill in the sighting | "Drop photo → date, time and location filled in" is a big time-saver |
| Missing files | A health check flags missing or corrupt files and offers "Locate…" or "Remove reference" | Handles broken references gracefully |
| Export privacy | Option to **strip GPS from exported photos** | Protects your home location and sensitive sites when sharing |

Large libraries stay smooth because thumbnails load on demand in the background and are kept in memory with a size limit (`QPixmapCache`).

---

## 8. Location and GPS

### 8.1 The reality on Windows

Most Windows PCs and laptops **have no GPS chip**. Windows' location service usually estimates position from nearby Wi-Fi networks. Qt can read it (`QtPositioning`), but accuracy ranges from roughly 20 m to several km, and it depends on privacy settings. So "Use my location" will be a **convenience** that always shows its accuracy, not the main method.

### 8.2 Ways to set a location (in order of usefulness)

1. **Photo GPS:** taken from your phone or camera photo's EXIF data.
2. **Click on the map** in the editor.
3. **Saved places:** pick "Rainham Marshes" from recent or nearby places.
4. **Type it:** decimal lat/lon, degrees-minutes-seconds, **OS grid reference** (`TQ308808`), or a pasted Google Maps / what3words-style link, with the format detected automatically.
5. **Current location** from Windows, with its accuracy shown.

### 8.3 OS grid references

UK recorders (iRecord, county recorders, the BSBI) work in **British National Grid references**, and the precision of a grid reference *is* its uncertainty: a 6-figure reference means a 100 m square. We'll:
- store WGS84 latitude and longitude, plus **uncertainty in metres**;
- display and accept OS grid references alongside latitude and longitude;
- convert using a small tested module with the standard Helmert transform (accurate to about 5 m, more than enough for 10–100 m grid squares). The alternative is the large `pyproj` library if we ever need survey-grade accuracy.

---

## 9. Calendar

Qt's `QCalendarWidget` is a date *picker*, not a calendar application, and no Python library offers good day/week/month/year views. So we'll build **custom-painted views** that all share one fast query ("sightings per day for this range").

| View | Design |
|---|---|
| **Year** | 12 small month grids where each day is shaded by number of sightings, like GitHub's activity grid. You can see your active wildlife-watching seasons at a glance. |
| **Month** | Full grid. Each day shows a count badge, up to 3 category-coloured dots, and the "headline" species (rarest, or first-of-year). |
| **Week** | 7 columns of **sighting cards ordered by time**. Sightings are moments, not appointments, so an Outlook-style hour grid would mostly be empty space. |
| **Day** | A timeline list with photos, plus a mini-map of that day's sightings |

Interaction: click a day to list its sightings in the side panel. Double-click a sighting to open it. Right-click a day → "Add sighting on this date". Arrow keys move between days, `T` jumps to today, and the filter bar applies here too (e.g. "only butterflies").

---

## 10. Statistics and charts

### 10.1 Chart technology

| Option | Verdict | Notes |
|---|---|---|
| Qt Charts | ❌ | Deprecated since Qt 6.10 |
| Qt Graphs | ❌ | Its replacement is designed for QML, and embedding it in a Widgets app is awkward |
| matplotlib | Fallback | Mature and pure Python, but looks dated without effort, has weak hover tooltips, and is slow to import |
| pyqtgraph | ❌ | Great for scientific real-time plots, but the "lab instrument" look is wrong for this app |
| **Apache ECharts in QWebEngineView** | ✅ | Polished, interactive tooltips, light/dark themes, built-in calendar heat map and PNG export. We already ship the web engine for the map, so it adds almost no size. |

**Rule that keeps this maintainable:** all numbers are computed in **Python/SQL** (fully testable). The chart page is a "dumb renderer" that receives JSON and draws it. No business logic lives in JavaScript.

The headline numbers (total sightings, species count and so on) are **native Qt `StatTile` widgets**, not charts.

### 10.2 Which statistics are worth showing

Every chart must answer a question you would actually ask:

| Question | Visual |
|---|---|
| How many species have I seen, and how is my list growing? | **Cumulative species curve** (life list over time) |
| What's new this year? | "Year list" and **first-of-year** table, with lifers highlighted |
| What do I see most? | Top-species bar chart (by sightings, or by individuals) |
| When am I most active, and when is wildlife most active? | Month × category heat table, plus a seasonal comparison |
| What time of day are my sightings? | Hour-of-day histogram (optionally relative to sunrise, which is computed offline) |
| Is this year better than last? | Year-over-year line (sightings and species by month) |
| Where are my best spots? | Top places by **species richness**, not just sighting count |
| When did I first and last see each species? | Sortable species table: first seen, last seen, total sightings, best count |

The filter bar applies to all of these (e.g. "Birds, 2025 only").

---

## 11. Search and filtering

Covered in section 5.5. In short: **FTS5 search** plus **one reusable `SightingFilter`** shared by every screen, a visible "filter chips" bar with **Clear all**, and results shown in a virtualised table that stays fast at 100k rows.

---

## 12. Backup, restore and data integrity

The layers of protection, from most frequent to least:

1. **Transactions and validation.** Every save is all-or-nothing, and invalid data (e.g. latitude 200) is rejected with a clear message before it reaches the database.
2. **Undo and a recycle bin** for deleted sightings and photos (soft delete, 30 days).
3. **Automatic database snapshots** using SQLite's **online backup API**, which takes a consistent copy even while the app is running. Copying the file directly can produce a corrupt backup. Snapshots run daily and on exit, and are kept on a rotating schedule (e.g. last 7 daily, 4 weekly, 12 monthly).
4. **Incremental photo backup.** Photos never change once stored (hash names), so each backup copies only *new* photos to a mirror folder.
5. **Verification after every backup:** open the copy, run `PRAGMA integrity_check` + `foreign_key_check`, and compare record counts. A backup that fails verification is reported, not silently kept.
6. **Pre-migration backup** before any schema upgrade.
7. **Restore** validates the backup first, then **saves a safety copy of your current data**, then swaps. Even a restore can be undone.
8. **A health check on startup** (`quick_check`) plus a full check from Settings → Data.
9. **Backup location warnings.** We recommend a second drive or a cloud-synced folder for *backups*, and warn if the *live* data folder is inside OneDrive, because cloud sync can corrupt an open SQLite database.
10. **"Last backup: 2 days ago"** is shown on the dashboard if backups fall behind.

---

## 13. Import and export (data portability)

| Format | Purpose |
|---|---|
| **CSV** (UTF-8 with BOM so Excel opens it correctly) | Spreadsheets; exports the current filter or everything |
| **JSON** | Full-fidelity export of everything (sightings, places, species, photo metadata) for re-import or other software |
| **Darwin Core-style CSV** | The international biodiversity data standard (`eventDate`, `decimalLatitude`, `coordinateUncertaintyInMeters`, `scientificName`…), plus an iRecord-friendly column set, so you can **submit your records to UK conservation schemes** if you want to |
| **GeoJSON / KML** | Open your sightings in Google Earth or GIS tools |
| **Full archive (.zip)** | Database snapshot + photos + a README explaining the contents, so the data is never trapped |

**Import** uses a wizard: choose file → match columns → **preview with a validation report** (e.g. "3 rows have unknown species → map them / create custom / skip") → duplicate detection → import inside **one transaction**, so a malformed file can never leave half-imported data.

---

## 14. Offline-first

Everything works offline: database, photos, species list, calendar, statistics, search, backups, and the map with pins (plus the background map if the map pack is installed).

Optional online extras, each failing gracefully with a clear message:

| Feature | Service | Notes |
|---|---|---|
| Online map background | OpenFreeMap | Free, no key |
| "Fill in weather" for a past sighting | Open-Meteo historical API | Free for non-commercial use, no key, CC BY 4.0 (needs attribution) |
| Species list update | UKSI download | Manual "Check for update" |

All network calls run in the background with short timeouts, so the UI never freezes waiting for the internet.

---

## 15. Settings

| Group | Settings |
|---|---|
| Appearance | Theme (System / Light / Dark), compact or comfortable density |
| Recording defaults | Default count, default evidence, "remember last place for N hours", coordinate format (lat/lon or OS grid ref) |
| Map | Default basemap, start location and zoom, offline map pack management |
| Photos | Library location, strip GPS on export, thumbnail cache size and "rebuild" |
| Backup | Backup folder, frequency, retention, "Back up now", "Restore…", last result |
| Data | Data folder location, health check, recycle bin, import/export, species list update |
| About | Version, licences and attributions (UKSI, OpenStreetMap, Open-Meteo…), log folder |

User preferences live in the database, so they are included in backups. Window size and position live in Qt's `QSettings`, which is per-PC and doesn't matter if lost.

---

## 16. Performance plan

We'll generate a realistic **stress dataset (20,000 sightings, 5,000 photos)** early and test against it. Problems show up long before you have that much real data.

| Risk area | Mitigation |
|---|---|
| Startup time | Map and statistics pages (and the web engine) load on **first visit**, not at launch. Target: window usable in under 2 seconds. |
| Long lists | `QTableView` + model (only visible rows are drawn), with paged loading |
| Images | Background thumbnail generation, an in-memory cache, never loading full-size images into lists |
| Map | GeoJSON for 20k points is about 2–3 MB. MapLibre clusters on the GPU, and filtering re-queries SQL. |
| Statistics | SQL aggregate queries with indexes, computed in a background worker |
| Search | FTS5 index |
| Responsiveness | All slow work (import, export, backup, thumbnails, network) runs on `QThreadPool` workers. The UI thread only draws. |

---

## 17. Testing strategy

Testing is built in from Phase 5, not saved for Phase 13.

| Layer | Tool | Examples |
|---|---|---|
| Domain logic | `pytest` | Grid reference ↔ lat/lon conversions against known points, validation rules, filter → SQL building |
| Database | `pytest` + temporary databases | Create/edit/delete/soft-delete sightings, foreign keys, FTS search results, **migrations from every past version** |
| Services | `pytest` | Backup → restore round-trip, export → import round-trip ("what goes out comes back identical"), photo import with EXIF fixtures, malformed CSV handling |
| UI | `pytest-qt` | Smoke tests: each page opens with empty and full data, Add Sighting with keyboard only, filters update the list |
| Manual | Checklist per phase | Written test script for things automation can't judge (looks, feel, flow) |
| Test data | `scripts/make_demo_data.py` | Realistic UK species, seasonal patterns, real place names, and photos with EXIF |

Code quality: `ruff` (formatting + linting) and type hints throughout, with optional `pyright` checks later.

---

## 18. Error handling and logging

- A **global error handler** catches anything unexpected and shows: "Something went wrong while saving the sighting. Your data is safe. [Copy details] [Open log folder]". There are **never raw tracebacks**.
- **Expected problems get specific messages**, for example "This photo is missing — it was at …", "This file doesn't look like a WildLife export", "Backup failed: the backup drive isn't connected".
- **Rotating log files** in the app data folder record full technical details for debugging.
- Services raise a small set of custom error types (`ValidationError`, `ImportError`, `BackupError`…), and the UI turns them into friendly messages in one place.

---

## 19. Packaging for Windows

| Option | Pros | Cons |
|---|---|---|
| **PyInstaller (one-folder)** | Most widely used, fast builds, good PySide6/WebEngine support | More antivirus false positives (especially in one-file mode) |
| **pyside6-deploy (Nuitka)** | Qt's officially recommended tool. Compiles to C, giving smaller and faster output with fewer antivirus flags. Configurable from `pyproject.toml` in 6.12. | Slower builds. WebEngine packaging has been fiddly for some users. |
| Briefcase (BeeWare) | Produces MSI installers | Less tested with PySide6 + WebEngine |

**Recommendation:**
- In **Phase 5, package a "hello world + web map" app with both tools** and keep whichever works cleanly. Discovering packaging problems in Phase 14 is a classic and painful mistake.
- Use **one-folder** output (not one-file), wrapped in an **Inno Setup** installer that installs per-user with no admin rights and adds Start-menu shortcuts and an uninstaller.
- Expected size: about 150–250 MB installed. The Chromium web engine is about half of that, which is the price of a good map.

**Code signing** stops the "Windows protected your PC" warning. As of this research, Microsoft's cheap Artifact Signing (~$10/month) is **not available to individuals in the UK** (organisations only). A traditional OV certificate costs about $150–300/year. **For personal use you don't need one**: you click "More info → Run anyway" once. We'll revisit if you ever distribute it.

**Licensing:** PySide6 (LGPL), MapLibre (BSD), ECharts (Apache-2.0), Pillow (MIT-CMU) and Lucide (ISC) are all compatible with personal use **and** with selling the app later, provided we keep the one-folder layout and include the licence notices.

---

## 20. Things you may have overlooked

1. **Where does "quick add when outdoors" actually happen?** (The biggest one.) A desktop app is rarely in the field. Realistic workflows are:
   - **(a)** a Windows laptop or tablet carried outdoors;
   - **(b)** photos taken on your phone, then entered at home (so **"create sightings from photos"** should be a first-class feature: drop 30 photos → each becomes a draft sighting with date, time and GPS filled in, and you just pick species);
   - **(c)** a **phone companion** later (e.g. a Flet or web app that exports a file the desktop imports).

   The architecture supports (c) from day one through UUIDs and a clean import format, but I recommend we **don't build a phone app in v1**.
2. **Version control (git).** This folder isn't a git repository yet. Git is your "undo for the whole project": if an AI-written change breaks something, you can see exactly what changed and roll back. Strongly recommended before any code is written.
3. **Outings or visits.** Birders think in trips ("Sunday at Titchwell: 47 species"). An optional outing groups sightings and holds the weather, so it isn't re-typed per sighting. It also enables "species per visit" statistics.
4. **Location uncertainty and grid references** (section 8). "Somewhere in Epping Forest" and "this exact tree" are very different data.
5. **Unknown time, approximate counts ("c. 200"), identification confidence, and heard-only records** are all common in real recording.
6. **Life list, year list, "firsts" and lifers.** This is what keeps people using a wildlife app for years.
7. **Observer-effort bias in heat maps** (section 4.4).
8. **Sensitive locations:** your home garden, or a rare species' nest site. Exports should be able to **blur coordinates** (e.g. to 1 km) and strip photo GPS.
9. **Live data in a OneDrive-synced folder** can corrupt the database (section 12).
10. **Taxonomy changes:** species get renamed or split. Keeping the UKSI key means your records follow the name change automatically.
11. **Unidentified sightings** ("gull sp.", "unidentified bat") must be recordable, which a taxon at a higher rank allows.
12. **Bulk editing:** e.g. "these 20 sightings were actually Common Darter, not Ruddy". Without it, corrections are painful.
13. **Contributing to science:** iRecord-compatible export lets your records help UK conservation. It is optional, but it adds meaning to the hobby.
14. **Accessibility:** keyboard navigation, focus visibility, readable contrast in both themes, and no information conveyed by colour alone (pins use icons as well as colours).

---

## 21. Problems with the proposed design (constructive critique)

| Issue in the brief | Why it's a problem | Proposed change |
|---|---|---|
| "GPS capture where possible" | Usually impossible or inaccurate on Windows | Prioritise photo GPS, map click, saved places and grid refs, and keep "current location" as an extra (section 8) |
| Weather, temperature, conditions, habitat, visibility on every sighting | Typing weather 15 times for one walk is the opposite of quick | Store conditions on the **outing**, or offer "fill from Open-Meteo". Keep only habitat per sighting, and keep it optional. |
| Backup is Phase 11 | You'll start entering **real** data after Phase 6. Five phases without automatic backups is a real risk. | Move **automatic snapshot backups into Phase 6**. Phase 11 adds restore UI, export and import. |
| Testing is Phase 13 | Bugs found late are expensive. AI-written code especially needs tests at every step. | Tests in every phase. Phase 13 becomes "hardening and stress testing". |
| Packaging is Phase 14 | QtWebEngine packaging is the riskiest technical part | Packaging spike in Phase 5, final installer in Phase 14 |
| UI polish is Phase 12 | Polish added at the end becomes paint over inconsistent screens | Design system and components in Phases 4–5. Phase 12 is an audit and refinement, not a redesign. |
| Photos are Phase 9, but Add Sighting (Phase 6) needs photo attach | Add Sighting would be built twice | Photo storage plus basic attach in Phase 6. The gallery, viewer and EXIF features stay in Phase 9. |
| Category plus scientific taxonomy | Two classification systems drift apart | Categories derived from taxonomy by default, with user overrides (section 5.4) |
| Heat map with a small dataset | Early on it will look sparse or misleading | Offer the grid-square view and point clusters too, and explain what each shows |
| Many optional fields from day one | Every extra field slows the main workflow | Progressive disclosure ("More details ▸"), with only species required |

---

## 22. Final recommended stack

| Layer | Choice | Version policy |
|---|---|---|
| Language | Python | 3.13.x (installed per project via `uv`; your current 3.12.0 stays untouched) |
| UI | PySide6 (Qt Widgets) incl. QtWebEngine and QtPositioning | 6.12.x LTS, pinned |
| Database | SQLite (bundled with Python), FTS5 | WAL, FULL sync, STRICT tables, foreign keys on |
| Images | Pillow + pillow-heif | Pinned |
| Map | MapLibre GL JS 5.x + pmtiles.js, vendored (bundled, no CDN) | Pinned |
| Charts | Apache ECharts, vendored | Pinned |
| Icons | Lucide SVG | Vendored subset |
| HTTP (optional features) | Qt's `QNetworkAccessManager` (no extra library) | — |
| Dev tooling | uv, ruff, pytest, pytest-qt, git | Latest |
| Packaging | PyInstaller **or** pyside6-deploy (decided by spike) + Inno Setup 6 | — |

---

## 23. Proposed architecture

### 23.1 The layers (and the one rule)

```
┌───────────────────────────────────────────────┐
│  UI  (ui/)          screens, components, theme │  knows Qt widgets
│        │  calls                                │
│        ▼                                       │
│  SERVICES (services/)  "use cases":            │  plain Python,
│   save sighting, search, stats, backup, import │  no widgets → easy to test
│        │  calls                                │
│        ▼                                       │
│  DATA (data/)   database connection,           │  all SQL lives here
│                 repositories, migrations       │
├───────────────────────────────────────────────┤
│  DOMAIN (domain/)  dataclasses + rules         │  used by every layer
│  Sighting, Taxon, Place, Photo, SightingFilter │  pure Python, no Qt, no SQL
└───────────────────────────────────────────────┘
```

**The rule:** arrows only point down. UI code never contains SQL. Services never create widgets. The domain layer depends on nothing.

**Why it helps you:** when something breaks, the layer tells you where to look. A wrong number in a chart means the stats service; a misaligned button means the UI. It also means 80% of the logic can be tested without opening a window.

We deliberately **won't** add abstract base classes, dependency-injection containers or "interfaces for everything". There is one simple layer per concern, and that's all.

### 23.2 Project folder (source code)

```
WildLife/
├─ pyproject.toml           # project definition, dependencies, tool settings
├─ uv.lock                  # exact versions of every dependency (reproducible installs)
├─ README.md
├─ docs/                    # research, spec, architecture, decision records
├─ src/wildlife/
│  ├─ __main__.py           # "python -m wildlife" starts the app
│  ├─ app.py                # startup: logging, paths, DB, theme, main window
│  ├─ config/
│  │  └─ paths.py           # where data/photos/backups/logs live
│  ├─ domain/               # plain data classes and rules (no Qt, no SQL)
│  │  ├─ models.py          # Sighting, Taxon, Place, Photo, Category…
│  │  ├─ filters.py         # SightingFilter (shared by every screen)
│  │  ├─ geo.py             # lat/lon ↔ OS grid ref, distance, validation
│  │  └─ errors.py          # friendly error types
│  ├─ data/
│  │  ├─ db.py              # open connection, apply PRAGMAs, transactions
│  │  ├─ migrations/        # 0001_initial.sql, 0002_….sql
│  │  └─ repositories/      # sightings.py, taxa.py, places.py, photos.py, settings.py
│  ├─ services/             # the app's "verbs"
│  │  ├─ sightings.py       # create / update / delete / restore
│  │  ├─ search.py          # FTS + filters
│  │  ├─ stats.py           # all statistics queries
│  │  ├─ photos.py          # import, EXIF, thumbnails, health check
│  │  ├─ backup.py          # snapshot, verify, rotate, restore
│  │  ├─ exchange.py        # import/export CSV, JSON, Darwin Core, GeoJSON
│  │  ├─ species_catalogue.py # UKSI import/update, ranking
│  │  └─ online.py          # optional: weather lookup (fails gracefully)
│  ├─ ui/
│  │  ├─ main_window.py     # shell: sidebar, search bar, page switching
│  │  ├─ theme/             # tokens.py, stylesheet builder, icons/
│  │  ├─ components/        # Card, StatTile, EmptyState, Toast, SpeciesPicker…
│  │  ├─ pages/             # dashboard, sightings, calendar, map, stats, species, places, settings
│  │  ├─ panels/            # sighting side panel (view/edit)
│  │  ├─ web/               # QWebEngine bridge + map.html/charts.html + vendored JS
│  │  └─ workers.py         # background task helper (keeps UI responsive)
│  └─ resources/            # species catalogue file, app icon, licences
├─ tests/
│  ├─ unit/  integration/  ui/
│  └─ fixtures/             # sample photos with EXIF, sample CSVs (good & malformed)
├─ scripts/                 # build_species_catalogue.py, make_demo_data.py
└─ packaging/               # build config + installer.iss (Inno Setup)
```

### 23.3 Your data folder (separate from the program)

```
%LOCALAPPDATA%\WildLife\          (location changeable in Settings)
├─ wildlife.db         # the database (+ -wal/-shm helper files while open)
├─ photos/2026/10/…    # your photo library (hash-named originals)
├─ thumbnails/         # cache, safe to delete
├─ maps/               # optional offline map pack
├─ logs/               # rotating log files
└─ backups/            # default backup location (we'll recommend another drive)
```

Keeping the **program** and **your data** separate means reinstalling or upgrading the app never touches your records.

---

## 24. Revised development roadmap

Your 14 phases are kept, with the changes from section 21 applied. Each phase ends with: what was done, what was learned, problems found, recommendation, and your go-ahead.

| # | Phase | Main deliverables | "Done when…" |
|---|---|---|---|
| 1 | **Research** ✅ | This document | You approve the stack and architecture |
| 2 | Product specification | Feature list with v1 / later split, field list, user workflows, glossary | We agree exactly what v1 does and doesn't do |
| 3 | Architecture & database | Final schema (SQL), module list, filter design, error and backup strategy | Schema reviewed, with sample queries for every screen |
| 4 | UI/UX design | Navigation, wireframes of every screen, design tokens, component list, light/dark palettes | You've seen and approved mock-ups |
| 5 | Foundation | git, `uv` project, ruff, pytest. **Spikes:** WebEngine + MapLibre + WebGL on your PC; packaging hello-world; UKSI import. App shell (sidebar, theme, empty pages), DB + migrations, logging, error handler, demo data generator | App launches, switches theme, passes tests, and a packaged test build runs on your PC |
| 6 | Core sightings | Add/edit/view/delete (soft) + undo, species picker, places, list with filters, global search, **basic photo attach**, **automatic backups** | You can safely record real sightings |
| 7 | Calendar | Year/month/week/day views, filters, add-from-date | Browse 20k demo sightings smoothly |
| 8 | Map | MapLibre map, category pins, clustering, click-to-open, place-pin, filters, heat/grid views, offline handling | All views work online and offline |
| 9 | Photos | Gallery, full-screen viewer, rotation, EXIF autofill, "sightings from photos", HEIC, health check | Drop 30 phone photos → 30 draft sightings |
| 10 | Statistics | Dashboard tiles, stats page, life/year lists, charts from section 10.2 | Every chart answers a listed question |
| 11 | Backup/import/export | Restore UI, verification report, CSV/JSON/Darwin Core/GeoJSON export, import wizard, full archive | Round-trip tests pass, and malformed files are handled |
| 12 | Polish | Full UI/UX audit against the section 3.3 checklist, accessibility pass | Audit issues fixed |
| 13 | Hardening | Stress tests (20k+), failure-injection tests (missing photos, corrupt DB, full disk), manual test script | No known data-loss paths |
| 14 | Packaging | Final build, installer, upgrade-in-place test, uninstall keeps data | Installs cleanly on a clean Windows account |

---

## 25. Decisions I need from you

1. **Field workflow:** will you mostly (a) carry a Windows laptop or tablet outdoors, (b) photograph on your phone and enter later, or (c) both? This sets how much priority "sightings from photos" gets.
2. **Outings:** include optional outings (trip grouping + weather) in v1? *My recommendation: yes, but kept optional.*
3. **Species catalogue:** full UKSI animal list with smart ranking (recommended), or a smaller curated starter list?
4. **Offline map pack:** is a one-off 1–3 GB UK map download acceptable, or is online-only background mapping fine for v1? Pins work offline either way.
5. **Git:** OK to initialise a git repository? A private GitHub backup of the *code* is optional.
6. **Future plans:** is this purely personal, or might you share or sell it one day? This affects licensing choices and code signing.
7. **Previous app lessons:** if you can point me at your reselling app's folder, I can review its code and list concrete lessons (structure, UI patterns, bugs), rather than the general lessons I've assumed here.

---

## 26. Sources

**Framework**
- [Qt for Python 6.12 release (9 Oct 2026)](https://www.qt.io/blog/qt-for-python-release-6.12-is-here)
- [PySide6 release notes](https://doc.qt.io/qtforpython-6/release_notes/pyside6_release_notes.html) · [Qt for Python development notes / compatibility matrix](https://wiki.qt.io/Qt_for_Python_Development_Notes) · [PySide6-Essentials on PyPI](https://pypi.org/project/PySide6-Essentials/)
- [Which Python GUI library should you use in 2026? (pythonguis)](https://www.pythonguis.com/faq/which-python-gui-library/) · [tkinter vs PySide6 vs Flet (2026)](https://www.pistack.xyz/posts/2026-08-30-python-gui-frameworks-tkinter-pyside6-flet-comparison/)
- [Flet 1.0 release coverage](https://runtimewire.com/article/flet-1-0-python-cross-platform-apps-feodor-fitsner) · [Flet Windows packaging docs](https://docs.flet.dev/publish/windows)
- [Qt Charts deprecated (obsolete members)](https://doc.qt.io/qt-6/qtcharts-module-qtcharts-obsolete.html) · [Qt Graphs widget limitations discussion](https://forum.qt.io/topic/163097/qt-graphs-lacking-functionalities-axes-range/18)
- [Qt forum: switching light/dark color scheme (6.8 setColorScheme)](https://forum.qt.io/topic/163228/switching-between-a-light-and-dark-color-scheme) · [QTBUG-112657](https://bugreports-test.qt.io/browse/QTBUG-112657)

**Maps**
- [OSMF tile usage policy](https://operations.osmfoundation.org/policies/tiles/) · [OSM Tile Clients wiki](https://wiki.openstreetmap.org/wiki/Tile_Clients)
- [MapLibre GL JS clustering example](https://maplibre.org/maplibre-gl-js/docs/examples/cluster/) · [Leaflet download / versions](https://leafletjs.com/download) · [Leaflet 2.0 alpha announcement](https://leafletjs.com/2025/05/18/leaflet-2.0.0-alpha.html)
- [Offline maps with Protomaps in MapLibre](https://blog.wxm.be/2024/01/14/offline-map-with-protomaps-maplibre.html) · [maplibre-offline-pmtiles](https://github.com/makinacorpus/maplibre-offline-pmtiles) · [MapLibre Flutter PMTiles notes](https://maplibre.org/flutter-maplibre-gl/advanced/pmtiles/)
- [OS Open Zoomstack vector tiles](https://docs.os.uk/os-downloads/products/maps-and-imagery-portfolio/os-open-zoomstack/os-open-zoomstack-getting-started-guide/zoomstack-vector-tiles) · [OS Open Zoomstack docs](https://docs.os.uk/os-downloads/products/maps-and-imagery-portfolio/os-open-zoomstack)
- [OpenFreeMap](https://openfreemap.org) · [Simon Willison on OpenFreeMap](https://simonwillison.net/2024/Sep/28/openfreemap)
- [pyqtlet (Leaflet in Qt) implementation notes](https://pyqtlet.readthedocs.io/en/latest/technical.html)
- [Chromium GPU process fallback](https://chromium.googlesource.com/chromium/src/+/main/content/browser/gpu/fallback.md) · [Intent to remove SwiftShader fallback](https://groups.google.com/a/chromium.org/g/blink-dev/c/yhFguWS_3pM/m/oLrB5up_BwAJ) · [MapLibre/WebGL rendering report (Vivaldi)](https://forum.vivaldi.net/post/915166)

**Data, species and recording standards**
- [UKSI on GBIF (CC BY 4.0, DwC-A)](https://www.gbif.org/dataset/dbaa27eb-29e7-4cbb-8eab-3f689cfce116) · [UKSI simplified copy (NHM Data Portal)](https://data.nhm.ac.uk/dataset/uk-species-inventory-simplified-copy) · [NHM UK Species Dictionary](https://www.nhm.ac.uk/our-science/data/uk-species/index) · [NBN Atlas species information](https://docs.nbnatlas.org/finding-basic-species-information/)
- [iRecord: entering a simple record](https://irecord-training.readthedocs.io/en/latest/a-simple-record.html) · [BSBI: demystifying grid references](https://bsbi.org/take-part/activities/100-plants-challenge/recording-guidance/where-demystifying-grid-references) · [Indicia taxon-observation API](https://indicia-online-recording-rest-api.readthedocs.io/en/latest/resources/taxon-observation.html)
- [Darwin Core term list](https://dwc.tdwg.org/list/2020-10-13) · [OBIS manual: Event tables](https://manual.obis.org/format_event.html)
- [eBird complete-checklist definition](https://support.ebird.org/support/solutions/articles/48000967748) · [Audubon beginner's guide to eBird](https://www.audubon.org/news/a-beginners-guide-using-ebird) · [Complete checklists & effort (bioRxiv)](https://www.biorxiv.org/content/10.1101/574392.full.pdf)
- [Recorder 6 maintenance arrangements (NBN)](https://nbn.org.uk/?p=22261) · [MapMate](https://mapmate.bsbi.org.uk/)

**Database**
- [Backing up a WAL-mode SQLite database safely](https://oneuptime.com/blog/post/2026-09-08-back-up-wal-mode-sqlite-safely/markdown) · [SQLite best practices](https://dragonflydb.io/databases/best-practices/sqlite)
- [Alembic + SQLite ALTER TABLE issues (Miguel Grinberg)](https://blog.miguelgrinberg.com/post/fixing-alter-table-errors-with-flask-migrate-and-sqlite/page/2)

**Photos, location, online services**
- [pillow-heif metadata utilities](https://tessl.io/registry/tessl/pypi-pillow-heif/files/docs/metadata-utilities.md)
- [PySide6 QtPositioning docs](https://doc.qt.io/qtforpython-6/PySide6/QtPositioning/index.html) · [QGeoPositionInfoSource on Windows (Qt mailing list)](https://lists.qt-project.org/pipermail/interest/2016-June/022870.html)
- [Open-Meteo](https://open-meteo.com/)

**Charts**
- [ADR: PyQtGraph vs Matplotlib (PySide6 project)](https://pyxraylabtool.readthedocs.io/en/latest/architecture/002-adr-pyqtgraph-vs-matplotlib.html) · [QWebEngineView docs](https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineWidgets/QWebEngineView.html)

**Packaging**
- [pyside6-deploy docs](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html) · [Qt for Python deployment overview](https://doc.qt.io/qtforpython-6/deployment/index.html) · [pyside6-deploy + WebEngine forum thread](https://forum.qt.io/topic/164262/debugging-mwe-of-pyside6-deploy-with-webengine)
- [PyInstaller antivirus false positives (pythonguis)](https://www.pythonguis.com/faq/problems-with-antivirus-software-and-pyinstaller/) · [PySide6 + Nuitka deployment example](https://github.com/Erriez/pyside6-nuitka-deployment)
- [Nuitka 4.2 release (Python 3.14 official)](https://nuitka.net/posts/nuitka-release-42.html)
- [Microsoft code signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options) · [Artifact Signing pricing](https://azure.microsoft.com/en-gb/pricing/details/trusted-signing/)
