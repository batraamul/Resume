"""Training sections, interview preparation, job-portal kit and ATS readiness
(PRF-23..25, INT-01..05, POR-01..04)."""

from __future__ import annotations

from datetime import date

import pytest

from ris.composition.composer import ComposeContext, ResumeComposer
from ris.domain.enums import Confidentiality, RecordKind, Verification
from ris.domain.models import InterviewStory, Questionnaire, Training, Variant
from ris.intelligence import interview as iv
from ris.intelligence import portal_kit as pk
from ris.intelligence.analysis import analyse
from ris.intelligence.ats import ats_readiness
from ris.rendering.export import ExportOptions, ExportService
from ris.rendering.specs import TemplateLibrary
from ris.services.profile import ProfileService
from tests.fixtures import _c

TODAY = date(2026, 10, 25)


def _compose(ws, **variant):
    snap = ProfileService(ws.repo).snapshot()
    v = Variant.model_validate({"name": "t", "mode": "general_professional", "template_id": "ats_minimal",
                                "length": "full", **variant})
    ctx = ComposeContext(snapshot=snap, variant=v, template_id=v.template_id, template_version="1.0.0",
                         approved_claims={}, is_sample=True, today=TODAY)
    return ResumeComposer(ctx).compose(), snap


# --------------------------------------------------------------------------- training


@pytest.mark.req("PRF-23")
def test_training_model_validation():
    t = Training(title="X", end="2022-03", valid_until="2025-03", duration_hours=40)
    assert t.display_title() == "X"
    with pytest.raises(ValueError):
        Training(title="X", end="2022-03", valid_until="2021-01")
    with pytest.raises(ValueError):
        Training(title="X", start="2022-05", end="2022-01")


@pytest.mark.req("PRF-23", "PRF-24")
def test_dedicated_training_sections_in_government_biodata(sample_ws):
    doc, snap = _compose(sample_ws, mode="government_biodata", template_id="government_cv")
    keys = [s.key for s in doc.sections]
    for key in ("training_programmes", "courses", "certifications", "workshops"):
        assert key in keys, key
    certs = doc.section("certifications")
    titles = [e.title for e in certs.entries]
    assert "Deep Learning for Edge Devices" in titles
    lang = next(e for e in certs.entries if "English" in e.title)
    assert lang.status_label == "Expired"
    progs = doc.section("training_programmes")
    assert progs.layout == "table" and any("Mid-Career" in r[0] for r in progs.table.rows)
    assert any("5 days" in r[3] for r in progs.table.rows)
    assert "training" not in keys  # the combined section is not used when every dedicated section is present
    assert not any("Executive Programme" in e.title for s in doc.sections for e in s.entries)  # planned hidden


@pytest.mark.req("PRF-24")
def test_combined_section_avoids_duplicates_and_drops_expired_in_short_resumes(sample_ws):
    doc, _ = _compose(sample_ws, length="two_pages", section_order=["summary", "experience", "training", "workshops"])
    combined = [e.title for e in doc.section("training").entries]
    workshops = [e.title for e in doc.section("workshops").entries]
    assert workshops and not set(combined) & set(workshops)
    assert not any("English" in t for t in combined), "expired certification left out of a two-page resume"
    assert any("Expired certification left out" in t for t in doc.trimmed)


@pytest.mark.req("PRF-24")
def test_certification_entry_details(sample_ws):
    doc, _ = _compose(sample_ws, section_order=["certifications"])
    e = next(e for e in doc.section("certifications").entries if e.title == "Deep Learning for Edge Devices")
    meta = dict(e.meta)
    assert meta["Duration"] == "40 hours" and meta["Credential"] == "EAAC-DL-0042"
    assert meta["Valid until"] == "Mar 2029" and meta["Mode"] == "Online"
    assert e.subtitle == "Example Academy of Applied Computing"


@pytest.mark.req("PRF-25")
def test_unconfirmed_training_needs_review_before_export(sample_ws, tmp_path):
    rec = sample_ws.repo.create(RecordKind.TRAINING, {"training_type": "certification", "title": "Unverified cert",
                                                      "end": "2024"}, verification=Verification.UNCONFIRMED)
    var = sample_ws.repo.create(RecordKind.VARIANT, Variant(name="v", mode="government_biodata",
                                                            template_id="government_cv", length="full"))
    out = ExportService(sample_ws, TemplateLibrary(), today=TODAY).export_variant(
        var.id, ExportOptions(formats=("pdf",), folder=tmp_path, pdf_engine="builtin"))
    assert not out.ok and any(i.record_id == rec.id for i in out.review.blocking)


