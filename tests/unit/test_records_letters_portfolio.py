"""Record coverage (summaries, projects, vacancies, applications, claims, service activities) and the
cover-letter and portfolio composers (PRF-05, PRF-10, PRF-22, VAC-01, TRK-01, TRK-03, TRK-04, PRV-02)."""

from __future__ import annotations

from datetime import date

import pytest

from ris.composition.composer import ComposeContext, ResumeComposer
from ris.composition.cover_letter import draft_cover_letter, letter_document
from ris.composition.portfolio import build_portfolio
from ris.domain.enums import Confidentiality, RecordKind, Verification
from ris.domain.models import Application, Claim, CoverLetter, Project, Vacancy, Variant
from ris.intelligence.analysis import analyse
from ris.rendering.export import ExportOptions, ExportService
from ris.rendering.specs import TemplateLibrary
from ris.services.profile import ProfileService
from tests.fixtures import _c

TODAY = date(2026, 10, 24)


def _compose(ws, **variant):
    snap = ProfileService(ws.repo).snapshot()
    v = Variant.model_validate({"name": "t", "mode": "general_professional", "template_id": "ats_minimal",
                                "length": "full", **variant})
    ctx = ComposeContext(snapshot=snap, variant=v, template_id=v.template_id, template_version="1.0.0",
                         approved_claims={}, is_sample=True, today=TODAY)
    return ResumeComposer(ctx).compose(), snap


@pytest.mark.req("PRF-05")
def test_multiple_summaries_chosen_by_focus_or_explicitly(repo, workspace):
    _c(repo, RecordKind.PERSONAL, {"full_name": "Focus Example"})
    general = _c(repo, RecordKind.SUMMARY, {"focus": "general", "text": "General engineering summary."})
    defence = _c(repo, RecordKind.SUMMARY, {"focus": "defence_technology", "text": "Defence technology summary."})
    research = _c(repo, RecordKind.SUMMARY, {"focus": "aiml_research", "text": "AI/ML research summary."})
    doc, _ = _compose(workspace, mode="defence_technical")
    assert doc.section("summary").source_ids == [defence.id]
    doc, _ = _compose(workspace, mode="scientific_research")
    assert doc.section("summary").source_ids == [research.id]
    doc, _ = _compose(workspace, mode="general_professional")
    assert doc.section("summary").source_ids == [general.id]
    doc, _ = _compose(workspace, mode="defence_technical", summary_id=research.id)
    assert doc.section("summary").paragraphs == ["AI/ML research summary."]


@pytest.mark.req("PRF-10")
def test_project_record_stores_every_documented_field(repo):
    data = {
        "title": "Sensor fusion test bench", "problem": "Manual calibration was slow.", "role": "Design lead",
        "involvement": "leading", "organisation": "Example Lab", "status": "completed", "start": "2021-04",
        "end": "2022-03", "approach": "Automated calibration sequence.", "architecture": "Host PC + MCU + rig.",
        "hardware": ["STM32", "Thermal chamber"], "software": ["Python"], "algorithms": ["Least squares"],
        "dataset": "Calibration logs (internal).", "results": "Calibration documented end to end.",
        "metrics": ["12 sensors per batch"], "limitations": "Bench only.", "individual_contribution": "Firmware.",
        "team_contribution": "Mechanical fixtures.", "team_size": 4, "evidence": "Test report TR-01.",
        "approved_external_description": "Built an automated sensor calibration bench.",
        "keywords": ["calibration"], "url": "https://example.org/bench",
    }
    rec = _c(repo, RecordKind.PROJECT, Project.model_validate(data))
    got = repo.get(rec.id).data
    for key, value in data.items():
        assert getattr(got, key) == value, key
    assert got.is_current is False


@pytest.mark.req("VAC-01")
def test_vacancy_record_fields(repo):
    data = {"title": "Scientist 'E'", "employer": "Example Establishment", "url": "https://example.org/advt",
            "reference": "ADVT-01/2026", "deadline": "2026-11-30", "raw_text": "Essential: M.Tech.",
            "essential_qualifications": "M.Tech. in Electronics", "desirable_qualifications": "Ph.D.",
            "required_skills": "Embedded systems", "experience_criteria": "10 years", "application_notes": "Via proper channel"}
    rec = _c(repo, RecordKind.VACANCY, Vacancy.model_validate(data))
    got = repo.get(rec.id).data
    for key, value in data.items():
        assert getattr(got, key) == value, key


@pytest.mark.req("TRK-01")
def test_application_record_fields(repo):
    data = {"organisation": "Example Establishment", "vacancy_title": "Scientist 'E'", "official_url": "https://example.org/a",
            "reference_number": "ADVT-01/2026", "eligibility_notes": "Check analogous post.", "deadline": "2026-11-30",
            "status": "applied", "submission_date": "2026-11-20", "interview_date": "2027-01-15",
            "follow_up_date": "2026-12-15", "outcome": ""}
    rec = _c(repo, RecordKind.APPLICATION, Application.model_validate(data))
    got = repo.get(rec.id).data
    for key, value in data.items():
        assert getattr(got, key) == value, key


