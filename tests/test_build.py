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


def write_scorers_fixture(root):
    """Two managers, 5 finished gameweeks, hand-picked players so the merged
    "scorers by team" list can be checked exactly, including a player (Ann)
    who moves from team 201 to team 202 partway through the season.

    Team 201: Cid 20+20=40 pts (2 starts), Ann 5+5=10 pts (2 starts, then
    transferred away), Ben 1x5=5 pts (5 starts), F 1x5=5 pts, G 1x5=5 pts,
    H 1 pt (1 start) -- six scorers, proving the list isn't capped at 5.
    Dan starts every round but always scores 0, so he must NOT appear.

    Team 202: Eve 2x5=10 pts (5 starts), Ann (after the move) 3x3=9 pts
    (3 starts) -- Ann appearing here too is the multi-team case.
    """
    _dump(root, "game.json", {"current_event": 5, "current_event_finished": True})
    _dump(root, "bootstrap.json", {
        "elements": [
            {"id": 1001, "web_name": "Ann", "element_type": 1, "team": 1},
            {"id": 1002, "web_name": "Ben", "element_type": 1, "team": 1},
            {"id": 1003, "web_name": "Cid", "element_type": 1, "team": 1},
            {"id": 1005, "web_name": "Eve", "element_type": 1, "team": 1},
            {"id": 1006, "web_name": "Dan", "element_type": 1, "team": 1},
            {"id": 1007, "web_name": "Fay", "element_type": 1, "team": 1},
            {"id": 1008, "web_name": "Gus", "element_type": 1, "team": 1},
            {"id": 1009, "web_name": "Hal", "element_type": 1, "team": 1},
        ],
        "teams": [{"id": 1, "short_name": "ARS"}],
    })
    _dump(root, "transactions.json", [])
    _dump(root, "league_details.json", {
        "league": {"id": 1, "name": "Two-team League"},
        "league_entries": [
            {"entry_id": 201, "id": 9001, "entry_name": "Solo Team",
             "player_first_name": "Sam", "player_last_name": "Solo", "short_name": "SOL"},
            {"entry_id": 202, "id": 9002, "entry_name": "Second Team",
             "player_first_name": "Robin", "player_last_name": "Second", "short_name": "SEC"},
        ],
        "standings": [{"league_entry": 9001, "total": 0}, {"league_entry": 9002, "total": 0}],
    })
    live_by_gw = {
        1: {1001: 5, 1002: 1, 1003: 20, 1005: 2, 1006: 0, 1007: 1, 1008: 1, 1009: 1},
        2: {1001: 5, 1002: 1, 1003: 20, 1005: 2, 1006: 0, 1007: 1, 1008: 1},
        3: {1001: 3, 1002: 1, 1005: 2, 1006: 0, 1007: 1, 1008: 1},
        4: {1001: 3, 1002: 1, 1005: 2, 1006: 0, 1007: 1, 1008: 1},
        5: {1001: 3, 1002: 1, 1005: 2, 1006: 0, 1007: 1, 1008: 1},
    }
    picks_201_by_gw = {
        1: [(1001, 1), (1002, 2), (1003, 3), (1006, 4), (1007, 5), (1008, 6), (1009, 7)],
        2: [(1001, 1), (1002, 2), (1003, 3), (1006, 4), (1007, 5), (1008, 6)],
        3: [(1002, 2), (1006, 4), (1007, 5), (1008, 6)],
        4: [(1002, 2), (1006, 4), (1007, 5), (1008, 6)],
        5: [(1002, 2), (1006, 4), (1007, 5), (1008, 6)],
    }
    picks_202_by_gw = {
        1: [(1005, 1)],
        2: [(1005, 1)],
        3: [(1001, 1), (1005, 2)],
        4: [(1001, 1), (1005, 2)],
        5: [(1001, 1), (1005, 2)],
    }
    for gw in range(1, 6):
        _dump(root, f"live/gw{gw}.json",
              {"elements": {str(e): {"stats": {"total_points": v}} for e, v in live_by_gw[gw].items()}})
        for eid, picks_by_gw in ((201, picks_201_by_gw), (202, picks_202_by_gw)):
            picks = [{"element": el, "position": pos} for el, pos in picks_by_gw[gw]]
            _dump(root, f"entries/{eid}/gw{gw}.json", {"picks": picks, "subs": [], "entry_history": {}})

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
        # GW1-4 finished (241/243/175/212) plus GW5's live score
        # (20/33/10/15) -- the running total and standings order update
        # while a round is still in progress.
        self.assertEqual([self.pm(n)["total"] for n in ("Alex", "Bo", "Cleo", "Dan")],
                         [261, 276, 185, 227])
        self.assertEqual([self.pm(n)["rank"] for n in ("Alex", "Bo", "Cleo", "Dan")], [2, 1, 4, 3])

    def test_live_round_points_are_exposed_separately_from_total(self):
        self.assertEqual([self.pm(n)["live_points"] for n in ("Alex", "Bo", "Cleo", "Dan")],
                         [20, 33, 10, 15])

    def test_live_round_does_not_affect_finished_only_records(self):
        # Rounds won, best/worst round and the GW count stay finished-only;
        # only the running total/standings pick up the live score.
        self.assertEqual([self.pm(n)["rounds_played"] for n in ("Alex", "Bo", "Cleo", "Dan")],
                         [4, 4, 4, 4])
        self.assertEqual([self.pm(n)["wins"] for n in ("Alex", "Bo", "Cleo", "Dan")], [2, 3, 0, 0])

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

    def test_live_round_folds_into_scorer_table_starts_and_points(self):
        # Alex's primary scorer (element 1) started every gameweek including
        # the live GW5 -- the live score folds into both starts and points,
        # same as the Standings total.
        rows = {r["id"]: r for r in self.d["players"]["scorers_by_manager"][self.m["Alex"]]}
        self.assertEqual(rows[1]["starts"], 5)
        self.assertEqual(rows[1]["live_points"], 20)
        self.assertEqual(rows[1]["points"], 232 + 20)

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

    def test_scorer_rows_flag_whether_the_player_is_still_on_the_squad(self):
        d2 = tempfile.mkdtemp()
        try:
            # One finished gameweek, two managers; a GW1 substitution gives
            # manager 0 (Alex, element 1 is their main scorer) a second
            # scorer, element 12 -- still owned per element_status, element
            # 12 has since been dropped (a free agent now).
            mock.write_raw(d2, [[50, 40]], current_finished=True,
                           subs={(1, 0): (2, 12)},
                           element_status=[
                               {"element": 1, "owner": 101, "status": "o"},
                               {"element": 12, "owner": None, "status": "a"},
                           ])
            out = build_stats.build(d2)
            rows = {r["id"]: r for r in out["players"]["scorers_by_manager"]["101"]}
            self.assertTrue(rows[1]["on_squad"])
            self.assertFalse(rows[12]["on_squad"])
        finally:
            shutil.rmtree(d2, ignore_errors=True)

    def test_finished_current_gameweek_counts(self):
        d2 = tempfile.mkdtemp()
        try:
            mock.write_raw(d2, SCORES, current_finished=True)
            out = build_stats.build(d2)
            self.assertEqual(out["trends"]["gws"], [1, 2, 3, 4, 5])
            self.assertIsNone(out["live_round"])
            # No live round once GW5 is finished -- it's already folded into
            # the finished total like any other round, not tracked separately.
            self.assertTrue(all(pm["live_points"] is None for pm in out["per_manager"].values()))
        finally:
            shutil.rmtree(d2, ignore_errors=True)


