import streamlit as st
import pandas as pd
import itertools
from collections import Counter, defaultdict
from math import comb

st.set_page_config(page_title="Hızlı On Aile Birleşme Analizi", layout="wide")
st.title("🧬 Hızlı On — Aile Birleşme / Doluluk Analizi")
st.caption("Amaç: yüksek REAL20 örtüşmelerinden üst aileleri çıkarıp, ailelerin 6→7→8→9→… birleşme yaşamını kronolojik incelemek.")

def parse_txt(text):
    rows=[]
    for line in text.splitlines():
        parts=line.strip().split(";")
        if len(parts)!=3:
            continue
        try:
            draw_id=int(parts[0])
            dt=pd.to_datetime(parts[1], format="%d.%m.%Y %H:%M")
            nums=tuple(sorted(map(int, parts[2].split(","))))
            if len(nums)==20 and len(set(nums))==20:
                rows.append((draw_id,dt,nums))
        except:
            pass
    df=pd.DataFrame(rows, columns=["draw_id","time","numbers"]).drop_duplicates("draw_id").sort_values("draw_id").reset_index(drop=True)
    return df

def pairwise_families(df, overlap_min=14):
    sets=[set(x) for x in df.numbers]
    out=[]
    for i in range(len(df)):
        a=sets[i]
        for j in range(i+1,len(df)):
            inter=a & sets[j]
            if len(inter)>=overlap_min:
                out.append({
                    "i":i,"j":j,
                    "draw1":int(df.at[i,"draw_id"]),
                    "time1":df.at[i,"time"],
                    "draw2":int(df.at[j,"draw_id"]),
                    "time2":df.at[j,"time"],
                    "gap_draws":j-i,
                    "overlap":len(inter),
                    "family":tuple(sorted(inter))
                })
    return pd.DataFrame(out)

def occupancy_trace(df, family):
    fam=set(family)
    rows=[]
    for i,r in df.iterrows():
        active=sorted(fam & set(r.numbers))
        rows.append({
            "idx":i, "draw_id":int(r.draw_id), "time":r.time,
            "occupancy":len(active), "active":",".join(map(str,active))
        })
    return pd.DataFrame(rows)

def rising_events(trace, min_start=5, target=8, window=12):
    occ=trace.occupancy.to_numpy()
    ev=[]
    for end in range(len(occ)):
        if occ[end] < target: continue
        lo=max(0,end-window)
        prev=occ[lo:end]
        if len(prev)==0: continue
        # "birleşerek yükselme": önce daha düşük doluluk, hedef elde target+
        best_before=max(prev)
        if best_before < target and best_before >= min_start:
            start_idx=lo + max(k for k,v in enumerate(prev) if v==best_before)
            ev.append({
                "from_draw":int(trace.at[start_idx,"draw_id"]),
                "from_time":trace.at[start_idx,"time"],
                "from_occ":int(occ[start_idx]),
                "to_draw":int(trace.at[end,"draw_id"]),
                "to_time":trace.at[end,"time"],
                "to_occ":int(occ[end]),
                "gap":end-start_idx
            })
    return pd.DataFrame(ev)

uploaded=st.file_uploader("TXT veri dosyasını yükle", type=["txt"])
if uploaded:
    text=uploaded.getvalue().decode("utf-8", errors="ignore")
else:
    st.info("`veri (6).txt` dosyasını buraya yükle. Uygulama veriyi kendi okuyup hesaplayacak.")
    st.stop()

df=parse_txt(text)
c1,c2,c3=st.columns(3)
c1.metric("Çekiliş",len(df))
c2.metric("İlk",f"#{df.draw_id.iloc[0]} — {df.time.iloc[0]}")
c3.metric("Son",f"#{df.draw_id.iloc[-1]} — {df.time.iloc[-1]}")

st.divider()
st.subheader("1) İstisnai üst aileleri bul")
overlap_min=st.slider("İki REAL20 arasında en az kaç ortak sayı?", 10, 18, 14)
if st.button("Üst aileleri tara", type="primary"):
    with st.spinner("Tüm çekiliş çiftleri karşılaştırılıyor..."):
        famdf=pairwise_families(df, overlap_min)
    st.session_state["famdf"]=famdf

