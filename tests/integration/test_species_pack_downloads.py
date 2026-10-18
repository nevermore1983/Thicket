"""Downloading species packs (docs/16-regions-plan.md, step 3), against a pretend
internet: a manifest and a pack built from helpers.US_PACK. Never the real one."""

import gzip
import hashlib
import json

import pytest

from helpers import US_PACK
from wildlife.domain.errors import OnlineServiceError
from wildlife.services.species_packs import MANIFEST_URL, PackError

PACK_URL = "https://github.com/nevermore1983/WildlifeTracker/releases/download/packs-2026-10/us-ca.jsonl.gz"


def pack_bytes(records=US_PACK) -> bytes:
    return gzip.compress("".join(json.dumps(r) + "\n" for r in records).encode("utf-8"))


def manifest(data: bytes, **changes) -> bytes:
    pack = {
        "region": "us-ca",
        "name": "California",
        "file": "us-ca.jsonl.gz",
        "species": len(US_PACK),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "url": PACK_URL,
    }
    body = {"format": 1, "created": "2026-10-18", "packs": [pack | changes]}
    return json.dumps(body).encode("utf-8")


class Internet(dict):
    """url -> what it answers (bytes, or an exception to raise), and what was asked for."""

    asked: list[str]


@pytest.fixture
def internet(ctx):
    """ctx.species_packs fetching from a dict of url -> bytes (or an exception)."""
    served = Internet()
    served.asked = asked = []

    def fetch(url: str) -> bytes:
        asked.append(url)
        answer = served[url]
        if isinstance(answer, Exception):
            raise answer
        return answer

    ctx.species_packs._fetch = fetch
    return served


def serve(internet, data=None, **changes):
    data = pack_bytes() if data is None else data
    internet[MANIFEST_URL] = manifest(pack_bytes() if "sha256" in changes else data, **changes)
    internet[PACK_URL] = data


def test_the_packs_offered_come_from_the_manifest(ctx, internet):
    serve(internet)
    (pack,) = ctx.species_packs.offered()
    assert (pack.region, pack.name, pack.species, pack.version) == (
        "us-ca",
        "California",
        5,
        "2026-10-18",
    )


def test_a_pack_is_downloaded_checked_and_installed(ctx, internet):
    serve(internet)
    (pack,) = ctx.species_packs.offered()
    steps = []
    assert ctx.species_packs.install(pack, lambda step, f: steps.append((step, f))) == 5
    assert {p["region"] for p in ctx.catalogue.packs()} == {"uk", "us-ca"}
    assert steps[0][1] == 0.0 and steps[-1][1] == pytest.approx(1.0)
    ctx.catalogue.set_region("us-ca")
    assert ctx.catalogue.search("cardinal")[0].taxon.display_name == "Northern Cardinal"


def test_a_pack_that_doesnt_match_its_checksum_is_not_installed(ctx, internet):
    serve(internet, sha256="0" * 64)  # the list says one thing, the file is another
    (pack,) = ctx.species_packs.offered()
    with pytest.raises(PackError) as refused:
        ctx.species_packs.install(pack)
    assert "checksum" in refused.value.user_message
    assert {p["region"] for p in ctx.catalogue.packs()} == {"uk"}  # nothing changed


def test_a_damaged_pack_is_not_installed(ctx, internet):
    serve(internet, data=pack_bytes([{"k": "gbif:1", "s": "Cardinalis cardinalis"}]))  # no rank
    (pack,) = ctx.species_packs.offered()
    with pytest.raises(PackError) as refused:
        ctx.species_packs.install(pack)
    assert "damaged" in refused.value.user_message
    serve(internet, data=b"not gzip at all")
    (pack,) = ctx.species_packs.offered(refresh=True)
    with pytest.raises(PackError):
        ctx.species_packs.install(pack)
    assert {p["region"] for p in ctx.catalogue.packs()} == {"uk"}


def test_packs_need_online_features(ctx, internet):
    serve(internet)
    ctx.settings.update(allow_online=False)
    with pytest.raises(PackError) as refused:
        ctx.species_packs.offered()
    assert "Allow online features" in refused.value.user_message
    assert internet.asked == []  # nothing was even asked for


def test_no_internet_is_explained(ctx, internet):
    internet[MANIFEST_URL] = OnlineServiceError("Couldn't connect. Check your internet connection.")
    with pytest.raises(PackError) as refused:
        ctx.species_packs.offered()
    assert "Couldn't get the list of species packs" in refused.value.user_message


def test_a_newer_manifest_asks_for_a_newer_wildlife(ctx, internet):
    internet[MANIFEST_URL] = json.dumps({"format": 99, "packs": []}).encode()
    with pytest.raises(PackError) as refused:
        ctx.species_packs.offered()
    assert "newer version of Thicket" in refused.value.user_message


def test_only_wildlifes_github_releases_are_approved():
    from wildlife.services.online import is_allowed

    assert is_allowed(MANIFEST_URL) and is_allowed(PACK_URL)
    assert is_allowed(
        "https://release-assets.githubusercontent.com/github-production-release-asset/1"
    )
    assert not is_allowed("http://github.com/nevermore1983/WildlifeTracker")  # https only
    assert not is_allowed("https://raw.githubusercontent.com/someone/else/main/pack.gz")
