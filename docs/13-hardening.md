# WildLife — Phase 13: hardening

**Date:** 16 October 2026
**Status:** Complete, awaiting review

This phase tried to break the app on purpose:
- a library of 20,000 sightings;
- the app killed in the middle of saving and of backing up;
- a full disk;
- a damaged data file;
- a backup drive that isn't there.

Each data-loss path it found is now fixed, and a test keeps it fixed. The spec's error table (section 10) and acceptance checklist (section 11) are checked off below, one row at a time.

**Exit rule: no known data-loss paths.** ✅ Met. Every problem below that could lose or damage data is fixed and has a test.

The checks that only a person can do are in [13-manual-tests.md](13-manual-tests.md).

---

## 1. Data-safety problems found and fixed

| # | What could go wrong | Now | Test |
|---|---|---|---|
| D1 | **A backup cut short looked like a real one.** A snapshot interrupted part-way left a half-written file with the right name, so it could be offered for restore. | Snapshots are written to `….part` and only renamed when complete. Rotation cleans up stray `.part` files. | `test_failures::test_an_interrupted_backup_never_looks_like_a_backup`, `test_kill::test_killed_while_backing_up_leaves_only_sound_backups` |
| D2 | **A restore could lose your newest changes.** SQLite keeps recent changes in a side file (the WAL). The safety copy taken before a restore ignored it, so changes still in the WAL were not in the copy. | The WAL is merged into the main file (a "checkpoint") before the safety copy is made. | `test_failures::test_restore_keeps_changes_that_were_still_in_the_side_file` |
| D3 | **Restoring over a damaged file crashed.** The safety copy couldn't read the damaged file. | The damaged files are copied as they are, to a `-damaged` folder, and the restore goes ahead. A failed restore is reported, never a crash. | `test_failures::test_a_damaged_data_file_can_be_replaced_by_the_latest_backup` |
| D4 | **A damaged data file gave a raw error at start-up.** A failed open also left the file locked. | A clear message: "Restore latest backup", or "Open data folder". The latest backup is found even when the data file can't be read. The file is closed after a failed open. | `test_failures::test_a_damaged_data_file_is_never_opened_quietly`, `test_restore::test_latest_backup_is_found_even_if_the_data_file_is_damaged` |
| D5 | **One Enter press could save twice.** The Count box passed Enter to the editor, whose "Enter on the date saves" rule fired as well. The result was two identical sightings. | Enter saves only when the date box itself has the focus, and a saved editor can't save again. | `test_scenarios::test_s1_quick_add_with_the_keyboard` (fails without the fix) |
| D6 | **Closing the app during a background job could crash it.** Examples are an automatic backup or making thumbnails. A job's database connection could be closed while it was still in use. | Connections in use are never closed under a job. The app waits (up to 60 s) for background work before it closes the data file. | `test_database::test_close_never_pulls_a_connection_from_under_a_running_job` |
| D7 | **A full disk** gave a technical error. | The save is undone completely, with the message "Not enough disk space, so nothing was changed." | `test_failures::test_a_full_disk_changes_nothing_and_says_so` |

