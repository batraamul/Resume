"""Shared fixtures and the requirement-traceability plugin.

Every test runs with RIS_DATA_DIR / RIS_CONFIG_DIR pointing to a temporary
folder, so the suite can never read or modify real user data.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_REQ_RESULTS: dict[str, list[dict]] = {}


def pytest_configure(config):
    config.addinivalue_line("markers", "req(*ids): requirement IDs this test provides evidence for")
    config.addinivalue_line("markers", "slow: slower tests (large profiles, many renders)")
    config.addinivalue_line("markers", "gui: GUI tests using the Qt offscreen platform")
    config.addinivalue_line("markers", "libreoffice: requires a LibreOffice installation")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    ids: list[str] = []
    for mark in item.iter_markers("req"):
        ids.extend(str(a) for a in mark.args)
    if not ids:
        return
    final = (report.when == "call") or (report.when == "setup" and report.outcome != "passed")
    if final:
        for rid in ids:
            _REQ_RESULTS.setdefault(rid, []).append({"test": item.nodeid, "outcome": report.outcome})


def pytest_sessionfinish(session, exitstatus):
    if not _REQ_RESULTS:
        return
    out = PROJECT_ROOT / "build" / "test-results"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "requirements.json"
    existing: dict[str, list[dict]] = {}
    if os.environ.get("RIS_TRACE_APPEND") and path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    for k, v in _REQ_RESULTS.items():
        existing.setdefault(k, [])
        seen = {e["test"] for e in existing[k]}
        existing[k] = [e for e in existing[k] if e["test"] not in {x["test"] for x in v}] + v
        del seen
    path.write_text(json.dumps(existing, indent=1, sort_keys=True), encoding="utf-8")


@pytest.fixture(autouse=True)
def _isolated_user_dirs(tmp_path_factory, monkeypatch):
    base = tmp_path_factory.mktemp("ris-user")
    monkeypatch.setenv("RIS_DATA_DIR", str(base / "data"))
    monkeypatch.setenv("RIS_CONFIG_DIR", str(base / "config"))
    monkeypatch.setenv("RIS_DISABLE_KEYRING", "1")
    monkeypatch.setenv("RIS_DISABLE_UPDATE_CHECK", "1")
    yield base


@pytest.fixture
def workspace(tmp_path):
    from ris.storage.workspace import Workspace

    ws = Workspace(tmp_path / "ws", "Test workspace", device_id="testdevice").open()
    yield ws
    ws.close()


@pytest.fixture
def repo(workspace):
    return workspace.repo


@pytest.fixture
def sample_ws(tmp_path):
    """A workspace loaded with the fictional sample profile."""
    from ris.services.sample import load_sample_profile
    from ris.storage.workspace import Workspace

    ws = Workspace(tmp_path / "sample", "Fictional Sample", is_sample=True, device_id="testdevice").open()
    load_sample_profile(ws)
    yield ws
    ws.close()
