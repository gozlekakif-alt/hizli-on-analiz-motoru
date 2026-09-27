import streamlit as st
import pandas as pd
import numpy as np
import json, zipfile, io, time
from pathlib import Path
from itertools import combinations
from collections import defaultdict

st.set_page_config(page_title="Hızlı On V3 — Gün Gün Motor", layout="wide")
st.title("🧬 Hızlı On V3 — Gün Gün Otomatik Motor Laboratuvarı")
st.caption("Bir seferde yalnız 1 gün • sonuç diske kaydolur • biten gün yeniden hesaplanmaz • 14 gün sonunda tek paket")

DATA="veri.txt"
STATE_DIR=Path(".hizli_on_v3")
STATE_DIR.mkdir(exist_ok=True)
D_END=pd.Timestamp("2026-08-31 23:59:59")

@st.cache_data(show_spinner=False)
def load_data(path):
    rows=[]
    with open(path,"r",encoding="utf-8-sig",errors="replace") as f:
        for ln in f:
            p=ln.strip().split(";")
            if len(p)<3: continue
            try:
                did=int(p[0]); dt=pd.to_datetime(p[1],dayfirst=True)
                nums=[int(x) for x in p[2].replace(" ","").split(",") if x]
                if len(nums)==20 and len(set(nums))==20:
                    rows.append((did,dt,nums))
            except: pass
    df=pd.DataFrame(rows,columns=["draw_id","dt","nums"]).sort_values("dt").reset_index(drop=True)
    X=np.zeros((len(df),81),dtype=np.uint8)
    for i,ns in enumerate(df.nums): X[i,ns]=1
    df["date"]=df.dt.dt.date
    df["period"]=np.where(df.dt<=D_END,"D","V")
    return df,X

if not Path(DATA).exists():
    up=st.file_uploader("veri.txt yükle",type="txt")
    if not up: st.stop()
    Path(DATA).write_bytes(up.getvalue())

df,X=load_data(DATA)
days=sorted(df.date.unique())
G10={f"{a:02d}-{a+9:02d}":list(range(a,a+10)) for a in range(1,81,10)}

def h(t,n,w): return int(X[max(0,t-w):t,n].sum())
def age(t,n):
    z=np.where(X[:t,n]==1)[0]
    return 999 if not len(z) else int(t-z[-1])
def patt(t,n,w=6):
    return "".join(map(str,X[max(0,t-w):t,n].astype(int).tolist())).rjust(w,"0")
def co(t,a,b,w):
    return int(np.sum(X[max(0,t-w):t,a]*X[max(0,t-w):t,b]))
def sig(m,t,cand,detail,score=1):
    cand=sorted(set(map(int,cand)))
    real=sorted(set(cand)&set(df.loc[t,"nums"]))
    return dict(motor=m,t=t,draw_id=int(df.loc[t,"draw_id"]),dt=str(df.loc[t,"dt"]),
                date=str(df.loc[t,"date"]),period=df.loc[t,"period"],
                candidates=",".join(map(str,cand)),n_candidates=len(cand),
                real=",".join(map(str,real)),n_real=len(real),detail=detail,score=float(score))

