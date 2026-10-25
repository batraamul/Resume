"""Enumerations used across the domain, with human-readable labels.

Machine values are stable identifiers stored in the database and in JSON
exports. Never rename a value; add a new one and migrate instead.
"""

from __future__ import annotations

from enum import StrEnum


class Verification(StrEnum):
    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"
    EVIDENCED = "evidenced"


class Confidentiality(StrEnum):
    PUBLIC = "public"
    APPROVED = "approved"
    REVIEW = "review"
    CONFIDENTIAL = "confidential"


class Origin(StrEnum):
    MANUAL = "manual"
    IMPORTED = "imported"
    PRELOADED = "preloaded"
    SAMPLE = "sample"
    GENERATED = "generated"
    SYNCED = "synced"


class RecordKind(StrEnum):
    PERSONAL = "personal"
    SUMMARY = "summary"
    POSITION = "position"
    ASSIGNMENT = "assignment"
    BULLET = "bullet"
    EDUCATION = "education"
    PUBLICATION = "publication"
    PROJECT = "project"
    SKILL = "skill"
    ACTIVITY = "activity"
    CUSTOM_SECTION = "custom_section"
    CUSTOM_ENTRY = "custom_entry"
    CAREER_TARGET = "career_target"
    VACANCY = "vacancy"
    VARIANT = "variant"
    CLAIM = "claim"
    APPLICATION = "application"
    COVER_LETTER = "cover_letter"
    EXPERTISE = "expertise"
    REFERENCE = "reference"
    TRAINING = "training"
    INTERVIEW_STORY = "interview_story"
    INTERVIEW_ANSWER = "interview_answer"
    QUESTIONNAIRE = "questionnaire"


#: Kinds that hold professional facts (subject to verification and disclosure rules).
FACT_KINDS: frozenset[RecordKind] = frozenset(
    {
        RecordKind.PERSONAL,
        RecordKind.SUMMARY,
        RecordKind.POSITION,
        RecordKind.ASSIGNMENT,
        RecordKind.BULLET,
        RecordKind.EDUCATION,
        RecordKind.PUBLICATION,
        RecordKind.PROJECT,
        RecordKind.SKILL,
        RecordKind.ACTIVITY,
        RecordKind.CUSTOM_ENTRY,
        RecordKind.EXPERTISE,
        RecordKind.REFERENCE,
        RecordKind.TRAINING,
    }
)


class EmploymentType(StrEnum):
    PERMANENT = "permanent"
    TEMPORARY = "temporary"
    CONTRACT = "contract"
    DEPUTATION = "deputation"
    AD_HOC = "ad_hoc"
    VISITING = "visiting"
    INTERNSHIP = "internship"
    OTHER = "other"


class Sector(StrEnum):
    CENTRAL_GOVERNMENT = "central_government"
    STATE_GOVERNMENT = "state_government"
    DEFENCE = "defence"
    PSU = "psu"
    AUTONOMOUS = "autonomous"
    ACADEMIC = "academic"
    PRIVATE = "private"
    OTHER = "other"


class AssignmentType(StrEnum):
    ADDITIONAL_CHARGE = "additional_charge"
    CONCURRENT = "concurrent"
    IN_CHARGE = "in_charge"
    NODAL_OFFICER = "nodal_officer"
    COMMITTEE_ROLE = "committee_role"
    OTHER = "other"


class BulletType(StrEnum):
    ACHIEVEMENT = "achievement"
    RESPONSIBILITY = "responsibility"
    DELIVERABLE = "deliverable"
    OUTCOME = "outcome"
    ACTIVITY = "activity"


class Involvement(StrEnum):
    LEADING = "leading"
    COORDINATING = "coordinating"
    INDIVIDUAL = "individual"
    PARTICIPATING = "participating"
    ADVISING = "advising"
    SUPPORTING = "supporting"


class QualificationType(StrEnum):
    DEGREE = "degree"
    DIPLOMA = "diploma"
    CERTIFICATION = "certification"
    TRAINING = "training"
    COURSE = "course"
    EXAMINATION = "examination"


