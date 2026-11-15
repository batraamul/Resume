"""UPSC Deputation Format Preview and Selection."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QLabel, QComboBox, QTextEdit
from PySide6.QtCore import Qt

from ris.ui.widgets.common import Card, Page, button, muted
from ris.intelligence.upsc_formats import (
    UPSCRecruitmentMode,
    recommend_upsc_format,
    UPSC_SECTIONS,
    UPSC_DEPUTATION_CHECKLIST,
    UPSC_LATERAL_ENTRY_CHECKLIST,
    UPSC_RESEARCH_SCIENTIST_CHECKLIST,
)


class UPSCFormatPage(Page):
    """UPSC Deputation Format preview and information."""

    key = "upsc_format"

    def __init__(self, ctx) -> None:
        super().__init__(ctx, "UPSC Deputation Format", "DoPT OM 02.07.2015 Compliant Bio-data Proforma")

        # Recruitment mode selector
        mode_card = Card("Select Recruitment Mode")
        mode_layout = QVBoxLayout()

        mode_label = QLabel("Recruitment Type:")
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Deputation", "deputation")
        self.mode_combo.addItem("Lateral Entry", "lateral_entry")
        self.mode_combo.addItem("Research Scientist", "research_scientist")
        self.mode_combo.currentIndexChanged.connect(self._update_format_display)

        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_combo)
        mode_card.body.addLayout(mode_layout)
        self.body.addWidget(mode_card)

        # Format description
        desc_card = Card("Format Overview")
        self.description_text = QLabel()
        self.description_text.setWordWrap(True)
        desc_card.body.addWidget(self.description_text)
        self.body.addWidget(desc_card)

        # Sections display
        sections_card = Card("Required Sections")
        self.sections_text = QTextEdit()
        self.sections_text.setReadOnly(True)
        self.sections_text.setMaximumHeight(200)
        sections_card.body.addWidget(self.sections_text)
        self.body.addWidget(sections_card)

        # Compliance checklist
        checklist_card = Card("Compliance Checklist")
        self.checklist_text = QTextEdit()
        self.checklist_text.setReadOnly(True)
        self.checklist_text.setMaximumHeight(200)
        checklist_card.body.addWidget(self.checklist_text)
        self.body.addWidget(checklist_card)

        # Information text
        info_text = muted(
            "The UPSC Bio-data Proforma follows DoPT OM dated 02.07.2015. "
            "This format is used for deputation to UPSC and other government organizations. "
            "Ensure all required sections are filled completely for successful submission."
        )
        self.body.addWidget(info_text)
        self.body.addStretch()

        # Update initial display
        self._update_format_display()

    def _update_format_display(self) -> None:
        """Update the displayed format information based on selected mode."""
        mode = self.mode_combo.currentData()

        # Get recommendation
        advice = recommend_upsc_format(level="scientist_f")

        # Update description
        if mode == "deputation":
            desc = (
                "Deputation Format: For existing government servants applying for "
                "deputation to UPSC and other central government organizations.\n\n"
                "Requirements:\n"
                "• All APARs for last 5 years\n"
                "• No vigilance or integrity issues\n"
                "• Medical fitness certificate\n"
                "• Character assessment from employer"
            )
            checklist = UPSC_DEPUTATION_CHECKLIST
        elif mode == "lateral_entry":
            desc = (
                "Lateral Entry Format: For specialists with 10+ years of experience "
                "and recognized expertise in their domain.\n\n"
                "Requirements:\n"
                "• Minimum 10 years relevant experience\n"
                "• Publications or patents (if applicable)\n"
                "• Recognized expertise documentation\n"
                "• Educational qualifications"
            )
            checklist = UPSC_LATERAL_ENTRY_CHECKLIST
        else:  # research_scientist
            desc = (
                "Research Scientist Format: For researchers with significant publications "
                "and research contributions.\n\n"
                "Requirements:\n"
                "• Research publications in peer-reviewed journals\n"
                "• Patents or IPR (if applicable)\n"
                "• Citation record\n"
                "• PhD or postdoc credentials"
            )
            checklist = UPSC_RESEARCH_SCIENTIST_CHECKLIST

        self.description_text.setText(desc)

        # Update sections
        sections_text = "Required Sections in Bio-data Proforma:\n\n"
        for section_key, section_info in UPSC_SECTIONS.items():
            sections_text += f"• {section_info['title']}\n"
            for field in section_info['fields']:
                sections_text += f"  - {field}\n"
            sections_text += "\n"

        self.sections_text.setPlainText(sections_text)

        # Update checklist
        checklist_text = "Compliance Checklist:\n\n"
        for item in checklist:
            checklist_text += f"{item}\n"

        self.checklist_text.setPlainText(checklist_text)
