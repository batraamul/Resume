"""Graphical resumes: charts, bars, tiles, expertise, referees and their honesty rules."""

from __future__ import annotations

import io
from datetime import date

import pytest
from PIL import Image

from ris.composition.composer import ComposeContext, ResumeComposer, short_org
from ris.domain.enums import RecordKind
from ris.domain.models import Variant
from ris.rendering import graphics
from ris.rendering.blocks import ImageBlock
from ris.rendering.layout import plan_layout
from ris.rendering.specs import TemplateLibrary, TemplateSpec
from ris.services.profile import ProfileService

LIB = TemplateLibrary()
TODAY = date(2026, 10, 25)


def _compose(ws, mode: str, template: str, **extra):
    snap = ProfileService(ws.repo).snapshot()
    spec = LIB.get(template)
    v = Variant(name="t", mode=mode, template_id=template, length="full", **extra)
    ctx = ComposeContext(snapshot=snap, variant=v, template_id=spec.id, template_version=spec.version,
                         date_style=spec.entry.date_style, today=TODAY, is_sample=True)
    return ResumeComposer(ctx).compose(), spec, snap


def _walk_images(blocks):
    from ris.rendering.blocks import BannerBlock, ColumnsBlock, TableBlock

    for b in blocks:
        if isinstance(b, ImageBlock):
            yield b
        elif isinstance(b, TableBlock):
            for row in b.rows:
                for c in row:
                    yield from _walk_images(c.blocks)
        elif isinstance(b, ColumnsBlock):
            yield from _walk_images(b.left)
            yield from _walk_images(b.right)
        elif isinstance(b, BannerBlock):
            yield from _walk_images(b.blocks)


@pytest.mark.req("GFX-01")
def test_chart_renderers_produce_png_at_300_dpi():
    bar = graphics.rating_bar(3, 90, 5, "#0F6E5C", "#D9DEE3")
    im = Image.open(io.BytesIO(bar))
    assert im.format == "PNG" and im.size == (graphics.px(90), graphics.px(5))
    tl = graphics.timeline([("Org A", "2010-01", "2014-06", False, 4.4), ("Org B", "2014-07", "", True, 12.3)],
                           400, 150, ("#123456", "#654321"))
    assert Image.open(io.BytesIO(tl)).size == (graphics.px(400), graphics.px(150))
    st = graphics.stacked_years([("2021", "Journal", 1), ("2022", "Conference", 2)], ["Journal", "Conference"],
                                300, 120, ("#123456", "#654321"))
    assert Image.open(io.BytesIO(st)).info.get("dpi", (0,))[0] == pytest.approx(300, abs=1)


def test_short_org_labels():
    assert short_org("Halcyon Avionics Design Bureau (HADB)") == "HADB"
    assert short_org("Northwind (HP)") == "Northwind (HP)"
    assert short_org("Meridian Electronics Limited") == "MEL"


@pytest.mark.req("GFX-02")
def test_career_timeline_uses_recorded_dates_and_text_legend(sample_ws):
    doc, spec, snap = _compose(sample_ws, "graphical_profile", "graphical_profile")
    sec = doc.section("career_timeline")
    assert sec is not None and sec.chart is not None and sec.chart.kind == "timeline"
    labels = [p.label for p in sec.chart.points]
    assert labels == ["Meridian", "Halcyon ADB", "Kestrel Lab"]  # chronological, short names used
    from ris.domain import dates

    for pt in sec.chart.points:
        months = dates.conservative_months(pt.start, pt.end, pt.is_current, TODAY)
        assert pt.value == round(months / 12, 1)
    assert len(sec.items) == 3 and all(any(org in line for org in ("Meridian", "Halcyon", "Kestrel")) for line in sec.items)
    assert "years" in sec.chart.alt_text and sec.chart.caption
    layout = plan_layout(doc, spec)
    imgs = list(_walk_images(layout.blocks))
    assert any(i.data and i.alt.startswith("Career timeline") for i in imgs)
    # The legend is real text in the layout.
    texts = " ".join(p.plain_text() for p in layout.iter_paras())
    assert "Halcyon Avionics Design Bureau" in texts


@pytest.mark.req("GFX-04", "TPL-02")
def test_ats_template_never_draws_images(sample_ws):
    doc, _spec, _ = _compose(sample_ws, "graphical_profile", "graphical_profile")
    ats = LIB.get("ats_minimal")
    layout = plan_layout(doc, ats)
    assert not list(_walk_images(layout.blocks))
    texts = " ".join(p.plain_text() for p in layout.iter_paras())
    assert "Kestrel Atmospheric Instrumentation Laboratory" in texts  # timeline legend becomes plain bullets
    bad = LIB.get("graphical_profile").model_dump(mode="json")
    bad.update({"id": "bad_ats", "ats_safe": True, "tables_allowed": False})
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TemplateSpec.model_validate(bad)


