import streamlit as st
import pandas as pd
import numpy as np
import sqlite3, json, hashlib, re, math, io, zipfile, base64, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

st.set_page_config(page_title='Hızlı On RNG Dijital İkiz V2', layout='wide')
DB='hizli_on_rng_twin_v2.db'
SEED_DEFAULT='HIZLI_ON_25_08_2026_07_09_2026_TAM_14_GUN(1).txt'
FEATURE_VERSION='V2.2-GITHUB-PERSIST'
LIVE_DAY='2026-09-08'


# ---------- GITHUB KALICI CANLI VERI ----------
# Streamlit Secrets örneği:
# GITHUB_TOKEN = "github_pat_..."
# GITHUB_REPO = "kullanici/depo"
# GITHUB_BRANCH = "main"              # opsiyonel
# GITHUB_LIVE_FILE = "veri.txt"       # opsiyonel

def _secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

def github_config():
    return {
        'token': _secret('GITHUB_TOKEN'),
        'repo': _secret('GITHUB_REPO'),
        'branch': _secret('GITHUB_BRANCH', 'main'),
        'path': _secret('GITHUB_LIVE_FILE', 'veri.txt'),
    }

def github_enabled():
    g=github_config()
    return bool(g['token'] and g['repo'])

def github_request(method, url, payload=None):
    g=github_config()
    data=None if payload is None else json.dumps(payload).encode('utf-8')
    req=urllib.request.Request(url, data=data, method=method)
    req.add_header('Authorization', f"Bearer {g['token']}")
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('X-GitHub-Api-Version', '2022-11-28')
    req.add_header('User-Agent', 'hizli-on-rng-twin')
    if data is not None: req.add_header('Content-Type','application/json')
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body=e.read().decode('utf-8',errors='ignore')
        if e.code==404: return 404, None
        raise RuntimeError(f'GitHub HTTP {e.code}: {body[:300]}')

def canonical_live_text(rows):
    # Kalıcı dosyada Detaylar/link ASLA tutulmaz.
    out=[]
    for draw_id,dt,nstr,_ in sorted(rows,key=lambda r:(r[1],r[0])):
        d=datetime.fromisoformat(dt)
        nums=list(map(int,nstr.split(',')))
        out += [f'### Çekiliş no:', f'### {draw_id}', d.strftime('%d.%m.%Y-%H:%M')]
        out += [str(n) for n in nums]
        out.append('')
    return '\n'.join(out).rstrip()+'\n'

def github_persist_live_rows(new_rows):
    """Repo veri.txt dosyasını draw_id bazında birleştirip temiz formatta commit eder."""
    if not github_enabled():
        raise RuntimeError('GitHub kalıcı kayıt ayarlı değil. Streamlit Secrets içine GITHUB_TOKEN ve GITHUB_REPO ekle.')
    g=github_config(); path=g['path'].strip('/')
    api=f"https://api.github.com/repos/{g['repo']}/contents/{path}?ref={g['branch']}"
    status,obj=github_request('GET',api)
    sha=None; existing=''
    if status==200 and obj:
        sha=obj.get('sha')
        existing=base64.b64decode(obj.get('content','')).decode('utf-8-sig',errors='ignore')
    old=parse_text(existing,'live') if existing.strip() else []
    merged={r[0]:r for r in old}
    for r in new_rows: merged[r[0]]=r
    final_rows=sorted(merged.values(),key=lambda r:(r[1],r[0]))
    content=canonical_live_text(final_rows)
    payload={
        'message': f"Canli Hızlı On verisi: {len(new_rows)} çekiliş işlendi",
        'content': base64.b64encode(content.encode('utf-8')).decode('ascii'),
        'branch': g['branch'],
    }
    if sha: payload['sha']=sha
    put_api=f"https://api.github.com/repos/{g['repo']}/contents/{path}"
    github_request('PUT',put_api,payload)
    audit('GITHUB_PERSIST',{'path':path,'new':len(new_rows),'total':len(final_rows)})
    return path,len(final_rows)

