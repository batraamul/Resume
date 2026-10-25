"""Diary-inspired visual theme: colour tokens, contrast checks, fonts and the Qt style sheet.

Light theme: maroon index panel (#701C35), ivory pages (#FFF3DF), cream cards (#FFFAF0)
and navy ink (#192B4B). The dark theme keeps the same structure with a deep-navy page,
lighter maroon accents and ivory ink. Every text/background pair used by the style sheet
is listed in ``TEXT_PAIRS`` and verified against WCAG 2.1 AA by the test suite.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields, replace

from ris.resources import fonts_dir


@dataclass(frozen=True)
class Palette:
    name: str
    page: str           # window / page background
    card: str           # cards, inputs
    card_alt: str       # alternating rows, subtle fills
    ink: str            # primary text
    ink_muted: str      # secondary text
    heading: str        # headings
    rule: str           # borders, ruled lines
    rule_strong: str
    accent: str         # primary buttons, links, focus
    accent_ink: str     # text on accent
    accent_hover: str
    nav_bg: str
    nav_ink: str
    nav_muted: str
    nav_active_bg: str
    nav_active_ink: str
    ribbon: str         # decorative ribbon (non-text)
    selection: str
    selection_ink: str
    ok_bg: str
    ok_ink: str
    warn_bg: str
    warn_ink: str
    bad_bg: str
    bad_ink: str
    info_bg: str
    info_ink: str
    sample_bg: str
    sample_ink: str


LIGHT = Palette(
    name="light",
    page="#FFF3DF", card="#FFFAF0", card_alt="#FBEBD2", ink="#192B4B", ink_muted="#4A5163", heading="#701C35",
    rule="#E2CFAF", rule_strong="#C9AE85",
    accent="#701C35", accent_ink="#FFF3DF", accent_hover="#5A1529",
    nav_bg="#701C35", nav_ink="#FFF3DF", nav_muted="#E9C9B5", nav_active_bg="#FFF3DF", nav_active_ink="#701C35",
    ribbon="#C8963E", selection="#F2D9BD", selection_ink="#192B4B",
    ok_bg="#E3F0DF", ok_ink="#1F5130", warn_bg="#FBEBC8", warn_ink="#6B4600", bad_bg="#F8DEDA", bad_ink="#8A1B1B",
    info_bg="#E0E8F3", info_ink="#192B4B", sample_bg="#192B4B", sample_ink="#FFF3DF",
)

DARK = Palette(
    name="dark",
    page="#131B2A", card="#1B2537", card_alt="#202C41", ink="#F4EBDD", ink_muted="#BDB5A8", heading="#F0B8C8",
    rule="#33405A", rule_strong="#4A5878",
    accent="#B8466A", accent_ink="#FFFFFF", accent_hover="#9E3A5A",
    nav_bg="#3B0F1E", nav_ink="#F4EBDD", nav_muted="#D9B8C2", nav_active_bg="#F4EBDD", nav_active_ink="#5A1529",
    ribbon="#C8963E", selection="#3A4A68", selection_ink="#FFFFFF",
    ok_bg="#1E3A2A", ok_ink="#BFE5C8", warn_bg="#3D3015", warn_ink="#F3D58F", bad_bg="#45201F", bad_ink="#F7C1BB",
    info_bg="#1F2F4A", info_ink="#D3E0F5", sample_bg="#F4EBDD", sample_ink="#192B4B",
)

PALETTES = {"light": LIGHT, "dark": DARK}


def _variant(base: Palette, name: str, **changes: str) -> Palette:
    return replace(base, name=name, **changes)


#: Colour presets. Each has a light and a dark palette; all pairs meet WCAG 2.1 AA (checked by tests).
PRESETS: dict[str, tuple[str, Palette, Palette]] = {
    "diary": ("Diary maroon (default)", LIGHT, DARK),
    "navy": ("Navy professional",
             _variant(LIGHT, "light", page="#F3F5F9", card="#FFFFFF", card_alt="#E8EDF5", ink="#16233A",
                      ink_muted="#475569", heading="#1F3A5F", rule="#D3DAE6", rule_strong="#A9B6CB", accent="#1F3A5F",
                      accent_ink="#FFFFFF", accent_hover="#162B47", nav_bg="#1F3A5F", nav_ink="#FFFFFF",
                      nav_muted="#C9D6EA", nav_active_bg="#F3F5F9", nav_active_ink="#1F3A5F", ribbon="#C8963E",
                      selection="#D6E2F3", selection_ink="#16233A", sample_bg="#16233A", sample_ink="#FFFFFF"),
             _variant(DARK, "dark", heading="#A9C7EE", accent="#4573B0", accent_hover="#3D6EA8", nav_bg="#0F1E33",
                      nav_active_ink="#1F3A5F")),
    "forest": ("Forest green",
               _variant(LIGHT, "light", page="#F4F7F2", card="#FFFFFF", card_alt="#E7EFE3", ink="#1C2B22",
                        ink_muted="#4A5A50", heading="#1E5B3F", rule="#D3E0D0", rule_strong="#A8BFA4",
                        accent="#1E5B3F", accent_ink="#FFFFFF", accent_hover="#164631", nav_bg="#1E5B3F",
                        nav_ink="#FFFFFF", nav_muted="#CFE3D6", nav_active_bg="#F4F7F2", nav_active_ink="#1E5B3F",
                        ribbon="#C8963E", selection="#D8EBDD", selection_ink="#1C2B22", sample_bg="#1C2B22",
                        sample_ink="#FFFFFF"),
               _variant(DARK, "dark", page="#121C17", card="#18251E", card_alt="#1E2D25", heading="#A8DDBF",
                        accent="#2F7D58", accent_hover="#276A4A", nav_bg="#0E2A1D", nav_active_ink="#1E5B3F",
                        rule="#2C4035", rule_strong="#44604F", selection="#2D4A3A")),
    "slate": ("Slate grey",
              _variant(LIGHT, "light", page="#F5F6F7", card="#FFFFFF", card_alt="#ECEFF1", ink="#1F2A30",
                       ink_muted="#4F5B62", heading="#37474F", rule="#D7DCDF", rule_strong="#AAB4BA", accent="#37474F",
                       accent_ink="#FFFFFF", accent_hover="#2A363C", nav_bg="#37474F", nav_ink="#FFFFFF",
                       nav_muted="#D5DEE2", nav_active_bg="#F5F6F7", nav_active_ink="#37474F", ribbon="#E0A030",
                       selection="#DCE3E7", selection_ink="#1F2A30", sample_bg="#1F2A30", sample_ink="#FFFFFF"),
              _variant(DARK, "dark", page="#15191C", card="#1C2226", card_alt="#22292E", heading="#C9D6DD",
                       accent="#56707D", accent_hover="#4A616C", nav_bg="#20282D", nav_active_ink="#37474F",
                       rule="#323C42", rule_strong="#4D5A61", selection="#37454D")),
    "plum": ("Royal plum",
             _variant(LIGHT, "light", page="#F8F4FA", card="#FFFFFF", card_alt="#EFE6F3", ink="#24182B",
                      ink_muted="#55485C", heading="#5B2A6E", rule="#E1D3E8", rule_strong="#BCA5C8", accent="#5B2A6E",
                      accent_ink="#FFFFFF", accent_hover="#47205A", nav_bg="#5B2A6E", nav_ink="#FFFFFF",
                      nav_muted="#E3CFEC", nav_active_bg="#F8F4FA", nav_active_ink="#5B2A6E", ribbon="#C8963E",
                      selection="#EADCF1", selection_ink="#24182B", sample_bg="#24182B", sample_ink="#FFFFFF"),
             _variant(DARK, "dark", heading="#E2C3F0", accent="#9654AE", accent_hover="#8A4DA3", nav_bg="#2E1538",
                      nav_active_ink="#5B2A6E")),
    "high_contrast": ("High contrast",
                      _variant(LIGHT, "light", page="#FFFFFF", card="#FFFFFF", card_alt="#F0F0F0", ink="#000000",
                               ink_muted="#2B2B2B", heading="#000000", rule="#5A5A5A", rule_strong="#000000",
                               accent="#0033A0", accent_ink="#FFFFFF", accent_hover="#00226B", nav_bg="#000000",
                               nav_ink="#FFFFFF", nav_muted="#E6E6E6", nav_active_bg="#FFD400",
                               nav_active_ink="#000000", ribbon="#FFD400", selection="#FFD400",
                               selection_ink="#000000", info_bg="#E6EEFF", info_ink="#000000",
                               sample_bg="#000000", sample_ink="#FFFFFF"),
                      _variant(DARK, "dark", page="#000000", card="#000000", card_alt="#1A1A1A", ink="#FFFFFF",
                               ink_muted="#E0E0E0", heading="#FFD400", rule="#9A9A9A", rule_strong="#FFFFFF",
                               accent="#FFD400", accent_ink="#000000", accent_hover="#E6BF00", nav_bg="#000000",
                               nav_ink="#FFFFFF", nav_muted="#E0E0E0", nav_active_bg="#FFD400",
                               nav_active_ink="#000000", ribbon="#FFD400", selection="#FFD400",
                               selection_ink="#000000", sample_bg="#FFD400", sample_ink="#000000")),
}

#: Colours a user can override, with the tokens that follow them automatically.
COLOUR_SLOTS: list[tuple[str, str]] = [
    ("accent", "Accent (buttons, links, focus)"), ("nav_bg", "Navigation panel"), ("page", "Page background"),
    ("card", "Cards and inputs"), ("ink", "Text"), ("heading", "Headings"),
]
DENSITY = {"compact": 0.7, "comfortable": 1.0, "spacious": 1.3}
NAV_STYLES = {"text": "Text only", "icons_text": "Icons and text", "icons": "Icons only (narrow)"}

#: Monochrome navigation glyphs from the bundled DejaVu Sans font (render the same on every platform).
NAV_ICONS = {
    "diary": "✎", "profile": "☺", "experience": "⚒", "education": "✍", "training": "✪", "research": "⚗",
    "skills": "✱", "projects": "⚑", "leadership": "♔", "targets": "◎", "opportunities": "✦", "interview": "☏",
    "portals": "⇄", "studio": "✐", "library": "▤", "letters": "✉", "tracker": "☑", "exports": "⇩", "sync": "☁",
    "backup": "↺", "settings": "⚙",
}


@dataclass
class Appearance:
    """User interface customisation, stored in the application configuration."""

    preset: str = "diary"
    colours: dict = field(default_factory=dict)
    ui_font: str = ""
    heading_font: str = ""
    density: str = "comfortable"
    radius: int = 5
    nav_style: str = "icons_text"
    nav_side: str = "left"
    editor_layout: str = "side_by_side"
    show_tagline: bool = True
    start_page: str = "diary"

    @classmethod
    def from_dict(cls, raw: dict | None) -> Appearance:
        raw = raw or {}
        known = {f.name for f in fields(cls)}
        a = cls(**{k: v for k, v in raw.items() if k in known})
        if a.preset not in PRESETS:
            a.preset = "diary"
        if a.density not in DENSITY:
            a.density = "comfortable"
        if a.nav_style not in NAV_STYLES:
            a.nav_style = "icons_text"
        a.nav_side = "right" if a.nav_side == "right" else "left"
        a.editor_layout = "stacked" if a.editor_layout == "stacked" else "side_by_side"
        try:
            a.radius = max(0, min(12, int(a.radius)))
        except (TypeError, ValueError):
            a.radius = 5
        a.colours = {k: v.upper() for k, v in (a.colours or {}).items()
                     if k in dict(COLOUR_SLOTS) and isinstance(v, str) and _HEX.match(v)}
        return a

    def to_dict(self) -> dict:
        return asdict(self)


_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02X}" for c in rgb)


def mix(a: str, b: str, t: float) -> str:
    """Blend colour a towards b by fraction t (0..1)."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(x + (y - x) * t for x, y in zip(ra, rb, strict=True)))


