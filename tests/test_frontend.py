"""Lightweight checks on docs/index.html.

The dashboard is plain HTML/JS with no build step and no dependencies, so
there is no JS test runner in this project. These tests are string-level
smoke checks that guard the markup/script for the behaviour described in
README.md, not a substitute for opening the page in a browser.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HTML = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")


class FrontendMarkupTest(unittest.TestCase):
    def test_best_and_worst_moves_section_is_gone(self):
        self.assertNotIn("Best and worst moves", HTML)

    def test_net_column_is_kept_in_all_moves_table(self):
        self.assertIn('"All moves"', HTML)
        self.assertIn('"Net"', HTML)

    def test_all_moves_has_filters_for_team_type_result_gw_and_name(self):
        self.assertIn('"Filter by team"', HTML)
        self.assertIn('"Filter by type"', HTML)
        self.assertIn('"Filter by result"', HTML)
        self.assertIn('"Filter by gameweek"', HTML)
        self.assertIn('"Filter by player name"', HTML)

    def test_all_moves_defaults_to_12_rows_with_show_all(self):
        self.assertIn("const LIM = 12;", HTML)
        self.assertIn("Show all", HTML)
        # A filter change must reset back to the 12-row view.
        self.assertIn("function applyFilters() { showAll = false; paint(); }", HTML)

    def test_heat_map_rows_are_sorted_by_standing_not_signup_order(self):
        self.assertIn("const heatRows = ranked.map(m =>", HTML)

    def test_lowest_scorers_present_alongside_top_scorers(self):
        self.assertIn("Top scorers", HTML)
        self.assertIn("Lowest scorers", HTML)
        self.assertIn("low_by_manager", HTML)
        self.assertIn("low_scorers_min_starts", HTML)

    def test_feedback_button_and_tab_exist(self):
        self.assertIn('"feedback", "Feedback"', HTML)
        self.assertIn("openFeedbackIssue", HTML)
        self.assertIn('"Feedback"', HTML)

    def test_feedback_button_is_next_to_theme_toggle(self):
        header = re.search(r'app\.append\(h\("header".*?\)\)\);', HTML, re.S).group(0)
        self.assertIn("openFeedbackIssue", header)
        self.assertIn("toggleTheme", header)

    def test_feedback_issue_link_targets_this_repo(self):
        self.assertIn('kartvigsen/fpl-draft-dashboard', HTML)
        self.assertIn("/issues/new?title=", HTML)

    def test_feedback_tab_fetches_issues_client_side_and_filters_prs(self):
        self.assertIn("api.github.com/repos/${REPO}/issues", HTML)
        self.assertIn("!it.pull_request", HTML)

    def test_feedback_tab_only_follows_github_links(self):
        self.assertIn('it.html_url.startsWith("https://github.com/")', HTML)

    def test_feedback_tab_handles_rate_limiting_with_retry(self):
        self.assertIn("rate-limited", HTML)
        self.assertIn("res.status === 403 || res.status === 429", HTML)
        self.assertIn("Retry", HTML)


if __name__ == "__main__":
    unittest.main()
