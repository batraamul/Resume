"""Achievement rewriting and claim validation (VAC-10, PRV-02..05, DEF-03, PRF-12)."""

from __future__ import annotations

import pytest

from ris.domain.enums import RecordKind
from ris.intelligence.claims import validate_claim
from ris.intelligence.rewriting import draft_summary, rewrite_bullet
from ris.services.profile import ProfileService


def _bullet(repo, text, involvement=None, parent_inv="participating", **extra):
    proj = repo.create(RecordKind.PROJECT, {"title": "P", "involvement": parent_inv})
    data = {"text": text, **extra}
    if involvement:
        data["involvement"] = involvement
    b = repo.create(RecordKind.BULLET, data, parent_id=proj.id)
    return b, proj


@pytest.mark.req("PRV-05")
class TestClaimValidation:
    def test_new_numbers_flagged(self):
        chk = validate_claim("Built a test rig.", "Built a test rig that cut test time by 40%.")
        assert chk.material and "40" in chk.new_numbers
        assert any("outcome" in f for f in chk.flags)

    def test_numbers_from_sources_allowed(self):
        chk = validate_claim("Built a test rig.", "Built a test rig (40% faster tests).", ["40% faster tests"])
        assert not chk.new_numbers

    def test_superlatives_and_inflation(self):
        chk = validate_claim("Supported the radar trials.", "Spearheaded world-class radar trials.",
                             involvement="supporting")
        assert any("world-class" in f for f in chk.flags)
        assert any("leading role" in f for f in chk.flags)

    def test_qualification_deployment_clearance_publication(self):
        chk = validate_claim("Developed a detector.", "Developed a detector deployed in operational use; PhD research.")
        text = " ".join(chk.flags)
        assert "deployment" in text and "qualification" in text
        chk2 = validate_claim("Paper on pruning.", "Paper on pruning published in IEEE Access.", publication_status="under_review")
        assert any("published" in f for f in chk2.flags)
        assert any("IEEE" in t for t in chk2.new_terms)
        chk3 = validate_claim("Worked on avionics.", "Worked on avionics as a security clearance holder.")
        assert any("clearance" in f for f in chk3.flags)

    def test_identical_is_clean(self):
        assert validate_claim("Calibrated sensors.", "Calibrated sensors.").ok


@pytest.mark.req("VAC-10", "PRF-12")
class TestRewriting:
    def test_weak_opening_uses_recorded_involvement(self, repo):
        b, p = _bullet(repo, "Responsible for the calibration schedule of field sensors", involvement="coordinating")
        s = rewrite_bullet(b, p)
        assert s.revised.startswith("Coordinated the calibration schedule")
        assert not s.material, s.check.flags
        assert s.original == "Responsible for the calibration schedule of field sensors"
        assert s.missing_metrics and s.source_facts[0].startswith("Statement:")

    def test_no_inflation_for_supporting_role(self, repo):
        b, p = _bullet(repo, "Responsible for designing the antenna mount", involvement="supporting")
        s = rewrite_bullet(b, p)
        assert not s.revised.startswith("Designed")
        assert s.revised.startswith("Supported designing")
        assert "Led" not in s.revised

    def test_gerund_to_past_for_individual_work(self, repo):
        b, p = _bullet(repo, "worked on developing a telemetry decoder", involvement="individual")
        s = rewrite_bullet(b, p)
        assert s.revised == "Developed a telemetry decoder."

    def test_metrics_outcome_tools_added_from_record(self, repo):
        b, p = _bullet(repo, "Optimised the detection model", involvement="individual",
                       metrics=["3× faster on Jetson Xavier NX"], outcome="Real-time processing in the field kit",
                       tools=["TensorRT"])
        s = rewrite_bullet(b, p)
        assert "3× faster on Jetson Xavier NX" in s.revised and "TensorRT" in s.revised
        assert "real-time processing" in s.revised.lower()
        assert not s.check.new_numbers, s.check.flags
        assert not s.missing_metrics

    def test_filler_removed(self, repo):
        b, p = _bullet(repo, "Successfully utilized various tools in order to automate reports", involvement="individual")
        s = rewrite_bullet(b, p)
        assert "Successfully" not in s.revised and "utilized" not in s.revised and "in order to" not in s.revised

    @pytest.mark.req("DEF-03")
    def test_glossary_translation_is_explicit(self, repo):
        b, p = _bullet(repo, "Maintained radiosonde ground receiving system at two stations", involvement="leading")
        plain = rewrite_bullet(b, p)
        assert "balloon-borne" not in plain.revised
        tr = rewrite_bullet(b, p, translate=True)
        assert "balloon-borne atmospheric sensor and telemetry package" in tr.revised
        assert any("glossary" in c.lower() for c in tr.changes)
        assert not tr.check.new_numbers

    def test_master_profile_not_modified(self, repo):
        b, p = _bullet(repo, "Responsible for testing radios", involvement="leading")
        rewrite_bullet(b, p)
        assert repo.get(b.id).data.text == "Responsible for testing radios"


def test_draft_summary_uses_confirmed_records_only(sample_ws):
    s = draft_summary(ProfileService(sample_ws.repo).snapshot())
    assert "years of recorded experience" in s.revised and "Scientist E" in s.revised
    import re

    from ris.domain.enums import RecordKind as RK
    from ris.intelligence.matching import EvidenceMatcher

    snap = ProfileService(sample_ws.repo).snapshot()
    years = EvidenceMatcher(snap).total_experience_months(confirmed_only=True) // 12
    assert f"{years}+ years" in s.revised
    assert any(f"at least {years} years" in f for f in s.source_facts)
    assert "AI / machine learning" in s.revised or "machine learning" not in s.revised  # acronyms keep their case
    # An unconfirmed (preliminary) position must not change the figure.
    sample_ws.repo.create(RK.POSITION, {"designation": "Unverified early post", "organisation": "Example",
                                        "start": "1980-01", "end": "1999-12"}, verification="unconfirmed")
    s2 = draft_summary(ProfileService(sample_ws.repo).snapshot())
    assert re.search(rf"\b{years}\+ years", s2.revised)
