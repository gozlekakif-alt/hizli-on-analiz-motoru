import streamlit as st
import pandas as pd
import sqlite3, re, math
from itertools import combinations
from pathlib import Path
from collections import Counter, defaultdict

st.set_page_config(page_title='Hızlı On Uzman Ana Beyin', layout='wide')
BASE=Path(__file__).resolve().parent
DB=BASE/'hizli_on_v3.db'
SEED=BASE/'14_GUN_3038_CEKILIS.txt'
BANDS=[(1,10),(11,20),(21,30),(31,40),(41,50),(51,60),(61,70),(71,80)]

# ---------- DATA ----------
def con(): return sqlite3.connect(DB)
def init_db():
    c=con()
    c.execute('CREATE TABLE IF NOT EXISTS draws(draw_id INTEGER PRIMARY KEY, draw_time TEXT NOT NULL, numbers TEXT NOT NULL)')
    c.execute('''CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY AUTOINCREMENT,target_draw_id INTEGER,engine TEXT,ticket_no INTEGER,numbers TEXT,checked INTEGER DEFAULT 0,hits INTEGER DEFAULT 0,matched TEXT DEFAULT '',UNIQUE(target_draw_id,engine,ticket_no))''')
    c.commit(); c.close()

def parse_nums(x): return [int(v.strip()) for v in str(x).split(',') if v.strip()]
def seed_data():
    if not SEED.exists(): return False,'14_GUN_3038_CEKILIS.txt bulunamadı'
    rows=[]
    try:
        for line in SEED.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip(): continue
            p=[x.strip() for x in line.split(';')]
            ns=parse_nums(p[2])
            if len(p)!=3 or len(ns)!=20 or len(set(ns))!=20 or any(not 1<=n<=80 for n in ns): raise ValueError('bozuk satır')
            rows.append((int(p[0]),p[1],ns))
    except Exception as e: return False,f'Ana veri okunamadı: {e}'
    if len(rows)!=3038: return False,f'Ana veri 3038 değil: {len(rows)}'
    dates=pd.to_datetime([r[1] for r in rows],dayfirst=True,errors='coerce')
    vc=pd.Series([x.date() for x in dates if not pd.isna(x)]).value_counts()
    if dates.isna().any() or len(vc)!=14 or not (vc==217).all(): return False,'14 gün × 217 kilidi geçmedi'
    c=con()
    for did,dt,ns in rows: c.execute('INSERT OR IGNORE INTO draws VALUES(?,?,?)',(did,dt,','.join(map(str,ns))))
    c.commit(); c.close(); return True,'ANA HAFIZA 3038/3038 | 14×217 ✓'

def load_draws():
    c=con(); d=pd.read_sql_query('SELECT * FROM draws ORDER BY draw_id',c); c.close()
    if d.empty: return pd.DataFrame(columns=['draw_id','draw_time','numbers','Sayilar','date'])
    d['Sayilar']=d['numbers'].map(parse_nums); d['draw_time']=pd.to_datetime(d['draw_time'],dayfirst=True,errors='coerce')
    d=d.dropna(subset=['draw_time']).sort_values(['draw_time','draw_id']).reset_index(drop=True); d['date']=d.draw_time.dt.date
    return d

def parse_natural(text):
    blocks=re.split(r'(?=Çekiliş\s*no\s*:)',text.strip(),flags=re.I); out=[]; errs=[]
    for b in blocks:
        if not b.strip(): continue
        try:
            mid=re.search(r'Çekiliş\s*no\s*:\s*(\d+)',b,re.I); mdt=re.search(r'(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})',b)
            if not mid or not mdt: raise ValueError('çekiliş no/tarih bulunamadı')
            ns=[int(x) for x in re.findall(r'(?<!\d)(\d{1,2})(?!\d)',b[mdt.end():])]
            if len(ns)!=20 or len(set(ns))!=20 or any(not 1<=n<=80 for n in ns): raise ValueError(f'20 benzersiz sayı bekleniyor, {len(ns)} bulundu')
            out.append((int(mid.group(1)),f'{mdt.group(1)} {mdt.group(2)}',ns))
        except Exception as e: errs.append(str(e))
    return out,errs

