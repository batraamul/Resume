"""Fresh Start - Safe data deletion dialog."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QDialog, QLabel, QVBoxLayout
from PySide6.QtCore import Qt

from ris.ui.widgets.common import button, confirm, error, info


class FreshStartDialog(QDialog):
    """Safe data deletion with backup."""

    def __init__(self, parent, workspace_path: Path) -> None:
        super().__init__(parent)
        self.workspace_path = Path(workspace_path)
        self.setWindowTitle("Fresh Start")
        self.setModal(True)
        self.setMinimumWidth(500)

        layout = QVBoxLayout()

        # Warning message
        warning = QLabel(
            "⚠️  <b>Fresh Start</b> will delete ALL your resume data, profiles, and variants.\n\n"
            "This action:\n"
            "• Deletes all stored resumes and profiles\n"
            "• Cannot be undone\n"
            "• Automatically creates a backup first\n\n"
            "Are you absolutely sure?"
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        # Confirmation checkbox
        self.confirm_check = QCheckBox("Yes, I understand and want to delete all data")
        layout.addWidget(self.confirm_check)

        # Buttons
        btn_layout = self._create_button_layout()
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _create_button_layout(self):
        from PySide6.QtWidgets import QHBoxLayout

        layout = QHBoxLayout()
        layout.addStretch()

        cancel_btn = button("Cancel", on_click=self.reject)
        delete_btn = button("Delete All Data", "danger", on_click=self._perform_fresh_start)

        layout.addWidget(cancel_btn)
        layout.addWidget(delete_btn)

        return layout

    def _perform_fresh_start(self):
        """Perform the fresh start operation."""
        if not self.confirm_check.isChecked():
            error(self, "Confirmation Required", "Please confirm that you understand the consequences.")
            return

        try:
            # Create backup
            backup_dir = self.workspace_path / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_before_fresh_start_{timestamp}"
            backup_path = backup_dir / backup_name

            # Backup data
            data_dir = self.workspace_path / "data"
            if data_dir.exists():
                shutil.copytree(data_dir, backup_path)

            # Delete all data
            if data_dir.exists():
                shutil.rmtree(data_dir)

            # Recreate empty data directory
            data_dir.mkdir(parents=True, exist_ok=True)

            info(
                self,
                "Fresh Start Complete",
                f"All data has been deleted.\n\nBackup saved to:\n{backup_path}",
            )
            self.accept()

        except Exception as e:
            error(self, "Fresh Start Failed", f"Error during fresh start:\n{str(e)}")


def show_fresh_start_dialog(parent, workspace_path: Path) -> bool:
    """Show fresh start dialog and return whether user confirmed."""
    dialog = FreshStartDialog(parent, workspace_path)
    return dialog.exec() == QDialog.Accepted
