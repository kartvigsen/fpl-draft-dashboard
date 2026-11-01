"""Lightweight checks on .github/workflows/update.yml.

No YAML parser is used (standard library only), just string-level checks on
the schedule, gating logic and push trigger described in README.md.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
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
        self.assertIn('if [ "${{ github.event_name }}" = "schedule" ] || [ "${{ inputs.check }}" = "true" ]; then\n'
                      '            python3 should_update.py >> "$GITHUB_OUTPUT"', gate)
        self.assertIn('echo "run=true" >> "$GITHUB_OUTPUT"', gate)  # push and plain manual runs always update
        # The gate needs the repo (fixtures, last build), so checkout comes first.
        self.assertLess(update_job.index("actions/checkout@v5"), update_job.index("id: gate"))
        def step_block(marker):
            at = update_job.index(marker)
            start = update_job.rindex("\n      - ", 0, at)
            end = update_job.find("\n      - ", at)
            return update_job[start:end if end != -1 else None]
        for marker in ("setup-python", "python3 update.py", "Save new data", "send_digest.py",
                       "configure-pages", "upload-pages-artifact"):
            self.assertIn("if: steps.gate.outputs.run == 'true'", step_block(marker), marker)
        self.assertIn("if: needs.update.outputs.run == 'true'", WORKFLOW[WORKFLOW.index("\n  deploy:"):])

    def test_external_scheduler_runs_go_through_the_same_check(self):
        # An outside scheduler starts the workflow via the API with
        # inputs {"check": "true"}; the plain "Run workflow" button
        # defaults to false and always updates.
        dispatch = WORKFLOW[WORKFLOW.index("  workflow_dispatch:"):WORKFLOW.index("\npermissions:")]
        self.assertIn("      check:", dispatch)
        self.assertIn("type: boolean", dispatch)
        self.assertIn("default: false", dispatch)

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
        self.assertIn("actions/deploy-pages@v5", WORKFLOW)
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


class NodeRuntimeTest(unittest.TestCase):
    def test_actions_run_on_node_24_not_the_retired_node_20(self):
        self.assertIn("actions/checkout@v5", WORKFLOW)
        self.assertIn("actions/setup-python@v6", WORKFLOW)
        self.assertNotIn("actions/checkout@v4", WORKFLOW)
        self.assertNotIn("actions/setup-python@v5", WORKFLOW)

    def test_pages_actions_run_on_node_24_too(self):
        # upload-pages-artifact v4+ leaves out dotfiles by default; docs/
        # has none, so nothing the site needs is dropped.
        self.assertIn("actions/configure-pages@v6", WORKFLOW)
        self.assertIn("actions/upload-pages-artifact@v5", WORKFLOW)
        self.assertIn("actions/deploy-pages@v5", WORKFLOW)
        hidden = [p for p in (ROOT / "docs").rglob(".*")]
        self.assertEqual(hidden, [], "upload-pages-artifact would leave these out")


def save_step_script():
    """The "Save new data to the repository" step's shell script, as run."""
    step = WORKFLOW[WORKFLOW.index("- name: Save new data to the repository"):]
    step = step[:step.index("\n\n")]
    return textwrap.dedent(step[step.index("run: |\n") + len("run: |\n"):])


class SaveStepPushRetryTest(unittest.TestCase):
    """Runs the real save-step script against a fake git whose first N
    pushes are refused -- another run saved newer data first, or GitHub
    answered with a 500 -- and a fake python3 standing in for update.py."""

    def run_save(self, failing_pushes, changes_after_rebuild=True):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        (tmp / "fails_left").write_text(str(failing_pushes))
        (tmp / "rebuilt").write_text("0")
        git = tmp / "git"
        git.write_text(textwrap.dedent(f"""\
            #!/bin/bash
            echo "git $*" >> {tmp}/calls
            case "$1" in
              diff)   # staged changes? always on the first build; after a rebuild, as configured
                if [ "$(cat {tmp}/rebuilt)" = 1 ] && [ "{int(changes_after_rebuild)}" = 0 ]; then exit 0; fi
                exit 1 ;;
              push)
                n=$(cat {tmp}/fails_left)
                if [ "$n" -gt 0 ]; then echo $((n - 1)) > {tmp}/fails_left; exit 1; fi ;;
            esac
            exit 0
            """))
        py = tmp / "python3"
        py.write_text(f"#!/bin/bash\necho \"python3 $*\" >> {tmp}/calls\necho 1 > {tmp}/rebuilt\n")
        sleep = tmp / "sleep"
        sleep.write_text("#!/bin/bash\necho \"sleep $*\" >> %s/calls\n" % tmp)
        for f in (git, py, sleep):
            f.chmod(0o755)
        env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}", "GITHUB_REF_NAME": "main"}
        proc = subprocess.run(["bash", "-e", "-c", save_step_script()], env=env, capture_output=True, text=True)
        calls = (tmp / "calls").read_text().splitlines()
        return proc.returncode, [c for c in calls if not c.startswith(("git config", "git add"))]

    def test_a_clean_push_happens_once(self):
        code, calls = self.run_save(0)
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["git diff --cached --quiet", "git commit -m " + calls[1].split("-m ", 1)[1], "git push"])

    def test_a_refused_push_starts_over_from_the_latest_main_instead_of_merging(self):
        # The night-time failure: another run had saved newer data, and a
        # rebase can't merge generated files. Now: fetch, reset, rebuild, retry.
        code, calls = self.run_save(1)
        self.assertEqual(code, 0)
        steps = [c for c in calls if not c.startswith(("git diff", "git commit"))]
        self.assertEqual(steps, ["git push", "sleep 15", "git fetch origin main", "git reset --hard origin/main",
                                 "python3 update.py", "git push"])
        self.assertFalse(any("rebase" in c or "pull" in c for c in calls))

    def test_nothing_new_after_rebuilding_means_done_without_pushing_again(self):
        code, calls = self.run_save(1, changes_after_rebuild=False)
        self.assertEqual(code, 0)
        self.assertEqual(sum(c == "git push" for c in calls), 1)
        self.assertEqual(sum(c.startswith("git commit") for c in calls), 1)

    def test_three_refused_pushes_fail_the_run(self):
        code, calls = self.run_save(3)
        self.assertNotEqual(code, 0)
        self.assertEqual(sum(c == "git push" for c in calls), 3)
        self.assertEqual(sum(c == "python3 update.py" for c in calls), 2)


class CheckoutTest(unittest.TestCase):
    def test_runs_start_from_the_branchs_latest_commit(self):
        # Not the commit the run was triggered on, which can be stale by
        # the time a queued run starts.
        step = WORKFLOW[WORKFLOW.index("- uses: actions/checkout@v5"):]
        step = step[:step.index("\n\n")]
        self.assertIn("ref: ${{ github.ref }}", step)

if __name__ == "__main__":
    unittest.main()
