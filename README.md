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

The dashboard has four tabs: Overview, Rounds, Transactions and Players. You can link straight to one, for example `index.html#rounds`.

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

## Rules used

- **Rounds won:** the top score among all managers in a gameweek. A tie counts as a win for each tied manager.
- **Transactions:** accepted moves only. Denied bids are shown separately.
- **Highest and lowest round:** finished gameweeks only.

## New season

Draft leagues get a new ID each season. Change `league_id` in `config.json`, move or delete `data/raw/` (keep it if you want the old data), and run `python3 update.py`.

## Limits

- The FPL Draft API is unofficial and can change without notice. Raw downloads are kept in `data/raw/` so nothing is lost if it does.
- Trades between managers are not included yet.
- Demo data is in `docs/data.js` until you run the first update. Regenerate it with `python3 tests/make_demo.py`.

## Tests

```
python3 -m unittest discover -s tests -v
```

The tests use invented data and check the scoring, records and caching logic. They do not call the real API.
