from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from collections import Counter, defaultdict
from itertools import combinations
import io
import math
import re
import zipfile
import pickle
from collections import defaultdict
import hashlib
import base64
import json
import urllib.request
import urllib.parse

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

st.set_page_config(page_title="Hızlı On — Yaşam Kimliği MASTER V4", page_icon="🧬", layout="wide")

NUMBERS = list(range(1, 81))
BASE_RATE = 20 / 80
TEMP_DECAY = 0.5 ** (1 / 12)
K_COUNT = 8
BANDS = [(1,10),(11,20),(21,30),(31,40),(41,50),(51,60),(61,70),(71,80)]
POOL_STEPS = [80,70,60,50,40,35,30,25,20]
DATA_FILE = Path("veri.txt")
EXPECTED_DAYS = [
    ("25.08.2026", 51213, 51429),
    ("26.08.2026", 51430, 51646),
    ("27.08.2026", 51647, 51863),
    ("28.08.2026", 51864, 52080),
    ("29.08.2026", 52081, 52297),
    ("30.08.2026", 52298, 52514),
    ("31.08.2026", 52515, 52731),
    ("01.09.2026", 52732, 52948),
    ("02.09.2026", 52949, 53165),
    ("03.09.2026", 53166, 53382),
    ("04.09.2026", 53383, 53599),
    ("05.09.2026", 53600, 53816),
    ("06.09.2026", 53817, 54033),
    ("07.09.2026", 54034, 54250),
]

def infer_date_from_draw(draw_no: int) -> str:
    for d,a,b in EXPECTED_DAYS:
        if a <= int(draw_no) <= b:
            return d
    return ""

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
        resolved_date = date or infer_date_from_draw(draw_no)
        out.append({"draw_no": draw_no, "date": resolved_date, "time": time, "nums": nums})
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

def data_health(df: pd.DataFrame):
    expected_total = sum(b-a+1 for _,a,b in EXPECTED_DAYS)
    actual_ids = set(int(x) for x in df.draw_no.tolist()) if not df.empty else set()
    expected_ids = set()
    day_rows=[]
    for d,a,b in EXPECTED_DAYS:
        ids=set(range(a,b+1)); expected_ids |= ids
        got=len(actual_ids & ids)
        day_rows.append({"Tarih":d,"Beklenen":len(ids),"Mevcut":got,"Eksik":len(ids-(actual_ids & ids)),"İlk":a,"Son":b})
    missing=sorted(expected_ids-actual_ids)
    extra=sorted(actual_ids-expected_ids)
    dup=int(df.draw_no.duplicated().sum()) if not df.empty else 0
    bad20=0
    if not df.empty:
        for nums in df.nums:
            if len(nums)!=20 or len(set(nums))!=20 or any(n<1 or n>80 for n in nums):
                bad20 += 1
    return {
        "expected_total": expected_total, "actual_total": len(df), "missing": missing,
        "extra": extra, "duplicates": dup, "bad20": bad20,
        "days": pd.DataFrame(day_rows),
        "ok": len(df)==expected_total and not missing and dup==0 and bad20==0
    }

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


@st.cache_data(show_spinner=False, max_entries=8)
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

@st.cache_data(show_spinner=False, max_entries=8)
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


# --------------------------- NEGATIVE-60 / TRACE / MASTER EXPORT ---------------------------
DIAG_COLS = [
    "recurrence","temp_layer","temp_migration","temp_slope_dir","K_phase","band_id",
    "neighbor_H1","corridor_H1_count","prev_block_member","prev_block_len",
    "block_corridor_age","path3","path6","hits6","hits12"
]


def negative60_diagnostic(labeled: pd.DataFrame) -> pd.DataFrame:
    """Dışarıda kalan 60 sayıyı, gerçek 20 içindeki en yakın kimlikle karşılaştırır.
    Bu bir nedensellik iddiası değildir; negatif kontrol fark haritasıdır.
    """
    x=add_identity_keys(labeled)
    hits=x[x.actual==1].copy()
    outs=x[x.actual==0].copy()
    rows=[]
    if hits.empty:
        return pd.DataFrame()
    for _,o in outs.iterrows():
        best=None
        for _,h in hits.iterrows():
            matches=[]; diffs=[]
            for c in DIAG_COLS:
                ov=o[c]; hv=h[c]
                # float pressure values are reduced to direction bins for interpretability
                if c=="block_corridor_age":
                    ov = "NEW" if float(ov)<=1 else "MID" if float(ov)<=3 else "OLD"
                    hv = "NEW" if float(hv)<=1 else "MID" if float(hv)<=3 else "OLD"
                if str(ov)==str(hv):
                    matches.append(c)
                else:
                    diffs.append(f"{c}:{ov}->{hv}")
            score=len(matches)/len(DIAG_COLS)
            cand=(score, int(h.number), matches, diffs)
            if best is None or cand[0]>best[0]:
                best=cand
        score, nearest, matches, diffs=best
        rows.append({
            "number":int(o.number),
            "nearest_real20":nearest,
            "identity_match_pct":round(score*100,1),
            "matched_fields":", ".join(matches),
            "different_fields":" | ".join(diffs),
            "recurrence":o.recurrence,
            "gap":o.gap,
            "temp_layer":o.temp_layer,
            "temp_migration":o.temp_migration,
            "K_phase":o.K_phase,
            "band":o.band,
            "neighbor_H1":o.neighbor_H1,
            "prev_block_member":o.prev_block_member,
            "social_top3":o.social_top3,
            "identity_core":o.identity_core,
        })
    return pd.DataFrame(rows).sort_values(["identity_match_pct","number"],ascending=[False,True]).reset_index(drop=True)


def real20_rival_summary(labeled: pd.DataFrame) -> pd.DataFrame:
    x=add_identity_keys(labeled)
    rows=[]
    for n in sorted(x.loc[x.actual==1,"number"].tolist()):
        r=x[x.number==n].iloc[0]
        core=x[x.identity_core==r.identity_core]
        det=x[x.identity_detail==r.identity_detail]
        rows.append({
            "number":int(n),
            "same_core_total":len(core),
            "same_core_outside":int((core.actual==0).sum()),
            "same_detail_total":len(det),
            "same_detail_outside":int((det.actual==0).sum()),
            "core_selectivity_pct":round(100/len(core),1) if len(core) else 0.0,
            "detail_selectivity_pct":round(100/len(det),1) if len(det) else 0.0,
        })
    return pd.DataFrame(rows)


def day_indices(df: pd.DataFrame, target_i: int):
    """Hedef çekilişin ait olduğu tam günün indekslerini döndürür."""
    d=str(df.iloc[target_i].date).strip()
    if d:
        idx=df.index[df["date"].astype(str)==d].tolist()
    else:
        # Tarih yoksa Hızlı On tam gün sınırını 00:02 başlangıcından bul.
        start=target_i
        while start>0 and str(df.iloc[start].time)!="00:02":
            start-=1
        end=target_i
        while end+1<len(df) and str(df.iloc[end].time)!="23:57":
            end+=1
        idx=list(range(start,end+1))
    return [int(x) for x in idx]

@st.cache_data(show_spinner=False)
def build_day_life_matrix_cached(serialized_text: str, target_draw_no: int) -> pd.DataFrame:
    """Bir gün için 217×80 tam yaşam matrisi. Her satır PRE-H kimliğidir; actual sonradan etiketlenir."""
    x=parse_text(serialized_text)
    hit=x.index[x.draw_no.astype(int)==int(target_draw_no)].tolist()
    if not hit:
        return pd.DataFrame()
    target_i=int(hit[0])
    rows=[]
    for j in day_indices(x,target_i):
        # İlk çekiliş için önceki veri varsa PRE-H üretilebilir; build_pre_snapshot zaten geçmişi kullanır.
        if j < 1:
            continue
        snap=build_pre_snapshot(x,j).copy()
        actual_set=set(x.iloc[j].nums)
        snap["actual_at_step"]=snap["number"].map(lambda n:int(int(n) in actual_set))
        snap["step_draw_no"]=int(x.iloc[j].draw_no)
        snap["step_date"]=x.iloc[j].date
        snap["step_time"]=x.iloc[j].time
        rows.append(snap)
    if not rows:
        return pd.DataFrame()
    return add_identity_keys(pd.concat(rows,ignore_index=True))

def full_day_life_matrix(df: pd.DataFrame, target_i: int) -> pd.DataFrame:
    """Hedef günün 1–80 bütün sayıları için tam günlük 217×80 yaşam matrisi."""
    return build_day_life_matrix_cached(serialize_master_txt(df), int(df.iloc[target_i].draw_no))

def number_trace(df: pd.DataFrame, target_i: int, n: int, lookback: int=None) -> pd.DataFrame:
    """Seçilen sayının hedef günün tamamındaki yaşam biyografisi (00:02→23:57)."""
    m=full_day_life_matrix(df,target_i)
    if m.empty:
        return pd.DataFrame()
    return m[m.number.astype(int)==int(n)].reset_index(drop=True)


def serialize_master_txt(df: pd.DataFrame) -> str:
    lines=[]
    for _,r in df.sort_values("draw_no").iterrows():
        nums=",".join(str(int(x)) for x in r.nums)
        d=str(r.date).strip()
        if d:
            lines.append(f"{int(r.draw_no)};{d} {r.time};{nums}")
        else:
            lines.append(f"{int(r.draw_no)};{r.time};{nums}")
    return "\n".join(lines)+"\n"


def github_config():
    try:
        token=str(st.secrets.get("GITHUB_TOKEN","")).strip()
        repo=str(st.secrets.get("GITHUB_REPO","gozlekakif-alt/hizli-on-analiz-motoru")).strip()
        branch=str(st.secrets.get("GITHUB_BRANCH","main")).strip()
        path=str(st.secrets.get("GITHUB_DATA_PATH","veri.txt")).strip()
    except Exception:
        token=""; repo="gozlekakif-alt/hizli-on-analiz-motoru"; branch="main"; path="veri.txt"
    return token,repo,branch,path


def github_write_text(text: str, message: str="Hızlı On veri güncelleme"):
    token,repo,branch,path=github_config()
    if not token:
        raise RuntimeError("GITHUB_TOKEN tanımlı değil")
    api=f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}"
    headers={
        "Authorization":f"Bearer {token}",
        "Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"hizli-on-master-v3",
    }
    sha=None
    try:
        req=urllib.request.Request(api+f"?ref={urllib.parse.quote(branch)}",headers=headers)
        with urllib.request.urlopen(req,timeout=20) as rr:
            sha=json.loads(rr.read().decode("utf-8")).get("sha")
    except Exception:
        pass
    body={"message":message,"content":base64.b64encode(text.encode("utf-8")).decode("ascii"),"branch":branch}
    if sha: body["sha"]=sha
    req=urllib.request.Request(api,data=json.dumps(body).encode("utf-8"),headers={**headers,"Content-Type":"application/json"},method="PUT")
    with urllib.request.urlopen(req,timeout=30) as rr:
        return json.loads(rr.read().decode("utf-8"))


def make_research_zip(df, i, snap, labeled, real20, neg60, rival, ts, report):
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_MASTER_VERI.txt",serialize_master_txt(df))
        z.writestr(f"01_PREH_{int(df.iloc[i].draw_no)}_80.csv",to_csv_bytes(snap))
        z.writestr(f"02_POSTH_{int(df.iloc[i].draw_no)}_80.csv",to_csv_bytes(labeled))
        z.writestr(f"03_GERCEK20_{int(df.iloc[i].draw_no)}.csv",to_csv_bytes(real20))
        z.writestr(f"04_NEGATIF60_{int(df.iloc[i].draw_no)}.csv",to_csv_bytes(neg60))
        z.writestr(f"05_GERCEK20_RAKIP_OZET_{int(df.iloc[i].draw_no)}.csv",to_csv_bytes(rival))
        z.writestr(f"06_KARAKTER_SALINIM_{int(df.iloc[i].draw_no)}.csv",to_csv_bytes(ts))
        daym=full_day_life_matrix(df,i)
        if not daym.empty:
            z.writestr(f"07_TAM_GUN_217x80_YASAM_MATRISI_{int(df.iloc[i].draw_no)}.csv",to_csv_bytes(daym))
            for n in range(1,81):
                tr=daym[daym.number.astype(int)==n].reset_index(drop=True)
                z.writestr(f"yasam_izleri_1_80/{n:02d}_TAM_GUN_yasam_izi.csv",to_csv_bytes(tr))
        z.writestr(f"08_MIMARI_RAPOR_{int(df.iloc[i].draw_no)}.txt",report)
    return bio.getvalue()


# --------------------------- TAM GÜN PROFİL / 20×60 / PUAN / NETLEŞME ---------------------------

PROFILE_NUMERIC_COLS = [
    "day_hits_before","carry_count","h2_count","h3_count","kisa_count","orta_count","uzun_count","derin_count",
    "ys_count","oy_count","od_count","s_count","temp_up_count","temp_down_count",
    "neighbor_active_count","block_ctx_count","avg_band_pressure_delta","avg_social_strength",
    "current_gap","hits6","hits12","hits24","corridor_H1_count","prev_block_len","block_corridor_age"
]
PROFILE_CATEGORICAL_COLS = ["current_recurrence","current_temp_layer","current_temp_migration","current_temp_slope_dir","K_phase","band"]

@st.cache_data(show_spinner=False, max_entries=8)
def target_day_profile(df: pd.DataFrame, target_i: int) -> pd.DataFrame:
    """Hedef anına kadar (hedef sonucu hariç) 1–80'in tam-gün birikimli yaşam profilini üretir.
    Geçmiş günler özellik hesaplamak için kullanılabilir; profil sayımları yalnız hedef günün önceki çekilişlerinden gelir.
    """
    target_draw=int(df.iloc[target_i].draw_no)
    idxs=[j for j in day_indices(df,target_i) if j <= target_i]
    if not idxs:
        return pd.DataFrame()
    current=add_identity_keys(build_pre_snapshot(df,target_i))
    prior_idxs=[j for j in idxs if j < target_i]
    hist_rows=[]
    for j in prior_idxs:
        sp=build_pre_snapshot(df,j).copy()
        aset=set(df.iloc[j].nums)
        sp["actual_past"]=sp.number.map(lambda n:int(int(n) in aset))
        hist_rows.append(sp)
    hist=pd.concat(hist_rows,ignore_index=True) if hist_rows else pd.DataFrame()
    rows=[]
    for n in NUMBERS:
        cur=current[current.number==n].iloc[0]
        h=hist[hist.number==n] if not hist.empty else pd.DataFrame()
        def cnt(col,val):
            return int((h[col]==val).sum()) if (not h.empty and col in h) else 0
        rows.append({
            "target_draw_no":target_draw,"target_date":str(df.iloc[target_i].date),"target_time":str(df.iloc[target_i].time),
            "number":n,"steps_before":len(h),"day_hits_before":int(h.actual_past.sum()) if not h.empty else 0,
            "carry_count":cnt("recurrence","CARRY"),"h2_count":cnt("recurrence","H2"),"h3_count":cnt("recurrence","H3"),
            "kisa_count":cnt("recurrence","KISA"),"orta_count":cnt("recurrence","ORTA"),"uzun_count":cnt("recurrence","UZUN"),"derin_count":cnt("recurrence","DERIN"),
            "ys_count":cnt("temp_layer","YS"),"oy_count":cnt("temp_layer","OY"),"od_count":cnt("temp_layer","OD"),"s_count":cnt("temp_layer","S"),
            "temp_up_count":cnt("temp_slope_dir","UP"),"temp_down_count":cnt("temp_slope_dir","DOWN"),
            "neighbor_active_count":int((h.neighbor_H1!="00").sum()) if not h.empty else 0,
            "block_ctx_count":int((h.prev_block_member==1).sum()) if not h.empty else 0,
            "avg_band_pressure_delta":float(h.band_pressure_delta.mean()) if not h.empty else 0.0,
            "avg_social_strength":float(h.social_strength.mean()) if not h.empty else 0.0,
            "current_gap":float(cur.gap) if pd.notna(cur.gap) else -1.0,
            "hits6":float(cur.hits6),"hits12":float(cur.hits12),"hits24":float(cur.hits24),
            "corridor_H1_count":float(cur.corridor_H1_count),"prev_block_len":float(cur.prev_block_len),"block_corridor_age":float(cur.block_corridor_age),
            "current_recurrence":cur.recurrence,"current_temp_layer":cur.temp_layer,"current_temp_migration":cur.temp_migration,
            "current_temp_slope_dir":cur.temp_slope_dir,"K_phase":cur.K_phase,"band":cur.band,
            "path24":cur.path24,"identity_core":cur.identity_core,"identity_detail":cur.identity_detail,
        })
    return pd.DataFrame(rows)

def full_day_similarity_tables(profile: pd.DataFrame, actual_nums) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    """Gerçek 20 ile dışarıdaki 60 arasında tam-gün profil benzerliği. 20×60=1200 çift üretir."""
    if profile.empty:
        return pd.DataFrame(),pd.DataFrame(),pd.DataFrame()
    x=profile.copy()
    actual=set(int(n) for n in actual_nums)
    x["actual"]=x.number.map(lambda n:int(int(n) in actual))
    num=x[PROFILE_NUMERIC_COLS].astype(float).copy()
    mu=num.mean(); sd=num.std(ddof=0).replace(0,1.0)
    z=(num-mu)/sd
    z.index=x.number.astype(int)
    bynum=x.set_index(x.number.astype(int))
    hits=sorted(actual); outs=sorted(set(NUMBERS)-actual)
    pairs=[]
    for h in hits:
        for o in outs:
            dz=float(np.sqrt(np.mean((z.loc[h].values-z.loc[o].values)**2)))
            num_sim=100.0/(1.0+dz)
            cat_matches=sum(str(bynum.loc[h,c])==str(bynum.loc[o,c]) for c in PROFILE_CATEGORICAL_COLS)
            cat_sim=100.0*cat_matches/len(PROFILE_CATEGORICAL_COLS)
            path_sim=100.0*sum(a==b for a,b in zip(str(bynum.loc[h,'path24']),str(bynum.loc[o,'path24'])))/24.0
            sim=0.62*num_sim+0.25*cat_sim+0.13*path_sim
            pairs.append({"real20_number":h,"outside60_number":o,"full_day_similarity_pct":round(sim,2),
                          "numeric_similarity_pct":round(num_sim,2),"categorical_similarity_pct":round(cat_sim,2),
                          "path24_similarity_pct":round(path_sim,2)})
    pairdf=pd.DataFrame(pairs).sort_values(["real20_number","full_day_similarity_pct"],ascending=[True,False])
    rrows=[]
    for h in hits:
        q=pairdf[pairdf.real20_number==h].sort_values("full_day_similarity_pct",ascending=False)
        rrows.append({"number":h,"nearest_outside":int(q.iloc[0].outside60_number),"nearest_similarity_pct":float(q.iloc[0].full_day_similarity_pct),
                      "outside_90plus":int((q.full_day_similarity_pct>=90).sum()),"outside_80plus":int((q.full_day_similarity_pct>=80).sum()),
                      "same_core_outside":int(((x.actual==0)&(x.identity_core==bynum.loc[h,'identity_core'])).sum()),
                      "same_detail_outside":int(((x.actual==0)&(x.identity_detail==bynum.loc[h,'identity_detail'])).sum())})
    orows=[]
    for o in outs:
        q=pairdf[pairdf.outside60_number==o].sort_values("full_day_similarity_pct",ascending=False)
        orows.append({"number":o,"nearest_real20":int(q.iloc[0].real20_number),"nearest_similarity_pct":float(q.iloc[0].full_day_similarity_pct),
                      "real20_90plus":int((q.full_day_similarity_pct>=90).sum()),"real20_80plus":int((q.full_day_similarity_pct>=80).sum())})
    return pairdf,pd.DataFrame(rrows).sort_values("nearest_similarity_pct",ascending=False),pd.DataFrame(orows).sort_values("nearest_similarity_pct",ascending=False)

@st.cache_data(show_spinner=False, max_entries=8)
def rolling_score_rows(df: pd.DataFrame, end_i: int, collect_date: str|None=None) -> pd.DataFrame:
    """Her hedef için puanı yalnız önceki çekilişlerde görülen kimlik başarılarından online öğrenir."""
    core_stats=defaultdict(lambda:[0,0]); ns_stats=defaultdict(lambda:[0,0])
    rows=[]
    for i in range(1,min(end_i,len(df)-1)+1):
        snap=add_identity_keys(build_pre_snapshot(df,i))
        actual=set(df.iloc[i].nums)
        scored=[]
        for _,r in snap.iterrows():
            cn,ch=core_stats[r.identity_core]
            nk=(int(r.number),str(r.recurrence),str(r.temp_layer)); nn,nh=ns_stats[nk]
            cm=(ch/cn) if cn else BASE_RATE; nm=(nh/nn) if nn else BASE_RATE
            a=(cm*min(cn,20)+BASE_RATE*10)/(min(cn,20)+10)
            b=(nm*min(nn,12)+BASE_RATE*8)/(min(nn,12)+8)
            sc=(a+b)/2
            scored.append((int(r.number),float(sc),r.identity_core,r.identity_detail))
        sdf=pd.DataFrame(scored,columns=["number","score","identity_core","identity_detail"]).sort_values(["score","number"],ascending=[False,True]).reset_index(drop=True)
        sdf["rank"]=np.arange(1,len(sdf)+1); sdf["actual"]=sdf.number.map(lambda n:int(n in actual))
        if collect_date is None or str(df.iloc[i].date)==str(collect_date):
            sdf.insert(0,"draw_no",int(df.iloc[i].draw_no)); sdf.insert(1,"date",str(df.iloc[i].date)); sdf.insert(2,"time",str(df.iloc[i].time))
            rows.append(sdf)
        for _,r in snap.iterrows():
            y=int(int(r.number) in actual)
            cs=core_stats[r.identity_core]; cs[0]+=1; cs[1]+=y
            nk=(int(r.number),str(r.recurrence),str(r.temp_layer)); ns=ns_stats[nk]; ns[0]+=1; ns[1]+=y
    return pd.concat(rows,ignore_index=True) if rows else pd.DataFrame()

def netlesme_from_scores(score_rows: pd.DataFrame) -> pd.DataFrame:
    if score_rows.empty: return pd.DataFrame()
    out=[]
    for draw_no,g in score_rows.groupby("draw_no",sort=True):
        h=g[g.actual==1]; o=g[g.actual==0]
        rec={"draw_no":int(draw_no),"date":str(g.iloc[0].date),"time":str(g.iloc[0].time),
             "real20_mean_score":float(h.score.mean()),"outside60_mean_score":float(o.score.mean()),
             "score_gap":float(h.score.mean()-o.score.mean()),"real20_mean_rank":float(h['rank'].mean()),
             "top20_hits":int(g.nsmallest(20,'rank').actual.sum()),"top30_hits":int(g.nsmallest(30,'rank').actual.sum()),
             "top40_hits":int(g.nsmallest(40,'rank').actual.sum()),"top50_hits":int(g.nsmallest(50,'rank').actual.sum())}
        out.append(rec)
    return pd.DataFrame(out)

def full_day_profiles_and_similarity_from_matrix(daym: pd.DataFrame):
    """217 hedefin tamamı için tam-gün birikimli 80 profil + 20×60 benzerlik tablolarını üretir.
    Her hedefte profil yalnız o hedeften ÖNCE gün içinde oluşmuş yaşamdan ve hedefin PRE-H satırından beslenir.
    """
    if daym.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    m=daym.sort_values(["step_draw_no","number"]).copy()
    # Birikimli sayaçlar: her sayı için yalnız önceki hedefler günceller.
    rec_keys=["CARRY","H2","H3","KISA","ORTA","UZUN","DERIN"]
    temp_keys=["YS","OY","OD","S"]
    state={n:{
        "steps":0,"day_hits":0,
        **{f"rec_{k}":0 for k in rec_keys},
        **{f"temp_{k}":0 for k in temp_keys},
        "up":0,"down":0,"neighbor":0,"block":0,
        "band_sum":0.0,"social_sum":0.0,
    } for n in NUMBERS}
    prof_chunks=[]; pair_chunks=[]; real_chunks=[]; out_chunks=[]
    for draw_no,g in m.groupby("step_draw_no",sort=True):
        g=g.sort_values("number").copy()
        profiles=[]
        for _,r in g.iterrows():
            n=int(r.number); stt=state[n]
            rec=str(r.recurrence); tl=str(r.temp_layer); slope=str(r.temp_slope_dir)
            profiles.append({
                "target_draw_no":int(draw_no),"target_date":str(r.step_date),"target_time":str(r.step_time),"number":n,
                "steps_before":stt["steps"],"day_hits_before":stt["day_hits"],
                "carry_count":stt["rec_CARRY"],"h2_count":stt["rec_H2"],"h3_count":stt["rec_H3"],
                "kisa_count":stt["rec_KISA"],"orta_count":stt["rec_ORTA"],"uzun_count":stt["rec_UZUN"],"derin_count":stt["rec_DERIN"],
                "ys_count":stt["temp_YS"],"oy_count":stt["temp_OY"],"od_count":stt["temp_OD"],"s_count":stt["temp_S"],
                "temp_up_count":stt["up"],"temp_down_count":stt["down"],
                "neighbor_active_count":stt["neighbor"],"block_ctx_count":stt["block"],
                "avg_band_pressure_delta":stt["band_sum"]/stt["steps"] if stt["steps"] else 0.0,
                "avg_social_strength":stt["social_sum"]/stt["steps"] if stt["steps"] else 0.0,
                "current_gap":float(r.gap) if pd.notna(r.gap) else -1.0,
                "hits6":float(r.hits6),"hits12":float(r.hits12),"hits24":float(r.hits24),
                "corridor_H1_count":float(r.corridor_H1_count),"prev_block_len":float(r.prev_block_len),"block_corridor_age":float(r.block_corridor_age),
                "current_recurrence":rec,"current_temp_layer":tl,"current_temp_migration":str(r.temp_migration),
                "current_temp_slope_dir":slope,"K_phase":str(r.K_phase),"band":str(r.band),
                "path24":str(r.path24),"identity_core":str(r.identity_core),"identity_detail":str(r.identity_detail),
                "actual":int(r.actual_at_step),
            })
        prof=pd.DataFrame(profiles)
        prof_chunks.append(prof)
        actual=set(prof.loc[prof.actual==1,"number"].astype(int))
        pairdf,realdf,outdf=full_day_similarity_tables(prof,actual)
        if not pairdf.empty:
            pairdf.insert(0,"draw_no",int(draw_no)); pairdf.insert(1,"date",str(g.iloc[0].step_date)); pairdf.insert(2,"time",str(g.iloc[0].step_time))
            pair_chunks.append(pairdf)
        if not realdf.empty:
            realdf.insert(0,"draw_no",int(draw_no)); realdf.insert(1,"date",str(g.iloc[0].step_date)); realdf.insert(2,"time",str(g.iloc[0].step_time))
            real_chunks.append(realdf)
        if not outdf.empty:
            outdf.insert(0,"draw_no",int(draw_no)); outdf.insert(1,"date",str(g.iloc[0].step_date)); outdf.insert(2,"time",str(g.iloc[0].step_time))
            out_chunks.append(outdf)
        # hedef sonucu açıldıktan sonra birikimli gün hafızasını güncelle
        for _,r in g.iterrows():
            n=int(r.number); stt=state[n]
            stt["steps"]+=1; stt["day_hits"]+=int(r.actual_at_step)
            rec=str(r.recurrence); tl=str(r.temp_layer); slope=str(r.temp_slope_dir)
            if rec in rec_keys: stt[f"rec_{rec}"]+=1
            if tl in temp_keys: stt[f"temp_{tl}"]+=1
            if slope=="UP": stt["up"]+=1
            if slope=="DOWN": stt["down"]+=1
            stt["neighbor"]+=int(str(r.neighbor_H1)!="00")
            stt["block"]+=int(r.prev_block_member==1)
            stt["band_sum"]+=float(r.band_pressure_delta)
            stt["social_sum"]+=float(r.social_strength)
    return (
        pd.concat(prof_chunks,ignore_index=True) if prof_chunks else pd.DataFrame(),
        pd.concat(pair_chunks,ignore_index=True) if pair_chunks else pd.DataFrame(),
        pd.concat(real_chunks,ignore_index=True) if real_chunks else pd.DataFrame(),
        pd.concat(out_chunks,ignore_index=True) if out_chunks else pd.DataFrame(),
    )


