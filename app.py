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

st.set_page_config(page_title="Hızlı On — Yaşam Kimliği MASTER V3", page_icon="🧬", layout="wide")

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


def number_trace(df: pd.DataFrame, target_i: int, n: int, lookback: int=18) -> pd.DataFrame:
    """Seçilen sayının hedefe yaklaşırken adım adım yaşam karakterini gösterir."""
    rows=[]
    start=max(1,target_i-lookback)
    for j in range(start,target_i+1):
        snap=build_pre_snapshot(df,j)
        r=snap[snap.number==n].iloc[0].to_dict()
        r["actual_at_step"]=int(n in set(df.iloc[j].nums))
        r["step_draw_no"]=int(df.iloc[j].draw_no)
        r["step_date"]=df.iloc[j].date
        r["step_time"]=df.iloc[j].time
        rows.append(r)
    return add_identity_keys(pd.DataFrame(rows)) if rows else pd.DataFrame()


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
        for n in sorted(real20.number.tolist()):
            tr=number_trace(df,i,int(n),lookback=18)
            z.writestr(f"yasam_izleri/{int(n):02d}_yasam_izi.csv",to_csv_bytes(tr))
        z.writestr(f"07_MIMARI_RAPOR_{int(df.iloc[i].draw_no)}.txt",report)
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
st.title("🧬 Hızlı On — Yaşam Kimliği MASTER APP V3")
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
    st.success("✅ 25–29 Ağustos ana veri tabanı eksiksiz: 5 gün × 217 = 1.085 çekiliş / 21.700 sayı sonucu.")
else:
    st.warning("⚠️ Ana veri tabanında eksik/fazla/bozuk kayıt var. Aşağıdaki günlük kontrolü incele.")
with st.expander("5 gün ayrı ayrı veri kontrolü", expanded=not health["ok"]):
    st.dataframe(health["days"],use_container_width=True,hide_index=True)
    if health["missing"]:
        st.write("Eksik çekilişler:", health["missing"][:100])
    if health["extra"]:
        st.write("Beklenen 5 gün aralığı dışındaki ek çekilişler:", health["extra"][:100])

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

T1,T2,T3,T4,T5,T6,T7=st.tabs([
    "🎯 Gerçek 20 Anatomisi",
    "🧬 Aynı Kimlik / Negatif 60",
    "🪜 20 Sayının Yaşam İzleri",
    "🌊 Karakter Salınımı",
    "🔢 Sayı Özel Hafıza",
    "🧪 Kör Havuz Testi",
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

with T3:
    st.subheader("Gerçek 20'nin adım adım yaşam izleri")
    trace_n=st.selectbox("Çıkan 20 içinden yaşamını izle",sorted(real20.number.tolist()),key="trace_n")
    look=st.slider("Kaç önceki hedef adımı gösterilsin?",6,36,18,key="trace_look")
    tr=number_trace(df,i,int(trace_n),lookback=look)
    trace_cols=["step_draw_no","step_date","step_time","actual_at_step","gap","recurrence","temp_layer","temp_migration","temp_slope_dir","K_phase","band","path6","hits12","neighbor_H1","corridor_H1_count","band_pressure_delta","prev_block_member","prev_block_len","social_top3","identity_core"]
    st.dataframe(tr[trace_cols],use_container_width=True,height=620)
    st.download_button(f"{int(trace_n)} yaşam izi CSV indir",to_csv_bytes(tr),f"{int(trace_n)}_yasam_izi_{sel_draw}.csv","text/csv")

    st.subheader("20 sayının son yaşam karakteri — tek tabloda")
    st.dataframe(real20[["number","recurrence","gap","temp_layer","temp_migration","temp_slope_dir","K_phase","band","path6","hits12","neighbor_H1","corridor_H1_count","band_pressure_delta","prev_block_member","social_top3","identity_detail"]].sort_values("number"),use_container_width=True,height=620)

with T4:
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

with T5:
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
    st.subheader("Tüm araştırmayı dışa aktar")
    st.download_button("Bu hedefin 80 PRE-H snapshot CSV'si",to_csv_bytes(snap),f"preH_{sel_draw}_80.csv","text/csv")
    st.download_button("Bu hedefin 80 POST-H etiketli CSV'si",to_csv_bytes(labeled),f"postH_{sel_draw}_80.csv","text/csv")
    st.download_button("Gerçek 20 kimlik CSV'si",to_csv_bytes(real20),f"real20_identity_{sel_draw}.csv","text/csv")
    st.download_button("Negatif 60 fark haritası CSV",to_csv_bytes(neg60),f"negatif60_{sel_draw}.csv","text/csv")
    st.download_button("Gerçek 20 rakip özeti CSV",to_csv_bytes(rival20),f"real20_rakip_{sel_draw}.csv","text/csv")
    report=architecture_report_text(df,i,labeled)
    st.download_button("Gerçek 20 mimari TXT raporu",report.encode("utf-8"),f"real20_mimari_{sel_draw}.txt","text/plain")
    bundle=make_research_zip(df,i,snap,labeled,real20,neg60,rival20,ts,report)
    st.download_button("📦 TÜM ARAŞTIRMAYI TEK ZIP İNDİR",bundle,f"HIZLI_ON_TUM_ARASTIRMA_{sel_draw}.zip","application/zip",use_container_width=True)
    st.caption("ZIP içinde: ana veri, 80 PRE-H, 80 POST-H, gerçek 20, negatif 60, rakip özeti, karakter salınımı, çıkan 20'nin ayrı yaşam izleri ve mimari rapor bulunur.")
    st.text_area("Rapor önizleme",report,height=520)

st.divider()
st.caption("MASTER V3 araştırma kuralı: Veri hızlı güncellenir → PRE-H 80 fotoğrafı → gerçek 20'nin tüm yaşam karakterleri → aynı kimlikteki rakipler → dışarıdaki 60'ın fark haritası → sayı özel yaşam izi → karakter salınımı → kör doğrulama. Kupon üretimi bu araştırma sürümünde bilinçli olarak yoktur.")
