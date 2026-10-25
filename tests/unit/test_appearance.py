"""Appearance customisation: presets, colour overrides with automatic contrast correction, style sheet options
(UX-09, UX-10)."""

from __future__ import annotations

import pytest

from ris.ui import theme


@pytest.mark.req("UX-09", "UX-06")
@pytest.mark.parametrize("preset", list(theme.PRESETS))
def test_every_preset_meets_wcag_in_light_and_dark(preset):
    _name, light, dark = theme.PRESETS[preset]
    for p in (light, dark):
        failures = [r for r in theme.contrast_report(p) if r[2] < r[3]]
        assert not failures, (preset, p.name, failures)
    assert theme.palette_for("light", theme.Appearance(preset=preset)) == light
    assert theme.palette_for("dark", theme.Appearance(preset=preset)) == dark


@pytest.mark.req("UX-09")
@pytest.mark.parametrize("colours", [
    {"page": "#202020"}, {"page": "#FFFFFF"}, {"accent": "#FFFF00"}, {"nav_bg": "#FFFFFF"},
    {"nav_bg": "#FFE680", "ink": "#777777"}, {"page": "#0B1A33", "heading": "#0B1A33"},
])
def test_overrides_keep_text_readable(colours):
    for mode in ("light", "dark"):
        p = theme.palette_for(mode, theme.Appearance.from_dict({"colours": colours}))
        text_pairs = [r for r in theme.contrast_report(p) if r[0] in ("ink", "ink_muted", "heading", "accent_ink",
                                                                     "nav_ink", "nav_muted") and r[2] < r[3]]
        assert not text_pairs, (mode, colours, text_pairs)


@pytest.mark.req("UX-09")
def test_unreadable_choice_is_reported():
    p = theme.palette_for("light", theme.Appearance.from_dict({"colours": {"card": "#000000"}}))
    assert theme.contrast_warnings(p)


@pytest.mark.req("UX-10")
def test_appearance_validation_and_stylesheet_options():
    a = theme.Appearance.from_dict({"preset": "nope", "density": "huge", "radius": 99, "nav_style": "x",
                                    "colours": {"accent": "#12ab34", "evil": "#000000", "page": "red"},
                                    "nav_side": "right", "unknown": 1})
    assert a.preset == "diary" and a.density == "comfortable" and a.radius == 12 and a.nav_style == "icons_text"
    assert a.colours == {"accent": "#12AB34"} and a.nav_side == "right"
    css = theme.stylesheet(theme.palette_for("light", a), 1.2, theme.Appearance(ui_font="Arial",
                                                                                 heading_font="Georgia",
                                                                                 density="compact", radius=0))
    assert '"Arial"' in css and '"Georgia"' in css and "border-radius: 4px" not in css
    assert "font-size: 12.6pt" in css
    roomy = theme.stylesheet(theme.LIGHT, 1.0, theme.Appearance(density="spacious"))
    tight = theme.stylesheet(theme.LIGHT, 1.0, theme.Appearance(density="compact"))
    assert roomy != tight
    assert set(theme.NAV_ICONS) >= {"diary", "training", "interview", "portals", "settings"}


@pytest.mark.req("UX-10")
def test_nav_icons_render_with_the_bundled_font():
    from reportlab.pdfbase.ttfonts import TTFont

    from ris.resources import fonts_dir

    face = TTFont("DejaVuCheck", str(fonts_dir() / "DejaVuSans.ttf")).face
    missing = [k for k, g in theme.NAV_ICONS.items() if ord(g) not in face.charToGlyph]
    assert not missing, missing
