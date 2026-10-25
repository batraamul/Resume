"""Backup, restore, integrity, encrypted archives, portable JSON and importers (STO-03..06, IMP-01..05)."""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from datetime import UTC, datetime, timedelta

import pytest

from ris.backup import crypto
from ris.backup.backup import BackupService
from ris.backup.integrity import check_database, rebuild_search_index
from ris.domain.enums import Confidentiality, Origin, RecordKind, Verification
from ris.errors import DecryptionError, ImportFailed, RestoreError
from ris.services import importers, portable


@pytest.mark.req("STO-06")
class TestCrypto:
    def test_roundtrip_and_header(self):
        blob = crypto.encrypt(b"secret data" * 100, "correct horse battery", meta={"reason": "manual"})
        assert crypto.is_encrypted(blob) and b"secret data" not in blob
        assert crypto.read_header(blob)["meta"]["reason"] == "manual"
        data, header = crypto.decrypt(blob, "correct horse battery")
        assert data == b"secret data" * 100 and header["cipher"] == "AES-256-GCM"

    def test_wrong_passphrase_and_tamper(self):
        blob = crypto.encrypt(b"payload", "correct horse battery")
        with pytest.raises(DecryptionError):
            crypto.decrypt(blob, "wrong passphrase!!")
        tampered = blob[:-5] + bytes([blob[-5] ^ 1]) + blob[-4:]
        with pytest.raises(DecryptionError):
            crypto.decrypt(tampered, "correct horse battery")
        # Tampering with the authenticated header is detected too.
        i = blob.index(b'"reason') if b'"reason' in blob else blob.index(b'"cipher"')
        hdr_tampered = blob[:i] + blob[i:].replace(b"AES-256-GCM", b"AES-256-GCX", 1)
        with pytest.raises(DecryptionError):
            crypto.decrypt(hdr_tampered, "correct horse battery")

    def test_short_passphrase_rejected(self):
        with pytest.raises(DecryptionError):
            crypto.encrypt(b"x", "short")


@pytest.mark.req("STO-03", "STO-05")
def test_backup_verify_restore_cycle(sample_ws):
    svc = BackupService(sample_ws)
    n_before = sample_ws.repo.count()
    info = svc.create(reason="manual")
    assert info.path.exists() and info.record_count == n_before
    assert svc.verify(info.path).ok
    # Damage the live data after the backup.
    for r in sample_ws.repo.list(RecordKind.SKILL):
        sample_ws.repo.delete(r.id)
    sample_ws.repo.create(RecordKind.SKILL, {"name": "Added after backup"})
    result = svc.restore(info.path)
    assert sample_ws.repo.count() == n_before
    assert not any(s.data.name == "Added after backup" for s in sample_ws.repo.list(RecordKind.SKILL))
    snap_path = result["pre_restore_snapshot"]
    # The pre-restore snapshot still contains the post-backup change, so nothing is lost.
    assert any(b.reason == "pre-restore" for b in svc.list())
    svc.restore(snap_path)
    assert any(s.data.name == "Added after backup" for s in sample_ws.repo.list(RecordKind.SKILL))
    assert check_database(sample_ws.db).ok


@pytest.mark.req("STO-06")
def test_encrypted_backup(sample_ws):
    svc = BackupService(sample_ws)
    info = svc.create(passphrase="a long passphrase")
    assert info.encrypted and info.path.name.endswith(".risbackup.enc")
    raw = info.path.read_bytes()
    assert b"Anika" not in raw and b"SQLite format" not in raw
    assert not svc.verify(info.path).ok  # no passphrase
    assert not svc.verify(info.path, "wrong passphrase!").ok
    assert svc.verify(info.path, "a long passphrase").ok
    with pytest.raises(RestoreError):
        svc.restore(info.path)
    svc.restore(info.path, "a long passphrase")


@pytest.mark.req("SYN-03", "DEF-05")
def test_cloud_safe_backup_excludes_confidential_and_restore_keeps_local(sample_ws):
    svc = BackupService(sample_ws)
    data, manifest = svc.build_archive(include_confidential=False)
    assert manifest["confidential_records_removed"] >= 1 and not manifest["includes_confidential"]
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        db_bytes = zf.read("ris.db")
    assert b"SAMPLE-X" not in db_bytes and b"CONFIDENTIAL-MARKER" not in db_bytes
    path = sample_ws.backups_dir / "cloudsafe.risbackup"
    path.write_bytes(data)
    svc.restore(path)
    titles = [p.title for p in sample_ws.repo.list(RecordKind.PROJECT)]
    assert any("SAMPLE-X" in t for t in titles), "local confidential records must be preserved"


