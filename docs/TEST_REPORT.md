# Test report — version 1.1.0

Date of the final run: 25 October 2026. This report states what was actually run, what passed, and what
was **not** verified. Programmatic validation of a document is not the same as looking at it; the pages that
were inspected visually are listed separately. The version 1.0.0 report is kept in the Git history.

## Environment (local development run)

| Item | Value |
|---|---|
| Operating system | Ubuntu 24.04 (Linux 6.18, x86-64, glibc 2.39), Qt offscreen platform for GUI tests |
| Python | 3.13.17 in a virtual environment created from `requirements.txt` + `requirements-dev.txt` |
| Key packages | PySide6 6.12.0, pydantic 2.14.1, python-docx 1.2.0, reportlab 5.1.0, pypdf 6.21.2, cryptography 50.0.2, Pillow 13.0.0 |
| SQLite | 3.53.1 with FTS5 |
| LibreOffice | 24.2.7.2 — used by the LibreOffice-engine tests and checks |
| Credential store | None available in the container: keyring disabled in tests (`RIS_DISABLE_KEYRING=1`) |
| Network | No live Google Drive, AI or GitHub update services were used by the tests: the update client was tested with an in-memory fake that answers the GitHub release and download addresses |

## Automated test suite

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

**Result: 319 passed, 0 failed, 0 skipped in 788 s (13 min 8 s).**

| Suite | Folder | Tests |
|---|---|---|
| Unit | `tests/unit` | 139 |
| Integration | `tests/integration` | 49 |
| Documents (all templates × profiles, DOCX + PDF, LibreOffice) | `tests/documents` | 72 |
| Security, privacy and documentation accuracy | `tests/security` | 20 |
| Synchronisation | `tests/sync` | 12 |
| Desktop interface (pytest-qt, offscreen) | `tests/gui` | 26 |
| End-to-end workflow | `tests/e2e` | 1 |

New in 1.1 (62 tests): training records and sections, interview question bank, personalisation, STAR analysis
and questionnaires, job-portal kit and file checks, ATS readiness, appearance presets and overrides, update
manifest signing and verification, update client (host allow-list, redirects, size and checksum checks,
channels, downgrades), installer plans, migration 0002 upgrade of a 1.0 database, GUI tests for the new pages
and dialogs, and the developer-guide checks (the tutorial code printed in the guide is identical to the tested
files, the tutorial's own five tests pass, and every path and function the guide names exists).

Lint: `ruff check ris tests scripts docs/tutorial` — no findings.

Requirement traceability (`python scripts/trace_requirements.py` → [REQUIREMENTS.md](REQUIREMENTS.md)):
of 149 requirements, 143 have passing automated tests and 6 have none (PRF-19, STU-03, UX-03, UX-07, REL-02,
REL-05); none are failing.

## Continuous integration (GitHub Actions)

The CI workflow (`.github/workflows/ci.yml`) ran lint, the full suite and `--selftest` for commit `202f1ae`
(training, interview, portals, customisation) and for commit `2effd80` (installers, updater, developer guide):

| Runner | `202f1ae` | `2effd80` |
|---|---|---|
| Ubuntu, Python 3.11 | passed | passed |
| Ubuntu, Python 3.12 | passed | passed |
| Ubuntu, Python 3.13 | passed | passed |
| macOS (Apple silicon), Python 3.12 | passed | passed |
| Windows, Python 3.12 | passed | passed |

## Document checks beyond the test suite

* `python scripts/generate_examples.py` (built-in PDF engine) and `--engine libreoffice`: all **15
  templates** exported from the fictional sample and passed export validation with both engines. Page counts
  are in `examples/README.md`; the Government CV, Academic Extended CV and Research Showcase grew by one page
  because the sample now has training, course, certification and workshop records.

### Visually inspected (rendered to images and looked at)

* Government CV (built-in engine), pages 4–5: the new *Training programmes*, *Professional courses* and
  *Workshops, seminars & conferences attended* tables and the *Certifications & licences* entries (credential,
  validity, expired language test marked "Expired").
* Contact sheet of the first page of all 15 templates (`examples/overview_first_pages.png`) at thumbnail
  resolution.
* The 1.0 visual checks (graphical templates, screenshots of the pages) were not repeated page by page for
  1.1; the new pages and dialogs were exercised by the GUI tests, which check behaviour, not appearance.

Other generated documents were validated programmatically only. No DOCX file was opened in Microsoft Word.

## Packaging and start-up

* `python run_application.py --selftest` — passed locally and in every CI job.
* Linux, local: PyInstaller one-folder build, `--selftest` of the frozen program passed; the `.tar.gz` and
  `.deb` packages were built with `packaging/linux/make_packages.sh`; the `.deb` was installed with `dpkg` in
  the container (only `libxcb-cursor0` had to be added) and the installed program passed `--selftest`; the
  tar.gz self-update (folder swap and restart by the helper script) was run end to end with a locally signed
  manifest.
* Windows installer, portable zip and macOS disk image: built and self-tested only by the release workflow
  (`.github/workflows/release.yml`) on GitHub's Windows and macOS runners. That workflow runs after this
  report is committed; its outcome is shown on the
  [Actions page](https://github.com/batraamul/Resume/actions) and the
  [release page](https://github.com/batraamul/Resume/releases).

## Not verified

* Installing and using the Windows and macOS builds interactively on a physical computer (including
  SmartScreen and Gatekeeper prompts, Start-menu and Applications shortcuts, and uninstalling).
* An update from one published release to the next on a real installation (1.1.0 is the first release that
  contains the updater; the first real update will be to the following version).
* Google Drive synchronisation and external AI providers against real accounts or keys.
* Screen-reader use (VoiceOver, NVDA) and high-DPI rendering on physical displays.
* Opening the DOCX outputs in Microsoft Word; layout in Word may differ from LibreOffice.
* Behaviour with OS credential stores (macOS Keychain, Windows Credential Manager, Secret Service).
* No independent security review or penetration test was performed.