# ---------- DB ----------
def cx(): return sqlite3.connect(DB)
def init_db():
    with cx() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS draws(draw_id INTEGER PRIMARY KEY, draw_time TEXT UNIQUE, numbers TEXT, source TEXT);
        CREATE TABLE IF NOT EXISTS predictions(id INTEGER PRIMARY KEY AUTOINCREMENT,target_time TEXT UNIQUE,created_at TEXT,numbers TEXT,probabilities TEXT,pre_state TEXT,sim_anatomy TEXT,sha256 TEXT,result_numbers TEXT,hit_count INTEGER,settled INTEGER DEFAULT 0,post_report TEXT);
        CREATE TABLE IF NOT EXISTS anatomy_baseline(key TEXT PRIMARY KEY,value REAL,n INTEGER,updated_at TEXT);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,ts TEXT,event TEXT,payload TEXT);
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
        ''')
        c.execute("INSERT OR IGNORE INTO meta VALUES('feature_version',?)",(FEATURE_VERSION,))
init_db()

def audit(event,payload):
    with cx() as c: c.execute('INSERT INTO audit(ts,event,payload) VALUES(?,?,?)',(datetime.now().isoformat(),event,json.dumps(payload,ensure_ascii=False)))

def parse_text(txt,source='seed'):
    """Arşiv satırlarını ve kullanıcının doğal Milli Piyango kopyala/yapıştır
    formatını toleranslı biçimde okur. Markdown başlık/linkleri, Detaylar satırı,
    boşluk ve ters sıralama sorun değildir.
    """
    rows=[]
    # 1) Arşiv: draw_id;DD.MM.YYYY HH:MM;n1,...,n20
    for line in txt.splitlines():
        m=re.match(r'^\s*(\d+)\s*;\s*(\d{2}\.\d{2}\.\d{4})\s+[- ]?(\d{2}:\d{2})\s*;\s*([\d, ]+)\s*$',line)
        if not m: continue
        nums=[int(x) for x in re.findall(r'\d+',m.group(4))]
        if len(nums)==20 and len(set(nums))==20 and min(nums)>=1 and max(nums)<=80:
            dt=datetime.strptime(m.group(2)+' '+m.group(3),'%d.%m.%Y %H:%M')
            rows.append((int(m.group(1)),dt.isoformat(sep=' '),','.join(map(str,sorted(nums))),source))
    if rows:
        return sorted({(r[0],r[1]):r for r in rows}.values(), key=lambda r:(r[1],r[0]))

    # 2) Doğal format. Tarih-saat satırını ana çapa kabul ederiz.
    #    Tarihten önceki en yakın bağımsız 4+ haneli sayı draw_id;
    #    tarihten sonraki ilk 20 bağımsız 1..80 sayı sonuçtur.
    clean=[]
    for raw in txt.replace('\r','\n').splitlines():
        x=re.sub(r'^\s*#+\s*','',raw).strip()
        # Markdown Detaylar linki veya çıplak Detaylar satırı sonuç sayılmaz.
        if re.search(r'Detaylar',x,re.I):
            clean.append('DETAYLAR')
        else:
            clean.append(x)

    date_re=re.compile(r'^(\d{2}\.\d{2}\.\d{4})\s*[-–—]?\s*(\d{2}:\d{2})(?::\d{2})?$')
    for i,line in enumerate(clean):
        dm=date_re.fullmatch(line)
        if not dm: continue

        # En yakın önceki bağımsız büyük tam sayı çekiliş numarasıdır.
        draw_id=None
        for k in range(i-1,max(-1,i-8),-1):
            q=clean[k]
            if re.fullmatch(r'\d{4,8}',q):
                draw_id=int(q); break
        if draw_id is None: continue

        nums=[]
        j=i+1
        while j<len(clean) and len(nums)<20:
            q=clean[j]
            if q=='DETAYLAR' or re.search(r'Çekiliş\s*no',q,re.I): break
            if date_re.fullmatch(q): break
            if re.fullmatch(r'\d{1,2}',q):
                v=int(q)
                if 1<=v<=80: nums.append(v)
            j+=1
        if len(nums)==20 and len(set(nums))==20:
            dt=datetime.strptime(dm.group(1)+' '+dm.group(2),'%d.%m.%Y %H:%M')
            rows.append((draw_id,dt.isoformat(sep=' '),','.join(map(str,sorted(nums))),source))

    return sorted({(r[0],r[1]):r for r in rows}.values(), key=lambda r:(r[1],r[0]))

def import_rows(rows):
    with cx() as c: c.executemany('INSERT OR IGNORE INTO draws VALUES(?,?,?,?)',rows)

def get_draws():
    with cx() as c: df=pd.read_sql_query('SELECT * FROM draws ORDER BY draw_time,draw_id',c)
    if len(df):
        df['dt']=pd.to_datetime(df.draw_time); df['date']=df.dt.dt.strftime('%Y-%m-%d'); df['time']=df.dt.dt.strftime('%H:%M'); df['nums']=df.numbers.map(lambda s:set(map(int,s.split(','))))
    return df

def z(v):
    v=np.asarray(v,float); s=v.std(); return (v-v.mean())/(s if s>1e-9 else 1.0)

def counts(sets,w):
    cc=Counter(x for s in sets[-w:] for x in s); return np.array([cc.get(n,0) for n in range(1,81)],float)

def same_day_sets(df):
    if df.empty:return []
    d=df.iloc[-1].date; return df[df.date==d].nums.tolist()

def ranks_from_sets(sets):
    cc=Counter(x for s in sets for x in s); order=sorted(range(1,81),key=lambda n:(-cc.get(n,0),n)); return {n:i+1 for i,n in enumerate(order)},cc

def age_vec(sets):
    out=[]
    for n in range(1,81):
        a=len(sets)+1
        for j,s in enumerate(reversed(sets)):
            if n in s: a=j; break
        out.append(min(a,80))
    return np.array(out,float)

def pair_strength(sets,anchor_set,w=36):
    last=sets[-w:]; out=[]
    for n in range(1,81):
        vals=[sum(1 for s in last if n in s and p in s) for p in anchor_set if p!=n]
        out.append(max(vals) if vals else 0)
    return np.array(out,float)

def last_digit_strength(sets,w=12):
    last=sets[-w:]; out=[]
    for n in range(1,81):
        fam={x for x in range(1,81) if x%10==n%10 and x!=n}
        out.append(sum(1 for s in last for x in fam if x in s)/(max(1,len(last))))
    return np.array(out,float)

def neighbor_strength(sets,w=12):
    last=sets[-w:]; out=[]
    for n in range(1,81):
        fam={x for x in (n-2,n-1,n+1,n+2) if 1<=x<=80}
        out.append(sum(1 for s in last for x in fam if x in s)/(max(1,len(last))))
    return np.array(out,float)

def feature_state(df):
    sets=df.nums.tolist(); daysets=same_day_sets(df); N=len(sets); nums=np.arange(1,81)
    rank,daycc=ranks_from_sets(daysets)
    f3,f6,f12,f17,f24,f36,f72=[counts(sets,w) for w in (3,6,12,17,24,36,72)]
    age=age_vec(daysets if daysets else sets)
    prev=sets[-1] if sets else set(); h1=np.array([1 if n in prev else 0 for n in nums],float)
    h2=np.array([1 if len(sets)>=2 and n in sets[-2] else 0 for n in nums],float)
    h3=np.array([1 if len(sets)>=3 and n in sets[-3] else 0 for n in nums],float)
    pair=pair_strength(sets,prev,36); ld=last_digit_strength(sets,12); neigh=neighbor_strength(sets,12)
    group=[]; boundary=[]
    for n in nums:
        r=rank[int(n)]; group.append('HOT' if r<=20 else ('MID' if r<=60 else 'COLD'))
        boundary.append(1 if r in range(17,25) or r in range(57,65) else 0)
    accel=f6-(f24/4.0); short_delta=f3-(f12/4.0)
    return pd.DataFrame({'number':nums,'rank':[rank[int(n)] for n in nums],'group':group,'day_count':[daycc.get(int(n),0) for n in nums],
      'f3':f3,'f6':f6,'f12':f12,'f17':f17,'f24':f24,'f36':f36,'f72':f72,'accel':accel,'short_delta':short_delta,
      'age':age,'h1':h1,'h2':h2,'h3':h3,'pair':pair,'last_digit':ld,'neighbor':neigh,'boundary':boundary})

def anatomy_of_draw(nums,fs,prev_set=None):
    s=set(nums); g=dict(zip(fs.number,fs.group)); rank=dict(zip(fs.number,fs['rank'])); age=dict(zip(fs.number,fs.age))
    hot=sum(g[n]=='HOT' for n in s); mid=sum(g[n]=='MID' for n in s); cold=20-hot-mid
    h1=len(s & (prev_set or set()))
    adj=sum(1 for n in s if n+1 in s); skip1=sum(1 for n in s if n+2 in s)
    bands=[sum(1 for n in s if lo<=n<=hi) for lo,hi in [(1,10),(11,20),(21,30),(31,40),(41,50),(51,60),(61,70),(71,80)]]
    digits=[sum(1 for n in s if n%10==d) for d in range(10)]
    boundary=sum(1 for n in s if rank[n] in range(17,25) or rank[n] in range(57,65))
    returns=sum(1 for n in s if 2<=age[n]<=7)
    deep=sum(1 for n in s if age[n]>=8)
    return {'hot':hot,'mid':mid,'cold':cold,'h1':h1,'adj_pairs':adj,'skip1_pairs':skip1,'boundary_hits':boundary,'return_age2_7':returns,'deep_age8p':deep,
            'band_max':max(bands),'band_sd':float(np.std(bands)),'digit_max':max(digits)}

def build_baseline_from_seed(df):
    seed=df[df.source=='seed'].copy()
    vals=defaultdict(list)
    for day,g in seed.groupby('date',sort=True):
        g=g.sort_values('dt').reset_index(drop=True)
        # start after 12 draws to avoid unstable rank ties
        for i in range(12,len(g)):
            pre=g.iloc[:i].copy(); fs=feature_state(pre); a=anatomy_of_draw(g.iloc[i].nums,fs,g.iloc[i-1].nums)
            for k,v in a.items(): vals[k].append(float(v))
    with cx() as c:
        for k,v in vals.items():
            c.execute('INSERT OR REPLACE INTO anatomy_baseline VALUES(?,?,?,?)',(k,float(np.mean(v)),len(v),datetime.now().isoformat()))
    audit('BASELINE_BUILT',{k:{'mean':float(np.mean(v)),'n':len(v)} for k,v in vals.items()})
    return {k:float(np.mean(v)) for k,v in vals.items()}

def baseline():
    with cx() as c: rows=c.execute('SELECT key,value FROM anatomy_baseline').fetchall()
    return dict(rows)

def score_state(fs):
    # Selection propensity only; anatomy constraints are enforced by simulation calibration.
    age_return=np.exp(-((fs.age.values-4.5)/3.5)**2)
    score=(0.55*z(fs.f6)+0.42*z(fs.f12)+0.22*z(fs.f24)+0.20*z(fs.accel)+0.12*z(fs.short_delta)+
           0.20*z(age_return)+0.18*z(fs.h1)+0.10*z(fs.h2)+0.08*z(fs.h3)+0.16*z(fs.pair)+0.08*z(fs.neighbor)+0.05*z(fs.last_digit)+0.12*z(fs.boundary))
    out=fs.copy(); out['score']=score; return out

def candidate_draw(sc,rng,temp=1.5):
    v=sc.score.values; p=np.exp((v-v.max())/max(.5,temp)); p=p/p.sum()
    return sorted(rng.choice(sc.number.values,20,replace=False,p=p).tolist())

def anatomy_distance(a,target):
    # normalized penalty; group/h1/boundary dominate, microstructure remains observable
    scales={'hot':2.0,'mid':2.5,'cold':2.0,'h1':1.7,'adj_pairs':1.5,'skip1_pairs':1.8,'boundary_hits':1.5,'return_age2_7':1.7,'deep_age8p':1.5,'band_max':1.5,'band_sd':1.0,'digit_max':1.2}
    return sum(((a[k]-target.get(k,a[k]))/scales.get(k,1))**2 for k in a)

def simulate_one(sc,target,prev,rng,candidates=80):
    best=None; bd=1e99; ba=None
    for _ in range(candidates):
        d=candidate_draw(sc,rng); a=anatomy_of_draw(d,sc,prev); dist=anatomy_distance(a,target)
        if dist<bd: best,bd,ba=d,dist,a
    return best,ba,bd

def simulate_many(sc,target,prev,n=3000,seed=20260922,candidates=20):
    rng=np.random.default_rng(seed); cc=Counter(); anatomies=[]
    for _ in range(n):
        d,a,_=simulate_one(sc,target,prev,rng,candidates); cc.update(d); anatomies.append(a)
    probs={n:cc[n]/n for n in range(1,81)}
    mean={k:float(np.mean([a[k] for a in anatomies])) for k in anatomies[0]}
    return probs,mean

def seal(df,target_time,n_sim=2000):
    fs=feature_state(df); sc=score_state(fs); target=baseline()
    if not target: target=build_baseline_from_seed(df)
    prev=df.iloc[-1].nums if len(df) else set()
    probs,sim=simulate_many(sc,target,prev,n_sim)
    # prediction is a separate calibrated draw, not top20 frequency list
    rng=np.random.default_rng(int(hashlib.sha256(target_time.encode()).hexdigest()[:12],16)); pred,pa,pd=simulate_one(sc,target,prev,rng,300)
    pre={'feature_version':FEATURE_VERSION,'target_anatomy':target,'pred_anatomy':pa,'pred_distance':pd,'top80':sc.sort_values('score',ascending=False).to_dict('records')}
    raw=json.dumps({'target':target_time,'numbers':pred,'pre':pre,'sim':sim},sort_keys=True,ensure_ascii=False,default=float); sha=hashlib.sha256(raw.encode()).hexdigest()
    with cx() as c: c.execute('INSERT OR REPLACE INTO predictions(target_time,created_at,numbers,probabilities,pre_state,sim_anatomy,sha256,settled) VALUES(?,?,?,?,?,?,?,0)',
        (target_time,datetime.now().isoformat(),','.join(map(str,pred)),json.dumps(probs),json.dumps(pre,ensure_ascii=False,default=float),json.dumps(sim,ensure_ascii=False),sha))
    audit('SEALED',{'target_time':target_time,'numbers':pred,'sha256':sha,'anatomy':pa})
    return pred,probs,pre,sim,sha

def settle(draw_id,dt,nums):
    nums=sorted(set(nums));
    if len(nums)!=20 or min(nums)<1 or max(nums)>80: raise ValueError('20 benzersiz sayı, 1-80 gerekli')
    df_before=get_draws(); fs=feature_state(df_before); prev=df_before.iloc[-1].nums if len(df_before) else set(); actual_a=anatomy_of_draw(nums,fs,prev)
    with cx() as c:
        row=c.execute('SELECT id,numbers,pre_state,sim_anatomy FROM predictions WHERE target_time=? AND settled=0',(dt,)).fetchone()
        c.execute('INSERT OR REPLACE INTO draws VALUES(?,?,?,?)',(int(draw_id),dt,','.join(map(str,nums)),'live'))
        if not row:
            audit('LIVE_WITHOUT_SEAL',{'draw_id':draw_id,'dt':dt,'anatomy':actual_a}); return None,actual_a
        pred=set(map(int,row[1].split(','))); hit=len(pred & set(nums)); pre=json.loads(row[2]); sim=json.loads(row[3]); target=pre['target_anatomy']
        diff={k:float(actual_a[k]-sim.get(k,0)) for k in actual_a}
        # Conservative anatomy calibration: baseline EMA. This learns observed output anatomy, not just coupon hits.
        alpha=0.025
        for k,v in actual_a.items():
            old=float(target.get(k,v)); nv=(1-alpha)*old+alpha*float(v)
            c.execute('INSERT OR REPLACE INTO anatomy_baseline VALUES(?,?,COALESCE((SELECT n FROM anatomy_baseline WHERE key=?),0)+1,?)',(k,nv,k,datetime.now().isoformat()))
        report={'hit':hit,'actual_anatomy':actual_a,'sim_mean':sim,'difference':diff,'alpha':alpha}
        c.execute('UPDATE predictions SET result_numbers=?,hit_count=?,settled=1,post_report=? WHERE id=?',(','.join(map(str,nums)),hit,json.dumps(report,ensure_ascii=False),row[0]))
    audit('SETTLED',{'draw_id':draw_id,'dt':dt,**report}); return hit,actual_a

def day_report():
    with cx() as c: pr=pd.read_sql_query('SELECT * FROM predictions WHERE settled=1 ORDER BY target_time',c)
    if pr.empty:return pr,pd.DataFrame()
    rows=[]
    for _,r in pr.iterrows():
        rep=json.loads(r.post_report); row={'target_time':r.target_time,'hit':r.hit_count,'sha256':r.sha256}
        for k,v in rep['actual_anatomy'].items(): row['real_'+k]=v
        for k,v in rep['sim_mean'].items(): row['sim_'+k]=v
        for k,v in rep['difference'].items(): row['diff_'+k]=v
        rows.append(row)
    det=pd.DataFrame(rows); det['date']=pd.to_datetime(det.target_time).dt.strftime('%Y-%m-%d')
    agg=det.groupby('date').agg(draws=('hit','size'),hit_mean=('hit','mean'))
    for k in ['hot','mid','cold','h1','adj_pairs','boundary_hits','return_age2_7']:
        agg['mae_'+k]=det.groupby('date')['diff_'+k].apply(lambda s:float(np.mean(np.abs(s))))
    return det,agg.reset_index()

# ---------- OTOMATİK ANA HAFIZA ----------
def ensure_seed_loaded():
    """Repo içindeki 14 günlük TXT'yi kullanıcıdan tekrar istemeden otomatik yükler."""
    df=get_draws()
    seed=df[df.source=='seed'] if not df.empty else pd.DataFrame()
    if len(seed)==3038 and seed.date.nunique()==14 and all(seed.groupby('date').size()==217):
        if not baseline(): build_baseline_from_seed(df)
        return True, 'Veritabanındaki 3.038 seed hazır.'
    candidates=[Path(SEED_DEFAULT), Path('veri.txt')]
    # İsmi değişse bile repo kökündeki 14_GUN içeren txt'yi dene.
    candidates += [x for x in Path('.').glob('*.txt') if '14_GUN' in x.name.upper()]
    seen=set()
    for fp in candidates:
        if str(fp) in seen or not fp.exists(): continue
        seen.add(str(fp))
        rows=parse_text(fp.read_text(encoding='utf-8-sig',errors='ignore'),'seed')
        if len(rows)==3038:
            # Dosyayı ayrıca 14x217 doğrula; yanlış 3038 satırı kabul etme.
            tmp=pd.DataFrame(rows,columns=['draw_id','draw_time','numbers','source'])
            tmp['date']=pd.to_datetime(tmp.draw_time).dt.strftime('%Y-%m-%d')
            if tmp.date.nunique()==14 and all(tmp.groupby('date').size()==217):
                import_rows(rows); df=get_draws()
                if not baseline(): build_baseline_from_seed(df)
                audit('AUTO_SEED_LOADED',{'file':fp.name,'rows':3038})
                return True, f'{fp.name} otomatik okundu: 3.038 çekiliş.'
    return False, 'Repo içinde doğrulanmış 14 gün × 217 = 3.038 çekilişlik TXT bulunamadı.'

def process_hour_block(txt):
    """Saatlik bloğu kronolojik işler. Her el, sonraki gerçek sonuç görülmeden önce mevcut durumdan simüle edilir.
    Bu mod saat sonunda toplu girildiğinde WALK-FORWARD REPLAY'dir; canlı ön-mühür değildir.
    """
    rows=parse_text(txt,'live')
    if not rows: raise ValueError('Bu metinden geçerli çekiliş okunamadı. Tarih-saat + çekiliş no + 20 sayı bulunamadı.')
    wrong=[r for r in rows if not r[1].startswith(LIVE_DAY)]
    if wrong:
        bad=', '.join(f'#{r[0]} {r[1]}' for r in wrong[:5])
        raise ValueError(f'15. gün yalnız 08.09.2026 olmalı. Farklı tarih bulundu: {bad}')
    results=[]
    newly_processed=[]
    for draw_id,dt,nstr,_ in rows:
        nums=list(map(int,nstr.split(',')))
        # Zaten kayıtlıysa tekrar işleme.
        with cx() as c:
            exists=c.execute('SELECT 1 FROM draws WHERE draw_id=? OR draw_time=?',(draw_id,dt)).fetchone()
        if exists:
            results.append({'draw_id':draw_id,'time':dt,'status':'zaten kayıtlı','hit':None}); continue
        dfpre=get_draws()
        # Replay mühürü: bu noktada yalnız geçmiş satırlar DB'dedir.
        pred,probs,pre,sm,sha=seal(dfpre,dt,1000)
        hit,a=settle(draw_id,dt,nums)
        newly_processed.append((draw_id,dt,nstr,'live'))
        results.append({'draw_id':draw_id,'time':dt,'status':'işlendi','hit':hit,'sha256':sha[:12],
                        'real_hot':a['hot'],'real_mid':a['mid'],'real_cold':a['cold'],'real_h1':a['h1']})
    gh=None
    if newly_processed:
        path,total=github_persist_live_rows(newly_processed)
        gh={'path':path,'total':total,'new':len(newly_processed)}
    return pd.DataFrame(results),gh

SEED_OK,SEED_MSG=ensure_seed_loaded()

# ---------- UI ----------
st.title('🧬 Hızlı On — RNG Dijital İkiz V2 — Tam Donanımlı Gözlem + Canlı Akort')
st.caption('Amaç: 14 günlük çıktı anatomisini modellemek; 15. günde her çekiliş öncesi mühür, gerçek sonuç sonrası fark analizi ve yalnız ileriye dönük akort.')

with st.sidebar:
    st.header('Ana hafıza')
    if SEED_OK: st.success(SEED_MSG)
    else: st.error(SEED_MSG)
    st.caption('14 günlük TXT GitHub/repo içinden otomatik okunur. Dosya yükleme yok.')
    if github_enabled(): st.success('GitHub kalıcı canlı kayıt: HAZIR ✓')
    else: st.warning('GitHub kalıcı kayıt için Secrets: GITHUB_TOKEN + GITHUB_REPO gerekli.')

df=get_draws()
if df.empty or not SEED_OK: st.error('Ana hafıza doğrulanamadı. Repo kökünde 3.038 çekilişlik 14 günlük TXT bulunmalı.'); st.stop()
seed=df[df.source=='seed']; live=df[df.source=='live']
c1,c2,c3,c4,c5=st.columns(5)
c1.metric('Toplam',len(df)); c2.metric('Seed',len(seed)); c3.metric('Canlı',len(live)); c4.metric('Gün',df.date.nunique()); c5.metric('Son',df.iloc[-1].draw_time)
if len(seed)==3038 and seed.date.nunique()==14 and all(seed.groupby('date').size()==217): st.success('14 gün × 217 = 3.038 başlangıç hafızası doğrulandı ✓')
else: st.warning('Seed veri kapısı henüz 3038/14×217 değil.')

tabs=st.tabs(['80 Sayı Yaşam','Anatomi Baseline','RNG-SIM','15. Gün Canlı','217-El Otopsi','Denetim'])
with tabs[0]:
    fs=feature_state(df); sc=score_state(fs).sort_values('rank')
    st.dataframe(sc,use_container_width=True,height=650)
    st.caption('HOT/MID/COLD yalnız o gün gerçekleşmiş çekilişlerle her el yeniden sıralanır. Geçmiş 14 gün kısa/orta hafıza ve baseline için kullanılır.')
with tabs[1]:
    b=baseline()
    if not b: st.info('Baseline kurmak için seed yükleme düğmesini kullan.')
    else:
        st.dataframe(pd.DataFrame([{'ölçü':k,'14_gün_ortalama':v} for k,v in b.items()]),use_container_width=True)
        st.markdown('**İzlenen mikro yapı:** sıcak/orta/soğuk bütçesi; H1; 20/21 ve 60/61 sınırı; yaş/dönüş; ardışık ve bir-atlamalı çift; 10’luk bant yoğunluğu; son-hane yoğunluğu. 3/6/12/17/24/36/72 el özellikleri 80 sayı tablosunda tutulur.')
with tabs[2]:
    fs=feature_state(df); sc=score_state(fs); b=baseline() or build_baseline_from_seed(df); prev=df.iloc[-1].nums
    ns=st.slider('Simülasyon',500,10000,2000,500)
    if st.button('Dijital ikizi simüle et'):
        probs,sm=simulate_many(sc,b,prev,ns); out=sc[['number','rank','group','score','f3','f6','f12','f17','f24','age','h1','boundary']].copy(); out['sim_p']=out.number.map(probs)
        st.write('Hedef anatomi',b); st.write('Simülasyon ortalaması',sm); st.dataframe(out.sort_values('sim_p',ascending=False),use_container_width=True)
with tabs[3]:
    st.subheader('15. Gün — 08.09.2026 — saatlik toplu giriş')
    st.caption('Sen 08.09.2026 tarihli 12 çekilişi tek seferde aynen yapıştırırsın. APP tarih/saat sırasına dizer; ### ve Detaylar linklerini yok sayar; içeride EL1→EL2→... tek tek walk-forward işler.')
    bulk=st.text_area('1 saatlik ham çekiliş bloğunu aynen yapıştır',height=420,placeholder='### Çekiliş no:\n### 55986\n15.09.2026-23:57\n5\n6\n...')
    if st.button('SAATLİK BLOĞU İŞLE → çekiliş çekiliş ilerle',type='primary'):
        try:
            rr,gh=process_hour_block(bulk)
            if gh:
                st.success(f"{len(rr)} çekiliş okundu ve işlendi. GitHub/{gh['path']} kalıcı kaydedildi ✓ (toplam {gh['total']})")
            else:
                st.success(f'{len(rr)} çekiliş okundu. Hepsi daha önce kayıtlıydı; tekrar yazılmadı.')
            st.dataframe(rr,use_container_width=True)
        except Exception as e: st.error(str(e))
    st.info('Not: Saat bittikten sonra 12 sonucu toplu yapıştırırsan bu bölüm kör walk-forward REPLAY yapar. Gerçek zamanlı ön-mühür için sonuç gelmeden önce RNG-SIM mühürü ayrıca kullanılmalıdır.')
    st.divider()
    st.subheader('İsteğe bağlı: gerçek zamanlı tek-el ön mühür')
    target=st.text_input('Bir sonraki hedef tarih-saat — YYYY-MM-DD HH:MM:SS')
    if st.button('Bir sonraki RNG-SIM 20’liyi mühürle'):
        if not target: st.error('Hedef zamanı gir.')
        else:
            pred,probs,pre,sm,sha=seal(get_draws(),target,2000)
            st.success('Mühür: '+sha); st.write('Üretilen 20:',pred)
with tabs[4]:
    det,agg=day_report()
    if det.empty: st.info('Henüz yerleşmiş canlı tahmin yok.')
    else:
        st.dataframe(agg,use_container_width=True); st.dataframe(det,use_container_width=True,height=500)
        st.download_button('Çekiliş-çekiliş otopsi CSV',det.to_csv(index=False).encode('utf-8-sig'),'rng_v2_cekilis_cekilis_otopsi.csv','text/csv')
        st.download_button('Gün sonu özet CSV',agg.to_csv(index=False).encode('utf-8-sig'),'rng_v2_gun_sonu_ozet.csv','text/csv')
with tabs[5]:
    with cx() as c: au=pd.read_sql_query('SELECT * FROM audit ORDER BY id DESC LIMIT 2000',c)
    st.dataframe(au,use_container_width=True,height=650)

st.caption('Bilimsel sınır: V2 gerçek RNG’nin gizli seed/algoritmasını bildiğini iddia etmez. Çıktı anatomisinin dijital ikizidir. Her canlı tahmin sonuçtan önce SHA-256 ile mühürlenir; akort yalnız sonuç geldikten sonra sonraki ele uygulanır.')
