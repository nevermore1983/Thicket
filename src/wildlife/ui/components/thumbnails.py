"""Loads photo thumbnails in the background and keeps recent ones in memory.

Grids ask for a thumbnail with get(); if it isn't ready they draw a placeholder and
repaint when `ready` fires. Making a thumbnail the first time can take ~50 ms (more for
RAW files), so it happens on worker threads; reading a cached one is ~1 ms.
"""

from __future__ import annotations

import contextlib
import logging
from collections import OrderedDict

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap

from wildlife.domain.models import Photo
from wildlife.services.photos import PhotoService

log = logging.getLogger(__name__)
MEMORY_LIMIT = 800  # thumbnails kept in memory (about 50 MB at 256 px)


class _Signals(QObject):
    done = Signal(object, object)  # key, QImage or None


class _Job(QRunnable):
    def __init__(self, photos: PhotoService, photo: Photo, size: int, key) -> None:
        super().__init__()
        self.photos, self.photo, self.size, self.key = photos, photo, size, key
        self.signals = _Signals()

    def run(self) -> None:
        image = None
        try:
            path = self.photos.thumbnail(self.photo, self.size)
            if path is not None:
                image = QImage(str(path))  # QImage is safe to make off the UI thread
        except Exception:  # never let one bad file stop the grid
            log.exception("Thumbnail job failed for photo %s", self.photo.id)
        with contextlib.suppress(RuntimeError):  # the app closed meanwhile
            self.signals.done.emit(self.key, image)


class ThumbnailLoader(QObject):
    ready = Signal(object)  # key: (photo id, rotation, size)
    MISSING = "missing"

    def __init__(self, photos: PhotoService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.photos = photos
        self._cache: OrderedDict = OrderedDict()
        self._pending: set = set()
        self._jobs: set[_Job] = set()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(4)

    @staticmethod
    def key(photo: Photo, size: int) -> tuple[int, int, int]:
        return photo.id, photo.rotation, size

    def get(self, photo: Photo, size: int = 256) -> QPixmap | str | None:
        """The thumbnail if ready, MISSING if the file can't be shown, else None (and it's
        requested; `ready` fires when it arrives)."""
        k = self.key(photo, size)
        if k in self._cache:
            self._cache.move_to_end(k)
            return self._cache[k]
        if k not in self._pending:
            self._pending.add(k)
            job = _Job(self.photos, photo, size, k)
            job.signals.done.connect(self._finished)
            self._jobs.add(job)
            self._pool.start(job)
        return None

    def _finished(self, key, image: QImage | None) -> None:
        self._pending.discard(key)
        self._jobs = {j for j in self._jobs if j.key != key}
        self._cache[key] = (
            QPixmap.fromImage(image) if image is not None and not image.isNull() else self.MISSING
        )
        while len(self._cache) > MEMORY_LIMIT:
            self._cache.popitem(last=False)
        self.ready.emit(key)

    def forget(self, photo_id: int) -> None:
        """Drop a photo's thumbnails (e.g. after rotating it or locating its file)."""
        for k in [k for k in self._cache if k[0] == photo_id]:
            del self._cache[k]

    def wait_idle(self, msecs: int = 10_000) -> bool:
        """For tests and screenshots: wait until every requested thumbnail is made."""
        return self._pool.waitForDone(msecs)
