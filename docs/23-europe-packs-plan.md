# Thicket — species packs for Europe (plan)

**Date:** 18 November 2026
**Status:** Plan for your approval. No code yet.
**Target:** version 1.6.0

The US packs (docs/16-regions-plan.md) made "where you record" a setting, and added one downloadable species pack per state. This plan adds **one pack per European country**, built and delivered the same way.

**Your choices (18 Nov):**
- one pack per country;
- all of Europe except Russia and Turkey (they stretch far into Asia, so their packs would be huge; they can come later);
- English common names shown, local-language names searchable;
- this plan first, then building.

---

## 1. What you'll see

- **First start:** "Where do you record?" offers **United Kingdom**, **Elsewhere in Europe** (then a country) or **United States** (then a state).
- **Settings › Region:** "Add a US state…" becomes **Add a region…**. It lists European countries and US states in two groups, with a search box. Each shows its number of species and size.
- **Names:**
  - Common names are in **British English**, as in the rest of Thicket.
  - A species that's also in the UK list keeps its UK name. In France a Robin is "Robin", not "European Robin".
  - Species with no UK name get an English name from GBIF where one exists. Many insects, fungi and the like have none anywhere, so they show their scientific name, as US packs do.
  - **Local names are searchable.** In France, typing "rougequeue noir" finds Black Redstart. Packs carry up to three names in each of the country's languages: Belgium gets French, Dutch and German; Switzerland gets German, French and Italian.
- **Suggestions** put species most recorded in that country first.
- **The map** opens on the country. Grid squares stay UK-only, and positions show as latitude and longitude.
- **Spreadsheet dates** are read day-first (03/05 is 3 May), as in the UK.
- **Times** in iNaturalist files use your PC's time zone, as for US states.

Packs only ever add species, as now. Your sightings, and species already in your list, are never removed or changed. A species already in your list (from the UK list, a US pack or your own) is linked, never copied, so your life list counts it once.

---

## 2. The countries (46 packs)

Albania, Andorra, Austria, Belarus, Belgium, Bosnia and Herzegovina, Bulgaria, Croatia, Cyprus, Czechia, Denmark, Estonia, Faroe Islands, Finland, France, Germany, Gibraltar, Greece, Hungary, Iceland, Ireland, Italy, Kosovo, Latvia, Liechtenstein, Lithuania, Luxembourg, Malta, Moldova, Monaco, Montenegro, Netherlands, North Macedonia, Norway, Poland, Portugal, Romania, San Marino, Serbia, Slovakia, Slovenia, Spain, Sweden, Switzerland, Ukraine, Vatican City.

Notes:
- **Not included:** the UK (built in), Russia, Turkey, and the Caucasus countries (which straddle Europe and Asia). Overseas territories (French Guiana, Greenland, Svalbard and so on) have their own country codes in GBIF, so they aren't in these packs.
- **Islands:** Spain's pack includes the Canary Islands, and Portugal's the Azores and Madeira, because GBIF records them under Spain and Portugal. Visitors there will want them, but they make those packs larger. We'll check in step 2 whether to keep them in.
- **Tiny countries** (Monaco, Vatican City, San Marino and others) will have small packs. Each species must have at least five records there, as for US states.
- **Region codes** follow the international country codes: `fr`, `de`, `ie` and so on. US states stay `us-oh`.

---

## 3. Where the data comes from

The same as the US packs: GBIF's records, and the GBIF Backbone Taxonomy we already use.

- **Which species, and how common:** GBIF's occurrence search, counted per country, with the same rules as before. A species needs at least five records. Zoo animals, garden plants and fossils don't count.
- **Names, authors and family tree:** the GBIF Backbone. The English name order is:
  1. the UK list's name, if the species is in it (the builder reads the UK list in the repository);
  2. a GBIF English name used in Britain or Ireland;
  3. the best other English name, by the same source rules as now.

  Local names come from the Backbone's names in the country's languages.
- **Credit:** packs keep the same GBIF citation (CC BY 4.0), shown in Settings › About.

Nothing changes about how packs are fetched. Downloads still come only from Thicket's own GitHub releases, and each is checked against its published checksum before installing.

---

## 4. How older versions are kept working

Thicket 1.5 reads `manifest.json` and doesn't know the European region codes. If European packs appeared there, an older Thicket would show France as "the UK", with the UK map and grid squares.

So **1.6.0 reads a new list, `manifest-2.json`**, with every US state and European country. `manifest.json` keeps listing only the US states, for older versions. Both are published by the same workflow.

---

## 5. Changes inside Thicket

- **Regions:** the 46 countries are added to Thicket's list of regions, each with where the map opens. All of them read dates day-first.
- **Packs:** a new field carries the local names, installed as searchable names (older versions skip it). Thicket reads `manifest-2.json`.
- **Screens:**
  - "Add a region…" lists Europe and the United States, with search.
  - The welcome screen gets "Elsewhere in Europe".
  - The GBIF credit in Settings says "species packs" rather than "US states".
