"""Resume variants: immutable versions, comparison and outdated detection (STU-04/05/06)."""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from typing import Any

from ris.composition.ir import ResumeDocument
from ris.domain.enums import RecordKind
from ris.errors import NotFound
from ris.storage.repository import Record, RecordRepository
from ris.util import canonical_json, new_id, sha256_text, utc_now_iso


@dataclass
class VersionInfo:
    id: str
    variant_id: str
    version_no: int
    created_at: str
    label: str
    template_id: str
    template_version: str
    checksum: str

    @property
    def title(self) -> str:
        return f"v{self.version_no}" + (f" — {self.label}" if self.label else "")


@dataclass
class OutdatedReport:
    changed: list[str]  # titles of source records changed since the version
    deleted: int
    outdated: bool

    def summary(self) -> str:
        if not self.outdated:
            return "Up to date with your profile."
        bits = []
        if self.changed:
            bits.append(f"{len(self.changed)} source record(s) changed")
        if self.deleted:
            bits.append(f"{self.deleted} removed")
        return "May be outdated: " + ", ".join(bits) + "."


class VariantService:
    def __init__(self, repo: RecordRepository) -> None:
        self.repo = repo
        self.db = repo.db

    # ------------------------------------------------------------------ versions
    def save_version(self, variant_id: str, doc: ResumeDocument, *, settings: dict[str, Any],
                     template_spec: dict[str, Any], label: str = "") -> VersionInfo:
        if self.repo.find(variant_id) is None:
            raise NotFound("The resume variant no longer exists.")
        payload_doc = doc.to_json_dict()
        settings_full = {"variant": settings, "template_spec": template_spec}
        checksum = sha256_text(canonical_json({"doc": payload_doc, "settings": settings_full}))
        with self.db.transaction():
            n = int(self.db.scalar("SELECT COALESCE(MAX(version_no), 0) FROM variant_versions WHERE variant_id = ?",
                                   (variant_id,)) or 0) + 1
            vid = new_id()
            self.db.execute(
                "INSERT INTO variant_versions (id, variant_id, version_no, created_at, label, settings, document,"
                " source_revisions, template_id, template_version, checksum) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (vid, variant_id, n, utc_now_iso(), label[:120], json.dumps(settings_full, ensure_ascii=False),
                 json.dumps(payload_doc, ensure_ascii=False), json.dumps(doc.source_revisions),
                 doc.template_id, doc.template_version, checksum),
            )
        return self.get_info(vid)

    def _row_info(self, row) -> VersionInfo:
        return VersionInfo(row["id"], row["variant_id"], int(row["version_no"]), row["created_at"], row["label"],
                           row["template_id"], row["template_version"], row["checksum"])

    def get_info(self, version_id: str) -> VersionInfo:
        row = self.db.query_one("SELECT * FROM variant_versions WHERE id = ?", (version_id,))
        if row is None:
            raise NotFound("That version no longer exists.")
        return self._row_info(row)

    def list_versions(self, variant_id: str) -> list[VersionInfo]:
        rows = self.db.query("SELECT * FROM variant_versions WHERE variant_id = ? ORDER BY version_no DESC",
                             (variant_id,))
        return [self._row_info(r) for r in rows]

    def load_document(self, version_id: str) -> tuple[ResumeDocument, dict[str, Any]]:
        row = self.db.query_one("SELECT document, settings, checksum FROM variant_versions WHERE id = ?", (version_id,))
        if row is None:
            raise NotFound("That version no longer exists.")
        doc_raw = json.loads(row["document"])
        settings = json.loads(row["settings"])
        actual = sha256_text(canonical_json({"doc": doc_raw, "settings": settings}))
        if actual != row["checksum"]:
            raise NotFound("This version failed its integrity check and cannot be used.")
        return ResumeDocument.model_validate(doc_raw), settings

    def delete_version(self, version_id: str) -> None:
        self.db.execute("DELETE FROM variant_versions WHERE id = ?", (version_id,))

    # ------------------------------------------------------------------ comparison
    @staticmethod
    def document_lines(doc: ResumeDocument) -> list[str]:
        lines: list[str] = []
        for s in doc.sections:
            lines.append(f"## {s.title}")
            lines.extend(s.paragraphs)
            lines.extend(f"• {i}" for i in s.items)
            for g in s.skill_groups:
                lines.append(f"{g.label}: {', '.join(g.items)}")
            if s.table:
                lines.extend(" | ".join(r) for r in s.table.rows)
            for e in s.entries:
                stack = [(e, 0)]
                while stack:
                    cur, depth = stack.pop(0)
                    head = " — ".join(x for x in (cur.title, cur.subtitle, cur.date_text) if x)
                    lines.append(("  " * depth) + head)
                    if cur.citation_rest:
                        lines.append(("  " * depth) + cur.citation_rest)
                    lines.extend(("  " * depth) + f"• {b.text}" for b in cur.bullets)
                    stack.extend((c, depth + 1) for c in cur.children)
        return lines

    def compare(self, version_a: str, version_b: str) -> list[str]:
        a, _ = self.load_document(version_a)
        b, _ = self.load_document(version_b)
        ia, ib = self.get_info(version_a), self.get_info(version_b)
        return list(difflib.unified_diff(self.document_lines(a), self.document_lines(b),
                                         fromfile=ia.title, tofile=ib.title, lineterm=""))

    def compare_html(self, version_a: str, version_b: str) -> str:
        a, _ = self.load_document(version_a)
        b, _ = self.load_document(version_b)
        ia, ib = self.get_info(version_a), self.get_info(version_b)
        return difflib.HtmlDiff(wrapcolumn=70).make_table(self.document_lines(a), self.document_lines(b),
                                                           ia.title, ib.title, context=True, numlines=2)

    # ------------------------------------------------------------------ outdated detection
    def outdated(self, source_revisions: dict[str, int]) -> OutdatedReport:
        current = self.repo.revisions(source_revisions.keys())
        changed: list[str] = []
        deleted = 0
        for rid, rev in source_revisions.items():
            cur = current.get(rid)
            if cur is None or cur == -1:
                deleted += 1
            elif cur != rev:
                rec = self.repo.find(rid)
                changed.append(rec.title if rec else rid)
        return OutdatedReport(changed=sorted(changed), deleted=deleted, outdated=bool(changed or deleted))

    def variant_outdated(self, variant: Record) -> OutdatedReport:
        versions = self.list_versions(variant.id)
        revisions = variant.data.source_revisions
        if versions:
            doc, _ = self.load_document(versions[0].id)
            revisions = doc.source_revisions
        if not revisions:
            return OutdatedReport([], 0, False)
        return self.outdated(revisions)

    def variants(self) -> list[Record]:
        return self.repo.list(RecordKind.VARIANT)
