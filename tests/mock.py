"""Synthetic FPL Draft raw data, used by the tests and to render the demo dashboard.

Nothing here is real league data. Player and manager names are invented.
"""
import json
import random
from pathlib import Path

SQUAD = 15  # 2 GK, 5 DEF, 5 MID, 3 FWD
FREE_AGENT_BASE = 100
POS_BY_SLOT = [1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4]  # element_type per squad slot
_A = ["Ber", "Cal", "Dor", "Esk", "Fen", "Gar", "Hal", "Ivo", "Jor", "Kel", "Lun", "Mar",
      "Nor", "Oll", "Par", "Quin", "Ros", "Sal", "Tor", "Uri", "Val", "Wex", "Yar", "Zan"]
_B = ["ton", "ley", "man", "berg", "ski", "vik", "rez", "dal", "sen", "ford", "ini", "ova"]


def fake_name(i):
    return _A[i % len(_A)] + _B[(i * 7 // 3) % len(_B)]


def _dump(root, rel, obj):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def write_raw(root, gw_scores, current_finished=False, subs=None, bench=None,
              transactions=None, league_name="Demo League", people=None,
              spread=False, seed=1, official=None, standings_ok=True,
              free_agent_points=None, element_status=None, draft_choices=None):
    """gw_scores: list (per gameweek) of per-manager XI point targets.

    The last gameweek is the current one. It is treated as in progress unless
    current_finished is True.
    subs: {(gw, manager_index): (out_slot, in_slot)} automatic substitution.
    bench: {(gw, manager_index): points} points on the bench (slot 13).
    official: {(gw, manager_index): points} to include as entry_history.points.
    """
    rng = random.Random(seed)
    subs, bench, official = subs or {}, bench or {}, official or {}
    n_gw = len(gw_scores)
    n_m = len(gw_scores[0])
    people = people or [("Alex", "Andersen", "Team Alpha"), ("Bo", "Berg", "Team Bravo"),
                        ("Cleo", "Clausen", "Team Charlie"), ("Dan", "Dahl", "Team Delta")][:n_m]
    entry_ids = [101 + i for i in range(n_m)]

    _dump(root, "game.json", {"current_event": n_gw, "current_event_finished": current_finished,
                              "next_event": n_gw + 1, "waivers_processed": False})

    def pid(m, slot):  # slot 1..15
        return m * SQUAD + slot

    elements = []
    for m in range(n_m):
        for slot in range(1, SQUAD + 1):
            elements.append({"id": pid(m, slot), "web_name": fake_name(pid(m, slot)),
                             "element_type": POS_BY_SLOT[slot - 1], "team": 1 + pid(m, slot) % 5})
    for k in range(12):
        elements.append({"id": FREE_AGENT_BASE + k, "web_name": fake_name(200 + k),
                         "element_type": 1 + k % 4, "team": 1 + k % 5})
    _dump(root, "bootstrap.json", {"elements": elements,
                                   "teams": [{"id": i, "short_name": n} for i, n in
                                             enumerate(["ARS", "AVL", "BHA", "CHE", "LIV", "MCI"], start=1)]})

    live_all, totals, cur_pts = {}, [0] * n_m, [0] * n_m
    for gw in range(1, n_gw + 1):
        pts = {}
        for m in range(n_m):
            target = gw_scores[gw - 1][m]
            sub = subs.get((gw, m))
            slots = list(range(1, 12))
            base = target
            # a substituted-in bench player contributes part of the XI target
            if sub:
                out_slot, in_slot = sub
                slots.remove(out_slot)
                sub_pts = subs_points(gw, m)
                base = target - sub_pts
                pts[pid(m, out_slot)] = 0
                pts[pid(m, in_slot)] = sub_pts
            if spread:
                w = [rng.random() for _ in slots]
                raw = [int(base * x / sum(w)) for x in w]
                raw[0] += base - sum(raw)
                for s, v in zip(slots, raw):
                    pts[pid(m, s)] = v
            else:
                for s in slots:
                    pts[pid(m, s)] = 0
                pts[pid(m, slots[0])] = base
            for s in (12, 13, 14, 15):
                if sub and s == sub[1]:
                    continue
                if s == 13 and (gw, m) in bench:
                    pts[pid(m, s)] = bench[(gw, m)]
                elif spread:
                    pts[pid(m, s)] = rng.choice([0, 0, 1, 2, 3, 5])
                else:
                    pts.setdefault(pid(m, s), 0)
            totals[m] += target
            if gw == n_gw:
                cur_pts[m] = target
        for k in range(12):
            pts[FREE_AGENT_BASE + k] = (free_agent_points or {}).get((gw, k),
                                                                     rng.randint(0, 9) if spread else 0)
        live_all[gw] = pts
        _dump(root, f"live/gw{gw}.json",
              {"elements": {str(e): {"stats": {"total_points": v}} for e, v in pts.items()}})

    for gw in range(1, n_gw + 1):
        for m, eid in enumerate(entry_ids):
            picks = [{"element": pid(m, s), "position": s, "multiplier": 1,
                      "is_captain": False, "is_vice_captain": False} for s in range(1, SQUAD + 1)]
            body = {"picks": picks, "subs": [], "entry_history": {}}
            sub = subs.get((gw, m))
            if sub:
                body["subs"] = [{"element_in": pid(m, sub[1]), "element_out": pid(m, sub[0]),
                                 "event": gw}]
            if (gw, m) in official:
                body["entry_history"] = {"points": official[(gw, m)]}
            _dump(root, f"entries/{eid}/gw{gw}.json", body)

    _dump(root, "transactions.json", transactions or [])
    _dump(root, "element_status.json", {"element_status": element_status or []})
    _dump(root, "draft_choices.json", draft_choices if draft_choices is not None else [])
    standings = []
    for m, eid in enumerate(entry_ids):
        total = totals[m] if standings_ok else totals[m] + 1
        standings.append({"league_entry": 1000 + m, "event_total": cur_pts[m], "total": total,
                          "rank": 0, "last_rank": 0, "rank_sort": 0})
    _dump(root, "league_details.json", {
        "league": {"id": 1, "name": league_name},
        "league_entries": [{"entry_id": eid, "id": 1000 + m, "entry_name": people[m][2],
                            "player_first_name": people[m][0], "player_last_name": people[m][1],
                            "short_name": people[m][2][:3].upper()}
                           for m, eid in enumerate(entry_ids)],
        "standings": standings})
    return live_all


_SUB_POINTS = {}


def subs_points(gw, m):
    return _SUB_POINTS.get((gw, m), 9)


def tx(id_, gw, m, kind, result, element_in, element_out, added="2026-09-01T10:00:00Z"):
    return {"id": id_, "event": gw, "entry": 101 + m, "kind": kind, "result": result,
            "element_in": element_in, "element_out": element_out, "added": added,
            "index": None, "priority": None}
