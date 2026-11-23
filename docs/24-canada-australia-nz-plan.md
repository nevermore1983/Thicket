# Species packs for Canada, Australia and New Zealand: plan

Status: **approved** (23 Nov 2026): Canada's dates month-first; French searchable in Québec and New Brunswick. Follows docs/16-regions-plan.md (the US) and docs/23-europe-packs-plan.md (Europe), and reuses everything they built.

## 1. What you get

- **Canada:** one pack per province and territory (13).
- **Australia:** one pack per state and territory (8).
- **New Zealand:** one pack for the whole country, its outlying islands included.

That's 22 new packs. Each works like a US state's: the species recorded there from GBIF, most-recorded suggested first, downloaded once from Settings › Region › **Add a region…** or the welcome screen.

## 2. How the areas are cut

The same way as the US states: GBIF's occurrence search, filtered by country and by GADM's first-level area (`gadmLevel1Gid`). Checked against GBIF on 23 Nov 2026:

| Country | GBIF areas | Records |
|---|---|---|
| Canada | 13: Ontario, Québec, British Columbia, Alberta, Nova Scotia, Manitoba, Saskatchewan, New Brunswick, Newfoundland and Labrador, Yukon, Prince Edward Island, Northwest Territories, Nunavut | 214 million |
| Australia | 8 states and territories, plus Jervis Bay Territory (0.4 million records), Ashmore and Cartier Islands and the Coral Sea Islands (a few thousand) | 263 million |
| New Zealand | 19 regions (not used: one pack) | 24 million |

- **Jervis Bay Territory** is a small coastal area surrounded by New South Wales, so its records go into the **New South Wales** pack.
- **Ashmore and Cartier and the Coral Sea Islands** are remote reefs with no residents, so they're left out.
- **Codes:**
  - Canada: `ca-on`, `ca-qc`, `ca-bc`… (Canada Post's two-letter codes).
  - Australia: `au-nsw`, `au-vic`, `au-qld`, `au-wa`, `au-sa`, `au-tas`, `au-nt`, `au-act`.
  - New Zealand: `nz`.
  - There's no clash with California, which is `us-ca`.

## 3. Names

| | Shown name | Searchable too |
|---|---|---|
| Canada | North American names, as in the US packs (Clements/eBird for birds: "Gray Jay" is "Canada Jay") | French, in Québec and New Brunswick (VASCAN has French names for Canada's plants; GBIF has them for most birds) |
| Australia | IOC bird names, which Australian birders use (BirdLife Australia follows them closely); Australian names preferred for everything else | — |
| New Zealand | IOC bird names, New Zealand names preferred | Māori names ("tūī", "pūkeko", "kererū"), as far as GBIF has them |

- The UK list's name isn't put first here, as it is in Europe. An Australian Blackbird is "Common Blackbird", as Australians call it, while the UK region still shows "Blackbird". Names are per region, so both stay right.
- The trial (step 2) checks real name quality before anything is published. The question is how many Australian insects and plants have English names in GBIF. As in the US and Europe, most insects and fungi won't have one anywhere.

## 4. In the app

- **Region groups:** Canada, Australia and New Zealand join the United States and Europe in **Add a region…**, each under its own heading, with search as now.
- **Welcome screen:** "Where do you record?" offers the United Kingdom, Elsewhere in Europe, the United States, **Canada**, **Australia** and **New Zealand**, each with its own list where there's a choice.
- **Map:** opens on the province or state. As everywhere outside the UK, positions show as coordinates, with no grid squares.
- **Dates in spreadsheets:**
  - Australia and New Zealand write them day-first, as in the UK.
  - Canada uses both orders, so it defaults to month-first, as in the US. The switch on the import page changes it for one file.
  - eBird and iNaturalist exports use unambiguous dates, so they aren't affected.
- **Time:** the PC's own time zone, as for the US. Nothing new.
- **Linking:** as before, packs only add species. A species you already have (UK list, another pack, your own) stays one species, including the synonym linking from 1.6.1.

## 5. Publishing, and older versions

- No new list is needed. 1.6.1 reads `manifest-3.json` and leaves out any region it doesn't know, so the new packs can go into the same list.
- 1.6.1 and older versions carry on exactly as now, and an update to 1.7.0 shows the new regions.
- `manifest-2.json` (1.6.0) and `manifest.json` (US only) stay as they are. In the builder, `AFTER_1_6_0` grows into a general "not in manifest-2" rule.

## 6. Steps

1. **App:** the regions (codes, names, map starts, languages, date order), the groups in "Add a region…" and the welcome screen, and tests.
2. **Builder:**
   - Canada's provinces and Australia's states from GBIF's GADM areas, with Jervis Bay joining New South Wales and New Zealand by country.
   - The name styles for each.
   - Trial build of Ontario, Québec, New South Wales, Tasmania and New Zealand, then review the names with you.
3. **Publish:** push and a `packs-2026-11-3` tag (asks you first). Then check that the real list installs.
4. **Release Thicket 1.7.0:** changelog, website (home, features, Help, privacy) and README, then the tag (asks you first).

## 7. Not in this plan

- Smaller areas within provinces or states, and other countries (a "rest of the world, one pack per country" plan can follow).
- Showing local names instead of English ones (a possible setting later).

## Step 1 results (23 Nov 2026)

- `domain/regions.py`: the groups Canada, Australia and New Zealand (`GROUPS` lists every group in order), 13 provinces and territories (`ca-on`…, `PROVINCE_CODES`), 8 states and territories (`au-nsw`…, `AU_STATE_CODES`) and `nz`. Québec and New Brunswick carry French, and New Zealand Māori (`mi`). `month_first` is true for the US and Canada.
- **"Add a region…"** arranges the list by `GROUPS`, under five headings.
- **The welcome screen's** choices come from one table (`REGION_CHOICES`). Each list shows under its choice once chosen, so the page stays short with six choices.
- **Settings › Region** describes the packs as covering Europe, North America, Australia and New Zealand.
- 699 tests (4 new). Screenshots: `scripts/screenshot.py --pages welcome-region add-region` now shows Canada.
