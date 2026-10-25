"""Secure automatic updates.

How it works (see docs/UPDATES.md):

1. The release workflow publishes installers to GitHub Releases together with ``ris-update.json`` — a
   manifest listing each installer's download address, size and SHA-256 — and ``ris-update.json.sig``,
   an Ed25519 signature of the manifest made with the project's private signing key.
2. The application asks the GitHub Releases API for the newest release, downloads the manifest and its
   signature over HTTPS, and verifies the signature with the public key built into the application. An
   unsigned or tampered manifest is rejected.
3. If the signed version is newer, the user is offered the update. The installer is downloaded, its size and
   SHA-256 are checked against the signed manifest, and it is installed only after the user agrees.

Nothing else is sent: the requests carry no personal data, only the application name and version in the
User-Agent header. Automatic checks can be turned off in Settings.
"""

from ris.update.client import UpdateClient, UpdateInfo  # noqa: F401
from ris.update.manifest import UpdateAsset, UpdateError, UpdateManifest, platform_key, verify_manifest  # noqa: F401
