"""Validated payload models for every record kind.

Each record is stored as an envelope (id, kind, verification, confidentiality,
revision, ...) plus a JSON payload validated by one of these models.

Design notes
------------
* ``extra="allow"``: unknown fields written by a newer version survive a
  round trip through an older one.
* Field metadata (``json_schema_extra``) drives the generic UI editor:
  ``widget``, ``group``, ``private`` (never rendered in resumes unless the user
  explicitly opts in for a specific variant), ``ref_kind`` for record links.
* Semantic warnings (chronology, plausibility) are computed by services;
  models only reject malformed values.
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from ris.domain import dates
from ris.domain.enums import (
    ActivityType,
    ApplicationStatus,
    AssignmentType,
    BulletType,
    ClaimStatus,
    EducationLevel,
    EducationStatus,
    EmploymentType,
    EvidenceStatus,
    Involvement,
    Proficiency,
    ProjectStatus,
    PublicationStatus,
    PublicationType,
    QualificationType,
    QuestionCategory,
    QuestionnaireType,
    RecruitmentMode,
    RequirementCategory,
    ResumeLength,
    Sector,
    SkillCategory,
    SummaryFocus,
    TrainingMode,
    TrainingStatus,
    TrainingType,
)
from ris.util import new_id

# --------------------------------------------------------------------------- coercion helpers


def first_line(text: str, limit: int = 80) -> str:
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


def _norm_date(value: Any) -> str:
    if value is None:
        return ""
    return dates.normalize(str(value))


def _to_list(value: Any) -> list[str]:
    """Accept a list or a newline-separated string; drop empty items."""
    if value is None:
        return []
    if isinstance(value, str):
        items = value.splitlines()
    elif isinstance(value, (list, tuple)):
        items = [str(v) for v in value if v is not None]
    else:
        items = [str(value)]
    return [i.strip() for i in items if i and i.strip()]


def _to_tags(value: Any) -> list[str]:
    """Accept a list or a comma/semicolon/newline-separated string; de-duplicate, keep order."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,;\n]", value)
    elif isinstance(value, (list, tuple)):
        parts = []
        for v in value:
            parts.extend(re.split(r"[,;\n]", str(v)) if v is not None else [])
    else:
        parts = [str(value)]
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if p and p.casefold() not in seen:
            seen.add(p.casefold())
            out.append(p)
    return out


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL = re.compile(r"^(https?://)?([\w-]+\.)+[\w-]{2,}(:\d+)?(/\S*)?$", re.IGNORECASE)
_ORCID = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
_PHONE_CHARS = re.compile(r"^[+\d\s().\-/]+$")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _norm_email(value: Any) -> str:
    v = (value or "").strip()
    if v and not _EMAIL.match(v):
        raise ValueError(f"'{v}' is not a valid email address")
    return v


def _norm_url(value: Any) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if v.lower().startswith(("mailto:", "tel:")):
        return v
    if not _URL.match(v):
        raise ValueError(f"'{v}' is not a valid web address")
    if not re.match(r"^https?://", v, re.IGNORECASE):
        v = "https://" + v
    return v


def _norm_phone(value: Any) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if not _PHONE_CHARS.match(v):
        raise ValueError("Telephone may contain digits, spaces, +, -, (, ) and / only")
    digits = re.sub(r"\D", "", v)
    if not (7 <= len(digits) <= 15):
        raise ValueError("Telephone should contain 7 to 15 digits")
    return v


def _norm_orcid(value: Any) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    v = re.sub(r"^https?://(www\.)?orcid\.org/", "", v, flags=re.IGNORECASE).strip("/")
    if not _ORCID.match(v.upper()):
        raise ValueError("ORCID must look like 0000-0002-1825-0097")
    return v.upper()


def _norm_doi(value: Any) -> str:
    v = (value or "").strip()
    v = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", v, flags=re.IGNORECASE)
    v = re.sub(r"^doi:\s*", "", v, flags=re.IGNORECASE)
    if v and not v.startswith("10."):
        raise ValueError("A DOI starts with '10.' (for example 10.1109/ACCESS.2024.1234567)")
    return v


def _norm_hex(value: Any) -> str:
    v = (value or "").strip()
    if v and not _HEX.match(v):
        raise ValueError("Colour must be a hex value such as #701C35")
    return v.upper()


PDate = Annotated[str, BeforeValidator(_norm_date)]
TextList = Annotated[list[str], BeforeValidator(_to_list)]
Tags = Annotated[list[str], BeforeValidator(_to_tags)]
Email = Annotated[str, BeforeValidator(_norm_email)]
Url = Annotated[str, BeforeValidator(_norm_url)]
Phone = Annotated[str, BeforeValidator(_norm_phone)]
Orcid = Annotated[str, BeforeValidator(_norm_orcid)]
Doi = Annotated[str, BeforeValidator(_norm_doi)]
HexColour = Annotated[str, BeforeValidator(_norm_hex)]


def F(
    default: Any = "",
    title: str = "",
    *,
    widget: str = "line",
    help: str = "",  # noqa: A002 - mirrors UI wording
    group: str = "Details",
    private: bool = False,
    ref_kind: str | None = None,
    placeholder: str = "",
    hidden: bool = False,
) -> Any:
    """Field with UI metadata. Mutable defaults become factories."""
    extra: dict[str, Any] = {"widget": widget, "group": group, "private": private}
    if ref_kind:
        extra["ref_kind"] = ref_kind
    if placeholder:
        extra["placeholder"] = placeholder
    if hidden:
        extra["hidden"] = True
    if isinstance(default, list):
        return Field(default_factory=list, title=title, description=help, json_schema_extra=extra)
    if isinstance(default, dict):
        return Field(default_factory=dict, title=title, description=help, json_schema_extra=extra)
    return Field(default=default, title=title, description=help, json_schema_extra=extra)


# --------------------------------------------------------------------------- base


