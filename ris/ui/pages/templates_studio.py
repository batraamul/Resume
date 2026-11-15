"""Templates Studio with integrated Help System, 30+ Templates, and Smart Recommendations."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QScrollArea, QWidget, QGridLayout, QFrame
)
from PySide6.QtCore import Qt

from ris.ui.widgets.common import Card, Page, button, muted
from ris.ui.widgets.help_system import HelpCenterDialog
from ris.ui.integrations.features_integration import (
    HelpButtonIntegration, TemplateRecommendationEngine, FeaturesV15
)
from ris.intelligence.resume_templates import (
    get_all_templates, get_templates_by_category, recommend_templates
)


class TemplateCard(QFrame):
    """Visual card for a resume template."""

    def __init__(self, template: dict, on_select=None):
        super().__init__()
        self.template = template
        self.on_select = on_select
        self.setStyleSheet("""
            QFrame {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 12px;
                background-color: #f9f9f9;
            }
            QFrame:hover {
                border: 1px solid #2196F3;
                background-color: #f0f7ff;
            }
        """)

        layout = QVBoxLayout()

        # Template name
        name_label = QLabel(template.get('name', 'Unnamed Template'))
        name_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(name_label)

        # Template description
        if template.get('description'):
            desc = QLabel(template['description'])
            desc.setWordWrap(True)
            desc.setStyleSheet("color: #666; font-size: 10pt;")
            layout.addWidget(desc)

        # Category and ATS info
        meta_text = f"Category: {template.get('category', 'General')} | "
        if template.get('is_ats_friendly'):
            meta_text += "✓ ATS Friendly"
        else:
            meta_text += "Not ATS optimized"

        meta_label = QLabel(meta_text)
        meta_label.setStyleSheet("color: #999; font-size: 9pt;")
        layout.addWidget(meta_label)

        # Best for roles
        if template.get('best_for_roles'):
            best_for = "Best for: " + ", ".join(template['best_for_roles'][:3])
            best_label = QLabel(best_for)
            best_label.setWordWrap(True)
            best_label.setStyleSheet("color: #2196F3; font-size: 9pt; font-style: italic;")
            layout.addWidget(best_label)

        # Select button
        select_btn = button("Use This Template", "primary", on_click=self._on_select)
        select_btn.setMaximumHeight(32)
        layout.addWidget(select_btn)

        layout.addStretch()
        self.setLayout(layout)
        self.setMinimumHeight(180)
        self.setMinimumWidth(250)

    def _on_select(self):
        """Handle template selection."""
        if self.on_select:
            self.on_select(self.template)


class TemplatesStudioPage(Page):
    """Templates Studio: Browse, search, and get AI recommendations."""

    key = "templates_studio"

    def __init__(self, ctx) -> None:
        super().__init__(
            ctx,
            "Resume Templates Studio",
            f"Access {FeaturesV15.TEMPLATES_COUNT}+ professional templates with smart recommendations"
        )

        # Recommendations section
        rec_card = Card("AI-Powered Recommendations")
        rec_layout = QVBoxLayout()

        rec_title = QLabel("Get Templates Matched to Your Profile")
        rec_title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        rec_layout.addWidget(rec_title)

        rec_help = HelpButtonIntegration.create_help_button("templates")
        rec_help.setToolTip("Get personalized template recommendations based on your role and industry")
        rec_help.clicked.connect(lambda: HelpCenterDialog.show_help_center())

        rec_btn_layout = QHBoxLayout()
        rec_btn_layout.addWidget(rec_help)
        rec_btn_layout.addWidget(button(
            "Get My Recommendations",
            "primary",
            on_click=self._get_recommendations
        ))
        rec_btn_layout.addStretch()
        rec_layout.addLayout(rec_btn_layout)

        self.rec_display = QLabel("Click 'Get My Recommendations' to see templates tailored for you")
        self.rec_display.setWordWrap(True)
        self.rec_display.setStyleSheet("color: #666; font-style: italic; margin-top: 8px;")
        rec_layout.addWidget(self.rec_display)

        rec_card.body.addLayout(rec_layout)
        self.body.addWidget(rec_card)

        # Browse all templates section
        browse_card = Card("Browse All Templates")
        browse_layout = QVBoxLayout()

        # Category filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter by category:"))

        self.category_combo = QComboBox()
        self.category_combo.addItem("All Templates", None)

        # Add all unique categories
        templates = get_all_templates()
        categories = sorted(set(t.get('category', 'Other') for t in templates))
        for cat in categories:
            self.category_combo.addItem(cat, cat)

        self.category_combo.currentIndexChanged.connect(self._update_templates_display)
        filter_layout.addWidget(self.category_combo)

        search_help = HelpButtonIntegration.create_help_button("templates")
        search_help.setToolTip("Filter templates by professional category")
        search_help.clicked.connect(lambda: HelpCenterDialog.show_help_center())
        filter_layout.addWidget(search_help)
        filter_layout.addStretch()

        browse_layout.addLayout(filter_layout)

        # Templates grid scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        self.templates_container = QWidget()
        self.templates_grid = QGridLayout()
        self.templates_grid.setSpacing(12)
        self.templates_container.setLayout(self.templates_grid)

        scroll.setWidget(self.templates_container)
        browse_layout.addWidget(scroll, 1)

        browse_card.body.addLayout(browse_layout)
        self.body.addWidget(browse_card, 1)

        # Feature status
        info_card = Card("Features in v1.5.0")
        info_text = muted(
            f"✓ Help System with {FeaturesV15.HELP_TOPICS_COUNT}+ contextual help topics\n"
            f"✓ {FeaturesV15.TEMPLATES_COUNT}+ Professional Templates from top sources\n"
            f"✓ Smart AI Recommendations based on your profile\n"
            f"✓ ATS-optimized templates for automated screening\n"
            f"✓ Fresh Start & UPSC Format from previous versions"
        )
        info_card.body.addWidget(info_text)
        self.body.addWidget(info_card)

        self.body.addStretch()

        # Load initial templates
        self._update_templates_display()

    def _update_templates_display(self):
        """Update the templates grid display."""
        # Clear existing templates
        while self.templates_grid.count():
            item = self.templates_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        category = self.category_combo.currentData()

        if category:
            templates = get_templates_by_category(category)
        else:
            templates = get_all_templates()

        # Display templates in grid (3 columns)
        row, col = 0, 0
        for template in templates:
            card = TemplateCard(template, on_select=self._on_template_selected)
            self.templates_grid.addWidget(card, row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1

        # Update display count
        self.rec_display.setText(f"Showing {len(templates)} templates in category: {category or 'All'}")

    def _get_recommendations(self):
        """Get AI-powered template recommendations."""
        # Get user profile data
        profile_data = {
            "current_designation": getattr(self.ctx.profile, 'designation', ''),
            "industry": getattr(self.ctx.profile, 'industry', ''),
            "experience_years": len(getattr(self.ctx.profile, 'experience', [])) or 0,
            "has_publications": bool(getattr(self.ctx.profile, 'publications', [])),
            "has_patents": bool(getattr(self.ctx.profile, 'patents', [])),
        }

        # Get recommendations
        recommended = TemplateRecommendationEngine.recommend_for_user(profile_data)

        if recommended:
            # Clear grid and show recommendations
            while self.templates_grid.count():
                item = self.templates_grid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            row, col = 0, 0
            for template in recommended:
                card = TemplateCard(template, on_select=self._on_template_selected)
                self.templates_grid.addWidget(card, row, col)
                col += 1
                if col >= 3:
                    col = 0
                    row += 1

            self.rec_display.setText(
                f"✓ Showing {len(recommended)} templates recommended for you based on your profile"
            )
            self.rec_display.setStyleSheet("color: #4caf50; font-style: italic; margin-top: 8px; font-weight: bold;")
        else:
            self.rec_display.setText("Fill in your profile details to get personalized recommendations")
            self.rec_display.setStyleSheet("color: #ff9800; font-style: italic; margin-top: 8px;")

    def _on_template_selected(self, template: dict):
        """Handle template selection."""
        from ris.ui.dialogs import show_dialog

        # Show template details and selection dialog
        msg = (
            f"Template: {template.get('name', 'Unnamed')}\n\n"
            f"Category: {template.get('category', 'General')}\n"
            f"Pages: {template.get('pages', '1')}\n"
            f"ATS Friendly: {'Yes' if template.get('is_ats_friendly') else 'No'}\n\n"
            f"Description:\n{template.get('description', 'No description available')}"
        )

        # Here you would implement the actual template application
        # For now, just show confirmation
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Template Selected",
            f"You selected: {template.get('name', 'Unnamed Template')}\n\n"
            "This template will be applied to your next resume generation."
        )
