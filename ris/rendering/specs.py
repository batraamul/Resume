"""Template specifications: versioned JSON files describing a layout system.

A template selects layout primitives (header, section-heading, entry, skills,
columns) plus typography and colour. Built-in templates ship in
``templates/``; users can duplicate and edit templates in
``<data dir>/templates/`` without touching code. See docs/TEMPLATE_GUIDE.md.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ris.errors import TemplateError
from ris.resources import templates_dir

FontName = Literal["Calibri", "Cambria", "Arial", "Times New Roman"]
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _hex(v: str) -> str:
    if not _HEX.match(v or ""):
        raise ValueError(f"'{v}' is not a #RRGGBB colour")
    return v.upper()


class PageSpec(_Spec):
    margin_top_mm: float = Field(16, ge=6, le=40)
    margin_bottom_mm: float = Field(16, ge=6, le=40)
    margin_left_mm: float = Field(18, ge=6, le=40)
    margin_right_mm: float = Field(18, ge=6, le=40)


class FontSpec(_Spec):
    body: FontName = "Calibri"
    heading: FontName = "Calibri"
    name: FontName = "Calibri"
    body_size: float = Field(10.5, ge=7, le=14)
    heading_size: float = Field(11.5, ge=8, le=18)
    name_size: float = Field(22, ge=12, le=36)
    headline_size: float = Field(11, ge=8, le=18)
    small_size: float = Field(9, ge=6.5, le=12)
    line_spacing: float = Field(1.08, ge=0.9, le=1.6)


class ColourSpec(_Spec):
    text: str = "#1F1F1F"
    muted: str = "#555555"
    accent: str = "#192B4B"
    rule: str = "#9AA3AD"
    fill: str = "#EEF1F4"
    banner_fill: str = "#192B4B"
    banner_text: str = "#FFFFFF"
    banner_outer: str = "#1F1F1F"
    sidebar_fill: str = "#F1F4F7"
    link: str = "#1F3A5F"
    tile_fill: str = "#EEF1F4"
    bar_track: str = "#D9DEE3"

    @field_validator("*")
    @classmethod
    def _v(cls, v: str) -> str:
        return _hex(v)


class HeaderSpec(_Spec):
    style: Literal["centered", "left", "split", "banner", "sidebar", "framed"] = "left"
    name_case: Literal["normal", "upper", "small_caps"] = "normal"
    name_colour: Literal["accent", "text"] = "text"
    headline_colour: Literal["accent", "text", "muted"] = "muted"
    contact_style: Literal["inline", "stacked"] = "inline"
    contact_icons: bool = False
    separator: str = Field("  |  ", max_length=8)
    rule: Literal["none", "single", "double", "thick"] = "none"


class HeadingSpec(_Spec):
    style: Literal["rule_below", "caps_rule", "shaded_bar", "left_bar", "small_caps", "plain_bold", "numbered",
                   "margin_label"] = "rule_below"
    case: Literal["upper", "title", "small_caps"] = "upper"
    colour: Literal["accent", "text"] = "accent"
    letter_spacing: float = Field(0.0, ge=0, le=4)
    space_before: float = Field(10, ge=0, le=30)
    space_after: float = Field(4, ge=0, le=20)
    rule_weight: float = Field(0.75, ge=0.25, le=4)
    label_width_mm: float = Field(32, ge=18, le=60)


class EntrySpec(_Spec):
    style: Literal["title_date_right", "org_first", "stacked", "date_left", "inline"] = "title_date_right"
    date_style: Literal["mon_year", "month_year", "mm_yyyy", "year"] = "mon_year"
    subtitle_italic: bool = True
    show_location: bool = True
    show_description: bool = True
    bullet_glyph: str = Field("•", min_length=1, max_length=2)
    bullet_indent_mm: float = Field(4.5, ge=2, le=12)
    gutter_mm: float = Field(26, ge=14, le=45)
    space_between: float = Field(5, ge=0, le=16)
    project_style: Literal["standard", "cards"] = "standard"


class SkillsSpec(_Spec):
    style: Literal["inline_categories", "table", "bullets", "inline", "bars"] = "inline_categories"
    competencies_style: Literal["inline", "columns", "bullets"] = "inline"
    columns: int = Field(3, ge=2, le=4)
    separator: str = Field(", ", max_length=6)


class PublicationSpec(_Spec):
    style: Literal["numbered", "bulleted"] = "numbered"
    highlight_name: bool = True


class ColumnsSpec(_Spec):
    enabled: bool = False
    side: Literal["left", "right"] = "left"
    width_frac: float = Field(0.31, ge=0.22, le=0.42)
    gap_mm: float = Field(6, ge=2, le=14)
    sidebar_sections: list[str] = Field(default_factory=lambda: ["competencies", "skills", "education", "training",
                                                                 "languages"])


class FooterSpec(_Spec):
    page_numbers: Literal["none", "page_x_of_y", "x_of_y", "x"] = "page_x_of_y"
    show_name: bool = True
    text: str = Field("", max_length=80)


class GraphicsSpec(_Spec):
    """Charts and visual elements for graphical templates (never used by ATS-safe templates)."""

    enabled: bool = False
    palette: list[str] = Field(default_factory=lambda: ["#0F6E5C", "#2F4F1E", "#123E63", "#159A7D", "#8E1B1B",
                                                        "#6B4C9A", "#B5651D"])
    timeline_height_mm: float = Field(58, ge=35, le=90)
    chart_height_mm: float = Field(48, ge=30, le=80)
    tiles_per_row: int = Field(4, ge=2, le=6)
    bar_width_mm: float = Field(30, ge=15, le=60)

    @field_validator("palette")
    @classmethod
    def _pal(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("palette needs at least one colour")
        return [_hex(c) for c in v[:12]]


class PhotoSpec(_Spec):
    allowed: bool = False
    width_mm: float = Field(28, ge=18, le=45)


class TemplateSpec(_Spec):
    schema_version: int = 1
    id: str = Field(..., pattern=r"^[a-z][a-z0-9_]{2,40}$")
    name: str = Field(..., min_length=2, max_length=60)
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    description: str = ""
    family: str = ""
    ats_safe: bool = False
    tables_allowed: bool = True
    recommended_modes: list[str] = Field(default_factory=list)
    summary_style: Literal["plain", "boxed", "italic"] = "plain"
    page: PageSpec = Field(default_factory=PageSpec)
    fonts: FontSpec = Field(default_factory=FontSpec)
    colours: ColourSpec = Field(default_factory=ColourSpec)
    header: HeaderSpec = Field(default_factory=HeaderSpec)
    heading: HeadingSpec = Field(default_factory=HeadingSpec)
    entry: EntrySpec = Field(default_factory=EntrySpec)
    skills: SkillsSpec = Field(default_factory=SkillsSpec)
    publications: PublicationSpec = Field(default_factory=PublicationSpec)
    columns: ColumnsSpec = Field(default_factory=ColumnsSpec)
    footer: FooterSpec = Field(default_factory=FooterSpec)
    photo: PhotoSpec = Field(default_factory=PhotoSpec)
    graphics: GraphicsSpec = Field(default_factory=GraphicsSpec)
    builtin: bool = Field(False, exclude=True)

    @model_validator(mode="after")
    def _consistency(self) -> TemplateSpec:
        if self.ats_safe:
            problems = []
            if self.tables_allowed:
                problems.append("tables_allowed must be false")
            if self.columns.enabled:
                problems.append("columns must be disabled")
            if self.header.style not in ("left", "centered"):
                problems.append("header style must be left or centered")
            if self.heading.style in ("margin_label", "shaded_bar"):
                problems.append("heading style must be conventional")
            if self.skills.competencies_style == "columns" or self.skills.style in ("table", "bars"):
                problems.append("skills must not use tables or bars")
            if self.graphics.enabled:
                problems.append("graphics must be disabled")
            if self.entry.project_style == "cards":
                problems.append("project cards are not ATS-safe")
            if problems:
                raise ValueError("ATS-safe template: " + "; ".join(problems))
        if self.header.style == "framed" and not self.tables_allowed:
            raise ValueError("A framed header requires tables_allowed = true")
        if self.header.style == "sidebar" and not self.columns.enabled:
            raise ValueError("A sidebar header requires columns.enabled = true")
        if self.columns.enabled and not self.tables_allowed:
            raise ValueError("Column layouts need tables_allowed = true")
        return self

    @property
    def uses_tables(self) -> bool:
        return self.tables_allowed and (
            self.columns.enabled or self.header.style in ("split", "banner", "framed")
            or self.heading.style == "margin_label" or self.skills.style in ("table", "bars")
            or self.skills.competencies_style == "columns" or self.graphics.enabled
            or self.entry.project_style == "cards"
        )


# --------------------------------------------------------------------------- library


class TemplateLibrary:
    """Built-in templates plus user templates from the data directory."""

    def __init__(self, user_dir: Path | None = None, builtin_dir: Path | None = None) -> None:
        self.builtin_dir = builtin_dir or templates_dir()
        self.user_dir = user_dir
        self._cache: dict[str, TemplateSpec] | None = None
        self.load_errors: list[str] = []

    @staticmethod
    def parse(text: str, source: str = "template") -> TemplateSpec:
        try:
            raw = json.loads(text)
        except ValueError as exc:
            raise TemplateError(f"{source}: not valid JSON ({exc.msg} at line {exc.lineno}).") from exc
        try:
            return TemplateSpec.model_validate(raw)
        except ValidationError as exc:
            msgs = []
            for e in exc.errors():
                loc = ".".join(str(x) for x in e.get("loc", ()))
                msgs.append(f"{loc}: {e.get('msg', '').removeprefix('Value error, ')}")
            raise TemplateError(f"{source}: " + "; ".join(msgs[:6])) from exc

    def _load_dir(self, folder: Path, builtin: bool) -> dict[str, TemplateSpec]:
        out: dict[str, TemplateSpec] = {}
        if not folder or not folder.exists():
            return out
        for path in sorted(folder.glob("*.json")):
            try:
                spec = self.parse(path.read_text(encoding="utf-8"), path.name)
            except (TemplateError, OSError) as exc:
                self.load_errors.append(str(getattr(exc, "user_message", exc)))
                continue
            spec.builtin = builtin
            out[spec.id] = spec
        return out

    def _all(self) -> dict[str, TemplateSpec]:
        if self._cache is None:
            self.load_errors = []
            builtin = self._load_dir(self.builtin_dir, True)
            user = self._load_dir(self.user_dir, False) if self.user_dir else {}
            for tid in list(user):
                if tid in builtin:
                    self.load_errors.append(f"User template '{tid}' has the same id as a built-in template and was ignored.")
                    user.pop(tid)
            self._cache = {**builtin, **user}
        return self._cache

    def reload(self) -> None:
        self._cache = None

    def list(self) -> list[TemplateSpec]:
        order = ["ats_minimal", "executive_technical", "defence_technical", "scientific_research",
                 "engineering_professional", "aiml_specialist", "avionics_drone", "government_cv",
                 "modern_professional", "academic_extended", "compact_two_page", "diary_edition",
                 "graphical_profile", "research_showcase", "infographic_timeline"]
        items = list(self._all().values())
        return sorted(items, key=lambda t: (order.index(t.id) if t.id in order else 99, t.name))

    def get(self, template_id: str) -> TemplateSpec:
        spec = self._all().get(template_id)
        if spec is None:
            raise TemplateError(f"Template '{template_id}' is not available.")
        return spec

    def find(self, template_id: str) -> TemplateSpec | None:
        return self._all().get(template_id)

    def save_user_template(self, spec: TemplateSpec) -> Path:
        if self.user_dir is None:
            raise TemplateError("No user template folder is configured.")
        existing = self._all().get(spec.id)
        if existing is not None and existing.builtin:
            raise TemplateError("Built-in templates cannot be overwritten; duplicate it under a new id.")
        self.user_dir.mkdir(parents=True, exist_ok=True)
        path = self.user_dir / f"{spec.id}.json"
        path.write_text(json.dumps(spec.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8")
        self.reload()
        return path

    def duplicate(self, template_id: str, new_name: str) -> TemplateSpec:
        base = self.get(template_id)
        slug = re.sub(r"[^a-z0-9]+", "_", new_name.lower()).strip("_")[:30] or "custom"
        new_id = f"user_{slug}"
        n = 2
        while new_id in self._all():
            new_id = f"user_{slug}_{n}"
            n += 1
        data = base.model_dump(mode="json")
        data.update({"id": new_id, "name": new_name.strip()[:60] or base.name, "version": "1.0.0"})
        spec = TemplateSpec.model_validate(data)
        self.save_user_template(spec)
        return self.get(new_id)

    def delete_user_template(self, template_id: str) -> None:
        spec = self.get(template_id)
        if spec.builtin:
            raise TemplateError("Built-in templates cannot be deleted.")
        assert self.user_dir is not None
        (self.user_dir / f"{template_id}.json").unlink(missing_ok=True)
        self.reload()
