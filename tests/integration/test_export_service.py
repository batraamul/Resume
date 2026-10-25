"""Export service: review gating, validation gating, versions, no-overwrite, engines (DOC-04..07, STU-04..06)."""

from __future__ import annotations

from datetime import date

import pytest

from ris.domain.enums import Confidentiality, RecordKind, Verification
from ris.rendering import export as export_mod
from ris.rendering.export import ExportOptions, ExportService
from ris.rendering.specs import TemplateLibrary
from ris.security.tempfiles import live_temp_dirs
from ris.services.variants import VariantService


@pytest.fixture
def svc(sample_ws):
    return ExportService(sample_ws, TemplateLibrary(), today=date(2026, 10, 24))


def _variant(ws):
    return ws.repo.list(RecordKind.VARIANT)[0]


@pytest.mark.req("DOC-05", "DOC-06", "STU-04", "SEC-04")
def test_export_both_formats_valid_and_logged(sample_ws, svc, tmp_path):
    before_tmp = set(live_temp_dirs())
    out = svc.export_variant(_variant(sample_ws).id, ExportOptions(formats=("docx", "pdf", "txt"), folder=tmp_path / "exports",
                                                                   pdf_engine="builtin"))
    assert out.ok, (out.message, out.report and [(c.name, c.details) for c in out.report.failures])
    assert {f.format for f in out.files} == {"docx", "pdf", "txt"}
    for f in out.files:
        assert f.path.exists() and f.size > 0 and len(f.sha256) == 64
    rows = sample_ws.db.query("SELECT format, status FROM exports")
    assert len(rows) == 3
    assert out.version_id and VariantService(sample_ws.repo).list_versions(_variant(sample_ws).id)
    assert set(live_temp_dirs()) == before_tmp, "temporary folders must be cleaned up"


@pytest.mark.req("STU-06")
def test_never_overwrites_previous_exports(sample_ws, svc, tmp_path):
    opts = ExportOptions(formats=("pdf",), folder=tmp_path / "exports", pdf_engine="builtin", filename="Same name")
    a = svc.export_variant(_variant(sample_ws).id, opts)
    first_bytes = a.files[0].path.read_bytes()
    b = svc.export_variant(_variant(sample_ws).id, opts)
    assert a.files[0].path != b.files[0].path
    assert a.files[0].path.read_bytes() == first_bytes
    assert b.files[0].path.name == "Same name (2).pdf"


@pytest.mark.req("STU-02", "PRF-15", "DEF-06")
def test_review_blocks_unconfirmed_and_review_items(sample_ws, svc, tmp_path):
    var = _variant(sample_ws)
    sample_ws.repo.patch(var.id, exclude_ids=[])  # include the unconfirmed, review-classified project
    out = svc.export_variant(var.id, ExportOptions(formats=("pdf",), folder=tmp_path / "exports", pdf_engine="builtin"))
    assert not out.ok and out.review is not None
    kinds = {i.kind for i in out.review.blocking}
    assert {"unconfirmed", "disclosure"} <= kinds
    assert not (tmp_path / "exports").exists() or not list((tmp_path / "exports").iterdir()), \
        "nothing may be written when review is required"
    glide = next(p for p in sample_ws.repo.list(RecordKind.PROJECT) if p.title.startswith("Glide"))
    sample_ws.repo.set_verification([glide.id], Verification.CONFIRMED)
    sample_ws.repo.set_confidentiality([glide.id], Confidentiality.APPROVED)
    out2 = svc.export_variant(var.id, ExportOptions(formats=("pdf",), folder=tmp_path / "exports", pdf_engine="builtin"))
    assert out2.ok, out2.message


def test_sensitive_warnings_need_acknowledgement(sample_ws, svc, tmp_path):
    pos = next(p for p in sample_ws.repo.list(RecordKind.POSITION) if p.data.is_current)
    sample_ws.repo.create(RecordKind.BULLET, {"text": "Installed receivers at Station Alpha operating at 403.5 MHz."},
                          parent_id=pos.id, verification="confirmed", confidentiality="approved")
    var = _variant(sample_ws)
    sample_ws.repo.patch(var.id, max_pages=None, length="full")
    out = svc.export_variant(var.id, ExportOptions(formats=("pdf",), folder=tmp_path / "exports", pdf_engine="builtin"))
    assert not out.ok and any(i.kind == "sensitive" for i in out.review.items)
    out2 = svc.export_variant(var.id, ExportOptions(formats=("pdf",), folder=tmp_path / "exports", pdf_engine="builtin",
                                                    acknowledge_warnings=True))
    assert out2.ok, out2.message


