"""Job Portal Kit: profile text for LinkedIn, Naukri and Indeed built from your confirmed facts, checked against
each portal's limits, plus checks of resume files against portal upload rules.

Only confirmed facts approved for professional use (or public) are used. Nothing is invented: headlines and
summaries rearrange your own titles, summaries, expertise, skills and achievement statements.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from ris.domain import dates
from ris.domain.enums import Confidentiality, Proficiency, RecordKind, Verification
from ris.resources import config_dir

ALLOWED = (Confidentiality.PUBLIC, Confidentiality.APPROVED)
PROFICIENCY_RANK = {p.value: i for i, p in enumerate(
    [Proficiency.EXPERT, Proficiency.ADVANCED, Proficiency.PROFICIENT, Proficiency.WORKING, Proficiency.FAMILIAR,
     Proficiency.NOT_RATED])}


@lru_cache(maxsize=2)
def load_portals(path: str | None = None) -> dict[str, Any]:
    return json.loads(Path(path or (config_dir() / "job_portals.json")).read_text(encoding="utf-8"))


def portal(portal_id: str) -> dict[str, Any]:
    return next(p for p in load_portals()["portals"] if p["id"] == portal_id)


@dataclass
class KitField:
    portal: str
    field_id: str
    label: str
    text: str = ""
    items: list[str] = field(default_factory=list)
    limit: int | None = None
    limit_kind: str = ""  # hard | advice | list | text
    limit_words: tuple[int, int] | None = None
    note: str = ""
    source_ids: list[str] = field(default_factory=list)

    @property
    def value(self) -> str:
        return self.text if self.text else "\n".join(self.items)

    @property
    def chars(self) -> int:
        return len(self.text)

    @property
    def words(self) -> int:
        return len(self.text.split())

    def status(self) -> tuple[str, str]:
        """(level, message) where level is ok, warn or over."""
        if self.items and self.limit:
            n = len(self.items)
            if n > self.limit:
                return ("over" if self.limit_kind == "hard" else "warn", f"{n} items; the limit is {self.limit}.")
            return "ok", f"{n} of {self.limit} items."
        if self.items:
            return "ok", f"{len(self.items)} items."
        if self.limit_words:
            lo, hi = self.limit_words
            w = self.words
            if w < lo:
                return "warn", f"{w} words; {lo}–{hi} words is recommended."
            if w > hi:
                return "warn", f"{w} words; {lo}–{hi} words is recommended."
            return "ok", f"{w} words ({lo}–{hi} recommended)."
        if self.limit:
            if self.chars > self.limit:
                level = "over" if self.limit_kind == "hard" else "warn"
                return level, f"{self.chars} characters; the {'limit' if level == 'over' else 'recommendation'} is " \
                              f"{self.limit}."
            return "ok", f"{self.chars} of {self.limit} characters."
        return "ok", f"{self.chars} characters."


def _fit(parts: list[str], limit: int, sep: str = " | ") -> str:
    """Join parts with sep, dropping trailing parts (never cutting a word) to stay within limit."""
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        candidate = sep.join([*out, p])
        if len(candidate) <= limit:
            out.append(p)
    if not out and parts:
        first = next(p for p in parts if p)
        return first[:limit].rsplit(" ", 1)[0] if len(first) > limit else first
    return sep.join(out)


def _join_and(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " & " + items[-1]


class _Facts:
    def __init__(self, snap, relevance=None) -> None:
        self.snap = snap
        self.rel = relevance

    def ok(self, rec) -> bool:
        return (self.snap.effective_verification(rec) != Verification.UNCONFIRMED
                and self.snap.effective_confidentiality(rec) in ALLOWED)

    def of(self, kind: RecordKind) -> list:
        return [r for r in self.snap.of(kind) if self.ok(r)]

    def positions(self) -> list:
        ps = [p for p in self.of(RecordKind.POSITION) if p.data.designation or p.data.organisation]
        ps.sort(key=lambda p: dates.range_sort_key(p.data.start, p.data.end, p.data.is_current), reverse=True)
        return ps

    def summary(self) -> Any:
        sums = [s for s in self.of(RecordKind.SUMMARY) if s.data.text]
        if not sums:
            return None
        if self.rel is not None and not self.rel.is_empty:
            sums.sort(key=lambda s: -self.rel.score_text(s.data.text))
            return sums[0]
        return next((s for s in sums if s.data.focus == "general"), sums[0])

    def expertise(self) -> list:
        return [e for e in self.of(RecordKind.EXPERTISE) if e.data.area]

    def skills(self) -> list:
        sk = [s for s in self.of(RecordKind.SKILL) if s.data.name and s.data.category != "languages"]
        if self.rel is not None and not self.rel.is_empty:
            sk.sort(key=lambda s: (-self.rel.score_record(s), PROFICIENCY_RANK.get(s.data.proficiency, 9)))
        else:
            sk.sort(key=lambda s: PROFICIENCY_RANK.get(s.data.proficiency, 9))
        return sk

    def achievements(self, parent, limit: int) -> list:
        kids = [b for b in self.snap.kids(parent.id, RecordKind.BULLET) if self.ok(b) and b.data.text]
        kids.sort(key=lambda b: (b.data.bullet_type not in ("achievement", "outcome", "deliverable"),))
        if self.rel is not None and not self.rel.is_empty:
            kids.sort(key=lambda b: -self.rel.score_text(b.data.text))
        return kids[:limit]

    def certifications(self) -> list:
        return [t for t in self.of(RecordKind.TRAINING)
                if t.data.title and t.data.training_type in ("certification", "licence", "language_test")
                and t.data.status != "planned"]

    def years_of_experience(self, today: date) -> int | None:
        starts = [dates.parse_or_none(p.data.start) for p in self.positions()]
        starts = [s for s in starts if s is not None]
        if not starts:
            return None
        first = min(starts, key=lambda s: s.sort_key())
        return max(0, today.year - first.year - (1 if (today.month < (first.month or 1)) else 0))


def _cert_line(t) -> str:
    d = t.data
    bits = [d.title]
    if d.provider:
        bits.append(d.provider)
    when = dates.format_date(d.end or d.start, "mon_year")
    if when:
        bits.append(when)
    line = " — ".join(bits[:2]) + (f" ({bits[2]})" if len(bits) > 2 else "")
    if d.credential_id:
        line += f" · Credential ID {d.credential_id}"
    return line


def build_kit(snap, *, relevance=None, today: date | None = None) -> dict[str, list[KitField]]:
    """Profile text for each portal, from confirmed and disclosable facts only."""
    today = today or date.today()
    f = _Facts(snap, relevance)
    p = snap.personal_data
    personal_ok = snap.personal is not None and f.ok(snap.personal)
    title = p.professional_title if personal_ok else ""
    positions = f.positions()
    current = next((x for x in positions if x.data.is_current), positions[0] if positions else None)
    org = ""
    if current is not None:
        org = current.data.short_name or current.data.organisation
    expertise = [e.data.area for e in f.expertise()]
    skills = f.skills()
    skill_names = [s.data.name for s in skills]
    top_topics = expertise[:3] or skill_names[:3]
    summary = f.summary()
    years = f.years_of_experience(today)
    lim = {fl["id"]: fl for fl in portal("linkedin")["fields"]}
    kit: dict[str, list[KitField]] = {}

    # LinkedIn ---------------------------------------------------------------------
    li: list[KitField] = []
    head_limit = lim["headline"]["limit"]
    headline = _fit([title, _join_and(top_topics), org], head_limit)
    li.append(KitField("linkedin", "headline", "Headline", text=headline, limit=head_limit, limit_kind="hard",
                       source_ids=[r.id for r in ([snap.personal] if personal_ok else [])]))
    about_parts: list[str] = []
    ids: list[str] = []
    if summary is not None:
        about_parts.append(summary.data.text.strip())
        ids.append(summary.id)
    if expertise:
        about_parts.append("Areas of expertise: " + ", ".join(expertise) + ".")
        ids += [e.id for e in f.expertise()]
    highlights = []
    for pos in positions[:2]:
        for b in f.achievements(pos, 3):
            highlights.append("• " + b.data.text.strip().rstrip(".") + ".")
            ids.append(b.id)
    about_limit = lim["about"]["limit"]
    while highlights:
        text = "\n\n".join(about_parts + (["Highlights:\n" + "\n".join(highlights)] if highlights else []))
        if len(text) <= about_limit:
            break
        highlights.pop()
    about = "\n\n".join(about_parts + (["Highlights:\n" + "\n".join(highlights)] if highlights else []))
    if len(about) > about_limit:
        about = about[:about_limit].rsplit(" ", 1)[0]
    li.append(KitField("linkedin", "about", "About", text=about, limit=about_limit, limit_kind="hard",
                       note=lim["about"].get("note", ""), source_ids=ids))
    exp_limit = lim["experience"]["limit"]
    for pos in positions[:5]:
        d = pos.data
        lines = [d.summary.strip()] if d.summary else []
        bl = f.achievements(pos, 5)
        lines += ["• " + b.data.text.strip() for b in bl]
        text = "\n".join(lines)
        while len(text) > exp_limit and len(lines) > 1:
            lines.pop()
            text = "\n".join(lines)
        rng = dates.format_range(d.start, d.end, d.is_current, "mon_year")
        li.append(KitField("linkedin", f"experience:{pos.id}",
                           f"Experience — {d.designation or 'Role'}, {d.organisation} ({rng})", text=text,
                           limit=exp_limit, limit_kind="hard", source_ids=[pos.id, *[b.id for b in bl]]))
    li.append(KitField("linkedin", "skills", "Skills (most relevant first)", items=skill_names[:50],
                       limit_kind="list", note=lim["skills"].get("note", ""), source_ids=[s.id for s in skills[:50]]))
    certs = f.certifications()
    if certs:
        li.append(KitField("linkedin", "certifications", "Licenses & certifications",
                           items=[_cert_line(t) for t in certs], limit_kind="list", source_ids=[t.id for t in certs]))
    kit["linkedin"] = li

    # Naukri -----------------------------------------------------------------------
    nk_fields = {fl["id"]: fl for fl in portal("naukri")["fields"]}
    nk: list[KitField] = []
    years_txt = f"{years}+ years" if years else ""
    nk_head_limit = nk_fields["resume_headline"]["limit"]
    nk_headline = _fit([title or (current.data.designation if current else ""), years_txt, _join_and(top_topics[:2])],
                       nk_head_limit)
    nk.append(KitField("naukri", "resume_headline", "Resume headline", text=nk_headline, limit=nk_head_limit,
                       limit_kind="advice", note=nk_fields["resume_headline"].get("note", ""),
                       source_ids=[snap.personal.id] if personal_ok else []))
    words_lo, words_hi = nk_fields["profile_summary"]["limit_words"]
    nk_parts: list[str] = []
    nk_ids: list[str] = []
    if summary is not None:
        nk_parts.append(summary.data.text.strip())
        nk_ids.append(summary.id)
    if expertise:
        nk_parts.append("Areas of expertise include " + _join_and(expertise[:6]) + ".")
    extra = [b for pos in positions[:2] for b in f.achievements(pos, 3)]
    for b in extra:
        candidate = " ".join([*nk_parts, b.data.text.strip().rstrip(".") + "."])
        if len(candidate.split()) > words_hi:
            break
        nk_parts.append(b.data.text.strip().rstrip(".") + ".")
        nk_ids.append(b.id)
    nk.append(KitField("naukri", "profile_summary", "Profile summary", text=" ".join(nk_parts),
                       limit_words=(words_lo, words_hi), limit_kind="advice", source_ids=nk_ids))
    nk.append(KitField("naukri", "key_skills", "Key skills", items=skill_names[:50],
                       limit=nk_fields["key_skills"]["limit"], limit_kind="hard",
                       note=nk_fields["key_skills"].get("note", ""), source_ids=[s.id for s in skills[:50]]))
    kit["naukri"] = nk

    # Indeed -----------------------------------------------------------------------
    ind: list[KitField] = [
        KitField("indeed", "headline", "Headline", text=title or (current.data.designation if current else ""),
                 limit_kind="text"),
        KitField("indeed", "summary", "Summary", text=summary.data.text.strip() if summary is not None else "",
                 limit_kind="text", source_ids=[summary.id] if summary is not None else []),
        KitField("indeed", "skills", "Skills", items=skill_names[:30], limit_kind="list",
                 source_ids=[s.id for s in skills[:30]]),
    ]
    kit["indeed"] = ind
    return kit


def kit_as_text(kit: dict[str, list[KitField]]) -> str:
    names = {p["id"]: p["name"] for p in load_portals()["portals"]}
    out: list[str] = []
    for pid, fields in kit.items():
        out.append(f"=== {names.get(pid, pid)} ===")
        for fl in fields:
            level, msg = fl.status()
            out.append(f"\n--- {fl.label} [{msg}] ---")
            out.append(fl.value or "(nothing yet — add confirmed facts to your profile)")
        out.append("")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- resume files


@dataclass
class FileCheck:
    level: str  # ok | warn | fail
    message: str


_GENERIC_NAMES = re.compile(r"^(resume|cv|document\d*|untitled|final|new)([ _-]?(v?\d+|final|copy))*$", re.I)


def check_file(path: Path, portal_id: str | None = None) -> list[FileCheck]:
    """Check a resume file against portal upload practice: type, size, readable text and file name."""
    path = Path(path)
    out: list[FileCheck] = []
    ext = path.suffix.lower().lstrip(".").upper()
    size_mb = path.stat().st_size / (1024 * 1024)
    portals = [portal(portal_id)] if portal_id else [p for p in load_portals()["portals"] if p.get("resume_max_mb")]
    for pt in portals:
        formats = pt.get("resume_formats") or []
        if formats and ext not in formats:
            out.append(FileCheck("fail", f"{pt['name']} accepts {', '.join(formats)}; this file is {ext}."))
        mx = pt.get("resume_max_mb")
        if mx and size_mb > mx:
            out.append(FileCheck("fail", f"{size_mb:.1f} MB is over the {mx} MB limit for {pt['name']}."))
    if size_mb <= 1:
        out.append(FileCheck("ok", f"{size_mb * 1024:.0f} KB — small enough for portals and email."))
    elif size_mb <= 2:
        out.append(FileCheck("warn", f"{size_mb:.1f} MB — fine for portals, but keep email attachments under 1 MB."))
    if ext == "PDF":
        try:
            from pypdf import PdfReader

            text = "".join((pg.extract_text() or "") for pg in PdfReader(str(path)).pages[:2])
            if len(text.strip()) < 200:
                out.append(FileCheck("fail", "The PDF has little or no selectable text (scanned or image-based); "
                                             "applicant tracking systems cannot read it."))
            else:
                out.append(FileCheck("ok", "The PDF contains selectable text."))
        except Exception:  # noqa: BLE001 - unreadable file is reported, not raised
            out.append(FileCheck("fail", "The PDF could not be read."))
    stem = path.stem
    if _GENERIC_NAMES.match(stem) or re.search(r"(final|v\d+)$", stem, re.I):
        out.append(FileCheck("warn", f"'{path.name}' is a generic name; use e.g. Firstname_Lastname_Resume.{ext.lower()}."))
    elif not re.search(r"resume|cv|bio-?data", stem, re.I):
        out.append(FileCheck("warn", f"Add 'Resume' or 'CV' to the file name so recruiters can find it "
                                     f"(e.g. Firstname_Lastname_Resume.{ext.lower()})."))
    else:
        out.append(FileCheck("ok", "Clear file name."))
    return out


def suggested_filename(full_name: str, ext: str, kind: str = "Resume") -> str:
    parts = [re.sub(r"[^A-Za-z0-9]", "", w) for w in (full_name or "").split()]
    parts = [w for w in parts if w and w.lower() not in ("dr", "mr", "mrs", "ms", "prof")]
    base = "_".join(parts) if parts else "My"
    return f"{base}_{kind}.{ext.lstrip('.')}"
