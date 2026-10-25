"""Career Targets: Defence & Intelligence presets, organisation profiles and the user's own targets."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ris.composition.modes import get_mode
from ris.domain.enums import RecordKind, SummaryFocus, label
from ris.strings import PAGE_SUBTITLES
from ris.ui.widgets.common import Page, banner, button, esc
from ris.ui.widgets.records import CollectionWidget

ORG_NOTE = ("Organisation profiles summarise publicly known technical domains to help you choose emphasis. They are "
            "not official eligibility rules or internal requirements — always follow the actual vacancy notification.")


class TargetsPage(Page):
    key = "targets"

    def __init__(self, ctx) -> None:
        super().__init__(ctx, "Career Targets", PAGE_SUBTITLES["targets"], scrollable=False)
        self.tabs = QTabWidget()
        self.mine = CollectionWidget(ctx, [RecordKind.CAREER_TARGET], empty_hint=(
            "Create a target from a preset or organisation profile, or add your own. Targets steer section order, "
            "emphasis keywords, the summary and the template in Resume Studio."))
        self.tabs.addTab(self.mine, "My targets")
        # presets
        pw = QWidget()
        pl = QHBoxLayout(pw)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.preset_list = QListWidget()
        self.preset_list.setAccessibleName("Career presets")
        for p in ctx.presets.presets.values():
            it = QListWidgetItem(p.name)
            it.setData(Qt.ItemDataRole.UserRole, p.id)
            self.preset_list.addItem(it)
        self.preset_list.currentItemChanged.connect(lambda c, _p: self._show_preset(c))
        split.addWidget(self.preset_list)
        right = QWidget()
        rl = QVBoxLayout(right)
        self.preset_view = QTextBrowser()
        self.preset_view.setAccessibleName("Preset details")
        rl.addWidget(self.preset_view, 1)
        rl.addWidget(button("Create a target from this preset", "primary", on_click=self._from_preset))
        split.addWidget(right)
        split.setSizes([300, 600])
        pl.addWidget(split)
        self.tabs.addTab(pw, "Defence && Intelligence presets")
        # organisations
        ow = QWidget()
        ol = QVBoxLayout(ow)
        ol.addWidget(banner(ORG_NOTE, "info"))
        osplit = QSplitter(Qt.Orientation.Horizontal)
        self.org_list = QListWidget()
        self.org_list.setAccessibleName("Organisation profiles")
        for o in ctx.presets.organisations.values():
            it = QListWidgetItem(o.name)
            it.setData(Qt.ItemDataRole.UserRole, o.id)
            self.org_list.addItem(it)
        self.org_list.currentItemChanged.connect(lambda c, _p: self._show_org(c))
        osplit.addWidget(self.org_list)
        oright = QWidget()
        orl = QVBoxLayout(oright)
        self.org_view = QTextBrowser()
        self.org_view.setAccessibleName("Organisation details")
        orl.addWidget(self.org_view, 1)
        orl.addWidget(button("Create a target for this organisation", "primary", on_click=self._from_org))
        osplit.addWidget(oright)
        osplit.setSizes([320, 580])
        ol.addWidget(osplit, 1)
        self.tabs.addTab(ow, "Organisation profiles")
        self.body.addWidget(self.tabs, 1)
        self.preset_list.setCurrentRow(0)
        self.org_list.setCurrentRow(0)

    def kinds_of_interest(self) -> set[str]:
        return {"career_target"}

    def refresh(self) -> None:
        self.mine.reload()

    def _show_preset(self, item) -> None:
        if item is None:
            return
        p = self.ctx.presets.preset(item.data(Qt.ItemDataRole.UserRole))
        tpl = self.ctx.templates.find(p.template)
        self.preset_view.setHtml(
            f"<h2>{esc(p.name)}</h2><p>{esc(p.description)}</p>"
            f"<h3>Emphasis</h3><ul>{''.join(f'<li>{esc(e)}</li>' for e in p.emphasis)}</ul>"
            f"<h3>Keywords used for relevance</h3><p>{esc(', '.join(p.keywords))}</p>"
            f"<h3>Defaults</h3><p>Resume mode: <b>{esc(get_mode(p.mode).name)}</b><br>"
            f"Template: <b>{esc(tpl.name if tpl else p.template)}</b><br>"
            f"Summary focus: <b>{esc(label(SummaryFocus(p.summary_focus)) if p.summary_focus else '—')}</b></p>"
            "<p><i>Presets change emphasis and ordering only. They never add facts to your profile.</i></p>")

    def _show_org(self, item) -> None:
        if item is None:
            return
        o = self.ctx.presets.org(item.data(Qt.ItemDataRole.UserRole))
        sug = [self.ctx.presets.preset(s).name for s in o.suggested_presets if self.ctx.presets.preset(s)]
        self.org_view.setHtml(
            f"<h2>{esc(o.name)}</h2><p>{esc(o.parent)}</p>"
            f"<h3>Publicly known technical domains</h3><p>{esc(', '.join(o.domains))}</p>"
            f"<h3>Suggested presets</h3><ul>{''.join(f'<li>{esc(s)}</li>' for s in sug)}</ul>"
            f"<h3>Note</h3><p>{esc(o.notes)}</p>")

    def _create(self, data: dict) -> None:
        rec = self.ctx.repo.create(RecordKind.CAREER_TARGET, data)
        self.ctx.invalidate()
        self.tabs.setCurrentIndex(0)
        self.mine.reload(select_id=rec.id)
        self.ctx.say("Career target created. Adjust it, then choose it in Resume Studio.")

    def _from_preset(self) -> None:
        it = self.preset_list.currentItem()
        if it is None:
            return
        p = self.ctx.presets.preset(it.data(Qt.ItemDataRole.UserRole))
        self._create({"name": p.name, "preset_id": p.id, "description": p.description, "keywords": list(p.keywords),
                      "emphasis_areas": list(p.emphasis), "preferred_mode": p.mode, "preferred_template": p.template,
                      "summary_focus": p.summary_focus, "sector": "Defence & Intelligence"})

    def _from_org(self) -> None:
        it = self.org_list.currentItem()
        if it is None:
            return
        o = self.ctx.presets.org(it.data(Qt.ItemDataRole.UserRole))
        p = self.ctx.presets.preset(o.suggested_presets[0]) if o.suggested_presets else None
        data = {"name": o.name, "org_profile_id": o.id, "organisation": o.name, "sector": o.parent,
                "description": o.notes, "keywords": list(dict.fromkeys(list(o.domains) + (list(p.keywords) if p else []))),
                "emphasis_areas": list(p.emphasis) if p else []}
        if p:
            data.update({"preset_id": p.id, "preferred_mode": p.mode, "preferred_template": p.template,
                         "summary_focus": p.summary_focus})
        self._create(data)

    def focus_record(self, record_id: str) -> bool:
        self.tabs.setCurrentIndex(0)
        return self.mine.focus_record(record_id)

    def has_unsaved_changes(self) -> bool:
        return self.mine.editor.is_dirty()

    def maybe_save(self) -> bool:
        return self.mine.editor.maybe_save()