class RecordData(BaseModel):
    """Base class for every record payload."""

    model_config = ConfigDict(
        extra="allow",
        str_strip_whitespace=True,
        use_enum_values=True,
        validate_default=True,
    )

    custom: dict[str, str] = F(
        {},
        "Custom fields",
        widget="custom",
        group="Custom fields",
        help="Your own fields (name → value). They are stored with the record and can be shown in custom sections.",
    )

    @field_validator("custom", mode="before")
    @classmethod
    def _custom_to_str(cls, v: Any) -> dict[str, str]:
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError("Custom fields must be name/value pairs")
        return {str(k).strip(): ("" if val is None else str(val)) for k, val in v.items() if str(k).strip()}

    # Subclasses override.
    def display_title(self) -> str:
        return ""

    def display_subtitle(self) -> str:
        return ""

    def search_text(self) -> str:
        parts: list[str] = []

        def walk(v: Any) -> None:
            if isinstance(v, str):
                if v:
                    parts.append(v)
            elif isinstance(v, dict):
                for k, x in v.items():
                    if isinstance(k, str):
                        parts.append(k)
                    walk(x)
            elif isinstance(v, (list, tuple)):
                for x in v:
                    walk(x)

        walk(self.model_dump())
        return "\n".join(parts)


class _Dated(RecordData):
    """Mixin validation for start/end/is_current."""

    @model_validator(mode="after")
    def _check_range(self) -> _Dated:
        start = getattr(self, "start", "")
        end = getattr(self, "end", "")
        is_current = getattr(self, "is_current", False)
        if is_current and end:
            # A current role has no end date; keep data consistent.
            object.__setattr__(self, "end", "")
            end = ""
        s = dates.parse_or_none(start)
        e = dates.parse_or_none(end)
        if s and e and e.sort_key() < s.sort_key():
            raise ValueError("End date is before start date")
        return self


# --------------------------------------------------------------------------- profile facts


class PersonalInfo(RecordData):
    full_name: str = F("", "Full name", group="Identity")
    preferred_name: str = F(
        "", "Preferred professional name", group="Identity", help="How your name should appear on documents, e.g. 'Dr. Anika Sharma'."
    )
    professional_title: str = F(
        "", "Professional title", group="Identity", help="Shown under your name, e.g. 'Scientist F — Upper Air Instrumentation'."
    )
    author_name_variants: Tags = F(
        [], "Author name variants", widget="tags", group="Identity",
        help="How your name appears in author lists (e.g. 'A. Sharma'); used to highlight you in publication lists.",
    )
    city: str = F("", "City", group="Location")
    state: str = F("", "State / region", group="Location")
    country: str = F("", "Country", group="Location")
    phone: Phone = F("", "Telephone", group="Contact")
    email: Email = F("", "Email", widget="email", group="Contact")
    linkedin: Url = F("", "LinkedIn", widget="url", group="Online profiles")
    github: Url = F("", "GitHub", widget="url", group="Online profiles")
    portfolio: Url = F("", "Portfolio", widget="url", group="Online profiles")
    website: Url = F("", "Personal website", widget="url", group="Online profiles")
    orcid: Orcid = F("", "ORCID iD", group="Online profiles", placeholder="0000-0000-0000-0000")
    google_scholar: Url = F("", "Google Scholar", widget="url", group="Online profiles")
    researchgate: Url = F("", "ResearchGate", widget="url", group="Online profiles")
    naukri: Url = F("", "Naukri profile", widget="url", group="Online profiles")
    indeed: Url = F("", "Indeed profile", widget="url", group="Online profiles")
    scopus_id: str = F("", "Scopus Author ID", group="Online profiles", placeholder="57200000000")
    researcher_id: str = F("", "Web of Science ResearcherID", group="Online profiles", placeholder="ABC-1234-2020")
    other_profiles: TextList = F(
        [], "Other research profiles", widget="list", group="Online profiles",
        help="One per line as 'Label | URL', e.g. 'Scopus | https://www.scopus.com/authid/...'.",
    )
    languages: Tags = F([], "Languages", widget="tags", group="Contact", help="Comma separated, e.g. English, Hindi.")
    citations: str = F("", "Total citations", group="Research metrics",
                       help="Enter only a figure you have checked, e.g. from your Google Scholar profile.")
    h_index: str = F("", "h-index", group="Research metrics")
    i10_index: str = F("", "i10-index", group="Research metrics")
    metrics_source: str = F("", "Source of metrics", group="Research metrics", placeholder="Google Scholar",
                            help="Shown next to the figures in graphical resumes, so readers know where they come from.")
    metrics_as_of: PDate = F("", "Metrics checked on", widget="date", group="Research metrics")
    photo_path: str = F("", "Photograph (optional)", widget="file", group="Photograph", help="Used only by templates and variants where you enable a photograph.")
    # ---- private particulars: excluded from documents by default
    home_address: str = F("", "Home address", widget="text", group="Private particulars", private=True)
    date_of_birth: PDate = F("", "Date of birth", widget="date", group="Private particulars", private=True)
    nationality: str = F("", "Nationality", group="Private particulars", private=True)
    date_of_entry_into_service: PDate = F(
        "", "Date of entry into service", widget="date", group="Private particulars", private=True
    )
    present_pay_level: str = F("", "Present pay level", group="Private particulars", private=True)
    nature_of_employment: str = F(
        "", "Nature of present employment", group="Private particulars", private=True,
        help="e.g. Permanent / Quasi-permanent / Temporary — used only in government bio-data when you enable it.",
    )

    def display_title(self) -> str:
        return self.preferred_name or self.full_name or "Personal details"

    def display_subtitle(self) -> str:
        return self.professional_title

    def display_name(self) -> str:
        return self.preferred_name or self.full_name


PRIVATE_PERSONAL_FIELDS: tuple[str, ...] = (
    "home_address",
    "date_of_birth",
    "nationality",
    "date_of_entry_into_service",
    "present_pay_level",
    "nature_of_employment",
)


class Summary(RecordData):
    focus: SummaryFocus = F(SummaryFocus.GENERAL, "Focus", widget="choice")
    title: str = F("", "Label", help="Your own label, e.g. 'Defence R&D — two lines'.")
    text: str = F("", "Summary text", widget="text")

    def display_title(self) -> str:
        return self.title or f"{SummaryFocus(self.focus).value.replace('_', ' ').capitalize()} summary"

    def display_subtitle(self) -> str:
        return self.text[:90]


