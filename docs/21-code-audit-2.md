# Thicket — code audit 2 (version 1.4.1)

**Date:** 25 October 2026
**Scope:** everything since the first audit (docs/15-code-audit.md, versions 1.0.1 and 1.0.2): regions and species packs, the rename, Choose on map, the eBird import, the GitHub workflows and the build and website scripts. Then a sweep of all 25,100 lines in `src/` for the usual kinds of bug.
**Status:** every bug (A1–A5) and improvements B1–B3 **fixed**, for version 1.4.2. 650 tests pass (644 before), lint is clean, and the test run reports no warnings.

**How it was done:**
- I read the new and changed code line by line, layer by layer: database and migrations, services, screens, the map page and the workflows.
- Then I swept the whole codebase for known kinds of bug:
  - background work reporting to a window that has closed;
  - SQL built from text;
  - swallowed errors;
  - half-written files;
  - leftover notes and debugging prints;
  - workflow permissions and inputs;
  - scripts that delete files.
- I ran the full suite with every warning shown.
- I proved each suspected bug with a real run before fixing it ("confirmed" below), and each fix comes with a test that fails without it.

---

## 1. Bugs

| # | Severity | What went wrong | Where | Confirmed |
|---|---|---|---|---|
| A1 | **High** | **The same record twice in one import file crashed the import.** The check page promised two new sightings, then Import stopped with a raw database error ("UNIQUE constraint failed"). It affected iNaturalist and eBird files, for example two exports pasted together. Nothing was half-imported (it's one transaction), but nothing came in either. | `services/importer.py` `preview_records` | ✅ run, then test |
| A2 | **High** | **Species brought in by a Thicket export couldn't be found by name.** When an export from another PC has a species this library's list lacks (one from a US state's pack, say), it's added as your own species, but without searchable names. The sightings came in, but the species picker, search and later imports couldn't find the species. | `data/repositories/exchange.py` `insert_custom_taxon` | ✅ run, then test |
| A3 | Medium | **One old iNaturalist observation could stop an import outside the UK.** For a region other than the UK, iNaturalist's UTC time is converted with the PC's time zone. Windows can't do that for dates before 1970 and raised an error, so the whole file failed. (Only when the observer's own typed time can't be read, so rare.) | `domain/dates.py` `pc_local` | ✅ run, then test |
| A4 | Medium | **The welcome screen could quietly ignore "United States".** Choosing the US and pressing Continue before the list of states had arrived installed just the UK list, without a word. | `ui/dialogs.py` `FirstRunDialog` | By reading, then test |
| A5 | Medium | **The welcome screen went online even if you chose the UK.** It fetched the list of US states from GitHub as soon as the region page appeared. The website's privacy page promises GitHub is asked "only when you add a state". | `ui/dialogs.py` `FirstRunDialog` | By reading, then test |

## 2. Improvements

| # | What |
|---|---|
| B1 | **Sorting by Place now uses the name the list shows.** Since 1.4.1 the Place column shows an imported location's name (an eBird hotspot, say) when there's no saved place, but sorting still treated those as "no place". |
| B2 | **The release build runs on a fixed Windows version** (`windows-2025`), like the other workflows. `windows-latest` moves to a new Windows without notice. |
| B3 | The README inside a Thicket export had a heading underline one character too long since the rename. |

## 3. The fixes

- **A1:** the check page now marks the second copy of a record "Appears twice in this file" and imports it once. A row with its own problem (no date, say) still gives that reason instead.
- **A2:** an imported species now gets its scientific and common names in the search index. **Migration 0008** adds them for species imported before 1.4.2. Like every upgrade, it makes a safety copy of your data first.
- **A3:** when Windows can't convert a time, Thicket uses the PC's current offset from UTC, which is right to within an hour.
- **A4:** Continue now waits, saying "Choose your state first: the list is on its way."
- **A5:** the list of states is fetched only when you choose "United States". If it can't be fetched, the choice goes back to the UK and says why.
- **B1–B3:** as described above.

New tests:
- `test_the_same_observation_twice_in_one_file_is_imported_once`
- `test_a_species_from_another_regions_pack_can_be_found_after_import`
- `test_migration_8_makes_imported_species_findable`
- the pre-1970 case in `test_each_region_has_its_clock`
- `test_choosing_the_uk_never_goes_online`
- `test_the_welcome_waits_for_a_state_before_going_on`
- `test_sorting_by_place_uses_the_location_name_shown`

## 4. Checked and fine

- **Species packs:**
  - a pack is installed only if its size and SHA-256 match the manifest;
  - its records are checked before anything changes;
  - installing only adds or links species, never copies one;
  - the database has the indexes switching region needs.
- **Internet access:** still only through `services/online.py`, which uses HTTPS and approved hosts only, follows redirects only to approved hosts, and has a size limit.
- **Background work:** every task started from a screen either checks the screen still exists or belongs to one that outlives it.
- **SQL:** text is never pasted into SQL. The few statements assembled in code use only table and column names from the code itself.
- **Workflows:**
  - actions pinned to exact commits;
  - minimal permissions;
  - the one manual input reaches the script through the environment, never pasted into it;
  - releases run only from tags you push.
- **Scripts:** the ones that delete files only delete their own build or temporary folders.
- **Search:** imported location names are searchable, via the trigram index from migration 0001.
- **Rename:** the names Windows remembers still use the first name, as docs/14-packaging.md lists.

## 5. Not fixed (minor, noted for later)

- **Shared names between packs:** if a UK list update drops a name that a US pack also has, that name stays out of search until the US pack is next updated. Packs share one row per name, and the first pack to add a name owns it. The effect is tiny, and fixing it needs a different way of recording which pack added which name.
- **Small leaks:** the "Add a US state" and recycle bin windows are kept (hidden) after closing, until Settings is redrawn. That's harmless, and it means a late answer from the internet never reaches a deleted window.
- **Pack addresses:** the manifest's pack addresses aren't limited to Thicket's own GitHub releases. The manifest comes from Thicket's own release over HTTPS, and it also gives each pack's checksum, so a limit there would add little.
- **Idea:** the place editor could have "Choose on map" too.
