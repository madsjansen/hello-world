"""Hent lydoptagelse fra et tidligere Vejle Byråds-møde og normalisér til WAV.

Vejle Kommune publicerer lydoptagelser fra byrådsmøder (ikke video/live) på
vejle.dk. Find den direkte lyd-URL (typisk en .mp3) ved at inspicere
afspillerens netværkskald, og giv den til ``download_audio``.

Kræver ``yt-dlp`` (håndterer både direkte filer og HLS) og ``ffmpeg`` på PATH
til at konvertere til 16 kHz mono WAV, som ASR-modeller forventer.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def download_audio(url: str, dest_dir: Path, name: str) -> Path:
    """Hent ``url`` og returnér stien til en 16 kHz mono WAV.

    ``name`` bruges som filnavn (uden endelse), fx mødedatoen.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    raw = dest_dir / f"{name}.download"
    wav = dest_dir / f"{name}.wav"

    if not _have("ffmpeg"):
        raise RuntimeError("ffmpeg er ikke installeret (kræves for WAV-konvertering).")

    if _have("yt-dlp"):
        # yt-dlp henter robust både direkte mediefiler og HLS-streams.
        subprocess.run(
            ["yt-dlp", "-f", "bestaudio/best", "-o", str(raw), url],
            check=True,
        )
        src = raw
    else:
        # Fallback: lad ffmpeg hente direkte (virker for almindelige http(s)-filer).
        src = url

    # Konvertér til 16 kHz mono WAV.
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", str(wav)],
        check=True,
    )
    if raw.exists():
        raw.unlink()
    return wav
