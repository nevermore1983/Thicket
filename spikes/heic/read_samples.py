"""Spike 4b: can the app's libraries (Pillow + pi-heif) read what we need?

For each sample: open it, apply the EXIF rotation, read date taken + GPS +
accuracy, make a thumbnail, and check against the known truth. Also checks
that a file without EXIF and a corrupt file fail gracefully.

Run:  uv run python spikes/heic/read_samples.py
"""

import sys
from pathlib import Path

import pi_heif
from PIL import Image, ImageOps, UnidentifiedImageError

pi_heif.register_heif_opener()
OUT = Path(__file__).parent / "output"
TRUTH = {"lat": 51.4955, "lon": 0.1975, "taken": "2026-10-10 10:42:07"}


def gps_to_decimal(dms, ref) -> float:
    d, m, s = (float(x) for x in dms)
    value = d + m / 60 + s / 3600
    return -value if ref in ("S", "W") else value


def read(path: Path) -> dict:
    with Image.open(path) as im:
        exif = im.getexif()
        upright = ImageOps.exif_transpose(im)  # applies Orientation, returns a new image
        info = {"stored_size": im.size, "upright_size": upright.size}
        # After a 90° CW rotation the red band (stored on the left) should be at the TOP
        info["red_on_top"] = upright.convert("RGB").getpixel((upright.width // 2, 10))[0] > 150
        sub = exif.get_ifd(0x8769)
        info["taken"] = (sub.get(0x9003) or exif.get(0x0132) or "").replace(":", "-", 2) or None
        info["offset"] = sub.get(0x9011)
        gps = exif.get_ifd(0x8825)
        if gps.get(2) and gps.get(4):
            info["lat"] = round(gps_to_decimal(gps[2], gps.get(1, "N")), 5)
            info["lon"] = round(gps_to_decimal(gps[4], gps.get(3, "E")), 5)
            info["accuracy_m"] = float(gps[0x1F]) if 0x1F in gps else None
        info["camera"] = f"{exif.get(0x010F, '')} {exif.get(0x0110, '')}".strip() or None
        thumb = upright.copy()
        thumb.thumbnail((256, 256))
        thumb.save(OUT / f"thumb_{path.stem}_{path.suffix[1:]}.webp", quality=80)
        info["thumb"] = thumb.size
    return info


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ok = True
    for name in ("sample.heic", "sample.jpg"):
        info = read(OUT / name)
        good = (info["red_on_top"] and info["upright_size"] == (300, 400)
                and info["taken"] == TRUTH["taken"]
                and abs(info["lat"] - TRUTH["lat"]) < 1e-4 and abs(info["lon"] - TRUTH["lon"]) < 1e-4)
        ok &= good
        print(f"{'PASS' if good else 'FAIL'} {name}: {info}")
    info = read(OUT / "no_exif.jpg")
    print(f"PASS no_exif.jpg reads with no date/GPS: taken={info['taken']} lat={info.get('lat')}")
    try:
        read(OUT / "corrupt.jpg")
        print("FAIL corrupt.jpg was accepted")
        ok = False
    except (UnidentifiedImageError, OSError) as exc:
        print(f"PASS corrupt.jpg rejected cleanly: {type(exc).__name__}")
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
