"""Read back exported files for validation (text, styles, links, fonts, positions)."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass
class DocxInfo:
    body_text: str
    footer_text: str
    paragraphs: list[str]
    heading_paragraphs: list[str]
    styles_used: set[str]
    hyperlinks: list[str]
    bullet_paragraphs: int
    tables: int
    has_page_field: bool


@dataclass
class PdfInfo:
    page_count: int
    page_texts: list[str]
    links: list[str]
    unembedded_fonts: list[str]
    out_of_bounds: list[str]
    metadata: dict[str, str] = field(default_factory=dict)
    page_sizes: list[tuple[float, float]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.page_texts)


def _para_text(p_el) -> str:
    parts: list[str] = []
    for el in p_el.iter():
        if el.tag == W_NS + "t":
            parts.append(el.text or "")
        elif el.tag == W_NS + "tab":
            parts.append("\t")
        elif el.tag in (W_NS + "br", W_NS + "cr"):
            parts.append("\n")
    return "".join(parts)


def read_docx(path: Path) -> DocxInfo:
    from docx import Document

    path = Path(path)
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        for required in ("[Content_Types].xml", "word/document.xml"):
            if required not in names:
                raise ValueError(f"Missing {required}")
    d = Document(str(path))
    body = d.element.body
    paras: list[str] = []
    headings: list[str] = []
    styles_used: set[str] = set()
    bullets = 0
    style_by_id = {s.style_id: s.name for s in d.styles}
    for p in body.iter(W_NS + "p"):
        text = _para_text(p)
        paras.append(text)
        ppr = p.find(W_NS + "pPr")
        if ppr is not None:
            ps = ppr.find(W_NS + "pStyle")
            if ps is not None:
                name = style_by_id.get(ps.get(W_NS + "val"), ps.get(W_NS + "val"))
                styles_used.add(name)
                if name and (name.startswith("Heading") or name == "Title"):
                    headings.append(text)
            if ppr.find(W_NS + "numPr") is not None:
                bullets += 1
    footer_parts: list[str] = []
    has_page_field = False
    for sec in d.sections:
        for part in (sec.footer, sec.header):
            for p in part._element.iter(W_NS + "p"):
                footer_parts.append(_para_text(p))
            for it in part._element.iter(W_NS + "instrText"):
                if "PAGE" in (it.text or ""):
                    has_page_field = True
    links = [r.target_ref for r in d.part.rels.values() if r.reltype.endswith("/hyperlink")]
    tables = len(list(body.iter(W_NS + "tbl")))
    return DocxInfo(
        body_text="\n".join(paras), footer_text="\n".join(footer_parts), paragraphs=paras,
        heading_paragraphs=headings, styles_used=styles_used, hyperlinks=links, bullet_paragraphs=bullets,
        tables=tables, has_page_field=has_page_field,
    )


def _resolve(obj):
    try:
        return obj.get_object()
    except AttributeError:
        return obj


def _font_embedded(font) -> bool:
    font = _resolve(font)
    subtype = font.get("/Subtype")
    if subtype == "/Type0":
        desc = font.get("/DescendantFonts")
        if desc:
            return all(_font_embedded(d) for d in _resolve(desc))
        return False
    if subtype == "/Type3":
        return True
    fd = font.get("/FontDescriptor")
    if fd is None:
        return False
    fd = _resolve(fd)
    return any(k in fd for k in ("/FontFile", "/FontFile2", "/FontFile3"))


def read_pdf(path: Path) -> PdfInfo:
    from pypdf import PdfReader

    path = Path(path)
    with open(path, "rb") as fh:
        head = fh.read(8)
        fh.seek(max(0, path.stat().st_size - 2048))
        tail = fh.read()
    if not head.startswith(b"%PDF-"):
        raise ValueError("Not a PDF file (missing %PDF header)")
    if b"%%EOF" not in tail:
        raise ValueError("PDF is truncated (no %%EOF marker)")
    reader = PdfReader(str(path))
    texts: list[str] = []
    links: list[str] = []
    unembedded: set[str] = set()
    oob: list[str] = []
    sizes: list[tuple[float, float]] = []
    for i, page in enumerate(reader.pages):
        box = page.mediabox
        w, h = float(box.width), float(box.height)
        sizes.append((w, h))
        positions: list[tuple[float, float, str]] = []

        def visitor(text, cm, tm, font_dict, font_size, _positions=positions):
            if text and text.strip():
                x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
                y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                _positions.append((x, y, text.strip()[:30]))

        texts.append(page.extract_text(visitor_text=visitor) or "")
        for x, y, t in positions:
            if x < -2 or x > w + 2 or y < -2 or y > h + 2:
                oob.append(f"page {i + 1}: '{t}' at ({x:.0f}, {y:.0f})")
        res = page.get("/Resources")
        if res is not None:
            res = _resolve(res)
            fonts = res.get("/Font")
            if fonts is not None:
                for name, font in _resolve(fonts).items():
                    f = _resolve(font)
                    if not _font_embedded(f):
                        unembedded.add(str(f.get("/BaseFont", name)))
        annots = page.get("/Annots")
        if annots:
            for a in _resolve(annots):
                a = _resolve(a)
                if a.get("/Subtype") == "/Link":
                    act = a.get("/A")
                    if act is not None:
                        uri = _resolve(act).get("/URI")
                        if uri:
                            links.append(str(uri))
    md = {}
    try:
        meta = reader.metadata or {}
        md = {k.lstrip("/"): str(v) for k, v in meta.items()}
    except Exception:  # pragma: no cover - malformed metadata is not fatal
        md = {}
    return PdfInfo(page_count=len(reader.pages), page_texts=texts, links=links, unembedded_fonts=sorted(unembedded),
                   out_of_bounds=oob, metadata=md, page_sizes=sizes)


_TOKEN = re.compile(r"[\w@+#]+(?:[.'/-][\w@+#]+)*", re.UNICODE)


def tokens(text: str) -> list[str]:
    from ris.util import normalize_for_compare

    return _TOKEN.findall(normalize_for_compare(text))