def readable_on(bg: str, preferred: str, minimum: float = 4.5) -> str:
    """The preferred text colour if it is readable on bg, otherwise black or white (whichever reads better)."""
    if contrast(preferred, bg) >= minimum:
        return preferred
    return "#000000" if contrast("#000000", bg) >= contrast("#FFFFFF", bg) else "#FFFFFF"


def palette_for(mode: str, appearance: Appearance | None = None) -> Palette:
    """Resolve the palette for 'light', 'dark' or 'system' with a preset and the user's colour overrides.

    Dependent tokens follow an override automatically (hover shades, text on the accent and the navigation
    panel) and text colours are corrected to black or white when an override would make them unreadable.
    """
    a = appearance or Appearance()
    base_mode = resolve(mode).name
    _, light, dark = PRESETS.get(a.preset, PRESETS["diary"])
    p = dark if base_mode == "dark" else light
    c = dict(a.colours or {})
    if not c:
        return p
    ch: dict[str, str] = {}
    is_dark = base_mode == "dark"
    if "page" in c:
        page_dark = luminance(c["page"]) < 0.18
        ch["page"] = c["page"]
        if "card" not in c:
            # Cards follow the page: a little lighter on dark pages, near-white on light pages.
            ch["card"] = mix(c["page"], "#FFFFFF", 0.07 if page_dark else 0.6)
        if page_dark != is_dark:
            # The page changed between light and dark: borders, selection and status colours follow.
            src = DARK if page_dark else LIGHT
            for tok in ("ok_bg", "ok_ink", "warn_bg", "warn_ink", "bad_bg", "bad_ink", "info_bg", "info_ink",
                        "selection", "selection_ink"):
                ch[tok] = getattr(src, tok)
    if "card" in c:
        ch["card"] = c["card"]
    if "page" in c or "card" in c:
        bgc = ch.get("card", p.card)
        page_dark = luminance(ch.get("page", p.page)) < 0.18
        ch["card_alt"] = mix(bgc, "#FFFFFF" if page_dark else "#000000", 0.06)
        ch["rule"] = mix(bgc, "#FFFFFF" if page_dark else "#000000", 0.18)
        ch["rule_strong"] = mix(bgc, "#FFFFFF" if page_dark else "#000000", 0.38)
    if "accent" in c:
        ch["accent"] = c["accent"]
        ch["accent_hover"] = mix(c["accent"], "#000000", 0.18)
        ch["accent_ink"] = readable_on(c["accent"], "#FFFFFF")
    if "nav_bg" in c:
        ch["nav_bg"] = c["nav_bg"]
        ch["nav_ink"] = readable_on(c["nav_bg"], p.nav_ink)
        ch["nav_muted"] = readable_on(c["nav_bg"], mix(ch["nav_ink"], c["nav_bg"], 0.25))
        ch["nav_active_ink"] = readable_on(p.nav_active_bg, c["nav_bg"])
    if "ink" in c:
        ch["ink"] = c["ink"]
        ch["ink_muted"] = mix(c["ink"], ch.get("page", p.page), 0.3)
    if "heading" in c:
        ch["heading"] = c["heading"]
    q = replace(p, **ch)
    # Keep every text colour readable after the overrides.
    fixes: dict[str, str] = {}
    for fg in ("ink", "ink_muted", "heading"):
        val = getattr(q, fg)
        worst = min((q.card, q.page), key=lambda b: contrast(val, b))
        if contrast(val, worst) < 4.5:
            fixes[fg] = readable_on(worst, val)
    return replace(q, **fixes) if fixes else q


