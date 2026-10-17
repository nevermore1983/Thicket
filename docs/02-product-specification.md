# WildLife — Phase 2: Product Specification

**Date:** 11 October 2026
**Status:** Draft for your review
**Builds on:** [01-research-and-architecture.md](01-research-and-architecture.md)

This document defines **what** version 1 of the app does, field by field and screen by screen. **How** it's built (database tables, code modules) is Phase 3. **How it looks** (wireframes, colours) is Phase 4.

---

## 0. How to read this

Every feature has a **priority**:

| Label | Meaning |
|---|---|
| **Must** | Version 1 is not finished without it |
| **Should** | Planned for version 1. Could slip to v1.1 if it proves much harder than expected. |
| **Could** | Nice to have. Built only if time allows, otherwise in the backlog. |
| **Later** | Deliberately *not* in version 1. Listed so the design doesn't block it. |

Each feature also shows the **phase** it's built in, using the revised roadmap in section 24 of the research document.

---

## 1. Vision and design principles

> **A personal wildlife journal that's quicker than a notebook and smarter than a spreadsheet.**
> See wildlife → record it in seconds → explore years of sightings on a calendar, map and charts.

These principles settle arguments later. When two designs compete, the one that fits these better wins.

1. **Recording first.** Adding a sighting is the most-used action and must never take more than a few seconds. Only the species is required.
2. **Save now, perfect later.** Incomplete sightings are allowed and are gently surfaced under "Needs attention". They are never blocked.
3. **Your data is sacred.** Nothing is lost by accident: undo, a recycle bin, automatic verified backups, and open export formats.
4. **Works offline.** Every core feature works without internet. Online extras say clearly when they're unavailable.
5. **One meaning everywhere.** A filter, a word or a colour means the same thing on every screen.
6. **Show insight, not decoration.** Every number or chart answers a question you'd actually ask.
7. **Calm and consistent.** Few pop-ups, no clutter, keyboard-friendly, and pleasant in both light and dark themes.

---

## 2. Decisions recorded from Phase 1

| # | Question | Decision |
|---|---|---|
| 1 | Field workflow | **Both:** quick entry at a laptop *and* "phone photos → sightings" back home. The Photo Inbox (section 8.6) is a **Must**. |
| 2 | Outings | **Yes, optional.** Sightings can belong to an outing; nothing forces you to use them. |
| 3 | Species list | **Full UKSI animal list**, ranked so your species come first, plus your own custom species |
| 4 | Offline map | Online map background by default. The **offline UK map pack is an optional download** (Should). |
| 5 | Git | **Done:** repository initialised in `E:\WildLife` |
| 6 | Future plans | Personal use, but only dependencies whose licences let you share or sell the app later |
| 7 | Previous app review | The reselling app wasn't found on drive E:. General lessons applied for now; we can review it any time you tell me where it is. |

---

## 3. Glossary

These are the **only** names the app uses for these things, in menus, buttons, messages and documentation.

| Term | Meaning |
|---|---|
| **Sighting** | One species (or unidentified group) observed at one time and place, with optional count, photos and notes |
| **Species** | Shorthand in the UI for any taxon you can record: a species, a subspecies, or a broader group such as "gull species". Technically called a *taxon*. |
| **Category** | A user-friendly group used for colours, icons and filters (Bird, Mammal, Butterfly & Moth…). Editable. |
| **Place** | A saved, named location you visit repeatedly (e.g. "Rainham Marshes"), with a centre point and radius |
| **Outing** | An optional trip or visit that groups sightings (e.g. "Titchwell, Sun 12 Oct") and holds the weather |
| **Photo Inbox** | Photos imported but not yet attached to a sighting |
| **Life list** | Every species you've ever recorded (rules in section 7.1) |
| **Year list** | Every species recorded in a calendar year |
| **Lifer** | The first time you ever record a species |
| **First of year (FOY)** | The first sighting of a species in a given year |
| **Uncertainty** | How precise a location is, in metres (e.g. ±100 m) |
| **Grid reference** | British National Grid reference, e.g. `TQ 308 808`. Its length sets its precision: 6 figures = 100 m square. |
| **Recycle bin** | Deleted sightings and photos, restorable for 30 days |
| **Snapshot** | One automatic or manual backup copy of the database |

---

## 4. Key scenarios

These are the stories the app must handle well. Phase 13 tests are written from them.