- **Builder** (`scripts/build_species_packs.py`):
  - a countries mode, counting by GBIF's country instead of by state;
  - name choice as in section 3;
  - local names;
  - both manifests.
- **Checker** (`scripts/check_species_packs.py`): also requires all 46 countries, and samples name quality.
- **Workflow:** builds the US and European packs on a `packs-*` tag, as now.

---

## 6. Steps (each with tests, each reviewed by you)

1. **Thicket itself:**
   - the European regions;
   - `manifest-2.json`;
   - local names in packs;
   - the "Add a region…" window and the welcome screen.

   Tested with an invented French pack. Nothing is published.
2. **The builder:** countries, names and local names. Trial builds of France, Spain and Ireland on this PC, with the GBIF Backbone we already have. You then check the names, for example France's birds, as we did with Ohio's.
3. **Build and publish all packs:** the workflow builds all 46 countries and the 51 US states, checks them, and publishes them, with both manifests. This needs your go-ahead, as it publishes.
4. **Release 1.6.0:** the changelog, and the website's Help page ("Changing region") and features page updated.

---

## 7. Risks and how they're handled

| Risk | Handling |
|---|---|
| Large countries (France, Spain, Germany, Italy) have tens of thousands of species | GBIF's counts are paged, as for California (35,000 species). Packs are compressed: an estimated 2–4 MB each. |
| Local names from GBIF vary in quality | Up to three per language, cleaned the same way as English names. They're only for searching, never shown as the main name. We'll sample them in step 2. |
| GBIF records in the wrong country (bad coordinates) | The five-record minimum, as now. The checker reports packs with odd groups. |
| A US pack or your own species has the same species | Linked, never copied, as now. |
| Older Thicket versions | They keep reading `manifest.json` (US states only), as in section 4. |
| The workflow takes longer (97 packs instead of 51) | Each pack takes a few GBIF requests. Expected under an hour, well inside GitHub's limit. |

---

## 8. Questions for later (not needed now)

- Russia and Turkey, perhaps as regions within them (European Russia, say).
- Packs for more of the world (Canada, Australia…), the same way.
- Local-language names shown instead of English, as a setting.

---

## Step 1 results (18 Nov 2026)

Done, with tests (684 pass, 4 more than before):

