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
        self.assertIn("`Pts include live GW${D.live_round.gw}.`", HTML)

    def test_header_subtitle_reflects_live_not_excluded(self):
        self.assertIn("`GW${meta.current_gw} live`", HTML)
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
        section_order = HTML.index('pg = panels.allplayers;')
        pivot_idx = HTML.index("Squad by overall rank bracket")
        table_idx = HTML.index('pg.append(card("Every Premier League player"')
        self.assertTrue(section_order < pivot_idx < table_idx)
        self.assertIn("Each squad by season-points rank", HTML)
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
        self.assertIn("Rounds in the ranking", HTML)
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

    def test_live_round_shows_bonus_as_a_colour_coded_box(self):
        # 3 green, 2 blue, 1 purple -- a double gameweek can exceed 3 (green).
        self.assertIn("bonus-box b${Math.min(n, 3)}", HTML)
        self.assertIn(".bonus-box.b3 { background: #1f9d55; }", HTML)
        self.assertIn(".bonus-box.b2 { background: #2a78d6; }", HTML)
        self.assertIn(".bonus-box.b1 { background: #8b5cf6; }", HTML)
        # On the card corner, next to the pop-up's points, and in the table.
        self.assertIn('bonusBox(p.bonus, "corner")', HTML)
        self.assertIn('`${fmt(p.points)} pts`, bonusBox(p.bonus, "lg")', HTML)
        self.assertIn("bonusBox(p.bonus) || fmt(p.bonus)", HTML)
        self.assertIn('statRow("Bonus", fmt(p.bonus))', HTML)
        self.assertIn('{ key: "bonus", label: "Bonus", num: true, get: p => p.bonus }', HTML)
        # The box replaces the old text versions, so bonus isn't shown twice.
        self.assertNotIn("`${p.bonus}B`", HTML)
        self.assertNotIn("bonus`) : null", HTML)

    def test_live_round_has_a_livescore_match_list_between_lineups_and_all_players(self):
        start = HTML.index("/* live round */") if "/* live round */" in HTML else 0
        lineups = HTML.index('card("Team lineups"', start)
        matches = HTML.index('card("Matches"', start)
        every = HTML.index("const LIM = 20;", lineups)
        self.assertLess(lineups, matches)
        self.assertLess(matches, every)
        self.assertIn("const MX = CR.matches || [];", HTML)
        self.assertIn('m.status === "live" ? h("span", { class: "mx-status live", title: "Live" }, clockEl(m))', HTML)
        self.assertIn('${p.name} (OG)', HTML)  # own goals count for the other side

    def test_tapping_a_match_opens_a_player_overview(self):
        self.assertIn("function openMatch(m)", HTML)
        self.assertIn('modalCard.className = "modal-card wide";', HTML)
        self.assertIn('["Min", "G", "A", "CS", "DC", "B", "Pts"]', HTML)
        self.assertIn("bonusBox(p.bonus)", HTML)
        self.assertIn('title: `Owned by ${nameOf(byId[p.owner_entry_id])}`', HTML)
        # The player pop-up goes back to its normal width after a match pop-up.
        self.assertIn('function openPlayerModal(p) {\n      modalCard.className = "modal-card";', HTML)

    def test_live_matches_show_a_counting_minute_with_a_blinking_tick(self):
        self.assertIn("function liveMinute(m, now = Date.now())", HTML)
        # Snapshot minute counts on in the browser, capped per half.
        self.assertIn("const cap = m.minutes <= 45 ? 45 : 90;", HTML)
        self.assertIn("setInterval(() => liveClocks.forEach(p => p()), 20000);", HTML)
        self.assertIn(".mx-tick { animation: mx-blink 1s step-end infinite; }", HTML)
        self.assertIn("@media (prefers-reduced-motion: reduce) { .mx-tick { animation: none; } }", HTML)
        self.assertIn('["Live · ", h("span", { class: "mx-status live" }, clockEl(m))]', HTML)

    def test_live_match_rows_are_tinted_green_including_teams(self):
        self.assertIn(".mx-row.live { background: color-mix(in oklab, var(--good) 12%, transparent); }", HTML)
        self.assertIn(".mx-row.live .mx-team, .mx-row.live .mx-score { color: var(--good); }", HTML)
        self.assertIn(".mx-status.live { color: var(--good); }", HTML)
        self.assertNotIn(".mx-row.live .mx-score { color: var(--bad); }", HTML)

    def test_match_rows_never_cut_off_team_names(self):
        self.assertIn(".mx-team { font-size: 14px; font-weight: 600; line-height: 1.2; }", HTML)
        self.assertIn("@media (max-width: 380px) { .mx-team { font-size: 12.5px; }", HTML)

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

    def test_removed_tabs_are_gone(self):
        for gone in ('"awards"', '"h2h"', "Weekly awards", "Head-to-head", "panels.awards", "panels.h2h", ".award {",
                     '"justice"', '"streaks"', "Table of justice", "Streaks & badges", "panels.justice", "panels.streaks",
                     "D.justice", "D.streaks", "D.milestones"):
            self.assertNotIn(gone, HTML)

    def test_tab_bar_only_scrolls_sideways(self):
        # overflow-x: auto alone makes the other axis "auto" too, and a tab
        # sticking 1px out below let the bar wobble up and down on phones.
        self.assertIn("overflow-x: auto; overflow-y: hidden;", HTML)
        self.assertIn("box-shadow: inset 0 -1px 0 var(--grid);", HTML)
        self.assertNotIn("border-bottom: 2px solid transparent; margin-bottom: -1px;", HTML)

    def test_slim_layout_drops_headings_that_repeat_the_tab_name(self):
        for gone in ('section("Round by round")', 'section("Live round")', 'section("All players")', 'section("Fixtures")',
                     "updates a few times a day, not in real time"):
            self.assertNotIn(gone, HTML)

    def test_slim_layout_keeps_explanations_behind_a_tap(self):
        self.assertIn('h("details", { class: "info" }, h("summary", {}, `Like-for-like swaps for GW${TS.next_gw}`', HTML)
        self.assertIn('h("details", {}, h("summary", {}, "How it works")', HTML)
        self.assertIn('"Open FPL Draft app ↗"', HTML)
        self.assertIn('h("li", {}, "★ stronger side")', HTML)
        self.assertIn('"▲ top score · ▼ lowest score"', HTML)

    def test_line_charts_draw_team_names_inside_and_tiles_are_compact_on_phones(self):
        # Names sit in a strip inside each chart, above the lines; no separate legend.
        self.assertIn("const rowsTop = cfg.names ? nameRows(cfg.series, W - m.l - m.r) : [];", HTML)
        self.assertEqual(HTML.count("names: true"), 3)  # both Overview charts + Points per round
        self.assertNotIn("legend(M)", HTML)
        self.assertNotIn("function legend(", HTML)
        # Names are text-coloured with a coloured key beside them, never coloured text.
        self.assertIn('fill: "var(--ink-2)", "font-size": NAME_PX }, nameOf(s.m)', HTML)
        self.assertIn(".tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 14px; }", HTML)

    def test_all_players_shows_the_top_20_first(self):
        panel = HTML[HTML.index("pg = panels.allplayers;"):HTML.index("/* fixtures */") if "/* fixtures */" in HTML else None]
        self.assertIn("const LIM = 20;", panel)
        self.assertIn("(showAll ? sorted : sorted.slice(0, LIM)).map(row)", panel)
        self.assertIn("more.textContent = showAll ? \"Show fewer\" : `Show all ${fmt(sorted.length)}`;", panel)
        self.assertIn('onchange: () => { showAll = false; render(); }', panel)  # filters collapse back to 20

    def test_tab_order_matches_the_requested_layout(self):
        tabs_line = re.search(r'const TABS = \[.*?\];', HTML).group(0)
        order = [k for k in re.findall(r'\["(\w+)",', tabs_line)]
        self.assertEqual(order, ["overview", "liveround", "rounds", "players", "transactions", "fixtures", "allplayers"])

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

if __name__ == "__main__":
    unittest.main()
