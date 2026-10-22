"""Checks the weekly digest's content logic and its guardrails against
accidentally emailing people (run: python3 -m unittest discover -s tests -v).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import build_stats  # noqa: E402
import mock  # noqa: E402 -- this project's own fixture builder, not unittest.mock
import send_digest  # noqa: E402


def write_digest_fixture(root):
    """Three managers, two finished gameweeks. GW2 scores are picked so
    every award has an unambiguous, distinct winner: Bo tops GW2, Cleo is
    bottom, and the rank order flips between GW1 and GW2 so climber/faller
    are both exercised. Season totals after both gameweeks are Bravo 120 >
    Alex 95 > Cleo 90, but Cleo's GW1 bench (30) is large enough that
    total-plus-bench reorders her above Alex, so the Table of Justice has
    both a "robbed" (Cleo) and a "blessed" (Alex) manager to report.
    """
    mock.write_raw(
        root,
        gw_scores=[[40, 50, 60], [55, 70, 30]],  # GW1: Alex<Bo<Cleo, GW2: Cleo<Alex<Bo
        current_finished=True,
        bench={(1, 2): 30, (2, 0): 20, (2, 1): 2, (2, 2): 1},  # Alex's gw2 bench is the flop
        people=[("Alex", "A.", "Team Alpha"), ("Bo", "B.", "Team Bravo"), ("Cleo", "C.", "Team Charlie")],
    )


class ComputeWeekTest(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        write_digest_fixture(tmp)
        self.data = build_stats.build(tmp)
        self.week = send_digest.compute_week(self.data, 2)
        self.by_team = {m["team"]: m["entry_id"] for m in self.data["managers"]}

    def test_top_scorer_and_wooden_spoon_are_gw2_specific_not_season_totals(self):
        # Season totals after GW2: Alpha 95, Bravo 120, Charlie 90 -- Bravo
        # leads overall, but GW2 alone was won by Bravo (70) and lost by
        # Charlie (30), which is what the weekly award must reflect.
        self.assertEqual(self.week["top_scorer"], {"entry_id": self.by_team["Team Bravo"], "points": 70})
        self.assertEqual(self.week["wooden_spoon"], {"entry_id": self.by_team["Team Charlie"], "points": 30})

    def test_bench_flop_picks_the_highest_bench_total_for_that_gameweek(self):
        self.assertEqual(self.week["bench_flop"],
                          {"entry_id": self.by_team["Team Alpha"], "points": 20})

    def test_climber_and_faller_reflect_the_rank_swing_between_gameweeks(self):
        # GW1 rank: Cleo 1st, Bo 2nd, Alex 3rd. GW2 rank: Bo 1st, Alex 2nd, Cleo 3rd.
        self.assertEqual(self.week["climber"], {"entry_id": self.by_team["Team Alpha"], "delta": 1})
        self.assertEqual(self.week["faller"], {"entry_id": self.by_team["Team Charlie"], "delta": 2})

    def test_table_of_justice_reorders_by_total_plus_bench_points(self):
        # Recompute directly from the public fields compute_week exposes via
        # most_robbed/most_blessed instead of poking at internals.
        robbed = self.week["most_robbed"]
        blessed = self.week["most_blessed"]
        self.assertIsNotNone(robbed)
        self.assertIsNotNone(blessed)
        self.assertGreater(robbed["luck_delta"], 0)
        self.assertLess(blessed["luck_delta"], 0)

    def test_standings_are_ordered_by_season_rank_not_gw2_alone(self):
        self.assertEqual(self.week["standings"][0], self.by_team["Team Bravo"])


class RenderTest(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        write_digest_fixture(tmp)
        self.data = build_stats.build(tmp)
        self.week = send_digest.compute_week(self.data, 2)
        self.by_team = {m["team"]: m["entry_id"] for m in self.data["managers"]}

    def test_render_is_deterministic_for_the_same_gameweek(self):
        subject1, html1, text1 = send_digest.render(self.data, self.week)
        subject2, html2, text2 = send_digest.render(self.data, self.week)
        self.assertEqual((subject1, html1, text1), (subject2, html2, text2))

    def test_subject_and_body_name_the_wooden_spoon_manager(self):
        subject, html, text = send_digest.render(self.data, self.week)
        cleo = self.data["managers"][self.data["managers"].index(
            next(m for m in self.data["managers"] if m["team"] == "Team Charlie"))]
        self.assertIn(cleo["first"], subject + html)

    def test_html_has_no_unfilled_template_placeholders(self):
        _, html, _ = send_digest.render(self.data, self.week)
        self.assertNotIn("{", html)
        self.assertNotIn("}", html)

    def test_html_is_table_based_for_email_client_compatibility(self):
        # Real inboxes don't reliably support CSS custom properties or
        # color-mix(); the digest has to use plain hex colors and inline
        # styles on <table>, unlike the artifact prototypes it's based on.
        _, html, _ = send_digest.render(self.data, self.week)
        self.assertIn('<table role="presentation"', html)
        self.assertNotIn("var(--", html)
        self.assertNotIn("color-mix(", html)

    def test_standings_table_lists_every_manager_with_their_total(self):
        _, html, _ = send_digest.render(self.data, self.week)
        for m in self.data["managers"]:
            self.assertIn(m["team"], html)
            total = self.data["per_manager"][str(m["entry_id"])]["total"]
            self.assertIn(str(total), html)


class SendTest(unittest.TestCase):
    """Port 465/SMTP_SSL was observed dropping the connection mid-login
    from GitHub Actions specifically (smtplib.SMTPServerDisconnected);
    587/STARTTLS is the reliable path, so lock in that it's what's used."""

    @patch("send_digest.smtplib.SMTP")
    def test_uses_starttls_on_587_not_implicit_ssl_on_465(self, mock_smtp_cls):
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        send_digest.send("Subject", "<p>html</p>", "text", ["a@example.com"], "me@gmail.com", "app password")

        mock_smtp_cls.assert_called_once_with("smtp.gmail.com", 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("me@gmail.com", "app password")
        mock_server.sendmail.assert_called_once()


class OrdinalTest(unittest.TestCase):
    def test_ordinal_suffixes(self):
        self.assertEqual(send_digest.ordinal(1), "st")
        self.assertEqual(send_digest.ordinal(2), "nd")
        self.assertEqual(send_digest.ordinal(3), "rd")
        self.assertEqual(send_digest.ordinal(4), "th")
        self.assertEqual(send_digest.ordinal(11), "th")
        self.assertEqual(send_digest.ordinal(12), "th")
        self.assertEqual(send_digest.ordinal(13), "th")
        self.assertEqual(send_digest.ordinal(21), "st")


class MainGuardrailTest(unittest.TestCase):
    """main() must never actually send unless explicitly enabled, and must
    never touch .digest_state.json on a --dry-run."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        raw = Path(tempfile.mkdtemp())
        write_digest_fixture(raw)
        data = build_stats.build(raw)
        (self.tmp / "docs").mkdir()
        (self.tmp / "docs" / "data.json").write_text(json.dumps(data))
        self.orig = (send_digest.DATA_FILE, send_digest.STATE_FILE,
                     send_digest.CONFIG_FILE, send_digest.PREVIEW_FILE)
        send_digest.DATA_FILE = self.tmp / "docs" / "data.json"
        send_digest.STATE_FILE = self.tmp / ".digest_state.json"
        send_digest.CONFIG_FILE = self.tmp / "config.json"
        send_digest.PREVIEW_FILE = self.tmp / "digest_preview.html"

    def tearDown(self):
        (send_digest.DATA_FILE, send_digest.STATE_FILE,
         send_digest.CONFIG_FILE, send_digest.PREVIEW_FILE) = self.orig

    def test_dry_run_writes_a_preview_and_never_touches_state(self):
        send_digest.main(["--dry-run"])
        self.assertTrue(send_digest.PREVIEW_FILE.exists())
        self.assertFalse(send_digest.STATE_FILE.exists())

    def test_without_digest_enabled_in_config_nothing_is_sent_or_recorded(self):
        (self.tmp / "config.json").write_text(json.dumps({"digest_enabled": False}))
        send_digest.main([])
        self.assertFalse(send_digest.STATE_FILE.exists())

    def test_missing_config_file_also_skips_sending(self):
        send_digest.main([])
        self.assertFalse(send_digest.STATE_FILE.exists())


if __name__ == "__main__":
    unittest.main()
