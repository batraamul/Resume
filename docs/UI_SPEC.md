# User-interface specification

## Identity

Diary-inspired: a maroon index panel (#701C35) like the tabbed edge of a professional diary, ivory pages
(#FFF3DF), cream cards (#FFFAF0) and navy ink (#192B4B), with a gold ribbon marking the open section.
Headings use Caladea (a Cambria-compatible serif); body text uses Carlito (Calibri-compatible). A matching
dark theme (deep navy pages, lighter maroon accents, ivory ink) and a "follow the system" option are available.
All text/background pairs are listed in `ris/ui/theme.py` and checked for WCAG 2.1 AA contrast by the tests.

## Layout

```
┌──────────────┬──────────────────────────────────────────────────────────────┐
│ Diary index  │ Top bar: workspace · search (Ctrl+F) · sync status           │
│ (18 sections │ [Fictional sample banner when the sample workspace is open]  │
│  in 5 groups)│ Page title + subtitle                       [page actions]   │
│              │ Page body (lists, editors, previews)                         │
│              │ Status bar (messages, progress)                              │
└──────────────┴──────────────────────────────────────────────────────────────┘
```

Groups and sections: **Diary** (My Professional Diary) · **Profile** (Master Profile, Experience, Education,
Research & Publications, Skills & Technologies, Projects & Achievements, Leadership & Responsibilities) ·
**Opportunities** (Career Targets, Job Opportunities) · **Documents** (Resume Studio, Resume Library, Cover
Letters, Application Tracker, Documents & Exports) · **System** (Synchronisation, Backup & Restore, Settings &
Security).

## Shared patterns

* **Collection pages**: filter box and status filter (All / Awaiting confirmation / Requires review /
  Confidential), a tree of records with linked items nested (positions → concurrent responsibilities →
  statements), Add / Add linked item / ↑ ↓ / Selected ▾ (confirm, classify, duplicate, delete), and the
  record editor on the right.
* **Record editor**: title, status chips (origin, verification, disclosure), contextual banner (preliminary,
  awaiting confirmation, requires review, confidential), verification and disclosure selectors with
  explanations, a form generated from the model (grouped fields, help text, private fields marked 🔒),
  revision line, Save (Ctrl+S) / Revert, extra actions (Improve wording ▾, Draft from confirmed facts, Delete).
  Unsaved changes are protected when switching records, pages or workspaces and when closing.
* **Suggestion dialog**: original and suggestion side by side, facts used, changes, flags, assumptions,
  missing metrics; material changes require an accuracy confirmation.
* **Review dialog** before export: blocking items and warnings with actions (confirm, approve, leave out,
  open record) and acknowledgement for sensitive wording.
* **Report dialogs**: validation checks with pass/warn/fail, fit adjustments, quality checks, files with
  SHA-256 and *Open folder*.
* Destructive operations always ask for confirmation, with the safer button as default.
* Background workers run rendering, conversion, export, backup and sync; results arrive on the interface thread.

## Accessibility

Every interactive control has an accessible name; form labels are buddies of their fields; focus is visible
(2 px accent outline); lists expose status as text ("confirmed, requires review"), not colour alone;
keyboard shortcuts cover navigation, search, add, save, move, delete, export and preview. Full screen-reader
testing has not been performed.

## Empty states and honesty

The dashboard shows only real counts; empty lists explain what to add. The sample workspace always shows
a banner. Scores are labelled as evidence alignment, never as selection probability.
