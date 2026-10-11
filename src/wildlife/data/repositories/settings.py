"""SQL for the `setting` table: user preferences that differ from the defaults."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def load_all(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        row["key"]: json.loads(row["value"])
        for row in conn.execute("SELECT key, value FROM setting")
    }


def save(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO setting (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )


def reset(conn: sqlite3.Connection, key: str) -> None:
    conn.execute("DELETE FROM setting WHERE key = ?", (key,))
