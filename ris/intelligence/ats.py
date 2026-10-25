"""Resume document quality and ATS-compatibility checks (document quality is assessed separately from relevance)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ris.composition.ir import ResumeDocument
from ris.intelligence.relevance import RelevanceModel
from ris.rendering.specs import TemplateSpec

_FIRST_PERSON = re.compile(r"\b(?:I|me|my|mine|myself)\b")
_WEAK_START = re.compile(r"^(?:responsible for|worked on|involved in|helped|assisted in|duties included|tasked with)\b", re.I)
_PASSIVE = re.compile(r"\b(?:was|were|been|being)\s+\w+ed\b", re.I)
STANDARD_HEADINGS = {"summary", "experience", "education", "skills", "projects", "publications", "certifications",
                     "training", "awards", "leadership", "languages", "competencies", "profile", "employment",
                     "qualifications", "appointments", "research", "patents", "memberships", "presentations",
                     "particulars", "declaration", "manuscripts", "activities", "domains", "expertise"}


@dataclass
class QualityItem:
    severity: str  # info | warn | problem
    message: str


@dataclass
class QualityReport:
    score: float  # 0..1
    ats_safe_layout: bool
    items: list[QualityItem] = field(default_factory=list)
    keyword_coverage: float | None = None
    missing_keywords: list[str] = field(default_factory=list)

    @property
    def problems(self) -> list[QualityItem]:
        return [i for i in self.items if i.severity == "problem"]


def check_quality(doc: ResumeDocument, spec: TemplateSpec, relevance: RelevanceModel | None = None,
                  page_count: int | None = None) -> QualityReport:
    items: list[QualityItem] = []
    penalties = 0.0
    ats = spec.ats_safe or not spec.uses_tables
    if spec.columns.enabled:
        items.append(QualityItem("warn", "Two-column layout: some applicant tracking systems read columns out of order. "
                                         "Use ATS Minimal for online portals."))
        penalties += 0.05
    elif spec.uses_tables:
        items.append(QualityItem("info", "This template uses tables for layout; prefer ATS Minimal for portals."))
    if not doc.contacts or not any(c.key == "email" for c in doc.contacts):
        items.append(QualityItem("problem", "No email address in the header."))
        penalties += 0.15
    if not any(s.key in ("summary",) for s in doc.sections) and doc.mode not in ("government_biodata",):
        items.append(QualityItem("warn", "No professional summary."))
        penalties += 0.05
    nonstandard = [s.title for s in doc.sections if not s.key.startswith("custom:")
                   and not any(w in s.title.lower() for w in STANDARD_HEADINGS)]
    if nonstandard:
        items.append(QualityItem("info", "Unconventional headings: " + ", ".join(nonstandard)))
    bullets = [b.text for s in doc.sections for e in s.entries for b in e.bullets] + \
              [b.text for s in doc.sections for e in s.entries for c in e.children for b in c.bullets]
    long_b = [b for b in bullets if len(b) > 260]
    if long_b:
        items.append(QualityItem("warn", f"{len(long_b)} bullet(s) are longer than about three lines; tighten them."))
        penalties += min(0.1, 0.02 * len(long_b))
    weak = [b for b in bullets if _WEAK_START.search(b)]
    if weak:
        items.append(QualityItem("warn", f"{len(weak)} bullet(s) start with weak phrases such as 'Responsible for'. "
                                         "Use the rewriting assistant."))
        penalties += min(0.08, 0.02 * len(weak))
    fp = [b for b in bullets if _FIRST_PERSON.search(b)]
    if fp:
        items.append(QualityItem("warn", f"{len(fp)} bullet(s) use first-person pronouns."))
        penalties += 0.03
    passive = [b for b in bullets if _PASSIVE.search(b)]
    if len(passive) > 3:
        items.append(QualityItem("info", f"{len(passive)} bullet(s) use passive voice."))
    exp = doc.section("experience")
    if exp is not None and exp.layout == "entries" and exp.entries and not exp.entries[0].bullets:
        items.append(QualityItem("warn", "Your most recent position has no achievements listed."))
        penalties += 0.05
    if page_count is not None:
        limit = doc.max_pages or {"one_page": 1, "two_pages": 2}.get(doc.length)
        if limit and page_count > limit:
            items.append(QualityItem("problem", f"{page_count} pages exceeds the {limit}-page target."))
            penalties += 0.1
    coverage = None
    missing: list[str] = []
    if relevance is not None and not relevance.is_empty:
        text = "\n".join(doc.text_fragments())
        present = relevance.taxonomy.concepts_in(text)
        wanted = [c for c, w in sorted(relevance.concept_weights.items(), key=lambda kv: (-kv[1], kv[0])) if w >= 0.7]
        if wanted:
            hit = [c for c in wanted if c in present]
            coverage = len(hit) / len(wanted)
            missing = [relevance.taxonomy.label(c) for c in wanted if c not in present][:10]
            if coverage < 0.6:
                items.append(QualityItem("warn", f"The resume mentions {coverage:.0%} of the key vacancy terms. "
                                                 "Missing: " + ", ".join(missing[:6]) +
                                                 ". Add them only where your records support them."))
                penalties += 0.1 * (0.6 - coverage) / 0.6
    if not items:
        items.append(QualityItem("info", "No document-quality issues detected."))
    return QualityReport(score=max(0.0, round(1.0 - penalties, 3)), ats_safe_layout=ats, items=items,
                         keyword_coverage=coverage, missing_keywords=missing)


# --------------------------------------------------------------------------- ATS readiness checklist

ATS_SOURCE = {"title": "ATS resume format 2026 design guide (scale.jobs)",
              "url": "https://scale.jobs/blog/ats-resume-format-2026-design-guide"}
FILE_SOURCE = {"title": "Resume PDF vs Word (Jobrise)", "url": "https://jobrise.io/blog/resume-pdf-vs-word-format"}
COMMON_FONTS = {"calibri", "carlito", "arial", "liberation sans", "helvetica", "georgia", "cambria", "caladea",
                "times new roman", "liberation serif", "garamond", "verdana", "tahoma", "segoe ui", "dejavu sans"}
PLAIN_BULLETS = {"•", "-", "–", "·", "▪"}


@dataclass
class ATSCheck:
    id: str
    title: str
    status: str  # pass | warn | fail
    detail: str
    source: dict | None = None


@dataclass
class ATSReadiness:
    checks: list[ATSCheck]
    keyword_coverage: float | None = None

    @property
    def score(self) -> int:
        if not self.checks:
            return 0
        pts = sum({"pass": 1.0, "warn": 0.5, "fail": 0.0}[c.status] for c in self.checks)
        return round(100 * pts / len(self.checks))

    @property
    def failures(self) -> list[ATSCheck]:
        return [c for c in self.checks if c.status == "fail"]


def _sentences(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])


def ats_readiness(doc: ResumeDocument, spec: TemplateSpec, relevance: RelevanceModel | None = None,
                  files: list | None = None) -> ATSReadiness:
    """Checklist of the formatting rules applicant tracking systems need, with the reason for each.

    Based on published ATS guidance (single column, no tables or graphics for core content, common fonts at
    10–12 pt, 0.5–1 inch margins, standard headings, reverse-chronological order, consistent dates, plain
    bullets, keywords mirrored from the vacancy) and portal file practice.
    """
    from pathlib import Path

    checks: list[ATSCheck] = []

    def add(cid: str, title: str, status: str, detail: str, source: dict | None = ATS_SOURCE) -> None:
        checks.append(ATSCheck(cid, title, status, detail, source))

    if spec.columns.enabled:
        add("columns", "Single column", "fail", "This template uses two columns; parsers may read them out of order. "
            "Use ATS Minimal for online applications.")
    else:
        add("columns", "Single column", "pass", "Content flows in one column.")
    if spec.graphics.enabled or spec.skills.style == "bars":
        add("graphics", "No charts, icons or rating bars", "fail",
            "Charts and skill bars are images or shapes that parsers ignore; the facts are repeated as text, but use "
            "a plain template for portals.")
    elif spec.header.contact_icons:
        add("graphics", "No charts, icons or rating bars", "warn", "Contact icons may be read as stray characters.")
    else:
        add("graphics", "No charts, icons or rating bars", "pass", "No graphics in the layout.")
    if spec.uses_tables and not spec.ats_safe:
        add("tables", "No tables or text boxes for core content", "warn",
            "This template positions content with tables; some parsers drop or scramble table contents.")
    else:
        add("tables", "No tables or text boxes for core content", "pass", "Core content is plain paragraphs.")
    if doc.photo_path:
        add("photo", "No photograph", "warn", "Photographs are ignored by parsers and discouraged by many employers.")
    add("contacts_body", "Contact details in the body, not the page header", "pass" if doc.contacts else "fail",
        "Name and contact details are part of the document body." if doc.contacts else
        "No contact details found.")
    body = spec.fonts.body.lower()
    add("font", "Common, readable font", "pass" if body in COMMON_FONTS else "warn",
        f"Body font: {spec.fonts.body}." if body in COMMON_FONTS else
        f"'{spec.fonts.body}' may not be available to the employer; use Calibri, Arial or Georgia.")
    size = spec.fonts.body_size * (doc.font_scale or 1.0)
    if 10 <= size <= 12:
        add("font_size", "Body text 10–12 pt", "pass", f"Body text is {size:.1f} pt.")
    else:
        add("font_size", "Body text 10–12 pt", "warn", f"Body text is {size:.1f} pt; use 10–12 pt.")
    margins = [spec.page.margin_left_mm, spec.page.margin_right_mm, spec.page.margin_top_mm, spec.page.margin_bottom_mm]
    if all(12.0 <= m <= 26.0 for m in margins):
        add("margins", "Margins 0.5–1 inch", "pass", "Margins are between 12.7 and 25.4 mm.")
    else:
        add("margins", "Margins 0.5–1 inch", "warn", "Some margins are outside 12.7–25.4 mm (0.5–1 inch).")
    nonstandard = [s.title for s in doc.sections if not s.key.startswith("custom:") and s.key not in ("tips",)
                   and not any(w in s.title.lower() for w in STANDARD_HEADINGS)]
    add("headings", "Standard section headings", "warn" if nonstandard else "pass",
        ("Unconventional headings may be misfiled: " + ", ".join(nonstandard)) if nonstandard else
        "Headings use standard names (Summary, Experience, Education, Skills …).")
    exp = doc.section("experience")
    if exp is not None and exp.entries:
        keys = [e.sort_key for e in exp.entries if e.sort_key]
        ordered = all(a >= b for a, b in zip(keys, keys[1:], strict=False))
        add("chronology", "Reverse-chronological experience", "pass" if ordered else "warn",
            "Most recent position first." if ordered else "Positions are not in reverse-chronological order.")
        styles = {re.sub(r"\d", "9", e.date_text.split("–")[0].strip()) for e in exp.entries if e.date_text}
        add("dates", "Consistent date format", "pass" if len(styles) <= 2 else "warn",
            "Dates use one format." if len(styles) <= 2 else "Dates mix formats; keep one format throughout.")
        recent = len(exp.entries[0].bullets)
        older = [len(e.bullets) for e in exp.entries[1:] if e.bullets]
        if recent and not (3 <= recent <= 7):
            add("bullets_recent", "4–6 bullets for the recent role", "warn",
                f"Your most recent role has {recent} bullet(s).")
        elif recent:
            add("bullets_recent", "4–6 bullets for the recent role", "pass", f"{recent} bullets.")
        if older and max(older) > 5:
            add("bullets_older", "2–3 bullets for older roles", "warn",
                "Some older roles have more than five bullets; shorten them.")
    glyph = (spec.entry.bullet_glyph or "•").strip()
    add("bullet_glyph", "Plain bullets", "pass" if glyph in PLAIN_BULLETS else "warn",
        f"Bullet character '{glyph}'." + ("" if glyph in PLAIN_BULLETS else " Use a plain round bullet."))
    summ = doc.section("summary")
    if summ is not None and summ.paragraphs:
        n = _sentences(" ".join(summ.paragraphs))
        add("summary", "Summary of 3–4 sentences", "pass" if 2 <= n <= 5 else "warn", f"Your summary has {n} sentence(s).")
    elif doc.mode != "government_biodata":
        add("summary", "Summary of 3–4 sentences", "warn", "No professional summary.")
    coverage = None
    if relevance is not None and not relevance.is_empty:
        text = "\n".join(doc.text_fragments())
        present = relevance.taxonomy.concepts_in(text)
        wanted = [c for c, w in sorted(relevance.concept_weights.items(), key=lambda kv: (-kv[1], kv[0])) if w >= 0.5]
        if wanted:
            hit = [c for c in wanted if c in present]
            coverage = len(hit) / len(wanted)
            missing = [relevance.taxonomy.label(c) for c in wanted if c not in present][:8]
            status = "pass" if coverage >= 0.75 else ("warn" if coverage >= 0.5 else "fail")
            add("keywords", "Vacancy keywords mirrored (target 75%+)", status,
                f"{coverage:.0%} of the vacancy's key terms appear." + (
                    f" Missing: {', '.join(missing)} — add them only where your records support them." if missing
                    else ""))
    for f in files or []:
        path = Path(f)
        ext = path.suffix.lower()
        if ext not in (".docx", ".pdf", ".doc"):
            add(f"file_type:{path.name}", f"File type ({path.name})", "fail", "Use DOCX or a text-based PDF.",
                FILE_SOURCE)
            continue
        size_mb = path.stat().st_size / (1024 * 1024)
        add(f"file_size:{path.name}", f"File size ({path.name})", "pass" if size_mb <= 2 else "fail",
            f"{size_mb * 1024:.0f} KB" + ("" if size_mb <= 2 else " — over the 2 MB limit used by Naukri and LinkedIn."),
            FILE_SOURCE)
    return ATSReadiness(checks=checks, keyword_coverage=coverage)
