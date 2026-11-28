"""notify.py: which events become push notifications, and when."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import notify  # noqa: E402

MANAGERS = [{"entry_id": 1, "team": "FC Biaggi"}, {"entry_id": 2, "team": "Los Ganadores"}]


def player(pid, name, owner, pos="MID", goals=0, assists=0, red=0, bonus=0, prov=0, points=2):
    p = {"id": pid, "name": name, "pos": pos, "owner_entry_id": owner, "goals_scored": goals, "assists": assists,
         "bonus": bonus, "bonus_provisional": prov, "points": points, "breakdown": []}
    if red:
        p["detail"] = {"red_cards": red}
    return p


def data(t, players, scores, gw=12, matches=(), rounds=(), finished=False, bench=()):
    teams = []
    for eid in (1, 2):
        mine = [p for p in players if p["owner_entry_id"] == eid]
        teams.append({"entry_id": eid, "score": scores.get(eid),
                      "xi": [p for p in mine if p["id"] not in bench],
                      "bench": [p for p in mine if p["id"] in bench]})
    return {"meta": {"generated_at": f"2026-11-28T{t}:00+00:00"}, "managers": MANAGERS,
            "rounds": list(rounds),
            "current_round": {"gw": gw, "finished": finished, "teams": teams,
                              "all_players": players, "matches": list(matches)}}


class DetectTest(unittest.TestCase):
    def base(self):
        players = [player(10, "Haaland", 1, pos="FWD"), player(20, "Muharemović", 2, pos="DEF"),
                   player(30, "FreeGuy", None)]
        return data("15:00", players, {1: 20, 2: 12})

    def run_pair(self, before, after):
        _, state = notify.detect(before, {})
        return notify.detect(after, state)

    def test_first_run_is_silent_and_records_a_baseline(self):
        events, state = notify.detect(self.base(), {})
        self.assertEqual(events, [])
        self.assertEqual(state["gw"], 12)
        self.assertEqual(state["players"]["10"], {"g": 0, "a": 0, "r": 0})
        self.assertEqual(state["leader"], 1)

    def test_goal_by_an_owned_starter(self):
        after = self.base()
        after["current_round"]["all_players"][0]["goals_scored"] = 1
        events, _ = self.run_pair(self.base(), after)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "⚽ Haaland scores! +4 for FC Biaggi")
        self.assertIn(events[0]["body"], [l.format(manager="FC Biaggi") for l in notify.GOAL_LINES])

    def test_goal_from_the_bench_gets_the_cruel_line(self):
        before, after = self.base(), self.base()
        for d in (before, after):
            t = d["current_round"]["teams"][0]
            t["bench"], t["xi"] = t["xi"], []
        after["current_round"]["all_players"][0]["goals_scored"] = 1
        events, _ = self.run_pair(before, after)
        self.assertEqual(events[0]["title"], "⚽ Haaland scores… on the bench 🙈")

    def test_goal_points_come_from_fpl_breakdown_when_present(self):
        after = self.base()
        p = after["current_round"]["all_players"][1]
        p["goals_scored"], p["breakdown"] = 1, [{"stat": "goals_scored", "value": 1, "points": 6}]
        events, _ = self.run_pair(self.base(), after)
        self.assertEqual(events[0]["title"], "⚽ Muharemović scores! +6 for Los Ganadores")

    def test_goal_points_per_goal_use_fpl_goal_count_not_the_live_total(self):
        # The live goal count can run ahead of FPL's breakdown for a moment.
        after = self.base()
        p = after["current_round"]["all_players"][0]
        p["goals_scored"], p["breakdown"] = 2, [{"stat": "goals_scored", "value": 1, "points": 4}]
        events, _ = self.run_pair(self.base(), after)
        self.assertEqual(events[0]["title"], "⚽ Haaland scores 2! +8 for FC Biaggi")

    def test_free_agents_are_ignored(self):
        after = self.base()
        after["current_round"]["all_players"][2]["goals_scored"] = 2
        events, _ = self.run_pair(self.base(), after)
        self.assertEqual(events, [])

    def test_assist_and_red_card(self):
        after = self.base()
        after["current_round"]["all_players"][1]["assists"] = 1
        after["current_round"]["all_players"][0]["detail"] = {"red_cards": 1}
        titles = [e["title"] for e in self.run_pair(self.base(), after)[0]]
        self.assertIn("🅰️ Assist Muharemović! +3 for Los Ganadores", titles)
        self.assertIn("🟥 Haaland sent off! −3 for FC Biaggi", titles)

    def test_the_same_goal_is_only_announced_once(self):
        after = self.base()
        after["current_round"]["all_players"][0]["goals_scored"] = 1
        _, state = notify.detect(self.base(), {})
        first, state = notify.detect(after, state)
        again, _ = notify.detect(copy.deepcopy(after), state)
        self.assertEqual(len(first), 1)
        self.assertEqual(again, [])

    def test_on_fire_after_fifteen_points_within_half_an_hour(self):
        _, state = notify.detect(self.base(), {})
        later = self.base()
        later["meta"]["generated_at"] = "2026-11-28T15:25:00+00:00"
        later["current_round"]["teams"][1]["score"] = 28          # Los Ganadores 12 -> 28
        events, state = notify.detect(later, state)
        fire = [e for e in events if e["title"].startswith("🔥")]
        self.assertEqual(fire[0]["title"], "🔥 Los Ganadores on fire: +16 in half an hour")
        # Not again straight away.
        again = self.base()
        again["meta"]["generated_at"] = "2026-11-28T15:30:00+00:00"
        again["current_round"]["teams"][1]["score"] = 45
        events, _ = notify.detect(again, state)
        self.assertFalse([e for e in events if e["title"].startswith("🔥")])

    def test_slow_gains_are_not_on_fire(self):
        _, state = notify.detect(self.base(), {})
        later = self.base()
        later["meta"]["generated_at"] = "2026-11-28T16:00:00+00:00"   # an hour later
        later["current_round"]["teams"][1]["score"] = 28
        events, _ = notify.detect(later, state)
        self.assertFalse([e for e in events if e["title"].startswith("🔥")])

    def test_new_leader(self):
        after = self.base()
        after["current_round"]["teams"][1]["score"] = 25          # 2 overtakes 1 (20)
        events, state = self.run_pair(self.base(), after)
        lead = [e for e in events if e["title"].startswith("👑")]
        self.assertEqual(lead[0]["title"], "👑 Los Ganadores take the lead in GW12 (25 pts)")
        self.assertEqual(state["leader"], 2)

    def test_a_tie_is_not_a_new_leader(self):
        after = self.base()
        after["current_round"]["teams"][1]["score"] = 20
        events, _ = self.run_pair(self.base(), after)
        self.assertFalse([e for e in events if e["title"].startswith("👑")])

    def test_bonus_once_confirmed_for_owned_players(self):
        def match(prov):
            return {"id": 99, "status": "ft", "home": {"short": "LEE", "score": 3, "players": [
                {"name": "Calvert-Lewin", "owner_entry_id": 1, "bonus": 2, "bonus_provisional": prov},
                {"name": "FreeGuy", "owner_entry_id": None, "bonus": 3, "bonus_provisional": 0}]},
                "away": {"short": "COV", "score": 0, "players": []}}
        before = self.base()
        provisional = self.base(); provisional["current_round"]["matches"] = [match(2)]
        confirmed = self.base(); confirmed["current_round"]["matches"] = [match(0)]
        _, state = notify.detect(before, {})
        events, state = notify.detect(provisional, state)
        self.assertEqual(events, [])                                 # still provisional
        events, state = notify.detect(confirmed, state)
        self.assertEqual(events[0]["title"], "🎁 Bonus confirmed: LEE 3–0 COV")
        self.assertEqual(events[0]["body"], "Calvert-Lewin +2 (FC Biaggi)")
        events, _ = notify.detect(confirmed, state)
        self.assertEqual(events, [])

    def test_final_scores_once_a_gameweek_is_finished(self):
        _, state = notify.detect(self.base(), {})
        done = self.base()
        done["rounds"] = [{"gw": 12, "finished": True, "scores": {"1": 61, "2": 44}}]
        events, state = notify.detect(done, state)
        self.assertEqual(events[0]["title"], "🏁 GW12 is done: FC Biaggi win with 61")
        self.assertIn("Los Ganadores", events[0]["body"])
        events, _ = notify.detect(done, state)
        self.assertEqual(events, [])

    def test_rounds_already_finished_on_the_first_run_are_not_announced(self):
        first = self.base()
        first["rounds"] = [{"gw": 11, "finished": True, "scores": {"1": 50, "2": 40}}]
        events, state = notify.detect(first, {})
        self.assertEqual(events, [])
        self.assertIn(11, state["final_announced"])

    def test_a_new_gameweek_starts_from_a_silent_baseline(self):
        _, state = notify.detect(self.base(), {})
        next_gw = self.base()
        next_gw["current_round"]["gw"] = 13
        next_gw["current_round"]["all_players"][0]["goals_scored"] = 1   # already in when first seen
        events, state = notify.detect(next_gw, state)
        self.assertEqual(events, [])
        self.assertEqual(state["gw"], 13)

    def test_bundle_caps_a_busy_run(self):
        events = [{"id": str(i), "title": f"E{i}", "body": ""} for i in range(8)]
        out = notify.bundle(events)
        self.assertEqual(len(out), notify.MAX_PER_RUN)
        self.assertEqual(out[-1]["title"], "📣 4 more things just happened")


class MainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sent = []

    def files(self, config, after_goal=False):
        d = DetectTest().base()
        if after_goal:
            d["current_round"]["all_players"][0]["goals_scored"] = 1
        (self.tmp / "data.json").write_text(json.dumps(d))
        (self.tmp / "config.json").write_text(json.dumps(config))

    def run_main(self, argv=(), env_key=None):
        import os
        old = os.environ.pop("ONESIGNAL_API_KEY", None)
        if env_key:
            os.environ["ONESIGNAL_API_KEY"] = env_key
        try:
            return notify.main(list(argv), data_file=self.tmp / "data.json", state_file=self.tmp / "state.json",
                               config_file=self.tmp / "config.json",
                               sender=lambda e, app, key: self.sent.append((e["title"], app, key)))
        finally:
            os.environ.pop("ONESIGNAL_API_KEY", None)
            if old is not None:
                os.environ["ONESIGNAL_API_KEY"] = old

    def test_sends_only_when_enabled_with_app_id_and_key(self):
        cfg = {"notifications_enabled": True, "onesignal_app_id": "app-123"}
        self.files(cfg)
        self.run_main(env_key="secret")                 # baseline
        self.files(cfg, after_goal=True)
        self.run_main(env_key="secret")
        self.assertEqual(self.sent, [("⚽ Haaland scores! +4 for FC Biaggi", "app-123", "secret")])

    def test_disabled_still_records_state_so_no_backlog_later(self):
        self.files({"notifications_enabled": False})
        self.run_main()
        self.files({"notifications_enabled": False}, after_goal=True)
        self.run_main()
        self.assertEqual(self.sent, [])
        state = json.loads((self.tmp / "state.json").read_text())
        self.assertEqual(state["players"]["10"]["g"], 1)

    def test_missing_key_means_no_send(self):
        cfg = {"notifications_enabled": True, "onesignal_app_id": "app-123"}
        self.files(cfg)
        self.run_main()
        self.files(cfg, after_goal=True)
        self.run_main()
        self.assertEqual(self.sent, [])

    def test_dry_run_changes_nothing(self):
        self.files({"notifications_enabled": False})
        self.run_main(["--dry-run"])
        self.assertFalse((self.tmp / "state.json").exists())

    def test_test_notification(self):
        self.files({"notifications_enabled": True, "onesignal_app_id": "app-123"})
        self.assertEqual(self.run_main(["--test"], env_key="secret"), 0)
        self.assertEqual(self.sent[0][0], "🔔 Notifications are on")
        self.sent.clear()
        self.files({"notifications_enabled": False})
        self.assertEqual(self.run_main(["--test"]), 1)
        self.assertEqual(self.sent, [])

    def test_a_failed_send_does_not_crash_and_state_is_saved(self):
        cfg = {"notifications_enabled": True, "onesignal_app_id": "app-123"}
        self.files(cfg)
        self.run_main(env_key="secret")
        self.files(cfg, after_goal=True)

        def boom(*_):
            raise OSError("network down")
        import os
        os.environ["ONESIGNAL_API_KEY"] = "secret"
        try:
            code = notify.main([], data_file=self.tmp / "data.json", state_file=self.tmp / "state.json",
                               config_file=self.tmp / "config.json", sender=boom)
        finally:
            os.environ.pop("ONESIGNAL_API_KEY", None)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads((self.tmp / "state.json").read_text())["players"]["10"]["g"], 1)


if __name__ == "__main__":
    unittest.main()
