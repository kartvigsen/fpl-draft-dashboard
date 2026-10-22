# FPL Draft dashboard

A small dashboard for a friends' FPL Draft league. After each gameweek you run one command; it downloads the league's data and rebuilds a static web page with standings, trends, rounds won, records, transactions and player insights.

Your league is set in `config.json` (`league_id`: 7281).

## What you need

Python 3.8 or newer. Nothing to install, and no login: it only reads public, read-only endpoints on `draft.premierleague.com`. Never put your Premier League password in this project.

## Update after each gameweek

```
python3 update.py
```

Then open `docs/index.html` in a browser. That is the whole routine.

The dashboard has ten tabs: Overview, Live round, Rounds, Team info, Transactions, Fixtures, All players, Table of justice, Streaks & badges and Weekly awards. You can link straight to one, for example `index.html#rounds`.

- Run it any time, including while a gameweek is still in progress — standings and each manager's total points update live. Records and "rounds won" still only count once a gameweek finishes, since bonus points and other adjustments aren't final until then.
- Finished gameweeks are cached in `data/raw/`, so later runs only download the newest gameweek.
- `python3 update.py --no-fetch` rebuilds from what is already downloaded. `--force` re-downloads everything.

## First run: check the numbers

Your league scores on total points, so the API has no per-round scores. The dashboard adds up each manager's starting XI (after automatic substitutions) from the official live player points.

At the bottom of the page, open **Data checks**. It compares the calculated totals with the site's own standings. The first time you run it, check that:

1. The Data checks say all passed. The script also prints this in the terminal.
2. A round score you remember from the site (for example a gameweek you won) matches.

If anything differs, the page shows a warning banner. Send me the terminal output and I'll fix the calculation.

## Publishing for your friends

The `docs/` folder is a complete static site (`index.html` and `data.js`). Options:

- **GitHub Pages:** put this project in a GitHub repository and serve the `docs/` folder. Note that a Pages site is public to anyone with the link, and it contains your friends' names and team names.
- **Just send it:** zip `docs/` and share it, or drop it on any file host.

If you use the included `.github/workflows/update.yml`, the dashboard rebuilds itself automatically five times a day, at 07:00, 12:00, 16:00, 20:00 and 23:00 Danish time (the workflow works out the current UTC offset itself, since Denmark shifts between UTC+1 and UTC+2), and also whenever `docs/index.html`, a top-level `.py` file, `config.json` or the workflow file changes on `main`. You can still trigger it manually from the Actions tab ("Run workflow").

**Add to Home Screen:** the site is installable as an app icon on phones (`docs/manifest.json`, `docs/icons/`, `docs/sw.js`). On iOS, open the site in Safari and use Share → "Add to Home Screen"; on Android/Chrome, use the browser menu's "Install app" / "Add to Home screen". It opens without browser chrome and uses the site's blue bar-chart icon.

## Rules used

- **Standings and total points:** update live while a gameweek is in progress, using that round's provisional score. The Standings table marks a live contribution with a small "(+N live)" next to a manager's points, and a note explains it while a round is in progress. The Overview tab's "Total points" and "Position in the league" charts extend one point further to show the live round too, labelled "GW_ live".
- **Automatic substitutions, live:** the official site only fills in a round's real substitutions once it's finished, so a provisional score (while a round is still live) applies the same rule itself: a starting player with 0 minutes is covered by the next bench player (in bench order) who actually played — a goalkeeper only ever by the bench goalkeeper. Once the round finishes, the official figure is used instead, which can differ slightly if the real substitution rule's formation constraints kick in (not modelled here). Until then, this can make the live total differ from the one shown on the official site — "Data checks" recognizes this specific, expected gap (the site's own live figure not being subbed yet) and doesn't flag it as a mismatch; a row still shows it, labelled "site's live round isn't subbed yet", for transparency.
- **Rounds won:** the top score among all managers in a gameweek. A tie counts as a win for each tied manager. Only finished gameweeks are eligible — a live round can't be "won" until bonus points and the rest are final.
- **Transactions:** accepted moves only. Denied bids are shown separately.
- **Highest and lowest round:** finished gameweeks only.

## Rounds tab

