"""Layout planner: ResumeDocument (content IR) + TemplateSpec → LayoutDocument (blocks).

The planner implements each template layout system once; both renderers then
draw the same blocks. Variant overrides (font scale, spacing, accent colour,
page size) are applied here.
"""

from __future__ import annotations

import re

from ris.composition.ir import ContactItem, IREntry, IRSection, ResumeDocument
from ris.rendering import graphics
from ris.rendering.blocks import (
    MM,
    PAGE_SIZES_PT,
    BannerBlock,
    Border,
    Cell,
    ColumnsBlock,
    FooterLayout,
    ImageBlock,
    LabeledSection,
    LayoutDocument,
    PageSetup,
    Para,
    ParaStyle,
    Rule,
    Run,
    Spacer,
    TableBlock,
)
from ris.rendering.specs import TemplateSpec

SPACING_FACTORS = {"compact": 0.7, "normal": 1.0, "relaxed": 1.3}
CONTACT_ICONS = {"email": "✉", "phone": "☎", "location": "⌂"}
LINK_ICON = "➤"
ICON_FONT = "DejaVu Sans"  # Word substitutes a symbol font when absent; avoids colour-emoji fallback in LibreOffice
FACET_SOURCE_FIELDS = {"individual_contribution", "approach", "results", "metrics", "problem"}
SELF_RATING_NOTE = "Bars show my own assessment of proficiency (five steps; five = expert)."


