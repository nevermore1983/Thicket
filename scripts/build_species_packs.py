"""Build species packs from GBIF: one per European country, US state, Canadian province or
territory and Australian state or territory, and one for New Zealand
(docs/16-regions-plan.md, docs/23-europe-packs-plan.md, docs/24-canada-australia-nz-plan.md).

    uv run python scripts/build_species_packs.py --backbone local_data/gbif/backbone.zip
    uv run python scripts/build_species_packs.py --backbone ... --regions fr,es,ie,us-oh

For each region:
1. GBIF's occurrence API lists every species recorded there (a US state, Canadian
   province or Australian state by GADM's boundaries, a country by GBIF's country code) with its number of records; species
   with fewer than --min-records (5) are left out (mostly misidentifications and garden
   escapes). Zoo animals, garden plants (living specimens) and fossils don't count.
2. Names, authors and family tree come from the GBIF Backbone Taxonomy file (read once,
   only the species needed are kept). The English name is chosen by choose_names():
   for the US and Canada as North American birders and naturalists use them; for
   Europe the UK list's name first (Thicket is in British English), then names used in
   Britain or Ireland; for Australia and New Zealand, IOC bird names and their own.
   Packs also carry names in the region's other languages ("ln"), for search: French in
   Europe, Québec and New Brunswick, Māori in New Zealand...
Output (in --out, default build/packs): fr.jsonl.gz, us-ca.jsonl.gz ... in the same
record format as the UK list (so Thicket installs them with the same code), and lists
of them with each pack's species count, size and SHA-256, which Thicket checks before
installing: manifest-3.json (every pack), manifest-2.json (those Thicket 1.6.0 knows)
and manifest.json (the US states only, for older versions): see write_manifests().
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wildlife.data.repositories.taxa import binomial_of, same_species_word  # noqa: E402
from wildlife.domain.regions import (  # noqa: E402  (one list of regions, shared with the app)
    AU_STATE_CODES,
    AUSTRALIA,
    CANADA,
    EUROPE,
    NEW_ZEALAND,
    NZ,
    POSTAL_CODES,
    PROVINCE_CODES,
    REGIONS,
    US,
)

DOWNLOADS = "https://github.com/nevermore1983/Thicket/releases/download"
API = "https://api.gbif.org/v1"
USER_AGENT = "Thicket species pack builder (https://github.com/nevermore1983/Thicket)"
COUNTED = (  # kinds of record that show a species lives there
    "HUMAN_OBSERVATION",
    "OBSERVATION",
    "MACHINE_OBSERVATION",
    "PRESERVED_SPECIMEN",
    "MATERIAL_SAMPLE",
    "OCCURRENCE",
)
PAGE = 20_000
FORMAT = 1  # manifest format; Thicket refuses a newer one
CITATION = (
    "Species and record counts: GBIF.org ({date}), GBIF Occurrence Search, "
    "https://www.gbif.org/. Names: GBIF Secretariat (2023), GBIF Backbone Taxonomy, "
    "checklist dataset, https://doi.org/10.15468/39omei, CC BY 4.0."
)

# English names: which source to trust first. Birders in the US use the Clements
# Checklist (eBird's); in Europe, the IOC list is closer to British names. Then general
# and North American lists; then anything.
BIRD_SOURCES = ("The Clements Checklist", "IOC World Bird List", "Multilingual IOC World Bird List")
EUROPE_BIRD_SOURCES = (
    "IOC World Bird List",
    "Multilingual IOC World Bird List",
    "The Clements Checklist",
)
SOURCES = (
    "Catalogue of Life Checklist",
    "Database of Vascular Plants of Canada (VASCAN)",
    "Checklist of the Butterflies",
    "Mammal Species of the World",
    "GRIN Taxonomy",
    "The IUCN Red List of Threatened Species",
    "Global Register of Introduced and Invasive Species - United States",
    "Checklist of Vermont Species",
)
UNTRUSTED = ("Martha's Vineyard species checklist",)  # many combined names ("Herring/Iceland Gull")
BRACKETED = re.compile(r"\s*\([^()]*\)\s*$")  # a note at the end of a name: "(Domestic type)"
NAMED_CLASSES = {
    "Aves",
    "Mammalia",
    "Amphibia",
    "Squamata",
    "Testudines",
    "Crocodylia",
    "Actinopterygii",
    "Elasmobranchii",
}
HYBRID_CROSS = re.compile(r"^\S+ \S+ [x×] ")  # "Genus species x species"


# ---- English names ----------------------------------------------------------------------
@dataclass(frozen=True)
class Candidate:
    name: str
    source: str
    country: str = ""


@dataclass(frozen=True)
class NameStyle:
    """Which English names a region's people use."""

    bird_sources: tuple[str, ...]
    home: tuple[str, ...]  # countries whose names are preferred
    home_first: bool  # before the source order (Europe) or only to break ties (the US)
    # The UK list's name for a species it has: shown first for "all" (Europe), for
    # everything but birds (Australia and New Zealand: IOC names for birds, and British
    # names for the weeds and pests that came from Britain), or "none" (North America)
    uk_names: str = "none"
    british: bool = False  # "Grey", not "Gray"


