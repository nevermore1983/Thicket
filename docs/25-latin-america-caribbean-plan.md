# Species packs for Latin America and the Caribbean: plan

Status: **approved** (23 Nov 2026): IOC bird names in British spelling; all 52 countries and territories. This is the first stage of "the rest of the world, one pack per country". It follows docs/23-europe-packs-plan.md (Europe, cut by country the same way) and docs/24-canada-australia-nz-plan.md, and reuses what they built.

## 1. What you get

One pack per country or territory: **52 in all**.

| Area | Countries and territories |
|---|---|
| Mexico and Central America (8) | Mexico, Guatemala, Belize, El Salvador, Honduras, Nicaragua, Costa Rica, Panama |
| South America (15) | Colombia, Venezuela, Ecuador, Peru, Bolivia, Brazil, Paraguay, Uruguay, Argentina, Chile, Guyana, Suriname, French Guiana, the Falkland Islands, South Georgia and the South Sandwich Islands |
| The Caribbean (29) | Cuba, Jamaica, Haiti, the Dominican Republic, Puerto Rico, the Bahamas, the Turks and Caicos Islands, the Cayman Islands, the US and British Virgin Islands, Anguilla, Montserrat, Saint Kitts and Nevis, Antigua and Barbuda, Dominica, Saint Lucia, Saint Vincent and the Grenadines, Barbados, Grenada, Trinidad and Tobago, Aruba, Curaçao, Sint Maarten, the Caribbean Netherlands (Bonaire, Sint Eustatius and Saba), Guadeloupe, Martinique, Saint Martin, Saint Barthélemy, and Bermuda (in the Atlantic, but usually listed with the Caribbean) |

Each works like a European country's pack: the species recorded there from GBIF, most-recorded suggested first, downloaded once from Settings › Region › **Add a region…** or the welcome screen.

## 2. How the areas are cut

By GBIF's country code, exactly as for Europe. No new area matching is needed. GBIF files the French, Dutch, British and US territories under their own codes, not under France, the Netherlands, the UK or the US, so each gets its own pack and the existing packs don't change.

Records in GBIF (23 Nov 2026):
- The biggest are Brazil (44 million), Mexico (35 million), Costa Rica (34 million) and Colombia (34 million).
- The smallest is Saint Barthélemy, with 32,000.

Packs for the megadiverse countries will be the largest Thicket has. France's is 61,000 species at 4 MB, and Brazil's or Colombia's may be 80,000–100,000 species at 5–6 MB. That's still a few seconds to download and install. The trial (step 2) measures it.

**Codes:** each region's code is its own two-letter code in lower case (`mx`, `br`, `cr`, `pr`, `gf`…), as in Europe. None clashes with a code Thicket already uses.

## 3. Names

