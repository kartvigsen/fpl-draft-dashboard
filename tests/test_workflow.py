"""Lightweight checks on .github/workflows/update.yml.

No YAML parser is used (standard library only), just string-level checks on
the schedule, gating logic and push trigger described in README.md.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WORKFLOW = (ROOT / ".github" / "workflows" / "update.yml").read_text(encoding="utf-8")


class WorkflowScheduleTest(unittest.TestCase):
    def test_cron_covers_all_four_possible_utc_times(self):
        # 14:00/18:00 Danish time is 12:00/16:00 UTC in summer (CEST, UTC+2)
        # and 13:00/17:00 UTC in winter (CET, UTC+1).
        self.assertIn('cron: "0 12,13,16,17 * * *"', WORKFLOW)

    def test_gate_step_checks_danish_local_time(self):
        self.assertIn("TZ=Europe/Copenhagen", WORKFLOW)
        self.assertIn('"$hour" != "14"', WORKFLOW)
        self.assertIn('"$hour" != "18"', WORKFLOW)

    def test_off_hour_scheduled_runs_skip_the_rest_of_the_job(self):
        self.assertIn("run=false", WORKFLOW)
        self.assertIn("steps.gate.outputs.run == 'true'", WORKFLOW)
        # Every real step after the gate must be conditional on it.
        gated_steps = WORKFLOW.count("if: steps.gate.outputs.run == 'true'")
        self.assertGreaterEqual(gated_steps, 6)

    def test_gate_does_not_apply_to_manual_or_push_runs(self):
        self.assertIn('github.event_name', WORKFLOW)
        self.assertIn('"schedule"', WORKFLOW)

    def test_push_trigger_rebuilds_on_relevant_file_changes(self):
        self.assertIn("branches: [main]", WORKFLOW)
        self.assertIn('"docs/index.html"', WORKFLOW)
        self.assertIn('"*.py"', WORKFLOW)
        self.assertIn('"config.json"', WORKFLOW)
        self.assertIn('".github/workflows/update.yml"', WORKFLOW)

    def test_existing_steps_and_concurrency_are_kept(self):
        self.assertIn("group: dashboard", WORKFLOW)
        self.assertIn("cancel-in-progress: false", WORKFLOW)
        self.assertIn("python3 update.py", WORKFLOW)
        self.assertIn("actions/deploy-pages@v4", WORKFLOW)
        self.assertIn("workflow_dispatch:", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