- **Regions** (`domain/regions.py`): the 46 countries, each with its map start, its group (Europe) and its languages (for step 2's local names). `COUNTRY_CODES` lists them for the builder. Only US states read dates month-first.
- **Packs:**
  - Thicket reads `manifest-2.json` (`services/species_packs.py`).
  - A pack's `ln` names (local languages) are installed as searchable names (`repositories/taxa.py`).
- **Screens:**
  - Settings › Region › **Add a region…** lists Europe and the United States under headings. Its search hides a heading with no matching region.
  - The welcome page offers **Elsewhere in Europe** with a country list. Both lists are fetched only when you choose Europe or the US, and Continue waits for a choice.
  - The GBIF credit says "Species packs (N)".
- **Tests** use an invented French pack (`helpers.FRANCE_PACK`): adding France shows "Black Redstart", typing "rougequeue" finds it, and a species in both packs stays one species.

Nothing is published yet: until step 3 there's no `manifest-2.json` on GitHub, so this version would find no packs. That's why step 3 comes before the release.

## Step 2 results (18 Nov 2026)

**The builder** (`scripts/build_species_packs.py`) builds European countries as well as US states:
- `--regions fr,es,ie` (or `europe`, `us`) picks which regions; by default it builds all of them.
- For Europe, English names come in this order: the UK list's name (read from the list built into Thicket), then names GBIF marks as used in Britain or Ireland, with the IOC bird list before Clements. US packs are built exactly as before.
- Local names: up to three per language of the country, tidied and never repeating an English one.
- It writes both lists: `manifest-2.json` (every pack) and `manifest.json` (US states only).

**The checker** reads `manifest-2.json`, checks that `manifest.json` is its US part, and has lower minimums for the tiny countries. With `--complete` (the workflow) it fails if any region has no pack. The workflow builds Europe too, and publishes both lists.

**Trial build** (France, Spain, Ireland; 7 minutes, mostly reading the Backbone):

| Pack | Species | Linked to UK species | Size | English name | Local names | Installs in |
|---|---|---|---|---|---|---|
| France | 61,532 | 28,673 | 4.0 MB | 29% | 12% | 13.5 s |
| Spain | 51,126 | 19,956 | 3.3 MB | 29% | 7.5% | 11.1 s |
| Ireland | 12,420 | 10,229 | 0.9 MB | 53% | 0.6% | 3.4 s |

- **Names are good.** Of France's 750 bird species, 747 have an English name and 734 French ones. Birds on the UK list keep their UK names (Blackbird, Woodpigeon, Pied Wagtail); the others get IOC names (Western Swamphen, Iberian Grey Shrike). Plants and mammals are just as good: Ivy, Hawthorn and Roe Deer, with "Lierre", "Aubépine" and "Chevreuil" searchable.
- **Spain** finds Spanish and Catalan names ("Petirrojo", "Pit-roig").
- **Gaps:** GBIF has few Irish-language names, and a few species lack a local name (Red Fox in France). This affects search only. Most insects and fungi have no English name anywhere, as in the US packs (29% named overall, like the large US states).
- **Islands:** Spain with the Canary Islands is 3.3 MB, so they stay in.
- **Checks:** all three packs pass. Fewer than 1% of animals, plants and fungi end up in "Other".

## Step 3 results (18 Nov 2026)

Published. The `packs-2026-11` tag built every pack on GitHub in about 45 minutes (Actions run 44305601627), checked them all, and published them.

- **`manifest-2.json`** (Thicket 1.6+) lists 97 packs: 46 European countries and 51 US states.
- **`manifest.json`** (older versions) lists the 51 US states only, so Thicket 1.5 and earlier carry on as before.
- **Sizes:** the European packs total 52.7 MB. The biggest are France (61,533 species, 4.0 MB), Sweden (53,797, 3.5 MB), Spain (51,126, 3.3 MB) and Germany (49,517, 3.4 MB). The smallest are Monaco (345 species), San Marino (189) and Vatican City (43).
- **End-to-end check:** the app's own download code, with the real internet, listed 97 packs and installed Ireland's (12,420 species), checked against its checksum. "Robin" then finds Robin, and "Irish Hare" finds Irish Hare.

Next: step 4, releasing Thicket 1.6.0, which reads `manifest-2.json`.

## Step 4 (18 Nov 2026)

Thicket 1.6.0: changelog entry; the website's home, features, Help ("The first start", "Changing region") and privacy pages, and the README, now mention Europe. The `v1.6.0` tag publishes it.

## Addendum: Russia, Turkey and the Caucasus (1.6.1)

Asked for after 1.6.0. Six more regions, all in the Europe group with British English names:

| Region | Code | Area | Local names |
|---|---|---|---|
| European Russia | `ru-eu` | Russia west of 60°E (the Urals) | Russian |
| Russia (all) | `ru` | all of Russia, Siberia and the Far East too | Russian |
| Turkey | `tr` | all of Turkey, Asian part too | Turkish |
| Georgia | `ge` | the whole country | Georgian |
| Armenia | `am` | the whole country | Armenian |
| Azerbaijan | `az` | the whole country | Azerbaijani |

- **European Russia** is the only pack not cut by country alone: GBIF's `decimalLongitude` filter (19 to 60) keeps it west of the Urals. Both Russia packs exist so someone in Moscow gets suggestions without Kamchatka's species, and someone travelling further can have them all.
- **A third list.** 1.6.0 would show a region it doesn't know with the UK's map and grid squares, so the new packs are only in `manifest-3.json`, which 1.6.1 reads. `manifest-2.json` stays as 1.6.0 knows it (the builder's `AFTER_1_6_0`), and 1.6.1 also leaves out any pack whose region it doesn't know, so later regions can be added the same way without waiting.
- **Local names are sparse.** GBIF has Russian names for most birds (441 of European Russia's 467) but few Turkish, Georgian, Armenian or Azerbaijani names (1 to 4% of species). Search by English or scientific name works everywhere.

### One species under two names

While checking Turkey's birds: GBIF's Backbone (2023) still has the Lesser Whitethroat as *Sylvia curruca*; the UK list has it as *Curruca curruca*. Packs linked to UK species only by key or the same scientific name, so a European pack added a **second** Lesser Whitethroat (named "Grey Whitethroat"), and so for about 1,200 of France's species (genus moves in birds, plants, fungi, insects).

The fix, in the app and the builder alike (`taxa.link_renamed`, `uk_name_for`):

- A pack species links to a UK species through synonyms: the pack's own (`sy`, a nominate subspecies such as *Curruca curruca curruca* counting as its species) or the UK list's.
- Only when it's safe: exactly one UK species fits, same kingdom, the species' own word is the same give or take its Latin ending (*Bromus erectus* → *Bromopsis erecta*), no other GBIF species is linked to it, and no other species in the pack wants it. Synonyms that change that word are too often a name once misapplied to another species (GBIF lists *Jasminum humile* as a synonym of *Chrysojasminum fruticans*), so those stay two species. A missed pair is no worse than before; a wrong merge would be.
- **Repair:** on its first start, 1.6.1 merges the copies 1.6.0 added. Sightings, notes, names, region details and saved filters move to the UK species; an imported sighting isn't marked as edited by the move.
- European packs now show the UK name for these (Lesser Whitethroat, not Grey Whitethroat).

With the real UK list and France's pack: 1,202 merged, in 1.4 s.
