# WildLife — Phase 11, part 1: plants & fungi, and importing from iNaturalist

**Date:** 12 October 2026
**Status:** Part 1 complete, awaiting review (part 2: CSV import, export, restore, health check)

Most of your records will come from iNaturalist, and over a third of them are plants and fungi. So WildLife now knows UK plants and fungi as well as animals, and can bring in an iNaturalist export, including the photos.

---

## 1. What was built

| Area | What you get |
|---|---|
| **Plants & fungi** | The species list grew from 65,500 animal names to **105,800 animal, plant and fungus names** (lichens included), with 17,300 English names. It installs in about 8 seconds, and once only. |
| **Categories** | Still 8 colours (the colour-blind-safe set), with groups merged: Bird · Mammal · **Reptile, amphibian & fish** · Butterfly & Moth · Dragonfly & Damselfly · **Plant** · **Insect & other invertebrate** · **Fungus & lichen** · Other. There are new plant and mushroom icons. |
| **Import from iNaturalist** | Settings › Import › iNaturalist. Choose the export (the `.zip` iNaturalist gives you, or the `.csv` inside it), check what will happen, then import. |
| **Check before importing** | Shows what's new, changed on iNaturalist since last time, already here, and what can't be imported and why (e.g. "Line 14 · No date"). Names not in the UK list ask you to choose a species; your choice is remembered next time. |
| **What each record becomes** | Date and time are UK clock time. The position and its accuracy are kept, and a saved place is filled in when the spot is inside it. Research grade becomes **certain**; needs-ID and casual become **probable**. Captive/cultivated becomes "not wild". Description and tags go to notes, and the place name to the location text. |
| **Importing again** | Only adds what's new and updates what changed on iNaturalist. A sighting you've **edited in WildLife is never overwritten**, and one you **deleted** isn't brought back. |
| **Undo** | The whole import is one step: "Undo import" in the window, or Undo on the message afterwards. |
| **Photos (optional)** | Downloads every photo of each observation at original size, in the background, with a progress bar and a Stop button. Photos already downloaded aren't fetched again. Needs "Allow online features". |
| **Where it came from** | An imported sighting's details say "Imported from iNaturalist · Open on iNaturalist". "Show imported sightings" lists just that import (a "From this import" filter). |

**On your own export** (read where it is; nothing was saved): of 201 rows, 192 can be imported and 9 have no date. **190 match the UK list automatically**: 187 by scientific name, 2 by English name (renamed species such as *Argynnis aglaja*, now *Speyeria aglaja*), and 1 through another of its names. Only *Apioideae* and *Sphecodogastra* need you to choose.

---

## 2. Decisions

| Decision | Why |
|---|---|
| **Plant and fungus "aggregates" count as species** (e.g. Bramble, *Rubus fruticosus* agg.) | Botanists record them as one species. Bird "aggregates" are really "A or B" pairs (Carrion/Hooded Crow), so those still don't count. Where an aggregate shares its exact name with a species (Daffodil), only the species counts, so nothing is counted twice. |
| A species with no English name takes its nominate variety's | e.g. *Amanita muscaria* has its English name "Fly Agaric" filed under var. *muscaria* in the UK list (57 species). |
| Time **as you entered it** on iNaturalist comes first | That's the clock you saw. If it can't be read, iNaturalist's UTC time is converted to UK time. |
| UK summer time is **worked out, not looked up** | Windows' Python has no time-zone data. The UK rule has been fixed since 1996, so writing it out (with tests) avoids a new download. |
| **Names are matched in this order:** your earlier choices → scientific name → other scientific names → English name (only if it means exactly one species) → you choose | Each step is safe: nothing is guessed. Names shared between kingdoms (*Prunella* is both the Dunnock's genus and Selfheal's) are resolved by iNaturalist's group. |
| A count is **not** invented | iNaturalist records presence, so imported sightings have no count ("present"). |
| **"Edited in WildLife" is recorded by the database itself** | A trigger marks an imported sighting as soon as one of its details really changes. A first version compared timestamps, and a test showed two changes in the same second slipped through. |
| **All internet access goes through one small module** | HTTPS only, three iNaturalist hosts only (redirects too), a size limit, a clear user agent, and only while online features are on. Downloads pause between photos to be polite to iNaturalist. |

---

## 3. Checks

- **Tests:** 371 automated tests (35 new), all passing. Every test row is invented; your real export was never copied into the project. The new tests cover:
  - reading exports: dates and UK times (including the clock-change hours), positions and obscured locations, quality grades, sound-only records, Excel re-saves, the `.zip`;
  - name matching: exact, subgenus, synonym, renamed species, plant against bird genus, remembered choices;
  - importing: categories, places, re-importing, updates, your edits kept, deleted records left deleted, Undo;
  - photos, using a fake internet: the API, the fallback to the export's links, a missing original size, the online switch, Undo into the recycle bin, reuse on re-import, and the host allow-list;
  - the import window.
- **Performance:** checking your 201-row export takes about 0.01 s; installing the bigger species list takes 8 s.
- **Packaged build:** smoke test passes; 571 MB (+1 MB for the bigger species list).
- **Visual checks:** the import window's three steps in light and dark, and the new icons.

---

## 4. Problems found and fixed

| Problem | Fix / lesson |
|---|---|
| "Edited here?" by comparing timestamps missed same-second edits | A database trigger now records real edits |
| A Daffodil "aggregate" with the same name as the species would have counted twice | Aggregates named like a species stay groups |
| UKSI files *Deraeocoris flavilinea* with its subgenus in brackets | The name without the subgenus is now indexed too, which also helps the species picker |
| Photo downloads announced every single photo, so an open page would redraw hundreds of times | Changes are announced in batches of 25 |
| "Purple Loosestrife" didn't match the boost list | UKSI writes it "Purple-loosestrife" |

---

## 5. Still to do

| Item | Where |
|---|---|
| ~~A test download of **your** photos from iNaturalist~~ | **Done 16 Oct 2026:** you downloaded all your photos in the app; it worked |
| General CSV import with column matching; export (CSV, JSON, Darwin Core, full archive); restore a backup inside the app; health check; blurring locations on export | Phase 11 part 2 |
| Import history (list of past imports) | Phase 11 part 2 |
| Iconic-group icons drawn by a designer | Phase 12 |
