"""Requirement extraction from vacancy notices (rules-based, offline).

The vacancy text is untrusted data: it is only parsed into requirement
records. Nothing in it is executed, and it cannot change settings or
classifications (VAC-13).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ris.domain.enums import RecruitmentMode, RequirementCategory
from ris.domain.models import Requirement, Vacancy
from ris.intelligence.taxonomy import Taxonomy, default_taxonomy
from ris.services.duplicates import similarity

MAX_TEXT = 60_000
MAX_ITEM_LEN = 600

_HEADING_RULES: list[tuple[str, re.Pattern]] = [
    ("essential", re.compile(r"^(?:essential|mandatory|minimum)\b.*\b(?:qualifications?|requirements?|criteria|"
                             r"eligibility|educational)\b|^(?:essential|mandatory)$", re.I)),
    ("desirable", re.compile(r"^(?:desirable|preferred|preferable|desired)\b", re.I)),
    ("experience", re.compile(r"^(?:work\s+)?experience(?:\s+(?:required|requirements?|criteria))?$", re.I)),
    ("eligibility", re.compile(r"^(?:eligibility(?:\s+conditions?|\s+criteria)?|who can apply|age(?:\s+limit)?|"
                               r"pay(?:\s+(?:scale|level|matrix))?|mode of recruitment|period of deputation|"
                               r"terms and conditions|conditions of eligibility)$", re.I)),
    ("documents", re.compile(r"^(?:documents?(?:\s+to\s+be\s+(?:enclosed|attached|submitted))?|enclosures?|"
                             r"how to apply|application procedure|procedure for applying)$", re.I)),
    ("duties", re.compile(r"^(?:duties(?:\s+and\s+responsibilities)?|job description|(?:key\s+)?responsibilities|"
                          r"nature of (?:duties|work)|job profile|role(?:\s+description)?|scope of work)$", re.I)),
    ("research", re.compile(r"^(?:research(?:\s+(?:experience|requirements?))?|publications?)$", re.I)),
]
_HEAD_WITH_COLON = re.compile(r"^\s*(?:\d{1,2}[.)]\s*)?(?P<head>[A-Za-z][A-Za-z &/()'.-]{1,70}?)\s*[:\-\u2013]\s*(?P<rest>.*)$")


def _heading_name(text: str) -> str | None:
    t = " ".join(text.strip().rstrip(":").split())
    if not t or any(ch.isdigit() for ch in t) or len(t.split()) > 7:
        return None
    for name, rx in _HEADING_RULES:
        if rx.search(t):
            return name
    return None


_ITEM_START = re.compile(r"^\s*(?:\(?\d{1,2}[.)]|\(?[a-z][.)]|\(?[ivx]{1,4}[.)]|[••\-\*–])\s+", re.I)
_DEGREE_HINT = re.compile(r"\b(?:degree|ph\.?\s?d|doctorate|master|bachelor|m\.?\s?tech|b\.?\s?tech|m\.?\s?e\b|b\.?\s?e\b|"
                          r"m\.?\s?sc|b\.?\s?sc|mca|diploma|graduat|post[- ]?graduat|qualification|amie)", re.I)
_YEARS = re.compile(r"(\d{1,2})\s*(?:\+\s*)?(?:or\s+more\s+)?years?", re.I)
_ELIG_HINT = re.compile(r"\b(?:age|years of age|not exceeding|analogous|regular basis|regular service|pay level|level \d+|"
                        r"deputation|cadre|grade pay|pay band|citizen|nationality|parent department|lien)\b", re.I)
_DOC_HINT = re.compile(r"\b(?:apar|acr|vigilance clearance|integrity certificate|no[- ]objection|noc|bio-?data|proforma|"
                       r"certificate|attested|copies of|self[- ]attested)\b", re.I)
_RESEARCH_HINT = re.compile(r"\b(?:publications?|papers?|journals?|research|patents?|peer[- ]reviewed|ph\.?\s?d)\b", re.I)
_LEAD_HINT = re.compile(r"\b(?:lead|leading|led|manage|managing|management|supervis|guid(?:e|ance|ing)|mentor|team|"
                        r"coordinat|head)\w*", re.I)
_MUST = re.compile(r"\b(?:must|essential|mandatory|required|minimum|should possess)\b", re.I)
_DESIRE = re.compile(r"\b(?:desirable|preferred|preferably|an advantage|added advantage|will be preferred)\b", re.I)
_JUNK = re.compile(r"^\s*(?:advertisement|advt\.?|ref(?:erence)?\.?\s*no|notice|notification|filling up of|"
                   r"applications? (?:are|is) invited|page \d+|-+|_+)\b", re.I)


@dataclass
class _Section:
    name: str
    lines: list[str]


def _split_sections(text: str) -> list[_Section]:
    sections: list[_Section] = [_Section("preamble", [])]
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            sections[-1].lines.append("")
            continue
        name = None
        rest = ""
        m = _HEAD_WITH_COLON.match(line)
        if m:
            name = _heading_name(m.group("head"))
            rest = m.group("rest").strip()
        if name is None:
            bare = re.sub(r"^\s*\d{1,2}[.)]\s*", "", line)
            name = _heading_name(bare)
            rest = ""
        if name is not None:
            # Keep the label for eligibility lines ("Age limit: 56 years") so the condition stays readable.
            keep = line if (name == "eligibility" and rest) else rest
            sections.append(_Section(name, [keep] if keep else []))
        else:
            sections[-1].lines.append(line)
    return sections


def _items(lines: list[str], split_semicolons: bool = False) -> list[str]:
    items: list[str] = []
    cur: list[str] = []
    for line in lines:
        if not line:
            if cur:
                items.append(" ".join(cur))
                cur = []
            continue
        if _ITEM_START.match(line):
            if cur:
                items.append(" ".join(cur))
            cur = [_ITEM_START.sub("", line, count=1)]
        else:
            cur.append(line)
    if cur:
        items.append(" ".join(cur))
    out: list[str] = []
    for it in items:
        it = " ".join(it.split())
        if not it or _JUNK.match(it) or len(it) < 6:
            continue
        # Split long compound items on semicolons.
        parts = [p.strip() for p in re.split(r";\s+", it)] if (split_semicolons or len(it) > 220) else [it]
        out.extend(p[:MAX_ITEM_LEN] for p in parts if len(p) >= 6)
    return out


def _classify(item: str, section: str) -> tuple[RequirementCategory, bool]:
    is_degree = bool(_DEGREE_HINT.search(item))
    has_years = bool(_YEARS.search(item))
    if section == "essential":
        if _ELIG_HINT.search(item) and not is_degree:
            return RequirementCategory.ELIGIBILITY, True
        if is_degree:
            return RequirementCategory.MANDATORY_QUALIFICATION, True
        if has_years or re.search(r"\bexperience\b", item, re.I):
            return RequirementCategory.EXPERIENCE, True
        return RequirementCategory.TECHNICAL, True
    if section == "desirable":
        if is_degree:
            return RequirementCategory.DESIRABLE_QUALIFICATION, False
        if _RESEARCH_HINT.search(item):
            return RequirementCategory.RESEARCH, False
        if _LEAD_HINT.search(item):
            return RequirementCategory.LEADERSHIP, False
        if re.search(r"\bexperience\b", item, re.I) and has_years:
            return RequirementCategory.EXPERIENCE, False
        return RequirementCategory.TECHNICAL, False
    if section == "experience":
        if _ELIG_HINT.search(item) and re.search(r"level|pay|regular|analogous", item, re.I):
            return RequirementCategory.ELIGIBILITY, True
        return RequirementCategory.EXPERIENCE, True
    if section == "eligibility":
        return RequirementCategory.ELIGIBILITY, True
    if section == "documents":
        return RequirementCategory.DOCUMENTATION, True
    if section == "research":
        return RequirementCategory.RESEARCH, bool(_MUST.search(item))
    if section == "duties":
        if _LEAD_HINT.search(item) and not _RESEARCH_HINT.search(item):
            return RequirementCategory.LEADERSHIP, False
        if _RESEARCH_HINT.search(item):
            return RequirementCategory.RESEARCH, False
        return RequirementCategory.TECHNICAL, False
    # Preamble / unlabelled text: infer from wording.
    mandatory = bool(_MUST.search(item)) and not _DESIRE.search(item)
    if _DOC_HINT.search(item) and re.search(r"enclos|attach|submit|copies", item, re.I):
        return RequirementCategory.DOCUMENTATION, True
    if _ELIG_HINT.search(item) and not is_degree:
        return RequirementCategory.ELIGIBILITY, True
    if is_degree:
        return (RequirementCategory.MANDATORY_QUALIFICATION if mandatory else RequirementCategory.DESIRABLE_QUALIFICATION,
                mandatory)
    if has_years and re.search(r"\bexperience\b", item, re.I):
        return RequirementCategory.EXPERIENCE, mandatory or True
    if _RESEARCH_HINT.search(item):
        return RequirementCategory.RESEARCH, mandatory
    if _LEAD_HINT.search(item):
        return RequirementCategory.LEADERSHIP, mandatory
    return RequirementCategory.TECHNICAL, mandatory


def _keywords(item: str, tax: Taxonomy) -> list[str]:
    kws = [tax.label(c) for c in sorted(tax.concepts_in(item))]
    kws += [f"level:{lvl}" for lvl in sorted(tax.degree_levels_in(item))]
    kws += [f"discipline:{d}" for d in sorted(tax.disciplines_in(item))]
    m = _YEARS.search(item)
    if m:
        kws.append(f"years:{m.group(1)}")
    return kws


def extract_requirements(vacancy: Vacancy, taxonomy: Taxonomy | None = None) -> list[Requirement]:
    """Extract categorised requirements from the structured fields and the full notice text."""
    tax = taxonomy or default_taxonomy()
    found: list[tuple[str, str]] = []  # (section, item)
    structured = [
        ("essential", vacancy.essential_qualifications),
        ("desirable", vacancy.desirable_qualifications),
        ("duties", vacancy.required_skills),
        ("experience", vacancy.experience_criteria),
    ]
    for section, text in structured:
        if text and text.strip():
            for it in _items(text.splitlines(), split_semicolons=section == "duties"):
                found.append((section, it))
    raw = (vacancy.raw_text or "")[:MAX_TEXT]
    if raw.strip():
        for sec in _split_sections(raw):
            if sec.name == "preamble":
                # Only pick preamble lines that clearly state requirements.
                for it in _items(sec.lines):
                    if _MUST.search(it) or _DESIRE.search(it) or _DEGREE_HINT.search(it) or _YEARS.search(it):
                        found.append(("preamble", it))
                continue
            for it in _items(sec.lines, split_semicolons=sec.name == "duties"):
                found.append((sec.name, it))
    reqs: list[Requirement] = []
    for section, item in found:
        cat, mandatory = _classify(item, section)
        if section == "preamble" and cat == RequirementCategory.TECHNICAL and not tax.concepts_in(item):
            continue
        dup = next((r for r in reqs if similarity(r.text, item) >= 0.9), None)
        if dup is not None:
            continue
        reqs.append(Requirement(category=cat, text=item, mandatory=mandatory, origin="extracted",
                                keywords=_keywords(item, tax)))
    return reqs


def merge_requirements(existing: list[Requirement], extracted: list[Requirement]) -> list[Requirement]:
    """Keep manual requirements and user overrides; replace previously extracted ones."""
    manual = [r for r in existing if r.origin == "manual"]
    prior = {r.text: r for r in existing if r.origin == "extracted"}
    out = list(manual)
    for r in extracted:
        old = prior.get(r.text)
        if old is not None:
            r = r.model_copy(update={"id": old.id, "status_override": old.status_override, "user_note": old.user_note,
                                     "possessed_note": old.possessed_note, "category": old.category,
                                     "mandatory": old.mandatory})
        out.append(r)
    return out


_PAY = re.compile(r"\b(?:pay\s+)?level[\s-]*(\d{1,2}A?)\b", re.I)
_DEADLINE = re.compile(r"(?:last\s+date|closing\s+date|on\s+or\s+before|not\s+later\s+than)[^\d]{0,40}"
                       r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", re.I)


def suggest_fields(raw_text: str) -> dict[str, str]:
    """Suggested vacancy fields found in the notice (the user confirms before saving)."""
    out: dict[str, str] = {}
    text = raw_text or ""
    m = _PAY.search(text)
    if m:
        out["pay_level"] = f"Level {m.group(1)}"
    if re.search(r"\bdeputation\b", text, re.I):
        out["recruitment_mode"] = RecruitmentMode.DEPUTATION.value
    elif re.search(r"\bdirect recruitment\b", text, re.I):
        out["recruitment_mode"] = RecruitmentMode.DIRECT.value
    elif re.search(r"\bcontract(?:ual)? basis\b", text, re.I):
        out["recruitment_mode"] = RecruitmentMode.CONTRACT.value
    m = _DEADLINE.search(text)
    if m:
        d, mo, y = (int(x) for x in m.groups())
        if 1 <= mo <= 12 and 1 <= d <= 31:
            out["deadline"] = f"{y:04d}-{mo:02d}-{d:02d}"
    m = re.search(r"(?:advertisement|advt\.?)\s*(?:no\.?|number)\s*[:.]?\s*([\w/.-]{4,40})", text, re.I)
    if m:
        out["reference"] = m.group(1).rstrip(".")
    return out
