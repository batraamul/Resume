"""Disclosure scanner: warns about sensitive official or personal content before export.

Heuristic by design. It flags candidates for the user's judgement; it cannot
decide what an employer permits. Identity and account numbers block export;
everything else is a warning the user must acknowledge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ris.composition.ir import ResumeDocument

BLOCK = "block"
WARN = "warn"


@dataclass(frozen=True)
class Finding:
    severity: str
    category: str
    message: str
    excerpt: str
    source_ids: tuple[str, ...] = ()


def _mask(text: str) -> str:
    return re.sub(r"\d", "•", text)


_RULES: list[tuple[str, str, str, re.Pattern]] = [
    (BLOCK, "identifier", "Looks like an Aadhaar number. Remove identity numbers from resumes.",
     re.compile(r"(?<!\d)[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")),
    (BLOCK, "identifier", "Looks like a PAN. Remove identity numbers from resumes.",
     re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    (BLOCK, "identifier", "Looks like a passport number. Remove identity numbers from resumes.",
     re.compile(r"\b(?:passport(?:\s+no\.?)?)\s*[:#]?\s*[A-PR-WY][1-9]\d{6}\b", re.IGNORECASE)),
    (BLOCK, "identifier", "Looks like a bank account or IFSC code.",
     re.compile(r"\b(?:IFSC\s*[:#]?\s*)?[A-Z]{4}0[A-Z0-9]{6}\b|\b(?:a/c|account)\s*(?:no\.?|number)?\s*[:#]?\s*\d{9,18}\b",
                re.IGNORECASE)),
    (WARN, "marking", "Contains a security classification marking (secret, restricted, classified, FOUO).",
     re.compile(r"\b(?:top\s+secret|secret|restricted|classified|confidential|for\s+official\s+use\s+only|fouo)\b",
                re.IGNORECASE)),
    (WARN, "security", "Mentions passwords, access codes or security procedures.",
     re.compile(r"\b(?:password|passcode|access\s+code|security\s+procedure|clearance\s+level|crypto\s*key)s?\b",
                re.IGNORECASE)),
    (WARN, "infrastructure", "Contains an IP address or network detail.",
     re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:vlan|firewall\s+rule|subnet|hostname)\b", re.IGNORECASE)),
    (WARN, "location", "Contains geographic coordinates or precise site details.",
     re.compile(r"\b\d{1,2}\.\d{3,}\s*°?\s*[NS]?\s*,\s*\d{1,3}\.\d{3,}\s*°?\s*[EW]?\b|\b(?:lat(?:itude)?|long(?:itude)?)\s*[:=]",
                re.IGNORECASE)),
    (WARN, "frequency", "Contains operating radio frequencies; check whether they are public.",
     re.compile(r"\b\d{2,5}(?:\.\d+)?\s?(?:MHz|GHz)\b")),
    (WARN, "deployment", "Describes deployment or installation specifics; check they are public.",
     re.compile(r"\b(?:deployed|installed|stationed|located)\s+(?:at|in)\s+(?:the\s+)?[A-Z][\w-]+", re.IGNORECASE)),
    (WARN, "internal", "Mentions internal file, letter or system references.",
     re.compile(r"\b(?:file|letter|office\s+order|order)\s+no\.?\s*[:#]?\s*[\w/.-]*\d|\b(?:intranet|internal\s+portal|e-office)\b",
                re.IGNORECASE)),
    (WARN, "personal", "Mentions a date of birth or other personal identifiers.",
     re.compile(r"\b(?:date\s+of\s+birth|d\.?o\.?b\.?|born\s+on|father'?s\s+name|husband'?s\s+name|marital\s+status)\b",
                re.IGNORECASE)),
]

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d\s()-]{8,}\d)")


def scan_text(text: str, source_ids: tuple[str, ...] = (), *, own_contacts: set[str] | None = None,
              skip_categories: set[str] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    skip = skip_categories or set()
    for sev, cat, msg, rx in _RULES:
        if cat in skip:
            continue
        for m in rx.finditer(text or ""):
            excerpt = text[max(0, m.start() - 25): m.end() + 25].strip()
            findings.append(Finding(sev, cat, msg, _mask(excerpt) if sev == BLOCK else excerpt, source_ids))
            break
    own = {c.casefold() for c in (own_contacts or set())}
    own_digits = {re.sub(r"\D", "", c) for c in (own_contacts or set())}
    if "personal" not in skip:
        for m in _EMAIL.finditer(text or ""):
            if m.group(0).casefold() not in own:
                findings.append(Finding(WARN, "personal", "Contains someone else's email address.", m.group(0),
                                        source_ids))
                break
        for m in _PHONE.finditer(text or ""):
            digits = re.sub(r"\D", "", m.group(0))
            if len(digits) >= 10 and digits not in own_digits and not any(digits.endswith(o[-10:]) for o in own_digits if o):
                findings.append(Finding(WARN, "personal", "Contains a telephone number that is not yours.",
                                        _mask(m.group(0)), source_ids))
                break
    return findings


def scan_document(doc: ResumeDocument) -> list[Finding]:
    """Scan every text fragment of the IR, attributing findings to source records."""
    own = {c.value for c in doc.contacts if c.key in ("email", "phone")}
    # Referees appear only when their permission is recorded; their own contact details are expected there.
    for s in doc.sections:
        if s.key == "references":
            for e in s.entries:
                own |= {v for k, v in e.meta if k in ("Email", "Telephone") and v}
    findings: list[Finding] = []
    for s in doc.sections:
        skip = {"personal"} if s.key in ("particulars", "declaration") else set()
        if s.key in ("publications", "manuscripts"):
            skip |= {"frequency"}
        for p in s.paragraphs:
            findings.extend(scan_text(p, tuple(s.source_ids), own_contacts=own, skip_categories=skip))
        for item in s.items:
            findings.extend(scan_text(item, tuple(s.source_ids), own_contacts=own, skip_categories=skip))
        if s.table:
            for row in s.table.rows:
                findings.extend(scan_text(" ".join(row), tuple(s.table.source_ids), own_contacts=own,
                                          skip_categories=skip))
        for t in s.tiles:
            findings.extend(scan_text(f"{t.value} {t.label} {t.caption}", tuple(t.source_ids), own_contacts=own,
                                      skip_categories=skip | {"frequency"}))
        if s.chart:
            for pt in s.chart.points:
                findings.extend(scan_text(f"{pt.label} {pt.caption}", tuple(pt.source_ids), own_contacts=own,
                                          skip_categories=skip))
        for e in s.entries:
            stack = [e]
            while stack:
                cur = stack.pop()
                text = " ".join(x for x in (cur.title, cur.subtitle, cur.description, cur.citation_rest,
                                            *(v for _, v in cur.facets), *cur.highlights) if x)
                findings.extend(scan_text(text, tuple(cur.source_ids), own_contacts=own, skip_categories=skip))
                for b in cur.bullets:
                    findings.extend(scan_text(b.text, tuple(b.source_ids), own_contacts=own, skip_categories=skip))
                for _, v in cur.meta:
                    findings.extend(scan_text(v, tuple(cur.source_ids), own_contacts=own, skip_categories=skip))
                stack.extend(cur.children)
    # De-duplicate identical findings.
    seen: set[tuple] = set()
    out: list[Finding] = []
    for f in findings:
        key = (f.category, f.excerpt, f.source_ids)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out
