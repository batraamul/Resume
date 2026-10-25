"""Plain-text (ATS) rendering of the IR: no formatting, conventional headings, UTF-8."""

from __future__ import annotations

import textwrap

from ris.composition.ir import IREntry, ResumeDocument

WIDTH = 92


def _wrap(text: str, indent: str = "", subsequent: str | None = None) -> list[str]:
    return textwrap.wrap(text, width=WIDTH, initial_indent=indent,
                         subsequent_indent=subsequent if subsequent is not None else indent,
                         break_on_hyphens=False, break_long_words=False) or [indent.rstrip()]


def _entry(e: IREntry, lines: list[str], child: bool = False) -> None:
    head = e.title
    if child and e.status_label:
        head = f"{e.status_label}: {head}"
    if e.subtitle:
        head += f" | {e.subtitle}"
    if e.location:
        head += f" | {e.location}"
    if e.date_text:
        head += f" | {e.date_text}"
    if e.status_label and not child and e.status_label.lower() not in (e.date_text or "").lower():
        head += f" ({e.status_label})"
    prefix = "  " if child else ""
    lines.extend(_wrap(head, prefix))
    if e.description:
        lines.extend(_wrap(e.description, prefix))
    for label, value in e.meta:
        lines.extend(_wrap(f"{label}: {value}", prefix))
    for b in e.bullets:
        lines.extend(_wrap(b.text, prefix + "- ", prefix + "  "))
    for c in e.children:
        _entry(c, lines, child=True)


def render_text(doc: ResumeDocument) -> str:
    lines: list[str] = []
    if doc.title_line:
        lines.append(doc.title_line)
        lines.append("")
    lines.append(doc.name)
    if doc.headline:
        lines.append(doc.headline)
    if doc.contacts:
        lines.append(" | ".join(c.value for c in doc.contacts))
    for s in doc.sections:
        lines.append("")
        lines.append(s.title.upper())
        lines.append("-" * min(len(s.title), WIDTH))
        for p in s.paragraphs:
            lines.extend(_wrap(p))
        if s.layout == "publications":
            for i, e in enumerate(s.entries, start=1):
                text = f"[{i}] {e.authors + ', ' if e.authors else ''}{e.citation_rest}"
                if e.status_label and e.status_label != "Accepted":
                    text += f" [{e.status_label}]"
                lines.extend(_wrap(text, "", "    "))
        else:
            for e in s.entries:
                _entry(e, lines)
        if s.tiles:
            lines.extend(_wrap(" | ".join(f"{t.value} {t.label}" + (f" ({t.caption})" if t.caption else "")
                                          for t in s.tiles)))
        for g in s.skill_groups:
            lines.extend(_wrap(f"{g.label}: {', '.join(g.items)}"))
        if s.items and s.layout != "declaration":
            for item in s.items:
                lines.extend(_wrap(item, "- ", "  "))
        if s.table:
            for row in s.table.rows:
                if s.table.header:
                    pairs = [f"{h}: {v}" for h, v in zip(s.table.header, row, strict=False) if v and not h.lower().startswith("s. no")]
                    lines.extend(_wrap("; ".join(p.replace("\n", "; ") for p in pairs), "- ", "  "))
                else:
                    head = row[0].replace("\n", ", ")
                    lines.extend(_wrap(f"{head}: {' '.join(row[1:])}"))
        if s.layout == "declaration":
            lines.extend(s.items)
    if doc.footer_note:
        lines.append("")
        lines.append(doc.footer_note)
    return "\n".join(lines).rstrip() + "\n"
