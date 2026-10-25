"""Which document format suits a vacancy best (advice only; the notice always prevails).

Based on how Central Government posts at Scientist F/G level (Pay Level 13A/14) are filled:

* Deputation, absorption and short-term contract circulars ask for the Bio-data / CV proforma of DoPT OM
  No. AB.14017/28/2014-Estt.(RR) dated 02.07.2015, forwarded through proper channel with the employer's certificate,
  APARs for five years, vigilance and integrity clearance and a statement of penalties (for example NTRO's 2026
  circulars). Some circulars enclose their own form, which must then be used.
* Direct recruitment (for example DRDO's Recruitment and Assessment Centre) is by online application with
  uploaded certificates; senior candidates are shortlisted on qualifications, relevant experience and
  achievements and selected by interview. A detailed, single-column CV that justifies each requirement helps
  fill the online form and is read at screening and interview.
* A graphical profile helps at interviews and in networking; it is not a substitute for the prescribed form.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ris.domain.enums import RecruitmentMode

PROFORMA_CHECKLIST = (
    "Bio-data in the DoPT proforma (items 1–18), signed, with a recent photograph if the circular asks for one",
    "Certification by the employer / cadre controlling authority (completed and countersigned by your office)",
    "Attested photocopies of APARs for the last five years (or the APAR dossier)",
    "Vigilance clearance and integrity certificate; cadre clearance if you are already on deputation",
    "Statement of major / minor penalties in the last ten years, or a 'nil' certificate",
    "Attested copies of educational qualifications and experience certificates",
    "Forward the application through proper channel before the closing date",
)
DIRECT_CHECKLIST = (
    "Apply online on the recruiter's portal before the closing date; keep each upload within the size limit",
    "Upload proof of date of birth, qualifications, experience certificates and pay proof for the claimed period",
    "Use the justification / experience fields to match each essential and desirable requirement",
    "Inform your cadre controlling authority in writing and carry the acknowledgement or NOC to the interview",
)


@dataclass
class FormatAdvice:
    mode: str
    template: str
    title: str
    reason: str
    companions: list[tuple[str, str, str]] = field(default_factory=list)  # (mode, template, purpose)
    checklist: tuple[str, ...] = ()
    own_form_warning: str = ""

    def as_text(self) -> str:
        lines = [f"Recommended: {self.title}", self.reason]
        if self.own_form_warning:
            lines.append(self.own_form_warning)
        for _mode, _tpl, purpose in self.companions:
            lines.append(f"Also useful: {purpose}")
        if self.checklist:
            lines.append("Checklist:")
            lines.extend(f"• {c}" for c in self.checklist)
        return "\n".join(lines)


_OWN_FORM = re.compile(r"\b(application form|prescribed (?:form|format|proforma)|annexure|bio-?data form)\b", re.I)
_SENIOR = re.compile(r"\b(scientist\s*['‘’]?\s*[fg]\b|level[\s-]*1[34]a?\b|13a|director|head|chief)", re.I)


def recommend(*, mode: str = "", pay_level: str = "", title: str = "", employer: str = "",
              notes: str = "") -> FormatAdvice:
    """Advice for one vacancy from its recruitment mode, level and notice text."""
    m = (mode or "").lower()
    text = " ".join([title, pay_level, notes])
    own = ("This notice mentions its own application form or annexure: fill that form, using the proforma "
           "content as your source.") if _OWN_FORM.search(notes or "") else ""
    graphical = ("senior_graphical", "senior_graphical",
                 "a graphical profile to hand to the interview board or use in networking (not for the application)")
    if m in (RecruitmentMode.DEPUTATION, RecruitmentMode.ABSORPTION, "deputation / absorption") or \
            "deputation" in m or "absorption" in m:
        return FormatAdvice(
            "deputation_proforma", "dopt_proforma", "Deputation application in the DoPT bio-data proforma",
            "Deputation, absorption and short-term contract circulars for Central Government posts prescribe the "
            "bio-data / CV proforma of DoPT OM dated 02.07.2015, forwarded through proper channel with the "
            "employer's certificate.",
            companions=[("senior_scientist", "senior_scientist",
                         "the Senior Scientist CV as the 'separate sheet' for items 7 and 16 if space is short"),
                        graphical],
            checklist=PROFORMA_CHECKLIST, own_form_warning=own)
    if m in (RecruitmentMode.DIRECT, "direct recruitment", RecruitmentMode.LATERAL, "lateral entry") or \
            (m in ("", RecruitmentMode.UNKNOWN, RecruitmentMode.OTHER) and _SENIOR.search(text)):
        org = (employer or "").lower()
        where = " through RAC's online system (rac.gov.in)" if ("drdo" in org or "rac" in org) else ""
        return FormatAdvice(
            "senior_scientist", "senior_scientist", "Senior Scientist (F/G) — R&D leadership CV",
            f"Direct and lateral recruitment is by online application{where} with uploaded certificates; senior "
            "candidates are shortlisted on qualifications, relevant experience and achievements and selected by "
            "interview. Link this vacancy so the CV includes a justification against each requirement.",
            companions=[graphical], checklist=DIRECT_CHECKLIST, own_form_warning=own)
    if m in (RecruitmentMode.CONTRACT, "contract"):
        return FormatAdvice(
            "senior_scientist", "senior_scientist", "Senior Scientist (F/G) — R&D leadership CV",
            "Contract appointments are usually made on a CV and interview; lead with leadership and programme "
            "delivery. Follow any format the notice prescribes.",
            companions=[graphical], own_form_warning=own)
    return FormatAdvice(
        "senior_scientist", "senior_scientist", "Senior Scientist (F/G) — R&D leadership CV",
        "The mode of recruitment is not recorded. A detailed single-column CV is the safest default; switch to the "
        "deputation proforma if the post is filled on deputation.",
        companions=[graphical], own_form_warning=own)


def recommend_for_vacancy(vacancy) -> FormatAdvice:
    return recommend(mode=str(vacancy.recruitment_mode), pay_level=vacancy.pay_level, title=vacancy.title,
                     employer=vacancy.employer, notes=" ".join([vacancy.application_notes, vacancy.raw_text]))
