import sqlite3
import threading
import uuid

import pytest

from wildlife.data import snapshot
from wildlife.data.db import Database
from wildlife.data.migrate import Migration, available_migrations, current_version, migrate
from wildlife.domain.errors import DatabaseError


def test_fresh_database_is_migrated_to_latest(db):
    with db.connection() as conn:
        assert current_version(conn) == available_migrations()[-1].version
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
    assert {"sighting", "taxon", "place", "outing", "photo", "sighting_photo", "setting"} <= tables


def test_connection_settings(db):
    with db.connection() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL


def test_migrate_twice_is_harmless(db):
    with db.connection() as conn:
        before = current_version(conn)
        assert migrate(conn) == before


def test_transaction_commits_on_success(db):
    with db.transaction() as conn:
        conn.execute("INSERT INTO setting (key, value) VALUES ('a', '1')")
    with db.connection() as conn:
        assert conn.execute("SELECT value FROM setting WHERE key='a'").fetchone()[0] == "1"


def test_transaction_rolls_back_everything_on_error(db):
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute("INSERT INTO setting (key, value) VALUES ('ok', '1')")
        conn.execute("INSERT INTO setting (key, value) VALUES ('bad', 'not json')")
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM setting").fetchone()[0] == 0
        assert not conn.in_transaction


def test_each_thread_gets_its_own_connection(db):
    seen = []
    with db.connection() as main_conn:
        seen.append(id(main_conn))

    def worker():
        with db.connection() as conn:
            seen.append(id(conn))
            conn.execute("SELECT 1")

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert len(set(seen)) == 2


def test_failed_migration_changes_nothing(db):
    good = available_migrations()
    broken = Migration(
        len(good) + 1, "9999_broken.sql", "CREATE TABLE half_done (id INTEGER);\nNOT SQL;"
    )
    with db.connection() as conn:
        before = current_version(conn)
        with pytest.raises(DatabaseError):
            migrate(conn, migrations=[*good, broken])
        assert current_version(conn) == before
        assert (
            conn.execute("SELECT COUNT(*) FROM sqlite_schema WHERE name='half_done'").fetchone()[0]
            == 0
        )


def test_backup_runs_before_upgrading_existing_data(db):
    good = available_migrations()
    extra = Migration(
        len(good) + 1, "0099_extra.sql", "CREATE TABLE extra (id INTEGER PRIMARY KEY) STRICT;"
    )
    calls = []
    with db.connection() as conn:
        migrate(conn, backup=lambda a, b: calls.append((a, b)), migrations=[*good, extra])
    assert calls == [(len(good), len(good) + 1)]


def test_refuses_database_from_newer_app(db):
    with db.connection() as conn:
        conn.execute("PRAGMA user_version = 999")
        with pytest.raises(DatabaseError) as err:
            migrate(conn)
    assert "newer version" in err.value.user_message


def test_snapshot_is_consistent_and_verified(db, tmp_path):
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO taxon (id, scientific_name, rank, category_id, is_custom) VALUES (1, 'Testus', 'species', 9, 1)"
        )
        conn.execute(
            "INSERT INTO sighting (uuid, taxon_id, observed_date) VALUES (?, 1, '2026-10-11')",
            (str(uuid.uuid4()),),
        )
    with db.connection() as conn:
        copy = snapshot.take_snapshot(conn, tmp_path / "copy.db")
    result = snapshot.verify(copy)
    assert result.ok and result.integrity == "ok"
    assert result.counts["sighting"] == 1 and result.counts["taxon"] == 1


def test_snapshot_refuses_to_overwrite(db, tmp_path):
    target = tmp_path / "exists.db"
    target.write_bytes(b"x")
    with db.connection() as conn, pytest.raises(FileExistsError):
        snapshot.take_snapshot(conn, target)


def test_category_rules_match_anywhere_in_lineage(db):
    """UKSI sometimes files an order (Odonata) in the class field."""
    resolve = """
        UPDATE taxon SET category_id = COALESCE(
            (SELECT category_id FROM category_rule WHERE taxon_name = taxon.tax_family),
            (SELECT category_id FROM category_rule WHERE taxon_name = taxon.tax_order),
            (SELECT category_id FROM category_rule WHERE taxon_name = taxon.tax_class),
            (SELECT category_id FROM category_rule WHERE taxon_name = taxon.tax_phylum),
            (SELECT category_id FROM category_rule WHERE taxon_name = taxon.tax_kingdom),
            (SELECT id FROM category WHERE is_fallback = 1))
        WHERE category_is_manual = 0"""
    rows = [  # (id, class, order, expected category)
        (1, "Insecta", "Odonata", 5),
        (2, "Odonata", None, 5),
        (3, "Insecta", "Coleoptera", 7),
        (4, "Actinopterygii", "Salmoniformes", 3),
        (5, "Aves", "Passeriformes", 1),
        (6, "Gastropoda", "Stylommatophora", 8),
    ]
    with db.transaction() as conn:
        for tid, cls, order, _ in rows:
            conn.execute(
                "INSERT INTO taxon (id, uksi_key, scientific_name, rank, tax_kingdom, tax_phylum, tax_class, "
                "tax_order, category_id) VALUES (?, ?, 'x', 'species', 'Animalia', 'Phylum', ?, ?, 9)",
                (tid, f"T{tid}", cls, order),
            )
        conn.execute(resolve)
    with db.connection() as conn:
        got = dict(conn.execute("SELECT id, category_id FROM taxon").fetchall())
    assert got == {tid: cat for tid, _, _, cat in rows}


def test_database_file_can_be_reopened(paths):
    first = Database(paths.database)
    with first.connection() as conn:
        migrate(conn)
    first.close()
    second = Database(paths.database)
    with second.connection() as conn:
        assert current_version(conn) == available_migrations()[-1].version
    second.close()
