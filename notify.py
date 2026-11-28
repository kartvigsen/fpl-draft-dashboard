#!/usr/bin/env python3
"""Banter push notifications during a gameweek, sent through OneSignal.

    python3 notify.py              # detect new events, send them (if enabled)
    python3 notify.py --dry-run    # print what would be sent, change nothing
    python3 notify.py --test       # send one test notification (setup check)

Runs after each dashboard rebuild. It compares the fresh docs/data.json with
what it saw last time (data/notify_state.json, committed with the data) and
announces, to everyone subscribed:

  * a goal or an assist by any player owned in the league (a goal from a
    manager's bench gets its own, crueller line)
  * a red card for an owned player
  * a manager "on fire": +15 points or more within about half an hour
  * a new leader in the live round
  * confirmed bonus points in a finished match, for owned players
  * the final scores once a gameweek is over

The first run, and the first run of each new gameweek, only records the
current state silently, so turning this on never floods anyone with old
news. Nothing is sent unless config.json has "notifications_enabled": true,
"onesignal_app_id" is set, and the ONESIGNAL_API_KEY environment variable
holds the OneSignal REST API key (a GitHub secret -- never put it in this
public repository). Otherwise the events are only printed and the state is
still updated, so switching on later doesn't replay a backlog.
"""
import json
import os
import random
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "docs" / "data.json"
STATE_FILE = ROOT / "data" / "notify_state.json"
CONFIG_FILE = ROOT / "config.json"
SITE_URL = "https://kartvigsen.github.io/fpl-draft-dashboard/#liveround"
ONESIGNAL_URL = "https://api.onesignal.com/notifications?c=push"

ON_FIRE_POINTS = 15         # gained within ON_FIRE_WINDOW minutes
ON_FIRE_WINDOW = 35
ON_FIRE_COOLDOWN = 60       # minutes before the same manager can be "on fire" again
LEADER_MIN_SCORE = 10       # don't announce a lead at 2-1 in the first minutes
MAX_PER_RUN = 5             # more than this in one run are rolled into one summary

GOAL_LINES = [
    "{manager} are dancing on the tables. Someone tell the neighbours.",
    "Cue {manager} pretending they saw that coming all along.",
    "{manager} just got a lot more insufferable in the group chat.",
    "The rest of you can start writing your excuses now.",
    "Lagom? Not today. {manager} cashing in.",
]
BENCH_GOAL_LINES = [
    "Shame it's on {manager}'s bench. Zero points. Pure pain.",
    "{manager} benched him. Of course he scores. Of course.",
    "Somewhere {manager} is staring at the wall. Bench points don't count, mate.",
]
ASSIST_LINES = [
    "Lovely bit of service. {manager} will take it.",
    "Not the glory, but {manager} isn't complaining.",
    "{manager} quietly stacking points while nobody's looking.",
]
RED_LINES = [
    "Early bath. {manager} won't be thrilled.",
    "Off he goes. {manager}'s week just got worse.",
    "Absolute scenes. {manager}, look away now.",
]
FIRE_LINES = [
    "Someone check {manager}'s phone for VAR.",
    "{manager} have found a cheat code. Report them.",
    "Stop the count. Actually, don't. Let's see how this ends.",
]
LEADER_LINES = [
    "{previous}, your crown is in the bin.",
    "Enjoy it while it lasts, {manager}.",
    "{manager} top of the round. For now. Nobody panic. (Panic.)",
]
FINAL_LINES = [
    "{spoon} brings up the rear with {low}. The wooden spoon suits you.",
    "{spoon} finished last on {low}. We'll say no more. (We'll say plenty more.)",
    "{spoon} with {low}. Thoughts and prayers.",
]


def pick(lines, seed):
    return lines[random.Random(seed).randrange(len(lines))]


def _load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _ts(iso):
    try:
        return datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return 0.0


GOAL_POINTS = {"GKP": 10, "DEF": 6, "MID": 5, "FWD": 4}


def _goal_points(player):
    """Points per goal: from FPL's own breakdown when it has the goal
    already, otherwise FPL's goal value for the player's position."""
    line = next((r for r in player.get("breakdown") or [] if r.get("stat") == "goals_scored"), None)
    if line and line.get("value") and line.get("points"):
        return line["points"] // line["value"]
    return GOAL_POINTS.get(player.get("pos"), 4)


