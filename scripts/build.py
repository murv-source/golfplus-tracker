"""Golf+ Tracker data build.

Inputs (data/):
  golfplus_raw.json   rounds from the GOLF+ API (source of truth for scores)
  rk_results.html     Roger's "VR Golf Past Results" page (fills gaps, playoffs, notes, guests)
  rk_schedule.html    Roger's "VR Golf Upcoming Games" page (schedule)
  tracker_rounds.json the original hand-built tracker (Sep 2025 - Nov 2026 gross scores)
Output: site/data.json

Rules: only Roger, Jerry, Murv are tracked. Guests never count. A core player with no score
is No show (or DNF if a note says so) and cannot win. Pro-difficulty rounds stay in history but
are excluded from averages and predictions. Ties for low core score go to Roger's site order;
a listed tie (T1st) splits the win.
"""
import json, re, os, sys, difflib, collections
from datetime import datetime, timezone, timedelta, date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import parse_rk

CORE = ['roger', 'jerry', 'murv']
NAMES = {'roger': 'Roger', 'jerry': 'Jerry', 'murv': 'Murv'}
FULL = {'roger killion': 'roger', 'jerry finney': 'jerry', 'murv berry': 'murv', 'murv berrt': 'murv'}
HANDLES = {'roger': 'RogerK9', 'jerry': 'jerry1025.2022', 'murv': 'murv500'}

ALIAS = {
    'eastlake2023': 'eastlake', 'eastlake2024': 'eastlake', 'eastlakegolfcub': 'eastlake', 'eastlakegolfclub': 'eastlake',
    'lofotenlinks': 'lofoten', 'oldatstandrews': 'standrewsold', 'oldcourseatstandrews': 'standrewsold',
    'pinehurstno10': 'pinehurst10', 'pinehurstno2': 'pinehurst2', 'castlelink': 'castlelinks',
    'harbourtowngolflinks': 'harbourtown', 'jameirahearth': 'jumeirahearth', 'kapaluaplantation': 'kapalua',
    'plantationatkapalua': 'kapalua', 'kiawahocean': 'kiawah', 'oceanatkiawah': 'kiawah', 'muirfield': 'muirfieldvillage',
    'olympia': 'olympiafields', 'omnilacosta': 'omnilacostanorth', 'pebblebeachgolflinks': 'pebblebeach',
    'royalportrush': 'royalportrushdunlucelinks', 'royalportrushdunluce': 'royalportrushdunlucelinks',
    'sweetenscoveilluminati': 'sweetensilluminati', 'medinah3': 'medinah3', 'castle': 'castlelinks',
}
PRETTY = {
    'standrewsold': 'Old Course at St Andrews', 'eastlake': 'East Lake', 'lofoten': 'Lofoten Links',
    'pinehurst10': 'Pinehurst No. 10', 'pinehurst2': 'Pinehurst No. 2', 'tpcsawgrass': 'TPC Sawgrass',
    'tpcscottsdale': 'TPC Scottsdale', 'tpcsouthwind': 'TPC Southwind', 'tpcriverhighlands': 'TPC River Highlands',
    'royalportrushdunlucelinks': 'Royal Portrush Dunluce Links', 'sweetensilluminati': 'Sweetens Cove Illuminati',
    'omnilacostanorth': 'Omni La Costa North', 'tearainorth': 'Te Arai North', 'tearaisouth': 'Te Arai South',
    'kapalua': 'Kapalua Plantation', 'medinah3': 'Medinah No. 3', 'savemuny': 'Save Muny', 'bellerive': 'Bellerive', 'castlelinks': 'Castle Links',
}
PT = timezone(timedelta(hours=-8))
HP = {}  # good enough for date bucketing of 8 AM PT rounds


def norm(s):
    s = (s or '').lower()
    s = re.sub(r'\*?new course\*?|\bnew\b|golf club|country club|golf course|\bcourse\b|\bthe\b|\bclub\b|#', '', s)
    k = re.sub(r'[^a-z0-9]', '', s)
    return ALIAS.get(k, k)


def pt_date(iso):
    dt = datetime.fromisoformat(iso.replace('Z', '+00:00'))
    # PDT/PST: use -7 between 2nd Sun Mar and 1st Sun Nov, else -8
    y = dt.year
    mar = datetime(y, 3, 8, 10, tzinfo=timezone.utc); mar += timedelta(days=(6 - mar.weekday()) % 7)
    nov = datetime(y, 11, 1, 9, tzinfo=timezone.utc); nov += timedelta(days=(6 - nov.weekday()) % 7)
    off = -7 if mar <= dt < nov else -8
    return (dt + timedelta(hours=off)).date().isoformat()


