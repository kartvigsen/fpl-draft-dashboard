"""Decide whether a scheduled workflow run should do a real update.

The workflow fires every 10 minutes; this keeps the real work to when it
matters, so the dashboard follows live matches (any day of the week)
without rebuilding all night. Prints "run=true" or "run=false" for
$GITHUB_OUTPUT, and the reason on stderr.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MATCH_WINDOW = timedelta(hours=2, minutes=30)  # kickoff to final whistle, plus time for final points
STALE_AFTER = timedelta(hours=3)               # injuries, news, waivers and free agents still change on blank days
IN_PROGRESS_CAP = timedelta(hours=6)           # an abandoned match can stay "started, not finished" for a long time
DATA_COMMITS = ("Update data", "Record digest")


def _parse(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def decide(now, fixtures, generated_at, head_time, head_subject):
    for f in fixtures:
        kickoff = _parse(f.get("kickoff_time"))
        if kickoff and kickoff <= now <= kickoff + MATCH_WINDOW:
            return True, f"a match kicked off at {kickoff:%H:%M} UTC"
        in_progress = f.get("started") and not (f.get("finished") or f.get("finished_provisional"))
        if in_progress and kickoff and now - kickoff <= IN_PROGRESS_CAP:
            return True, f"the {kickoff:%H:%M} UTC match is still in progress"
    built = _parse(generated_at)
    if built is None:
        return True, "no previous build found"
    if now - built > STALE_AFTER:
        return True, f"the data is from {built:%d %b %H:%M} UTC, more than 3 hours ago"
    if head_time and head_time > built and not head_subject.startswith(DATA_COMMITS):
        return True, "code changed since the last build"
    return False, "no match on and the data is recent"


def _load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def main(root=ROOT, now=None):
    raw = Path(root) / "data" / "raw"
    cur = (_load(raw / "game.json", {}) or {}).get("current_event")
    fixtures = list(_load(raw / "fixtures.json", []) or [])
    if cur:
        fixtures += (_load(raw / "live" / f"gw{cur}.json", {}) or {}).get("fixtures") or []
    generated_at = ((_load(Path(root) / "docs" / "data.json", {}) or {}).get("meta") or {}).get("generated_at")
    try:
        ts, subject = subprocess.run(["git", "log", "-1", "--format=%ct %s"], cwd=root, capture_output=True,
                                     text=True, check=True).stdout.strip().split(" ", 1)
        head_time = datetime.fromtimestamp(int(ts), timezone.utc)
    except (subprocess.CalledProcessError, OSError, ValueError):
        head_time, subject = None, ""
    run, reason = decide(now or datetime.now(timezone.utc), fixtures, generated_at, head_time, subject)
    print(f"run={'true' if run else 'false'}")
    print(f"{'Updating' if run else 'Skipping'}: {reason}", file=sys.stderr)


if __name__ == "__main__":
    main()
