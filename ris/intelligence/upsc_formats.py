"""UPSC deputation format support (DoPT OM 02.07.2015 compliant)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class UPSCRecruitmentMode(Enum):
    """UPSC recruitment modes."""

    DEPUTATION = "deputation"
    LATERAL_ENTRY = "lateral_entry"
    RESEARCH_SCIENTIST = "research_scientist"


@dataclass
class UPSCFormatAdvice:
    """Recommendation for UPSC format."""

    mode: UPSCRecruitmentMode
    template: str
    required_sections: list[str]
    checklist: list[str]
    notes: str


# UPSC Bio-data Proforma Sections (DoPT OM 02.07.2015)
UPSC_SECTIONS = {
    "particulars": {
        "title": "Part A: Official Particulars",
        "fields": [
            "Name", "Date of Birth", "Gender", "Category",
            "Present Grade/Designation", "Cadre", "Office Address",
        ],
    },
    "experience": {
        "title": "Part B: Experience Record",
        "fields": [
            "Positions Held", "Period", "Location", "Key Responsibilities",
            "Specialization/Expertise", "Publications/Patents",
        ],
    },
    "apar": {
        "title": "Part C: APAR Record (Last 5 years)",
        "fields": [
            "Grading Year 1", "Grading Year 2", "Grading Year 3",
            "Grading Year 4", "Grading Year 5",
        ],
    },
    "compliance": {
        "title": "Part D: Compliance & Clearances",
        "fields": [
            "Vigilance Status", "Integrity Certification",
            "CBI/ED/Court Cases", "Medical Fitness",
            "No Bar to Deputations", "SC/ST Certificate (if applicable)",
        ],
    },
    "deputation": {
        "title": "Part E: Deputation Details",
        "fields": [
            "Type of Deputation", "Duration",
            "Physical Fitness", "Willingness",
            "Family Accompanying Status",
        ],
    },
    "employer": {
        "title": "Part F: Employer's Assessment",
        "fields": [
            "Employer Certification", "Performance Comments",
            "Character Assessment", "Authorized Signatory",
        ],
    },
}

# UPSC Deputation Checklist
UPSC_DEPUTATION_CHECKLIST = [
    "✓ All APARs for last 5 years completed",
    "✓ No vigilance case pending",
    "✓ Integrity certificate obtained",
    "✓ Medical fitness certificate",
    "✓ Character assessment from employer",
    "✓ No CBI/ED/Court cases",
    "✓ SC/ST certificate (if applicable)",
    "✓ Deputation willingness certified",
    "✓ All annexures attached",
]

# UPSC Lateral Entry Checklist
UPSC_LATERAL_ENTRY_CHECKLIST = [
    "✓ Relevant specialized experience (minimum 10+ years)",
    "✓ Publications/Patents (if applicable)",
    "✓ Recognized expertise in domain",
    "✓ Educational qualifications verified",
    "✓ No vigilance/integrity issues",
    "✓ Medical fitness certificate",
    "✓ Character assessment",
]

# UPSC Research Scientist Checklist
UPSC_RESEARCH_SCIENTIST_CHECKLIST = [
    "✓ Research publications (minimum requirement)",
    "✓ Patents/IPR (if applicable)",
    "✓ Citations in peer-reviewed journals",
    "✓ Research supervision experience",
    "✓ PhD/Postdoc credentials",
    "✓ Medical fitness",
    "✓ No plagiarism cases",
]


def get_experience_certificate_forms() -> dict[str, dict]:
    """Get UPSC experience certificate forms (Form-I, II, III)."""
    return {
        "form_i": {
            "name": "Form-I: Standard Experience Certificate",
            "use_for": "General government experience",
            "sections": [
                "Designation and period held",
                "Classification of post",
                "Duties and responsibilities",
                "Sanctioned strength of office",
                "Authority certifying",
            ],
        },
        "form_ii": {
            "name": "Form-II: Experience in Research",
            "use_for": "Research and scientific positions",
            "sections": [
                "Research area and specialization",
                "Publications and research output",
                "Patents and IPR",
                "Supervision of research scholars",
                "Professional recognition",
            ],
        },
        "form_iii": {
            "name": "Form-III: Experience in Administration",
            "use_for": "Administrative and managerial positions",
            "sections": [
                "Administrative positions held",
                "Budget handled and financial responsibility",
                "Staff supervised and management",
                "Policy formulation contribution",
                "Organization impact and achievements",
            ],
        },
    }


def validate_upsc_data(profile: dict) -> tuple[bool, list[str]]:
    """Validate profile data for UPSC compliance."""
    errors = []

    # Check required fields
    required_fields = [
        "name", "date_of_birth", "category", "current_designation",
    ]
    for field in required_fields:
        if not profile.get(field):
            errors.append(f"Missing required field: {field}")

    # Check experience
    experience = profile.get("experience", [])
    if len(experience) == 0:
        errors.append("At least one position must be recorded")

    # Check APARs (last 5 years)
    apars = profile.get("apars", [])
    if len(apars) < 5:
        errors.append(f"APARs incomplete: {len(apars)}/5 years")

    # Check compliance clearances
    compliance = profile.get("compliance", {})
    if not compliance.get("vigilance_clear"):
        errors.append("Vigilance clearance required")
    if not compliance.get("integrity_certified"):
        errors.append("Integrity certification required")

    return len(errors) == 0, errors


def recommend_upsc_format(
    category: str = "",
    level: str = "",
    experience_years: int = 0,
    has_publications: bool = False,
    has_patents: bool = False,
) -> UPSCFormatAdvice:
    """Get UPSC format recommendation based on profile."""

    # Deputation recommendation
    if level in ["scientist_f", "scientist_g", "group_a"]:
        return UPSCFormatAdvice(
            mode=UPSCRecruitmentMode.DEPUTATION,
            template="upsc_deputation",
            required_sections=list(UPSC_SECTIONS.keys()),
            checklist=UPSC_DEPUTATION_CHECKLIST,
            notes="Deputation format for senior government scientists and officers. DoPT OM 02.07.2015 compliant.",
        )

    # Lateral entry recommendation
    if experience_years >= 10 and (has_publications or has_patents):
        return UPSCFormatAdvice(
            mode=UPSCRecruitmentMode.LATERAL_ENTRY,
            template="upsc_lateral_entry",
            required_sections=["particulars", "experience", "compliance", "employer"],
            checklist=UPSC_LATERAL_ENTRY_CHECKLIST,
            notes="Lateral entry for specialized positions. Requires significant domain expertise.",
        )

    # Research scientist recommendation
    if has_publications or has_patents:
        return UPSCFormatAdvice(
            mode=UPSCRecruitmentMode.RESEARCH_SCIENTIST,
            template="upsc_research_scientist",
            required_sections=["particulars", "experience", "compliance", "employer"],
            checklist=UPSC_RESEARCH_SCIENTIST_CHECKLIST,
            notes="Research scientist position. Requires publication and research record.",
        )

    # Default to deputation
    return UPSCFormatAdvice(
        mode=UPSCRecruitmentMode.DEPUTATION,
        template="upsc_deputation",
        required_sections=list(UPSC_SECTIONS.keys()),
        checklist=UPSC_DEPUTATION_CHECKLIST,
        notes="Standard UPSC deputation format.",
    )
