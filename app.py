import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from itertools import combinations
from collections import defaultdict, Counter

st.set_page_config(page_title="Hızlı On V2 — Otomatik Motor Laboratuvarı", layout="wide")
st.title("🧬 Hızlı On V2 — 14 Gün Otomatik Motor Laboratuvarı")
st.caption("Gün gün yürütme • geçmiş hafızası korunur • PRE-H • ~100 mikro-pencere/gün • motorlar ayrı • birleşim en sonda")

DATA_FILE="veri.txt"
D_END=pd.Timestamp("2026-08-31 23:59:59")

# ---------------- DATA ----------------
@st.cache_data(show_spinner=False)
def load_data(path):
    rows=[]
    with open(path,"r",encoding="utf-8-sig",errors="replace") as f:
        for line in f:
            line=line.strip()
            if not line or ";" not in line: continue
            p=line.split(";")
            if len(p)<3: continue
            try:
                did=int(p[0]); dt=pd.to_datetime(p[1],dayfirst=True)
                nums=[int(x) for x in p[2].replace(" ","").split(",") if x]
                if len(nums)==20 and len(set(nums))==20 and min(nums)>=1 and max(nums)<=80:
                    rows.append((did,dt,nums))
            except: pass
    df=pd.DataFrame(rows,columns=["draw_id","dt","nums"]).sort_values("dt").reset_index(drop=True)
    if df.empty: return df,None
    X=np.zeros((len(df),81),dtype=np.uint8)
    for i,ns in enumerate(df.nums): X[i,ns]=1
    df["date"]=df.dt.dt.date
    df["time"]=df.dt.dt.strftime("%H:%M")
    df["period"]=np.where(df.dt<=D_END,"D","V")
    return df,X

def find_data():
    for p in [Path(DATA_FILE),Path.cwd()/DATA_FILE]:
        if p.exists(): return str(p)
    return None

path=find_data()
upload=st.sidebar.file_uploader("veri.txt (repo içinde yoksa)",type=["txt"])
if upload:
    Path("veri_uploaded.txt").write_bytes(upload.getvalue()); path="veri_uploaded.txt"
if not path:
    st.error("veri.txt bulunamadı. GitHub/Streamlit reposunda app ile aynı klasöre veri.txt koy.")
    st.stop()

df,X=load_data(path)
if df.empty:
    st.error("Veri okunamadı.")
    st.stop()

G20={"A 1-20":list(range(1,21)),"B 21-40":list(range(21,41)),
     "C 41-60":list(range(41,61)),"D 61-80":list(range(61,81))}
G10={f"{a:02d}-{a+9:02d}":list(range(a,a+10)) for a in range(1,81,10)}
G5={f"{a:02d}-{a+4:02d}":list(range(a,a+5)) for a in range(1,81,5)}

def gc(groups):
    z=pd.DataFrame(index=df.index)
    for k,v in groups.items(): z[k]=X[:,v].sum(1)
    return z
C20,C10,C5=gc(G20),gc(G10),gc(G5)

def h(t,n,w): return int(X[max(0,t-w):t,n].sum())
def age(t,n):
    z=np.where(X[:t,n]==1)[0]
    return 999 if not len(z) else int(t-z[-1])
def pattern(t,n,w=6):
    s=max(0,t-w)
    return "".join(map(str,X[s:t,n].astype(int).tolist())).rjust(w,"0")
def co(t,a,b,w,exclude_last=0):
    e=max(0,t-exclude_last); s=max(0,e-w)
    return int(np.sum(X[s:e,a]*X[s:e,b]))