**S1 — Quick add at the laptop.** A goldfinch lands on the feeder.
Ctrl+N → type "goldf" → Enter (Goldfinch) → Tab to count, type 3 → Enter. Saved in **under 10 seconds**, with today's date and time and the "Garden" place (because it was the last place used today).

**S2 — Back home with phone photos.** 40 photos from a Sunday walk.
Drag the folder onto the app → the photos land in the **Photo Inbox**, grouped by time and location → select 3 photos of the same heron → "Create sighting" → pick Grey Heron. Date, time and location come from the photos. Repeat for each animal. Leftover photos stay in the Inbox for later.

**S3 — A planned day trip.**
Start an outing: "Titchwell Marsh", today, sunny, 14 °C. Every sighting added today defaults to that outing. That evening, the outing summary shows 47 species, 3 of them new this year.

**S4 — "When did I last see a kingfisher?"**
Ctrl+K → "kingfisher" → the species result shows: 12 sightings, first seen 14 May 2023, last seen 2 Sep 2026 → click to open all 12 on the map.

**S5 — Year in review.**
Statistics → 2026 → species curve against 2025, top places by species, best month, list of lifers.

**S6 — New PC (disaster recovery).**
Install the app → Restore from backup → pick the backup folder on the external drive → everything (sightings, photos, settings) is back and verified.

**S7 — Fixing a mistake.**
Realise 8 "Ruddy Darter" sightings were actually Common Darter → filter → select all 8 → "Change species…" → done, with Undo available.

---

## 5. Feature scope

### 5.1 Recording sightings

| Feature | Priority | Phase |
|---|---|---|
| Add sighting panel (species-only required, smart defaults) | Must | 6 |
| Searchable species picker (common + scientific names, ranked) | Must | 6 |
| Edit, view and delete sightings, with Undo toast | Must | 6 |
| "Save & add another" (keeps date, time, place, outing) | Must | 6 |
| Location by: saved place, map click, lat/lon, OS grid reference | Must | 6 |
| Location by: pasted map link (Google/OSM/Bing) | Should | 6 |
| Location by: Windows "current location", showing accuracy | Could | 8 |
| Count with qualifier (exact / approx / at least), parsing "c. 200" and "50+" | Must | 6 |
| Optional details: sex, life stage, evidence, ID confidence, habitat, not-wild flag | Must | 6 |
| Attach photos while adding or editing | Must | 6 |
| Outings: create, edit, assign sightings, summary | Should | 6 |
| Outing weather fields | Should | 6 |
| Bulk edit (change species, place, date or outing on many sightings) | Should | 6 |
| Duplicate a sighting | Could | 6 |
| Auto-fill outing weather from Open-Meteo (online) | Could | 11 |
| Irish Grid references (Northern Ireland) | Could | 8 |

### 5.2 Photos

| Feature | Priority | Phase |
|---|---|---|
| Managed photo library (copy-in, de-duplicate by content) | Must | 6 |
| Thumbnails in a background cache | Must | 6 |
| Photo Inbox: import files or folders, auto-group by time and place, create sightings from selected photos | Must | 9 |
| Gallery (all photos, filterable) and full-screen viewer with keyboard navigation | Must | 9 |
| Read EXIF date, time and GPS; suggest them for sightings | Must | 9 |
| Rotate (non-destructive), reorder, choose cover photo, caption | Must | 9 |
| HEIC (iPhone) support | Must | 9 |
| Missing or corrupt photo detection, with "Locate…" or "Remove" | Must | 9 |
| Camera clock correction for a batch ("camera was 1 h behind") | Could | 9 |
| Edit or crop images | Later | — |

### 5.3 Exploring

| Feature | Priority | Phase |
|---|---|---|
| Dashboard | Must | 6 (basic), 10 (full) |
| Sightings list: sortable columns, filter bar, virtualised for 100k rows | Must | 6 |
| Global search (Ctrl+K): species, places, notes, outings, dates | Must | 6 |
| Shared filter (category, species, date range, place/area, evidence, has photos, outing, needs attention) | Must | 6 |
| Calendar: year, month, week, day views | Must | 7 |
| Map: category pins, clustering, click to open, add from map, filters | Must | 8 |
| Map heat views: density, species-per-square | Must | 8 |
| Map: "visits vs richness" view | Could | 8 |
| Offline UK map pack (optional download) | Should | 8 |
| Statistics page (section 8.8) | Must | 10 |
| Life list and year lists, with lifers and firsts of year | Must | 10 |
| Saved filters ("My moth-trap nights") | Could | 10 |
| Species page: your species, catalogue browser, category management | Must | 6 (basic), 10 (stats) |
| Places page: list, map, edit, merge, archive | Must | 6 |

