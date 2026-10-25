# PyInstaller specification for Resume Intelligence Studio.
#   pyinstaller packaging/ris.spec --noconfirm --clean
# Produces dist/ResumeIntelligenceStudio/ (one folder). On macOS also an .app bundle.
# Verify the build with:  dist/ResumeIntelligenceStudio/ResumeIntelligenceStudio --selftest
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - provided by PyInstaller
datas = [(str(ROOT / d), d) for d in ("templates", "migrations", "config", "assets", "sample_data")]
# python-docx needs its built-in part templates (default header/footer XML) at run time.
datas += collect_data_files("docx") + collect_data_files("reportlab")
# python-docx resolves templates as docx/parts/../templates, so the parts folder must exist on disk.
datas += [(str(ROOT / "packaging" / "docx_parts_placeholder.txt"), "docx/parts")]

a = Analysis(  # noqa: F821
    [str(ROOT / "run_application.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=["PySide6.QtPdf", "PySide6.QtPdfWidgets", "keyring.backends", "ris.ui.application"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtMultimedia", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtCharts",
              "PySide6.QtDataVisualization", "pytest", "tests", "google", "googleapiclient"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
icon = None
exe = EXE(  # noqa: F821
    pyz, a.scripts, [], exclude_binaries=True, name="ResumeIntelligenceStudio", console=False, icon=icon,
    debug=False, strip=False, upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ResumeIntelligenceStudio", strip=False, upx=False)  # noqa: F821
if sys.platform == "darwin":
    app = BUNDLE(coll, name="Resume Intelligence Studio.app", bundle_identifier="org.example.resumeintelligencestudio",  # noqa: F821
                 info_plist={"NSHighResolutionCapable": True, "CFBundleShortVersionString": "1.0.0"})
