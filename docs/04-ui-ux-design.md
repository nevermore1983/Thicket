# WildLife — Phase 4: UI/UX Design

**Date:** 11 October 2026
**Status:** Draft for your review
**Builds on:** [02 Product specification](02-product-specification.md) · [03 Architecture](03-architecture.md)

**Clickable prototype:**
- Online (private to you): <https://claude.ai/artifact/JgMxHWDBZmUhk5SfJQ5r8k>
- Local copy: [`prototype/index.html`](../prototype/index.html). Open it in any browser.

The prototype is throwaway HTML with made-up sample data (about 1,550 sightings, 2024–2026). Its job is to settle **look, layout, flow and wording** before any Qt code exists. The real app will be built in Qt to match it.

---

## 1. How to review the prototype

Use **Prototype controls** (bottom of the sidebar) to switch between:
- **Theme:** System / Light / Dark.
- **Library:** sample data, or an empty library (what a brand-new user sees).
- **Internet:** online or offline (look at the Map).
- **Show first run:** the welcome and setup steps.
- **Shortcuts:** the keyboard sheet (also opened with `?`).

Things worth trying:

| Try this | What it shows |
|---|---|
| Press **Ctrl+N**, type `finch`, press Enter, type `c. 12`, press Enter | The keyboard-only quick add, with species ranking and count parsing |
| In the add panel, type `TQ 308 808` into *Exact position* | Grid reference parsing and validation, with a mini-map |
| **Photos › Inbox** › *Select group* › *Create sighting* | "Phone photos → sightings": date, time and location come from the photos |
| **Calendar**, then use ← → and the keys **Y M W D** | Year, month, week and day views; click a day to list it |
| **Map**, switching *Pins / Heat / Grid squares*, clicking legend items | Clustering, density, species per square, filtering from the legend |
| **Sightings**, then tick some rows | Bulk actions: change species, delete with Undo |
| **Statistics**, then *Last year / All time* | Chart forms, hover tooltips, the "question" caption on every chart |
| **Ctrl+K**, then type `heron` or `may 2025` | Global search grouped into species, places, notes and dates |

---

## 2. Visual direction

> **Calm field notebook.** A quiet, slightly green-tinted neutral background, one green accent for actions, and colour reserved for *data* (species categories, charts). The interface recedes so your sightings and photos stand out.

- **Neutrals lean green** rather than pure grey. This is subtle, but it ties the app to the outdoors without being "themed".
- **One accent** (green) is used only for actions, selection and focus. It is never a data colour.
- **Data colours** come from a validated palette (section 3.3), separate from the accent.
- **Scientific names in a serif italic**, the way field guides print them. This one detail makes the app feel like a naturalist's tool.
- **UK conventions throughout:** `Sun 11 Oct 2026`, 24-hour clock, OS grid references (`TQ 308 808`), °C, "c. 200" for approximate counts.

---

## 3. Design tokens

Tokens are named values that every screen uses instead of raw numbers. In the Qt app they live in `ui/theme/tokens.py`, and the stylesheet is generated from them, so a theme change touches one file.

### 3.1 Colour: surfaces and text

| Token | Light | Dark | Use |
|---|---|---|---|
| `bg` | `#f3f5f1` | `#0f1210` | Window background |
| `surface` | `#ffffff` | `#181c19` | Cards, panels, tables |
| `surface-2` | `#f0f2ed` | `#1f2420` | Hover, inputs, subtle fills |
| `surface-3` | `#e5e9e2` | `#282e29` | Pills, tracks |
| `border` | `#dfe3dc` | `#2b322d` | Dividers, card edges |
| `border-strong` | `#c7cec4` | `#3b443d` | Inputs, buttons |
| `text` | `#17201a` | `#e6ebe6` | Primary text |
| `text-2` | `#556058` | `#a9b3aa` | Secondary text (6.2:1 / 7.8:1) |
| `text-3` | `#687069` | `#8d978e` | Captions, axis labels (≈4.5:1) |
| `accent` | `#2e7d4f` | `#5fbf85` | Primary buttons, selection, focus ring (5.1:1 / 7.5:1) |
| `accent-subtle` | `#e2f0e7` | `#1b3125` | Selected nav item, chips, Lifer badge |
| `danger` / `warning` | `#c4372c` / `#8f5b00` | `#ef7166` / `#e3a73f` | Errors, "Needs attention" |