def load_pars():
    out = {}
    p = os.path.join(ROOT, 'data', 'hole_pars.txt')
    if os.path.exists(p):
        for line in open(p):
            parts = line.strip().split('|')
            if len(parts) != 3:
                continue
            c, tee, pars = parts
            hp = [int(x) for x in pars.split('.') if x]
            if len(hp) == 18:
                out.setdefault((c.replace(' ', ''), tee), hp)
                out.setdefault((c.replace(' ', ''), '*'), hp)
                out.setdefault((norm(c.replace(' ', '')), '*'), hp)
    return out


def load():
    d = os.path.join(ROOT, 'data')
    gp = json.load(open(os.path.join(d, 'golfplus_raw.json')))
    rk = parse_rk.parse(parse_rk.to_text(open(os.path.join(d, 'rk_results.html')).read()))
    sched = parse_rk.parse(parse_rk.to_text(open(os.path.join(d, 'rk_schedule.html')).read()))
    tr = json.load(open(os.path.join(d, 'tracker_rounds.json')))
    return gp, rk, sched, tr


def parse_tracker(tr):
    out = []
    for r in tr:
        m = re.match(r'\w+, (\w+) (\d+), (\d{4}) · Par (\d+)', r['date'])
        d = datetime.strptime(f'{m.group(1)} {m.group(2)} {m.group(3)}', '%b %d %Y').date().isoformat()
        par = int(m.group(4))
        cond = r.get('cond') or ''
        tees = (re.search(r'(\w+) tees', cond) or [None, None])[1]
        pins = (re.search(r'(\w+) pins', cond) or [None, None])[1]
        pl = {}
        for p in r['players']:
            mm = re.match(r'(Roger|Jerry|Murv)\s+(\d+)\s*\(([^)]+)\)', p)
            if mm:
                pl[mm.group(1).lower()] = {'gross': int(mm.group(2)), 'par': par}
                continue
            mm = re.match(r'(Roger|Jerry|Murv)\s*(No show|DNF|no completed score)', p)
            if mm:
                pl[mm.group(1).lower()] = {'status': 'dnf' if mm.group(2) != 'No show' else 'noshow'}
        win = re.sub(r'^Won by ', '', r.get('win') or '').split(',')[0].strip().lower()
        out.append({'date': d, 'course': r['course'], 'key': norm(r['course']), 'par': par, 'tees': tees and tees.title(),
                    'pins': pins and pins.title(), 'pro': 'Pro' in cond or 'Pro' in r['date'], 'players': pl, 'win': win, 'cond': cond})
    return out


UIDS = {'457748': 'roger', '784296': 'jerry', '815081': 'murv'}
GROUP_INFO = {}   # (date, key) -> {'dnf': set(players), 'guests': [...], 'pos': {player: (pos, tiebreak)}}