# ---------- individual motors ----------
def motors_for_draw(t):
    out=[]
    # 2/3 - 3/3
    if t>=3:
        cnt=X[t-3:t,1:].sum(0)
        for k in [2,3]:
            ns=np.where(cnt==k)[0]+1
            if len(ns): out.append(sig(f"AKTIF_{k}_3",t,ns,f"önceki 3 elde {k}/3",k))
    # H1-H8 carry
    if t>=12:
        for lag in range(1,9):
            ns=np.where(X[t-lag,1:]==1)[0]+1
            ns=[n for n in ns if h(t,n,12)>=3]
            if ns: out.append(sig(f"H{lag}_TASIMA",t,ns,f"t-{lag} ve H12>=3",1))
    # sleep/return
    if t>=24:
        ns=[n for n in range(1,81) if h(t,n,24)>=5 and h(t,n,6)<=1 and 3<=age(t,n)<=12]
        if ns: out.append(sig("UYKU_DONUS",t,ns,"H24>=5 H6<=1 AGE3..12",1))
    # rhythm exact repeated gap
    if t>=24:
        by=defaultdict(list)
        for n in range(1,81):
            z=np.where(X[t-24:t,n]==1)[0]
            if len(z)>=3:
                g=np.diff(z)
                if len(g)>=2 and g[-1]==g[-2] and 1<=g[-1]<=8 and age(t,n)==g[-1]:
                    by[int(g[-1])].append(n)
        for gap,ns in by.items(): out.append(sig(f"RITIM_{gap}",t,ns,f"iki eşit gap={gap}",1))
    # consecutive
    if t>=6:
        f=X[t-6:t,1:].sum(0); ns=set()
        for n in range(1,80):
            if f[n-1]>=2 and f[n]>=2: ns.update([n,n+1])
        if ns: out.append(sig("ARDISIK",t,ns,"H6 komşu çift yükü",1))
    # last digit
    if t>=12:
        for d in range(10):
            fam=[n for n in range(1,81) if n%10==d]
            load=sum(h(t,n,12) for n in fam)
            ns=[n for n in fam if age(t,n)<=6]
            if load>=30 and ns: out.append(sig(f"SON_HANE_{d}",t,ns,f"H12 yük={load}",1))
    # mirror
    if t>=12:
        ns=set()
        for n in range(1,41):
            m=81-n
            if h(t,n,6)>=2 and h(t,m,12)>=2 and age(t,m)>=2: ns.add(m)
            if h(t,m,6)>=2 and h(t,n,12)>=2 and age(t,n)>=2: ns.add(n)
        if ns: out.append(sig("AYNA_81",t,ns,"n↔81-n",1))
    # AB->A 011110
    if t>=14:
        ns=set(); pairs=0
        for b in range(1,81):
            if patt(t,b)!="011110" or not(X[t-2,b] and not X[t-1,b]): continue
            if int(X[t-12:t-6,b].sum())>2: continue
            for a in range(1,81):
                if a!=b and X[t-2,a] and X[t-1,a] and co(t,a,b,12)>=3:
                    ns.update([a,b]); pairs+=1
        if ns: out.append(sig("SOSYAL_AB_A",t,ns,f"{pairs} çift",2))
    # 8x10 pressure / handoff
    if t>=36:
        means12={g:float(X[t-12:t,nums].sum(1).mean()) for g,nums in G10.items()}
        means24={g:float(X[t-36:t-12,nums].sum(1).mean()) for g,nums in G10.items()}
        for g,nums in G10.items():
            d=means12[g]-means24[g]
            if d<=-.55:
                cand=[n for n in nums if h(t,n,24)>=3]
                if cand: out.append(sig("BASKI_"+g,t,cand,f"Δ={d:.2f}",abs(d)))
        for a,b in combinations(G10,2):
            da=means12[a]-means24[a]; db=means12[b]-means24[b]
            if da<=-.5 and db>=.5: out.append(sig("NOBET_"+a+"_TO_"+b,t,G10[b],f"{da:.2f}/{db:.2f}",abs(da)+abs(db)))
            elif db<=-.5 and da>=.5: out.append(sig("NOBET_"+b+"_TO_"+a,t,G10[a],f"{db:.2f}/{da:.2f}",abs(da)+abs(db)))
    # dynamic 4x20 temperature
    if t>=48:
        vals=[]
        for n in range(1,81):
            h6,h12,h48=h(t,n,6),h(t,n,12),h(t,n,48)
            old42=int(X[t-48:t-6,n].sum()); mom=h6-old42/7
            vals.append((n,h48,h12,h6,age(t,n),mom))
        vals.sort(key=lambda r:(-r[1],-r[2],-r[3],r[4],r[0]))
        top,bot=vals[:40],vals[40:]
        stc=set(r[0] for r in sorted(top,key=lambda r:(r[5],r[0]))[:20])
        cts=set(r[0] for r in sorted(bot,key=lambda r:(-r[5],r[0]))[:20])
        hot=set(r[0] for r in top)-stc; cold=set(r[0] for r in bot)-cts
        for name,ns in [("SICAK20",hot),("SICAKTAN_SOGUK20",stc),("SOGUK20",cold),("SOGUKTAN_SICAK20",cts)]:
            out.append(sig("ISI_"+name,t,ns,name,1))
    return out

def day_file(day): return STATE_DIR/f"day_{day}.csv"
def done_days(): return [d for d in days if day_file(d).exists()]

def analyze_one_day(day, progress=None):
    ids=df.index[df.date==day].tolist()
    rows=[]
    total=len(ids)
    for j,t in enumerate(ids):
        rows.extend(motors_for_draw(t))
        if progress and (j%5==0 or j==total-1): progress.progress((j+1)/total,text=f"{day} • {j+1}/{total} çekiliş")
    out=pd.DataFrame(rows)
    out.to_csv(day_file(day),index=False,encoding="utf-8-sig")
    return out

