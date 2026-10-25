# Implementation Status

This file preserves progress between development sessions. Update it at the end of every phase.
Evidence for each statement is in [TEST_REPORT.md](TEST_REPORT.md) and [REQUIREMENTS.md](REQUIREMENTS.md).

## Current phase

Version 1.0.0 — all planned phases complete. Release ZIP built by `scripts/make_release.py`.

## Completed (with tests)

- Phase 1: architecture, requirements register (`docs/requirements.toml`, 126 requirements), PRD, threat model.
- Phase 2a: domain models (`ris/domain`, 20 record kinds; awards, patents, talks, grants, peer review and similar
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

## Outstanding (see BACKLOG.md)

- Builds and launchers have not been run on macOS or Windows; no code signing or notarisation.
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

1. Run `--selftest` and the PyInstaller build on macOS and Windows; sign the builds.
2. Live test Google Drive sync with a real OAuth client and an external AI provider with a real key.
3. Vector charts and complex-script shaping in the built-in PDF engine.
