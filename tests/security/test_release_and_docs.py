"""Release hygiene and required documentation (REL-03, REL-04, MNT-02, MNT-04, STO-08, STO-09, SEC-01, DEF-07).

The release check is the same function `scripts/make_release.py` runs before building the ZIP.
"""

from __future__ import annotations

import importlib.util
import re
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _release_module():
    spec = importlib.util.spec_from_file_location("make_release", ROOT / "scripts" / "make_release.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _doc(name: str) -> str:
    return (ROOT / "docs" / name).read_text(encoding="utf-8")


@pytest.mark.req("REL-03", "SEC-02")
def test_release_file_set_is_clean_and_has_required_files(monkeypatch):
    mod = _release_module()
    monkeypatch.setenv("RIS_RELEASE_FORBIDDEN", "")
    files = list(mod.iter_files())
    rels = {rel.as_posix() for _p, rel in files}
    for required in ("README.md", "CHANGELOG.md", "LICENSE.txt", "requirements.txt", "run_application.py",
                     "launch_macos.command", "launch_windows.bat", "launch_linux.sh", "packaging/ris.spec",
                     "docs/TEST_REPORT.md", "docs/USER_GUIDE.md", "sample_data/fictional_sample_profile.ris.json"):
        assert required in rels, required
    for rel in rels:
        parts = set(rel.split("/"))
        assert not parts & {".venv", "build", "dist", "__pycache__", ".pytest_cache"}, rel
        assert not rel.endswith((".db", ".sqlite", ".risbackup", ".key", ".pem", ".log")), rel
        assert "personal" not in parts, rel
    assert mod.check(files) == []


@pytest.mark.req("REL-03")
def test_release_scan_detects_secrets_and_personal_strings_inside_documents(tmp_path, monkeypatch):
    mod = _release_module()
    secret = tmp_path / "config.json"
    # Built at run time so this test file itself does not trip the release scan.
    secret.write_text('{"client_' + 'secret": "' + "abcdefghijklmnop" + '"}', encoding="utf-8")
    key = tmp_path / "notes.txt"
    key.write_text("token sk-ant-" + "x" * 30, encoding="utf-8")
    docx = tmp_path / "resume.docx"
    with zipfile.ZipFile(docx, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", "<w:t>Jane Q. Private</w:t>")
    monkeypatch.setenv("RIS_RELEASE_FORBIDDEN", "Jane Q. Private")
    problems = mod.check([(secret, Path("config.json")), (key, Path("notes.txt")), (docx, Path("examples/resume.docx"))])
    joined = "\n".join(problems)
    assert "config.json" in joined and "notes.txt" in joined and "resume.docx" in joined


@pytest.mark.req("MNT-02")
def test_dependencies_are_pinned():
    for name in ("requirements.txt", "requirements-dev.txt", "requirements-optional.txt"):
        lines = [ln.strip() for ln in (ROOT / name).read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.strip().startswith(("#", "-r"))]
        assert lines, name
        for ln in lines:
            assert re.fullmatch(r"[A-Za-z0-9_.\-\[\]]+==[0-9][0-9A-Za-z.\-]*", ln), f"{name}: {ln}"


@pytest.mark.req("MNT-04")
def test_upgrade_process_documented_and_migrations_numbered():
    install = _doc("INSTALL.md")
    assert "## Upgrading" in install and "migration" in install.lower() and "pre-upgrade" in install
    names = sorted(p.name for p in (ROOT / "migrations").glob("*.sql"))
    assert names and all(re.match(r"^\d{3,4}_", n) for n in names)


@pytest.mark.req("STO-08")
def test_recovery_instructions_documented():
    text = _doc("TROUBLESHOOTING.md")
    assert "## Recovering your data" in text
    for phrase in ("Recently deleted", "Restore from a file", "pre-restore", "pre-upgrade", "Check database integrity"):
        assert phrase in text, phrase


@pytest.mark.req("STO-09")
def test_storage_protection_disclosed_honestly():
    from ris.strings import STORAGE_NOTICE

    assert "unencrypted" in STORAGE_NOTICE.lower()
    assert "not encrypted at rest" in _doc("SECURITY_PRIVACY.md")


@pytest.mark.req("SEC-01")
def test_threat_model_documented():
    text = _doc("THREAT_MODEL.md")
    assert len(re.findall(r"^\| T\d+ ", text, flags=re.M)) >= 6


@pytest.mark.req("REL-04")
def test_macos_launcher_and_signing_steps_documented():
    launcher = (ROOT / "launch_macos.command").read_text(encoding="utf-8")
    assert launcher.startswith("#!") and "run_application.py" in launcher
    install = _doc("INSTALL.md")
    for phrase in ("codesign", "notarytool", "stapler", ".app"):
        assert phrase in install, phrase


@pytest.mark.req("DEF-07")
def test_responsibility_notice_text():
    from ris.strings import RESPONSIBILITY_NOTICE

    assert "You are responsible" in RESPONSIBILITY_NOTICE
    assert "responsib" in _doc("SECURITY_PRIVACY.md").lower()
