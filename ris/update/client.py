"""Checking GitHub Releases for a signed update and downloading the installer safely.

Only HTTPS requests to GitHub hosts are made (redirects included). No personal data is sent.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import ssl
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from ris import __version__
from ris.update.keys import PUBLIC_KEYS, REPOSITORY
from ris.update.manifest import (
    MANIFEST_NAME,
    SIGNATURE_NAME,
    UpdateAsset,
    UpdateError,
    UpdateManifest,
    is_newer,
    platform_key,
    verify_manifest,
)

log = logging.getLogger(__name__)

ALLOWED_HOSTS = frozenset({
    "api.github.com", "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com",
    "github-releases.githubusercontent.com",
})
USER_AGENT = f"ResumeIntelligenceStudio/{__version__} (update check)"
CHUNK = 64 * 1024


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:  # bundled CA certificates help on systems whose Python lacks a usable trust store (macOS builds)
        import certifi

        ctx.load_verify_locations(certifi.where())
    except (ImportError, OSError, ssl.SSLError):
        pass
    return ctx


def _check_url(url: str) -> None:
    u = urlparse(url)
    if u.scheme != "https" or (u.hostname or "") not in ALLOWED_HOSTS:
        raise UpdateError(f"Refusing to contact {u.hostname or url}: updates are only downloaded from GitHub over "
                          "HTTPS.")


class _SafeRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102 - urllib API
        _check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def default_opener():
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ssl_context()), _SafeRedirects())


@dataclass
class UpdateInfo:
    manifest: UpdateManifest
    release_url: str
    asset: UpdateAsset | None  # the installer for this computer, if one is published

    @property
    def version(self) -> str:
        return self.manifest.version


class UpdateClient:
    def __init__(self, *, repository: str = REPOSITORY, current_version: str = __version__,
                 keys: tuple[str, ...] = PUBLIC_KEYS, opener=None, timeout: float = 20.0) -> None:
        self.repository = repository
        self.current = current_version
        self.keys = keys
        self.opener = opener or default_opener()
        self.timeout = timeout

    # ------------------------------------------------------------------ http
    def _get(self, url: str, limit: int, accept: str = "application/octet-stream") -> bytes:
        _check_url(url)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                data = resp.read(limit + 1)
        except UpdateError:
            raise
        except OSError as exc:
            raise UpdateError("The update server could not be reached. Check your internet connection.",
                              detail=type(exc).__name__) from exc
        if len(data) > limit:
            raise UpdateError("The update server sent more data than expected.")
        return data

    def _releases(self, channel: str) -> list[dict]:
        base = f"https://api.github.com/repos/{self.repository}/releases"
        if channel == "stable":
            raw = self._get(base + "/latest", 2 * 1024 * 1024, "application/vnd.github+json")
            return [json.loads(raw)]
        raw = self._get(base + "?per_page=10", 4 * 1024 * 1024, "application/vnd.github+json")
        return json.loads(raw)

    # ------------------------------------------------------------------ check
    def check(self, channel: str = "stable") -> UpdateInfo | None:
        """Return the newest signed update for this computer, or None when you are up to date."""
        try:
            releases = self._releases(channel)
        except (ValueError, TypeError) as exc:
            raise UpdateError("The update server sent an unexpected reply.") from exc
        for rel in releases:
            if not isinstance(rel, dict) or rel.get("draft"):
                continue
            if rel.get("prerelease") and channel == "stable":
                continue
            assets = {a.get("name"): a for a in rel.get("assets", []) if isinstance(a, dict)}
            if MANIFEST_NAME not in assets or SIGNATURE_NAME not in assets:
                log.info("Release %s has no signed manifest; skipped", rel.get("tag_name"))
                continue
            data = self._get(assets[MANIFEST_NAME]["browser_download_url"], 256 * 1024)
            sig = self._get(assets[SIGNATURE_NAME]["browser_download_url"], 4096)
            manifest = verify_manifest(data, sig, self.keys, self.repository)
            if channel == "stable" and manifest.channel != "stable":
                continue
            if not is_newer(manifest.version, self.current):
                return None
            plat = platform_key()
            candidates = manifest.assets_for(plat)
            preferred = _preferred_asset(candidates)
            return UpdateInfo(manifest=manifest, release_url=str(rel.get("html_url", "")), asset=preferred)
        return None

    # ------------------------------------------------------------------ download
    def download(self, asset: UpdateAsset, folder: Path | None = None,
                 progress: Callable[[int, int], None] | None = None) -> Path:
        """Download an installer, checking its size and SHA-256 against the signed manifest."""
        _check_url(asset.url)
        folder = Path(folder or tempfile.mkdtemp(prefix="ris-update-"))
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / asset.name
        partial = folder / (asset.name + ".partial")
        req = urllib.request.Request(asset.url, headers={"User-Agent": USER_AGENT,
                                                         "Accept": "application/octet-stream"})
        digest = hashlib.sha256()
        received = 0
        try:
            with self.opener.open(req, timeout=self.timeout) as resp, open(partial, "wb") as fh:
                while True:
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > asset.size:
                        raise UpdateError("The download is larger than the signed manifest says.")
                    digest.update(chunk)
                    fh.write(chunk)
                    if progress:
                        progress(received, asset.size)
        except UpdateError:
            partial.unlink(missing_ok=True)
            raise
        except OSError as exc:
            partial.unlink(missing_ok=True)
            raise UpdateError("The download was interrupted. Try again later.", detail=type(exc).__name__) from exc
        if received != asset.size or digest.hexdigest() != asset.sha256:
            partial.unlink(missing_ok=True)
            raise UpdateError("The downloaded file does not match the signed checksum and was deleted.")
        os.replace(partial, target)
        if not asset.name.endswith((".exe", ".dmg", ".deb")):
            target.chmod(0o600)
        return target


def _preferred_asset(candidates: list[UpdateAsset]) -> UpdateAsset | None:
    if not candidates:
        return None
    from ris.update.installer import install_kind

    kind = install_kind()
    order = {"windows-installer": ["windows-installer"], "macos-app": ["macos-dmg"],
             "linux-deb": ["linux-deb", "linux-tar"], "linux-folder": ["linux-tar", "linux-deb"]}.get(
        kind, ["windows-installer", "macos-dmg", "linux-tar", "linux-deb"])
    for k in order:
        for a in candidates:
            if a.kind == k:
                return a
    return candidates[0]
