"""Resume Studio: compose a tailored resume, review every claim, preview the layout and export."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ris.composition.modes import MODES, PROFORMA_SECTIONS, SECTION_TITLES, get_mode
from ris.domain import registry
from ris.domain.charts import CHARTS
from ris.domain.enums import Confidentiality, RecordKind, ResumeLength, SummaryFocus, Verification, choices, label
from ris.domain.models import Variant
from ris.errors import RISError
from ris.strings import PAGE_SUBTITLES
from ris.ui.dialogs import ReportDialog, ReviewDialog, SuggestionDialog, report_html
from ris.ui.widgets.common import (
    Card,
    Page,
    ask_text,
    banner,
    button,
    confirm,
    error,
    esc,
    info,
    muted,
    scroll,
    set_banner,
)
from ris.ui.widgets.pdf_preview import PdfPreview
from ris.ui.workers import run_task
from ris.util import utc_now_iso

log = logging.getLogger(__name__)

CONTACT_KEYS = [("email", "Email"), ("phone", "Telephone"), ("location", "Location"), ("linkedin", "LinkedIn"),
                ("github", "GitHub"), ("website", "Website"), ("portfolio", "Portfolio"), ("orcid", "ORCID"),
                ("google_scholar", "Google Scholar"), ("researchgate", "ResearchGate"), ("scopus_id", "Scopus ID"),
                ("researcher_id", "ResearcherID"), ("naukri", "Naukri"), ("indeed", "Indeed")]
PARTICULARS = [("date_of_birth", "Date of birth"), ("date_of_entry_into_service", "Date of entry into service"),
               ("present_pay_level", "Present pay level"), ("nature_of_employment", "Nature of present employment"),
               ("nationality", "Nationality"), ("home_address", "Address for correspondence")]
#: Extra particulars that only the deputation proforma prints (items 3, 9–15 and 18).
PROFORMA_PARTICULARS = [("date_of_retirement", "Date of retirement (item 3)"),
                        ("employer_type", "Type of present employer (item 11)"),
                        ("present_deputation_details", "Present deputation / contract details (item 9)"),
                        ("past_deputation_details", "Previous deputation(s) (item 10)"),
                        ("feeder_grade_status", "Feeder grade status (item 12)"),
                        ("pay_revision_details", "Revised pay scale details (item 13)"),
                        ("basic_pay", "Basic pay (item 14)"), ("total_emoluments", "Total emoluments (item 14)"),
                        ("non_central_pay_details", "Non-Central pay details (item 15)"),
                        ("sc_st_status", "Whether belongs to SC / ST (item 18)")]
BASIS_CHOICES = ["", "Deputation (ISTC)", "Deputation (STC)", "Absorption", "Re-employment", "Short-term contract"]
PICKER_KINDS = [RecordKind.POSITION, RecordKind.ASSIGNMENT, RecordKind.BULLET, RecordKind.EDUCATION,
                RecordKind.PUBLICATION, RecordKind.PROJECT, RecordKind.SKILL, RecordKind.ACTIVITY,
                RecordKind.EXPERTISE, RecordKind.REFERENCE, RecordKind.CUSTOM_ENTRY]


def eligibility_reason(snap, rec) -> str:
    v = snap.effective_verification(rec)
    c = snap.effective_confidentiality(rec)
    if c == Confidentiality.CONFIDENTIAL:
        return "Confidential — never exported"
    if v == Verification.UNCONFIRMED:
        return "Awaiting confirmation"
    if c == Confidentiality.REVIEW:
        return "Requires disclosure review"
    return ""


class RecordPickerDialog(QDialog):
    """Choose which eligible records this resume may include (unticked = excluded)."""

    def __init__(self, parent: QWidget | None, ctx, variant: Variant) -> None:
        super().__init__(parent)
        self.setWindowTitle("Records in this resume")
        self.resize(820, 620)
        lay = QVBoxLayout(self)
        lay.addWidget(muted("Untick records to leave them out of this resume. Records awaiting confirmation, "
                            "requiring review or marked Confidential cannot be included until their status changes."))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Record", "Status"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setAccessibleName("Records")
        lay.addWidget(self.tree, 1)
        snap = ctx.snapshot()
        excluded = set(variant.exclude_ids)
        self.items: dict[str, QTreeWidgetItem] = {}

        def add(rec, parent_item):
            reason = eligibility_reason(snap, rec)
            it = QTreeWidgetItem([("• " if rec.kind == RecordKind.BULLET else "") + (rec.title or label(rec.kind)),
                                  reason or "Eligible"])
            it.setData(0, Qt.ItemDataRole.UserRole, rec.id)
            if reason:
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                it.setDisabled(True)
            else:
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(0, Qt.CheckState.Unchecked if rec.id in excluded else Qt.CheckState.Checked)
                self.items[rec.id] = it
            (parent_item.addChild(it) if parent_item else self.tree.addTopLevelItem(it))
            for k in snap.kids(rec.id):
                if k.kind in PICKER_KINDS:
                    add(k, it)

        groups: dict[RecordKind, QTreeWidgetItem] = {}
        for kind in PICKER_KINDS:
            for rec in snap.of(kind):
                if rec.parent_id and snap.get(rec.parent_id) is not None:
                    continue
                if kind not in groups:
                    g = QTreeWidgetItem([label(kind) + "s" if not label(kind).endswith("s") else label(kind), ""])
                    g.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    self.tree.addTopLevelItem(g)
                    groups[kind] = g
                add(rec, groups[kind])
        self.tree.expandAll()
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def excluded_ids(self) -> list[str]:
        return sorted(rid for rid, it in self.items.items() if it.checkState(0) == Qt.CheckState.Unchecked)


class ExportDialog(QDialog):
    def __init__(self, parent: QWidget | None, ctx, default_name: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export resume")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        fmts = QHBoxLayout()
        self.docx = QCheckBox("Word (DOCX)")
        self.pdf = QCheckBox("PDF")
        self.txt = QCheckBox("Plain text (TXT)")
        self.docx.setChecked(True)
        self.pdf.setChecked(True)
        for c in (self.docx, self.pdf, self.txt):
            fmts.addWidget(c)
        fmts.addStretch(1)
        form.addRow("Formats:", fmts)
        self.name = QLineEdit(default_name)
        self.name.setAccessibleName("File name")
        form.addRow("File name:", self.name)
        frow = QHBoxLayout()
        folder = ctx.settings.get("export.default_folder") or ctx.config.last_export_folder or str(ctx.ws.exports_dir)
        self.folder = QLineEdit(folder)
        self.folder.setAccessibleName("Destination folder")
        b = QToolButton()
        b.setText("Browse…")
        b.clicked.connect(self._browse)
        frow.addWidget(self.folder, 1)
        frow.addWidget(b)
        form.addRow("Folder:", frow)
        self.engine = QComboBox()
        for v, t in (("auto", "Automatic (LibreOffice if installed, otherwise built-in)"),
                     ("libreoffice", "LibreOffice (closest to Word layout)"), ("builtin", "Built-in PDF engine")):
            self.engine.addItem(t, v)
        self.engine.setCurrentIndex(max(self.engine.findData(ctx.pdf_engine), 0))
        form.addRow("PDF engine:", self.engine)
        self.fit = QCheckBox("Fit to the page limit (adjust spacing, then trim the least relevant items)")
        self.fit.setChecked(True)
        form.addRow("", self.fit)
        self.label = QLineEdit()
        self.label.setPlaceholderText("Optional label for this version, e.g. 'Sent to DRDO 24 Oct'")
        form.addRow("Version label:", self.label)
        lay.addLayout(form)
        lay.addWidget(muted("Existing files are never overwritten; a new name is used instead. The export is "
                            "reported as successful only after the files pass validation."))
        bb = QDialogButtonBox()
        ok = bb.addButton("Export", QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setProperty("kind", "primary")
        bb.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Export folder", self.folder.text())
        if d:
            self.folder.setText(d)

    def options(self):
        from ris.rendering.export import ExportOptions

        fmts = tuple(f for f, c in (("docx", self.docx), ("pdf", self.pdf), ("txt", self.txt)) if c.isChecked())
        return ExportOptions(formats=fmts, folder=Path(self.folder.text()).expanduser(),
                             filename=self.name.text().strip() or None, pdf_engine=self.engine.currentData(),
                             fit_to_pages=self.fit.isChecked(), label=self.label.text().strip())


class StudioPage(Page):
    key = "studio"

    def __init__(self, ctx) -> None:
        super().__init__(ctx, "Resume Studio", PAGE_SUBTITLES["studio"], scrollable=False)
        top = QHBoxLayout()
        top.addWidget(QLabel("Resume variant:"))
        self.variant_combo = QComboBox()
        self.variant_combo.setMinimumWidth(320)
        self.variant_combo.setAccessibleName("Resume variant")
        self.variant_combo.currentIndexChanged.connect(self._variant_selected)
        top.addWidget(self.variant_combo, 1)
        top.addWidget(button("New", on_click=self.new_variant, tooltip="Create a new resume variant"))
        more = QToolButton()
        more.setText("More ▾")
        more.setAccessibleName("More variant actions")
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        m = QMenu(more)
        m.addAction("Duplicate", self.duplicate_variant)
        m.addAction("Rename…", self.rename_variant)
        m.addAction("Save a version now", self.save_version)
        m.addSeparator()
        m.addAction("Delete variant…", self.delete_variant)
        more.setMenu(m)
        top.addWidget(more)
        tw = QWidget()
        tw.setLayout(top)
        self.body.addWidget(tw)
        self.empty = banner("Create a resume variant to start. A variant remembers the mode, template, target, "
                            "vacancy and your choices; the content always comes from your profile.", "info")
        self.body.addWidget(self.empty)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._build_settings())
        split.addWidget(self._build_right())
        split.setSizes([390, 820])
        split.setStretchFactor(1, 1)
        self.split = split
        self.body.addWidget(split, 1)
        bar = QHBoxLayout()
        self.status = muted("")
        bar.addWidget(self.status, 1)
        self.b_export = button("Export…", "primary", on_click=self.export, shortcut="Ctrl+E",
                               tooltip="Export DOCX/PDF after review and validation")
        bar.addWidget(self.b_export)
        bw = QWidget()
        bw.setLayout(bar)
        self.body.addWidget(bw)
        self.variant_id: str | None = None
        self._loaded_rev = -1
        self._loading = False
        self._gen = 0
        self._last = None
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(450)
        self._save_timer.timeout.connect(self._save_settings)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(500)
        self._preview_timer.timeout.connect(self.update_preview)
        ctx.workspace_closing.connect(self._on_workspace_closing)

    def _on_workspace_closing(self) -> None:
        self._flush_save()
        self._preview_timer.stop()
        self._gen += 1  # discard any preview still rendering
        self.variant_id = None
        self._loaded_rev = -1

    # ------------------------------------------------------------------ layout
    def _build_settings(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 8, 0)
        purpose = Card("Purpose")
        f = QFormLayout()
        self.mode = QComboBox()
        for k, mo in MODES.items():
            self.mode.addItem(mo.name, k)
            self.mode.setItemData(self.mode.count() - 1, mo.description, Qt.ItemDataRole.ToolTipRole)
        self.template = QComboBox()
        self.target = QComboBox()
        self.vacancy = QComboBox()
        self.length = QComboBox()
        for v, t in choices(ResumeLength):
            self.length.addItem(t, v)
        self.max_pages = QSpinBox()
        self.max_pages.setRange(0, 20)
        self.max_pages.setSpecialValueText("Use length")
        self.page_size = QComboBox()
        self.page_size.addItem("A4", "A4")
        self.page_size.addItem("US Letter", "Letter")
        for lbl, wdg in (("Mode", self.mode), ("Template", self.template), ("Career target", self.target),
                         ("Vacancy", self.vacancy), ("Length", self.length), ("Page limit", self.max_pages),
                         ("Page size", self.page_size)):
            wdg.setAccessibleName(lbl)
            f.addRow(lbl + ":", wdg)
        purpose.body.addLayout(f)
        self.mode_note = muted("")
        purpose.add(self.mode_note)
        lay.addWidget(purpose)
        content = Card("Content")
        cf = QFormLayout()
        self.summary = QComboBox()
        self.summary.setAccessibleName("Summary")
        cf.addRow("Summary:", self.summary)
        self.pubs = QComboBox()
        for v, t in (("relevant", "Relevant to the target"), ("all", "All publications"), ("none", "Do not include")):
            self.pubs.addItem(t, v)
        self.pubs.setAccessibleName("Publications")
        cf.addRow("Publications:", self.pubs)
        content.body.addLayout(cf)
        content.add(QLabel("Sections (drag to reorder, untick to hide):"))
        self.sections = QListWidget()
        self.sections.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.sections.setMinimumHeight(200)
        self.sections.setAccessibleName("Sections")
        self.sections.model().rowsMoved.connect(lambda *_a: self._changed())
        self.sections.itemChanged.connect(lambda _i: self._changed())
        content.add(self.sections)
        srow = QHBoxLayout()
        up = QToolButton()
        up.setText("↑")
        up.setAccessibleName("Move section up")
        up.clicked.connect(lambda: self._move_section(-1))
        down = QToolButton()
        down.setText("↓")
        down.setAccessibleName("Move section down")
        down.clicked.connect(lambda: self._move_section(1))
        srow.addWidget(up)
        srow.addWidget(down)
        self.b_add_section = QToolButton()
        self.b_add_section.setText("Add section ▾")
        self.b_add_section.setAccessibleName("Add a section to this resume")
        self.b_add_section.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.b_add_section.setMenu(QMenu(self.b_add_section))
        self.b_add_section.menu().aboutToShow.connect(self._fill_add_section_menu)
        srow.addWidget(self.b_add_section)
        srow.addStretch(1)
        srow.addWidget(button("Reset to mode order", on_click=self._reset_sections))
        content.body.addLayout(srow)
        content.add(QLabel("Contact details shown:"))
        self.contacts: dict[str, QCheckBox] = {}
        grid = QWidget()
        gl = QFormLayout(grid)
        gl.setContentsMargins(0, 0, 0, 0)
        row = None
        for i, (k, t) in enumerate(CONTACT_KEYS):
            cb = QCheckBox(t)
            cb.toggled.connect(lambda _c: self._changed())
            self.contacts[k] = cb
            if i % 2 == 0:
                row = QHBoxLayout()
                row.addWidget(cb)
            else:
                row.addWidget(cb)
                gl.addRow(row)
        content.add(grid)
        self.planned = QCheckBox("Show planned qualifications (clearly marked as planned)")
        self.redacted = QCheckBox("Redacted version (public items only)")
        self.declaration = QCheckBox("Include declaration (bio-data)")
        for c in (self.planned, self.redacted, self.declaration):
            c.toggled.connect(lambda _c: self._changed())
            content.add(c)
        self.particulars_box = QWidget()
        pl = QVBoxLayout(self.particulars_box)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(QLabel("Official particulars to include (bio-data only):"))
        self.particulars: dict[str, QCheckBox] = {}
        self.proforma_only: set[str] = {k for k, _ in PROFORMA_PARTICULARS}
        for k, t in PARTICULARS + PROFORMA_PARTICULARS:
            cb = QCheckBox(t)
            cb.toggled.connect(lambda _c: self._changed())
            self.particulars[k] = cb
            pl.addWidget(cb)
        self.proforma_note = muted("Unticked items are left blank on the form, for you to fill in by hand. Enter the "
                                   "values under Master Profile → Personal details.")
        pl.addWidget(self.proforma_note)
        self.employer_cert = QCheckBox("Include the employer's certificate (for your office to complete)")
        self.employer_cert.toggled.connect(lambda _c: self._changed())
        pl.addWidget(self.employer_cert)
        self.b_proforma = button("Proforma answers (items 5, 6 and 17)…", on_click=self.edit_proforma_answers,
                                 tooltip="Your own statements for the deputation proforma")
        pl.addWidget(self.b_proforma)
        content.add(self.particulars_box)
        content.add(button("Choose records…", on_click=self.choose_records,
                           tooltip="Include or leave out individual records for this resume"))
        self.excluded_note = muted("")
        content.add(self.excluded_note)
        lay.addWidget(content)
        look = Card("Appearance")
        lf = QFormLayout()
        self.font_scale = QDoubleSpinBox()
        self.font_scale.setRange(0.85, 1.15)
        self.font_scale.setSingleStep(0.01)
        self.font_scale.setDecimals(2)
        self.spacing = QComboBox()
        for v, t in (("compact", "Compact"), ("normal", "Normal"), ("relaxed", "Relaxed")):
            self.spacing.addItem(t, v)
        self.accent = QLineEdit()
        self.accent.setPlaceholderText("Template colour")
        self.photo = QCheckBox("Show photograph (only templates that allow one)")
        for lbl, wdg in (("Type size", self.font_scale), ("Spacing", self.spacing), ("Accent colour", self.accent)):
            wdg.setAccessibleName(lbl)
            lf.addRow(lbl + ":", wdg)
        look.body.addLayout(lf)
        look.add(self.photo)
        lay.addWidget(look)
        charts = Card("Charts (graphical templates)")
        self.charts_note = muted("")
        charts.add(self.charts_note)
        chf = QFormLayout()
        self.chart_combos: dict[str, QComboBox] = {}
        for key, chart_info in CHARTS.items():
            cb = QComboBox()
            cb.addItem("Template default", "")
            for style, text in chart_info.styles:
                cb.addItem(text, style)
            cb.setToolTip(chart_info.help)
            cb.setAccessibleName(f"Chart: {chart_info.label}")
            cb.currentIndexChanged.connect(lambda _i: self._changed())
            self.chart_combos[key] = cb
            chf.addRow(chart_info.label + ":", cb)
        charts.body.addLayout(chf)
        lay.addWidget(charts)
        self.charts_card = charts
        lay.addStretch(1)
        for wdg in (self.mode, self.template, self.target, self.vacancy, self.length, self.page_size, self.summary,
                    self.pubs, self.spacing):
            wdg.currentIndexChanged.connect(lambda _i: self._changed())
        self.template.currentIndexChanged.connect(lambda _i: self._update_charts_ui())
        self.max_pages.valueChanged.connect(lambda _v: self._changed())
        self.font_scale.valueChanged.connect(lambda _v: self._changed())
        self.accent.editingFinished.connect(self._changed)
        self.photo.toggled.connect(lambda _c: self._changed())
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.settings_panel = scroll(w)
        self.settings_panel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.settings_panel.setMinimumWidth(340)
        return self.settings_panel

    def _build_right(self) -> QWidget:
        self.tabs = QTabWidget()
        pv = QWidget()
        pl = QVBoxLayout(pv)
        prow = QHBoxLayout()
        self.preview_engine = QComboBox()
        self.preview_engine.addItem("Preview with built-in engine (fast)", "builtin")
        self.preview_engine.addItem("Preview with export engine (exact, slower)", "export")
        self.preview_engine.setAccessibleName("Preview engine")
        self.preview_engine.currentIndexChanged.connect(lambda _i: self.schedule_preview())
        prow.addWidget(self.preview_engine)
        prow.addWidget(button("Refresh preview", on_click=self.update_preview, shortcut="F5"))
        prow.addStretch(1)
        pl.addLayout(prow)
        self.preview_note = banner("", "info")
        self.preview_note.setVisible(False)
        pl.addWidget(self.preview_note)
        self.preview = PdfPreview()
        pl.addWidget(self.preview, 1)
        self.tabs.addTab(pv, "Preview")
        ct = QWidget()
        cl = QVBoxLayout(ct)
        cl.addWidget(muted("Every line comes from a confirmed record. Select a statement to tailor its wording for "
                           "this resume only — your profile stays unchanged and each change needs your approval."))
        self.content_tree = QTreeWidget()
        self.content_tree.setHeaderLabels(["Content", "Source"])
        self.content_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.content_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.content_tree.setAccessibleName("Resume content")
        self.content_tree.itemDoubleClicked.connect(lambda it, _c: self._open_source(it))
        cl.addWidget(self.content_tree, 1)
        crow = QHBoxLayout()
        crow.addWidget(button("Tailor wording for this resume…", on_click=self.tailor_selected))
        crow.addWidget(button("Remove tailored wording", on_click=self.remove_claim))
        crow.addWidget(button("Leave this item out", on_click=self.exclude_selected))
        crow.addWidget(button("Open source record", on_click=lambda: self._open_source(self.content_tree.currentItem())))
        crow.addStretch(1)
        cl.addLayout(crow)
        self.tabs.addTab(ct, "Content && claims")
        self.checks = QTextBrowser()
        self.checks.setAccessibleName("Checks")
        self.tabs.addTab(self.checks, "Checks")
        return self.tabs

    # ------------------------------------------------------------------ data loading
    def kinds_of_interest(self) -> set[str] | None:
        return None

    def refresh(self) -> None:
        self._reload_variants()
        self._reload_refs()
        rec = self.ctx.repo.find(self.variant_id) if self.variant_id else None
        if rec is not None and rec.revision != self._loaded_rev:
            self._load_settings(rec)
        self.schedule_preview()

    def _reload_variants(self) -> None:
        self.variant_combo.blockSignals(True)
        self.variant_combo.clear()
        variants = self.ctx.snapshot().of(RecordKind.VARIANT)
        for v in variants:
            self.variant_combo.addItem(v.data.name or "(unnamed variant)", v.id)
        if self.variant_id and self.variant_combo.findData(self.variant_id) >= 0:
            self.variant_combo.setCurrentIndex(self.variant_combo.findData(self.variant_id))
        elif variants:
            self.variant_id = variants[0].id
            self.variant_combo.setCurrentIndex(0)
            self._loaded_rev = -1
        else:
            self.variant_id = None
        self.variant_combo.blockSignals(False)
        has = self.variant_id is not None
        self.split.setVisible(has)
        self.empty.setVisible(not has)
        self.b_export.setEnabled(has)

    def _fill_combo(self, cb: QComboBox, items: list[tuple[str, str]], keep: str) -> None:
        cb.blockSignals(True)
        cb.clear()
        for v, t in items:
            cb.addItem(t, v)
        idx = cb.findData(keep)
        cb.setCurrentIndex(max(idx, 0))
        cb.blockSignals(False)

    def _reload_refs(self) -> None:
        snap = self.ctx.snapshot()
        self._fill_combo(self.template, [(t.id, t.name + (" · ATS-safe" if t.ats_safe else "")
                                          + ("" if t.builtin else " (custom)")) for t in self.ctx.templates.list()],
                         self.template.currentData() or "")
        self._fill_combo(self.target, [("", "(none)")] + [(r.id, r.data.name or "(unnamed)")
                                                           for r in snap.of(RecordKind.CAREER_TARGET)],
                         self.target.currentData() or "")
        self._fill_combo(self.vacancy, [("", "(none)")] + [(r.id, r.data.title or "(untitled vacancy)")
                                                            for r in snap.of(RecordKind.VACANCY)],
                         self.vacancy.currentData() or "")
        self._fill_combo(self.summary, [("", "(best match automatically)")] + [
            (r.id, (r.data.title or label(r.data.focus, SummaryFocus) or "Summary")
             + ("" if not eligibility_reason(snap, r) else f" — {eligibility_reason(snap, r).lower()}"))
            for r in snap.of(RecordKind.SUMMARY)], self.summary.currentData() or "")

    def _variant_selected(self, _i: int) -> None:
        rid = self.variant_combo.currentData()
        if rid == self.variant_id:
            return
        self._flush_save()
        self.variant_id = rid
        self._loaded_rev = -1
        rec = self.ctx.repo.find(rid) if rid else None
        if rec is not None:
            self._load_settings(rec)
        self.schedule_preview()

    def focus_record(self, record_id: str) -> bool:
        rec = self.ctx.repo.find(record_id)
        if rec is None or rec.kind != RecordKind.VARIANT:
            return False
        self._flush_save()
        self.variant_id = record_id
        self._loaded_rev = -1
        self.refresh()
        return True

    def _load_settings(self, rec) -> None:
        self._loading = True
        try:
            d: Variant = rec.data
            self._loaded_rev = rec.revision
            self._reload_refs()
            for cb, val in ((self.mode, d.mode), (self.template, d.template_id), (self.target, d.target_id),
                            (self.vacancy, d.vacancy_id), (self.length, d.length), (self.page_size, d.page_size),
                            (self.summary, d.summary_id), (self.pubs, d.publication_scope), (self.spacing, d.spacing)):
                idx = cb.findData(val or "")
                cb.setCurrentIndex(max(idx, 0))
            self.max_pages.setValue(d.max_pages or 0)
            self.font_scale.setValue(d.font_scale or 1.0)
            self.accent.setText(d.accent_color or "")
            self.photo.setChecked(d.show_photo)
            self.planned.setChecked(d.include_planned_education)
            self.redacted.setChecked(d.redacted)
            self.declaration.setChecked(d.include_declaration)
            mode = get_mode(d.mode)
            visible = list(d.contact_fields) or list(mode.contact_fields)
            for k, cb in self.contacts.items():
                cb.setChecked(k in visible)
            for k, cb in self.particulars.items():
                cb.setChecked(k in d.official_particulars)
            self.employer_cert.setChecked(d.include_employer_certificate)
            self._proforma_answers = dict(d.proforma)
            for k, cb in self.chart_combos.items():
                cb.setCurrentIndex(max(cb.findData(d.charts.get(k, "")), 0))
            self._update_charts_ui()
            self._fill_sections(d)
            self._update_mode_ui(mode)
            self.excluded_note.setText(f"{len(d.exclude_ids)} record(s) left out of this resume."
                                       if d.exclude_ids else "")
        finally:
            self._loading = False

    def _fill_sections(self, d: Variant) -> None:
        from ris.composition.ordering import resolve_order

        mode = get_mode(d.mode)
        snap = self.ctx.snapshot()
        custom = [f"custom:{s.id}" for s in snap.of(RecordKind.CUSTOM_SECTION)]
        order = resolve_order(mode, user_order=list(d.section_order), hidden=[], custom_keys=custom)
        hidden = set(d.hidden_sections)
        for s in snap.of(RecordKind.CUSTOM_SECTION):
            if not s.data.include_by_default and f"custom:{s.id}" not in d.section_order:
                hidden.add(f"custom:{s.id}")
        self.sections.blockSignals(True)
        self.sections.clear()
        names = {f"custom:{s.id}": s.data.name or "Custom section" for s in snap.of(RecordKind.CUSTOM_SECTION)}
        for k in order:
            it = QListWidgetItem(names.get(k) or mode.title_for(k) or SECTION_TITLES.get(k, k))
            it.setData(Qt.ItemDataRole.UserRole, k)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
            it.setCheckState(Qt.CheckState.Unchecked if k in hidden else Qt.CheckState.Checked)
            self.sections.addItem(it)
        self.sections.blockSignals(False)

    def _fill_add_section_menu(self) -> None:
        from ris.composition.modes import ALL_SECTION_KEYS

        menu = self.b_add_section.menu()
        menu.clear()
        present = {self.sections.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.sections.count())}
        mode = get_mode(self.mode.currentData())
        excluded = {"particulars", "declaration", "requirements_matrix"}
        if not mode.proforma:
            excluded |= set(PROFORMA_SECTIONS)
        missing = [k for k in ALL_SECTION_KEYS if k not in present and k not in excluded]
        if not missing:
            menu.addAction("All sections are already listed").setEnabled(False)
        for k in missing:
            menu.addAction(mode.title_for(k), lambda k=k: self.add_section(k))

    def add_section(self, key: str) -> None:
        mode = get_mode(self.mode.currentData())
        it = QListWidgetItem(mode.title_for(key))
        it.setData(Qt.ItemDataRole.UserRole, key)
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
        it.setCheckState(Qt.CheckState.Checked)
        self.sections.addItem(it)
        self.sections.setCurrentItem(it)
        self._changed()

    def _update_mode_ui(self, mode) -> None:
        self.particulars_box.setVisible(mode.government)
        self.declaration.setVisible(mode.government)
        self.mode_note.setText(mode.description)
        for k in self.proforma_only:
            self.particulars[k].setVisible(mode.proforma)
        for w in (self.proforma_note, self.employer_cert, self.b_proforma):
            w.setVisible(mode.proforma)

    def _update_charts_ui(self) -> None:
        spec = self.ctx.templates.find(self.template.currentData() or "")
        on = bool(spec and spec.graphics.enabled and spec.tables_allowed)
        for key, cb in self.chart_combos.items():
            cb.setEnabled(on)
            default = spec.graphics.chart_styles.get(key, CHARTS[key].default) if spec else CHARTS[key].default
            cb.setItemText(0, f"Template default ({CHARTS[key].style_label(default)})")
        self.charts_note.setText(
            "Switch each chart off or choose how it is drawn. Every chart's facts also appear as text." if on else
            "This template has no charts. Choose a graphical template (Senior Scientist Graphical, Graphical Career "
            "Profile, Research Showcase or Infographic Timeline) to use them.")

    def edit_proforma_answers(self, values: dict | None = None) -> dict | None:
        """Dialog for the candidate's own statements in the proforma (item 5 equivalence, item 6, item 17)."""
        current = dict(getattr(self, "_proforma_answers", {}))
        if values is None:
            from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit

            dlg = QDialog(self)
            dlg.setWindowTitle("Proforma answers")
            form = QFormLayout(dlg)
            eq = QLineEdit(current.get("equivalence_authority", ""))
            eq.setPlaceholderText("Only if a qualification was treated as equivalent")
            stmt = QPlainTextEdit(current.get("meets_requirements", ""))
            stmt.setPlaceholderText("Your own statement, e.g. 'Yes. Essential qualification: …; experience: …'")
            stmt.setMaximumHeight(110)
            basis = QComboBox()
            basis.setEditable(True)
            basis.addItems(BASIS_CHOICES)
            basis.setCurrentText(current.get("application_basis", ""))
            form.addRow(muted("These are your own statements; the application never answers them for you."))
            form.addRow("Item 5 — authority for equivalence:", eq)
            form.addRow("Item 6 — do you meet the essential qualifications and experience?", stmt)
            form.addRow("Item 17 — basis of application:", basis)
            bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            bb.accepted.connect(dlg.accept)
            bb.rejected.connect(dlg.reject)
            form.addRow(bb)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return None
            values = {"equivalence_authority": eq.text(), "meets_requirements": stmt.toPlainText(),
                      "application_basis": basis.currentText()}
        self._proforma_answers = {k: str(v).strip() for k, v in values.items() if str(v).strip()}
        self._changed()
        return self._proforma_answers

    def _mode_changed(self) -> None:
        if self._loading:
            return
        mode = get_mode(self.mode.currentData())
        self._update_mode_ui(mode)
        # Adopt mode defaults for template, length, contacts and section order.
        self._loading = True
        self.template.setCurrentIndex(max(self.template.findData(mode.default_template), 0))
        self.length.setCurrentIndex(max(self.length.findData(mode.default_length.value
                                                             if hasattr(mode.default_length, "value")
                                                             else mode.default_length), 0))
        for k, cb in self.contacts.items():
            cb.setChecked(k in mode.contact_fields)
        self._loading = False
        rec = self.ctx.repo.find(self.variant_id)
        if rec is not None:
            d = rec.data.model_copy(update={"mode": mode.id, "section_order": [], "hidden_sections": []})
            self._fill_sections(d)
        self._changed()

    def _move_section(self, delta: int) -> None:
        r = self.sections.currentRow()
        j = r + delta
        if r < 0 or j < 0 or j >= self.sections.count():
            return
        it = self.sections.takeItem(r)
        self.sections.insertItem(j, it)
        self.sections.setCurrentRow(j)
        self._changed()

    def _reset_sections(self) -> None:
        rec = self.ctx.repo.find(self.variant_id) if self.variant_id else None
        if rec is None:
            return
        d = rec.data.model_copy(update={"section_order": [], "hidden_sections": [], "mode": self.mode.currentData()})
        self._fill_sections(d)
        self._user_reset_order = True
        self._changed()

    # ------------------------------------------------------------------ saving settings
    def _changed(self) -> None:
        if self._loading or self.variant_id is None:
            return
        self._save_timer.start()
        self.status.setText("Unsaved changes…")

    def _collect(self, rec) -> dict:
        data = rec.payload()
        order = [self.sections.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.sections.count())]
        hidden = [self.sections.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.sections.count())
                  if self.sections.item(i).checkState() == Qt.CheckState.Unchecked]
        mode = get_mode(self.mode.currentData())
        reset = getattr(self, "_user_reset_order", False)
        self._user_reset_order = False
        default_order = [k for k in order if k in mode.section_order]
        user_order = [] if (reset or order == list(mode.section_order) or
                            (default_order == list(mode.section_order) and len(order) == len(default_order))) else order
        contacts = [k for k, cb in self.contacts.items() if cb.isChecked()]
        data.update({
            "mode": mode.id, "template_id": self.template.currentData() or mode.default_template,
            "target_id": self.target.currentData() or "", "vacancy_id": self.vacancy.currentData() or "",
            "length": self.length.currentData(), "max_pages": self.max_pages.value() or None,
            "page_size": self.page_size.currentData(), "summary_id": self.summary.currentData() or "",
            "publication_scope": self.pubs.currentData(), "section_order": user_order, "hidden_sections": hidden,
            "contact_fields": [] if contacts == list(mode.contact_fields) else contacts,
            "include_planned_education": self.planned.isChecked(), "redacted": self.redacted.isChecked(),
            "include_declaration": self.declaration.isChecked(),
            "official_particulars": [k for k, cb in self.particulars.items() if cb.isChecked()
                                     and (mode.proforma or k not in self.proforma_only)] if mode.government else [],
            "include_employer_certificate": self.employer_cert.isChecked(),
            "proforma": dict(getattr(self, "_proforma_answers", {})),
            "charts": {k: cb.currentData() for k, cb in self.chart_combos.items() if cb.currentData()},
            "font_scale": round(self.font_scale.value(), 2), "spacing": self.spacing.currentData(),
            "accent_color": self.accent.text().strip(), "show_photo": self.photo.isChecked(),
        })
        return data

    def _save_settings(self) -> None:
        if not self.ctx.has_workspace:
            return
        rec = self.ctx.repo.find(self.variant_id) if self.variant_id else None
        if rec is None:
            return
        try:
            new = self.ctx.repo.update(rec.id, self._collect(rec))
        except RISError as exc:
            self.status.setText("Could not save: " + exc.user_message)
            return
        self._loaded_rev = new.revision
        self.status.setText("Settings saved.")
        self.ctx.invalidate()
        self.schedule_preview()

    def _flush_save(self) -> None:
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_settings()

    # ------------------------------------------------------------------ preview
    def schedule_preview(self) -> None:
        if self.variant_id is not None and self.isVisible() and self.ctx.has_workspace:
            self._preview_timer.start()

    def update_preview(self, synchronous: bool = False) -> None:
        if not self.ctx.has_workspace:
            return
        self._flush_save()
        if self.variant_id is None:
            return
        rec = self.ctx.repo.find(self.variant_id)
        if rec is None:
            return
        self._gen += 1
        gen = self._gen
        svc = self.ctx.export_service()
        snap = self.ctx.snapshot()
        engine = "builtin" if self.preview_engine.currentData() == "builtin" else self.ctx.pdf_engine
        self.preview.info.setText("Rendering preview…")

        def work():
            from ris.intelligence.ats import check_quality

            comp = svc.compose(rec.data, snap, variant_id=rec.id)
            doc, spec = comp.doc, comp.spec
            review = svc.review(doc, snap)
            target = doc.max_pages or {"one_page": 1, "two_pages": 2}.get(doc.length)
            if target:
                doc, _ = svc.fit(doc, spec, target)
            data, pages, used, warnings = svc.preview_pdf(doc, spec, engine=engine)
            quality = check_quality(doc, spec, comp.analysis.relevance if comp.analysis else None, pages)
            return gen, doc, spec, review, data, pages, used, warnings, quality, target

        run_task(work, self._preview_ready, self._preview_failed, synchronous=synchronous)

    def _preview_ready(self, result) -> None:
        gen, doc, spec, review, data, pages, used, warnings, quality, target = result
        if gen != self._gen:
            return  # a newer preview is on its way
        self._last = result
        eng = {"builtin": "built-in engine", "libreoffice": "LibreOffice"}.get(used, used)
        over = f" — exceeds the {target}-page limit" if target and pages > target else ""
        self.preview.set_pdf(data, f"{spec.name} · {pages} page(s){over} · rendered with {eng}")
        notes = list(warnings)
        if self.preview_engine.currentData() == "builtin" and self.ctx.pdf_engine != "builtin":
            notes.append("The exported PDF may paginate slightly differently when LibreOffice is used.")
        if review.blocking:
            notes.append(f"{len(review.blocking)} item(s) need your review before export (see Checks).")
        set_banner(self.preview_note, " ".join(notes), "warn" if review.blocking else "info")
        self.preview_note.setVisible(bool(notes))
        self._fill_content(doc)
        self._fill_checks(doc, review, quality)
        self.status.setText(f"{pages} page(s) · {sum(len(s.entries) for s in doc.sections)} entries · "
                            f"{len(doc.trimmed)} fit adjustment(s)")

    def _preview_failed(self, msg: str, detail: str) -> None:
        self.preview.clear("Preview failed: " + msg)
        log.warning("Preview failed")

    def _fill_content(self, doc) -> None:
        self.content_tree.clear()
        snap = self.ctx.snapshot()
        for s in doc.sections:
            si = QTreeWidgetItem([s.title, ""])
            si.setData(0, Qt.ItemDataRole.UserRole, ("section", s.key, ""))
            self.content_tree.addTopLevelItem(si)
            for p in s.paragraphs:
                si.addChild(QTreeWidgetItem([p[:160] + ("…" if len(p) > 160 else ""), ""]))
            for g in s.skill_groups:
                si.addChild(QTreeWidgetItem([f"{g.label}: {', '.join(g.items)}" if g.label else ", ".join(g.items), ""]))
            for it in s.items:
                si.addChild(QTreeWidgetItem([it, ""]))

            def add_entry(e, parent):
                rid = e.source_ids[0] if e.source_ids else ""
                ei = QTreeWidgetItem([" · ".join(x for x in (e.title, e.subtitle, e.date_text) if x) or e.citation_rest,
                                      label(RecordKind(e.kind)) if e.kind in RecordKind._value2member_map_ else ""])
                ei.setData(0, Qt.ItemDataRole.UserRole, ("entry", rid, ""))
                parent.addChild(ei)
                for b in e.bullets:
                    bid = next((x for x in b.source_ids if snap.get(x) and snap.get(x).kind == RecordKind.BULLET), "")
                    bi = QTreeWidgetItem(["• " + b.text, "Tailored wording (approved)" if b.claim_id else
                                          ("Profile statement" if bid else "From record")])
                    bi.setData(0, Qt.ItemDataRole.UserRole, ("bullet", bid or (b.source_ids[0] if b.source_ids else ""),
                                                             b.claim_id))
                    bi.setToolTip(0, b.text)
                    ei.addChild(bi)
                for c in e.children:
                    add_entry(c, ei)

            for e in s.entries:
                add_entry(e, si)
            if s.table is not None:
                for row in s.table.rows:
                    si.addChild(QTreeWidgetItem([" — ".join(row)[:200], ""]))
        self.content_tree.expandToDepth(1)

    def _fill_checks(self, doc, review, quality) -> None:
        html = []
        if review.items:
            html.append("<h3>Before export</h3><ul>")
            for i in review.items:
                html.append(f"<li>{'⛔' if i.blocking else '⚠'} <b>{esc(i.title)}</b>: {esc(i.detail)}</li>")
            html.append("</ul>")
        else:
            html.append("<h3>Before export</h3><p>✔ Every included fact is confirmed and cleared for disclosure; no "
                        "identifiers were detected.</p>")
        if doc.warnings:
            html.append("<h3>Composition notes</h3><ul>" + "".join(f"<li>{esc(w)}</li>" for w in doc.warnings) + "</ul>")
        html.append(report_html(None, quality, doc.trimmed))
        self.checks.setHtml("".join(html))

    # ------------------------------------------------------------------ claims (variant-specific wording)
    def _selected_bullet(self):
        it = self.content_tree.currentItem()
        if it is None:
            return None, None, ""
        data = it.data(0, Qt.ItemDataRole.UserRole)
        if not data or data[0] != "bullet":
            return None, None, ""
        rec = self.ctx.repo.find(data[1]) if data[1] else None
        return it, rec, data[2]

    def tailor_selected(self) -> None:
        it, rec, _claim = self._selected_bullet()
        if rec is None or rec.kind != RecordKind.BULLET:
            info(self, "Tailor wording", "Select a statement (a line starting with •) that comes from your profile.")
            return
        from ris.intelligence.rewriting import default_glossary, rewrite_bullet

        parent = self.ctx.repo.find(rec.parent_id) if rec.parent_id else None
        glossary = default_glossary()
        glossary.update(self.ctx.settings.get("glossary.overrides") or {})
        translate = confirm(self, "Tailor wording", "Also explain specialist terms for engineering readers "
                                                    "(for example meteorological instrument names)?",
                            ok="Yes, explain terms") if self._has_domain_terms(rec.data.text, glossary) else False
        s = rewrite_bullet(rec, parent, translate=translate, glossary=glossary)
        involvement = rec.data.involvement or (getattr(parent.data, "involvement", None) if parent else None)
        dlg = SuggestionDialog(self, s, involvement=involvement, title="Tailor wording for this resume",
                               generator_note="The approved wording is used in this resume only. Your profile "
                                              "statement is unchanged.")
        if dlg.exec() != 1:
            return
        text = dlg.approved_text()
        if text == rec.data.text.strip():
            return
        self.ctx.repo.create(RecordKind.CLAIM, {
            "target_bullet_id": rec.id, "source_record_ids": s.source_ids or [rec.id], "source_field": "text",
            "original_text": rec.data.text, "generated_text": s.revised, "approved_text": text,
            "material_facts": s.source_facts, "assumptions": s.assumptions, "missing_metrics": s.missing_metrics,
            "flags": dlg.check.flags, "status": "approved", "approved_at": utc_now_iso(),
            "confidentiality": self.ctx.snapshot().effective_confidentiality(rec).value,
            "generator": "rules-engine"}, parent_id=self.variant_id)
        self.ctx.invalidate()
        self.ctx.say("Tailored wording approved for this resume.")
        self.update_preview()

    @staticmethod
    def _has_domain_terms(text: str, glossary: dict[str, str]) -> bool:
        low = text.lower()
        return any(k.lower() in low for k in glossary)

    def remove_claim(self) -> None:
        it, rec, claim_id = self._selected_bullet()
        if not claim_id:
            info(self, "Tailored wording", "The selected line uses your profile wording already.")
            return
        claim = self.ctx.repo.find(claim_id)
        if claim is not None:
            self.ctx.repo.update(claim.id, {**claim.payload(), "status": "rejected"})
            self.ctx.invalidate()
            self.ctx.say("Tailored wording removed; the profile wording is used again.")
            self.update_preview()

    def exclude_selected(self) -> None:
        it = self.content_tree.currentItem()
        data = it.data(0, Qt.ItemDataRole.UserRole) if it else None
        if not data or data[0] not in ("entry", "bullet") or not data[1]:
            info(self, "Leave out", "Select an entry or statement first.")
            return
        rec = self.ctx.repo.get(self.variant_id)
        ex = list(dict.fromkeys(list(rec.data.exclude_ids) + [data[1]]))
        self.ctx.repo.patch(self.variant_id, exclude_ids=ex)
        self.ctx.invalidate()
        self._loaded_rev = -1
        self.refresh()
        self.ctx.say("Left out of this resume. Use 'Choose records…' to include it again.")

    def _open_source(self, it) -> None:
        data = it.data(0, Qt.ItemDataRole.UserRole) if it else None
        if data and data[0] in ("entry", "bullet") and data[1]:
            self.ctx.navigate.emit("record", data[1])

    def choose_records(self) -> None:
        self._flush_save()
        rec = self.ctx.repo.find(self.variant_id) if self.variant_id else None
        if rec is None:
            return
        dlg = RecordPickerDialog(self, self.ctx, rec.data)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            snap = self.ctx.snapshot()
            keep = [x for x in rec.data.exclude_ids if snap.get(x) is not None and eligibility_reason(snap, snap.get(x))]
            self.ctx.repo.patch(rec.id, exclude_ids=sorted(set(keep) | set(dlg.excluded_ids())))
            self.ctx.invalidate()
            self._loaded_rev = -1
            self.refresh()

    # ------------------------------------------------------------------ variants
    def new_variant(self) -> None:
        name = ask_text(self, "New resume variant", "Name (for example 'DRDO Scientist E — avionics'):")
        if not name:
            return
        mode = get_mode("defence_technical")
        rec = self.ctx.repo.create(RecordKind.VARIANT, {"name": name, "mode": mode.id,
                                                        "template_id": mode.default_template,
                                                        "length": mode.default_length.value})
        self.ctx.invalidate()
        self.focus_record(rec.id)

    def duplicate_variant(self) -> None:
        rec = self.ctx.repo.find(self.variant_id) if self.variant_id else None
        if rec is None:
            return
        self._flush_save()
        data = self.ctx.repo.get(rec.id).payload()
        data["name"] = data.get("name", "Variant") + " (copy)"
        data["last_generated_at"] = ""
        new = self.ctx.repo.create(RecordKind.VARIANT, data)
        for c in self.ctx.repo.children(rec.id, RecordKind.CLAIM):
            self.ctx.repo.create(RecordKind.CLAIM, c.payload(), parent_id=new.id)
        self.ctx.invalidate()
        self.focus_record(new.id)

    def rename_variant(self) -> None:
        rec = self.ctx.repo.find(self.variant_id) if self.variant_id else None
        if rec is None:
            return
        name = ask_text(self, "Rename variant", "New name:", rec.data.name)
        if name:
            self.ctx.repo.patch(rec.id, name=name)
            self.ctx.invalidate()
            self._loaded_rev = -1
            self.refresh()

    def delete_variant(self) -> None:
        rec = self.ctx.repo.find(self.variant_id) if self.variant_id else None
        if rec is None:
            return
        if not confirm(self, "Delete variant", f"Move the variant '{rec.data.name}' to Recently deleted?",
                       ok="Delete", destructive=True,
                       detail="Saved versions and exported files are kept. You can restore the variant from Backup & "
                              "Restore → Recently deleted."):
            return
        self.ctx.repo.delete(rec.id)
        self.variant_id = None
        self.ctx.invalidate()
        self.refresh()

    def save_version(self) -> None:
        if self._last is None:
            self.update_preview(synchronous=True)
        if self._last is None:
            return
        _gen, doc, spec, review, *_rest = self._last
        if review.blocking:
            error(self, "Save version", "Resolve the items listed under Checks first: versions contain only "
                                        "confirmed, disclosure-cleared facts.")
            return
        lbl = ask_text(self, "Save version", "Label for this version:", "Saved") or "Saved"
        rec = self.ctx.repo.get(self.variant_id)
        info_ = self.ctx.variants().save_version(rec.id, doc, settings=rec.payload(),
                                                  template_spec=spec.model_dump(mode="json"), label=lbl)
        self.ctx.say(f"Version {info_.title} saved. Compare versions in the Resume Library.")

    # ------------------------------------------------------------------ export
    def export(self) -> None:
        self._flush_save()
        rec = self.ctx.repo.find(self.variant_id) if self.variant_id else None
        if rec is None:
            return
        svc = self.ctx.export_service()
        try:
            doc = svc.compose(rec.data, self.ctx.snapshot(), variant_id=rec.id).doc
            default = svc._default_name(doc, rec)
        except RISError:
            default = rec.data.name
        dlg = ExportDialog(self, self.ctx, default)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        opts = dlg.options()
        if not opts.formats:
            error(self, "Export", "Choose at least one format.")
            return
        self.ctx.config.last_export_folder = str(opts.folder)
        try:
            self.ctx.config.save()
        except OSError:
            pass
        self._run_export(rec.id, opts)

    def _run_export(self, variant_id: str, opts, synchronous: bool = False) -> None:
        svc = self.ctx.export_service()
        self.b_export.setEnabled(False)
        self.ctx.say("Exporting and validating…", 0)
        run_task(lambda: svc.export_variant(variant_id, opts),
                 lambda out: self._export_done(variant_id, opts, out),
                 lambda m, d: (self.b_export.setEnabled(True), self.ctx.say(""),
                               error(self, "Export failed", m, d)), synchronous=synchronous)

    def _export_done(self, variant_id: str, opts, out) -> None:
        self.b_export.setEnabled(True)
        self.ctx.say("")
        if not out.ok and out.report is None and out.review is not None and (
                out.review.blocking or out.review.warnings):
            dlg = ReviewDialog(self, self.ctx, out.review, variant_id=variant_id)
            res = dlg.exec()
            if dlg.changed:
                self.ctx.invalidate()
                self._loaded_rev = -1
                self.refresh()
            if res == QDialog.DialogCode.Accepted:
                opts.acknowledge_warnings = dlg.acknowledged()
                self._run_export(variant_id, opts)
            return
        if not out.ok:
            ReportDialog(self, "Export stopped", report_html(out.report, out.quality, out.document.trimmed
                                                             if out.document else None), out.message, "bad").exec()
            return
        files = "<h3>Files</h3><ul>" + "".join(
            f"<li>{esc(f.path.name)} — {f.size:,} bytes"
            + (f", {f.page_count} page(s)" if f.page_count else "")
            + f"<br><small>SHA-256 {f.sha256}</small></li>" for f in out.files) + "</ul>"
        dlg = ReportDialog(self, "Export complete", files + report_html(out.report, out.quality, out.document.trimmed,
                                                                         out.review),
                           out.message + " Saved as a new version in the Resume Library.",
                           "ok" if not out.report.warnings else "warn")
        open_b = dlg.findChild(QDialogButtonBox).addButton("Open folder", QDialogButtonBox.ButtonRole.ActionRole)
        folder = out.files[0].path.parent if out.files else None
        open_b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))) if folder else None)
        dlg.exec()
        self.ctx.invalidate()
        self.ctx.data_changed.emit({"export"})

    def has_unsaved_changes(self) -> bool:
        return self._save_timer.isActive()

    def maybe_save(self) -> bool:
        self._flush_save()
        return True


_ = (registry, scroll)
