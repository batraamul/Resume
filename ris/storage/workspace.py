"""Workspaces: an isolated folder with its own database, backups and exports.

The real master profile and the fictional sample live in different
workspaces, so test or demo records can never mix with real ones.
"""

from __future__ import annotations

import logging
import re
import shutil
import sqlite3
from pathlib import Path

from ris.config import AppConfig, WorkspaceEntry
from ris.errors import RISError, StorageError
from ris.paths import ensure_private_dir
from ris.storage import migrations
from ris.storage.database import Database
from ris.storage.repository import RecordRepository
from ris.storage.settings import SettingsStore
from ris.util import new_id, utc_now_iso

log = logging.getLogger(__name__)

DB_NAME = "ris.db"
SAMPLE_WORKSPACE_NAME = "Fictional Sample (demo)"


class Workspace:
    def __init__(self, folder: Path, name: str = "Workspace", *, is_sample: bool = False,
                 device_id: str = "", workspace_id: str = "") -> None:
        self.folder = Path(folder)
        self.name = name
        self.is_sample = is_sample
        self.device_id = device_id
        self.id = workspace_id or ""
        self.db = Database(self.folder / DB_NAME)
        self._repo: RecordRepository | None = None
        self._settings: SettingsStore | None = None
        self.migration_warnings: list[str] = []
        self.applied_migrations: list[migrations.Migration] = []

    # ------------------------------------------------------------------ paths
    @property
    def db_path(self) -> Path:
        return self.folder / DB_NAME

    @property
    def backups_dir(self) -> Path:
        return self.folder / "backups"

    @property
    def exports_dir(self) -> Path:
        return self.folder / "exports"

    # ------------------------------------------------------------------ lifecycle
    def open(self) -> Workspace:
        ensure_private_dir(self.folder)
        ensure_private_dir(self.backups_dir)
        ensure_private_dir(self.exports_dir)
        existed = self.db_path.exists() and self.db_path.stat().st_size > 0
        self.db.connect()
        try:
            pend = migrations.pending(self.db)
            if existed and pend and migrations.current_version(self.db) > 0:
                self._pre_migration_snapshot()
            self.applied_migrations = migrations.migrate(self.db)
            self.migration_warnings = migrations.verify_applied(self.db)
        except Exception:
            self.db.close()
            raise
        self._settings = SettingsStore(self.db)
        if not self._settings.get("device.id") and self.device_id:
            self._settings.set("device.id", self.device_id)
        self._repo = RecordRepository(self.db, device_id=self.device_id)
        return self

    def _pre_migration_snapshot(self) -> None:
        from ris.backup.backup import BackupService

        version = migrations.current_version(self.db)
        try:
            BackupService(self).create(reason=f"pre-upgrade-v{version}")
        except Exception as exc:  # pragma: no cover - defensive; upgrade must not proceed silently
            raise StorageError(
                "A safety backup could not be created before upgrading the database; the upgrade was cancelled.",
                detail=str(exc),
            ) from exc

    def close(self) -> None:
        self.db.close()
        self._repo = None
        self._settings = None

    @property
    def repo(self) -> RecordRepository:
        if self._repo is None:
            raise RISError("The workspace is not open.")
        return self._repo

    @property
    def settings(self) -> SettingsStore:
        if self._settings is None:
            raise RISError("The workspace is not open.")
        return self._settings

    def __enter__(self) -> Workspace:
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:40] or "workspace"


