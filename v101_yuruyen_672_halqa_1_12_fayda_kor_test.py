#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V101 — Which life stages of the true walking 672/FIFO ring help?

Retains V100C (no file modifications). Every target t is preceded by
[ t-672, t ) ONLY; 56 sealed 12-draw rings at boundary, otherwise 55
sealed + 2 partial (oldest and newborn). Absolute ring IDs never reset.

Prespecified diagnostic candidates are evaluated chronologically by
36/18/18 historical days, with Oct-13+ separately tagged NEW_DATA.
20-number selections are paired per exact target with HOT72 and seeded
RANDOM20. Inspect the newborn ring at each of its 12 growing stages,
and the 12 vs 72 pool interactions, before looking at the target.
Descriptive coincidences do not imply RNG predictability or profits.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,io,json,math,random,zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import (
    CAPACITY, GROUP, HISTORY_WARMUP, load, temperature, top20)
VERSION="V101.1"
SEED=101162672
START=CAPACITY+HISTORY_WARMUP
POOLS=("SOGUK","SERIN","NOTR","ILIK","SICAK")
METHODS=("HOT72","PREVIEW_POOL","PREVIEW_COUNT","LAST12_TRAILING",
         "LAST_COMPLETED_RING","PREVIEW_PLUS_72","RISING_SEALED6",
         "REBOUND_RING","RECENT_HOT_RING3","LAST_DRAW_REPEAT")
ALT=METHODS[1:]
STATUSES=("TRAIN","VALIDATE","HOLDOUT","NEW_DATA")

