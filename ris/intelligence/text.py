"""Text normalisation and tokenisation shared by matching, scoring and validation."""

from __future__ import annotations

import re
import unicodedata

_KEEP = re.compile(r"[^0-9a-z+#\s]")
_SPACES = re.compile(r"\s+")
_NUMBER = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)(\s?(?:%|x|×|ms|s|fps|db|hz|khz|mhz|ghz|km|m|mm|kg|g|w|kw|mw|years?|months?|days?|hours?|lakh|crore|k|m|b))?(?![\w])",
                     re.IGNORECASE)


def normalize(text: str) -> str:
    """Lower-case, fold accents, turn punctuation into spaces (keeping + and # for C++/C#)."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = t.lower().replace("–", " ").replace("—", " ")
    t = _KEEP.sub(" ", t)
    return _SPACES.sub(" ", t).strip()


def tokens(text: str) -> list[str]:
    n = normalize(text)
    return n.split() if n else []


def stem(token: str) -> str:
    """Very light English stemming adequate for keyword overlap (systems → system)."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "us", "is", "os")):
        return token[:-1]
    return token


def content_tokens(text: str, stopwords: set[str]) -> list[str]:
    out: list[str] = []
    for t in tokens(text):
        if t in stopwords:
            continue
        if len(t) < 3 and not any(c.isdigit() for c in t) and t not in ("ai", "ml", "rf", "c++", "c#", "ui"):
            continue
        out.append(stem(t))
    return out


def numbers_in(text: str) -> list[str]:
    """Numeric facts (with units) mentioned in text, normalised (e.g. '4x', '20 ms', '35%')."""
    out: list[str] = []
    for m in _NUMBER.finditer(text or ""):
        num = m.group(1).replace(",", "")
        unit = (m.group(2) or "").strip().lower().replace("×", "x")
        out.append(f"{num}{unit}")
    return out


def bare_numbers(text: str) -> set[str]:
    return {re.sub(r"[^\d.]", "", n).rstrip(".") for n in numbers_in(text) if re.sub(r"[^\d.]", "", n)}


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(])", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def first_sentence(text: str, max_len: int = 240) -> str:
    s = sentences(text)
    out = s[0] if s else (text or "").strip()
    return out if len(out) <= max_len else out[: max_len - 1].rstrip() + "…"
