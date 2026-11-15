"""Fresh Start: empty the current workspace after writing and verifying a full backup.

Records are removed for good when the workspace is not synchronised. With synchronisation switched on they are
deleted in the normal way instead, so that the deletion reaches the other devices rather than the records
coming back at the next sync. Settings, earlier backups and files already exported stay untouched.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ris.backup.backup import BackupService
from ris.errors import RISError

log = logging.getLogger(__name__)

BACKUP_REASON = "before-fresh-start"


class FreshStartError(RISError):
    pass


@dataclass
class FreshStartResult:
    backup_path: Path
    records_removed: int
    purged: bool  # False when synchronisation is on: records are in 'Deleted records' until the next sync

    def summary(self) -> str:
        text = (f"{self.records_removed} record(s) removed. A full backup was saved first:\n{self.backup_path}\n\n"
                "To get the data back, open Backup & Restore and restore that backup.")
        if not self.purged:
            text += ("\n\nSynchronisation is on, so the deletions will be sent to your other devices at the "
                     "next sync.")
        return text


def record_count(ws) -> int:
    return int(ws.repo.count())


def fresh_start(ws) -> FreshStartResult:
    """Back up, verify the backup, then remove every record in the workspace."""
    if getattr(ws, "is_sample", False):
        raise FreshStartError("The sample workspace is demonstration data. Switch to your own workspace to "
                              "start afresh.")
    repo = ws.repo
    before = record_count(ws)
    svc = BackupService(ws)
    try:
        info = svc.create(reason=BACKUP_REASON)
        check = svc.verify(info.path)
    except OSError as exc:
        raise FreshStartError("The safety backup could not be written, so nothing was deleted.", detail=str(exc)) from exc
    if not check.ok:
        raise FreshStartError("The safety backup did not pass verification, so nothing was deleted.",
                              detail="; ".join(check.problems))
    synced = (ws.settings.get("sync.provider") or "off") != "off"
    for rec in repo.list(parent_id=None):
        repo.delete(rec.id)
    for rec in repo.list():  # anything whose parent was already missing
        repo.delete(rec.id)
    if not synced:
        for rec in repo.deleted_records():
            if repo.find(rec.id, include_deleted=True) is not None:
                repo.purge(rec.id)
        with repo.db.transaction():
            repo.db.execute("DELETE FROM variant_versions")
            repo.db.execute("UPDATE exports SET removed = 1")
    log.info("Fresh start: %d record(s) removed (purged=%s)", before, not synced)
    return FreshStartResult(info.path, before, not synced)
