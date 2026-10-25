"""Step 2 — saving and loading: one SQLite file, the profile stored as JSON."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from model import Profile


class Store:
    def __init__(self, path: Path) -> None:
        self.conn = sqlite3.connect(path)
        self.conn.execute("CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT)")

    def save(self, profile: Profile) -> None:
        with self.conn:                                  # a transaction: all or nothing
            self.conn.execute("INSERT OR REPLACE INTO profile (id, data) VALUES (1, ?)",
                              (profile.model_dump_json(),))

    def load(self) -> Profile | None:
        row = self.conn.execute("SELECT data FROM profile WHERE id = 1").fetchone()
        return Profile.model_validate_json(row[0]) if row else None