class Position(_Dated):
    designation: str = F("", "Official designation", group="Role")
    organisation: str = F("", "Organisation", group="Role")
    division: str = F("", "Division / unit", group="Role")
    employment_type: EmploymentType = F(EmploymentType.PERMANENT, "Employment type", widget="choice", group="Role")
    sector: Sector = F(Sector.CENTRAL_GOVERNMENT, "Sector", widget="choice", group="Role")
    location: str = F("", "Location", group="Role")
    start: PDate = F("", "Start", widget="date", group="Dates")
    end: PDate = F("", "End", widget="date", group="Dates")
    is_current: bool = F(False, "Current position", widget="bool", group="Dates")
    summary: str = F("", "Role summary", widget="text", group="Description", help="One or two sentences describing the role in plain language.")
    nature_of_duties: str = F(
        "", "Nature of duties (bio-data)", widget="text", group="Description",
        help="Used by the government bio-data format ('Nature of duties').",
    )
    tools: Tags = F([], "Tools & technologies", widget="tags", group="Description")
    short_name: str = F("", "Short organisation name", group="Graphical resumes",
                        help="Used as the label in career timeline charts, e.g. 'DRDO' or 'ISRO'.")
    highlight: str = F("", "One-line highlight", group="Graphical resumes",
                       help="A short phrase for timeline legends, e.g. 'LCA avionics and weapon-system integration'.")
    approved_external_wording: str = F(
        "", "Approved external wording", widget="text", group="Disclosure",
        help="Employer-approved description for external use. When present it is preferred in documents.",
    )
    evidence: str = F("", "Supporting evidence", widget="text", group="Disclosure", help="e.g. office order number and date, appointment letter.")
    pay_level: str = F("", "Pay level", group="Government particulars", private=True)
    notes: str = F("", "Private notes", widget="text", group="Private notes", private=True)

    def display_title(self) -> str:
        return self.designation or "Untitled position"

    def display_subtitle(self) -> str:
        bits = [b for b in (self.organisation, dates.format_range(self.start, self.end, self.is_current)) if b]
        return " · ".join(bits)


class Assignment(_Dated):
    title: str = F("", "Responsibility", help="e.g. 'Workshop In-charge'.")
    assignment_type: AssignmentType = F(AssignmentType.ADDITIONAL_CHARGE, "Type", widget="choice")
    unit: str = F("", "Unit / scope", help="e.g. 'Upper Air Division Workshop'.")
    start: PDate = F("", "Start", widget="date", group="Dates")
    end: PDate = F("", "End", widget="date", group="Dates")
    is_current: bool = F(False, "Current", widget="bool", group="Dates")
    description: str = F("", "Description", widget="text")
    evidence: str = F("", "Supporting evidence", widget="text", group="Disclosure")
    notes: str = F("", "Private notes", widget="text", group="Private notes", private=True)

    def display_title(self) -> str:
        return ", ".join(b for b in (self.title, self.unit) if b) or "Concurrent responsibility"

    def display_subtitle(self) -> str:
        return dates.format_range(self.start, self.end, self.is_current)


class Bullet(RecordData):
    text: str = F("", "Statement", widget="text", help="One factual statement. Avoid numbers you cannot verify.")
    bullet_type: BulletType = F(BulletType.ACHIEVEMENT, "Type", widget="choice")
    involvement: Involvement | None = F(None, "Your involvement", widget="choice", help="Leave empty to use the parent record's involvement.")
    outcome: str = F("", "Outcome", widget="text")
    metrics: TextList = F([], "Verified metrics", widget="list", help="One per line, e.g. '4× smaller model on Jetson Xavier NX'.")
    tools: Tags = F([], "Tools & technologies", widget="tags")
    keywords: Tags = F([], "Keywords", widget="tags")
    date: PDate = F("", "Date", widget="date")
    evidence: str = F("", "Supporting evidence", widget="text", group="Disclosure")
    notes: str = F("", "Private notes", widget="text", group="Private notes", private=True)

    def display_title(self) -> str:
        return self.text[:120] or "Empty statement"


class Education(_Dated):
    qualification_type: QualificationType = F(QualificationType.DEGREE, "Type", widget="choice", group="Qualification")
    level: EducationLevel = F(EducationLevel.BACHELORS, "Level", widget="choice", group="Qualification")
    degree: str = F("", "Qualification", group="Qualification", help="e.g. 'M.Tech', 'Ph.D.', 'AWS Certified ...'.")
    discipline: str = F("", "Discipline", group="Qualification", help="e.g. 'Electronics and Communication Engineering'.")
    specialisation: str = F("", "Specialisation", group="Qualification")
    institution: str = F("", "Institution", group="Institution")
    university: str = F("", "University / awarding body", group="Institution")
    issuer: str = F("", "Issuer (certifications)", group="Institution")
    location: str = F("", "Location", group="Institution")
    start: PDate = F("", "Start", widget="date", group="Dates & status")
    end: PDate = F("", "Completion", widget="date", group="Dates & status")
    status: EducationStatus = F(EducationStatus.COMPLETED, "Status", widget="choice", group="Dates & status")
    grade: str = F("", "Grade / division", group="Dates & status", help="e.g. 'CGPA 8.4/10' or 'First Class with Distinction'.")
    thesis_title: str = F("", "Thesis / dissertation", widget="text", group="Research")
    supervisor: str = F("", "Supervisor", group="Research")
    coursework: TextList = F([], "Relevant coursework", widget="list", group="Research")
    credential_url: Url = F("", "Credential URL", widget="url", group="Institution")
    notes: str = F("", "Private notes", widget="text", group="Private notes", private=True)

    def display_title(self) -> str:
        d = self.degree or "Qualification"
        return f"{d}, {self.discipline}" if self.discipline else d

    def display_subtitle(self) -> str:
        bits = [b for b in (self.institution or self.issuer, self.end or self.start, self.status) if b]
        return " · ".join(bits)