US_NAMES = NameStyle(BIRD_SOURCES, ("US",), home_first=False)
EUROPE_NAMES = NameStyle(
    EUROPE_BIRD_SOURCES, ("GB", "IE"), home_first=True, uk_names="all", british=True
)
# Canadian birders use the same (eBird, AOS) names as the US
CANADA_NAMES = NameStyle(BIRD_SOURCES, ("CA", "US"), home_first=False)
# BirdLife Australia and Birds New Zealand follow the IOC list closely
AUSTRALIA_NAMES = NameStyle(
    EUROPE_BIRD_SOURCES, ("AU",), home_first=True, uk_names="not birds", british=True
)
NEW_ZEALAND_NAMES = NameStyle(
    EUROPE_BIRD_SOURCES, ("NZ", "AU"), home_first=True, uk_names="not birds", british=True
)
# Where GBIF's Backbone joins two species the IOC list keeps apart, its name is the one
# that isn't there: Australia's Rainbow Lorikeet came out as the Coconut Lorikeet of New
# Guinea. Names that people in the region use, by scientific name.
PREFERRED = {
    AUSTRALIA: {
        "Trichoglossus haematodus": "Rainbow Lorikeet",
        "Chenonetta jubata": "Australian Wood Duck",
    },
    NEW_ZEALAND: {"Trichoglossus haematodus": "Rainbow Lorikeet"},
}
GRAY = re.compile(r"\b(G|g)ray\b(?!')")  # not "Gray's Beaked Whale", named after Mr Gray
MACRON = re.compile("[āēīōūĀĒĪŌŪ]")  # Māori: GBIF often files "Tūī", "Kererū" as English

STYLES = {
    EUROPE: EUROPE_NAMES,
    US: US_NAMES,
    CANADA: CANADA_NAMES,
    AUSTRALIA: AUSTRALIA_NAMES,
    NEW_ZEALAND: NEW_ZEALAND_NAMES,
}


def tidy(name: str) -> str | None:
    """A usable common name, or None: no lists or combinations ("House/Italian Sparrow",
    "Fox, Red Fox", "Northern Cardinal (Common)"), and all-lowercase names capitalised."""
    name = " ".join(name.split())
    if not name or any(ch in name for ch in "/(),;[]") or len(name) > 60:
        return None
    if name == name.lower():
        name = " ".join(w[:1].upper() + w[1:] for w in name.split(" "))
    return name


def _rank(candidate: Candidate, is_bird: bool, style: NameStyle) -> tuple[int, int]:
    order = (*style.bird_sources, *SOURCES) if is_bird else (*SOURCES, *style.bird_sources)
    position = next((i for i, s in enumerate(order) if candidate.source.startswith(s)), len(order))
    if candidate.source.startswith(UNTRUSTED):
        position = len(order) + 1
    home = 0 if candidate.country in style.home else 1
    return (home, position) if style.home_first else (position, home)


