"""Scientist F/G formats, chart choices and the openings-feed import (FMT-01..05, CHT-01..03, FED-01..02)."""

from __future__ import annotations

import json
from datetime import date

import pytest

from ris.composition.composer import PROFORMA_DECLARATION, ComposeContext, ResumeComposer
from ris.composition.ir import ResumeDocument
from ris.domain import charts
from ris.domain.enums import RecordKind
from ris.domain.models import Vacancy, Variant
from ris.intelligence.formats import recommend, recommend_for_vacancy
from ris.rendering import graphics
from ris.rendering.export import ExportOptions, ExportService
from ris.rendering.layout import LayoutPlanner
from ris.rendering.specs import TemplateLibrary
from ris.services.openings_feed import import_feed, item_to_vacancy, newest_feed
from ris.services.profile import ProfileService

TODAY = date(2026, 10, 25)


def _compose(ws, vacancy=None, **variant):
    snap = ProfileService(ws.repo).snapshot()
    v = Variant.model_validate({"name": "t", "mode": "deputation_proforma", "template_id": "dopt_proforma",
                                "length": "full", **variant})
    ctx = ComposeContext(snapshot=snap, variant=v, template_id=v.template_id, template_version="1.0.0",
                         approved_claims={}, is_sample=True, today=TODAY, vacancy=vacancy,
                         vacancy_title=vacancy.title if vacancy else "")
    return ResumeComposer(ctx).compose()


def _rows(doc: ResumeDocument, key: str) -> dict[str, str]:
    return {r[0]: r[1] for r in doc.section(key).table.rows}


# --------------------------------------------------------------------------- deputation proforma


@pytest.mark.req("FMT-01")
def test_proforma_follows_dopt_items_and_keeps_private_items_blank_by_default(sample_ws):
    vac = Vacancy(title="Scientist F", employer="Example Organisation", reference="ADV/1/2026",
                  recruitment_mode="deputation", essential_qualifications="Master's degree in Electronics.")
    doc = _compose(sample_ws, vac)
    keys = [s.key for s in doc.sections]
    for key in ("proforma_particulars", "education", "proforma_requirements", "proforma_statement", "experience",
                "proforma_service", "proforma_basis", "declaration", "employer_certificate"):
        assert key in keys, key
    assert doc.title_line == "BIO-DATA / CURRICULUM VITAE PROFORMA"
    assert doc.headline.startswith("Application for the post of Scientist F, Example Organisation")
    assert "ADV/1/2026" in doc.headline
    p = _rows(doc, "proforma_particulars")
    assert p["1. Name and address (in block letters)"] == "ANIKA SHARMA"  # no address unless opted in
    assert p["2. Date of birth (in Christian era)"] == ""
    assert _rows(doc, "proforma_basis")["17. Whether applying on deputation (ISTC / STC), absorption or "
                                        "re-employment basis"] == "Deputation"
    assert _rows(doc, "proforma_statement")[next(iter(_rows(doc, "proforma_statement")))] == ""
    req = doc.section("proforma_requirements").table
    assert req.rows[0][:2] == ["Essential", "Master's degree in Electronics."] and req.rows[0][2] == ""
    assert doc.section("declaration").paragraphs == [PROFORMA_DECLARATION]
    emp = doc.section("experience").table
    assert emp.header[1] == "Post held on regular basis" and len(emp.header) == 6
    assert all(row[4] == "" for row in emp.rows), "pay is printed only when opted in"
    assert any("•" in row[5] for row in emp.rows), "duties include the statements of work"


@pytest.mark.req("FMT-01", "PRF-03")
def test_proforma_prints_opted_in_particulars_and_own_answers(sample_ws):
    pid = ProfileService(sample_ws.repo).snapshot().personal.id
    sample_ws.repo.patch(pid, date_of_retirement="2042-12-31", employer_type="Central Government",
                         sc_st_status="No", basic_pay="Rs 1,00,000")
    doc = _compose(sample_ws, None, official_particulars=["date_of_birth", "date_of_retirement", "employer_type",
                                                          "sc_st_status", "basic_pay", "present_pay_level"],
                   proforma={"meets_requirements": "Yes.", "application_basis": "Absorption",
                             "equivalence_authority": ""},
                   include_employer_certificate=False)
    p = _rows(doc, "proforma_particulars")
    assert p["3. (ii) Date of retirement under Central / State Government rules"] == "31/12/2042"
    assert p["2. Date of birth (in Christian era)"]
    s = _rows(doc, "proforma_service")
    assert s[next(k for k in s if k.startswith("11."))].startswith("Central Government (")
    assert "Basic pay: Rs 1,00,000" in s[next(k for k in s if k.startswith("14."))]
    b = _rows(doc, "proforma_basis")
    assert b[next(k for k in b if k.startswith("17."))] == "Absorption"
    assert b["18. Whether belongs to SC / ST"] == "No"
    assert doc.section("employer_certificate") is None
    assert next(iter(_rows(doc, "proforma_statement").values())) == "Yes."
    assert any(row[4] for row in doc.section("experience").table.rows), "pay level printed when opted in"


