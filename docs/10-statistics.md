# WildLife — Phase 10: Statistics

**Date:** 12 October 2026
**Status:** Complete, awaiting review

A Statistics page where every chart answers one question, a fuller dashboard, year lists, and a profile for each species. Every bar, cell and row opens the matching sightings.

---

## 1. What was built

| Area | What you get |
|---|---|
| **Statistics page** | Period: This year · Last year · All time · Custom… (plus the shared filter). Tiles: sightings (and days), species, lifers, outings, places, busiest day. |
| **"How is my species list growing?"** | A step line of different species seen; a year is drawn against the year before on a shared Jan–Dec axis (this year in blue, last year in grey, labelled at the line ends). A crosshair tooltip shows both totals on any day. |
| **"What do I see most?"** | Top 10 species by sightings, or by animals counted. |
| **"Which groups do I record?"** | Sightings per category (the table version adds species). |
| **"When in the year is each group about?"** | Month × category heat table with the numbers written in. |
| **"What time of day are my sightings?"** | 24 hourly columns. |
| **"Am I seeing more than last year?"** | Species per month, this year against last. |
| **"Where are my best places?"** | Places ranked by species, with visits (days there), sightings and species per visit. This is the map phase's "visits vs richness" idea, as a table. |
| **"What's new on my lists?"** | Lifers, or firsts of the year, with date and place; opens on whichever list has entries. |
| **Click-through** | Bars, cells, columns and rows open the Sightings list filtered to them. Two new filters make that exact: **month of year** ("In May") and **hour of day** ("07:00–08:00"), shown as chips you can remove. |
| **Table versions** | Every chart has "Show table": the same numbers as a table, so nothing is only readable by hovering. |
| **Dashboard** | New: the year as an activity strip (a square per day; click opens the calendar day), "New in 2026" (latest lifers and firsts), and "Most seen in 2026". |
| **Year lists** | Species page › "2026 list", "2025 list"…: species seen that year with first and last date that year; ★ marks lifers. |
| **Species profile** | Click a species: sightings, animals counted, best count, first and last seen, "When in the year do I see it?", sightings each year, best places, photos (open the viewer), Show sightings, Show on map. |

---

## 2. Decisions

| Decision | Why |
|---|---|
| **Charts are painted with Qt, not ECharts** (a change from the Phase 3 plan) | The charts needed are simple (bars, columns, one step line, a heat table). Painting them like the calendar is fast, theme-aware and sharp, needs no second web view or JavaScript bridge, sends clicks straight to Python, and lets tests check the data directly. |
| Charts follow the data-visualisation checklist | Thin marks with 4 px rounded data-ends, hairline gridlines, one y axis, text never in the series colour, a hover tooltip on every mark (value first), a legend for two series plus direct end-labels, keyboard access (arrows + Enter), and a table version of every chart. |
| Colours were **validated with the palette script**, not judged by eye | The category colours pass the colour-blindness, lightness and contrast checks in both themes. The light-mode contrast warning for three of them is covered by labels and table views. |
| The dark-theme amount ramp was **re-stepped** | Two neighbouring steps were too close to tell apart (ΔL 0.047). The new steps come from the reference blue ramp, with every gap ≥ 0.06. The lightest "near zero" step may fade into the background, which is allowed for amounts. The calendar's year view and the map heat use it too. |
| Firsts and lifers come from **all** records | As in the calendar: filtering to one group never makes an old species look new. |

---

## 3. Checks

- **Tests:** 336 automated (37 new), passing in about 57 s with no warnings. New tests cover:
  - the statistics numbers against hand-checked data (summary, tie rule for the busiest day, growth curves on a shared axis, categories, seasons, hours, top species with subspecies merged, places, species per month, firsts decided from all records, probable IDs, the new month/hour filters, an empty library);
  - the chart components (tick rounding, hit-testing, tooltips, table versions, keyboard, clicks);
  - the page, dashboard, year lists and profile through the real window.
- **Performance** with 20,000 sightings:

  | Action | Time |
  |---|---|
  | Statistics page, this year (in the background, to drawn) | 114 ms |
  | Statistics page, all time | 204 ms |
  | Dashboard rebuild (with the new cards) | 95 ms |

- **Packaged build:** smoke test passes; 570 MB (unchanged).
- **Visual checks:** Statistics in light and dark, the dashboard, a year list with a profile open.

---

## 4. Problems found and fixed

| Problem | Fix / lesson |
|---|---|
| **My species (and Places) were listed Z→A since Phase 6** | Qt's tables sort descending unless told otherwise. They now sort A→Z, and a test checks the order |
| With the side panel open, species names shrank to "Chi…" | Columns size to their contents, and Category hides when narrow (the swatch already shows it) |
| `@dataclass` had slipped onto a Qt widget class | Removed: it would replace the widget's identity-based equality and hashing |
| Placeholder stubs and alias string-hacks crept back into new files | Removed, and now checked for before every commit |
| "No lifers" sat in the middle of a tall card, and the list opened empty in years without lifers | Top-aligned, and the card opens on the list that has entries |
| The dashboard's recent sightings spread out to fill a taller card | Rows stay together at the top |

---

## 5. Deferred (deliberately)

| Item | Where |
|---|---|
| Saved filters ("My moth-trap nights"), a Could | Phase 12 |
| Species notes in the profile (not stored yet) | Phase 12 |
| Catalogue browser and category management tabs on the Species page | Phase 12 |
| Exporting a chart as an image | Phase 11 (export), if wanted |
