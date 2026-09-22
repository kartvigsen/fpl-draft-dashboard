"""Checks the stats builder against hand-worked expectations.

Run:  python3 -m unittest discover -s tests -v
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import build_stats  # noqa: E402
import mock  # noqa: E402


def _dump(root, rel, obj):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def write_low_scorers_fixture(root):
    """One manager, 5 finished gameweeks, four hand-picked players so the
    "at least 60% of finished rounds" threshold (ceil(0.6*5) = 3 starts) and
    the points/starts tie-break can be checked exactly.

    Ann:  5,5,5,0,0 = 15 pts, 5 starts   (qualifies)
    Ben:  1,1,1,1,1 =  5 pts, 5 starts   (qualifies, fewest points)
    Cid: 20,20        = 40 pts, 2 starts (does NOT qualify: below 3 starts)
    Eve:  2,2,1        =  5 pts, 3 starts (qualifies, ties Ben on points)
    """
    _dump(root, "game.json", {"current_event": 5, "current_event_finished": True})
    _dump(root, "bootstrap.json", {
        "elements": [
            {"id": 1001, "web_name": "Ann", "element_type": 1, "team": 1},
            {"id": 1002, "web_name": "Ben", "element_type": 1, "team": 1},
            {"id": 1003, "web_name": "Cid", "element_type": 1, "team": 1},
            {"id": 1005, "web_name": "Eve", "element_type": 1, "team": 1},
        ],
        "teams": [{"id": 1, "short_name": "ARS"}],
    })
    _dump(root, "transactions.json", [])
    _dump(root, "league_details.json", {
        "league": {"id": 1, "name": "Solo League"},
        "league_entries": [{"entry_id": 201, "id": 9001, "entry_name": "Solo Team",
                            "player_first_name": "Sam", "player_last_name": "Solo",
                            "short_name": "SOL"}],
        "standings": [{"league_entry": 9001, "event_total": 0, "total": 0}],
    })
    live_by_gw = {
        1: {1001: 5, 1002: 1, 1003: 20, 1005: 2},
        2: {1001: 5, 1002: 1, 1003: 20, 1005: 2},
        3: {1001: 5, 1002: 1, 1005: 1},
        4: {1001: 0, 1002: 1},
        5: {1001: 0, 1002: 1},
    }
    picks_by_gw = {
        1: [(1001, 1), (1002, 2), (1003, 3), (1005, 5)],
        2: [(1001, 1), (1002, 2), (1003, 3), (1005, 5)],
        3: [(1001, 1), (1002, 2), (1005, 5)],
        4: [(1001, 1), (1002, 2)],
        5: [(1001, 1), (1002, 2)],
    }
    for gw in range(1, 6):
        _dump(root, f"live/gw{gw}.json",
              {"elements": {str(e): {"stats": {"total_points": v}} for e, v in live_by_gw[gw].items()}})
        picks = [{"element": el, "position": pos} for el, pos in picks_by_gw[gw]]
        _dump(root, f"entries/201/gw{gw}.json", {"picks": picks, "subs": [], "entry_history": {}})

# Four managers, gameweeks 1-4 finished, gameweek 5 in progress.
SCORES = [
    [50, 60, 40, 55],   # GW1: manager B wins by 5, C last
    [54, 70, 44, 50],   # GW2: B wins by 16, A includes a subbed-in bench player (9 pts)
    [65, 65, 30, 52],   # GW3: A and B tie for the win, C last
    [72, 48, 61, 55],   # GW4: A wins by 11, B last
    [20, 33, 10, 15],   # GW5: in progress, must not count towards records
]
TXS = [
    mock.tx(1, 2, 0, "f", "a", 100, 5),    # A: free agent, in-player scores 12 over GW2-4
    mock.tx(2, 1, 1, "w", "a", 101, 20),   # B: accepted waiver
    mock.tx(3, 3, 1, "w", "do", 102, 21),  # B: denied waiver
    mock.tx(4, 4, 3, "f", "a", 103, 50),   # D: free agent
    mock.tx(5, 4, 3, "f", "a", 104, 51),   # D: free agent
]
FA_POINTS = {(2, 0): 3, (3, 0): 8, (4, 0): 1}  # element 100 by gameweek


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        mock.write_raw(self.tmp, SCORES, subs={(2, 0): (5, 12)},
                       bench={**{(g, 3): 2 for g in range(1, 5)}, (2, 1): 14, (5, 0): 30},
                       transactions=TXS, free_agent_points=FA_POINTS,
                       official={(1, 0): 50})
        self.d = build_stats.build(self.tmp)
        self.m = {m["first"]: str(m["entry_id"]) for m in self.d["managers"]}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pm(self, name):
        return self.d["per_manager"][self.m[name]]

    def test_only_finished_rounds_count(self):
        self.assertEqual(self.d["trends"]["gws"], [1, 2, 3, 4])
        self.assertEqual(self.d["meta"]["last_finished_gw"], 4)
        self.assertEqual(self.d["live_round"]["gw"], 5)

    def test_totals_and_ranks(self):
        self.assertEqual([self.pm(n)["total"] for n in ("Alex", "Bo", "Cleo", "Dan")],
                         [241, 243, 175, 212])
        self.assertEqual([self.pm(n)["rank"] for n in ("Alex", "Bo", "Cleo", "Dan")], [2, 1, 4, 3])

    def test_rounds_won_with_tie_shared(self):
        self.assertEqual([self.pm(n)["wins"] for n in ("Alex", "Bo", "Cleo", "Dan")], [2, 3, 0, 0])
        self.assertEqual([self.pm(n)["lows"] for n in ("Alex", "Bo", "Cleo", "Dan")], [0, 1, 3, 0])
        self.assertEqual(self.d["records"]["ties_for_win"], 1)

    def test_substitution_is_applied(self):
        gw2 = next(r for r in self.d["rounds"] if r["gw"] == 2)
        self.assertEqual(gw2["scores"][self.m["Alex"]], 54)

    def test_records(self):
        r = self.d["records"]
        self.assertEqual((r["highest_round"]["points"], r["highest_round"]["gw"]), (72, 4))
        self.assertEqual((r["lowest_round"]["points"], r["lowest_round"]["gw"]), (30, 3))
        self.assertEqual((r["biggest_win"]["margin"], r["biggest_win"]["gw"]), (16, 2))
        self.assertEqual((r["closest_round"]["margin"], r["closest_round"]["gw"]), (0, 3))
        self.assertEqual(r["longest_win_streak"]["length"], 3)
        self.assertEqual(str(r["longest_win_streak"]["entry_id"]), self.m["Bo"])

    def test_cumulative_and_rank_trend(self):
        self.assertEqual(self.d["trends"]["cumulative"][self.m["Bo"]], [60, 130, 195, 243])
        self.assertEqual(self.d["trends"]["rank"][self.m["Bo"]], [1, 1, 1, 1])
        self.assertEqual(self.d["trends"]["cumulative"][self.m["Alex"]], [50, 104, 169, 241])
        # Running totals A/B/C/D: GW1 50/60/40/55, GW2 104/130/84/105,
        # GW3 169/195/114/157, GW4 241/243/175/212.
        self.assertEqual(self.d["trends"]["rank"][self.m["Alex"]], [3, 3, 2, 2])
        self.assertEqual(self.d["trends"]["rank"][self.m["Dan"]], [2, 2, 3, 3])

    def test_transactions_count_accepted_only(self):
        self.assertEqual([self.pm(n)["tx_accepted"] for n in ("Alex", "Bo", "Cleo", "Dan")], [1, 1, 0, 2])
        self.assertEqual(self.pm("Bo")["tx_denied"], 1)
        self.assertEqual(self.pm("Dan")["tx_free_agent"], 2)
        self.assertEqual(self.pm("Bo")["tx_waiver"], 1)

    def test_transaction_value(self):
        move = next(x for x in self.d["transactions"]["moves"] if x["id"] == 1)
        self.assertEqual(move["in_points"], 12)
        self.assertEqual(move["out_points"], 0)
        self.assertEqual(move["delta"], 12)
        denied = next(x for x in self.d["transactions"]["moves"] if x["id"] == 3)
        self.assertNotIn("delta", denied)

    def test_bench_points(self):
        self.assertEqual(self.d["players"]["bench"][self.m["Dan"]]["total"], 8)
        self.assertEqual(self.d["players"]["bench"][self.m["Alex"]]["total"], 0)

    def test_biggest_bench_misses(self):
        missed = self.d["players"]["missed"]
        # 14 pts for Bo in GW2 is the biggest; Dan's four 2-pt benchings follow.
        self.assertEqual((missed[0]["points"], missed[0]["gw"], str(missed[0]["entry_id"])),
                         (14, 2, self.m["Bo"]))
        self.assertEqual([r["points"] for r in missed], [14, 2, 2, 2, 2])
        # The 30 points on Alex's bench in GW5 are ignored: that round is not finished.
        self.assertTrue(all(r["gw"] <= 4 for r in missed))
        # Alex's subbed-in bench player (9 pts, GW2) started, so he is not a "miss".
        self.assertEqual([r for r in missed if r["entry_id"] == 101], [])
        # Bench totals and the ranked list agree.
        self.assertEqual(self.d["players"]["bench"][self.m["Bo"]]["total"], 14)

    def test_checks_pass_and_official_agrees(self):
        c = self.d["checks"]
        self.assertTrue(c["all_ok"], c)
        self.assertEqual(c["lineup_vs_official_mismatches"], [])
        self.assertTrue(all(x["matches"] for x in c["standings"]))

    def test_mismatch_is_reported(self):
        p = self.tmp / "entries" / "101" / "gw1.json"
        body = json.loads(p.read_text())
        body["entry_history"] = {"points": 99}
        p.write_text(json.dumps(body))
        d = build_stats.build(self.tmp)
        self.assertFalse(d["checks"]["all_ok"])
        self.assertEqual(d["checks"]["lineup_vs_official_mismatches"][0]["official"], 99)

    def test_bad_standings_are_flagged(self):
        d2 = tempfile.mkdtemp()
        try:
            mock.write_raw(d2, SCORES, standings_ok=False)
            out = build_stats.build(d2)
            self.assertFalse(out["checks"]["all_ok"])
        finally:
            shutil.rmtree(d2, ignore_errors=True)

    def test_finished_current_gameweek_counts(self):
        d2 = tempfile.mkdtemp()
        try:
            mock.write_raw(d2, SCORES, current_finished=True)
            out = build_stats.build(d2)
            self.assertEqual(out["trends"]["gws"], [1, 2, 3, 4, 5])
            self.assertIsNone(out["live_round"])
        finally:
            shutil.rmtree(d2, ignore_errors=True)


class LowScorersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        write_low_scorers_fixture(self.tmp)
        self.d = build_stats.build(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_threshold_is_60pct_of_finished_rounds_rounded_up(self):
        self.assertEqual(self.d["players"]["low_scorers_min_starts"], 3)

    def test_players_below_the_threshold_are_excluded(self):
        low = self.d["players"]["low_by_manager"]["201"]
        names = [p["name"] for p in low]
        self.assertNotIn("Cid", names)  # only 2 starts, despite scoring 40

    def test_lowest_scorers_ordered_by_points_then_starts(self):
        low = self.d["players"]["low_by_manager"]["201"]
        # Ben and Eve tie on 5 points; Ben started more rounds (5 vs 3) so
        # comes first. Ann (15 points) comes last.
        self.assertEqual([(p["name"], p["points"], p["starts"]) for p in low],
                         [("Ben", 5, 5), ("Eve", 5, 3), ("Ann", 15, 5)])

    def test_top_scorers_unaffected_by_the_threshold(self):
        top = self.d["players"]["top_by_manager"]["201"]
        # Cid tops the list despite starting only 2 of 5 rounds.
        self.assertEqual(top[0]["name"], "Cid")
        self.assertEqual(top[0]["points"], 40)


if __name__ == "__main__":
    unittest.main()
