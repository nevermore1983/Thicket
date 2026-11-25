# Species packs for Asia and the Middle East: plan

**Status:** plan, for approval (25 Nov 2026). Target: Thicket 1.11.0.

**Your choices:**
- all 48 countries and territories;
- two headings, "Middle East" and "Asia";
- IOC bird names in British spelling;
- Chinese, Japanese and Korean names searchable, with a fix for short searches.

This is the third stage of "the rest of the world, one pack per country", after Latin America (docs/25) and Africa (docs/26). It reuses what they built. The welcome's search (docs/27) means Asia needs no new buttons.

## 1. What you get

One pack per country or territory: **48 in all**.

| Heading | Area | Countries and territories |
|---|---|---|
| Middle East (14) | | Saudi Arabia, United Arab Emirates, Oman, Yemen, Qatar, Bahrain, Kuwait, Iraq, Iran, Jordan, Israel, Palestine, Lebanon, Syria |
| Asia (34) | Central Asia (6) | Kazakhstan, Uzbekistan, Turkmenistan, Kyrgyzstan, Tajikistan, Afghanistan |
| | South Asia (7) | India, Pakistan, Nepal, Bhutan, Bangladesh, Sri Lanka, the Maldives |
| | East Asia (8) | China, Japan, South Korea, North Korea, Mongolia, Taiwan, Hong Kong, Macao |
| | Southeast Asia (11) | Myanmar, Thailand, Laos, Cambodia, Vietnam, Malaysia, Singapore, Indonesia, Brunei, the Philippines, Timor-Leste |
| | Islands (2) | Christmas Island, the Cocos (Keeling) Islands |

**Staying where they are:**
- Turkey, Cyprus, Georgia, Armenia and Azerbaijan stay under Europe.
- "Russia (all)", which includes Siberia and the Russian Far East, also stays under Europe.

**Names:** places are named the way GBIF and the international standard (ISO 3166) name them, in their everyday short form: "South Korea", "Laos", "Vietnam", "Taiwan", "Palestine".

Each pack works like an African one: the species recorded there from GBIF, with the most-recorded suggested first.

## 2. How the areas are cut

By GBIF's country code, as for Europe, Latin America and Africa. Every place in the table has its own code.

Species with at least 5 records (GBIF, 25 Nov 2026):

| | Country | Species |
|---|---|---|
| Largest | China | 60,387 |
| | Japan | 52,845 |
| | Indonesia | 42,634 |
| | India | 38,980 |
| | the Philippines | 28,256 |
| Smallest | Cocos (Keeling) Islands | 967 |
| | Qatar | 682 |
| | Bahrain | 490 |

- **In all:** about 502,000 species across the 48, about as many as Latin America.
- **No country needs splitting:** even China is well under Brazil (87,529), whose pack already installs in about 20 seconds. China's will be about 3–4 MB.
- **Bahrain is under the checker's 500-species minimum, and Qatar is close to it.** Both get a lower floor (`TINY`), as Djibouti and Sint Maarten have.

**Codes:** each region's code is its own two-letter code in lower case (`cn`, `jp`, `in`, `il`…). None clashes with a code Thicket already uses.

## 3. Names

**Shown name: English.**
- **Birds** have the IOC names, spelt the British way, as in Africa and Latin America. eBird's names stay searchable.
- **Everything else** has GBIF's English names.

**Searchable too (local names).** These are the languages GBIF's Backbone has names in, counted on 25 Nov 2026:

| Language | Names | Where |
|---|---|---|
| Japanese | 27,600 | Japan |
| Chinese | 25,900 (simplified and traditional) | China, Taiwan, Hong Kong, Macao, Singapore |
| Russian | 15,000 | the five Central Asian countries, Mongolia |
| Malay | 11,700 | Malaysia, Brunei, Singapore, Indonesia |
| Arabic | 5,800 | the Arab countries of the Middle East |
| Tagalog | 4,300 | the Philippines |
| Tamil | 3,200 | India, Sri Lanka, Singapore |
| Thai | 2,900 | Thailand |
| Khmer | 2,900 | Cambodia |
| Korean | 2,100 | South and North Korea |
| Vietnamese | 2,100 | Vietnam |
| Indonesian | 1,000 | Indonesia |
| Bengali | 1,000 | Bangladesh, India |
| Hebrew | 960 | Israel (with Arabic) |
| Sinhala | 740 | Sri Lanka |
| Persian | 590 | Iran, Afghanistan |
| Nepali, Hindi, Burmese, Lao, Mongolian, Urdu | 100–530 each | Nepal; India; Myanmar; Laos; Mongolia; Pakistan |
| Portuguese | 48,000 | Timor-Leste |