class Publication(RecordData):
    title: str = F("", "Title", widget="text", group="Citation")
    authors: str = F("", "Authors (as published)", group="Citation", help="e.g. 'A. Sharma, R. Iyer, and K. Rao'.")
    venue: str = F("", "Journal / conference / publisher", group="Citation")
    pub_type: PublicationType = F(PublicationType.JOURNAL, "Type", widget="choice", group="Citation")
    status: PublicationStatus = F(PublicationStatus.DRAFT, "Status", widget="choice", group="Citation",
                                  help="Only 'Published' items are described as published in documents.")
    date: PDate = F("", "Date", widget="date", group="Citation", help="Publication date, or submission date for unpublished work.")
    volume: str = F("", "Volume", group="Citation")
    issue: str = F("", "Issue", group="Citation")
    pages: str = F("", "Pages / article no.", group="Citation")
    doi: Doi = F("", "DOI", group="Links")
    url: Url = F("", "Verified public URL", widget="url", group="Links")
    indexing: str = F("", "Indexing (as verified)", group="Citation", help="e.g. 'SCIE, Scopus' — enter only what you have verified.")
    abstract: str = F("", "Abstract", widget="text", group="Content")
    contribution: str = F("", "Your contribution", widget="text", group="Content")
    methodology: str = F("", "Methodology", widget="text", group="Content")
    metrics: TextList = F([], "Key results / metrics", widget="list", group="Content")
    related_project_ids: list[str] = F([], "Related projects", widget="refs", group="Links", ref_kind="project")
    notes: str = F("", "Private notes", widget="text", group="Private notes", private=True)

    def display_title(self) -> str:
        return self.title or "Untitled publication"

    def display_subtitle(self) -> str:
        bits = [b for b in (self.venue, self.date[:4] if self.date else "", PublicationStatus(self.status).value.replace("_", " ")) if b]
        return " · ".join(bits)


class Project(_Dated):
    title: str = F("", "Title", group="Overview")
    problem: str = F("", "Problem addressed", widget="text", group="Overview")
    role: str = F("", "Your role", group="Overview", help="e.g. 'Principal investigator', 'Design lead'.")
    involvement: Involvement = F(Involvement.PARTICIPATING, "Involvement", widget="choice", group="Overview")
    organisation: str = F("", "Organisation / sponsor", group="Overview")
    status: ProjectStatus = F(ProjectStatus.COMPLETED, "Status", widget="choice", group="Overview")
    start: PDate = F("", "Start", widget="date", group="Dates")
    end: PDate = F("", "End", widget="date", group="Dates")
    is_current: bool = F(False, "Ongoing", widget="bool", group="Dates")
    approach: str = F("", "Technical approach", widget="text", group="Technical")
    architecture: str = F("", "Architecture", widget="text", group="Technical")
    hardware: Tags = F([], "Hardware", widget="tags", group="Technical")
    software: Tags = F([], "Software", widget="tags", group="Technical")
    algorithms: Tags = F([], "Algorithms / methods", widget="tags", group="Technical")
    dataset: str = F("", "Dataset", widget="text", group="Technical")
    results: str = F("", "Results", widget="text", group="Results")
    metrics: TextList = F([], "Verified metrics", widget="list", group="Results")
    limitations: str = F("", "Limitations", widget="text", group="Results")
    individual_contribution: str = F("", "Individual contribution", widget="text", group="Contribution")
    team_contribution: str = F("", "Team contribution", widget="text", group="Contribution")
    team_size: int | None = F(None, "Team size", widget="number", group="Contribution")
    evidence: str = F("", "Supporting evidence", widget="text", group="Disclosure")
    approved_external_description: str = F(
        "", "Approved external description", widget="text", group="Disclosure",
        help="Description cleared for external use. Preferred in documents and the only text used in the redacted portfolio.",
    )
    related_position_id: str = F("", "Related position", widget="ref", group="Links", ref_kind="position")
    keywords: Tags = F([], "Keywords", widget="tags", group="Links")
    url: Url = F("", "Public URL", widget="url", group="Links")
    notes: str = F("", "Private notes", widget="text", group="Private notes", private=True)

    @field_validator("team_size", mode="before")
    @classmethod
    def _team(cls, v: Any) -> int | None:
        if v in (None, ""):
            return None
        n = int(v)
        if n < 1 or n > 10000:
            raise ValueError("Team size must be between 1 and 10000")
        return n

    def display_title(self) -> str:
        return self.title or "Untitled project"

    def display_subtitle(self) -> str:
        bits = [b for b in (self.role, dates.format_range(self.start, self.end, self.is_current)) if b]
        return " · ".join(bits)


class Skill(RecordData):
    name: str = F("", "Skill")
    category: SkillCategory = F(SkillCategory.OTHER, "Category", widget="choice")
    proficiency: Proficiency = F(Proficiency.NOT_RATED, "Proficiency (your assessment)", widget="choice",
                                 help="Set by you. The software never infers proficiency.")
    years_experience: float | None = F(None, "Years of experience", widget="number")
    last_used: str = F("", "Last used (year)", placeholder="2026")
    project_ids: list[str] = F([], "Associated projects", widget="refs", ref_kind="project")
    evidence: str = F("", "Evidence", widget="text")
    aliases: Tags = F([], "Synonyms for matching", widget="tags", help="Other names recruiters use, e.g. 'DL' for deep learning.")
    notes: str = F("", "Private notes", widget="text", group="Private notes", private=True)

    @field_validator("years_experience", mode="before")
    @classmethod
    def _years(cls, v: Any) -> float | None:
        if v in (None, ""):
            return None
        f = float(v)
        if f < 0 or f > 60:
            raise ValueError("Years of experience must be between 0 and 60")
        return round(f, 1)

    @field_validator("last_used", mode="before")
    @classmethod
    def _last_used(cls, v: Any) -> str:
        s = str(v or "").strip()
        if s and not re.fullmatch(r"(19|20)\d{2}", s):
            raise ValueError("Last used must be a four-digit year")
        return s

    def display_title(self) -> str:
        return self.name or "Unnamed skill"

    def display_subtitle(self) -> str:
        return SkillCategory(self.category).value.replace("_", " ")


