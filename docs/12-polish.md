# WildLife — Phase 12: polish

**Date:** 12 October 2026
**Status:** Complete, awaiting review

An audit of every screen against the UX rules agreed in Phase 1, with every finding fixed. The audit itself now runs as a test, so the problems can't come back. Alongside it, the everyday-editing and "your own notes and lists" features you chose, and the scientific-name font.

---

## 1. The audit

The full findings are in [12-audit.md](12-audit.md): 4 high, 9 medium and 2 low. **All are fixed.**

| # | What was wrong | Now |
|---|---|---|
| A1 | Icon-only buttons with no name (photo thumbnails, the map's "without a location" button) | Every one has a name a screen reader can say |
| A2 | The Species page said "wild **animals**" (plants and fungi are included now); "animals counted" on charts | "Every wild species you've identified with certainty"; "individuals counted" |
| A3 | With the side panel open, "All sightings" was squeezed to "sightin" | When narrow, Export becomes an icon button and the page's second Add button steps aside |
| A4 | No keyboard shortcuts sheet | **?** or **F1** (or Settings › About) lists every shortcut |
| B1 | Form labels weren't linked to their fields | Linked in the one shared field helper, which fixed every editor at once; the help text is read out too |
| B2 | Tables and lists had no names | Named |
| B3 | Arrow keys in the calendar changed the month, so a keyboard user couldn't choose a day | Arrows choose the day, Enter opens it, Page Up / Page Down change the period |
| B4 | Mistakes in a time or a temperature showed only on Save | Checked when you leave the field; "930" is tidied to "09:30" |
| B5 | The first screen only offered "Add your first sighting" | It also offers **Import from iNaturalist** and **Import a spreadsheet** |
| B6 | Statistics and Species empty states had no button | They have one |
| B7 | Species suggestions scrolled sideways and cut off "seen 12×" | No sideways scrolling; long names give way |
| B8 | The Photos column showed "3 ph…" | The number, with "3 photos" on hover and for screen readers |
| B9 | The photo-size slider had no visible label | Small and large picture icons on either side |
| C1 | "Saved locations", "Records (and photos)", "Your complete records" | The agreed words: place, sightings |
| C2 | The empty map didn't say how pins appear | A note, as the calendar has |

**Found while fixing:**

* **Sidebar:** Tab reached only the current page's link. This is Qt's rule for any group of buttons, so the sidebar no longer uses one.
* **Option bars** (Year · Month · Week · Day, and similar): Tab sometimes went to an unselected option. The bar now sets its Tab stop itself, and the arrow keys still move between options.

---

## 2. New features

| Feature | Where |
|---|---|
| **Change several sightings at once** | Sightings › select › **Change…**: species, place (optionally replacing their own exact positions with the place's centre), date, or outing. One step to undo each. |
| **Put photos in order** | In the sighting editor, ‹ › under each photo; the first is the cover |
| **Fix the time of photos** | Photos › Inbox › select › **Fix time…** moves them by hours and minutes (for a camera clock that was wrong), with a preview and Undo |
| **Find moved photos** | Photos page (when files are missing) and the health check: **Look in a folder…**. WildLife looks through it and puts back every file that is exactly a missing photo (checked by its contents, not its name) |
| **Saved filters** | Any filter bar › **Saved**: save the current filter under a name ("Moth-trap nights"), choose one, delete one. The chip shows the name when a saved filter is in use. |
| **Species notes** | In a species profile: your notes on the species. They save themselves, and travel with a WildLife export (an import never overwrites your notes, and Undo removes the ones it added). |
| **Restore at a failed start** | If the data file can't be opened, WildLife offers **Restore latest backup**. Each backup now writes a small pointer beside the data saying where backups go, because the backup-folder setting lives inside the database that may be damaged. |
| **Scientific-name font** | Source Serif 4 (Adobe, SIL Open Font License) is bundled. It was downloaded from the tagged release in Adobe's repository and checked against that repository's own fingerprint for the file; a test checks it again on every run. |

---

## 3. Checks

- **Tests:** 456 automated (31 new), all passing. They include:
  - **Accessibility** (`tests/ui/test_accessibility.py`): every page, panel and window is checked for controls without a name or a Tab stop, so a new nameless button fails the build. Also the shortcuts sheet, and that typing "?" in a text box still types it.
  - **Hygiene**, now also covering tests: no placeholder functions, alias hacks, `@dataclass` on Qt classes, or conditions that can never fail.
  - Bulk changes and their Undo; the photo time shift; photo order; finding moved photos; saved filters (every filter option survives saving); species notes, including export, import and Undo; finding the latest backup with a damaged data file; the bundled font is the one recorded and is used.
- **The audit script** (`scripts/audit_ui.py`) on the 20,000-sighting library: no high, medium or low items left.
- **Packaged build:** smoke test passes; 572 MB (+1 MB for the font).

---

## 4. Problems found and fixed

| Problem | Lesson |
|---|---|
| A field label above a field isn't the same as a label *linked* to it | Screen readers need `setBuddy` / an accessible name; one shared helper fixed every form |
| Qt buttons in any `QButtonGroup` hand their Tab stop around as the checked one changes | Set Tab stops on purpose where it matters |
| The font's real family name is "Source Serif 4 **Variable**", so the old setting never matched | Ask Qt what the family is called; a test now checks the font is really used |
| I wrote `if False` / `or True` lines into tests twice, and a stray assignment once | The hygiene test now rejects dead conditions |
| `\n` written through the shell became real line breaks, twice more | Text containing backslashes goes through the Edit tool only, never a shell heredoc |

---

## 5. Not done (as agreed)

Catalogue browser and category editing, map extras (dragging a place's circle, KML), the offline map pack and mini maps stay out, as you chose at the start of the phase.
