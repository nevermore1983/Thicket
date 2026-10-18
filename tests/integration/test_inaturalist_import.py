"""Importing iNaturalist exports: matching names, re-imports, Undo and photos.

All rows are invented, and the internet is replaced by a fake that serves made-up
API answers and tiny generated photos.
"""

import io
import json
from dataclasses import replace
from datetime import date

import pytest
from PIL import Image

from helpers import inat_csv, inat_row, taxon_id
from wildlife.domain.codes import Identification
from wildlife.domain.errors import OnlineServiceError
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import PlaceDraft
from wildlife.services.inaturalist import ADD, SAME, SKIP, UPDATE, name_variants
from wildlife.services.online import is_allowed


def write(tmp_path, rows, name="observations-1.csv"):
    path = tmp_path / name
    path.write_text(inat_csv(rows), encoding="utf-8")
    return path


def import_rows(ctx, tmp_path, rows, choices=None):
    plan = ctx.inaturalist.preview(write(tmp_path, rows))
    return plan, ctx.inaturalist.run(plan, choices)


def category_of(ctx, sighting_id):
    return ctx.catalogue.category(ctx.sightings.get(sighting_id).category_id).name


def test_names_are_matched_to_the_uk_list(ctx, tmp_path):
    rows = [
        inat_row(1),  # exact scientific name
        inat_row(2, "Deraeocoris flavilinea", iconic_taxon_name="Insecta"),  # UKSI adds a subgenus
        inat_row(3, "Argentina anserina", iconic_taxon_name="Plantae"),  # a synonym
        inat_row(
            4, "Argynnis aglaja", common_name="Dark Green Fritillary", iconic_taxon_name="Insecta"
        ),
        inat_row(5, "Prunella", iconic_taxon_name="Plantae"),  # the plant genus, not the bird's
        inat_row(6, "Sphecodogastra", iconic_taxon_name="Insecta"),  # not in the UK list
    ]
    plan = ctx.inaturalist.preview(write(tmp_path, rows))
    got = {r.record.source_id: (r.taxon_id, r.matched_by) for r in plan.rows}
    assert got["1001"] == (taxon_id(ctx, "Erithacus rubecula"), "name")
    # UKSI's name without the subgenus is one of its other names
    assert got["1002"] == (taxon_id(ctx, "Deraeocoris (Deraeocoris) flavilinea"), "synonym")
    assert got["1003"] == (taxon_id(ctx, "Potentilla anserina"), "synonym")
    assert got["1004"] == (taxon_id(ctx, "Speyeria aglaja"), "english")
    assert ctx.catalogue.get(got["1005"][0]).scientific_name == "Prunella"
    with ctx.db.connection() as conn:
        kingdom = conn.execute("SELECT tax_kingdom FROM taxon WHERE id = ?", (got["1005"][0],))
        assert kingdom.fetchone()[0] == "Plantae"
    assert got["1006"] == (None, "") and list(plan.unmatched) == ["Sphecodogastra"]


def test_name_variants():
    assert name_variants("Salix × multinervis") == ["Salix x multinervis"]
    assert name_variants("Deraeocoris (Camptobrochis) serenus") == [
        "Deraeocoris (Camptobrochis) serenus",
        "Deraeocoris serenus",
    ]
    assert "Primula vulgaris subsp. sibthorpii" in name_variants("Primula vulgaris sibthorpii")