class EducationLevel(StrEnum):
    DOCTORATE = "doctorate"
    MASTERS = "masters"
    BACHELORS = "bachelors"
    DIPLOMA = "diploma"
    HIGHER_SECONDARY = "higher_secondary"
    SECONDARY = "secondary"
    CERTIFICATE = "certificate"
    OTHER = "other"


class EducationStatus(StrEnum):
    COMPLETED = "completed"
    ONGOING = "ongoing"
    PLANNED = "planned"


class PublicationType(StrEnum):
    JOURNAL = "journal"
    CONFERENCE = "conference"
    PREPRINT = "preprint"
    THESIS = "thesis"
    BOOK_CHAPTER = "book_chapter"
    BOOK = "book"
    TECHNICAL_REPORT = "technical_report"
    POSTER = "poster"
    OTHER = "other"


class PublicationStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


class ProjectStatus(StrEnum):
    CONCEPT = "concept"
    IN_PROGRESS = "in_progress"
    PROTOTYPE = "prototype"
    COMPLETED = "completed"
    OPERATIONAL = "operational"
    DISCONTINUED = "discontinued"


class SkillCategory(StrEnum):
    ELECTRONICS = "electronics"
    AVIONICS = "avionics"
    EMBEDDED = "embedded"
    INSTRUMENTATION = "instrumentation"
    IOT = "iot"
    AIML = "aiml"
    COMPUTER_VISION = "computer_vision"
    EDGE_AI = "edge_ai"
    GPU_COMPUTING = "gpu_computing"
    MODEL_OPTIMISATION = "model_optimisation"
    DRONES = "drones"
    RADAR_SENSORS = "radar_sensors"
    SOFTWARE = "software"
    DATA = "data"
    RESEARCH = "research"
    PROJECT_MANAGEMENT = "project_management"
    LEADERSHIP = "leadership"
    PROCUREMENT_ADMIN = "procurement_admin"
    LANGUAGES = "languages"
    OTHER = "other"


class Proficiency(StrEnum):
    NOT_RATED = "not_rated"
    FAMILIAR = "familiar"
    WORKING = "working"
    PROFICIENT = "proficient"
    ADVANCED = "advanced"
    EXPERT = "expert"


class ActivityType(StrEnum):
    LEADERSHIP = "leadership"
    COMMITTEE = "committee"
    WORKSHOP_MANAGEMENT = "workshop_management"
    MENTORING = "mentoring"
    PROJECT_COORDINATION = "project_coordination"
    TECHNICAL_REVIEW = "technical_review"
    PROCUREMENT = "procurement"
    PRESENTATION = "presentation"
    AWARD = "award"
    MEMBERSHIP = "membership"
    PATENT = "patent"
    TECHNICAL_WRITING = "technical_writing"
    TRAINING_DELIVERED = "training_delivered"
    OUTREACH = "outreach"
    RESEARCH_GRANT = "research_grant"
    PEER_REVIEW = "peer_review"
    SUPERVISION = "supervision"
    CONFERENCE_ORGANISATION = "conference_organisation"
    OTHER = "other"


class TrainingType(StrEnum):
    TRAINING_PROGRAMME = "training_programme"
    MANDATORY_TRAINING = "mandatory_training"
    PROFESSIONAL_COURSE = "professional_course"
    ONLINE_COURSE = "online_course"
    CERTIFICATION = "certification"
    LICENCE = "licence"
    LANGUAGE_TEST = "language_test"
    WORKSHOP = "workshop"
    SEMINAR = "seminar"
    FACULTY_DEVELOPMENT = "faculty_development"
    OTHER_QUALIFICATION = "other_qualification"


class TrainingMode(StrEnum):
    CLASSROOM = "classroom"
    ONLINE = "online"
    BLENDED = "blended"
    ON_THE_JOB = "on_the_job"
    ABROAD = "abroad"


class TrainingStatus(StrEnum):
    COMPLETED = "completed"
    ONGOING = "ongoing"
    PLANNED = "planned"


class QuestionCategory(StrEnum):
    PERSONAL = "personal"
    MOTIVATION = "motivation"
    TECHNICAL = "technical"
    RESEARCH = "research"
    PROJECTS = "projects"
    LEADERSHIP = "leadership"
    BEHAVIOURAL = "behavioural"
    SITUATIONAL = "situational"
    GOVERNMENT = "government"
    ORGANISATION = "organisation"
    QUESTIONNAIRE = "questionnaire"
    CLOSING = "closing"


