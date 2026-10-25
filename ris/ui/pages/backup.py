"""Backup & Restore: local backups, verification, restore, integrity checks and recently deleted records."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ris.domain.enums import label
from ris.errors import RISError
from ris.strings import PAGE_SUBTITLES, STORAGE_NOTICE
from ris.ui.importing import export_profile_json, import_profile_file
from ris.ui.widgets.common import Card, Page, ask_passphrase, banner, button, confirm, error, info, muted, set_banner
from ris.ui.workers import run_task


class BackupPage(Page):
    key = "backup"

    def __init__(self, ctx) -> None:
        super().__init__(ctx, "Backup & Restore", PAGE_SUBTITLES["backup"])
        self.body.addWidget(banner(STORAGE_NOTICE, "info"))
        local = Card("Local backups")
        local.add(muted("A backup is a single file containing your whole workspace database, with a manifest and "
                        "checksum. Encrypted backups use AES-256-GCM with a key derived from your passphrase — "
                        "if you forget the passphrase, the backup cannot be opened."))
        row = QHBoxLayout()
        row.addWidget(button("Back up now", "primary", on_click=lambda: self.backup(False)))
        row.addWidget(button("Back up now (encrypted)…", on_click=lambda: self.backup(True)))
        row.addWidget(button("Save a copy elsewhere…", on_click=self.backup_elsewhere))
        row.addStretch(1)
        row.addWidget(button("Open backup folder", on_click=self.open_folder))
        local.body.addLayout(row)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Created (UTC)", "Reason", "Encrypted", "Records", "File"])
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(220)
        self.table.setAccessibleName("Backups")
        local.add(self.table)
        row2 = QHBoxLayout()
        row2.addWidget(button("Verify selected", on_click=self.verify))
        row2.addWidget(button("Restore selected…", on_click=self.restore))
        row2.addWidget(button("Restore from a file…", on_click=self.restore_file))
        row2.addStretch(1)
        local.body.addLayout(row2)
        self.result = banner("", "info")
        self.result.setVisible(False)
        local.add(self.result)
        self.body.addWidget(local)
        auto = Card("Automatic backups")
        f = QFormLayout()
        self.auto = QCheckBox("Back up automatically while the application is open")
        self.interval = QSpinBox()
        self.interval.setRange(1, 168)
        self.interval.setSuffix(" hours")
        self.keep = QSpinBox()
        self.keep.setRange(1, 200)
        self.on_exit = QCheckBox("Back up when the application closes")
        f.addRow(self.auto)
        f.addRow("Interval:", self.interval)
        f.addRow("Keep the latest:", self.keep)
        f.addRow(self.on_exit)
        auto.body.addLayout(f)
        auto.add(muted("Only automatic backups are pruned; backups you create yourself are kept until you delete "
                       "them."))
        self.auto.toggled.connect(lambda v: self._set("backup.auto_enabled", v))
        self.interval.valueChanged.connect(lambda v: self._set("backup.interval_hours", v))
        self.keep.valueChanged.connect(lambda v: self._set("backup.keep_last", v))
        self.on_exit.toggled.connect(lambda v: self._set("backup.on_exit", v))
        self.body.addWidget(auto)
        portable = Card("Portable profile (JSON)")
        portable.add(muted("Move your profile between installations or keep a human-readable copy. Imported records "
                           "always arrive unconfirmed and requiring review."))
        prow = QHBoxLayout()
        prow.addWidget(button("Export profile…", on_click=lambda: export_profile_json(self, self.ctx)))
        prow.addWidget(button("Import…", on_click=lambda: import_profile_file(self, self.ctx)))
        prow.addStretch(1)
        portable.body.addLayout(prow)
        self.body.addWidget(portable)
        integ = Card("Integrity")
        irow = QHBoxLayout()
        irow.addWidget(button("Check database integrity", on_click=self.integrity))
        irow.addWidget(button("Rebuild search index", on_click=self.rebuild))
        irow.addStretch(1)
        integ.body.addLayout(irow)
        self.integ_result = banner("", "info")
        self.integ_result.setVisible(False)
        integ.add(self.integ_result)
        self.body.addWidget(integ)
        deleted = Card("Recently deleted")
        deleted.add(muted("Deleted records stay here until you remove them permanently."))
        self.deleted = QTableWidget(0, 3)
        self.deleted.setHorizontalHeaderLabels(["Deleted (UTC)", "Type", "Record"])
        self.deleted.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.deleted.verticalHeader().setVisible(False)
        self.deleted.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.deleted.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.deleted.setMinimumHeight(160)
        self.deleted.setAccessibleName("Recently deleted records")
        deleted.add(self.deleted)
        drow = QHBoxLayout()
        drow.addWidget(button("Restore selected", on_click=self.undelete))
        drow.addWidget(button("Delete permanently…", "danger", on_click=self.purge))
        drow.addStretch(1)
        deleted.body.addLayout(drow)
        self.body.addWidget(deleted)
        self.body.addStretch(1)
        self._loading = False
        self.infos: list = []
        self.deleted_recs: list = []

    def kinds_of_interest(self) -> set[str] | None:
        return None

    def _set(self, key: str, value) -> None:
        if not self._loading:
            self.ctx.settings.set(key, value)

    def refresh(self) -> None:
        self._loading = True
        s = self.ctx.settings
        self.auto.setChecked(bool(s.get("backup.auto_enabled")))
        self.interval.setValue(int(s.get("backup.interval_hours") or 24))
        self.keep.setValue(int(s.get("backup.keep_last") or 10))
        self.on_exit.setChecked(bool(s.get("backup.on_exit")))
        self._loading = False
        self.infos = self.ctx.backups().list()
        self.table.setRowCount(len(self.infos))
        for i, b in enumerate(self.infos):
            vals = [b.created_at[:19].replace("T", " "), b.reason, "Yes" if b.encrypted else "No",
                    str(b.record_count) if b.manifest else ("—" if b.encrypted else "?"), b.path.name]
            for j, v in enumerate(vals):
                self.table.setItem(i, j, QTableWidgetItem(v))
        self.deleted_recs = self.ctx.repo.deleted_records()
        self.deleted.setRowCount(len(self.deleted_recs))
        for i, r in enumerate(self.deleted_recs):
            for j, v in enumerate([(r.deleted_at or "")[:16].replace("T", " "), label(r.kind), r.title or "(untitled)"]):
                self.deleted.setItem(i, j, QTableWidgetItem(v))

    def _selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return self.infos[rows[0]] if rows else None

    def backup(self, encrypted: bool, dest: Path | None = None) -> None:
        pw = None
        if encrypted:
            pw = ask_passphrase(self, "Encrypted backup", confirm_twice=True,
                                note="Choose a passphrase of at least 10 characters. It is not stored anywhere.")
            if not pw:
                return
        svc = self.ctx.backups()

        def done(b) -> None:
            set_banner(self.result, f"Backup created: {b.path.name} ({b.size:,} bytes).", "ok")
            self.refresh()

        run_task(lambda: svc.create(reason="manual", passphrase=pw, dest_dir=dest), done,
                 lambda m, d: error(self, "Backup", m, d))

    def backup_elsewhere(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Save a backup copy to")
        if d:
            enc = confirm(self, "Encrypt?", "Encrypt this copy with a passphrase?", ok="Encrypt",
                          detail="Recommended for USB drives and shared folders.")
            self.backup(enc, Path(d))

    def open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.backups().folder)))

    def _passphrase_for(self, path: Path) -> tuple[bool, str | None]:
        from ris.backup import crypto

        if crypto.is_encrypted(path.read_bytes()[:16]):
            pw = ask_passphrase(self, "Backup passphrase")
            return (pw is not None), pw
        return True, None

    def verify(self, path: Path | None = None) -> None:
        b = self._selected() if path is None else None
        p = path or (b.path if b else None)
        if p is None:
            return
        ok, pw = self._passphrase_for(p)
        if not ok:
            return
        try:
            v = self.ctx.backups().verify(p, pw)
        except RISError as exc:
            set_banner(self.result, exc.user_message, "bad")
            return
        if v.ok:
            recs = v.manifest.get("records", {}).get("total", "?")
            set_banner(self.result, f"Backup verified: checksum matches and the database is intact ({recs} records).",
                       "ok")
        else:
            set_banner(self.result, "Verification failed: " + "; ".join(v.problems[:3]), "bad")

    def restore(self) -> None:
        b = self._selected()
        if b is not None:
            self._restore(b.path)

    def restore_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Restore from backup", "", "Backups (*.risbackup *.enc)")
        if path:
            self._restore(Path(path))

    def _restore(self, path: Path) -> None:
        if not confirm(self, "Restore backup", "Replace the current workspace with this backup?", ok="Restore",
                       destructive=True, detail="Your current data is first saved as a 'pre-restore' backup, so you "
                                                "can return to it."):
            return
        ok, pw = self._passphrase_for(path)
        if not ok:
            return
        for page in (self.window().pages.values() if hasattr(self.window(), "pages") else []):
            if hasattr(page, "maybe_save") and not page.maybe_save():
                return
        try:
            res = self.ctx.backups().restore(path, pw)
        except RISError as exc:
            error(self, "Restore", exc.user_message, exc.detail)
            return
        self.ctx.after_restore()
        info(self, "Restore complete", "The workspace was restored. Your previous data was saved as "
                                       f"{Path(res['pre_restore_snapshot']).name}."
             + (" Confidential records kept on this computer were preserved." if res.get("kept_local_confidential")
                else ""))
        self.refresh()

    def integrity(self) -> None:
        from ris.backup.integrity import check_database

        rep = check_database(self.ctx.ws.db)
        text = rep.summary()
        if rep.problems:
            text += " " + "; ".join(rep.problems[:4]) + " Restore a recent backup if problems persist."
        elif rep.warnings:
            text += " " + "; ".join(rep.warnings[:3])
        set_banner(self.integ_result, text, "ok" if rep.ok else "bad")

    def rebuild(self) -> None:
        from ris.backup.integrity import rebuild_search_index

        n = rebuild_search_index(self.ctx.repo)
        set_banner(self.integ_result, f"Search index rebuilt for {n} record(s).", "ok")

    def _deleted_selected(self) -> list:
        rows = sorted({i.row() for i in self.deleted.selectedIndexes()})
        return [self.deleted_recs[r] for r in rows]

    def undelete(self) -> None:
        done = 0
        for r in self._deleted_selected():
            try:
                self.ctx.repo.undelete(r.id)
                done += 1
            except RISError as exc:
                error(self, "Restore record", exc.user_message)
        if done:
            self.ctx.invalidate()
            self.ctx.say(f"{done} record(s) restored.")
            self.refresh()

    def purge(self) -> None:
        sel = self._deleted_selected()
        if not sel:
            return
        if not confirm(self, "Delete permanently", f"Permanently delete {len(sel)} record(s)?", ok="Delete permanently",
                       destructive=True, detail="This cannot be undone except by restoring a backup."):
            return
        for r in sel:
            self.ctx.repo.purge(r.id)
        self.refresh()


_ = (Qt, QWidget)
