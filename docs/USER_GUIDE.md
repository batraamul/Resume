# User guide

Resume Intelligence Studio keeps **one master profile** of verified facts and builds every resume, bio-data,
CV and cover letter from it. You never retype facts per application, and nothing appears in a document
unless you entered it, confirmed it and cleared it for disclosure.

## 1. The two statuses on every fact

| Verification | Meaning |
|---|---|
| Awaiting confirmation | Imported or preliminary; **cannot be exported** until you confirm it. |
| Confirmed | You checked it is accurate. |
| Confirmed with evidence | You also hold the proof (office order, certificate, DOI…). |

| Disclosure | Meaning |
|---|---|
| Public | Already public; may appear anywhere, including redacted portfolios. |
| Approved for professional use | You checked it may appear in resumes you send. |
| Requires review | **Not exported** until you decide. Work records and all imported data start here. |
| Confidential | Never exported, never sent to an AI provider, replaced by a placeholder in cloud copies. |

Change them in the record editor, or select several records and use **Selected ▾** (confirm, classify,
duplicate, delete). Statements (bullets) inherit their parent's restrictions.

## 2. First steps

1. **Master Profile → Personal & contact**: name, title, contact details, online profiles, research metrics
   (with their source and date) and private particulars (used only when you tick them for a bio-data).
2. **Import…** an existing CV (DOCX, PDF, TXT), a spreadsheet (CSV with column mapping) or a profile JSON.
   You choose which candidate records to keep; duplicates are unticked. Everything arrives *Awaiting
   confirmation* and *Requires review* — check each item, correct it, then confirm.
3. Fill the sections: **Experience** (positions; add concurrent responsibilities and statements as *linked
   items*), **Education** (completed / ongoing / planned), **Research & Publications** (exact status —
   unpublished work is never described as published), **Skills** (your own proficiency), **Projects**
   (problem, approach, results, your contribution), **Leadership** (committees, awards, patents, talks,
   grants, peer review, supervision, conference organisation).
4. **Master Profile → Areas of expertise**: broad domains with a short narrative — shown as the
   "Areas of Expertise" table in graphical and executive resumes.
5. **Master Profile → Referees**: add referees and tick *agreed to be named*; until then they never appear.

The **Diary** (dashboard) shows completeness, items awaiting confirmation or review, chronology warnings,
possible duplicates, outdated resumes and upcoming deadlines. Double-click an item to open it.

## 3. Targets and vacancies

* **Career Targets**: create a target from one of the ten Defence & Intelligence presets or twelve
  organisation profiles. Targets change emphasis, ordering, summary choice and template — never facts.
* **Job Opportunities**: *New vacancy* (paste the notice) or *Import notice…* (PDF/DOCX/TXT). Notice text is
  data only; instructions inside it are ignored.
  * **Requirements** tab: extracted by transparent rules; correct categories, mark essential items, add what
    was missed, override a status with a note.
  * **Evidence & score** tab: each requirement shows *Supported by verified evidence*, *Supported, awaiting
    confirmation*, *Partially supported*, *Not found*, *Not applicable* or *Requires official verification*,
    with the records used. The 0–100 alignment score shows its components (35/25/15/10/10/5 by default;
    change weights in Settings). **It is not a probability of selection**, and eligibility (age, pay level,
    service conditions) is always left to the recruiting authority.
  * **Create tailored resume**, **Draft cover letter**, **Track this application**.

## 4. Resume Studio

Pick or create a **variant** (a named set of choices). Settings save automatically.

* **Mode** — content strategy: Professional, Defence & Intelligence technical, Scientific research,
  Academic CV, Government bio-data, ATS-optimised, One-page executive, Technical specialist,
  **Graphical career profile**, **Research portfolio**, **Project portfolio**.
* **Template** — visual layout (15). ATS-safe templates are single-column without tables or images.
* **Target / vacancy** — drive ordering and emphasis; a vacancy adds the "required vs possessed" table to
  bio-data.
* **Sections** — drag to reorder, untick to hide; **Contact details shown**; **Official particulars** (bio-data
  only); **Choose records…** to leave individual records out.
