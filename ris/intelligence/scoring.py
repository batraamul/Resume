"""Transparent, deterministic alignment scoring (VAC-05..09).

Three assessments are kept separate:
1. Evidence-based vacancy relevance (the weighted score below);
2. Formal recruitment eligibility (never scored — a checklist for official verification);
3. Resume document quality (from document checks; also 5% of the score by default).

The score measures how well your *recorded evidence* aligns with the stated
requirements. It is not a probability of selection, appointment or clearance,
and a missing mandatory qualification caps the overall band regardless of score.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ris.domain.enums import EvidenceStatus, RequirementCategory
from ris.intelligence.matching import RequirementResult

DEFAULT_WEIGHTS: dict[str, float] = {
    "essential": 35.0,
    "technical": 25.0,
    "evidence": 15.0,
    "experience": 10.0,
    "research": 10.0,
    "quality": 5.0,
}
COMPONENT_LABELS = {
    "essential": "Essential requirement coverage",
    "technical": "Technical and functional relevance",
    "evidence": "Verified achievements and evidence",
    "experience": "Experience and seniority alignment",
    "research": "Research and specialist credentials",
    "quality": "Readability and document quality",
}
SCORE_DISCLAIMER = ("Evidence-based alignment with the stated requirements. This is not a probability of "
                    "recruitment, selection, appointment or security clearance.")


def normalise_weights(weights: dict[str, float] | None) -> dict[str, float]:
    w = {k: float(v) for k, v in (weights or DEFAULT_WEIGHTS).items() if k in DEFAULT_WEIGHTS}
    for k in DEFAULT_WEIGHTS:
        w.setdefault(k, 0.0)
    if any(v < 0 for v in w.values()):
        raise ValueError("Weights cannot be negative.")
    total = sum(w.values())
    if total <= 0:
        raise ValueError("At least one weight must be greater than zero.")
    return {k: v / total for k, v in w.items()}


@dataclass
class Component:
    key: str
    label: str
    weight: float  # normalised (0..1), before redistribution
    value: float | None  # 0..1, None = not applicable
    effective_weight: float = 0.0
    points: float = 0.0
    explanation: str = ""


@dataclass
class EligibilityItem:
    text: str
    status: str
    note: str


@dataclass
class Assessment:
    score: float  # 0..100
    band: str
    components: list[Component]
    mandatory_gaps: list[str]
    mandatory_partial: list[str]
    eligibility: list[EligibilityItem]
    documentation: list[EligibilityItem]
    quality: float | None
    disclaimer: str = SCORE_DISCLAIMER
    notes: list[str] = field(default_factory=list)

    def explain(self) -> list[str]:
        lines = [f"Overall alignment: {self.score:.0f}/100 — {self.band}.", self.disclaimer]
        for c in self.components:
            if c.value is None:
                lines.append(f"• {c.label}: not applicable to this vacancy (weight redistributed).")
            else:
                lines.append(f"• {c.label}: {c.value:.0%} × weight {c.effective_weight:.0%} = {c.points:.1f} points. "
                             f"{c.explanation}")
        return lines


def _mean_credit(results: list[RequirementResult]) -> float | None:
    rs = [r for r in results if r.status not in (EvidenceStatus.NOT_APPLICABLE, EvidenceStatus.OFFICIAL_VERIFICATION)]
    if not rs:
        return None
    return sum(r.credit for r in rs) / len(rs)


def assess(
    results: list[RequirementResult],
    *,
    weights: dict[str, float] | None = None,
    quality: float | None = None,
) -> Assessment:
    w = normalise_weights(weights)
    cats = {c: [r for r in results if RequirementCategory(r.requirement.category) == c] for c in RequirementCategory}
    essential = [r for r in results if r.requirement.mandatory and RequirementCategory(r.requirement.category) in (
        RequirementCategory.MANDATORY_QUALIFICATION, RequirementCategory.EXPERIENCE, RequirementCategory.TECHNICAL,
        RequirementCategory.LEADERSHIP, RequirementCategory.RESEARCH)]
    technical = [r for r in results if RequirementCategory(r.requirement.category) in (
        RequirementCategory.TECHNICAL, RequirementCategory.DESIRABLE_QUALIFICATION, RequirementCategory.LEADERSHIP)
        and not r.requirement.mandatory]
    experience = cats[RequirementCategory.EXPERIENCE]
    research = cats[RequirementCategory.RESEARCH]

    comps: list[Component] = []

    def comp(key: str, value: float | None, explanation: str) -> None:
        comps.append(Component(key, COMPONENT_LABELS[key], w[key], value, explanation=explanation))

    ess_v = _mean_credit(essential)
    n_ok = sum(1 for r in essential if r.status in (EvidenceStatus.VERIFIED, EvidenceStatus.AWAITING_CONFIRMATION))
    comp("essential", ess_v, f"{n_ok} of {len(essential)} essential requirement(s) supported." if essential
         else "No essential requirements were identified.")
    tech_v = _mean_credit(technical)
    comp("technical", tech_v, f"{sum(1 for r in technical if r.credit >= 0.6)} of {len(technical)} technical/desirable "
         "requirement(s) supported." if technical else "No technical or desirable requirements were identified.")

    ev_items = [e for r in results for e in r.evidence]
    if ev_items:
        uniq = {e.record_id: e for e in ev_items}
        conf_share = sum(1 for e in uniq.values() if e.confirmed) / len(uniq)
        outcome_share = sum(1 for e in uniq.values() if e.has_outcome) / len(uniq)
        ev_v = 0.6 * conf_share + 0.4 * outcome_share
        comp("evidence", ev_v, f"{conf_share:.0%} of {len(uniq)} evidence record(s) confirmed; "
             f"{outcome_share:.0%} state outcomes or metrics.")
    else:
        comp("evidence", None, "No evidence records were matched.")

    exp_v = _mean_credit(experience)
    comp("experience", exp_v, f"{len(experience)} experience requirement(s) assessed." if experience
         else "No experience requirement was identified.")
    res_v = _mean_credit(research)
    comp("research", res_v, f"{len(research)} research requirement(s) assessed." if research
         else "No research requirement was identified.")
    comp("quality", quality, "From the document quality checks." if quality is not None
         else "Generate a resume to assess document quality.")

    avail = [c for c in comps if c.value is not None and c.weight > 0]
    total_w = sum(c.weight for c in avail)
    score = 0.0
    for c in comps:
        if c.value is not None and c.weight > 0 and total_w > 0:
            c.effective_weight = c.weight / total_w
            c.points = round(100 * c.effective_weight * c.value, 2)
            score += c.points
    score = round(score, 1)

    mand_qual = [r for r in results if r.requirement.mandatory and RequirementCategory(r.requirement.category) in (
        RequirementCategory.MANDATORY_QUALIFICATION, RequirementCategory.EXPERIENCE)]
    gaps = [r.requirement.text for r in mand_qual if r.status == EvidenceStatus.NOT_FOUND]
    partial = [r.requirement.text for r in mand_qual if r.status == EvidenceStatus.PARTIAL]
    if not avail:
        band = "Not enough requirements to assess"
    elif gaps:
        band = "Mandatory requirement not evidenced"
    elif score >= 75:
        band = "Strong evidence alignment"
    elif score >= 55:
        band = "Moderate evidence alignment"
    else:
        band = "Limited evidence alignment"
    notes = []
    if partial:
        notes.append("Some mandatory requirements are only partly supported; verify equivalence or add evidence.")
    elig = [EligibilityItem(r.requirement.text, r.status.value, r.explanation) for r in cats[RequirementCategory.ELIGIBILITY]]
    docs = [EligibilityItem(r.requirement.text, r.status.value, r.explanation) for r in cats[RequirementCategory.DOCUMENTATION]]
    return Assessment(score=score, band=band, components=comps, mandatory_gaps=gaps, mandatory_partial=partial,
                      eligibility=elig, documentation=docs, quality=quality, notes=notes)
