"""Spike 3: what does the real UK Species Inventory look like for animals?

Source: UKSI as published on GBIF (dataset dbaa27eb-29e7-4cbb-8eab-3f689cfce116,
CC BY 4.0, Natural History Museum). The NBN registry download refused
automated requests (HTTP 403), so this uses GBIF's public API instead.

Downloads every ACCEPTED animal name (with English common names), saves it to
spikes/uksi/output/uksi_animals.json, and prints what we learn about ranks,
classes, common names and size.

Run:  uv run python spikes/uksi/fetch_uksi_animals.py
"""

import collections
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

DS = "dbaa27eb-29e7-4cbb-8eab-3f689cfce116"
ANIMALIA = 180120333
OUT = Path(__file__).parent / "output"
UA = {"User-Agent": "WildLife-dev/0.1 (personal wildlife journal; species list import test)"}
KEEP = ("key", "taxonID", "scientificName", "canonicalName", "authorship", "rank", "parentKey",
        "kingdom", "phylum", "class", "order", "family", "genus")


def get(**query):
    url = "https://api.gbif.org/v1/species/search?" + urllib.parse.urlencode(query, doseq=True)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return json.load(r)
        except OSError as exc:  # network hiccup: wait and retry
            print(f"  retry {attempt + 1}: {exc}")
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"failed: {url}")


def fetch() -> list[dict]:
    """Download page by page, saving each page so an interrupted run can resume."""
    cache = OUT / "uksi_animals.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    partial = OUT / "partial.jsonl"
    rows = [json.loads(line) for line in partial.read_text(encoding="utf-8").splitlines()] if partial.exists() else []
    offset, t0 = len(rows) // 1000 * 1000, time.time()
    rows = rows[:offset]  # drop any half-written page
    with partial.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        while True:
            page = get(datasetKey=DS, highertaxonKey=ANIMALIA, status="ACCEPTED", limit=1000, offset=offset)
            for r in page["results"]:
                row = {k: r.get(k) for k in KEEP}
                row["english"] = sorted({v["vernacularName"] for v in r.get("vernacularNames", [])
                                         if v.get("language") in ("eng", "en", None)})
                rows.append(row)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            offset += 1000
            print(f"  {len(rows):>6,} / {page['count']:,}  ({time.time() - t0:.0f} s)", flush=True)
            if page["endOfRecords"]:
                break
            time.sleep(0.3)  # be polite to a free public service
    cache.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    partial.unlink()
    return rows


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = fetch()
    ranks = collections.Counter(r["rank"] for r in rows)
    print(f"Accepted animal names: {len(rows):,}")
    print("By rank:", ranks.most_common(12))
    sp = [r for r in rows if r["rank"] in ("SPECIES", "SUBSPECIES", "SPECIES_AGGREGATE")]
    named = [r for r in sp if r["english"]]
    print(f"Species/subspecies/aggregates: {len(sp):,}; with an English name: {len(named):,} "
          f"({100 * len(named) / len(sp):.0f}%)")
    multi = [r for r in named if len(r["english"]) > 1]
    print(f"  with more than one English name: {len(multi):,}  e.g. {multi[0]['canonicalName']}: {multi[0]['english'][:4]}")
    classes = collections.Counter(r["class"] for r in sp)
    print("Species per class (top 20):", classes.most_common(20))
    no_class = sum(1 for r in sp if not r["class"])
    print(f"Species with no class in their lineage: {no_class:,}")

    by_name = {}
    for r in sp:
        for n in r["english"]:
            by_name.setdefault(n.lower(), []).append(r)
    for test in ["robin", "common darter", "grass snake", "brown trout", "red fox", "garden spider",
                 "seven-spot ladybird", "pied wagtail", "peacock", "common frog", "red admiral"]:
        hits = by_name.get(test, [])
        print(f"  '{test}': " + ("; ".join(f"{h['canonicalName']} [{h['rank']}] class={h['class']} order={h['order']} "
                                            f"TVK={h['taxonID']}" for h in hits[:2]) or "NOT FOUND"))

    # How big would a bundled catalogue be? (taxa + names + trigram search index)
    db_path = OUT / "catalogue_test.db"
    db_path.unlink(missing_ok=True)
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE taxon (id INTEGER PRIMARY KEY, tvk TEXT, sci TEXT, common TEXT, rank TEXT, "
                "parent INTEGER, kingdom TEXT, phylum TEXT, class TEXT, ord TEXT, family TEXT)")
    con.execute("CREATE TABLE name (taxon_id INTEGER, name TEXT)")
    con.execute("CREATE VIRTUAL TABLE name_fts USING fts5(name, content='name', tokenize='trigram remove_diacritics 1')")
    for r in rows:
        con.execute("INSERT INTO taxon VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (r["key"], r["taxonID"], r["canonicalName"], (r["english"] or [None])[0], r["rank"],
                     r["parentKey"], r["kingdom"], r["phylum"], r["class"], r["order"], r["family"]))
        for n in {r["canonicalName"], *r["english"]} - {None}:
            con.execute("INSERT INTO name VALUES (?,?)", (r["key"], n))
    con.execute("INSERT INTO name_fts(name_fts) VALUES ('rebuild')")
    con.commit()
    con.execute("VACUUM")
    con.close()
    print(f"Test catalogue database: {db_path.stat().st_size / 1e6:.1f} MB "
          f"(JSON source {(OUT / 'uksi_animals.json').stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