All text/background pairs were checked for contrast. Body text reaches at least 4.5:1 (WCAG AA) in both themes.

### 3.2 Typography

| Role | Face | Size / weight |
|---|---|---|
| Page title | Segoe UI Variable Display | 24 / 600 |
| Card / panel title | Segoe UI Variable Text | 14.5–22 / 600 |
| Body | Segoe UI Variable Text | 14 / 400 |
| Table / meta | Segoe UI Variable Text | 12.5–13.5 / 400–600 |
| Big numbers (tiles) | Segoe UI Variable Display | 30 / 600 |
| **Scientific names** | **Source Serif 4 Italic** | 1 em of surrounding text |

Segoe UI Variable is Windows 11's own font, so there's nothing to bundle. Source Serif 4 is free (SIL Open Font License) and will be bundled with the app.

### 3.3 Category colours: validated, not eyeballed

Category colours mark identity on map pins, calendar dots and legends. Many colour sets look fine to full-colour vision but collapse for colour-blind users, so I ran the palette through a colour-blindness validator (protanopia and deuteranopia simulation).

| # | Category | Light | Dark | Icon |
|---|---|---|---|---|
| 1 | Bird | `#2a78d6` | `#3987e5` | bird |
| 2 | Mammal | `#eb6834` | `#d95926` | rabbit |
| 3 | Fish | `#1baf7a` | `#199e70` | fish |
| 4 | Butterfly & Moth | `#eda100` | `#c98500` | butterfly |
| 5 | Dragonfly & Damselfly | `#e87ba4` | `#d55181` | dragonfly |
| 6 | Reptile & Amphibian | `#008300` | `#008300` | frog |
| 7 | Other insect | `#4a3aa7` | `#9085e9` | bug |
| 8 | Other invertebrate | `#e34948` | `#e66767` | snail |
| – | Other | `#7d847e` | `#7a847b` | paw print |

**Results:**
- **All checks pass in both themes.** The closest neighbouring pair stays clearly separable under colour-blind simulation (ΔE 9.1 light / 8.4 dark, target ≥ 8), and full-colour distinctness is ≥ 19 (floor 15).
- **The colour order is the safety mechanism.** Re-ordering the same colours failed the test badly (ΔE 1.6), so the order is fixed.
- **Colour is never used alone.** Pins and swatches always carry an icon, and legends always carry names.
- Three light-mode colours are below 3:1 contrast against white, so those categories always appear with a visible label or a dark icon on the swatch.
- **This changes the specification slightly.** The default categories go from 11 to **8 + Other**:
  - Reptile and Amphibian are merged (UK recorders often group them anyway).
  - Spiders join Other invertebrate.

  You can still add categories. A new category reuses one of the 8 colours and gets its own icon, because a 9th "generated" colour would break colour-blind safety. The database design (`schema_v1.sql`) has been updated, and the stress test still passes 26/26.

### 3.4 Data scales

- **Magnitude** (busy days, species per square, heat tables) uses a **single blue ramp**, light → dark, with seven steps. In dark mode the ramp flips so "more" is brighter.
- **Status** (backup OK, needs attention) uses fixed good/warning colours, always with an icon and words.

### 3.5 Spacing, shape, depth, motion

| Token | Values |
|---|---|
| Spacing | 4 · 8 · 12 · 16 · 24 · 32 px |
| Radius | 6 (controls) · 10 (inputs, menus) · 14 (cards) · fully round (chips, badges) |
| Elevation | Cards are flat with a 1 px border. Shadows only on things that float: panels, menus, toasts, dialogs. |
| Motion | 150–220 ms ease for panels and toasts. Nothing else animates. Respects Windows' "reduce animations" setting. |

---

## 4. Layout and navigation

```
┌────────────┬─────────────────────────────────────────┬──────────────────┐
│ ◉ WildLife │ [🔍 Search… Ctrl K]   (Outing·Garden) [+ Add sighting] │
│            ├─────────────────────────────────────────┤  Side panel      │
│ Dashboard  │                                         │  (view / edit    │
│ Sightings  │            current page                 │   sighting,      │
│ Calendar   │                                         │   species,       │
│ Map        │                                         │   place, day,    │
│ Photos (9) │                                         │   outing)        │
│ Statistics │                                         │                  │
│ Species    │                                         │  [Save] [Cancel] │
│ Places     │                                         │                  │
│ ⚙ Settings │                                         │                  │
└────────────┴─────────────────────────────────────────┴──────────────────┘
```

