"""Resume modes: content strategies (what to include, in what order, how much).

Modes are orthogonal to templates (visual layout). A mode sets the default
section order, length budgets and summary preference. Ordering is then
adapted to the career target or vacancy (see ``ordering.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ris.domain.enums import ResumeLength, SummaryFocus


@dataclass(frozen=True)
class Budget:
    positions: int | None
    bullets_primary: int | None
    bullets_other: int | None
    assignments_bullets: int | None
    projects: int | None
    project_bullets: int | None
    publications: int | None
    manuscripts: int | None
    activities: int | None
    skill_groups: int | None
    skills_per_group: int | None
    competencies: int | None
    training: int | None
    awards: int | None

    @staticmethod
    def unlimited() -> Budget:
        return Budget(*([None] * 14))


BUDGETS: dict[ResumeLength, Budget] = {
    ResumeLength.ONE_PAGE: Budget(
        positions=3, bullets_primary=4, bullets_other=2, assignments_bullets=1, projects=2, project_bullets=2,
        publications=3, manuscripts=1, activities=3, skill_groups=4, skills_per_group=7, competencies=9,
        training=2, awards=2,
    ),
    ResumeLength.TWO_PAGES: Budget(
        positions=6, bullets_primary=6, bullets_other=3, assignments_bullets=3, projects=4, project_bullets=3,
        publications=6, manuscripts=4, activities=6, skill_groups=7, skills_per_group=10, competencies=12,
        training=5, awards=5,
    ),
    ResumeLength.FULL: Budget.unlimited(),
}


SECTION_TITLES: dict[str, str] = {
    "summary": "Professional Summary",
    "competencies": "Core Competencies",
    "experience": "Professional Experience",
    "projects": "Key Projects",
    "education": "Education",
    "publications": "Publications",
    "manuscripts": "Manuscripts Under Review / In Preparation",
    "skills": "Technical Skills",
    "leadership": "Leadership & Responsibilities",
    "awards": "Awards & Honours",
    "patents": "Patents",
    "presentations": "Talks & Presentations",
    "memberships": "Professional Memberships",
    "training": "Certifications & Training",
    "training_programmes": "Training Programmes",
    "courses": "Professional Courses",
    "certifications": "Certifications & Licences",
    "workshops": "Workshops, Seminars & Conferences Attended",
    "other_qualifications": "Other Qualifications",
    "languages": "Languages",
    "other_activities": "Other Activities",
    "particulars": "Particulars",
    "requirements_matrix": "Qualifications and Experience Against the Requirements of the Post",
    "declaration": "Declaration",
    "expertise": "Areas of Expertise",
    "career_timeline": "Career Timeline",
    "research_overview": "Research at a Glance",
    "grants": "Research Grants & Funding",
    "service": "Professional Service",
    "references": "Referees",
    "proforma_particulars": "Personal and Service Particulars (items 1–3)",
    "proforma_requirements": "5. Whether Educational and Other Qualifications Required for the Post Are Satisfied",
    "proforma_statement": "6. Statement on Essential Qualifications and Work Experience",
    "proforma_service": "Present Employment and Pay (items 8–15)",
    "proforma_additional": "16 A. Additional Information Relevant to the Post",
    "proforma_basis": "Basis of Application (items 17–18)",
    "employer_certificate": "Certification by the Employer / Cadre Controlling Authority",
}

#: Sections that only make sense in the deputation proforma.
PROFORMA_SECTIONS = ("proforma_particulars", "proforma_requirements", "proforma_statement", "proforma_service",
                     "proforma_additional", "proforma_basis", "employer_certificate")


@dataclass(frozen=True)
class ResumeMode:
    id: str
    name: str
    description: str
    section_order: tuple[str, ...]
    default_template: str
    default_length: ResumeLength
    summary_focus: tuple[SummaryFocus, ...] = ()
    title_line: str = ""
    government: bool = False
    publication_scope: str = "relevant"
    show_tools: bool = False
    title_overrides: dict[str, str] = field(default_factory=dict)
    contact_fields: tuple[str, ...] = ("email", "phone", "location", "linkedin", "website")
    #: Follows the DoPT bio-data proforma item by item.
    proforma: bool = False
    #: The line under the name names the post applied for (from the linked vacancy).
    headline_from_vacancy: bool = False

    def title_for(self, key: str) -> str:
        return self.title_overrides.get(key) or SECTION_TITLES.get(key, key.replace("_", " ").title())


MODES: dict[str, ResumeMode] = {
    m.id: m
    for m in [
        ResumeMode(
            id="general_professional",
            name="Professional resume",
            description="Balanced two-page resume for most technical and scientific roles.",
            section_order=("summary", "competencies", "experience", "projects", "education", "publications",
                           "manuscripts", "leadership", "awards", "training", "skills", "languages"),
            default_template="engineering_professional",
            default_length=ResumeLength.TWO_PAGES,
            summary_focus=(SummaryFocus.GENERAL, SummaryFocus.TECHNICAL_MANAGEMENT),
        ),
        ResumeMode(
            id="defence_technical",
            name="Defence & Intelligence technical resume",
            description="Emphasises verified engineering evidence for defence, aviation and technical "
                        "intelligence roles; uses the selected career target's emphasis.",
            section_order=("summary", "competencies", "experience", "projects", "education", "publications",
                           "manuscripts", "leadership", "training", "awards", "patents", "skills", "languages"),
            default_template="defence_technical",
            default_length=ResumeLength.TWO_PAGES,
            summary_focus=(SummaryFocus.DEFENCE_TECHNOLOGY, SummaryFocus.ELECTRONICS_AVIONICS, SummaryFocus.GENERAL),
            show_tools=True,
            title_overrides={"competencies": "Technical Domains", "projects": "Technical Projects"},
            contact_fields=("email", "phone", "location", "linkedin"),
        ),
        ResumeMode(
            id="scientific_research",
            name="Scientific research CV",
            description="Research-first CV: education, publications and research projects lead.",
            section_order=("summary", "education", "publications", "manuscripts", "experience", "projects",
                           "grants", "presentations", "awards", "service", "memberships", "training", "skills",
                           "languages"),
            default_template="scientific_research",
            default_length=ResumeLength.TWO_PAGES,
            summary_focus=(SummaryFocus.AIML_RESEARCH, SummaryFocus.SCIENTIFIC_LEADERSHIP, SummaryFocus.ACADEMIC),
            publication_scope="all",
            title_overrides={"summary": "Research Profile", "projects": "Research Projects"},
            contact_fields=("email", "phone", "location", "orcid", "google_scholar", "website"),
        ),
        ResumeMode(
            id="academic_cv",
            name="Academic extended CV",
            description="Complete academic CV with every publication, talk and service record; no page limit.",
            section_order=("summary", "education", "experience", "publications", "manuscripts", "projects",
                           "grants", "presentations", "awards", "service", "memberships", "leadership",
                           "certifications", "courses", "workshops", "training_programmes", "skills",
                           "other_activities", "languages", "references"),
            default_template="academic_extended",
            default_length=ResumeLength.FULL,
            summary_focus=(SummaryFocus.ACADEMIC, SummaryFocus.AIML_RESEARCH),
            publication_scope="all",
            title_overrides={"summary": "Research Interests", "experience": "Appointments",
                             "leadership": "Service & Leadership"},
            contact_fields=("email", "phone", "location", "orcid", "google_scholar", "researchgate", "website"),
        ),
        ResumeMode(
            id="government_biodata",
            name="Government bio-data (deputation style)",
            description="Formal bio-data in the style commonly used for Government of India deputation and "
                        "recruitment. Always follow the exact proforma prescribed in the vacancy circular.",
            section_order=("particulars", "education", "experience", "requirements_matrix", "publications",
                           "manuscripts", "projects", "training_programmes", "courses", "certifications",
                           "workshops", "other_qualifications", "awards", "leadership", "declaration"),
            default_template="government_cv",
            default_length=ResumeLength.FULL,
            summary_focus=(SummaryFocus.GOVERNMENT_DEPUTATION, SummaryFocus.SCIENTIFIC_LEADERSHIP),
            title_line="BIO-DATA / CURRICULUM VITAE",
            government=True,
            publication_scope="all",
            title_overrides={"education": "Educational Qualifications",
                             "experience": "Details of Employment (in chronological order)",
                             "projects": "Major Projects and Technical Contributions",
                             "leadership": "Additional Responsibilities and Committees",
                             "training": "Training Programmes and Certifications",
                             "particulars": "Personal and Official Particulars"},
            contact_fields=("email", "phone"),
        ),
        ResumeMode(
            id="ats_plain",
            name="ATS-optimised resume",
            description="Plain, keyword-aligned resume for online application portals and applicant tracking systems.",
            section_order=("summary", "skills", "experience", "projects", "education", "publications",
                           "manuscripts", "training", "awards", "languages"),
            default_template="ats_minimal",
            default_length=ResumeLength.TWO_PAGES,
            summary_focus=(SummaryFocus.GENERAL,),
            title_overrides={"skills": "Skills"},
            contact_fields=("email", "phone", "location", "linkedin"),
        ),
        ResumeMode(
            id="executive_summary",
            name="One-page executive profile",
            description="One-page leadership profile: summary, domains, recent roles and leadership.",
            section_order=("summary", "competencies", "experience", "leadership", "education", "awards"),
            default_template="executive_technical",
            default_length=ResumeLength.ONE_PAGE,
            summary_focus=(SummaryFocus.SCIENTIFIC_LEADERSHIP, SummaryFocus.TECHNICAL_MANAGEMENT),
            title_overrides={"competencies": "Areas of Expertise", "leadership": "Leadership"},
            contact_fields=("email", "phone", "location", "linkedin"),
        ),
        ResumeMode(
            id="technical_specialist",
            name="Technical specialist resume",
            description="Skills- and project-first resume for AI/ML, embedded or drone engineering roles.",
            section_order=("summary", "skills", "projects", "experience", "publications", "manuscripts",
                           "education", "training", "awards"),
            default_template="aiml_specialist",
            default_length=ResumeLength.TWO_PAGES,
            summary_focus=(SummaryFocus.AIML_RESEARCH, SummaryFocus.EMBEDDED_SYSTEMS, SummaryFocus.DRONE_ENGINEERING),
            show_tools=True,
            contact_fields=("email", "phone", "location", "github", "linkedin", "website"),
        ),
    ]
}


MODES.update({
    m.id: m
    for m in [
        ResumeMode(
            id="graphical_profile",
            name="Graphical career profile",
            description="Designed two-page profile with a career timeline chart, competency bars, areas of "
                        "expertise and project highlights. Ideal for printed applications and interviews; use the "
                        "ATS mode for online portals.",
            section_order=("summary", "expertise", "career_timeline", "experience", "projects", "education",
                           "publications", "manuscripts", "leadership", "awards", "patents", "training", "skills",
                           "languages"),
            default_template="graphical_profile",
            default_length=ResumeLength.TWO_PAGES,
            summary_focus=(SummaryFocus.DEFENCE_TECHNOLOGY, SummaryFocus.SCIENTIFIC_LEADERSHIP, SummaryFocus.GENERAL),
            title_overrides={"projects": "Projects Executed", "skills": "Core Competency"},
            contact_fields=("email", "phone", "location", "linkedin"),
        ),
        ResumeMode(
            id="research_portfolio",
            name="Research portfolio",
            description="Research-results CV: verified metrics, publications by year, every paper with its exact "
                        "status, research projects as cards, grants, patents, talks and professional service.",
            section_order=("summary", "research_overview", "publications", "manuscripts", "projects", "grants",
                           "patents", "presentations", "experience", "education", "service", "awards",
                           "memberships", "certifications", "workshops", "skills", "references"),
            default_template="research_showcase",
            default_length=ResumeLength.FULL,
            summary_focus=(SummaryFocus.AIML_RESEARCH, SummaryFocus.ACADEMIC, SummaryFocus.SCIENTIFIC_LEADERSHIP),
            publication_scope="all",
            title_overrides={"summary": "Research Profile", "projects": "Research Projects",
                             "publications": "Peer-reviewed Publications", "experience": "Appointments"},
            contact_fields=("email", "phone", "location", "orcid", "google_scholar", "researchgate", "website"),
        ),
        ResumeMode(
            id="project_portfolio",
            name="Project portfolio",
            description="Projects first, each shown as a card with challenge, approach, outcome and technologies, "
                        "followed by a career timeline and supporting experience.",
            section_order=("summary", "expertise", "projects", "career_timeline", "experience", "skills",
                           "education", "publications", "patents", "awards", "references"),
            default_template="infographic_timeline",
            default_length=ResumeLength.FULL,
            summary_focus=(SummaryFocus.TECHNICAL_MANAGEMENT, SummaryFocus.DRONE_ENGINEERING, SummaryFocus.GENERAL),
            show_tools=True,
            title_overrides={"projects": "Project Portfolio", "skills": "Skills"},
            contact_fields=("email", "phone", "location", "github", "linkedin", "portfolio"),
        ),
    ]
})


MODES.update({
    m.id: m
    for m in [
        ResumeMode(
            id="deputation_proforma",
            name="Deputation application — DoPT bio-data proforma",
            description="Application on deputation, absorption or short-term contract in the Bio-data / CV proforma "
                        "of DoPT OM No. AB.14017/28/2014-Estt.(RR) dated 02.07.2015 (items 1–18, declaration and "
                        "the employer's certificate), the format Central Government deputation circulars commonly "
                        "prescribe (NTRO's 2026 circulars, for example). Link the vacancy to fill item 5. If the "
                        "circular encloses its own form, follow that form.",
            section_order=("proforma_particulars", "education", "proforma_requirements", "proforma_statement",
                           "experience", "proforma_service", "proforma_additional", "training", "publications",
                           "manuscripts", "projects", "awards", "memberships", "patents", "leadership",
                           "presentations", "proforma_basis", "declaration", "employer_certificate"),
            default_template="dopt_proforma",
            default_length=ResumeLength.FULL,
            summary_focus=(SummaryFocus.GOVERNMENT_DEPUTATION, SummaryFocus.SCIENTIFIC_LEADERSHIP),
            title_line="BIO-DATA / CURRICULUM VITAE PROFORMA",
            government=True,
            publication_scope="all",
            proforma=True,
            headline_from_vacancy=True,
            title_overrides={
                "education": "4. Educational Qualifications",
                "experience": "7. Details of Employment, in Chronological Order",
                "training": "16 A. Professional Training, Courses and Certifications",
                "publications": "16 B (i). Research Publications and Reports",
                "manuscripts": "16 B (i). Manuscripts Under Review / In Preparation",
                "projects": "16 B (i). Special Projects",
                "awards": "16 B (ii). Awards, Scholarships and Official Appreciation",
                "memberships": "16 B (iii). Affiliation with Professional Bodies, Institutions and Societies",
                "patents": "16 B (iv). Patents",
                "leadership": "16 B (vi). Other Information: Responsibilities and Committees",
                "presentations": "16 B (vi). Other Information: Talks and Presentations",
                "declaration": "Declaration by the Candidate",
            },
            contact_fields=("email", "phone"),
        ),
        ResumeMode(
            id="senior_scientist",
            name="Senior Scientist (F/G) — R&D leadership CV",
            description="Detailed CV for Scientist F/G and equivalent posts by direct recruitment (for example DRDO "
                        "RAC) or as the detailed CV sent with a deputation application: specialisation, positions, "
                        "major R&D projects, leadership, publications, patents and awards, with a justification "
                        "against the post's requirements when a vacancy is linked. Single column and ATS-readable.",
            section_order=("summary", "expertise", "competencies", "requirements_matrix", "experience", "projects",
                           "leadership", "publications", "manuscripts", "patents", "awards", "grants",
                           "presentations", "training_programmes", "certifications", "courses", "workshops",
                           "education", "memberships", "service", "languages", "references"),
            default_template="senior_scientist",
            default_length=ResumeLength.FULL,
            summary_focus=(SummaryFocus.SCIENTIFIC_LEADERSHIP, SummaryFocus.DEFENCE_TECHNOLOGY,
                           SummaryFocus.TECHNICAL_MANAGEMENT),
            publication_scope="all",
            show_tools=True,
            headline_from_vacancy=False,
            title_overrides={"summary": "Professional Profile", "expertise": "Areas of Specialisation",
                             "competencies": "Technical Domains",
                             "requirements_matrix": "Justification Against the Requirements of the Post",
                             "experience": "Positions Held",
                             "projects": "Major R&D Projects and Technical Contributions",
                             "leadership": "Leadership, Committees and Responsibilities",
                             "training_programmes": "Training Programmes Attended"},
            contact_fields=("email", "phone", "location", "linkedin", "orcid", "google_scholar"),
        ),
        ResumeMode(
            id="senior_graphical",
            name="Senior scientist graphical profile",
            description="Designed profile for interview boards, presentations and networking: career timeline, "
                        "areas of expertise, research at a glance and selected projects, with charts you can switch "
                        "off or change. Use the proforma or the Senior Scientist CV for the formal application.",
            section_order=("summary", "expertise", "career_timeline", "research_overview", "experience", "projects",
                           "leadership", "publications", "patents", "awards", "training", "education", "skills",
                           "languages"),
            default_template="senior_graphical",
            default_length=ResumeLength.TWO_PAGES,
            summary_focus=(SummaryFocus.SCIENTIFIC_LEADERSHIP, SummaryFocus.DEFENCE_TECHNOLOGY, SummaryFocus.GENERAL),
            title_overrides={"summary": "Profile", "projects": "Selected Projects", "skills": "Core Competency",
                             "leadership": "Leadership & Responsibilities"},
            contact_fields=("email", "phone", "location", "linkedin"),
        ),
    ]
})


def get_mode(mode_id: str) -> ResumeMode:
    return MODES.get(mode_id) or MODES["general_professional"]


ALL_SECTION_KEYS: tuple[str, ...] = tuple(SECTION_TITLES)
