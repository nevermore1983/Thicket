"""Spike 4a: create test photos (HEIC + JPEG) with known EXIF.

Uses pillow-heif ONLY here, because it can *write* HEIC. The app itself uses
pi-heif, which can only read. Each photo is landscape pixels with an EXIF
"rotate 90° clockwise" flag (Orientation 6), like a phone held upright.

Run:  uv run --with pillow-heif python spikes/heic/make_samples.py
"""

from pathlib import Path

import pillow_heif
from PIL import Image, ImageDraw

pillow_heif.register_heif_opener()
OUT = Path(__file__).parent / "output"
OUT.mkdir(exist_ok=True)

# Known truth: Rainham Marshes, 10 Oct 2026 10:42:07, taken in BST (+01:00)
LAT, LON = 51.4955, 0.1975


def dms(value: float) -> tuple[float, float, float]:
    d = int(value)
    m = int((value - d) * 60)
    s = round(((value - d) * 60 - m) * 60, 4)
    return (float(d), float(m), s)


img = Image.new("RGB", (400, 300), "#5d7a3a")
draw = ImageDraw.Draw(img)
draw.rectangle([0, 0, 120, 300], fill="#c0392b")  # red band on the LEFT of the stored pixels
exif = Image.Exif()
exif[0x0112] = 6  # Orientation: rotate 90° CW to display
exif[0x010F] = "Apple"
exif[0x0110] = "iPhone 16"
exif_ifd = exif.get_ifd(0x8769)
exif_ifd[0x9003] = "2026:10:10 10:42:07"  # DateTimeOriginal (camera's local time)
exif_ifd[0x9011] = "+01:00"  # OffsetTimeOriginal
gps = exif.get_ifd(0x8825)
gps[1], gps[2] = "N", dms(LAT)
gps[3], gps[4] = "E", dms(abs(LON))
gps[0x1F] = 4.7  # GPSHPositioningError (metres)

img.save(OUT / "sample.heic", exif=exif.tobytes(), quality=80)
img.save(OUT / "sample.jpg", exif=exif.tobytes(), quality=85)
Image.new("RGB", (200, 150), "#7a8f9e").save(OUT / "no_exif.jpg")
(OUT / "corrupt.jpg").write_bytes(b"\xff\xd8\xff\xe0 this is not really a jpeg")
print("wrote", sorted(p.name for p in OUT.iterdir()))
