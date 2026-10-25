"""Record editor and collection browser used by every profile section."""

from __future__ import annotations

import logging
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ris.domain import registry
from ris.domain.enums import Confidentiality, Origin, RecordKind, SummaryFocus, Verification, choices, label
from ris.errors import ConcurrencyConflict, RISError, ValidationFailed
from ris.ui.dialogs import PayloadPreviewDialog, SuggestionDialog, status_text
from ris.ui.widgets.common import (
    TONE_CONFIDENTIALITY,
    TONE_VERIFICATION,
    banner,
    button,
    chip,
    confirm,
    error,
    info,
    muted,
    scroll,
    set_banner,
    set_chip,
)
from ris.ui.widgets.form import RecordForm

log = logging.getLogger(__name__)

CHILD_KINDS: dict[RecordKind, list[RecordKind]] = {
    RecordKind.POSITION: [RecordKind.ASSIGNMENT, RecordKind.BULLET],
    RecordKind.ASSIGNMENT: [RecordKind.BULLET],
    RecordKind.PROJECT: [RecordKind.BULLET],
    RecordKind.ACTIVITY: [RecordKind.BULLET],
    RecordKind.CUSTOM_SECTION: [RecordKind.CUSTOM_ENTRY],
}

CONF_HELP = {
    "public": "Public: already in the public domain; may appear anywhere, including redacted portfolios.",
    "approved": "Approved for professional use: you have checked it may appear in resumes you send.",
    "review": "Requires review: not exported until you complete a disclosure review.",
    "confidential": "Confidential: never exported, never sent to AI providers, excluded from cloud copies by default.",
}
VER_HELP = {
    "unconfirmed": "Awaiting confirmation: not exported until you confirm it is accurate.",
    "confirmed": "Confirmed by you.",
    "evidenced": "Confirmed, and you hold supporting evidence (office order, certificate, DOI…).",
}


