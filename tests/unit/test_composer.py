"""Composer rules: disclosure, privacy, nesting, status wording, provenance, ordering (PRF/PRV/DEF/VAC-11)."""

from __future__ import annotations

from datetime import date

import pytest

from ris.composition.composer import ComposeContext, ResumeComposer, claims_by_bullet
from ris.composition.modes import get_mode
from ris.composition.ordering import resolve_order
from ris.domain.enums import ClaimStatus, Confidentiality, RecordKind
from ris.domain.models import Variant
from ris.services.profile import ProfileService


def compose(ws, **variant):
    snap = ProfileService(ws.repo).snapshot()
    var_rec = ws.repo.list(RecordKind.VARIANT)[0]
    data = var_rec.payload()
    data.update(variant)
    v = Variant.model_validate(data)
    claims = claims_by_bullet(snap.kids(var_rec.id, RecordKind.CLAIM))
    ctx = ComposeContext(snapshot=snap, variant=v, template_id=v.template_id, template_version="1.0.0",
                         approved_claims=claims, is_sample=True, today=date(2026, 10, 24))
    return ResumeComposer(ctx).compose(), snap


def all_text(doc) -> str:
    return "\n".join(doc.text_fragments())


@pytest.mark.req("DEF-05", "PRF-03")
def test_confidential_and_private_excluded_by_default(sample_ws):
    doc, snap = compose(sample_ws, length="full", exclude_ids=[])
    text = all_text(doc)
    assert "SAMPLE-X" not in text and "CONFIDENTIAL-MARKER-7Q" not in text
    for secret in ("1981", "12 Example Street", "Level 12 (7th CPC)"):
        assert secret not in text
    conf_ids = {r.id for r in snap.records.values() if r.confidentiality == Confidentiality.CONFIDENTIAL}
    assert not (doc.all_source_ids() & conf_ids)


@pytest.mark.req("PRF-03")
def test_official_particulars_only_when_opted_in(sample_ws):
    doc, _ = compose(sample_ws, mode="government_biodata", template_id="government_cv",
                     official_particulars=["date_of_birth", "present_pay_level"])
    part = doc.section("particulars")
    labels = [r[0] for r in part.table.rows]
    assert "Date of birth" in labels and "Present pay level" in labels
    assert "Address for correspondence" not in labels
    assert any("12/05/1981" in r[1] for r in part.table.rows)


@pytest.mark.req("PRF-07")
def test_concurrent_assignment_nested(sample_ws):
    doc, _ = compose(sample_ws, mode="general_professional")
    exp = doc.section("experience")
    titles = [e.title for e in exp.entries]
    assert "Workshop In-charge" not in titles
    current = exp.entries[0]
    assert current.title == "Scientist E"
    child = next(c for c in current.children if c.title == "Workshop In-charge")
    assert child.status_label == "Additional charge"


@pytest.mark.req("PRF-08")
def test_education_status_labels(sample_ws):
    doc, _ = compose(sample_ws, length="full")
    edu = doc.section("education")
    phd = next(e for e in edu.entries if e.title.startswith("Ph.D."))
    assert phd.status_label == "Ongoing" and "ongoing" in phd.date_text.lower()
    assert all("Executive Programme" not in e.title for s in doc.sections for e in s.entries)
    assert any("Planned qualification hidden" in t for t in doc.trimmed)
    doc2, _ = compose(sample_ws, length="full", include_planned_education=True)
    assert "Executive Programme in Technology Management" in all_text(doc2)


@pytest.mark.req("PRF-09")
def test_publication_status_wording(sample_ws):
    doc, _ = compose(sample_ws, length="full", publication_scope="all")
    pubs = doc.section("publications")
    mans = doc.section("manuscripts")
    assert {e.status_label for e in pubs.entries} <= {"", "Accepted"}
    assert all("under review" in e.citation_rest or "in preparation" in e.citation_rest
               or "submitted" in e.citation_rest for e in mans.entries)
    text = all_text(doc)
    assert "withdrawn" not in text.lower()
    rev = next(e for e in mans.entries if e.title.startswith("Detection-aware"))
    assert "published" not in rev.citation_rest.lower()


