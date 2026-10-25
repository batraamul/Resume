"""Application Tracker: applications, statuses, deadlines and linked documents."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ris.domain import dates
from ris.domain.enums import ApplicationStatus, RecordKind, choices, label
from ris.strings import PAGE_SUBTITLES
from ris.ui.widgets.common import Page, button, muted
from ris.ui.widgets.records import RecordEditor

COLUMNS = ["Organisation", "Vacancy", "Status", "Deadline", "Submitted", "Interview", "Follow-up"]


class TrackerPage(Page):
    key = "tracker"

    def __init__(self, ctx) -> None:
        super().__init__(ctx, "Application Tracker", PAGE_SUBTITLES["tracker"], scrollable=False)
        self.header.add_action(button("New application", "primary", on_click=self.new_app))
        row = QHBoxLayout()
        row.addWidget(QLabel("Show:"))
        self.filter = QComboBox()
        self.filter.setAccessibleName("Status filter")
        self.filter.addItem("Active applications", "active")
        self.filter.addItem("All applications", "")
        for v, t in choices(ApplicationStatus):
            self.filter.addItem(t, v)
        self.filter.currentIndexChanged.connect(lambda _i: self.refresh())
        row.addWidget(self.filter)
        row.addStretch(1)
        self.summary = muted("")
        row.addWidget(self.summary)
        rw = QWidget()
        rw.setLayout(row)
        self.body.addWidget(rw)
        split = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAccessibleName("Applications")
        self.table.itemSelectionChanged.connect(self._selected)
        split.addWidget(self.table)
        self.editor = RecordEditor(ctx)
        self.editor.saved.connect(lambda rid: self.refresh(select=rid))
        self.editor.deleted.connect(lambda _rid: self.refresh())
        split.addWidget(self.editor)
        split.setSizes([300, 480])
        self.body.addWidget(split, 1)
        self._suppress = False

    def kinds_of_interest(self) -> set[str]:
        return {"application", "vacancy", "variant", "cover_letter"}

    def refresh(self, select: str | None = None) -> None:
        cur = select or (self.editor.record.id if self.editor.record else None)
        flt = self.filter.currentData()
        today = self.ctx.today or date.today()
        active = {"saved", "researching", "eligibility_review", "preparing", "applied", "interview",
                  "awaiting_decision"}
        apps = self.ctx.snapshot().of(RecordKind.APPLICATION)
        shown = [a for a in apps if (flt == "" or (flt == "active" and a.data.status in active)
                                     or a.data.status == flt)]
        self._suppress = True
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(shown))
        sel_row = None
        for i, a in enumerate(shown):
            d = a.data
            vals = [d.organisation, d.vacancy_title, label(ApplicationStatus(d.status)), d.deadline,
                    d.submission_date, d.interview_date, d.follow_up_date]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v or "")
                if j == 0:
                    it.setData(Qt.ItemDataRole.UserRole, a.id)
                if j == 3 and v and d.status in active and d.status != "applied":
                    pd = dates.parse_or_none(v)
                    if pd is not None and pd.earliest() < today:
                        it.setText(f"{v} (passed)")
                self.table.setItem(i, j, it)
            if a.id == cur:
                sel_row = i
        self.table.setSortingEnabled(True)
        self._suppress = False
        n_active = sum(1 for a in apps if a.data.status in active)
        self.summary.setText(f"{n_active} active · {len(apps)} total")
        if sel_row is not None:
            self.table.selectRow(sel_row)
        elif not self.editor.is_dirty() and self.editor.kind is None or (
                self.editor.record is not None and self.ctx.repo.find(self.editor.record.id) is None):
            self.editor.set_record(None)

    def _selected(self) -> None:
        if self._suppress:
            return
        rows = {i.row() for i in self.table.selectedIndexes()}
        if not rows:
            return
        rid = self.table.item(next(iter(rows)), 0).data(Qt.ItemDataRole.UserRole)
        if self.editor.record is not None and self.editor.record.id == rid:
            return
        if not self.editor.maybe_save():
            return
        self.editor.reset_forms()
        self.editor.set_record(self.ctx.repo.find(rid))

    def new_app(self) -> None:
        if not self.editor.maybe_save():
            return
        self.editor.reset_forms()
        self.editor.start_new(RecordKind.APPLICATION)

    def focus_record(self, record_id: str) -> bool:
        self.filter.setCurrentIndex(1)
        self.refresh(select=record_id)
        rec = self.ctx.repo.find(record_id)
        if rec is not None and (self.editor.record is None or self.editor.record.id != record_id):
            self.editor.set_record(rec)
        return rec is not None

    def has_unsaved_changes(self) -> bool:
        return self.editor.is_dirty()

    def maybe_save(self) -> bool:
        return self.editor.maybe_save()


_ = QVBoxLayout