- **Side panel instead of dialogs.** On wide windows (≥ 1240 px) the panel *pushes* the page aside, so the calendar or map stays fully visible. On narrower windows it slides over the page. Panels stack: Sighting › Species › back.
- **Dialogs only where they're right:** first-run setup, export, bulk change, keyboard shortcuts. There are no "Are you sure?" pop-ups. Deletes go to the recycle bin with **Undo**.
- **Sidebar** collapses to an icon rail below 860 px wide.
- **Minimum supported window:** 1024 × 640. Every page was checked down to phone width with no sideways scrolling.

---

## 5. Component inventory (the Qt build list)

These become `ui/components/` in Phase 5/6. Each is built once and reused everywhere.

| Component | Used on | States to support |
|---|---|---|
| `NavItem` | Sidebar | Normal, hover, current, count badge, rail (icon only) |
| `SearchBox` + results popover | Top bar | Empty, typing, grouped results, no results |
| `Button` | Everywhere | Primary, secondary, ghost, danger, small, disabled, with icon |
| `SegmentedControl` | Calendar view, map view, stats period, theme | Pressed / not pressed |
| `Tabs` | Sightings, Photos, Species | Selected, with count pill |
| `FilterBar` + `FilterChip` + menus | Sightings, Calendar, Map, Photos, Statistics | Inactive, active (with ×), menu open, "Clear all" |
| `Card`, `StatTile` | Dashboard, Statistics, panels | With delta (good / neutral) |
| `SightingRow` | Dashboard, day panel, outing panel | Thumbnail or placeholder, Lifer / FOY badges, "No location" |
| `SightingTable` (model/view) | Sightings | Sorting, multi-select, bulk bar, footer totals, empty / no-match |
| `SpeciesPicker` | Add/edit panel | Typing, ranked suggestions, keyboard highlight, "create custom" |
| `PlacePicker` (chips + select) | Add/edit panel | Recent places, other place, none |
| `CoordinateField` | Add/edit panel | Empty, parsed (grid ref / lat-lon / link), invalid, swapped lat/lon |
| `CountField` | Add/edit panel | Exact, "c. 200", "50+", empty = present, invalid |
| `PhotoStrip`, `PhotoGrid`, `PhotoViewer` | Panels, Photos | Placeholder, missing file, selected, rotate, info overlay |
| `MiniMap` | Panels | Point(s), place centre, no location |
| `CalendarMonth/Year/Week/Day` | Calendar | Today, other month, counts, category dots, star for firsts |
| `ActivityGrid` | Dashboard, Calendar year | Seven-step ramp, today ring, tooltips |
| `Toast` | Global | Message, Undo, Open, auto-dismiss (4 s, or 10 s with Undo) |
| `EmptyState` | Every list or page | Icon, title, explanation, action buttons |
| `Callout` | Panels, Settings, Inbox | Info, warning, success |
| `SidePanel` | Global | View, edit, stacked with Back, unsaved-changes guard |
| `Badge` | Lists, panels | Lifer, First of year, warning |

---

## 6. Interaction rules

1. **Only the species is required.** Date and time default to now, the place defaults to the last one used today, and count defaults to 1.
2. **Keyboard first for recording:** Ctrl+N → type → Enter (pick) → type count → Enter (save). Ctrl+Enter = save and add another.
3. **Validation appears beside the field as you type**, in plain words with an example. The app catches swapped lat/lon and malformed grid references.
4. **Undo instead of confirm.** Every delete or bulk change shows a toast with Undo (and Ctrl+Z). Confirmation is reserved for genuinely irreversible actions: emptying the recycle bin and restoring a backup.
5. **Every list has an empty state** that explains and offers the next action. Filters that match nothing say so and offer "Clear filters".
6. **Anything slower than ~300 ms shows progress**: skeleton rows for lists and a progress bar for imports and backups.
7. **One filter, everywhere.** The same filter chips appear on Sightings, Calendar, Map, Photos and Statistics, and mean the same thing.
8. **Click-through from summaries.** Chart bars, heat cells, calendar days, map pins and dashboard rows all open the matching sightings.

