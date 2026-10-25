"""Interview preparation: question bank, questions generated from your profile, STAR story checks and
consistency checks for personal questionnaires (SSB PIQ, DAF-style forms).

Everything here works offline and only rearranges what you recorded. Generated questions are prompts for
practice; they never become facts and are never printed in resumes.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from ris.composition.ir import IREntry, IRSection, ResumeDocument
from ris.domain import dates
from ris.domain.enums import (
    Confidentiality,
    EvidenceStatus,
    Proficiency,
    PublicationStatus,
    QuestionCategory,
    QuestionnaireType,
    RecordKind,
    RecruitmentMode,
    label,
)
from ris.domain.models import InterviewStory, Questionnaire
from ris.resources import config_dir
from ris.util import utc_now_iso

#: Typical conversational speaking rate used to estimate answer length (words per minute).
SPEAKING_WPM = 140
#: Recommended share of a STAR answer for each part (The Interview Guys, 2026).
STAR_SHARES = {"situation": 0.20, "task": 0.15, "action": 0.50, "result": 0.15}
STAR_TARGET_SECONDS = (60, 90)


@dataclass
class Question:
    category: str
    text: str
    hint: str = ""
    source: str = ""  # a source id from the bank, or "profile", "vacancy", "organisation", "questionnaire"
    record_ids: list[str] = field(default_factory=list)

    @property
    def personalised(self) -> bool:
        return self.source in ("profile", "vacancy", "organisation", "questionnaire")

    @property
    def category_label(self) -> str:
        return label(QuestionCategory(self.category))


@dataclass
class QuestionBank:
    questions: list[Question]
    tips: dict[str, dict[str, Any]]
    sources: dict[str, dict[str, str]]

    def by_category(self, category: str) -> list[Question]:
        return [q for q in self.questions if q.category == category]

    def source_for(self, q: Question) -> dict[str, str] | None:
        return self.sources.get(q.source)


@lru_cache(maxsize=4)
def load_bank(path: str | None = None) -> QuestionBank:
    raw = json.loads(Path(path or (config_dir() / "interview_questions.json")).read_text(encoding="utf-8"))
    sources = {s["id"]: {"title": s["title"], "url": s["url"]} for s in raw.get("sources", [])}
    questions = []
    for q in raw.get("questions", []):
        cat = q.get("category", "personal")
        if cat not in QuestionCategory._value2member_map_:
            continue
        questions.append(Question(category=cat, text=q["text"], hint=q.get("hint", ""), source=q.get("source", "")))
    return QuestionBank(questions=questions, tips=raw.get("tips", {}), sources=sources)


# --------------------------------------------------------------------------- personalised questions


def _year(text: str) -> str:
    pd = dates.parse_or_none(text)
    return str(pd.year) if pd else ""


def _month_index(text: str, end: bool = False) -> int | None:
    pd = dates.parse_or_none(text)
    if pd is None:
        return None
    month = pd.month or (12 if end else 1)
    return pd.year * 12 + month


def personalised_questions(snap, *, vacancy=None, analysis=None, organisation: dict | None = None,
                           questionnaire: Questionnaire | None = None, include_confidential: bool = False,
                           today: date | None = None) -> list[Question]:
    """Questions an interview board is likely to ask about *your* record.

    ``snap`` is a ProfileSnapshot; ``analysis`` a VacancyAnalysis; ``organisation`` an organisation profile
    from the career presets. Confidential records are left out unless asked for.
    """
    today = today or date.today()
    out: list[Question] = []

    def ok(rec) -> bool:
        return include_confidential or snap.effective_confidentiality(rec) != Confidentiality.CONFIDENTIAL

    def add(category: QuestionCategory, text: str, hint: str = "", source: str = "profile",
            ids: list[str] | None = None) -> None:
        out.append(Question(category=category.value, text=text, hint=hint, source=source, record_ids=ids or []))

    # Career path ----------------------------------------------------------------
    positions = [p for p in snap.of(RecordKind.POSITION) if ok(p) and (p.data.designation or p.data.organisation)]
    positions.sort(key=lambda p: dates.range_sort_key(p.data.start, p.data.end, p.data.is_current), reverse=True)
    for p in positions[:3]:
        d = p.data
        role = d.designation or "your role"
        org = d.organisation or "your organisation"
        add(QuestionCategory.PERSONAL, f"Walk us through your responsibilities as {role} at {org}.",
            "Cover scope, team, budget or equipment handled, and one result you are proud of.", ids=[p.id])
        add(QuestionCategory.PROJECTS, f"What was your most significant contribution as {role}?",
            "Use a STAR story and quantify only with verified figures.", ids=[p.id])
    chronological = list(reversed(positions))
    for older, newer in zip(chronological, chronological[1:], strict=False):
        o, n = older.data, newer.data
        if o.organisation and n.organisation and o.organisation != n.organisation:
            when = _year(n.start)
            add(QuestionCategory.PERSONAL,
                f"Why did you move from {o.organisation} to {n.organisation}{' in ' + when if when else ''}?",
                "Give a positive, honest reason focused on growth or contribution.", ids=[older.id, newer.id])
        end_i, start_i = _month_index(o.end, end=True), _month_index(n.start)
        if end_i is not None and start_i is not None and start_i - end_i > 6 and not o.is_current:
            add(QuestionCategory.PERSONAL,
                f"What did you do between {dates.format_date(o.end)} and {dates.format_date(n.start)}?",
                "Answer briefly and factually; boards mainly want to see that you can account for the time.",
                ids=[older.id, newer.id])
    for a in snap.of(RecordKind.ASSIGNMENT):
        if ok(a) and a.data.title:
            add(QuestionCategory.LEADERSHIP,
                f"How did you balance your additional responsibility as {a.data.title} with your main duties?",
                ids=[a.id])
            break

    # Projects -------------------------------------------------------------------
    projects = [p for p in snap.of(RecordKind.PROJECT) if ok(p) and p.data.title]
    if analysis is not None and not analysis.relevance.is_empty:
        projects.sort(key=lambda p: -analysis.relevance.score_record(p, snap.kids(p.id, RecordKind.BULLET)))
    else:
        projects.sort(key=lambda p: dates.range_sort_key(p.data.start, p.data.end, p.data.is_current), reverse=True)
    for p in projects[:4]:
        d = p.data
        add(QuestionCategory.PROJECTS, f"Explain '{d.title}' to a non-specialist in two minutes.", ids=[p.id])
        add(QuestionCategory.PROJECTS,
            f"In '{d.title}', what was your individual contribution, as distinct from the team's?",
            "Boards probe for 'I' versus 'we'. Name the decisions and work that were yours.", ids=[p.id])
        if d.limitations:
            add(QuestionCategory.PROJECTS, f"What were the limitations of '{d.title}', and how would you address them?",
                ids=[p.id])

    # Research -------------------------------------------------------------------
    pubs = [x for x in snap.of(RecordKind.PUBLICATION) if ok(x) and x.data.title]
    pubs.sort(key=lambda x: x.data.date or "", reverse=True)
    for x in pubs[:4]:
        d = x.data
        if d.status == "published":
            add(QuestionCategory.RESEARCH, f"What is the main contribution of your paper '{d.title}', and who uses it?",
                ids=[x.id])
        elif d.status in ("accepted", "under_review", "submitted"):
            add(QuestionCategory.RESEARCH,
                f"Your paper '{d.title}' is {label(PublicationStatus(d.status)).lower()}. "
                "What is new compared with earlier work, and what have reviewers questioned?",
                "Describe the status exactly as it is — never as published.", ids=[x.id])
        else:
            add(QuestionCategory.RESEARCH, f"What stage is '{d.title}' at, and what remains to be done?", ids=[x.id])
    for e in snap.of(RecordKind.EDUCATION):
        if not ok(e):
            continue
        d = e.data
        if d.status == "ongoing" and d.level == "doctorate":
            add(QuestionCategory.MOTIVATION,
                "How will you balance your doctoral research with the responsibilities of this post?", ids=[e.id])
        if d.thesis_title:
            add(QuestionCategory.RESEARCH, f"Summarise your thesis '{d.thesis_title}' and its practical relevance.",
                ids=[e.id])

    # Skills and training ----------------------------------------------------------
    strong = [s for s in snap.of(RecordKind.SKILL) if ok(s)
              and s.data.proficiency in (Proficiency.ADVANCED.value, Proficiency.EXPERT.value)]
    for s in strong[:3]:
        add(QuestionCategory.TECHNICAL,
            f"You rate yourself {label(Proficiency(s.data.proficiency)).lower()} in {s.data.name}. "
            "Give an example that justifies that rating.",
            "Expect follow-up questions that test the depth of a self-rating.", ids=[s.id])
    trainings = [t for t in snap.of(RecordKind.TRAINING) if ok(t) and t.data.title and t.data.status != "planned"
                 and t.data.training_type not in ("seminar", "language_test", "licence")]
    trainings.sort(key=lambda t: t.data.end or t.data.start or "", reverse=True)
    for t in trainings[:3]:
        add(QuestionCategory.TECHNICAL, f"How have you applied what you learned in '{t.data.title}'?", ids=[t.id])

    # Leadership -----------------------------------------------------------------
    acts = [a for a in snap.of(RecordKind.ACTIVITY) if ok(a) and a.data.title
            and a.data.activity_type in ("leadership", "committee", "workshop_management", "mentoring",
                                         "project_coordination", "procurement")]
    for a in acts[:3]:
        add(QuestionCategory.LEADERSHIP, f"As {a.data.title}, what was the hardest decision you had to take?",
            ids=[a.id])

    # Vacancy --------------------------------------------------------------------
    if analysis is not None:
        verified, gaps = [], []
        for r in analysis.results:
            cat = r.requirement.category
            if cat in ("eligibility", "documentation"):
                continue
            if r.status == EvidenceStatus.VERIFIED:
                verified.append(r)
            elif r.status in (EvidenceStatus.NOT_FOUND, EvidenceStatus.PARTIAL):
                gaps.append(r)
        for r in verified[:5]:
            req = r.requirement.text.rstrip(".")
            add(QuestionCategory.TECHNICAL, f"The post asks for: {req}. Give an example from your work that shows it.",
                source="vacancy", ids=list(r.possessed_sources))
        for r in gaps[:3]:
            req = r.requirement.text.rstrip(".")
            add(QuestionCategory.MOTIVATION, f"The post asks for: {req}. How would you close this gap?",
                "Acknowledge the gap honestly and show a concrete plan.", source="vacancy")
    if vacancy is not None and getattr(vacancy, "recruitment_mode", "") == RecruitmentMode.DEPUTATION.value:
        add(QuestionCategory.GOVERNMENT,
            "Why are you seeking deputation, and what will you bring back to your parent department?",
            source="vacancy")

    # Organisation ---------------------------------------------------------------
    if organisation:
        name = organisation.get("name", "this organisation")
        add(QuestionCategory.ORGANISATION, f"Why do you want to work with {name}?", source="organisation")
        domains = organisation.get("domains", [])[:3]
        if domains:
            add(QuestionCategory.ORGANISATION,
                f"What do you know about {name}'s work in {', '.join(domains)}, and where would you contribute?",
                source="organisation")

    # Questionnaire --------------------------------------------------------------
    if questionnaire is not None:
        q = questionnaire
        for h in q.hobbies[:3]:
            add(QuestionCategory.QUESTIONNAIRE, f"You list {h} as an interest. What have you done or read about it "
                                                "recently?", "Only list genuine interests.", source="questionnaire")
        for s in q.sports[:2]:
            if s.activity:
                add(QuestionCategory.QUESTIONNAIRE,
                    f"What was your role in {s.activity}{' at ' + s.level + ' level' if s.level else ''}, and what did "
                    "it teach you about teamwork?", source="questionnaire")
        for r in q.responsibilities[:2]:
            add(QuestionCategory.QUESTIONNAIRE, f"What did you learn from being {r}?", source="questionnaire")
        for at in q.previous_attempts[:2]:
            if at.examination:
                add(QuestionCategory.QUESTIONNAIRE,
                    f"Tell us about your previous attempt at {at.examination}{' (' + at.year + ')' if at.year else ''}. "
                    "What has changed since then?", source="questionnaire")
        if q.ncc:
            add(QuestionCategory.QUESTIONNAIRE, "What did NCC teach you, and how have you used it since?",
                source="questionnaire")
        if q.service_choice:
            add(QuestionCategory.QUESTIONNAIRE, f"Why have you chosen {first_words(q.service_choice, 12)}?",
                source="questionnaire")

    seen: set[str] = set()
    unique = []
    for qn in out:
        k = qn.text.casefold()
        if k not in seen:
            seen.add(k)
            unique.append(qn)
    return unique


def first_words(text: str, n: int) -> str:
    words = text.split()
    return " ".join(words[:n]) + ("…" if len(words) > n else "")


def practice_set(questions: list[Question], categories: set[str] | None = None, n: int = 10,
                 seed: int | None = None) -> list[Question]:
    """A shuffled practice round, biased towards personalised questions."""
    pool = [q for q in questions if not categories or q.category in categories]
    rng = random.Random(seed)
    personal = [q for q in pool if q.personalised]
    general = [q for q in pool if not q.personalised]
    rng.shuffle(personal)
    rng.shuffle(general)
    take_p = min(len(personal), max(n // 2, n - len(general)))
    chosen = personal[:take_p] + general[: n - take_p]
    rng.shuffle(chosen)
    return chosen


# --------------------------------------------------------------------------- STAR stories

_WORD = re.compile(r"[\w'’-]+")
_I = re.compile(r"\b(?:I|my|me|myself)\b")
_WE = re.compile(r"\b(?:we|our|us)\b", re.IGNORECASE)
_NUMBER = re.compile(r"\d")


@dataclass
class StoryAnalysis:
    words: dict[str, int]
    total_words: int
    shares: dict[str, float]
    seconds: int
    i_count: int
    we_count: int
    issues: list[str] = field(default_factory=list)
    good: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def analyse_story(story: InterviewStory | dict) -> StoryAnalysis:
    s = story if isinstance(story, InterviewStory) else InterviewStory.model_validate(story)
    parts = {k: getattr(s, k) or "" for k in STAR_SHARES}
    words = {k: len(_WORD.findall(v)) for k, v in parts.items()}
    total = sum(words.values())
    shares = {k: (words[k] / total if total else 0.0) for k in words}
    seconds = round(total / SPEAKING_WPM * 60)
    i_count = len(_I.findall(parts["action"] + " " + parts["task"]))
    we_count = len(_WE.findall(parts["action"] + " " + parts["task"]))
    issues: list[str] = []
    good: list[str] = []
    for k in STAR_SHARES:
        if not parts[k].strip():
            issues.append(f"Add the {k.title()} part.")
    if total:
        if shares["action"] < 0.35 and parts["action"].strip():
            issues.append(f"Action is {shares['action']:.0%} of the story; aim for about half — describe what you did.")
        if shares["situation"] > 0.35:
            issues.append(f"Situation is {shares['situation']:.0%} of the story; trim the background.")
        if seconds > 120:
            issues.append(f"About {seconds} seconds when spoken; aim for {STAR_TARGET_SECONDS[0]}–"
                          f"{STAR_TARGET_SECONDS[1]} seconds.")
        elif seconds < 30 and all(parts.values()):
            issues.append(f"About {seconds} seconds when spoken; add specific detail to the Action and Result.")
        if we_count > i_count:
            issues.append("You say 'we' more than 'I' in the Task and Action; make your own contribution clear.")
        if parts["result"].strip() and not _NUMBER.search(parts["result"]):
            good.append("Consider adding a measurable outcome to the Result — only if you can verify it.")
        if STAR_TARGET_SECONDS[0] <= seconds <= STAR_TARGET_SECONDS[1]:
            good.append(f"Length is about {seconds} seconds — within the recommended range.")
    return StoryAnalysis(words=words, total_words=total, shares=shares, seconds=seconds, i_count=i_count,
                         we_count=we_count, issues=issues, good=good)


# --------------------------------------------------------------------------- questionnaires


@dataclass
class ConsistencyIssue:
    level: str  # warn | info
    area: str
    message: str


_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall((text or "").lower()) if len(t) > 1 or t.isdigit()}


def _degree_key(text: str) -> str:
    return re.sub(r"[^a-z]", "", (text or "").lower())


def check_questionnaire(q: Questionnaire, snap) -> list[ConsistencyIssue]:
    """Compare a questionnaire with the profile. Boards cross-check these forms, so inconsistencies matter."""
    issues: list[ConsistencyIssue] = []
    blanks = []
    for name, title in (("place_of_birth", "place of birth"), ("father", "father's details"),
                        ("mother", "mother's details"), ("service_choice", "choice of service/post"),
                        ("reasons", "reasons for applying")):
        if not getattr(q, name):
            blanks.append(title)
    if not q.education:
        blanks.append("education")
    if not q.hobbies:
        blanks.append("hobbies and interests")
    if blanks:
        issues.append(ConsistencyIssue("warn", "Completeness",
                                       "Not yet filled: " + ", ".join(blanks) + ". Leave no section blank."))
    degrees = [e for e in snap.of(RecordKind.EDUCATION)
               if e.data.qualification_type in ("degree", "diploma") and e.data.status == "completed" and e.data.degree]
    for e in degrees:
        key = _degree_key(e.data.degree)
        row = next((r for r in q.education if key and key in _degree_key(r.examination)), None)
        if row is None:
            issues.append(ConsistencyIssue("warn", "Education",
                                           f"Your profile lists {e.data.degree} but the questionnaire does not."))
            continue
        year = _year(e.data.end)
        if year and row.year and year not in row.year:
            issues.append(ConsistencyIssue("warn", "Education",
                                           f"{e.data.degree}: the questionnaire says {row.year}, your profile says {year}."))
        if e.data.grade and row.result and not (_tokens(e.data.grade) & _tokens(row.result)):
            issues.append(ConsistencyIssue("warn", "Education",
                                           f"{e.data.degree}: result '{row.result}' differs from '{e.data.grade}' in "
                                           "your profile. Use exactly what your certificate says."))
    known = [e for e in snap.of(RecordKind.EDUCATION) if e.data.degree and e.data.status != "planned"]
    for r in q.education:
        if r.examination and not any(_degree_key(e.data.degree) and _degree_key(e.data.degree) in
                                     _degree_key(r.examination) for e in known) and \
                not re.search(r"\b(10|12|x|xii|matric|secondary|hsc|ssc)\b", r.examination.lower()):
            issues.append(ConsistencyIssue("info", "Education",
                                           f"'{r.examination}' is not in your profile; add it so your resume and "
                                           "questionnaire agree."))
    langs_profile = {x.lower() for x in snap.personal_data.languages}
    langs_q = {x.lower() for x in q.languages}
    if langs_profile and langs_q and langs_profile != langs_q:
        only_p = sorted(langs_profile - langs_q)
        only_q = sorted(langs_q - langs_profile)
        bits = []
        if only_p:
            bits.append("missing here: " + ", ".join(only_p))
        if only_q:
            bits.append("not in your profile: " + ", ".join(only_q))
        issues.append(ConsistencyIssue("info", "Languages", "Languages differ — " + "; ".join(bits) + "."))
    titles = [a.data.title for a in snap.of(RecordKind.ASSIGNMENT) if a.data.title] + \
             [a.data.title for a in snap.of(RecordKind.ACTIVITY) if a.data.title]
    for resp in q.responsibilities:
        rt = _tokens(resp)
        if rt and not any(len(rt & _tokens(t)) >= max(1, min(2, len(rt))) for t in titles):
            issues.append(ConsistencyIssue("info", "Responsibilities",
                                           f"'{resp}' is not recorded in your profile; add it as an activity or "
                                           "concurrent responsibility so the two agree."))
    return issues


def autofill_questionnaire(q: Questionnaire, snap) -> Questionnaire:
    """Fill empty questionnaire sections from the profile (education, languages, responsibilities)."""
    data = q.model_dump()
    if not q.education:
        rank = {"doctorate": 0, "masters": 1, "bachelors": 2, "diploma": 3, "higher_secondary": 4, "secondary": 5}
        edus = [e for e in snap.of(RecordKind.EDUCATION)
                if e.data.qualification_type in ("degree", "diploma") and e.data.status != "planned"]
        edus.sort(key=lambda e: rank.get(e.data.level, 9))
        data["education"] = [{
            "examination": ", ".join(x for x in (e.data.degree, e.data.discipline) if x),
            "institution": e.data.institution, "board": e.data.university, "year": _year(e.data.end) or
            ("ongoing" if e.data.status == "ongoing" else ""), "result": e.data.grade,
            "subjects": e.data.specialisation,
        } for e in edus]
    if not q.languages:
        data["languages"] = list(snap.personal_data.languages)
    if not q.responsibilities:
        resp = [a.data.title for a in snap.of(RecordKind.ASSIGNMENT) if a.data.title]
        resp += [a.data.title for a in snap.of(RecordKind.ACTIVITY)
                 if a.data.title and a.data.activity_type in ("leadership", "committee", "workshop_management",
                                                              "project_coordination", "mentoring")]
        data["responsibilities"] = resp[:10]
    return Questionnaire.model_validate(data)


# --------------------------------------------------------------------------- printable pack


def interview_pack(snap, *, questions: list[Question], answers: list, stories: list,
                   questionnaire: Questionnaire | None = None, title: str = "", template_id: str = "ats_minimal",
                   template_version: str = "", is_sample: bool = False) -> ResumeDocument:
    """A private preparation document: your questions, answer notes, STAR stories and questionnaire."""
    p = snap.personal_data
    bank = load_bank()
    sections: list[IRSection] = []
    by_cat: dict[str, list[str]] = {}
    for q in questions:
        by_cat.setdefault(q.category, []).append(q.text)
    for cat, texts in by_cat.items():
        sections.append(IRSection(key=f"q_{cat}", title=f"Questions — {label(QuestionCategory(cat))}",
                                  layout="list", items=texts))
    if answers:
        entries = []
        for a in answers:
            d = a.data
            e = IREntry(id=a.id, kind="answer", title=d.question, subtitle=label(QuestionCategory(d.category)),
                        description=d.answer)
            if d.confidence:
                e.meta.append(("Confidence", f"{d.confidence}/5"))
            entries.append(e)
        sections.append(IRSection(key="answers", title="Prepared Answers", layout="entries", entries=entries))
    if stories:
        entries = []
        for s in stories:
            d = s.data
            e = IREntry(id=s.id, kind="story", title=d.title or "Story", subtitle=", ".join(d.competencies))
            for part in ("situation", "task", "action", "result"):
                text = getattr(d, part)
                if text:
                    e.meta.append((part.title(), text))
            entries.append(e)
        sections.append(IRSection(key="stories", title="STAR Stories", layout="entries", entries=entries))
    if questionnaire is not None:
        rows = [(lbl, val) for lbl, val in (
            ("Form", label(QuestionnaireType(questionnaire.form_type))),
            ("Hobbies and interests", ", ".join(questionnaire.hobbies)),
            ("Languages", ", ".join(questionnaire.languages)),
            ("Positions of responsibility", "; ".join(questionnaire.responsibilities)),
            ("NCC", questionnaire.ncc), ("Choice of service / post", questionnaire.service_choice),
            ("Why you want to join", questionnaire.reasons)) if val]
        if rows:
            sections.append(IRSection(key="questionnaire", title="Questionnaire Summary", layout="entries",
                                      entries=[IREntry(id=f"qn{i}", kind="questionnaire", title=lbl, description=val)
                                               for i, (lbl, val) in enumerate(rows)]))
    tips = []
    for key in ("star", "board", "questionnaire"):
        t = bank.tips.get(key)
        if t:
            tips.extend(t["points"])
    if tips:
        sections.append(IRSection(key="tips", title="Reminders", layout="list", items=tips))
    name = p.display_name() or "Interview preparation"
    return ResumeDocument(
        doc_type="interview_pack", name=name, headline=title or "Interview preparation pack", sections=sections,
        template_id=template_id, template_version=template_version, mode="interview_pack", length="full",
        generated_at=utc_now_iso(), is_sample=is_sample,
        footer_note="Private preparation notes — not for submission",
        metadata={"title": f"{name} — {title or 'Interview preparation'}", "author": name},
    )


def questionnaire_document(q: Questionnaire, snap, *, template_id: str = "government_cv",
                           template_version: str = "", is_sample: bool = False) -> ResumeDocument:
    """A printable copy of your questionnaire for your own reference (it contains private details)."""
    from ris.composition.ir import IRTable

    p = snap.personal_data
    sections: list[IRSection] = []

    def pairs(key: str, title: str, items: list[tuple[str, str]]) -> None:
        rows = [[k, v] for k, v in items if v]
        if rows:
            sections.append(IRSection(key=key, title=title, layout="table",
                                      table=IRTable(header=["Item", "Details"], rows=rows, col_widths=[0.3, 0.7])))

    def table(key: str, title: str, header: list[str], rows: list[list[str]], widths: list[float]) -> None:
        rows = [r for r in rows if any(c for c in r)]
        if rows:
            sections.append(IRSection(key=key, title=title, layout="table",
                                      table=IRTable(header=header, rows=rows, col_widths=widths)))

    pairs("q_personal", "Personal Details", [("Name", p.full_name or p.display_name()),
                                              ("Place of birth", q.place_of_birth), ("Home town", q.home_town),
                                              ("Permanent address", q.permanent_address),
                                              ("Present address", q.present_address)])
    pairs("q_family", "Family", [("Father", q.father), ("Mother", q.mother), ("Siblings", q.siblings)])
    table("q_education", "Education", ["Examination", "Institution", "Board / University", "Year", "Result", "Subjects"],
          [[r.examination, r.institution, r.board, r.year, r.result, r.subjects] for r in q.education],
          [0.2, 0.22, 0.18, 0.1, 0.12, 0.18])
    table("q_sports", "Sports", ["Game / sport", "Level", "Position / role", "Year", "Achievement"],
          [[r.activity, r.level, r.role, r.year, r.achievement] for r in q.sports], [0.22, 0.16, 0.18, 0.1, 0.34])
    table("q_extra", "Extra-curricular Activities", ["Activity", "Level", "Role", "Year", "Achievement"],
          [[r.activity, r.level, r.role, r.year, r.achievement] for r in q.extracurricular],
          [0.22, 0.16, 0.18, 0.1, 0.34])
    pairs("q_activities", "Interests and Responsibilities", [
        ("NCC", q.ncc), ("Hobbies and interests", ", ".join(q.hobbies)),
        ("Positions of responsibility", "; ".join(q.responsibilities)), ("Languages known", ", ".join(q.languages))])
    table("q_attempts", "Previous Attempts / Interviews", ["Examination / interview", "Year", "Centre", "Result"],
          [[r.examination, r.year, r.centre, r.result] for r in q.previous_attempts], [0.4, 0.12, 0.24, 0.24])
    pairs("q_pref", "Preferences", [("Choice of service / post", q.service_choice), ("Why you want to join", q.reasons)])
    name = p.display_name() or "Questionnaire"
    return ResumeDocument(
        doc_type="questionnaire", name=name, headline=q.title or label(QuestionnaireType(q.form_type)),
        title_line="PERSONAL QUESTIONNAIRE — PRIVATE COPY", sections=sections, template_id=template_id,
        template_version=template_version, mode="questionnaire", length="full", generated_at=utc_now_iso(),
        is_sample=is_sample, footer_note="Private copy for your own preparation",
        metadata={"title": f"{name} — {q.title or 'Personal questionnaire'}", "author": name},
    )
