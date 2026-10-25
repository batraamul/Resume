"""Installing a verified update.

The installer is started only after the user agrees, and the application then closes so files can be
replaced. Your data folder is never touched by an update.

* Windows: the per-user installer runs silently, replaces the program files and restarts the application.
* macOS: a helper waits for the application to quit, copies the new app from the disk image over the old
  one, and reopens it. If the application folder is not writable, the disk image is opened instead.
* Linux (.tar.gz folder): a helper swaps the program folder after the application quits and restarts it.
* Linux (.deb): the package is opened in the system's software installer (administrator rights needed).
* Running from source: the verified installer is saved and its folder is opened.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ris.update.manifest import UpdateAsset, UpdateError


def install_kind() -> str:
    """How this copy was installed: windows-installer, macos-app, linux-deb, linux-folder or source."""
    if not getattr(sys, "frozen", False):
        return "source"
    exe = Path(sys.executable).resolve()
    if sys.platform.startswith("win"):
        return "windows-installer"
    if sys.platform == "darwin":
        return "macos-app"
    if str(exe).startswith("/opt/resume-intelligence-studio/"):
        return "linux-deb"
    return "linux-folder"


def app_bundle() -> Path | None:
    """The .app bundle that contains this executable (macOS)."""
    for parent in Path(sys.executable).resolve().parents:
        if parent.suffix == ".app":
            return parent
    return None


@dataclass
class InstallPlan:
    description: str
    command: list[str]
    quit_app: bool


def plan_install(installer: Path, asset: UpdateAsset, *, pid: int | None = None,
                 kind: str | None = None) -> InstallPlan:
    """Work out (without running anything) how to install a downloaded, verified update."""
    pid = pid or os.getpid()
    kind = kind or install_kind()
    installer = Path(installer)
    if kind == "windows-installer" and asset.kind == "windows-installer":
        # The installer's [Run] section starts the new version after a silent install; Restart Manager restarts
        # are turned off so the application cannot be started twice.
        return InstallPlan("The installer will update Resume Intelligence Studio and restart it.",
                           [str(installer), "/SP-", "/SILENT", "/NOCANCEL", "/NORESTART", "/CLOSEAPPLICATIONS",
                            "/NORESTARTAPPLICATIONS"], True)
    if kind == "macos-app" and asset.kind == "macos-dmg":
        bundle = app_bundle()
        if bundle is not None and os.access(bundle.parent, os.W_OK):
            script = _write_script(_MAC_SCRIPT.format(pid=pid, dmg=shlex.quote(str(installer)),
                                                      target=shlex.quote(str(bundle)),
                                                      name=shlex.quote(bundle.name)))
            return InstallPlan("The application will close, update itself from the disk image and reopen.",
                               ["/bin/sh", str(script)], True)
        return InstallPlan("The disk image will open. Drag Resume Intelligence Studio into Applications to replace "
                           "the old version.", ["open", str(installer)], False)
    if kind == "linux-folder" and asset.kind == "linux-tar":
        app_dir = Path(sys.executable).resolve().parent
        if not os.access(app_dir.parent, os.W_OK):
            raise UpdateError("The program folder is not writable; extract the new version manually.")
        staging = Path(tempfile.mkdtemp(prefix=".ris-update-", dir=str(app_dir.parent)))
        _safe_extract(installer, staging)
        new_root = next((p for p in staging.iterdir() if p.is_dir()), None)
        if new_root is None or not (new_root / Path(sys.executable).name).exists():
            raise UpdateError("The update archive does not contain the application.")
        script = _write_script(_LINUX_SCRIPT.format(pid=pid, old=shlex.quote(str(app_dir)),
                                                    new=shlex.quote(str(new_root)), staging=shlex.quote(str(staging)),
                                                    exe=shlex.quote(str(app_dir / Path(sys.executable).name))))
        return InstallPlan("The application will close, replace its program folder and restart.",
                           ["/bin/sh", str(script)], True)
    if kind == "source":
        opener = "explorer" if sys.platform.startswith("win") else ("open" if sys.platform == "darwin" else "xdg-open")
        return InstallPlan("This copy runs from source code, so it cannot replace itself. The verified installer was "
                           f"saved in {installer.parent}; run it, or update your source checkout.",
                           [opener, str(installer.parent)], False)
    if asset.kind == "linux-deb":
        return InstallPlan("The package will open in your software installer. If nothing opens, run: sudo apt "
                           f"install {shlex.quote(str(installer))}", ["xdg-open", str(installer)], False)
    raise UpdateError("This copy cannot install updates automatically (for example when running from source). "
                      "Download the new version from the release page.")


def run_plan(plan: InstallPlan) -> None:
    """Start the installer or helper detached from this process."""
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                    "close_fds": True}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(plan.command, **kwargs)  # noqa: S603 - fixed command built from verified paths
    except OSError as exc:
        raise UpdateError("The installer could not be started.", detail=str(exc)) from exc


def _write_script(body: str) -> Path:
    fd, path = tempfile.mkstemp(prefix="ris-update-", suffix=".sh")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, 0o700)
    return Path(path)


def _safe_extract(archive: Path, dest: Path) -> None:
    with tarfile.open(archive, "r:gz") as tf:
        for m in tf.getmembers():
            root = str(dest.resolve())
            target = (dest / m.name).resolve()
            unsafe = not str(target).startswith(root + os.sep)
            if m.issym() or m.islnk():
                unsafe = unsafe or not str((target.parent / m.linkname).resolve()).startswith(root)
            if unsafe:
                raise UpdateError("The update archive contains unsafe paths.")
        try:
            tf.extractall(dest, filter="tar")
        except TypeError:  # Python without extraction filters (members were checked above)
            tf.extractall(dest)  # noqa: S202


_MAC_SCRIPT = """#!/bin/sh
# Resume Intelligence Studio updater: wait for the app to quit, replace it from the verified disk image, reopen.
while kill -0 {pid} 2>/dev/null; do sleep 1; done
MNT=$(mktemp -d /tmp/ris-update-mnt.XXXXXX)
hdiutil attach -nobrowse -readonly -mountpoint "$MNT" {dmg} >/dev/null || exit 1
if [ -d "$MNT"/{name} ]; then
  rm -rf {target}.old
  mv {target} {target}.old && ditto "$MNT"/{name} {target} && rm -rf {target}.old || mv {target}.old {target}
fi
hdiutil detach "$MNT" >/dev/null
open {target}
rm -f "$0"
"""

_LINUX_SCRIPT = """#!/bin/sh
# Resume Intelligence Studio updater: wait for the app to quit, swap in the new program folder, restart.
while kill -0 {pid} 2>/dev/null; do sleep 1; done
rm -rf {old}.old
mv {old} {old}.old && mv {new} {old} && rm -rf {old}.old || mv {old}.old {old}
rm -rf {staging}
nohup {exe} >/dev/null 2>&1 &
rm -f "$0"
"""
