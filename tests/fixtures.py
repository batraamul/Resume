"""Programmatic test profiles (all fictional) for template and engine robustness tests."""

from __future__ import annotations

from ris.domain.enums import Confidentiality, Origin, RecordKind, Verification

CONF = {"verification": Verification.CONFIRMED, "confidentiality": Confidentiality.APPROVED, "origin": Origin.MANUAL}


def _c(repo, kind, data, parent=None, **kw):
    opts = dict(CONF)
    opts.update(kw)
    return repo.create(kind, data, parent_id=parent, **opts)


def build_short(repo) -> None:
    _c(repo, RecordKind.PERSONAL, {"full_name": "Short Profile", "email": "short@example.org"})
    _c(repo, RecordKind.POSITION, {"designation": "Engineer", "organisation": "Example Works", "start": "2020",
                                   "is_current": True})
    _c(repo, RecordKind.EDUCATION, {"degree": "B.Tech.", "discipline": "Electronics", "institution": "Example College",
                                    "end": "2019", "level": "bachelors"})


def build_incomplete(repo) -> None:
    _c(repo, RecordKind.PERSONAL, {"full_name": "Incomplete Person"})
    _c(repo, RecordKind.POSITION, {"designation": "Technician"})
    _c(repo, RecordKind.SKILL, {"name": "Soldering"})


def build_long(repo, positions: int = 8, bullets: int = 8, projects: int = 15, pubs: int = 40, skills: int = 120,
               activities: int = 20) -> None:
    _c(repo, RecordKind.PERSONAL, {
        "full_name": "Long Profile Example", "preferred_name": "Dr. Long Profile Example",
        "professional_title": "Principal Scientist — Avionics, Instrumentation and Applied Machine Learning",
        "email": "long.profile@example.org", "phone": "+91 00000 99999", "city": "Bengaluru", "country": "India",
        "linkedin": "https://www.linkedin.com/in/long-profile-example", "orcid": "0000-0002-1825-0097",
        "author_name_variants": ["L. P. Example"],
    })
    _c(repo, RecordKind.SUMMARY, {"focus": "general", "text": "Engineer with long experience. " * 6})
    for i in range(positions):
        start = 2024 - 3 * (i + 1)
        pos = _c(repo, RecordKind.POSITION, {
            "designation": f"Senior Engineer Grade {i + 1}", "organisation": f"Example Organisation {i + 1}",
            "division": "Systems Division", "location": "Bengaluru", "start": f"{start}-01",
            "end": "" if i == 0 else f"{start + 2}-12", "is_current": i == 0, "tools": ["Python", "C", "MATLAB"],
        })
        for j in range(bullets):
            _c(repo, RecordKind.BULLET, {"text": f"Delivered work package {j + 1} for programme {i + 1}, covering "
                                                 "design, integration, verification and documentation of embedded "
                                                 "avionics and sensor subsystems."}, parent=pos.id)
    for i in range(projects):
        _c(repo, RecordKind.PROJECT, {
            "title": f"Project {i + 1}: an exceptionally long project title describing a multi-year research and "
                     "development effort on airborne sensing, embedded processing and validation",
            "role": "Lead engineer", "start": f"{2010 + i % 14}", "end": f"{2011 + i % 14}",
            "results": "Validated prototype with documented test results.", "software": ["Python", "PyTorch"],
        })
    for i in range(pubs):
        status = ["published", "accepted", "under_review", "submitted", "draft"][i % 5]
        _c(repo, RecordKind.PUBLICATION, {
            "title": f"Study {i + 1} of lightweight networks for embedded sensing", "authors": "L. P. Example and A. Coauthor",
            "venue": f"Example Journal {i % 7}", "status": status, "date": f"{2010 + i % 15}-0{1 + i % 9}",
            "pub_type": "journal",
        })
    cats = ["electronics", "avionics", "embedded", "instrumentation", "iot", "aiml", "computer_vision", "edge_ai",
            "software", "data", "research", "leadership"]
    for i in range(skills):
        _c(repo, RecordKind.SKILL, {"name": f"Skill {i + 1}", "category": cats[i % len(cats)],
                                    "proficiency": ["working", "proficient", "advanced"][i % 3]})
    for i in range(activities):
        _c(repo, RecordKind.ACTIVITY, {"activity_type": ["committee", "award", "presentation", "membership"][i % 4],
                                       "title": f"Activity {i + 1}", "organisation": "Example Body",
                                       "start": f"{2005 + i}", "end": f"{2006 + i}"})
    for i in range(3):
        _c(repo, RecordKind.EDUCATION, {"degree": ["Ph.D.", "M.Tech.", "B.E."][i],
                                        "level": ["doctorate", "masters", "bachelors"][i],
                                        "discipline": "Electronics Engineering", "institution": "Example Institute",
                                        "end": f"{2015 - 4 * i}", "status": "completed"})


def build_unicode(repo) -> None:
    _c(repo, RecordKind.PERSONAL, {
        "full_name": "Ānanya Śarmā", "preferred_name": "Dr. Ānanya Śarmā",
        "professional_title": "Scientist — μ-controllers, σ-δ converters & signal ≥ 40 dB SNR",
        "email": "ananya@example.org", "city": "Puṇe", "country": "India",
    })
    _c(repo, RecordKind.SUMMARY, {"focus": "general", "text": "Works on “calibrated” sensors — ±0.1 °C accuracy → field use; "
                                                             "Sādhanā reviewer; naïve façade café résumé test."})
    pos = _c(repo, RecordKind.POSITION, {"designation": "Wissenschaftlerin", "organisation": "Institut für Messtechnik",
                                         "start": "2018", "is_current": True})
    _c(repo, RecordKind.BULLET, {"text": "Designed Σ-Δ ADC front-ends (Ω-level impedance, ≤ 5 µV noise) for "
                                         "atmospheric probes."}, parent=pos.id)
    _c(repo, RecordKind.EDUCATION, {"degree": "M.Sc.", "discipline": "Physik", "institution": "Universität Göttingen",
                                    "end": "2016", "level": "masters"})
    _c(repo, RecordKind.SKILL, {"name": "Signal processing (FFT, Σ-Δ)", "category": "radar_sensors"})


def default_variant(repo, mode: str, template: str, **extra):
    data = {"name": f"{template} test", "mode": mode, "template_id": template, "length": "full"}
    data.update(extra)
    return _c(repo, RecordKind.VARIANT, data)
