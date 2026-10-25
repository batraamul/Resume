"""Evidence mapping: link each vacancy requirement to supporting profile records.

Statuses (VAC-04):
* verified — supported by records you have confirmed;
* awaiting_confirmation — supported only by records still awaiting confirmation;
* partial — some of the requirement is supported, or an equivalence needs checking;
* not_found — no supporting record;
* not_applicable — set by you;
* official_verification — eligibility and documentation conditions the software must not decide.

Confidential records are never used as evidence, so nothing derived from them
can reach a document. Expertise is never inferred from durations or keywords
alone; matches only point at records you entered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from ris.domain import dates
from ris.domain.enums import (
    Confidentiality,
    EducationStatus,
    EvidenceStatus,
    Involvement,
    PublicationStatus,
    QualificationType,
    RecordKind,
    RequirementCategory,
    Verification,
    label,
)
from ris.domain.models import Requirement
from ris.intelligence.taxonomy import Taxonomy, default_taxonomy
from ris.intelligence.text import content_tokens
from ris.services.profile import ProfileSnapshot
from ris.storage.repository import Record

LEVEL_RANK = {"doctorate": 4, "masters": 3, "bachelors": 2, "diploma": 1, "higher_secondary": 0, "secondary": 0,
              "certificate": 0, "other": 0}
CREDIT = {
    EvidenceStatus.VERIFIED: 1.0,
    EvidenceStatus.AWAITING_CONFIRMATION: 0.6,
    EvidenceStatus.PARTIAL: 0.5,
    EvidenceStatus.NOT_FOUND: 0.0,
}
EVIDENCE_KINDS = (RecordKind.SKILL, RecordKind.BULLET, RecordKind.POSITION, RecordKind.ASSIGNMENT, RecordKind.PROJECT,
                  RecordKind.PUBLICATION, RecordKind.ACTIVITY, RecordKind.EDUCATION, RecordKind.CUSTOM_ENTRY,
                  RecordKind.EXPERTISE, RecordKind.TRAINING)


@dataclass
class EvidenceItem:
    record_id: str
    kind: str
    title: str
    reason: str
    confirmed: bool
    has_outcome: bool = False


@dataclass
class RequirementResult:
    requirement: Requirement
    status: EvidenceStatus
    evidence: list[EvidenceItem] = field(default_factory=list)
    explanation: str = ""
    possessed: str = ""  # suggested "qualification possessed" wording (from confirmed records only)
    possessed_sources: list[str] = field(default_factory=list)
    credit: float = 0.0

    @property
    def status_label(self) -> str:
        return label(self.status)


def _clip(text: str, limit: int = 180) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


def possessed_phrase(r: Record) -> str:
    """How one confirmed record reads in a 'qualifications / experience possessed' column."""
    d = r.data
    if r.kind == RecordKind.BULLET:
        return _clip(d.text).rstrip(".")
    if r.kind == RecordKind.POSITION:
        return ", ".join(x for x in (d.designation, d.organisation) if x) or r.title
    if r.kind == RecordKind.PROJECT:
        return f"Project: {_clip(r.title, 120)}"
    if r.kind == RecordKind.PUBLICATION:
        return f"Publication: {_clip(r.title, 140)}"
    if r.kind == RecordKind.SKILL:
        return f"Skill: {r.title}"
    if r.kind == RecordKind.TRAINING:
        return f"Training: {_clip(r.title, 120)}"
    return _clip(r.title, 140)


class EvidenceMatcher:
    def __init__(self, snapshot: ProfileSnapshot, taxonomy: Taxonomy | None = None, today=None) -> None:
        self.snap = snapshot
        self.tax = taxonomy or default_taxonomy()
        self.today = today
        self._concept_cache: dict[str, set[str]] = {}
        self._token_cache: dict[str, set[str]] = {}
        self.records = [r for r in snapshot.records.values()
                        if r.kind in EVIDENCE_KINDS and snapshot.effective_confidentiality(r) != Confidentiality.CONFIDENTIAL]
        self.records.sort(key=lambda r: (r.kind.value, r.sort_order, r.id))
        self._record_ids = {r.id for r in self.records}

    # ------------------------------------------------------------------ helpers
    def _text(self, r: Record) -> str:
        parts = [r.data.display_title(), r.data.search_text()]
        if r.kind == RecordKind.SKILL:
            parts.extend(r.data.aliases)
        return "\n".join(parts)

    def concepts(self, r: Record) -> set[str]:
        c = self._concept_cache.get(r.id)
        if c is None:
            c = self.tax.concepts_in(self._text(r))
            self._concept_cache[r.id] = c
        return c

    def toks(self, r: Record) -> set[str]:
        t = self._token_cache.get(r.id)
        if t is None:
            t = set(content_tokens(self._text(r), self.tax.stopwords))
            self._token_cache[r.id] = t
        return t

    def confirmed(self, r: Record) -> bool:
        return self.snap.effective_verification(r) != Verification.UNCONFIRMED

    @staticmethod
    def _has_outcome(r: Record) -> bool:
        d = r.data
        return bool(getattr(d, "metrics", None) or getattr(d, "outcome", "") or getattr(d, "results", ""))

    def _item(self, r: Record, reason: str) -> EvidenceItem:
        return EvidenceItem(r.id, r.kind.value, r.title, reason, self.confirmed(r), self._has_outcome(r))

    # ------------------------------------------------------------------ qualifications
    def _degrees(self) -> list[Record]:
        return [r for r in self.records if r.kind == RecordKind.EDUCATION
                and QualificationType(r.data.qualification_type) in (QualificationType.DEGREE, QualificationType.DIPLOMA)]

    def match_qualification(self, req: Requirement) -> RequirementResult:
        levels = self.tax.degree_levels_in(req.text)
        discs = self.tax.disciplines_in(req.text)
        if not levels:
            return self.match_concepts(req)
        need_rank = min(LEVEL_RANK.get(lv, 0) for lv in levels)
        best: tuple[int, Record, str] | None = None  # (score, record, reason)
        for e in self._degrees():
            d = e.data
            if d.status == EducationStatus.PLANNED.value:
                continue
            rank = LEVEL_RANK.get(d.level, 0)
            if rank < need_rank:
                continue
            rec_discs = self.tax.disciplines_in(" ".join([d.discipline, d.specialisation, d.degree]))
            if not discs:
                disc_score, disc_reason = 2, "any discipline accepted"
            elif rec_discs & discs:
                disc_score, disc_reason = 2, "discipline matches"
            elif any(rd in self.tax.related_disciplines(x) or x in self.tax.related_disciplines(rd)
                     for x in discs for rd in rec_discs):
                disc_score, disc_reason = 1, "related discipline — check the equivalence stated in the notice"
            else:
                disc_score, disc_reason = 0, "different discipline"
            status_score = 2 if d.status == EducationStatus.COMPLETED.value else 1
            score = disc_score * 10 + status_score * 3 + (1 if self.confirmed(e) else 0)
            reason = f"{label(EducationStatus(d.status)).lower()}; {disc_reason}"
            if best is None or score > best[0]:
                best = (score, e, reason)
        if best is None:
            return RequirementResult(req, EvidenceStatus.NOT_FOUND,
                                     explanation="No qualification at the required level was found in your profile.")
        score, rec, reason = best
        disc_score = score // 10
        completed = rec.data.status == EducationStatus.COMPLETED.value
        item = self._item(rec, reason)
        if disc_score == 0:
            status = EvidenceStatus.PARTIAL
            expl = "A qualification at the required level exists, but in a different discipline."
        elif disc_score == 1 or not completed:
            status = EvidenceStatus.PARTIAL
            expl = ("Qualification is ongoing — not yet awarded." if not completed
                    else "Related discipline; the recruiting authority decides equivalence.")
        else:
            status = EvidenceStatus.VERIFIED if self.confirmed(rec) else EvidenceStatus.AWAITING_CONFIRMATION
            expl = "Matching qualification found. Recognition and equivalence are decided by the recruiting authority."
        d = rec.data
        possessed = ""
        if self.confirmed(rec) and disc_score > 0:
            inst = ", ".join(x for x in (d.institution, d.university) if x)
            when = (dates.format_date(d.end, "year") if completed else "ongoing")
            possessed = f"{d.degree}{', ' + d.discipline if d.discipline else ''} — {inst} ({when})".strip()
        return RequirementResult(req, status, [item], expl, possessed, [rec.id] if possessed else [])

    # ------------------------------------------------------------------ experience
    def _positions(self) -> list[Record]:
        return [r for r in self.records if r.kind == RecordKind.POSITION]

    def total_experience_months(self, confirmed_only: bool = False) -> int:
        """Conservative total months across primary positions (overlaps merged)."""
        spans = []
        for p in self._positions():
            if confirmed_only and not self.confirmed(p):
                continue
            s = dates.parse_or_none(p.data.start)
            if not s:
                continue
            if p.data.is_current:
                end = self.today or date.today()
            else:
                e = dates.parse_or_none(p.data.end)
                if not e:
                    continue
                end = e.earliest()
            spans.append((s.latest(), end))
        spans.sort()
        total_days = 0
        cur_s = cur_e = None
        for s, e in spans:
            if cur_s is None:
                cur_s, cur_e = s, e
            elif s <= cur_e:
                cur_e = max(cur_e, e)
            else:
                total_days += (cur_e - cur_s).days
                cur_s, cur_e = s, e
        if cur_s is not None:
            total_days += (cur_e - cur_s).days
        return max(int(total_days / 30.44), 0)

    def match_experience(self, req: Requirement) -> RequirementResult:
        m = re.search(r"(\d{1,2})\s*(?:\+\s*)?(?:or\s+more\s+)?years?", req.text, re.I)
        years_req = int(m.group(1)) if m else None
        if re.search(r"\b(?:level\s*\d+|pay\s+level|regular\s+(?:basis|service)|analogous|grade pay|pay band)\b",
                     req.text, re.I):
            return RequirementResult(req, EvidenceStatus.OFFICIAL_VERIFICATION,
                                     explanation="Service-condition experience (pay level, regular service, analogous "
                                                 "post) must be verified from official service records.")
        concepts = self.tax.concepts_in(req.text)
        relevant: list[Record] = []
        for p in self._positions():
            text_concepts = set(self.concepts(p))
            for ch in self.snap.kids(p.id):
                if ch.kind in (RecordKind.BULLET, RecordKind.ASSIGNMENT) and ch.id in self._record_ids:
                    text_concepts |= self.concepts(ch)
            if not concepts or text_concepts & concepts:
                relevant.append(p)
        months_all = self.total_experience_months()
        months_conf = self.total_experience_months(confirmed_only=True)
        rel_months = 0
        for p in relevant:
            n = dates.conservative_months(p.data.start, p.data.end, p.data.is_current, self.today)
            rel_months += n or 0
        have_years = (rel_months if concepts else months_all) / 12
        evidence = [self._item(p, "relevant experience" if concepts else "employment period") for p in relevant[:4]]
        if years_req is None:
            status = (EvidenceStatus.VERIFIED if relevant and all(self.confirmed(p) for p in relevant)
                      else EvidenceStatus.AWAITING_CONFIRMATION if relevant else EvidenceStatus.NOT_FOUND)
            expl = "Relevant experience found in your positions." if relevant else "No relevant experience found."
        else:
            if have_years >= years_req:
                status = (EvidenceStatus.VERIFIED if all(self.confirmed(p) for p in relevant) and months_conf
                          else EvidenceStatus.AWAITING_CONFIRMATION)
                expl = f"About {have_years:.0f} years of matching experience recorded (required {years_req})."
            elif have_years >= 0.7 * years_req:
                status = EvidenceStatus.PARTIAL
                expl = f"About {have_years:.1f} years of matching experience recorded; {years_req} required."
            else:
                status = EvidenceStatus.NOT_FOUND if not relevant else EvidenceStatus.PARTIAL
                expl = f"About {have_years:.1f} years of matching experience recorded; {years_req} required."
            expl += " Calculated conservatively from your position dates; the employer verifies service records."
        possessed = ""
        sources: list[str] = []
        conf_rel = [p for p in relevant if self.confirmed(p)]
        if conf_rel and status in (EvidenceStatus.VERIFIED, EvidenceStatus.PARTIAL):
            starts = [dates.parse_or_none(p.data.start) for p in conf_rel]
            starts = [s for s in starts if s]
            if starts:
                first = min(starts)
                areas = sorted({self.tax.label(c) for p in conf_rel for c in self.concepts(p) & concepts})[:4] \
                    if concepts else []
                yrs = int(have_years)
                possessed = (f"At least {yrs} years (since {first.format('mon_year')})"
                             + (f" in {', '.join(areas).lower()}" if areas else "")
                             + ": " + "; ".join(f"{p.data.designation}, {p.data.organisation}" for p in conf_rel[:3]))
                sources = [p.id for p in conf_rel[:3]]
        return RequirementResult(req, status, evidence, expl, possessed, sources)

    # ------------------------------------------------------------------ concept matching
    def match_concepts(self, req: Requirement, kinds: tuple[RecordKind, ...] | None = None,
                       require_leading: bool = False) -> RequirementResult:
        want = self.tax.concepts_in(req.text)
        pool = [r for r in self.records if kinds is None or r.kind in kinds]
        if require_leading:
            pool = [r for r in pool if getattr(r.data, "involvement", None) in
                    (Involvement.LEADING.value, Involvement.COORDINATING.value)
                    or r.kind in (RecordKind.ASSIGNMENT,)]
        if not want:
            words = set(content_tokens(req.text, self.tax.stopwords))
            if not words:
                return RequirementResult(req, EvidenceStatus.NOT_FOUND,
                                         explanation="No recognisable terms; review this requirement manually.")
            scored = []
            for r in pool:
                overlap = words & self.toks(r)
                if overlap:
                    scored.append((len(overlap), r, overlap))
            scored.sort(key=lambda t: (-t[0], t[1].kind.value, t[1].id))
            best = scored[:4]
            cover = (best[0][0] / len(words)) if best else 0.0
            evidence = [self._item(r, "shares: " + ", ".join(sorted(ov)[:5])) for _, r, ov in best]
            return self._status_from_cover(req, cover, evidence, [r for _, r, _ in best],
                                           "No recognised technical concepts; matched on wording only.")
        covered: dict[str, list[Record]] = {}
        for r in pool:
            for c in self.concepts(r) & want:
                covered.setdefault(c, []).append(r)
        cover = len(covered) / len(want)
        contributing: list[Record] = []
        reasons: dict[str, set[str]] = {}
        for c, recs in sorted(covered.items()):
            recs.sort(key=lambda r: (not self.confirmed(r), r.kind != RecordKind.PROJECT, r.kind != RecordKind.BULLET,
                                     r.id))
            for r in recs[:2]:
                if r not in contributing:
                    contributing.append(r)
                reasons.setdefault(r.id, set()).add(self.tax.label(c))
        evidence = [self._item(r, "covers " + ", ".join(sorted(reasons.get(r.id, set())))) for r in contributing[:6]]
        missing = sorted(self.tax.label(c) for c in want - set(covered))
        note = f"Not evidenced: {', '.join(missing)}." if missing else ""
        return self._status_from_cover(req, cover, evidence, contributing, note)

    def _status_from_cover(self, req: Requirement, cover: float, evidence: list[EvidenceItem],
                           records: list[Record], note: str) -> RequirementResult:
        if cover >= 0.75 and records:
            all_conf = all(e.confirmed for e in evidence[:3])
            status = EvidenceStatus.VERIFIED if all_conf else EvidenceStatus.AWAITING_CONFIRMATION
            expl = "Supported by your records."
        elif cover >= 0.3 and records:
            status = EvidenceStatus.PARTIAL
            expl = "Partly supported by your records."
        else:
            status = EvidenceStatus.NOT_FOUND
            expl = "No supporting evidence found in your profile."
        if note:
            expl += " " + note
        conf = [r for r in records if self.confirmed(r)][:3]
        possessed = "; ".join(possessed_phrase(r) for r in conf) if status != EvidenceStatus.NOT_FOUND else ""
        return RequirementResult(req, status, evidence, expl, possessed, [r.id for r in conf] if possessed else [])

    # ------------------------------------------------------------------ research
    def match_research(self, req: Requirement) -> RequirementResult:
        if re.search(r"publication|paper|journal|peer", req.text, re.I):
            pubs = [r for r in self.records if r.kind == RecordKind.PUBLICATION]
            published = [p for p in pubs if p.data.status in (PublicationStatus.PUBLISHED.value,
                                                             PublicationStatus.ACCEPTED.value)]
            pending = [p for p in pubs if p.data.status in (PublicationStatus.SUBMITTED.value,
                                                           PublicationStatus.UNDER_REVIEW.value)]
            evidence = [self._item(p, label(PublicationStatus(p.data.status)).lower()) for p in (published + pending)[:6]]
            if published:
                conf = [p for p in published if self.confirmed(p)]
                status = EvidenceStatus.VERIFIED if conf else EvidenceStatus.AWAITING_CONFIRMATION
                expl = f"{len(published)} published or accepted publication(s) in your profile."
                if pending:
                    expl += f" {len(pending)} more under review/submitted (not counted as published)."
                possessed = f"{len(conf)} peer-reviewed publication(s): " + "; ".join(p.title for p in conf[:3]) if conf else ""
                return RequirementResult(req, status, evidence, expl, possessed, [p.id for p in conf[:3]])
            if pending:
                return RequirementResult(req, EvidenceStatus.PARTIAL, evidence,
                                         "Only manuscripts under review or submitted — these are not publications yet.")
            return RequirementResult(req, EvidenceStatus.NOT_FOUND, [], "No publications in your profile.")
        if re.search(r"ph\.?\s?d|doctor", req.text, re.I):
            return self.match_qualification(req)
        return self.match_concepts(req)

    # ------------------------------------------------------------------ dispatcher
    def match(self, req: Requirement) -> RequirementResult:
        if req.status_override:
            st = EvidenceStatus(req.status_override)
            res = RequirementResult(req, st, explanation="Status set by you.")
        else:
            cat = RequirementCategory(req.category)
            if cat == RequirementCategory.ELIGIBILITY:
                res = RequirementResult(req, EvidenceStatus.OFFICIAL_VERIFICATION, explanation=(
                    "Formal eligibility (age, pay level, analogous post, service conditions) is decided by the "
                    "recruiting authority from official records. The software does not assess it."))
            elif cat == RequirementCategory.DOCUMENTATION:
                res = RequirementResult(req, EvidenceStatus.OFFICIAL_VERIFICATION, explanation=(
                    "A document you must obtain or prepare; the software cannot verify it."))
            elif cat in (RequirementCategory.MANDATORY_QUALIFICATION, RequirementCategory.DESIRABLE_QUALIFICATION):
                res = self.match_qualification(req)
            elif cat == RequirementCategory.EXPERIENCE:
                res = self.match_experience(req)
            elif cat == RequirementCategory.RESEARCH:
                res = self.match_research(req)
            elif cat == RequirementCategory.LEADERSHIP:
                res = self.match_concepts(req)
                lead = self.match_concepts(req, require_leading=True)
                if lead.status != EvidenceStatus.NOT_FOUND:
                    res = lead
                elif not any(getattr(self.snap.get(e.record_id).data, "involvement", None) in ("leading", "coordinating")
                             for e in res.evidence if self.snap.get(e.record_id) is not None):
                    if res.status in (EvidenceStatus.VERIFIED, EvidenceStatus.AWAITING_CONFIRMATION):
                        res.status = EvidenceStatus.PARTIAL
                        res.explanation += " Records do not state a leading or coordinating role."
            else:
                res = self.match_concepts(req)
        if req.possessed_note:
            res.possessed = req.possessed_note
            res.possessed_sources = []
        res.credit = CREDIT.get(res.status, 0.0)
        return res

    def match_all(self, reqs: list[Requirement]) -> list[RequirementResult]:
        return [self.match(r) for r in reqs]