def contrast_warnings(p: Palette) -> list[str]:
    names = {"ink": "text", "ink_muted": "secondary text", "heading": "headings", "page": "page", "card": "cards",
             "accent": "accent", "accent_ink": "button text", "nav_ink": "navigation text", "nav_bg": "navigation",
             "nav_muted": "navigation labels", "accent_hover": "accent (hover)", "card_alt": "alternate rows"}
    out = []
    for fg, bg, ratio, need in contrast_report(p):
        if ratio < need and fg in names and bg in names:
            out.append(f"{names[fg].capitalize()} on {names[bg]}: contrast {ratio}:1 (needs {need}:1)")
    return out

#: (foreground token, background token, minimum ratio). 4.5 = WCAG AA body text, 3.0 = large text / UI parts.
TEXT_PAIRS: list[tuple[str, str, float]] = [
    ("ink", "page", 4.5), ("ink", "card", 4.5), ("ink", "card_alt", 4.5),
    ("ink_muted", "page", 4.5), ("ink_muted", "card", 4.5),
    ("heading", "page", 4.5), ("heading", "card", 4.5),
    ("accent_ink", "accent", 4.5), ("accent_ink", "accent_hover", 4.5),
    ("accent", "card", 3.0), ("accent", "page", 3.0),
    ("nav_ink", "nav_bg", 4.5), ("nav_muted", "nav_bg", 4.5), ("nav_active_ink", "nav_active_bg", 4.5),
    ("selection_ink", "selection", 4.5),
    ("ok_ink", "ok_bg", 4.5), ("warn_ink", "warn_bg", 4.5), ("bad_ink", "bad_bg", 4.5), ("info_ink", "info_bg", 4.5),
    ("sample_ink", "sample_bg", 4.5),
    ("rule_strong", "card", 1.6),  # input borders (non-text, visual boundary)
]


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def contrast_report(p: Palette) -> list[tuple[str, str, float, float]]:
    d = asdict(p)
    return [(fg, bg, round(contrast(d[fg], d[bg]), 2), need) for fg, bg, need in TEXT_PAIRS]