@pytest.mark.req("IMP-05")
def test_restore_rejects_hostile_archives(sample_ws, tmp_path):
    svc = BackupService(sample_ws)
    bad = tmp_path / "evil.risbackup"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": "ris-backup", "format_version": 1}))
        zf.writestr("../../etc/passwd", "x")
        zf.writestr("ris.db", "not a db")
    v = svc.verify(bad)
    assert not v.ok and "unexpected file" in v.problems[0]
    junk = tmp_path / "junk.risbackup"
    junk.write_bytes(b"PK\x03\x04garbage")
    assert not svc.verify(junk).ok
    n = sample_ws.repo.count()
    with pytest.raises(RestoreError):
        svc.restore(bad)
    assert sample_ws.repo.count() == n


@pytest.mark.req("STO-04")
def test_auto_backup_schedule_and_retention(sample_ws):
    svc = BackupService(sample_ws)
    sample_ws.settings.set("backup.interval_hours", 24)
    sample_ws.settings.set("backup.keep_last", 2)
    t0 = datetime(2026, 10, 1, tzinfo=UTC)
    assert svc.auto_backup_if_due(now=t0) is not None
    assert svc.auto_backup_if_due(now=t0 + timedelta(hours=2)) is None
    for d in range(1, 5):
        svc.auto_backup_if_due(now=t0 + timedelta(days=d))
    autos = [b for b in svc.list() if b.is_automatic]
    assert len(autos) == 2


@pytest.mark.req("STO-05")
def test_integrity_detects_tampering(sample_ws):
    rec = sample_ws.repo.list(RecordKind.SKILL)[0]
    sample_ws.db.execute("UPDATE records SET data = json_set(data, '$.name', 'Tampered') WHERE id = ?", (rec.id,))
    rep = check_database(sample_ws.db)
    assert not rep.ok and any("checksum" in p for p in rep.problems)
    sample_ws.db.execute("DELETE FROM records_fts")
    rep2 = check_database(sample_ws.db)
    assert any("Search index" in w for w in rep2.warnings)
    assert rebuild_search_index(sample_ws.repo) > 0


@pytest.mark.req("IMP-04", "IMP-01")
def test_portable_json_roundtrip_and_duplicates(sample_ws, tmp_path, workspace):
    path = portable.write_export(sample_ws.repo, tmp_path / "profile.json", include_confidential=False)
    data = json.loads(path.read_text())
    assert data["format_version"] == 1 and data["excluded_confidential"] >= 1
    assert "SAMPLE-X" not in path.read_text()
    prev = portable.preview(workspace.repo, portable.load_payload(path))
    rep = portable.commit(workspace.repo, prev)
    assert rep.created > 50
    facts = [r for r in workspace.repo.list() if r.kind in (RecordKind.SKILL, RecordKind.PROJECT)]
    assert all(r.verification == Verification.UNCONFIRMED and r.confidentiality == Confidentiality.REVIEW
               and r.origin == Origin.IMPORTED for r in facts)
    # Bullets keep their parents.
    bullets = workspace.repo.list(RecordKind.BULLET)
    assert bullets and all(workspace.repo.find(b.parent_id) for b in bullets)
    # Re-importing detects duplicates and skips them by default.
    prev2 = portable.preview(workspace.repo, portable.load_payload(path))
    dups = [c for c in prev2.candidates if c.duplicate is not None]
    assert len(dups) > 20 and all(not c.include for c in dups)


@pytest.mark.req("IMP-05")
def test_portable_rejects_bad_files(tmp_path, workspace):
    p = tmp_path / "x.json"
    p.write_text("{not json")
    with pytest.raises(ImportFailed):
        portable.load_payload(p)
    p.write_text(json.dumps({"format": "something-else", "records": []}))
    with pytest.raises(ImportFailed):
        portable.load_payload(p)
    p.write_text(json.dumps({"format": portable.FORMAT_ID, "format_version": 1,
                             "records": [{"kind": "skill", "data": {"name": "ok"}},
                                         {"kind": "skill", "data": {"name": "bad", "years_experience": 500}},
                                         {"kind": "nonsense", "data": {}}]}))
    prev = portable.preview(workspace.repo, portable.load_payload(p))
    assert len(prev.candidates) == 2 and sum(c.valid for c in prev.candidates) == 1


