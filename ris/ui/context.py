"""Application context shared by all pages: configuration, open workspace, services and change signals."""

from __future__ import annotations

import logging
from datetime import date

from PySide6.QtCore import QObject, QTimer, Signal

from ris.backup.backup import BackupService
from ris.config import AppConfig
from ris.domain.enums import RecordKind
from ris.intelligence.presets import PresetLibrary, default_presets
from ris.rendering.export import ExportService
from ris.rendering.specs import TemplateLibrary
from ris.security.secrets import SecretStore
from ris.services.profile import ProfileService, ProfileSnapshot
from ris.services.variants import VariantService
from ris.storage.workspace import Workspace, WorkspaceManager
from ris.sync.service import SyncService

log = logging.getLogger(__name__)


class AppContext(QObject):
    workspace_opened = Signal()
    workspace_closing = Signal()
    data_changed = Signal(set)   # set of record kinds changed (debounced)
    status = Signal(str, int)    # message, timeout ms
    theme_changed = Signal()
    navigate = Signal(str, str)  # page key, optional record id

    def __init__(self, config: AppConfig, *, secrets: SecretStore | None = None) -> None:
        super().__init__()
        self.config = config
        self.manager = WorkspaceManager(config)
        self.secrets = secrets or SecretStore()
        self.templates = TemplateLibrary(user_dir=config.resolved_data_dir() / "templates")
        self.presets: PresetLibrary = default_presets()
        self.ws: Workspace | None = None
        self._snapshot: ProfileSnapshot | None = None
        self._pending: set[str] = set()
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self._flush_changes)
        self._listener_signal = _ListenerBridge()
        self._listener_signal.changed.connect(self._on_repo_change)
        self.today: date | None = None  # tests may pin the date
        self.remote_factory = None      # tests inject an in-memory remote
        self._sync: SyncService | None = None

    # ------------------------------------------------------------------ workspace
    @property
    def has_workspace(self) -> bool:
        return self.ws is not None

    @property
    def is_sample(self) -> bool:
        return bool(self.ws and self.ws.is_sample)

    def open_entry(self, entry) -> Workspace:
        self.close_workspace(backup=False)
        ws = self.manager.open(entry)
        self.manager.set_active(entry.id)
        self.ws = ws
        self._snapshot = None
        ws.repo.add_listener(self._listener_signal.relay)
        if not ws.settings.get("device.id"):
            ws.settings.set("device.id", self.config.device_id)
        log.info("Workspace opened (sample=%s)", ws.is_sample)
        self.workspace_opened.emit()
        return ws

    def open_active(self, prefer_sample: bool = False) -> Workspace:
        entry = self.manager.ensure_sample() if prefer_sample else self.manager.active_entry()
        return self.open_entry(entry)

    def after_restore(self) -> None:
        """A restore replaces the database and reopens the workspace: re-attach and refresh everything."""
        if self.ws is None:
            return
        self.ws.repo.add_listener(self._listener_signal.relay)
        self._snapshot = None
        self._sync = None
        self.workspace_opened.emit()

    def close_workspace(self, backup: bool = True) -> None:
        if self.ws is None:
            return
        self.workspace_closing.emit()
        ws = self.ws
        try:
            if backup and not ws.is_sample and ws.settings.get("backup.on_exit"):
                try:
                    BackupService(ws).create(reason="on-exit")
                    BackupService(ws).prune()
                except Exception:  # noqa: BLE001 - never block closing on a backup problem
                    log.exception("Backup on exit failed")
            ws.repo.remove_listener(self._listener_signal.relay)
        finally:
            ws.close()
            self.ws = None
            self._snapshot = None
            self._sync = None

    # ------------------------------------------------------------------ data
    @property
    def repo(self):
        assert self.ws is not None, "no workspace open"
        return self.ws.repo

    @property
    def settings(self):
        assert self.ws is not None, "no workspace open"
        return self.ws.settings

    def snapshot(self) -> ProfileSnapshot:
        if self._snapshot is None:
            self._snapshot = ProfileService(self.repo).snapshot()
        return self._snapshot

    def profile(self) -> ProfileService:
        return ProfileService(self.repo)

    def invalidate(self) -> None:
        self._snapshot = None

    def _on_repo_change(self, kind: str) -> None:
        self._snapshot = None
        self._pending.add(kind)
        self._debounce.start()

    def _flush_changes(self) -> None:
        kinds, self._pending = self._pending, set()
        if kinds and self.ws is not None:
            self.data_changed.emit(kinds)

    def flush(self) -> None:
        """Deliver pending change notifications immediately (used after bulk operations and in tests)."""
        self._debounce.stop()
        self._flush_changes()

    # ------------------------------------------------------------------ services
    @property
    def pdf_engine(self) -> str:
        return self.config.pdf_engine or "auto"

    def export_service(self) -> ExportService:
        return ExportService(self.ws, self.templates, soffice_path=self.config.libreoffice_path or None,
                             today=self.today)

    def variants(self) -> VariantService:
        return VariantService(self.repo)

    def backups(self) -> BackupService:
        return BackupService(self.ws)

    def sync(self) -> SyncService:
        if self._sync is None or self._sync.ws is not self.ws:
            self._sync = SyncService(self.ws, self.secrets, remote_factory=self.remote_factory)
        return self._sync

    def say(self, message: str, timeout: int = 6000) -> None:
        self.status.emit(message, timeout)

    def records(self, kind: RecordKind) -> list:
        return self.repo.list(kind)


class _ListenerBridge(QObject):
    """Turns repository callbacks (possibly from worker threads) into queued Qt signals."""

    changed = Signal(str)

    def relay(self, action: str, record_id: str, kind: str) -> None:  # noqa: ARG002
        self.changed.emit(kind or "")
