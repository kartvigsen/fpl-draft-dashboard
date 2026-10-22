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
    def test_cron_covers_all_ten_possible_utc_times(self):
        # Each of 07:00/12:00/16:00/20:00/23:00 Danish time is one hour
        # earlier in summer (CEST, UTC+2) than in winter (CET, UTC+1), so
        # ten UTC cron slots are needed to cover all five year-round.
        self.assertIn('cron: "0 5,6,10,11,14,15,18,19,21,22 * * *"', WORKFLOW)

    def test_gate_step_checks_danish_local_time(self):
        self.assertIn("TZ=Europe/Copenhagen", WORKFLOW)
        self.assertIn("07|12|16|20|23) wanted=true ;;", WORKFLOW)

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

    def test_digest_step_runs_after_the_dashboard_data_is_already_saved(self):
        # The digest must never block the dashboard's own update/deploy, so
        # it runs (and is committed) after the real data is already saved,
        # not interleaved before it.
        self.assertIn("python3 send_digest.py", WORKFLOW)
        self.assertIn("GMAIL_USER: ${{ secrets.GMAIL_USER }}", WORKFLOW)
        self.assertIn("GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}", WORKFLOW)
        self.assertIn("DIGEST_RECIPIENTS: ${{ secrets.DIGEST_RECIPIENTS }}", WORKFLOW)
        self.assertLess(WORKFLOW.index("Save new data to the repository"), WORKFLOW.index("python3 send_digest.py"))

    def test_digest_step_cannot_fail_the_job(self):
        # A send failure (bad credentials, Gmail hiccup) must not stop the
        # dashboard data/Pages deploy steps that come after it.
        digest_step = WORKFLOW[WORKFLOW.index("Send the weekly digest"):]
        self.assertIn("continue-on-error: true", digest_step.split("\n\n", 1)[0])

    def test_digest_state_file_is_committed_with_cached_diff_not_unstaged(self):
        # git diff (unstaged) never reports a brand-new untracked file, so
        # the very first send would silently fail to record itself and
        # re-send next run -- must stage first, then check the staged diff.
        self.assertIn("git add .digest_state.json", WORKFLOW)
        self.assertIn("git diff --cached --quiet -- .digest_state.json", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