def test_import_creates_sightings_in_the_right_categories(ctx, tmp_path):
    ctx.places.save(PlaceDraft("Test Park", 51.5001, -0.1201, radius_m=200))
    rows = [
        inat_row(1),
        inat_row(2, "Rubus fruticosus", iconic_taxon_name="Plantae", quality_grade="needs_id"),
        inat_row(3, "Amanita muscaria", iconic_taxon_name="Fungi"),
        inat_row(4, "Xanthoria parietina", iconic_taxon_name="Fungi"),
        inat_row(5, "Zootoca vivipara", iconic_taxon_name="Reptilia"),
        inat_row(6, observed_on_string="", observed_on="", time_observed_at=""),  # no date
    ]
    plan, result = import_rows(ctx, tmp_path, rows)
    assert (plan.count(ADD), plan.count(SKIP)) == (5, 1)
    assert result.describe() == "5 added · 1 skipped"
    robin = ctx.sightings.get(result.added[0])
    assert (robin.observed_date, robin.observed_time) == (date(2026, 5, 3), "07:40")
    assert robin.place_name == "Test Park" and robin.latitude == 51.5  # exact spot kept too
    assert robin.count is None and robin.source == "inaturalist" and robin.source_id == "1001"
    bramble = ctx.sightings.get(result.added[1])
    assert bramble.identification is Identification.PROBABLE
    assert [category_of(ctx, i) for i in result.added] == [
        "Bird",
        "Plant",
        "Fungus & lichen",
        "Fungus & lichen",
        "Reptile, amphibian & fish",
    ]


def test_choices_are_used_and_remembered(ctx, tmp_path):
    rows = [inat_row(1, "Sphecodogastra", iconic_taxon_name="Insecta")]
    beetle = taxon_id(ctx, "Beetlus obscurus")
    _, result = import_rows(ctx, tmp_path, rows, {"Sphecodogastra": beetle})
    assert ctx.sightings.get(result.added[0]).taxon_id == beetle
    plan = ctx.inaturalist.preview(write(tmp_path, [inat_row(2, "Sphecodogastra")], "again.csv"))
    assert (plan.rows[0].taxon_id, plan.rows[0].matched_by) == (beetle, "remembered")


def test_unmatched_names_without_a_choice_are_skipped(ctx, tmp_path):
    _, result = import_rows(ctx, tmp_path, [inat_row(1, "Sphecodogastra")])
    assert result.added == [] and result.skipped == 1


def test_importing_the_same_file_again_adds_nothing(ctx, tmp_path):
    rows = [inat_row(1), inat_row(2, "Vulpes vulpes", iconic_taxon_name="Mammalia")]
    import_rows(ctx, tmp_path, rows)
    plan, result = import_rows(ctx, tmp_path, rows)
    assert plan.count(SAME) == 2 and result.added == [] and result.skipped == 0
    assert ctx.sightings.totals(SightingFilter())[0] == 2


def test_changes_on_inaturalist_update_the_sighting(ctx, tmp_path):
    _, first = import_rows(ctx, tmp_path, [inat_row(1, quality_grade="needs_id")])
    changed = inat_row(1, quality_grade="research", updated_at="2026-06-01 09:00:00 UTC")
    plan, result = import_rows(ctx, tmp_path, [changed])
    assert plan.rows[0].action == UPDATE and result.updated == first.added
    assert ctx.sightings.get(first.added[0]).identification is Identification.CERTAIN
    result.undo.run()  # undoing the update puts the earlier version back
    assert ctx.sightings.get(first.added[0]).identification is Identification.PROBABLE
    assert ctx.inaturalist.preview(write(tmp_path, [changed])).rows[0].action == UPDATE


def test_your_own_edits_are_never_overwritten(ctx, tmp_path):
    _, first = import_rows(ctx, tmp_path, [inat_row(1)])
    draft = ctx.sightings.get(first.added[0]).to_draft()
    ctx.sightings.save(replace(draft, notes="My note"))
    changed = inat_row(1, updated_at="2026-06-01 09:00:00 UTC")
    plan = ctx.inaturalist.preview(write(tmp_path, [changed]))
    assert plan.rows[0].action == SKIP and "kept" in plan.rows[0].reason


def test_deleted_sightings_are_not_brought_back(ctx, tmp_path):
    _, first = import_rows(ctx, tmp_path, [inat_row(1)])
    ctx.sightings.delete(first.added)
    plan = ctx.inaturalist.preview(write(tmp_path, [inat_row(1)]))
    assert plan.rows[0].reason == "You deleted it in Thicket"


def test_undo_removes_the_whole_import(ctx, tmp_path):
    _, result = import_rows(ctx, tmp_path, [inat_row(1), inat_row(2, "Vulpes vulpes")])
    result.undo.run()
    plan = ctx.inaturalist.preview(write(tmp_path, [inat_row(1)]))
    assert plan.rows[0].action == ADD  # gone, so it can be imported again
    with ctx.db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM import_batch").fetchone()[0] == 0