@st.cache_data(show_spinner=False, max_entries=3)
def make_full_day_research_zip(df: pd.DataFrame, target_i: int) -> bytes:
    """Seçilen günün eksiksiz MASTER araştırma paketi.
    İçerik: 217×80 PRE-H yaşam, 217 hedef puan/netleşme, her hedef 20×60 tam-gün benzerlik,
    çıkan20/dışarı60 rakip özetleri, 80 tam-gün biyografi, karakter salınımı ve kalite manifesti.
    """
    d=str(df.iloc[target_i].date)
    idxs=day_indices(df,target_i)
    end_i=max(idxs)
    daym=full_day_life_matrix(df,end_i)
    scores=rolling_score_rows(df,end_i,collect_date=d)
    net=netlesme_from_scores(scores)
    anat=anatomy_timeseries(df,min(idxs))
    if not anat.empty:
        anat=anat[anat.date.astype(str)==d].copy()
    profiles,pairs,real_rivals,out_rivals=full_day_profiles_and_similarity_from_matrix(daym)

    # Kalite kontrolü: paketi üretmeden önce temel mimariyi doğrula.
    expected_draws=sum(1 for _j in idxs if _j >= 1)
    qc={
        "date":d,
        "expected_draws":expected_draws,
        "life_matrix_rows":len(daym),
        "expected_life_matrix_rows":expected_draws*80,
        "score_rows":len(scores),
        "expected_score_rows":expected_draws*80,
        "profile_rows":len(profiles),
        "expected_profile_rows":expected_draws*80,
        "pair_rows":len(pairs),
        "expected_pair_rows":expected_draws*20*60,
        "real_rival_rows":len(real_rivals),
        "expected_real_rival_rows":expected_draws*20,
        "outside_rival_rows":len(out_rivals),
        "expected_outside_rival_rows":expected_draws*60,
        "netlesme_rows":len(net),
        "actual_sum_life_matrix":int(daym.actual_at_step.sum()) if not daym.empty else 0,
        "expected_actual_sum":expected_draws*20,
    }
    qc["PASS"] = all([
        qc["life_matrix_rows"]==qc["expected_life_matrix_rows"],
        qc["score_rows"]==qc["expected_score_rows"],
        qc["profile_rows"]==qc["expected_profile_rows"],
        qc["pair_rows"]==qc["expected_pair_rows"],
        qc["real_rival_rows"]==qc["expected_real_rival_rows"],
        qc["outside_rival_rows"]==qc["expected_outside_rival_rows"],
        qc["netlesme_rows"]==expected_draws,
        qc["actual_sum_life_matrix"]==qc["expected_actual_sum"],
    ])
    if not qc["PASS"]:
        raise RuntimeError("Tam gün araştırma paketi kalite kontrolünden geçemedi: "+str(qc))

    bio=io.BytesIO()
    with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('00_MASTER_VERI.txt',serialize_master_txt(df))
        z.writestr(f'01_{d}_217x80_TAM_GUN_YASAM.csv',to_csv_bytes(daym))
        z.writestr(f'02_{d}_80_PUAN_TUM_HEDEFLER.csv',to_csv_bytes(scores))
        z.writestr(f'03_{d}_NETLESME_217_HEDEF.csv',to_csv_bytes(net))
        z.writestr(f'04_{d}_20_KARAKTER_SALINIM.csv',to_csv_bytes(anat))
        z.writestr(f'05_{d}_TAM_GUN_80_PROFIL_TUM_HEDEFLER.csv',to_csv_bytes(profiles))
        z.writestr(f'06_{d}_20x60_TAM_GUN_KIMLIK_BENZERLIK.csv',to_csv_bytes(pairs))
        z.writestr(f'07_{d}_CIKAN20_EN_YAKIN_DISARIDA60.csv',to_csv_bytes(real_rivals))
        z.writestr(f'08_{d}_DISARIDA60_EN_YAKIN_CIKAN20.csv',to_csv_bytes(out_rivals))
        if not scores.empty:
            z.writestr(f'09_{d}_CIKAN20_PUANLARI.csv',to_csv_bytes(scores[scores.actual==1].copy()))
            z.writestr(f'10_{d}_DISARIDA60_PUANLARI.csv',to_csv_bytes(scores[scores.actual==0].copy()))
        for n in NUMBERS:
            tr=daym[daym.number.astype(int)==n].reset_index(drop=True)
            z.writestr(f'1_80_TAM_GUN_BIYOGRAFI/{n:02d}_yasam_izi.csv',to_csv_bytes(tr))
        qc_txt='\n'.join(f'{k}={v}' for k,v in qc.items())+'\n'
        z.writestr('99_KALITE_KONTROL.txt',qc_txt)
        manifest=(
            'HIZLI ON MASTER V4.1 TAM GUN ARASTIRMA PAKETI\n'
            'Ana mimari: 1-80 tam gun PRE-H yasam -> her hedefte cikan20/disarida60 -> '
            '20x60 tam-gun kimlik benzerligi -> puan/netlesme -> karakter salinimi.\n'
            f'Gun={d}; PRE-H_hedef={expected_draws}; yasam_satiri={len(daym)}; 20x60_satiri={len(pairs)}; QC_PASS={qc["PASS"]}\n'
        )
        z.writestr('98_MIMARI_MANIFEST.txt',manifest)
    return bio.getvalue()


@st.cache_data(show_spinner=False, max_entries=2)
def make_14_day_research_zip(df: pd.DataFrame) -> bytes:
    """25.08.2026–07.09.2026 arasındaki 14 tam gün araştırma paketlerini tek ZIP içinde toplar."""
    bio = io.BytesIO()
    available_dates = []
    for d, _a, _b in EXPECTED_DAYS:
        idxs = df.index[df["date"].astype(str) == d].tolist()
        if len(idxs) == 217:
            available_dates.append((d, max(idxs)))

    if len(available_dates) != len(EXPECTED_DAYS):
        found = {d for d, _ in available_dates}
        missing_days = [d for d, _, _ in EXPECTED_DAYS if d not in found]
        raise RuntimeError("14 günlük paket için eksik/tam olmayan gün var: " + ", ".join(missing_days))

    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_MASTER_VERI_14_GUN.txt", serialize_master_txt(df))
        manifest = [
            "HIZLI ON — 14 GÜNLÜK MASTER ARAŞTIRMA PAKETİ",
            "Aralık: 25.08.2026–07.09.2026",
            "Gün: 14",
            "Çekiliş: 3038",
            "",
        ]
        for pos, (d, end_i) in enumerate(available_dates, start=1):
            day_zip = make_full_day_research_zip(df, int(end_i))
            safe_d = d.replace(".", "_")
            z.writestr(f"GUNLER/{pos:02d}_{safe_d}_MASTER_TAM_GUN.zip", day_zip)
            manifest.append(f"{pos:02d}. {d} — 217 çekiliş — günlük MASTER ZIP")
        z.writestr("00_MANIFEST.txt", "\n".join(manifest) + "\n")
    return bio.getvalue()



def assemble_14_day_research_zip_from_parts(df: pd.DataFrame, parts: dict) -> bytes:
    """Önceden hesaplanmış 14 günlük günlük ZIP'leri tekrar hesaplamadan tek ana ZIP'te birleştirir."""
    expected_dates=[d for d,_,_ in EXPECTED_DAYS]
    missing=[d for d in expected_dates if d not in parts]
    if missing:
        raise RuntimeError("Henüz hesaplanmamış günler: " + ", ".join(missing))
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_MASTER_VERI_14_GUN.txt",serialize_master_txt(df))
        manifest=[
            "HIZLI ON — 14 GÜNLÜK MASTER ARAŞTIRMA PAKETİ",
            "Aralık: 25.08.2026–07.09.2026",
            "Gün: 14",
            "Çekiliş: 3038",
            "Üretim modu: CPU SAFE / gün gün hesaplandı, finalde yeniden hesaplama yok.",
            "",
        ]
        for pos,d in enumerate(expected_dates,1):
            safe=d.replace(".","_")
            z.writestr(f"GUNLER/{pos:02d}_{safe}_MASTER_TAM_GUN.zip",parts[d])
            manifest.append(f"{pos:02d}. {d} — günlük MASTER ZIP — hazır")
        z.writestr("00_MANIFEST.txt","\n".join(manifest)+"\n")
    return bio.getvalue()


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
st.title("🧬 Hızlı On — Yaşam Kimliği MASTER APP V6.2 — ARDIŞIK PROFESÖRÜ + DURUM MAKİNESİ")
st.caption("Gerçek 20'nin en küçük kimlik ayrıntısını çıkarır; aynı anda aynı/benzer kimlikte bulunan diğer sayıları negatif kontrol olarak gösterir. PRE-H → POST-H ayrımı zorunludur.")

with st.sidebar:
    st.header("Veri / Hızlı Güncelleme")
    st.caption("Ana kaynak: GitHub deposundaki veri.txt. Yeni sonucu tekli veya toplu yapıştırabilirsin.")
    ups=st.file_uploader("Ek TXT yükle",type=["txt"],accept_multiple_files=True)
    quick_text=st.text_area("Yeni çekiliş(ler)i yapıştır",height=180,placeholder="Çekiliş no: 52298\n30.08.2026 - 00:02\n...20 sayı...\n\nveya\n52298;30.08.2026 00:02;1,2,...")
    if "session_added_text" not in st.session_state:
        st.session_state["session_added_text"]=""
    if st.button("➕ Yeni çekilişi veriye ekle",use_container_width=True):
        nd=parse_text(quick_text)
        if nd.empty:
            st.error("Yeni çekiliş okunamadı. Çekiliş no + tarih/saat + 20 sayı kontrol et.")
        else:
            oldx=parse_text(st.session_state["session_added_text"]) if st.session_state["session_added_text"].strip() else pd.DataFrame()
            mx=merge_frames(oldx,nd)
            st.session_state["session_added_text"]=serialize_master_txt(mx)
            st.success(f"{len(nd)} çekiliş oturuma eklendi.")

frames=[]
auto_source=False
if DATA_FILE.exists():
    try:
        auto_text=DATA_FILE.read_text(encoding="utf-8",errors="ignore")
        auto_df=parse_text(auto_text)
        if not auto_df.empty:
            frames.append(auto_df)
            auto_source=True
    except Exception as e:
        st.sidebar.error(f"veri.txt okunamadı: {e}")

for f in ups or []:
    frames.append(parse_text(f.getvalue().decode("utf-8",errors="ignore")))
if st.session_state.get("session_added_text","").strip():
    frames.append(parse_text(st.session_state["session_added_text"]))
df=merge_frames(*frames)

with st.sidebar:
    st.download_button("⬇️ Güncel veri.txt indir",serialize_master_txt(df).encode("utf-8"),"veri.txt","text/plain",use_container_width=True)
    token,_,_,_=github_config()
    if token:
        if st.button("☁️ veri.txt'yi GitHub'a kalıcı kaydet",use_container_width=True):
            try:
                github_write_text(serialize_master_txt(df),f"Hızlı On veri güncelleme — {int(df.iloc[-1].draw_no)}")
                st.success("GitHub veri.txt güncellendi.")
            except Exception as e:
                st.error(f"GitHub kayıt hatası: {e}")
    else:
        st.caption("Kalıcı tek tuş GitHub kaydı için Streamlit Secrets'a GITHUB_TOKEN eklenebilir. Şimdilik güncel veri.txt'yi indirip GitHub'a yükleyebilirsin.")

if df.empty:
    st.error("GitHub kök dizininde veri.txt bulunamadı veya geçerli çekiliş okunamadı.")
    st.info("veri.txt dosyasını app.py ile aynı klasöre koy. Yedek olarak sol menüden TXT de yükleyebilirsin.")
    st.stop()

health=data_health(df)
if auto_source:
    st.sidebar.success(f"veri.txt otomatik yüklendi: {len(df)} çekiliş")
else:
    st.sidebar.warning("veri.txt otomatik bulunamadı; yüklenen/yapıştırılan veri kullanılıyor.")

issues=validate(df)
if issues:
    st.error("\n".join(issues[:30]))
    st.stop()

st.subheader("📦 Ana veri sağlık kontrolü")
c1,c2,c3,c4,c5=st.columns(5)
c1.metric("Çekiliş",f"{len(df)}/{health['expected_total']}")
c2.metric("Gün",df.date[df.date.astype(str).str.len()>0].nunique())
c3.metric("Eksik",len(health["missing"]))
c4.metric("Mükerrer",health["duplicates"])
c5.metric("Bozuk 20'li",health["bad20"])
if health["ok"]:
    st.success("✅ 25 Ağustos–7 Eylül ana veri tabanı eksiksiz: 14 gün × 217 = 3.038 çekiliş / 60.760 sayı sonucu.")
else:
    st.warning("⚠️ Ana veri tabanında eksik/fazla/bozuk kayıt var. Aşağıdaki günlük kontrolü incele.")
with st.expander("14 gün ayrı ayrı veri kontrolü", expanded=not health["ok"]):
    st.dataframe(health["days"],use_container_width=True,hide_index=True)
    if health["missing"]:
        st.write("Eksik çekilişler:", health["missing"][:100])
    if health["extra"]:
        st.write("Beklenen 14 gün aralığı dışındaki ek çekilişler:", health["extra"][:100])

c1,c2,c3,c4=st.columns(4)
c1.metric("İlk",int(df.iloc[0].draw_no))
c2.metric("Son",int(df.iloc[-1].draw_no))
c3.metric("İlk saat",str(df.iloc[0].time))
c4.metric("Son saat",str(df.iloc[-1].time))

# Hedef seçim
options=[f"#{int(r.draw_no)} | {r.date} {r.time}" for _,r in df.iloc[1:].iterrows()]
sel=st.selectbox("İncelenecek gerçek çekiliş",options,index=len(options)-1)
sel_draw=int(re.search(r"#(\d+)",sel).group(1))
i=int(df.index[df.draw_no==sel_draw][0])

snap=build_pre_snapshot(df,i)
labeled=attach_post_label(snap,df.iloc[i].nums)
labeled=add_identity_keys(labeled)
summary,real20=real20_anatomy(labeled)
neg60=pd.DataFrame()
rival20=pd.DataFrame()

# Invariant checks
st.success(f"PRE-H fotoğraf: {len(snap)} sayı | POST-H gerçek etiket: {int(labeled.actual.sum())}/20")

