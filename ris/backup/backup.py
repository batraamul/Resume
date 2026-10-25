"""Backups and restore for a workspace (STO-03/04/06).

A backup is a ZIP archive holding a consistent SQLite snapshot (made with the
SQLite backup API) and a manifest with counts and a SHA-256 of the database.
It can be encrypted (AES-256-GCM). Restore always verifies the archive first
and takes a recoverable "pre-restore" snapshot of the current data before
replacing anything.
"""

from __future__ import annotations

import io
import json
import logging
import os
import sqlite3
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ris import __version__
from ris.backup import crypto
from ris.backup.integrity import IntegrityReport, check_file
from ris.errors import BackupError, RestoreError
from ris.paths import ensure_private_dir, restrict_file
from ris.security.tempfiles import private_tempdir
from ris.storage import migrations
from ris.storage.database import Database
from ris.util import sha256_file, utc_now_iso

log = logging.getLogger(__name__)

FORMAT_ID = "ris-backup"
FORMAT_VERSION = 1
EXT = ".risbackup"
ENC_EXT = ".risbackup.enc"
ALLOWED_MEMBERS = {"manifest.json", "ris.db"}
MAX_MEMBER_BYTES = 512 * 1024 * 1024
AUTO_REASONS = ("auto", "on-exit", "pre-restore", "pre-upgrade", "pre-sync")


@dataclass
class BackupInfo:
    path: Path
    created_at: str
    reason: str
    encrypted: bool
    size: int
    manifest: dict = field(default_factory=dict)

    @property
    def record_count(self) -> int:
        return int(self.manifest.get("records", {}).get("total", 0)) if self.manifest else 0

    @property
    def is_automatic(self) -> bool:
        return any(self.reason.startswith(r) for r in AUTO_REASONS)


@dataclass
class VerifyResult:
    ok: bool
    manifest: dict
    integrity: IntegrityReport | None
    problems: list[str]