class Activity(_Dated):
    activity_type: ActivityType = F(ActivityType.LEADERSHIP, "Type", widget="choice")
    title: str = F("", "Title", help="e.g. 'Chair, Committee on server inventory'.")
    role: str = F("", "Your role")
    involvement: Involvement = F(Involvement.PARTICIPATING, "Involvement", widget="choice")
    organisation: str = F("", "Organisation / body")
    start: PDate = F("", "Start", widget="date", group="Dates")
    end: PDate = F("", "End", widget="date", group="Dates")
    is_current: bool = F(False, "Current", widget="bool", group="Dates")
    description: str = F("", "Description", widget="text")
    outcome: str = F("", "Outcome", widget="text")
    identifier: str = F("", "Identifier", help="Patent/application number, award reference, membership number (public identifiers only).")
    status: str = F("", "Status", help="e.g. 'Filed', 'Granted' for patents.")
    url: Url = F("", "Public URL", widget="url")
    evidence: str = F("", "Supporting evidence", widget="text", group="Disclosure")
    notes: str = F("", "Private notes", widget="text", group="Private notes", private=True)

    def display_title(self) -> str:
        return self.title or "Untitled activity"

    def display_subtitle(self) -> str:
        return " · ".join(b for b in (self.organisation, dates.format_range(self.start, self.end, self.is_current)) if b)


class Expertise(RecordData):
    """A domain of expertise with a short narrative (the 'profile summary' table of many CVs)."""

    area: str = F("", "Area of expertise", help="e.g. 'R&D in avionics' or 'Drone ecosystem design and certification'.")
    description: str = F("", "Description", widget="text",
                         help="Factual narrative of what you did in this area, e.g. programmes, platforms, organisations.")
    years_experience: float | None = F(None, "Years of experience", widget="number",
                                       help="Optional; shown under the area name when entered.")
    keywords: Tags = F([], "Keywords", widget="tags", help="Used to match vacancies and choose relevant areas.")
    related_position_ids: list[str] = F([], "Related positions", widget="refs", ref_kind="position")
    related_project_ids: list[str] = F([], "Related projects", widget="refs", ref_kind="project")
    evidence: str = F("", "Supporting evidence", widget="text", group="Disclosure")
    notes: str = F("", "Private notes", widget="text", group="Private notes", private=True)

    def display_title(self) -> str:
        return self.area or "Untitled area"

    def display_subtitle(self) -> str:
        return first_line(self.description, 80)


class Reference(RecordData):
    """A referee. Exported only when you confirm the person agreed to be named."""

    name: str = F("", "Name", group="Referee")
    designation: str = F("", "Designation", group="Referee")
    organisation: str = F("", "Organisation", group="Referee")
    relationship: str = F("", "Relationship", group="Referee", help="e.g. 'Former Project Director' or 'PhD supervisor'.")
    email: Email = F("", "Email", widget="email", group="Contact")
    phone: Phone = F("", "Telephone", group="Contact")
    address: str = F("", "Address", widget="text", group="Contact")
    permission_confirmed: bool = F(False, "This person has agreed to be named as a referee", widget="bool",
                                   group="Permission",
                                   help="Referees are never included in documents until you tick this box.")
    show_contact_details: bool = F(True, "Show their email and telephone in documents", widget="bool", group="Permission")
    notes: str = F("", "Private notes", widget="text", group="Private notes", private=True)

    def display_title(self) -> str:
        return self.name or "Unnamed referee"

    def display_subtitle(self) -> str:
        return ", ".join(x for x in (self.designation, self.organisation) if x)


class Training(_Dated):
    """A training programme, professional course, certification, workshop, seminar or other qualification."""

    training_type: TrainingType = F(TrainingType.TRAINING_PROGRAMME, "Type", widget="choice", group="Programme")
    title: str = F("", "Title", group="Programme",
                   help="As on the certificate, e.g. 'Mid-Career Training Programme' or 'AWS Certified Machine "
                        "Learning – Specialty'.")
    provider: str = F("", "Institute / issuing body", group="Programme",
                      help="e.g. 'ISTM, New Delhi', 'NPTEL (IIT Madras)', 'IEEE', 'Amazon Web Services'.")
    sponsor: str = F("", "Sponsored / nominated by", group="Programme",
                     help="The organisation that nominated or funded you, if different from the provider.")
    mode: TrainingMode = F(TrainingMode.CLASSROOM, "Mode", widget="choice", group="Programme")
    location: str = F("", "Location", group="Programme")
    start: PDate = F("", "Start", widget="date", group="Dates & duration")
    end: PDate = F("", "End / issue date", widget="date", group="Dates & duration")
    is_current: bool = F(False, "Ongoing", widget="bool", group="Dates & duration")
    duration_hours: float | None = F(None, "Duration (hours)", widget="number", group="Dates & duration")
    duration_days: float | None = F(None, "Duration (days)", widget="number", group="Dates & duration")
    status: TrainingStatus = F(TrainingStatus.COMPLETED, "Status", widget="choice", group="Dates & duration",
                               help="Planned items are hidden from documents unless you choose to show them.")
    valid_until: PDate = F("", "Valid until (certifications)", widget="date", group="Credential",
                           help="Expired certifications are labelled as expired and left out of one- and "
                                "two-page resumes.")
    grade: str = F("", "Grade / score / result", group="Credential", help="e.g. 'Elite + Gold (NPTEL)', 'Band 8.0'.")
    credential_id: str = F("", "Certificate / credential number", group="Credential")
    credential_url: Url = F("", "Verification URL", widget="url", group="Credential")
    skills: Tags = F([], "Skills covered", widget="tags", group="Content",
                     help="Used to match vacancy requirements and to suggest LinkedIn skills.")
    topics: TextList = F([], "Topics covered", widget="list", group="Content")
    outcome: str = F("", "How you applied it", widget="text", group="Content",
                     help="One sentence on what you did with what you learned (optional).")
    evidence: str = F("", "Supporting evidence", widget="text", group="Disclosure",
                      help="e.g. certificate number, office order nominating you.")
    notes: str = F("", "Private notes", widget="text", group="Private notes", private=True)

    @model_validator(mode="after")
    def _check_validity(self) -> Training:
        e = dates.parse_or_none(self.end)
        v = dates.parse_or_none(self.valid_until)
        if e and v and v.sort_key() < e.sort_key():
            raise ValueError("'Valid until' is before the issue date")
        return self

    def display_title(self) -> str:
        return self.title or "Untitled training"

    def display_subtitle(self) -> str:
        bits = [b for b in (self.provider, self.end or self.start, self.status if self.status != "completed" else "")
                if b]
        return " · ".join(bits)