# --------------------------------------------------------------------------- fonts

UI_FONT = "Carlito"
HEADING_FONT = "Caladea"
_fonts_loaded = False


def load_fonts() -> list[str]:
    """Register the bundled UI fonts with Qt (idempotent). Returns loaded family names."""
    global _fonts_loaded
    from PySide6.QtGui import QFontDatabase

    families: list[str] = []
    if _fonts_loaded:
        return families
    for name in ("Carlito-Regular", "Carlito-Bold", "Carlito-Italic", "Carlito-BoldItalic",
                 "Caladea-Regular", "Caladea-Bold", "Caladea-Italic", "DejaVuSans", "DejaVuSans-Bold"):
        path = fonts_dir() / f"{name}.ttf"
        if path.exists():
            fid = QFontDatabase.addApplicationFont(str(path))
            if fid >= 0:
                families.extend(QFontDatabase.applicationFontFamilies(fid))
    _fonts_loaded = True
    return families


def resolve(theme: str) -> Palette:
    if theme == "system":
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QGuiApplication

            hints = QGuiApplication.styleHints()
            if hints.colorScheme() == Qt.ColorScheme.Dark:
                return DARK
        except Exception:  # noqa: BLE001 - older Qt or no application
            pass
        return LIGHT
    return PALETTES.get(theme, LIGHT)


