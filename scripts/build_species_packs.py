"""Build species packs for US states from GBIF (docs/16-regions-plan.md, step 2).

    uv run python scripts/build_species_packs.py --backbone local_data/gbif/backbone.zip
    uv run python scripts/build_species_packs.py --backbone ... --states CA,OH,TX

For each state:
1. GBIF's occurrence API lists every species recorded there (by coordinates, using
   GADM's state boundaries) with its number of records; species with fewer than
   --min-records (5) are left out (mostly misidentifications and garden escapes).
   Zoo animals, garden plants (living specimens) and fossils don't count.
2. Names, authors and family tree come from the GBIF Backbone Taxonomy file (read once,
   only the species needed are kept), and an English common name is chosen by
   choose_names() below.
Output (in --out, default build/packs): us-ca.jsonl.gz ... in the same record format as
the UK list (so WildLife installs them with the same code), and manifest.json with each
pack's species count, size and SHA-256, which WildLife checks before installing.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import time
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = "https://github.com/nevermore1983/WildlifeTracker/releases/download"
API = "https://api.gbif.org/v1"
USER_AGENT = "WildLife species pack builder (https://github.com/nevermore1983/WildlifeTracker)"
COUNTED = (  # kinds of record that show a species lives there
    "HUMAN_OBSERVATION",
    "OBSERVATION",
    "MACHINE_OBSERVATION",
    "PRESERVED_SPECIMEN",
    "MATERIAL_SAMPLE",
    "OCCURRENCE",
)
PAGE = 20_000
FORMAT = 1  # manifest format; WildLife refuses a newer one
CITATION = (
    "Species and record counts: GBIF.org ({date}), GBIF Occurrence Search, "
    "https://www.gbif.org/. Names: GBIF Secretariat (2023), GBIF Backbone Taxonomy, "
    "checklist dataset, https://doi.org/10.15468/39omei, CC BY 4.0."
)

# English names: which source to trust first. Birders in the US use the Clements
# Checklist (eBird's); then international and North American lists; then anything.
BIRD_SOURCES = ("The Clements Checklist", "IOC World Bird List", "Multilingual IOC World Bird List")
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


def tidy(name: str) -> str | None:
    """A usable common name, or None: no lists or combinations ("House/Italian Sparrow",
    "Fox, Red Fox", "Northern Cardinal (Common)"), and all-lowercase names capitalised."""
    name = " ".join(name.split())
    if not name or any(ch in name for ch in "/(),;[]") or len(name) > 60:
        return None
    if name == name.lower():
        name = " ".join(w[:1].upper() + w[1:] for w in name.split(" "))
    return name


def _rank(candidate: Candidate, is_bird: bool) -> tuple[int, int]:
    order = (*BIRD_SOURCES, *SOURCES) if is_bird else (*SOURCES, *BIRD_SOURCES)
    position = next((i for i, s in enumerate(order) if candidate.source.startswith(s)), len(order))
    if candidate.source.startswith(UNTRUSTED):
        position = len(order) + 1
    return position, 0 if candidate.country == "US" else 1


def choose_names(candidates: list[Candidate], is_bird: bool) -> tuple[str | None, list[str]]:
    """(the common name to show, up to 3 other English names for search)."""
    ranked = sorted(candidates, key=lambda c: _rank(c, is_bird))
    names: list[str] = []
    for c in ranked:
        if (name := tidy(c.name)) and name.lower() not in {n.lower() for n in names}:
            names.append(name)
    if not names:  # only bracketed ones: "Muscovy Duck (Domestic type)" -> "Muscovy Duck"
        for c in ranked:
            if name := tidy(BRACKETED.sub("", c.name)):
                return name, []
    return (names[0] if names else None), names[1:4]


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
class State:
    gid: str  # GADM level 1, e.g. USA.5_1
    name: str  # California
    code: str  # CA

    @property
    def region(self) -> str:
        return f"us-{self.code.lower()}"


# The 50 states and DC, with their postal codes (pack names: us-oh). A fixed list: GBIF's
# own data lacks some codes (Rhode Island's was missing, and that state was skipped).
POSTAL_CODES = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "District of Columbia": "DC",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}


def us_states() -> list[State]:
    """The 50 states and DC, as GBIF knows them (GADM boundaries)."""
    facets = get_json(
        "occurrence/search",
        {"country": "US", "facet": "gadmLevel1Gid", "facetLimit": 100, "limit": 0},
    )["facets"][0]["counts"]
    states = []
    for gid in sorted({f["name"] for f in facets if f["name"].startswith("USA.")}):
        name = get_json(f"geocode/gadm/{gid}")["name"]
        if name not in POSTAL_CODES:
            raise SystemExit(f"GBIF knows a US area WildLife doesn't: {name} ({gid})")
        states.append(State(gid, name, POSTAL_CODES[name]))
    if len(states) != len(POSTAL_CODES):
        missing = sorted(set(POSTAL_CODES) - {s.name for s in states})
        raise SystemExit(
            f"Expected {len(POSTAL_CODES)} states, GBIF gave {len(states)}; missing {missing}"
        )
    return states


def species_counts(state: State, min_records: int) -> dict[int, int]:
    """GBIF species key -> number of records in the state (at least min_records)."""
    counts: dict[int, int] = {}
    offset = 0
    while True:
        params = [
            ("country", "US"),
            ("gadmLevel1Gid", state.gid),
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
    path: Path, wanted: set[int]
) -> tuple[dict[int, dict], dict[int, list[str]], dict[int, list[Candidate]]]:
    """(species details, synonyms, English name candidates) for the wanted keys."""
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
        for row in _rows(archive, "VernacularName.tsv"):
            if row["language"] == "en" and row["taxonID"] in keys:
                names[int(row["taxonID"])].append(
                    Candidate(
                        row["vernacularName"], row.get("source", ""), row.get("countryCode", "")
                    )
                )
    return taxa, synonyms, names


def lineage(taxon: dict) -> list[str | None]:
    """[kingdom, phylum, class, order, family]. GBIF's Backbone gives ray-finned fish no
    class (their orders sit straight under Chordata): it's filled in, so WildLife sorts
    them with the fish. (Bird and mammal orders always come with their class.)"""
    ranks = [taxon.get(r) or None for r in ("kingdom", "phylum", "class", "order", "family")]
    if ranks[1] == "Chordata" and ranks[2] is None and (ranks[3] or "").endswith("iformes"):
        ranks[2] = "Actinopterygii"
    return ranks


def record(key: int, count: int, taxon: dict, synonyms: list[str], names: list[Candidate]) -> dict:
    """One species in WildLife's pack format (the same as the UK list's)."""
    common, others = choose_names(names, taxon.get("class") == "Aves")
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backbone", type=Path, required=True, help="GBIF backbone.zip")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "packs")
    parser.add_argument("--states", help="only these, e.g. CA,OH,TX (default: all)")
    parser.add_argument("--min-records", type=int, default=5)
    parser.add_argument(
        "--release",
        help="the GitHub release the packs go in (e.g. packs-2026-10): sets each pack's url",
    )
    args = parser.parse_args()

    backbone_sha = hashlib.sha256(args.backbone.read_bytes()).hexdigest()
    states = us_states()
    if args.states:
        chosen = {s.strip().upper() for s in args.states.split(",")}
        states = [s for s in states if s.code in chosen]
    print(f"{len(states)} states", flush=True)
    counts: dict[State, dict[int, int]] = {}
    for state in states:
        started = time.perf_counter()
        counts[state] = species_counts(state, args.min_records)
        print(
            f"  {state.name}: {len(counts[state]):,} species ({time.perf_counter() - started:.0f} s)",
            flush=True,
        )

    wanted = set().union(*(c.keys() for c in counts.values())) if counts else set()
    print(f"Reading the Backbone for {len(wanted):,} species…", flush=True)
    taxa, synonyms, names = read_backbone(args.backbone, wanted)
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
    for state in states:
        records = [
            record(k, n, taxa[k], synonyms.get(k, []), names.get(k, []))
            for k, n in counts[state].items()
            if k in taxa
            and not is_hybrid_cross(taxa[k].get("canonicalName") or taxa[k]["scientificName"])
        ]
        file = f"{state.region}.jsonl.gz"
        size, sha = write_pack(args.out / file, records)
        manifest["packs"].append(
            {
                "region": state.region,
                "name": state.name,
                "file": file,
                "species": len(records),
                "bytes": size,
                "sha256": sha,
                "url": f"{DOWNLOADS}/{args.release}/{file}" if args.release else None,
            }
        )
        named = sum(1 for r in records if r.get("c"))
        print(
            f"  {file}: {len(records):,} species, {named / max(1, len(records)):.0%} with an English name, {size / 1e6:.1f} MB",
            flush=True,
        )
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"Done: {args.out}", flush=True)


if __name__ == "__main__":
    from ci_report import report_failures

    report_failures(main, "Building the species packs failed")
