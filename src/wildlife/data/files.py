"""Writing files so they are either complete or not there at all.

Every file WildLife stores (a photo copied into the library, a thumbnail, a backup copy)
is first written under a temporary name, then renamed in one step. An interrupted copy
leaves only a `.part` file, never a half-written photo with the right name.

The temporary name is unique to each write, so two copies of the same file at the same
moment (two background threads making the same thumbnail, a backup and a photo import)
never write into each other's file. Clean-up of `.part` files only removes old ones
(`remove_stale_parts`), so it can't pull a file from under a copy that's still running.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
import uuid
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)
STALE_AFTER_S = 3600  # a .part file this old belongs to a copy that was interrupted


def part_path(dest: Path) -> Path:
    """A temporary name next to `dest`, unique to this write."""
    return dest.with_name(f"{dest.name}.{uuid.uuid4().hex[:8]}.part")


def write_atomically(dest: Path, write: Callable[[Path], None]) -> None:
    """Call `write(temporary path)`, then move the result to `dest` in one step.

    For files whose name says what they contain (WildLife's photos are named by their
    content hash, thumbnails by photo and size): if `dest` appears meanwhile, another
    copy of the very same file won the race, and that's fine."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = part_path(dest)
    try:
        write(tmp)
        try:
            os.replace(tmp, dest)
        except PermissionError:
            # Windows won't replace a file another thread has open. If it's there, it's
            # the same file (see above), so ours isn't needed.
            if not dest.exists():
                raise
    finally:
        tmp.unlink(missing_ok=True)


def copy_atomically(source: Path, dest: Path) -> None:
    """Copy `source` to `dest` (keeping its timestamps), complete or not at all."""
    write_atomically(dest, lambda tmp: shutil.copy2(source, tmp))


def is_stale_part(path: Path) -> bool:
    """A `.part` file left by an interrupted copy (not one still being written)."""
    try:
        return path.suffix == ".part" and path.stat().st_mtime < time.time() - STALE_AFTER_S
    except OSError:
        return False


def remove_stale_parts(folder: Path, recursive: bool = False) -> int:
    """Delete `.part` files left by copies that were interrupted (older than an hour).
    Recent ones may belong to a copy still running, so they're left alone."""
    if not folder.exists():
        return 0
    removed = 0
    for part in folder.rglob("*.part") if recursive else folder.glob("*.part"):
        try:
            if is_stale_part(part):
                part.unlink()
                removed += 1
        except OSError as exc:  # in use, or already gone
            log.info("Left %s: %s", part.name, exc)
    return removed
