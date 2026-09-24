#!/usr/bin/env python3
"""Download raw FPL Draft data for one league into data/raw/.

Only public, read-only endpoints are used. No login, cookies or passwords.
Finished gameweeks are cached, so an update after each round only downloads
the new round plus the small league-level files.

Usage:  python3 collect.py            # normal update
        python3 collect.py --force    # re-download everything
"""
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://draft.premierleague.com/api"
ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
UA = "Mozilla/5.0 (compatible; fpl-draft-friends-dashboard/1.0)"
PAUSE = 0.25  # seconds between requests, be polite to the server


class FetchError(Exception):
    pass


def get_json(path, retries=3):
    url = f"{BASE}/{path.lstrip('/')}"
    last = "unknown error"
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
            time.sleep(PAUSE)
            return json.loads(body)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} for {url}"
            if e.code in (401, 403, 404):
                break  # retrying will not help
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            # The game is briefly offline while scores update; JSON decode fails then.
            last = f"{type(e).__name__}: {e} for {url}"
        time.sleep(1.5 * attempt)
    raise FetchError(last)


def save(rel_path, obj):
    p = RAW / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def load_state():
    """Return the saved cache state, or None if there isn't one yet."""
    p = RAW / "_state.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def collect(force=False, log=print):
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    league_id = cfg["league_id"]
    RAW.mkdir(parents=True, exist_ok=True)
    warnings = []

    # 1. Game state decides which gameweeks are finished (and so cacheable).
    game = get_json("game")
    save("game.json", game)
    current = int(game.get("current_event") or 0)
    finished = bool(game.get("current_event_finished"))
    last_final = current if finished else current - 1
    log(f"Game state: gameweek {current} ({'finished' if finished else 'in progress'})")

    # 2. League-level files, refreshed every run (small).
    details = get_json(f"league/{league_id}/details")
    save("league_details.json", details)
    save("bootstrap.json", get_json("bootstrap-static"))
    save("transactions.json", get_json(f"draft/league/{league_id}/transactions"))
    save("element_status.json", get_json(f"league/{league_id}/element-status"))
    save("draft_choices.json", get_json(f"draft/{league_id}/choices"))
    entry_ids = [e["entry_id"] for e in details.get("league_entries", [])]
    log(f"League '{details.get('league', {}).get('name')}' with {len(entry_ids)} managers")

    # 3. Per-gameweek files: live player points + each manager's lineup.
    # A new season gets a new league_id (see README); an old cache saved
    # before this check existed has no "league_id" at all. Either way the
    # cached "final" gameweeks belong to a different league and must not be
    # trusted, or last season's numbers would leak into the new one.
    prev_state = load_state()
    if not force and prev_state is not None and prev_state.get("league_id") != league_id:
        force = True
        log(f"League changed (was {prev_state.get('league_id')!r}, now {league_id}); re-downloading everything.")
    state = {"final_gws": []} if force or prev_state is None else prev_state
    final = set(state.get("final_gws", []))
    fetched = []
    for gw in range(1, current + 1):
        if gw in final:
            continue
        ok = True
        try:
            save(f"live/gw{gw}.json", get_json(f"event/{gw}/live"))
        except FetchError as e:
            warnings.append(f"GW{gw} live points: {e}")
            ok = False
        for eid in entry_ids:
            try:
                save(f"entries/{eid}/gw{gw}.json", get_json(f"entry/{eid}/event/{gw}"))
            except FetchError as e:
                warnings.append(f"GW{gw} lineup for entry {eid}: {e}")
                ok = False
        if ok and gw <= last_final:
            final.add(gw)
        fetched.append(gw)

    state = {
        "final_gws": sorted(final),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "league_id": league_id,
    }
    save("_state.json", state)
    log(f"Downloaded gameweeks: {fetched or 'none (all cached)'}")
    for w in warnings:
        log(f"WARNING: {w}")
    return warnings


if __name__ == "__main__":
    try:
        w = collect(force="--force" in sys.argv)
    except FetchError as e:
        sys.exit(f"Could not reach the FPL Draft API: {e}\n"
                 "If it says the game is updating, try again in a few minutes.")
    sys.exit(1 if w else 0)