**Shown name: English.** Most visiting birders come from the US or the UK, and the two bird lists mostly agree in the Neotropics. Where they differ, one style has to win. **Chosen: the IOC list.**
- **The IOC list, spelt the British way** ("Grey-headed Kite"), as in Australia and New Zealand and in keeping with Thicket's British English. eBird's names stay searchable.
- (Not chosen: eBird's Clements names, spelt the American way, as in the US and Canada.)

For everything else, GBIF's English names, as now. Tropical insects and plants mostly won't have one, but birds, mammals, reptiles, amphibians and butterflies mostly will. The UK list's name is used for non-birds it has, as in Australia (weeds and pests that came from Britain).

**Searchable too (local names):**

| Language | Where |
|---|---|
| Spanish | every Spanish-speaking country, and Puerto Rico |
| Portuguese | Brazil |
| French | Haiti, French Guiana, Guadeloupe, Martinique, Saint Martin, Saint Barthélemy |
| Dutch | Suriname, Aruba, Curaçao, Sint Maarten, the Caribbean Netherlands |

GBIF has Spanish and Portuguese names for most birds and many other animals and plants, so typing "colibrí" or "beija-flor" will find hummingbirds.

## 4. In the app

- **"Add a region…":** a new heading, **Latin America and the Caribbean**, with all 52, searchable as now.
- **Welcome screen:** "Where do you record?" gains a seventh choice, **Latin America and the Caribbean**, with its country list appearing once chosen, as Europe's does. When Africa and Asia follow, the choices will be replaced by a single "find your country" search, since that list would grow too long (a later plan).
- **Map:** opens on the country. As everywhere outside the UK, positions show as coordinates, with no grid squares.
- **Dates in spreadsheets:**
  - **Day-first** everywhere in the region.
  - **Month-first** only in Puerto Rico and the US Virgin Islands, which follow the US.
  - The switch on the import page changes it for one file, and eBird and iNaturalist exports aren't affected.
- **Linking:** as before, packs only add species. A species you already have, from the UK list, another pack or your own, stays one species. That includes the synonym linking (1.6.1) and the regional splits (1.7.0).

## 5. Publishing, and older versions

- The new packs go into `manifest-3.json`. 1.6.1 and 1.7.0 leave out regions they don't know, so they carry on exactly as now, and an update to 1.8.0 shows the new regions.
- `manifest-2.json` (1.6.0) and `manifest.json` (US only) stay as they are. `in_1_6_0()` already leaves the new regions out.
- The packs workflow builds all 177 packs in one run. It took about an hour for 125, and Brazil and Mexico will add to that. The trial checks it stays within GitHub's six-hour limit, which it should easily.

## 6. Steps

1. **App:** the regions (codes, names, map starts, languages, date order), the new heading in "Add a region…" and the welcome-screen choice, and tests.
2. **Builder:**
   - The region's countries from the shared list.
   - The name style.
   - A trial build of Brazil (the biggest), Costa Rica, Mexico, Puerto Rico and Martinique, then a review of the names with you.
3. **Publish:** push and a `packs-2026-11-5` tag (asks you first), then check that the real list installs.
4. **Release Thicket 1.8.0:** changelog, website (home, features, Help, privacy) and README, then the tag (asks you first).

## 7. Not in this plan

- Areas smaller than a country: Brazil's or Mexico's states. These could come later, US-style, if people ask.
- Africa, Asia and the Middle East (the next stages), and the "find your country" welcome screen they'll need.
- Showing local names instead of English ones (a possible setting later).

## Step 1 results (23 Nov 2026)

- **`domain/regions.py`:**
  - The group `LATIN_AMERICA` ("Latin America and the Caribbean"), last in `GROUPS`.
  - 52 countries and territories (`_LATIN_AMERICA`, `LATIN_AMERICA_CODES`), each coded by its own two-letter code (`br`, `cr`, `pr`…) with its map start and languages: Spanish, Portuguese (Brazil), French or Dutch.
  - The map for the Caribbean Netherlands opens on Bonaire.
  - `month_first` is also true for Puerto Rico and the US Virgin Islands (`MONTH_FIRST_TOO`).
- **The welcome screen** has a seventh choice, "Latin America and the Caribbean: a country's or territory's species from GBIF", whose list appears once chosen.
- **"Add a region…"** shows the new heading last. Its intro and Settings › Region mention the region.
- **Tests:** 710 (3 new). Screenshots: `scripts/screenshot.py --pages welcome-region add-region` now shows Costa Rica.

## Step 2 results (23 Nov 2026)

**Builder:**
- `countries(group)` makes any group's country packs by GBIF's country code: Europe's as before, and Latin America's (`latin_american_countries()`).
- `--regions` tells a bare code's group from the shared region list, not from how its code starts, so `cr` and `fr` both work. The group name is `latin-america`.
- `LATIN_AMERICA_NAMES`: IOC bird names spelt the British way. British names only break ties, and the UK list's name is used for everything but birds, as in Australia.

**Trial** (all pass the checker):

| Pack | Species | Size | English name | Local names | Installs in |
|---|---|---|---|---|---|
| Brazil | 87,254 | 4.7 MB | 15% | 12% Portuguese | 16.8 s |
| Mexico | 71,594 | 4.0 MB | 23% | 10% Spanish | 14.7 s |
| Costa Rica | 37,915 | 2.0 MB | 18% | 9% Spanish | 7.7 s |
| Puerto Rico | 10,021 | 0.7 MB | 39% | 16% Spanish | 3.5 s |
| Martinique | 6,022 | 0.4 MB | 43% | 14% French | 2.4 s |

- **Birds are excellent.**
  - Brazil has English names for 1,863 of 1,875 birds and Portuguese names for 1,706 ("Bem-te-vi", "João-de-barro", "Sabiá-laranjeira").
  - Costa Rica has 1,015 of 1,019, Puerto Rico 335 of 336, and Martinique all 177, with Spanish or French names for nearly all.
  - British spelling: "Blue-grey Tanager", "Grey Kingbird".
- **Mammals:** Mexico names 591 of 604 ("White-nosed Coati", also found as "pizote").
- **Gaps:** as everywhere, most tropical insects and plants have no English name. Costa Rica names 1,221 of 17,007 insects. Search by scientific name always works.
- **Search:** "bem-te-vi" finds Great Kiskadee; "beija-flor" and "colibrí" find hummingbirds.
- **Brazil** is the biggest pack yet, and still installs in under 20 seconds with the progress bar.

## Step 3 (23 Nov 2026)

Before publishing:
- **The packs workflow's time limit** goes from 2 to 4 hours. The last run took an hour for 125 packs, and the trial showed Latin America needs about 8,000 more name lookups from GBIF.
- **Anguilla** has only 421 species with enough records, under the checker's 500 minimum for a sensible pack. Like Monaco and the Vatican, it gets a lower floor (`TINY`), with Sint Maarten's (711) given some headroom too. Every other territory has at least 800 (Montserrat).

## Step 3 results (24 Nov 2026)

- **The first run failed** after 2 h 19 min: GitHub's build machine lost contact ("the hosted runner lost communication with the server"), with no error from the builder. Memory wasn't the cause: reading 500,000 species and all 44 languages from the Backbone peaks at 1.2 GB of the runner's 16 GB. **Re-running the same job succeeded**, so nothing changed in the code.
- **Published** (`packs-2026-11-5`):
  - `manifest-3.json` has 177 packs, 52 of them Latin American and Caribbean.
  - `manifest-2.json` (97) and `manifest.json` (51) are unchanged apart from the new release's links.
  - The largest pack is Brazil (87,529 species, 4.7 MB), then Mexico (71,595) and Colombia (47,039). The smallest is Anguilla (421).
- **Installed from the real release with the app's own code**, into a fresh library:

| Pack | Species | Installs in |
|---|---|---|
| Brazil | 87,529 | 21 s |
| Costa Rica | 37,915 | 12 s |
| Puerto Rico | 10,021 | 7 s |
| Anguilla | 421 | 4 s |

- **Search works:** "bem-te-vi" finds Great Kiskadee, "beija-flor" and "colibrí" find hummingbirds, "pizote" finds White-nosed Coati, and "coquí" finds Common Coqui. Names use British spelling, e.g. Blue-grey Tanager and Grey Kingbird.
- **Packs link up:** Great Kiskadee, in both Brazil's and Puerto Rico's packs, is still one species.

## Step 4 (24 Nov 2026)

Thicket 1.8.0:
- **Changelog:** the new regions, names, local-language search, the biggest packs, and dates and the map.
- **Website:** the home and Features pages are retitled "The UK, Europe, the Americas and Australasia". Help's "The first start" and "Changing region" and the privacy page name the new region.
- **README** and the version number are updated.