def load_groups(gp):
    """Group rounds from GOLF+ round details: fill core rounds missing from a player's own list,
    and record DNFs, guests and official finishing positions."""
    p = os.path.join(ROOT, 'data', 'golfplus_groups.txt')
    if not os.path.exists(p):
        return []
    groups = collections.defaultdict(list)
    for line in open(p):
        v = line.rstrip('\n').split('|')
        if len(v) < 15 or v[0] != 'grp':
            continue
        _, uuid, completed, course, typ, diff, user, uid, pos, tb, holes, total, topar, tee, pin = v[:15]
        groups[uuid].append(dict(completed=completed, course=course, type=typ, bucket=diff, user=user, uid=uid, pos=pos,
                                 tb=tb, holes=holes, total=total, topar=topar, tee=tee, pin=pin))
    have = collections.defaultdict(list)
    for r in gp:
        have[(r['player'], r['course'].replace(' ', ''))].append(datetime.fromisoformat(r['completed'].replace('Z', '+00:00')))
    extra = []
    for uuid, ps in groups.items():
        core = [x for x in ps if x['uid'] in UIDS]
        if not core:
            continue
        c0 = ps[0]
        when = datetime.fromisoformat(c0['completed'].replace('Z', '+00:00'))
        d = pt_date(c0['completed']); k = norm(c0['course'].replace(' ', ''))
        info = GROUP_INFO.setdefault((d, k), {'dnf': set(), 'guests': [], 'pos': {}, 'n_core': 0})
        info['n_core'] = max(info['n_core'], len(core))
        for x in ps:
            pl = UIDS.get(x['uid'])
            if pl:
                info['pos'][pl] = (x['pos'], x['tb'])
                if not x['holes']:
                    info['dnf'].add(pl)
                    continue
                if any(abs((t - when).total_seconds()) < 5400 for t in have[(pl, x['course'].replace(' ', ''))]):
                    continue
                total = int(x['total']); tp = int(x['topar'])
                extra.append({'player': pl, 'bucket': x['bucket'], 'id': 'g-' + uuid[:8] + '-' + pl, 'course': x['course'], 'tee': x['tee'],
                              'pin': x['pin'], 'wind': '', 'green': '', 'score': str(total), 'par': str(total - tp), 'holes': x['holes'],
                              'completed': x['completed'], 'started': (when - timedelta(minutes=80)).isoformat().replace('+00:00', 'Z'),
                              'mode': 'Multiplayer', 'modeDetails': 'Round', 'type': x['type'], 'difficulty': x['bucket'], 'yds': '0',
                              'diff': '', 'inhcp': '0', 'gpid': ''})
                have[(pl, x['course'].replace(' ', ''))].append(when)
            elif x['holes'] and not any(g['name'] == x['user'] for g in info['guests']):
                info['guests'].append({'name': x['user'], 'gross': int(x['total']), 'toPar': int(x['topar'])})
    return extra


def gp_rounds(gp):
    """Per player, 18-hole rounds (two nines on the same day/course are joined)."""
    gp = list(gp) + load_groups(gp)
    by = collections.defaultdict(list)
    for r in gp:
        if r['player'] not in CORE:
            continue
        r = dict(r)
        r['date'] = pt_date(r['completed'])
        r['key'] = norm(r['course'].replace(' ', ''))
        r['score'] = int(r['score']); r['par'] = int(r['par'])
        r['holeList'] = [int(x) for x in r['holes'].split('.') if x != '']
        by[r['player']].append(r)
    out = []
    for p, rs in by.items():
        nines = collections.defaultdict(list)
        for r in rs:
            if r['type'] in ('front 9', 'back 9'):
                nines[(r['date'], r['key'], r['bucket'])].append(r)
            else:
                out.append(r)
        for k, ns in nines.items():
            f = [n for n in ns if n['type'] == 'front 9']; b = [n for n in ns if n['type'] == 'back 9']
            if f and b:
                j = dict(b[0]); j['score'] = f[0]['score'] + b[0]['score']; j['holeList'] = f[0]['holeList'] + b[0]['holeList']
                j['type'] = '18 holes'; j['id'] = f[0]['id'] + '+' + b[0]['id']; out.append(j)
    return out


def note_status(notes, name):
    t = ' '.join(notes).lower()
    if name.lower() in t and re.search(r'dnf|did not finish|didn.t finish|could not finish|couldn.t finish|battery|dropped|disconnect', t):
        return 'dnf'
    return 'noshow'


