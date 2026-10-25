"""Synchronisation engine, remotes, cloud backups and Google Drive adapter (mocked) — SYN-01..09."""

from __future__ import annotations

import json

import pytest

from ris.domain.enums import Confidentiality, RecordKind
from ris.errors import AuthExpired, NetworkUnavailable, SyncError
from ris.security.secrets import SecretStore
from ris.storage.workspace import Workspace
from ris.sync.engine import STATE_NAME, SyncEngine
from ris.sync.gdrive import GoogleDriveRemote
from ris.sync.remote import LocalFolderRemote, MemoryRemote
from ris.sync.service import SyncService


@pytest.fixture
def two_devices(tmp_path):
    a = Workspace(tmp_path / "A", "A", device_id="device-a").open()
    b = Workspace(tmp_path / "B", "B", device_id="device-b").open()
    yield a, b
    a.close()
    b.close()


def eng(ws, remote, **kw):
    return SyncEngine(ws.repo, remote, device_id=ws.device_id, **kw)


@pytest.mark.req("SYN-04")
def test_push_pull_roundtrip(two_devices):
    a, b = two_devices
    remote = MemoryRemote()
    pos = a.repo.create(RecordKind.POSITION, {"designation": "Scientist", "start": "2020"})
    a.repo.create(RecordKind.BULLET, {"text": "Built X"}, parent_id=pos.id)
    r1 = eng(a, remote).sync()
    assert r1.pushed == 2
    r2 = eng(b, remote).sync()
    assert r2.pulled == 2
    assert b.repo.get(pos.id).checksum == a.repo.get(pos.id).checksum
    # Edit on B, deletion on A of a different record, then converge.
    b.repo.patch(pos.id, designation="Senior Scientist")
    s = a.repo.create(RecordKind.SKILL, {"name": "Temp"})
    eng(a, remote).sync()
    eng(b, remote).sync()
    a.repo.delete(s.id)
    eng(a, remote).sync()
    eng(b, remote).sync()
    eng(a, remote).sync()
    assert a.repo.get(pos.id).data.designation == "Senior Scientist"
    assert b.repo.find(s.id) is None and b.repo.get(s.id, include_deleted=True).deleted


@pytest.mark.req("SYN-05", "SYN-08")
def test_simultaneous_edits_create_conflict_and_preserve_both(two_devices):
    a, b = two_devices
    remote = MemoryRemote()
    rec = a.repo.create(RecordKind.SKILL, {"name": "Python"})
    eng(a, remote).sync()
    eng(b, remote).sync()
    a.repo.patch(rec.id, name="Python (A)")
    b.repo.patch(rec.id, name="Python (B)")
    eng(a, remote).sync()
    rb = eng(b, remote).sync()
    assert rb.conflicts == 1
    assert b.repo.get(rec.id).data.name == "Python (B)", "local edit must not be overwritten"
    state = json.loads(remote.files[STATE_NAME])
    assert state["records"][rec.id]["data"]["name"] == "Python (A)", "remote edit must not be overwritten"
    conflict = eng(b, remote).open_conflicts()[0]
    assert conflict.local["data"]["name"] == "Python (B)" and conflict.remote["data"]["name"] == "Python (A)"
    eng(b, remote).resolve(conflict.id, "keep_local")
    eng(b, remote).sync()
    eng(a, remote).sync()
    assert a.repo.get(rec.id).data.name == "Python (B)"


def test_conflict_keep_remote_and_keep_both(two_devices):
    a, b = two_devices
    remote = MemoryRemote()
    rec = a.repo.create(RecordKind.SKILL, {"name": "C"})
    eng(a, remote).sync()
    eng(b, remote).sync()
    a.repo.patch(rec.id, name="C (A)")
    b.repo.patch(rec.id, name="C (B)")
    eng(a, remote).sync()
    eng(b, remote).sync()
    c = eng(b, remote).open_conflicts()[0]
    eng(b, remote).resolve(c.id, "keep_both")
    names = sorted(s.data.name for s in b.repo.list(RecordKind.SKILL))
    assert names == ["C (A)", "C (B)"]
    assert not eng(b, remote).open_conflicts()


@pytest.mark.req("DEF-05", "SYN-04")
def test_confidential_never_uploaded_and_marker_propagates(two_devices):
    a, b = two_devices
    remote = MemoryRemote()
    secret = a.repo.create(RecordKind.PROJECT, {"title": "SECRET-PROJECT-Q"}, confidentiality=Confidentiality.CONFIDENTIAL)
    a.repo.create(RecordKind.BULLET, {"text": "child of secret"}, parent_id=secret.id)
    public = a.repo.create(RecordKind.PROJECT, {"title": "Open project"}, confidentiality=Confidentiality.APPROVED)
    eng(a, remote).sync()
    raw = remote.files[STATE_NAME]
    assert b"SECRET-PROJECT-Q" not in raw and b"child of secret" not in raw
    eng(b, remote).sync()
    a.repo.set_confidentiality([public.id], Confidentiality.CONFIDENTIAL)
    rep = eng(a, remote).sync()
    assert rep.redacted == 1
    assert b"Open project" not in remote.files[STATE_NAME]
    eng(b, remote).sync()
    assert b.repo.get(public.id).confidentiality == Confidentiality.CONFIDENTIAL


