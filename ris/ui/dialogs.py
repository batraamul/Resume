"""Dialogs: suggestion approval, export review, AI request preview, validation report,
import preview, version comparison and synchronisation conflicts."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ris.domain.enums import Confidentiality, RecordKind, Verification, label
from ris.intelligence.claims import validate_claim
from ris.ui.widgets.common import banner, esc, muted, section_title, set_banner

# --------------------------------------------------------------------------- suggestion approval


class SuggestionDialog(QDialog):
    """Side-by-side original and suggested wording with provenance and validation flags.

    Nothing is changed unless the user approves. Material suggestions (new numbers,
    stronger involvement, outcomes, qualifications, deployments…) need an explicit
    accuracy confirmation.
    """

    def __init__(self, parent: QWidget | None, suggestion, *, title: str = "Review suggested wording",
                 involvement: str | None = None, generator_note: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(940, 620)
        self.suggestion = suggestion
        self.involvement = involvement
        lay = QVBoxLayout(self)
        if generator_note:
            lay.addWidget(banner(generator_note, "info"))
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(section_title("Your recorded wording"))
        orig = QPlainTextEdit(suggestion.original)
        orig.setReadOnly(True)
        orig.setAccessibleName("Original wording")
        ll.addWidget(orig)
        ll.addWidget(section_title("Facts used"))
        facts = QTextBrowser()
        facts.setAccessibleName("Facts used")
        facts.setHtml("<ul>" + "".join(f"<li>{esc(f)}</li>" for f in suggestion.source_facts) + "</ul>")
        ll.addWidget(facts)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(section_title("Suggested wording (you can edit it)"))
        self.edit = QPlainTextEdit(suggestion.revised)
        self.edit.setAccessibleName("Suggested wording")
        self.edit.textChanged.connect(self._revalidate)
        rl.addWidget(self.edit)
        rl.addWidget(section_title("Checks"))
        self.checks = QTextBrowser()
        self.checks.setAccessibleName("Checks")
        rl.addWidget(self.checks)
        split.addWidget(right)
        lay.addWidget(split, 1)
        self.status = banner("", "info")
        lay.addWidget(self.status)
        self.accuracy = QCheckBox("I confirm this wording is accurate and supported by my records.")
        lay.addWidget(self.accuracy)
        bb = QDialogButtonBox()
        self.approve = bb.addButton("Approve wording", QDialogButtonBox.ButtonRole.AcceptRole)
        self.approve.setProperty("kind", "primary")
        bb.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.accuracy.toggled.connect(lambda _c: self._update_buttons())
        self._revalidate()

    def _revalidate(self) -> None:
        text = self.edit.toPlainText().strip()
        facts = [f.split(":", 1)[-1].strip() for f in self.suggestion.source_facts]
        self.check = validate_claim(self.suggestion.original, text, facts, self.involvement)
        parts = []
        if self.suggestion.changes:
            parts.append("<b>Changes</b><ul>" + "".join(f"<li>{esc(c)}</li>" for c in self.suggestion.changes) + "</ul>")
        if self.check.flags:
            parts.append("<b>Needs your attention</b><ul>" + "".join(f"<li>{esc(f)}</li>" for f in self.check.flags)
                         + "</ul>")
        if self.suggestion.assumptions:
            parts.append("<b>Assumptions</b><ul>" + "".join(f"<li>{esc(a)}</li>" for a in self.suggestion.assumptions)
                         + "</ul>")
        if self.suggestion.missing_metrics:
            parts.append("<b>Information that would strengthen this (add only if you can verify it)</b><ul>"
                         + "".join(f"<li>{esc(m)}</li>" for m in self.suggestion.missing_metrics) + "</ul>")
        self.checks.setHtml("".join(parts) or "<p>No issues found.</p>")
        if not text:
            set_banner(self.status, "The wording cannot be empty.", "bad")
        elif self.check.material:
            set_banner(self.status, "This wording adds or strengthens facts compared with your records. Approve it "
                       "only if it is accurate.", "warn")
        elif text == self.suggestion.original.strip():
            set_banner(self.status, "The wording is unchanged.", "info")
        else:
            set_banner(self.status, "The suggestion only rearranges facts you recorded.", "ok")
        self.accuracy.setVisible(self.check.material)
        self._update_buttons()

    def _update_buttons(self) -> None:
        text = self.edit.toPlainText().strip()
        ok = bool(text) and (not self.check.material or self.accuracy.isChecked())
        self.approve.setEnabled(ok)

    def _accept(self) -> None:
        if self.approve.isEnabled():
            self.accept()

    def approved_text(self) -> str:
        return " ".join(self.edit.toPlainText().split())


# --------------------------------------------------------------------------- export review


class ReviewDialog(QDialog):
    """Lists items that block or warn before export, with explicit actions."""

    def __init__(self, parent: QWidget | None, ctx, review, *, variant_id: str | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.review = review
        self.variant_id = variant_id
        self.changed = False
        self.setWindowTitle("Review before export")
        self.resize(900, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(muted("Unconfirmed facts and items that need a disclosure review cannot be exported. "
                            "Possible identifiers block export; sensitive wording needs your acknowledgement."))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Issue", "Record", "Detail"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.setAccessibleName("Review items")
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.b_confirm = QPushButton("Confirm selected facts")
        self.b_confirm.setToolTip("Mark the selected facts as confirmed by you.")
        self.b_confirm.clicked.connect(self._confirm)
        self.b_approve = QPushButton("Approve selected for professional use")
        self.b_approve.setToolTip("Complete the disclosure review: the selected records may appear in external documents.")
        self.b_approve.clicked.connect(self._approve)
        self.b_exclude = QPushButton("Exclude selected from this resume")
        self.b_exclude.clicked.connect(self._exclude)
        self.b_exclude.setEnabled(variant_id is not None)
        self.b_open = QPushButton("Open record")
        self.b_open.clicked.connect(self._open)
        for b in (self.b_confirm, self.b_approve, self.b_exclude, self.b_open):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.ack = QCheckBox("I have reviewed the sensitive wording warnings and want to keep that wording.")
        lay.addWidget(self.ack)
        self.note = banner("", "info")
        lay.addWidget(self.note)
        bb = QDialogButtonBox()
        self.b_retry = bb.addButton("Check again and export", QDialogButtonBox.ButtonRole.AcceptRole)
        self.b_retry.setProperty("kind", "primary")
        bb.addButton("Close", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._fill()

    def _fill(self) -> None:
        items = self.review.items
        self.table.setRowCount(len(items))
        names = {"unconfirmed": "Awaiting confirmation", "disclosure": "Disclosure review",
                 "identifier": "Possible identifier", "sensitive": "Sensitive wording"}
        for i, it in enumerate(items):
            a = QTableWidgetItem(("⛔ " if it.blocking else "⚠ ") + names.get(it.kind, it.kind))
            a.setData(Qt.ItemDataRole.UserRole, i)
            self.table.setItem(i, 0, a)
            self.table.setItem(i, 1, QTableWidgetItem(it.title or ""))
            self.table.setItem(i, 2, QTableWidgetItem(it.detail))
        self.table.resizeRowsToContents()
        has_sensitive = any(i.kind == "sensitive" for i in items)
        self.ack.setVisible(has_sensitive)
        blocking = len(self.review.blocking)
        set_banner(self.note, f"{blocking} item(s) block export." if blocking else
                   "No blocking items remain." + (" Acknowledge the warnings to continue." if has_sensitive else ""),
                   "warn" if blocking else "ok")

    def _selected_items(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.review.items[r] for r in rows]

    def _ids(self, kinds: set[str]) -> list[str]:
        return sorted({i.record_id for i in self._selected_items() if i.record_id and i.kind in kinds})

    def _confirm(self) -> None:
        ids = self._ids({"unconfirmed"})
        if ids:
            self.ctx.profile().confirm(ids)
            self.changed = True
            self._mark_done(ids, "unconfirmed")

    def _approve(self) -> None:
        ids = self._ids({"disclosure"})
        snap = self.ctx.snapshot()
        ids = [i for i in ids if snap.get(i) is not None and snap.get(i).confidentiality == Confidentiality.REVIEW]
        if ids:
            self.ctx.repo.set_confidentiality(ids, Confidentiality.APPROVED)
            self.changed = True
            self._mark_done(ids, "disclosure")

    def _exclude(self) -> None:
        ids = sorted({i.record_id for i in self._selected_items() if i.record_id})
        if ids and self.variant_id:
            rec = self.ctx.repo.get(self.variant_id)
            ex = list(dict.fromkeys(list(rec.data.exclude_ids) + ids))
            self.ctx.repo.patch(self.variant_id, exclude_ids=ex)
            self.changed = True
            self.review.items = [i for i in self.review.items if i.record_id not in ids]
            self._fill()

    def _mark_done(self, ids: list[str], kind: str) -> None:
        self.ctx.invalidate()
        self.review.items = [i for i in self.review.items if not (i.kind == kind and i.record_id in ids)]
        self._fill()

    def _open(self) -> None:
        sel = self._selected_items()
        if sel and sel[0].record_id:
            self.ctx.navigate.emit("record", sel[0].record_id)
            self.reject()

    def acknowledged(self) -> bool:
        return self.ack.isChecked()


# --------------------------------------------------------------------------- external AI preview


class PayloadPreviewDialog(QDialog):
    def __init__(self, parent: QWidget | None, provider_desc: str, request_json: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("Send to external AI provider?")
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(banner(f"The following will be sent to {provider_desc}. The API key is sent in a request header "
                             "and is not shown. Nothing else from your profile is sent.", "warn"))
        view = QPlainTextEdit(request_json)
        view.setReadOnly(True)
        view.setAccessibleName("Exact request")
        lay.addWidget(view, 1)
        bb = QDialogButtonBox()
        send = bb.addButton("Send this request", QDialogButtonBox.ButtonRole.AcceptRole)
        send.setProperty("kind", "primary")
        bb.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


# --------------------------------------------------------------------------- validation report


def report_html(report, quality=None, trimmed: list[str] | None = None, review=None) -> str:
    icon = {"pass": "✔", "warn": "⚠", "fail": "✖", "skip": "–"}
    rows = []
    if report is not None:
        for c in report.checks:
            det = ""
            if c.details:
                det = "<br><small>" + "<br>".join(esc(d) for d in c.details[:8]) + "</small>"
            rows.append(f"<tr><td>{icon.get(c.status, c.status)}</td><td><b>{esc(c.name)}</b></td>"
                        f"<td>{esc(c.message)}{det}</td></tr>")
    html = ""
    if rows:
        html += ("<h3>Validation</h3><table cellpadding='4' cellspacing='0' width='100%'>"
                 + "".join(rows) + "</table>")
    if trimmed:
        html += "<h3>Fit to page</h3><ul>" + "".join(f"<li>{esc(t)}</li>" for t in trimmed) + "</ul>"
    if quality is not None and getattr(quality, "items", None):
        sev = {"info": "ℹ", "warn": "⚠", "problem": "✖"}
        html += f"<h3>Quality checks (score {quality.score:.0%})</h3><ul>" + "".join(
            f"<li>{sev.get(q.severity, '')} {esc(q.message)}</li>" for q in quality.items) + "</ul>"
        if quality.missing_keywords:
            html += ("<p><b>Vacancy keywords not found in this resume</b> (add them only where your records support "
                     "them): " + esc(", ".join(quality.missing_keywords[:20])) + "</p>")
    if review is not None and review.warnings:
        html += "<h3>Acknowledged warnings</h3><ul>" + "".join(
            f"<li>{esc(w.title)}: {esc(w.detail)}</li>" for w in review.warnings) + "</ul>"
    return html or "<p>No report.</p>"


class ReportDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, html: str, summary: str = "", tone: str = "info") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 600)
        lay = QVBoxLayout(self)
        if summary:
            lay.addWidget(banner(summary, tone))
        view = QTextBrowser()
        view.setOpenExternalLinks(False)
        view.setHtml(html)
        view.setAccessibleName(title)
        lay.addWidget(view, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)


# --------------------------------------------------------------------------- import preview


class ImportPreviewDialog(QDialog):
    """Choose which candidate records to import. Imported facts arrive unconfirmed and 'Requires review'."""

    def __init__(self, parent: QWidget | None, preview, *, title: str = "Import preview") -> None:
        super().__init__(parent)
        self.preview = preview
        self.setWindowTitle(title)
        self.resize(940, 600)
        lay = QVBoxLayout(self)
        lay.addWidget(banner("Nothing is saved until you choose Import. Every imported fact arrives as "
                             "'Awaiting confirmation' and 'Requires review'. Likely duplicates are unticked.", "info"))
        self.table = QTableWidget(len(preview.candidates), 4)
        self.table.setHorizontalHeaderLabels(["Import", "Type", "Title", "Notes"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAccessibleName("Candidate records")
        for i, c in enumerate(preview.candidates):
            box = QTableWidgetItem()
            box.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled if c.valid
                         else Qt.ItemFlag.ItemIsEnabled)
            box.setCheckState(Qt.CheckState.Checked if c.include else Qt.CheckState.Unchecked)
            self.table.setItem(i, 0, box)
            indent = "    " if c.parent_source_id else ""
            self.table.setItem(i, 1, QTableWidgetItem(indent + label(c.kind)))
            self.table.setItem(i, 2, QTableWidgetItem(c.title))
            notes = "; ".join(c.errors) if c.errors else ""
            if c.duplicate is not None:
                notes = (notes + "; " if notes else "") + f"Possible duplicate of '{c.duplicate.record.title}' " \
                                                          f"({c.duplicate.reason})"
            self.table.setItem(i, 3, QTableWidgetItem(notes))
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        for text, state in (("Select all", True), ("Select none", False)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, s=state: self._all(s))
            row.addWidget(b)
        row.addStretch(1)
        self.count = QLabel()
        row.addWidget(self.count)
        lay.addLayout(row)
        self.table.itemChanged.connect(lambda _i: self._update())
        bb = QDialogButtonBox()
        self.ok = bb.addButton("Import selected", QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok.setProperty("kind", "primary")
        bb.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._update()

    def _all(self, state: bool) -> None:
        for i, c in enumerate(self.preview.candidates):
            if c.valid:
                self.table.item(i, 0).setCheckState(Qt.CheckState.Checked if state else Qt.CheckState.Unchecked)

    def _update(self) -> None:
        n = sum(1 for i in range(self.table.rowCount())
                if self.table.item(i, 0).checkState() == Qt.CheckState.Checked)
        self.count.setText(f"{n} of {self.table.rowCount()} selected")
        self.ok.setEnabled(n > 0)

    def _accept(self) -> None:
        for i, c in enumerate(self.preview.candidates):
            c.include = c.valid and self.table.item(i, 0).checkState() == Qt.CheckState.Checked
        self.accept()


# --------------------------------------------------------------------------- comparison & conflicts


class HtmlDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, html: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(980, 640)
        lay = QVBoxLayout(self)
        view = QTextBrowser()
        view.setHtml(html)
        view.setAccessibleName(title)
        lay.addWidget(view, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


def _env_text(env: dict | None) -> str:
    if env is None:
        return "(deleted on this side)"
    if env.get("deleted"):
        return "(deleted on this side)"
    data = env.get("data") or {}
    lines = [f"Revision {env.get('revision', '?')} · changed {env.get('updated_at', '')[:19].replace('T', ' ')}",
             f"Verification: {env.get('verification', '')} · Classification: {env.get('confidentiality', '')}", ""]
    for k, v in data.items():
        if v in ("", None, [], {}):
            continue
        lines.append(f"{k}: {json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v}")
    return "\n".join(lines)


class ConflictDialog(QDialog):
    """Choose between the local and remote version of a record changed on two devices."""

    def __init__(self, parent: QWidget | None, conflict) -> None:
        super().__init__(parent)
        self.choice: str | None = None
        kind = conflict.kind
        try:
            kind = label(RecordKind(kind))
        except ValueError:
            pass
        self.setWindowTitle(f"Resolve conflict — {kind}")
        self.resize(980, 600)
        lay = QVBoxLayout(self)
        lay.addWidget(muted("This record was changed on this computer and on another device since the last "
                            "synchronisation. Nothing is lost until you choose."))
        split = QSplitter(Qt.Orientation.Horizontal)
        for title, env in (("This computer", conflict.local), ("Other device (cloud)", conflict.remote)):
            w = QWidget()
            wl = QVBoxLayout(w)
            wl.addWidget(section_title(title))
            t = QPlainTextEdit(_env_text(env))
            t.setReadOnly(True)
            t.setAccessibleName(title)
            wl.addWidget(t)
            split.addWidget(w)
        lay.addWidget(split, 1)
        bb = QDialogButtonBox()
        for text, choice, role in (("Keep this computer's version", "keep_local", QDialogButtonBox.ButtonRole.AcceptRole),
                                   ("Keep the other device's version", "keep_remote", QDialogButtonBox.ButtonRole.AcceptRole),
                                   ("Keep both (as separate records)", "keep_both", QDialogButtonBox.ButtonRole.AcceptRole)):
            b = bb.addButton(text, role)
            b.clicked.connect(lambda _=False, c=choice: self._choose(c))
        bb.addButton("Decide later", QDialogButtonBox.ButtonRole.RejectRole)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _choose(self, c: str) -> None:
        self.choice = c
        self.accept()


def status_text(rec: Any) -> str:
    """Short plain-text status for lists (screen-reader friendly)."""
    v = {"unconfirmed": "awaiting confirmation", "confirmed": "confirmed", "evidenced": "evidenced"}.get(
        rec.verification.value, rec.verification.value)
    c = {"public": "public", "approved": "approved", "review": "requires review",
         "confidential": "confidential"}.get(rec.confidentiality.value, rec.confidentiality.value)
    return f"{v}, {c}"


__all__ = ["SuggestionDialog", "ReviewDialog", "PayloadPreviewDialog", "ReportDialog", "report_html",
           "ImportPreviewDialog", "HtmlDialog", "ConflictDialog", "status_text", "Verification"]
