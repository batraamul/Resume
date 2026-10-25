"""Documents & Exports: every exported file with checksum and validation report; redacted portfolio."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ris.strings import PAGE_SUBTITLES
from ris.ui.dialogs import ReportDialog, ReviewDialog
from ris.ui.widgets.common import Page, button, confirm, error, esc, info, muted
from ris.ui.workers import run_task
from ris.util import sha256_file

COLS = ["Created (UTC)", "Document", "Format", "File", "Pages", "Engine", "Validation", "File present"]


class ExportsPage(Page):
    key = "exports"

    def __init__(self, ctx) -> None:
        super().__init__(ctx, "Documents & Exports", PAGE_SUBTITLES["exports"], scrollable=False)
        self.header.add_action(button("Create redacted portfolio…", on_click=self.portfolio,
                                      tooltip="A public-safe portfolio built only from Public / Approved records"))
        self.body.addWidget(muted("Files are listed with the SHA-256 checksum recorded at export, so you can check "
                                  "that a file has not changed. Removing an entry from this list does not delete "
                                  "the file."))
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAccessibleName("Exported files")
        self.table.cellDoubleClicked.connect(lambda r, _c: self.open_file())
        self.body.addWidget(self.table, 1)
        row = QHBoxLayout()
        for text, fn in (("Open file", self.open_file), ("Open folder", self.open_folder),
                         ("Validation report", self.show_report), ("Verify checksum", self.verify),
                         ("Remove from list", self.remove)):
            row.addWidget(button(text, on_click=fn))
        row.addStretch(1)
        w = QWidget()
        w.setLayout(row)
        self.body.addWidget(w)
        self.rows: list = []

    def kinds_of_interest(self) -> set[str]:
        return {"export", "variant", "cover_letter"}

    def refresh(self) -> None:
        self.rows = self.ctx.repo.db.query("SELECT * FROM exports WHERE removed = 0 ORDER BY created_at DESC")
        self.table.setRowCount(len(self.rows))
        kinds = {"resume": "Resume", "cover_letter": "Cover letter", "portfolio": "Portfolio"}
        for i, r in enumerate(self.rows):
            p = Path(r["path"])
            vals = [r["created_at"][:16].replace("T", " "), kinds.get(r["document_kind"], r["document_kind"]),
                    r["format"].upper(), p.name, str(r["page_count"] or ""), r["engine"],
                    "Passed" if r["status"] == "valid" else "Passed with warnings", "Yes" if p.exists() else "No"]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 3:
                    it.setToolTip(str(p))
                self.table.setItem(i, j, it)

    def _row(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return self.rows[rows[0]] if rows else None

    def open_file(self) -> None:
        r = self._row()
        if r is not None and Path(r["path"]).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(r["path"]))
        elif r is not None:
            info(self, "Open file", "The file is no longer at its original location.")

    def open_folder(self) -> None:
        r = self._row()
        folder = Path(r["path"]).parent if r is not None else self.ctx.ws.exports_dir
        if folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def show_report(self) -> None:
        r = self._row()
        if r is None:
            return
        rep = json.loads(r["validation"] or "{}")
        icon = {"pass": "✔", "warn": "⚠", "fail": "✖", "skip": "–"}
        html = "<table cellpadding='4'>" + "".join(
            f"<tr><td>{icon.get(c.get('status'), '')}</td><td><b>{esc(c.get('name', ''))}</b></td>"
            f"<td>{esc(c.get('message', ''))}</td></tr>" for c in rep.get("checks", [])) + "</table>"
        html += f"<p><small>SHA-256 at export: {esc(r['sha256'])}</small></p>"
        ReportDialog(self, "Validation report", html, Path(r["path"]).name).exec()

    def verify(self) -> None:
        r = self._row()
        if r is None:
            return
        p = Path(r["path"])
        if not p.exists():
            info(self, "Verify checksum", "The file is no longer at its original location.")
            return
        same = sha256_file(p) == r["sha256"]
        info(self, "Verify checksum", "The file is unchanged since export." if same else
             "The file has changed since it was exported (its checksum differs).")

    def remove(self) -> None:
        r = self._row()
        if r is None:
            return
        if confirm(self, "Remove from list", "Remove this entry from the list? The file itself is not deleted."):
            self.ctx.repo.db.execute("UPDATE exports SET removed = 1 WHERE id = ?", (r["id"],))
            self.refresh()

    def portfolio(self, acknowledge: bool = False, folder: str | None = None, public_only: bool | None = None) -> None:
        from ris.composition.portfolio import build_portfolio
        from ris.rendering.export import ExportOptions

        if public_only is None:
            public_only = confirm(self, "Redacted portfolio", "Include only records classified as Public?",
                                  ok="Public only",
                                  detail="Choose Cancel to include Public and Approved-for-professional-use records. "
                                         "Confidential and unreviewed records are never included.")
        if folder is None:
            folder = QFileDialog.getExistingDirectory(self, "Export folder", str(self.ctx.ws.exports_dir))
            if not folder:
                return
        spec = self.ctx.templates.get("modern_professional")
        doc = build_portfolio(self.ctx.snapshot(), template_id=spec.id, template_version=spec.version,
                              public_only=public_only, is_sample=self.ctx.is_sample)
        svc = self.ctx.export_service()
        opts = ExportOptions(formats=("docx", "pdf"), folder=Path(folder), pdf_engine=self.ctx.pdf_engine,
                             fit_to_pages=False, acknowledge_warnings=acknowledge,
                             filename="Portfolio (redacted)")

        def done(out) -> None:
            if not out.ok and out.report is None and out.review is not None:
                dlg = ReviewDialog(self, self.ctx, out.review)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self.portfolio(acknowledge=dlg.acknowledged(), folder=folder, public_only=public_only)
                return
            from ris.ui.dialogs import report_html

            ReportDialog(self, "Portfolio export", "<ul>" + "".join(f"<li>{esc(str(f.path))}</li>" for f in out.files)
                         + "</ul>" + report_html(out.report), out.message, "ok" if out.ok else "bad").exec()
            self.refresh()

        run_task(lambda: svc.export_document(doc, spec, opts, document_kind="portfolio"), done,
                 lambda m, d: error(self, "Portfolio", m, d))


_ = Qt
