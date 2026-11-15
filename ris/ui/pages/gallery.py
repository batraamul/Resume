"""Template Gallery: every resume layout with a thumbnail, filters, advice for this profile and a preview
rendered from the user's own data."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ris.composition.modes import MODES, get_mode
from ris.domain.enums import RecordKind
from ris.domain.models import Variant
from ris.intelligence.template_advice import (
    GALLERY_FILTERS,
    TemplateSuggestion,
    profile_traits,
    recommend_templates,
    template_tags,
)
from ris.strings import PAGE_SUBTITLES
from ris.ui.widgets.common import Card, Page, banner, button, chip, muted, repolish, set_banner
from ris.ui.widgets.pdf_preview import PdfPreview
from ris.ui.workers import run_task

CARD_WIDTH = 268


def preview_mode_for(spec) -> str:
    """The resume mode used when a template is shown or started on its own."""
    for m in spec.recommended_modes:
        if m in MODES:
            return m
    return "general_professional"


class TemplateThumbnail(QWidget):
    """A small schematic of a template drawn from its specification (header, headings, columns, colours)."""

    def __init__(self, spec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.spec = spec
        self.setFixedSize(QSize(132, 176))
        self.setAccessibleName(f"Layout sketch of {spec.name}")

    def paintEvent(self, _e) -> None:  # noqa: N802
        s = self.spec
        c = s.colours
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width() - 2, self.height() - 2
        page = QRectF(1, 1, w, h)
        p.setPen(QPen(QColor("#B8BEC6"), 1))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRect(page)
        accent, text, muted_c, rule = QColor(c.accent), QColor(c.text), QColor("#C9CED5"), QColor(c.rule)
        mx, y = 9.0, 9.0
        left, right = 1 + mx, 1 + w - mx
        # sidebar
        body_left, body_right = left, right
        if s.columns.enabled:
            sw = w * s.columns.width_frac
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c.sidebar_fill))
            if s.columns.side == "left":
                p.drawRect(QRectF(1.5, 1.5, sw, h - 1))
                body_left = 1 + sw + 6
            else:
                p.drawRect(QRectF(1 + w - sw - 0.5, 1.5, sw, h - 1))
                body_right = 1 + w - sw - 6
        p.setPen(Qt.PenStyle.NoPen)
        # header
        style = s.header.style
        if style in ("banner", "framed"):
            p.setBrush(QColor(c.banner_fill))
            p.drawRect(QRectF(1.5, 1.5, w - 1, 30))
            p.setBrush(QColor(c.banner_text))
            p.drawRect(QRectF(left, 9, w * 0.45, 6))
            p.drawRect(QRectF(left, 19, w * 0.6, 2.5))
            y = 38
        else:
            name_w = w * 0.48
            name_colour = accent if s.header.name_colour == "accent" else text
            hl, hr = (body_left, body_right) if style == "sidebar" else (left, right)
            x = hl + ((hr - hl) - name_w) / 2 if style == "centered" else hl
            p.setBrush(name_colour)
            p.drawRect(QRectF(x, y, name_w, 6.5))
            p.setBrush(muted_c)
            if style == "split":
                for i in range(3):
                    p.drawRect(QRectF(hr - 30, y + i * 4, 30, 2))
                p.drawRect(QRectF(hl, y + 10, w * 0.34, 2.5))
            elif style == "centered":
                p.drawRect(QRectF(hl + ((hr - hl) - w * 0.62) / 2, y + 10, w * 0.62, 2.5))
            else:
                p.drawRect(QRectF(hl, y + 10, min(w * 0.62, hr - hl), 2.5))
            y += 17
            if s.header.rule != "none":
                p.setBrush(rule)
                thick = 2.2 if s.header.rule == "thick" else 0.9
                p.drawRect(QRectF(hl, y, hr - hl, thick))
                if s.header.rule == "double":
                    p.drawRect(QRectF(hl, y + 2.2, hr - hl, 0.9))
                y += 6
        # sidebar content
        if s.columns.enabled:
            sx = 6.0 if s.columns.side == "left" else body_right + 9
            sw = w * s.columns.width_frac - 10
            sy = y if style != "sidebar" else 10
            for _block in range(4):
                p.setBrush(accent)
                p.drawRect(QRectF(sx, sy, sw * 0.6, 2.6))
                p.setBrush(muted_c)
                for i in range(4):
                    p.drawRect(QRectF(sx, sy + 6 + i * 4, sw * (0.9 if i % 2 == 0 else 0.7), 1.8))
                sy += 30
                if sy > h - 20:
                    break
        # main sections
        heading = s.heading.style
        head_colour = accent if s.heading.colour == "accent" else text
        label_w = 26 if heading == "margin_label" else 0
        chart_drawn = False
        while y < h - 20:
            bw = body_right - body_left
            if heading == "shaded_bar":
                p.setBrush(QColor(c.fill))
                p.drawRect(QRectF(body_left, y - 1.5, bw, 7))
                p.setBrush(head_colour)
                p.drawRect(QRectF(body_left + 2, y + 0.5, bw * 0.34, 3))
            elif heading == "left_bar":
                p.setBrush(head_colour)
                p.drawRect(QRectF(body_left, y - 1, 1.8, 6))
                p.drawRect(QRectF(body_left + 4, y + 0.5, bw * 0.34, 3))
            elif heading == "margin_label":
                p.setBrush(head_colour)
                p.drawRect(QRectF(body_left, y + 0.5, label_w - 5, 3))
            else:
                p.setBrush(head_colour)
                p.drawRect(QRectF(body_left, y + 0.5, bw * 0.36, 3))
                if heading in ("rule_below", "caps_rule"):
                    p.setBrush(rule)
                    p.drawRect(QRectF(body_left, y + 5.4, bw, 0.7))
            ty = y + (0 if heading == "margin_label" else 10)
            tx = body_left + label_w
            if s.graphics.enabled and not chart_drawn:
                chart_drawn = True
                pal = [QColor(x) for x in s.graphics.palette[:5]]
                for i, col in enumerate(pal):
                    bh = 8 + (i * 7) % 14
                    p.setBrush(col)
                    p.drawRect(QRectF(tx + i * 14, ty + 22 - bh, 9, bh))
                ty += 26
            else:
                gutter = 20 if s.entry.style == "date_left" else 0
                for i in range(4):
                    p.setBrush(muted_c)
                    if gutter and i == 0:
                        p.drawRect(QRectF(tx, ty + i * 4.4, gutter - 5, 1.9))
                    lw = (body_right - tx - gutter) * (1.0 if i < 2 else 0.82 if i == 2 else 0.55)
                    p.drawRect(QRectF(tx + gutter, ty + i * 4.4, lw, 1.9))
                ty += 18
            y = ty + 6
        p.end()


class TemplateCard(QFrame):
    def __init__(self, spec, suggestion: TemplateSuggestion | None, on_preview, on_apply, on_new,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.spec = spec
        self.setObjectName("TemplateCard")
        self.setProperty("recommended", "true" if suggestion else "false")
        self.setFixedWidth(CARD_WIDTH)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(6)
        top = QHBoxLayout()
        top.addStretch(1)
        top.addWidget(TemplateThumbnail(spec))
        top.addStretch(1)
        lay.addLayout(top)
        name = QLabel(spec.name)
        name.setObjectName("SectionTitle")
        name.setWordWrap(True)
        lay.addWidget(name)
        chips = QHBoxLayout()
        chips.setSpacing(4)
        if suggestion:
            chips.addWidget(chip("Recommended", "ok", suggestion.reason_text()))
        if spec.ats_safe:
            chips.addWidget(chip("ATS-safe", "ok", "Single column, no tables or graphics: safe for online portals"))
        if spec.columns.enabled:
            chips.addWidget(chip("Two-column", "info"))
        if spec.graphics.enabled:
            chips.addWidget(chip("Graphical", "warn", "For interviews and networking, not for online portals"))
        if not spec.builtin:
            chips.addWidget(chip("Custom", "info"))
        chips.addStretch(1)
        lay.addLayout(chips)
        desc = muted(spec.description)
        lay.addWidget(desc)
        modes = [MODES[m].name for m in spec.recommended_modes if m in MODES][:2]
        if modes:
            lay.addWidget(muted("Suits: " + "; ".join(modes)))
        if suggestion:
            why = QLabel(suggestion.reason_text())
            why.setWordWrap(True)
            lay.addWidget(why)
        lay.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(button("Preview", on_click=lambda: on_preview(spec.id),
                             tooltip="See this template with your own profile"))
        use = QToolButton()
        use.setText("Use template ▾")
        use.setProperty("kind", "primary")
        use.setAccessibleName(f"Use template {spec.name}")
        use.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(use)
        menu.addAction("Apply to the resume open in Resume Studio", lambda: on_apply(spec.id))
        menu.addAction("Start a new resume with this template", lambda: on_new(spec.id))
        use.setMenu(menu)
        row.addWidget(use)
        row.addStretch(1)
        lay.addLayout(row)


class TemplatePreviewDialog(QDialog):
    """A template rendered with the user's own profile."""

    def __init__(self, parent: QWidget | None, title: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 860)
        lay = QVBoxLayout(self)
        self.preview = PdfPreview(self)
        lay.addWidget(self.preview, 1)
        row = QHBoxLayout()
        row.addWidget(muted("Preview with your own profile. Nothing is saved or exported."), 1)
        row.addWidget(button("Close", on_click=self.accept))
        lay.addLayout(row)
        self.alive = True
        self.finished.connect(lambda _r: setattr(self, "alive", False))


