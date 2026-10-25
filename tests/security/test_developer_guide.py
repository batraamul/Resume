"""The beginner developer guide stays accurate (MNT-05).

* The tutorial code printed in docs/DEVELOPER_GUIDE.md is exactly the code in docs/tutorial/resume_lite/.
* The tutorial's own tests pass.
* Every repository path and every function named in the guide exists.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "DEVELOPER_GUIDE.md"
TUTORIAL = ROOT / "docs" / "tutorial" / "resume_lite"

#: Functions from Python, Qt, Pydantic or pytest that the guide mentions but the project does not define, plus
#: parameter names and the example names used in recipes.
EXTERNAL = {"print", "breakpoint", "model_dump_json", "model_validate_json", "exec", "show", "connect", "raises",
            "escape", "home", "on_done", "section_mykey"}
#: Files the recipes tell the reader to create.
EXAMPLE_PATHS = {"migrations/0003_short_description.sql", "ris/ui/pages/mypage.py"}


def _guide() -> str:
    return GUIDE.read_text(encoding="utf-8")


@pytest.mark.req("MNT-05")
def test_guide_embeds_the_tutorial_code_verbatim():
    guide = _guide()
    files = sorted(TUTORIAL.glob("*.py"))
    assert len(files) == 6
    for f in files:
        assert f.read_text(encoding="utf-8").rstrip("\n") in guide, f"{f.name} differs from the guide"


@pytest.mark.req("MNT-05")
def test_paths_named_in_the_guide_exist():
    guide = _guide()
    paths = set(re.findall(r"`((?:ris|tests|scripts|packaging|migrations|templates|config|assets|docs|"
                           r"sample_data|\.github)/[\w./-]*)`", guide))
    paths |= set(re.findall(r"`([\w-]+\.(?:py|md|toml|txt|json|spec))`", guide)) & {
        p.name for p in ROOT.iterdir()}
    assert len(paths) > 40
    missing = sorted(p for p in paths - EXAMPLE_PATHS if not (ROOT / p.rstrip("/")).exists())
    assert not missing, missing


@pytest.mark.req("MNT-05")
def test_functions_named_in_the_guide_exist():
    guide = _guide()
    prose = re.sub(r"```.*?```", "", guide, flags=re.S)  # code blocks are checked by running them
    named = set(re.findall(r"`(?:[A-Za-z_][\w.]*\.)?([a-z_][a-z0-9_]*)\(", prose))
    sources = [*ROOT.joinpath("ris").rglob("*.py"), *ROOT.joinpath("scripts").glob("*.py"),
               *TUTORIAL.glob("*.py")]
    defined = set()
    for f in sources:
        defined |= set(re.findall(r"^\s*def (\w+)\(", f.read_text(encoding="utf-8"), re.M))
    assert len(named) > 40
    missing = sorted(named - defined - EXTERNAL)
    assert not missing, missing


@pytest.mark.req("MNT-05")
def test_tutorial_tests_pass(tmp_path):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", str(tmp_path / "t"),
         str(TUTORIAL)],
        cwd=TUTORIAL, env=env, capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
    assert "5 passed" in proc.stdout
