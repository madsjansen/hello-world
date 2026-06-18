"""Konfiguration læst fra miljøvariabler (og evt. en .env-fil)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Letvægts .env-indlæsning uden ekstra afhængighed.
def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(Path(".env"))

# Repo-rod (to niveauer op fra denne fil: src/vejle_faktatjek/config.py).
ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    model: str = os.environ.get("VF_MODEL", "claude-opus-4-8")
    db_path: Path = ROOT / os.environ.get("VF_DB", "data/vejle.db")
    audio_dir: Path = ROOT / os.environ.get("VF_AUDIO_DIR", "data/audio")
    whisper_model: str = os.environ.get("VF_WHISPER_MODEL", "large-v3")
    hf_token: str = os.environ.get("VF_HF_TOKEN", "")
    politicians_path: Path = ROOT / "data/politicians.json"
    sample_dir: Path = ROOT / "data/sample"
    site_data_path: Path = ROOT / "web/leaderboard.json"

    def require_api_key(self) -> str:
        if not self.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY mangler. Sæt den i .env eller miljøet."
            )
        return self.anthropic_api_key


CONFIG = Config()
