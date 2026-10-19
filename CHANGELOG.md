# Changes

Each version's notes are used for its download page on GitHub (`scripts/release_notes.py`).

## 1.4.0

- **Import from eBird** (Settings › Import & export › From eBird). Thicket reads eBird's **Download My Data** file, with every species on every checklist and its position, time, count and notes, or a life or year list. Each sighting links back to its checklist on eBird. Importing a newer download later adds only what's new, and a life list followed by the full data doesn't double anything up. Escaped and domestic birds are marked not wild. The website's Help page has a step-by-step guide.

## 1.3.0

- **Choose on map:** when adding or editing a sighting, the button beside the position box opens a map. Click where you saw it, drag the pin to adjust, and the grid reference (or coordinates outside Britain) is filled in, with the place it's in. Zoom in for a more precise position. From the keyboard, the arrow keys move the map and Enter picks its centre.
- Fixed: after changing some settings (such as online features), switching between light and dark could show an error message.
- Thicket is free software under the GNU General Public License v3. The licence comes with the app (`LICENSE.txt` in the program folder) and is mentioned in Settings › About.

## 1.2.1

- Fixed: switching between light and dark while Thicket was open (in Settings, or when Windows switches by itself) turned the map's clusters black and hid their numbers until Thicket was restarted.
- Thicket has a website: [nevermore1983.github.io/Thicket](https://nevermore1983.github.io/Thicket/), with a tour of the features, help with installing and backing up, and exactly what Thicket connects to.

## 1.2.0

WildLife is now called **Thicket**.

- The new name is on the window, the Start menu, the installer and exports. Nothing else changes.
- Installing Thicket over WildLife upgrades it in place. Your sightings, photos, settings and backups carry straight on, and the old Start-menu and desktop shortcuts are replaced by Thicket ones. A taskbar pin keeps working.
- Exports made by WildLife import into Thicket as usual.
- Behind the scenes some names stay as they were, so nothing goes missing: the data folder is still `%LOCALAPPDATA%\WildLife`, and a backup folder you chose keeps its "WildLife Backups" folder. New backup folders are called "Thicket Backups".

## 1.1.0

WildLife now works outside the UK, starting with the United States.

- **Where you record:** choose the UK or a US state, when WildLife first starts or in Settings › Region.
- **Species packs for every US state** (and DC), downloaded in the app: species recorded in that state from GBIF, with the common names US birders and naturalists use, most-recorded first in suggestions. Each pack is checked against its published checksum before it's installed. Packs only add species: a species already in your list is never copied, so your life list counts it once.
- Species suggestions and common names follow your region ("robin" suggests American Robin in Ohio, Robin in the UK). Either name finds a species.
- The map opens on your region. Grid squares, which use the British grid, are offered in the UK only.
- Positions outside Great Britain are shown as latitude and longitude.
- Spreadsheet dates are read month/day in the US and day/month in the UK, with a switch on the import page.
- iNaturalist times in UTC are converted with your PC's time zone outside the UK.
- Exports say where each species name comes from: the UK Species Inventory or GBIF.

## 1.0.3

The first version available to download from GitHub.

- If another program (such as antivirus or a sync app) is briefly using the data file when WildLife starts, WildLife now waits a few seconds and tries again. It used to call this "damaged" and offer an older backup. If the file still can't be read, the message says so plainly. "Damaged" is kept for files that really are damaged.
- The third-party notices now state that WildLife's terms don't restrict modifying the Qt libraries it includes, as Qt's licence (the LGPL) requires for a public download.

## 1.0.2

- Rotating a photo removes its old thumbnails.
- Backups tidy their photo folder. A photo copy is removed only when neither your library nor any backup still kept needs it.
- Spreadsheet exports are safe to open in Excel: text starting with `=`, `+`, `-` or `@` is kept as text, not run as a formula.
- Pages showing "today" are redrawn just after midnight.
- Fixed: a backup folder with `#` or `%` in its name showed its backups as empty in the restore list.

## 1.0.1

Fixes from a full code audit (see `docs/15-code-audit.md`).

- Importing a photo that's in the recycle bin brings it back, instead of leaving it hidden there.
- Deleting a place that an outing uses explains why it can't be deleted.
- One backup runs at a time, so two can't spoil each other.
- Saving a sighting waits for photos still being added.
- Undoing an edit also brings back the photos it had.
- "Empty now" empties photos too.
- `_` and `%` in a search match only themselves. Bulk changes work on any number of sightings.

## 1.0.0

The first release: recording sightings, photos (including RAW and HEIC), calendar, map, statistics, outings, places, iNaturalist and spreadsheet import, exports, automatic verified backups, restore and a health check.
