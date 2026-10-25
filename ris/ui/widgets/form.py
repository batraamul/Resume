"""Schema-driven record form built from the payload model's field metadata.

Every record kind is edited through this form, so validation, help text,
private-field marking and accessibility behave the same everywhere.
"""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ris.composition.modes import MODES
from ris.domain.enums import RecordKind, SummaryFocus, choices, label
from ris.domain.registry import FieldMeta, field_metas
from ris.ui.widgets.common import muted, repolish

STR_CHOICES: dict[str, list[tuple[str, str]]] = {
    "layout": [("entries", "Entries"), ("bullets", "Bullet points"), ("paragraph", "Paragraph")],
    "page_size": [("A4", "A4"), ("Letter", "US Letter")],
    "spacing": [("compact", "Compact"), ("normal", "Normal"), ("relaxed", "Relaxed")],
    "publication_scope": [("relevant", "Relevant to the target"), ("all", "All publications"),
                          ("none", "Do not include")],
    "style": [("formal", "Formal (government)"), ("professional", "Professional")],
    "status": [("draft", "Draft"), ("final", "Final"), ("sent", "Sent")],
    "summary_focus": [("", "(not set)")] + choices(SummaryFocus),
}

PRIVATE_NOTE = ("Private — never shown in resumes unless you explicitly select an item (for example, official "
                "particulars in a bio-data).")


class _ListEdit(QPlainTextEdit):
    """One item per line."""

    def __init__(self) -> None:
        super().__init__()
        self.setTabChangesFocus(True)
        self.setFixedHeight(74)

    def value(self) -> list[str]:
        return [ln.strip() for ln in self.toPlainText().splitlines() if ln.strip()]

    def set_value(self, v: Any) -> None:
        self.setPlainText(v if isinstance(v, str) else "\n".join(str(x) for x in (v or [])))


class _TextEdit(QPlainTextEdit):
    def __init__(self, tall: bool = False) -> None:
        super().__init__()
        self.setTabChangesFocus(True)
        self.setMinimumHeight(110 if tall else 64)
        self.setMaximumHeight(260 if tall else 140)


