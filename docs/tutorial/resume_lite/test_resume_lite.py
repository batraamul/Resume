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
