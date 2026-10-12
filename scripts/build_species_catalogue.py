"""Build WildLife's bundled species catalogue from the UK Species Inventory.

Input:  the Natural History Museum's "UKSI Simplified Copy" workbook (.xlsx),
        downloaded by hand from https://data.nhm.ac.uk/dataset/uk-species-inventory-simplified-copy
Output: src/wildlife/resources/species/uksi_taxa.jsonl.gz  (+ catalogue_info.json)

Run:    uv run --with openpyxl python scripts/build_species_catalogue.py local_data/uksi/<file>.xlsx

The UKSI is (c) Natural History Museum, licensed CC BY 4.0. Animals, plants and fungi
(lichens included) are kept; redundant (retired) taxa are dropped. Each output line is one taxon:
  {"k": TVK, "p": parent TVK, "r": rank, "s": scientific name, "a": authority,
   "c": preferred English name, "l": [kingdom, phylum, class, order, family],
   "g": informal group, "nn": non-native?, "pr": picker priority,
   "en": [other English names], "sy": [scientific synonyms]}
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import re
import sys
import time
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "src" / "wildlife" / "resources" / "species"
COMMON_FILE = ROOT / "scripts" / "data" / "common_species.txt"
KINGDOMS = ("Animalia", "Plantae", "Fungi")
# Bump when the build rules change, so existing libraries reinstall the catalogue.
BUILD = 2

RANKS = {  # UKSI rank -> WildLife rank
    "Kingdom": "kingdom",
    "Phylum": "phylum",
    "Class": "class",
    "Order": "order",
    "Family": "family",
    "Genus": "genus",
    "Species": "species",
    "Subspecies": "subspecies",
    "Variety": "subspecies",
    "Form": "subspecies",
    "Morphotype": "subspecies",
    "Species aggregate": "species_group",
    "Species group": "species_group",
    "Species sensu lato": "species_group",
    "Microspecies": "species",
}
POPULAR = {  # informal groups most people record: these rank higher in the species picker
    "bird": 4,
    "terrestrial mammal": 4,
    "marine mammal": 3,
    "insect - butterfly": 4,
    "insect - dragonfly (Odonata)": 4,
    "reptile": 4,
    "amphibian": 4,
    "bony fish (Actinopterygii)": 2,
    "insect - moth": 2,
    "insect - orthopteran": 2,
    "insect - beetle (Coleoptera)": 1,
    "insect - hymenopteran": 1,
    "insect - true fly (Diptera)": 1,
    "spider (Araneae)": 1,
    "mollusc": 1,
    "insect - true bug (Hemiptera)": 1,
    "flowering plant": 3,
    "conifer": 2,
    "fern": 2,
    "lichen": 1,
    "fungus": 1,
    "moss": 1,
    "horsetail": 1,
}


def rank_of(t: dict, lineage: dict[str, str]) -> str:
    """WildLife rank for a UKSI taxon. Botanists and mycologists record aggregates
    ("Bramble", "Daffodil") as species, so outside animals they count as one;
    "A/B" or "A or B" pairs (and animal aggregates such as "Carrion/Hooded Crow")
    stay groups that don't count."""
    rank = RANKS.get(t["rank"], "other")
    name = t["taxon_name"] or ""
    if (
        rank == "species_group"
        and t["rank"] in ("Species aggregate", "Species sensu lato")
        and lineage.get("Kingdom") != "Animalia"
        and "/" not in name
        and " or " not in name
    ):
        return "species"
    return rank


def read_sheet(wb, name: str):
    rows = wb[name].iter_rows(values_only=True)
    header = [h.lower() for h in next(rows)]
    for row in rows:
        yield dict(zip(header, row, strict=False))


def clean(text: str | None) -> str | None:
    if text is None:
        return None
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text or None