class GalleryPage(Page):
    key = "gallery"

    def __init__(self, ctx, on_apply=None, on_new=None) -> None:
        super().__init__(ctx, "Template Gallery", PAGE_SUBTITLES["gallery"])
        self.on_apply = on_apply
        self.on_new = on_new
        self.cards: list[TemplateCard] = []
        self._shown: list[TemplateCard] = []
        self.suggestions: dict[str, TemplateSuggestion] = {}
        self._columns = 0
        self.synchronous_preview = False  # tests render inline
        self.last_preview: TemplatePreviewDialog | None = None
        bar = Card()
        row = QHBoxLayout()
        row.addWidget(QLabel("Show:"))
        self.filter = QComboBox()
        self.filter.setAccessibleName("Template filter")
        for k, label in GALLERY_FILTERS:
            self.filter.addItem(label, k)
        self.filter.currentIndexChanged.connect(lambda _i: self._apply_filter())
        row.addWidget(self.filter)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search templates by name or description…")
        self.search.setAccessibleName("Search templates")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self._apply_filter())
        row.addWidget(self.search, 1)
        self.count = muted("", wrap=False)
        row.addWidget(self.count)
        bar.body.addLayout(row)
        self.advice = banner("", "info")
        bar.add(self.advice)
        self.body.addWidget(bar)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.body.addWidget(self.grid_host)
        self.empty = muted("No template matches this filter.")
        self.body.addWidget(self.empty)
        self.body.addStretch(1)

    def kinds_of_interest(self) -> set[str] | None:
        return None

    # ------------------------------------------------------------------ data
    def refresh(self) -> None:
        self.ctx.templates.reload()
        templates = self.ctx.templates.list()
        snap = self.ctx.snapshot()
        suggestions = recommend_templates(snap, templates, today=self.ctx.today)
        self.suggestions = {s.template_id: s for s in suggestions}
        traits = profile_traits(snap, self.ctx.today)
        if traits.is_empty:
            set_banner(self.advice, "Your profile is still empty, so the suggestions are general starting points. "
                                    "Add experience, projects and publications for advice that fits you.", "info")
        else:
            facts = []
            if traits.years >= 1:
                facts.append(f"{traits.years:.0f} years of experience")
            if traits.government:
                facts.append("government / defence / public-sector service")
            if traits.publications:
                facts.append(f"{traits.publications} publication(s)")
            if traits.projects:
                facts.append(f"{traits.projects} project(s)")
            if traits.deputation_vacancy:
                facts.append("a deputation vacancy in your list")
            set_banner(self.advice, f"{len(suggestions)} template(s) are recommended from your profile "
                                    f"({', '.join(facts) or 'recorded facts'}). Hover over 'Recommended' on a card "
                                    "for the reason. Advice only — a vacancy notice's prescribed form always "
                                    "prevails.", "info")
        for card in self.cards:
            card.setParent(None)
            card.deleteLater()
        rank = {s.template_id: i for i, s in enumerate(suggestions)}
        ordered = sorted(templates, key=lambda t: (rank.get(t.id, 999),))
        self.cards = [TemplateCard(t, self.suggestions.get(t.id), self.preview_template, self.apply_template,
                                   self.new_with_template, parent=self.grid_host) for t in ordered]
        for card in self.cards:
            repolish(card)
        self._columns = 0
        self._apply_filter()

    def visible_ids(self) -> list[str]:
        return [c.spec.id for c in self._shown]

    def _matches(self, card: TemplateCard, key: str, words: list[str]) -> bool:
        spec = card.spec
        if key == "recommended":
            if spec.id not in self.suggestions:
                return False
        elif key not in template_tags(spec):
            return False
        hay = f"{spec.name} {spec.description} {spec.family}".lower()
        return all(w in hay for w in words)

    def _apply_filter(self) -> None:
        key = self.filter.currentData() or "all"
        words = self.search.text().lower().split()
        shown = [c for c in self.cards if self._matches(c, key, words)]
        self._shown = shown
        self._layout_cards(shown, force=True)
        for c in self.cards:
            c.setVisible(c in shown)
        self.count.setText(f"{len(shown)} of {len(self.cards)} templates")
        self.empty.setVisible(not shown)

    def _layout_cards(self, shown: list[TemplateCard] | None = None, force: bool = False) -> None:
        cols = max(1, (self.grid_host.width() + 12) // (CARD_WIDTH + 12))
        if not force and cols == self._columns:
            return
        self._columns = cols
        if shown is None:
            shown = self._shown
        while self.grid.count():
            self.grid.takeAt(0)
        for i, card in enumerate(shown):
            self.grid.addWidget(card, i // cols, i % cols)

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._layout_cards()

    # ------------------------------------------------------------------ actions
    def apply_template(self, template_id: str) -> None:
        if self.on_apply:
            self.on_apply(template_id)

    def new_with_template(self, template_id: str) -> None:
        if self.on_new:
            self.on_new(template_id)

    def _preview_variant(self, template_id: str) -> tuple[Variant, str | None]:
        """Settings for the preview: the user's first resume variant restyled, or the template's own mode."""
        variants = self.ctx.snapshot().of(RecordKind.VARIANT)
        spec = self.ctx.templates.get(template_id)
        if variants and (not spec.recommended_modes or variants[0].data.mode in spec.recommended_modes):
            return variants[0].data.model_copy(update={"template_id": template_id}), variants[0].id
        mode = get_mode(preview_mode_for(spec))
        return Variant(name=spec.name, mode=mode.id, template_id=template_id, length=mode.default_length), None

    def preview_template(self, template_id: str) -> TemplatePreviewDialog:
        spec = self.ctx.templates.get(template_id)
        dlg = TemplatePreviewDialog(self, f"Preview — {spec.name}")
        dlg.preview.info.setText("Rendering preview…")
        self.last_preview = dlg
        variant, variant_id = self._preview_variant(template_id)
        svc = self.ctx.export_service()
        snap = self.ctx.snapshot()

        def work():
            comp = svc.compose(variant, snap, variant_id=variant_id)
            data, pages, _used, _warnings = svc.preview_pdf(comp.doc, comp.spec, engine="builtin")
            return data, pages

        def done(result) -> None:
            if dlg.alive:
                data, pages = result
                dlg.preview.set_pdf(data, f"{spec.name} · {pages} page(s) · {get_mode(variant.mode).name}")

        def failed(msg: str, _detail: str) -> None:
            if dlg.alive:
                dlg.preview.clear("Preview failed: " + msg)

        run_task(work, done, failed, synchronous=self.synchronous_preview)
        if not self.synchronous_preview:
            dlg.show()
        return dlg
