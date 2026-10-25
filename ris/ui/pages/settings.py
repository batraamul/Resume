"""Settings & Security."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
)

from ris import APP_NAME, __version__
from ris.errors import RISError
from ris.strings import AI_DISCLOSURE, PAGE_SUBTITLES, RESPONSIBILITY_NOTICE, STORAGE_NOTICE
from ris.ui.widgets.common import Card, Page, ask_text, banner, button, confirm, error, info, muted, set_banner

WEIGHT_KEYS = [("essential", "Essential qualifications"), ("technical", "Technical competencies"),
               ("evidence", "Strength of evidence"), ("experience", "Relevant experience"),
               ("research", "Research & publications"), ("quality", "Document quality")]
DEFAULT_WEIGHTS = {"essential": 35, "technical": 25, "evidence": 15, "experience": 10, "research": 10, "quality": 5}


class SettingsPage(Page):
    key = "settings"

    def __init__(self, ctx, on_theme=None, on_workspace=None, on_check_updates=None) -> None:
        super().__init__(ctx, "Settings & Security", PAGE_SUBTITLES["settings"])
        self.on_theme = on_theme
        self.on_workspace = on_workspace
        self.on_check_updates = on_check_updates
        self._loading = False
        # appearance
        app = Card("Appearance")
        f = QFormLayout()
        self.theme = QComboBox()
        for v, t in (("light", "Light"), ("dark", "Dark"), ("system", "Follow the system")):
            self.theme.addItem(t, v)
        self.ui_scale = QDoubleSpinBox()
        self.ui_scale.setRange(0.85, 1.5)
        self.ui_scale.setSingleStep(0.05)
        self.ui_scale.setDecimals(2)
        f.addRow("Theme:", self.theme)
        f.addRow("Text size:", self.ui_scale)
        app.body.addLayout(f)
        arow = QHBoxLayout()
        arow.addWidget(button("Customise appearance…", "primary", on_click=self.customise_appearance,
                              tooltip="Colour presets, your own colours, fonts, density, navigation and layout"))
        arow.addWidget(muted("Colours, fonts, text size, density, icons, navigation and layout."))
        arow.addStretch(1)
        app.body.addLayout(arow)
        self.theme.currentIndexChanged.connect(self._appearance_changed)
        self.ui_scale.valueChanged.connect(self._appearance_changed)
        self.body.addWidget(app)
        # updates
        from ris.ui.updates import PRIVACY_NOTE

        upd = Card("Updates")
        uf = QFormLayout()
        uf.addRow("Installed version:", QLabel(__version__))
        self.update_auto = QCheckBox("Check for updates automatically (once a day)")
        self.update_auto.setAccessibleName("Check for updates automatically")
        self.update_channel = QComboBox()
        self.update_channel.setAccessibleName("Update channel")
        self.update_channel.addItem("Stable releases", "stable")
        self.update_channel.addItem("Stable and test (beta) releases", "beta")
        uf.addRow("", self.update_auto)
        uf.addRow("Channel:", self.update_channel)
        upd.body.addLayout(uf)
        urow = QHBoxLayout()
        urow.addWidget(button("Check for updates now", on_click=self._check_updates))
        self.update_status = muted("")
        urow.addWidget(self.update_status, 1)
        upd.body.addLayout(urow)
        upd.add(muted(PRIVACY_NOTE))
        self.update_auto.toggled.connect(self._updates_changed)
        self.update_channel.currentIndexChanged.connect(self._updates_changed)
        self.body.addWidget(upd)
        # documents
        docs = Card("Documents")
        df = QFormLayout()
        self.engine = QComboBox()
        for v, t in (("auto", "Automatic (LibreOffice if installed, otherwise built-in)"),
                     ("libreoffice", "LibreOffice"), ("builtin", "Built-in PDF engine")):
            self.engine.addItem(t, v)
        df.addRow("PDF engine:", self.engine)
        lo_row = QHBoxLayout()
        self.lo_path = QLineEdit()
        self.lo_path.setPlaceholderText("Detected automatically")
        lo_row.addWidget(self.lo_path, 1)
        lo_row.addWidget(button("Browse…", on_click=self._browse_lo))
        lo_row.addWidget(button("Detect", on_click=self._detect_lo))
        df.addRow("LibreOffice:", lo_row)
        self.lo_status = muted("")
        df.addRow("", self.lo_status)
        ex_row = QHBoxLayout()
        self.export_folder = QLineEdit()
        self.export_folder.setPlaceholderText("The workspace's exports folder")
        ex_row.addWidget(self.export_folder, 1)
        ex_row.addWidget(button("Browse…", on_click=self._browse_export))
        df.addRow("Default export folder:", ex_row)
        self.pattern = QLineEdit()
        self.pattern.setToolTip("Placeholders: {name} {variant} {date} {template}")
        df.addRow("File name pattern:", self.pattern)
        docs.body.addLayout(df)
        self.engine.currentIndexChanged.connect(self._docs_changed)
        self.lo_path.editingFinished.connect(self._docs_changed)
        self.export_folder.editingFinished.connect(self._docs_changed)
        self.pattern.editingFinished.connect(self._docs_changed)
        self.body.addWidget(docs)
        # scoring
        sc = Card("Vacancy alignment weights")
        sc.add(muted("Weights for the transparent alignment score (they are normalised to 100). The score reflects "
                     "your recorded evidence only — it is never a prediction of selection."))
        sf = QFormLayout()
        self.weights: dict[str, QSpinBox] = {}
        for k, t in WEIGHT_KEYS:
            sp = QSpinBox()
            sp.setRange(0, 100)
            sp.setSuffix(" %")
            sp.valueChanged.connect(self._weights_changed)
            sp.setAccessibleName(t)
            self.weights[k] = sp
            sf.addRow(t + ":", sp)
        sc.body.addLayout(sf)
        wrow = QHBoxLayout()
        self.weight_total = muted("")
        wrow.addWidget(self.weight_total, 1)
        wrow.addWidget(button("Reset to 35/25/15/10/10/5", on_click=self._reset_weights))
        sc.body.addLayout(wrow)
        self.body.addWidget(sc)
        # privacy
        pr = Card("Privacy & security")
        pr.add(banner(RESPONSIBILITY_NOTICE, "info"))
        pr.add(muted(STORAGE_NOTICE))
        self.keyring = muted("")
        pr.add(self.keyring)
        self.data_dir = muted("")
        pr.add(self.data_dir)
        prow = QHBoxLayout()
        prow.addWidget(button("Move data folder…", on_click=self._relocate))
        prow.addWidget(button("Open log folder", on_click=self._open_logs))
        prow.addStretch(1)
        pr.body.addLayout(prow)
        pr.add(muted("Logs record events and counts only — never resume content, passwords, API keys or tokens. "
                     "No telemetry is collected, and nothing is sent anywhere unless you turn on synchronisation "
                     "or an AI provider."))
        self.body.addWidget(pr)
        # AI
        ai = Card("Optional external AI provider")
        ai.add(banner(AI_DISCLOSURE, "warn"))
        af = QFormLayout()
        self.ai = QComboBox()
        for v, t in (("off", "Off (built-in rules engine only)"), ("anthropic", "Anthropic API"),
                     ("openai_compatible", "OpenAI-compatible endpoint")):
            self.ai.addItem(t, v)
        self.ai_endpoint = QLineEdit()
        self.ai_endpoint.setPlaceholderText("https://… (empty = provider default)")
        self.ai_model = QLineEdit()
        self.ai_model.setPlaceholderText("Model name")
        key_row = QHBoxLayout()
        self.ai_key_state = QLabel("")
        key_row.addWidget(self.ai_key_state, 1)
        key_row.addWidget(button("Set API key…", on_click=self._set_key))
        key_row.addWidget(button("Remove key", on_click=self._remove_key))
        af.addRow("Provider:", self.ai)
        af.addRow("Endpoint:", self.ai_endpoint)
        af.addRow("Model:", self.ai_model)
        af.addRow("API key:", key_row)
        ai.body.addLayout(af)
        ai.add(muted("The API key is stored only in the operating system's credential store. Every request is shown "
                     "to you before it is sent."))
        self.ai.currentIndexChanged.connect(self._ai_changed)
        self.ai_endpoint.editingFinished.connect(self._ai_changed)
        self.ai_model.editingFinished.connect(self._ai_changed)
        self.body.addWidget(ai)
        # workspaces
        wsc = Card("Workspaces")
        wsc.add(muted("Each workspace is a separate profile database. The fictional sample workspace is for "
                      "exploring the application safely."))
        self.ws_list = QListWidget()
        self.ws_list.setMaximumHeight(140)
        self.ws_list.setAccessibleName("Workspaces")
        wsc.add(self.ws_list)
        wrow2 = QHBoxLayout()
        for text, fn in (("Open selected", self._open_ws), ("New workspace…", self._new_ws),
                         ("Rename…", self._rename_ws), ("Open fictional sample", self._open_sample)):
            wrow2.addWidget(button(text, on_click=fn))
        wrow2.addStretch(1)
        wsc.body.addLayout(wrow2)
        self.body.addWidget(wsc)
        # glossary
        gl = Card("Glossary for engineering readers")
        gl.add(muted("Used by 'Explain domain terms'. Add or override explanations of specialist terms."))
        self.glossary = QTableWidget(0, 2)
        self.glossary.setHorizontalHeaderLabels(["Term", "Explanation"])
        self.glossary.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.glossary.verticalHeader().setVisible(False)
        self.glossary.setMinimumHeight(160)
        self.glossary.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.glossary.setAccessibleName("Glossary overrides")
        gl.add(self.glossary)
        grow = QHBoxLayout()
        grow.addWidget(button("Add term", on_click=self._add_term))
        grow.addWidget(button("Remove selected", on_click=self._remove_term))
        grow.addStretch(1)
        grow.addWidget(button("Save glossary", on_click=self._save_glossary))
        gl.body.addLayout(grow)
        self.body.addWidget(gl)
        about = Card(f"About {APP_NAME}")
        about.add(QLabel(f"Version {__version__}. Local-first: your data stays on this computer."))
        about.add(muted("Bundled fonts: Carlito and Caladea (SIL Open Font License), Liberation (SIL OFL), DejaVu "
                        "(Bitstream Vera licence). See assets/fonts/LICENSES."))
        self.body.addWidget(about)
        self.body.addStretch(1)
        self.status = banner("", "info")
        self.status.setVisible(False)

    def kinds_of_interest(self) -> set[str] | None:
        return set()

    def refresh(self) -> None:
        self._loading = True
        c = self.ctx.config
        s = self.ctx.settings
        self.theme.setCurrentIndex(max(self.theme.findData(c.theme), 0))
        self.ui_scale.setValue(c.ui_font_scale or 1.0)
        self.update_auto.setChecked(c.update_auto_check)
        self.update_channel.setCurrentIndex(max(self.update_channel.findData(c.update_channel), 0))
        self.update_status.setText(f"Last checked {c.update_last_check[:16].replace('T', ' ')} UTC."
                                   if c.update_last_check else "Not checked yet.")
        self.engine.setCurrentIndex(max(self.engine.findData(c.pdf_engine), 0))
        self.lo_path.setText(c.libreoffice_path)
        self.export_folder.setText(s.get("export.default_folder") or "")
        self.pattern.setText(s.get("export.filename_pattern") or "")
        w = s.get("scoring.weights") or DEFAULT_WEIGHTS
        for k, sp in self.weights.items():
            sp.setValue(int(round(float(w.get(k, 0)))))
        self.ai.setCurrentIndex(max(self.ai.findData(c.ai_provider), 0))
        self.ai_endpoint.setText(c.ai_endpoint)
        self.ai_model.setText(c.ai_model)
        self._loading = False
        self._weights_changed()
        self._lo_status()
        self.keyring.setText("Credential store: " + self.ctx.secrets.describe())
        self.data_dir.setText(f"Data folder: {c.resolved_data_dir()}")
        self.ai_key_state.setText("Key stored." if self.ctx.secrets.has("ai_api_key") else "No key stored.")
        self.ws_list.clear()
        for e in self.ctx.manager.entries():
            it = QListWidgetItem(e.name + (" (fictional sample)" if e.is_sample else "")
                                 + ("  ← open" if self.ctx.ws and e.id == self.ctx.ws.id else ""))
            it.setData(Qt.ItemDataRole.UserRole, e.id)
            self.ws_list.addItem(it)
        self.glossary.setRowCount(0)
        for k, v in (s.get("glossary.overrides") or {}).items():
            r = self.glossary.rowCount()
            self.glossary.insertRow(r)
            self.glossary.setItem(r, 0, QTableWidgetItem(k))
            self.glossary.setItem(r, 1, QTableWidgetItem(v))

    def _save_config(self) -> None:
        try:
            self.ctx.config.save()
        except OSError as exc:
            error(self, "Settings", "The settings could not be saved.", str(exc))

    def _appearance_changed(self) -> None:
        if self._loading:
            return
        self.ctx.config.theme = self.theme.currentData()
        self.ctx.config.ui_font_scale = round(self.ui_scale.value(), 2)
        self._save_config()
        if self.on_theme:
            self.on_theme()

    def _updates_changed(self) -> None:
        if self._loading:
            return
        self.ctx.config.update_auto_check = self.update_auto.isChecked()
        self.ctx.config.update_channel = self.update_channel.currentData()
        self._save_config()

    def _check_updates(self) -> None:
        self.update_status.setText("Checking…")
        if self.on_check_updates:
            self.on_check_updates()

    def customise_appearance(self, exec_dialog: bool = True):
        from ris.ui.appearance import AppearanceDialog

        def applied() -> None:
            if self.on_theme:
                self.on_theme()

        dlg = AppearanceDialog(self, self.ctx, applied)
        if exec_dialog:
            dlg.exec()
            self.refresh()
        return dlg

    def _docs_changed(self) -> None:
        if self._loading:
            return
        self.ctx.config.pdf_engine = self.engine.currentData()
        self.ctx.config.libreoffice_path = self.lo_path.text().strip()
        self._save_config()
        folder = self.export_folder.text().strip()
        self.ctx.settings.set("export.default_folder", folder)
        pat = self.pattern.text().strip() or "{name} - {variant} - {date}"
        self.ctx.settings.set("export.filename_pattern", pat)
        self._lo_status()

    def _lo_status(self) -> None:
        from ris.rendering.libreoffice import find_soffice, version

        p = find_soffice(self.lo_path.text().strip() or None)
        if p is None:
            self.lo_status.setText("LibreOffice was not found. PDFs are produced by the built-in engine. Installing "
                                   "LibreOffice gives PDFs that match the Word layout most closely.")
        else:
            self.lo_status.setText(f"Found: {p} ({version(str(p)) or 'version unknown'})")

    def _browse_lo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Locate LibreOffice (soffice)")
        if path:
            self.lo_path.setText(path)
            self._docs_changed()

    def _detect_lo(self) -> None:
        self.lo_path.setText("")
        self._docs_changed()

    def _browse_export(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Default export folder")
        if d:
            self.export_folder.setText(d)
            self._docs_changed()

    def _weights_changed(self) -> None:
        total = sum(sp.value() for sp in self.weights.values())
        self.weight_total.setText(f"Total: {total} %" + ("" if total == 100 else " — weights are normalised to 100."))
        if self._loading or total == 0:
            return
        self.ctx.settings.set("scoring.weights", {k: sp.value() for k, sp in self.weights.items()})
        self.ctx.data_changed.emit({"settings"})

    def _reset_weights(self) -> None:
        self._loading = True
        for k, sp in self.weights.items():
            sp.setValue(DEFAULT_WEIGHTS[k])
        self._loading = False
        self._weights_changed()

    def _relocate(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose an empty folder for your data")
        if not d:
            return
        if not confirm(self, "Move data folder", f"Copy all workspaces to {d} and use that location from now on?",
                       detail="The data is copied and verified first; the old folder is left in place for you to "
                              "delete once you are satisfied."):
            return
        current = self.ctx.manager.active_entry()
        self.ctx.close_workspace(backup=False)
        try:
            old = self.ctx.manager.relocate(Path(d))
        except RISError as exc:
            error(self, "Move data folder", exc.user_message, exc.detail)
            self.ctx.open_entry(current)
            return
        self.ctx.templates.user_dir = self.ctx.config.resolved_data_dir() / "templates"
        self.ctx.templates.reload()
        self.ctx.open_entry(self.ctx.manager.active_entry())
        info(self, "Data folder moved", f"Your data is now in {d}. The previous folder ({old}) was left in place.")

    def _open_logs(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.config.resolved_data_dir() / "logs")))

    def _ai_changed(self) -> None:
        if self._loading:
            return
        prov = self.ai.currentData()
        if prov != "off" and self.ctx.config.ai_provider == "off":
            if not confirm(self, "External AI provider", "Allow sending selected statements to an external AI "
                                                         "provider when you ask for a suggestion?",
                           detail=AI_DISCLOSURE):
                self._loading = True
                self.ai.setCurrentIndex(0)
                self._loading = False
                return
        self.ctx.config.ai_provider = prov
        self.ctx.config.ai_endpoint = self.ai_endpoint.text().strip()
        self.ctx.config.ai_model = self.ai_model.text().strip()
        self._save_config()

    def _set_key(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        key, ok = QInputDialog.getText(self, "API key", "Paste the API key (stored in the credential store):",
                                       QLineEdit.EchoMode.Password)
        if ok and key.strip():
            persistent = self.ctx.secrets.set("ai_api_key", key.strip())
            self.ai_key_state.setText("Key stored." if persistent else "Key kept for this session only.")

    def _remove_key(self) -> None:
        self.ctx.secrets.delete("ai_api_key")
        self.ai_key_state.setText("No key stored.")

    # workspaces
    def _selected_ws(self):
        it = self.ws_list.currentItem()
        return self.ctx.config.find_workspace(it.data(Qt.ItemDataRole.UserRole)) if it else None

    def _open_ws(self) -> None:
        e = self._selected_ws()
        if e is not None and self.on_workspace:
            self.on_workspace(e)

    def _new_ws(self) -> None:
        name = ask_text(self, "New workspace", "Name:")
        if name and self.on_workspace:
            self.on_workspace(self.ctx.manager.create(name))

    def _rename_ws(self) -> None:
        e = self._selected_ws()
        if e is None:
            return
        name = ask_text(self, "Rename workspace", "New name:", e.name)
        if name:
            self.ctx.manager.rename(e.id, name)
            if self.ctx.ws and self.ctx.ws.id == e.id:
                self.ctx.ws.name = name
            self.refresh()

    def _open_sample(self) -> None:
        if self.on_workspace:
            self.on_workspace(self.ctx.manager.ensure_sample())

    # glossary
    def _add_term(self) -> None:
        r = self.glossary.rowCount()
        self.glossary.insertRow(r)
        self.glossary.setItem(r, 0, QTableWidgetItem(""))
        self.glossary.setItem(r, 1, QTableWidgetItem(""))
        self.glossary.editItem(self.glossary.item(r, 0))

    def _remove_term(self) -> None:
        for r in sorted({i.row() for i in self.glossary.selectedIndexes()}, reverse=True):
            self.glossary.removeRow(r)

    def _save_glossary(self) -> None:
        out = {}
        for r in range(self.glossary.rowCount()):
            k = (self.glossary.item(r, 0).text() if self.glossary.item(r, 0) else "").strip()
            v = (self.glossary.item(r, 1).text() if self.glossary.item(r, 1) else "").strip()
            if k and v:
                out[k] = v
        self.ctx.settings.set("glossary.overrides", out)
        self.ctx.say("Glossary saved.")


_ = (QCheckBox, set_banner)
