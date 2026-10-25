"""Small reusable widgets and dialogs helpers."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ris.domain.enums import Confidentiality, Verification, label

TONE_VERIFICATION = {"unconfirmed": "warn", "confirmed": "ok", "evidenced": "ok"}
TONE_CONFIDENTIALITY = {"public": "ok", "approved": "info", "review": "warn", "confidential": "bad"}
SHORT_CONF = {"public": "Public", "approved": "Approved", "review": "Requires review", "confidential": "Confidential"}
SHORT_VER = {"unconfirmed": "Awaiting confirmation", "confirmed": "Confirmed", "evidenced": "Evidenced"}


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


def chip(text: str, tone: str = "info", tooltip: str = "") -> QLabel:
    lab = QLabel(text)
    lab.setProperty("chip", tone)
    lab.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    if tooltip:
        lab.setToolTip(tooltip)
    lab.setAccessibleName(text)
    return lab


def set_chip(lab: QLabel, text: str, tone: str) -> None:
    lab.setText(text)
    lab.setProperty("chip", tone)
    lab.setAccessibleName(text)
    repolish(lab)


def verification_chip(v: Verification | str) -> QLabel:
    v = str(getattr(v, "value", v))
    return chip(SHORT_VER.get(v, v), TONE_VERIFICATION.get(v, "info"), label(Verification(v)))


def confidentiality_chip(c: Confidentiality | str) -> QLabel:
    c = str(getattr(c, "value", c))
    return chip(SHORT_CONF.get(c, c), TONE_CONFIDENTIALITY.get(c, "info"), label(Confidentiality(c)))


def banner(text: str, tone: str = "info") -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setProperty("banner", tone)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lab


def set_banner(lab: QLabel, text: str, tone: str) -> None:
    lab.setText(text)
    lab.setProperty("banner", tone)
    lab.setVisible(bool(text))
    repolish(lab)


def muted(text: str, wrap: bool = True) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("Muted")
    lab.setWordWrap(wrap)
    return lab


def section_title(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("SectionTitle")
    lab.setAccessibleName(text)
    return lab


def rule() -> QFrame:
    f = QFrame()
    f.setObjectName("Rule")
    f.setFrameShape(QFrame.Shape.NoFrame)
    return f


def button(text: str, kind: str | None = None, *, tooltip: str = "", shortcut: str | None = None,
           on_click: Callable | None = None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    if tooltip:
        b.setToolTip(tooltip)
    if shortcut:
        b.setShortcut(QKeySequence(shortcut))
        b.setToolTip((tooltip + " " if tooltip else "") + f"({QKeySequence(shortcut).toString(QKeySequence.SequenceFormat.NativeText)})")
    if on_click:
        b.clicked.connect(lambda _=False: on_click())
    b.setAccessibleName(text.replace("&", ""))
    return b


class Card(QFrame):
    def __init__(self, title: str | None = None, *, accent: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        if accent:
            self.setProperty("accent", "true")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 12)
        self.body.setSpacing(8)
        if title:
            self.title_label = section_title(title)
            self.body.addWidget(self.title_label)

    def add(self, w: QWidget | None = None, stretch: int = 0) -> None:
        if w is not None:
            self.body.addWidget(w, stretch)


class StatTile(Card):
    def __init__(self, value: str, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(accent=True, parent=parent)
        self.value = QLabel(value)
        self.value.setObjectName("StatValue")
        self.caption = QLabel(caption)
        self.caption.setObjectName("StatLabel")
        self.caption.setWordWrap(True)
        self.body.addWidget(self.value)
        self.body.addWidget(self.caption)
        self.setAccessibleName(f"{caption}: {value}")

    def set(self, value: str, caption: str | None = None) -> None:
        self.value.setText(value)
        if caption is not None:
            self.caption.setText(caption)
        self.setAccessibleName(f"{self.caption.text()}: {value}")


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("PageTitle")
        self.title.setAccessibleName(title)
        texts.addWidget(self.title)
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("PageSubtitle")
        self.subtitle.setWordWrap(True)
        texts.addWidget(self.subtitle)
        lay.addLayout(texts, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(6)
        lay.addLayout(self.actions)

    def add_action(self, w: QWidget) -> None:
        self.actions.addWidget(w)


def scroll(widget: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setWidget(widget)
    return sa


class Page(QWidget):
    """Base page: header + body; subclasses fill ``self.body`` and implement ``refresh``."""

    key = ""

    def __init__(self, ctx, title: str, subtitle: str = "", *, scrollable: bool = True) -> None:
        super().__init__()
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 14)
        outer.setSpacing(12)
        self.header = PageHeader(title, subtitle)
        outer.addWidget(self.header)
        self.content = QWidget()
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(12)
        if scrollable:
            outer.addWidget(scroll(self.content), 1)
        else:
            outer.addWidget(self.content, 1)
        self._dirty = True

    def mark_dirty(self) -> None:
        self._dirty = True
        if self.isVisible():
            self.refresh_if_needed()

    def refresh_if_needed(self) -> None:
        if self._dirty and self.ctx.has_workspace:
            self._dirty = False
            self.refresh()

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        self.refresh_if_needed()

    def refresh(self) -> None:  # pragma: no cover - overridden
        pass

    def kinds_of_interest(self) -> set[str] | None:
        """Record kinds whose changes require a refresh (None = all)."""
        return None

    def focus_record(self, record_id: str) -> None:  # pragma: no cover - optional
        pass

    def has_unsaved_changes(self) -> bool:
        return False


# --------------------------------------------------------------------------- dialogs


def confirm(parent: QWidget | None, title: str, text: str, *, ok: str = "Continue", destructive: bool = False,
            detail: str = "") -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Warning if destructive else QMessageBox.Icon.Question)
    box.setText(text)
    if detail:
        box.setInformativeText(detail)
    yes = box.addButton(ok, QMessageBox.ButtonRole.DestructiveRole if destructive else QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel if destructive else yes)
    box.exec()
    return box.clickedButton() is yes


def info(parent: QWidget | None, title: str, text: str, detail: str = "") -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Information)
    box.setText(text)
    if detail:
        box.setDetailedText(detail)
    box.exec()


def error(parent: QWidget | None, title: str, text: str, detail: str = "") -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setText(text)
    if detail:
        box.setDetailedText(detail)
    box.exec()


def ask_text(parent: QWidget | None, title: str, prompt: str, default: str = "") -> str | None:
    text, ok = QInputDialog.getText(parent, title, prompt, QLineEdit.EchoMode.Normal, default)
    return text.strip() if ok and text.strip() else None


class PassphraseDialog(QDialog):
    """Ask for a passphrase (optionally twice). The value is never logged or stored by this dialog."""

    def __init__(self, parent: QWidget | None, title: str, *, confirm_twice: bool = False, note: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        lay = QVBoxLayout(self)
        if note:
            lay.addWidget(muted(note))
        self.first = QLineEdit()
        self.first.setEchoMode(QLineEdit.EchoMode.Password)
        self.first.setPlaceholderText("Passphrase (at least 10 characters)")
        self.first.setAccessibleName("Passphrase")
        lay.addWidget(self.first)
        self.second = QLineEdit()
        self.second.setEchoMode(QLineEdit.EchoMode.Password)
        self.second.setPlaceholderText("Repeat passphrase")
        self.second.setAccessibleName("Repeat passphrase")
        self.second.setVisible(confirm_twice)
        lay.addWidget(self.second)
        self.problem = banner("", "bad")
        self.problem.setVisible(False)
        lay.addWidget(self.problem)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._confirm = confirm_twice

    def _accept(self) -> None:
        a = self.first.text()
        if self._confirm:
            if len(a) < 10:
                set_banner(self.problem, "Use at least 10 characters.", "bad")
                return
            if a != self.second.text():
                set_banner(self.problem, "The two passphrases do not match.", "bad")
                return
        if not a:
            set_banner(self.problem, "Enter the passphrase.", "bad")
            return
        self.accept()

    def value(self) -> str:
        return self.first.text()


def ask_passphrase(parent: QWidget | None, title: str, *, confirm_twice: bool = False, note: str = "") -> str | None:
    d = PassphraseDialog(parent, title, confirm_twice=confirm_twice, note=note)
    if d.exec() == QDialog.DialogCode.Accepted:
        return d.value()
    return None


def hbox(*widgets: QWidget | None, stretch_end: bool = True, spacing: int = 6) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for x in widgets:
        if x is None:
            lay.addStretch(1)
        else:
            lay.addWidget(x)
    if stretch_end:
        lay.addStretch(1)
    return w


def esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
