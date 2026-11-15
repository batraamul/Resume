"""Deputation & UPSC formats: what each recruitment route asks for, how ready the profile is for the DoPT
bio-data proforma, and one-click creation of the right document."""

from __future__ import annotations

from html import escape

from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QTableWidget, QTableWidgetItem

from ris.intelligence.formats import DIRECT_CHECKLIST, PROFORMA_CHECKLIST
from ris.intelligence.proforma_guide import STATUS_LABEL, proforma_readiness, readiness_summary
from ris.strings import ELIGIBILITY_NOTE, PAGE_SUBTITLES
from ris.ui.widgets.common import Card, Page, banner, button, muted, set_banner

#: (mode id, button text, what it is for)
FORMATS = [
    ("deputation_proforma", "Create the deputation proforma",
     "Deputation, absorption or short-term contract (including posts advertised through UPSC): the bio-data / "
     "CV proforma of DoPT OM No. AB.14017/28/2014-Estt.(RR) dated 02.07.2015 — items 1–18, your declaration "
     "and the employer's certificate."),
    ("senior_scientist", "Create a Senior Scientist CV",
     "Direct or lateral recruitment (UPSC Online Recruitment Application, DRDO RAC and similar): a detailed "
     "single-column CV that justifies each requirement. Use it to fill the online form and at interview."),
    ("government_biodata", "Create a government bio-data",
     "Internal postings, committees and nominations: a formal bio-data with official particulars."),
]


def _bullets(items) -> str:
    return "<ul style='margin-top:2px'>" + "".join(f"<li>{escape(i)}</li>" for i in items) + "</ul>"


class DeputationPage(Page):
    key = "deputation"

    def __init__(self, ctx, on_create=None) -> None:
        super().__init__(ctx, "Deputation & UPSC Formats", PAGE_SUBTITLES["deputation"])
        self.on_create = on_create
        fmt = Card("Which format does the vacancy need?")
        for mode_id, text, purpose in FORMATS:
            row = QHBoxLayout()
            lab = QLabel(purpose)
            lab.setWordWrap(True)
            row.addWidget(lab, 1)
            row.addWidget(button(text, "primary" if mode_id == "deputation_proforma" else None,
                                 on_click=lambda m=mode_id: self.create(m),
                                 tooltip="Creates a resume in Resume Studio with this format"))
            fmt.body.addLayout(row)
        fmt.add(muted("If the vacancy circular encloses its own form or annexure, that form must be used; copy the "
                      "content across from the proforma. " + ELIGIBILITY_NOTE))
        self.body.addWidget(fmt)

        ready = Card("Your readiness for the DoPT bio-data proforma")
        self.summary = banner("", "info")
        ready.add(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Item", "What the proforma asks", "Status", "Where to record it"])
        self.table.setAccessibleName("Proforma readiness")
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(lambda item: self._open_row(item.row()))
        ready.add(self.table)
        row = QHBoxLayout()
        row.addWidget(button("Open the selected item", on_click=lambda: self._open_row(self.table.currentRow()),
                             tooltip="Go to the page where this item is recorded"))
        row.addWidget(muted("Private particulars print only in the proforma, and only those you tick for that "
                            "resume in Resume Studio."), 1)
        ready.body.addLayout(row)
        self.body.addWidget(ready)

        lists = Card("What to send with the application")
        text = QLabel("<b>Deputation, absorption or short-term contract</b>" + _bullets(PROFORMA_CHECKLIST)
                      + "<b>Direct or lateral recruitment (online application)</b>" + _bullets(DIRECT_CHECKLIST))
        text.setWordWrap(True)
        lists.add(text)
        lists.add(muted("Advice only: the notice and its prescribed form always prevail."))
        self.body.addWidget(lists)
        self.body.addStretch(1)
        self._items = []

    def kinds_of_interest(self) -> set[str] | None:
        return {"personal", "position", "education", "publication", "activity", "training", "vacancy"}

    def refresh(self) -> None:
        self._items = proforma_readiness(self.ctx.snapshot())
        set_banner(self.summary, readiness_summary(self._items),
                   "warn" if any(i.status == "missing" for i in self._items) else "ok")
        self.table.setRowCount(len(self._items))
        for r, it in enumerate(self._items):
            what = it.title + (f"\n{it.detail}" if it.detail else "")
            for c, value in enumerate((it.number, what, STATUS_LABEL[it.status], it.where)):
                cell = QTableWidgetItem(value)
                if c == 1 and it.detail:
                    cell.setToolTip(it.detail)
                self.table.setItem(r, c, cell)
        self.table.resizeRowsToContents()
        self.table.setMinimumHeight(min(620, 34 + sum(self.table.rowHeight(r) for r in range(len(self._items)))))

    def _open_row(self, row: int) -> None:
        if 0 <= row < len(self._items) and self._items[row].page:
            self.ctx.navigate.emit(self._items[row].page, "")

    def create(self, mode_id: str) -> None:
        if self.on_create:
            self.on_create(mode_id)
