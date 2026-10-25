"""End-to-end workflow without the GUI: import → review gate → confirm → analyse → export → backup/restore."""

from __future__ import annotations

from datetime import date

import pytest

from ris.backup.backup import BackupService
from ris.config import AppConfig
from ris.domain.enums import Confidentiality, RecordKind, Verification
from ris.domain.registry import info as kind_info
from ris.intelligence.analysis import analyse
from ris.rendering.export import ExportOptions, ExportService
from ris.rendering.extract import read_pdf
from ris.rendering.specs import TemplateLibrary
from ris.services import portable
from ris.services.profile import ProfileService
from ris.storage.workspace import WorkspaceManager

TODAY = date(2026, 10, 25)


@pytest.mark.req("IMP-01", "PRF-15", "DEF-04", "DOC-06", "STO-03", "STU-04", "GFX-01")
def test_full_workflow_from_import_to_restore(sample_ws, tmp_path):
    # 1. A portable export of the fictional profile becomes the "existing CV" to import.
    exported = portable.export_profile(sample_ws.repo, include_confidential=False, label="e2e")
    mgr = WorkspaceManager(AppConfig.load())
    entry = mgr.create("My Profile", activate=True)
    ws = mgr.open(entry)
    try:
        prev = portable.preview(ws.repo, exported)
        assert prev.candidates
        rep = portable.commit(ws.repo, prev)
        assert rep.created > 40
        facts = [r for r in ws.repo.list() if kind_info(r.kind).is_fact]
        assert facts and all(r.verification == Verification.UNCONFIRMED for r in facts)
        assert all(r.confidentiality in (Confidentiality.REVIEW,) for r in facts if r.kind != RecordKind.PERSONAL)

        lib = TemplateLibrary()
        svc = ExportService(ws, lib, today=TODAY)
        var = next(v for v in ws.repo.list(RecordKind.VARIANT) if v.data.mode == "graphical_profile")
        opts = ExportOptions(formats=("docx", "pdf"), folder=tmp_path / "out", pdf_engine="builtin",
                             acknowledge_warnings=True)
        # 2. The review gate blocks unconfirmed, unreviewed facts.
        blocked = svc.export_variant(var.id, opts)
        assert not blocked.ok and blocked.review and blocked.review.blocking
        assert not (tmp_path / "out").exists() or not any((tmp_path / "out").iterdir())

        # 3. The user confirms the facts and completes the disclosure review.
        prof = ProfileService(ws.repo)
        prof.confirm([r.id for r in facts])
        ws.repo.set_confidentiality([r.id for r in facts if r.confidentiality == Confidentiality.REVIEW],
                                    Confidentiality.APPROVED)

        # 4. Vacancy analysis on the imported notice.
        vac = ws.repo.list(RecordKind.VACANCY)[0]
        res = analyse(prof.snapshot(), vac.data, today=TODAY)
        assert 0 <= res.assessment.score <= 100 and res.results

        # 5. Export succeeds, validates and saves an immutable version.
        out = svc.export_variant(var.id, opts)
        assert out.ok, [(c.name, c.details[:3]) for c in (out.report.failures if out.report else [])]
        pdf = next(f.path for f in out.files if f.format == "pdf")
        text = "\n".join(read_pdf(pdf).page_texts)
        assert "Career Timeline".upper() in text.upper()
        versions = svc.variants.list_versions(var.id)
        assert len(versions) == 1

        # 6. Encrypted backup, a destructive change, then restore.
        backups = BackupService(ws)
        b = backups.create(reason="manual", passphrase="correct horse battery staple")
        count = ws.repo.count()
        for r in ws.repo.list(RecordKind.PUBLICATION):
            ws.repo.delete(r.id)
        assert ws.repo.count() < count
        result = backups.restore(b.path, "correct horse battery staple")
        assert ws.repo.count() == count
        assert result["pre_restore_snapshot"]

        # 7. Re-exporting the saved version reproduces the same content.
        again = svc.export_variant(var.id, opts, version_id=versions[0].id)
        assert again.ok
        pdf2 = next(f.path for f in again.files if f.format == "pdf")
        assert pdf2 != pdf  # never overwritten
        assert read_pdf(pdf2).page_texts == read_pdf(pdf).page_texts
    finally:
        ws.close()
