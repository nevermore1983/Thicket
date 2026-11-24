# Changes

Each version's notes are used for its download page on GitHub (`scripts/release_notes.py`).

## 1.8.0

**Species packs for Latin America and the Caribbean.** 52 more regions in **Add a region…**: every country and territory from Mexico to Tierra del Fuego, every Caribbean island, Bermuda, the Falklands and South Georgia.

- **Where you record:** the welcome screen now offers Latin America and the Caribbean too. Its list appears once you choose it.
- **Names:** birds have the IOC names, spelt the British way ("Blue-grey Tanager"), as in Australia and New Zealand; eBird's names still find them. Everything else has GBIF's English names where there are any.
- **Search in the local language:** Spanish, Portuguese, French or Dutch, where GBIF has the names. "bem-te-vi" finds Great Kiskadee in Brazil, "colibrí" finds hummingbirds, and "pizote" finds White-nosed Coati.
- **The biggest packs yet:** Brazil's has 87,529 species and Mexico's 71,595. They still download and install in under half a minute.
- **Dates and the map:** spreadsheet dates are read day-first, except in Puerto Rico and the US Virgin Islands, which write them the US way; the switch on the import page changes it for one file. The map opens on your country or island.

## 1.7.0

**Species packs for Canada, Australia and New Zealand.** 22 more regions in **Add a region…**: every Canadian province and territory, every Australian state and territory, and New Zealand.

- **Where you record:** the welcome screen now offers Canada, Australia and New Zealand too. Each list appears once you choose it, so the page stays short.
- **Names:**
  - Canada has the names North American birders and naturalists use, as in the US packs. In Québec and New Brunswick you can also search in French: "mésange à tête noire" finds Black-capped Chickadee.
  - Australia and New Zealand have the IOC bird names Australian and New Zealand birders use, and their own names for everything else, spelt the British way ("Grey Butcherbird"). Weeds and pests that came from Britain keep their UK names, such as Spear Thistle.
  - New Zealand's Māori names are searchable where GBIF has them, which so far is only a few birds.
- **Dates and the map:** spreadsheet dates are read month-first in Canada, as in the US, and day-first in Australia and New Zealand; the switch on the import page changes it for one file. The map opens on your province, state or country.
- **Better names in other packs** (packs update from Settings › Region):
  - US packs now use the American Ornithological Society's newer names: Canada Jay (not Gray Jay), Thick-billed Longspur, and Common Gull for *Larus canus* (North America's bird is the Short-billed Gull). The old names still find them.
  - European packs spell "Grey" the British way for species the UK list doesn't have.

## 1.6.1

**Species packs for Russia, Turkey and the Caucasus.** Six more regions in **Add a region…**: European Russia (west of the Urals), all of Russia, Turkey, Georgia, Armenia and Azerbaijan. Russian names are searchable in both Russia packs.

- Fixed: a European or US pack could add a second copy of a species the UK list calls by a newer name, such as the Lesser Whitethroat (*Curruca curruca*, still *Sylvia curruca* in GBIF's list), which showed as "Grey Whitethroat". Packs now link to the UK species through its older names, and keep its UK name. If you installed a pack in 1.6.0, the copies are merged when Thicket 1.6.1 first starts: any sightings, notes and saved filters on them move to the UK species.

## 1.6.0

**Species packs for Europe.** Every European country, from Ireland and Iceland to Greece and Ukraine, has its own species pack (46 in all; Russia and Turkey may follow later).

- **Where you record:** the welcome screen offers the United Kingdom, **Elsewhere in Europe** (then a country) or the United States. In Settings › Region, **Add a region…** lists Europe's countries and the US states, with a search box.
- **Names in British English:** a species that's also in the UK list keeps its UK name, so a Robin is "Robin" in France too. Other species get English names from GBIF, preferring those used in Britain and Ireland.
- **Search in the local language:** typing "rougequeue noir" finds Black Redstart in France, and "pit-roig" finds Robin in Spain. Each pack carries names in its country's languages.
- Suggestions put the species most recorded in that country first. The map opens on the country, and spreadsheet dates are read day-first, as in the UK.
- As before, packs only add species: your sightings never change, and a species you already have (from the UK list, a US pack or one of your own) stays one species.

## 1.5.1

Fixes and improvements from a check of the code (docs/22-code-audit-3.md).

- Fixed: an eBird **Download My Data** file imported before 1.5.0 never got its outings. Import it again, and the sightings it brought in are grouped into one outing per checklist. (Nothing else changes: they still update from later downloads.)
- Fixed: when eBird renames a species (it updates its names every year), your next download no longer brings those sightings in a second time.
- Fixed: removing an eBird import later (Settings › Import & export) now puts away the outings it made, instead of leaving them empty. Undo brings them back.
- Fixed: an eBird checklist with no duration, imported on the day it was made, no longer looks like an outing in progress.
- Fixed: adding your own species under an older scientific name of a species in the list (such as *Parus caeruleus*, the Blue Tit) made a second copy of it. Thicket now says which species it is. "Larus sp." isn't accepted as a species any more, and hybrids written with both genus names are.
- **Change or remove your own species**, in Settings › Region › Your own species. A species can be removed if no sighting uses it.
- Before an eBird import, the check page says how many outings it will make.
- Outings made from eBird checklists at one of your places are named by the place and date (such as "Rainham Marshes · Sun 12 Oct 2026"), and link to their checklist on eBird.
- Updated the libraries that read photos (Pillow 13.0, rawpy 0.28).

## 1.5.0

- **Add your own species.** If a species isn't in your list (an escape, a new arrival, one from a region whose pack you haven't added), the species box now offers "Add … as your own species" as its last suggestion. Give it a name and its scientific name; its group comes from a known species of the same genus. It works like any other species, travels with your exports, and if a species pack adds it later, the two become one.
- **eBird checklists become outings.** Importing eBird's Download My Data now makes an outing for each checklist, with its date, start and end time, place, comments and whether it was a complete list, and groups its sightings in it. A newer download uses the same outings, and Undo import removes them too.
- **Choose on map for places**: the place editor has the same map button as the sighting editor, for putting a place's centre where you click.
- **Report a problem or suggest an idea** from Settings › About. Each opens a short form on GitHub in your browser, with Thicket's and Windows' versions filled in. Nothing is sent unless you submit it there. When Thicket shows "Something went wrong", **Report it…** copies the details for you to paste in.

## 1.4.2

Fixes from a full check of the code.

- Fixed: an iNaturalist or eBird file with the same record in it twice (two exports pasted together, say) stopped the import with an error. The second copy is now skipped, as "Appears twice in this file".
- Fixed: a species brought in by a Thicket export from another PC (one from a US state's species pack, say) couldn't be found by name afterwards, in the species picker or in search. Species imported before this version are put right when you upgrade.
- Fixed: outside the UK, an iNaturalist observation from before 1970 could stop the whole import.
- Fixed: on the welcome screen, choosing the United States and pressing Continue before the list of states had loaded set up only the UK list. Thicket now waits for you to choose a state.
- The welcome screen now goes online only if you choose the United States, as the privacy page says. Choosing the UK never connects to anything.
- Sorting the sightings list by Place now uses the location names it shows, such as eBird hotspots.

## 1.4.1

- Fixed: sightings imported with a location name but no saved place, such as eBird hotspots, showed "No location", as if the location was lost. The name now shows in the sightings list, the calendar and the sighting's details (as "Location name"). iNaturalist's place names show the same way.
- eBird: importing **Download My Data** after a life list now fills in those sightings' times and exact positions, instead of calling them already imported. A sighting you've edited in Thicket keeps your version.

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
