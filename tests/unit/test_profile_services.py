from datetime import date

import pytest

from ris.domain.enums import Confidentiality, Origin, RecordKind, Verification
from ris.errors import ValidationFailed
from ris.services import completeness
from ris.services.chronology import check_chronology
from ris.services.duplicates import find_duplicate_groups, match_candidate
from ris.services.profile import ProfileService


@pytest.fixture
def svc(repo):
    return ProfileService(repo)


@pytest.mark.req("DEF-04")
def test_effective_confidentiality_inherits(svc, repo):
    pos = repo.create(RecordKind.POSITION, {"designation": "Scientist"}, confidentiality=Confidentiality.CONFIDENTIAL)
    b = repo.create(RecordKind.BULLET, {"text": "x"}, parent_id=pos.id, confidentiality=Confidentiality.PUBLIC)
    snap = svc.snapshot()
    assert snap.effective_confidentiality(snap.get(b.id)) == Confidentiality.CONFIDENTIAL


@pytest.mark.req("PRF-15")
def test_confirm_with_evidence_requires_note(svc, repo):
    p = repo.create(RecordKind.PROJECT, {"title": "P"}, origin=Origin.IMPORTED)
    assert p.verification == Verification.UNCONFIRMED
    with pytest.raises(ValidationFailed):
        svc.confirm([p.id], with_evidence=True)
    repo.patch(p.id, evidence="Office order 12/2024")
    svc.confirm([p.id], with_evidence=True)
    assert repo.get(p.id).verification == Verification.EVIDENCED
    assert svc.awaiting_confirmation() == []


@pytest.mark.req("PRF-18", "PRV-05")
def test_chronology_checks(svc, repo):
    a = repo.create(RecordKind.POSITION, {"designation": "A", "start": "2010-01", "end": "2015-12"})
    b = repo.create(RecordKind.POSITION, {"designation": "B", "start": "2014-01", "end": "2018-12"})
    c = repo.create(RecordKind.POSITION, {"designation": "C", "start": "2019-01", "is_current": True})
    repo.create(RecordKind.POSITION, {"designation": "D", "start": "2020-01", "is_current": True})
    repo.create(RecordKind.ASSIGNMENT, {"title": "In-charge", "start": "2018-01", "is_current": True}, parent_id=c.id)
    repo.create(RecordKind.EDUCATION, {"degree": "Ph.D.", "status": "completed", "end": "2099"})
    repo.create(RecordKind.EDUCATION, {"degree": "M.Tech", "status": "ongoing", "end": "2001"})
    repo.create(RecordKind.PUBLICATION, {"title": "Future paper", "status": "published", "date": "2099"})
    repo.create(RecordKind.SKILL, {"name": "Python", "years_experience": 40})
    issues = check_chronology(svc.snapshot(), today=date(2026, 10, 1))
    msgs = " | ".join(i.message for i in issues)
    assert "overlap" in msgs and a.id in {i.record_id for i in issues} and b.id in {i.record_id for i in issues}
    assert "More than one current position" in msgs
    assert "starts before its parent position" in msgs
    assert "completion date is in the future" in msgs
    assert "ongoing but its completion date has passed" in msgs
    assert "published with a future date" in msgs
    assert "more than your recorded career length" in msgs


@pytest.mark.req("PRF-17")
def test_duplicates(repo):
    p1 = repo.create(RecordKind.PUBLICATION, {"title": "Lightweight CNN for drone image super-resolution", "doi": "10.1/abc"})
    repo.create(RecordKind.PUBLICATION, {"title": "Something else entirely"})
    m = match_candidate(RecordKind.PUBLICATION, {"title": "Different title", "doi": "10.1/ABC"}, repo.list())
    assert m and m.record.id == p1.id and m.reason == "same DOI"
    m2 = match_candidate(RecordKind.PUBLICATION, {"title": "Lightweight CNN for drone-image super resolution"}, repo.list())
    assert m2 and m2.record.id == p1.id
    s = repo.create(RecordKind.SKILL, {"name": "Deep learning", "aliases": ["DL"]})
    assert match_candidate(RecordKind.SKILL, {"name": "DL"}, repo.list()).record.id == s.id
    repo.create(RecordKind.SKILL, {"name": "deep-learning"})
    groups = find_duplicate_groups(repo.list(RecordKind.SKILL))
    assert len(groups) == 1 and len(groups[0]) == 2


@pytest.mark.req("PRF-16", "UX-05")
def test_completeness_is_real(svc, repo):
    empty = completeness.compute(svc.snapshot())
    assert empty.overall < 20 and empty.fact_count == 0
    assert "Add your full name" in empty.top_actions(10)
    svc.ensure_personal()
    repo.update(repo.singleton(RecordKind.PERSONAL).id, {"full_name": "A B", "professional_title": "Scientist",
                                                         "email": "a@example.org", "phone": "+91 11 1234 5678",
                                                         "city": "Delhi", "country": "India"})
    after = completeness.compute(svc.snapshot())
    personal = next(s for s in after.sections if s.key == "personal")
    assert personal.percent == 100 and after.overall > empty.overall