@pytest.mark.req("IMP-02")
def test_csv_import(tmp_path, workspace):
    p = tmp_path / "skills.csv"
    p.write_text("Skill,Category,Years\nPyTorch,aiml,5\nVHDL,electronics,3\nBad,aiml,999\n", encoding="utf-8")
    headers, _ = importers.read_csv(p)
    mapping = importers.suggest_mapping(RecordKind.SKILL, headers)
    assert mapping == {"Skill": "name", "Category": "category"}
    mapping["Years"] = "years_experience"
    prev = importers.preview_csv(workspace.repo, p, importers.CsvMapping(RecordKind.SKILL, mapping))
    assert [c.valid for c in prev.candidates] == [True, True, False]
    rep = portable.commit(workspace.repo, prev)
    assert rep.created == 2 and workspace.repo.list(RecordKind.SKILL)[0].verification == Verification.UNCONFIRMED


CV_TEXT = """Jane Example
Professional Experience
Senior Engineer, Example Avionics Ltd, Jan 2015 – Present
• Led integration of flight-control computers.
• Built automated test rigs.
Engineer | Example Systems | 2010 - 2014
- Designed PCB layouts.
Education
M.Tech. in Avionics, Example Institute, 2010
B.E. Electronics, Example College, 2008
Skills
Python, MATLAB; VHDL | Embedded C
Publications
J. Example, "Lightweight networks for drones," Example Journal, 2022.
J. Example, "A study under review," submitted to Example Letters, 2025.
Awards
Best Paper Award 2022
"""


@pytest.mark.req("IMP-03")
def test_cv_text_import_preview_and_commit(tmp_path, workspace):
    p = tmp_path / "cv.txt"
    p.write_text(CV_TEXT, encoding="utf-8")
    prev = importers.preview_file(workspace.repo, p)
    kinds = [c.kind for c in prev.candidates]
    assert kinds.count(RecordKind.POSITION) == 2 and kinds.count(RecordKind.BULLET) == 3
    assert kinds.count(RecordKind.EDUCATION) == 2 and kinds.count(RecordKind.SKILL) == 4
    pubs = [c for c in prev.candidates if c.kind == RecordKind.PUBLICATION]
    assert pubs[0].data["title"] == "Lightweight networks for drones" and pubs[1].data["status"] == "submitted"
    pos = next(c for c in prev.candidates if c.kind == RecordKind.POSITION)
    assert pos.data["is_current"] is True and pos.data["start"] == "2015-01"
    rep = portable.commit(workspace.repo, prev)
    assert rep.created == len([c for c in prev.candidates if c.include])
    assert all(r.verification == Verification.UNCONFIRMED for r in workspace.repo.list(RecordKind.POSITION))


def test_docx_and_pdf_text_extraction(tmp_path, workspace):
    from docx import Document
    from reportlab.pdfgen import canvas

    d = Document()
    for line in CV_TEXT.splitlines():
        d.add_paragraph(line)
    d.save(tmp_path / "cv.docx")
    assert "Senior Engineer" in importers.extract_text(tmp_path / "cv.docx")
    c = canvas.Canvas(str(tmp_path / "cv.pdf"))
    c.drawString(72, 720, "Skills")
    c.drawString(72, 700, "Python, MATLAB")
    c.save()
    assert "MATLAB" in importers.extract_text(tmp_path / "cv.pdf")
    (tmp_path / "fake.docx").write_bytes(b"not a zip")
    with pytest.raises(ImportFailed):
        importers.extract_text(tmp_path / "fake.docx")
    (tmp_path / "empty.txt").write_bytes(b"")
    with pytest.raises(ImportFailed):
        importers.extract_text(tmp_path / "empty.txt")


@pytest.mark.req("VAC-02")
def test_vacancy_from_file(tmp_path):
    p = tmp_path / "notice.txt"
    p.write_text("Recruitment of Scientist D\nAdvertisement No. ABC/12/2026\nEssential Qualifications:\n"
                 "Master's degree in Electronics.\nLast date: 31/12/2026\n", encoding="utf-8")
    f = importers.vacancy_from_file(p)
    assert f["reference"] == "ABC/12/2026" and f["deadline"] == "2026-12-31"
    assert f["title"] == "Recruitment of Scientist D" and "Essential" in f["raw_text"]


def test_backup_of_closed_sqlite_file_is_consistent(sample_ws):
    svc = BackupService(sample_ws)
    info = svc.create()
    with zipfile.ZipFile(info.path) as zf:
        raw = zf.read("ris.db")
    tmp = sample_ws.folder / "copy.db"
    tmp.write_bytes(raw)
    conn = sqlite3.connect(tmp)
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()
