"""Profile completeness computed from real data (no placeholders, no fake metrics)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ris.domain.enums import FACT_KINDS, Confidentiality, RecordKind, SkillCategory, Verification
from ris.services.profile import ProfileSnapshot


@dataclass
class SectionScore:
    key: str
    title: str
    score: float  # 0..1
    items_done: int
    items_total: int
    actions: list[str] = field(default_factory=list)
    optional: bool = False

    @property
    def percent(self) -> int:
        return round(self.score * 100)


@dataclass
class Completeness:
    sections: list[SectionScore]
    verified_share: float
    classified_share: float
    fact_count: int

    @property
    def overall(self) -> int:
        req = [s for s in self.sections if not s.optional]
        if not req:
            return 0
        return round(100 * sum(s.score for s in req) / len(req))

    def top_actions(self, n: int = 6) -> list[str]:
        out: list[str] = []
        for s in sorted(self.sections, key=lambda x: (x.optional, x.score)):
            out.extend(s.actions)
        return out[:n]


def _sec(key: str, title: str, checks: list[tuple[bool, str]], optional: bool = False) -> SectionScore:
    done = sum(1 for ok, _ in checks if ok)
    total = len(checks)
    actions = [msg for ok, msg in checks if not ok]
    return SectionScore(key, title, (done / total) if total else 1.0, done, total, actions, optional)


def compute(snap: ProfileSnapshot) -> Completeness:
    p = snap.personal_data
    sections: list[SectionScore] = []
    sections.append(_sec("personal", "Personal & contact", [
        (bool(p.full_name), "Add your full name"),
        (bool(p.professional_title), "Add a professional title"),
        (bool(p.email), "Add an email address"),
        (bool(p.phone), "Add a telephone number"),
        (bool(p.city and p.country), "Add your city and country"),
    ]))
    summaries = snap.of(RecordKind.SUMMARY)
    sections.append(_sec("summary", "Professional summaries", [
        (len(summaries) >= 1, "Write at least one professional summary"),
        (len(summaries) >= 2, "Add a second summary for a different focus (e.g. defence technology)"),
    ]))
    positions = snap.of(RecordKind.POSITION)
    pos_checks: list[tuple[bool, str]] = [(len(positions) >= 1, "Add your current position")]
    for pos in positions:
        d = pos.data
        pos_checks.append((bool(d.designation and d.organisation), f"Complete designation and organisation for '{pos.title}'"))
        pos_checks.append((bool(d.start), f"Add a start date for '{pos.title}'"))
        pos_checks.append((bool(d.is_current or d.end), f"Add an end date (or mark current) for '{pos.title}'"))
        n_bul = len(snap.kids(pos.id, RecordKind.BULLET)) + sum(
            len(snap.kids(a.id, RecordKind.BULLET)) for a in snap.kids(pos.id, RecordKind.ASSIGNMENT)
        )
        pos_checks.append((n_bul >= 2, f"Add at least two achievements or responsibilities to '{pos.title}'"))
    sections.append(_sec("experience", "Experience", pos_checks))

    edu = snap.of(RecordKind.EDUCATION)
    edu_checks: list[tuple[bool, str]] = [(len(edu) >= 1, "Add your qualifications")]
    for e in edu:
        d = e.data
        edu_checks.append((bool(d.institution or d.issuer), f"Add the institution for '{e.title}'"))
        edu_checks.append((bool(d.end or d.status != "completed"), f"Add the completion year for '{e.title}'"))
    sections.append(_sec("education", "Education", edu_checks))

    skills = snap.of(RecordKind.SKILL)
    categorised = [s for s in skills if s.data.category != SkillCategory.OTHER.value]
    sections.append(_sec("skills", "Skills & technologies", [
        (len(skills) >= 5, "Add at least five skills"),
        (len(skills) >= 12, "Add more skills so different resumes can draw on them"),
        (bool(skills) and len(categorised) == len(skills), "Assign a category to every skill"),
    ]))
    projects = snap.of(RecordKind.PROJECT)
    proj_checks: list[tuple[bool, str]] = [(len(projects) >= 1, "Add a project")]
    for pr in projects:
        d = pr.data
        proj_checks.append((bool(d.role), f"State your role in '{pr.title}'"))
        proj_checks.append((bool(d.results or d.metrics), f"Record results for '{pr.title}'"))
    sections.append(_sec("projects", "Projects & achievements", proj_checks))

    pubs = snap.of(RecordKind.PUBLICATION)
    sections.append(_sec("publications", "Research & publications", [
        (len(pubs) >= 1, "Add publications or manuscripts (optional for non-research roles)"),
        (all(bool(x.data.venue) for x in pubs) if pubs else False, "Add venues to every publication"),
    ], optional=True))
    acts = snap.of(RecordKind.ACTIVITY)
    sections.append(_sec("leadership", "Leadership & responsibilities", [
        (len(acts) >= 1, "Add leadership roles, committees or other responsibilities"),
    ], optional=True))

    facts = [r for r in snap.facts() if r.kind != RecordKind.PERSONAL]
    n = len(facts)
    verified = sum(1 for r in facts if r.verification != Verification.UNCONFIRMED)
    classified = sum(1 for r in facts if r.confidentiality != Confidentiality.REVIEW)
    return Completeness(
        sections=sections,
        verified_share=(verified / n) if n else 0.0,
        classified_share=(classified / n) if n else 0.0,
        fact_count=sum(1 for r in snap.records.values() if r.kind in FACT_KINDS),
    )
