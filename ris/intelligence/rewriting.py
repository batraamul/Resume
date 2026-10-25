"""Achievement-rewriting assistant (rules-based; VAC-10, DEF-03).

Improves clarity and impact *using only recorded facts*: stronger verbs that
match your recorded involvement, removal of filler, recorded metrics, outcomes
and tools, and optional glossary explanations of domain terms. Every
suggestion shows the original, the revision, the facts used, assumptions and
missing metrics, and is validated as a claim. Nothing is adopted without approval.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache

from ris.domain.enums import Involvement, RecordKind
from ris.intelligence.claims import ClaimCheck, validate_claim
from ris.intelligence.text import bare_numbers
from ris.resources import config_dir
from ris.storage.repository import Record

GERUND_TO_PAST = {
    "designing": "Designed", "developing": "Developed", "building": "Built", "testing": "Tested",
    "integrating": "Integrated", "implementing": "Implemented", "managing": "Managed", "leading": "Led",
    "coordinating": "Coordinated", "preparing": "Prepared", "writing": "Wrote", "maintaining": "Maintained",
    "installing": "Installed", "commissioning": "Commissioned", "calibrating": "Calibrated", "planning": "Planned",
    "analysing": "Analysed", "analyzing": "Analysed", "evaluating": "Evaluated", "procuring": "Procured",
    "supervising": "Supervised", "training": "Trained", "mentoring": "Mentored", "reviewing": "Reviewed",
    "documenting": "Documented", "automating": "Automated", "deploying": "Deployed", "optimising": "Optimised",
    "optimizing": "Optimised", "configuring": "Configured", "troubleshooting": "Troubleshot", "repairing": "Repaired",
    "operating": "Operated", "monitoring": "Monitored", "establishing": "Established", "creating": "Created",
    "drafting": "Drafted", "conducting": "Conducted", "organising": "Organised", "organizing": "Organised",
    "delivering": "Delivered", "validating": "Validated", "verifying": "Verified", "modelling": "Modelled",
    "modeling": "Modelled", "simulating": "Simulated", "programming": "Programmed", "coding": "Coded",
    "researching": "Researched", "investigating": "Investigated", "overseeing": "Oversaw", "handling": "Handled",
    "running": "Ran", "setting up": "Set up", "teaching": "Taught", "assisting": "Assisted", "supporting": "Supported",
    "executing": "Executed", "upgrading": "Upgraded", "fabricating": "Fabricated", "assembling": "Assembled",
}
LEADING_VERBS = {"designed", "developed", "built", "led", "managed", "supervised", "oversaw", "established",
                 "created", "implemented", "directed", "coordinated", "deployed", "commissioned"}
INVOLVEMENT_VERB = {
    Involvement.LEADING.value: "Led",
    Involvement.COORDINATING.value: "Coordinated",
    Involvement.INDIVIDUAL.value: "Carried out",
    Involvement.PARTICIPATING.value: "Contributed to",
    Involvement.SUPPORTING.value: "Supported",
    Involvement.ADVISING.value: "Advised on",
}
FILLER = [
    (r"\bsuccessfully\s+", ""), (r"\bvarious\s+", ""), (r",?\s*etc\.?", ""), (r"\bin order to\b", "to"),
    (r"\butili[sz]ed\b", "used"), (r"\butili[sz]ing\b", "using"), (r"\bwith the help of\b", "using"),
    (r"\bin the field of\b", "in"), (r"\bon a daily basis\b", "daily"), (r"\bdue to the fact that\b", "because"),
    (r"\ba wide range of\b", "a range of"), (r"\bvery\s+", ""), (r"\breally\s+", ""),
]
WEAK_OPENINGS = re.compile(
    r"^(?:i\s+)?(?:was\s+|am\s+)?(?:responsible for|in charge of|tasked with|involved in|worked on|helped(?: to)?|"
    r"assisted(?: in| with)?|duties included|participated in)\s+", re.IGNORECASE)


@dataclass
class RewriteSuggestion:
    original: str
    revised: str
    source_facts: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    missing_metrics: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    check: ClaimCheck = field(default_factory=ClaimCheck)
    source_ids: list[str] = field(default_factory=list)

    @property
    def material(self) -> bool:
        return self.check.material

    @property
    def unchanged(self) -> bool:
        return self.revised.strip() == self.original.strip()


@lru_cache(maxsize=1)
def default_glossary() -> dict[str, str]:
    raw = json.loads((config_dir() / "glossary.json").read_text(encoding="utf-8"))
    return {k.lower(): v for k, v in raw.get("terms", {}).items()}


def _effective_involvement(bullet: Record, parent: Record | None) -> str | None:
    inv = getattr(bullet.data, "involvement", None)
    if inv:
        return inv
    if parent is not None:
        return getattr(parent.data, "involvement", None)
    return None


def _missing_metric_hints(text: str, keywords: list[str]) -> list[str]:
    t = (text + " " + " ".join(keywords)).lower()
    hints = []
    if re.search(r"model|inference|network|detect|classif|super-?resolution|learning", t):
        hints.append("Model result: accuracy, latency (ms), frame rate or model size — as measured.")
    if re.search(r"test|qualif|calibrat|acceptance|inspect", t):
        hints.append("Scale: number of units, tests, stations or defects found.")
    if re.search(r"procure|tender|bid|purchase|gem\b", t):
        hints.append("Scope: number or value of procurements handled.")
    if re.search(r"lead|team|supervis|mentor|group", t):
        hints.append("Team size or number of people supervised.")
    if re.search(r"network|iot|sensor|monitor|dashboard", t):
        hints.append("Coverage: number of sensors, sites or data points.")
    if re.search(r"time|faster|reduc|automat|efficien", t):
        hints.append("Time or effort saved, compared with the earlier method.")
    if not hints:
        hints.append("A verified measure of scale, quality, time or cost.")
    return hints


def rewrite_bullet(bullet: Record, parent: Record | None = None, *, translate: bool = False,
                   glossary: dict[str, str] | None = None, current_role: bool | None = None) -> RewriteSuggestion:
    d = bullet.data
    original = (d.text or "").strip()
    text = " ".join(original.split())
    changes: list[str] = []
    assumptions: list[str] = []
    facts = [f"Statement: {original}"]
    involvement = _effective_involvement(bullet, parent)
    if involvement:
        facts.append(f"Recorded involvement: {involvement}")

    # 1. Weak openings → verb matching recorded involvement.
    m = WEAK_OPENINGS.match(text)
    if m:
        rest = text[m.end():]
        verb = None
        g = re.match(r"(setting up|[a-z]+ing)\b\s*", rest, re.IGNORECASE)
        if g and g.group(1).lower() in GERUND_TO_PAST:
            candidate = GERUND_TO_PAST[g.group(1).lower()]
            if candidate.lower() in LEADING_VERBS and involvement in ("participating", "supporting", "advising"):
                verb = INVOLVEMENT_VERB[involvement]
                rest = rest  # keep the gerund phrase: "Contributed to designing …"
                assumptions.append(f"Kept a supporting verb because your involvement is recorded as {involvement}.")
            else:
                verb = candidate
                rest = rest[g.end():]
        else:
            verb = INVOLVEMENT_VERB.get(involvement or "", "Contributed to")
            assumptions.append(f"Verb chosen from your recorded involvement ({involvement or 'not recorded'}).")
        text = f"{verb} {rest}".strip()
        changes.append("Replaced a weak opening with an action verb.")

    # 2. Filler removal.
    before = text
    for pat, rep in FILLER:
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if text != before:
        changes.append("Removed filler words.")

    # 3. Recorded metrics, outcome and tools.
    metrics = list(getattr(d, "metrics", []) or [])
    if metrics:
        facts.append("Metrics: " + "; ".join(metrics))
        present = bare_numbers(text)
        new = [mt for mt in metrics if not (bare_numbers(mt) & present)]
        if new:
            text = text.rstrip(". ") + f" ({'; '.join(new[:2])})."
            changes.append("Added your recorded metrics.")
    outcome = getattr(d, "outcome", "") or ""
    if outcome:
        facts.append(f"Outcome: {outcome}")
        if outcome.lower()[:30] not in text.lower():
            text = text.rstrip(". ") + " — " + outcome[0].lower() + outcome[1:].rstrip(".") + "."
            changes.append("Added your recorded outcome.")
    tools = list(getattr(d, "tools", []) or [])
    if tools:
        facts.append("Tools: " + ", ".join(tools))
        missing_tools = [t for t in tools if t.lower() not in text.lower()]
        if missing_tools and len(text) < 200:
            text = text.rstrip(". ") + " using " + ", ".join(missing_tools[:3]) + "."
            changes.append("Named your recorded tools.")

    # 4. Optional glossary translation (first occurrence of each term).
    if translate:
        gl = glossary if glossary is not None else default_glossary()
        for term in sorted(gl, key=len, reverse=True):
            pattern = re.compile(r"(?<![\w(])" + re.escape(term) + r"(?![\w)])", re.IGNORECASE)
            if pattern.search(text) and gl[term].lower() not in text.lower():
                text = pattern.sub(gl[term], text, count=1)
                changes.append(f"Explained '{term}' in engineering terms (glossary).")
                assumptions.append(f"Glossary wording for '{term}' is a general explanation, not a claim about your work.")

    # 5. Tidy.
    if text and not text[0].isupper():
        text = text[0].upper() + text[1:]
    if text and text[-1] not in ".!?":
        text += "."
    if len(text) > 260:
        assumptions.append("The statement is long; consider splitting it into two.")

    missing = [] if (metrics or bare_numbers(original)) else _missing_metric_hints(original, list(getattr(d, "keywords", [])))
    sources = [original, *metrics, outcome, *tools]
    if translate:
        gl = glossary if glossary is not None else default_glossary()
        sources.extend(v for k, v in gl.items() if k in text.lower() or v.lower() in text.lower())
    check = validate_claim(original, text, sources, involvement)
    if current_role is not None:
        assumptions.append("Tense kept as in the original statement.")
    return RewriteSuggestion(original=original, revised=text, source_facts=facts, assumptions=assumptions,
                             missing_metrics=missing, changes=changes, check=check,
                             source_ids=[bullet.id] + ([parent.id] if parent is not None else []))


def draft_summary(snapshot, focus_label: str = "") -> RewriteSuggestion:
    """A factual summary draft from confirmed records only (designation, years, domains)."""
    from ris.domain.enums import SkillCategory, Verification, label
    from ris.intelligence.matching import EvidenceMatcher

    p = snapshot.personal_data
    positions = [x for x in snapshot.of(RecordKind.POSITION) if x.verification != Verification.UNCONFIRMED]
    current = next((x for x in positions if x.data.is_current), None)
    months = EvidenceMatcher(snapshot).total_experience_months(confirmed_only=True)
    years = months // 12
    cats: dict[str, int] = {}
    for s in snapshot.of(RecordKind.SKILL):
        if s.verification != Verification.UNCONFIRMED and s.data.category not in ("other", "languages", "software"):
            cats[s.data.category] = cats.get(s.data.category, 0) + 1
    def soften(lbl: str) -> str:
        # Lower-case ordinary words but keep acronyms ("AI / machine learning", "IoT").
        return " ".join(w if (sum(ch.isupper() for ch in w) > 1 or w in ("IoT",)) else w.lower() for w in lbl.split())

    top = [soften(label(SkillCategory(c))) for c, _ in sorted(cats.items(), key=lambda kv: (-kv[1], kv[0]))[:4]]
    facts, ids = [], []
    parts = []
    lead = p.professional_title or (current.data.designation if current else "Professional")
    if years:
        parts.append(f"{lead} with {years}+ years of recorded experience")
        facts.append(f"Experience: at least {years} years from confirmed position dates")
    else:
        parts.append(lead)
    if top:
        parts[-1] += " across " + ", ".join(top[:-1]) + (" and " if len(top) > 1 else "") + top[-1]
        facts.append("Domains: categories of your confirmed skills")
    text = parts[0] + "."
    if current is not None:
        text += f" Currently {current.data.designation}" + (f", {current.data.organisation}" if current.data.organisation else "") + "."
        facts.append(f"Current position: {current.data.designation}")
        ids.append(current.id)
    original = ""
    check = validate_claim(original, text, [text])
    return RewriteSuggestion(original=original, revised=text, source_facts=facts,
                             assumptions=["Built only from confirmed records; edit freely before saving."],
                             missing_metrics=[], changes=["Drafted from confirmed records."], check=check,
                             source_ids=ids)
