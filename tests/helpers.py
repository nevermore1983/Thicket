"""Test data and helpers shared by the test files: import them with `from helpers import ...`."""

from __future__ import annotations

from datetime import date

from wildlife.context import AppContext

TODAY = date(2026, 10, 11)

# A miniature catalogue in the same format as the bundled UKSI file.
_L_BIRD = ["Animalia", "Chordata", "Aves", "Passeriformes"]
MINI_CATALOGUE = [
    {"k": "K1", "r": "kingdom", "s": "Animalia", "l": ["Animalia"]},
    {
        "k": "B0",
        "p": "K1",
        "r": "genus",
        "s": "Larus",
        "c": "Gull",
        "en": ["Seagull"],
        "l": ["Animalia", "Chordata", "Aves", "Charadriiformes", "Laridae"],
        "pr": 3,
    },
    {
        "k": "B1",
        "p": "B0",
        "r": "species",
        "s": "Larus argentatus",
        "c": "Herring Gull",
        "l": ["Animalia", "Chordata", "Aves", "Charadriiformes", "Laridae"],
        "pr": 9,
    },
    {
        "k": "R1",
        "p": "K1",
        "r": "species",
        "s": "Erithacus rubecula",
        "c": "Robin",
        "en": ["Redbreast", "European Robin"],
        "l": [*_L_BIRD, "Muscicapidae"],
        "pr": 10,
    },
    {
        "k": "R2",
        "p": "K1",
        "r": "species",
        "s": "Turdus migratorius",
        "c": "American Robin",
        "l": [*_L_BIRD, "Turdidae"],
        "pr": 6,
    },
    {
        "k": "W1",
        "p": "K1",
        "r": "species",
        "s": "Motacilla alba",
        "c": "Pied Wagtail",
        "l": [*_L_BIRD, "Motacillidae"],
        "pr": 10,
    },
    {
        "k": "W2",
        "p": "W1",
        "r": "subspecies",
        "s": "Motacilla alba yarrellii",
        "c": "Pied Wagtail (yarrellii)",
        "l": [*_L_BIRD, "Motacillidae"],
        "pr": 5,
    },
    {
        "k": "D1",
        "p": "K1",
        "r": "species",
        "s": "Sympetrum striolatum",
        "c": "Common Darter",
        "l": ["Animalia", "Arthropoda", "Insecta", "Odonata", "Libellulidae"],
        "pr": 10,
    },
    {
        "k": "P1",
        "p": "K1",
        "r": "species",
        "s": "Aglais io",
        "c": "Peacock",
        "l": ["Animalia", "Arthropoda", "Insecta", "Lepidoptera", "Nymphalidae"],
        "pr": 10,
    },
    {
        "k": "M1",
        "p": "K1",
        "r": "species",
        "s": "Vulpes vulpes",
        "c": "Red Fox",
        "l": ["Animalia", "Chordata", "Mammalia", "Carnivora", "Canidae"],
        "pr": 10,
    },
    {
        "k": "X1",
        "p": "K1",
        "r": "species",
        "s": "Beetlus obscurus",
        "l": ["Animalia", "Arthropoda", "Insecta", "Coleoptera", "Carabidae"],
        "pr": 0,
    },
    # Names that test matching: a subgenus, a renamed butterfly, a reptile
    {
        "k": "H1",
        "p": "K1",
        "r": "species",
        "s": "Deraeocoris (Deraeocoris) flavilinea",
        "l": ["Animalia", "Arthropoda", "Insecta", "Hemiptera", "Miridae"],
    },
    {
        "k": "F1",
        "p": "K1",
        "r": "species",
        "s": "Speyeria aglaja",
        "c": "Dark Green Fritillary",
        "l": ["Animalia", "Arthropoda", "Insecta", "Lepidoptera", "Nymphalidae"],
        "pr": 8,
    },
    {
        "k": "L1",
        "p": "K1",
        "r": "species",
        "s": "Zootoca vivipara",
        "c": "Common Lizard",
        "l": ["Animalia", "Chordata", "Reptilia", "Squamata", "Lacertidae"],
        "pr": 8,
    },
    {  # Prunella is a bird genus (Dunnock) and a plant genus (Selfheal)
        "k": "U0",
        "p": "K1",
        "r": "genus",
        "s": "Prunella",
        "l": ["Animalia", "Chordata", "Aves", "Passeriformes", "Prunellidae"],
    },
    # The species in the spec's scenarios (S1 Goldfinch, S2 Grey Heron, S4 Kingfisher,
    # S7 Ruddy Darter mistaken for Common Darter)
    {
        "k": "S1",
        "p": "K1",
        "r": "species",
        "s": "Carduelis carduelis",
        "c": "Goldfinch",
        "l": [*_L_BIRD, "Fringillidae"],
        "pr": 10,
    },
    {
        "k": "S2",
        "p": "K1",
        "r": "species",
        "s": "Ardea cinerea",
        "c": "Grey Heron",
        "l": ["Animalia", "Chordata", "Aves", "Pelecaniformes", "Ardeidae"],
        "pr": 10,
    },
    {
        "k": "S4",
        "p": "K1",
        "r": "species",
        "s": "Alcedo atthis",
        "c": "Kingfisher",
        "l": ["Animalia", "Chordata", "Aves", "Coraciiformes", "Alcedinidae"],
        "pr": 10,
    },
    {
        "k": "S7",
        "p": "K1",
        "r": "species",
        "s": "Sympetrum sanguineum",
        "c": "Ruddy Darter",
        "l": ["Animalia", "Arthropoda", "Insecta", "Odonata", "Libellulidae"],
        "pr": 9,
    },
    # Plants and fungi
    {"k": "K2", "r": "kingdom", "s": "Plantae", "l": ["Plantae"]},
    {"k": "K3", "r": "kingdom", "s": "Fungi", "l": ["Fungi"]},
    {
        "k": "V0",
        "p": "K2",
        "r": "genus",
        "s": "Prunella",
        "l": ["Plantae", None, "Magnoliopsida", "Lamiales", "Lamiaceae"],
    },
    {
        "k": "V1",
        "p": "V0",
        "r": "species",
        "s": "Prunella vulgaris",
        "c": "Selfheal",
        "l": ["Plantae", None, "Magnoliopsida", "Lamiales", "Lamiaceae"],
        "pr": 9,
    },
    {
        "k": "V2",
        "p": "K2",
        "r": "species",
        "s": "Rubus fruticosus",
        "c": "Bramble",
        "l": ["Plantae", None, "Magnoliopsida", "Rosales", "Rosaceae"],
        "pr": 9,
    },
    {
        "k": "V3",
        "p": "K2",
        "r": "species",
        "s": "Potentilla anserina",
        "c": "Silverweed",
        "sy": ["Argentina anserina"],
        "l": ["Plantae", None, "Magnoliopsida", "Rosales", "Rosaceae"],
        "pr": 5,
    },
    {
        "k": "G1",
        "p": "K3",
        "r": "species",
        "s": "Amanita muscaria",
        "c": "Fly Agaric",
        "l": ["Fungi", "Basidiomycota", "Agaricomycetes", "Agaricales", "Amanitaceae"],
        "pr": 7,
    },
    {
        "k": "G2",
        "p": "K3",
        "r": "species",
        "s": "Xanthoria parietina",
        "c": "Common Orange Lichen",
        "l": ["Fungi", "Ascomycota", "Lecanoromycetes", "Teloschistales", "Teloschistaceae"],
        "pr": 7,
    },
]


