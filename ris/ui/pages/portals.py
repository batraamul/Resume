"""Job Portals & Recruiters: recruiter directory, portal guidance, profile kit and ATS readiness."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ris.composition.modes import get_mode
from ris.domain.enums import RecordKind
from ris.intelligence import portal_kit as pk
from ris.intelligence.ats import ATSCheck, ats_readiness
from ris.resources import config_dir
from ris.strings import PAGE_SUBTITLES
from ris.ui.widgets.common import Page, banner, button, error, esc, info, muted

DIRECTORY_NOTE = ("Recruitment routes and documents are orientation summaries from the sources shown. Rules change: "
                  "always follow the actual notification and the organisation's official website.")
STATUS_ICON = {"pass": "✓", "warn": "⚠", "fail": "✗", "ok": "✓", "over": "✗"}


def load_recruiters() -> dict:
    return json.loads((config_dir() / "recruiters.json").read_text(encoding="utf-8"))


def _sources_html(sources: list[dict]) -> str:
    if not sources:
        return ""
    return ("<p style='color:gray'>Sources: " + "; ".join(
        f"<a href='{esc(s['url'])}'>{esc(s['title'])}</a>" for s in sources) + "</p>")


class PortalsPage(Page):
    key = "portals"

    def __init__(self, ctx) -> None:
        super().__init__(ctx, "Job Portals & Recruiters", PAGE_SUBTITLES["portals"], scrollable=False)
        self.directory = load_recruiters()
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName("Job portal and recruiter sections")
        self.tabs.addTab(self._build_recruiters(), "Recruiters")
        self.tabs.addTab(self._build_portals(), "Job portals")
        self.tabs.addTab(self._build_kit(), "Profile kit")
        self.tabs.addTab(self._build_ats(), "ATS check")
        self.trends = QTextBrowser()
        self.trends.setOpenExternalLinks(True)
        self.trends.setAccessibleName("Recruitment trends")
        self.tabs.addTab(self.trends, "Trends")
        self.body.addWidget(self.tabs, 1)
        self._render_trends()

    # ------------------------------------------------------------------ recruiters
    def _build_recruiters(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(banner(DIRECTORY_NOTE, "info"))
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Category:"))
        self.rec_cat = QComboBox()
        self.rec_cat.setAccessibleName("Recruiter category")
        self.rec_cat.addItem("All", "")
        for c in self.directory.get("categories", []):
            self.rec_cat.addItem(c, c)
        self.rec_cat.currentIndexChanged.connect(lambda _i: self._fill_recruiters())
        bar.addWidget(self.rec_cat)
        bar.addStretch(1)
        lay.addLayout(bar)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.rec_list = QListWidget()
        self.rec_list.setAccessibleName("Recruiters")
        self.rec_list.currentItemChanged.connect(lambda c, _p: self._show_recruiter(c))
        split.addWidget(self.rec_list)
        right = QWidget()
        rl = QVBoxLayout(right)
        self.rec_view = QTextBrowser()
        self.rec_view.setOpenExternalLinks(True)
        self.rec_view.setAccessibleName("Recruiter details")
        rl.addWidget(self.rec_view, 1)
        row = QHBoxLayout()
        self.b_site = button("Open official website", on_click=self._open_site)
        self.b_target = button("Create a career target", "primary", on_click=self._make_target)
        row.addWidget(self.b_site)
        row.addStretch(1)
        self.b_format = button("Create resume in this format ▾", on_click=None,
                               tooltip="Start a resume in a format that suits this recruiter")
        from PySide6.QtWidgets import QMenu

        self.b_format.setMenu(QMenu(self.b_format))
        row.addWidget(self.b_format)
        row.addWidget(self.b_target)
        rl.addLayout(row)
        split.addWidget(right)
        split.setSizes([330, 650])
        lay.addWidget(split, 1)
        self._fill_recruiters()
        return w

    def _fill_recruiters(self) -> None:
        cat = self.rec_cat.currentData()
        self.rec_list.clear()
        for r in self.directory["recruiters"]:
            if cat and r["category"] != cat:
                continue
            it = QListWidgetItem(r["name"])
            it.setData(Qt.ItemDataRole.UserRole, r)
            it.setToolTip(r["category"])
            self.rec_list.addItem(it)
        if self.rec_list.count():
            self.rec_list.setCurrentRow(0)

    def _current_recruiter(self) -> dict | None:
        it = self.rec_list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _show_recruiter(self, item) -> None:
        if item is None:
            return
        r = item.data(Qt.ItemDataRole.UserRole)

        def lst(title: str, items: list[str]) -> str:
            return f"<h3>{esc(title)}</h3><ul>" + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ul>" if items else ""

        site = (f"<p><a href='{esc(r['website'])}'>{esc(r['website'])}</a>"
                + (f" · careers: <a href='{esc(r['careers'])}'>{esc(r['careers'])}</a>"
                   if r.get("careers") and r["careers"] != r["website"] else "") + "</p>") if r.get("website") else \
            "<p><i>No public recruitment website; watch official advertisements.</i></p>"
        self.rec_view.setHtml(
            f"<h2>{esc(r['name'])}</h2><p><i>{esc(r['category'])}</i></p>{site}"
            + lst("Recruitment routes", r.get("routes", []))
            + lst("Where vacancies are advertised", r.get("advertised_in", []))
            + lst("Documents usually asked for", r.get("documents", []))
            + lst("What interviews tend to focus on", r.get("interview_focus", []))
            + lst("Document formats that suit each route", [
                f"{f['route']}: {get_mode(f['mode']).name}" for f in r.get("formats", [])])
            + _sources_html(r.get("sources", [])))
        self.b_site.setEnabled(bool(r.get("website")))
        menu = self.b_format.menu()
        menu.clear()
        for f in r.get("formats", []):
            menu.addAction(f"{f['route']} — {get_mode(f['mode']).name}",
                           lambda f=f, r=r: self.create_resume_in_format(r, f))
        self.b_format.setEnabled(bool(r.get("formats")))
        self.b_target.setEnabled(bool(r.get("org_profile")) and self.ctx.presets.org(r["org_profile"]) is not None)

    def create_resume_in_format(self, r: dict, f: dict):
        m = get_mode(f["mode"])
        rec = self.ctx.repo.create(RecordKind.VARIANT, {
            "name": f"{r['name']} — {f['route']}", "mode": m.id, "template_id": f.get("template") or m.default_template,
            "length": m.default_length.value})
        self.ctx.invalidate()
        self.ctx.say(f"Resume created in the {m.name} format. Link the vacancy in Resume Studio when you apply.")
        self.ctx.navigate.emit("studio", rec.id)
        return rec

    def _open_site(self) -> None:
        r = self._current_recruiter()
        if r and r.get("website"):
            QDesktopServices.openUrl(QUrl(r.get("careers") or r["website"]))

    def _make_target(self):
        r = self._current_recruiter()
        if not r or not r.get("org_profile"):
            return None
        o = self.ctx.presets.org(r["org_profile"])
        if o is None:
            return None
        p = self.ctx.presets.preset(o.suggested_presets[0]) if o.suggested_presets else None
        data = {"name": r["name"], "org_profile_id": o.id, "organisation": r["name"], "sector": o.parent,
                "description": o.notes, "keywords": list(dict.fromkeys(list(o.domains) + (list(p.keywords) if p else []))),
                "emphasis_areas": list(p.emphasis) if p else []}
        if p:
            data.update({"preset_id": p.id, "preferred_mode": p.mode, "preferred_template": p.template,
                         "summary_focus": p.summary_focus})
        rec = self.ctx.repo.create(RecordKind.CAREER_TARGET, data)
        self.ctx.invalidate()
        self.ctx.say(f"Career target created for {r['name']}.")
        self.ctx.navigate.emit("record", rec.id)
        return rec

    # ------------------------------------------------------------------ portals
    def _build_portals(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.portal_list = QListWidget()
        self.portal_list.setAccessibleName("Job portals")
        data = pk.load_portals()
        for p in data["portals"]:
            it = QListWidgetItem(p["name"])
            it.setData(Qt.ItemDataRole.UserRole, ("portal", p))
            self.portal_list.addItem(it)
        it = QListWidgetItem("Research and profile sites")
        it.setData(Qt.ItemDataRole.UserRole, ("sites", data["profile_sites"]))
        self.portal_list.addItem(it)
        it = QListWidgetItem("Resume file practice")
        it.setData(Qt.ItemDataRole.UserRole, ("files", data["file_practices"]))
        self.portal_list.addItem(it)
        self.portal_list.currentItemChanged.connect(lambda c, _p: self._show_portal(c))
        split.addWidget(self.portal_list)
        self.portal_view = QTextBrowser()
        self.portal_view.setOpenExternalLinks(True)
        self.portal_view.setAccessibleName("Portal details")
        split.addWidget(self.portal_view)
        split.setSizes([300, 680])
        lay.addWidget(split)
        self.portal_list.setCurrentRow(0)
        return w

    def _show_portal(self, item) -> None:
        if item is None:
            return
        kind, p = item.data(Qt.ItemDataRole.UserRole)
        if kind == "sites":
            self.portal_view.setHtml(
                "<h2>Research and profile sites</h2><p>Add these in Master Profile → Online profiles; choose which "
                "appear on each resume in Resume Studio.</p><ul>" + "".join(
                    f"<li><b><a href='{esc(s['url'])}'>{esc(s['name'])}</a></b> — {esc(s['use'])}</li>" for s in p)
                + "</ul>")
            return
        if kind == "files":
            self.portal_view.setHtml("<h2>Resume file practice</h2><ul>" + "".join(
                f"<li>{esc(a)}</li>" for a in p["advice"]) + "</ul>" + _sources_html(p.get("sources", [])))
            return
        fields = "".join(
            f"<tr><td>{esc(f['label'])}</td><td>" + (
                f"{f['limit']} {'characters' if f['id'] not in ('key_skills', 'skills') else 'items'}"
                f"{' (recommended)' if f.get('kind') == 'advice' else ''}" if f.get("limit") else
                (f"{f['limit_words'][0]}–{f['limit_words'][1]} words (recommended)" if f.get("limit_words") else "—"))
            + f"</td><td>{esc(f.get('note', ''))}</td></tr>" for f in p.get("fields", []))
        formats = ", ".join(p.get("resume_formats") or []) or "—"
        size = f"{p['resume_max_mb']} MB" if p.get("resume_max_mb") else "not stated"
        self.portal_view.setHtml(
            f"<h2><a href='{esc(p['url'])}'>{esc(p['name'])}</a></h2><p><b>Best for:</b> {esc(p['best_for'])}</p>"
            f"<p><b>Resume files:</b> {esc(formats)} · maximum size {esc(size)}</p>"
            + (f"<h3>Profile fields</h3><table cellpadding='4' border='0'><tr><th align='left'>Field</th>"
               f"<th align='left'>Limit</th><th align='left'>Note</th></tr>{fields}</table>" if fields else "")
            + ("<h3>Tips</h3><ul>" + "".join(f"<li>{esc(t)}</li>" for t in p.get("tips", [])) + "</ul>"
               if p.get("tips") else "")
            + _sources_html(p.get("sources", [])))

    # ------------------------------------------------------------------ profile kit
    def _build_kit(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(muted("Text built only from facts you confirmed and approved for professional use. Edit it here "
                            "before copying — edits are not saved to your profile."))
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Emphasise for vacancy:"))
        self.kit_vacancy = QComboBox()
        self.kit_vacancy.setAccessibleName("Vacancy to emphasise")
        bar.addWidget(self.kit_vacancy, 1)
        bar.addWidget(button("Build", "primary", on_click=self.build_kit))
        bar.addWidget(button("Save all as text…", on_click=lambda: self.save_kit()))
        lay.addLayout(bar)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.kit_tree = QTreeWidget()
        self.kit_tree.setHeaderLabels(["Field", "Status"])
        self.kit_tree.setAccessibleName("Profile kit fields")
        self.kit_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.kit_tree.currentItemChanged.connect(lambda c, _p: self._show_field(c))
        split.addWidget(self.kit_tree)
        right = QWidget()
        rl = QVBoxLayout(right)
        self.kit_text = QPlainTextEdit()
        self.kit_text.setAccessibleName("Field text")
        self.kit_text.textChanged.connect(self._recount)
        rl.addWidget(self.kit_text, 1)
        row = QHBoxLayout()
        self.kit_count = muted("")
        row.addWidget(self.kit_count, 1)
        row.addWidget(button("Copy", "primary", on_click=self.copy_field))
        rl.addLayout(row)
        split.addWidget(right)
        split.setSizes([380, 600])
        lay.addWidget(split, 1)
        self.kit: dict[str, list[pk.KitField]] = {}
        self._field: pk.KitField | None = None
        return w

    def build_kit(self) -> dict:
        if not self.ctx.has_workspace:
            return {}
        snap = self.ctx.snapshot()
        relevance = None
        vid = self.kit_vacancy.currentData()
        if vid:
            from ris.intelligence.analysis import analyse

            vac = self.ctx.repo.find(vid)
            if vac is not None:
                relevance = analyse(snap, vac.data, today=self.ctx.today).relevance
        self.kit = pk.build_kit(snap, relevance=relevance, today=self.ctx.today)
        names = {p["id"]: p["name"] for p in pk.load_portals()["portals"]}
        self.kit_tree.clear()
        first = None
        for pid, fields in self.kit.items():
            top = QTreeWidgetItem([names.get(pid, pid), ""])
            self.kit_tree.addTopLevelItem(top)
            for f in fields:
                level, msg = f.status()
                it = QTreeWidgetItem([f.label, f"{STATUS_ICON.get(level, '')} {msg}"])
                it.setData(0, Qt.ItemDataRole.UserRole, f)
                it.setToolTip(1, msg)
                top.addChild(it)
                first = first or it
            top.setExpanded(True)
        if first is not None:
            self.kit_tree.setCurrentItem(first)
        return self.kit

    def _show_field(self, item) -> None:
        f = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        self._field = f
        self.kit_text.blockSignals(True)
        self.kit_text.setPlainText(f.value if f else "")
        self.kit_text.blockSignals(False)
        self._recount()

    def _recount(self) -> None:
        f = self._field
        if f is None:
            self.kit_count.setText("")
            return
        text = self.kit_text.toPlainText()
        tmp = pk.KitField(f.portal, f.field_id, f.label, text=text if not f.items else "",
                          items=[x for x in text.splitlines() if x.strip()] if f.items else [], limit=f.limit,
                          limit_kind=f.limit_kind, limit_words=f.limit_words)
        level, msg = tmp.status()
        self.kit_count.setText(f"{STATUS_ICON.get(level, '')} {msg}" + (f"  ·  {f.note}" if f.note else ""))

    def copy_field(self) -> None:
        QGuiApplication.clipboard().setText(self.kit_text.toPlainText())
        self.ctx.say("Copied to the clipboard.")

    def save_kit(self, path: str | None = None) -> Path | None:
        if not self.kit:
            self.build_kit()
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Save profile kit", str(self.ctx.ws.exports_dir /
                                                                              "Profile kit.txt"), "Text (*.txt)")
            if not path:
                return None
        out = Path(path)
        out.write_text(pk.kit_as_text(self.kit), encoding="utf-8")
        self.ctx.say(f"Profile kit saved to {out.name}.")
        return out

    # ------------------------------------------------------------------ ATS check
    def _build_ats(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(muted("Checks a resume against published applicant-tracking-system guidance and portal file "
                            "rules. Graphical templates are for people; use ATS Minimal for online portals."))
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Resume:"))
        self.ats_variant = QComboBox()
        self.ats_variant.setAccessibleName("Resume variant to check")
        bar.addWidget(self.ats_variant, 1)
        bar.addWidget(button("Check resume", "primary", on_click=self.check_variant))
        bar.addWidget(button("Check an exported file…", on_click=lambda: self.check_file()))
        lay.addLayout(bar)
        self.ats_score = QLabel("")
        self.ats_score.setObjectName("SectionTitle")
        self.ats_score.setAccessibleName("ATS readiness score")
        lay.addWidget(self.ats_score)
        self.ats_tree = QTreeWidget()
        self.ats_tree.setHeaderLabels(["", "Check", "Result"])
        self.ats_tree.setAccessibleName("ATS checks")
        self.ats_tree.setRootIsDecorated(False)
        self.ats_tree.setWordWrap(True)
        self.ats_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.ats_tree.setColumnWidth(0, 30)
        self.ats_tree.setColumnWidth(1, 280)
        lay.addWidget(self.ats_tree, 1)
        self.ats_sources = QLabel("")
        self.ats_sources.setOpenExternalLinks(True)
        self.ats_sources.setWordWrap(True)
        lay.addWidget(self.ats_sources)
        return w

    def check_variant(self):
        vid = self.ats_variant.currentData()
        if not vid:
            info(self, "ATS check", "Create a resume in Resume Studio first.")
            return None
        try:
            comp = self.ctx.export_service().compose_record(vid)
        except Exception as exc:  # noqa: BLE001 - shown to the user
            error(self, "ATS check", getattr(exc, "user_message", "The resume could not be composed."), str(exc))
            return None
        rel = comp.analysis.relevance if comp.analysis else None
        rep = ats_readiness(comp.doc, comp.spec, rel)
        self._show_ats(rep.checks, f"ATS readiness: {rep.score}/100 — {comp.spec.name}")
        return rep

    def check_file(self, path: str | None = None):
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Choose a resume file", str(self.ctx.ws.exports_dir),
                                                  "Resumes (*.pdf *.docx *.doc *.rtf)")
            if not path:
                return None
        checks = pk.check_file(Path(path))
        rows = [ATSCheck(f"file{i}", Path(path).name, {"ok": "pass"}.get(c.level, c.level), c.message,
                         {"title": "Resume PDF vs Word (Jobrise)", "url": "https://jobrise.io/blog/resume-pdf-vs-word-format"})
                for i, c in enumerate(checks)]
        self._show_ats(rows, f"File check — {Path(path).name}")
        name = self.ctx.snapshot().personal_data.full_name
        if name:
            self.ats_sources.setText(f"Suggested file name: <b>{esc(pk.suggested_filename(name, Path(path).suffix))}"
                                     "</b>")
        return checks

    def _show_ats(self, checks, title: str) -> None:
        self.ats_score.setText(title)
        self.ats_tree.clear()
        sources = {}
        for c in checks:
            it = QTreeWidgetItem([STATUS_ICON.get(c.status, ""), c.title, c.detail])
            it.setToolTip(2, c.detail)
            self.ats_tree.addTopLevelItem(it)
            if c.source:
                sources[c.source["url"]] = c.source["title"]
        self.ats_sources.setText("Sources: " + "; ".join(f"<a href='{esc(u)}'>{esc(t)}</a>"
                                                         for u, t in sources.items()) if sources else "")

    # ------------------------------------------------------------------ trends
    def _render_trends(self) -> None:
        items = self.directory.get("trends", [])
        self.trends.setHtml("<h2>Recruitment trends</h2><ul>" + "".join(
            f"<li>{esc(t['text'])}<br><span style='color:gray'>Source: <a href='{esc(t['source']['url'])}'>"
            f"{esc(t['source']['title'])}</a></span></li>" for t in items)
            + f"</ul><p style='color:gray'>Checked {esc(self.directory.get('checked', ''))}.</p>")

    # ------------------------------------------------------------------ lifecycle
    def kinds_of_interest(self) -> set[str]:
        return {"variant", "vacancy", "personal", "summary", "position", "bullet", "skill", "expertise", "training"}

    def refresh(self) -> None:
        if not self.ctx.has_workspace:
            return
        for cb, kind, empty in ((self.kit_vacancy, RecordKind.VACANCY, "(no vacancy)"),
                                (self.ats_variant, RecordKind.VARIANT, None)):
            cur = cb.currentData()
            cb.blockSignals(True)
            cb.clear()
            if empty:
                cb.addItem(empty, "")
            for r in self.ctx.repo.list(kind):
                cb.addItem(r.title or kind.value, r.id)
            idx = cb.findData(cur)
            cb.setCurrentIndex(max(0, idx))
            cb.blockSignals(False)
