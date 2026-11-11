# Thicket — code and app audit 3 (version 1.5.0)

**Date:** 11 November 2026
**Scope:** everything new in 1.5.0 (your own species, the feedback links, eBird checklists as outings, Choose on map for places, the split of the three biggest files), then the app as a whole: speed, accessibility, libraries and the GitHub side.
**Status:** all six bugs (A1–A6) and improvements B1–B4 **fixed in version 1.5.1**. B5 is left for later. 680 tests pass (666 before).

**How it was done:**
- I read the new code line by line.
- I proved each suspected bug with a real run on a temporary library with invented data ("confirmed" below).
- I ran the full test suite with warnings shown, the accessibility audit over every page, and the speed benchmark on the 20,000-sighting demo library.
- I checked the libraries for newer versions, and GitHub for issues, labels and downloads.

---

## 1. Bugs

| # | Severity | What goes wrong | Where | Confirmed |
|---|---|---|---|---|
| A1 | **Medium‑high** | **An eBird "Download My Data" file imported before 1.5.0 never gets its outings.** Importing the same file again says every sighting is "already in Thicket" and skips it, so no outings are made and nothing is grouped. Outings are only made for sightings that are new, or that came from a life list first. | `services/importer.py` `run` | ✅ run |
| A2 | Medium | **Adding your own species under an older scientific name makes a second copy of a species you have.** "Parus caeruleus" is in the UK list as a synonym of Blue Tit (*Cyanistes caeruleus*). Add your own species only checks current names, so it accepted it, and search then showed two Blue Tits. Sightings and life-list counts would be split between them. | `repositories/taxa.py` `same_name` | ✅ run (full UK list) |
| A3 | Medium | **When eBird renames a species, your next download imports those sightings a second time.** eBird updates its names every year. Thicket recognises an eBird record by its checklist plus the scientific name, so a renamed species looks new. | `domain/ebird.py` `parse_row` (`source_id`) | ✅ run |
| A4 | Low‑medium | **Removing an eBird import later (Settings › Import & export) leaves its outings behind, empty.** The sightings go to the recycle bin, but the outings stay on the calendar and in the outings list. (Undo straight after importing does remove them.) | `services/import_history.py` `remove` | ✅ run |
| A5 | Low | **A checklist with no duration, imported on the day it was made, shows as an "outing in progress".** It has a start time and no end time, which is how Thicket marks an outing you're on now, so new sightings that day would default into it. | `domain/ebird.py` `_checklist` | ✅ run |
| A6 | Cosmetic | **Add your own species accepts "Larus sp."** as a species name, and refuses a hybrid written with both genus names ("Anas platyrhynchos × Anas acuta"). | `services/species_catalogue.py` `_SCIENTIFIC` | ✅ run |

## 2. Improvements

| # | Worth it? | What |
|---|---|---|
| B1 | **Yes** | **Your own species can't be renamed or removed.** A typo in the name is permanent. A small "Your species" list in Settings, with rename and (if unused) delete, would fix that. |
| B2 | Yes | **The import check page doesn't mention outings.** Before an eBird import it could say "and 12 outings, one per checklist". |
| B3 | Yes | **Outings made from checklists are all titled with just the location's name**, so twenty visits to one reserve read the same wherever the title shows without its date. Leaving the title empty when the place is one of yours gives "Rainham Marshes · Sun 12 Oct 2026". The outing could also link to its checklist on eBird, as sightings do. |
| B4 | Yes | **Two libraries have newer versions:** Pillow 12.3 → 13.0 and rawpy 0.27 → 0.28. Both read image files, where fixes matter most. Needs a full test run and a build, as Pillow 13 is a major version. |
| B5 | Later | **A Thicket export doesn't carry which eBird checklist an outing came from.** It only matters if you move to a new PC by export rather than by backup and then import eBird again; backups keep it. |

## 3. Checked and fine

- **Tests and lint:** 666 tests pass, lint and formatting are clean, and the run shows no warnings.
- **Speed (20,000 sightings, 4,485 photos):** every target is met. Start-up 2.2 s (target 3 s), saving a sighting 25 ms, search 48 ms, calendar views under 60 ms, map pins 0.7 s, statistics 0.4 s, backup 4.2 s, memory 410 MB (limit 600 MB).
- **Accessibility audit:** no failures on any page; only the wording notes accepted in earlier audits.
- **The file split:** nothing is imported under an old name, and the packaged app starts and draws its map.
- **Feedback links:** they send only the Thicket and Windows versions, and the `problem` and `idea` labels exist on GitHub.
- **Own species:** searchable by both names, counted in lists, and linked (not copied) when a pack later adds the same current name.
- **eBird outings:** a newer download reuses them, a deleted one isn't remade, and Undo import removes them.
- **GitHub:** no issues reported; 1.5.0 has been downloaded 9 times so far.

## 4. Still open from audit 2 (unchanged, minor)

- A name shared by two packs can drop out of search if the first pack's update removes it.
- The "Add a US state" and recycle bin windows are kept hidden until Settings is redrawn.
- Pack addresses in the manifest aren't limited to Thicket's own releases (each pack's checksum is checked).

## 5. The fixes (version 1.5.1)

- **A1:** an eBird record that's already in Thicket but in no outing is grouped into its checklist's outing on the next import. Grouping doesn't count as your edit, so later downloads still update the sighting. Undo takes them out again.
- **A2:** "Add your own species" also checks older names (synonyms), and says which species the name belongs to: "That's in the list already, as Silverweed (Potentilla anserina)".
- **A3:** an eBird record that isn't known by its id is matched by its checklist and the species it matched. A renamed species is then recognised, not imported twice.
- **A4:** removing an import later also puts away the outings it made that are left empty. Undo brings them back.
- **A5:** a checklist with no duration ends when it starts, so it never looks like an outing in progress.
- **A6:** a scientific name must be a genus and species. "Larus sp." is refused; subspecies and hybrids ("Dactylorhiza x grandis", "Anas platyrhynchos × Anas acuta") are accepted.
- **B1:** Settings › Region › Your own species lists them, with Change… (names and group) and Remove (only when no sighting uses it, the recycle bin included).
- **B2:** the import check page says "N outings, one per checklist".
- **B3:** at one of your places, a checklist's outing has no title, so it shows as "Place · date". Its panel links to the checklist on eBird.
- **B4:** Pillow 13.0 and rawpy 0.28. All tests pass, and the packaged app builds and starts.

New tests cover each of these (`test_ebird_import.py`, `test_own_species.py`, `test_own_species_ui.py`).