Some of these names are written in the Latin alphabet (romanised) rather than the local script. GBIF has what it has, and both kinds are searchable.

**Short searches in Chinese, Japanese and Korean.**
- **Today:** a search of 1–2 characters only matches the start of a name or of a word after a space. These scripts don't put spaces between words, so 乌鸦 ("crow") wouldn't find 大嘴乌鸦 (Large-billed Crow), and 773 Chinese names are only 1–2 characters long.
- **The fix:** a short search written in a script without spaces (Chinese, Japanese, Korean, Thai, Lao, Khmer, Burmese) matches anywhere in a name. Searches of 3 or more characters already do.
- **Speed:** I'll time it on the trial packs before deciding. It must stay instant as you type.

## 4. Dates and the map

**Year-first dates.** Japan, China, Korea and Taiwan write dates year first.
- Today a spreadsheet date like 2026-11-25 is read, but 2026/11/25, 2026.11.25 and 2026年11月25日 (or 2026년 11월 25일) are not.
- These will be read for everyone. A date that starts with a four-digit year can't be confused with a day-first or a month-first one, so this changes nothing for UK users.

**Month-first.** The Philippines writes dates month first, as the US does, so it joins Puerto Rico and the US Virgin Islands in `MONTH_FIRST_TOO`. Everywhere else in Asia and the Middle East is day first or year first.

**The map** opens on each country, with a centre and zoom chosen for each, as for Africa.

## 5. In the app

- **Two new headings**, "Middle East" and "Asia", come after Africa in the region list.
- **The welcome's suggestion works for Asia with no change:** if Windows is set to Japan, Japan is chosen.
- **Other names** (docs/27) gain the names people also use:

  | Typed | Finds |
  |---|---|
  | Burma | Myanmar |
  | East Timor | Timor-Leste |
  | UAE | United Arab Emirates |
  | Macau | Macao |
  | Viet Nam | Vietnam |
  | Republic of Korea | South Korea |
  | DPRK | North Korea |
  | West Bank, Gaza | Palestine |
  | Keeling | the Cocos (Keeling) Islands |

- **Words:** the "No region called…" note, Add a region's introduction, Settings and the website will name the Middle East and Asia.

## 6. Publishing, and the packs run

- **One run, as before:** one pack per region, checked, then published.
- **How long:** with Asia there are 285 packs. The last run, with 237, took 1¼ hours, so this one should take about 1¾ hours, well inside the 4-hour limit.
- **Older Thicket versions:**
  - 1.6.1 and later skip regions they don't know, so Asia appears only from 1.11.0.
  - 1.6.0 (`manifest-2.json`) and the US-only list are unchanged.

## 7. Steps

1. **Regions.**
   - The 48 places with their codes, map views and languages, the two headings, the other names, and the Philippines month-first.
   - Year-first dates read for everyone.
   - Tests.
2. **The pack builder and a trial.**
   - Asian names and languages in `scripts/build_species_packs.py`.
   - A trial build of China, Japan, India, Israel and the Philippines on this computer, checked by the checker and installed with the app's code.
   - Check what names they have.
3. **Short searches.** The fix for scripts without spaces, timed on the trial packs, with tests.
4. **Publish the packs.** The lower floors, the release text naming Asia, and the packs run. I'll ask before pushing.
5. **Release Thicket 1.11.0.** The changelog, README, website and help, and the version. I'll ask before pushing.

As before, you approve the end of each step.

## 8. Not in this plan

