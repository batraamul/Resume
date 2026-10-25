"""Private temporary directories that are always cleaned up.

Rendering and conversion happen in per-operation folders created with
user-only permissions (0700) and removed in ``finally`` blocks. Stale folders
left by a crash are removed at the next start (``cleanup_stale``).
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

PREFIX = "ris-tmp-"


def temp_root() -> Path:
    return Path(tempfile.gettempdir())


@contextmanager
def private_tempdir(purpose: str = "work") -> Iterator[Path]:
    path = Path(tempfile.mkdtemp(prefix=f"{PREFIX}{purpose}-"))
    try:
        if os.name == "posix":
            os.chmod(path, 0o700)
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def cleanup_stale(max_age_hours: float = 12.0) -> int:
    """Remove RIS temp folders older than ``max_age_hours``. Returns the number removed."""
    removed = 0
    cutoff = time.time() - max_age_hours * 3600
    try:
        entries = list(temp_root().iterdir())
    except OSError:
        return 0
    for p in entries:
        if p.name.startswith(PREFIX) and p.is_dir():
            try:
                if p.stat().st_mtime < cutoff:
                    shutil.rmtree(p, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
    return removed


def live_temp_dirs() -> list[Path]:
    try:
        return [p for p in temp_root().iterdir() if p.name.startswith(PREFIX)]
    except OSError:
        return []
