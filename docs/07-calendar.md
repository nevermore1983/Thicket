# WildLife — Phase 7: Calendar and Outings

**Date:** 11 October 2026
**Status:** Complete, awaiting review

You can now browse your sightings by date in year, month, week and day views. Trips can be recorded as outings, with times and weather, and typing a date into search ("May 2025") opens it in the calendar.

---

## 1. What was built

| Area | What you get |
|---|---|
| **Month view** | A painted grid: each day shows its count, up to four category dots, and as many species names as fit. New species come first with a ★; when not everything fits, the last line reads "+N more". Other months' days are dimmed and today has a green pill. Hover for a summary, click to list the day in the side panel, double-click for the day view. |
| **Year view** | Twelve mini months. Each day is shaded by how busy it was; the shades split your active days into six equal groups, so one huge day doesn't wash out the rest. A ★ marks days with a new species for your life list. Click a day to list it, or a month name to open that month. The whole year fits on one screen (6 × 2) when there's room. An empty year offers to jump to your first sighting. |
| **Week view** | Seven columns of compact cards (category colour, name, time and place, ★ for firsts), untimed sightings first. Empty days have "+ Add". |
| **Day view** | The day's sightings in time order, with Lifer / First-of-the-year badges, beside that day's outings and their weather. The cards stack when space is narrow. |
| **Day panel** | Click any day: its sightings and outings in the side panel, plus "Add sighting on this date" and "Open day view". Opening a sighting from it keeps the day underneath (Back returns). |
| **Toolbar and keys** | ‹ › Today, the title, and a Year / Month / Week / Day switch. Keys: ← → previous/next, T today, Y M W D views, N add on the selected day. Switching views keeps the day you chose. With the side panel open, the title moves onto its own line so nothing is squeezed. |
| **Filters** | The shared filter bar (category, place, species, text). The calendar's period acts as the date filter, so that chip is hidden. |
| **Firsts** | Lifers and first-of-the-year are always worked out from *all* your countable records, so filtering to dragonflies never makes an old species look new. Only the earliest sighting of a species that day is marked. |
| **Outings** | A trip or visit: date, start/end times, place, title, weather, temperature, wind, visibility, "complete list", and notes. Its panel shows species, sightings, new-this-year count, the weather and its sightings. Deleting an outing keeps its sightings (Undo regroups them). |
| **Live outings** | "Start outing now" (Sightings › Outings) starts one at the current time. A green chip in the top bar shows it while it runs ("● Rainham · since 07:45 · 12 seen"). "End outing" stops it. |
| **Outing in the add form** | An Outing field appears only when the date has outings. It picks the outing that covers the time by itself, but only when there's no doubt, and stops following once you choose. "Save & add another" keeps the outing. |
| **Outings tab** | Sightings page › Outings lists every outing, newest first, 100 at a time with "Show more". |
| **Dates in search** | "May 2025", "may" (the most recent May), "2025", "12 May 2025", "12/5/2025" (UK order) and "2025-05-12" offer "Open … in the calendar" as the first suggestion. |
| **Demo data** | `scripts/make_demo_data.py` now also creates outings (with seasonal weather) for about 60 % of trips. |

---

## 2. Checks

- **Tests:** 215 automated (81 new), all passing in about 27 s, repeated three times to check for flakiness. New tests cover:
  - date parsing and week labels;
  - outing rules, storage, undo and default-outing choice;
  - calendar summaries, firsts with and without filters, and the probable-IDs setting;
  - month-cell lines and the year shading;
  - UI flows: clicking days, the keyboard, view zooming, date search, starting/adding to/ending an outing, the outing form's errors and "discard changes?", and delete with undo.
- **Performance** with 20,000 sightings and 1,006 outings (refresh and paint):

  | Action | Time |
  |---|---|
  | Month view | 22 ms |
  | Month view, birds only | 22 ms |
  | Year view | 29 ms |
  | Week view | 26 ms |
  | Day view | 45 ms |
  | Day panel (busiest day, 57 sightings) | 64 ms |
  | Outing panel | 33 ms |
  | Outings tab (was 324 ms with 500 rows) | 59 ms |
  | Calendar data for a whole year | ≤ 25 ms |

- **Packaged build:** still 111 MB; its smoke test passes (opening the window now builds the calendar too).
- **Visual checks:** screenshots of all four views, the day panel, outing panel, outing form and Outings tab, in light and dark (`scripts/screenshot.py --pages calendar-month day-panel outing …`).

---

## 3. Problems found and fixed

| Problem | Fix / lesson |
|---|---|
| Nearly every day in the year view had a ★ (about 250 species are "new for the year" each year) | The year view stars lifers only, which are rare and worth spotting; month and week views keep both kinds |
| The year view needed scrolling | 6 × 2 layout when there's room, and the count shortens to a number on narrow cards |
| Month cells showed one name and a lot of empty space | Day summaries carry the top six names; the cell shows as many as fit |
| Three "Gull" (genus) records counted as three species | Kinds are counted by species, else by name |
| The window could no longer shrink enough for the sidebar to collapse (caught by a test) | A long explanation in the Outings tab couldn't wrap; measured each page's minimum width to find it |
| A UI test failed only when run after others: the search popup's timer fired after its window was destroyed | Timers now pass the popup as their *context object*, so Qt cancels them if the popup goes first |
| A stray 640-px box behind the filter chips in dark screenshots | Removed widgets wait for `deleteLater()`; one never laid out keeps Qt's default 640 × 480 size and still draws. A shared `clear_layout()` now hides widgets as it removes them (it replaced 7 copies of the same loop) |
| With the side panel open, the view switch read "Yea · Mont" | Measured the toolbar (564 px needed, 556 available); the title now moves to its own line when narrow, and switch buttons never shrink below their text |
| The outing form reported one mistake per Save | It now checks every rule at once, even when the temperature can't be read |
| `from conftest import …` broke when a second conftest was added | Shared test data moved to `tests/helpers.py`; test file names must be unique across folders |

---

## 4. Deferred (deliberately)

| Item | Where |
|---|---|
| Keyboard movement between individual days (arrows currently change the period) | Phase 12 polish, with the accessibility pass |
| Screen-reader detail for painted views (they announce a summary, not each day) | Phase 12 accessibility pass |
| The side panel sliding *over* the page on narrow windows | Phase 12 |
| Mini map of the day's sightings in the day view | Phase 8 (map) |
| Linking several existing sightings to an outing from the Sightings table | Phase 12 (bulk edit) |
| Weather filled in automatically from an online service | Not planned: the app works offline and asks for nothing online |
