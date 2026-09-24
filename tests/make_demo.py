"""Write invented demo data to docs/data.js so the dashboard can be previewed.

Run:  python3 tests/make_demo.py
The first real `python3 update.py` overwrites it with your league's data.
"""
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import build_stats  # noqa: E402
import mock  # noqa: E402


def _element_status(n_m):
    """Every rostered squad player (ids 1..n_m*15) owned by their manager;
    the free-agent pool (mock.FREE_AGENT_BASE and up) unowned."""
    status = []
    for m in range(n_m):
        for slot in range(1, mock.SQUAD + 1):
            status.append({"element": m * mock.SQUAD + slot, "owner": 101 + m,
                           "status": "o", "in_accepted_trade": False})
    for k in range(12):
        status.append({"element": mock.FREE_AGENT_BASE + k, "owner": None,
                       "status": "a", "in_accepted_trade": False})
    return {"element_status": status}


def _draft_choices(n_m):
    """A snake draft over the squads: round = squad slot, "pick" resets each
    round (1..n_m), "index" is the real overall draft position."""
    choices, overall = [], 1
    entry_ids = [101 + m for m in range(n_m)]
    for slot in range(1, mock.SQUAD + 1):
        order = entry_ids if slot % 2 == 1 else list(reversed(entry_ids))
        for pick, eid in enumerate(order, start=1):
            m = entry_ids.index(eid)
            choices.append({"element": m * mock.SQUAD + slot, "entry": eid,
                            "round": slot, "pick": pick, "index": overall})
            overall += 1
    return {"choices": choices}


def main(gws=11, seed=7):
    rng = random.Random(seed)
    means = [54, 57, 51, 55]
    n_m = len(means)
    scores = [[max(22, int(rng.gauss(mu, 11))) for mu in means] for _ in range(gws)]
    txs, tid = [], 1
    for gw in range(1, gws + 1):
        for m in range(4):
            for _ in range(rng.choice([0, 0, 1, 1, 2]) if m != 2 else rng.choice([0, 0, 0, 1])):
                kind = rng.choice(["f", "f", "w"])
                txs.append(mock.tx(tid, gw, m, kind, "a", mock.FREE_AGENT_BASE + rng.randrange(12),
                                   m * 15 + rng.randint(2, 15),
                                   added=f"2026-09-{min(gw + 1, 28):02d}T{rng.randint(8, 21):02d}:00:00Z"))
                tid += 1
        if rng.random() < 0.5:
            txs.append(mock.tx(tid, gw, rng.randrange(4), "w", "do",
                               mock.FREE_AGENT_BASE + rng.randrange(12), None,
                               added=f"2026-09-{min(gw + 1, 28):02d}T07:00:00Z"))
            tid += 1
    tmp = Path(tempfile.mkdtemp())
    mock.write_raw(tmp, scores, current_finished=False, spread=True, seed=seed, transactions=txs,
                   league_name="Demo League (invented data)",
                   people=[("Alex", "Andersen", "Team Alpha"), ("Bo", "Berg", "Team Bravo"),
                           ("Cleo", "Clausen", "Team Charlie"), ("Dan", "Dahl", "Team Delta")],
                   element_status=_element_status(n_m)["element_status"],
                   draft_choices=_draft_choices(n_m))

    # mock.write_raw doesn't invent season-long PL stats for each player, but
    # the All players tab reads them, so add plausible ones for the demo.
    boot_path = tmp / "bootstrap.json"
    boot = json.loads(boot_path.read_text())
    for el in boot["elements"]:
        total = rng.randint(0, 140)
        el["total_points"] = total
        el["starts"] = rng.randint(3, gws)
        el["points_per_game"] = str(round(total / el["starts"], 1))
    boot_path.write_text(json.dumps(boot))

    data = build_stats.build(tmp)
    data["meta"]["demo"] = True
    build_stats.write(data, ROOT / "docs")
    build_stats.summary(data)


if __name__ == "__main__":
    main()
