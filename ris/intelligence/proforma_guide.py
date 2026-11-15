"""Readiness for the deputation bio-data proforma (DoPT OM No. AB.14017/28/2014-Estt.(RR) dated 02.07.2015).

Lists the eighteen items of the proforma, where each is recorded in the application and whether the profile
already holds what is needed. Advice only: the vacancy circular and its prescribed form always prevail, and
formal eligibility is decided by the recruiting authority.
"""

from __future__ import annotations

from dataclasses import dataclass

from ris.domain.enums import RecordKind

READY, MISSING, PER_APPLICATION, IF_APPLICABLE = "ready", "missing", "per_application", "if_applicable"

STATUS_LABEL = {READY: "Recorded", MISSING: "To fill in", PER_APPLICATION: "Per application",
                IF_APPLICABLE: "If applicable"}
STATUS_TONE = {READY: "ok", MISSING: "warn", PER_APPLICATION: "info", IF_APPLICABLE: "info"}


@dataclass
class ProformaItem:
    number: str
    title: str
    status: str
    where: str          # where to record it in the application
    page: str = ""      # navigation key of that page
    detail: str = ""


def _has(personal, *names: str) -> bool:
    return all(str(getattr(personal, n, "") or "").strip() for n in names)


def proforma_readiness(snapshot) -> list[ProformaItem]:
    """The eighteen proforma items with their status for this profile."""
    p = snapshot.personal_data
    positions = snapshot.of(RecordKind.POSITION)
    education = snapshot.of(RecordKind.EDUCATION)
    vacancies = snapshot.of(RecordKind.VACANCY)
    achievements = (len(snapshot.of(RecordKind.PUBLICATION)) + len(snapshot.of(RecordKind.ACTIVITY))
                    + len(snapshot.of(RecordKind.TRAINING)))
    particulars = "Master Profile → Private particulars / Deputation proforma particulars"

    def personal_item(number: str, title: str, *fields: str, optional: bool = False) -> ProformaItem:
        if _has(p, *fields):
            return ProformaItem(number, title, READY, particulars, "profile")
        return ProformaItem(number, title, IF_APPLICABLE if optional else MISSING, particulars, "profile")

    duties = [x for x in positions if str(getattr(x.data, "nature_of_duties", "") or "").strip()]
    if not positions:
        item7 = ProformaItem("7", "Details of employment in chronological order", MISSING, "Experience",
                             "experience", "Add each post held on a regular basis with its dates.")
    elif len(duties) < len(positions):
        item7 = ProformaItem("7", "Details of employment in chronological order", MISSING, "Experience",
                             "experience",
                             f"{len(positions) - len(duties)} of {len(positions)} post(s) have no 'nature of duties' "
                             "text; the proforma asks for duties in detail, highlighting experience required "
                             "for the post.")
    else:
        item7 = ProformaItem("7", "Details of employment in chronological order", READY, "Experience",
                             "experience", f"{len(positions)} post(s) with nature of duties.")

    return [
        personal_item("1", "Name and address (in block letters)", "full_name", "home_address"),
        personal_item("2", "Date of birth (in Christian era)", "date_of_birth"),
        personal_item("3", "Date of entry into service and date of retirement under the rules",
                      "date_of_entry_into_service", "date_of_retirement"),
        ProformaItem("4", "Educational qualifications", READY if education else MISSING, "Education", "education",
                     f"{len(education)} qualification(s) recorded." if education else ""),
        ProformaItem("5", "Whether the educational and other qualifications required for the post are satisfied",
                     PER_APPLICATION, "Job Opportunities → link the vacancy to the resume", "opportunities",
                     "Paste the vacancy circular; the proforma then sets each essential and desirable requirement "
                     "against your evidence." if not vacancies else
                     f"{len(vacancies)} vacancy record(s) available to link."),
        ProformaItem("6", "Statement that you meet the requisite essential qualifications and work experience",
                     PER_APPLICATION, "Resume Studio → Proforma answers", "studio"),
        item7,
        personal_item("8", "Nature of present employment (ad hoc, temporary, quasi-permanent or permanent)",
                      "nature_of_employment"),
        personal_item("9", "If the present post is held on deputation or contract: details",
                      "present_deputation_details", optional=True),
        personal_item("10", "Any post held on deputation in the past: date of return and other details",
                      "past_deputation_details", optional=True),
        personal_item("11", "Present employer (Central / State Government, autonomous body, undertaking, "
                            "university, others)", "employer_type"),
        personal_item("12", "Whether in the same department and in the feeder or feeder-to-feeder grade",
                      "feeder_grade_status", optional=True),
        personal_item("13", "Whether in a revised scale of pay; date of revision and pre-revised scale",
                      "pay_revision_details", optional=True),
        personal_item("14", "Total emoluments per month now drawn (pay level, basic pay, total)",
                      "present_pay_level", "basic_pay", "total_emoluments"),
        personal_item("15", "If the employer does not follow Central Government pay scales: latest salary slip",
                      "non_central_pay_details", optional=True),
        ProformaItem("16", "Additional information and achievements (publications, awards, professional bodies, "
                           "patents, innovations)", READY if achievements else MISSING,
                     "Research & Publications, Training, Leadership & Responsibilities", "research",
                     f"{achievements} supporting record(s)." if achievements else ""),
        ProformaItem("17", "Whether applying on deputation (ISTC), absorption or re-employment basis",
                     PER_APPLICATION, "Resume Studio → Proforma answers", "studio"),
        personal_item("18", "Whether belongs to SC / ST", "sc_st_status", optional=True),
    ]


def readiness_summary(items: list[ProformaItem]) -> str:
    ready = sum(1 for i in items if i.status == READY)
    missing = sum(1 for i in items if i.status == MISSING)
    if missing:
        return f"{ready} of {len(items)} items are recorded; {missing} still need details from you."
    return f"{ready} of {len(items)} items are recorded; the rest are answered for each application."
