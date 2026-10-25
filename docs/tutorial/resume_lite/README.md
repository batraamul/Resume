# Resume Lite — tutorial project

A small resume application (about 300 lines) that uses the same ideas and libraries as Resume Intelligence
Studio: a Pydantic data model, SQLite storage, Word and PDF export, a PySide6 window and pytest tests.

It is explained step by step in [Part 12 of the Developer Guide](../../DEVELOPER_GUIDE.md#12-build-a-similar-app-from-scratch-resume-lite).

```bash
python -m pip install PySide6 pydantic python-docx reportlab pypdf pytest pytest-qt
python app.py              # run the app (saves to resume_lite.db in your home folder)
python -m pytest -q        # run its tests (Linux without a screen: QT_QPA_PLATFORM=offscreen)
```

The RIS test suite runs these tests too (`tests/security/test_developer_guide.py`) and checks that the code
shown in the guide is exactly the code in this folder.
