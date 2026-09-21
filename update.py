#!/usr/bin/env python3
"""One command to refresh the dashboard after each gameweek.

    python3 update.py              # download new data, rebuild docs/data.js
    python3 update.py --no-fetch   # rebuild from data already in data/raw/
    python3 update.py --force      # re-download every gameweek

Then open docs/index.html in a browser (or publish the docs/ folder).
"""
import sys

import build_stats
import collect


def main(argv):
    if "--no-fetch" not in argv:
        try:
            warnings = collect.collect(force="--force" in argv)
        except collect.FetchError as e:
            sys.exit(f"Could not reach the FPL Draft API: {e}\n"
                     "If the game is updating, try again in a few minutes.")
        if warnings:
            print("Some downloads failed (see WARNING lines above). Building with what we have.")
    data = build_stats.build()
    build_stats.write(data)
    build_stats.summary(data)
    print("Done. Open docs/index.html to see the dashboard.")


if __name__ == "__main__":
    main(sys.argv[1:])