@pytest.mark.req("PRV-01")
def test_every_bullet_traced_and_revisions_recorded(sample_ws):
    doc, snap = compose(sample_ws, length="full")
    for s in doc.sections:
        for e in s.entries:
            stack = [e]
            while stack:
                cur = stack.pop()
                assert cur.source_ids or s.key in ("publications", "manuscripts")
                for b in cur.bullets:
                    assert b.source_ids and all(snap.get(i) is not None for i in b.source_ids)
                stack.extend(cur.children)
    for rid, rev in doc.source_revisions.items():
        assert snap.get(rid).revision == rev


@pytest.mark.req("PRV-04", "PRV-06")
def test_only_approved_claims_replace_text(sample_ws):
    repo = sample_ws.repo
    var = repo.list(RecordKind.VARIANT)[0]
    bullet = next(b for b in repo.list(RecordKind.BULLET) if b.data.text.startswith("Led acceptance testing"))
    original = bullet.data.text
    pending = repo.create(RecordKind.CLAIM, {"target_bullet_id": bullet.id, "source_record_ids": [bullet.id],
                                             "original_text": original, "generated_text": "PENDING WORDING",
                                             "status": ClaimStatus.PENDING}, parent_id=var.id)
    doc, _ = compose(sample_ws)
    assert "PENDING WORDING" not in all_text(doc) and original in all_text(doc)
    repo.patch(pending.id, status="approved", approved_text="Led acceptance testing at three stations (approved).",
               approved_at="2026-10-24T00:00:00Z")
    doc, _ = compose(sample_ws)
    assert "Led acceptance testing at three stations (approved)." in all_text(doc)
    # Master profile is unchanged.
    assert repo.get(bullet.id).data.text == original


@pytest.mark.req("DEF-05")
def test_redacted_variant_public_only(sample_ws):
    doc, snap = compose(sample_ws, redacted=True, length="full")
    for rid in doc.all_source_ids():
        rec = snap.get(rid)
        if rec.kind in (RecordKind.PERSONAL,):
            continue
        assert snap.effective_confidentiality(rec) == Confidentiality.PUBLIC, rec.title


@pytest.mark.req("PRF-04")
def test_contact_visibility_per_variant(sample_ws):
    doc, _ = compose(sample_ws, contact_fields=["email"])
    assert [c.key for c in doc.contacts] == ["email"]
    doc2, _ = compose(sample_ws, mode="scientific_research", contact_fields=[])
    assert "orcid" in [c.key for c in doc2.contacts]


@pytest.mark.req("VAC-11")
def test_section_order_adapts():
    mode = get_mode("general_professional")
    base = resolve_order(mode)
    research = resolve_order(mode, emphasis={"research": 0.5})
    assert research.index("publications") < base.index("publications")
    assert research.index("publications") < research.index("experience")
    lead = resolve_order(mode, emphasis={"leadership": 0.4})
    assert lead.index("leadership") == lead.index("experience") + 1
    user = resolve_order(mode, user_order=["education", "summary"], hidden=["skills"])
    assert user[:2] == ["education", "summary"] and "skills" not in user and "experience" in user
    gov = resolve_order(get_mode("government_biodata"), emphasis={"research": 0.9})
    assert gov == list(get_mode("government_biodata").section_order)


@pytest.mark.req("PRF-13")
def test_custom_section_included_when_requested(sample_ws):
    sec = sample_ws.repo.list(RecordKind.CUSTOM_SECTION)[0]
    doc, _ = compose(sample_ws, section_order=[f"custom:{sec.id}", "summary"])
    assert doc.sections[0].title == "Professional Development"


def test_mode_budgets_trim_and_report(sample_ws):
    doc, _ = compose(sample_ws, length="one_page", mode="executive_summary")
    exp = doc.section("experience")
    assert len(exp.entries[0].bullets) <= 4
    assert doc.trimmed, "one-page mode must report what it left out"


def test_sample_footer_note(sample_ws):
    doc, _ = compose(sample_ws)
    assert doc.is_sample and "Fictional sample" in doc.footer_note