def build(xlsx: Path) -> dict:
    t0 = time.time()
    wb = openpyxl.load_workbook(xlsx, read_only=True)
    taxa = {r["organism_key"]: r for r in read_sheet(wb, "TAXA")}
    print(f"read {len(taxa):,} taxa ({time.time() - t0:.0f} s)")

    def ancestors(key: str):
        seen = 0
        while key in taxa and seen < 80:
            yield taxa[key]
            key, seen = taxa[key]["parent_key"], seen + 1

    def lineage_of(key: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for t in ancestors(key):
            out.setdefault(t["rank"], clean(t["taxon_name"]))
        return out

    keep: dict[str, dict] = {}  # TVK -> output record
    org_to_tvk: dict[str, str] = {}
    for key, t in taxa.items():
        if t["redundant_flag"] == "Y":
            continue
        lin = lineage_of(key)
        if lin.get("Kingdom") not in KINGDOMS:
            continue
        tvk = t["taxon_version_key"]
        org_to_tvk[key] = tvk
        keep[tvk] = {
            "k": tvk,
            "_org": key,
            "r": rank_of(t, lin),
            "s": clean(t["taxon_name"]),
            "a": clean(t["taxon_authority"]),
            "l": [lin.get(r) for r in ("Kingdom", "Phylum", "Class", "Order", "Family")],
            "g": clean(t["informal_group"]),
            "nn": t["non_native_flag"] == "Y",
            "_agg": t["rank"] in ("Species aggregate", "Species sensu lato"),
        }
    # An aggregate named exactly like a species (Narcissus pseudonarcissus agg. beside
    # the species itself) stays a group, so the two never count twice.
    true_species = {r["s"] for r in keep.values() if r["r"] == "species" and not r["_agg"]}
    for rec in keep.values():
        if rec.pop("_agg") and rec["r"] == "species" and rec["s"] in true_species:
            rec["r"] = "species_group"
    # Parent = nearest kept ancestor (skips any dropped/redundant levels)
    for rec in keep.values():
        parent = None
        for anc in list(ancestors(rec["_org"]))[1:]:
            if anc["organism_key"] in org_to_tvk:
                parent = org_to_tvk[anc["organism_key"]]
                break
        rec["p"] = parent
    print(f"kept {len(keep):,} taxa ({time.time() - t0:.0f} s)")

    # Best English name per taxon: recommended first, then well-formed synonyms
    # (e.g. Eristalis tenax has no recommended name, but "Drone Fly" is the usual one).
    status_rank = {"R": 0, "S": 1, "U": 2}
    form_rank = {"W": 0, "I": 1, "U": 2}
    best_en: dict[str, tuple[tuple[int, int, int], str]] = {}
    preferred_count = 0
    other_en: dict[str, set[str]] = collections.defaultdict(set)
    synonyms: dict[str, set[str]] = collections.defaultdict(set)
    for n in read_sheet(wb, "NAMES"):
        tvk = n["recommended_taxon_version_key"]
        if tvk not in keep or n["deprecated_date"]:
            continue
        name = clean(n["taxon_name"])
        if not name:
            continue
        if n["language"] == "en":
            other_en[tvk].add(name)
            score = (
                status_rank.get(n["name_status"], 3),
                form_rank.get(n["name_form"], 3),
                len(name),
            )
            if score[1] == 0 and (tvk not in best_en or score < best_en[tvk][0]):
                best_en[tvk] = (score, name)
        elif n["language"] == "la" and n["name_status"] == "S" and n["name_form"] == "W":
            synonyms[tvk].add(name)
    preferred = {tvk: name for tvk, (_, name) in best_en.items()}
    preferred_count = sum(1 for score, _ in best_en.values() if score[0] == 0)
    # A species with no English name of its own takes its nominate variety's or
    # subspecies' ("Fly Agaric" is filed under Amanita muscaria var. muscaria).
    inherited: dict[str, str] = {}
    for tvk, rec in keep.items():
        parent = keep.get(rec["p"]) if rec["p"] else None
        if (
            tvk in preferred
            and rec["r"] == "subspecies"
            and parent is not None
            and parent["r"] == "species"
            and parent["k"] not in preferred
            and rec["s"].split()[-1] == parent["s"].split()[-1]
        ):
            inherited[parent["k"]] = preferred[tvk]
    preferred.update(inherited)
    print(f"English names taken from a nominate variety/subspecies: {len(inherited):,}")
    print(
        f"English names: {preferred_count:,} recommended + {len(preferred) - preferred_count:,} from synonyms"
    )
    common_list = {
        line.strip().lower()
        for line in COMMON_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    boosted: set[str] = set()
    for tvk, rec in keep.items():
        common = preferred.get(tvk) or None  # only the recommended English name is promoted
        rec["c"] = common
        rec["en"] = sorted(other_en.get(tvk, set()) - {common, rec["s"]})
        rec["sy"] = sorted(synonyms.get(tvk, set()) - {rec["s"]})
        score = POPULAR.get(rec["g"] or "", 0)
        if common:
            score += 2
        if rec["r"] in ("species", "subspecies") and common and common.lower() in common_list:
            score += 4
            boosted.add(common.lower())
        if rec["r"] in ("subspecies", "species_group", "other", "genus"):
            score -= 1
        if rec["r"] in ("family", "order", "class", "phylum", "kingdom"):
            score -= 3  # groups ("Finches") shouldn't outrank actual species
        rec["pr"] = max(score, 0)
    missing = sorted(common_list - boosted)
    print(f"names attached ({time.time() - t0:.0f} s); preferred English names: {len(preferred):,}")
    print(f"common-species boost: {len(boosted)} matched; not found in UKSI: {missing or 'none'}")
    return keep


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx", type=Path)
    args = parser.parse_args()
    version = re.search(r"(\d{8}[a-z]?)", args.xlsx.name)
    keep = build(args.xlsx)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("uksi_*.jsonl.gz"):
        old.unlink()
    out = OUT_DIR / "uksi_taxa.jsonl.gz"
    with gzip.open(out, "wt", encoding="utf-8", compresslevel=9) as f:
        for rec in sorted(keep.values(), key=lambda r: r["k"]):
            rec.pop("_org")
            f.write(
                json.dumps(
                    {k: v for k, v in rec.items() if v not in (None, [], False)},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
    ranks = collections.Counter(r["r"] for r in keep.values())
    info = {
        "source": "UK Species Inventory (UKSI) Simplified Copy, Natural History Museum",
        "source_url": "https://data.nhm.ac.uk/dataset/uk-species-inventory-simplified-copy",
        "licence": "CC BY 4.0",
        "attribution": "Species names from the UK Species Inventory, (c) Natural History Museum, CC BY 4.0",
        "version": f"{version[1] if version else args.xlsx.stem}-{BUILD}",
        "kingdoms": list(KINGDOMS),
        "taxa": len(keep),
        "species": ranks["species"],
        "with_english_name": sum(1 for r in keep.values() if r["c"]),
        "ranks": dict(ranks.most_common()),
    }
    (OUT_DIR / "catalogue_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(json.dumps(info, indent=2))
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