class LayoutPlanner:
    def __init__(self, doc: ResumeDocument, spec: TemplateSpec) -> None:
        self.doc = doc
        self.spec = spec
        self.scale = float(doc.font_scale or 1.0)
        self.sp = SPACING_FACTORS.get(doc.spacing or "normal", 1.0)
        c = spec.colours
        self.accent = doc.accent_color or c.accent
        self.text = c.text
        self.muted = c.muted
        self.rule_color = doc.accent_color if (doc.accent_color and c.rule == c.accent) else c.rule
        self.fill = c.fill
        w, h = PAGE_SIZES_PT.get(doc.page_size or "A4", PAGE_SIZES_PT["A4"])
        p = spec.page
        self.page = PageSetup(w, h, p.margin_top_mm * MM, p.margin_bottom_mm * MM, p.margin_left_mm * MM,
                              p.margin_right_mm * MM)
        self.bullet_indent = spec.entry.bullet_indent_mm * MM
        self.section_index = 0
        self.in_sidebar = False
        self.in_columns = False  # inside a two-column body: avoid nested tables (LibreOffice cannot split them)
        self.cur_width = self.page.text_width
        self.palette = tuple(spec.graphics.palette)
        if doc.accent_color:
            self.palette = (doc.accent_color, *self.palette[1:])

    # ------------------------------------------------------------------ styles
    def _s(self, pt: float) -> float:
        return round(pt * self.scale, 2)

    def _gap(self, pt: float) -> float:
        return round(pt * self.sp, 2)

    def styles(self) -> dict[str, ParaStyle]:
        f = self.spec.fonts
        hd = self.spec.heading
        hdr = self.spec.header
        ls = f.line_spacing + (0.04 if self.doc.spacing == "relaxed" else (-0.03 if self.doc.spacing == "compact" else 0))
        body = self._s(f.body_size)
        small = self._s(f.small_size)
        name_color = self.accent if hdr.name_colour == "accent" else self.text
        head_color = {"accent": self.accent, "text": self.text, "muted": self.muted}[hdr.headline_colour]
        h_align = "center" if hdr.style == "centered" else "left"
        heading_color = self.accent if hd.colour == "accent" else self.text
        st: dict[str, ParaStyle] = {}

        def add(s: ParaStyle) -> None:
            st[s.name] = s

        add(ParaStyle("Normal", f.body, body, color=self.text, line_spacing=ls, space_after=0, docx_base="Normal"))
        add(ParaStyle("Name", f.name, self._s(f.name_size), bold=True, color=name_color, align=h_align,
                      space_after=self._gap(2), line_spacing=1.0, small_caps=hdr.name_case == "small_caps",
                      docx_base="Title", outline_level=None,
                      letter_spacing=0.5 if hdr.name_case in ("upper", "small_caps") else 0.0))
        add(ParaStyle("TitleLine", f.heading, self._s(f.heading_size + 1.5), bold=True, color=self.text,
                      align="center", space_after=self._gap(6), line_spacing=1.0))
        add(ParaStyle("Headline", f.body, self._s(f.headline_size), color=head_color, align=h_align,
                      space_after=self._gap(3), line_spacing=1.05))
        add(ParaStyle("Contact", f.body, small + 0.3, color=self.text, align=h_align, space_after=self._gap(1),
                      line_spacing=1.1))
        add(ParaStyle("SectionHeading", f.heading, self._s(hd.heading_size if hasattr(hd, "heading_size") else f.heading_size),
                      bold=hd.style not in ("small_caps",), color=heading_color,
                      space_before=self._gap(hd.space_before), space_after=self._gap(hd.space_after),
                      keep_with_next=True, letter_spacing=hd.letter_spacing, small_caps=hd.case == "small_caps",
                      docx_base="Heading 1", outline_level=0, line_spacing=1.0))
        st["SectionHeading"].size = self._s(f.heading_size)
        add(ParaStyle("MarginLabel", f.heading, self._s(f.heading_size), bold=True, color=heading_color,
                      letter_spacing=hd.letter_spacing, line_spacing=1.05, space_before=0, space_after=0,
                      docx_base="Heading 1", outline_level=0))
        add(ParaStyle("EntryTitle", f.body, body + 0.3, bold=False, color=self.text, keep_with_next=True,
                      space_before=0, space_after=0, line_spacing=ls, docx_base="Heading 2", outline_level=1))
        add(ParaStyle("EntrySub", f.body, body, color=self.muted, keep_with_next=True, line_spacing=ls,
                      space_after=self._gap(1)))
        add(ParaStyle("EntryMeta", f.body, small, color=self.muted, line_spacing=ls, space_after=self._gap(1)))
        add(ParaStyle("ChildTitle", f.body, body, color=self.text, keep_with_next=True, line_spacing=ls,
                      left_indent=self.bullet_indent, space_before=self._gap(2)))
        add(ParaStyle("Body", f.body, body, color=self.text, line_spacing=ls, space_after=self._gap(2)))
        add(ParaStyle("Summary", f.body, body, color=self.text, line_spacing=ls + 0.03, space_after=self._gap(2),
                      align="justify" if self.spec.summary_style != "boxed" else "left",
                      italic=self.spec.summary_style == "italic"))
        add(ParaStyle("Bullet", f.body, body, color=self.text, line_spacing=ls, left_indent=self.bullet_indent,
                      first_line_indent=-self.bullet_indent, space_after=self._gap(1)))
        add(ParaStyle("Meta", f.body, small, color=self.muted, line_spacing=ls, space_after=self._gap(1)))
        add(ParaStyle("Citation", f.body, body, color=self.text, line_spacing=ls, space_after=self._gap(3)))
        add(ParaStyle("TableHead", f.body, small + 0.4, bold=True, color=self.text, line_spacing=1.05))
        add(ParaStyle("TableText", f.body, small + 0.6, color=self.text, line_spacing=1.08))
        add(ParaStyle("SidebarHeading", f.heading, self._s(f.heading_size - 0.5), bold=True, color=self.accent,
                      space_before=self._gap(9), space_after=self._gap(3), keep_with_next=True,
                      letter_spacing=max(hd.letter_spacing, 0.6), docx_base="Heading 1", outline_level=0,
                      line_spacing=1.0))
        add(ParaStyle("SidebarText", f.body, small + 0.4, color=self.text, line_spacing=1.12,
                      space_after=self._gap(1.5)))
        add(ParaStyle("SidebarTitle", f.body, small + 0.6, bold=True, color=self.text, line_spacing=1.08,
                      keep_with_next=True))
        add(ParaStyle("BannerName", f.name, self._s(f.name_size), bold=True, color=self.spec.colours.banner_text,
                      line_spacing=1.0, space_after=self._gap(2), docx_base="Title",
                      small_caps=hdr.name_case == "small_caps", letter_spacing=0.6))
        add(ParaStyle("BannerText", f.body, self._s(f.headline_size), color=self.spec.colours.banner_text,
                      line_spacing=1.1, space_after=self._gap(1)))
        add(ParaStyle("BannerContact", f.body, small + 0.3, color=self.spec.colours.banner_text, line_spacing=1.1))
        add(ParaStyle("Declaration", f.body, body, color=self.text, line_spacing=ls + 0.05, space_after=self._gap(4)))
        add(ParaStyle("DefLabel", f.body, body, bold=True, color=self.accent if hd.colour == "accent" else self.text,
                      line_spacing=ls, space_after=0))
        add(ParaStyle("DefText", f.body, body, color=self.text, line_spacing=ls, align="left", space_after=0))
        add(ParaStyle("Legend", f.body, small + 0.5, color=self.text, line_spacing=1.12, space_after=self._gap(1.2),
                      left_indent=11, first_line_indent=-11))
        add(ParaStyle("TileValue", f.heading, self._s(f.heading_size + 7), bold=True, color=self.accent,
                      align="center", line_spacing=1.0, space_after=0))
        add(ParaStyle("TileLabel", f.body, small + 0.3, color=self.text, align="center", line_spacing=1.05))
        add(ParaStyle("TileCaption", f.body, small - 0.8, italic=True, color=self.muted, align="center",
                      line_spacing=1.0))
        add(ParaStyle("CardTitle", f.body, body + 0.6, bold=True, color=self.accent, keep_with_next=True,
                      line_spacing=ls, docx_base="Heading 2", outline_level=1))
        add(ParaStyle("BarLabel", f.body, small + 0.6, bold=True, color=self.text, line_spacing=1.05,
                      keep_with_next=True, space_after=self._gap(0.8)))
        return st

    # ------------------------------------------------------------------ text helpers
    def _case(self, text: str) -> str:
        return text.upper() if self.spec.heading.case == "upper" else text

    def _link_run(self, text: str, url: str, style_color: str | None = None) -> Run:
        return Run(text, link=url or None, color=style_color)

    def _contact_runs(self, contacts: list[ContactItem], color: str | None, sep_color: str | None,
                      icon_color: str | None = None) -> list[Run]:
        runs: list[Run] = []
        sep = self.spec.header.separator
        for i, c in enumerate(contacts):
            if i:
                runs.append(Run(sep, color=sep_color))
            if self.spec.header.contact_icons:
                runs.append(Run(CONTACT_ICONS.get(c.key, LINK_ICON) + "\u00a0", color=icon_color or color or self.accent,
                                font=ICON_FONT))
            runs.append(Run(c.value, link=c.url or None, color=color))
        return runs

    def _author_runs(self, authors: str, names: list[str]) -> list[Run]:
        if not authors:
            return []
        if not names or not self.spec.publications.highlight_name:
            return [Run(authors)]
        pattern = "|".join(re.escape(n) for n in sorted(set(names), key=len, reverse=True) if n)
        if not pattern:
            return [Run(authors)]
        runs: list[Run] = []
        pos = 0
        for m in re.finditer(pattern, authors, flags=re.IGNORECASE):
            if m.start() > pos:
                runs.append(Run(authors[pos : m.start()]))
            runs.append(Run(m.group(0), bold=True))
            pos = m.end()
        if pos < len(authors):
            runs.append(Run(authors[pos:]))
        return runs

    # ------------------------------------------------------------------ header
    def header_blocks(self) -> list:
        d = self.doc
        hs = self.spec.header
        blocks: list = []
        if d.title_line:
            blocks.append(Para("TitleLine", [Run(d.title_line, bold=True, underline=True)]))
        name_text = d.name.upper() if hs.name_case == "upper" else d.name
        name_run = Run(name_text, small_caps=hs.name_case == "small_caps")
        style = hs.style
        if style in ("split", "banner", "framed") and not self.spec.tables_allowed:
            style = "left"

        if style == "framed":
            c = self.spec.colours
            inner = [Para("BannerName", [name_run])]
            if d.headline:
                inner.append(Para("BannerText", [Run(d.headline)]))
            outer: list = [BannerBlock(inner, fill=c.banner_fill, padding=10)]
            if d.contacts:
                outer.append(Para("BannerContact", self._contact_runs(d.contacts, c.banner_text, c.banner_text,
                                                                     c.banner_text), align="center", space_before=5))
            blocks.append(BannerBlock(outer, fill=c.banner_outer, padding=6))
            blocks.append(Spacer(self._gap(6)))
            return self._with_photo(blocks)

        if style == "banner":
            inner = [Para("BannerName", [name_run])]
            if d.headline:
                inner.append(Para("BannerText", [Run(d.headline)]))
            if d.contacts:
                inner.append(Para("BannerContact", self._contact_runs(d.contacts, self.spec.colours.banner_text,
                                                                         self.spec.colours.banner_text)))
            blocks.append(BannerBlock(inner, fill=self.spec.colours.banner_fill, padding=9))
            blocks.append(Spacer(self._gap(4)))
            return self._with_photo(blocks)

        if style == "split":
            left = [Para("Name", [name_run], align="left")]
            if d.headline:
                left.append(Para("Headline", [Run(d.headline)], align="left"))
            right = [Para("Contact", [Run(c.value, link=c.url or None)], align="right", space_after=0.5)
                     for c in d.contacts]
            blocks.append(TableBlock(rows=[[Cell(left), Cell(right)]], col_widths=[0.6, 0.4], borders="none",
                                     padding=0))
            blocks.extend(self._header_rule())
            return self._with_photo(blocks)

        # centered / left / sidebar (sidebar shows name across the top; contacts go in the sidebar)
        blocks.append(Para("Name", [name_run]))
        if d.headline:
            blocks.append(Para("Headline", [Run(d.headline)]))
        if style != "sidebar" and d.contacts:
            if hs.contact_style == "stacked" and style == "centered":
                for c in d.contacts:
                    blocks.append(Para("Contact", [Run(c.value, link=c.url or None)]))
            elif hs.contact_style == "stacked":
                # Left header with stacked contacts: two per line keeps it compact.
                for i in range(0, len(d.contacts), 2):
                    blocks.append(Para("Contact", self._contact_runs(d.contacts[i : i + 2], None, self.muted)))
            else:
                blocks.append(Para("Contact", self._contact_runs(d.contacts, None, self.muted)))
        blocks.extend(self._header_rule())
        return self._with_photo(blocks)

    def _header_rule(self) -> list:
        r = self.spec.header.rule
        if r == "none":
            return [Spacer(self._gap(3))]
        if r == "double":
            return [Rule(self.rule_color, 0.5, space_before=self._gap(3), space_after=1.2),
                    Rule(self.rule_color, 0.5, space_before=0, space_after=self._gap(4))]
        width = 2.0 if r == "thick" else 0.75
        return [Rule(self.rule_color, width, space_before=self._gap(3), space_after=self._gap(4))]

    def _with_photo(self, blocks: list) -> list:
        if not (self.doc.photo_path and self.spec.photo.allowed and self.spec.tables_allowed):
            return blocks
        img = ImageBlock(self.doc.photo_path, self.spec.photo.width_mm * MM, align="right")
        photo_frac = min(0.3, (self.spec.photo.width_mm * MM + 8) / self.page.text_width)
        return [TableBlock(rows=[[Cell(blocks), Cell([img])]], col_widths=[1 - photo_frac, photo_frac],
                           borders="none", padding=0)]

    # ------------------------------------------------------------------ section headings
    def heading_para(self, title: str) -> Para:
        hd = self.spec.heading
        self.section_index += 1
        text = self._case(title)
        if hd.style == "numbered":
            text = f"{self.section_index}. {text}"
        run = Run(text, small_caps=hd.case == "small_caps")
        p = Para("SectionHeading", [run], heading_level=1)
        if hd.style in ("rule_below", "caps_rule"):
            p.border_bottom = Border(self.rule_color, hd.rule_weight, space=1.5)
        elif hd.style == "shaded_bar":
            p.shading = self.fill
        elif hd.style == "left_bar":
            p.border_left = Border(self.accent, hd.rule_weight, space=4)
        return p

    # ------------------------------------------------------------------ entries
    def _status_suffix(self, e: IREntry) -> list[Run]:
        if not e.status_label or e.kind in ("assignment", "publication"):
            return []
        if e.status_label.lower() in (e.date_text or "").lower():
            return []
        return [Run(f" ({e.status_label})", italic=True, color=self.muted)]

    def entry_blocks(self, e: IREntry, level: int = 0, indent: float = 0.0) -> list:
        es = self.spec.entry
        style = es.style
        blocks: list = []
        if not e.title and e.subtitle:
            # No recorded title (e.g. designation not yet entered): the organisation becomes the title line.
            e = e.model_copy(update={"title": e.subtitle, "subtitle": ""})
        title_runs = [Run(e.title, bold=True)] + self._status_suffix(e)
        date_runs = [Run(e.date_text)] if e.date_text else None
        sub = e.subtitle
        loc = e.location if es.show_location else ""
        gutter = es.gutter_mm * MM
        body_indent = indent

        if style == "date_left":
            blocks.append(Para("EntryTitle", title_runs, gutter_runs=[Run(e.date_text)] if e.date_text else [Run("")],
                               gutter_width=gutter, left_indent=indent + gutter))
            body_indent = indent + gutter
            if sub or loc:
                blocks.append(Para("EntrySub", [Run(", ".join(x for x in (sub, loc) if x), italic=es.subtitle_italic)],
                                   left_indent=body_indent))
        elif style == "org_first" and sub:
            blocks.append(Para("EntryTitle", [Run(sub, bold=True)], right_runs=[Run(loc)] if loc else None,
                               left_indent=indent or None))
            blocks.append(Para("EntrySub", [Run(e.title, italic=es.subtitle_italic, color=self.text),
                                            *self._status_suffix(e)],
                               right_runs=date_runs, left_indent=indent or None))
        elif style == "stacked":
            blocks.append(Para("EntryTitle", title_runs, left_indent=indent or None))
            meta = " · ".join(x for x in (sub, loc, e.date_text) if x)
            if meta:
                blocks.append(Para("EntryMeta", [Run(meta)], left_indent=indent or None))
        elif style == "inline":
            runs = list(title_runs)
            if sub:
                runs.append(Run(f", {sub}"))
            if loc:
                runs.append(Run(f", {loc}", color=self.muted))
            if e.date_text:
                runs.append(Run(f" ({e.date_text})", color=self.muted))
            blocks.append(Para("EntryTitle", runs, left_indent=indent or None))
        else:  # title_date_right (and org_first without organisation)
            blocks.append(Para("EntryTitle", title_runs, right_runs=date_runs, left_indent=indent or None))
            if sub or loc:
                blocks.append(Para("EntrySub", [Run(", ".join(x for x in (sub, loc) if x), italic=es.subtitle_italic)],
                                   left_indent=indent or None))

        if e.description and es.show_description:
            blocks.append(Para("Body", [Run(e.description)], left_indent=body_indent or None))
        for label_, value in e.meta:
            blocks.append(Para("Meta", [Run(f"{label_}: ", bold=True), Run(value)], left_indent=body_indent or None))
        glyph = es.bullet_glyph
        for b in e.bullets:
            blocks.append(Para("Bullet", [Run(b.text)], bullet=glyph, bullet_level=level,
                               left_indent=(body_indent + self.bullet_indent * (level + 1)) if (body_indent or level)
                               else None))
        for child in e.children:
            blocks.extend(self.child_blocks(child, body_indent))
        blocks.append(Spacer(self._gap(es.space_between)))
        return blocks

    def sidebar_entry_blocks(self, e: IREntry) -> list:
        """Compact stacked entry for narrow sidebars: title, then organisation, then date."""
        out: list = [Para("SidebarTitle", [Run(e.title)] + self._status_suffix(e))]
        if e.subtitle:
            out.append(Para("SidebarText", [Run(e.subtitle, italic=True)], space_after=0))
        if e.date_text:
            out.append(Para("SidebarText", [Run(e.date_text, color=self.muted)], space_after=0))
        for label_, value in e.meta:
            if label_ in ("Grade", "Thesis"):
                out.append(Para("SidebarText", [Run(f"{label_}: ", bold=True), Run(value)], space_after=0))
        out.append(Spacer(self._gap(4)))
        return out

    def child_blocks(self, c: IREntry, indent: float) -> list:
        es = self.spec.entry
        runs = []
        if c.status_label:
            runs.append(Run(f"{c.status_label}: ", italic=True, color=self.muted))
        runs.append(Run(c.title, bold=True))
        if c.subtitle:
            runs.append(Run(f", {c.subtitle}"))
        child_indent = indent + self.bullet_indent
        blocks: list = [Para("ChildTitle", runs, right_runs=[Run(c.date_text)] if c.date_text else None,
                             left_indent=child_indent)]
        if c.description and es.show_description:
            blocks.append(Para("Body", [Run(c.description)], left_indent=child_indent))
        for b in c.bullets:
            blocks.append(Para("Bullet", [Run(b.text)], bullet=es.bullet_glyph, bullet_level=1,
                               left_indent=child_indent + self.bullet_indent))
        return blocks

    # ------------------------------------------------------------------ sections
    def section_body(self, s: IRSection) -> list:
        lay = s.layout
        if lay == "paragraph":
            out = []
            for text in s.paragraphs:
                p = Para("Summary" if s.key == "summary" else "Body", [Run(text)])
                if s.key == "summary" and self.spec.summary_style == "boxed":
                    p.shading = self.fill
                    p.border_left = Border(self.accent, 2.0, space=6)
                out.append(p)
            return out
        if lay == "entries":
            out = []
            cards = (s.key == "projects" and self.spec.entry.project_style == "cards" and self.spec.tables_allowed
                     and not self.in_sidebar)
            for e in s.entries:
                if self.in_sidebar:
                    out.extend(self.sidebar_entry_blocks(e))
                elif cards:
                    out.extend(self.card_blocks(e))
                else:
                    out.extend(self.entry_blocks(e))
            return out
        if lay == "definitions":
            return self.definition_blocks(s)
        if lay == "chart":
            return self.chart_blocks(s)
        if lay == "overview":
            return self.overview_blocks(s)
        if lay == "publications":
            return self.publication_blocks(s)
        if lay == "skills":
            return self.skills_blocks(s)
        if lay == "list":
            return self.list_blocks(s)
        if lay in ("table", "particulars"):
            return self.table_blocks(s)
        if lay == "declaration":
            out = [Para("Declaration", [Run(t)]) for t in s.paragraphs]
            items = list(s.items) + ["", "", ""]
            out.append(Spacer(self._gap(14)))
            out.append(Para("Body", [Run(items[0])]))
            out.append(Para("Body", [Run(items[1])], right_runs=[Run("(Signature)")]))
            if items[2]:
                out.append(Para("Body", [Run("")], right_runs=[Run(items[2], bold=True)]))
            return out
        return []

    def publication_blocks(self, s: IRSection) -> list:
        out: list = []
        numbered = self.spec.publications.style == "numbered"
        gutter = 9 * MM if len(s.entries) >= 10 else 7.5 * MM
        for i, e in enumerate(s.entries, start=1):
            runs = self._author_runs(e.authors, e.highlight_names)
            rest = e.citation_rest
            if runs:
                runs.append(Run(", "))
            m = re.search(r"\sdoi:\s*(\S+)$", rest)
            if m and e.link:
                runs.append(Run(rest[: m.start()]))
                runs.append(Run(f" doi: {m.group(1)}", link=e.link, color=self.spec.colours.link))
            else:
                runs.append(Run(rest))
            if e.status_label and e.status_label not in ("Accepted",):
                runs.append(Run(f" [{e.status_label}]", italic=True, color=self.muted))
            if numbered:
                out.append(Para("Citation", runs, gutter_runs=[Run(f"[{i}]")], gutter_width=gutter,
                                left_indent=gutter))
            else:
                out.append(Para("Bullet", runs, bullet=self.spec.entry.bullet_glyph))
        return out

    def skills_blocks(self, s: IRSection) -> list:
        sk = self.spec.skills
        out: list = []
        if sk.style == "bars" and self.spec.tables_allowed and any(lv > 0 for g in s.skill_groups for lv in g.levels):
            return self.skill_bar_blocks(s)
        if self.in_sidebar:
            for g in s.skill_groups:
                out.append(Para("SidebarTitle", [Run(g.label)]))
                out.append(Para("SidebarText", [Run(", ".join(g.items))]))
            return out
        style = sk.style
        if style == "table" and not self.spec.tables_allowed:
            style = "inline_categories"
        if style == "table":
            rows = [[Cell([Para("TableHead", [Run(g.label)])]), Cell([Para("TableText", [Run(sk.separator.join(g.items))])])]
                    for g in s.skill_groups]
            out.append(TableBlock(rows=rows, col_widths=[0.27, 0.73], borders="rows", border_color=self.spec.colours.rule,
                                  border_width=0.4, padding=2.5))
            out.append(Spacer(self._gap(2)))
        elif style == "bullets":
            for g in s.skill_groups:
                out.append(Para("Bullet", [Run(f"{g.label}: ", bold=True), Run(sk.separator.join(g.items))],
                                bullet=self.spec.entry.bullet_glyph))
        elif style == "inline":
            items = [i for g in s.skill_groups for i in g.items]
            out.append(Para("Body", [Run(" · ".join(items))]))
        else:
            for g in s.skill_groups:
                out.append(Para("Body", [Run(f"{g.label}: ", bold=True), Run(sk.separator.join(g.items))],
                                space_after=self._gap(1.5)))
        return out

    def list_blocks(self, s: IRSection) -> list:
        sk = self.spec.skills
        if self.in_sidebar:
            return [Para("SidebarText", [Run(item)]) for item in s.items]
        if s.key == "competencies":
            style = sk.competencies_style
            if style == "columns" and not self.spec.tables_allowed:
                style = "inline"
            if style == "columns":
                n = sk.columns
                per = -(-len(s.items) // n)
                cols = [s.items[i * per : (i + 1) * per] for i in range(n)]
                cells = [Cell([Para("Bullet", [Run(it)], bullet="▪") for it in col]) for col in cols]
                return [TableBlock(rows=[cells], col_widths=[1 / n] * n, borders="none", padding=1.5),
                        Spacer(self._gap(2))]
            if style == "bullets":
                return [Para("Bullet", [Run(it)], bullet=self.spec.entry.bullet_glyph) for it in s.items]
            return [Para("Body", [Run("  •  ".join(s.items) if len(s.items) < 6 else " · ".join(s.items))])]
        return [Para("Body", [Run(", ".join(s.items))])]

    def table_blocks(self, s: IRSection) -> list:
        t = s.table
        if t is None or not t.rows:
            return []
        if not self.spec.tables_allowed:
            out: list = []
            for row in t.rows:
                if t.header:
                    runs: list[Run] = []
                    for j, cell in enumerate(row):
                        if not cell:
                            continue
                        hdr = t.header[j] if j < len(t.header) else ""
                        if hdr and hdr.lower().startswith("s. no"):
                            continue
                        runs.extend([Run(f"{hdr}: ", bold=True), Run(cell.replace("\n", "; ")), Run("   ")])
                    out.append(Para("Body", runs))
                else:
                    out.append(Para("Body", [Run(f"{row[0]}: ", bold=True), Run(" ".join(row[1:]))]))
            return out
        rows: list[list[Cell]] = []
        if t.header:
            rows.append([Cell([Para("TableHead", [Run(h)])]) for h in t.header])
        for row in t.rows:
            cells = []
            for j, val in enumerate(row):
                paras = [Para("TableText", [Run(line)]) for line in (val.split("\n") if val else [""])]
                if s.layout == "particulars" and j == 0:
                    paras = [Para("TableHead", [Run(val)])]
                cells.append(Cell(paras))
            rows.append(cells)
        widths = t.col_widths if len(t.col_widths) == len(rows[0]) else [1 / len(rows[0])] * len(rows[0])
        gov = self.spec.heading.style == "numbered"
        return [TableBlock(rows=rows, col_widths=widths, header_rows=1 if t.header else 0,
                           borders="grid" if gov or s.layout == "table" else "rows",
                           border_color=self.spec.colours.rule if not gov else "#000000", border_width=0.5,
                           header_fill=self.fill if t.header else None, padding=3),
                Spacer(self._gap(3))]

    # ------------------------------------------------------------------ graphical elements
    def _graphics_on(self) -> bool:
        return self.spec.graphics.enabled and self.spec.tables_allowed

    def definition_blocks(self, s: IRSection) -> list:
        t = s.table
        if t is None or not t.rows:
            return []
        if self.in_columns and not self.in_sidebar and self.spec.tables_allowed:
            out = []
            for row in t.rows:
                area, desc = (row + ["", ""])[:2]
                lines = area.split("\n")
                head = [Run(lines[0])] + ([Run(f"  ·  {lines[1]}", color=self.muted, bold=False)]
                                          if len(lines) > 1 else [])
                out.append(Para("DefLabel", head, keep_with_next=True, space_before=self._gap(2)))
                if desc:
                    out.append(Para("DefText", [Run(desc)], space_after=self._gap(2),
                                    border_bottom=Border(self.spec.colours.rule, 0.4, space=3)))
            return out
        if self.in_sidebar or not self.spec.tables_allowed:
            out: list = []
            for row in t.rows:
                area, desc = (row + ["", ""])[:2]
                lines = area.split("\n")
                head = [Run(lines[0], bold=True)] + ([Run(f" ({lines[1]})", color=self.muted)] if len(lines) > 1 else [])
                out.append(Para("SidebarTitle" if self.in_sidebar else "EntryTitle", head))
                if desc:
                    out.append(Para("SidebarText" if self.in_sidebar else "Body", [Run(desc)]))
            return out
        rows = []
        for row in t.rows:
            area, desc = (row + ["", ""])[:2]
            lines = area.split("\n")
            left = [Para("DefLabel", [Run(lines[0])])]
            if len(lines) > 1:
                left.append(Para("Meta", [Run(lines[1])]))
            rows.append([Cell(left), Cell([Para("DefText", [Run(desc)])])])
        widths = t.col_widths if len(t.col_widths) == 2 else [0.32, 0.68]
        return [TableBlock(rows=rows, col_widths=widths, borders="rows", border_color=self.spec.colours.rule,
                           border_width=0.4, padding=3.5), Spacer(self._gap(3))]

    def _legend(self, s: IRSection, with_swatches: bool) -> list:
        out = []
        for i, line in enumerate(s.items):
            runs = [Run("■ ", color=self.palette[i % len(self.palette)])] if with_swatches else []
            out.append(Para("Legend", runs + [Run(line)]))
        return out

    def chart_blocks(self, s: IRSection) -> list:
        ch = s.chart
        if ch is None or not ch.points:
            return []
        if not self._graphics_on() or self.in_sidebar:
            return [Para("Bullet", [Run(line)], bullet=self.spec.entry.bullet_glyph) for line in s.items]
        g = self.spec.graphics
        width = self.cur_width
        if ch.kind == "timeline":
            data = graphics.timeline([(p.label, p.start, p.end, p.is_current, p.value) for p in ch.points],
                                     width, g.timeline_height_mm * MM, self.palette, font=self.spec.fonts.body,
                                     text=self.text, axis=self.spec.colours.rule)
        else:
            data = graphics.stacked_years([(p.label, p.group, p.value) for p in ch.points], ch.series, width,
                                          g.chart_height_mm * MM, self.palette, font=self.spec.fonts.body,
                                          text=self.text, muted=self.muted)
        out: list = [ImageBlock("", width, align="center", data=data, alt=ch.alt_text, space_after=self._gap(3),
                                keep_with_next=True)]
        out.extend(self._legend(s, with_swatches=ch.kind == "timeline"))
        if ch.caption:
            out.append(Para("Meta", [Run(ch.caption, italic=True)]))
        out.append(Spacer(self._gap(3)))
        return out

    def overview_blocks(self, s: IRSection) -> list:
        tiles = s.tiles
        out: list = []
        if tiles:
            if not self._graphics_on() or self.in_sidebar or self.in_columns:
                runs: list[Run] = []
                for i, t in enumerate(tiles):
                    if i:
                        runs.append(Run("   ·   ", color=self.muted))
                    runs.extend([Run(f"{t.value} ", bold=True, color=self.accent if self._graphics_on() else None),
                                 Run(t.label)])
                    if t.caption:
                        runs.append(Run(f" ({t.caption})", italic=True, color=self.muted))
                out.append(Para("Body", runs))
            else:
                per = max(2, min(self.spec.graphics.tiles_per_row, len(tiles)))
                rows = []
                for i in range(0, len(tiles), per):
                    chunk = tiles[i:i + per]
                    cells = []
                    for t in chunk:
                        blocks = [Para("TileValue", [Run(t.value)]), Para("TileLabel", [Run(t.label)])]
                        if t.caption:
                            blocks.append(Para("TileCaption", [Run(t.caption)]))
                        cells.append(Cell(blocks, fill=self.spec.colours.tile_fill))
                    while len(cells) < per:
                        cells.append(Cell([Para("TileLabel", [Run("")])]))
                    rows.append(cells)
                out.append(TableBlock(rows=rows, col_widths=[1 / per] * per, borders="grid", border_color="#FFFFFF",
                                      border_width=4, padding=4))
                out.append(Spacer(self._gap(4)))
        ch = s.chart
        if ch is not None and ch.points and self._graphics_on() and not self.in_sidebar:
            g = self.spec.graphics
            width = self.cur_width
            data = graphics.stacked_years([(p.label, p.group, p.value) for p in ch.points], ch.series, width,
                                          g.chart_height_mm * MM, self.palette, font=self.spec.fonts.body,
                                          text=self.text, muted=self.muted)
            out.append(ImageBlock("", width, align="center", data=data, alt=ch.alt_text, space_after=self._gap(2)))
            if ch.caption:
                out.append(Para("Meta", [Run(ch.caption, italic=True)]))
            out.append(Spacer(self._gap(2)))
        return out

    def skill_bar_blocks(self, s: IRSection) -> list:
        c = self.spec.colours
        out: list = []
        if self.in_sidebar:
            bar_w = min(self.cur_width - 4, self.spec.graphics.bar_width_mm * MM * 1.6)
            for grp in s.skill_groups:
                out.append(Para("SidebarTitle", [Run(grp.label, color=self.accent)], space_after=2))
                unrated = []
                for item, lvl in zip(grp.items, grp.levels or [0] * len(grp.items), strict=False):
                    if lvl <= 0:
                        unrated.append(item)
                        continue
                    out.append(Para("BarLabel", [Run(item)]))
                    out.append(ImageBlock("", bar_w, align="left", alt=f"{item}: {lvl} of 5 (self-assessed)",
                                          data=graphics.rating_bar(lvl, round(bar_w, 1), 4.0, self.accent,
                                                                   c.bar_track), space_after=3.5))
                if unrated:
                    out.append(Para("SidebarText", [Run(", ".join(unrated))]))
                out.append(Spacer(self._gap(3)))
            out.append(Para("SidebarText", [Run(SELF_RATING_NOTE, italic=True, color=self.muted, size=self._s(6.8))]))
            return out
        bar_w = self.spec.graphics.bar_width_mm * MM
        if self.in_columns:
            for grp in s.skill_groups:
                out.append(Para("BarLabel", [Run(grp.label, color=self.accent)]))
                unrated = []
                for item, lvl in zip(grp.items, grp.levels or [0] * len(grp.items), strict=False):
                    if lvl <= 0:
                        unrated.append(item)
                        continue
                    out.append(Para("TableText", [Run(item)], keep_with_next=True))
                    out.append(ImageBlock("", bar_w, align="left", alt=f"{item}: {lvl} of 5 (self-assessed)",
                                          data=graphics.rating_bar(lvl, round(bar_w, 1), 4.0, self.accent,
                                                                   c.bar_track), space_after=3))
                if unrated:
                    out.append(Para("Body", [Run(", ".join(unrated))]))
            out.append(Para("Meta", [Run(SELF_RATING_NOTE, italic=True)]))
            return out
        for grp in s.skill_groups:
            rated = [(i, lv) for i, lv in zip(grp.items, grp.levels or [0] * len(grp.items), strict=False) if lv > 0]
            unrated = [i for i, lv in zip(grp.items, grp.levels or [0] * len(grp.items), strict=False) if lv <= 0]
            out.append(Para("BarLabel", [Run(grp.label, color=self.accent)]))
            rows = []
            for k in range(0, len(rated), 2):
                cells = []
                for item, lvl in rated[k:k + 2]:
                    cells.append(Cell([Para("TableText", [Run(item)])]))
                    cells.append(Cell([ImageBlock("", bar_w, align="left", alt=f"{item}: {lvl} of 5 (self-assessed)",
                                                  data=graphics.rating_bar(lvl, round(bar_w, 1), 4.0, self.accent,
                                                                           c.bar_track))]))
                while len(cells) < 4:
                    cells.append(Cell([Para("TableText", [Run("")])]))
                rows.append(cells)
            if rows:
                text_w = (1 - 2 * min(0.24, bar_w / self.cur_width + 0.02)) / 2
                bw = (1 - 2 * text_w) / 2
                out.append(TableBlock(rows=rows, col_widths=[text_w, bw, text_w, bw], borders="none", padding=1.6))
            if unrated:
                out.append(Para("Body", [Run(", ".join(unrated))]))
            out.append(Spacer(self._gap(2)))
        out.append(Para("Meta", [Run(SELF_RATING_NOTE, italic=True)]))
        return out

    def card_blocks(self, e: IREntry) -> list:
        inner: list = [Para("CardTitle", [Run(e.title)] + self._status_suffix(e),
                            right_runs=[Run(e.date_text, color=self.muted, bold=False)] if e.date_text else None)]
        if e.subtitle:
            inner.append(Para("EntrySub", [Run(e.subtitle, italic=True)]))
        labels = {lbl for lbl, _ in e.facets}
        if e.description and "Challenge" not in labels:
            inner.append(Para("Body", [Run(e.description)]))
        for lbl, text in e.facets:
            inner.append(Para("Body", [Run(f"{lbl}: ", bold=True, color=self.accent), Run(text)],
                              space_after=self._gap(1.5)))
        if e.highlights:
            runs: list[Run] = []
            for i, h in enumerate(e.highlights):
                if i:
                    runs.append(Run("    "))
                runs.extend([Run("◆ ", color=self.accent, font=ICON_FONT), Run(h, bold=True)])
            inner.append(Para("Body", runs))
        for b in e.bullets:
            if b.source_field in FACET_SOURCE_FIELDS:
                continue
            inner.append(Para("Bullet", [Run(b.text)], bullet=self.spec.entry.bullet_glyph))
        for lbl, value in e.meta:
            inner.append(Para("Meta", [Run(f"{lbl}: ", bold=True), Run(value)]))
        if self.in_columns:
            # Shaded paragraphs with an accent bar look like a card without nesting a table.
            fill = self.spec.colours.tile_fill
            for p in inner:
                p.shading = fill
                p.border_left = Border(self.accent, 2.2, space=5)
                p.space_after = 0 if p is not inner[-1] else self._gap(2)
            inner[0].space_before = self._gap(3)
            return [*inner, Spacer(self._gap(4))]
        return [BannerBlock(inner, fill=self.spec.colours.tile_fill, padding=7), Spacer(self._gap(5))]

    # ------------------------------------------------------------------ assembly
    def section_blocks(self, s: IRSection) -> list:
        body = self.section_body(s)
        if not body:
            return []
        if self.in_sidebar:
            return [Para("SidebarHeading", [Run(s.title.upper())], heading_level=1), *body]
        if self.spec.heading.style == "margin_label":
            label = Para("MarginLabel", [Run(self._case(s.title))], heading_level=1)
            return [LabeledSection(label=label, blocks=body, label_width=self.spec.heading.label_width_mm * MM,
                                   gap=8), Spacer(self._gap(self.spec.heading.space_before))]
        return [self.heading_para(s.title), *body]

    def sidebar_contact_blocks(self) -> list:
        if not self.doc.contacts:
            return []
        out: list = [Para("SidebarHeading", [Run("CONTACT")], heading_level=1)]
        from reportlab.pdfbase.pdfmetrics import stringWidth

        from ris.rendering import fonts

        base = self.styles_cache["SidebarText"].size if hasattr(self, "styles_cache") else self._s(
            self.spec.fonts.small_size) + 0.4
        avail = self.cur_width - (12 if self.spec.header.contact_icons else 0) - 4
        for c in self.doc.contacts:
            icon = ([Run(CONTACT_ICONS.get(c.key, LINK_ICON) + "\u00a0", color=self.accent, font=ICON_FONT)]
                    if self.spec.header.contact_icons else [])
            size = None
            width = stringWidth(c.value, fonts.font_name(self.spec.fonts.body), base)
            if width > avail:
                # Shrink long values (URLs) to fit one line rather than breaking them mid-word.
                size = round(max(6.2, base * avail / width), 2)
            out.append(Para("SidebarText", icon + [Run(c.value, link=c.url or None, size=size)]))
        return out

    def footer(self) -> FooterLayout:
        ft = self.spec.footer
        left = ""
        if ft.show_name and self.doc.name:
            left = self.doc.name + (f" — {ft.text}" if ft.text else "")
        elif ft.text:
            left = ft.text
        return FooterLayout(left_text=left, page_numbers=ft.page_numbers, note=self.doc.footer_note,
                            font=self.spec.fonts.body, size=self._s(self.spec.fonts.small_size - 0.5), color=self.muted)

    def letter_blocks(self) -> list:
        lt = self.doc.letter
        assert lt is not None
        blocks: list = []
        for i, line in enumerate(lt.sender_lines):
            blocks.append(Para("Body", [Run(line, bold=(i == 0))], space_after=0))
        blocks.append(Rule(self.rule_color, 0.6, space_before=self._gap(4), space_after=self._gap(6)))
        if lt.date_line:
            blocks.append(Para("Body", [Run(lt.date_line)], align="right"))
        if lt.recipient_lines:
            blocks.append(Para("Body", [Run("To,")], space_after=0))
            for line in lt.recipient_lines:
                blocks.append(Para("Body", [Run(line)], space_after=0))
            blocks.append(Spacer(self._gap(8)))
        if lt.subject:
            blocks.append(Para("Body", [Run("Subject: ", bold=True), Run(lt.subject, bold=True)]))
        if lt.reference_line:
            blocks.append(Para("Body", [Run("Reference: ", bold=True), Run(lt.reference_line)]))
        if lt.salutation:
            blocks.append(Spacer(self._gap(4)))
            blocks.append(Para("Body", [Run(lt.salutation)]))
        for para in lt.paragraphs:
            blocks.append(Para("Declaration", [Run(para)], align="justify"))
        if lt.closing:
            blocks.append(Spacer(self._gap(6)))
            blocks.append(Para("Body", [Run(lt.closing)]))
            blocks.append(Spacer(self._gap(26)))
        for i, line in enumerate(lt.signature_lines):
            blocks.append(Para("Body", [Run(line, bold=(i == 0))], space_after=0))
        if lt.place_line:
            blocks.append(Spacer(self._gap(8)))
            blocks.append(Para("Body", [Run(lt.place_line)]))
        if lt.enclosures:
            blocks.append(Spacer(self._gap(6)))
            blocks.append(Para("Body", [Run("Enclosures: ", bold=True), Run("; ".join(lt.enclosures))]))
        return blocks

    def plan(self) -> LayoutDocument:
        styles = self.styles()
        self.styles_cache = styles
        if self.doc.letter is not None:
            md = dict(self.doc.metadata)
            md.setdefault("author", self.doc.name)
            footer = FooterLayout(note=self.doc.footer_note, font=self.spec.fonts.body,
                                  size=self._s(self.spec.fonts.small_size - 0.5), color=self.muted)
            return LayoutDocument(page=self.page, styles=styles, blocks=self.letter_blocks(), footer=footer,
                                  metadata=md, link_color=self.spec.colours.link, bullet_indent=self.bullet_indent,
                                  template_id=self.spec.id)
        blocks: list = list(self.header_blocks())
        cols = self.spec.columns
        if cols.enabled and self.spec.tables_allowed:
            side_keys = set(cols.sidebar_sections)
            side_secs = [s for s in self.doc.sections if s.key in side_keys and s.sidebar_ok]
            main_secs = [s for s in self.doc.sections if s not in side_secs]
            self.in_sidebar = True
            self.in_columns = True
            gap = cols.gap_mm * MM
            # Must match the renderers: the filled sidebar has 6 pt padding each side; both columns lose gap/2.
            self.cur_width = self.page.text_width * cols.width_frac - 2 * 6.0 - gap / 2
            # Contacts go in the sidebar only when the header itself does not show them.
            side_blocks = self.sidebar_contact_blocks() if self.spec.header.style == "sidebar" else []
            for s in side_secs:
                side_blocks.extend(self.section_blocks(s))
            self.in_sidebar = False
            self.cur_width = self.page.text_width * (1 - cols.width_frac) - gap / 2
            main_blocks: list = []
            for s in main_secs:
                main_blocks.extend(self.section_blocks(s))
            self.cur_width = self.page.text_width
            self.in_columns = False
            # "Keep with next" inside a page-spanning column row stops LibreOffice (and sometimes Word) from
            # splitting the row across pages, pushing the whole body to the next page. Disable it there.
            for p in _walk_paras(side_blocks + main_blocks):
                p.keep_with_next = False
            for img in _walk_images(side_blocks + main_blocks):
                img.keep_with_next = False
            if cols.side == "left":
                blocks.append(ColumnsBlock(left=side_blocks, right=main_blocks, left_frac=cols.width_frac,
                                           gap=cols.gap_mm * MM, left_fill=self.spec.colours.sidebar_fill))
            else:
                blocks.append(ColumnsBlock(left=main_blocks, right=side_blocks, left_frac=1 - cols.width_frac,
                                           gap=cols.gap_mm * MM, right_fill=self.spec.colours.sidebar_fill))
        else:
            for s in self.doc.sections:
                blocks.extend(self.section_blocks(s))
        md = dict(self.doc.metadata)
        md.setdefault("author", self.doc.name)
        return LayoutDocument(page=self.page, styles=styles, blocks=blocks, footer=self.footer(), metadata=md,
                              link_color=self.spec.colours.link, bullet_indent=self.bullet_indent,
                              template_id=self.spec.id)


def _walk(blocks):
    for b in blocks:
        yield b
        if isinstance(b, TableBlock):
            for row in b.rows:
                for cell in row:
                    yield from _walk(cell.blocks)
        elif isinstance(b, ColumnsBlock):
            yield from _walk(b.left)
            yield from _walk(b.right)
        elif isinstance(b, BannerBlock):
            yield from _walk(b.blocks)
        elif isinstance(b, LabeledSection):
            yield b.label
            yield from _walk(b.blocks)


def _walk_paras(blocks):
    return [b for b in _walk(blocks) if isinstance(b, Para)]


def _walk_images(blocks):
    return [b for b in _walk(blocks) if isinstance(b, ImageBlock)]


def plan_layout(doc: ResumeDocument, spec: TemplateSpec) -> LayoutDocument:
    return LayoutPlanner(doc, spec).plan()
