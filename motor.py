# -*- coding: utf-8 -*-
"""Hizli On V7: resumable exact-family mining and prequential backtesting.
No future result is used for generating any prediction in validation.
"""
from __future__ import annotations
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
