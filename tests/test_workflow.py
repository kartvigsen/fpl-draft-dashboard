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
    def test_cron_fires_every_ten_minutes(self):
        self.assertIn('cron: "*/10 * * * *"', WORKFLOW)

    def test_no_fixed_clock_time_gate(self):
        # GitHub's schedule delivery can run hours late, so an exact-hour
        # local-time gate once silently skipped every run for days.
        self.assertNotIn("TZ=Europe/Copenhagen", WORKFLOW)
        self.assertNotIn("date +%H", WORKFLOW)

    def test_scheduled_runs_are_gated_by_the_match_aware_check(self):
        update_job = WORKFLOW[WORKFLOW.index("\n  update:"):WORKFLOW.index("\n  deploy:")]
        gate = update_job[update_job.index("id: gate"):]
        self.assertIn('if [ "${{ github.event_name }}" = "schedule" ]; then\n            python3 should_update.py >> "$GITHUB_OUTPUT"', gate)
        self.assertIn('echo "run=true" >> "$GITHUB_OUTPUT"', gate)  # push and manual runs always update
        # The gate needs the repo (fixtures, last build), so checkout comes first.
        self.assertLess(update_job.index("actions/checkout@v4"), update_job.index("id: gate"))
        def step_block(marker):
            at = update_job.index(marker)
            start = update_job.rindex("\n      - ", 0, at)
            end = update_job.find("\n      - ", at)
            return update_job[start:end if end != -1 else None]
        for marker in ("setup-python", "python3 update.py", "Save new data", "send_digest.py",
                       "configure-pages", "upload-pages-artifact"):
            self.assertIn("if: steps.gate.outputs.run == 'true'", step_block(marker), marker)
        self.assertIn("if: needs.update.outputs.run == 'true'", WORKFLOW[WORKFLOW.index("\n  deploy:"):])

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

    def test_pages_deploy_is_a_separate_job_gated_to_main_only(self):
        # The github-pages environment's branch protection applies to the
        # whole job that declares it, not just the deploy step -- so the
        # data rebuild and digest send live in a job with no environment.
        # That way "Run workflow" on a feature branch can still rebuild data
        # and send a real digest for testing, without being able to publish
        # to the live site (the environment protection itself blocks that).
        update_job = WORKFLOW[WORKFLOW.index("\n  update:"):WORKFLOW.index("\n  deploy:")]
        deploy_job = WORKFLOW[WORKFLOW.index("\n  deploy:"):]
        self.assertNotIn("environment:", update_job)
        self.assertIn("needs: update", deploy_job)
        self.assertIn("name: github-pages", deploy_job)

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
