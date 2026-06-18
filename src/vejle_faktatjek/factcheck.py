"""Evidensbaseret faktatjek af en enkelt påstand med Claude.

To trin, så domme bygger på fremfundet evidens — ikke på modellens hukommelse:

  1. RESEARCH: Claude bruger det serverside web_search-værktøj til at finde
     relevante kilder (helst danske: Danmarks Statistik, kommunens budgetter/
     regnskaber, officielle registre, referater).
  2. DOM: en separat, struktureret kald dømmer påstanden ud fra fundene og
     returnerer en kategori + forklaring + kildehenvisninger.
"""

from __future__ import annotations

from typing import Optional

import anthropic
from pydantic import BaseModel, Field

from .config import CONFIG

RATINGS = ["Korrekt", "Delvist korrekt", "Misvisende", "Forkert", "Ikke verificerbar"]

_RESEARCH_SYSTEM = """Du er faktatjekker. Du får én påstand fra et byrådsmøde i
Vejle Kommune. Brug web_search til at finde pålidelig, helst dansk og officiel,
evidens der kan be- eller afkræfte påstanden (Danmarks Statistik, kommunens
budgetter og regnskaber, regionens data, officielle registre, mødereferater,
anerkendte medier). Søg konkret og målrettet. Skriv til sidst et kort,
nøgternt notat med de relevante fund og angiv URL'er. Konkludér ikke selv —
referér kun evidensen."""

_JUDGE_SYSTEM = f"""Du er faktatjekker og dømmer en påstand fra et byrådsmøde
UDELUKKENDE ud fra den fremlagte evidens. Brug aldrig din egen hukommelse.

Vælg én vurdering:
- "Korrekt": evidensen understøtter påstanden klart.
- "Delvist korrekt": rigtig i hovedtræk, men upræcis eller mangler forbehold.
- "Misvisende": teknisk korrekte tal brugt vildledende, eller mangler vigtig kontekst.
- "Forkert": evidensen modsiger påstanden.
- "Ikke verificerbar": evidensen er utilstrækkelig til at dømme.

Vær konservativ: vælg "Ikke verificerbar" hvis evidensen ikke er klar.
confidence er 0-1. Skriv forklaringen kort og neutralt på dansk, og henvis til
de konkrete kilder. Tilgængelige vurderinger: {', '.join(RATINGS)}."""


class Source(BaseModel):
    title: str = ""
    url: str = ""


class Verdict(BaseModel):
    rating: str = Field(description=f"Én af: {', '.join(RATINGS)}")
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    sources: list[Source] = []


def _research(claim_text: str, client: anthropic.Anthropic) -> str:
    """Kør web_search og returnér modellens evidensnotat som tekst."""
    messages = [{"role": "user", "content": f"Påstand der skal undersøges:\n{claim_text}"}]
    tools = [{
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": 6,
    }]
    # Serverside-værktøjsløkke: gentag ved pause_turn til modellen er færdig.
    for _ in range(6):
        resp = client.messages.create(
            model=CONFIG.model,
            max_tokens=4000,
            system=_RESEARCH_SYSTEM,
            thinking={"type": "adaptive"},
            messages=messages,
            tools=tools,
        )
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        text = "\n".join(b.text for b in resp.content if b.type == "text")
        return text.strip()
    return ""


def _judge(claim_text: str, evidence: str, client: anthropic.Anthropic) -> Optional[Verdict]:
    if not evidence:
        return Verdict(
            rating="Ikke verificerbar",
            confidence=0.3,
            explanation="Ingen evidens fundet ved websøgning.",
            sources=[],
        )
    response = client.messages.parse(
        model=CONFIG.model,
        max_tokens=2000,
        system=_JUDGE_SYSTEM,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        messages=[{
            "role": "user",
            "content": f"Påstand:\n{claim_text}\n\nFremfundet evidens:\n{evidence}",
        }],
        output_format=Verdict,
    )
    return response.parsed_output


def factcheck(claim_text: str, client: Optional[anthropic.Anthropic] = None) -> Verdict:
    """Faktatjek én påstand. Returnerer en valideret Verdict."""
    client = client or anthropic.Anthropic(api_key=CONFIG.require_api_key())
    evidence = _research(claim_text, client)
    verdict = _judge(claim_text, evidence, client)
    if verdict is None:
        verdict = Verdict(rating="Ikke verificerbar", confidence=0.0,
                          explanation="Kunne ikke danne en struktureret dom.", sources=[])
    if verdict.rating not in RATINGS:
        verdict.rating = "Ikke verificerbar"
    return verdict
