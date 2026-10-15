#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V79 — WHERE (five pools + rank 1..16) and WHEN (trajectory phase)
does each number actually become a target-1?

72 complete days; 80 numbers; past-N=60 equal temperature quintiles of 16.
All features are computed BEFORE target t from prior draws only:
    old_pool(t-12), mid_pool(t-6), pool(t), within-pool rank 1..16,
    relative direction old->now, 6+6 initiation/continuation/reversal stage,
    immediate new entrant, capped residence age in pool,
    recent four historical 0/1 values.
Once actual draw t happens, its 20 ones and 60 zeros are overlaid.

Emits only valid consecutive-history (N+12) cases for temporal inference,
respecting 23 Aug gap. Full target raw 1/0 already in V77.
Records ~309,600 actual 1 states + summary with denominators (zeros included),
72-day daily "which stage got 1" and focus draw exact twenty labels.

Historical description only — independent fair 20/80 lottery implies target
p=.25 for every pre-target-defined number regardless of its pool stage.
"""
from __future__ import annotations
import argparse, csv, gzip, io, json, math, zipfile
from collections import defaultdict
from pathlib import Path
import numpy as np

from v78_16lik_sira_nereden_geldi_son4bit_hedef01 import (
    load, prefixize, rolling_ranks, valid_targets
)

VER="V79.1"
N=60
STEP=6
LAG=12
POOL=("SOGUK","SERIN","NOTR","ILIK","SICAK")
TRENDS=("SOGUYA","SABIT","ISINIYOR")
PHASES=(
    "DURGUN",
    "ISINMAYA_BASLADI",
    "ISINMA_SURUYOR",
    "SOGUMADAN_ISINMAYA_DONDU",
    "ISINMA_DURAKLADI",
    "SOGUMA_DURAKLADI",
    "SOGUMAYA_BASLADI",
    "SOGUMA_SURUYOR",
    "ISINMADAN_SOGUMAYA_DONDU",
)
AGE_BUCKETS=("YENI_GIRIS","2_3_ADIM","4_7_ADIM","8_VE_USTU")
POS_QUARTERS=("SIRA_1_4","SIRA_5_8","SIRA_9_12","SIRA_13_16")

def compute_phase(old,mid,new):
    """0..8 2x6-draw stages, all comparisons from before target."""
    early=np.sign(mid.astype(np.int16)-old.astype(np.int16))
    late=np.sign(new.astype(np.int16)-mid.astype(np.int16))
    phase=np.zeros(old.shape,dtype=np.uint8)
    phase[(early==0)&(late>0)]=1
    phase[(early>0)&(late>0)]=2
    phase[(early<0)&(late>0)]=3
    phase[(early>0)&(late==0)]=4
    phase[(early<0)&(late==0)]=5
    phase[(early==0)&(late<0)]=6
    phase[(early<0)&(late<0)]=7
    phase[(early>0)&(late<0)]=8
    return phase

def rate_rows(counter,names):
    result=[]
    for key,(op,one) in sorted(counter.items()):
        if op<1:continue
        label={name:str(k) for name,k in zip(names,key)}
        result.append(dict(**label,opportunities=op,target_ones=one,
                           target_zeros=op-one,
                           target_one_pct=round(100*one/op,6),
                           difference_from_25_pct_points=round(100*one/op-25,6)))
    return result

def writer(z,filename,rows,cols=None):
    if cols is None:
        if not rows: raise ValueError("Need rows "+filename)
        cols=list(rows[0])
    with z.open(filename,"w",force_zip64=True) as raw:
        stream=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        w=csv.DictWriter(stream,fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
        stream.flush();stream.detach()

def writer_gz(z,filename,rows,header):
    with z.open(filename,"w",force_zip64=True) as raw:
        with gzip.GzipFile(fileobj=raw,mode="wb",compresslevel=5) as gz:
            tx=io.TextIOWrapper(gz,encoding="utf-8",newline="")
            w=csv.writer(tx)
            w.writerow(header)
            for row in rows:w.writerow(row)
            tx.flush();tx.detach()

def encode_flags(phase, q, pos, oldq, midq, oldpos, age, before, selected):
    """"selected" is actual target hit flag, never a pre-target selection."""
    direction=1 if q>oldq else -1 if q<oldq else 0
    return (POOL[q],pos,POOL[oldq],oldpos,
        POOL[midq],direction,PHASES[phase],
        "YENI_GIRIS" if age==1 else "2_3_ADIM" if age<=3 else
        "4_7_ADIM" if age<=7 else "8_VE_USTU",
        before,selected)

def run(source,out):
    days,rows,y,gaps,excluded,issues,malformed=load(source)
    pp=prefixize(y)
    ranks=rolling_ranks(pp,N)
    valid=valid_targets(rows,N)
    idx=np.flatnonzero(valid)
    counts=pp[idx]-pp[idx-N] # prior N appearance counts, no current target
    curr=ranks[idx]//16
    middle=ranks[idx-STEP]//16
    old=ranks[idx-LAG]//16
    herepos=ranks[idx]%16+1
    oldpos=ranks[idx-LAG]%16+1
    previous=ranks[idx-1]//16
    phase=compute_phase(old,middle,curr)
    target=y[idx]
    if not np.array_equal(target.sum(axis=1),np.full(len(idx),20)):
        raise AssertionError("Every target has 20 ones exactly")
    if len(idx)!=15480:raise RuntimeError(f"Eligible rows changed: {len(idx)}")
    pattern=np.zeros_like(curr,dtype=np.uint8)
    for delay in (4,3,2,1):
        pattern=pattern*2+y[idx-delay]
    age=np.ones_like(curr,dtype=np.uint8)
    # Age (number of consecutive PRE-TARGET snapshots in same exact 16 tier).
    # At t prior old tier available; clamp age at 12.
    residence=np.ones(80,dtype=np.uint8)
    prev_tier=np.full(80,255,dtype=np.uint8)
    prev_id=None
    ptr=0
    for t in range(N,len(rows)):
        ct=ranks[t]//16
        if prev_id is None or rows[t]["id"]!=prev_id+1 or (prev_tier==255).all():
            residence[:]=1
        else:
            residence=np.where(ct==prev_tier,np.minimum(residence+1,12),1).astype(np.uint8)
        if ptr<len(idx) and int(idx[ptr])==t:
            age[ptr]=residence
            ptr+=1
        prev_tier=ct.copy()
        prev_id=rows[t]["id"]
    assert ptr==len(idx)
    ageclass=np.where(age==1,0,np.where(age<=3,1,np.where(age<=7,2,3))).astype(np.uint8)
    position_group=((herepos-1)//4).astype(np.uint8)
    transitions=(curr.astype(np.int16)-old.astype(np.int16)).astype(np.int8)
    laststep=(curr!=previous)
    assert np.all((curr>=0)&(curr<=4))
    per_stage=defaultdict(lambda:[0,0])
    per_phase=defaultdict(lambda:[0,0])
    per_exact_pos=defaultdict(lambda:[0,0])
    per_level_shift=defaultdict(lambda:[0,0])
    per_combined=defaultdict(lambda:[0,0])
    per_pattern=defaultdict(lambda:[0,0])
    per_age=defaultdict(lambda:[0,0])
    per_coming=defaultdict(lambda:[0,0])
    per_day=defaultdict(lambda:[0,0])
    by_dir=defaultdict(lambda:[0,0])
    actual_rows=[]
    target100=[]
    actual_total=0
    for i,t in enumerate(idx):
        item=rows[int(t)]
        row_ones=[]
        for b in range(80):
            q=int(curr[i,b]);oq=int(old[i,b]);m=int(middle[i,b])
            pos=int(herepos[i,b]);oldp=int(oldpos[i,b])
            agecl=int(ageclass[i,b]);move=int(transitions[i,b])
            ph=int(phase[i,b]);pat=int(pattern[i,b]);entry=int(laststep[i,b])
            hit=int(target[i,b])
            direction="ISINIYOR" if move>0 else "SOGUYOR" if move<0 else "SABIT"
            level=(oq,q)
            stage=(q,ph)
            exactpos=(q,pos)
            stageshift=(q,move)
            combined=(q,ph,int(position_group[i,b]),agecl)
            hist=(q,ph,pat)
            currage=(q,agecl)
            entered=(q,entry)
            for counter,key in (
                (per_stage,stage),(per_phase,(ph,)),
                (per_exact_pos,exactpos),(per_level_shift,stageshift),
                (per_combined,combined),(per_pattern,hist),
                (per_age,currage),(per_coming,entered),
                (per_day,(item["day"],ph)),(by_dir,(direction,))):
                counter[key][0]+=1
                counter[key][1]+=hit
            if not hit:continue
            actual_total+=1
            row_ones.append(b+1)
            actual_rows.append((item["day"],item["time"],item["id"],
                 item["pos"],b+1,
                 int(counts[i,b]),
                 POOL[oq],oldp,POOL[m],POOL[q],pos,
                 move,direction,PHASES[ph],
                 age[i,b],AGE_BUCKETS[agecl],entry,
                 format(pat,"04b"),hit))
        assert len(row_ones)==20
        if i%3500==0:print(f"V79 processed {i}/{len(idx)}",flush=True)

    def summarize(counter,keys,to_text):
        source=rate_rows(counter,keys)
        return [dict(**{key:to_text[key](r[key]) if key in to_text else r[key]
                        for key in keys},**{z:r[z] for z in (
                         "opportunities","target_ones","target_zeros",
                         "target_one_pct","difference_from_25_pct_points")})
                for r in source]

    # Apply human-readable meaning to stage numeric groups.
    stage=summarize(per_stage,("pool_index","phase_index"),
          {"pool_index":lambda v:POOL[int(v)],"phase_index":lambda v:PHASES[int(v)]})
    phases=summarize(per_phase,("phase_index",),
                    {"phase_index":lambda v:PHASES[int(v)]})
    exact_positions=summarize(per_exact_pos,("pool_index","inside_rank"),
                    {"pool_index":lambda v:POOL[int(v)]})
    shifts=summarize(per_level_shift,("pool_index","move_12_pool_delta"),
                    {"pool_index":lambda v:POOL[int(v)]})
    combined=summarize(per_combined,("pool_index","movement_phase",
                      "position_quarter","age_bin"),
                   {"pool_index":lambda v:POOL[int(v)],
                    "movement_phase":lambda v:PHASES[int(v)],
                    "position_quarter":lambda v:POS_QUARTERS[int(v)],
                    "age_bin":lambda v:AGE_BUCKETS[int(v)]})
    patterns=summarize(per_pattern,("pool_index","phase_index","last_4"),
                  {"pool_index":lambda v:POOL[int(v)],
                   "phase_index":lambda v:PHASES[int(v)],
                   "last_4":lambda v:format(int(v),"04b")})
    ages=summarize(per_age,("pool_index","residence_age"),
                  {"pool_index":lambda v:POOL[int(v)],
                   "residence_age":lambda v:AGE_BUCKETS[int(v)]})
    entrances=summarize(per_coming,("pool_index","entry_since_last_draw"),
                  {"pool_index":lambda v:POOL[int(v)]})
    days_phases=summarize(per_day,("day","phase_index"),
                  {"phase_index":lambda v:PHASES[int(v)]})
    directions=rate_rows(by_dir,("direction",))
    directions.sort(key=lambda row:row["direction"])
    # Clear target-1 position references. Unconditionally number of actual true 1 per day sums to 217*20, except first partial analytic days and gap.
    summary=[
      "V79 — 80 SAYININ HANGI YONDE, HANGI ASAMADA HEDEFTE 1 OLDUGU",
      f"Complete days={len(days)}, total raw draws={len(rows)}, valid movement-linked draws={len(idx)}.",
      f"Total labeled true-1 records={actual_total}, predicted checks={len(idx)}.",
      f"Each valid target draw has exactly twenty 1 outcomes and sixty 0 outcomes.",
      "Main N=60 PREVIOUS draws defines 5x16 heat groups with stable tie ranking.",
      "Movement prior history: t-12 -> t-6 -> t (two six-draw phases).",
      "Nine stages distinguish first warming, warming continuation, reversal,",
      "warming pause, no movement, first cooling, cooling continuation, reversal, cooling pause.",
      "Where 1 occurs: exact current group (1..5), current rank INSIDE group (1..16),",
      "old group and rank 12 drawings ago, direction, stage, how long resident,",
      "newly arrived this one draw, previous 4-target 1/0 bits.",
      "ALL positions and signals at t were calculated BEFORE opening outcome t.",
      f"Input incomplete days skipped={excluded}; draw-ID gap={gaps}.",
      "All rate tables include 1 AND 0 denominators; 1-only audit rows separately provided.",
      "",
      "NINE MOVEMENT STAGES vs realized target 1 percentages (fair expected 25%):"
    ]
    for row in phases:
        summary.append(f"{row['phase_index']:34} : "
                       f"{row['target_ones']}/{row['opportunities']} "
                       f"= {row['target_one_pct']:.5f}%")
    summary+=["","THREE LONG-DIRECTION STATES TARGET 1 rate:"]
    for row in directions:
        summary.append(f"{row['direction']:10}: "
          f"{row['target_ones']}/{row['opportunities']} "
          f"= {row['target_one_pct']:.5f}%")
    summary+=["","FIRST 6 NUMBER IDENTITY RECORDS WHERE TARGET 1:"]
    for r in actual_rows[:6]:
        summary.append(f"#{r[2]} id={r[4]} 12-before={r[6]} at rank={r[7]}, "
            f"now={r[9]} rank={r[10]}, delta={r[11]}, dir={r[12]}, "
            f"stage={r[13]}, last4={r[17]}, target={r[18]}")
    summary+=["",
      "Interpretation: All 9 movement categories, 5 heat classes and intra-16",
      "positions are derived from rolling frequency RANKS, not true RNG state.",
      "A target 1 is the actual drawn number and does NOT establish that",
      "the stage or direction predicted its future appearance.",
      "Inspect rates and holdout comparisons before considering signal.",
      "See V78: adding those features to candidate selection did not beat random.",
      ""
    ]
    outfile=Path(out);outfile.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(outfile,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        z.writestr("00_V79_KISA_SONUC.txt","\n".join(summary))
        writer_gz(z,"01_HEDEFTE_1_OLAN_BUTUN_SAYILAR_YON_ASAMA_IC_SIRA.csv.gz",
                  actual_rows,
                  ["tarih","saat","cekilis_no","gun_sirasi","sayi",
                   "son_60_cikis_sayisi","12_onceki_havuz","12_onceki_1_16_sira",
                   "6_onceki_havuz","hedef_oncesi_havuz","hedef_oncesi_1_16_sira",
                   "havuz_12_hareket_farki","yon","yon_hareket_asamasi",
                   "bu_havuzda_kalis_adimi_enfazla12","yas_sinifi",
                   "son_hedef_oncesi_giris_1_0","onceki4_hedef_1_0","hedef_1"])
        for filename,rr in (
          ("02_DOKUZ_YON_ASAMASI_HEDEF_1_0_ORAN.csv",phases),
          ("03_BES_HAVUZ_X_DOKUZ_ASAMA_HEDEF_1_0.csv",stage),
          ("04_BES_HAVUZ_ICIN_TAM_1_16_SIRA_HEDEF_1_0.csv",exact_positions),
          ("05_BES_HAVUZ_X_12_CEKILISLIK_4_DERECE_YER_DEGISIMI.csv",shifts),
          ("06_HAVUZ_X_ASAMA_X_SIRA_CEYREGI_X_KALIS_SURESI.csv",combined),
          ("07_HAVUZ_X_ASAMA_X_ONCEKI4BIT_1_0.csv",patterns),
          ("08_HAVUZ_X_KALIS_SURESI_HEDEF_1_0.csv",ages),
          ("09_YENI_GIRDI_MI_HEDEF_1_0.csv",entrances),
          ("10_72_GUN_ASAMA_BAZLI_1_0_GUNLUK.csv",days_phases),
          ("11_UC_YON_HEDEF_1_0_ORANI.csv",directions)):
             writer(z,filename,rr)
        z.writestr("12_KURALLAR_VE_VERI_KALITESI.txt","\n".join([
           "The true target indicator=1 if 20 drawn includes the ball; otherwise 0.",
           "No target outcome influences its own rank, pool, stage, direction or age.",
           "At draw t, current tier from appearances in draws t-60 through t-1.",
           "Old tier uses target prehistory t-12; midway pool t-6.",
           "Changes are labels on sorted 16-number frequency bins, NOT movements",
           "of an actual ball/lottery physical state.",
           "Rank-inside-tiers current 1..16 and earlier t-12 1..16 are stored.",
           "A 1-only table for all 309600 actual target 1 instances per eligible draw.",
           "All 1/0 denominators in grouped rate tables, fair expected 25%.",
           "Movement ages capped at 12 consecutive target-index updates.",
           "Incomplete 23 Aug excluded; gap-aware valid window avoids all missing data.",
           "N=60 distinct from 72 complete DAYS of observational data.",
           "No independent prospective selection advantage has yet been demonstrated."
        ]))
        z.writestr("13_AUDIT.json",json.dumps(dict(
          version=VER,valid_target_draws=len(idx),total_true1=actual_total,
          valid_identity_records=int(target.size),
          total_true0=int(target.size-actual_total),
          main_reference=N,trajectory_lag=LAG,trajectory_mid=STEP,
          nine_phase_labels=PHASES,full_days=days,
          incomplete_days=excluded,id_gaps=gaps,malformed=malformed[:20],
          warnings=issues[:20]),ensure_ascii=False,indent=2))
    print("\n".join(summary),flush=True)
    print("V79 OUTPUT",str(outfile),outfile.stat().st_size,flush=True)

def selftest():
    a=np.array([[0,1,1,2,1,2,1,3,1]],dtype=np.uint8)
    b=np.array([[0,1,2,1,2,1,1,2,2]],dtype=np.uint8)
    c=np.array([[0,2,3,2,2,1,0,1,1]],dtype=np.uint8)
    got=compute_phase(a,b,c)
    assert got.shape==(1,9)
    assert set(int(x) for x in got[0])==set(range(9))
    print("V79 NINE STAGES SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v79_output/V79_72_GUN_HANGI_YONDE_HANGI_ASAMADA_HEDEF_1_OLUYOR.zip")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest()
    else:run(args.source,args.out)
