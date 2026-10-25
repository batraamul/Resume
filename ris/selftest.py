"""Environment self-test: verifies dependencies, fonts, templates, storage and a full sample export.

Run with ``python run_application.py --selftest``. Uses temporary folders only.
"""

from __future__ import annotations

import os
import platform
import sqlite3
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from datetime import date
from pathlib import Path


def run(out: Callable[[str], None] = print, gui: bool = True) -> int:
    failures = 0

    def check(name: str, fn, critical: bool = True) -> None:
        nonlocal failures
        t0 = time.time()
        try:
            detail = fn() or "ok"
            out(f"[ OK ] {name}: {detail} ({time.time() - t0:.1f}s)")
        except Exception as exc:  # noqa: BLE001 - report every failure
            if critical:
                failures += 1
            out(f"[{'FAIL' if critical else 'WARN'}] {name}: {type(exc).__name__}: {exc}")
            if os.environ.get("RIS_SELFTEST_TRACE"):
                traceback.print_exc()

    from ris import __version__

    out(f"Resume Intelligence Studio {__version__} self-test")
    out(f"Python {sys.version.split()[0]} on {platform.platform()}")

    def deps():
        import cryptography
        import docx  # noqa: F401
        import pydantic
        import pypdf
        import reportlab

        return (f"pydantic {pydantic.VERSION}, pypdf {pypdf.__version__}, reportlab {reportlab.Version}, "
                f"cryptography {cryptography.__version__}")

    check("Python packages", deps)

    def sqlite_check():
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        return f"SQLite {sqlite3.sqlite_version} with FTS5"

    check("SQLite", sqlite_check)

    def templates():
        from ris.rendering.specs import TemplateLibrary

        lib = TemplateLibrary()
        n = len(lib.list())
        if lib.load_errors or n < 12:
            raise RuntimeError(f"{n} templates; errors: {lib.load_errors}")
        return f"{n} templates"

    check("Templates", templates)

    def fonts_check():
        from ris.rendering import fonts

        fams = fonts.register_fonts()
        missing = [c for c in "ĀāŚśΣΩμ≥±→€" if not (fonts.supports(fonts.font_name("Calibri"), c)
                                                    or fonts.supports(fonts.fallback_name(), c))]
        if missing:
            raise RuntimeError("glyphs missing: " + "".join(missing))
        return f"{len(fams)} font families embedded"

    check("Fonts", fonts_check)

    def lo():
        from ris.rendering.libreoffice import find_soffice, version

        p = find_soffice()
        if p is None:
            return "not found — the built-in PDF engine will be used (LibreOffice is optional)"
        return f"{p} ({version(str(p)) or 'version unknown'})"

    check("LibreOffice (optional)", lo, critical=False)

    def secrets():
        from ris.security.secrets import SecretStore

        return SecretStore().describe()

    check("Credential store", secrets, critical=False)

    def end_to_end():
        from ris.domain.enums import RecordKind
        from ris.rendering.export import ExportOptions, ExportService
        from ris.rendering.specs import TemplateLibrary
        from ris.services.sample import load_sample_profile
        from ris.storage.workspace import Workspace

        with tempfile.TemporaryDirectory(prefix="ris-selftest-") as tmp:
            ws = Workspace(Path(tmp) / "ws", "Self-test", is_sample=True, device_id="selftest").open()
            try:
                load_sample_profile(ws)
                svc = ExportService(ws, TemplateLibrary(), today=date.today())
                var = ws.repo.list(RecordKind.VARIANT)[0]
                res = svc.export_variant(var.id, ExportOptions(formats=("docx", "pdf"), folder=Path(tmp) / "out",
                                                               pdf_engine="builtin"))
                if not res.ok:
                    raise RuntimeError(res.message + " " + "; ".join(c.name for c in (res.report.failures if res.report else [])))
                return f"sample exported and validated ({res.report.page_count} PDF pages)"
            finally:
                ws.close()

    check("Sample export (DOCX + PDF, validated)", end_to_end)

    if gui:
        def qt():
            if not os.environ.get("DISPLAY") and sys.platform.startswith("linux") and not os.environ.get("QT_QPA_PLATFORM"):
                os.environ["QT_QPA_PLATFORM"] = "offscreen"
            from PySide6 import __version__ as pv
            from PySide6.QtPdf import QPdfDocument  # noqa: F401
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance() or QApplication([])
            return f"PySide6 {pv}, platform '{app.platformName()}'"

        check("Desktop toolkit", qt)
    out("Self-test passed." if not failures else f"Self-test found {failures} problem(s).")
    return 0 if not failures else 1
