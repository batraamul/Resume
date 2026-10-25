"""Visual template designer: every template setting with a live preview, readability and ATS checks.

The controls are generated from the template specification models (ris/rendering/specs.py), so new
settings appear here automatically. Built-in templates are never changed: they are saved as a copy.
"""

from __future__ import annotations

import json
import re
import tempfile
import typing
from datetime import date
from pathlib import Path

from annotated_types import Ge, Le
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ris.composition.modes import SECTION_TITLES
from ris.rendering.specs import TemplateSpec
from ris.ui.theme import contrast, readable_on
from ris.ui.widgets.common import banner, button, scroll, set_banner
from ris.ui.widgets.pdf_preview import PdfPreview
from ris.ui.workers import run_task

GROUPS: list[tuple[str, str]] = [
    ("page", "Page"), ("fonts", "Fonts & sizes"), ("colours", "Colours"), ("header", "Header"),
    ("heading", "Section headings"), ("entry", "Entries"), ("skills", "Skills"), ("publications", "Publications"),
    ("columns", "Columns"), ("graphics", "Graphics"), ("photo", "Photograph"), ("footer", "Footer"),
]
LABELS = {
    "margin_top_mm": "Top margin (mm)", "margin_bottom_mm": "Bottom margin (mm)", "margin_left_mm": "Left margin (mm)",
    "margin_right_mm": "Right margin (mm)", "body": "Body font", "heading": "Heading font", "name": "Name font",
    "body_size": "Body size (pt)", "heading_size": "Heading size (pt)", "name_size": "Name size (pt)",
    "headline_size": "Headline size (pt)", "small_size": "Small text (pt)", "line_spacing": "Line spacing",
    "text": "Text", "muted": "Secondary text", "accent": "Accent", "rule": "Rules and lines", "fill": "Shaded fill",
    "banner_fill": "Banner background", "banner_text": "Banner text", "banner_outer": "Banner frame",
    "sidebar_fill": "Sidebar background", "link": "Links", "tile_fill": "Metric tiles", "bar_track": "Bar track",
    "contact_icons": "Contact icons", "letter_spacing": "Letter spacing (pt)", "space_before": "Space before (pt)",
    "space_after": "Space after (pt)", "rule_weight": "Rule weight (pt)", "label_width_mm": "Label width (mm)",
    "bullet_glyph": "Bullet character", "bullet_indent_mm": "Bullet indent (mm)", "gutter_mm": "Date column (mm)",
    "space_between": "Space between entries (pt)", "width_frac": "Sidebar width (fraction)", "gap_mm": "Gap (mm)",
    "sidebar_sections": "Sections in the sidebar", "timeline_height_mm": "Timeline height (mm)",
    "chart_height_mm": "Chart height (mm)", "tiles_per_row": "Tiles per row", "bar_width_mm": "Bar width (mm)",
    "palette": "Chart palette", "width_mm": "Photo width (mm)", "show_name": "Show name in footer",
    "page_numbers": "Page numbers", "highlight_name": "Highlight your name in author lists",
}

#: Professional colour schemes for resumes. Accents are dark enough for text on white (WCAG AA).
RESUME_SCHEMES: dict[str, dict] = {
    "Navy classic": {"accent": "#192B4B", "link": "#1F3A5F", "banner_fill": "#192B4B", "fill": "#EEF1F4",
                     "sidebar_fill": "#F1F4F7", "tile_fill": "#EEF1F4", "rule": "#9AA3AD",
                     "palette": ["#192B4B", "#2F5D8A", "#5B7FA6", "#8E1B1B", "#C8963E"]},
    "Maroon diary": {"accent": "#701C35", "link": "#701C35", "banner_fill": "#701C35", "fill": "#F7ECE6",
                     "sidebar_fill": "#FBF3EE", "tile_fill": "#F7ECE6", "rule": "#C9AE85",
                     "palette": ["#701C35", "#A23B5A", "#C8963E", "#192B4B", "#5C7A3A"]},
    "Teal modern": {"accent": "#0F6E5C", "link": "#0F5C4E", "banner_fill": "#0F6E5C", "fill": "#E6F2EF",
                    "sidebar_fill": "#EFF7F5", "tile_fill": "#E6F2EF", "rule": "#9CC3BA",
                    "palette": ["#0F6E5C", "#2F4F1E", "#123E63", "#159A7D", "#8E1B1B"]},
    "Charcoal": {"accent": "#333333", "link": "#2B4A6B", "banner_fill": "#333333", "fill": "#EFEFEF",
                 "sidebar_fill": "#F4F4F4", "tile_fill": "#EFEFEF", "rule": "#A0A0A0",
                 "palette": ["#333333", "#5E5E5E", "#2B4A6B", "#8A6D1E", "#7A2E2E"]},
    "Forest": {"accent": "#1E5B3F", "link": "#1E5B3F", "banner_fill": "#1E5B3F", "fill": "#E9F1EB",
               "sidebar_fill": "#F1F6F2", "tile_fill": "#E9F1EB", "rule": "#A8BFA4",
               "palette": ["#1E5B3F", "#4F7F3A", "#2B5E7A", "#A2702E", "#6E2B3F"]},
    "Royal blue": {"accent": "#1A4C8B", "link": "#1A4C8B", "banner_fill": "#1A4C8B", "fill": "#E8EFF8",
                   "sidebar_fill": "#F0F5FB", "tile_fill": "#E8EFF8", "rule": "#A3B7D3",
                   "palette": ["#1A4C8B", "#3C7BC4", "#0F6E5C", "#B5651D", "#7A2E5C"]},
    "Plum": {"accent": "#5B2A6E", "link": "#5B2A6E", "banner_fill": "#5B2A6E", "fill": "#F1E9F4",
             "sidebar_fill": "#F7F1F9", "tile_fill": "#F1E9F4", "rule": "#BCA5C8",
             "palette": ["#5B2A6E", "#8A4DA3", "#2B4A6B", "#C8963E", "#3E6B48"]},
}