### 5.4 Data safety and portability

| Feature | Priority | Phase |
|---|---|---|
| Transactions and validation on every save | Must | 5 |
| Recycle bin (30 days, restore, empty) | Must | 6 |
| Automatic snapshots (daily + on exit) with rotation and verification | Must | 6 |
| Incremental photo backup | Must | 6 |
| Backup status on the dashboard; warning when overdue | Must | 6 |
| Restore (with safety copy of current data) | Must | 11 |
| Health check (database + photo files) | Must | 11 |
| Export CSV / JSON / Darwin Core CSV / GeoJSON: current filter or everything | Must | 11 |
| Export full archive (.zip: data + photos + readme) | Must | 11 |
| Import CSV with column mapping, preview, validation report, duplicate check | Must | 11 |
| Import the app's own JSON export (round-trip) | Must | 11 |
| Location blurring and photo GPS stripping on export | Should | 11 |
| Export KML (Google Earth) | Could | 11 |
| iRecord-ready CSV column preset | Should | 11 |
| Direct upload to iRecord | Later | — |

### 5.5 App-wide

| Feature | Priority | Phase |
|---|---|---|
| Light / dark / follow-Windows theme | Must | 5 |
| Settings (section 8.11) | Must | 5–11 |
| First-run welcome (data folder, your name, theme, species catalogue install) | Must | 6 |
| Friendly error messages + log files; never raw tracebacks | Must | 5 |
| Keyboard shortcuts + shortcuts sheet (`?`) | Must | 12 |
| "Try with sample data" (separate demo library) | Could | 13 |
| Installer (per-user, no admin rights) | Must | 14 |
| In-app update check | Later | — |

---

## 6. Data specification

"Shown under *More details*" means the field is hidden until you expand that section, which keeps the add form short.

### 6.1 Sighting

| Field | Required | Default | Rules / notes |
|---|---|---|---|
| Species | **Yes** | — | Any rank (species, subspecies, genus, family…), so "Gull species" is allowed |
| Date | **Yes** | Today (or the calendar date you added from) | Not in the future; not before 1 Jan 1900 |
| Time | No | Now, when the date is today; blank otherwise | 24-hour HH:MM. Blank means "time unknown". |
| Place | No | Last place used within the last 3 hours (setting) | Picking a place fills the location from it |
| Coordinates | No | From the place, a photo or a map click | Lat −90…90, lon −180…180, stored to 6 decimals (~10 cm) |
| Uncertainty (m) | No | Set by the location method (section 7.3) | 1 – 100,000 m |
| Location description | No | — | Free text, e.g. "by the bridge, north side". Max 200 chars. |
| Count | No | 1 | Whole number ≥ 1, or blank meaning "present, not counted" |
| Count qualifier | No | Exact | Exact / Approximate / At least. Typing "c. 200" or "50+" sets it automatically. |
| Evidence | No | Seen | Seen · Heard · Seen & heard · Signs (tracks, droppings, nest…) · Dead · Trapped (e.g. moth trap). *More details.* |
| Identification | No | Certain | Certain · Probable · Possible. *More details.* |
| Sex | No | Not recorded | Male · Female · Mixed · Unknown. *More details.* |
| Life stage | No | Not recorded | Adult · Juvenile · Immature · Egg · Larva/caterpillar · Pupa · Nymph · Other. *More details.* |
| Habitat | No | Place's habitat, if set | Woodland · Grassland · Farmland · Heath & moorland · Wetland · Freshwater · Coastal · Marine · Garden & urban · Upland · Other. *More details.* |
| Not wild | No | Off | Captive, escaped or released animals. These are excluded from lists (section 7.1). *More details.* |
| Outing | No | Today's outing, if exactly one matches (section 7.4) | — |
| Notes | No | — | Free text, max 10,000 chars, searchable |
| Photos | No | — | 0 or more, ordered; the first is the cover |
| *System* | auto | — | ID, unique ID (UUID), created, last edited, deleted date (if in recycle bin) |

### 6.2 Species (taxon)

