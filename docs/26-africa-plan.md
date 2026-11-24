# Species packs for Africa: plan

Status: **approved** (24 Nov 2026). The choices: all 60 countries and territories, IOC bird names in British spelling, and Africa as an eighth welcome-screen choice. This is the second stage of "the rest of the world, one pack per country", after docs/25-latin-america-caribbean-plan.md, and it reuses what that built.

## 1. What you get

One pack per country or territory: **60 in all**.

| Area | Countries and territories |
|---|---|
| North Africa (7) | Morocco, Algeria, Tunisia, Libya, Egypt, Sudan, Western Sahara |
| West Africa (16) | Mauritania, Senegal, the Gambia, Guinea-Bissau, Guinea, Sierra Leone, Liberia, Côte d'Ivoire, Ghana, Togo, Benin, Nigeria, Mali, Burkina Faso, Niger, Cabo Verde |
| Central Africa (9) | Cameroon, Chad, the Central African Republic, Equatorial Guinea, Gabon, the Republic of the Congo, the Democratic Republic of the Congo, São Tomé and Príncipe, Angola |
| East Africa (12) | Ethiopia, Eritrea, Djibouti, Somalia, South Sudan, Kenya, Uganda, Rwanda, Burundi, Tanzania, Malawi, Mozambique |
| Southern Africa (7) | South Africa, Namibia, Botswana, Zimbabwe, Zambia, Lesotho, Eswatini |
| Islands (9) | Madagascar, Mauritius, Réunion, Mayotte, the Comoros, the Seychelles, Saint Helena (with Ascension and Tristan da Cunha), the British Indian Ocean Territory, the French Southern Territories |

Each pack works like a Latin American one: the species recorded there from GBIF, most-recorded suggested first. You download it once, from Settings › Region › **Add a region…** or from the welcome screen.

**Left out:**
- **Bouvet Island:** uninhabited and sub-Antarctic, with only 75 species.
- **The Canary Islands, Madeira, Ceuta and Melilla:** they're already in Spain's and Portugal's packs, because GBIF files them under those countries.

## 2. How the areas are cut

The areas are cut by GBIF's country code, exactly as for Europe and Latin America. Every place in the table has its own code in GBIF, so each gets its own pack. Each place is named as GBIF and the international standard (ISO 3166) name it.

Species with at least 5 records (GBIF, 24 Nov 2026):

| | Countries | Species |
|---|---|---|
| Largest | South Africa | 51,752 |
| | Madagascar | 22,702 |
| | Tanzania | 20,101 |
| | DR Congo | 17,946 |
| | Kenya | 16,088 |
| Smallest | Chagos (British Indian Ocean Territory) | 1,051 |
| | South Sudan | 897 |
| | Djibouti | 720 |

Pack sizes:
- **South Africa's pack** will be about 3 MB, a little smaller than Mexico's.
- **Most packs** are 0.2–1 MB.

There are far fewer records than in Latin America, so packs are smaller, and fewer insects and plants will make the 5-record cut. Birds, mammals, reptiles and the better-known plants are well recorded almost everywhere.

**Codes:** each region's code is its own two-letter code in lower case (`za`, `ke`, `mg`, `re`…). None clashes with a code Thicket already uses (checked).

## 3. Names

**Shown name: English.**
- **Birds** have the IOC names, spelt the British way ("Grey Go-away-bird"), as in Latin America, Australia and New Zealand. Most African field guides use them, and South Africa's own (Roberts) names are very close. eBird's names stay searchable.
- **Everything else** has GBIF's English names, as now. The UK list's name is used for non-birds it has.

**Searchable too (local names).** These are the languages GBIF's Backbone has enough names in:

| Language | Names in GBIF | Where |
|---|---|---|
| French | 68,000 | the French-speaking countries, Madagascar, Réunion, Mayotte, the Comoros, the Seychelles, Mauritius, the French Southern Territories, and Morocco, Algeria and Tunisia |
| Portuguese | 48,000 | Angola, Mozambique, Guinea-Bissau, Cabo Verde, São Tomé and Príncipe |
| Spanish | 71,000 | Equatorial Guinea |
| Arabic | 5,800 | North Africa, Sudan, Mauritania, Chad, Djibouti, Somalia, the Comoros |
| Afrikaans | 5,000 | South Africa, Namibia |
| Malagasy | 3,700 | Madagascar |
| Swahili | 1,300 | Kenya, Tanzania, Uganda, DR Congo |
| Kinyarwanda | 1,200 | Rwanda |
| Wolof | 800 | Senegal, the Gambia |
| Somali | 560 | Somalia |
| Chichewa | 420 | Malawi, Zambia |
| Lingala | 380 | DR Congo, the Republic of the Congo |
| Hausa | 320 | Nigeria, Niger |

GBIF has too few names to be worth adding in Amharic, Zulu, Xhosa, Shona, Yoruba, Igbo, Tigrinya or Oromo (under 200 each). They can be added later if GBIF gains them.

**Arabic is the first right-to-left script in a pack.** Step 2 checks that it shows and searches properly.

## 4. In the app

- **"Add a region…":** a new heading, **Africa**, with all 60 places, searchable as now.
- **Welcome screen:** "Where do you record?" gains an eighth choice, **Africa**, whose list appears once it's chosen, as with Latin America.
  - The "find your country" search that will replace these choices gets its own small plan before Asia, which would make a ninth choice.
