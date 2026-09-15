
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from collections import Counter, defaultdict
from itertools import combinations

st.set_page_config(page_title="H1-H8 Derin Yaşam Laboratuvarı", layout="wide")
st.title("Hızlı On — H1→H8 Derin Yaşam / Dönüşüm Laboratuvarı")
st.caption("1–80 sayı bazında • 14 gün tek zincir • no-leakage • H1,H2,H3,H4,H5,H6,H7,H8 • dönüş, uyku, zincir ve kombinasyon")

@st.cache_data
def load():
    rows=[]
    for line in Path("veri.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        a,b,c=line.split(";")
        nums=set(map(int,c.split(",")))
        rows.append((int(a),pd.to_datetime(b,dayfirst=True),nums))
    df=pd.DataFrame(rows,columns=["draw_id","dt","nums"]).sort_values("draw_id").reset_index(drop=True)
    df["date"]=df.dt.dt.date.astype(str)
    return df

@st.cache_data(show_spinner=True)
def analyze(df):
    sets=df.nums.tolist()
    events=[]
    # Each target draw t: Hk means number existed at t-k.
    for t in range(8,len(df)):
        actual=sets[t]
        for num in range(1,81):
            bits=tuple(int(num in sets[t-h]) for h in range(1,9))
            events.append({
                "i":t,"draw_id":int(df.draw_id.iloc[t]),"dt":df.dt.iloc[t],
                "date":df.date.iloc[t],"num":num,"real":int(num in actual),
                **{f"H{h}":bits[h-1] for h in range(1,9)},
                "mask":"".join(map(str,bits))
            })
    ev=pd.DataFrame(events)

    # H1..H8 singles
    summary=[]
    for h in range(1,9):
        x=ev[ev[f"H{h}"]==1]
        summary.append([f"H{h}",len(x),int(x.real.sum()),x.real.mean(),x.real.mean()/0.25])

    # All pair/triple H combinations
    combos=[]
    for r in (2,3,4):
        for hs in combinations(range(1,9),r):
            mask=np.ones(len(ev),dtype=bool)
            for h in hs: mask &= ev[f"H{h}"].to_numpy()==1
            x=ev[mask]
            if len(x):
                combos.append(["+".join(f"H{h}" for h in hs),r,len(x),int(x.real.sum()),x.real.mean(),x.real.mean()/0.25])
    combo=pd.DataFrame(combos,columns=["H_kombinasyon","Boyut","Aday","REAL","Başarı","Lift"])

    # Exact H1-H8 path masks
    paths=(ev.groupby("mask").real.agg(["size","sum","mean"]).reset_index()
           .rename(columns={"size":"Aday","sum":"REAL","mean":"Başarı"}))
    paths["Lift"]=paths.Başarı/.25
    paths["H_sayısı"]=paths["mask"].str.count("1")

    # Per-number H performance
    nr=[]
    for num,g in ev.groupby("num"):
        row={"Sayı":num,"Toplam_REAL":int(g.real.sum())}
        for h in range(1,9):
            x=g[g[f"H{h}"]==1]
            row[f"H{h}_aday"]=len(x)
            row[f"H{h}_real"]=int(x.real.sum())
            row[f"H{h}_oran"]=x.real.mean() if len(x) else np.nan
        nr.append(row)
    numbers=pd.DataFrame(nr)

    # Actual appearance binary life sequence for every number and run/sleep/return cycles.
    cycles=[]
    transitions=[]
    for num in range(1,81):
        seq=np.array([int(num in s) for s in sets],dtype=np.int8)
        # consecutive REAL run lengths and zero sleeps between REALs
        pos=np.flatnonzero(seq)
        gaps=np.diff(pos)-1
        for sleep in range(0,24):
            idx=np.where(gaps==sleep)[0]
            cycles.append([num,sleep,len(idx)])
        # pattern -> next outcome, patterns length 2..8, no leakage
        for L in range(2,9):
            d=defaultdict(lambda:[0,0])
            for t in range(L,len(seq)):
                pat="".join(map(str,seq[t-L:t]))
                d[pat][0]+=1; d[pat][1]+=int(seq[t])
            for pat,(n,hit) in d.items():
                transitions.append([num,L,pat,n,hit,hit/n,hit/n/.25])
    cyc=pd.DataFrame(cycles,columns=["Sayı","Uyku_eli","Dönüş_sayısı"])
    tr=pd.DataFrame(transitions,columns=["Sayı","Yol_Uzunluğu","Geçmiş_Yol","Olay","Sonraki_REAL","Başarı","Lift"])

    # Aggregate transition paths across 1-80
    tra=(tr.groupby(["Yol_Uzunluğu","Geçmiş_Yol"])[["Olay","Sonraki_REAL"]].sum().reset_index())
    tra["Başarı"]=tra.Sonraki_REAL/tra.Olay
    tra["Lift"]=tra.Başarı/.25

    # Day consistency for H singles and combinations
    day=[]
    tests=[(f"H{h}",(h,)) for h in range(1,9)]
    tests += [( "+".join(f"H{h}" for h in hs), hs) for r in (2,3) for hs in combinations(range(1,9),r)]
    for name,hs in tests:
        mask=np.ones(len(ev),dtype=bool)
        for h in hs: mask &= ev[f"H{h}"].to_numpy()==1
        tmp=ev[mask]
        for d,g in tmp.groupby("date"):
            day.append([name,d,len(g),int(g.real.sum()),g.real.mean(),g.real.mean()/.25])
    daily=pd.DataFrame(day,columns=["Test","Tarih","Aday","REAL","Başarı","Lift"])

    return ev,pd.DataFrame(summary,columns=["H","Aday","REAL","Başarı","Lift"]),combo,paths,numbers,cyc,tr,tra,daily

df=load()
st.success(f"{len(df)} çekiliş • {df.draw_id.iloc[0]}→{df.draw_id.iloc[-1]} • {df.date.nunique()} gün • TEK ZİNCİR")
st.info("H1 = hedef çekilişten 1 el önce, H2 = 2 el önce ... H8 = 8 el önce. Hedef sonuç özellik hesabından sonra açılır.")

if st.button("H1→H8 TAM DERİN ANALİZİ ÇALIŞTIR",type="primary"):
    with st.spinner("H yaşam yolları çıkarılıyor..."):
        st.session_state["HRES"]=analyze(df)

if "HRES" in st.session_state:
    ev,single,combo,paths,numbers,cyc,tr,tra,daily=st.session_state["HRES"]
    tabs=st.tabs(["H1-H8","H Kombinasyon","H Yaşam Yolları","1–80 Sayı Detayı","Uyku→Dönüş","Dönüşümlü Ritim","Gün Gün","Tek MASTER"])
    with tabs[0]:
        st.subheader("H1 → H8 tek tek")
        st.dataframe(single,use_container_width=True)
    with tabs[1]:
        st.subheader("Bütün 2'li, 3'lü ve 4'lü H kesişimleri")
        st.dataframe(combo.sort_values("Lift",ascending=False),use_container_width=True,height=650)
    with tabs[2]:
        st.subheader("Tam H1-H8 geçmiş yolu")
        st.caption("Örn. 10100010 = sayı H1,H3,H7'de vardı; diğer H basamaklarında yoktu.")
        st.dataframe(paths.sort_values(["Lift","Aday"],ascending=[False,False]),use_container_width=True,height=650)
    with tabs[3]:
        num=st.selectbox("Sayı seç",range(1,81))
        row=numbers[numbers.Sayı==num]
        st.dataframe(row,use_container_width=True)
        st.subheader(f"{num} — en güçlü geçmiş yaşam yolları")
        z=tr[(tr.Sayı==num)&(tr.Olay>=5)].sort_values(["Lift","Olay"],ascending=[False,False])
        st.dataframe(z.head(100),use_container_width=True,height=500)
    with tabs[4]:
        num2=st.selectbox("Uyku/dönüş için sayı",range(1,81),key="sleep")
        st.dataframe(cyc[cyc.Sayı==num2],use_container_width=True)
    with tabs[5]:
        st.subheader("1→0→1 / 1→00→1 / 11→0→1 vb. dönüş yolları")
        st.dataframe(tra[tra.Olay>=50].sort_values(["Lift","Olay"],ascending=[False,False]),use_container_width=True,height=650)
    with tabs[6]:
        test=st.selectbox("H testi",daily.Test.unique())
        st.dataframe(daily[daily.Test==test],use_container_width=True)
    with tabs[7]:
        lines=[
          "HIZLI ON H1-H8 DERIN ZINCIR MASTER",
          f"CEKILIS={len(df)}|BAS={df.draw_id.iloc[0]}|SON={df.draw_id.iloc[-1]}|GUN={df.date.nunique()}",
          "NO_LEAKAGE=EVET|BASELINE=0.25",
          "",
          "=== H1-H8 ==="
        ]
        for _,r in single.iterrows():
            lines.append(f"{r.H}|ADAY={r.Aday}|REAL={r.REAL}|RATE={r.Başarı:.6f}|LIFT={r.Lift:.4f}")
        lines.append("\n=== H KOMBINASYONLARI ===")
        for _,r in combo.iterrows():
            lines.append(f"{r.H_kombinasyon}|BOYUT={r.Boyut}|ADAY={r.Aday}|REAL={r.REAL}|RATE={r.Başarı:.6f}|LIFT={r.Lift:.4f}")
        lines.append("\n=== H1-H8 TAM YOLLAR ===")
        for _,r in paths.iterrows():
            lines.append(f"{r['mask']}|H={r.H_sayısı}|ADAY={r.Aday}|REAL={r.REAL}|RATE={r.Başarı:.6f}|LIFT={r.Lift:.4f}")
        lines.append("\n=== 1-80 SAYI H DETAY ===")
        lines.append(numbers.to_csv(index=False))
        lines.append("\n=== UYKU DONUS ===")
        lines.append(cyc.to_csv(index=False))
        lines.append("\n=== DONUSUMLU RITIM TOPLAM ===")
        lines.append(tra.to_csv(index=False))
        lines.append("\n=== GUNLUK H TUTARLILIK ===")
        lines.append(daily.to_csv(index=False))
        master="\n".join(lines)
        st.download_button("H1-H8 TEK MASTER TXT İNDİR",master.encode("utf-8"),"H1_H8_DERIN_MASTER.txt","text/plain")
        st.download_button("1-80 H DETAY CSV",numbers.to_csv(index=False).encode("utf-8-sig"),"H1_H8_1_80_DETAY.csv","text/csv")

st.caption("Amaç H davranışını ölçmektir; geçmiş örüntüler gelecek çekiliş için garanti oluşturmaz.")
