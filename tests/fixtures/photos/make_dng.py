"""Write sample.dng: a tiny but valid DNG (RAW) file for tests.

A DNG is a TIFF file with extra tags describing the camera sensor. This writes one by
hand (64 x 48 pixels, an RGGB Bayer pattern, uncompressed 16-bit), with the EXIF date
and GPS position a phone would add, so tests never need a real person's photo.

    uv run python tests/fixtures/photos/make_dng.py
"""

from __future__ import annotations

import struct
from pathlib import Path

WIDTH, HEIGHT = 64, 48
OUT = Path(__file__).with_name("sample.dng")

SHORT, LONG, RATIONAL, SRATIONAL, ASCII, BYTE = 3, 4, 5, 10, 2, 1
SIZES = {BYTE: 1, ASCII: 1, SHORT: 2, LONG: 4, RATIONAL: 8, SRATIONAL: 8}


def bayer() -> bytes:
    """Green-ish scene: brighter on the right, so it isn't flat."""
    out = bytearray()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            level = 6000 + x * 300
            red, green, blue = level // 2, level, level // 3
            value = (red, green)[x % 2] if y % 2 == 0 else (green, blue)[x % 2]
            out += struct.pack("<H", value)
    return bytes(out)


def ifd(entries: list[tuple[int, int, list]], start: int, next_ifd: int = 0) -> tuple[bytes, bytes]:
    """(IFD bytes, overflow data bytes) for an IFD that will sit at file offset `start`."""
    entries = sorted(entries)
    table = struct.pack("<H", len(entries))
    data = b""
    data_start = start + 2 + 12 * len(entries) + 4
    for tag, kind, values in entries:
        if kind == ASCII:
            raw = values[0].encode("ascii") + b"\0"
            count = len(raw)
        elif kind in (RATIONAL, SRATIONAL):
            fmt = "<II" if kind == RATIONAL else "<ii"
            raw = b"".join(struct.pack(fmt, n, d) for n, d in values)
            count = len(values)
        else:
            fmt = {BYTE: "<B", SHORT: "<H", LONG: "<I"}[kind]
            raw = b"".join(struct.pack(fmt, v) for v in values)
            count = len(values)
        if len(raw) <= 4:
            field = raw.ljust(4, b"\0")
        else:
            field = struct.pack("<I", data_start + len(data))
            data += raw + (b"\0" if len(raw) % 2 else b"")
        table += struct.pack("<HHI", tag, kind, count) + field
    table += struct.pack("<I", next_ifd)
    return table, data


def dms(value: float) -> list[tuple[int, int]]:
    degrees = int(value)
    minutes = int((value - degrees) * 60)
    seconds = round(((value - degrees) * 60 - minutes) * 60 * 1000)
    return [(degrees, 1), (minutes, 1), (seconds, 1000)]


def main() -> None:
    pixels = bayer()
    # Layout: header (8) | IFD0 + its data | EXIF IFD + data | GPS IFD + data | pixels
    exif_entries = [
        (0x9003, ASCII, ["2026:10:11 08:15:30"]),
        (0x9004, ASCII, ["2026:10:11 08:15:30"]),
    ]
    gps_entries = [
        (0x0000, BYTE, [2, 3, 0, 0]),
        (0x0001, ASCII, ["N"]),
        (0x0002, RATIONAL, dms(51.4955)),
        (0x0003, ASCII, ["E"]),
        (0x0004, RATIONAL, dms(0.1975)),
    ]

    def ifd0_entries(exif_at: int, gps_at: int, pixels_at: int) -> list:
        return [
            (254, LONG, [0]),
            (256, LONG, [WIDTH]),
            (257, LONG, [HEIGHT]),
            (258, SHORT, [16]),
            (259, SHORT, [1]),
            (262, SHORT, [32803]),  # colour filter array (a Bayer sensor)
            (271, ASCII, ["Google"]),
            (272, ASCII, ["Pixel 10 Pro"]),
            (273, LONG, [pixels_at]),
            (274, SHORT, [1]),
            (277, SHORT, [1]),
            (278, LONG, [HEIGHT]),
            (279, LONG, [len(pixels)]),
            (284, SHORT, [1]),
            (306, ASCII, ["2026:10:11 08:15:30"]),
            (33421, SHORT, [2, 2]),
            (33422, BYTE, [0, 1, 1, 2]),  # R G / G B
            (34665, LONG, [exif_at]),
            (34853, LONG, [gps_at]),
            (50706, BYTE, [1, 4, 0, 0]),
            (50708, ASCII, ["Google Pixel 10 Pro"]),
            (50714, SHORT, [0]),
            (50717, LONG, [65535]),
            # sRGB-ish colour matrix and a neutral white balance
            (
                50721,
                SRATIONAL,
                [
                    (32404, 10000),
                    (-15371, 10000),
                    (-4985, 10000),
                    (-9692, 10000),
                    (18760, 10000),
                    (415, 10000),
                    (556, 10000),
                    (-2040, 10000),
                    (10572, 10000),
                ],
            ),
            (50728, RATIONAL, [(1, 2), (1, 1), (1, 3)]),
            (50778, SHORT, [21]),  # D65
        ]

    # Two passes: sizes first (offsets don't change sizes), then the real offsets
    ifd0_size = len(b"".join(ifd(ifd0_entries(0, 0, 0), 8)))
    exif_at = 8 + ifd0_size
    exif_size = len(b"".join(ifd(exif_entries, exif_at)))
    gps_at = exif_at + exif_size
    gps_size = len(b"".join(ifd(gps_entries, gps_at)))
    pixels_at = gps_at + gps_size
    parts = [b"II*\0" + struct.pack("<I", 8)]
    parts += ifd(ifd0_entries(exif_at, gps_at, pixels_at), 8)
    parts += ifd(exif_entries, exif_at)
    parts += ifd(gps_entries, gps_at)
    parts.append(pixels)
    OUT.write_bytes(b"".join(parts))
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