- **Map:** opens on the country. Positions show as coordinates, with no grid squares.
- **Dates in spreadsheets:** read day-first everywhere in Africa. The switch on the import page changes it for one file.
- **Linking:** as before, packs only add species. A species you already have stays one species.

## 5. Publishing, and the packs run

- The new packs go into `manifest-3.json`. Versions 1.6.1 to 1.8.0 leave out regions they don't know, so they carry on exactly as now. An update to 1.9.0 shows the new regions.
- `manifest-2.json` (for 1.6.0) and `manifest.json` (US only) stay as they are.
- **The packs run needs speeding up first.**
  - The last run took 3 hours of its 4-hour limit: 2 h 52 min building, up from about an hour before Latin America. Its first attempt died after 2 h 19 min when GitHub's build machine lost contact.
  - Most of the extra time is very likely the one-at-a-time calls to GBIF's species pages, which look up a name for each unnamed vertebrate and dragonfly. Latin America added thousands of these, and Africa will add more.
  - Step 3 measures where the time goes. It then makes the slow part faster, for example by asking GBIF a few pages at a time instead of one, or by keeping the answers between runs as the Backbone file is kept. GitHub's own limit of six hours stays well out of reach.

## 6. Steps

1. **App:**
   - the 60 regions (codes, names, map starts, languages, day-first dates);
   - the **Africa** heading in "Add a region…";
   - the welcome-screen choice;
   - tests.
2. **Builder:**
   - the region's countries from the shared list, and the name style;
   - a trial build of South Africa (the biggest), Madagascar, Kenya, Morocco (Arabic and French) and Réunion;
   - a review of the names with you.
3. **A faster packs run:** measure, then speed up the slow part, and check it with a trial.
4. **Publish:** push and a `packs-2026-11-6` tag (asking you first), then check that the real packs install.
5. **Release Thicket 1.9.0:** changelog, website (home, features, Help, privacy) and README, then the tag (asking you first).

## 7. Not in this plan

- Areas smaller than a country, such as South Africa's provinces. These could come later, US-style, if people ask.
- Asia and the Middle East (the next stage), and the "find your country" welcome screen.
- Bouvet Island and Antarctica.
- Showing local names instead of English ones (a possible setting later).

## Step 1 results (24 Nov 2026)

- **`domain/regions.py`:**
  - The group `AFRICA` ("Africa"), last in `GROUPS`.
  - 60 countries and territories (`_AFRICA`, `AFRICA_CODES`), each coded by its own two-letter code (`za`, `ke`, `re`…), with its map start and languages.
  - The maps of scattered islands open on the main one: Saint Helena, Mauritius, Mahé, Chagos and Kerguelen.
  - Dates are day-first throughout.
- **The welcome screen** has an eighth choice, "Africa: a country's or territory's species from GBIF". Its list appears once it's chosen, and the page still fits.
- **"Add a region…"** shows the Africa heading last. Its intro, and Settings › Region, mention Africa.
- **Tests:** 714, of which 3 are new. The screenshots (`scripts/screenshot.py --pages welcome-region add-region`) now show Kenya.

## Step 2 results (24 Nov 2026)

**Builder:**
- `african_countries()` makes Africa's packs by GBIF's country code, like Latin America's. The `--regions` group name is `africa`.
- `AFRICA_NAMES`: IOC bird names spelt the British way, as for Latin America.

**Trial** (all pass the checker):

| Pack | Species | Size | Birds with an English name | Local names | Installs in |
|---|---|---|---|---|---|
| South Africa | 51,139 | 2.7 MB | 971 of 974 | 5% (Afrikaans for 722 birds) | 9.8 s |
| Madagascar | 22,476 | 1.2 MB | 334 of 335 | 13% (Malagasy and French) | 4.7 s |
| Kenya | 15,944 | 1.0 MB | 1,238 of 1,243 | 2% (Swahili) | 4.1 s |
| Morocco | 10,767 | 0.8 MB | all 432 | 23% (Arabic and French) | 3.4 s |
| Réunion | 7,530 | 0.5 MB | all 117 | 18% (French) | 2.7 s |

**Birds:** all but a handful have English names, spelt the British way. None is left as "Gray".

**Mammals:** nearly all have English names too: 331 of 333 in South Africa and 447 of 455 in Kenya.

**Local names:**
- Afrikaans in South Africa: "Tortelduif" finds Ring-necked Dove, and "Hadeda" finds Hadada Ibis.
- Malagasy in Madagascar: "Varika" finds Brown Lemur.
- French in Madagascar and Réunion: "Foudi rouge" finds Red Fody.
- Swahili in Kenya: GBIF has it mostly for big mammals ("Punda Milia" finds Plains Zebra, "twiga" finds Giraffe), not birds.

**Arabic:**
- 168 Moroccan species have Arabic names. "العوسق" finds Kestrel, "حمام" finds Rock Dove, and "القبرة" finds the larks.
- In the species picker, "also “…”" shows an Arabic name right to left, with the quotation marks in the right places. No change was needed.

**Gaps:** as everywhere, most insects and plants have no English name. Search by scientific name always works.

**For step 3:** the 1,880 lookups on GBIF's species pages took 6.5 minutes. About 6 of those minutes were 3 calls that stalled for about 2 minutes each before being retried. Every call waits up to 3 minutes (`timeout=180` in `get_json`). The big species-count searches need that, but a species page answers in well under a second.
