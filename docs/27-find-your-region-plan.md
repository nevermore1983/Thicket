# 27. Find your region: one search on the welcome screen

**Status:** plan, for approval (25 Nov 2026). Target: Thicket 1.10.0, before the Asia packs.

## 1. Why

Thicket now offers 237 species packs, and Asia will add many more.

**The welcome screen today** ("Where do you record?") has 8 choices: the UK and 7 parts of the world. Choosing one shows a dropdown of its regions, and you scroll it to find yours. Asia would make 9 choices, then 10, and you have to know which group a place is in. Is Cyprus in Europe? Is Réunion in Africa or with France?

**Settings › Add a region** already has a "type to find" box. It needs the exact letters, though:
- "Reunion" doesn't find Réunion, and "Ivory Coast" finds nothing.
- It looks at the whole line, so typing "mb" (as in MB, the size) matches every region.

## 2. What you chose

- **The welcome has two choices.** "United Kingdom" is still the default, and nothing is downloaded. "Somewhere else" shows one search box over a single list of every region under its headings, like Add a region. Adding Asia later adds no new buttons.
- **The search ignores accents and knows other names.**
  - "Reunion" finds Réunion, "Curacao" finds Curaçao, and "Quebec" finds Quebec whichever way it's typed.
  - "Ivory Coast" finds Côte d'Ivoire, and "Swaziland" finds Eswatini.
  - Short codes are **not** matched: "CA" would show Canada, California and many more.
- **Thicket suggests your country from Windows' region setting.** It's read on your computer and never sent anywhere. If Windows says Kenya, choosing "Somewhere else" opens the list with Kenya chosen and in view. The UK stays the choice until you change it.

## 3. How the search matches

Both what you type and each region's names are "folded" the same way before they're compared:
- Capitals don't matter, and accents are dropped (é → e, ç → c, ã → a).
- Apostrophes and full stops go ("Cote dIvoire", "St. Lucia"). Hyphens become spaces ("Guinea Bissau"), and "&" becomes "and".
- "St" and "St." count as "Saint" ("St Kitts", "St Helena", "St Barthelemy").

A region is shown if what you type appears anywhere in its name, or in one of its other names. Only the names are searched, not the species count or size.

**Other names** (a short hand-made list, in `domain/regions.py`):

| Typed | Finds |
|---|---|
| Ivory Coast | Côte d'Ivoire |
| Swaziland | Eswatini |
| Cape Verde | Cabo Verde |
| DR Congo, DRC, Congo-Kinshasa, Zaire | Democratic Republic of the Congo |
| Congo-Brazzaville | Republic of the Congo |
| Czech Republic | Czechia |
| Holland | Netherlands |
| Türkiye | Turkey |
| Holy See | Vatican City |
| Bonaire, Sint Eustatius, Saba | Caribbean Netherlands |
| US Virgin Islands, USVI | United States Virgin Islands |
| BVI | British Virgin Islands |
| St Barts, St Barths | Saint Barthélemy |
| Washington DC | District of Columbia |
| ACT | Australian Capital Territory |
| NSW | New South Wales |
| PEI | Prince Edward Island |

These are the everyday names and abbreviations people really use. Plain codes (ZA, TX) are still not matched.

**The UK:** typing "England", "Scotland", "Wales", "Northern Ireland", "Britain" or "UK" shows a short note: "The UK's species list is built in: it's the first choice above." In Add a region, the note says "…choose it in Settings › Region" instead.

**Nothing found:** the note says "No region called “…”. Thicket has packs for Europe, North America, Latin America and the Caribbean, Africa, Australia and New Zealand."

## 4. Windows' region setting

Thicket asks Windows for the country set in **Settings › Time & language › Language & region › Country or region**. It uses `GetUserDefaultGeoName`, which answers instantly, without going online. On this computer it answers "GB".

What happens depends on the answer:

| Windows says | When you choose "Somewhere else" |
|---|---|
| GB, or a country without a pack (India, say), or nothing | The list opens at the top, with nothing chosen |
| A country with one pack (Kenya, France, Brazil…) | That region is chosen and scrolled into view |
| The US, Canada, Australia or Russia (several packs) | The list opens at its heading, with nothing chosen: you pick your state, province or part |

- Only the welcome screen uses the suggestion. Add a region doesn't need one.
- The privacy page will say Thicket reads this setting at the first start, and that it stays on your computer.
- Tests never read the real setting; they hand in a made-up answer.

## 5. In the app

**One shared region list.** A new `RegionPicker` widget (in `ui/regions.py`) holds the search box and the list under its headings. Both the welcome and Add a region use it, so they behave alike and are tested once.

**The welcome's "Where do you record?" page:**
- "United Kingdom" stays first and chosen.
- "Somewhere else: its species from GBIF (downloaded once)" comes second. Choosing it fetches the list of packs, as choosing a group does today. Choosing the UK still never goes online.
- The picker appears under "Somewhere else" once that's chosen, with the search box ready to type in.
- **Next** with nothing chosen says "Choose your region first" and stays on the page, as it does today.

**Add a region:** looks the same as now, with the better matching and the notes.

## 6. Steps

1. **Matching.** Add folding, the other names and the UK note in `domain/regions.py`, and use them in Add a region's search. Tests for each row of the table in section 3.
2. **The shared list.** Add `RegionPicker`; Add a region uses it. It should look the same, and the existing tests still pass.
3. **The welcome.** Two choices plus the picker, and Windows' suggestion. Update the welcome tests and the screenshot (`scripts/screenshot.py`).
4. **Words and release.** Update the help page's "The first start", the privacy page (the Windows setting), README, `docs/13-manual-tests.md` and the changelog. Release Thicket 1.10.0, and ask before pushing.

As before, you approve the end of each step.

## 7. Not in this plan

- The Asia and Middle East packs: their own plan next.
- Finding a region by clicking a map.
- Suggesting a region from your sightings or photos' locations.

## Step 1 results (25 Nov 2026)

- **`domain/regions.py`:**
  - `fold()` drops capitals, accents, apostrophes and full stops, turns hyphens into spaces and "&" into "and", and treats "St " as "Saint". The "St" rule needs the space after it, so typing "st" on the way to "Sta…" still finds Estonia.
  - `OTHER_NAMES` holds the table in section 3.
  - `region_matches()` checks a region's name and other names. `means_the_uk()` is for the UK note.
  - The UK note matches only the start of a UK name. "Wales" gets it, though New South Wales is found too, but "Ireland" doesn't.
- **Add a region:** searches names only, with the matching above. The line under the list says when nothing is found, or that the UK is built in, and goes back to "N regions. Choose one…" when the search is cleared.
- **Tests:** 54 in `tests/unit/test_region_search.py`, plus one in the Add a region dialog. 771 pass.

## Step 2 results (25 Nov 2026)

- **`RegionPicker`** (`ui/regions.py`) is the search box and the list under its headings, as one widget. It tells its window three things:
  - `changed`: the region chosen changed, or the search hid it.
  - `activated`: a region was double-clicked. A heading does nothing.
  - `noted`: what to say about the search. The window decides where to show it.

  Each window also says how the UK note should end ("choose it in Settings › Region" here; "it's the first choice above" on the welcome).
- **Add a region** is now built from a `RegionPicker`. It looks and works as before, and all its old tests pass unchanged. The search box also gets a small ✕ to clear it.
- **Tests:** one new test of the picker on its own. 772 pass.