T1,T2,T3,T4,T5,T6,T7,T8=st.tabs([
    "🎯 Gerçek 20 Anatomisi",
    "🧬 Aynı Kimlik / Negatif 60",
    "🪜 20 Sayının Yaşam İzleri",
    "🌊 Karakter Salınımı",
    "🔢 Sayı Özel Hafıza",
    "🧪 Kör Havuz Testi",
    "📈 Hedef Netleşmesi / Puan",
    "💾 Tüm Araştırmayı İndir",
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

    st.subheader("Hedef öncesi 1–80 puanı ve çıkan 20'nin puanları")
    st.caption("CPU SAFE: puan hesabı yalnız düğmeye bastığında çalışır.")
    if st.button("🎯 BU HEDEFİN 1–80 PUANINI HESAPLA",key="calc_target_score",use_container_width=True):
        with st.spinner("Hedef puanı geçmişten hesaplanıyor..."):
            _score_all=rolling_score_rows(df,i,collect_date=str(df.iloc[i].date))
            _target_score=_score_all[_score_all.draw_no.astype(int)==sel_draw].copy() if not _score_all.empty else pd.DataFrame()
            st.session_state["target_score_df"]=_target_score
            st.session_state["target_score_draw"]=sel_draw
    _target_score=st.session_state.get("target_score_df",pd.DataFrame())
    if (not _target_score.empty) and st.session_state.get("target_score_draw")==sel_draw:
        _target_score=_target_score.copy()
        _target_score["group"]=_target_score.actual.map({1:"ÇIKAN20",0:"DIŞARIDA60"})
        st.dataframe(_target_score[["number","score","rank","group","identity_core"]].sort_values("rank"),use_container_width=True,height=500)

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

    st.subheader("Gerçek 20 rakipleri + Negatif 60")
    st.caption("ULTRA CPU SAFE: bu iki tablo yalnız düğmeye basınca hesaplanır.")
    if st.button("🧬 RAKİP 20 + NEGATİF 60 HESAPLA",key="calc_rival_neg",use_container_width=True):
        with st.spinner("Rakip 20 ve negatif 60 hazırlanıyor..."):
            _r20=real20_rival_summary(labeled)
            _n60=negative60_diagnostic(labeled)
            st.session_state["cpu_rival20"]=_r20
            st.session_state["cpu_neg60"]=_n60
            st.session_state["cpu_rival_neg_draw"]=sel_draw
    if st.session_state.get("cpu_rival_neg_draw")==sel_draw:
        rival20=st.session_state.get("cpu_rival20",pd.DataFrame())
        neg60=st.session_state.get("cpu_neg60",pd.DataFrame())
        if not rival20.empty:
            st.subheader("Gerçek 20'nin aynı kimlikteki rakipleri")
            st.dataframe(rival20,use_container_width=True,height=420)
        if not neg60.empty:
            st.subheader("Dışarıda kalan 60 — negatif kontrol fark haritası")
            st.dataframe(neg60,use_container_width=True,height=620)

    st.subheader("Tam-gün yaşam kimliği: Çıkan 20 × dışarıdaki 60")
    st.caption("CPU SAFE: 20×60 karşılaştırması yalnız isteyince hesaplanır.")
    if st.button("🧬 BU HEDEFİN 20×60 TAM-GÜN BENZERLİĞİNİ HESAPLA",key="calc_target_20x60",use_container_width=True):
        with st.spinner("Tam-gün profil ve 20×60 benzerlik hesaplanıyor..."):
            _profile=target_day_profile(df,i)
            _pairs,_real20_day,_outside60_day=full_day_similarity_tables(_profile,df.iloc[i].nums)
            st.session_state["target_profile"]=_profile
            st.session_state["target_pairs"]=_pairs
            st.session_state["target_real20_day"]=_real20_day
            st.session_state["target_outside60_day"]=_outside60_day
            st.session_state["target_20x60_draw"]=sel_draw
    if st.session_state.get("target_20x60_draw")==sel_draw:
        _profile=st.session_state.get("target_profile",pd.DataFrame())
        _pairs=st.session_state.get("target_pairs",pd.DataFrame())
        _real20_day=st.session_state.get("target_real20_day",pd.DataFrame())
        _outside60_day=st.session_state.get("target_outside60_day",pd.DataFrame())
        if not _profile.empty:
            st.dataframe(_real20_day,use_container_width=True,height=420)
            st.markdown("**Dışarıdaki 60'ın gerçek 20'ye en yakın tam-gün kimlikleri**")
            st.dataframe(_outside60_day,use_container_width=True,height=420)
            with st.expander("20×60 = 1.200 tam-gün benzerlik çiftini göster"):
                st.dataframe(_pairs,use_container_width=True,height=620)

with T3:
    st.subheader("1–80 TAM GÜN yaşam biyografisi")
    st.caption("CPU SAFE: tam gün matrisi yalnız düğmeye bastığında üretilir ve aynı gün için oturumda tekrar kullanılır.")
    trace_n=st.selectbox("1–80 arasından yaşamını izle",list(range(1,81)),index=0,key="trace_n")
    _day_key=str(df.iloc[i].date)
    if st.button("🪜 SEÇİLİ GÜNÜN 217×80 YAŞAM MATRİSİNİ HESAPLA",key="calc_day_matrix",use_container_width=True):
        with st.spinner("217×80 tam gün yaşam matrisi hazırlanıyor..."):
            _daym=full_day_life_matrix(df,i)
            st.session_state["cpu_daym"]=_daym
            st.session_state["cpu_daym_date"]=_day_key
    daym=st.session_state.get("cpu_daym",pd.DataFrame())
    if (not daym.empty) and st.session_state.get("cpu_daym_date")==_day_key:
        tr=daym[daym.number.astype(int)==int(trace_n)].reset_index(drop=True)
        trace_cols=["step_draw_no","step_date","step_time","actual_at_step","gap","recurrence","temp_layer","temp_migration","temp_slope_dir","K_phase","band","path1","path2","path3","path4","path6","path12","path24","hits6","hits12","hits24","neighbor_H1","corridor_H1_count","band_pressure_delta","prev_block_member","prev_block_len","social_top3","identity_core","identity_detail"]
        showcols=[c for c in trace_cols if c in tr.columns]
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Günlük adım",len(tr))
        c2.metric("Gün içinde çıktı",int(tr.actual_at_step.sum()) if not tr.empty else 0)
        c3.metric("İlk",str(tr.iloc[0].step_time) if not tr.empty else "-")
        c4.metric("Son",str(tr.iloc[-1].step_time) if not tr.empty else "-")
        st.dataframe(tr[showcols],use_container_width=True,height=700)
        st.download_button(f"{int(trace_n)} TAM GÜN yaşam izi CSV indir",to_csv_bytes(tr),f"{int(trace_n)}_TAM_GUN_yasam_izi_{sel_draw}.csv","text/csv")
        st.subheader("80 sayının tam gün yaşam matrisi")
        st.caption(f"{len(daym):,} sayı-durum satırı.")
        st.download_button("217×80 TAM GÜN yaşam matrisi CSV indir",to_csv_bytes(daym),f"217x80_TAM_GUN_YASAM_{sel_draw}.csv","text/csv")
    else:
        st.info("Tam gün matrisi henüz hesaplanmadı.")
    st.subheader("20 sayının son yaşam karakteri — tek tabloda")
    st.dataframe(real20[["number","recurrence","gap","temp_layer","temp_migration","temp_slope_dir","K_phase","band","path6","hits12","neighbor_H1","corridor_H1_count","band_pressure_delta","prev_block_member","social_top3","identity_detail"]].sort_values("number"),use_container_width=True,height=620)

with T4:
    st.subheader("Çekilişten çekilişe gerçek 20 karakter bütçesi")
    st.caption("CPU SAFE: karakter salınımı yalnız düğmeye basınca hesaplanır.")
    if st.button("🌊 SON 40 HEDEF KARAKTER SALINIMINI HESAPLA",key="calc_ts",use_container_width=True):
        with st.spinner("Karakter salınımı hazırlanıyor..."):
            _ts=anatomy_timeseries(df,max(1,i-40))
            st.session_state["cpu_ts"]=_ts
            st.session_state["cpu_ts_draw"]=sel_draw
    ts=st.session_state.get("cpu_ts",pd.DataFrame())
    if (not ts.empty) and st.session_state.get("cpu_ts_draw")==sel_draw:
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

with T5:
    n2=st.selectbox("1–80 sayı özel hafızası",NUMBERS,index=int(real20.iloc[0].number)-1,key="n2")
    st.caption("CPU SAFE: sayı hafızası yalnız düğmeye basınca hesaplanır.")
    if st.button("🔢 SEÇİLEN SAYININ HAFIZASINI HESAPLA",key="calc_num_mem",use_container_width=True):
        with st.spinner("Sayı özel hafızası hazırlanıyor..."):
            _mem=number_memory(df,int(n2),min_i=12)
            st.session_state["cpu_mem"]=_mem
            st.session_state["cpu_mem_n"]=int(n2)
    mem=st.session_state.get("cpu_mem",pd.DataFrame())
    if (not mem.empty) and st.session_state.get("cpu_mem_n")==int(n2):
        st.metric("Geçmiş hedef örneği",len(mem))
        st.metric("Doğum",int(mem.actual.sum()))
        st.dataframe(mem[["target_draw_no","target_time","actual","gap","recurrence","temp_layer","temp_migration","path6","hits12","neighbor_H1","band_pressure_delta","identity_core"]].tail(250),use_container_width=True,height=520)
        st.subheader("Tekrarlanan çekirdek kimlikler")
        stats=signature_stats(mem,"identity_core",min_cases=3)
        st.dataframe(stats.head(100),use_container_width=True)
    else:
        st.info("Sayı hafızası henüz hesaplanmadı.")

with T6:
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

with T7:
    st.subheader("Gün içinde hedef netleşiyor mu?")
    st.caption("Her çekilişte puan yalnız geçmişten dondurulur. Sonuç açıldıktan sonra çıkan 20 ile dışarıdaki 60'ın puan/rank ayrışması ölçülür.")
    if st.button("Seçili günün 217 hedef netleşme raporunu hesapla",use_container_width=True):
        _day_scores=rolling_score_rows(df,max(day_indices(df,i)),collect_date=str(df.iloc[i].date))
        _net=netlesme_from_scores(_day_scores)
        st.session_state['day_scores']=_day_scores
        st.session_state['day_net']=_net
    _net=st.session_state.get('day_net',pd.DataFrame())
    _day_scores=st.session_state.get('day_scores',pd.DataFrame())
    if not _net.empty and str(_net.iloc[0].date)==str(df.iloc[i].date):
        st.dataframe(_net,use_container_width=True,height=580)
        st.line_chart(_net.set_index('draw_no')[[c for c in ['score_gap','top20_hits','top30_hits','top40_hits'] if c in _net.columns]])
        st.download_button("Günlük netleşme CSV indir",to_csv_bytes(_net),f"{df.iloc[i].date}_NETLESME_217.csv","text/csv")
        st.download_button("80 sayı puanları — tüm hedefler CSV",to_csv_bytes(_day_scores),f"{df.iloc[i].date}_80_PUAN_TUM_HEDEFLER.csv","text/csv")

with T8:
    st.subheader("Tüm araştırmayı dışa aktar")
    st.download_button("Bu hedefin 80 PRE-H snapshot CSV'si",to_csv_bytes(snap),f"preH_{sel_draw}_80.csv","text/csv")
    st.download_button("Bu hedefin 80 POST-H etiketli CSV'si",to_csv_bytes(labeled),f"postH_{sel_draw}_80.csv","text/csv")
    st.download_button("Gerçek 20 kimlik CSV'si",to_csv_bytes(real20),f"real20_identity_{sel_draw}.csv","text/csv")
    st.download_button("Negatif 60 fark haritası CSV",to_csv_bytes(neg60),f"negatif60_{sel_draw}.csv","text/csv")
    st.download_button("Gerçek 20 rakip özeti CSV",to_csv_bytes(rival20),f"real20_rakip_{sel_draw}.csv","text/csv")
    report=architecture_report_text(df,i,labeled)
    st.download_button("Gerçek 20 mimari TXT raporu",report.encode("utf-8"),f"real20_mimari_{sel_draw}.txt","text/plain")
    st.caption("CPU SAFE: hedef ZIP'i de yalnız düğmeye basınca hazırlanır.")
    if st.button("🎯 BU HEDEFİN ARAŞTIRMA ZIP'İNİ HAZIRLA",key="prepare_target_zip_tab",use_container_width=True):
        with st.spinner("Hedef araştırma ZIP'i hazırlanıyor..."):
            _ts_for_zip=anatomy_timeseries(df,max(1,i-40))
            _neg_for_zip=negative60_diagnostic(labeled)
            _rival_for_zip=real20_rival_summary(labeled)
            _bundle=make_research_zip(df,i,snap,labeled,real20,_neg_for_zip,_rival_for_zip,_ts_for_zip,report)
            st.session_state["target_bundle"]=_bundle
            st.session_state["target_bundle_draw"]=sel_draw
    if st.session_state.get("target_bundle") and st.session_state.get("target_bundle_draw")==sel_draw:
        st.download_button("📦 TÜM ARAŞTIRMAYI TEK ZIP İNDİR",st.session_state["target_bundle"],f"HIZLI_ON_TUM_ARASTIRMA_{sel_draw}.zip","application/zip",use_container_width=True)

    st.markdown("### Tam gün araştırma paketi")
    st.caption("Bana göndermek için en uygun paket: 217×80 yaşam matrisi + her hedefin 80 puanı + çıkan20/dışarıda60 puanları + netleşme + 80 ayrı tam-gün biyografi.")
    if st.button("📦 TAM GÜN ARAŞTIRMA PAKETİNİ HAZIRLA",use_container_width=True):
        with st.spinner("Tam gün 1–80 yaşam, puan ve netleşme paketi hazırlanıyor..."):
            st.session_state['full_day_zip']=make_full_day_research_zip(df,i)
            st.session_state['full_day_zip_date']=str(df.iloc[i].date)
    if st.session_state.get('full_day_zip') and st.session_state.get('full_day_zip_date')==str(df.iloc[i].date):
        st.download_button("⬇️ TAM GÜN ARAŞTIRMA ZIP İNDİR",st.session_state['full_day_zip'],f"HIZLI_ON_{df.iloc[i].date.replace('.','_')}_TAM_GUN_ARASTIRMA.zip","application/zip",use_container_width=True)
    st.text_area("Rapor önizleme",report,height=520)


# --------------------------- HER ZAMAN GÖRÜNEN İNDİRME MERKEZİ ---------------------------
st.divider()
st.header("📦 MASTER ARAŞTIRMA İNDİRME MERKEZİ")
st.caption("Bu bölüm sekmelerden bağımsızdır; sayfanın en altında her zaman görünür. Bana göndermek için TAM GÜN MASTER ZIP'i kullan.")

_v_report=architecture_report_text(df,i,labeled)
if st.button("🎯 BU HEDEFİN TAM ARAŞTIRMA ZIP'İNİ HAZIRLA",use_container_width=True,key="visible_prepare_target_zip"):
    with st.spinner("Hedef ZIP hazırlanıyor..."):
        _v_ts=anatomy_timeseries(df,max(1,i-40))
        _v_neg=negative60_diagnostic(labeled)
        _v_rival=real20_rival_summary(labeled)
        _v_target_zip=make_research_zip(df,i,snap,labeled,real20,_v_neg,_v_rival,_v_ts,_v_report)
        st.session_state["visible_target_zip_bytes"]=_v_target_zip
        st.session_state["visible_target_zip_draw"]=sel_draw
if st.session_state.get("visible_target_zip_bytes") and st.session_state.get("visible_target_zip_draw")==sel_draw:
    st.download_button(
        "⬇️ BU HEDEFİN TAM ARAŞTIRMA ZIP'İNİ İNDİR",
        st.session_state["visible_target_zip_bytes"],
        f"HIZLI_ON_HEDEF_{sel_draw}_TAM_ARASTIRMA.zip",
        "application/zip",
        use_container_width=True,
        key="visible_target_zip"
    )

st.info("📌 Bu işlem 217×80 yaşam ve 260.400 adet 20×60 karşılaştırmayı gerçekten üretir. Telefonda üstte ‘Stop’ görünüyorsa hesaplama DEVAM EDİYORDUR; sayfadan çıkma.")
if st.button("🧬 TAM GÜN MASTER PAKETİNİ HAZIRLA (217×80 + 20×60)",use_container_width=True,key="visible_prepare_full_day",type="primary"):
    st.session_state.pop('visible_full_day_zip',None)
    st.session_state.pop('visible_full_day_zip_date',None)
    _status=st.status("MASTER paket hazırlanıyor…", expanded=True)
    try:
        st.write("1/4 — 217×80 PRE-H tam gün yaşam matrisi hazırlanıyor…")
        st.write("2/4 — Her hedefin 80 puanı ve 20/60 etiketi hazırlanıyor…")
        st.write("3/4 — 217 hedef için 20×60 kimlik karşılaştırmaları hazırlanıyor…")
        st.write("4/4 — Kalite kontrolü ve ZIP paketleme yapılıyor…")
        _full_zip=make_full_day_research_zip(df,i)
        st.session_state['visible_full_day_zip']=_full_zip
        st.session_state['visible_full_day_zip_date']=str(df.iloc[i].date)
        _status.update(label="✅ MASTER paket hazır — aşağıdaki İNDİR düğmesine bas",state="complete",expanded=False)
        st.success("Paket hazırlandı. Şimdi hemen aşağıdaki yeşil ‘TAM GÜN MASTER ZIP’İ İNDİR’ düğmesine bas.")
    except Exception as _e:
        st.session_state.pop('visible_full_day_zip',None)
        _status.update(label="❌ Paket hazırlanamadı",state="error",expanded=True)
        st.exception(_e)

if st.session_state.get('visible_full_day_zip') and st.session_state.get('visible_full_day_zip_date')==str(df.iloc[i].date):
    st.download_button(
        "⬇️ TAM GÜN MASTER ZIP’İ İNDİR — HAZIR",
        st.session_state['visible_full_day_zip'],
        f"HIZLI_ON_{str(df.iloc[i].date).replace('.','_')}_MASTER_TAM_GUN.zip",
        "application/zip",
        use_container_width=True,
        key="visible_download_full_day"
    )
    st.success("Bu ZIP bana göndermen gereken ana araştırma paketidir.")


st.divider()
st.subheader("⚡ 14 GÜNLÜK HAFİF RAPOR — ANINDA")
st.caption("CPU kısıtlıyken kullan: 14 günün veri sağlığı + günlük frekans + ardışık blok özeti + tekrar özetini ağır 20×60 hesabı olmadan tek ZIP yapar.")

def make_14_day_light_zip(df: pd.DataFrame) -> bytes:
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_MASTER_VERI_14_GUN.txt",serialize_master_txt(df))
        rows=[]
        for d,_,_ in EXPECTED_DAYS:
            g=df[df["date"].astype(str)==d].copy()
            if g.empty:
                continue
            freq=Counter(n for nums in g.nums for n in nums)
            repeat_vals=[]
            block_counts=[]
            prev=None
            for nums in g.nums:
                s=set(nums)
                if prev is not None:
                    repeat_vals.append(len(s & prev))
                block_counts.append(len(consecutive_blocks(sorted(s))))
                prev=s
            rows.append({
                "date":d,
                "draws":len(g),
                "avg_repeat":float(np.mean(repeat_vals)) if repeat_vals else 0.0,
                "avg_block_count":float(np.mean(block_counts)) if block_counts else 0.0,
                "max_block_count":max(block_counts) if block_counts else 0,
                "top10_freq":",".join(f"{n}:{c}" for n,c in freq.most_common(10)),
            })
        light=pd.DataFrame(rows)
        z.writestr("01_14_GUN_HAFIF_OZET.csv",to_csv_bytes(light))
        z.writestr("02_VERI_SAGLIK.csv",to_csv_bytes(data_health(df)["days"]))
    return bio.getvalue()

if st.button("⚡ 14 GÜNLÜK HAFİF ZIP HAZIRLA",use_container_width=True,key="prepare_14_light"):
    st.session_state["zip14_light"]=make_14_day_light_zip(df)
if st.session_state.get("zip14_light"):
    st.download_button(
        "⬇️ 14 GÜNLÜK HAFİF RAPOR ZIP İNDİR",
        st.session_state["zip14_light"],
        "HIZLI_ON_25_08_07_09_14_GUN_HAFIF_RAPOR.zip",
        "application/zip",
        use_container_width=True,
        key="download_14_light"
    )

st.divider()
st.subheader("🗓️ 14 GÜNLÜK TÜM ANALİZLER — KALICI CPU SAFE")
st.caption("Her tıklamada yalnız 1 tam gün hesaplanır. Tamamlanan günlük MASTER ZIP disk önbelleğine yazılır; Streamlit rerun/session reset olsa bile uygulama yeniden açıldığında kaldığı yerden devam eder.")

# Kalıcı önbellek: uygulamanın çalıştığı makinede saklanır.
# GitHub/Streamlit tam redeploy veya container değişiminde yerel disk silinebilir;
# bu yüzden her tamamlanan gün ayrıca indirilebilir.
_CACHE14 = Path(".hizli_on_master14_cache")
_CACHE14.mkdir(parents=True, exist_ok=True)
_expected14=[d for d,_,_ in EXPECTED_DAYS]

def _day_cache_path14(d):
    return _CACHE14 / f"{d.replace('.','_')}_MASTER_TAM_GUN.zip"

def _load_parts14():
    parts={}
    for d in _expected14:
        fp=_day_cache_path14(d)
        if fp.exists() and fp.stat().st_size>0:
            try:
                b=fp.read_bytes()
                with zipfile.ZipFile(io.BytesIO(b),"r") as zz:
                    if zz.testzip() is None:
                        parts[d]=b
            except Exception:
                pass
    return parts

_done14=_load_parts14()
_progress14=len(_done14)
st.progress(_progress14/14 if _progress14 else 0.0,text=f"14 günlük paket ilerleme: {_progress14}/14 gün")
st.caption("V4.6 kayıt: günlük MASTER ZIP doğrudan final dosyaya yazılır; .tmp kullanılmaz.")

if _done14:
    st.write("Kalıcı hazır günler:", " • ".join(d for d in _expected14 if d in _done14))

c14a,c14b=st.columns(2)
with c14a:
    if st.button("▶️ SONRAKİ GÜNÜ HESAPLA",use_container_width=True,key="master14_next_day_persistent",type="primary",disabled=(_progress14>=14)):
        _next_date=next(d for d in _expected14 if d not in _done14)
        _idxs=df.index[df["date"].astype(str)==_next_date].tolist()
        if len(_idxs)!=217:
            st.error(f"{_next_date}: 217 çekiliş bulunamadı.")
        else:
            _status14=st.status(f"{_next_date} hesaplanıyor…",expanded=True)
            try:
                _dayzip=make_full_day_research_zip(df,int(max(_idxs)))
                _final_path=_day_cache_path14(_next_date)
                _final_path.parent.mkdir(parents=True, exist_ok=True)

                # V4.6: in-memory ZIP zaten tamamen üretildiği için geçici dosya kullanma.
                # Streamlit'in eşzamanlı rerun'larında .tmp dosyasının silinmesi riskini kaldır.
                if not _dayzip or len(_dayzip) < 100:
                    raise IOError("MASTER ZIP bellekte boş/eksik üretildi.")

                _final_path.write_bytes(_dayzip)

                if (not _final_path.exists()) or _final_path.stat().st_size != len(_dayzip):
                    raise IOError(f"MASTER ZIP kalıcı yazılamadı: {_final_path}")

                # Yazılan dosyanın gerçek ZIP olduğunu hemen doğrula.
                with zipfile.ZipFile(_final_path, "r") as _zz:
                    _bad = _zz.testzip()
                    if _bad is not None:
                        raise IOError(f"MASTER ZIP bozuk kayıt: {_bad}")
                _status14.update(label=f"✅ {_next_date} kalıcı kaydedildi",state="complete",expanded=False)
                st.rerun()
            except Exception as _e:
                _status14.update(label=f"❌ {_next_date} hazırlanamadı",state="error",expanded=True)
                st.exception(_e)
with c14b:
    if st.button("♻️ 14 GÜNLÜK İLERLEMEYİ SIFIRLA",use_container_width=True,key="master14_reset_persistent"):
        for _fp in _CACHE14.glob("*_MASTER_TAM_GUN.zip"):
            try: _fp.unlink()
            except Exception: pass
        st.session_state.pop("master14_final_zip_persistent",None)
        st.rerun()

_done14=_load_parts14()
if _done14:
    _last=next(reversed([d for d in _expected14 if d in _done14]))
    st.download_button(
        f"⬇️ SON HAZIR GÜNÜ İNDİR — {_last}",
        _done14[_last],
        f"HIZLI_ON_{_last.replace('.','_')}_MASTER_TAM_GUN.zip",
        "application/zip",
        use_container_width=True,
        key="download_last_master14_day"
    )

if len(_done14)==14:
    _sig14=hashlib.sha256(b"".join(_done14[d] for d in _expected14)).hexdigest()
    if st.session_state.get("master14_final_sig") != _sig14:
        st.session_state["master14_final_zip_persistent"]=assemble_14_day_research_zip_from_parts(df,_done14)
        st.session_state["master14_final_sig"]=_sig14
    st.success("✅ 14/14 gün hazır. Final ZIP günlük kalıcı paketlerden, yeniden ağır hesaplama yapmadan birleştirildi.")
    st.download_button(
        "⬇️ 25.08–07.09 14 GÜNLÜK MASTER ZIP’İ İNDİR",
        st.session_state["master14_final_zip_persistent"],
        "HIZLI_ON_25_08_2026_07_09_2026_14_GUN_MASTER.zip",
        "application/zip",
        use_container_width=True,
        key="download_14_day_master_persistent"
    )

st.divider()
st.caption("MASTER V4.6 KALICI KAYIT DIRECT araştırma kuralı: Veri hızlı güncellenir → PRE-H 80 fotoğrafı → gerçek 20'nin tüm yaşam karakterleri → aynı kimlikteki rakipler → dışarıdaki 60'ın fark haritası → sayı özel yaşam izi → karakter salınımı → kör doğrulama. Kupon üretimi bu araştırma sürümünde bilinçli olarak yoktur.")



# =====================================================================
# V5.1 FULL RESEARCH ARCHITECTURE
# Araştırma-only. Kupon üretimi bilinçli olarak YOK.
# Her hedef H için özellikler yalnız PRE-H'den çıkarılır; H sonucu POST etikettir.
# =====================================================================

V51_EXPERTS = [
    ("01_GAME_CHARACTER", "Oyun karakteri hakemi"),
    ("02_TEMPERATURE_SURFACE", "Dinamik sıcaklık yüzeyi / sıcak 5-10-20-30"),
    ("03_PRESSURE_800", "Salınımlı 800 baskısı / H1 toplamı / cross geçişleri"),
    ("04_BAND_NEIGHBOR", "Bant-komşuluk / kayan bant / n±1±2±3"),
    ("05_CONSECUTIVE_BLOCKS", "Ardışık blok doğum-büyüme-kayma-bölünme-birleşme"),
    ("06_RHYTHMIC_SEQUENCES", "2–6 üyeli ritmik sabit-adım dizileri"),
    ("07_LAST_DIGIT_FAMILIES", "Aynı son hane aileleri"),
    ("08_TENS_GEOMETRY", "Aynı onlar / çapraz bant / geometrik aileler"),
    ("09_CARRY_RETURN_H1_H8", "H1 taşıma, H2–H8 dönüş ve fazlar"),
    ("10_AGE_SLEEP_CYCLE", "Yaş-uyku-dinlenip dönüş yaşam döngüsü"),
    ("11_SOCIAL_NETWORK_2_6", "2–6 birlikte yaşam / lider / taşıyıcı / yeniden birleşme"),
    ("12_LEADER_FOLLOWER", "Öncü-takipçi 1–5 el gecikmeli ilişkiler"),
    ("13_HOUR_PHASE", "Saat/faz koşullu davranış"),
    ("14_CHARACTER_BREAKS", "Gün içi karakter kırılmaları"),
    ("15_PARITY_DISTRIBUTION", "Tek/çift, düşük/yüksek, dağılım rejimi"),
    ("16_POOL_DYNAMICS", "Sıcak havuz daralma-genişleme / turnover"),
    ("17_CLUSTER_MIGRATION", "Küme göçü / bant ve merkez hareketi"),
    ("18_NUMBER_MEMORY", "1–80 sayı özel hafıza"),
    ("19_NEGATIVE60", "Negatif 60 kontrolü"),
    ("20_BLIND_VALIDATION", "Kronolojik kör test / kural yaşam süresi / veto"),
]

def _v51_x(df):
    x = df.sort_values("draw_no").reset_index(drop=True).copy()
    x["numset"] = x["nums"].map(lambda z:set(map(int,z)))
    x["sum20"] = x["nums"].map(lambda z:int(sum(map(int,z))))
    x["hour"] = x["time"].astype(str).str.slice(0,2).astype(int)
    return x

def _v51_zone800(v):
    v=float(v)
    if v < 760: return "<760"
    if v < 790: return "760-789"
    if v < 810: return "790-809"
    if v < 830: return "810-829"
    if v < 860: return "830-859"
    return "860+"

def _v51_osc800(h1,h2):
    if h2 is None: return "NA"
    if h2 < 800 <= h1: return "CROSS_UP"
    if h2 >= 800 > h1: return "CROSS_DOWN"
    if h1 >= 800 and h1 > h2: return "ABOVE_RISING"
    if h1 >= 800: return "ABOVE_FALLING_OR_FLAT"
    if h1 > h2: return "BELOW_RISING"
    return "BELOW_FALLING_OR_FLAT"

def _v51_phase(t):
    h=int(str(t)[:2])
    if h <= 1: return "GECE_00_01"
    if h < 10: return "SABAH_07_09"
    if h < 13: return "OGLEDEN_ONCE_10_12"
    if h < 17: return "OGLEDEN_SONRA_13_16"
    if h < 21: return "AKSAM_17_20"
    return "GECE_21_23"

def _v51_blocks(S):
    a=sorted(S); out=[]
    if not a: return out
    run=[a[0]]
    for n in a[1:]:
        if n==run[-1]+1:
            run.append(n)
        else:
            if len(run)>=2: out.append(tuple(run))
            run=[n]
    if len(run)>=2: out.append(tuple(run))
    return out

def _v51_isolated(S):
    S=set(S)
    return sorted(n for n in S if (n-1 not in S and n+1 not in S))

def _v51_roll_freq(x, i, w):
    lo=max(0,i-w)
    c=Counter()
    for S in x.iloc[lo:i].numset:
        c.update(S)
    den=max(1,i-lo)
    return {n:c[n]/den for n in range(1,81)}

def _v51_gap_before(x,i,n):
    for j in range(i-1,-1,-1):
        if n in x.iloc[j].numset:
            return i-j-1
    return i

def _v51_character_rows(x):
    rows=[]
    for i in range(1,len(x)):
        h1=x.iloc[i-1].numset
        h2=x.iloc[i-2].numset if i>=2 else set()
        h3=x.iloc[i-3].numset if i>=3 else set()
        b1=_v51_blocks(h1)
        s1=int(x.iloc[i-1].sum20)
        s2=int(x.iloc[i-2].sum20) if i>=2 else None
        rf20=_v51_roll_freq(x,i,20)
        vals=sorted(rf20.values(), reverse=True)
        hot_spread=(vals[0]-vals[19]) if len(vals)>=20 else 0.0
        band_counts=[sum(10*k+1 <= n <= 10*k+10 for n in h1) for k in range(8)]
        carry_pre=len(h1 & h2) if i>=2 else 0
        low=sum(n<=40 for n in h1); even=sum(n%2==0 for n in h1)
        # Hakem: yalnız PRE-H.
        tags=[]
        if len(b1)>=4: tags.append("ARDISIK_YOGUN")
        if carry_pre>=7: tags.append("TASIMA_YOGUN")
        if max(band_counts)>=5: tags.append("BANT_SIKISIK")
        if s1>=830: tags.append("800_UST_BASKI")
        if s1<790: tags.append("800_ALT_BASKI")
        if hot_spread<=0.10: tags.append("SICAKLIK_DAR")
        if hot_spread>=0.25: tags.append("SICAKLIK_GENIS")
        if low>=13 or low<=7: tags.append("ALT_UST_DENGESIZ")
        if even>=14 or even<=6: tags.append("PARITE_UC")
        regime="+".join(tags) if tags else "DENGELI"
        rows.append({
            "idx":i,"draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
            "phase":_v51_phase(x.iloc[i].time),"pre_regime":regime,
            "H1_sum":s1,"H1_zone800":_v51_zone800(s1),"H1_osc800":_v51_osc800(s1,s2),
            "H1_blocks":len(b1),"H1_adj_edges":sum(len(b)-1 for b in b1),
            "H1_carry_from_H2":carry_pre,"H1_low40":low,"H1_even":even,
            "H1_band_max":max(band_counts),"pre_hot20_spread":hot_spread,
        })
    return pd.DataFrame(rows)

def _v51_save_zip(name, tables, manifest_lines=None):
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        if manifest_lines:
            z.writestr("00_MANIFEST.txt","\n".join(manifest_lines)+"\n")
        for fn,tab in tables.items():
            if tab is None: tab=pd.DataFrame()
            z.writestr(fn, tab.to_csv(index=False).encode("utf-8-sig"))
    return bio.getvalue()

def _v51_expert_game_character(x):
    c=_v51_character_rows(x)
    sm=(c.groupby(["pre_regime","phase"],dropna=False)
          .agg(events=("draw_no","count"),mean_H1_sum=("H1_sum","mean"),
               mean_blocks=("H1_blocks","mean"),mean_carry=("H1_carry_from_H2","mean"))
          .reset_index())
    return {"01_PREH_CHARACTER_BY_DRAW.csv":c,"02_CHARACTER_PHASE_SUMMARY.csv":sm}

def _v51_expert_temperature(x):
    ctab=_v51_character_rows(x).set_index("idx")
    rows=[]; pool=[]
    prev_top={10:set(),20:set(),30:set()}
    for i in range(5,len(x)):
        reg=ctab.loc[i,"pre_regime"] if i in ctab.index else "NA"
        f5=_v51_roll_freq(x,i,5); f10=_v51_roll_freq(x,i,10); f20=_v51_roll_freq(x,i,20); f40=_v51_roll_freq(x,i,40)
        score={n:0.35*f5[n]+0.30*f10[n]+0.20*f20[n]+0.15*f40[n] for n in range(1,81)}
        order=sorted(score,key=lambda n:(score[n],f10[n],-n),reverse=True)
        rank={n:r+1 for r,n in enumerate(order)}
        cur=x.iloc[i].numset
        for n in range(1,81):
            rows.append({"draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                "pre_regime":reg,"number":n,"temp_score":score[n],"temp_rank":rank[n],
                "in_hot5":int(rank[n]<=5),"in_hot10":int(rank[n]<=10),"in_hot20":int(rank[n]<=20),
                "in_hot30":int(rank[n]<=30),"actual":int(n in cur),
                "f5":f5[n],"f10":f10[n],"f20":f20[n],"f40":f40[n]})
        rec={"draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,"pre_regime":reg}
        for k in (10,20,30):
            top=set(order[:k]); rec[f"hot{k}_overlap_prev"]=len(top&prev_top[k]); rec[f"hot{k}_turnover"]=k-len(top&prev_top[k]); prev_top[k]=top
        rec["hot20_score_max"]=score[order[0]]; rec["hot20_score_min"]=score[order[19]]
        rec["hot20_spread"]=rec["hot20_score_max"]-rec["hot20_score_min"]
        rec["actual_in_hot20"]=len(cur & set(order[:20]))
        pool.append(rec)
    a=pd.DataFrame(rows); b=pd.DataFrame(pool)
    sm=(a.groupby(["pre_regime","in_hot20"]).actual.agg(["count","sum","mean"]).reset_index()
          .rename(columns={"count":"tests","sum":"hits","mean":"hit_rate"}))
    return {"01_NUMBER_TEMPERATURE_PREH.csv":a,"02_HOT_POOL_DYNAMICS.csv":b,"03_HOT20_CHARACTER_PERFORMANCE.csv":sm}

def _v51_expert_800(x):
    c=_v51_character_rows(x).set_index("idx")
    rows=[]
    for i in range(2,len(x)):
        h1=x.iloc[i-1].numset; cur=x.iloc[i].numset
        h1s=int(x.iloc[i-1].sum20); h2s=int(x.iloc[i-2].sum20)
        osc=_v51_osc800(h1s,h2s); zone=_v51_zone800(h1s)
        bands=[]
        for k in range(8):
            lo=10*k+1; hi=lo+9
            h1c=sum(lo<=n<=hi for n in h1); hc=sum(lo<=n<=hi for n in cur)
            bands.append((f"{lo}-{hi}",h1c,hc))
        for band,h1c,hc in bands:
            rows.append({"draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                         "pre_regime":c.loc[i,"pre_regime"],"H1_sum":h1s,"H2_sum":h2s,"H1_zone":zone,
                         "oscillation":osc,"band":band,"H1_band_count":h1c,"target_band_count":hc,
                         "delta_band_count":hc-h1c,"target_sum":int(x.iloc[i].sum20)})
    a=pd.DataFrame(rows)
    z=(a.groupby(["band","H1_zone"],dropna=False)
       .agg(events=("draw_no","count"),next_band_mean=("target_band_count","mean"),
            delta_band_mean=("delta_band_count","mean")).reset_index())
    o=(a.groupby(["band","oscillation"],dropna=False)
       .agg(events=("draw_no","count"),next_band_mean=("target_band_count","mean"),
            delta_band_mean=("delta_band_count","mean")).reset_index())
    return {"01_800_BAND_EVENTS.csv":a,"02_800_ZONE_X_10LUK.csv":z,"03_800_OSCILLATION_X_BAND.csv":o}

def _v51_expert_band_neighbor(x):
    c=_v51_character_rows(x).set_index("idx"); rows=[]; neigh=[]
    for i in range(1,len(x)):
        h1=x.iloc[i-1].numset; cur=x.iloc[i].numset; reg=c.loc[i,"pre_regime"]
        for width in (5,10,20):
            for lo in range(1,82-width):
                hi=lo+width-1
                p=sum(lo<=n<=hi for n in h1); q=sum(lo<=n<=hi for n in cur)
                if p>=max(2,width//5):
                    rows.append({"draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                                 "pre_regime":reg,"width":width,"lo":lo,"hi":hi,"H1_count":p,"H_count":q,"delta":q-p})
        for n in range(1,81):
            if n not in h1: continue
            for r in (1,2,3):
                cand={m for m in range(max(1,n-r),min(80,n+r)+1) if m!=n}
                neigh.append({"draw_no":int(x.iloc[i].draw_no),"pre_regime":reg,"number":n,"radius":r,
                              "neighbor_candidates":len(cand),"neighbor_hits":len(cand&cur),
                              "self_carry":int(n in cur)})
    a=pd.DataFrame(rows); b=pd.DataFrame(neigh)
    sm=(b.groupby(["pre_regime","radius"]).agg(events=("number","count"),mean_neighbor_hits=("neighbor_hits","mean"),
                                                self_carry_rate=("self_carry","mean")).reset_index())
    return {"01_MOVING_BANDS.csv":a,"02_NEIGHBOR_CORRIDORS.csv":b,"03_NEIGHBOR_CHARACTER_SUMMARY.csv":sm}

def _v51_expert_blocks(x):
    c=_v51_character_rows(x).set_index("idx"); rows=[]
    for i in range(1,len(x)):
        prev=x.iloc[i-1].numset; cur=x.iloc[i].numset; reg=c.loc[i,"pre_regime"]
        pb=_v51_blocks(prev); cb=_v51_blocks(cur)
        for b in pb:
            bs=set(b)
            # maximal block lifecycle
            exact=int(bs<=cur)
            grown_left=int(min(b)>1 and (min(b)-1 in cur) and exact)
            grown_right=int(max(b)<80 and (max(b)+1 in cur) and exact)
            rows.append({"draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                "pre_regime":reg,"block":"-".join(map(str,b)),"length":len(b),"event":"LIFECYCLE",
                "score":len(bs&cur)/len(bs),"full":exact,"grow_left":grown_left,"grow_right":grown_right})
            for d,label in [(-2,"SOLA_2"),(-1,"SOLA_1"),(0,"SABIT"),(1,"SAGA_1"),(2,"SAGA_2")]:
                sh={n+d for n in bs if 1<=n+d<=80}
                if len(sh)==len(bs):
                    hit=len(sh&cur)
                    rows.append({"draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                        "pre_regime":reg,"block":"-".join(map(str,b)),"length":len(b),"event":label,
                        "score":hit/len(bs),"full":int(hit==len(bs)),"grow_left":0,"grow_right":0})
        # isolated single movement
        for n in _v51_isolated(prev):
            for d,label in [(-2,"TEK_SOLA_2"),(-1,"TEK_SOLA_1"),(0,"TEK_SABIT"),(1,"TEK_SAGA_1"),(2,"TEK_SAGA_2")]:
                m=n+d
                if 1<=m<=80:
                    rows.append({"draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                        "pre_regime":reg,"block":str(n),"length":1,"event":label,"score":int(m in cur),
                        "full":int(m in cur),"grow_left":0,"grow_right":0})
    a=pd.DataFrame(rows)
    sm=(a.groupby(["pre_regime","length","event"]).full.agg(["count","sum","mean"]).reset_index()
        .rename(columns={"count":"tests","sum":"hits","mean":"hit_rate"}))
    return {"01_BLOCK_LIFECYCLE_MOVES.csv":a,"02_BLOCK_CHARACTER_PERFORMANCE.csv":sm}

def _v51_sequences_catalog():
    seqs=[]
    for step in range(2,21):
        for L in range(2,7):
            for start in range(1,81-step*(L-1)):
                seqs.append((step,L,tuple(start+step*k for k in range(L))))
    return seqs

def _v51_expert_rhythm(x):
    c=_v51_character_rows(x).set_index("idx"); seqs=_v51_sequences_catalog(); rows=[]
    for i in range(1,len(x)):
        p=x.iloc[i-1].numset; cur=x.iloc[i].numset; reg=c.loc[i,"pre_regime"]
        for step,L,seq in seqs:
            ph=sum(n in p for n in seq)
            if ph < max(2,L-1): continue
            hh=sum(n in cur for n in seq)
            rows.append({"draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                         "pre_regime":reg,"step":step,"length":L,"sequence":"-".join(map(str,seq)),
                         "pre_hits":ph,"post_hits":hh,"full":int(hh==L)})
    a=pd.DataFrame(rows)
    sm=(a.groupby(["pre_regime","step","length"]).full.agg(["count","sum","mean"]).reset_index()
        .rename(columns={"count":"tests","sum":"hits","mean":"hit_rate"}))
    return {"01_RHYTHMIC_CANDIDATES.csv":a,"02_RHYTHMIC_CHARACTER_PERFORMANCE.csv":sm}

def _v51_expert_lastdigit(x):
    c=_v51_character_rows(x).set_index("idx"); rows=[]
    fams={d:set(n for n in range(1,81) if n%10==d) for d in range(10)}
    for i in range(1,len(x)):
        p=x.iloc[i-1].numset; cur=x.iloc[i].numset; reg=c.loc[i,"pre_regime"]
        for d,F in fams.items():
            pm=sorted(p&F); hm=sorted(cur&F)
            rows.append({"draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                         "pre_regime":reg,"last_digit":d,"H1_count":len(pm),"H_count":len(hm),
                         "H1_members":"-".join(map(str,pm)),"H_members":"-".join(map(str,hm)),
                         "carry_count":len(set(pm)&set(hm))})
    a=pd.DataFrame(rows)
    sm=a.groupby(["pre_regime","last_digit","H1_count"]).agg(events=("draw_no","count"),
        next_mean=("H_count","mean"),carry_mean=("carry_count","mean")).reset_index()
    return {"01_LAST_DIGIT_EVENTS.csv":a,"02_LAST_DIGIT_CHARACTER_SUMMARY.csv":sm}

def _v51_expert_tens(x):
    c=_v51_character_rows(x).set_index("idx"); rows=[]
    for i in range(1,len(x)):
        p=x.iloc[i-1].numset; cur=x.iloc[i].numset; reg=c.loc[i,"pre_regime"]
        for band in range(8):
            lo=10*band+1; hi=lo+9; F=set(range(lo,hi+1))
            rows.append({"draw_no":int(x.iloc[i].draw_no),"pre_regime":reg,"band":f"{lo}-{hi}",
                         "H1_count":len(p&F),"H_count":len(cur&F),"delta":len(cur&F)-len(p&F)})
        # mirrored pairs 1-80, 2-79...
        for n in range(1,41):
            pair={n,81-n}
            if len(p&pair):
                rows.append({"draw_no":int(x.iloc[i].draw_no),"pre_regime":reg,"band":f"MIRROR_{n}_{81-n}",
                             "H1_count":len(p&pair),"H_count":len(cur&pair),"delta":len(cur&pair)-len(p&pair)})
    a=pd.DataFrame(rows)
    sm=a.groupby(["pre_regime","band"]).agg(events=("draw_no","count"),next_mean=("H_count","mean"),
                                            delta_mean=("delta","mean")).reset_index()
    return {"01_TENS_MIRROR_EVENTS.csv":a,"02_TENS_GEOMETRY_SUMMARY.csv":sm}

def _v51_expert_carry(x):
    c=_v51_character_rows(x).set_index("idx"); rows=[]
    for i in range(8,len(x)):
        reg=c.loc[i,"pre_regime"]; cur=x.iloc[i].numset
        hist=[x.iloc[i-k].numset for k in range(1,9)]
        for n in range(1,81):
            mask=[int(n in S) for S in hist]
            last_k=next((k+1 for k,v in enumerate(mask) if v),0)
            rows.append({"draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                         "pre_regime":reg,"number":n,**{f"H{k}":mask[k-1] for k in range(1,9)},
                         "nearest_lag":last_k,"actual":int(n in cur)})
    a=pd.DataFrame(rows)
    sm=a.groupby(["pre_regime","nearest_lag"]).actual.agg(["count","sum","mean"]).reset_index()
    sm.columns=["pre_regime","nearest_lag","tests","hits","hit_rate"]
    return {"01_H1_H8_NUMBER_PHASES.csv":a,"02_H1_H8_CHARACTER_PERFORMANCE.csv":sm}

def _v51_expert_age(x):
    c=_v51_character_rows(x).set_index("idx"); rows=[]; last={n:None for n in range(1,81)}
    for i in range(len(x)):
        if i>0:
            reg=c.loc[i,"pre_regime"] if i in c.index else "NA"; cur=x.iloc[i].numset
            for n in range(1,81):
                gap=i if last[n] is None else i-last[n]-1
                gb="0" if gap==0 else ("1-2" if gap<=2 else "3-5" if gap<=5 else "6-11" if gap<=11 else "12-23" if gap<=23 else "24+")
                rows.append({"draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                             "pre_regime":reg,"number":n,"gap":gap,"gap_band":gb,"actual":int(n in cur)})
        for n in x.iloc[i].numset: last[n]=i
    a=pd.DataFrame(rows)
    sm=a.groupby(["pre_regime","gap_band"]).actual.agg(["count","sum","mean"]).reset_index()
    sm.columns=["pre_regime","gap_band","tests","hits","hit_rate"]
    return {"01_AGE_SLEEP_NUMBER.csv":a,"02_AGE_SLEEP_CHARACTER_PERFORMANCE.csv":sm}

def _v51_expert_social(x):
    # 2–6 birlikte yaşam: sürekli/yeniden birleşen grupları, ardışık çekiliş kesişimlerinden çıkarır.
    rows=[]; counts=Counter(); rejoin=Counter()
    prev_intersections={}
    for i in range(1,len(x)):
        inter=x.iloc[i-1].numset & x.iloc[i].numset
        for k in range(2,min(6,len(inter))+1):
            for g in combinations(sorted(inter),k):
                counts[(k,g)]+=1
        if i>=2:
            # H-2 ve H'de var, H-1'de en az bir üye eksik = yeniden birleşme adayı.
            A=x.iloc[i-2].numset; B=x.iloc[i-1].numset; C=x.iloc[i].numset
            reac=(A&C)
            for k in range(2,min(6,len(reac))+1):
                for g in combinations(sorted(reac),k):
                    if not set(g)<=B:
                        rejoin[(k,g)]+=1
    for (k,g),v in counts.items():
        rows.append({"size":k,"group":"-".join(map(str,g)),"consecutive_survival":v,
                     "rejoin_after_break":rejoin.get((k,g),0)})
    a=pd.DataFrame(rows)
    if not a.empty: a=a.sort_values(["size","consecutive_survival","rejoin_after_break"],ascending=[True,False,False])
    return {"01_SOCIAL_GROUPS_2_6.csv":a}

def _v51_expert_leadfollow(x):
    # Binary matrix; PRE-only lag associations, then summarize next occurrence.
    import numpy as np
    A=np.zeros((len(x),80),dtype=np.uint8)
    for i,S in enumerate(x.numset):
        for n in S: A[i,n-1]=1
    rows=[]
    base=A.mean(axis=0)
    for lag in range(1,6):
        P=A[:-lag]; T=A[lag:]
        co=P.T @ T
        denom=P.sum(axis=0)
        for a in range(80):
            if denom[a]<20: continue
            for b in range(80):
                rate=float(co[a,b]/denom[a])
                lift=rate/float(base[b]) if base[b]>0 else 0
                if lift>=1.15 or lift<=0.85:
                    rows.append({"lag":lag,"leader":a+1,"follower":b+1,"events":int(denom[a]),
                                 "next_hits":int(co[a,b]),"next_rate":rate,"base_rate":float(base[b]),"lift":lift})
    a=pd.DataFrame(rows)
    if not a.empty: a=a.sort_values(["lag","lift"],ascending=[True,False])
    return {"01_LEADER_FOLLOWER_1_5.csv":a}

def _v51_expert_hour(x):
    c=_v51_character_rows(x).set_index("idx"); rows=[]
    for i in range(1,len(x)):
        rows.append({"draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                     "phase":_v51_phase(x.iloc[i].time),"pre_regime":c.loc[i,"pre_regime"],
                     "carry":len(x.iloc[i-1].numset & x.iloc[i].numset),
                     "block_count":len(_v51_blocks(x.iloc[i].numset)),"sum20":int(x.iloc[i].sum20)})
    a=pd.DataFrame(rows)
    sm=a.groupby(["phase","pre_regime"]).agg(events=("draw_no","count"),carry_mean=("carry","mean"),
        block_mean=("block_count","mean"),sum_mean=("sum20","mean")).reset_index()
    return {"01_PHASE_EVENTS.csv":a,"02_PHASE_CHARACTER_SUMMARY.csv":sm}

def _v51_expert_breaks(x):
    c=_v51_character_rows(x)
    rows=[]
    for d,g in c.groupby("date",sort=False):
        g=g.sort_values("draw_no").reset_index(drop=True)
        prev=None; run=0
        for _,r in g.iterrows():
            if r.pre_regime!=prev:
                rows.append({"date":d,"draw_no":r.draw_no,"time":r.time,"from_regime":prev or "START",
                             "to_regime":r.pre_regime,"previous_run_length":run})
                prev=r.pre_regime; run=1
            else: run+=1
    return {"01_CHARACTER_BREAKS.csv":pd.DataFrame(rows)}

def _v51_expert_parity(x):
    c=_v51_character_rows(x).set_index("idx"); rows=[]
    for i in range(1,len(x)):
        p=x.iloc[i-1].numset; cur=x.iloc[i].numset
        rows.append({"draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                     "pre_regime":c.loc[i,"pre_regime"],"H1_even":sum(n%2==0 for n in p),
                     "H_even":sum(n%2==0 for n in cur),"H1_low40":sum(n<=40 for n in p),
                     "H_low40":sum(n<=40 for n in cur),"H1_sum":int(x.iloc[i-1].sum20),"H_sum":int(x.iloc[i].sum20)})
    a=pd.DataFrame(rows)
    return {"01_PARITY_LOW_HIGH.csv":a}

def _v51_expert_pool(x):
    # Derived from temperature expert but smaller table.
    temp=_v51_expert_temperature(x)
    return {"01_POOL_DYNAMICS.csv":temp["02_HOT_POOL_DYNAMICS.csv"],
            "02_HOT20_CHARACTER.csv":temp["03_HOT20_CHARACTER_PERFORMANCE.csv"]}

def _v51_expert_migration(x):
    c=_v51_character_rows(x).set_index("idx"); rows=[]
    for i in range(1,len(x)):
        p=x.iloc[i-1].numset; cur=x.iloc[i].numset
        pc=sum(p)/20; cc=sum(cur)/20
        pb=[sum(10*k+1<=n<=10*k+10 for n in p) for k in range(8)]
        cb=[sum(10*k+1<=n<=10*k+10 for n in cur) for k in range(8)]
        rows.append({"draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                     "pre_regime":c.loc[i,"pre_regime"],"H1_center":pc,"H_center":cc,"center_delta":cc-pc,
                     "H1_peak_band":int(np.argmax(pb))+1,"H_peak_band":int(np.argmax(cb))+1,
                     "peak_band_delta":int(np.argmax(cb))-int(np.argmax(pb))})
    a=pd.DataFrame(rows)
    sm=a.groupby("pre_regime").agg(events=("draw_no","count"),center_delta_mean=("center_delta","mean"),
                                   peak_band_delta_mean=("peak_band_delta","mean")).reset_index()
    return {"01_CLUSTER_MIGRATION.csv":a,"02_MIGRATION_CHARACTER_SUMMARY.csv":sm}

def _v51_expert_memory(x):
    c=_v51_character_rows(x).set_index("idx")
    age=_v51_expert_age(x)["01_AGE_SLEEP_NUMBER.csv"]
    carry=_v51_expert_carry(x)["01_H1_H8_NUMBER_PHASES.csv"]
    # aggregate personal profile
    g=age.groupby(["number","pre_regime","gap_band"]).actual.agg(["count","sum","mean"]).reset_index()
    g.columns=["number","pre_regime","gap_band","tests","hits","hit_rate"]
    lag=carry.groupby(["number","nearest_lag"]).actual.agg(["count","sum","mean"]).reset_index()
    lag.columns=["number","nearest_lag","tests","hits","hit_rate"]
    return {"01_NUMBER_MEMORY_GAP_REGIME.csv":g,"02_NUMBER_MEMORY_LAG.csv":lag}

def _v51_expert_negative60(x):
    c=_v51_character_rows(x).set_index("idx"); rows=[]
    for i in range(8,len(x)):
        reg=c.loc[i,"pre_regime"]; cur=x.iloc[i].numset
        f10=_v51_roll_freq(x,i,10); f20=_v51_roll_freq(x,i,20)
        for n in range(1,81):
            gap=_v51_gap_before(x,i,n)
            neigh1=int((n-1 in x.iloc[i-1].numset if n>1 else False) or (n+1 in x.iloc[i-1].numset if n<80 else False))
            rows.append({"draw_no":int(x.iloc[i].draw_no),"pre_regime":reg,"number":n,"actual":int(n in cur),
                         "gap":gap,"f10":f10[n],"f20":f20[n],"H1":int(n in x.iloc[i-1].numset),
                         "H2":int(n in x.iloc[i-2].numset),"neighbor_H1":neigh1})
    a=pd.DataFrame(rows)
    sm=a.groupby(["pre_regime","actual"]).agg(events=("number","count"),gap_mean=("gap","mean"),
        f10_mean=("f10","mean"),f20_mean=("f20","mean"),H1_rate=("H1","mean"),
        H2_rate=("H2","mean"),neighbor_rate=("neighbor_H1","mean")).reset_index()
    return {"01_NEGATIVE60_FEATURES.csv":a,"02_REAL20_VS_NEG60_CHARACTER.csv":sm}

def _v51_expert_validation(x):
    # Build a compact common evidence table from several experts and run chronological blind validation.
    char=_v51_character_rows(x)
    cut_draw=int(x.iloc[int(len(x)*0.70)].draw_no)
    evidence=[]
    # 800 oscillation -> next sum above/below 800
    for _,r in char.iterrows():
        i=int(r.idx); outcome=int(x.iloc[i].sum20>=800)
        evidence.append({"draw_no":r.draw_no,"date":r.date,"rule_family":"800_OSC",
                         "rule":f"{r.pre_regime}|{r.H1_osc800}|{r.H1_zone800}","success":outcome})
    # block regime -> next >=4 blocks
    for _,r in char.iterrows():
        i=int(r.idx); outcome=int(len(_v51_blocks(x.iloc[i].numset))>=4)
        evidence.append({"draw_no":r.draw_no,"date":r.date,"rule_family":"BLOCK_REGIME",
                         "rule":f"{r.pre_regime}|H1blocks={min(int(r.H1_blocks),5)}","success":outcome})
    E=pd.DataFrame(evidence)
    vals=[]
    for (fam,rule),g in E.groupby(["rule_family","rule"]):
        tr=g[g.draw_no<cut_draw]; te=g[g.draw_no>=cut_draw]
        if len(tr)<12 or len(te)<5: continue
        trr=float(tr.success.mean()); ter=float(te.success.mean())
        vals.append({"rule_family":fam,"rule":rule,"train_tests":len(tr),"train_hits":int(tr.success.sum()),
                     "train_rate":trr,"blind_tests":len(te),"blind_hits":int(te.success.sum()),"blind_rate":ter,
                     "stability_ratio":ter/trr if trr>0 else 0})
    v=pd.DataFrame(vals)
    if not v.empty:
        v["status"]=np.where((v.blind_tests>=5)&(v.blind_hits>0)&(v.stability_ratio>=0.75),
                             "DOGRULANDI","KANIT_YETERSIZ")
        # day-level lifespan
        life=E.groupby(["rule_family","rule","date"]).success.mean().reset_index()
        lsum=life.groupby(["rule_family","rule"]).agg(days=("date","nunique"),
            positive_days=("success",lambda z:int((z>0.5).sum())),day_mean=("success","mean")).reset_index()
        v=v.merge(lsum,on=["rule_family","rule"],how="left")
        veto=v[(v.blind_tests>=5)&(v.blind_rate<0.35)].copy()
        veto["veto"]="NEGATIF_KOSUL"
    else:
        veto=pd.DataFrame()
    return {"01_COMMON_EVIDENCE.csv":E,"02_BLIND_VALIDATION.csv":v,
            "03_VALIDATED_RULES.csv":v[v.status=="DOGRULANDI"] if not v.empty else pd.DataFrame(),
            "04_INSUFFICIENT_RULES.csv":v[v.status!="DOGRULANDI"] if not v.empty else pd.DataFrame(),
            "05_VETO_RULES.csv":veto}

V51_DISPATCH = {
    "01_GAME_CHARACTER": _v51_expert_game_character,
    "02_TEMPERATURE_SURFACE": _v51_expert_temperature,
    "03_PRESSURE_800": _v51_expert_800,
    "04_BAND_NEIGHBOR": _v51_expert_band_neighbor,
    "05_CONSECUTIVE_BLOCKS": _v51_expert_blocks,
    "06_RHYTHMIC_SEQUENCES": _v51_expert_rhythm,
    "07_LAST_DIGIT_FAMILIES": _v51_expert_lastdigit,
    "08_TENS_GEOMETRY": _v51_expert_tens,
    "09_CARRY_RETURN_H1_H8": _v51_expert_carry,
    "10_AGE_SLEEP_CYCLE": _v51_expert_age,
    "11_SOCIAL_NETWORK_2_6": _v51_expert_social,
    "12_LEADER_FOLLOWER": _v51_expert_leadfollow,
    "13_HOUR_PHASE": _v51_expert_hour,
    "14_CHARACTER_BREAKS": _v51_expert_breaks,
    "15_PARITY_DISTRIBUTION": _v51_expert_parity,
    "16_POOL_DYNAMICS": _v51_expert_pool,
    "17_CLUSTER_MIGRATION": _v51_expert_migration,
    "18_NUMBER_MEMORY": _v51_expert_memory,
    "19_NEGATIVE60": _v51_expert_negative60,
    "20_BLIND_VALIDATION": _v51_expert_validation,
}

_V51_CACHE=Path(".hizli_on_v51_full_cache")
_V51_CACHE.mkdir(parents=True,exist_ok=True)

def _v51_cache_path(code): return _V51_CACHE/f"{code}.zip"

def _v51_run_expert(df,code):
    x=_v51_x(df)
    tables=V51_DISPATCH[code](x)
    manifest=[
        f"HIZLI ON V5.1 FULL RESEARCH — {code}",
        "PRE-H -> POST-H ayrımı zorunludur.",
        "Kupon üretimi yoktur.",
        "Uzmanlar ayrı tutulur; tek kaba puanda ezilmez.",
    ]
    b=_v51_save_zip(code,tables,manifest)
    _v51_cache_path(code).write_bytes(b)
    return b

def _v51_load_done():
    d={}
    for code,_ in V51_EXPERTS:
        p=_v51_cache_path(code)
        if p.exists() and p.stat().st_size>0:
            try:
                b=p.read_bytes()
                with zipfile.ZipFile(io.BytesIO(b),"r") as z:
                    if z.testzip() is None: d[code]=b
            except Exception: pass
    return d

def _v51_final_zip(df,done):
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_MASTER_VERI_14_GUN.txt",serialize_master_txt(df))
        manifest=[
            "HIZLI ON — V5.1 FULL RESEARCH RESULTS",
            "Aralık: 25.08.2026–07.09.2026",
            "14 gün / 3038 çekiliş",
            "Kupon üretimi: KAPALI",
            "Karakter ve tüm sinyaller PRE-H; hedef sonuç yalnız doğrulama etiketi.",
            "",
            "UZMANLAR:"
        ]
        for code,label in V51_EXPERTS:
            manifest.append(f"{code} — {label}")
            z.writestr(f"UZMANLAR/{code}.zip",done[code])
        z.writestr("00_V51_ARCHITECTURE_MANIFEST.txt","\n".join(manifest)+"\n")
    return bio.getvalue()

st.divider()
st.header("🧠 V5.1 FULL RESEARCH ARCHITECTURE — 14 GÜN")
st.caption("Tam donanımlı araştırma laboratuvarı. Her uzman ayrı çalışır ve kalıcı ZIP olarak saklanır. Sonunda yalnız TEK sonuç ZIP'i indirirsin.")

_done51=_v51_load_done()
_p51=len(_done51)
st.progress(_p51/len(V51_EXPERTS), text=f"V5.1 uzman ilerleme: {_p51}/{len(V51_EXPERTS)}")

if _done51:
    st.write("Hazır uzmanlar:", " • ".join(code for code,_ in V51_EXPERTS if code in _done51))

c51a,c51b=st.columns(2)
with c51a:
    if st.button("▶️ SONRAKİ UZMANI ÇALIŞTIR",use_container_width=True,type="primary",
                 key="v51_run_next",disabled=(_p51>=len(V51_EXPERTS))):
        _next=next(code for code,_ in V51_EXPERTS if code not in _done51)
        _label=dict(V51_EXPERTS)[_next]
        _st=st.status(f"{_next} — {_label} çalışıyor…",expanded=True)
        try:
            _v51_run_expert(df,_next)
            _st.update(label=f"✅ {_next} tamamlandı ve kalıcı kaydedildi",state="complete",expanded=False)
            st.rerun()
        except Exception as _e:
            _st.update(label=f"❌ {_next} hata verdi",state="error",expanded=True)
            st.exception(_e)
with c51b:
    if st.button("♻️ V5.1 ARAŞTIRMA ÖNBELLEĞİNİ SIFIRLA",use_container_width=True,key="v51_reset"):
        for p in _V51_CACHE.glob("*.zip"):
            try: p.unlink()
            except Exception: pass
        st.session_state.pop("v51_final_zip",None)
        st.rerun()

_done51=_v51_load_done()
if len(_done51)==len(V51_EXPERTS):
    if "v51_final_zip" not in st.session_state:
        st.session_state["v51_final_zip"]=_v51_final_zip(df,_done51)
    st.success("✅ V5.1 FULL RESEARCH tamamlandı. 20 uzman tek sonuç ZIP'inde birleştirildi.")
    st.download_button(
        "⬇️ V5.1 FULL RESEARCH — TEK SONUÇ ZIP'İNİ İNDİR",
        st.session_state["v51_final_zip"],
        "HIZLI_ON_V5_1_FULL_RESEARCH_RESULTS.zip",
        "application/zip",use_container_width=True,key="v51_final_download"
    )
# =====================================================================
# /V5.1 FULL RESEARCH ARCHITECTURE
# =====================================================================



# =====================================================================
# V5.2 EKSİK KAPATMA / 80→20 AYRIŞTIRMA LABORATUVARI
# Amaç: PRE-H özelliklerinden GERÇEK20 ile NEGATİF60'ı ayırmak,
# karakter tahmin doğruluğunu ölçmek, sayı-bulucu/veto adaylarını
# kronolojik kör testte sınamak. Kupon üretimi YOK.
# =====================================================================

_V52_CACHE = Path(".hizli_on_v52_cache")
_V52_CACHE.mkdir(parents=True, exist_ok=True)

V52_STEPS = [
    ("01_MATRIX_80_20", "Her hedef için 80 sayılık PRE-H özellik matrisi"),
    ("02_CHARACTER_ACCURACY", "Oyun karakteri çözülme/doğruluk raporu"),
    ("03_SINGLE_RULES", "Tek özelliklerin GERÇEK20/NEGATİF60 ayrıştırması"),
    ("04_COMBINATIONS", "Karakter-koşullu 2'li uzman kombinasyonları"),
    ("05_VETO", "Güçlü görünen ama NEGATİF60'ta kalan veto koşulları"),
    ("06_FINAL_VALIDATION", "Walk-forward doğrulama + sayı bulucu/veto sınıflaması"),
]

def _v52_cache(code):
    return _V52_CACHE / f"{code}.pkl"

def _v52_csv_zip(code, tables, note_lines=None):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        if note_lines:
            z.writestr("00_README.txt", "\n".join(note_lines) + "\n")
        for fn, tab in tables.items():
            if tab is None:
                tab = pd.DataFrame()
            z.writestr(fn, tab.to_csv(index=False).encode("utf-8-sig"))
    return bio.getvalue()

def _v52_gap_band(g):
    g=int(g)
    if g==0: return "0"
    if g<=2: return "1-2"
    if g<=5: return "3-5"
    if g<=11: return "6-11"
    if g<=23: return "12-23"
    return "24+"

def _v52_rank_band(r):
    r=int(r)
    if r<=5: return "R01-05"
    if r<=10: return "R06-10"
    if r<=20: return "R11-20"
    if r<=30: return "R21-30"
    if r<=40: return "R31-40"
    if r<=60: return "R41-60"
    return "R61-80"

def _v52_count_bin(v):
    v=int(v)
    return str(v) if v<=4 else "5+"

def _v52_carry_class(v):
    v=int(v)
    if v<=3: return "LOW_0_3"
    if v<=6: return "MID_4_6"
    return "HIGH_7+"

def _v52_block_class(v):
    v=int(v)
    if v<=2: return "LOW_0_2"
    if v<=4: return "MID_3_4"
    return "HIGH_5+"

def _v52_even_class(v):
    v=int(v)
    if v<=7: return "ODD_HEAVY"
    if v>=13: return "EVEN_HEAVY"
    return "BALANCED"

def _v52_low_class(v):
    v=int(v)
    if v<=7: return "HIGH_SIDE"
    if v>=13: return "LOW_SIDE"
    return "BALANCED"

def _v52_sum_class(v):
    v=float(v)
    if v<760: return "<760"
    if v<790: return "760-789"
    if v<810: return "790-809"
    if v<830: return "810-829"
    if v<860: return "830-859"
    return "860+"

def _v52_mode(vals, default="NA"):
    vals=[v for v in vals if v is not None]
    if not vals: return default
    c=Counter(vals)
    return c.most_common(1)[0][0]

def _v52_online_pair_support(history_sets, h1, n, lookback=24):
    # PRE-H only: candidate n'nin H1 üyeleriyle son lookback içindeki birlikte-yaşam desteği.
    if not history_sets: return 0.0
    hs=history_sets[-lookback:]
    partners=[m for m in h1 if m!=n]
    if not partners: return 0.0
    n_seen=sum(n in S for S in hs)
    if n_seen==0: return 0.0
    vals=[]
    for m in partners:
        both=sum((n in S and m in S) for S in hs)
        vals.append(both/n_seen)
    vals.sort(reverse=True)
    return float(sum(vals[:3])/min(3,len(vals))) if vals else 0.0

def _v52_rhythm_support(h1, n):
    # n hedef adayı; H1 içinde n ile aynı sabit-adım ailesini destekleyen sayıları say.
    # +2..+20; 2–6'lı ailelerin kaba PRE-H destek yoğunluğu.
    s=0
    for step in range(2,21):
        neigh=[n-step,n+step,n-2*step,n+2*step]
        hits=sum(1 for m in neigh if 1<=m<=80 and m in h1)
        if hits>=1: s+=1
        if hits>=2: s+=1
    return s

def _v52_block_shift_support(h1, n):
    # H1 ardışık bloklarının sabit/±1/±2 kaymış halinde n bulunuyor mu?
    sup=0
    for b in _v51_blocks(h1):
        bs=set(b)
        for d in (-2,-1,0,1,2):
            sh={m+d for m in bs if 1<=m+d<=80}
            if len(sh)==len(bs) and n in sh:
                sup+=1
    return sup

def _v52_build_matrix(df):
    x=_v51_x(df)
    char=_v51_character_rows(x).set_index("idx")
    rows=[]
    last_seen={n:None for n in range(1,81)}
    history_sets=[]

    # last_seen must represent PRE-H. Seed sequentially.
    for i in range(len(x)):
        cur=x.iloc[i].numset
        if i < 8:
            history_sets.append(cur)
            for n in cur: last_seen[n]=i
            continue

        h=[x.iloc[i-k].numset for k in range(1,9)]
        h1=h[0]
        f5=_v51_roll_freq(x,i,5)
        f10=_v51_roll_freq(x,i,10)
        f20=_v51_roll_freq(x,i,20)
        f40=_v51_roll_freq(x,i,40)
        temp={n:0.35*f5[n]+0.30*f10[n]+0.20*f20[n]+0.15*f40[n] for n in range(1,81)}
        order=sorted(temp,key=lambda n:(temp[n],f10[n],-n),reverse=True)
        rank={n:r+1 for r,n in enumerate(order)}

        reg=char.loc[i,"pre_regime"] if i in char.index else "NA"
        phase=_v51_phase(x.iloc[i].time)
        h1sum=int(x.iloc[i-1].sum20)
        h2sum=int(x.iloc[i-2].sum20)
        zone=_v51_zone800(h1sum)
        osc=_v51_osc800(h1sum,h2sum)

        # H1 family densities.
        last_digit_count=Counter(n%10 for n in h1)
        tens_count={}
        for b in range(8):
            lo=10*b+1; hi=lo+9
            tens_count[b]=sum(lo<=m<=hi for m in h1)

        for n in range(1,81):
            gap=i if last_seen[n] is None else i-last_seen[n]-1
            nearest=next((k+1 for k,S in enumerate(h) if n in S),0)
            r1=sum((m in h1) for m in range(max(1,n-1),min(80,n+1)+1) if m!=n)
            r2=sum((m in h1) for m in range(max(1,n-2),min(80,n+2)+1) if m!=n)
            r3=sum((m in h1) for m in range(max(1,n-3),min(80,n+3)+1) if m!=n)
            bidx=min(7,(n-1)//10)
            local5=sum(max(1,n-2)<=m<=min(80,n+2) for m in h1)
            local10=sum(max(1,n-5)<=m<=min(80,n+4) for m in h1)
            local20=sum(max(1,n-10)<=m<=min(80,n+9) for m in h1)

            rhythm=_v52_rhythm_support(h1,n)
            bshift=_v52_block_shift_support(h1,n)
            social=_v52_online_pair_support(history_sets,h1,n,lookback=24)

            rows.append({
                "draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                "number":n,"actual":int(n in cur),
                "pre_regime":reg,"phase":phase,"zone800":zone,"osc800":osc,
                "H1_sum":h1sum,
                "temp_score":temp[n],"temp_rank":rank[n],"temp_rank_band":_v52_rank_band(rank[n]),
                "temp_slope_5_20":f5[n]-f20[n],
                "f5":f5[n],"f10":f10[n],"f20":f20[n],"f40":f40[n],
                "hot5":int(rank[n]<=5),"hot10":int(rank[n]<=10),"hot20":int(rank[n]<=20),"hot30":int(rank[n]<=30),
                **{f"H{k}":int(n in h[k-1]) for k in range(1,9)},
                "nearest_lag":nearest,"gap":gap,"gap_band":_v52_gap_band(gap),
                "last_digit":n%10,"last_digit_H1_count":last_digit_count[n%10],
                "last_digit_H1_bin":_v52_count_bin(last_digit_count[n%10]),
                "tens_band":bidx+1,"tens_H1_count":tens_count[bidx],"tens_H1_bin":_v52_count_bin(tens_count[bidx]),
                "neighbor_r1":r1,"neighbor_r2":r2,"neighbor_r3":r3,
                "local5_H1":local5,"local10_H1":local10,"local20_H1":local20,
                "rhythm_support":rhythm,"rhythm_bin":("0" if rhythm==0 else "1-3" if rhythm<=3 else "4-7" if rhythm<=7 else "8+"),
                "block_shift_support":bshift,"block_shift_bin":("0" if bshift==0 else "1" if bshift==1 else "2-3" if bshift<=3 else "4+"),
                "social_support":social,"social_bin":("LOW" if social<0.20 else "MID" if social<0.40 else "HIGH"),
            })

        history_sets.append(cur)
        for n in cur: last_seen[n]=i

    return pd.DataFrame(rows)

def _v52_character_accuracy(df):
    x=_v51_x(df)
    rows=[]
    # Predict each H character component from only earlier realized components, using trailing mode/mean.
    realized=[]
    for i in range(2,len(x)):
        cur=x.iloc[i].numset
        h1=x.iloc[i-1].numset
        blocks=len(_v51_blocks(cur))
        carry=len(h1 & cur)
        even=sum(n%2==0 for n in cur)
        low=sum(n<=40 for n in cur)
        bcounts=[sum(10*k+1<=n<=10*k+10 for n in cur) for k in range(8)]
        peak=int(np.argmax(bcounts))+1
        actual={
            "sum_zone":_v52_sum_class(x.iloc[i].sum20),
            "carry_class":_v52_carry_class(carry),
            "block_class":_v52_block_class(blocks),
            "even_class":_v52_even_class(even),
            "low_class":_v52_low_class(low),
            "peak_band":str(peak),
        }
        # trailing 24 realized labels; no current H leakage.
        hist=realized[-24:]
        pred={}
        for k in actual:
            pred[k]=_v52_mode([r[k] for r in hist], default="NA")
        row={"draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time}
        for k in actual:
            row[f"pred_{k}"]=pred[k]; row[f"actual_{k}"]=actual[k]
            row[f"ok_{k}"]=int(pred[k]==actual[k] and pred[k]!="NA")
        rows.append(row)
        realized.append(actual)

    a=pd.DataFrame(rows)
    metrics=[]
    for k in ["sum_zone","carry_class","block_class","even_class","low_class","peak_band"]:
        valid=a[a[f"pred_{k}"]!="NA"]
        metrics.append({"component":k,"tests":len(valid),"correct":int(valid[f"ok_{k}"].sum()),
                        "accuracy":float(valid[f"ok_{k}"].mean()) if len(valid) else 0.0})
    m=pd.DataFrame(metrics)
    if not a.empty:
        oks=[c for c in a.columns if c.startswith("ok_")]
        a["character_component_score"]=a[oks].mean(axis=1)
    overall=pd.DataFrame([{
        "tests":len(a),
        "mean_component_accuracy":float(m.accuracy.mean()) if not m.empty else 0.0,
        "mean_per_draw_component_score":float(a.character_component_score.mean()) if len(a) else 0.0
    }])
    return {"01_CHARACTER_PREDICTIONS.csv":a,"02_COMPONENT_ACCURACY.csv":m,"03_OVERALL_CHARACTER_SCORE.csv":overall}

def _v52_rule_stats(g, base=0.25):
    tests=len(g); hits=int(g.actual.sum()); rate=float(g.actual.mean()) if tests else 0.0
    return tests,hits,rate,(rate/base if base else 0.0),rate-base

V52_RULE_FIELDS = [
    "pre_regime","phase","zone800","osc800","temp_rank_band","gap_band","nearest_lag",
    "last_digit_H1_bin","tens_H1_bin","rhythm_bin","block_shift_bin","social_bin",
    "H1","H2","H3","neighbor_r1","neighbor_r2","neighbor_r3"
]

def _v52_single_rules(matrix):
    rows=[]
    for f in V52_RULE_FIELDS:
        for val,g in matrix.groupby(f,dropna=False):
            tests,hits,rate,lift,effect=_v52_rule_stats(g)
            if tests<80: continue
            rows.append({"feature":f,"value":str(val),"tests":tests,"hits":hits,"hit_rate":rate,
                         "base_rate":0.25,"lift":lift,"abs_effect":effect})
    a=pd.DataFrame(rows)
    if not a.empty:
        a["direction"]=np.where(a.hit_rate>0.25,"SELECTOR","VETO")
        a=a.sort_values(["abs_effect","tests"],key=lambda col:col.abs() if col.name=="abs_effect" else col,
                        ascending=[False,False])
    return a

def _v52_combo_rules(matrix):
    # Pairwise categorical rules, chronologically blind validated.
    fields=[
        "pre_regime","phase","zone800","osc800","temp_rank_band","gap_band","nearest_lag",
        "last_digit_H1_bin","tens_H1_bin","rhythm_bin","block_shift_bin","social_bin","H1","H2","H3"
    ]
    cut_draw=int(matrix.draw_no.quantile(0.70))
    tr=matrix[matrix.draw_no<cut_draw]
    te=matrix[matrix.draw_no>=cut_draw]
    rows=[]
    for f1,f2 in combinations(fields,2):
        grp=tr.groupby([f1,f2],dropna=False).actual.agg(["count","sum","mean"]).reset_index()
        grp=grp[grp["count"]>=100]
        for _,r in grp.iterrows():
            mask=(te[f1]==r[f1])&(te[f2]==r[f2])
            tg=te[mask]
            if len(tg)<30: continue
            blind=float(tg.actual.mean())
            train=float(r["mean"])
            rows.append({
                "feature1":f1,"value1":str(r[f1]),"feature2":f2,"value2":str(r[f2]),
                "train_tests":int(r["count"]),"train_hits":int(r["sum"]),"train_rate":train,
                "blind_tests":len(tg),"blind_hits":int(tg.actual.sum()),"blind_rate":blind,
                "train_lift":train/0.25,"blind_lift":blind/0.25,
                "blind_effect":blind-0.25,
                "stability_ratio":(blind/train if train>0 else 0.0),
            })
    a=pd.DataFrame(rows)
    if not a.empty:
        a["status"]=np.where(
            (a.blind_tests>=30)&
            (((a.train_rate>0.25)&(a.blind_rate>0.25)&(a.stability_ratio>=0.75)) |
             ((a.train_rate<0.25)&(a.blind_rate<0.25)&(a.blind_rate<=a.train_rate*1.25))),
            "BLIND_CONFIRMED","INSUFFICIENT"
        )
        a["role"]=np.where(a.blind_rate>0.25,"SELECTOR","VETO")
        a=a.sort_values(["status","blind_effect","blind_tests"],
                        key=lambda col: col.abs() if col.name=="blind_effect" else col,
                        ascending=[True,False,False])
    return a

def _v52_veto(matrix, single, combo):
    # Strong-looking PRE-H candidates that still land in negative60.
    m=matrix.copy()
    m["looks_strong"]=(
        (m.temp_rank<=20).astype(int)+m.H1.astype(int)+m.H2.astype(int)+
        (m.social_support>=0.40).astype(int)+(m.rhythm_support>=4).astype(int)+
        (m.block_shift_support>=2).astype(int)+(m.neighbor_r2>=2).astype(int)
    )
    hard=m[m.looks_strong>=4]
    prof=(hard.groupby(["pre_regime","temp_rank_band","gap_band","rhythm_bin","block_shift_bin","social_bin"])
          .actual.agg(["count","sum","mean"]).reset_index())
    prof=prof[prof["count"]>=30].rename(columns={"count":"tests","sum":"hits","mean":"hit_rate"})
    prof["negative60_rate"]=1-prof.hit_rate
    prof["veto_effect_vs_base"]=0.25-prof.hit_rate
    prof=prof.sort_values(["veto_effect_vs_base","tests"],ascending=[False,False])
    confirmed_combo=combo[(combo.status=="BLIND_CONFIRMED")&(combo.role=="VETO")].copy() if not combo.empty else pd.DataFrame()
    return {"01_STRONG_LOOKING_NEG60_PROFILES.csv":prof,"02_BLIND_CONFIRMED_VETO_COMBOS.csv":confirmed_combo}

def _v52_final_validation(matrix, single, combo):
    # Day-by-day robustness + minimum evidence.
    rows=[]
    if combo.empty:
        return pd.DataFrame(),pd.DataFrame(),pd.DataFrame()
    confirmed=combo[combo.status=="BLIND_CONFIRMED"].copy()
    for _,r in confirmed.iterrows():
        f1,f2=r.feature1,r.feature2
        # compare as strings to preserve int/category mixed types
        g=matrix[(matrix[f1].astype(str)==str(r.value1))&(matrix[f2].astype(str)==str(r.value2))]
        day=g.groupby("date").actual.agg(["count","sum","mean"]).reset_index()
        valid_days=day[day["count"]>=5]
        if len(valid_days)==0: continue
        positive_days=int((valid_days["mean"]>0.25).sum())
        negative_days=int((valid_days["mean"]<0.25).sum())
        role=r.role
        consistent_days=positive_days if role=="SELECTOR" else negative_days
        rows.append({
            "role":role,"feature1":f1,"value1":r.value1,"feature2":f2,"value2":r.value2,
            "blind_tests":int(r.blind_tests),"blind_rate":float(r.blind_rate),"blind_lift":float(r.blind_lift),
            "days_tested":len(valid_days),"consistent_days":consistent_days,
            "day_consistency":consistent_days/len(valid_days),
            "final_status":"VALIDATED" if len(valid_days)>=5 and consistent_days/len(valid_days)>=0.60 else "INSUFFICIENT"
        })
    v=pd.DataFrame(rows)
    sel=v[(v.final_status=="VALIDATED")&(v.role=="SELECTOR")].copy() if not v.empty else pd.DataFrame()
    veto=v[(v.final_status=="VALIDATED")&(v.role=="VETO")].copy() if not v.empty else pd.DataFrame()
    return v,sel,veto

def _v52_run_step(df,code):
    # Load prior dependencies from cache; compute only one heavy stage per click.
    if code=="01_MATRIX_80_20":
        matrix=_v52_build_matrix(df)
        obj={"matrix":matrix}
        tables={"01_PREH_80_TO_20_MATRIX.csv":matrix}
    elif code=="02_CHARACTER_ACCURACY":
        obj=_v52_character_accuracy(df)
        tables=obj
    elif code=="03_SINGLE_RULES":
        matrix=pd.read_pickle(_v52_cache("01_MATRIX_80_20"))["matrix"]
        rules=_v52_single_rules(matrix)
        obj={"single":rules}
        tables={"01_SINGLE_RULE_SEPARATION.csv":rules}
    elif code=="04_COMBINATIONS":
        matrix=pd.read_pickle(_v52_cache("01_MATRIX_80_20"))["matrix"]
        combo=_v52_combo_rules(matrix)
        obj={"combo":combo}
        tables={"01_PAIRWISE_BLIND_COMBINATIONS.csv":combo,
                "02_CONFIRMED_COMBINATIONS.csv":combo[combo.status=="BLIND_CONFIRMED"] if not combo.empty else pd.DataFrame()}
    elif code=="05_VETO":
        matrix=pd.read_pickle(_v52_cache("01_MATRIX_80_20"))["matrix"]
        single=pd.read_pickle(_v52_cache("03_SINGLE_RULES"))["single"]
        combo=pd.read_pickle(_v52_cache("04_COMBINATIONS"))["combo"]
        obj=_v52_veto(matrix,single,combo)
        tables=obj
    elif code=="06_FINAL_VALIDATION":
        matrix=pd.read_pickle(_v52_cache("01_MATRIX_80_20"))["matrix"]
        single=pd.read_pickle(_v52_cache("03_SINGLE_RULES"))["single"]
        combo=pd.read_pickle(_v52_cache("04_COMBINATIONS"))["combo"]
        v,sel,veto=_v52_final_validation(matrix,single,combo)
        obj={"validation":v,"selectors":sel,"vetos":veto}
        tables={"01_DAY_ROBUSTNESS_VALIDATION.csv":v,
                "02_VALIDATED_SELECTORS.csv":sel,
                "03_VALIDATED_VETOS.csv":veto}
    else:
        raise ValueError(code)

    pd.to_pickle(obj,_v52_cache(code))
    return _v52_csv_zip(code,tables,[
        f"HIZLI ON V5.2 — {code}",
        "Amaç: GERÇEK20 / NEGATİF60 ayrıştırması.",
        "Bütün özellikler PRE-H; actual etiketi yalnız POST-H.",
        "Baz oran: 20/80 = 0.25.",
        "Kupon üretimi yoktur."
    ])

def _v52_done():
    return {code:_v52_cache(code).exists() for code,_ in V52_STEPS}

def _v52_final_zip(df):
    matrix=pd.read_pickle(_v52_cache("01_MATRIX_80_20"))["matrix"]
    char=pd.read_pickle(_v52_cache("02_CHARACTER_ACCURACY"))
    single=pd.read_pickle(_v52_cache("03_SINGLE_RULES"))["single"]
    combo=pd.read_pickle(_v52_cache("04_COMBINATIONS"))["combo"]
    veto_obj=pd.read_pickle(_v52_cache("05_VETO"))
    final=pd.read_pickle(_v52_cache("06_FINAL_VALIDATION"))
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_MASTER_VERI_14_GUN.txt",serialize_master_txt(df))
        z.writestr("00_ARCHITECTURE.txt",
            "V5.2 EKSİK KAPATMA / 80→20 AYRIŞTIRMA\n"
            "PRE-H -> POST-H zorunlu.\n"
            "Baz oran 0.25.\n"
            "Sayı bulucu ve veto ancak kör + günler arası doğrulama ile VALIDATED olur.\n"
            "Kupon üretimi kapalıdır.\n")
        z.writestr("01_80_TO_20_MATRIX.csv",matrix.to_csv(index=False).encode("utf-8-sig"))
        for fn,tab in char.items():
            z.writestr("02_CHARACTER/"+fn,tab.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("03_SINGLE_RULES.csv",single.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("04_PAIRWISE_BLIND_COMBINATIONS.csv",combo.to_csv(index=False).encode("utf-8-sig"))
        for fn,tab in veto_obj.items():
            z.writestr("05_VETO/"+fn,tab.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("06_FINAL/01_DAY_ROBUSTNESS_VALIDATION.csv",final["validation"].to_csv(index=False).encode("utf-8-sig"))
        z.writestr("06_FINAL/02_VALIDATED_SELECTORS.csv",final["selectors"].to_csv(index=False).encode("utf-8-sig"))
        z.writestr("06_FINAL/03_VALIDATED_VETOS.csv",final["vetos"].to_csv(index=False).encode("utf-8-sig"))
    return bio.getvalue()

st.divider()
st.header("🔬 V5.2 EKSİK KAPATMA — 80→20 AYRIŞTIRMA")
st.caption("Karakteri ölçmekten gerçek 20 sayıya geçiş köprüsü. 80 sayı aynı anda karşılaştırılır; çıkan20 ve dışarıda60 aynı PRE-H özellik uzayında test edilir.")

_d52=_v52_done()
_n52=sum(_d52.values())
st.progress(_n52/len(V52_STEPS),text=f"V5.2 ilerleme: {_n52}/{len(V52_STEPS)}")

if _n52:
    st.write("Hazır:", " • ".join(code for code,_ in V52_STEPS if _d52[code]))

c52a,c52b=st.columns(2)
with c52a:
    if st.button("▶️ V5.2 SONRAKİ ADIMI ÇALIŞTIR",use_container_width=True,type="primary",
                 key="v52_next",disabled=(_n52>=len(V52_STEPS))):
        _next=next(code for code,_ in V52_STEPS if not _d52[code])
        _label=dict(V52_STEPS)[_next]
        _st52=st.status(f"{_next} — {_label} çalışıyor…",expanded=True)
        try:
            _zip52=_v52_run_step(df,_next)
            st.session_state[f"v52_zip_{_next}"]=_zip52
            _st52.update(label=f"✅ {_next} tamamlandı ve kalıcı kaydedildi",state="complete",expanded=False)
            st.rerun()
        except Exception as _e:
            _st52.update(label=f"❌ {_next} hata verdi",state="error",expanded=True)
            st.exception(_e)
with c52b:
    if st.button("♻️ V5.2 ÖNBELLEĞİNİ SIFIRLA",use_container_width=True,key="v52_reset"):
        for p in _V52_CACHE.glob("*.pkl"):
            try:p.unlink()
            except Exception:pass
        st.session_state.pop("v52_final_zip",None)
        st.rerun()

_d52=_v52_done()
if all(_d52.values()):
    if "v52_final_zip" not in st.session_state:
        st.session_state["v52_final_zip"]=_v52_final_zip(df)
    st.success("✅ V5.2 tamamlandı: karakter çözülme + 80→20 ayrıştırma + kombinasyon + veto + walk-forward doğrulama hazır.")
    st.download_button(
        "⬇️ V5.2 EKSİK KAPATMA — TEK SONUÇ ZIP'İNİ İNDİR",
        st.session_state["v52_final_zip"],
        "HIZLI_ON_V5_2_80_TO_20_GAP_CLOSURE_RESULTS.zip",
        "application/zip",use_container_width=True,key="v52_final_download"
    )
# =====================================================================
# /V5.2
# =====================================================================



# =====================================================================
# V5.3 GERÇEK WALK-FORWARD HAKEMİ
# Kural: hedef H veya daha sonrası keşif/seçim/eşik ayarında ASLA kullanılamaz.
# Her test bloğunda kurallar yalnız geçmişten öğrenilir, dondurulur, sonra test edilir.
# Kupon üretimi YOK.
# =====================================================================
_V53_CACHE=Path(".hizli_on_v53_cache")
_V53_CACHE.mkdir(parents=True,exist_ok=True)

V53_FIELDS=[
 "pre_regime","phase","zone800","osc800","temp_rank_band","gap_band","nearest_lag",
 "last_digit_H1_bin","tens_H1_bin","rhythm_bin","block_shift_bin","social_bin",
 "H1","H2","H3","neighbor_r1","neighbor_r2","neighbor_r3"
]

def _v53_learn_rules(train,min_train=160,min_days=5,min_effect=0.035):
    rows=[]
    base=0.25
    # single + pair rules. No test information is used here.
    for f in V53_FIELDS:
        for val,g in train.groupby(f,dropna=False):
            if len(g)<min_train or g.date.nunique()<min_days: continue
            rate=float(g.actual.mean()); eff=rate-base
            if abs(eff)<min_effect: continue
            rows.append({"kind":"SINGLE","f1":f,"v1":str(val),"f2":"","v2":"",
                         "train_tests":len(g),"train_days":g.date.nunique(),"train_rate":rate,
                         "role":"SELECTOR" if eff>0 else "VETO","effect":eff})
    # Pair search uses only categorical fields with controlled cardinality.
    pair_fields=["pre_regime","phase","zone800","osc800","temp_rank_band","gap_band","nearest_lag",
                 "last_digit_H1_bin","tens_H1_bin","rhythm_bin","block_shift_bin","social_bin","H1","H2","H3"]
    for a in range(len(pair_fields)):
        for b in range(a+1,len(pair_fields)):
            f1,f2=pair_fields[a],pair_fields[b]
            gg=train.groupby([f1,f2],dropna=False,observed=True)
            for vals,g in gg:
                if len(g)<min_train or g.date.nunique()<min_days: continue
                rate=float(g.actual.mean()); eff=rate-base
                if abs(eff)<min_effect: continue
                rows.append({"kind":"PAIR","f1":f1,"v1":str(vals[0]),"f2":f2,"v2":str(vals[1]),
                             "train_tests":len(g),"train_days":g.date.nunique(),"train_rate":rate,
                             "role":"SELECTOR" if eff>0 else "VETO","effect":eff})
    r=pd.DataFrame(rows)
    if r.empty:return r
    # Prefer evidence and effect; cap correlated rule explosion per role.
    r["strength"]=r.effect.abs()*np.sqrt(r.train_tests)
    return r.sort_values(["role","strength"],ascending=[True,False]).groupby("role",group_keys=False).head(150).reset_index(drop=True)

def _v53_apply(test,rules):
    out=test[["draw_no","date","time","number","actual"]].copy()
    sel=np.zeros(len(test),dtype=np.int16); veto=np.zeros(len(test),dtype=np.int16)
    sw=np.zeros(len(test)); vw=np.zeros(len(test))
    for _,r in rules.iterrows():
        m=(test[r.f1].astype(str).to_numpy()==str(r.v1))
        if r.kind=="PAIR":
            m &= (test[r.f2].astype(str).to_numpy()==str(r.v2))
        w=min(0.20,abs(float(r.effect)))
        if r.role=="SELECTOR":
            sel[m]+=1; sw[m]+=w
        else:
            veto[m]+=1; vw[m]+=w
    out["selector_count"]=sel; out["veto_count"]=veto
    out["selector_weight"]=sw; out["veto_weight"]=vw
    out["net_count"]=sel-veto; out["net_weight"]=sw-vw
    return out

def _v53_run_walkforward(matrix,warmup_draws=900,test_block=120):
    m=matrix.sort_values(["draw_no","number"]).reset_index(drop=True)
    draws=sorted(m.draw_no.unique())
    allpred=[]; rulebook=[]; blocks=[]
    for pos in range(warmup_draws,len(draws),test_block):
        td=draws[pos:min(pos+test_block,len(draws))]
        if not td:break
        first=td[0]
        train=m[m.draw_no<first]
        test=m[m.draw_no.isin(td)]
        # CPU-safe: discover rules from a deterministic trailing training window.
        # Still strictly PRE-test; no future/test information enters discovery.
        train_rule=train[train.draw_no>=max(int(train.draw_no.min()), int(first)-720)]
        rules=_v53_learn_rules(train_rule,min_train=120,min_days=4,min_effect=0.035)
        pred=_v53_apply(test,rules)
        pred["wf_block"]=len(blocks)+1
        pred["train_last_draw"]=int(first-1)
        allpred.append(pred)
        rr=rules.copy()
        if not rr.empty:
            rr["wf_block"]=len(blocks)+1; rr["test_from"]=td[0]; rr["test_to"]=td[-1]
            rulebook.append(rr)
        blocks.append({"wf_block":len(blocks)+1,"train_draws":train.draw_no.nunique(),
                       "test_from":td[0],"test_to":td[-1],"test_draws":len(td),
                       "rules":len(rules),"selectors":int((rules.role=="SELECTOR").sum()) if len(rules) else 0,
                       "vetos":int((rules.role=="VETO").sum()) if len(rules) else 0})
    P=pd.concat(allpred,ignore_index=True) if allpred else pd.DataFrame()
    R=pd.concat(rulebook,ignore_index=True) if rulebook else pd.DataFrame()
    B=pd.DataFrame(blocks)
    return P,R,B

def _v53_reports(P):
    base=0.25
    if P.empty:return {}
    net=P.groupby("net_count").actual.agg(["count","sum","mean"]).reset_index()
    net.columns=["net_count","tests","hits","hit_rate"]; net["lift"]=net.hit_rate/base
    # draw-level "kaç tahmin / kaç isabet": thresholds are fixed BEFORE reading test results.
    rows=[]
    policies=[
      ("SEL_ANY",lambda g:(g.selector_count>=1)&(g.veto_count==0)),
      ("SEL_2PLUS",lambda g:(g.selector_count>=2)&(g.veto_count==0)),
      ("NET_1PLUS",lambda g:g.net_count>=1),
      ("NET_2PLUS",lambda g:g.net_count>=2),
      ("VETO_ANY",lambda g:g.veto_count>=1),
      ("VETO_2PLUS",lambda g:g.veto_count>=2),
    ]
    for name,fn in policies:
        for d,g in P.groupby("draw_no",sort=True):
            mask=fn(g)
            cand=g[mask]
            rows.append({"policy":name,"draw_no":d,"date":g.date.iloc[0],"time":g.time.iloc[0],
                         "predictions":len(cand),"hits":int(cand.actual.sum()),
                         "precision":float(cand.actual.mean()) if len(cand) else np.nan})
    D=pd.DataFrame(rows)
    S=D.groupby("policy").agg(draws=("draw_no","count"),draws_with_signal=("predictions",lambda z:int((z>0).sum())),
        predictions=("predictions","sum"),hits=("hits","sum")).reset_index()
    S["hit_rate"]=S.hits/S.predictions.replace(0,np.nan); S["lift"]=S.hit_rate/base
    # block stability
    K=P.groupby(["wf_block","net_count"]).actual.agg(["count","sum","mean"]).reset_index()
    K.columns=["wf_block","net_count","tests","hits","hit_rate"]
    return {"01_NET_COUNT_PERFORMANCE.csv":net,"02_DRAW_BY_DRAW_PREDICTIONS.csv":D,
            "03_POLICY_SUMMARY.csv":S,"04_BLOCK_STABILITY.csv":K}

def _v53_final_zip(matrix,P,R,B,reports):
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_README.txt",
          "V5.3 GERCEK WALK-FORWARD\n"
          "Her test blogu icin kurallar sadece onceki cekilislerden ogrenilir ve test boyunca dondurulur.\n"
          "Hedef/test sonuclari kural secimi veya esik ayarinda kullanilmaz.\n"
          "Baz oran 20/80=0.25. Kupon uretimi yoktur.\n")
        z.writestr("01_WF_BLOCKS.csv",B.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("02_FROZEN_RULEBOOK.csv",R.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("03_OUT_OF_SAMPLE_NUMBER_PREDICTIONS.csv",P.to_csv(index=False).encode("utf-8-sig"))
        for fn,t in reports.items():z.writestr("04_REPORTS/"+fn,t.to_csv(index=False).encode("utf-8-sig"))
    return bio.getvalue()

st.divider()
st.header("🧪 V5.3 GERÇEK WALK-FORWARD HAKEMİ")
st.caption("Geçmişte öğren → kuralı dondur → görülmemiş gelecekte test et. Test sonucu hiçbir biçimde kural seçimine geri sızmaz.")

_v53_done=(_V53_CACHE/"RESULTS.zip").exists()
if st.button("▶️ V5.3 GERÇEK WALK-FORWARD TESTİNİ ÇALIŞTIR",use_container_width=True,type="primary",
             key="v53_run",disabled=_v53_done):
    _st=st.status("V5.3: 80→20 matrisi hazırlanıyor…",expanded=True)
    try:
        _m=_v52_build_matrix(df)
        _st.write(f"Matris hazır: {len(_m):,} sayı-hedef kaydı.")
        _P,_R,_B=_v53_run_walkforward(_m,warmup_draws=900,test_block=120)
        _st.write(f"Gerçek ileri test: {_P.draw_no.nunique():,} hedef çekiliş.")
        _rep=_v53_reports(_P)
        _zip=_v53_final_zip(_m,_P,_R,_B,_rep)
        (_V53_CACHE/"RESULTS.zip").write_bytes(_zip)
        _st.update(label="✅ V5.3 gerçek walk-forward tamamlandı",state="complete",expanded=False)
        st.rerun()
    except Exception as _e:
        _st.update(label="❌ V5.3 hata verdi",state="error",expanded=True)
        st.exception(_e)

if (_V53_CACHE/"RESULTS.zip").exists():
    _b=(_V53_CACHE/"RESULTS.zip").read_bytes()
    st.success("V5.3 sonucu hazır. Bu ZIP yalnız out-of-sample ileri test sonuçlarını raporlar.")
    st.download_button("⬇️ V5.3 GERÇEK WALK-FORWARD — TEK ZIP",
        _b,"HIZLI_ON_V5_3_TRUE_WALK_FORWARD_RESULTS.zip","application/zip",
        use_container_width=True,key="v53_download")
# =====================================================================
# /V5.3
# =====================================================================



# =====================================================================
# V5.4 CHARACTER-FIRST TRUE WALK-FORWARD
# Ana ilke: sayı kimliği öğrenilmez. Önce PRE-H oyun karakteri belirlenir;
# yalnız aynı/benzer geçmiş karakter içindeki SAYI ROLLERİ öğrenilir.
# Sonra bugünkü 1..80 sayılar bu rollere yerleştirilir.
# Hedef/test sonucu keşif, karakter seçimi veya eşik ayarına sızamaz.
# Kupon üretimi YOK.
# =====================================================================
_V54_CACHE=Path(".hizli_on_v54_cache")
_V54_CACHE.mkdir(parents=True,exist_ok=True)

# Sayı kimliğinden bağımsız roller. "number" veya doğrudan sayı ID'si kural değildir.
V54_ROLE_FIELDS=[
 "temp_rank_band","gap_band","nearest_lag",
 "last_digit_H1_bin","tens_H1_bin","rhythm_bin","block_shift_bin","social_bin",
 "H1","H2","H3","neighbor_r1","neighbor_r2","neighbor_r3"
]

def _v54_character_signature(row):
    # Tamamı PRE-H: mevcut hedefin sonucunu kullanmaz.
    return (
        str(row["pre_regime"]),
        str(row["phase"]),
        str(row["zone800"]),
        str(row["osc800"]),
    )

def _v54_character_pool(train, test_signature, min_rows=2400):
    # 1) Önce tam aynı karakter.
    pr,ph,z,o=test_signature
    exact=train[
        (train.pre_regime.astype(str)==pr)&
        (train.phase.astype(str)==ph)&
        (train.zone800.astype(str)==z)&
        (train.osc800.astype(str)==o)
    ]
    if len(exact)>=min_rows:
        return exact,"EXACT_4"

    # 2) Karakter yetersizse kontrollü gevşetme:
    # pre_regime zorunlu kalır; sonra 800 salınımı/bölgesi, en son saat fazı gevşer.
    p3=train[
        (train.pre_regime.astype(str)==pr)&
        (train.zone800.astype(str)==z)&
        (train.osc800.astype(str)==o)
    ]
    if len(p3)>=min_rows:
        return p3,"REGIME_ZONE_OSC"

    p2=train[
        (train.pre_regime.astype(str)==pr)&
        (train.osc800.astype(str)==o)
    ]
    if len(p2)>=min_rows:
        return p2,"REGIME_OSC"

    p1=train[train.pre_regime.astype(str)==pr]
    if len(p1)>=min_rows:
        return p1,"REGIME_ONLY"

    # Karakter yeterli tarih üretmiyorsa uzman SUSAR; global sayı kuralına düşmez.
    return train.iloc[0:0].copy(),"NO_CHARACTER_HISTORY"

def _v54_learn_role_rules(pool,min_train=120,min_days=4,min_effect=0.035):
    base=.25
    rows=[]
    if pool.empty:return pd.DataFrame(rows)

    # Tek rol
    for f in V54_ROLE_FIELDS:
        for val,g in pool.groupby(f,dropna=False):
            if len(g)<min_train or g.date.nunique()<min_days:continue
            rate=float(g.actual.mean()); eff=rate-base
            if abs(eff)<min_effect:continue
            rows.append({"kind":"ROLE_SINGLE","f1":f,"v1":str(val),"f2":"","v2":"",
                         "train_tests":len(g),"train_days":g.date.nunique(),
                         "train_rate":rate,"effect":eff,
                         "role":"SELECTOR" if eff>0 else "VETO"})

    # İki rolün birleşimi
    for a in range(len(V54_ROLE_FIELDS)):
        for b in range(a+1,len(V54_ROLE_FIELDS)):
            f1,f2=V54_ROLE_FIELDS[a],V54_ROLE_FIELDS[b]
            for vals,g in pool.groupby([f1,f2],dropna=False,observed=True):
                if len(g)<min_train or g.date.nunique()<min_days:continue
                rate=float(g.actual.mean()); eff=rate-base
                if abs(eff)<min_effect:continue
                rows.append({"kind":"ROLE_PAIR","f1":f1,"v1":str(vals[0]),"f2":f2,"v2":str(vals[1]),
                             "train_tests":len(g),"train_days":g.date.nunique(),
                             "train_rate":rate,"effect":eff,
                             "role":"SELECTOR" if eff>0 else "VETO"})
    r=pd.DataFrame(rows)
    if r.empty:return r
    r["strength"]=r.effect.abs()*np.sqrt(r.train_tests)
    # Kural patlamasını engelle; her karakterde yalnız en kanıtlı roller.
    return (r.sort_values(["role","strength"],ascending=[True,False])
             .groupby("role",group_keys=False).head(100).reset_index(drop=True))

def _v54_apply_roles(test,rules):
    out=test[["draw_no","date","time","number","actual"]].copy()
    sel=np.zeros(len(test),dtype=np.int16); veto=np.zeros(len(test),dtype=np.int16)
    sw=np.zeros(len(test)); vw=np.zeros(len(test))
    for _,r in rules.iterrows():
        mask=(test[r.f1].astype(str).to_numpy()==str(r.v1))
        if r.kind=="ROLE_PAIR":
            mask &= (test[r.f2].astype(str).to_numpy()==str(r.v2))
        w=min(.20,abs(float(r.effect)))
        if r.role=="SELECTOR":
            sel[mask]+=1; sw[mask]+=w
        else:
            veto[mask]+=1; vw[mask]+=w
    out["selector_count"]=sel;out["veto_count"]=veto
    out["selector_weight"]=sw;out["veto_weight"]=vw
    out["net_count"]=sel-veto;out["net_weight"]=sw-vw
    return out

def _v54_run(matrix,warmup_draws=900,test_block=120,history_window=960):
    m=matrix.sort_values(["draw_no","number"]).reset_index(drop=True)
    draws=sorted(m.draw_no.unique())
    predictions=[]; rulebooks=[]; block_rows=[]; char_rows=[]

    for pos in range(warmup_draws,len(draws),test_block):
        td=draws[pos:min(pos+test_block,len(draws))]
        if not td:break
        first=td[0]
        # Yalnız geçmiş. Test bloğu asla eğitim havuzunda değildir.
        train=m[(m.draw_no<first)&(m.draw_no>=max(draws[0],first-history_window))]
        test_block_df=m[m.draw_no.isin(td)]

        block_pred=[]
        # Her hedefin PRE-H karakteri farklı olabilir; karaktere göre rol kitabı seçilir.
        # Aynı karakter imzası için aynı geçmişten öğrenilen kitap cache edilir.
        cache={}
        for d,g in test_block_df.groupby("draw_no",sort=True):
            sig=_v54_character_signature(g.iloc[0])
            if sig not in cache:
                pool,level=_v54_character_pool(train,sig)
                rules=_v54_learn_role_rules(pool)
                cache[sig]=(rules,level,len(pool),pool.date.nunique() if len(pool) else 0)
            rules,level,pool_n,pool_days=cache[sig]
            pp=_v54_apply_roles(g,rules)
            pp["character_regime"]=sig[0];pp["character_phase"]=sig[1]
            pp["character_zone800"]=sig[2];pp["character_osc800"]=sig[3]
            pp["match_level"]=level
            pp["character_history_rows"]=pool_n
            pp["character_history_days"]=pool_days
            pp["wf_block"]=len(block_rows)+1
            block_pred.append(pp)
            char_rows.append({"wf_block":len(block_rows)+1,"draw_no":d,"date":g.date.iloc[0],"time":g.time.iloc[0],
                              "pre_regime":sig[0],"phase":sig[1],"zone800":sig[2],"osc800":sig[3],
                              "match_level":level,"history_rows":pool_n,"history_days":pool_days,
                              "rules":len(rules),
                              "selectors":int((rules.role=="SELECTOR").sum()) if len(rules) else 0,
                              "vetos":int((rules.role=="VETO").sum()) if len(rules) else 0})
        if block_pred:
            bp=pd.concat(block_pred,ignore_index=True)
            predictions.append(bp)

        for sig,(rules,level,pool_n,pool_days) in cache.items():
            if len(rules):
                rr=rules.copy()
                rr["wf_block"]=len(block_rows)+1
                rr["pre_regime"],rr["phase"],rr["zone800"],rr["osc800"]=sig
                rr["match_level"]=level;rr["history_rows"]=pool_n;rr["history_days"]=pool_days
                rulebooks.append(rr)

        block_rows.append({"wf_block":len(block_rows)+1,"train_before":first,
                           "test_from":td[0],"test_to":td[-1],"test_draws":len(td),
                           "character_books":len(cache)})

    P=pd.concat(predictions,ignore_index=True) if predictions else pd.DataFrame()
    R=pd.concat(rulebooks,ignore_index=True) if rulebooks else pd.DataFrame()
    B=pd.DataFrame(block_rows); C=pd.DataFrame(char_rows)
    return P,R,B,C

def _v54_reports(P,C):
    if P.empty:return {}
    base=.25
    net=P.groupby("net_count").actual.agg(["count","sum","mean"]).reset_index()
    net.columns=["net_count","tests","hits","hit_rate"];net["lift"]=net.hit_rate/base

    # Karakter bazında gerçek OOS performans
    char=(P.groupby(["character_regime","match_level"])
          .actual.agg(["count","sum","mean"]).reset_index())
    char.columns=["character_regime","match_level","tests","hits","hit_rate"]
    char["lift"]=char.hit_rate/base

    rows=[]
    policies=[
      ("CHAR_SEL_ANY",lambda g:(g.selector_count>=1)&(g.veto_count==0)),
      ("CHAR_SEL_2PLUS",lambda g:(g.selector_count>=2)&(g.veto_count==0)),
      ("CHAR_NET_1PLUS",lambda g:g.net_count>=1),
      ("CHAR_NET_2PLUS",lambda g:g.net_count>=2),
      ("CHAR_VETO_ANY",lambda g:g.veto_count>=1),
      ("CHAR_VETO_2PLUS",lambda g:g.veto_count>=2),
    ]
    for name,fn in policies:
        for d,g in P.groupby("draw_no",sort=True):
            q=g[fn(g)]
            rows.append({"policy":name,"draw_no":d,"date":g.date.iloc[0],"time":g.time.iloc[0],
                         "pre_regime":g.character_regime.iloc[0],"match_level":g.match_level.iloc[0],
                         "predictions":len(q),"hits":int(q.actual.sum()),
                         "hit_rate":float(q.actual.mean()) if len(q) else np.nan})
    D=pd.DataFrame(rows)
    S=D.groupby("policy").agg(draws=("draw_no","count"),
        signal_draws=("predictions",lambda x:int((x>0).sum())),
        predictions=("predictions","sum"),hits=("hits","sum")).reset_index()
    S["hit_rate"]=S.hits/S.predictions.replace(0,np.nan);S["lift"]=S.hit_rate/base

    # Blok ve karakter kararlılığı
    K=(P.groupby(["wf_block","character_regime","net_count"])
       .actual.agg(["count","sum","mean"]).reset_index())
    K.columns=["wf_block","character_regime","net_count","tests","hits","hit_rate"]
    return {"01_NET_PERFORMANCE.csv":net,"02_CHARACTER_OOS_PERFORMANCE.csv":char,
            "03_DRAW_BY_DRAW.csv":D,"04_POLICY_SUMMARY.csv":S,
            "05_BLOCK_CHARACTER_STABILITY.csv":K,
            "06_CHARACTER_MATCH_AUDIT.csv":C}

def _v54_zip(P,R,B,C,reports):
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_README.txt",
          "V5.4 CHARACTER-FIRST TRUE WALK-FORWARD\n"
          "Sayi kimligi ogrenilmez. Once PRE-H karakter secilir, sonra ayni/benzer gecmis karakterde rol kurallari ogrenilir.\n"
          "pre_regime karakter eslesmesinde zorunludur; yeterli gecmis yoksa uzman susar.\n"
          "Test sonucu kural kesfine, esige veya karakter secimine sizmaz. Baz oran=0.25. Kupon yok.\n")
        z.writestr("01_WF_BLOCKS.csv",B.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("02_CHARACTER_MATCH_AUDIT.csv",C.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("03_FROZEN_CHARACTER_ROLE_RULEBOOK.csv",R.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("04_OOS_NUMBER_ROLE_PREDICTIONS.csv",P.to_csv(index=False).encode("utf-8-sig"))
        for fn,t in reports.items():
            z.writestr("05_REPORTS/"+fn,t.to_csv(index=False).encode("utf-8-sig"))
    return bio.getvalue()

st.divider()
st.header("🧬 V5.4 CHARACTER-FIRST — GERÇEK WALK-FORWARD")
st.caption("Rakam değişir; karakter ve rol öğrenilir. Önce oyun karakteri → aynı/benzer geçmiş karakter → çalışan sayı rolleri → bugünkü 1–80.")

if st.button("▶️ V5.4 KARAKTER-ÖNCELİKLİ İLERİ TESTİ ÇALIŞTIR",
             use_container_width=True,type="primary",key="v54_run",
             disabled=(_V54_CACHE/"RESULTS.zip").exists()):
    _s=st.status("V5.4 karakter-öncelikli walk-forward çalışıyor…",expanded=True)
    try:
        _m=_v52_build_matrix(df)
        _s.write(f"80→20 PRE-H matrisi: {len(_m):,} kayıt.")
        _P,_R,_B,_C=_v54_run(_m,warmup_draws=900,test_block=120,history_window=960)
        _s.write(f"Tamamen ileri test edilen hedef: {_P.draw_no.nunique():,}")
        _rep=_v54_reports(_P,_C)
        _bytes=_v54_zip(_P,_R,_B,_C,_rep)
        (_V54_CACHE/"RESULTS.zip").write_bytes(_bytes)
        _s.update(label="✅ V5.4 CHARACTER-FIRST tamamlandı",state="complete",expanded=False)
        st.rerun()
    except Exception as _e:
        _s.update(label="❌ V5.4 hata verdi",state="error",expanded=True)
        st.exception(_e)

if (_V54_CACHE/"RESULTS.zip").exists():
    st.success("V5.4 sonucu hazır: karakter → rol → sayı zincirinin gerçek out-of-sample testi.")
    st.download_button("⬇️ V5.4 CHARACTER-FIRST — TEK ZIP",
        (_V54_CACHE/"RESULTS.zip").read_bytes(),
        "HIZLI_ON_V5_4_CHARACTER_FIRST_TRUE_WF_RESULTS.zip",
        "application/zip",use_container_width=True,key="v54_download")
# =====================================================================
# /V5.4
# =====================================================================



# =====================================================================
# V5.5 CHARACTER-FIRST — PARÇALI/KALICI TRUE WALK-FORWARD
# V5.4 araştırma mantığı korunur; yalnız çalışma ve kayıt mimarisi değişir.
# Her basışta yalnız 1 test bloğu (120 çekiliş, son blok daha kısa olabilir)
# hesaplanır, kalıcı ZIP olarak saklanır. 18/18 tamamlanınca tek sonuç ZIP üretilir.
# =====================================================================

_V55_CACHE = Path(".hizli_on_v55_blocks")
_V55_CACHE.mkdir(parents=True, exist_ok=True)

def _v55_block_plan(matrix, warmup_draws=900, test_block=120):
    draws = sorted(matrix.draw_no.unique())
    plan=[]
    idx=1
    for pos in range(warmup_draws, len(draws), test_block):
        td = draws[pos:min(pos+test_block, len(draws))]
        if not td: break
        plan.append({
            "block": idx,
            "test_from": int(td[0]),
            "test_to": int(td[-1]),
            "test_draws": len(td),
            "train_before": int(td[0]),
        })
        idx += 1
    return plan

def _v55_block_path(k):
    return _V55_CACHE / f"block_{int(k):02d}.zip"

def _v55_is_valid_zip(path):
    try:
        if not path.exists() or path.stat().st_size == 0:
            return False
        with zipfile.ZipFile(path, "r") as z:
            return z.testzip() is None
    except Exception:
        return False

def _v55_saved_blocks(plan):
    done={}
    for p in plan:
        fp=_v55_block_path(p["block"])
        if _v55_is_valid_zip(fp):
            done[p["block"]] = fp
    return done

def _v55_compute_one_block(matrix, block_info, history_window=960):
    m = matrix.sort_values(["draw_no","number"]).reset_index(drop=True)
    td = sorted(m[(m.draw_no>=block_info["test_from"])&(m.draw_no<=block_info["test_to"])].draw_no.unique())
    if not td:
        raise RuntimeError("Test bloğu boş.")

    first = td[0]
    train = m[(m.draw_no < first) & (m.draw_no >= max(int(m.draw_no.min()), int(first)-history_window))]
    test_block_df = m[m.draw_no.isin(td)]

    predictions=[]; rulebooks=[]; char_rows=[]
    char_cache={}

    for d,g in test_block_df.groupby("draw_no", sort=True):
        sig=_v54_character_signature(g.iloc[0])
        if sig not in char_cache:
            pool,level=_v54_character_pool(train,sig)
            rules=_v54_learn_role_rules(pool)
            char_cache[sig]=(rules,level,len(pool),pool.date.nunique() if len(pool) else 0)
        rules,level,pool_n,pool_days=char_cache[sig]

        pp=_v54_apply_roles(g,rules)
        pp["character_regime"]=sig[0]
        pp["character_phase"]=sig[1]
        pp["character_zone800"]=sig[2]
        pp["character_osc800"]=sig[3]
        pp["match_level"]=level
        pp["character_history_rows"]=pool_n
        pp["character_history_days"]=pool_days
        pp["wf_block"]=block_info["block"]
        predictions.append(pp)

        char_rows.append({
            "wf_block":block_info["block"],"draw_no":d,"date":g.date.iloc[0],"time":g.time.iloc[0],
            "pre_regime":sig[0],"phase":sig[1],"zone800":sig[2],"osc800":sig[3],
            "match_level":level,"history_rows":pool_n,"history_days":pool_days,
            "rules":len(rules),
            "selectors":int((rules.role=="SELECTOR").sum()) if len(rules) else 0,
            "vetos":int((rules.role=="VETO").sum()) if len(rules) else 0
        })

    for sig,(rules,level,pool_n,pool_days) in char_cache.items():
        if len(rules):
            rr=rules.copy()
            rr["wf_block"]=block_info["block"]
            rr["pre_regime"],rr["phase"],rr["zone800"],rr["osc800"]=sig
            rr["match_level"]=level
            rr["history_rows"]=pool_n
            rr["history_days"]=pool_days
            rulebooks.append(rr)

    P=pd.concat(predictions,ignore_index=True) if predictions else pd.DataFrame()
    R=pd.concat(rulebooks,ignore_index=True) if rulebooks else pd.DataFrame()
    C=pd.DataFrame(char_rows)
    B=pd.DataFrame([block_info])

    rep=_v54_reports(P,C)

    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_BLOCK_INFO.csv",B.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("01_CHARACTER_MATCH_AUDIT.csv",C.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("02_FROZEN_CHARACTER_ROLE_RULEBOOK.csv",R.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("03_OOS_NUMBER_ROLE_PREDICTIONS.csv",P.to_csv(index=False).encode("utf-8-sig"))
        for fn,t in rep.items():
            z.writestr("04_REPORTS/"+fn,t.to_csv(index=False).encode("utf-8-sig"))
    return bio.getvalue(), P, R, C, rep

def _v55_merge_blocks(plan):
    Ps=[]; Rs=[]; Cs=[]; Bs=[]
    for info in plan:
        fp=_v55_block_path(info["block"])
        if not _v55_is_valid_zip(fp):
            raise RuntimeError(f"Blok eksik/bozuk: {info['block']}")
        with zipfile.ZipFile(fp,"r") as z:
            Bs.append(pd.read_csv(z.open("00_BLOCK_INFO.csv")))
            Cs.append(pd.read_csv(z.open("01_CHARACTER_MATCH_AUDIT.csv")))
            try:
                r=pd.read_csv(z.open("02_FROZEN_CHARACTER_ROLE_RULEBOOK.csv"))
                Rs.append(r)
            except Exception:
                pass
            Ps.append(pd.read_csv(z.open("03_OOS_NUMBER_ROLE_PREDICTIONS.csv")))

    P=pd.concat(Ps,ignore_index=True) if Ps else pd.DataFrame()
    R=pd.concat(Rs,ignore_index=True) if Rs else pd.DataFrame()
    C=pd.concat(Cs,ignore_index=True) if Cs else pd.DataFrame()
    B=pd.concat(Bs,ignore_index=True) if Bs else pd.DataFrame()
    rep=_v54_reports(P,C)
    return _v54_zip(P,R,B,C,rep)


# ---------------- V5.6 KALICI ANA MATRİS ----------------
_V56_MATRIX_DIR = Path(".hizli_on_v56_matrix_cache")
_V56_MATRIX_DIR.mkdir(parents=True, exist_ok=True)

def _v56_data_fingerprint(df):
    # veri değişince eski matris otomatik geçersizleşir
    txt = serialize_master_txt(df).encode("utf-8")
    return hashlib.sha256(txt).hexdigest()[:16]

def _v56_matrix_path(df):
    return _V56_MATRIX_DIR / f"matrix_{_v56_data_fingerprint(df)}.pkl"

def _v56_matrix_meta_path(df):
    return _V56_MATRIX_DIR / f"matrix_{_v56_data_fingerprint(df)}.meta.txt"

def _v56_matrix_ready(df):
    p = _v56_matrix_path(df)
    if not p.exists() or p.stat().st_size == 0:
        return False
    try:
        m = pd.read_pickle(p)
        required = {"draw_no","date","time","number","actual","pre_regime"}
        return (not m.empty) and required.issubset(set(m.columns))
    except Exception:
        return False

def _v56_load_matrix(df):
    if not _v56_matrix_ready(df):
        raise RuntimeError("Kalıcı 80→20 matrisi hazır değil.")
    return pd.read_pickle(_v56_matrix_path(df))

def _v56_build_and_save_matrix(df):
    m = _v52_build_matrix(df)
    if m.empty:
        raise RuntimeError("80→20 matrisi boş üretildi.")
    tmp = Path(str(_v56_matrix_path(df)) + ".tmp")
    pd.to_pickle(m, tmp)
    # tekrar okuyarak doğrula
    chk = pd.read_pickle(tmp)
    if len(chk) != len(m) or chk.shape[1] != m.shape[1]:
        raise IOError("Kalıcı matris doğrulaması başarısız.")
    tmp.replace(_v56_matrix_path(df))
    _v56_matrix_meta_path(df).write_text(
        f"fingerprint={_v56_data_fingerprint(df)}\n"
        f"rows={len(m)}\n"
        f"cols={m.shape[1]}\n"
        f"draws={m.draw_no.nunique()}\n"
        f"days={m.date.nunique()}\n",
        encoding="utf-8"
    )
    return m

def _v56_clear_old_matrices_keep_current(df):
    current = _v56_matrix_path(df).name
    current_meta = _v56_matrix_meta_path(df).name
    for p in _V56_MATRIX_DIR.glob("*"):
        if p.name not in {current, current_meta}:
            try: p.unlink()
            except Exception: pass
# ---------------- /V5.6 KALICI ANA MATRİS ----------------

st.divider()
st.header("🧱 V5.6 CHARACTER-FIRST — KALICI MATRİS + PARÇALI WALK-FORWARD")

st.caption("Ana 80→20 matrisi artık bir kez hazırlanır ve diske kalıcı kaydedilir. Sonraki açılışlarda tekrar hesaplanmaz. Veri değişirse fingerprint değişir ve yeni matris istenir.")

_v56_ready = _v56_matrix_ready(df)

if not _v56_ready:
    st.warning("Ana 80→20 matrisi henüz kalıcı olarak hazır değil.")
    if st.button("🧱 ANA 80→20 MATRİSİNİ BİR KEZ HAZIRLA", use_container_width=True,
                 type="primary", key="v56_build_matrix"):
        _ms = st.status("80→20 PRE-H ana matrisi hazırlanıyor ve kalıcı kaydediliyor…", expanded=True)
        try:
            _m = _v56_build_and_save_matrix(df)
            _v56_clear_old_matrices_keep_current(df)
            _ms.write(f"Matris: {len(_m):,} kayıt × {_m.shape[1]} sütun")
            _ms.write(f"Çekiliş: {_m.draw_no.nunique():,} | Gün: {_m.date.nunique()}")
            _ms.update(label="✅ Ana matris kalıcı kaydedildi", state="complete", expanded=False)
            st.rerun()
        except Exception as _e:
            _ms.update(label="❌ Ana matris hazırlanamadı", state="error", expanded=True)
            st.exception(_e)
    st.info("Ana matris hazır olmadan walk-forward blokları başlamaz.")
    st.stop()

_v55_matrix = _v56_load_matrix(df)
st.success(f"✅ Kalıcı ana matris hazır: {len(_v55_matrix):,} kayıt. Yeniden hesaplanmıyor.")
_v55_plan=_v55_block_plan(_v55_matrix,warmup_draws=900,test_block=120)
_v55_done=_v55_saved_blocks(_v55_plan)
_v55_n=len(_v55_done)

st.progress(_v55_n/len(_v55_plan) if _v55_plan else 0.0,
            text=f"V5.6 blok ilerleme: {_v55_n}/{len(_v55_plan)}")

if _v55_done:
    st.write("Hazır bloklar:", " • ".join(str(k) for k in sorted(_v55_done)))

c55a,c55b=st.columns(2)
with c55a:
    if st.button("▶️ SONRAKİ BLOĞU HESAPLA",
                 use_container_width=True,type="primary",key="v55_next",
                 disabled=(_v55_n>=len(_v55_plan))):
        _next=next(p for p in _v55_plan if p["block"] not in _v55_done)
        _status=st.status(
            f"Blok {_next['block']}/{len(_v55_plan)} — {_next['test_from']}→{_next['test_to']} hesaplanıyor…",
            expanded=True
        )
        try:
            _bytes,_P,_R,_C,_rep=_v55_compute_one_block(_v55_matrix,_next,history_window=960)
            fp=_v55_block_path(_next["block"])
            fp.write_bytes(_bytes)
            if not _v55_is_valid_zip(fp):
                raise IOError("Blok ZIP yazıldı ama bütünlük kontrolünden geçmedi.")

            _summary=_rep.get("04_POLICY_SUMMARY.csv",pd.DataFrame())
            if not _summary.empty:
                st.write(_summary[["policy","predictions","hits","hit_rate","lift"]])
            _status.update(
                label=f"✅ Blok {_next['block']} tamamlandı ve kalıcı kaydedildi",
                state="complete",expanded=False
            )
            st.rerun()
        except Exception as _e:
            _status.update(label=f"❌ Blok {_next['block']} hata verdi",state="error",expanded=True)
            st.exception(_e)

with c55b:
    if st.button("♻️ V5.5 BLOKLARINI SIFIRLA",use_container_width=True,key="v55_reset"):
        for fp in _V55_CACHE.glob("block_*.zip"):
            try: fp.unlink()
            except Exception: pass
        st.session_state.pop("v55_final_zip",None)
        st.rerun()

_v55_done=_v55_saved_blocks(_v55_plan)
if _v55_n < len(_v55_plan):
    # Son hazır bloğu ayrı indirebilme: güvenlik yedeği
    if _v55_done:
        _last=max(_v55_done)
        st.download_button(
            f"⬇️ SON HAZIR BLOĞU İNDİR — {_last}/{len(_v55_plan)}",
            _v55_done[_last].read_bytes(),
            f"HIZLI_ON_V5_5_BLOCK_{_last:02d}.zip",
            "application/zip",use_container_width=True,key="v55_last_block_download"
        )

if len(_v55_done)==len(_v55_plan) and len(_v55_plan)>0:
    if "v55_final_zip" not in st.session_state:
        with st.spinner("18 blok tek sonuç ZIP'inde birleştiriliyor..."):
            st.session_state["v55_final_zip"]=_v55_merge_blocks(_v55_plan)
    st.success("✅ V5.6 18/18 tamamlandı. Tüm bloklar tek out-of-sample sonuç ZIP'inde birleştirildi.")
    st.download_button(
        "⬇️ V5.6 CHARACTER-FIRST KALICI MATRİS + PARÇALI WF — TEK ZIP",
        st.session_state["v55_final_zip"],
        "HIZLI_ON_V5_6_CHARACTER_FIRST_PERSISTENT_MATRIX_WF_RESULTS.zip",
        "application/zip",use_container_width=True,key="v55_final_download"
    )
# =====================================================================
# /V5.5
# =====================================================================



# =====================================================================
# V6.0 UZMAN DERİNLEŞTİRME LABORATUVARI
# UZMAN-01: ARDIŞIK BLOK PROFESÖRÜ
# Bu motor yalnız ardışık yapıların mikro yaşamını inceler.
# Sayı kimliği öğrenmez; PRE-H yapı/karakter/koridor/rol öğrenir.
# Q2 KORİDOR KAPANMA kuralı DONDURULMUŞ referans olarak korunur.
# Kupon üretimi YOK.
# =====================================================================

_V60_DIR = Path(".hizli_on_v60_ardisik")
_V60_DIR.mkdir(parents=True, exist_ok=True)

def _v60_adj_state(S, a):
    # adjacent pair (a,a+1): 00 / 01 / 10 / 11
    return f"{int(a in S)}{int((a+1) in S)}"

def _v60_pair_corridor_silent(hist_sets, a):
    # Q2: dış ±2 koridor, H-3..H-1 boyunca sessiz.
    # Pair a,a+1; outer corridor: a-2,a-1,a+2,a+3
    corridor={n for n in (a-2,a-1,a+2,a+3) if 1<=n<=80}
    return all(len(S & corridor)==0 for S in hist_sets)

def _v60_same_pair_seen_full_same_day(x, i, a):
    d=x.iloc[i].date
    for j in range(i-1,-1,-1):
        if x.iloc[j].date != d:
            break
        S=x.iloc[j].numset
        if a in S and (a+1) in S:
            return True
    return False

def _v60_block_role(block, n):
    if len(block)==1: return "SINGLE"
    if n==block[0]: return "LEFT"
    if n==block[-1]: return "RIGHT"
    if len(block)%2==1 and n==block[len(block)//2]: return "MIDDLE"
    return "INNER"

def _v60_block_map(S):
    mp={}
    for b in _v51_blocks(S):
        for n in b:
            mp[n]=b
    return mp

def _v60_overlap_relation(pb, cb):
    A=set(pb); B=set(cb)
    inter=len(A&B)
    if inter==0: return None
    if A==B: return "SAME"
    if A < B: return "GROW"
    if B < A: return "SHRINK"
    if len(A)==len(B):
        delta=min(B)-min(A)
        if delta==-2:return "SHIFT_LEFT_2"
        if delta==-1:return "SHIFT_LEFT_1"
        if delta==1:return "SHIFT_RIGHT_1"
        if delta==2:return "SHIFT_RIGHT_2"
    return "MORPH"

def _v60_build_micro_events(df):
    x=_v51_x(df)
    char=_v51_character_rows(x).set_index("idx")
    rows=[]
    pair_rows=[]
    number_rows=[]

    for i in range(3,len(x)):
        H=x.iloc[i].numset
        H1=x.iloc[i-1].numset
        H2=x.iloc[i-2].numset
        H3=x.iloc[i-3].numset
        pb=_v51_blocks(H1)
        cb=_v51_blocks(H)
        reg=char.loc[i,"pre_regime"] if i in char.index else "NA"
        phase=_v51_phase(x.iloc[i].time)

        # block-level lifecycle
        matched_current=set()
        for b in pb:
            relations=[]
            for c in cb:
                rel=_v60_overlap_relation(b,c)
                if rel:
                    relations.append((rel,c))
            if not relations:
                rows.append({
                    "draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                    "pre_regime":reg,"phase":phase,
                    "pre_block":"-".join(map(str,b)),"pre_len":len(b),
                    "event":"DEATH","target_block":"","target_len":0,
                    "overlap":0,"pre_total_blocks":len(pb),"target_total_blocks":len(cb),
                    "H1_sum":int(x.iloc[i-1].sum20),"zone800":_v51_zone800(x.iloc[i-1].sum20),
                    "osc800":_v51_osc800(x.iloc[i-1].sum20,x.iloc[i-2].sum20)
                })
            else:
                # strongest structural relation
                priority={"SAME":9,"GROW":8,"SHRINK":7,"SHIFT_RIGHT_1":6,"SHIFT_LEFT_1":6,
                          "SHIFT_RIGHT_2":5,"SHIFT_LEFT_2":5,"MORPH":4}
                rel,c=max(relations,key=lambda t:priority.get(t[0],0))
                matched_current.add(c)
                rows.append({
                    "draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                    "pre_regime":reg,"phase":phase,
                    "pre_block":"-".join(map(str,b)),"pre_len":len(b),
                    "event":rel,"target_block":"-".join(map(str,c)),"target_len":len(c),
                    "overlap":len(set(b)&set(c)),"pre_total_blocks":len(pb),"target_total_blocks":len(cb),
                    "H1_sum":int(x.iloc[i-1].sum20),"zone800":_v51_zone800(x.iloc[i-1].sum20),
                    "osc800":_v51_osc800(x.iloc[i-1].sum20,x.iloc[i-2].sum20)
                })
        for c in cb:
            if c not in matched_current:
                rows.append({
                    "draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                    "pre_regime":reg,"phase":phase,
                    "pre_block":"","pre_len":0,"event":"BIRTH",
                    "target_block":"-".join(map(str,c)),"target_len":len(c),
                    "overlap":0,"pre_total_blocks":len(pb),"target_total_blocks":len(cb),
                    "H1_sum":int(x.iloc[i-1].sum20),"zone800":_v51_zone800(x.iloc[i-1].sum20),
                    "osc800":_v51_osc800(x.iloc[i-1].sum20,x.iloc[i-2].sum20)
                })

        # every adjacent pair state-transition; includes frozen Q2 gate
        for a in range(1,80):
            s3=_v60_adj_state(H3,a); s2=_v60_adj_state(H2,a); s1=_v60_adj_state(H1,a)
            sh=_v60_adj_state(H,a)
            corridor_silent=_v60_pair_corridor_silent([H3,H2,H1],a)
            seen_full=_v60_same_pair_seen_full_same_day(x,i,a)
            q2_gate=int(s2=="00" and s1 in ("01","10") and corridor_silent and not seen_full)
            pair_rows.append({
                "draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                "pre_regime":reg,"phase":phase,"pair":f"{a}-{a+1}",
                "H3_state":s3,"H2_state":s2,"H1_state":s1,"H_state":sh,
                "target_full11":int(sh=="11"),
                "corridor_silent_H3_H1":int(corridor_silent),
                "same_pair_seen_11_same_day":int(seen_full),
                "Q2_GATE_FROZEN":q2_gate,
                "Q2_HIT":int(q2_gate and sh=="11"),
                "H1_sum":int(x.iloc[i-1].sum20),
                "zone800":_v51_zone800(x.iloc[i-1].sum20),
                "osc800":_v51_osc800(x.iloc[i-1].sum20,x.iloc[i-2].sum20),
                "pre_total_blocks":len(pb)
            })

        # number-level role inside consecutive geometry: REAL20 vs NEG60
        bmap=_v60_block_map(H1)
        for n in range(1,81):
            b=bmap.get(n)
            number_rows.append({
                "draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                "number":n,"actual":int(n in H),"pre_regime":reg,"phase":phase,
                "in_pre_block":int(b is not None),
                "pre_block_len":len(b) if b else 0,
                "pre_block_role":_v60_block_role(b,n) if b else "OUTSIDE",
                "left_neighbor_H1":int(n>1 and n-1 in H1),
                "right_neighbor_H1":int(n<80 and n+1 in H1),
                "left2_H1":int(n>2 and n-2 in H1),
                "right2_H1":int(n<79 and n+2 in H1),
                "block_shift_candidate":_v52_block_shift_support(H1,n),
                "H1_sum":int(x.iloc[i-1].sum20),
                "zone800":_v51_zone800(x.iloc[i-1].sum20),
                "osc800":_v51_osc800(x.iloc[i-1].sum20,x.iloc[i-2].sum20),
                "pre_total_blocks":len(pb)
            })

    return pd.DataFrame(rows),pd.DataFrame(pair_rows),pd.DataFrame(number_rows)

def _v60_q2_report(pair_df):
    q=pair_df[pair_df.Q2_GATE_FROZEN==1].copy()
    if q.empty:return pd.DataFrame()
    day=q.groupby("date").Q2_HIT.agg(["count","sum","mean"]).reset_index()
    day.columns=["date","signals","hits","hit_rate"]
    return day

def _v60_micro_summary(block_df):
    if block_df.empty:return pd.DataFrame()
    return (block_df.groupby(["pre_regime","phase","pre_len","event"],dropna=False)
            .agg(events=("draw_no","count"),
                 target_len_mean=("target_len","mean"),
                 target_blocks_mean=("target_total_blocks","mean"))
            .reset_index())

def _v60_number_separation(number_df):
    if number_df.empty:return pd.DataFrame()
    keys=["pre_regime","phase","pre_block_len","pre_block_role","block_shift_candidate","zone800","osc800"]
    out=[]
    for f in keys:
        for v,g in number_df.groupby(f,dropna=False):
            if len(g)<80:continue
            rate=float(g.actual.mean())
            out.append({"feature":f,"value":str(v),"tests":len(g),"hits":int(g.actual.sum()),
                        "hit_rate":rate,"base_rate":0.25,"lift":rate/0.25,"effect":rate-0.25})
    a=pd.DataFrame(out)
    if not a.empty:a=a.sort_values("effect",key=lambda x:x.abs(),ascending=False)
    return a

def _v60_walkforward_pair_rules(pair_df):
    # Pair-state rules learned only from past blocks; exact frozen Q2 reported separately.
    draws=sorted(pair_df.draw_no.unique())
    rows=[]; block_size=120; warmup=900
    for pos in range(warmup,len(draws),block_size):
        td=draws[pos:min(pos+block_size,len(draws))]
        if not td:break
        first=td[0]
        tr=pair_df[pair_df.draw_no<first]
        te=pair_df[pair_df.draw_no.isin(td)]
        fields=["H3_state","H2_state","H1_state","corridor_silent_H3_H1",
                "same_pair_seen_11_same_day","pre_total_blocks","zone800","osc800","pre_regime","phase"]
        candidates=[]
        for f in fields:
            gg=tr.groupby(f,dropna=False).target_full11.agg(["count","sum","mean"]).reset_index()
            for _,r in gg[gg["count"]>=160].iterrows():
                candidates.append((f,str(r[f]),int(r["count"]),float(r["mean"])))
        for f1,f2 in combinations(fields,2):
            gg=tr.groupby([f1,f2],dropna=False,observed=True).target_full11.agg(["count","sum","mean"]).reset_index()
            for _,r in gg[gg["count"]>=160].iterrows():
                candidates.append((f"{f1}+{f2}",f"{r[f1]}|{r[f2]}",int(r["count"]),float(r["mean"])))
        # only structurally elevated or suppressed
        candidates=[c for c in candidates if c[3]>=0.12 or c[3]<=0.03]
        for name,val,n,train_rate in candidates:
            if "+" in name:
                f1,f2=name.split("+",1); v1,v2=val.split("|",1)
                g=te[(te[f1].astype(str)==v1)&(te[f2].astype(str)==v2)]
            else:
                g=te[te[name].astype(str)==val]
            if len(g)<30:continue
            rows.append({
                "test_from":td[0],"test_to":td[-1],"rule":name,"value":val,
                "train_tests":n,"train_rate":train_rate,
                "blind_tests":len(g),"blind_hits":int(g.target_full11.sum()),
                "blind_rate":float(g.target_full11.mean())
            })
    return pd.DataFrame(rows)

def _v60_make_zip(df):
    block,pair,num=_v60_build_micro_events(df)
    q2=_v60_q2_report(pair)
    micro=_v60_micro_summary(block)
    sep=_v60_number_separation(num)
    wf=_v60_walkforward_pair_rules(pair)

    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_MANIFEST.txt",
            "V6.0 UZMAN-01 ARDISIK BLOK PROFESORU\n"
            "PRE-H -> POST-H ayrimi zorunlu.\n"
            "Q2 KORIDOR KAPANMA kuralinin tanimi dondurulmustur; sonuca gore degistirilmez.\n"
            "Analizler: 1-6 blok rolleri, dogum/olum/buyume/kuculme, sag/sol kayma,\n"
            "pair 00/01/10/11 gecisleri, dis koridor sessizligi, ayni gece onceki 11,\n"
            "karakter/saat/800 kosullari, REAL20/NEG60 ayrimi ve gercek walk-forward.\n"
            "Kupon uretimi yoktur.\n")
        for fn,t in {
            "01_BLOCK_MICRO_LIFECYCLE.csv":block,
            "02_PAIR_STATE_TRANSITIONS.csv":pair,
            "03_NUMBER_BLOCK_ROLES_80_TO_20.csv":num,
            "04_BLOCK_CHARACTER_SUMMARY.csv":micro,
            "05_Q2_FROZEN_DAY_REPORT.csv":q2,
            "06_NUMBER_REAL20_NEG60_SEPARATION.csv":sep,
            "07_PAIR_RULE_TRUE_WALK_FORWARD.csv":wf,
        }.items():
            z.writestr(fn,t.to_csv(index=False).encode("utf-8-sig"))
    return bio.getvalue()

st.divider()
st.header("🎓 V6.0 UZMAN-01 — ARDIŞIK BLOK PROFESÖRÜ")
st.caption("İlk kanalı profesör seviyesine indiriyoruz: blok yaşamı + mikro rol + koridor + 00/01/10/11 + karakter + 80→20 ayrımı + gerçek walk-forward.")

if st.button("▶️ UZMAN-01 ARDIŞIK PROFESÖRÜ ÇALIŞTIR",
             use_container_width=True,type="primary",key="v60_ard_run",
             disabled=(_V60_DIR/"UZMAN01.zip").exists()):
    _u=st.status("Ardışık Profesörü çalışıyor…",expanded=True)
    try:
        _u.write("1/5 — blok mikro yaşamı çıkarılıyor…")
        _u.write("2/5 — 79 komşu ikilinin 00/01/10/11 yolları çıkarılıyor…")
        _u.write("3/5 — Q2 dondurulmuş koridor kuralı aynen ölçülüyor…")
        _u.write("4/5 — 80 sayı blok rolleri REAL20/NEG60 ayrımında inceleniyor…")
        _u.write("5/5 — pair-state kuralları gerçek walk-forward test ediliyor…")
        _b=_v60_make_zip(df)
        (_V60_DIR/"UZMAN01.zip").write_bytes(_b)
        _u.update(label="✅ UZMAN-01 Ardışık Profesörü tamamlandı",state="complete",expanded=False)
        st.rerun()
    except Exception as _e:
        _u.update(label="❌ UZMAN-01 hata verdi",state="error",expanded=True)
        st.exception(_e)

if (_V60_DIR/"UZMAN01.zip").exists():
    st.download_button("⬇️ UZMAN-01 ARDIŞIK PROFESÖRÜ — TEK ZIP",
        (_V60_DIR/"UZMAN01.zip").read_bytes(),
        "HIZLI_ON_V6_0_UZMAN01_ARDISIK_PROFESORU.zip",
        "application/zip",use_container_width=True,key="v60_ard_download")
# =====================================================================
# /V6.0
# =====================================================================



# =====================================================================
# V6.1 UZMAN-01 ARDIŞIK PROFESÖRÜ — PARÇALI / KALICI / DERİN
# Amaç: ardışık yapıyı "tek olay" değil, yaşam zinciri olarak okumak.
# Her gün ayrı mikro veri üretir, kalıcı kaydeder; sonra gerçek walk-forward
# bloklarını ayrı ayrı çalıştırır. Sonuçlar tamamlanınca TEK ZIP verir.
# Kupon üretimi YOK.
# =====================================================================

_V61_DIR = Path(".hizli_on_v61_ardisik")
_V61_DAY_DIR = _V61_DIR / "days"
_V61_WF_DIR = _V61_DIR / "wf"
_V61_DAY_DIR.mkdir(parents=True, exist_ok=True)
_V61_WF_DIR.mkdir(parents=True, exist_ok=True)

def _v61_day_path(d):
    return _V61_DAY_DIR / f"{str(d).replace('.','_')}.zip"

def _v61_wf_path(k):
    return _V61_WF_DIR / f"wf_{int(k):02d}.zip"

def _v61_valid_zip(p):
    try:
        if not p.exists() or p.stat().st_size == 0: return False
        with zipfile.ZipFile(p, "r") as z:
            return z.testzip() is None
    except Exception:
        return False

def _v61_block_state_signature(S):
    bl=_v51_blocks(S)
    lens=sorted((len(b) for b in bl), reverse=True)
    return f"B{len(bl)}_L" + "-".join(map(str,lens[:6]))

def _v61_block_chain_features(x, i):
    H1=x.iloc[i-1].numset
    H2=x.iloc[i-2].numset
    H3=x.iloc[i-3].numset
    b1=_v51_blocks(H1); b2=_v51_blocks(H2); b3=_v51_blocks(H3)

    return {
        "H3_shape":_v61_block_state_signature(H3),
        "H2_shape":_v61_block_state_signature(H2),
        "H1_shape":_v61_block_state_signature(H1),
        "H3_block_count":len(b3),
        "H2_block_count":len(b2),
        "H1_block_count":len(b1),
        "H3_max_len":max([len(b) for b in b3], default=0),
        "H2_max_len":max([len(b) for b in b2], default=0),
        "H1_max_len":max([len(b) for b in b1], default=0),
        "block_count_delta_32":len(b2)-len(b3),
        "block_count_delta_21":len(b1)-len(b2),
        "max_len_delta_32":max([len(b) for b in b2], default=0)-max([len(b) for b in b3], default=0),
        "max_len_delta_21":max([len(b) for b in b1], default=0)-max([len(b) for b in b2], default=0),
    }

def _v61_build_one_day(df, day):
    x=_v51_x(df)
    idxs=x.index[x.date.astype(str)==str(day)].tolist()
    if not idxs:
        raise RuntimeError(f"{day}: veri yok.")
    rows=[]; pair_rows=[]; number_rows=[]; chain_rows=[]
    char=_v51_character_rows(x).set_index("idx")

    for i in idxs:
        if i < 3: 
            continue
        H=x.iloc[i].numset; H1=x.iloc[i-1].numset; H2=x.iloc[i-2].numset; H3=x.iloc[i-3].numset
        pb=_v51_blocks(H1); cb=_v51_blocks(H)
        reg=char.loc[i,"pre_regime"] if i in char.index else "NA"
        phase=_v51_phase(x.iloc[i].time)
        chain=_v61_block_chain_features(x,i)

        # H3→H2→H1 shape chain, sonuç yalnız POST etiketi.
        chain_rows.append({
            "draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
            "pre_regime":reg,"phase":phase,**chain,
            "H_block_count":len(cb),"H_max_len":max([len(b) for b in cb],default=0),
            "H_shape":_v61_block_state_signature(H)
        })

        matched_current=set()
        for b in pb:
            relations=[]
            for c in cb:
                rel=_v60_overlap_relation(b,c)
                if rel: relations.append((rel,c))
            if not relations:
                rel="DEATH"; c=tuple()
            else:
                priority={"SAME":9,"GROW":8,"SHRINK":7,"SHIFT_RIGHT_1":6,"SHIFT_LEFT_1":6,
                          "SHIFT_RIGHT_2":5,"SHIFT_LEFT_2":5,"MORPH":4}
                rel,c=max(relations,key=lambda t:priority.get(t[0],0))
                matched_current.add(c)
            rows.append({
                "draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                "pre_regime":reg,"phase":phase,
                "pre_block":"-".join(map(str,b)),"pre_len":len(b),
                "event":rel,"target_block":"-".join(map(str,c)) if c else "",
                "target_len":len(c) if c else 0,
                "overlap":len(set(b)&set(c)) if c else 0,
                "pre_total_blocks":len(pb),"target_total_blocks":len(cb),
                "H1_sum":int(x.iloc[i-1].sum20),"zone800":_v51_zone800(x.iloc[i-1].sum20),
                "osc800":_v51_osc800(x.iloc[i-1].sum20,x.iloc[i-2].sum20),
                **chain
            })
        for c in cb:
            if c not in matched_current:
                rows.append({
                    "draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                    "pre_regime":reg,"phase":phase,"pre_block":"","pre_len":0,"event":"BIRTH",
                    "target_block":"-".join(map(str,c)),"target_len":len(c),"overlap":0,
                    "pre_total_blocks":len(pb),"target_total_blocks":len(cb),
                    "H1_sum":int(x.iloc[i-1].sum20),"zone800":_v51_zone800(x.iloc[i-1].sum20),
                    "osc800":_v51_osc800(x.iloc[i-1].sum20,x.iloc[i-2].sum20),
                    **chain
                })

        # 79 adjacent pairs with exact H3/H2/H1 state path + frozen Q2.
        for a in range(1,80):
            s3=_v60_adj_state(H3,a); s2=_v60_adj_state(H2,a); s1=_v60_adj_state(H1,a); sh=_v60_adj_state(H,a)
            corridor=_v60_pair_corridor_silent([H3,H2,H1],a)
            seen=_v60_same_pair_seen_full_same_day(x,i,a)
            q2=int(s2=="00" and s1 in ("01","10") and corridor and not seen)
            pair_rows.append({
                "draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                "pre_regime":reg,"phase":phase,"pair":f"{a}-{a+1}",
                "H3_state":s3,"H2_state":s2,"H1_state":s1,"H_state":sh,
                "state_path":f"{s3}>{s2}>{s1}",
                "target_full11":int(sh=="11"),
                "corridor_silent_H3_H1":int(corridor),
                "same_pair_seen_11_same_day":int(seen),
                "Q2_GATE_FROZEN":q2,"Q2_HIT":int(q2 and sh=="11"),
                "H1_sum":int(x.iloc[i-1].sum20),
                "zone800":_v51_zone800(x.iloc[i-1].sum20),
                "osc800":_v51_osc800(x.iloc[i-1].sum20,x.iloc[i-2].sum20),
                "pre_total_blocks":len(pb),**chain
            })

        # number roles: kenar/iç/komşu/shift hedefi; REAL20/NEG60.
        bmap=_v60_block_map(H1)
        for n in range(1,81):
            b=bmap.get(n)
            number_rows.append({
                "draw_no":int(x.iloc[i].draw_no),"date":x.iloc[i].date,"time":x.iloc[i].time,
                "number":n,"actual":int(n in H),"pre_regime":reg,"phase":phase,
                "in_pre_block":int(b is not None),
                "pre_block_len":len(b) if b else 0,
                "pre_block_role":_v60_block_role(b,n) if b else "OUTSIDE",
                "left_neighbor_H1":int(n>1 and n-1 in H1),
                "right_neighbor_H1":int(n<80 and n+1 in H1),
                "left2_H1":int(n>2 and n-2 in H1),
                "right2_H1":int(n<79 and n+2 in H1),
                "block_shift_candidate":_v52_block_shift_support(H1,n),
                "H1_sum":int(x.iloc[i-1].sum20),
                "zone800":_v51_zone800(x.iloc[i-1].sum20),
                "osc800":_v51_osc800(x.iloc[i-1].sum20,x.iloc[i-2].sum20),
                "pre_total_blocks":len(pb),**chain
            })

    return pd.DataFrame(rows),pd.DataFrame(pair_rows),pd.DataFrame(number_rows),pd.DataFrame(chain_rows)

def _v61_save_day(day, block, pair, num, chain):
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("01_BLOCK.csv",block.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("02_PAIR.csv",pair.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("03_NUMBER.csv",num.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("04_CHAIN.csv",chain.to_csv(index=False).encode("utf-8-sig"))
    p=_v61_day_path(day); p.write_bytes(bio.getvalue())
    if not _v61_valid_zip(p): raise IOError(f"{day}: günlük ZIP bozuk.")
    return p

def _v61_merge_days(days):
    bs=[];ps=[];ns=[];cs=[]
    for d in days:
        p=_v61_day_path(d)
        if not _v61_valid_zip(p): raise RuntimeError(f"Eksik gün: {d}")
        with zipfile.ZipFile(p,"r") as z:
            bs.append(pd.read_csv(z.open("01_BLOCK.csv")))
            ps.append(pd.read_csv(z.open("02_PAIR.csv")))
            ns.append(pd.read_csv(z.open("03_NUMBER.csv")))
            cs.append(pd.read_csv(z.open("04_CHAIN.csv")))
    return (pd.concat(bs,ignore_index=True),pd.concat(ps,ignore_index=True),
            pd.concat(ns,ignore_index=True),pd.concat(cs,ignore_index=True))

def _v61_wf_plan(pair_df,warmup=900,block=120):
    draws=sorted(pair_df.draw_no.unique())
    out=[];k=1
    for pos in range(warmup,len(draws),block):
        td=draws[pos:min(pos+block,len(draws))]
        if td:
            out.append({"block":k,"from":int(td[0]),"to":int(td[-1]),"n_draws":len(td)})
            k+=1
    return out

def _v61_learn_pair_rules(tr):
    fields=["state_path","H2_state","H1_state","corridor_silent_H3_H1",
            "same_pair_seen_11_same_day","pre_total_blocks","zone800","osc800",
            "pre_regime","phase","H1_shape","H2_shape","block_count_delta_21","max_len_delta_21"]
    rows=[]
    for f in fields:
        gg=tr.groupby(f,dropna=False).target_full11.agg(["count","sum","mean"]).reset_index()
        for _,r in gg[gg["count"]>=180].iterrows():
            rate=float(r["mean"])
            if rate>=0.12 or rate<=0.03:
                rows.append({"kind":"SINGLE","f1":f,"v1":str(r[f]),"f2":"","v2":"",
                             "train_tests":int(r["count"]),"train_rate":rate})
    for a in range(len(fields)):
        for b in range(a+1,len(fields)):
            f1,f2=fields[a],fields[b]
            gg=tr.groupby([f1,f2],dropna=False,observed=True).target_full11.agg(["count","sum","mean"]).reset_index()
            for _,r in gg[gg["count"]>=180].iterrows():
                rate=float(r["mean"])
                if rate>=0.12 or rate<=0.03:
                    rows.append({"kind":"PAIR","f1":f1,"v1":str(r[f1]),"f2":f2,"v2":str(r[f2]),
                                 "train_tests":int(r["count"]),"train_rate":rate})
    return pd.DataFrame(rows)

def _v61_run_one_wf(pair_df, info):
    tr=pair_df[pair_df.draw_no<info["from"]]
    te=pair_df[(pair_df.draw_no>=info["from"])&(pair_df.draw_no<=info["to"])]
    rules=_v61_learn_pair_rules(tr)
    rows=[]
    for _,r in rules.iterrows():
        m=(te[r.f1].astype(str)==str(r.v1))
        if r.kind=="PAIR":
            m &= (te[r.f2].astype(str)==str(r.v2))
        g=te[m]
        if len(g)<30: continue
        rows.append({"wf_block":info["block"],"test_from":info["from"],"test_to":info["to"],
                     "kind":r.kind,"f1":r.f1,"v1":r.v1,"f2":r.f2,"v2":r.v2,
                     "train_tests":r.train_tests,"train_rate":r.train_rate,
                     "blind_tests":len(g),"blind_hits":int(g.target_full11.sum()),
                     "blind_rate":float(g.target_full11.mean())})
    res=pd.DataFrame(rows)
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("01_RULES.csv",rules.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("02_BLIND.csv",res.to_csv(index=False).encode("utf-8-sig"))
    p=_v61_wf_path(info["block"]);p.write_bytes(bio.getvalue())
    if not _v61_valid_zip(p):raise IOError("WF ZIP bozuk.")
    return res

def _v61_merge_wf(plan):
    arr=[]
    for info in plan:
        p=_v61_wf_path(info["block"])
        if not _v61_valid_zip(p):raise RuntimeError(f"WF blok eksik: {info['block']}")
        with zipfile.ZipFile(p,"r") as z:
            try: arr.append(pd.read_csv(z.open("02_BLIND.csv")))
            except Exception: pass
    return pd.concat(arr,ignore_index=True) if arr else pd.DataFrame()

def _v61_final_zip(df,days):
    block,pair,num,chain=_v61_merge_days(days)
    q2=_v60_q2_report(pair)
    micro=_v60_micro_summary(block)
    sep=_v60_number_separation(num)
    plan=_v61_wf_plan(pair)
    wf=_v61_merge_wf(plan)

    # Deep chain summaries
    chain_sum=(chain.groupby(["pre_regime","phase","H3_shape","H2_shape","H1_shape"],dropna=False)
               .agg(events=("draw_no","count"),H_block_mean=("H_block_count","mean"),
                    H_max_len_mean=("H_max_len","mean")).reset_index())

    # Q2 + pair-state day/hour view
    pair_char=(pair.groupby(["pre_regime","phase","state_path","corridor_silent_H3_H1"],dropna=False)
               .target_full11.agg(["count","sum","mean"]).reset_index()
               .rename(columns={"count":"tests","sum":"hits","mean":"hit_rate"}))

    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_MANIFEST.txt",
            "V6.1 UZMAN-01 ARDISIK PROFESORU — PARCALI/KALICI/DERIN\n"
            "Blok yasami H3->H2->H1 zinciriyle okunur; sonuc sadece POST etikettir.\n"
            "Q2 dondurulmus kural aynen korunur.\n"
            "Gercek walk-forward bloklari test sonucuna gore yeniden ayarlanmaz.\n"
            "Kupon yok.\n")
        for fn,t in {
            "01_BLOCK_MICRO_LIFECYCLE.csv":block,
            "02_PAIR_STATE_TRANSITIONS.csv":pair,
            "03_NUMBER_BLOCK_ROLES_80_TO_20.csv":num,
            "04_SHAPE_CHAIN_H3_H2_H1.csv":chain,
            "05_SHAPE_CHAIN_SUMMARY.csv":chain_sum,
            "06_BLOCK_CHARACTER_SUMMARY.csv":micro,
            "07_Q2_FROZEN_DAY_REPORT.csv":q2,
            "08_NUMBER_REAL20_NEG60_SEPARATION.csv":sep,
            "09_PAIR_CHARACTER_STATE_SUMMARY.csv":pair_char,
            "10_PAIR_RULE_TRUE_WALK_FORWARD.csv":wf,
        }.items():
            z.writestr(fn,t.to_csv(index=False).encode("utf-8-sig"))
    return bio.getvalue(),plan

st.divider()
st.header("🎓 V6.1 UZMAN-01 — ARDIŞIK PROFESÖRÜ / PARÇALI-KALICI")
st.caption("Aynı uzmanlık korunur ama işlem artık gün gün ve walk-forward blok blok kalıcı ilerler. H3→H2→H1 şekil zinciri de eklendi.")

_v61_days=sorted(df.date.astype(str).dropna().unique().tolist(),
                 key=lambda d: pd.to_datetime(d,dayfirst=True,errors="coerce"))
_v61_day_done={d:_v61_day_path(d) for d in _v61_days if _v61_valid_zip(_v61_day_path(d))}
st.progress(len(_v61_day_done)/len(_v61_days) if _v61_days else 0.0,
            text=f"Mikro günler: {len(_v61_day_done)}/{len(_v61_days)}")

if len(_v61_day_done)<len(_v61_days):
    if st.button("▶️ SONRAKİ GÜNÜ MİKRO ANALİZ ET",use_container_width=True,type="primary",key="v61_day_next"):
        d=next(d for d in _v61_days if d not in _v61_day_done)
        _st=st.status(f"{d} ardışık mikro yaşamı çıkarılıyor…",expanded=True)
        try:
            b,p,n,c=_v61_build_one_day(df,d)
            _v61_save_day(d,b,p,n,c)
            _st.update(label=f"✅ {d} kalıcı kaydedildi",state="complete",expanded=False)
            st.rerun()
        except Exception as e:
            _st.update(label=f"❌ {d} hata verdi",state="error",expanded=True)
            st.exception(e)

if len(_v61_day_done)==len(_v61_days) and _v61_days:
    block61,pair61,num61,chain61=_v61_merge_days(_v61_days)
    plan61=_v61_wf_plan(pair61)
    donewf={p["block"]:_v61_wf_path(p["block"]) for p in plan61 if _v61_valid_zip(_v61_wf_path(p["block"]))}
    st.success("✅ Tüm günlük mikro yaşam verileri hazır.")
    st.progress(len(donewf)/len(plan61) if plan61 else 1.0,
                text=f"Gerçek walk-forward: {len(donewf)}/{len(plan61)} blok")
    if len(donewf)<len(plan61):
        if st.button("🧪 SONRAKİ WALK-FORWARD BLOĞUNU TEST ET",use_container_width=True,type="primary",key="v61_wf_next"):
            info=next(p for p in plan61 if p["block"] not in donewf)
            _st=st.status(f"WF blok {info['block']}/{len(plan61)} test ediliyor…",expanded=True)
            try:
                rr=_v61_run_one_wf(pair61,info)
                if not rr.empty:
                    st.write(rr.head(20))
                _st.update(label=f"✅ WF blok {info['block']} kalıcı kaydedildi",state="complete",expanded=False)
                st.rerun()
            except Exception as e:
                _st.update(label=f"❌ WF blok {info['block']} hata verdi",state="error",expanded=True)
                st.exception(e)

    donewf={p["block"]:_v61_wf_path(p["block"]) for p in plan61 if _v61_valid_zip(_v61_wf_path(p["block"]))}
    if len(donewf)==len(plan61):
        if "v61_final_zip" not in st.session_state:
            st.session_state["v61_final_zip"],_=_v61_final_zip(df,_v61_days)
        st.success("✅ UZMAN-01 tamamlandı: günlük mikro yaşam + gerçek walk-forward hazır.")
        st.download_button("⬇️ V6.1 UZMAN-01 ARDIŞIK PROFESÖRÜ — TEK ZIP",
            st.session_state["v61_final_zip"],
            "HIZLI_ON_V6_1_UZMAN01_ARDISIK_PROFESORU_RESULTS.zip",
            "application/zip",use_container_width=True,key="v61_final_download")
# =====================================================================
# /V6.1
# =====================================================================



# =====================================================================
# V6.2 UZMAN-01B — ARDIŞIK DURUM MAKİNESİ / ZAMANLAMA KATMANI
# V6.1'i değiştirmez; onun üstüne kronolojik yaşam/zamanlama uzmanlığı ekler.
# Amaç: sayı adı değil, PRE-H ardışık yaşam durumundan H hareketini ayırmak.
# Kupon üretimi YOK.
# =====================================================================
_V62_DIR=Path(".hizli_on_v62_state_machine")
_V62_DIR.mkdir(parents=True,exist_ok=True)

def _v62_load_v61_days():
    days=sorted(df.date.astype(str).dropna().unique().tolist(),
                key=lambda d:pd.to_datetime(d,dayfirst=True,errors="coerce"))
    if not all(_v61_valid_zip(_v61_day_path(d)) for d in days):
        raise RuntimeError("Önce V6.1 günlük mikro analizlerinin tamamı hazır olmalı.")
    return days,_v61_merge_days(days)

def _v62_motion_class(r):
    # Only PRE-H H3->H2->H1 geometry.
    dc=int(r["block_count_delta_21"]); dl=int(r["max_len_delta_21"])
    if dc==0 and dl==0:return "STABLE"
    if dl>0:return "EXPANDING"
    if dl<0:return "CONTRACTING"
    if dc>0:return "FRAGMENTING"
    if dc<0:return "MERGING"
    return "MORPHING"

def _v62_build_state_table(chain):
    q=chain.copy()
    q["pre_motion"]=q.apply(_v62_motion_class,axis=1)
    q["pre_state_key"]=(
        q.pre_regime.astype(str)+"|"+q.phase.astype(str)+"|"+
        q.H3_shape.astype(str)+">"+q.H2_shape.astype(str)+">"+q.H1_shape.astype(str)+"|"+
        q.pre_motion.astype(str)
    )
    q["target_block_delta"]=q.H_block_count-q.H1_block_count
    q["target_maxlen_delta"]=q.H_max_len-q.H1_max_len
    q["target_motion"]=np.select(
        [q.target_maxlen_delta>0,q.target_maxlen_delta<0,q.target_block_delta>0,q.target_block_delta<0],
        ["EXPAND","CONTRACT","FRAGMENT","MERGE"],default="STABLE_OR_MORPH")
    return q

def _v62_q2_context(pair):
    q=pair[pair.Q2_GATE_FROZEN==1].copy()
    if q.empty:return q
    q["pre_motion"]=q.apply(_v62_motion_class,axis=1)
    q["context_key"]=(
        q.pre_regime.astype(str)+"|"+q.phase.astype(str)+"|"+q.zone800.astype(str)+"|"+
        q.osc800.astype(str)+"|"+q.pre_motion.astype(str)+"|B"+q.pre_total_blocks.astype(str))
    return q

def _v62_transition_summary(state):
    return (state.groupby(["pre_regime","phase","pre_motion","H1_shape","target_motion"],dropna=False)
            .agg(events=("draw_no","count"),
                 target_blocks_mean=("H_block_count","mean"),
                 target_maxlen_mean=("H_max_len","mean"))
            .reset_index())

def _v62_state_walkforward(state,warmup=900,block=120):
    draws=sorted(state.draw_no.unique()); rows=[]
    for pos in range(warmup,len(draws),block):
        td=draws[pos:min(pos+block,len(draws))]
        if not td:continue
        tr=state[state.draw_no<td[0]]
        te=state[state.draw_no.isin(td)]
        # Learn only recurrent PRE-H states from past.
        stats=(tr.groupby(["pre_regime","pre_motion","H1_shape"],dropna=False)
               .target_motion.value_counts(normalize=False).rename("hits").reset_index())
        totals=(tr.groupby(["pre_regime","pre_motion","H1_shape"],dropna=False)
                .size().rename("train_tests").reset_index())
        st=stats.merge(totals,on=["pre_regime","pre_motion","H1_shape"])
        st["train_rate"]=st.hits/st.train_tests
        st=st[(st.train_tests>=12)&(st.train_rate>=0.45)]
        for _,r in st.iterrows():
            g=te[(te.pre_regime.astype(str)==str(r.pre_regime))&
                 (te.pre_motion.astype(str)==str(r.pre_motion))&
                 (te.H1_shape.astype(str)==str(r.H1_shape))]
            if len(g)<3:continue
            hit=(g.target_motion.astype(str)==str(r.target_motion))
            rows.append({"test_from":td[0],"test_to":td[-1],
                         "pre_regime":r.pre_regime,"pre_motion":r.pre_motion,"H1_shape":r.H1_shape,
                         "predicted_motion":r.target_motion,
                         "train_tests":int(r.train_tests),"train_rate":float(r.train_rate),
                         "blind_tests":len(g),"blind_hits":int(hit.sum()),"blind_rate":float(hit.mean())})
    return pd.DataFrame(rows)

def _v62_q2_walkforward(q,warmup=500,block=120):
    if q.empty:return pd.DataFrame()
    draws=sorted(q.draw_no.unique());rows=[]
    for pos in range(min(warmup,max(1,len(draws)//3)),len(draws),block):
        td=draws[pos:min(pos+block,len(draws))]
        if not td:continue
        tr=q[q.draw_no<td[0]];te=q[q.draw_no.isin(td)]
        st=(tr.groupby(["pre_regime","pre_motion","zone800","osc800"],dropna=False)
            .Q2_HIT.agg(["count","sum","mean"]).reset_index())
        st=st[st["count"]>=5]
        for _,r in st.iterrows():
            g=te[(te.pre_regime.astype(str)==str(r.pre_regime))&
                 (te.pre_motion.astype(str)==str(r.pre_motion))&
                 (te.zone800.astype(str)==str(r.zone800))&
                 (te.osc800.astype(str)==str(r.osc800))]
            if len(g)==0:continue
            rows.append({"test_from":td[0],"test_to":td[-1],"pre_regime":r.pre_regime,
                         "pre_motion":r.pre_motion,"zone800":r.zone800,"osc800":r.osc800,
                         "train_signals":int(r["count"]),"train_hits":int(r["sum"]),
                         "train_rate":float(r["mean"]),"blind_signals":len(g),
                         "blind_hits":int(g.Q2_HIT.sum()),"blind_rate":float(g.Q2_HIT.mean())})
    return pd.DataFrame(rows)

def _v62_make_zip():
    days,(block61,pair61,num61,chain61)=_v62_load_v61_days()
    state=_v62_build_state_table(chain61)
    trans=_v62_transition_summary(state)
    q2=_v62_q2_context(pair61)
    wf=_v62_state_walkforward(state)
    q2wf=_v62_q2_walkforward(q2)
    # recurrent state map, descriptive only
    state_map=(state.groupby(["pre_regime","phase","pre_motion","H1_shape","target_motion"],dropna=False)
               .size().rename("events").reset_index())
    if not state_map.empty:
        den=state_map.groupby(["pre_regime","phase","pre_motion","H1_shape"]).events.transform("sum")
        state_map["rate"]=state_map.events/den
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_MANIFEST.txt",
          "V6.2 ARDISIK DURUM MAKINESI\n"
          "V6.1 mikro verisinin zamanlama katmanidir.\n"
          "PRE-H H3>H2>H1 yasam durumu: stable/expanding/contracting/fragmenting/merging.\n"
          "H sonucu yalniz hedef etiketi olarak kullanilir. Walk-forward gelecege sizmaz.\n"
          "Q2 tanimi degistirilmez; sadece hangi PRE-H baglamlarda calistigi olculur.\n"
          "Kupon yok.\n")
        for fn,t in {
          "01_STATE_TIMELINE.csv":state,
          "02_TRANSITION_SUMMARY.csv":trans,
          "03_RECURRENT_STATE_MAP.csv":state_map,
          "04_STATE_TRUE_WALK_FORWARD.csv":wf,
          "05_Q2_CONTEXT_EVENTS.csv":q2,
          "06_Q2_CONTEXT_TRUE_WALK_FORWARD.csv":q2wf
        }.items():
            z.writestr(fn,t.to_csv(index=False).encode("utf-8-sig"))
    return bio.getvalue()

st.divider()
st.header("🧠 V6.2 UZMAN-01B — ARDIŞIK DURUM MAKİNESİ")
st.caption("Doğum/büyüme/daralma/parçalanma/birleşme yaşamının ZAMANINI H3→H2→H1 üzerinden öğrenir; Q2'yi de karakter bağlamında ayrı doğrular.")

if st.button("▶️ V6.2 DURUM MAKİNESİNİ ÇALIŞTIR",use_container_width=True,type="primary",
             key="v62_run",disabled=(_V62_DIR/"RESULTS.zip").exists()):
    ss=st.status("Ardışık durum makinesi çalışıyor…",expanded=True)
    try:
        bb=_v62_make_zip()
        (_V62_DIR/"RESULTS.zip").write_bytes(bb)
        ss.update(label="✅ V6.2 Ardışık Durum Makinesi tamamlandı",state="complete",expanded=False)
        st.rerun()
    except Exception as e:
        ss.update(label="❌ V6.2 hata verdi",state="error",expanded=True)
        st.exception(e)

if (_V62_DIR/"RESULTS.zip").exists():
    st.download_button("⬇️ V6.2 ARDIŞIK DURUM MAKİNESİ — TEK ZIP",
        (_V62_DIR/"RESULTS.zip").read_bytes(),
        "HIZLI_ON_V6_2_ARDISIK_DURUM_MAKINESI_RESULTS.zip",
        "application/zip",use_container_width=True,key="v62_download")
# =====================================================================
# /V6.2
# =====================================================================
