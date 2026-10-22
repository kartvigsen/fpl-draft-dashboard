#!/usr/bin/env python3
"""Email a savage weekly recap after each gameweek finishes.

    python3 send_digest.py             # send if a new gameweek just finished
    python3 send_digest.py --dry-run   # render to digest_preview.html instead of sending
    python3 send_digest.py --force     # (re)send even if this gameweek was already sent

Reads docs/data.json (built by build_stats.py) and tracks the last gameweek
it sent in .digest_state.json, so a scheduled rebuild that finds nothing new
finished is a silent no-op. Needs three things to actually send:

  - config.json: "digest_enabled": true (off by default, so nobody gets
    emailed before you've previewed the content with --dry-run)
  - the GMAIL_USER and GMAIL_APP_PASSWORD environment variables (an "app
    password" from Google Account -> Security -> App passwords, not your
    normal Gmail password)
  - the DIGEST_RECIPIENTS environment variable: a comma-separated list of
    every recipient's email address

All three secrets are read from the environment only -- never put real
email addresses or passwords in config.json or anywhere else in this
(public) repository. In GitHub Actions, add them as repository secrets
(Settings -> Secrets and variables -> Actions) and pass them to the step's
`env:`.
"""
import json
import os
import random
import smtplib
import ssl
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "docs" / "data.json"
STATE_FILE = ROOT / ".digest_state.json"
CONFIG_FILE = ROOT / "config.json"
PREVIEW_FILE = ROOT / "digest_preview.html"


# ---------- content: numbers come from real data, wording is picked from
# a bank of hand-written variants so the tone doesn't go stale week to week.
# The pick is seeded per gameweek+slot, so a re-run for the same gameweek
# (e.g. --dry-run while drafting) always shows the same line. ----------

SUBJECTS = [
    "GW{gw}: {spoon_first} Hits a New Personal Low",
    "GW{gw}: Spare a Thought for {spoon_first}",
    "GW{gw}: {spoon_first} Finds a New Way to Disappoint Us",
    "GW{gw}: {top_team} Flexes, {spoon_team} Implodes",
]

GREETINGS = [
    "Right then. Grab a cuppa — or if you're feeling continental, a lukewarm filter coffee and a slice of knekkebrød — because gameweek {gw} delivered exactly the chaos we've come to expect from this shower.",
    "Evening, degenerates. Gameweek {gw} is in the books, and as ever, somebody's week was better spent elsewhere.",
    "Settle in. This week's gameweek {gw} recap contains scenes some readers may find upsetting, mostly {spoon_first}'s lineup.",
]

TOP_SCORER = [
    "{team} put up {pts} points this week. Somebody fetch {first} a trophy made of absolutely nothing, because that's the going rate for weekly bragging rights around here.",
    "{pts} points for {team}. Insufferable? Almost certainly. Earned? Also yes.",
    "{team} ran away with {pts} points this week. Everyone else, kindly see yourselves out.",
]

WOODEN_SPOON = [
    "{team} limped to {pts} points. {first}, that's not a lineup, that's a cry for help.",
    "{pts} points. {first}, we've seen better scores from managers who forgot to set a team at all.",
    "{team} mustered a grand total of {pts}. Somewhere, a Janteloven elder is nodding approvingly — {first}, you truly do not think you are anything special, and this week you proved it beyond reasonable doubt.",
]

BENCH_FLOP = [
    "{first} left {pts} points rotting on the bench this week — a genuine contender for worst benching job in the league's history.",
    "{pts} points stranded on {first}'s bench. A moment of silence, please.",
    "Somewhere, {first}'s bench scored {pts} points that will never, ever count. Lagom, this was not.",
]

CLIMBER = [
    "{first} quietly climbed {delta} place{plural} and said absolutely nothing about it, which is more restraint than this chat has shown, ever.",
    "{first} moved up {delta} place{plural} this week. Don't let it go to your head — it will, but don't let it.",
]

FALLER = [
    "{first} dropped {delta} place{plural}. The league giveth, and the league taketh away.",
    "{first} fell {delta} place{plural} this week. Character building, allegedly.",
]

