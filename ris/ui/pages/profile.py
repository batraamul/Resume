"""Master profile and the profile collection pages."""

from __future__ import annotations

from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from ris.domain.enums import RecordKind
from ris.services.completeness import compute
from ris.strings import PAGE_SUBTITLES
from ris.ui.importing import export_profile_json, import_profile_file
from ris.ui.widgets.common import Page, banner, button, set_banner
from ris.ui.widgets.records import CollectionWidget, RecordEditor


class CollectionPage(Page):
    """One profile section (Experience, Education, …)."""

    def __init__(self, ctx, key: str, title: str, kinds: list[RecordKind], *, empty_hint: str = "",
                 add_labels: dict | None = None) -> None:
        super().__init__(ctx, title, PAGE_SUBTITLES.get(key, ""), scrollable=False)
        self.key = key
        self.collection = CollectionWidget(ctx, kinds, empty_hint=empty_hint, add_labels=add_labels)
        self.body.addWidget(self.collection, 1)

    def kinds_of_interest(self) -> set[str]:
        return self.collection.all_kinds()

    def refresh(self) -> None:
        ed = self.collection.editor
        if not ed.is_dirty():
            # Rebuild forms so reference lists (projects, positions, templates) are current.
            rid = ed.record.id if ed.record else None
            ed.reset_forms()
            ed.set_record(self.ctx.repo.find(rid) if rid else None)
        self.collection.reload()

    def focus_record(self, record_id: str) -> bool:
        return self.collection.focus_record(record_id)

    def has_unsaved_changes(self) -> bool:
        return self.collection.editor.is_dirty()

    def maybe_save(self) -> bool:
        return self.collection.editor.maybe_save()


class ProfilePage(Page):
    key = "profile"

    def __init__(self, ctx) -> None:
        super().__init__(ctx, "Master Profile", PAGE_SUBTITLES["profile"], scrollable=False)
        self.header.add_action(button("Import…", tooltip="Import a profile JSON, spreadsheet or existing CV",
                                      on_click=self._import))
        self.header.add_action(button("Export profile (JSON)…", on_click=lambda: export_profile_json(self, ctx)))
        self.completeness = banner("", "info")
        self.body.addWidget(self.completeness)
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName("Profile sections")
        personal = QWidget()
        pl = QVBoxLayout(personal)
        self.personal = RecordEditor(ctx)
        self.personal.saved.connect(lambda _rid: self.mark_dirty())
        pl.addWidget(self.personal)
        self.tabs.addTab(personal, "Personal && contact")
        self.summaries = CollectionWidget(ctx, [RecordKind.SUMMARY], empty_hint=(
            "Add one or more summaries for different audiences (defence R&D, academic, technical). "
            "'Draft from confirmed facts' writes a factual starting point."))
        self.tabs.addTab(self.summaries, "Professional summaries")
        self.expertise = CollectionWidget(ctx, [RecordKind.EXPERTISE], empty_hint=(
            "Areas of expertise are broad domains with a short factual narrative, for example 'R&D in avionics' — "
            "shown as a two-column table in graphical and executive resumes."),
            add_labels={RecordKind.EXPERTISE: "area of expertise"})
        self.tabs.addTab(self.expertise, "Areas of expertise")
        self.references = CollectionWidget(ctx, [RecordKind.REFERENCE], empty_hint=(
            "Referees are included only after you tick 'This person has agreed to be named as a referee'."),
            add_labels={RecordKind.REFERENCE: "referee"})
        self.tabs.addTab(self.references, "Referees")
        self.custom = CollectionWidget(ctx, [RecordKind.CUSTOM_SECTION], empty_hint=(
            "Custom sections hold anything the standard sections do not cover, for example 'Field campaigns'."))
        self.tabs.addTab(self.custom, "Custom sections")
        self.body.addWidget(self.tabs, 1)

    def kinds_of_interest(self) -> set[str]:
        return {"personal", "summary", "custom_section", "custom_entry", "position", "education", "skill",
                "publication", "project", "activity", "bullet", "expertise", "reference"}

    def refresh(self) -> None:
        prof = self.ctx.profile()
        rec = self.ctx.repo.singleton(RecordKind.PERSONAL) or prof.ensure_personal()
        if not self.personal.is_dirty():
            self.personal.set_record(rec)
        for col in (self.summaries, self.expertise, self.references, self.custom):
            if not col.editor.is_dirty():
                rid = col.editor.record.id if col.editor.record else None
                col.editor.reset_forms()
                col.editor.set_record(self.ctx.repo.find(rid) if rid else None)
            col.reload()
        c = compute(self.ctx.snapshot())
        actions = c.top_actions(3)
        set_banner(self.completeness, f"Profile completeness: {c.overall}%." + (
            " Next: " + " · ".join(actions) if actions else " Every section has the essentials."),
                   "ok" if c.overall >= 80 else "info")

    def _import(self) -> None:
        if import_profile_file(self, self.ctx):
            self.mark_dirty()

    def focus_record(self, record_id: str) -> bool:
        rec = self.ctx.repo.find(record_id)
        if rec is None:
            return False
        if rec.kind == RecordKind.PERSONAL:
            self.tabs.setCurrentIndex(0)
            return True
        for col in (self.summaries, self.expertise, self.references, self.custom):
            if rec.kind.value in col.all_kinds():
                self.tabs.setCurrentWidget(col)
                return col.focus_record(record_id)
        return False

    def _editors(self):
        return (self.personal, self.summaries.editor, self.expertise.editor, self.references.editor, self.custom.editor)

    def has_unsaved_changes(self) -> bool:
        return any(e.is_dirty() for e in self._editors())

    def maybe_save(self) -> bool:
        return all(e.maybe_save() for e in self._editors())


SECTION_PAGES: list[tuple[str, str, list[RecordKind], str, dict]] = [
    ("experience", "Experience", [RecordKind.POSITION],
     "Add each position. Concurrent responsibilities (additional charge, in-charge, nodal officer) and the "
     "statements describing your work are added as linked items.", {RecordKind.POSITION: "position"}),
    ("education", "Education", [RecordKind.EDUCATION],
     "Add degrees and diplomas, including ongoing or planned study. Planned items are never shown as "
     "completed. Training, courses and certifications have their own page.", {RecordKind.EDUCATION: "qualification"}),
    ("training", "Training & Certifications", [RecordKind.TRAINING],
     "Add training programmes, professional and online courses, certifications and licences, workshops, seminars "
     "and other qualifications. Each type appears in its own resume section; certification expiry dates are "
     "tracked.", {RecordKind.TRAINING: "training or certification"}),
    ("research", "Research & Publications", [RecordKind.PUBLICATION],
     "Add publications and manuscripts with their exact status (in preparation, submitted, under review, "
     "accepted, published).", {RecordKind.PUBLICATION: "publication"}),
    ("skills", "Skills & Technologies", [RecordKind.SKILL],
     "Add only skills you want to claim. Proficiency is your own assessment; link projects as evidence.",
     {RecordKind.SKILL: "skill"}),
    ("projects", "Projects & Achievements", [RecordKind.PROJECT],
     "Describe problem, approach, results and your individual contribution. Classify sensitive projects as "
     "Confidential — they are never exported.", {RecordKind.PROJECT: "project"}),
    ("leadership", "Leadership & Responsibilities", [RecordKind.ACTIVITY],
     "Committees, laboratory or workshop management, mentoring, reviews, awards, memberships, patents and talks.",
     {RecordKind.ACTIVITY: "activity"}),
]
