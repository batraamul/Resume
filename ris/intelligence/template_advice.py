"""Which templates suit this profile (advice only; offline rules, no generative model).

The advice reads facts already recorded in the profile — sectors worked in, length of service,
publications, projects, career targets and vacancies — and matches them with the resume modes each
template was designed for. Every suggestion carries the reasons, so the user can judge it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ris.domain import dates
from ris.domain.enums import RecordKind, RecruitmentMode, Sector

GOVERNMENT_SECTORS = {Sector.CENTRAL_GOVERNMENT.value, Sector.STATE_GOVERNMENT.value, Sector.DEFENCE.value,
                      Sector.PSU.value, Sector.AUTONOMOUS.value}

#: Profile trait → (resume modes that serve it, reason shown to the user).
TRAIT_MODES: dict[str, tuple[tuple[str, ...], str]] = {
    "deputation": (("deputation_proforma",),
                   "a vacancy in your list is filled on deputation or absorption"),
    "government": (("government_biodata", "senior_scientist", "defence_technical"),
                   "you have government, defence or public-sector service"),
    "research": (("scientific_research", "academic_cv", "research_portfolio", "senior_scientist"),
                 "you have a publication record"),
    "senior": (("executive_summary", "senior_scientist"),
               "you have fifteen or more years of experience"),
    "technical": (("technical_specialist", "defence_technical", "project_portfolio"),
                  "you have recorded projects and technical skills"),
}

#: Filters offered in the template gallery: key → label.
GALLERY_FILTERS: list[tuple[str, str]] = [
    ("all", "All templates"),
    ("recommended", "Recommended for my profile"),
    ("ats", "ATS-safe (online portals)"),
    ("government", "Government, defence & deputation"),
    ("executive", "Executive & leadership"),
    ("research", "Scientific & academic"),
    ("technical", "Technical & projects"),
    ("two_column", "Two-column"),
    ("graphical", "Graphical (interviews, networking)"),
    ("custom", "My own templates"),
]

_TAG_MODES = {
    "government": {"government_biodata", "deputation_proforma", "senior_scientist", "defence_technical"},
    "executive": {"executive_summary", "senior_scientist", "senior_graphical"},
    "research": {"scientific_research", "academic_cv", "research_portfolio"},
    "technical": {"technical_specialist", "project_portfolio", "defence_technical"},
}


def template_tags(spec) -> set[str]:
    """Gallery filter keys that apply to a template."""
    tags = {"all"}
    modes = set(spec.recommended_modes)
    for tag, wanted in _TAG_MODES.items():
        if modes & wanted:
            tags.add(tag)
    if spec.ats_safe:
        tags.add("ats")
    if spec.columns.enabled:
        tags.add("two_column")
    if spec.graphics.enabled:
        tags.add("graphical")
    if not spec.builtin:
        tags.add("custom")
    return tags


@dataclass
class ProfileTraits:
    years: float = 0.0
    publications: int = 0
    projects: int = 0
    skills: int = 0
    positions: int = 0
    government: bool = False
    deputation_vacancy: bool = False
    preferred_templates: dict[str, str] = field(default_factory=dict)  # template id → career target name

    @property
    def traits(self) -> list[str]:
        out = []
        if self.deputation_vacancy:
            out.append("deputation")
        if self.government:
            out.append("government")
        if self.publications >= 3:
            out.append("research")
        if self.years >= 15:
            out.append("senior")
        if self.projects >= 2 or self.skills >= 8:
            out.append("technical")
        return out

    @property
    def is_empty(self) -> bool:
        return not (self.positions or self.publications or self.projects or self.skills)


def profile_traits(snapshot, today: date | None = None) -> ProfileTraits:
    today = today or date.today()
    t = ProfileTraits()
    positions = snapshot.of(RecordKind.POSITION)
    t.positions = len(positions)
    earliest: tuple[int, int] | None = None
    for p in positions:
        if str(getattr(p.data, "sector", "") or "") in GOVERNMENT_SECTORS:
            t.government = True
        try:
            start = dates.parse_or_none(getattr(p.data, "start", ""))
        except ValueError:
            start = None
        if start is not None:
            key = (start.year, start.month or 1)
            earliest = key if earliest is None or key < earliest else earliest
    if earliest is not None:
        t.years = max(0.0, (today.year - earliest[0]) + (today.month - earliest[1]) / 12)
    personal = snapshot.personal_data
    if getattr(personal, "present_pay_level", "") or getattr(personal, "date_of_entry_into_service", ""):
        t.government = True
    t.publications = len(snapshot.of(RecordKind.PUBLICATION))
    t.projects = len(snapshot.of(RecordKind.PROJECT))
    t.skills = len(snapshot.of(RecordKind.SKILL))
    for v in snapshot.of(RecordKind.VACANCY):
        if str(v.data.recruitment_mode) in (RecruitmentMode.DEPUTATION.value, RecruitmentMode.ABSORPTION.value):
            t.deputation_vacancy = True
    for c in snapshot.of(RecordKind.CAREER_TARGET):
        if c.data.preferred_template:
            t.preferred_templates.setdefault(c.data.preferred_template, c.data.name or "your career target")
    return t


@dataclass
class TemplateSuggestion:
    template_id: str
    score: int
    reasons: list[str]

    def reason_text(self) -> str:
        if not self.reasons:
            return ""
        return "Suggested because " + "; ".join(self.reasons) + "."


def recommend_templates(snapshot, templates, *, limit: int = 6, today: date | None = None) -> list[TemplateSuggestion]:
    """Rank templates for this profile. Returns at most ``limit`` suggestions, best first."""
    traits = profile_traits(snapshot, today)
    if traits.is_empty:
        starters = ["ats_minimal", "corporate_blue", "modern_minimal", "executive_classic", "government_cv"]
        available = {t.id for t in templates}
        return [TemplateSuggestion(tid, 1, ["it is a sound starting point — add your experience, projects and "
                                            "publications to get suggestions that fit your profile"])
                for tid in starters if tid in available][:limit]
    active = traits.traits
    out: list[TemplateSuggestion] = []
    for spec in templates:
        modes = set(spec.recommended_modes)
        score, reasons = 0, []
        if spec.id in traits.preferred_templates:
            score += 4
            reasons.append(f"it is the preferred template of '{traits.preferred_templates[spec.id]}'")
        for trait in active:
            wanted, why = TRAIT_MODES[trait]
            if modes & set(wanted):
                score += 10 if trait == "deputation" else 2  # a prescribed form outranks style
                reasons.append(why)
        if not score:
            continue
        if spec.ats_safe and "deputation" not in active:
            score += 1
            reasons.append("it is safe for online application portals")
        if spec.graphics.enabled:
            score -= 1
            reasons.append("use it for interviews and networking, not for the application itself")
        out.append(TemplateSuggestion(spec.id, score, reasons))
    order = {spec.id: i for i, spec in enumerate(templates)}
    out.sort(key=lambda s: (-s.score, order.get(s.template_id, 999)))
    return out[:limit]
