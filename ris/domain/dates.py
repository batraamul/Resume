"""Partial dates (year, year-month or full date) used throughout the profile.

Career records often know only a year or a month. Stored values are ISO-like
strings: ``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD``. Empty string means unknown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_LONG = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_MONTH_LOOKUP = {m.lower(): i + 1 for i, m in enumerate(MONTHS_SHORT)}
_MONTH_LOOKUP.update({m.lower(): i + 1 for i, m in enumerate(MONTHS_LONG)})
_MONTH_LOOKUP["sept"] = 9

_ISO = re.compile(r"^(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?$")
_SLASH_MY = re.compile(r"^(\d{1,2})[/.-](\d{4})$")
_SLASH_DMY = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
_YEAR_SLASH_M = re.compile(r"^(\d{4})[/.](\d{1,2})$")
_NAME_Y = re.compile(r"^([A-Za-z]{3,9})\.?,?\s+(\d{4})$")
_D_NAME_Y = re.compile(r"^(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})$")

DATE_STYLES = ("mon_year", "month_year", "mm_yyyy", "year", "iso")

MIN_YEAR = 1900
MAX_YEAR = 2100


@dataclass(frozen=True, order=True)
class PartialDate:
    year: int
    month: int | None = None
    day: int | None = None

    def __post_init__(self) -> None:
        if not (MIN_YEAR <= self.year <= MAX_YEAR):
            raise ValueError(f"Year {self.year} is outside {MIN_YEAR}–{MAX_YEAR}")
        if self.month is not None and not (1 <= self.month <= 12):
            raise ValueError(f"Month {self.month} is not between 1 and 12")
        if self.day is not None:
            if self.month is None:
                raise ValueError("A day requires a month")
            date(self.year, self.month, self.day)  # raises ValueError if impossible

    # ------------------------------------------------------------------ parsing
    @classmethod
    def parse(cls, text: str | None) -> PartialDate | None:
        """Parse common date spellings. Returns None for empty input.

        Accepted: 2019, 2019-03, 2019-03-15, 03/2019, 15/03/2019 (day first),
        2019/03, Mar 2019, March 2019, 15 March 2019.
        """
        if text is None:
            return None
        s = str(text).strip()
        if not s:
            return None
        m = _ISO.match(s)
        if m:
            y, mo, d = m.groups()
            return cls(int(y), int(mo) if mo else None, int(d) if d else None)
        m = _SLASH_MY.match(s)
        if m:
            return cls(int(m.group(2)), int(m.group(1)))
        m = _SLASH_DMY.match(s)
        if m:
            return cls(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        m = _YEAR_SLASH_M.match(s)
        if m:
            return cls(int(m.group(1)), int(m.group(2)))
        m = _NAME_Y.match(s)
        if m and m.group(1).lower() in _MONTH_LOOKUP:
            return cls(int(m.group(2)), _MONTH_LOOKUP[m.group(1).lower()])
        m = _D_NAME_Y.match(s)
        if m and m.group(2).lower() in _MONTH_LOOKUP:
            return cls(int(m.group(3)), _MONTH_LOOKUP[m.group(2).lower()], int(m.group(1)))
        raise ValueError(
            f"Unrecognised date '{s}'. Use a year (2019), year-month (2019-03) or full date (2019-03-15)."
        )

    @classmethod
    def from_date(cls, d: date) -> PartialDate:
        return cls(d.year, d.month, d.day)

    @classmethod
    def today(cls) -> PartialDate:
        return cls.from_date(date.today())

    # ------------------------------------------------------------------ output
    def iso(self) -> str:
        if self.month is None:
            return f"{self.year:04d}"
        if self.day is None:
            return f"{self.year:04d}-{self.month:02d}"
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"

    def sort_key(self) -> tuple[int, int, int]:
        return (self.year, self.month or 0, self.day or 0)

    def format(self, style: str = "mon_year") -> str:
        if style == "iso":
            return self.iso()
        if style == "year" or self.month is None:
            return str(self.year)
        if style == "month_year":
            return f"{MONTHS_LONG[self.month - 1]} {self.year}"
        if style == "mm_yyyy":
            return f"{self.month:02d}/{self.year}"
        return f"{MONTHS_SHORT[self.month - 1]} {self.year}"

    def earliest(self) -> date:
        return date(self.year, self.month or 1, self.day or 1)

    def latest(self) -> date:
        month = self.month or 12
        if self.day:
            return date(self.year, month, self.day)
        # last day of the month
        nxt = date(self.year + (month == 12), (month % 12) + 1, 1)
        return date.fromordinal(nxt.toordinal() - 1)

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.iso()


def normalize(text: str | None) -> str:
    """Validate and normalise a user-entered partial date; '' for empty.

    Raises ValueError with a readable message for invalid input.
    """
    pd = PartialDate.parse(text)
    return pd.iso() if pd else ""


def parse_or_none(text: str | None) -> PartialDate | None:
    """Lenient parse: returns None instead of raising."""
    try:
        return PartialDate.parse(text)
    except ValueError:
        return None


def format_date(text: str | None, style: str = "mon_year") -> str:
    pd = parse_or_none(text)
    return pd.format(style) if pd else ""


def format_range(
    start: str | None,
    end: str | None,
    is_current: bool = False,
    style: str = "mon_year",
    present_label: str = "Present",
    dash: str = "–",
) -> str:
    """Format a date range such as ``Mar 2019 – Present``.

    Year-only ranges in the same year collapse to a single year.
    """
    s = parse_or_none(start)
    e = parse_or_none(end)
    left = s.format(style) if s else ""
    if is_current:
        right = present_label
    else:
        right = e.format(style) if e else ""
    if left and right:
        if left == right:
            return left
        return f"{left} {dash} {right}"
    if left and not right:
        return left
    if right and not left:
        return right
    return ""


def range_sort_key(start: str | None, end: str | None, is_current: bool) -> tuple:
    """Key for reverse-chronological ordering: current first, then by end, then start."""
    s = parse_or_none(start)
    e = parse_or_none(end)
    end_key = (9999, 99, 99) if is_current else (e.sort_key() if e else (s.sort_key() if s else (0, 0, 0)))
    start_key = s.sort_key() if s else (0, 0, 0)
    return (end_key, start_key)


def conservative_months(start: str | None, end: str | None, is_current: bool, today: date | None = None) -> int | None:
    """Minimum whole months between two partial dates (conservative).

    Uses the *latest* possible start and the *earliest* possible end so that
    derived experience totals never overstate the record. Returns None when
    the start is unknown or the end is unknown and the role is not current.
    """
    s = parse_or_none(start)
    if s is None:
        return None
    if is_current:
        end_date = today or date.today()
    else:
        e = parse_or_none(end)
        if e is None:
            return None
        end_date = e.earliest()
    start_date = s.latest()
    months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
    if end_date.day < start_date.day:
        months -= 1
    return max(months, 0)


def is_future(text: str | None, today: date | None = None) -> bool:
    pd = parse_or_none(text)
    if pd is None:
        return False
    return pd.earliest() > (today or date.today())
