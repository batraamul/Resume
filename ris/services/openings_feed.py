"""Import an openings feed (the JSON list kept by the weekly Scientist F/G opening scan) as job opportunities.

Feed format (``e-diary-jobs-feed-YYYY-MM-DD.json``)::

    {"fetchedAt": "...", "items": [{"id", "org", "post", "level", "mode", "area", "location", "lastDate",
      "published", "eligibility", "vacancies", "link", "source", "verified", "notes"}], "sources": [...]}

The feed is treated as data. Each item becomes (or updates) a Vacancy record; items whose closing date has passed
are skipped. Nothing about the user is read from or written to the feed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ris.domain import dates
from ris.domain.enums import RecordKind, RecruitmentMode
from ris.errors import ImportFailed as FeedError

FEED_PREFIX = "e-diary-jobs-feed-"
SOURCE_TAG = "openings-feed:"
MAX_ITEMS = 500

_MODES = {
    "direct recruitment": RecruitmentMode.DIRECT,
    "deputation": RecruitmentMode.DEPUTATION,
    "deputation / absorption": RecruitmentMode.DEPUTATION,
    "deputation/absorption": RecruitmentMode.DEPUTATION,
    "absorption": RecruitmentMode.ABSORPTION,
    "lateral entry": RecruitmentMode.LATERAL,
    "contract": RecruitmentMode.CONTRACT,
}


@dataclass
class FeedResult:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    expired: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    fetched_at: str = ""
    source: str = ""

    def summary(self) -> str:
        bits = [f"{len(self.added)} added", f"{len(self.updated)} updated", f"{len(self.unchanged)} unchanged"]
        if self.expired:
            bits.append(f"{len(self.expired)} closed (skipped)")
        if self.invalid:
            bits.append(f"{len(self.invalid)} unreadable (skipped)")
        when = f" (list of {self.fetched_at[:10]})" if self.fetched_at else ""
        return "Openings imported" + when + ": " + ", ".join(bits) + "."


def newest_feed(folder: Path) -> Path | None:
    """The most recent e-diary-jobs-feed-*.json in a folder (for example a Google Drive folder synced to disk)."""
    files = sorted(Path(folder).glob(f"{FEED_PREFIX}*.json"))
    return files[-1] if files else None


def load_feed(path: Path) -> dict:
    path = Path(path)
    if path.is_dir():
        found = newest_feed(path)
        if found is None:
            raise FeedError("No openings list (e-diary-jobs-feed-*.json) was found in that folder.")
        path = found
    try:
        if path.stat().st_size > 5_000_000:
            raise FeedError("The openings file is too large to be an openings list.")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeedError("The openings file could not be read as JSON.", detail=str(exc)) from exc
    if isinstance(data, dict) and isinstance(data.get("data"), dict) and "items" in data["data"]:
        data = data["data"]  # an export of the online copy wraps the list
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise FeedError("This file is not an openings list: it has no 'items'.")
    data["_path"] = str(path)
    return data


def _text(item: dict, key: str, limit: int = 4000) -> str:
    v = item.get(key)
    return "" if v is None else str(v).strip()[:limit]


def item_to_vacancy(item: dict) -> dict:
    """Vacancy fields for one feed item (pure function, used by the importer and tests)."""
    level = _text(item, "level", 20)
    mode = _MODES.get(_text(item, "mode").lower(), RecruitmentMode.OTHER if item.get("mode") else RecruitmentMode.UNKNOWN)
    link = _text(item, "link", 1000)
    notes = []
    for label_, key in (("Area", "area"), ("Location", "location"), ("Vacancies", "vacancies"),
                        ("Published", "published"), ("Source", "source")):
        if _text(item, key):
            notes.append(f"{label_}: {_text(item, key)}")
    if item.get("verified") is False:
        notes.append("The official notice could not be opened when this list was made; check it before applying.")
    if _text(item, "notes"):
        notes.append(_text(item, "notes"))
    last = _text(item, "lastDate", 10)
    return {
        "title": _text(item, "post", 300) or "Untitled post",
        "employer": _text(item, "org", 300),
        "url": link if link.startswith("https://") else "",
        "recruitment_mode": mode.value,
        "pay_level": f"Level {level}" if level and level != "other" else "",
        "deadline": last if dates.parse_or_none(last) else "",
        "essential_qualifications": _text(item, "eligibility"),
        "application_notes": "\n".join(notes),
        "raw_text": "\n".join(x for x in (_text(item, "post"), _text(item, "eligibility"), _text(item, "notes")) if x),
        "source_file": SOURCE_TAG + _text(item, "id", 120),
    }


def import_feed(repo, path: Path, today: date | None = None) -> FeedResult:
    data = load_feed(path)
    today = today or date.today()
    res = FeedResult(fetched_at=str(data.get("fetchedAt") or ""), source=data["_path"])
    existing = {}
    for rec in repo.list(RecordKind.VACANCY):
        tag = rec.data.source_file or ""
        if tag.startswith(SOURCE_TAG):
            existing[tag] = rec
        elif rec.data.url:
            existing.setdefault("url:" + rec.data.url, rec)
    for item in data["items"][:MAX_ITEMS]:
        if not isinstance(item, dict) or not item.get("id") or not item.get("post"):
            res.invalid.append(str(item.get("id") if isinstance(item, dict) else item)[:60])
            continue
        fields = item_to_vacancy(item)
        pd = dates.parse_or_none(fields["deadline"])
        if pd is not None and pd.latest() < today:
            res.expired.append(fields["title"])
            continue
        rec = existing.get(fields["source_file"]) or (existing.get("url:" + fields["url"]) if fields["url"] else None)
        if rec is None:
            repo.create(RecordKind.VACANCY, fields, origin="imported")
            res.added.append(fields["title"])
            continue
        current = rec.payload()
        changes = {k: v for k, v in fields.items() if k != "raw_text" and v and current.get(k) != v}
        if changes:
            repo.patch(rec.id, **changes)
            res.updated.append(fields["title"])
        else:
            res.unchanged.append(fields["title"])
    return res