class QuestionnaireType(StrEnum):
    SSB_PIQ = "ssb_piq"
    INTERVIEW_DAF = "interview_daf"
    ORGANISATION = "organisation"
    OTHER = "other"


class SummaryFocus(StrEnum):
    GENERAL = "general"
    SCIENTIFIC_LEADERSHIP = "scientific_leadership"
    DEFENCE_TECHNOLOGY = "defence_technology"
    ELECTRONICS_AVIONICS = "electronics_avionics"
    AIML_RESEARCH = "aiml_research"
    EMBEDDED_SYSTEMS = "embedded_systems"
    DRONE_ENGINEERING = "drone_engineering"
    ACADEMIC = "academic"
    TECHNICAL_MANAGEMENT = "technical_management"
    GOVERNMENT_DEPUTATION = "government_deputation"
    CUSTOM = "custom"


class RequirementCategory(StrEnum):
    MANDATORY_QUALIFICATION = "mandatory_qualification"
    DESIRABLE_QUALIFICATION = "desirable_qualification"
    TECHNICAL = "technical"
    RESEARCH = "research"
    LEADERSHIP = "leadership"
    EXPERIENCE = "experience"
    DOCUMENTATION = "documentation"
    ELIGIBILITY = "eligibility"


class EvidenceStatus(StrEnum):
    VERIFIED = "verified"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    PARTIAL = "partial"
    NOT_FOUND = "not_found"
    NOT_APPLICABLE = "not_applicable"
    OFFICIAL_VERIFICATION = "official_verification"


class RecruitmentMode(StrEnum):
    UNKNOWN = "unknown"
    DIRECT = "direct_recruitment"
    DEPUTATION = "deputation"
    ABSORPTION = "absorption"
    CONTRACT = "contract"
    LATERAL = "lateral_entry"
    PROMOTION = "promotion"
    OTHER = "other"


class ApplicationStatus(StrEnum):
    SAVED = "saved"
    RESEARCHING = "researching"
    ELIGIBILITY_REVIEW = "eligibility_review"
    PREPARING = "preparing"
    APPLIED = "applied"
    INTERVIEW = "interview"
    AWAITING_DECISION = "awaiting_decision"
    SELECTED = "selected"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ResumeLength(StrEnum):
    ONE_PAGE = "one_page"
    TWO_PAGES = "two_pages"
    FULL = "full"


class ClaimStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


