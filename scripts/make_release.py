#!/usr/bin/env python3
"""Build the release ZIP and verify it contains no personal data, secrets or build clutter.

    python scripts/make_release.py [--out dist]

The archive contains source, templates, assets, docs, tests, scripts, launchers and the fictional
sample only. The check fails the build if it finds private paths, databases, backups, keys or
any string listed in RIS_RELEASE_FORBIDDEN (comma-separated; use it for your own name, email and phone).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE_DIRS = ["ris", "templates", "migrations", "config", "assets", "sample_data", "docs", "tests", "scripts",
                "packaging", "examples"]
INCLUDE_FILES = ["README.md", "CHANGELOG.md", "LICENSE.txt", "pyproject.toml", "requirements.txt",
                 "requirements-dev.txt", "requirements-optional.txt", "run_application.py", "launch_macos.command",
                 "launch_linux.sh", "launch_windows.bat"]
EXCLUDE_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".venv", "build", "dist", ".git"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".db", ".sqlite", ".risbackup", ".enc", ".log", ".partial", ".key", ".pem"}
SECRET_PATTERNS = [re.compile(p) for p in (
    r"sk-ant-[A-Za-z0-9_-]{20,}", r"sk-[A-Za-z0-9]{32,}", r"AIza[0-9A-Za-z_-]{35}", r"ya29\.[0-9A-Za-z_-]{20,}",
    r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----", r'"client_secret"\s*:\s*"[^"]{8,}"', r"refresh_token\"\s*:\s*\"1//")]


def iter_files():
    for d in INCLUDE_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(ROOT)
            if p.is_dir() or EXCLUDE_PARTS & set(rel.parts) or p.suffix.lower() in EXCLUDE_SUFFIXES:
                continue
            yield p, rel
    for f in INCLUDE_FILES:
        p = ROOT / f
        if p.exists():
            yield p, p.relative_to(ROOT)


def _readable_text(p: Path) -> str:
    """Text to scan: compressed containers (DOCX, PDF) are opened so their contents are checked too."""
    suffix = p.suffix.lower()
    if suffix == ".docx":
        with zipfile.ZipFile(p) as z:
            return "\n".join(z.read(n).decode("utf-8", errors="ignore") for n in z.namelist()
                             if n.endswith((".xml", ".rels")))
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(p))
        parts = [page.extract_text() or "" for page in reader.pages]
        parts.append(str(reader.metadata or ""))
        return "\n".join(parts) + p.read_bytes().decode("latin-1", errors="ignore")
    if suffix in (".png", ".ttf", ".ico", ".icns", ".jpg", ".jpeg"):
        return p.read_bytes().decode("latin-1", errors="ignore")
    return p.read_text(encoding="utf-8", errors="ignore")


def check(files: list[tuple[Path, Path]]) -> list[str]:
    problems = []
    forbidden = [s.strip().lower() for s in os.environ.get("RIS_RELEASE_FORBIDDEN", "").split(",") if s.strip()]
    for p, rel in files:
        data = _readable_text(p)
        low = data.lower()
        for rx in SECRET_PATTERNS:
            if rx.search(data):
                problems.append(f"{rel}: looks like a secret ({rx.pattern[:20]}…)")
        for s in forbidden:
            if s in low:
                problems.append(f"{rel}: contains a forbidden personal string")
        if rel.parts[0] == "sample_data" and "fictional" not in low:
            problems.append(f"{rel}: sample data must be marked fictional")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist"))
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    from ris import __version__

    files = list(iter_files())
    problems = check(files)
    if problems:
        print("Release check failed:")
        for pr in problems:
            print("  -", pr)
        return 1
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    name = f"ResumeIntelligenceStudio-{__version__}"
    zpath = out / f"{name}.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p, rel in files:
            info = zipfile.ZipInfo.from_file(p, f"{name}/{rel.as_posix()}")
            if rel.name in ("launch_macos.command", "launch_linux.sh", "run_application.py"):
                info.external_attr = (0o755 << 16)
            with open(p, "rb") as fh:
                zf.writestr(info, fh.read(), compress_type=zipfile.ZIP_DEFLATED)
    digest = hashlib.sha256(zpath.read_bytes()).hexdigest()
    (out / f"{name}.zip.sha256").write_text(f"{digest}  {zpath.name}\n", encoding="utf-8")
    print(f"{zpath} ({zpath.stat().st_size:,} bytes, {len(files)} files)\nSHA-256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
