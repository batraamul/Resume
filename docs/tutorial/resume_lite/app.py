"""Step 5 — the desktop window with PySide6 (Qt for Python)."""
from __future__ import annotations

import sys
from pathlib import Path

from pydantic import ValidationError
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from export_docx import export_docx
from export_pdf import export_pdf
from model import Job, Profile
from storage import Store


def parse_jobs(text: str) -> list[Job]:
    """Each job starts with 'Title | Organisation | start | end'; lines starting with '- ' are achievements."""
    jobs: list[Job] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("- ") and jobs:
            jobs[-1].achievements.append(line[2:].strip())
        else:
            parts = [p.strip() for p in line.split("|")] + ["", "", ""]
            jobs.append(Job(title=parts[0], organisation=parts[1], start=parts[2],
                            end="" if parts[3].lower() in ("", "present") else parts[3]))
    return jobs


def jobs_to_text(jobs: list[Job]) -> str:
    lines = []
    for j in jobs:
        lines.append(f"{j.title} | {j.organisation} | {j.start} | {j.end or 'present'}")
        lines += [f"- {a}" for a in j.achievements]
    return "\n".join(lines)


class MainWindow(QWidget):
    def __init__(self, store: Store) -> None:
        super().__init__()
        self.store = store
        self.setWindowTitle("Resume Lite")
        self.name, self.email, self.headline = QLineEdit(), QLineEdit(), QLineEdit()
        self.summary, self.jobs, self.skills = QPlainTextEdit(), QPlainTextEdit(), QLineEdit()
        self.jobs.setPlaceholderText("Scientist | Example Lab | 2019-04 | present\n- Led the sensor test programme")
        form = QFormLayout()
        for label, widget in (("Name", self.name), ("Email", self.email), ("Headline", self.headline),
                              ("Summary", self.summary), ("Experience", self.jobs), ("Skills (comma separated)",
                                                                                   self.skills)):
            form.addRow(label + ":", widget)
        buttons = QHBoxLayout()
        for text, slot in (("Save", self.save), ("Export Word", lambda: self.export("docx")),
                           ("Export PDF", lambda: self.export("pdf"))):
            b = QPushButton(text)
            b.clicked.connect(slot)          # signal (clicked) → slot (our method)
            buttons.addWidget(b)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)
        if (p := store.load()) is not None:
            self.show_profile(p)

    def show_profile(self, p: Profile) -> None:
        self.name.setText(p.name)
        self.email.setText(p.email)
        self.headline.setText(p.headline)
        self.summary.setPlainText(p.summary)
        self.jobs.setPlainText(jobs_to_text(p.jobs))
        self.skills.setText(", ".join(p.skills))

    def profile(self) -> Profile:
        return Profile(name=self.name.text(), email=self.email.text(), headline=self.headline.text(),
                       summary=self.summary.toPlainText(), jobs=parse_jobs(self.jobs.toPlainText()),
                       skills=[s.strip() for s in self.skills.text().split(",") if s.strip()])

    def save(self) -> bool:
        try:
            self.store.save(self.profile())
            return True
        except ValidationError as exc:      # show the model's own error messages
            QMessageBox.warning(self, "Please check", str(exc))
            return False

    def export(self, kind: str) -> None:
        if not self.save():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export", f"Resume.{kind}")
        if path:
            (export_docx if kind == "docx" else export_pdf)(self.profile(), Path(path))


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow(Store(Path.home() / "resume_lite.db"))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
