"""Built-in PDF renderer: LayoutDocument → PDF (ReportLab).

Produces genuine PDFs with selectable text, embedded TrueType fonts (with a
per-glyph Unicode fallback), link annotations, outline bookmarks for section
headings, document metadata and "Page X of Y" footers. Used when LibreOffice
is unavailable or when the built-in engine is selected; it draws the same
layout blocks as the DOCX renderer.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Table,
    TableStyle,
)
from reportlab.platypus import Spacer as RLSpacer
from reportlab.platypus.flowables import HRFlowable

from ris import __version__
from ris.rendering import fonts
from ris.rendering.blocks import (
    BannerBlock,
    ColumnsBlock,
    ImageBlock,
    LabeledSection,
    LayoutDocument,
    PageBreakBlock,
    Para,
    ParaStyle,
    Rule,
    Run,
    Spacer,
    TableBlock,
)

_ALIGN = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT, "justify": TA_JUSTIFY}


@dataclass
class PdfRenderResult:
    page_count: int
    missing_glyphs: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)


class _Decorated(Flowable):
    """A paragraph with optional shading, left bar and bottom/top rules."""

    def __init__(self, para: Paragraph, avail: float, shading=None, left=None, bottom=None, top=None,
                 space_before: float = 0, space_after: float = 0, keep_with_next: bool = False):
        super().__init__()
        self.para = para
        self.avail = avail
        self.shading = shading
        self.left = left
        self.bottom = bottom
        self.top = top
        self.spaceBefore = space_before
        self.spaceAfter = space_after
        self.keepWithNext = keep_with_next
        self.pad_x = 3.0 if shading else 0.0
        self.pad_y = 2.2 if shading else 0.0
        self.left_off = (left.width + left.space) if left else 0.0

    def wrap(self, aw, ah):
        inner = aw - 2 * self.pad_x - self.left_off
        _, h = self.para.wrap(inner, ah)
        self.inner_h = h
        extra = 2 * self.pad_y
        if self.bottom:
            extra += self.bottom.space + self.bottom.width
        if self.top:
            extra += self.top.space + self.top.width
        self.width = aw
        self.height = h + extra
        return aw, self.height

    def draw(self):
        c = self.canv
        y0 = 0.0
        if self.bottom:
            c.setStrokeColor(colors.HexColor(self.bottom.color))
            c.setLineWidth(self.bottom.width)
            c.line(0, self.bottom.width / 2, self.width, self.bottom.width / 2)
            y0 = self.bottom.space + self.bottom.width
        box_h = self.inner_h + 2 * self.pad_y
        if self.shading:
            c.setFillColor(colors.HexColor(self.shading))
            c.rect(0, y0, self.width, box_h, stroke=0, fill=1)
        if self.left:
            c.setFillColor(colors.HexColor(self.left.color))
            c.rect(0, y0, self.left.width, box_h, stroke=0, fill=1)
        if self.top:
            c.setStrokeColor(colors.HexColor(self.top.color))
            c.setLineWidth(self.top.width)
            ytop = y0 + box_h + self.top.space + self.top.width / 2
            c.line(0, ytop, self.width, ytop)
        self.para.drawOn(c, self.pad_x + self.left_off, y0 + self.pad_y)

    def split(self, aw, ah):
        return []


class _Outline(Flowable):
    """Zero-size marker that adds a PDF bookmark/outline entry where it is drawn."""

    _count = 0

    def __init__(self, title: str, level: int = 0):
        super().__init__()
        self.title = title
        self.level = level
        _Outline._count += 1
        self.key = f"ris-h{_Outline._count}"
        self.width = self.height = 0

    def wrap(self, aw, ah):
        return 0, 0

    def draw(self):
        self.canv.bookmarkPage(self.key)
        self.canv.addOutlineEntry(self.title, self.key, level=self.level, closed=False)


def _make_canvas_class(layout: LayoutDocument):
    ft = layout.footer
    page = layout.page

    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            # The canvas preamble declares an initial font on every page; use an embedded one.
            if not kwargs.get("initialFontName"):
                kwargs["initialFontName"] = fonts.font_name(ft.font)
            if not kwargs.get("initialFontSize"):
                kwargs["initialFontSize"] = ft.size
            super().__init__(*args, **kwargs)
            self._saved_page_states: list[dict] = []

        def showPage(self):  # noqa: N802 - ReportLab API
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self._draw_footer(total)
                super().showPage()
            super().save()

        def _draw_footer(self, total: int) -> None:
            if ft.page_numbers == "none" and not ft.left_text and not ft.note:
                return
            fname = fonts.font_name(ft.font)
            self.saveState()
            self.setFont(fname, ft.size)
            self.setFillColor(colors.HexColor(ft.color))
            y = max(page.margin_bottom * 0.45, 14)
            if ft.left_text:
                self.drawString(page.margin_left, y, _fallback_plain(ft.left_text, fname))
            n = self._pageNumber
            label = {"page_x_of_y": f"Page {n} of {total}", "x_of_y": f"{n} / {total}", "x": f"{n}"}.get(
                ft.page_numbers, "")
            if label:
                self.drawRightString(page.width - page.margin_right, y, label)
            if ft.note:
                self.setFont(fonts.font_name(ft.font, italic=True), ft.size)
                self.drawCentredString(page.width / 2, y - ft.size - 2, _fallback_plain(ft.note, fname))
            self.restoreState()

    return NumberedCanvas


def _empty() -> Flowable:
    """Zero-size placeholder for empty table cells (avoids ReportLab's default Helvetica)."""
    return RLSpacer(0.1, 0.1)


def _fallback_plain(text: str, font_name: str) -> str:
    return "".join(ch if fonts.supports(font_name, ch) else "?" for ch in text)


class _DocTemplate(BaseDocTemplate):
    def __init__(self, filename, layout: LayoutDocument, **kw):
        super().__init__(filename, **kw)
        pg = layout.page
        frame = Frame(pg.margin_left, pg.margin_bottom, pg.text_width, pg.text_height, id="main",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate(id="page", frames=[frame])])


