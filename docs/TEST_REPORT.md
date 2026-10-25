# Test report — version 1.0.0

Date of the final run: 25 October 2026. This report states what was actually run, what passed, and what
was **not** verified. Programmatic validation of a document is not the same as looking at it; the pages that
were inspected visually are listed separately.

## Environment

| Item | Value |
|---|---|
| Operating system | Linux 6.18 (x86-64, glibc 2.39), Qt offscreen platform for GUI tests |
| Python | 3.13.17 in a virtual environment created from `requirements.txt` + `requirements-dev.txt` |
| Key packages | PySide6 6.12.0, pydantic 2.14.1, python-docx 1.2.0, reportlab 5.1.0, pypdf 6.21.2, cryptography 50.0.2, Pillow 13.0.0 |
| SQLite | 3.53.1 with FTS5 |
| LibreOffice | 24.2.7.2 (`/usr/bin/soffice`) — used by the LibreOffice-engine tests and checks |
| Credential store | None available in the container: keyring disabled in tests (`RIS_DISABLE_KEYRING=1`); the session-only fallback was exercised |
| Network | No live network services were used. Google Drive and AI providers were tested against mocked sessions only |

## Automated test suite

Command (from the project folder):

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

**Result: 257 passed, 0 failed, 0 skipped in 277 s (4 min 37 s)** — in the development environment and
again in a clean installation from the release ZIP (see *Packaging and start-up*).

| Suite | Folder | Tests |
|---|---|---|
| Unit | `tests/unit` | 91 |
| Integration | `tests/integration` | 48 |
| Documents (all templates × profiles, DOCX + PDF, LibreOffice) | `tests/documents` | 72 |
| Security and privacy | `tests/security` | 16 |
| Synchronisation | `tests/sync` | 12 |
| Desktop interface (pytest-qt, offscreen) | `tests/gui` | 17 |
| End-to-end workflow | `tests/e2e` | 1 |

No tests were skipped or marked as expected failures in this run. Lint: `ruff check ris tests scripts` —
no findings.

Requirement traceability (`python scripts/trace_requirements.py` → [REQUIREMENTS.md](REQUIREMENTS.md)):
of 126 requirements, 120 have passing automated tests and 6 have none (PRF-19, STU-03, UX-03, UX-07, REL-02, REL-05); none are failing. Requirements without an automated test are listed there with notes; most are interface
behaviours checked manually (see below) or platform work that was not possible here.

### Performance (1,442-record profile, from `build/test-results/performance.json`)

| Operation | Time |
|---|---|
| Create 1,442 records | 0.66 s |
| Profile snapshot | 0.05 s |
| Vacancy analysis | 0.08 s |
| 50-page academic CV — compose / layout / built-in PDF | 0.02 s / 0.01 s / 0.69 s |
| 51-page research portfolio — compose / layout / built-in PDF | 0.03 s / 0.06 s / 1.00 s |
| Fit a general resume to two pages | 2.77 s |

Timings are from one run on the development container and will differ on other machines.

## Document checks beyond the test suite

* `python scripts/generate_examples.py` (built-in PDF engine): all **15 templates** exported from the
  fictional sample and passed export validation (contents, contacts, chronology, confidential phrases,
  page limits, DOCX/PDF consistency). Files are in `examples/`.
* `python scripts/generate_examples.py --engine libreoffice`: all **15 templates** exported with
  LibreOffice producing the PDF and passed the same validation (page counts in `examples/README.md`).
  This run found that letter-spaced headings in two templates (Executive Technical, Modern Professional)
  were extracted from LibreOffice PDFs as "P R O F E S S I O N A L", which failed the presence check. The
  validator now also reads re-joined letter-spaced runs (the original text is always checked as well); a
  unit test covers it.

### Visually inspected (rendered to images and looked at)

* Contact sheets of the first page of all 15 templates, built-in engine (`examples/overview_first_pages.png`)
  and LibreOffice (`examples/overview_first_pages_libreoffice.png`) — at thumbnail resolution.
* Graphical Career Profile, pages 1–2 (built-in and LibreOffice) at readable resolution: framed banner,
  areas of expertise, career-timeline chart, sidebar competency bars, contact icons.
* Research Showcase, all four pages (built-in): metric tiles, publications-by-year chart, publication
  lists, grants, project cards, professional service, competency bars and the referee section.
* Infographic Timeline, pages 1–2 (built-in).
* The two draft previews made from the user's preliminary profile (delivered separately, not in the release).
* Desktop interface screenshots of all 18 pages (`--screenshot`, light theme, 1440 × 900), from source and
  from the frozen build; the Diary, Master Profile, Research & Publications, Experience, Opportunities and
  Resume Studio pages were reviewed closely.

Other generated documents were validated programmatically only. No DOCX file was opened in Microsoft Word.

## Packaging and start-up

* `python run_application.py --selftest` — passed (packages, SQLite FTS5, 15 templates, fonts, LibreOffice,
  credential store fallback, validated sample export, Qt).
* PyInstaller one-folder build on Linux (`pyinstaller packaging/ris.spec`) — built; the frozen
  application passed `--selftest` and rendered all 18 pages with `--screenshot`. Size about 265 MB.
* Release ZIP built with `scripts/make_release.py` with `RIS_RELEASE_FORBIDDEN` set to the developer-supplied
  personal strings; the scan (file names, text, and the text inside DOCX and PDF files) found nothing.
* Clean-install check: the release ZIP was extracted into an empty folder, a new virtual environment was
  created with `python3 -m venv .venv` and `pip install -r requirements-dev.txt` (pinned versions resolved
  exactly), then the full suite ran there — **257 passed, 0 failed, 0 skipped (277 s)** — and
  `run_application.py --selftest` passed. This run used the code exactly as shipped; the only files that
  differ in the final ZIP are this report and the known-limitations list in CHANGELOG.md.

## Not verified

* macOS and Windows: the launchers, `--selftest`, the PyInstaller builds, the `.app` bundle, code signing
  and notarisation were **not run** on those platforms.
* Google Drive synchronisation and external AI providers against real accounts or keys (only mocked HTTP
  sessions and an in-memory remote were used).
* Screen-reader use (VoiceOver, NVDA) and high-DPI rendering on physical displays.
* Opening the DOCX outputs in Microsoft Word; layout in Word may differ from LibreOffice.
* Behaviour with OS credential stores (macOS Keychain, Windows Credential Manager, Secret Service).
* Long-term use, upgrade from a previous release (there is none), and very large attachments.
* No independent security review or penetration test was performed.