def build():
    global HP
    HP = load_pars()
    gp, rk, sched, tr = load()
    trk = parse_tracker(tr)
    gpr = gp_rounds(gp)
    par_by_key = {}
    for r in gpr:
        par_by_key.setdefault(r['key'], r['par'])
    for t in trk:
        par_by_key.setdefault(t['key'], t['par'])
    pretty = dict(PRETTY)
    matches, cancelled = [], []
    for t in trk:
        pretty.setdefault(t['key'], t['course'])

    # 1) anchors: tracker rounds and GOLF+ group rounds (2+ core players, multiplayer, same day + course)
    def dnum(d): return date.fromisoformat(d).toordinal()
    anchors = []
    for t in trk:
        anchors.append({'date': t['date'], 'key': t['key'], 'tr': t, 'gp': {}, 'rk': None})
    groups = collections.defaultdict(list)
    for r in gpr:
        groups[(r['date'], r['key'])].append(r)
    loose = []
    for (d, k), rs in sorted(groups.items()):
        byp = collections.defaultdict(list)
        for r in rs:
            byp[r['player']].append(r)
        a = next((a for a in anchors if a['key'] == k and abs(dnum(a['date']) - dnum(d)) <= 1), None)
        if a:
            for p, lst in byp.items():
                a['gp'].setdefault(p, []).extend(lst)
        elif len([p for p, lst in byp.items() if any(r['mode'] == 'Multiplayer' for r in lst)]) >= 2:
            anchors.append({'date': d, 'key': k, 'tr': None, 'gp': dict(byp), 'rk': None})
        else:
            loose.append((d, k, dict(byp)))
    # 2) attach Roger's entries: same course within 4 days (closest), else same date with one free anchor
    rk_real = []
    for m in rk:
        if m['course'] and re.match(r'(?i)no match|match cancelled', m['course']):
            m['cancel'] = True
        m['key'] = norm(m['course'])
        seen, res = set(), []
        for x in m['results']:          # entries that list two rounds: keep the first round
            if x['name'] in seen:
                break
            seen.add(x['name']); res.append(x)
        m['results'] = res
        if m['results']:
            rk_real.append(m)
    for m in sorted(rk_real, key=lambda m: m['date']):
        cands = [a for a in anchors if a['rk'] is None and a['key'] == m['key'] and abs(dnum(a['date']) - dnum(m['date'])) <= 4]
        if not cands:
            cands = [a for a in anchors if a['rk'] is None and a['date'] == m['date']]
        if cands:
            a = min(cands, key=lambda a: abs(dnum(a['date']) - dnum(m['date'])))
            a['rk'] = m
        else:
            a = {'date': m['date'], 'key': m['key'], 'tr': None, 'gp': {}, 'rk': m}
            anchors.append(a)
            # a loose GOLF+ round for a listed player on that date/course belongs here
        for (d, k, lbyp) in loose:
            if abs(dnum(d) - dnum(a['date'])) <= 1 and (k == a['key'] or d == a['date']):
                for p, r in lbyp.items():
                    names = {FULL.get(x['name'].lower()) for x in m['results']}
                    if p in names and p not in a['gp'] and not (a['tr'] and p in a['tr']['players']):
                        a['gp'][p] = r
    for m in rk:
        if not m['results'] and not any(a['date'] == m['date'] for a in anchors):
            cancelled.append({'date': m['date'], 'course': re.sub(r'(?i)^no match\s*-?\s*|^match cancelled\s*', '', m['course'] or '').strip(), 'note': ' '.join(m['notes'])})

    def start_min(r):
        t = datetime.fromisoformat(r['started'].replace('Z', '+00:00'))
        return t.hour * 60 + t.minute
    for a in sorted(anchors, key=lambda a: a['date']):
        rkm, trm = a['rk'], a['tr']
        hints = {}
        for p in CORE:
            x = next((x for x in rkm['results'] if FULL.get(x['name'].lower()) == p), None) if rkm else None
            t = trm['players'].get(p) if trm else None
            if x: hints[p] = x['toPar']
            elif t and 'gross' in t: hints[p] = t['gross'] - t['par']
        cand = a['gp']
        single = {p: lst[0] for p, lst in cand.items() if len(lst) == 1}
        ref = [start_min(r) for r in single.values()]
        ref = sum(ref) / len(ref) if ref else 15 * 60 + 60
        byp = {}
        for p, lst in cand.items():
            lst = [r for r in lst if r['mode'] == 'Multiplayer'] or lst
            byp[p] = min(lst, key=lambda r: (0 if p in hints and r['score'] - r['par'] == hints[p] else 1, abs(start_min(r) - ref)))
        d = a['date']
        key = (next(iter(byp.values()))['key'] if byp else None) or (trm and trm['key']) or a['key']
        any_gp = next(iter(byp.values()), None)
        par = (any_gp and any_gp['par']) or (trm and trm['par']) or par_by_key.get(key)
        pro = bool((any_gp and any_gp['bucket'] == 'pro') or (trm and trm['pro']))
        notes = list(rkm['notes']) if rkm else []
        nine = bool(re.search(r'(?i)only tracked the (back|front) 9|back 9 only|front 9 only|scores listed are for the (back|front) 9', ' '.join(notes)))
        players = {}
        for p in CORE:
            g = byp.get(p)
            rres = next((x for x in rkm['results'] if FULL.get(x['name'].lower()) == p), None) if rkm else None
            tp = trm['players'].get(p) if trm else None
            gi0 = GROUP_INFO.get((d, key)) or {}
            if g and p in gi0.get('dnf', ()) and g['mode'] != 'Multiplayer':
                players[p] = {'status': 'dnf'}
                notes.append(f"GOLF+ has {NAMES[p]} as a DNF in the group game; he finished the round later in single player ({g['score']}, {g['score'] - g['par']:+d}).".replace('+0', 'E'))
            elif g:
                players[p] = {'status': 'played', 'gross': g['score'], 'toPar': g['score'] - g['par'], 'holes': g['holeList'], 'src': 'golfplus'}
            elif tp and 'gross' in tp:
                players[p] = {'status': 'played', 'gross': tp['gross'], 'toPar': tp['gross'] - tp['par'], 'src': 'tracker'}
            elif rres:
                players[p] = {'status': 'played', 'gross': (par + rres['toPar']) if (par and not nine) else None, 'toPar': rres['toPar'], 'src': 'roger'}
            else:
                gi = GROUP_INFO.get((d, key)) or {}
                st = 'dnf' if p in gi.get('dnf', ()) else ((tp or {}).get('status') or note_status(notes, NAMES[p]))
                players[p] = {'status': st}
        played = [p for p in CORE if players[p]['status'] == 'played']
        if not played:
            continue
        ginfo = GROUP_INFO.get((d, key)) or {}
        guests = []
        if rkm:
            for x in rkm['results']:
                if x['name'].lower() not in FULL:
                    guests.append({'name': x['name'].split()[0], 'toPar': x['toPar'], 'gross': (par + x['toPar']) if par and not nine else None})
        if not guests:
            guests = [{'name': g['name'], 'toPar': g['toPar'], 'gross': g['gross']} for g in ginfo.get('guests', [])]
        rk_order = []
        if rkm:
            for x in rkm['results']:
                c = FULL.get(x['name'].lower())
                if c in played:
                    rk_order.append((x['pos'], x['tie'], c))
            rk_order.sort()
        only_rk = all(players[p]['src'] == 'roger' for p in played)
        share, playoff = {}, False
        if (only_rk or nine) and rk_order:
            top = [c for pos, tie, c in rk_order if pos == rk_order[0][0]]
            share = {c: round(1 / len(top), 3) for c in top}
        else:
            low = min(players[p]['toPar'] for p in played)
            tied = [p for p in played if players[p]['toPar'] == low]
            gpos = {p: ginfo['pos'][p] for p in tied if p in ginfo.get('pos', {})}
            if len(tied) == 1:
                share = {tied[0]: 1}
            elif len(gpos) == len(tied) and any(tb == 'playoff' for _, tb in gpos.values()):
                w = [p for p, (pos, tb) in gpos.items() if tb == 'playoff' and pos == '1']
                share = {w[0]: 1} if w else {c: round(1 / len(tied), 3) for c in tied}; playoff = bool(w)
                if w and rk_order:
                    rk_top = [c for pos, tie, c in rk_order if c in tied][:1]
                    if rk_top and rk_top[0] != w[0]:
                        notes.append(f"GOLF+ records {NAMES[w[0]]} winning the playoff; Roger's site lists {NAMES[rk_top[0]]} first.")
            else:
                order = [o for o in rk_order if o[2] in tied]
                if order:
                    top = [c for pos, tie, c in order if pos == order[0][0]]
                    share = {c: round(1 / len(top), 3) for c in top}; playoff = len(top) == 1
                elif trm and trm['win'] in tied:
                    share = {trm['win']: 1}; playoff = True
                else:
                    share = {c: round(1 / len(tied), 3) for c in tied}
        hp = None
        if any_gp:
            raw = any_gp['course'].replace(' ', '')
            hp = HP.get((raw, any_gp['tee'])) or HP.get((raw, '*'))
        hp = hp or HP.get((key, '*'))
        if hp and par and sum(hp) != par:
            hp = None
        m = {
            'id': f"{d}-{key}", 'date': d, 'holePars': hp, 'dow': date.fromisoformat(d).strftime('%A'),
            'key': key, 'course': pretty.get(key) or (rkm and re.sub(r'(?i)\s*\*?new course\*?|\s+new$', '', rkm['course']).strip()) or key,
            'par': par, 'tees': (any_gp and any_gp['tee'].title()) or (trm and trm['tees']) or (rkm and rkm['tees']),
            'pins': (any_gp and any_gp['pin'].title()) or (trm and trm['pins']) or (rkm and rkm['pins']),
            'wind': any_gp and any_gp['wind'], 'greens': any_gp and any_gp['green'], 'yds': (any_gp and int(any_gp['yds'] or 0)) or None,
            'pro': pro, 'nine': nine, 'players': players, 'guests': guests, 'win': share, 'playoff': playoff,
            'notes': notes, 'src': [s for s, v in (('golfplus', byp), ('roger', rkm), ('tracker', trm)) if v],
        }
        matches.append(m)
    matches.sort(key=lambda m: m['date'])
    return matches, cancelled, sched, par_by_key, pretty


