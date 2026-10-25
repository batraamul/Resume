# Releasing a new version (maintainers)

Releases are built by GitHub Actions from a version tag. You do not need a Mac or Windows computer.

## One-time setup

1. **Update signing key.** Add the repository secret **`RIS_UPDATE_SIGNING_KEY`** (Settings → Secrets and
   variables → Actions → New repository secret) containing the base64 Ed25519 private key whose public half
   is in `ris/update/keys.py`. Keep a copy in a password manager; never commit it.
   To create a new key pair instead:
   ```bash
   python scripts/release_manifest.py genkey --out signing-key.txt
   ```
   Put the printed public key in `ris/update/keys.py` (keep the old key there until a release signed with
   the old key has shipped), store the file's contents as the secret, then delete the file.
2. **Protect the release path.** Protect the `main` branch and `v*` tags, and require review for changes to
   `.github/workflows/`.
3. **Optional code signing** (removes operating-system warnings):
   * macOS: secrets `MACOS_CERTIFICATE_P12` (base64 Developer ID Application certificate),
     `MACOS_CERTIFICATE_PASSWORD`, `MACOS_SIGN_IDENTITY`, `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD`
     (app-specific password). The workflow then signs, notarises and staples the app
     (`packaging/macos/sign_and_notarise.sh`).
   * Windows: sign `dist\installer\*.exe` with your certificate (`signtool`, see INSTALL.md) — add a step to
     the workflow when you have a certificate.

## Every release

1. Update `__version__` in `ris/__init__.py` and `version` in `pyproject.toml`.
2. Add a `## <version> — <date>` section to `CHANGELOG.md` (it becomes the release notes and the text shown
   in the update dialog).
3. Run the checks: `ruff check ris tests scripts docs/tutorial` and `QT_QPA_PLATFORM=offscreen python -m pytest`.
4. Commit, then tag and push:
   ```bash
   git tag -a v1.2.0 -m "Resume Intelligence Studio 1.2.0"
   git push origin main v1.2.0
   ```
   Use a tag like `v1.3.0-beta.1` for a test release (published as a pre-release; only users on the beta
   channel are offered it).
5. The **Release** workflow:
   * checks that the tag matches `ris.__version__`;
   * runs the unit, integration and security tests on Windows, macOS and Linux;
   * builds the application with PyInstaller and runs its `--selftest` on each system;
   * packages `…-windows-x64-setup.exe` (Inno Setup, per-user) and a portable zip, `…-macos-arm64.dmg`, and
     `…-linux-x86_64.tar.gz` plus `resume-intelligence-studio_<version>_amd64.deb`;
   * writes `ris-update.json` and `SHA256SUMS.txt`, signs the manifest (and checks the signature with the
     public key the application uses), records build provenance, and publishes the GitHub Release.
6. Check the release page: all files present, notes correct, `ris-update.json.sig` attached.

## If the signing secret is missing

The workflow publishes a **draft**. Sign it on your own computer and publish:

```bash
gh release download v1.2.0 --repo batraamul/Resume --pattern 'ris-update.json' --dir release
RIS_UPDATE_SIGNING_KEY="$(cat signing-key.txt)" python scripts/release_manifest.py sign --manifest release/ris-update.json
gh release upload v1.2.0 release/ris-update.json.sig --repo batraamul/Resume
gh release edit v1.2.0 --draft=false --repo batraamul/Resume
```

## Re-running a build

Actions → Release → *Run workflow* with the existing tag. Delete the old release first if it was created.
