"""should_update.py: when a scheduled run does real work."""
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import should_update  # noqa: E402

NOW = datetime(2026, 10, 28, 20, 0, tzinfo=timezone.utc)  # a Wednesday evening
RECENT = (NOW - timedelta(hours=1)).isoformat()


def fixture(kickoff, started=False, finished=False, provisional=False):
    return {"kickoff_time": kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"), "started": started,
            "finished": finished, "finished_provisional": provisional}


class DecideTest(unittest.TestCase):
    def decide(self, fixtures=(), generated_at=RECENT, head_time=None, head_subject="Update data 2026-10-28"):
        return should_update.decide(NOW, list(fixtures), generated_at, head_time, head_subject)[0]

    def test_a_midweek_match_in_its_window_triggers_an_update(self):
        self.assertTrue(self.decide([fixture(NOW - timedelta(minutes=45))]))

    def test_the_window_runs_until_two_and_a_half_hours_after_kickoff(self):
        self.assertTrue(self.decide([fixture(NOW - timedelta(hours=2, minutes=29))]))
        self.assertFalse(self.decide([fixture(NOW - timedelta(hours=2, minutes=31), started=True, provisional=True)]))

    def test_a_match_that_has_not_kicked_off_yet_does_not(self):
        self.assertFalse(self.decide([fixture(NOW + timedelta(minutes=5))]))

    def test_a_long_running_match_still_counts_while_not_finished(self):
        self.assertTrue(self.decide([fixture(NOW - timedelta(hours=3), started=True)]))

    def test_an_abandoned_match_stops_counting_after_six_hours(self):
        self.assertFalse(self.decide([fixture(NOW - timedelta(hours=7), started=True)]))

    def test_data_older_than_three_hours_triggers_an_update_on_a_blank_day(self):
        self.assertTrue(self.decide(generated_at=(NOW - timedelta(hours=3, minutes=1)).isoformat()))
        self.assertFalse(self.decide(generated_at=(NOW - timedelta(hours=2, minutes=59)).isoformat()))

    def test_no_previous_build_triggers_an_update(self):
        self.assertTrue(self.decide(generated_at=None))

    def test_a_code_commit_newer_than_the_build_triggers_an_update(self):
        # Heals a push-triggered run that GitHub cancelled in favour of a
        # newer queued scheduled run.
        later = NOW - timedelta(minutes=30)
        self.assertTrue(self.decide(head_time=later, head_subject="Live round: something new (#40)"))

    def test_the_data_commit_itself_does_not(self):
        later = NOW - timedelta(minutes=30)
        self.assertFalse(self.decide(head_time=later, head_subject="Update data 2026-10-28"))
        self.assertFalse(self.decide(head_time=later, head_subject="Record digest sent for this gameweek"))


class MainTest(unittest.TestCase):
    """Reads the fixtures saved by the last update (upcoming ones from
    fixtures.json, plus the live gameweek's, which still lists a match
    already under way) and prints a $GITHUB_OUTPUT line."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "data" / "raw" / "live").mkdir(parents=True)
        (self.tmp / "docs").mkdir()
        self.write("data/raw/game.json", {"current_event": 9})
        self.write("data/raw/fixtures.json", [])
        self.write("data/raw/live/gw9.json", {"fixtures": []})
        self.write("docs/data.json", {"meta": {"generated_at": RECENT}})

    def write(self, rel, obj):
        (self.tmp / rel).write_text(json.dumps(obj))

    def run_main(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            should_update.main(self.tmp, now=NOW)
        return out.getvalue().strip(), err.getvalue()

    def test_quiet_period_prints_run_false(self):
        self.assertEqual(self.run_main()[0], "run=false")

    def test_a_match_under_way_is_found_in_the_live_gameweek_file(self):
        self.write("data/raw/live/gw9.json", {"fixtures": [fixture(NOW - timedelta(minutes=50), started=True)]})
        out, err = self.run_main()
        self.assertEqual(out, "run=true")
        self.assertIn("19:10 UTC", err)

    def test_an_upcoming_match_is_found_in_fixtures_json(self):
        self.write("data/raw/fixtures.json", [fixture(NOW - timedelta(minutes=5))])
        self.assertEqual(self.run_main()[0], "run=true")

    def test_missing_files_mean_update(self):
        shutil.rmtree(self.tmp / "data")
        (self.tmp / "docs" / "data.json").unlink()
        self.assertEqual(self.run_main()[0], "run=true")

    def test_reads_the_head_commit_from_git(self):
        subprocess.run(["git", "init", "-q"], cwd=self.tmp, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
                        "-m", "Fixtures: new feature (#41)"], cwd=self.tmp, check=True)
        # The commit is "now" in real time, later than a build dated NOW-1h
        # in 2026 only if the clock says so -- so date the build far back.
        self.write("docs/data.json", {"meta": {"generated_at": "2020-01-01T00:00:00+00:00"}})
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            should_update.main(self.tmp, now=datetime(2020, 1, 1, 1, 0, tzinfo=timezone.utc))
        self.assertEqual(out.getvalue().strip(), "run=true")
        self.assertIn("code changed", err.getvalue())


if __name__ == "__main__":
    unittest.main()