def load_all_results():
    parts=[]
    for d in done_days():
        try: parts.append(pd.read_csv(day_file(d)))
        except: pass
    return pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()

def make_package():
    allr=load_all_results()
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("TUM_14_GUN_MOTOR_SINYALLERI.csv",allr.to_csv(index=False))
        if not allr.empty:
            k=allr.groupby(["motor","period"]).agg(tetik=("draw_id","count"),aday=("n_candidates","sum"),real=("n_real","sum")).reset_index()
            k["aday_hit"]=k.real/k.aday.replace(0,np.nan)
            z.writestr("MOTOR_KARNESI_DV.csv",k.to_csv(index=False))
            g=allr.groupby(["date","motor"]).agg(tetik=("draw_id","count"),aday=("n_candidates","sum"),real=("n_real","sum")).reset_index()
            z.writestr("GUN_GUN_MOTOR_KARNESI.csv",g.to_csv(index=False))
        for d in done_days():
            z.write(day_file(d),arcname=f"gunler/{day_file(d).name}")
    bio.seek(0); return bio.getvalue()

# ---------- state ----------
if "auto" not in st.session_state: st.session_state.auto=False

done=done_days()
next_day=next((d for d in days if d not in done),None)
c1,c2,c3,c4=st.columns(4)
c1.metric("Tamamlanan gün",f"{len(done)}/{len(days)}")
c2.metric("Son tamamlanan",str(done[-1]) if done else "-")
c3.metric("Sıradaki",str(next_day) if next_day else "TAMAM")
c4.metric("Mod","OTOMATİK" if st.session_state.auto else "BEKLİYOR")

st.progress(len(done)/max(1,len(days)),text=f"14 günlük genel ilerleme: {len(done)}/{len(days)}")

a,b,c=st.columns(3)
if a.button("▶️ Otomatik analizi başlat / devam",use_container_width=True):
    st.session_state.auto=True
if b.button("⏸️ Gün sonunda durdur",use_container_width=True):
    st.session_state.auto=False
if c.button("🗑️ Analizi sıfırla",use_container_width=True):
    for f in STATE_DIR.glob("day_*.csv"): f.unlink(missing_ok=True)
    st.session_state.auto=False
    st.rerun()

# Process EXACTLY ONE day per script run, save, then rerun.
# This prevents one monolithic 14-day Python loop from holding the page.
if st.session_state.auto and next_day is not None:
    st.info(f"Şimdi yalnız **{next_day}** analiz ediliyor. Bitince dosyaya kaydedilecek ve sonraki güne geçilecek.")
    pr=st.progress(0,text="Gün hazırlanıyor")
    analyze_one_day(next_day,pr)
    pr.empty()
    time.sleep(.15)
    st.rerun()

if next_day is None:
    st.success("✅ 14 günün tamamı analiz edildi.")
    st.session_state.auto=False

# ---------- results already persisted ----------
R=load_all_results()
tabs=st.tabs(["Günler","Motor Karnesi","Ham Sinyaller","Tek Paket İndir"])
with tabs[0]:
    status=pd.DataFrame({"Gün":[str(d) for d in days],
                         "Durum":["✅ TAMAM" if d in done else ("▶ SIRADA" if d==next_day else "⏳") for d in days]})
    st.dataframe(status,use_container_width=True,hide_index=True)
with tabs[1]:
    if not R.empty:
        k=R.groupby(["motor","period"]).agg(tetik=("draw_id","count"),aday=("n_candidates","sum"),real=("n_real","sum")).reset_index()
        k["aday_hit"]=k.real/k.aday.replace(0,np.nan)
        st.dataframe(k.round(4),use_container_width=True,height=550)
    else: st.caption("Henüz tamamlanmış gün yok.")
with tabs[2]:
    if not R.empty: st.dataframe(R.tail(2000),use_container_width=True,height=550)
    else: st.caption("Henüz sinyal kaydı yok.")
with tabs[3]:
    if len(done):
        st.download_button("📦 Şu ana kadarki TÜM sonuçları tek ZIP indir",
                           make_package(),"HIZLI_ON_14_GUN_TUM_ANALIZ.zip","application/zip",
                           use_container_width=True)
        if len(done)<len(days): st.caption(f"Paket şu an {len(done)} tamamlanmış günü içeriyor. 14/14 olduğunda tam araştırma paketidir.")