JUSTICE_ROBBED = [
    "If bench points actually counted — they don't, so stop crying — {first} would be sitting {deserved_rank}{deserved_suffix}, not {actual_rank}{actual_suffix}. Somewhere, actual justice is being denied, and we suspect it's on purpose.",
]
JUSTICE_BLESSED = [
    "{first} is sitting a full spot better than their own squad deserves. Bit like parallel parking in a disabled bay because nobody was watching, and getting away with it.",
]
JUSTICE_FAIR = [
    "{first}'s actual rank matches what their squad actually deserves, bench included. Boring. But fair.",
]

SIGNOFFS = [
    "That's the carnage. Set your lineups, make your trades, and {spoon_first} — please, for all our sakes, check your bench before Saturday. The rest of you: don't get comfortable, this league humbles everyone eventually.\n\nSkål and see you next week,\nThe {league} Bot — unpaid, unbothered, unfiltered",
    "That's your lot for gameweek {gw}. Get your transfers in, and {spoon_first}, maybe set an alarm this time.\n\nUntil next week,\nThe {league} Bot",
]


def pick(options, gw, slot):
    return options[random.Random(f"{gw}-{slot}").randrange(len(options))]


def ordinal(n):
    if 10 <= n % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def compute_week(data, gw):
    """Weekly awards + table of justice, as of the given finished gameweek."""
    rounds_by_gw = {r["gw"]: r for r in data["rounds"]}
    r = rounds_by_gw[gw]
    scores = {int(k): v for k, v in r["scores"].items()}
    by_id = {m["entry_id"]: m for m in data["managers"]}
    ids = list(by_id)

    top = max(ids, key=lambda e: scores[e])
    bottom = min(ids, key=lambda e: scores[e])

    bench = data["players"]["bench"]
    bench_by_gw = {eid: bench.get(str(eid), {}).get("by_gw", {}).get(str(gw), 0) for eid in ids}
    bench_flop = max(ids, key=lambda e: bench_by_gw[e])

    climber = faller = None
    prev = rounds_by_gw.get(gw - 1)
    if prev:
        prev_scores = {int(k): v for k, v in prev["scores"].items()}
        prev_rank = {e: sorted(ids, key=lambda x: -prev_scores[x]).index(e) + 1 for e in ids}
        cur_rank = {e: sorted(ids, key=lambda x: -scores[x]).index(e) + 1 for e in ids}
        deltas = {e: prev_rank[e] - cur_rank[e] for e in ids}
        best = max(ids, key=lambda e: deltas[e])
        worst = min(ids, key=lambda e: deltas[e])
        if deltas[best] > 0:
            climber = {"entry_id": best, "delta": deltas[best]}
        if deltas[worst] < 0:
            faller = {"entry_id": worst, "delta": -deltas[worst]}

    justice = []
    for eid in ids:
        pm = data["per_manager"][str(eid)]
        justice.append({"entry_id": eid, "actual_rank": pm["rank"],
                         "deserved_total": pm["total"] + pm["bench_points"]})
    justice.sort(key=lambda j: -j["deserved_total"])
    for i, j in enumerate(justice):
        j["deserved_rank"] = i + 1
        j["luck_delta"] = j["actual_rank"] - j["deserved_rank"]
    most_robbed = max(justice, key=lambda j: j["luck_delta"])
    most_blessed = min(justice, key=lambda j: j["luck_delta"])

    standings = sorted(ids, key=lambda e: data["per_manager"][str(e)]["rank"])

    return {
        "gw": gw, "by_id": by_id,
        "top_scorer": {"entry_id": top, "points": scores[top]},
        "wooden_spoon": {"entry_id": bottom, "points": scores[bottom]},
        "bench_flop": {"entry_id": bench_flop, "points": bench_by_gw[bench_flop]},
        "climber": climber, "faller": faller,
        "most_robbed": most_robbed if most_robbed["luck_delta"] > 0 else None,
        "most_blessed": most_blessed if most_blessed["luck_delta"] < 0 else None,
        "standings": standings,
    }


