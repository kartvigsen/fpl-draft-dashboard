"""Checks collect.py's caching and file layout against a fake API (no network)."""
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
import collect  # noqa: E402
import mock  # noqa: E402

SCORES = [[50, 60, 40, 55], [54, 70, 44, 50], [65, 65, 30, 52], [72, 48, 61, 55], [20, 33, 10, 15]]


class CollectTest(unittest.TestCase):
    def setUp(self):
        self.api = Path(tempfile.mkdtemp())
        self.out = Path(tempfile.mkdtemp())
        self.project = Path(tempfile.mkdtemp())  # holds a throwaway config.json
        (self.project / "config.json").write_text(json.dumps({"league_id": 7281}))
        mock.write_raw(self.api, SCORES)
        self.calls = []
        self._orig = (collect.get_json, collect.RAW, collect.ROOT)
        collect.get_json = self.fake_get
        collect.RAW = self.out
        collect.ROOT = self.project

    def tearDown(self):
        collect.get_json, collect.RAW, collect.ROOT = self._orig
        shutil.rmtree(self.api, ignore_errors=True)
        shutil.rmtree(self.out, ignore_errors=True)
        shutil.rmtree(self.project, ignore_errors=True)

    def set_league_id(self, league_id):
        (self.project / "config.json").write_text(json.dumps({"league_id": league_id}))

    def fake_get(self, path):
        self.calls.append(path)
        parts = path.split("/")
        if path == "game": f = "game.json"
        elif path == "bootstrap-static": f = "bootstrap.json"
        elif parts[0] == "league" and parts[2] == "details": f = "league_details.json"
        elif parts[0] == "league" and parts[2] == "element-status": f = "element_status.json"
        elif parts[:2] == ["draft", "league"] and parts[3] == "transactions": f = "transactions.json"
        elif parts[0] == "event" and parts[2] == "live": f = f"live/gw{parts[1]}.json"
        elif parts[0] == "entry" and parts[2] == "event": f = f"entries/{parts[1]}/gw{parts[3]}.json"
        else: raise AssertionError("unexpected endpoint " + path)
        return json.loads((self.api / f).read_text())

    def test_first_run_downloads_everything_and_builds(self):
        warnings = collect.collect(log=lambda *_: None)
        self.assertEqual(warnings, [])
        self.assertEqual(sum(1 for c in self.calls if c.startswith("event/")), 5)
        self.assertEqual(sum(1 for c in self.calls if c.startswith("entry/")), 20)
        d = build_stats.build(self.out)
        self.assertEqual(d["trends"]["gws"], [1, 2, 3, 4])
        self.assertTrue(d["checks"]["all_ok"])

    def test_second_run_only_refetches_unfinished_gameweek(self):
        collect.collect(log=lambda *_: None)
        self.calls.clear()
        collect.collect(log=lambda *_: None)
        live = [c for c in self.calls if c.startswith("event/")]
        self.assertEqual(live, ["event/5/live"])
        self.assertEqual(sum(1 for c in self.calls if c.startswith("entry/")), 4)

    def test_force_refetches_everything(self):
        collect.collect(log=lambda *_: None)
        self.calls.clear()
        collect.collect(force=True, log=lambda *_: None)
        self.assertEqual(sum(1 for c in self.calls if c.startswith("event/")), 5)

    def test_new_league_id_forces_full_redownload(self):
        collect.collect(log=lambda *_: None)
        state = json.loads((self.out / "_state.json").read_text())
        self.assertEqual(state["league_id"], 7281)

        # Simulate a new season: config.json now points at a different league,
        # but the raw cache on disk still belongs to the old one.
        self.set_league_id(9999)
        self.calls.clear()
        collect.collect(log=lambda *_: None)
        # Every gameweek must be refetched, not skipped as "already final".
        self.assertEqual(sum(1 for c in self.calls if c.startswith("event/")), 5)
        state2 = json.loads((self.out / "_state.json").read_text())
        self.assertEqual(state2["league_id"], 9999)
        self.assertEqual(state2["final_gws"], [1, 2, 3, 4])

    def test_state_without_league_id_forces_full_redownload(self):
        collect.collect(log=lambda *_: None)
        state = json.loads((self.out / "_state.json").read_text())
        del state["league_id"]  # simulate a cache saved before this check existed
        (self.out / "_state.json").write_text(json.dumps(state))
        self.calls.clear()
        collect.collect(log=lambda *_: None)
        self.assertEqual(sum(1 for c in self.calls if c.startswith("event/")), 5)

    def test_gameweek_becomes_final_once_finished(self):
        collect.collect(log=lambda *_: None)
        game = json.loads((self.api / "game.json").read_text())
        game["current_event"], game["current_event_finished"] = 6, False  # gw5 now over
        (self.api / "game.json").write_text(json.dumps(game))
        for name in ("live/gw6.json",):
            (self.api / name).write_text(json.dumps({"elements": {}}))
        for eid in (101, 102, 103, 104):
            (self.api / "entries" / str(eid) / "gw6.json").write_text(json.dumps({"picks": [], "subs": []}))
        self.calls.clear()
        collect.collect(log=lambda *_: None)
        live = [c for c in self.calls if c.startswith("event/")]
        self.assertEqual(live, ["event/5/live", "event/6/live"])  # 5 refreshed one last time
        state = json.loads((self.out / "_state.json").read_text())
        self.assertEqual(state["final_gws"], [1, 2, 3, 4, 5])


if __name__ == "__main__":
    unittest.main()
