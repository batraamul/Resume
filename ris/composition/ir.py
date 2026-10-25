"""Shared intermediate representation (IR) for resumes, CVs, letters and portfolios.

Both the DOCX and PDF renderers consume the same IR (via the layout planner),
so content is identical across formats. Every substantive piece of text
carries the identifiers of the profile records it came from.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

IR_SCHEMA_VERSION = 1


class _IRBase(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ContactItem(_IRBase):
    key: str
    label: str
    value: str
    url: str = ""


class IRBullet(_IRBase):
    text: str
    source_ids: list[str] = Field(default_factory=list)
    source_field: str = ""
    claim_id: str = ""
    verification: str = "confirmed"
    confidentiality: str = "approved"
    relevance: float = 0.0


class IREntry(_IRBase):
    id: str = ""
    kind: str = ""
    title: str = ""
    subtitle: str = ""
    location: str = ""
    date_text: str = ""
    sort_key: list[int] = Field(default_factory=list)
    status_label: str = ""
    description: str = ""
    bullets: list[IRBullet] = Field(default_factory=list)
    children: list[IREntry] = Field(default_factory=list)
    meta: list[tuple[str, str]] = Field(default_factory=list)
    link: str = ""
    authors: str = ""
    citation_rest: str = ""
    highlight_names: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    verification: str = "confirmed"
    confidentiality: str = "approved"
    relevance: float = 0.0
    is_current: bool = False
    #: Labelled details (e.g. Challenge / Approach / Outcome) used by card layouts.
    facets: list[tuple[str, str]] = Field(default_factory=list)
    #: Short emphasised figures (verified metrics) shown as highlights in graphical layouts.
    highlights: list[str] = Field(default_factory=list)


class IRSkillGroup(_IRBase):
    category: str
    label: str
    items: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    #: Self-assessed depth per item, 0 (not rated) to 5 (expert); drawn as bars by graphical templates.
    levels: list[int] = Field(default_factory=list)


class IRChartPoint(_IRBase):
    label: str
    start: str = ""          # partial ISO date (timeline)
    end: str = ""
    is_current: bool = False
    value: float = 0.0       # e.g. years in post, or a count
    group: str = ""          # stack / series name
    caption: str = ""
    source_ids: list[str] = Field(default_factory=list)


class IRChart(_IRBase):
    kind: str                # timeline | stacked_years | years_bars
    points: list[IRChartPoint] = Field(default_factory=list)
    alt_text: str = ""
    caption: str = ""
    series: list[str] = Field(default_factory=list)


class IRTile(_IRBase):
    value: str
    label: str
    caption: str = ""
    source_ids: list[str] = Field(default_factory=list)


class IRTable(_IRBase):
    header: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    col_widths: list[float] = Field(default_factory=list)  # fractions of the text width
    source_ids: list[str] = Field(default_factory=list)


class IRSection(_IRBase):
    key: str
    title: str
    layout: str  # paragraph | entries | skills | list | table | publications | declaration | particulars | certificate
    paragraphs: list[str] = Field(default_factory=list)
    entries: list[IREntry] = Field(default_factory=list)
    skill_groups: list[IRSkillGroup] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
    table: IRTable | None = None
    source_ids: list[str] = Field(default_factory=list)
    note: str = ""
    sidebar_ok: bool = False
    chart: IRChart | None = None
    tiles: list[IRTile] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.paragraphs or self.entries or self.skill_groups or self.items
                    or (self.table and self.table.rows) or self.tiles or (self.chart and self.chart.points))


class LetterBlock(_IRBase):
    sender_lines: list[str] = Field(default_factory=list)
    date_line: str = ""
    recipient_lines: list[str] = Field(default_factory=list)
    reference_line: str = ""
    subject: str = ""
    salutation: str = ""
    paragraphs: list[str] = Field(default_factory=list)
    closing: str = ""
    signature_lines: list[str] = Field(default_factory=list)
    enclosures: list[str] = Field(default_factory=list)
    place_line: str = ""


class ResumeDocument(_IRBase):
    schema_version: int = IR_SCHEMA_VERSION
    doc_type: str = "resume"  # resume | cover_letter | portfolio
    name: str = ""
    headline: str = ""
    title_line: str = ""  # e.g. "CURRICULUM VITAE" for government bio-data
    contacts: list[ContactItem] = Field(default_factory=list)
    photo_path: str = ""
    sections: list[IRSection] = Field(default_factory=list)
    letter: LetterBlock | None = None
    template_id: str = ""
    template_version: str = ""
    mode: str = ""
    length: str = "two_pages"
    max_pages: int | None = None
    page_size: str = "A4"
    font_scale: float = 1.0
    spacing: str = "normal"
    accent_color: str = ""
    generated_at: str = ""
    is_sample: bool = False
    footer_note: str = ""
    warnings: list[str] = Field(default_factory=list)
    trimmed: list[str] = Field(default_factory=list)
    source_revisions: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, str] = Field(default_factory=dict)
    #: Chart choices made for this resume (chart key → style); templates supply the defaults.
    chart_styles: dict[str, str] = Field(default_factory=dict)

    # ------------------------------------------------------------------ helpers for validation
    def section(self, key: str) -> IRSection | None:
        return next((s for s in self.sections if s.key == key), None)

    def iter_entries(self):
        for s in self.sections:
            for e in s.entries:
                yield s, e
                for c in e.children:
                    yield s, c

    def all_source_ids(self) -> set[str]:
        ids: set[str] = set()
        for s in self.sections:
            ids.update(s.source_ids)
            for g in s.skill_groups:
                ids.update(g.source_ids)
            if s.table:
                ids.update(s.table.source_ids)
            if s.chart:
                for pt in s.chart.points:
                    ids.update(pt.source_ids)
            for t in s.tiles:
                ids.update(t.source_ids)
            for e in s.entries:
                stack = [e]
                while stack:
                    cur = stack.pop()
                    ids.update(cur.source_ids)
                    for b in cur.bullets:
                        ids.update(b.source_ids)
                    stack.extend(cur.children)
        return {i for i in ids if i}

    def text_fragments(self) -> list[str]:
        """Every substantive text fragment, in document order (used for consistency checks)."""
        out: list[str] = []
        if self.title_line:
            out.append(self.title_line)
        out.extend(x for x in (self.name, self.headline) if x)
        out.extend(c.value for c in self.contacts)
        for s in self.sections:
            out.append(s.title)
            out.extend(s.paragraphs)
            out.extend(s.items)
            for g in s.skill_groups:
                out.append(g.label)
                out.extend(g.items)
            for t in s.tiles:
                out.extend(x for x in (t.value, t.label, t.caption) if x)
            if s.chart:
                out.extend(x for x in (s.chart.caption, s.chart.alt_text) if x)
                for pt in s.chart.points:
                    out.extend(x for x in (pt.label, pt.caption) if x)
            if s.table:
                out.extend(h for h in s.table.header if h)
                for row in s.table.rows:
                    out.extend(c for c in row if c)
            for e in s.entries:
                stack = [e]
                while stack:
                    cur = stack.pop(0)
                    out.extend(x for x in (cur.title, cur.subtitle, cur.location, cur.date_text,
                                           cur.status_label, cur.description, cur.authors, cur.citation_rest) if x)
                    out.extend(v for _, v in cur.meta if v)
                    out.extend(v for _, v in cur.facets if v)
                    out.extend(cur.highlights)
                    out.extend(b.text for b in cur.bullets)
                    stack.extend(cur.children)
        if self.letter:
            lt = self.letter
            out.extend([*lt.sender_lines, lt.date_line, *lt.recipient_lines, lt.reference_line, lt.subject,
                        lt.salutation, *lt.paragraphs, lt.closing, *lt.signature_lines, *lt.enclosures, lt.place_line])
        return [x for x in out if x and x.strip()]

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
