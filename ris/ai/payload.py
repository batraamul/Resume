"""Minimal, previewable payloads for external AI requests (AI-03, DEF-05, VAC-13).

Only the selected statement and the facts recorded on that statement (and its
parent's involvement) are included, plus — optionally — one vacancy
requirement as clearly delimited, untrusted text. Confidential, review-pending
or unconfirmed records are refused. The full master profile is never sent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ris.domain.enums import Confidentiality, Verification
from ris.errors import AIProviderError
from ris.services.profile import ProfileSnapshot
from ris.storage.repository import Record

MAX_REQUIREMENT_CHARS = 600


@dataclass
class RewritePayload:
    statement: str
    involvement: str
    metrics: list[str]
    outcome: str
    tools: list[str]
    requirement: str
    record_ids: list[str]

    def facts(self) -> list[str]:
        out = [self.statement, *self.metrics, self.outcome, *self.tools]
        return [x for x in out if x]

    def to_json(self) -> str:
        return json.dumps({
            "statement": self.statement, "recorded_involvement": self.involvement,
            "recorded_metrics": self.metrics, "recorded_outcome": self.outcome, "recorded_tools": self.tools,
            "vacancy_requirement_untrusted_text": self.requirement,
        }, indent=2, ensure_ascii=False)


def build_rewrite_payload(bullet: Record, snapshot: ProfileSnapshot, requirement_text: str = "") -> RewritePayload:
    conf = snapshot.effective_confidentiality(bullet)
    if conf == Confidentiality.CONFIDENTIAL:
        raise AIProviderError("Confidential statements are never sent to an external AI provider.")
    if conf == Confidentiality.REVIEW:
        raise AIProviderError("Complete the disclosure review (approve for professional use) before sending this "
                              "statement to an external provider.")
    if snapshot.effective_verification(bullet) == Verification.UNCONFIRMED:
        raise AIProviderError("Confirm this statement before sending it to an external provider.")
    d = bullet.data
    parent = snapshot.get(bullet.parent_id) if bullet.parent_id else None
    involvement = d.involvement or (getattr(parent.data, "involvement", "") if parent is not None else "") or ""
    req = " ".join((requirement_text or "").split())[:MAX_REQUIREMENT_CHARS]
    return RewritePayload(statement=d.text, involvement=involvement, metrics=list(d.metrics), outcome=d.outcome,
                          tools=list(d.tools), requirement=req, record_ids=[bullet.id])
