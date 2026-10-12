"""Photo file rules (RAW pairing, dates in names) and Inbox grouping."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from wildlife.domain.codes import LocationMethod
from wildlife.domain.models import Photo
from wildlife.domain.photo_files import date_from_name, is_raw, pair_files, pair_key
from wildlife.domain.photo_groups import draft_from_photos, group_encounters

D = Path("C:/phone/DCIM")


@pytest.mark.parametrize(
    "name",
    [
        "PXL_20240407_152207242.RAW-01.COVER.jpg",
        "PXL_20240407_152207242.RAW-02.ORIGINAL.dng",
        "PXL_20240407_152207242.RAW-01.MP.COVER.jpg",
        "PXL_20240407_152207242.jpg",
        "PXL_20240407_152207242.dng",
        "PXL_20240407_152207242.MP.jpg",
    ],
)
def test_pixel_names_share_a_pair_key(name):
    assert pair_key(D / name) == (str(D).lower(), "pxl_20240407_152207242")


def test_raw_and_jpeg_become_one_photo():
    files = [
        D / "PXL_20240407_152207242.RAW-02.ORIGINAL.dng",
        D / "PXL_20240407_152207242.RAW-01.COVER.jpg",
        D / "PXL_20240407_160000000.jpg",  # an ordinary photo
        D / "PXL_20240407_170000000.RAW-02.ORIGINAL.dng",  # a RAW whose JPEG wasn't copied
        D / "IMG_0001.JPG",
        D / "IMG_0001.CR3",  # a camera's RAW + JPEG
    ]
    items = pair_files(files)
    assert [(i.main.name, i.raw.name if i.raw else None) for i in items] == [
        ("PXL_20240407_152207242.RAW-01.COVER.jpg", "PXL_20240407_152207242.RAW-02.ORIGINAL.dng"),
        ("PXL_20240407_160000000.jpg", None),
        ("PXL_20240407_170000000.RAW-02.ORIGINAL.dng", None),
        ("IMG_0001.JPG", "IMG_0001.CR3"),
    ]


def test_same_name_in_different_folders_is_not_a_pair():
    items = pair_files([Path("a/IMG_1.jpg"), Path("b/IMG_1.dng")])
    assert len(items) == 2 and all(i.raw is None for i in items)


def test_raw_types():
    assert is_raw("x.DNG") and is_raw("x.cr3") and is_raw("x.nef")
    assert not is_raw("x.jpg") and not is_raw("x.heic")


def test_pixel_file_name_time_is_utc():
    expected = (
        datetime(2026, 7, 11, 8, 15, 30, tzinfo=UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    )
    assert date_from_name("PXL_20260711_081530123.RAW-01.COVER.jpg") == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("IMG_20260711_081530.jpg", "2026-07-11 08:15:30"),  # most phones: local time
        ("IMG-20260711-WA0003.jpg", None),  # WhatsApp: a date but no time
        ("holiday.jpg", None),
        ("PXL_20261341_081530123.jpg", None),  # month 13
    ],
)
def test_other_file_name_dates(name, expected):
    assert date_from_name(name) == expected


# ---- grouping ----------------------------------------------------------------------
def photo(i, taken, lat=None, lon=None):
    return Photo(
        id=i,
        uuid=str(i),
        sha256=f"{i:064d}",
        rel_path=f"p/{i}.jpg",
        original_name=f"{i}.jpg",
        file_size=1,
        width=10,
        height=10,
        taken_at=taken,
        gps_latitude=lat,
        gps_longitude=lon,
    )


RAINHAM, EPPING = (51.4955, 0.1975), (51.6611, 0.0520)


def test_photos_close_in_time_and_place_are_one_encounter():
    photos = [
        photo(1, "2026-10-11 08:00:00", *RAINHAM),
        photo(2, "2026-10-11 08:04:00", RAINHAM[0] + 0.0005, RAINHAM[1]),  # 55 m away
        photo(3, "2026-10-11 08:13:00"),  # no GPS, 9 minutes later: same encounter
        photo(4, "2026-10-11 08:30:00", *RAINHAM),  # 17-minute gap
        photo(5, "2026-10-11 08:31:00", *EPPING),  # 20 km away
        photo(6, None),  # no date
    ]
    groups = group_encounters(reversed(photos))  # any order in
    assert [[p.id for p in g.photos] for g in groups] == [[1, 2, 3], [4], [5], [6]]
    assert groups[0].start == "2026-10-11 08:00:00" and groups[0].end == "2026-10-11 08:13:00"
    assert groups[0].located == 2


def test_draft_from_photos_uses_earliest_time_and_first_gps():
    draft = draft_from_photos(
        [photo(2, "2026-10-11 08:04:00", *RAINHAM), photo(1, "2026-10-11 08:00:00")],
        date(2026, 10, 11),
    )
    assert (draft.observed_date, draft.observed_time) == (date(2026, 10, 11), "08:00")
    assert (draft.latitude, draft.longitude, draft.uncertainty_m) == (*RAINHAM, 10)
    assert draft.location_method is LocationMethod.PHOTO and draft.taxon_id is None


def test_draft_from_undated_photos_uses_today():
    draft = draft_from_photos([photo(1, None)], date(2026, 10, 11))
    assert draft.observed_date == date(2026, 10, 11) and draft.observed_time is None
    assert draft.latitude is None
