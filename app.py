
from pathlib import Path
from collections import Counter, defaultdict
import math
import re

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Hızlı On 23:17 Seçici Kupon Motoru",
    page_icon="🎯",
    layout="wide",
)

st.title("🎯 Hızlı On 23:17 — Seçici Kupon Motoru")
st.caption(
    "23:02 + 23:07 + 23:12 sonuçlarını okur; geçmiş gece karakteri, taşıma, "
    "dinlenip dönüş, yaşam yolu, bant ve ardışık yapıyı birleştirir. "
    "Aynı sıralamadan 6'lı, 7'li, 8'li, 9'lu ve 10'lu kupon üretir."
)

DATA_FILE = Path("veri.txt")
SLOTS = ["23:02","23:07","23:12","23:17","23:22","23:27","23:32","23:37","23:42","23:47","23:52","23:57"]
TARGET = "23:17"
INPUTS = ["23:02","23:07","23:12"]
BASE = 20/80


# ============================================================
# VERİ
# ============================================================
def parse_pipe_text(text):
    rows=[]
    for raw in str(text).splitlines():
        p=[x.strip() for x in raw.split("|")]
        if len(p)<3:
            continue
        try:
            no=int(p[0])
            d,t=p[1].split()
            nums=sorted(set(int(x) for x in re.findall(r"\d+", p[2])))
        except Exception:
            continue
        if t not in SLOTS or len(nums)!=20 or any(n<1 or n>80 for n in nums):
            continue
        rows.append({"draw_no":no,"date":d,"time":t,"numbers":nums})
    df=pd.DataFrame(rows)
    if df.empty:
        return df
    df["_dt"]=pd.to_datetime(df["date"]+" "+df["time"],format="%d.%m.%Y %H:%M",errors="coerce")
    df=df.dropna(subset=["_dt"])
    return (
        df.sort_values(["_dt","draw_no"])
        .drop_duplicates(["date","time"],keep="last")
        .reset_index(drop=True)
    )

def load_df():
    up=st.sidebar.file_uploader("İstersen veri.txt yükle",type=["txt","csv"])
    if up is not None:
        txt=up.getvalue().decode("utf-8",errors="ignore")
        return parse_pipe_text(txt), f"Yüklenen: {up.name}"
    if DATA_FILE.exists():
        return parse_pipe_text(DATA_FILE.read_text(encoding="utf-8")), "Repo veri.txt"
    return pd.DataFrame(), "Veri yok"


# ============================================================
# YARDIMCILAR
# ============================================================
def day_map(df):
    out={}
    for _,r in df.iterrows():
        out.setdefault(str(r["date"]),{})[str(r["time"])]=set(r["numbers"])
    return out

def ordered_dates(df):
    return list(dict.fromkeys(df["date"].astype(str).tolist()))

def path3(n,s02,s07,s12):
    return f"{int(n in s02)}{int(n in s07)}{int(n in s12)}"

def life_label(path):
    return {
        "001":"23:12'DE DOĞDU",
        "011":"07→12 DEVAM",
        "111":"3 EL DEVAM",
        "101":"GERİ DÖNDÜ",
        "110":"12'DE SÖNDÜ",
        "010":"23:07 TEK",
        "100":"23:02 SONRA UYKU",
        "000":"İLK 3 EL YOK"
    }.get(path,path)

def band(n):
    return (n-1)//10

def consecutive_neighbor_score(n,s12):
    return int((n-1) in s12) + int((n+1) in s12)

def prev_night_signature(n, prev_day):
    if not prev_day:
        return "0000"
    slots=["23:42","23:47","23:52","23:57"]
    return "".join("1" if n in prev_day.get(s,set()) else "0" for s in slots)

def safe_shrink(h,n,prior=BASE,strength=16):
    return (h + prior*strength)/(n+strength)

