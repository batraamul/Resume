"""Non-sensitive logging (SEC-02).

Policy: log events, record ids and kinds, counts and timings — never record
contents, resume text, API keys, tokens or passwords. As defence in depth a
redaction filter masks e-mail addresses, phone numbers, bearer tokens,
API-key shapes and long secrets before anything is written.
"""

from __future__ import annotations

import logging
import logging.handlers
import re
from pathlib import Path

from ris.paths import ensure_private_dir

_PATTERNS = [
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer [REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{10,}"), "[REDACTED-KEY]"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{10,}"), "[REDACTED-KEY]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{20,}"), "[REDACTED-KEY]"),
    (re.compile(r"\bya29\.[0-9A-Za-z_.-]{10,}"), "[REDACTED-TOKEN]"),
    (re.compile(r"\b1//[0-9A-Za-z_-]{20,}"), "[REDACTED-TOKEN]"),
    (re.compile(r"(?i)(refresh_token|access_token|client_secret|api[_-]?key|password|passphrase)"
                r"(['\"]?\s*[:=]\s*['\"]?)[^\s'\",}]+"), r"\1\2[REDACTED]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"(?<!\w)\+?\d[\d\s()-]{8,}\d(?!\w)"), "[PHONE]"),
    (re.compile(r"\b[A-Za-z0-9+/_-]{40,}={0,2}"), "[REDACTED-LONG]"),
]


def redact(text: str) -> str:
    for rx, rep in _PATTERNS:
        text = rx.sub(rep, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - never break logging
            msg = str(record.msg)
        record.msg = redact(msg)
        record.args = ()
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


class _RedactingFormatter(logging.Formatter):
    def formatException(self, ei) -> str:  # noqa: N802 - logging API
        return redact(super().formatException(ei))


def configure_logging(log_dir: Path, level: str = "INFO", console: bool = False) -> Path:
    ensure_private_dir(log_dir)
    path = log_dir / "ris.log"
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_ris", False):
            root.removeHandler(h)
    fmt = _RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.addFilter(RedactingFilter())
    fh._ris = True  # type: ignore[attr-defined]
    root.addHandler(fh)
    if console:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        ch.addFilter(RedactingFilter())
        ch._ris = True  # type: ignore[attr-defined]
        root.addHandler(ch)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for noisy in ("PIL", "fontTools", "urllib3", "googleapiclient", "pypdf"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return path
