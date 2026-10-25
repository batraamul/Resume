"""Synchronisation service: provider selection, status, retries, cloud snapshot backups (SYN-01/03/06/07).

Snapshot backup (a complete, verifiable archive uploaded to the cloud) is kept
distinct from record synchronisation (merging individual records across
devices). Cloud copies exclude confidential records unless the user opts in,
and are encrypted when a sync passphrase is set.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from ris.backup import crypto
from ris.backup.backup import ENC_EXT, EXT, BackupService
from ris.errors import AuthExpired, NetworkUnavailable, SyncError
from ris.security.secrets import SecretStore
from ris.sync.engine import SyncEngine, SyncReport
from ris.sync.remote import LocalFolderRemote, RemoteFile, RemoteStore
from ris.util import utc_now_iso

log = logging.getLogger(__name__)
BACKUP_PREFIX = "ris-backups/"
PASSPHRASE_SECRET = "cloud_passphrase"


@dataclass
class SyncStatus:
    provider: str
    configured: bool
    description: str
    last_success: str
    last_error: str
    last_backup: str
    encrypted: bool
    include_confidential: bool


class SyncService:
    def __init__(self, workspace, secrets: SecretStore, *, remote_factory=None) -> None:
        self.ws = workspace
        self.secrets = secrets
        self._remote_factory = remote_factory  # tests and the Google Drive provider inject remotes
        self._remote: RemoteStore | None = None

    # ------------------------------------------------------------------ configuration
    @property
    def settings(self):
        return self.ws.settings

    @property
    def provider(self) -> str:
        return self.settings.get("sync.provider") or "off"

    def configure_folder(self, folder: Path) -> None:
        folder = Path(folder).expanduser()
        if not folder.exists():
            raise SyncError("Choose an existing folder (for example your Google Drive for desktop folder).")
        self.settings.set("sync.provider", "folder")
        self.settings.set("sync.folder_path", str(folder))
        self._remote = None

    def configure_remote(self, provider: str, remote: RemoteStore) -> None:
        self.settings.set("sync.provider", provider)
        self._remote = remote

    def disable(self) -> None:
        self.settings.set("sync.provider", "off")
        self._remote = None

    def passphrase(self) -> str | None:
        return self.secrets.get(f"{PASSPHRASE_SECRET}:{self.ws.id or self.ws.name}")

    def set_passphrase(self, value: str) -> bool:
        if value:
            crypto.check_passphrase(value)
        return self.secrets.set(f"{PASSPHRASE_SECRET}:{self.ws.id or self.ws.name}", value)

    def remote(self) -> RemoteStore:
        if self._remote is not None:
            return self._remote
        if self._remote_factory is not None:
            self._remote = self._remote_factory(self.provider)
            return self._remote
        if self.provider == "folder":
            path = self.settings.get("sync.folder_path")
            if not path:
                raise SyncError("No sync folder is configured.")
            self._remote = LocalFolderRemote(Path(path))
            return self._remote
        if self.provider == "gdrive":
            from ris.sync.gdrive import drive_remote_from_settings

            self._remote = drive_remote_from_settings(self.ws, self.secrets)
            return self._remote
        raise SyncError("Synchronisation is turned off.")

    def status(self) -> SyncStatus:
        configured = self.provider != "off"
        desc = "Off — everything stays on this computer."
        if configured:
            try:
                desc = self.remote().describe()
            except SyncError as exc:
                desc = exc.user_message
        return SyncStatus(self.provider, configured, desc, self.settings.get("sync.last_success_at") or "",
                          self.settings.get("sync.last_error") or "", self.settings.get("sync.last_backup_at") or "",
                          bool(self.passphrase()), bool(self.settings.get("sync.include_confidential")))

    # ------------------------------------------------------------------ helpers
    def _with_retry(self, fn, attempts: int = 3, delay: float = 0.5):
        last: Exception | None = None
        for i in range(attempts):
            try:
                return fn()
            except NetworkUnavailable as exc:
                last = exc
                if i < attempts - 1:
                    time.sleep(delay * (2 ** i))
            except AuthExpired:
                raise
        assert last is not None
        raise last

    def _record_error(self, exc: Exception) -> None:
        msg = getattr(exc, "user_message", str(exc))
        self.settings.set("sync.last_error", f"{utc_now_iso()} — {msg}")
        log.warning("Sync failed: %s", type(exc).__name__)

    # ------------------------------------------------------------------ record sync
    def engine(self) -> SyncEngine:
        return SyncEngine(self.ws.repo, self.remote(), passphrase=self.passphrase(),
                          include_confidential=bool(self.settings.get("sync.include_confidential")),
                          device_id=self.ws.device_id)

    def sync_now(self, retry_delay: float = 0.5) -> SyncReport:
        try:
            report = self._with_retry(lambda: self.engine().sync(), delay=retry_delay)
        except Exception as exc:
            self._record_error(exc)
            raise
        self.settings.set("sync.last_success_at", utc_now_iso())
        self.settings.set("sync.last_error", "")
        return report

    # ------------------------------------------------------------------ cloud snapshot backups
    def upload_backup(self, *, allow_unencrypted: bool = False, retry_delay: float = 0.5) -> RemoteFile:
        passphrase = self.passphrase()
        if not passphrase and not allow_unencrypted:
            raise SyncError("Set a sync passphrase to encrypt cloud backups, or explicitly allow an unencrypted upload.")
        include_conf = bool(self.settings.get("sync.include_confidential"))
        data, manifest = BackupService(self.ws).build_archive(reason="cloud", include_confidential=include_conf)
        if passphrase:
            data = crypto.encrypt(data, passphrase, meta={"created_at": manifest["created_at"], "reason": "cloud"})
        stamp = manifest["created_at"].replace(":", "").replace("-", "")
        name = f"{BACKUP_PREFIX}{stamp}{ENC_EXT if passphrase else EXT}"
        try:
            info = self._with_retry(lambda: self.remote().write(name, data), delay=retry_delay)
        except Exception as exc:
            self._record_error(exc)
            raise
        self.settings.set("sync.last_backup_at", utc_now_iso())
        return info

    def list_cloud_backups(self) -> list[RemoteFile]:
        files = self._with_retry(lambda: self.remote().list_files(BACKUP_PREFIX))
        return sorted(files, key=lambda f: f.name, reverse=True)

    def restore_cloud_backup(self, name: str) -> dict:
        data, _ = self._with_retry(lambda: self.remote().read(name))
        local = self.ws.backups_dir / ("downloaded-" + Path(name).name)
        local.write_bytes(data)
        try:
            return BackupService(self.ws).restore(local, self.passphrase())
        finally:
            local.unlink(missing_ok=True)

    def delete_cloud_backup(self, name: str) -> None:
        """Explicitly delete a cloud copy. Local data and local backups are not affected."""
        if not name.startswith(BACKUP_PREFIX):
            raise SyncError("Only cloud backup files can be deleted here.")
        self._with_retry(lambda: self.remote().delete(name))