def stylesheet(p: Palette, scale: float = 1.0, appearance: Appearance | None = None) -> str:
    a = appearance or Appearance()
    base = round(10.5 * scale, 1)
    small = round(9.5 * scale, 1)
    h1 = round(19 * scale, 1)
    h2 = round(13.5 * scale, 1)
    ui_font = a.ui_font or UI_FONT
    heading_font = a.heading_font or HEADING_FONT
    d = DENSITY.get(a.density, 1.0)
    r = a.radius

    def px(v: float) -> int:
        return max(1, round(v * d))

    css = f"""
* {{ font-family: "{ui_font}", "{UI_FONT}", "Calibri", "Segoe UI", "Helvetica Neue", "DejaVu Sans", sans-serif;
     font-size: {base}pt; }}
QMainWindow, QDialog, #PageArea, QStackedWidget#Pages > QWidget {{ background: {p.page}; color: {p.ink}; }}
QWidget {{ color: {p.ink}; }}
QToolTip {{ background: {p.card}; color: {p.ink}; border: 1px solid {p.rule_strong}; padding: 4px; }}

/* ---------- diary index (navigation) ---------- */
#NavPanel {{ background: {p.nav_bg}; border: none; }}
#NavBrand {{ color: {p.nav_ink}; font-family: "{HEADING_FONT}", Georgia, serif; font-size: {round(15 * scale, 1)}pt;
             font-weight: bold; padding: 18px 16px 2px 18px; }}
#NavTagline {{ color: {p.nav_muted}; font-size: {small}pt; padding: 0 16px 12px 18px; }}
#NavGroup {{ color: {p.nav_muted}; font-size: {small}pt; font-weight: bold; letter-spacing: 1px;
             padding: 12px 18px 4px 18px; text-transform: uppercase; }}
QPushButton#NavItem {{ background: transparent; color: {p.nav_ink}; border: none; text-align: left;
                       padding: 7px 14px 7px 22px; border-radius: 0; font-size: {base}pt; }}
QPushButton#NavItem:hover {{ background: {p.accent_hover if p.name == 'light' else '#561A2C'}; }}
QPushButton#NavItem:checked {{ background: {p.nav_active_bg}; color: {p.nav_active_ink}; font-weight: bold;
                               border-left: 6px solid {p.ribbon}; padding-left: 16px;
                               border-top-left-radius: 0; border-bottom-left-radius: 0; }}
QPushButton#NavItem:focus {{ outline: none; border-left: 6px solid {p.ribbon}; padding-left: 16px; }}

/* ---------- top bar ---------- */
#TopBar {{ background: {p.card}; border-bottom: 1px solid {p.rule}; }}
#TopBar QLabel {{ color: {p.ink_muted}; }}
#SampleBanner {{ background: {p.sample_bg}; color: {p.sample_ink}; font-weight: bold; padding: 5px 12px; }}

/* ---------- page headers ---------- */
#PageTitle {{ font-family: "{HEADING_FONT}", Georgia, serif; font-size: {h1}pt; color: {p.heading}; font-weight: bold; }}
#PageSubtitle {{ color: {p.ink_muted}; }}
#SectionTitle {{ font-family: "{HEADING_FONT}", Georgia, serif; font-size: {h2}pt; color: {p.heading}; font-weight: bold; }}
#Muted {{ color: {p.ink_muted}; }}
#Rule {{ background: {p.rule}; max-height: 1px; min-height: 1px; }}

/* ---------- cards ---------- */
#Card {{ background: {p.card}; border: 1px solid {p.rule}; border-radius: 6px; }}
#Card[accent="true"] {{ border-left: 5px solid {p.ribbon}; }}
#StatValue {{ font-family: "{HEADING_FONT}", Georgia, serif; font-size: {round(22 * scale, 1)}pt; color: {p.heading}; font-weight: bold; }}
#StatLabel {{ color: {p.ink_muted}; font-size: {small}pt; }}

/* ---------- chips ---------- */
QLabel[chip="ok"] {{ background: {p.ok_bg}; color: {p.ok_ink}; border-radius: 9px; padding: 1px 8px; font-size: {small}pt; }}
QLabel[chip="warn"] {{ background: {p.warn_bg}; color: {p.warn_ink}; border-radius: 9px; padding: 1px 8px; font-size: {small}pt; }}
QLabel[chip="bad"] {{ background: {p.bad_bg}; color: {p.bad_ink}; border-radius: 9px; padding: 1px 8px; font-size: {small}pt; }}
QLabel[chip="info"] {{ background: {p.info_bg}; color: {p.info_ink}; border-radius: 9px; padding: 1px 8px; font-size: {small}pt; }}
QLabel[banner="info"] {{ background: {p.info_bg}; color: {p.info_ink}; border-radius: 5px; padding: 8px 10px; }}
QLabel[banner="warn"] {{ background: {p.warn_bg}; color: {p.warn_ink}; border-radius: 5px; padding: 8px 10px; }}
QLabel[banner="bad"] {{ background: {p.bad_bg}; color: {p.bad_ink}; border-radius: 5px; padding: 8px 10px; }}
QLabel[banner="ok"] {{ background: {p.ok_bg}; color: {p.ok_ink}; border-radius: 5px; padding: 8px 10px; }}

/* ---------- inputs ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {{
    background: {p.card}; color: {p.ink}; border: 1px solid {p.rule_strong}; border-radius: 4px; padding: 4px 6px;
    selection-background-color: {p.selection}; selection-color: {p.selection_ink}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 2px solid {p.accent}; padding: 3px 5px; }}
QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"] {{ border: 2px solid {p.bad_ink}; }}
QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled {{ color: {p.ink_muted}; background: {p.card_alt}; }}
QComboBox QAbstractItemView {{ background: {p.card}; color: {p.ink}; selection-background-color: {p.selection};
                              selection-color: {p.selection_ink}; border: 1px solid {p.rule_strong}; }}
QCheckBox, QRadioButton {{ spacing: 6px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
QCheckBox::indicator {{ border: 1px solid {p.rule_strong}; background: {p.card}; border-radius: 3px; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border: 1px solid {p.accent}; }}
QCheckBox:focus {{ outline: 1px dotted {p.accent}; }}

/* ---------- buttons ---------- */
QPushButton {{ background: {p.card}; color: {p.ink}; border: 1px solid {p.rule_strong}; border-radius: 4px; padding: 5px 12px; }}
QPushButton:hover {{ background: {p.card_alt}; }}
QPushButton:focus {{ border: 2px solid {p.accent}; padding: 4px 11px; }}
QPushButton:disabled {{ color: {p.ink_muted}; background: {p.card_alt}; border-color: {p.rule}; }}
QPushButton[kind="primary"] {{ background: {p.accent}; color: {p.accent_ink}; border: 1px solid {p.accent}; font-weight: bold; }}
QPushButton[kind="primary"]:hover {{ background: {p.accent_hover}; }}
QPushButton[kind="primary"]:focus {{ border: 2px solid {p.ink}; }}
QPushButton[kind="primary"]:disabled {{ background: {p.card_alt}; color: {p.ink_muted}; border-color: {p.rule}; }}
QPushButton[kind="danger"] {{ color: {p.bad_ink}; border-color: {p.bad_ink}; }}
QToolButton {{ background: transparent; color: {p.ink}; border: 1px solid transparent; border-radius: 4px; padding: 3px 6px; }}
QToolButton:hover {{ background: {p.card_alt}; border-color: {p.rule}; }}
QToolButton:focus {{ border: 1px solid {p.accent}; }}

/* ---------- lists & tables ---------- */
QListWidget, QTreeWidget, QTableWidget, QTableView, QTreeView, QListView {{
    background: {p.card}; color: {p.ink}; border: 1px solid {p.rule}; border-radius: 4px;
    alternate-background-color: {p.card_alt}; outline: none; }}
QListWidget::item, QTreeWidget::item {{ padding: 5px 4px; border-bottom: 1px solid {p.rule}; }}
QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected, QTableView::item:selected {{
    background: {p.selection}; color: {p.selection_ink}; }}
QListWidget:focus, QTreeWidget:focus, QTableWidget:focus {{ border: 1px solid {p.accent}; }}
QHeaderView::section {{ background: {p.card_alt}; color: {p.ink}; border: none; border-bottom: 1px solid {p.rule_strong};
                        padding: 5px 6px; font-weight: bold; }}

/* ---------- tabs, groups, scroll ---------- */
QTabWidget::pane {{ border: 1px solid {p.rule}; border-radius: 4px; background: {p.card}; top: -1px; }}
QTabBar::tab {{ background: {p.card_alt}; color: {p.ink}; border: 1px solid {p.rule}; border-bottom: none;
                padding: 6px 14px; margin-right: 2px; border-top-left-radius: 5px; border-top-right-radius: 5px; }}
QTabBar::tab:selected {{ background: {p.card}; color: {p.heading}; font-weight: bold; border-top: 3px solid {p.ribbon}; }}
QTabBar::tab:focus {{ color: {p.accent}; }}
QGroupBox {{ background: {p.card}; border: 1px solid {p.rule}; border-radius: 6px; margin-top: 14px; padding: 12px 10px 10px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {p.heading};
                    font-family: "{HEADING_FONT}", Georgia, serif; font-weight: bold; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {p.rule_strong}; border-radius: 5px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; }}
QScrollBar::handle:horizontal {{ background: {p.rule_strong}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QSplitter::handle {{ background: {p.rule}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QStatusBar {{ background: {p.card}; color: {p.ink_muted}; border-top: 1px solid {p.rule}; }}
QStatusBar QLabel {{ color: {p.ink_muted}; }}
QProgressBar {{ background: {p.card_alt}; border: 1px solid {p.rule}; border-radius: 4px; text-align: center; color: {p.ink}; }}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 3px; }}
QMenu {{ background: {p.card}; color: {p.ink}; border: 1px solid {p.rule_strong}; }}
QMenu::item:selected {{ background: {p.selection}; color: {p.selection_ink}; }}
QTextBrowser {{ background: {p.card}; color: {p.ink}; border: 1px solid {p.rule}; border-radius: 4px; }}
"""
    # Headings use the heading font; rounding and padding follow the user's choices.
    css = css.replace(f'"{HEADING_FONT}", Georgia', f'"{heading_font}", "{HEADING_FONT}", Georgia')
    css = re.sub(r"border-radius: (\d+)px", lambda m: f"border-radius: {round(int(m.group(1)) * r / 5)}px", css)
    css = css.replace("padding: 5px 12px;", f"padding: {px(5)}px {px(12)}px;")
    css = css.replace("padding: 4px 11px;", f"padding: {max(0, px(5) - 1)}px {max(0, px(12) - 1)}px;")
    css = css.replace("padding: 4px 6px;", f"padding: {px(4)}px {px(6)}px;")
    css = css.replace("padding: 5px 4px; border-bottom", f"padding: {px(5)}px 4px; border-bottom")
    css = css.replace("padding: 7px 14px 7px 22px;", f"padding: {px(7)}px 14px {px(7)}px 22px;")
    css = css.replace("padding: 6px 14px; margin-right", f"padding: {px(6)}px 14px; margin-right")
    return css


def html_colours(p: Palette) -> dict[str, str]:
    """Colours for rich-text (HTML) fragments shown inside widgets."""
    return {"ink": p.ink, "muted": p.ink_muted, "heading": p.heading, "ok": p.ok_ink, "warn": p.warn_ink,
            "bad": p.bad_ink, "accent": p.accent, "rule": p.rule, "card_alt": p.card_alt, "ok_bg": p.ok_bg,
            "warn_bg": p.warn_bg, "bad_bg": p.bad_bg, "info_bg": p.info_bg}


def appearance_of(config) -> Appearance:
    return Appearance.from_dict(getattr(config, "appearance", None) or {})


def stylesheet_for(config) -> str:
    """The complete style sheet for an application configuration."""
    a = appearance_of(config)
    return stylesheet(palette_for(config.theme, a), config.ui_font_scale or 1.0, a)
