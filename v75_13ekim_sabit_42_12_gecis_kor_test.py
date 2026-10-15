#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V75 next-day replay of frozen V74 winner without retuning.

V74 training on 29 Aug–12 Sep fixed N=42, lag12, DIRECTION15, alpha=250.
V74 validation and 15-day holdout selected the recipe. This V75 tests
chronologically NEXT 13 October 2026 draws in veri.txt. The 13 Oct file
contains missing draw IDs, so use only the initial complete consecutive
prefix from 13 Oct 00:02 until immediately BEFORE its first missing draw.
No gap-filling or post-hoc parameter changes. Results are a one-day
retrospective next-day check, NOT a guaranteed actual future prediction.
"""
from __future__ import annotations
import argparse,csv,io,json,math,zipfile
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt
from v74_5x5_kimlik_yon_gecis_kalibrasyon import (
    EARLY_DAYS,PER_DAY,DAYS_PER_PART,SEED,TARGETS,
    prefixify,fixed_quintiles,states_of,posteriors,selection,
    paired_p as comparison_p,fair_p)
N=42
LAG=12
KIND="DIRECTION15"
STRENGTH=250
FOCUS="2026-10-13"
HEAT=("SOGUK","SERIN","NOTR","ILIK","SICAK")
DIR=("SOGUYOR","SABIT","ISINIYOR")

def data(src):
    buckets,issues,malformed=parse_txt(src)
    dates=sorted(d for d,v in buckets.items()
           if len(v)==217 and [r["pos"] for r in v]==list(range(1,218)))
    if len(dates)<72 or dates[71]!="2026-10-12":
        raise ValueError("Needs V74 corpus through 12 October")
    history=[r for d in dates[:72] for r in buckets[d]]
    after=buckets.get(FOCUS,[])
    if not after:raise ValueError("Missing 13 October partial day")
    if history[-1]["id"]!=61845 or after[0]["id"]!=61846:
        raise ValueError("Unexpected date boundary")
    expected=after[0]["id"]
    usable=[]
    for row in after:
        if row["id"]!=expected:
            break
        usable.append(row)
        expected+=1
    missing=[]
    known={r["id"] for r in after}
    for ident in range(after[0]["id"],after[-1]["id"]+1):
        if ident not in known:missing.append(ident)
    if not usable:raise ValueError("No gap-free future data")
    return history,after,usable,missing,issues,malformed

def csvsave(z,path,rows):
    with z.open(path,"w",force_zip64=True) as raw:
        stream=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        stream.flush();stream.detach()

def analyse(src,out):
    history,partial,test,gaps,issues,malformed=data(src)
    allrows=history+test
    prefix=prefixify(allrows)
    numids=np.arange(80,dtype=int)
    train_start=EARLY_DAYS*PER_DAY
    train_end=train_start+DAYS_PER_PART*PER_DAY
    train_size=train_end-train_start
    train_states=np.empty((train_size,80),dtype=np.uint8)
    train_y=np.zeros((train_size,80),dtype=np.uint8)
    for i,t in enumerate(range(train_start,train_end)):
        current=fixed_quintiles(prefix,t,N,numids)
        prior=fixed_quintiles(prefix,t-LAG,N,numids)
        train_states[i]=states_of(current,prior,KIND)
        train_y[i,np.asarray(allrows[t]["nums"],dtype=int)-1]=1
    fitted,ncounts,nhits=posteriors(train_states,train_y,KIND,STRENGTH)
    tstart=len(history)
    ntest=len(test)
    current=np.empty((ntest,80),dtype=np.uint8)
    before=np.empty((ntest,80),dtype=np.uint8)
    states=np.empty((ntest,80),dtype=np.uint8)
    y=np.zeros((ntest,80),dtype=np.uint8)
    for i,t in enumerate(range(tstart,tstart+ntest)):
        current[i]=fixed_quintiles(prefix,t,N,numids)
        before[i]=fixed_quintiles(prefix,t-LAG,N,numids)
        states[i]=states_of(current[i],before[i],KIND)
        y[i,np.asarray(allrows[t]["nums"],dtype=int)-1]=1
    # Same 741015-generated tie-break sequence as continuing V74's
    # 9,765 chronological TRAIN+VALIDATE+HOLDOUT targets from the next draw.
    tie=np.random.default_rng(SEED).random((TARGETS+ntest,80))[TARGETS:]
    chosen=selection(current,states,fitted,tie)
    balanced=selection(current,current,np.ones(5)*.25,tie)
    inference,a,b=comparison_p(chosen,balanced,y)
    fair=fair_p(int(a.sum()),ntest)
    per_target=[]
    per_number=[]
    movement_profile=[]
    dates_seen=[]
    for i,row in enumerate(test):
        heat=current[i];prev=before[i]
        sel=chosen[i];actual=y[i]
        pools=[]
        poolhits=[]
        for j in range(5):
            vals=[int(b)+1 for b in np.flatnonzero(sel & (heat==j))]
            pools.append(vals)
            poolhits.append(int(actual[heat==j].sum()))
        per_target.append(dict(date=row["day"],draw_id=row["id"],
            time=row["time"],day_slot=row["pos"],
            model_n=N,lag=LAG,shrinkage=STRENGTH,
            selected20=",".join(map(str,np.flatnonzero(sel)+1)),
            model_hits=int(a[i]),random_5x4_hits=int(b[i]),
            model_hit_numbers=",".join(str(j+1) for j in np.flatnonzero(sel & actual)),
            **{f"havuz_{HEAT[j].lower()}":",".join(map(str,pools[j])) for j in range(5)},
            **{f"gercek_{HEAT[j].lower()}":poolhits[j] for j in range(5)}))
        for j in range(80):
            d=int(heat[j])-int(prev[j])
            per_number.append(dict(date=row["day"],draw_id=row["id"],
              ball=j+1,previous_heat=HEAT[prev[j]],current_heat=HEAT[heat[j]],
              tier_difference=d,up_or_down=("UP" if d>0 else "DOWN" if d<0 else "STAY"),
              trained_p=round(float(fitted[states[i,j]]),7),
              chosen_in20=int(sel[j]),actual_next_draw_hit=int(actual[j])))
    for heat in range(5):
        for d in range(3):
            prev_gt=np.where(current>before,2,np.where(current<before,0,1))
            mask=(current==heat)&(prev_gt==d)
            op=int(mask.sum());num=int(y[mask].sum())
            movement_profile.append(dict(
               heat_pool=HEAT[heat],movement=DIR[d],
               number_draw_opportunities=op,actual_hits=num,
               rate=round(num/op,6) if op else None,fair_rate=.25))
    observed_mean=float(a.mean())
    random_mean=float(b.mean())
    per_draw_gap=observed_mean-random_mean
    brier=float(np.mean((fitted[states]-y)**2))
    null_brier=float(np.mean((.25-y)**2))
    total_sum=int(a.sum())
    summary=[
       "V75 — 13 EKIM YENI GUN FROZEN V74 42/12 YON MODELI",
       f"V74 winner parameters FROZEN: N={N}, LAG={LAG}, MODEL={KIND}, SHRINK={STRENGTH}.",
       f"Training fitted ONLY to 29 Aug–12 Sep 2026 15 complete days = {train_size} draws.",
       f"Test day: {FOCUS}, provided records={len(partial)}, usable CONTIGUOUS segment={ntest}.",
       f"Test first draw #{test[0]['id']} {test[0]['time']} last valid #{test[-1]['id']} {test[-1]['time']}.",
       f"Missing full-day draw IDs present within supplied range: {gaps}.",
       "Records after the first missing draw NOT used: lag/N require genuinely consecutive past draws.",
       "The exact model scoring recipe from V74 remains fixed, and the 20 number selection",
       "is built BEFORE the held-out true 20 balls are read for each target draw.",
       "",
       f"13 OCT SELECTED 20 average hits: {observed_mean:.6f}/20, total hits={total_sum}.",
       f"13 OCT RANDOM 5x4 average hits: {random_mean:.6f}/20, total hits={int(b.sum())}.",
       f"Paired difference model - control: {per_draw_gap:+.6f} hits/draw.",
       f"Paired Z={inference['paired_z']:.4f}, one-sided p={inference['paired_one_sided_p']:.6f}.",
       f"Fair independent RNG expected 5/20, approximate one-sided p={fair:.6f}.",
       f"Model Brier={brier:.9f}, fair 0.25 Brier={null_brier:.9f}.",
       f"Model hits>=7: {int((a>=7).sum())}; >=8: {int((a>=8).sum())};",
       f">=9: {int((a>=9).sum())}; >=10: {int((a>=10).sum())}.",
       "",
       "First missing draw invalidates exact historical N and lag for later records;",
       "do not fabricate those results or silently compress gaps.",
       "Even this new-day historical replay is not a real-time prospective test;",
       "13 October data are pre-existing and from a partially completed day.",
       "Evidence from 112-ish draws will have high uncertainty; no guaranteed 20/20.",
       "All individual 20 candidates and heat movements are in the ZIP."
    ]
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        z.writestr("00_KISA_SONUC_V75.txt","\n".join(summary)+"\n")
        csvsave(z,"01_13_EKIM_HER_HEDEF_20_ADAY_VE_ISABET.csv",per_target)
        csvsave(z,"02_13_EKIM_HER_SAYI_ESKI_YENI_HAVUZ_ISI_YON.csv",per_number)
        csvsave(z,"03_5x3_ISI_YON_13_EKIM_CALIBRATION.csv",movement_profile)
        scores=[dict(current_heat=HEAT[j//3],
          movement=DIR[j%3],train_opportunities=int(ncounts[j]),
          train_hits=int(nhits[j]),fixed_train_probability=round(float(fitted[j]),9))
                for j in range(15)]
        csvsave(z,"04_DEGISTIRILMEYEN_TRAIN_OGRENILMIS_ORANLAR.csv",scores)
        z.writestr("05_KURAL_DENETIMI.txt","\n".join([
          "Frozen V74 recipe N=42, lag=12, DIRECTION15, pseudocount alpha250.",
          "TRAIN 29 Aug–12 Sep. Validation/holdout not used to refit.",
          "5x16 current temperature ranks, 4 candidate balls from each tier.",
          "Learnt conditional 5x3 tier/direction rate ranks each ball.",
          "Fixed seeded tiebreak deterministic continuing V74 RNG SEED.",
          "Test is only the first uninterrupted segment of 13 October partial draws.",
          "Before missing #61958 no draw is missing from the prediction history.",
          "After #61958 at least one target-relevant draw would be missing;",
          "those outcomes cannot be used as contiguous N+lag history.",
          "Target numbers do not enter their own predictions; prefix excludes them.",
          "Later data already exists: this is retrospective next-day replay,",
          "NOT a real-time or truly never-inspected future validation."
        ])+"\n")
        z.writestr("06_AUDIT.json",json.dumps(dict(
          version="V75",focus_day=FOCUS,frozen=dict(N=N,lag=LAG,
          kind=KIND,strength=STRENGTH,seed=SEED),
          total_partial_day_records=len(partial),contiguous_test_draws=ntest,
          first_draw_id=test[0]["id"],last_draw_id=test[-1]["id"],
          missing_ids=gaps,model_mean=observed_mean,
          random_mean=random_mean,paired=inference,fair_p_one_sided=fair,
          model_brier=brier,null_brier=null_brier,
          data_warnings=issues[:20],malformed=malformed[:20]),
          ensure_ascii=False,indent=2))
    print("\n".join(summary),flush=True)
    print("V75 ZIP",out,out.stat().st_size,flush=True)

def selftest():
    assert N==42 and LAG==12 and KIND=="DIRECTION15" and STRENGTH==250
    assert SEED==741015
    assert TARGETS==9765
    print("V75 FROZEN SELFTEST OK")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v75_output/V75_13EKIM_SABIT_42_12_GECIS_ILK_KESINTISIZ_KOR_TEST.zip")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:selftest()
    else:analyse(a.source,a.out)
