"""SQLite connection management.

One connection per workspace guarded by a re-entrant lock, so background
workers can safely read and write. Rollback-journal mode keeps the database a
single file (simpler, safer copies and restores); ``synchronous=FULL`` favours
durability over speed, which is the right trade-off for a personal record.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ris.errors import StorageError
from ris.paths import restrict_file

log = logging.getLogger(__name__)


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path) if str(path) != ":memory:" else Path(":memory:")
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._tx_depth = 0

    # ------------------------------------------------------------------ lifecycle
    def connect(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                if str(self.path) != ":memory:":
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    conn = sqlite3.connect(
                        str(self.path), isolation_level=None, check_same_thread=False, timeout=10.0
                    )
                except sqlite3.Error as exc:  # pragma: no cover - environment specific
                    raise StorageError("The profile database could not be opened.", detail=str(exc)) from exc
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = DELETE")
                conn.execute("PRAGMA synchronous = FULL")
                conn.execute("PRAGMA busy_timeout = 5000")
                conn.execute("PRAGMA trusted_schema = OFF")
                self._conn = conn
                if str(self.path) != ":memory:":
                    restrict_file(self.path)
            return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                finally:
                    self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        return self.connect()

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    # ------------------------------------------------------------------ queries
    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, params)

    def executemany(self, sql: str, seq: list[tuple]) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.executemany(sql, seq)

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(sql, params).fetchone()

    def scalar(self, sql: str, params: tuple | dict = ()) -> Any:
        row = self.query_one(sql, params)
        return None if row is None else row[0]

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Nested-safe transaction. Outermost level issues BEGIN IMMEDIATE/COMMIT."""
        with self._lock:
            conn = self.conn
            outer = self._tx_depth == 0
            if outer:
                conn.execute("BEGIN IMMEDIATE")
            else:
                conn.execute(f"SAVEPOINT sp_{self._tx_depth}")
            self._tx_depth += 1
            try:
                yield conn
            except BaseException:
                self._tx_depth -= 1
                if outer:
                    conn.execute("ROLLBACK")
                else:
                    conn.execute(f"ROLLBACK TO sp_{self._tx_depth}")
                    conn.execute(f"RELEASE sp_{self._tx_depth}")
                raise
            else:
                self._tx_depth -= 1
                if outer:
                    conn.execute("COMMIT")
                else:
                    conn.execute(f"RELEASE sp_{self._tx_depth}")

    def table_exists(self, name: str) -> bool:
        return bool(self.scalar("SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?", (name,)))

    def backup_to(self, target_path: Path) -> None:
        """Consistent online copy using SQLite's backup API."""
        with self._lock:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            dest = sqlite3.connect(str(target_path))
            try:
                self.conn.backup(dest)
            finally:
                dest.close()
            restrict_file(target_path)
