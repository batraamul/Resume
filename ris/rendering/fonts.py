"""Font registration for the built-in PDF engine.

Templates name Microsoft-compatible fonts (Calibri, Cambria, Arial, Times New
Roman) so Word and LibreOffice render the DOCX faithfully. The built-in PDF
engine embeds bundled open fonts with identical metrics:

* Calibri → Carlito, Cambria → Caladea (SIL OFL)
* Arial → Liberation Sans, Times New Roman → Liberation Serif (SIL OFL)
* DejaVu Sans is the per-glyph fallback for characters a primary font lacks.

Line-height factors were measured from each font's hhea table, matching how
Word and LibreOffice compute single line spacing.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from functools import lru_cache

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from ris.resources import fonts_dir


@dataclass(frozen=True)
class Family:
    key: str
    regular: str
    bold: str
    italic: str
    bold_italic: str
    line_factor: float


_FILES = {
    "Carlito": ("Carlito-Regular.ttf", "Carlito-Bold.ttf", "Carlito-Italic.ttf", "Carlito-BoldItalic.ttf", 1.2207),
    "Caladea": ("Caladea-Regular.ttf", "Caladea-Bold.ttf", "Caladea-Italic.ttf", "Caladea-BoldItalic.ttf", 1.172),
    "LiberationSans": ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf", "LiberationSans-Italic.ttf",
                       "LiberationSans-BoldItalic.ttf", 1.1499),
    "LiberationSerif": ("LiberationSerif-Regular.ttf", "LiberationSerif-Bold.ttf", "LiberationSerif-Italic.ttf",
                        "LiberationSerif-BoldItalic.ttf", 1.1499),
    "DejaVuSans": ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf",
                   1.1641),
}

LOGICAL_TO_FAMILY = {
    "Calibri": "Carlito",
    "Cambria": "Caladea",
    "Arial": "LiberationSans",
    "Times New Roman": "LiberationSerif",
}
FALLBACK_FAMILY = "DejaVuSans"

_lock = threading.Lock()
_registered: dict[str, Family] = {}
_ttfonts: dict[str, TTFont] = {}


def register_fonts() -> dict[str, Family]:
    """Register bundled fonts with ReportLab (idempotent, thread-safe)."""
    with _lock:
        if _registered:
            return _registered
        base = fonts_dir()
        for fam, (r, b, i, bi, factor) in _FILES.items():
            names = []
            for suffix, fname in (("", r), ("-Bold", b), ("-Italic", i), ("-BoldItalic", bi)):
                font_name = f"RIS-{fam}{suffix}"
                path = base / fname
                font = TTFont(font_name, str(path))
                pdfmetrics.registerFont(font)
                _ttfonts[font_name] = font
                names.append(font_name)
            pdfmetrics.registerFontFamily(f"RIS-{fam}", normal=names[0], bold=names[1], italic=names[2],
                                          boldItalic=names[3])
            _registered[fam] = Family(fam, names[0], names[1], names[2], names[3], factor)
        return _registered


def family_for(logical: str) -> Family:
    fams = register_fonts()
    return fams[LOGICAL_TO_FAMILY.get(logical, FALLBACK_FAMILY)]


def font_name(logical: str, bold: bool = False, italic: bool = False) -> str:
    fam = family_for(logical)
    if bold and italic:
        return fam.bold_italic
    if bold:
        return fam.bold
    if italic:
        return fam.italic
    return fam.regular


def fallback_name(bold: bool = False, italic: bool = False) -> str:
    fam = register_fonts()[FALLBACK_FAMILY]
    return fam.bold_italic if (bold and italic) else fam.bold if bold else fam.italic if italic else fam.regular


@lru_cache(maxsize=64)
def _cmap(font_name_: str) -> frozenset[int]:
    register_fonts()
    font = _ttfonts[font_name_]
    return frozenset(font.face.charToGlyph.keys())


def supports(font_name_: str, ch: str) -> bool:
    cp = ord(ch)
    if cp < 32 or ch in "\n\t":
        return True
    return cp in _cmap(font_name_)
