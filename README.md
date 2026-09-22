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

The dashboard has five tabs: Overview, Rounds, Transactions, Players and Feedback. You can link straight to one, for example `index.html#rounds`.

- Run it once the gameweek is finished. A gameweek still in progress is shown as "live" and is not counted in records or rounds won.
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

If you use the included `.github/workflows/update.yml`, the dashboard rebuilds itself automatically twice a day, at 14:00 and 18:00 Danish time (the workflow works out the current UTC offset itself, since Denmark shifts between UTC+1 and UTC+2), and also whenever `docs/index.html`, a top-level `.py` file, `config.json` or the workflow file changes on `main`. You can still trigger it manually from the Actions tab ("Run workflow").

## Rules used

- **Rounds won:** the top score among all managers in a gameweek. A tie counts as a win for each tied manager.
- **Transactions:** accepted moves only. Denied bids are shown separately.
- **Highest and lowest round:** finished gameweeks only.
- **Lowest scorers (Players tab):** among a manager's starting-XI players, the fewest total points, but only counting players who started at least 60% of the finished rounds so far (rounded up — 3 starts after 5 rounds, 6 after 10). This keeps a single high-scoring substitute appearance from looking like your worst starter. Ties go to whoever started more rounds.

## Transactions tab

- **All moves** can be filtered by team, type (free agent/waiver), result (accepted/denied), gameweek and player name (matches either the player brought in or let go). It shows 12 rows at a time with a "Show all" button; changing a filter goes back to 12 rows of the new, filtered list.
- **Moves per gameweek** (the heat map) lists teams by current league standing, not by the order they were added to the league.

## Feedback

The **Feedback** button in the header (and the **Feedback** tab) opens a new GitHub issue on this repository, with the tab you were viewing pre-filled in the title and body. The Feedback tab also lists the repository's existing issues (title, status, author, date, reply count), fetched live from the public GitHub API in your browser — no server involved. Pull requests are filtered out, and only `https://github.com/` links are ever followed. If GitHub rate-limits the request, the tab shows a message and a **Retry** button instead of breaking.

## New season

Draft leagues get a new ID each season. Change `league_id` in `config.json` and run `python3 update.py`. The next update automatically detects that the league changed (or that the cache predates this check) and re-downloads everything, so last season's cached "finished" gameweeks can't leak into the new season's numbers. You can still move or delete `data/raw/` yourself if you want to keep the old season's raw files elsewhere.

## Limits

- The FPL Draft API is unofficial and can change without notice. Raw downloads are kept in `data/raw/` so nothing is lost if it does.
- Trades between managers are not included yet.
- Demo data is in `docs/data.js` until you run the first update. Regenerate it with `python3 tests/make_demo.py`.

## Tests

```
python3 -m unittest discover -s tests -v
```

The tests use invented data and check the scoring, records and caching logic. They do not call the real API. `test_frontend.py` and `test_workflow.py` are string-level smoke checks on `docs/index.html` and the GitHub Actions workflow (no JS runner or YAML parser is used, to keep this a stdlib-only project) — they guard the markup and schedule described above, and are not a substitute for opening the page in a browser.