# ---------------- stats ----------------
def countable(m, p):
    """Score counts toward averages/predictions."""
    pl = m['players'][p]
    return pl['status'] == 'played' and not m['pro'] and not m['nine']


def season_stats(ms):
    s = {p: {'wins': 0, 'matches': 0, 'played': 0, 'rounds': 0, 'sumToPar': 0, 'best': None, 'noshow': 0, 'dnf': 0} for p in CORE}
    h2h = {a: {b: [0, 0, 0] for b in CORE if b != a} for a in CORE}
    for m in ms:
        for p in CORE:
            pl = m['players'][p]; st = s[p]
            st['matches'] += 1
            st['wins'] += m['win'].get(p, 0)
            if pl['status'] == 'played':
                st['played'] += 1
            elif pl['status'] == 'dnf':
                st['dnf'] += 1
            else:
                st['noshow'] += 1
            if countable(m, p):
                st['rounds'] += 1; st['sumToPar'] += pl['toPar']
                if st['best'] is None or pl['toPar'] < st['best']['toPar']:
                    st['best'] = {'toPar': pl['toPar'], 'gross': pl.get('gross'), 'course': m['course'], 'date': m['date']}
        for a in CORE:
            for b in CORE:
                if a >= b:
                    continue
                pa, pb = m['players'][a], m['players'][b]
                if pa['status'] != 'played' or pb['status'] != 'played':
                    continue
                if pa['toPar'] < pb['toPar'] or (pa['toPar'] == pb['toPar'] and m['win'].get(a, 0) > m['win'].get(b, 0)):
                    h2h[a][b][0] += 1; h2h[b][a][1] += 1
                elif pb['toPar'] < pa['toPar'] or (pa['toPar'] == pb['toPar'] and m['win'].get(b, 0) > m['win'].get(a, 0)):
                    h2h[b][a][0] += 1; h2h[a][b][1] += 1
                else:
                    h2h[a][b][2] += 1; h2h[b][a][2] += 1
    for p in CORE:
        st = s[p]
        st['avg'] = round(st['sumToPar'] / st['rounds'], 2) if st['rounds'] else None
        st['wins'] = round(st['wins'], 2)
        del st['sumToPar']
    order = sorted(CORE, key=lambda p: (-s[p]['wins'], s[p]['avg'] if s[p]['avg'] is not None else 99))
    return {'matches': len(ms), 'players': s, 'h2h': h2h, 'order': order}