def candidate_table(train):
    dm=day_map(train)
    dates=ordered_dates(train)
    if not dates:
        raise ValueError("Veri yok.")
    d=dates[-1]
    if not all(s in dm.get(d,{}) for s in INPUTS):
        miss=[s for s in INPUTS if s not in dm.get(d,{})]
        raise ValueError("23:17 için önce şu sonuçlar gerekli: "+", ".join(miss))

    current=dm[d]
    s02,s07,s12=[current[s] for s in INPUTS]
    prev_day=dm[dates[-2]] if len(dates)>=2 else {}

    # Yalnız hedefi geçmişte tamamlanmış günler
    hist=[]
    for hd in dates[:-1]:
        if all(s in dm.get(hd,{}) for s in INPUTS+[TARGET]):
            hist.append(hd)
    if len(hist)<18:
        raise ValueError("En az 18 tamamlanmış 23:17 geçmiş günü gerekli.")

    # Son günlere biraz daha fazla ağırlık
    recency_weight={}
    L=len(hist)
    for i,hd in enumerate(hist):
        age=L-1-i
        recency_weight[hd]=math.exp(-age/32.0)

    rows=[]
    for n in range(1,81):
        p=path3(n,s02,s07,s12)
        in12=n in s12
        night=prev_night_signature(n,prev_day)

        # kanallar
        path_h=path_n=0.0
        night_h=night_n=0.0
        side_h=side_n=0.0
        id_h=id_n=0.0
        band_h=band_n=0.0
        carry_state_h=carry_state_n=0.0

        for hd in hist:
            w=recency_weight[hd]
            hday=dm[hd]
            a,b,c,y=[hday[s] for s in INPUTS+[TARGET]]
            hp=path3(n,a,b,c)
            hit=int(n in y)

            if hp==p:
                path_h += w*hit
                path_n += w

            if (n in c)==in12:
                side_h += w*hit
                side_n += w

            # önceki gecedeki aynı 4-bit imza
            hi=dates.index(hd)
            hprev=dm[dates[hi-1]] if hi>0 else {}
            hn=prev_night_signature(n,hprev)
            if hn==night:
                night_h += w*hit
                night_n += w

            # sayı kimliği zayıf kanal
            id_h += w*hit
            id_n += w

            # aynı bant yoğunluğu bağlamı
            now_band_count=sum(band(x)==band(n) for x in s12)
            hist_band_count=sum(band(x)==band(n) for x in c)
            if hist_band_count==now_band_count:
                band_h += w*hit
                band_n += w

            # 23:12 kaynakta ise yaşam yolunu ayrıca öğren
            if in12 and hp==p:
                carry_state_h += w*hit
                carry_state_n += w

        r_path=safe_shrink(path_h,path_n,BASE,12)
        r_night=safe_shrink(night_h,night_n,BASE,18)
        r_side=safe_shrink(side_h,side_n,BASE,24)
        r_id=safe_shrink(id_h,id_n,BASE,36)
        r_band=safe_shrink(band_h,band_n,BASE,22)
        r_carry=safe_shrink(carry_state_h,carry_state_n,r_path,10) if in12 else r_path

        # Kanıt gücü: destek yoksa yüksek skor cezalandırılır
        support=path_n + 0.55*night_n + 0.35*band_n
        reliability=math.sqrt(support/(support+18.0)) if support>0 else 0.0

        # Ana skor
        raw = (
            0.40*r_path +
            0.18*r_night +
            0.14*r_side +
            0.10*r_band +
            0.08*r_id +
            0.10*r_carry
        )

        # 23:12 kaynakta/olmayanlar için hafif yaşam düzeltmesi
        if p=="111":
            raw -= 0.012   # uzamış seriyi körlemesine ödüllendirme
        elif p in ("001","101"):
            raw += 0.010   # yeni doğum / geri dönüş penceresi
        elif p=="110":
            raw -= 0.008

        neigh=consecutive_neighbor_score(n,s12)
        raw += 0.004*neigh

        evidence = BASE + (raw-BASE)*reliability

        rows.append({
            "Sayı":n,
            "Kaynakta12":in12,
            "3-El Yol":p,
            "Yaşam":life_label(p),
            "Gece İzi":night,
            "Yol":r_path,
            "Gece":r_night,
            "Taraf":r_side,
            "Bant":r_band,
            "Kimlik":r_id,
            "Komşu":neigh,
            "Destek":support,
            "Ham":raw,
            "Kanıt":evidence
        })

    tab=pd.DataFrame(rows)

    # Taşıma ve dönüş ayrı lig
    tab["Taşıma Sıra"]=999
    tab["Dönüş Sıra"]=999
    cidx=tab.index[tab["Kaynakta12"]]
    ridx=tab.index[~tab["Kaynakta12"]]
    tab.loc[cidx,"Taşıma Sıra"]=tab.loc[cidx,"Kanıt"].rank(ascending=False,method="first").astype(int)
    tab.loc[ridx,"Dönüş Sıra"]=tab.loc[ridx,"Kanıt"].rank(ascending=False,method="first").astype(int)

    # Geçmiş gerçek 23:12->23:17 taşıma ortalaması
    carr=[]
    for hd in hist[-60:]:
        carr.append(len(dm[hd]["23:12"] & dm[hd]["23:17"]))
    exp_carry=float(np.mean(carr)) if carr else 5.0

    return tab.sort_values(["Kanıt","Ham"],ascending=False).reset_index(drop=True), exp_carry, d


