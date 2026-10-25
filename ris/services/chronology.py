"""Chronology and plausibility checks across the profile.

These are *warnings* that help the user keep records truthful; storage-level
validation already rejects impossible values (e.g. an end before a start).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ris.domain import dates
from ris.domain.enums import EducationStatus, PublicationStatus, RecordKind
from ris.services.profile import ProfileSnapshot


@dataclass(frozen=True)
class Issue:
    record_id: str
    severity: str  # error | warning | info
    message: str
    kind: str = ""


def _overlap(a_start, a_end, b_start, b_end) -> bool:
    return a_start <= b_end and b_start <= a_end


def check_chronology(snap: ProfileSnapshot, today: date | None = None) -> list[Issue]:
    today = today or date.today()
    issues: list[Issue] = []
    positions = snap.of(RecordKind.POSITION)

    current = [p for p in positions if p.data.is_current]
    if len(current) > 1:
        names = ", ".join(p.title for p in current)
        for p in current:
            issues.append(Issue(p.id, "warning", (
                f"More than one current position ({names}). If one is an additional charge, record it as a "
                "concurrent responsibility under the main position."), "position"))

    spans = []
    for p in positions:
        d = p.data
        if not d.start:
            issues.append(Issue(p.id, "warning", f"'{p.title}' has no start date.", "position"))
        if not d.is_current and not d.end and d.start:
            issues.append(Issue(p.id, "warning", f"'{p.title}' has no end date and is not marked current.", "position"))
        if dates.is_future(d.start, today):
            issues.append(Issue(p.id, "error", f"'{p.title}' starts in the future.", "position"))
        s = dates.parse_or_none(d.start)
        e = dates.parse_or_none(d.end)
        if s:
            spans.append((p, s.earliest(), today if d.is_current else (e.latest() if e else None)))
        for a in snap.kids(p.id, RecordKind.ASSIGNMENT):
            ad = a.data
            a_s = dates.parse_or_none(ad.start)
            if s and a_s and a_s.sort_key() < s.sort_key():
                issues.append(Issue(a.id, "warning",
                                    f"'{a.title}' starts before its parent position '{p.title}'.", "assignment"))
            a_e = dates.parse_or_none(ad.end)
            if e and not d.is_current and a_e and a_e.sort_key() > e.sort_key():
                issues.append(Issue(a.id, "warning",
                                    f"'{a.title}' ends after its parent position '{p.title}'.", "assignment"))
            if ad.is_current and not d.is_current:
                issues.append(Issue(a.id, "warning",
                                    f"'{a.title}' is marked current but '{p.title}' has ended.", "assignment"))

    closed = [(p, s, e) for p, s, e in spans if e is not None]
    for i in range(len(closed)):
        for j in range(i + 1, len(closed)):
            p1, s1, e1 = closed[i]
            p2, s2, e2 = closed[j]
            # Ignore overlaps of up to ~31 days (handover periods, month-only dates).
            if _overlap(s1, e1, s2, e2) and (min(e1, e2) - max(s1, s2)).days > 31:
                msg = (f"'{p1.title}' and '{p2.title}' overlap. If one was concurrent, record it as an "
                       "additional charge under the other.")
                issues.append(Issue(p1.id, "warning", msg, "position"))
                issues.append(Issue(p2.id, "warning", msg, "position"))

    for ed in snap.of(RecordKind.EDUCATION):
        d = ed.data
        status = EducationStatus(d.status)
        if status == EducationStatus.COMPLETED and dates.is_future(d.end, today):
            issues.append(Issue(ed.id, "error",
                                f"'{ed.title}' is marked completed but its completion date is in the future.",
                                "education"))
        if status == EducationStatus.ONGOING and d.end and not dates.is_future(d.end, today):
            issues.append(Issue(ed.id, "warning",
                                f"'{ed.title}' is marked ongoing but its completion date has passed. Update the status.",
                                "education"))
        if status == EducationStatus.COMPLETED and not d.end:
            issues.append(Issue(ed.id, "info", f"'{ed.title}' has no completion year.", "education"))

    for pub in snap.of(RecordKind.PUBLICATION):
        d = pub.data
        status = PublicationStatus(d.status)
        if status == PublicationStatus.PUBLISHED and dates.is_future(d.date, today):
            issues.append(Issue(pub.id, "error", f"'{pub.title}' is marked published with a future date.",
                                "publication"))
        if status in (PublicationStatus.PUBLISHED, PublicationStatus.ACCEPTED) and not d.venue:
            issues.append(Issue(pub.id, "warning", f"'{pub.title}' is {status.value} but has no venue.", "publication"))

    # Career length for plausibility of skill durations.
    starts = [dates.parse_or_none(p.data.start) for p in positions]
    starts = [s for s in starts if s]
    career_years = None
    if starts:
        first = min(s.earliest() for s in starts)
        career_years = (today - first).days / 365.25
    for sk in snap.of(RecordKind.SKILL):
        d = sk.data
        if d.last_used and int(d.last_used) > today.year:
            issues.append(Issue(sk.id, "error", f"Skill '{sk.title}' has a last-used year in the future.", "skill"))
        if career_years is not None and d.years_experience and d.years_experience > career_years + 6:
            issues.append(Issue(sk.id, "warning", (
                f"Skill '{sk.title}' claims {d.years_experience:g} years, more than your recorded career length "
                f"(~{career_years:.0f} years) plus study. Check the figure."), "skill"))

    for b in snap.of(RecordKind.BULLET):
        if b.data.metrics and not b.data.evidence:
            issues.append(Issue(b.id, "info", "This statement has metrics but no supporting-evidence note.", "bullet"))
    return issues
