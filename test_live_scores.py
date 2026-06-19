"""Standalone check for the live World Cup scoreboard — no MySQL, no Flask.

Run from the project root:

    python test_live_scores.py

It calls football-data.org through the same service the website uses and prints
what came back, so you can confirm the token + World Cup feed work before
wiring up the full app.
"""

import os
import sys

# Make sure the token is available even if you haven't exported it. The website
# reads config.py; this script falls back to the same hard-coded token.
os.environ.setdefault("FOOTBALL_DATA_TOKEN", "c665fce411204ba6b5cb96d7d73a96fd")

try:
    from app.services.worldcup import MatchDataManager
except ModuleNotFoundError:
    sys.exit(
        "Could not import app.services.worldcup — run this from the NicheForum "
        "project root (the folder that contains the 'app' package)."
    )


def main():
    manager = MatchDataManager(token=os.environ["FOOTBALL_DATA_TOKEN"])
    data = manager.get_scoreboard(force_refresh=True)

    print("=" * 60)
    print(f" competition : {data['competition']}")
    print(f" source      : {data['source']}")
    print(f" message     : {data['message']}")
    print(f" live now    : {data['live_count']}")
    print(f" goals today : {data['goals_today']}")
    print(f" updated     : {data['updated']}")
    budget = getattr(manager.client, "requests_available", None)
    if budget is not None:
        print(f" rate budget : {budget} requests left this minute")
    print("=" * 60)

    if data["source"] == "error":
        print("\nUPSTREAM ERROR — the page will show this message instead of scores:")
        print(f"  {data['message']}")
        print("\nIf it mentions 403/World Cup access, your token doesn't cover WC.")
        return

    matches = data["matches"] or []
    if not matches:
        print("\nNo matches to display right now.")
    else:
        label = "LIVE MATCHES" if data["source"] == "live" else "FIXTURES (nothing live this minute)"
        print(f"\n{label}:")
        for m in matches:
            h, a = m["home"], m["away"]
            hs = h["goals"] if h["goals"] is not None else "-"
            as_ = a["goals"] if a["goals"] is not None else "-"
            stage = m.get("stage") or ""
            grp = m.get("group") or ""
            print(f"  [{m['status']:<9}] {h['name']:>18}  {hs} - {as_}  {a['name']:<18}  {stage} {grp}".rstrip())

    if data.get("upcoming"):
        print("\nNEXT KICKOFFS:")
        for m in data["upcoming"]:
            print(f"  {m['utc_date']}  {m['home']['name']} vs {m['away']['name']}")

    print("\nOK — the /live page will render this same data.")


if __name__ == "__main__":
    main()