def choose_names(
    candidates: list[Candidate],
    is_bird: bool,
    style: NameStyle = US_NAMES,
    uk_name: str | None = None,
) -> tuple[str | None, list[str]]:
    """(the common name to show, up to 3 other English names for search). `uk_name`, the
    UK list's name for the species, comes first when given (European packs)."""
    ranked = sorted(candidates, key=lambda c: _rank(c, is_bird, style))
    names: list[str] = [uk_name] if uk_name else []
    for c in ranked:
        name = tidy(c.name)
        if name and style.british:
            name = GRAY.sub(lambda m: m[1] + "rey", name)
        if name and name.lower() not in {n.lower() for n in names}:
            names.append(name)
    if not names:  # only bracketed ones: "Muscovy Duck (Domestic type)" -> "Muscovy Duck"
        for c in ranked:
            if name := tidy(BRACKETED.sub("", c.name)):
                return name, []
    return (names[0] if names else None), names[1:4]


def local_names(
    by_language: dict[str, list[str]], languages: tuple[str, ...], english: set[str]
) -> list[str]:
    """Up to 3 names in each of a country's languages, for search: tidied ("Rougequeue
    noir", only the first letter capitalised), none repeated, none the same as an English
    one."""
    out: list[str] = []
    seen = {e.lower() for e in english}
    for language in languages:
        kept = 0
        for raw in by_language.get(language, ()):
            name = " ".join(raw.split())
            if not name or any(ch in name for ch in "/(),;[]") or len(name) > 60:
                continue
            name = name[:1].upper() + name[1:]
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            out.append(name)
            kept += 1
            if kept == 3:
                break
    return out


def uk_names(path: Path | None = None) -> dict:
    """The UK list's common names (the one built into Thicket), by (scientific name,
    kingdom): a species in it keeps its UK name in a European pack."""
    path = path or ROOT / "src" / "wildlife" / "resources" / "species" / "uksi_taxa.jsonl.gz"
    names: dict = {}  # (name, kingdom) -> its UK name; (SYNONYM, name, kingdom) -> {names}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("r") == "species" and rec.get("c"):
                kingdom = ((rec.get("l") or [None])[0] or "").lower()
                names.setdefault((rec["s"].lower(), kingdom), rec["c"])
                for synonym in rec.get("sy", ()):
                    if (binomial := binomial_of(synonym)) and same_species_word(synonym, rec["s"]):
                        names.setdefault((SYNONYM, binomial, kingdom), set()).add(rec["c"])
    return names


SYNONYM = "synonym"  # uk_names()'s keys for the UK list's older names: (SYNONYM, name, kingdom)


def uk_name_for(uk: dict, canonical: str, kingdom: str, synonyms: list[str]) -> str | None:
    """The UK list's name for a species, also when the two disagree on its genus (GBIF's
    Sylvia curruca is the UK list's Curruca curruca, Lesser Whitethroat): by the GBIF
    species' synonyms, or the UK list's. The same rule Thicket links them by
    (taxa.link_renamed): only one fits, and the species' own word is the same."""
    kingdom = kingdom.lower()
    if found := uk.get((canonical.lower(), kingdom)):
        return found
    fits = {
        uk[(b, kingdom)]
        for s in synonyms
        if (b := binomial_of(s)) and (b, kingdom) in uk and same_species_word(s, canonical)
    }
    if not fits and (b := binomial_of(canonical)):
        fits = set(uk.get((SYNONYM, b, kingdom), ()))
    return fits.pop() if len(fits) == 1 else None


def wants_a_name(taxon: dict) -> bool:
    """Groups where people expect a common name: vertebrates, dragonflies and damselflies.
    (Most insects, fungi and the like have none anywhere, so they aren't looked up.)"""
    ranks = lineage(taxon)
    return ranks[2] in NAMED_CLASSES or ranks[3] == "Odonata"


def is_hybrid_cross(scientific_name: str) -> bool:
    """A cross between two species ("Anas rubripes x platyrhynchos"): not a species, so not
    in a pack. A named hybrid species ("Mentha × piperita", peppermint) is kept."""
    return bool(HYBRID_CROSS.match(scientific_name))


# ---- GBIF's API -------------------------------------------------------------------------
def get_json(path: str, params: dict | list | None = None) -> dict:
    query = urllib.parse.urlencode(params or {}, doseq=True)
    url = f"{API}/{path}" + (f"?{query}" if query else "")
    for attempt in range(5):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.load(response)
        except (OSError, ValueError) as exc:
            if attempt == 4:
                raise
            wait = 5 * (attempt + 1)
            print(f"  GBIF didn't answer ({exc}); trying again in {wait} s", flush=True)
            time.sleep(wait)
    raise AssertionError("unreachable")


