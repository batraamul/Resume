"""Application (per-installation) configuration: workspace registry and preferences.

Stored as JSON in the OS config directory. Never contains secrets or profile data.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ris.paths import default_config_dir, default_data_dir, ensure_private_dir, restrict_file
from ris.util import new_id, utc_now_iso

log = logging.getLogger(__name__)

CONFIG_VERSION = 1


@dataclass
class WorkspaceEntry:
    id: str
    name: str
    folder: str  # absolute path, or relative to data_dir
    is_sample: bool = False
    created_at: str = ""


@dataclass
class AppConfig:
    version: int = CONFIG_VERSION
    data_dir: str = ""  # empty → OS default
    device_id: str = ""
    workspaces: list[WorkspaceEntry] = field(default_factory=list)
    active_workspace_id: str = ""
    theme: str = "light"  # light | dark | system
    pdf_engine: str = "auto"  # auto | libreoffice | builtin
    libreoffice_path: str = ""
    page_size: str = "A4"
    date_style: str = "mon_year"
    ui_font_scale: float = 1.0
    log_level: str = "INFO"
    ai_provider: str = "off"  # off | anthropic | openai_compatible
    ai_endpoint: str = ""
    ai_model: str = ""
    ai_confirm_each_request: bool = True
    window_geometry: str = ""
    window_state: str = ""
    last_export_folder: str = ""
    first_run_completed: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ paths
    def resolved_data_dir(self) -> Path:
        return Path(self.data_dir).expanduser() if self.data_dir else default_data_dir()

    def workspace_folder(self, entry: WorkspaceEntry) -> Path:
        p = Path(entry.folder).expanduser()
        return p if p.is_absolute() else self.resolved_data_dir() / p

    def find_workspace(self, workspace_id: str) -> WorkspaceEntry | None:
        return next((w for w in self.workspaces if w.id == workspace_id), None)

    # ------------------------------------------------------------------ persistence
    @staticmethod
    def path() -> Path:
        return default_config_dir() / "config.json"

    @classmethod
    def load(cls) -> AppConfig:
        p = cls.path()
        cfg = cls()
        if p.exists():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                cfg = cls.from_dict(raw)
            except (OSError, ValueError, TypeError) as exc:
                # Keep the broken file for inspection and start with defaults.
                broken = p.with_suffix(f".broken-{utc_now_iso().replace(':', '')}.json")
                try:
                    p.replace(broken)
                except OSError:
                    pass
                log.warning("Configuration file was unreadable and has been set aside: %s", type(exc).__name__)
        if not cfg.device_id:
            cfg.device_id = new_id()[:16]
            cfg.save()
        return cfg

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AppConfig:
        known = {f for f in cls.__dataclass_fields__}  # noqa: C416
        kwargs = {k: v for k, v in raw.items() if k in known and k != "workspaces"}
        cfg = cls(**kwargs)
        cfg.workspaces = [WorkspaceEntry(**w) for w in raw.get("workspaces", []) if isinstance(w, dict)]
        cfg.extra = {k: v for k, v in raw.items() if k not in known}
        return cfg

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        extra = d.pop("extra", {}) or {}
        d.update(extra)
        return d

    def save(self) -> None:
        p = self.path()
        ensure_private_dir(p.parent)
        data = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        # Atomic write: temp file in the same directory, then replace.
        fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".json", dir=str(p.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, p)
            restrict_file(p)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