class InterviewStory(RecordData):
    """A STAR story (Situation, Task, Action, Result) prepared for interviews. Never printed in resumes."""

    title: str = F("", "Story title", group="Story", help="A short name, e.g. 'Rescuing the radiosonde trial'.")
    competencies: Tags = F([], "Competencies it shows", widget="tags", group="Story",
                           help="e.g. leadership, problem-solving, teamwork, integrity, initiative.")
    situation: str = F("", "Situation", widget="text", group="STAR",
                       help="Context in two or three sentences: where, when, what was at stake.")
    task: str = F("", "Task", widget="text", group="STAR", help="What you personally were responsible for.")
    action: str = F("", "Action", widget="text", group="STAR",
                    help="The steps you took and why. Say 'I', not 'we'. This should be the longest part.")
    result: str = F("", "Result", widget="text", group="STAR",
                    help="The outcome, with verified numbers if you have them, and what you learned.")
    linked_ids: list[str] = F([], "Linked profile records", widget="refs", group="Links",
                              ref_kind="position,assignment,project,activity,training",
                              help="Positions, projects or activities this story comes from.")
    notes: str = F("", "Private notes", widget="text", group="Private notes", private=True)

    def display_title(self) -> str:
        return self.title or first_line(self.situation) or "Untitled story"

    def display_subtitle(self) -> str:
        return ", ".join(self.competencies[:4])


class InterviewAnswer(RecordData):
    """Your notes for one interview question, with practice history."""

    question: str = F("", "Question", widget="text", group="Question")
    category: QuestionCategory = F(QuestionCategory.PERSONAL, "Category", widget="choice", group="Question")
    answer: str = F("", "Answer notes", widget="text", group="Answer",
                    help="Key points, not a script: interviewers notice memorised answers.")
    story_ids: list[str] = F([], "STAR stories to use", widget="refs", ref_kind="interview_story", group="Answer")
    confidence: int = F(0, "Confidence (0–5)", widget="number", group="Practice")
    times_practised: int = F(0, "Times practised", widget="number", group="Practice")
    last_practised: str = F("", "Last practised", hidden=True)
    source: str = F("", "Where the question came from", hidden=True)

    @field_validator("confidence", "times_practised", mode="before")
    @classmethod
    def _non_negative(cls, v: Any) -> int:
        try:
            n = int(v or 0)
        except (TypeError, ValueError):
            raise ValueError("Enter a whole number") from None
        return max(0, n)

    @field_validator("confidence")
    @classmethod
    def _cap(cls, v: int) -> int:
        return min(5, v)

    def display_title(self) -> str:
        return first_line(self.question) or "Untitled question"

    def display_subtitle(self) -> str:
        return f"confidence {self.confidence}/5" if self.confidence else ""


class QEducationRow(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)
    examination: str = ""
    institution: str = ""
    board: str = ""
    year: str = ""
    result: str = ""
    subjects: str = ""


class QActivityRow(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)
    activity: str = ""
    level: str = ""
    role: str = ""
    year: str = ""
    achievement: str = ""


class QAttemptRow(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)
    examination: str = ""
    year: str = ""
    centre: str = ""
    result: str = ""


class Questionnaire(RecordData):
    """A personal questionnaire you fill for an interview board (SSB PIQ, DAF-style forms).

    Everything here is private: it is never used in resumes. Boards frame questions from these
    forms, so the app checks them against your profile for inconsistencies.
    """

    form_type: QuestionnaireType = F(QuestionnaireType.SSB_PIQ, "Form", widget="choice", group="Form")
    title: str = F("", "Name of this form", group="Form", help="e.g. 'SSB 2026 PIQ' or 'DRDO interview DAF'.")
    place_of_birth: str = F("", "Place of birth", group="Personal", private=True)
    home_town: str = F("", "Home town / district / state", group="Personal", private=True)
    permanent_address: str = F("", "Permanent address", widget="text", group="Personal", private=True)
    present_address: str = F("", "Present address", widget="text", group="Personal", private=True)
    father: str = F("", "Father's name, education and occupation", widget="text", group="Family", private=True,
                    help="Be specific about the post held, e.g. 'Retired Senior Section Engineer, Indian Railways'.")
    mother: str = F("", "Mother's name, education and occupation", widget="text", group="Family", private=True)
    siblings: str = F("", "Siblings (education, occupation)", widget="text", group="Family", private=True)
    education: list[QEducationRow] = F([], "Education", hidden=True)
    ncc: str = F("", "NCC (certificate, wing, rank)", group="Activities")
    sports: list[QActivityRow] = F([], "Sports", hidden=True)
    extracurricular: list[QActivityRow] = F([], "Extra-curricular activities", hidden=True)
    hobbies: Tags = F([], "Hobbies and interests", widget="tags", group="Activities",
                      help="List only genuine interests: the interviewer will ask about them in detail.")
    responsibilities: TextList = F([], "Positions of responsibility held", widget="list", group="Activities")
    languages: Tags = F([], "Languages known", widget="tags", group="Activities")
    previous_attempts: list[QAttemptRow] = F([], "Previous attempts / interviews", hidden=True)
    service_choice: str = F("", "Choice of service / arm / post", widget="text", group="Preferences")
    reasons: str = F("", "Why you want to join", widget="text", group="Preferences")
    self_description: str = F("", "Self-description notes", widget="text", group="Preferences", private=True)
    notes: str = F("", "Private notes", widget="text", group="Private notes", private=True)

    def display_title(self) -> str:
        return self.title or "Personal questionnaire"


class CustomSection(RecordData):
    name: str = F("", "Section name")
    description: str = F("", "Description", widget="text")
    layout: str = F("entries", "Layout", widget="choice_str", help="entries, bullets or paragraph")
    include_by_default: bool = F(False, "Include in resumes by default", widget="bool")

    @field_validator("layout", mode="before")
    @classmethod
    def _layout(cls, v: Any) -> str:
        v = (v or "entries").strip().lower()
        if v not in ("entries", "bullets", "paragraph"):
            raise ValueError("Layout must be entries, bullets or paragraph")
        return v

    def display_title(self) -> str:
        return self.name or "Untitled section"


