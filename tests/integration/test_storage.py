import sqlite3

import pytest

from ris.domain.enums import Confidentiality, Origin, RecordKind, Verification
from ris.errors import ConcurrencyConflict, MigrationError, ValidationFailed
from ris.storage import migrations
from ris.storage.database import Database
from ris.storage.repository import compute_checksum


@pytest.mark.req("STO-01")
class TestMigrations:
    def test_fresh_database_migrated(self, workspace):
        assert migrations.current_version(workspace.db) == migrations.latest_version()
        assert workspace.db.table_exists("records")
        assert workspace.db.table_exists("records_fts")
        assert migrations.verify_applied(workspace.db) == []

    def test_idempotent(self, workspace):
        assert migrations.migrate(workspace.db) == []

    def test_refuses_newer_schema(self, tmp_path):
        db = Database(tmp_path / "x.db")
        migrations.migrate(db)
        db.execute("INSERT INTO schema_migrations VALUES (999, 'future', 'now', 'x')")
        with pytest.raises(MigrationError):
            migrations.migrate(db)
        db.close()

    def test_failed_migration_rolls_back(self, tmp_path):
        mdir = tmp_path / "migs"
        mdir.mkdir()
        (mdir / "0001_a.sql").write_text("CREATE TABLE a (x INTEGER);")
        (mdir / "0002_b.sql").write_text("CREATE TABLE b (y INTEGER);\nTHIS IS NOT SQL;")
        db = Database(tmp_path / "y.db")
        with pytest.raises(MigrationError):
            migrations.migrate(db, mdir)
        assert migrations.current_version(db) == 1
        assert not db.table_exists("b")
        db.close()

    @pytest.mark.req("MNT-04")
    def test_upgrade_from_version_1_keeps_exports(self, tmp_path):
        import shutil

        from ris.resources import migrations_dir

        v1 = tmp_path / "v1"
        v1.mkdir()
        shutil.copy(migrations_dir() / "0001_initial.sql", v1 / "0001_initial.sql")
        db = Database(tmp_path / "old.db")
        migrations.migrate(db, v1)
        db.execute("INSERT INTO exports (id, created_at, document_kind, format, path, size_bytes, sha256, status)"
                   " VALUES ('e1', 't', 'resume', 'pdf', '/x.pdf', 10, 'abc', 'valid')")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO exports (id, created_at, document_kind, format, path, size_bytes, sha256, status)"
                       " VALUES ('e2', 't', 'interview_pack', 'pdf', '/y.pdf', 10, 'abc', 'valid')")
        applied = migrations.migrate(db)
        assert [m.version for m in applied] == list(range(2, migrations.latest_version() + 1))
        assert db.query_one("SELECT path FROM exports WHERE id = 'e1'")["path"] == "/x.pdf"
        db.execute("INSERT INTO exports (id, created_at, document_kind, format, path, size_bytes, sha256, status)"
                   " VALUES ('e3', 't', 'interview_pack', 'pdf', '/z.pdf', 10, 'abc', 'valid')")
        assert db.scalar("SELECT COUNT(*) FROM exports") == 2
        db.close()

    def test_constraints_enforced(self, workspace):
        with pytest.raises(sqlite3.IntegrityError):
            workspace.db.execute(
                "INSERT INTO records (id, kind, verification, confidentiality, origin, data, created_at, updated_at,"
                " checksum) VALUES ('x','skill','bogus','public','manual','{}','t','t','c')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            workspace.db.execute(
                "INSERT INTO records (id, kind, data, created_at, updated_at, checksum)"
                " VALUES ('y','skill','not json','t','t','c')"
            )


