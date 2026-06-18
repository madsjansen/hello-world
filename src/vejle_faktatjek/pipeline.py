"""Orkestrering: bind trinnene sammen til en kørbar pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .config import CONFIG
from .store import Store


def load_roster(store: Store, path: Optional[Path] = None) -> int:
    """Indlæs politiker-roster fra JSON ([{name, party, voiceprint?}, ...])."""
    path = path or CONFIG.politicians_path
    if not Path(path).exists():
        return 0
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for p in data:
        store.upsert_politician(p["name"], p["party"], p.get("voiceprint"))
    return len(data)


def step_fetch(store: Store, meeting_id: int, url: str) -> Path:
    from . import fetch  # tung import (yt-dlp/ffmpeg) — kun ved behov
    m = store.meeting(meeting_id)
    wav = fetch.download_audio(url, CONFIG.audio_dir, name=str(m["date"]))
    store.set_meeting_audio(meeting_id, str(wav))
    return wav


def step_transcribe(store: Store, meeting_id: int) -> int:
    from . import transcribe  # tung import (whisperx/torch) — kun ved behov
    m = store.meeting(meeting_id)
    if not m["audio_path"]:
        raise RuntimeError("Mødet har ingen lydfil. Kør fetch først.")
    segs = transcribe.transcribe(
        Path(m["audio_path"]),
        model_name=CONFIG.whisper_model,
        hf_token=CONFIG.hf_token,
    )
    segs = transcribe.merge_consecutive(segs)
    store.replace_segments(meeting_id, segs)
    store.set_meeting_status(meeting_id, "transcribed")
    return len(segs)


def step_identify_speakers(store: Store, meeting_id: int,
                           threshold: float = 0.5) -> tuple[int, dict[str, str]]:
    """Tildel politikere til segmenter via stemme-aftryk. Returnerer (antal, mapping)."""
    from .speakers import apply_label_map
    from .voiceprints import identify_meeting_speakers
    m = store.meeting(meeting_id)
    if not m["audio_path"]:
        raise RuntimeError("Mødet har ingen lydfil. Kør fetch + transcribe først.")
    mapping = identify_meeting_speakers(store, meeting_id, Path(m["audio_path"]), threshold)
    return apply_label_map(store, meeting_id, mapping), mapping


def step_extract_claims(store: Store, meeting_id: int) -> int:
    import anthropic

    from .claims import extract_claims
    client = anthropic.Anthropic(api_key=CONFIG.require_api_key())

    rows = []
    for seg in store.segments(meeting_id):
        for claim in extract_claims(seg["text"], client=client):
            rows.append({
                "segment_id": seg["id"],
                "politician_id": seg["politician_id"],
                "text": claim.text,
                "category": claim.category,
                "ts": seg["start"],
            })
    store.replace_claims(meeting_id, rows)
    store.set_meeting_status(meeting_id, "claims")
    return len(rows)


def step_factcheck(store: Store, meeting_id: int) -> int:
    import anthropic

    from .factcheck import factcheck
    client = anthropic.Anthropic(api_key=CONFIG.require_api_key())

    pending = store.claims_without_verdict(meeting_id)
    for claim in pending:
        verdict = factcheck(claim["text"], client=client)
        store.save_verdict(
            claim["id"], verdict.rating, verdict.confidence, verdict.explanation,
            [s.model_dump() for s in verdict.sources],
        )
    store.set_meeting_status(meeting_id, "factchecked")
    return len(pending)


def step_build_site(store: Store) -> Path:
    from .leaderboard import build_leaderboard
    data = build_leaderboard(store)
    out = CONFIG.site_data_path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def run_all(store: Store, url: str, date: str, title: str,
            label_map: Optional[dict[str, str]] = None) -> int:
    """Kør hele kæden for et nyt møde. Returnerer meeting_id."""
    load_roster(store)
    meeting_id = store.create_meeting(date, title, url)
    step_fetch(store, meeting_id, url)
    step_transcribe(store, meeting_id)
    # Foretræk automatisk taler-ID via stemme-aftryk; fald tilbage til en manuel
    # kortlægning hvis ingen aftryk er enrolleret.
    n_auto, _ = step_identify_speakers(store, meeting_id)
    if n_auto == 0 and label_map:
        from .speakers import apply_label_map
        apply_label_map(store, meeting_id, label_map)
    step_extract_claims(store, meeting_id)
    step_factcheck(store, meeting_id)
    step_build_site(store)
    return meeting_id
