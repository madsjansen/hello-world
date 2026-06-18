"""Aggregér domme til pålidelighedsscorer pr. politiker og parti.

Scoren bygger KUN på verificerbare domme (Korrekt / Delvist korrekt /
Misvisende / Forkert). "Ikke verificerbar" tælles separat og påvirker ikke
scoren. Antal påstande vises altid ved siden af scoren, så en politiker der
siger lidt ikke fremstår kunstigt pålidelig.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .store import RATING_WEIGHT, VERIFIABLE_RATINGS, Store


@dataclass
class Tally:
    name: str
    party: str = ""
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    weighted_sum: float = 0.0
    verifiable: int = 0

    def add(self, rating: str) -> None:
        self.counts[rating] += 1
        if rating in VERIFIABLE_RATINGS:
            self.verifiable += 1
            self.weighted_sum += RATING_WEIGHT[rating]

    @property
    def score(self) -> Optional[float]:
        if self.verifiable == 0:
            return None
        return round(100 * self.weighted_sum / self.verifiable, 1)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "party": self.party,
            "score": self.score,
            "verifiable": self.verifiable,
            "total": sum(self.counts.values()),
            "breakdown": dict(self.counts),
        }


def build_leaderboard(store: Store) -> dict:
    """Byg leaderboard-strukturen til frontend (politikere, partier, påstande)."""
    rows = store.verdict_rows()

    politicians: dict[str, Tally] = {}
    parties: dict[str, Tally] = {}
    claims_out: list[dict] = []

    for r in rows:
        name = r["politician"] or "Ukendt"
        party = r["party"] or "Ukendt"
        rating = r["rating"]

        politicians.setdefault(name, Tally(name=name, party=party)).add(rating)
        parties.setdefault(party, Tally(name=party, party=party)).add(rating)

        try:
            sources = json.loads(r["sources"] or "[]")
        except (ValueError, TypeError):
            sources = []
        claims_out.append({
            "claim": r["claim_text"],
            "category": r["category"],
            "politician": name,
            "party": party,
            "rating": rating,
            "confidence": r["confidence"],
            "explanation": r["explanation"],
            "sources": sources,
            "meeting": {"date": r["date"], "title": r["title"]},
        })

    def ranked(d: dict[str, Tally]) -> list[dict]:
        items = [t.to_dict() for t in d.values()]
        # Sortér: dem med en score først (højest øverst), dem uden til sidst.
        items.sort(key=lambda x: (x["score"] is None, -(x["score"] or 0), -x["verifiable"]))
        return items

    return {
        "politicians": ranked(politicians),
        "parties": ranked(parties),
        "claims": claims_out,
        "ratings": ["Korrekt", "Delvist korrekt", "Misvisende", "Forkert", "Ikke verificerbar"],
    }
