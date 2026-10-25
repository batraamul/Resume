"""Resume Library: variants, immutable versions, comparisons, re-export and templates."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ris.composition.modes import get_mode
from ris.domain.enums import RecordKind
from ris.errors import RISError
from ris.rendering.specs import TemplateSpec
from ris.strings import PAGE_SUBTITLES
from ris.ui.dialogs import HtmlDialog, ReportDialog, report_html
from ris.ui.widgets.common import Page, ask_text, banner, button, confirm, error, esc, info, muted, set_banner
from ris.ui.widgets.pdf_preview import PdfPreview
from ris.ui.workers import run_task


class LibraryPage(Page):
    key = "library"

    def __init__(self, ctx) -> None:
        super().__init__(ctx, "Resume Library", PAGE_SUBTITLES["library"], scrollable=False)
        self.tabs = QTabWidget()
        # variants & versions
        vw = QWidget()
        vl = QHBoxLayout(vw)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        ll.addWidget(QLabel("Variants"))
        self.variants = QListWidget()
        self.variants.setAccessibleName("Resume variants")
        self.variants.currentItemChanged.connect(lambda _c, _p: self._load_versions())
        ll.addWidget(self.variants, 1)
        ll.addWidget(button("Open in Resume Studio", on_click=self._open_studio))
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        self.outdated = banner("", "info")
        rl.addWidget(self.outdated)
        rl.addWidget(muted("Every export saves an immutable version. Versions keep the exact content and layout "
                           "settings, so a version can be re-exported identically later."))
        self.versions = QTableWidget(0, 4)
        self.versions.setHorizontalHeaderLabels(["Version", "Created (UTC)", "Template", "Checksum"])
        self.versions.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.versions.verticalHeader().setVisible(False)
        self.versions.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.versions.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.versions.setAccessibleName("Versions")
        self.versions.itemSelectionChanged.connect(self._preview_version)
        rl.addWidget(self.versions, 1)
        row = QHBoxLayout()
        row.addWidget(button("Compare two selected", on_click=self._compare,
                             tooltip="Select two versions (Ctrl+click) to see what changed"))
        row.addWidget(button("Re-export selected version", on_click=self._reexport))
        row.addWidget(button("Delete version", "danger", on_click=self._delete_version))
        row.addStretch(1)
        rl.addLayout(row)
        self.preview = PdfPreview()
        self.preview.setMinimumHeight(260)
        rl.addWidget(self.preview, 2)
        split.addWidget(right)
        split.setSizes([300, 900])
        vl.addWidget(split)
        self.tabs.addTab(vw, "Variants && versions")
        # templates
        tw = QWidget()
        tl = QHBoxLayout(tw)
        tsplit = QSplitter(Qt.Orientation.Horizontal)
        tleft = QWidget()
        tll = QVBoxLayout(tleft)
        self.templates = QListWidget()
        self.templates.setAccessibleName("Templates")
        self.templates.currentItemChanged.connect(lambda _c, _p: self._show_template())
        tll.addWidget(self.templates, 1)
        trow = QHBoxLayout()
        trow.addWidget(button("Duplicate…", on_click=self._dup_template))
        self.b_edit_t = button("Design…", "primary", on_click=self._edit_template,
                               tooltip="Open the template designer: every setting with a live preview. Built-in "
                                       "templates are saved as your own copy.")
        self.b_del_t = button("Delete", "danger", on_click=self._del_template)
        trow.addWidget(self.b_edit_t)
        trow.addWidget(self.b_del_t)
        tll.addLayout(trow)
        tsplit.addWidget(tleft)
        tright = QWidget()
        trl = QVBoxLayout(tright)
        self.template_info = QTextBrowser()
        self.template_info.setMaximumHeight(170)
        self.template_info.setAccessibleName("Template details")
        trl.addWidget(self.template_info)
        trl.addWidget(button("Preview with the fictional sample", on_click=self._preview_template))
        self.template_preview = PdfPreview()
        trl.addWidget(self.template_preview, 1)
        tsplit.addWidget(tright)
        tsplit.setSizes([300, 900])
        tl.addWidget(tsplit)
        self.tabs.addTab(tw, "Templates")
        self.body.addWidget(self.tabs, 1)

    def kinds_of_interest(self) -> set[str] | None:
        return None

    def refresh(self) -> None:
        cur = self.variants.currentItem().data(Qt.ItemDataRole.UserRole) if self.variants.currentItem() else None
        self.variants.blockSignals(True)
        self.variants.clear()
        for v in self.ctx.snapshot().of(RecordKind.VARIANT):
            n = len(self.ctx.variants().list_versions(v.id))
            it = QListWidgetItem(f"{v.data.name or '(unnamed)'}\n{get_mode(v.data.mode).name} · {n} version(s)")
            it.setData(Qt.ItemDataRole.UserRole, v.id)
            self.variants.addItem(it)
            if v.id == cur:
                self.variants.setCurrentItem(it)
        self.variants.blockSignals(False)
        if self.variants.currentItem() is None and self.variants.count():
            self.variants.setCurrentRow(0)
        else:
            self._load_versions()
        self._load_templates()

    def focus_record(self, record_id: str) -> bool:
        for i in range(self.variants.count()):
            if self.variants.item(i).data(Qt.ItemDataRole.UserRole) == record_id:
                self.tabs.setCurrentIndex(0)
                self.variants.setCurrentRow(i)
                return True
        return False

    def _variant_id(self) -> str | None:
        it = self.variants.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _load_versions(self) -> None:
        vid = self._variant_id()
        self.versions.setRowCount(0)
        self.preview.clear("Select a version to preview it.")
        if vid is None:
            set_banner(self.outdated, "No resume variants yet. Create one in Resume Studio.", "info")
            return
        rec = self.ctx.repo.find(vid)
        rep = self.ctx.variants().variant_outdated(rec)
        set_banner(self.outdated, rep.summary() + (" Changed: " + ", ".join(rep.changed[:5]) if rep.changed else ""),
                   "warn" if rep.outdated else "ok")
        infos = list(reversed(self.ctx.variants().list_versions(vid)))
        self.versions.setRowCount(len(infos))
        for i, v in enumerate(infos):
            a = QTableWidgetItem(v.title)
            a.setData(Qt.ItemDataRole.UserRole, v.id)
            self.versions.setItem(i, 0, a)
            self.versions.setItem(i, 1, QTableWidgetItem(v.created_at[:16].replace("T", " ")))
            self.versions.setItem(i, 2, QTableWidgetItem(f"{v.template_id} {v.template_version}"))
            self.versions.setItem(i, 3, QTableWidgetItem(v.checksum[:16] + "…"))
        if not infos:
            set_banner(self.outdated, "No versions yet — exporting from Resume Studio saves one.", "info")

    def _selected_versions(self) -> list[str]:
        rows = sorted({i.row() for i in self.versions.selectedIndexes()})
        return [self.versions.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in rows]

    def _preview_version(self) -> None:
        sel = self._selected_versions()
        if len(sel) != 1:
            return
        vs = self.ctx.variants()
        try:
            doc, settings = vs.load_document(sel[0])
        except RISError as exc:
            self.preview.clear(exc.user_message)
            return
        spec = TemplateSpec.model_validate(settings["template_spec"])
        svc = self.ctx.export_service()

        def work():
            return svc.preview_pdf(doc, spec, engine="builtin")

        run_task(work, lambda r: self.preview.set_pdf(r[0], f"Saved version · {r[1]} page(s) · built-in preview"),
                 lambda m, _d: self.preview.clear(m))

    def _compare(self) -> None:
        sel = self._selected_versions()
        if len(sel) != 2:
            info(self, "Compare versions", "Select exactly two versions (hold Ctrl or Cmd while clicking).")
            return
        older, newer = sel[1], sel[0]  # table is newest first
        html = self.ctx.variants().compare_html(older, newer)
        HtmlDialog(self, "Compare versions", "<p>Left: older version · Right: newer version. Highlighted lines "
                                             "changed.</p>" + html).exec()

    def _reexport(self) -> None:
        sel = self._selected_versions()
        vid = self._variant_id()
        if len(sel) != 1 or vid is None:
            info(self, "Re-export", "Select one version.")
            return
        from ris.rendering.export import ExportOptions

        opts = ExportOptions(formats=("docx", "pdf"), folder=self.ctx.ws.exports_dir,
                             pdf_engine=self.ctx.pdf_engine, acknowledge_warnings=True)
        svc = self.ctx.export_service()

        def done(out) -> None:
            if out.ok:
                ReportDialog(self, "Re-export complete", "<ul>" + "".join(
                    f"<li>{esc(str(f.path))}</li>" for f in out.files) + "</ul>" + report_html(out.report),
                             out.message, "ok").exec()
            else:
                ReportDialog(self, "Re-export stopped", report_html(out.report) if out.report else
                             "<ul>" + "".join(f"<li>{esc(i.title)}: {esc(i.detail)}</li>"
                                              for i in (out.review.items if out.review else [])) + "</ul>",
                             out.message, "bad").exec()
            self.ctx.data_changed.emit({"export"})

        run_task(lambda: svc.export_variant(vid, opts, version_id=sel[0]), done,
                 lambda m, d: error(self, "Re-export", m, d))

    def _delete_version(self) -> None:
        sel = self._selected_versions()
        if not sel:
            return
        if not confirm(self, "Delete version", f"Permanently delete {len(sel)} saved version(s)?", ok="Delete",
                       destructive=True, detail="Exported files are not affected. This cannot be undone except by "
                                                "restoring a backup."):
            return
        for v in sel:
            self.ctx.variants().delete_version(v)
        self._load_versions()

    def _open_studio(self) -> None:
        vid = self._variant_id()
        if vid:
            self.ctx.navigate.emit("studio", vid)

    # ------------------------------------------------------------------ templates
    def _load_templates(self) -> None:
        cur = self.templates.currentItem().data(Qt.ItemDataRole.UserRole) if self.templates.currentItem() else None
        self.templates.blockSignals(True)
        self.templates.clear()
        for t in self.ctx.templates.list():
            it = QListWidgetItem(t.name + (" · ATS-safe" if t.ats_safe else "") + ("" if t.builtin else " (custom)"))
            it.setData(Qt.ItemDataRole.UserRole, t.id)
            self.templates.addItem(it)
            if t.id == cur:
                self.templates.setCurrentItem(it)
        self.templates.blockSignals(False)
        if self.templates.currentItem() is None and self.templates.count():
            self.templates.setCurrentRow(0)
        self._show_template()

    def _spec(self) -> TemplateSpec | None:
        it = self.templates.currentItem()
        return self.ctx.templates.find(it.data(Qt.ItemDataRole.UserRole)) if it else None

    def _show_template(self) -> None:
        t = self._spec()
        if t is None:
            return
        self.b_edit_t.setEnabled(True)
        self.b_del_t.setEnabled(not t.builtin)
        modes = ", ".join(get_mode(m).name for m in t.recommended_modes)
        self.template_info.setHtml(
            f"<h3>{esc(t.name)} <small>v{esc(t.version)}</small></h3><p>{esc(t.description)}</p>"
            f"<p><b>Layout:</b> header {esc(t.header.style)}, headings {esc(t.heading.style)}, entries "
            f"{esc(t.entry.style)}{', two columns' if t.columns.enabled else ''}. <b>Fonts:</b> {esc(t.fonts.body)} "
            f"{t.fonts.body_size:g} pt. <b>ATS-safe:</b> {'yes — single column, no tables' if t.ats_safe else 'no'}."
            f"</p><p><b>Recommended for:</b> {esc(modes) or '—'}</p>")
        self.template_preview.clear("Choose 'Preview with the fictional sample'.")

    def _preview_template(self) -> None:
        t = self._spec()
        if t is None:
            return
        import tempfile
        from pathlib import Path

        from ris.domain.models import Variant
        from ris.rendering.export import ExportService
        from ris.services.sample import load_sample_profile
        from ris.storage.workspace import Workspace

        lib = self.ctx.templates

        def work():
            with tempfile.TemporaryDirectory(prefix="ris-tpl-") as tmp:
                ws = Workspace(Path(tmp) / "ws", "Template preview", is_sample=True).open()
                try:
                    load_sample_profile(ws)
                    svc = ExportService(ws, lib)
                    base = ws.repo.list(RecordKind.VARIANT)[0]
                    mode = t.recommended_modes[0] if t.recommended_modes else "general_professional"
                    v = Variant.model_validate({**base.payload(), "template_id": t.id, "mode": mode,
                                                "max_pages": None, "length": "two_pages"})
                    comp = svc.compose(v, variant_id=base.id)
                    return svc.preview_pdf(comp.doc, comp.spec, engine="builtin")
                finally:
                    ws.close()

        self.template_preview.info.setText("Rendering…")
        run_task(work, lambda r: self.template_preview.set_pdf(r[0], f"{t.name} · fictional sample · {r[1]} page(s)"),
                 lambda m, _d: self.template_preview.clear(m))

    def _dup_template(self) -> None:
        t = self._spec()
        if t is None:
            return
        name = ask_text(self, "Duplicate template", "Name for your copy:", f"{t.name} (custom)")
        if not name:
            return
        try:
            new = self.ctx.templates.duplicate(t.id, name)
        except RISError as exc:
            error(self, "Duplicate template", exc.user_message)
            return
        self._load_templates()
        for i in range(self.templates.count()):
            if self.templates.item(i).data(Qt.ItemDataRole.UserRole) == new.id:
                self.templates.setCurrentRow(i)
        self.ctx.say("Template duplicated. Edit it, then choose it in Resume Studio.")

    def _edit_template(self, exec_dialog: bool = True):
        from ris.ui.template_designer import TemplateDesignerDialog

        t = self._spec()
        if t is None:
            return None
        dlg = TemplateDesignerDialog(self, self.ctx, t)
        if not exec_dialog:
            return dlg
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_spec is not None:
            self._load_templates()
            for i in range(self.templates.count()):
                if self.templates.item(i).data(Qt.ItemDataRole.UserRole) == dlg.result_spec.id:
                    self.templates.setCurrentRow(i)
            self.ctx.say(f"Template '{dlg.result_spec.name}' saved. Choose it in Resume Studio.")
        return dlg

    def _del_template(self) -> None:
        t = self._spec()
        if t is None or t.builtin:
            return
        used = [v.data.name for v in self.ctx.repo.list(RecordKind.VARIANT) if v.data.template_id == t.id]
        if not confirm(self, "Delete template", f"Delete the custom template '{t.name}'?", ok="Delete",
                       destructive=True, detail=("Used by: " + ", ".join(used) + ". Those variants will need "
                                                 "another template.") if used else ""):
            return
        self.ctx.templates.delete_user_template(t.id)
        self._load_templates()