def streaks(ms):
    out = {}
    for p in CORE:
        cur = best = 0; best_end = None
        for m in ms:
            if m['players'][p]['status'] != 'played':
                continue
            if m['win'].get(p, 0) >= 1:
                cur += 1
                if cur > best:
                    best, best_end = cur, m['date']
            else:
                cur = 0
        out[p] = {'current': cur, 'longest': best, 'longestEnded': best_end}
    return out


def form(ms, p, n=5):
    res = []
    for m in reversed(ms):
        st = m['players'][p]['status']
        if st != 'played':
            continue
        w = m['win'].get(p, 0)
        res.append('W' if w >= 1 else ('T' if w > 0 else 'L'))
        if len(res) == n:
            break
    return res


def course_stats(ms):
    by = collections.defaultdict(list)
    for m in ms:
        by[m['key']].append(m)
    out = {}
    for k, lst in by.items():
        together = [m for m in lst if all(m['players'][p]['status'] == 'played' for p in CORE)]
        wins = {p: round(sum(m['win'].get(p, 0) for m in lst), 2) for p in CORE}
        best = {}
        avgs = {}
        for p in CORE:
            sc = [m for m in lst if countable(m, p)]
            if sc:
                b = min(sc, key=lambda m: m['players'][p]['toPar'])
                best[p] = {'toPar': b['players'][p]['toPar'], 'gross': b['players'][p].get('gross'), 'date': b['date']}
                avgs[p] = round(sum(m['players'][p]['toPar'] for m in sc) / len(sc), 2)
        out[k] = {'key': k, 'course': lst[-1]['course'], 'par': lst[-1]['par'], 'played': len(lst), 'together': len(together),
                  'last': lst[-1]['id'], 'wins': wins, 'best': best, 'avg': avgs}
    return out