| Field | Required | Notes |
|---|---|---|
| Scientific name | **Yes** | e.g. *Erithacus rubecula* |
| Common name | No | Many insects have none. When there isn't one, the scientific name is displayed instead. |
| Other names | No | Alternative common names, used by search |
| Rank | **Yes** | Species, subspecies, genus, family, order… |
| Parent | No | Builds the taxonomy tree, e.g. subspecies → species |
| Category | **Yes** | Set automatically from taxonomy; can be overridden |
| UKSI key | UKSI only | Keeps the link to the official list so updates can rename safely |
| Custom | auto | On for species you create. Custom species are never changed by catalogue updates. |
| Hidden | No | Hides the species from the picker (e.g. groups you'll never record) |

### 6.3 Category

| Field | Required | Notes |
|---|---|---|
| Name | **Yes** | Unique |
| Colour | **Yes** | Used for map pins, calendar dots and charts. Checked for readable contrast in both themes. |
| Icon | **Yes** | Chosen from a built-in icon set |
| Order | auto | Order in lists and legends, changed by dragging |
| Taxonomic groups | No | e.g. class Aves → Bird. Used to categorise species automatically. |

**Default categories:** Bird · Mammal · Fish · Butterfly & Moth · Dragonfly & Damselfly · Reptile & Amphibian · Other insect · Other invertebrate · Other. The UK recording community treats butterflies, moths and dragonflies as separate groups, so they get their own categories. Everything is editable.

*Updated in Phase 4:* this list was 11 categories. It became 8 + Other so that every category colour stays distinguishable for colour-blind users (see [04-ui-ux-design.md §3.3](04-ui-ux-design.md)).

### 6.4 Place

| Field | Required | Default / notes |
|---|---|---|
| Name | **Yes** | e.g. "Rainham Marshes". Warns (but allows) if the name already exists. |
| Centre coordinates | **Yes** | Map click, typed coordinates, or grid reference |
| Radius (m) | **Yes** | 250 m. Sightings within this radius suggest this place. |
| Default habitat | No | Pre-fills sighting habitat |
| Notes | No | Access, parking, best seasons… |
| Favourite | No | Favourites appear first in pickers |
| Archived | No | Hidden from pickers, but sightings keep their link |

### 6.5 Outing

| Field | Required | Default / notes |
|---|---|---|
| Date | **Yes** | Today |
| Start / end time | No | Start = now when created for today |
| Place | No | Main place of the trip |
| Title | No | Auto-generated: "Titchwell Marsh · Sun 12 Oct 2026" |
| Weather | No | Sunny · Partly cloudy · Overcast · Rain · Drizzle · Snow · Fog/mist |
| Temperature | No | °C (or °F by setting) |
| Wind | No | Calm · Light · Moderate · Strong · Gale |
| Visibility | No | Good · Moderate · Poor |
| Complete list | No | Off. "I recorded every species I could identify", as eBird does. Enables better statistics later. |
| Notes | No | Free text |

### 6.6 Photo

| Field | Notes |
|---|---|
| Image file | Stored in the library, named by content (duplicates are detected automatically) |
| Original file name | Shown in the viewer, searchable |
| Date/time taken | From EXIF data; editable |
| GPS position | From EXIF data, if present |
| Width, height, file size | Read automatically |
| Rotation | 0 / 90 / 180 / 270. Applied on display; the original file is never changed. |
| Caption | Optional |
| Sighting | Blank means the photo is in the **Inbox** |
| Order | Position within the sighting; the first photo is the cover |

### 6.7 Recorder

**Your name** (set at first run and in Settings) is stored once and added to exports as the *recorder* (`recordedBy` in Darwin Core). There are no multi-user accounts in v1.

---

## 7. Rules

### 7.1 What counts towards lists and species totals

A sighting counts towards the **life list, year lists, lifers, firsts of year and the "species" statistic** only when:
- it is not in the recycle bin;
- its identification is **Certain**, or Probable if the setting "Count probable identifications" is on (default **off**);
- **Not wild** is off;
- the species is at **species rank or below**, with subspecies counting as their parent species.

Broader groups ("Gull species", "Unidentified bat") are kept and shown everywhere else, but don't add to species counts. This mirrors standard birding list rules, and the Statistics page shows a short "How lists are counted" note.

**Sighting counts** (e.g. "total sightings") include every non-deleted sighting, with no exclusions.

### 7.2 Required fields and "Needs attention"

Only **species** and **date** are required. The app gently lists these items under **Needs attention** (on the dashboard and as a filter):
- sightings with **no location** (no place and no coordinates);
- photos waiting in the **Photo Inbox**;
- **missing photo files**;
- **backups** overdue or failed.

### 7.3 Location rules

- **Effective location** is the sighting's own coordinates if set, otherwise its place's centre. A sighting with neither isn't shown on the map but is counted in the "no location" total, which links to those sightings.
- **Uncertainty is set automatically** from how the location was entered:

  | Method | Uncertainty |
  |---|---|
  | Place | The place's radius |
  | Grid reference | The grid square size (e.g. 6-figure = 100 m) |
  | Map click | Based on zoom level (e.g. street level ≈ 10 m, county level ≈ 1 km) |
  | Photo GPS | 10 m, or the value stored in the photo if present |
  | Typed lat/lon | From the number of decimals |
  | Windows location | The accuracy Windows reports |

  You can always overwrite it.
- **Place suggestion.** When coordinates fall inside a saved place's radius, that place is suggested. If several match, the nearest is suggested. Suggestions are never forced.
- **Sightings outside the UK** are allowed, for example on holiday. Grid references are shown only where the grid applies. Species not in the UK list can be added as custom species.
- **Coordinate format.** The display format follows your setting (decimal or grid reference). Input accepts any supported format: decimal, degrees-minutes-seconds, grid reference, or a pasted map link.

### 7.4 Outing rules

- A new sighting defaults to an outing when **exactly one** outing exists on that date and the time falls within its start/end times (or the outing has no times). Otherwise no outing is set.
- An outing summary shows: species count, sightings, lifers and firsts of year, a map of its sightings, its weather, and its photos.
- **Deleting an outing** keeps its sightings (they become unlinked) unless you choose "Delete outing *and* its sightings", which sends them to the recycle bin.

### 7.5 Deleting and merging

| Item | What happens |
|---|---|
| Sighting | Goes to the recycle bin with its photos, with an Undo toast. Restorable for 30 days. |
| Photo removed from a sighting | Choice of "Move to Inbox" (default) or "Delete" (recycle bin) |
| Place in use | Cannot be deleted. **Archive** it (hidden from pickers) or **Merge into…** another place. |
| Category in use | Choose a replacement category first |
| Custom species in use | **Merge into…** another species. All sightings move, with Undo. |
| UKSI species | Can't be deleted, only hidden |
| Recycle bin purge | After 30 days (setting), or "Empty bin". This is the **only** time photo files are permanently deleted, and only if no other sighting uses them. |

### 7.6 Time rules

- Dates and times are stored **exactly as you'd read them on a UK clock** (local time, including BST). There is no time-zone conversion.
- Photo times use the camera's "date taken". If the camera clock was wrong, the batch clock correction fixes it (Could).
- "Today" rolls over at midnight local time.

### 7.7 Photo rules

- Supported formats: JPEG, PNG, WebP, HEIC/HEIF, TIFF. Other files are skipped and listed in the import summary.
- **Duplicates:** if the same image is already in the library, it isn't copied again. The summary says where it's already used.
- **Auto-grouping in the Inbox:** photos taken within 10 minutes and 200 m of each other are grouped as "probably the same encounter". Grouping only helps you select; it never creates sightings by itself.
- When a sighting is created from photos and its fields are empty: **date and time** come from the earliest photo, and **coordinates** come from the first photo with GPS.

---

## 8. Screen specifications

Every screen lists: purpose · contents · main actions · empty state · keyboard. Visual design is Phase 4.

### 8.1 App shell (always visible)

- **Sidebar:** Dashboard · Sightings · Calendar · Map · Photos · Statistics · Species · Places, with **Settings** at the bottom. It collapses to icons only.
- **Top bar:** global search (Ctrl+K) · **+ Add sighting** (Ctrl+N) · active outing chip, if one is in progress.
- **Side panel** (right): view and edit a sighting, outing, place or photo without leaving the current page. Esc closes it, with a warning if there are unsaved changes.
- **Toasts** (bottom): short confirmations with **Undo** and **Open** where relevant.
- Keyboard: Ctrl+1…8 switch pages, Ctrl+N add, Ctrl+K search, `?` shortcuts sheet, F5 refresh.

### 8.2 Dashboard

**Purpose:** "What's been happening, and what do I need to do?"

| Block | Content |
|---|---|
| Headline tiles | Total sightings · Life list species · Species this year (vs same date last year) · Sightings this month |
| Recent sightings | Last 10, with photo thumbnail, species, place and date. Click to open. |
| New this year | Latest firsts of year and lifers |
| Top species this year | Top 5 by number of sightings |
| Activity | This year's mini activity grid (click a day to go to the calendar) |
| Recent places | Last 5 places, with sighting counts |
| Needs attention | Inbox photos, sightings with no location, missing photos, backup status |

**Empty state (new user):** a welcome card with "Add your first sighting", "Import photos" and "Import existing records".

### 8.3 Add / edit sighting (side panel)

**Purpose:** record in seconds. Layout, top to bottom:
1. **Species** (focused when the panel opens). Suggestions show the common name, scientific name in italics, a category icon, and "seen 12×" for species you've recorded. The last option is always "+ Create custom species…".
2. **Date · Time**
3. **Location:** place picker with recent and nearby chips, a mini-map, and a coordinate/grid reference field showing ±uncertainty
4. **Count** (accepts "c. 200" and "50+")
5. **Photos:** drop zone and thumbnails
6. **Notes**
7. **▸ More details:** evidence, identification, sex, life stage, habitat, not wild, outing
8. Buttons: **Save** (Enter or Ctrl+S) · **Save & add another** (Ctrl+Enter) · Cancel (Esc)

Behaviour:
- Validation appears next to fields as you type.
- After saving, a toast shows "Robin saved · Undo · Open".
- "Save & add another" keeps date, time, place and outing, clears species, count and notes, and puts focus back on Species.
- Edit mode is the same panel, plus Delete and Duplicate, and "Added 3 May 2025 · edited 4 May 2025".

### 8.4 Sighting detail (side panel, read mode)

Contents: photo strip (click for full screen), species with category, date and time, location (mini-map, place, coordinates, grid reference, uncertainty), count, details, notes and outing link. The species line shows a badge if this sighting was a **lifer** or **first of year**.

Actions: Edit (E) · Delete (Del) · Show on map · Show in calendar · Other sightings of this species.

### 8.5 Sightings page

**Tabs:** All sightings · Outings.

- **Filter bar:** chips for each active filter, "+ Add filter", **Clear all**. This bar is the shared filter used across the app.
- **Table columns:** photo · species · category · date · time · place · count · evidence · outing. Columns can be shown/hidden and sorted. Multi-select allows bulk actions (Change species / place / date / outing, Delete, Export these).
- **Footer:** "1,248 sightings · 214 species", recalculated for the current filter.
- **Outings tab:** list of outings with date, place, species count and weather. Opening one shows its summary.
- **Empty states:** no sightings at all → "Add your first sighting"; no matches for the filter → "No sightings match these filters · Clear filters".

### 8.6 Photos page

**Tabs:** Library · **Inbox (count)**.

- **Library:** thumbnail grid of all attached photos, using the shared filter. Size slider. Click opens the full-screen viewer.
- **Inbox:** drop zone + "Import photos…" (files or folder). Photos are grouped by encounter (time and place). Select photos → **Create sighting** (side panel opens pre-filled) or **Add to existing sighting…**. Delete removes them from the Inbox.
- **Viewer:** full screen, ← → to navigate, R to rotate, I for an info overlay (EXIF, sighting link, file name), Esc to close.
- Import runs in the background with a progress bar. The summary says "38 imported · 2 duplicates skipped · 0 failed".

### 8.7 Calendar

- **View switch:** Year · Month · Week · Day (keys Y / M / W / D). ← → move by one unit; T jumps to today.
- **Year:** 12 mini-months with days shaded by sighting count, plus a total per month.
- **Month:** day cells with a count badge, up to 3 category dots, and the headline species. Days with lifers or firsts of year get a small star.
- **Week:** 7 columns of sighting cards in time order. Sightings with no time are shown at the top.
- **Day:** timeline of that day's sightings with photos, outing summary, and a mini-map.
- Clicking a day lists its sightings in the side panel. Right-click (or N) adds a sighting on that date.
- The shared filter applies (e.g. butterflies only).
- **Empty state:** an empty year shows "No sightings in 2019 · Jump to your first sighting (12 May 2021)".

### 8.8 Map

- **Pins** have category colour + icon. Clusters show counts at lower zoom. A pin's popup shows species, date, photo, then "Open". Overlapping pins at max zoom fan out.
- **View switch:** Pins · Heat (density) · Grid squares (species per 1 km or 2 km square).
- **Heat weighting:** by sightings or by number of animals.
- **Add from map:** right-click → "Add sighting here" / "Create place here".
- **Places layer:** optional circles showing saved places and their radius.
- **Basemap picker:** Standard · Light · Dark · Offline pack (if installed).
- **Filters:** the shared filter bar sits above the map. "Fit to results" zooms to show all filtered sightings.
- **Offline behaviour:** pins still show, with a banner explaining how to get the offline map pack.
- **No WebGL:** a clear explanation plus a link to the help page, never a blank panel.

### 8.9 Statistics

A period selector at the top (This year · Last year · All time · Custom range), plus the shared filter.

| Section | Contents |
|---|---|
| Summary tiles | Sightings · Species · Lifers · Outings · Places · Busiest day |
| Species growth | Cumulative species curve for this period, optionally compared with the previous year |
| By category | Sightings and species per category (bar) |
| Seasons | Month × category heat table |
| Time of day | Hour-of-day histogram for sightings with a time |
| Top species | Top 10 by sightings, or by individuals counted |
| Top places | Top 10 places by species count (and by sightings) |
| Year over year | Species per month, this year against last |
| Lifers and firsts | Table: species, date, place |

Every chart has a one-line caption saying what question it answers. Clicking a bar or cell opens the matching sightings.

### 8.10 Species page

**Tabs:** My species · Catalogue · Categories.

- **My species:** your life list table with species, category, sightings, first seen, last seen, best count and photo. Click opens a **species profile**: photos, sightings over time, a month-of-year chart ("when do I see it?"), a map of sightings and your notes.
- **Catalogue:** search and browse the UKSI list and custom species. Create a custom species, hide species, and see the catalogue version with "Check for update".
- **Categories:** list with colour, icon and order. Add, edit, reorder and delete (with a replacement choice).

### 8.11 Places page

A list on the left (name, sightings, species, last visit) and a map on the right. Actions: create, edit (drag the centre, resize the radius), merge, archive. A place's profile shows its species list, visits per month, best months and photos.

### 8.12 Settings

| Section | Settings (default) |
|---|---|
| General | Your name; start page (Dashboard) |
| Appearance | Theme (System); density (Comfortable); show scientific names (After common name) |
| Recording | Default count (1); remember last place for (3 hours); count probable IDs in lists (Off); coordinate display (Grid reference in GB, otherwise decimal); units (Metric) |
| Map | Default basemap (Standard); start view (Fit all sightings); offline map pack (download / remove / size) |
| Photos | Library location; thumbnail cache size + "Rebuild"; strip GPS from exported photos (On) |
| Backup | Backup folder (none → warning until set); automatic (Daily + on exit); keep (7 daily / 4 weekly / 12 monthly); Back up now; Restore…; last result |
| Data | Data folder location (with OneDrive warning); health check; recycle bin (keep 30 days, Empty now); import; export; species catalogue update |
| Online features | Master switch "Allow online features" (On); individually: online map, weather lookup |
| About | Version, licences and attributions, open log folder |

### 8.13 First run

1. Welcome: "WildLife keeps your sightings on this PC".
2. Choose the data folder (default suggested; warns if inside OneDrive).
3. Your name (optional, used in exports).
4. Theme.
5. Install the species catalogue (progress bar, about 10–30 s).
6. Choose the backup folder, recommended on another drive or a synced cloud folder. This can be skipped, but the dashboard will keep reminding you.
7. Finish: "Add your first sighting" or "Import photos".

---

## 9. Non-functional requirements (measurable)

Measured on your PC with the **stress dataset**: 20,000 sightings, 5,000 photos, 1,500 species, 300 places.

| Area | Target |
|---|---|
| Startup | Main window usable in **≤ 3 s** (map and charts load on first visit) |
| Saving a sighting | **≤ 100 ms** |
| Global search | Results in **≤ 200 ms** as you type |
| Sightings list | Smooth scrolling. Any filter change in **≤ 300 ms**. |
| Calendar | View change in **≤ 300 ms** |
| Map | First load of 20k pins in **≤ 2 s**. Pan and zoom stay smooth. |
| Statistics | Page fully drawn in **≤ 1.5 s** |
| Photo grid | 1,000 thumbnails scroll smoothly. Cached thumbnails appear instantly. |
| Photo import | ≥ 5 photos/second, in the background, with the UI fully usable |
| Backup | Daily snapshot in ≤ 10 s, in the background |
| Memory | ≤ 600 MB in normal use (including the map browser engine) |
| Reliability | No data loss when the app is killed or power is cut mid-save (only the save in progress can be lost) |
| Offline | Every Must feature works with the network unplugged |
| Accessibility | Every action reachable by keyboard. Visible focus. Text contrast ≥ 4.5:1 in both themes. Usable at 100–200% Windows scaling. Never colour alone. |
| Privacy | No telemetry or analytics. Network used only for listed online features, which can all be switched off. |
| Portability | All data exportable to open formats. The data folder is self-contained and can be moved. |
| Maintainability | Layers as in the architecture. Automated tests for every service. No file over ~400 lines without a reason. |

---

## 10. Errors and edge cases

| Situation | Behaviour |
|---|---|
| Photo file missing | Placeholder thumbnail with a "Missing" badge; viewer offers "Locate…" or "Remove". Counted under Needs attention. |
| Photo corrupt or unsupported | Skipped on import with the reason listed. An existing photo shows a "Can't display" placeholder. |
| Invalid coordinates | Inline message. A swapped lat/lon (e.g. "0.1, 51.5") is detected with a suggestion to swap. |
| Grid reference typo | "That doesn't look like a grid reference. Example: TQ 308 808". |
| Date in the future | Inline error. Times later today are allowed, with a gentle warning. |
| Map fails to load | Explanation panel instead of a blank area (no WebGL / no internet + no map pack) |
| No internet | Online features show "Offline" and disable themselves. Nothing freezes. |
| Malformed import file | Nothing is imported. A report lists row numbers and problems, and can be saved. |
| Import of unknown species | Per name: map to an existing species, create a custom species, or skip those rows |
| Backup folder missing (drive unplugged) | Backup is marked "skipped — drive not connected". Dashboard warning. Retries next time. |
| Backup verification fails | Bad copy discarded. Error shown and logged. Retries next time. |
| Database problem at startup | Clear message with options: "Restore latest backup" or "Open data folder". The app never runs on a damaged database silently. |
| Disk full | Save fails safely (transaction rolled back), with message "Not enough disk space — nothing was changed". |
| Data folder in OneDrive | Warning at first run and in Settings, with "Move data folder…" |
| Unexpected error | Friendly dialog: "Something went wrong. Your data is safe." [Copy details] [Open log]. Full details are logged. |
| Accidental delete | Undo toast (10 s) + recycle bin (30 days) |
| Two copies of the app opened | The second launch brings the first window to the front instead of opening another |

---

## 11. Acceptance checklist (v1 "done")

Version 1 is done when all of these pass on the stress dataset and on a fresh install:

- [ ] Scenarios S1–S7 (section 4) work as described
- [ ] S1 takes under 10 s with the keyboard only
- [ ] Every Must feature in section 5 is complete
- [ ] Every target in section 9 is met
- [ ] Every row of section 10 has been tested (automated where possible)
- [ ] Backup → wipe → restore returns identical data and photos
- [ ] Export JSON → import into an empty library returns identical data
- [ ] The UI/UX audit (Phase 12) has no open "high" items
- [ ] The installer works on a Windows account that has never run the app, and uninstalling leaves your data folder untouched

---

## 12. Not in version 1 (backlog)

| Idea | Why later |
|---|---|
| Phone companion app | Big separate project. The UUIDs and import format already make it possible. |
| Sync between two PCs | Needs conflict handling; backup and restore covers moving PCs |
| Sound recordings (bird song for heard-only records) | Valuable, but a new media pipeline; the photo design extends to it |
| Direct iRecord upload | Needs their API agreement; CSV export covers it for now |
| Satellite imagery | Licensing for free satellite tiles is restrictive |
| Species information (descriptions, reference images) | Online-dependent and licensing-heavy |
| Trip report PDF | Nice output once statistics are mature |
| Breeding codes, moth-trap session details, transect counts | Specialist recording schemes; can be added as optional fields later |
| Image editing / cropping | Use a photo editor; we never alter originals |
| Multiple users | A personal app; the recorder name covers exports |
| Custom species (add a species that isn't on the UK list, including per name during an import) | Moved to version 2 on 17 Oct 2026 (your choice). Unmatched import names can be matched to an existing species or skipped. |
| "Move data folder…" and a first-run warning about cloud-synced folders | Moved to version 2 on 17 Oct 2026. The default folder isn't cloud-synced, and Settings already warns if it is. |

---

## 13. Remaining minor questions (with my defaults)

These don't block Phase 3. I'll use the defaults unless you say otherwise.

| Question | Default |
|---|---|
| Show scientific names? | After the common name, in grey italics |
| Coordinate display in GB | Grid reference (decimal lat/lon one click away) |
| Temperature / distance units | °C and metric |
| Recycle bin retention | 30 days |
| "Remember last place" window | 3 hours |
| Count probable IDs in lists | Off |