@pytest.mark.req("PRV-02")
def test_claim_record_keeps_provenance_and_both_wordings(repo):
    var = _c(repo, RecordKind.VARIANT, {"name": "v"})
    data = {"target_bullet_id": "b1", "source_record_ids": ["b1", "p1"], "source_field": "text",
            "original_text": "Worked on calibration.", "generated_text": "Calibrated sensors.",
            "approved_text": "Calibrated humidity sensors.", "material_facts": ["Calibrated humidity sensors"],
            "assumptions": ["Humidity sensors were the subject"], "missing_metrics": ["How many sensors?"],
            "flags": [], "status": "approved", "confidentiality": "approved", "approved_at": "2026-10-24T10:00:00Z",
            "generator": "rules-engine"}
    rec = repo.create(RecordKind.CLAIM, Claim.model_validate(data), parent_id=var.id)
    got = repo.get(rec.id).data
    for key, value in data.items():
        assert getattr(got, key) == value, key


@pytest.mark.req("PRF-22")
def test_grants_and_academic_service_have_dedicated_sections(sample_ws):
    doc, snap = _compose(sample_ws, mode="research_portfolio", template_id="research_showcase")
    grants, service = doc.section("grants"), doc.section("service")
    assert grants is not None and grants.entries
    assert service is not None and service.entries
    types = {snap.get(e.source_ids[0]).data.activity_type for e in service.entries}
    assert types <= {"peer_review", "supervision", "conference_organisation"} and types


@pytest.mark.req("TRK-03", "DEF-05")
def test_cover_letter_uses_only_confirmed_disclosable_facts_and_exports(sample_ws, tmp_path):
    snap = ProfileService(sample_ws.repo).snapshot()
    vac = sample_ws.repo.list(RecordKind.VACANCY)[0]
    analysis = analyse(snap, vac.data, today=TODAY)
    payload = draft_cover_letter(snap, vac.data, analysis, style="formal", today=TODAY)
    assert payload["source_record_ids"]
    for rid in payload["source_record_ids"]:
        rec = snap.get(rid)
        assert snap.effective_verification(rec) != Verification.UNCONFIRMED
        assert snap.effective_confidentiality(rec) != Confidentiality.CONFIDENTIAL
    text = " ".join(payload["paragraphs"]).lower()
    for invented in ("recommended by", "referred by", "insider", "i know your", "personally acquainted"):
        assert invented not in text
    confidential = [r for r in snap.facts() if snap.effective_confidentiality(r) == Confidentiality.CONFIDENTIAL]
    for r in confidential:
        assert r.title.lower() not in text
    letter = sample_ws.repo.create(RecordKind.COVER_LETTER, CoverLetter.model_validate(payload),
                                   verification=Verification.CONFIRMED, confidentiality=Confidentiality.APPROVED)
    lib = TemplateLibrary()
    spec = lib.get("ats_minimal")
    doc = letter_document(sample_ws.repo.get(letter.id).data, snap, template_id=spec.id, template_version=spec.version,
                          is_sample=True)
    out = ExportService(sample_ws, lib, today=TODAY).export_document(
        doc, spec, ExportOptions(formats=("docx", "pdf"), folder=tmp_path, pdf_engine="builtin",
                                 acknowledge_warnings=True), document_kind="cover_letter", source_id=letter.id)
    assert out.ok, out.message
    assert {f.format for f in out.files} == {"docx", "pdf"}


@pytest.mark.req("TRK-04", "DEF-05")
def test_redacted_portfolio_contains_only_approved_project_descriptions(sample_ws, tmp_path):
    snap = ProfileService(sample_ws.repo).snapshot()
    doc = build_portfolio(snap, template_id="modern_professional", template_version="1.0.0", is_sample=True)
    projects = doc.section("projects")
    assert projects is not None and projects.entries
    for e in projects.entries:
        rec = snap.get(e.source_ids[0])
        assert rec.data.approved_external_description and e.description == rec.data.approved_external_description
        assert snap.effective_confidentiality(rec) in (Confidentiality.PUBLIC, Confidentiality.APPROVED)
        assert snap.effective_verification(rec) != Verification.UNCONFIRMED
    public = build_portfolio(snap, template_id="modern_professional", template_version="1.0.0", public_only=True,
                             is_sample=True)
    for rid in public.all_source_ids():
        rec = snap.get(rid)
        if rec.kind != RecordKind.PERSONAL:
            assert snap.effective_confidentiality(rec) == Confidentiality.PUBLIC, rec.title
    lib = TemplateLibrary()
    out = ExportService(sample_ws, lib, today=TODAY).export_document(
        doc, lib.get("modern_professional"), ExportOptions(formats=("pdf",), folder=tmp_path, pdf_engine="builtin",
                                                          acknowledge_warnings=True), document_kind="portfolio")
    assert out.ok, out.message


@pytest.mark.req("SEC-05", "PRF-21")
def test_leaving_out_deleting_and_purging_are_distinct(sample_ws):
    repo = sample_ws.repo
    ref = repo.list(RecordKind.REFERENCE)[0]
    # 1. Leaving a referee out of one resume changes only that resume.
    doc, _ = _compose(sample_ws, mode="research_portfolio", template_id="research_showcase", exclude_ids=[ref.id])
    assert ref.id not in doc.all_source_ids() and repo.find(ref.id) is not None
    # 2. Deleting moves the record to Recently deleted, from where it can be restored.
    repo.delete(ref.id)
    assert repo.find(ref.id) is None and any(r.id == ref.id for r in repo.deleted_records())
    repo.undelete(ref.id)
    assert repo.find(ref.id) is not None
    # 3. Purging is a separate, final step.
    repo.delete(ref.id)
    repo.purge(ref.id)
    assert repo.find(ref.id) is None and not any(r.id == ref.id for r in repo.deleted_records())
