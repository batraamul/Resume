"""Update checks and installation in the interface."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ris import __version__
from ris.ui.widgets.common import banner, esc, set_banner
from ris.ui.workers import run_task
from ris.update.client import UpdateClient, UpdateInfo
from ris.update.manifest import UpdateError
from ris.util import utc_now_iso

log = logging.getLogger(__name__)
CHECK_INTERVAL = timedelta(hours=24)
PRIVACY_NOTE = ("Update checks contact GitHub over HTTPS and send no personal data — only the application name "
                "and version. Every update is verified against the project's signing key before it is offered.")


def updates_allowed() -> bool:
    """Automatic checks are off for tests, screenshots and anyone who sets RIS_DISABLE_UPDATE_CHECK."""
    import os

    return not (os.environ.get("RIS_DISABLE_UPDATE_CHECK") or os.environ.get("QT_QPA_PLATFORM") == "offscreen")


def due_for_check(config, now: datetime | None = None) -> bool:
    if not config.update_auto_check:
        return False
    if not config.update_last_check:
        return True
    try:
        last = datetime.fromisoformat(config.update_last_check.replace("Z", "+00:00"))
    except ValueError:
        return True
    now = now or datetime.now(UTC)
    return now - last >= CHECK_INTERVAL


def _notes_html(text: str) -> str:
    lines = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            lines.append(f"<h4>{esc(line.lstrip('#').strip())}</h4>")
        elif line[:2] in ("* ", "- "):
            lines.append(f"<li>{esc(line[2:])}</li>")
        else:
            lines.append(f"<p>{esc(line)}</p>")
    return "".join(lines) or "<p>No release notes were provided.</p>"


class UpdateChecker(QObject):
    """Runs update checks in the background and reports the result."""

    found = Signal(object)        # UpdateInfo
    up_to_date = Signal()
    failed = Signal(str)

    def __init__(self, ctx, client_factory=None) -> None:
        super().__init__()
        self.ctx = ctx
        self.client_factory = client_factory or (lambda: UpdateClient())
        self.busy = False

    def check(self, *, manual: bool = False, synchronous: bool = False) -> None:
        if self.busy:
            return
        self.busy = True
        channel = self.ctx.config.update_channel or "stable"

        def work():
            return self.client_factory().check(channel)

        def done(info: UpdateInfo | None) -> None:
            self.busy = False
            self.ctx.config.update_last_check = utc_now_iso()
            try:
                self.ctx.config.save()
            except OSError:
                pass
            if info is None:
                self.up_to_date.emit()
            elif manual or info.version != self.ctx.config.update_skipped_version:
                self.found.emit(info)

        def fail(msg: str, detail: str) -> None:
            self.busy = False
            log.info("Update check failed: %s", detail or msg)
            self.failed.emit(msg)

        run_task(work, done, fail, synchronous=synchronous)


class UpdateDialog(QDialog):
    """Shows a verified update and installs it when the user agrees."""

    def __init__(self, parent: QWidget | None, ctx, info: UpdateInfo, client_factory=None, quit_app=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.info = info
        self.client_factory = client_factory or (lambda: UpdateClient())
        self.quit_app = quit_app
        self.downloaded = None
        self.plan = None
        self.setWindowTitle("Update available")
        self.resize(620, 520)
        lay = QVBoxLayout(self)
        m = info.manifest
        title = QLabel(f"<h2>Resume Intelligence Studio {esc(m.version)}</h2>"
                       f"<p>You have version {esc(__version__)}."
                       + (f" Released {esc(m.released[:10])}." if m.released else "") + "</p>")
        lay.addWidget(title)
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setAccessibleName("Release notes")
        notes.setHtml(_notes_html(m.notes) + (f"<p><a href='{esc(info.release_url)}'>Release page</a></p>"
                                              if info.release_url else ""))
        lay.addWidget(notes, 1)
        self.status = banner("✓ Signature verified — this update was published by the project's release key.", "ok")
        lay.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setAccessibleName("Download progress")
        lay.addWidget(self.progress)
        lay.addWidget(QLabel("Your profile, documents and backups are not changed by an update."))
        row = QHBoxLayout()
        self.b_skip = QPushButton("Skip this version")
        self.b_skip.clicked.connect(self.skip)
        row.addWidget(self.b_skip)
        row.addStretch(1)
        bb = QDialogButtonBox()
        self.b_later = bb.addButton("Remind me later", QDialogButtonBox.ButtonRole.RejectRole)
        self.b_install = bb.addButton("Download and install", QDialogButtonBox.ButtonRole.AcceptRole)
        self.b_install.setProperty("kind", "primary")
        bb.rejected.connect(self.reject)
        self.b_install.clicked.connect(lambda: self.download_and_install())
        row.addWidget(bb)
        lay.addLayout(row)
        if info.asset is None:
            self.b_install.setEnabled(False)
            set_banner(self.status, "No installer for this computer is attached to this release; download it from "
                                    "the release page.", "warn")

    def skip(self) -> None:
        self.ctx.config.update_skipped_version = self.info.version
        try:
            self.ctx.config.save()
        except OSError:
            pass
        self.reject()

    def download_and_install(self, synchronous: bool = False, run: bool = True) -> None:
        from ris.update.installer import plan_install, run_plan

        asset = self.info.asset
        if asset is None:
            return
        self.b_install.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, max(1, asset.size))
        client = self.client_factory()
        holder = {"done": 0}

        def work():
            path = client.download(asset, progress=lambda done, _total: holder.__setitem__("done", done))
            return path, plan_install(path, asset)

        def done(result) -> None:
            self.progress.setValue(asset.size)
            self.downloaded, self.plan = result
            set_banner(self.status, "✓ Download verified (size and SHA-256 match the signed manifest). "
                       + self.plan.description, "ok")
            if run:
                try:
                    run_plan(self.plan)
                except UpdateError as exc:
                    set_banner(self.status, exc.user_message, "bad")
                    return
                if self.plan.quit_app and self.quit_app:
                    self.accept()
                    self.quit_app()

        def fail(msg: str, _detail: str) -> None:
            set_banner(self.status, msg, "bad")
            self.b_install.setEnabled(True)
            self.progress.setVisible(False)

        run_task(work, done, fail, synchronous=synchronous)