def prep(prefix,t):
    """Past-only ring stages/features, no target x[t] access."""
    phase=t%12
    stage=phase if phase else 12
    completed_end=t-phase  # t itself if exactly at ring boundary
    oldstart=t-672
    assert oldstart>=60
    oldest_size=(12-phase) if phase else 12
    newest_size=stage
    # last 7 SEALED ring endpoints (enough for last-6 direction).
    last7=np.stack([temperature(prefix[e]-prefix[e-72])
       for e in range(completed_end-72,completed_end+1,12)],axis=1)
    assert last7.shape==(80,7)
    latest_state=last7[:,-1]
    rising=(last7[:,-1]-last7[:,0]).astype(float)
    rebound=2*last7[:,-1]-last7[:,-4]-last7[:,-7]
    last3hot=np.sum(last7[:,-3:]==4,axis=1)
    # Newborn from absolute ring origin, not last 'stage' sliding draws.
    active_counts=(prefix[t]-prefix[t-stage]).astype(float)
    prev_complete=(prefix[completed_end]-prefix[completed_end-12]).astype(float)
    last12=(prefix[t]-prefix[t-12]).astype(float)
    hot72=(prefix[t]-prefix[t-72]).astype(float)
    live_state=temperature(active_counts)
    lastdraw=(prefix[t]-prefix[t-1]).astype(float)
    eps=hot72/1000+(79-np.arange(80))/1e7
    # Same candidate specification for all target dates and ring stages.
    scores={
      "HOT72":hot72,
      "PREVIEW_POOL":live_state*20+eps,
      "PREVIEW_COUNT":active_counts*20+eps,
      "LAST12_TRAILING":last12,
      "LAST_COMPLETED_RING":prev_complete,
      "PREVIEW_PLUS_72":4*active_counts/max(stage,1)+hot72/18+eps,
      "RISING_SEALED6":rising*20+eps,
      "REBOUND_RING":rebound*20+eps,
      "RECENT_HOT_RING3":last3hot*20+eps,
      "LAST_DRAW_REPEAT":lastdraw*20+eps
    }
    assert len(scores)==len(METHODS) and set(scores)==set(METHODS)
    features=dict(stage=stage,oldest_size=oldest_size,
      newborn_size=newest_size,
      preview=live_state,last72_state=temperature(hot72),
      completed_state=latest_state,trend=np.sign(rising).astype(int),
      rising=rising,oldest_id=(oldstart//12),newest_id=((t-1)//12),
      prev_complete_freq=prev_complete,
      active_count=active_counts,hot72_count=hot72)
    return scores,features

def rand20(draw_id):
    h=hashlib.blake2b(f"{SEED}|{draw_id}".encode(),digest_size=8).digest()
    return np.asarray(random.Random(int.from_bytes(h,"big")).sample(range(80),20))

def report_summary(matched):
    out=[]
    for phase in STATUSES:
        rr=[r for r in matched if r["phase"]==phase]
        if not rr:continue
        base=np.asarray([r["HOT72_hits"] for r in rr],np.int16)
        rnd=np.asarray([r["RANDOM20_hits"] for r in rr],np.int16)
        for m in METHODS:
            aa=np.asarray([r[m+"_hits"] for r in rr],np.int16)
            out.append(dict(phase=phase,method=m,n=len(rr),mean20=round(float(aa.mean()),7),
              hot72=round(float(base.mean()),7),random20=round(float(rnd.mean()),7),
              delta_vs_hot72=round(float((aa-base).mean()),7),
              five_plus=int(np.sum(aa>=5)),eight_plus=int(np.sum(aa>=8)),
              nine_plus=int(np.sum(aa>=9)),ten_plus=int(np.sum(aa>=10)),
              maximum=int(aa.max())))
    return out

def group_stage(matched):
    s=[]
    for phase in STATUSES:
        for step in range(1,13):
            a=[r for r in matched if r["phase"]==phase and r["stage"]==step]
            if not a:continue
            for method in METHODS:
                own=np.array([r[method+"_hits"] for r in a],float)
                hot=np.array([r["HOT72_hits"] for r in a],float)
                s.append(dict(phase=phase,step_newborn_12=step,method=method,
                   n=len(a),mean_hits20=round(float(own.mean()),6),
                   hot72_mean20=round(float(hot.mean()),6),
                   delta_vs_hot72=round(float(np.mean(own-hot)),6),
                   count8plus=int((own>=8).sum())))
    return s

def tally_bucket(buckets):
    result=[]
    for key,arr in sorted(buckets.items()):
        phase,stage,pre_pool,prev_pool,dirn=key
        n,y=arr
        result.append(dict(phase=phase,newborn_stage=stage,
         preview_temp=POOLS[pre_pool],prior_completed72_temp=POOLS[prev_pool],
         recent_direction=dirn,occurrences=n,target_hit=y,
         observed_pct=round(100*y/n,5),reference_pct=25))
    return result

def statistics(selected,matched):
    daily=collections.defaultdict(list)
    for r in matched:
        if r["phase"]=="HOLDOUT":
            daily[r["day"]].append(r[selected+"_hits"]-r["HOT72_hits"])
    vals=np.array([np.mean(x) for x in daily.values()],float)
    center=float(vals.mean())
    width=float(1.96*vals.std(ddof=1)/np.sqrt(len(vals)))
    return center,[center-width,center+width],len(daily)

def run(source,out):
    days,rows,X,issues,bad=load(source)
    historic=days[:72]
    phase_map={day:("TRAIN" if i<36 else "VALIDATE" if i<54
                else "HOLDOUT") for i,day in enumerate(historic)}
    for d in days[72:]: phase_map[d]="NEW_DATA"
    prefix=np.vstack((np.zeros((1,80),np.int32),
                      np.cumsum(X,axis=0,dtype=np.int32)))
    matched=[]
    buckets=collections.defaultdict(lambda:[0,0])
    step_pool=collections.defaultdict(lambda:[0,0])
    movement=collections.defaultdict(lambda:[0,0])
    # Same full-batch audit as V100C but with diagnosis at EVERY ring stage.
    for t in range(START,len(X)):
        row=rows[t]; phase=phase_map[row["day"]]
        scores,f=prep(prefix,t)
        stage=f["stage"]
        y=X[t]
        top={m:top20(sc) for m,sc in scores.items()}
        hist_start=rows[t-672]["id"]
        rr=dict(phase=phase,day=row["day"],target_id=row["id"],
                target_time=row["time"],from_id=hist_start,
                newest_known_id=rows[t-1]["id"],
                stage=stage,first_old_ring=f["oldest_size"],
                sealed_rings=(56 if stage==12 else 55),
                active_rings=(56 if stage==12 else 57),
                memory=672,RANDOM20_hits=int(y[rand20(row["id"])].sum()))
        for m in METHODS:rr[m+"_hits"]=int(y[top[m]].sum())
        matched.append(rr)
        for b in range(80):
            k=(phase,stage,int(f["preview"][b]),
               int(f["completed_state"][b]),int(f["trend"][b]))
            buckets[k][0]+=1;buckets[k][1]+=int(y[b])
            h=(phase,stage,int(f["preview"][b]))
            step_pool[h][0]+=1;step_pool[h][1]+=int(y[b])
            m=(phase,stage,int(f["last72_state"][b]),
               int(f["preview"][b]))
            movement[m][0]+=1;movement[m][1]+=int(y[b])
        if (t-START)%2500==0:
            print("V101 processed",t,"/",len(X),flush=True)
    total=report_summary(matched)
    validate=[r for r in total if r["phase"]=="VALIDATE" and r["method"] in ALT]
    win=max(validate,key=lambda r:(r["delta_vs_hot72"],-ALT.index(r["method"])))
    selected=win["method"] if win["delta_vs_hot72"]>0 else "HOT72"
    daymean,CI,daynum=statistics(selected,matched)
    stage_rows=group_stage(matched)
    pool_rows=[dict(phase=ph,stage=st,temp=POOLS[pool],n=a[0],
      target_number_occurred=a[1],real_pct=round(100*a[1]/a[0],5),
      reference_pct=25)
      for (ph,st,pool),a in sorted(step_pool.items())]
    move_rows=[dict(phase=ph,stage=st,last72_pool=POOLS[p72],
       newborn_preview_pool=POOLS[p12],n=a[0],target_count=a[1],
       actual_pct=round(100*a[1]/a[0],5))
      for (ph,st,p72,p12),a in sorted(movement.items())]
    future_t=len(X)
    final_scores,final_f=prep(prefix,future_t)
    next_source=rows[-1]
    proposed={m:[int(v+1) for v in top20(f)] for m,f in final_scores.items()}
    future_rows=[]
    for n in range(80):
        future_rows.append(dict(number=n+1,
            last_observed_id=next_source["id"],last_observed_date=next_source["day"],
            next_target_id="UNKNOWN_UNOBSERVED",
            newborn_stage=final_f["stage"],oldest_ring_size=final_f["oldest_size"],
            newborn_size=final_f["newborn_size"],
            preview_temp=POOLS[int(final_f["preview"][n])],
            prior_complete_temp=POOLS[int(final_f["completed_state"][n])],
            last72_temp=POOLS[int(final_f["last72_state"][n])],
            last6_ring_direction=int(final_f["trend"][n]),
            present_in_validation_selected_20=int(n in set(top20(final_scores[selected]))),
            present_in_hot72_top20=int(n in set(top20(final_scores["HOT72"])))))
    metadata=dict(version=VERSION,recorded_draws=len(X),start_index=START,
        scored_targets=len(matched),historical_72_days=historic,
        post_oct12_draws=sum(r["phase"]=="NEW_DATA" for r in matched),
        fresh_source_last_id=next_source["id"],
        next_unseen_target_id="NOT_KNOWN",next_stage=final_f["stage"],
        models=METHODS,validation_selected=selected,
        validation_selected_delta=win["delta_vs_hot72"],
        historical_holdout_days=daynum,historical_holdout_day_mean=daymean,
        historical_holdout_95day_ci=CI,
        post_history_part_has_single_day=(
            len(set(r["day"] for r in matched if r["phase"]=="NEW_DATA"))<5),
        warnings=[
          "All 72 historical days had been studied in prior models: no virgin holdout.",
          "Recorded source ends on October 13, 2026 in present repository; do not invent Oct 14-16 draws.",
          "Next unseen target predictions only, never scored as if observed.",
          "Newborn partial-ring pool ranks are relative and have numeric tie effects.",
          "2026-10-13 new data is a small external slice and not 18-day holdout.",
          "Use prospective sealed predictions and day-level paired controls for any edge."
        ])
    val=sorted([v for v in total if v["phase"]=="VALIDATE"],
               key=lambda r:-r["delta_vs_hot72"])
    hold=next(r for r in total if r["phase"]=="HOLDOUT" and r["method"]==selected)
    hot=next(r for r in total if r["phase"]=="HOLDOUT" and r["method"]=="HOT72")
    latest=[r for r in total if r["phase"]=="NEW_DATA"]
    brief=[
      "V101 | YURUYEN HALKADA HER 1..12 CEKILIS ASAMASI / FAYDA DENETIMI",
      "V100A and V100C unchanged, no separate nested V100B.",
      f"Real draws in repo: {len(X)}. After 672+60 warmup, target count: {len(matched)}",
      f"Latest observed #{next_source['id']} / {next_source['day']} {next_source['time']}",
      f"Next (not yet observed) ring stage: {final_f['stage']}/12.",
      "Each candidate selected before knowing exact target, pooled and by stage.",
      "Each ring continuously maintains 672 known draws, no target is used.",
      "",
      "VALIDATION last-18 of training partition? Actual split: 36 days train",
      "18 days validation then 18 historical days holdout; Oct-13+ NEW_DATA.",
      "VALIDATION alternatives vs same-target HOT72:"]
    for v in val:
        brief.append(f" {v['method']:23} avg={v['mean20']:.6f} HOT72={v['hot72']:.6f} gain={v['delta_vs_hot72']:+.6f}")
    brief.extend(["",f"Validation-selected variant: {selected}",
      f"Historical HOLDOUT selected={hold['mean20']:.6f}, HOT72={hot['mean20']:.6f}, RAND20={hot['random20']:.6f}.",
      f"Gain/target={hold['delta_vs_hot72']:+.6f}",
      f"Daily paired 95% CI [{CI[0]:+.6f},{CI[1]:+.6f}], calendar days={daynum}.",
      "Target has 20 unique numbers. Fair baseline for a 20-selection = 5.0.",
      "",
      "NEW_DATA after Oct 12 (small, NOT validation-optimized):"])
    for r in sorted(latest,key=lambda z:-z["delta_vs_hot72"]):
        brief.append(f" {r['method']:23} n={r['n']} hits={r['mean20']:.6f} HOT72={r['hot72']:.6f} gain={r['delta_vs_hot72']:+.6f}")
    brief.extend(["","LAST RING PHASE HOLDOUT by newborn length (preview vs HOT72):"])
    for st in range(1,13):
        r=next(x for x in stage_rows if x["phase"]=="HOLDOUT"
             and x["method"]=="PREVIEW_POOL" and x["step_newborn_12"]==st)
        brief.append(f" {st:2}/12: n={r['n']} preview={r['mean_hits20']:.5f} HOT72={r['hot72_mean20']:.5f} gain={r['delta_vs_hot72']:+.5f}")
    brief.extend(["",
      f"Next-unknown chosen model={selected}; future 20 candidate numbers="+
      "-".join(map(str,proposed[selected])),
      "This future list is an unscored research diagnostic, not a betting recommendation.",
      "Not enough independent fresh draws to claim any predictive advantage.",
      "CSV includes each phase, transition pool, exact target and next unobserved features.",
      "No live fetch: code processes only verified draws present in veri.txt.",
      "Because of multiple prior historical searches, any new pattern is exploratory."])
    dst=Path(out);dst.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dst,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        z.writestr("00_V101_YURUYEN_HALKA_FAYDA_SONUCLARI.txt","\n".join(brief)+"\n")
        csvzip(z,"01_10_YONTEM_36_18_18_YENI_VERI.csv",total)
        csvzip(z,"02_12_ASAMA_AYRI_10_YONTEM_KONTROL.csv",stage_rows)
        csvzip(z,"03_HER_HEDEF_ONCEKI_672_SABIT_HALKA.csv",matched)
        csvzip(z,"04_HER_ASAMA_5_HAVUZDA_HEDEFTE_GELME.csv",pool_rows)
        csvzip(z,"05_72_VE_YENI_HALKA_HAVUZU_25_ESLESME.csv",move_rows)
        csvzip(z,"06_ONCEKI_HALKANIN_YONU_ILE_HAVUZ.csv",tally_bucket(buckets))
        csvzip(z,"07_SON_GERCEK_CEKILISTEN_SONRA_80_SAYI_DIAGNOSTIK.csv",future_rows)
        z.writestr("08_ONCEDEN_SABITLENMIS_GORULMEMIS_HEDEF.json",
            json.dumps(dict(last_observed_draw_id=next_source["id"],
               last_observed_date=next_source["day"],
               unobserved_next_target_id="UNKNOWN",expected_stage=final_f["stage"],
               historical_validation_chosen=selected,
               unscored_diagnostic_top20=proposed,
               freeze_before_future_draw_if_using=True),indent=2))
        z.writestr("09_VERI_VE_GERIYE_SIZMA_DENETIMI.json",
                   json.dumps(metadata,ensure_ascii=False,indent=2,default=str))
    print("\n".join(brief),flush=True)
    print("V101 FINISHED",dst,dst.stat().st_size,flush=True)

def csvzip(z,name,rows):
    if not rows:return
    with z.open(name,"w",force_zip64=True) as f:
        stream=io.TextIOWrapper(f,encoding="utf-8",newline="")
        w=csv.DictWriter(stream,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
        stream.flush();stream.detach()

def selftest():
    xx=np.zeros((770,80),dtype=np.uint8)
    for t in range(770):xx[t,(np.arange(20)+t)%80]=1
    pp=np.vstack((np.zeros((1,80),np.int32),np.cumsum(xx,axis=0,dtype=np.int32)))
    for t in (732,733,734,739,743,744,745):
        s,f=prep(pp,t)
        assert len(s)==len(METHODS) and len(f["preview"])==80
        assert f["oldest_size"]+f["newborn_size"]==24 if t%12==0 else f["oldest_size"]+f["newborn_size"]==12
        assert all(len(set(top20(x)))==20 for x in s.values())
        assert sorted(np.bincount(f["preview"],minlength=5))==[16]*5
    print("V101 SELFTEST OK",flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",default="veri.txt")
    ap.add_argument("--out",default="v101_output/V101_YURUYEN_HALKA_1_12_12_ASAMA_FAYDA_DENETIM.zip")
    ap.add_argument("--selftest",action="store_true")
    a=ap.parse_args()
    if a.selftest:selftest()
    else:run(a.source,a.out)
