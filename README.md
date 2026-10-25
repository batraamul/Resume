# Resume Intelligence Studio

*One Professional Profile. Every Opportunity. The Right Resume.*

A local-first desktop application (macOS, Windows, Linux) for keeping one verified master professional
profile and producing accurate, tailored resumes for Defence, Intelligence, scientific and technical
posts — plain ATS resumes, Government of India bio-data, academic CVs and **graphical resumes** with
career-timeline charts, competency bars, research metric tiles and project cards.

Your data stays on your computer. Nothing is sent anywhere unless you turn on synchronisation or an AI
provider (the daily update check sends only the app name and version to GitHub and can be turned off), and the application never invents facts: every line in a document traces to a record you
entered and confirmed.

## What it does

* **Master profile** — personal details (with private particulars excluded by default), summaries,
  positions with concurrent responsibilities, statements, qualifications (completed / ongoing / planned),
  publications with exact status, projects, skills, areas of expertise, leadership, awards, patents,
  talks, grants, peer review, supervision, referees (only with recorded permission) and custom sections.
* **Verification and disclosure** — every fact is *Awaiting confirmation*, *Confirmed* or *Confirmed
  with evidence*, and *Public*, *Approved for professional use*, *Requires review* or *Confidential*.
  Unconfirmed and unreviewed facts cannot be exported; confidential ones never leave the profile.
* **Defence & Intelligence career mode** — ten presets and twelve organisation profiles (DRDO, NTRO,
  ARC, ISRO, ADA, CSIR, C-DAC, DST and others) that change emphasis only.
* **Vacancy analysis** — paste or import a notice; requirements are extracted by transparent rules,
  mapped to your evidence and scored 35/25/15/10/10/5 with a full explanation. The score is never a
  prediction of selection, and formal eligibility is always left to official verification.
* **Resume Studio** — 11 resume modes × 15 templates (12 classic, 3 graphical), section ordering,
  contact visibility, record inclusion, per-resume wording approved claim by claim, live preview.
* **Validated export** — genuine DOCX (real Word styles) and PDF (LibreOffice if installed, otherwise
  a built-in engine with embedded fonts), checked for content, contacts, chronology, confidential text,
  page limits and DOCX/PDF consistency before success is reported. Files are never overwritten.
* **Library and tracker** — immutable versions with comparison and re-export, cover letters drafted from
  confirmed facts, application tracker with deadlines, export log with checksums, redacted portfolio.
* **Backups and sync** — plain or AES-256-GCM encrypted backups with verification and pre-restore
  snapshots; optional encrypted record-level sync through a folder or Google Drive (`drive.file` scope).
* **Training & certifications** — dedicated sections for training programmes, professional courses,
  certifications and licences (with expiry), workshops and seminars, and other qualifications.
* **Interview preparation** — questions generated from your own record and the vacancy, a sourced question
  bank, timed practice, STAR story checks, and SSB PIQ / DAF-style questionnaires checked against your profile.
* **Job portals & recruiters** — recruiter directory, LinkedIn/Naukri/Indeed profile text within each
  portal's limits, an ATS readiness checklist and resume-file checks, with sources.
* **Make it yours** — colour presets, your own colours (contrast-checked), fonts, text size, density, icons,
  navigation and layout; a template designer with live preview and ATS checks.
* **Installers and automatic updates** — Windows, macOS and Linux installers built by GitHub Actions;
  signed, verified updates from GitHub Releases.

## Install

Download the installer for Windows, macOS (Apple silicon) or Linux from
**[GitHub Releases](https://github.com/batraamul/Resume/releases/latest)** — see
[docs/INSTALL.md](docs/INSTALL.md). Installed copies update themselves after verifying the project's signature
([docs/UPDATES.md](docs/UPDATES.md)).

## Run from source

| Platform | Start |
|---|---|
| macOS | Double-click `launch_macos.command` (right-click → Open the first time). |
| Windows | Double-click `launch_windows.bat`. |
| Linux | `./launch_linux.sh` |

The first launch creates a private Python environment in `.venv` and installs the pinned dependencies
(Python 3.11 or newer and an internet connection are needed once). Details: [docs/INSTALL.md](docs/INSTALL.md).

Check an installation at any time:

```bash
python run_application.py --selftest
```

Open the fictional sample workspace to explore safely: `python run_application.py --sample`.

## Documentation

| Topic | Document |
|---|---|
| Using the application | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) |
| Installation | [docs/INSTALL.md](docs/INSTALL.md) |
| Problems | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| Privacy and security | [docs/SECURITY_PRIVACY.md](docs/SECURITY_PRIVACY.md), [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) |
| Google Drive | [docs/GOOGLE_DRIVE_SETUP.md](docs/GOOGLE_DRIVE_SETUP.md) |
| Optional AI provider | [docs/AI_PROVIDER.md](docs/AI_PROVIDER.md) |
| Templates (including graphical) | [docs/TEMPLATE_GUIDE.md](docs/TEMPLATE_GUIDE.md) |
| Example outputs (every template) | [examples/README.md](examples/README.md) |
| Product requirements | [docs/PRD.md](docs/PRD.md), [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) |
| Architecture and data | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DATA_MODEL.md](docs/DATA_MODEL.md), [docs/UI_SPEC.md](docs/UI_SPEC.md) |
| Learning the code (beginner's guide) | [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) |
| Research behind 1.1 features | [docs/RESEARCH_FINDINGS.md](docs/RESEARCH_FINDINGS.md) |
| Updates and releases | [docs/UPDATES.md](docs/UPDATES.md), [docs/RELEASING.md](docs/RELEASING.md) |
| Testing | [docs/TEST_PLAN.md](docs/TEST_PLAN.md), [docs/TEST_REPORT.md](docs/TEST_REPORT.md) |
| Release | [CHANGELOG.md](CHANGELOG.md), [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md), [docs/BACKLOG.md](docs/BACKLOG.md) |

## Project layout

```
ris/              application package (domain, storage, services, composition, rendering, intelligence,
                  backup, sync, ai, security, update, ui)
templates/        15 template specifications (JSON)
migrations/       versioned SQL migrations
config/           taxonomy, career presets, glossary, interview questions, job portals, recruiters
assets/           bundled open fonts (with licences) and icons (SVG, ICO, ICNS, PNG)
sample_data/      fictional sample profile (not a real person)
tests/            unit, integration, documents, security, sync, GUI and end-to-end tests
scripts/          traceability, examples, data dictionary, source ZIP, update manifest signing, CI annotations
packaging/        PyInstaller spec, Windows installer (Inno Setup), macOS disk image, Linux .deb/.tar.gz
.github/workflows CI on Windows/macOS/Linux and the tagged release workflow
examples/         example DOCX/PDF for every template (fictional sample)
```

## Development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest      # 257 tests
.venv/bin/ruff check ris tests scripts docs/tutorial
python scripts/trace_requirements.py                       # docs/REQUIREMENTS.md
python scripts/generate_examples.py                        # examples/
pyinstaller packaging/ris.spec --noconfirm --clean         # dist/ResumeIntelligenceStudio/
```

## Status

Version 1.1.0. See [docs/TEST_REPORT.md](docs/TEST_REPORT.md) for exactly what was verified and how,
and [CHANGELOG.md](CHANGELOG.md) for known limitations. This software has not had an independent
security audit and is not claimed to be production-certified.