LABELS: dict[type, dict[str, str]] = {
    Verification: {
        "unconfirmed": "Awaiting confirmation",
        "confirmed": "Confirmed",
        "evidenced": "Confirmed with evidence",
    },
    Confidentiality: {
        "public": "Public",
        "approved": "Approved for professional use",
        "review": "Requires review",
        "confidential": "Confidential — exclude from external resumes",
    },
    Origin: {
        "manual": "Entered manually",
        "imported": "Imported",
        "preloaded": "Preliminary (pre-populated)",
        "sample": "Fictional sample",
        "generated": "Generated",
        "synced": "Synchronised",
    },
    RecordKind: {
        "personal": "Personal & contact details",
        "summary": "Professional summary",
        "position": "Position",
        "assignment": "Concurrent responsibility",
        "bullet": "Achievement / responsibility",
        "education": "Qualification",
        "publication": "Publication",
        "project": "Project",
        "skill": "Skill",
        "activity": "Leadership & activity",
        "custom_section": "Custom section",
        "custom_entry": "Custom entry",
        "career_target": "Career target",
        "vacancy": "Job opportunity",
        "variant": "Resume variant",
        "claim": "Claim",
        "application": "Application",
        "cover_letter": "Cover letter",
        "expertise": "Area of expertise",
        "reference": "Referee",
        "training": "Training & certification",
        "interview_story": "Interview story (STAR)",
        "interview_answer": "Interview answer",
        "questionnaire": "Personal questionnaire",
    },
    TrainingType: {
        "training_programme": "Training programme",
        "mandatory_training": "Induction / mandatory / mid-career training",
        "professional_course": "Professional course",
        "online_course": "Online course (MOOC)",
        "certification": "Certification",
        "licence": "Licence",
        "language_test": "Language proficiency test",
        "workshop": "Workshop",
        "seminar": "Seminar / conference attended",
        "faculty_development": "Faculty / staff development programme",
        "other_qualification": "Other qualification",
    },
    TrainingMode: {
        "classroom": "Classroom / in person",
        "online": "Online",
        "blended": "Blended",
        "on_the_job": "On the job",
        "abroad": "Abroad",
    },
    TrainingStatus: {"completed": "Completed", "ongoing": "Ongoing", "planned": "Planned"},
    QuestionCategory: {
        "personal": "Personal & background",
        "motivation": "Motivation & fit",
        "technical": "Technical / domain",
        "research": "Research & publications",
        "projects": "Projects",
        "leadership": "Leadership & management",
        "behavioural": "Behavioural (STAR)",
        "situational": "Situational & administrative",
        "government": "Government service & ethics",
        "organisation": "About the organisation",
        "questionnaire": "From your questionnaire (PIQ/DAF)",
        "closing": "Questions to ask the board",
    },
    QuestionnaireType: {
        "ssb_piq": "SSB Personal Information Questionnaire (PIQ)",
        "interview_daf": "Interview application form (DAF-style)",
        "organisation": "Organisation-specific questionnaire",
        "other": "Other questionnaire",
    },
    EmploymentType: {
        "permanent": "Permanent / regular",
        "temporary": "Temporary",
        "contract": "Contract",
        "deputation": "Deputation",
        "ad_hoc": "Ad hoc",
        "visiting": "Visiting",
        "internship": "Internship",
        "other": "Other",
    },
    Sector: {
        "central_government": "Central Government",
        "state_government": "State Government",
        "defence": "Defence",
        "psu": "Public Sector Undertaking",
        "autonomous": "Autonomous body",
        "academic": "Academic",
        "private": "Private sector",
        "other": "Other",
    },
    AssignmentType: {
        "additional_charge": "Additional charge",
        "concurrent": "Concurrent responsibility",
        "in_charge": "In-charge",
        "nodal_officer": "Nodal officer",
        "committee_role": "Committee role",
        "other": "Other",
    },
    BulletType: {
        "achievement": "Achievement",
        "responsibility": "Responsibility",
        "deliverable": "Deliverable",
        "outcome": "Outcome",
        "activity": "Activity",
    },
    Involvement: {
        "leading": "Leading",
        "coordinating": "Coordinating",
        "individual": "Individual contribution",
        "participating": "Participating",
        "advising": "Advising",
        "supporting": "Supporting",
    },
    QualificationType: {
        "degree": "Degree",
        "diploma": "Diploma",
        "certification": "Certification",
        "training": "Professional training",
        "course": "Course",
        "examination": "Examination",
    },
    EducationLevel: {
        "doctorate": "Doctorate",
        "masters": "Master's",
        "bachelors": "Bachelor's",
        "diploma": "Diploma",
        "higher_secondary": "Higher secondary",
        "secondary": "Secondary",
        "certificate": "Certificate",
        "other": "Other",
    },
    EducationStatus: {"completed": "Completed", "ongoing": "Ongoing", "planned": "Planned"},
    PublicationType: {
        "journal": "Journal article",
        "conference": "Conference paper",
        "preprint": "Preprint",
        "thesis": "Thesis",
        "book_chapter": "Book chapter",
        "book": "Book",
        "technical_report": "Technical report",
        "poster": "Poster / abstract",
        "other": "Other",
    },
    PublicationStatus: {
        "draft": "In preparation",
        "submitted": "Submitted",
        "under_review": "Under review",
        "accepted": "Accepted",
        "published": "Published",
        "withdrawn": "Withdrawn",
    },
    ProjectStatus: {
        "concept": "Concept",
        "in_progress": "In progress",
        "prototype": "Prototype",
        "completed": "Completed",
        "operational": "Operational",
        "discontinued": "Discontinued",
    },
    SkillCategory: {
        "electronics": "Electronics",
        "avionics": "Avionics",
        "embedded": "Embedded systems",
        "instrumentation": "Scientific instrumentation",
        "iot": "IoT",
        "aiml": "AI / machine learning",
        "computer_vision": "Computer vision",
        "edge_ai": "Edge AI",
        "gpu_computing": "GPU computing",
        "model_optimisation": "Model optimisation",
        "drones": "Drones & UAV systems",
        "radar_sensors": "Radar & sensors",
        "software": "Software & tools",
        "data": "Data & databases",
        "research": "Research methods",
        "project_management": "Project management",
        "leadership": "Technical leadership",
        "procurement_admin": "Procurement & administration",
        "languages": "Languages",
        "other": "Other",
    },
    Proficiency: {
        "not_rated": "Not rated",
        "familiar": "Familiar",
        "working": "Working knowledge",
        "proficient": "Proficient",
        "advanced": "Advanced",
        "expert": "Expert",
    },
    ActivityType: {
        "leadership": "Leadership role",
        "committee": "Committee",
        "workshop_management": "Workshop / laboratory management",
        "mentoring": "Mentoring",
        "project_coordination": "Project coordination",
        "technical_review": "Technical review",
        "procurement": "Procurement",
        "presentation": "Presentation / talk",
        "award": "Award / honour",
        "membership": "Professional membership",
        "patent": "Patent",
        "technical_writing": "Technical writing",
        "training_delivered": "Training delivered",
        "outreach": "Outreach",
        "research_grant": "Research grant / funding",
        "peer_review": "Peer review / editorial role",
        "supervision": "Student supervision",
        "conference_organisation": "Conference / workshop organisation",
        "other": "Other",
    },
    SummaryFocus: {
        "general": "General",
        "scientific_leadership": "Scientific leadership",
        "defence_technology": "Defence technology",
        "electronics_avionics": "Electronics & avionics",
        "aiml_research": "AI/ML research",
        "embedded_systems": "Embedded systems",
        "drone_engineering": "Drone engineering",
        "academic": "Academic",
        "technical_management": "Technical management",
        "government_deputation": "Government deputation",
        "custom": "Custom",
    },
    RequirementCategory: {
        "mandatory_qualification": "Mandatory qualification",
        "desirable_qualification": "Desirable qualification",
        "technical": "Technical competency",
        "research": "Research expectation",
        "leadership": "Leadership requirement",
        "experience": "Experience requirement",
        "documentation": "Documentation requirement",
        "eligibility": "Eligibility condition",
    },
    EvidenceStatus: {
        "verified": "Supported by verified evidence",
        "awaiting_confirmation": "Supported, awaiting confirmation",
        "partial": "Partially supported",
        "not_found": "Not found in the profile",
        "not_applicable": "Not applicable",
        "official_verification": "Requires official verification",
    },
    RecruitmentMode: {
        "unknown": "Not stated",
        "direct_recruitment": "Direct recruitment",
        "deputation": "Deputation",
        "absorption": "Absorption",
        "contract": "Contract",
        "lateral_entry": "Lateral entry",
        "promotion": "Promotion",
        "other": "Other",
    },
    ApplicationStatus: {
        "saved": "Saved",
        "researching": "Researching",
        "eligibility_review": "Eligibility review",
        "preparing": "Preparing",
        "applied": "Applied",
        "interview": "Interview",
        "awaiting_decision": "Awaiting decision",
        "selected": "Selected",
        "rejected": "Rejected",
        "withdrawn": "Withdrawn",
    },
    ResumeLength: {"one_page": "One page", "two_pages": "Two pages", "full": "Full CV (no limit)"},
    ClaimStatus: {"pending": "Pending approval", "approved": "Approved", "rejected": "Rejected"},
}


def label(member: StrEnum | str, enum_type: type | None = None) -> str:
    """Return the human-readable label for an enum member (or raw value + type)."""
    if enum_type is None:
        if not isinstance(member, StrEnum):
            return str(member)
        enum_type = type(member)
    value = member.value if isinstance(member, StrEnum) else str(member)
    return LABELS.get(enum_type, {}).get(value, value.replace("_", " ").capitalize())


def choices(enum_type: type) -> list[tuple[str, str]]:
    """List of (value, label) pairs in declaration order, for UI combo boxes."""
    return [(m.value, label(m)) for m in enum_type]  # type: ignore[attr-defined]
