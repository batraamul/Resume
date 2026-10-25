"""Desktop application bootstrap."""

from __future__ import annotations

import logging
import os
import sys
import time
import traceback
from pathlib import Path

from ris import APP_ID, APP_NAME, __version__

log = logging.getLogger(__name__)


def _icon():
    from PySide6.QtGui import QIcon

    from ris.resources import resource_path

    p = resource_path("assets", "icons", "app.svg")
    return QIcon(str(p)) if p.exists() else QIcon()


def create_app(argv: list[str] | None = None):
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(argv or sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ID)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(_icon())
    return app


def apply_theme(app, config) -> None:
    from PySide6.QtGui import QFont

    from ris.ui import theme

    theme.load_fonts()
    app.setFont(QFont(theme.UI_FONT, 10))
    app.setStyleSheet(theme.stylesheet(theme.resolve(config.theme), config.ui_font_scale or 1.0))


def _install_excepthook() -> None:
    from PySide6.QtWidgets import QMessageBox

    def hook(etype, value, tb) -> None:
        log.error("Unhandled error: %s", etype.__name__)
        detail = "".join(traceback.format_exception_only(etype, value)).strip()
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen" or os.environ.get("RIS_DEBUG"):
            # Headless runs (tests, screenshots): print instead of blocking on a dialog.
            traceback.print_exception(etype, value, tb)
            return
        try:
            box = QMessageBox()
            box.setIcon(QMessageBox.Icon.Critical)
            box.setWindowTitle("Unexpected problem")
            box.setText("Something went wrong. Your saved data is safe; unsaved edits in the open form may need to "
                        "be re-entered.")
            box.setDetailedText(detail)
            box.exec()
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = hook


class WelcomeDialog:
    """First-run choices; shown once per installation."""

    @staticmethod
    def run(parent, ctx) -> str:
        from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

        from ris.strings import RESPONSIBILITY_NOTICE, STORAGE_NOTICE
        from ris.ui.widgets.common import banner

        d = QDialog(parent)
        d.setWindowTitle(f"Welcome to {APP_NAME}")
        d.setMinimumWidth(620)
        lay = QVBoxLayout(d)
        title = QLabel(f"Welcome to {APP_NAME}")
        title.setObjectName("PageTitle")
        lay.addWidget(title)
        intro = QLabel("Keep one verified master profile and produce tailored, accurate resumes for Defence, "
                       "Intelligence and technical posts. Your data stays on this computer.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        lay.addWidget(banner(RESPONSIBILITY_NOTICE, "info"))
        lay.addWidget(banner(STORAGE_NOTICE, "info"))
        choice = {"value": "empty"}
        for text, val, primary in (("Start my profile", "empty", True),
                                   ("Import an existing CV or profile file…", "import", False),
                                   ("Explore the fictional sample first", "sample", False)):
            b = QPushButton(text)
            if primary:
                b.setProperty("kind", "primary")
            b.clicked.connect(lambda _=False, v=val: (choice.__setitem__("value", v), d.accept()))
            lay.addWidget(b)
        d.exec()
        return choice["value"]


def run_gui(config, *, open_sample: bool = False, screenshot: str | None = None) -> int:
    if screenshot and not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = create_app()
    apply_theme(app, config)
    _install_excepthook()
    from ris.ui.context import AppContext
    from ris.ui.main_window import MainWindow
    from ris.ui.widgets.common import error

    ctx = AppContext(config)
    try:
        ctx.open_active(prefer_sample=open_sample or bool(screenshot))
    except Exception as exc:  # noqa: BLE001 - shown to the user with recovery advice
        log.exception("Workspace could not be opened")
        error(None, "Workspace could not be opened",
              getattr(exc, "user_message", "The profile database could not be opened.") +
              " The fictional sample workspace will be opened instead. Use Backup & Restore to recover your data.",
              getattr(exc, "detail", ""))
        ctx.open_active(prefer_sample=True)
    win = MainWindow(ctx)
    win.setWindowIcon(_icon())
    win.restore_geometry()
    if screenshot:
        return _screenshots(app, win, Path(screenshot))
    win.show()
    if not config.first_run_completed and not open_sample:
        choice = WelcomeDialog.run(win, ctx)
        config.first_run_completed = True
        try:
            config.save()
        except OSError:
            pass
        if choice == "sample":
            win.switch_workspace(ctx.manager.ensure_sample())
        elif choice == "import":
            from ris.ui.importing import import_profile_file

            win.navigate("profile", "")
            import_profile_file(win, ctx)
        else:
            win.navigate("profile", "")
    return app.exec()


def _screenshots(app, win, folder: Path) -> int:
    """Developer aid: render every page of the sample workspace to PNG (used for visual review)."""
    from ris.ui.workers import wait_idle

    folder.mkdir(parents=True, exist_ok=True)
    win.resize(1440, 900)
    win.show()
    for key in win.pages:
        win.navigate(key, "")
        for _ in range(30):
            app.processEvents()
        if key == "studio":
            page = win.pages[key]
            page._preview_timer.stop()
            page.update_preview(synchronous=True)
        wait_idle(30000)
        # The PDF viewer renders pages on its own thread; give it a moment before capturing.
        for _ in range(80 if key == "studio" else 30):
            app.processEvents()
            if key == "studio":
                time.sleep(0.025)
        win.grab().save(str(folder / f"{list(win.pages).index(key) + 1:02d}_{key}.png"))
    wait_idle(30000)
    app.processEvents()
    win.ctx.close_workspace(backup=False)
    return 0