def add_draws(text):
    rows,errs=parse_natural(text)
    if errs or not rows: return 0,errs or ['çekiliş okunamadı']
    c=con(); n=0
    for did,dt,ns in rows:
        cur=c.execute('INSERT OR IGNORE INTO draws VALUES(?,?,?)',(did,dt,','.join(map(str,ns)))); n+=cur.rowcount
    c.commit(); c.close(); return n,[]

# ---------- PRE-H LIFE ----------
def current_day(d): return d[d.date==d.iloc[-1].date].reset_index(drop=True) if not d.empty else d
def age_map(day):
    out={}
    for n in range(1,81):
        out[n]=next((len(day)-j for j in range(len(day)-1,-1,-1) if n in day.iloc[j].Sayilar),None)
    return out
def src(age):
    if age==1:return 'H1'
    if age in (2,3):return 'SHORT'
    if age in (4,5,6):return 'MID'
    if age is not None and 7<=age<=12:return 'LONG'
    if age is not None and age>=13:return 'DEEP'
    return 'DAY_UNSEEN'
def hbit(day,n,k): return int(len(day)>=k and n in day.iloc[-k].Sayilar)
def last_gaps(day,n):
    ix=[i for i,r in day.iterrows() if n in r.Sayilar]
    return [ix[i]-ix[i-1] for i in range(len(ix)-3,len(ix))] if len(ix)>=4 else []
def rhythms(day,n,age):
    H=lambda k:hbit(day,n,k); rr=[]
    if len(day)>=12 and H(12) and H(8) and H(4) and all(not H(k) for k in [11,10,9,7,6,5,3,2,1]): rr.append('R1')
    if len(day)>=12 and H(6) and H(4) and H(2) and all(not H(k) for k in [12,11,10,9,8,7,5,3,1]): rr.append('R2')
    g=last_gaps(day,n)
    if g==[1,4,1] and age==4: rr.append('R3')
    if g==[1,2,1] and age in (7,8,9): rr.append('R4')
    return rr

# ---------- V30/V31 SOURCE SEAT EXPERT ----------
def source_supply(day):
    am=age_map(day); c=Counter(src(a) for a in am.values()); return am,c

def seat_expert(day):
    am,sup=source_supply(day); observed=len(day)
    # TEST baselines from locked research
    seats={'H1':4.96,'SHORT':6.56,'MID':4.86,'LONG':3.02,'DEEP':0.60}
    state={'H1':'OWN','SHORT':'WAIT','MID':'WAIT','LONG':'WAIT','DEEP':'WAIT'}
    # Only call a layer when that H horizon can actually exist in the day.
    if observed>=3:
        state['SHORT']='HIGH' if sup['SHORT']>=28 else ('LOW' if sup['SHORT']<=25 else 'MID')
        seats['SHORT']={'HIGH':7.28,'LOW':5.93,'MID':6.63}[state['SHORT']]
    if observed>=6:
        state['MID']='HIGH' if sup['MID']>=21 else ('LOW' if sup['MID']<=18 else 'MID')
        seats['MID']={'HIGH':5.62,'LOW':4.07,'MID':4.87}[state['MID']]
    if observed>=12:
        state['LONG']='HIGH' if sup['LONG']>=13 else ('LOW' if sup['LONG']<=10 else 'MID')
        seats['LONG']={'HIGH':3.53,'LOW':2.12,'MID':2.97}[state['LONG']]
    if observed>=13:
        state['DEEP']='HIGH' if sup['DEEP']>=3 else 'LOW'
        seats['DEEP']={'HIGH':0.93,'LOW':0.32}[state['DEEP']]
    # H1 independent: never residual. Keep its own baseline, mild team evidence handled later.
    # Normalize only displayed expected seats to 20 while retaining independent H1.
    total=sum(seats.values()); seats={k:v*20/total for k,v in seats.items()}
    ints={k:int(math.floor(v)) for k,v in seats.items()}; left=20-sum(ints.values())
    for k,_ in sorted(seats.items(),key=lambda kv:kv[1]-math.floor(kv[1]),reverse=True)[:left]: ints[k]+=1
    return am,sup,state,seats,ints