def make_nested_tickets(tab, exp_carry):
    """
    6/7/8/9/10 kuponları tek sıralamadan ama taşıma/dönüş dengesi korunarak üretir.
    Küçük kuponlarda yalnız en güçlü kanıtlar kalır.
    """
    out={}
    carry=tab[tab["Kaynakta12"]].sort_values(["Kanıt","Destek"],ascending=False).reset_index(drop=True)
    ret=tab[~tab["Kaynakta12"]].sort_values(["Kanıt","Destek"],ascending=False).reset_index(drop=True)

    # Gerçek taşıma ortalaması 20 sayı içinde ~5 ise 10'lu kuponda bunun yaklaşık yarısı.
    base_c=int(np.clip(round(exp_carry/2),2,4))

    for size in [6,7,8,9,10]:
        # küçük kupon daha seçici; taşıma koltuğu da boyuta göre ölçeklenir
        cseats=int(np.clip(round(base_c*size/10),1,min(4,size-2)))
        rseats=size-cseats
        cand=pd.concat([carry.head(cseats),ret.head(rseats)])
        cand=cand.sort_values(["Kanıt","Destek"],ascending=False)
        out[size]=cand["Sayı"].astype(int).tolist()
    return out


def confidence_summary(tab,tickets):
    top=tab.sort_values("Kanıt",ascending=False).reset_index(drop=True)
    q={}
    for size,t in tickets.items():
        x=top[top["Sayı"].isin(t)]["Kanıt"]
        q[size]=float(x.mean()) if len(x) else BASE
    # öneri: küçük kuponun ortalama kanıtı bariz daha yüksekse küçük kupon
    ordered=sorted(q.items(), key=lambda z:z[1], reverse=True)
    return q, ordered[0][0]


def walk_forward(df, ntest=60):
    dm=day_map(df)
    dates=ordered_dates(df)
    eligible=[d for d in dates if all(s in dm.get(d,{}) for s in INPUTS+[TARGET])]
    eligible=eligible[-ntest:]

    rows=[]
    for d in eligible:
        target_dt=pd.to_datetime(d+" 23:17",format="%d.%m.%Y %H:%M")
        dts=pd.to_datetime(df["date"]+" "+df["time"],format="%d.%m.%Y %H:%M")
        train=df[dts<target_dt].reset_index(drop=True)
        try:
            tab,exp,_=candidate_table(train)
            tickets=make_nested_tickets(tab,exp)
        except Exception:
            continue
        actual=dm[d][TARGET]
        row={"Tarih":d}
        for size,t in tickets.items():
            row[f"{size}li"]=len(set(t)&actual)
        rows.append(row)
    return pd.DataFrame(rows)


