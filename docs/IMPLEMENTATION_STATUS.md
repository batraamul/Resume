# Implementation Status

This file preserves progress between development sessions. Update it at the end of every phase.
Evidence for each statement is in [TEST_REPORT.md](TEST_REPORT.md) and [REQUIREMENTS.md](REQUIREMENTS.md).

## Current phase

Version 1.1.0 — installers for Windows, macOS and Linux built by GitHub Actions, signed automatic updates,
training sections, interview preparation, job-portal kit, appearance and template customisation, developer
guide. Source code at <https://github.com/batraamul/Resume>.

## Completed (with tests)

- Phase 1: architecture, requirements register (`docs/requirements.toml`, 126 requirements in 1.0, 149 in 1.1), PRD, threat model.
- Phase 2a: domain models (`ris/domain`, 20 record kinds in 1.0, 24 in 1.1; awards, patents, talks, grants, peer review and similar
  items are typed activities), SQLite record store with migrations, FTS5 search,
  revisions, audit, settings, workspaces and relocation, profile services (snapshot, completeness,
  chronology, duplicates).
- Phase 2b: IR (`ris/composition/ir.py`), 11 resume modes, composer, 15 template specs (12 classic,
  3 graphical), layout planner, DOCX renderer, built-in PDF renderer (embedded fonts, glyph fallback),
  LibreOffice converter, text export, validation, export service (review gating, fit-to-page, versions,
  no-overwrite, export log).
- Phase 2c: backups (plain and AES-256-GCM), verify/restore with pre-restore snapshot, cloud-safe archives,
  integrity checks, portable JSON import/export, CSV/TXT/DOCX/PDF importers, vacancy-from-file.
- Phase 2d: PySide6 desktop interface — diary-inspired theme (light/dark/system, WCAG AA checked), 18
  pages, record editor generated from the models, review/suggestion/report/conflict dialogs, background
  workers, unsaved-change protection, keyboard shortcuts, accessible names.
- Phase 3: vacancy extraction, evidence matching, transparent 35/25/15/10/10/5 scoring, readiness, presets
  and organisation profiles, disclosure scanner, ATS/quality checks, claim validation, rewriting assistant
  (offline rules; optional external provider with payload preview), glossary.
- Phase 4a: cover letters drafted from confirmed facts, redacted portfolio, application tracker, resume
  library with immutable versions, comparison and re-export.
- Phase 4b: record-level three-way sync engine, folder remote and Google Drive remote (`drive.file`,
  OAuth desktop flow, tokens in the OS keychain), encryption of synced records, conflict UI.
- Phase 4c (graphical resumes): areas of expertise, referees (permission-gated), research metrics,
  short organisation names, position highlights; three graphical templates (Graphical Career Profile,
  Research Showcase, Infographic Timeline) with career-timeline and publications-by-year charts,
  competency bars, metric tiles, project cards and contact icons — all derived from recorded data, with
  alt text and the same facts as selectable text.
- Phase 5: GUI, security, sync, end-to-end and performance tests; documentation; PyInstaller spec and Linux
  one-folder build; self-test; screenshot mode; examples; release script with secret/personal-data scan.

- Version 1.1 (all with tests):
  - Training & Certifications: `training` record kind (programmes, mandatory training, professional and online
    courses, certifications and licences with expiry, language tests, workshops, seminars, faculty development,
    other qualifications); dedicated resume sections in every relevant mode; government bio-data tables.
  - Interview Preparation page: sourced question bank (about 70 questions), questions personalised from
    records, timed practice, saved answers, STAR story editor with live analysis, personal questionnaire
    (PIQ/DAF) with fill-from-profile and consistency check, interview pack and questionnaire export.
  - Job Portals & Recruiters page: recruiter directory with routes and sources, portal guidance, LinkedIn /
    Naukri / Indeed profile kit from confirmed facts with live limits, ATS readiness and file checks; new
    profile links (Naukri, Indeed, Scopus, ResearcherID). Research notes in RESEARCH_FINDINGS.md.
  - Appearance: six colour presets (light and dark, WCAG AA), per-colour overrides with automatic contrast
    correction, fonts, text size, density, corner radius, navigation style/side, editor layout, start page;
    import/export of settings. Template designer generated from the template schema with live preview,
    readability and ATS checks.
  - Studio "Add section" menu; migration 0002 (new document kinds).
  - Distribution: application icons; PyInstaller spec for all platforms; Windows Inno Setup installer and
    portable zip; macOS DMG (optional signing/notarisation); Linux tar.gz and .deb; CI on Windows, macOS and
    Linux; release workflow with frozen self-tests, signed manifest and build provenance.
  - Secure automatic updates (`ris/update`): Ed25519-signed manifest, GitHub-only HTTPS, verified downloads,
    per-platform installation, channels, skip/remind, privacy note.
  - DEVELOPER_GUIDE.md with the tested Resume Lite tutorial.

## Outstanding (see BACKLOG.md)

- No Apple or Microsoft code-signing certificate is configured, so the operating systems warn on first install.
- The macOS build is for Apple silicon (arm64); Intel Macs run from source.
- Interactive installation and the update flow on real Windows and macOS desktops are verified by the release
  workflow's automated self-tests only, not by a person (see TEST_REPORT.md).
- Google Drive sync and external AI providers verified only against mocked services.
- Built-in PDF engine: no complex-script shaping (Devanagari) — LibreOffice required for those.
- Charts are raster (300 dpi) images rather than vector drawings.

## Development environment

- Virtualenv: `/home/claude/.venvs/ris` (outside the project tree).
- Run tests: `QT_QPA_PLATFORM=offscreen /home/claude/.venvs/ris/bin/python -m pytest -q`.
- Results of the last full run are recorded in TEST_REPORT.md.

## Known issues / decisions

- Built-in PDF engine cannot shape complex scripts; validation fails loudly and suggests LibreOffice.
- Letter spacing in headings is applied in DOCX/LibreOffice output but not in the built-in PDF engine.
- In two-column templates keep-with-next is cleared so that LibreOffice/Word can split the column row
  across pages; a heading can occasionally end a page.
- Skill levels are optional and never inferred; competency bars appear only for skills with a recorded level.

## Exact next steps

1. Add the `RIS_UPDATE_SIGNING_KEY` repository secret so releases are signed and published automatically.
2. Install each 1.1.0 package on a real Windows, macOS and Linux desktop; when 1.1.1 or 1.2.0 is released,
   test the update from 1.1.0 end to end.
3. Code-sign the Windows installer and notarise the macOS app when certificates are available.
4. Live test Google Drive sync with a real OAuth client and an external AI provider with a real key.
5. Vector charts and complex-script shaping in the built-in PDF engine.