# ---------- BAND / REGION SHAPE EXPERT ----------
def band_counts(ns): return tuple(sum(1 for n in ns if lo<=n<=hi) for lo,hi in BANDS)
def band_name(i): return f'{BANDS[i][0]:02d}-{BANDS[i][1]:02d}'
def band_expert(d):
    if len(d)<2: return [2.5]*8,[],0
    cur=band_counts(d.iloc[-1].Sayilar); hist=[]
    # nearest PRE-H geometries -> next draw shape, same-day transitions only
    for i in range(len(d)-1):
        if d.iloc[i].date!=d.iloc[i+1].date: continue
        x=band_counts(d.iloc[i].Sayilar); y=band_counts(d.iloc[i+1].Sayilar)
        dist=sum(abs(x[j]-cur[j]) for j in range(8))
        hist.append((dist,i,y))
    hist.sort(key=lambda z:(z[0],-z[1])); near=hist[:80]
    if not near: return [2.5]*8,[],0
    weights=[1/(1+x[0]) for x in near]; sw=sum(weights)
    pred=[sum(w*r[2][j] for w,r in zip(weights,near))/sw for j in range(8)]
    # exact integer 20 seats
    ints=[int(math.floor(x)) for x in pred]; left=20-sum(ints)
    for j in sorted(range(8),key=lambda j:pred[j]-math.floor(pred[j]),reverse=True)[:left]: ints[j]+=1
    return pred,ints,len(near)

# ---------- TEAM / NETWORK / PROTECT ----------
def pair_carry(d,lookback=300):
    z=d.tail(lookback).reset_index(drop=True); pc=Counter()
    for i in range(1,len(z)):
        common=sorted(set(z.iloc[i-1].Sayilar)&set(z.iloc[i].Sayilar))
        for p in combinations(common,2): pc[p]+=1
    return pc

def transition_number_lift(d,n,band_idx):
    # number-specific conditional appearance after similar band occupancy; not raw hot frequency
    if len(d)<3:return 0.0
    cur=band_counts(d.iloc[-1].Sayilar); hits=tot=0
    for i in range(len(d)-1):
        if d.iloc[i].date!=d.iloc[i+1].date: continue
        x=band_counts(d.iloc[i].Sayilar)
        if sum(abs(x[j]-cur[j]) for j in range(8))<=6:
            tot+=1; hits+=int(n in d.iloc[i+1].Sayilar)
    return (hits/tot-.25) if tot>=20 else 0.0

def build_brain(d):
    day=current_day(d); am,sup,state,seats,seat_int=seat_expert(day); bp,bi,bn=band_expert(d); pc=pair_carry(d)
    last=set(d.iloc[-1].Sayilar); rows=[]
    for n in range(1,81):
        a=am[n]; so=src(a); rr=rhythms(day,n,a); b=(n-1)//10
        team=sum(pc[tuple(sorted((n,m)))] for m in last if m!=n) if n in last else 0
        # score = life + verified specialist signals + predicted band demand. No raw frequency selector.
        base={'H1':1.25,'SHORT':1.20,'MID':1.05,'LONG':.85,'DEEP':.55,'DAY_UNSEEN':.35}[so]
        s=base + .32*bp[b]
        why=[so,f'BAND {band_name(b)}≈{bp[b]:.1f}']
        if rr: s+=1.45*len(rr); why+=rr
        if hbit(day,n,6): s+=.35; why.append('+6')
        if team: s+=min(1.35,team/45); why.append(f'V33:{team}')
        lift=transition_number_lift(d,n,b)
        if lift>0: s+=min(.7,lift*2.5); why.append('BANT_GEÇİŞ+')
        # source-state preference, only when observable
        if so in state and state[so]=='HIGH': s+=.45; why.append(f'{so}_HIGH')
        if so in state and state[so]=='LOW': s-=.20; why.append(f'{so}_LOW')
        rows.append((n,a,so,','.join(rr) or '-',band_name(b),team,round(s,3),' | '.join(why)))
    all80=pd.DataFrame(rows,columns=['Sayı','H yaşı','Kaynak','Ritim','Bant','V33 takım','Skor','Neden'])
    # constrained 20 pool: honor predicted band seats and approximate source seats, while allowing best signals
    chosen=[]; band_used=Counter(); source_used=Counter()
    ranked=all80.sort_values(['Skor','V33 takım','Sayı'],ascending=[False,False,True]).to_dict('records')
    for r in ranked:
        bidx=(r['Sayı']-1)//10; so=r['Kaynak']; target_band=bi[bidx] if bi else 3
        target_src=seat_int.get(so,99) if so!='DAY_UNSEEN' else 99
        if band_used[bidx]<target_band and source_used[so]<target_src:
            chosen.append(r); band_used[bidx]+=1; source_used[so]+=1
        if len(chosen)==20: break
    # fill any shortage by score + band capacity
    if len(chosen)<20:
        have={r['Sayı'] for r in chosen}
        for r in ranked:
            if r['Sayı'] in have: continue
            bidx=(r['Sayı']-1)//10; target_band=bi[bidx] if bi else 3
            if band_used[bidx]<target_band:
                chosen.append(r); have.add(r['Sayı']); band_used[bidx]+=1
            if len(chosen)==20: break
    pool=pd.DataFrame(chosen)
    return pool,all80,(sup,state,seats,seat_int),(bp,bi,bn)

