# -*- coding: utf-8 -*-
"""HIZLI ON V7.2.1 · Standalone mobile Streamlit release.
Motor and interface are in this app.py to prevent mismatch between module versions.
"""
from __future__ import annotations

# ============ ANALYSIS ENGINE ============
# -*- coding: utf-8 -*-
"""Hizli On V7: resumable exact-family mining and prequential backtesting.
No future result is used for generating any prediction in validation.
"""

import os, sqlite3, json, hashlib, re, io, zipfile, math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone, date
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from math import comb
import pandas as pd

SIZES=tuple(range(5,11))
DAY_GAPS=(1,2,3,5,7,10,14,21)
SCHEMA=10

@dataclass(frozen=True)
class Draw:
    id:int
    dt:datetime
    nums:tuple
    mask:int
    pos:int
    @property
    def day(self): return self.dt.date()


def pos_time(p):
    p=int(p)
    if 1<=p<=13: m=2+5*(p-1)
    elif 14<=p<=217: m=422+5*(p-14)
    else:return ''
    return f'{m//60:02d}:{m%60:02d}'

def time_pos(dt):
    m=dt.hour*60+dt.minute
    if 2<=m<=62 and (m-2)%5==0:return 1+(m-2)//5
    if 422<=m<=1437 and (m-422)%5==0:return 14+(m-422)//5
    return None

def mask_of(nums):
    v=0
    for n in nums:v|=1<<(int(n)-1)
    return v

def mask_nums(mask):
    a=[]
    while mask:
        bit=mask & -mask
        a.append(bit.bit_length())
        mask ^= bit
    return tuple(a)

def _check(id_,dt,nums):
    if len(nums)!=20 or len(set(nums))!=20 or min(nums)<1 or max(nums)>80:return None
    p=time_pos(dt)
    if p is None or not 1<=id_<=9999999999:return None
    nums=tuple(sorted(nums))
    return Draw(id_,dt,nums,mask_of(nums),p)

def parse(text):
    """Parse both native TXT and Milli Piyango pastes; preserve conflict warnings."""
    text=text.replace('\ufeff','')
    found=[];bad=0
    for line in text.splitlines():
        if ';' not in line:continue
        a=line.strip().split(';')
        if len(a)!=3:bad+=1;continue
        try:
            r=_check(int(a[0]), datetime.strptime(a[1].strip(),'%d.%m.%Y %H:%M'),
                     [int(x) for x in re.split(r'[,\s]+',a[2].strip()) if x])
            if r: found.append(r)
            else:bad+=1
        except (ValueError,OverflowError):bad+=1
    blocks=list(re.finditer(r'(?:Çekiliş\s*no\s*:\s*#*|###\s*)(\d{5,9})',text,re.I))
    for i,x in enumerate(blocks):
        section=text[x.end(): blocks[i+1].start() if i+1<len(blocks) else len(text)]
        tm=re.search(r'(\d{2}\.\d{2}\.\d{4})\s*[- ]\s*(\d\d:\d\d)',section)
        if not tm:continue
        tail=section[tm.end():].split('Detaylar')[0].split('[Detaylar]')[0]
        try:
            ns=[int(v.strip()) for v in tail.splitlines() if re.fullmatch(r'\s*\d{1,2}\s*',v)]
            r=_check(int(x.group(1)),datetime.strptime(tm.group(1)+' '+tm.group(2),'%d.%m.%Y %H:%M'),ns)
            if r:found.append(r)
        except ValueError:continue
    slots={}; ids={}; conflicts=[]
    for r in sorted(found,key=lambda x:(x.dt,x.id)):
        prev=ids.get(r.id); byslot=slots.get((r.day,r.pos))
        if prev and prev!=r: conflicts.append('Aynı çekiliş no: '+str(r.id))
        elif byslot and byslot!=r:conflicts.append('Çelişen saat: '+str(r.dt))
        else:ids[r.id]=r;slots[(r.day,r.pos)]=r
    out=sorted(ids.values(),key=lambda x:(x.dt,x.id))
    return out,{'gecersiz':bad,'celiski':conflicts,'tekrar_sayisi':len(found)-len(out)}

def serialize(draws):return '\n'.join(f"{x.id};{x.dt:%d.%m.%Y %H:%M};{','.join(map(str,x.nums))}" for x in draws)+'\n'

def byday(draws):
    z=defaultdict(dict)
    for d in draws:z[d.day][d.pos]=d
    return dict(z)

def data_quality(draws):
    tab=[]
    for d,entries in sorted(byday(draws).items()):
        missing=sorted(set(range(1,218))-set(entries))
        tab.append({'Gün':str(d),'Çekiliş':len(entries),'Eksik slot':len(missing),'İlk saat':pos_time(min(entries)),
                    'Son saat':pos_time(max(entries)),'Eksik sıra (ilk 20)':','.join(map(str,missing[:20]))})
    return pd.DataFrame(tab)

def hash_settings(draws,options):
    h=hashlib.sha256()
    h.update(str(SCHEMA).encode());h.update(json.dumps(options,sort_keys=True).encode())
    for r in draws:
        h.update(f'{r.id},{r.dt.isoformat()},{r.mask};'.encode())
    return h.hexdigest()[:20]

def connect(path):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(p),timeout=25)
    c.execute('PRAGMA busy_timeout=25000')
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA synchronous=NORMAL')
    return c

def initialize(path,draws,holdout,per_size,topgap):
    days=sorted(byday(draws));cut_idx=max(1,len(days)-holdout)
    cut=days[cut_idx]
    c=connect(path)
    c.executescript('''
    CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY,v TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS candidates(k INTEGER,fam TEXT,n INTEGER NOT NULL,nday INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(k,fam));
    CREATE TABLE IF NOT EXISTS selected(k INTEGER,fam TEXT,src TEXT,PRIMARY KEY(k,fam));
    CREATE TABLE IF NOT EXISTS profile(k INTEGER,fam TEXT,occ INTEGER,nday INTEGER,anyday3 INTEGER,sameday3 INTEGER,crossday3 INTEGER,trainday3 INTEGER,traincross3 INTEGER,first_at TEXT,last_at TEXT,primary_gap TEXT,PRIMARY KEY(k,fam));
    CREATE TABLE IF NOT EXISTS triples(k INTEGER,fam TEXT,day TEXT,pos1 INTEGER,pos2 INTEGER,pos3 INTEGER,gap1 INTEGER,gap2 INTEGER,equal INTEGER,PRIMARY KEY(k,fam,day,pos1,pos2,pos3));
    CREATE TABLE IF NOT EXISTS rhythm(k INTEGER,fam TEXT,mode TEXT,gap INTEGER,train3 INTEGER,all3 INTEGER,PRIMARY KEY(k,fam,mode,gap));
    CREATE TABLE IF NOT EXISTS hits(k INTEGER,fam TEXT,day TEXT,pos INTEGER,id INTEGER,PRIMARY KEY(k,fam,day,pos));
    CREATE TABLE IF NOT EXISTS predictions(k INTEGER,fam TEXT,day TEXT,pos INTEGER,mode TEXT,gap INTEGER,train3 INTEGER,hit INTEGER,source_first TEXT,source_second TEXT,PRIMARY KEY(k,fam,day,pos,mode,gap));
    ''')
    if not c.execute("SELECT 1 FROM meta WHERE k='stage'").fetchone():
        c.executemany('INSERT INTO meta(k,v) VALUES (?,?)', [('stage','mine'),('mine_pos','0'),('profile_pos','0'),('cutoff',cut.isoformat()),('holdout',str(holdout)),('limit',str(per_size)),('max_gap',str(topgap))]);c.commit()
    c.close();return cut

def meta(c): return dict(c.execute('SELECT k,v FROM meta'))

def change_meta(c,**kwargs): c.executemany('INSERT OR REPLACE INTO meta(k,v) VALUES (?,?)',[(k,str(v)) for k,v in kwargs.items()])

def _subsets(shared,max_choices=12):
    nums=mask_nums(shared);n=len(nums)
    if n<5:return
    for k in SIZES:
        if k>n:break
        total=comb(n,k)
        if total<=max_choices:
            for part in combinations(nums,k):yield k,'-'.join(map(str,part))
        else:
            targets={round(i*(total-1)/(max_choices-1)) for i in range(max_choices)}
            for j,part in enumerate(combinations(nums,k)):
                if j in targets:yield k,'-'.join(map(str,part))
                if j>max(targets):break

def mine_one_day(day,days,opts):
    own=days[day];count=Counter();limit=int(opts.get('gap',18))
    for p,a in own.items():
        for g in range(1,limit+1):
            b=own.get(p+g)
            if not b or int((b.dt-a.dt).total_seconds())!=300*g:continue
            common=a.mask & b.mask
            if common.bit_count()>=5:
                count.update(_subsets(common,12))
        for daygap in DAY_GAPS:
            other=days.get(day-timedelta(days=daygap),{})
            if not other:continue
            for shift in (-24,-12,-6,-2,-1,0,1,2,6,12,24):
                b=other.get(p+shift)
                if b:
                    common=a.mask & b.mask
                    if common.bit_count()>=5:count.update(_subsets(common,8))
    return count

