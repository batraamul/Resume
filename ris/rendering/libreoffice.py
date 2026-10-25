"""Optional LibreOffice DOCX→PDF conversion.

LibreOffice gives a PDF with exactly the DOCX layout (and tagged PDF
structure). It runs headless with a throw-away user profile, a timeout, and
output in a private temporary folder. If LibreOffice is missing, callers use
the built-in PDF renderer and say so; nothing pretends conversion succeeded.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from ris.errors import ConversionError
from ris.security.tempfiles import private_tempdir

log = logging.getLogger(__name__)

_CANDIDATES = {
    "darwin": ["/Applications/LibreOffice.app/Contents/MacOS/soffice",
               str(Path.home() / "Applications/LibreOffice.app/Contents/MacOS/soffice")],
    "win32": [r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"],
}
TAGGED_FILTER = ('pdf:writer_pdf_Export:{"UseTaggedPDF":{"type":"boolean","value":"true"},'
                 '"ExportBookmarks":{"type":"boolean","value":"true"}}')


def find_soffice(explicit: str | None = None) -> Path | None:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    env = os.environ.get("RIS_SOFFICE")
    if env:
        candidates.append(env)
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    candidates.extend(_CANDIDATES.get(sys.platform, []))
    for c in candidates:
        p = Path(c)
        if p.is_file() and os.access(p, os.X_OK):
            return p
    return None


@lru_cache(maxsize=8)
def version(soffice: str) -> str:
    try:
        out = subprocess.run([soffice, "--version"], capture_output=True, text=True, timeout=30, check=False)
        m = re.search(r"(\d+\.\d+(?:\.\d+)*)", out.stdout or "")
        return m.group(1) if m else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _supports_json_filter(ver: str) -> bool:
    try:
        major, minor = (int(x) for x in ver.split(".")[:2])
    except ValueError:
        return False
    return (major, minor) >= (7, 4)


def convert_docx_to_pdf(docx: Path, out_pdf: Path, soffice: Path, timeout: int = 120) -> Path:
    """Convert ``docx`` to ``out_pdf``. Raises ConversionError with a readable reason on failure."""
    docx = Path(docx)
    out_pdf = Path(out_pdf)
    ver = version(str(soffice))
    filters = [TAGGED_FILTER, "pdf"] if _supports_json_filter(ver) else ["pdf"]
    last_err = ""
    with private_tempdir("lo") as work:
        profile = work / "profile"
        outdir = work / "out"
        outdir.mkdir()
        for flt in filters:
            cmd = [str(soffice), "--headless", "--norestore", "--nolockcheck", "--nodefault", "--nofirststartwizard",
                   f"-env:UserInstallation={profile.as_uri()}", "--convert-to", flt, "--outdir", str(outdir), str(docx)]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False,
                                      env={**os.environ, "HOME": str(work)})
            except subprocess.TimeoutExpired:
                raise ConversionError(f"LibreOffice did not finish within {timeout} seconds.") from None
            except OSError as exc:
                raise ConversionError("LibreOffice could not be started.", detail=str(exc)) from exc
            produced = outdir / (docx.stem + ".pdf")
            if proc.returncode == 0 and produced.exists() and produced.stat().st_size > 0:
                out_pdf.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(produced), str(out_pdf))
                return out_pdf
            last_err = (proc.stderr or proc.stdout or "").strip()[-300:]
    raise ConversionError("LibreOffice could not convert the document to PDF.", detail=last_err)
