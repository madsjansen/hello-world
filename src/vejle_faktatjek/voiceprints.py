"""Stemme-aftryk til automatisk taler-identifikation.

Idé: enrollér hver politiker én gang fra et stykke lyd hvor man ved hvem der
taler → gem et stemme-embedding (ECAPA-TDNN) på politikeren. Ved hvert nyt møde
beregnes et embedding pr. diarization-klynge ("SPEAKER_00", …) og matches mod de
gemte aftryk via cosine-lighed. Klynger over en tærskel tildeles den nærmeste
politiker; resten forbliver ukendte (og kan rettes manuelt).

Embedding-modellen er en tung, valgfri afhængighed — importeres først ved kald.
Standard er SpeechBrain ECAPA-TDNN (``speechbrain/spkrec-ecapa-voxceleb``), som
ikke kræver gated Hugging Face-adgang.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .store import Store

# Empirisk cosine-tærskel for "samme taler" med L2-normaliserede ECAPA-embeddings.
# Juster på egne data: højere = færre fejl-match, flere ukendte.
DEFAULT_THRESHOLD = 0.5

_MODEL = None


def _load_model():
    global _MODEL
    if _MODEL is None:
        try:
            from speechbrain.inference.speaker import EncoderClassifier  # type: ignore
        except ImportError as e:  # pragma: no cover - valgfri pakke
            raise RuntimeError(
                "speechbrain/torchaudio er ikke installeret. Afkommentér dem i "
                "requirements.txt og kør `pip install -r requirements.txt`."
            ) from e
        _MODEL = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            run_opts={"device": "cpu"},
        )
    return _MODEL


def _embed_spans(audio_path: Path, spans: Optional[list[tuple[float, float]]]):
    """Beregn ét L2-normaliseret embedding ud fra de(t) givne lyd-udsnit.

    ``spans`` er en liste af (start, slut) i sekunder; None = hele filen.
    """
    import numpy as np  # type: ignore
    import torchaudio  # type: ignore

    model = _load_model()
    wav, sr = torchaudio.load(str(audio_path))
    if wav.shape[0] > 1:  # downmix til mono
        wav = wav.mean(dim=0, keepdim=True)
    if sr != 16000:
        wav = torchaudio.functional.resample(wav, sr, 16000)
        sr = 16000

    if not spans:
        chunks = [wav]
    else:
        chunks = []
        for start, end in spans:
            a, b = int(start * sr), int(end * sr)
            seg = wav[:, a:b]
            if seg.shape[1] > sr * 0.3:  # spring meget korte udsnit over
                chunks.append(seg)
        if not chunks:
            chunks = [wav]

    embs = []
    for ch in chunks:
        e = model.encode_batch(ch).squeeze().detach().cpu().numpy()
        embs.append(e)
    emb = np.mean(embs, axis=0)
    return emb / (np.linalg.norm(emb) + 1e-9)


def enroll_politician(store: Store, name: str, audio_path: Path,
                      spans: Optional[list[tuple[float, float]]] = None) -> int:
    """Beregn og gem et stemme-aftryk for en politiker. Returnerer dimensionen."""
    pol = store.politician_by_name(name)
    if pol is None:
        raise ValueError(f"Ukendt politiker: {name!r}. Tilføj til data/politicians.json først.")
    emb = _embed_spans(Path(audio_path), spans)
    store.set_voiceprint(pol["id"], json.dumps(emb.tolist()))
    return int(emb.shape[0])


def load_voiceprints(store: Store) -> dict[str, list]:
    return {p["name"]: json.loads(p["voiceprint"]) for p in store.politicians_with_voiceprints()}


def identify_meeting_speakers(store: Store, meeting_id: int, audio_path: Path,
                              threshold: float = DEFAULT_THRESHOLD) -> dict[str, str]:
    """Match diarization-labels til politikere. Returnerer {label: navn}.

    Kun klynger med en cosine-lighed >= ``threshold`` tildeles.
    """
    import numpy as np  # type: ignore

    prints = load_voiceprints(store)
    if not prints:
        return {}

    label_spans: dict[str, list[tuple[float, float]]] = {}
    for seg in store.segments(meeting_id):
        label = seg["speaker_label"]
        if not label or seg["start"] is None or seg["end"] is None:
            continue
        label_spans.setdefault(label, []).append((seg["start"], seg["end"]))

    names = list(prints)
    matrix = np.vstack([np.array(prints[n]) for n in names])  # (P, D), allerede normaliseret

    mapping: dict[str, str] = {}
    for label, spans in label_spans.items():
        emb = _embed_spans(Path(audio_path), spans)
        sims = matrix @ emb  # cosine, da begge er normaliserede
        best = int(np.argmax(sims))
        if float(sims[best]) >= threshold:
            mapping[label] = names[best]
    return mapping