@pytest.mark.req("SYN-08")
def test_offline_interrupted_and_expired_auth_lose_nothing(two_devices):
    a, b = two_devices
    remote = MemoryRemote()
    a.repo.create(RecordKind.SKILL, {"name": "Kept"})
    remote.offline = True
    with pytest.raises(NetworkUnavailable):
        eng(a, remote).sync()
    remote.offline = False
    remote.interrupt_next_write = True
    with pytest.raises(NetworkUnavailable):
        eng(a, remote).sync()
    assert STATE_NAME not in remote.files, "an interrupted upload must not leave partial data"
    assert not a.db.query("SELECT * FROM sync_base"), "base is only updated after a successful upload"
    remote.auth_expired = True
    with pytest.raises(AuthExpired):
        eng(a, remote).sync()
    remote.auth_expired = False
    assert eng(a, remote).sync().pushed == 1
    assert a.repo.count(RecordKind.SKILL) == 1


@pytest.mark.req("SYN-08")
def test_concurrent_writer_detected_and_retried(two_devices):
    a, b = two_devices
    remote = MemoryRemote()
    a.repo.create(RecordKind.SKILL, {"name": "From A"})
    b.repo.create(RecordKind.SKILL, {"name": "From B"})
    eng(b, remote).sync()

    def other_device_writes(_name):
        b.repo.create(RecordKind.SKILL, {"name": "Raced in from B"})
        eng(b, remote).sync()

    remote.on_before_write = other_device_writes
    rep = eng(a, remote).sync()
    assert rep.attempts == 2
    eng(b, remote).sync()
    eng(a, remote).sync()
    names = {s.data.name for s in a.repo.list(RecordKind.SKILL)}
    assert names == {"From A", "From B", "Raced in from B"}


def test_duplicate_records_first_sync_is_conflict_not_overwrite(two_devices):
    a, b = two_devices
    remote = MemoryRemote()
    env = a.repo.create(RecordKind.SKILL, {"name": "Same id"}).envelope()
    b.repo.write_envelope(env, origin_override="manual")
    b.repo.patch(env["id"], name="Same id, edited on B before first sync")
    eng(a, remote).sync()
    rep = eng(b, remote).sync()
    assert rep.conflicts == 1 and b.repo.get(env["id"]).data.name.endswith("before first sync")


@pytest.mark.req("SYN-03", "SYN-07", "SYN-09", "SYN-01", "SEC-05")
def test_service_folder_backup_restore_delete(sample_ws, tmp_path):
    secrets = SecretStore(use_keyring=False)
    svc = SyncService(sample_ws, secrets)
    assert svc.status().provider == "off"
    with pytest.raises(SyncError):
        svc.sync_now()
    folder = tmp_path / "GoogleDriveForDesktop"
    folder.mkdir()
    svc.configure_folder(folder)
    with pytest.raises(SyncError):
        svc.upload_backup()  # no passphrase and no explicit permission
    svc.set_passphrase("cloud passphrase 123")
    info = svc.upload_backup()
    assert info.name.endswith(".risbackup.enc")
    stored = (folder / info.name).read_bytes()
    assert b"Anika" not in stored
    assert [f.name for f in svc.list_cloud_backups()] == [info.name]
    rep = svc.sync_now()
    assert rep.pushed > 0 and svc.status().last_success
    n = sample_ws.repo.count()
    sample_ws.repo.delete(sample_ws.repo.list(RecordKind.SKILL)[0].id)
    svc.restore_cloud_backup(info.name)
    assert sample_ws.repo.count() == n
    svc.delete_cloud_backup(info.name)
    assert not svc.list_cloud_backups()
    assert sample_ws.repo.count() == n, "deleting a cloud copy never touches local data"
    with pytest.raises(SyncError):
        svc.delete_cloud_backup("ris-sync/state.json")


def test_encrypted_sync_state_requires_passphrase(two_devices):
    a, b = two_devices
    remote = MemoryRemote()
    a.repo.create(RecordKind.SKILL, {"name": "Encrypted skill"})
    eng(a, remote, passphrase="shared passphrase 1").sync()
    assert b"Encrypted skill" not in remote.files[STATE_NAME]
    with pytest.raises(SyncError):
        eng(b, remote).sync()
    assert eng(b, remote, passphrase="shared passphrase 1").sync().pulled == 1


def test_local_folder_remote_version_check(tmp_path):
    r = LocalFolderRemote(tmp_path)
    info = r.write("ris-sync/state.json", b"one", expected_version="")
    r.write("ris-sync/state.json", b"two", expected_version=info.version)
    from ris.errors import RemoteChanged

    with pytest.raises(RemoteChanged):
        r.write("ris-sync/state.json", b"three", expected_version=info.version)
    with pytest.raises(SyncError):
        r.write("../escape.txt", b"x")
    missing = LocalFolderRemote(tmp_path / "unplugged-drive")
    with pytest.raises(NetworkUnavailable):
        missing.list_files()