class CustomEntry(_Dated):
    title: str = F("", "Title")
    subtitle: str = F("", "Subtitle / organisation")
    start: PDate = F("", "Start", widget="date", group="Dates")
    end: PDate = F("", "End", widget="date", group="Dates")
    is_current: bool = F(False, "Current", widget="bool", group="Dates")
    description: str = F("", "Description", widget="text")
    bullets: TextList = F([], "Points", widget="list")
    url: Url = F("", "Public URL", widget="url")
    notes: str = F("", "Private notes", widget="text", group="Private notes", private=True)

    def display_title(self) -> str:
        return self.title or "Untitled entry"


# --------------------------------------------------------------------------- targets and vacancies


class CareerTarget(RecordData):
    name: str = F("", "Target name")
    preset_id: str = F("", "Based on preset", widget="preset")
    org_profile_id: str = F("", "Organisation profile", widget="org_profile")
    organisation: str = F("", "Organisation")
    sector: str = F("", "Sector")
    description: str = F("", "Description", widget="text")
    keywords: Tags = F([], "Emphasis keywords", widget="tags")
    emphasis_areas: TextList = F([], "Emphasis areas", widget="list")
    preferred_mode: str = F("", "Preferred resume mode", widget="mode")
    preferred_template: str = F("", "Preferred template", widget="template")
    summary_focus: str = F("", "Preferred summary focus", widget="choice_str")
    section_order: TextList = F([], "Section order", widget="list", hidden=True)
    notes: str = F("", "Notes", widget="text", private=True)

    def display_title(self) -> str:
        return self.name or "Untitled target"

    def display_subtitle(self) -> str:
        return self.organisation


class Requirement(BaseModel):
    """One requirement extracted from (or added to) a vacancy."""

    model_config = ConfigDict(extra="allow", use_enum_values=True, str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: new_id()[:12])
    category: RequirementCategory = RequirementCategory.TECHNICAL
    text: str = ""
    mandatory: bool = False
    origin: str = "extracted"  # extracted | manual
    keywords: list[str] = Field(default_factory=list)
    status_override: EvidenceStatus | None = None
    user_note: str = ""
    possessed_note: str = ""  # user's wording for "qualification possessed" in bio-data matrices


class Vacancy(RecordData):
    title: str = F("", "Post / job title", group="Vacancy")
    employer: str = F("", "Employer / organisation", group="Vacancy")
    url: Url = F("", "Official vacancy URL", widget="url", group="Vacancy")
    reference: str = F("", "Recruitment reference / advertisement no.", group="Vacancy")
    recruitment_mode: RecruitmentMode = F(RecruitmentMode.UNKNOWN, "Mode of recruitment", widget="choice", group="Vacancy")
    pay_level: str = F("", "Pay level (as advertised)", group="Vacancy")
    deadline: PDate = F("", "Closing date", widget="date", group="Vacancy")
    target_id: str = F("", "Career target", widget="ref", ref_kind="career_target", group="Vacancy")
    raw_text: str = F("", "Full vacancy text", widget="text", group="Text", help="Paste the notification text. It is treated as data only.")
    essential_qualifications: str = F("", "Essential qualifications", widget="text", group="Text")
    desirable_qualifications: str = F("", "Desirable qualifications", widget="text", group="Text")
    required_skills: str = F("", "Required skills", widget="text", group="Text")
    experience_criteria: str = F("", "Experience criteria", widget="text", group="Text")
    application_notes: str = F("", "Application notes", widget="text", group="Text")
    source_file: str = F("", "Imported from", group="Vacancy", hidden=True)
    requirements: list[Requirement] = F([], "Requirements", widget="requirements", hidden=True)
    extracted_at: str = F("", "Requirements extracted at", hidden=True)

    def display_title(self) -> str:
        return self.title or "Untitled vacancy"

    def display_subtitle(self) -> str:
        return " · ".join(b for b in (self.employer, f"closes {self.deadline}" if self.deadline else "") if b)


# --------------------------------------------------------------------------- resume variants and claims


class Variant(RecordData):
    name: str = F("", "Variant name")
    mode: str = F("general_professional", "Resume mode", widget="mode")
    template_id: str = F("ats_minimal", "Template", widget="template")
    template_version: str = F("", "Template version", hidden=True)
    target_id: str = F("", "Career target", widget="ref", ref_kind="career_target")
    vacancy_id: str = F("", "Vacancy", widget="ref", ref_kind="vacancy")
    length: ResumeLength = F(ResumeLength.TWO_PAGES, "Length", widget="choice")
    max_pages: int | None = F(None, "Maximum pages", widget="number")
    page_size: str = F("A4", "Page size", widget="choice_str")
    section_order: TextList = F([], "Section order", widget="list", hidden=True)
    hidden_sections: TextList = F([], "Hidden sections", widget="list", hidden=True)
    contact_fields: TextList = F([], "Visible contact fields", widget="list", hidden=True)
    summary_id: str = F("", "Summary", widget="ref", ref_kind="summary")
    include_ids: TextList = F([], "Always include", widget="list", hidden=True)
    exclude_ids: TextList = F([], "Exclude", widget="list", hidden=True)
    font_scale: float = F(1.0, "Font scale", widget="number")
    spacing: str = F("normal", "Spacing", widget="choice_str")
    accent_color: HexColour = F("", "Accent colour override", widget="colour")
    show_photo: bool = F(False, "Show photograph", widget="bool")
    include_declaration: bool = F(True, "Include declaration (bio-data)", widget="bool")
    official_particulars: TextList = F([], "Official particulars to include", widget="list", hidden=True)
    redacted: bool = F(False, "Redacted (public items only)", widget="bool")
    include_planned_education: bool = F(False, "Show planned qualifications", widget="bool")
    publication_scope: str = F("relevant", "Publications", widget="choice_str")
    notes: str = F("", "Notes", widget="text", private=True)
    last_generated_at: str = F("", "Last generated", hidden=True)
    source_revisions: dict[str, int] = F({}, "Source revisions", hidden=True)

    @field_validator("font_scale", mode="before")
    @classmethod
    def _scale(cls, v: Any) -> float:
        f = float(v if v not in (None, "") else 1.0)
        if not (0.8 <= f <= 1.2):
            raise ValueError("Font scale must be between 0.8 and 1.2")
        return round(f, 2)

    @field_validator("spacing", mode="before")
    @classmethod
    def _spacing(cls, v: Any) -> str:
        v = (v or "normal").strip().lower()
        if v not in ("compact", "normal", "relaxed"):
            raise ValueError("Spacing must be compact, normal or relaxed")
        return v

    @field_validator("page_size", mode="before")
    @classmethod
    def _page(cls, v: Any) -> str:
        v = (v or "A4").strip()
        if v.upper() == "A4":
            return "A4"
        if v.lower() == "letter":
            return "Letter"
        raise ValueError("Page size must be A4 or Letter")

    @field_validator("max_pages", mode="before")
    @classmethod
    def _max_pages(cls, v: Any) -> int | None:
        if v in (None, "", 0, "0"):
            return None
        n = int(v)
        if n < 1 or n > 50:
            raise ValueError("Maximum pages must be between 1 and 50")
        return n

    @field_validator("publication_scope", mode="before")
    @classmethod
    def _pub_scope(cls, v: Any) -> str:
        v = (v or "relevant").strip().lower()
        if v not in ("relevant", "all", "none"):
            raise ValueError("Publications must be relevant, all or none")
        return v

    def display_title(self) -> str:
        return self.name or "Untitled resume"


