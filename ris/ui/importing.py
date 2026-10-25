"""Profile import flow: choose a file → preview candidates → commit selected (as unconfirmed, requires review)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ris.domain.enums import RecordKind, label
from ris.domain.registry import field_metas, model_for
from ris.errors import RISError
from ris.ui.dialogs import ImportPreviewDialog
from ris.ui.widgets.common import error, info, muted

CSV_KINDS = [RecordKind.POSITION, RecordKind.EDUCATION, RecordKind.PUBLICATION, RecordKind.PROJECT,
             RecordKind.SKILL, RecordKind.ACTIVITY, RecordKind.BULLET]


class CsvMappingDialog(QDialog):
    def __init__(self, parent: QWidget | None, headers: list[str]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Map spreadsheet columns")
        self.headers = headers
        lay = QVBoxLayout(self)
        lay.addWidget(muted("Choose what each row describes, then match the columns to fields. Unmatched columns "
                            "are ignored."))
        top = QFormLayout()
        self.kind = QComboBox()
        for k in CSV_KINDS:
            self.kind.addItem(label(k), k.value)
        top.addRow("Each row is a:", self.kind)
        lay.addLayout(top)
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        lay.addWidget(self.form_host)
        self.combos: dict[str, QComboBox] = {}
        self.kind.currentIndexChanged.connect(self._rebuild)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._rebuild()

    def _rebuild(self) -> None:
        from ris.services.importers import suggest_mapping

        while self.form.rowCount():
            self.form.removeRow(0)
        self.combos.clear()
        kind = RecordKind(self.kind.currentData())
        metas = [m for m in field_metas(model_for(kind)) if m.widget not in ("custom", "refs", "ref")]
        suggested = suggest_mapping(kind, self.headers)
        for h in self.headers:
            cb = QComboBox()
            cb.addItem("(ignore)", "")
            for m in metas:
                cb.addItem(m.title, m.name)
            idx = cb.findData(suggested.get(h, ""))
            cb.setCurrentIndex(max(idx, 0))
            cb.setAccessibleName(f"Field for column {h}")
            self.combos[h] = cb
            self.form.addRow(QLabel(h), cb)

    def mapping(self):
        from ris.services.importers import CsvMapping

        return CsvMapping(RecordKind(self.kind.currentData()),
                          {h: cb.currentData() for h, cb in self.combos.items() if cb.currentData()})


def import_profile_file(parent: QWidget, ctx, path: str | None = None) -> int:
    """Run the import flow. Returns the number of records created."""
    from ris.services import importers, portable

    if path is None:
        path, _ = QFileDialog.getOpenFileName(
            parent, "Import into your profile", "",
            "Supported files (*.json *.csv *.txt *.md *.docx *.pdf);;Profile JSON (*.json);;Spreadsheet (*.csv);;"
            "Documents (*.txt *.md *.docx *.pdf)")
        if not path:
            return 0
    p = Path(path)
    try:
        ext = p.suffix.lower()
        if ext == ".json":
            prev = portable.preview(ctx.repo, portable.load_payload(p))
        elif ext == ".csv":
            headers, _rows = importers.read_csv(p)
            dlg = CsvMappingDialog(parent, headers)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return 0
            prev = importers.preview_csv(ctx.repo, p, dlg.mapping())
        else:
            prev = importers.preview_file(ctx.repo, p)
    except RISError as exc:
        error(parent, "Import", exc.user_message, exc.detail)
        return 0
    if not prev.candidates:
        info(parent, "Import", "No records could be recognised in that file. You can enter the details manually.")
        return 0
    if ext != ".json":
        info(parent, "Import", "Text extracted from documents is a rough starting point. Check every field after "
                               "importing — dates and titles are often split differently from the original.")
    dlg = ImportPreviewDialog(parent, prev, title=f"Import preview — {p.name}")
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return 0
    rep = portable.commit(ctx.repo, prev)
    ctx.invalidate()
    msg = f"Imported {rep.created} record(s)."
    if rep.merged_personal:
        msg += " Empty personal details were filled in; existing details were kept."
    if rep.errors:
        msg += " " + " ".join(rep.errors[:3])
    info(parent, "Import complete", msg + " Every imported fact is awaiting your confirmation and requires a "
                                          "disclosure review.")
    return rep.created


def export_profile_json(parent: QWidget, ctx) -> None:
    from ris.services import portable
    from ris.ui.widgets.common import confirm

    path, _ = QFileDialog.getSaveFileName(parent, "Export profile (JSON)", "profile.ris.json", "Profile JSON (*.json)")
    if not path:
        return
    include = confirm(parent, "Confidential records",
                      "Include records marked Confidential in this export file?",
                      ok="Include confidential records",
                      detail="Choose Cancel to leave them out. The file is not encrypted; store it carefully.")
    try:
        portable.write_export(ctx.repo, Path(path), include_confidential=include, label=ctx.ws.name)
    except RISError as exc:
        error(parent, "Export", exc.user_message)
        return
    ctx.say(f"Profile exported to {Path(path).name}.")