@dataclass(frozen=True)
class Area:
    """A region a pack is built for: a European country, a US state..."""

    region: str  # 'us-ca', 'fr'
    name: str  # 'California', 'France'
    filters: tuple[tuple[str, str], ...]  # GBIF's occurrence search, for this region
    group: str  # one of regions.GROUPS
    languages: tuple[str, ...] = ()

    @property
    def style(self) -> NameStyle:
        return STYLES[self.group]


def us_states() -> list[Area]:
    """The 50 states and DC, as GBIF knows them (GADM boundaries)."""
    facets = get_json(
        "occurrence/search",
        {"country": "US", "facet": "gadmLevel1Gid", "facetLimit": 100, "limit": 0},
    )["facets"][0]["counts"]
    states = []
    for gid in sorted({f["name"] for f in facets if f["name"].startswith("USA.")}):
        name = get_json(f"geocode/gadm/{gid}")["name"]
        if name not in POSTAL_CODES:
            raise SystemExit(f"GBIF knows a US area Thicket doesn't: {name} ({gid})")
        code = POSTAL_CODES[name].lower()
        states.append(Area(f"us-{code}", name, (("country", "US"), ("gadmLevel1Gid", gid)), US))
    if len(states) != len(POSTAL_CODES):
        missing = sorted(set(POSTAL_CODES) - {s.name for s in states})
        raise SystemExit(
            f"Expected {len(POSTAL_CODES)} states, GBIF gave {len(states)}; missing {missing}"
        )
    return states


def _plain(name: str) -> str:
    """'Québec' -> 'quebec': GADM's names, compared with Thicket's."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()


# GADM areas that go into a neighbour's pack: Jervis Bay Territory, surrounded by New
# South Wales. Ashmore and Cartier and the Coral Sea Islands (remote reefs, nobody lives
# there) are left out.
JOINS = {"Jervis Bay Territory": "New South Wales"}
LEFT_OUT = {"Ashmore and Cartier Islands", "Coral Sea Islands Territory"}


def gadm_areas(
    country: str, gadm: str, codes: dict[str, str], prefix: str, group: str
) -> list[Area]:
    """A country's first-level areas (Canada's provinces, Australia's states) as GBIF
    knows them (GADM boundaries), each with Thicket's code."""
    facets = get_json(
        "occurrence/search",
        {"country": country, "facet": "gadmLevel1Gid", "facetLimit": 100, "limit": 0},
    )["facets"][0]["counts"]
    gids: dict[str, list[str]] = defaultdict(list)  # Thicket's name -> GADM ids
    by_plain = {_plain(name): name for name in codes}
    for gid in sorted({f["name"] for f in facets if f["name"].startswith(f"{gadm}.")}):
        name = get_json(f"geocode/gadm/{gid}")["name"]
        if name in LEFT_OUT:
            continue
        name = JOINS.get(name, name)
        if _plain(name) not in by_plain:
            raise SystemExit(f"GBIF knows an area of {country} Thicket doesn't: {name} ({gid})")
        gids[by_plain[_plain(name)]].append(gid)
    if set(gids) != set(codes):
        raise SystemExit(
            f"Missing from GBIF's areas of {country}: {sorted(set(codes) - set(gids))}"
        )
    areas = []
    for name, ids in sorted(gids.items()):
        code = f"{prefix}-{codes[name].lower()}"
        filters = (("country", country), *(("gadmLevel1Gid", g) for g in ids))
        areas.append(Area(code, name, filters, group, REGIONS[code].languages))
    return areas


def canadian_provinces() -> list[Area]:
    return gadm_areas("CA", "CAN", PROVINCE_CODES, "ca", CANADA)


def australian_states() -> list[Area]:
    return gadm_areas("AU", "AUS", AU_STATE_CODES, "au", AUSTRALIA)


def new_zealand() -> list[Area]:
    """One pack for the whole country, its outlying islands too."""
    nz = REGIONS[NZ]
    return [Area(NZ, nz.name, (("country", "NZ"),), NEW_ZEALAND, nz.languages)]