def _counts(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT kind, COUNT(*) FROM records WHERE deleted = 0 GROUP BY kind").fetchall()
        total = sum(n for _, n in rows)
        conf = conn.execute("SELECT COUNT(*) FROM records WHERE deleted = 0 AND confidentiality = 'confidential'").fetchone()[0]
        return {"total": total, "by_kind": dict(rows), "confidential": conf}
    finally:
        conn.close()


def _strip_confidential(db_path: Path) -> int:
    """Remove confidential records and their descendants from a database copy (for cloud copies)."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        ids = [r[0] for r in conn.execute("SELECT id FROM records WHERE confidentiality = 'confidential'")]
        removed = 0
        stack = list(ids)
        doomed: set[str] = set()
        while stack:
            rid = stack.pop()
            if rid in doomed:
                continue
            doomed.add(rid)
            stack.extend(r[0] for r in conn.execute("SELECT id FROM records WHERE parent_id = ?", (rid,)))
        for rid in doomed:
            conn.execute("DELETE FROM records_fts WHERE record_id = ?", (rid,))
        for rid in ids:
            conn.execute("DELETE FROM records WHERE id = ?", (rid,))
            removed += 1
        # Exports log can reveal file names; cloud-safe copies drop it.
        conn.execute("DELETE FROM exports")
        conn.execute("DELETE FROM audit_log")
        conn.commit()
        conn.execute("VACUUM")
        return len(doomed)
    finally:
        conn.close()


class BackupService:
    def __init__(self, workspace) -> None:
        self.ws = workspace

    @property
    def folder(self) -> Path:
        return ensure_private_dir(self.ws.backups_dir)

    # ------------------------------------------------------------------ create
    def build_archive(self, *, reason: str = "manual", include_confidential: bool = True) -> tuple[bytes, dict]:
        """Return (zip bytes, manifest) for the current workspace database."""
        with private_tempdir("backup") as tmp:
            snap = tmp / "ris.db"
            self.ws.db.backup_to(snap)
            stripped = 0
            if not include_confidential:
                stripped = _strip_confidential(snap)
            manifest = {
                "format": FORMAT_ID, "format_version": FORMAT_VERSION, "app_version": __version__,
                "created_at": utc_now_iso(), "reason": reason,
                "schema_version": migrations.current_version(self.ws.db),
                "workspace": {"name": self.ws.name, "is_sample": bool(self.ws.is_sample)},
                "includes_confidential": include_confidential, "confidential_records_removed": stripped,
                "db_sha256": sha256_file(snap), "records": _counts(snap),
            }
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))
                zf.write(snap, "ris.db")
            return buf.getvalue(), manifest

    def create(self, *, reason: str = "manual", passphrase: str | None = None, dest_dir: Path | None = None,
               include_confidential: bool = True) -> BackupInfo:
        data, manifest = self.build_archive(reason=reason, include_confidential=include_confidential)
        encrypted = bool(passphrase)
        if encrypted:
            data = crypto.encrypt(data, passphrase or "", meta={"created_at": manifest["created_at"],
                                                                 "reason": reason, "app_version": __version__})
        folder = ensure_private_dir(Path(dest_dir)) if dest_dir else self.folder
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        safe_reason = "".join(ch for ch in reason if ch.isalnum() or ch in "-_")[:30] or "backup"
        path = folder / f"{stamp}-{safe_reason}{ENC_EXT if encrypted else EXT}"
        n = 2
        while path.exists():
            path = folder / f"{stamp}-{safe_reason}-{n}{ENC_EXT if encrypted else EXT}"
            n += 1
        tmp = path.with_name(path.name + ".partial")
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        restrict_file(path)
        log.info("Backup created (%s, %d bytes, encrypted=%s)", reason, len(data), encrypted)
        return BackupInfo(path, manifest["created_at"], reason, encrypted, len(data), manifest)

    # ------------------------------------------------------------------ inspect
    def list(self, folder: Path | None = None) -> list[BackupInfo]:
        folder = folder or self.folder
        out: list[BackupInfo] = []
        for p in sorted(folder.glob("*.risbackup*"), reverse=True):
            if p.name.endswith(".partial"):
                continue
            try:
                out.append(self.describe(p))
            except BackupError:
                out.append(BackupInfo(p, "", "unreadable", p.name.endswith(ENC_EXT), p.stat().st_size, {}))
        return out

    def describe(self, path: Path) -> BackupInfo:
        path = Path(path)
        head = path.read_bytes()[:200_000]
        if crypto.is_encrypted(head):
            header = crypto.read_header(head)
            meta = header.get("meta", {})
            return BackupInfo(path, meta.get("created_at", ""), meta.get("reason", ""), True, path.stat().st_size, {})
        try:
            with zipfile.ZipFile(path) as zf:
                manifest = json.loads(zf.read("manifest.json"))
        except (zipfile.BadZipFile, KeyError, ValueError) as exc:
            raise BackupError("This backup file is damaged or not a backup.") from exc
        return BackupInfo(path, manifest.get("created_at", ""), manifest.get("reason", ""), False,
                          path.stat().st_size, manifest)

    def _open_zip_bytes(self, path: Path, passphrase: str | None) -> bytes:
        blob = Path(path).read_bytes()
        if crypto.is_encrypted(blob[:16]):
            if not passphrase:
                raise RestoreError("This backup is encrypted; enter its passphrase.")
            data, _ = crypto.decrypt(blob, passphrase)
            return data
        return blob

    def _extract(self, zip_bytes: bytes, dest: Path) -> dict:
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile as exc:
            raise RestoreError("The backup archive is damaged.") from exc
        with zf:
            names = zf.namelist()
            for info in zf.infolist():
                name = info.filename
                if name not in ALLOWED_MEMBERS or name.startswith(("/", "\\")) or ".." in name:
                    raise RestoreError(f"The backup contains an unexpected file ('{name[:40]}') and was rejected.")
                if info.file_size > MAX_MEMBER_BYTES:
                    raise RestoreError("The backup contains an oversized file and was rejected.")
            if "manifest.json" not in names or "ris.db" not in names:
                raise RestoreError("The backup is incomplete.")
            manifest = json.loads(zf.read("manifest.json"))
            if manifest.get("format") != FORMAT_ID:
                raise RestoreError("This is not a Resume Intelligence Studio backup.")
            if int(manifest.get("format_version", 0)) > FORMAT_VERSION:
                raise RestoreError("This backup was made by a newer version of the application.")
            with zf.open("ris.db") as src, open(dest, "wb") as out:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
        return manifest

    def verify(self, path: Path, passphrase: str | None = None) -> VerifyResult:
        problems: list[str] = []
        try:
            zip_bytes = self._open_zip_bytes(path, passphrase)
        except (RestoreError, crypto.DecryptionError) as exc:
            return VerifyResult(False, {}, None, [getattr(exc, "user_message", str(exc))])
        with private_tempdir("verify") as tmp:
            dbp = tmp / "ris.db"
            try:
                manifest = self._extract(zip_bytes, dbp)
            except RestoreError as exc:
                return VerifyResult(False, {}, None, [exc.user_message])
            if sha256_file(dbp) != manifest.get("db_sha256"):
                problems.append("The database inside the backup does not match its recorded checksum.")
            integrity = check_file(dbp)
            problems.extend(integrity.problems)
            schema = int(manifest.get("schema_version", 0))
            if schema > migrations.latest_version():
                problems.append("The backup uses a newer database schema than this application supports.")
        return VerifyResult(not problems, manifest, integrity, problems)

    # ------------------------------------------------------------------ restore
    def restore(self, path: Path, passphrase: str | None = None, *, keep_local_confidential: bool | None = None) -> dict:
        """Replace the workspace database with the backup's. Returns a summary dict.

        A pre-restore snapshot of the current data is always created first.
        When the backup excludes confidential records (a cloud copy), local
        confidential records are kept unless told otherwise.
        """
        result = self.verify(path, passphrase)
        if not result.ok:
            raise RestoreError("The backup failed verification and was not restored: " + "; ".join(result.problems[:3]))
        manifest = result.manifest
        if keep_local_confidential is None:
            keep_local_confidential = not manifest.get("includes_confidential", True)
        snapshot = self.create(reason="pre-restore")
        zip_bytes = self._open_zip_bytes(path, passphrase)
        with private_tempdir("restore") as tmp:
            new_db = tmp / "ris.db"
            self._extract(zip_bytes, new_db)
            staged = Database(new_db)
            try:
                migrations.migrate(staged)
                if keep_local_confidential:
                    self._copy_confidential_into(staged)
            finally:
                staged.close()
            target = self.ws.db_path
            staging = target.with_name(target.name + ".restoring")
            data = new_db.read_bytes()
            self.ws.close()
            try:
                with open(staging, "wb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                for suffix in ("-journal", "-wal", "-shm"):
                    side = target.with_name(target.name + suffix)
                    if side.exists():
                        side.unlink()
                os.replace(staging, target)
                restrict_file(target)
            finally:
                if staging.exists():
                    staging.unlink()
                self.ws.open()
        log.info("Workspace restored from backup")
        return {"restored_from": str(path), "pre_restore_snapshot": str(snapshot.path),
                "records": manifest.get("records", {}), "kept_local_confidential": bool(keep_local_confidential)}

    def _copy_confidential_into(self, staged: Database) -> int:
        """Copy local confidential records (and descendants) into a staged database."""
        src = self.ws.db
        conf = [r["id"] for r in src.query("SELECT id FROM records WHERE confidentiality = 'confidential'")]
        ids: list[str] = []
        stack = list(conf)
        while stack:
            rid = stack.pop(0)
            if rid in ids:
                continue
            ids.append(rid)
            stack.extend(r["id"] for r in src.query("SELECT id FROM records WHERE parent_id = ?", (rid,)))
        n = 0
        cols = [r[1] for r in src.query("PRAGMA table_info(records)")]
        for rid in ids:
            row = src.query_one("SELECT * FROM records WHERE id = ?", (rid,))
            if row is None:
                continue
            parent = row["parent_id"]
            if parent and staged.query_one("SELECT 1 FROM records WHERE id = ?", (parent,)) is None and parent not in ids:
                continue
            placeholders = ",".join("?" * len(cols))
            staged.execute(f"INSERT OR REPLACE INTO records ({','.join(cols)}) VALUES ({placeholders})",
                           tuple(row[c] for c in cols))
            n += 1
        if n:
            from ris.backup.integrity import rebuild_search_index
            from ris.storage.repository import RecordRepository

            rebuild_search_index(RecordRepository(staged))
        return n

    # ------------------------------------------------------------------ automation
    def prune(self, keep_last: int | None = None) -> list[Path]:
        keep = int(keep_last if keep_last is not None else self.ws.settings.get("backup.keep_last"))
        autos = [b for b in self.list() if b.is_automatic]
        removed: list[Path] = []
        for b in autos[max(keep, 1):]:
            try:
                b.path.unlink()
                removed.append(b.path)
            except OSError:
                pass
        return removed

    def auto_backup_if_due(self, now: datetime | None = None, reason: str = "auto") -> BackupInfo | None:
        s = self.ws.settings
        if not s.get("backup.auto_enabled"):
            return None
        hours = float(s.get("backup.interval_hours") or 24)
        last = s.get("backup.last_auto_at") or ""
        now = now or datetime.now(UTC)
        if last:
            try:
                last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                if now - last_dt < timedelta(hours=hours):
                    return None
            except ValueError:
                pass
        if self.ws.repo.count() == 0:
            return None
        info = self.create(reason=reason)
        s.set("backup.last_auto_at", now.replace(microsecond=0).isoformat().replace("+00:00", "Z"))
        self.prune()
        return info
