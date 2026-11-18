"""Build species packs from GBIF: one per US state and one per European country
(docs/16-regions-plan.md, docs/23-europe-packs-plan.md).

    uv run python scripts/build_species_packs.py --backbone local_data/gbif/backbone.zip
    uv run python scripts/build_species_packs.py --backbone ... --regions fr,es,ie,us-oh

For each region:
1. GBIF's occurrence API lists every species recorded there (a US state by GADM's
   boundaries, a country by GBIF's country code) with its number of records; species
   with fewer than --min-records (5) are left out (mostly misidentifications and garden
   escapes). Zoo animals, garden plants (living specimens) and fossils don't count.
2. Names, authors and family tree come from the GBIF Backbone Taxonomy file (read once,
   only the species needed are kept). The English name is chosen by choose_names():
   for the US as US birders and naturalists use them; for Europe the UK list's name
   first (Thicket is in British English), then names used in Britain or Ireland.
   European packs also carry names in the country's languages ("ln"), for search.
Output (in --out, default build/packs): fr.jsonl.gz, us-ca.jsonl.gz ... in the same
record format as the UK list (so Thicket installs them with the same code), and two
lists of them with each pack's species count, size and SHA-256, which Thicket checks
before installing: manifest-2.json (every pack, read by Thicket 1.6 and later) and
manifest.json (the US states only, for older versions, which don't know Europe).
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
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wildlife.domain.regions import (  # noqa: E402  (one list of regions, shared with the app)
    EUROPE,
    POSTAL_CODES,
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


US_NAMES = NameStyle(BIRD_SOURCES, ("US",), home_first=False)
EUROPE_NAMES = NameStyle(EUROPE_BIRD_SOURCES, ("GB", "IE"), home_first=True)


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
        if (name := tidy(c.name)) and name.lower() not in {n.lower() for n in names}:
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


def uk_names(path: Path | None = None) -> dict[tuple[str, str], str]:
    """The UK list's common names (the one built into Thicket), by (scientific name,
    kingdom): a species in it keeps its UK name in a European pack."""
    path = path or ROOT / "src" / "wildlife" / "resources" / "species" / "uksi_taxa.jsonl.gz"
    names: dict[tuple[str, str], str] = {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("r") == "species" and rec.get("c"):
                kingdom = ((rec.get("l") or [None])[0] or "").lower()
                names.setdefault((rec["s"].lower(), kingdom), rec["c"])
    return names


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
    """A region a pack is built for: a US state or a European country."""

    region: str  # 'us-ca', 'fr'
    name: str  # 'California', 'France'
    filters: tuple[tuple[str, str], ...]  # GBIF's occurrence search, for this region
    group: str  # US or EUROPE
    languages: tuple[str, ...] = ()

    @property
    def style(self) -> NameStyle:
        return EUROPE_NAMES if self.group == EUROPE else US_NAMES


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


def european_countries() -> list[Area]:
    """The countries of Europe Thicket offers (domain/regions.py), by GBIF's country code."""
    return [
        Area(r.code, r.name, (("country", r.code.upper()),), EUROPE, r.languages)
        for r in REGIONS.values()
        if r.group == EUROPE
    ]


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
    """Every region, or those asked for: region codes ('fr,es,us-oh'), 'europe' or 'us'."""
    if not wanted:
        return european_countries() + us_states()
    asked = {w.strip().lower() for w in wanted.split(",") if w.strip()}
    areas: list[Area] = []
    if asked & {"europe"} or any(not a.startswith("us-") and a != "us" for a in asked):
        areas += european_countries()
    if asked & {"us"} or any(a.startswith("us-") for a in asked):
        areas += us_states()
    if asked - {"europe", "us"}:
        areas = [
            a
            for a in areas
            if a.region in asked
            or ("europe" in asked and a.group == EUROPE)
            or ("us" in asked and a.group == US)
        ]
    unknown = asked - {"europe", "us"} - {a.region for a in areas}
    if unknown:
        raise SystemExit(f"Not a region Thicket knows: {', '.join(sorted(unknown))}")
    return areas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backbone", type=Path, required=True, help="GBIF backbone.zip")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "packs")
    parser.add_argument(
        "--regions", help="only these: region codes (fr,es,us-oh), europe or us (default: all)"
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
    uk = uk_names() if any(a.group == EUROPE for a in areas) else {}

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
            uk_name = None
            if area.group == EUROPE:
                uk_name = uk.get((canonical.lower(), (taxon.get("kingdom") or "").lower()))
            english = {c.name for c in names.get(k, [])} | ({uk_name} if uk_name else set())
            ln = local_names(local.get(k, {}), area.languages, english) or None
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
    """manifest-2.json lists every pack (Thicket 1.6 and later); manifest.json only the
    US states, for older versions, which would take a European country for the UK."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest-2.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    older = {**manifest, "packs": [p for p in manifest["packs"] if p["region"].startswith("us-")]}
    (out / "manifest.json").write_text(json.dumps(older, indent=1), encoding="utf-8")


if __name__ == "__main__":
    from ci_report import report_failures

    report_failures(main, "Building the species packs failed")
