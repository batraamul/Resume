from datetime import date

import pytest
from pydantic import ValidationError

from ris.domain import dates
from ris.domain.enums import Confidentiality, Origin, RecordKind
from ris.domain.models import Bullet, Education, PersonalInfo, Position, Publication, Skill, Variant
from ris.domain.registry import default_confidentiality, field_metas, private_fields


class TestPartialDates:
    @pytest.mark.parametrize(
        "text,iso",
        [
            ("2019", "2019"),
            ("2019-3", "2019-03"),
            ("2019-03-15", "2019-03-15"),
            ("03/2019", "2019-03"),
            ("15/03/2019", "2019-03-15"),
            ("2019/03", "2019-03"),
            ("Mar 2019", "2019-03"),
            ("March 2019", "2019-03"),
            ("15 March 2019", "2019-03-15"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_parse_variants(self, text, iso):
        assert dates.normalize(text) == iso

    @pytest.mark.parametrize("bad", ["2019-13", "31/02/2020", "yesterday", "1800", "2019-02-30"])
    def test_rejects_invalid(self, bad):
        with pytest.raises(ValueError):
            dates.normalize(bad)

    def test_format_range(self):
        assert dates.format_range("2019-03", "", True) == "Mar 2019 – Present"
        assert dates.format_range("2015", "2019", False, style="year") == "2015 – 2019"
        assert dates.format_range("2019", "2019") == "2019"
        assert dates.format_range("", "2020") == "2020"
        assert dates.format_range("2019-03", "2020-01", style="mm_yyyy") == "03/2019 – 01/2020"

    def test_conservative_months_never_overstates(self):
        # Year-only start 2015 is treated as Dec 2015; year-only end 2019 as Jan 2019.
        assert dates.conservative_months("2015", "2019", False) == 36
        assert dates.conservative_months("2015-01", "2015-12", False) == 10
        assert dates.conservative_months("2020-01", "", True, today=date(2021, 1, 15)) == 11
        assert dates.conservative_months("", "2019", False) is None


@pytest.mark.req("PRF-02", "PRF-06")
class TestModels:
    def test_personal_validation(self):
        p = PersonalInfo(full_name="Test User", email="t@example.org", linkedin="linkedin.com/in/test",
                         orcid="https://orcid.org/0000-0002-1825-0097", phone="+91 11 2345 6789")
        assert p.linkedin == "https://linkedin.com/in/test"
        assert p.orcid == "0000-0002-1825-0097"
        with pytest.raises(ValidationError):
            PersonalInfo(email="not-an-email")
        with pytest.raises(ValidationError):
            PersonalInfo(orcid="1234")
        with pytest.raises(ValidationError):
            PersonalInfo(phone="call me")

    def test_position_dates(self):
        pos = Position(designation="Scientist", organisation="Lab", start="2019-03", end="2021", is_current=True)
        assert pos.end == ""  # current role has no end
        with pytest.raises(ValidationError):
            Position(designation="X", start="2020", end="2019")

    def test_lists_and_tags_coerced(self):
        b = Bullet(text="Did a thing", metrics="4x smaller\n\n20 ms latency", tools="PyTorch, TensorRT; ONNX")
        assert b.metrics == ["4x smaller", "20 ms latency"]
        assert b.tools == ["PyTorch", "TensorRT", "ONNX"]

    def test_unknown_fields_preserved(self):
        e = Education.model_validate({"degree": "M.Tech", "future_field": {"x": 1}})
        assert e.model_dump()["future_field"] == {"x": 1}

    def test_doi_normalised(self):
        p = Publication(title="T", doi="https://doi.org/10.1109/ACCESS.2024.1")
        assert p.doi == "10.1109/ACCESS.2024.1"
        with pytest.raises(ValidationError):
            Publication(title="T", doi="abc")

    def test_skill_bounds(self):
        with pytest.raises(ValidationError):
            Skill(name="X", years_experience=99)
        with pytest.raises(ValidationError):
            Skill(name="X", last_used="20")

    def test_variant_bounds(self):
        with pytest.raises(ValidationError):
            Variant(font_scale=2)
        assert Variant(page_size="letter").page_size == "Letter"


@pytest.mark.req("PRF-03", "DEF-04")
def test_private_fields_and_default_classification():
    priv = private_fields(PersonalInfo)
    assert {"home_address", "date_of_birth", "present_pay_level"} <= priv
    assert "email" not in priv
    assert default_confidentiality(RecordKind.PROJECT, Origin.MANUAL) == Confidentiality.REVIEW
    assert default_confidentiality(RecordKind.EDUCATION, Origin.IMPORTED) == Confidentiality.REVIEW
    assert default_confidentiality(RecordKind.EDUCATION, Origin.MANUAL) == Confidentiality.APPROVED


def test_field_metas_for_ui():
    metas = field_metas(Position)
    names = [m.name for m in metas]
    assert names[-1] == "custom"
    emp = next(m for m in metas if m.name == "employment_type")
    assert emp.widget == "choice" and emp.enum_type is not None
    inv = next(m for m in field_metas(Bullet) if m.name == "involvement")
    assert inv.optional_enum
