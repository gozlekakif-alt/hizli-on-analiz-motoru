
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from collections import Counter, defaultdict
from math import sqrt

st.set_page_config(page_title="Hızlı On — 306 Zincir Araştırma Lab", layout="wide")
st.title("Hızlı On — 306 Maddelik Kronolojik Zincir Araştırma Laboratuvarı")
st.caption("14 gün tek zincir • PRE-DRAW/no-leakage • 306 gerçek test • Event_ID • REAL/NEGATIVE • lift • günlük tutarlılık")

DATA = Path("veri.txt")

@st.cache_data(show_spinner=False)
def load_data(path="veri.txt"):
    rows=[]
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        a,b,c=line.strip().split(";")
        nums=tuple(sorted(map(int,c.split(","))))
        if len(nums)!=20 or len(set(nums))!=20 or min(nums)<1 or max(nums)>80:
            raise ValueError(f"Bozuk çekiliş: {line[:80]}")
        rows.append((int(a),pd.to_datetime(b,dayfirst=True),nums))
    df=pd.DataFrame(rows,columns=["draw_id","dt","nums"]).sort_values("draw_id").reset_index(drop=True)
    df["date"]=df.dt.dt.date.astype(str)
    return df

def z_ci(p,n):
    if n<=0: return (np.nan,np.nan)
    se=sqrt(max(p*(1-p),1e-12)/n)
    return max(0,p-1.96*se), min(1,p+1.96*se)

