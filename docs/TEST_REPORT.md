# Test report — version 1.2.0

Date of the final run: 25 October 2026. This report states what was actually run, what passed, and what
was **not** verified. Programmatic validation of a document is not the same as looking at it; the pages that
were inspected visually are listed separately. Earlier reports are kept in the Git history.

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

**Result: 345 passed, 0 failed, 0 skipped in 971 s (16 min 11 s).**

| Suite | Folder | Tests |
|---|---|---|
| Unit | `tests/unit` | 150 |
| Integration | `tests/integration` | 49 |
| Documents (all templates × profiles, DOCX + PDF, LibreOffice) | `tests/documents` | 84 |
| Security, privacy and documentation accuracy | `tests/security` | 20 |
| Synchronisation | `tests/sync` | 12 |
| Desktop interface (pytest-qt, offscreen) | `tests/gui` | 29 |
| End-to-end workflow | `tests/e2e` | 1 |

New in 1.2 (26 tests): the deputation proforma (items, blank private items unless opted in, own answers, employer's certificate), export and validation of the three new formats, format recommendations, chart choice validation and drawing, chart styles changing or removing images while the facts stay in text, the openings-list import (mapping, add/update/skip, malformed files), the three new templates with every test profile, and GUI tests for the Studio chart and proforma controls, the openings import and the recruiter formats.

New in 1.1 (62 tests): training records and sections, interview question bank, personalisation, STAR analysis
and questionnaires, job-portal kit and file checks, ATS readiness, appearance presets and overrides, update
manifest signing and verification, update client (host allow-list, redirects, size and checksum checks,
channels, downgrades), installer plans, migration 0002 upgrade of a 1.0 database, GUI tests for the new pages
and dialogs, and the developer-guide checks (the tutorial code printed in the guide is identical to the tested
files, the tutorial's own five tests pass, and every path and function the guide names exists).

Lint: `ruff check ris tests scripts docs/tutorial` — no findings.

Requirement traceability (`python scripts/trace_requirements.py` → [REQUIREMENTS.md](REQUIREMENTS.md)):
of 157 requirements, 151 have passing automated tests and 6 have none (PRF-19, STU-03, UX-03, UX-07, REL-02,
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

* `python scripts/generate_examples.py` (built-in PDF engine) and `--engine libreoffice`: all **18
  templates** exported from the fictional sample and passed export validation with both engines (page counts
  in `examples/README.md`). The Government CV is one page shorter than in 1.1 with the built-in engine
  because table rows are now kept whole and headings no longer push long tables to the next page.

### Visually inspected (rendered to images and looked at)

* Version 1.2, built-in engine: the deputation proforma (all seven pages: items 1–18, declaration and the
  employer's certificate), the Senior Scientist Dossier (first four pages) and the Senior Scientist Graphical
  profile in its default chart styles and with donut / line / pie / dots / text styles; the Senior Scientist
  Graphical first page with the LibreOffice engine. These checks found and led to fixes for a page left almost
  empty before a long table, a table row cut in the middle, shortened evidence text in the requirements table
  and oversized pie charts.

* Government CV (built-in engine), pages 4–5: the new *Training programmes*, *Professional courses* and
  *Workshops, seminars & conferences attended* tables and the *Certifications & licences* entries (credential,
  validity, expired language test marked "Expired").
* Contact sheet of the first page of all templates (`examples/overview_first_pages.png`) at thumbnail
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
* **Release workflow dry run** (`.github/workflows/release.yml`, branch `release-dry-run`, commit `2f20bc4`,
  nothing published). Each job ran the unit, integration and security suites, built the application with
  PyInstaller, ran the frozen program's `--selftest`, and packaged it. Results as reported by the jobs'
  annotations:

  | Runner | Tests | Frozen self-test | Packages |
  |---|---|---|---|
  | Windows Server 2025, Python 3.12.10 | 208 passed, 0 failed | passed (8 checks) | `…-windows-x64-setup.exe` (55 MB), `…-windows-x64-portable.zip` (80 MB) |
  | macOS 26.6 (Apple silicon), Python 3.12.10 | 208 passed, 0 failed | passed (8 checks) | `…-macos-arm64.dmg` (73 MB) |
  | Ubuntu 22.04 (glibc 2.35), Python 3.12.15 | 208 passed, 0 failed | passed (8 checks) | `…-linux-x86_64.tar.gz` (112 MB), `…_amd64.deb` (88 MB) |

  The eight checks are: Python packages, SQLite with FTS5, templates, embedded fonts, LibreOffice (optional;
  reported as absent on the runners), credential store, a validated DOCX + PDF sample export, and Qt.
  The publish step (manifest, signature, provenance, GitHub Release) was not part of the dry run; the manifest
  build, signing and verification commands were tested locally and by `tests/unit/test_updates.py`.

## Not verified

* Installing and using the Windows and macOS builds interactively on a physical computer (including
  SmartScreen and Gatekeeper prompts, Start-menu and Applications shortcuts, and uninstalling). The packages
  were built and the frozen programs self-tested on GitHub's runners, but the installers themselves were not
  run.
* The publish job of the release workflow (it runs for the first time with the first real release).
* An update from one published release to the next on a real installation (1.1.0 is the first release that
  contains the updater; the first real update will be to the following version).
* Google Drive synchronisation and external AI providers against real accounts or keys.
* Screen-reader use (VoiceOver, NVDA) and high-DPI rendering on physical displays.
* Opening the DOCX outputs in Microsoft Word; layout in Word may differ from LibreOffice.
* Behaviour with OS credential stores (macOS Keychain, Windows Credential Manager, Secret Service).
* No independent security review or penetration test was performed.