def taxon_id(ctx: AppContext, scientific_name: str) -> int:
    with ctx.db.connection() as conn:
        return conn.execute(
            "SELECT id FROM taxon WHERE scientific_name = ?", (scientific_name,)
        ).fetchone()[0]


# iNaturalist's export columns, in its order. Test rows are invented: never real records.
INAT_COLUMNS = [
    "id",
    "uuid",
    "observed_on_string",
    "observed_on",
    "time_observed_at",
    "time_zone",
    "user_id",
    "user_login",
    "user_name",
    "created_at",
    "updated_at",
    "quality_grade",
    "license",
    "url",
    "image_url",
    "sound_url",
    "tag_list",
    "description",
    "num_identification_agreements",
    "num_identification_disagreements",
    "captive_cultivated",
    "oauth_application_id",
    "place_guess",
    "latitude",
    "longitude",
    "positional_accuracy",
    "private_place_guess",
    "private_latitude",
    "private_longitude",
    "public_positional_accuracy",
    "geoprivacy",
    "taxon_geoprivacy",
    "coordinates_obscured",
    "positioning_method",
    "positioning_device",
    "species_guess",
    "scientific_name",
    "common_name",
    "iconic_taxon_name",
    "taxon_id",
]


def inat_row(n: int, scientific: str = "Erithacus rubecula", **kw) -> dict[str, str]:
    """An invented iNaturalist row (observation id 1000 + n) seen at a park in May 2026."""
    row = dict.fromkeys(INAT_COLUMNS, "")
    row.update(
        id=str(1000 + n),
        observed_on_string="2026-05-03 07:40:12",
        observed_on="2026-05-03",
        time_observed_at="2026-05-03 06:40:12 UTC",
        time_zone="London",
        updated_at="2026-05-04 10:00:00 UTC",
        quality_grade="research",
        url=f"https://www.inaturalist.org/observations/{1000 + n}",
        image_url=f"https://inaturalist-open-data.s3.amazonaws.com/photos/{5000 + n}/medium.jpg",
        captive_cultivated="false",
        place_guess="Test Park, Testshire, UK",
        latitude="51.5",
        longitude="-0.12",
        positional_accuracy="12",
        coordinates_obscured="false",
        scientific_name=scientific,
        iconic_taxon_name="Aves",
    )
    row.update({k: str(v) for k, v in kw.items()})
    return row


