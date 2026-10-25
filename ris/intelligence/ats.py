"""Resume document quality and ATS-compatibility checks (document quality is assessed separately from relevance)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ris.composition.ir import ResumeDocument
from ris.intelligence.relevance import RelevanceModel
from ris.rendering.specs import TemplateSpec

_FIRST_PERSON = re.compile(r"\b(?:I|me|my|mine|myself)\b")
_WEAK_START = re.compile(r"^(?:responsible for|worked on|involved in|helped|assisted in|duties included|tasked with)\b", re.I)
_PASSIVE = re.compile(r"\b(?:was|were|been|being)\s+\w+ed\b", re.I)
STANDARD_HEADINGS = {"summary", "experience", "education", "skills", "projects", "publications", "certifications",
                     "training", "awards", "leadership", "languages", "competencies", "profile", "employment",
                     "qualifications", "appointments", "research", "patents", "memberships", "presentations",
                     "particulars", "declaration", "manuscripts", "activities", "domains", "expertise"}


@dataclass
class QualityItem:
    severity: str  # info | warn | problem
    message: str


@dataclass
class QualityReport:
    score: float  # 0..1
    ats_safe_layout: bool
    items: list[QualityItem] = field(default_factory=list)
    keyword_coverage: float | None = None
    missing_keywords: list[str] = field(default_factory=list)

    @property
    def problems(self) -> list[QualityItem]:
        return [i for i in self.items if i.severity == "problem"]


def check_quality(doc: ResumeDocument, spec: TemplateSpec, relevance: RelevanceModel | None = None,
                  page_count: int | None = None) -> QualityReport:
    items: list[QualityItem] = []
    penalties = 0.0
    ats = spec.ats_safe or not spec.uses_tables
    if spec.columns.enabled:
        items.append(QualityItem("warn", "Two-column layout: some applicant tracking systems read columns out of order. "
                                         "Use ATS Minimal for online portals."))
        penalties += 0.05
    elif spec.uses_tables:
        items.append(QualityItem("info", "This template uses tables for layout; prefer ATS Minimal for portals."))
    if not doc.contacts or not any(c.key == "email" for c in doc.contacts):
        items.append(QualityItem("problem", "No email address in the header."))
        penalties += 0.15
    if not any(s.key in ("summary",) for s in doc.sections) and doc.mode not in ("government_biodata",):
        items.append(QualityItem("warn", "No professional summary."))
        penalties += 0.05
    nonstandard = [s.title for s in doc.sections if not s.key.startswith("custom:")
                   and not any(w in s.title.lower() for w in STANDARD_HEADINGS)]
    if nonstandard:
        items.append(QualityItem("info", "Unconventional headings: " + ", ".join(nonstandard)))
    bullets = [b.text for s in doc.sections for e in s.entries for b in e.bullets] + \
              [b.text for s in doc.sections for e in s.entries for c in e.children for b in c.bullets]
    long_b = [b for b in bullets if len(b) > 260]
    if long_b:
        items.append(QualityItem("warn", f"{len(long_b)} bullet(s) are longer than about three lines; tighten them."))
        penalties += min(0.1, 0.02 * len(long_b))
    weak = [b for b in bullets if _WEAK_START.search(b)]
    if weak:
        items.append(QualityItem("warn", f"{len(weak)} bullet(s) start with weak phrases such as 'Responsible for'. "
                                         "Use the rewriting assistant."))
        penalties += min(0.08, 0.02 * len(weak))
    fp = [b for b in bullets if _FIRST_PERSON.search(b)]
    if fp:
        items.append(QualityItem("warn", f"{len(fp)} bullet(s) use first-person pronouns."))
        penalties += 0.03
    passive = [b for b in bullets if _PASSIVE.search(b)]
    if len(passive) > 3:
        items.append(QualityItem("info", f"{len(passive)} bullet(s) use passive voice."))
    exp = doc.section("experience")
    if exp is not None and exp.layout == "entries" and exp.entries and not exp.entries[0].bullets:
        items.append(QualityItem("warn", "Your most recent position has no achievements listed."))
        penalties += 0.05
    if page_count is not None:
        limit = doc.max_pages or {"one_page": 1, "two_pages": 2}.get(doc.length)
        if limit and page_count > limit:
            items.append(QualityItem("problem", f"{page_count} pages exceeds the {limit}-page target."))
            penalties += 0.1
    coverage = None
    missing: list[str] = []
    if relevance is not None and not relevance.is_empty:
        text = "\n".join(doc.text_fragments())
        present = relevance.taxonomy.concepts_in(text)
        wanted = [c for c, w in sorted(relevance.concept_weights.items(), key=lambda kv: (-kv[1], kv[0])) if w >= 0.7]
        if wanted:
            hit = [c for c in wanted if c in present]
            coverage = len(hit) / len(wanted)
            missing = [relevance.taxonomy.label(c) for c in wanted if c not in present][:10]
            if coverage < 0.6:
                items.append(QualityItem("warn", f"The resume mentions {coverage:.0%} of the key vacancy terms. "
                                                 "Missing: " + ", ".join(missing[:6]) +
                                                 ". Add them only where your records support them."))
                penalties += 0.1 * (0.6 - coverage) / 0.6
    if not items:
        items.append(QualityItem("info", "No document-quality issues detected."))
    return QualityReport(score=max(0.0, round(1.0 - penalties, 3)), ats_safe_layout=ats, items=items,
                         keyword_coverage=coverage, missing_keywords=missing)
