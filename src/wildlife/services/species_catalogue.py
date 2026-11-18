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
from wildlife.domain.errors import ConflictError, ValidationError
from wildlife.domain.models import Category, Taxon, TaxonMatch
from wildlife.services.events import EventHub

log = logging.getLogger(__name__)
Progress = Callable[[str, float], None]
_GENUS = re.compile(r"^[A-Z][a-z]+$")
_EPITHET = re.compile(r"^[a-z][a-z-]+$")  # 'bruniceps', 'novae-angliae'; not 'sp.'
_RANK_WORDS = {"subsp.", "ssp.", "var.", "f."}
_CROSS = {"×", "x"}


def already_listed(have: Taxon) -> str:
    """'That's in the list already, as Blue Tit (Cyanistes caeruleus). ...'"""
    if have.common_name:
        what = f"{have.common_name} ({have.scientific_name})"
    else:
        what = have.scientific_name
    return f"That's in the list already, as {what}. Search for it instead."


def looks_scientific(name: str) -> bool:
    """A species' scientific name: 'Emberiza bruniceps', 'Larus michahellis atlantis',
    'Dactylorhiza x grandis', 'Anas platyrhynchos × Anas acuta'. Not just a genus,
    and not 'Larus sp.' (that's a genus, not a species)."""
    words = name.split()
    if len(words) < 2 or not _GENUS.match(words[0][:1].upper() + words[0][1:]):
        return False
    after_cross = False
    for word in words[1:]:
        if word in _CROSS:
            after_cross = True
            continue
        ok = _EPITHET.match(word) or word in _RANK_WORDS or (after_cross and _GENUS.match(word))
        if not ok:
            return False
        after_cross = False
    return words[-1] not in _CROSS and words[-1] not in _RANK_WORDS


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

    def link_renamed_once(self) -> int:
        """Merge the second copies 1.6.0's European packs could add (Sylvia curruca next
        to the UK list's Curruca curruca): once, on the first start of 1.6.1."""
        with self._db.transaction() as conn:
            if repo.get_meta(conn, "renamed_linked"):
                return 0
            merged = repo.link_renamed(conn)
            if merged:
                repo.apply_region(conn, repo.current_region(conn))
            repo.set_meta(conn, "renamed_linked", "1")
        if merged:
            log.info("Merged %d species a pack had added twice under another name", merged)
            self._events.publish("taxa")
        return merged

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
        scientific, common = self._checked_names(scientific_name, common_name)
        with self._db.transaction() as conn:
            if (have := repo.same_name(conn, scientific)) is not None:
                raise ValidationError({"scientific_name": already_listed(have)})
            if category_id is None:
                relative = repo.genus_relative(conn, scientific)
                category_id = relative["category_id"] if relative else self._fallback_id()
            taxon_id = repo.add_own_species(conn, scientific, common, category_id)
        log.info("Added a species of your own: %s", scientific)
        self._events.publish("taxa", (taxon_id,))
        return self.get(taxon_id)

    def own_species(self) -> list[tuple[Taxon, int]]:
        """Your own species, with how many sightings use each (recycle bin included)."""
        with self._db.connection() as conn:
            return repo.own_species(conn)

    def rename_species(
        self, taxon_id: int, scientific_name: str, common_name: str | None, category_id: int
    ) -> Taxon:
        """Correct a species of your own: its names and group. Its sightings follow."""
        scientific, common = self._checked_names(scientific_name, common_name)
        with self._db.transaction() as conn:
            have = repo.same_name(conn, scientific)
            if have is not None and have.id != taxon_id:
                raise ValidationError({"scientific_name": already_listed(have)})
            repo.rename_own_species(conn, taxon_id, scientific, common, category_id)
        self._events.publish("taxa", (taxon_id,))
        return self.get(taxon_id)

    def remove_species(self, taxon_id: int) -> None:
        """Remove a species of your own, if no sighting uses it (recycle bin included)."""
        uses = dict((t.id, n) for t, n in self.own_species()).get(taxon_id)
        if uses is None:
            raise ConflictError("Only a species you added yourself can be removed.")
        if uses:
            raise ConflictError(
                f"{uses:,} sighting{'s use' if uses != 1 else ' uses'} this species, "
                "including any in the recycle bin. Change their species first."
            )
        with self._db.transaction() as conn:
            repo.remove_own_species(conn, taxon_id)
        self._events.publish("taxa", (taxon_id,))

    @staticmethod
    def _checked_names(scientific_name: str, common_name: str | None) -> tuple[str, str | None]:
        scientific = " ".join(scientific_name.split())
        common = " ".join((common_name or "").split()) or None
        if not scientific:
            raise ValidationError({"scientific_name": "The scientific name is needed."})
        if not looks_scientific(scientific):
            raise ValidationError(
                {"scientific_name": "Write it as genus and species, like Emberiza bruniceps."}
            )
        return scientific[0].upper() + scientific[1:], common

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