famdf=st.session_state.get("famdf")
if famdf is not None:
    st.write(f"Bulunan çift: **{len(famdf):,}**")
    if len(famdf):
        show=famdf[["draw1","time1","draw2","time2","gap_draws","overlap"]].copy()
        st.dataframe(show, use_container_width=True, hide_index=True)

        exact=Counter(famdf.overlap)
        st.write("Örtüşme dağılımı:", dict(sorted(exact.items())))

        options=[]
        for k,r in famdf.iterrows():
            label=f"{k} | {r.overlap}/20 | #{r.draw1} ↔ #{r.draw2} | " + "-".join(map(str,r.family))
            options.append((label,k))
        label=st.selectbox("İncelenecek üst aile", [x[0] for x in options])
        idx=dict(options)[label]
        row=famdf.loc[idx]
        family=row.family

        st.subheader("2) Ailenin kronolojik doluluk yaşamı")
        st.write("Üst aile:", "**"+" - ".join(map(str,family))+"**")
        trace=occupancy_trace(df,family)

        a,b,c,d=st.columns(4)
        a.metric("Aile boyu",len(family))
        b.metric("8+ olduğu el",int((trace.occupancy>=8).sum()))
        c.metric("9+ olduğu el",int((trace.occupancy>=9).sum()))
        d.metric(f"{len(family)}/{len(family)} olduğu el",int((trace.occupancy==len(family)).sum()))

        dist=trace.occupancy.value_counts().sort_index().rename_axis("doluluk").reset_index(name="el")
        st.dataframe(dist, use_container_width=True, hide_index=True)

        st.line_chart(trace.set_index("time")["occupancy"])

        st.subheader("3) Birleşerek 8+'e yükselme")
        window=st.slider("Önceki kaç el içinde yükseliş ara?", 2, 50, 12)
        min_start=st.slider("Başlangıç doluluğu en az", 3, 7, 5)
        rises=rising_events(trace,min_start,8,window)
        st.write(f"Bulunan 8+ birleşme olayı: **{len(rises)}**")
        if len(rises):
            st.dataframe(rises, use_container_width=True, hide_index=True)

        st.subheader("4) 8'li alt kadrolar")
        if len(family)>=8:
            drawsets=[set(x) for x in df.numbers]
            records=[]
            for sub in itertools.combinations(family,8):
                s=set(sub)
                hits=[i for i,x in enumerate(drawsets) if s <= x]
                if len(hits)>=2:
                    records.append({
                        "8li":"-".join(map(str,sub)),
                        "kaç_REAL20":len(hits),
                        "ilk":int(df.at[hits[0],"draw_id"]),
                        "son":int(df.at[hits[-1],"draw_id"]),
                        "yayılım_el":hits[-1]-hits[0]
                    })
            subs=pd.DataFrame(records)
            if len(subs):
                subs=subs.sort_values(["kaç_REAL20","yayılım_el"], ascending=[False,True])
                st.dataframe(subs, use_container_width=True, hide_index=True)
                st.write("En yüksek 8/8 tekrar:", int(subs["kaç_REAL20"].max()))
            else:
                st.write("En az iki REAL20'de komple bulunan 8'li yok.")

        st.subheader("5) Patlamadan ÖNCEKİ yaşam")
        first=min(int(row.i),int(row.j))
        before=trace.iloc[:first]
        if len(before):
            counts={k:int((before.occupancy==k).sum()) for k in range(3,len(family)+1)}
            st.write(counts)
            last=before[before.occupancy>=6].tail(30)
            st.dataframe(last[["draw_id","time","occupancy","active"]],use_container_width=True,hide_index=True)

        st.warning("Bu ekran geçmiş örüntüyü keşfeder. Tahmin gücü için ayrıca yalnız geçmiş bilgiyi kullanan dondurulmuş walk-forward testi gerekir.")
