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

    def test_net_column_is_removed_from_all_moves_table(self):
        self.assertIn('"All moves"', HTML)
        self.assertNotIn('"Net"', HTML)

    def test_all_moves_result_is_colour_coded(self):
        self.assertIn('h("span", { class: ok ? "up" : "down" }, ok ? "Accepted" : "Denied")', HTML)

    def test_standings_total_includes_the_live_round(self):
        self.assertIn("p.live_points != null", HTML)
        self.assertIn("live)`", HTML)

    def test_standings_explains_the_live_score_when_a_round_is_in_progress(self):
        self.assertIn("if (D.live_round) pg.append(", HTML)
        self.assertIn("isn't final yet", HTML)

    def test_header_subtitle_reflects_live_not_excluded(self):
        self.assertIn("in progress (live, not yet final)", HTML)
        self.assertNotIn("in progress (not counted)", HTML)

    def test_leader_tile_flags_a_live_total(self):
        self.assertIn('(D.live_round ? " (live)" : "")', HTML)

    def test_footer_rule_text_reflects_live_standings(self):
        self.assertIn("Standings and total points update live while a gameweek is in progress", HTML)
        self.assertNotIn("Only finished gameweeks count.", HTML)

    def test_scrollable_tables_show_an_edge_shadow(self):
        # Wide tables (heatmap, all moves, all players, ...) overflow on
        # narrow screens; a scroll-shadow hints there's more off-screen
        # without needing JS, matched to whatever background the table
        # wrapper sits on (surface by default, page in the footer).
        self.assertIn(".tbl-wrap {", HTML)
        self.assertIn("--tbl-bg: var(--surface);", HTML)
        self.assertIn(".foot .tbl-wrap { --tbl-bg: var(--page); }", HTML)
        self.assertIn("no-repeat local", HTML)
        self.assertIn("no-repeat scroll", HTML)


