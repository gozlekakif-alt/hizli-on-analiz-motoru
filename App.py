from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from collections import Counter, defaultdict
from itertools import combinations
import io
import math
import re

import numpy as np
import pandas as pd
import streamlit as st

# ============================================================
# HIZLI ON — MASTER APP V2
# ANA AMAÇ:
# Her hedef çekilişten ÖNCE 1–80'in yaşam fotoğrafını çıkar.
# Sonuç geldikten sonra yalnızca çıktı/çıkmadı etiketini ekle.
# Gerçek 20'nin hangi çoklu kimliklerden oluştuğunu ve aynı anda
# aynı/benzer kimlikte başka hangi sayıların bulunduğunu göster.
# ============================================================

st.set_page_config(page_title="Hızlı On — Yaşam Kimliği MASTER V2", page_icon="🧬", layout="wide")

NUMBERS = list(range(1, 81))
BASE_RATE = 20 / 80
TEMP_DECAY = 0.5 ** (1 / 12)
K_COUNT = 8
BANDS = [(1,10),(11,20),(21,30),(31,40),(41,50),(51,60),(61,70),(71,80)]
POOL_STEPS = [80,70,60,50,40,35,30,25,20]

# --------------------------- DATA PARSER ---------------------------

def _extract_draw_blocks(text: str):
    """Çeşitli kullanıcı formatlarını tek tek çekiliş kayıtlarına dönüştürür."""
    text = text.replace("\r", "\n")

    # 1) CekilisNo;Saat;1,2,... formatı
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^\s*(\d{4,6})\s*[;|]\s*(?:(\d{1,2}\.\d{1,2}\.\d{4})\s+)?(\d{1,2}:\d{2})\s*[;|]\s*(.*)$", s)
        if m:
            draw_no = int(m.group(1))
            date = m.group(2)
            time = m.group(3)
            nums = [int(x) for x in re.findall(r"\d+", m.group(4))]
            if len(nums) >= 20:
                rows.append((draw_no, date, time, nums[:20]))
    if rows:
        return rows

    # 2) Çekiliş no: ... blok formatı
    pattern = re.compile(
        r"Çekiliş\s*no\s*:\s*(\d+).*?(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}:\d{2})(.*?)(?=Çekiliş\s*no\s*:|\Z)",
        re.I | re.S,
    )
    for m in pattern.finditer(text):
        draw_no = int(m.group(1)); date = m.group(2); time = m.group(3)
        nums = [int(x) for x in re.findall(r"\b(?:[1-9]|[1-7]\d|80)\b", m.group(4))]
        if len(nums) >= 20:
            rows.append((draw_no, date, time, nums[:20]))
    return rows


def parse_text(text: str) -> pd.DataFrame:
    rows = _extract_draw_blocks(text)
    out = []
    for draw_no, date, time, nums in rows:
        nums = sorted(set(nums))
        if len(nums) != 20 or any(n < 1 or n > 80 for n in nums):
            continue
        out.append({"draw_no": draw_no, "date": date or "", "time": time, "nums": nums})
    df = pd.DataFrame(out)
    if df.empty:
        return pd.DataFrame(columns=["draw_no","date","time","nums"])
    df = df.drop_duplicates("draw_no").sort_values("draw_no").reset_index(drop=True)
    return df


def merge_frames(*dfs):
    valid = [x for x in dfs if x is not None and not x.empty]
    if not valid:
        return pd.DataFrame(columns=["draw_no","date","time","nums"])
    return pd.concat(valid, ignore_index=True).drop_duplicates("draw_no").sort_values("draw_no").reset_index(drop=True)


def validate(df: pd.DataFrame):
    issues=[]
    if df.empty:
        return ["Geçerli çekiliş bulunamadı."]
    for i,r in df.iterrows():
        if len(r.nums)!=20 or len(set(r.nums))!=20:
            issues.append(f"#{r.draw_no}: 20 benzersiz sayı değil")
        if any(n<1 or n>80 for n in r.nums):
            issues.append(f"#{r.draw_no}: 1–80 dışı sayı")
    return issues