@pytest.mark.req("FMT-01", "FMT-02", "DOC-06")
@pytest.mark.parametrize("mode,template", [("deputation_proforma", "dopt_proforma"),
                                           ("senior_scientist", "senior_scientist"),
                                           ("senior_graphical", "senior_graphical")])
def test_new_formats_export_and_validate(sample_ws, tmp_path, mode, template):
    lib = TemplateLibrary()
    snap = ProfileService(sample_ws.repo).snapshot()
    pending = [r.id for r in snap.facts() if r.verification == "unconfirmed" or r.confidentiality == "review"]
    sample_ws.repo.set_verification(pending, "confirmed")  # the sample keeps one item pending to demonstrate the gate
    sample_ws.repo.set_confidentiality(pending, "approved")
    vac = sample_ws.repo.list(RecordKind.VACANCY)[0]
    rec = sample_ws.repo.create(RecordKind.VARIANT, {
        "name": mode, "mode": mode, "template_id": template, "length": "full" if mode != "senior_graphical"
        else "two_pages", "vacancy_id": vac.id if mode != "senior_graphical" else ""})
    res = ExportService(sample_ws, lib, today=TODAY).export_variant(
        rec.id, ExportOptions(formats=("docx", "pdf"), folder=tmp_path, pdf_engine="builtin",
                              acknowledge_warnings=True))
    assert res.ok, (res.message, [(c.name, c.message, c.details) for c in res.report.checks] if res.report else
                    [(i.kind, i.title, i.detail) for i in res.review.items if i.blocking])
    assert {f.format for f in res.files} == {"docx", "pdf"}
    if mode == "senior_scientist":
        assert lib.get(template).ats_safe
        assert res.document.section("requirements_matrix") is not None


@pytest.mark.req("FMT-03")
def test_format_recommendations():
    dep = recommend(mode="deputation", pay_level="Level 13A", title="Scientist F")
    assert dep.mode == "deputation_proforma" and dep.template == "dopt_proforma"
    assert any("APAR" in c for c in dep.checklist) and dep.companions
    direct = recommend(mode="direct_recruitment", title="Scientist G", employer="DRDO RAC")
    assert direct.mode == "senior_scientist" and "rac.gov.in" in direct.reason
    contract = recommend(mode="contract", title="Director", notes="Serving government employees may apply.")
    assert contract.mode == "senior_scientist" and "Contract" in contract.reason
    own = recommend(mode="deputation", notes="Bio-data form: https://example.org/application_form.pdf")
    assert own.own_form_warning
    v = Vacancy(title="Scientist F", recruitment_mode="absorption")
    assert recommend_for_vacancy(v).mode == "deputation_proforma"
    assert "Advice only" not in recommend(mode="").as_text()  # wording added by the interface, not the engine


# --------------------------------------------------------------------------- charts


@pytest.mark.req("CHT-01")
def test_chart_choices_are_validated_and_resolved():
    assert charts.clean_choices({"career_timeline": "pie", "skill_levels": "auto", "x": "y"}) == \
        {"career_timeline": "pie"}
    with pytest.raises(ValueError):
        charts.clean_choices({"publications_by_year": "pie"})  # a pie of a time series is not offered
    with pytest.raises(ValueError):
        Variant(name="x", charts={"skill_levels": "radar"})
    assert charts.resolve("career_timeline", {}, {}) == "timeline"
    assert charts.resolve("career_timeline", {}, {"career_timeline": "bars"}) == "bars"
    assert charts.resolve("career_timeline", {"career_timeline": "off"}, {"career_timeline": "bars"}) == "off"
    spec = TemplateLibrary().get("senior_graphical")
    assert spec.graphics.chart_styles["publications_by_type"] == "donut"


@pytest.mark.req("CHT-02")
def test_chart_drawing_functions_return_images():
    pal = ("#1C3D6E", "#B5651D", "#2E7D6B")
    for data in (graphics.pie([("A", 3), ("B", 1)], 300, 100, pal, donut=True, centre="4"),
                 graphics.pie([("A", 3), ("B", 1)], 300, 100, pal),
                 graphics.hbars([("A", 3, "3 years"), ("B", 1, "1 year")], 300, pal),
                 graphics.columns([("2024", 2), ("2025", 3)], 300, 100, pal[0]),
                 graphics.line([("2024", 2), ("2025", 5)], 300, 100, pal[0]),
                 graphics.rating_dots(3, 60, 6, pal[0], "#DDDDDD")):
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        w, h = graphics.image_size_pt(data)
        assert w > 0 and h > 0


def _images(layout) -> list:
    from ris.rendering.layout import _walk_images

    return list(_walk_images(layout.blocks))