- **Points per round** extends one point further than the last finished gameweek while a round is live, labelled "GW_ live" — the highest/lowest round labels on the chart still only ever point at a finished round, same as the Records table.
- **Every round** shades each score from red through orange and yellow to green, on the same scale across every round and manager (not reset per row), so a shade means the same thing anywhere in the table — on top of the existing ▲/▼ markers for the top and lowest score of each round.
- The **Records** table no longer shows "Closest round" (everything else — highest/lowest round, biggest winning margin, longest winning streak — is unchanged).

## Transactions tab

- **All moves** can be filtered by team, type (free agent/waiver), result (accepted/denied, shown in green/red), gameweek and player name (matches either the player brought in or let go). It shows 12 rows at a time with a "Show all" button; changing a filter goes back to 12 rows of the new, filtered list. There's no Net/points column here — see the Players tab for scoring.
- **Moves per gameweek** (the heat map) lists teams by current league standing, not by the order they were added to the league.

## Live round tab

Everyone's lineup for the current (or just-finished) gameweek, without needing to open the official app. Click a manager's name to switch between a visual pitch view of their squad — starting XI grouped by position (keeper at the top, then defenders, midfielders and forwards), bench below — with each player's points for the round and a badge for the captain (C) and vice-captain (V). A line never splits across rows, even a back five or a five-man midfield. Tap a player for their full stats (minutes, goals, assists, clean sheet, defensive contribution).

Below that, every Premier League player's points and extra stats (minutes, goals, assists, clean sheets, defensive contribution) for the round, highest first — filter by owner (including "Free agent"), club or position, or click a column to sort. Shows the top 20 by default; "Show all" expands to every player, and changing a filter collapses it back to 20.

This updates whenever `update.py` runs (a few times a day on the included schedule), not in real time.

## Team info tab

Click a manager's name to switch to their table of every player who scored a positive total while in that manager's starting XI, with columns for starts, points and average points per start — click a column header to sort by it (click again to reverse). Starts and points include the live gameweek while a round is in progress, same as the Standings total. Sorted by points by default; the top 5 show directly and the rest show under "Show N more players". A player who was traded mid-season appears under both teams, with the points they scored for each. A green "Squad" label next to a name means that player is still on the manager's squad, including the bench — not just the ones who started the round they scored in.

**Biggest bench misses** and **Biggest single-player rounds** are each one row per player (name, club/manager, gameweek, points) — scrolls sideways rather than wrapping a long name onto a second line. **Biggest single-player rounds** also includes the live round in progress (labelled "GW_ live"), ranked alongside finished rounds, not just appended at the end — it just isn't eligible to be the season's single best round until the round finishes, same as every other finished-rounds-only record.

## All players tab

**Squad by overall rank bracket** is a pivot table above the main list: how many players on each manager's current squad (15 players, including the bench) rank in each bracket of the *entire* Premier League player pool, sorted by season total points (1st–10th highest scorer, 11th–20th, ... down to the bottom of the list). Darker cells mean more players. A bracket like "1–10" is the 10 highest scorers across all players, not players who scored 1 to 10 points — sort the table below by Total points to see the full ranking and check who's in which bracket.

Every Premier League player, not just the ones on a roster in this league — filter by owner (including "Free agent"), position or club, or search by name, and click a column header to sort (click again to reverse). Columns:

- **Draft rank** — the pick number from this league's original season draft (e.g. "Pick 23"). A player never drafted (picked up later, or never owned at all) shows "–".
- **Owner** — whoever currently holds the player, which can differ from who drafted them if they moved by waiver or trade. Unowned players are shown as a green "Free agent" pill.
- **Total points** / **Avg points** — the player's actual Premier League season total and per-game average, regardless of whether their fantasy owner ever started them.

The table shows the full Premier League player pool by default — untick "Show every player" to narrow it to players who are or have been owned in this league this season (drafted, waivered or traded at some point).

## Fixtures tab

Every Premier League team's next five fixtures (real match fixtures, nothing to do with this draft league), coloured by that team's own FPL difficulty rating (FDR): 1 (easiest, dark green) through 5 (hardest, dark red). A ★ marks a fixture where the team is the stronger side, comparing both teams' home/away strength ratings for that specific match — not just this team's own difficulty colour, which only reflects the opponent's strength from this team's point of view. Hover a fixture for the gameweek, venue and difficulty.

