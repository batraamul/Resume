# Developer Guide — how Resume Intelligence Studio works, and how to build an app like it

This guide explains the source code of Resume Intelligence Studio (RIS) from the ground up. It is written for
someone who knows a little programming — what a variable, a function and a loop are — but has never built a
desktop application. By the end you should be able to:

1. set up the project on your own computer and run it;
2. find your way around the code and know which file does what;
3. follow one button press all the way to a finished PDF;
4. make common changes (a new field, a new resume section, a new template, a new colour scheme);
5. understand how the installers, automatic builds and secure updates work; and
6. **build a smaller resume app of your own**, step by step, with code that is tested (Part 12).

You do not have to read it in one go. Parts 1–4 give the big picture; Parts 5–9 are a tour of each layer;
Parts 10–12 are hands-on.

> **Tip.** Keep the code open next to this guide. Every name written like `this` is a real file, class or
> function you can search for (in VS Code: *Ctrl+Shift+F* / *Cmd+Shift+F*).

---

## Contents

1. [What the application does](#1-what-the-application-does)
2. [Set up your computer](#2-set-up-your-computer)
3. [Python ideas you will meet](#3-python-ideas-you-will-meet)
4. [The big picture: layers](#4-the-big-picture-layers)
5. [A tour of the folders](#5-a-tour-of-the-folders)
6. [Layer by layer](#6-layer-by-layer)
7. [Follow one click: from "Export" to a PDF](#7-follow-one-click-from-export-to-a-pdf)
8. [Honesty and safety rules built into the code](#8-honesty-and-safety-rules-built-into-the-code)
9. [Testing](#9-testing)
10. [Installers, automatic builds, releases and updates](#10-installers-automatic-builds-releases-and-updates)
11. [Recipes: common changes](#11-recipes-common-changes)
12. [Build a similar app from scratch: "Resume Lite"](#12-build-a-similar-app-from-scratch-resume-lite)
13. [When something goes wrong](#13-when-something-goes-wrong)
14. [Glossary](#14-glossary)
15. [Further reading](#15-further-reading)

---

## 1. What the application does

RIS keeps **one master profile** — your positions, education, training, publications, projects, skills and
so on — and produces **many documents** from it: resumes in different styles, government bio-data, cover
letters, interview packs and questionnaires. The key idea is:

```
   facts you enter once  ──►  choose what to show  ──►  lay it out  ──►  Word / PDF / text files
   (the master profile)       (a "variant")             (a template)     (checked before saving)
```

Everything happens on your own computer. Data lives in a single **SQLite** database file per workspace;
nothing is sent anywhere unless you turn on Google Drive sync, the optional AI provider, or update checks.

The program is written in **Python** and uses these libraries (the exact versions are in `requirements.txt`):

| Library | What it is used for |
|---|---|
| **PySide6** (Qt for Python) | The windows, buttons, forms and lists |
| **Pydantic** | Describing and validating data ("a start date must look like 2019-04") |
| **sqlite3** (built into Python) | Storing records in a database file |
| **python-docx** | Writing Word (.docx) files |
| **ReportLab** | Writing PDF files |
| **pypdf** | Reading PDFs back to check them |
| **Pillow** | Drawing charts (career timelines, skill bars) as images |
| **cryptography** | Encrypted backups and checking update signatures |
| **keyring** | Storing secrets (tokens, API keys) in the operating system's password store |
| **certifi** | Up-to-date list of trusted web certificates for update checks |

---

## 2. Set up your computer

You need **Python 3.11, 3.12 or 3.13** and **Git**.

* Windows: install Python from [python.org](https://www.python.org/downloads/) (tick *Add python.exe to PATH*)
  and Git from [git-scm.com](https://git-scm.com/).
* macOS: install Python from python.org (or `brew install python@3.12`); Git comes with the Xcode command-line
  tools (`xcode-select --install`).
* Linux (Ubuntu/Debian): `sudo apt install python3 python3-venv git libxcb-cursor0`.

Then, in a terminal:

```bash
git clone https://github.com/batraamul/Resume.git
cd Resume

python3 -m venv .venv                 # Windows: py -3.12 -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
python -m pip install -r requirements-dev.txt

python run_application.py --sample    # opens the app with the fictional sample profile
```

What these commands do:

* `git clone` downloads the code.
* `python -m venv .venv` creates a **virtual environment**: a private folder of libraries for this project,
  so it cannot clash with other Python projects. You "activate" it in each new terminal.
* `pip install -r requirements-dev.txt` installs the libraries listed in that file (it includes
  `requirements.txt` plus testing and packaging tools).
* `run_application.py` starts the program.

Other useful commands:

```bash
python run_application.py --version             # print the version
python run_application.py --selftest            # check that everything the app needs works
python -m ris.cli templates                     # list resume templates without opening a window
python -m ris.cli sample-export --out examples  # make sample documents from the command line
python -m pytest                                # run all automatic tests
ruff check ris tests scripts docs/tutorial      # check code style
```

Use a good editor: **VS Code** with the Python extension, or **PyCharm Community**. Both let you jump to the
definition of a function (F12 / Ctrl+B), which is the fastest way to learn a codebase.

---

## 3. Python ideas you will meet

You can skim this part now and come back to it when you see something unfamiliar.

**Modules and packages.** Every `.py` file is a *module*. A folder of modules is a *package*. `ris/` is the
application's package, so `from ris.storage.database import Database` means "open `ris/storage/database.py`
and take `Database` from it".

**Type hints.** `def find(self, record_id: str) -> Record | None:` says the function takes a string and
returns a `Record` or `None`. Python does not enforce hints at run time; they document the code and let the
editor and tools catch mistakes.

**Classes and objects.** A *class* is a blueprint; an *object* is one thing built from it. `self` is the
object a method was called on.

**Dataclasses.** `@dataclass` writes the boring parts of a class (constructor, comparison) for you:

```python
from dataclasses import dataclass

@dataclass
class Check:
    name: str
    status: str
    message: str
```

**Pydantic models.** Like dataclasses, but they *validate* data. If a field must be a number and you give it
`"abc"`, Pydantic raises a `ValidationError` with a readable message. RIS describes every kind of record
(position, publication, training …) as a Pydantic model in `ris/domain/models.py`.

**Enums.** A fixed list of allowed values, for example `Verification.UNCONFIRMED`, `CONFIRMED`, `EVIDENCED`
(in `ris/domain/enums.py`). They stop typos such as `"confimed"`.

**Context managers (`with`).** `with db.transaction():` runs a block and guarantees a clean-up step
afterwards — here, *commit* if everything worked or *roll back* if anything failed.

**Decorators.** Lines starting with `@` wrap a function: `@staticmethod`, `@property`,
`@pytest.mark.req("UPD-01")`.

**Exceptions.** Errors are *raised* and *caught*. RIS has its own family in `ris/errors.py` (`RISError`,
`NotFound`, `ExportError` …). Each carries a `user_message` (shown to the user) and a `detail` (for logs).

**Callbacks and lambdas.** A function can be passed to another function and called later. `lambda x: x + 1`
is a tiny unnamed function. The interface uses this everywhere: "when the button is clicked, call this".

**Signals and slots (Qt).** Qt widgets *emit signals* (`clicked`, `textChanged`) and you *connect* them to
*slots* (any function): `button.clicked.connect(self.save)`.

**`pathlib.Path`.** A file path object that works on Windows, macOS and Linux:
`Path.home() / "Documents" / "resume.pdf"`.

---

## 4. The big picture: layers

The code is split into **layers**. Each layer only uses the layers *below* it. This keeps the important
logic independent of the user interface, so it can be tested without opening a window (and reused by the
command line tool `ris/cli.py`).

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ UI  (ris/ui)            windows, pages, forms, dialogs, theme, update dialog  │
├──────────────────────────────────────────────────────────────────────────────┤
│ Rendering (ris/rendering)  templates → layout → DOCX / PDF / text → validation│
│ Composition (ris/composition)  profile + variant → ResumeDocument ("IR")      │
│ Intelligence (ris/intelligence)  vacancy analysis, matching, ATS, interview,  │
│                                  portal kit, disclosure scan, rewriting       │
│ Services (ris/services)   snapshots, variants, import/export, chronology      │
│ Backup · Sync · AI · Update (ris/backup, ris/sync, ris/ai, ris/update)        │
├──────────────────────────────────────────────────────────────────────────────┤
│ Storage (ris/storage)     SQLite database, migrations, records repository     │
├──────────────────────────────────────────────────────────────────────────────┤
│ Domain (ris/domain)       what a record is: enums, Pydantic models, registry  │
└──────────────────────────────────────────────────────────────────────────────┘
        shared helpers: ris/errors.py, ris/paths.py, ris/config.py, ris/util.py
```

The rule "the UI never writes SQL" is checked by a test (`MNT-03`). If you need data in a page, ask a
service or the repository.

---

## 5. A tour of the folders

| Path | What is inside |
|---|---|
| `run_application.py` | The file you run. It calls `ris.app.main()`. |
| `ris/__init__.py` | The version number (`__version__`) and the application name. |
| `ris/app.py` | Reads command-line options (`--sample`, `--selftest`, `--report` …) and starts the interface. |
| `ris/cli.py` | Command-line tools that work without a window (export, backup, restore …). |
| `ris/domain/` | `enums.py` (allowed values), `models.py` (one Pydantic model per record kind), `registry.py` (which kinds exist and their rules), `dates.py` (partial dates like "2019" or "2019-04"). |
| `ris/storage/` | `database.py` (SQLite connection and transactions), `migrations.py` (upgrading the database), `repository.py` (create/read/update/delete records), `workspace.py` (a folder holding one database), `settings.py`. |
| `ris/services/` | `profile.py` (a read-only *snapshot* of all records), `variants.py` (saved resume versions), `portable.py` (JSON import/export), `importers.py`, `chronology.py`, `completeness.py`, `duplicates.py`. |
| `ris/intelligence/` | Vacancy analysis (`vacancy.py`, `analysis.py`), skill vocabulary (`taxonomy.py`), matching evidence to requirements (`matching.py`, `scoring.py`, `relevance.py`), `ats.py`, `interview.py`, `portal_kit.py`, `disclosure.py` (finds sensitive text), `claims.py` and `rewriting.py`. |
| `ris/composition/` | `composer.py` (chooses and orders content), `modes.py` (resume styles and their sections), `ir.py` (the in-between document format), `cover_letter.py`, `portfolio.py`. |
| `ris/rendering/` | `specs.py` (template settings), `layout.py` (turns the document into positioned blocks), `docx_renderer.py`, `pdf_renderer.py`, `graphics.py` (charts), `validation.py` (reads the files back), `export.py` (the whole export process). |
| `ris/ui/` | `application.py` (starts Qt), `main_window.py`, `context.py` (shared state), `pages/` (one file per page), `widgets/` (reusable pieces such as the record form), `theme.py` and `appearance.py` (colours, fonts, layout), `template_designer.py`, `updates.py`. |
| `ris/update/` | Secure automatic updates: `manifest.py` (signed release description), `client.py` (download from GitHub), `installer.py` (install per platform), `keys.py` (public key). |
| `ris/backup/`, `ris/sync/`, `ris/ai/`, `ris/security/` | Encrypted backups, Google Drive sync, the optional AI provider, secret storage and private temporary folders. |
| `migrations/` | Numbered SQL files that create and upgrade the database. |
| `templates/` | One JSON file per resume template. |
| `config/` | Data files: skill taxonomy, glossary, career presets, interview questions, job portals, recruiters. |
| `assets/` | Fonts and icons. |
| `sample_data/` | The fictional sample profile. |
| `tests/` | Automatic tests, grouped into `unit`, `integration`, `documents`, `gui`, `security`, `sync`, `e2e`. |
| `scripts/` | Helper programs: release ZIP, requirement tracing, update manifest signing, CI annotations. |
| `packaging/` | Installer recipes: PyInstaller spec, Windows Inno Setup, macOS disk image, Linux packages. |
| `.github/workflows/` | Automatic builds on GitHub (`ci.yml` for every change, `release.yml` for releases). |
| `docs/` | All documentation, including this guide and the tutorial code in `docs/tutorial/resume_lite/`. |

---

## 6. Layer by layer

### 6.1 Domain — what a record is

Everything you enter is a **record**. A record has a **kind** (`RecordKind.POSITION`, `RecordKind.TRAINING`,
`RecordKind.PUBLICATION` …) and **data** described by a Pydantic model.

Here is part of the model for a position (`ris/domain/models.py`):

```python
class Position(_Dated):
    designation: str = F("", "Official designation", group="Role")
    organisation: str = F("", "Organisation", group="Role")
    start: PDate = F("", "Start", widget="date", group="Dates")
    end: PDate = F("", "End", widget="date", group="Dates")
    is_current: bool = F(False, "Current position", widget="bool", group="Dates")
    tools: Tags = F([], "Tools & technologies", widget="tags", group="Description")
    pay_level: str = F("", "Pay level", group="Government particulars", private=True)
```

`F()` is a small helper (defined in the same file) that creates a Pydantic field **and** stores interface
hints: the label, which kind of input box to use (`widget="date"`), which group of the form it belongs to,
and whether it is private (never printed in documents). Because the form is built from these hints
(see 6.7), adding a field to the model automatically adds it to the form.

`ris/domain/registry.py` lists every kind in `REGISTRY` with its rules:

```python
RecordKind.TRAINING: KindInfo(RecordKind.TRAINING, m.Training,
                              default_confidentiality=Confidentiality.APPROVED),
RecordKind.BULLET: KindInfo(RecordKind.BULLET, m.Bullet,
                            parents=(RecordKind.POSITION, RecordKind.ASSIGNMENT, RecordKind.PROJECT,
                                     RecordKind.ACTIVITY)),
```

* `parents` — which kinds a record may belong to (an achievement bullet belongs to a position or project).
* `singleton` — only one may exist (personal details).
* `is_fact` — facts are things about you that need your confirmation; non-facts are working items such as
  resume variants, vacancies or interview answers.
* `default_confidentiality` — the starting classification.

Two labels on every record keep documents honest:

| Label | Values | Meaning |
|---|---|---|
| **Verification** | unconfirmed, confirmed, evidenced | Has the user confirmed this fact? Imported or sample items start unconfirmed. |
| **Confidentiality** | public, approved, review, confidential | May it appear in an exported document? *Confidential* never does; *review* blocks export until reviewed. |

`ris/domain/dates.py` handles **partial dates** ("2019", "2019-04", "2019-04-15") because resumes often only
know the year or month.

### 6.2 Storage — the database

**SQLite** is a database in a single file. RIS uses one file (`ris.db`) per **workspace** (a folder chosen
in `ris/storage/workspace.py`). The tables are created by the numbered SQL files in `migrations/`.

The main table is `records` (see `migrations/0001_initial.sql`):

| Column | Meaning |
|---|---|
| `id` | A unique identifier |
| `kind` | The record kind, e.g. `position` |
| `parent_id` | The record it belongs to (for bullets, assignments …) |
| `verification`, `confidentiality`, `origin` | The labels described above; where it came from |
| `data` | The Pydantic model stored as JSON text |
| `revision`, `checksum`, `updated_at` | Change tracking (used by sync and saved resume versions) |
| `deleted` | Soft delete: deleted records go to a recycle bin first |

Storing the data as JSON means a new field does not need a database change — only the Pydantic model
changes. There is also a full-text search table (`records_fts`), and tables for saved resume versions,
exports, settings and an audit log.

The important classes:

* **`Database`** (`database.py`) wraps the connection. `db.transaction()` makes several changes *all or
  nothing*; `db.query(...)` returns rows. A lock makes it safe to use from background threads.
* **`migrate(db)`** (`migrations.py`) applies any SQL files the database has not seen yet, in order, inside a
  transaction. Before it runs, `Workspace.open()` makes a *pre-upgrade* backup, and cancels the upgrade if
  that backup cannot be made. **Never edit a released migration — add a new numbered
  file** (e.g. `0002_more_document_kinds.sql`).
* **`RecordRepository`** (`repository.py`) is the only code that reads and writes records:
  `create(kind, data, parent_id=...)`, `get(id)`, `find(id)`, `list(kind)`, `update(id, data)`,
  `patch(id, **fields)`, `delete(id)` (soft), `undelete(id)`, `search(text)`. Every write validates the data
  with the kind's Pydantic model, updates the revision and checksum, the search index and the audit log, and
  tells *listeners* (the interface) what changed.
* **`Record`** is what you get back: `rec.id`, `rec.kind`, `rec.data` (the Pydantic object), `rec.title`,
  `rec.verification`, `rec.confidentiality` …

```python
repo = workspace.repo
rec = repo.create(RecordKind.TRAINING, {"title": "Leadership Programme", "provider": "Example Institute",
                                        "training_type": "training_programme", "start": "2023-02"})
print(rec.title)            # "Leadership Programme"
repo.patch(rec.id, grade="A")
```

### 6.3 Services — working with the whole profile

**`ProfileSnapshot`** (`ris/services/profile.py`) loads *all* records once into memory, so the composer and the
intelligence code can look things up quickly without touching the database again:

```python
snap = ProfileService(repo).snapshot()
snap.of(RecordKind.POSITION)          # all positions
snap.kids(position_id)                # its bullets and assignments
snap.personal_data                    # name, email, links …
snap.effective_confidentiality(rec)   # a bullet inherits "confidential" from its project
```

Other services: `VariantService` saves and compares exported versions of a resume; `portable.py` exports
and imports the whole profile as JSON; `chronology.py` finds gaps and overlaps in dates; `completeness.py`
works out what is missing; `duplicates.py` spots near-duplicates when importing.

### 6.4 Intelligence — analysis without inventing anything

These modules read the profile and *suggest*; they never add facts.

* **Vacancy analysis** — `extract_requirements()` (`vacancy.py`) splits a job notice into requirements
  (essential/desirable, qualification/experience/skill); `analyse()` (`analysis.py`) matches them with your
  evidence using `EvidenceMatcher` (`matching.py`) and the skill vocabulary in `config/taxonomy.json`, and
  scores the fit (`scoring.py`).
* **ATS** — `check_quality()` and `ats_readiness()` (`ats.py`) check a composed resume against applicant
  tracking system rules (single column, standard headings, common fonts, no images for core content …).
  The rules and their sources are listed in `docs/RESEARCH_FINDINGS.md`.
* **Interview preparation** — `interview.py` loads the question bank (`config/interview_questions.json`),
  personalises questions from your records (`personalised_questions()`), checks STAR stories
  (`analyse_story()`: Situation/Task/Action/Result shares and spoken length), checks a personal
  questionnaire for consistency with your profile (`check_questionnaire()`), and builds interview packs.
* **Job portals** — `portal_kit.py` builds LinkedIn, Naukri and Indeed profile text from *confirmed,
  exportable* facts only (`build_kit()`), counts characters against each portal's limits
  (`config/job_portals.json`), and checks an exported file before upload (`check_file()`).
* **Disclosure** — `scan_text()` and `scan_document()` (`disclosure.py`) look for things that should not leave
  your computer: identity numbers (Aadhaar, PAN, passport, bank account) block the export; classification
  markings, network details, coordinates, radio frequencies and internal file references are flagged for
  review.
* **Rewriting and claims** — `rewrite_bullet()` suggests clearer wording; `validate_claim()` (`claims.py`)
  rejects a rewrite that adds numbers, names or achievements that were not in the original.

### 6.5 Composition — choosing what goes in a resume

A **variant** (a `Variant` record) is one resume: its mode (style), length, template, the vacancy it targets,
sections to hide, items to include or exclude.

**`ResumeComposer`** (`ris/composition/composer.py`) turns *snapshot + variant* into a **`ResumeDocument`**:

```python
doc = ResumeComposer(ctx).compose()
```

`compose()`:

1. works out the order of sections from the mode (`modes.py`), your own order and the vacancy's emphasis
   (`resolve_order()` in `ordering.py`);
2. calls `build_section(key)` for each section — a dictionary maps keys such as `"experience"`,
   `"certifications"` or `"publications"` to methods such as `section_experience()`;
3. each section method picks eligible records (`eligible()` skips confidential, excluded or unconfirmed
   items according to the rules), sorts them, applies length budgets, and creates `IRSection` /
   `IREntry` / `IRBullet` objects;
4. records which source records (and their revisions) were used, and collects warnings.

`ResumeDocument` and its parts are defined in `ir.py`. **IR** means *intermediate representation*: a
description of the content that knows nothing about fonts or pages. This separation is the most important
design decision in the app:

```
 composer (what to say)  ──►  ResumeDocument  ──►  layout + renderers (how it looks)
```

Because of it, one composed document can be printed with any template, saved as a version and re-exported
later exactly as it was, checked for confidential text, and compared with the exported files.

### 6.6 Rendering — from document to files

**Templates** are JSON files in `templates/` validated by **`TemplateSpec`** (`specs.py`): page margins,
fonts and sizes, colours, header style, heading style, entry style, columns, graphics, photo rules. User
templates made in the template designer are saved in the data folder by `TemplateLibrary`.

The path from document to files:

```
ResumeDocument + TemplateSpec
        │  plan_layout()            (layout.py, class LayoutPlanner)
        ▼
LayoutDocument  — paragraphs, runs, tables, columns, images, footer (blocks.py)
        │
        ├── render_docx()   → .docx   (docx_renderer.py, python-docx)
        ├── render_pdf()    → .pdf    (pdf_renderer.py, ReportLab)   or LibreOffice converts the .docx
        └── render_text()   → .txt    (text_export.py)
        │
        ▼
validate_outputs()  (validation.py) reads every file back
```

* **`LayoutPlanner`** decides *how* each part looks: the header, headings, entries with dates on the left or
  right, skill groups, publication lists, two-column layouts, charts (`graphics.py` draws timelines and
  rating bars with Pillow).
* **Both renderers draw the same `LayoutDocument`**, so Word and PDF match.
* **`validate_outputs()`** extracts the text from the DOCX and PDF and checks that every expected piece of
  content is there, that no placeholder text (`None`, `{name}`, `lorem`) leaked, that no confidential phrase
  appears, that the page count is right and dates are in order. **If validation fails, nothing is saved.**

**`ExportService`** (`export.py`) runs the whole process: compose → review → fit to the page limit → render →
validate → move the files into place → save a version → log the export.

### 6.7 UI — the windows

The interface uses **Qt** through **PySide6**. Qt programs follow this pattern:

```python
app = QApplication(sys.argv)     # one per program
window = MainWindow(...)
window.show()
app.exec()                       # the "event loop": waits for clicks and key presses and reacts
```

Important pieces:

* **`run_gui()`** (`ris/ui/application.py`) creates the application, loads fonts, applies the theme, shows the
  first-run window and opens the main window.
* **`AppContext`** (`context.py`) is shared by all pages. It holds the open workspace, the template library and
  configuration, and offers `ctx.repo`, `ctx.snapshot()`, `ctx.export_service()` and so on. It also has
  **signals** such as `data_changed` (emitted after records change, so pages can refresh) and `navigate`.
* **`MainWindow`** (`main_window.py`) builds the navigation list (from `NAV_SECTIONS` in `ris/strings.py`) and a
  stack of pages (`_build_pages()`), the top bar, and the update button.
* **Pages** (`ris/ui/pages/`) — one class per page: `StudioPage` (resume studio), `InterviewPage`,
  `PortalsPage`, `SettingsPage` …. The profile pages (experience, education, training …) are all the same
  generic page configured by `SECTION_PAGES` in `pages/profile.py`.
* **`RecordForm`** (`widgets/form.py`) builds an input form *from the Pydantic model*: it reads
  `field_metas(model)` (from `registry.py`) and creates a line edit, text box, date box, drop-down or tag
  editor for each field, grouped into sections. **`CollectionWidget`** (`widgets/records.py`) shows a list of
  records with an editor next to it (or below it, in the stacked layout).
* **Background work** — long jobs (exporting, previews, sync) must not freeze the window. `run_task(fn,
  on_done, on_error)` (`workers.py`) runs `fn` in a thread pool and calls `on_done(result)` back on the
  interface thread. Tests pass `synchronous=True` to run it immediately.
* **Theme and customisation** — `theme.py` defines colour presets (each with a light and a dark palette that
  meet WCAG AA contrast), the `Appearance` settings (fonts, text size, density, corner radius, navigation
  style, editor layout, start page) and `stylesheet()`, which turns them into a Qt style sheet (Qt's version
  of CSS). `appearance.py` is the dialog that edits them, and `template_designer.py` edits resume templates
  with a live preview and readability/ATS checks.

### 6.8 Backup, sync, AI and security

* **Backups** (`ris/backup/`) copy the database with SQLite's online backup, optionally **encrypted** with a
  passphrase (`crypto.py`: scrypt to derive a key, AES-GCM to encrypt). `integrity.py` checks a backup before
  restoring it, and a restore always keeps a copy of the current data first.
* **Sync** (`ris/sync/`) exchanges records with a Google Drive app folder. `SyncEngine` compares revisions and
  checksums and shows conflicts instead of overwriting.
* **AI** (`ris/ai/`) is optional and off by default. `payload.py` builds the smallest possible request (one
  statement and its own facts), shows it to you first, and refuses confidential, review-pending or
  unconfirmed records; the master profile is never sent.
* **Security helpers** — `SecretStore` (`security/secrets.py`) keeps tokens in the operating system's
  keyring; `private_tempdir()` (`security/tempfiles.py`) creates temporary folders only you can read and
  deletes them afterwards; `paths.py` restricts file permissions on the data folder.

### 6.9 Updates

`ris/update/` checks GitHub Releases for a newer version. The check downloads two small files —
`ris-update.json` (the version, release notes, and for each installer its address, size and SHA-256 checksum)
and `ris-update.json.sig` (an **Ed25519 digital signature** of that file). The app contains only the
*public* key (`keys.py`); only the holder of the *private* key can produce a signature it accepts. So even if
someone could change files on the download server, the app would refuse them. Details are in Part 10 and in
`docs/UPDATES.md`.

---

## 7. Follow one click: from "Export" to a PDF

This trace shows how the layers cooperate. Open each file as you read.

1. **The button.** In `ris/ui/pages/studio.py`, the *Export* button is connected to `StudioPage.export()`.
   It saves pending edits (`_flush_save()`), works out a default file name, and opens `ExportDialog` where you
   choose formats and a folder. `dlg.options()` returns an `ExportOptions` object.
2. **Run in the background.** `_run_export()` disables the button and calls
   `run_task(lambda: svc.export_variant(variant_id, opts), on_done=_export_done, on_error=...)`.
3. **Load and compose.** `ExportService.export_variant()` (`ris/rendering/export.py`) finds the variant, takes a
   fresh `ProfileSnapshot`, and calls `compose()`, which loads the template (`TemplateLibrary.get()`), runs the
   vacancy analysis if a vacancy is linked, builds a `ComposeContext`, and calls
   `ResumeComposer(ctx).compose()` → a `ResumeDocument`.
4. **Review gate.** `review()` lists every used record that is unconfirmed, needs a disclosure review or is
   confidential, plus anything the disclosure scanner found. If there are blocking items, the export stops
   and returns them; the studio shows `ReviewDialog` so you can confirm or reclassify items, then tries again.
5. **Fit to pages.** For one- or two-page resumes, `fit()` renders, counts pages and trims the least relevant
   items until it fits (each trim is recorded in `doc.trimmed`).
6. **Render.** `_render_and_finish()` works in a private temporary folder: `plan_layout(doc, spec)` →
   `render_docx()`; then either LibreOffice converts the DOCX to PDF (if installed and selected) or
   `PdfRenderer` draws it; and `render_text()` writes the plain-text version.
7. **Validate.** `validate_outputs()` reads the files back. `check_quality()` adds ATS and layout advice. If
   validation fails, the method returns *"Export stopped … Nothing was saved."*
8. **Finish.** The files are moved to the export folder with unique names, a version of the variant is saved
   (`VariantService.save_version()`), and each file is logged in the `exports` table with its checksum.
9. **Back in the window.** `_export_done(…)` runs on the interface thread and shows the result: the files,
   warnings, and the ATS/quality findings.

---

## 8. Honesty and safety rules built into the code

The application is meant for recruitment where false statements have serious consequences, so several
rules are enforced by code, not just by advice:

| Rule | Where it is enforced |
|---|---|
| Nothing is invented: suggestions only rephrase what you wrote. | `claims.py` (`validate_claim()` rejects new numbers, names and achievements); `rewriting.py` marks missing metrics as *questions*, not text. |
| Unconfirmed facts are not exported without review. | `ExportService.review()`; imported and sample records start `unconfirmed`. |
| Confidential records never appear in documents. | `ResumeComposer.eligible()`, then again in `review()` and `validate_outputs()` (defence in depth). |
| Private fields (pay level, notes …) are never printed. | `F(..., private=True)` and `private_fields()` in `registry.py`. |
| Planned or ongoing qualifications are never shown as completed. | Model validators and the composer's wording. |
| Generated files are checked before they are saved. | `validate_outputs()`; failure means nothing is written. |
| Your data is not overwritten silently. | Soft delete, pre-upgrade copies, backup before restore, sync conflicts shown to you. |
| Updates cannot be faked. | Signed manifest and checksums (`ris/update/`). |
| No secrets in the code. | Secrets go to the keyring; tests and `scripts/make_release.py` scan for keys and personal data. |

When you add features, keep to these rules: **suggest, never assert**; **show the user what will leave the
computer**; **stop rather than produce a wrong file**.

---

## 9. Testing

Automatic tests are small programs that use the app's code and check the result. They run with **pytest**:

```bash
python -m pytest                                   # everything
python -m pytest tests/unit                        # one folder
python -m pytest tests/unit/test_composer.py -k training   # tests whose names contain "training"
python -m pytest -x -q                             # stop at the first failure, short output
```

On Linux without a screen, or in automatic builds, set `QT_QPA_PLATFORM=offscreen` so Qt draws windows in
memory.

A typical test:

```python
@pytest.mark.req("PRF-23")
def test_training_model_validation():
    t = Training(title="X", end="2022-03", valid_until="2025-03", duration_hours=40)
    assert t.display_title() == "X"
    with pytest.raises(ValueError):                     # expiry before completion is rejected
        Training(title="X", end="2022-03", valid_until="2021-01")
    with pytest.raises(ValueError):                     # end before start is rejected
        Training(title="X", start="2022-05", end="2022-01")
```

(from `tests/unit/test_training_interview_portals.py`). `assert` checks a condition; `pytest.raises` checks
that an error happens.

* *Fixtures* are helpers that pytest passes to a test by the parameter name: `tmp_path` is a fresh temporary
  folder for each test, `repo` and `sample_ws` (from `tests/conftest.py`) are a new empty profile and a copy of
  the fictional sample, so tests never touch your real data.
* `qtbot` (from **pytest-qt**) creates and drives widgets in GUI tests (`tests/gui/test_gui.py`).
* `@pytest.mark.req("PRF-23")` links the test to a requirement in `docs/requirements.toml`.
  Each test run records which requirements passed (`build/test-results/requirements.json`);
  `python scripts/trace_requirements.py` then writes `docs/REQUIREMENTS.md`, showing which requirements have
  passing evidence.
* `tests/conftest.py` sets safe defaults for every test (no keyring, no update checks, separate data and
  configuration folders).

The test folders: `unit` (single functions and classes), `integration` (several parts with a real database),
`documents` (every template renders and validates), `gui` (pages and dialogs), `security` (privacy, release
hygiene, no secrets), `sync`, and `e2e` (a full user workflow).

**Write a test whenever you fix a bug** — first a test that fails because of the bug, then the fix.

---

## 10. Installers, automatic builds, releases and updates

### 10.1 From Python files to an installable program

Users should not need Python. **PyInstaller** collects the Python interpreter, the libraries and the app into
one folder with a normal program file. The recipe is `packaging/ris.spec`:

```bash
pyinstaller packaging/ris.spec --noconfirm      # result: dist/ResumeIntelligenceStudio/
dist/ResumeIntelligenceStudio/ResumeIntelligenceStudio --selftest
```

PyInstaller cannot cross-compile: Windows builds must be made on Windows, macOS builds on a Mac, Linux builds
on Linux. That is why the builds run on GitHub's computers (next section). The folder is then packaged:

| System | Script | Result |
|---|---|---|
| Windows | `packaging/windows/ris.iss` (Inno Setup) | `…-windows-x64-setup.exe` — per-user installer, no administrator rights; plus a portable zip |
| macOS | `packaging/macos/make_dmg.sh` | `…-macos-arm64.dmg` — drag the app to Applications |
| Linux | `packaging/linux/make_packages.sh` | `…-linux-x86_64.tar.gz` and a `.deb` package |

### 10.2 GitHub Actions: automatic builds

**GitHub Actions** runs scripts on GitHub's computers when something happens in the repository. The scripts
are YAML files in `.github/workflows/`:

* **`ci.yml`** runs on every push and pull request: install the dependencies, `ruff check`, the whole test
  suite and `--selftest` on Windows, macOS and Linux (Python 3.11–3.13). A red cross on GitHub means
  something broke.
* **`release.yml`** runs when a version tag such as `v1.2.0` is pushed. A *matrix* starts three machines
  (Windows, macOS, Linux); each runs the tests, builds with PyInstaller, runs the frozen program's self-test
  and packages it. A final *publish* job collects all files, writes the update manifest, signs it, records
  build provenance and creates the GitHub Release.

A workflow step looks like this:

```yaml
- name: Run tests
  run: python -m pytest -q
```

### 10.3 Versions and releases

Versions follow **semantic versioning** — `MAJOR.MINOR.PATCH` (1.1.0): increase PATCH for fixes, MINOR for
new features, MAJOR for incompatible changes. A version like `1.3.0-beta.1` is a *pre-release*, offered only to
users on the beta channel. The steps for maintainers are in `docs/RELEASING.md`.

### 10.4 How the secure update works

```
 maintainer pushes tag v1.2.0
        │
        ▼
 release.yml builds installers ──► release_manifest.py build   (ris-update.json: version, notes,
        │                                                       file URLs, sizes, SHA-256)
        │                         release_manifest.py sign     (ris-update.json.sig with the PRIVATE key
        ▼                                                       from the RIS_UPDATE_SIGNING_KEY secret)
 GitHub Release with installers + ris-update.json + .sig
        │
        ▼
 the app (UpdateClient.check)
   1. asks api.github.com for the latest release (HTTPS, GitHub hosts only)
   2. downloads ris-update.json and .sig
   3. verify_manifest(): signature valid for the embedded PUBLIC key? same repository? URLs inside
      this release's download folder? version newer than mine?
   4. shows the release notes — the user chooses "Download and install"
   5. UpdateClient.download(): streams the installer, stops if larger than the signed size,
      compares SHA-256; deletes it on any mismatch
   6. plan_install() / run_plan(): runs the right installer for this system and restarts the app
```

**Digital signatures in one paragraph.** A key pair has a *private* key (secret) and a *public* key (shared).
Signing a file with the private key produces a short signature. Anyone with the public key can check that the
signature matches *exactly these bytes* — change one character and the check fails — but cannot create a new
valid signature. RIS uses **Ed25519**, a modern, fast signature scheme, via the `cryptography` library.

**Checksums in one paragraph.** SHA-256 turns any file into a 64-character fingerprint. If even one byte of the
download differs, the fingerprint differs. Because the expected fingerprint is inside the signed manifest, the
installer is protected by the signature too.

---

## 11. Recipes: common changes

After every change: run `ruff check ris tests scripts docs/tutorial` and the relevant tests, then the full suite.

### Add a field to an existing record kind

Example: a "sponsoring department" for training records.

1. In `ris/domain/models.py`, add to `class Training`:
   ```python
   sponsor_department: str = F("", "Sponsoring department", group="Provider")
   ```
2. That is enough for it to appear in the form and be saved (data is stored as JSON).
3. To print it, use it in `ResumeComposer._training_entry()` (`composer.py`).
4. Add a test in `tests/unit/test_training_interview_portals.py`.
5. Run `python scripts/gen_data_dictionary.py` to refresh `docs/DATA_MODEL.md`.

### Add a new record kind

1. Add a value to `RecordKind` (and a label in `LABELS`) in `ris/domain/enums.py`; add it to `FACT_KINDS` if it
   is a fact about the user.
2. Create its Pydantic model in `models.py` (inherit from `RecordData`, or `_Dated` if it has dates; give it a
   `display_title()` method).
3. Register it in `REGISTRY` (`registry.py`).
4. Show it in the interface: add an entry to `SECTION_PAGES` (`ris/ui/pages/profile.py`), to `NAV_SECTIONS`
   (`ris/strings.py`, with an icon in `NAV_ICONS` in `theme.py`) and to `PAGE_FOR_KIND` (`main_window.py`).
5. Add it to `KIND_ORDER` in `ris/services/portable.py` so JSON export/import includes it.
6. If the database has a `CHECK` constraint listing allowed values for something you add, write a new migration.

### Add a resume section

1. Add the key and title to `SECTION_TITLES` in `ris/composition/modes.py`, and put the key in the `order`
   of the modes that should show it.
2. Write a method `section_mykey(self, key)` in `ResumeComposer` that returns an `IRSection` (or `None`).
3. Add `"mykey": self.section_mykey` to the dictionary in `build_section()`.
4. Test: compose a variant and assert the section and its text appear; the `documents` tests will render it
   with every template.

### Add a resume template

1. Copy a file in `templates/` (for example `modern_professional.json`) and change `id`, `name`,
   `description`, fonts, colours and styles. The allowed values are the fields of `TemplateSpec` in
   `ris/rendering/specs.py`.
2. Set `"ats_safe": true` only if the template is single-column without tables or graphics.
3. Run `python -m pytest tests/documents` — every template is rendered to DOCX and PDF and validated.
   (Users can do the same without code in *Resume Library → Design…*.)

### Add an interview question or tip

Add an object to `questions` in `config/interview_questions.json`:

```json
{"category": "technical", "text": "How do you validate a sensor model?", "hint": "Describe data, method and limits."}
```

Valid categories are the values of `QuestionCategory` in `enums.py`. Add a source to `sources` if the
question comes from published guidance.

### Add a colour preset

Add an entry to `PRESETS` in `ris/ui/theme.py` with a light and a dark palette (use `_variant()` to change only
some colours). `tests/unit/test_appearance.py` checks every text/background pair of every preset meets WCAG
AA (4.5:1 for normal text), so you will find out at once if a colour is too faint.

### Add a page to the interface

1. Create `ris/ui/pages/mypage.py` with a `class MyPage(Page)` (`Page` is in `ris/ui/widgets/common.py`: a
   header plus a body you fill) that takes the `AppContext`, builds its widgets and implements `refresh()`.
   `pages/targets.py` is a short example to copy.
2. Register it in `MainWindow._build_pages()` and add its key to `NAV_SECTIONS` and `PAGE_SUBTITLES`
   (`ris/strings.py`) and `NAV_ICONS` (`theme.py`).
3. Add a GUI test using the `window` fixture in `tests/gui/test_gui.py`.

### Change the database structure

Create `migrations/0003_short_description.sql`. It runs once, inside a transaction, on every user's database
the next time the app starts. SQLite cannot change a `CHECK` constraint in place, so rebuild the table as
`0002_more_document_kinds.sql` does (create new table → copy rows → drop old → rename).

### Add a job portal

Add an object to `portals` in `config/job_portals.json` (limits, accepted files, tips and **sources**). To give
it a profile kit, add a builder in `build_kit()` (`portal_kit.py`).

---

## 12. Build a similar app from scratch: "Resume Lite"

This part builds a small but complete resume app in **six steps and about 300 lines**. It uses the same ideas
and libraries as RIS, so when you finish you will recognise them in the big application. The finished code is
in [`docs/tutorial/resume_lite/`](tutorial/resume_lite/) and its tests run as part of the RIS test suite, so the
code below is known to work.

```
 Resume Lite                       Resume Intelligence Studio
 ─────────────────────────────     ──────────────────────────────────────────
 model.py      (Pydantic)      →   ris/domain/models.py, registry.py
 storage.py    (SQLite + JSON) →   ris/storage/database.py, repository.py
 export_docx.py, export_pdf.py →   ris/composition (what) + ris/rendering (how)
 app.py        (PySide6)       →   ris/ui/
 test_resume_lite.py (pytest)  →   tests/
```

### Step 0 — prepare a folder

```bash
mkdir resume_lite && cd resume_lite
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
python -m pip install PySide6 pydantic python-docx reportlab pypdf pytest pytest-qt
```

### Step 1 — the data model (`model.py`)

Describe *what* a resume contains, and the rules the data must follow. Pydantic checks the rules every time an
object is created.

```python
"""Step 1 — the data model: what a resume contains, with validation."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

DATE = re.compile(r"^\d{4}(-\d{2})?$")   # "2019" or "2019-04"


class Job(BaseModel):
    title: str
    organisation: str
    start: str
    end: str = ""                                   # empty means "present"
    achievements: list[str] = Field(default_factory=list)

    @field_validator("start", "end")
    @classmethod
    def check_date(cls, value: str) -> str:
        if value and not DATE.match(value):
            raise ValueError("use YYYY or YYYY-MM, for example 2019-04")
        return value


class Profile(BaseModel):
    name: str
    email: str = ""
    headline: str = ""
    summary: str = ""
    jobs: list[Job] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        if value and "@" not in value:
            raise ValueError("this is not an email address")
        return value
```

Try it in a Python shell (`python`):

```python
>>> from model import Job
>>> Job(title="Engineer", organisation="Example Lab", start="April 2019")
pydantic_core._pydantic_core.ValidationError: 1 validation error for Job
start
  Value error, use YYYY or YYYY-MM, for example 2019-04 ...
```

### Step 2 — saving and loading (`storage.py`)

Store the whole profile as JSON in one SQLite row. `model_dump_json()` turns the object into text;
`model_validate_json()` turns text back into a checked object. `with self.conn:` is a transaction.

```python
"""Step 2 — saving and loading: one SQLite file, the profile stored as JSON."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from model import Profile


class Store:
    def __init__(self, path: Path) -> None:
        self.conn = sqlite3.connect(path)
        self.conn.execute("CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT)")

    def save(self, profile: Profile) -> None:
        with self.conn:                                  # a transaction: all or nothing
            self.conn.execute("INSERT OR REPLACE INTO profile (id, data) VALUES (1, ?)",
                              (profile.model_dump_json(),))

    def load(self) -> Profile | None:
        row = self.conn.execute("SELECT data FROM profile WHERE id = 1").fetchone()
        return Profile.model_validate_json(row[0]) if row else None
```

RIS uses the same idea — JSON in a `data` column — but one row per record, with revisions, soft delete and a
search index.

### Step 3 — a Word document (`export_docx.py`)

```python
"""Step 3 — a Word document with python-docx."""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.shared import Pt

from model import Profile


def period(start: str, end: str) -> str:
    return f"{start} – {end or 'Present'}"


def export_docx(profile: Profile, path: Path) -> Path:
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    doc.add_heading(profile.name, level=0)
    if profile.headline:
        doc.add_paragraph(profile.headline)
    if profile.email:
        doc.add_paragraph(profile.email)
    if profile.summary:
        doc.add_heading("Professional Summary", level=1)
        doc.add_paragraph(profile.summary)
    if profile.jobs:
        doc.add_heading("Experience", level=1)
        for job in profile.jobs:
            p = doc.add_paragraph()
            p.add_run(f"{job.title}, {job.organisation}").bold = True
            p.add_run(f"    {period(job.start, job.end)}")
            for a in job.achievements:
                doc.add_paragraph(a, style="List Bullet")
    if profile.skills:
        doc.add_heading("Skills", level=1)
        doc.add_paragraph(", ".join(profile.skills))
    doc.save(path)
    return path
```

### Step 4 — a PDF (`export_pdf.py`)

ReportLab builds a PDF from a list of *flowables* (paragraphs, spacers, lists). `escape()` matters: ReportLab
paragraphs understand a little HTML, so a name like "R&D" must become "R&amp;D".

```python
"""Step 4 — a PDF with ReportLab."""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

from export_docx import period
from model import Profile


def export_pdf(profile: Profile, path: Path) -> Path:
    styles = getSampleStyleSheet()
    story = [Paragraph(escape(profile.name), styles["Title"])]
    for line in (profile.headline, profile.email):
        if line:
            story.append(Paragraph(escape(line), styles["Normal"]))
    if profile.summary:
        story += [Spacer(1, 4 * mm), Paragraph("Professional Summary", styles["Heading2"]),
                  Paragraph(escape(profile.summary), styles["Normal"])]
    if profile.jobs:
        story.append(Paragraph("Experience", styles["Heading2"]))
        for job in profile.jobs:
            story.append(Paragraph(f"<b>{escape(job.title)}, {escape(job.organisation)}</b> — "
                                   f"{escape(period(job.start, job.end))}", styles["Normal"]))
            if job.achievements:
                story.append(ListFlowable([ListItem(Paragraph(escape(a), styles["Normal"]))
                                           for a in job.achievements], bulletType="bullet"))
    if profile.skills:
        story += [Paragraph("Skills", styles["Heading2"]), Paragraph(escape(", ".join(profile.skills)),
                                                                     styles["Normal"])]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                      topMargin=16 * mm, bottomMargin=16 * mm, title=f"{profile.name} — Resume").build(story)
    return path
```

Notice that Steps 3 and 4 both decide *what* to show and *how* it looks. With two formats that is fine; with
fifteen templates it is not. RIS splits it: the composer decides *what* (a `ResumeDocument`), the layout planner
and renderers decide *how*.

### Step 5 — the window (`app.py`)

A form with text boxes and three buttons. Each button's `clicked` signal is connected to a method. Errors from
the model are shown in a message box instead of crashing.

```python
"""Step 5 — the desktop window with PySide6 (Qt for Python)."""
from __future__ import annotations

import sys
from pathlib import Path

from pydantic import ValidationError
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from export_docx import export_docx
from export_pdf import export_pdf
from model import Job, Profile
from storage import Store


def parse_jobs(text: str) -> list[Job]:
    """Each job starts with 'Title | Organisation | start | end'; lines starting with '- ' are achievements."""
    jobs: list[Job] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("- ") and jobs:
            jobs[-1].achievements.append(line[2:].strip())
        else:
            parts = [p.strip() for p in line.split("|")] + ["", "", ""]
            jobs.append(Job(title=parts[0], organisation=parts[1], start=parts[2],
                            end="" if parts[3].lower() in ("", "present") else parts[3]))
    return jobs


def jobs_to_text(jobs: list[Job]) -> str:
    lines = []
    for j in jobs:
        lines.append(f"{j.title} | {j.organisation} | {j.start} | {j.end or 'present'}")
        lines += [f"- {a}" for a in j.achievements]
    return "\n".join(lines)


class MainWindow(QWidget):
    def __init__(self, store: Store) -> None:
        super().__init__()
        self.store = store
        self.setWindowTitle("Resume Lite")
        self.name, self.email, self.headline = QLineEdit(), QLineEdit(), QLineEdit()
        self.summary, self.jobs, self.skills = QPlainTextEdit(), QPlainTextEdit(), QLineEdit()
        self.jobs.setPlaceholderText("Scientist | Example Lab | 2019-04 | present\n- Led the sensor test programme")
        form = QFormLayout()
        for label, widget in (("Name", self.name), ("Email", self.email), ("Headline", self.headline),
                              ("Summary", self.summary), ("Experience", self.jobs), ("Skills (comma separated)",
                                                                                   self.skills)):
            form.addRow(label + ":", widget)
        buttons = QHBoxLayout()
        for text, slot in (("Save", self.save), ("Export Word", lambda: self.export("docx")),
                           ("Export PDF", lambda: self.export("pdf"))):
            b = QPushButton(text)
            b.clicked.connect(slot)          # signal (clicked) → slot (our method)
            buttons.addWidget(b)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)
        if (p := store.load()) is not None:
            self.show_profile(p)

    def show_profile(self, p: Profile) -> None:
        self.name.setText(p.name)
        self.email.setText(p.email)
        self.headline.setText(p.headline)
        self.summary.setPlainText(p.summary)
        self.jobs.setPlainText(jobs_to_text(p.jobs))
        self.skills.setText(", ".join(p.skills))

    def profile(self) -> Profile:
        return Profile(name=self.name.text(), email=self.email.text(), headline=self.headline.text(),
                       summary=self.summary.toPlainText(), jobs=parse_jobs(self.jobs.toPlainText()),
                       skills=[s.strip() for s in self.skills.text().split(",") if s.strip()])

    def save(self) -> bool:
        try:
            self.store.save(self.profile())
            return True
        except ValidationError as exc:      # show the model's own error messages
            QMessageBox.warning(self, "Please check", str(exc))
            return False

    def export(self, kind: str) -> None:
        if not self.save():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export", f"Resume.{kind}")
        if path:
            (export_docx if kind == "docx" else export_pdf)(self.profile(), Path(path))


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow(Store(Path.home() / "resume_lite.db"))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

Run it with `python app.py`. Your profile is saved to `resume_lite.db` in your home folder.

### Step 6 — tests (`test_resume_lite.py`)

```python
"""Step 6 — automatic tests with pytest."""
import pytest
from docx import Document
from pypdf import PdfReader

from app import jobs_to_text, parse_jobs
from export_docx import export_docx
from export_pdf import export_pdf
from model import Job, Profile
from storage import Store

SAMPLE = Profile(name="Asha Rao", email="asha@example.org", headline="Embedded engineer",
                 summary="Builds reliable instruments.", skills=["C", "Python"],
                 jobs=[Job(title="Engineer", organisation="Example Lab", start="2019-04",
                           achievements=["Built a test rig"])])


def test_validation_rejects_bad_dates_and_emails():
    with pytest.raises(ValueError):
        Job(title="x", organisation="y", start="April 2019")
    with pytest.raises(ValueError):
        Profile(name="x", email="not-an-email")


def test_jobs_round_trip_through_text():
    jobs = parse_jobs("Engineer | Example Lab | 2019-04 | present\n- Built a test rig")
    assert jobs == SAMPLE.jobs
    assert parse_jobs(jobs_to_text(jobs)) == jobs


def test_save_and_load(tmp_path):
    store = Store(tmp_path / "r.db")
    store.save(SAMPLE)
    assert store.load() == SAMPLE


def test_exports_contain_the_facts(tmp_path):
    docx = export_docx(SAMPLE, tmp_path / "r.docx")
    text = "\n".join(p.text for p in Document(str(docx)).paragraphs)
    assert "Asha Rao" in text and "Built a test rig" in text
    pdf = export_pdf(SAMPLE, tmp_path / "r.pdf")
    assert "Example Lab" in PdfReader(str(pdf)).pages[0].extract_text()


def test_window_saves_and_reloads(tmp_path, qtbot):
    from app import MainWindow

    w = MainWindow(Store(tmp_path / "w.db"))
    qtbot.addWidget(w)
    w.show_profile(SAMPLE)
    assert w.save()
    w2 = MainWindow(Store(tmp_path / "w.db"))
    qtbot.addWidget(w2)
    assert w2.profile() == SAMPLE
```

Run `python -m pytest -q` (on Linux without a screen: `QT_QPA_PLATFORM=offscreen python -m pytest -q`). You
should see `5 passed`.

### Where to go next

Grow Resume Lite one idea at a time, and look at how RIS does each one:

| Next feature | How RIS does it |
|---|---|
| Separate records instead of one big profile; delete with undo | `RecordRepository` with `parent_id`, `revision`, soft `delete()` |
| Forms generated from the model | `F()` metadata + `field_metas()` + `RecordForm` |
| Several layouts from one content description | `ResumeDocument` (IR) + `TemplateSpec` + `LayoutPlanner` |
| Check the files you made | `validate_outputs()` |
| Do not freeze the window during export | `run_task()` with a thread pool |
| Confirmation and confidentiality labels | `Verification`, `Confidentiality`, `ExportService.review()` |
| Upgrading old databases | numbered files in `migrations/` + `migrate()` |
| An installer | PyInstaller spec + Inno Setup / DMG / tar.gz scripts + GitHub Actions |
| Safe updates | Signed manifest + SHA-256 (`ris/update/`) |

---

## 13. When something goes wrong

| Problem | What to try |
|---|---|
| `ModuleNotFoundError: No module named 'PySide6'` | The virtual environment is not active. Run `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`). |
| `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"` (Linux) | Install `libxcb-cursor0` (`sudo apt install libxcb-cursor0`), or use `QT_QPA_PLATFORM=offscreen` for tests. |
| A test fails only on Windows | Paths (`\` vs `/`), file locking (close files before deleting), or text encoding — always pass `encoding="utf-8"`. |
| `ValidationError` when saving | The message names the field and the rule. The model in `models.py` shows what is allowed. |
| The window freezes | Long work is running on the interface thread; move it into `run_task()`. |
| Export says validation failed | Open the report in the export dialog: it lists the missing text or the leak it found. |
| Something only happens in the installed app | Run the program with `--selftest --report report.txt` and read the report; look at the log (*Settings & Security → Open log folder*). |

Debugging tips: put `breakpoint()` in the code and run the test (`python -m pytest tests/unit/test_x.py -k name
-s`) to stop there and inspect variables; or use your editor's debugger. Logs never contain resume content
(by design), so log *what happened*, not *what the user wrote*.

---

## 14. Glossary

| Term | Meaning |
|---|---|
| **ATS** | Applicant tracking system: software employers use to read and rank resumes. |
| **Checksum / SHA-256** | A fingerprint of a file; any change produces a different fingerprint. |
| **CI** | Continuous integration: automatic tests on every change (`ci.yml`). |
| **Composer** | Code that decides which records go into a document and in what order. |
| **Ed25519** | A digital signature scheme used to sign update manifests. |
| **Event loop** | Qt's loop that waits for user actions and calls the connected functions. |
| **Fixture** | A pytest helper that prepares something for a test (a temporary folder, a window). |
| **IR** | Intermediate representation: `ResumeDocument`, the content without styling. |
| **JSON** | A text format for structured data: `{"name": "Asha", "skills": ["C"]}`. |
| **Manifest** | `ris-update.json`: the description of a release that the app checks. |
| **Migration** | A numbered SQL file that upgrades the database structure. |
| **Mode** | A resume style with its own sections and wording (e.g. government bio-data, academic CV). |
| **PIQ / DAF** | Personal Information Questionnaire (SSB) / Detailed Application Form (UPSC). |
| **PyInstaller** | Tool that bundles Python and the app into a stand-alone program. |
| **Pydantic model** | A class that describes data and validates it. |
| **Record** | One item in the profile: a position, a degree, a training course, a skill … |
| **Repository** | The class that reads and writes records in the database. |
| **Signal / slot** | Qt's way of saying "when this happens, call that". |
| **Snapshot** | All records loaded into memory for fast, consistent reading. |
| **Soft delete** | Marking a record deleted (recoverable) instead of erasing it. |
| **STAR** | Situation, Task, Action, Result — a way to structure interview answers. |
| **Template** | A JSON file describing how a resume looks. |
| **Transaction** | A group of database changes that succeed or fail together. |
| **Variant** | One resume made from the master profile (its mode, template, length, target). |
| **Virtual environment** | A private folder of libraries for one project (`.venv`). |
| **Workspace** | A folder holding one profile database, its backups and exports. |

---

## 15. Further reading

* Python tutorial — <https://docs.python.org/3/tutorial/>
* Qt for Python (PySide6) — <https://doc.qt.io/qtforpython-6/>
* Pydantic — <https://docs.pydantic.dev/>
* SQLite — <https://www.sqlite.org/docs.html> and Python's `sqlite3` — <https://docs.python.org/3/library/sqlite3.html>
* python-docx — <https://python-docx.readthedocs.io/>
* ReportLab user guide — <https://docs.reportlab.com/>
* pytest — <https://docs.pytest.org/> and pytest-qt — <https://pytest-qt.readthedocs.io/>
* PyInstaller — <https://pyinstaller.org/>
* GitHub Actions — <https://docs.github.com/actions>
* Semantic versioning — <https://semver.org/>

Related documents in this repository: `ARCHITECTURE.md` (design decisions in more depth), `DATA_MODEL.md`
(every field of every record kind), `TEMPLATE_GUIDE.md`, `UPDATES.md`, `RELEASING.md`, `TEST_PLAN.md`,
`SECURITY_PRIVACY.md` and `THREAT_MODEL.md`.