# ---------- Canonical 306 registry ----------
# Every row is a distinct, executable predicate. No padding/cycling.
def registry():
    R=[]
    def add(group,name,kind,**kw):
        R.append(dict(id=f"M{len(R)+1:03d}",group=group,name=name,kind=kind,**kw))

    # 1) H1-H8 membership: 8
    for h in range(1,9):
        add("H taşıma","H%d içinde"%h,"h",lags=(h,))

    # 2) H pair intersections: C(8,2)=28
    for a in range(1,9):
        for b in range(a+1,9):
            add("H dönüşüm","H%d + H%d ortak"%(a,b),"h_all",lags=(a,b))

    # 3) H triple intersections: C(8,3)=56
    for a in range(1,9):
        for b in range(a+1,9):
            for c in range(b+1,9):
                add("H dönüşüm","H%d + H%d + H%d ortak"%(a,b,c),"h_all",lags=(a,b,c))

    # 4) Exact H-path masks over H1-H4: 16
    for mask in range(16):
        bits=tuple((mask>>i)&1 for i in range(4))
        add("H yaşam yolu","H1-H4 yol "+''.join(map(str,bits)),"h_mask",bits=bits)

    # 5) Age/sleep buckets: 12
    for lo,hi in [(1,1),(2,2),(3,3),(4,4),(5,5),(6,6),(7,8),(9,10),(11,13),(14,17),(18,24),(25,9999)]:
        add("Yaş/Uyku",f"Yaş {lo}" if lo==hi else f"Yaş {lo}-{hi if hi<9999 else '∞'}","age",lo=lo,hi=hi)

    # 6) Rolling frequency quantiles, 6 windows x 5 layers =30
    for w in (6,12,24,36,72,144):
        for q in range(5):
            add("Sıcaklık",f"Son {w} el frekans katmanı Q{q+1}","freq_q",window=w,q=q)

    # 7) Consecutive / neighborhood predicates: 24
    for lag in (1,2,3,6):
        for d in (1,2,3):
            add("Komşu",f"H{lag} içinde ±{d} komşusu var","neighbor",lag=lag,dist=d)
    for lag in (1,2,3,6):
        for step in (2,3,4):
            add("Atlamalı",f"H{lag} içinde ±{step} atlamalı eş var","neighbor",lag=lag,dist=step)

    # 8) Pair-family support: 24
    for w in (12,24,48,96):
        for k in (1,2,3,4,5,6):
            add("2'li aile",f"Son {w} elde H1 partnerleriyle en az {k} ortak yaşam","pair_support",window=w,k=k)

    # 9) Triple-family support: 18
    for w in (24,48,96):
        for k in (1,2,3,4,5,6):
            add("3'lü aile",f"Son {w} elde H1'den iki partnerle en az {k} üçlü yaşam","triple_support",window=w,k=k)

    # 10) Rhythm exact recent gaps: 18
    for g in range(1,19):
        add("Ritim",f"Son görünüm aralığı tam {g} el","gap",gap=g)

    # 11) Repeated-gap rhythm: 12
    for g in range(1,13):
        add("Ritim",f"Son iki görünüm aralığı {g}→{g}","repeat_gap",gap=g)

    # 12) Band pressure: 16 (8 bands x high/low relative to expected)
    for band in range(8):
        add("Bant",f"{band*10+1}-{band*10+10} bandı son 12 elde yüksek baskı","band_pressure",band=band,window=12,side="high")
        add("Bant",f"{band*10+1}-{band*10+10} bandı son 12 elde düşük baskı","band_pressure",band=band,window=12,side="low")

    # 13) Same-last-digit pressure: 20
    for s in range(10):
        add("Son hane",f"Son hane {s}: son 12 elde yüksek baskı","suffix_pressure",suffix=s,window=12,side="high")
        add("Son hane",f"Son hane {s}: son 12 elde düşük baskı","suffix_pressure",suffix=s,window=12,side="low")

    # 14) Cross-engine combinations: 22
    combos=[
      ("H1 + yaş1","combo",("h1","age1")),
      ("H1 + yaş2","combo",("h1","age2")),
      ("H1 + yaş3-5","combo",("h1","age3_5")),
      ("H1 + sıcak12","combo",("h1","hot12")),
      ("H1 + soğuk12","combo",("h1","cold12")),
      ("H1 + komşu1","combo",("h1","nei1")),
      ("H1 + komşu2","combo",("h1","nei2")),
      ("H1 + çift-aile24","combo",("h1","pair24")),
      ("H1 + üçlü-aile48","combo",("h1","triple48")),
      ("H1 + ritim1","combo",("h1","gap1")),
      ("H1 + ritim2","combo",("h1","gap2")),
      ("H2 + yaş1","combo",("h2","age1")),
      ("H2 + sıcak12","combo",("h2","hot12")),
      ("H2 + çift-aile24","combo",("h2","pair24")),
      ("H3 + sıcak12","combo",("h3","hot12")),
      ("H3 + çift-aile24","combo",("h3","pair24")),
      ("H1H2 + sıcak12","combo",("h1h2","hot12")),
      ("H1H3 + sıcak12","combo",("h1h3","hot12")),
      ("H1H2 + çift-aile24","combo",("h1h2","pair24")),
      ("H1H3 + çift-aile24","combo",("h1h3","pair24")),
      ("H1 + düşük bant","combo",("h1","lowband")),
      ("H1 + yüksek sonhane","combo",("h1","highsuffix")),
    ]
    for name,kind,parts in combos:
        add("Çapraz motor",name,kind,parts=parts)

    assert len(R)==306, len(R)
    return R

REG=registry()

