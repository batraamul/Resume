"""Interview Preparation: tailored questions, STAR stories, timed practice and personal questionnaires."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSlider,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ris.domain.enums import QuestionCategory, RecordKind, choices
from ris.domain.models import Questionnaire
from ris.intelligence import interview as iv
from ris.strings import PAGE_SUBTITLES
from ris.ui.dialogs import ReportDialog, ReviewDialog
from ris.ui.widgets.common import Card, Page, banner, button, error, esc, info, muted, scroll, set_banner
from ris.ui.widgets.form import RecordForm
from ris.ui.widgets.records import CollectionWidget
from ris.ui.workers import run_task
from ris.util import utc_now_iso

PRIVATE_NOTE = ("Everything on this page is private preparation. Questions are generated from your own records "
                "and never become facts; nothing here is printed in resumes.")

TABLES = {
    "education": (["Examination", "Institution", "Board / University", "Year", "Result", "Subjects"],
                  ["examination", "institution", "board", "year", "result", "subjects"]),
    "sports": (["Game / sport", "Level", "Position / role", "Year", "Achievement"],
               ["activity", "level", "role", "year", "achievement"]),
    "extracurricular": (["Activity", "Level", "Role", "Year", "Achievement"],
                        ["activity", "level", "role", "year", "achievement"]),
    "previous_attempts": (["Examination / interview", "Year", "Centre", "Result"],
                          ["examination", "year", "centre", "result"]),
}


class RowTable(QWidget):
    """A small editable table for questionnaire rows."""

    def __init__(self, title: str, headers: list[str], fields: list[str]) -> None:
        super().__init__()
        self.fields = fields
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel(f"<b>{esc(title)}</b>"))
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setAccessibleName(title)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(120)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(button("Add row", on_click=self.add_row))
        row.addWidget(button("Remove row", on_click=self.remove_row))
        row.addStretch(1)
        lay.addLayout(row)

    def add_row(self, values: dict | None = None) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, f in enumerate(self.fields):
            self.table.setItem(r, c, QTableWidgetItem(str((values or {}).get(f, "") or "")))

    def remove_row(self) -> None:
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def set_rows(self, rows: list) -> None:
        self.table.setRowCount(0)
        for row in rows:
            self.add_row(row if isinstance(row, dict) else row.model_dump())

    def rows(self) -> list[dict]:
        out = []
        for r in range(self.table.rowCount()):
            vals = {f: (self.table.item(r, c).text().strip() if self.table.item(r, c) else "")
                    for c, f in enumerate(self.fields)}
            if any(vals.values()):
                out.append(vals)
        return out


class InterviewPage(Page):
    key = "interview"

    def __init__(self, ctx) -> None:
        super().__init__(ctx, "Interview Preparation", PAGE_SUBTITLES["interview"], scrollable=False)
        self.header.add_action(button("Export preparation pack…", on_click=lambda: self.export_pack()))
        self.body.addWidget(banner(PRIVATE_NOTE, "info"))
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName("Interview preparation sections")
        self.questions: list[iv.Question] = []
        self.tabs.addTab(self._build_questions(), "Questions")
        self.tabs.addTab(self._build_practice(), "Practice")
        self.answers = CollectionWidget(ctx, [RecordKind.INTERVIEW_ANSWER], empty_hint=(
            "Prepare answers from the Questions tab, or add your own. Keep notes as key points, not scripts."),
            add_labels={RecordKind.INTERVIEW_ANSWER: "answer"})
        self.tabs.addTab(self.answers, "My answers")
        self.tabs.addTab(self._build_stories(), "STAR stories")
        self.tabs.addTab(self._build_questionnaire(), "Questionnaire (PIQ / DAF)")
        self.tips = QTextBrowser()
        self.tips.setOpenExternalLinks(True)
        self.tips.setAccessibleName("Interview tips")
        self.tabs.addTab(self.tips, "Tips")
        self.body.addWidget(self.tabs, 1)
        self._render_tips()

    # ------------------------------------------------------------------ questions
    def _build_questions(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Vacancy:"))
        self.vacancy = QComboBox()
        self.vacancy.setAccessibleName("Vacancy for tailored questions")
        bar.addWidget(self.vacancy, 2)
        bar.addWidget(QLabel("Organisation:"))
        self.org = QComboBox()
        self.org.setAccessibleName("Organisation for tailored questions")
        self.org.addItem("(none)", "")
        for o in self.ctx.presets.organisations.values():
            self.org.addItem(o.name, o.id)
        bar.addWidget(self.org, 2)
        bar.addWidget(QLabel("Show:"))
        self.cat = QComboBox()
        self.cat.setAccessibleName("Question category")
        self.cat.addItem("All categories", "")
        for v, t in choices(QuestionCategory):
            self.cat.addItem(t, v)
        bar.addWidget(self.cat, 1)
        self.only_mine = QComboBox()
        self.only_mine.setAccessibleName("Question source")
        self.only_mine.addItem("Tailored and general", "all")
        self.only_mine.addItem("Tailored to me", "mine")
        self.only_mine.addItem("General bank", "bank")
        bar.addWidget(self.only_mine, 1)
        bar.addWidget(button("Refresh", "primary", on_click=self.generate))
        lay.addLayout(bar)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.qtree = QTreeWidget()
        self.qtree.setHeaderLabels(["Question", "Category", "From"])
        self.qtree.setAccessibleName("Interview questions")
        self.qtree.setRootIsDecorated(False)
        self.qtree.setAlternatingRowColors(True)
        self.qtree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.qtree.currentItemChanged.connect(lambda c, _p: self._show_question(c))
        split.addWidget(self.qtree)
        right = QWidget()
        rl = QVBoxLayout(right)
        self.qdetail = QTextBrowser()
        self.qdetail.setOpenExternalLinks(True)
        self.qdetail.setAccessibleName("Question details")
        rl.addWidget(self.qdetail, 1)
        rl.addWidget(button("Prepare an answer", "primary", on_click=self.prepare_selected))
        split.addWidget(right)
        split.setSizes([700, 360])
        lay.addWidget(split, 1)
        for cb in (self.cat, self.only_mine):
            cb.currentIndexChanged.connect(lambda _i: self._fill_questions())
        for cb in (self.vacancy, self.org):
            cb.currentIndexChanged.connect(lambda _i: self.generate())
        return w

    def _questionnaire_record(self):
        recs = self.ctx.repo.list(RecordKind.QUESTIONNAIRE) if self.ctx.has_workspace else []
        return recs[0] if recs else None

    def generate(self) -> None:
        if not self.ctx.has_workspace:
            return
        from ris.intelligence.analysis import analyse

        snap = self.ctx.snapshot()
        vac_id = self.vacancy.currentData()
        vac = self.ctx.repo.find(vac_id) if vac_id else None
        analysis = analyse(snap, vac.data, today=self.ctx.today) if vac is not None else None
        org = None
        oid = self.org.currentData()
        if oid:
            o = self.ctx.presets.org(oid)
            org = {"name": o.name, "domains": list(o.domains)}
        qrec = self.questionnaire_rec or self._questionnaire_record()
        mine = iv.personalised_questions(snap, vacancy=vac.data if vac else None, analysis=analysis,
                                         organisation=org, questionnaire=qrec.data if qrec else None,
                                         today=self.ctx.today)
        self.questions = mine + iv.load_bank().questions
        self._fill_questions()

    def _visible_questions(self) -> list[iv.Question]:
        cat = self.cat.currentData()
        src = self.only_mine.currentData()
        out = []
        for q in self.questions:
            if cat and q.category != cat:
                continue
            if src == "mine" and not q.personalised:
                continue
            if src == "bank" and q.personalised:
                continue
            out.append(q)
        return out

    def _fill_questions(self) -> None:
        self.qtree.clear()
        names = {"profile": "Your profile", "vacancy": "The vacancy", "organisation": "The organisation",
                 "questionnaire": "Your questionnaire"}
        for q in self._visible_questions():
            it = QTreeWidgetItem([q.text, q.category_label, names.get(q.source, "General bank")])
            it.setData(0, Qt.ItemDataRole.UserRole, q)
            it.setToolTip(0, q.text)
            self.qtree.addTopLevelItem(it)
        if self.qtree.topLevelItemCount():
            self.qtree.setCurrentItem(self.qtree.topLevelItem(0))
        else:
            self.qdetail.setHtml("<p>No questions match. Add records to your profile or change the filters.</p>")

    def _show_question(self, item) -> None:
        if item is None:
            return
        q: iv.Question = item.data(0, Qt.ItemDataRole.UserRole)
        bank = iv.load_bank()
        html = [f"<h3>{esc(q.text)}</h3><p><i>{esc(q.category_label)}</i></p>"]
        if q.hint:
            html.append(f"<p><b>How to approach it:</b> {esc(q.hint)}</p>")
        if q.category == "behavioural":
            html.append("<p>Answer with a STAR story (see the STAR stories tab).</p>")
        if q.record_ids:
            snap = self.ctx.snapshot()
            titles = [snap.get(r).title for r in q.record_ids if snap.get(r) is not None]
            if titles:
                html.append("<p><b>Based on:</b> " + esc("; ".join(titles)) + "</p>")
        src = bank.source_for(q)
        if src:
            html.append(f"<p style='color:gray'>Source: <a href='{esc(src['url'])}'>{esc(src['title'])}</a></p>")
        existing = self._answer_for(q.text)
        if existing is not None:
            html.append(f"<p><b>You have notes for this question</b> (confidence {existing.data.confidence}/5).</p>")
        self.qdetail.setHtml("".join(html))

    def _answer_for(self, text: str):
        key = text.strip().casefold()
        for a in self.ctx.repo.list(RecordKind.INTERVIEW_ANSWER):
            if a.data.question.strip().casefold() == key:
                return a
        return None

    def prepare_selected(self) -> None:
        it = self.qtree.currentItem()
        if it is None:
            info(self, "Prepare an answer", "Select a question first.")
            return
        self.prepare_answer(it.data(0, Qt.ItemDataRole.UserRole))

    def prepare_answer(self, q: iv.Question):
        rec = self._answer_for(q.text)
        if rec is None:
            rec = self.ctx.repo.create(RecordKind.INTERVIEW_ANSWER, {"question": q.text, "category": q.category,
                                                                    "source": q.source})
            self.ctx.invalidate()
        self.tabs.setCurrentWidget(self.answers)
        self.answers.reload(select_id=rec.id)
        self.answers.focus_record(rec.id)
        return rec

    # ------------------------------------------------------------------ practice
    def _build_practice(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Questions per round:"))
        self.n_questions = QSpinBox()
        self.n_questions.setRange(3, 30)
        self.n_questions.setValue(8)
        self.n_questions.setAccessibleName("Questions per round")
        bar.addWidget(self.n_questions)
        bar.addWidget(QLabel("Category:"))
        self.practice_cat = QComboBox()
        self.practice_cat.setAccessibleName("Practice category")
        self.practice_cat.addItem("Mixed", "")
        for v, t in choices(QuestionCategory):
            self.practice_cat.addItem(t, v)
        bar.addWidget(self.practice_cat)
        bar.addWidget(button("Start a round", "primary", on_click=self.start_practice))
        bar.addStretch(1)
        lay.addLayout(bar)
        card = Card("Question")
        self.p_question = QLabel("Start a round to practise. Answer aloud; aim for 60–90 seconds for STAR answers.")
        self.p_question.setWordWrap(True)
        self.p_question.setObjectName("SectionTitle")
        self.p_question.setAccessibleName("Practice question")
        card.add(self.p_question)
        self.p_progress = muted("")
        card.add(self.p_progress)
        trow = QHBoxLayout()
        self.p_timer = QLabel("00:00")
        self.p_timer.setObjectName("StatValue")
        self.p_timer.setAccessibleName("Elapsed time")
        trow.addWidget(self.p_timer)
        self.p_timer_note = muted("")
        trow.addWidget(self.p_timer_note, 1)
        card.body.addLayout(trow)
        lay.addWidget(card)
        lay.addWidget(QLabel("Notes (key points you want to remember):"))
        self.p_notes = QPlainTextEdit()
        self.p_notes.setAccessibleName("Practice notes")
        lay.addWidget(self.p_notes, 1)
        crow = QHBoxLayout()
        crow.addWidget(QLabel("How confident were you?"))
        self.p_conf = QSlider(Qt.Orientation.Horizontal)
        self.p_conf.setRange(0, 5)
        self.p_conf.setAccessibleName("Confidence from 0 to 5")
        self.p_conf.setMaximumWidth(220)
        crow.addWidget(self.p_conf)
        self.p_conf_label = QLabel("0/5")
        self.p_conf.valueChanged.connect(lambda v: self.p_conf_label.setText(f"{v}/5"))
        crow.addWidget(self.p_conf_label)
        crow.addStretch(1)
        crow.addWidget(button("Save notes", on_click=self.save_practice))
        crow.addWidget(button("Next question", "primary", on_click=self.next_question))
        lay.addLayout(crow)
        self._round: list[iv.Question] = []
        self._pos = -1
        self._t0 = 0.0
        self._tick = QTimer(self)
        self._tick.setInterval(500)
        self._tick.timeout.connect(self._update_timer)
        return w

    def start_practice(self) -> None:
        if not self.questions:
            self.generate()
        cat = self.practice_cat.currentData()
        self._round = iv.practice_set(self.questions, {cat} if cat else None, self.n_questions.value())
        self._pos = -1
        if not self._round:
            self.p_question.setText("No questions available for this category yet.")
            return
        self.next_question(save=False)

    def next_question(self, save: bool = True) -> None:
        if save and self._pos >= 0 and self.p_notes.toPlainText().strip():
            self.save_practice()
        if not self._round:
            return
        self._pos += 1
        if self._pos >= len(self._round):
            self._tick.stop()
            self.p_question.setText("Round complete. Review your notes in My answers, then start another round.")
            self.p_progress.setText("")
            return
        q = self._round[self._pos]
        self.p_question.setText(q.text)
        self.p_progress.setText(f"Question {self._pos + 1} of {len(self._round)} · {q.category_label}"
                                + (f" · {q.hint}" if q.hint else ""))
        existing = self._answer_for(q.text)
        self.p_notes.setPlainText(existing.data.answer if existing else "")
        self.p_conf.setValue(existing.data.confidence if existing else 0)
        self._t0 = time.monotonic()
        self._tick.start()
        self._update_timer()

    def _update_timer(self) -> None:
        secs = int(time.monotonic() - self._t0) if self._t0 else 0
        self.p_timer.setText(f"{secs // 60:02d}:{secs % 60:02d}")
        lo, hi = iv.STAR_TARGET_SECONDS
        if secs < lo:
            self.p_timer_note.setText(f"Aim for {lo}–{hi} seconds.")
        elif secs <= hi:
            self.p_timer_note.setText("Good length — start wrapping up with the result.")
        elif secs <= 120:
            self.p_timer_note.setText("Getting long; finish with the outcome.")
        else:
            self.p_timer_note.setText("Over two minutes — boards usually want shorter answers.")

    def save_practice(self):
        if not (0 <= self._pos < len(self._round)):
            return None
        q = self._round[self._pos]
        rec = self._answer_for(q.text)
        data = {"question": q.text, "category": q.category, "answer": self.p_notes.toPlainText().strip(),
                "confidence": self.p_conf.value(), "source": q.source, "last_practised": utc_now_iso()}
        if rec is None:
            data["times_practised"] = 1
            rec = self.ctx.repo.create(RecordKind.INTERVIEW_ANSWER, data)
        else:
            data["times_practised"] = rec.data.times_practised + 1
            rec = self.ctx.repo.patch(rec.id, **data)
        self.ctx.invalidate()
        self.ctx.say("Practice notes saved.")
        return rec

    # ------------------------------------------------------------------ stories
    def _build_stories(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.stories = CollectionWidget(self.ctx, [RecordKind.INTERVIEW_STORY], empty_hint=(
            "Prepare five to seven true stories that show different competencies. Write the Action in the first "
            "person; add numbers to the Result only if you can verify them."),
            add_labels={RecordKind.INTERVIEW_STORY: "STAR story"})
        split.addWidget(self.stories)
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.addWidget(QLabel("<b>Story check</b>"))
        self.story_check = QTextBrowser()
        self.story_check.setAccessibleName("STAR story check")
        sl.addWidget(self.story_check, 1)
        split.addWidget(side)
        split.setSizes([800, 300])
        lay.addWidget(split)
        self.stories.editor.saved.connect(lambda _rid: self.check_story())
        self.stories.tree.currentItemChanged.connect(lambda _c, _p: QTimer.singleShot(0, self.check_story))
        return w

    def check_story(self) -> iv.StoryAnalysis | None:
        ed = self.stories.editor
        if ed.form is None or ed.kind != RecordKind.INTERVIEW_STORY:
            self.story_check.setHtml("<p>Select or add a story.</p>")
            return None
        a = iv.analyse_story(ed.form.data())
        rows = "".join(f"<tr><td>{k.title()}</td><td align='right'>{a.words[k]} words</td>"
                       f"<td align='right'>{a.shares[k]:.0%}</td><td align='right'>aim ≈{iv.STAR_SHARES[k]:.0%}</td></tr>"
                       for k in iv.STAR_SHARES)
        html = [f"<p>About <b>{a.seconds} seconds</b> when spoken ({a.total_words} words at "
                f"{iv.SPEAKING_WPM} words a minute).</p><table cellpadding='3'>{rows}</table>",
                f"<p>'I' {a.i_count} · 'we' {a.we_count} (in Task and Action)</p>"]
        if a.issues:
            html.append("<p><b>To improve</b></p><ul>" + "".join(f"<li>{esc(i)}</li>" for i in a.issues) + "</ul>")
        if a.good:
            html.append("<ul>" + "".join(f"<li>{esc(g)}</li>" for g in a.good) + "</ul>")
        if not a.issues:
            html.append("<p>The structure looks good. Practise it aloud.</p>")
        self.story_check.setHtml("".join(html))
        return a

    # ------------------------------------------------------------------ questionnaire
    def _build_questionnaire(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Questionnaire:"))
        self.q_select = QComboBox()
        self.q_select.setAccessibleName("Questionnaire")
        self.q_select.currentIndexChanged.connect(lambda _i: self._load_questionnaire())
        bar.addWidget(self.q_select, 1)
        bar.addWidget(button("New", on_click=self.new_questionnaire))
        bar.addWidget(button("Fill empty sections from profile", on_click=self.fill_from_profile))
        bar.addWidget(button("Check against profile", on_click=self.check_questionnaire))
        bar.addWidget(button("Export copy…", on_click=lambda: self.export_questionnaire()))
        bar.addWidget(button("Save", "primary", on_click=self.save_questionnaire))
        lay.addLayout(bar)
        self.q_status = banner("", "info")
        self.q_status.setVisible(False)
        lay.addWidget(self.q_status)
        split = QSplitter(Qt.Orientation.Horizontal)
        host = QWidget()
        hl = QVBoxLayout(host)
        self.q_form = RecordForm(self.ctx, RecordKind.QUESTIONNAIRE)
        hl.addWidget(self.q_form)
        self.q_tables = {k: RowTable(Questionnaire.model_fields[k].title or k, *v) for k, v in TABLES.items()}
        for t in self.q_tables.values():
            hl.addWidget(t)
        split.addWidget(scroll(host))
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.addWidget(QLabel("<b>Consistency with your profile</b>"))
        self.q_issues = QListWidget()
        self.q_issues.setWordWrap(True)
        self.q_issues.setAccessibleName("Questionnaire consistency issues")
        sl.addWidget(self.q_issues, 1)
        sl.addWidget(muted("Interview boards cross-check these forms against your answers. Keep them consistent "
                           "and leave no section blank."))
        split.addWidget(side)
        split.setSizes([760, 340])
        lay.addWidget(split, 1)
        self.questionnaire_rec = None
        return w

    def _fill_questionnaire_list(self, select_id: str | None = None) -> None:
        recs = self.ctx.repo.list(RecordKind.QUESTIONNAIRE) if self.ctx.has_workspace else []
        self.q_select.blockSignals(True)
        self.q_select.clear()
        for r in recs:
            self.q_select.addItem(r.title or "Questionnaire", r.id)
        if select_id:
            idx = self.q_select.findData(select_id)
            if idx >= 0:
                self.q_select.setCurrentIndex(idx)
        self.q_select.blockSignals(False)
        self._load_questionnaire()

    def _load_questionnaire(self) -> None:
        rid = self.q_select.currentData()
        rec = self.ctx.repo.find(rid) if rid else None
        self.questionnaire_rec = rec
        data = rec.data if rec is not None else Questionnaire()
        self.q_form.set_data(data.model_dump())
        for k, t in self.q_tables.items():
            t.set_rows(getattr(data, k))
        enabled = rec is not None
        self.q_form.setEnabled(enabled)
        for t in self.q_tables.values():
            t.setEnabled(enabled)
        self.q_issues.clear()
        if not enabled:
            self.q_issues.addItem("Create a questionnaire with New. It stays private and is never used in resumes.")

    def _questionnaire_from_ui(self) -> Questionnaire:
        data = self.q_form.data()
        for k, t in self.q_tables.items():
            data[k] = t.rows()
        return Questionnaire.model_validate(data)

    def new_questionnaire(self):
        rec = self.ctx.repo.create(RecordKind.QUESTIONNAIRE, {"title": f"Questionnaire {date.today().year}"})
        self.ctx.invalidate()
        self._fill_questionnaire_list(rec.id)
        return rec

    def save_questionnaire(self) -> bool:
        if self.questionnaire_rec is None:
            return False
        try:
            q = self._questionnaire_from_ui()
        except Exception as exc:  # noqa: BLE001 - validation message for the user
            set_banner(self.q_status, f"Please correct: {str(exc).splitlines()[0][:200]}", "bad")
            self.q_status.setVisible(True)
            return False
        rec = self.ctx.repo.update(self.questionnaire_rec.id, q, expected_revision=self.questionnaire_rec.revision)
        self.questionnaire_rec = rec
        self.ctx.invalidate()
        set_banner(self.q_status, "Questionnaire saved.", "ok")
        self.q_status.setVisible(True)
        self._fill_questionnaire_list(rec.id)
        return True

    def fill_from_profile(self) -> None:
        if self.questionnaire_rec is None:
            info(self, "Questionnaire", "Create a questionnaire first.")
            return
        q = iv.autofill_questionnaire(self._questionnaire_from_ui(), self.ctx.snapshot())
        self.q_form.set_data(q.model_dump())
        for k, t in self.q_tables.items():
            t.set_rows(getattr(q, k))
        set_banner(self.q_status, "Empty sections were filled from your profile. Check them against your "
                                  "certificates, then Save.", "info")
        self.q_status.setVisible(True)

    def check_questionnaire(self) -> list[iv.ConsistencyIssue]:
        if self.questionnaire_rec is None:
            return []
        issues = iv.check_questionnaire(self._questionnaire_from_ui(), self.ctx.snapshot())
        self.q_issues.clear()
        for i in issues:
            it = QListWidgetItem(("⚠ " if i.level == "warn" else "ℹ ") + f"{i.area}: {i.message}")
            self.q_issues.addItem(it)
        if not issues:
            self.q_issues.addItem("✓ No inconsistencies found.")
        return issues

    def export_questionnaire(self, folder: str | None = None) -> None:
        if self.questionnaire_rec is None:
            info(self, "Questionnaire", "Create a questionnaire first.")
            return
        spec = self.ctx.templates.get("government_cv")
        doc = iv.questionnaire_document(self._questionnaire_from_ui(), self.ctx.snapshot(), template_id=spec.id,
                                        template_version=spec.version, is_sample=self.ctx.is_sample)
        self._export(doc, spec, "questionnaire", f"{self.questionnaire_rec.title or 'Questionnaire'} (private)", folder)

    # ------------------------------------------------------------------ export
    def export_pack(self, folder: str | None = None, acknowledge: bool = False) -> None:
        if not self.ctx.has_workspace:
            return
        if not self.questions:
            self.generate()
        snap = self.ctx.snapshot()
        spec = self.ctx.templates.get("ats_minimal")
        qrec = self._questionnaire_record()
        doc = iv.interview_pack(snap, questions=[q for q in self.questions if q.personalised] or self.questions[:30],
                                answers=self.ctx.repo.list(RecordKind.INTERVIEW_ANSWER),
                                stories=self.ctx.repo.list(RecordKind.INTERVIEW_STORY),
                                questionnaire=qrec.data if qrec else None,
                                title=self.vacancy.currentText() if self.vacancy.currentData() else "",
                                template_id=spec.id, template_version=spec.version, is_sample=self.ctx.is_sample)
        self._export(doc, spec, "interview_pack", "Interview preparation pack", folder, acknowledge)

    def _export(self, doc, spec, kind: str, filename: str, folder: str | None, acknowledge: bool = True) -> None:
        from ris.rendering.export import ExportOptions

        if folder is None:
            folder = QFileDialog.getExistingDirectory(self, "Export folder", str(self.ctx.ws.exports_dir))
            if not folder:
                return
        svc = self.ctx.export_service()
        opts = ExportOptions(formats=("docx", "pdf"), folder=Path(folder), pdf_engine=self.ctx.pdf_engine,
                             fit_to_pages=False, acknowledge_warnings=True, filename=filename)

        def done(out) -> None:
            self.last_export = out
            if not out.ok and out.report is None and out.review is not None:
                ReviewDialog(self, self.ctx, out.review).exec()
                return
            from ris.ui.dialogs import report_html

            ReportDialog(self, "Export", "<ul>" + "".join(f"<li>{esc(str(f.path))}</li>" for f in out.files)
                         + "</ul>" + report_html(out.report), out.message, "ok" if out.ok else "bad").exec()

        run_task(lambda: svc.export_document(doc, spec, opts, document_kind=kind), done,
                 lambda m, d: error(self, "Export", m, d))

    # ------------------------------------------------------------------ tips
    def _render_tips(self) -> None:
        bank = iv.load_bank()
        html = []
        for t in bank.tips.values():
            src = bank.sources.get(t.get("source", ""))
            html.append(f"<h3>{esc(t['title'])}</h3><ul>" + "".join(f"<li>{esc(p)}</li>" for p in t["points"])
                        + "</ul>")
            if src:
                html.append(f"<p style='color:gray'>Source: <a href='{esc(src['url'])}'>{esc(src['title'])}</a></p>")
        html.append("<h3>All sources</h3><ul>" + "".join(
            f"<li><a href='{esc(s['url'])}'>{esc(s['title'])}</a></li>" for s in bank.sources.values()) + "</ul>")
        self.tips.setHtml("".join(html))

    # ------------------------------------------------------------------ page lifecycle
    def kinds_of_interest(self) -> set[str]:
        return {"interview_answer", "interview_story", "questionnaire", "vacancy", "position", "project",
                "publication", "education", "skill", "training", "activity", "assignment"}

    def refresh(self) -> None:
        if not self.ctx.has_workspace:
            return
        cur = self.vacancy.currentData()
        self.vacancy.blockSignals(True)
        self.vacancy.clear()
        self.vacancy.addItem("(no vacancy)", "")
        for v in self.ctx.repo.list(RecordKind.VACANCY):
            self.vacancy.addItem(v.title or "Vacancy", v.id)
        idx = self.vacancy.findData(cur)
        self.vacancy.setCurrentIndex(max(0, idx))
        self.vacancy.blockSignals(False)
        self.answers.reload()
        self.stories.reload()
        self._fill_questionnaire_list(self.questionnaire_rec.id if self.questionnaire_rec else None)
        self.generate()

    def has_unsaved_changes(self) -> bool:
        return self.answers.editor.is_dirty() or self.stories.editor.is_dirty()

    def maybe_save(self) -> bool:
        return self.answers.editor.maybe_save() and self.stories.editor.maybe_save()

