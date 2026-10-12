# WildLife — Phase 12: UI/UX audit

**Date:** 12 October 2026
**How:** checked against the UX rules agreed in Phase 1 (section 3.3), in two parts:

* **Automated:** `scripts/audit_ui.py` opened every page, side panel and window on the 20,000-sighting demo library. For every visible control it checked three things: that a screen reader can say what the control is, that Tab reaches it, and that the wording follows the agreed terms.
* **By eye:** screenshots of every page, empty and full, in light and dark, with the side panel open and closed.

**Severity:** *high* = wrong information, or something a keyboard or screen-reader user can't do at all. *Medium* = works, but harder than it should be. *Low* = wording or finish.

The script's first run reported 102 items. Most were the script being stricter than Qt's own conventions: for example, Tab reaches a group of options through the selected one, and the arrow keys move between options. Those rules were written into the script, which left the real items below.

---

## Findings

| # | Severity | Where | Finding | Fix |
|---|---|---|---|---|
| A1 | high | Species profile, Map | Icon-only buttons have no name (the profile's photo thumbnails; the map's "sightings without a location" button). A screen reader just says "button". | Name every icon-only button |
| A2 | high | Species page | Says "certain identifications of **wild animals**", but the list now includes plants and fungi | Correct the wording everywhere "animal" is used to mean "wildlife" |
| A3 | high | Sightings page | With the side panel open, the header squeezes "All sightings" to "sightin" | Narrow header: Export becomes an icon button, and the page's second "Add sighting" hides (the top bar has one) |
| A4 | high | Everywhere | No keyboard shortcuts sheet (a *Must* in the spec) | **?** opens a sheet listing every shortcut |
| B1 | medium | Sighting, place and outing editors; Settings | Field labels aren't linked to their fields, so a screen reader can't say the field's name, and there's no Alt+letter access | The shared field helper links each label and reads its help text out too |
| B2 | medium | Sightings, Species, Places, Statistics tables; restore list; map background menu | Tables and lists have no names | Name them |
| B3 | medium | Calendar | Arrow keys change the month; a keyboard user can't choose a day, so **N** ("add on the selected day") only works with the mouse | Arrows move the selected day; Page Up / Page Down change the period |
| B4 | medium | Editors | Mistakes are shown only when you press Save | Check each field when you leave it (time, count, position, temperature) |
| B5 | medium | Dashboard (empty) | The first screen only offers "Add your first sighting", yet most of your records will come from iNaturalist | Add "Import from iNaturalist" and "Import a spreadsheet" |
| B6 | medium | Statistics, Species (empty) | The empty states have no action button (rule: every empty state offers one) | Add one |
| B7 | medium | Species picker | The suggestion list shows a horizontal scroll bar and cuts off "seen 12×" | No sideways scrolling; long names shortened with "…" |
| B8 | medium | Sightings table | The Photos column shows "3 ph…" | A camera icon and the number |
| B9 | medium | Photos page | The photo-size slider has no label or name | Small/large picture icons each side, and a name |
| C1 | low | Places, Settings, Export | "Saved locations you visit", "Records (and photos)", "Your complete records": the agreed words are Sighting, Place and Species | Reworded |
| C2 | low | Map (empty) | Nothing explains how pins appear | A note like the calendar's |

**Checked and fine:**
* Every page has an empty state.
* Long jobs show progress (imports, exports, backups, the health check, the statistics and map loading).
* Deleting can be undone.
* Focus is always visible.
* Option bars and the sidebar work with Tab and the arrow keys.
* Dark mode has its own validated colours.

---

## Fixed in Phase 12

**All 15 items are fixed.** Section 1 of [12-polish.md](12-polish.md) shows each fix, and `tests/ui/test_accessibility.py` keeps the automated checks running on every build.