# --------------------------------------------------------------------------- Google Drive adapter (mocked HTTP)


class FakeResp:
    def __init__(self, code=200, payload=None, content=b"", text=""):
        self.status_code = code
        self._payload = payload
        self.content = content
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        return self._payload


class FakeDrive:
    """Minimal in-memory imitation of the Drive v3 endpoints the adapter uses."""

    def __init__(self):
        self.files = {}
        self.next_id = 1
        self.calls = []
        self.fail = None

    def request(self, method, url, timeout=None, params=None, json=None, data=None, headers=None):  # noqa: A002
        self.calls.append((method, url, params))
        if self.fail:
            f, self.fail = self.fail, None
            if isinstance(f, Exception):
                raise f
            return FakeResp(f)
        params = params or {}
        if method == "GET" and url.endswith("/files") and "q" in params:
            q = params["q"]
            if "mimeType='application/vnd.google-apps.folder'" in q:
                hits = [f for f in self.files.values() if f.get("folder") and not f["trashed"]]
            else:
                name = q.split("name='")[1].split("'")[0] if "name='" in q else None
                hits = [f for f in self.files.values() if not f.get("folder") and not f["trashed"]
                        and (name is None or f["name"] == name)]
            return FakeResp(200, {"files": [{k: v for k, v in f.items() if k != "data"} for f in hits]})
        if method == "POST" and url.endswith("/drive/v3/files") and "/upload/" not in url:
            fid = f"id{self.next_id}"
            self.next_id += 1
            self.files[fid] = {"id": fid, "name": json["name"], "folder": True, "trashed": False, "version": "1"}
            return FakeResp(200, {"id": fid})
        if method == "POST" and "/upload/" in url:
            body = data
            meta = body.split(b"\r\n\r\n", 1)[1].split(b"\r\n--", 1)[0]
            content = body.split(b"application/octet-stream\r\n\r\n", 1)[1].rsplit(b"\r\n--", 1)[0]
            name = __import__("json").loads(meta)["name"]
            fid = f"id{self.next_id}"
            self.next_id += 1
            self.files[fid] = {"id": fid, "name": name, "data": content, "trashed": False, "version": "1",
                               "size": str(len(content))}
            return FakeResp(200, {k: v for k, v in self.files[fid].items() if k != "data"})
        if method == "PATCH" and "/upload/" in url:
            fid = url.rsplit("/", 1)[1]
            f = self.files[fid]
            f["data"] = data
            f["version"] = str(int(f["version"]) + 1)
            f["size"] = str(len(data))
            return FakeResp(200, {k: v for k, v in f.items() if k != "data"})
        if method == "PATCH":
            fid = url.rsplit("/", 1)[1]
            self.files[fid]["trashed"] = bool(json.get("trashed"))
            return FakeResp(200, {"id": fid})
        if method == "GET" and params.get("alt") == "media":
            fid = url.rsplit("/", 1)[1]
            return FakeResp(200, content=self.files[fid]["data"])
        return FakeResp(404, {"error": "not found"})


@pytest.mark.req("SYN-02", "SYN-06", "SYN-08")
def test_google_drive_adapter_with_mocked_api(two_devices):
    a, b = two_devices
    drive = FakeDrive()
    remote = GoogleDriveRemote(drive, "RIS Test")
    a.repo.create(RecordKind.SKILL, {"name": "Drive skill"})
    assert eng(a, remote).sync().pushed == 1
    assert any(f.get("folder") for f in drive.files.values())
    assert eng(b, GoogleDriveRemote(drive, "RIS Test")).sync().pulled == 1
    drive.fail = 401
    with pytest.raises(AuthExpired):
        remote.list_files()
    drive.fail = 503
    with pytest.raises(NetworkUnavailable):
        remote.list_files()
    drive.fail = ConnectionError("network down")
    with pytest.raises(NetworkUnavailable):
        remote.list_files()
    remote.write("ris-backups/x.risbackup", b"abc")
    remote.delete("ris-backups/x.risbackup")
    assert all(f["trashed"] for f in drive.files.values() if f["name"] == "ris-backups__x.risbackup")
    scopes = __import__("ris.sync.gdrive", fromlist=["SCOPES"]).SCOPES
    assert scopes == ["https://www.googleapis.com/auth/drive.file"]


def test_service_retries_transient_network_errors(sample_ws):
    remote = MemoryRemote()
    svc = SyncService(sample_ws, SecretStore(use_keyring=False), remote_factory=lambda _p: remote)
    sample_ws.settings.set("sync.provider", "memory")
    remote.fail_next_write = NetworkUnavailable("blip")
    rep = svc.sync_now(retry_delay=0)
    assert rep.pushed > 0
    remote.auth_expired = True
    with pytest.raises(AuthExpired):
        svc.sync_now(retry_delay=0)
    assert "expired" in svc.status().last_error.lower()
