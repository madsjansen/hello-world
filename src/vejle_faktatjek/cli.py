"""Kommandolinje-interface for Vejle Faktatjek."""

from __future__ import annotations

import argparse
import json
import sys

from .config import CONFIG
from .store import Store


def _store() -> Store:
    return Store(CONFIG.db_path)


def cmd_seed_demo(args) -> None:
    from .seed import seed_demo
    store = _store()
    stats = seed_demo(store)
    print(f"Indlæst sample-data: {stats}")
    store.close()


def cmd_build_site(args) -> None:
    from .pipeline import step_build_site
    store = _store()
    out = step_build_site(store)
    print(f"Skrev leaderboard til {out}")
    store.close()


def cmd_fetch(args) -> None:
    from .pipeline import load_roster, step_fetch
    store = _store()
    load_roster(store)
    meeting_id = args.meeting or store.create_meeting(args.date, args.title or args.date, args.url)
    wav = step_fetch(store, meeting_id, args.url)
    print(f"Møde {meeting_id}: hentede lyd til {wav}")
    store.close()


def cmd_transcribe(args) -> None:
    from .pipeline import step_transcribe
    store = _store()
    n = step_transcribe(store, args.meeting)
    print(f"Møde {args.meeting}: {n} segmenter transskriberet")
    store.close()


def cmd_extract_claims(args) -> None:
    from .pipeline import step_extract_claims
    store = _store()
    n = step_extract_claims(store, args.meeting)
    print(f"Møde {args.meeting}: {n} påstande udtrukket")
    store.close()


def cmd_factcheck(args) -> None:
    from .pipeline import step_factcheck
    store = _store()
    n = step_factcheck(store, args.meeting)
    print(f"Møde {args.meeting}: {n} påstande faktatjekket")
    store.close()


def cmd_run(args) -> None:
    from .pipeline import run_all
    store = _store()
    label_map = json.loads(args.label_map) if args.label_map else None
    meeting_id = run_all(store, args.url, args.date, args.title or args.date, label_map)
    print(f"Færdig. Møde-id {meeting_id}.")
    store.close()


def cmd_speakers(args) -> None:
    from .speakers import speaker_label_summary
    store = _store()
    summary = speaker_label_summary(store, args.meeting)
    for label, count in sorted(summary.items(), key=lambda x: -x[1]):
        print(f"{label}: {count} segmenter")
    store.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vejle_faktatjek", description="Faktatjek af Vejle Byråds lydoptagelser")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("seed-demo", help="Indlæs sample-data i databasen").set_defaults(func=cmd_seed_demo)
    sub.add_parser("build-site", help="Generér web/leaderboard.json").set_defaults(func=cmd_build_site)

    f = sub.add_parser("fetch", help="Hent lydoptagelse")
    f.add_argument("--url", required=True)
    f.add_argument("--date", required=True)
    f.add_argument("--title", default="")
    f.add_argument("--meeting", type=int)
    f.set_defaults(func=cmd_fetch)

    t = sub.add_parser("transcribe", help="Transskribér et møde")
    t.add_argument("--meeting", type=int, required=True)
    t.set_defaults(func=cmd_transcribe)

    e = sub.add_parser("extract-claims", help="Udtræk påstande")
    e.add_argument("--meeting", type=int, required=True)
    e.set_defaults(func=cmd_extract_claims)

    c = sub.add_parser("factcheck", help="Faktatjek påstande")
    c.add_argument("--meeting", type=int, required=True)
    c.set_defaults(func=cmd_factcheck)

    s = sub.add_parser("speakers", help="Vis speaker-labels for et møde")
    s.add_argument("--meeting", type=int, required=True)
    s.set_defaults(func=cmd_speakers)

    r = sub.add_parser("run", help="Kør hele kæden for et nyt møde")
    r.add_argument("--url", required=True)
    r.add_argument("--date", required=True)
    r.add_argument("--title", default="")
    r.add_argument("--label-map", help='JSON, fx \'{"SPEAKER_00": "Jens Ejner Christensen"}\'')
    r.set_defaults(func=cmd_run)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
