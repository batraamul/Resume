"""Importers for CSV, plain text, DOCX and PDF (IMP-02/03/05, VAC-02).

Every importer produces an ImportPreview of candidate records. Nothing is saved
until the user commits the preview, and committed records are *unconfirmed*
and classified *Requires review*. Files are size-limited and parsed defensively.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ris.domain import registry
from ris.domain.enums import RecordKind
from ris.errors import ImportFailed
from ris.services.duplicates import match_candidate
from ris.services.portable import ImportCandidate, ImportPreview
from ris.storage.repository import RecordRepository, format_validation_error
from ris.util import new_id

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
MAX_PDF_PAGES = 60
MAX_DOCX_UNCOMPRESSED = 200 * 1024 * 1024
CSV_KINDS = (RecordKind.SKILL, RecordKind.PUBLICATION, RecordKind.PROJECT, RecordKind.POSITION, RecordKind.EDUCATION,
             RecordKind.ACTIVITY)


def _check_size(path: Path) -> None:
    size = Path(path).stat().st_size
    if size == 0:
        raise ImportFailed("The file is empty.")
    if size > MAX_FILE_BYTES:
        raise ImportFailed(f"The file is too large ({size // (1024 * 1024)} MB; the limit is 20 MB).")


# --------------------------------------------------------------------------- text extraction


def extract_text(path: Path) -> str:
    """Plain text from a .txt/.md, .docx or .pdf file (defensive, size-limited)."""
    path = Path(path)
    _check_size(path)
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md", ".text", ".csv"):
        raw = path.read_bytes()
        for enc in ("utf-8-sig", "utf-16", "cp1252"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ImportFailed("The text file's encoding is not recognised.")
    elif suffix == ".docx":
        text = _docx_text(path)
    elif suffix == ".pdf":
        text = _pdf_text(path)
    else:
        raise ImportFailed("Supported files: .txt, .md, .docx and .pdf.")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text[:MAX_TEXT_CHARS]


def _docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            total = sum(i.file_size for i in zf.infolist())
            if total > MAX_DOCX_UNCOMPRESSED:
                raise ImportFailed("The Word file expands to an unusually large size and was rejected.")
            if "word/document.xml" not in zf.namelist():
                raise ImportFailed("This is not a valid Word (.docx) file.")
    except zipfile.BadZipFile as exc:
        raise ImportFailed("This is not a valid Word (.docx) file.") from exc
    try:
        from docx import Document

        d = Document(str(path))
    except Exception as exc:  # noqa: BLE001 - parser errors are user-facing import failures
        raise ImportFailed("The Word file could not be read.", detail=str(exc)[:200]) from exc
    lines: list[str] = []
    from ris.rendering.extract import W_NS, _para_text

    for p in d.element.body.iter(W_NS + "p"):
        t = _para_text(p).strip()
        if t:
            lines.append(t)
    return "\n".join(lines)


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise ImportFailed("The PDF is password-protected; remove the protection and try again.")
        pages = reader.pages[:MAX_PDF_PAGES]
        text = "\n".join((p.extract_text() or "") for p in pages)
    except ImportFailed:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ImportFailed("The PDF could not be read.", detail=str(exc)[:200]) from exc
    if not text.strip():
        raise ImportFailed("No text could be extracted. The PDF may be a scanned image (OCR is not supported).")
    return text


# --------------------------------------------------------------------------- CSV


@dataclass
class CsvMapping:
    kind: RecordKind
    columns: dict[str, str] = field(default_factory=dict)  # csv column → payload field


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    _check_size(path)
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = []
    for i, row in enumerate(reader):
        if i >= 5000:
            break
        rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items() if k})
    return [h.strip() for h in (reader.fieldnames or []) if h], rows


def suggest_mapping(kind: RecordKind, headers: list[str]) -> dict[str, str]:
    model = registry.model_for(kind)
    fields = {name: (fi.title or name) for name, fi in model.model_fields.items() if name != "custom"}
    synonyms = {"title": ["name", "project", "paper"], "name": ["skill", "title"], "designation": ["position", "role", "post"],
                "organisation": ["organization", "employer", "company"], "start": ["from", "start date"],
                "end": ["to", "end date"], "degree": ["qualification"], "institution": ["college", "university"],
                "venue": ["journal", "conference"], "date": ["year"], "category": ["type", "group"]}
    out: dict[str, str] = {}
    for h in headers:
        hn = re.sub(r"[^a-z0-9]+", " ", h.lower()).strip()
        best = None
        for fname, title in fields.items():
            cands = {fname.replace("_", " "), title.lower(), *synonyms.get(fname, [])}
            if hn in cands:
                best = fname
                break
        if best and best not in out.values():
            out[h] = best
    return out


def preview_csv(repo: RecordRepository, path: Path, mapping: CsvMapping) -> ImportPreview:
    headers, rows = read_csv(path)
    del headers
    existing = repo.list(mapping.kind)
    model = registry.model_for(mapping.kind)
    cands: list[ImportCandidate] = []
    for i, row in enumerate(rows, start=1):
        payload: dict[str, Any] = {}
        for col, fname in mapping.columns.items():
            if fname and col in row and row[col] != "":
                payload[fname] = row[col]
        if not payload:
            continue
        errors: list[str] = []
        title = ""
        try:
            obj = model.model_validate(payload)
            title = obj.display_title()
        except ValidationError as exc:
            errors = [f"Row {i}: {m}" for m in format_validation_error(model, exc)]
            title = str(next(iter(payload.values())))
        dup = match_candidate(mapping.kind, payload, existing) if not errors else None
        cands.append(ImportCandidate(source_id=new_id(), kind=mapping.kind, parent_source_id=None, data=payload,
                                     verification="unconfirmed", confidentiality="review", title=title, errors=errors,
                                     duplicate=dup, include=not errors and dup is None))
    return ImportPreview(cands, label=f"CSV import: {Path(path).name}")


# --------------------------------------------------------------------------- CV text heuristics

_SECTION_HEADS = [
    (RecordKind.POSITION, re.compile(r"^(?:professional\s+)?(?:experience|employment(?:\s+history)?|work history|"
                                     r"appointments|career(?:\s+history)?)\b", re.I)),
    (RecordKind.EDUCATION, re.compile(r"^(?:education(?:al qualifications?)?|qualifications|academic)\b", re.I)),
    (RecordKind.SKILL, re.compile(r"^(?:(?:technical|key|core)\s+)?(?:skills|competencies|expertise)\b", re.I)),
    (RecordKind.PUBLICATION, re.compile(r"^(?:publications?|papers|research outputs?)\b", re.I)),
    (RecordKind.PROJECT, re.compile(r"^(?:(?:key|major|research)\s+)?projects?\b", re.I)),
    (RecordKind.ACTIVITY, re.compile(r"^(?:awards?|honou?rs|achievements|memberships?|leadership|committees|"
                                     r"responsibilities)\b", re.I)),
    (RecordKind.SUMMARY, re.compile(r"^(?:summary|profile|professional summary|objective|about me)\b", re.I)),
]
_DATE_RANGE = re.compile(r"((?:[A-Za-z]{3,9}\.?\s+)?\d{4})\s*(?:-|–|—|to)\s*((?:[A-Za-z]{3,9}\.?\s+)?\d{4}|present|"
                         r"till date|current|now)", re.I)
_BULLET = re.compile(r"^\s*(?:[••\-\*–▪›]|\d{1,2}[.)])\s+")
_DEGREE = re.compile(r"\b(ph\.?\s?d\.?|m\.?\s?tech\.?|b\.?\s?tech\.?|m\.?\s?e\.|b\.?\s?e\.|m\.?\s?sc\.?|b\.?\s?sc\.?|"
                     r"mca|mba|diploma|master'?s?|bachelor'?s?)(?![a-z])", re.I)
_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def _level_for(text: str) -> str:
    t = text.lower().replace(" ", "")
    if "ph.d" in t or "phd" in t or "doctor" in t:
        return "doctorate"
    if re.search(r"m\.?tech|m\.?e\.|m\.?sc|mca|mba|master", t):
        return "masters"
    if re.search(r"b\.?tech|b\.?e\.|b\.?sc|bachelor", t):
        return "bachelors"
    if "diploma" in t:
        return "diploma"
    return "other"


def _norm_date(token: str) -> str:
    from ris.domain import dates

    token = token.strip()
    if token.lower() in ("present", "till date", "current", "now"):
        return ""
    try:
        return dates.normalize(token)
    except ValueError:
        m = _YEAR.search(token)
        return m.group(0) if m else ""


def parse_cv_text(text: str) -> list[tuple[RecordKind, dict[str, Any], int | None]]:
    """Heuristically split CV text into (kind, payload, parent_index) candidates."""
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[tuple[RecordKind, dict[str, Any], int | None]] = []
    section: RecordKind | None = None
    current_parent: int | None = None
    for line in lines:
        if not line:
            continue
        bare = _BULLET.sub("", line).strip().rstrip(":")
        head = next((k for k, rx in _SECTION_HEADS if rx.match(bare) and len(bare) < 60), None)
        if head is not None and not _DATE_RANGE.search(bare):
            section = head
            current_parent = None
            continue
        if section is None:
            continue
        is_bullet = bool(_BULLET.match(line))
        if section == RecordKind.POSITION:
            m = _DATE_RANGE.search(bare)
            if m and not is_bullet:
                before = (bare[: m.start()] + bare[m.end():]).strip(" ,|–-()")
                parts = [p.strip() for p in re.split(r"\s*(?:,|\||–|—| at )\s*", before) if p.strip()]
                payload = {"designation": parts[0] if parts else before[:80],
                           "organisation": parts[1] if len(parts) > 1 else "",
                           "start": _norm_date(m.group(1))}
                end_tok = m.group(2)
                if end_tok.lower() in ("present", "till date", "current", "now"):
                    payload["is_current"] = True
                else:
                    payload["end"] = _norm_date(end_tok)
                out.append((RecordKind.POSITION, payload, None))
                current_parent = len(out) - 1
            elif current_parent is not None:
                out.append((RecordKind.BULLET, {"text": bare}, current_parent))
        elif section == RecordKind.EDUCATION:
            if _DEGREE.search(bare):
                yrs = re.findall(r"\b(?:19|20)\d{2}\b", bare)
                rest = re.sub(r"\b(?:19|20)\d{2}\b", "", _DEGREE.sub("", bare, count=1))
                parts = [x.strip(" .-–()") for x in rest.split(",") if x.strip(" .-–()")]
                discipline = institution = ""
                for part in parts:
                    part = re.sub(r"^(?:in|of)\s+", "", part, flags=re.I)
                    if re.search(r"institut|college|university|school|academy|\biit\b|\bnit\b", part, re.I) \
                            and not institution:
                        institution = part
                    elif not discipline:
                        discipline = part
                    elif not institution:
                        institution = part
                payload = {"degree": _DEGREE.search(bare).group(0), "level": _level_for(bare),
                           "discipline": discipline[:120], "institution": institution[:120],
                           "end": yrs[-1] if yrs else "", "status": "completed"}
                if re.search(r"\b(?:ongoing|pursuing|expected)\b", bare, re.I):
                    payload["status"] = "ongoing"
                    payload["end"] = ""
                out.append((RecordKind.EDUCATION, payload, None))
        elif section == RecordKind.SKILL:
            for part in re.split(r"[,;|•·]", re.sub(r"^[^:]{1,40}:\s*", "", bare)):
                part = part.strip()
                if 1 < len(part) <= 60:
                    out.append((RecordKind.SKILL, {"name": part}, None))
        elif section == RecordKind.PUBLICATION:
            title_m = re.search(r"[\"“](.+?)[\"”]", bare)
            status = "published"
            # Look for status words outside the title so a title cannot change the status.
            low = (bare[: title_m.start()] + bare[title_m.end():]).lower() if title_m else bare.lower()
            if "under review" in low:
                status = "under_review"
            elif "submitted" in low:
                status = "submitted"
            elif "accepted" in low or "in press" in low:
                status = "accepted"
            elif "preparation" in low:
                status = "draft"
            yrs = re.findall(r"\b(?:19|20)\d{2}\b", bare)
            out.append((RecordKind.PUBLICATION, {"title": (title_m.group(1) if title_m else bare)[:400].rstrip(",."),
                                                 "authors": bare[: title_m.start()].strip(" ,") if title_m else "",
                                                 "status": status, "date": yrs[-1] if yrs else ""}, None))
        elif section == RecordKind.PROJECT:
            if not is_bullet or current_parent is None:
                out.append((RecordKind.PROJECT, {"title": bare[:200]}, None))
                current_parent = len(out) - 1
            else:
                out.append((RecordKind.BULLET, {"text": bare}, current_parent))
        elif section == RecordKind.ACTIVITY:
            atype = "award" if re.search(r"award|honou?r|medal|prize", bare, re.I) else (
                "membership" if re.search(r"member", bare, re.I) else "other")
            yrs = re.findall(r"\b(?:19|20)\d{2}\b", bare)
            out.append((RecordKind.ACTIVITY, {"activity_type": atype, "title": bare[:200],
                                              "start": yrs[0] if yrs else ""}, None))
        elif section == RecordKind.SUMMARY:
            if out and out[-1][0] == RecordKind.SUMMARY:
                out[-1][1]["text"] += " " + bare
            else:
                out.append((RecordKind.SUMMARY, {"focus": "general", "text": bare}, None))
    return out


def preview_text(repo: RecordRepository, text: str, label: str = "Imported text") -> ImportPreview:
    parsed = parse_cv_text(text)
    existing = repo.list()
    cands: list[ImportCandidate] = []
    ids: list[str] = []
    for kind, payload, parent_idx in parsed:
        sid = new_id()
        ids.append(sid)
        model = registry.model_for(kind)
        errors: list[str] = []
        try:
            title = model.model_validate(payload).display_title()
        except ValidationError as exc:
            errors = format_validation_error(model, exc)
            title = str(next(iter(payload.values()), kind.value))
        parent = ids[parent_idx] if parent_idx is not None else None
        dup = match_candidate(kind, payload, existing) if (not errors and kind != RecordKind.BULLET) else None
        cands.append(ImportCandidate(sid, kind, parent, payload, "unconfirmed", "review", title, errors, dup,
                                     include=not errors and dup is None))
    return ImportPreview(cands, label=label)


def preview_file(repo: RecordRepository, path: Path) -> ImportPreview:
    return preview_text(repo, extract_text(path), label=f"Imported from {Path(path).name}")


def vacancy_from_file(path: Path) -> dict[str, str]:
    """Vacancy fields from a notice file: the text is stored as untrusted raw text."""
    from ris.intelligence.vacancy import suggest_fields

    text = extract_text(path)
    fields = {"raw_text": text, "source_file": Path(path).name}
    fields.update(suggest_fields(text))
    first = next((ln.strip() for ln in text.splitlines() if 8 < len(ln.strip()) < 140), "")
    fields.setdefault("title", first)
    return fields