def detect(data, state):
    """Return (events, new_state). Each event is {id, title, body}."""
    cr = data.get("current_round") or {}
    gw = cr.get("gw")
    now = _ts((data.get("meta") or {}).get("generated_at"))
    team_name = {m["entry_id"]: m["team"] for m in data.get("managers", [])}
    role = {}
    for t in cr.get("teams", []):
        for p in t.get("xi", []):
            role[p["id"]] = "xi"
        for p in t.get("bench", []):
            role[p["id"]] = "bench"
    owned = [p for p in cr.get("all_players", []) if p.get("owner_entry_id") in team_name]
    scores = {t["entry_id"]: t.get("score") for t in cr.get("teams", []) if t.get("score") is not None}
    finished_rounds = {r["gw"]: r for r in data.get("rounds", []) if r.get("finished")}

    fresh = not state or state.get("gw") != gw
    new = {
        "gw": gw,
        "players": {str(p["id"]): {"g": p.get("goals_scored", 0), "a": p.get("assists", 0),
                                   "r": (p.get("detail") or {}).get("red_cards", 0)} for p in owned},
        "bonus_matches": [] if fresh else list(state.get("bonus_matches", [])),
        "history": {} if fresh else dict(state.get("history", {})),
        "fired": {} if fresh else dict(state.get("fired", {})),
        "leader": None if fresh else state.get("leader"),
        "final_announced": sorted(set(state.get("final_announced", [])) | (set(finished_rounds) if not state else set())),
    }
    events = []
    old_players = {} if fresh else state.get("players", {})

    for p in owned:
        if fresh:
            break
        before = old_players.get(str(p["id"]), {"g": 0, "a": 0, "r": 0})
        manager = team_name[p["owner_entry_id"]]
        on_bench = role.get(p["id"]) == "bench"
        g_new = p.get("goals_scored", 0) - before.get("g", 0)
        a_new = p.get("assists", 0) - before.get("a", 0)
        r_new = (p.get("detail") or {}).get("red_cards", 0) - before.get("r", 0)
        if g_new > 0:
            seed = f"{gw}-g-{p['id']}-{p.get('goals_scored')}"
            per_goal = _goal_points(p)
            what = "scores" if g_new == 1 else f"scores {g_new}"
            if on_bench:
                events.append({"id": seed, "title": f"⚽ {p['name']} {what}… on the bench 🙈",
                               "body": pick(BENCH_GOAL_LINES, seed).format(manager=manager)})
            else:
                events.append({"id": seed, "title": f"⚽ {p['name']} {what}! +{per_goal * g_new} for {manager}",
                               "body": pick(GOAL_LINES, seed).format(manager=manager)})
        if a_new > 0:
            seed = f"{gw}-a-{p['id']}-{p.get('assists')}"
            if on_bench:
                events.append({"id": seed, "title": f"🅰️ Assist for {p['name']}… on {manager}'s bench",
                               "body": "Wasted. Absolutely wasted."})
            else:
                events.append({"id": seed, "title": f"🅰️ Assist {p['name']}! +{3 * a_new} for {manager}",
                               "body": pick(ASSIST_LINES, seed).format(manager=manager)})
        if r_new > 0:
            seed = f"{gw}-r-{p['id']}"
            events.append({"id": seed, "title": f"🟥 {p['name']} sent off! −3 for {manager}",
                           "body": pick(RED_LINES, seed).format(manager=manager)})

    # On fire: the live round score jumped within the last half hour.
    for eid, score in scores.items():
        hist = [h for h in new["history"].get(str(eid), []) if now - h[0] <= ON_FIRE_WINDOW * 60]
        if not fresh and hist and score - min(s for _, s in hist) >= ON_FIRE_POINTS \
                and now - new["fired"].get(str(eid), 0) >= ON_FIRE_COOLDOWN * 60:
            gain = score - min(s for _, s in hist)
            seed = f"{gw}-f-{eid}-{score}"
            events.append({"id": seed, "title": f"🔥 {team_name[eid]} on fire: +{gain} in half an hour",
                           "body": f"Now on {score} for GW{gw}. " + pick(FIRE_LINES, seed).format(manager=team_name[eid])})
            new["fired"][str(eid)] = now
        new["history"][str(eid)] = hist + [[now, score]]

    # A new leader in the live round (ties don't count as a change).
    if scores and not cr.get("finished"):
        top = max(scores.values())
        leaders = [e for e, s in scores.items() if s == top]
        if len(leaders) == 1 and top >= LEADER_MIN_SCORE:
            leader = leaders[0]
            if not fresh and new["leader"] is not None and leader != new["leader"]:
                seed = f"{gw}-l-{leader}-{top}"
                prev = team_name.get(new["leader"], "the old leader")
                events.append({"id": seed, "title": f"👑 {team_name[leader]} take the lead in GW{gw} ({top} pts)",
                               "body": pick(LEADER_LINES, seed).format(manager=team_name[leader], previous=prev)})
            new["leader"] = leader

    # Bonus confirmed by FPL for a finished match (no provisional bonus left).
    for m in cr.get("matches", []):
        if m.get("status") != "ft" or m["id"] in new["bonus_matches"]:
            continue
        players = m["home"]["players"] + m["away"]["players"]
        if any(p.get("bonus_provisional") for p in players) or not any(p.get("bonus") for p in players):
            continue
        new["bonus_matches"].append(m["id"])
        if fresh:
            continue
        got = sorted((p for p in players if p.get("bonus") and p.get("owner_entry_id") in team_name),
                     key=lambda p: -p["bonus"])
        if got:
            seed = f"{gw}-b-{m['id']}"
            parts = ", ".join(f"{p['name']} +{p['bonus']} ({team_name[p['owner_entry_id']]})" for p in got)
            events.append({"id": seed, "title": f"🎁 Bonus confirmed: {m['home']['short']} {m['home']['score']}–{m['away']['score']} {m['away']['short']}",
                           "body": parts})

    # Final scores once a gameweek is over.
    for g, r in sorted(finished_rounds.items()):
        if g in new["final_announced"]:
            continue
        new["final_announced"].append(g)
        sc = {int(k): v for k, v in r.get("scores", {}).items() if v is not None}
        if not sc:
            continue
        hi, lo = max(sc.values()), min(sc.values())
        winners = " & ".join(team_name.get(e, "?") for e, v in sc.items() if v == hi)
        spoon = " & ".join(team_name.get(e, "?") for e, v in sc.items() if v == lo)
        seed = f"{g}-final"
        events.append({"id": seed, "title": f"🏁 GW{g} is done: {winners} win with {hi}",
                       "body": pick(FINAL_LINES, seed).format(spoon=spoon, low=lo)})

    new["bonus_matches"] = sorted(new["bonus_matches"])
    new["final_announced"] = sorted(new["final_announced"])
    return events, new