# Regions that aren't a whole country: GBIF's search filters for them
SPECIAL_FILTERS = {
    # Russia west of the Urals (about 60°E): Moscow, St Petersburg, the Volga, Kaliningrad
    "ru-eu": (("country", "RU"), ("decimalLongitude", "19,60")),
}
# European packs Thicket 1.6.0 doesn't know (it reads manifest-2.json: see in_1_6_0)
AFTER_1_6_0 = {"ru", "ru-eu", "tr", "ge", "am", "az"}


def in_1_6_0(region: str) -> bool:
    """Whether Thicket 1.6.0 knows this region: the US states and Europe as it was. It
    would show another with the UK's map and grid squares, so manifest-2.json leaves it
    out. (1.6.1 and later read manifest-3.json and skip what they don't know.)"""
    if region.startswith("us-"):
        return True
    known = REGIONS.get(region)
    return known is not None and known.group == EUROPE and region not in AFTER_1_6_0


def european_countries() -> list[Area]:
    """The countries of Europe Thicket offers (domain/regions.py), by GBIF's country code."""
    return [
        Area(
            r.code,
            r.name,
            SPECIAL_FILTERS.get(r.code, (("country", r.code.upper()),)),
            EUROPE,
            r.languages,
        )
        for r in REGIONS.values()
        if r.group == EUROPE
    ]


# Each group's areas, and how its region codes start ('' for Europe's country codes)
SOURCES_OF_AREAS = (
    ("us", "us-", us_states),
    ("canada", "ca-", canadian_provinces),
    ("australia", "au-", australian_states),
    ("nz", NZ, new_zealand),
    ("europe", "", european_countries),
)


def species_counts(area: Area, min_records: int) -> dict[int, int]:
    """GBIF species key -> number of records in the region (at least min_records)."""
    counts: dict[int, int] = {}
    offset = 0
    while True:
        params = [
            *area.filters,
            ("occurrenceStatus", "PRESENT"),
            *(("basisOfRecord", b) for b in COUNTED),
            ("facet", "speciesKey"),
            ("facetMincount", min_records),
            ("facetLimit", PAGE),
            ("facetOffset", offset),
            ("limit", 0),
        ]
        page = get_json("occurrence/search", params)["facets"][0]["counts"]
        counts.update((int(f["name"]), f["count"]) for f in page)
        if len(page) < PAGE:
            return counts
        offset += PAGE