class EarlyTransactionGameweekTest(unittest.TestCase):
    """Waivers/free-agent moves for the next gameweek are often accepted
    before the draft API's own "current_event" rolls over to it (e.g. GW5 is
    the last one finished, but GW6's waivers already ran) -- that gameweek
    must still show up for filtering/display, without being flagged as a
    missing lineup, since no one has lineups for a gameweek that hasn't
    started yet."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        txs = TXS + [mock.tx(6, 6, 0, "w", "a", 105, 52)]  # GW6: manager A, accepted waiver
        mock.write_raw(self.tmp, SCORES, current_finished=False, transactions=txs)
        self.d = build_stats.build(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_early_gameweek_appears_as_an_unfinished_round(self):
        self.assertEqual(self.d["meta"]["current_gw"], 5)
        gws = [r["gw"] for r in self.d["rounds"]]
        self.assertIn(6, gws)
        gw6 = next(r for r in self.d["rounds"] if r["gw"] == 6)
        self.assertFalse(gw6["finished"])
        self.assertTrue(all(v is None for v in gw6["scores"].values()))

    def test_it_is_not_reported_as_a_missing_lineup(self):
        self.assertEqual(self.d["checks"]["missing_lineups"], [])
        self.assertTrue(self.d["checks"]["all_ok"])

    def test_its_accepted_move_is_counted_in_the_transactions_matrix(self):
        entry_id = str(self.d["managers"][0]["entry_id"])
        self.assertEqual(self.d["transactions"]["matrix"][entry_id]["6"], 1)


def write_live_round_fixture(root):
    """Two managers plus a free agent, for the Live round tab:

    Manager 201's squad: 1001 (GK, captain, in the XI), 1002 (DEF, vice
    captain, in the XI), 1003 (MID, on the bench).
    Manager 202's squad: 1004 (FWD, captain, in the XI) -- and NO gw3 picks
    file at all, to check a manager with no lineup yet doesn't crash the
    build.
    1005 is a free agent (never owned), to check it still appears in the
    round's "all_players" list with no owner.
    """
    _dump(root, "game.json", {"current_event": 3, "current_event_finished": False})
    _dump(root, "bootstrap.json", {
        "elements": [
            {"id": 1001, "web_name": "Gio", "element_type": 1, "team": 1},
            {"id": 1002, "web_name": "Dex", "element_type": 2, "team": 1},
            {"id": 1003, "web_name": "Milo", "element_type": 3, "team": 1},
            {"id": 1004, "web_name": "Fox", "element_type": 4, "team": 2},
            {"id": 1005, "web_name": "Ray", "element_type": 4, "team": 2},
        ],
        "teams": [{"id": 1, "short_name": "ARS"}, {"id": 2, "short_name": "AVL"}],
    })
    _dump(root, "live/gw3.json", {"elements": {
        "1001": {"stats": {"total_points": 10, "minutes": 90, "goals_scored": 0, "assists": 1,
                            "clean_sheets": 1, "defensive_contribution": 2}},
        "1002": {"stats": {"total_points": 5, "minutes": 90, "goals_scored": 1, "assists": 0,
                            "clean_sheets": 0, "defensive_contribution": 0}},
        "1003": {"stats": {"total_points": 2, "minutes": 10, "goals_scored": 0, "assists": 0,
                            "clean_sheets": 0, "defensive_contribution": 0}},
        "1004": {"stats": {"total_points": 8, "minutes": 90, "goals_scored": 1, "assists": 0,
                            "clean_sheets": 0, "defensive_contribution": 0}},
        "1005": {"stats": {"total_points": 3, "minutes": 45, "goals_scored": 0, "assists": 0,
                            "clean_sheets": 0, "defensive_contribution": 1}},
    }})
    _dump(root, "entries/201/gw3.json", {"picks": [
        {"element": 1001, "position": 1, "multiplier": 2, "is_captain": True, "is_vice_captain": False},
        {"element": 1002, "position": 2, "multiplier": 1, "is_captain": False, "is_vice_captain": True},
        {"element": 1003, "position": 12, "multiplier": 1, "is_captain": False, "is_vice_captain": False},
    ], "subs": [], "entry_history": {}})
    # No entries/202/gw3.json at all -- manager 202's lineup isn't in yet.
    _dump(root, "element_status.json", {"element_status": [
        {"element": 1001, "owner": 201, "status": "o"},
        {"element": 1002, "owner": 201, "status": "o"},
        {"element": 1003, "owner": 201, "status": "o"},
        {"element": 1004, "owner": 202, "status": "o"},
        {"element": 1005, "owner": None, "status": "a"},
    ]})
    _dump(root, "transactions.json", [])
    _dump(root, "draft_choices.json", [])
    _dump(root, "league_details.json", {
        "league": {"id": 1, "name": "Live Round League"},
        "league_entries": [
            {"entry_id": 201, "id": 9001, "entry_name": "Solo Team",
             "player_first_name": "Sam", "player_last_name": "Solo", "short_name": "SOL"},
            {"entry_id": 202, "id": 9002, "entry_name": "Second Team",
             "player_first_name": "Robin", "player_last_name": "Second", "short_name": "SEC"},
        ],
        "standings": [{"league_entry": 9001, "total": 0}, {"league_entry": 9002, "total": 0}],
    })


def write_auto_sub_fixture(root, keeper_minutes=90, bench_keeper_minutes=90):
    """One manager, one gameweek still in progress (the draft API hasn't
    filled in "subs" yet): two starting midfielders didn't play (0
    minutes), and so did the first two bench outfielders -- only the
    last bench slot (a defender who played) is a usable substitute.
    Mirrors a real case reported against the live dashboard (multiple
    blanks in the XI, with the bench itself mostly blank too)."""
    _dump(root, "game.json", {"current_event": 1, "current_event_finished": False})
    _dump(root, "bootstrap.json", {
        "elements": [
            {"id": 1, "web_name": "Keeper", "element_type": 1, "team": 1},
            {"id": 2, "web_name": "Defender", "element_type": 2, "team": 1},
            {"id": 3, "web_name": "BlankMidA", "element_type": 3, "team": 1},
            {"id": 4, "web_name": "BlankMidB", "element_type": 3, "team": 1},
            {"id": 5, "web_name": "Striker", "element_type": 4, "team": 1},
            {"id": 12, "web_name": "BenchKeeper", "element_type": 1, "team": 1},
            {"id": 13, "web_name": "BlankSubA", "element_type": 2, "team": 1},
            {"id": 14, "web_name": "BlankSubB", "element_type": 3, "team": 1},
            {"id": 15, "web_name": "UsableSub", "element_type": 2, "team": 1},
        ],
        "teams": [{"id": 1, "short_name": "ARS"}],
    })
    _dump(root, "live/gw1.json", {"elements": {
        "1": {"stats": {"total_points": 2 if keeper_minutes else 0, "minutes": keeper_minutes}},
        "2": {"stats": {"total_points": 6, "minutes": 90}},
        "3": {"stats": {"total_points": 0, "minutes": 0}},
        "4": {"stats": {"total_points": 0, "minutes": 0}},
        "5": {"stats": {"total_points": 4, "minutes": 90}},
        "12": {"stats": {"total_points": 2 if bench_keeper_minutes else 0, "minutes": bench_keeper_minutes}},
        "13": {"stats": {"total_points": 0, "minutes": 0}},
        "14": {"stats": {"total_points": 0, "minutes": 0}},
        "15": {"stats": {"total_points": 9, "minutes": 90}},
    }})
    _dump(root, "entries/201/gw1.json", {"picks": [
        {"element": 1, "position": 1, "multiplier": 1, "is_captain": False, "is_vice_captain": False},
        {"element": 2, "position": 2, "multiplier": 1, "is_captain": False, "is_vice_captain": False},
        {"element": 3, "position": 6, "multiplier": 1, "is_captain": False, "is_vice_captain": False},
        {"element": 4, "position": 8, "multiplier": 1, "is_captain": False, "is_vice_captain": False},
        {"element": 5, "position": 10, "multiplier": 1, "is_captain": False, "is_vice_captain": False},
        {"element": 12, "position": 12, "multiplier": 1, "is_captain": False, "is_vice_captain": False},
        {"element": 13, "position": 13, "multiplier": 1, "is_captain": False, "is_vice_captain": False},
        {"element": 14, "position": 14, "multiplier": 1, "is_captain": False, "is_vice_captain": False},
        {"element": 15, "position": 15, "multiplier": 1, "is_captain": False, "is_vice_captain": False},
    ], "subs": [], "entry_history": {}})
    _dump(root, "transactions.json", [])
    _dump(root, "element_status.json", {"element_status": []})
    _dump(root, "draft_choices.json", [])
    _dump(root, "league_details.json", {
        "league": {"id": 1, "name": "Sub League"},
        "league_entries": [{"entry_id": 201, "id": 9001, "entry_name": "Solo Team",
                            "player_first_name": "Sam", "player_last_name": "Solo", "short_name": "SOL"}],
        "standings": [{"league_entry": 9001, "total": 0}],
    })


class ProvisionalAutoSubTest(unittest.TestCase):
    """When a gameweek is still in progress, the draft API's own "subs"
    list is empty -- build_stats must apply the same automatic
    substitution rule itself, rather than just summing blanks as 0."""
    def score(self, **kwargs):
        tmp = Path(tempfile.mkdtemp())
        try:
            write_auto_sub_fixture(tmp, **kwargs)
            d = build_stats.build(tmp)
            return d["rounds"][0]["scores"]["201"]
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cascades_past_blank_bench_players_to_the_first_one_who_played(self):
        # Raw XI (no subs) would be 2+6+0+0+4 = 12. Both bench outfielders
        # ahead of the usable one are themselves blank, so only one swap
        # actually happens -- the usable sub's 9 points come in once,
        # covering one of the two blank midfielders; the other stays blank.
        self.assertEqual(self.score(), 12 + 9)

    def test_the_live_round_tab_lineup_reflects_the_same_substitution(self):
        # The pitch view in the Live round tab has its own, separate read
        # of the lineup -- it must show the same substitution (the usable
        # sub actually in the XI, not the blank they replaced), so what's
        # displayed always adds up to the same total shown alongside it.
        tmp = Path(tempfile.mkdtemp())
        try:
            write_auto_sub_fixture(tmp)
            d = build_stats.build(tmp)
            team = d["current_round"]["teams"][0]
            xi_names = {p["name"] for p in team["xi"]}
            bench_names = {p["name"] for p in team["bench"]}
            self.assertIn("UsableSub", xi_names)
            self.assertIn("BlankSubA", bench_names)
            self.assertIn("BlankSubB", bench_names)
            self.assertEqual(sum(p["points"] for p in team["xi"]), team["score"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_bench_player_who_also_has_0_minutes_is_not_a_valid_substitute(self):
        # If the single usable bench player is removed (also blanked),
        # neither blank midfielder can be covered, so the score is just
        # the raw sum with both blanks still at 0.
        tmp = Path(tempfile.mkdtemp())
        try:
            write_auto_sub_fixture(tmp)
            live_path = tmp / "live" / "gw1.json"
            live = json.loads(live_path.read_text())
            live["elements"]["15"]["stats"]["minutes"] = 0
            live_path.write_text(json.dumps(live))
            d = build_stats.build(tmp)
            self.assertEqual(d["rounds"][0]["scores"]["201"], 12)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_blank_keeper_is_only_ever_covered_by_the_bench_keeper(self):
        # Starting keeper blanks (0 pts); the bench keeper played and
        # scored 2, so their points replace the keeper's -- on top of
        # the outfield sub (Defender 6 + UsableSub 9 + Striker 4).
        self.assertEqual(self.score(keeper_minutes=0), 2 + 6 + 9 + 4)

    def test_a_bench_keeper_who_also_blanked_cannot_cover_the_keeper(self):
        # Neither keeper played, so no swap happens and the keeper slot
        # stays at 0 -- only the outfield sub still applies.
        self.assertEqual(self.score(keeper_minutes=0, bench_keeper_minutes=0), 0 + 6 + 9 + 4)

    def test_official_subs_from_the_api_are_still_preferred_once_present(self):
        # Once the gameweek is finished, the draft API provides its own
        # authoritative "subs" -- build_stats must use that instead of
        # computing its own, even if it looks different.
        tmp = Path(tempfile.mkdtemp())
        try:
            write_auto_sub_fixture(tmp)
            game_path = tmp / "game.json"
            game_path.write_text(json.dumps({"current_event": 1, "current_event_finished": True}))
            entry_path = tmp / "entries" / "201" / "gw1.json"
            data = json.loads(entry_path.read_text())
            data["subs"] = [{"element_out": 4, "element_in": 12, "event": 1}]
            entry_path.write_text(json.dumps(data))
            d = build_stats.build(tmp)
            # Official subs swap element 4 (blank) for element 12 (2 pts),
            # not element 15 -- a different result than our own rule would
            # give, proving the official data wins.
            self.assertEqual(d["rounds"][0]["scores"]["201"], 12 + 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_sites_own_unsubbed_live_total_is_not_flagged_as_a_mismatch(self):
        # The site's own "total" reflects the raw (unsubbed) live score
        # (12) -- it hasn't caught up with our own, correctly-subbed one
        # (21) yet. That's expected while the round is live, not a real
        # problem, so "Data checks" should still pass.
        tmp = Path(tempfile.mkdtemp())
        try:
            write_auto_sub_fixture(tmp)
            league_path = tmp / "league_details.json"
            data = json.loads(league_path.read_text())
            data["standings"][0]["total"] = 12
            data["standings"][0]["event_total"] = 12
            league_path.write_text(json.dumps(data))
            d = build_stats.build(tmp)
            check = d["checks"]["standings"][0]
            self.assertEqual(check["matches"], "through_finished_plus_live_unsubbed")
            self.assertTrue(d["checks"]["all_ok"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_genuine_standings_mismatch_is_still_flagged(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            write_auto_sub_fixture(tmp)
            league_path = tmp / "league_details.json"
            data = json.loads(league_path.read_text())
            data["standings"][0]["total"] = 999  # agrees with no formula
            data["standings"][0]["event_total"] = 5
            league_path.write_text(json.dumps(data))
            d = build_stats.build(tmp)
            check = d["checks"]["standings"][0]
            self.assertIsNone(check["matches"])
            self.assertFalse(d["checks"]["all_ok"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def write_best_rounds_fixture(root):
    """One manager, two gameweeks: GW1 finished (a modest score), GW2 live
    (a much bigger one) for the same player -- proves the live round's
    performance isn't just included in "best_rounds" but properly ranked
    against finished rounds, not merely tacked on at the end."""
    _dump(root, "game.json", {"current_event": 2, "current_event_finished": False})
    _dump(root, "bootstrap.json", {
        "elements": [{"id": 1, "web_name": "Star", "element_type": 4, "team": 1}],
        "teams": [{"id": 1, "short_name": "ARS"}],
    })
    _dump(root, "live/gw1.json", {"elements": {"1": {"stats": {"total_points": 10, "minutes": 90}}}})
    _dump(root, "live/gw2.json", {"elements": {"1": {"stats": {"total_points": 25, "minutes": 90}}}})
    picks = [{"element": 1, "position": 1, "multiplier": 1, "is_captain": False, "is_vice_captain": False}]
    _dump(root, "entries/201/gw1.json", {"picks": picks, "subs": [], "entry_history": {}})
    _dump(root, "entries/201/gw2.json", {"picks": picks, "subs": [], "entry_history": {}})
    _dump(root, "transactions.json", [])
    _dump(root, "element_status.json", {"element_status": []})
    _dump(root, "draft_choices.json", [])
    _dump(root, "league_details.json", {
        "league": {"id": 1, "name": "Best Rounds League"},
        "league_entries": [{"entry_id": 201, "id": 9001, "entry_name": "Solo Team",
                            "player_first_name": "Sam", "player_last_name": "Solo", "short_name": "SOL"}],
        "standings": [{"league_entry": 9001, "total": 0}],
    })


class BestRoundsLiveTest(unittest.TestCase):
    def test_the_live_rounds_performance_is_included_and_properly_ranked(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            write_best_rounds_fixture(tmp)
            d = build_stats.build(tmp)
            best = d["players"]["best_rounds"]
            self.assertEqual((best[0]["gw"], best[0]["points"]), (2, 25))
            self.assertEqual((best[1]["gw"], best[1]["points"]), (1, 10))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TableOfJusticeTest(unittest.TestCase):
    """Three managers, two finished gameweeks. Season totals are Bravo
    120 > Alex 95 > Cleo 90, but Cleo's gw1 bench (30) is large enough
    that total-plus-bench reorders her above Alex, so the table should
    show both a "robbed" (Cleo) and a "blessed" (Alex) manager."""

    def test_standings_are_reordered_by_total_plus_bench_points(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            mock.write_raw(
                tmp,
                gw_scores=[[40, 50, 60], [55, 70, 30]],
                current_finished=True,
                bench={(1, 2): 30, (2, 0): 20, (2, 1): 2, (2, 2): 1},
                people=[("Alex", "A.", "Team Alpha"), ("Bo", "B.", "Team Bravo"), ("Cleo", "C.", "Team Charlie")],
            )
            d = build_stats.build(tmp)
            by_team = {m["team"]: m["entry_id"] for m in d["managers"]}
            justice_by_id = {j["entry_id"]: j for j in d["justice"]}

            bravo = justice_by_id[by_team["Team Bravo"]]
            alpha = justice_by_id[by_team["Team Alpha"]]
            charlie = justice_by_id[by_team["Team Charlie"]]

            self.assertEqual(bravo["deserved_rank"], 1)
            self.assertEqual(bravo["luck_delta"], 0)

            self.assertEqual(charlie["deserved_total"], 90 + 31)
            self.assertEqual(charlie["deserved_rank"], 2)
            self.assertEqual(charlie["actual_rank"], 3)
            self.assertEqual(charlie["luck_delta"], 1)  # robbed

            self.assertEqual(alpha["deserved_total"], 95 + 20)
            self.assertEqual(alpha["deserved_rank"], 3)
            self.assertEqual(alpha["actual_rank"], 2)
            self.assertEqual(alpha["luck_delta"], -1)  # blessed

            # d["justice"] itself is already sorted by deserved rank
            self.assertEqual([j["entry_id"] for j in d["justice"]],
                              [by_team["Team Bravo"], by_team["Team Charlie"], by_team["Team Alpha"]])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class StreaksAndMilestonesTest(unittest.TestCase):
    """Three managers, four finished gameweeks, scores picked so each
    streak type breaks and restarts at least once (proving "current" and
    "best" are tracked separately), and so the 100/200-point milestones
    land in different gameweeks for each manager, including a manager
    (Charlie) who never reaches the 200 threshold at all."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        mock.write_raw(
            self.tmp,
            gw_scores=[[60, 50, 40], [70, 50, 40], [30, 80, 40], [90, 20, 50]],
            current_finished=True,
            people=[("Alex", "A.", "Team Alpha"), ("Bo", "B.", "Team Bravo"), ("Cleo", "C.", "Team Charlie")],
        )
        self.d = build_stats.build(self.tmp)
        self.by_team = {m["team"]: m["entry_id"] for m in self.d["managers"]}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_win_streak_breaks_and_restarts(self):
        # Alpha wins gw1+gw2 (streak 2), is last in gw3 (breaks), wins gw4
        # again (restarts at 1) -- best must stay 2, current must be 1.
        win = self.d["streaks"]["win"][str(self.by_team["Team Alpha"])]
        self.assertEqual(win, {"current": 1, "best": 2})

    def test_top2_and_cold_streaks_per_manager(self):
        s = self.d["streaks"]
        alpha, bravo, charlie = (str(self.by_team[t]) for t in ("Team Alpha", "Team Bravo", "Team Charlie"))
        self.assertEqual(s["top2"][alpha], {"current": 1, "best": 2})
        self.assertEqual(s["cold"][alpha], {"current": 0, "best": 1})

        self.assertEqual(s["win"][bravo], {"current": 0, "best": 1})
        self.assertEqual(s["top2"][bravo], {"current": 0, "best": 3})
        self.assertEqual(s["cold"][bravo], {"current": 1, "best": 1})

        self.assertEqual(s["win"][charlie], {"current": 0, "best": 0})
        self.assertEqual(s["top2"][charlie], {"current": 2, "best": 2})
        self.assertEqual(s["cold"][charlie], {"current": 0, "best": 2})

    def test_milestones_are_the_gameweek_each_threshold_was_first_crossed(self):
        alpha, bravo, charlie = (str(self.by_team[t]) for t in ("Team Alpha", "Team Bravo", "Team Charlie"))
        m = self.d["milestones"]
        # Alpha: 60, 130, 160, 250 -- crosses 100 in gw2, 200 in gw4.
        self.assertEqual(m[alpha], [{"threshold": 100, "gw": 2}, {"threshold": 200, "gw": 4}])
        # Bravo: 50, 100, 180, 200 -- crosses 100 in gw2, 200 in gw4.
        self.assertEqual(m[bravo], [{"threshold": 100, "gw": 2}, {"threshold": 200, "gw": 4}])
        # Charlie: 40, 80, 120, 170 -- crosses 100 in gw3, never reaches 200.
        self.assertEqual(m[charlie], [{"threshold": 100, "gw": 3}])