def bundle(events):
    """At most MAX_PER_RUN notifications; anything beyond becomes one summary."""
    if len(events) <= MAX_PER_RUN:
        return events
    keep, rest = events[:MAX_PER_RUN - 1], events[MAX_PER_RUN - 1:]
    return keep + [{"id": "summary-" + rest[0]["id"], "title": f"📣 {len(rest)} more things just happened",
                    "body": " · ".join(e["title"] for e in rest)[:240]}]


def send(event, app_id, api_key):
    body = json.dumps({
        "app_id": app_id,
        "target_channel": "push",
        "included_segments": ["Total Subscriptions"],
        "headings": {"en": event["title"]},
        "contents": {"en": event["body"]},
        "web_url": SITE_URL,
    }).encode()
    req = urllib.request.Request(ONESIGNAL_URL, data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Key {api_key}"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status


def main(argv=None, data_file=DATA_FILE, state_file=STATE_FILE, config_file=CONFIG_FILE, sender=send):
    argv = sys.argv[1:] if argv is None else argv
    dry = "--dry-run" in argv
    config = _load(config_file, {})
    app_id = config.get("onesignal_app_id")
    api_key = os.environ.get("ONESIGNAL_API_KEY", "")
    enabled = bool(config.get("notifications_enabled") and app_id and api_key)

    if "--test" in argv:
        if not enabled:
            print("Notifications aren't set up yet: need notifications_enabled, onesignal_app_id and ONESIGNAL_API_KEY.")
            return 1
        sender({"id": "test", "title": "🔔 Notifications are on",
                "body": "You'll hear about goals, assists, red cards and who's on fire. Brace yourselves."}, app_id, api_key)
        print("Test notification sent.")
        return 0

    data = _load(data_file, {})
    if not data.get("current_round"):
        print("No live round data; nothing to do.")
        return 0
    state = _load(state_file, {})
    events, new_state = detect(data, state)
    events = bundle(events)
    for e in events:
        print(f"{'SEND' if enabled and not dry else 'would send'}: {e['title']} | {e['body']}")
    if dry:
        return 0
    if enabled:
        for e in events:
            try:
                sender(e, app_id, api_key)
            except Exception as exc:   # a failed send must never block the dashboard
                print(f"Could not send '{e['title']}': {exc}")
    Path(state_file).parent.mkdir(parents=True, exist_ok=True)
    Path(state_file).write_text(json.dumps(new_state, indent=1, sort_keys=True), encoding="utf-8")
    if not events:
        print("Nothing new to announce.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
