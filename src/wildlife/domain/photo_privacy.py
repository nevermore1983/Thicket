"""Removing where a photo was taken before it's shared.

A JPEG's location sits in its EXIF block (and sometimes in XMP). Removing them by
editing just those blocks leaves the picture itself untouched, so the shared copy
is exactly as sharp as the original. The original in your library is never changed.
"""

from __future__ import annotations

from PIL import Image

_GPS_IFD = 0x8825
_EXIF = b"Exif\x00\x00"
_XMP = b"http://ns.adobe.com/xap/1.0/\x00"


def jpeg_without_gps(data: bytes) -> bytes:
    """The same JPEG without GPS: EXIF keeps everything else (camera, date...), and
    XMP, which can also hold a location, is left out. Raises ValueError if `data`
    isn't a JPEG."""
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    out = [data[:2]]
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            raise ValueError("damaged JPEG")
        marker = data[i + 1]
        if marker == 0xDA:  # start of the picture data: copy the rest as it is
            out.append(data[i:])
            return b"".join(out)
        length = int.from_bytes(data[i + 2 : i + 4], "big")
        segment = data[i : i + 2 + length]
        body = segment[4:]
        if marker == 0xE1 and body.startswith(_EXIF):
            exif = Image.Exif()
            exif.load(body)
            if _GPS_IFD in exif:
                del exif[_GPS_IFD]
                new_body = exif.tobytes()
                segment = b"\xff\xe1" + (len(new_body) + 2).to_bytes(2, "big") + new_body
        elif marker == 0xE1 and body.startswith(_XMP):
            segment = b""
        out.append(segment)
        i += 2 + length
    out.append(data[i:])
    return b"".join(out)


def has_gps(data: bytes) -> bool:
    """Does this image file say where it was taken?"""
    import io

    try:
        with Image.open(io.BytesIO(data)) as im:
            return bool(im.getexif().get_ifd(_GPS_IFD)) or b"exif:GPS" in data
    except OSError:
        return False
