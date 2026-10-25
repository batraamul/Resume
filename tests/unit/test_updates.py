"""Secure updates: signed manifests, version rules, safe downloads, install plans and release tooling
(UPD-01..05)."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ris.update import installer
from ris.update.client import UpdateClient, _check_url
from ris.update.manifest import (
    UpdateAsset,
    UpdateError,
    build_manifest,
    is_newer,
    parse_version,
    platform_key,
    sign,
    verify_manifest,
)

REPO = "example/Resume"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def keypair():
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return key, (base64.b64encode(pub).decode(),)


def _asset(name="ResumeIntelligenceStudio-9.0.0-linux-x86_64.tar.gz", data=b"payload", plat=None, kind="linux-tar",
           version="9.0.0", repo=REPO):
    return UpdateAsset(platform=plat or platform_key(), kind=kind, name=name,
                       url=f"https://github.com/{repo}/releases/download/v{version}/{name}",
                       sha256=hashlib.sha256(data).hexdigest(), size=len(data))


# --------------------------------------------------------------------------- versions and manifests


@pytest.mark.req("UPD-02")
def test_version_ordering():
    assert is_newer("1.1.0", "1.0.0") and is_newer("1.10.0", "1.9.9") and is_newer("2.0.0", "1.99.99")
    assert is_newer("1.2.0", "1.2.0-beta.2") and is_newer("1.2.0-beta.10", "1.2.0-beta.2")
    assert not is_newer("1.0.0", "1.0.0") and not is_newer("1.0.0", "1.1.0")
    assert parse_version("v1.2.3") == parse_version("1.2.3")
    with pytest.raises(UpdateError):
        parse_version("1.2")


@pytest.mark.req("UPD-01")
def test_signed_manifest_round_trip_and_tampering(keypair):
    key, pubs = keypair
    data = build_manifest("9.0.0", "2026-10-25T00:00:00Z", "Notes", [_asset()], REPO)
    sig = sign(data, key)
    m = verify_manifest(data, sig, pubs, REPO)
    assert m.version == "9.0.0" and m.channel == "stable" and m.assets[0].kind == "linux-tar"
    with pytest.raises(UpdateError, match="signature"):
        verify_manifest(data.replace(b"9.0.0", b"9.0.1"), sig, pubs, REPO)
    other = Ed25519PrivateKey.generate()
    with pytest.raises(UpdateError, match="signature"):
        verify_manifest(data, sign(data, other), pubs, REPO)
    with pytest.raises(UpdateError):
        verify_manifest(data, b"not base64!!", pubs, REPO)
    with pytest.raises(UpdateError, match="repository"):
        verify_manifest(data, sig, pubs, "attacker/Resume")
    beta = build_manifest("9.1.0-beta.1", "", "", [_asset(version="9.1.0-beta.1")], REPO)
    assert verify_manifest(beta, sign(beta, key), pubs, REPO).channel == "beta"


@pytest.mark.req("UPD-01")
@pytest.mark.parametrize("change,message", [
    ({"url": "https://evil.example.com/x.tar.gz"}, "outside"),
    ({"url": f"https://github.com/{REPO}/releases/download/v8.0.0/x.tar.gz"}, "different release"),
    ({"sha256": "abc"}, "checksum"),
    ({"size": 0}, "size"),
    ({"name": "../x.tar.gz"}, "file name"),
])
def test_manifest_asset_rules(keypair, change, message):
    key, pubs = keypair
    raw = _asset().__dict__ | change
    body = json.loads(build_manifest("9.0.0", "", "", [_asset()], REPO))
    body["assets"] = [raw]
    data = json.dumps(body).encode()
    with pytest.raises(UpdateError, match=message):
        verify_manifest(data, sign(data, key), pubs, REPO)


@pytest.mark.req("UPD-01")
def test_embedded_public_key_is_well_formed():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    from ris.update.keys import PUBLIC_KEYS, REPOSITORY

    assert PUBLIC_KEYS and REPOSITORY == "batraamul/Resume"
    for k in PUBLIC_KEYS:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(k))


# --------------------------------------------------------------------------- client


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, routes: dict[str, bytes]) -> None:
        self.routes = routes
        self.requests: list = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        url = req.full_url
        if url not in self.routes:
            raise OSError(f"no route for {url}")
        return FakeResponse(self.routes[url])


def _server(key, version="9.0.0", payload=b"installer-bytes", signed=True, prerelease=False, plat=None):
    base = f"https://api.github.com/repos/{REPO}/releases"
    dl = f"https://github.com/{REPO}/releases/download/v{version}/"
    asset = _asset(data=payload, version=version, plat=plat)
    manifest = build_manifest(version, "2026-10-25T00:00:00Z", "## What's new\n* Faster", [asset], REPO)
    assets = [{"name": "ris-update.json", "browser_download_url": dl + "ris-update.json"},
              {"name": asset.name, "browser_download_url": asset.url}]
    if signed:
        assets.append({"name": "ris-update.json.sig", "browser_download_url": dl + "ris-update.json.sig"})
    release = {"tag_name": f"v{version}", "draft": False, "prerelease": prerelease, "assets": assets,
               "html_url": f"https://github.com/{REPO}/releases/tag/v{version}"}
    routes = {base + "/latest": json.dumps(release).encode(), base + "?per_page=10": json.dumps([release]).encode(),
              dl + "ris-update.json": manifest, dl + "ris-update.json.sig": sign(manifest, key), asset.url: payload}
    return FakeOpener(routes), asset


@pytest.mark.req("UPD-02", "UPD-03")
def test_client_finds_verified_update_and_downloads_it(keypair, tmp_path):
    key, pubs = keypair
    opener, asset = _server(key)
    client = UpdateClient(repository=REPO, current_version="1.1.0", keys=pubs, opener=opener)
    info = client.check("stable")
    assert info is not None and info.version == "9.0.0" and info.asset.name == asset.name
    assert "Faster" in info.manifest.notes
    ua = opener.requests[0].headers.get("User-agent", "")
    assert ua.startswith("ResumeIntelligenceStudio/") and "@" not in ua
    seen = []
    path = client.download(info.asset, tmp_path, progress=lambda d, t: seen.append((d, t)))
    assert path.read_bytes() == b"installer-bytes" and seen[-1] == (len(b"installer-bytes"),) * 2
    assert UpdateClient(repository=REPO, current_version="9.0.0", keys=pubs, opener=opener).check() is None


@pytest.mark.req("UPD-02")
def test_client_ignores_unsigned_and_rejects_foreign_keys(keypair):
    key, pubs = keypair
    opener, _ = _server(key, signed=False)
    assert UpdateClient(repository=REPO, current_version="1.0.0", keys=pubs, opener=opener).check() is None
    opener2, _ = _server(Ed25519PrivateKey.generate())
    with pytest.raises(UpdateError, match="signature"):
        UpdateClient(repository=REPO, current_version="1.0.0", keys=pubs, opener=opener2).check()


@pytest.mark.req("UPD-02")
def test_beta_channel_only_sees_prereleases_when_chosen(keypair):
    key, pubs = keypair
    opener, _ = _server(key, version="9.1.0-beta.1", prerelease=True)
    client = UpdateClient(repository=REPO, current_version="1.0.0", keys=pubs, opener=opener)
    assert client.check("beta").version == "9.1.0-beta.1"
    # The stable endpoint returns the pre-release here; the client must still ignore it.
    assert client.check("stable") is None


@pytest.mark.req("UPD-03")
def test_download_rejects_wrong_checksum_and_oversized_files(keypair, tmp_path):
    key, pubs = keypair
    opener, asset = _server(key)
    client = UpdateClient(repository=REPO, current_version="1.0.0", keys=pubs, opener=opener)
    bad = UpdateAsset(**{**asset.__dict__, "sha256": "0" * 64})
    with pytest.raises(UpdateError, match="checksum"):
        client.download(bad, tmp_path)
    assert not list(tmp_path.iterdir())
    small = UpdateAsset(**{**asset.__dict__, "size": 3})
    with pytest.raises(UpdateError, match="larger"):
        client.download(small, tmp_path)


@pytest.mark.req("UPD-03", "SEC-03")
def test_only_github_https_hosts_are_contacted():
    _check_url("https://api.github.com/repos/x/y/releases/latest")
    _check_url("https://objects.githubusercontent.com/abc")
    for url in ("http://github.com/x", "https://evil.example.com/x", "https://github.com.evil.example/x",
                "file:///etc/passwd"):
        with pytest.raises(UpdateError):
            _check_url(url)


# --------------------------------------------------------------------------- installing


@pytest.mark.req("UPD-04")
def test_install_plans(tmp_path, monkeypatch):
    exe = tmp_path / "setup.exe"
    exe.write_bytes(b"x")
    win = installer.plan_install(exe, _asset(name="a.exe", kind="windows-installer"), kind="windows-installer")
    assert win.command[0] == str(exe) and "/SILENT" in win.command and win.quit_app
    assert "/NORESTARTAPPLICATIONS" in win.command and "/RESTARTAPPLICATIONS" not in win.command
    deb = installer.plan_install(tmp_path / "a.deb", _asset(name="a.deb", kind="linux-deb"), kind="linux-deb")
    assert deb.command[0] == "xdg-open" and not deb.quit_app
    src = installer.plan_install(exe, _asset(), kind="source")
    assert not src.quit_app and src.command[-1] == str(tmp_path)
    with pytest.raises(UpdateError):
        installer.plan_install(exe, _asset(kind="linux-tar"), kind="windows-installer")
    # macOS without a writable bundle falls back to opening the disk image.
    monkeypatch.setattr(installer, "app_bundle", lambda: None)
    mac = installer.plan_install(tmp_path / "a.dmg", _asset(name="a.dmg", kind="macos-dmg"), kind="macos-app")
    assert mac.command[0] == "open" and not mac.quit_app
    assert installer.install_kind() == "source"


@pytest.mark.req("UPD-04")
def test_linux_folder_update_stages_archive_and_rejects_unsafe_paths(tmp_path, monkeypatch):
    app_dir = tmp_path / "apps" / "ResumeIntelligenceStudio"
    app_dir.mkdir(parents=True)
    (app_dir / "ResumeIntelligenceStudio").write_text("old")
    monkeypatch.setattr(sys, "executable", str(app_dir / "ResumeIntelligenceStudio"))
    archive = tmp_path / "new.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        data = b"new"
        info = tarfile.TarInfo("ResumeIntelligenceStudio/ResumeIntelligenceStudio")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    plan = installer.plan_install(archive, _asset(), kind="linux-folder", pid=999999)
    script = Path(plan.command[1]).read_text()
    assert "kill -0 999999" in script and str(app_dir) in script and plan.quit_app
    evil = tmp_path / "evil.tar.gz"
    with tarfile.open(evil, "w:gz") as tf:
        info = tarfile.TarInfo("../../escape.txt")
        info.size = 1
        tf.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(UpdateError, match="unsafe"):
        installer.plan_install(evil, _asset(), kind="linux-folder")


# --------------------------------------------------------------------------- release tooling


@pytest.mark.req("UPD-05", "REL-06")
def test_release_manifest_script_build_sign_verify(tmp_path, keypair, monkeypatch):
    key, pubs = keypair
    raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                            serialization.NoEncryption())
    key_file = tmp_path / "key.txt"
    key_file.write_text(base64.b64encode(raw).decode())
    rel = tmp_path / "release"
    rel.mkdir()
    for name in ("ResumeIntelligenceStudio-1.1.0-windows-x64-setup.exe", "ResumeIntelligenceStudio-1.1.0-macos-arm64.dmg",
                 "ResumeIntelligenceStudio-1.1.0-linux-x86_64.tar.gz", "resume-intelligence-studio_1.1.0_amd64.deb",
                 "ResumeIntelligenceStudio-1.1.0-windows-x64-portable.zip"):
        (rel / name).write_bytes(name.encode())
    script = ROOT / "scripts" / "release_manifest.py"
    out = subprocess.run([sys.executable, str(script), "build", "--dir", str(rel), "--version", "1.1.0", "--tag",
                          "v1.1.0", "--repo", REPO], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    manifest = json.loads((rel / "ris-update.json").read_text())
    kinds = {(a["platform"], a["kind"]) for a in manifest["assets"]}
    assert kinds == {("windows-x64", "windows-installer"), ("macos-arm64", "macos-dmg"),
                     ("linux-x86_64", "linux-tar"), ("linux-x86_64", "linux-deb")}
    assert len((rel / "SHA256SUMS.txt").read_text().splitlines()) == 5
    assert "Training" in manifest["notes"] or manifest["notes"]
    # The script refuses to sign with a key the application would not accept …
    bad = subprocess.run([sys.executable, str(script), "sign", "--manifest", str(rel / "ris-update.json"),
                          "--key-file", str(key_file)], capture_output=True, text=True)
    assert bad.returncode != 0 and not (rel / "ris-update.json.sig").exists()
    # … and signs when the key matches the embedded public key.
    from ris.update import keys

    monkeypatch.setattr(keys, "PUBLIC_KEYS", pubs)
    monkeypatch.setattr(keys, "REPOSITORY", REPO)
    import importlib.util

    spec = importlib.util.spec_from_file_location("release_manifest", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.cmd_sign(type("A", (), {"manifest": str(rel / "ris-update.json"), "key_file": str(key_file)})()) == 0
    data = (rel / "ris-update.json").read_bytes()
    assert verify_manifest(data, (rel / "ris-update.json.sig").read_bytes(), pubs, REPO).version == "1.1.0"
    assert mod.cmd_verify(type("A", (), {"manifest": str(rel / "ris-update.json"), "sig": "",
                                         "dir": str(rel)})()) == 0
