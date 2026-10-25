"""Portable JSON format for profiles (export, import with preview, duplicate detection).

Format::

    {
      "format": "resume-intelligence-studio/profile",
      "format_version": 1,
      "app_version": "1.0.0",
      "exported_at": "2026-10-24T10:00:00Z",
      "label": "...",
      "records": [
        {"id": "...", "kind": "position", "parent_id": null, "verification": "confirmed",
         "confidentiality": "review", "origin": "manual", "sort_order": 1, "data": {...}},
        ...
      ]
    }

Hand-written files (sample profile, preliminary profile) may use short
readable ids ("pos-1"); references are remapped to fresh ids on import.
Imported facts are *unconfirmed* and classified *Requires review* unless the
caller explicitly preserves status (fictional sample, own backups).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ris import __version__
from ris.domain import registry
from ris.domain.enums import Confidentiality, Origin, RecordKind, Verification
from ris.errors import ImportFailed
from ris.services.duplicates import DuplicateMatch, match_candidate
from ris.storage.repository import RecordRepository, format_validation_error
from ris.util import new_id, utc_now_iso

FORMAT_ID = "resume-intelligence-studio/profile"
FORMAT_VERSION = 1
MAX_IMPORT_BYTES = 20 * 1024 * 1024
MAX_RECORDS = 20000

# Payload fields that reference other records.
REF_FIELDS_SCALAR = ("related_position_id", "target_id", "vacancy_id", "variant_id", "summary_id",
                     "cover_letter_id", "application_id", "target_bullet_id")
REF_FIELDS_LIST = ("related_project_ids", "related_position_ids", "project_ids", "include_ids", "exclude_ids",
                   "source_record_ids", "linked_ids", "story_ids")
# Kinds imported before their dependants (parents first).
KIND_ORDER = [RecordKind.PERSONAL, RecordKind.SUMMARY, RecordKind.POSITION, RecordKind.ASSIGNMENT,
              RecordKind.PROJECT, RecordKind.ACTIVITY, RecordKind.BULLET, RecordKind.EDUCATION,
              RecordKind.PUBLICATION, RecordKind.SKILL, RecordKind.EXPERTISE, RecordKind.REFERENCE,
              RecordKind.TRAINING, RecordKind.CUSTOM_SECTION, RecordKind.CUSTOM_ENTRY,
              RecordKind.CAREER_TARGET, RecordKind.VACANCY, RecordKind.VARIANT, RecordKind.CLAIM,
              RecordKind.COVER_LETTER, RecordKind.APPLICATION, RecordKind.INTERVIEW_STORY,
              RecordKind.INTERVIEW_ANSWER, RecordKind.QUESTIONNAIRE]


def export_profile(repo: RecordRepository, *, include_confidential: bool = True, label: str = "",
                   kinds: list[RecordKind] | None = None) -> dict[str, Any]:
    recs = repo.list(kinds=kinds) if kinds else repo.list()
    excluded_ids: set[str] = set()
    if not include_confidential:
        # Exclude confidential records and everything beneath them.
        by_parent: dict[str, list[str]] = {}
        for r in recs:
            if r.parent_id:
                by_parent.setdefault(r.parent_id, []).append(r.id)
        stack = [r.id for r in recs if r.confidentiality == Confidentiality.CONFIDENTIAL]
        while stack:
            rid = stack.pop()
            if rid in excluded_ids:
                continue
            excluded_ids.add(rid)
            stack.extend(by_parent.get(rid, []))
    records = []
    for r in recs:
        if r.id in excluded_ids:
            continue
        records.append({
            "id": r.id, "kind": r.kind.value, "parent_id": r.parent_id, "sort_order": r.sort_order,
            "verification": r.verification.value, "confidentiality": r.confidentiality.value,
            "origin": r.origin.value, "created_at": r.created_at, "updated_at": r.updated_at,
            "revision": r.revision, "data": r.payload(),
        })
    return {
        "format": FORMAT_ID, "format_version": FORMAT_VERSION, "app_version": __version__,
        "exported_at": utc_now_iso(), "label": label,
        "excluded_confidential": len(excluded_ids), "records": records,
    }


def write_export(repo: RecordRepository, path: Path, **kw) -> Path:
    data = export_profile(repo, **kw)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_payload(path: Path) -> dict[str, Any]:
    path = Path(path)
    size = path.stat().st_size
    if size > MAX_IMPORT_BYTES:
        raise ImportFailed(f"The file is too large to import ({size // 1024 // 1024} MB; limit 20 MB).")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ImportFailed("The file is not UTF-8 text.") from exc
    except ValueError as exc:
        raise ImportFailed(f"The file is not valid JSON ({exc}).") from exc
    return validate_payload(data)


def validate_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("format") != FORMAT_ID:
        raise ImportFailed("This is not a Resume Intelligence Studio profile file.")
    if int(data.get("format_version", 0)) > FORMAT_VERSION:
        raise ImportFailed("This file was written by a newer version of the application.")
    records = data.get("records")
    if not isinstance(records, list):
        raise ImportFailed("The file has no records list.")
    if len(records) > MAX_RECORDS:
        raise ImportFailed("The file contains too many records.")
    return data


@dataclass
class ImportCandidate:
    source_id: str
    kind: RecordKind
    parent_source_id: str | None
    data: dict[str, Any]
    verification: str
    confidentiality: str
    title: str
    errors: list[str] = field(default_factory=list)
    duplicate: DuplicateMatch | None = None
    include: bool = True

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass
class ImportPreview:
    candidates: list[ImportCandidate]
    label: str = ""

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.candidates:
            out[c.kind.value] = out.get(c.kind.value, 0) + 1
        return out


def preview(repo: RecordRepository, data: dict[str, Any], *, detect_duplicates: bool = True) -> ImportPreview:
    data = validate_payload(data)
    existing = repo.list() if detect_duplicates else []
    cands: list[ImportCandidate] = []
    for raw in data["records"]:
        if not isinstance(raw, dict):
            continue
        try:
            kind = RecordKind(raw.get("kind"))
        except ValueError:
            continue
        payload = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        model = registry.model_for(kind)
        errors: list[str] = []
        title = ""
        try:
            obj = model.model_validate(payload)
            title = obj.display_title()
        except ValidationError as exc:
            errors = format_validation_error(model, exc)
            title = str(payload.get("title") or payload.get("name") or payload.get("designation") or kind.value)
        cand = ImportCandidate(
            source_id=str(raw.get("id") or new_id()), kind=kind, parent_source_id=raw.get("parent_id"),
            data=payload, verification=str(raw.get("verification", "unconfirmed")),
            confidentiality=str(raw.get("confidentiality", "review")), title=title, errors=errors,
        )
        if detect_duplicates and not errors and kind != RecordKind.PERSONAL:
            cand.duplicate = match_candidate(kind, payload, existing)
            if cand.duplicate is not None:
                cand.include = False
        if errors:
            cand.include = False
        cands.append(cand)
    return ImportPreview(cands, label=str(data.get("label", "")))


@dataclass
class ImportReport:
    created: int = 0
    skipped: int = 0
    merged_personal: bool = False
    errors: list[str] = field(default_factory=list)
    id_map: dict[str, str] = field(default_factory=dict)


def commit(repo: RecordRepository, prev: ImportPreview, *, origin: Origin = Origin.IMPORTED,
           preserve_status: bool = False) -> ImportReport:
    """Create the selected candidates in one transaction, remapping references."""
    report = ImportReport()
    selected = [c for c in prev.candidates if c.include and c.valid]
    selected_ids = {c.source_id for c in selected}
    # Children whose parent was not selected cannot be imported.
    changed = True
    while changed:
        changed = False
        for c in list(selected):
            if c.parent_source_id and c.parent_source_id not in selected_ids:
                selected.remove(c)
                selected_ids.discard(c.source_id)
                report.skipped += 1
                report.errors.append(f"Skipped '{c.title}' because its parent record was not imported.")
                changed = True
    id_map = {c.source_id: new_id() for c in selected}
    order = {k: i for i, k in enumerate(KIND_ORDER)}
    selected.sort(key=lambda c: order.get(c.kind, 99))

    def remap(payload: dict[str, Any]) -> dict[str, Any]:
        out = dict(payload)
        for f in REF_FIELDS_SCALAR:
            if isinstance(out.get(f), str) and out[f]:
                out[f] = id_map.get(out[f], "")
        for f in REF_FIELDS_LIST:
            if isinstance(out.get(f), list):
                out[f] = [id_map[x] for x in out[f] if isinstance(x, str) and x in id_map]
        if "requirements" in out and isinstance(out["requirements"], list):
            out["requirements"] = [dict(r) for r in out["requirements"] if isinstance(r, dict)]
        return out

    with repo.db.transaction():
        for c in selected:
            payload = remap(c.data)
            if preserve_status:
                ver = c.verification if c.verification in {v.value for v in Verification} else "unconfirmed"
                conf = c.confidentiality if c.confidentiality in {x.value for x in Confidentiality} else "review"
            else:
                ver = Verification.UNCONFIRMED.value if registry.info(c.kind).is_fact else Verification.CONFIRMED.value
                conf = registry.default_confidentiality(c.kind, origin).value
                if c.confidentiality == Confidentiality.CONFIDENTIAL.value:
                    conf = Confidentiality.CONFIDENTIAL.value  # never downgrade a confidential marking
            parent = id_map.get(c.parent_source_id) if c.parent_source_id else None
            if c.kind == RecordKind.PERSONAL:
                existing = repo.singleton(RecordKind.PERSONAL)
                if existing is not None:
                    merged = existing.payload()
                    for k, v in payload.items():
                        if v and not merged.get(k):
                            merged[k] = v
                    repo.update(existing.id, merged)
                    id_map[c.source_id] = existing.id
                    report.merged_personal = True
                    continue
            rec = repo.create(c.kind, payload, parent_id=parent, verification=ver, confidentiality=conf,
                              origin=origin, record_id=id_map[c.source_id])
            report.created += 1
            del rec
    report.skipped += sum(1 for c in prev.candidates if not (c.include and c.valid))
    report.id_map = id_map
    return report


def import_file(repo: RecordRepository, path: Path, **kw) -> ImportReport:
    data = load_payload(path)
    return commit(repo, preview(repo, data), **kw)