def _bounds(fi) -> tuple[float | None, float | None]:
    lo = hi = None
    for m in fi.metadata:
        if isinstance(m, Ge):
            lo = m.ge
        elif isinstance(m, Le):
            hi = m.le
    return lo, hi


def _label(name: str) -> str:
    return LABELS.get(name, name.replace("_", " ").capitalize())


class ColourButton(QPushButton):
    def __init__(self, value: str, on_change) -> None:
        super().__init__()
        self._value = value
        self._on_change = on_change
        self.clicked.connect(self._pick)
        self.set_value(value)

    def value(self) -> str:
        return self._value

    def set_value(self, v: str) -> None:
        self._value = (v or "#000000").upper()
        self.setText(self._value)
        ink = readable_on(self._value, "#000000")
        self.setStyleSheet(f"background: {self._value}; color: {ink}; border: 1px solid #888888; padding: 3px 8px;")

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self._value), self, "Choose a colour")
        if c.isValid():
            self.set_value(c.name())
            self._on_change()


class TemplateDesignerDialog(QDialog):
    def __init__(self, parent: QWidget | None, ctx, spec: TemplateSpec) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.base = spec
        self.setWindowTitle(f"Template designer — {spec.name}")
        self.resize(1280, 820)
        self.data = spec.model_dump(mode="json")
        self.editors: dict[tuple[str, str], QWidget] = {}
        self.result_spec: TemplateSpec | None = None
        self._loading = True
        self._gen = 0
        self._tmp = tempfile.TemporaryDirectory(prefix="ris-designer-")
        self._ws = None
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Name:"))
        self.name = QLineEdit(spec.name if not spec.builtin else f"{spec.name} (custom)")
        self.name.setAccessibleName("Template name")
        top.addWidget(self.name, 2)
        top.addWidget(QLabel("Colour scheme:"))
        self.scheme = QComboBox()
        self.scheme.setAccessibleName("Colour scheme")
        self.scheme.addItem("(keep current colours)", "")
        for k in RESUME_SCHEMES:
            self.scheme.addItem(k, k)
        self.scheme.currentIndexChanged.connect(self._apply_scheme)
        top.addWidget(self.scheme, 1)
        self.ats = QCheckBox("ATS-safe (single column, no tables or graphics)")
        self.ats.setAccessibleName("ATS-safe template")
        self.ats.setChecked(spec.ats_safe)
        self.ats.toggled.connect(self._ats_toggled)
        top.addWidget(self.ats)
        lay.addLayout(top)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName("Template settings")
        for key, title in GROUPS:
            self.tabs.addTab(scroll(self._group_widget(key)), title)
        split.addWidget(self.tabs)
        right = QWidget()
        rl = QVBoxLayout(right)
        self.preview = PdfPreview()
        rl.addWidget(self.preview, 1)
        self.checks = banner("", "info")
        rl.addWidget(self.checks)
        split.addWidget(right)
        split.setSizes([520, 760])
        lay.addWidget(split, 1)
        self.problem = banner("", "bad")
        self.problem.setVisible(False)
        lay.addWidget(self.problem)
        row = QHBoxLayout()
        row.addWidget(button("Import JSON…", on_click=lambda: self.import_json()))
        row.addWidget(button("Export JSON…", on_click=lambda: self.export_json()))
        row.addStretch(1)
        row.addWidget(button("Cancel", on_click=self.reject))
        self.b_save_new = button("Save as new template", on_click=lambda: self.save(as_new=True))
        row.addWidget(self.b_save_new)
        self.b_save = button("Save", "primary", on_click=lambda: self.save(as_new=False))
        self.b_save.setVisible(not spec.builtin)
        row.addWidget(self.b_save)
        lay.addLayout(row)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self.update_preview)
        self._loading = False
        self._timer.start()

    # ------------------------------------------------------------------ controls from the schema
    def _group_widget(self, group: str) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        model = TemplateSpec.model_fields[group].annotation
        values = self.data[group]
        for name, fi in model.model_fields.items():
            ann = fi.annotation
            origin = typing.get_origin(ann)
            val = values.get(name)
            editor: QWidget
            if origin is typing.Literal or (ann is not None and getattr(ann, "__origin__", None) is typing.Literal):
                editor = QComboBox()
                for opt in typing.get_args(ann):
                    editor.addItem(str(opt).replace("_", " "), opt)
                editor.setCurrentIndex(max(0, editor.findData(val)))
                editor.currentIndexChanged.connect(self._changed)
            elif ann is bool:
                editor = QCheckBox()
                editor.setChecked(bool(val))
                editor.toggled.connect(self._changed)
            elif ann is int:
                editor = QSpinBox()
                lo, hi = _bounds(fi)
                editor.setRange(int(lo if lo is not None else 0), int(hi if hi is not None else 100))
                editor.setValue(int(val))
                editor.valueChanged.connect(self._changed)
            elif ann is float:
                editor = QDoubleSpinBox()
                lo, hi = _bounds(fi)
                editor.setRange(float(lo if lo is not None else 0), float(hi if hi is not None else 100))
                editor.setDecimals(2)
                editor.setSingleStep(0.5 if (hi or 0) > 5 else 0.05)
                editor.setValue(float(val))
                editor.valueChanged.connect(self._changed)
            elif group == "colours" or (isinstance(val, str) and re.match(r"^#[0-9A-Fa-f]{6}$", val or "")):
                editor = ColourButton(val, self._changed)
            elif name == "palette":
                editor = QWidget()
                hl = QHBoxLayout(editor)
                hl.setContentsMargins(0, 0, 0, 0)
                editor.buttons = [ColourButton(c, self._changed) for c in val]  # type: ignore[attr-defined]
                for b in editor.buttons:  # type: ignore[attr-defined]
                    hl.addWidget(b)
            elif name == "sidebar_sections":
                editor = QListWidget()
                editor.setMaximumHeight(170)
                for key, title in SECTION_TITLES.items():
                    it = QListWidgetItem(title)
                    it.setData(Qt.ItemDataRole.UserRole, key)
                    it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    it.setCheckState(Qt.CheckState.Checked if key in (val or []) else Qt.CheckState.Unchecked)
                    editor.addItem(it)
                editor.itemChanged.connect(self._changed)
            else:
                editor = QLineEdit(str(val or ""))
                editor.textChanged.connect(self._changed)
            editor.setAccessibleName(f"{dict(GROUPS)[group]}: {_label(name)}")
            if fi.description:
                editor.setToolTip(fi.description)
            self.editors[(group, name)] = editor
            form.addRow(_label(name) + ":", editor)
        return w

    def _value(self, editor: QWidget):
        if isinstance(editor, QComboBox):
            return editor.currentData()
        if isinstance(editor, QCheckBox):
            return editor.isChecked()
        if isinstance(editor, (QSpinBox, QDoubleSpinBox)):
            return editor.value()
        if isinstance(editor, ColourButton):
            return editor.value()
        if isinstance(editor, QListWidget):
            return [editor.item(i).data(Qt.ItemDataRole.UserRole) for i in range(editor.count())
                    if editor.item(i).checkState() == Qt.CheckState.Checked]
        if hasattr(editor, "buttons"):
            return [b.value() for b in editor.buttons]
        return editor.text()

    def _set(self, group: str, name: str, value) -> None:
        ed = self.editors.get((group, name))
        if ed is None:
            return
        if isinstance(ed, QComboBox):
            ed.setCurrentIndex(max(0, ed.findData(value)))
        elif isinstance(ed, QCheckBox):
            ed.setChecked(bool(value))
        elif isinstance(ed, (QSpinBox, QDoubleSpinBox)):
            ed.setValue(value)
        elif isinstance(ed, ColourButton):
            ed.set_value(value)
        elif hasattr(ed, "buttons"):
            for b, v in zip(ed.buttons, value, strict=False):
                b.set_value(v)

    def collect(self) -> dict:
        data = json.loads(json.dumps(self.data))
        for (group, name), ed in self.editors.items():
            data[group][name] = self._value(ed)
        data["name"] = self.name.text().strip()[:60] or self.base.name
        data["ats_safe"] = self.ats.isChecked()
        return data

    def set_value(self, group: str, name: str, value) -> None:
        """Set one setting programmatically (used by tests and scripts)."""
        self._set(group, name, value)
        self._changed()

    # ------------------------------------------------------------------ reactions
    def _changed(self, *_a) -> None:
        if not self._loading:
            self._timer.start()

    def _apply_scheme(self) -> None:
        key = self.scheme.currentData()
        if not key:
            return
        s = RESUME_SCHEMES[key]
        self._loading = True
        for k, v in s.items():
            if k == "palette":
                self._set("graphics", "palette", v)
            else:
                self._set("colours", k, v)
        self._loading = False
        self._changed()

    def _ats_toggled(self, on: bool) -> None:
        if on:
            self._loading = True
            for (group, name), value in {("columns", "enabled"): False, ("graphics", "enabled"): False,
                                         ("header", "contact_icons"): False}.items():
                self._set(group, name, value)
            if self._value(self.editors[("header", "style")]) not in ("left", "centered"):
                self._set("header", "style", "left")
            if self._value(self.editors[("heading", "style")]) in ("margin_label", "shaded_bar"):
                self._set("heading", "style", "rule_below")
            if self._value(self.editors[("skills", "style")]) in ("table", "bars"):
                self._set("skills", "style", "inline_categories")
            if self._value(self.editors[("skills", "competencies_style")]) == "columns":
                self._set("skills", "competencies_style", "inline")
            self._set("entry", "project_style", "standard")
            self.data["tables_allowed"] = False
            self._loading = False
        else:
            self.data["tables_allowed"] = True
        self._changed()

    def spec_or_error(self) -> tuple[TemplateSpec | None, str]:
        data = self.collect()
        if not data["ats_safe"] and (data["columns"]["enabled"] or data["graphics"]["enabled"]
                                     or data["header"]["style"] in ("split", "banner", "framed")):
            data["tables_allowed"] = True
        try:
            return TemplateSpec.model_validate(data), ""
        except Exception as exc:  # noqa: BLE001 - shown to the user
            msgs = getattr(exc, "errors", lambda: [])()
            text = "; ".join(m.get("msg", "").removeprefix("Value error, ") for m in msgs[:3]) or str(exc)
            return None, text

    def readability(self, spec: TemplateSpec) -> list[str]:
        c = spec.colours
        out = []
        pairs = [("Text", c.text, "#FFFFFF", 4.5), ("Secondary text", c.muted, "#FFFFFF", 4.5),
                 ("Accent headings", c.accent, "#FFFFFF", 3.0), ("Links", c.link, "#FFFFFF", 4.5),
                 ("Text on shaded fill", c.text, c.fill, 4.5)]
        if spec.header.style in ("banner", "framed"):
            pairs.append(("Banner text", c.banner_text, c.banner_fill, 4.5))
        if spec.columns.enabled:
            pairs.append(("Text in the sidebar", c.text, c.sidebar_fill, 4.5))
        for label, fg, bg, need in pairs:
            r = contrast(fg, bg)
            if r < need:
                out.append(f"{label}: contrast {r:.1f}:1 (needs {need}:1)")
        if spec.fonts.body_size < 9.5:
            out.append(f"Body text {spec.fonts.body_size} pt is small; 10–12 pt reads best.")
        if min(spec.page.margin_left_mm, spec.page.margin_right_mm) < 12:
            out.append("Side margins under 12 mm look cramped and may be cut off when printed.")
        return out

    def update_preview(self) -> None:
        spec, err = self.spec_or_error()
        if spec is None:
            set_banner(self.problem, "Please correct: " + err, "bad")
            self.problem.setVisible(True)
            return
        self.problem.setVisible(False)
        self._gen += 1
        gen = self._gen
        ws_holder = self

        def work():
            from ris.domain.enums import RecordKind
            from ris.domain.models import Variant
            from ris.intelligence.ats import ats_readiness
            from ris.rendering.export import ExportService
            from ris.rendering.specs import TemplateLibrary
            from ris.services.sample import load_sample_profile
            from ris.storage.workspace import Workspace

            if ws_holder._ws is None:
                ws = Workspace(Path(ws_holder._tmp.name) / "ws", "Designer preview", is_sample=True).open()
                load_sample_profile(ws)
                ws_holder._ws = ws
            ws = ws_holder._ws
            lib = TemplateLibrary()
            lib._all()[spec.id] = spec
            svc = ExportService(ws, lib, today=date.today())
            base = next(v for v in ws.repo.list(RecordKind.VARIANT) if v.data.mode == "defence_technical")
            mode = spec.recommended_modes[0] if spec.recommended_modes else "general_professional"
            v = Variant.model_validate({**base.payload(), "template_id": spec.id, "mode": mode, "max_pages": None,
                                        "length": "two_pages"})
            comp = svc.compose(v, variant_id=base.id)
            data, pages, _used, _w = svc.preview_pdf(comp.doc, spec, engine="builtin")
            return gen, data, pages, ats_readiness(comp.doc, spec)

        def done(result) -> None:
            g, data, pages, ats = result
            if g != self._gen:
                return
            self.preview.set_pdf(data, f"Preview with the fictional sample · {pages} page(s)")
            notes = self.readability(spec)
            fails = [c.title for c in ats.checks if c.status == "fail"]
            text = f"ATS readiness {ats.score}/100" + (f" — not suited to portals: {', '.join(fails)}." if fails else
                                                       " — suitable for online portals.")
            if notes:
                text += " Readability: " + "; ".join(notes)
            set_banner(self.checks, text, "warn" if notes else "ok" if not fails else "info")
            self.last_checks = (ats, notes)

        run_task(work, done, lambda m, _d: self.preview.clear("Preview failed: " + m))

    # ------------------------------------------------------------------ files and saving
    def export_json(self, path: str | None = None) -> Path | None:
        spec, err = self.spec_or_error()
        if spec is None:
            set_banner(self.problem, "Please correct: " + err, "bad")
            self.problem.setVisible(True)
            return None
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Export template", f"{spec.id}.json", "JSON (*.json)")
            if not path:
                return None
        Path(path).write_text(json.dumps(spec.model_dump(mode="json"), indent=2), encoding="utf-8")
        return Path(path)

    def import_json(self, path: str | None = None) -> bool:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Import template", "", "JSON (*.json)")
            if not path:
                return False
        try:
            spec = TemplateSpec.model_validate_json(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - shown to the user
            set_banner(self.problem, f"That file is not a valid template: {str(exc).splitlines()[0][:200]}", "bad")
            self.problem.setVisible(True)
            return False
        self.data = spec.model_dump(mode="json")
        self._loading = True
        for (group, name), _ed in self.editors.items():
            self._set(group, name, self.data[group][name])
        self.name.setText(spec.name)
        self.ats.setChecked(spec.ats_safe)
        self._loading = False
        self._changed()
        return True

    def save(self, as_new: bool) -> TemplateSpec | None:
        spec, err = self.spec_or_error()
        if spec is None:
            set_banner(self.problem, "Please correct: " + err, "bad")
            self.problem.setVisible(True)
            return None
        lib = self.ctx.templates
        data = spec.model_dump(mode="json")
        if as_new or self.base.builtin:
            slug = re.sub(r"[^a-z0-9]+", "_", data["name"].lower()).strip("_")[:30] or "custom"
            new_id, n = f"user_{slug}", 2
            while lib.find(new_id) is not None:
                new_id, n = f"user_{slug}_{n}", n + 1
            data.update({"id": new_id, "version": "1.0.0"})
        else:
            major, minor, patch = (int(x) for x in self.base.version.split("."))
            data["version"] = f"{major}.{minor}.{patch + 1}"
        try:
            final = TemplateSpec.model_validate(data)
            lib.save_user_template(final)
        except Exception as exc:  # noqa: BLE001 - shown to the user
            set_banner(self.problem, getattr(exc, "user_message", str(exc).splitlines()[0][:200]), "bad")
            self.problem.setVisible(True)
            return None
        self.result_spec = lib.get(final.id)
        self.accept()
        return self.result_spec

    def done(self, r: int) -> None:  # noqa: D401 - Qt override
        try:
            if self._ws is not None:
                self._ws.close()
                self._ws = None
            self._tmp.cleanup()
        except OSError:
            pass
        super().done(r)