class Claim(RecordData):
    """A resume-specific wording of profile facts, with provenance."""

    target_bullet_id: str = F("", "Statement replaced", hidden=True)
    source_record_ids: list[str] = F([], "Source records", hidden=True)
    source_field: str = F("", "Source field", hidden=True)
    original_text: str = F("", "Original wording", widget="text")
    generated_text: str = F("", "Suggested wording", widget="text")
    approved_text: str = F("", "Approved wording", widget="text")
    material_facts: list[str] = F([], "Material facts used", widget="list")
    assumptions: list[str] = F([], "Assumptions", widget="list")
    missing_metrics: list[str] = F([], "Missing metrics", widget="list")
    flags: list[str] = F([], "Validation flags", widget="list")
    status: ClaimStatus = F(ClaimStatus.PENDING, "Status", widget="choice")
    confidentiality: str = F("", "Confidentiality (inherited)", hidden=True)
    approved_at: str = F("", "Approved at", hidden=True)
    generator: str = F("rules-engine", "Generated by", hidden=True)

    def display_title(self) -> str:
        return (self.approved_text or self.generated_text or self.original_text)[:120]


# --------------------------------------------------------------------------- applications and letters


class Application(RecordData):
    organisation: str = F("", "Organisation", group="Vacancy")
    vacancy_title: str = F("", "Vacancy title", group="Vacancy")
    vacancy_id: str = F("", "Linked vacancy", widget="ref", ref_kind="vacancy", group="Vacancy")
    official_url: Url = F("", "Official URL", widget="url", group="Vacancy")
    reference_number: str = F("", "Reference number", group="Vacancy")
    eligibility_notes: str = F("", "Eligibility notes", widget="text", group="Vacancy",
                               help="Your notes after checking the official eligibility conditions.")
    deadline: PDate = F("", "Deadline", widget="date", group="Dates")
    status: ApplicationStatus = F(ApplicationStatus.SAVED, "Status", widget="choice", group="Status")
    variant_id: str = F("", "Resume variant", widget="ref", ref_kind="variant", group="Documents")
    version_id: str = F("", "Resume version", widget="version", group="Documents")
    cover_letter_id: str = F("", "Cover letter", widget="ref", ref_kind="cover_letter", group="Documents")
    submission_date: PDate = F("", "Submitted on", widget="date", group="Dates")
    interview_date: PDate = F("", "Interview date", widget="date", group="Dates")
    follow_up_date: PDate = F("", "Follow-up date", widget="date", group="Dates")
    outcome: str = F("", "Outcome", widget="text", group="Status")
    notes: str = F("", "Notes", widget="text", group="Status", private=True)

    def display_title(self) -> str:
        return self.vacancy_title or "Untitled application"

    def display_subtitle(self) -> str:
        return " · ".join(b for b in (self.organisation, ApplicationStatus(self.status).value.replace("_", " ")) if b)


class CoverLetter(RecordData):
    title: str = F("", "Letter name", group="Letter")
    vacancy_id: str = F("", "Vacancy", widget="ref", ref_kind="vacancy", group="Letter")
    application_id: str = F("", "Application", widget="ref", ref_kind="application", group="Letter")
    style: str = F("formal", "Style", widget="choice_str", group="Letter", help="formal (government) or professional")
    date_text: str = F("", "Date line", group="Letter")
    place: str = F("", "Place", group="Letter")
    recipient_name: str = F("", "Recipient name", group="Recipient")
    recipient_designation: str = F("", "Recipient designation", group="Recipient")
    recipient_organisation: str = F("", "Recipient organisation", group="Recipient")
    recipient_address: TextList = F([], "Recipient address", widget="list", group="Recipient")
    subject: str = F("", "Subject", widget="text", group="Content")
    reference_line: str = F("", "Reference", group="Content")
    salutation: str = F("Dear Sir/Madam,", "Salutation", group="Content")
    paragraphs: TextList = F([], "Paragraphs (one per line)", widget="paragraphs", group="Content")
    closing: str = F("Yours faithfully,", "Closing", group="Content")
    signature_name: str = F("", "Signature name", group="Content")
    signature_designation: str = F("", "Signature designation", group="Content")
    enclosures: TextList = F([], "Enclosures", widget="list", group="Content")
    source_record_ids: list[str] = F([], "Source records", hidden=True)
    status: str = F("draft", "Status", widget="choice_str", group="Letter")

    @field_validator("style", mode="before")
    @classmethod
    def _style(cls, v: Any) -> str:
        v = (v or "formal").strip().lower()
        if v not in ("formal", "professional"):
            raise ValueError("Style must be formal or professional")
        return v

    def display_title(self) -> str:
        return self.title or self.subject[:80] or "Untitled cover letter"
