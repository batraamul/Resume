"""Redacted professional portfolio (TRK-04): only approved, externally cleared project information."""

from __future__ import annotations

from ris.composition.ir import ContactItem, IREntry, IRSection, IRSkillGroup, ResumeDocument
from ris.domain import dates
from ris.domain.enums import Confidentiality, PublicationStatus, RecordKind, SkillCategory, Verification, label
from ris.services.profile import ProfileSnapshot
from ris.util import utc_now_iso

ALLOWED = (Confidentiality.PUBLIC, Confidentiality.APPROVED)


def build_portfolio(snap: ProfileSnapshot, *, template_id: str = "", template_version: str = "",
                    public_only: bool = False, is_sample: bool = False) -> ResumeDocument:
    allowed = (Confidentiality.PUBLIC,) if public_only else ALLOWED
    used: dict[str, int] = {}

    def ok(r) -> bool:
        return (snap.effective_confidentiality(r) in allowed
                and snap.effective_verification(r) != Verification.UNCONFIRMED)

    p = snap.personal_data
    sections: list[IRSection] = []
    summaries = [s for s in snap.of(RecordKind.SUMMARY) if ok(s) and s.data.text]
    if summaries:
        used[summaries[0].id] = summaries[0].revision
        sections.append(IRSection(key="summary", title="Profile", layout="paragraph", paragraphs=[summaries[0].data.text],
                                  source_ids=[summaries[0].id]))
    entries = []
    for pr in snap.of(RecordKind.PROJECT):
        if not ok(pr) or not pr.data.approved_external_description:
            continue
        d = pr.data
        used[pr.id] = pr.revision
        tech = list(dict.fromkeys([*d.hardware, *d.software, *d.algorithms]))
        e = IREntry(id=pr.id, kind="project", title=d.title, subtitle=d.role,
                    date_text=dates.format_range(d.start, d.end, d.is_current), description=d.approved_external_description,
                    source_ids=[pr.id], link=d.url)
        if tech:
            e.meta.append(("Technologies", ", ".join(tech[:10])))
        entries.append(e)
    entries.sort(key=lambda e: e.date_text, reverse=True)
    if entries:
        sections.append(IRSection(key="projects", title="Selected Projects", layout="entries", entries=entries))
    pubs = [x for x in snap.of(RecordKind.PUBLICATION) if ok(x) and x.data.status == PublicationStatus.PUBLISHED.value]
    if pubs:
        pe = []
        for x in pubs:
            used[x.id] = x.revision
            year = dates.format_date(x.data.date, "year")
            pe.append(IREntry(id=x.id, kind="publication", title=x.data.title, authors=x.data.authors,
                              citation_rest=f"“{x.data.title},” {x.data.venue}{', ' + year if year else ''}.",
                              link=f"https://doi.org/{x.data.doi}" if x.data.doi else x.data.url, source_ids=[x.id]))
        sections.append(IRSection(key="publications", title="Publications", layout="publications", entries=pe))
    groups: dict[str, list] = {}
    for s in snap.of(RecordKind.SKILL):
        if ok(s) and s.data.category not in ("languages",):
            groups.setdefault(s.data.category, []).append(s)
            used[s.id] = s.revision
    if groups:
        sections.append(IRSection(key="skills", title="Skills", layout="skills", skill_groups=[
            IRSkillGroup(category=c, label=label(SkillCategory(c)), items=[m.data.name for m in ms][:10],
                         source_ids=[m.id for m in ms][:10]) for c, ms in sorted(groups.items())]))
    contacts = [ContactItem(key="email", label="Email", value=p.email, url=f"mailto:{p.email}")] if p.email else []
    return ResumeDocument(
        doc_type="portfolio", name=p.display_name(), headline=p.professional_title, title_line="",
        contacts=contacts, sections=sections, template_id=template_id, template_version=template_version,
        mode="portfolio", length="full", generated_at=utc_now_iso(), is_sample=is_sample,
        footer_note="Fictional sample profile — not a real person" if is_sample else "",
        source_revisions=used, metadata={"title": f"{p.display_name()} — Professional Portfolio",
                                          "author": p.display_name()},
    )
