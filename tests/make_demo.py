"""Write invented demo data to docs/data.js so the dashboard can be previewed.

Run:  python3 tests/make_demo.py
The first real `python3 update.py` overwrites it with your league's data.
"""
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import build_stats  # noqa: E402
import mock  # noqa: E402


def main(gws=11, seed=7):
    rng = random.Random(seed)
    means = [54, 57, 51, 55]
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
                           ("Cleo", "Clausen", "Team Charlie"), ("Dan", "Dahl", "Team Delta")])
    data = build_stats.build(tmp)
    data["meta"]["demo"] = True
    build_stats.write(data, ROOT / "docs")
    build_stats.summary(data)


if __name__ == "__main__":
    main()
