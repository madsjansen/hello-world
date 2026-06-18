"""Indlæs sample-data, så leaderboardet kan vises uden at køre ML/Claude.

Læser data/sample/*.json (møder med segmenter, påstande og færdige domme) og
skriver dem direkte i databasen.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import CONFIG
from .pipeline import load_roster
from .store import Store


def seed_demo(store: Store, sample_dir: Path | None = None) -> dict:
    sample_dir = sample_dir or CONFIG.sample_dir
    load_roster(store)

    meetings = json.loads((sample_dir / "meetings.json").read_text(encoding="utf-8"))
    n_claims = 0
    n_verdicts = 0

    for m in meetings:
        meeting_id = store.create_meeting(m["date"], m["title"], m.get("source_url", ""))
        store.set_meeting_status(meeting_id, "factchecked")

        segs = m.get("segments", [])
        for s in segs:
            pol = store.politician_by_name(s["politician"]) if s.get("politician") else None
            s["politician_id"] = pol["id"] if pol else None
        seg_ids = store.replace_segments(meeting_id, segs)

        claim_rows = []
        for c in m.get("claims", []):
            pol = store.politician_by_name(c["politician"]) if c.get("politician") else None
            claim_rows.append({
                "segment_id": None,
                "politician_id": pol["id"] if pol else None,
                "text": c["text"],
                "category": c.get("category"),
                "ts": c.get("ts"),
                "_verdict": c.get("verdict"),
            })
        claim_ids = store.replace_claims(meeting_id, claim_rows)
        n_claims += len(claim_ids)

        for claim_id, c in zip(claim_ids, claim_rows):
            v = c.get("_verdict")
            if not v:
                continue
            store.save_verdict(
                claim_id, v["rating"], v.get("confidence", 0.7),
                v.get("explanation", ""), v.get("sources", []),
            )
            n_verdicts += 1

    return {"meetings": len(meetings), "claims": n_claims, "verdicts": n_verdicts}