def make_tickets(pool):
    rec=pool.to_dict('records'); used=Counter(); out=[]
    for k in range(3):
        cp=[]; bands=Counter()
        while len(cp)<4:
            cand=[r for r in rec if r['Sayı'] not in cp]
            pick=max(cand,key=lambda r:r['Skor']-.38*used[r['Sayı']]-.20*bands[r['Bant']])
            cp.append(pick['Sayı']); used[pick['Sayı']]+=1; bands[pick['Bant']]+=1
        out.append(sorted(cp))
    return out

# User-supplied V33+V30 producer, kept separate and free to choose its own numbers.
def user_engine(d,all80):
    if len(d)<6:return 'YETERSİZ',[],[]
    last=set(d.iloc[-1].Sayilar); pc=pair_carry(d,100); teams=[]
    for tri in combinations(sorted(last),3): teams.append((sum(pc[p] for p in combinations(tri,2)),tri))
    teams.sort(reverse=True); team=list(teams[0][1]) if teams and teams[0][0]>0 else []
    short=(set(d.iloc[-2].Sayilar)|set(d.iloc[-3].Sayilar))-last
    mid=(set(d.iloc[-4].Sayilar)|set(d.iloc[-5].Sayilar)|set(d.iloc[-6].Sayilar))-last-short
    if len(short)>=28 or len(mid)<=18: regime,cand='SHORT_HIGH',short
    elif len(mid)>=21 or len(short)<=25: regime,cand='MID_HIGH',mid
    else: regime,cand='NEUTRAL',short|mid
    score=dict(zip(all80['Sayı'],all80['Skor'])); cand=sorted(cand,key=lambda n:(score.get(n,0),-n),reverse=True)
    tickets=[]
    if len(team)==3:
        for n in cand:
            if n not in team: tickets.append(sorted(team+[n]))
            if len(tickets)==3:break
    return regime,team,tickets

def save_tickets(target,engine,tickets):
    c=con()
    for i,cp in enumerate(tickets,1): c.execute('INSERT OR IGNORE INTO tickets(target_draw_id,engine,ticket_no,numbers) VALUES(?,?,?,?)',(target,engine,i,','.join(map(str,cp))))
    c.commit(); c.close()
def check_tickets():
    c=con(); rows=c.execute('SELECT t.id,t.numbers,d.numbers FROM tickets t JOIN draws d ON d.draw_id=t.target_draw_id WHERE t.checked=0').fetchall()
    for tid,cp,real in rows:
        hit=sorted(set(parse_nums(cp))&set(parse_nums(real))); c.execute('UPDATE tickets SET checked=1,hits=?,matched=? WHERE id=?',(len(hit),','.join(map(str,hit)),tid))
    c.commit(); c.close()
def results():
    c=con(); r=pd.read_sql_query("SELECT target_draw_id Hedef,engine Motor,ticket_no Kolon,numbers Sayılar,hits Isabet,matched Tutanlar FROM tickets WHERE checked=1 ORDER BY target_draw_id DESC,id DESC LIMIT 30",c); c.close()
    if not r.empty:r['Sonuç']=r.Isabet.astype(str)+'/4'
    return r

