"""Per-workspace settings stored as JSON values in the ``settings`` table.

Never store secrets here — use ``ris.security.secrets``.
"""

from __future__ import annotations

import json
from typing import Any

from ris.storage.database import Database
from ris.util import utc_now_iso

#: Defaults for workspace settings. Keys are namespaced with dots.
DEFAULTS: dict[str, Any] = {
    "scoring.weights": {
        "essential": 35,
        "technical": 25,
        "evidence": 15,
        "experience": 10,
        "research": 10,
        "quality": 5,
    },
    "backup.auto_enabled": True,
    "backup.interval_hours": 24,
    "backup.keep_last": 10,
    "backup.on_exit": True,
    "backup.last_auto_at": "",
    "export.default_folder": "",
    "export.filename_pattern": "{name} - {variant} - {date}",
    "export.pdf_engine": "auto",
    "glossary.overrides": {},
    "taxonomy.extensions": {},
    "sync.provider": "off",
    "sync.folder_path": "",
    "sync.drive_folder_name": "Resume Intelligence Studio",
    "sync.drive_folder_id": "",
    "sync.drive_client_file": "",
    "sync.include_confidential": False,
    "sync.encrypt": True,
    "sync.last_success_at": "",
    "sync.last_error": "",
    "sync.last_backup_at": "",
    "privacy.notice_acknowledged": False,
    "device.id": "",
}


class SettingsStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        if row is None:
            if default is not None:
                return default
            value = DEFAULTS.get(key)
            # Return copies of mutable defaults.
            return json.loads(json.dumps(value)) if isinstance(value, (dict, list)) else value
        return json.loads(row["value"])

    def set(self, key: str, value: Any) -> None:
        self.db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False), utc_now_iso()),
        )

    def delete(self, key: str) -> None:
        self.db.execute("DELETE FROM settings WHERE key = ?", (key,))

    def all(self) -> dict[str, Any]:
        out = {k: (json.loads(json.dumps(v)) if isinstance(v, (dict, list)) else v) for k, v in DEFAULTS.items()}
        for row in self.db.query("SELECT key, value FROM settings"):
            out[row["key"]] = json.loads(row["value"])
        return out