class RecordEditor(QWidget):
    saved = Signal(str)          # record id
    deleted = Signal(str)

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.record = None
        self.kind: RecordKind | None = None
        self.parent_id: str | None = None
        self.form: RecordForm | None = None
        self._forms: dict[RecordKind, RecordForm] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        head = QHBoxLayout()
        self.title = QLabel("Select a record")
        self.title.setObjectName("SectionTitle")
        self.title.setWordWrap(True)
        head.addWidget(self.title, 1)
        self.chip_ver = chip("", "info")
        self.chip_conf = chip("", "info")
        self.chip_origin = chip("", "info")
        for c in (self.chip_origin, self.chip_ver, self.chip_conf):
            head.addWidget(c)
        lay.addLayout(head)
        self.banner = banner("", "info")
        self.banner.setVisible(False)
        lay.addWidget(self.banner)
        status = QHBoxLayout()
        self.ver_label = QLabel("Verification:")
        status.addWidget(self.ver_label)
        self.ver = QComboBox()
        for v, t in choices(Verification):
            self.ver.addItem(t, v)
            self.ver.setItemData(self.ver.count() - 1, VER_HELP[v], Qt.ItemDataRole.ToolTipRole)
        self.ver.setAccessibleName("Verification status")
        self.ver.setToolTip("\n".join(VER_HELP.values()))
        status.addWidget(self.ver)
        status.addSpacing(12)
        self.conf_label = QLabel("Disclosure:")
        status.addWidget(self.conf_label)
        self.conf = QComboBox()
        for v, t in choices(Confidentiality):
            self.conf.addItem(t, v)
            self.conf.setItemData(self.conf.count() - 1, CONF_HELP[v], Qt.ItemDataRole.ToolTipRole)
        self.conf.setAccessibleName("Disclosure classification")
        self.conf.setToolTip("\n".join(CONF_HELP.values()))
        status.addWidget(self.conf)
        status.addStretch(1)
        lay.addLayout(status)
        self.ver.currentIndexChanged.connect(self._status_changed)
        self.conf.currentIndexChanged.connect(self._status_changed)
        self.form_host = QWidget()
        self.form_layout = QVBoxLayout(self.form_host)
        self.form_layout.setContentsMargins(0, 0, 4, 0)
        lay.addWidget(scroll(self.form_host), 1)
        self.meta = muted("")
        lay.addWidget(self.meta)
        foot = QHBoxLayout()
        self.extra_actions = QHBoxLayout()
        foot.addLayout(self.extra_actions)
        foot.addStretch(1)
        self.b_revert = button("Revert", tooltip="Discard unsaved changes", on_click=self.revert)
        self.b_save = button("Save", "primary", tooltip="Save this record", on_click=self.save)
        foot.addWidget(self.b_revert)
        foot.addWidget(self.b_save)
        lay.addLayout(foot)
        self._dirty = False
        self._loading = False
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self.save,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.set_record(None)

    # ------------------------------------------------------------------ loading
    def _form_for(self, kind: RecordKind) -> RecordForm:
        f = self._forms.get(kind)
        if f is None:
            f = RecordForm(self.ctx, kind)
            f.changed.connect(self._on_changed)
            self._forms[kind] = f
            self.form_layout.addWidget(f)
        return f

    def _show_form(self, kind: RecordKind | None) -> None:
        for k, f in self._forms.items():
            f.setVisible(k == kind)
        self.form = self._form_for(kind) if kind is not None else None
        if self.form is not None:
            self.form.setVisible(True)

    def reset_forms(self) -> None:
        """Rebuild forms (reference lists such as projects or templates may have changed)."""
        for f in self._forms.values():
            f.setParent(None)
            f.deleteLater()
        self._forms.clear()

    def set_record(self, record) -> None:
        self._loading = True
        try:
            self.record = record
            self.kind = record.kind if record is not None else None
            self.parent_id = record.parent_id if record is not None else None
            self._show_form(self.kind)
            enabled = record is not None
            for w in (self.ver, self.conf, self.b_save, self.b_revert):
                w.setEnabled(enabled)
            for w in (self.ver, self.conf, self.ver_label, self.conf_label):
                w.setVisible(record is not None)
            if record is None:
                self.title.setText("Select a record, or add a new one")
                for c in (self.chip_ver, self.chip_conf, self.chip_origin):
                    c.setVisible(False)
                self.banner.setVisible(False)
                self.meta.setText("")
                self._set_extra([])
                return
            self.form.set_data(record.payload())
            self._select(self.ver, record.verification.value)
            self._select(self.conf, record.confidentiality.value)
            self.title.setText(record.title or f"Untitled {label(record.kind).lower()}")
            self._update_chips(record.verification.value, record.confidentiality.value, record.origin.value)
            self.meta.setText(f"Revision {record.revision} · last changed "
                              f"{record.updated_at[:16].replace('T', ' ')} UTC · {label(record.origin)}")
            self._contextual_banner()
            self._set_extra(self._actions_for(record.kind))
            self._set_status_enabled(registry.info(record.kind).is_fact)
        finally:
            self._loading = False
            self._dirty = False
            self._update_save()

    def start_new(self, kind: RecordKind, parent_id: str | None = None, defaults: dict | None = None) -> None:
        self._loading = True
        try:
            self.record = None
            self.kind = RecordKind(kind)
            self.parent_id = parent_id
            self._show_form(self.kind)
            model = registry.model_for(self.kind)
            data = model().model_dump(mode="json")
            data.update(defaults or {})
            self.form.set_data(data)
            self._select(self.ver, Verification.CONFIRMED.value)
            self._select(self.conf, registry.default_confidentiality(self.kind, Origin.MANUAL).value)
            parent = self.ctx.repo.find(parent_id) if parent_id else None
            self.title.setText(f"New {label(self.kind).lower()}" + (f" — {parent.title}" if parent else ""))
            self._update_chips(Verification.CONFIRMED.value, self.conf.currentData(), "manual")
            self.meta.setText("Not saved yet.")
            for w in (self.ver, self.conf, self.b_save, self.b_revert):
                w.setEnabled(True)
            self.conf.setVisible(True)
            self.conf_label.setVisible(True)
            self._set_status_enabled(registry.info(self.kind).is_fact)
            set_banner(self.banner, "Enter only facts you can support. Work-related records start as "
                       "'Requires review' until you decide they may appear in external documents.", "info")
            self._set_extra(self._actions_for(self.kind, new=True))
        finally:
            self._loading = False
            self._dirty = True
            self._update_save()
        first = next(iter(self.form.editors.values()), None)
        if first is not None:
            first.setFocus()

    def _set_status_enabled(self, is_fact: bool) -> None:
        self.ver.setEnabled(is_fact)
        self.ver.setVisible(is_fact)
        self.ver_label.setVisible(is_fact)
        self.chip_ver.setVisible(is_fact)

    @staticmethod
    def _select(cb: QComboBox, value: str) -> None:
        idx = cb.findData(value)
        cb.setCurrentIndex(max(idx, 0))

    def _update_chips(self, ver: str, conf: str, origin: str) -> None:
        set_chip(self.chip_ver, label(Verification(ver)), TONE_VERIFICATION.get(ver, "info"))
        set_chip(self.chip_conf, {"approved": "Approved"}.get(conf, label(Confidentiality(conf)).split(" — ")[0]),
                 TONE_CONFIDENTIALITY.get(conf, "info"))
        set_chip(self.chip_origin, label(Origin(origin)), "info")
        for c in (self.chip_ver, self.chip_conf):
            c.setVisible(True)
        self.chip_origin.setVisible(origin in ("imported", "preloaded", "sample", "synced", "generated"))

    def _contextual_banner(self) -> None:
        r = self.record
        if r is None:
            self.banner.setVisible(False)
            return
        if r.confidentiality == Confidentiality.CONFIDENTIAL:
            set_banner(self.banner, "Confidential: excluded from every exported document, AI request and (by "
                       "default) cloud copy.", "bad")
        elif r.origin in (Origin.PRELOADED, Origin.IMPORTED) and r.verification == Verification.UNCONFIRMED:
            set_banner(self.banner, "Preliminary information. Check every detail against your records, correct it, "
                       "then set Verification to Confirmed. Nothing unconfirmed is exported.", "warn")
        elif r.verification == Verification.UNCONFIRMED and registry.info(r.kind).is_fact:
            set_banner(self.banner, "Awaiting your confirmation — this record is not exported until you confirm it.",
                       "warn")
        elif r.confidentiality == Confidentiality.REVIEW and registry.info(r.kind).is_fact:
            set_banner(self.banner, "Requires a disclosure review — decide whether it may appear in external "
                       "documents (Approved for professional use) or must stay private (Confidential).", "warn")
        else:
            self.banner.setVisible(False)

    # ------------------------------------------------------------------ actions
    def _set_extra(self, widgets: list[QWidget]) -> None:
        while self.extra_actions.count():
            it = self.extra_actions.takeAt(0)
            if it.widget():
                it.widget().setParent(None)
        for w in widgets:
            self.extra_actions.addWidget(w)

    def _actions_for(self, kind: RecordKind, new: bool = False) -> list[QWidget]:
        out: list[QWidget] = []
        if kind == RecordKind.BULLET and not new:
            tb = QToolButton()
            tb.setText("Improve wording ▾")
            tb.setAccessibleName("Improve wording")
            tb.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(tb)
            menu.addAction("Tighten wording (rules engine, offline)", lambda: self.suggest(translate=False))
            menu.addAction("Explain domain terms for engineering readers (offline)",
                           lambda: self.suggest(translate=True))
            if self.ctx.config.ai_provider != "off":
                menu.addSeparator()
                menu.addAction("Ask external AI provider…", self.suggest_external)
            tb.setMenu(menu)
            out.append(tb)
        if kind == RecordKind.SUMMARY:
            out.append(button("Draft from confirmed facts", tooltip="A factual draft from your confirmed records only",
                              on_click=self.draft_summary))
        if not new and self.record is not None:
            out.append(button("Delete", "danger", tooltip="Move to Recently deleted (can be restored)",
                              on_click=self.delete))
        return out

    def suggest(self, translate: bool = False) -> None:
        if self.record is None or self.record.kind != RecordKind.BULLET:
            return
        if self.is_dirty() and not self.save():
            return
        from ris.intelligence.rewriting import default_glossary, rewrite_bullet

        rec = self.ctx.repo.get(self.record.id)
        parent = self.ctx.repo.find(rec.parent_id) if rec.parent_id else None
        glossary = default_glossary()
        glossary.update(self.ctx.settings.get("glossary.overrides") or {})
        s = rewrite_bullet(rec, parent, translate=translate, glossary=glossary)
        if s.unchanged and not s.missing_metrics:
            info(self, "Wording assistant", "The rules engine has no change to suggest for this statement.")
            return
        self._review_suggestion(rec, s, "Suggestions come from the built-in rules engine, which works offline and "
                                        "only rearranges facts you recorded. It is not a generative AI model.")

    def suggest_external(self) -> None:
        if self.record is None:
            return
        if self.is_dirty() and not self.save():
            return
        from ris.ai.external import make_provider
        from ris.ai.payload import build_rewrite_payload

        rec = self.ctx.repo.get(self.record.id)
        try:
            payload = build_rewrite_payload(rec, self.ctx.snapshot())
            provider = make_provider(self.ctx.config.ai_provider, self.ctx.config.ai_endpoint,
                                     self.ctx.config.ai_model, self.ctx.secrets.get("ai_api_key"))
        except RISError as exc:
            error(self, "External AI", exc.user_message)
            return
        if PayloadPreviewDialog(self, provider.describe(), provider.request_preview(payload)).exec() != 1:
            return
        from ris.ui.workers import run_task

        self.ctx.say("Waiting for the AI provider…", 0)

        def done(s) -> None:
            self.ctx.say("Suggestion received — review it before approving.")
            self._review_suggestion(rec, s, f"Suggested by an external AI model ({provider.describe()}). It may be "
                                            "wrong: check every word against your records.")

        run_task(lambda: provider.rewrite(payload), done,
                 lambda m, d: (self.ctx.say(""), error(self, "External AI", m)))

    def _review_suggestion(self, rec, s, note: str) -> None:
        parent = self.ctx.repo.find(rec.parent_id) if rec.parent_id else None
        involvement = rec.data.involvement or (getattr(parent.data, "involvement", None) if parent else None)
        dlg = SuggestionDialog(self, s, involvement=involvement, generator_note=note)
        if dlg.exec() != 1:
            return
        new_text = dlg.approved_text()
        if new_text == rec.data.text.strip():
            return
        notes = rec.data.notes
        stamp = date.today().isoformat()
        notes = (notes + "\n" if notes else "") + f"Previous wording ({stamp}): {rec.data.text}"
        try:
            updated = self.ctx.repo.update(rec.id, {**rec.payload(), "text": new_text, "notes": notes},
                                           expected_revision=rec.revision)
        except RISError as exc:
            error(self, "Could not save", exc.user_message)
            return
        self.ctx.say("Approved wording saved. The previous wording is kept in the record's private notes.")
        self.set_record(updated)
        self.saved.emit(updated.id)

    def draft_summary(self) -> None:
        from ris.intelligence.rewriting import draft_summary

        focus = self.form.value("focus") if self.form else ""
        s = draft_summary(self.ctx.snapshot(), label(focus, SummaryFocus) if focus else "")
        if not s.revised:
            info(self, "Draft summary", "Confirm your current position, qualifications or skills first; the draft "
                                        "uses confirmed records only.")
            return
        s.original = self.form.value("text") or ""
        dlg = SuggestionDialog(self, s, title="Draft summary",
                               generator_note="Drafted by the rules engine from confirmed records only. Edit freely; "
                                              "nothing is saved until you choose Save.")
        if dlg.exec() == 1:
            self.form.set_value("text", dlg.approved_text())

    def delete(self) -> None:
        if self.record is None:
            return
        kids = self.ctx.repo.children(self.record.id)
        extra = f" It has {len(kids)} linked item(s), which are moved too." if kids else ""
        if not confirm(self, "Delete record", f"Move '{self.record.title or 'this record'}' to Recently deleted?{extra}",
                       ok="Delete", destructive=True,
                       detail="You can restore it from Backup & Restore → Recently deleted."):
            return
        rid = self.record.id
        self.ctx.repo.delete(rid)
        self.ctx.say("Moved to Recently deleted.")
        self.set_record(None)
        self.deleted.emit(rid)

    # ------------------------------------------------------------------ dirty tracking & saving
    def _on_changed(self) -> None:
        if not self._loading:
            self._dirty = True
            self._update_save()

    def _status_changed(self) -> None:
        if self._loading:
            return
        self._dirty = True
        self._update_chips(self.ver.currentData(), self.conf.currentData(),
                           self.record.origin.value if self.record else "manual")
        self._update_save()

    def _update_save(self) -> None:
        has = self.kind is not None
        self.b_save.setEnabled(has and self._dirty)
        self.b_revert.setEnabled(has and self._dirty)
        self.b_save.setText("Save" + (" *" if self._dirty and has else ""))

    def is_dirty(self) -> bool:
        return self.kind is not None and self._dirty

    def revert(self) -> None:
        if self.record is not None:
            self.set_record(self.ctx.repo.get(self.record.id))
        elif self.kind is not None:
            self.start_new(self.kind, self.parent_id)

    def save(self) -> bool:
        if self.kind is None or self.form is None:
            return False
        data = self.form.data()
        ver = self.ver.currentData()
        conf = self.conf.currentData()
        try:
            if self.record is None:
                rec = self.ctx.repo.create(self.kind, data, parent_id=self.parent_id, verification=ver,
                                           confidentiality=conf, origin=Origin.MANUAL)
            else:
                rec = self.ctx.repo.update(self.record.id, data, verification=ver, confidentiality=conf,
                                           expected_revision=self.record.revision)
        except ValidationFailed as exc:
            rest = self.form.show_errors(exc.errors)
            set_banner(self.banner, "Please correct the highlighted fields: " + "; ".join(exc.errors)
                       + ("" if not rest else ""), "bad")
            return False
        except ConcurrencyConflict as exc:
            box = QMessageBox(self)
            box.setWindowTitle("Record changed elsewhere")
            box.setText(exc.user_message)
            reload_b = box.addButton("Reload (discard my edits)", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton("Keep editing", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is reload_b:
                self.set_record(self.ctx.repo.get(self.record.id))
            return False
        except RISError as exc:
            error(self, "Could not save", exc.user_message, exc.detail)
            return False
        self.ctx.say("Saved.", 3000)
        self.set_record(rec)
        self.saved.emit(rec.id)
        return True

    def maybe_save(self) -> bool:
        """Ask about unsaved changes. Returns False if the user cancels."""
        if not self.is_dirty():
            return True
        box = QMessageBox(self)
        box.setWindowTitle("Unsaved changes")
        box.setText("Save the changes to this record?")
        save_b = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save_b)
        box.exec()
        if box.clickedButton() is save_b:
            return self.save()
        if box.clickedButton() is discard:
            self._dirty = False
            self._update_save()
            return True
        return False


class CollectionWidget(QWidget):
    """Tree of records (with nested statements) and an editor."""

    def __init__(self, ctx, kinds: list[RecordKind], *, add_labels: dict[RecordKind, str] | None = None,
                 empty_hint: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.kinds = [RecordKind(k) for k in kinds]
        self.add_labels = add_labels or {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        ll.setSpacing(6)
        filt = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter…")
        self.search.setAccessibleName("Filter records")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self.reload())
        self.status_filter = QComboBox()
        self.status_filter.setAccessibleName("Status filter")
        for text, val in (("All", ""), ("Awaiting confirmation", "unconfirmed"), ("Requires review", "review"),
                          ("Confidential", "confidential")):
            self.status_filter.addItem(text, val)
        self.status_filter.currentIndexChanged.connect(lambda _i: self.reload())
        filt.addWidget(self.search, 1)
        filt.addWidget(self.status_filter)
        ll.addLayout(filt)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Record", "Status"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setAccessibleName("Records")
        self.tree.setUniformRowHeights(False)
        self.tree.currentItemChanged.connect(self._current_changed)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        ll.addWidget(self.tree, 1)
        self.empty = muted(empty_hint)
        self.empty.setVisible(False)
        ll.addWidget(self.empty)
        bar = QHBoxLayout()
        self.b_add = QToolButton()
        self.b_add.setText("Add ▾" if len(self.kinds) > 1 else f"Add {self.add_labels.get(self.kinds[0], label(self.kinds[0]).lower())}")
        self.b_add.setAccessibleName("Add record")
        self.b_add.setToolTip("Add a record (Ctrl+N)")
        if len(self.kinds) > 1:
            m = QMenu(self.b_add)
            for k in self.kinds:
                m.addAction(self.add_labels.get(k, label(k)), lambda k=k: self.add(k))
            self.b_add.setMenu(m)
            self.b_add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        else:
            self.b_add.clicked.connect(lambda: self.add(self.kinds[0]))
        bar.addWidget(self.b_add)
        self.b_child = QToolButton()
        self.b_child.setText("Add linked item ▾")
        self.b_child.setAccessibleName("Add linked item")
        self.b_child.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.b_child.setMenu(QMenu(self.b_child))
        bar.addWidget(self.b_child)
        self.b_up = QToolButton()
        self.b_up.setText("↑")
        self.b_up.setToolTip("Move up (Alt+Up)")
        self.b_up.setAccessibleName("Move up")
        self.b_up.clicked.connect(lambda: self.move(-1))
        self.b_down = QToolButton()
        self.b_down.setText("↓")
        self.b_down.setToolTip("Move down (Alt+Down)")
        self.b_down.setAccessibleName("Move down")
        self.b_down.clicked.connect(lambda: self.move(1))
        bar.addWidget(self.b_up)
        bar.addWidget(self.b_down)
        bar.addStretch(1)
        self.b_bulk = QToolButton()
        self.b_bulk.setText("Selected ▾")
        self.b_bulk.setAccessibleName("Actions for selected records")
        self.b_bulk.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        bm = QMenu(self.b_bulk)
        bm.addAction("Confirm selected", lambda: self.bulk_verify(Verification.CONFIRMED))
        bm.addAction("Confirm selected (with evidence)", lambda: self.bulk_verify(Verification.EVIDENCED))
        bm.addAction("Mark selected as awaiting confirmation", lambda: self.bulk_verify(Verification.UNCONFIRMED))
        bm.addSeparator()
        for v, t in choices(Confidentiality):
            bm.addAction(f"Classify: {t}", lambda v=v: self.bulk_classify(v))
        bm.addSeparator()
        bm.addAction("Duplicate", self.duplicate)
        bm.addAction("Delete selected…", self.bulk_delete)
        self.b_bulk.setMenu(bm)
        bar.addWidget(self.b_bulk)
        ll.addLayout(bar)
        split.addWidget(left)
        self.editor = RecordEditor(ctx)
        self.editor.saved.connect(self._after_save)
        self.editor.deleted.connect(lambda _rid: self.reload())
        split.addWidget(self.editor)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        split.setSizes([380, 620])
        lay.addWidget(split)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=lambda: self.add(self.kinds[0]),
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence("Alt+Up"), self.tree, activated=lambda: self.move(-1),
                  context=Qt.ShortcutContext.WidgetShortcut)
        QShortcut(QKeySequence("Alt+Down"), self.tree, activated=lambda: self.move(1),
                  context=Qt.ShortcutContext.WidgetShortcut)
        QShortcut(QKeySequence.StandardKey.Delete, self.tree, activated=self.bulk_delete,
                  context=Qt.ShortcutContext.WidgetShortcut)
        self._suppress = False

    # ------------------------------------------------------------------ tree
    def all_kinds(self) -> set[str]:
        out = {k.value for k in self.kinds}
        stack = list(self.kinds)
        while stack:
            k = stack.pop()
            for c in CHILD_KINDS.get(k, []):
                if c.value not in out:
                    out.add(c.value)
                    stack.append(c)
        return out

    def _matches(self, rec, text: str, status: str) -> bool:
        if status == "unconfirmed" and not (rec.verification == Verification.UNCONFIRMED
                                            and registry.info(rec.kind).is_fact):
            return False
        if status in ("review", "confidential") and rec.confidentiality.value != status:
            return False
        if text:
            return text in (rec.data.search_text() or "").lower()
        return True

    def reload(self, select_id: str | None = None) -> None:
        if not self.ctx.has_workspace:
            return
        current = select_id or (self.editor.record.id if self.editor.record else None)
        self._suppress = True
        self.tree.clear()
        snap = self.ctx.snapshot()
        text = self.search.text().strip().lower()
        status = self.status_filter.currentData() or ""
        items: dict[str, QTreeWidgetItem] = {}

        def add(rec, parent_item) -> bool:
            kids = [k for k in snap.kids(rec.id) if k.kind in CHILD_KINDS.get(rec.kind, [])]
            it = QTreeWidgetItem()
            title = rec.title or f"(untitled {label(rec.kind).lower()})"
            if rec.kind == RecordKind.BULLET:
                title = "• " + title
            elif rec.kind == RecordKind.ASSIGNMENT:
                title = "↳ " + title
            it.setText(0, title)
            it.setToolTip(0, (rec.subtitle + "\n" if rec.subtitle else "") + label(rec.kind))
            st = status_text(rec) if registry.info(rec.kind).is_fact else ""
            it.setText(1, st)
            it.setData(0, Qt.ItemDataRole.UserRole, rec.id)
            it.setData(0, Qt.ItemDataRole.AccessibleTextRole, f"{label(rec.kind)}: {title}. {st}")
            if rec.subtitle:
                it.setText(0, f"{title}\n{rec.subtitle}")
            visible_kid = False
            for k in kids:
                visible_kid = add(k, it) or visible_kid
            me = self._matches(rec, text, status)
            if me or visible_kid:
                if parent_item is None:
                    self.tree.addTopLevelItem(it)
                else:
                    parent_item.addChild(it)
                items[rec.id] = it
                return True
            return False

        for kind in self.kinds:
            for rec in snap.of(kind):
                if rec.parent_id is None or snap.get(rec.parent_id) is None:
                    add(rec, None)
        self.tree.expandAll()
        self._suppress = False
        self.empty.setVisible(self.tree.topLevelItemCount() == 0)
        if current and current in items:
            self.tree.setCurrentItem(items[current])
        elif self.editor.record is not None and self.editor.record.id not in items and not self.editor.is_dirty():
            self.editor.set_record(None)
        self._update_child_menu()

    def selected_ids(self) -> list[str]:
        return [it.data(0, Qt.ItemDataRole.UserRole) for it in self.tree.selectedItems()]

    def _current_changed(self, cur: QTreeWidgetItem | None, prev: QTreeWidgetItem | None) -> None:
        if self._suppress:
            return
        rid = cur.data(0, Qt.ItemDataRole.UserRole) if cur else None
        if self.editor.record is not None and rid == self.editor.record.id:
            return
        if not self.editor.maybe_save():
            self._suppress = True
            self.tree.setCurrentItem(prev)
            self._suppress = False
            return
        rec = self.ctx.repo.find(rid) if rid else None
        self.editor.set_record(rec)
        self._update_child_menu()

    def _update_child_menu(self) -> None:
        menu = self.b_child.menu()
        menu.clear()
        rec = self.editor.record
        kinds = CHILD_KINDS.get(rec.kind, []) if rec is not None else []
        for k in kinds:
            menu.addAction(f"{label(k)} for '{(rec.title or '')[:40]}'", lambda k=k, pid=rec.id: self.add(k, pid))
        self.b_child.setEnabled(bool(kinds))

    def _context_menu(self, pos) -> None:
        m = QMenu(self)
        rec = self.editor.record
        for k in CHILD_KINDS.get(rec.kind, []) if rec else []:
            m.addAction(f"Add {label(k).lower()}", lambda k=k, pid=rec.id: self.add(k, pid))
        if rec:
            m.addSeparator()
        m.addAction("Confirm selected", lambda: self.bulk_verify(Verification.CONFIRMED))
        cm = m.addMenu("Classify selected")
        for v, t in choices(Confidentiality):
            cm.addAction(t, lambda v=v: self.bulk_classify(v))
        m.addAction("Duplicate", self.duplicate)
        m.addAction("Delete selected…", self.bulk_delete)
        m.exec(self.tree.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ operations
    def add(self, kind: RecordKind, parent_id: str | None = None) -> None:
        if not self.editor.maybe_save():
            return
        self.editor.start_new(kind, parent_id)

    def _after_save(self, rid: str) -> None:
        self.ctx.invalidate()
        self.reload(select_id=rid)

    def bulk_verify(self, v: Verification) -> None:
        ids = [i for i in self.selected_ids() if registry.info(self.ctx.repo.get(i).kind).is_fact]
        if not ids:
            return
        if v != Verification.UNCONFIRMED and len(ids) > 1 and not confirm(
                self, "Confirm records", f"Mark {len(ids)} records as {label(v).lower()}? Only do this after checking "
                                         "each one against your records."):
            return
        if not self.editor.maybe_save():
            return
        n = self.ctx.repo.set_verification(ids, v)
        self.ctx.say(f"{n} record(s) updated.")
        self.ctx.invalidate()
        self.reload()
        if self.editor.record is not None:
            self.editor.set_record(self.ctx.repo.get(self.editor.record.id))

    def bulk_classify(self, level: str) -> None:
        ids = self.selected_ids()
        if not ids or not self.editor.maybe_save():
            return
        if level in ("public", "approved") and not confirm(
                self, "Disclosure review", f"Allow {len(ids)} record(s) to appear in external documents "
                                           f"({label(Confidentiality(level))})?",
                detail="Only approve information your employer's rules allow you to disclose."):
            return
        n = self.ctx.repo.set_confidentiality(ids, level)
        self.ctx.say(f"{n} record(s) reclassified.")
        self.ctx.invalidate()
        self.reload()
        if self.editor.record is not None:
            self.editor.set_record(self.ctx.repo.get(self.editor.record.id))

    def bulk_delete(self) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        if not confirm(self, "Delete records", f"Move {len(ids)} record(s) and their linked items to Recently "
                                               "deleted?", ok="Delete", destructive=True):
            return
        for rid in ids:
            if self.ctx.repo.find(rid) is not None:
                self.ctx.repo.delete(rid)
        self.editor.set_record(None)
        self.ctx.invalidate()
        self.reload()
        self.ctx.say("Moved to Recently deleted.")

    def duplicate(self) -> None:
        ids = self.selected_ids()
        if len(ids) != 1:
            return
        rec = self.ctx.repo.get(ids[0])
        if registry.info(rec.kind).singleton:
            return
        data = rec.payload()
        for f in ("title", "name", "designation"):
            if isinstance(data.get(f), str) and data[f]:
                data[f] = data[f] + " (copy)"
                break
        new = self.ctx.repo.create(rec.kind, data, parent_id=rec.parent_id, verification=Verification.UNCONFIRMED
                                   if registry.info(rec.kind).is_fact else None,
                                   confidentiality=rec.confidentiality, origin=Origin.MANUAL)
        self.ctx.invalidate()
        self.reload(select_id=new.id)
        self.ctx.say("Duplicated. The copy is awaiting confirmation.")

    def move(self, delta: int) -> None:
        it = self.tree.currentItem()
        if it is None:
            return
        parent = it.parent()
        siblings = [parent.child(i) if parent else self.tree.topLevelItem(i)
                    for i in range(parent.childCount() if parent else self.tree.topLevelItemCount())]
        rec = self.ctx.repo.get(it.data(0, Qt.ItemDataRole.UserRole))
        same = [s.data(0, Qt.ItemDataRole.UserRole) for s in siblings
                if self.ctx.repo.get(s.data(0, Qt.ItemDataRole.UserRole)).kind == rec.kind]
        i = same.index(rec.id)
        j = i + delta
        if j < 0 or j >= len(same):
            return
        same[i], same[j] = same[j], same[i]
        self.ctx.repo.reorder(same)
        self.ctx.invalidate()
        self.reload(select_id=rec.id)
        self.tree.setFocus()

    def focus_record(self, record_id: str) -> bool:
        self.search.clear()
        self.status_filter.setCurrentIndex(0)
        self.reload(select_id=record_id)
        return self.editor.record is not None and self.editor.record.id == record_id


_ = QAction, QPushButton  # re-exported for type checkers