# --------------------------- HELPERS ---------------------------

def draw_sets(df):
    return [set(x) for x in df["nums"]]


def band_id(n):
    return (n-1)//10 + 1


def band_label(n):
    a,b=BANDS[band_id(n)-1]
    return f"B{band_id(n)}:{a}-{b}"


def kvar_from_time(t: str):
    """Günü 8 eşit saat fazına yaklaşık böler; veri saati mevcut değilse 1."""
    try:
        h,m = map(int, str(t).split(":"))
        mins=h*60+m
        return min(8, mins//180 + 1)
    except Exception:
        return 1


def last_presence_path(sets, i, n, k):
    vals=[]
    for j in range(max(0,i-k), i):
        vals.append("1" if n in sets[j] else "0")
    return "".join(vals).rjust(k,"0")


def gap_age(sets, i, n):
    if i<=0:
        return None
    c=0
    for j in range(i-1,-1,-1):
        if n in sets[j]:
            return c
        c+=1
    return c


def prev_hit(sets,i,n,h):
    j=i-h
    return int(j>=0 and n in sets[j])


def recurrence_class(gap):
    if gap is None:
        return "NEW_UNKNOWN"
    if gap==0: return "CARRY"
    if gap==1: return "H2"
    if gap==2: return "H3"
    if 3<=gap<=5: return "KISA"
    if 6<=gap<=11: return "ORTA"
    if 12<=gap<=23: return "UZUN"
    return "DERIN"


def exp_temperature(sets, i):
    scores=np.zeros(80,float)
    w=1.0
    for j in range(i-1,-1,-1):
        for n in sets[j]:
            scores[n-1]+=w
        w*=TEMP_DECAY
        if w<1e-5:
            break
    return scores


def temp_layers(scores):
    order=np.argsort(-scores)
    layer=np.empty(80,object)
    labs=["YS"]*20+["OY"]*20+["OD"]*20+["S"]*20
    for idx,lab in zip(order,labs):
        layer[idx]=lab
    return layer


def temp_history(sets,i):
    now=exp_temperature(sets,i)
    prev=exp_temperature(sets,max(0,i-1)) if i>0 else np.zeros(80)
    lay_now=temp_layers(now) if i>0 else np.array(["S"]*80,object)
    lay_prev=temp_layers(prev) if i>1 else np.array(["S"]*80,object)
    return now,prev,lay_now,lay_prev


def consecutive_blocks(nums):
    nums=sorted(nums)
    if not nums: return []
    out=[]; cur=[nums[0]]
    for x in nums[1:]:
        if x==cur[-1]+1: cur.append(x)
        else:
            if len(cur)>=2: out.append(cur)
            cur=[x]
    if len(cur)>=2: out.append(cur)
    return out


def neighbor_state(sets,i,n):
    if i<=0: return "00"
    prev=sets[i-1]
    return f"{int(n-1 in prev)}{int(n+1 in prev)}"


def corridor_state(sets,i,n):
    if i<=0: return 0
    prev=sets[i-1]
    return sum(x in prev for x in (n-2,n-1,n+1,n+2) if 1<=x<=80)


def social_features(sets,i,n,lookback=24):
    """Geçmiş son lookback elde n ile birlikte en sık yaşayan partnerler."""
    start=max(0,i-lookback)
    pair=Counter(); appearances=0
    for j in range(start,i):
        s=sets[j]
        if n in s:
            appearances+=1
            for m in s:
                if m!=n: pair[m]+=1
    tops=pair.most_common(3)
    return appearances, ",".join(str(x) for x,_ in tops), sum(c for _,c in tops)


def band_pressure(sets,i,bid,short=3,long=12):
    def count(j):
        a,b=BANDS[bid-1]
        return sum(a<=n<=b for n in sets[j])
    if i<=0: return 0.0,0.0,0.0
    recent=[count(j) for j in range(max(0,i-short),i)]
    older=[count(j) for j in range(max(0,i-long),max(0,i-short))]
    r=float(np.mean(recent)) if recent else 0.0
    o=float(np.mean(older)) if older else r
    return r,o,r-o


def block_context(sets,i,n):
    if i<=0: return {"prev_block_member":0,"prev_block_len":0,"block_corridor_age":0}
    prev_blocks=consecutive_blocks(sets[i-1])
    member=0; blen=0
    for b in prev_blocks:
        if n in b or n-1 in b or n+1 in b:
            member=1; blen=max(blen,len(b))
    age=0
    for j in range(i-1,max(-1,i-7),-1):
        bs=consecutive_blocks(sets[j])
        if any(any(abs(x-n)<=1 for x in b) for b in bs):
            break
        age+=1
    return {"prev_block_member":member,"prev_block_len":blen,"block_corridor_age":age}

# --------------------------- SNAPSHOT ENGINE ---------------------------

def build_pre_snapshot(df: pd.DataFrame, i: int) -> pd.DataFrame:
    """Target i sonucunu ASLA kullanmaz. Yalnız 0..i-1 geçmişinden 80 sayı fotoğrafı."""
    sets=draw_sets(df)
    if i<=0:
        raise ValueError("PRE-H snapshot için en az bir önceki çekiliş gerekli")

    temp_now,temp_prev,lay_now,lay_prev=temp_history(sets,i)
    rows=[]
    time=str(df.iloc[i]["time"])
    kval=kvar_from_time(time)

    for n in NUMBERS:
        g=gap_age(sets,i,n)
        rec=recurrence_class(g)
        bid=band_id(n)
        bp3,bp12,bdelta=band_pressure(sets,i,bid)
        app24,partners,social_strength=social_features(sets,i,n,24)
        bc=block_context(sets,i,n)
        layer=str(lay_now[n-1])
        prev_layer=str(lay_prev[n-1])
        slope=float(temp_now[n-1]-temp_prev[n-1])
        if slope>1e-9: slope_dir="UP"
        elif slope<-1e-9: slope_dir="DOWN"
        else: slope_dir="FLAT"

        rows.append({
            "target_index":i,
            "target_draw_no":int(df.iloc[i]["draw_no"]),
            "target_date":str(df.iloc[i]["date"]),
            "target_time":time,
            "number":n,
            "band":band_label(n),
            "band_id":bid,
            "K_phase":f"K{kval}",
            "gap":g,
            "recurrence":rec,
            "H1":prev_hit(sets,i,n,1),
            "H2":prev_hit(sets,i,n,2),
            "H3":prev_hit(sets,i,n,3),
            "path1":last_presence_path(sets,i,n,1),
            "path2":last_presence_path(sets,i,n,2),
            "path3":last_presence_path(sets,i,n,3),
            "path4":last_presence_path(sets,i,n,4),
            "path6":last_presence_path(sets,i,n,6),
            "path12":last_presence_path(sets,i,n,12),
            "path24":last_presence_path(sets,i,n,24),
            "hits6":sum(n in sets[j] for j in range(max(0,i-6),i)),
            "hits12":sum(n in sets[j] for j in range(max(0,i-12),i)),
            "hits24":sum(n in sets[j] for j in range(max(0,i-24),i)),
            "temperature":float(temp_now[n-1]),
            "temperature_prev":float(temp_prev[n-1]),
            "temp_layer":layer,
            "temp_prev_layer":prev_layer,
            "temp_migration":f"{prev_layer}->{layer}",
            "temp_slope":slope,
            "temp_slope_dir":slope_dir,
            "neighbor_H1":neighbor_state(sets,i,n),
            "corridor_H1_count":corridor_state(sets,i,n),
            "band_pressure_short":bp3,
            "band_pressure_long":bp12,
            "band_pressure_delta":bdelta,
            "social_appearances24":app24,
            "social_top3":partners,
            "social_strength":social_strength,
            **bc,
        })
    return pd.DataFrame(rows)


def attach_post_label(snapshot: pd.DataFrame, actual_nums):
    out=snapshot.copy()
    actual=set(actual_nums)
    out["actual"] = out["number"].isin(actual).astype(int)
    return out

# --------------------------- IDENTITY SIGNATURES ---------------------------
CORE_ID_COLS=[
    "recurrence","temp_layer","temp_migration","temp_slope_dir","K_phase","band_id",
    "neighbor_H1","corridor_H1_count","prev_block_member"
]

DETAIL_ID_COLS=CORE_ID_COLS + [
    "path3","path6","hits6","hits12","band_pressure_delta","block_corridor_age"
]


def identity_key(row, detail=False):
    cols=DETAIL_ID_COLS if detail else CORE_ID_COLS
    vals=[]
    for c in cols:
        v=row[c]
        if c=="band_pressure_delta":
            v = "UP" if v>0.25 else "DOWN" if v<-0.25 else "FLAT"
        vals.append(f"{c}={v}")
    return " | ".join(vals)


def add_identity_keys(df):
    x=df.copy()
    x["identity_core"]=[identity_key(r,False) for _,r in x.iterrows()]
    x["identity_detail"]=[identity_key(r,True) for _,r in x.iterrows()]
    return x


def same_identity_report(labeled: pd.DataFrame, number: int):
    x=add_identity_keys(labeled)
    row=x[x.number==number].iloc[0]
    core=row.identity_core; detail=row.identity_detail
    same_core=x[x.identity_core==core].copy()
    same_detail=x[x.identity_detail==detail].copy()
    return {
        "number":number,
        "core":core,
        "detail":detail,
        "same_core":same_core,
        "same_detail":same_detail,
    }

# --------------------------- REAL-20 ANATOMY ---------------------------

def real20_anatomy(labeled: pd.DataFrame):
    hit=labeled[labeled.actual==1].copy()
    if hit.empty: return {}, pd.DataFrame()
    summary={
        "CARRY":int((hit.recurrence=="CARRY").sum()),
        "H2":int((hit.recurrence=="H2").sum()),
        "H3":int((hit.recurrence=="H3").sum()),
        "KISA":int((hit.recurrence=="KISA").sum()),
        "ORTA":int((hit.recurrence=="ORTA").sum()),
        "UZUN":int((hit.recurrence=="UZUN").sum()),
        "DERIN":int((hit.recurrence=="DERIN").sum()),
        "YS":int((hit.temp_layer=="YS").sum()),
        "OY":int((hit.temp_layer=="OY").sum()),
        "OD":int((hit.temp_layer=="OD").sum()),
        "S":int((hit.temp_layer=="S").sum()),
        "TEMP_UP":int((hit.temp_slope_dir=="UP").sum()),
        "TEMP_DOWN":int((hit.temp_slope_dir=="DOWN").sum()),
        "BLOCK_CTX":int((hit.prev_block_member==1).sum()),
        "NEIGHBOR_ACTIVE":int((hit.neighbor_H1!="00").sum()),
    }
    return summary, hit


def anatomy_timeseries(df, start_i=1):
    rows=[]
    for i in range(max(1,start_i),len(df)):
        snap=build_pre_snapshot(df,i)
        lab=attach_post_label(snap,df.iloc[i].nums)
        summary,_=real20_anatomy(lab)
        summary.update({"draw_no":int(df.iloc[i].draw_no),"date":df.iloc[i].date,"time":df.iloc[i].time})
        rows.append(summary)
    return pd.DataFrame(rows)

# --------------------------- NUMBER-SPECIFIC MEMORY ---------------------------

def number_memory(df, n, min_i=24):
    rows=[]
    for i in range(max(1,min_i),len(df)):
        snap=build_pre_snapshot(df,i)
        row=snap[snap.number==n].iloc[0].to_dict()
        row["actual"]=int(n in set(df.iloc[i].nums))
        rows.append(row)
    return add_identity_keys(pd.DataFrame(rows)) if rows else pd.DataFrame()


def signature_stats(mem: pd.DataFrame, key_col="identity_core", min_cases=3):
    if mem.empty: return pd.DataFrame()
    g=mem.groupby(key_col).actual.agg(["count","sum","mean"]).reset_index()
    g=g[g["count"]>=min_cases].copy()
    g["lift_vs_base"]=g["mean"]-BASE_RATE
    return g.sort_values(["lift_vs_base","count"],ascending=[False,False])

# --------------------------- BLIND POOL TEST ---------------------------

def score_from_history(history: pd.DataFrame, target_snapshot: pd.DataFrame):
    """Yalnız geçmiş etiketli snapshotlardan kimlik oranlarını öğrenir."""
    if history.empty:
        x=target_snapshot.copy(); x["score"]=0.0; return x
    hist=add_identity_keys(history)
    tgt=add_identity_keys(target_snapshot)

    core=hist.groupby("identity_core").actual.agg(["count","mean"])
    # sayı özel recurrence x temp katmanı küçük hafıza
    ns=hist.groupby(["number","recurrence","temp_layer"]).actual.agg(["count","mean"])

    scores=[]
    for _,r in tgt.iterrows():
        c=core.loc[r.identity_core] if r.identity_core in core.index else None
        if c is None:
            c_mean=BASE_RATE; c_n=0
        else:
            c_mean=float(c["mean"]); c_n=int(c["count"])
        key=(r.number,r.recurrence,r.temp_layer)
        if key in ns.index:
            z=ns.loc[key]; n_mean=float(z["mean"]); n_n=int(z["count"])
        else:
            n_mean=BASE_RATE; n_n=0
        # shrinkage, tek kaba motor değildir; yalnız BLIND havuz testinin sıralama metriği
        sc=((c_mean*min(c_n,20)+BASE_RATE*10)/(min(c_n,20)+10) +
            (n_mean*min(n_n,12)+BASE_RATE*8)/(min(n_n,12)+8))/2
        scores.append(sc)
    tgt["score"]=scores
    return tgt.sort_values(["score","number"],ascending=[False,True])


def walk_forward_pool(df, start_i=60):
    history=[]; rows=[]
    for i in range(1,len(df)):
        snap=build_pre_snapshot(df,i)
        if i>=start_i and history:
            hist=pd.concat(history,ignore_index=True)
            scored=score_from_history(hist,snap)
            actual=set(df.iloc[i].nums)
            rec={"draw_no":int(df.iloc[i].draw_no),"time":df.iloc[i].time}
            for k in POOL_STEPS:
                top=set(scored.head(k).number)
                rec[f"hit_{k}"]=len(top & actual)
            rows.append(rec)
        lab=attach_post_label(snap,df.iloc[i].nums)
        history.append(lab)
    return pd.DataFrame(rows)

# --------------------------- EXPORTS ---------------------------

def to_csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8-sig")


def architecture_report_text(df, i, labeled):
    summary,hit=real20_anatomy(labeled)
    lines=[]
    r=df.iloc[i]
    lines.append(f"HIZLI ON MASTER V2 — ÇEKİLİŞ #{int(r.draw_no)} {r.date} {r.time}")
    lines.append("PRE-H snapshot: hedef sonucu kullanılmadan üretildi.")
    lines.append("")
    lines.append("GERÇEK 20 KARAKTER BÜTÇESİ")
    for k,v in summary.items(): lines.append(f"{k}: {v}")
    lines.append("")
    lines.append("GERÇEK 20 SAYI KİMLİKLERİ")
    hit=add_identity_keys(hit)
    for _,x in hit.sort_values("number").iterrows():
        lines.append(f"{int(x.number)} :: {x.identity_detail}")
    return "\n".join(lines)

# --------------------------- UI ---------------------------
st.title("🧬 Hızlı On — Yaşam Kimliği MASTER APP V2")
st.caption("Gerçek 20'nin en küçük kimlik ayrıntısını çıkarır; aynı anda aynı/benzer kimlikte bulunan diğer sayıları negatif kontrol olarak gösterir. PRE-H → POST-H ayrımı zorunludur.")

with st.sidebar:
    st.header("Veri")
    ups=st.file_uploader("TXT dosyalarını yükle",type=["txt"],accept_multiple_files=True)
    pasted=st.text_area("İstersen çekilişleri buraya topluca yapıştır",height=180)

frames=[]
for f in ups or []:
    frames.append(parse_text(f.getvalue().decode("utf-8",errors="ignore")))
if pasted.strip():
    frames.append(parse_text(pasted))
df=merge_frames(*frames)

if df.empty:
    st.info("Analiz için Hızlı On TXT verisini yükle veya çekilişleri metin alanına yapıştır.")
    st.stop()

issues=validate(df)
if issues:
    st.error("\n".join(issues[:30]))
    st.stop()

c1,c2,c3,c4=st.columns(4)
c1.metric("Çekiliş",len(df))
c2.metric("İlk",int(df.iloc[0].draw_no))
c3.metric("Son",int(df.iloc[-1].draw_no))
c4.metric("Gün",df.date.nunique() if "date" in df else 0)

# Hedef seçim
options=[f"#{int(r.draw_no)} | {r.date} {r.time}" for _,r in df.iloc[1:].iterrows()]
sel=st.selectbox("İncelenecek gerçek çekiliş",options,index=len(options)-1)
sel_draw=int(re.search(r"#(\d+)",sel).group(1))
i=int(df.index[df.draw_no==sel_draw][0])

snap=build_pre_snapshot(df,i)
labeled=attach_post_label(snap,df.iloc[i].nums)
labeled=add_identity_keys(labeled)
summary,real20=real20_anatomy(labeled)

# Invariant checks
st.success(f"PRE-H fotoğraf: {len(snap)} sayı | POST-H gerçek etiket: {int(labeled.actual.sum())}/20")

T1,T2,T3,T4,T5,T6=st.tabs([
    "🎯 Gerçek 20 Anatomisi",
    "🧬 Aynı Kimlik / Negatif 60",
    "🌊 Karakter Salınımı",
    "🔢 Sayı Özel Hafıza",
    "🧪 Kör Havuz Testi",
    "💾 Rapor / Dışa Aktar",
])

with T1:
    st.subheader("Gerçek 20 — karakter bütçesi")
    cols=st.columns(7)
    keys=["CARRY","H2","H3","KISA","ORTA","UZUN","DERIN"]
    for c,k in zip(cols,keys): c.metric(k,summary.get(k,0))
    cols=st.columns(8)
    for c,k in zip(cols,["YS","OY","OD","S","TEMP_UP","TEMP_DOWN","BLOCK_CTX","NEIGHBOR_ACTIVE"]):
        c.metric(k,summary.get(k,0))

    display_cols=["number","recurrence","gap","temp_layer","temp_migration","temp_slope_dir","K_phase","band","path6","hits12","neighbor_H1","corridor_H1_count","band_pressure_delta","prev_block_member","prev_block_len","social_top3","identity_detail"]
    st.dataframe(real20[display_cols].sort_values("number"),use_container_width=True,height=620)

with T2:
    n=st.selectbox("Gerçek 20 içinden sayı seç",sorted(real20.number.tolist()))
    rep=same_identity_report(labeled,int(n))
    st.markdown("**Seçilen sayının çekirdek kimliği**")
    st.code(rep["core"])
    st.markdown("**Detay kimliği**")
    st.code(rep["detail"])

    a,b=st.columns(2)
    with a:
        st.metric("Aynı çekirdek kimlikte sayı",len(rep["same_core"]))
        st.metric("Bunlardan çıkan",int(rep["same_core"].actual.sum()))
        st.dataframe(rep["same_core"][["number","actual","recurrence","temp_layer","temp_migration","band","K_phase"]],use_container_width=True)
    with b:
        st.metric("Aynı detay kimlikte sayı",len(rep["same_detail"]))
        st.metric("Bunlardan çıkan",int(rep["same_detail"].actual.sum()))
        st.dataframe(rep["same_detail"][["number","actual","identity_detail"]],use_container_width=True)

    st.subheader("Gerçek 20 ile negatif 60 aynı anda")
    st.dataframe(labeled[["number","actual","recurrence","gap","temp_layer","temp_migration","K_phase","band","neighbor_H1","corridor_H1_count","prev_block_member","identity_core"]],use_container_width=True,height=600)

with T3:
    st.subheader("Çekilişten çekilişe gerçek 20 karakter bütçesi")
    min_i=max(1,i-40)
    ts=anatomy_timeseries(df,min_i)
    if not ts.empty:
        st.dataframe(ts,use_container_width=True,height=460)
        numeric=[c for c in ts.columns if c not in ("draw_no","date","time")]
        chart_cols=st.multiselect("Grafikte gösterilecek karakterler",numeric,default=[x for x in ["CARRY","H2","H3","YS","S","BLOCK_CTX"] if x in numeric])
        if chart_cols:
            st.line_chart(ts.set_index("draw_no")[chart_cols])

    st.subheader("Anlık 8 bant basıncı")
    bp=labeled.groupby("band").agg(
        real20=("actual","sum"),
        short_pressure=("band_pressure_short","mean"),
        long_pressure=("band_pressure_long","mean"),
        delta=("band_pressure_delta","mean")
    ).reset_index()
    st.dataframe(bp,use_container_width=True)

with T4:
    n2=st.selectbox("1–80 sayı özel hafızası",NUMBERS,index=int(real20.iloc[0].number)-1,key="n2")
    mem=number_memory(df,int(n2),min_i=12)
    if mem.empty:
        st.info("Yeterli geçmiş yok.")
    else:
        st.metric("Geçmiş hedef örneği",len(mem))
        st.metric("Doğum",int(mem.actual.sum()))
        st.dataframe(mem[["target_draw_no","target_time","actual","gap","recurrence","temp_layer","temp_migration","path6","hits12","neighbor_H1","band_pressure_delta","identity_core"]].tail(250),use_container_width=True,height=520)
        st.subheader("Tekrarlanan çekirdek kimlikler")
        stats=signature_stats(mem,"identity_core",min_cases=3)
        st.dataframe(stats.head(100),use_container_width=True)

with T5:
    st.caption("Bu bölüm araştırma anatomisinden ayrıdır. Sıralama yalnız geçmiş PRE-H + POST-H örneklerinden öğrenilir; hedef sonucu puan üretiminde kullanılmaz.")
    start=st.slider("Walk-forward başlangıç hedefi",min_value=20,max_value=max(20,len(df)-1),value=min(max(60,20),max(20,len(df)-1)))
    if st.button("Kronolojik kör havuz testini çalıştır"):
        wf=walk_forward_pool(df,start_i=start)
        if wf.empty:
            st.warning("Test için yeterli hedef yok.")
        else:
            st.dataframe(wf,use_container_width=True,height=500)
            means={k:float(wf[f"hit_{k}"].mean()) for k in POOL_STEPS if f"hit_{k}" in wf}
            mcols=st.columns(len(means))
            for c,(k,v) in zip(mcols,means.items()): c.metric(f"80→{k}",f"{v:.2f}/20")
            st.download_button("Walk-forward CSV indir",to_csv_bytes(wf),"walk_forward_master_v2.csv","text/csv")

with T6:
    st.subheader("Dışa aktar")
    st.download_button("Bu hedefin 80 PRE-H snapshot CSV'si",to_csv_bytes(snap),f"preH_{sel_draw}_80.csv","text/csv")
    st.download_button("Bu hedefin 80 POST-H etiketli CSV'si",to_csv_bytes(labeled),f"postH_{sel_draw}_80.csv","text/csv")
    st.download_button("Gerçek 20 kimlik CSV'si",to_csv_bytes(real20),f"real20_identity_{sel_draw}.csv","text/csv")
    report=architecture_report_text(df,i,labeled)
    st.download_button("Gerçek 20 mimari TXT raporu",report.encode("utf-8"),f"real20_mimari_{sel_draw}.txt","text/plain")
    st.text_area("Rapor önizleme",report,height=520)

st.divider()
st.caption("MASTER V2 araştırma kuralı: Önce mimari → gerçek 20 anatomisi → aynı kimlikteki negatifler → sayı özel hafıza → karakter salınımı → kör doğrulama. Kupon üretimi bu sürümde bilinçli olarak yoktur.")