def render(data, week):
    gw = week["gw"]
    by_id = week["by_id"]
    league = data["meta"]["league_name"]
    top, spoon, flop = week["top_scorer"], week["wooden_spoon"], week["bench_flop"]
    top_m, spoon_m = by_id[top["entry_id"]], by_id[spoon["entry_id"]]

    subject = pick(SUBJECTS, gw, "subject").format(
        gw=gw, spoon_first=spoon_m["first"], top_team=top_m["team"], spoon_team=spoon_m["team"])
    greeting = pick(GREETINGS, gw, "greeting").format(gw=gw, spoon_first=spoon_m["first"])

    sections = []
    sections.append(("\U0001F3C6 The headline", pick(TOP_SCORER, gw, "top").format(
        team=top_m["team"], first=top_m["first"], pts=top["points"])))
    sections.append(("\U0001F62D The disaster", pick(WOODEN_SPOON, gw, "spoon").format(
        team=spoon_m["team"], first=spoon_m["first"], pts=spoon["points"])))
    flop_m = by_id[flop["entry_id"]]
    sections.append(("\U0001FA91 Bench flop", pick(BENCH_FLOP, gw, "flop").format(
        first=flop_m["first"], pts=flop["points"])))

    movers = []
    if week["climber"]:
        c = week["climber"]; cm = by_id[c["entry_id"]]
        movers.append(pick(CLIMBER, gw, "climber").format(
            first=cm["first"], delta=c["delta"], plural="" if c["delta"] == 1 else "s"))
    if week["faller"]:
        f = week["faller"]; fm = by_id[f["entry_id"]]
        movers.append(pick(FALLER, gw, "faller").format(
            first=fm["first"], delta=f["delta"], plural="" if f["delta"] == 1 else "s"))
    if movers:
        sections.append(("\U0001F4C9 Movers & shakers", " ".join(movers)))

    justice_lines = []
    if week["most_robbed"]:
        j = week["most_robbed"]; jm = by_id[j["entry_id"]]
        justice_lines.append(pick(JUSTICE_ROBBED, gw, "robbed").format(
            first=jm["first"], deserved_rank=j["deserved_rank"], actual_rank=j["actual_rank"],
            deserved_suffix=ordinal(j["deserved_rank"]), actual_suffix=ordinal(j["actual_rank"])))
    if week["most_blessed"]:
        j = week["most_blessed"]; jm = by_id[j["entry_id"]]
        justice_lines.append(pick(JUSTICE_BLESSED, gw, "blessed").format(first=jm["first"]))
    if not justice_lines:
        any_id = week["standings"][0]
        justice_lines.append(pick(JUSTICE_FAIR, gw, "fair").format(first=by_id[any_id]["first"]))
    sections.append(("⚖️ The Table of Justice", " ".join(justice_lines)))

    standings_rows = "".join(
        f'<tr><td style="padding:7px 8px 7px 0;border-bottom:1px solid #ddd;font-weight:700;color:#888;width:18px">{i + 1}</td>'
        f'<td style="padding:7px 8px 7px 0;border-bottom:1px solid #ddd;font-weight:600">{by_id[eid]["team"]}'
        f'<br><span style="font-size:11px;color:#888;font-weight:400">{by_id[eid]["first"]}</span></td>'
        f'<td style="padding:7px 0 7px 8px;border-bottom:1px solid #ddd;text-align:right;font-variant-numeric:tabular-nums">'
        f'{data["per_manager"][str(eid)]["total"]}</td></tr>'
        for i, eid in enumerate(week["standings"]))

    body_sections = "".join(
        f'<tr><td style="padding-bottom:18px">'
        f'<div style="font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:#888;margin-bottom:6px">{title}</div>'
        f'<div style="font-size:15px;line-height:1.55">{text}</div>'
        f'</td></tr>'
        for title, text in sections)

    signoff = pick(SIGNOFFS, gw, "signoff").format(gw=gw, spoon_first=spoon_m["first"], league=league)
    signoff_html = signoff.replace("\n", "<br>")

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:24px 12px;background:#e4ded1;font-family:Georgia,'Times New Roman',serif;color:#201c14">
<table role="presentation" width="100%" style="max-width:560px;margin:0 auto;background:#fbf8f1;border:1px solid #d9d1bd;border-radius:14px" cellpadding="0" cellspacing="0">
<tr><td style="padding:28px 24px 8px">
<div style="text-align:center;padding-bottom:18px;border-bottom:3px double #d9d1bd;margin-bottom:22px">
  <div style="font-size:11px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:#b4432a;font-family:Arial,sans-serif">
    Gameweek {gw} &middot; {league} Weekly
  </div>
  <div style="font-size:28px;font-weight:800;margin:8px 0 4px">{subject}</div>
  <div style="font-size:13px;color:#5a5346;font-style:italic">A dispatch nobody asked for, delivered every week regardless</div>