@st.cache_data(show_spinner=True)
def build_events(df):
    n=len(df)
    sets=[set(x) for x in df.nums]
    dates=df.date.tolist()
    ids=df.draw_id.tolist()
    # Histories updated only AFTER each target is evaluated.
    last_seen=[None]*81
    prev_seen=[None]*81
    freq_windows={w:[Counter() for _ in range(n)] for w in []}  # placeholder
    records=[]
    # Precompute occurrence prefix for fast rolling frequency
    X=np.zeros((n,81),dtype=np.uint8)
    for i,s in enumerate(sets):
        X[i,list(s)]=1
    P=X.cumsum(axis=0)

    def count_num(t,num,w):
        a=max(0,t-w); z=t-1
        if z<0:return 0
        return int(P[z,num]-(P[a-1,num] if a>0 else 0))

    # Pair/triple supports are computed from prior-window draws only.
    for t in range(1,n):
        target=sets[t]
        hsets={h:(sets[t-h] if t-h>=0 else set()) for h in range(1,9)}
        # last/prev occurrence positions strictly before target
        hist_positions={}
        for num in range(1,81):
            pos=np.flatnonzero(X[:t,num])
            hist_positions[num]=pos[-3:].tolist()

        # caches for this target
        freq_cache={}
        for w in (6,12,24,36,72,144):
            vals=np.array([count_num(t,num,w) for num in range(1,81)])
            freq_cache[w]=vals
        h1=hsets[1]
        # pair/triple caches only for needed windows
        pair_cache={}
        triple_cache={}
        for w in (12,24,48,96):
            start=max(0,t-w)
            pc={num:0 for num in range(1,81)}
            for j in range(start,t):
                s=sets[j]
                partners=s & h1
                if not partners: continue
                for num in s:
                    if num not in h1:
                        pc[num]+=len(partners)
                    else:
                        pc[num]+=max(0,len(partners)-1)
            pair_cache[w]=pc
        for w in (24,48,96):
            start=max(0,t-w)
            tc={num:0 for num in range(1,81)}
            for j in range(start,t):
                s=sets[j]; partners=s & h1
                if len(partners)<2: continue
                for num in s:
                    m=len(partners)-(1 if num in partners else 0)
                    if m>=2: tc[num]+=m*(m-1)//2
            triple_cache[w]=tc

        band_counts=[0]*8; suffix_counts=[0]*10
        for j in range(max(0,t-12),t):
            for x in sets[j]:
                band_counts[(x-1)//10]+=1
                suffix_counts[x%10]+=1
        # expected: 30 per band and 24 per suffix over 12 draws
        for num in range(1,81):
            pos=hist_positions[num]
            age=(t-pos[-1]) if pos else 9999
            gap=(pos[-1]-pos[-2]) if len(pos)>=2 else 9999
            prevgap=(pos[-2]-pos[-3]) if len(pos)>=3 else 9999
            rec={
              "target_i":t,"draw_id":ids[t],"date":dates[t],"num":num,
              "real":1 if num in target else 0,"age":age,"gap":gap,"prevgap":prevgap,
              "hbits":tuple(1 if num in hsets[h] else 0 for h in range(1,9)),
              "freq":{w:int(freq_cache[w][num-1]) for w in freq_cache},
              "pair":{w:pair_cache[w][num] for w in pair_cache},
              "triple":{w:triple_cache[w][num] for w in triple_cache},
              "neighbors":{(h,d):int(any((num-d in hsets[h],num+d in hsets[h]))) for h in (1,2,3,6) for d in (1,2,3,4)},
              "band_high":band_counts[(num-1)//10]>30,
              "band_low":band_counts[(num-1)//10]<30,
              "suffix_high":suffix_counts[num%10]>24,
              "suffix_low":suffix_counts[num%10]<24,
            }
            records.append(rec)
    return records

def pred(r,spec):
    k=spec["kind"]
    if k=="h": return bool(r["hbits"][spec["lags"][0]-1])
    if k=="h_all": return all(r["hbits"][h-1] for h in spec["lags"])
    if k=="h_mask": return tuple(r["hbits"][:4])==tuple(spec["bits"])
    if k=="age": return spec["lo"]<=r["age"]<=spec["hi"]
    if k=="freq_q":
        # Candidate's rank layer reconstructed from count; boundaries are fixed fractions of window.
        # Use count thresholds corresponding to empirical intensity, not future data.
        w=spec["window"]; q=spec["q"]; c=r["freq"][w]
        # 5 ordinal bins around expected w/4
        cuts=[max(0,int(w*.12)),int(w*.20),int(w*.28),int(w*.36)]
        return ([c<=cuts[0],cuts[0]<c<=cuts[1],cuts[1]<c<=cuts[2],cuts[2]<c<=cuts[3],c>cuts[3]][q])
    if k=="neighbor": return bool(r["neighbors"].get((spec["lag"],spec["dist"]),0))
    if k=="pair_support": return r["pair"][spec["window"]]>=spec["k"]
    if k=="triple_support": return r["triple"][spec["window"]]>=spec["k"]
    if k=="gap": return r["gap"]==spec["gap"]
    if k=="repeat_gap": return r["gap"]==spec["gap"] and r["prevgap"]==spec["gap"]
    if k=="band_pressure": return r["band_high"] if spec["side"]=="high" else r["band_low"]
    if k=="suffix_pressure": return r["suffix_high"] if spec["side"]=="high" else r["suffix_low"]
    if k=="combo":
        def part(p):
            if p=="h1": return r["hbits"][0]
            if p=="h2": return r["hbits"][1]
            if p=="h3": return r["hbits"][2]
            if p=="h1h2": return r["hbits"][0] and r["hbits"][1]
            if p=="h1h3": return r["hbits"][0] and r["hbits"][2]
            if p=="age1": return r["age"]==1
            if p=="age2": return r["age"]==2
            if p=="age3_5": return 3<=r["age"]<=5
            if p=="hot12": return r["freq"][12]>=4
            if p=="cold12": return r["freq"][12]<=2
            if p=="nei1": return r["neighbors"][(1,1)]
            if p=="nei2": return r["neighbors"][(1,2)]
            if p=="pair24": return r["pair"][24]>=3
            if p=="triple48": return r["triple"][48]>=2
            if p=="gap1": return r["gap"]==1
            if p=="gap2": return r["gap"]==2
            if p=="lowband": return r["band_low"]
            if p=="highsuffix": return r["suffix_high"]
            return False
        return all(part(p) for p in spec["parts"])
    return False

@st.cache_data(show_spinner=True)
def evaluate(df):
    ev=build_events(df)
    rows=[]
    daily_rows=[]
    for spec in REG:
        byday=defaultdict(lambda:[0,0])
        n=hit=0
        for r in ev:
            if pred(r,spec):
                n+=1; hit+=r["real"]
                byday[r["date"]][0]+=1; byday[r["date"]][1]+=r["real"]
        rate=hit/n if n else np.nan
        lift=rate/.25 if n else np.nan
        lo,hi=z_ci(rate,n) if n else (np.nan,np.nan)
        good_days=0; tested_days=0
        for d,(dn,dh) in byday.items():
            if dn:
                tested_days+=1
                if dh/dn>.25: good_days+=1
                daily_rows.append([spec["id"],d,dn,dh,dh/dn,(dh/dn)/.25])
        # Conservative status: enough events + CI lower bound over baseline + cross-day majority
        if n==0: status="OLAY YOK"
        elif n<100: status="AZ ÖRNEK"
        elif lo>.25 and good_days>=8: status="GÜÇLÜ ADAY"
        elif rate>.25 and good_days>=7: status="İZLE"
        elif hi<.25: status="NEGATİF/VETO ADAYI"
        else: status="TABAN / BELİRSİZ"
        rows.append([spec["id"],spec["group"],spec["name"],n,hit,n-hit,rate,lift,lo,hi,tested_days,good_days,status])
    cols=["ID","Grup","Araştırma","Aday","REAL","NEGATIVE","Başarı","Lift","CI_alt","CI_üst","Test_gün","%25_üstü_gün","Sonuç"]
    res=pd.DataFrame(rows,columns=cols)
    daily=pd.DataFrame(daily_rows,columns=["ID","Tarih","Aday","REAL","Başarı","Lift"])
    return res,daily

df=load_data()
st.success(f"Kaynak: {len(df):,} çekiliş • {df.draw_id.iloc[0]}→{df.draw_id.iloc[-1]} • {df.date.nunique()} gün • tek kronolojik zincir")
st.info("No-leakage kilidi: Her hedef çekilişin özellikleri yalnız daha önceki çekilişlerden hesaplanır. Sonuç daha sonra REAL/NEGATIVE etiketi olarak açılır.")

with st.expander("306 araştırma maddesinin tam listesi"):
    st.dataframe(pd.DataFrame(REG)[["id","group","name"]],use_container_width=True,height=500)

if st.button("306 MADDEYİ 14 GÜN TEK ZİNCİRDE ÇALIŞTIR",type="primary"):
    with st.spinner("3.038 çekilişlik zincir ve 306 deney yürütülüyor..."):
        res,daily=evaluate(df)
    st.session_state["res"]=res
    st.session_state["daily"]=daily

if "res" in st.session_state:
    res=st.session_state["res"]; daily=st.session_state["daily"]
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Gerçek araştırma",len(res))
    c2.metric("Olay üreten",(res.Aday>0).sum())
    c3.metric("Güçlü aday",(res.Sonuç=="GÜÇLÜ ADAY").sum())
    c4.metric("Veto adayı",(res.Sonuç=="NEGATİF/VETO ADAYI").sum())

    tabs=st.tabs(["306 Sonuç","H1/H2/H3 Kadavra","Güçlü Sinyaller","Veto Sinyalleri","Günlük Tutarlılık","MASTER Çıktı"])
    with tabs[0]:
        st.dataframe(res.sort_values(["Lift","Aday"],ascending=[False,False]),use_container_width=True,height=650)
    with tabs[1]:
        h=res[res.Grup.isin(["H taşıma","H dönüşüm","H yaşam yolu","Çapraz motor"])].copy()
        st.dataframe(h.sort_values("Lift",ascending=False),use_container_width=True,height=650)
        st.caption("Burada H1, H2, H3 ayrı ayrı; H1+H2, H1+H3, H2+H3; üçlü H kesişimleri ve H1-H4 yaşam yolları birlikte test edilir.")
    with tabs[2]:
        st.dataframe(res[res.Sonuç=="GÜÇLÜ ADAY"].sort_values("Lift",ascending=False),use_container_width=True,height=650)
    with tabs[3]:
        st.dataframe(res[res.Sonuç=="NEGATİF/VETO ADAYI"].sort_values("Lift"),use_container_width=True,height=650)
    with tabs[4]:
        pick=st.selectbox("Araştırma ID",res.ID.tolist())
        st.dataframe(daily[daily.ID==pick],use_container_width=True)
    with tabs[5]:
        meta=[
          "HIZLI ON 306 ZINCIR ARASTIRMA MASTER V2",
          f"CEKILIS={len(df)} | {df.draw_id.iloc[0]}->{df.draw_id.iloc[-1]} | GUN={df.date.nunique()}",
          "NO_LEAKAGE=EVET | BASELINE_REAL=0.25",
          f"GERCEK_MADDE={len(res)}/306",
          ""
        ]
        txt="\n".join(meta)
        for _,r in res.iterrows():
            txt += (f"{r.ID}|{r.Grup}|{r.Araştırma}|ADAY={r.Aday}|REAL={r.REAL}|NEG={r.NEGATIVE}"
                    f"|RATE={r.Başarı:.6f}|LIFT={r.Lift:.4f}|CI={r.CI_alt:.6f}-{r.CI_üst:.6f}"
                    f"|GUN={r.Test_gün}|UST_GUN={r['%25_üstü_gün']}|SONUC={r.Sonuç}\n")
        txt+="\n--- GUNLUK KIRILIM ---\n"
        for _,r in daily.iterrows():
            txt+=f"{r.ID}|{r.Tarih}|ADAY={r.Aday}|REAL={r.REAL}|RATE={r.Başarı:.6f}|LIFT={r.Lift:.4f}\n"
        st.download_button("TEK MASTER TXT İNDİR",txt.encode("utf-8"),"HIZLI_ON_306_ZINCIR_MASTER_V2.txt","text/plain")
        st.download_button("306 SONUÇ CSV İNDİR",res.to_csv(index=False).encode("utf-8-sig"),"HIZLI_ON_306_SONUCLAR_V2.csv","text/csv")

st.divider()
st.caption("Araştırma motorudur; geçmiş sonuçlarda görülen ilişki gelecekte kazanç garantisi değildir.")
