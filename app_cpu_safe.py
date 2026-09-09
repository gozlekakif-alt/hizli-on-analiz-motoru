from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from collections import Counter, defaultdict
from itertools import combinations
import io
import math
import re
import zipfile
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
st.title("🧬 Hızlı On — Yaşam Kimliği MASTER APP V4.2 — CPU SAFE + 14 GÜN")
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
neg60=negative60_diagnostic(labeled)
rival20=real20_rival_summary(labeled)

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

    st.subheader("Gerçek 20'nin aynı kimlikteki rakipleri")
    st.caption("Aynı kimlikte başka sayı varsa, o kimlik tek başına ayırıcı değildir.")
    st.dataframe(rival20,use_container_width=True,height=420)

    st.subheader("Dışarıda kalan 60 — negatif kontrol fark haritası")
    st.caption("'Neden dışarıda?' burada nedensellik olarak değil, çıkan 20'ye göre hangi yaşam alanlarında farklılaştığı olarak gösterilir.")
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
            _bundle=make_research_zip(df,i,snap,labeled,real20,neg60,rival20,_ts_for_zip,report)
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
        _v_target_zip=make_research_zip(df,i,snap,labeled,real20,neg60,rival20,_v_ts,_v_report)
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
st.subheader("🗓️ 14 GÜNLÜK TÜM ANALİZLER — CPU SAFE")
st.caption("14 gün tek seferde CPU'ya yüklenmez. Her tıklamada yalnız 1 gün hesaplanır; tamamlanan gün oturumda tutulur. 14/14 olunca tek ana ZIP indirilir.")

if "master14_parts" not in st.session_state:
    st.session_state["master14_parts"]={}
if "master14_next" not in st.session_state:
    st.session_state["master14_next"]=0

_expected14=[d for d,_,_ in EXPECTED_DAYS]
_done14=st.session_state["master14_parts"]
_progress14=len(_done14)
st.progress(_progress14/14 if _progress14 else 0.0,text=f"14 günlük paket ilerleme: {_progress14}/14 gün")

c14a,c14b=st.columns(2)
with c14a:
    if st.button("▶️ SONRAKİ GÜNÜ HESAPLA",use_container_width=True,key="master14_next_day",type="primary",disabled=(_progress14>=14)):
        _next_date=_expected14[_progress14]
        _idxs=df.index[df["date"].astype(str)==_next_date].tolist()
        if len(_idxs)!=217:
            st.error(f"{_next_date}: 217 çekiliş bulunamadı.")
        else:
            _status14=st.status(f"{_next_date} hesaplanıyor…",expanded=True)
            try:
                _dayzip=make_full_day_research_zip(df,int(max(_idxs)))
                st.session_state["master14_parts"][_next_date]=_dayzip
                _status14.update(label=f"✅ {_next_date} hazır",state="complete",expanded=False)
                st.rerun()
            except Exception as _e:
                _status14.update(label=f"❌ {_next_date} hazırlanamadı",state="error",expanded=True)
                st.exception(_e)
with c14b:
    if st.button("♻️ 14 GÜNLÜK İLERLEMEYİ SIFIRLA",use_container_width=True,key="master14_reset"):
        st.session_state["master14_parts"]={}
        st.session_state.pop("master14_final_zip",None)
        st.rerun()

_done14=st.session_state["master14_parts"]
if _done14:
    st.write("Hazır günler:", " • ".join(_done14.keys()))

if len(_done14)==14:
    if "master14_final_zip" not in st.session_state:
        st.session_state["master14_final_zip"]=assemble_14_day_research_zip_from_parts(df,_done14)
    st.success("✅ 14/14 gün hazır. Final ZIP yeniden hesaplama yapmadan birleştirildi.")
    st.download_button(
        "⬇️ 25.08–07.09 14 GÜNLÜK MASTER ZIP’İ İNDİR",
        st.session_state["master14_final_zip"],
        "HIZLI_ON_25_08_2026_07_09_2026_14_GUN_MASTER.zip",
        "application/zip",
        use_container_width=True,
        key="download_14_day_master_cpu_safe"
    )

st.divider()
st.caption("MASTER V4.2 CPU SAFE araştırma kuralı: Veri hızlı güncellenir → PRE-H 80 fotoğrafı → gerçek 20'nin tüm yaşam karakterleri → aynı kimlikteki rakipler → dışarıdaki 60'ın fark haritası → sayı özel yaşam izi → karakter salınımı → kör doğrulama. Kupon üretimi bu araştırma sürümünde bilinçli olarak yoktur.")
