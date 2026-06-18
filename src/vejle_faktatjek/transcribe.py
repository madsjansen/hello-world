"""Dansk transskription med speaker diarization.

Producerer en liste af segmenter: ``{"speaker", "start", "end", "text"}``.

Implementeringen bruger WhisperX (ord-præcise tidsstempler + pyannote
diarization). For bedst dansk kvalitet: peg ``VF_WHISPER_MODEL`` på en
dansk-tunet model (fx CoRal/Alvenir Whisper-vægte) i stedet for ``large-v3``.

Afhængighederne er tunge og valgfrie — importen sker først ved kald, så resten
af pipelinen kan køre uden dem.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def transcribe(audio_path: Path, model_name: str = "large-v3",
               hf_token: str = "", device: str = "auto",
               language: str = "da") -> list[dict]:
    """Transskribér ``audio_path`` med taler-labels.

    Returnerer segmenter med felterne ``speaker``, ``start``, ``end``, ``text``.
    Diarization springes over (alle ``speaker=None``), hvis ``hf_token`` mangler.
    """
    try:
        import torch  # type: ignore
        import whisperx  # type: ignore
    except ImportError as e:  # pragma: no cover - afhænger af valgfri pakker
        raise RuntimeError(
            "whisperx/torch er ikke installeret. Afkommentér dem i requirements.txt "
            "og kør `pip install -r requirements.txt`."
        ) from e

    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    audio = whisperx.load_audio(str(audio_path))

    model = whisperx.load_model(model_name, device, compute_type=compute_type, language=language)
    result = model.transcribe(audio, language=language)

    # Ord-præcise tidsstempler (forbedrer både diarization-match og citat-links).
    align_model, metadata = whisperx.load_align_model(language_code=language, device=device)
    result = whisperx.align(result["segments"], align_model, metadata, audio, device)

    if hf_token:
        diarize = whisperx.DiarizationPipeline(use_auth_token=hf_token, device=device)
        diarize_segments = diarize(audio)
        result = whisperx.assign_word_speakers(diarize_segments, result)

    segments: list[dict] = []
    for seg in result["segments"]:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        segments.append({
            "speaker": seg.get("speaker"),
            "start": seg.get("start"),
            "end": seg.get("end"),
            "text": text,
        })
    return segments


def merge_consecutive(segments: list[dict]) -> list[dict]:
    """Slå tilstødende segmenter fra samme taler sammen til hele taleture."""
    merged: list[dict] = []
    for s in segments:
        if merged and merged[-1].get("speaker") == s.get("speaker"):
            prev = merged[-1]
            prev["text"] = f"{prev['text']} {s['text']}".strip()
            prev["end"] = s.get("end", prev.get("end"))
        else:
            merged.append(dict(s))
    return merged