def region_of(n,size=10):
    a=((n-1)//size)*size+1
    return f"{a:02d}-{a+size-1:02d}"

# ---------------- MICRO WINDOWS ----------------
def micro_windows(day_idx,window=24,step=2):
    idx=np.array(list(day_idx))
    out=[]
    if len(idx)<window:return pd.DataFrame()
    for s in range(0,len(idx)-window+1,step):
        ids=idx[s:s+window]
        out.append((ids[0],ids[-1],df.loc[ids[0],"dt"],df.loc[ids[-1],"dt"]))
    return pd.DataFrame(out,columns=["start_i","end_i","start","end"])

# ---------------- MOTOR HELPERS ----------------
def signal(name,t,candidates,detail,score=1.0):
    cand=sorted(set(int(x) for x in candidates if 1<=int(x)<=80))
    real=sorted(set(cand)&set(df.loc[t,"nums"]))
    return {"motor":name,"t":t,"draw_id":int(df.loc[t,"draw_id"]),"dt":df.loc[t,"dt"],
            "date":df.loc[t,"date"],"period":df.loc[t,"period"],
            "candidates":cand,"n_candidates":len(cand),"real":real,"n_real":len(real),
            "detail":detail,"score":float(score)}

def dynamic_temperature(t):
    if t<48:return {}
    vals=[]
    for n in range(1,81):
        h6=h(t,n,6); h12=h(t,n,12); h48=h(t,n,48)
        old42=int(X[t-48:t-6,n].sum())
        mom=h6-old42/7.0
        vals.append((n,h48,h12,h6,age(t,n),mom))
    vals=sorted(vals,key=lambda r:(-r[1],-r[2],-r[3],r[4],r[0]))
    top=vals[:40]; bot=vals[40:]
    top_sorted=sorted(top,key=lambda r:(r[5],r[0]))
    bot_sorted=sorted(bot,key=lambda r:(-r[5],r[0]))
    stc={r[0] for r in top_sorted[:20]}
    hot={r[0] for r in top if r[0] not in stc}
    cts={r[0] for r in bot_sorted[:20]}
    cold={r[0] for r in bot if r[0] not in cts}
    return {"SICAK20":hot,"SICAKTAN_SOGUK20":stc,"SOGUK20":cold,"SOGUKTAN_SICAK20":cts}

def motor_temperature(t):
    if t<48:return []
    g=dynamic_temperature(t); out=[]
    for name,nums in g.items():
        out.append(signal("ISI_"+name,t,nums,f"Dinamik 20'lik grup: {name}",1))
    return out

def motor_hcarry(t):
    if t<12:return []
    out=[]
    # H1-H8: exact previous lag carry/return candidate sets
    for lag in range(1,9):
        if t<lag:continue
        nums=np.where(X[t-lag,1:]==1)[0]+1
        # score favors numbers also seen in last12
        cand=[n for n in nums if h(t,n,12)>=3]
        if cand: out.append(signal(f"H{lag}_TASIMA",t,cand,f"t-{lag} görüldü ve H12>=3",lag))
    return out

def motor_rhythm(t):
    if t<24:return []
    out=[]
    for n in range(1,81):
        seq=np.where(X[max(0,t-24):t,n]==1)[0]
        if len(seq)<3:continue
        gaps=np.diff(seq)
        if len(gaps)>=2 and gaps[-1]==gaps[-2] and 1<=gaps[-1]<=8:
            due=int(gaps[-1])
            if age(t,n)==due:
                out.append((n,due))
    if not out:return []
    by=defaultdict(list)
    for n,d in out:by[d].append(n)
    return [signal(f"RITIM_GAP_{d}",t,ns,f"Son iki aralık={d}, AGE={d}",d) for d,ns in by.items()]

def motor_consecutive(t):
    if t<6:return []
    # PRE-H: numbers adjacent to active recent numbers, plus repeated consecutive families
    freq=np.sum(X[max(0,t-6):t,1:],axis=0)
    cand=set()
    for n in range(1,80):
        if freq[n-1]>=2 and freq[n]>=2:
            cand.update([n,n+1])
    return [signal("ARDISIK_BLOK",t,cand,"H6 içinde komşu iki sayı >=2 kez aktif",1)] if cand else []

def motor_lastdigit(t):
    if t<12:return []
    fam=defaultdict(list)
    for n in range(1,81): fam[n%10].append(n)
    out=[]
    for d,ns in fam.items():
        load=sum(h(t,n,12) for n in ns)
        if load>=30:
            cand=[n for n in ns if age(t,n)<=6]
            if cand:out.append(signal(f"SON_HANE_{d}",t,cand,f"H12 aile yükü={load}",load))
    return out

def motor_age_sleep(t):
    if t<24:return []
    # transition: historically active but currently sleeping
    cand=[]
    for n in range(1,81):
        if h(t,n,24)>=5 and h(t,n,6)<=1 and 3<=age(t,n)<=12:cand.append(n)
    return [signal("UYKU_DONUS",t,cand,"H24>=5, H6<=1, AGE 3..12",1)] if cand else []

def motor_mirror(t):
    if t<12:return []
    # mirror around 81: n <-> 81-n; recent asymmetric activation
    cand=set()
    for n in range(1,41):
        m=81-n
        if h(t,n,6)>=2 and h(t,m,12)>=2 and age(t,m)>=2:cand.add(m)
        if h(t,m,6)>=2 and h(t,n,12)>=2 and age(t,n)>=2:cand.add(n)
    return [signal("AYNA_81",t,cand,"n ↔ 81-n PRE-H karşılıklı aktivasyon",1)] if cand else []

def motor_social_ab(t):
    if t<14:return []
    cand=set(); pairs=[]
    # exact AB -> A and missing B 011110, CO12>=3, old6<=2
    for b in range(1,81):
        if pattern(t,b,6)!="011110":continue
        if not (X[t-2,b]==1 and X[t-1,b]==0):continue
        old6=int(X[t-12:t-6,b].sum())
        if old6>2:continue
        for a in range(1,81):
            if a==b:continue
            if X[t-2,a] and X[t-1,a] and co(t,a,b,12)>=3:
                cand.update([a,b]);pairs.append(f"{a}-{b}")
    return [signal("SOSYAL_AB_A_011110",t,cand,f"{len(pairs)} yönlü çift; "+",".join(pairs[:12]),2)] if cand else []

def lag_score(t,a,b,lag,W=24):
    s=t-2-W;e=t-2
    if s<0:return np.nan
    if lag>=0:
        aa=X[s:e-lag if lag else e,a];bb=X[s+lag:e,b]
    else:
        k=-lag;aa=X[s+k:e,a];bb=X[s:e-k,b]
    return float(np.mean(aa*bb)) if len(aa) else np.nan

def motor_leader_follower(t):
    if t<30:return []
    # restricted to pairs with recent relation to keep runtime bounded
    active=[n for n in range(1,81) if h(t,n,12)>=3]
    cand=set(); hits=[]
    for a,b in combinations(active,2):
        scores={k:lag_score(t,a,b,k) for k in range(-5,6)}
        vals=[v for v in scores.values() if not np.isnan(v)]
        if not vals:continue
        mx=max(vals); dom=[k for k,v in scores.items() if v==mx]
        if len(dom)==1 and dom[0] in [1,2,3,4,5] and mx>=0.15:
            cand.add(b);hits.append((a,b,dom[0],round(mx,2)))
    return [signal("LIDER_TAKIPCI_FAZ",t,cand,f"{len(hits)} ilişki; {hits[:10]}",2)] if cand else []

def motor_region_pressure(t):
    if t<36:return []
    out=[]
    for g,nums in G10.items():
        # last 12 vs previous 24 per-draw region count
        recent=C10.loc[t-12:t-1,g].mean()
        old=C10.loc[t-36:t-13,g].mean()
        delta=recent-old
        if delta<=-0.55: # suppressed region, return-watch
            cand=[n for n in nums if h(t,n,24)>=3]
            if cand:out.append(signal("BASKI_TELAFI_"+g,t,cand,f"12 ort={recent:.2f}, önceki24={old:.2f}, Δ={delta:.2f}",abs(delta)))
    return out

def motor_region_handoff(t):
    if t<36:return []
    out=[]
    names=list(G10)
    r12={g:C10.loc[t-12:t-1,g].mean() for g in names}
    p24={g:C10.loc[t-36:t-13,g].mean() for g in names}
    for a,b in combinations(names,2):
        da=r12[a]-p24[a]; db=r12[b]-p24[b]
        if da<=-0.5 and db>=0.5:
            cand=G10[b]
            out.append(signal("NOBET_"+a+"_TO_"+b,t,cand,f"{a} Δ={da:.2f}; {b} Δ={db:.2f}",abs(da)+abs(db)))
        elif db<=-0.5 and da>=0.5:
            cand=G10[a]
            out.append(signal("NOBET_"+b+"_TO_"+a,t,cand,f"{b} Δ={db:.2f}; {a} Δ={da:.2f}",abs(da)+abs(db)))
    return out

def motor_two_three(t):
    if t<4:return []
    # numbers appearing 2/3 or 3/3 in immediately prior 3 draws
    cnt=np.sum(X[t-3:t,1:],axis=0)
    c2=np.where(cnt==2)[0]+1;c3=np.where(cnt==3)[0]+1
    out=[]
    if len(c2):out.append(signal("AKTIF_2_3",t,c2,"Önceki 3 elde 2/3",2))
    if len(c3):out.append(signal("AKTIF_3_3",t,c3,"Önceki 3 elde 3/3",3))
    return out

MOTORS=[
    ("Sıcaklık 4×20",48,motor_temperature),
    ("H1-H8 taşıma",12,motor_hcarry),
    ("Ritim",24,motor_rhythm),
    ("Ardışık",6,motor_consecutive),
    ("Son hane",12,motor_lastdigit),
    ("Yaş/uyku",24,motor_age_sleep),
    ("Ayna/simetri",12,motor_mirror),
    ("Sosyal AB→A",14,motor_social_ab),
    ("Lider/takipçi faz",30,motor_leader_follower),
    ("Baskı/telafi",36,motor_region_pressure),
    ("Bölge nöbet devri",36,motor_region_handoff),
    ("2/3–3/3",4,motor_two_three),
]

# ---------------- FULL SEQUENTIAL RUN ----------------
@st.cache_data(show_spinner=False)
def run_all():
    signals=[]
    daylog=[]
    days=sorted(df.date.unique())
    for di,day in enumerate(days,1):
        ids=df.index[df.date==day].tolist()
        before=len(signals)
        for t in ids: # strict chronological execution
            for label,warm,fn in MOTORS:
                if t<warm:continue
                try: signals.extend(fn(t))
                except Exception as e:
                    signals.append({"motor":"ERROR_"+label,"t":t,"draw_id":int(df.loc[t,"draw_id"]),
                                    "dt":df.loc[t,"dt"],"date":day,"period":df.loc[t,"period"],
                                    "candidates":[],"n_candidates":0,"real":[],"n_real":0,
                                    "detail":str(e),"score":0.0})
        daylog.append((day,len(ids),len(signals)-before))
    S=pd.DataFrame(signals)
    D=pd.DataFrame(daylog,columns=["date","draws","signals"])
    return S,D

with st.spinner("Motorlar 14 günü kronolojik tarıyor..."):
    S,DAYLOG=run_all()

# ---------------- COMBINER ----------------
@st.cache_data(show_spinner=False)
def combine_signals():
    if S.empty:return pd.DataFrame(),pd.DataFrame()
    votes=[]
    for t,g in S[~S.motor.str.startswith("ERROR_")].groupby("t"):
        per=defaultdict(lambda:{"motors":set(),"score":0.0})
        for _,r in g.iterrows():
            for n in r.candidates:
                per[n]["motors"].add(r.motor);per[n]["score"]+=r.score
        for n,v in per.items():
            votes.append((t,int(df.loc[t,"draw_id"]),df.loc[t,"dt"],df.loc[t,"period"],n,
                          len(v["motors"]),v["score"],int(X[t,n]),"|".join(sorted(v["motors"]))))
    V=pd.DataFrame(votes,columns=["t","draw_id","dt","period","num","motor_votes","score","REAL","motors"])
    rows=[]
    for t,g in V.groupby("t"):
        top=g.sort_values(["motor_votes","score"],ascending=False).head(20)
        rows.append((t,int(df.loc[t,"draw_id"]),df.loc[t,"dt"],len(g),int(top.REAL.sum()),
                     int((g.REAL==1).sum()),float(g.REAL.mean())))
    C=pd.DataFrame(rows,columns=["t","draw_id","dt","signaled_unique","TOP20_REAL","all_signal_REAL","candidate_hit_rate"])
    return V,C
VOTES,COMBO=combine_signals()

# ---------------- UI ----------------
st.sidebar.success(f"{len(df):,} çekiliş • {df.date.nunique()} gün")
page=st.sidebar.radio("V2 ekranı",[
    "Motor Kontrol Merkezi","Gün Gün Yürütme","~100 Mikro-Pencere",
    "Motor Karnesi D/V","Tek Motor Derinliği","8×10 İlişki/Faz",
    "Motor Birleştirici","REAL20 Açıklama","Tek Çekiliş Otopsisi","Dışa Aktar"
])

if page=="Motor Kontrol Merkezi":
    st.subheader("Otomatik motorlar")
    rows=[]
    for label,warm,fn in MOTORS:
        z=S[S.motor.str.startswith(("ISI_" if label=="Sıcaklık 4×20" else ""))] if False else None
        rows.append((label,warm))
    st.dataframe(pd.DataFrame(rows,columns=["Motor ailesi","Warm-up minimum çekiliş"]),use_container_width=True)
    a,b,c,d=st.columns(4)
    a.metric("Motor sinyali",len(S)); b.metric("Motor türü",S.motor.nunique() if not S.empty else 0)
    c.metric("Aday-sayı olayı",int(S.n_candidates.sum()) if not S.empty else 0)
    d.metric("REAL yakalama",int(S.n_real.sum()) if not S.empty else 0)
    if not S.empty:
        err=S[S.motor.str.startswith("ERROR_")]
        st.caption(f"Hata kaydı: {len(err)}")

elif page=="Gün Gün Yürütme":
    st.subheader("Bir gün biter → sonraki güne geçer; uzun geçmiş korunur")
    z=DAYLOG.copy()
    if not S.empty:
        agg=S.groupby("date").agg(candidate_events=("n_candidates","sum"),real=("n_real","sum")).reset_index()
        z=z.merge(agg,on="date",how="left")
    st.dataframe(z,use_container_width=True)
    day=st.selectbox("Gün detayı",z.date.tolist())
    sd=S[S.date==day]
    st.dataframe(sd[["dt","draw_id","motor","n_candidates","n_real","detail"]],use_container_width=True,height=600)

elif page=="~100 Mikro-Pencere":
    day=st.selectbox("Gün",sorted(df.date.unique()))
    window=st.slider("Pencere",6,48,24)
    step=st.slider("Adım",1,12,2)
    ids=df.index[df.date==day]
    mw=micro_windows(ids,window,step)
    st.write(f"**{len(mw)} mikro-pencere**")
    rows=[]
    for _,r in mw.iterrows():
        ss=S[(S.t>=r.start_i)&(S.t<=r.end_i)]
        rows.append((r.start,r.end,len(ss),int(ss.n_candidates.sum()) if len(ss) else 0,
                     int(ss.n_real.sum()) if len(ss) else 0,ss.motor.nunique() if len(ss) else 0))
    st.dataframe(pd.DataFrame(rows,columns=["Başlangıç","Bitiş","Sinyal","Aday","REAL","Aktif motor"]),use_container_width=True,height=600)

elif page=="Motor Karnesi D/V":
    if S.empty:st.stop()
    rows=[]
    for (m,p),g in S.groupby(["motor","period"]):
        cand=int(g.n_candidates.sum());real=int(g.n_real.sum())
        rows.append((m,p,len(g),cand,real,real/cand if cand else np.nan,
                     g.date.nunique(),g.draw_id.nunique()))
    K=pd.DataFrame(rows,columns=["Motor","D/V","Tetik","Aday","REAL","Aday hit","Aktif gün","Aktif çekiliş"])
    st.dataframe(K.sort_values(["Motor","D/V"]),use_container_width=True,height=650)
    st.caption("Aday-sayı bazında rastgele tek sayı tabanı %25'tir. Çift/olay motorlarının kendi uygun null modeli ayrıca değerlendirilmelidir.")

elif page=="Tek Motor Derinliği":
    motors=sorted(S.motor.unique()) if not S.empty else []
    m=st.selectbox("Motor",motors)
    q=S[S.motor==m].copy()
    st.dataframe(q[["dt","draw_id","period","n_candidates","n_real","score","detail"]],use_container_width=True,height=600)
    if len(q):
        byday=q.groupby("date").agg(tetik=("draw_id","count"),aday=("n_candidates","sum"),real=("n_real","sum"))
        byday["hit"]=byday.real/byday.aday.replace(0,np.nan)
        st.dataframe(byday.round(4),use_container_width=True)

elif page=="8×10 İlişki/Faz":
    a=st.selectbox("Bölge A",list(G10),0);b=st.selectbox("Bölge B",list(G10),6)
    day=st.selectbox("Gün",["14 gün"]+list(sorted(df.date.unique())))
    ids=df.index if day=="14 gün" else df.index[df.date==day]
    rows=[]
    xa=C10.loc[ids,a].to_numpy(float);xb=C10.loc[ids,b].to_numpy(float)
    for lag in range(-12,13):
        if lag<0:x=xa[-lag:];y=xb[:len(xb)+lag]
        elif lag>0:x=xa[:-lag];y=xb[lag:]
        else:x=xa;y=xb
        corr=np.corrcoef(x,y)[0,1] if len(x)>4 and np.std(x)>0 and np.std(y)>0 else np.nan
        rows.append((lag,corr,len(x)))
    st.dataframe(pd.DataFrame(rows,columns=["Lag","Korelasyon","N"]).round(4),use_container_width=True)
    z=df.loc[ids,["dt"]].copy();z[a]=C10.loc[ids,a];z[b]=C10.loc[ids,b]
    st.line_chart(z.set_index("dt")[[a,b]])

elif page=="Motor Birleştirici":
    if VOTES.empty:st.stop()
    minv=st.slider("Minimum bağımsız motor oyu",1,10,2)
    q=VOTES[VOTES.motor_votes>=minv]
    a,b,c=st.columns(3)
    a.metric("Aday olay",len(q));b.metric("REAL",int(q.REAL.sum()))
    c.metric("Hit",f"{100*q.REAL.mean():.2f}%" if len(q) else "-")
    st.dataframe(q.sort_values(["dt","motor_votes","score"],ascending=[False,False,False]).head(1000),
                 use_container_width=True,height=650)

elif page=="REAL20 Açıklama":
    if VOTES.empty:st.stop()
    rows=[]
    for t in range(len(df)):
        q=VOTES[VOTES.t==t]
        real=set(df.loc[t,"nums"])
        explained=set(q.loc[q.REAL==1,"num"])
        rows.append((df.loc[t,"draw_id"],df.loc[t,"dt"],df.loc[t,"period"],len(explained),
                     20-len(explained),len(set(q.num)-real)))
    E=pd.DataFrame(rows,columns=["draw_id","dt","D/V","REAL20 açıklanan","Açıklanamayan","NEGATIVE60 ateş"])
    st.dataframe(E,use_container_width=True,height=650)
    st.write(E[["REAL20 açıklanan","Açıklanamayan","NEGATIVE60 ateş"]].describe().round(3))

elif page=="Tek Çekiliş Otopsisi":
    did=st.selectbox("Çekiliş",df.draw_id.tolist(),index=len(df)-1)
    t=int(df.index[df.draw_id==did][0])
    st.write(f"### {did} — {df.loc[t,'dt']}")
    st.write("**REAL20:**",", ".join(map(str,df.loc[t,"nums"])))
    q=S[S.t==t]
    st.dataframe(q[["motor","n_candidates","n_real","score","candidates","real","detail"]],
                 use_container_width=True,height=600)
    if not VOTES.empty:
        v=VOTES[VOTES.t==t].sort_values(["motor_votes","score"],ascending=False)
        st.subheader("80 havuzunda motor oyları")
        st.dataframe(v,use_container_width=True,height=500)

elif page=="Dışa Aktar":
    st.download_button("Motor ham sinyalleri CSV",S.to_csv(index=False).encode("utf-8-sig"),
                       "motor_ham_sinyaller.csv","text/csv")
    st.download_button("Motor oyları CSV",VOTES.to_csv(index=False).encode("utf-8-sig"),
                       "motor_birlesim_oylari.csv","text/csv")
    st.download_button("Gün yürütme CSV",DAYLOG.to_csv(index=False).encode("utf-8-sig"),
                       "gun_gun_yurutme.csv","text/csv")
    st.download_button("Birleşim özeti CSV",COMBO.to_csv(index=False).encode("utf-8-sig"),
                       "motor_birlesim_ozeti.csv","text/csv")
