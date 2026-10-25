"""Skill/concept taxonomy with synonym matching (loaded from config/taxonomy.json)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from ris.intelligence.text import normalize, tokens
from ris.resources import config_dir


@dataclass(frozen=True)
class Concept:
    id: str
    label: str
    category: str
    terms: tuple[str, ...]


@dataclass
class Taxonomy:
    concepts: dict[str, Concept]
    stopwords: set[str]
    degree_levels: dict[str, list[str]]
    disciplines: dict[str, list[str]]
    discipline_groups: dict[str, list[str]]
    _phrases: dict[tuple[str, ...], str] = field(default_factory=dict)
    _max_len: int = 1
    _degree_phrases: dict[tuple[str, ...], str] = field(default_factory=dict)
    _disc_phrases: dict[tuple[str, ...], str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for cid, c in self.concepts.items():
            for term in c.terms:
                key = tuple(tokens(term))
                if key:
                    # First definition wins for shared terms (deterministic: file order).
                    self._phrases.setdefault(key, cid)
                    self._max_len = max(self._max_len, len(key))
        for level, terms in self.degree_levels.items():
            for term in terms:
                key = tuple(tokens(term))
                if key:
                    self._degree_phrases.setdefault(key, level)
        for disc, terms in self.disciplines.items():
            for term in terms:
                key = tuple(tokens(term))
                if key:
                    self._disc_phrases.setdefault(key, disc)

    # ------------------------------------------------------------------ matching
    @staticmethod
    def _scan(toks: list[str], phrases: dict[tuple[str, ...], str], max_len: int) -> list[tuple[str, int, int]]:
        found: list[tuple[str, int, int]] = []
        i = 0
        n = len(toks)
        while i < n:
            matched = False
            for size in range(min(max_len, n - i), 0, -1):
                key = tuple(toks[i : i + size])
                cid = phrases.get(key)
                if cid is not None:
                    found.append((cid, i, i + size))
                    i += size
                    matched = True
                    break
            if not matched:
                i += 1
        return found

    def match(self, text: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for cid, _, _ in self._scan(tokens(text), self._phrases, self._max_len):
            counts[cid] = counts.get(cid, 0) + 1
        return counts

    def concepts_in(self, text: str) -> set[str]:
        return set(self.match(text))

    def label(self, cid: str) -> str:
        c = self.concepts.get(cid)
        return c.label if c else cid

    def category(self, cid: str) -> str:
        c = self.concepts.get(cid)
        return c.category if c else "other"

    def degree_levels_in(self, text: str) -> set[str]:
        ml = max((len(k) for k in self._degree_phrases), default=1)
        return {lvl for lvl, _, _ in self._scan(tokens(text), self._degree_phrases, ml)}

    def disciplines_in(self, text: str) -> set[str]:
        ml = max((len(k) for k in self._disc_phrases), default=1)
        return {d for d, _, _ in self._scan(tokens(text), self._disc_phrases, ml)}

    def related_disciplines(self, disc: str) -> set[str]:
        return set(self.discipline_groups.get(disc, []))

    def with_extensions(self, extensions: dict[str, list[str]]) -> Taxonomy:
        """Return a copy where user synonyms extend (or create) concepts."""
        if not extensions:
            return self
        concepts = dict(self.concepts)
        for cid, extra_terms in extensions.items():
            terms = [t for t in extra_terms if normalize(t)]
            if cid in concepts:
                c = concepts[cid]
                concepts[cid] = Concept(c.id, c.label, c.category, tuple(dict.fromkeys([*c.terms, *terms])))
            elif terms:
                concepts[cid] = Concept(cid, cid.replace("_", " ").capitalize(), "other", tuple(terms))
        return Taxonomy(concepts, set(self.stopwords), self.degree_levels, self.disciplines, self.discipline_groups)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_taxonomy(path: Path | None = None) -> Taxonomy:
    raw = _load(path or (config_dir() / "taxonomy.json"))
    concepts = {
        cid: Concept(cid, c.get("label", cid), c.get("category", "other"), tuple(c.get("terms", [])))
        for cid, c in raw.get("concepts", {}).items()
    }
    groups = {k: v for k, v in raw.get("discipline_groups", {}).items() if not k.startswith("_")}
    return Taxonomy(
        concepts=concepts,
        stopwords=set(raw.get("stopwords", [])),
        degree_levels=raw.get("degree_levels", {}),
        disciplines=raw.get("disciplines", {}),
        discipline_groups=groups,
    )


@lru_cache(maxsize=1)
def default_taxonomy() -> Taxonomy:
    return load_taxonomy()
