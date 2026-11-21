"""Merge new GOLF+ rounds into data/golfplus_raw.json.

Input: a text file with one round per line, in the format the daily task writes from the browser:
  <player>_<difficulty>|id|course|tee|pin|wind|green|score|par|holes|completedAt|startedAt|mode|modeDetails|type|difficulty|yds|differential|inHandicap|gamePlayerId
Prints how many rounds were new.
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLS = 'id course tee pin wind green score par holes completed started mode modeDetails type difficulty yds diff inhcp gpid'.split()
path = os.path.join(ROOT, 'data', 'golfplus_raw.json')
rows = json.load(open(path))
have = {(r['player'], r['id']) for r in rows}
new = 0
for line in open(sys.argv[1]):
    line = line.strip()
    if '|' not in line or not line.split('|')[0].count('_'):
        continue
    v = line.split('|')
    player, bucket = v.pop(0).split('_')
    d = dict(zip(COLS, v)); d['player'] = player; d['bucket'] = bucket
    if player not in ('roger', 'jerry', 'murv') or len(v) < len(COLS) - 1 or (player, d['id']) in have:
        continue
    rows.append(d); have.add((player, d['id'])); new += 1
json.dump(rows, open(path, 'w'))
print(json.dumps({'new_rounds': new, 'total': len(rows)}))
