"""Remote stores used by synchronisation and cloud backups.

* ``LocalFolderRemote`` — any folder, including a locally synchronised cloud
  folder such as Google Drive for desktop (SYN-09).
* ``MemoryRemote`` — in-memory store with fault injection, for tests.
* ``GoogleDriveRemote`` lives in ``ris.sync.gdrive`` (Drive API v3).
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ris.errors import AuthExpired, NetworkUnavailable, RemoteChanged, SyncError

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,120}(?:/[A-Za-z0-9._-]{1,120})?$")


@dataclass(frozen=True)
class RemoteFile:
    name: str
    size: int
    modified: str
    version: str
    remote_id: str = ""


class RemoteStore(Protocol):
    name: str

    def list_files(self, prefix: str = "") -> list[RemoteFile]: ...
    def stat(self, name: str) -> RemoteFile | None: ...
    def read(self, name: str) -> tuple[bytes, RemoteFile]: ...
    def write(self, name: str, data: bytes, expected_version: str | None = None) -> RemoteFile: ...
    def delete(self, name: str) -> None: ...
    def describe(self) -> str: ...


def check_name(name: str) -> str:
    if not _SAFE_NAME.match(name) or ".." in name:
        raise SyncError(f"Invalid remote file name: {name!r}")
    return name


class LocalFolderRemote:
    name = "folder"

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder).expanduser()

    def describe(self) -> str:
        return f"Folder: {self.folder}"

    def _path(self, name: str) -> Path:
        return self.folder / check_name(name)

    def _info(self, name: str, p: Path) -> RemoteFile:
        st = p.stat()
        digest = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        return RemoteFile(name, st.st_size, str(st.st_mtime_ns), f"{st.st_size}-{digest}")

    def _available(self) -> None:
        if not self.folder.exists():
            raise NetworkUnavailable(f"The sync folder is not available: {self.folder}")

    def list_files(self, prefix: str = "") -> list[RemoteFile]:
        self._available()
        out = []
        base = self.folder
        for p in sorted(base.rglob("*")):
            if p.is_file() and not p.name.endswith(".partial"):
                rel = p.relative_to(base).as_posix()
                if rel.startswith(prefix) and _SAFE_NAME.match(rel):
                    out.append(self._info(rel, p))
        return out

    def stat(self, name: str) -> RemoteFile | None:
        self._available()
        p = self._path(name)
        return self._info(name, p) if p.exists() else None

    def read(self, name: str) -> tuple[bytes, RemoteFile]:
        self._available()
        p = self._path(name)
        if not p.exists():
            raise SyncError(f"Remote file not found: {name}")
        data = p.read_bytes()
        return data, self._info(name, p)

    def write(self, name: str, data: bytes, expected_version: str | None = None) -> RemoteFile:
        self._available()
        p = self._path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        if expected_version is not None:
            cur = self.stat(name)
            if (cur.version if cur else "") != expected_version:
                raise RemoteChanged("The remote copy changed during synchronisation.")
        fd, tmp = tempfile.mkstemp(prefix=".ris-", suffix=".partial", dir=str(p.parent))
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return self._info(name, p)

    def delete(self, name: str) -> None:
        self._available()
        p = self._path(name)
        if p.exists():
            p.unlink()


class MemoryRemote:
    """In-memory remote with failure injection (offline, expired auth, interrupted upload, races)."""

    name = "memory"

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.versions: dict[str, int] = {}
        self.offline = False
        self.auth_expired = False
        self.fail_next_write: Exception | None = None
        self.interrupt_next_write = False
        self.on_before_write = None  # callable(name) to simulate concurrent writers
        self.writes = 0

    def describe(self) -> str:
        return "In-memory test store"

    def _guard(self) -> None:
        if self.offline:
            raise NetworkUnavailable("No network connection.")
        if self.auth_expired:
            raise AuthExpired("Authorisation expired; reconnect the account.")

    def _info(self, name: str) -> RemoteFile:
        return RemoteFile(name, len(self.files[name]), str(self.versions[name]), str(self.versions[name]))

    def list_files(self, prefix: str = "") -> list[RemoteFile]:
        self._guard()
        return [self._info(n) for n in sorted(self.files) if n.startswith(prefix)]

    def stat(self, name: str) -> RemoteFile | None:
        self._guard()
        return self._info(name) if name in self.files else None

    def read(self, name: str) -> tuple[bytes, RemoteFile]:
        self._guard()
        if name not in self.files:
            raise SyncError(f"Remote file not found: {name}")
        return self.files[name], self._info(name)

    def write(self, name: str, data: bytes, expected_version: str | None = None) -> RemoteFile:
        self._guard()
        check_name(name)
        if self.on_before_write is not None:
            cb, self.on_before_write = self.on_before_write, None
            cb(name)
        if self.fail_next_write is not None:
            exc, self.fail_next_write = self.fail_next_write, None
            raise exc
        if expected_version is not None and str(self.versions.get(name, "")) != (expected_version or ""):
            raise RemoteChanged("The remote copy changed during synchronisation.")
        if self.interrupt_next_write:
            self.interrupt_next_write = False
            # An interrupted upload leaves the previous version intact (atomic replace semantics).
            raise NetworkUnavailable("The upload was interrupted.")
        self.files[name] = bytes(data)
        self.versions[name] = self.versions.get(name, 0) + 1
        self.writes += 1
        return self._info(name)

    def delete(self, name: str) -> None:
        self._guard()
        self.files.pop(name, None)
        self.versions.pop(name, None)
