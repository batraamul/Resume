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
def test_navigation_sections_and_every_page_opens(window, qtbot):
    keys = [k for _g, items in NAV_SECTIONS for k, _t in items]
    assert len(keys) == 21 and set(keys) == set(window.pages)
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


@pytest.mark.req("PRF-23")
def test_training_page_lists_and_creates_records(window):
    page = window.pages["training"]
    window.navigate("training", "")
    col = page.collection
    col.add(RecordKind.TRAINING)
    form = col.editor.form
    form.set_value("title", "Advanced Radar Signal Processing")
    form.set_value("training_type", "workshop")
    form.set_value("provider", "Example Institute")
    form.set_value("end", "2025-02")
    assert col.editor.save()
    rec = window.ctx.repo.get(col.editor.record.id)
    assert rec.kind == RecordKind.TRAINING and rec.data.training_type == "workshop"


@pytest.mark.req("INT-02", "INT-05")
def test_interview_page_questions_answers_and_practice(window):
    page = window.pages["interview"]
    window.navigate("interview", "")
    assert page.qtree.topLevelItemCount() > 40
    mine = [q for q in page.questions if q.personalised]
    assert mine
    rec = page.prepare_answer(mine[0])
    assert rec.kind == RecordKind.INTERVIEW_ANSWER and page.answers.editor.record.id == rec.id
    page.n_questions.setValue(3)
    page.start_practice()
    assert page.p_question.text() and "Question 1 of 3" in page.p_progress.text()
    page.p_notes.setPlainText("Key points: scope, team, result.")
    page.p_conf.setValue(4)
    saved = page.save_practice()
    assert saved.data.confidence == 4 and saved.data.times_practised >= 1
    page.next_question()
    assert "Question 2 of 3" in page.p_progress.text()


@pytest.mark.req("INT-03")
def test_interview_story_check(window):
    page = window.pages["interview"]
    window.navigate("interview", "")
    page.tabs.setCurrentIndex(3)
    page.stories.add(RecordKind.INTERVIEW_STORY)
    form = page.stories.editor.form
    form.set_value("title", "Receiver failure")
    form.set_value("situation", "Long background " * 30)
    form.set_value("task", "We had to deliver.")
    form.set_value("action", "We fixed it.")
    form.set_value("result", "It worked.")
    a = page.check_story()
    assert a is not None and a.issues and "Situation is" in page.story_check.toPlainText()


@pytest.mark.req("INT-04")
def test_questionnaire_tab_fill_check_and_save(window):
    page = window.pages["interview"]
    window.navigate("interview", "")
    rec = page.new_questionnaire()
    assert page.questionnaire_rec.id == rec.id
    page.fill_from_profile()
    assert page.q_tables["education"].rows()
    page.q_form.set_value("hobbies", "cycling, chess")
    assert page.save_questionnaire()
    saved = window.ctx.repo.get(rec.id)
    assert saved.data.hobbies == ["cycling", "chess"] and saved.data.education
    issues = page.check_questionnaire()
    assert any(i.area == "Completeness" for i in issues)
    assert page.q_issues.count() >= 1


@pytest.mark.req("POR-02", "POR-04")
def test_portals_page_kit_ats_and_target(window, tmp_path):
    page = window.pages["portals"]
    window.navigate("portals", "")
    kit = page.build_kit()
    assert {"linkedin", "naukri", "indeed"} <= set(kit) and page.kit_tree.topLevelItemCount() == 3
    path = page.save_kit(str(tmp_path / "kit.txt"))
    assert "=== LinkedIn ===" in path.read_text(encoding="utf-8")
    page.tabs.setCurrentIndex(3)
    rep = page.check_variant()
    assert rep is not None and page.ats_tree.topLevelItemCount() == len(rep.checks)
    assert "ATS readiness" in page.ats_score.text()
    page.tabs.setCurrentIndex(0)
    for i in range(page.rec_list.count()):
        if page.rec_list.item(i).data(0x0100)["id"] == "isro":
            page.rec_list.setCurrentRow(i)
    target = page._make_target()
    assert target is not None and target.kind == RecordKind.CAREER_TARGET


@pytest.mark.req("STU-07")
def test_studio_add_section(window, qtbot):
    page = window.pages["studio"]
    window.navigate("studio", "")
    before = page.sections.count()
    page._fill_add_section_menu()
    assert page.b_add_section.menu().actions()
    page.add_section("workshops")
    assert page.sections.count() == before + 1
    page._flush_save()
    rec = window.ctx.repo.get(page.variant_id)
    assert "workshops" in rec.data.section_order