@pytest.mark.req("PRF-23")
def test_training_evidence_matches_vacancy_requirements(repo):
    from ris.domain.models import Requirement, Vacancy

    _c(repo, RecordKind.PERSONAL, {"full_name": "A"})
    t = _c(repo, RecordKind.TRAINING, {"training_type": "certification", "title": "Certified Kubernetes Administrator",
                                       "skills": ["Kubernetes"], "end": "2024"})
    snap = ProfileService(repo).snapshot()
    vac = Vacancy(title="DevOps", requirements=[Requirement(text="Experience with Kubernetes", category="technical")])
    res = analyse(snap, vac, today=TODAY).results[0]
    assert t.id in res.possessed_sources


# --------------------------------------------------------------------------- interview


@pytest.mark.req("INT-01")
def test_question_bank_loads_with_sources():
    bank = iv.load_bank()
    assert len(bank.questions) >= 60
    cats = {q.category for q in bank.questions}
    assert {"personal", "technical", "research", "behavioural", "government", "questionnaire", "closing"} <= cats
    for q in bank.questions:
        if q.source:
            assert q.source in bank.sources
    assert {"star", "board", "questionnaire"} <= set(bank.tips)


@pytest.mark.req("INT-02")
def test_personalised_questions_come_from_records(sample_ws):
    snap = ProfileService(sample_ws.repo).snapshot()
    vac = sample_ws.repo.list(RecordKind.VACANCY)[0]
    analysis = analyse(snap, vac.data, today=TODAY)
    qs = iv.personalised_questions(snap, vacancy=vac.data, analysis=analysis,
                                   organisation={"name": "Example Agency", "domains": ["avionics"]},
                                   questionnaire=Questionnaire(hobbies=["cycling"]), today=TODAY)
    texts = [q.text for q in qs]
    assert any("Why did you move from" in t for t in texts)
    assert any("Edge super-resolution pipeline" in t for t in texts)
    assert any("Why do you want to work with Example Agency" in t for t in texts)
    assert any("cycling" in t for t in texts)
    assert any(q.source == "vacancy" for q in qs)
    under_review = next(t for t in texts if "Detection-aware" in t)
    assert "under review" in under_review and "published" not in under_review.split("never")[0]
    confidential = [r.title for r in snap.facts() if snap.effective_confidentiality(r) == Confidentiality.CONFIDENTIAL]
    for title in confidential:
        assert not any(title in t for t in texts)
    for q in qs:
        for rid in q.record_ids:
            assert snap.get(rid) is not None
    assert len(texts) == len({t.casefold() for t in texts})


@pytest.mark.req("INT-02")
def test_practice_set_mixes_personalised_questions():
    qs = [iv.Question("personal", f"P{i}", source="profile") for i in range(5)] + \
         [iv.Question("technical", f"G{i}") for i in range(20)]
    round_ = iv.practice_set(qs, None, 8, seed=1)
    assert len(round_) == 8 and sum(q.personalised for q in round_) >= 4
    only = iv.practice_set(qs, {"technical"}, 5, seed=2)
    assert all(q.category == "technical" for q in only)


@pytest.mark.req("INT-03")
def test_star_story_analysis():
    weak = iv.analyse_story(InterviewStory(
        situation="In 2021 our division was preparing for a review and there was a lot going on across many teams "
                  "with several deadlines and a great deal of background to explain to everyone involved.",
        task="We had to deliver.", action="We fixed it.", result="It worked."))
    assert any("Action is" in i for i in weak.issues)
    assert any("Situation is" in i for i in weak.issues)
    assert any("'we' more than 'I'" in i for i in weak.issues)
    good = iv.analyse_story({"situation": "Two days before a field trial, the receiver failed acceptance tests.",
                             "task": "I was responsible for getting the ground station certified in time.",
                             "action": " ".join(["I isolated the fault to the RF front end, replaced the filter, "
                                                 "re-ran the calibration sequence and documented each step."] * 4),
                             "result": "The station passed on the next run and the trial started on schedule; "
                                       "3 stations now use the procedure."})
    assert not any("Action is" in i for i in good.issues) and good.i_count > good.we_count
    assert 0 < good.seconds < 200
    missing = iv.analyse_story({"situation": "x"})
    assert any("Add the Result" in i for i in missing.issues)