# ---- photos -------------------------------------------------------------------------
def jpeg(colour) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), colour).save(out, "JPEG")
    return out.getvalue()


class FakeInternet:
    """Answers like iNaturalist would; remembers what was asked for."""

    def __init__(self, api_works=True):
        self.asked: list[str] = []
        self.api_works = api_works

    def __call__(self, url: str) -> bytes:
        assert is_allowed(url), url
        self.asked.append(url)
        if url.startswith("https://api.inaturalist.org/"):
            if not self.api_works:
                raise OnlineServiceError("API down")
            ids = url.split("id=")[1].split("&")[0].split(",")
            results = [
                {
                    "id": int(i),
                    "photos": [
                        {
                            "id": int(i) * 10 + k,
                            "url": f"https://static.inaturalist.org/photos/{int(i) * 10 + k}/square.jpg",
                        }
                        for k in (1, 2)
                    ],
                }
                for i in ids
            ]
            return json.dumps({"results": results}).encode()
        if "/original." in url and "photos/5002/" in url:
            raise OnlineServiceError("No original")  # falls back to the large size
        return jpeg((len(self.asked) * 7 % 255, 90, 40))


@pytest.fixture
def online(ctx):
    internet = FakeInternet()
    ctx.inaturalist._fetch = internet
    ctx.inaturalist._pause = lambda seconds: None
    return internet


def test_photos_are_fetched_and_attached(ctx, tmp_path, online):
    _, result = import_rows(ctx, tmp_path, [inat_row(1), inat_row(2, "Vulpes vulpes")])
    fetched = ctx.inaturalist.fetch_photos(result)
    assert fetched.describe() == "4 photos added"
    photos = ctx.photos.for_sighting(result.added[0])
    assert [p.original_name for p in photos] == ["inaturalist-10011.jpg", "inaturalist-10012.jpg"]
    assert all("/original." in u for u in online.asked[1:])
    again = ctx.inaturalist.fetch_photos(result)  # nothing left to fetch
    assert again.fetched == 0 and len(online.asked) == 5


def test_export_links_are_used_when_the_api_is_down(ctx, tmp_path, online):
    online.api_works = False
    _, result = import_rows(ctx, tmp_path, [inat_row(1), inat_row(2, "Vulpes vulpes")])
    fetched = ctx.inaturalist.fetch_photos(result)
    assert fetched.fetched == 2
    assert online.asked[-2:] == [  # photo 5002 has no original, so "large" is used
        "https://inaturalist-open-data.s3.amazonaws.com/photos/5002/original.jpg",
        "https://inaturalist-open-data.s3.amazonaws.com/photos/5002/large.jpg",
    ]


def test_photos_need_online_features(ctx, tmp_path, online):
    ctx.settings.update(allow_online=False)
    _, result = import_rows(ctx, tmp_path, [inat_row(1)])
    with pytest.raises(OnlineServiceError, match="Allow online features"):
        ctx.inaturalist.fetch_photos(result)
    assert online.asked == []


def test_undo_puts_fetched_photos_in_the_recycle_bin(ctx, tmp_path, online):
    _, result = import_rows(ctx, tmp_path, [inat_row(1)])
    ctx.inaturalist.fetch_photos(result)
    result.undo.run()
    assert len(ctx.photos.recycle_bin()) == 2 and ctx.photos.inbox() == []
    _, again = import_rows(ctx, tmp_path, [inat_row(1)])  # importing again reuses them
    asked = len(online.asked)
    assert ctx.inaturalist.fetch_photos(again).already == 2
    assert len(online.asked) == asked + 1  # only the API was asked
    assert ctx.photos.recycle_bin() == []


def test_only_known_hosts_over_https():
    assert is_allowed("https://static.inaturalist.org/photos/1/original.jpg")
    assert not is_allowed("http://static.inaturalist.org/photos/1/original.jpg")
    assert not is_allowed("https://example.com/photo.jpg")
    assert not is_allowed("https://static.inaturalist.org.example.com/x.jpg")
