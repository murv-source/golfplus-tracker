# Golf+ Tracker

Live tracker for Roger, Jerry and Murv's Golf+ matches (Mondays and Fridays, 8:00am PT).

- `docs/index.html`: the tracker page (served by GitHub Pages from `/docs`)
- `docs/embed.html`: compact widget for an iframe on rogerkillion.com
- `docs/data.json`: everything the pages show, rebuilt by `scripts/build.py`

## Data sources
1. GOLF+ (source of truth): `data/golfplus_raw.json`, appended daily by a Claude scheduled task that reads the three players' rounds from Murv's signed-in browser (`scripts/ingest.py`).
2. Roger's results and schedule pages (`data/rk_*.html`): older seasons, playoffs, guests, notes, the upcoming schedule.
3. The original hand-built tracker (`data/tracker_rounds.json`): gross scores Sep 2025 to Nov 2026.

## Rules
Only Roger, Jerry and Murv are tracked. Guests show in a round only. A core player with no score is No show or DNF and cannot win. Pro-difficulty rounds stay in history but are left out of averages, records and predictions. Ties go to the playoff result on Roger's site; a listed tie splits the win.

## Pre-match text
`python3 scripts/preview.py YYYY-MM-DD` prints the group-text preview for a match day.
