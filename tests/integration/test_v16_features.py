"""Fresh Start, template advice, the deputation proforma guide and the help content (FS-01, TPL-07, FMT-04, HLP-01)."""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

from ris.backup.backup import BackupService
from ris.domain.enums import RecordKind
from ris.intelligence.proforma_guide import MISSING, READY, proforma_readiness
from ris.intelligence.template_advice import profile_traits, recommend_templates, template_tags
from ris.rendering.specs import TemplateLibrary
from ris.services.fresh_start import FreshStartError, fresh_start
from ris.services.profile import ProfileService

ROOT = Path(__file__).resolve().parents[2]
LIB = TemplateLibrary()


@pytest.mark.req("SEC-QT")
def test_no_pyqt_only_names_in_the_source():
    """PySide6 has Signal/Slot, not pyqtSignal/pyqtSlot. Importing them crashes the packaged app."""
    bad = []
    for path in (ROOT / "ris").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(("PySide6", "PyQt")):
                for alias in node.names:
                    if alias.name.startswith("pyqt") or node.module.startswith("PyQt"):
                        bad.append(f"{path.relative_to(ROOT)}: {node.module}.{alias.name}")
    assert not bad, bad


@pytest.mark.req("TPL-07")
def test_template_library_has_thirty_plus_valid_templates():
    specs = LIB.list()
    assert not LIB.load_errors
    assert len(specs) >= 30
    ats = [s for s in specs if s.ats_safe]
    assert len(ats) >= 8
    assert sum(1 for s in specs if s.columns.enabled) >= 4
    for s in specs:
        assert "all" in template_tags(s)


@pytest.mark.req("TPL-07")
def test_recommendations_follow_the_profile(sample_ws):
    snap = ProfileService(sample_ws.repo).snapshot()
    traits = profile_traits(snap, date(2026, 11, 15))
    assert not traits.is_empty and traits.publications >= 3
    recs = recommend_templates(snap, LIB.list(), today=date(2026, 11, 15))
    assert 1 <= len(recs) <= 6
    assert all(r.reasons and r.reason_text().startswith("Suggested because") for r in recs)
    ids = {s.id for s in LIB.list()}
    assert all(r.template_id in ids for r in recs)
    assert [r.score for r in recs] == sorted((r.score for r in recs), reverse=True)


@pytest.mark.req("TPL-07")
def test_deputation_vacancy_puts_the_proforma_first(sample_ws):
    sample_ws.repo.create(RecordKind.VACANCY, {"title": "Scientist F", "recruitment_mode": "deputation"})
    snap = ProfileService(sample_ws.repo).snapshot()
    recs = recommend_templates(snap, LIB.list(), today=date(2026, 11, 15))
    assert recs[0].template_id == "dopt_proforma"


@pytest.mark.req("TPL-07")
def test_empty_profile_gets_starting_points(workspace):
    snap = ProfileService(workspace.repo).snapshot()
    recs = recommend_templates(snap, LIB.list())
    assert recs and recs[0].template_id == "ats_minimal"


@pytest.mark.req("FMT-04")
def test_proforma_readiness_lists_all_eighteen_items(workspace, sample_ws):
    empty = proforma_readiness(ProfileService(workspace.repo).snapshot())
    assert [i.number for i in empty] == [str(n) for n in range(1, 19)]
    assert any(i.status == MISSING for i in empty)
    full = proforma_readiness(ProfileService(sample_ws.repo).snapshot())
    assert next(i for i in full if i.number == "4").status == READY


@pytest.mark.req("FS-01")
def test_fresh_start_backs_up_then_removes_everything(tmp_path):
    from ris.services.sample import load_sample_profile
    from ris.storage.workspace import Workspace

    ws = Workspace(tmp_path / "mine", "Mine", is_sample=True, device_id="t").open()
    try:
        load_sample_profile(ws)
        ws.is_sample = False  # treat it as the user's own data
        before = ws.repo.count()
        assert before > 20
        result = fresh_start(ws)
        assert result.records_removed == before and result.purged
        assert ws.repo.count() == 0 and not ws.repo.deleted_records()
        assert result.backup_path.exists()
        restored = BackupService(ws).restore(result.backup_path)
        assert restored is not None
    finally:
        ws.close()
    ws = Workspace(tmp_path / "mine", "Mine", device_id="t").open()
    try:
        assert ws.repo.count() == before
    finally:
        ws.close()


@pytest.mark.req("FS-01")
def test_fresh_start_refuses_the_sample_workspace(sample_ws):
    with pytest.raises(FreshStartError):
        fresh_start(sample_ws)
    assert sample_ws.repo.count() > 0


@pytest.mark.req("FS-01")
def test_fresh_start_with_sync_soft_deletes(tmp_path):
    from ris.services.sample import load_sample_profile
    from ris.storage.workspace import Workspace

    ws = Workspace(tmp_path / "synced", "Synced", is_sample=True, device_id="t").open()
    try:
        load_sample_profile(ws)
        ws.is_sample = False
        ws.settings.set("sync.provider", "folder")
        result = fresh_start(ws)
        assert not result.purged and ws.repo.count() == 0 and ws.repo.deleted_records()
    finally:
        ws.close()


@pytest.mark.req("HLP-01")
def test_help_covers_every_page_and_key_fields():
    from ris.strings import NAV_SECTIONS
    from ris.ui.widgets.help_system import FIELD_GUIDE, GUIDES, guide_html

    for key in ("profile", "experience", "education", "research", "skills", "projects", "studio", "gallery",
                "deputation", "settings"):
        assert key in GUIDES and guide_html(key)
    nav = {k for _g, items in NAV_SECTIONS for k, _t in items}
    assert {"gallery", "deputation"} <= nav
    for kind in ("personal", "position", "bullet", "education", "publication", "skill", "project"):
        assert any(k == kind for k, _f in FIELD_GUIDE)