@pytest.mark.req("GFX-03", "GFX-02")
def test_research_overview_counts_and_sourced_metrics(sample_ws):
    doc, spec, snap = _compose(sample_ws, "research_portfolio", "research_showcase")
    sec = doc.section("research_overview")
    assert sec is not None
    tiles = {t.label: t for t in sec.tiles}
    pubs = [p for p in snap.of(RecordKind.PUBLICATION) if p.data.status in ("published", "accepted")]
    journals = [p for p in pubs if p.data.pub_type == "journal"]
    assert tiles["Journal articles"].value == str(len(journals))
    assert "Manuscript under review" in tiles
    assert tiles["Citations"].caption.startswith("Google Scholar")
    assert sec.chart is not None and sec.chart.kind == "stacked_years"
    assert sum(p.value for p in sec.chart.points) == len(pubs)
    # Withdrawn and draft work is never counted as published.
    assert all(p.data.status not in ("withdrawn", "draft") for p in pubs)


@pytest.mark.req("PRF-21")
def test_referees_require_recorded_permission(sample_ws):
    doc, _spec, _ = _compose(sample_ws, "research_portfolio", "research_showcase")
    sec = doc.section("references")
    names = [e.title for e in sec.entries]
    assert names == ["Dr. R. Iyer (fictional)"]
    assert any("permission" in w for w in doc.warnings)
    ref = next(r for r in sample_ws.repo.list(RecordKind.REFERENCE) if r.data.name.startswith("Dr. R. Iyer"))
    sample_ws.repo.patch(ref.id, show_contact_details=False)
    doc2, _s, _ = _compose(sample_ws, "research_portfolio", "research_showcase")
    assert not doc2.section("references").entries[0].meta
    from ris.intelligence.disclosure import scan_document

    assert not [f for f in scan_document(doc) if "someone else's" in f.message]


@pytest.mark.req("PRF-20")
def test_expertise_table_and_evidence(sample_ws):
    doc, spec, _ = _compose(sample_ws, "graphical_profile", "graphical_profile")
    sec = doc.section("expertise")
    assert sec.layout == "definitions" and sec.table.rows[0][0].startswith("R&D in avionics systems")
    assert "12 years" in sec.table.rows[0][0]
    from ris.intelligence.matching import EVIDENCE_KINDS

    assert RecordKind.EXPERTISE in EVIDENCE_KINDS


@pytest.mark.req("GFX-02", "PRV-01")
def test_project_facets_respect_approved_external_wording(sample_ws):
    proj = next(p for p in sample_ws.repo.list(RecordKind.PROJECT) if p.data.approach and not p.is_confidential
                and p.id != "prj-glide" and not p.data.approved_external_description)
    doc, _s, _ = _compose(sample_ws, "research_portfolio", "research_showcase")
    entry = next(e for e in doc.section("projects").entries if e.id == proj.id)
    assert "Approach" in [label for label, _ in entry.facets]
    sample_ws.repo.patch(proj.id, approved_external_description="Approved public description only.")
    doc2, _s, _ = _compose(sample_ws, "research_portfolio", "research_showcase")
    entry2 = next(e for e in doc2.section("projects").entries if e.id == proj.id)
    assert not entry2.facets and not entry2.highlights
    assert entry2.description == "Approved public description only."


@pytest.mark.req("GFX-02")
def test_skill_bars_are_labelled_self_assessed(sample_ws):
    doc, spec, _ = _compose(sample_ws, "graphical_profile", "graphical_profile")
    layout = plan_layout(doc, spec)
    bars = [i for i in _walk_images(layout.blocks) if "self-assessed" in i.alt]
    assert bars
    texts = " ".join(p.plain_text() for p in layout.iter_paras())
    assert "own assessment" in texts


@pytest.mark.req("GFX-01", "DOC-06")
@pytest.mark.parametrize("variant_name", ["Graphical career profile (sample)", "Research portfolio (sample)"])
def test_graphical_sample_variants_export_and_validate(sample_ws, tmp_path, variant_name):
    from ris.rendering.export import ExportOptions, ExportService

    var = next(v for v in sample_ws.repo.list(RecordKind.VARIANT) if v.data.name == variant_name)
    svc = ExportService(sample_ws, LIB, today=TODAY)
    res = svc.export_variant(var.id, ExportOptions(formats=("docx", "pdf", "txt"), folder=tmp_path,
                                                   pdf_engine="builtin", acknowledge_warnings=True))
    assert res.ok, (res.message, [(c.name, c.details[:3]) for c in (res.report.failures if res.report else [])],
                    [i.detail for i in (res.review.blocking if res.review else [])])
    from docx import Document

    d = Document(str(next(f.path for f in res.files if f.format == "docx")))
    descr = [el.get("descr") for el in d.element.body.iter() if el.tag.endswith("}docPr")]
    assert any(descr), "charts and bars carry alternative text in Word"
