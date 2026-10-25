"""Claim validation: flag wording that goes beyond the recorded facts (PRV-04/05).

Used for rule-based rewrites, external-AI suggestions and manual overrides.
A suggestion that introduces new numbers, outcomes, qualifications,
deployments, names or stronger involvement is *material*: it can only be
adopted through explicit approval, and the flags are shown to the user.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ris.intelligence.text import bare_numbers

SUPERLATIVES = ["world-class", "world class", "best-in-class", "unparalleled", "unprecedented", "unique",
                "pioneering", "pioneered", "revolutionary", "revolutionised", "revolutionized", "first-ever",
                "groundbreaking", "ground-breaking", "renowned", "exceptional", "outstanding", "visionary",
                "guru", "ninja", "rockstar", "expert in", "leading expert", "dramatically", "massively",
                "significantly", "tremendously", "single-handedly"]
LEAD_VERBS = ["led", "lead", "leads", "headed", "heads", "spearheaded", "directed", "directs", "managed", "manages",
              "supervised", "supervises", "oversaw", "oversee", "oversees", "championed", "drove", "chaired",
              "commanded"]
OUTCOME_WORDS = ["resulting in", "leading to", "which led to", "improved", "increased", "reduced", "saved",
                 "boosted", "cut ", "accelerated", "enhanced", "achieved", "won", "doubled", "tripled", "halved"]
QUALIFICATION_WORDS = ["ph.d", "phd", "doctorate", "m.tech", "mtech", "master's", "masters degree", "b.tech",
                       "certified", "certification", "chartered"]
DEPLOYMENT_WORDS = ["deployed", "fielded", "in service", "operational use", "inducted", "commissioned",
                    "rolled out", "in production"]
CLEARANCE_WORDS = ["security clearance", "cleared for", "top secret", "clearance holder"]
PUBLISHED_WORDS = ["published in", "published", "accepted in", "accepted for publication"]
LOW_INVOLVEMENT = {"participating", "supporting", "advising", "individual"}


@dataclass
class ClaimCheck:
    flags: list[str] = field(default_factory=list)
    new_numbers: list[str] = field(default_factory=list)
    new_terms: list[str] = field(default_factory=list)
    material: bool = False

    @property
    def ok(self) -> bool:
        return not self.flags


def _contains(text: str, phrase: str) -> bool:
    return re.search(r"(?<![\w])" + re.escape(phrase) + r"(?![\w])", text, re.IGNORECASE) is not None


def _proper_terms(text: str) -> set[str]:
    """Capitalised words/acronyms that are not sentence-initial (rough named-entity proxy)."""
    terms: set[str] = set()
    for m in re.finditer(r"(?<![.!?]\s)(?<!^)\b([A-Z][A-Za-z0-9-]{2,}|[A-Z]{2,}[A-Za-z0-9-]*)\b", text):
        terms.add(m.group(1))
    return terms


def validate_claim(original: str, revised: str, source_texts: list[str] | None = None,
                   involvement: str | None = None, publication_status: str | None = None) -> ClaimCheck:
    sources = "\n".join([original, *(source_texts or [])])
    chk = ClaimCheck()
    new_nums = sorted(bare_numbers(revised) - bare_numbers(sources), key=lambda x: (len(x), x))
    if new_nums:
        chk.new_numbers = new_nums
        chk.flags.append("Introduces numbers not in your records: " + ", ".join(new_nums))
    for w in SUPERLATIVES:
        if _contains(revised, w) and not _contains(sources, w):
            chk.flags.append(f"Uses unsupported emphasis ('{w}').")
    if involvement in LOW_INVOLVEMENT:
        for v in LEAD_VERBS:
            if _contains(revised, v) and not _contains(sources, v):
                chk.flags.append(f"Implies a leading role ('{v}') but your involvement is recorded as {involvement}.")
                break
    for w in OUTCOME_WORDS:
        if _contains(revised, w.strip()) and not _contains(sources, w.strip()):
            chk.flags.append(f"States an outcome not in your records ('{w.strip()}').")
            break
    for w in QUALIFICATION_WORDS:
        if _contains(revised, w) and not _contains(sources, w):
            chk.flags.append(f"Mentions a qualification not in this record ('{w}').")
            break
    for w in DEPLOYMENT_WORDS:
        if _contains(revised, w) and not _contains(sources, w):
            chk.flags.append(f"Claims a deployment or operational use not recorded ('{w}').")
            break
    for w in CLEARANCE_WORDS:
        if _contains(revised, w) and not _contains(sources, w):
            chk.flags.append("Mentions a security clearance that is not recorded.")
            break
    if publication_status and publication_status not in ("published", "accepted"):
        for w in PUBLISHED_WORDS:
            if _contains(revised, w):
                chk.flags.append(f"Describes work as published/accepted but its status is '{publication_status}'.")
                break
    new_terms = sorted(_proper_terms(revised) - _proper_terms(sources) - {w.capitalize() for w in sources.split()})
    src_lower = sources.lower()
    new_terms = [t for t in new_terms if t.lower() not in src_lower]
    if new_terms:
        chk.new_terms = new_terms
        chk.flags.append("Introduces names or terms not in your records: " + ", ".join(new_terms[:6]))
    chk.material = bool(chk.flags)
    return chk
