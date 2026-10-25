"""Operating-system-appropriate locations for configuration and personal data.

Personal data never lives in the source tree. Defaults:

* macOS:   ~/Library/Application Support/Resume Intelligence Studio
* Windows: %APPDATA%\\ResumeIntelligenceStudio
* Linux:   $XDG_DATA_HOME/resume-intelligence-studio (data) and
           $XDG_CONFIG_HOME/resume-intelligence-studio (config)

``RIS_DATA_DIR`` and ``RIS_CONFIG_DIR`` override the defaults (used by tests).
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from ris import APP_ID, APP_NAME


def _platform() -> str:
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("win"):
        return "win"
    return "linux"


def default_config_dir() -> Path:
    env = os.environ.get("RIS_CONFIG_DIR")
    if env:
        return Path(env).expanduser()
    plat = _platform()
    if plat == "mac":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if plat == "win":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_ID
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "resume-intelligence-studio"


def default_data_dir() -> Path:
    env = os.environ.get("RIS_DATA_DIR")
    if env:
        return Path(env).expanduser()
    plat = _platform()
    if plat == "mac":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if plat == "win":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_ID
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "resume-intelligence-studio"


def ensure_private_dir(path: Path) -> Path:
    """Create a directory readable only by the current user (POSIX 0700)."""
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        try:
            os.chmod(path, stat.S_IRWXU)
        except OSError:
            pass
    return path


def restrict_file(path: Path) -> None:
    """Make a file readable/writable only by the current user (POSIX 0600)."""
    if os.name == "posix" and path.exists():
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


def is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
