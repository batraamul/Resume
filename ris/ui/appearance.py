"""Customise appearance: colour presets and overrides, fonts, text size, density, navigation and layout.

Changes apply immediately so the whole window acts as the preview; contrast problems are reported as you go.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ris.strings import NAV_SECTIONS
from ris.ui import theme
from ris.ui.widgets.common import banner, button, set_banner


class AppearanceDialog(QDialog):
    def __init__(self, parent: QWidget | None, ctx, on_apply) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.on_apply = on_apply
        self.setWindowTitle("Customise appearance")
        self.resize(720, 640)
        self._original = (dict(ctx.config.appearance or {}), ctx.config.theme, ctx.config.ui_font_scale)
        self.a = theme.appearance_of(ctx.config)
        self._loading = True
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Changes apply immediately — the whole window is your preview. Resume templates are "
                             "customised separately in Resume Library."))
        # colours
        colours = QGroupBox("Colours")
        cg = QGridLayout(colours)
        self.preset = QComboBox()
        self.preset.setAccessibleName("Colour preset")
        for key, (name, _l, _d) in theme.PRESETS.items():
            self.preset.addItem(name, key)
        self.mode = QComboBox()
        self.mode.setAccessibleName("Light or dark")
        for v, t in (("light", "Light"), ("dark", "Dark"), ("system", "Follow the system")):
            self.mode.addItem(t, v)
        cg.addWidget(QLabel("Preset:"), 0, 0)
        cg.addWidget(self.preset, 0, 1, 1, 2)
        cg.addWidget(QLabel("Mode:"), 1, 0)
        cg.addWidget(self.mode, 1, 1, 1, 2)
        self.swatches: dict[str, QPushButton] = {}
        for i, (slot, title) in enumerate(theme.COLOUR_SLOTS, start=2):
            b = QPushButton()
            b.setAccessibleName(f"{title} colour")
            b.setMinimumWidth(140)
            b.clicked.connect(lambda _=False, s=slot: self._pick(s))
            reset = button("Default", on_click=lambda s=slot: self._reset_colour(s))
            reset.setAccessibleName(f"Default {title} colour")
            cg.addWidget(QLabel(title + ":"), i, 0)
            cg.addWidget(b, i, 1)
            cg.addWidget(reset, i, 2)
            self.swatches[slot] = b
        lay.addWidget(colours)
        # text
        text = QGroupBox("Text")
        tf = QFormLayout(text)
        self.ui_font = QFontComboBox()
        self.ui_font.setAccessibleName("Interface font")
        self.heading_font = QFontComboBox()
        self.heading_font.setAccessibleName("Heading font")
        self.use_default_fonts = QCheckBox("Use the bundled fonts (Carlito and Caladea)")
        self.scale = QDoubleSpinBox()
        self.scale.setRange(0.85, 1.6)
        self.scale.setSingleStep(0.05)
        self.scale.setDecimals(2)
        self.scale.setAccessibleName("Text size")
        tf.addRow("", self.use_default_fonts)
        tf.addRow("Interface font:", self.ui_font)
        tf.addRow("Heading font:", self.heading_font)
        tf.addRow("Text size (×):", self.scale)
        lay.addWidget(text)
        # layout
        layout = QGroupBox("Layout")
        lf = QFormLayout(layout)
        self.density = QComboBox()
        self.density.setAccessibleName("Density")
        for v, t in (("compact", "Compact"), ("comfortable", "Comfortable"), ("spacious", "Spacious")):
            self.density.addItem(t, v)
        self.radius = QSpinBox()
        self.radius.setRange(0, 12)
        self.radius.setSuffix(" px")
        self.radius.setAccessibleName("Corner roundness")
        self.nav_style = QComboBox()
        self.nav_style.setAccessibleName("Navigation style")
        for v, t in theme.NAV_STYLES.items():
            self.nav_style.addItem(t, v)
        self.nav_side = QComboBox()
        self.nav_side.setAccessibleName("Navigation side")
        self.nav_side.addItem("Left", "left")
        self.nav_side.addItem("Right", "right")
        self.editor_layout = QComboBox()
        self.editor_layout.setAccessibleName("Record editor layout")
        self.editor_layout.addItem("List beside the editor", "side_by_side")
        self.editor_layout.addItem("List above the editor", "stacked")
        self.tagline = QCheckBox("Show the tagline under the name")
        self.start_page = QComboBox()
        self.start_page.setAccessibleName("Start page")
        for _g, items in NAV_SECTIONS:
            for key, title in items:
                self.start_page.addItem(title, key)
        lf.addRow("Density:", self.density)
        lf.addRow("Corner roundness:", self.radius)
        lf.addRow("Navigation:", self.nav_style)
        lf.addRow("Navigation side:", self.nav_side)
        lf.addRow("Record pages:", self.editor_layout)
        lf.addRow("", self.tagline)
        lf.addRow("Open on start:", self.start_page)
        lay.addWidget(layout)
        self.contrast = banner("", "ok")
        lay.addWidget(self.contrast)
        row = QHBoxLayout()
        row.addWidget(button("Reset everything", on_click=self.reset_all))
        row.addWidget(button("Export…", on_click=lambda: self.export_settings()))
        row.addWidget(button("Import…", on_click=lambda: self.import_settings()))
        row.addStretch(1)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Keep these settings")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Undo changes")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._apply)
        for w in (self.preset, self.mode, self.density, self.nav_style, self.nav_side, self.editor_layout,
                  self.start_page):
            w.currentIndexChanged.connect(self._changed)
        for w in (self.ui_font, self.heading_font):
            w.currentFontChanged.connect(self._changed)
        self.scale.valueChanged.connect(self._changed)
        self.radius.valueChanged.connect(self._changed)
        self.tagline.toggled.connect(self._changed)
        self.use_default_fonts.toggled.connect(self._fonts_toggled)
        self._load()

    # ------------------------------------------------------------------ state
    def _load(self) -> None:
        self._loading = True
        a = self.a
        self.preset.setCurrentIndex(max(0, self.preset.findData(a.preset)))
        self.mode.setCurrentIndex(max(0, self.mode.findData(self.ctx.config.theme)))
        self.use_default_fonts.setChecked(not a.ui_font and not a.heading_font)
        self.ui_font.setCurrentFont(QFont(a.ui_font or theme.UI_FONT))
        self.heading_font.setCurrentFont(QFont(a.heading_font or theme.HEADING_FONT))
        self.ui_font.setEnabled(not self.use_default_fonts.isChecked())
        self.heading_font.setEnabled(not self.use_default_fonts.isChecked())
        self.scale.setValue(self.ctx.config.ui_font_scale or 1.0)
        self.density.setCurrentIndex(max(0, self.density.findData(a.density)))
        self.radius.setValue(a.radius)
        self.nav_style.setCurrentIndex(max(0, self.nav_style.findData(a.nav_style)))
        self.nav_side.setCurrentIndex(max(0, self.nav_side.findData(a.nav_side)))
        self.editor_layout.setCurrentIndex(max(0, self.editor_layout.findData(a.editor_layout)))
        self.tagline.setChecked(a.show_tagline)
        self.start_page.setCurrentIndex(max(0, self.start_page.findData(a.start_page)))
        self._loading = False
        self._refresh_swatches()

    def _collect(self) -> None:
        a = self.a
        a.preset = self.preset.currentData()
        default_fonts = self.use_default_fonts.isChecked()
        a.ui_font = "" if default_fonts else self.ui_font.currentFont().family()
        a.heading_font = "" if default_fonts else self.heading_font.currentFont().family()
        a.density = self.density.currentData()
        a.radius = self.radius.value()
        a.nav_style = self.nav_style.currentData()
        a.nav_side = self.nav_side.currentData()
        a.editor_layout = self.editor_layout.currentData()
        a.show_tagline = self.tagline.isChecked()
        a.start_page = self.start_page.currentData()

    def _fonts_toggled(self, on: bool) -> None:
        self.ui_font.setEnabled(not on)
        self.heading_font.setEnabled(not on)
        self._changed()

    def _changed(self, *_args) -> None:
        if self._loading:
            return
        self._timer.start()

    def _apply(self) -> None:
        self._collect()
        cfg = self.ctx.config
        cfg.appearance = self.a.to_dict()
        cfg.theme = self.mode.currentData()
        cfg.ui_font_scale = round(self.scale.value(), 2)
        self.on_apply()
        self._refresh_swatches()

    def apply_now(self) -> None:
        """Apply pending changes immediately (used by tests and when the dialog closes)."""
        if self._timer.isActive():
            self._timer.stop()
        self._apply()

    def _palette(self) -> theme.Palette:
        return theme.palette_for(self.mode.currentData() or "light", self.a)

    def _refresh_swatches(self) -> None:
        p = self._palette()
        for slot, b in self.swatches.items():
            val = getattr(p, slot)
            custom = slot in self.a.colours
            b.setText(f"{val}{'  (custom)' if custom else ''}")
            ink = theme.readable_on(val, "#000000")
            b.setStyleSheet(f"background: {val}; color: {ink}; border: 1px solid #888888; padding: 4px 8px;")
        warnings = theme.contrast_warnings(p)
        if warnings:
            set_banner(self.contrast, "Some colours are hard to read: " + "; ".join(warnings[:4]) +
                       ". Choose different colours or press Default.", "warn")
        else:
            set_banner(self.contrast, "All text colours meet the WCAG AA contrast level.", "ok")

    def set_colour(self, slot: str, hex_colour: str | None) -> None:
        if hex_colour:
            self.a.colours[slot] = hex_colour.upper()
        else:
            self.a.colours.pop(slot, None)
        self.apply_now()

    def _pick(self, slot: str) -> None:
        current = QColor(getattr(self._palette(), slot))
        c = QColorDialog.getColor(current, self, f"Choose a colour — {dict(theme.COLOUR_SLOTS)[slot]}")
        if c.isValid():
            self.set_colour(slot, c.name())

    def _reset_colour(self, slot: str) -> None:
        self.set_colour(slot, None)

    def reset_all(self) -> None:
        self.a = theme.Appearance()
        self.ctx.config.ui_font_scale = 1.0
        self._load()
        self.apply_now()

    def export_settings(self, path: str | None = None) -> Path | None:
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Export appearance", "appearance.json", "JSON (*.json)")
            if not path:
                return None
        self._collect()
        data = {"format": "ris-appearance", "version": 1, "theme": self.mode.currentData(),
                "ui_font_scale": round(self.scale.value(), 2), "appearance": self.a.to_dict()}
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        return Path(path)

    def import_settings(self, path: str | None = None) -> bool:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Import appearance", "", "JSON (*.json)")
            if not path:
                return False
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if data.get("format") != "ris-appearance":
                raise ValueError("not an appearance file")
        except (OSError, ValueError) as exc:
            set_banner(self.contrast, f"That file could not be used ({exc}).", "bad")
            return False
        self.a = theme.Appearance.from_dict(data.get("appearance"))
        if data.get("theme") in ("light", "dark", "system"):
            self.ctx.config.theme = data["theme"]
        try:
            self.ctx.config.ui_font_scale = max(0.85, min(1.6, float(data.get("ui_font_scale", 1.0))))
        except (TypeError, ValueError):
            pass
        self._load()
        self.apply_now()
        return True

    # ------------------------------------------------------------------ closing
    def accept(self) -> None:
        self.apply_now()
        self._save()
        super().accept()

    def reject(self) -> None:
        appearance, mode, scale = self._original
        self.ctx.config.appearance = appearance
        self.ctx.config.theme = mode
        self.ctx.config.ui_font_scale = scale
        self.on_apply()
        super().reject()

    def _save(self) -> None:
        try:
            self.ctx.config.save()
        except OSError:
            pass
