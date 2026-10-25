# Automatic updates

Resume Intelligence Studio can find, verify and install new versions published on
[GitHub Releases](https://github.com/batraamul/Resume/releases).

## For users

* **Settings & Security → Updates**: turn automatic checks on or off, choose *Stable* or *Stable and test
  (beta)* releases, or press *Check for updates now*. The first-run window has the same switch.
* When an update is found, an **Update available** button appears at the top of the window. It opens the
  release notes with three choices: *Download and install*, *Remind me later* or *Skip this version*.
* Installing never touches your data folder (profile database, backups, exports, settings).

| Installed from | What *Download and install* does |
|---|---|
| Windows installer | Runs the new per-user installer silently, then restarts the application. |
| macOS disk image | Closes the application, copies the new app over the old one, and reopens it. If the Applications folder is not writable, the disk image opens so you can drag the app across. |
| Linux `.tar.gz` | Closes the application, swaps the program folder, and restarts it. |
| Linux `.deb` | Opens the package in your software installer (administrator rights needed), or run `sudo apt install ./resume-intelligence-studio_<version>_amd64.deb`. |
| Source checkout | Saves the verified installer and opens its folder; update your checkout with `git pull`. |

### Privacy

An update check sends HTTPS requests only to GitHub (`api.github.com`, `github.com` and GitHub's download
hosts). The requests carry no personal data — only the header
`User-Agent: ResumeIntelligenceStudio/<version> (update check)`. GitHub can see your IP address, as with
any website. Automatic checks run at most once a day and can be turned off.

## Security design

1. **Signed manifest.** Each release contains `ris-update.json` (version, release notes, and for every
   installer its platform, download address, size and SHA-256) and `ris-update.json.sig`, an **Ed25519**
   signature of the exact manifest bytes.
2. **Embedded public key.** The application contains only the public key (`ris/update/keys.py`). A manifest
   that is unsigned, signed with another key, altered, written for another repository, or pointing outside
   `https://github.com/batraamul/Resume/releases/download/<version>/` is rejected.
3. **Verified download.** The installer is streamed to a temporary folder; if it is larger than the signed
   size, or its SHA-256 differs, it is deleted and nothing is installed.
4. **HTTPS to GitHub only**, including redirects; the bundled `certifi` certificates supplement the system
   trust store.
5. **No downgrades.** Only a version newer than the installed one is offered.
6. **User consent.** Nothing is installed without *Download and install*.
7. **Drafts for unsigned builds.** If the release workflow has no signing key, it publishes a draft that the
   application cannot see until a maintainer signs and publishes it.
8. **Build provenance.** Release files carry GitHub build-provenance attestations
   (`gh attestation verify <file> --repo batraamul/Resume`).

### What the signature does not cover

* The builds are not code-signed by Apple or Microsoft unless the optional certificates are configured (see
  [RELEASING.md](RELEASING.md)), so the operating system warns on first install.
* Anyone who obtains the private signing key can publish an update. Keep it only in the repository secret
  and an offline password manager. Rotate keys as described in `ris/update/keys.py`.
* Someone with write access to the repository could change the workflow to misuse the secret. Protect the
  `main` branch and tags, and require review for workflow changes.

## Verifying a download yourself

```bash
python scripts/release_manifest.py verify --manifest ris-update.json --dir .   # signature + checksums
sha256sum -c SHA256SUMS.txt                                                     # Linux / macOS (shasum -a 256 -c)
gh attestation verify ResumeIntelligenceStudio-1.1.0-windows-x64-setup.exe --repo batraamul/Resume
```