@pytest.mark.req("CHT-01", "CHT-03")
def test_chart_styles_change_or_remove_images_but_keep_the_facts(sample_ws):
    lib = TemplateLibrary()
    spec = lib.get("senior_graphical")
    base = _compose(sample_ws, None, mode="senior_graphical", template_id="senior_graphical", length="two_pages")
    n_default = len(_images(LayoutPlanner(base, spec).plan()))
    off = base.model_copy(update={"chart_styles": dict.fromkeys(charts.CHARTS, "off")})
    lay_off = LayoutPlanner(off, spec).plan()
    assert len(_images(lay_off)) < n_default
    text = " ".join(p.plain_text() for p in _walk_paras_all(lay_off))
    timeline = base.section("career_timeline")
    for line in timeline.items:
        assert line.split(" — ")[0] in text, "the career facts remain as text"
    alt_styles = {"career_timeline": "donut", "publications_by_year": "cumulative", "publications_by_type": "pie",
                  "skill_levels": "text", "research_metrics": "text", "expertise_years": "bars"}
    alt = base.model_copy(update={"chart_styles": alt_styles})
    lay_alt = LayoutPlanner(alt, spec).plan()
    alt_text = " ".join(p.plain_text() for p in _walk_paras_all(lay_alt))
    assert "Cumulative" in alt_text and "share of the total years" in alt_text
    assert "(Advanced)" in alt_text or "(Expert)" in alt_text or "(Proficient)" in alt_text
    # ATS-safe templates never draw charts, whatever the resume asks for.
    plain = alt.model_copy(update={"template_id": "senior_scientist"})
    assert not _images(LayoutPlanner(plain, lib.get("senior_scientist")).plan())


def _walk_paras_all(layout):
    from ris.rendering.layout import _walk_paras

    return list(_walk_paras(layout.blocks))


# --------------------------------------------------------------------------- openings feed


FEED = {"fetchedAt": "2026-10-19T01:38:56Z", "items": [
    {"id": "org-a-sci-f", "org": "Organisation A", "post": "Scientist F", "level": "13A", "mode": "Deputation",
     "area": "Defence", "location": "New Delhi", "lastDate": "2026-11-20", "eligibility": "Analogous post at Level 13A.",
     "link": "https://example.org/notice.pdf", "source": "Employment News", "verified": False, "notes": "60 days."},
    {"id": "org-b-old", "org": "Organisation B", "post": "Scientist G", "level": "14", "mode": "Direct recruitment",
     "lastDate": "2026-10-01", "link": "https://example.org/old.pdf"},
    {"id": "org-c-rolling", "org": "Organisation C", "post": "Director", "level": "other", "mode": "Contract",
     "lastDate": None, "link": "http://insecure.example.org/x"},
    {"post": "no id"},
], "sources": []}


@pytest.mark.req("FED-01")
def test_feed_item_mapping():
    v = item_to_vacancy(FEED["items"][0])
    assert v["title"] == "Scientist F" and v["employer"] == "Organisation A"
    assert v["recruitment_mode"] == "deputation" and v["pay_level"] == "Level 13A" and v["deadline"] == "2026-11-20"
    assert v["url"] == "https://example.org/notice.pdf" and v["source_file"] == "openings-feed:org-a-sci-f"
    assert "could not be opened" in v["application_notes"]
    c = item_to_vacancy(FEED["items"][2])
    assert c["url"] == "" and c["pay_level"] == "" and c["recruitment_mode"] == "contract"
    Vacancy.model_validate(v)


@pytest.mark.req("FED-01", "FED-02")
def test_feed_import_adds_updates_and_skips(repo, tmp_path):
    folder = tmp_path / "E-Diary Jobs"
    folder.mkdir()
    (folder / "e-diary-jobs-feed-2026-10-12.json").write_text("{}", encoding="utf-8")
    path = folder / "e-diary-jobs-feed-2026-10-19.json"
    path.write_text(json.dumps(FEED), encoding="utf-8")
    assert newest_feed(folder) == path
    res = import_feed(repo, folder, today=TODAY)
    assert len(res.added) == 2 and len(res.expired) == 1 and len(res.invalid) == 1
    assert "2 added" in res.summary()
    again = import_feed(repo, path, today=TODAY)
    assert not again.added and len(again.unchanged) == 2
    FEED["items"][0]["lastDate"] = "2026-11-30"  # extended
    path.write_text(json.dumps(FEED), encoding="utf-8")
    third = import_feed(repo, path, today=TODAY)
    assert third.updated == ["Scientist F"]
    vac = next(v for v in repo.list(RecordKind.VACANCY) if v.data.title == "Scientist F")
    assert vac.data.deadline == "2026-11-30"
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2]", encoding="utf-8")
    from ris.errors import RISError

    with pytest.raises(RISError):
        import_feed(repo, bad, today=TODAY)
