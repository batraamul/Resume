"""Defence & Intelligence Career Mode presets and organisation profiles (config-driven)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ris.resources import config_dir


@dataclass(frozen=True)
class CareerPreset:
    id: str
    name: str
    description: str
    keywords: tuple[str, ...]
    emphasis: tuple[str, ...]
    mode: str
    template: str
    summary_focus: str


@dataclass(frozen=True)
class OrgProfile:
    id: str
    name: str
    parent: str
    domains: tuple[str, ...]
    suggested_presets: tuple[str, ...]
    notes: str


@dataclass
class PresetLibrary:
    presets: dict[str, CareerPreset] = field(default_factory=dict)
    organisations: dict[str, OrgProfile] = field(default_factory=dict)

    def preset(self, pid: str) -> CareerPreset | None:
        return self.presets.get(pid)

    def org(self, oid: str) -> OrgProfile | None:
        return self.organisations.get(oid)


def load_presets(path: Path | None = None) -> PresetLibrary:
    raw = json.loads((path or (config_dir() / "career_presets.json")).read_text(encoding="utf-8"))
    lib = PresetLibrary()
    for p in raw.get("presets", []):
        lib.presets[p["id"]] = CareerPreset(
            id=p["id"], name=p["name"], description=p.get("description", ""), keywords=tuple(p.get("keywords", [])),
            emphasis=tuple(p.get("emphasis", [])), mode=p.get("mode", "general_professional"),
            template=p.get("template", "ats_minimal"), summary_focus=p.get("summary_focus", "general"),
        )
    for o in raw.get("organisations", []):
        lib.organisations[o["id"]] = OrgProfile(
            id=o["id"], name=o["name"], parent=o.get("parent", ""), domains=tuple(o.get("domains", [])),
            suggested_presets=tuple(o.get("suggested_presets", [])), notes=o.get("notes", ""),
        )
    return lib


@lru_cache(maxsize=1)
def default_presets() -> PresetLibrary:
    return load_presets()
