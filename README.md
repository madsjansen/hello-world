# Vejle Faktatjek

Pipeline der henter lydoptagelser fra Vejle Byråds møder, transskriberer dem
med taler-identifikation, udtrækker efterprøvbare påstande, faktatjekker dem med
Claude + websøgning, og bygger et leaderboard over politikernes og partiernes
pålidelighed.

> Datagrundlaget (lydoptagelser, dagsordener, referater) er offentligt tilgængeligt
> på [vejle.dk](https://www.vejle.dk/politik/politik-og-byraad/moeder-i-byraad-og-udvalg/lydoptagelser-fra-byraadsmoeder/)
> og via [Kommune-TV](https://kommune-tv.dk/).

## Arkitektur

```
  Kommune-TV / vejle.dk lyd-URL
            │  (fetch.py)
            ▼
   Lydfil (16 kHz mono WAV)
            │  (transcribe.py — faster-whisper + diarization)
            ▼
   Segmenter: {taler, start, slut, tekst}
            │  (speakers.py — match Speaker-N → navngiven politiker)
            ▼
   Påstande   (claims.py — Claude, struktureret output)
            │
            ▼
   Domme      (factcheck.py — Claude + web_search, evidensbaseret)
            │  (store.py — SQLite)
            ▼
   leaderboard.json  (leaderboard.py / scripts/build_site.py)
            │
            ▼
   Statisk side (web/index.html)
```

Pipelinen kører som batch efter hvert møde. Hvert trin er et selvstændigt modul
med et rent interface, så et live-overlay senere kan genbruge `transcribe` +
`claims` + `factcheck` oven på en streaming-kilde.

## Hurtig start

### 1. Installér

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # udfyld ANTHROPIC_API_KEY
```

`faster-whisper` og `whisperx` er valgfrie tunge afhængigheder (kun nødvendige
for selve transskriptionen). Resten af pipelinen og leaderboardet kører uden dem.

### 2. Se leaderboardet med det samme (sample-data)

```bash
python -m vejle_faktatjek.cli seed-demo      # indlæser data/sample i en lokal DB
python -m vejle_faktatjek.cli build-site     # genererer web/leaderboard.json
python -m http.server -d web 8000            # åbn http://localhost:8000
```

### 3. Kør et rigtigt møde gennem pipelinen

```bash
# Hele kæden fra en lyd-URL:
python -m vejle_faktatjek.cli run \
    --url "https://…/byraadsmoede-2026-06-15.mp3" \
    --date 2026-06-15 --title "Byrådsmøde juni 2026"

# Eller ét trin ad gangen:
python -m vejle_faktatjek.cli fetch --url "…" --date 2026-06-15
python -m vejle_faktatjek.cli transcribe --meeting 1
python -m vejle_faktatjek.cli extract-claims --meeting 1
python -m vejle_faktatjek.cli factcheck --meeting 1
python -m vejle_faktatjek.cli build-site
```

## Politiker-roster

Taler-identifikation kobler "Speaker 1/2/3" fra diarization til navngivne
politikere. Udfyld `data/politicians.json` med byrådets medlemmer (navn + parti).
Indtil hver politiker har et stemme-aftryk (`voiceprint`), markeres ukendte
talere som `Ukendt` og kan rettes manuelt i databasen.

## Vurderingskategorier

Hver påstand dømmes som én af: `Korrekt`, `Delvist korrekt`, `Misvisende`,
`Forkert`, `Ikke verificerbar`. Pålidelighedsscoren pr. politiker/parti bygger
**kun** på de verificerbare påstande, og antallet vises altid ved siden af scoren
så en der siger lidt ikke fremstår kunstigt pålidelig.

## Moduloversigt

| Modul | Ansvar |
|-------|--------|
| `config.py` | Konfiguration (API-nøgle, model, stier) fra miljøvariabler |
| `fetch.py` | Hent lyd/stream fra vejle.dk / Kommune-TV → 16 kHz WAV |
| `transcribe.py` | Dansk ASR + speaker diarization → segmenter |
| `speakers.py` | Match diarization-labels til navngivne politikere |
| `claims.py` | Udtræk efterprøvbare påstande (Claude, struktureret output) |
| `factcheck.py` | Evidensbaseret dom pr. påstand (Claude + `web_search`) |
| `store.py` | SQLite-lager + datamodel |
| `leaderboard.py` | Aggregér domme til pålidelighedsscorer |
| `pipeline.py` | Orkestrér hele kæden |
| `cli.py` | Kommandolinje-interface |

## Status / begrænsninger

- Faktatjek er evidensbaseret (Claude får websøgeresultater og dømmer ud fra dem,
  ikke fra hukommelsen) — men kvaliteten afhænger af kilderne. Hold et menneske
  på godkendelse før noget publiceres offentligt.
- ASR på dansk er bedst med en dansk-tunet model (se `transcribe.py`).
- Stemme-baseret taler-ID er ikke implementeret endnu (kræver indtalte profiler);
  i mellemtiden bruges referatets talerækkefølge som hint + manuel kvalitetssikring.
```
