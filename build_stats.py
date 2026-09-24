#!/usr/bin/env python3
"""Turn the raw FPL Draft JSON in data/raw/ into docs/data.js for the dashboard.

Scoring notes (your league is a total-points league, so the API has no match
list; round scores are derived):
  * A manager's round score = live points of their final starting XI
    (positions 1-11, after automatic substitutions).
  * If the API also gives an official round score, that one is used and any
    difference is reported under "checks".
  * Only FINISHED gameweeks count towards records and rounds won.
    The gameweek in progress is shown separately as provisional.
  * A tied top score counts as a round won for every tied manager.
  * Transactions = accepted moves only (result "a"). Denied bids are a
    separate stat.
"""
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
DOCS = ROOT / "docs"
POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def _load(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def _rank_desc(values):
    """Competition ranking (1,1,3,4) for {key: value}; higher value = better rank."""
    order = sorted(values.items(), key=lambda kv: -kv[1])
    ranks, prev, prev_rank = {}, None, 0
    for i, (k, v) in enumerate(order, start=1):
        rank = prev_rank if v == prev else i
        ranks[k], prev, prev_rank = rank, v, rank
    return ranks


def build(raw=RAW, now=None):
    raw = Path(raw)
    game = _load(raw / "game.json", {})
    details = _load(raw / "league_details.json", {})
    boot = _load(raw / "bootstrap.json", {})
    tx_raw = _load(raw / "transactions.json", [])
    if isinstance(tx_raw, dict):
        tx_raw = tx_raw.get("transactions", [])
    status_raw = _load(raw / "element_status.json", {})
    status_list = status_raw.get("element_status", []) if isinstance(status_raw, dict) else (status_raw or [])

    cur = int(game.get("current_event") or 0)
    cur_done = bool(game.get("current_event_finished"))
    last_final = cur if cur_done else cur - 1
    all_gws = list(range(1, cur + 1))
    fin_gws = [g for g in all_gws if g <= last_final]

    # ---- managers -------------------------------------------------------
    entries = sorted(details.get("league_entries", []), key=lambda e: e["entry_id"])
    managers = []
    for i, e in enumerate(entries):
        first = (e.get("player_first_name") or "").strip()
        last = (e.get("player_last_name") or "").strip()
        managers.append({
            "entry_id": e["entry_id"],
            "league_entry_id": e.get("id"),
            "team": e.get("entry_name", ""),
            "manager": f"{first} {last}".strip(),
            "first": first or e.get("short_name", ""),
            "color": i,  # fixed slot per manager, never per rank
        })
    eids = [m["entry_id"] for m in managers]

    # ---- players --------------------------------------------------------
    teams = {t["id"]: t.get("short_name") or t.get("name", "") for t in boot.get("teams", [])}
    players = {}
    for p in boot.get("elements", []):
        players[p["id"]] = {
            "name": p.get("web_name") or p.get("second_name") or str(p["id"]),
            "pos": POS.get(p.get("element_type"), "?"),
            "team": teams.get(p.get("team"), ""),
        }

    def pinfo(eid_):
        info = players.get(eid_, {"name": f"Player {eid_}", "pos": "?", "team": ""})
        return {"id": eid_, **info}

    # ---- live points per gameweek --------------------------------------
    pp = {}  # gw -> {element: points}
    for gw in all_gws:
        live = _load(raw / "live" / f"gw{gw}.json", {}) or {}
        elems = live.get("elements", {}) or {}
        pp[gw] = {int(k): (v.get("stats", {}) or {}).get("total_points", 0) or 0
                  for k, v in elems.items()}

    # ---- lineups & round scores ----------------------------------------
    scores = {gw: {} for gw in all_gws}        # gw -> {eid: points or None}
    computed = {gw: {} for gw in all_gws}
    official = {gw: {} for gw in all_gws}
    contrib = {eid: {} for eid in eids}         # eid -> element -> {gw: pts} (in XI)
    bench_pts = {eid: {} for eid in eids}       # eid -> {gw: pts}
    bench_final = {}                            # (eid, gw) -> bench elements after subs
    xi_size = {}
    mismatches = []
    missing = []
    for gw in all_gws:
        for eid in eids:
            data = _load(raw / "entries" / str(eid) / f"gw{gw}.json")
            if not data or not data.get("picks"):
                scores[gw][eid] = None
                missing.append({"gw": gw, "entry_id": eid})
                continue
            picks = sorted(data["picks"], key=lambda p: p.get("position", 99))
            xi = [p["element"] for p in picks if p.get("position", 99) <= 11]
            bench = [p["element"] for p in picks if p.get("position", 99) > 11]
            for s in data.get("subs") or []:
                out_, in_ = s.get("element_out"), s.get("element_in")
                if out_ in xi and in_ in bench:  # ignore if picks are already post-sub
                    xi[xi.index(out_)] = in_
                    bench[bench.index(in_)] = out_
            pts_map = pp.get(gw, {})
            comp = sum(pts_map.get(e, 0) for e in xi)
            computed[gw][eid] = comp
            eh = data.get("entry_history") or {}
            off = eh.get("points") if isinstance(eh.get("points"), int) else None
            official[gw][eid] = off
            scores[gw][eid] = off if off is not None else comp
            if off is not None and off != comp:
                mismatches.append({"gw": gw, "entry_id": eid, "computed": comp, "official": off})
            for e in xi:
                contrib[eid].setdefault(e, {})[gw] = pts_map.get(e, 0)
            bench_pts[eid][gw] = sum(pts_map.get(e, 0) for e in bench)
            bench_final[(eid, gw)] = bench
            xi_size[(gw, eid)] = len(xi)

    complete = [g for g in fin_gws if all(scores[g].get(e) is not None for e in eids)]

    # Points scored by a player while sitting on a manager's bench (after automatic
    # substitutions), one row per player per round. Finished rounds only.
    missed = []
    for (eid, gw), bench_list in bench_final.items():
        if gw not in complete:
            continue
        for el in bench_list:
            pts = pp.get(gw, {}).get(el, 0)
            if pts > 0:
                missed.append({**pinfo(el), "points": pts, "gw": gw, "entry_id": eid})
    missed.sort(key=lambda r: (-r["points"], r["gw"], r["entry_id"], r["id"]))

    # ---- rounds ---------------------------------------------------------
    rounds = []
    for gw in all_gws:
        sc = scores[gw]
        entry = {
            "gw": gw,
            "finished": gw <= last_final,
            "scores": {str(e): sc.get(e) for e in eids},
            "winners": [], "lowest": [], "margin": None,
        }
        vals = [v for v in sc.values() if v is not None]
        if gw in complete and vals:
            hi, lo = max(vals), min(vals)
            entry["winners"] = [e for e in eids if sc[e] == hi]
            entry["lowest"] = [e for e in eids if sc[e] == lo]
            ordered = sorted(vals, reverse=True)
            entry["margin"] = ordered[0] - ordered[1] if len(ordered) > 1 else None
        rounds.append(entry)

    # ---- per-manager stats ---------------------------------------------
    tx_list = []
    for t in tx_raw:
        tx_list.append({
            "id": t.get("id"), "gw": t.get("event"), "entry_id": t.get("entry"),
            "kind": t.get("kind"), "result": t.get("result"), "added": t.get("added"),
            "element_in": t.get("element_in"), "element_out": t.get("element_out"),
        })
    accepted = [t for t in tx_list if t["result"] == "a"]

    # ---- all Premier League players (not just those rostered here) ------
    # "owner" in element_status is a manager's entry_id (the same id used
    # everywhere else in this file), or None for a free agent.
    owner_by_element = {s["element"]: s.get("owner") for s in status_list if s.get("owner") is not None}
    ever_owned = (set(owner_by_element)
                  | {t["element_in"] for t in accepted if t["element_in"] is not None}
                  | {t["element_out"] for t in accepted if t["element_out"] is not None})

    def points_per_game(p):
        raw_ppg = p.get("points_per_game")
        try:
            if raw_ppg not in (None, ""):
                return round(float(raw_ppg), 1)
        except (TypeError, ValueError):
            pass
        starts_ct = p.get("starts") or 0
        return round((p.get("total_points", 0) or 0) / starts_ct, 1) if starts_ct else 0.0

    all_players = []
    for p in boot.get("elements", []):
        pid_ = p["id"]
        all_players.append({
            "id": pid_,
            "name": p.get("web_name") or p.get("second_name") or str(pid_),
            "club": teams.get(p.get("team"), ""),
            "pos": POS.get(p.get("element_type"), "?"),
            "owner_entry_id": owner_by_element.get(pid_),
            "total_points": p.get("total_points", 0) or 0,
            "avg_points": points_per_game(p),
            # Filled in once /draft/{league_id}/choices parsing is wired up.
            "draft_pick": None,
            "ever_owned": pid_ in ever_owned,
        })
    all_players.sort(key=lambda r: r["name"])

    cum, rank_by_gw = {e: [] for e in eids}, {e: [] for e in eids}
    running = {e: 0 for e in eids}
    for gw in complete:
        for e in eids:
            running[e] += scores[gw][e]
            cum[e].append(running[e])
        for e, r in _rank_desc(running).items():
            rank_by_gw[e].append(r)

    per_manager = {}
    for e in eids:
        gs = [(gw, scores[gw][e]) for gw in complete]
        pts = [p for _, p in gs]
        wins = sum(1 for r in rounds if e in r["winners"])
        lows = sum(1 for r in rounds if e in r["lowest"])
        best = max(gs, key=lambda x: (x[1], -x[0])) if gs else None
        worst = min(gs, key=lambda x: (x[1], x[0])) if gs else None
        mine = [t for t in tx_list if t["entry_id"] == e]
        acc = [t for t in mine if t["result"] == "a"]
        per_manager[str(e)] = {
            "rounds_played": len(pts),
            "total": sum(pts),
            "average": round(sum(pts) / len(pts), 1) if pts else None,
            "stdev": round(statistics.pstdev(pts), 1) if len(pts) > 1 else None,
            "wins": wins,
            "lows": lows,
            "best": {"gw": best[0], "points": best[1]} if best else None,
            "worst": {"gw": worst[0], "points": worst[1]} if worst else None,
            "tx_accepted": len(acc),
            "tx_free_agent": sum(1 for t in acc if t["kind"] == "f"),
            "tx_waiver": sum(1 for t in acc if t["kind"] == "w"),
            "tx_denied": sum(1 for t in mine if t["result"] != "a"),
            "bench_points": sum(v for g, v in bench_pts[e].items() if g in complete),
            "rank": None,
        }
    for e, r in _rank_desc({e: per_manager[str(e)]["total"] for e in eids}).items():
        per_manager[str(e)]["rank"] = r

    # ---- records --------------------------------------------------------
    all_rounds = [(scores[gw][e], gw, e) for gw in complete for e in eids]
    records = {}
    if all_rounds:
        hi = max(all_rounds, key=lambda x: (x[0], -x[1]))
        lo = min(all_rounds, key=lambda x: (x[0], x[1]))
        records["highest_round"] = {"points": hi[0], "gw": hi[1], "entry_id": hi[2]}
        records["lowest_round"] = {"points": lo[0], "gw": lo[1], "entry_id": lo[2]}
        margins = [(r["margin"], r["gw"], r["winners"]) for r in rounds if r["margin"] is not None]
        if margins:
            big = max(margins, key=lambda x: (x[0], -x[1]))
            small = min(margins, key=lambda x: (x[0], x[1]))
            records["biggest_win"] = {"margin": big[0], "gw": big[1], "entry_ids": big[2]}
            records["closest_round"] = {"margin": small[0], "gw": small[1], "entry_ids": small[2]}
        best_streak = {"length": 0, "entry_id": None, "from": None, "to": None}
        for e in eids:
            run, start = 0, None
            for r in rounds:
                if r["gw"] in complete and e in r["winners"]:
                    run = run + 1 if run else 1
                    start = start if run > 1 else r["gw"]
                    if run > best_streak["length"]:
                        best_streak = {"length": run, "entry_id": e, "from": start, "to": r["gw"]}
                else:
                    run, start = 0, None
        records["longest_win_streak"] = best_streak
        records["ties_for_win"] = sum(1 for r in rounds if len(r["winners"]) > 1)

    # ---- transactions ---------------------------------------------------
    tx_matrix = {str(e): {str(gw): 0 for gw in all_gws} for e in eids}
    for t in accepted:
        g = str(t["gw"])
        if str(t["entry_id"]) in tx_matrix and g in tx_matrix[str(t["entry_id"])]:
            tx_matrix[str(t["entry_id"])][g] += 1

    def since(element, from_gw):
        return sum(pp[g].get(element, 0) for g in fin_gws if g >= (from_gw or 0))

    moves = []
    for t in sorted(tx_list, key=lambda x: x.get("added") or "", reverse=True):
        row = {**t,
               "in": pinfo(t["element_in"]) if t["element_in"] is not None else None,
               "out": pinfo(t["element_out"]) if t["element_out"] is not None else None}
        if t["result"] == "a" and t["element_in"] is not None:
            row["in_points"] = since(t["element_in"], t["gw"])
            row["out_points"] = since(t["element_out"], t["gw"]) if t["element_out"] is not None else 0
            row["delta"] = row["in_points"] - row["out_points"]
            row["in_started_points"] = sum(
                v for g, v in contrib.get(t["entry_id"], {}).get(t["element_in"], {}).items()
                if g >= (t["gw"] or 0) and g in complete)
        moves.append(row)

    # ---- player insights ------------------------------------------------
    # Every player who scored a positive total while in a manager's starting
    # XI, one list per manager. The same real player can appear under more
    # than one manager if they were traded mid-season.
    scorers_by_manager, best_rounds = {}, []
    for e in eids:
        rows = []
        for el, by_gw in contrib[e].items():
            fin = {g: v for g, v in by_gw.items() if g in complete}
            if not fin:
                continue
            for g, v in fin.items():
                best_rounds.append({**pinfo(el), "points": v, "gw": g, "entry_id": e})
            pts = sum(fin.values())
            if pts > 0:
                rows.append({**pinfo(el), "points": pts, "starts": len(fin)})
        scorers_by_manager[str(e)] = sorted(rows, key=lambda r: (-r["points"], r["name"]))
    best_rounds.sort(key=lambda r: (-r["points"], r["gw"]))

    bench = {}
    for e in eids:
        per_gw = {g: v for g, v in bench_pts[e].items() if g in complete}
        worst = max(per_gw.items(), key=lambda kv: (kv[1], -kv[0])) if per_gw else None
        bench[str(e)] = {"total": sum(per_gw.values()),
                         "worst_gw": {"gw": worst[0], "points": worst[1]} if worst else None,
                         "by_gw": {str(g): v for g, v in per_gw.items()}}

    # ---- provisional round ---------------------------------------------
    live_round = None
    if cur and not cur_done:
        live_round = {"gw": cur, "scores": {str(e): scores[cur].get(e) for e in eids}}

    # ---- checks ---------------------------------------------------------
    standings = {s.get("league_entry"): s for s in details.get("standings", [])}
    standing_checks = []
    for m in managers:
        s = standings.get(m["league_entry_id"])
        if not s:
            continue
        through_cur = sum(scores[g].get(m["entry_id"]) or 0 for g in all_gws)
        through_fin = sum(scores[g].get(m["entry_id"]) or 0 for g in fin_gws)
        matches = ("through_current" if through_cur == s.get("total")
                   else "through_finished" if through_fin == s.get("total") else None)
        ev_total = s.get("event_total")
        standing_checks.append({
            "entry_id": m["entry_id"], "site_total": s.get("total"),
            "computed_through_current": through_cur,
            "computed_through_finished": through_fin,
            "matches": matches,
            "site_event_total": ev_total,
            "computed_current_gw": scores[cur].get(m["entry_id"]) if cur else None,
        })
    checks = {
        "lineup_vs_official_mismatches": mismatches,
        "missing_lineups": missing,
        "standings": standing_checks,
        "all_ok": (not mismatches and not missing
                   and all(c["matches"] for c in standing_checks)),
    }

    league = details.get("league", {})
    return {
        "meta": {
            "league_id": league.get("id"),
            "league_name": league.get("name", "FPL Draft league"),
            "current_gw": cur,
            "current_gw_finished": cur_done,
            "last_finished_gw": last_final if last_final > 0 else 0,
            "generated_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
            "demo": False,
        },
        "managers": managers,
        "rounds": rounds,
        "live_round": live_round,
        "per_manager": per_manager,
        "trends": {"gws": complete,
                   "cumulative": {str(e): cum[e] for e in eids},
                   "rank": {str(e): rank_by_gw[e] for e in eids}},
        "records": records,
        "transactions": {"matrix": tx_matrix, "moves": moves},
        "players": {"scorers_by_manager": scorers_by_manager,
                    "best_rounds": best_rounds[:10],
                    "bench": bench, "missed": missed[:10]},
        "all_players": all_players,
        "checks": checks,
    }


def write(data, docs=DOCS):
    docs = Path(docs)
    docs.mkdir(parents=True, exist_ok=True)
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    (docs / "data.js").write_text(f"window.FPL_DATA={js};\n", encoding="utf-8")
    (docs / "data.json").write_text(js, encoding="utf-8")


def summary(data, log=print):
    m = {x["entry_id"]: x for x in data["managers"]}
    pm = data["per_manager"]
    log(f"Built stats for {data['meta']['league_name']} - finished gameweeks: {data['trends']['gws']}")
    for e in sorted(m, key=lambda k: pm[str(k)]["rank"] or 99):
        s = pm[str(e)]
        log(f"  {s['rank']}. {m[e]['team']:<24} {s['total']:>4} pts  wins {s['wins']}  "
            f"moves {s['tx_accepted']}")
    c = data["checks"]
    if c["all_ok"]:
        log("Checks: OK (round scores agree with the site's standings)")
    else:
        log("Checks: PLEASE REVIEW")
        for x in c["standings"]:
            if not x["matches"]:
                log(f"  entry {x['entry_id']}: site total {x['site_total']} vs computed "
                    f"{x['computed_through_current']} (incl. current GW) / "
                    f"{x['computed_through_finished']} (finished GWs only)")
        for x in c["lineup_vs_official_mismatches"]:
            log(f"  GW{x['gw']} entry {x['entry_id']}: computed {x['computed']} vs official {x['official']}")
        for x in c["missing_lineups"]:
            log(f"  missing lineup GW{x['gw']} entry {x['entry_id']}")


if __name__ == "__main__":
    out = build()
    write(out)
    summary(out)
    sys.exit(0)
