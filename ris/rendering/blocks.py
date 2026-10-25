"""Renderer-neutral layout blocks.

The layout planner produces these; the DOCX and PDF renderers implement each
block type, so both formats share structure and content.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MM = 72.0 / 25.4  # points per millimetre

PAGE_SIZES_PT: dict[str, tuple[float, float]] = {
    "A4": (210 * MM, 297 * MM),
    "Letter": (8.5 * 72.0, 11 * 72.0),
}


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    color: str | None = None
    link: str | None = None
    size: float | None = None
    small_caps: bool = False
    underline: bool = False
    font: str | None = None  # explicit font (e.g. a symbol font for contact icons)


@dataclass
class Border:
    color: str
    width: float  # points
    space: float = 1.0  # points between text and border


@dataclass
class ParaStyle:
    name: str
    font: str
    size: float
    bold: bool = False
    italic: bool = False
    color: str = "#000000"
    align: str = "left"
    space_before: float = 0.0
    space_after: float = 0.0
    line_spacing: float = 1.0
    left_indent: float = 0.0
    first_line_indent: float = 0.0
    keep_with_next: bool = False
    letter_spacing: float = 0.0
    small_caps: bool = False
    docx_base: str | None = None  # Word built-in style to configure ("Title", "Heading 1", ...)
    outline_level: int | None = None


@dataclass
class Para:
    style: str
    runs: list[Run] = field(default_factory=list)
    right_runs: list[Run] | None = None
    gutter_runs: list[Run] | None = None
    gutter_width: float = 0.0
    bullet: str | None = None
    bullet_level: int = 0
    align: str | None = None
    keep_with_next: bool | None = None
    space_before: float | None = None
    space_after: float | None = None
    left_indent: float | None = None
    border_bottom: Border | None = None
    border_top: Border | None = None
    border_left: Border | None = None
    shading: str | None = None
    heading_level: int | None = None

    def plain_text(self) -> str:
        parts = []
        if self.gutter_runs:
            parts.append("".join(r.text for r in self.gutter_runs))
        parts.append("".join(r.text for r in self.runs))
        if self.right_runs:
            parts.append("".join(r.text for r in self.right_runs))
        return " ".join(p for p in parts if p)


@dataclass
class Cell:
    blocks: list = field(default_factory=list)
    fill: str | None = None


@dataclass
class TableBlock:
    rows: list[list[Cell]]
    col_widths: list[float]  # fractions of the available width
    header_rows: int = 0
    borders: str = "none"  # none | grid | rows | header_rule
    border_color: str = "#000000"
    border_width: float = 0.5
    header_fill: str | None = None
    padding: float = 3.0


@dataclass
class Spacer:
    height: float


@dataclass
class Rule:
    color: str
    width: float = 0.75
    space_before: float = 0.0
    space_after: float = 3.0
    double: bool = False


@dataclass
class ColumnsBlock:
    left: list
    right: list
    left_frac: float
    gap: float
    left_fill: str | None = None
    right_fill: str | None = None
    padding: float = 6.0


@dataclass
class BannerBlock:
    blocks: list
    fill: str
    padding: float = 9.0


@dataclass
class LabeledSection:
    label: Para
    blocks: list
    label_width: float
    gap: float = 8.0


@dataclass
class ImageBlock:
    path: str
    width: float
    align: str = "right"
    data: bytes | None = None      # in-memory PNG (charts); takes precedence over ``path``
    alt: str = ""                  # alternative text (Word alt text; tagged PDFs via LibreOffice)
    space_after: float = 0.0
    keep_with_next: bool = False   # keep a chart with its legend; never chain small images (bars)

    def source(self):
        import io

        return io.BytesIO(self.data) if self.data is not None else self.path


@dataclass
class PageBreakBlock:
    pass


@dataclass
class PageSetup:
    width: float
    height: float
    margin_top: float
    margin_bottom: float
    margin_left: float
    margin_right: float

    @property
    def text_width(self) -> float:
        return self.width - self.margin_left - self.margin_right

    @property
    def text_height(self) -> float:
        return self.height - self.margin_top - self.margin_bottom


@dataclass
class FooterLayout:
    left_text: str = ""
    page_numbers: str = "none"  # none | page_x_of_y | x_of_y | x
    note: str = ""
    font: str = "Calibri"
    size: float = 8.5
    color: str = "#555555"


@dataclass
class LayoutDocument:
    page: PageSetup
    styles: dict[str, ParaStyle]
    blocks: list
    footer: FooterLayout
    metadata: dict[str, str] = field(default_factory=dict)
    link_color: str = "#1F3A5F"
    bullet_indent: float = 12.0
    template_id: str = ""
    lang: str = "en-IN"

    def iter_paras(self):
        """Yield every Para in document order (including nested containers)."""
        def walk(blocks):
            for b in blocks:
                if isinstance(b, Para):
                    yield b
                elif isinstance(b, TableBlock):
                    for row in b.rows:
                        for cell in row:
                            yield from walk(cell.blocks)
                elif isinstance(b, ColumnsBlock):
                    yield from walk(b.left)
                    yield from walk(b.right)
                elif isinstance(b, BannerBlock):
                    yield from walk(b.blocks)
                elif isinstance(b, LabeledSection):
                    yield b.label
                    yield from walk(b.blocks)
        yield from walk(self.blocks)
