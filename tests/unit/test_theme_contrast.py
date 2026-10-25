"""Interface palette: the diary identity colours and WCAG 2.1 AA contrast for every text pair."""

from __future__ import annotations

import pytest

from ris.ui.theme import DARK, LIGHT, contrast, contrast_report, stylesheet


@pytest.mark.req("UX-01")
def test_diary_identity_colours():
    assert LIGHT.nav_bg == "#701C35" and LIGHT.page == "#FFF3DF" and LIGHT.card == "#FFFAF0" and LIGHT.ink == "#192B4B"
    css = stylesheet(LIGHT)
    for colour in ("#701C35", "#FFF3DF", "#FFFAF0", "#192B4B"):
        assert colour in css


@pytest.mark.req("UX-06", "UX-04")
@pytest.mark.parametrize("palette", [LIGHT, DARK], ids=["light", "dark"])
def test_every_text_pair_meets_wcag_aa(palette):
    failures = [(fg, bg, ratio, need) for fg, bg, ratio, need in contrast_report(palette) if ratio < need]
    assert not failures, failures


def test_contrast_formula_reference_values():
    assert contrast("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.01)
    assert contrast("#777777", "#FFFFFF") == pytest.approx(4.48, abs=0.02)