@pytest.mark.req("UX-09", "UX-10")
def test_appearance_dialog_applies_and_undoes(window, tmp_path):
    page = window.pages["settings"]
    window.navigate("settings", "")
    dlg = page.customise_appearance(exec_dialog=False)
    dlg.preset.setCurrentIndex(dlg.preset.findData("forest"))
    dlg.nav_style.setCurrentIndex(dlg.nav_style.findData("icons"))
    dlg.editor_layout.setCurrentIndex(dlg.editor_layout.findData("stacked"))
    dlg.set_colour("accent", "#123456")
    dlg.apply_now()
    css = QApplication.instance().styleSheet()
    assert "#123456" in css and "#1E5B3F" in css  # custom accent and the forest navigation colour
    assert window.nav.width() == 64 and window.nav_buttons["diary"].text() == "✎"
    from PySide6.QtCore import Qt as _Qt

    assert window.pages["experience"].collection.split.orientation() == _Qt.Orientation.Vertical
    path = dlg.export_settings(str(tmp_path / "look.json"))
    assert path.exists()
    dlg.reject()
    assert "#123456" not in QApplication.instance().styleSheet()
    assert window.nav.width() == 250
    dlg2 = page.customise_appearance(exec_dialog=False)
    assert dlg2.import_settings(str(tmp_path / "look.json"))
    assert window.ctx.config.appearance["preset"] == "forest"
    dlg2.reject()


@pytest.mark.req("TPL-03", "TPL-04", "TPL-06")
def test_template_designer_saves_copy_with_live_checks(window, qtbot, tmp_path):
    from ris.ui.workers import wait_idle

    page = window.pages["library"]
    window.navigate("library", "")
    for i in range(page.templates.count()):
        if page.templates.item(i).data(0x0100) == "modern_professional":
            page.templates.setCurrentRow(i)
    dlg = page._edit_template(exec_dialog=False)
    assert ("colours", "accent") in dlg.editors and ("graphics", "palette") in dlg.editors
    dlg.scheme.setCurrentIndex(dlg.scheme.findData("Teal modern"))
    dlg.set_value("fonts", "body_size", 11.0)
    dlg.update_preview()
    wait_idle(30000)
    qtbot.waitUntil(lambda: hasattr(dlg, "last_checks"), timeout=30000)
    ats, notes = dlg.last_checks
    assert ats.score > 0 and not notes
    dlg.set_value("colours", "text", "#DDDDDD")
    spec, err = dlg.spec_or_error()
    assert spec is not None and any("Text: contrast" in n for n in dlg.readability(spec))
    dlg.set_value("colours", "text", "#1F1F1F")
    dlg.ats.setChecked(True)
    spec, err = dlg.spec_or_error()
    assert spec is not None and spec.ats_safe and not spec.columns.enabled and not err
    out = dlg.export_json(str(tmp_path / "t.json"))
    assert out.exists()
    dlg.name.setText("My Teal ATS")
    saved = dlg.save(as_new=True)
    assert saved is not None and not saved.builtin and saved.id.startswith("user_my_teal_ats")
    assert saved.colours.accent == "#0F6E5C" and saved.fonts.body_size == 11.0 and saved.ats_safe
    assert window.ctx.templates.get("modern_professional").colours.accent != "#0F6E5C"  # built-in unchanged


@pytest.mark.req("UPD-02", "UPD-03", "UPD-04")
def test_update_check_dialog_and_settings(window, monkeypatch, tmp_path):
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from ris.ui.updates import UpdateDialog, due_for_check
    from ris.update.client import UpdateClient
    from tests.unit.test_updates import REPO, _server

    key = Ed25519PrivateKey.generate()
    pubs = (base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,
                                                           serialization.PublicFormat.Raw)).decode(),)
    opener, asset = _server(key)
    factory = lambda: UpdateClient(repository=REPO, current_version="1.1.0", keys=pubs, opener=opener)  # noqa: E731
    window.updater.client_factory = factory
    found = []
    window.updater.found.connect(found.append)
    window._manual_check = False
    window.updater.check(manual=False, synchronous=True)
    assert found and window.update_button.isVisible() and "9.0.0" in window.update_button.text()
    assert window.ctx.config.update_last_check and not due_for_check(window.ctx.config)
    dlg = UpdateDialog(window, window.ctx, found[0], client_factory=factory)
    assert "Signature verified" in dlg.status.text()
    dlg.download_and_install(synchronous=True, run=False)
    assert dlg.downloaded is not None and dlg.downloaded.read_bytes() == b"installer-bytes"
    assert dlg.plan is not None and "Download verified" in dlg.status.text()
    dlg.skip()
    assert window.ctx.config.update_skipped_version == "9.0.0"
    found.clear()
    window.updater.check(manual=False, synchronous=True)
    assert not found, "a skipped version is not offered again automatically"
    page = window.pages["settings"]
    window.navigate("settings", "")
    page.update_auto.setChecked(False)
    assert window.ctx.config.update_auto_check is False and not due_for_check(window.ctx.config)