def choose_families(c,opts,cutoff):
    counts=0
    for k in SIZES:
        nmax=int(opts.get('per_size',160))
        names=set()
        for sql in ('ORDER BY nday DESC,n DESC,fam','ORDER BY n DESC,nday DESC,fam'):
            names.update(fam for fam,n,nday in c.execute('SELECT fam,n,nday FROM candidates WHERE k=? '+sql+' LIMIT ?',
                                               (k,nmax//2)) if n>=2)
        rows=[(k,fam,'Eğitim dönemi madenciliği') for fam in sorted(names)]
        c.executemany('INSERT OR IGNORE INTO selected(k,fam,src) VALUES (?,?,?)',rows);counts+=len(rows)
    # Historical V5/V6 seeded families are only enabled if already known BEFORE the holdout starts.
    # Never validate an October holdout using seeds discovered on Oct 9.
    if cutoff>date(2026,10,9):
        try:
            from legacy_seeds import LEGACY_SEEDS
            rows=[]
            for key in LEGACY_SEEDS:
                nums=tuple(sorted(int(v) for v in str(key).split('-')))
                if len(nums) in SIZES and len(set(nums))==len(nums):rows.append((len(nums),'-'.join(map(str,nums)),'Önceden bilinen izleme ailesi'))
            c.executemany('INSERT OR IGNORE INTO selected(k,fam,src) VALUES (?,?,?)',rows)
        except ImportError:pass
    return counts

def _family_events(hits,max_gap,train_cutoff):
    """Triples of consecutive family appearances. Two independent modes: drawing and day."""
    daily=defaultdict(list)
    for r in hits:daily[r.day].append(r)
    events=[]
    for d,h in daily.items():
        h.sort(key=lambda r:r.pos)
        bypos={x.pos:x for x in h}
        for a in h:
            for g in range(1,max_gap+1):
                b,third=bypos.get(a.pos+g),bypos.get(a.pos+2*g)
                if b and third and (b.dt-a.dt).total_seconds()==300*g and (third.dt-b.dt).total_seconds()==300*g:
                    events.append(('çekiliş',g,third.day,a,b,third))
    active=set(daily)
    for d1 in sorted(active):
        for g in DAY_GAPS:
            d2,d3=d1+timedelta(days=g),d1+timedelta(days=2*g)
            if d2 not in active or d3 not in active:continue
            a=min(daily[d1],key=lambda r:r.pos)
            b=min(daily[d2],key=lambda r:abs(r.pos-a.pos))
            third=min(daily[d3],key=lambda r:abs(r.pos-b.pos))
            events.append(('gün',g,third.day,a,b,third))
    allct=Counter((m,g) for m,g,d,a,b,z in events)
    trct=Counter((m,g) for m,g,d,a,b,z in events if d<train_cutoff)
    return daily,events,allct,trct

def profile_one(k,fam,draws,cutoff,max_gap):
    fm=mask_of(int(n) for n in fam.split('-'))
    hits=[r for r in draws if r.mask & fm==fm]
    daily,events,allct,trct=_family_events(hits,max_gap,cutoff)
    strongest=allct.most_common(1)
    rows=[]
    for mode,gap in sorted(set(allct)|set(trct)):
        rows.append((k,fam,mode,gap,int(trct[(mode,gap)]),int(allct[(mode,gap)])))
    anytriples=[]
    for d,hh in daily.items():
        for a,b,third in zip(hh,hh[1:],hh[2:]):
            g1=b.pos-a.pos;g2=third.pos-b.pos
            anytriples.append((k,fam,str(d),a.pos,b.pos,third.pos,g1,g2,int(g1==g2 and
                (b.dt-a.dt).total_seconds()==300*g1 and (third.dt-b.dt).total_seconds()==300*g2)))
    profile=(k,fam,len(hits),len(daily),len(anytriples),sum(v for (m,g),v in allct.items() if m=='çekiliş'),
             sum(v for (m,g),v in allct.items() if m=='gün'),
             sum(v for (m,g),v in trct.items() if m=='çekiliş'),
             sum(v for (m,g),v in trct.items() if m=='gün'),
             hits[0].dt.isoformat(' ') if hits else '',hits[-1].dt.isoformat(' ') if hits else '',
             f'{strongest[0][0][0]} +{strongest[0][0][1]} ×{strongest[0][1]}' if strongest else '')
    return profile,rows,hits,trct,anytriples

def exact_holdout(k,fam,hits,trct,all_days,cutoff,max_gap):
    out=[]
    md=defaultdict(dict)
    for h in hits:md[h.day][h.pos]=h
    seen=set()
    for day in sorted(d for d in md if d>=cutoff):
        same=md[day]
        for b in same.values():
            for g in range(1,max_gap+1):
                a=same.get(b.pos-g);pos=b.pos+g
                if not a or pos>217 or trct.get(('çekiliş',g),0)<2:continue
                if (b.dt-a.dt).total_seconds()!=300*g or not _same_session(b.pos,pos):continue
                key=(day,pos,'çekiliş',g)
                if key in seen:continue
                seen.add(key)
                result=all_days.get(day,{}).get(pos)
                if not result:continue
                fm=mask_of(int(z) for z in fam.split('-'))
                out.append((k,fam,str(day),pos,'çekiliş',g,int(trct[('çekiliş',g)]),
                            int((result.mask & fm).bit_count()),str(a.id),str(b.id)))
    for day in sorted(d for d in all_days if d>=cutoff):
        for g in DAY_GAPS:
            d1,d2=day-timedelta(days=2*g),day-timedelta(days=g)
            if d1 not in md or d2 not in md or trct.get(('gün',g),0)<2:continue
            a=min(md[d1].values(),key=lambda r:r.pos)
            b=min(md[d2].values(),key=lambda r:abs(r.pos-a.pos))
            pos=b.pos
            result=all_days[day].get(pos)
            if not result:continue
            key=(day,pos,'gün',g)
            if key in seen:continue
            seen.add(key)
            fm=mask_of(int(z) for z in fam.split('-'))
            out.append((k,fam,str(day),pos,'gün',g,int(trct[('gün',g)]),
                        int((result.mask & fm).bit_count()),str(a.id),str(b.id)))
    return out

def _same_session(p,q):return (p<=13 and q<=13) or (p>=14 and q>=14)

def step_job(path,draws,opts,batch=2):
    c=connect(path);m=meta(c);stage=m.get('stage','mine')
    days=byday(draws);ordered=sorted(days);cutoff=date.fromisoformat(m['cutoff']);train=[d for d in ordered if d<cutoff]
    if stage=='mine':
        idx=int(m['mine_pos']);n=min(int(batch),max(0,len(train)-idx))
        for d in train[idx:idx+n]:
            cnt=mine_one_day(d,days,opts)
            c.executemany('INSERT INTO candidates(k,fam,n,nday) VALUES(?,?,?,1) ON CONFLICT(k,fam) DO UPDATE SET n=n+excluded.n,nday=nday+1',
                          [(k,fam,min(nn,10)) for (k,fam),nn in cnt.items()])
        idx+=n
        change_meta(c,mine_pos=idx)
        if idx>=len(train):
            choose_families(c,opts,cutoff)
            change_meta(c,stage='profile')
    elif stage=='profile':
        idx=int(m['profile_pos'])
        allsel=list(c.execute('SELECT k,fam FROM selected ORDER BY k,fam LIMIT ? OFFSET ?',
                              (int(batch)*8,idx)))
        for k,fam in allsel:
            profile,rhythms,hits,trct,triples=profile_one(k,fam,draws,cutoff,int(opts['gap']))
            c.execute('INSERT OR REPLACE INTO profile VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',profile)
            c.executemany('INSERT OR REPLACE INTO rhythm VALUES (?,?,?,?,?,?)',rhythms)
            c.executemany('INSERT OR REPLACE INTO triples VALUES (?,?,?,?,?,?,?,?,?)',triples)
            c.executemany('INSERT OR REPLACE INTO hits VALUES (?,?,?,?,?)',
                          [(k,fam,str(h.day),h.pos,h.id) for h in hits])
            predictions=exact_holdout(k,fam,hits,trct,days,cutoff,int(opts['gap']))
            c.executemany('INSERT OR REPLACE INTO predictions VALUES (?,?,?,?,?,?,?,?,?,?)',predictions)
        idx+=len(allsel);change_meta(c,profile_pos=idx)
        if len(allsel)<int(batch)*8:change_meta(c,stage='ready')
    c.commit()
    m2=meta(c)
    nc=c.execute('SELECT count(*) FROM candidates').fetchone()[0]
    nf=c.execute('SELECT count(*) FROM selected').fetchone()[0]
    c.close()
    return {**m2,'train_days':len(train),'candidate_count':nc,'selected_count':nf}

def status(path):
    if not Path(path).exists():return {'stage':'none'}
    c=connect(path);m=meta(c)
    m['selected_count']=c.execute('SELECT count(*) FROM selected').fetchone()[0]
    m['profile_count']=c.execute('SELECT count(*) FROM profile').fetchone()[0]
    m['candidate_count']=c.execute('SELECT count(*) FROM candidates').fetchone()[0]
    c.close();return m

def to_frame(path,table):
    c=connect(path)
    try:return pd.read_sql_query('SELECT * FROM '+table,c)
    finally:c.close()

def live_exact(draws,path,target,as_of,horizon=12):
    """Output only forecast positions strictly AFTER target-date last known slot."""
    days=byday(draws)
    subset=[r for r in draws if r.day<target or (r.day==target and r.pos<=as_of)]
    c=connect(path)
    rows=[]
    latest=byday(subset);maxgap=int(meta(c).get('max_gap','18'))
    for k,fam in c.execute('SELECT k,fam FROM selected'):
        rhythm={(mode,g):n for mode,g,n in c.execute('SELECT mode,gap,train3 FROM rhythm WHERE k=? AND fam=? AND train3>=2',(k,fam))}
        if not rhythm:continue
        fm=mask_of(int(z) for z in fam.split('-'))
        events=[r for r in subset if r.mask & fm==fm]
        today={r.pos:r for r in events if r.day==target}
        for b in today.values():
            for gap in range(1,maxgap+1):
                a=today.get(b.pos-gap);future=b.pos+gap
                if (a and ('çekiliş',gap) in rhythm and b.pos<=as_of and
                    as_of<future<=min(217,as_of+horizon) and _same_session(b.pos,future)
                    and (b.dt-a.dt).total_seconds()==300*gap):
                    rows.append((k,fam,str(target),pos_time(future),future,'Gün içi',gap,
                                 rhythm[('çekiliş',gap)],str(a.id),str(b.id)))
        prior=defaultdict(list)
        for r in events:
            if r.day<target:prior[r.day].append(r)
        for mode,g in rhythm:
            if mode!='gün':continue
            d1,d2=target-timedelta(days=2*g),target-timedelta(days=g)
            if d1 not in prior or d2 not in prior:continue
            aa=min(prior[d1],key=lambda r:r.pos)
            bb=min(prior[d2],key=lambda r:abs(r.pos-aa.pos))
            if as_of<bb.pos<=min(217,as_of+horizon):
                rows.append((k,fam,str(target),pos_time(bb.pos),bb.pos,'Günler arası',g,
                             rhythm[('gün',g)],str(aa.id),str(bb.id)))
    c.close()
    columns=['Boyut','Aile','Hedef gün','Hedef saat','Hedef sıra','Mekanizma','Gap','Eğitim üçlüsü','1. çekiliş','2. çekiliş']
    return pd.DataFrame(rows,columns=columns).drop_duplicates(['Boyut','Aile','Hedef gün','Hedef sıra','Mekanizma','Gap']).sort_values(['Eğitim üçlüsü','Boyut'],ascending=[False,True]) if rows else pd.DataFrame(columns=columns)

def prob_overlap(k):
    denom=comb(80,20)
    return sum(comb(20,i)*comb(60,20-i) for i in range(k,21))/denom

def exact_chance(k):return comb(20,k)/comb(80,k)

def wilson_lower(success,n,z=1.96):
    if not n:return 0
    p=success/n;t=z*z
    return (p+t/(2*n)-z*math.sqrt((p*(1-p)+t/(4*n))/n))/(1+t/n)

def structure_statistics(draws,cutoff,max_gap=18):
    """Counts structural 1->2->3. This is different from identical-number families.
    Input pair (a,b) exists before target c; c is only used for scoring afterward.
    """
    mp=byday(draws)
    train=defaultdict(lambda:[0,0,0,0]);test=defaultdict(lambda:[0,0,0,0])
    for d,day in sorted(mp.items()):
        for p,a in day.items():
            for gap in range(1,max_gap+1):
                b,c=day.get(p+gap),day.get(p+2*gap)
                if b is None or c is None or not _same_session(p,c.pos):continue
                if int((b.dt-a.dt).total_seconds())!=300*gap or int((c.dt-b.dt).total_seconds())!=300*gap:continue
                common=a.mask&b.mask
                shared=common.bit_count()
                bc=(b.mask&c.mask).bit_count()
                common_nums=mask_nums(common)
                for k in SIZES:
                    if shared<k:break
                    for band in (-1,c.dt.hour//4):
                        key=('çekiliş',gap,band,k)
                        dst=train if d<cutoff else test
                        dst[key][0]+=1;dst[key][1]+=int(bc>=k)
                        ticket=mask_of(common_nums[:k]);h=(c.mask&ticket).bit_count()
                        dst[key][2]+=h;dst[key][3]+=int(h==k)
        # same canonical position on three dates
        for gap in DAY_GAPS:
            mid=mp.get(d+timedelta(days=gap));last=mp.get(d+timedelta(days=2*gap))
            if not mid or not last:continue
            for p,a in day.items():
                b=mid.get(p);c=last.get(p)
                if not b or not c:continue
                common=a.mask&b.mask
                shared=common.bit_count();bc=(b.mask&c.mask).bit_count();common_nums=mask_nums(common)
                for k in SIZES:
                    if shared<k:break
                    for band in (-1,c.dt.hour//4):
                        key=('gün',gap,band,k)
                        dst=train if c.day<cutoff else test
                        dst[key][0]+=1;dst[key][1]+=int(bc>=k)
                        ticket=mask_of(common_nums[:k]);h=(c.mask&ticket).bit_count()
                        dst[key][2]+=h;dst[key][3]+=int(h==k)
    rows=[]
    for key in sorted(set(train)|set(test)):
        mode,gap,band,k=key
        n,s,nh,nfull=train[key];nt,st,th,tfull=test[key]
        baseline=prob_overlap(k)
        rows.append({'Mekanizma':mode,'Gap':gap,'Saat bandı':'Tüm gün' if band==-1 else f'{4*band:02d}–{min(23,4*band+3):02d}',
                     'Boyut':k,'Eğitim olay':n,'Eğitim 3. devam':s,'Eğitim oran':round(s/n,4) if n else 0,
                     'Eğitim alt sınır':round(wilson_lower(s,n),4),'Kör test olay':nt,
                     'Kör test 3. devam':st,'Kör test oran':round(st/nt,4) if nt else None,
                     'Rastgele baz':round(baseline,4),'Kör kupon ort.':round(th/nt,3) if nt else None,'Kör tam kupon':tfull,
                     'Rastgele kupon ort.':k/4,'Test baz üstü':bool(nt>=25 and wilson_lower(st,nt)>baseline and n>=40 and wilson_lower(s,n)>baseline)})
    return pd.DataFrame(rows)

def performance(pred):
    rows=[]
    for k in SIZES:
        part=pred[pred['k']==k] if not pred.empty else pd.DataFrame()
        n=len(part);hits=list(part['hit']) if n else []
        row={'Boyut':k,'Önceden hedeflenen':n,'3. tam isabet':sum(x==k for x in hits),
             'Ortalama isabet':round(sum(hits)/n,3) if n else 0,'Rastgele ortalama':k/4,
             'Maksimum':max(hits) if hits else 0}
        row.update({f'{h}/{k}':sum(v==h for v in hits) for h in range(k+1)})
        rows.append(row)
    return pd.DataFrame(rows)

def bundle_reports(tables,notes):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,df in tables.items():
            if isinstance(df,pd.DataFrame):z.writestr(name,df.to_csv(index=False).encode('utf-8-sig'))
        z.writestr('99_METODOLOJI.txt',notes.encode('utf-8'))
    return b.getvalue()


def verify_structural(df):
    """Conservative Bonferroni screen of test cases; correlated events remain exploratory."""
    if df.empty:return df
    from scipy.stats import binomtest
    df=df.copy()
    eligible=(df['Eğitim olay']>=40)&(df['Kör test olay']>=25)&(df['Eğitim alt sınır']>df['Rastgele baz'])
    ntests=max(1,int(eligible.sum()))
    df['Tek yön p']=1.0
    for i in df.index[eligible]:
        r=df.loc[i]
        p=prob_overlap(int(r['Boyut']))
        df.at[i,'Tek yön p']=float(binomtest(int(r['Kör test 3. devam']),int(r['Kör test olay']),p,alternative='greater').pvalue)
    df['Düzeltilmiş p']=(df['Tek yön p']*ntests).clip(upper=1.0)
    df['Doğrulama']=eligible & (df['Düzeltilmiş p']<0.05) & (df['Kör kupon ort.']>df['Rastgele kupon ort.'])
    return df.sort_values(['Doğrulama','Düzeltilmiş p','Kör test olay'],ascending=[False,True,False]).reset_index(drop=True)


def structural_live(draws,target,as_of,verified,max_gap=18,horizon=12):
    """Approved structural windows only; tickets depend solely on a and b.
    Requires at least one holdout-validated rule and only known previous draws.
    """
    if verified is None or verified.empty or 'Doğrulama' not in verified.columns:return pd.DataFrame()
    rules=verified[verified['Doğrulama']]
    if rules.empty:return pd.DataFrame()
    usable={(r['Mekanizma'],int(r['Gap']),str(r['Saat bandı']),int(r['Boyut'])):r for _,r in rules.iterrows()}
    dp=byday([r for r in draws if r.day<target or (r.day==target and r.pos<=as_of)])
    today=dp.get(target,{})
    forecasts=[];quota=Counter()
    for p in range(as_of+1,min(217,as_of+horizon)+1):
        clock=pos_time(p);hour=int(clock[:2]);band=f'{4*(hour//4):02d}–{min(23,4*(hour//4)+3):02d}'
        for g in range(1,max_gap+1):
            a,b=today.get(p-2*g),today.get(p-g)
            if not a or not b or not _same_session(a.pos,p) or int((b.dt-a.dt).total_seconds())!=300*g:continue
            common=mask_nums(a.mask&b.mask)
            for k in SIZES:
                if len(common)<k:break
                matched=usable.get(('çekiliş',g,band,k))
                if matched is None:matched=usable.get(('çekiliş',g,'Tüm gün',k))
                if matched is None or quota[(hour,k)]>=2:continue
                ticket='-'.join(map(str,common[:k]))
                forecasts.append({'Boyut':k,'Kupon':ticket,'Tarih':str(target),'Saat':clock,'Sıra':p,
                                  'Mekanizma':'Rakam değişimli','Gap':g,'Önceki 1':a.id,'Önceki 2':b.id,
                                  'Kör test olay':int(matched['Kör test olay']),'Kör test oran':matched['Kör test oran'],
                                  'Kupon türü':'Doğrulama filtresini geçti; garanti değil'})
                quota[(hour,k)]+=1
        # Across calendar days, match the same canonical draw position.
        for g in DAY_GAPS:
            a=dp.get(target-timedelta(days=2*g),{}).get(p)
            b=dp.get(target-timedelta(days=g),{}).get(p)
            if not a or not b:continue
            common=mask_nums(a.mask & b.mask)
            for k in SIZES:
                if len(common)<k:break
                matched=usable.get(('gün',g,band,k))
                if matched is None:matched=usable.get(('gün',g,'Tüm gün',k))
                if matched is None or quota[(hour,k)]>=2:continue
                forecasts.append({'Boyut':k,'Kupon':'-'.join(map(str,common[:k])),
                                  'Tarih':str(target),'Saat':clock,'Sıra':p,'Mekanizma':'Günler arası rakam değişimli',
                                  'Gap':g,'Önceki 1':a.id,'Önceki 2':b.id,
                                  'Kör test olay':int(matched['Kör test olay']),'Kör test oran':matched['Kör test oran'],
                                  'Kupon türü':'Doğrulama filtresini geçti; garanti değil'})
                quota[(hour,k)]+=1
    return pd.DataFrame(forecasts)


# ====== V7.2 TAM VERI CAPRAZ GUN UCUNCU GORUNUS MOTORU ======
"""V7.2: reproducible cross-day exact 1->2->3 rhythm scan.
All triple events are inferred from the three draw outcomes. Predictions use
only other days that ended before the target day; no selected-family leakage.
"""
from collections import defaultdict, Counter
from datetime import date
from itertools import combinations, islice
from math import comb
import json, sqlite3
from pathlib import Path
import pandas as pd

V72_SIZES=(6,7,8,9,10)
V72_SCHEMA=3

def _v72_session(a,b):
    return (a<=13 and b<=13) or (a>=14 and b<=217)

def _v72_family(mask,k):
    nums=[]
    while mask:
        bit=mask & -mask
        nums.append(bit.bit_length());mask^=bit
    return ('-'.join(map(str,v)) for v in combinations(nums,k))

def v72_conn(path):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(path),timeout=25)
    c.execute('PRAGMA busy_timeout=25000')
    c.execute('PRAGMA journal_mode=WAL')
    return c

def v72_init(path,draws,cutoff,max_gap):
    c=v72_conn(path)
    c.executescript('''
    CREATE TABLE IF NOT EXISTS v72_meta(k TEXT PRIMARY KEY, v TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS v72_triples(
       k INTEGER,fam TEXT,day TEXT,gap INTEGER,p1 INTEGER,p2 INTEGER,p3 INTEGER,
       id1 INTEGER,id2 INTEGER,id3 INTEGER,
       PRIMARY KEY (k,fam,day,gap,p1,p2,p3));
    CREATE INDEX IF NOT EXISTS v72_lookup ON v72_triples(day,k,gap);
    CREATE TABLE IF NOT EXISTS v72_blind(
       k INTEGER,fam TEXT,day TEXT,gap INTEGER,p1 INTEGER,p2 INTEGER,p3 INTEGER,
       past_days INTEGER, hit INTEGER, id1 INTEGER,id2 INTEGER,
       PRIMARY KEY (k,fam,day,gap,p1,p2,p3));
    ''')
    state=dict(c.execute('SELECT k,v FROM v72_meta'))
    if not state:
        vals={'schema':str(V72_SCHEMA),'stage':'scan','scan_at':'0','test_at':'0',
              'cutoff':cutoff.isoformat(),'max_gap':str(max_gap),'limited_events':'0'}
        c.executemany('INSERT INTO v72_meta(k,v) VALUES (?,?)',vals.items())
    elif (state.get('schema')!=str(V72_SCHEMA) or state.get('cutoff')!=cutoff.isoformat() or state.get('max_gap')!=str(max_gap)):
        raise ValueError('Eski V7.2 veritabanı başka ayarlara ait. Yeni anahtar kullanılmalı.')
    c.commit();c.close()

def v72_state(path):
    c=v72_conn(path)
    try:
        st=dict(c.execute('SELECT k,v FROM v72_meta'))
        st['triple_count']=c.execute('SELECT COUNT(*) FROM v72_triples').fetchone()[0]
        st['pred_count']=c.execute('SELECT COUNT(*) FROM v72_blind').fetchone()[0]
        return st
    finally:c.close()

def _v72_events(daymap,d,max_gap,max_families_per_triplet=120):
    out=[];capped=0
    for p,a in daymap.items():
        for g in range(1,max_gap+1):
            p3=p+2*g
            if p3>217 or not _v72_session(p,p3):continue
            b,c=daymap.get(p+g),daymap.get(p3)
            if b is None or c is None:continue
            # pos slots imply exact 5-min spacing within one session
            shared=a.mask & b.mask & c.mask
            n=shared.bit_count()
            if n<6:continue
            for k in V72_SIZES:
                if k>n:break
                total=comb(n,k)
                if total>max_families_per_triplet:capped+=total-max_families_per_triplet
                for fam in islice(_v72_family(shared,k),max_families_per_triplet):
                    out.append((k,fam,str(d),g,p,p+g,p3,a.id,b.id,c.id))
    return out,capped

def _v72_predictions(daymap,d,max_gap,rule_dict):
    """Predict after draw p+gap, before reading p+2*gap; score later."""
    out=[]
    for p,a in daymap.items():
        for g in range(1,max_gap+1):
            p2,p3=p+g,p+2*g
            if p3>217 or not _v72_session(p,p3):continue
            b,c=daymap.get(p2),daymap.get(p3)
            if b is None or c is None:continue  # incomplete slots not scored
            pair=a.mask & b.mask
            if pair.bit_count()<6:continue
            for k in V72_SIZES:
                if pair.bit_count()<k:break
                for fm,mask,nprior in rule_dict.get((k,g),[]):
                    if (pair&mask)==mask:
                        out.append((k,fm,str(d),g,p,p2,p3,nprior,(c.mask&mask).bit_count(),a.id,b.id))
    return out

def v72_step(path,draws,max_gap,batch=2):
    """Each batch completes in one transaction; restart is idempotent."""
    days=byday(draws);all_dates=sorted(days)
    c=v72_conn(path)
    try:
        st=dict(c.execute('SELECT k,v FROM v72_meta'))
        stage=st.get('stage','scan');num=max(1,int(batch))
        if stage=='scan':
            start=int(st['scan_at']);added=0;capped=0
            for i in range(start,min(len(all_dates),start+num)):
                dt=all_dates[i]
                triples,ignored=_v72_events(days[dt],dt,max_gap)
                c.executemany('INSERT OR IGNORE INTO v72_triples VALUES (?,?,?,?,?,?,?,?,?,?)',triples)
                added+=len(triples);capped+=ignored
                c.execute("UPDATE v72_meta SET v=? WHERE k='scan_at'",(str(i+1),))
                c.execute('UPDATE v72_meta SET v=CAST(v AS INTEGER)+? WHERE k=?',(ignored,'limited_events'))
                c.commit()
            if start+num>=len(all_dates):
                c.execute("UPDATE v72_meta SET v='test' WHERE k='stage'");c.commit()
        elif stage=='test':
            cutoff=date.fromisoformat(st['cutoff'])
            held=[d for d in all_dates if d>=cutoff]
            start=int(st['test_at'])
            for i in range(start,min(len(held),start+num)):
                dt=held[i]
                q='SELECT k,fam,gap,COUNT(DISTINCT day) FROM v72_triples WHERE day<? GROUP BY k,fam,gap'
                rule_dict=defaultdict(list)
                for k,fam,gap,n in c.execute(q,(str(dt),)):
                    rule_dict[(k,gap)].append((fam,mask_of(map(int,fam.split('-'))),n))
                predictions=_v72_predictions(days[dt],dt,max_gap,rule_dict)
                c.executemany('INSERT OR IGNORE INTO v72_blind VALUES (?,?,?,?,?,?,?,?,?,?,?)',predictions)
                c.execute("UPDATE v72_meta SET v=? WHERE k='test_at'",(str(i+1),))
                c.commit()
            if start+num>=len(held):
                c.execute("UPDATE v72_meta SET v='ready' WHERE k='stage'");c.commit()
        return v72_state(path)
    finally:c.close()

def v72_reports(path):
    c=v72_conn(path)
    try:
        triples=pd.read_sql_query('SELECT * FROM v72_triples ORDER BY day,k,gap,p1',c)
        blind=pd.read_sql_query('SELECT * FROM v72_blind ORDER BY day,k,p3',c)
    finally:c.close()
    cols=['k','fam','gap','days','examples','dates','last_day']
    if triples.empty:
        repeated=pd.DataFrame(columns=cols)
        changed=pd.DataFrame(columns=['k','gap','days','families','events'])
    else:
        repeated=triples.groupby(['k','fam','gap']).agg(
            days=('day','nunique'),examples=('p1','size'),
            dates=('day',lambda s:', '.join(sorted(set(s)))),
            last_day=('day','max')).reset_index().sort_values(['days','examples','k'],ascending=[False,False,True])
        changed=triples.groupby(['k','gap']).agg(
            days=('day','nunique'),families=('fam','nunique'),events=('p1','size')).reset_index().sort_values(['days','events'],ascending=False)
    summaries=[]
    for k in V72_SIZES:
        t=triples[triples.k==k];b=blind[blind.k==k]
        rep=repeated[(repeated.k==k)&(repeated.days>=2)]
        row={'Boyut':k,'Tam üçlü olay':len(t),'Üçlü yapan aile':t.fam.nunique() if len(t) else 0,
             'Aynı aile+gap ≥2 ayrı gün':len(rep),
             'Kör hedef (önceden 1 gün)':len(b),
             'Kör tam isabet':int((b.hit==k).sum()) if len(b) else 0,
             'Kör maksimum':int(b.hit.max()) if len(b) else 0,
             'Kör ortalama':round(float(b.hit.mean()),3) if len(b) else None,
             'Rastgele ortalama':k/4,
             'Güçlü geçmiş (≥2 gün) kör hedef':int((b.past_days>=2).sum()) if len(b) else 0}
        row.update({f'{i}/{k}':int((b.hit==i).sum()) if len(b) else 0 for i in range(k+1)})
        summaries.append(row)
    return {'ozet':pd.DataFrame(summaries),'tum_ucluler':triples,
            'tekrarlayan_aile_gap':repeated,'degisen_aile_yapisi':changed,'kor_test':blind}

def v72_live(path,draws,target,as_of,max_gap,horizon=12,need_days=2):
    c=v72_conn(path)
    try:
        rows=c.execute('SELECT k,fam,gap,COUNT(DISTINCT day) FROM v72_triples WHERE day<? GROUP BY k,fam,gap HAVING COUNT(DISTINCT day)>=?',(str(target),int(need_days))).fetchall()
    finally:c.close()
    pool=byday([x for x in draws if x.day==target and x.pos<=as_of]).get(target,{})
    grouped=defaultdict(list)
    for k,fam,g,n in rows:
        grouped[(k,g)].append((fam,mask_of(map(int,fam.split('-'))),n))
    out=[]
    for bpos,b in pool.items():
        for g in range(1,max_gap+1):
            a=pool.get(bpos-g)
            p3=bpos+g
            if not a or not(as_of<p3<=min(217,as_of+horizon)) or not _v72_session(a.pos,p3):continue
            shared=a.mask&b.mask
            if shared.bit_count()<6:continue
            for k in V72_SIZES:
                if shared.bit_count()<k:break
                for fam,m,ndays in grouped.get((k,g),[]):
                    if shared&m==m:
                        out.append({'Boyut':k,'Aile':fam,'Gap':g,'Hedef gün':str(target),'Hedef sıra':p3,
                                    'Hedef saat':pos_time(p3),'Geçmiş üçlü gün':ndays,
                                    '1. çekiliş':a.id,'2. çekiliş':b.id,'Etiket':'ARAŞTIRMA / garanti değil'})
    return pd.DataFrame(out).drop_duplicates() if out else pd.DataFrame(columns=['Boyut','Aile','Gap','Hedef gün','Hedef sıra','Hedef saat','Geçmiş üçlü gün','1. çekiliş','2. çekiliş','Etiket'])

def v72_changed_family_test(draws,cutoff,max_gap=36,top_gap=3,max_daily_per_size=4):
    """Train gap/time rhythm without using holdout; prospectively score deterministic
    k-number coupons made from first two draws. Numbers may change each event.
    Results are exploratory; they are NOT proof of predictability.
    """
    import math
    days=byday(draws)
    counts=defaultdict(lambda:[0,0,0])
    for d,drawset in sorted(days.items()):
        if d>=cutoff:continue
        for p,a in drawset.items():
            for g in range(1,max_gap+1):
                p3=p+2*g
                if p3>217 or not _v72_session(p,p3):continue
                b,c=drawset.get(p+g),drawset.get(p3)
                if b is None or c is None:continue
                pair=a.mask&b.mask
                n=pair.bit_count()
                if n<6:continue
                common=mask_nums(pair)
                for k in V72_SIZES:
                    if n<k:break
                    ticket=0
                    for v in common[:k]:ticket|=1<<(v-1)
                    hit=(ticket&c.mask).bit_count()
                    agg=counts[(k,g)];agg[0]+=1;agg[1]+=hit;agg[2]+=int(hit==k)
    summary=[];candidates=defaultdict(list)
    for (k,g),(n,h,full) in sorted(counts.items()):
        baseline=k/4
        mean=h/n
        # Hypergeometric variance of k fixed ticket numbers drawn out of 80 with 20 winners.
        var=k*0.25*0.75*(80-k)/79
        z=(mean-baseline)/math.sqrt(var/n)
        selected=n>=60 and mean>baseline+0.08 and z>=1.5
        row={'Boyut':k,'Gap':g,'Eğitim çift':n,'Eğitim ort.':round(mean,4),
             'Rastgele ort.':baseline,'Eğitim z':round(z,3),'Eğitim tam':full,
             'Deneme filtresi':selected}
        summary.append(row)
        if selected:candidates[k].append((z,g))
    chosen={k:set(g for z,g in sorted(candidates[k],reverse=True)[:top_gap]) for k in V72_SIZES}
    targets=[]
    for d,drawset in sorted(days.items()):
        if d<cutoff:continue
        used=Counter()
        for p3 in sorted(drawset):
            for k in V72_SIZES:
                if used[k]>=max_daily_per_size:continue
                for g in sorted(chosen[k]):
                    p1,p2=p3-2*g,p3-g
                    if p1<1 or not _v72_session(p1,p3):continue
                    a,b,c=drawset.get(p1),drawset.get(p2),drawset.get(p3)
                    if a is None or b is None or c is None:continue
                    shared=a.mask&b.mask
                    if shared.bit_count()<k:continue
                    nums=mask_nums(shared)[:k]
                    ticket=sum(1<<(n-1) for n in nums)
                    targets.append({'Boyut':k,'Tarih':str(d),'Gap':g,'1. sıra':p1,'2. sıra':p2,
                                    'Önceden hedeflenen 3. sıra':p3,'Önceki çekilişler':f'{a.id},{b.id}',
                                    'Kupon':'-'.join(map(str,nums)),'İsabet':(ticket&c.mask).bit_count(),
                                    'Durum':'DENEYSEL — %100 garantisi yok'})
                    used[k]+=1
                    break
    return pd.DataFrame(summary),pd.DataFrame(targets),chosen


# ============ STREAMLIT UI ============
from datetime import datetime,timedelta,timezone,date
from pathlib import Path
import io,zipfile,shutil,sqlite3,json
import pandas as pd
import requests
import streamlit as st
st.set_page_config(page_title='Hızlı On V7.2 | Mobil Ritim',page_icon='🎯',layout='wide',initial_sidebar_state='collapsed')
st.markdown("""<style>
@media (max-width: 700px) {
 .block-container {padding-top:0.9rem !important;padding-left:0.8rem !important;padding-right:0.8rem !important;}
 h1 {font-size:1.55rem !important;line-height:1.2 !important;}
 h2 {font-size:1.3rem !important;}
 [data-testid="stMetricValue"] {font-size:1.25rem !important;}
 [data-testid="stHorizontalBlock"] {gap:0.4rem !important;}
}
</style>""", unsafe_allow_html=True)
st.title('🎯 Hızlı On V7.2')
st.caption("5–10’lu aileler · gün ve saat ritimleri · 1→2→3 görünüş · kör isabet testi")
st.caption('Geçmiş ritim, gelecekte %100 isabet garantisi değildir. Onaylanmayan sinyaller kupon sayılmaz.')
RAW='https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt'
TR_NOW=(datetime.now(timezone.utc)+timedelta(hours=3)).date()
WORKDIR=Path('.hizli_on_v7_jobs')

@st.cache_data(ttl=90,show_spinner=False)
def fetch_url(url,nonce):
    r=requests.get(url,timeout=25,headers={'Cache-Control':'no-cache','Pragma':'no-cache'});r.raise_for_status();return r.text

@st.cache_data(show_spinner=False)
def parse_cached(txt): return parse(txt)

@st.cache_data(show_spinner=False)
def structure_cached(txt,cut,maxgap,target):
    draws,_=parse_cached(txt)
    # Do not use the target day's realized results when validating today's signals.
    past=[r for r in draws if r.day<target]
    result=structure_statistics(past,date.fromisoformat(cut),maxgap)
    return verify_structural(result)


def show(df,limit=200,height=450):
    if df is None or df.empty:
        st.caption('Bu koşullarda kayıt bulunamadı. 0 sonuç da geçerli sonuçtur.')
    else:
        st.dataframe(df.head(limit),use_container_width=True,hide_index=True,height=min(height,44+36*(min(limit,len(df))+1)))
        if len(df)>limit:st.caption(f'{limit}/{len(df)} satır gösteriliyor; tamamı indirilen raporda.')

# Telefon için yan menü yerine tek sayfalık, kolay anlaşılır kontrol alanı.
# Hazır modlar küçük işlem bloklarıyla çalışır. Değerler yalnızca "Özel" seçilirse değişir.
st.markdown('### 🧭 Analiz ayarları')
scan_mode=st.radio('Nasıl tarayalım?', ['Hızlı', 'Dengeli (önerilen)', 'Derin'],
                   index=1, horizontal=True, help='Dengeli: kapsamlı ve telefon için daha kontrollü işlem.')
presets={
    'Hızlı': (7,12,80,2),
    'Dengeli (önerilen)': (16,24,160,2),
    'Derin': (16,36,240,1),
}
holdout,maxgap,maxfam,batch=presets[scan_mode]
target=st.date_input('Hedef gün',TR_NOW)
with st.expander('⚙️ İleri ayarlar (istersen değiştir)', expanded=False):
    custom=st.checkbox('Hazır değerler yerine kendim ayarlayayım',value=False,key='v71_custom')
    if custom:
        holdout=st.slider('Kör test: son kaç gün?',5,16,holdout)
        maxgap=st.slider('Gün içi aralık (çekiliş)',6,36,maxgap,step=6)
        maxfam=st.slider('Boyut başına yeni aile',40,400,maxfam,step=40)
        batch=st.slider('Tek işlemde kaç gün?',1,4,batch)
    st.caption('Kör test: geçmişi öğrenmeden yapılan sınama. Aralık: 1. ve 2. görünüş arasında araştırılan en büyük çekiliş farkı.')
    st.caption('Aile limiti çok büyürse işlem uzar. Gün sayısını küçük tutmak daha güvenli ilerleme sağlar.')
with st.expander('📁 Veri ekle veya yedekten devam et (isteğe bağlı)', expanded=False):
    url=st.text_input('GitHub veri.txt bağlantısı',RAW)
    uploaded=st.file_uploader('Ek çekiliş TXT dosyaları',type=['txt'],accept_multiple_files=True)
    paste=st.text_area('Canlı çekilişleri buraya da yapıştırabilirsin',height=90,
                       placeholder='61674;12.10.2026 09:42;1,2,... (20 sayı)')
    old_backup=st.file_uploader('İlerleme yedeği (checkpoint ZIP)',type=['zip'],key='v7_restore')
    if st.button('🔄 GitHub önbelleğini temizle'):
        fetch_url.clear();st.rerun()
st.caption(f'**{scan_mode}:** {holdout} gün kör test · en fazla {maxgap} çekiliş aralığı · '
           f'{maxfam} yeni aile / boyut · {batch} gün / işlem')
start=st.button('🚀 VERİYİ AL VE ANALİZİ BAŞLAT',type='primary',use_container_width=True)

if start:
    try:base=fetch_url(url,str(TR_NOW))
    except Exception as e:
        base='';st.warning(f'GitHub okunamadı: {e}. Yüklenen/yapıştırılan veri kullanılacak.')
    parts=[base]
    for file in uploaded or []:
        data=file.getvalue()
        try:parts.append(data.decode('utf-8-sig'))
        except UnicodeDecodeError:parts.append(data.decode('cp1254',errors='replace'))
    if paste.strip():parts.append(paste)
    draws,issues=parse_cached('\n'.join(parts))
    if issues['celiski']:
        st.error('Veride çelişen çekilişler var, analiz durduruldu: '+'; '.join(issues['celiski'][:5]));st.stop()
    if draws and target<draws[-1].day:
        draws=[r for r in draws if r.day<=target]
        st.warning('Geçmiş hedef gün seçildi. Sonraki günlerin verisi analizden çıkarıldı; ileriye bakma hatası önlendi.')
    days=byday(draws)
    if len(days)<12:
        st.error(f'Yeterli gün yok: {len(days)}. Kör test için en az 12 gün ve geçerli 20 sayılı çekiliş gerekli.');st.stop()
    options={'holdout':holdout,'gap':maxgap,'per_size':maxfam}
    txt=serialize(draws);key=hash_settings(draws,options)
    path=WORKDIR/f'ritim_v7_{key}.sqlite'
    if old_backup is not None:
        raw=old_backup.getvalue()
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if not {'checkpoint.sqlite','settings.json'}.issubset(z.namelist()):raise ValueError('V7 yedek biçimi değil')
                info=json.loads(z.read('settings.json'))
                if info.get('key')!=key:raise ValueError('Yedek, bu veri ve ayarlarla aynı değil')
                stat=z.getinfo('checkpoint.sqlite')
                if stat.file_size>250*1024*1024:raise ValueError('Yedek çok büyük')
                path.parent.mkdir(parents=True,exist_ok=True)
                for suffix in ('-wal','-shm'):
                    Path(str(path)+suffix).unlink(missing_ok=True)
                path.write_bytes(z.read('checkpoint.sqlite'))
                conn=sqlite3.connect(path)
                if conn.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Bozuk SQLite veritabanı')
                conn.close()
            st.success('İşlem yedeği aynı veriye geri yüklendi.')
        except Exception as e:
            st.error('Yedek yüklenemedi: '+str(e));st.stop()
    initialize(path,draws,holdout,maxfam,maxgap)
    st.session_state['v7_job']={'text':txt,'path':str(path),'key':key,'options':options,'target':target.isoformat(),'issues':issues}
    st.session_state['v7_auto']=False
    st.session_state.pop('v7_structure',None)
    st.session_state.pop('v7_backup',None)
    st.session_state.pop('v72_changed_result',None)
    st.session_state.pop('v72_changed_cache_key',None)
    st.rerun()

job=st.session_state.get('v7_job')
if job:
    stored_target=date.fromisoformat(job['target'])
    changed=(target!=stored_target or {'holdout':holdout,'gap':maxgap,'per_size':maxfam}!=job['options'])
    if changed:
        st.warning('Hedef gün veya tarama ayarları değişti. Bunları kullanmak için “VERİYİ AL VE ANALİZİ BAŞLAT” düğmesine bas. Mevcut rapor eski sabit ayarlarla gösteriliyor.')
        target=stored_target

if not job:
    st.markdown('**Başlamak için** **“VERİYİ AL VE ANALİZİ BAŞLAT”** düğmesine dokun. `veri.txt` GitHub’dan okunur; burada yeni dosya yüklemek zorunlu değil.')
    st.markdown('Analiz, her işlem adımını kendi veritabanına kaydeder. Uygulama açıkken **otomatik devam** edebilir veya sen her adımı elle başlatabilirsin. Sunucu yeniden başlarsa indirilen yedeği yeniden yüklemek gerekebilir.')
    st.stop()

opts=job['options'];path=job['path'];txt=job['text']
draws,issues=parse_cached(txt)
q=data_quality(draws)
cut=initialize(path,draws,opts['holdout'],opts['per_size'],opts['gap'])
stg=status(path)
all_days=sorted(byday(draws))
train_days=sum(d<cut for d in all_days)
meta_stage=stg.get('stage','mine')
name_stage={'mine':'1/2 · Aile keşfi','profile':'2/2 · Aile ve üçlü doğrulama','ready':'TAMAMLANDI'}
c1,c2,c3,c4=st.columns(4)
c1.metric('Geçerli çekiliş',f'{len(draws):,}'.replace(',','.'))
c2.metric('Analiz günü',len(all_days))
c3.metric('Bulunan aday',int(stg.get('candidate_count',0)))
c4.metric('Aile profili',int(stg.get('profile_count',0)))
st.write(f"**Aşama:** {name_stage.get(meta_stage,meta_stage)} · **Eğitim/test sınırı:** {cut:%d.%m.%Y} · **Son kayıt:** {draws[-1].dt:%d.%m.%Y %H:%M}")
if issues.get('gecersiz'):st.caption(f"Atlanan geçersiz satır: {issues['gecersiz']}")
if meta_stage=='mine':
    st.progress(min(1,int(stg.get('mine_pos',0))/max(1,train_days)))
    st.caption(f"İşlenen eğitim günü: {stg.get('mine_pos',0)} / {train_days}")
elif_stage=meta_stage=='profile'
if elif_stage:
    st.progress(min(1,int(stg.get('profile_pos',0))/max(1,int(stg.get('selected_count',1)))))
    st.caption(f"İşlenen aile: {stg.get('profile_pos',0)} / {stg.get('selected_count',0)}")

if meta_stage!='ready':
    st.session_state.setdefault('v7_auto',False)
    st.toggle('▶ Otomatik devam et (ekran açıkken parça parça)',key='v7_auto')
    if st.button('⏩ Sonraki parçayı işle',type='primary'):
        try:
            with st.spinner('Küçük bölüm işleniyor; önceki ilerleme silinmez…'):
                step_job(path,draws,opts,batch=batch)
            st.rerun()
        except (sqlite3.Error,ValueError,RuntimeError) as e:
            st.error('İşlem kesildi; son başarılı bölüm saklandı. Tekrar deneyebilirsin: '+str(e))
    @st.fragment(run_every='3s')
    def advance():
        if st.session_state.get('v7_auto',False):
            try:
                with st.spinner('Otomatik küçük parça analiz ediliyor…'):
                    res=step_job(path,draws,opts,batch=min(batch,3))
                st.write(f"Kaydedildi · {name_stage.get(res['stage'],res['stage'])} · gün {res.get('mine_pos')} · aile {res.get('profile_pos')}")
                if res['stage']=='ready':
                    st.session_state['v7_completed']=True
                    st.rerun()
            except (sqlite3.Error,ValueError,RuntimeError) as e:
                st.error('Otomatik işlem bu adımda durdu. Son ilerleme saklı: '+str(e))
                st.caption('Otomatik devam düğmesini kapatıp elle devam etmeyi deneyebilirsin.')
        else:
            st.caption('Otomatik işlem kapalı; elle devam edebilirsin.')
    advance()
    with st.expander('Kaldığın yerden devam ve güvenlik'):
        if st.button('💾 Şu anki ilerleme yedeğini hazırla'):
            b=io.BytesIO()
            source=connect(path);tmp=sqlite3.connect(':memory:');source.backup(tmp)
            dst=WORKDIR/'backup_snapshot.sqlite';snapshot=sqlite3.connect(dst)
            tmp.backup(snapshot);snapshot.close();tmp.close();source.close()
            with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
                z.write(dst,'checkpoint.sqlite')
                z.writestr('settings.json',json.dumps({'key':job['key']},ensure_ascii=False))
            st.session_state['v7_backup']=b.getvalue()
        if st.session_state.get('v7_backup'):
            st.download_button('⬇️ İLERLEME YEDEĞİNİ İNDİR',st.session_state['v7_backup'],
                               'HIZLI_ON_V7_CHECKPOINT.zip',mime='application/zip')
        st.write('Aynı veri ve ayarlarla uygulamayı yeniden açtığında kaydedilmiş ilerlemeden devam eder. Streamlit Cloud yerel diski sunucu yeniden kurulunca silinebilir. ZIP raporunu ve varsa veritabanı yedeğini indir.')
    st.stop()

# ===== V7.2 Cross-day scan is separate from V7 daily candidate mining. =====
@st.cache_data(show_spinner=False)
def _v72_changed_cached(data_text, cut_iso, gap_limit):
    ds,_=parse_cached(data_text)
    return v72_changed_family_test(ds,date.fromisoformat(cut_iso),gap_limit)

# Completed: all views read-only, no expensive mining on each page refresh.
profiles=to_frame(path,'profile')
selected=to_frame(path,'selected')
rhythms=to_frame(path,'rhythm')
triple=to_frame(path,'triples')
hits=to_frame(path,'hits')
exact=to_frame(path,'predictions')
hits=hits.sort_values(['k','fam','day','pos']).copy()
if not hits.empty:
    hits['Gün içi görünüş no']=hits.groupby(['k','fam','day']).cumcount()+1
    hits['Genel görünüş no']=hits.groupby(['k','fam']).cumcount()+1
    hits['Saat']=hits.pos.map(pos_time)
    hits['Saat bandı']=hits['Saat'].str[:2]
    hourly=hits.groupby(['day','Saat bandı','k']).agg(
        **{'Tam aile görünüşü':('fam','size'),'Farklı aile':('fam','nunique')}).reset_index()
else:
    hourly=pd.DataFrame(columns=['day','Saat bandı','k','Tam aile görünüşü','Farklı aile'])
timeline=pd.DataFrame([{'Tarih':str(r.day),'Saat':pos_time(r.pos),'Günlük sıra':r.pos,
                        'Çekiliş no':r.id,'20 sayı':','.join(map(str,r.nums))} for r in draws])
if not hits.empty:
    count_by=hits.groupby(['day','pos','k']).size().unstack(fill_value=0).reset_index()
    count_by.columns=['Tarih','Günlük sıra']+[f'{col}lı aile' for col in count_by.columns[2:]]
    timeline=timeline.merge(count_by,on=['Tarih','Günlük sıra'],how='left')
    for k in SIZES:
        c=f'{k}lı aile'
        if c not in timeline.columns:timeline[c]=0
    timeline[[f'{k}lı aile' for k in SIZES]]=timeline[[f'{k}lı aile' for k in SIZES]].fillna(0).astype(int)
limit_day=target if isinstance(target,date) else date.fromisoformat(str(target))
asof=max([r.pos for r in draws if r.day==limit_day],default=0)
if len([r for r in draws if r.day==limit_day])>=180:
    st.caption('Hedef günün çok sayıda çekilişi kaydedilmiş olabilir; gelecekteki hedef ancak en son veri sonrasına üretilebilir.')

st.success('Aile taraması tamamlandı; kayıtlar hazır. Alt sekmeleri açmak yeniden 70 günlük analizi çalıştırmaz.')
with st.expander('Hedef pencere ayarı',expanded=False):
    horizon=st.slider('Kaç sonraki çekiliş için aday gösterilsin?',1,36,12)
    manual_asof=st.slider('Gün içi bilinen son çekiliş sırası',0,217,asof)
    st.caption('Geriye dönük canlı simülasyonda 1. ve 2. gelişler yalnızca seçilen sıraya kadar okunur. Ancak bu ekrandaki tarihsel puanlar geriye dönük canlı doğrulaması yerine geçmez.')
else_horizon=locals().get('horizon',12)
else_asof=locals().get('manual_asof',asof)
live=live_exact(draws,path,limit_day,else_asof,else_horizon)
perf=performance(exact)

# Structural analysis is an optional single additional pass; cached for this exact data/time split.
if st.button('🧪 Rakam değişimli kör testini hesapla (bir defa)'):
    with st.spinner('Geçmiş 1→2→3 çiftleri eğitim ve test olarak ayrı sayılıyor…'):
        st.session_state['v7_structure']=structure_cached(txt,cut.isoformat(),opts['gap'],limit_day)
struc=st.session_state.get('v7_structure')
if struc is None:struct_live=pd.DataFrame()
else:struct_live=structural_live(draws,limit_day,else_asof,struc,opts['gap'],else_horizon)

c1,c2,c3,c4=st.columns(4)
c1.metric('Seçilen aile',len(profiles))
c2.metric('Gün içinde 3 görünüş',int(profiles['anyday3'].sum()) if not profiles.empty else 0)
c3.metric('Sabit aralıklı üçlü',int(profiles['sameday3'].sum()) if not profiles.empty else 0)
c4.metric('Önceden hedeflenip tam gelen',int((exact['hit']==exact['k']).sum()) if not exact.empty else 0)

# V7.2 is optional and resumable; the V7 results above remain available.
st.markdown('### 🔬 V7.2 — 6’lı–10’lu farklı günlerde aynı çekiliş ritmi')
with st.expander('Ayrıntılı çapraz-gün taramasını aç',expanded=False):
    st.caption('Bu motor önceden seçilmiş ailelerle sınırlı değildir. Gerçek çekilişlerden aynı gün g/g eşit aralıklı üçlüleri üretir; günler arası aynı aile+gap tekrarını ve sonradan görmeden yapılmış kör hedefleri ayrı gösterir.')
    cross_path=WORKDIR/f"v72_{job['key']}_{cut.isoformat()}_{opts['gap']}.sqlite"
    with st.expander('💾 V7.2 ilerleme yedeği / geri yükle',expanded=False):
        v72_restore=st.file_uploader('V7.2 checkpoint ZIP',type=['zip'],key='v72_restore_upload')
        if v72_restore is not None and st.button('V7.2 yedeğini geri yükle',key='v72_restore_btn'):
            try:
                with zipfile.ZipFile(io.BytesIO(v72_restore.getvalue())) as zz:
                    info=json.loads(zz.read('settings.json').decode('utf-8'))
                    if info.get('key')!=job['key'] or info.get('cutoff')!=cut.isoformat() or info.get('maxgap')!=opts['gap']:
                        raise ValueError('Bu yedek farklı veri veya ayarlara ait')
                    entry=zz.getinfo('v72_checkpoint.sqlite')
                    if entry.file_size>250*1024*1024:raise ValueError('Yedek çok büyük')
                    tmp=cross_path.with_suffix('.restore.sqlite')
                    tmp.parent.mkdir(parents=True,exist_ok=True)
                    tmp.write_bytes(zz.read('v72_checkpoint.sqlite'))
                    check=sqlite3.connect(str(tmp))
                    ok=check.execute('PRAGMA quick_check').fetchone()[0]
                    check.close()
                    if ok!='ok':raise ValueError('SQLite kontrolü başarısız')
                    for suffix in ('-wal','-shm'):
                        Path(str(cross_path)+suffix).unlink(missing_ok=True)
                    tmp.replace(cross_path)
                st.success('V7.2 ilerleme yedeği geri yüklendi.')
                st.rerun()
            except (zipfile.BadZipFile,ValueError,sqlite3.Error,KeyError,RuntimeError) as e:
                st.error('Yedek geri yüklenemedi: '+str(e))
        if cross_path.exists() and st.button('💾 V7.2 ilerleme yedeği hazırla',key='v72_backup_btn'):
            try:
                mem=sqlite3.connect(':memory:')
                src=sqlite3.connect(str(cross_path))
                src.backup(mem)
                src.close()
                tmp=cross_path.with_suffix('.backup.sqlite')
                dst=sqlite3.connect(str(tmp))
                mem.backup(dst)
                mem.close();dst.close()
                out=io.BytesIO()
                with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as zz:
                    zz.write(tmp,'v72_checkpoint.sqlite')
                    zz.writestr('settings.json',json.dumps({'key':job['key'],'cutoff':cut.isoformat(),'maxgap':opts['gap']}))
                st.session_state['v72_progress_backup']=out.getvalue()
                tmp.unlink(missing_ok=True)
            except (sqlite3.Error,ValueError) as e:st.error('Yedek hazırlanamadı: '+str(e))
        if st.session_state.get('v72_progress_backup'):
            st.download_button('⬇️ V7.2 İLERLEME ZIP İNDİR',st.session_state['v72_progress_backup'],
                               file_name='HIZLI_ON_V72_CHECKPOINT.zip',mime='application/zip',key='v72_backup_download')
    try:
        v72_init(cross_path,draws,cut,opts['gap'])
        cs=v72_state(cross_path)
    except (sqlite3.Error,ValueError) as e:
        st.error('V7.2 tarama verisi açılamadı: '+str(e));cs={}
    if cs:
        total_days=len(all_days)
        total_test=sum(d>=cut for d in all_days)
        cross_stage=cs.get('stage','scan')
        if cross_stage!='ready':
            if cross_stage=='scan':
                st.progress(min(1,int(cs['scan_at'])/max(1,total_days)))
                st.caption(f"Geçmiş taraması: {cs['scan_at']} / {total_days} gün · aile üçlü kaydı: {cs['triple_count']}")
            else:
                st.progress(min(1,int(cs['test_at'])/max(1,total_test)))
                st.caption(f"Geleceği görmeyen doğrulama: {cs['test_at']} / {total_test} gün")
            if st.button('⏩ V7.2: Sonraki 2 günü işle',key='v72_next',type='primary'):
                try:
                    v72_step(cross_path,draws,opts['gap'],batch=2)
                    st.rerun()
                except (ValueError,sqlite3.Error) as e:
                    st.error('Bu adım kesildi; önceki ilerleme saklandı: '+str(e))
            st.toggle('▶ V7.2 otomatik küçük parçalarla devam et',key='v72_auto',value=False)
            @st.fragment(run_every='3s')
            def v72_advance():
                if st.session_state.get('v72_auto',False):
                    try:
                        state=v72_step(cross_path,draws,opts['gap'],batch=2)
                        st.caption(f"V7.2: {state['stage']} · {state['scan_at']} gün tarandı · {state['test_at']} kör gün")
                        if state['stage']=='ready':
                            st.session_state['v72_auto']=False
                            st.rerun()
                    except (ValueError,sqlite3.Error) as e:
                        st.session_state['v72_auto']=False
                        st.error('V7.2 otomatik işleme durdu, kayıt korundu: '+str(e))
            v72_advance()
        else:
            st.success(f"V7.2 taraması tamamlandı: {cs['triple_count']} tarihsel üçlü, {cs['pred_count']} önceden belirlenmiş sabit aile hedefi.")
            result=v72_reports(cross_path)
            show(result['ozet'],10)
            repeated=result['tekrarlayan_aile_gap']
            repeated=repeated[repeated['days']>=2] if not repeated.empty else repeated
            st.markdown('**Aynı aile + aynı gap, en az iki farklı günde**')
            show(repeated,60)
            st.markdown('**Farklı rakamlarla yinelenen çekiliş aralıkları (tanımlayıcı)**')
            show(result['degisen_aile_yapisi'],60)
            st.markdown('**Üçüncü çekiliş öncesinde sabit aileden türetilmiş kör hedefler**')
            show(result['kor_test'],70)
            st.markdown('**Rakam değişimli deneysel kör test**')
            if st.button('🧪 Rakam değişimli kör testi hesapla',key='v72_changed_btn'):
                try:
                    with st.spinner('Eğitim dönemindeki aralıklar seçiliyor, sonraki günler kör ölçülüyor…'):
                        st.session_state['v72_changed_result']=_v72_changed_cached(txt,cut.isoformat(),opts['gap'])
                        st.session_state['v72_changed_cache_key']=str(cross_path)
                except (ValueError,RuntimeError,MemoryError) as e:
                    st.error('Kör test tamamlanamadı: '+str(e))
            change=st.session_state.get('v72_changed_result') if st.session_state.get('v72_changed_cache_key')==str(cross_path) else None
            if change:
                train_df,pred_df,chosen=change
                st.caption('Deneysel adaylar sadece eğitimdeki eşiklerle seçilir. Kör dönemde seçimin başarı garantisi yoktur.')
                show(train_df[train_df['Deneme filtresi']],75)
                if not pred_df.empty:
                    summary=pred_df.groupby('Boyut').agg(**{
                        'Kör kupon':('İsabet','size'),'Ortalama':('İsabet','mean'),
                        'En yüksek':('İsabet','max')}).reset_index()
                    summary['Rastgele ortalama']=summary['Boyut']/4
                    show(summary,10)
                    show(pred_df,70)
                else:st.caption('Kör deneysel aday yok. Bu da geçerli bir sonuçtur.')
            st.markdown('**Canlı üçüncü görünüş adayı (en az iki önceki ayrı ritim günü gerekir)**')
            future=v72_live(cross_path,draws,limit_day,else_asof,opts['gap'],else_horizon,need_days=2)
            show(future,40)
            export={
                'V72_01_BOYUT_OZETI.csv':result['ozet'],
                'V72_02_TUM_ESIT_GAP_UCLULER.csv':result['tum_ucluler'],
                'V72_03_SABIT_AILE_GAP_TEKRARI.csv':result['tekrarlayan_aile_gap'],
                'V72_04_RAKAM_DEGISIMLI_GAP_GOZLEMI.csv':result['degisen_aile_yapisi'],
                'V72_05_SABIT_AILE_KOR_HEDEF.csv':result['kor_test'],
                'V72_06_CANLI_ARASTIRMA.csv':future}
            if change:
                export['V72_07_DEGISKEN_EGITIM.csv']=change[0]
                export['V72_08_DEGISKEN_KOR_HEDEFLER.csv']=change[1]
            methodological='V7.2 tam veri 6-10 ailesi: Üçlüler aynı gün eşit çekiliş gapleriyle bulunur. Kör sabit aile tahminleri sadece hedef günden önceki aile+gap üçlülerini kullanır. Değişken rakam kuponu ilk iki çekilişte ortak çıkan ilk k rakamdan oluşturulur; gapler yalnız eğitimde seçilir. Tarihsel üçlüler birden fazla kombinasyonla örtüşebilir. Geçmişte 100% = gelecekte garanti DEĞİLDİR. 0 doğrulanmış sinyal için 0 onaylı kupon.'
            st.download_button('⬇️ V7.2 TAM RAPOR ZIP',bundle_reports(export,methodological),
                               file_name='HIZLI_ON_V72_TAM_ARASTIRMA_RAPORU.zip',mime='application/zip',key='v72_download')

T=st.tabs(['📊 Özet','5️⃣ Beşli','6️⃣ Altılı','7️⃣ Yedili','8️⃣ Sekizli','9️⃣ Dokuzlu','🔟 Onlu','🔗 Üçlü ritimler','🧪 Kör isabet','🎯 Hedef kupon','📦 Tek ZIP'])
with T[0]:
    st.subheader('Veri bütünlüğü ve motorların sonuçları')
    show(q.tail(80),80)
    st.markdown('**Çekiliş çekiliş: tam aile eşleşme sayıları**')
    show(timeline.tail(120).iloc[::-1],120)
    st.markdown('**Gün / saat / aile boyutu görünüş tablosu**')
    show(hourly.tail(150).iloc[::-1],150)
    summary=[]
    for k in SIZES:
        p=profiles[profiles.k==k]
        summary.append({'Boyut':k,'Bulunan aile':len(p),'Aynı gün 3 gelişi':int(p['anyday3'].sum()),
                        'Eşit gap üçlüsü':int(p['sameday3'].sum()),'Günler arası 3 gün ritmi':int(p['crossday3'].sum()),
                        'Kör hedef':int((exact.k==k).sum()),'Kör tam isabet':int(((exact.k==k)&(exact.hit==k)).sum())})
    overview=pd.DataFrame(summary)
    show(overview,10)
    st.caption('Bu sayılar birbirine eklenerek bağımsız olay sayısı kabul edilmez: tek aile birden çok örtüşen zincir oluşturabilir. Aile keşfi bütçeli olup tüm C(20,k) kombinasyonları eksiksiz saymaz.')

for index,k in enumerate(SIZES):
    with T[index+1]:
        p=profiles[profiles.k==k].copy()
        st.subheader(f'{k}’lı aileler — kendi başına analiz')
        if p.empty:
            st.warning(f'{k}’lı boyutta bu tarama bütçesiyle doğrulanmış aile kaydı bulunamadı. Bu, bütün olası {k}’lıların hiç tekrarlanmadığı anlamına gelmez.')
        else:
            pp=p.merge(selected[selected.k==k][['fam','src']],on='fam',how='left')
            show(pp.sort_values(['sameday3','crossday3','occ'],ascending=False),200)
            st.markdown('**En düzenli üçlü ritimler (aynı aile)**')
            rr=rhythms[(rhythms.k==k)&(rhythms.train3>0)].sort_values(['train3','all3'],ascending=False)
            show(rr,150)
            st.markdown('**Bugün için önceden hedef kaydı**')
            show(live[live.Boyut==k],50)

with T[7]:
    st.subheader('Gerçek 1. → 2. → 3. görünüş ayrıntıları')
    st.markdown('**Gün içinde üç geliş:** Tek bir ailenin 3 kere çıkması ile iki aralığın eşit olması ayrı sütunlardır.')
    tr=triple.sort_values(['equal','day','k'],ascending=[False,False,True]) if not triple.empty else triple
    show(tr,250)
    st.markdown('**Farklı günlerde aynı ritim:**')
    show(rhythms[(rhythms['mode']=='gün')&(rhythms['all3']>0)].sort_values(['train3','all3'],ascending=False),200)
    st.caption('Günler arası üçlü, o ailenin üç farklı aktif gününün eşit takvim aralığı oluşturmasıdır. Aynı saat/sırada tam tekrar ayrıca zorunlu değildir; zaman tutarlılığı ikinci bir test gerektirir.')

with T[8]:
    st.subheader('Aile bazında, tahmin yapıldıktan sonra ölçülen isabet')
    show(perf,10)
    st.markdown('**Gerçek kör hedefler (tahminin 1. ve 2. çekilişi hedeften öncedir):**')
    show(exact.sort_values(['day','pos'],ascending=[False,False]),220)
    if struc is not None:
        st.subheader('Rakam değişimli üçlü araştırması: eğitim / bağımsız test')
        show(struc,260)
        st.caption('3. devam ölçütü: ikinci ve üçüncü çekilişte >=k ortak sayı. Tam kupon ölçütü ayrı verilir. Eğitimde iyi görünen sonuç yalnız kör testten geçerse aday sayılır. İstatistiksel test sonuçları çakışan üçlüler nedeniyle kesin bağımsız kanıt değildir.')
    else:st.info('Rakam değişimli üçüncü geliş testini görmek için üstteki “Rakam değişimli kör testini hesapla” düğmesine bas.')

with T[9]:
    st.subheader('Yeni gün, yeni saat: 3. hedef çekilişi')
    st.markdown('**Gerçek tam aile adayları — eğitimde daha önce en az 2 eşit ritimli üçlü:**')
    show(live,160)
    st.markdown('**Rakam değişimli, bağımsız test filtresini geçen adaylar:**')
    show(struct_live,160)
    # Exact signals need independent out-of-sample performance; positive samples on other days not enough for 100% guarantee.
    st.warning('**Kesin (%100) kupon: 0.** Tekrarlayan ritim veya önceki tam isabet, gelecek çekilişte aynı aileyi garanti etmez. Yukarıdaki satırlar yalnız önceden planlanabilir araştırma hedefidir; kabul edilmiş kupon sayısı performans kanıtı gerektirir.')
    if live.empty and struct_live.empty:st.success('Bu hedef gün ve pencere için doğrulanabilir sinyal bulunmadı → 0 kupon.')

with T[10]:
    st.subheader('Tüm detayları tek ZIP indir')
    table={'01_VERI_KALITESI.csv':q,'02_BOYUT_OZETI.csv':overview,'03_TUM_AILELER.csv':profiles,
           '04_RITIM_GAP_GUN_CEKILIS.csv':rhythms,'05_3_KEZ_GELENLER.csv':triple,
           '06_AILE_VURUS_SAAT_SIRA.csv':hits,'07_KOR_HEDEF_ISABET.csv':exact,
           '08_BOYUT_ISABET_0_K.csv':perf,'09_CANLI_TAM_AILE_ADAY.csv':live,
           '10_RAKAM_DEGISIMLI_KOR_TEST.csv':struc if struc is not None else pd.DataFrame(),
           '11_RAKAM_DEGISIMLI_CANLI_ADAY.csv':struct_live,
           '15_HER_CEKILIS_AILE_GORUNUS.csv':timeline,'16_GUN_SAAT_BOYUT_OZET.csv':hourly}
    note=f'''HIZLI ON V7 — ARAŞTIRMA NOTLARI\nVeri: {len(draws)} çekiliş; aralık {draws[0].dt} – {draws[-1].dt}.\nEğitim/test ayrımı: {cut}. Yeni ailelerin otomatik keşfi yalnız eğitim döneminde.\nHer boyut 5/6/7/8/9/10 ayrı incelenir. 1→2→3 tam aile, aynı sayıların 3 ayrı çekilişte görünmesidir.\nGün içinde 3 kere çıkan aile, iki gap eşit olmasa da sayılır; eşit aralıklı ritim ayrıca sınıflandırılır.\nGünler-arası ardışık aktif günleri eşit gap olan üçlüler ayrı sınıftır.\nKör tahminde eğitim öncesi sonuçlar gelecek kuponu seçmek için kullanılmaz.\nCanlı sonuçlar gün içinde yalnız son bilinen sıradan sonraki pencerelere üretilir.\nHızlı On 1–80 arası 20 sayıdan oluşur: rastgele k sayılık kuponun ortalama tutanı k/4'tür.\nGeçmişte %100 sıklık ≠ gelecekte %100 isabet; geçmiş ritim gelecek olasılığını garanti etmez.\nSaat ile gün içi sıra bağımsız iki kanıt değildir.\nVeri eksik/hatalı olabilir; kalite tablosundaki eksik slotları incele.\nAday keşfi bütçelidir: 20 sayıdan C(20,k) tüm alt kümeler eksiksiz taranmamıştır. 9/10 bulamamak yokluk kanıtı değildir.\nRakam değişimli olay, tam aynı aile tekrarı değildir.\nÇoklu test düzeltmesi Bonferroni'dir; ilişkili çekilişler nedeniyle sonuçlar ihtiyatla yorumlanmalıdır.\nKullanıcı her yeni TXT güncellemesinde yeni veri hash’iyle ayrı tarama başlatabilir.\nBu ürün kumar sonucu garanti edemez.\n'''
    for k in SIZES:
        table[f'12_{k}LI_AYRI_AILE_ANALIZI.csv']=profiles[profiles.k==k]
        table[f'13_{k}LI_AYRI_GAP_RITIMLERI.csv']=rhythms[rhythms.k==k]
        table[f'14_{k}LI_AYRI_KOR_HEDEFLER.csv']=exact[exact.k==k]
    data=bundle_reports(table,note)
    st.download_button('⬇️ TÜM RAPORLAR · TEK ZIP',data=data,file_name='HIZLI_ON_V7_TUM_DETAYLI_RAPORLAR.zip',mime='application/zip',type='primary')
    st.download_button('⬇️ Temizlenmiş birleştirilmiş veri.txt',data=txt.encode('utf-8'),file_name='veri_V7_temiz.txt',mime='text/plain')
    st.caption('İlerleme, aynı veri hash’i için yerel SQLite veritabanına yazıldı. Streamlit Cloud yeniden kurulursa yerel veriler kaybolabileceğinden ZIP raporunu mutlaka indir.')

st.caption('V7 · Gözlemlenen örüntü ile ileriye dönük isabet kanıtı farklıdır. Araştırma aracı; kazanç veya kesin tahmin garantisi yoktur.')