@pytest.mark.req("INT-04")
def test_questionnaire_autofill_and_consistency(sample_ws):
    snap = ProfileService(sample_ws.repo).snapshot()
    q = iv.autofill_questionnaire(Questionnaire(), snap)
    assert any("M.Tech." in r.examination for r in q.education) and q.languages
    assert not [i for i in iv.check_questionnaire(q, snap) if i.area == "Education"]
    edited = q.model_copy(deep=True)
    row = next(r for r in edited.education if "M.Tech." in r.examination)
    row.year = "2011"
    row.result = "First class"
    edited.responsibilities = edited.responsibilities + ["Captain of the college cricket team"]
    edited.languages = ["English"]
    issues = iv.check_questionnaire(edited, snap)
    msgs = " ".join(i.message for i in issues)
    assert "says 2011, your profile says 2010" in msgs
    assert "differs from 'CGPA 8.6/10'" in msgs
    assert "cricket" in msgs and "Languages differ" in msgs
    assert any(i.area == "Completeness" for i in issues)


@pytest.mark.req("INT-05", "DEF-05")
def test_interview_pack_and_questionnaire_export(sample_ws, tmp_path):
    snap = ProfileService(sample_ws.repo).snapshot()
    sample_ws.repo.create(RecordKind.INTERVIEW_ANSWER, {"question": "Tell us about yourself.", "category": "personal",
                                                        "answer": "Twenty years across avionics and instrumentation.",
                                                        "confidence": 3})
    sample_ws.repo.create(RecordKind.INTERVIEW_STORY, {"title": "Receiver failure", "situation": "A receiver failed.",
                                                       "task": "I owned certification.", "action": "I fixed it.",
                                                       "result": "Trial on time."})
    lib = TemplateLibrary()
    svc = ExportService(sample_ws, lib, today=TODAY)
    spec = lib.get("ats_minimal")
    doc = iv.interview_pack(snap, questions=iv.personalised_questions(snap, today=TODAY),
                            answers=sample_ws.repo.list(RecordKind.INTERVIEW_ANSWER),
                            stories=sample_ws.repo.list(RecordKind.INTERVIEW_STORY), template_id=spec.id,
                            template_version=spec.version, is_sample=True)
    out = svc.export_document(doc, spec, ExportOptions(formats=("docx", "pdf"), folder=tmp_path, pdf_engine="builtin",
                                                       acknowledge_warnings=True), document_kind="interview_pack")
    assert out.ok, (out.message, out.report and [(c.name, c.details) for c in out.report.failures])
    q = iv.autofill_questionnaire(Questionnaire(title="Test PIQ", place_of_birth="Pune", hobbies=["cycling"]), snap)
    gov = lib.get("government_cv")
    qdoc = iv.questionnaire_document(q, snap, template_id=gov.id, template_version=gov.version, is_sample=True)
    out2 = svc.export_document(qdoc, gov, ExportOptions(formats=("pdf",), folder=tmp_path, pdf_engine="builtin",
                                                        acknowledge_warnings=True), document_kind="questionnaire")
    assert out2.ok, (out2.message, out2.report and [(c.name, c.details) for c in out2.report.failures])


# --------------------------------------------------------------------------- portals


@pytest.mark.req("POR-01")
def test_portal_config_has_sourced_limits():
    data = pk.load_portals()
    ids = {p["id"] for p in data["portals"]}
    assert {"linkedin", "naukri", "indeed", "ncs"} <= ids
    li = {f["id"]: f for f in pk.portal("linkedin")["fields"]}
    assert li["headline"]["limit"] == 220 and li["about"]["limit"] == 2600 and li["experience"]["limit"] == 2000
    nk = pk.portal("naukri")
    assert nk["resume_max_mb"] == 2 and "RTF" in nk["resume_formats"]
    assert {f["id"]: f for f in nk["fields"]}["key_skills"]["limit"] == 50
    for p in data["portals"]:
        for f in p.get("fields", []):
            if f.get("limit") or f.get("limit_words"):
                assert p.get("sources"), p["id"]


