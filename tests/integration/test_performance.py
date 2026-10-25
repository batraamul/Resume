"""Large-profile performance (MNT-01). Timings are recorded in build/test-results/performance.json."""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

import pytest

from ris.composition.composer import ComposeContext, ResumeComposer
from ris.domain.enums import Confidentiality, RecordKind, Verification
from ris.domain.models import Requirement, Variant
from ris.intelligence.analysis import analyse
from ris.rendering.export import ExportService
from ris.rendering.layout import plan_layout
from ris.rendering.pdf_renderer import PdfRenderer
from ris.rendering.specs import TemplateLibrary
from ris.services.profile import ProfileService

ROOT = Path(__file__).resolve().parents[2]
SKILL_CATS = ["electronics", "avionics", "embedded", "iot", "aiml", "computer_vision", "software", "data", "research"]


def _build_large(repo) -> None:
    ok = {"verification": Verification.CONFIRMED, "confidentiality": Confidentiality.APPROVED}
    with repo.db.transaction():
        repo.create(RecordKind.PERSONAL, {"full_name": "Large Profile Example", "email": "large@example.org",
                                          "phone": "+91 00000 99999", "city": "Pune", "country": "India"}, **ok)
        repo.create(RecordKind.SUMMARY, {"text": "Engineer with a very large record for performance testing."}, **ok)
        for i in range(40):
            y = 1986 + i
            pos = repo.create(RecordKind.POSITION, {"designation": f"Engineer grade {i}", "organisation": f"Org {i % 7}",
                                                    "start": f"{y}-01", "end": f"{y}-12"}, **ok)
            for j in range(10):
                repo.create(RecordKind.BULLET, {"text": f"Delivered avionics test item {i}-{j} using Python and MQTT."},
                            parent_id=pos.id, **ok)
        for i in range(300):
            repo.create(RecordKind.PROJECT, {"title": f"Project {i}: embedded vision prototype",
                                             "problem": "Needed real-time image enhancement on embedded GPUs.",
                                             "approach": "Pruned residual networks deployed with TensorRT.",
                                             "results": "Prototype demonstrated in laboratory trials.",
                                             "start": f"{1990 + i % 35}-03", "end": f"{1990 + i % 35}-11"}, **ok)
        for i in range(400):
            repo.create(RecordKind.SKILL, {"name": f"Skill {i}", "category": SKILL_CATS[i % len(SKILL_CATS)],
                                           "proficiency": ["working", "proficient", "advanced"][i % 3]}, **ok)
        for i in range(300):
            repo.create(RecordKind.PUBLICATION, {"title": f"Paper {i} on aerial image enhancement",
                                                 "authors": "L. Example and A. Coauthor", "venue": "Example Journal",
                                                 "pub_type": "journal" if i % 2 else "conference",
                                                 "status": "published", "date": f"{1995 + i % 30}-05"}, **ok)


@pytest.mark.slow
@pytest.mark.req("MNT-01")
def test_large_profile_performance(workspace, tmp_path):
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    _build_large(workspace.repo)
    timings["create_1442_records_s"] = time.perf_counter() - t0
    assert workspace.repo.count() == 1442  # 40 positions, 400 statements, 300 projects, 400 skills, 300 papers

    t0 = time.perf_counter()
    snap = ProfileService(workspace.repo).snapshot()
    timings["snapshot_s"] = time.perf_counter() - t0

    from ris.domain.models import Vacancy

    vac = Vacancy(title="Scientist", raw_text="Essential: degree in electronics. Desirable: avionics, embedded vision.",
                  requirements=[Requirement(text="Experience in avionics testing", category="technical"),
                                Requirement(text="Publications in image enhancement", category="research"),
                                Requirement(text="Degree in electronics engineering", category="mandatory_qualification",
                                            mandatory=True)])
    t0 = time.perf_counter()
    res = analyse(snap, vac, today=date(2026, 10, 25))
    timings["vacancy_analysis_s"] = time.perf_counter() - t0
    assert res.results

    lib = TemplateLibrary()
    for mode, tpl, length in (("academic_cv", "academic_extended", "full"),
                              ("research_portfolio", "research_showcase", "full"),
                              ("general_professional", "engineering_professional", "two_pages")):
        spec = lib.get(tpl)
        v = Variant(name="perf", mode=mode, template_id=tpl, length=length)
        t0 = time.perf_counter()
        doc = ResumeComposer(ComposeContext(snapshot=snap, variant=v, template_id=tpl,
                                            template_version=spec.version, today=date(2026, 10, 25))).compose()
        timings[f"compose_{mode}_s"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        layout = plan_layout(doc, spec)
        timings[f"layout_{mode}_s"] = time.perf_counter() - t0
        if length == "full":
            t0 = time.perf_counter()
            _data, r = PdfRenderer(layout).render_bytes()
            timings[f"pdf_{mode}_s"] = time.perf_counter() - t0
            timings[f"pdf_{mode}_pages"] = r.page_count
        else:
            t0 = time.perf_counter()
            svc = ExportService(workspace, lib)
            fitted, pages = svc.fit(doc, spec, 2)
            timings["fit_two_pages_s"] = time.perf_counter() - t0
            assert pages <= 2
    out = ROOT / "build" / "test-results"
    out.mkdir(parents=True, exist_ok=True)
    (out / "performance.json").write_text(json.dumps({k: round(v, 3) for k, v in timings.items()}, indent=1))
    # Generous ceilings: the point is to detect pathological regressions, not to benchmark hardware.
    assert timings["snapshot_s"] < 10
    assert timings["vacancy_analysis_s"] < 20
    assert all(v < 20 for k, v in timings.items() if k.startswith("compose_"))
    assert timings["fit_two_pages_s"] < 120
