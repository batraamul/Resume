"""Desktop interface tests (Qt offscreen platform via pytest-qt).

Modal dialogs are replaced with immediate answers so the tests never block.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("pytestqt")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,  # noqa: E402
    QDialog,
    QMessageBox,
)

from ris.config import AppConfig  # noqa: E402
from ris.domain.enums import Confidentiality, RecordKind, Verification  # noqa: E402
from ris.strings import NAV_SECTIONS  # noqa: E402

pytestmark = pytest.mark.gui


@pytest.fixture
def no_modals(monkeypatch):
    """Answer every modal dialog immediately (accept) instead of blocking."""
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted.value)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    import ris.ui.widgets.common as common

    monkeypatch.setattr(common, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(common, "info", lambda *a, **k: None)
    monkeypatch.setattr(common, "error", lambda *a, **k: None)
    for mod in ("ris.ui.widgets.records", "ris.ui.pages.studio", "ris.ui.pages.opportunities", "ris.ui.pages.backup",
                "ris.ui.pages.sync", "ris.ui.pages.library", "ris.ui.pages.exports", "ris.ui.pages.settings",
                "ris.ui.importing", "ris.ui.pages.letters"):
        m = __import__(mod, fromlist=["x"])
        for name in ("confirm", "info", "error"):
            if hasattr(m, name):
                monkeypatch.setattr(m, name, getattr(common, name))
    yield


@pytest.fixture
def window(qtbot, no_modals):
    from ris.ui.application import apply_theme
    from ris.ui.context import AppContext
    from ris.ui.main_window import MainWindow

    cfg = AppConfig.load()
    apply_theme(QApplication.instance(), cfg)
    ctx = AppContext(cfg)
    ctx.today = date(2026, 10, 25)
    ctx.open_active(prefer_sample=True)
    win = MainWindow(ctx)
    qtbot.addWidget(win)
    win.resize(1360, 860)
    win.show()
    yield win
    ctx.close_workspace(backup=False)
    win.close()
    win.deleteLater()
    ctx.deleteLater()
    QApplication.processEvents()
    import gc

    gc.collect()


@pytest.mark.req("UX-01", "UX-02")
def test_navigation_has_eighteen_sections_and_every_page_opens(window, qtbot):
    keys = [k for _g, items in NAV_SECTIONS for k, _t in items]
    assert len(keys) == 18 and set(keys) == set(window.pages)
    for key in keys:
        window.navigate(key, "")
        qtbot.wait(10)
        assert window.stack.currentWidget() is window.pages[key]
        assert window.nav_buttons[key].isChecked()
    assert window.sample_banner.isVisible()
    assert "Fictional Sample" in window.ws_label.text()


@pytest.mark.req("UX-06")
def test_navigation_labels_and_accessible_names(window):
    for _key, button in window.nav_buttons.items():
        assert button.accessibleName().endswith("page")
        assert "_" not in button.text().replace("&&", "&")


@pytest.mark.req("PRF-01", "PRF-06")
def test_create_validate_and_confirm_a_position(window, qtbot):
    page = window.pages["experience"]
    window.navigate("experience", "")
    col = page.collection
    col.add(RecordKind.POSITION)
    form = col.editor.form
    form.set_value("designation", "Test Engineer")
    form.set_value("organisation", "Example Test Organisation")
    form.set_value("start", "2020-13")  # invalid month
    assert not col.editor.save()
    assert col.editor.banner.isVisible() and "Start" in col.editor.banner.text()
    form.set_value("start", "2020-03")
    form.set_value("end", "2021-02")
    assert col.editor.save()
    rec = window.ctx.repo.get(col.editor.record.id)
    assert rec.data.designation == "Test Engineer" and rec.verification == Verification.CONFIRMED
    assert rec.confidentiality == Confidentiality.REVIEW  # work records need a disclosure review
    col.editor.form.set_value("designation", "Test Engineer II")
    assert col.editor.is_dirty()
    col.editor.revert()
    assert not col.editor.is_dirty()


@pytest.mark.req("PRF-15", "DEF-04")
def test_bulk_confirm_and_classify(window):
    page = window.pages["projects"]
    window.navigate("projects", "")
    col = page.collection
    glide = next(r for r in window.ctx.repo.list(RecordKind.PROJECT) if r.verification == Verification.UNCONFIRMED)
    assert col.focus_record(glide.id)
    col.bulk_verify(Verification.CONFIRMED)
    col.bulk_classify(Confidentiality.APPROVED.value)
    rec = window.ctx.repo.get(glide.id)
    assert rec.verification == Verification.CONFIRMED and rec.confidentiality == Confidentiality.APPROVED


@pytest.mark.req("PRF-20", "PRF-21")
def test_profile_page_has_expertise_and_referees(window):
    page = window.pages["profile"]
    window.navigate("profile", "")
    titles = [page.tabs.tabText(i) for i in range(page.tabs.count())]
    assert "Areas of expertise" in titles and "Referees" in titles
    ref = window.ctx.repo.list(RecordKind.REFERENCE)[0]
    window.navigate("record", ref.id)
    assert page.tabs.currentWidget() is page.references
    assert page.references.editor.record.id == ref.id


@pytest.mark.req("STU-01", "STU-02", "UX-08")
def test_studio_preview_renders_pdf(window, qtbot):
    page = window.pages["studio"]
    window.navigate("studio", "")
    assert page.variant_id is not None
    page.update_preview(synchronous=True)
    assert page.preview.page_count >= 1
    assert page.content_tree.topLevelItemCount() > 0
    assert "Before export" in page.checks.toPlainText()


@pytest.mark.req("GFX-01")
def test_studio_graphical_variant_preview(window, qtbot):
    page = window.pages["studio"]
    window.navigate("studio", "")
    var = next(v for v in window.ctx.repo.list(RecordKind.VARIANT) if v.data.mode == "graphical_profile")
    assert page.focus_record(var.id)
    page.update_preview(synchronous=True)
    assert page.preview.page_count >= 1
    assert page.template.currentData() == "graphical_profile"


@pytest.mark.req("DOC-06", "STU-06")
def test_studio_export_validates_and_logs(window, qtbot, tmp_path, monkeypatch):
    from ris.rendering.export import ExportOptions

    page = window.pages["studio"]
    window.navigate("studio", "")
    shown = {}

    import ris.ui.pages.studio as studio_mod

    class _Report:
        def __init__(self, parent, title, html, summary="", tone="info"):
            shown.update(title=title, summary=summary, tone=tone)
            from PySide6.QtWidgets import QDialogButtonBox

            self._bb = QDialogButtonBox()

        def findChild(self, _cls):
            return self._bb

        def exec(self):
            return 1

    monkeypatch.setattr(studio_mod, "ReportDialog", _Report)
    opts = ExportOptions(formats=("docx", "pdf"), folder=tmp_path, pdf_engine="builtin", acknowledge_warnings=True)
    page._run_export(page.variant_id, opts, synchronous=True)
    assert shown.get("title") == "Export complete", shown
    assert list(tmp_path.glob("*.pdf")) and list(tmp_path.glob("*.docx"))
    rows = window.ctx.repo.db.query("SELECT COUNT(*) AS n FROM exports")
    assert rows[0]["n"] == 2


@pytest.mark.req("VAC-04", "VAC-05")
def test_opportunity_analysis_shows_transparent_score(window):
    page = window.pages["opportunities"]
    window.navigate("opportunities", "")
    assert page.current_id is not None
    page.analyse()
    assert page.results.rowCount() > 0
    assert "/100" in page.score_banner.text() and "not a probability" in page.score_banner.text()
    assert "How the score is calculated" in page.explain.toPlainText()


@pytest.mark.req("STO-03")
def test_backup_page_creates_and_verifies(window, qtbot):
    page = window.pages["backup"]
    window.navigate("backup", "")
    svc = window.ctx.backups()
    info = svc.create(reason="manual")
    page.refresh()
    assert page.table.rowCount() >= 1
    page.verify(info.path)
    assert "verified" in page.result.text().lower()


@pytest.mark.req("UX-04")
def test_theme_switch_applies_dark_stylesheet(window):

    window.ctx.config.theme = "dark"
    window.apply_theme()
    assert "#131B2A" in QApplication.instance().styleSheet()
    window.ctx.config.theme = "light"
    window.apply_theme()
    assert "#FFF3DF" in QApplication.instance().styleSheet()


@pytest.mark.req("UX-05")
def test_dashboard_shows_real_counts(window):
    page = window.pages["diary"]
    window.navigate("diary", "")
    snap = window.ctx.snapshot()
    unconfirmed = sum(1 for r in snap.facts() if r.verification == Verification.UNCONFIRMED)
    assert page.t_unconfirmed.value.text() == str(unconfirmed)
    assert page.t_variants.value.text() == str(len(snap.of(RecordKind.VARIANT)))


@pytest.mark.req("SYN-01", "SYN-04")
def test_sync_page_with_in_memory_remote(window, qtbot):
    from ris.sync.remote import MemoryRemote

    remote = MemoryRemote()
    window.ctx.remote_factory = lambda provider: remote
    window.ctx._sync = None
    window.ctx.settings.set("sync.provider", "folder")
    window.ctx.sync().set_passphrase("correct horse battery staple")
    page = window.pages["sync"]
    window.navigate("sync", "")
    page.sync_now()
    qtbot.waitUntil(lambda: page.b_sync.isEnabled(), timeout=20000)
    assert "Synchronised" in page.result.text(), page.result.text()
    assert remote.list_files("ris-sync/")


@pytest.mark.req("TRK-02")
def test_dashboard_lists_upcoming_deadlines(window):
    from ris.domain.models import Application, Vacancy

    repo = window.ctx.repo
    repo.create(RecordKind.VACANCY, Vacancy(title="Deadline Test Post", deadline="2026-11-10"))
    repo.create(RecordKind.APPLICATION, Application(organisation="Example Body", vacancy_title="Interview Test Post",
                                                    status="interview", interview_date="2026-11-02"))
    window.ctx.invalidate()
    page = window.pages["diary"]
    window.navigate("diary", "")
    page.refresh()
    items = [page.deadline_list.item(i).text() for i in range(page.deadline_list.count())]
    assert any("Deadline Test Post" in t and "in 16 days" in t for t in items), items
    assert any("Interview — Interview Test Post" in t and "in 8 days" in t for t in items), items


@pytest.mark.req("SEC-06")
def test_delete_requires_confirmation(window, monkeypatch):
    import ris.ui.widgets.records as records

    page = window.pages["skills"]
    window.navigate("skills", "")
    col = page.collection
    skill = window.ctx.repo.list(RecordKind.SKILL)[0]
    assert col.focus_record(skill.id)
    asked = []
    monkeypatch.setattr(records, "confirm", lambda *a, **k: asked.append(k.get("destructive")) or False)
    col.editor.delete()
    assert asked == [True] and window.ctx.repo.find(skill.id) is not None
    monkeypatch.setattr(records, "confirm", lambda *a, **k: True)
    col.editor.delete()
    assert window.ctx.repo.find(skill.id) is None
    assert any(r.id == skill.id for r in window.ctx.repo.deleted_records())


@pytest.mark.req("PRV-03", "PRV-05")
def test_suggestion_dialog_side_by_side_and_material_gate(window):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPlainTextEdit, QSplitter

    from ris.intelligence.rewriting import rewrite_bullet
    from ris.ui.dialogs import SuggestionDialog

    repo = window.ctx.repo
    bullet = next(b for b in repo.list(RecordKind.BULLET) if b.data.text)
    parent = repo.find(bullet.parent_id) if bullet.parent_id else None
    dlg = SuggestionDialog(window, rewrite_bullet(bullet, parent))
    split = dlg.findChild(QSplitter)
    assert split is not None and split.orientation() == Qt.Orientation.Horizontal and split.count() == 2
    left = [w.toPlainText() for w in split.widget(0).findChildren(QPlainTextEdit)]
    assert left == [bullet.data.text]
    assert split.widget(1).findChild(QPlainTextEdit) is dlg.edit
    dlg.edit.setPlainText(bullet.data.text.rstrip(".") + ", reducing test time by 40%.")
    assert dlg.check.material and not dlg.approve.isEnabled()
    dlg.accuracy.setChecked(True)
    assert dlg.approve.isEnabled()
    dlg.deleteLater()


@pytest.mark.req("DEF-07", "STO-09")
def test_responsibility_and_storage_notices_shown(window):
    from PySide6.QtWidgets import QLabel

    from ris.strings import RESPONSIBILITY_NOTICE, STORAGE_NOTICE

    def texts(page):
        return [lbl.text() for lbl in page.findChildren(QLabel)]

    assert RESPONSIBILITY_NOTICE in texts(window.pages["diary"])
    settings = texts(window.pages["settings"])
    assert RESPONSIBILITY_NOTICE in settings and STORAGE_NOTICE in settings
