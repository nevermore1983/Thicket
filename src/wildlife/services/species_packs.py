"""Species packs to download: which regions are offered, and getting one safely.

docs/16-regions-plan.md, step 3. The packs are built and published by GitHub
(.github/workflows/species-packs.yml). manifest.json, in Thicket's "species-packs"
release, lists each pack with its address, size and SHA-256. A pack is installed only
if it matches, and only while "Allow online features" is on. Everything goes through
services/online.py, which only connects to its approved hosts.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

from wildlife.domain.errors import OnlineServiceError, WildlifeError
from wildlife.services import online
from wildlife.services.settings import SettingsService
from wildlife.services.species_catalogue import SpeciesCatalogue

log = logging.getLogger(__name__)
MANIFEST_URL = (
    "https://github.com/nevermore1983/WildlifeTracker/releases/download/species-packs/manifest.json"
)
FORMAT = 1  # the newest manifest format this version understands
MAX_PACK = 30 * 1024 * 1024  # the biggest state's pack is ~2 MB
Progress = Callable[[str, float], None]


class PackError(WildlifeError):
    """A species pack couldn't be fetched or installed. Nothing was changed."""


@dataclass(frozen=True, slots=True)
class Pack:
    region: str  # 'us-ca'
    name: str  # 'California'
    species: int
    bytes: int
    sha256: str
    url: str
    version: str  # the manifest's date


class SpeciesPacks:
    def __init__(
        self,
        catalogue: SpeciesCatalogue,
        settings: SettingsService,
        fetch: online.Fetch = online.fetch,
    ) -> None:
        self._catalogue, self._settings, self._fetch = catalogue, settings, fetch
        self._offered: list[Pack] | None = None

    def offered(self, refresh: bool = False) -> list[Pack]:
        """The packs Thicket can download, by name. Needs online features."""
        if self._offered is not None and not refresh:
            return self._offered
        self._need_online()
        try:
            manifest = json.loads(self._fetch(MANIFEST_URL).decode("utf-8"))
        except OnlineServiceError as exc:
            raise PackError(
                f"Couldn't get the list of species packs. {exc.user_message}", detail=str(exc)
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PackError("The list of species packs couldn't be read.", detail=str(exc)) from exc
        if not isinstance(manifest, dict) or not isinstance(manifest.get("format"), int):
            raise PackError("The list of species packs couldn't be read.")
        if manifest["format"] > FORMAT:
            raise PackError(
                "These species packs need a newer version of Thicket. Please update Thicket."
            )
        packs = []
        for p in manifest.get("packs", []):
            try:
                packs.append(
                    Pack(
                        p["region"],
                        p["name"],
                        int(p["species"]),
                        int(p["bytes"]),
                        p["sha256"],
                        p["url"],
                        manifest.get("created", ""),
                    )
                )
            except (KeyError, TypeError, ValueError):
                log.warning("Skipped a species pack the list describes badly: %r", p)
        self._offered = sorted(packs, key=lambda p: p.name)
        return self._offered

    def install(self, pack: Pack, progress: Progress = lambda s, f: None) -> int:
        """Download, check and install a pack. Safe to run on a worker thread. Returns
        the number of species in it. Raises PackError (nothing changed) if anything's
        wrong: no internet, a different file than the list says, or a damaged one."""
        self._need_online()
        progress(f"Downloading the {pack.name} species pack", 0.0)
        try:
            data = self._fetch(pack.url) if pack.bytes <= MAX_PACK else b""
        except OnlineServiceError as exc:
            raise PackError(
                f"Couldn't download the {pack.name} species pack. {exc.user_message}",
                detail=str(exc),
            ) from exc
        if len(data) != pack.bytes or hashlib.sha256(data).hexdigest() != pack.sha256:
            raise PackError(
                f"The {pack.name} species pack didn't match its checksum, so it wasn't "
                "installed. Try again later.",
                detail=f"{len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()}",
            )
        records = _records(data, pack)
        progress(f"Installing {pack.species:,} species", 0.1)
        n = self._catalogue.install_pack(
            records,
            pack.region,
            pack.name,
            pack.version,
            lambda step, f: progress(step, 0.1 + 0.9 * f),
        )
        log.info("Species pack %s (%s) installed: %s species", pack.name, pack.version, f"{n:,}")
        return n

    def _need_online(self) -> None:
        if not self._settings.current.allow_online:
            raise PackError(
                "Species packs are downloaded from the internet. Turn on "
                "“Allow online features” in Settings first."
            )


def _records(data: bytes, pack: Pack) -> list[dict]:
    """The pack's species, each checked before anything is installed."""
    try:
        records = [json.loads(line) for line in gzip.decompress(data).decode("utf-8").splitlines()]
    except (OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackError(f"The {pack.name} species pack is damaged.", detail=str(exc)) from exc
    for rec in records:
        if not (
            isinstance(rec, dict)
            and str(rec.get("k", "")).startswith("gbif:")
            and isinstance(rec.get("s"), str)
            and rec.get("r") in ("species", "subspecies")
        ):
            raise PackError(f"The {pack.name} species pack is damaged.", detail=repr(rec)[:200])
    return records