def inat_csv(rows: list[dict[str, str]]) -> str:
    import csv
    import io

    out = io.StringIO()
    writer = csv.DictWriter(out, INAT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def jpeg_with_gps(path, colour=(30, 120, 60), lat=(51, 30, 0), lon=(0, 7, 0), taken=None):
    """A small JPEG whose EXIF says where (north and west) and, optionally, when it was
    taken ('2026:10:10 09:00:00')."""
    from PIL import Image

    exif = Image.Exif()
    exif[0x010F] = "TestCam"
    if taken:
        exif.get_ifd(0x8769)[0x9003] = taken  # DateTimeOriginal
    gps = exif.get_ifd(0x8825)
    gps.update({1: "N", 2: tuple(float(x) for x in lat), 3: "W", 4: tuple(float(x) for x in lon)})
    Image.new("RGB", (64, 48), colour).save(path, "JPEG", exif=exif, quality=90)
    return path


# A made-up species pack for California, in GBIF pack format (tests of regions and packs).
# Some species are in MINI_CATALOGUE too (linked, not copied); some only here.
_BIRD = ["Animalia", "Chordata", "Aves", "Passeriformes"]
US_PACK = [
    # In the UK list too, under another key: linked, not copied
    {
        "k": "gbif:5219243",
        "r": "species",
        "s": "Vulpes vulpes",
        "c": "Red Fox",
        "l": ["Animalia", "Chordata", "Mammalia", "Carnivora", "Canidae"],
        "pr": 500,
    },
    {
        "k": "gbif:9504470",
        "r": "species",
        "s": "Turdus migratorius",
        "c": "American Robin",
        "l": [*_BIRD, "Turdidae"],
        "pr": 9000,
    },
    {
        "k": "gbif:2481139",
        "r": "species",
        "s": "Larus argentatus",
        "c": "American Herring Gull",
        "l": ["Animalia", "Chordata", "Aves", "Charadriiformes", "Laridae"],
        "pr": 300,
    },
    # Only in the US
    {
        "k": "gbif:2490384",
        "r": "species",
        "s": "Cardinalis cardinalis",
        "c": "Northern Cardinal",
        "en": ["Redbird"],
        "l": [*_BIRD, "Cardinalidae"],
        "pr": 8000,
    },
    {
        "k": "gbif:5133088",
        "r": "species",
        "s": "Danaus plexippus",
        "c": "Monarch",
        "l": ["Animalia", "Arthropoda", "Insecta", "Lepidoptera", "Nymphalidae"],
        "pr": 4000,
    },
]


def serve_us_pack(ctx, records=None) -> list[str]:
    """Make ctx.species_packs fetch from a pretend internet offering one pack, California,
    built from US_PACK (never the real internet). Returns the list of urls asked for."""
    import gzip
    import hashlib
    import json

    from wildlife.services.species_packs import MANIFEST_URL

    data = gzip.compress("".join(json.dumps(r) + "\n" for r in records or US_PACK).encode("utf-8"))
    pack_url = "https://github.com/nevermore1983/Thicket/releases/download/packs-test/us-ca.jsonl.gz"
    manifest = {
        "format": 1,
        "created": "2026-10-18",
        "packs": [
            {
                "region": "us-ca",
                "name": "California",
                "file": "us-ca.jsonl.gz",
                "species": len(records or US_PACK),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "url": pack_url,
            }
        ],
    }
    served = {MANIFEST_URL: json.dumps(manifest).encode("utf-8"), pack_url: data}
    asked: list[str] = []

    def fetch(url: str) -> bytes:
        asked.append(url)
        return served[url]

    ctx.species_packs._fetch = fetch
    return asked