Teams are ranked by **Avg FDR**, the average difficulty of their next fixtures, easiest first — click "Avg FDR" or "Team" to re-sort. Untick one of the five "Fixture" checkboxes to leave that round out of the ranking (and the table); at least one must stay ticked. The dropdown above narrows the table to just the 5 teams with the easiest or hardest run of fixtures.

This data comes from the classic (non-draft) FPL API, fetched best-effort: if it's briefly unreachable on an update run, the tab just keeps showing whatever was cached last time rather than breaking the rest of the update.

## Table of justice tab

The season standings re-ranked by total points **including bench points** — what the table would look like if every point your squad actually scored had counted, not just the starting XI. Each row shows the gap from where you actually sit: "Robbed by N" means bench points would have put you N places higher; "Blessed by N" means you're sitting N places better than your squad's total deserves.

## Streaks & badges tab

Switch between managers to see hot and cold runs (current and best win streaks, top-2 finishes, and the worst run of last-place finishes), the latest 100-point milestone crossed, and season-long badges (Most round wins, Highest average, Mr. Consistent for lowest week-to-week variance, Rollercoaster for the highest, Bench waster, Market mover, Most bids rejected, and a win-streak badge once someone's strung together more than one). A badge is awarded to every manager tied for the lead, not just the first one found.

## Weekly awards tab

Five trophies for whichever gameweek you step to with the arrows (defaults to the latest finished one): **Top scorer**, **Wooden spoon**, **Bench flop** (most points left on the bench), and **Climber**/**Faller of the week** (biggest rank swing from the previous gameweek — not shown on the first gameweek, since there's nothing to compare against). Nothing captain-based; this league doesn't use captains or bonuses.

## Weekly digest email

`send_digest.py` can email the league a recap after each gameweek finishes — top scorer, wooden spoon, biggest bench blunder, climber/faller of the week, the "Table of Justice" (standings re-ranked as if bench points counted), and the current standings. The wording is picked each week from a bank of hand-written variants in a deliberately salty British/Scandinavian tone, so it doesn't read identically every time.

It's off by default. To turn it on:

1. Preview it first: `python3 send_digest.py --dry-run` renders the current gameweek to `digest_preview.html` without sending anything or touching any state — open it in a browser and check the tone lands before anyone else sees it.
2. Generate a Gmail "app password": Google Account → Security → App passwords (needs 2-Step Verification turned on). This is not your normal Gmail password.
3. In the repo's Settings → Secrets and variables → Actions, add three repository secrets: `GMAIL_USER` (the sending Gmail address), `GMAIL_APP_PASSWORD` (the app password from step 2), and `DIGEST_RECIPIENTS` (a comma-separated list of every recipient's email address). Keep these as secrets, never in a committed file — this repository is public.
4. Set `"digest_enabled": true` in `config.json` and push.

From then on, the scheduled workflow sends the digest automatically the first time it sees a finished gameweek it hasn't sent yet (tracked in `.digest_state.json`), so a gameweek is only emailed once no matter how many times the workflow runs that day.

## New season

Draft leagues get a new ID each season. Change `league_id` in `config.json` and run `python3 update.py`. The next update automatically detects that the league changed (or that the cache predates this check) and re-downloads everything, so last season's cached "finished" gameweeks can't leak into the new season's numbers. You can still move or delete `data/raw/` yourself if you want to keep the old season's raw files elsewhere.

## Limits

- The FPL Draft API is unofficial and can change without notice. Raw downloads are kept in `data/raw/` so nothing is lost if it does. The Fixtures tab also depends on the classic (non-draft) FPL API for real-world fixtures and team strength — same caveat, and it's fetched best-effort so a hiccup there won't break the rest of an update.
- Trades between managers are not included yet.
- Demo data is in `docs/data.js` until you run the first update. Regenerate it with `python3 tests/make_demo.py`.

## Tests

```
python3 -m unittest discover -s tests -v
```

The tests use invented data and check the scoring, records and caching logic. They do not call the real API. `test_frontend.py` and `test_workflow.py` are string-level smoke checks on `docs/index.html` and the GitHub Actions workflow (no JS runner or YAML parser is used, to keep this a stdlib-only project) — they guard the markup and schedule described above, and are not a substitute for opening the page in a browser.