</div>
<div style="font-size:15px;margin-bottom:18px;line-height:1.55">{greeting}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{body_sections}</table>
<div style="font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:#888;margin:4px 0 8px;font-family:Arial,sans-serif">\U0001F3C1 The standings</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:13.5px;margin-bottom:20px">{standings_rows}</table>
<div style="padding-top:16px;border-top:1px solid #d9d1bd;font-size:14px;line-height:1.55">{signoff_html}</div>
</td></tr>
</table>
<div style="text-align:center;font-size:11px;color:#948c7a;padding:16px 8px 0;font-family:Arial,sans-serif">
You're getting this because you're in the league and nobody asked you first.
</div>
</body></html>"""

    text_lines = [subject, "", greeting, ""]
    for title, t in sections:
        text_lines += [title, t, ""]
    text_lines += ["STANDINGS"]
    for i, eid in enumerate(week["standings"]):
        text_lines.append(f'{i + 1}. {by_id[eid]["team"]} ({by_id[eid]["first"]}) - {data["per_manager"][str(eid)]["total"]} pts')
    text_lines += ["", signoff]
    return subject, html, "\n".join(text_lines)


def send(subject, html, text, recipients, gmail_user, gmail_password):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, recipients, msg.as_string())


def main(argv):
    dry_run = "--dry-run" in argv
    force = "--force" in argv

    if not DATA_FILE.exists():
        sys.exit(f"{DATA_FILE} doesn't exist yet - run update.py first.")
    data = json.loads(DATA_FILE.read_text())

    meta = data["meta"]
    if not meta.get("current_gw_finished"):
        print(f"Gameweek {meta['current_gw']} isn't finished yet - nothing to send.")
        return
    gw = meta["current_gw"]

    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"last_sent_gw": 0}
    if gw <= state["last_sent_gw"] and not force and not dry_run:
        print(f"Gameweek {gw} was already sent (last sent: {state['last_sent_gw']}). Nothing to do.")
        return

    week = compute_week(data, gw)
    subject, html, text = render(data, week)

    if dry_run:
        PREVIEW_FILE.write_text(html, encoding="utf-8")
        print(f"Dry run - wrote {PREVIEW_FILE} (subject: {subject!r}). Nothing sent, state not updated.")
        return

    config = json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
    if not config.get("digest_enabled"):
        print("digest_enabled is not set to true in config.json - skipping send (preview with --dry-run).")
        return

    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    recipients_raw = os.environ.get("DIGEST_RECIPIENTS", "")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    if not gmail_user or not gmail_password:
        sys.exit("GMAIL_USER and GMAIL_APP_PASSWORD must be set to send the digest.")
    if not recipients:
        sys.exit("DIGEST_RECIPIENTS must be set to a comma-separated list of email addresses.")

    send(subject, html, text, recipients, gmail_user, gmail_password)
    state["last_sent_gw"] = gw
    STATE_FILE.write_text(json.dumps(state))
    print(f"Sent gameweek {gw} digest to {len(recipients)} recipient(s): {subject!r}")


if __name__ == "__main__":
    main(sys.argv[1:])
