"""Career-readiness analysis: separate missing *profile data* from genuine *gaps* (VAC-12)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ris.domain.enums import EvidenceStatus, RecordKind, RequirementCategory, Verification
from ris.intelligence.matching import RequirementResult
from ris.services.profile import ProfileSnapshot


@dataclass
class ReadinessItem:
    requirement: str
    kind: str  # confirm | add_data | possible_gap | verify_officially | strengthen
    advice: str


@dataclass
class Readiness:
    items: list[ReadinessItem] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)

    def by_kind(self, kind: str) -> list[ReadinessItem]:
        return [i for i in self.items if i.kind == kind]


def analyse_readiness(results: list[RequirementResult], snap: ProfileSnapshot) -> Readiness:
    out = Readiness()
    has_edu = bool(snap.of(RecordKind.EDUCATION))
    has_pos = bool(snap.of(RecordKind.POSITION))
    has_skills = bool(snap.of(RecordKind.SKILL))
    has_pubs = bool(snap.of(RecordKind.PUBLICATION))
    unconfirmed_titles = {r.title.casefold() for r in snap.facts() if r.verification == Verification.UNCONFIRMED}
    for r in results:
        text = r.requirement.text
        cat = RequirementCategory(r.requirement.category)
        if r.status == EvidenceStatus.VERIFIED:
            if r.requirement.mandatory:
                out.strengths.append(text)
            continue
        if r.status == EvidenceStatus.OFFICIAL_VERIFICATION:
            out.items.append(ReadinessItem(text, "verify_officially",
                                           "Check this against official rules/records or prepare the document."))
            continue
        if r.status == EvidenceStatus.NOT_APPLICABLE:
            continue
        if r.status == EvidenceStatus.AWAITING_CONFIRMATION:
            out.items.append(ReadinessItem(text, "confirm",
                                           "Evidence exists but awaits your confirmation. Review and confirm it."))
            continue
        # partial or not found
        if cat in (RequirementCategory.MANDATORY_QUALIFICATION, RequirementCategory.DESIRABLE_QUALIFICATION) and not has_edu:
            out.items.append(ReadinessItem(text, "add_data", "Your qualifications are not recorded yet — add them first."))
        elif cat == RequirementCategory.EXPERIENCE and not has_pos:
            out.items.append(ReadinessItem(text, "add_data", "Your positions are not recorded yet — add them first."))
        elif cat == RequirementCategory.RESEARCH and not has_pubs:
            out.items.append(ReadinessItem(text, "add_data",
                                           "No publications are recorded. Add them if you have any; otherwise this "
                                           "is a gap to consider."))
        elif cat == RequirementCategory.TECHNICAL and not has_skills:
            out.items.append(ReadinessItem(text, "add_data", "Your skills are not recorded yet — add them first."))
        elif any(e.title.casefold() in unconfirmed_titles for e in r.evidence):
            out.items.append(ReadinessItem(text, "confirm", "Related records await confirmation."))
        elif r.status == EvidenceStatus.PARTIAL:
            out.items.append(ReadinessItem(text, "strengthen",
                                           "Partly supported. Add specific evidence (projects, outcomes) if you have "
                                           "it, or check the equivalence stated in the notice."))
        else:
            advice = ("Not found in your profile. If you have this experience, record it with evidence; if not, it "
                      "may be a genuine gap — consider relevant training, a project or a certification.")
            if r.requirement.mandatory and cat == RequirementCategory.MANDATORY_QUALIFICATION:
                advice = ("Mandatory qualification not found in your profile. If you hold it, add it; otherwise you "
                          "may not meet the essential criteria. Check with the recruiting authority.")
            out.items.append(ReadinessItem(text, "possible_gap", advice))
    return out
