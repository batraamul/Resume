"""Vacancy analysis facade: requirements → evidence → scores, relevance, ordering emphasis and bio-data matrix."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from ris.domain.enums import EvidenceStatus, RequirementCategory
from ris.domain.models import CareerTarget, Requirement, Vacancy
from ris.intelligence.matching import EvidenceMatcher, RequirementResult
from ris.intelligence.presets import default_presets
from ris.intelligence.readiness import Readiness, analyse_readiness
from ris.intelligence.relevance import RelevanceModel
from ris.intelligence.scoring import Assessment, assess
from ris.intelligence.taxonomy import Taxonomy, default_taxonomy
from ris.intelligence.vacancy import extract_requirements
from ris.services.profile import ProfileSnapshot

CATEGORY_WEIGHT = {
    RequirementCategory.MANDATORY_QUALIFICATION: 1.0,
    RequirementCategory.EXPERIENCE: 1.0,
    RequirementCategory.TECHNICAL: 0.85,
    RequirementCategory.DESIRABLE_QUALIFICATION: 0.6,
    RequirementCategory.RESEARCH: 0.7,
    RequirementCategory.LEADERSHIP: 0.7,
}


@dataclass
class VacancyAnalysis:
    requirements: list[Requirement]
    results: list[RequirementResult]
    assessment: Assessment
    readiness: Readiness
    relevance: RelevanceModel
    emphasis: dict[str, float] = field(default_factory=dict)

    def matrix(self) -> list[tuple[str, str, list[str]]]:
        """Rows for the bio-data 'required vs possessed' table (confirmed evidence only)."""
        rows = []
        for r in self.results:
            cat = RequirementCategory(r.requirement.category)
            if cat in (RequirementCategory.ELIGIBILITY, RequirementCategory.DOCUMENTATION):
                continue
            if r.status == EvidenceStatus.NOT_APPLICABLE:
                continue
            if cat in (RequirementCategory.TECHNICAL, RequirementCategory.LEADERSHIP) and not r.requirement.mandatory \
                    and not r.possessed:
                continue
            label = ("Essential: " if r.requirement.mandatory else "Desirable: ") + r.requirement.text
            rows.append((label, r.possessed, list(r.possessed_sources)))
        return rows

    def mandatory_gaps(self) -> list[str]:
        return list(self.assessment.mandatory_gaps)


def target_relevance(target: CareerTarget | None, taxonomy: Taxonomy | None = None) -> RelevanceModel:
    if target is None:
        return RelevanceModel.empty()
    texts: list[tuple[str, float]] = [(" ; ".join(target.keywords), 0.9), (" ; ".join(target.emphasis_areas), 0.7),
                                      (target.description, 0.5)]
    preset = default_presets().preset(target.preset_id) if target.preset_id else None
    if preset is not None:
        texts.append((" ; ".join(preset.keywords), 0.6))
    org = default_presets().org(target.org_profile_id) if target.org_profile_id else None
    if org is not None:
        texts.append((" ; ".join(org.domains), 0.4))
    return RelevanceModel.from_weighted_texts(texts, taxonomy)


def analyse(
    snapshot: ProfileSnapshot,
    vacancy: Vacancy,
    *,
    target: CareerTarget | None = None,
    weights: dict[str, float] | None = None,
    quality: float | None = None,
    taxonomy: Taxonomy | None = None,
    today: date | None = None,
) -> VacancyAnalysis:
    tax = taxonomy or default_taxonomy()
    reqs = list(vacancy.requirements) or extract_requirements(vacancy, tax)
    matcher = EvidenceMatcher(snapshot, tax, today=today)
    results = matcher.match_all(reqs)
    assessment = assess(results, weights=weights, quality=quality)
    readiness = analyse_readiness(results, snapshot)
    texts = [(r.text, CATEGORY_WEIGHT.get(RequirementCategory(r.category), 0.5)) for r in reqs
             if RequirementCategory(r.category) in CATEGORY_WEIGHT]
    rel = RelevanceModel.from_weighted_texts(texts, tax)
    if target is not None:
        rel = rel.merged(target_relevance(target, tax))
    counts = Counter(RequirementCategory(r.category) for r in reqs)
    n = max(sum(counts.values()) - counts[RequirementCategory.ELIGIBILITY] - counts[RequirementCategory.DOCUMENTATION], 1)
    emphasis = {
        "research": counts[RequirementCategory.RESEARCH] / n,
        "leadership": counts[RequirementCategory.LEADERSHIP] / n,
        "education": (counts[RequirementCategory.MANDATORY_QUALIFICATION]
                      + counts[RequirementCategory.DESIRABLE_QUALIFICATION]) / n,
        "projects": counts[RequirementCategory.TECHNICAL] / n,
    }
    return VacancyAnalysis(reqs, results, assessment, readiness, rel, emphasis)
