"""Contextual help: a '?' button beside form fields, a writing guide for every page and a searchable help window.

The guidance is written for government, defence and scientific careers. It explains what each section is for
and how to word it; it never invents facts — every example is a pattern to adapt to what you actually did.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWhatsThis,
    QWidget,
)

from ris.ui.widgets.common import button, muted


@dataclass
class Guide:
    title: str
    intro: str
    tips: list[str] = field(default_factory=list)
    weak: str = ""      # a weak wording …
    strong: str = ""    # … and the stronger pattern
    keywords: str = ""  # extra search words


#: Topic key → guide. Page keys from the navigation double as topic keys.
GUIDES: dict[str, Guide] = {
    "getting_started": Guide(
        "Getting started",
        "Record each fact about your career once in the Profile pages. Resume Studio then composes any number of "
        "tailored resumes from those facts, so you never retype your history.",
        ["Start with Master Profile (name, contact details, summary), then Experience and Education.",
         "Add statements under each post in Experience: these become the bullet points of your resumes.",
         "Add Projects, Publications, Training and Skills as far as they apply to you.",
         "Open Template Gallery to see every layout with your own data, then pick one in Resume Studio.",
         "Paste a vacancy notice into Job Opportunities to get a resume tailored to its requirements.",
         "Press F1 on any page for its guide, or click the ? beside a field for advice on that field."],
        keywords="start begin first steps how to use"),
    "profile": Guide(
        "Master Profile",
        "Identity, contact details, summaries, areas of expertise and referees. Private particulars (date of "
        "birth, pay, service dates) are kept apart and print only in formats that need them, and only when you "
        "tick them for that resume.",
        ["Give your name exactly as in your service records; add a preferred professional name if it differs.",
         "Write the professional title as a reader outside your office would understand it, for example "
         "'Scientist F — Upper Air Instrumentation' rather than an internal post code.",
         "Use an e-mail address and telephone number you check yourself. Avoid official addresses if your "
         "employer's rules restrict their use for applications.",
         "Record research metrics only from a source you have checked, with the date.",
         "Fill in 'Deputation proforma particulars' once; the DoPT proforma then completes items 1–3 and 8–18."],
        keywords="name contact email phone address personal particulars"),
    "summary": Guide(
        "Professional summary",
        "Three to five lines that tell a selection board who you are, what you have led and what you would bring "
        "to the post. Keep several summaries with different emphasis; each resume picks the best match.",
        ["Open with your level and field, then years of experience and the scale of what you managed.",
         "Name two or three strengths that the target post asks for, in the words of the vacancy circular.",
         "Close with your strongest result or credential (a deployed system, a patent, a doctorate).",
         "Avoid adjectives that cannot be checked: 'dynamic', 'results-oriented', 'passionate'.",
         "Write in the third person without 'I', and keep to facts recorded elsewhere in your profile."],
        weak="Hard-working scientist with vast experience in many areas seeking a challenging position.",
        strong="Scientist F with 18 years in airborne instrumentation and embedded systems; led a 12-member "
               "division that fielded a telemetry system at six stations; PhD candidate in image super-resolution.",
        keywords="objective profile about me headline"),
    "experience": Guide(
        "Experience",
        "Posts you held, additional charges under each post, and the statements that describe your work. "
        "Selection boards and screening software both look here first.",
        ["One record for each post held on a regular basis, with exact month and year of joining and leaving.",
         "Fill in 'Nature of duties' for every post: the deputation proforma prints it in item 7.",
         "Under each post add statements, one result per statement. Begin with a verb: led, designed, "
         "commissioned, evaluated, procured, trained.",
         "Give scale wherever you can: team size, budget, number of sites, accuracy, time saved.",
         "Describe additional charges (nodal officer, committee chair, in-charge) as assignments under the post.",
         "Mark anything restricted as 'Requires review' or 'Confidential'; it is then kept out of resumes."],
        weak="Responsible for procurement work and looking after the lab.",
        strong="Led technical evaluation of 14 tenders worth ₹18 crore through GeM in line with GFR 2017; "
               "all contracts placed within the financial year.",
        keywords="work history employment job post position duties bullet achievement"),
    "education": Guide(
        "Education",
        "Degrees and diplomas, including ongoing and planned qualifications. Government forms ask for the "
        "degree, subject, institution, university and year for each.",
        ["Enter the degree as on the certificate: 'B.Tech. (Electronics and Communication Engineering)'.",
         "Give the grade as awarded (percentage, CGPA with its scale, or division).",
         "For a doctorate in progress set the status to ongoing and add the thesis title and supervisor.",
         "If a qualification is 'equivalent' to one named in a circular, note the authority for equivalence; "
         "the proforma asks for it."],
        keywords="degree qualification university college phd grade"),
    "training": Guide(
        "Training & certifications",
        "Courses, certifications, workshops and seminars. Include those relevant to the post or sponsored by "
        "your department.",
        ["Name the course and the institution as on the certificate, with duration in days or hours.",
         "Record the sponsor if the department nominated you; it shows the confidence placed in you.",
         "Add an outcome line where there is one: what you applied afterwards.",
         "Give the expiry date of certifications that lapse."],
        keywords="course certificate workshop seminar mooc"),
    "research": Guide(
        "Research & publications",
        "Papers, reports and manuscripts, each with its exact status. Never list a submitted paper as published.",
        ["Enter authors in the order printed; your name is highlighted automatically using the author-name "
         "variants in Master Profile.",
         "Set the status precisely: published, accepted, under review, in preparation.",
         "Add the DOI or URL so that a reader can verify the paper.",
         "Record indexing (SCIE, Scopus) only as stated by the journal.",
         "Use the contribution field for what you personally did; boards ask about it at interview."],
        keywords="paper journal conference patent doi citation"),
    "skills": Guide(
        "Skills & technologies",
        "Skills you choose to claim, with your own proficiency and evidence. Claim only what you could discuss "
        "at an interview.",
        ["Use the term the vacancy uses ('MIL-STD-1553', not 'avionics bus') and add other spellings as aliases.",
         "Link each important skill to a project or post as evidence; unsupported skills are flagged.",
         "Group by category so that resumes can show a compact table.",
         "Keep the list current: lower the proficiency of tools you have not used for years."],
        keywords="technology tool software language proficiency"),
    "projects": Guide(
        "Projects & achievements",
        "Projects with the problem, your approach, the result and your own contribution. Boards value a small "
        "number of well-described projects over a long list.",
        ["State the problem in one sentence that a non-specialist member of the board can follow.",
         "Separate what the team did from what you did; fill in 'Individual contribution'.",
         "Give measured results: accuracy, range, endurance, cost, time, units delivered.",
         "For official projects use the 'approved external description' and mark the disclosure status.",
         "Mention the technologies used; they feed the skills evidence and keyword match."],
        weak="Worked on a drone project.",
        strong="Designed the flight-control and telemetry electronics of a 25 kg fixed-wing UAV; led integration "
               "and 40 flight trials; endurance improved from 2 h to 3.5 h.",
        keywords="achievement system development result contribution"),
    "leadership": Guide(
        "Leadership & responsibilities",
        "Committees, additional charges, awards, memberships, patents, talks, supervision and peer review. "
        "For senior posts this section carries much of the case for leadership.",
        ["Give your role (chair, member-secretary, nodal officer) and the authority that constituted the body.",
         "State the outcome: a report submitted, a policy adopted, a procurement completed.",
         "List awards with the awarding body and year; official appreciation counts.",
         "Include patents with their number and status (filed, published, granted)."],
        keywords="committee award membership patent talk supervision chair"),
    "targets": Guide(
        "Career targets",
        "The kinds of post you are aiming at. A target supplies keywords and emphasis so that resumes for that "
        "kind of post rank your most relevant work first.",
        ["Start from a preset such as 'Scientist F/G — deputation' and adjust the keywords.",
         "Set a preferred mode and template; the gallery then recommends that template."],
        keywords="goal preset organisation emphasis"),
    "opportunities": Guide(
        "Job opportunities",
        "Paste or import a vacancy notice. The application extracts the requirements, maps your evidence to "
        "each one and recommends the format the recruiter expects.",
        ["Paste the full text of the circular, including essential and desirable qualifications.",
         "Set the mode of recruitment (deputation, direct, contract): it decides the recommended format.",
         "Check each requirement marked as a gap before you apply; add missing evidence to your profile.",
         "The score shows how well recorded evidence matches the notice. It is not a probability of selection, "
         "and formal eligibility is decided only by the recruiting authority."],
        keywords="vacancy notice circular advertisement requirement eligibility"),
    "studio": Guide(
        "Resume Studio",
        "Compose a resume from your profile: choose a mode (what the document is for), a template (how it "
        "looks), a target or vacancy, then review and export DOCX and PDF.",
        ["Mode decides the sections and their order; template decides typography and layout.",
         "For online portals choose an ATS-safe template: single column, no tables or graphics.",
         "For deputation choose 'Deputation application — DoPT bio-data proforma' and tick the private "
         "particulars to print.",
         "Use the page limit to fit a one- or two-page rule; the least relevant items are trimmed first.",
         "Review every item listed under Checks before exporting."],
        keywords="compose export pdf docx mode template preview"),
    "gallery": Guide(
        "Template Gallery",
        "Every layout available, with a thumbnail, what it is suited to and a preview using your own profile.",
        ["'Recommended for my profile' ranks templates from facts in your profile and states the reason.",
         "ATS-safe templates pass applicant-tracking systems used by online portals.",
         "Two-column and graphical templates suit print, e-mail and interviews, not portals.",
         "To make your own layout, open Resume Library → Templates and edit a copy in the template designer."],
        keywords="templates layout design recommend ats two column graphical"),
    "deputation": Guide(
        "Deputation & UPSC formats",
        "Central Government posts filled on deputation, absorption or short-term contract (including those "
        "advertised through UPSC) ask for the bio-data / CV proforma of DoPT OM dated 02.07.2015, forwarded "
        "through proper channel.",
        ["Fill in the deputation particulars once in Master Profile.",
         "Link the vacancy to the resume so that item 5 sets each requirement against your qualifications.",
         "Enter your own statements for items 5, 6 and 17 under 'Proforma answers' in Resume Studio.",
         "Your office completes and countersigns the employer's certificate; attach APARs for five years, "
         "vigilance clearance, integrity certificate and the statement of penalties.",
         "If the circular encloses its own form, use that form and copy the content across."],
        keywords="upsc dopt proforma bio-data biodata apar vigilance cadre clearance annexure"),
    "letters": Guide(
        "Cover letters",
        "Factual covering letters drafted from your profile and the vacancy.",
        ["Address the authority named in the circular and quote its reference number and date.",
         "Keep to one page: the post applied for, how you meet the essential requirements, enclosures."],
        keywords="covering forwarding letter"),
    "interview": Guide(
        "Interview preparation",
        "Questions drawn from your profile and the vacancy, STAR stories and timed practice.",
        ["Prepare one story for each major project: Situation, Task, Action, Result.",
         "Practise the answer on why you want the post and what you would do in the first year."],
        keywords="star question board piq daf practice"),
    "portals": Guide(
        "Job portals & recruiters",
        "Profile text sized for LinkedIn, Naukri and Indeed, and an ATS readiness check for resume files.",
        ["Run the ATS check on the exported file before uploading it to a portal."],
        keywords="linkedin naukri indeed ats recruiter"),
    "privacy": Guide(
        "What you may disclose",
        "You are responsible for deciding what may be stored and disclosed under your employer's rules.",
        ["Describe classified or sensitive work only in wording your organisation has approved.",
         "Mark doubtful records 'Requires review' or 'Confidential'; they are left out of resumes and "
         "unencrypted backups.",
         "Use the redacted option in Resume Studio for a public version of a resume."],
        keywords="confidential classified sensitive secret security disclosure redact"),
    "settings": Guide(
        "Settings, backup and Fresh Start",
        "Appearance, PDF engine, privacy and data location. 'Fresh Start' empties the current workspace so that "
        "you can begin again.",
        ["Fresh Start first writes a full backup, then removes every record in the workspace.",
         "Restore that backup from Backup & Restore if you change your mind.",
         "Exported files and earlier backups stay on disk; settings are kept."],
        keywords="delete all data reset clear erase start again backup restore theme appearance"),
}

#: Advice for individual form fields: (record kind, field name) → text.
FIELD_GUIDE: dict[tuple[str, str], str] = {
    ("personal", "full_name"): "As in your service book and certificates. The deputation proforma prints it in "
                               "block letters.",
    ("personal", "professional_title"): "What a reader outside your office would call you: level and field.",
    ("personal", "email"): "An address you read yourself. Check your employer's rules before using an official one.",
    ("personal", "phone"): "With the country code, for example +91 98xxx xxxxx.",
    ("personal", "linkedin"): "The full address of your public profile.",
    ("personal", "home_address"): "Printed only in government bio-data and the deputation proforma, when ticked.",
    ("personal", "date_of_birth"): "Proforma item 2. Use the date in your matriculation certificate.",
    ("personal", "date_of_entry_into_service"): "Proforma item 3(i): the date you first joined government service.",
    ("personal", "date_of_retirement"): "Proforma item 3(ii): date of superannuation under the rules.",
    ("personal", "present_pay_level"): "For example 'Level 13A (Pay Matrix, 7th CPC)'.",
    ("summary", "text"): "Three to five lines: level and field, years and scale, two strengths the post asks "
                         "for, one strongest result. No unverifiable adjectives.",
    ("summary", "focus"): "The kind of post this summary is written for; resumes choose the closest match.",
    ("position", "designation"): "The designation in the office order, for example 'Scientist F'.",
    ("position", "organisation"): "Full name of the organisation, then ministry or department if relevant.",
    ("position", "start"): "Month and year of joining the post (2019-03). Exact dates matter in government forms.",
    ("position", "end"): "Leave empty and tick 'current' for the post you hold now.",
    ("position", "summary"): "One or two lines on the scope of the post: what the division does and what you "
                             "answer for.",
    ("position", "nature_of_duties"): "Printed in proforma item 7. Write the duties in detail and bring out the "
                                      "experience the target post asks for.",
    ("position", "pay_level"): "Pay level or scale of the post held on a regular basis (proforma item 7).",
    ("position", "sector"): "Decides how the post is described in government formats and which templates are "
                            "recommended.",
    ("bullet", "text"): "One result per statement. Start with a verb, say what you did, on what scale and with "
                        "what result: 'Commissioned … at 6 stations, cutting data loss from 9% to under 1%.'",
    ("bullet", "metrics"): "Numbers you can defend at interview: counts, percentages, amounts, durations.",
    ("bullet", "outcome"): "What changed because of this work.",
    ("bullet", "involvement"): "Be exact about your role: led, contributed or supported. Boards check this.",
    ("education", "degree"): "As printed on the certificate.",
    ("education", "grade"): "As awarded: percentage, CGPA with scale (8.4/10) or division.",
    ("education", "thesis_title"): "Full title; for a doctorate in progress add the supervisor and status.",
    ("publication", "authors"): "All authors in printed order, separated by commas.",
    ("publication", "status"): "Published, accepted, under review or in preparation — exactly as it stands today.",
    ("publication", "contribution"): "Your own part in the work, in one or two lines.",
    ("skill", "name"): "Use the term a vacancy would use; add other spellings under aliases.",
    ("skill", "proficiency"): "Your honest level. Expert means you could teach it or review others' work.",
    ("skill", "evidence"): "Where you used it: a post, project or certificate. Unsupported skills are flagged.",
    ("project", "title"): "A name a board member outside your field can understand.",
    ("project", "problem"): "The need or problem, in one or two sentences.",
    ("project", "approach"): "How it was solved: the main design decisions.",
    ("project", "results"): "Measured results. Prefer numbers to adjectives.",
    ("project", "individual_contribution"): "What you personally did, as distinct from the team.",
    ("project", "approved_external_description"): "Wording cleared for use outside your organisation. Resumes "
                                                  "use it instead of the internal description.",
    ("activity", "title"): "Name of the committee, award, membership, patent or talk.",
    ("activity", "outcome"): "What came of it: report submitted, procedure adopted, award citation.",
    ("training", "title"): "Course name as on the certificate.",
    ("training", "outcome"): "What you applied afterwards, if anything.",
    ("expertise", "area"): "A specialisation in a few words, for example 'Upper-air instrumentation'.",
    ("expertise", "description"): "Two lines on depth: what you can do in this area and the proof.",
    ("vacancy", "raw_text"): "Paste the whole circular. Requirements are extracted from it.",
    ("vacancy", "recruitment_mode"): "Deputation and absorption use the DoPT proforma; direct recruitment uses "
                                     "an online application supported by a detailed CV.",
    ("reference", "permission_confirmed"): "Tick only after the referee has agreed to be named.",
}

#: Record kind → guide topic, for forms opened outside their own page.
KIND_TOPIC = {"personal": "profile", "summary": "summary", "position": "experience", "assignment": "experience",
              "bullet": "experience", "education": "education", "training": "training", "publication": "research",
              "skill": "skills", "project": "projects", "activity": "leadership", "expertise": "profile",
              "reference": "profile", "career_target": "targets", "vacancy": "opportunities"}


def field_help_text(kind: str, name: str, base: str = "") -> str:
    """Plain help text for a form field: the field's own description plus writing advice."""
    extra = FIELD_GUIDE.get((str(kind), name), "")
    return "\n".join(x for x in (base, extra) if x)