* **Preview** — the built-in engine is fast; *export engine* shows the exact pagination.
* **Content & claims** — select a statement → **Tailor wording for this resume…**: the suggestion is shown
  next to your original with every check (new numbers, stronger involvement, outcomes, qualifications…).
  Approved wording applies to this resume only; your profile is unchanged.
* **Checks** — review items, composition notes, quality checks, missing vacancy keywords, fit adjustments.
* **Export…** (Ctrl+E) — DOCX, PDF and/or TXT. Unconfirmed or unreviewed items open the review window, where
  you can confirm, approve, leave items out or open the record. Sensitive wording needs acknowledgement.
  Files are validated before success is reported, saved as a new version, and never overwrite older files.

### Graphical resumes

The three graphical templates (Graphical Career Profile, Research Showcase, Infographic Timeline) add:

* a framed or banner header with contact icons;
* an **Areas of Expertise** table;
* a **career timeline** chart: one bar per organisation (consecutive posts merged), height = years in post
  calculated from your recorded dates, with a coloured legend in text. Set *Short organisation name* and
  *One-line highlight* on each position for the best labels;
* **competency bars**: five-step bars from the proficiency you set on each skill, labelled as your own
  assessment. Unrated skills are listed as text, without bars;
* **Research at a Glance** tiles (journal articles, conference papers, manuscripts under review, patents,
  grants, talks, and citations / h-index / i10-index with their source) and a publications-by-year chart;
* **project cards** with Challenge, Approach, Outcome, My contribution, verified metrics and technologies.
  If a project has *approved external description*, only that text is shown.

Graphical resumes are for people to read. For online portals use the ATS mode and template.

## 5. Library, letters, tracker, exports

* **Resume Library** — variants, immutable versions (preview, compare two, re-export identically, delete),
  "may be outdated" warnings when source records changed; **Templates** tab to preview with the fictional
  sample, duplicate a template and edit fonts, colours and margins of your copy.
* **Cover Letters** — drafts from confirmed facts and the vacancy; edit, preview, export (validated).
* **Application Tracker** — status, deadlines, interview and follow-up dates, linked resume version and letter.
* **Documents & Exports** — every exported file with checksum and validation report; *Verify checksum*;
  *Create redacted portfolio* (Public only, or Public + Approved).

## 6. Backup, sync and settings

* **Backup & Restore** — back up now (optionally encrypted), save a copy elsewhere, verify, restore (your
  current data is saved first as *pre-restore*), automatic backups, integrity check, search-index rebuild,
  portable JSON, and **Recently deleted** (restore or delete permanently).
* **Synchronisation** — off by default. Choose a folder (e.g. Google Drive for desktop) or Google Drive
  directly; set a passphrase so everything is encrypted before upload; confidential records are replaced
  by placeholders unless you explicitly include them. Conflicts (changed on two devices) are shown side by
  side: keep this computer's, the other device's, or both. See GOOGLE_DRIVE_SETUP.md.
* **Settings & Security** — theme, text size, PDF engine and LibreOffice path, export folder and file-name
  pattern, score weights, credential store status, data folder, optional AI provider (see AI_PROVIDER.md),
  workspaces (including the fictional sample) and the glossary for engineering readers.

## 7. Keyboard

| Keys | Action |
|---|---|
| Ctrl+1 … Ctrl+9 | Diary, Master Profile, Experience, Studio, Opportunities, Library, Tracker, Backup, Settings |
| Ctrl+F | Search the whole profile |
| Ctrl+N | Add a record in the current section |
| Ctrl+S | Save the record being edited |
| Alt+↑ / Alt+↓ | Move the selected record |
| Delete | Move selected records to Recently deleted |
| Ctrl+E / F5 | Export / refresh preview in Resume Studio |

## 8. Responsibility

You decide what may be stored and disclosed under your employer's rules. Local storage and cloud copies do
not make sensitive official information permissible to keep or share. When in doubt, mark an item
*Requires review* or *Confidential*.
