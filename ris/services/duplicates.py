"""Duplicate detection for manual entry and imports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from ris.domain.enums import RecordKind
from ris.storage.repository import Record

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def norm(text: str) -> str:
    t = _PUNCT.sub(" ", (text or "").casefold())
    return " ".join(t.split())


def similarity(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _key_fields(kind: RecordKind, data: dict[str, Any]) -> list[str]:
    g = data.get
    if kind == RecordKind.POSITION:
        return [g("designation", ""), g("organisation", ""), (g("start") or "")[:4]]
    if kind == RecordKind.EDUCATION:
        return [g("degree", ""), g("discipline", ""), g("institution", "") or g("issuer", "")]
    if kind == RecordKind.PUBLICATION:
        return [g("title", "")]
    if kind == RecordKind.PROJECT:
        return [g("title", "")]
    if kind == RecordKind.SKILL:
        return [g("name", "")]
    if kind == RecordKind.ACTIVITY:
        return [g("title", ""), g("organisation", "")]
    if kind == RecordKind.BULLET:
        return [g("text", "")]
    if kind == RecordKind.SUMMARY:
        return [g("text", "")]
    if kind == RecordKind.ASSIGNMENT:
        return [g("title", ""), g("unit", "")]
    if kind == RecordKind.VACANCY:
        return [g("title", ""), g("employer", ""), g("reference", "")]
    return [str(g("title", "") or g("name", ""))]


@dataclass(frozen=True)
class DuplicateMatch:
    record: Record
    score: float
    reason: str


def match_candidate(kind: RecordKind | str, data: dict[str, Any], existing: list[Record],
                    threshold: float = 0.88) -> DuplicateMatch | None:
    """Best existing record that looks like a duplicate of ``data`` (or None)."""
    kind = RecordKind(kind)
    best: DuplicateMatch | None = None
    doi = (data.get("doi") or "").lower() if kind == RecordKind.PUBLICATION else ""
    cand_key = " ".join(_key_fields(kind, data))
    if not norm(cand_key) and not doi:
        return None
    names = {norm(data.get("name", ""))} | {norm(a) for a in data.get("aliases", []) or []} if kind == RecordKind.SKILL else set()
    for rec in existing:
        if rec.kind != kind:
            continue
        payload = rec.payload()
        if doi and (payload.get("doi") or "").lower() == doi:
            return DuplicateMatch(rec, 1.0, "same DOI")
        if kind == RecordKind.SKILL:
            rec_names = {norm(payload.get("name", ""))} | {norm(a) for a in payload.get("aliases", []) or []}
            if names & rec_names - {""}:
                return DuplicateMatch(rec, 1.0, "same skill name or synonym")
        score = similarity(cand_key, " ".join(_key_fields(kind, payload)))
        if score >= threshold and (best is None or score > best.score):
            best = DuplicateMatch(rec, score, "very similar wording" if score < 1 else "identical")
    return best


def find_duplicate_groups(records: list[Record], threshold: float = 0.9) -> list[list[Record]]:
    """Groups of records of the same kind (and parent, for bullets) that look duplicated."""
    groups: list[list[Record]] = []
    seen: set[str] = set()
    for i, a in enumerate(records):
        if a.id in seen:
            continue
        group = [a]
        for b in records[i + 1 :]:
            if b.id in seen or b.kind != a.kind:
                continue
            if a.kind == RecordKind.BULLET and a.parent_id != b.parent_id:
                continue
            m = match_candidate(a.kind, a.payload(), [b], threshold)
            if m is not None:
                group.append(b)
        if len(group) > 1:
            seen.update(r.id for r in group)
            groups.append(group)
    return groups
