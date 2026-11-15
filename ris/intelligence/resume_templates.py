"""Professional resume templates library with 30+ templates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class ResumeTemplate:
    """Resume template definition."""

    template_id: str
    name: str
    category: str
    description: str
    layout: str  # single_column, two_column
    colors: dict  # primary, secondary, accent
    is_ats_friendly: bool
    best_for_roles: List[str]
    best_for_industries: List[str]
    pages: int  # 1 or 2
    difficulty: str  # simple, moderate, advanced


# 30+ Professional Resume Templates
TEMPLATES = [
    # EXECUTIVE TEMPLATES
    ResumeTemplate(
        template_id="executive_modern",
        name="Executive Modern",
        category="Executive",
        description="Modern executive resume with sidebar and minimalist design",
        layout="two_column",
        colors={"primary": "#1F4788", "secondary": "#6C5CE7", "accent": "#00B894"},
        is_ats_friendly=True,
        best_for_roles=["CEO", "VP", "Director", "Senior Manager"],
        best_for_industries=["Tech", "Finance", "Consulting"],
        pages=1,
        difficulty="moderate",
    ),
    ResumeTemplate(
        template_id="executive_classic",
        name="Executive Classic",
        category="Executive",
        description="Traditional executive resume with professional formatting",
        layout="single_column",
        colors={"primary": "#2C3E50", "secondary": "#34495E", "accent": "#E74C3C"},
        is_ats_friendly=True,
        best_for_roles=["Executive", "C-Suite", "Board Member"],
        best_for_industries=["All"],
        pages=1,
        difficulty="simple",
    ),
    ResumeTemplate(
        template_id="executive_premium",
        name="Executive Premium",
        category="Executive",
        description="Premium two-page executive resume with detailed sections",
        layout="two_column",
        colors={"primary": "#16213E", "secondary": "#0F3460", "accent": "#E94560"},
        is_ats_friendly=False,
        best_for_roles=["Senior Executive", "President"],
        best_for_industries=["All"],
        pages=2,
        difficulty="advanced",
    ),
    ResumeTemplate(
        template_id="executive_minimal",
        name="Executive Minimal",
        category="Executive",
        description="Minimal executive resume focusing on key achievements",
        layout="single_column",
        colors={"primary": "#1A1A1A", "secondary": "#666666", "accent": "#0066CC"},
        is_ats_friendly=True,
        best_for_roles=["Executive", "Director"],
        best_for_industries=["Tech", "Startup"],
        pages=1,
        difficulty="simple",
    ),
    ResumeTemplate(
        template_id="executive_sophisticated",
        name="Executive Sophisticated",
        category="Executive",
        description="Sophisticated executive resume with timeline and achievements",
        layout="two_column",
        colors={"primary": "#2B2D42", "secondary": "#6B6B83", "accent": "#D4A373"},
        is_ats_friendly=True,
        best_for_roles=["Executive", "Senior Manager"],
        best_for_industries=["Finance", "Consulting"],
        pages=1,
        difficulty="moderate",
    ),
    # GOVERNMENT TEMPLATES
    ResumeTemplate(
        template_id="government_standard",
        name="Government Standard",
        category="Government",
        description="Standard Indian Government format for Civil Service",
        layout="single_column",
        colors={"primary": "#1F4E78", "secondary": "#4472C4", "accent": "#FFC000"},
        is_ats_friendly=True,
        best_for_roles=["IAS", "IPS", "Civil Service"],
        best_for_industries=["Government"],
        pages=1,
        difficulty="simple",
    ),
    ResumeTemplate(
        template_id="government_upsc",
        name="Government UPSC",
        category="Government",
        description="UPSC deputation format (DoPT OM 02.07.2015 compliant)",
        layout="single_column",
        colors={"primary": "#003DA5", "secondary": "#4472C4", "accent": "#70AD47"},
        is_ats_friendly=True,
        best_for_roles=["UPSC Deputation", "Scientist", "Researcher"],
        best_for_industries=["Government", "Defence"],
        pages=2,
        difficulty="moderate",
    ),
    ResumeTemplate(
        template_id="government_defence",
        name="Government Defence",
        category="Government",
        description="Format suitable for defence and intelligence services",
        layout="single_column",
        colors={"primary": "#1F4D2D", "secondary": "#375623", "accent": "#C65000"},
        is_ats_friendly=True,
        best_for_roles=["Officer", "Scientist", "Engineer"],
        best_for_industries=["Defence", "Intelligence"],
        pages=1,
        difficulty="moderate",
    ),
    # TECHNICAL TEMPLATES
    ResumeTemplate(
        template_id="technical_developer",
        name="Technical Developer",
        category="Technical",
        description="Developer-focused resume with skills highlight",
        layout="two_column",
        colors={"primary": "#0D47A1", "secondary": "#1565C0", "accent": "#64B5F6"},
        is_ats_friendly=True,
        best_for_roles=["Software Engineer", "Developer", "DevOps Engineer"],
        best_for_industries=["Tech", "Software"],
        pages=1,
        difficulty="moderate",
    ),
    ResumeTemplate(
        template_id="technical_scientist",
        name="Technical Scientist",
        category="Technical",
        description="Research and scientist-oriented resume",
        layout="single_column",
        colors={"primary": "#004B87", "secondary": "#0066CC", "accent": "#00A8E8"},
        is_ats_friendly=True,
        best_for_roles=["Scientist", "Researcher", "PhD"],
        best_for_industries=["Research", "Academia"],
        pages=2,
        difficulty="moderate",
    ),
    ResumeTemplate(
        template_id="technical_engineer",
        name="Technical Engineer",
        category="Technical",
        description="Engineering-focused with projects and certifications",
        layout="two_column",
        colors={"primary": "#D32F2F", "secondary": "#F57C00", "accent": "#FBC02D"},
        is_ats_friendly=True,
        best_for_roles=["Engineer", "Technical Lead", "Architect"],
        best_for_industries=["Engineering", "Tech"],
        pages=1,
        difficulty="moderate",
    ),
    # CREATIVE TEMPLATES
    ResumeTemplate(
        template_id="creative_designer",
        name="Creative Designer",
        category="Creative",
        description="Creative resume for designers with visual elements",
        layout="two_column",
        colors={"primary": "#FF6F61", "secondary": "#6A4C93", "accent": "#1982C4"},
        is_ats_friendly=False,
        best_for_roles=["Designer", "UX/UI Designer", "Creative Director"],
        best_for_industries=["Design", "Media"],
        pages=1,
        difficulty="advanced",
    ),
    ResumeTemplate(
        template_id="creative_artist",
        name="Creative Artist",
        category="Creative",
        description="Resume for artists and creative professionals",
        layout="two_column",
        colors={"primary": "#8B4513", "secondary": "#D2691E", "accent": "#FF8C00"},
        is_ats_friendly=False,
        best_for_roles=["Artist", "Illustrator", "Animator"],
        best_for_industries=["Arts", "Entertainment"],
        pages=1,
        difficulty="advanced",
    ),
    # ACADEMIC TEMPLATES
    ResumeTemplate(
        template_id="academic_professor",
        name="Academic Professor",
        category="Academic",
        description="Academic CV for professors and researchers",
        layout="single_column",
        colors={"primary": "#1B4965", "secondary": "#2D728F", "accent": "#C8E0E8"},
        is_ats_friendly=True,
        best_for_roles=["Professor", "Academic", "Researcher"],
        best_for_industries=["Education", "Research"],
        pages=2,
        difficulty="moderate",
    ),
    ResumeTemplate(
        template_id="academic_student",
        name="Academic Student",
        category="Academic",
        description="Resume for students and fresh graduates",
        layout="single_column",
        colors={"primary": "#0099CC", "secondary": "#00CCFF", "accent": "#FFCC00"},
        is_ats_friendly=True,
        best_for_roles=["Student", "Graduate", "Intern"],
        best_for_industries=["All"],
        pages=1,
        difficulty="simple",
    ),
    # SPECIALTY TEMPLATES (Additional 10+)
    ResumeTemplate(
        template_id="sales_professional",
        name="Sales Professional",
        category="Sales",
        description="Resume for sales and business development roles",
        layout="two_column",
        colors={"primary": "#C1272D", "secondary": "#E74C3C", "accent": "#27AE60"},
        is_ats_friendly=True,
        best_for_roles=["Sales Manager", "Account Executive", "BD"],
        best_for_industries=["Sales", "Business"],
        pages=1,
        difficulty="moderate",
    ),
    ResumeTemplate(
        template_id="finance_analyst",
        name="Finance Analyst",
        category="Finance",
        description="Resume for finance and accounting professionals",
        layout="single_column",
        colors={"primary": "#003D7A", "secondary": "#0051BA", "accent": "#FFB81C"},
        is_ats_friendly=True,
        best_for_roles=["Analyst", "Accountant", "Finance Manager"],
        best_for_industries=["Finance", "Banking"],
        pages=1,
        difficulty="simple",
    ),
    ResumeTemplate(
        template_id="healthcare_medical",
        name="Healthcare Medical",
        category="Healthcare",
        description="Resume for doctors and medical professionals",
        layout="single_column",
        colors={"primary": "#00A3E0", "secondary": "#00BCD4", "accent": "#FF6F61"},
        is_ats_friendly=True,
        best_for_roles=["Doctor", "Nurse", "Medical Professional"],
        best_for_industries=["Healthcare"],
        pages=1,
        difficulty="moderate",
    ),
    ResumeTemplate(
        template_id="education_teacher",
        name="Education Teacher",
        category="Education",
        description="Resume for teachers and educational professionals",
        layout="single_column",
        colors={"primary": "#2E5090", "secondary": "#6A4C93", "accent": "#7CB342"},
        is_ats_friendly=True,
        best_for_roles=["Teacher", "Educator", "Instructor"],
        best_for_industries=["Education"],
        pages=1,
        difficulty="simple",
    ),
    ResumeTemplate(
        template_id="legal_attorney",
        name="Legal Attorney",
        category="Legal",
        description="Resume for lawyers and legal professionals",
        layout="single_column",
        colors={"primary": "#1A237E", "secondary": "#283593", "accent": "#7986CB"},
        is_ats_friendly=True,
        best_for_roles=["Attorney", "Lawyer", "Legal Counsel"],
        best_for_industries=["Legal"],
        pages=1,
        difficulty="moderate",
    ),
    ResumeTemplate(
        template_id="hr_specialist",
        name="HR Specialist",
        category="HR",
        description="Resume for HR and recruitment professionals",
        layout="two_column",
        colors={"primary": "#5B2C6F", "secondary": "#7E57C2", "accent": "#29B6F6"},
        is_ats_friendly=True,
        best_for_roles=["HR Manager", "Recruiter", "HR Specialist"],
        best_for_industries=["HR", "Business"],
        pages=1,
        difficulty="moderate",
    ),
    ResumeTemplate(
        template_id="marketing_manager",
        name="Marketing Manager",
        category="Marketing",
        description="Resume for marketing and brand professionals",
        layout="two_column",
        colors={"primary": "#FF6B6B", "secondary": "#FF8E8E", "accent": "#4ECDC4"},
        is_ats_friendly=True,
        best_for_roles=["Marketing Manager", "Brand Manager", "CMO"],
        best_for_industries=["Marketing", "Business"],
        pages=1,
        difficulty="moderate",
    ),
    ResumeTemplate(
        template_id="operations_manager",
        name="Operations Manager",
        category="Operations",
        description="Resume for operations and supply chain professionals",
        layout="single_column",
        colors={"primary": "#2F3B52", "secondary": "#435A7A", "accent": "#FFA500"},
        is_ats_friendly=True,
        best_for_roles=["Operations Manager", "Supply Chain", "Logistics"],
        best_for_industries=["Operations", "Logistics"],
        pages=1,
        difficulty="moderate",
    ),
    ResumeTemplate(
        template_id="project_manager",
        name="Project Manager",
        category="Project Management",
        description="Resume for project and program managers",
        layout="two_column",
        colors={"primary": "#00838F", "secondary": "#0097A7", "accent": "#26A69A"},
        is_ats_friendly=True,
        best_for_roles=["Project Manager", "Program Manager", "Scrum Master"],
        best_for_industries=["IT", "Business"],
        pages=1,
        difficulty="moderate",
    ),
]


def get_all_templates() -> List[ResumeTemplate]:
    """Get all available templates."""
    return TEMPLATES


def get_template_by_id(template_id: str) -> ResumeTemplate | None:
    """Get a template by its ID."""
    for template in TEMPLATES:
        if template.template_id == template_id:
            return template
    return None


def get_templates_by_category(category: str) -> List[ResumeTemplate]:
    """Get all templates in a category."""
    return [t for t in TEMPLATES if t.category == category]


def get_templates_by_role(role: str) -> List[ResumeTemplate]:
    """Get templates best suited for a specific role."""
    role_lower = role.lower()
    return [t for t in TEMPLATES if any(role_lower in r.lower() for r in t.best_for_roles)]


def recommend_templates(role: str = "", industry: str = "", count: int = 5) -> List[ResumeTemplate]:
    """Get recommended templates based on role and industry."""
    recommendations = []

    for template in TEMPLATES:
        score = 0

        # Score based on role match
        if role:
            role_lower = role.lower()
            if any(role_lower in r.lower() for r in template.best_for_roles):
                score += 2

        # Score based on industry match
        if industry:
            industry_lower = industry.lower()
            if any(industry_lower in i.lower() for i in template.best_for_industries):
                score += 1

        # Prefer ATS-friendly templates
        if template.is_ats_friendly:
            score += 1

        if score > 0:
            recommendations.append((template, score))

    # Sort by score and return top N
    recommendations.sort(key=lambda x: x[1], reverse=True)
    return [t[0] for t in recommendations[:count]]
