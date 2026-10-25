"""Signed update manifests: format, signature verification, version comparison and platform keys."""

from __future__ import annotations

import base64
import json
import platform
import re
import sys
from dataclasses import dataclass, field
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ris.errors import RISError
from ris.update.keys import PUBLIC_KEYS, REPOSITORY

APP_ID = "resume-intelligence-studio"
MANIFEST_NAME = "ris-update.json"
SIGNATURE_NAME = "ris-update.json.sig"
MAX_MANIFEST_BYTES = 256 * 1024
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class UpdateError(RISError):
    """An update could not be checked, verified, downloaded or installed."""


def parse_version(text: str) -> tuple:
    """Comparable version key. A release sorts after its pre-releases (1.2.0 > 1.2.0-beta.2)."""
    m = _VERSION.match((text or "").strip())
    if not m:
        raise UpdateError(f"'{text}' is not a valid version number.")
    major, minor, patch, pre = m.groups()
    pre_key: tuple = (1,) if not pre else (0, *[(0, int(p)) if p.isdigit() else (1, p) for p in pre.split(".")])
    return (int(major), int(minor), int(patch), pre_key)


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def platform_key() -> str:
    """The manifest key for this computer: windows-x64, macos-arm64, macos-x64 or linux-x86_64."""
    machine = platform.machine().lower()
    if sys.platform.startswith("win"):
        return "windows-arm64" if machine in ("arm64", "aarch64") else "windows-x64"
    if sys.platform == "darwin":
        return "macos-arm64" if machine in ("arm64", "aarch64") else "macos-x64"
    return "linux-aarch64" if machine in ("arm64", "aarch64") else "linux-x86_64"


@dataclass
class UpdateAsset:
    platform: str
    kind: str  # windows-installer | macos-dmg | linux-tar | linux-deb
    name: str
    url: str
    sha256: str
    size: int


@dataclass
class UpdateManifest:
    version: str
    released: str
    channel: str
    notes: str
    repository: str
    assets: list[UpdateAsset] = field(default_factory=list)

    def assets_for(self, plat: str) -> list[UpdateAsset]:
        return [a for a in self.assets if a.platform == plat]


def _check_asset(raw: dict[str, Any], repository: str, version: str) -> UpdateAsset:
    try:
        asset = UpdateAsset(platform=str(raw["platform"]), kind=str(raw["kind"]), name=str(raw["name"]),
                            url=str(raw["url"]), sha256=str(raw["sha256"]).lower(), size=int(raw["size"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise UpdateError("The update manifest lists an asset with missing fields.") from exc
    prefix = f"https://github.com/{repository}/releases/download/"
    if not asset.url.startswith(prefix) or "/../" in asset.url:
        raise UpdateError("The update manifest points outside this project's GitHub releases.")
    if f"/v{version}/" not in asset.url and f"/{version}/" not in asset.url:
        raise UpdateError("The update manifest points to a different release.")
    if not _SHA256.match(asset.sha256):
        raise UpdateError("The update manifest has an invalid checksum.")
    if not (0 < asset.size < 2 * 1024 ** 3):
        raise UpdateError("The update manifest has an invalid file size.")
    if "/" in asset.name or "\\" in asset.name or asset.name.startswith("."):
        raise UpdateError("The update manifest has an invalid file name.")
    return asset


def verify_manifest(data: bytes, signature: bytes, keys: tuple[str, ...] = PUBLIC_KEYS,
                    repository: str = REPOSITORY) -> UpdateManifest:
    """Verify the Ed25519 signature over the exact manifest bytes, then parse and check the contents."""
    if len(data) > MAX_MANIFEST_BYTES:
        raise UpdateError("The update manifest is unexpectedly large.")
    try:
        sig = base64.b64decode(signature.strip(), validate=True)
    except ValueError as exc:
        raise UpdateError("The update signature is not valid base64.") from exc
    verified = False
    for k in keys:
        try:
            Ed25519PublicKey.from_public_bytes(base64.b64decode(k)).verify(sig, data)
            verified = True
            break
        except (InvalidSignature, ValueError):
            continue
    if not verified:
        raise UpdateError("The update manifest's signature does not match this application's signing key. "
                          "The update was not installed.")
    try:
        raw = json.loads(data.decode("utf-8"))
    except ValueError as exc:
        raise UpdateError("The update manifest is not valid JSON.") from exc
    if raw.get("app") != APP_ID or raw.get("format") != 1:
        raise UpdateError("The update manifest is for a different application.")
    if raw.get("repository") != repository:
        raise UpdateError("The update manifest is for a different repository.")
    version = str(raw.get("version", ""))
    parse_version(version)
    assets = [_check_asset(a, repository, version) for a in raw.get("assets", [])]
    return UpdateManifest(version=version, released=str(raw.get("released", "")),
                          channel=str(raw.get("channel", "stable")), notes=str(raw.get("notes", ""))[:20000],
                          repository=repository, assets=assets)


# --------------------------------------------------------------------------- creating manifests (release tooling)


def build_manifest(version: str, released: str, notes: str, assets: list[UpdateAsset],
                   repository: str = REPOSITORY) -> bytes:
    parse_version(version)
    channel = "beta" if "-" in version.lstrip("v") else "stable"
    body = {"format": 1, "app": APP_ID, "repository": repository, "version": version.lstrip("v"),
            "released": released, "channel": channel, "notes": notes,
            "assets": [a.__dict__ for a in sorted(assets, key=lambda a: (a.platform, a.kind))]}
    return (json.dumps(body, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def load_private_key(text: str) -> Ed25519PrivateKey:
    """Accept a raw 32-byte key in base64 or a PEM-encoded PKCS#8 key."""
    text = text.strip()
    if text.startswith("-----BEGIN"):
        from cryptography.hazmat.primitives import serialization

        key = serialization.load_pem_private_key(text.encode(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise UpdateError("The signing key is not an Ed25519 key.")
        return key
    try:
        return Ed25519PrivateKey.from_private_bytes(base64.b64decode(text, validate=True))
    except ValueError as exc:
        raise UpdateError("The signing key is not a valid Ed25519 key.") from exc


def sign(data: bytes, private_key: Ed25519PrivateKey) -> bytes:
    return base64.b64encode(private_key.sign(data)) + b"\n"
