"""Phase 3 spike: prove the v1 schema works, and is fast at stress-test scale.

Run from the project folder:
    uv run --no-project --python 3.13 spikes/schema_check/check_schema.py

What it does
  1. Builds a fresh database from docs/design/schema_v1.sql using the planned
     migration approach (one atomic script per schema version).
  2. Checks that bad data is rejected and that a failed migration rolls back.
  3. Generates a stress dataset (20k sightings, 40k taxa, 5k photos, ...).
  4. Runs the query behind every screen, timing it and reporting whether it
     reads a whole table ("SCAN") or jumps straight in via an index ("SEARCH").
  5. Backs up with SQLite's online backup API and verifies the copy.

This is throwaway code. Its job is to inform the real implementation.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import sqlite3
import statistics
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "docs" / "design" / "schema_v1.sql"

N_SYNTHETIC_TAXA = 40_000
N_PLACES = 300
N_OUTINGS = 1_500
N_SIGHTINGS = 20_000
N_PHOTOS = 5_000
N_INBOX_PHOTOS = 300

rng = random.Random(42)


# ---------------------------------------------------------------------------
# Connection + transaction helpers (prototype of src/wildlife/data/db.py)
# ---------------------------------------------------------------------------
def connect(path: Path) -> sqlite3.Connection:
    # autocommit=True: Python never opens transactions behind our back;
    # we open them explicitly with BEGIN IMMEDIATE.
    conn = sqlite3.connect(path, autocommit=True)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def apply_migration(conn: sqlite3.Connection, version: int, sql: str) -> None:
    """Apply one migration script atomically, then bump user_version."""
    script = f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;"
    try:
        conn.executescript(script)
    except sqlite3.Error:
        # With autocommit=True, conn.rollback() is a no-op, so roll back explicitly.
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


# ---------------------------------------------------------------------------
# 1 + 2. Build schema, constraint tests, migration rollback test
# ---------------------------------------------------------------------------
checks: list[tuple[str, bool, str]] = []


def expect_rejected(conn, label, sql, params=()):
    try:
        with transaction(conn):
            conn.execute(sql, params)
    except sqlite3.IntegrityError as exc:
        checks.append((f"rejects {label}", True, str(exc)[:70]))
    else:
        checks.append((f"rejects {label}", False, "was ACCEPTED"))


def expect_accepted(conn, label, sql, params=()):
    try:
        with transaction(conn):
            conn.execute(sql, params)
    except sqlite3.Error as exc:
        checks.append((f"accepts {label}", False, str(exc)[:70]))
    else:
        checks.append((f"accepts {label}", True, ""))


def constraint_tests(conn):
    with transaction(conn):
        conn.execute(
            "INSERT INTO taxon (id, scientific_name, rank, category_id, is_custom) "
            "VALUES (900001, 'Testus testus', 'species', 11, 1)"
        )
        conn.execute(
            "INSERT INTO place (id, name, latitude, longitude) VALUES (900001, 'Test place', 51.5, -0.1)"
        )
    ins = "INSERT INTO sighting (uuid, taxon_id, observed_date{extra_cols}) VALUES (?, ?, ?{extra_vals})"

    def sql(extra=()):
        cols = "".join(f", {c}" for c in extra)
        vals = "".join(", ?" for _ in extra)
        return ins.format(extra_cols=cols, extra_vals=vals)

    u = lambda: str(uuid.uuid4())  # noqa: E731
    expect_accepted(conn, "minimal sighting (species + date)", sql(), (u(), 900001, "2026-10-11"))
    expect_accepted(conn, "leap day 2024-02-29", sql(), (u(), 900001, "2024-02-29"))
    expect_accepted(conn, "time 23:59", sql(["observed_time"]), (u(), 900001, "2026-10-11", "23:59"))
    expect_rejected(conn, "impossible date 2026-02-30", sql(), (u(), 900001, "2026-02-30"))
    expect_rejected(conn, "UK-style date 11/10/2026", sql(), (u(), 900001, "11/10/2026"))
    expect_rejected(conn, "time '9:30' (needs 09:30)", sql(["observed_time"]), (u(), 900001, "2026-10-11", "9:30"))
    expect_rejected(conn, "time 24:00", sql(["observed_time"]), (u(), 900001, "2026-10-11", "24:00"))
    expect_rejected(conn, "latitude 200", sql(["latitude", "longitude"]), (u(), 900001, "2026-10-11", 200.0, 0.0))
    expect_rejected(conn, "latitude without longitude", sql(["latitude"]), (u(), 900001, "2026-10-11", 51.5))
    expect_rejected(conn, "count 0", sql(["count"]), (u(), 900001, "2026-10-11", 0))
    expect_rejected(conn, "count 'abc' (STRICT typing)", sql(["count"]), (u(), 900001, "2026-10-11", "abc"))
    expect_rejected(conn, "unknown evidence code", sql(["evidence"]), (u(), 900001, "2026-10-11", "spotted"))
    expect_rejected(conn, "missing species (FK)", sql(), (u(), 123456789, "2026-10-11"))
    expect_rejected(conn, "duplicate uuid", sql(), (_dup_uuid(conn), 900001, "2026-10-11"))
    expect_rejected(conn, "non-JSON setting value", "INSERT INTO setting (key, value) VALUES ('x', 'not json')")
    expect_rejected(conn, "second fallback category",
                    "INSERT INTO category (name, colour, icon, is_fallback) VALUES ('Other 2', '#000000', 'x', 1)")
    expect_rejected(conn, "bad colour", "INSERT INTO category (name, colour, icon) VALUES ('Bad', 'red', 'x')")
    with transaction(conn):
        conn.execute(sql(["place_id"]), (u(), 900001, "2026-10-11", 900001))
    expect_rejected(conn, "deleting a species in use", "DELETE FROM taxon WHERE id = 900001")
    expect_rejected(conn, "deleting a place in use", "DELETE FROM place WHERE id = 900001")

    # Clean up the test rows so they don't skew the benchmark.
    with transaction(conn):
        conn.execute("DELETE FROM sighting WHERE taxon_id = 900001")
        conn.execute("DELETE FROM place WHERE id = 900001")
        conn.execute("DELETE FROM taxon WHERE id = 900001")


def _dup_uuid(conn):
    return conn.execute("SELECT uuid FROM sighting LIMIT 1").fetchone()[0]


def migration_rollback_test(conn):
    before = conn.execute("PRAGMA user_version").fetchone()[0]
    broken = "CREATE TABLE should_not_exist (id INTEGER PRIMARY KEY);\nTHIS IS NOT SQL;"
    try:
        apply_migration(conn, before + 1, broken)
    except sqlite3.Error:
        pass
    after = conn.execute("PRAGMA user_version").fetchone()[0]
    leftover = conn.execute(
        "SELECT COUNT(*) FROM sqlite_schema WHERE name = 'should_not_exist'"
    ).fetchone()[0]
    checks.append(("failed migration leaves version unchanged", after == before, f"user_version={after}"))
    checks.append(("failed migration leaves no half-applied changes", leftover == 0, f"leftover tables={leftover}"))


# ---------------------------------------------------------------------------
# 3. Stress dataset
# ---------------------------------------------------------------------------
# (common name, scientific name, phylum, class, order, family, weight)
REAL_SPECIES = [
    ("Robin", "Erithacus rubecula", "Chordata", "Aves", "Passeriformes", "Muscicapidae", 60),
    ("Blackbird", "Turdus merula", "Chordata", "Aves", "Passeriformes", "Turdidae", 60),
    ("Blue Tit", "Cyanistes caeruleus", "Chordata", "Aves", "Passeriformes", "Paridae", 55),
    ("Great Tit", "Parus major", "Chordata", "Aves", "Passeriformes", "Paridae", 45),
    ("Goldfinch", "Carduelis carduelis", "Chordata", "Aves", "Passeriformes", "Fringillidae", 40),
    ("Goldcrest", "Regulus regulus", "Chordata", "Aves", "Passeriformes", "Regulidae", 15),
    ("Chaffinch", "Fringilla coelebs", "Chordata", "Aves", "Passeriformes", "Fringillidae", 30),
    ("House Sparrow", "Passer domesticus", "Chordata", "Aves", "Passeriformes", "Passeridae", 40),
    ("Starling", "Sturnus vulgaris", "Chordata", "Aves", "Passeriformes", "Sturnidae", 30),
    ("Wren", "Troglodytes troglodytes", "Chordata", "Aves", "Passeriformes", "Troglodytidae", 30),
    ("Dunnock", "Prunella modularis", "Chordata", "Aves", "Passeriformes", "Prunellidae", 20),
    ("Woodpigeon", "Columba palumbus", "Chordata", "Aves", "Columbiformes", "Columbidae", 50),
    ("Magpie", "Pica pica", "Chordata", "Aves", "Passeriformes", "Corvidae", 35),
    ("Carrion Crow", "Corvus corone", "Chordata", "Aves", "Passeriformes", "Corvidae", 30),
    ("Jackdaw", "Corvus monedula", "Chordata", "Aves", "Passeriformes", "Corvidae", 20),
    ("Jay", "Garrulus glandarius", "Chordata", "Aves", "Passeriformes", "Corvidae", 10),
    ("Grey Heron", "Ardea cinerea", "Chordata", "Aves", "Pelecaniformes", "Ardeidae", 20),
    ("Little Egret", "Egretta garzetta", "Chordata", "Aves", "Pelecaniformes", "Ardeidae", 10),
    ("Mute Swan", "Cygnus olor", "Chordata", "Aves", "Anseriformes", "Anatidae", 20),
    ("Mallard", "Anas platyrhynchos", "Chordata", "Aves", "Anseriformes", "Anatidae", 30),
    ("Canada Goose", "Branta canadensis", "Chordata", "Aves", "Anseriformes", "Anatidae", 15),
    ("Coot", "Fulica atra", "Chordata", "Aves", "Gruiformes", "Rallidae", 15),
    ("Moorhen", "Gallinula chloropus", "Chordata", "Aves", "Gruiformes", "Rallidae", 15),
    ("Kingfisher", "Alcedo atthis", "Chordata", "Aves", "Coraciiformes", "Alcedinidae", 4),
    ("Buzzard", "Buteo buteo", "Chordata", "Aves", "Accipitriformes", "Accipitridae", 15),
    ("Red Kite", "Milvus milvus", "Chordata", "Aves", "Accipitriformes", "Accipitridae", 10),
    ("Kestrel", "Falco tinnunculus", "Chordata", "Aves", "Falconiformes", "Falconidae", 8),
    ("Sparrowhawk", "Accipiter nisus", "Chordata", "Aves", "Accipitriformes", "Accipitridae", 5),
    ("Barn Owl", "Tyto alba", "Chordata", "Aves", "Strigiformes", "Tytonidae", 3),
    ("Tawny Owl", "Strix aluco", "Chordata", "Aves", "Strigiformes", "Strigidae", 3),
    ("Great Spotted Woodpecker", "Dendrocopos major", "Chordata", "Aves", "Piciformes", "Picidae", 10),
    ("Green Woodpecker", "Picus viridis", "Chordata", "Aves", "Piciformes", "Picidae", 6),
    ("Black-headed Gull", "Chroicocephalus ridibundus", "Chordata", "Aves", "Charadriiformes", "Laridae", 20),
    ("Herring Gull", "Larus argentatus", "Chordata", "Aves", "Charadriiformes", "Laridae", 15),
    ("Lapwing", "Vanellus vanellus", "Chordata", "Aves", "Charadriiformes", "Charadriidae", 6),
    ("Curlew", "Numenius arquata", "Chordata", "Aves", "Charadriiformes", "Scolopacidae", 4),
    ("Avocet", "Recurvirostra avosetta", "Chordata", "Aves", "Charadriiformes", "Recurvirostridae", 3),
    ("Swallow", "Hirundo rustica", "Chordata", "Aves", "Passeriformes", "Hirundinidae", 10),
    ("Swift", "Apus apus", "Chordata", "Aves", "Apodiformes", "Apodidae", 8),
    ("Chiffchaff", "Phylloscopus collybita", "Chordata", "Aves", "Passeriformes", "Phylloscopidae", 12),
    ("Blackcap", "Sylvia atricapilla", "Chordata", "Aves", "Passeriformes", "Sylviidae", 10),
    ("Long-tailed Tit", "Aegithalos caudatus", "Chordata", "Aves", "Passeriformes", "Aegithalidae", 15),
    ("White Wagtail", "Motacilla alba", "Chordata", "Aves", "Passeriformes", "Motacillidae", 2),
    ("Grey Squirrel", "Sciurus carolinensis", "Chordata", "Mammalia", "Rodentia", "Sciuridae", 30),
    ("Red Squirrel", "Sciurus vulgaris", "Chordata", "Mammalia", "Rodentia", "Sciuridae", 2),
    ("Red Fox", "Vulpes vulpes", "Chordata", "Mammalia", "Carnivora", "Canidae", 10),
    ("Badger", "Meles meles", "Chordata", "Mammalia", "Carnivora", "Mustelidae", 4),
    ("Hedgehog", "Erinaceus europaeus", "Chordata", "Mammalia", "Eulipotyphla", "Erinaceidae", 5),
    ("Rabbit", "Oryctolagus cuniculus", "Chordata", "Mammalia", "Lagomorpha", "Leporidae", 15),
    ("Brown Hare", "Lepus europaeus", "Chordata", "Mammalia", "Lagomorpha", "Leporidae", 4),
    ("Roe Deer", "Capreolus capreolus", "Chordata", "Mammalia", "Artiodactyla", "Cervidae", 6),
    ("Reeves's Muntjac", "Muntiacus reevesi", "Chordata", "Mammalia", "Artiodactyla", "Cervidae", 5),
    ("Grey Seal", "Halichoerus grypus", "Chordata", "Mammalia", "Carnivora", "Phocidae", 2),
    ("Otter", "Lutra lutra", "Chordata", "Mammalia", "Carnivora", "Mustelidae", 1),
    ("Common Pipistrelle", "Pipistrellus pipistrellus", "Chordata", "Mammalia", "Chiroptera", "Vespertilionidae", 5),
    ("Stoat", "Mustela erminea", "Chordata", "Mammalia", "Carnivora", "Mustelidae", 1),
    ("Red Admiral", "Vanessa atalanta", "Arthropoda", "Insecta", "Lepidoptera", "Nymphalidae", 12),
    ("Peacock", "Aglais io", "Arthropoda", "Insecta", "Lepidoptera", "Nymphalidae", 12),
    ("Small Tortoiseshell", "Aglais urticae", "Arthropoda", "Insecta", "Lepidoptera", "Nymphalidae", 8),
    ("Comma", "Polygonia c-album", "Arthropoda", "Insecta", "Lepidoptera", "Nymphalidae", 6),
    ("Brimstone", "Gonepteryx rhamni", "Arthropoda", "Insecta", "Lepidoptera", "Pieridae", 8),
    ("Orange-tip", "Anthocharis cardamines", "Arthropoda", "Insecta", "Lepidoptera", "Pieridae", 6),
    ("Large White", "Pieris brassicae", "Arthropoda", "Insecta", "Lepidoptera", "Pieridae", 10),
    ("Small White", "Pieris rapae", "Arthropoda", "Insecta", "Lepidoptera", "Pieridae", 10),
    ("Common Blue", "Polyommatus icarus", "Arthropoda", "Insecta", "Lepidoptera", "Lycaenidae", 6),
    ("Meadow Brown", "Maniola jurtina", "Arthropoda", "Insecta", "Lepidoptera", "Nymphalidae", 12),
    ("Gatekeeper", "Pyronia tithonus", "Arthropoda", "Insecta", "Lepidoptera", "Nymphalidae", 8),
    ("Speckled Wood", "Pararge aegeria", "Arthropoda", "Insecta", "Lepidoptera", "Nymphalidae", 8),
    ("Painted Lady", "Vanessa cardui", "Arthropoda", "Insecta", "Lepidoptera", "Nymphalidae", 3),
    ("Elephant Hawk-moth", "Deilephila elpenor", "Arthropoda", "Insecta", "Lepidoptera", "Sphingidae", 3),
    ("Large Yellow Underwing", "Noctua pronuba", "Arthropoda", "Insecta", "Lepidoptera", "Noctuidae", 6),
    ("Cinnabar", "Tyria jacobaeae", "Arthropoda", "Insecta", "Lepidoptera", "Erebidae", 3),
    ("Common Darter", "Sympetrum striolatum", "Arthropoda", "Insecta", "Odonata", "Libellulidae", 8),
    ("Ruddy Darter", "Sympetrum sanguineum", "Arthropoda", "Insecta", "Odonata", "Libellulidae", 3),
    ("Broad-bodied Chaser", "Libellula depressa", "Arthropoda", "Insecta", "Odonata", "Libellulidae", 4),
    ("Emperor Dragonfly", "Anax imperator", "Arthropoda", "Insecta", "Odonata", "Aeshnidae", 4),
    ("Southern Hawker", "Aeshna cyanea", "Arthropoda", "Insecta", "Odonata", "Aeshnidae", 4),
    ("Banded Demoiselle", "Calopteryx splendens", "Arthropoda", "Insecta", "Odonata", "Calopterygidae", 5),
    ("Azure Damselfly", "Coenagrion puella", "Arthropoda", "Insecta", "Odonata", "Coenagrionidae", 6),
    ("Large Red Damselfly", "Pyrrhosoma nymphula", "Arthropoda", "Insecta", "Odonata", "Coenagrionidae", 5),
    ("Common Frog", "Rana temporaria", "Chordata", "Amphibia", "Anura", "Ranidae", 6),
    ("Common Toad", "Bufo bufo", "Chordata", "Amphibia", "Anura", "Bufonidae", 4),
    ("Smooth Newt", "Lissotriton vulgaris", "Chordata", "Amphibia", "Caudata", "Salamandridae", 3),
    ("Great Crested Newt", "Triturus cristatus", "Chordata", "Amphibia", "Caudata", "Salamandridae", 1),
    ("Grass Snake", "Natrix helvetica", "Chordata", "Reptilia", "Squamata", "Natricidae", 2),
    ("Adder", "Vipera berus", "Chordata", "Reptilia", "Squamata", "Viperidae", 1),
    ("Slow-worm", "Anguis fragilis", "Chordata", "Reptilia", "Squamata", "Anguidae", 2),
    ("Common Lizard", "Zootoca vivipara", "Chordata", "Reptilia", "Squamata", "Lacertidae", 2),
    ("Brown Trout", "Salmo trutta", "Chordata", "Actinopteri", "Salmoniformes", "Salmonidae", 1),
    ("Atlantic Salmon", "Salmo salar", "Chordata", "Actinopteri", "Salmoniformes", "Salmonidae", 1),
    ("Three-spined Stickleback", "Gasterosteus aculeatus", "Chordata", "Actinopteri", "Gasterosteiformes", "Gasterosteidae", 1),
    ("Buff-tailed Bumblebee", "Bombus terrestris", "Arthropoda", "Insecta", "Hymenoptera", "Apidae", 10),
    ("Western Honey Bee", "Apis mellifera", "Arthropoda", "Insecta", "Hymenoptera", "Apidae", 8),
    ("Seven-spot Ladybird", "Coccinella septempunctata", "Arthropoda", "Insecta", "Coleoptera", "Coccinellidae", 8),
    ("Stag Beetle", "Lucanus cervus", "Arthropoda", "Insecta", "Coleoptera", "Lucanidae", 2),
    ("Common Wasp", "Vespula vulgaris", "Arthropoda", "Insecta", "Hymenoptera", "Vespidae", 5),
    ("Marmalade Hoverfly", "Episyrphus balteatus", "Arthropoda", "Insecta", "Diptera", "Syrphidae", 5),
    ("Garden Spider", "Araneus diadematus", "Arthropoda", "Arachnida", "Araneae", "Araneidae", 5),
    ("Wasp Spider", "Argiope bruennichi", "Arthropoda", "Arachnida", "Araneae", "Araneidae", 1),
    ("Garden Snail", "Cornu aspersum", "Mollusca", "Gastropoda", "Stylommatophora", "Helicidae", 4),
    ("Common Earthworm", "Lumbricus terrestris", "Annelida", "Clitellata", "Crassiclitellata", "Lumbricidae", 2),
    ("Edible Crab", "Cancer pagurus", "Arthropoda", "Malacostraca", "Decapoda", "Cancridae", 1),
]

SYNTHETIC_GROUPS = [  # (phylum, class, [orders], share)
    ("Arthropoda", "Insecta", ["Coleoptera", "Diptera", "Hymenoptera", "Hemiptera", "Trichoptera"], 0.55),
    ("Arthropoda", "Insecta", ["Lepidoptera"], 0.15),
    ("Arthropoda", "Arachnida", ["Araneae", "Acari", "Opiliones"], 0.08),
    ("Arthropoda", "Malacostraca", ["Decapoda", "Isopoda", "Amphipoda"], 0.05),
    ("Mollusca", "Gastropoda", ["Stylommatophora", "Littorinimorpha"], 0.06),
    ("Annelida", "Polychaeta", ["Phyllodocida"], 0.04),
    ("Chordata", "Aves", ["Passeriformes", "Charadriiformes"], 0.03),
    ("Chordata", "Actinopteri", ["Perciformes", "Cypriniformes"], 0.03),
    ("Chordata", "Ascidiacea", ["Stolidobranchia"], 0.01),
]
SYLLABLES = ["ar", "bel", "cor", "dra", "ex", "fu", "gal", "hor", "ix", "lep", "mor", "nax",
             "op", "pra", "quel", "ros", "sil", "tor", "ul", "ven", "xan", "zor"]
ADJ = ["Lesser", "Greater", "Mottled", "Common", "Northern", "Dusky", "Small", "Pale", "Spotted", "Marsh"]
NOUN = ["Weevil", "Shieldbug", "Hoverfly", "Carpet", "Pug", "Wolf Spider", "Sawfly", "Snail", "Chafer", "Mayfly"]
NOTE_BITS = ["feeding on the mudflats", "pair seen near the nest", "heron fishing in the reeds",
             "flushed from the hedge", "singing from the top of an oak", "carrying food",
             "displaying", "basking on the path", "came to the moth trap", "in the garden pond",
             "chased off by crows", "juveniles with parents", "under the bridge", "very confiding",
             "distant views only", "heard calling at dusk"]


def lat_lon_near(lat, lon, metres):
    d = metres / 111_320
    return (round(lat + rng.uniform(-d, d), 6),
            round(lon + rng.uniform(-d, d) / math.cos(math.radians(lat)), 6))


def build_dataset(conn):
    t0 = time.perf_counter()
    with transaction(conn):
        # --- taxa -----------------------------------------------------------
        taxa = []
        next_id = 1
        for i, (common, sci, phy, cls, order, fam, _w) in enumerate(REAL_SPECIES):
            taxa.append((next_id, f"REAL{i:04d}", sci, common, "species", None, phy, cls, order, fam, 100))
            next_id += 1
        real_ids = list(range(1, next_id))
        # Subspecies (counts as its species) and a genus-level "gull species".
        white_wagtail = next(i for i, t in zip(real_ids, REAL_SPECIES) if t[0] == "White Wagtail")
        pied = next_id
        taxa.append((pied, "REALSSP1", "Motacilla alba yarrellii", "Pied Wagtail", "subspecies",
                     white_wagtail, "Chordata", "Aves", "Passeriformes", "Motacillidae", 100))
        gull_genus = next_id + 1
        taxa.append((gull_genus, "REALGEN1", "Larus", "Gull species", "genus", None,
                     "Chordata", "Aves", "Charadriiformes", "Laridae", 50))
        next_id += 2

        shares = [g[3] for g in SYNTHETIC_GROUPS]
        for n in range(N_SYNTHETIC_TAXA):
            phy, cls, orders, _ = rng.choices(SYNTHETIC_GROUPS, weights=shares)[0]
            genus = "".join(rng.choices(SYLLABLES, k=3)).capitalize()
            sci = f"{genus} {''.join(rng.choices(SYLLABLES, k=3))}"
            common = f"{rng.choice(ADJ)} {genus} {rng.choice(NOUN)}" if rng.random() < 0.25 else None
            taxa.append((next_id, f"SYN{n:06d}", sci, common, "species", None, phy, cls,
                         rng.choice(orders), f"{genus}idae", 0))
            next_id += 1

        conn.executemany(
            "INSERT INTO taxon (id, uksi_key, scientific_name, common_name, rank, parent_id, "
            "tax_kingdom, tax_phylum, tax_class, tax_order, tax_family, priority, category_id) "
            "VALUES (?, ?, ?, ?, ?, ?, 'Animalia', ?, ?, ?, ?, ?, 11)",
            taxa,
        )
        # species_id: self for species, parent for subspecies, NULL for broader ranks.
        conn.execute("UPDATE taxon SET species_id = id WHERE rank = 'species'")
        conn.execute("UPDATE taxon SET species_id = parent_id WHERE rank = 'subspecies'")
        resolve_categories(conn)
        conn.execute(
            "INSERT INTO taxon_name (taxon_id, name, kind) "
            "SELECT id, scientific_name, 'scientific' FROM taxon"
        )
        conn.execute(
            "INSERT INTO taxon_name (taxon_id, name, kind) "
            "SELECT id, common_name, 'common' FROM taxon WHERE common_name IS NOT NULL"
        )

        # --- places ---------------------------------------------------------
        places = []
        for i in range(N_PLACES):
            lat, lon = rng.uniform(50.2, 57.5), rng.uniform(-5.0, 1.6)
            name = f"{rng.choice(['North', 'South', 'Upper', 'Lower', 'Old', 'Great'])} " \
                   f"{''.join(rng.choices(SYLLABLES, k=2)).capitalize()} " \
                   f"{rng.choice(['Marsh', 'Wood', 'Common', 'Reservoir', 'Heath', 'Bay', 'Park'])}"
            places.append((i + 1, name, round(lat, 6), round(lon, 6), rng.choice([100, 250, 500, 1000])))
        places[0] = (1, "Garden", 51.52, -0.11, 50)
        conn.executemany("INSERT INTO place (id, name, latitude, longitude, radius_m) VALUES (?, ?, ?, ?, ?)", places)
        place_by_id = {p[0]: p for p in places}

        # --- outings --------------------------------------------------------
        start = date(2015, 1, 1)
        span = (date(2026, 10, 10) - start).days
        outings = []
        for i in range(N_OUTINGS):
            d = start + timedelta(days=rng.randrange(span))
            outings.append((i + 1, str(uuid.uuid4()), d.isoformat(), f"{rng.randint(6, 15):02d}:00",
                            rng.randint(2, N_PLACES), rng.choice(["sunny", "overcast", "rain", None])))
        conn.executemany(
            "INSERT INTO outing (id, uuid, outing_date, start_time, place_id, weather) VALUES (?, ?, ?, ?, ?, ?)",
            outings,
        )

        # --- sightings ------------------------------------------------------
        weights = [s[6] for s in REAL_SPECIES]
        synthetic_ids = list(range(gull_genus + 1, next_id))
        rows = []
        for i in range(N_SIGHTINGS):
            r = rng.random()
            taxon = (rng.choices(real_ids, weights=weights)[0] if r < 0.80
                     else pied if r < 0.81 else gull_genus if r < 0.82 else rng.choice(synthetic_ids))
            if rng.random() < 0.7:
                o = rng.choice(outings)
                outing_id, obs_date, place_id = o[0], o[2], o[4]
            else:
                outing_id = None
                # Seasonal bias: more sightings Apr-Aug.
                while True:
                    d = start + timedelta(days=rng.randrange(span))
                    if rng.random() < (0.35 + 0.65 * math.sin(math.pi * (d.month - 1) / 11)):
                        break
                obs_date = d.isoformat()
                place_id = 1 if rng.random() < 0.4 else rng.randint(2, N_PLACES)
            obs_time = (f"{min(23, max(0, int(rng.gauss(11, 3.5)))):02d}:{rng.randrange(60):02d}"
                        if rng.random() < 0.85 else None)
            lat = lon = unc = method = None
            loc = rng.random()
            if loc < 0.60 and place_id:
                p = place_by_id[place_id]
                lat, lon = lat_lon_near(p[2], p[3], p[4])
                unc, method = rng.choice([10, 10, 100]), rng.choice(["map", "photo", "grid_ref"])
            elif loc < 0.85:
                method = "place"
            elif loc < 0.95:
                place_id = None
                lat, lon = round(rng.uniform(50.2, 57.5), 6), round(rng.uniform(-5.0, 1.6), 6)
                unc, method = 100, "typed"
            else:
                place_id = None  # no location at all -> "Needs attention"
            notes = (", ".join(rng.sample(NOTE_BITS, k=rng.randint(1, 3))).capitalize() + "."
                     if rng.random() < 0.4 else None)
            rows.append((
                str(uuid.uuid4()), taxon, obs_date, obs_time, place_id, lat, lon, unc, method,
                rng.choice([1, 1, 1, 2, 3, 5, 12, None]),
                rng.choices(["seen", "heard", "seen_heard", "signs", "trapped"], weights=[70, 12, 10, 4, 4])[0],
                rng.choices(["certain", "probable", "possible"], weights=[90, 7, 3])[0],
                1 if rng.random() < 0.01 else 0, outing_id, notes,
                "2026-01-01T00:00:00Z" if rng.random() < 0.01 else None,
            ))
        conn.executemany(
            "INSERT INTO sighting (uuid, taxon_id, observed_date, observed_time, place_id, latitude, longitude, "
            "uncertainty_m, location_method, count, evidence, identification, is_not_wild, outing_id, notes, deleted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

        # --- photos ---------------------------------------------------------
        photo_rows, links = [], []
        for i in range(N_PHOTOS):
            sha = hashlib.sha256(f"photo-{i}".encode()).hexdigest()
            photo_rows.append((i + 1, str(uuid.uuid4()), sha, f"photos/2025/06/{sha}.jpg", f"IMG_{i:05d}.JPG",
                               rng.randint(1_500_000, 6_000_000), 4032, 3024))
            if i >= N_INBOX_PHOTOS:
                links.append((rng.randint(1, N_SIGHTINGS), i + 1, rng.randint(0, 3)))
        conn.executemany(
            "INSERT INTO photo (id, uuid, sha256, rel_path, original_name, file_size, width, height) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            photo_rows,
        )
        conn.executemany(
            "INSERT OR IGNORE INTO sighting_photo (sighting_id, photo_id, sort_order) VALUES (?, ?, ?)", links
        )
    conn.execute("ANALYZE")  # gives SQLite's query planner statistics about the data
    return time.perf_counter() - t0, len(taxa)


def resolve_categories(conn):
    """Most specific matching rule wins; falls back to the fallback category."""
    conn.execute("""
        UPDATE taxon SET category_id = COALESCE(
            (SELECT category_id FROM category_rule WHERE rank = 'family'  AND taxon_name = taxon.tax_family),
            (SELECT category_id FROM category_rule WHERE rank = 'order'   AND taxon_name = taxon.tax_order),
            (SELECT category_id FROM category_rule WHERE rank = 'class'   AND taxon_name = taxon.tax_class),
            (SELECT category_id FROM category_rule WHERE rank = 'phylum'  AND taxon_name = taxon.tax_phylum),
            (SELECT category_id FROM category_rule WHERE rank = 'kingdom' AND taxon_name = taxon.tax_kingdom),
            (SELECT id FROM category WHERE is_fallback = 1))
        WHERE category_is_manual = 0
    """)


# ---------------------------------------------------------------------------
# 4. The query behind every screen
# ---------------------------------------------------------------------------
# A sighting counts towards lists when: species rank or below, wild, and the
# identification is good enough. Probable IDs are a user setting.
COUNTABLE = "species_id IS NOT NULL AND is_not_wild = 0 AND identification IN ('certain')"

results: list[tuple[str, float, int, list[str]]] = []


def bench(conn, label, sql, params=(), runs=7):
    plan = [row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + sql, params)]
    times = []
    rows = []
    for _ in range(runs):
        t = time.perf_counter()
        rows = conn.execute(sql, params).fetchall()
        times.append((time.perf_counter() - t) * 1000)
    scans = sorted({p for p in plan if p.startswith("SCAN") and "VIRTUAL TABLE" not in p})
    results.append((label, statistics.median(times), len(rows), scans))
    return rows


def picker_sql(fragment: str) -> tuple[str, dict]:
    """Species picker: ranked suggestions for what the user has typed so far."""
    if len(fragment) >= 3:  # trigram index needs 3+ characters
        match = "taxon_name_fts MATCH :fts"
        source = "taxon_name_fts f JOIN taxon_name n ON n.id = f.rowid"
    else:
        match = "n.name LIKE :q || '%'"
        source = "taxon_name n"
    sql = f"""
        WITH hits AS (
            SELECT n.taxon_id,
                   CASE WHEN n.name LIKE :q || '%'        THEN 0   -- name starts with it
                        WHEN n.name LIKE '% ' || :q || '%' THEN 1  -- a word starts with it
                        ELSE 2 END AS match_rank
            FROM {source}
            WHERE {match}
        ),
        usage AS (
            SELECT taxon_id, COUNT(*) AS n, MAX(observed_date) AS last_seen
            FROM sighting WHERE deleted_at IS NULL GROUP BY taxon_id
        )
        SELECT t.id, t.common_name, t.scientific_name, MIN(h.match_rank) AS match_rank, u.n AS uses
        FROM hits h
        JOIN taxon t ON t.id = h.taxon_id
        LEFT JOIN usage u ON u.taxon_id = t.id
        WHERE t.is_hidden = 0
        GROUP BY t.id
        ORDER BY (u.n IS NULL), match_rank, u.n DESC, t.priority DESC,
                 length(COALESCE(t.common_name, t.scientific_name))
        LIMIT 20
    """
    return sql, {"q": fragment, "fts": '"' + fragment.replace('"', '""') + '"'}


def run_queries(conn):
    y, ny, m, nm = "2025-01-01", "2026-01-01", "2025-06-01", "2025-07-01"

    bench(conn, "Dashboard: headline tiles", f"""
        SELECT (SELECT COUNT(*) FROM sighting_v),
               (SELECT COUNT(DISTINCT species_id) FROM sighting_v WHERE {COUNTABLE}),
               (SELECT COUNT(DISTINCT species_id) FROM sighting_v WHERE {COUNTABLE}
                    AND observed_date >= :y AND observed_date < :ny),
               (SELECT COUNT(*) FROM sighting_v WHERE observed_date >= :m AND observed_date < :nm)
    """, {"y": y, "ny": ny, "m": m, "nm": nm})

    bench(conn, "Dashboard: 10 recent + cover photo", """
        SELECT v.id, v.common_name, v.place_name, v.observed_date, v.observed_time,
               (SELECT p.rel_path FROM sighting_photo sp JOIN photo p ON p.id = sp.photo_id
                 WHERE sp.sighting_id = v.id AND p.deleted_at IS NULL
                 ORDER BY sp.sort_order LIMIT 1) AS cover
        FROM sighting_v v
        ORDER BY v.observed_date DESC, v.observed_time DESC LIMIT 10
    """)

    bench(conn, "Dashboard: needs attention", """
        SELECT (SELECT COUNT(*) FROM sighting_v WHERE eff_latitude IS NULL),
               (SELECT COUNT(*) FROM photo p WHERE p.deleted_at IS NULL
                   AND NOT EXISTS (SELECT 1 FROM sighting_photo sp WHERE sp.photo_id = p.id))
    """)

    list_where = "v.category_id IN (1, 6) AND v.observed_date >= '2020-01-01' AND v.observed_date < '2026-01-01'"
    bench(conn, "Sightings list: filtered page (offset 5000)", f"""
        SELECT v.id, v.common_name, v.scientific_name, v.category_id, v.observed_date, v.observed_time,
               v.place_name, v.count, v.evidence
        FROM sighting_v v WHERE {list_where}
        ORDER BY v.observed_date DESC, v.observed_time DESC, v.id DESC LIMIT 200 OFFSET 5000
    """)
    bench(conn, "Sightings list: footer totals", f"""
        SELECT COUNT(*), COUNT(DISTINCT CASE WHEN {COUNTABLE} THEN species_id END)
        FROM sighting_v v WHERE {list_where}
    """)
    bench(conn, "Sightings list: sort by species name", """
        SELECT v.id FROM sighting_v v
        ORDER BY COALESCE(v.common_name, v.scientific_name), v.observed_date DESC LIMIT 200
    """)

    for frag in ("ro", "gold", "finch", "erith"):
        sql, params = picker_sql(frag)
        rows = bench(conn, f"Species picker: '{frag}'", sql, params)
        top = ", ".join(r[1] or r[2] for r in rows[:4])
        print(f"    picker '{frag}' -> {top}")

    bench(conn, "Global search: notes 'heron'", """
        SELECT v.id, v.common_name, v.observed_date
        FROM sighting_text_fts f JOIN sighting_v v ON v.id = f.rowid
        WHERE sighting_text_fts MATCH '"heron"'
        ORDER BY v.observed_date DESC LIMIT 50
    """)
    bench(conn, "Global search: places 'marsh'", """
        SELECT id, name FROM place WHERE name LIKE '%' || 'marsh' || '%' AND is_archived = 0 LIMIT 20
    """)

    bench(conn, "Calendar: month (per-day counts + categories)", """
        SELECT observed_date, COUNT(*), group_concat(DISTINCT category_id)
        FROM sighting_v WHERE observed_date >= '2025-05-01' AND observed_date < '2025-06-01'
        GROUP BY observed_date
    """)
    bench(conn, "Calendar: year (per-day counts)", """
        SELECT observed_date, COUNT(*) FROM sighting_v
        WHERE observed_date >= :y AND observed_date < :ny GROUP BY observed_date
    """, {"y": y, "ny": ny})
    bench(conn, "Calendar: week cards", """
        SELECT id, common_name, observed_date, observed_time, place_name, category_id
        FROM sighting_v WHERE observed_date >= '2025-05-12' AND observed_date < '2025-05-19'
        ORDER BY observed_date, observed_time IS NOT NULL, observed_time
    """)

    map_rows = bench(conn, "Map: all points with a location", """
        SELECT id, eff_latitude, eff_longitude, category_id, COALESCE(common_name, scientific_name), observed_date
        FROM sighting_v WHERE eff_latitude IS NOT NULL
    """)
    t = time.perf_counter()
    geojson = json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": r[0],
         "geometry": {"type": "Point", "coordinates": [r[2], r[1]]},
         "properties": {"c": r[3], "n": r[4], "d": r[5]}} for r in map_rows]}, separators=(",", ":"))
    results.append(("Map: build GeoJSON in Python", (time.perf_counter() - t) * 1000, len(map_rows), []))
    t = time.perf_counter()
    squares: dict[tuple[int, int], set] = {}
    for r in map_rows:  # rough 1 km binning; the real app converts to OS grid squares
        key = (int(r[1] * 111.32), int(r[2] * 111.32 * math.cos(math.radians(r[1]))))
        squares.setdefault(key, set()).add(r[4])
    results.append(("Map: species-per-1km-square (Python)", (time.perf_counter() - t) * 1000, len(squares), []))

    bench(conn, "Stats: cumulative species curve", f"""
        WITH firsts AS (
            SELECT species_id, MIN(observed_date) AS first_date
            FROM sighting_v WHERE {COUNTABLE} GROUP BY species_id
        )
        SELECT first_date, COUNT(*) OVER (ORDER BY first_date ROWS UNBOUNDED PRECEDING)
        FROM firsts ORDER BY first_date
    """)
    bench(conn, "Stats: month x category", """
        SELECT substr(observed_date, 6, 2) AS month, category_id, COUNT(*)
        FROM sighting_v WHERE observed_date >= :y AND observed_date < :ny
        GROUP BY month, category_id
    """, {"y": y, "ny": ny})
    bench(conn, "Stats: time of day", """
        SELECT CAST(substr(observed_time, 1, 2) AS INTEGER) AS hour, COUNT(*)
        FROM sighting_v WHERE observed_time IS NOT NULL GROUP BY hour
    """)
    bench(conn, "Stats: top places by species", f"""
        SELECT place_id, place_name, COUNT(DISTINCT species_id) AS species, COUNT(*) AS sightings
        FROM sighting_v WHERE place_id IS NOT NULL AND {COUNTABLE}
        GROUP BY place_id ORDER BY species DESC LIMIT 10
    """)
    bench(conn, "Stats: year-over-year species by month", f"""
        SELECT substr(observed_date, 1, 4) AS yr, substr(observed_date, 6, 2) AS mo, COUNT(DISTINCT species_id)
        FROM sighting_v WHERE {COUNTABLE} AND observed_date >= '2024-01-01' AND observed_date < '2026-01-01'
        GROUP BY yr, mo
    """)
    bench(conn, "Stats: lifers in 2025", f"""
        SELECT species_id, first_date FROM (
            SELECT species_id, MIN(observed_date) AS first_date
            FROM sighting_v WHERE {COUNTABLE} GROUP BY species_id)
        WHERE first_date >= :y AND first_date < :ny ORDER BY first_date
    """, {"y": y, "ny": ny})
    bench(conn, "Stats: firsts of year 2025", f"""
        SELECT species_id, MIN(observed_date) FROM sighting_v
        WHERE {COUNTABLE} AND observed_date >= :y AND observed_date < :ny
        GROUP BY species_id ORDER BY 2
    """, {"y": y, "ny": ny})

    bench(conn, "Species: life list table", f"""
        SELECT t.id, t.common_name, t.scientific_name, t.category_id,
               MIN(v.observed_date), MAX(v.observed_date), COUNT(*), MAX(v.count)
        FROM sighting_v v JOIN taxon t ON t.id = v.species_id
        WHERE {COUNTABLE.replace('species_id', 'v.species_id')}
        GROUP BY t.id ORDER BY COALESCE(t.common_name, t.scientific_name)
    """)
    bench(conn, "Species profile: month-of-year", """
        SELECT substr(observed_date, 6, 2), COUNT(*) FROM sighting_v
        WHERE taxon_id = 1 GROUP BY 1
    """)
    bench(conn, "Photos: library page (newest 200)", """
        SELECT DISTINCT p.id, p.rel_path, p.taken_at FROM photo p
        JOIN sighting_photo sp ON sp.photo_id = p.id
        JOIN sighting s ON s.id = sp.sighting_id AND s.deleted_at IS NULL
        WHERE p.deleted_at IS NULL ORDER BY p.taken_at DESC, p.id DESC LIMIT 200
    """)
    bench(conn, "Photos: inbox", """
        SELECT p.id, p.rel_path, p.taken_at FROM photo p
        WHERE p.deleted_at IS NULL AND NOT EXISTS (SELECT 1 FROM sighting_photo sp WHERE sp.photo_id = p.id)
        ORDER BY p.taken_at
    """)
    bench(conn, "Outing summary", f"""
        SELECT COUNT(*), COUNT(DISTINCT CASE WHEN {COUNTABLE} THEN species_id END)
        FROM sighting_v WHERE outing_id = 10
    """)
    bench(conn, "Recycle bin", """
        SELECT id, taxon_id, observed_date, deleted_at FROM sighting
        WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC
    """)
    bench(conn, "Export: every sighting, all columns", "SELECT * FROM sighting_v", runs=3)

    # --- writes -----------------------------------------------------------
    times = []
    for _ in range(50):
        t = time.perf_counter()
        with transaction(conn):
            conn.execute(
                "INSERT INTO sighting (uuid, taxon_id, observed_date, observed_time, place_id, count, notes) "
                "VALUES (?, 1, '2026-10-11', '09:30', 1, 2, 'Feeding under the bird table')",
                (str(uuid.uuid4()),),
            )
        times.append((time.perf_counter() - t) * 1000)
    results.append(("Write: save one sighting (FULL sync)", statistics.median(times), 50, []))
    t = time.perf_counter()
    with transaction(conn):
        ids = [r[0] for r in conn.execute("SELECT id FROM sighting_v WHERE taxon_id = 75 LIMIT 100")]
        conn.executemany("UPDATE sighting SET taxon_id = 74, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
                         "WHERE id = ?", [(i,) for i in ids])
    results.append(("Write: bulk change species", (time.perf_counter() - t) * 1000, len(ids), []))
    return len(geojson)


# ---------------------------------------------------------------------------
# 5. Backup + verification
# ---------------------------------------------------------------------------
def backup_test(conn, folder: Path):
    dest_path = folder / "snapshot.db"
    t = time.perf_counter()
    dest = sqlite3.connect(dest_path)
    conn.backup(dest)  # consistent copy even while the app is using the database
    dest.close()
    took = (time.perf_counter() - t) * 1000
    check = sqlite3.connect(f"file:{dest_path}?mode=ro", uri=True)
    integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
    fk_problems = check.execute("PRAGMA foreign_key_check").fetchall()
    counts_match = all(
        check.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone() == conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()
        for tbl in ("sighting", "taxon", "photo", "place", "outing", "sighting_photo")
    )
    check.close()
    checks.append(("backup: integrity_check = ok", integrity == "ok", integrity))
    checks.append(("backup: no foreign-key problems", not fk_problems, f"{len(fk_problems)} problems"))
    checks.append(("backup: row counts identical", counts_match, ""))
    return took, dest_path.stat().st_size


# ---------------------------------------------------------------------------
def main() -> int:
    print(f"Python {sys.version.split()[0]} | SQLite {sqlite3.sqlite_version}\n")
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        conn = connect(folder / "wildlife.db")
        apply_migration(conn, 1, SCHEMA.read_text(encoding="utf-8"))
        constraint_tests(conn)
        migration_rollback_test(conn)

        build_s, n_taxa = build_dataset(conn)
        print(f"Built stress dataset in {build_s:.1f} s: {n_taxa:,} taxa, {N_PLACES} places, "
              f"{N_OUTINGS:,} outings, {N_SIGHTINGS:,} sightings, {N_PHOTOS:,} photos")
        cats = conn.execute("""
            SELECT c.name, COUNT(*) FROM taxon t JOIN category c ON c.id = t.category_id
            GROUP BY c.id ORDER BY c.sort_order""").fetchall()
        print("Taxa per category (auto-assigned by rules): " + ", ".join(f"{n} {c}" for c, n in cats))
        wag = conn.execute("""
            SELECT COUNT(DISTINCT species_id) FROM sighting_v
            WHERE scientific_name LIKE 'Motacilla alba%'""").fetchone()[0]
        checks.append(("subspecies counts as its species (Pied -> White Wagtail)", wag == 1, f"{wag} species"))
        gull = conn.execute("SELECT species_id FROM taxon WHERE scientific_name = 'Larus'").fetchone()[0]
        checks.append(("'Gull species' (genus) does not count as a species", gull is None, ""))
        print()

        geojson_bytes = run_queries(conn)
        backup_ms, backup_size = backup_test(conn, folder)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db_size = (folder / "wildlife.db").stat().st_size
        conn.close()

    print(f"{'Query / operation':48} {'median':>9} {'rows':>7}  full-table scans")
    print("-" * 110)
    for label, ms, n, scans in results:
        print(f"{label:48} {ms:7.1f}ms {n:7,}  {'; '.join(scans) if scans else '-'}")
    print("-" * 110)
    print(f"Map GeoJSON payload: {geojson_bytes / 1e6:.1f} MB | Backup: {backup_ms:.0f} ms | "
          f"DB size: {db_size / 1e6:.1f} MB\n")

    failed = 0
    for label, ok, detail in checks:
        failed += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not ok else ""))
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
