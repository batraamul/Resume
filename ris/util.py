"""Small, dependency-free helpers shared across layers."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any


def new_id() -> str:
    """Stable, globally unique record identifier (UUID4 hex)."""
    return uuid.uuid4().hex


def utc_now_iso() -> str:
    """Current UTC time as ISO-8601 with seconds precision and 'Z' suffix."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(obj: Any) -> str:
    """Deterministic JSON (sorted keys, compact) used for checksums and comparisons."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Any, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


_WS = re.compile(r"\s+")


def collapse_ws(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


def normalize_for_compare(text: str) -> str:
    """Normalise text for content comparisons between DOCX/PDF/IR.

    NFKC folds ligatures (ﬁ → fi); dashes and quotes are unified; whitespace
    collapsed; soft hyphens removed; case folded.
    """
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("­", "").replace("\u200b", "")
    t = re.sub(r"(?<=\w)/\s+(?=\w)", "/", t)  # URL wrapped after a slash
    t = re.sub(r"(?<=\w)-[ \t]*\n\s*(?=\w)", "-", t)  # compound or URL wrapped at its hyphen (no auto-hyphenation)
    t = re.sub(r"[‐-―−]", "-", t)
    t = re.sub(r"[‘’‚‛′]", "'", t)
    t = re.sub(r"[“”„‟″]", '"', t)
    t = t.replace("•", " ").replace("▪", " ").replace("‣", " ")
    return collapse_ws(t).casefold()


def safe_filename(name: str, max_len: int = 120) -> str:
    """Make a portable filename component (keeps letters, digits, dash, underscore, dot, space)."""
    name = unicodedata.normalize("NFKC", name or "").strip()
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", name)
    name = re.sub(r"\s+", " ", name)
    name = name.strip(" .")
    if not name:
        name = "document"
    return name[:max_len]


def chunked(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def truncate(text: str, length: int = 80) -> str:
    text = collapse_ws(text)
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"
