"""Diary-inspired visual theme: colour tokens, contrast checks, fonts and the Qt style sheet.

Light theme: maroon index panel (#701C35), ivory pages (#FFF3DF), cream cards (#FFFAF0)
and navy ink (#192B4B). The dark theme keeps the same structure with a deep-navy page,
lighter maroon accents and ivory ink. Every text/background pair used by the style sheet
is listed in ``TEXT_PAIRS`` and verified against WCAG 2.1 AA by the test suite.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

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
                 "Caladea-Regular", "Caladea-Bold", "Caladea-Italic"):
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


def stylesheet(p: Palette, scale: float = 1.0) -> str:
    base = round(10.5 * scale, 1)
    small = round(9.5 * scale, 1)
    h1 = round(19 * scale, 1)
    h2 = round(13.5 * scale, 1)
    return f"""
* {{ font-family: "{UI_FONT}", "Calibri", "Segoe UI", "Helvetica Neue", sans-serif; font-size: {base}pt; }}
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


def html_colours(p: Palette) -> dict[str, str]:
    """Colours for rich-text (HTML) fragments shown inside widgets."""
    return {"ink": p.ink, "muted": p.ink_muted, "heading": p.heading, "ok": p.ok_ink, "warn": p.warn_ink,
            "bad": p.bad_ink, "accent": p.accent, "rule": p.rule, "card_alt": p.card_alt, "ok_bg": p.ok_bg,
            "warn_bg": p.warn_bg, "bad_bg": p.bad_bg, "info_bg": p.info_bg}
