"""Database integrity checks (STO-05) and safe repairs."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from ris.domain import registry
from ris.domain.enums import RecordKind
from ris.storage import migrations
from ris.storage.database import Database
from ris.storage.repository import compute_checksum
from ris.util import canonical_json, sha256_text


@dataclass
class IntegrityReport:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    records_checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.problems

    def summary(self) -> str:
        if self.ok and not self.warnings:
            return f"No problems found ({self.records_checked} records checked)."
        if self.ok:
            return f"No problems found; {len(self.warnings)} note(s) ({self.records_checked} records checked)."
        return f"{len(self.problems)} problem(s) found ({self.records_checked} records checked)."


def check_database(db: Database, deep: bool = True) -> IntegrityReport:
    rep = IntegrityReport()
    try:
        res = db.scalar("PRAGMA integrity_check")
    except sqlite3.DatabaseError as exc:
        rep.problems.append(f"SQLite could not read the database: {exc}")
        return rep
    if res != "ok":
        rep.problems.append(f"SQLite integrity check failed: {res}")
    fk = db.query("PRAGMA foreign_key_check")
    if fk:
        rep.problems.append(f"{len(fk)} record(s) reference missing parent records.")
    try:
        cur = migrations.current_version(db)
        latest = migrations.latest_version()
        if cur > latest:
            rep.problems.append(f"Database schema {cur} is newer than this application supports ({latest}).")
        elif cur < latest:
            rep.warnings.append(f"Database schema {cur} will be upgraded to {latest} when opened.")
        rep.warnings.extend(migrations.verify_applied(db))
    except sqlite3.DatabaseError as exc:
        rep.problems.append(f"Schema information unreadable: {exc}")
        return rep
    if not deep or not db.table_exists("records"):
        return rep
    rows = db.query("SELECT * FROM records")
    ids = {r["id"]: r for r in rows}
    personal_live = 0
    for r in rows:
        rep.records_checked += 1
        try:
            kind = RecordKind(r["kind"])
        except ValueError:
            rep.problems.append(f"Record {r['id'][:8]} has an unknown kind '{r['kind']}'.")
            continue
        try:
            payload = json.loads(r["data"])
        except ValueError:
            rep.problems.append(f"Record {r['id'][:8]} ({kind.value}) contains invalid JSON.")
            continue
        model = registry.model_for(kind)
        try:
            norm = model.model_validate(payload).model_dump(mode="json")
        except ValidationError as exc:
            rep.problems.append(f"Record {r['id'][:8]} ({kind.value}) fails validation: {exc.errors()[0].get('msg')}")
            continue
        expected = compute_checksum(kind.value, r["parent_id"], r["sort_order"], r["verification"],
                                    r["confidentiality"], r["origin"], norm, bool(r["deleted"]))
        if expected != r["checksum"]:
            rep.problems.append(f"Record {r['id'][:8]} ({kind.value}) checksum does not match its content.")
        allowed = registry.info(kind).parents
        if r["parent_id"]:
            parent = ids.get(r["parent_id"])
            if parent is None:
                rep.problems.append(f"Record {r['id'][:8]} ({kind.value}) has a missing parent.")
            elif allowed and RecordKind(parent["kind"]) not in allowed:
                rep.problems.append(f"Record {r['id'][:8]} ({kind.value}) has a parent of the wrong kind.")
            elif parent["deleted"] and not r["deleted"]:
                rep.warnings.append(f"Record {r['id'][:8]} ({kind.value}) belongs to a deleted parent.")
        elif allowed:
            rep.problems.append(f"Record {r['id'][:8]} ({kind.value}) is missing its parent.")
        if kind == RecordKind.PERSONAL and not r["deleted"]:
            personal_live += 1
    if personal_live > 1:
        rep.problems.append("More than one personal-details record exists.")
    live = sum(1 for r in rows if not r["deleted"])
    if db.table_exists("records_fts"):
        fts = int(db.scalar("SELECT COUNT(*) FROM records_fts") or 0)
        if fts != live:
            rep.warnings.append(f"Search index has {fts} entries for {live} records; rebuild the index.")
    if db.table_exists("variant_versions"):
        for v in db.query("SELECT id, document, settings, checksum FROM variant_versions"):
            try:
                actual = sha256_text(canonical_json({"doc": json.loads(v["document"]),
                                                     "settings": json.loads(v["settings"])}))
            except ValueError:
                actual = ""
            if actual != v["checksum"]:
                rep.problems.append(f"Saved resume version {v['id'][:8]} fails its integrity check.")
    return rep


def check_file(path: Path) -> IntegrityReport:
    db = Database(path)
    try:
        return check_database(db)
    finally:
        db.close()


def rebuild_search_index(repo) -> int:
    """Recreate the full-text index from live records. Returns the number indexed."""
    with repo.db.transaction():
        repo.db.execute("DELETE FROM records_fts")
        recs = repo.list()
        for r in recs:
            repo._index(r.id, r.kind.value, r.data, False)
    return len(recs)
