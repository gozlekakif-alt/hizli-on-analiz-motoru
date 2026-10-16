#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V105 — ALL 56 ring direction chain -> next completed ring direction.

Unchanged base: original full 72 days, 15624 observed draws, initial 672,
stable GLOBAL groups of 12 and one-draw FIFO (V104). For each ring-close
boundary t=672,684,...,15612, freeze the complete 56-ring trajectory for
each of 80 numbers, then describe its NEXT ring direction AFTER that
target ring closes 12 draws later. No coupons, no 20-number hit counts.

Topics: Does prior direction repeat? What old-ring lags have influence?
Do 56-ring volatility and turn density distinguish balls with IDENTICAL
last pool and last-6 net direction? Compare early36 with late36.
A conservative descriptive cross-period Brier comparison concerns ONLY
3-way pool direction, not actual lottery draw-number forecasts. Future
direction is not claimed predictable.
"""
from __future__ import annotations
import argparse,collections,csv,io,json,math,zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load,temperature
from v104_72gun_basindan_672_56_halka_fifo_yon import stable_paths,profile,category
VER="V105.1"
POOLS=("SOGUK","SERIN","NOTR","ILIK","SICAK")
DIR=("SOGUMA","SABIT","ISINMA")
STEP={-1:"D",0:"=",1:"Y"}
CHAR="CSNIH"

def write_csv(z,name,values):
    if not values:return
    with z.open(name,"w",force_zip64=True) as stream:
        f=io.TextIOWrapper(stream,encoding="utf-8",newline="")
        writer=csv.DictWriter(f,fieldnames=list(values[0]))
        writer.writeheader();writer.writerows(values)
        f.flush();f.detach()

def make_chain(d):
    """Temporal characteristics over all 55 historical direction steps."""
    up=(d>0).sum(axis=1)
    down=(d<0).sum(axis=1)
    stable=(d==0).sum(axis=1)
    nonzero=(d!=0).sum(axis=1)
    reversal=(d[:,:-1]*d[:,1:]==-1).sum(axis=1)
    tr=np.zeros(80,np.int16)
    for j in range(80):
        path=d[j]
        turns=[int(v) for v in path if v!=0]
        tr[j]=sum(int(a!=b) for a,b in zip(turns,turns[1:]))
    age=np.full(80,55,dtype=np.int16)
    for k in range(55):
        active=(d[:,54-k]!=0)&(age==55)
        age[active]=k
    return dict(up=up,down=down,steady=stable,volume=nonzero,
                reversal=reversal,turns=tr,age=age)

def early_recent_bucket(volume):
    return np.where(volume<=24,0,np.where(volume<=34,1,2)).astype(np.int8)

def turn_class(turns):
    """Predeclared fixed descriptive bins. Not optimized on results."""
    return np.where(turns<=10,0,np.where(turns<=19,1,2)).astype(np.int8)

def train_eval(events):
    """First half direction frequencies vs next-half, by 5-state & net6.

    All 56-direction history is used via chain-volume, turn class, and
    longest old-vs-new temperature divergence. Fixed smoothing prevents
    the large number of tiny cells being interpreted as a mechanism.
    """
    base=np.zeros((5,3,3),dtype=np.int32)
    more=np.zeros((5,3,3,3),dtype=np.int32)
    turns=np.zeros((5,3,3,3),dtype=np.int32)
    age=np.zeros((5,3,3,3),dtype=np.int32)
    for a in events:
        if a["period"]!="FIRST36":continue
        p=a["last_pool_rank"]; s=a["last6_sign"]+1;y=a["next_dir_sign"]+1
        base[p,s,y]+=1
        more[p,s,a["volume_bin"],y]+=1
        turns[p,s,a["turn_bin"],y]+=1
        age[p,s,a["age_bin"],y]+=1
    pb=(base+3)/(base.sum(axis=2,keepdims=True)+9)
    def conditional(q):
        prior=pb[:,:,None,:]
        return (q+40*prior)/(q.sum(axis=3,keepdims=True)+40)
    pvolume=conditional(more)
    pturn=conditional(turns)
    page=conditional(age)
    summary=[]
    by_day=collections.defaultdict(lambda:collections.defaultdict(list))
    for a in events:
        if a["period"]!="LAST36":continue
        p=a["last_pool_rank"];s=a["last6_sign"]+1;y=a["next_dir_sign"]+1
        family=[
            ("ONLY_LAST6",pb[p,s]),
            ("FULL56_VOLUME",pvolume[p,s,a["volume_bin"]]),
            ("FULL56_TURNS",pturn[p,s,a["turn_bin"]]),
            ("FULL56_LAST_ACTIVITY",page[p,s,a["age_bin"]])]
        for name,q in family:
            score=float(np.sum(q*q)-2*q[y]+1)
            logloss=float(-np.log(max(q[y],1e-12)))
            by_day[a["day"]][name].append((score,logloss))
    allrows=collections.defaultdict(list)
    for day, methods in by_day.items():
        for method,vals in methods.items():
            sb=float(np.mean([x[0] for x in vals]))
            ll=float(np.mean([x[1] for x in vals]))
            summary.append(dict(day=day,method=method,
                  ball_ring_obs=len(vals),multiclass_brier=sb,
                  logloss=ll))
            allrows[method].extend(vals)
    methods=[]
    reference=float(np.mean([v[0] for v in allrows["ONLY_LAST6"]]))
    for method,vals in allrows.items():
        avg=float(np.mean([x[0] for x in vals]))
        methods.append(dict(method=method,test_period="LAST36",
            samples=len(vals),brier=avg,
            brier_delta_vs_last6=avg-reference,
            logloss=float(np.mean([x[1] for x in vals]))))
    return summary,methods,base,more,turns,age

def pooled_controlled_corr(counts):
    """Partial correlation of earlier ring direction and future ring
    direction, within FIXED last-pool and last6-sign strata.
    """
    c=np.asarray(counts,dtype=float) # (55, 5, 3, 3, 3)
    answers=[]
    signs=np.array([-1.,0.,1.])
    for lag in range(55):
        weighted_cov=weighted_vx=weighted_vy=0.
        count=0
        for pool in range(5):
            for net in range(3):
                mat=c[lag,pool,net] # past sign (3) x next sign (3)
                n=mat.sum()
                if n<10:continue
                px=mat.sum(axis=1)/n
                py=mat.sum(axis=0)/n
                mx=float(signs@px);my=float(signs@py)
                exy=float((signs[:,None]*signs[None,:]*mat).sum()/n)
                ex2=float((signs*signs)@px)
                ey2=float((signs*signs)@py)
                weighted_cov+=n*(exy-mx*my)
                weighted_vx+=n*(ex2-mx*mx)
                weighted_vy+=n*(ey2-my*my)
                count+=int(n)
        corr=(weighted_cov/math.sqrt(weighted_vx*weighted_vy)
              if weighted_vx>0 and weighted_vy>0 else 0.)
        answers.append(dict(lag=lag+1,
          previous_ring_relative_age=lag+1,
          directional_corr_controlled_pool_last6=corr,
          samples=count))
    return answers

def run(src,dest):
    days,rows,X,issues,bad=load(src)
    rows=rows[:15624];X=X[:15624]
    assert len(rows)==15624 and np.all(X.sum(axis=1)==20)
    n=len(rows)
    p=np.vstack((np.zeros((1,80),dtype=np.int32),np.cumsum(X,axis=0,dtype=np.int32)))
    seal=np.empty((n//12,80),np.int8)
    for ring in range(n//12):
        end=(ring+1)*12
        seal[ring]=temperature(p[end]-p[max(0,end-72)])
    all_events=[]
    perboundary=[]
    cohorts=collections.defaultdict(lambda:np.zeros(3,dtype=np.int64))
    n_lags=np.zeros((2,55,5,3,3,3),dtype=np.int64)
    transition=np.zeros((2,5,3,3),dtype=np.int64)
    latest_profile=[]
    chronology=collections.defaultdict(list)
    for t in range(672,n,12):
        gids,S,D=stable_paths(t,seal)
        assert len(gids)==56 and D.shape==(80,55)
        prof=profile(S,D)
        long=make_chain(D)
        r=t//12
        current=S[:,-1]
        nxt=seal[r]
        ns=np.sign(nxt-current).astype(np.int8)
        prior=D[:,-1]
        six=np.sign(prof["net6"]).astype(np.int8)
        vols=early_recent_bucket(long["volume"])
        turns=turn_class(long["turns"])
        # "how long since any relative pool change" bins 0,1-2,3+
        ages=np.where(long["age"]==0,0,np.where(long["age"]<=2,1,2))
        period="FIRST36" if days.index(rows[t+11]["day"])<36 else "LAST36"
        pi=0 if period=="FIRST36" else 1
        for lag in range(1,56):
            old=D[:,-lag]
            for j in range(80):
                n_lags[pi,lag-1,int(current[j]),int(six[j])+1,
                        int(old[j])+1,int(ns[j])+1]+=1
        transition[pi]+=np.bincount(
            (current.astype(np.int32)*9+
             (prior.astype(np.int32)+1)*3+
             (ns.astype(np.int32)+1)),
            minlength=45).reshape(5,3,3)
        c=collections.Counter()
        for j in range(80):
            event=dict(boundary_t=t,
                 frozen_before_next_ring_draw_id=rows[t-1]["id"],
                 label_next_ring_end_id=rows[t+11]["id"],
                 day=rows[t+11]["day"],period=period,
                 ball=j+1,last_pool=POOLS[int(current[j])],
                 last_pool_rank=int(current[j]),
                 last6_sign=int(six[j]),
                 last6_delta=int(prof["net6"][j]),
                 last12_delta=int(prof["net12"][j]),
                 first_of_56_pool=int(S[j,0]),
                 first_to_last_delta=int(S[j,-1]-S[j,0]),
                 up_full56=int(long["up"][j]),
                 down_full56=int(long["down"][j]),
                 stable_full56=int(long["steady"][j]),
                 movement_full56=int(long["volume"][j]),
                 volume_bin=int(vols[j]),total_sign_turns=int(long["turns"][j]),
                 turn_bin=int(turns[j]),adjacent_flip_count=int(long["reversal"][j]),
                 steps_since_last_change=int(long["age"][j]),
                 age_bin=int(ages[j]),
                 last_step_sign=int(prior[j]),
                 next_dir_sign=int(ns[j]),
                 next_direction=("SOGUMA" if ns[j]<0 else "ISINMA" if ns[j]>0 else "SABIT"),
                 full_56_pool_path="".join(CHAR[int(v)] for v in S[j]),
                 full_55_dir_path="".join(STEP[int(v)] for v in D[j]),
                 next_ring_12_seen=int(X[t:t+12,j].sum()))
            all_events.append(event)
            if t==n-12:latest_profile.append(event)
            key=(period,int(current[j]),int(six[j]),int(vols[j]))
            cohorts[key][int(ns[j])+1]+=1
            c["ISINMA" if ns[j]>0 else "SOGUMA" if ns[j]<0 else "SABIT"]+=1
        perboundary.append(dict(
            ring_id=r,period=period,first_draw_id=rows[t]["id"],
            last_draw_id=rows[t+11]["id"],day=rows[t+11]["day"],
            warming_count=c["ISINMA"],cooling_count=c["SOGUMA"],
            stable_count=c["SABIT"],
            **{"n":80}))
        if t%2400==0:print("V105 processed ring",r,flush=True)
    train_day,models,base,more,turn_count,age_count=train_eval(all_events)
    transition_rows=[]
    for pi,period in enumerate(("FIRST36","LAST36")):
        for pool in range(5):
            for prev in range(3):
                tab=transition[pi,pool,prev]
                nobs=int(tab.sum())
                if not nobs:continue
                transition_rows.append(dict(period=period,
                    current_pool=POOLS[pool],last_completed_step=STEP[prev-1],
                    obs=nobs,next_soguma=int(tab[0]),next_sabit=int(tab[1]),
                    next_isinma=int(tab[2]),
                    next_soguma_pct=100*tab[0]/nobs,
                    next_sabit_pct=100*tab[1]/nobs,
                    next_isinma_pct=100*tab[2]/nobs))
    lag_rows=[]
    c0=pooled_controlled_corr(n_lags[0])
    c1=pooled_controlled_corr(n_lags[1])
    for i in range(55):
        lag_rows.append(dict(lag=i+1,
            first36_corr=c0[i]["directional_corr_controlled_pool_last6"],
            last36_corr=c1[i]["directional_corr_controlled_pool_last6"],
            first36_n=c0[i]["samples"],last36_n=c1[i]["samples"],
            stable_direction_sign=(np.sign(c0[i]["directional_corr_controlled_pool_last6"])==
                         np.sign(c1[i]["directional_corr_controlled_pool_last6"]))))
    by_hist=[]
    for (period,pool,net,v),arr in sorted(cohorts.items()):
        nobs=int(arr.sum())
        if not nobs:continue
        by_hist.append(dict(period=period,latest_pool=POOLS[pool],
            last6="SOGUMA" if net<0 else "ISINMA" if net>0 else "SABIT",
            full56_volume=("AZ_HAREKET" if v==0 else
                           "ORTA_HAREKET" if v==1 else "COK_HAREKET"),
            n=nobs,after_cooling=int(arr[0]),
            after_steady=int(arr[1]),after_warming=int(arr[2]),
            warming_pct=float(arr[2]/nobs*100),
            cooling_pct=float(arr[0]/nobs*100),
            stable_pct=float(arr[1]/nobs*100)))
    paired=[]
    for pool in POOLS:
        for short in ("SOGUMA","SABIT","ISINMA"):
            for cl in ("AZ_HAREKET","ORTA_HAREKET","COK_HAREKET"):
                data=[x for x in by_hist if x["latest_pool"]==pool and
                      x["last6"]==short and x["full56_volume"]==cl]
                a=next((x for x in data if x["period"]=="FIRST36"),None)
                b=next((x for x in data if x["period"]=="LAST36"),None)
                if a and b:
                    paired.append(dict(latest_pool=pool,last6=short,full56_volume=cl,
                        first36_n=a["n"],first36_next_warming_pct=a["warming_pct"],
                        last36_n=b["n"],last36_next_warming_pct=b["warming_pct"],
                        change_pp=b["warming_pct"]-a["warming_pct"]))
    favs=sorted(lag_rows,key=lambda r:abs(r["first36_corr"]),reverse=True)
    common=[x for x in favs if x["first36_corr"]*x["last36_corr"]>0]
    mbase=next(x for x in models if x["method"]=="ONLY_LAST6")
    diff_by_model={x["method"]:x for x in models}
    nbound=len(perboundary)
    avg=np.mean([[v["warming_count"],v["cooling_count"],v["stable_count"]]
                 for v in perboundary],axis=0)
    topreps=sum(1 for x in favs[:10] if x["first36_corr"]*x["last36_corr"]>0)
    main=[
      "V105: 56 HALKA KADRO DIRECTION INFLUENCE ATLAS",
      "First 672 observed draws formed 56 rings; 12 draw absolute group IDs",
      "and 1-by-1 FIFO walking in V104 preserved exactly; NO new re-bucketing.",
      f"72 days, 15624 draws, {nbound} ring boundaries evaluated BEFORE next12 outcomes.",
      f"80 balls x boundary = {len(all_events)} individually labeled next-ring directions.",
      "",
      "WHICH MOVEMENTS REPEAT?",
      f"Mean next-ring warm/cool/stay among 80 = {avg[0]:.3f}/{avg[1]:.3f}/{avg[2]:.3f}",
      "The upper SICAK pool cannot warm further; lower SOGUK cannot cool",
      "further BY DEFINITION (relative 5-rank boundary); these must NOT be signals.",
      "Every one of the previous 55 direction STEPS is kept, including",
      "its distance to next ring, whole56 movement volume, reversals, age",
      "since last change, full pool path, and the ring's next actual direction.",
      "",
      "DOES OLD-CHAIN DIRECTION CORRELATE WITH NEXT DIRECTION",
      "AFTER HOLDING last_pool AND last6_net FIXED?",
      "Per-lag partial correlations from the FIRST36 and LAST36 periods:",
    ]
    for lag in (1,2,3,6,12,18,24,36,48,55):
        z=lag_rows[lag-1]
        main.append(f" lag={lag:2d}: first36 corr={z['first36_corr']:+.5f}; last36 corr={z['last36_corr']:+.5f}")
    main+=["",
      f"The first-half 10 strongest lag correlations kept same sign in last36: {topreps}/10.",
      "These are dependent 80-ball per-ring observations, not independent",
      "statistical proof. Direction correlations can arise mechanically",
      "because the five pools are bounded and ranks share a fixed quota.",
      "",
      "FULL56 vs ONLY-LAST6 FOR NEXT 3-WAY POOL DIRECTION:",
      f"First36 frozen frequency tables; LAST36 next-ring comparison. "
      f"Base multiclass Brier={mbase['brier']:.8f}."]
    for name in ("FULL56_VOLUME","FULL56_TURNS","FULL56_LAST_ACTIVITY"):
        d=diff_by_model[name]
        main.append(f" {name:23s} multiclass Brier={d['brier']:.8f}; "
           f"delta vs last6={d['brier_delta_vs_last6']:+.8f}")
    main.extend(["Negative delta would mean smaller direction error; positive worse.",
        "These are DIRECTION analyses, not lottery NUMBER HIT predictions.",
        "",
        "PREVIOUS V104 POOL+LAST6+FULL56 BUCKET CONTRASTS REVISITED:",
        "The CSV includes FIRST36 and LAST36 differences for identical",
        "last-pool and last6 direction groups. Do not interpret the",
        "largest historical single-group difference as universal law.",
        "",
        "FINAL CLOSED RING EXAMPLE:",
        f"Last boundary target ring starts #{rows[n-12]['id']}",
        f"and ends #{rows[n-1]['id']}; all 80 full56 histories",
        "and the actual next ring directions are in CSV 06.",
        "",
        "KEY FINDING: each ring group DOES NOT move as one; older layers",
        "can be described separately from recent layers. Future-leading",
        "value requires stable relationships across chronological periods.",
        "No coupon generation, no RNG solution or high-certainty forecast."])
    meta=dict(version=VER,source_days=72,draws=n,
        first_672_first_id=rows[0]["id"],
        first_672_last_id=rows[671]["id"],
        next_ring_boundary_examples=nbound,number_ring_examples=len(all_events),
        initial_seal_first5="provisional due to <72 observed draws",
        past_only=True,
        per_lag_control="last pool and last6 net sign",
        old_ring_gids_preserved=True,
        first_period=days[:36],last_period=days[36:72],
        next_direction_label="pool72 rank after next 12 real draws",
        no_number_hit_selection=True,
        uncertainty="Descriptive/transition calibration, historical data reused in prior studies")
    dst=Path(dest);dst.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dst,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_56_HALKA_YON_ETKI_KESIN_SONUC.txt","\n".join(main)+"\n")
        write_csv(z,"01_HER_12_TAM_HALKADA_80_SAYI_56_ZINCIR_GELECEK_YON.csv",all_events)
        write_csv(z,"02_55_ESKI_HALKANIN_GELECEK_YONLE_ILISKISI.csv",lag_rows)
        write_csv(z,"03_5_HAVUZ_SON_ADIM_GELECEK_YON_MATRISI.csv",transition_rows)
        write_csv(z,"04_56_HALKA_HAREKET_AZ_ORTA_COK_DONEM_KARSILASTIRMA.csv",by_hist)
        write_csv(z,"05_AYNI_HAVUZ_SON6_56_ZINCIR_IKI_DONEM.csv",paired)
        write_csv(z,"06_SON_TAM_HALKADA_80_SAYI_YON_FILMI.csv",latest_profile)
        write_csv(z,"07_HER_12_TAM_HALKADA_GENEL_YON_KADRO.csv",perboundary)
        write_csv(z,"08_ILK36_OGREN_SON36_YON_KALIBRASYON.csv",models)
        write_csv(z,"09_SON36_GUNLUK_YON_KALIBRASYON.csv",train_day)
        z.writestr("10_METOT_DENETIM.json",json.dumps(meta,ensure_ascii=False,
                   indent=2,default=str))
    print("\n".join(main),flush=True)
    print("V105 COMPLETE",dst,dst.stat().st_size,flush=True)

def selftest():
    tmp=np.tile(np.arange(5,dtype=np.int8).repeat(16),(80,1))
    g,S,D=stable_paths(672,tmp)
    assert S.shape==(80,56) and D.shape==(80,55)
    long=make_chain(D)
    assert np.all(long["volume"]==0)
    assert np.all(long["age"]==55)
    assert len(pooled_controlled_corr(np.zeros((55,5,3,3,3))))==55
    print("V105 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v105_output/V105_56_HALKANIN_TAM_YON_ETKISI.zip")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest()
    else:run(args.source,args.out)