# ---- the Backbone file ------------------------------------------------------------------
def _rows(archive: zipfile.ZipFile, member: str):
    with archive.open(member) as f:
        reader = csv.reader(
            io.TextIOWrapper(f, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE
        )
        header = next(reader)
        for row in reader:
            yield dict(zip(header, row, strict=False))


def read_backbone(
    path: Path, wanted: set[int], languages: set[str] = frozenset()
) -> tuple[
    dict[int, dict],
    dict[int, list[str]],
    dict[int, list[Candidate]],
    dict[int, dict[str, list[str]]],
]:
    """(species details, synonyms, English name candidates, names in other languages:
    key -> language -> names) for the wanted keys."""
    taxa: dict[int, dict] = {}
    synonyms: dict[int, list[str]] = defaultdict(list)
    keys = {str(k) for k in wanted}
    with zipfile.ZipFile(path) as archive:
        for row in _rows(archive, "Taxon.tsv"):
            if row["taxonID"] in keys and row["taxonomicStatus"] == "accepted":
                taxa[int(row["taxonID"])] = row
            elif row["acceptedNameUsageID"] in keys and row["taxonomicStatus"] != "accepted":
                accepted = int(row["acceptedNameUsageID"])
                if row["canonicalName"] and len(synonyms[accepted]) < 5:
                    synonyms[accepted].append(row["canonicalName"])
        names: dict[int, list[Candidate]] = defaultdict(list)
        local: dict[int, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for row in _rows(archive, "VernacularName.tsv"):
            if row["taxonID"] not in keys:
                continue
            if row["language"] == "en":
                names[int(row["taxonID"])].append(
                    Candidate(
                        row["vernacularName"], row.get("source", ""), row.get("countryCode", "")
                    )
                )
            elif row["language"] in languages:
                local[int(row["taxonID"])][row["language"]].append(row["vernacularName"])
    return taxa, synonyms, names, local


def lineage(taxon: dict) -> list[str | None]:
    """[kingdom, phylum, class, order, family]. GBIF's Backbone gives ray-finned fish no
    class (their orders sit straight under Chordata): it's filled in, so Thicket sorts
    them with the fish. (Bird and mammal orders always come with their class.)"""
    ranks = [taxon.get(r) or None for r in ("kingdom", "phylum", "class", "order", "family")]
    if ranks[1] == "Chordata" and ranks[2] is None and (ranks[3] or "").endswith("iformes"):
        ranks[2] = "Actinopterygii"
    return ranks


def record(
    key: int,
    count: int,
    taxon: dict,
    synonyms: list[str],
    names: list[Candidate],
    style: NameStyle = US_NAMES,
    uk_name: str | None = None,
    local: list[str] | None = None,
) -> dict:
    """One species in Thicket's pack format (the same as the UK list's)."""
    common, others = choose_names(names, taxon.get("class") == "Aves", style, uk_name)
    canonical = taxon.get("canonicalName") or taxon["scientificName"]
    rec = {
        "k": f"gbif:{key}",
        "r": "species",
        "s": canonical,
        "a": taxon.get("scientificNameAuthorship") or None,
        "c": common,
        "l": lineage(taxon),
        "pr": count,
    }
    if others:
        rec["en"] = others
    if local:
        rec["ln"] = local
    if synonyms := [s for s in synonyms if s != canonical]:
        rec["sy"] = synonyms
    return {k: v for k, v in rec.items() if v is not None}


def write_pack(path: Path, records: list[dict]) -> tuple[int, str]:
    """Write a pack (most recorded first); returns (bytes, SHA-256)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as f:
        for rec in sorted(records, key=lambda r: -r["pr"]):
            f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def chosen_areas(wanted: str | None) -> list[Area]:
    """Every region, or those asked for: region codes ('fr,ca-on,nz') or whole groups
    ('europe', 'us', 'canada', 'australia', 'nz'). Only the groups needed are asked
    GBIF for their areas."""
    if not wanted:
        return [a for _, _, areas in SOURCES_OF_AREAS for a in areas()]
    asked = {w.strip().lower() for w in wanted.split(",") if w.strip()}

    def group_of_code(code: str) -> str:
        return next(g for g, start, _ in SOURCES_OF_AREAS if code.startswith(start))

    groups = {a for a in asked if a in {g for g, _, _ in SOURCES_OF_AREAS}}
    codes = asked - groups
    areas = [
        a
        for g, _, make in SOURCES_OF_AREAS
        if g in groups or any(group_of_code(c) == g for c in codes)
        for a in make()
        if g in groups or a.region in codes
    ]
    unknown = codes - {a.region for a in areas}
    if unknown:
        raise SystemExit(f"Not a region Thicket knows: {', '.join(sorted(unknown))}")
    return areas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backbone", type=Path, required=True, help="GBIF backbone.zip")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "packs")
    parser.add_argument(
        "--regions",
        help="only these: region codes (fr,ca-on,nz) or europe, us, canada, australia, nz "
        "(default: all)",
    )
    parser.add_argument("--min-records", type=int, default=5)
    parser.add_argument(
        "--release",
        help="the GitHub release the packs go in (e.g. packs-2026-11): sets each pack's url",
    )
    args = parser.parse_args()

    backbone_sha = hashlib.sha256(args.backbone.read_bytes()).hexdigest()
    areas = chosen_areas(args.regions)
    print(f"{len(areas)} regions", flush=True)
    counts: dict[Area, dict[int, int]] = {}
    for area in areas:
        started = time.perf_counter()
        counts[area] = species_counts(area, args.min_records)
        print(
            f"  {area.name}: {len(counts[area]):,} species ({time.perf_counter() - started:.0f} s)",
            flush=True,
        )

    wanted = set().union(*(c.keys() for c in counts.values())) if counts else set()
    languages = {lang for a in areas for lang in a.languages}
    print(f"Reading the Backbone for {len(wanted):,} species…", flush=True)
    taxa, synonyms, names, local = read_backbone(args.backbone, wanted, languages)
    missing = wanted - taxa.keys()
    for key in sorted(missing):  # newer than the Backbone file: ask GBIF
        info = get_json(f"species/{key}")
        if info.get("taxonomicStatus") == "ACCEPTED" and info.get("rank") == "SPECIES":
            taxa[key] = {
                "canonicalName": info.get("canonicalName"),
                "scientificName": info.get("scientificName"),
                "scientificNameAuthorship": info.get("authorship"),
                **{r: info.get(r) for r in ("kingdom", "phylum", "class", "order", "family")},
            }
            if info.get("vernacularName"):
                names[key].append(Candidate(info["vernacularName"], "GBIF species page"))
    print(f"  {len(missing):,} looked up through the API", flush=True)
    unnamed = [
        k
        for k, t in taxa.items()
        if wants_a_name(t) and not choose_names(names.get(k, []), False)[0]
    ]
    for key in unnamed:  # the Backbone file has no English name: GBIF's live page may
        if name := get_json(f"species/{key}").get("vernacularName"):
            names[key].append(Candidate(name, "GBIF species page"))
    print(
        f"  {len(unnamed):,} vertebrates and dragonflies without a name: asked GBIF's species pages",
        flush=True,
    )
    uk = uk_names() if any(a.style.uk_names != "none" for a in areas) else {}

    today = datetime.now(UTC).date().isoformat()
    manifest = {
        "format": FORMAT,
        "created": today,
        "source": "GBIF",
        "citation": CITATION.format(date=today),
        "backbone_sha256": backbone_sha,
        "min_records": args.min_records,
        "packs": [],
    }
    for area in areas:
        records = []
        for k, n in counts[area].items():
            taxon = taxa.get(k)
            canonical = taxon and (taxon.get("canonicalName") or taxon["scientificName"])
            if taxon is None or is_hybrid_cross(canonical):
                continue
            # The name to show first: one the region's people use, else the UK list's
            uk_name = PREFERRED.get(area.group, {}).get(canonical)
            uk_rule = area.style.uk_names
            if not uk_name and (
                uk_rule == "all" or (uk_rule == "not birds" and taxon.get("class") != "Aves")
            ):
                uk_name = uk_name_for(
                    uk, canonical, taxon.get("kingdom") or "", synonyms.get(k, [])
                )
            english = {c.name for c in names.get(k, [])} | ({uk_name} if uk_name else set())
            by_language = local.get(k, {})
            if "mi" in area.languages:  # Māori names GBIF has as English ones
                maori = [c.name for c in names.get(k, []) if MACRON.search(c.name)]
                by_language = {**by_language, "mi": [*by_language.get("mi", []), *maori]}
                english -= set(maori)
            ln = local_names(by_language, area.languages, english) or None
            records.append(
                record(k, n, taxon, synonyms.get(k, []), names.get(k, []), area.style, uk_name, ln)
            )
        file = f"{area.region}.jsonl.gz"
        size, sha = write_pack(args.out / file, records)
        manifest["packs"].append(
            {
                "region": area.region,
                "name": area.name,
                "file": file,
                "species": len(records),
                "bytes": size,
                "sha256": sha,
                "url": f"{DOWNLOADS}/{args.release}/{file}" if args.release else None,
            }
        )
        named = sum(1 for r in records if r.get("c"))
        with_local = sum(1 for r in records if r.get("ln"))
        print(
            f"  {file}: {len(records):,} species, {named / max(1, len(records)):.0%} with an "
            f"English name, {with_local / max(1, len(records)):.0%} with local names, "
            f"{size / 1e6:.1f} MB",
            flush=True,
        )
    write_manifests(args.out, manifest)
    print(f"Done: {args.out}", flush=True)


def write_manifests(out: Path, manifest: dict) -> None:
    """Three lists, each for the versions that know its regions:
    manifest-3.json every pack (Thicket 1.6.1+, which skips regions it doesn't know);
    manifest-2.json those 1.6.0 knows (it would take an unknown region for the UK:
    in_1_6_0);
    manifest.json the US states only (1.1 to 1.5)."""
    out.mkdir(parents=True, exist_ok=True)

    def write(name: str, keep) -> None:
        packs = [p for p in manifest["packs"] if keep(p["region"])]
        (out / name).write_text(
            json.dumps({**manifest, "packs": packs}, indent=1), encoding="utf-8"
        )

    write("manifest-3.json", lambda region: True)
    write("manifest-2.json", in_1_6_0)
    write("manifest.json", lambda region: region.startswith("us-"))


if __name__ == "__main__":
    from ci_report import report_failures

    report_failures(main, "Building the species packs failed")