class WorkspaceManager:
    """Registry of workspaces in the application config."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @property
    def data_dir(self) -> Path:
        return self.config.resolved_data_dir()

    def entries(self) -> list[WorkspaceEntry]:
        return list(self.config.workspaces)

    def folder_of(self, entry: WorkspaceEntry) -> Path:
        return self.config.workspace_folder(entry)

    def create(self, name: str, *, is_sample: bool = False, activate: bool = False) -> WorkspaceEntry:
        name = name.strip() or "My Profile"
        folder_rel = Path("workspaces") / f"{_slug(name)}-{new_id()[:6]}"
        entry = WorkspaceEntry(id=new_id()[:12], name=name, folder=str(folder_rel), is_sample=is_sample,
                               created_at=utc_now_iso())
        ensure_private_dir(self.data_dir / folder_rel)
        self.config.workspaces.append(entry)
        if activate or not self.config.active_workspace_id:
            self.config.active_workspace_id = entry.id
        self.config.save()
        return entry

    def ensure_default(self) -> WorkspaceEntry:
        real = [w for w in self.config.workspaces if not w.is_sample]
        if real:
            if not self.config.find_workspace(self.config.active_workspace_id):
                self.config.active_workspace_id = real[0].id
                self.config.save()
            return self.config.find_workspace(self.config.active_workspace_id) or real[0]
        return self.create("My Profile", activate=True)

    def open(self, entry: WorkspaceEntry) -> Workspace:
        ws = Workspace(self.folder_of(entry), entry.name, is_sample=entry.is_sample,
                       device_id=self.config.device_id, workspace_id=entry.id)
        return ws.open()

    def active_entry(self) -> WorkspaceEntry:
        entry = self.config.find_workspace(self.config.active_workspace_id)
        return entry or self.ensure_default()

    def set_active(self, workspace_id: str) -> None:
        if not self.config.find_workspace(workspace_id):
            raise RISError("That workspace is not registered.")
        self.config.active_workspace_id = workspace_id
        self.config.save()

    def rename(self, workspace_id: str, new_name: str) -> None:
        entry = self.config.find_workspace(workspace_id)
        if entry is None:
            raise RISError("That workspace is not registered.")
        entry.name = new_name.strip() or entry.name
        self.config.save()

    def remove_from_list(self, workspace_id: str) -> WorkspaceEntry:
        """Forget a workspace without touching its files."""
        entry = self.config.find_workspace(workspace_id)
        if entry is None:
            raise RISError("That workspace is not registered.")
        self.config.workspaces = [w for w in self.config.workspaces if w.id != workspace_id]
        if self.config.active_workspace_id == workspace_id:
            self.config.active_workspace_id = self.config.workspaces[0].id if self.config.workspaces else ""
        self.config.save()
        return entry

    def delete_files(self, workspace_id: str) -> None:
        """Permanently delete a workspace folder (caller must confirm with the user)."""
        entry = self.remove_from_list(workspace_id)
        folder = self.folder_of(entry)
        if folder.exists():
            shutil.rmtree(folder)

    def sample_entry(self) -> WorkspaceEntry | None:
        return next((w for w in self.config.workspaces if w.is_sample), None)

    def ensure_sample(self) -> WorkspaceEntry:
        """Create the fictional sample workspace (once) and load the sample profile."""
        entry = self.sample_entry()
        if entry is not None:
            return entry
        entry = self.create(SAMPLE_WORKSPACE_NAME, is_sample=True)
        ws = self.open(entry)
        try:
            from ris.services.sample import load_sample_profile

            load_sample_profile(ws)
        finally:
            ws.close()
        return entry

    # ------------------------------------------------------------------ relocation
    def relocate(self, new_dir: Path) -> Path:
        """Copy the whole data directory to ``new_dir``, verify, then switch to it.

        The old directory is left in place; the caller offers to delete it.
        The caller must close any open workspace first.
        """
        old = self.data_dir.resolve()
        new_dir = Path(new_dir).expanduser().resolve()
        if new_dir == old:
            raise RISError("The new location is the same as the current one.")
        if old in new_dir.parents:
            raise RISError("The new location cannot be inside the current data folder.")
        if new_dir.exists() and any(new_dir.iterdir()):
            raise RISError("Choose an empty folder for the new data location.")
        ensure_private_dir(new_dir)
        for item in old.iterdir():
            if item.name in ("tmp",):
                continue
            dest = new_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        # Verify every relative workspace database opened and matches record counts.
        for entry in self.config.workspaces:
            if Path(entry.folder).is_absolute():
                continue
            src_db = old / entry.folder / DB_NAME
            dst_db = new_dir / entry.folder / DB_NAME
            if src_db.exists():
                if not dst_db.exists():
                    raise StorageError(f"Copy verification failed for workspace '{entry.name}'.")
                if _count_records(src_db) != _count_records(dst_db) or _integrity(dst_db) != "ok":
                    raise StorageError(f"Copy verification failed for workspace '{entry.name}'.")
        self.config.data_dir = str(new_dir)
        self.config.save()
        return old


def _count_records(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        try:
            return int(conn.execute("SELECT COUNT(*) FROM records").fetchone()[0])
        except sqlite3.Error:
            return -1
    finally:
        conn.close()


def _integrity(db_path: Path) -> str:
    conn = sqlite3.connect(str(db_path))
    try:
        return str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        conn.close()