# ============================================================
# UI
# ============================================================
df,source=load_df()
if df.empty:
    st.error("veri.txt bulunamadı veya okunamadı.")
    st.stop()

st.caption(
    f"📂 {source} · {len(df)} çekiliş · {df['date'].nunique()} gece · "
    f"son: #{df.iloc[-1]['draw_no']} {df.iloc[-1]['date']} {df.iloc[-1]['time']}"
)

tabs=st.tabs(["🏆 Kuponlar","🔬 Neden Seçildi?","🧪 Boyut Testi"])

with tabs[0]:
    st.subheader("🏆 23:17 Kuponları")
    try:
        tab,exp,target_date=candidate_table(df)
        tickets=make_nested_tickets(tab,exp)
        q,recommended=confidence_summary(tab,tickets)

        c1,c2,c3=st.columns(3)
        c1.metric("Hedef",f"{target_date} 23:17")
        c2.metric("Beklenen gerçek taşıma",f"{exp:.2f}/20")
        c3.metric("Önerilen boyut",f"{recommended}'li")

        st.info(
            "Kuponlar aynı aday sıralamasından türetilir. Küçük kupon daha seçicidir; "
            "10'lu kupon daha fazla aday kapsar. Hiçbiri isabet garantisi değildir."
        )

        for size in [6,7,8,9,10]:
            label=" ⭐ ÖNERİLEN" if size==recommended else ""
            st.markdown(f"### 🎯 {size}'Lİ KUPON{label}")
            st.code("  ".join(f"{n:02d}" for n in tickets[size]))
            st.caption(f"Ortalama kanıt skoru: {q[size]:.3f}")

    except Exception as e:
        st.warning(str(e))
        st.info("23:02 → 23:07 → 23:12 sonuçlarını veri.txt'ye ekle; sonra kuponlar açılır.")

with tabs[1]:
    st.subheader("🔬 Adayların Ayrışımı")
    try:
        tab,exp,_=candidate_table(df)
        show=tab.copy()
        for c in ["Yol","Gece","Taraf","Bant","Kimlik","Ham","Kanıt","Destek"]:
            show[c]=show[c].map(lambda x:round(float(x),3))
        st.dataframe(
            show[[
                "Sayı","Kaynakta12","3-El Yol","Yaşam","Gece İzi",
                "Yol","Gece","Taraf","Bant","Kimlik","Komşu",
                "Destek","Kanıt","Taşıma Sıra","Dönüş Sıra"
            ]],
            use_container_width=True,
            hide_index=True
        )
    except Exception as e:
        st.warning(str(e))

with tabs[2]:
    st.subheader("🧪 6/7/8/9/10 Walk-Forward Karşılaştırması")
    ntest=st.slider("Son kaç 23:17 hedef günü?",20,120,60,10)
    if st.button("🧪 TEST ET",use_container_width=True):
        bt=walk_forward(df,ntest)
        if bt.empty:
            st.warning("Test üretilemedi.")
        else:
            metrics=[]
            for size in [6,7,8,9,10]:
                col=f"{size}li"
                metrics.append({
                    "Boyut":f"{size}'li",
                    "Ort İsabet":round(bt[col].mean(),2),
                    "3+ %":round(100*(bt[col]>=3).mean(),1),
                    "4+ %":round(100*(bt[col]>=4).mean(),1),
                    "5+ %":round(100*(bt[col]>=5).mean(),1),
                    "En İyi":int(bt[col].max()),
                })
            st.dataframe(pd.DataFrame(metrics),use_container_width=True,hide_index=True)
            st.markdown("#### Gün gün sonuç")
            st.dataframe(bt.iloc[::-1],use_container_width=True,hide_index=True)

st.caption(
    "Amaç, kupon boyutunu küçültürken kanıt yoğunluğunu artırmaktır. "
    "Geçmiş performans gelecekteki bağımsız çekilişleri garanti etmez."
)
