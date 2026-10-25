# Release checklist

- [ ] Version updated in `ris/__init__.py`, `pyproject.toml` and `CHANGELOG.md`.
- [ ] New database changes are a new numbered migration; older migrations unchanged (checksums verified at start-up).
- [ ] `ruff check ris tests scripts` clean.
- [ ] `QT_QPA_PLATFORM=offscreen python -m pytest` — all tests pass; failures investigated, not skipped.
- [ ] `python scripts/trace_requirements.py` — no *Failing* requirements; review *No automated test* entries.
- [ ] `python scripts/gen_data_dictionary.py` — DATA_MODEL.md regenerated.
- [ ] `python scripts/generate_examples.py` (built-in) and `--engine libreoffice` — all templates validate;
      selected outputs inspected visually and listed in TEST_REPORT.md.
- [ ] `--selftest` passes from source on each platform you release for.
- [ ] PyInstaller build produced and `--selftest` passes on the frozen application.
- [ ] Screenshot pass reviewed (`--screenshot`).
- [ ] `RIS_RELEASE_FORBIDDEN="<your name>,<your email>,<your phone>" python scripts/make_release.py` passes.
- [ ] ZIP extracted to an empty folder; clean install from `requirements.txt`; tests and self-test pass there.
- [ ] TEST_REPORT.md and IMPLEMENTATION_STATUS.md updated with what was and was not verified.
- [ ] Known limitations listed in CHANGELOG.md.
