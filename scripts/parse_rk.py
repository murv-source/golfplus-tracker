"""Parse Roger's VR Golf Past Results page (text) into match records."""
import re, json, sys, html
MONTHS={m:i for i,m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'],1)}
DATE=re.compile(r'^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+([A-Z][a-z]+)\s+(\d{1,2})(?:,\s*(.*))?$')
RES=re.compile(r'^(T?)(\d)(?:st|nd|rd|th):\s*(.+?)\s*\(([+-]?\d+|E)\)\s*(.*)$')
COND=re.compile(r'^(Back|Middle|Front|Forward|Pro|Tips?)\s+Tees?,\s*(Easy|Medium|Hard)\s+Pins?',re.I)
def to_text(raw):
    s=re.sub(r'(?is)<(script|style).*?</\1>','',raw)
    s=re.sub(r'(?i)<br\s*/?>|</p>|</h\d>|</li>|</div>','\n',s)
    return html.unescape(re.sub(r'<[^>]+>','',s))
def parse(text):
    lines=[l.strip() for l in text.split('\n')]
    year=None; out=[]; cur=None
    for l in lines:
        if re.fullmatch(r'20\d\d',l): year=int(l); continue
        m=DATE.match(l)
        if m and year:
            cur={'date':f"{year}-{MONTHS[m.group(2)]:02d}-{int(m.group(3)):02d}",'time':m.group(4) or '','course':None,'tees':None,'pins':None,'results':[],'notes':[]}
            out.append(cur); continue
        if cur is None or not l: continue
        if cur['course'] is None: cur['course']=l; continue
        c=COND.match(l)
        if c and cur['tees'] is None: cur['tees']=c.group(1).title(); cur['pins']=c.group(2).title(); continue
        r=RES.match(l)
        if r:
            tp=0 if r.group(4)=='E' else int(r.group(4))
            cur['results'].append({'pos':int(r.group(2)),'tie':bool(r.group(1)),'name':r.group(3).strip(),'toPar':tp,'extra':r.group(5)}); continue
        if l.upper().startswith('NOTE'): cur['notes'].append(re.sub(r'^NOTE:?\s*','',l,flags=re.I)); continue
        if cur['notes']: cur['notes'][-1]+=' '+l
    return out
if __name__=='__main__':
    raw=open(sys.argv[1]).read()
    m=parse(to_text(raw) if '<html' in raw.lower() else raw)
    json.dump(m,open(sys.argv[2],'w'),indent=1)
    import collections
    print(len(m), collections.Counter(x['date'][:4] for x in m))
    bad=[x for x in m if not x['results'] and not x['notes']]; print('empty',len(bad), bad[:3])
    nocond=[x for x in m if x['tees'] is None]; print('nocond',len(nocond),[ (x['date'],x['course']) for x in nocond[:8]])
    names=collections.Counter(r['name'] for x in m for r in x['results']); print(names)
