# Test plan

Run everything with `QT_QPA_PLATFORM=offscreen python -m pytest`. Each test is tagged with the requirement
ids it provides evidence for (`@pytest.mark.req`); `scripts/trace_requirements.py` turns the results into
`docs/REQUIREMENTS.md`. Every test runs against temporary data folders and the keyring is disabled, so the
suite can never touch real data or secrets.

| Suite | Folder | Covers |
|---|---|---|
| Unit | `tests/unit` | partial dates, models and validation, profile services (completeness, chronology, duplicates), composer rules (confidential exclusion, nesting, planned qualifications, publication wording, private particulars), vacancy extraction, evidence matching, scoring, readiness, presets, disclosure scan, claim validation, rewriting, glossary, graphics (charts, bars, tiles, timeline maths, referee permission, expertise, card facets) |
| Integration | `tests/integration` | SQLite store (revisions, soft delete, concurrency, FTS, migrations, newer-schema refusal), export service (review gate, fit, versions, no overwrite, export log), backups (plain/encrypted, verify, restore, pre-restore snapshot, zip-slip), importers, large-profile performance |
| Documents | `tests/documents` | every template × short / long / incomplete / Unicode profiles, long titles, many publications, large skill lists, missing photo; DOCX and PDF validation; LibreOffice conversion when installed; complex-script failure |
| Security | `tests/security` | confidential leakage into every output, logs free of content and secrets, no telemetry or stray network code, business logic independent of the UI, temporary-file hygiene, AI payload refusal |
| Sync | `tests/sync` | three-way merge, conflicts and resolution, tombstones, redaction of confidential records, encryption, retries, offline and expired-auth faults, Google Drive adapter against a mocked HTTP session |
| GUI | `tests/gui` | eighteen pages open, accessible names, create/validate/revert a record, bulk confirm/classify, expertise and referee tabs, Studio preview (classic and graphical), export with validation, vacancy analysis, backup, theme switch, dashboard counts, sync with an in-memory remote |
| End-to-end | `tests/e2e` | import → review gate → confirm/approve → vacancy analysis → graphical export → encrypted backup → destructive change → restore → identical re-export of a saved version |

## Manual checks per release

1. `python run_application.py --selftest` on each target platform.
2. `python scripts/generate_examples.py` with the built-in engine and with LibreOffice; open several PDFs and
   DOCX files and look at them (record which ones in TEST_REPORT.md — programmatic validation is not visual review).
3. Screenshot pass: `python run_application.py --screenshot <folder>` renders every page of the sample workspace.
4. PyInstaller build and `--selftest` of the frozen application.
5. `python scripts/make_release.py` with `RIS_RELEASE_FORBIDDEN` set to your own name, email and phone.
6. Extract the ZIP into an empty folder, install from `requirements.txt` and run the test suite and self-test.
