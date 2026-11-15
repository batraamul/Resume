"""Contextual help system for the application."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QSplitter, QPushButton
from PySide6.QtCore import Qt, pyqtSignal
from PySide6.QtGui import QFont

from ris.ui.widgets.common import button, Card


HELP_TOPICS = {
    "name": {
        "title": "Full Name",
        "description": "Enter your complete professional name as it should appear on your resume.",
        "tips": [
            "Use your official name or preferred professional name",
            "Include middle names if they are part of your professional identity",
            "Example: Dr. Amul Batra",
        ],
    },
    "email": {
        "title": "Email Address",
        "description": "A professional email address where employers can contact you.",
        "tips": [
            "Use a professional email format (firstname.lastname@example.com)",
            "Avoid informal email addresses",
            "Make sure you have access to this email inbox",
        ],
    },
    "phone": {
        "title": "Phone Number",
        "description": "A reliable phone number for job inquiries.",
        "tips": [
            "Include country code if applying internationally",
            "Use a professional voicemail greeting",
            "Example: +91-98765-43210",
        ],
    },
    "experience": {
        "title": "Professional Experience",
        "description": "Document your work history with specific roles, responsibilities, and achievements.",
        "tips": [
            "Use the STAR method: Situation, Task, Action, Result",
            "Quantify achievements (% improvement, cost savings, etc.)",
            "Focus on accomplishments, not just duties",
            "Example: 'Led team of 5 engineers, increased productivity by 30%'",
        ],
    },
    "education": {
        "title": "Education & Qualifications",
        "description": "List your degrees, certifications, and educational achievements.",
        "tips": [
            "Include institution name and graduation date",
            "Add relevant coursework or specializations",
            "Include GPA if it's 3.5 or above",
        ],
    },
    "skills": {
        "title": "Technical Skills",
        "description": "List relevant technical skills, programming languages, tools, and frameworks.",
        "tips": [
            "Prioritize skills relevant to your target role",
            "Be honest about your proficiency level",
            "Group skills by category (Languages, Tools, Frameworks)",
        ],
    },
    "upsc_format": {
        "title": "UPSC Deputation Format",
        "description": "Special format for Government of India recruitment and deputation.",
        "tips": [
            "Follows DoPT OM dated 02.07.2015",
            "Includes APARs (Annual Performance Assessment Reports)",
            "Requires compliance checklist completion",
            "Supports three recruitment modes: Deputation, Lateral Entry, Research Scientist",
        ],
    },
}


class HelpButton(QPushButton):
    """Blue help button that displays contextual help."""

    help_requested = pyqtSignal(str)

    def __init__(self, help_key: str, tooltip: str = ""):
        super().__init__("?")
        self.help_key = help_key
        self.setMaximumWidth(30)
        self.setMaximumHeight(30)
        self.setStyleSheet("QPushButton { background-color: #2196F3; color: white; font-weight: bold; border-radius: 15px; }")
        self.setToolTip(tooltip or f"Help: {help_key}")
        self.clicked.connect(lambda: self.help_requested.emit(self.help_key))


class HelpCenterDialog(QDialog):
    """Full help center with searchable help topics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Help Center")
        self.setModal(True)
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)

        layout = QVBoxLayout()

        # Search box
        search_label = QLabel("Search help topics:")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Type to search...")
        self.search_box.textChanged.connect(self._filter_topics)
        layout.addWidget(search_label)
        layout.addWidget(self.search_box)

        # Splitter with topics list and help content
        splitter = QSplitter(Qt.Horizontal)

        # Topics list
        self.topics_list = QListWidget()
        for key, content in HELP_TOPICS.items():
            item = QListWidgetItem(content["title"])
            item.setData(Qt.UserRole, key)
            self.topics_list.addItem(item)
        self.topics_list.itemClicked.connect(self._show_topic)
        splitter.addWidget(self.topics_list)

        # Help content area
        self.content_widget = Card("Help Content")
        self.topic_title = QLabel()
        self.topic_title.setFont(QFont())
        self.topic_title.font().setBold(True)
        self.topic_description = QLabel()
        self.topic_description.setWordWrap(True)
        self.topic_tips = QLabel()
        self.topic_tips.setWordWrap(True)

        self.content_widget.body.addWidget(self.topic_title)
        self.content_widget.body.addWidget(self.topic_description)
        self.content_widget.body.addWidget(self.topic_tips)
        self.content_widget.body.addStretch()

        splitter.addWidget(self.content_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

        # Close button
        close_btn = button("Close", on_click=self.accept)
        layout.addWidget(close_btn)

        self.setLayout(layout)

        # Show first topic
        if self.topics_list.count() > 0:
            self.topics_list.setCurrentRow(0)
            self._show_topic(self.topics_list.item(0))

    def _filter_topics(self):
        """Filter topics based on search text."""
        search_text = self.search_box.text().lower()
        for i in range(self.topics_list.count()):
            item = self.topics_list.item(i)
            text = item.text().lower()
            item.setHidden(search_text not in text)

    def _show_topic(self, item):
        """Display selected topic."""
        key = item.data(Qt.UserRole)
        if key in HELP_TOPICS:
            topic = HELP_TOPICS[key]
            self.topic_title.setText(topic["title"])
            self.topic_description.setText(topic["description"])
            tips_text = "Tips:\n" + "\n".join(f"• {tip}" for tip in topic["tips"])
            self.topic_tips.setText(tips_text)

    @staticmethod
    def show_help_center(parent=None):
        """Show the help center dialog."""
        dialog = HelpCenterDialog(parent)
        dialog.exec()
