"""Job Opportunities: vacancy notices, requirement extraction, evidence mapping and transparent scoring."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
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

from ris.domain.enums import EvidenceStatus, RecordKind, RecruitmentMode, RequirementCategory, choices, label
from ris.domain.models import Requirement
from ris.errors import RISError
from ris.strings import ELIGIBILITY_NOTE, PAGE_SUBTITLES, SCORE_NOTE
from ris.ui.widgets.common import Page, banner, button, confirm, error, esc, info, muted, set_banner
from ris.ui.widgets.records import RecordEditor

STATUS_TONE = {"verified": "ok", "awaiting_confirmation": "warn", "partial": "warn", "not_found": "bad",
               "not_applicable": "info", "official_verification": "info"}


class OpportunitiesPage(Page):
    key = "opportunities"

    def __init__(self, ctx) -> None:
        super().__init__(ctx, "Job Opportunities", PAGE_SUBTITLES["opportunities"], scrollable=False)
        self.header.add_action(button("New vacancy", on_click=self.new_vacancy, tooltip="Paste a notice manually"))
        self.header.add_action(button("Import notice…", on_click=self.import_notice,
                                      tooltip="Read a notice from a PDF, DOCX or text file"))
        self.header.add_action(button("Import openings list…", on_click=self.import_openings,
                                      tooltip="Add the openings from your weekly Scientist F/G scan "
                                              "(e-diary-jobs-feed-*.json)"))
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        self.list = QListWidget()
        self.list.setAccessibleName("Vacancies")
        self.list.setWordWrap(True)
        self.list.currentItemChanged.connect(self._select)
        ll.addWidget(self.list, 1)
        self.empty = muted("No vacancies yet. Paste or import a notification to analyse it against your profile.")
        ll.addWidget(self.empty)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        # vacancy tab
        vt = QWidget()
        vl = QVBoxLayout(vt)
        vl.addWidget(muted("Vacancy text is treated as data only. Instructions inside a notice are never followed."))
        self.editor = RecordEditor(ctx)
        self.editor.saved.connect(self._saved)
        self.editor.deleted.connect(lambda _rid: self.refresh())
        vl.addWidget(self.editor, 1)
        row = QHBoxLayout()
        row.addWidget(button("Suggest fields from the text", on_click=self.suggest_fields,
                             tooltip="Fill empty fields (closing date, pay level, sections) from the pasted text"))
        row.addStretch(1)
        vl.addLayout(row)
        self.tabs.addTab(vt, "Vacancy")
        # requirements tab
        qt = QWidget()
        ql = QVBoxLayout(qt)
        ql.addWidget(muted("Requirements are extracted from the notice by transparent rules. Correct the category, "
                           "mark essential items, add anything missed, then save."))
        self.req_table = QTableWidget(0, 5)
        self.req_table.setHorizontalHeaderLabels(["Essential", "Category", "Requirement", "Your status override",
                                                  "Note"])
        h = self.req_table.horizontalHeader()
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.req_table.setColumnWidth(1, 190)
        self.req_table.setColumnWidth(3, 200)
        self.req_table.verticalHeader().setVisible(False)
        self.req_table.setWordWrap(True)
        self.req_table.setAccessibleName("Requirements")
        self.req_table.itemChanged.connect(lambda _i: self._req_dirty(True))
        ql.addWidget(self.req_table, 1)
        rrow = QHBoxLayout()
        rrow.addWidget(button("Extract from the vacancy text", on_click=self.extract))
        rrow.addWidget(button("Add requirement", on_click=self.add_requirement))
        rrow.addWidget(button("Remove selected", on_click=self.remove_requirement))
        rrow.addStretch(1)
        self.b_save_req = button("Save requirements", "primary", on_click=self.save_requirements)
        rrow.addWidget(self.b_save_req)
        ql.addLayout(rrow)
        self.tabs.addTab(qt, "Requirements")
        # analysis tab
        at = QWidget()
        al = QVBoxLayout(at)
        self.score_banner = banner("", "info")
        al.addWidget(self.score_banner)
        asplit = QSplitter(Qt.Orientation.Vertical)
        self.results = QTableWidget(0, 4)
        self.results.setHorizontalHeaderLabels(["Requirement", "Ess.", "Evidence status", "Evidence in your profile"])
        rh = self.results.horizontalHeader()
        rh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        rh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.results.verticalHeader().setVisible(False)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results.setWordWrap(True)
        self.results.setAccessibleName("Requirement evidence matrix")
        self.results.cellDoubleClicked.connect(self._open_evidence)
        asplit.addWidget(self.results)
        self.explain = QTextBrowser()
        self.explain.setAccessibleName("Score explanation and readiness")
        asplit.addWidget(self.explain)
        asplit.setSizes([380, 300])
        al.addWidget(asplit, 1)
        arow = QHBoxLayout()
        arow.addWidget(button("Re-analyse", on_click=self.analyse))
        arow.addStretch(1)
        arow.addWidget(button("Track this application", on_click=self.track))
        arow.addWidget(button("Draft cover letter", on_click=self.letter))
        arow.addWidget(button("Graphical profile", on_click=lambda: self.tailor(graphical=True),
                              tooltip="A graphical profile for the interview board or networking"))
        arow.addWidget(button("Create resume in recommended format", "primary", on_click=self.tailor))
        al.addLayout(arow)
        self.format_box = QTextBrowser()
        self.format_box.setAccessibleName("Recommended format")
        self.format_box.setMaximumHeight(170)
        al.addWidget(self.format_box)
        self.tabs.addTab(at, "Evidence && score")
        rl.addWidget(self.tabs, 1)
        split.addWidget(right)
        split.setSizes([300, 900])
        self.body.addWidget(split, 1)
        self.current_id: str | None = None
        self._req_changed = False
        self.analysis = None

    def kinds_of_interest(self) -> set[str] | None:
        return None  # evidence depends on the whole profile

    # ------------------------------------------------------------------ list
    def refresh(self) -> None:
        cur = self.current_id
        self.list.blockSignals(True)
        self.list.clear()
        sel = None
        for v in self.ctx.snapshot().of(RecordKind.VACANCY):
            text = v.data.title or "(untitled vacancy)"
            if v.data.employer:
                text += f"\n{v.data.employer}"
            if v.data.deadline:
                text += f" · closes {v.data.deadline}"
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, v.id)
            self.list.addItem(it)
            if v.id == cur:
                sel = it
        self.list.blockSignals(False)
        self.empty.setVisible(self.list.count() == 0)
        if sel is not None:
            self.list.setCurrentItem(sel)
            self._load(cur, keep_editor=self.editor.is_dirty())
        elif self.list.count() and not self.editor.is_dirty():
            self.list.setCurrentRow(0)
        elif not self.list.count() and not self.editor.is_dirty():
            self.current_id = None
            self.editor.set_record(None)
            self._clear_analysis()

    def _select(self, cur, _prev) -> None:
        rid = cur.data(Qt.ItemDataRole.UserRole) if cur else None
        if rid == self.current_id:
            return
        if not self.editor.maybe_save() or not self._maybe_save_requirements():
            return
        self._load(rid)

    def _load(self, rid: str | None, keep_editor: bool = False) -> None:
        self.current_id = rid
        rec = self.ctx.repo.find(rid) if rid else None
        if (rec is not None and not rec.data.requirements and not rec.data.extracted_at
                and (rec.data.raw_text or rec.data.essential_qualifications or rec.data.required_skills)):
            # First open of a notice that was never analysed: extract once (editable, never repeated silently).
            self._auto_extract(rec.id)
            self.ctx.invalidate()
            rec = self.ctx.repo.get(rec.id)
        if not keep_editor:
            self.editor.set_record(rec)
        self._fill_requirements(rec)
        self.show_format_advice(rec)
        self.analyse()

    def focus_record(self, record_id: str) -> bool:
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == record_id:
                self.list.setCurrentRow(i)
                return True
        return False

    # ------------------------------------------------------------------ vacancy
    def new_vacancy(self) -> None:
        if not self.editor.maybe_save():
            return
        self.tabs.setCurrentIndex(0)
        self.current_id = None
        self.list.clearSelection()
        self.editor.start_new(RecordKind.VACANCY)
        self._fill_requirements(None)
        self._clear_analysis()

    def import_notice(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import vacancy notice", "",
                                              "Notices (*.pdf *.docx *.txt *.md *.html *.htm)")
        if not path:
            return
        from ris.domain.models import Vacancy
        from ris.services.importers import vacancy_from_file

        try:
            fields = vacancy_from_file(Path(path))
        except RISError as exc:
            error(self, "Import notice", exc.user_message, exc.detail)
            return
        data = {k: v for k, v in fields.items() if k in Vacancy.model_fields}
        try:
            rec = self.ctx.repo.create(RecordKind.VACANCY, data)
        except RISError as exc:
            error(self, "Import notice", exc.user_message)
            return
        self._auto_extract(rec.id)
        self.ctx.invalidate()
        self.current_id = rec.id
        self.refresh()
        self.tabs.setCurrentIndex(1)
        info(self, "Notice imported", "Check the title, employer and closing date, then review the extracted "
                                      "requirements before relying on the analysis.")

    def _auto_extract(self, rid: str) -> None:
        from ris.intelligence.vacancy import extract_requirements

        rec = self.ctx.repo.get(rid)
        reqs = extract_requirements(rec.data)
        self.ctx.repo.patch(rid, requirements=[r.model_dump(mode="json") for r in reqs],
                            extracted_at=date.today().isoformat())

    def suggest_fields(self) -> None:
        from ris.intelligence.vacancy import suggest_fields

        if self.editor.form is None or self.editor.kind != RecordKind.VACANCY:
            return
        raw = self.editor.form.value("raw_text")
        if not raw:
            info(self, "Suggest fields", "Paste the vacancy text into 'Full vacancy text' first.")
            return
        sugg = suggest_fields(raw)
        filled = []
        for k, v in sugg.items():
            if k in self.editor.form.editors and not self.editor.form.value(k):
                self.editor.form.set_value(k, v)
                filled.append(self.editor.form.labels[k].text())
        info(self, "Suggest fields", ("Filled: " + ", ".join(filled) + ". Check them, then save.") if filled else
             "No empty fields could be filled from the text.")

    def _saved(self, rid: str) -> None:
        rec = self.ctx.repo.get(rid)
        if not rec.data.requirements and (rec.data.raw_text or rec.data.essential_qualifications):
            self._auto_extract(rid)
        self.current_id = rid
        self.ctx.invalidate()
        self.refresh()

    # ------------------------------------------------------------------ requirements
    def _req_dirty(self, v: bool) -> None:
        if not getattr(self, "_filling", False):
            self._req_changed = v
            self.b_save_req.setText("Save requirements" + (" *" if v else ""))

    def _fill_requirements(self, rec) -> None:
        self._filling = True
        self.req_table.setRowCount(0)
        reqs = rec.data.requirements if rec is not None else []
        for r in reqs:
            self._add_row(Requirement.model_validate(r) if isinstance(r, dict) else r)
        self.req_table.resizeRowsToContents()
        self._filling = False
        self._req_dirty(False)
        self.b_save_req.setEnabled(rec is not None)

    def _add_row(self, r: Requirement) -> None:
        i = self.req_table.rowCount()
        self.req_table.insertRow(i)
        box = QCheckBox()
        box.setChecked(bool(r.mandatory))
        box.setAccessibleName("Essential")
        box.toggled.connect(lambda _c: self._req_dirty(True))
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(6, 0, 0, 0)
        hl.addWidget(box)
        self.req_table.setCellWidget(i, 0, holder)
        cat = QComboBox()
        for v, t in choices(RequirementCategory):
            cat.addItem(t, v)
        cat.setCurrentIndex(max(cat.findData(str(r.category)), 0))
        cat.setAccessibleName("Category")
        cat.currentIndexChanged.connect(lambda _i: self._req_dirty(True))
        self.req_table.setCellWidget(i, 1, cat)
        t = QTableWidgetItem(r.text)
        t.setData(Qt.ItemDataRole.UserRole, r.model_dump(mode="json"))
        t.setToolTip(f"Origin: {r.origin}" + (f" · keywords: {', '.join(r.keywords)}" if r.keywords else ""))
        self.req_table.setItem(i, 2, t)
        ov = QComboBox()
        ov.addItem("(automatic)", "")
        for v, tx in choices(EvidenceStatus):
            ov.addItem(tx, v)
        ov.setCurrentIndex(max(ov.findData(str(r.status_override or "")), 0))
        ov.setAccessibleName("Status override")
        ov.currentIndexChanged.connect(lambda _i: self._req_dirty(True))
        self.req_table.setCellWidget(i, 3, ov)
        self.req_table.setItem(i, 4, QTableWidgetItem(r.user_note))

    def _collect(self) -> list[dict]:
        out = []
        for i in range(self.req_table.rowCount()):
            item = self.req_table.item(i, 2)
            text = (item.text() if item else "").strip()
            if not text:
                continue
            base = dict(item.data(Qt.ItemDataRole.UserRole) or {})
            box = self.req_table.cellWidget(i, 0).findChild(QCheckBox)
            base.update({
                "text": text,
                "mandatory": box.isChecked(),
                "category": self.req_table.cellWidget(i, 1).currentData(),
                "status_override": self.req_table.cellWidget(i, 3).currentData() or None,
                "user_note": (self.req_table.item(i, 4).text() if self.req_table.item(i, 4) else "").strip(),
            })
            if base.get("text") != (item.data(Qt.ItemDataRole.UserRole) or {}).get("text"):
                base["origin"] = "manual"
            out.append(Requirement.model_validate(base).model_dump(mode="json"))
        return out

    def add_requirement(self) -> None:
        if self.current_id is None:
            info(self, "Requirements", "Save the vacancy first.")
            return
        self._add_row(Requirement(text="", origin="manual", category=RequirementCategory.TECHNICAL))
        r = self.req_table.rowCount() - 1
        self.req_table.setCurrentCell(r, 2)
        self.req_table.editItem(self.req_table.item(r, 2))
        self._req_dirty(True)

    def remove_requirement(self) -> None:
        rows = sorted({i.row() for i in self.req_table.selectedIndexes()}, reverse=True)
        cur = self.req_table.currentRow()
        if not rows and cur >= 0:
            rows = [cur]
        for r in rows:
            self.req_table.removeRow(r)
        if rows:
            self._req_dirty(True)

    def save_requirements(self) -> bool:
        if self.current_id is None:
            return False
        try:
            self.ctx.repo.patch(self.current_id, requirements=self._collect())
        except RISError as exc:
            error(self, "Requirements", exc.user_message)
            return False
        self._req_dirty(False)
        self.ctx.invalidate()
        self.analyse()
        self.ctx.say("Requirements saved and analysis updated.")
        return True

    def _maybe_save_requirements(self) -> bool:
        if not self._req_changed:
            return True
        if confirm(self, "Unsaved requirements", "Save your changes to the requirements?", ok="Save"):
            return self.save_requirements()
        self._req_dirty(False)
        return True

    def extract(self) -> None:
        from ris.intelligence.vacancy import extract_requirements, merge_requirements

        if self.current_id is None:
            info(self, "Requirements", "Save the vacancy first.")
            return
        if self.editor.is_dirty() and not self.editor.save():
            return
        rec = self.ctx.repo.get(self.current_id)
        existing = [Requirement.model_validate(r) for r in self._collect()]
        extracted = extract_requirements(rec.data)
        merged = merge_requirements(existing, extracted)
        self.ctx.repo.patch(self.current_id, requirements=[r.model_dump(mode="json") for r in merged],
                            extracted_at=date.today().isoformat())
        self.ctx.invalidate()
        self._fill_requirements(self.ctx.repo.get(self.current_id))
        self.analyse()
        self.ctx.say(f"{len(extracted)} requirement(s) extracted. Your manual items and corrections were kept.")

    # ------------------------------------------------------------------ analysis
    def _clear_analysis(self) -> None:
        self.analysis = None
        self.results.setRowCount(0)
        self.explain.setHtml("")
        set_banner(self.score_banner, "Save a vacancy and its requirements to see the evidence analysis.", "info")

    def analyse(self) -> None:
        from ris.intelligence.analysis import analyse

        if self.current_id is None:
            self._clear_analysis()
            return
        rec = self.ctx.repo.find(self.current_id)
        if rec is None or not rec.data.requirements:
            self._clear_analysis()
            if rec is not None:
                set_banner(self.score_banner, "No requirements yet. Paste the notice text and choose 'Extract from "
                           "the vacancy text' on the Requirements tab.", "info")
            return
        snap = self.ctx.snapshot()
        target = snap.get(rec.data.target_id) if rec.data.target_id else None
        res = analyse(snap, rec.data, target=target.data if target is not None else None,
                      weights=self.ctx.settings.get("scoring.weights"), today=self.ctx.today)
        self.analysis = res
        a = res.assessment
        tone = "ok" if a.score >= 70 and not a.mandatory_gaps else ("warn" if a.score >= 45 else "bad")
        gaps = f" {len(a.mandatory_gaps)} essential requirement(s) not supported by your records." \
            if a.mandatory_gaps else ""
        set_banner(self.score_banner, f"Evidence alignment {a.score:.0f}/100 — {a.band}.{gaps} {SCORE_NOTE}", tone)
        self.results.setRowCount(len(res.results))
        for i, r in enumerate(res.results):
            req = QTableWidgetItem(r.requirement.text)
            req.setToolTip(label(RequirementCategory(r.requirement.category)) + (f"\n{r.explanation}" if r.explanation
                                                                                 else ""))
            self.results.setItem(i, 0, req)
            self.results.setItem(i, 1, QTableWidgetItem("Yes" if r.requirement.mandatory else ""))
            st = QTableWidgetItem(("✔ " if r.status == EvidenceStatus.VERIFIED else
                                   "✖ " if r.status == EvidenceStatus.NOT_FOUND else "• ") + r.status_label)
            st.setToolTip(r.explanation)
            self.results.setItem(i, 2, st)
            ev = "; ".join(f"{e.title}{'' if e.confirmed else ' (unconfirmed)'}" for e in r.evidence[:4])
            evi = QTableWidgetItem(ev or "—")
            evi.setData(Qt.ItemDataRole.UserRole, r.evidence[0].record_id if r.evidence else "")
            evi.setToolTip("\n".join(f"{e.title}: {e.reason}" for e in r.evidence) or "No matching evidence.")
            self.results.setItem(i, 3, evi)
        self.results.resizeRowsToContents()
        html = ["<h3>How the score is calculated</h3><ul>"]
        for c in a.components:
            if c.value is None:
                html.append(f"<li><b>{esc(c.label)}</b>: not applicable (weight redistributed).</li>")
            else:
                html.append(f"<li><b>{esc(c.label)}</b>: {c.value:.0%} × {c.effective_weight:.0%} = "
                            f"{c.points:.1f} points. {esc(c.explanation)}</li>")
        html.append("</ul>")
        for n in a.notes:
            html.append(f"<p>{esc(n)}</p>")
        if a.mandatory_gaps:
            html.append("<h3>Essential requirements without supporting evidence</h3><ul>"
                        + "".join(f"<li>{esc(g)}</li>" for g in a.mandatory_gaps) + "</ul>")
        if a.eligibility or a.documentation:
            html.append(f"<h3>Requires official verification</h3><p><i>{esc(ELIGIBILITY_NOTE)}</i></p><ul>"
                        + "".join(f"<li>{esc(e.text)} — {esc(e.note)}</li>" for e in a.eligibility + a.documentation)
                        + "</ul>")
        rd = res.readiness
        if rd.items:
            groups = {"confirm": "Confirm evidence you already recorded", "add_data": "Add missing information",
                      "possible_gap": "Possible gaps", "strengthen": "Could be strengthened",
                      "verify_officially": "Check officially / prepare documents"}
            html.append("<h3>Application readiness</h3>")
            for k, title in groups.items():
                items = rd.by_kind(k)
                if items:
                    html.append(f"<p><b>{esc(title)}</b></p><ul>" + "".join(
                        f"<li>{esc(i.requirement)} — {esc(i.advice)}</li>" for i in items) + "</ul>")
        if rd.strengths:
            html.append("<h3>Strengths (essential items with verified evidence)</h3><ul>"
                        + "".join(f"<li>{esc(s)}</li>" for s in rd.strengths) + "</ul>")
        self.explain.setHtml("".join(html))

    def _open_evidence(self, row: int, col: int) -> None:
        item = self.results.item(row, 3)
        rid = item.data(Qt.ItemDataRole.UserRole) if item else ""
        if rid:
            self.ctx.navigate.emit("record", rid)

    # ------------------------------------------------------------------ follow-on actions
    def _vacancy(self):
        if self.current_id is None:
            info(self, "Vacancy", "Select or save a vacancy first.")
            return None
        if self.editor.is_dirty() and not self.editor.save():
            return None
        return self.ctx.repo.get(self.current_id)

    def show_format_advice(self, rec) -> None:
        from html import escape

        from ris.intelligence.formats import recommend_for_vacancy

        if rec is None:
            self.format_box.setHtml("")
            return
        a = recommend_for_vacancy(rec.data)
        parts = [f"<b>Recommended format:</b> {escape(a.title)}<br>{escape(a.reason)}"]
        if a.own_form_warning:
            parts.append(f"<br><b>{escape(a.own_form_warning)}</b>")
        if a.checklist:
            parts.append("<br><b>Checklist</b><ul>" + "".join(f"<li>{escape(c)}</li>" for c in a.checklist) + "</ul>")
        parts.append("<i>Advice only: the notice and its prescribed form always prevail.</i>")
        self.format_box.setHtml("".join(parts))

    def import_openings(self, path: str | None = None) -> None:
        from ris.services.openings_feed import import_feed

        if path is None:
            start = getattr(self.ctx.config, "openings_feed_path", "") or ""
            path, _ = QFileDialog.getOpenFileName(self, "Import openings list", start,
                                                  "Openings list (*.json)")
            if not path:
                return
        try:
            res = import_feed(self.ctx.repo, Path(path), today=self.ctx.today)
        except RISError as exc:
            error(self, "Import openings list", exc.user_message, exc.detail)
            return
        self.ctx.config.openings_feed_path = str(Path(path).parent)
        try:
            self.ctx.config.save()
        except OSError:
            pass
        self.ctx.invalidate()
        self.refresh()
        info(self, "Openings imported", res.summary() + " Open each one to see the recommended format, and check "
             "the official notice before applying.")
        return res

    def tailor(self, graphical: bool = False) -> None:
        v = self._vacancy()
        if v is None:
            return
        from ris.composition.modes import get_mode
        from ris.intelligence.formats import recommend_for_vacancy

        target = self.ctx.repo.find(v.data.target_id) if v.data.target_id else None
        advice = recommend_for_vacancy(v.data)
        if graphical:
            mode, template = "senior_graphical", "senior_graphical"
        else:
            mode, template = advice.mode, advice.template
            if (target is not None and target.data.preferred_mode and mode == "senior_scientist"
                    and v.data.recruitment_mode not in (RecruitmentMode.DIRECT.value, RecruitmentMode.LATERAL.value)):
                mode = target.data.preferred_mode
                template = target.data.preferred_template or get_mode(mode).default_template
        m = get_mode(mode)
        data = {"name": f"{v.data.title or 'Vacancy'}" + (f" — {v.data.employer}" if v.data.employer else "")
                        + (" (graphical)" if graphical else ""),
                "mode": mode, "template_id": template, "vacancy_id": v.id, "target_id": v.data.target_id,
                "length": m.default_length.value if hasattr(m.default_length, "value") else str(m.default_length)}
        rec = self.ctx.repo.create(RecordKind.VARIANT, data)
        self.ctx.invalidate()
        self.ctx.say("Tailored resume created. Review it in Resume Studio.")
        self.ctx.navigate.emit("studio", rec.id)

    def letter(self) -> None:
        v = self._vacancy()
        if v is None:
            return
        from ris.composition.cover_letter import draft_cover_letter

        payload = draft_cover_letter(self.ctx.snapshot(), v.data, self.analysis,
                                     style="formal" if v.data.recruitment_mode != RecruitmentMode.UNKNOWN.value
                                     else "professional", today=self.ctx.today)
        payload["vacancy_id"] = v.id
        rec = self.ctx.repo.create(RecordKind.COVER_LETTER, payload)
        self.ctx.invalidate()
        self.ctx.say("Cover letter drafted from confirmed facts. Review every paragraph before using it.")
        self.ctx.navigate.emit("letters", rec.id)

    def track(self) -> None:
        v = self._vacancy()
        if v is None:
            return
        existing = [a for a in self.ctx.repo.list(RecordKind.APPLICATION) if a.data.vacancy_id == v.id]
        if existing:
            self.ctx.navigate.emit("tracker", existing[0].id)
            return
        rec = self.ctx.repo.create(RecordKind.APPLICATION, {
            "organisation": v.data.employer, "vacancy_title": v.data.title, "vacancy_id": v.id,
            "official_url": v.data.url, "reference_number": v.data.reference, "deadline": v.data.deadline,
            "status": "researching"})
        self.ctx.invalidate()
        self.ctx.navigate.emit("tracker", rec.id)

    def has_unsaved_changes(self) -> bool:
        return self.editor.is_dirty() or self._req_changed

    def maybe_save(self) -> bool:
        return self.editor.maybe_save() and self._maybe_save_requirements()


_ = QLabel
