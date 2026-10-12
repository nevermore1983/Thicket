"""Add synthetic photos to a demo library: some on sightings, some waiting in the Inbox.

    uv run python scripts/make_demo_photos.py --data-dir local_data/demo8 --count 400

The pictures are painted (sky, ground and a coloured animal shape), not real photos,
but they carry real EXIF: a Pixel camera, the sighting's date/time and GPS position.
Inbox photos use Pixel file names, including RAW + JPEG pairs (.RAW-01.COVER.jpg with
.RAW-02.ORIGINAL.dng). Refuses a library that already has photos.
"""

from __future__ import annotations

import argparse
import random
import shutil
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from wildlife.config.paths import DataPaths
from wildlife.context import AppContext
from wildlife.domain.filters import SightingFilter

DNG = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "photos" / "sample.dng"
SKIES = [
    ((122, 170, 220), (214, 230, 240)),
    ((150, 160, 175), (210, 214, 220)),
    ((240, 170, 120), (250, 225, 190)),
]
GROUNDS = [(96, 128, 64), (120, 140, 80), (150, 130, 90), (70, 110, 120), (90, 110, 70)]


def rational(value: float) -> tuple:
    value = abs(value)
    d = int(value)
    m = int((value - d) * 60)
    s = round(((value - d) * 60 - m) * 60, 2)
    return (d, m, s)


def paint(rng: random.Random, colour: str, portrait: bool) -> Image.Image:
    w, h = (1200, 1600) if portrait else (1600, 1200)
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    top, bottom = rng.choice(SKIES)
    horizon = int(h * rng.uniform(0.45, 0.65))
    for y in range(horizon):
        t = y / horizon
        d.line(
            [(0, y), (w, y)],
            fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom, strict=True)),
        )
    ground = rng.choice(GROUNDS)
    for y in range(horizon, h):
        t = (y - horizon) / (h - horizon)
        d.line([(0, y), (w, y)], fill=tuple(int(c * (1 - 0.35 * t)) for c in ground))
    for _ in range(rng.randint(2, 5)):  # distant trees / reeds
        x = rng.randint(0, w)
        r = rng.randint(40, 140)
        d.ellipse(
            [x - r, horizon - r * 1.4, x + r, horizon + 10],
            fill=tuple(int(c * 0.7) for c in ground),
        )
    # the 'animal': body + head in the category's colour, a little darker
    rgb = tuple(int(colour[i : i + 2], 16) for i in (1, 3, 5))
    body = tuple(int(c * 0.75) for c in rgb)
    cx, cy = rng.randint(int(w * 0.3), int(w * 0.7)), rng.randint(horizon - 40, int(h * 0.8))
    size = rng.randint(90, 220)
    d.ellipse([cx - size, cy - size * 0.6, cx + size, cy + size * 0.6], fill=body)
    hx = cx + size * rng.choice((-0.9, 0.9))
    d.ellipse([hx - size * 0.38, cy - size * 0.95, hx + size * 0.38, cy - size * 0.2], fill=body)
    d.ellipse([hx - 10, cy - size * 0.7, hx + 6, cy - size * 0.55], fill=(20, 20, 20))
    return img.filter(ImageFilter.GaussianBlur(1.2))


def save(
    img: Image.Image, path: Path, taken: datetime, lat: float | None, lon: float | None
) -> None:
    exif = Image.Exif()
    exif[0x010F] = "Google"
    exif[0x0110] = "Pixel 10 Pro"
    exif[0x0132] = taken.strftime("%Y:%m:%d %H:%M:%S")
    exif.get_ifd(0x8769)[0x9003] = taken.strftime("%Y:%m:%d %H:%M:%S")
    if lat is not None:
        gps = exif.get_ifd(0x8825)
        gps[1], gps[2] = ("N" if lat >= 0 else "S"), rational(lat)
        gps[3], gps[4] = ("E" if lon >= 0 else "W"), rational(lon)
    img.save(path, "JPEG", quality=84, exif=exif)


def pixel_name(taken: datetime) -> str:
    utc = taken.astimezone(UTC) if taken.tzinfo else taken.astimezone().astimezone(UTC)
    return f"PXL_{utc:%Y%m%d_%H%M%S}{utc.microsecond // 1000:03d}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--count", type=int, default=400, help="photos on sightings")
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    started = time.perf_counter()
    ctx = AppContext.open(DataPaths(args.data_dir))
    try:
        with ctx.db.connection() as conn:
            if conn.execute("SELECT COUNT(*) FROM photo").fetchone()[0]:
                print("That library already has photos; refusing to add demo photos.")
                return 1
        sightings = [
            s
            for s in ctx.sightings.page(SightingFilter(), "date", True, 0, 3000)
            if s.has_location and s.observed_time
        ]
        rng.shuffle(sightings)
        work = Path(tempfile.mkdtemp(prefix="wildlife-demo-photos-"))
        made = 0
        for s in sightings:
            if made >= args.count:
                break
            colour = ctx.catalogue.category(s.category_id).colour
            files = []
            for k in range(rng.choice((1, 1, 2, 3))):
                taken = datetime.fromisoformat(f"{s.observed_date}T{s.observed_time}") + timedelta(
                    seconds=7 * k
                )
                path = work / f"{pixel_name(taken)}.jpg"
                save(
                    paint(rng, colour, rng.random() < 0.2),
                    path,
                    taken,
                    s.eff_latitude,
                    s.eff_longitude,
                )
                files.append(path)
            summary = ctx.photos.import_files(files)
            ctx.photos.attach(s.id, [p.id for p in summary.photos])
            made += len(files)
        # The Inbox: three encounters from a walk yesterday, some as RAW + JPEG pairs
        inbox = work / "inbox"
        inbox.mkdir()
        base = datetime.now().replace(hour=7, minute=40, second=0, microsecond=0) - timedelta(
            days=1
        )
        spots = [(51.4955, 0.1975), (51.4985, 0.2040), (51.4931, 0.2101)]
        n = 0
        for e, (lat, lon) in enumerate(spots):
            start = base + timedelta(minutes=40 * e)
            for k in range(rng.randint(4, 7)):
                taken = start + timedelta(seconds=rng.randint(5, 50) * (k + 1))
                stem = pixel_name(taken)
                colour = rng.choice(["#2a78d6", "#eda100", "#e87ba4", "#eb6834"])
                img = paint(rng, colour, rng.random() < 0.25)
                if n % 3 == 0:  # a RAW + JPEG pair, named like a Pixel's
                    save(img, inbox / f"{stem}.RAW-01.COVER.jpg", taken, lat, lon)
                    # every real RAW file differs; make each demo copy unique too
                    (inbox / f"{stem}.RAW-02.ORIGINAL.dng").write_bytes(
                        DNG.read_bytes() + f"demo {n}".encode()
                    )
                else:
                    save(img, inbox / f"{stem}.jpg", taken, lat, lon)
                n += 1
        summary = ctx.photos.import_files([inbox])
        print(
            f"Demo photos ready in {time.perf_counter() - started:.1f} s: {made} on sightings; "
            f"Inbox: {summary.describe()}"
        )
        shutil.rmtree(work, ignore_errors=True)
    finally:
        ctx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
