"""Udtræk efterprøvbare påstande fra transskriberede taleture med Claude.

Adskiller faktuelle, efterprøvbare påstande (kan tjekkes mod kilder) fra
holdninger, forhandling og procedure — kun de første skal faktatjekkes.

Bruger structured outputs (``messages.parse``) så outputtet er valideret JSON.
"""

from __future__ import annotations

from typing import Optional

import anthropic
from pydantic import BaseModel, Field

from .config import CONFIG

CATEGORIES = ["økonomi", "klima", "social", "infrastruktur", "beskæftigelse", "andet"]

_SYSTEM = """Du analyserer transskriberet tale fra et dansk byrådsmøde i Vejle Kommune.
Din opgave er at finde FAKTUELLE, EFTERPRØVBARE påstande — udsagn der kan
afgøres som sande eller falske ved opslag i kilder (statistik, budgetter,
regnskaber, referater, officielle data).

Medtag KUN efterprøvbare påstande. Spring over:
- holdninger og værdiudsagn ("det er en dårlig idé")
- hensigtserklæringer og forslag om fremtiden
- spørgsmål, procedure og høflighedsfraser

Skriv hver påstand som en kort, selvstændig, faktatjekbar sætning på dansk.
Bevar tal og navne præcist som de blev sagt."""


class Claim(BaseModel):
    text: str = Field(description="Selvstændig, efterprøvbar påstand på dansk.")
    category: str = Field(description=f"Én af: {', '.join(CATEGORIES)}")


class ClaimList(BaseModel):
    claims: list[Claim]


def extract_claims(turn_text: str, client: Optional[anthropic.Anthropic] = None) -> list[Claim]:
    """Udtræk efterprøvbare påstande fra én taletur (kan være tom)."""
    if not turn_text.strip():
        return []
    client = client or anthropic.Anthropic(api_key=CONFIG.require_api_key())

    response = client.messages.parse(
        model=CONFIG.model,
        max_tokens=4000,
        system=_SYSTEM,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": f"Taletur:\n\n{turn_text}"}],
        output_format=ClaimList,
    )
    parsed = response.parsed_output
    return parsed.claims if parsed else []