class PdfRenderer:
    def __init__(self, layout: LayoutDocument) -> None:
        fonts.register_fonts()
        self.layout = layout
        self.missing: set[str] = set()
        self._style_cache: dict[tuple, ParagraphStyle] = {}

    # ------------------------------------------------------------------ text markup
    def _markup(self, runs: list[Run], ps: ParaStyle) -> str:
        out: list[str] = []
        for r in runs:
            if not r.text:
                continue
            bold = ps.bold or r.bold
            italic = ps.italic or r.italic
            primary = fonts.font_name(ps.font, bold, italic)
            size = r.size or ps.size
            small_caps = r.small_caps or ps.small_caps
            pieces = self._segments(r.text, primary, bold, italic, size, small_caps)
            inner = "".join(pieces)
            color = r.color or (self.layout.link_color if r.link else None)
            if color:
                inner = f'<font color="{color}">{inner}</font>'
            if r.underline:
                inner = f"<u>{inner}</u>"
            if r.link:
                inner = f'<a href="{escape(r.link, {chr(34): "&quot;"})}">{inner}</a>'
            out.append(inner)
        return "".join(out)

    def _segments(self, text: str, primary: str, bold: bool, italic: bool, size: float, small_caps: bool) -> list[str]:
        fallback = fonts.fallback_name(bold, italic)
        segs: list[str] = []
        cur_font = None
        cur_size = None
        buf: list[str] = []

        def flush():
            if buf:
                s = escape("".join(buf)).replace("\n", "<br/>")
                segs.append(f'<font name="{cur_font}" size="{cur_size:.2f}">{s}</font>')
                buf.clear()

        for ch in text:
            if ch == "\t":
                ch = " "
            out_ch = ch
            ch_size = size
            if small_caps and ch.isalpha() and ch.islower():
                out_ch = ch.upper()
                ch_size = round(size * 0.8, 2)
            font = primary
            if not fonts.supports(primary, out_ch):
                if fonts.supports(fallback, out_ch):
                    font = fallback
                else:
                    self.missing.add(out_ch)
            if font != cur_font or ch_size != cur_size:
                flush()
                cur_font, cur_size = font, ch_size
            buf.append(out_ch)
        flush()
        return segs

    def _pstyle(self, ps: ParaStyle, *, left_indent: float | None = None, align: str | None = None,
                space_before: float | None = None, space_after: float | None = None,
                keep: bool | None = None, first_line: float | None = None) -> ParagraphStyle:
        key = (ps.name, left_indent, align, space_before, space_after, keep, first_line)
        st = self._style_cache.get(key)
        if st is not None:
            return st
        fam = fonts.family_for(ps.font)
        leading = round(ps.size * fam.line_factor * ps.line_spacing, 2)
        st = ParagraphStyle(
            name=f"{ps.name}-{len(self._style_cache)}",
            fontName=fonts.font_name(ps.font, ps.bold, ps.italic),
            fontSize=ps.size,
            leading=leading,
            textColor=colors.HexColor(ps.color),
            alignment=_ALIGN.get(align or ps.align, TA_LEFT),
            spaceBefore=ps.space_before if space_before is None else space_before,
            spaceAfter=ps.space_after if space_after is None else space_after,
            leftIndent=ps.left_indent if left_indent is None else left_indent,
            firstLineIndent=(0 if first_line is None else first_line),
            keepWithNext=ps.keep_with_next if keep is None else keep,
            allowWidows=0,
            allowOrphans=0,
            splitLongWords=1,
            bulletFontName=fonts.font_name(ps.font),
            bulletFontSize=ps.size,
        )
        self._style_cache[key] = st
        return st

    def _tstyle(self, cmds: list) -> TableStyle:
        """TableStyle with an embedded font set for every cell (ReportLab defaults to Helvetica)."""
        base = fonts.font_name(self.layout.styles["Normal"].font)
        return TableStyle([("FONTNAME", (0, 0), (-1, -1), base), *cmds])

    # ------------------------------------------------------------------ blocks
    def _para(self, p: Para, avail: float) -> list[Flowable]:
        ps = self.layout.styles.get(p.style, self.layout.styles["Normal"])
        flow: list[Flowable] = []
        if p.heading_level:
            flow.append(_Outline("".join(r.text for r in p.runs).strip() or "Section", 0))
        sb = p.space_before
        sa = p.space_after
        keep = p.keep_with_next

        if p.gutter_runs is not None:
            base = (p.left_indent if p.left_indent is not None else ps.left_indent) - p.gutter_width
            base = max(base, 0.0)
            g_style = self._pstyle(ps, left_indent=0, space_before=0, space_after=0, keep=False)
            m_style = self._pstyle(ps, left_indent=0, space_before=0, space_after=0, keep=False)
            gutter = Paragraph(self._markup(p.gutter_runs, ps) or "&nbsp;", g_style)
            main = Paragraph(self._markup(p.runs, ps) or "&nbsp;", m_style)
            widths = ([base] if base > 0.5 else []) + [p.gutter_width, max(avail - base - p.gutter_width, 20)]
            row = ([_empty()] if base > 0.5 else []) + [gutter, main]
            t = Table([row], colWidths=widths, splitInRow=1, hAlign="LEFT")
            t.setStyle(self._tstyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
            t.spaceBefore = ps.space_before if sb is None else sb
            t.spaceAfter = ps.space_after if sa is None else sa
            t.keepWithNext = ps.keep_with_next if keep is None else keep
            flow.append(t)
            return flow

        if p.right_runs:
            left_indent = p.left_indent if p.left_indent is not None else ps.left_indent
            l_style = self._pstyle(ps, left_indent=0, space_before=0, space_after=0, keep=False, align="left")
            r_style = self._pstyle(ps, left_indent=0, space_before=0, space_after=0, keep=False, align="right")
            right_text = "".join(r.text for r in p.right_runs)
            from reportlab.pdfbase.pdfmetrics import stringWidth

            rw = stringWidth(right_text, fonts.font_name(ps.font, ps.bold), ps.size) + 6
            rw = min(max(rw, 20), avail * 0.45)
            left = Paragraph(self._markup(p.runs, ps) or "&nbsp;", l_style)
            right = Paragraph(self._markup(p.right_runs, ps) or "&nbsp;", r_style)
            widths = ([left_indent] if left_indent > 0.5 else []) + [max(avail - left_indent - rw, 20), rw]
            row = ([_empty()] if left_indent > 0.5 else []) + [left, right]
            t = Table([row], colWidths=widths, splitInRow=1, hAlign="LEFT")
            t.setStyle(self._tstyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
            t.spaceBefore = ps.space_before if sb is None else sb
            t.spaceAfter = ps.space_after if sa is None else sa
            t.keepWithNext = ps.keep_with_next if keep is None else keep
            flow.append(t)
            return flow

        if p.bullet:
            indent = p.left_indent if p.left_indent is not None else self.layout.bullet_indent * (p.bullet_level + 1)
            st = self._pstyle(ps, left_indent=indent, space_before=sb, space_after=sa, keep=keep, align=p.align)
            st.bulletIndent = max(indent - self.layout.bullet_indent, 0)
            glyph = p.bullet if p.bullet_level == 0 else ("–" if p.bullet_level == 1 else "·")
            if not fonts.supports(st.bulletFontName, glyph):
                st.bulletFontName = fonts.fallback_name()
            flow.append(Paragraph(self._markup(p.runs, ps) or "&nbsp;", st, bulletText=glyph))
            return flow

        decorated = bool(p.border_bottom or p.border_left or p.border_top or p.shading)
        left_indent = p.left_indent if p.left_indent is not None else None
        st = self._pstyle(ps, left_indent=left_indent, align=p.align,
                          space_before=0 if decorated else sb, space_after=0 if decorated else sa,
                          keep=False if decorated else keep)
        para = Paragraph(self._markup(p.runs, ps) or "&nbsp;", st)
        if decorated:
            flow.append(_Decorated(
                para, avail, shading=p.shading, left=p.border_left, bottom=p.border_bottom, top=p.border_top,
                space_before=ps.space_before if sb is None else sb, space_after=ps.space_after if sa is None else sa,
                keep_with_next=ps.keep_with_next if keep is None else keep,
            ))
        else:
            flow.append(para)
        return flow

    def _blocks(self, blocks: list, avail: float) -> list[Flowable]:
        out: list[Flowable] = []
        for b in blocks:
            out.extend(self._block(b, avail))
        return out

    def _block(self, b, avail: float) -> list[Flowable]:
        if isinstance(b, Para):
            return self._para(b, avail)
        if isinstance(b, Spacer):
            return [RLSpacer(1, b.height)] if b.height > 0 else []
        if isinstance(b, Rule):
            return [HRFlowable(width="100%", thickness=b.width, color=colors.HexColor(b.color),
                               spaceBefore=b.space_before, spaceAfter=b.space_after, lineCap="butt")]
        if isinstance(b, PageBreakBlock):
            return [PageBreak()]
        if isinstance(b, ImageBlock):
            try:
                ir = ImageReader(b.source())
                iw, ih = ir.getSize()
                w = min(b.width, avail)
                h = w * ih / iw if iw else w
                img = Image(b.source(), width=w, height=h)
                img.hAlign = {"left": "LEFT", "center": "CENTER"}.get(b.align, "RIGHT")
                out: list[Flowable] = [img]
                if b.space_after:
                    out.append(RLSpacer(1, b.space_after))
                return out
            except Exception:
                self.layout_warning("An image could not be read and was left out of the PDF."
                                    if b.data is not None else
                                    "The photograph could not be read and was left out of the PDF.")
                return []
        if isinstance(b, TableBlock):
            widths = [avail * f for f in b.col_widths]
            data = []
            for row in b.rows:
                data.append([self._blocks(cell.blocks, widths[i] - 2 * b.padding) or [_empty()]
                             for i, cell in enumerate(row)])
            cmds = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), b.padding),
                    ("RIGHTPADDING", (0, 0), (-1, -1), b.padding), ("TOPPADDING", (0, 0), (-1, -1), b.padding * 0.6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), b.padding * 0.6)]
            col = colors.HexColor(b.border_color)
            if b.borders == "grid":
                cmds.append(("GRID", (0, 0), (-1, -1), b.border_width, col))
            elif b.borders == "rows":
                cmds.append(("LINEBELOW", (0, 0), (-1, -1), b.border_width, col))
            elif b.borders == "header_rule" and b.header_rows:
                cmds.append(("LINEBELOW", (0, b.header_rows - 1), (-1, b.header_rows - 1), b.border_width, col))
            if b.header_fill and b.header_rows:
                cmds.append(("BACKGROUND", (0, 0), (-1, b.header_rows - 1), colors.HexColor(b.header_fill)))
            for ri, row in enumerate(b.rows):
                for ci, cell in enumerate(row):
                    if cell.fill:
                        cmds.append(("BACKGROUND", (ci, ri), (ci, ri), colors.HexColor(cell.fill)))
            t = Table(data, colWidths=widths, repeatRows=b.header_rows, splitInRow=1, hAlign="LEFT")
            t.setStyle(self._tstyle(cmds))
            return [t]
        if isinstance(b, ColumnsBlock):
            lw = avail * b.left_frac
            rw = avail - lw
            lpad = b.padding if b.left_fill else 0.0
            rpad = b.padding if b.right_fill else 0.0
            left = self._blocks(b.left, lw - 2 * lpad - b.gap / 2) or [_empty()]
            right = self._blocks(b.right, rw - 2 * rpad - b.gap / 2) or [_empty()]
            t = Table([[left, right]], colWidths=[lw, rw], splitInRow=1, hAlign="LEFT")
            cmds = [("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (0, 0), lpad), ("RIGHTPADDING", (0, 0), (0, 0), lpad + b.gap / 2),
                    ("LEFTPADDING", (1, 0), (1, 0), rpad + b.gap / 2), ("RIGHTPADDING", (1, 0), (1, 0), rpad),
                    ("TOPPADDING", (0, 0), (-1, -1), lpad or rpad), ("BOTTOMPADDING", (0, 0), (-1, -1), lpad or rpad)]
            if b.left_fill:
                cmds.append(("BACKGROUND", (0, 0), (0, 0), colors.HexColor(b.left_fill)))
            if b.right_fill:
                cmds.append(("BACKGROUND", (1, 0), (1, 0), colors.HexColor(b.right_fill)))
            t.setStyle(self._tstyle(cmds))
            return [t]
        if isinstance(b, BannerBlock):
            inner = self._blocks(b.blocks, avail - 2 * b.padding) or [_empty()]
            t = Table([[inner]], colWidths=[avail], hAlign="LEFT")
            t.setStyle(self._tstyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(b.fill)),
                                   ("LEFTPADDING", (0, 0), (-1, -1), b.padding),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), b.padding),
                                   ("TOPPADDING", (0, 0), (-1, -1), b.padding * 0.8),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), b.padding * 0.8),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            return [t]
        if isinstance(b, LabeledSection):
            lw = b.label_width
            rw = avail - lw
            label = self._para(b.label, lw - b.gap)
            content = self._blocks(b.blocks, rw) or [_empty()]
            t = Table([[label, content]], colWidths=[lw, rw], splitInRow=1, hAlign="LEFT")
            t.setStyle(self._tstyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (0, 0), b.gap), ("RIGHTPADDING", (1, 0), (1, 0), 0),
                                   ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
            return [t]
        return []

    _warnings: list[str]

    def layout_warning(self, msg: str) -> None:
        if not hasattr(self, "_warnings"):
            self._warnings = []
        self._warnings.append(msg)

    # ------------------------------------------------------------------ main
    def _build(self, target) -> PdfRenderResult:
        lay = self.layout
        md = lay.metadata
        doc = _DocTemplate(
            target, lay, pagesize=(lay.page.width, lay.page.height),
            leftMargin=lay.page.margin_left, rightMargin=lay.page.margin_right,
            topMargin=lay.page.margin_top, bottomMargin=lay.page.margin_bottom,
            title=md.get("title", ""), author=md.get("author", ""), subject=md.get("subject", ""),
            keywords=md.get("keywords", ""), creator=md.get("creator", f"Resume Intelligence Studio {__version__}"),
            producer=f"Resume Intelligence Studio {__version__} (ReportLab)", lang=lay.lang,
        )
        story = self._blocks(lay.blocks, lay.page.text_width)
        doc.build(story, canvasmaker=_make_canvas_class(lay))
        warnings = list(getattr(self, "_warnings", []))
        if self.missing:
            warnings.append("Some characters are not available in the embedded fonts: "
                            + " ".join(sorted(self.missing)))
        return PdfRenderResult(page_count=doc.page, missing_glyphs=set(self.missing), warnings=warnings)

    def render(self, path: Path) -> PdfRenderResult:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return self._build(str(path))

    def render_bytes(self) -> tuple[bytes, PdfRenderResult]:
        buf = io.BytesIO()
        res = self._build(buf)
        return buf.getvalue(), res


def render_pdf(layout: LayoutDocument, path: Path) -> PdfRenderResult:
    return PdfRenderer(layout).render(path)
