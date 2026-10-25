"""User templates from JSON, configurable layout settings and template versions in saved resumes
(TPL-03, TPL-04, TPL-05)."""

from __future__ import annotations

import json
import zipfile
from datetime import date

import pytest
from docx import Document
from docx.shared import Mm

from ris.domain.enums import RecordKind
from ris.domain.models import Variant
from ris.errors import TemplateError
from ris.rendering.export import ExportOptions, ExportService
from ris.rendering.specs import TemplateLibrary
from ris.services.variants import VariantService


def _variant(ws, template_id: str):
    base = next(v for v in ws.repo.list(RecordKind.VARIANT) if v.data.mode == "defence_technical")
    data = {**base.payload(), "name": f"T {template_id}", "template_id": template_id, "length": "two_pages"}
    return ws.repo.create(RecordKind.VARIANT, Variant.model_validate(data))


@pytest.mark.req("TPL-04", "TPL-03")
def test_user_template_from_json_changes_margins_colour_and_footer(sample_ws, tmp_path):
    lib = TemplateLibrary(user_dir=tmp_path / "templates")
    copy = lib.duplicate("modern_professional", "My Maroon Layout")
    assert not copy.builtin and (tmp_path / "templates" / f"{copy.id}.json").exists()
    path = tmp_path / "templates" / f"{copy.id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["page"].update({"margin_left_mm": 25, "margin_right_mm": 22, "margin_top_mm": 20})
    raw["colours"]["accent"] = "#7A1F3D"
    raw["footer"]["page_numbers"] = "x_of_y"
    raw["version"] = "1.1.0"
    path.write_text(json.dumps(raw), encoding="utf-8")
    lib.reload()
    spec = lib.get(copy.id)
    assert spec.version == "1.1.0" and spec.colours.accent == "#7A1F3D"

    var = _variant(sample_ws, spec.id)
    out = ExportService(sample_ws, lib, today=date(2026, 10, 24)).export_variant(
        var.id, ExportOptions(formats=("docx", "pdf"), folder=tmp_path / "out", pdf_engine="builtin",
                              acknowledge_warnings=True))
    assert out.ok, out.message
    docx_path = next(f.path for f in out.files if f.format == "docx")
    section = Document(str(docx_path)).sections[0]
    assert abs(section.left_margin - Mm(25)) < Mm(0.5)
    assert abs(section.right_margin - Mm(22)) < Mm(0.5)
    assert abs(section.top_margin - Mm(20)) < Mm(0.5)
    with zipfile.ZipFile(docx_path) as z:
        xml = "".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist() if n.endswith(".xml"))
    assert "7A1F3D" in xml.upper()


@pytest.mark.req("TPL-04")
def test_invalid_user_template_reported_and_builtin_protected(tmp_path):
    folder = tmp_path / "templates"
    folder.mkdir()
    (folder / "broken.json").write_text("{ not json", encoding="utf-8")
    (folder / "bad_values.json").write_text(json.dumps({"id": "bad_values", "name": "Bad", "version": "1.0.0",
                                                        "page": {"margin_left_mm": 2}}), encoding="utf-8")
    lib = TemplateLibrary(user_dir=folder)
    ids = {t.id for t in lib.list()}
    assert "broken" not in ids and "bad_values" not in ids and len(ids) >= 15
    assert any("broken.json" in e for e in lib.load_errors)
    assert any("margin_left_mm" in e for e in lib.load_errors)
    builtin = lib.get("ats_minimal")
    with pytest.raises(TemplateError):
        lib.save_user_template(builtin)
    with pytest.raises(TemplateError):
        lib.delete_user_template("ats_minimal")


@pytest.mark.req("TPL-05")
def test_template_version_recorded_in_saved_resume_version(sample_ws, tmp_path):
    lib = TemplateLibrary()
    spec = lib.get("graphical_profile")
    var = _variant(sample_ws, spec.id)
    out = ExportService(sample_ws, lib, today=date(2026, 10, 24)).export_variant(
        var.id, ExportOptions(formats=("pdf",), folder=tmp_path, pdf_engine="builtin", acknowledge_warnings=True))
    assert out.ok, out.message
    info = VariantService(sample_ws.repo).get_info(out.version_id)
    assert info.template_id == spec.id and info.template_version == spec.version
    doc, settings = VariantService(sample_ws.repo).load_document(out.version_id)
    assert doc.template_version == spec.version
    assert settings["template_spec"]["version"] == spec.version