### Keyboard map
| Keys | Action |
|---|---|
| Ctrl+N / Ctrl+K | Add sighting / Search |
| Enter, Ctrl+S / Ctrl+Enter | Save / Save & add another |
| Esc | Close menu, panel or dialog |
| Ctrl+Z | Undo last action |
| Ctrl+1…8 | Switch page |
| E / Delete | Edit / delete the open sighting |
| Calendar: ← → T Y M W D N | Move, today, view, add on day |
| Photo viewer: ← → R I Esc | Navigate, rotate, info, close |
| ? | Shortcut sheet |

---

## 7. Charts

These rules come from a data-visualisation checklist, and the prototype follows them:
- **Every chart is captioned with the question it answers** ("What time of day are my sightings?"). If no question fits, the chart doesn't exist.
- **Chart forms:**
  - Life list growth: step line, this year against last year.
  - Top species and categories: horizontal bars, one colour.
  - Seasons: month × category heat table.
  - Time of day: 24 hourly bars.
  - Best places: a table, not a chart.
- **One y-axis per chart, ever.** Thin marks, 4 px rounded bar ends, recessive gridlines.
- **Hover tooltips on every mark.** Legends whenever there are two or more series, with direct labels at line ends.
- **Text uses text colours, never the series colour.**

---

## 8. Wording guide

| Do | Don't |
|---|---|
| "Sighting", "Place", "Outing", "Species" | Record / Observation / Location / Trip used interchangeably |
| "Robin saved · Undo" | "Operation completed successfully" |
| "That doesn't look like a grid reference. Example: TQ 308 808" | "Invalid input" |
| "No internet, so the detailed background map is unavailable. Your sightings still show." | "Network error 0x80072EE7" |
| "9 sightings without a location" | "9 records have NULL coordinates" |
| `Sun 11 Oct 2026`, `09:41`, `c. 200`, `±100 m` | `10/11/2026`, `9:41 AM`, `~200`, `100m accuracy` |

---

## 9. What prototyping taught us (and how the Qt build will avoid it)

Testing the prototype in a real browser found **11 bugs** in about an hour, and all are fixed. The important point is the lessons for the real app:

| Bug found | Lesson for the Qt build |
|---|---|
| A style called `.empty` (empty state) also matched thumbnails marked `empty`, giving them 40 px of padding | **Name styles by component** (`EmptyState`, `Thumbnail`), never generic words. In Qt: per-component object names in the stylesheet. |
| The map grew taller than the window | **Set explicit size policies for anything that draws itself**: map, charts, calendar. |
| Count saved as "c. 121" because typing went *before* the pre-filled "1" | **Fields with a default select their contents on focus**, so typing replaces the default |
| Map pins couldn't be clicked because the pan gesture captured the mouse | **Only start a drag after the pointer actually moves a few pixels** |
| "More details" collapsed while typing | **Re-rendering must preserve UI state** (expanded sections, scroll position, focus). In Qt, update widgets rather than rebuilding them. |
| Menus stayed open after choosing | Popovers close on choice unless they're multi-select |
| Arrow keys in the photo viewer also moved the calendar behind it | **A modal view owns the keyboard** |
| Clicks inside dialogs were blocked | Never cancel default behaviour globally |
| Tab bar showed stray scroll arrows | Scroll containers scroll on one axis only |
| An apostrophe broke the script | (HTML-only) Run a syntax check before every review |
| Phone-width test was invalid without a viewport tag | Test at the sizes we claim to support, with the real page setup |

---

## 10. Changes to the specification from this phase

1. **Default categories: 8 + Other** (was 11), for colour-blind safety (section 3.3).
2. **Week view** shows time-ordered sighting cards per day, not an hour grid (confirmed in the prototype).
3. **Map views** are named *Pins · Heat · Grid squares*. Grid squares are 10 km at country zoom and 1 km when zoomed in.
4. **Dashboard** adds "Most seen this year" and an activity grid. "Recent places" stays.
5. **Prototype controls** exist only in the prototype.

---

## 11. Questions for your review

1. **Overall feel:** does the "calm field notebook" direction suit you, or would you like it bolder or more colourful?
2. **Green accent:** keep it, or prefer another (e.g. deep teal, slate blue)?
3. **Serif scientific names:** do you like the field-guide touch?
4. **Category set:** happy with the 8 categories above, or would you rather split something differently (e.g. Bees & Wasps as its own group)?
5. **Dashboard:** anything you'd remove, add or move higher?
6. **Add sighting panel:** is anything missing from the main form, or anything there that should move into *More details*?
7. **Anything that felt slow, confusing or fiddly** while clicking around?