**Killing the app** (the spec's "power cut mid-save" target):
- A helper program saves, or backs up, in a loop.
- The test kills it at several points with no warning (`test_kill.py`, 5 cases).
- Every save it reported is still there, and every backup left behind is sound.
- It passed 10 runs out of 10.

**Also fixed (not data loss):**
- **A damaged photo showed "File missing".** A file that is present but can't be read (damaged, or an unsupported format) now shows **"Can't display"**. "File missing" is kept for files that have gone. This applies in the grid, the sighting detail and the species profile.
- **291 "connection not closed" warnings in the tests.** Each one was a real connection left open by a background thread. There are now 0, and the suite fails if one comes back.

---

## 2. Speed and memory with the stress library

Measured on your PC with the **stress library**: 20,000 sightings, 1,483 species, 300 places, 995 outings and 4,485 photos (`scripts/make_demo_data.py --places 300 --species 1500`).

To repeat the measurements:

```
uv run python scripts/benchmark.py --data-dir local_data/demo13
```

| Area | Target | First run | Now |
|---|---|---|---|
| Start-up | ≤ 3 s | 2.55 s | **2.5–2.7 s** ✅ |
| Saving a sighting | ≤ 100 ms | 113 ms ❌ | **17 ms** ✅ |
| Global search | ≤ 200 ms | 33 ms | **32 ms** ✅ |
| Filter change | ≤ 300 ms | 24 ms | **14 ms** ✅ |
| Calendar view change | ≤ 300 ms | Day view 317 ms ❌ | **31–69 ms** ✅ |
| Map, 20k pins | ≤ 2 s | 0.71 s | **0.63 s** ✅ |
| Statistics page | ≤ 1.5 s | 0.37 s | **0.30 s** ✅ |
| Photo grid scroll | smooth | 5 ms | **4 ms** per step ✅ |
| Photo import | ≥ 5 per second | 93 per second | **98 per second** ✅ |
| Backup | ≤ 10 s | 5.5 s | **1.7 s** ✅ |
| Memory, normal use | ≤ 600 MB | 817 MB ❌ | **414–453 MB** ✅ |
| Long use (every page 30 times) | no growth | +287 MB ❌ | **+16 MB**, levels off ✅ |
| Species list after a change | (not in the spec) | **103 s** ❌ | **0.15 s** ✅ |

**What made the difference:**

- **Saving.** Each save rebuilt the dashboard straight away. Pages now refresh after the save, once (several changes together cause one refresh), and only the page you're looking at.
- **Day view.** Missing thumbnails were made while you waited. They're now made in the background and appear when ready.
- **Species and Places lists.** Columns that size themselves to their contents re-measured every row after each cell was filled, which took 103 seconds for 1,483 species. The sizing is now switched off while the list fills and runs once at the end.
- **Memory.**
  - The map had kept two copies of all 20,000 pins. It now keeps the one the current view needs, which saved 110 MB.
  - The thumbnail memory cache is smaller: 400 pictures.
  - Memory is now measured the way Task Manager does ("private working set") across the app and its map engine. The first figure also counted Windows files shared with other programs.
- **"Long use" growth.** This was a measuring mistake, not a leak. Qt removes closed widgets a moment later, and the benchmark never gave it that moment. With that fixed, memory levels off.
- **Photo grid.** Thumbnails for rows you scroll quickly past are no longer made. Only the rows you stop at are.

---

## 3. Spec section 10: every error case and its test

| Situation | Tested by |
|---|---|
| Photo file missing | `test_photo_library::test_missing_file_is_found_and_can_be_located`, `test_photos_ui::test_missing_file_can_be_located_in_the_viewer`, `test_photos_ui::test_missing_files_are_reported_on_the_library`, `test_health::test_missing_photos_come_back_from_the_backup` |
| Photo corrupt or unsupported | `test_photos_and_backup::test_bad_files_are_reported_not_fatal` (import), `test_error_cases::test_a_damaged_photo_says_cant_display_and_a_gone_one_says_missing` (existing photo) |
| Invalid coordinates, swapped lat/lon | `test_geo::test_swapped_pair_is_flagged`, `test_domain::test_sighting_rules` |
| Grid reference typo | `test_error_cases::test_a_grid_reference_typo_is_explained` |
| Date in the future; later today | `test_domain::test_sighting_rules` (the editor also can't pick a future day), `test_spreadsheet_import` (row reason), `test_error_cases::test_a_time_later_than_now_today_gets_a_gentle_note` |
| Map fails to load | `test_map_ui::test_no_webgl_shows_an_explanation`, `test_map_ui::test_plain_background_and_banner_when_online_is_off` |
| No internet | `test_map_ui::test_plain_background_and_banner_when_online_is_off`, `test_inaturalist_import::test_photos_need_online_features`, `test_safety_nets::test_fetch_errors_are_explained`, `test_web::test_network_gate` |
| Malformed import file | `test_exchange_ui::test_a_wrong_file_is_explained`, `test_failures::test_an_import_that_fails_part_way_adds_nothing`, `test_error_cases::test_an_import_report_can_be_saved` |
| Import of unknown species | `test_inaturalist_import::test_names_are_matched_to_the_uk_list`, `test_inaturalist_import::test_unmatched_names_without_a_choice_are_skipped`. ⚠️ **"Create a custom species" is not built** (see section 5). |
| Backup drive not connected | `test_photos_and_backup::test_backup_to_missing_drive_fails_clearly`, `test_photos_and_backup::test_backup_is_due_daily_and_after_failures`, `test_error_cases::test_a_failed_backup_shows_on_the_dashboard` |
| Backup verification fails | `test_safety_nets::test_a_backup_that_fails_its_check_is_discarded`, `test_safety_nets::test_a_full_backup_drive_is_explained` |
| Database problem at start-up | `test_failures::test_a_damaged_data_file_is_never_opened_quietly`, `test_failures::test_a_damaged_data_file_can_be_replaced_by_the_latest_backup`; the dialog itself is checked by hand (manual test M5) |
| Disk full | `test_failures::test_a_full_disk_changes_nothing_and_says_so` |
| Data folder in OneDrive | `test_error_cases::test_a_cloud_synced_data_folder_is_spotted`, `test_error_cases::test_settings_warns_about_a_cloud_synced_data_folder`. ⚠️ **Not built: a first-run warning and "Move data folder…"** (see section 5). |
| Unexpected error | `test_error_handler::test_unexpected_error_is_logged_but_user_sees_friendly_text`, `test_safety_nets::test_unexpected_errors_are_logged_and_shown_gently` |
| Accidental delete | `test_sightings::test_delete_goes_to_recycle_bin_and_can_be_undone`, `test_main_window::test_delete_from_detail_and_undo`, `test_main_window::test_recycle_bin_restore` |
| Two copies opened | `test_safety_nets::test_a_second_launch_finds_the_first` |

---

## 4. Spec section 11: acceptance checklist

| Item | Status |
|---|---|
| Scenarios S1–S7 work as described | ✅ `tests/ui/test_scenarios.py`, one test per scenario |
| S1 under 10 s, keyboard only | ✅ The test types the whole sighting with keys alone. Timing it by hand is manual test M1. |
| Every Must feature complete | ⚠️ All but custom species (section 5) |
| Every section 9 target met | ✅ Section 2 above. Offline, privacy and accessibility are covered by tests and the Phase 12 audit. |
| Every row of section 10 tested | ✅ Section 3 above, with the two gaps marked |
| Backup → wipe → restore identical | ✅ `test_scenarios::test_s6_new_pc_restore_from_the_backup_drive` (data and photos) |
| Export JSON → import into empty library identical | ✅ `test_wildlife_import::test_round_trip_into_an_empty_library` |
| UI/UX audit has no open "high" items | ✅ All fixed in Phase 12, and the audit runs as a test |
| Installer works on a fresh account; uninstall keeps data | ⏳ Phase 14 |

---

## 5. Open items for you to decide

**Decided on 17 Oct 2026:** both moved to the version 2 backlog (spec section 12).

1. **Custom species** (spec 5.1 and section 10: "create a custom species" while importing). This is not built, following your Phase 12 choice to leave out "add your own species". Today a name that isn't on the UK list can be matched to an existing species, or its rows can be skipped. Options:
   - build it (about a day's work);
   - or move it to the version 2 backlog.
2. **"Move data folder…"** and a first-run warning about cloud-synced folders. The default data folder is in AppData, which OneDrive doesn't sync, so this only matters if someone picks a folder with `--data-dir`. Settings already warns. Options:
   - add a "Move data folder…" button;
   - or move it to the backlog.

---

## 6. Tests and tools added

- **Tests.**
  - 494 tests pass: 34 in the new files listed below, plus 5 added to existing files.
  - Code covered by tests: **89%**. The `pytest-cov` tool was added for development only.
  - Warnings: **0**. A leaked connection now fails the suite.
- **`tests/integration/test_failures.py`:** full disk, failed import, interrupted backup, damaged file, restore and WAL.
- **`tests/integration/test_kill.py`:** kills a real process mid-save and mid-backup.
- **`tests/integration/test_safety_nets.py`:**
  - backup checks and a full backup drive;
  - the online allow-list and its redirects;
  - the error reporter, a second launch, and log rotation.
- **`tests/ui/test_scenarios.py`:** scenarios S1–S7.
- **`tests/ui/test_error_cases.py`:** the section 10 rows not covered before.
- **`scripts/benchmark.py`:** measures every section 9 target on any data folder. `--soak N` repeats every page N times to look for memory growth.
- **`scripts/make_demo_data.py`:** new `--places` and `--species` options for the stress library.

## 7. What I learned

- **"Saved" has to mean "on disk, complete".** Each of the backup problems was a moment when a file looked finished but wasn't. The fix is always the same pattern: write somewhere else, then rename in one step.
- **Kill tests find what reading the code doesn't.** The connection-closing crash only showed up when coverage measurement slowed the tests down and changed the timing.
- **Measure before fixing.** The "memory leak" was a measuring mistake: Qt deletes widgets later, and the benchmark never let that happen. The real memory saving was elsewhere, in the duplicate map data.
- **Qt traps:**
  - Columns sized to their contents, combined with filling a visible table one cell at a time, gets slower the more rows there are, and badly so with thousands.
  - A text box passes Enter up to the form it sits in.
