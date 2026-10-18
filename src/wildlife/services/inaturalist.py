"""Importing observations exported from iNaturalist.

The file is read into ordinary import records (see `domain.inaturalist`) and goes
through the shared import pipeline (`services.importer`): preview, then import as
one batch that can be undone. Each record keeps its iNaturalist id, so importing a
newer export later only adds what's new and updates what changed there.

Photos are a separate, optional step (`fetch_photos`) because it needs the internet.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from wildlife.config.paths import DataPaths
from wildlife.data.db import Database
from wildlife.data.repositories import imports as repo
from wildlife.data.repositories import photos as photos_repo
from wildlife.domain.dates import local_clock
from wildlife.domain.errors import OnlineServiceError
from wildlife.domain.inaturalist import SOURCE, read_file
from wildlife.services import online
from wildlife.services.events import EventHub
from wildlife.services.importer import (  # noqa: F401  (re-exported for callers)
    ADD,
    SAME,
    SKIP,
    UPDATE,
    ImportPlan,
    ImportResult,
    PlannedRow,
    RecordImporter,
    name_variants,
)
from wildlife.services.photos import PhotoService
from wildlife.services.settings import SettingsService

log = logging.getLogger(__name__)

_PHOTO_ID = re.compile(r"/photos/(\d+)/")
_PHOTO_SIZE = re.compile(r"/(square|thumb|small|medium|large|original)\.")
API = "https://api.inaturalist.org/v1/observations?id={}&per_page={}"
API_BATCH = 100


@dataclass
class PhotoFetchResult:
    fetched: int = 0
    already: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)  # (observation, reason)
    cancelled: bool = False

    def describe(self) -> str:
        parts = [f"{self.fetched:,} photo{'s' if self.fetched != 1 else ''} added"]
        if self.already:
            parts.append(f"{self.already:,} already here")
        if self.failed:
            parts.append(f"{len(self.failed):,} couldn't be fetched")
        return " · ".join(parts)


class InaturalistImporter(RecordImporter):
    def __init__(
        self,
        paths: DataPaths,
        db: Database,
        events: EventHub,
        settings: SettingsService,
        photos: PhotoService,
        today: Callable[[], date] = date.today,
        fetch: online.Fetch = online.fetch,
        pause: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(paths, db, events, settings, photos, today)
        self._fetch, self._pause = fetch, pause

    def preview(
        self, path: Path, progress: Callable[[int, int], None] = lambda d, t: None
    ) -> ImportPlan:
        records = read_file(path, local_clock(self.region()))  # UTC times: the region's clock
        return self.preview_records(records, path.name, SOURCE, progress)

    # ---- photos (optional, online) ---------------------------------------------------
    def fetch_photos(
        self,
        result: ImportResult,
        progress: Callable[[int, int], None] = lambda d, t: None,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> PhotoFetchResult:
        """Download the photos of the sightings just imported that have none yet."""
        if not self._settings.current.allow_online:
            raise OnlineServiceError(
                "Photos need the internet. Turn on “Allow online features” in Settings first."
            )
        out = PhotoFetchResult()
        with self._db.connection() as conn:
            waiting = repo.sightings_without_photos(conn, SOURCE)
        mine = set(result.added) | set(result.updated)
        wanted = {src: sid for src, sid in waiting.items() if sid in mine}
        if not wanted:
            return out
        urls = self._photo_urls(list(wanted), result, wanted)
        total = sum(len(v) for v in urls.values())
        done = 0
        changed: list[int] = []  # sightings given photos, announced in batches

        def announce() -> None:
            if changed:
                self._events.publish("sightings", tuple(changed))
                changed.clear()

        with tempfile.TemporaryDirectory(dir=self._paths.root, prefix="inat-") as tmp:
            for source_id, photos in urls.items():
                attached: list[int] = []
                for photo_id, url in photos:
                    if cancelled():
                        out.cancelled = True
                        break
                    progress(done, total)
                    done += 1
                    try:
                        pid, new = self._one_photo(photo_id, url, Path(tmp))
                    except OnlineServiceError as exc:
                        out.failed.append((source_id, exc.user_message))
                        continue
                    attached.append(pid)
                    if new:
                        out.fetched += 1
                        self._pause(0.5)  # be gentle with iNaturalist's servers
                    else:
                        out.already += 1
                if attached:
                    with self._db.transaction() as conn:
                        photos_repo.attach(conn, wanted[source_id], attached)
                    changed.append(wanted[source_id])
                    if len(changed) >= 25:  # not once per photo: open pages would redraw constantly
                        announce()
                if out.cancelled:
                    break
        announce()
        progress(total, total)
        return out

    def _photo_urls(
        self, source_ids: list[str], result: ImportResult, wanted: dict[str, int]
    ) -> dict[str, list[tuple[str, str]]]:
        """Every photo of each observation (iNaturalist's API), or just the first one
        from the export file if the API can't be reached."""
        urls: dict[str, list[tuple[str, str]]] = {}
        for start in range(0, len(source_ids), API_BATCH):
            chunk = source_ids[start : start + API_BATCH]
            try:
                data = json.loads(self._fetch(API.format(",".join(chunk), len(chunk))))
                for obs in data.get("results", []):
                    photos = [
                        (str(p["id"]), p["url"])
                        for p in obs.get("photos", [])
                        if p.get("id") and p.get("url")
                    ]
                    if photos:
                        urls[str(obs["id"])] = photos
            except (OnlineServiceError, ValueError, KeyError, TypeError) as exc:
                log.warning("iNaturalist API unavailable, using the export's photo links: %s", exc)
            self._pause(1.0)
        for source_id in source_ids:
            first = result.image_urls.get(wanted[source_id])
            if source_id not in urls and first and (m := _PHOTO_ID.search(first)):
                urls[source_id] = [(m[1], first)]
        return urls

    def _one_photo(self, photo_id: str, url: str, tmp: Path) -> tuple[int, bool]:
        """(library photo id, newly downloaded?). A photo fetched before is reused."""
        with self._db.connection() as conn:
            known = repo.photo_by_source(conn, SOURCE, photo_id)
        if known is not None:
            with self._db.transaction() as conn:
                photos_repo.restore(conn, [known])
            return known, False
        data, error = None, None
        for size in ("original", "large", "medium"):
            try:
                data = self._fetch(_PHOTO_SIZE.sub(f"/{size}.", url, count=1))
                break
            except OnlineServiceError as exc:
                error = exc
        if data is None:
            raise error or OnlineServiceError("The photo couldn't be fetched.")
        suffix = Path(url.split("?")[0]).suffix.lower() or ".jpg"
        file = tmp / f"inaturalist-{photo_id}{suffix}"
        file.write_bytes(data)
        summary = self._photos.import_files([file])
        file.unlink(missing_ok=True)
        if not summary.photos:
            reason = summary.failed[0][1] if summary.failed else "Not a photo"
            raise OnlineServiceError(f"The photo couldn't be read ({reason}).")
        photo = summary.photos[0]
        with self._db.transaction() as conn:
            repo.set_photo_source(conn, photo.id, SOURCE, photo_id)
            photos_repo.restore(conn, [photo.id])
        return photo.id, bool(summary.imported)