@pytest.mark.req("POR-02", "DEF-05")
def test_kit_uses_only_confirmed_disclosable_facts_within_limits(sample_ws):
    snap = ProfileService(sample_ws.repo).snapshot()
    kit = pk.build_kit(snap, today=TODAY)
    assert set(kit) == {"linkedin", "naukri", "indeed"}
    for fields in kit.values():
        for f in fields:
            level, _msg = f.status()
            if f.limit_kind == "hard":
                assert level != "over", (f.portal, f.field_id)
            for rid in f.source_ids:
                rec = snap.get(rid)
                assert snap.effective_verification(rec) != Verification.UNCONFIRMED
                assert snap.effective_confidentiality(rec) in (Confidentiality.PUBLIC, Confidentiality.APPROVED)
    li = {f.field_id: f for f in kit["linkedin"]}
    assert li["headline"].text.startswith("Scientist E") and len(li["headline"].text) <= 220
    assert "Highlights:" in li["about"].text
    assert any("Deep Learning for Edge Devices" in c for c in li["certifications"].items)
    nk = {f.field_id: f for f in kit["naukri"]}
    assert len(nk["key_skills"].items) <= 50 and "years" in nk["resume_headline"].text
    confidential = [r for r in snap.facts() if snap.effective_confidentiality(r) == Confidentiality.CONFIDENTIAL]
    text = pk.kit_as_text(kit)
    for r in confidential:
        assert r.title not in text


@pytest.mark.req("POR-02")
def test_kit_field_status_messages():
    f = pk.KitField("linkedin", "headline", "Headline", text="x" * 230, limit=220, limit_kind="hard")
    assert f.status()[0] == "over"
    f2 = pk.KitField("naukri", "summary", "Summary", text="word " * 150, limit_words=(200, 300), limit_kind="advice")
    assert f2.status()[0] == "warn" and "150 words" in f2.status()[1]
    f3 = pk.KitField("naukri", "key_skills", "Key skills", items=[str(i) for i in range(51)], limit=50,
                     limit_kind="hard")
    assert f3.status()[0] == "over"


@pytest.mark.req("POR-03")
def test_file_checks(tmp_path, sample_ws):
    lib = TemplateLibrary()
    var = sample_ws.repo.list(RecordKind.VARIANT)[0]
    out = ExportService(sample_ws, lib, today=TODAY).export_variant(
        var.id, ExportOptions(formats=("pdf", "docx"), folder=tmp_path, pdf_engine="builtin",
                              filename="Anika_Sharma_Resume", acknowledge_warnings=True))
    pdf = next(f.path for f in out.files if f.format == "pdf")
    checks = pk.check_file(pdf)
    assert all(c.level != "fail" for c in checks), checks
    assert any("selectable text" in c.message for c in checks)
    generic = tmp_path / "resume.pdf"
    generic.write_bytes(pdf.read_bytes())
    assert any("generic name" in c.message for c in pk.check_file(generic))
    big = tmp_path / "Big_Resume.pdf"
    big.write_bytes(b"%PDF-1.4\n" + b"0" * (3 * 1024 * 1024))
    msgs = [c for c in pk.check_file(big) if c.level == "fail"]
    assert any("2 MB limit" in c.message for c in msgs) and any("selectable text" in c.message or "could not be read"
                                                                 in c.message for c in msgs)
    txt = tmp_path / "Anika_Resume.txt"
    txt.write_text("hello")
    assert any(c.level == "fail" and "accepts" in c.message for c in pk.check_file(txt, "naukri"))
    assert pk.suggested_filename("Dr. Anika Sharma", ".pdf") == "Anika_Sharma_Resume.pdf"


@pytest.mark.req("POR-04")
def test_ats_readiness_distinguishes_plain_and_graphical(sample_ws):
    lib = TemplateLibrary()
    doc, snap = _compose(sample_ws, template_id="ats_minimal", length="two_pages")
    plain = ats_readiness(doc, lib.get("ats_minimal"))
    by_id = {c.id: c for c in plain.checks}
    assert by_id["columns"].status == "pass" and by_id["graphics"].status == "pass"
    assert all(c.source for c in plain.checks)
    graphical = ats_readiness(doc, lib.get("graphical_profile"))
    gid = {c.id: c for c in graphical.checks}
    assert gid["columns"].status == "fail" and gid["graphics"].status == "fail"
    assert graphical.score < plain.score
    vac = sample_ws.repo.list(RecordKind.VACANCY)[0]
    rel = analyse(snap, vac.data, today=TODAY).relevance
    with_kw = ats_readiness(doc, lib.get("ats_minimal"), rel)
    kw = next(c for c in with_kw.checks if c.id == "keywords")
    assert with_kw.keyword_coverage is not None and "%" in kw.detail