class WeeklyAwardsTest(unittest.TestCase):
    """Four managers (the default mock.py line-up), two finished gameweeks.
    GW1 establishes a baseline rank order with no climber/faller to
    compare against (first gameweek). GW2's scores are picked so Alpha's
    rank climb (+3) and Delta's rank fall (-2) are each unambiguously the
    biggest -- no ties to worry about -- and bench points differ enough
    each gameweek that bench_flop has a clear, distinct winner too."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        mock.write_raw(
            self.tmp,
            gw_scores=[[40, 50, 60, 70], [80, 30, 55, 45]],
            current_finished=True,
            bench={(1, 0): 1, (1, 1): 2, (1, 2): 3, (1, 3): 4,
                   (2, 0): 5, (2, 1): 3, (2, 2): 9, (2, 3): 2},
        )
        self.d = build_stats.build(self.tmp)
        self.by_team = {m["team"]: m["entry_id"] for m in self.d["managers"]}
        self.awards = self.d["weekly_awards"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_first_gameweek_has_no_climber_or_faller(self):
        wk1 = self.awards[0]
        self.assertEqual(wk1["gw"], 1)
        self.assertEqual(wk1["top_scorer"], {"entry_id": self.by_team["Team Delta"], "points": 70})
        self.assertEqual(wk1["wooden_spoon"], {"entry_id": self.by_team["Team Alpha"], "points": 40})
        self.assertEqual(wk1["bench_flop"], {"entry_id": self.by_team["Team Delta"], "points": 4})
        self.assertIsNone(wk1["climber"])
        self.assertIsNone(wk1["faller"])

    def test_second_gameweek_awards_and_unambiguous_climber_faller(self):
        wk2 = self.awards[1]
        self.assertEqual(wk2["gw"], 2)
        self.assertEqual(wk2["top_scorer"], {"entry_id": self.by_team["Team Alpha"], "points": 80})
        self.assertEqual(wk2["wooden_spoon"], {"entry_id": self.by_team["Team Bravo"], "points": 30})
        self.assertEqual(wk2["bench_flop"], {"entry_id": self.by_team["Team Charlie"], "points": 9})
        # Alpha: last (4th) in gw1 -> 1st in gw2, a 3-place climb.
        self.assertEqual(wk2["climber"], {"entry_id": self.by_team["Team Alpha"], "delta": 3})
        # Delta: 1st in gw1 -> 3rd in gw2, a 2-place fall.
        self.assertEqual(wk2["faller"], {"entry_id": self.by_team["Team Delta"], "delta": 2})


class LiveRoundTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        write_live_round_fixture(self.tmp)
        self.d = build_stats.build(self.tmp)
        self.cr = self.d["current_round"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def team(self, entry_id):
        return next(t for t in self.cr["teams"] if t["entry_id"] == entry_id)

    def test_gw_and_finished_flag(self):
        self.assertEqual(self.cr["gw"], 3)
        self.assertFalse(self.cr["finished"])

    def test_xi_and_bench_split_by_squad_position(self):
        t = self.team(201)
        self.assertEqual([p["id"] for p in t["xi"]], [1001, 1002])
        self.assertEqual([p["id"] for p in t["bench"]], [1003])

    def test_captain_and_vice_captain_flags(self):
        t = self.team(201)
        gio, dex = t["xi"][0], t["xi"][1]
        self.assertTrue(gio["is_captain"])
        self.assertFalse(gio["is_vice_captain"])
        self.assertTrue(dex["is_vice_captain"])
        self.assertFalse(dex["is_captain"])

    def test_points_and_extra_stats_come_from_the_live_file(self):
        gio = self.team(201)["xi"][0]
        self.assertEqual(gio["points"], 10)
        self.assertEqual(gio["minutes"], 90)
        self.assertEqual(gio["assists"], 1)
        self.assertEqual(gio["clean_sheets"], 1)
        self.assertEqual(gio["defensive_contribution"], 2)

    def test_team_score_is_the_same_as_the_round_score(self):
        self.assertEqual(self.team(201)["score"], self.d["rounds"][-1]["scores"]["201"])

    def test_a_manager_with_no_lineup_yet_has_an_empty_squad_not_a_crash(self):
        t = self.team(202)
        # Manager 202 has no entries/202/gw3.json at all.
        self.assertEqual(t["xi"], [])
        self.assertEqual(t["bench"], [])

    def test_all_players_includes_free_agents_sorted_by_points_desc(self):
        ids = [p["id"] for p in self.cr["all_players"]]
        self.assertEqual(ids, [1001, 1004, 1002, 1005, 1003])
        ray = next(p for p in self.cr["all_players"] if p["id"] == 1005)
        self.assertIsNone(ray["owner_entry_id"])
        self.assertEqual(ray["points"], 3)


def write_all_players_fixture(root):
    """A minimal league (no gameweeks played yet) with four Premier League
    players in different ownership/draft situations, to check the "all
    players" list independently of the scoring logic:

    PlayerA (501): drafted 1st overall, currently owned by entry 101.
        points_per_game present.
    PlayerB (502): drafted 2nd overall, but was dropped by entry 101 later
        (an accepted transaction) -- a free agent now, still "ever owned".
    PlayerC (503): never drafted, never owned, never transacted -- a pure
        free agent. points_per_game is blank, so the average falls back
        to total_points / starts.
    PlayerD (504): drafted in round 2, pick 1 of that round -- but the
        draft API resets "pick" every round, so the real (overall) draft
        rank is "index", not "pick". Never owned or transacted since, so
        "ever_owned" must come from the draft history alone.
    """
    _dump(root, "game.json", {"current_event": 0, "current_event_finished": False})
    _dump(root, "bootstrap.json", {
        "elements": [
            {"id": 501, "web_name": "Ann", "element_type": 1, "team": 1,
             "total_points": 80, "points_per_game": "8.0", "starts": 10},
            {"id": 502, "web_name": "Ben", "element_type": 2, "team": 2,
             "total_points": 30, "points_per_game": None, "starts": 5},
            {"id": 503, "web_name": "Cid", "element_type": 3, "team": 1,
             "total_points": 10, "points_per_game": "", "starts": 0},
            {"id": 504, "web_name": "Dez", "element_type": 4, "team": 2,
             "total_points": 20, "points_per_game": "4.0", "starts": 5},
        ],
        "teams": [{"id": 1, "short_name": "ARS"}, {"id": 2, "short_name": "AVL"}],
    })
    _dump(root, "element_status.json", {"element_status": [
        {"element": 501, "owner": 101, "status": "o"},
        {"element": 502, "owner": None, "status": "a"},
        {"element": 503, "owner": None, "status": "a"},
        {"element": 504, "owner": None, "status": "a"},
    ]})
    _dump(root, "transactions.json", [
        {"id": 1, "event": 1, "entry": 101, "kind": "f", "result": "a",
         "element_in": 501, "element_out": 502, "added": "2026-08-01T10:00:00Z"},
    ])
    _dump(root, "draft_choices.json", {"choices": [
        {"element": 501, "entry": 101, "round": 1, "pick": 1, "index": 1},
        {"element": 502, "entry": 102, "round": 1, "pick": 2, "index": 2},
        {"element": 504, "entry": 102, "round": 2, "pick": 1, "index": 5},
    ]})
    _dump(root, "league_details.json", {
        "league": {"id": 1, "name": "Solo League"},
        "league_entries": [{"entry_id": 101, "id": 9001, "entry_name": "Solo Team",
                            "player_first_name": "Sam", "player_last_name": "Solo",
                            "short_name": "SOL"}],
        "standings": [{"league_entry": 9001, "total": 0}],
    })


class AllPlayersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        write_all_players_fixture(self.tmp)
        self.d = build_stats.build(self.tmp)
        self.by_id = {p["id"]: p for p in self.d["all_players"]}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_current_round_before_any_gameweek_starts(self):
        self.assertIsNone(self.d["current_round"])

    def test_every_bootstrap_player_is_included(self):
        self.assertEqual(set(self.by_id), {501, 502, 503, 504})

    def test_draft_pick_uses_overall_index_not_the_per_round_pick(self):
        # Player D was pick 1 of round 2, which resets each round -- the
        # real overall draft rank is index 5, not the per-round pick 1.
        self.assertEqual(self.by_id[504]["draft_pick"], 5)
        self.assertEqual(self.by_id[501]["draft_pick"], 1)
        self.assertEqual(self.by_id[502]["draft_pick"], 2)

    def test_undrafted_player_has_no_draft_pick(self):
        self.assertIsNone(self.by_id[503]["draft_pick"])

    def test_ever_owned_via_draft_history_alone(self):
        # Player D was drafted but never appears in element_status or a
        # transaction since -- draft history alone must mark it "ever owned".
        self.assertTrue(self.by_id[504]["ever_owned"])
        self.assertIsNone(self.by_id[504]["owner_entry_id"])  # currently a free agent

    def test_owner_is_the_current_owner_not_who_drafted_or_traded_them(self):
        self.assertEqual(self.by_id[501]["owner_entry_id"], 101)
        self.assertIsNone(self.by_id[502]["owner_entry_id"])  # dropped, now a free agent
        self.assertIsNone(self.by_id[503]["owner_entry_id"])

    def test_ever_owned_covers_current_owners_and_past_transactions(self):
        self.assertTrue(self.by_id[501]["ever_owned"])
        self.assertTrue(self.by_id[502]["ever_owned"])   # free agent now, but was traded
        self.assertFalse(self.by_id[503]["ever_owned"])  # untouched all season

    def test_average_uses_points_per_game_when_present(self):
        self.assertEqual(self.by_id[501]["avg_points"], 8.0)

    def test_average_falls_back_to_total_points_over_starts(self):
        self.assertEqual(self.by_id[502]["avg_points"], 6.0)  # 30 / 5

    def test_average_is_zero_not_a_crash_when_starts_is_zero(self):
        self.assertEqual(self.by_id[503]["avg_points"], 0.0)

    def test_name_club_and_position_come_from_bootstrap(self):
        self.assertEqual((self.by_id[501]["name"], self.by_id[501]["club"], self.by_id[501]["pos"]),
                         ("Ann", "ARS", "GKP"))
        self.assertEqual(self.by_id[502]["pos"], "DEF")
        self.assertEqual(self.by_id[503]["pos"], "MID")


class ScorersByTeamTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        write_scorers_fixture(self.tmp)
        self.d = build_stats.build(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_all_scorers_included_not_just_top_5(self):
        team201 = self.d["players"]["scorers_by_manager"]["201"]
        self.assertEqual(len(team201), 6)

    def test_zero_point_players_are_excluded(self):
        team201 = self.d["players"]["scorers_by_manager"]["201"]
        self.assertNotIn("Dan", [p["name"] for p in team201])

    def test_ordered_by_points_desc_then_name(self):
        team201 = self.d["players"]["scorers_by_manager"]["201"]
        self.assertEqual([(p["name"], p["points"], p["starts"]) for p in team201],
                         [("Cid", 40, 2), ("Ann", 10, 2), ("Ben", 5, 5),
                          ("Fay", 5, 5), ("Gus", 5, 5), ("Hal", 1, 1)])

    def test_transferred_player_appears_under_both_teams(self):
        team201 = {p["name"]: p for p in self.d["players"]["scorers_by_manager"]["201"]}
        team202 = {p["name"]: p for p in self.d["players"]["scorers_by_manager"]["202"]}
        self.assertEqual((team201["Ann"]["points"], team201["Ann"]["starts"]), (10, 2))
        self.assertEqual((team202["Ann"]["points"], team202["Ann"]["starts"]), (9, 3))

    def test_no_leftover_low_scorer_fields(self):
        self.assertNotIn("low_by_manager", self.d["players"])
        self.assertNotIn("low_scorers_min_starts", self.d["players"])
        self.assertNotIn("top_by_manager", self.d["players"])


# Four real Premier League teams (distinct from the fantasy ones above), to
# check the "next 5 fixtures" / "favourite" logic in isolation.
# SFC is strong everywhere, WFC is weak everywhere, MFC and EFC are
# identically mid-strength (an exact tie, on purpose).
CLASSIC_TEAMS = [
    {"id": 1, "name": "Strong FC", "short_name": "SFC", "strength_overall_home": 5, "strength_overall_away": 4},
    {"id": 2, "name": "Weak FC", "short_name": "WFC", "strength_overall_home": 2, "strength_overall_away": 1},
    {"id": 3, "name": "Mid FC", "short_name": "MFC", "strength_overall_home": 3, "strength_overall_away": 3},
    {"id": 4, "name": "Even FC", "short_name": "EFC", "strength_overall_home": 3, "strength_overall_away": 3},
]


def _fixture(event, team_h, team_a, kickoff, h_diff=3, a_diff=3):
    return {"event": event, "team_h": team_h, "team_a": team_a, "kickoff_time": kickoff,
            "team_h_difficulty": h_diff, "team_a_difficulty": a_diff, "finished": False}


class FixturesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        fixtures = [
            _fixture(7, 1, 2, "2026-10-17T11:30:00Z", h_diff=1, a_diff=5),   # SFC(H) vs WFC(A)
            _fixture(8, 2, 1, "2026-10-24T11:30:00Z", h_diff=5, a_diff=1),   # WFC(H) vs SFC(A)
            _fixture(9, 3, 1, "2026-10-31T11:30:00Z"),                      # MFC(H) vs SFC(A)
            _fixture(7, 3, 4, "2026-10-17T14:00:00Z"),                      # MFC(H) vs EFC(A) -- a tie
            # SFC's 3rd-6th fixtures, to check the next-5 cap and ordering.
            _fixture(10, 1, 2, "2026-11-07T11:30:00Z"),
            _fixture(11, 1, 2, "2026-11-14T11:30:00Z"),
            _fixture(12, 1, 2, "2026-11-21T11:30:00Z"),
            _fixture(13, 1, 2, "2026-11-28T11:30:00Z"),
        ]
        mock.write_raw(self.tmp, SCORES, classic_teams=CLASSIC_TEAMS, fixtures=fixtures)
        self.d = build_stats.build(self.tmp)
        self.by_short = {t["short_name"]: t for t in self.d["fixtures_by_team"]}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_classic_team_gets_an_entry(self):
        self.assertEqual(set(self.by_short), {"SFC", "WFC", "MFC", "EFC"})

    def test_strong_team_is_favourite_home_and_away(self):
        sfc = self.by_short["SFC"]["fixtures"]
        gw7 = next(f for f in sfc if f["gw"] == 7)  # SFC home vs WFC away: 5 > 1
        self.assertTrue(gw7["favourite"])
        self.assertTrue(gw7["home"])
        self.assertEqual(gw7["opponent"], "WFC")
        gw8 = next(f for f in sfc if f["gw"] == 8)  # SFC away vs WFC home: 4 > 2
        self.assertTrue(gw8["favourite"])
        self.assertFalse(gw8["home"])

    def test_weak_team_is_never_favourite_against_the_strong_team(self):
        wfc = self.by_short["WFC"]["fixtures"]
        gw7 = next(f for f in wfc if f["gw"] == 7)  # WFC away vs SFC home: 1 < 5
        self.assertFalse(gw7["favourite"])
        gw8 = next(f for f in wfc if f["gw"] == 8)  # WFC home vs SFC away: 2 < 4
        self.assertFalse(gw8["favourite"])

    def test_equal_strength_is_no_favourite_for_either_side(self):
        mfc = self.by_short["MFC"]["fixtures"]
        efc = self.by_short["EFC"]["fixtures"]
        self.assertIsNone(next(f for f in mfc if f["opponent"] == "EFC")["favourite"])
        self.assertIsNone(next(f for f in efc if f["opponent"] == "MFC")["favourite"])

    def test_own_difficulty_rating_is_exposed_separately_from_favourite(self):
        sfc = self.by_short["SFC"]["fixtures"]
        gw7 = next(f for f in sfc if f["gw"] == 7)
        self.assertEqual(gw7["difficulty"], 1)  # SFC's own (easy) rating for that fixture

    def test_only_the_next_5_fixtures_are_kept_in_order(self):
        sfc = self.by_short["SFC"]["fixtures"]
        self.assertEqual(len(sfc), 5)
        self.assertEqual([f["gw"] for f in sfc], [7, 8, 9, 10, 11])


if __name__ == "__main__":
    unittest.main()
