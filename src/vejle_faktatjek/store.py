"""SQLite-lager og datamodel for pipelinen.

Tabeller:
  politicians (id, name, party, voiceprint)
  meetings    (id, date, title, source_url, audio_path, status)
  segments    (id, meeting_id, idx, speaker_label, politician_id, start, end, text)
  claims      (id, meeting_id, segment_id, politician_id, text, category, ts)
  verdicts    (id, claim_id, rating, confidence, explanation, sources, created_at)
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS politicians (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    party       TEXT NOT NULL,
    voiceprint  TEXT
);
CREATE TABLE IF NOT EXISTS meetings (
    id          INTEGER PRIMARY KEY,
    date        TEXT NOT NULL,
    title       TEXT NOT NULL,
    source_url  TEXT,
    audio_path  TEXT,
    status      TEXT NOT NULL DEFAULT 'new'
);
CREATE TABLE IF NOT EXISTS segments (
    id            INTEGER PRIMARY KEY,
    meeting_id    INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    idx           INTEGER NOT NULL,
    speaker_label TEXT,
    politician_id INTEGER REFERENCES politicians(id),
    start         REAL,
    "end"         REAL,
    text          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claims (
    id            INTEGER PRIMARY KEY,
    meeting_id    INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    segment_id    INTEGER REFERENCES segments(id),
    politician_id INTEGER REFERENCES politicians(id),
    text          TEXT NOT NULL,
    category      TEXT,
    ts            REAL
);
CREATE TABLE IF NOT EXISTS verdicts (
    id          INTEGER PRIMARY KEY,
    claim_id    INTEGER NOT NULL UNIQUE REFERENCES claims(id) ON DELETE CASCADE,
    rating      TEXT NOT NULL,
    confidence  REAL,
    explanation TEXT,
    sources     TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
"""

# Verdict-vurderinger der tæller som "verificerbare" i scoren.
VERIFIABLE_RATINGS = {"Korrekt", "Delvist korrekt", "Misvisende", "Forkert"}
# Vægt pr. dom: 1.0 = fuldt pålidelig, 0.0 = upålidelig.
RATING_WEIGHT = {
    "Korrekt": 1.0,
    "Delvist korrekt": 0.5,
    "Misvisende": 0.25,
    "Forkert": 0.0,
}


class Store:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # ---- politicians ----
    def upsert_politician(self, name: str, party: str, voiceprint: Optional[str] = None) -> int:
        with self._tx() as c:
            c.execute(
                """INSERT INTO politicians (name, party, voiceprint) VALUES (?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET party=excluded.party,
                       voiceprint=COALESCE(excluded.voiceprint, politicians.voiceprint)""",
                (name, party, voiceprint),
            )
        row = self.conn.execute("SELECT id FROM politicians WHERE name=?", (name,)).fetchone()
        return row["id"]

    def politician_by_name(self, name: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM politicians WHERE name=?", (name,)).fetchone()

    def set_voiceprint(self, politician_id: int, voiceprint_json: str) -> None:
        with self._tx() as c:
            c.execute("UPDATE politicians SET voiceprint=? WHERE id=?", (voiceprint_json, politician_id))

    def politicians_with_voiceprints(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM politicians WHERE voiceprint IS NOT NULL AND voiceprint != ''"
        ).fetchall()

    # ---- meetings ----
    def create_meeting(self, date: str, title: str, source_url: str = "") -> int:
        with self._tx() as c:
            cur = c.execute(
                "INSERT INTO meetings (date, title, source_url) VALUES (?, ?, ?)",
                (date, title, source_url),
            )
        return cur.lastrowid

    def set_meeting_audio(self, meeting_id: int, audio_path: str) -> None:
        with self._tx() as c:
            c.execute("UPDATE meetings SET audio_path=? WHERE id=?", (audio_path, meeting_id))

    def set_meeting_status(self, meeting_id: int, status: str) -> None:
        with self._tx() as c:
            c.execute("UPDATE meetings SET status=? WHERE id=?", (status, meeting_id))

    def meeting(self, meeting_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()

    # ---- segments ----
    def replace_segments(self, meeting_id: int, segments: Iterable[dict]) -> list[int]:
        ids: list[int] = []
        with self._tx() as c:
            c.execute("DELETE FROM segments WHERE meeting_id=?", (meeting_id,))
            for i, s in enumerate(segments):
                cur = c.execute(
                    """INSERT INTO segments
                       (meeting_id, idx, speaker_label, politician_id, start, "end", text)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (meeting_id, i, s.get("speaker"), s.get("politician_id"),
                     s.get("start"), s.get("end"), s["text"]),
                )
                ids.append(cur.lastrowid)
        return ids

    def segments(self, meeting_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM segments WHERE meeting_id=? ORDER BY idx", (meeting_id,)
        ).fetchall()

    def set_segment_politician(self, segment_id: int, politician_id: Optional[int]) -> None:
        with self._tx() as c:
            c.execute("UPDATE segments SET politician_id=? WHERE id=?", (politician_id, segment_id))

    # ---- claims ----
    def replace_claims(self, meeting_id: int, claims: Iterable[dict]) -> list[int]:
        ids: list[int] = []
        with self._tx() as c:
            c.execute("DELETE FROM claims WHERE meeting_id=?", (meeting_id,))
            for cl in claims:
                cur = c.execute(
                    """INSERT INTO claims
                       (meeting_id, segment_id, politician_id, text, category, ts)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (meeting_id, cl.get("segment_id"), cl.get("politician_id"),
                     cl["text"], cl.get("category"), cl.get("ts")),
                )
                ids.append(cur.lastrowid)
        return ids

    def claims(self, meeting_id: Optional[int] = None) -> list[sqlite3.Row]:
        if meeting_id is None:
            return self.conn.execute("SELECT * FROM claims").fetchall()
        return self.conn.execute(
            "SELECT * FROM claims WHERE meeting_id=?", (meeting_id,)
        ).fetchall()

    def claims_without_verdict(self, meeting_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT c.* FROM claims c
               LEFT JOIN verdicts v ON v.claim_id = c.id
               WHERE c.meeting_id=? AND v.id IS NULL""",
            (meeting_id,),
        ).fetchall()

    # ---- verdicts ----
    def save_verdict(self, claim_id: int, rating: str, confidence: float,
                     explanation: str, sources: list[dict]) -> None:
        with self._tx() as c:
            c.execute(
                """INSERT INTO verdicts (claim_id, rating, confidence, explanation, sources)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(claim_id) DO UPDATE SET rating=excluded.rating,
                       confidence=excluded.confidence, explanation=excluded.explanation,
                       sources=excluded.sources, created_at=datetime('now')""",
                (claim_id, rating, confidence, explanation, json.dumps(sources, ensure_ascii=False)),
            )

    def verdict_rows(self) -> list[sqlite3.Row]:
        """Alle domme joinet med påstand + politiker, til aggregering."""
        return self.conn.execute(
            """SELECT v.*, c.text AS claim_text, c.category, c.meeting_id,
                      p.id AS politician_id, p.name AS politician, p.party,
                      m.date, m.title
               FROM verdicts v
               JOIN claims c       ON c.id = v.claim_id
               LEFT JOIN politicians p ON p.id = c.politician_id
               LEFT JOIN meetings m    ON m.id = c.meeting_id"""
        ).fetchall()

    def close(self) -> None:
        self.conn.close()
