"""The species catalogue: installing the bundled UK list and searching it."""

from __future__ import annotations

import gzip
import json
import logging
import re
import time
from collections.abc import Callable
from importlib import resources
from pathlib import Path

from wildlife.data.db import Database
from wildlife.data.repositories import taxa as repo
from wildlife.domain.errors import ValidationError
from wildlife.domain.models import Category, Taxon, TaxonMatch
from wildlife.services.events import EventHub

log = logging.getLogger(__name__)
Progress = Callable[[str, float], None]
# "Emberiza bruniceps", "Larus michahellis atlantis", "Anas platyrhynchos × acuta"
_SCIENTIFIC = re.compile(r"^[A-Za-z][a-z]+(?: (?:[a-z][a-z.-]+|×|x))+$")


def bundled_catalogue() -> tuple[Path, dict]:
    folder = resources.files("wildlife.resources.species")
    info = json.loads(folder.joinpath("catalogue_info.json").read_text(encoding="utf-8"))
    return Path(str(folder.joinpath("uksi_taxa.jsonl.gz"))), info


def read_records(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


class SpeciesCatalogue:
    def __init__(self, db: Database, events: EventHub) -> None:
        self._db, self._events = db, events
        self._categories: list[Category] | None = None

    # ---- installing ---------------------------------------------------------
    def installed_version(self) -> str | None:
        with self._db.connection() as conn:
            return repo.get_meta(conn, "catalogue_version")

    def needs_install(self) -> bool:
        _, info = bundled_catalogue()
        return self.installed_version() != info["version"]

    def install(self, progress: Progress = lambda s, f: None, path: Path | None = None) -> int:
        """Install (or update to) the bundled catalogue. Safe to run on a worker thread."""
        bundled_path, info = bundled_catalogue()
        path = path or bundled_path
        started = time.perf_counter()
        progress("Reading the species list", 0.0)
        records = read_records(path)
        version = info["version"] if path == bundled_path else path.stem
        with self._db.transaction() as conn:
            n = repo.install_catalogue(conn, records, progress, version)
            repo.set_meta(conn, "catalogue_version", version)
        log.info("Installed %s taxa in %.1f s", f"{n:,}", time.perf_counter() - started)
        self._events.publish("taxa")
        return n

    # ---- species packs and regions (docs/16-regions-plan.md) ------------------
    def install_pack(
        self,
        records: list[dict],
        region: str,
        name: str,
        version: str,
        progress: Progress = lambda s, f: None,
    ) -> int:
        """Add a region's species pack (from GBIF). Species already in your list are
        linked, never copied; nothing is removed. Safe to run on a worker thread."""
        started = time.perf_counter()
        with self._db.transaction() as conn:
            n = repo.install_pack(conn, records, region, name, "gbif", version, progress)
        log.info(
            "Installed the %s pack: %s species in %.1f s",
            name,
            f"{n:,}",
            time.perf_counter() - started,
        )
        self._events.publish("taxa")
        return n

    def region(self) -> str:
        """The region whose names and suggestion order are shown ('uk', 'us-ca'...)."""
        with self._db.connection() as conn:
            return repo.current_region(conn)

    def set_region(self, region: str) -> None:
        with self._db.transaction() as conn:
            repo.apply_region(conn, region)
        self._events.publish("taxa")

    def packs(self) -> list[dict]:
        """The species packs installed: region, name, source, version, taxa, installed_at."""
        with self._db.connection() as conn:
            return [dict(r) for r in repo.packs(conn)]

    # ---- your own species ---------------------------------------------------------
    def add_species(
        self, scientific_name: str, common_name: str | None, category_id: int | None = None
    ) -> Taxon:
        """Add a species that isn't in any list (an escape, a new arrival, one from a
        region whose pack you haven't added). Raises ValidationError if the name is
        missing, doesn't look like a scientific name, or is in the list already."""
        scientific = " ".join(scientific_name.split())
        common = " ".join((common_name or "").split()) or None
        if not scientific:
            raise ValidationError({"scientific_name": "The scientific name is needed."})
        if not _SCIENTIFIC.match(scientific):
            raise ValidationError(
                {"scientific_name": "Write it as genus and species, like Emberiza bruniceps."}
            )
        scientific = scientific[0].upper() + scientific[1:]
        with self._db.transaction() as conn:
            if (have := repo.same_name(conn, scientific)) is not None:
                raise ValidationError(
                    {
                        "scientific_name": f"That's in the list already, as "
                        f"{have.common_name or have.scientific_name}. Search for it instead."
                    }
                )
            if category_id is None:
                relative = repo.genus_relative(conn, scientific)
                category_id = relative["category_id"] if relative else self._fallback_id()
            taxon_id = repo.add_own_species(conn, scientific, common, category_id)
        log.info("Added a species of your own: %s", scientific)
        self._events.publish("taxa", (taxon_id,))
        return self.get(taxon_id)

    def suggested_category(self, scientific_name: str) -> int | None:
        """The group of a known species in the same genus, if there is one."""
        with self._db.connection() as conn:
            relative = repo.genus_relative(conn, " ".join(scientific_name.split()))
        return relative["category_id"] if relative else None

    def _fallback_id(self) -> int:
        return next(c.id for c in self.categories() if c.is_fallback)

    # ---- reading ------------------------------------------------------------
    def search(self, text: str, limit: int = 20) -> list[TaxonMatch]:
        with self._db.connection() as conn:
            return repo.search(conn, text, limit)

    def get(self, taxon_id: int) -> Taxon | None:
        with self._db.connection() as conn:
            return repo.get(conn, taxon_id)

    def categories(self) -> list[Category]:
        if self._categories is None:
            with self._db.connection() as conn:
                self._categories = repo.categories(conn)
        return self._categories

    def category(self, category_id: int) -> Category:
        return next(c for c in self.categories() if c.id == category_id)
