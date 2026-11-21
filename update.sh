#!/bin/sh
# Refresh Roger's pages and rebuild docs/data.json. Run from the repo root.
set -e
curl -fsS -m 30 -o data/rk_results.html https://rogerkillion.com/styled/styled-3/ || echo "results page unavailable, keeping last copy"
curl -fsS -m 30 -o data/rk_schedule.html https://rogerkillion.com/styled/styled-2/ || echo "schedule page unavailable, keeping last copy"
python3 -I scripts/build.py