# ---------- UI ----------
init_db(); ok,msg=seed_data(); check_tickets(); d=load_draws()
st.title('🧠 Hızlı On — Uzman Ana Beyin')
st.caption('El şekli → bant/bölge → V30/V31 koltuk → R1–R4 → +6 → V33 takım → 20’lik havuz → 3×4 | ayrı kod motoru 3×4')
if not ok: st.error(msg); st.stop()
st.success(msg)

st.subheader('➕ Yeni çekiliş / aynı ekranda kontrol ve yeni tahmin')
text=st.text_area('Çekilişi yapıştır',height=210,placeholder='''Çekiliş no: 54251\n08.09.2026 - 00:02\n3\n7\n10\n... toplam 20 sayı''')
if st.button('EKLE → ESKİ KOLONLARI KONTROL ET → YENİ ELİ ÜRET',type='primary',use_container_width=True):
    n,err=add_draws(text)
    if err: st.error(' | '.join(err))
    else:
        check_tickets(); st.success(f'{n} yeni çekiliş eklendi.'); st.rerun()

if d.empty: st.stop()
target=int(d.iloc[-1].draw_id)+1
pool,all80,seatinfo,bandinfo=build_brain(d); sup,state,seats,seat_int=seatinfo; bp,bi,bn=bandinfo
main=make_tickets(pool); regime,team,other=user_engine(d,all80)
save_tickets(target,'ANA_BEYIN',main); save_tickets(target,'KOD_MOTORU',other)

st.subheader(f'🔮 Yeni el tahmini — hedef #{target}')
c1,c2=st.columns(2)
with c1:
    st.markdown('**V30/V31 — 20 koltuk kaynak geometrisi**')
    sdf=pd.DataFrame([{'Kaynak':k,'Arz':sup.get(k,0),'Durum':state.get(k,'-'),'Tahmini koltuk':seat_int[k],'Beklenti':round(seats[k],2)} for k in ['H1','SHORT','MID','LONG','DEEP']])
    st.dataframe(sdf,use_container_width=True,hide_index=True)
with c2:
    st.markdown('**Bant/Bölge Uzmanı — gelecek REAL20 şekli**')
    bdf=pd.DataFrame([{'Bant':band_name(i),'Son el':band_counts(d.iloc[-1].Sayilar)[i],'Tahmini koltuk':bi[i] if bi else '-','Beklenti':round(bp[i],2)} for i in range(8)])
    st.dataframe(bdf,use_container_width=True,hide_index=True)
    st.caption(f'Benzer geçmiş PRE-H geometri örneği: {bn}')

st.subheader('🎯 ANA BEYİN — 3×4')
cols=st.columns(3)
for i,cp in enumerate(main): cols[i].success(f'ANA {i+1}: '+', '.join(map(str,cp)))
st.subheader('🧩 Gönderdiğin V33 + V30 kod motoru — 3×4')
st.caption(f'Rejim: {regime} | H1 takım: {team or "sinyal yok"}')
cols=st.columns(3)
for i in range(3):
    if i<len(other): cols[i].info(f'KOD {i+1}: '+', '.join(map(str,other[i])))
    else: cols[i].warning(f'KOD {i+1}: güçlü sinyal yok — abstain')

st.subheader('🧬 ANA BEYİN 20’lik REAL aday havuzu')
st.write(' • '.join(f"{int(n):02d}" for n in pool['Sayı'].tolist()))
st.dataframe(pool[['Sayı','H yaşı','Kaynak','Ritim','Bant','V33 takım','Skor','Neden']],use_container_width=True,hide_index=True)

st.subheader('📊 Önceki kolonlar kaç/4 tuttu?')
r=results()
if r.empty: st.info('Henüz sonucu gelmiş takip edilen kolon yok.')
else: st.dataframe(r[['Hedef','Motor','Kolon','Sayılar','Sonuç','Tutanlar']],use_container_width=True,hide_index=True)

with st.expander('80 sayının uzman raporu'):
    st.dataframe(all80,use_container_width=True,hide_index=True)