class HomeScreenInstallTest(unittest.TestCase):
    """"Add to Home Screen" support: a web app manifest, icons, and a
    minimal service worker so the dashboard installs like an app."""

    def test_manifest_and_icons_are_linked_in_the_head(self):
        self.assertIn('<link rel="manifest" href="manifest.json">', HTML)
        self.assertIn('<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">', HTML)
        self.assertIn('<link rel="icon" href="icons/favicon.ico" sizes="any">', HTML)
        self.assertIn('<meta name="theme-color" content="#2a78d6">', HTML)
        self.assertIn('<meta name="apple-mobile-web-app-capable" content="yes">', HTML)

    def test_service_worker_is_registered(self):
        self.assertIn('navigator.serviceWorker.register("sw.js")', HTML)

    def test_manifest_json_is_valid_and_matches_the_linked_icons(self):
        import json
        manifest = json.loads((ROOT / "docs" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["display"], "standalone")
        icon_srcs = {icon["src"] for icon in manifest["icons"]}
        self.assertEqual(icon_srcs, {
            "icons/icon-192.png", "icons/icon-512.png",
            "icons/icon-192-maskable.png", "icons/icon-512-maskable.png",
        })
        for src in icon_srcs:
            self.assertTrue((ROOT / "docs" / src).exists(), f"missing {src}")

    def test_favicon_and_apple_touch_icon_files_exist(self):
        self.assertTrue((ROOT / "docs" / "icons" / "favicon.ico").exists())
        self.assertTrue((ROOT / "docs" / "icons" / "apple-touch-icon.png").exists())

    def test_service_worker_file_exists_and_handles_fetch(self):
        sw = (ROOT / "docs" / "sw.js").read_text(encoding="utf-8")
        self.assertIn('addEventListener("fetch"', sw)

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

    def test_scorers_merged_into_one_foldable_list_per_team(self):
        self.assertIn("scorers_by_manager", HTML)
        self.assertNotIn("low_by_manager", HTML)
        self.assertNotIn("low_scorers_min_starts", HTML)
        self.assertNotIn("top_by_manager", HTML)
        self.assertIn('h("details"', HTML)
        self.assertIn("more player", HTML)

    def test_team_info_tab_switches_between_teams_instead_of_a_grid_of_cards(self):
        self.assertNotIn("grid-2col", HTML)
        section = HTML[HTML.index('pg.append(section("Scorers by team"))'):HTML.index("const benchRows")]
        self.assertIn('class: "teamtab"', section)
        self.assertIn("activeEntryId = m.entry_id; paintTeam()", section)

    def test_biggest_bench_misses_and_single_player_rounds_are_one_row_tables(self):
        # These used to be <ul class="plist"> lists that wrapped onto two
        # lines once a name was long enough -- now a table, which never
        # wraps a cell (it scrolls sideways on overflow instead).
        self.assertIn("function rankedList(rows, cols)", HTML)
        section = HTML[HTML.index("const benchRows ="):HTML.index('card("Biggest single-player rounds"') + 500]
        self.assertIn("rankedList(P.missed", section)
        self.assertIn("rankedList(P.best_rounds", section)
        self.assertNotIn('class: "plist"', section)

    def test_biggest_single_player_rounds_labels_the_live_round(self):
        self.assertIn("D.live_round && p.gw === D.live_round.gw", HTML)
        self.assertIn("Includes the live round in progress", HTML)

    def test_scorer_table_is_a_single_table_so_expanded_rows_stay_aligned(self):
        # Splitting the visible/expanded rows into two separate <table>
        # elements let each size its columns independently, so the "show
        # more" rows didn't line up with the header above. One table/tbody,
        # with extra rows just not rendered until "Show more" is clicked,
        # keeps every row's columns aligned with the shared header.
        section = HTML[HTML.index("function scorerTable("):HTML.index("pg.append(section(\"Scorers by team\"))")]
        self.assertNotIn("headBody", section)
        self.assertNotIn("restBody", section)
        self.assertIn("h(\"table\", {}, thead, body)", section)
        self.assertIn("showAll ? sorted : sorted.slice(0, 5)", section)

    def test_scorer_table_shows_live_points_and_still_on_squad(self):
        self.assertIn("p.live_points != null", HTML)
        self.assertIn('p.on_squad ? h("span", { class: "tag-squad"', HTML)
        self.assertIn("still on the squad", HTML)
        # The name itself stays plain text; only the pill is coloured.
        self.assertNotIn('class: p.on_squad ? "up" : ""', HTML)

    def test_squad_pill_reuses_the_free_agent_pill_styling(self):
        self.assertIn(".tag-free, .tag-squad {", HTML)

    def test_rank_bracket_pivot_lives_on_all_players_above_the_main_table(self):
        # Brackets are by overall rank in the full player pool (1st-10th
        # highest scorer, 11th-20th, ...), not by points value -- a
        # "1-10" bucket is the 10 highest scorers across all players, so
        # ranking by points descending and slicing is the right approach,
        # not filtering by a total_points range.
        self.assertIn("Squad by overall rank bracket", HTML)
        self.assertIn('"1–10"', HTML)
        self.assertIn("byRank.slice(lo - 1, hi)", HTML)
        self.assertIn("[...AP].sort((a, b) => b.total_points - a.total_points)", HTML)
        section_order = HTML.index('pg.append(section("All players"));')
        pivot_idx = HTML.index("Squad by overall rank bracket")
        table_idx = HTML.index('pg.append(card("Every Premier League player"')
        self.assertTrue(section_order < pivot_idx < table_idx)
        self.assertIn("not players who scored 1 to 10 points", HTML)
        players_section = HTML[HTML.index('pg = panels.players;'):HTML.index('/* all players */')]
        self.assertNotIn("Squad by overall rank bracket", players_section)

    def test_fixtures_tab_shows_next_five_with_fdr_colours_and_favourite_marker(self):
        self.assertIn('"fixtures", "Fixtures"', HTML)
        self.assertIn("D.fixtures_by_team", HTML)
        self.assertIn("--fdr-1", HTML)
        self.assertIn("--fdr-5", HTML)
        self.assertIn('f.favourite === true ? h("span", { class: "fav" }, "★") : null', HTML)
        self.assertIn('`Fixture ${i + 1}`', HTML)

    def test_fixtures_tab_has_an_fdr_legend(self):
        self.assertIn('h("ul", { class: "legend" }, [1, 2, 3, 4, 5].map(', HTML)
        self.assertIn('"Easy"', HTML)
        self.assertIn('"Hard"', HTML)

    def test_fixtures_tab_handles_no_fixture_data(self):
        self.assertIn("isn't available yet", HTML)

    def test_fixtures_tab_ranks_by_average_difficulty(self):
        self.assertIn('{ key: "avg", label: "Avg FDR"', HTML)
        self.assertIn('makeSortHeader(COLS, "avg", 1)', HTML)
        self.assertIn("function avgFdr(t)", HTML)

    def test_fixtures_tab_has_round_toggles_and_easiest_hardest_filter(self):
        self.assertIn('"5 easiest schedules"', HTML)
        self.assertIn('"5 hardest schedules"', HTML)
        self.assertIn("Rounds included in the ranking", HTML)
        self.assertIn("included.filter(Boolean).length <= 1", HTML)

    def test_live_round_tab_shows_a_pitch_with_captain_and_vice_captain_badges(self):
        self.assertIn('["liveround", "Live round"]', HTML)
        self.assertIn("D.current_round", HTML)
        self.assertIn('class: "badge c", title: "Captain"', HTML)
        self.assertIn('class: "badge vc", title: "Vice-captain"', HTML)
        self.assertIn('class: "pitch"', HTML)

    def test_live_round_pitch_is_ordered_keeper_first_and_rows_never_wrap(self):
        self.assertIn('const POS_ORDER = ["GKP", "DEF", "MID", "FWD"];', HTML)
        self.assertIn(".pitch-row { display: flex; justify-content: center; align-items: flex-start; gap: 4px; flex-wrap: nowrap; }", HTML)
        self.assertIn("flex: 0 1 19%", HTML)

    def test_live_round_player_chip_opens_a_modal_with_full_stats(self):
        self.assertIn('onclick: () => openPlayerModal(p)', HTML)
        self.assertIn("function openPlayerModal(p)", HTML)
        self.assertIn('class: "modal-backdrop"', HTML)
        self.assertIn('statRow("Minutes"', HTML)
        self.assertIn('statRow("Defensive contribution"', HTML)
        self.assertIn('ev.key === "Escape"', HTML)

    def test_live_round_highlights_players_who_have_played(self):
        self.assertIn('class: p.minutes > 0 ? "player-chip played" : "player-chip"', HTML)
        # On a green pitch, a green "played" tint is hard to see, so the
        # players who haven't played are faded instead.
        self.assertIn(".player-chip:not(.played) { opacity: .5; box-shadow: inset 0 0 0 1px rgba(0,0,0,.18); }", HTML)
        self.assertNotIn(".player-chip.played {", HTML)

    def test_live_round_pitch_has_score_and_played_count_corner_boxes(self):
        self.assertIn('class: "pitch-box l", title: "Round score"', HTML)
        self.assertIn("const playedCount = t.xi.filter(p => p.minutes > 0).length;", HTML)
        self.assertIn("`${playedCount}/${t.xi.length}`", HTML)
        self.assertNotIn("Round score: ${", HTML)

    def test_transactions_tab_has_transfer_suggestions_with_a_team_switcher(self):
        start = HTML.index("/* transactions */")
        block = HTML[start:HTML.index("const rows = ranked.map", start)]
        self.assertIn("const TS = D.transfer_suggestions;", block)
        self.assertIn('card("Transfer suggestions"', block)
        self.assertIn("sgActive = m.entry_id; paintSuggestions();", block)
        self.assertIn('kind === "in" ? "IN" : "OUT"', block)
        self.assertIn("fdrColor(f.difficulty)", block)
        self.assertIn('href: "https://draft.premierleague.com/", target: "_blank", rel: "noopener"', block)

    def test_suggestion_cards_never_overflow_a_phone_screen(self):
        # A grid track grows to fit unwrapped text (a long injury note)
        # unless it's explicitly allowed to shrink.
        self.assertIn(".sg-list { display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; }", HTML)

    def test_fdr_colour_helpers_are_shared_not_redeclared(self):
        self.assertEqual(HTML.count("const fdrColor = d =>"), 1)
        self.assertEqual(HTML.count("const fdrInk = d =>"), 1)

    def test_live_round_shows_bonus_on_chips_modal_and_table(self):
        self.assertIn("if (p.bonus) parts.push(`${p.bonus}B`);", HTML)
        # Right after minutes, so a narrow chip never cuts it off.
        self.assertLess(HTML.index("parts.push(`${p.minutes}'`)"), HTML.index("parts.push(`${p.bonus}B`)"))
        self.assertLess(HTML.index("parts.push(`${p.bonus}B`)"), HTML.index("parts.push(`${p.goals_scored}G`)"))
        self.assertIn('statRow("Bonus", fmt(p.bonus))', HTML)
        self.assertIn("`incl. ${fmt(p.bonus)} bonus`", HTML)
        self.assertIn('{ key: "bonus", label: "Bonus", num: true, get: p => p.bonus }', HTML)

    def test_live_round_tab_has_a_team_switcher(self):
        self.assertIn('class: "teamtab"', HTML)
        self.assertIn("activeEntryId = m.entry_id", HTML)

    def test_live_round_tab_table_is_sortable_and_filterable_by_club_and_position(self):
        self.assertIn('makeSortHeader(COLS, "points", -1)', HTML)
        self.assertIn('{ key: "defensive_contribution", label: "DEFCON"', HTML)
        self.assertIn('"aria-label": "Filter by club"', HTML)
        self.assertIn('"aria-label": "Filter by position"', HTML)

    def test_live_round_tab_table_is_also_filterable_by_owner(self):
        self.assertIn('h("div", { class: "filters" }, ownerSel, clubSel, posSel)', HTML)
        self.assertIn('Filter by owner, club or position', HTML)

    def test_live_round_tab_table_shows_top_20_with_a_show_all_toggle(self):
        self.assertIn("const LIM = 20;", HTML)
        self.assertIn("showAll = !showAll; render();", HTML)
        self.assertIn('`Show all ${sorted.length}`', HTML)
        self.assertIn('"Show fewer"', HTML)

    def test_live_round_tab_handles_no_round_yet(self):
        self.assertIn("Appears once the first gameweek has started.", HTML)

    def test_scorer_table_is_sortable_by_name_starts_points_and_avg(self):
        self.assertIn('key: "name"', HTML)
        self.assertIn('key: "starts"', HTML)
        self.assertIn('key: "points"', HTML)
        self.assertIn('key: "avg"', HTML)
        self.assertIn("Avg/start", HTML)
        self.assertIn("p.points / p.starts", HTML)
        self.assertIn('role: "button"', HTML)

    def test_closest_round_removed_from_records(self):
        self.assertNotIn("Closest round", HTML)

    def test_every_round_table_uses_a_muted_red_to_green_scale(self):
        self.assertIn("function roundColor", HTML)
        self.assertIn("--rs-lo", HTML)
        self.assertIn("--rs-hi", HTML)
        self.assertIn("color-mix(in oklab,", HTML)

    def test_every_round_gradient_is_scaled_across_all_rounds(self):
        # The color scale must be computed once from every finished round's
        # scores, not reset per row, so shades are comparable table-wide.
        self.assertIn("allRoundVals", HTML)
        self.assertIn("const allLo = Math.min(...allRoundVals), allHi = Math.max(...allRoundVals);", HTML)

    def test_points_per_round_chart_extends_to_the_live_round(self):
        self.assertIn("const chartGws = D.live_round ? [...gws, D.live_round.gw] : gws;", HTML)
        self.assertIn("D.live_round.scores[s.m.entry_id] ?? 0", HTML)
        self.assertIn("xs: chartGws, series: chartSeries", HTML)

    def test_tab_order_matches_the_requested_layout(self):
        tabs_line = re.search(r'const TABS = \[.*?\];', HTML).group(0)
        order = [k for k in re.findall(r'\["(\w+)",', tabs_line)]
        self.assertEqual(order, ["overview", "liveround", "rounds", "players", "transactions", "fixtures", "allplayers", "justice", "streaks", "awards", "h2h"])

    def test_players_tab_is_labeled_team_info(self):
        self.assertIn('["players", "Team info"]', HTML)

    def test_all_players_table_has_the_required_columns(self):
        for key in ("name", "club", "pos", "draft_pick", "owner", "total_points", "avg_points"):
            self.assertIn(f'key: "{key}"', HTML)
        self.assertIn("Draft rank", HTML)

    def test_all_players_undrafted_shown_as_dash_not_zero(self):
        self.assertIn('p.draft_pick == null ? "–"', HTML)
        self.assertNotIn('`Pick ${p.draft_pick || 0}`', HTML)

    def test_all_players_free_agent_label(self):
        self.assertIn('"Free agent"', HTML)

    def test_all_players_filters_present(self):
        self.assertIn('"Filter by owner"', HTML)
        self.assertIn('"Filter by position"', HTML)
        self.assertIn('"Filter by club"', HTML)
        self.assertIn('"Filter by player name"', HTML)

    def test_all_players_defaults_to_showing_everyone_with_a_toggle_to_narrow_it(self):
        self.assertIn("let showEveryone = true;", HTML)
        self.assertIn("everyoneToggle.checked = true;", HTML)
        self.assertIn("p.ever_owned", HTML)
        self.assertIn("Show every player", HTML)

    def test_all_players_free_agent_shown_as_a_green_pill(self):
        self.assertIn('class: "tag-free"', HTML)
        self.assertIn(".tag-free, .tag-squad {", HTML)
        self.assertIn("border-radius: 999px", HTML)

    def test_all_players_columns_are_sortable(self):
        header = HTML[HTML.index("/* all players */"):HTML.index("/* footer + checks */")]
        self.assertIn("makeSortHeader(COLS", header)
        self.assertIn("sorter.row(render)", header)

    def test_players_and_all_players_tables_share_one_sort_helper(self):
        # Both tables should reuse the same helper rather than each
        # hand-rolling their own click-to-sort/aria-sort/keyboard logic.
        self.assertEqual(HTML.count("function makeSortHeader("), 1)
        self.assertIn("makeSortHeader(SCORER_COLS", HTML)
        self.assertIn("makeSortHeader(COLS", HTML)

    def test_tab_bar_does_not_rubber_band_when_swiped(self):
        self.assertIn("overscroll-behavior-x: contain;", HTML)

    def test_tab_bar_shows_an_edge_shadow_like_scrollable_tables(self):
        # With eleven tabs the bar overflows on desktop too, not just
        # mobile -- same scroll-shadow technique as .tbl-wrap so it's
        # clear there's more to scroll to, not just a cut-off list.
        tabs_css = HTML[HTML.index(".tabs {"):HTML.index(".tabs::-webkit-scrollbar")]
        self.assertIn("no-repeat local", tabs_css)
        self.assertIn("no-repeat scroll", tabs_css)
        self.assertIn("var(--page);", tabs_css)  # opaque base, since the bar is sticky

    def test_feedback_is_removed(self):
        for needle in ("Feedback", "feedback", "openFeedbackIssue", "activeTabLabel"):
            self.assertNotIn(needle, HTML)

    def test_header_only_has_the_theme_toggle(self):
        header = re.search(r'app\.append\(h\("header".*?\)\)\);', HTML, re.S).group(0)
        self.assertIn("toggleTheme", header)
        self.assertEqual(header.count('h("button"'), 1)

    def test_trends_charts_extend_to_the_live_round(self):
        self.assertIn("const trendGws = D.live_round ? [...gws, D.live_round.gw] : gws;", HTML)
        self.assertIn("PM[m.entry_id].total", HTML)
        self.assertIn("PM[m.entry_id].rank", HTML)
        self.assertIn("`GW${g} live`", HTML)

    def test_data_checks_explains_an_unsubbed_live_total_instead_of_flagging_it(self):
        self.assertIn('"through_finished_plus_live_unsubbed"', HTML)
        self.assertIn("site's live round isn't subbed yet", HTML)

    def test_table_of_justice_tab_ranks_by_deserved_total_and_labels_the_gap(self):
        panel = HTML[HTML.index("/* table of justice */"):HTML.index("/* streaks & badges */")]
        self.assertIn("D.justice.map(", panel)
        self.assertIn("j.deserved_total", panel)
        self.assertIn("j.actual_rank", panel)
        self.assertIn("`Robbed by ${j.luck_delta}`", panel)
        self.assertIn("`Blessed by ${-j.luck_delta}`", panel)
        self.assertIn('"Spot on"', panel)

    def test_table_of_justice_handles_no_finished_gameweeks_yet(self):
        panel = HTML[HTML.index("/* table of justice */"):HTML.index("/* streaks & badges */")]
        self.assertIn("if (!gws.length) pg.append(emptyMsg(", panel)

    def test_streaks_tab_switches_between_managers_like_team_info(self):
        panel = HTML[HTML.index("/* streaks & badges */"):HTML.index("/* weekly awards */")]
        self.assertIn('class: "teamtab"', panel)
        self.assertIn("activeEntryId = m.entry_id; paintStreaks();", panel)

    def test_streaks_tab_shows_current_and_best_for_each_streak_type(self):
        panel = HTML[HTML.index("/* streaks & badges */"):HTML.index("/* weekly awards */")]
        self.assertIn("s.win[activeEntryId].current", panel)
        self.assertIn("s.win[activeEntryId].best", panel)
        self.assertIn("s.top2[activeEntryId].current", panel)
        self.assertIn("s.cold[activeEntryId].best", panel)

    def test_streaks_tab_badges_account_for_ties(self):
        # Every badge is awarded to every manager tied for the lead, not
        # just the first one found.
        panel = HTML[HTML.index("/* streaks & badges */"):HTML.index("/* weekly awards */")]
        self.assertIn("function leadersBy(fn) {", panel)
        self.assertIn("M.filter(m => fn(PM[m.entry_id]) === best).map(m => m.entry_id)", panel)

    def test_streaks_tab_handles_no_finished_gameweeks_yet(self):
        panel = HTML[HTML.index("/* streaks & badges */"):HTML.index("/* weekly awards */")]
        self.assertIn("if (!gws.length) pg.append(emptyMsg(", panel)

    def test_weekly_awards_has_no_captain_based_category(self):
        panel = HTML[HTML.index("/* weekly awards */"):HTML.index("/* head to head */")]
        self.assertIn("No captain-based awards", panel)  # the explanatory subtitle
        for needle in ("is_captain", "is_vice_captain", "vice-captain", "Captain of the week"):
            self.assertNotIn(needle, panel)

    def test_weekly_awards_steps_through_gameweeks_defaulting_to_latest(self):
        panel = HTML[HTML.index("/* weekly awards */"):HTML.index("/* head to head */")]
        self.assertIn("let awardIdx = D.weekly_awards.length - 1;", panel)
        self.assertIn("awardIdx--; paintAwards();", panel)
        self.assertIn("awardIdx++; paintAwards();", panel)
        self.assertIn("prevBtn.disabled = awardIdx === 0;", panel)
        self.assertIn("nextBtn.disabled = awardIdx === D.weekly_awards.length - 1;", panel)

    def test_weekly_awards_skips_climber_faller_when_absent(self):
        panel = HTML[HTML.index("/* weekly awards */"):HTML.index("/* head to head */")]
        self.assertIn("if (!a) continue;", panel)

    def test_weekly_awards_handles_no_finished_gameweeks_yet(self):
        panel = HTML[HTML.index("/* weekly awards */"):HTML.index("/* head to head */")]
        self.assertIn("if (!D.weekly_awards.length) pg.append(emptyMsg(", panel)

    def test_h2h_tab_defaults_to_the_top_two_ranked_managers(self):
        panel = HTML[HTML.index("/* head to head */"):HTML.index("/* players */")]
        self.assertIn("selA.value = ranked[0].entry_id;", panel)
        self.assertIn("selB.value = ranked[1].entry_id;", panel)

    def test_h2h_tab_guards_against_picking_the_same_manager_twice(self):
        panel = HTML[HTML.index("/* head to head */"):HTML.index("/* players */")]
        self.assertIn("if (a === b) {", panel)

    def test_h2h_record_counts_finished_rounds_only_chart_extends_to_live(self):
        panel = HTML[HTML.index("/* head to head */"):HTML.index("/* players */")]
        self.assertIn("for (const r of finishedRounds) {", panel)
        self.assertIn("if (D.live_round) {", panel)
        self.assertIn("chartGws = [...gws, D.live_round.gw];", panel)

    def test_h2h_chart_reuses_the_shared_line_chart_component(self):
        panel = HTML[HTML.index("/* head to head */"):HTML.index("/* players */")]
        self.assertIn("lineChart(host1,", panel)

    def test_h2h_season_totals_compare_points_bench_and_moves(self):
        panel = HTML[HTML.index("/* head to head */"):HTML.index("/* players */")]
        self.assertIn('metricBars("Total points", "pts", a, b, p => p.total)', panel)
        self.assertIn('metricBars("Bench points", "pts", a, b, p => p.bench_points)', panel)
        self.assertIn('metricBars("Moves made", "moves", a, b, p => p.tx_accepted)', panel)


if __name__ == "__main__":
    unittest.main()