@pytest.mark.req("DOC-06", "DEF-05")
def test_validation_failure_discards_files(sample_ws, svc, tmp_path):
    """A user override that smuggles confidential wording into the resume must stop the export."""
    var = _variant(sample_ws)
    bullet = next(b for b in sample_ws.repo.list(RecordKind.BULLET) if b.data.text.startswith("Led acceptance"))
    sample_ws.repo.create(RecordKind.CLAIM, {
        "target_bullet_id": bullet.id, "source_record_ids": [bullet.id], "original_text": bullet.data.text,
        "approved_text": "Integrated the Mission computer upgrade — Project SAMPLE-X (restricted) avionics.",
        "status": "approved", "approved_at": "2026-10-24T00:00:00Z"}, parent_id=var.id)
    out = svc.export_variant(var.id, ExportOptions(formats=("docx", "pdf"), folder=tmp_path / "exports",
                                                   pdf_engine="builtin"))
    assert not out.ok and out.review is not None  # the word "restricted" is flagged for review first
    out = svc.export_variant(var.id, ExportOptions(formats=("docx", "pdf"), folder=tmp_path / "exports",
                                                   pdf_engine="builtin", acknowledge_warnings=True))
    assert not out.ok
    assert any(c.name == "confidential" for c in out.report.failures)
    assert not (tmp_path / "exports").exists() or not list((tmp_path / "exports").iterdir())
    assert sample_ws.db.scalar("SELECT COUNT(*) FROM exports") == 0


@pytest.mark.req("DOC-04")
def test_explicit_libreoffice_missing_is_reported(sample_ws, svc, tmp_path, monkeypatch):
    monkeypatch.setattr(export_mod, "find_soffice", lambda *_: None)
    out = svc.export_variant(_variant(sample_ws).id, ExportOptions(formats=("pdf",), folder=tmp_path / "exports",
                                                                   pdf_engine="libreoffice"))
    assert not out.ok and "LibreOffice" in out.message
    auto = svc.export_variant(_variant(sample_ws).id, ExportOptions(formats=("pdf",), folder=tmp_path / "exports",
                                                                    pdf_engine="auto"))
    assert auto.ok and auto.engine == "builtin"


@pytest.mark.req("DOC-07")
def test_fit_to_page_limit_reports_trimming(sample_ws, svc, tmp_path):
    var = _variant(sample_ws)
    sample_ws.repo.patch(var.id, max_pages=1, length="one_page")
    out = svc.export_variant(var.id, ExportOptions(formats=("pdf",), folder=tmp_path / "exports", pdf_engine="builtin"))
    assert out.ok, [(c.name, c.message) for c in out.report.failures]
    assert out.report.page_count == 1
    assert any(t.startswith("Fit to 1 page") for t in out.document.trimmed)


@pytest.mark.req("STU-05", "STU-04")
def test_versions_compare_and_outdated(sample_ws, svc, tmp_path):
    var = _variant(sample_ws)
    vs = VariantService(sample_ws.repo)
    a = svc.export_variant(var.id, ExportOptions(formats=("pdf",), folder=tmp_path / "exports", pdf_engine="builtin"))
    assert not vs.variant_outdated(sample_ws.repo.get(var.id)).outdated
    bullet = next(b for b in sample_ws.repo.list(RecordKind.BULLET) if b.data.text.startswith("Designed and deployed"))
    sample_ws.repo.patch(bullet.id, text="Designed and deployed an IoT monitoring network (revised wording).")
    rep = vs.variant_outdated(sample_ws.repo.get(var.id))
    assert rep.outdated and rep.changed
    b = svc.export_variant(var.id, ExportOptions(formats=("pdf",), folder=tmp_path / "exports", pdf_engine="builtin"))
    diff = vs.compare(a.version_id, b.version_id)
    assert any("revised wording" in line for line in diff)
    # Re-export of the old version reproduces old content.
    old = svc.export_variant(var.id, ExportOptions(formats=("txt",), folder=tmp_path / "exports"), version_id=a.version_id)
    assert old.ok and "revised wording" not in old.files[0].path.read_text(encoding="utf-8")
