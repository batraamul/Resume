"""Record repository: validated, revisioned, audited storage for every entity.

Every write:
* validates the payload with the kind's Pydantic model,
* enforces parent/singleton rules,
* increments the revision and recomputes a content checksum,
* updates the full-text index,
* appends a value-free entry to the audit log,
all inside one transaction.

Deletes are soft (tombstones) so synchronisation can propagate them and the
user can undo; ``purge`` removes rows permanently.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from ris.domain import registry
from ris.domain.enums import FACT_KINDS, Confidentiality, Origin, RecordKind, Verification
from ris.domain.models import RecordData
from ris.errors import ConcurrencyConflict, NotFound, ValidationFailed
from ris.storage.database import Database
from ris.util import canonical_json, new_id, sha256_text, utc_now_iso

log = logging.getLogger(__name__)


def compute_checksum(
    kind: str,
    parent_id: str | None,
    sort_order: float,
    verification: str,
    confidentiality: str,
    origin: str,
    payload: dict[str, Any],
    deleted: bool,
) -> str:
    return sha256_text(
        canonical_json(
            {
                "kind": kind,
                "parent_id": parent_id,
                "sort_order": float(sort_order),
                "verification": verification,
                "confidentiality": confidentiality,
                "origin": origin,
                "data": payload,
                "deleted": bool(deleted),
            }
        )
    )


def format_validation_error(model: type[BaseModel], exc: ValidationError) -> list[str]:
    msgs: list[str] = []
    for err in exc.errors():
        loc = err.get("loc", ())
        name = str(loc[0]) if loc else ""
        fi = model.model_fields.get(name)
        title = (fi.title if fi and fi.title else name.replace("_", " ").capitalize()) if name else "Record"
        msg = str(err.get("msg", "invalid value"))
        msg = msg.removeprefix("Value error, ")
        msgs.append(f"{title}: {msg}")
    return msgs


@dataclass
class Record:
    id: str
    kind: RecordKind
    parent_id: str | None
    sort_order: float
    verification: Verification
    confidentiality: Confidentiality
    origin: Origin
    data: RecordData
    created_at: str
    updated_at: str
    revision: int
    checksum: str
    deleted: bool = False
    deleted_at: str | None = None
    modified_by: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return self.data.display_title()

    @property
    def subtitle(self) -> str:
        return self.data.display_subtitle()

    @property
    def is_confirmed(self) -> bool:
        return self.verification in (Verification.CONFIRMED, Verification.EVIDENCED)

    @property
    def is_confidential(self) -> bool:
        return self.confidentiality == Confidentiality.CONFIDENTIAL

    def payload(self) -> dict[str, Any]:
        return self.data.model_dump(mode="json")

    def envelope(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "parent_id": self.parent_id,
            "sort_order": self.sort_order,
            "verification": self.verification.value,
            "confidentiality": self.confidentiality.value,
            "origin": self.origin.value,
            "data": self.payload(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "revision": self.revision,
            "checksum": self.checksum,
            "deleted": self.deleted,
            "deleted_at": self.deleted_at,
            "modified_by": self.modified_by,
        }


_TOKEN = re.compile(r"[\w][\w.+#-]*", re.UNICODE)


class RecordRepository:
    def __init__(self, db: Database, device_id: str = "") -> None:
        self.db = db
        self.device_id = device_id
        self._listeners: list = []

    # ------------------------------------------------------------------ change notification
    def add_listener(self, callback) -> None:
        """Register ``callback(action, record_id, kind)``; called after commits."""
        self._listeners.append(callback)

    def remove_listener(self, callback) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self, action: str, record_id: str, kind: str) -> None:
        for cb in list(self._listeners):
            try:
                cb(action, record_id, kind)
            except Exception:  # pragma: no cover - listener bugs must not break storage
                log.exception("Record listener failed")

    # ------------------------------------------------------------------ helpers
    def _row_to_record(self, row) -> Record:
        kind = RecordKind(row["kind"])
        raw = json.loads(row["data"])
        model = registry.model_for(kind)
        try:
            data = model.model_validate(raw)
        except ValidationError:
            # Stored data failed validation (e.g. written by an older buggy build). Keep it
            # readable without dropping fields; integrity checks report it.
            data = model.model_construct(**raw)
        return Record(
            id=row["id"],
            kind=kind,
            parent_id=row["parent_id"],
            sort_order=float(row["sort_order"]),
            verification=Verification(row["verification"]),
            confidentiality=Confidentiality(row["confidentiality"]),
            origin=Origin(row["origin"]),
            data=data,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            revision=int(row["revision"]),
            checksum=row["checksum"],
            deleted=bool(row["deleted"]),
            deleted_at=row["deleted_at"],
            modified_by=row["modified_by"],
        )

    def _validate(self, kind: RecordKind, data: dict[str, Any] | BaseModel | None) -> RecordData:
        model = registry.model_for(kind)
        try:
            if data is None:
                return model()
            if isinstance(data, model):
                # Re-validate to apply normalisers to mutated instances.
                return model.model_validate(data.model_dump())
            if isinstance(data, BaseModel):
                data = data.model_dump()
            return model.model_validate(data)
        except ValidationError as exc:
            msgs = format_validation_error(model, exc)
            raise ValidationFailed("Please correct: " + "; ".join(msgs), errors=msgs) from exc

    def _check_parent(self, kind: RecordKind, parent_id: str | None) -> None:
        allowed = registry.info(kind).parents
        if not allowed:
            if parent_id:
                raise ValidationFailed(f"A {kind.value} record cannot have a parent.")
            return
        if not parent_id:
            raise ValidationFailed(f"A {kind.value} record must belong to a parent record.")
        row = self.db.query_one("SELECT kind, deleted FROM records WHERE id = ?", (parent_id,))
        if row is None or row["deleted"]:
            raise ValidationFailed("The parent record does not exist.")
        if RecordKind(row["kind"]) not in allowed:
            raise ValidationFailed(f"A {kind.value} record cannot belong to a {row['kind']} record.")

    def _check_singleton(self, kind: RecordKind, exclude_id: str | None = None) -> None:
        if not registry.info(kind).singleton:
            return
        row = self.db.query_one(
            "SELECT id FROM records WHERE kind = ? AND deleted = 0 AND id <> ?", (kind.value, exclude_id or "")
        )
        if row is not None:
            raise ValidationFailed(f"Only one {kind.value} record is allowed.")

    def _index(self, record_id: str, kind: str, data: RecordData, deleted: bool) -> None:
        self.db.execute("DELETE FROM records_fts WHERE record_id = ?", (record_id,))
        if not deleted:
            content = f"{data.display_title()}\n{data.search_text()}"
            self.db.execute(
                "INSERT INTO records_fts (record_id, kind, content) VALUES (?, ?, ?)", (record_id, kind, content)
            )

    def _audit(self, action: str, record_id: str | None, kind: str | None, detail: str = "") -> None:
        self.db.execute(
            "INSERT INTO audit_log (at, action, record_id, kind, detail) VALUES (?, ?, ?, ?, ?)",
            (utc_now_iso(), action, record_id, kind, detail[:500]),
        )

    def _next_sort(self, kind: RecordKind, parent_id: str | None) -> float:
        val = self.db.scalar(
            "SELECT MAX(sort_order) FROM records WHERE kind = ? AND COALESCE(parent_id,'') = ?",
            (kind.value, parent_id or ""),
        )
        return float(val or 0) + 1.0

    # ------------------------------------------------------------------ create / read
    def create(
        self,
        kind: RecordKind | str,
        data: dict[str, Any] | BaseModel | None = None,
        *,
        parent_id: str | None = None,
        verification: Verification | str | None = None,
        confidentiality: Confidentiality | str | None = None,
        origin: Origin | str = Origin.MANUAL,
        sort_order: float | None = None,
        record_id: str | None = None,
    ) -> Record:
        kind = RecordKind(kind)
        origin = Origin(origin)
        model = self._validate(kind, data)
        if verification is None:
            verification = Verification.CONFIRMED if origin == Origin.MANUAL else Verification.UNCONFIRMED
            if not registry.info(kind).is_fact:
                verification = Verification.CONFIRMED
        verification = Verification(verification)
        confidentiality = Confidentiality(
            confidentiality if confidentiality is not None else registry.default_confidentiality(kind, origin)
        )
        rid = record_id or new_id()
        now = utc_now_iso()
        payload = model.model_dump(mode="json")
        with self.db.transaction():
            self._check_parent(kind, parent_id)
            self._check_singleton(kind)
            order = float(sort_order) if sort_order is not None else self._next_sort(kind, parent_id)
            checksum = compute_checksum(
                kind.value, parent_id, order, verification.value, confidentiality.value, origin.value, payload, False
            )
            self.db.execute(
                "INSERT INTO records (id, kind, parent_id, sort_order, verification, confidentiality, origin, data,"
                " created_at, updated_at, revision, checksum, deleted, deleted_at, modified_by)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 0, NULL, ?)",
                (
                    rid, kind.value, parent_id, order, verification.value, confidentiality.value, origin.value,
                    json.dumps(payload, ensure_ascii=False), now, now, checksum, self.device_id,
                ),
            )
            self._index(rid, kind.value, model, False)
            self._audit("create", rid, kind.value, f"origin={origin.value}")
        self._notify("create", rid, kind.value)
        return self.get(rid)

    def find(self, record_id: str, include_deleted: bool = False) -> Record | None:
        row = self.db.query_one("SELECT * FROM records WHERE id = ?", (record_id,))
        if row is None or (row["deleted"] and not include_deleted):
            return None
        return self._row_to_record(row)

    def get(self, record_id: str, include_deleted: bool = False) -> Record:
        rec = self.find(record_id, include_deleted=include_deleted)
        if rec is None:
            raise NotFound("The record no longer exists.")
        return rec

    def list(
        self,
        kind: RecordKind | str | None = None,
        *,
        parent_id: str | None | object = ...,
        include_deleted: bool = False,
        kinds: Iterable[RecordKind | str] | None = None,
    ) -> list[Record]:
        sql = "SELECT * FROM records WHERE 1=1"
        params: list[Any] = []
        if kind is not None:
            sql += " AND kind = ?"
            params.append(RecordKind(kind).value)
        if kinds is not None:
            ks = [RecordKind(k).value for k in kinds]
            if not ks:
                return []
            sql += f" AND kind IN ({','.join('?' * len(ks))})"
            params.extend(ks)
        if parent_id is not ...:
            if parent_id is None:
                sql += " AND parent_id IS NULL"
            else:
                sql += " AND parent_id = ?"
                params.append(parent_id)
        if not include_deleted:
            sql += " AND deleted = 0"
        sql += " ORDER BY sort_order, created_at, id"
        return [self._row_to_record(r) for r in self.db.query(sql, tuple(params))]

    def children(self, parent_id: str, kind: RecordKind | str | None = None) -> list[Record]:
        return self.list(kind, parent_id=parent_id)

    def singleton(self, kind: RecordKind | str) -> Record | None:
        recs = self.list(kind)
        return recs[0] if recs else None

    def count(self, kind: RecordKind | str | None = None, **filters: str) -> int:
        sql = "SELECT COUNT(*) FROM records WHERE deleted = 0"
        params: list[Any] = []
        if kind is not None:
            sql += " AND kind = ?"
            params.append(RecordKind(kind).value)
        for col in ("verification", "confidentiality", "origin"):
            if col in filters:
                sql += f" AND {col} = ?"
                params.append(str(filters[col]))
        return int(self.db.scalar(sql, tuple(params)) or 0)

    # ------------------------------------------------------------------ update
    def update(
        self,
        record_id: str,
        data: dict[str, Any] | BaseModel | None = None,
        *,
        verification: Verification | str | None = None,
        confidentiality: Confidentiality | str | None = None,
        parent_id: str | None | object = ...,
        sort_order: float | None = None,
        expected_revision: int | None = None,
        audit_action: str = "update",
    ) -> Record:
        with self.db.transaction():
            current = self.get(record_id)
            if expected_revision is not None and current.revision != expected_revision:
                raise ConcurrencyConflict(
                    "This record was changed elsewhere since you opened it. Reload it before saving."
                )
            model = self._validate(current.kind, data) if data is not None else current.data
            new_parent = current.parent_id if parent_id is ... else parent_id  # type: ignore[assignment]
            if new_parent != current.parent_id:
                self._check_parent(current.kind, new_parent)  # type: ignore[arg-type]
            ver = Verification(verification) if verification is not None else current.verification
            conf = Confidentiality(confidentiality) if confidentiality is not None else current.confidentiality
            order = float(sort_order) if sort_order is not None else current.sort_order
            payload = model.model_dump(mode="json")
            checksum = compute_checksum(
                current.kind.value, new_parent, order, ver.value, conf.value, current.origin.value, payload, False  # type: ignore[arg-type]
            )
            if checksum == current.checksum:
                return current  # nothing changed — keep revision stable
            changed = self._changed_fields(current, model, ver, conf, new_parent, order)  # type: ignore[arg-type]
            now = utc_now_iso()
            self.db.execute(
                "UPDATE records SET parent_id = ?, sort_order = ?, verification = ?, confidentiality = ?, data = ?,"
                " updated_at = ?, revision = revision + 1, checksum = ?, modified_by = ? WHERE id = ?",
                (
                    new_parent, order, ver.value, conf.value, json.dumps(payload, ensure_ascii=False),
                    now, checksum, self.device_id, record_id,
                ),
            )
            self._index(record_id, current.kind.value, model, False)
            self._audit(audit_action, record_id, current.kind.value, "fields=" + ",".join(changed))
        self._notify(audit_action, record_id, current.kind.value)
        return self.get(record_id)

    @staticmethod
    def _changed_fields(
        current: Record, model: RecordData, ver: Verification, conf: Confidentiality, parent: str | None, order: float
    ) -> list[str]:
        changed: list[str] = []
        old = current.payload()
        new = model.model_dump(mode="json")
        for key in sorted(set(old) | set(new)):
            if old.get(key) != new.get(key):
                changed.append(key)
        if ver != current.verification:
            changed.append("@verification")
        if conf != current.confidentiality:
            changed.append("@confidentiality")
        if parent != current.parent_id:
            changed.append("@parent")
        if order != current.sort_order:
            changed.append("@order")
        return changed

    def patch(self, record_id: str, **fields: Any) -> Record:
        """Update selected payload fields, keeping the rest."""
        current = self.get(record_id)
        payload = current.payload()
        payload.update(fields)
        return self.update(record_id, payload)

    def set_verification(self, record_ids: Iterable[str], status: Verification | str) -> int:
        n = 0
        with self.db.transaction():
            for rid in record_ids:
                rec = self.find(rid)
                if rec and rec.verification != Verification(status):
                    self.update(rid, verification=status, audit_action="verify")
                    n += 1
        return n

    def set_confidentiality(self, record_ids: Iterable[str], level: Confidentiality | str) -> int:
        n = 0
        with self.db.transaction():
            for rid in record_ids:
                rec = self.find(rid)
                if rec and rec.confidentiality != Confidentiality(level):
                    self.update(rid, confidentiality=level, audit_action="classify")
                    n += 1
        return n

    def reorder(self, ordered_ids: list[str]) -> None:
        with self.db.transaction():
            for i, rid in enumerate(ordered_ids):
                rec = self.find(rid)
                if rec and rec.sort_order != float(i + 1):
                    self.update(rid, sort_order=float(i + 1), audit_action="reorder")

    # ------------------------------------------------------------------ delete
    def _descendants(self, record_id: str) -> list[str]:
        out: list[str] = []
        stack = [record_id]
        while stack:
            pid = stack.pop()
            rows = self.db.query("SELECT id FROM records WHERE parent_id = ?", (pid,))
            for r in rows:
                out.append(r["id"])
                stack.append(r["id"])
        return out

    def delete(self, record_id: str) -> list[str]:
        """Soft-delete a record and its descendants. Returns affected ids."""
        affected: list[str] = []
        with self.db.transaction():
            rec = self.get(record_id)
            now = utc_now_iso()
            for rid in [record_id, *self._descendants(record_id)]:
                row = self.db.query_one("SELECT * FROM records WHERE id = ?", (rid,))
                if row is None or row["deleted"]:
                    continue
                payload = json.loads(row["data"])
                checksum = compute_checksum(
                    row["kind"], row["parent_id"], row["sort_order"], row["verification"],
                    row["confidentiality"], row["origin"], payload, True,
                )
                self.db.execute(
                    "UPDATE records SET deleted = 1, deleted_at = ?, updated_at = ?, revision = revision + 1,"
                    " checksum = ?, modified_by = ? WHERE id = ?",
                    (now, now, checksum, self.device_id, rid),
                )
                self.db.execute("DELETE FROM records_fts WHERE record_id = ?", (rid,))
                self._audit("delete", rid, row["kind"])
                affected.append(rid)
        self._notify("delete", record_id, rec.kind.value)
        return affected

    def undelete(self, record_id: str) -> Record:
        with self.db.transaction():
            row = self.db.query_one("SELECT * FROM records WHERE id = ?", (record_id,))
            if row is None:
                raise NotFound("The record no longer exists.")
            if not row["deleted"]:
                return self.get(record_id)
            if row["parent_id"]:
                parent = self.db.query_one("SELECT deleted FROM records WHERE id = ?", (row["parent_id"],))
                if parent is None or parent["deleted"]:
                    raise ValidationFailed("Restore the parent record first.")
            kind = RecordKind(row["kind"])
            self._check_singleton(kind, exclude_id=record_id)
            payload = json.loads(row["data"])
            checksum = compute_checksum(
                row["kind"], row["parent_id"], row["sort_order"], row["verification"],
                row["confidentiality"], row["origin"], payload, False,
            )
            now = utc_now_iso()
            self.db.execute(
                "UPDATE records SET deleted = 0, deleted_at = NULL, updated_at = ?, revision = revision + 1,"
                " checksum = ?, modified_by = ? WHERE id = ?",
                (now, checksum, self.device_id, record_id),
            )
            rec = self.get(record_id)
            self._index(record_id, row["kind"], rec.data, False)
            self._audit("undelete", record_id, row["kind"])
        self._notify("undelete", record_id, row["kind"])
        return rec

    def purge(self, record_id: str) -> None:
        """Permanently remove a record (and descendants via ON DELETE CASCADE)."""
        with self.db.transaction():
            ids = [record_id, *self._descendants(record_id)]
            kind = self.db.scalar("SELECT kind FROM records WHERE id = ?", (record_id,))
            for rid in ids:
                self.db.execute("DELETE FROM records_fts WHERE record_id = ?", (rid,))
            self.db.execute("DELETE FROM records WHERE id = ?", (record_id,))
            self._audit("purge", record_id, kind)
        self._notify("purge", record_id, kind or "")

    def deleted_records(self) -> list[Record]:
        rows = self.db.query("SELECT * FROM records WHERE deleted = 1 ORDER BY deleted_at DESC")
        return [self._row_to_record(r) for r in rows]

    # ------------------------------------------------------------------ search
    @staticmethod
    def build_fts_query(text: str) -> str:
        tokens = [t.replace('"', "") for t in _TOKEN.findall(text or "")]
        tokens = [t for t in tokens if t]
        if not tokens:
            return ""
        return " ".join(f'"{t}"*' for t in tokens[:12])

    def search(
        self, text: str, kinds: Iterable[RecordKind | str] | None = None, limit: int = 50
    ) -> list[tuple[Record, str]]:
        q = self.build_fts_query(text)
        if not q:
            return []
        sql = (
            "SELECT record_id, snippet(records_fts, 2, '[', ']', '…', 10) AS snip"
            " FROM records_fts WHERE records_fts MATCH ?"
        )
        params: list[Any] = [q]
        if kinds is not None:
            ks = [RecordKind(k).value for k in kinds]
            sql += f" AND kind IN ({','.join('?' * len(ks))})"
            params.extend(ks)
        sql += " ORDER BY rank LIMIT ?"
        params.append(int(limit))
        out: list[tuple[Record, str]] = []
        for row in self.db.query(sql, tuple(params)):
            rec = self.find(row["record_id"])
            if rec is not None:
                out.append((rec, row["snip"] or ""))
        return out

    # ------------------------------------------------------------------ revisions, fingerprints
    def revisions(self, ids: Iterable[str]) -> dict[str, int]:
        ids = list(ids)
        out: dict[str, int] = {}
        for chunk_start in range(0, len(ids), 500):
            chunk = ids[chunk_start : chunk_start + 500]
            rows = self.db.query(
                f"SELECT id, revision, deleted FROM records WHERE id IN ({','.join('?' * len(chunk))})", tuple(chunk)
            )
            for r in rows:
                out[r["id"]] = -1 if r["deleted"] else int(r["revision"])
        return out

    def fingerprint(self, kinds: Iterable[RecordKind] = FACT_KINDS) -> str:
        ks = [k.value for k in kinds]
        rows = self.db.query(
            f"SELECT id, revision FROM records WHERE deleted = 0 AND kind IN ({','.join('?' * len(ks))}) ORDER BY id",
            tuple(ks),
        )
        return sha256_text(canonical_json([[r["id"], r["revision"]] for r in rows]))

    def stats(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {"kind": {}, "verification": {}, "confidentiality": {}}
        for col in out:
            for row in self.db.query(f"SELECT {col} AS k, COUNT(*) AS n FROM records WHERE deleted = 0 GROUP BY {col}"):
                out[col][row["k"]] = int(row["n"])
        return out

    # ------------------------------------------------------------------ raw envelopes (backup / sync)
    def all_envelopes(self, include_deleted: bool = True) -> list[dict[str, Any]]:
        sql = "SELECT * FROM records" + ("" if include_deleted else " WHERE deleted = 0") + " ORDER BY created_at, id"
        return [self._row_to_record(r).envelope() for r in self.db.query(sql)]

    def write_envelope(self, env: dict[str, Any], *, origin_override: str | None = None, action: str = "sync") -> None:
        """Write a complete envelope as-is (used by sync and restore-merge).

        The payload is validated; revision, timestamps and checksum are kept so
        that both devices converge on identical state.
        """
        kind = RecordKind(env["kind"])
        model = self._validate(kind, env.get("data") or {})
        payload = model.model_dump(mode="json")
        origin = origin_override or env.get("origin", Origin.SYNCED.value)
        deleted = bool(env.get("deleted"))
        checksum = compute_checksum(
            kind.value, env.get("parent_id"), float(env.get("sort_order", 0)), env["verification"],
            env["confidentiality"], origin, payload, deleted,
        )
        with self.db.transaction():
            exists = self.db.query_one("SELECT id FROM records WHERE id = ?", (env["id"],))
            params = (
                kind.value, env.get("parent_id"), float(env.get("sort_order", 0)), env["verification"],
                env["confidentiality"], origin, json.dumps(payload, ensure_ascii=False), env["created_at"],
                env["updated_at"], int(env["revision"]), checksum, 1 if deleted else 0, env.get("deleted_at"),
                env.get("modified_by", ""),
            )
            if exists:
                self.db.execute(
                    "UPDATE records SET kind = ?, parent_id = ?, sort_order = ?, verification = ?, confidentiality = ?,"
                    " origin = ?, data = ?, created_at = ?, updated_at = ?, revision = ?, checksum = ?, deleted = ?,"
                    " deleted_at = ?, modified_by = ? WHERE id = ?",
                    (*params, env["id"]),
                )
            else:
                self.db.execute(
                    "INSERT INTO records (kind, parent_id, sort_order, verification, confidentiality, origin, data,"
                    " created_at, updated_at, revision, checksum, deleted, deleted_at, modified_by, id)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (*params, env["id"]),
                )
            self._index(env["id"], kind.value, model, deleted)
            self._audit(action, env["id"], kind.value)
        self._notify(action, env["id"], kind.value)

    def audit_entries(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (int(limit),))
        return [dict(r) for r in rows]
