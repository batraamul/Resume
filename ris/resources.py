"""Locate bundled, read-only resources (templates, migrations, config, assets).

Works from a source checkout and from a PyInstaller bundle (``sys._MEIPASS``).
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def resource_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def migrations_dir() -> Path:
    return resource_path("migrations")


def templates_dir() -> Path:
    return resource_path("templates")


def config_dir() -> Path:
    return resource_path("config")


def fonts_dir() -> Path:
    return resource_path("assets", "fonts")


def sample_data_dir() -> Path:
    return resource_path("sample_data")
