"""Main window: diary-index navigation, top bar, page stack and lifecycle."""

from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QCompleter,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ris import APP_NAME, TAGLINE
from ris.domain.enums import RecordKind, label
from ris.strings import NAV_SECTIONS, SAMPLE_BANNER, WINDOW_TITLE
from ris.ui import theme
from ris.ui.pages.backup import BackupPage
from ris.ui.pages.diary import DiaryPage
from ris.ui.pages.exports import ExportsPage
from ris.ui.pages.interview import InterviewPage
from ris.ui.pages.letters import LettersPage
from ris.ui.pages.library import LibraryPage
from ris.ui.pages.opportunities import OpportunitiesPage
from ris.ui.pages.portals import PortalsPage
from ris.ui.pages.profile import SECTION_PAGES, CollectionPage, ProfilePage
from ris.ui.pages.settings import SettingsPage
from ris.ui.pages.studio import StudioPage
from ris.ui.pages.sync import SyncPage
from ris.ui.pages.targets import TargetsPage
from ris.ui.pages.tracker import TrackerPage
from ris.ui.widgets.common import error
from ris.ui.widgets.records import CollectionWidget
from ris.ui.workers import run_task

log = logging.getLogger(__name__)

PAGE_FOR_KIND = {
    RecordKind.PERSONAL: "profile", RecordKind.SUMMARY: "profile", RecordKind.CUSTOM_SECTION: "profile",
    RecordKind.CUSTOM_ENTRY: "profile", RecordKind.POSITION: "experience", RecordKind.ASSIGNMENT: "experience",
    RecordKind.EDUCATION: "education", RecordKind.PUBLICATION: "research", RecordKind.SKILL: "skills",
    RecordKind.PROJECT: "projects", RecordKind.ACTIVITY: "leadership", RecordKind.CAREER_TARGET: "targets",
    RecordKind.VACANCY: "opportunities", RecordKind.VARIANT: "studio", RecordKind.APPLICATION: "tracker",
    RecordKind.COVER_LETTER: "letters", RecordKind.EXPERTISE: "profile", RecordKind.REFERENCE: "profile",
    RecordKind.TRAINING: "training", RecordKind.INTERVIEW_STORY: "interview", RecordKind.INTERVIEW_ANSWER: "interview",
    RecordKind.QUESTIONNAIRE: "interview",
}


