"""Master-profile service: snapshots, review queues, confirmation and classification."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from ris.domain.enums import FACT_KINDS, Confidentiality, Origin, RecordKind, Verification
from ris.domain.models import PersonalInfo
from ris.errors import ValidationFailed
from ris.storage.repository import Record, RecordRepository


@dataclass
class ProfileSnapshot:
    """Immutable view of all live records, indexed for composition and analysis."""

    records: dict[str, Record] = field(default_factory=dict)
    by_kind: dict[RecordKind, list[Record]] = field(default_factory=lambda: defaultdict(list))
    children: dict[str, list[Record]] = field(default_factory=lambda: defaultdict(list))
    fingerprint: str = ""

    @classmethod
    def from_records(cls, records: Iterable[Record], fingerprint: str = "") -> ProfileSnapshot:
        snap = cls(fingerprint=fingerprint)
        for r in records:
            if r.deleted:
                continue
            snap.records[r.id] = r
            snap.by_kind[r.kind].append(r)
            if r.parent_id:
                snap.children[r.parent_id].append(r)
        for lst in list(snap.by_kind.values()) + list(snap.children.values()):
            lst.sort(key=lambda x: (x.sort_order, x.created_at, x.id))
        return snap

    def of(self, kind: RecordKind | str) -> list[Record]:
        return list(self.by_kind.get(RecordKind(kind), []))

    def kids(self, parent_id: str, kind: RecordKind | str | None = None) -> list[Record]:
        items = self.children.get(parent_id, [])
        if kind is None:
            return list(items)
        k = RecordKind(kind)
        return [r for r in items if r.kind == k]

    def get(self, record_id: str) -> Record | None:
        return self.records.get(record_id)

    @property
    def personal(self) -> Record | None:
        items = self.of(RecordKind.PERSONAL)
        return items[0] if items else None

    @property
    def personal_data(self) -> PersonalInfo:
        p = self.personal
        return p.data if p is not None else PersonalInfo()  # type: ignore[return-value]

    def facts(self) -> list[Record]:
        return [r for r in self.records.values() if r.kind in FACT_KINDS]

    def ancestors(self, record: Record) -> list[Record]:
        out: list[Record] = []
        cur = record
        seen: set[str] = set()
        while cur.parent_id and cur.parent_id not in seen:
            seen.add(cur.parent_id)
            parent = self.records.get(cur.parent_id)
            if parent is None:
                break
            out.append(parent)
            cur = parent
        return out

    def effective_confidentiality(self, record: Record) -> Confidentiality:
        """A child is never less restricted than its ancestors."""
        order = [Confidentiality.PUBLIC, Confidentiality.APPROVED, Confidentiality.REVIEW, Confidentiality.CONFIDENTIAL]
        level = order.index(record.confidentiality)
        for a in self.ancestors(record):
            level = max(level, order.index(a.confidentiality))
        return order[level]

    def effective_verification(self, record: Record) -> Verification:
        """A child counts as unconfirmed if any ancestor is unconfirmed."""
        if record.verification == Verification.UNCONFIRMED:
            return Verification.UNCONFIRMED
        for a in self.ancestors(record):
            if a.kind in FACT_KINDS and a.verification == Verification.UNCONFIRMED:
                return Verification.UNCONFIRMED
        return record.verification


class ProfileService:
    def __init__(self, repo: RecordRepository) -> None:
        self.repo = repo

    def snapshot(self) -> ProfileSnapshot:
        return ProfileSnapshot.from_records(self.repo.list(), fingerprint=self.repo.fingerprint())

    def ensure_personal(self) -> Record:
        rec = self.repo.singleton(RecordKind.PERSONAL)
        if rec is None:
            rec = self.repo.create(
                RecordKind.PERSONAL, PersonalInfo(), verification=Verification.CONFIRMED,
                confidentiality=Confidentiality.APPROVED, origin=Origin.MANUAL,
            )
        return rec

    # ------------------------------------------------------------------ review queues
    def awaiting_confirmation(self) -> list[Record]:
        return [r for r in self.repo.list() if r.kind in FACT_KINDS and r.verification == Verification.UNCONFIRMED]

    def requiring_review(self) -> list[Record]:
        return [r for r in self.repo.list() if r.kind in FACT_KINDS and r.confidentiality == Confidentiality.REVIEW]

    def confirm(self, record_ids: Iterable[str], with_evidence: bool = False) -> int:
        """Mark records as confirmed by the user.

        ``with_evidence`` requires an evidence note on each record.
        """
        ids = list(record_ids)
        if with_evidence:
            missing = []
            for rid in ids:
                rec = self.repo.get(rid)
                if not getattr(rec.data, "evidence", "").strip():
                    missing.append(rec.title)
            if missing:
                raise ValidationFailed(
                    "Add a supporting-evidence note before marking these as confirmed with evidence: "
                    + "; ".join(missing[:5])
                )
            return self.repo.set_verification(ids, Verification.EVIDENCED)
        return self.repo.set_verification(ids, Verification.CONFIRMED)

    def classify(self, record_ids: Iterable[str], level: Confidentiality | str) -> int:
        return self.repo.set_confidentiality(record_ids, level)
