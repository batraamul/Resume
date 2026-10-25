"""Chart choices for graphical resumes.

Each chart can be switched off or drawn in one of the styles that suit its data: part-to-whole data (share of
career years, publications by type) may be a pie or donut; data over time (publications per year) may be columns
or a line; levels (self-assessed skill levels) may be bars, dots or words. Styles that would misrepresent the data
(for example a pie of publications per year) are not offered.

A resume variant stores only the charts the user changed (``Variant.charts``); a template may set its own defaults
(``GraphicsSpec.chart_styles``); otherwise ``ChartInfo.default`` applies. Charts are drawn only by templates with
graphics enabled; every chart's facts also appear as text.
"""

from __future__ import annotations

from dataclasses import dataclass

OFF = "off"


@dataclass(frozen=True)
class ChartInfo:
    key: str
    label: str
    section: str
    styles: tuple[tuple[str, str], ...]
    default: str
    help: str = ""

    @property
    def style_ids(self) -> tuple[str, ...]:
        return tuple(s for s, _ in self.styles)

    def style_label(self, style: str) -> str:
        return dict(self.styles).get(style, style)


CHARTS: dict[str, ChartInfo] = {c.key: c for c in (
    ChartInfo("career_timeline", "Career timeline", "career_timeline",
              (("timeline", "Timeline columns"), ("bars", "Horizontal bars (years)"),
               ("donut", "Donut — share of career"), ("pie", "Pie — share of career"), (OFF, "Off — text list only")),
              "timeline", "Years in each organisation, calculated from your recorded dates."),
    ChartInfo("publications_by_year", "Publications by year", "research_overview",
              (("stacked", "Stacked columns by type"), ("columns", "Columns — total per year"),
               ("line", "Line — per year"), ("cumulative", "Cumulative line"), (OFF, "Off")),
              "stacked", "Published and accepted outputs per year."),
    ChartInfo("publications_by_type", "Publications by type", "research_overview",
              ((OFF, "Off"), ("donut", "Donut"), ("pie", "Pie"), ("bars", "Horizontal bars")),
              OFF, "Share of journal, conference and other outputs."),
    ChartInfo("research_metrics", "Research metrics", "research_overview",
              (("tiles", "Tiles"), ("text", "One line of text"), (OFF, "Off")),
              "tiles", "Counts of publications, patents, grants and talks, and citation figures you entered."),
    ChartInfo("skill_levels", "Skill levels", "skills",
              (("bars", "Segmented bars"), ("dots", "Dots"), ("text", "Words (e.g. Advanced)"),
               (OFF, "Off — skill names only")),
              "bars", "Your own assessment of proficiency, shown only for skills you rated."),
    ChartInfo("expertise_years", "Areas of expertise", "expertise",
              ((OFF, "Text only"), ("bars", "Bar chart of years")),
              OFF, "Years of experience you recorded for each area."),
)}

LEVEL_WORDS = {1: "Familiar", 2: "Working knowledge", 3: "Proficient", 4: "Advanced", 5: "Expert"}


def clean_choices(choices: dict | None) -> dict[str, str]:
    """Keep only known charts and allowed styles ('auto' or empty means: use the template's default)."""
    out: dict[str, str] = {}
    for key, style in (choices or {}).items():
        info = CHARTS.get(str(key))
        style = str(style or "").strip().lower()
        if info is None or not style or style == "auto":
            continue
        if style not in info.style_ids:
            raise ValueError(f"'{style}' is not a style for {info.label}; choose one of "
                             + ", ".join(info.style_ids))
        out[info.key] = style
    return out


def resolve(key: str, variant: dict[str, str] | None = None, template: dict[str, str] | None = None) -> str:
    """Style to draw: the resume's choice, else the template's default, else the built-in default."""
    info = CHARTS[key]
    for source in (variant or {}, template or {}):
        style = source.get(key)
        if style in info.style_ids:
            return style
    return info.default
