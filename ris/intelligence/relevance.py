"""Deterministic relevance model used to rank and select profile evidence.

Weights come from a career target (preset keywords) and/or a vacancy's
requirements. A record's relevance is the weighted share of target concepts
and keywords it mentions. Scores are for ordering only; they are never shown
as probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ris.domain.enums import RecordKind
from ris.intelligence.taxonomy import Taxonomy, default_taxonomy
from ris.intelligence.text import content_tokens
from ris.storage.repository import Record


@dataclass
class RelevanceModel:
    taxonomy: Taxonomy
    concept_weights: dict[str, float] = field(default_factory=dict)
    keyword_weights: dict[str, float] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> RelevanceModel:
        return cls(default_taxonomy())

    @property
    def is_empty(self) -> bool:
        return not self.concept_weights and not self.keyword_weights

    @classmethod
    def from_weighted_texts(cls, texts: list[tuple[str, float]], taxonomy: Taxonomy | None = None) -> RelevanceModel:
        tax = taxonomy or default_taxonomy()
        cw: dict[str, float] = {}
        kw: dict[str, float] = {}
        for text, weight in texts:
            if not text or weight <= 0:
                continue
            for cid in tax.concepts_in(text):
                cw[cid] = max(cw.get(cid, 0.0), weight)
            for tok in content_tokens(text, tax.stopwords):
                kw[tok] = max(kw.get(tok, 0.0), weight * 0.5)
        return cls(tax, cw, kw)

    def merged(self, other: RelevanceModel) -> RelevanceModel:
        cw = dict(self.concept_weights)
        for k, v in other.concept_weights.items():
            cw[k] = max(cw.get(k, 0.0), v)
        kw = dict(self.keyword_weights)
        for k, v in other.keyword_weights.items():
            kw[k] = max(kw.get(k, 0.0), v)
        return RelevanceModel(self.taxonomy, cw, kw)

    # ------------------------------------------------------------------ scoring
    def score_text(self, text: str) -> float:
        if self.is_empty or not text:
            return 0.0
        concepts = self.taxonomy.concepts_in(text)
        toks = set(content_tokens(text, self.taxonomy.stopwords))
        c_total = sum(self.concept_weights.values()) or 1.0
        k_total = sum(self.keyword_weights.values()) or 1.0
        c_score = sum(w for c, w in self.concept_weights.items() if c in concepts) / c_total
        k_score = sum(w for k, w in self.keyword_weights.items() if k in toks) / k_total
        # Concepts dominate; keywords break ties and catch domain-specific terms.
        return round(0.8 * c_score + 0.2 * k_score, 6)

    def matched_concepts(self, text: str) -> list[str]:
        concepts = self.taxonomy.concepts_in(text)
        return sorted((c for c in self.concept_weights if c in concepts), key=lambda c: (-self.concept_weights[c], c))

    def record_text(self, record: Record, children: list[Record] | None = None) -> str:
        parts = [record.data.display_title(), record.data.search_text()]
        if record.kind == RecordKind.SKILL:
            parts.extend(record.data.aliases)
        for ch in children or []:
            parts.append(ch.data.search_text())
        return "\n".join(p for p in parts if p)

    def score_record(self, record: Record, children: list[Record] | None = None) -> float:
        return self.score_text(self.record_text(record, children))
