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
pars_path = os.path.join(ROOT, 'data', 'hole_pars.txt')
known = {tuple(l.strip().split('|')[:2]) for l in open(pars_path)} if os.path.exists(pars_path) else set()
new_pars = []
for line in open(sys.argv[1]):
    line = line.strip()
    if line.startswith('pars|'):
        p = line.split('|')
        if len(p) == 4 and len(p[3].split('.')) == 18 and (p[1], p[2]) not in known:
            new_pars.append('|'.join(p[1:])); known.add((p[1], p[2]))
        continue
    if '|' not in line or not line.split('|')[0].count('_'):
        continue
    v = line.split('|')
    player, bucket = v.pop(0).split('_')
    d = dict(zip(COLS, v)); d['player'] = player; d['bucket'] = bucket
    if player not in ('roger', 'jerry', 'murv') or len(v) < len(COLS) - 1 or (player, d['id']) in have:
        continue
    rows.append(d); have.add((player, d['id'])); new += 1
json.dump(rows, open(path, 'w'))
if new_pars:
    with open(pars_path, 'a') as f:
        f.write('\n'.join(new_pars) + '\n')
print(json.dumps({'new_rounds': new, 'new_course_pars': len(new_pars), 'total': len(rows)}))
