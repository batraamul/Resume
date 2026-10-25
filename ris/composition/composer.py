"""Resume composer: profile snapshot + variant settings → ResumeDocument (IR).

Rules enforced here (see requirements PRF-03/07/08/09, PRV-01/04, DEF-05):
* Confidential records (or children of confidential records) never enter the IR.
* Redacted variants contain Public items only.
* Private personal particulars appear only when the variant explicitly opts in.
* Concurrent responsibilities are nested under their parent position.
* Ongoing/planned qualifications are labelled; planned ones are hidden by default.
* Publications are worded strictly by status; unpublished work is listed separately.
* Only *approved* claim rewrites replace original wording.
* Every bullet and entry carries its source record ids; used revisions are recorded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from ris import __version__
from ris.composition.ir import (
    ContactItem,
    IRBullet,
    IRChart,
    IRChartPoint,
    IREntry,
    IRSection,
    IRSkillGroup,
    IRTable,
    IRTile,
    ResumeDocument,
)
from ris.composition.modes import BUDGETS, ResumeMode, get_mode
from ris.composition.ordering import resolve_order
from ris.domain import dates
from ris.domain.enums import (
    ActivityType,
    AssignmentType,
    ClaimStatus,
    Confidentiality,
    EducationStatus,
    ProjectStatus,
    PublicationStatus,
    PublicationType,
    QualificationType,
    RecordKind,
    ResumeLength,
    SkillCategory,
    SummaryFocus,
    TrainingMode,
    Verification,
    label,
)
from ris.domain.models import Vacancy, Variant
from ris.intelligence.relevance import RelevanceModel
from ris.intelligence.text import first_sentence
from ris.services.profile import ProfileSnapshot
from ris.storage.repository import Record
from ris.util import utc_now_iso

PROFICIENCY_RANK = {"expert": 5, "advanced": 4, "proficient": 3, "working": 2, "familiar": 1, "not_rated": 0}
LEADERSHIP_TYPES = {
    ActivityType.LEADERSHIP, ActivityType.COMMITTEE, ActivityType.WORKSHOP_MANAGEMENT,
    ActivityType.PROJECT_COORDINATION, ActivityType.TECHNICAL_REVIEW, ActivityType.PROCUREMENT,
    ActivityType.MENTORING, ActivityType.TRAINING_DELIVERED,
}
OTHER_ACTIVITY_TYPES = {ActivityType.TECHNICAL_WRITING, ActivityType.OUTREACH, ActivityType.OTHER}
SERVICE_TYPES = {ActivityType.PEER_REVIEW, ActivityType.CONFERENCE_ORGANISATION, ActivityType.SUPERVISION}
JOURNAL_TYPES = {PublicationType.JOURNAL.value}
CONFERENCE_TYPES = {PublicationType.CONFERENCE.value, PublicationType.POSTER.value}
FACET_FIELDS = (("problem", "Challenge"), ("approach", "Approach"), ("results", "Outcome"),
                ("individual_contribution", "My contribution"))


LINK_LABELS = {"linkedin": "LinkedIn", "github": "GitHub", "website": "Website", "portfolio": "Portfolio",
               "google_scholar": "Google Scholar", "researchgate": "ResearchGate", "naukri": "Naukri",
               "indeed": "Indeed"}
NAMED_LINKS = {"google_scholar", "researchgate", "naukri", "indeed"}


def short_org(name: str) -> str:
    """Compact organisation label for charts: an acronym in parentheses, a short name, or initials."""
    name = (name or "").strip()
    if len(name) <= 16:
        return name
    m = re.search(r"\(([A-Z][A-Za-z&.\- ]{1,14})\)", name)
    if m:
        return m.group(1).strip()
    words = [w for w in re.split(r"[\s,]+", name) if w and w[0].isupper() and w.lower() not in ("of", "and", "the")]
    initials = "".join(w[0] for w in words)
    return initials if 2 <= len(initials) <= 6 else name[:16].rstrip() + "…"


#: Dedicated training sections and the training types each one shows.
TRAINING_SECTIONS: dict[str, set[str]] = {
    "training_programmes": {"training_programme", "mandatory_training", "faculty_development"},
    "courses": {"professional_course", "online_course"},
    "certifications": {"certification", "licence", "language_test"},
    "workshops": {"workshop", "seminar"},
    "other_qualifications": {"other_qualification"},
}
#: Older profiles kept training in Education records; they are shown in the matching dedicated section.
LEGACY_EDUCATION_SECTION = {"certification": "certifications", "training": "training_programmes",
                            "course": "courses", "examination": "other_qualifications"}
TRAINING_TYPES = {QualificationType.CERTIFICATION, QualificationType.TRAINING, QualificationType.COURSE,
                  QualificationType.EXAMINATION}
PRIVATE_LABELS = {
    "date_of_birth": "Date of birth",
    "date_of_entry_into_service": "Date of entry into service",
    "present_pay_level": "Present pay level",
    "nature_of_employment": "Nature of present employment",
    "nationality": "Nationality",
    "home_address": "Address for correspondence",
}
#: Deputation-proforma particulars: printed only in the proforma, and only when the resume opts in.
PROFORMA_PARTICULARS = {
    "date_of_retirement": "Date of retirement",
    "employer_type": "Type of present employer",
    "present_deputation_details": "Present deputation / contract details",
    "past_deputation_details": "Previous deputation(s)",
    "feeder_grade_status": "Feeder grade status",
    "pay_revision_details": "Revised pay scale details",
    "basic_pay": "Basic pay",
    "total_emoluments": "Total emoluments",
    "non_central_pay_details": "Pay details (non-Central pay scales)",
    "sc_st_status": "Whether belongs to SC / ST",
}
DATE_PARTICULARS = {"date_of_birth", "date_of_entry_into_service", "date_of_retirement"}
#: Wording of the candidate's declaration in the DoPT bio-data proforma (OM dated 02.07.2015).
PROFORMA_DECLARATION = (
    "I have carefully gone through the vacancy circular / advertisement and I am well aware that the information "
    "furnished in the Curriculum Vitae duly supported by the documents in respect of Essential Qualification / Work "
    "Experience submitted by me will also be assessed by the Selection Committee at the time of selection for the "
    "post. The information / details provided by me are correct and true to the best of my knowledge and no material "
    "fact having a bearing on my selection has been suppressed / withheld."
)
BASIS_FROM_MODE = {"deputation": "Deputation", "absorption": "Absorption", "contract": "Short-term contract"}
GENERIC_CATEGORIES = {SkillCategory.OTHER.value, SkillCategory.LANGUAGES.value}


@dataclass
class ComposeContext:
    snapshot: ProfileSnapshot
    variant: Variant
    template_id: str = ""
    template_version: str = ""
    date_style: str = "mon_year"
    photo_allowed: bool = False
    relevance: RelevanceModel = field(default_factory=RelevanceModel.empty)
    approved_claims: dict[str, Record] = field(default_factory=dict)  # bullet id → approved claim record
    requirements_matrix: list[tuple[str, str, list[str]]] | None = None  # (required, possessed, source ids)
    emphasis: dict[str, float] = field(default_factory=dict)
    target: Record | None = None
    vacancy_title: str = ""
    vacancy: Vacancy | None = None
    mandatory_gaps: list[str] = field(default_factory=list)
    is_sample: bool = False
    today: date = field(default_factory=date.today)


def _duration_text(hours: float | None, days: float | None) -> str:
    def fmt(v: float) -> str:
        return str(int(v)) if float(v).is_integer() else f"{v:g}"
    parts = []
    if days:
        parts.append(f"{fmt(days)} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{fmt(hours)} hour{'s' if hours != 1 else ''}")
    return " / ".join(parts)


def _bio_date(text: str) -> str:
    """Bio-data style date: MM/YYYY when the month is known, else the year."""
    pd = dates.parse_or_none(text)
    if pd is None:
        return ""
    return pd.format("mm_yyyy") if pd.month else str(pd.year)


def claims_by_bullet(claim_records: list[Record]) -> dict[str, Record]:
    """Approved claims keyed by the bullet they replace (latest approval wins)."""
    out: dict[str, Record] = {}
    for c in sorted(claim_records, key=lambda r: (r.data.approved_at or "", r.id)):
        d = c.data
        if d.status == ClaimStatus.APPROVED.value and d.approved_text and d.target_bullet_id:
            out[d.target_bullet_id] = c
    return out


class ResumeComposer:
    def __init__(self, ctx: ComposeContext) -> None:
        self.ctx = ctx
        self.snap = ctx.snapshot
        self.v = ctx.variant
        self.mode: ResumeMode = get_mode(self.v.mode)
        self.length = ResumeLength(self.v.length)
        self.budget = BUDGETS[self.length]
        self.rel = ctx.relevance
        self.used: dict[str, int] = {}
        self.trimmed: list[str] = []
        self.warnings: list[str] = []
        self.include_ids = set(self.v.include_ids)
        self.exclude_ids = set(self.v.exclude_ids)
        self.order: list[str] = []

    # ------------------------------------------------------------------ eligibility & tracking
    def eligible(self, rec: Record) -> bool:
        if rec.id in self.exclude_ids:
            return False
        conf = self.snap.effective_confidentiality(rec)
        if conf == Confidentiality.CONFIDENTIAL:
            return False
        return not (self.v.redacted and conf != Confidentiality.PUBLIC)

    def _use(self, rec: Record) -> None:
        self.used[rec.id] = rec.revision

    def _status(self, rec: Record) -> tuple[str, str]:
        return (self.snap.effective_verification(rec).value, self.snap.effective_confidentiality(rec).value)

    def _rank(self, recs: list[Record], children_kind: RecordKind | None = None) -> list[Record]:
        if self.rel.is_empty:
            return recs
        def score(r: Record) -> float:
            kids = self.snap.kids(r.id, children_kind) if children_kind else []
            return self.rel.score_record(r, kids)
        indexed = list(enumerate(recs))
        indexed.sort(key=lambda t: (-score(t[1]), t[0]))
        return [r for _, r in indexed]

    def _limit(self, recs: list[Record], n: int | None, what: str) -> list[Record]:
        if n is None or len(recs) <= n:
            return recs
        keep = list(recs[:n])
        # Explicit includes are never trimmed.
        for r in recs[n:]:
            if r.id in self.include_ids:
                keep.append(r)
            else:
                self.trimmed.append(f"{what}: {r.title}")
        return keep

    def _bullet(self, b: Record) -> IRBullet:
        self._use(b)
        claim = self.ctx.approved_claims.get(b.id)
        ver, conf = self._status(b)
        if claim is not None:
            self._use(claim)
            return IRBullet(text=claim.data.approved_text, source_ids=[b.id, *claim.data.source_record_ids],
                            claim_id=claim.id, verification=ver, confidentiality=conf,
                            relevance=self.rel.score_text(claim.data.approved_text))
        return IRBullet(text=b.data.text, source_ids=[b.id], verification=ver, confidentiality=conf,
                        relevance=self.rel.score_text(b.data.text))

    def _bullets_of(self, parent: Record, limit: int | None, what: str) -> list[IRBullet]:
        kids = [b for b in self.snap.kids(parent.id, RecordKind.BULLET) if self.eligible(b) and b.data.text]
        kids = self._rank(kids)
        kept = self._limit(kids, limit, f"{what} statement ({parent.title})")
        return [self._bullet(b) for b in kept]

    def _date(self, start: str, end: str, is_current: bool, style: str | None = None) -> str:
        return dates.format_range(start, end, is_current, style or self.ctx.date_style)

    @staticmethod
    def _sort_key(start: str, end: str, is_current: bool) -> list[int]:
        k = dates.range_sort_key(start, end, is_current)
        return [*k[0], *k[1]]

    # ------------------------------------------------------------------ header
    def _contacts(self) -> list[ContactItem]:
        p = self.snap.personal_data
        keys = self.v.contact_fields or list(self.mode.contact_fields)
        out: list[ContactItem] = []

        def short(url: str) -> str:
            return re.sub(r"^https?://(www\.)?", "", url).rstrip("/")

        for key in keys:
            if key == "email" and p.email:
                out.append(ContactItem(key="email", label="Email", value=p.email, url=f"mailto:{p.email}"))
            elif key == "phone" and p.phone:
                out.append(ContactItem(key="phone", label="Phone", value=p.phone,
                                       url="tel:" + re.sub(r"[^\d+]", "", p.phone)))
            elif key == "location":
                loc = ", ".join(x for x in (p.city or p.state, p.country) if x)
                if loc:
                    out.append(ContactItem(key="location", label="Location", value=loc))
            elif key == "orcid" and p.orcid:
                out.append(ContactItem(key="orcid", label="ORCID", value=f"ORCID {p.orcid}",
                                       url=f"https://orcid.org/{p.orcid}"))
            elif key in LINK_LABELS:
                url = getattr(p, key, "")
                if url:
                    lbl = LINK_LABELS[key]
                    value = short(url) if key not in NAMED_LINKS else lbl
                    out.append(ContactItem(key=key, label=lbl, value=value, url=url))
            elif key == "scopus_id" and p.scopus_id:
                out.append(ContactItem(key=key, label="Scopus", value=f"Scopus ID {p.scopus_id}",
                                       url=f"https://www.scopus.com/authid/detail.uri?authorId={p.scopus_id}"))
            elif key == "researcher_id" and p.researcher_id:
                out.append(ContactItem(key=key, label="ResearcherID", value=f"ResearcherID {p.researcher_id}",
                                       url=f"https://www.webofscience.com/wos/author/record/{p.researcher_id}"))
        return out

    # ------------------------------------------------------------------ sections
    def section_summary(self, key: str) -> IRSection | None:
        summaries = [s for s in self.snap.of(RecordKind.SUMMARY) if self.eligible(s) and s.data.text]
        if not summaries:
            self.warnings.append("No professional summary is available for this resume.")
            return None
        chosen: Record | None = None
        if self.v.summary_id:
            chosen = next((s for s in summaries if s.id == self.v.summary_id), None)
        if chosen is None:
            prefs: list[str] = []
            if self.ctx.target is not None and self.ctx.target.data.summary_focus:
                prefs.append(self.ctx.target.data.summary_focus)
            prefs.extend(f.value for f in self.mode.summary_focus)
            prefs.append(SummaryFocus.GENERAL.value)
            for f in prefs:
                chosen = next((s for s in summaries if s.data.focus == f), None)
                if chosen:
                    break
        if chosen is None:
            chosen = self._rank(summaries)[0]
        self._use(chosen)
        return IRSection(key=key, title=self.mode.title_for(key), layout="paragraph",
                         paragraphs=[chosen.data.text], source_ids=[chosen.id])

    def _skills(self) -> list[Record]:
        return [s for s in self.snap.of(RecordKind.SKILL)
                if self.eligible(s) and s.data.name and s.data.category != SkillCategory.LANGUAGES.value]

    def _skill_sort(self, skills: list[Record]) -> list[Record]:
        indexed = list(enumerate(skills))
        indexed.sort(key=lambda t: (-self.rel.score_record(t[1]) if not self.rel.is_empty else 0,
                                    -PROFICIENCY_RANK.get(t[1].data.proficiency, 0), t[0]))
        return [r for _, r in indexed]

    def _grouped_skills(self) -> list[tuple[str, list[Record]]]:
        groups: dict[str, list[Record]] = {}
        for s in self._skill_sort(self._skills()):
            groups.setdefault(s.data.category, []).append(s)
        cat_order = [c.value for c in SkillCategory]

        def gscore(item: tuple[str, list[Record]]) -> tuple:
            cat, members = item
            top = sum(self.rel.score_record(m) for m in members[:3]) if not self.rel.is_empty else 0.0
            return (-top, cat in GENERIC_CATEGORIES, cat_order.index(cat) if cat in cat_order else 99)

        return sorted(groups.items(), key=gscore)

    def section_skills(self, key: str) -> IRSection | None:
        groups = self._grouped_skills()
        if not groups:
            return None
        if self.budget.skill_groups is not None and len(groups) > self.budget.skill_groups:
            for cat, members in groups[self.budget.skill_groups:]:
                self.trimmed.append(f"Skill group: {label(SkillCategory(cat))} ({len(members)} skills)")
            groups = groups[: self.budget.skill_groups]
        out: list[IRSkillGroup] = []
        for cat, members in groups:
            kept = self._limit(members, self.budget.skills_per_group, "Skill")
            for m in kept:
                self._use(m)
            out.append(IRSkillGroup(category=cat, label=label(SkillCategory(cat)), items=[m.data.name for m in kept],
                                    source_ids=[m.id for m in kept],
                                    levels=[PROFICIENCY_RANK.get(m.data.proficiency, 0) for m in kept]))
        return IRSection(key=key, title=self.mode.title_for(key), layout="skills", skill_groups=out, sidebar_ok=True)

    def section_competencies(self, key: str) -> IRSection | None:
        groups = [(c, m) for c, m in self._grouped_skills() if c not in GENERIC_CATEGORIES]
        if not groups:
            return None
        n = self.budget.competencies
        items: list[str] = []
        ids: list[str] = []
        for cat, members in groups[: n if n else None]:
            top = members[:3]
            names = ", ".join(m.data.name for m in top)
            items.append(f"{label(SkillCategory(cat))} ({names})" if names else label(SkillCategory(cat)))
            for m in top:
                self._use(m)
                ids.append(m.id)
        return IRSection(key=key, title=self.mode.title_for(key), layout="list", items=items, source_ids=ids,
                         sidebar_ok=True)

    def _position_entry(self, pos: Record, with_bullets: bool, primary: bool) -> IREntry:
        d = pos.data
        self._use(pos)
        ver, conf = self._status(pos)
        subtitle = ", ".join(x for x in (d.division, d.organisation) if x)
        description = d.approved_external_wording or (first_sentence(d.summary, 300) if d.summary else "")
        entry = IREntry(
            id=pos.id, kind="position", title=d.designation, subtitle=subtitle, location=d.location,
            date_text=self._date(d.start, d.end, d.is_current), sort_key=self._sort_key(d.start, d.end, d.is_current),
            description=description if with_bullets else "", source_ids=[pos.id], verification=ver,
            confidentiality=conf, is_current=d.is_current,
        )
        if with_bullets:
            limit = self.budget.bullets_primary if primary else self.budget.bullets_other
            entry.bullets = self._bullets_of(pos, limit, "Experience")
            if self.mode.show_tools and d.tools:
                entry.meta.append(("Tools", ", ".join(d.tools[:12])))
        for a in self.snap.kids(pos.id, RecordKind.ASSIGNMENT):
            if not self.eligible(a):
                continue
            self._use(a)
            ad = a.data
            a_ver, a_conf = self._status(a)
            child = IREntry(
                id=a.id, kind="assignment", title=ad.title, subtitle=ad.unit,
                date_text=self._date(ad.start, ad.end, ad.is_current),
                sort_key=self._sort_key(ad.start, ad.end, ad.is_current),
                status_label=label(AssignmentType(ad.assignment_type)),
                description=first_sentence(ad.description, 240) if (with_bullets and ad.description) else "",
                source_ids=[a.id], verification=a_ver, confidentiality=a_conf, is_current=ad.is_current,
            )
            if with_bullets:
                child.bullets = self._bullets_of(a, self.budget.assignments_bullets, "Responsibility")
            entry.children.append(child)
        return entry

    def _positions_sorted(self) -> list[Record]:
        positions = [p for p in self.snap.of(RecordKind.POSITION) if self.eligible(p)]
        positions.sort(key=lambda p: dates.range_sort_key(p.data.start, p.data.end, p.data.is_current), reverse=True)
        return positions

    def section_experience(self, key: str) -> IRSection | None:
        positions = self._positions_sorted()
        if not positions:
            return None
        if self.mode.government:
            return self._experience_table(key, positions)
        n = self.budget.positions
        entries: list[IREntry] = []
        for i, pos in enumerate(positions):
            within = n is None or i < n or pos.id in self.include_ids
            if within:
                entries.append(self._position_entry(pos, with_bullets=True, primary=(i == 0)))
            elif self.length == ResumeLength.ONE_PAGE:
                self.trimmed.append(f"Position: {pos.title}")
            else:
                entries.append(self._position_entry(pos, with_bullets=False, primary=False))
        return IRSection(key=key, title=self.mode.title_for(key), layout="entries", entries=entries)

    def _experience_table(self, key: str, positions: list[Record]) -> IRSection:
        proforma = self.mode.proforma
        pay_opted = "present_pay_level" in self.v.official_particulars
        # The proforma always has the pay column; it is filled only when the resume opts in to pay details.
        show_pay = pay_opted or proforma
        if proforma:
            header = ["Office / Institution", "Post held on regular basis", "From", "To",
                      "Pay level / pay scale of the post", "Nature of duties (in detail), highlighting experience "
                      "required for the post applied for"]
        else:
            header = ["Office / Organisation", "Post held", "From", "To", *(["Pay level"] if show_pay else []),
                      "Nature of duties"]
        rows: list[list[str]] = []
        ids: list[str] = []
        # Bio-data proformas list employment in chronological order (oldest first).
        for pos in reversed(positions):
            d = pos.data
            self._use(pos)
            ids.append(pos.id)
            duties = d.nature_of_duties or d.approved_external_wording or d.summary
            bullets = [b for b in self.snap.kids(pos.id, RecordKind.BULLET) if self.eligible(b) and b.data.text]
            if proforma and bullets:
                limit = None if self.length == ResumeLength.FULL else 4
                ranked = self._rank(bullets) if not self.rel.is_empty else bullets
                lines = ["• " + self._bullet(b).text for b in (ranked if limit is None else ranked[:limit])]
                for b in bullets:
                    self._use(b)
                    ids.append(b.id)
                duties = "\n".join(([duties] if duties else []) + lines)
            elif not duties and bullets:
                duties = "; ".join(self._bullet(b).text.rstrip(".") for b in bullets[:4]) + "."
            assignments = [a for a in self.snap.kids(pos.id, RecordKind.ASSIGNMENT) if self.eligible(a)]
            for a in assignments:
                self._use(a)
                ids.append(a.id)
                extra = f"{label(AssignmentType(a.data.assignment_type))}: {a.data.title}"
                if a.data.unit:
                    extra += f", {a.data.unit}"
                rng = self._date(a.data.start, a.data.end, a.data.is_current)
                duties = (duties + "\n" if duties else "") + extra + (f" ({rng})" if rng else "")
            frm = _bio_date(d.start)
            to = "Till date" if d.is_current else _bio_date(d.end)
            org = ", ".join(x for x in (d.division, d.organisation) if x)
            row = [org, d.designation, frm, to, *([d.pay_level if pay_opted else ""] if show_pay else []), duties or ""]
            rows.append(row)
        widths = [0.22, 0.17, 0.09, 0.09, *([0.09] if show_pay else []), 0.43 - (0.09 if show_pay else 0)]
        if proforma:
            widths = [0.18, 0.17, 0.09, 0.09, 0.10, 0.37]
        return IRSection(key=key, title=self.mode.title_for(key), layout="table",
                         table=IRTable(header=header, rows=rows, col_widths=widths, source_ids=ids), source_ids=ids)

    def _education_records(self) -> list[Record]:
        recs = [e for e in self.snap.of(RecordKind.EDUCATION)
                if self.eligible(e) and QualificationType(e.data.qualification_type) not in TRAINING_TYPES]
        if not self.v.include_planned_education:
            planned = [e for e in recs if e.data.status == EducationStatus.PLANNED.value]
            for e in planned:
                self.trimmed.append(f"Planned qualification hidden: {e.title}")
            recs = [e for e in recs if e.data.status != EducationStatus.PLANNED.value]
        recs.sort(key=lambda e: dates.range_sort_key(e.data.start, e.data.end,
                                                     e.data.status == EducationStatus.ONGOING.value), reverse=True)
        return recs

    def _edu_date(self, e: Record) -> str:
        d = e.data
        status = EducationStatus(d.status)
        if status == EducationStatus.ONGOING:
            start = dates.format_date(d.start, "year")
            return f"{start} – ongoing" if start else "Ongoing"
        if status == EducationStatus.PLANNED:
            return "Planned"
        return dates.format_date(d.end or d.start, "year")

    def section_education(self, key: str) -> IRSection | None:
        recs = self._education_records()
        if not recs:
            return None
        if self.mode.government:
            header = ["Qualification", "Discipline / Subject", "Institution / University", "Year", "Division / Grade"]
            rows = []
            ids = []
            for e in reversed(recs):
                d = e.data
                self._use(e)
                ids.append(e.id)
                inst = ", ".join(dict.fromkeys(x for x in (d.institution, d.university) if x))
                year = self._edu_date(e)
                grade = d.grade
                if d.status == EducationStatus.ONGOING.value:
                    grade = (grade + "; " if grade else "") + "Ongoing"
                discipline = d.discipline + (f" ({d.specialisation})" if d.specialisation else "")
                if d.thesis_title:
                    discipline += f"\nThesis: {d.thesis_title}"
                rows.append([d.degree, discipline, inst, year, grade])
            return IRSection(key=key, title=self.mode.title_for(key), layout="table",
                             table=IRTable(header=header, rows=rows, col_widths=[0.15, 0.30, 0.30, 0.11, 0.14],
                                           source_ids=ids), source_ids=ids)
        entries: list[IREntry] = []
        research = self.mode.id in ("scientific_research", "academic_cv")
        for e in recs:
            d = e.data
            self._use(e)
            ver, conf = self._status(e)
            title = d.degree + (f", {d.discipline}" if d.discipline else "")
            if d.specialisation:
                title += f" ({d.specialisation})"
            subtitle = ", ".join(dict.fromkeys(x for x in (d.institution, d.university) if x))
            status = EducationStatus(d.status)
            entry = IREntry(
                id=e.id, kind="education", title=title, subtitle=subtitle, location=d.location,
                date_text=self._edu_date(e),
                sort_key=self._sort_key(d.start, d.end, status == EducationStatus.ONGOING),
                status_label={"ongoing": "Ongoing", "planned": "Planned"}.get(status.value, ""),
                source_ids=[e.id], verification=ver, confidentiality=conf,
                is_current=status == EducationStatus.ONGOING,
            )
            if d.grade:
                entry.meta.append(("Grade", d.grade))
            if d.thesis_title:
                entry.meta.append(("Thesis", d.thesis_title))
            if research and d.supervisor:
                entry.meta.append(("Supervisor", d.supervisor))
            entries.append(entry)
        return IRSection(key=key, title=self.mode.title_for(key), layout="entries", entries=entries, sidebar_ok=True)

    # ------------------------------------------------------------------ training & certifications
    def _training_section_of(self, rec: Record) -> str:
        if rec.kind == RecordKind.TRAINING:
            for key, types in TRAINING_SECTIONS.items():
                if rec.data.training_type in types:
                    return key
            return "other_qualifications"
        return LEGACY_EDUCATION_SECTION.get(rec.data.qualification_type, "other_qualifications")

    def _training_candidates(self, section_keys: set[str]) -> list[Record]:
        """Eligible training records (and legacy training-type education records) for the given sections."""
        recs = [r for r in self.snap.of(RecordKind.TRAINING) if self.eligible(r) and r.data.title]
        recs += [e for e in self.snap.of(RecordKind.EDUCATION)
                 if self.eligible(e) and QualificationType(e.data.qualification_type) in TRAINING_TYPES]
        recs = [r for r in recs if self._training_section_of(r) in section_keys]
        out = []
        for r in recs:
            planned = r.data.status in (EducationStatus.PLANNED.value, "planned")
            if planned and not self.v.include_planned_education:
                self.trimmed.append(f"Planned qualification hidden: {r.title}")
                continue
            if r.kind == RecordKind.TRAINING and self._expired(r) and self.length != ResumeLength.FULL:
                self.trimmed.append(f"Expired certification left out: {r.title}")
                continue
            out.append(r)

        def key(r: Record):
            d = r.data
            ongoing = d.status in ("ongoing",) or bool(getattr(d, "is_current", False))
            return dates.range_sort_key(d.start, d.end, ongoing)
        out.sort(key=key, reverse=True)
        return out

    def _expired(self, rec: Record) -> bool:
        v = dates.parse_or_none(rec.data.valid_until)
        if v is None:
            return False
        last = date(v.year, v.month or 12, v.day or 28)
        return last < self.ctx.today

    def _training_entry(self, r: Record, detail: bool) -> IREntry:
        self._use(r)
        ver, conf = self._status(r)
        if r.kind == RecordKind.EDUCATION:
            d = r.data
            return IREntry(
                id=r.id, kind="training", title=d.degree or d.discipline, subtitle=d.issuer or d.institution,
                date_text=self._edu_date(r),
                status_label={"ongoing": "Ongoing", "planned": "Planned"}.get(d.status, ""),
                link=d.credential_url, source_ids=[r.id], verification=ver, confidentiality=conf,
            )
        d = r.data
        subtitle = d.provider
        if d.sponsor and d.sponsor.lower() not in (d.provider or "").lower():
            subtitle = f"{subtitle} (sponsored by {d.sponsor})" if subtitle else f"Sponsored by {d.sponsor}"
        if d.status == "planned":
            when = "Planned"
        elif d.status == "ongoing" or d.is_current:
            start = dates.format_date(d.start, self.ctx.date_style)
            when = f"{start} – ongoing" if start else "Ongoing"
        elif d.start and d.end and dates.format_date(d.start, "mon_year") != dates.format_date(d.end, "mon_year"):
            when = self._date(d.start, d.end, False)
        else:
            when = dates.format_date(d.end or d.start, self.ctx.date_style)
        status = ""
        if self._expired(r):
            status = "Expired"
        elif d.status == "ongoing" or d.is_current:
            status = "Ongoing"
        elif d.status == "planned":
            status = "Planned"
        entry = IREntry(id=r.id, kind="training", title=d.title, subtitle=subtitle, date_text=when,
                        status_label=status, link=d.credential_url, source_ids=[r.id], verification=ver,
                        confidentiality=conf, is_current=d.is_current)
        duration = _duration_text(d.duration_hours, d.duration_days)
        if duration:
            entry.meta.append(("Duration", duration))
        if d.grade:
            entry.meta.append(("Result", d.grade))
        if d.credential_id:
            entry.meta.append(("Credential", d.credential_id))
        if d.valid_until:
            entry.meta.append(("Valid until" if not self._expired(r) else "Expired",
                               dates.format_date(d.valid_until, self.ctx.date_style)))
        if detail:
            if d.mode in ("online", "blended", "abroad"):
                entry.meta.append(("Mode", label(TrainingMode(d.mode))))
            if d.skills:
                entry.meta.append(("Skills", ", ".join(d.skills[:8])))
            if d.outcome:
                entry.description = first_sentence(d.outcome, 240)
        return entry

    def section_training(self, key: str) -> IRSection | None:
        """Combined 'Certifications & Training' section for compact resumes.

        Items whose dedicated section (certifications, courses, workshops …) is also in this resume
        are shown there instead, so nothing appears twice.
        """
        keys = {k for k in TRAINING_SECTIONS if k not in self.order}
        recs = self._training_candidates(keys)
        if not recs:
            return None
        recs = self._limit(self._rank(recs) if not self.rel.is_empty else recs, self.budget.training, "Training")
        detail = self.length == ResumeLength.FULL
        entries = [self._training_entry(r, detail) for r in recs]
        return IRSection(key=key, title=self.mode.title_for(key), layout="entries", entries=entries, sidebar_ok=True)

    def section_training_group(self, key: str) -> IRSection | None:
        recs = self._training_candidates({key})
        if not recs:
            return None
        recs = self._limit(self._rank(recs) if not self.rel.is_empty else recs, self.budget.training,
                           self.mode.title_for(key))
        detail = self.length == ResumeLength.FULL
        if self.mode.government and key != "certifications":
            header = ["Programme / course", "Institute / sponsor", "Period", "Duration"]
            rows = []
            for r in recs:
                e = self._training_entry(r, False)
                dur = next((v for k, v in e.meta if k == "Duration"), "")
                rows.append([e.title, e.subtitle, e.date_text, dur])
            ids = [r.id for r in recs]
            return IRSection(key=key, title=self.mode.title_for(key), layout="table",
                             table=IRTable(header=header, rows=rows, col_widths=[0.38, 0.32, 0.18, 0.12],
                                           source_ids=ids), source_ids=ids)
        entries = [self._training_entry(r, detail) for r in recs]
        return IRSection(key=key, title=self.mode.title_for(key), layout="entries", entries=entries, sidebar_ok=True)

    def _publication_entry(self, pub: Record, names: list[str]) -> IREntry:
        d = pub.data
        self._use(pub)
        ver, conf = self._status(pub)
        status = PublicationStatus(d.status)
        when = dates.parse_or_none(d.date)
        year = str(when.year) if when else ""
        parts: list[str] = [f"“{d.title.rstrip('.')},”"]
        if status == PublicationStatus.PUBLISHED:
            venue = d.venue
            if d.volume:
                venue += f", vol. {d.volume}"
            if d.issue:
                venue += f", no. {d.issue}"
            if d.pages:
                venue += f", pp. {d.pages}" if re.match(r"^\d+\s*[-–]\s*\d+$", d.pages) else f", {d.pages}"
            if when:
                venue += f", {when.format('mon_year') if when.month else year}"
            parts.append(venue.strip(", ") + ".")
            status_label = ""
        elif status == PublicationStatus.ACCEPTED:
            parts.append(f"accepted for publication in {d.venue}." if d.venue else "accepted for publication.")
            status_label = "Accepted"
        elif status == PublicationStatus.UNDER_REVIEW:
            parts.append(f"under review at {d.venue}." if d.venue else "under review.")
            status_label = "Under review"
        elif status == PublicationStatus.SUBMITTED:
            parts.append(f"submitted to {d.venue}." if d.venue else "submitted.")
            status_label = "Submitted"
        else:
            parts.append("in preparation.")
            status_label = "In preparation"
        link = f"https://doi.org/{d.doi}" if d.doi else d.url
        rest = " ".join(parts)
        if d.doi:
            rest += f" doi: {d.doi}"
        return IREntry(
            id=pub.id, kind="publication", title=d.title, subtitle=d.venue, date_text=year,
            sort_key=list(when.sort_key()) if when else [0, 0, 0], status_label=status_label,
            authors=d.authors, citation_rest=rest, highlight_names=names, link=link, source_ids=[pub.id],
            verification=ver, confidentiality=conf,
        )

    def _publications(self, statuses: set[PublicationStatus], limit: int | None, what: str) -> list[Record]:
        scope = self.v.publication_scope if self.v.publication_scope else self.mode.publication_scope
        if scope == "none":
            return []
        pubs = [p for p in self.snap.of(RecordKind.PUBLICATION)
                if self.eligible(p) and PublicationStatus(p.data.status) in statuses and p.data.title]
        def by_date(p: Record) -> tuple:
            pd = dates.parse_or_none(p.data.date)
            return pd.sort_key() if pd else (0, 0, 0)
        pubs.sort(key=by_date, reverse=True)
        if scope == "all" or self.mode.publication_scope == "all" and self.length == ResumeLength.FULL:
            return pubs
        if limit is not None and len(pubs) > limit:
            ranked = self._rank(pubs) if not self.rel.is_empty else pubs
            keep_ids = {p.id for p in ranked[:limit]} | (self.include_ids & {p.id for p in pubs})
            for p in pubs:
                if p.id not in keep_ids:
                    self.trimmed.append(f"{what}: {p.title}")
            pubs = [p for p in pubs if p.id in keep_ids]
        return pubs

    def _author_names(self) -> list[str]:
        p = self.snap.personal_data
        names = [*p.author_name_variants, p.full_name, p.preferred_name]
        return [n for n in dict.fromkeys(names) if n]

    def section_publications(self, key: str) -> IRSection | None:
        pubs = self._publications({PublicationStatus.PUBLISHED, PublicationStatus.ACCEPTED},
                                  self.budget.publications, "Publication")
        if not pubs:
            return None
        names = self._author_names()
        return IRSection(key=key, title=self.mode.title_for(key), layout="publications",
                         entries=[self._publication_entry(p, names) for p in pubs])

    def section_manuscripts(self, key: str) -> IRSection | None:
        pubs = self._publications({PublicationStatus.SUBMITTED, PublicationStatus.UNDER_REVIEW, PublicationStatus.DRAFT},
                                  self.budget.manuscripts, "Manuscript")
        if not pubs:
            return None
        names = self._author_names()
        return IRSection(key=key, title=self.mode.title_for(key), layout="publications",
                         entries=[self._publication_entry(p, names) for p in pubs],
                         note="Listed separately from published work; status as stated.")

    def section_projects(self, key: str) -> IRSection | None:
        projects = [p for p in self.snap.of(RecordKind.PROJECT) if self.eligible(p) and p.data.title]
        if not projects:
            return None
        projects.sort(key=lambda p: dates.range_sort_key(p.data.start, p.data.end, p.data.is_current), reverse=True)
        projects = self._rank(projects, RecordKind.BULLET)
        projects = self._limit(projects, self.budget.projects, "Project")
        entries: list[IREntry] = []
        for pr in projects:
            d = pr.data
            self._use(pr)
            ver, conf = self._status(pr)
            subtitle = ", ".join(x for x in (d.role, d.organisation) if x)
            status_label = ""
            if d.is_current:
                status_label = "Ongoing"
            elif d.status in (ProjectStatus.CONCEPT.value, ProjectStatus.PROTOTYPE.value, ProjectStatus.IN_PROGRESS.value):
                status_label = label(ProjectStatus(d.status))
            description = d.approved_external_description or (first_sentence(d.problem, 260) if d.problem else "")
            entry = IREntry(
                id=pr.id, kind="project", title=d.title, subtitle=subtitle,
                date_text=self._date(d.start, d.end, d.is_current),
                sort_key=self._sort_key(d.start, d.end, d.is_current), status_label=status_label,
                description=description, link=d.url, source_ids=[pr.id], verification=ver, confidentiality=conf,
                is_current=d.is_current,
            )
            entry.bullets = self._bullets_of(pr, self.budget.project_bullets, "Project")
            if not entry.bullets and not d.approved_external_description:
                # Field-level bullets, each traced to the project record and field.
                limit = self.budget.project_bullets or 4
                for fname in ("individual_contribution", "approach", "results"):
                    val = getattr(d, fname)
                    if val and len(entry.bullets) < limit:
                        entry.bullets.append(IRBullet(text=first_sentence(val, 260), source_ids=[pr.id],
                                                      source_field=fname, verification=ver, confidentiality=conf))
                for metric in d.metrics:
                    if len(entry.bullets) < limit:
                        entry.bullets.append(IRBullet(text=metric, source_ids=[pr.id], source_field="metrics",
                                                      verification=ver, confidentiality=conf))
            if not d.approved_external_description:
                for fname, flabel in FACET_FIELDS:
                    val = getattr(d, fname)
                    if val:
                        entry.facets.append((flabel, first_sentence(val, 240)))
                entry.highlights = [m for m in d.metrics[:3] if m]
            tech = list(dict.fromkeys([*d.hardware, *d.software, *d.algorithms]))
            if tech:
                entry.meta.append(("Technologies", ", ".join(tech[:10])))
            entries.append(entry)
        return IRSection(key=key, title=self.mode.title_for(key), layout="entries", entries=entries)

    def _activities(self, types: set[ActivityType]) -> list[Record]:
        acts = [a for a in self.snap.of(RecordKind.ACTIVITY)
                if self.eligible(a) and ActivityType(a.data.activity_type) in types and a.data.title]
        acts.sort(key=lambda a: dates.range_sort_key(a.data.start, a.data.end, a.data.is_current), reverse=True)
        return acts

    def _activity_entry(self, a: Record, with_detail: bool = True, date_style: str | None = None) -> IREntry:
        d = a.data
        self._use(a)
        ver, conf = self._status(a)
        sub_parts = [d.role] if d.role and d.role.lower() not in d.title.lower() else []
        sub_parts.append(d.organisation)
        entry = IREntry(
            id=a.id, kind="activity", title=d.title, subtitle=", ".join(x for x in sub_parts if x),
            date_text=self._date(d.start, d.end, d.is_current, date_style),
            sort_key=self._sort_key(d.start, d.end, d.is_current), link=d.url, source_ids=[a.id],
            verification=ver, confidentiality=conf, is_current=d.is_current,
        )
        if with_detail:
            entry.description = first_sentence(d.description, 260) if d.description else ""
            entry.bullets = self._bullets_of(a, 3, "Activity")
            if d.outcome and len(entry.bullets) < 3:
                entry.bullets.append(IRBullet(text=first_sentence(d.outcome, 260), source_ids=[a.id],
                                              source_field="outcome", verification=ver, confidentiality=conf))
        return entry

    def section_leadership(self, key: str) -> IRSection | None:
        acts = self._limit(self._rank(self._activities(LEADERSHIP_TYPES)), self.budget.activities, "Activity")
        acts.sort(key=lambda a: dates.range_sort_key(a.data.start, a.data.end, a.data.is_current), reverse=True)
        if not acts:
            return None
        return IRSection(key=key, title=self.mode.title_for(key), layout="entries",
                         entries=[self._activity_entry(a) for a in acts])

    def _simple_activity_section(self, key: str, types: set[ActivityType], limit: int | None) -> IRSection | None:
        acts = self._limit(self._activities(types), limit, self.mode.title_for(key))
        if not acts:
            return None
        entries = []
        for a in acts:
            e = self._activity_entry(a, with_detail=False, date_style="year")
            if ActivityType(a.data.activity_type) == ActivityType.PATENT:
                bits = [x for x in (a.data.identifier, a.data.status) if x]
                if bits:
                    e.subtitle = ", ".join(x for x in (e.subtitle, " — ".join(bits)) if x)
            entries.append(e)
        return IRSection(key=key, title=self.mode.title_for(key), layout="entries", entries=entries)

    def section_languages(self, key: str) -> IRSection | None:
        p = self.snap.personal_data
        items = list(p.languages)
        ids = [self.snap.personal.id] if (items and self.snap.personal) else []
        for s in self.snap.of(RecordKind.SKILL):
            if s.data.category == SkillCategory.LANGUAGES.value and self.eligible(s) and s.data.name not in items:
                items.append(s.data.name)
                ids.append(s.id)
                self._use(s)
        if not items:
            return None
        return IRSection(key=key, title=self.mode.title_for(key), layout="list", items=items, source_ids=ids,
                         sidebar_ok=True)

    def section_custom(self, key: str) -> IRSection | None:
        sec_id = key.split(":", 1)[1]
        sec = self.snap.get(sec_id)
        if sec is None or sec.kind != RecordKind.CUSTOM_SECTION:
            return None
        entries_recs = [e for e in self.snap.kids(sec.id, RecordKind.CUSTOM_ENTRY) if self.eligible(e)]
        if not entries_recs:
            return None
        self._use(sec)
        layout = sec.data.layout
        if layout == "paragraph":
            paras = []
            ids = []
            for e in entries_recs:
                self._use(e)
                if e.data.description:
                    paras.append(e.data.description)
                    ids.append(e.id)
            return IRSection(key=key, title=sec.data.name, layout="paragraph", paragraphs=paras, source_ids=ids)
        if layout == "bullets":
            items = []
            ids = []
            for e in entries_recs:
                self._use(e)
                text = e.data.title + (f" — {e.data.description}" if e.data.description else "")
                items.append(text)
                ids.append(e.id)
            return IRSection(key=key, title=sec.data.name, layout="list", items=items, source_ids=ids)
        entries = []
        for e in entries_recs:
            d = e.data
            self._use(e)
            ver, conf = self._status(e)
            ent = IREntry(id=e.id, kind="custom", title=d.title, subtitle=d.subtitle,
                          date_text=self._date(d.start, d.end, d.is_current), description=d.description,
                          link=d.url, source_ids=[e.id], verification=ver, confidentiality=conf)
            ent.bullets = [IRBullet(text=b, source_ids=[e.id], source_field="bullets", verification=ver,
                                    confidentiality=conf) for b in d.bullets]
            entries.append(ent)
        return IRSection(key=key, title=sec.data.name, layout="entries", entries=entries)

    def section_expertise(self, key: str) -> IRSection | None:
        recs = [r for r in self.snap.of(RecordKind.EXPERTISE) if self.eligible(r) and r.data.area]
        if not recs:
            return None
        recs = self._rank(recs) if not self.rel.is_empty else recs
        limit = None if self.length == ResumeLength.FULL else (4 if self.length == ResumeLength.ONE_PAGE else 7)
        recs = self._limit(recs, limit, "Area of expertise")
        rows: list[list[str]] = []
        ids: list[str] = []
        for r in recs:
            self._use(r)
            ids.append(r.id)
            area = r.data.area
            if r.data.years_experience:
                yrs = r.data.years_experience
                area += f"\n{yrs:g} year{'s' if yrs != 1 else ''}"
            rows.append([area, r.data.description])
        rated = [r for r in recs if r.data.years_experience]
        chart = None
        if len(rated) >= 2:
            chart = IRChart(kind="years_bars",
                            points=[IRChartPoint(label=r.data.area, value=float(r.data.years_experience),
                                                 source_ids=[r.id]) for r in rated],
                            alt_text="Years of experience by area: " + "; ".join(
                                f"{r.data.area} {r.data.years_experience:g} years" for r in rated),
                            caption="Years of experience in each area, as you recorded them; areas overlap in time.")
        return IRSection(key=key, title=self.mode.title_for(key), layout="definitions", chart=chart,
                         table=IRTable(header=[], rows=rows, col_widths=[0.32, 0.68], source_ids=ids), source_ids=ids)

    def section_career_timeline(self, key: str) -> IRSection | None:
        positions = [p for p in self.snap.of(RecordKind.POSITION)
                     if self.eligible(p) and dates.parse_or_none(p.data.start) is not None]
        positions.sort(key=lambda p: dates.parse_or_none(p.data.start).sort_key())
        # Consecutive posts in the same organisation form one bar.
        groups: list[list[Record]] = []
        for p in positions:
            org = (p.data.short_name or p.data.organisation).strip().lower()
            if groups and (groups[-1][-1].data.short_name or groups[-1][-1].data.organisation).strip().lower() == org:
                groups[-1].append(p)
            else:
                groups.append([p])
        if len(groups) < 2:
            return None
        points: list[IRChartPoint] = []
        legend: list[str] = []
        ids: list[str] = []
        for g in groups:
            first, last = g[0].data, g[-1].data
            months = dates.conservative_months(first.start, last.end, last.is_current, self.ctx.today) or 0
            years = round(months / 12, 1)
            designations = " → ".join(dict.fromkeys(x.data.designation for x in g if x.data.designation))
            highlight = next((x.data.highlight for x in reversed(g) if x.data.highlight), "")
            rng = self._date(first.start, last.end, last.is_current)
            name = first.short_name or short_org(first.organisation)
            for x in g:
                self._use(x)
                ids.append(x.id)
            points.append(IRChartPoint(label=name, start=first.start, end=last.end, is_current=last.is_current,
                                       value=years, caption=highlight or designations,
                                       source_ids=[x.id for x in g]))
            line = f"{first.organisation or name}"
            if designations:
                line += f" — {designations}"
            line += f" ({rng})" if rng else ""
            if highlight:
                line += f": {highlight}"
            legend.append(line)
        alt = "Career timeline: " + "; ".join(
            f"{pt.label} {self._date(pt.start, pt.end, pt.is_current)} ({pt.value:g} years)" for pt in points)
        chart = IRChart(kind="timeline", points=points, alt_text=alt,
                        caption="Bar height shows time in post, calculated from your recorded dates.")
        return IRSection(key=key, title=self.mode.title_for(key), layout="chart", chart=chart, items=legend,
                         source_ids=ids)

    def section_research_overview(self, key: str) -> IRSection | None:
        pubs = [p for p in self.snap.of(RecordKind.PUBLICATION) if self.eligible(p) and p.data.title]
        out_status = {PublicationStatus.PUBLISHED.value, PublicationStatus.ACCEPTED.value}
        done = [p for p in pubs if p.data.status in out_status]
        pending = [p for p in pubs if p.data.status in (PublicationStatus.SUBMITTED.value,
                                                         PublicationStatus.UNDER_REVIEW.value)]
        journals = [p for p in done if p.data.pub_type in JOURNAL_TYPES]
        confs = [p for p in done if p.data.pub_type in CONFERENCE_TYPES]
        others = [p for p in done if p not in journals and p not in confs]
        patents = self._activities({ActivityType.PATENT})
        grants = self._activities({ActivityType.RESEARCH_GRANT})
        talks = self._activities({ActivityType.PRESENTATION})
        tiles: list[IRTile] = []

        def tile(n: int, one: str, many: str, recs: list[Record]) -> None:
            if n:
                tiles.append(IRTile(value=str(n), label=one if n == 1 else many, source_ids=[r.id for r in recs]))
                for r in recs:
                    self._use(r)

        tile(len(journals), "Journal article", "Journal articles", journals)
        tile(len(confs), "Conference paper", "Conference papers", confs)
        tile(len(others), "Other publication", "Other publications", others)
        tile(len(pending), "Manuscript under review", "Manuscripts under review", pending)
        tile(len(patents), "Patent", "Patents", patents)
        tile(len(grants), "Research grant", "Research grants", grants)
        tile(len(talks), "Talk / presentation", "Talks & presentations", talks)
        p = self.snap.personal_data
        caption = ", ".join(x for x in (p.metrics_source, dates.format_date(p.metrics_as_of, "mon_year")) if x)
        pid = [self.snap.personal.id] if self.snap.personal else []
        for val, lbl in ((p.citations, "Citations"), (p.h_index, "h-index"), (p.i10_index, "i10-index")):
            if val:
                tiles.append(IRTile(value=val, label=lbl, caption=caption, source_ids=pid))
        if not tiles:
            return None
        chart = None
        years: dict[int, dict[str, float]] = {}
        for pub in done:
            pd = dates.parse_or_none(pub.data.date)
            if pd is None:
                continue
            grp = "Journal" if pub in journals else ("Conference" if pub in confs else "Other")
            years.setdefault(pd.year, {}).setdefault(grp, 0)
            years[pd.year][grp] += 1
        if len(years) >= 2 and sum(sum(v.values()) for v in years.values()) >= 3:
            series = [g for g in ("Journal", "Conference", "Other") if any(g in v for v in years.values())]
            pts = [IRChartPoint(label=str(y), value=n, group=g) for y in range(min(years), max(years) + 1)
                   for g, n in sorted(years.get(y, {}).items())]
            alt = "Publications per year: " + "; ".join(
                f"{y}: " + ", ".join(f"{int(n)} {g.lower()}" for g, n in sorted(v.items()))
                for y, v in sorted(years.items()))
            chart = IRChart(kind="stacked_years", points=pts, series=series, alt_text=alt,
                            caption="Published and accepted outputs by year (from your publication records).")
        return IRSection(key=key, title=self.mode.title_for(key), layout="overview", tiles=tiles, chart=chart,
                         source_ids=[r.id for r in done])

    def section_grants(self, key: str) -> IRSection | None:
        acts = self._activities({ActivityType.RESEARCH_GRANT})
        if not acts:
            return None
        entries = []
        for a in acts:
            e = self._activity_entry(a)
            if a.data.status:
                e.status_label = a.data.status
            if a.data.identifier:
                e.meta.append(("Reference", a.data.identifier))
            entries.append(e)
        return IRSection(key=key, title=self.mode.title_for(key), layout="entries", entries=entries)

    def section_references(self, key: str) -> IRSection | None:
        refs = [r for r in self.snap.of(RecordKind.REFERENCE) if self.eligible(r) and r.data.name]
        allowed = [r for r in refs if r.data.permission_confirmed]
        if len(allowed) < len(refs):
            self.warnings.append(f"{len(refs) - len(allowed)} referee(s) not shown: their permission to be named "
                                 "is not confirmed.")
        if not allowed:
            return None
        entries = []
        for r in allowed:
            d = r.data
            self._use(r)
            ver, conf = self._status(r)
            e = IREntry(id=r.id, kind="reference", title=d.name,
                        subtitle=", ".join(x for x in (d.designation, d.organisation) if x),
                        description=d.relationship, source_ids=[r.id], verification=ver, confidentiality=conf)
            if d.show_contact_details:
                if d.email:
                    e.meta.append(("Email", d.email))
                if d.phone:
                    e.meta.append(("Telephone", d.phone))
            entries.append(e)
        return IRSection(key=key, title=self.mode.title_for(key), layout="entries", entries=entries)

    def section_particulars(self, key: str) -> IRSection | None:
        p = self.snap.personal_data
        rows: list[list[str]] = []
        if p.full_name:
            rows.append(["Name", p.full_name])
        current = next((x for x in self._positions_sorted() if x.data.is_current), None)
        if current is not None:
            self._use(current)
            rows.append(["Present designation", current.data.designation])
            org = ", ".join(x for x in (current.data.division, current.data.organisation) if x)
            if org:
                rows.append(["Present organisation", org])
        for fname in self.v.official_particulars:
            if fname not in PRIVATE_LABELS:
                continue
            val = getattr(p, fname, "")
            if fname in ("date_of_birth", "date_of_entry_into_service"):
                pd = dates.parse_or_none(val)
                val = pd.earliest().strftime("%d/%m/%Y") if (pd and pd.day) else (pd.format("month_year") if pd else "")
            if val:
                rows.append([PRIVATE_LABELS[fname], val])
        for c in self._contacts():
            if c.key in ("email", "phone"):
                rows.append([c.label if c.key != "phone" else "Telephone", c.value])
        if not rows:
            return None
        ids = [self.snap.personal.id] if self.snap.personal else []
        if self.snap.personal:
            self._use(self.snap.personal)
        return IRSection(key=key, title=self.mode.title_for(key), layout="particulars",
                         table=IRTable(header=[], rows=rows, col_widths=[0.34, 0.66], source_ids=ids), source_ids=ids)

    def section_requirements_matrix(self, key: str) -> IRSection | None:
        matrix = self.ctx.requirements_matrix
        if not matrix:
            return None
        rows = []
        ids: list[str] = []
        for i, (req, possessed, src) in enumerate(matrix, start=1):
            rows.append([str(i), req, possessed])
            ids.extend(src)
            for sid in src:
                rec = self.snap.get(sid)
                if rec is not None:
                    self._use(rec)
        title = self.mode.title_for(key)
        return IRSection(key=key, title=title, layout="table",
                         table=IRTable(header=["S. No.", "Qualifications / experience required (as advertised)",
                                               "Qualifications / experience possessed"],
                                       rows=rows, col_widths=[0.08, 0.42, 0.50], source_ids=ids), source_ids=ids)

    def section_declaration(self, key: str) -> IRSection | None:
        if not self.v.include_declaration:
            return None
        p = self.snap.personal_data
        text = PROFORMA_DECLARATION if self.mode.proforma else (
            "I hereby declare that the particulars furnished above are true, complete and correct to the best of my "
            "knowledge and belief.")
        return IRSection(
            key=key, title=self.mode.title_for(key), layout="declaration", paragraphs=[text],
            items=[f"Place: {p.city}" if p.city else "Place:", "Date:", p.full_name or p.display_name()],
        )

    # ------------------------------------------------------------------ deputation proforma (DoPT OM 02.07.2015)
    def _particular(self, fname: str) -> str:
        """A private particular, only when this resume opts in to it; otherwise empty (left blank on the form)."""
        if fname not in self.v.official_particulars:
            return ""
        val = str(getattr(self.snap.personal_data, fname, "") or "").strip()
        if fname in DATE_PARTICULARS and val:
            pd = dates.parse_or_none(val)
            if pd is not None:
                val = pd.earliest().strftime("%d/%m/%Y") if pd.day else pd.format("month_year")
        if val and self.snap.personal is not None:
            self._use(self.snap.personal)
        return val

    def _rows_section(self, key: str, rows: list[list[str]], widths: tuple[float, float] = (0.46, 0.54)) -> IRSection:
        ids = [self.snap.personal.id] if self.snap.personal else []
        return IRSection(key=key, title=self.mode.title_for(key), layout="particulars",
                         table=IRTable(header=[], rows=rows, col_widths=list(widths), source_ids=ids),
                         source_ids=ids)

    def section_proforma_particulars(self, key: str) -> IRSection | None:
        p = self.snap.personal_data
        name = (p.full_name or p.display_name()).upper()
        if self.snap.personal is not None and name:
            self._use(self.snap.personal)
        address = self._particular("home_address").upper()
        return self._rows_section(key, [
            ["1. Name and address (in block letters)", "\n".join(x for x in (name, address) if x)],
            ["2. Date of birth (in Christian era)", self._particular("date_of_birth")],
            ["3. (i) Date of entry into service", self._particular("date_of_entry_into_service")],
            ["3. (ii) Date of retirement under Central / State Government rules",
             self._particular("date_of_retirement")],
        ])

    def section_proforma_requirements(self, key: str) -> IRSection | None:
        rows: list[list[str]] = []
        ids: list[str] = []
        for req, possessed, src in self.ctx.requirements_matrix or []:
            kind, _, text = req.partition(": ")
            rows.append([kind or "Requirement", text or req, possessed])
            ids.extend(src)
            for sid in src:
                rec = self.snap.get(sid)
                if rec is not None:
                    self._use(rec)
        vac = self.ctx.vacancy
        if not rows and vac is not None:
            if vac.essential_qualifications:
                rows.append(["Essential", vac.essential_qualifications, ""])
            if vac.experience_criteria:
                rows.append(["Essential (experience)", vac.experience_criteria, ""])
            if vac.desirable_qualifications:
                rows.append(["Desirable", vac.desirable_qualifications, ""])
        if not rows:
            rows = [["Essential", "", ""], ["Desirable", "", ""]]
        authority = self.v.proforma.get("equivalence_authority", "")
        if authority:
            rows.append(["Equivalence", "Authority for treating a qualification as equivalent", authority])
        return IRSection(key=key, title=self.mode.title_for(key), layout="table",
                         table=IRTable(header=["", "Qualifications / experience required as mentioned in the "
                                               "advertisement / vacancy circular",
                                               "Qualifications / experience possessed by the officer"],
                                       rows=rows, col_widths=[0.16, 0.42, 0.42], source_ids=ids), source_ids=ids)

    def section_proforma_statement(self, key: str) -> IRSection | None:
        return self._rows_section(key, [[
            "6. Please state clearly whether, in the light of the entries made above, you meet the requisite "
            "essential qualifications and work experience of the post",
            self.v.proforma.get("meets_requirements", "")]])

    def section_proforma_service(self, key: str) -> IRSection | None:
        current = next((x for x in self._positions_sorted() if x.data.is_current), None)
        org = ""
        if current is not None:
            org = ", ".join(x for x in (current.data.division, current.data.organisation) if x)
        etype = self._particular("employer_type")
        employer = f"{etype} ({org})" if (etype and org) else etype
        pay_bits = [f"{lbl}: {v}" for lbl, v in (("Pay level", self._particular("present_pay_level")),
                                                  ("Basic pay", self._particular("basic_pay")),
                                                  ("Total emoluments", self._particular("total_emoluments"))) if v]
        return self._rows_section(key, [
            ["8. Nature of present employment, i.e. ad hoc, temporary, quasi-permanent or permanent",
             self._particular("nature_of_employment")],
            ["9. If the present employment is held on deputation / contract basis: (a) date of initial appointment, "
             "(b) period of appointment on deputation / contract, (c) parent office / organisation, (d) name and pay "
             "of the post held in substantive capacity in the parent organisation",
             self._particular("present_deputation_details")],
            ["10. If any post was held on deputation in the past: date of return from the last deputation and "
             "other details", self._particular("past_deputation_details")],
            ["11. Present employer: Central Government, State Government, autonomous organisation, government "
             "undertaking, university or others", employer],
            ["12. Whether working in the same department and in the feeder or feeder-to-feeder grade",
             self._particular("feeder_grade_status")],
            ["13. Whether in a revised scale of pay; if so, the date of revision and the pre-revised scale",
             self._particular("pay_revision_details")],
            ["14. Total emoluments per month now drawn", "; ".join(pay_bits)],
            ["15. If the employer does not follow Central Government pay scales: details of the latest salary "
             "slip (enclosed)", self._particular("non_central_pay_details")],
        ])

    def section_proforma_additional(self, key: str) -> IRSection | None:
        paragraphs: list[str] = []
        ids: list[str] = []
        summary = self.section_summary("summary")
        if summary is not None:
            paragraphs.extend(summary.paragraphs)
            ids.extend(summary.source_ids)
        areas = [r for r in self.snap.of(RecordKind.EXPERTISE) if self.eligible(r) and r.data.area]
        if areas:
            bits = []
            for r in self._rank(areas) if not self.rel.is_empty else areas:
                self._use(r)
                ids.append(r.id)
                yrs = r.data.years_experience
                bits.append(r.data.area + (f" ({yrs:g} year{'s' if yrs != 1 else ''})" if yrs else ""))
            paragraphs.append("Areas of specialisation: " + "; ".join(bits) + ".")
        if not paragraphs:
            return None
        return IRSection(key=key, title=self.mode.title_for(key), layout="paragraph", paragraphs=paragraphs,
                         source_ids=ids)

    def section_proforma_basis(self, key: str) -> IRSection | None:
        basis = self.v.proforma.get("application_basis", "")
        if not basis and self.ctx.vacancy is not None:
            basis = BASIS_FROM_MODE.get(str(self.ctx.vacancy.recruitment_mode), "")
        return self._rows_section(key, [
            ["17. Whether applying on deputation (ISTC / STC), absorption or re-employment basis", basis],
            ["18. Whether belongs to SC / ST", self._particular("sc_st_status")],
        ])

    def section_employer_certificate(self, key: str) -> IRSection | None:
        if not self.v.include_employer_certificate:
            return None
        name = self.snap.personal_data.full_name or self.snap.personal_data.display_name() or "the applicant"
        return IRSection(
            key=key, title=self.mode.title_for(key), layout="certificate",
            paragraphs=["The information / details provided in the above application by the applicant are true and "
                        "correct as per the facts available on records. The applicant possesses the educational "
                        "qualifications and experience mentioned in the vacancy circular. If selected, the applicant "
                        "will be relieved immediately.",
                        "Also certified that:"],
            items=[f"(i) There is no vigilance or disciplinary case pending / contemplated against {name}.",
                   "(ii) The applicant's integrity is certified.",
                   "(iii) The APAR dossier in original is enclosed / photocopies of the APARs for the last five "
                   "years, duly attested by an officer of the rank of Under Secretary to the Government of India or "
                   "above, are enclosed.",
                   "(iv) No major / minor penalty has been imposed on the applicant during the last ten years / a "
                   "list of major / minor penalties imposed during the last ten years is enclosed (as the case may "
                   "be)."],
            note="Countersigned (Employer / Cadre Controlling Authority, with seal)",
        )

    # ------------------------------------------------------------------ main
    def build_section(self, key: str) -> IRSection | None:
        if key.startswith("custom:"):
            return self.section_custom(key)
        handler = {
            "summary": self.section_summary,
            "competencies": self.section_competencies,
            "experience": self.section_experience,
            "projects": self.section_projects,
            "education": self.section_education,
            "publications": self.section_publications,
            "manuscripts": self.section_manuscripts,
            "skills": self.section_skills,
            "leadership": self.section_leadership,
            "awards": lambda k: self._simple_activity_section(k, {ActivityType.AWARD}, self.budget.awards),
            "patents": lambda k: self._simple_activity_section(k, {ActivityType.PATENT}, None),
            "presentations": lambda k: self._simple_activity_section(k, {ActivityType.PRESENTATION},
                                                                     self.budget.activities),
            "memberships": lambda k: self._simple_activity_section(k, {ActivityType.MEMBERSHIP}, None),
            "other_activities": lambda k: self._simple_activity_section(k, OTHER_ACTIVITY_TYPES,
                                                                        self.budget.activities),
            "training": self.section_training,
            "training_programmes": self.section_training_group,
            "courses": self.section_training_group,
            "certifications": self.section_training_group,
            "workshops": self.section_training_group,
            "other_qualifications": self.section_training_group,
            "languages": self.section_languages,
            "particulars": self.section_particulars,
            "requirements_matrix": self.section_requirements_matrix,
            "declaration": self.section_declaration,
            "proforma_particulars": self.section_proforma_particulars,
            "proforma_requirements": self.section_proforma_requirements,
            "proforma_statement": self.section_proforma_statement,
            "proforma_service": self.section_proforma_service,
            "proforma_additional": self.section_proforma_additional,
            "proforma_basis": self.section_proforma_basis,
            "employer_certificate": self.section_employer_certificate,
            "expertise": self.section_expertise,
            "career_timeline": self.section_career_timeline,
            "research_overview": self.section_research_overview,
            "grants": self.section_grants,
            "service": lambda k: self._simple_activity_section(k, SERVICE_TYPES, self.budget.activities),
            "references": self.section_references,
        }.get(key)
        return handler(key) if handler else None

    def compose(self) -> ResumeDocument:
        p = self.snap.personal_data
        custom_keys = [f"custom:{s.id}" for s in self.snap.of(RecordKind.CUSTOM_SECTION)
                       if s.data.include_by_default and self.eligible(s)]
        target_order = list(self.ctx.target.data.section_order) if self.ctx.target is not None else None
        order = resolve_order(self.mode, user_order=list(self.v.section_order), target_order=target_order,
                              hidden=list(self.v.hidden_sections), emphasis=self.ctx.emphasis, custom_keys=custom_keys)
        sections: list[IRSection] = []
        self.order = list(order)
        for key in order:
            sec = self.build_section(key)
            if sec is not None and not sec.is_empty():
                sections.append(sec)
        if self.snap.personal is not None:
            self._use(self.snap.personal)
        photo = ""
        if self.v.show_photo and self.ctx.photo_allowed and p.photo_path:
            photo = p.photo_path
        name = p.display_name()
        if not name:
            self.warnings.append("Your name is missing from the profile.")
        unconfirmed = [rid for rid in self.used if (r := self.snap.get(rid)) is not None
                       and self.snap.effective_verification(r) == Verification.UNCONFIRMED]
        review = [rid for rid in self.used if (r := self.snap.get(rid)) is not None
                  and self.snap.effective_confidentiality(r) == Confidentiality.REVIEW]
        if unconfirmed:
            self.warnings.append(f"{len(unconfirmed)} item(s) are awaiting your confirmation.")
        if review:
            self.warnings.append(f"{len(review)} item(s) require a disclosure review before export.")
        for gap in self.ctx.mandatory_gaps:
            self.warnings.append(f"Mandatory requirement not found in your profile: {gap}")
        subject = self.ctx.vacancy_title or (self.ctx.target.data.name if self.ctx.target is not None else "")
        headline = p.professional_title
        if self.mode.headline_from_vacancy and self.ctx.vacancy is not None and self.ctx.vacancy.title:
            vac = self.ctx.vacancy
            headline = "Application for the post of " + vac.title + (f", {vac.employer}" if vac.employer else "")
            if vac.reference:
                headline += f" (Advt. / Circular No. {vac.reference})"
        keywords = ", ".join(self.rel.taxonomy.label(c) for c in list(self.rel.concept_weights)[:12])
        return ResumeDocument(
            doc_type="resume", name=name, headline=headline, title_line=self.mode.title_line,
            contacts=self._contacts(), photo_path=photo, sections=sections, template_id=self.ctx.template_id,
            template_version=self.ctx.template_version, mode=self.mode.id, length=self.length.value,
            max_pages=self.v.max_pages, page_size=self.v.page_size, font_scale=self.v.font_scale,
            spacing=self.v.spacing, accent_color=self.v.accent_color, generated_at=utc_now_iso(),
            is_sample=self.ctx.is_sample,
            footer_note="Fictional sample profile — not a real person" if self.ctx.is_sample else "",
            warnings=self.warnings, trimmed=self.trimmed, source_revisions=dict(sorted(self.used.items())),
            chart_styles=dict(self.v.charts),
            metadata={"title": f"{name} — {self.mode.name}" if name else self.mode.name,
                      "subject": subject, "keywords": keywords, "creator": f"Resume Intelligence Studio {__version__}"},
        )