class _CustomFields(QWidget):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Field name", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setFixedHeight(110)
        self.table.setAccessibleName("Custom fields")
        self.table.itemChanged.connect(lambda _i: self.changed.emit())
        lay.addWidget(self.table)
        row = QHBoxLayout()
        add = QPushButton("Add field")
        add.clicked.connect(self._add)
        rem = QPushButton("Remove selected")
        rem.clicked.connect(self._remove)
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch(1)
        lay.addLayout(row)

    def _add(self) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(""))
        self.table.setItem(r, 1, QTableWidgetItem(""))
        self.table.editItem(self.table.item(r, 0))

    def _remove(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        self.changed.emit()

    def value(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for r in range(self.table.rowCount()):
            k = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            v = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
            if k:
                out[k] = v
        return out

    def set_value(self, v: dict | None) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for k, val in (v or {}).items():
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(str(k)))
            self.table.setItem(r, 1, QTableWidgetItem(str(val)))
        self.table.blockSignals(False)


class RecordForm(QWidget):
    """Edit a payload dict for one record kind."""

    changed = Signal()

    def __init__(self, ctx, kind: RecordKind, *, show_private: bool = True, exclude: set[str] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.kind = RecordKind(kind)
        from ris.domain.registry import model_for

        self.model = model_for(self.kind)
        self.metas: list[FieldMeta] = [m for m in field_metas(self.model) if m.name not in (exclude or set())
                                       and m.widget != "requirements"]
        if not show_private:
            self.metas = [m for m in self.metas if not m.private]
        self.editors: dict[str, QWidget] = {}
        self.labels: dict[str, QLabel] = {}
        self._original: dict[str, Any] = {}
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        groups: dict[str, list[FieldMeta]] = {}
        for m in self.metas:
            groups.setdefault(m.group, []).append(m)
        for gname, metas in groups.items():
            box = QGroupBox(gname)
            box.setAccessibleName(gname)
            form = QFormLayout(box)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setVerticalSpacing(7)
            if all(m.private for m in metas):
                form.addRow(muted(PRIVATE_NOTE))
            for m in metas:
                ed = self._make_editor(m)
                self.editors[m.name] = ed
                text = m.title + (" 🔒" if m.private and not all(x.private for x in metas) else "")
                lab = QLabel(text)
                lab.setBuddy(ed)
                lab.setWordWrap(True)
                self.labels[m.name] = lab
                tip = m.help or ""
                if m.private:
                    tip = (tip + "\n" if tip else "") + PRIVATE_NOTE
                if tip:
                    ed.setToolTip(tip)
                    lab.setToolTip(tip)
                ed.setAccessibleName(m.title)
                if m.help:
                    ed.setAccessibleDescription(m.help)
                if m.help and m.widget in ("text", "list", "tags", "date", "refs"):
                    holder = QWidget()
                    hl = QVBoxLayout(holder)
                    hl.setContentsMargins(0, 0, 0, 0)
                    hl.setSpacing(2)
                    hl.addWidget(ed)
                    h = muted(m.help)
                    hl.addWidget(h)
                    form.addRow(lab, holder)
                else:
                    form.addRow(lab, ed)
            lay.addWidget(box)
        lay.addStretch(1)

    # ------------------------------------------------------------------ editors
    def _ref_items(self, kind: str) -> list[tuple[str, str]]:
        if not self.ctx or not self.ctx.has_workspace:
            return []
        out = []
        kinds = [k.strip() for k in (kind or "").split(",") if k.strip()]
        for k in kinds:
            prefix = f"{label(RecordKind(k))}: " if len(kinds) > 1 else ""
            for r in self.ctx.repo.list(RecordKind(k)):
                out.append((r.id, prefix + (r.title or "(untitled)") + (f" — {r.subtitle}" if r.subtitle else "")))
        return out

    def _combo(self, items: list[tuple[str, str]], editable: bool = False) -> QComboBox:
        cb = QComboBox()
        cb.setEditable(editable)
        for value, text in items:
            cb.addItem(text, value)
        cb.currentIndexChanged.connect(self._emit)
        if editable:
            cb.editTextChanged.connect(self._emit)
        return cb

    def _make_editor(self, m: FieldMeta) -> QWidget:
        w = m.widget
        if m.enum_type is not None:
            items = ([("", "(not set)")] if m.optional_enum else []) + choices(m.enum_type)
            return self._combo(items)
        if w == "bool":
            cb = QCheckBox()
            cb.toggled.connect(self._emit)
            return cb
        if w == "text" or w == "paragraphs":
            te = _TextEdit(tall=m.name in ("text", "raw_text", "paragraphs", "abstract", "description", "summary"))
            te.textChanged.connect(self._emit)
            if m.placeholder:
                te.setPlaceholderText(m.placeholder)
            return te
        if w == "list":
            le = _ListEdit()
            le.textChanged.connect(self._emit)
            le.setPlaceholderText("One item per line")
            return le
        if w == "custom":
            cf = _CustomFields()
            cf.changed.connect(self._emit)
            return cf
        if w == "ref":
            return self._combo([("", "(none)")] + self._ref_items(m.ref_kind or ""))
        if w == "refs":
            lw = QListWidget()
            lw.setFixedHeight(96)
            lw.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            for rid, text in self._ref_items(m.ref_kind or ""):
                it = QListWidgetItem(text)
                it.setData(Qt.ItemDataRole.UserRole, rid)
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Unchecked)
                lw.addItem(it)
            lw.itemChanged.connect(lambda _i: self._emit())
            return lw
        if w == "mode":
            return self._combo([(k, v.name) for k, v in MODES.items()])
        if w == "template":
            items = [(t.id, t.name + ("" if t.builtin else " (custom)")) for t in self.ctx.templates.list()] \
                if self.ctx else []
            return self._combo(([("", "(none)")] if m.name == "preferred_template" else []) + items)
        if w == "preset":
            items = [(p.id, p.name) for p in self.ctx.presets.presets.values()] if self.ctx else []
            return self._combo([("", "(none)")] + items)
        if w == "org_profile":
            items = [(o.id, o.name) for o in self.ctx.presets.organisations.values()] if self.ctx else []
            return self._combo([("", "(none)")] + items)
        if w == "choice_str":
            items = STR_CHOICES.get(m.name, [])
            return self._combo(items, editable=not items)
        if w == "version":
            items = [("", "(none)")]
            if self.ctx and self.ctx.has_workspace:
                vs = self.ctx.variants()
                for v in vs.variants():
                    for info in vs.list_versions(v.id):
                        items.append((info.id, f"{v.data.name} — {info.title}"))
            return self._combo(items)
        if w == "colour":
            holder = _ColourEdit()
            holder.edit.textChanged.connect(self._emit)
            return holder
        if w == "file":
            holder = _FileEdit()
            holder.edit.textChanged.connect(self._emit)
            return holder
        le = QLineEdit()
        if w == "number":
            le.setValidator(QDoubleValidator(0, 1e6, 2) if self._is_float(m.name) else QIntValidator(0, 100000))
        if w == "date":
            le.setPlaceholderText("YYYY, YYYY-MM or YYYY-MM-DD")
            le.setMaximumWidth(220)
        elif w == "tags":
            le.setPlaceholderText("Comma separated")
        elif w == "email":
            le.setPlaceholderText("name@example.org")
        elif w == "url":
            le.setPlaceholderText("https://…")
        if m.placeholder:
            le.setPlaceholderText(m.placeholder)
        le.textChanged.connect(self._emit)
        return le

    def _is_float(self, name: str) -> bool:
        fi = self.model.model_fields.get(name)
        return fi is not None and "float" in str(fi.annotation)

    def _emit(self, *_a) -> None:
        if not self._loading:
            self.changed.emit()

    # ------------------------------------------------------------------ values
    def set_data(self, data: dict[str, Any]) -> None:
        self._loading = True
        try:
            self._original = json.loads(json.dumps(data, default=str))
            for m in self.metas:
                ed = self.editors[m.name]
                v = data.get(m.name)
                self._set(ed, m, v)
                self.mark_invalid(m.name, False)
        finally:
            self._loading = False

    def _set(self, ed: QWidget, m: FieldMeta, v: Any) -> None:
        if isinstance(ed, QComboBox):
            val = "" if v is None else str(v)
            idx = ed.findData(val)
            if idx < 0 and val:
                if ed.isEditable():
                    ed.setEditText(val)
                    return
                ed.addItem(f"{val} (unavailable)", val)
                idx = ed.count() - 1
            ed.setCurrentIndex(max(idx, 0))
        elif isinstance(ed, QCheckBox):
            ed.setChecked(bool(v))
        elif isinstance(ed, _ListEdit):
            ed.set_value(v)
        elif isinstance(ed, QPlainTextEdit):
            ed.setPlainText("" if v is None else str(v))
        elif isinstance(ed, _CustomFields):
            ed.set_value(v)
        elif isinstance(ed, QListWidget):
            chosen = set(v or [])
            for i in range(ed.count()):
                it = ed.item(i)
                it.setCheckState(Qt.CheckState.Checked if it.data(Qt.ItemDataRole.UserRole) in chosen
                                 else Qt.CheckState.Unchecked)
        elif isinstance(ed, (_ColourEdit, _FileEdit)):
            ed.edit.setText("" if v is None else str(v))
        elif isinstance(ed, QLineEdit):
            if m.widget == "tags":
                ed.setText(v if isinstance(v, str) else ", ".join(str(x) for x in (v or [])))
            elif v is None:
                ed.setText("")
            elif isinstance(v, float) and v.is_integer() and m.widget == "number":
                ed.setText(str(int(v)) if not self._is_float(m.name) else f"{v:g}")
            else:
                ed.setText(str(v))

    def _get(self, ed: QWidget, m: FieldMeta) -> Any:
        if isinstance(ed, QComboBox):
            if ed.isEditable():
                idx = ed.findText(ed.currentText())
                return ed.itemData(idx) if idx >= 0 else ed.currentText().strip()
            v = ed.currentData()
            if m.enum_type is not None and m.optional_enum and v == "":
                return None
            return v if v is not None else ""
        if isinstance(ed, QCheckBox):
            return ed.isChecked()
        if isinstance(ed, _ListEdit):
            return ed.value()
        if isinstance(ed, QPlainTextEdit):
            return ed.toPlainText().strip()
        if isinstance(ed, _CustomFields):
            return ed.value()
        if isinstance(ed, QListWidget):
            return [ed.item(i).data(Qt.ItemDataRole.UserRole) for i in range(ed.count())
                    if ed.item(i).checkState() == Qt.CheckState.Checked]
        if isinstance(ed, (_ColourEdit, _FileEdit)):
            return ed.edit.text().strip()
        if isinstance(ed, QLineEdit):
            t = ed.text().strip()
            if m.widget == "tags":
                return [x.strip() for x in t.replace(";", ",").split(",") if x.strip()]
            if m.widget == "number":
                if not t:
                    return None
                try:
                    return float(t) if self._is_float(m.name) else int(float(t))
                except ValueError:
                    return t  # let validation report it
            return t
        return None

    def data(self) -> dict[str, Any]:
        """Edited values merged onto the original payload (keeps hidden and unknown fields)."""
        out = dict(self._original)
        for m in self.metas:
            out[m.name] = self._get(self.editors[m.name], m)
        return out

    def value(self, name: str) -> Any:
        m = next(x for x in self.metas if x.name == name)
        return self._get(self.editors[name], m)

    def set_value(self, name: str, v: Any) -> None:
        m = next(x for x in self.metas if x.name == name)
        self._set(self.editors[name], m, v)
        self._emit()

    def is_modified(self) -> bool:
        cur = json.loads(json.dumps(self.data(), default=str))
        base = dict(self._original)
        for m in self.metas:
            a, b = cur.get(m.name), base.get(m.name)
            if (a in ("", None, [], {}) and b in ("", None, [], {})) or a == b:
                continue
            return True
        return False

    # ------------------------------------------------------------------ validation display
    def mark_invalid(self, name: str, invalid: bool) -> None:
        ed = self.editors.get(name)
        if ed is None:
            return
        target = ed.edit if isinstance(ed, (_ColourEdit, _FileEdit)) else ed
        target.setProperty("invalid", "true" if invalid else "false")
        repolish(target)

    def show_errors(self, messages: list[str]) -> list[str]:
        """Highlight fields named in 'Title: message' errors; returns messages not matched to a field."""
        unmatched = []
        titles = {m.title.lower(): m.name for m in self.metas}
        for m in self.metas:
            self.mark_invalid(m.name, False)
        first = None
        for msg in messages:
            title = msg.split(":", 1)[0].strip().lower()
            name = titles.get(title)
            if name:
                self.mark_invalid(name, True)
                first = first or name
            else:
                unmatched.append(msg)
        if first:
            self.editors[first].setFocus()
        return unmatched


class _ColourEdit(QWidget):
    def __init__(self) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("#701C35 (empty = template colour)")
        self.edit.setMaximumWidth(220)
        pick = QToolButton()
        pick.setText("Choose…")
        pick.setAccessibleName("Choose colour")
        pick.clicked.connect(self._pick)
        lay.addWidget(self.edit)
        lay.addWidget(pick)
        lay.addStretch(1)
        self.setFocusProxy(self.edit)

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self.edit.text() or "#701C35"), self, "Accent colour")
        if c.isValid():
            self.edit.setText(c.name().upper())


class _FileEdit(QWidget):
    def __init__(self) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("No file chosen")
        b = QToolButton()
        b.setText("Browse…")
        b.setAccessibleName("Browse for file")
        b.clicked.connect(self._browse)
        clear = QToolButton()
        clear.setText("Clear")
        clear.clicked.connect(lambda: self.edit.setText(""))
        lay.addWidget(self.edit, 1)
        lay.addWidget(b)
        lay.addWidget(clear)
        self.setFocusProxy(self.edit)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a photograph", "", "Images (*.png *.jpg *.jpeg)")
        if path:
            self.edit.setText(path)
