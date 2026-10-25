"""Synchronisation: optional encrypted cloud copies and record-level sync with conflict resolution."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ris.domain.enums import RecordKind, label
from ris.errors import RISError
from ris.strings import PAGE_SUBTITLES
from ris.ui.dialogs import ConflictDialog
from ris.ui.widgets.common import Card, Page, ask_passphrase, banner, button, confirm, error, info, muted, set_banner
from ris.ui.workers import run_task

PRIVACY = ("Synchronisation is off unless you turn it on. When on, records marked Confidential are replaced by a "
           "placeholder in the cloud copy (unless you explicitly include them), and with a passphrase everything is "
           "encrypted on this computer before upload. The cloud provider cannot read encrypted data.")


class SyncPage(Page):
    key = "sync"

    def __init__(self, ctx) -> None:
        super().__init__(ctx, "Synchronisation", PAGE_SUBTITLES["sync"])
        self.body.addWidget(banner(PRIVACY, "info"))
        self.status = banner("", "info")
        self.body.addWidget(self.status)
        prov = Card("Where to synchronise")
        self.group = QButtonGroup(self)
        self.r_off = QRadioButton("Off — keep everything on this computer")
        self.r_folder = QRadioButton("A folder (for example your Google Drive for desktop, OneDrive or a USB drive)")
        self.r_drive = QRadioButton("Google Drive directly (sign in with Google in your browser)")
        for i, r in enumerate((self.r_off, self.r_folder, self.r_drive)):
            self.group.addButton(r, i)
            prov.add(r)
        frow = QHBoxLayout()
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("Choose a folder…")
        self.folder.setReadOnly(True)
        self.folder.setAccessibleName("Sync folder")
        frow.addWidget(self.folder, 1)
        frow.addWidget(button("Choose folder…", on_click=self.choose_folder))
        prov.body.addLayout(frow)
        drow = QHBoxLayout()
        self.client = QLineEdit()
        self.client.setPlaceholderText("Your Google OAuth client file (Desktop app JSON)")
        self.client.setReadOnly(True)
        self.client.setAccessibleName("Google OAuth client file")
        drow.addWidget(self.client, 1)
        drow.addWidget(button("Choose client file…", on_click=self.choose_client))
        self.b_connect = button("Connect Google account…", on_click=self.connect_drive)
        self.b_disconnect = button("Disconnect", on_click=self.disconnect_drive)
        drow.addWidget(self.b_connect)
        drow.addWidget(self.b_disconnect)
        prov.body.addLayout(drow)
        prov.add(muted("Google Drive access uses the 'drive.file' permission: the application can only see files it "
                       "created. Your Google password is entered only on Google's own page, never here. See "
                       "docs/GOOGLE_DRIVE_SETUP.md."))
        self.group.idToggled.connect(self._provider_changed)
        self.body.addWidget(prov)
        sec = Card("Protection")
        prow = QHBoxLayout()
        self.pass_state = QLabel("")
        prow.addWidget(self.pass_state, 1)
        prow.addWidget(button("Set sync passphrase…", on_click=self.set_passphrase))
        prow.addWidget(button("Forget passphrase on this computer", on_click=self.forget_passphrase))
        sec.body.addLayout(prow)
        self.include_conf = QCheckBox("Include records marked Confidential in cloud copies (not recommended)")
        self.include_conf.toggled.connect(self._include_conf_changed)
        sec.add(self.include_conf)
        sec.add(muted("Use the same passphrase on every device. It is kept in this computer's credential store and "
                      "is never uploaded."))
        self.body.addWidget(sec)
        act = Card("Synchronise")
        arow = QHBoxLayout()
        self.b_sync = button("Sync now", "primary", on_click=self.sync_now)
        self.b_upload = button("Upload an encrypted backup", on_click=self.upload_backup)
        arow.addWidget(self.b_sync)
        arow.addWidget(self.b_upload)
        arow.addStretch(1)
        act.body.addLayout(arow)
        self.result = banner("", "info")
        self.result.setVisible(False)
        act.add(self.result)
        act.add(QLabel("Conflicts (changed on two devices):"))
        self.conflicts = QTableWidget(0, 3)
        self.conflicts.setHorizontalHeaderLabels(["Detected (UTC)", "Type", "Record"])
        self.conflicts.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.conflicts.verticalHeader().setVisible(False)
        self.conflicts.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.conflicts.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.conflicts.setMinimumHeight(120)
        self.conflicts.setAccessibleName("Conflicts")
        self.conflicts.cellDoubleClicked.connect(lambda _r, _c: self.resolve())
        act.add(self.conflicts)
        act.add(button("Resolve selected conflict…", on_click=self.resolve))
        self.body.addWidget(act)
        cloud = Card("Cloud backups")
        self.cloud = QTableWidget(0, 3)
        self.cloud.setHorizontalHeaderLabels(["File", "Size", "Modified"])
        self.cloud.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.cloud.verticalHeader().setVisible(False)
        self.cloud.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.cloud.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.cloud.setMinimumHeight(120)
        self.cloud.setAccessibleName("Cloud backups")
        cloud.add(self.cloud)
        crow = QHBoxLayout()
        crow.addWidget(button("Refresh list", on_click=self.list_cloud))
        crow.addWidget(button("Restore selected…", on_click=self.restore_cloud))
        crow.addWidget(button("Delete selected from cloud…", "danger", on_click=self.delete_cloud))
        crow.addStretch(1)
        cloud.body.addLayout(crow)
        self.body.addWidget(cloud)
        self.body.addStretch(1)
        self._loading = False
        self._conflicts: list = []
        self._cloud_files: list = []

    def kinds_of_interest(self) -> set[str] | None:
        return set()

    # ------------------------------------------------------------------ state
    def refresh(self) -> None:
        self._loading = True
        s = self.ctx.settings
        svc = self.ctx.sync()
        prov = s.get("sync.provider") or "off"
        {"off": self.r_off, "folder": self.r_folder, "gdrive": self.r_drive}.get(prov, self.r_off).setChecked(True)
        self.folder.setText(s.get("sync.folder_path") or "")
        self.client.setText(s.get("sync.drive_client_file") or "")
        self.include_conf.setChecked(bool(s.get("sync.include_confidential")))
        self._loading = False
        self._update_status(svc)
        self._load_conflicts()

    def _auth(self):
        from ris.sync.gdrive import TOKEN_SECRET, GoogleDriveAuth

        ws = self.ctx.ws
        return GoogleDriveAuth(self.ctx.secrets, self.ctx.settings.get("sync.drive_client_file") or None,
                               secret_name=f"{TOKEN_SECRET}:{ws.id or ws.name}")

    def _update_status(self, svc=None) -> None:
        svc = svc or self.ctx.sync()
        prov = self.ctx.settings.get("sync.provider") or "off"
        on = prov != "off"
        try:
            st = svc.status()
            desc = st.description
            last = st.last_success
            err = st.last_error
        except RISError as exc:
            desc, last, err = exc.user_message, "", ""
        has_pass = bool(svc.passphrase())
        self.pass_state.setText("Passphrase set — cloud copies are encrypted." if has_pass else
                                "No passphrase — cloud copies would not be encrypted.")
        if not on:
            set_banner(self.status, "Synchronisation is off. Nothing leaves this computer.", "info")
        elif err:
            set_banner(self.status, f"{desc} Last problem: {err}", "warn")
        else:
            set_banner(self.status, f"{desc} " + (f"Last synchronised {last[:16].replace('T', ' ')} UTC."
                                                  if last else "Not synchronised yet."), "ok")
        self.b_sync.setEnabled(on)
        self.b_upload.setEnabled(on)
        drive = prov == "gdrive"
        connected = self._auth().connected() if drive or self.client.text() else False
        self.b_connect.setEnabled(not connected)
        self.b_disconnect.setEnabled(connected)

    def _provider_changed(self, bid: int, checked: bool) -> None:
        if self._loading or not checked:
            return
        svc = self.ctx.sync()
        if bid == 0:
            svc.disable()
        elif bid == 1:
            if not self.folder.text():
                self.choose_folder()
                if not self.folder.text():
                    self._loading = True
                    self.r_off.setChecked(True)
                    self._loading = False
                    return
            else:
                svc.settings.set("sync.provider", "folder")
        elif bid == 2:
            from ris.sync.gdrive import google_libraries_available

            if not google_libraries_available():
                info(self, "Google Drive", "Google Drive support needs optional packages. Install them with:\n\n"
                                           "pip install -r requirements-optional.txt\n\nThen restart the application. "
                                           "Alternatively, use the folder option with Google Drive for desktop.")
                self._loading = True
                (self.r_folder if self.folder.text() else self.r_off).setChecked(True)
                self._loading = False
                return
            svc.settings.set("sync.provider", "gdrive")
        self.ctx._sync = None
        self._update_status()

    def choose_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose a sync folder")
        if not d:
            return
        try:
            self.ctx.sync().configure_folder(d)
        except RISError as exc:
            error(self, "Sync folder", exc.user_message)
            return
        self.folder.setText(d)
        self._loading = True
        self.r_folder.setChecked(True)
        self._loading = False
        self.ctx._sync = None
        self._update_status()

    def choose_client(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Google OAuth client (Desktop app)", "", "JSON (*.json)")
        if path:
            self.ctx.settings.set("sync.drive_client_file", path)
            self.client.setText(path)
            self._update_status()

    def connect_drive(self) -> None:
        auth = self._auth()
        self.ctx.say("Complete the Google sign-in in your browser…", 0)
        run_task(auth.connect_interactive, lambda _r: (self.ctx.say("Google Drive connected."), self._update_status()),
                 lambda m, d: (self.ctx.say(""), error(self, "Google Drive", m, d)))

    def disconnect_drive(self) -> None:
        if confirm(self, "Disconnect Google Drive", "Remove this computer's access to your Google Drive?",
                   detail="Files already in Drive are not deleted."):
            self._auth().disconnect()
            if self.ctx.settings.get("sync.provider") == "gdrive":
                self.ctx.sync().disable()
            self.refresh()

    def set_passphrase(self) -> None:
        pw = ask_passphrase(self, "Sync passphrase", confirm_twice=True,
                            note="Cloud copies are encrypted with this passphrase. Use the same one on each device. "
                                 "If it is lost, encrypted cloud copies cannot be opened.")
        if not pw:
            return
        try:
            persistent = self.ctx.sync().set_passphrase(pw)
        except RISError as exc:
            error(self, "Sync passphrase", exc.user_message)
            return
        if not persistent:
            info(self, "Sync passphrase", "No secure credential store is available, so the passphrase is remembered "
                                          "only until you quit.")
        self._update_status()

    def forget_passphrase(self) -> None:
        svc = self.ctx.sync()
        self.ctx.secrets.delete(f"cloud_passphrase:{self.ctx.ws.id or self.ctx.ws.name}")
        del svc
        self._update_status()

    def _include_conf_changed(self, v: bool) -> None:
        if self._loading:
            return
        if v and not confirm(self, "Include confidential records?",
                             "Confidential records would be copied to the cloud provider.",
                             ok="Include them", destructive=True,
                             detail="Only do this if your employer's rules allow it and a passphrase is set."):
            self._loading = True
            self.include_conf.setChecked(False)
            self._loading = False
            return
        self.ctx.settings.set("sync.include_confidential", v)

    # ------------------------------------------------------------------ actions
    def sync_now(self) -> None:
        svc = self.ctx.sync()
        if not svc.passphrase() and not confirm(self, "No passphrase", "Synchronise without encryption?",
                                                ok="Synchronise unencrypted",
                                                detail="Set a passphrase first to encrypt the cloud copy."):
            return
        for page in (self.window().pages.values() if hasattr(self.window(), "pages") else []):
            if hasattr(page, "maybe_save") and not page.maybe_save():
                return
        self.b_sync.setEnabled(False)
        self.ctx.say("Synchronising…", 0)

        def done(rep) -> None:
            self.b_sync.setEnabled(True)
            self.ctx.say(rep.summary())
            set_banner(self.result, rep.summary() + (" " + " ".join(rep.notes[:3]) if rep.notes else ""),
                       "warn" if rep.conflicts else "ok")
            self.ctx.invalidate()
            self.ctx.data_changed.emit({"synced"})
            self._update_status()
            self._load_conflicts()

        def failed(m: str, d: str) -> None:
            self.b_sync.setEnabled(True)
            self.ctx.say("")
            set_banner(self.result, m + " Your local data is unchanged.", "bad")
            self._update_status()

        run_task(svc.sync_now, done, failed)

    def upload_backup(self) -> None:
        svc = self.ctx.sync()
        allow = False
        if not svc.passphrase():
            if not confirm(self, "Unencrypted upload", "Upload a backup without encryption?", ok="Upload unencrypted",
                           destructive=True, detail="Set a sync passphrase to encrypt cloud backups."):
                return
            allow = True
        run_task(lambda: svc.upload_backup(allow_unencrypted=allow),
                 lambda f: (set_banner(self.result, f"Backup uploaded: {f.name.split('/')[-1]}.", "ok"),
                            self._update_status(), self.list_cloud()),
                 lambda m, d: set_banner(self.result, m, "bad"))

    def _load_conflicts(self) -> None:
        try:
            self._conflicts = self.ctx.sync().engine().open_conflicts() \
                if self.ctx.settings.get("sync.provider") != "off" else []
        except RISError:
            self._conflicts = []
        self.conflicts.setRowCount(len(self._conflicts))
        for i, c in enumerate(self._conflicts):
            env = c.local or c.remote or {}
            title = ""
            try:
                from ris.domain.registry import model_for

                title = model_for(RecordKind(c.kind)).model_validate(env.get("data") or {}).display_title()
            except Exception:  # noqa: BLE001 - title is only a hint
                title = c.object_id
            kind = label(RecordKind(c.kind)) if c.kind in RecordKind._value2member_map_ else c.kind
            for j, v in enumerate([c.detected_at[:16].replace("T", " "), kind, title]):
                self.conflicts.setItem(i, j, QTableWidgetItem(v))

    def resolve(self) -> None:
        rows = sorted({i.row() for i in self.conflicts.selectedIndexes()})
        if not rows:
            return
        c = self._conflicts[rows[0]]
        dlg = ConflictDialog(self, c)
        if dlg.exec() and dlg.choice:
            try:
                self.ctx.sync().engine().resolve(c.id, dlg.choice)
            except RISError as exc:
                error(self, "Resolve conflict", exc.user_message)
                return
            self.ctx.invalidate()
            self.ctx.data_changed.emit({"synced"})
            self._load_conflicts()
            self.ctx.say("Conflict resolved. Sync again to send your decision to the cloud copy.")

    def list_cloud(self) -> None:
        svc = self.ctx.sync()

        def done(files) -> None:
            self._cloud_files = files
            self.cloud.setRowCount(len(files))
            for i, f in enumerate(files):
                for j, v in enumerate([f.name.split("/")[-1], f"{f.size:,} bytes", f.modified[:16].replace("T", " ")]):
                    self.cloud.setItem(i, j, QTableWidgetItem(v))

        run_task(svc.list_cloud_backups, done, lambda m, d: set_banner(self.result, m, "bad"))

    def _cloud_selected(self):
        rows = sorted({i.row() for i in self.cloud.selectedIndexes()})
        return self._cloud_files[rows[0]] if rows else None

    def restore_cloud(self) -> None:
        f = self._cloud_selected()
        if f is None:
            return
        if not confirm(self, "Restore cloud backup", "Replace the current workspace with this cloud backup?",
                       ok="Restore", destructive=True,
                       detail="Your current data is saved first as a 'pre-restore' backup on this computer. "
                              "Confidential records kept only on this computer are preserved."):
            return
        try:
            res = self.ctx.sync().restore_cloud_backup(f.name)
        except RISError as exc:
            error(self, "Restore", exc.user_message, exc.detail)
            return
        self.ctx.after_restore()
        info(self, "Restore complete", "Restored from the cloud backup. Previous data saved as "
                                       f"{res['pre_restore_snapshot'].split('/')[-1]}.")

    def delete_cloud(self) -> None:
        f = self._cloud_selected()
        if f is None:
            return
        if not confirm(self, "Delete cloud backup", f"Delete {f.name.split('/')[-1]} from the cloud?", ok="Delete",
                       destructive=True, detail="Local data and local backups are not affected."):
            return
        run_task(lambda: self.ctx.sync().delete_cloud_backup(f.name), lambda _r: self.list_cloud(),
                 lambda m, d: set_banner(self.result, m, "bad"))


_ = QVBoxLayout
