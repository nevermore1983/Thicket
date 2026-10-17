"""Files are written complete or not at all, even when several copies race (data/files.py)."""

import os
import threading
import time
from pathlib import Path

from wildlife.data.files import STALE_AFTER_S, copy_atomically, remove_stale_parts

FIXTURES = Path(__file__).parents[1] / "fixtures" / "photos"


def _all_at_once(n: int, job) -> list:
    """Run `job` on n threads released together; returns what each returned or raised."""
    start, results = threading.Barrier(n), []

    def run() -> None:
        start.wait()
        try:
            results.append(job())
        except Exception as exc:  # collected, so the test can show it
            results.append(exc)

    threads = [threading.Thread(target=run) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_a_copy_is_complete_and_leaves_nothing_behind(tmp_path):
    dest = tmp_path / "library" / "photo.jpg"
    copy_atomically(FIXTURES / "sample.jpg", dest)
    assert dest.read_bytes() == (FIXTURES / "sample.jpg").read_bytes()
    assert list(dest.parent.glob("*.part")) == []


def test_the_same_file_copied_by_many_threads_at_once(tmp_path):
    dest = tmp_path / "photo.jpg"
    results = _all_at_once(8, lambda: copy_atomically(FIXTURES / "sample.jpg", dest))
    assert [r for r in results if isinstance(r, Exception)] == []
    assert dest.read_bytes() == (FIXTURES / "sample.jpg").read_bytes()
    assert list(tmp_path.glob("*.part")) == []


def test_only_old_part_files_are_cleaned_up(tmp_path):
    running = tmp_path / "copy-in-progress.jpg.1234abcd.part"
    abandoned = tmp_path / "interrupted.jpg.5678abcd.part"
    for f in (running, abandoned):
        f.write_bytes(b"x")
    old = time.time() - STALE_AFTER_S - 60
    os.utime(abandoned, (old, old))
    assert remove_stale_parts(tmp_path) == 1
    assert running.exists() and not abandoned.exists()


def test_the_same_thumbnail_made_by_many_threads_at_once(ctx):
    """The grid, the day view and the sighting rows can all ask for one thumbnail at the
    same moment. Every one of them must get it (it used to fail for some: 'Can't display')."""
    photo = ctx.photos.import_files([FIXTURES / "sample.jpg"]).imported[0]
    results = _all_at_once(8, lambda: ctx.photos.thumbnail(photo, 300))
    assert all(isinstance(r, Path) and r.exists() for r in results), results
