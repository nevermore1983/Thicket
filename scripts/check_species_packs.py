"""Check built species packs the way WildLife will use them, before they're published.

    uv run python scripts/check_species_packs.py build/packs

Each pack is checked against manifest.json (size, SHA-256), then installed into a fresh
WildLife database with the app's own code (on top of the UK list, as for a UK user who
adds a state). Reports, per pack, how many species WildLife couldn't sort into one of
its categories ("Other"), how many have no English name, how many were linked to a UK
species instead of being added, and how long installing took. Exits 1 if anything is
wrong, so the workflow publishes nothing.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wildlife.data.migrate import migrate  # noqa: E402
from wildlife.data.repositories import taxa  # noqa: E402
from wildlife.services.species_catalogue import bundled_catalogue, read_records  # noqa: E402

MAX_OTHER = 0.05  # at most 5% of a pack's species in "Other"
MIN_SPECIES = 500  # a state with fewer is suspicious (an API or boundary problem)


def check(folder: Path) -> list[str]:
    """Problems found (none: all good)."""
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    problems = []
    work = Path(tempfile.mkdtemp(prefix="wildlife-pack-check-"))
    template = work / "uk.db"
    _uk_library(template)  # once; each pack is installed into a copy of it
    for pack in manifest["packs"]:
        data = (folder / pack["file"]).read_bytes()
        if len(data) != pack["bytes"] or hashlib.sha256(data).hexdigest() != pack["sha256"]:
            problems.append(f"{pack['file']}: doesn't match manifest.json")
            continue
        records = [json.loads(line) for line in gzip.decompress(data).decode("utf-8").splitlines()]
        if len(records) != pack["species"] or len(records) < MIN_SPECIES:
            problems.append(f"{pack['file']}: {len(records)} species")
        library = work / f"{pack['region']}.db"
        shutil.copy(template, library)
        conn = sqlite3.connect(library, autocommit=True)
        try:
            conn.execute("BEGIN")
            before = conn.execute("SELECT COUNT(*) FROM taxon").fetchone()[0]
            started = time.perf_counter()
            taxa.install_pack(
                conn, records, pack["region"], pack["name"], "gbif", manifest["created"]
            )
            seconds = time.perf_counter() - started
            conn.execute("COMMIT")
            added = conn.execute("SELECT COUNT(*) FROM taxon").fetchone()[0] - before
            other = conn.execute(
                "SELECT COUNT(*) FROM taxon_region r JOIN taxon t ON t.id = r.taxon_id "
                "JOIN category c ON c.id = t.category_id WHERE r.region = ? AND c.is_fallback = 1",
                (pack["region"],),
            ).fetchone()[0]
        finally:
            conn.close()
        library.unlink()
        unnamed = sum(1 for r in records if not r.get("c"))
        n = len(records)
        print(
            f"{pack['name']:<22} {n:>7,} species  {added:>7,} new, {n - added:>6,} linked to UK ones  "
            f"other {other / n:5.1%}  no English name {unnamed / n:5.1%}  installed in {seconds:4.1f} s"
        )
        if other / n > MAX_OTHER:
            problems.append(f"{pack['file']}: {other / n:.1%} of species in 'Other'")
    shutil.rmtree(work, ignore_errors=True)
    return problems


def _uk_library(path: Path) -> None:
    """A WildLife database with the UK list installed, as a UK user has."""
    uk_path, uk_info = bundled_catalogue()
    conn = sqlite3.connect(path, autocommit=True)
    try:
        migrate(conn)
        conn.execute("BEGIN")
        taxa.install_catalogue(conn, read_records(uk_path), version=uk_info["version"])
        conn.execute("COMMIT")
    finally:
        conn.close()


def main() -> int:
    problems = check(Path(sys.argv[1]))
    for p in problems:
        print(f"PROBLEM: {p}")
    print("Species packs: " + ("FAILED" if problems else "OK"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