- Splitting China, India or Indonesia by province: their packs are a fine size whole.
- Antarctica and the remaining Pacific islands (Fiji, Papua New Guinea, Hawaii's neighbours…): a later stage.

## Step 1 results (25 Nov 2026)

- **`domain/regions.py`:**
  - `_MIDDLE_EAST` (14) and `_ASIA` (34), with codes, map views and languages.
  - The headings `MIDDLE_EAST` and `ASIA` come after Africa in `GROUPS`. There are now 286 regions.
  - The Philippines is in `MONTH_FIRST_TOO`.
  - The other names from section 5 are added. The search tests found two more matches, both right: "za" now also finds Kazakhstan, and Palestine (through "Gaza").
- **Dates** (`domain/csv_import.py`): 2026/05/03, 2026.05.03, 2026年5月3日 and 2026년 5월 3일 are read for every region, the same whichever way the region writes dates. Mixed separators (2026/05-03) are still not a date.
- **Words:** the "No region called…" note, Add a region's introduction and Settings name the Middle East and Asia.
- **Not yet safe to publish packs:** `check_species_packs.py` expects a pack for every region, so a packs run before step 2 would fail. Nothing is pushed until step 4.
- **Tests:** 796 pass, including new ones for the 48 places and the year-first dates.

## Step 2 results (25 Nov 2026)

**The builder** (`scripts/build_species_packs.py`):
- `ASIA_NAMES` is the same name style as Africa's, used for both new headings.
- `middle_eastern_countries()` and `asian_countries()` provide the areas, and `--regions middle-east,asia` works.

**Trial** (`build/packs-asia2`): all pass the checker.

| Pack | Species | Size | Install |
|---|---|---|---|
| China | 59,592 | 3.5 MB | 11.0 s |
| Japan | 52,198 | 3.2 MB | 10.6 s |
| India | 38,452 | 2.4 MB | 8.0 s |
| the Philippines | 27,978 | 1.6 MB | 6.0 s |
| Israel | 9,733 | 0.7 MB | 3.0 s |

- **Birds are nearly all named:** 1,437 of 1,454 in China and 1,444 of 1,464 in India. The only "Gray" left is "Gray's Grasshopper Warbler", named after a person.
- **Local names:**
  - China has 4,000 in simplified and traditional characters, 326 of them only 1–2 characters long (麻雀, 白鹭, 八哥…).
  - Japan has 5,100 in katakana (スズメ, ハシブトガラス…).
  - Israel has about 300 each in Hebrew and Arabic.
  - India and the Philippines have few for birds, because GBIF hasn't got them.
- **Search** takes under 50 ms everywhere. 大嘴乌鸦 and 珠颈斑鸠 are found, but 乌鸦 and 斑鸠 are not yet (step 3).

**Found and fixed: the Giant Panda was "Bamboo Bear".**
- **The cause:** for most non-birds the most trusted source is the Catalogue of Life, which gives some species several English names in no particular order. The panda has six, and "Bamboo Bear" came first. The builder took the top source's first name, so it came down to luck.
- **The fix:** within the same source, the name most sources agree on now comes first.
  - Giant Panda, Red Panda, Dhole, White Rhinoceros.
  - Hemp (not "Grass"), Stinging Nettle (not "Big-sting Nettle"), Milkfish (not "Bangos").
- **What changes:** in a sample, 5–13% of named species, mostly fish and plants: 1,558 in California, 857 in South Africa and 882 in China.
  - Birds don't change, since their lists give one name each, and Europe's UK names still come first.
  - A few changes are for the worse, such as California's "Gray Wolf" becoming "Wolf".
- **Your choice (25 Nov):** use it in every pack, from the next packs run.
- **The old name stays searchable:** it's always kept among the three other names, so the name you learned still finds the species. In the sample, none was lost.

**Tests:** new ones for the builder's Asia areas and for the name agreement. 798 pass.

## Step 3 results (25 Nov 2026)

- **`data/repositories/taxa.py`:** a 1–2 character search containing Chinese, Japanese (kana too), Korean, Thai, Lao, Khmer or Burmese letters matches anywhere in a name (`instr`), not only at a word's start.
  - A match inside a name ranks with "a word starts with it", so a name that *starts* with the search still comes first.
  - Searches in the Latin alphabet behave as before.
- **Timed** with China, Japan and India installed (580,000 names in all), median of 5:

  | Search | Time | Found |
  |---|---|---|
  | 乌鸦 (crow) | 35 ms | Large-billed Crow, Carrion Crow, Rook, Hooded Crow |
  | 斑鸠 (dove) | 35 ms | 6 doves |
  | 鸦 | 35 ms | 20 (parrotbills, crows, choughs…) |
  | スズ | 34 ms | Tree Sparrow, House Sparrow, Greater Scaup… |
  | "ro", "cr" (unchanged) | 80–90 ms | |
  | "crow", 大嘴乌鸦 (3+) | 0–1 ms | |

  All are well inside the search box's pause before it searches.
- **Tests:** three new ones in `tests/integration/test_catalogue.py`, for Chinese, Japanese, and Latin-alphabet searches staying as they were. 801 pass.
