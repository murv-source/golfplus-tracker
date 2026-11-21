"""Print the newest GOLF+ round id per player (the daily task only asks the browser for rounds newer than these)."""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = json.load(open(os.path.join(ROOT, 'data', 'golfplus_raw.json')))
out = {}
for r in rows:
    out[r['player']] = max(out.get(r['player'], 0), int(r['id'].split('+')[-1]))
print(json.dumps(out))
