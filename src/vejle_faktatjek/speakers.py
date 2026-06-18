"""Match diarization-labels ("Speaker 1") til navngivne politikere.

Stemme-baseret matching (embeddings pr. byrådsmedlem) er det rigtige langsigtede
svar, men kræver indtalte profiler. Indtil da tilbyder dette modul en simpel,
manuel kortlægning: en dict fra speaker-label til politiker-navn, fx udledt af
referatets talerækkefølge og derefter kvalitetssikret i hånden.
"""

from __future__ import annotations

from typing import Optional

from .store import Store


def apply_label_map(store: Store, meeting_id: int, label_to_name: dict[str, str]) -> int:
    """Tildel politiker-id til segmenter ud fra en {label: navn}-kortlægning.

    Navne der ikke findes i roster oprettes ikke automatisk — de skal ligge i
    ``data/politicians.json``. Returnerer antal opdaterede segmenter.
    """
    updated = 0
    for seg in store.segments(meeting_id):
        label = seg["speaker_label"]
        if not label or label not in label_to_name:
            continue
        pol = store.politician_by_name(label_to_name[label])
        if pol is None:
            continue
        store.set_segment_politician(seg["id"], pol["id"])
        updated += 1
    return updated


def speaker_label_summary(store: Store, meeting_id: int) -> dict[str, int]:
    """Tæl segmenter pr. speaker-label — hjælper med at lave kortlægningen."""
    counts: dict[str, int] = {}
    for seg in store.segments(meeting_id):
        label = seg["speaker_label"] or "Ukendt"
        counts[label] = counts.get(label, 0) + 1
    return counts
