# Product Requirements Document — Resume Intelligence Studio (RIS)

**Tagline:** One Professional Profile. Every Opportunity. The Right Resume.

## 1. Problem

A senior Indian government scientific and technical professional applies to very different opportunities: defence R&D laboratories, technical intelligence organisations, aviation research, national laboratories, academic and industry roles. These applications are often made through deputation or direct recruitment. Each needs a differently emphasised resume, CV or bio-data, written truthfully, with nothing sensitive disclosed, in Word and PDF. Keeping many hand-edited Word files consistent is slow and error-prone. It also invites mistakes: wrong dates, a paper described as published when it is under review, internal project details leaking out.

## 2. Users

* **Primary:** the owner of the master profile (a scientist/engineer with electronics, avionics, instrumentation, AI/ML, embedded, drone and leadership experience).
* **Secondary:** anyone with a similar profile who installs the software (all personal data stays local).

## 3. Goals

1. Enter professional information once, in a structured, searchable, verifiable record.
2. Produce tailored, factual resumes and CVs for a target or a specific vacancy in minutes.
3. Make relevance and gaps visible and explainable, separating evidence-based relevance from formal eligibility.
4. Never fabricate, inflate or leak: provenance, confirmation and disclosure review are built in.
5. Produce genuine, editable DOCX and readable, selectable PDF that are validated before being reported as exported.
6. Keep the data safe: local-first, backups, integrity checks, optional encrypted cloud copies.

## 4. Non-goals

* Predicting selection, recruitment, appointment or security-clearance outcomes.
* Determining formal eligibility (age, pay level, cadre, deputation rules). The app flags these for official verification.
* Scraping recruitment websites or submitting applications.
* Multi-user collaboration or server deployment.

## 5. Scope by phase

| Phase | Scope |
|---|---|
| 1 | Environment assessment, architecture, requirements, data model, threat model |
| 2 | Desktop UI, master profile, SQLite persistence, validation, distinct templates, composition, DOCX, PDF, preview, backup/restore |
| 3 | Vacancy entry/import, requirement extraction, evidence mapping, transparent scoring, rewriting, Defence & Intelligence mode, disclosure review, claim validation |
| 4 | Full template library, versioning, application tracker, cover letters, Google Drive OAuth, backup sync, conflict resolution, optional AI provider |
| 5 | Test suite, defect fixing, verified outputs, packaging, clean-install check, documentation |

## 6. Success criteria (release gates)

* **A — Functional:** create/edit/persist profile; several modes; preview; genuine DOCX/PDF export.
* **B — Content quality:** traceable claims; controlled factual errors; correct section selection; readable documents.
* **C — Privacy & recovery:** confidential exclusion verified; secrets protected; restore verified.
* **D — Operational:** launches from a clean install; dependencies documented; critical tests pass.
* **E — Integrations:** cloud and AI tested to the extent claimed; unverified live integrations labelled.

## 7. Key product rules

* The master profile is the single source of truth. Resume edits are overrides stored with the variant.
* Every substantive sentence in an exported resume traces back to profile records.
* Facts awaiting confirmation, items requiring disclosure review and pending rewrites block export until resolved.
* Confidential records never leave the profile: not in exports, previews, logs, AI requests or cloud copies.
* Scores explain alignment with evidence; they are never probabilities.
* Previously exported files are never overwritten; every export is tied to an immutable version.

## 8. Requirements

The detailed register with IDs, priorities, implementation and test evidence is in `docs/requirements.toml`, rendered as `docs/REQUIREMENTS.md`.
