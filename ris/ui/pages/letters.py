"""Cover Letters: factual drafts from confirmed facts and the vacancy, with preview and validated export."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ris.domain.enums import RecordKind
from ris.errors import RISError
from ris.strings import PAGE_SUBTITLES
from ris.ui.dialogs import ReportDialog, ReviewDialog, report_html
from ris.ui.widgets.common import Page, button, error, esc, info, muted
from ris.ui.widgets.pdf_preview import PdfPreview
from ris.ui.widgets.records import CollectionWidget
from ris.ui.workers import run_task


class LettersPage(Page):
    key = "letters"

    def __init__(self, ctx) -> None:
        super().__init__(ctx, "Cover Letters", PAGE_SUBTITLES["letters"], scrollable=False)
        self.header.add_action(button("Draft from a vacancy…", "primary", on_click=self.draft))
        self.body.addWidget(muted("Drafts use only confirmed, disclosure-cleared facts and the vacancy details. Edit "
                                  "every paragraph so it reads in your own voice before sending."))
        split = QSplitter(Qt.Orientation.Vertical)
        self.collection = CollectionWidget(ctx, [RecordKind.COVER_LETTER], empty_hint=(
            "No letters yet. Choose 'Draft from a vacancy…' or add a blank letter."))
        split.addWidget(self.collection)
        pw = QWidget()
        pl = QVBoxLayout(pw)
        row = QHBoxLayout()
        row.addWidget(QLabel("Template:"))
        self.template = QComboBox()
        self.template.setAccessibleName("Letter template")
        row.addWidget(self.template)
        row.addWidget(button("Preview selected letter", on_click=self.preview_letter))
        row.addStretch(1)
        row.addWidget(button("Export selected letter…", on_click=self.export_letter))
        pl.addLayout(row)
        self.preview = PdfPreview()
        pl.addWidget(self.preview, 1)
        split.addWidget(pw)
        split.setSizes([480, 360])
        self.body.addWidget(split, 1)

    def kinds_of_interest(self) -> set[str]:
        return {"cover_letter", "vacancy", "application", "personal"}

    def refresh(self) -> None:
        cur = self.template.currentData() or "executive_technical"
        self.template.clear()
        for t in self.ctx.templates.list():
            self.template.addItem(t.name, t.id)
        self.template.setCurrentIndex(max(self.template.findData(cur), 0))
        self.collection.reload()

    def focus_record(self, record_id: str) -> bool:
        return self.collection.focus_record(record_id)

    def has_unsaved_changes(self) -> bool:
        return self.collection.editor.is_dirty()

    def maybe_save(self) -> bool:
        return self.collection.editor.maybe_save()

    def draft(self) -> None:
        from ris.composition.cover_letter import draft_cover_letter
        from ris.intelligence.analysis import analyse

        vacs = self.ctx.repo.list(RecordKind.VACANCY)
        names = ["(no specific vacancy)"] + [v.data.title or "(untitled)" for v in vacs]
        choice, ok = QInputDialog.getItem(self, "Draft cover letter", "Vacancy:", names, 1 if vacs else 0, False)
        if not ok:
            return
        vac = vacs[names.index(choice) - 1] if names.index(choice) > 0 else None
        snap = self.ctx.snapshot()
        analysis = None
        if vac is not None and vac.data.requirements:
            analysis = analyse(snap, vac.data, weights=self.ctx.settings.get("scoring.weights"), today=self.ctx.today)
        style = "formal" if vac is None or vac.data.recruitment_mode != "unknown" else "professional"
        payload = draft_cover_letter(snap, vac.data if vac else None, analysis, style=style, today=self.ctx.today)
        if vac is not None:
            payload["vacancy_id"] = vac.id
        rec = self.ctx.repo.create(RecordKind.COVER_LETTER, payload)
        self.ctx.invalidate()
        self.collection.reload(select_id=rec.id)
        self.ctx.say("Draft created from confirmed facts. Review and personalise it.")

    def _letter(self):
        ed = self.collection.editor
        if ed.record is None or ed.record.kind != RecordKind.COVER_LETTER:
            info(self, "Cover letter", "Select a letter first.")
            return None
        if ed.is_dirty() and not ed.save():
            return None
        return self.ctx.repo.get(ed.record.id)

    def _doc(self, rec):
        from ris.composition.cover_letter import letter_document

        spec = self.ctx.templates.get(self.template.currentData())
        doc = letter_document(rec.data, self.ctx.snapshot(), template_id=spec.id, template_version=spec.version,
                              is_sample=self.ctx.is_sample)
        return doc, spec

    def preview_letter(self) -> None:
        rec = self._letter()
        if rec is None:
            return
        doc, spec = self._doc(rec)
        svc = self.ctx.export_service()
        run_task(lambda: svc.preview_pdf(doc, spec, engine="builtin"),
                 lambda r: self.preview.set_pdf(r[0], f"{spec.name} · {r[1]} page(s)"),
                 lambda m, _d: self.preview.clear(m))

    def export_letter(self, acknowledge: bool = False, folder: str | None = None) -> None:
        rec = self._letter()
        if rec is None:
            return
        if folder is None:
            folder = QFileDialog.getExistingDirectory(self, "Export folder", str(self.ctx.ws.exports_dir))
            if not folder:
                return
        from pathlib import Path

        from ris.rendering.export import ExportOptions

        doc, spec = self._doc(rec)
        svc = self.ctx.export_service()
        opts = ExportOptions(formats=("docx", "pdf"), folder=Path(folder), pdf_engine=self.ctx.pdf_engine,
                             fit_to_pages=False, acknowledge_warnings=acknowledge,
                             filename=f"Cover letter - {rec.data.title or 'letter'}")

        def done(out) -> None:
            if not out.ok and out.report is None and out.review is not None:
                dlg = ReviewDialog(self, self.ctx, out.review)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self.export_letter(acknowledge=dlg.acknowledged(), folder=folder)
                return
            ReportDialog(self, "Cover letter export", "<ul>" + "".join(f"<li>{esc(str(f.path))}</li>"
                                                                       for f in out.files) + "</ul>"
                         + report_html(out.report), out.message, "ok" if out.ok else "bad").exec()
            self.ctx.data_changed.emit({"export"})

        try:
            run_task(lambda: svc.export_document(doc, spec, opts, document_kind="cover_letter", source_id=rec.id),
                     done, lambda m, d: error(self, "Export", m, d))
        except RISError as exc:
            error(self, "Export", exc.user_message)


_ = QTabWidget
