# Changelog

## 1.0.0 — 2026-10-25

First release.

### Added
* Master profile with 20 record kinds, verification statuses, four disclosure classifications, private
  particulars, custom fields and custom sections; soft delete with restore.
* Areas of expertise, referees (exported only with recorded permission), research grants, peer review,
  student supervision and conference organisation; research metrics with source and date.
* Import from profile JSON, CSV (column mapping), TXT, DOCX and PDF — always as unconfirmed, requiring review.
* Defence & Intelligence career mode: ten presets, twelve organisation profiles, glossary translation.
* Vacancy analysis: rule-based requirement extraction, evidence matching (six statuses), transparent
  weighted score with explanation, readiness checklist, official-verification items.
* Resume Studio with eleven modes and fifteen templates, including three graphical templates (Graphical
  Career Profile, Research Showcase, Infographic Timeline) with career timeline charts, five-step
  self-assessed competency bars, metric tiles, publications-by-year chart, project cards and contact icons.
* Claim-level wording assistant (offline rules engine; optional external AI with request preview).
* DOCX and PDF export (LibreOffice or built-in engine) with validation, fit-to-page, immutable versions,
  version comparison, export log with SHA-256, redacted portfolio and cover letters.
* Application tracker, dashboard with real metrics only.
* Backups (plain and AES-256-GCM), verification, restore with pre-restore snapshot, integrity checks,
  portable JSON export, data-folder relocation.
* Optional synchronisation through a folder or Google Drive (`drive.file`) with encryption, confidential
  redaction and conflict resolution.
* Diary-inspired PySide6 interface with eighteen sections, light and dark themes (WCAG AA contrast).
* Self-test (`--selftest`), headless CLI (`python -m ris.cli`), PyInstaller specification, launchers.

### Known limitations
* The built-in PDF engine cannot shape complex scripts (for example Devanagari); export validation fails
  clearly and recommends LibreOffice. Latin, Greek and common symbols work.
* Letter-spacing in headings is applied in DOCX/LibreOffice output but not by the built-in PDF engine.
* Graphical templates are designed for reading by people; use the ATS template for online portals.
* Charts are embedded as 300-dpi images (with alt text); the same facts appear as text beside them.
* Google Drive sync and external AI providers were tested against mocked services only; no live account
  or API was used during development.
* The Windows and macOS launchers and PyInstaller builds were not run on those platforms during
  development; the Linux one-folder build was built and passed `--selftest`.
* In Word and LibreOffice, headings inside two-column templates may occasionally be separated from the
  following line at a page break (keep-with-next is disabled there to allow the columns to split).
* Requirement extraction from vacancy notices is rule-based; always review the extracted list.
* Resume Studio has a single mode; a separate Guided/Advanced switch is not implemented (per-resume wording
  is still kept apart from profile statements).
* Interface text is English only and dates use a fixed English format rather than the system locale.
* DOCX output was checked with LibreOffice and python-docx, not with Microsoft Word.