class MainWindow(QMainWindow):
    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(1080, 700)
        self.resize(1360, 860)
        root = QWidget()
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_nav())
        right = QWidget()
        right.setObjectName("PageArea")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self._build_topbar())
        self.sample_banner = QLabel(SAMPLE_BANNER)
        self.sample_banner.setObjectName("SampleBanner")
        self.sample_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rl.addWidget(self.sample_banner)
        self.stack = QStackedWidget()
        self.stack.setObjectName("Pages")
        rl.addWidget(self.stack, 1)
        lay.addWidget(right, 1)
        self.setCentralWidget(root)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.pages: dict[str, QWidget] = {}
        self._build_pages()
        ctx.status.connect(self._status)
        ctx.data_changed.connect(self._data_changed)
        ctx.workspace_opened.connect(self._workspace_opened)
        ctx.navigate.connect(self.navigate)
        ctx.workspace_closing.connect(self._workspace_closing)
        self.current_key = ""
        self.auto_timer = QTimer(self)
        self.auto_timer.setInterval(30 * 60 * 1000)
        self.auto_timer.timeout.connect(self._auto_backup)
        self.auto_timer.start()
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: (self.search.setFocus(), self.search.selectAll()))
        for i, key in enumerate(["diary", "profile", "experience", "studio", "opportunities", "library", "tracker",
                                 "backup", "settings"], start=1):
            QShortcut(QKeySequence(f"Ctrl+{i}"), self, activated=lambda k=key: self.navigate(k, ""))
        if ctx.has_workspace:
            self._workspace_opened()
        self.apply_layout()
        start = theme.appearance_of(ctx.config).start_page
        self.navigate(start if start in self.pages else "diary", "")

    # ------------------------------------------------------------------ construction
    def _build_nav(self) -> QWidget:
        nav = QFrame()
        nav.setObjectName("NavPanel")
        nav.setFixedWidth(250)
        outer = QVBoxLayout(nav)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.nav = nav
        brand = self.nav_brand = QLabel("Resume Intelligence\nStudio")
        brand.setObjectName("NavBrand")
        brand.setAccessibleName(APP_NAME)
        outer.addWidget(brand)
        tag = self.nav_tagline = QLabel(TAGLINE)
        tag.setObjectName("NavTagline")
        tag.setWordWrap(True)
        outer.addWidget(tag)
        holder = QWidget()
        holder.setObjectName("NavPanel")
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 12)
        hl.setSpacing(0)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        self.nav_groups: list[QLabel] = []
        for group, items in NAV_SECTIONS:
            g = QLabel(group.upper())
            g.setObjectName("NavGroup")
            self.nav_groups.append(g)
            hl.addWidget(g)
            for key, title in items:
                b = QPushButton(title.replace("&", "&&"))
                b.setObjectName("NavItem")
                b.setCheckable(True)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setAccessibleName(f"{title} page")
                b.clicked.connect(lambda _=False, k=key: self.navigate(k, ""))
                self.nav_group.addButton(b)
                self.nav_buttons[key] = b
                hl.addWidget(b)
        hl.addStretch(1)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setWidget(holder)
        sa.setObjectName("NavPanel")
        outer.addWidget(sa, 1)
        return nav

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 8, 18, 8)
        self.ws_label = QLabel("")
        self.ws_label.setAccessibleName("Current workspace")
        lay.addWidget(self.ws_label)
        lay.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search your profile…  (Ctrl+F)")
        self.search.setAccessibleName("Search your profile")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(320)
        self.search.returnPressed.connect(self._search)
        lay.addWidget(self.search)
        lay.addStretch(1)
        self.sync_label = QLabel("")
        self.sync_label.setAccessibleName("Synchronisation status")
        lay.addWidget(self.sync_label)
        return bar

    def _build_pages(self) -> None:
        ctx = self.ctx
        pages: list[tuple[str, QWidget]] = [("diary", DiaryPage(ctx)), ("profile", ProfilePage(ctx))]
        for key, title, kinds, hint, add_labels in SECTION_PAGES:
            pages.append((key, CollectionPage(ctx, key, title, kinds, empty_hint=hint, add_labels=add_labels)))
        pages += [("targets", TargetsPage(ctx)), ("opportunities", OpportunitiesPage(ctx)),
                  ("interview", InterviewPage(ctx)), ("portals", PortalsPage(ctx)), ("studio", StudioPage(ctx)),
                  ("library", LibraryPage(ctx)), ("letters", LettersPage(ctx)), ("tracker", TrackerPage(ctx)),
                  ("exports", ExportsPage(ctx)), ("sync", SyncPage(ctx)), ("backup", BackupPage(ctx)),
                  ("settings", SettingsPage(ctx, on_theme=self.apply_theme, on_workspace=self.switch_workspace))]
        for key, page in pages:
            page.key = key
            self.pages[key] = page
            self.stack.addWidget(page)

    # ------------------------------------------------------------------ navigation
    def navigate(self, key: str, record_id: str = "") -> None:
        if key == "record":
            key, record_id = self._page_for_record(record_id)
            if not key:
                self._status("That record is no longer available.", 5000)
                return
        page = self.pages.get(key)
        if page is None:
            return
        current = self.pages.get(self.current_key)
        if current is not None and current is not page and hasattr(current, "maybe_save") \
                and current.has_unsaved_changes() and not current.maybe_save():
            self.nav_buttons[self.current_key].setChecked(True)
            return
        self.current_key = key
        self.nav_buttons[key].setChecked(True)
        self.stack.setCurrentWidget(page)
        page.refresh_if_needed()
        if record_id:
            if page._dirty:
                page.refresh_if_needed()
            page.focus_record(record_id)

    def _page_for_record(self, record_id: str) -> tuple[str, str]:
        if not self.ctx.has_workspace or not record_id:
            return "", ""
        rec = self.ctx.repo.find(record_id)
        if rec is None:
            return "", ""
        if rec.kind == RecordKind.CLAIM and rec.parent_id:
            return "studio", rec.parent_id
        top = rec
        while top.kind in (RecordKind.BULLET, RecordKind.ASSIGNMENT, RecordKind.CUSTOM_ENTRY) and top.parent_id:
            parent = self.ctx.repo.find(top.parent_id)
            if parent is None:
                break
            top = parent
        return PAGE_FOR_KIND.get(top.kind, ""), record_id

    # ------------------------------------------------------------------ events
    def _status(self, message: str, timeout: int) -> None:
        if message:
            self.status_bar.showMessage(message, timeout)
        else:
            self.status_bar.clearMessage()

    def _data_changed(self, kinds: set) -> None:
        for _key, page in self.pages.items():
            interest = page.kinds_of_interest()
            if interest is None or (interest & set(kinds)) or "synced" in kinds:
                if page is self.stack.currentWidget():
                    page.mark_dirty()
                else:
                    page._dirty = True
        self._update_topbar()

    def _workspace_opened(self) -> None:
        if not self.auto_timer.isActive():
            self.auto_timer.start()
        for page in self.pages.values():
            page._dirty = True
            if hasattr(page, "collection"):
                page.collection.editor.set_record(None)
        self._update_topbar()
        cur = self.stack.currentWidget()
        if cur is not None:
            cur.refresh_if_needed()

    def _update_topbar(self) -> None:
        if not self.ctx.has_workspace:
            self.ws_label.setText("No workspace open")
            self.sample_banner.setVisible(False)
            return
        ws = self.ctx.ws
        self.ws_label.setText(f"Workspace: {ws.name}  ·  saved on this computer")
        self.sample_banner.setVisible(ws.is_sample)
        prov = ws.settings.get("sync.provider") or "off"
        if prov == "off":
            self.sync_label.setText("Sync off")
        else:
            last = ws.settings.get("sync.last_success_at") or ""
            err = ws.settings.get("sync.last_error") or ""
            self.sync_label.setText("Sync problem — see Synchronisation" if err else
                                    (f"Synced {last[:16].replace('T', ' ')} UTC" if last else "Sync not run yet"))

    def _search(self) -> None:
        text = self.search.text().strip()
        if not text or not self.ctx.has_workspace:
            return
        results = self.ctx.repo.search(text, limit=30)
        if not results:
            self._status(f"No records match '{text}'.", 5000)
            return
        if len(results) == 1:
            self.navigate("record", results[0][0].id)
            return
        from PySide6.QtWidgets import QInputDialog

        labels = [f"{label(r.kind)}: {r.title or '(untitled)'}" for r, _snip in results]
        choice, ok = QInputDialog.getItem(self, "Search results", f"{len(results)} records match '{text}':", labels, 0,
                                          False)
        if ok:
            self.navigate("record", results[labels.index(choice)][0].id)

    def _workspace_closing(self) -> None:
        self.auto_timer.stop()

    def _auto_backup(self) -> None:
        if not self.ctx.has_workspace or self.ctx.is_sample:
            return
        svc = self.ctx.backups()
        run_task(svc.auto_backup_if_due, lambda b: self._status("Automatic backup created.", 4000) if b else None,
                 lambda m, _d: self._status("Automatic backup failed: " + m, 8000))

    # ------------------------------------------------------------------ theme & workspace
    def apply_theme(self) -> None:
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(_Qt.CursorShape.WaitCursor)
        try:
            from PySide6.QtGui import QFont

            a = theme.appearance_of(self.ctx.config)
            QApplication.instance().setFont(QFont(a.ui_font or theme.UI_FONT, 10))
            QApplication.instance().setStyleSheet(theme.stylesheet_for(self.ctx.config))
            self.apply_layout()
        finally:
            QApplication.restoreOverrideCursor()
        self.ctx.theme_changed.emit()

    def apply_layout(self) -> None:
        """Navigation style and side, tagline and editor layout from the appearance settings."""
        a = theme.appearance_of(self.ctx.config)
        icons = a.nav_style in ("icons", "icons_text")
        for _group, items in NAV_SECTIONS:
            for key, title in items:
                b = self.nav_buttons[key]
                glyph = theme.NAV_ICONS.get(key, "•")
                if a.nav_style == "icons":
                    b.setText(glyph)
                elif icons:
                    b.setText(f"{glyph}   {title.replace('&', '&&')}")
                else:
                    b.setText(title.replace("&", "&&"))
                b.setToolTip(title)
        narrow = a.nav_style == "icons"
        self.nav.setFixedWidth(64 if narrow else 250)
        self.nav_brand.setVisible(not narrow)
        self.nav_tagline.setVisible(a.show_tagline and not narrow)
        for g in self.nav_groups:
            g.setVisible(not narrow)
        root_layout = self.centralWidget().layout()
        want = 0 if a.nav_side == "left" else 1
        if root_layout.indexOf(self.nav) != want:
            root_layout.removeWidget(self.nav)
            root_layout.insertWidget(want, self.nav)
        stacked = a.editor_layout == "stacked"
        for page in self.pages.values():
            for col in page.findChildren(CollectionWidget):
                col.set_stacked(stacked)

    def switch_workspace(self, entry) -> None:
        for page in self.pages.values():
            if page.has_unsaved_changes() and hasattr(page, "maybe_save") and not page.maybe_save():
                return
        try:
            self.ctx.open_entry(entry)
        except Exception as exc:  # noqa: BLE001 - shown to the user
            error(self, "Open workspace", getattr(exc, "user_message", "The workspace could not be opened."),
                  getattr(exc, "detail", ""))
            return
        self.navigate("diary", "")

    # ------------------------------------------------------------------ lifecycle
    def restore_geometry(self) -> None:
        g = self.ctx.config.window_geometry
        if g:
            try:
                self.restoreGeometry(QByteArray.fromBase64(g.encode("ascii")))
            except Exception:  # noqa: BLE001
                pass

    def closeEvent(self, event) -> None:  # noqa: N802
        for page in self.pages.values():
            if page.has_unsaved_changes() and hasattr(page, "maybe_save") and not page.maybe_save():
                event.ignore()
                return
        try:
            self.ctx.config.window_geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self.ctx.config.save()
        except Exception:  # noqa: BLE001
            log.warning("Could not save window geometry")
        self.status_bar.showMessage("Saving a backup and closing…")
        self.ctx.close_workspace(backup=True)
        event.accept()


_ = QCompleter
