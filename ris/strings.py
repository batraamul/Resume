"""Centralised user-facing strings (ready for future localisation)."""

from __future__ import annotations

from ris import APP_NAME, TAGLINE

NAV_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Diary", [("diary", "My Professional Diary")]),
    ("Profile", [
        ("profile", "Master Profile"),
        ("experience", "Experience"),
        ("education", "Education"),
        ("training", "Training & Certifications"),
        ("research", "Research & Publications"),
        ("skills", "Skills & Technologies"),
        ("projects", "Projects & Achievements"),
        ("leadership", "Leadership & Responsibilities"),
    ]),
    ("Opportunities", [
        ("targets", "Career Targets"),
        ("opportunities", "Job Opportunities"),
        ("interview", "Interview Preparation"),
        ("portals", "Job Portals & Recruiters"),
    ]),
    ("Documents", [
        ("studio", "Resume Studio"),
        ("library", "Resume Library"),
        ("letters", "Cover Letters"),
        ("tracker", "Application Tracker"),
        ("exports", "Documents & Exports"),
    ]),
    ("System", [
        ("sync", "Synchronisation"),
        ("backup", "Backup & Restore"),
        ("settings", "Settings & Security"),
    ]),
]

PAGE_SUBTITLES = {
    "diary": "Your profile at a glance: what needs attention, recent documents and upcoming deadlines.",
    "profile": "Identity, contact details, research metrics, summaries, areas of expertise, referees and custom "
               "sections.",
    "experience": "Positions, concurrent responsibilities and the statements that describe your work.",
    "education": "Degrees and diplomas, including ongoing and planned qualifications.",
    "training": "Training programmes, professional courses, certifications, workshops, seminars and other "
                "qualifications.",
    "interview": "Questions tailored to your profile and vacancy, STAR stories, practice with a timer, and your "
                 "personal questionnaire (PIQ/DAF) checked against your profile.",
    "portals": "Leading recruiters and job portals, profile text for LinkedIn, Naukri and Indeed within their "
               "limits, and an ATS readiness check for your resume files.",
    "research": "Publications and manuscripts, each with its exact status.",
    "skills": "Skills you choose to claim, with your own proficiency and evidence.",
    "projects": "Projects with problem, approach, results, contribution and disclosure status.",
    "leadership": "Leadership, committees, awards, memberships, patents, talks, research grants, peer review, "
                  "supervision and conference organisation.",
    "targets": "Defence & Intelligence presets, organisation profiles and your own career targets.",
    "opportunities": "Vacancies: paste or import a notice, extract requirements and map your evidence.",
    "studio": "Compose a tailored resume — plain, government, academic or graphical — review every claim, preview "
              "the layout and export.",
    "library": "Saved resume variants, immutable versions and comparisons.",
    "letters": "Factual cover letters drafted from your profile and the vacancy.",
    "tracker": "Applications, statuses and deadlines.",
    "exports": "Every exported file, with its checksum and validation report.",
    "sync": "Optional encrypted cloud backup and record-level synchronisation.",
    "backup": "Local backups, restore, integrity checks and portable exports.",
    "settings": "Appearance, PDF engine, privacy, optional AI provider and data location.",
}

SCORE_NOTE = ("This score shows how well your recorded evidence aligns with the stated requirements. "
              "It is not a probability of selection, appointment or security clearance.")
ELIGIBILITY_NOTE = ("Formal eligibility (age, pay level, analogous post, service conditions, documents) is decided "
                    "by the recruiting authority. The software never assesses it.")
RESPONSIBILITY_NOTICE = (
    "You are responsible for deciding what may be stored and disclosed under your employer's rules. Local storage "
    "and cloud copies do not make sensitive official information permissible to keep or share. Mark anything "
    "doubtful as 'Requires review' or 'Confidential'.")
STORAGE_NOTICE = (
    "Your profile database is stored unencrypted in your user folder (protected by your account permissions). "
    "Use full-disk encryption (FileVault on macOS) and encrypted backups for stronger protection.")
RULES_ENGINE_NOTE = ("Suggestions come from the built-in rules engine, which works offline and only rearranges "
                     "facts you recorded. It is not a generative AI model.")
SAMPLE_BANNER = "FICTIONAL SAMPLE WORKSPACE — demonstration data, not a real person."
AI_DISCLOSURE = (
    "When enabled, the selected statement, its recorded facts and the vacancy requirement text are sent to the "
    "provider you configured. Confidential and unconfirmed records are never sent. You see the exact request "
    "before it is sent, and suggestions must be approved.")

WINDOW_TITLE = f"{APP_NAME} — {TAGLINE}"
