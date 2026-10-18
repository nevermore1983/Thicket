# WildLife — regions and species packs (plan)

**Date:** 18 October 2026
**Status:** Plan for your approval. No code yet.
**Target:** version 1.1.0

Friends in the USA want to test WildLife. They need to pick where they record and get a species list for that area. Today WildLife is UK-only in several ways. This plan makes "where you record" a setting, and adds downloadable **species packs**: one per US state, alongside the UK list already built in.

**Your choices (18 Oct):**
- one pack per state;
- downloaded inside the app;
- species plus the basics follow the region;
- this plan first, then building.

---

## 1. What you'll see

- **First start:** "Where do you record?" offers **United Kingdom** (as now, nothing to download) or **United States**, then a state. Choosing a state downloads that state's pack (a few MB) and installs it. The pack is checked against its published checksum first.
- **Settings › Region:** change your region or add another state's pack (for a trip, say). Each pack shows its date and number of species.
- **Species suggestions** come from the chosen region, most-recorded first, using that region's common names. Typing "robin" in Ohio suggests American Robin first; in the UK, Robin.
- **The map** opens on your region.
- **Locations:**
  - In the UK, grid references work as now.
  - Elsewhere, positions show as latitude/longitude, and the map's grid-square mode (built on the British National Grid) is hidden.
- **Times** from iNaturalist imports and phone photo names are converted with your PC's own time zone, instead of UK clock rules.
- **Spreadsheet imports** read dates month-first (03/05 is 5 March) in the US, day-first in the UK. The import page already warns when a column only makes sense one way, and gets a switch to change it.
- **Exports** say where each species name came from: the UK Species Inventory, or GBIF.

**Not changing in 1.1.0:**
- °C and metres stay;
- spelling stays British English;
- the UK pack stays built in.

Packs only ever **add** species. Your sightings, and species already in your list, are never removed or changed.

---

## 2. Where the species data comes from

**[GBIF](https://www.gbif.org/)**, the Global Biodiversity Information Facility: the world's open network of biodiversity records. I tested its public API on 18 Oct.
- **Which species, how often:** for each state, GBIF lists every species recorded there with its number of records. In California that's over 60,000 species, returned in a few seconds per 20,000.
  - Species with very few records (often misidentifications, garden plants or escapes) are left out. The cut-off will be set from real numbers, likely 5+ records.
  - The number of records becomes the suggestion order, as the UK list's recording frequency does now.
- **Names:** scientific names, family tree and English common names come from GBIF's master species list (the GBIF Backbone Taxonomy). It's a ~1 GB file, used only when *building* packs, never by the app.
- **Categories:** WildLife sorts species into its 8 categories by the Latin family, order and class names. GBIF uses the same names, so no new rules should be needed. A test will check that each pack's species land in the right categories, not "Other".
- **Licences:**
  - GBIF's species list is CC BY 4.0, and its records are CC0, CC BY or CC BY-NC.
  - Packs use only names and counts, never the records themselves, and cite GBIF as its data-use agreement asks.
  - The citation goes in each pack, in the third-party notices and in exports.
- **Considered and not chosen:**
  - **ITIS** (the US government list): public domain, but its "where does it live" data is patchy, and it can't rank by how common a species is.
  - **iNaturalist's taxonomy export:** licence unclear, and its API discourages bulk use.

---

## 3. How packs are built and delivered

- **Building:** `scripts/build_species_packs.py` runs on GitHub, like the app's releases. A separate workflow starts when a `packs-YYYY-MM` tag is pushed. It:
  1. downloads the GBIF Backbone (checksum recorded, cached between runs);
  2. asks GBIF's API for each state's species and counts;
  3. writes one pack per state, in the same record format as the UK list (so the existing installer code is reused);
  4. publishes the 51 packs (50 states and DC) plus a `manifest.json` (name, date, species count, size, SHA-256 of each) as a GitHub release.
- **Updating:** run it again whenever you like. GBIF gains records every day, so a yearly refresh is plenty.
- **Delivery:**
  - The app knows the manifest's address.
  - It downloads a pack only while "Allow online features" is on, and only from `github.com` and `release-assets.githubusercontent.com` (added to the approved list).
  - It installs a pack only if its SHA-256 matches the manifest.
  - Without internet, the region choice explains that a pack needs a connection once, and the UK list stays available.

---

## 4. Changes inside WildLife

| Area | Change |
|---|---|
| Database (migration 7) | A pack's species keys (`gbif:2490384`) are stored separately from UK keys. **One species, one entry:** when a pack has a species already in the list (same accepted scientific name, such as Red Fox or House Sparrow), the pack links to it instead of adding a second copy. Your life list then never counts a species twice. Each region keeps its own common names and suggestion order. |
| Region setting | `region` in settings: `uk` or `us-<state>`. Migrating sets `uk` for existing libraries, so nothing changes for you. |
| Species search | Ranks by the region's record counts and shows the region's common name first. The other names still match ("Starling" finds European Starling). |
| First run and Settings | The region choice; download with progress, checksum check and install (in the background, cancellable). |
| Map | Opens on the region's centre. The grid-square mode is shown only in the UK. |
| Locations | UK: grid references. Elsewhere: latitude/longitude everywhere positions are shown or typed. Typing coordinates already works. |
| Times | The UK clock rules (`dates.uk_local`) are replaced by the PC's own time zone. In the UK that gives the same answers. |
| Spreadsheets | Date order follows the region, with a switch on the import page. |
| Exports | Darwin Core `nameAccordingTo` / `taxonID` per species source (UKSI or GBIF). |
| Notices | GBIF citation added. |

---

## 5. Steps (each with tests, each reviewed by you)

1. **Database and installing a pack:** migration 7, linking instead of duplicating, region names and order. Tested with a tiny made-up pack, including a species shared with the UK list.
2. **Pack builder:** the script and workflow. First built locally for 2–3 states to check numbers, sizes and name quality (are bird names the usual American ones?), then the full 51 on GitHub.
3. **Region choice and download:** first run, Settings, the approved addresses, checksum verification, and an offline message. Tested against a fake server, never the real internet.
4. **Region-aware basics:** suggestions, map start, latitude/longitude display, hiding grid squares, PC time zone, spreadsheet date order, exports.
5. **Release 1.1.0:** changelog, docs, the GitHub release. Then your friends install it and choose their state.

**Rough size:** a phase like Phase 11, done in parts, each ending with a working app.

---

## 6. Risks and how they're handled

| Risk | Handling |
|---|---|
| GBIF common names: some species have several English names, or none | Prefer well-known sources (for birds, the names US birders use), then the most common one. Check samples in step 2. With no English name, the scientific name is shown, as for UK species without one. |
| GBIF's species numbers come from its current Backbone. If GBIF changes its Backbone, numbers could shift | Keys are stored per pack and matched by name on install. A key the Backbone file doesn't know is looked up through GBIF's API while building. |
| Big packs (California, Texas) | The cut-off keeps each pack to tens of thousands of species: a few MB, about the size of the UK list. The search indexes already handle 100,000+. |
| A tampered or broken download | The SHA-256 must match the manifest, and both come from WildLife's own GitHub releases. |
| Friends see "Windows protected your PC" | Explained on the download page (More info › Run anyway). |
| Mixed regions (a trip, or moving house) | Packs add to one list, so a sighting's species stays valid whichever region is chosen later. |

---

## 7. Questions for later (not needed now)

- °F and miles for US users (you chose "basics" for now).
- Other countries: the same builder works for any country or province GBIF covers.
- Removing a pack you no longer need. Not in 1.1.0: species your sightings use must stay.