def guide_html(key: str) -> str:
    g = GUIDES.get(key)
    if g is None:
        return ""
    parts = [f"<h2>{escape(g.title)}</h2>", f"<p>{escape(g.intro)}</p>"]
    if g.tips:
        parts.append("<ul>" + "".join(f"<li>{escape(t)}</li>" for t in g.tips) + "</ul>")
    if g.weak and g.strong:
        parts.append(f"<p><b>Weak:</b> <i>{escape(g.weak)}</i><br><b>Stronger:</b> {escape(g.strong)}</p>"
                     "<p><i>The example shows a pattern only. Write what you actually did.</i></p>")
    return "".join(parts)


class HelpButton(QToolButton):
    """Small '?' button that shows help for one field in a pop-up beside it."""

    def __init__(self, title: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HelpButton")
        self.setText("?")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(f"Help: {title}")
        self.setToolTip(f"Help: {title}")
        self.help_title = title
        self.help_text = text
        self.clicked.connect(self.show_help)

    def html(self) -> str:
        body = "<br>".join(escape(line) for line in self.help_text.split("\n") if line)
        return f"<b>{escape(self.help_title)}</b><br>{body}"

    def show_help(self) -> None:
        QWhatsThis.showText(self.mapToGlobal(QPoint(self.width() + 4, 0)), self.html(), self)


class HelpDialog(QDialog):
    """Searchable help window. It is not modal, so it can stay open beside the form being filled in."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Help and writing guide")
        self.setModal(False)
        self.resize(820, 560)
        lay = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search help (for example: deputation, summary, ATS, delete all data)")
        self.search.setAccessibleName("Search help")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.topics = QListWidget()
        self.topics.setAccessibleName("Help topics")
        for key, g in GUIDES.items():
            item = QListWidgetItem(g.title)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.topics.addItem(item)
        self.topics.currentItemChanged.connect(lambda cur, _prev: self._show(cur))
        split.addWidget(self.topics)
        self.view = QTextBrowser()
        self.view.setAccessibleName("Help text")
        self.view.setOpenExternalLinks(False)
        split.addWidget(self.view)
        split.setSizes([250, 570])
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)
        row = QHBoxLayout()
        row.addWidget(muted("Tip: click the ? beside a field for advice on that field. Press F1 for the guide "
                            "to the page you are on."), 1)
        row.addWidget(button("Close", on_click=self.close))
        lay.addLayout(row)
        self.show_topic("getting_started")

    def _show(self, item: QListWidgetItem | None) -> None:
        self.view.setHtml(guide_html(item.data(Qt.ItemDataRole.UserRole)) if item is not None else "")

    def _filter(self, text: str) -> None:
        words = text.lower().split()
        first = None
        for i in range(self.topics.count()):
            item = self.topics.item(i)
            g = GUIDES[item.data(Qt.ItemDataRole.UserRole)]
            hay = " ".join([g.title, g.intro, g.keywords, *g.tips]).lower()
            hidden = bool(words) and not all(w in hay for w in words)
            item.setHidden(hidden)
            if not hidden and first is None:
                first = item
        cur = self.topics.currentItem()
        if first is not None and (cur is None or cur.isHidden()):
            self.topics.setCurrentItem(first)

    def visible_topics(self) -> list[str]:
        return [self.topics.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.topics.count())
                if not self.topics.item(i).isHidden()]

    def show_topic(self, key: str) -> None:
        key = key if key in GUIDES else "getting_started"
        self.search.clear()
        for i in range(self.topics.count()):
            if self.topics.item(i).data(Qt.ItemDataRole.UserRole) == key:
                self.topics.setCurrentRow(i)
                break


def open_help(widget: QWidget | None, topic: str = "") -> HelpDialog:
    """Show the help window on a topic, reusing the main window's single help window when there is one."""
    win = widget.window() if widget is not None else None
    if win is not None and hasattr(win, "show_help"):
        return win.show_help(topic)
    dlg = HelpDialog(win)
    dlg.show_topic(topic)
    dlg.show()
    return dlg


def guide_button(owner: QWidget, topic: str) -> QToolButton:
    """'? Guide' button for a page header."""
    b = QToolButton()
    b.setText("? Guide")
    b.setToolTip("How to fill in this page well (F1)")
    b.setAccessibleName("Open the guide for this page")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(lambda _=False: open_help(owner, topic))
    return b
