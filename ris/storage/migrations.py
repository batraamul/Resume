"""Explicit, versioned schema migrations.

Migrations are SQL files named ``NNNN_description.sql`` in the top-level
``migrations/`` folder. Each runs in its own transaction and is recorded in
``schema_migrations`` with a checksum so edited migrations are detected.
A database created by a newer application version is refused (no silent
downgrade).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from ris.errors import MigrationError
from ris.resources import migrations_dir
from ris.storage.database import Database
from ris.util import sha256_text, utc_now_iso

log = logging.getLogger(__name__)

_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    checksum: str


def discover(directory: Path | None = None) -> list[Migration]:
    directory = directory or migrations_dir()
    found: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        m = _NAME.match(path.name)
        if not m:
            continue
        sql = path.read_text(encoding="utf-8")
        found.append(Migration(int(m.group(1)), m.group(2), sql, sha256_text(sql)))
    versions = [mg.version for mg in found]
    if len(versions) != len(set(versions)):
        raise MigrationError("Duplicate migration versions found.")
    return found


def latest_version(directory: Path | None = None) -> int:
    migs = discover(directory)
    return migs[-1].version if migs else 0


def _ensure_table(db: Database) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL, checksum TEXT NOT NULL)"
    )


def current_version(db: Database) -> int:
    if not db.table_exists("schema_migrations"):
        return 0
    return int(db.scalar("SELECT COALESCE(MAX(version), 0) FROM schema_migrations") or 0)


def pending(db: Database, directory: Path | None = None) -> list[Migration]:
    cur = current_version(db)
    return [m for m in discover(directory) if m.version > cur]


def verify_applied(db: Database, directory: Path | None = None) -> list[str]:
    """Return warnings for applied migrations whose files changed since they ran."""
    if not db.table_exists("schema_migrations"):
        return []
    files = {m.version: m for m in discover(directory)}
    warnings: list[str] = []
    for row in db.query("SELECT version, name, checksum FROM schema_migrations ORDER BY version"):
        f = files.get(row["version"])
        if f is None:
            warnings.append(f"Applied migration {row['version']:04d}_{row['name']} is missing from the application.")
        elif f.checksum != row["checksum"]:
            warnings.append(f"Migration {row['version']:04d}_{row['name']} was modified after it was applied.")
    return warnings


def migrate(db: Database, directory: Path | None = None) -> list[Migration]:
    """Apply all pending migrations. Returns the migrations applied."""
    _ensure_table(db)
    known = discover(directory)
    latest = known[-1].version if known else 0
    cur = current_version(db)
    if cur > latest:
        raise MigrationError(
            "This profile was created by a newer version of Resume Intelligence Studio "
            f"(schema {cur}, this version supports up to {latest}). Please update the application.",
        )
    applied: list[Migration] = []
    conn = db.conn
    for mig in known:
        if mig.version <= cur:
            continue
        log.info("Applying migration %04d_%s", mig.version, mig.name)
        with db.lock:
            try:
                conn.execute("BEGIN IMMEDIATE")
                # executescript would COMMIT implicitly; run statements one by one instead.
                for statement in _split_sql(mig.sql):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at, checksum) VALUES (?, ?, ?, ?)",
                    (mig.version, mig.name, utc_now_iso(), mig.checksum),
                )
                conn.execute("COMMIT")
            except Exception as exc:
                conn.execute("ROLLBACK")
                raise MigrationError(
                    f"Database upgrade step {mig.version:04d} failed; no changes were made.", detail=str(exc)
                ) from exc
        applied.append(mig)
    return applied


def _split_sql(sql: str) -> list[str]:
    """Split a migration script into statements (handles comments and quoted text)."""
    statements: list[str] = []
    buf: list[str] = []
    in_single = in_double = False
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if not in_single and not in_double and ch == "-" and sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j == -1 else j + 1
            buf.append("\n")
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == ";" and not in_single and not in_double:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements
