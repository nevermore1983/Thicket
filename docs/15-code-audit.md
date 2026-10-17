# WildLife — code audit (version 1.0.0)

**Date:** 17 October 2026
**Scope:** all 23,350 lines in `src/`, plus the build scripts and tests.
**Status:** All bugs (A1–A12) and improvements B1, B2, B3 and B5 **fixed on 17 Oct 2026 in version 1.0.1** (section 4). B4, B6, B7 and B8 are left for later.

**How it was done:**
- I read every layer: database, services, screens and the map page.
- Broader lint rules than the project normally uses: bug patterns, security, time zones, performance.
- Every suspected bug was then **proved with a real test** against a real WildLife library. The 7 marked "confirmed" each failed exactly as described.

---

## 1. Bugs

| # | Severity | What goes wrong | Where | Confirmed |
|---|---|---|---|---|
| A1 | **High** | **Re-importing a photo that's in the recycle bin hides it.** The import says "1 already in your library". The photo stays in the bin and doesn't appear in the Inbox. If you attach it to a sighting it's invisible there, and it's permanently deleted when the bin empties (30 days). It happens wherever photos come in: Add photos, the editor and iNaturalist photo downloads. (The WildLife-archive import already handles this case correctly.) | `services/photos.py` `_import_one` | ✅ test |
| A2 | Medium | **Deleting a place an outing uses gives "Something went wrong".** The "is this place in use?" check counts sightings but not outings, so the database refuses the delete with a raw error. Nothing is lost, but the message doesn't say why. | `services/places.py` `delete`, `repositories/places.py` `in_use` | ✅ test |
| A3 | Medium | **Two backups at once can trip each other up.** Nothing stops a second backup starting while one runs: the automatic start-up backup plus "Back up now", or the backup on exit. The first to finish clears away the second's unfinished file mid-write, and the second then fails with a misleading "check free space" message. The health check's clean-up can do the same to a photo import running at that moment. | `services/backup.py` `_rotate`, `services/health.py` | ✅ test (the clean-up removes another backup's file) |
| A4 | Medium | **Photos still being added when you press Save are left out.** RAW files take a few seconds. The sighting saves without them and they land in the Photo Inbox. If you close the panel before they finish, the finished import tries to update a form that has gone, and the error dialog appears. | `ui/panels/sighting_editor.py` `_add_photo_files` | By reading |
| A5 | Medium‑low | **A thumbnail can show "Can't display" for a good photo.** Two background threads making the same thumbnail write to the same temporary file. One can fail, and the grid then remembers "Can't display" until WildLife restarts. | `services/photos.py` `thumbnail` | By reading |
| A6 | Low | **Any other `.db` file in the backup folder stops all backups.** For example a copy you made yourself. The clean-up step expects every `.db` there to have a date in its name, and fails on the first one that doesn't. | `services/backup.py` `_rotate` | ✅ test |
| A7 | Low | **Settings › "Empty now" empties sightings only.** Photos in the bin stay, including those of the sightings just removed, for another 30 days. The button is also greyed out when only photos are in the bin. | `ui/pages/settings_page.py` `_empty_bin` | ✅ test |
| A8 | Low | **Searching for 1–2 characters treats `_` and `%` as wildcards.** Typing `_` matches every sighting. | `data/sql_filters.py` | ✅ test |
| A9 | Low | **Changing more than 32,766 sightings at once fails.** That's SQLite's limit on values per query. It only matters if you select an enormous list for a bulk change. | `repositories/sightings.py` | ✅ (limit measured) |
| A10 | Low | **Undoing an edit doesn't bring back photos you removed in that edit.** They're in the Photo Inbox, not lost. | `sighting_editor.py` `save` | By reading |
| A11 | Low | **"This place is used by N sightings" counts ones in the recycle bin**, so you can't find them in your lists. | `repositories/places.py` `in_use` | By reading |
| A12 | Cosmetic | **Names from an import file are shown as formatted text without escaping** (in the "choose a species" list). A name containing `<` displays oddly. Qt labels can't run scripts, so this is display only. | `ui/exchange/import_dialog.py` | By reading |

---

## 2. Improvements

| # | Worth it? | What |
|---|---|---|
| B1 | **Yes** | **One shared "copy safely" helper.** The "copy to a temporary file, then rename" pattern is written out separately in 7 places (photos, backup, health, restore, export). One helper with a temporary name unique to each copy fixes A3 and A5 together and removes the repetition. |
| B2 | **Yes** | **One backup at a time.** A lock in the backup service: a second request waits, or is skipped with "a backup is already running". |
| B3 | **Yes** | **Tests for start-up.** `app.py` has 0% test coverage, so the "damaged data, restore the latest backup?" path is only checked by the build's smoke test. It can be tested with the dialog's answer supplied automatically. |
| B4 | Later | **Split the biggest files.** The spec aims for about 400 lines per file. Seven are over 600, led by `sighting_editor.py` at 905, then `main_window.py` (743) and `charts.py` (742). They work. Splitting would make them easier to change, but it carries risk, so it's best done alongside a feature that touches them. |
| B5 | Small | The same SQL timestamp expression (`NOW`) is defined in 4 files. Define it once. |
| B6 | Small | **Disk tidiness.** Rotating a photo leaves the old thumbnails behind, and the backup photo folder never drops photos you've permanently deleted. Both only grow slowly. A health-check option could tidy them. |
| B7 | Optional | **Spreadsheet safety.** A note starting with `=`, `+`, `-` or `@` is treated as a formula when an export is opened in Excel. It's your own data, so low risk, but a leading `'` on such cells is the usual guard. |
| B8 | Small | The calendar and the dashboard work out "today" for themselves. Left open past midnight, they still highlight yesterday until you move to another view. |

---

## 3. Checked and fine

- **SQL injection.** All 52 places that build SQL use column names written in the code. Anything you type is always passed as a value, never pasted into the SQL.
- **Internet access.** HTTPS only, an allow-list of hosts that also applies to redirects, a size cap, and plain-English errors.
- **Archive imports.** Photos are written under WildLife's own file names, never a path taken from the archive ("zip-slip" safe).
- **The map page.** Every name or note shown in a map pop-up is escaped, so data can't run as script.
- **Saving.** Every change is one database transaction. Undo restores exact previous values. Foreign keys and full-sync writes are on.
- **Background work.** Results always come back to the screen's own thread. A crash in a job is logged and reported, never lost.
- **Data folder vs program folder.** They're kept apart, so upgrades and uninstalls can't touch your data (Phase 14).

---

## 4. What was fixed (version 1.0.1)

Each fix started with a test that failed on the old code and passes on the new.
- **Tests:** 520 automated tests pass, 24 of them new. Coverage is 90% (89% before), and `app.py` went from 0% to 36%.
- **Build:** the app smoke test and the full install, upgrade and uninstall check both pass.

| # | Fix | Test |
|---|---|---|
| A1 | A photo imported again comes **out of the recycle bin** (into the Inbox). A photo whose library file had gone gets the file back from the copy being imported. | `test_photo_library::test_importing_a_photo_from_the_recycle_bin_brings_it_back`, `…_puts_back_its_missing_file` |
| A2, A11 | Deleting a place checks outings too, and says exactly what still uses it: "used by 2 sightings (1 in the recycle bin) and 1 outing". | `test_sightings::test_a_place_an_outing_uses_cannot_be_deleted_and_says_why`, `…_mentions_the_recycle_bin` |
| A3, B2 | **One backup at a time.** A second request waits for the first. Clean-up only removes unfinished files older than an hour, so it can't pull a file from under a copy still running, in the backup folder or (via the health check) the photo folder. Also fixed: a change saved while a backup ran was wrongly treated as backed up. | `test_safety_nets::test_backups_run_one_at_a_time`, `…_change_made_while_a_backup_runs…`, `test_files::test_only_old_part_files_are_cleaned_up`, `test_health` |
| A4 | While photos are still being added, **Save waits**: the buttons are disabled, and Enter or Ctrl+S shows "Still adding photos…". Closing the form mid-import is quiet, and the photos stay in the Inbox. | `test_photos_ui::test_save_waits_while_photos_are_still_being_added`, `…_closing_the_form_while_photos_are_added_is_fine` |
| A5, B1 | **One shared "copy safely" helper** (`data/files.py`) gives every copy its own temporary name. Seven copies of the old pattern were replaced. The same thumbnail made by 8 threads at once failed every time before the fix, and now always works. | `test_files.py` (4 tests) |
| A6 | Only files named like WildLife's backups are rotated or offered for restore. Any other `.db` file in the folder is left alone. | `test_safety_nets::test_other_files_in_the_backup_folder_are_left_alone` |
| A7 | "Empty now" empties photos too, and works when only photos are in the bin. The Settings row shows both counts. | `test_main_window::test_empty_now_empties_photos_too`, `…_when_only_photos_are_in_the_bin` |
| A8 | `_` and `%` in a search match only themselves. | `test_sightings::test_search_treats_wildcard_characters_as_plain_text` |
| A9 | Bulk changes go to the database in parts of 500, so any number of sightings works. | `test_sightings::test_bulk_changes_to_tens_of_thousands_of_sightings` |
| A10 | Undoing an edit also puts back the photos it had. The form now saves its photos in one step (`PhotoService.set_sighting_photos`). | `test_photos_ui::test_undoing_an_edit_brings_back_photos_removed_in_it` |
| A12 | Names from an import file are escaped. | `test_exchange_ui::test_names_from_the_file_are_shown_as_plain_text` |
| B3 | The start-up path ("can't open your data, restore the latest backup?") is now its own function, `app.open_data`, tested with the real dialog. | `tests/ui/test_startup.py` (4 tests) |
| B5 | The SQL timestamp is defined once (`data/repositories/__init__.py`). | (covered by the existing tests) |