def predict(ms, key, par, upto=None):
    """Murv's method: avg(course avg to par with the group, last-3 avg to par), rounded, + par."""
    hist = [m for m in ms if upto is None or m['date'] < upto]
    out = {}
    for p in CORE:
        recent = [m['players'][p]['toPar'] for m in reversed(hist) if countable(m, p)][:3]
        course = [m['players'][p]['toPar'] for m in hist if m['key'] == key and countable(m, p)]
        if not recent and not course:
            out[p] = None; continue
        r = sum(recent) / len(recent) if recent else None
        c = sum(course) / len(course) if course else None
        v = r if c is None else (c if r is None else (c + r) / 2)
        tp = int(round(v + 1e-9)) if v >= 0 else -int(round(-v + 1e-9))
        out[p] = {'toPar': tp, 'gross': (par + tp) if par else None, 'courseAvg': c and round(c, 2), 'last3': r and round(r, 2), 'nCourse': len(course), 'nRecent': len(recent)}
    return out


def aces(ms):
    out = []
    for m in ms:
        for p in CORE:
            hl = m['players'][p].get('holes') or []
            for i, s in enumerate(hl):
                if s == 1:
                    out.append({'player': p, 'hole': i + 1, 'course': m['course'], 'date': m['date']})
    return out


def schedule(sched, par_by_key, pretty, today):
    out = []
    for s in sched:
        if s['date'] < today:
            continue
        nomatch = bool(re.match(r'(?i)no match', s['course'] or ''))
        k = norm(s['course'])
        out.append({'date': s['date'], 'dow': date.fromisoformat(s['date']).strftime('%A'), 'time': '8:00am PT',
                    'course': re.sub(r'(?i)^no match\s*-\s*', '', s['course']) if nomatch else (pretty.get(k) or re.sub(r'(?i)\s+new$', '', s['course']).strip()),
                    'isNew': bool(re.search(r'(?i)\bnew\b', s['course'] or '')) and not nomatch,
                    'key': None if nomatch else k, 'par': par_by_key.get(k), 'tees': s['tees'], 'pins': s['pins'], 'noMatch': nomatch})
    return out


def main():
    matches, cancelled, sched, par_by_key, pretty = build()
    now = datetime.now(timezone.utc)
    today = pt_date(now.isoformat().replace('+00:00', 'Z'))
    years = sorted({m['date'][:4] for m in matches})
    seasons = {y: season_stats([m for m in matches if m['date'][:4] == y]) for y in years}
    seasons['all'] = season_stats(matches)
    up = schedule(sched, par_by_key, pretty, today)
    nxt = next((s for s in up if not s['noMatch']), None)
    if nxt:
        nxt['predict'] = predict(matches, nxt['key'], nxt['par'])
    for m in matches:
        m['predicted'] = None
    data = {
        'generatedAt': now.isoformat(timespec='seconds'), 'today': today,
        'players': {p: {'name': NAMES[p], 'handle': HANDLES[p]} for p in CORE},
        'seasons': seasons, 'years': years, 'streaks': streaks(matches),
        'form': {p: form(matches, p) for p in CORE}, 'courses': course_stats(matches), 'aces': aces(matches),
        'schedule': up, 'next': nxt, 'cancelled': cancelled, 'matches': matches,
    }
    os.makedirs(os.path.join(ROOT, 'docs'), exist_ok=True)
    with open(os.path.join(ROOT, 'docs', 'data.json'), 'w') as f:
        json.dump(data, f, separators=(',', ':'))
    return data


if __name__ == '__main__':
    d = main()
    y = d['years'][-1]; s = d['seasons'][y]
    print('matches', len(d['matches']), 'cancelled', len(d['cancelled']), 'years', d['years'])
    for yy in d['years'] + ['all']:
        ss = d['seasons'][yy]
        print(yy, ss['matches'], {p: (ss['players'][p]['wins'], ss['players'][p]['avg'], ss['players'][p]['rounds']) for p in CORE})
    print('next', d['next'] and (d['next']['date'], d['next']['course'], d['next']['predict']))
