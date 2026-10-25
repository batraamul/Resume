"""AI provider interface and the default offline rules provider (AI-01, AI-04)."""

from __future__ import annotations

from typing import Protocol

from ris.ai.payload import RewritePayload
from ris.intelligence.claims import validate_claim
from ris.intelligence.rewriting import RewriteSuggestion, rewrite_bullet
from ris.storage.repository import Record


class AIProvider(Protocol):
    name: str
    is_generative: bool
    sends_data: bool

    def describe(self) -> str: ...


class OfflineRulesProvider:
    """Deterministic rules engine. Works offline; never generates new facts."""

    name = "rules-engine"
    is_generative = False
    sends_data = False

    def describe(self) -> str:
        return "Built-in rules engine (offline, deterministic — not a generative AI model)."

    def rewrite(self, bullet: Record, parent: Record | None = None, *, translate: bool = False,
                glossary: dict[str, str] | None = None) -> RewriteSuggestion:
        return rewrite_bullet(bullet, parent, translate=translate, glossary=glossary)


def suggestion_from_external(payload: RewritePayload, revised: str, notes: str, generator: str) -> RewriteSuggestion:
    """Wrap an external model's text as an untrusted suggestion validated against recorded facts."""
    revised = " ".join((revised or "").split())
    check = validate_claim(payload.statement, revised, payload.facts(), payload.involvement or None)
    return RewriteSuggestion(
        original=payload.statement, revised=revised,
        source_facts=[f"Statement: {payload.statement}"] + [f"Metric: {m}" for m in payload.metrics]
        + ([f"Outcome: {payload.outcome}"] if payload.outcome else []) + ([f"Tools: {', '.join(payload.tools)}"]
                                                                           if payload.tools else []),
        assumptions=[f"Suggested by {generator}. Treat as a draft; it may be wrong."] + ([notes[:300]] if notes else []),
        missing_metrics=[], changes=["External AI suggestion."], check=check, source_ids=list(payload.record_ids),
    )
