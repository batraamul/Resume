"""Integration layer for v1.5.0 features: Help System, Templates, and Recommendations."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QWidget, QPushButton
from PySide6.QtCore import Qt, pyqtSignal

from ris.ui.widgets.help_system import HelpCenterDialog
from ris.intelligence.resume_templates import recommend_templates, get_all_templates
from ris.intelligence.upsc_formats import recommend_upsc_format


class HelpButtonIntegration:
    """Mixin to add help buttons to form fields."""

    HELP_TOPICS = {
        "name": ("Full Name", "Enter your complete professional name as it should appear on your resume."),
        "email": ("Email", "A professional email address where employers can contact you."),
        "phone": ("Phone", "A reliable phone number for job inquiries."),
        "summary": ("Professional Summary", "A brief overview of your professional background and goals."),
        "date_of_birth": ("Date of Birth", "Your date of birth (format: YYYY-MM-DD)."),
        "location": ("Location", "Your current city and country."),
        "designation": ("Designation", "Your current job title or position."),
        "organization": ("Organization", "The name of your current or recent employer."),
        "responsibilities": ("Responsibilities", "Key duties and responsibilities in your role."),
        "achievements": ("Achievements", "Quantified achievements and impact metrics."),
        "skills": ("Skills", "Technical and professional skills relevant to your target role."),
        "education": ("Education", "Degree, institution, graduation date and relevant coursework."),
        "certifications": ("Certifications", "Professional certifications and licenses."),
        "publications": ("Publications", "Research papers, articles or publications you've authored."),
        "projects": ("Projects", "Notable projects you've worked on with descriptions."),
    }

    @staticmethod
    def create_help_button(field_name: str) -> QPushButton:
        """Create a help button for a form field."""
        btn = QPushButton("?")
        btn.setMaximumWidth(30)
        btn.setMaximumHeight(30)
        btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; font-weight: bold; border-radius: 15px; }")

        if field_name in HelpButtonIntegration.HELP_TOPICS:
            title, desc = HelpButtonIntegration.HELP_TOPICS[field_name]
            btn.setToolTip(desc)

        return btn

    @staticmethod
    def add_help_to_layout(layout: QHBoxLayout, field_name: str) -> None:
        """Add a help button to a horizontal layout."""
        help_btn = HelpButtonIntegration.create_help_button(field_name)
        help_btn.clicked.connect(lambda: HelpCenterDialog.show_help_center())
        layout.addWidget(help_btn)


class TemplateRecommendationEngine:
    """Smart recommendation engine for resume templates."""

    @staticmethod
    def recommend_for_user(profile: dict) -> list:
        """Get template recommendations based on user profile."""
        role = profile.get("current_designation", "")
        industry = profile.get("industry", "")

        return recommend_templates(role=role, industry=industry, count=5)

    @staticmethod
    def get_all_available() -> list:
        """Get all available templates."""
        return get_all_templates()

    @staticmethod
    def get_upsc_format_recommendation(profile: dict) -> dict:
        """Get UPSC format recommendation."""
        category = profile.get("category", "general")
        level = profile.get("level", "")
        experience_years = profile.get("experience_years", 0)
        has_publications = profile.get("has_publications", False)
        has_patents = profile.get("has_patents", False)

        return recommend_upsc_format(
            category=category,
            level=level,
            experience_years=experience_years,
            has_publications=has_publications,
            has_patents=has_patents
        )


class FeaturesV15:
    """v1.5.0 Features Collection."""

    # Feature 1: Fresh Start (already in v1.4.0)
    FRESH_START_ENABLED = True

    # Feature 2: UPSC Format (already in v1.4.0)
    UPSC_FORMAT_ENABLED = True

    # Feature 3: Help System
    HELP_SYSTEM_ENABLED = True
    HELP_TOPICS_COUNT = len(HelpButtonIntegration.HELP_TOPICS)

    # Feature 4: Resume Templates Library
    TEMPLATES_LIBRARY_ENABLED = True
    TEMPLATES_COUNT = len(get_all_templates())

    # Feature 5: Template Recommendations
    TEMPLATE_RECOMMENDATIONS_ENABLED = True

    @staticmethod
    def get_feature_status() -> dict:
        """Get status of all v1.5.0 features."""
        return {
            "fresh_start": FeaturesV15.FRESH_START_ENABLED,
            "upsc_format": FeaturesV15.UPSC_FORMAT_ENABLED,
            "help_system": FeaturesV15.HELP_SYSTEM_ENABLED,
            "templates_library": FeaturesV15.TEMPLATES_LIBRARY_ENABLED,
            "template_recommendations": FeaturesV15.TEMPLATE_RECOMMENDATIONS_ENABLED,
            "help_topics": FeaturesV15.HELP_TOPICS_COUNT,
            "templates": FeaturesV15.TEMPLATES_COUNT,
        }
