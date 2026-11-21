"""Pre-match preview text for the "Roger & Jerry & Murv" group chat.

Usage: python3 scripts/preview.py [YYYY-MM-DD]   (default: today, Pacific)
Prints JSON: {"status": "ok"|"no_match"|"not_scheduled"|"no_data", "text": ..., "facts": {...}}
Follows Murv's spec: schedule from Roger's site, scores from the tracker data, first names only,
no em dashes, Pro rounds out of averages, guests never count.
"""
import json, os, sys, random
from datetime import date, datetime, timezone
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build

P = ['roger', 'jerry', 'murv']; N = {'roger': 'Roger', 'jerry': 'Jerry', 'murv': 'Murv'}


def tp(n):
    return 'E' if n == 0 else (f'+{n}' if n > 0 else str(n))


def wn(v):
    return str(int(v)) if float(v).is_integer() else f'{v:.1f}'


def season_wins(ms, year):
    w = {p: 0.0 for p in P}
    for m in ms:
        if m['date'][:4] == year:
            for p, s in m['win'].items():
                w[p] += s
    return w


def main():
    d = json.load(open(os.path.join(ROOT, 'docs', 'data.json')))
    day = sys.argv[1] if len(sys.argv) > 1 else d['today']
    _, _, sched, par_by_key, pretty = build.build()
    entry = next((s for s in sched if s['date'] == day), None)
    if entry is None:
        return {'status': 'not_scheduled', 'text': None, 'facts': {'date': day}}
    import re
    if re.match(r'(?i)no match', entry['course'] or ''):
        return {'status': 'no_match', 'text': None, 'facts': {'date': day, 'reason': entry['course']}}
    key = build.norm(entry['course'])
    course = pretty.get(key) or re.sub(r'(?i)\s+new$', '', entry['course']).strip()
    par = par_by_key.get(key)
    ms = [m for m in d['matches'] if m['date'] < day]
    if not ms:
        return {'status': 'no_data', 'text': None, 'facts': {}}
    dow = date.fromisoformat(day).strftime('%A')
    tees = entry['tees'] or '?'; pins = entry['pins'] or '?'
    lines = []
    lines.append(f"Morning fellas. {dow}'s match: {course}, {tees} Tees, {pins} Pins, 8:00am PT tee time.")

    # 2) history at this course
    here = [m for m in ms if m['key'] == key]
    together = [m for m in here if all(m['players'][p]['status'] == 'played' for p in P)]
    if not here:
        lines.append(f"We've never played {course} together, so this one is a clean slate." + (" It's a new course for us." if 'new' in (entry['course'] or '').lower() else ''))
    else:
        last = here[-1]
        when = datetime.fromisoformat(last['date']).strftime('%B') + ('' if last['date'][:4] == day[:4] else f" {last['date'][:4]}")
        winners = [p for p in P if last['win'].get(p)]
        order = sorted([p for p in P if last['players'][p]['status'] == 'played'], key=lambda p: (last['players'][p]['toPar'], -last['win'].get(p, 0)))
        def sc(p):
            x = last['players'][p]
            return f"{tp(x['toPar'])} ({x['gross']})" if x.get('gross') else tp(x['toPar'])
        n = len(together)
        cnt = {1: 'once', 2: 'twice'}.get(n, f'{n} times')
        if n:
            s = f"We've played {course} {cnt} together, last in {when}."
        else:
            s = f"The three of us have never finished {course} together, but we played it in {when}."
        s += f" {' and '.join(N[p] for p in winners)} took it at {sc(winners[0])}"
        rest = [p for p in order if p not in winners]
        s += (', ' + ', '.join(f"{'I' if p == 'murv' else N[p]} {'was' if True else ''} {sc(p)}".replace('  ', ' ') for p in rest) + '.') if rest else '.'
        if last['playoff']:
            s += ' That one went to a playoff.'
        if last['tees'] and last['pins'] and (last['tees'] != tees or last['pins'] != pins):
            harder = {'Easy': 0, 'Medium': 1, 'Hard': 2}
            diff = harder.get(pins, 1) - harder.get(last['pins'], 1) + (0.5 if tees == 'Back' else 0) - (0.5 if last['tees'] == 'Back' else 0)
            feel = 'should play a little friendlier' if diff < 0 else ('should play tougher' if diff > 0 else 'plays a bit different')
            s += f" That round was {last['tees']} Tees and {last['pins']} Pins, so today {feel}."
        # notable low scores
        lows = []
        for m in here:
            if m['pro'] or m['nine']:
                continue
            for p in P:
                x = m['players'][p]
                if x['status'] == 'played':
                    lows.append((x['toPar'], m['date'], p, x.get('gross')))
        lows.sort()
        if lows and len(here) > 1 and lows[0][0] <= -4:
            t, dd, p, g = lows[0]
            s += f" Low score here is {N[p]}'s {g if g else ''} ({tp(t)}) from {datetime.fromisoformat(dd).strftime('%B %Y')}.".replace('  ', ' ').replace(' (', ' (', 1)
        lines.append(s)

    # 3) standings
    yr = day[:4]
    now_w = season_wins(ms, yr)
    lines_st = f"Standings this season: Roger {wn(now_w['roger'])}, Jerry {wn(now_w['jerry'])}, Murv {wn(now_w['murv'])}."
    # 4) movement since the match before last
    season_ms = [m for m in ms if m['date'][:4] == yr]
    move = ''
    if season_ms:
        prev_w = season_wins(season_ms[:-1], yr)
        top_now = max(now_w.values()); top_prev = max(prev_w.values())
        lead_now = {p for p in P if now_w[p] == top_now}; lead_prev = {p for p in P if prev_w[p] == top_prev}
        bits = []
        if lead_now != lead_prev and len(season_ms) > 1:
            if len(lead_now) > 1:
                bits.append(f"{' and '.join(N[p] for p in P if p in lead_now)} are now tied at the top")
            else:
                bits.append(f"{N[next(iter(lead_now))]} just took over the lead")
        else:
            for p in P:
                if p in lead_now:
                    continue
                gap_n, gap_p = top_now - now_w[p], top_prev - prev_w[p]
                if gap_n <= 1 < gap_p or (gap_n <= 1 and gap_p <= 1 and gap_n != gap_p):
                    leader = next(iter(lead_now))
                    bits.append(f"{N[p]} is just {wn(gap_n)} behind {N[leader]}, so the lead can flip today")
        # streaks of 2+
        streak = {}
        for p in P:
            c = 0
            for m in reversed(ms):
                if m['players'][p]['status'] != 'played':
                    continue
                if m['win'].get(p, 0) >= 1:
                    c += 1
                else:
                    break
            streak[p] = c
        for p in P:
            if streak[p] >= 2:
                bits.append(f"{N[p]} has won {streak[p]} straight")
        for p in P:
            if now_w[p] == 0:
                bits.append(f"{N[p]} is still chasing his first win of the season")
        if bits:
            move = ' ' + '. '.join(b[0].upper() + b[1:] for b in bits) + '.'
    lines.append(lines_st + move)

    # 5) predictions
    pr = build.predict(ms, key, par)
    def pv(p):
        x = pr.get(p)
        if not x:
            return None
        return str(x['gross']) if x['gross'] is not None else tp(x['toPar'])
    vals = [(p, pv(p)) for p in P]
    if any(v is None for _, v in vals):
        missing = [N[p] for p, v in vals if v is None]
        return {'status': 'no_data', 'text': None, 'facts': {'date': day, 'missing_predictions': missing}}
    closers = ['See you out there.', 'Fairways and greens, boys.', "Let's go.", 'Bring your A game.', 'Good luck, gentlemen.']
    random.seed(day)
    note = '' if par else ' (to par, new course so no par on file yet)'
    lines.append('Predictions: ' + ', '.join(f"{N[p]} {v}" for p, v in vals) + note + '. ' + random.choice(closers))
    text = '\n\n'.join(lines).replace('—', ',').replace('–', '-')
    return {'status': 'ok', 'text': text, 'facts': {'date': day, 'course': course, 'par': par, 'tees': tees, 'pins': pins,
            'together': len(together), 'wins': now_w, 'predictions': pr}}


if __name__ == '__main__':
    print(json.dumps(main(), indent=1))