@pytest.mark.req("PRF-01", "PRF-15")
class TestRepository:
    def test_create_get_update_revision(self, repo):
        rec = repo.create(RecordKind.SKILL, {"name": "PyTorch", "category": "aiml"})
        assert rec.revision == 1 and rec.verification == Verification.CONFIRMED
        assert rec.confidentiality == Confidentiality.APPROVED
        rec2 = repo.patch(rec.id, name="PyTorch 2")
        assert rec2.revision == 2 and rec2.data.name == "PyTorch 2"
        assert rec2.checksum != rec.checksum
        # No-op update keeps revision.
        rec3 = repo.update(rec.id, rec2.payload())
        assert rec3.revision == 2

    def test_imported_defaults(self, repo):
        rec = repo.create(RecordKind.PROJECT, {"title": "Imported project"}, origin=Origin.IMPORTED)
        assert rec.verification == Verification.UNCONFIRMED
        assert rec.confidentiality == Confidentiality.REVIEW

    def test_validation_messages(self, repo):
        with pytest.raises(ValidationFailed) as ei:
            repo.create(RecordKind.PERSONAL, {"email": "bad"})
        assert "Email" in ei.value.user_message

    def test_parent_rules(self, repo):
        pos = repo.create(RecordKind.POSITION, {"designation": "Scientist"})
        b = repo.create(RecordKind.BULLET, {"text": "Built X"}, parent_id=pos.id)
        assert repo.children(pos.id)[0].id == b.id
        with pytest.raises(ValidationFailed):
            repo.create(RecordKind.BULLET, {"text": "orphan"})
        skill = repo.create(RecordKind.SKILL, {"name": "C"})
        with pytest.raises(ValidationFailed):
            repo.create(RecordKind.ASSIGNMENT, {"title": "x"}, parent_id=skill.id)

    def test_singleton(self, repo):
        repo.create(RecordKind.PERSONAL, {"full_name": "A"})
        with pytest.raises(ValidationFailed):
            repo.create(RecordKind.PERSONAL, {"full_name": "B"})

    def test_soft_delete_cascade_and_undelete(self, repo):
        pos = repo.create(RecordKind.POSITION, {"designation": "Scientist"})
        b = repo.create(RecordKind.BULLET, {"text": "Built X"}, parent_id=pos.id)
        affected = repo.delete(pos.id)
        assert set(affected) == {pos.id, b.id}
        assert repo.find(pos.id) is None
        tomb = repo.get(b.id, include_deleted=True)
        assert tomb.deleted and tomb.revision == 2
        repo.undelete(pos.id)
        assert repo.find(pos.id) is not None
        with pytest.raises(ValidationFailed):
            repo.delete(pos.id)
            repo.undelete(b.id)  # parent deleted → cannot restore child alone

    def test_purge(self, repo):
        pos = repo.create(RecordKind.POSITION, {"designation": "Scientist"})
        repo.create(RecordKind.BULLET, {"text": "Built X"}, parent_id=pos.id)
        repo.purge(pos.id)
        assert repo.db.scalar("SELECT COUNT(*) FROM records") == 0

    def test_optimistic_concurrency(self, repo):
        rec = repo.create(RecordKind.SKILL, {"name": "C"})
        repo.patch(rec.id, name="C++")
        with pytest.raises(ConcurrencyConflict):
            repo.update(rec.id, {"name": "Rust"}, expected_revision=1)

    @pytest.mark.req("PRF-14")
    def test_search(self, repo):
        repo.create(RecordKind.PROJECT, {"title": "Radiosonde telemetry decoder", "software": ["Python"]})
        repo.create(RecordKind.PROJECT, {"title": "Drone image super-resolution"})
        hits = repo.search("radio")
        assert [h[0].title for h in hits] == ["Radiosonde telemetry decoder"]
        assert repo.search('super "resolution') and repo.search("") == []
        # Deleted records disappear from search.
        repo.delete(hits[0][0].id)
        assert repo.search("radiosonde") == []

    def test_audit_log_has_no_values(self, repo):
        rec = repo.create(RecordKind.SKILL, {"name": "SecretSkillName"})
        repo.patch(rec.id, name="AnotherSecret")
        details = " ".join(e["detail"] for e in repo.audit_entries())
        assert "SecretSkillName" not in details and "AnotherSecret" not in details
        assert "fields=name" in details

    def test_checksum_deterministic(self):
        a = compute_checksum("skill", None, 1, "confirmed", "public", "manual", {"b": 1, "a": 2}, False)
        b = compute_checksum("skill", None, 1.0, "confirmed", "public", "manual", {"a": 2, "b": 1}, False)
        assert a == b

    def test_fingerprint_changes(self, repo):
        f0 = repo.fingerprint()
        rec = repo.create(RecordKind.SKILL, {"name": "C"})
        f1 = repo.fingerprint()
        repo.patch(rec.id, name="D")
        assert len({f0, f1, repo.fingerprint()}) == 3

    def test_write_envelope_roundtrip(self, repo, tmp_path):
        from ris.storage.workspace import Workspace

        rec = repo.create(RecordKind.SKILL, {"name": "Embedded C"})
        env = rec.envelope()
        other = Workspace(tmp_path / "other", device_id="d2").open()
        try:
            other.repo.write_envelope(env, origin_override=env["origin"])
            copy = other.repo.get(rec.id)
            assert copy.checksum == rec.checksum and copy.revision == rec.revision
        finally:
            other.close()


def test_settings_defaults_and_roundtrip(workspace):
    s = workspace.settings
    assert s.get("scoring.weights")["essential"] == 35
    s.set("backup.keep_last", 3)
    assert s.get("backup.keep_last") == 3
    w = s.get("scoring.weights")
    w["essential"] = 1  # mutating the returned default must not leak
    assert s.get("scoring.weights")["essential"] == 35


@pytest.mark.req("STO-02", "STO-07", "REL-01")
def test_workspace_manager_and_relocation(tmp_path):
    from ris.config import AppConfig
    from ris.storage.workspace import WorkspaceManager

    cfg = AppConfig.load()
    mgr = WorkspaceManager(cfg)
    entry = mgr.ensure_default()
    ws = mgr.open(entry)
    ws.repo.create(RecordKind.SKILL, {"name": "Relocated skill"})
    ws.close()
    assert str(mgr.data_dir).startswith(str(tmp_path.parent)) or "ris-user" in str(mgr.data_dir)
    new_dir = tmp_path / "moved"
    old = mgr.relocate(new_dir)
    assert old.exists()
    assert AppConfig.load().data_dir == str(new_dir.resolve())
    ws2 = WorkspaceManager(AppConfig.load()).open(entry)
    assert ws2.repo.list(RecordKind.SKILL)[0].data.name == "Relocated skill"
    ws2.close()
