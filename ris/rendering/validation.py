"""Export validation: verify generated files before an export is reported as successful.

Checks (requirement DOC-06): existence and size; DOCX reopen/parse; PDF validity
and text extraction; substantive content; contact details; chronology;
section presence; leftover placeholders; confidential content; page limits;
DOCX/PDF consistency; out-of-bounds text and nearly empty last pages;
embedded fonts; hyperlinks.

A "pass" on these checks is programmatic. Visual layout review is reported
separately and never claimed unless a person looked at the pages.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ris.composition.ir import ResumeDocument
from ris.rendering import extract
from ris.util import normalize_for_compare

PASS, WARN, FAIL, SKIP = "pass", "warn", "fail", "skip"

_PLACEHOLDER = re.compile(
    r"\{\{|\}\}|\[(?:TODO|TBD|INSERT|PLACEHOLDER|YOUR|NAME HERE|DATE HERE)[^\]]*\]|lorem ipsum|"
    r"<\s*(?:insert|your|placeholder)[^>]*>|\bTODO\b|\bTBD\b|\bXXX+\b",
    re.IGNORECASE,
)
_PYTHON_LEAK = re.compile(r"(?<![\w-])(?:None|null|undefined|NaN)(?![\w-])")
_PAGE_LABEL = re.compile(r"\b(?:page\s+)?\d+\s*(?:of|/)\s*\d+\b", re.IGNORECASE)


@dataclass
class Check:
    name: str
    status: str
    message: str
    details: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    checks: list[Check] = field(default_factory=list)
    page_count: int | None = None

    def add(self, name: str, status: str, message: str, details: list[str] | None = None) -> None:
        self.checks.append(Check(name, status, message, list(details or [])[:25]))

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.status == WARN]

    @property
    def ok(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict:
        return {"page_count": self.page_count,
                "checks": [{"name": c.name, "status": c.status, "message": c.message, "details": c.details}
                           for c in self.checks]}


def _fuzzy_contains(hay: list[str], index: dict[str, list[int]], needle: list[str], max_gap: int = 6) -> bool:
    if not needle:
        return True
    for start in index.get(needle[0], []):
        pos = start
        ok = True
        for tok in needle[1:]:
            nxt = next((p for p in index.get(tok, []) if pos < p <= pos + max_gap + 1), None)
            if nxt is None:
                ok = False
                break
            pos = nxt
        if ok:
            return True
    return False


def _index(tokens: list[str]) -> dict[str, list[int]]:
    idx: dict[str, list[int]] = {}
    for i, t in enumerate(tokens):
        idx.setdefault(t, []).append(i)
    return idx


def expected_snippets(doc: ResumeDocument) -> list[tuple[str, str]]:
    """(category, text) pairs that must appear in every output."""
    out: list[tuple[str, str]] = []
    if doc.name:
        out.append(("name", doc.name))
    for c in doc.contacts:
        out.append(("contact", c.value))
    if doc.letter is not None:
        lt = doc.letter
        for frag in (lt.subject, lt.salutation, lt.closing, *lt.signature_lines):
            if frag:
                out.append(("letter", " ".join(frag.split()[:12])))
        for para in lt.paragraphs:
            out.append(("paragraph", " ".join(para.split()[:12])))
    for s in doc.sections:
        out.append(("section", s.title))
        for p in s.paragraphs:
            out.append(("paragraph", " ".join(p.split()[:14])))
        for e in s.entries:
            stack = [e]
            while stack:
                cur = stack.pop()
                if cur.title:
                    out.append(("entry", " ".join(cur.title.split()[:12])))
                for b in cur.bullets:
                    out.append(("bullet", " ".join(b.text.split()[:12])))
                stack.extend(cur.children)
        for g in s.skill_groups:
            out.extend(("skill", i) for i in g.items[:3])
        if s.table:
            for row in s.table.rows:
                for cell in row:
                    if cell and len(cell) > 3:
                        out.append(("table", " ".join(cell.split("\n")[0].split()[:8])))
    return out


_SMALL_CAPS_SPLIT = re.compile(r"(?<![\w])([A-Za-z]) {1,2}(?=[A-Z]{2,})")
_SMALL_CAPS_PAIR = re.compile(r"(?<![\w])([A-Z]) ([A-Z])(?![\w])")  # "I N" → "IN"
_SPACE_BEFORE_HYPHEN = re.compile(r"(?<=\w) +-(?=\w)")
# Letter-spaced headings: PDF extractors insert a space between widely tracked characters
# ("P R O F E S S I O N A L  S U M M A R Y"); words stay separated by two or more spaces.
_LETTER_SPACED = re.compile(r"(?<!\S)(?:\w ){1,}\w")


def _alt_reading(text: str) -> str:
    """Alternative reading of extracted PDF text that re-joins small-caps splits ("F UNDING" → "FUNDING").

    Used only as a second chance for presence checks and as an extra net for confidential-phrase checks;
    the original text is always checked too.
    """
    text = _SMALL_CAPS_PAIR.sub(r"\1\2", _SPACE_BEFORE_HYPHEN.sub("-", text))
    return _SMALL_CAPS_SPLIT.sub(r"\1", text)


def _letter_spaced_reading(text: str) -> str:
    """Re-join letter-spaced runs ("S U M M A R Y" → "SUMMARY"). A second-chance reading like `_alt_reading`."""
    # A space is added after each run: in margin-label layouts the extractor can glue the label to the
    # first word of the neighbouring cell ("E D U C A T I O NPh.D." → "EDUCATION Ph.D.").
    return _LETTER_SPACED.sub(lambda m: m.group(0).replace(" ", "") + " ", text)


def _strip_footer_page(text: str, footer_strings: list[str]) -> str:
    """Remove running-footer lines (name, note, page label) from the end of one page's text.

    Only the last few lines are examined, so the same words elsewhere on the page
    (for example the name heading) are kept.
    """
    fs_norm = {normalize_for_compare(f) for f in footer_strings if f}
    lines = text.splitlines()
    for _ in range(4):
        if not lines:
            break
        core = _PAGE_LABEL.sub(" ", lines[-1])
        if re.fullmatch(r"\s*\d{1,3}\s*", core):
            core = ""  # bare page number ("x" footer style)
        n = normalize_for_compare(core)
        rest = n
        for f in sorted(fs_norm, key=len, reverse=True):
            rest = rest.replace(f, " ")
        if not n or not rest.strip() or n in fs_norm:
            lines.pop()
        else:
            break
    return "\n".join(lines)


def _strip_footer(page_texts: list[str], footer_strings: list[str]) -> str:
    return "\n".join(_strip_footer_page(t, footer_strings) for t in page_texts)


def validate_outputs(
    doc: ResumeDocument,
    *,
    docx_path: Path | None = None,
    pdf_path: Path | None = None,
    txt_path: Path | None = None,
    confidential_phrases: list[str] | None = None,
    footer_strings: list[str] | None = None,
    engine: str = "",
    missing_glyphs: set[str] | None = None,
    check_chronology: bool = True,
) -> ValidationReport:
    rep = ValidationReport()
    footer_strings = [s for s in (footer_strings or []) if s]
    paths = {k: v for k, v in (("docx", docx_path), ("pdf", pdf_path), ("txt", txt_path)) if v is not None}

    # 1. existence and size
    missing = [f"{k}: {p.name}" for k, p in paths.items() if not p.exists() or p.stat().st_size == 0]
    rep.add("files_exist", FAIL if missing else PASS,
            "Every requested file exists and is not empty." if not missing else "Some files are missing or empty.",
            missing)
    if missing:
        return rep

    texts: dict[str, str] = {}
    docx_info = pdf_info = None
    # 2. DOCX reopen
    if docx_path:
        try:
            docx_info = extract.read_docx(docx_path)
            texts["docx"] = docx_info.body_text
            details = []
            if not any(s and (s.startswith("Heading") or s == "Title") for s in docx_info.styles_used):
                details.append("No heading styles were used.")
            rep.add("docx_parse", WARN if details else PASS,
                    "The Word file reopens and parses; heading styles, lists and fields are present."
                    if not details else "The Word file reopens, with formatting notes.", details)
        except Exception as exc:  # noqa: BLE001 - any parse failure is a validation failure
            rep.add("docx_parse", FAIL, "The Word file could not be reopened.", [type(exc).__name__ + ": " + str(exc)[:200]])
    # 3. PDF validity
    if pdf_path:
        try:
            pdf_info = extract.read_pdf(pdf_path)
            texts["pdf"] = _strip_footer(pdf_info.page_texts, footer_strings)
            rep.page_count = pdf_info.page_count
            if not pdf_info.text.strip():
                rep.add("pdf_parse", FAIL, "The PDF contains no extractable text.")
            else:
                rep.add("pdf_parse", PASS, f"The PDF is valid with selectable text ({pdf_info.page_count} page(s)).")
        except Exception as exc:  # noqa: BLE001
            rep.add("pdf_parse", FAIL, "The PDF could not be read.", [type(exc).__name__ + ": " + str(exc)[:200]])
    if txt_path:
        texts["txt"] = Path(txt_path).read_text(encoding="utf-8")

    # 4. substantive content
    expected = expected_snippets(doc)
    readings: dict[str, list[tuple[list[str], dict[str, list[int]]]]] = {}
    for fmt, text in texts.items():
        variants = [text] + ([_alt_reading(text), _letter_spaced_reading(text)] if fmt == "pdf" else [])
        readings[fmt] = [(t, _index(t)) for t in (extract.tokens(v) for v in variants)]

    def present(fmt: str, needle: list[str]) -> bool:
        return any(_fuzzy_contains(toks, idx, needle) for toks, idx in readings[fmt])

    for fmt in texts:
        missing_items = []
        for cat, snippet in expected:
            needle = extract.tokens(snippet)
            if needle and not present(fmt, needle):
                missing_items.append(f"{cat}: {snippet[:70]}")
        rep.add(f"content_{fmt}", FAIL if missing_items else PASS,
                f"All {len(expected)} expected items appear in the {fmt.upper()}." if not missing_items
                else f"{len(missing_items)} expected item(s) are missing from the {fmt.upper()}.", missing_items)

    # 5. contact details exact
    contact_problems = []
    for c in doc.contacts:
        if c.key not in ("email", "phone"):
            continue
        for fmt, text in texts.items():
            norm = normalize_for_compare(text)
            val = normalize_for_compare(c.value)
            if c.key == "phone":
                if re.sub(r"\D", "", c.value) not in re.sub(r"\D", "", text):
                    contact_problems.append(f"{fmt}: telephone not found exactly")
            elif val not in norm:
                contact_problems.append(f"{fmt}: email not found exactly")
    rep.add("contacts", FAIL if contact_problems else PASS,
            "Contact details are present and exact." if not contact_problems else "Contact details differ.",
            contact_problems)

    # 6. chronology
    if check_chronology:
        problems = []
        for s in doc.sections:
            if s.key not in ("experience", "education", "projects", "leadership") or s.layout != "entries":
                continue
            keys = [tuple(e.sort_key) for e in s.entries if e.sort_key]
            if s.key == "projects":
                continue  # projects may be ordered by relevance
            for a, b in zip(keys, keys[1:], strict=False):
                if a < b:
                    problems.append(f"{s.title}: entries are not in reverse-chronological order")
                    break
        rep.add("chronology", FAIL if problems else PASS,
                "Dated sections are in reverse-chronological order." if not problems else "Chronology problems found.",
                problems)

    # 7. sections present
    sec_missing = []
    for fmt in texts:
        for s in doc.sections:
            if not present(fmt, extract.tokens(s.title)):
                sec_missing.append(f"{fmt}: {s.title}")
    rep.add("sections", FAIL if sec_missing else PASS,
            f"All {len(doc.sections)} sections are present in every format." if not sec_missing
            else "Some sections are missing.", sec_missing)

    # 8. placeholders
    ph = []
    for fmt, text in texts.items():
        for m in _PLACEHOLDER.finditer(text):
            ph.append(f"{fmt}: '{m.group(0)}'")
        for m in _PYTHON_LEAK.finditer(text):
            ph.append(f"{fmt}: '{m.group(0)}'")
    rep.add("placeholders", FAIL if ph else PASS,
            "No placeholders or unfilled values remain." if not ph else "Placeholder text was found.", ph)

    # 9. confidential content
    leaks = []
    phrases = [p for p in (confidential_phrases or []) if p]
    for fmt, text in texts.items():
        readings = {normalize_for_compare(text), normalize_for_compare(_alt_reading(text)),
                    normalize_for_compare(_letter_spaced_reading(text))}
        for phrase in phrases:
            if any(normalize_for_compare(phrase) in r for r in readings):
                leaks.append(f"{fmt}: matched a confidential phrase ('{phrase[:40]}…')")
    rep.add("confidential", FAIL if leaks else PASS,
            f"No confidential content found ({len(phrases)} protected phrase(s) checked)." if not leaks
            else "Confidential content appears in the output.", leaks)

    # 10. page limits
    if rep.page_count is not None:
        target = doc.max_pages
        soft = {"one_page": 1, "two_pages": 2}.get(doc.length)
        if target and rep.page_count > target:
            rep.add("page_limit", FAIL, f"The PDF has {rep.page_count} pages; the limit is {target}.")
        elif soft and rep.page_count > soft:
            rep.add("page_limit", WARN, f"The PDF has {rep.page_count} pages; the preferred length is {soft}.")
        else:
            rep.add("page_limit", PASS, f"Page count {rep.page_count} is within the limit.")

    # 11. DOCX/PDF consistency
    if "docx" in texts and "pdf" in texts:
        d = Counter(t for t in extract.tokens(texts["docx"]) if len(t) > 1)
        p = Counter(t for t in extract.tokens(texts["pdf"]) if len(t) > 1)
        common = sum((d & p).values())
        recall_d = common / max(sum(d.values()), 1)
        recall_p = common / max(sum(p.values()), 1)
        missing_tok = sorted((d - p).keys())[:15]
        extra_tok = sorted((p - d).keys())[:15]
        status = PASS if min(recall_d, recall_p) >= 0.97 else (WARN if min(recall_d, recall_p) >= 0.9 else FAIL)
        rep.add("consistency", status,
                f"DOCX and PDF content match ({recall_d:.1%} / {recall_p:.1%} of words).",
                ([f"only in DOCX: {', '.join(missing_tok)}"] if missing_tok else [])
                + ([f"only in PDF: {', '.join(extra_tok)}"] if extra_tok else []))

    # 12. layout heuristics
    if pdf_info is not None:
        notes = list(pdf_info.out_of_bounds)
        status = FAIL if notes else PASS
        if pdf_info.page_count > 1:
            last = len(pdf_info.page_texts[-1].strip())
            avg = sum(len(t.strip()) for t in pdf_info.page_texts[:-1]) / max(pdf_info.page_count - 1, 1)
            if avg and last < 0.08 * avg:
                notes.append("The last page is nearly empty; consider tightening the layout.")
                status = WARN if status == PASS else status
        rep.add("overflow", status, "No text outside the page area was detected." if status == PASS
                else "Layout issues were detected.", notes)
        if pdf_info.unembedded_fonts:
            rep.add("fonts", WARN, "Some PDF fonts are not embedded.", pdf_info.unembedded_fonts)
        else:
            rep.add("fonts", PASS, "All PDF fonts are embedded.")
        if missing_glyphs:
            rep.add("glyphs", FAIL, "Some characters cannot be drawn by the built-in PDF engine. Choose the "
                    "LibreOffice engine (with fonts for these characters installed) or remove them.",
                    sorted(missing_glyphs))
    # 13. hyperlinks
    expected_links = [c.url for c in doc.contacts if c.url and c.url.startswith("http")]
    if expected_links and docx_info is not None:
        missing_links = [u for u in expected_links if u not in docx_info.hyperlinks]
        rep.add("links_docx", WARN if missing_links else PASS,
                "Contact links are clickable in the Word file." if not missing_links
                else "Some contact links are not clickable in the Word file.", missing_links)
    if expected_links and pdf_info is not None:
        missing_links = [u for u in expected_links if u not in pdf_info.links]
        rep.add("links_pdf", WARN if missing_links else PASS,
                "Contact links are clickable in the PDF." if not missing_links
                else "Some contact links are not clickable in the PDF.", missing_links)

    rep.add("visual_review", SKIP,
            "Visual layout has not been inspected automatically. Review the preview before sending.")
    return rep


_DISTINCTIVE_FIELDS = {
    "title", "text", "problem", "approach", "architecture", "dataset", "results", "metrics", "limitations",
    "individual_contribution", "team_contribution", "approved_external_description", "approved_external_wording",
    "description", "outcome", "summary", "nature_of_duties", "abstract", "contribution", "methodology", "bullets",
}


def confidential_phrases_from(snapshot) -> list[str]:
    """Distinctive phrases from confidential records (and their descendants)."""
    from ris.domain.enums import Confidentiality

    phrases: list[str] = []
    for rec in snapshot.records.values():
        if snapshot.effective_confidentiality(rec) != Confidentiality.CONFIDENTIAL:
            continue
        payload = rec.payload()
        candidates = [rec.title]
        for k, v in payload.items():
            # Only distinctive free-text fields: shared values such as organisation,
            # location, role or tool names would cause false alarms.
            if k not in _DISTINCTIVE_FIELDS:
                continue
            if isinstance(v, str):
                candidates.append(v)
            elif isinstance(v, list):
                candidates.extend(x for x in v if isinstance(x, str))
        for c in candidates:
            c = " ".join((c or "").split())
            if len(c.split()) >= 3 or len(c) >= 20:
                phrases.append(" ".join(c.split()[:10]))
    return sorted(set(phrases))
