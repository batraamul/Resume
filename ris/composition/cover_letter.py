"""Cover-letter drafting and letter IR (TRK-03).

Drafts use only your recorded facts and the vacancy text: the post, your
current role, evidence mapped to the requirements and your own statements.
They never invent endorsements, personal connections or insider knowledge.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ris.composition.ir import ContactItem, LetterBlock, ResumeDocument
from ris.domain.enums import EvidenceStatus, RecordKind, RequirementCategory, Verification
from ris.domain.models import CoverLetter, Vacancy
from ris.intelligence.analysis import VacancyAnalysis
from ris.services.profile import ProfileSnapshot
from ris.util import utc_now_iso


def _current_position(snap: ProfileSnapshot):
    positions = [p for p in snap.of(RecordKind.POSITION) if p.data.is_current and p.verification != Verification.UNCONFIRMED]
    return positions[0] if positions else None


def draft_cover_letter(snap: ProfileSnapshot, vacancy: Vacancy | None, analysis: VacancyAnalysis | None,
                       *, style: str = "formal", today: date | None = None) -> dict[str, Any]:
    """Return a CoverLetter payload (dict) with source ids. Only confirmed, non-confidential facts are used."""
    p = snap.personal_data
    today = today or date.today()
    title = vacancy.title if vacancy and vacancy.title else "the advertised post"
    employer = vacancy.employer if vacancy and vacancy.employer else ""
    ref = vacancy.reference if vacancy and vacancy.reference else ""
    sources: list[str] = []
    paragraphs: list[str] = []
    if style == "formal":
        opening = f"I wish to apply for the post of {title}"
        if employer:
            opening += f" in {employer}"
        opening += f", advertised vide {ref}." if ref else "."
    else:
        opening = f"I am writing to apply for the {title} position" + (f" at {employer}." if employer else ".")
    paragraphs.append(opening)
    cur = _current_position(snap)
    if cur is not None and cur.confidentiality.value != "confidential":
        d = cur.data
        where = ", ".join(x for x in (d.division, d.organisation) if x)
        sent = f"I am presently working as {d.designation}" + (f" in {where}" if where else "")
        if d.summary and cur.confidentiality.value in ("public", "approved"):
            s = d.summary.strip().rstrip(".")
            sent += f". In this role I am {s[0].lower() + s[1:]}" if s.lower().startswith("responsible") else f". {s}"
        paragraphs.append(sent.rstrip(".") + ".")
        sources.append(cur.id)
    if analysis is not None:
        lines = []
        for r in analysis.results:
            cat = RequirementCategory(r.requirement.category)
            if cat in (RequirementCategory.ELIGIBILITY, RequirementCategory.DOCUMENTATION):
                continue
            if r.status != EvidenceStatus.VERIFIED or not r.possessed:
                continue
            req = r.requirement.text.rstrip(".")
            lines.append(f"{req[0].lower() + req[1:] if req else req}: {r.possessed}")
            sources.extend(r.possessed_sources)
            if len(lines) >= 4:
                break
        if lines:
            intro = ("Against the requirements of the post, my qualifications and experience are as follows: "
                     if style == "formal" else "Relevant to your requirements: ")
            paragraphs.append(intro + "; ".join(lines) + ".")
    # Up to two of your own confirmed, approved achievement statements, ranked by relevance.
    if analysis is not None:
        bullets = [b for b in snap.of(RecordKind.BULLET)
                   if snap.effective_verification(b) != Verification.UNCONFIRMED
                   and snap.effective_confidentiality(b).value in ("public", "approved")
                   and b.data.bullet_type in ("achievement", "outcome", "deliverable")]
        bullets.sort(key=lambda b: (-analysis.relevance.score_text(b.data.text), b.id))
        chosen = [b for b in bullets[:2] if analysis.relevance.score_text(b.data.text) > 0]
        if chosen:
            paragraphs.append("Recent work includes: " + " ".join(
                (b.data.text.rstrip(".") + ".") for b in chosen))
            sources.extend(b.id for b in chosen)
    if style == "formal":
        paragraphs.append("I request that my application be considered. My bio-data is enclosed for your kind perusal.")
        closing = "Yours faithfully,"
        salutation = "Sir/Madam,"
    else:
        paragraphs.append("Thank you for considering my application. I would welcome the opportunity to discuss how "
                          "my experience could contribute to your work.")
        closing = "Yours sincerely,"
        salutation = "Dear Hiring Committee,"
    sig_designation = ""
    if cur is not None:
        sig_designation = ", ".join(x for x in (cur.data.designation, cur.data.organisation) if x)
    subject = f"Application for the post of {title}" + (f" (Advt. No. {ref})" if ref else "")
    return {
        "title": f"Cover letter — {title}"[:120], "style": style,
        "date_text": today.strftime("%d %B %Y"), "place": p.city,
        "recipient_designation": "", "recipient_organisation": employer, "recipient_address": [],
        "subject": subject, "reference_line": "", "salutation": salutation, "paragraphs": paragraphs,
        "closing": closing, "signature_name": p.display_name() or p.full_name, "signature_designation": sig_designation,
        "enclosures": ["Bio-data"] if style == "formal" else [], "source_record_ids": list(dict.fromkeys(sources)),
        "status": "draft",
    }


def letter_document(letter: CoverLetter, snap: ProfileSnapshot, *, template_id: str = "", template_version: str = "",
                    is_sample: bool = False) -> ResumeDocument:
    p = snap.personal_data
    contacts = []
    if p.email:
        contacts.append(ContactItem(key="email", label="Email", value=p.email, url=f"mailto:{p.email}"))
    if p.phone:
        contacts.append(ContactItem(key="phone", label="Phone", value=p.phone))
    sender = [x for x in (letter.signature_name or p.display_name(), letter.signature_designation) if x]
    recipient = [x for x in (letter.recipient_name, letter.recipient_designation, letter.recipient_organisation) if x]
    recipient += list(letter.recipient_address)
    block = LetterBlock(
        sender_lines=sender + [c.value for c in contacts], date_line=letter.date_text, recipient_lines=recipient,
        reference_line=letter.reference_line, subject=letter.subject, salutation=letter.salutation,
        paragraphs=list(letter.paragraphs), closing=letter.closing,
        signature_lines=[x for x in (letter.signature_name, letter.signature_designation) if x],
        enclosures=list(letter.enclosures), place_line=f"Place: {letter.place}" if letter.place else "",
    )
    return ResumeDocument(
        doc_type="cover_letter", name=letter.signature_name or p.display_name(), contacts=contacts, letter=block,
        template_id=template_id, template_version=template_version, length="full", generated_at=utc_now_iso(),
        is_sample=is_sample, footer_note="Fictional sample profile — not a real person" if is_sample else "",
        source_revisions={sid: r.revision for sid in letter.source_record_ids if (r := snap.get(sid)) is not None},
        metadata={"title": letter.subject or "Cover letter", "subject": letter.subject, "author": p.display_name()},
    )
