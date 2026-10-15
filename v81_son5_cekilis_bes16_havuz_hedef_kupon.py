#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V81 — USER REQUEST: build the 5×16 hot/cold pools using ONLY the PREVIOUS
FIVE draws, and test observed 20-ball targets and real 10-ball coupons.

Key epistemic caveat: In five 20-of-80 draws there are just 100 appearances.
Most 80 identities tie at 0,1,2 appearances. A tie-break is compulsory to
manufacture exactly five groups of sixteen; fixed, seeded identity priority
is used. This remains a deterministic function of last FIVE draws plus a
globally fixed prior ID permutation, not earlier results. Other tie choices
are tested for robustness, not retuning.

Experiments:
 N5, direction lookback lag L = 1,2,3,5 preceding target snapshots;
 FREE (globally highest 10/20) vs BALANCED (top 2/4 per 16 group);
 a fixed N60, L6, FREE anchor recalculated under identical tie logic;
 all results compared to matched fair pre-target random tickets.
 Train 29 Aug–12 Sep, validation 13–27 Sep, locked holdout 28 Sep–12 Oct,
 plus next Oct 13 first consecutive 112 targets only.
 Strict target independence: previous-draw tiers, directions, scores only;
 actual target Y is measured after choices are locked.

We use rank-based 5x16 groups but also provide target1 rate by exact prior
five-draw frequency 0..5, which avoids the equal-count boundary artifacts.
No claim of RNG prediction is warranted without genuinely new dates.
"""
from __future__ import annotations
import argparse,csv,gzip,io,json,math,zipfile
from pathlib import Path
from collections import defaultdict
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VER="V81.1"
MAIN=5
LAGS=(1,2,3,5)
METHODS=("FREE","BALANCED")
BASE_N=60;BASE_LAG=6;BASE_METHOD="FREE"
ALPHA=250
SEED=811015
DAY=217
TRAIN=27*DAY
VALID=42*DAY
HOLD=57*DAY
END=72*DAY
POOLS=("SOGUK","SERIN","NOTR","ILIK","SICAK")
DIRECTIONS=("SOGUYOR","SABIT","ISINIYOR")

def input_data(path):
    buckets,issues,malformed=parse_txt(path)
    dates=sorted(k for k,v in buckets.items() if
       len(v)==DAY and [d["pos"] for d in v]==list(range(1,DAY+1)))
    if len(dates)!=72 or dates[0]!="2026-08-01" or dates[-1]!="2026-10-12":
        raise RuntimeError(f"Expected 72 full days: got {len(dates)}")
    historical=[row for date in dates for row in buckets[date]]
    if len(historical)!=15624 or historical[-1]["id"]!=61845:
        raise RuntimeError("Historical boundary changed")
    oct13=buckets.get("2026-10-13",[])
    extra=[]
    for row in oct13:
        if row["id"]!=historical[-1]["id"]+1+len(extra):break
        extra.append(row)
    if len(extra)<100:raise RuntimeError("Not enough consecutive Oct13 targets")
    known={r["id"] for r in oct13}
    missing=[i for i in range(oct13[0]["id"],oct13[-1]["id"]+1) if i not in known]
    rows=historical+extra
    actual=np.zeros((len(rows),80),dtype=np.uint8)
    for i,r in enumerate(rows):
        actual[i,np.asarray(r["nums"],dtype=int)-1]=1
    assert np.all(actual.sum(axis=1)==20)
    return dates,rows,actual,extra,len(oct13),missing,issues,malformed

def prefix(y):
    p=np.zeros((len(y)+1,80),dtype=np.int32)
    p[1:]=np.cumsum(y,dtype=np.int32,axis=0)
    return p

def tie_key(seed,mode="seeded"):
    if mode=="number":
        return np.arange(80,dtype=np.int16)
    if mode=="reverse":
        return np.arange(79,-1,-1,dtype=np.int16)
    perm=np.random.default_rng(seed).permutation(80)
    inv=np.empty(80,dtype=np.int16)
    inv[perm]=np.arange(80,dtype=np.int16)
    return inv

def ranks(p,N,tie):
    """All 5×16 groups independently depend on prior N draws + FIXED ID tie order."""
    out=np.full((p.shape[0]-1,80),255,dtype=np.uint8)
    for t in range(N,len(out)):
        appearance=p[t]-p[t-N]
        order=np.lexsort((tie,appearance))
        group_rank=np.empty(80,dtype=np.uint8)
        group_rank[order]=np.arange(80,dtype=np.uint8)
        out[t]=group_rank
    return out

def intact_mask(rows,N,lag):
    ids=np.array([r["id"] for r in rows],dtype=np.int32)
    bad=np.r_[0,(np.diff(ids)!=1).astype(np.int32)]
    cum=np.r_[0,np.cumsum(bad)]
    ok=np.zeros(len(rows),dtype=bool)
    required=N+lag
    for t in range(required,len(rows)):
        ok[t]=cum[t+1]-cum[t-required+1]==0
    return ok

def state_and_tier(rr,ix,L):
    cur=rr[ix]//16
    before=rr[ix-L]//16
    recent=rr[ix-1]//16
    direction=np.where(cur>before,2,np.where(cur<before,0,1)).astype(np.uint8)
    entrant=(cur!=recent).astype(np.uint8)
    st=((cur*3+direction)*2+entrant).astype(np.uint8)
    assert st.min()>=0 and st.max()<30
    return cur,before,recent,direction,entrant,st

def learn(st,y):
    n=np.bincount(st.reshape(-1),minlength=30).astype(np.int64)
    hit=np.bincount(st.reshape(-1),weights=y.reshape(-1),
                    minlength=30).astype(np.float64)
    return (hit+.25*ALPHA)/(n+ALPHA),n,hit

def predict(cur,st,p,noise,mode,k):
    score=p[st]+noise*1e-9
    chosen=np.zeros(cur.shape,dtype=np.uint8)
    idx=np.arange(len(cur))[:,None]
    if mode=="FREE":
        top=np.argpartition(score,-k,axis=1)[:,-k:]
        chosen[idx,top]=1
    elif mode=="BALANCED":
        assert k%5==0
        per=k//5
        for q in range(5):
            score_q=np.where(cur==q,score,-2.)
            top=np.argpartition(score_q,-per,axis=1)[:,-per:]
            assert np.all(cur[idx,top]==q)
            chosen[idx,top]=1
    else:raise ValueError(mode)
    assert np.all(chosen.sum(axis=1)==k)
    return chosen

def pairhit(sel,randomsel,yy,k):
    h=(sel*yy).sum(axis=1).astype(int)
    b=(randomsel*yy).sum(axis=1).astype(int)
    miss=k-(sel*randomsel).sum(axis=1)
    variance=float(np.sum(2*miss*.25*.75*80/79))
    z=(int(h.sum())-int(b.sum()))/math.sqrt(variance) if variance>0 else 0.
    fairvar=k*.25*.75*(80-k)/79
    fairz=(int(h.sum())-.25*k*len(h)-.5)/math.sqrt(fairvar*len(h))
    return dict(observations=len(h),mean=round(float(h.mean()),7),
      random_mean=round(float(b.mean()),7),
      diff=round(float((h-b).mean()),7),
      total_hits=int(h.sum()),fair_expected=.25*k,
      one_sided_fair_p=round(.5*math.erfc(fairz/math.sqrt(2)),7),
      one_sided_paired_p=round(.5*math.erfc(z/math.sqrt(2)),7),
      hits4plus=int((h>=4).sum()),hits5plus=int((h>=5).sum()),
      hits6plus=int((h>=6).sum()),hits7plus=int((h>=7).sum()),
      hits8plus=int((h>=8).sum()),hits9plus=int((h>=9).sum()),
      hits10=int((h>=10).sum())),h,b

def util(h,ix):
    ds=np.unique(ix//DAY)
    daymeans=np.array([h[ix//DAY==d].mean() for d in ds])
    var=float(np.std(daymeans,ddof=1)) if len(ds)>1 else 0.
    return float(h.mean()-.25*var),var

def save_csv(z,name,rows):
    if not rows:return
    with z.open(name,"w",force_zip64=True) as raw:
        stream=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        w=csv.DictWriter(stream,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
        stream.flush();stream.detach()

def save_gz(z,name,header,rows):
    with z.open(name,"w",force_zip64=True) as raw:
        with gzip.GzipFile(fileobj=raw,mode="wb",compresslevel=4) as gz:
            tx=io.TextIOWrapper(gz,encoding="utf-8",newline="")
            w=csv.writer(tx)
            w.writerow(header)
            for row in rows:w.writerow(row)
            tx.flush();tx.detach()

def features(y,p,rows,rr,indices,lag,N):
    cur,old,recent,dir_,entered,st=state_and_tier(rr,indices,lag)
    frequency=(p[indices]-p[indices-N]).astype(np.uint8)
    return dict(ix=indices,cur=cur,old=old,recent=recent,
                direction=dir_,entered=entered,states=st,frequency=frequency)

def describe_tiers(records,y,p,rr,valid):
    """Raw 72-day five-draw outcomes for all classes/frequencies/directions."""
    targets=np.flatnonzero(valid[:END])
    exact_freq=np.zeros((6,2),dtype=np.int64)
    poolfreq=np.zeros((5,6,2),dtype=np.int64)
    poolhit=np.zeros((5,2),dtype=np.int64)
    updown=np.zeros((3,2),dtype=np.int64)
    steptrans=np.zeros((5,5,2),dtype=np.int64)
    tied_boundaries=np.zeros(4,dtype=np.int64)
    entrants=0
    full_5freq_hist=np.zeros((6,),dtype=np.int64)
    daily=[]
    for t in targets:
        f=p[t]-p[t-MAIN]
        q=rr[t]//16
        prev=rr[t-1]//16
        past=rr[t-MAIN]//16
        d=np.where(q>past,2,np.where(q<past,0,1)).astype(np.uint8)
        yy=y[t]
        entrants+=int(np.count_nonzero(q!=prev))
        for freq in range(6):
            mask=f==freq
            exact_freq[freq,1]+=int(yy[mask].sum())
            exact_freq[freq,0]+=int(mask.sum()-yy[mask].sum())
            full_5freq_hist[freq]+=int(mask.sum())
        for qval in range(5):
            qmask=q==qval
            poolhit[qval,1]+=int(yy[qmask].sum())
            poolhit[qval,0]+=int(qmask.sum()-yy[qmask].sum())
            for freq in range(6):
                mask=qmask&(f==freq)
                poolfreq[qval,freq,1]+=int(yy[mask].sum())
                poolfreq[qval,freq,0]+=int(mask.sum()-yy[mask].sum())
            for other in range(5):
                mask=qmask&(prev==other)
                steptrans[other,qval,1]+=int(yy[mask].sum())
                steptrans[other,qval,0]+=int(mask.sum()-yy[mask].sum())
        for dval in range(3):
            mask=d==dval
            updown[dval,1]+=int(yy[mask].sum())
            updown[dval,0]+=int(mask.sum()-yy[mask].sum())
        # pool-boundary frequencies tie, so the tie-key decides these memberships
        ordered=np.sort(f)
        for i,boundary in enumerate((16,32,48,64)):
            tied_boundaries[i]+=int(ordered[boundary-1]==ordered[boundary])
    assert int(poolhit[:,1].sum())==len(targets)*20
    def csvrows(array,axes):
        out=[]
        for ix in np.ndindex(array.shape[:-1]):
            miss,h=map(int,array[ix])
            n=miss+h
            row={names:v for names,v in zip(axes,ix)}
            row.update(target1=h,target0=miss,count=n,
              target1_percent=round(100*h/n,6) if n else None,
              fair_expectation_percent=25.)
            out.append(row)
        return out
    poolrows=csvrows(poolhit,("pool_index",))
    for row in poolrows:row["pool_index"]=POOLS[row["pool_index"]]
    freqrows=csvrows(exact_freq,("past_5_draw_appearance",))
    mixrows=csvrows(poolfreq,("pool_index","past_5_draw_appearance"))
    for row in mixrows:row["pool_index"]=POOLS[row["pool_index"]]
    movrows=csvrows(updown,("direction5",))
    for row in movrows:row["direction5"]=DIRECTIONS[row["direction5"]]
    entries=csvrows(steptrans,("old_pool","new_pool"))
    for row in entries:
        row["old_pool"]=POOLS[row["old_pool"]]
        row["new_pool"]=POOLS[row["new_pool"]]
    return dict(targets=int(len(targets)),entrants=int(entrants),
      average_entrants=float(entrants/len(targets)),
      pool=poolrows,frequency=freqrows,mix=mixrows,directions=movrows,
      transitions=entries,boundary_ties=tied_boundaries.tolist(),
      boundary_tie_percent=(tied_boundaries/len(targets)*100).tolist())

def snapshots(rows,y,p,rr,valid):
    for t in np.flatnonzero(valid[:END]):
        count=p[t]-p[t-MAIN]
        cur=rr[t]//16
        prev=rr[t-1]//16
        past=rr[t-MAIN]//16
        s=rows[int(t)]
        result=[s["day"],s["time"],s["id"],s["pos"],
            ",".join(map(str,np.flatnonzero(y[t])+1))]
        for group in range(5):
            members=np.flatnonzero(cur==group)
            assert len(members)==16
            entering=np.flatnonzero((cur==group)&(prev!=group))
            leaving=np.flatnonzero((cur!=group)&(prev==group))
            drawn=np.flatnonzero((cur==group)&(y[t]==1))
            result.extend([
              ",".join(map(str,members+1)),
              ",".join(map(str,entering+1)),
              ",".join(map(str,leaving+1)),
              int(len(drawn)),
              ",".join(map(str,drawn+1))])
        yield result

def main_data(source,out):
    dates,rows,y,nextday,next_total,missing,issues,malformed=input_data(source)
    pp=prefix(y)
    tie=tie_key(SEED)
    rk5=ranks(pp,MAIN,tie)
    rk60=ranks(pp,BASE_N,tie)
    valid5=intact_mask(rows,MAIN,MAIN)
    stats=describe_tiers(rows,y,pp,rk5,valid5)
    rg=np.random.default_rng(SEED+1)
    noise=rg.random((len(rows)-TRAIN,80))
    stages=dict(TRAIN=np.arange(TRAIN,VALID),
        VALIDATE=np.arange(VALID,HOLD),
        HOLDOUT=np.arange(HOLD,END),
        NEXT_DAY=np.arange(END,len(rows)))
    for k,idx in stages.items():
        assert np.all(rk5[idx]<80) and np.all(rk60[idx]<80)
    dataset={}
    records=[]
    model_rates=[]
    for L in LAGS:
        ftrain=features(y,pp,rows,rk5,stages["TRAIN"],L,MAIN)
        probabilities,n,nh=learn(ftrain["states"],y[stages["TRAIN"]])
        for q in range(5):
            for d in range(3):
                for e in range(2):
                    k=(q*3+d)*2+e
                    model_rates.append(dict(N=MAIN,L=L,pool=POOLS[q],
                         move=DIRECTIONS[d],entry_last_draw=e,
                         opportunities=int(n[k]),target_ones=int(nh[k]),
                         shrink_probability=round(float(probabilities[k]),8)))
        for phase in ("VALIDATE","HOLDOUT","NEXT_DAY"):
            idx=stages[phase]
            f=features(y,pp,rows,rk5,idx,L,MAIN)
            scores=probabilities
            no=noise[idx-TRAIN]
            for mode in METHODS:
                ten=predict(f["cur"],f["states"],scores,no,mode,10)
                twenty=predict(f["cur"],f["states"],scores,no,mode,20)
                random10=predict(f["cur"],f["cur"],
                  np.ones(5)*.25,no,mode,10)
                random20=predict(f["cur"],f["cur"],
                  np.ones(5)*.25,no,mode,20)
                assert not (ten & ~twenty).any()
                ms10,h10,rh10=pairhit(ten,random10,y[idx],10)
                ms20,h20,rh20=pairhit(twenty,random20,y[idx],20)
                u,sd=util(h10,idx)
                drec=dict(reference_draws=MAIN,direction_lag=L,
                    policy=mode,phase=phase,selection_utility=round(u,7),
                    across_days_sd=round(sd,7),
                    coupon10_avg=ms10["mean"],
                    control10_avg=ms10["random_mean"],
                    coupon10_gain=ms10["diff"],
                    coupon10_paired_p=ms10["one_sided_paired_p"],
                    coupon10_fair_p=ms10["one_sided_fair_p"],
                    coupon10_6plus=ms10["hits6plus"],
                    coupon10_7plus=ms10["hits7plus"],
                    coupon10_8plus=ms10["hits8plus"],
                    coupon10_9plus=ms10["hits9plus"],
                    coupon10_10of10=ms10["hits10"],
                    candidate20_avg=ms20["mean"],
                    control20_avg=ms20["random_mean"],
                    candidate20_gain=ms20["diff"],
                    candidate20_paired_p=ms20["one_sided_paired_p"],
                    target_draws=len(idx))
                records.append(drec)
                dataset[(L,mode,phase)]=dict(idx=idx,feature=f,
                     t10=ten,t20=twenty,r10=random10,r20=random20,
                     h10=h10,h20=h20,hr10=rh10,hr20=rh20)
        print(f"V81 N=5 lag={L} test complete",flush=True)
    chosen=sorted([r for r in records if r["phase"]=="VALIDATE"],
        key=lambda r:(-r["selection_utility"],-r["candidate20_avg"],
            r["direction_lag"],METHODS.index(r["policy"])))[0]
    lockkey=(chosen["direction_lag"],chosen["policy"])
    locked_test=next(r for r in records if r["phase"]=="HOLDOUT" and
        (r["direction_lag"],r["policy"])==lockkey)
    locked_next=next(r for r in records if r["phase"]=="NEXT_DAY" and
        (r["direction_lag"],r["policy"])==lockkey)
    # Reference comparator: same tie, same stages, fixed N60 L6 FREE.
    baseprob,_,_=learn(
       features(y,pp,rows,rk60,stages["TRAIN"],BASE_LAG,BASE_N)["states"],
       y[stages["TRAIN"]])
    baseline=[]
    for phase in ("VALIDATE","HOLDOUT","NEXT_DAY"):
        idx=stages[phase]
        f=features(y,pp,rows,rk60,idx,BASE_LAG,BASE_N)
        no=noise[idx-TRAIN]
        ten=predict(f["cur"],f["states"],baseprob,no,"FREE",10)
        twenty=predict(f["cur"],f["states"],baseprob,no,"FREE",20)
        control10=predict(f["cur"],f["cur"],np.ones(5)*.25,no,"FREE",10)
        control20=predict(f["cur"],f["cur"],np.ones(5)*.25,no,"FREE",20)
        result10,_,_=pairhit(ten,control10,y[idx],10)
        result20,_,_=pairhit(twenty,control20,y[idx],20)
        baseline.append(dict(phase=phase,reference_draws=BASE_N,
            direction_lag=BASE_LAG,policy="FREE",
            avg10=result10["mean"],control10=result10["random_mean"],
            avg20=result20["mean"],control20=result20["random_mean"],
            coupon10_paired_p=result10["one_sided_paired_p"],
            coupon10_10of10=result10["hits10"],draws=len(idx)))
    # Freeze L and mode, but test how much tiny data TIES decide 5x16 labels.
    tie_robustness=[]
    chosenL,chosenMode=lockkey
    for tname,tie2 in (("SEED_811015",tie),
        ("SAYI_ARTAN",tie_key(SEED,"number")),
        ("SAYI_AZALAN",tie_key(SEED,"reverse")),
        ("IKINCI_SABIT_KARMA",tie_key(141015))):
        rr=rk5 if tname=="SEED_811015" else ranks(pp,MAIN,tie2)
        tr=features(y,pp,rows,rr,stages["TRAIN"],chosenL,MAIN)
        prob,_,_=learn(tr["states"],y[stages["TRAIN"]])
        f=features(y,pp,rows,rr,stages["HOLDOUT"],chosenL,MAIN)
        no=noise[stages["HOLDOUT"]-TRAIN]
        a=predict(f["cur"],f["states"],prob,no,chosenMode,10)
        b=predict(f["cur"],f["cur"],np.ones(5)*.25,no,chosenMode,10)
        m,_,_=pairhit(a,b,y[stages["HOLDOUT"]],10)
        tie_robustness.append(dict(fixed_lag=chosenL,
            fixed_policy=chosenMode,tiebreak=tname,
            mean10=m["mean"],random10=m["random_mean"],
            mean_minus_random=m["diff"],
            p_paired=m["one_sided_paired_p"]))
    tickets=[]
    for phase in ("HOLDOUT","NEXT_DAY"):
        a=dataset[(chosenL,chosenMode,phase)]
        for j,t in enumerate(a["idx"]):
            this=rows[int(t)]
            freq=a["feature"]["frequency"][j]
            pool=a["feature"]["cur"][j]
            sel10=a["t10"][j];sel20=a["t20"][j]
            row=dict(day=this["day"],time=this["time"],
                     draw_no=this["id"],day_slot=this["pos"],
                     frozen_N=MAIN,frozen_lag=chosenL,
                     frozen_policy=chosenMode,
                     coupon10=",".join(map(str,np.flatnonzero(sel10)+1)),
                     coupon10_hits=int(a["h10"][j]),
                     random10_hits=int(a["hr10"][j]),
                     candidate20=",".join(map(str,np.flatnonzero(sel20)+1)),
                     candidate20_hits=int(a["h20"][j]),
                     random20_hits=int(a["hr20"][j]),
                     actual_target20=",".join(map(str,np.flatnonzero(y[t])+1)))
            for q in range(5):
                row[f"all16_{POOLS[q].lower()}"]=",".join(
                  map(str,np.flatnonzero(pool==q)+1))
                row[f"selected10_{POOLS[q].lower()}"]=",".join(
                  map(str,np.flatnonzero((pool==q)&(sel10==1))+1))
            tickets.append(row)
    # 5-draw real target1+0 for all 80 identities, with crossing/shape direction.
    def all_identities():
        ix=np.flatnonzero(valid5[:END])
        for t in ix:
            f=pp[t]-pp[t-MAIN]
            cur=rk5[t]//16
            prev=rk5[t-1]//16
            old=rk5[t-MAIN]//16
            step=cur.astype(np.int16)-prev.astype(np.int16)
            delta=cur.astype(np.int16)-old.astype(np.int16)
            rec=rows[int(t)]
            for b in range(80):
                yield [rec["day"],rec["time"],rec["id"],b+1,
                   int(f[b]),POOLS[int(cur[b])],
                   int(rk5[t,b]%16)+1,
                   POOLS[int(prev[b])],int(step[b]),
                   POOLS[int(old[b])],int(delta[b]),
                   DIRECTIONS[2 if delta[b]>0 else 0 if delta[b]<0 else 1],
                   int(cur[b]!=prev[b]),int(y[t,b])]
    summary=[
      "V81 — SON 5 CEKILISLE 80 SAYININ BES 16'LIK HAVUZU",
      "User requested that the HEAT POOLS themselves use just the prior FIVE draws.",
      f"Corpus: {len(dates)} complete days, 15624 targets Aug1–Oct12.",
      f"Next day Oct13 contiguous {len(nextday)} of {next_total} records; missing ids {missing}.",
      "At every target t, each 80 identity's frequency in drawings t-5...t-1",
      "ranks exactly five hot/cold buckets of 16. Target t NEVER used to sort.",
      "Appearance count possible 0,1,2,3,4,5; expected each ball 1.25/5.",
      "COUNT TIES ARE PREVALENT: equal appearance counts are broken by one",
      "globally fixed ID permutation; 5x16 boundaries may be ARBITRARY.",
      "Also test fixed ascending, descending, second ID permutation ties.",
      f"Valid uninterrupted N5+lag5 target snapshots={stats['targets']}.",
      f"Mean ball identity changes pool per target={stats['average_entrants']:.5f}.",
      "At any 20/80 target, fair expected target1 among any 16 pool=4.",
      "Actual target1 means per pool:"
    ]
    for r in stats["pool"]:
        summary.append(f"  {r['pool_index']:7}: "
             f"mean1={r['target1']/stats['targets']:.5f}, "
             f"target1-rate={r['target1_percent']:.5f}%")
    summary+=["","HISTORICAL FREQUENCY 0..5 IN PREVIOUS FIVE DRAWS:"]
    for r in stats["frequency"]:
        summary.append(f"   count={r['past_5_draw_appearance']}: "
           f"targets1={r['target1']}, opportunities={r['count']}, "
           f"target1-rate={r['target1_percent']:.5f}%")
    summary+=["",
      "HOW OFTEN A GROUP BOUNDARY SPLITS NUMBERS WITH SAME COUNT:"]
    for i,count in enumerate(stats["boundary_ties"]):
        summary.append(f"  after rank {16*(i+1)}: "
                      f"{count}/{stats['targets']} "
                      f"= {stats['boundary_tie_percent'][i]:.2f}%")
    summary+=["",
      "VALIDATION (10/10 coupon mean; fair expected 2.50000):"]
    for r in sorted((rr for rr in records if rr["phase"]=="VALIDATE"),
                    key=lambda x:(x["direction_lag"],x["policy"])):
        summary.append(f"N5 L={r['direction_lag']} {r['policy']:8}: "
           f"coupon10={r['coupon10_avg']:.5f}, "
           f"random10={r['control10_avg']:.5f}, "
           f"pool20={r['candidate20_avg']:.5f}")
    summary+=["",
      f"FROZEN BY VALIDATION: N5/L={chosenL}/{chosenMode},"
      f" coupon10={chosen['coupon10_avg']:.5f},pool20={chosen['candidate20_avg']:.5f}.",
      f"HOLDOUT 3255: coupon10={locked_test['coupon10_avg']:.5f},"
      f" matched random={locked_test['control10_avg']:.5f},"
      f" delta={locked_test['coupon10_gain']:+.5f},"
      f" paired p={locked_test['coupon10_paired_p']:.6f};"
      f" 10/10={locked_test['coupon10_10of10']}.",
      f"HOLDOUT 3255: candidate20={locked_test['candidate20_avg']:.5f},"
      f" random20={locked_test['control20_avg']:.5f},"
      f" delta={locked_test['candidate20_gain']:+.5f}.",
      f"NEXT 13Oct 112: coupon10={locked_next['coupon10_avg']:.5f},"
      f" random={locked_next['control10_avg']:.5f},"
      f" 20={locked_next['candidate20_avg']:.5f},"
      f" random20={locked_next['control20_avg']:.5f}.",
      "",
      "FIXED N60/L6 FREE ANCHOR (same tie order, separate train fit):"]
    for r in baseline:
        summary.append(f"  {r['phase']}: coupon10={r['avg10']:.5f}"
            f" random10={r['control10']:.5f},"
            f" pool20={r['avg20']:.5f}"
            f" random20={r['control20']:.5f}")
    summary+=["",
      "N5 tied-frequency rankings SENSITIVITY to four fixed tie methods:"
    ]
    for r in tie_robustness:
        summary.append(f"  {r['tiebreak']}: coupon10={r['mean10']:.5f}"
                       f" random10={r['random10']:.5f},"
                       f" difference={r['mean_minus_random']:+.5f}")
    summary+=["",
      "SCIENCE: five-draw buckets are especially underdetermined because",
      "many ball identities have exactly the same past-five hit count.",
      "The arbitrary tie breaks can change which 16-ball group gets an ID.",
      "A 10-number coupon chosen BEFORE a fair 20/80 draw expects 2.5 hits.",
      "A chosen 20-number pool expects 5.0 hits regardless of heat group.",
      "This data set and 13Oct records previously explored many times;",
      "apparent historical differences are not prospective proof.",
      "Report one preselected candidate for genuinely NEW unseen targets."
    ]
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as z:
        z.writestr("00_V81_BES_CEKILIS_KISA_SONUC.txt","\n".join(summary),
                   compress_type=zipfile.ZIP_DEFLATED)
        for name,rec in [
            ("01_BES_HAVUZ_HER_BIRININ_HEDEF_1_0.csv",stats["pool"]),
            ("02_SON5_GERCEK_CIKMA_0_5_EKSIKSIZ.csv",stats["frequency"]),
            ("03_HAVUZ_X_SON5_CIKMA_X_HEDEF_1_0.csv",stats["mix"]),
            ("04_YON_5_CEKILIS_ONCESI_HEDEF_1_0.csv",stats["directions"]),
            ("05_HAVUZ_ONCEKI_YENI_5X5_GIRIS_HEDEF1_0.csv",stats["transitions"]),
            ("06_TUM_5_YON_ALT_ARALIGI_VAL_HOLD_13EKIM_KUPON10_20.csv",records),
            ("07_60_CEKILIS_REFERANS_ALTERNATIF_KUPON_ISABET.csv",baseline),
            ("08_ESIT_FREKANS_BAGLAMA_TURU_DAYANIKLILIK.csv",tie_robustness),
            ("09_5_CEKILIS_30_DURUM_OGRENILEN_1_0_ORAN.csv",model_rates),
            ("10_BES_CEKILIS_KILITLI_KURAL_TAM_KUPONLAR.csv",tickets)]:
            save_csv(z,name,rec)
        header=["day","clock","draw_id","day_slot","actual_target20"]
        for gr in POOLS:
            header+= [f"{gr}_16_all",f"{gr}_new_members",f"{gr}_outgoing",
                 f"{gr}_target1_count",f"{gr}_target1_numbers"]
        save_gz(z,"11_72GUN_HER_CEKILIS_BES_16LIK_HAVUZ_20_HEDEF.csv.gz",
                header,snapshots(rows,y,pp,rk5,valid5))
        save_gz(z,"12_72GUN_80_SAYI_GERCEK_5LI_HAVUZ_YON_HEDEF_1_0.csv.gz",
             ["day","clock","draw_id","number","appearances_last5",
               "current_16_pool","rank_inside16","previous_draw_16_pool",
               "last_step_pool_delta","pool_5_draws_earlier",
               "five_draw_pool_delta","heat_direction5",
               "entered_pool_last_step","actual_target1_0"],
             all_identities())
        z.writestr("13_KURAL_METOT.txt","\n".join([
          "Five last DRAWINGS (NOT five whole days) define the thermal pools.",
          "For each pre-target time t appearance count is in [t-5,t) only.",
          "There are 100 ball appearances total in these five draws.",
          "80 balls get raw counts 0..5; group them in a sorted order into",
          "five exactly equal groups of 16. TIES resolved using a fixed seed",
          "identity permutation, independent of earlier draw data.",
          "In a five-draw window, severe count ties make rank boundaries arbitrary.",
          "Group features before target: current tier, direction over lag L,",
          "did ball enter another 16-member tier since prior draw.",
          "TRAIN 29Aug–12Sep estimates 30 target1 conditional rates, alpha250.",
          "VALIDATE 13–27Sep selects one of 8 N5 lag x policy combos.",
          "HOLDOUT 28Sep–12Oct keeps selected combo frozen.",
          "10-ball coupon is always included in chosen 20-ball candidate set.",
          "10-ball fair expected hits 2.5, 20-ball pool expected hits 5.",
          "Compare FREE rank top10/top20 and BALANCED quota2/quota4 per tier.",
          "Matched random controls use exact same quota and tie seeds.",
          "October 13 has missing draws #61958 and #61972, after first112 stop.",
          "The full 72-day archive excludes 23Aug incomplete records.",
          "Any 72-day descriptive target with missing last10 draws is excluded.",
          "Full 10-day rolling movement study N5+lag5 excludes draw-ID gap.",
          "Four tie-break rules are audited for frozen N5 model robustness.",
          "Historical splits have been re-used many times; not new evidence.",
          "RNG cannot be inferred from historical appearance ranking alone."
        ]),compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("14_AUDIT.json",json.dumps(dict(
          version=VER,reference_main=MAIN,lag_variants=LAGS,mode_variants=METHODS,
          full_days=dates,training_days=dates[27:42],
          validation_days=dates[42:57],holdout_days=dates[57:72],
          partial13oct=len(nextday),partial_total=next_total,missing13oct=missing,
          tie_seed=SEED,reference_anchor=(BASE_N,BASE_LAG,BASE_METHOD),
          frozen=(MAIN,chosenL,chosenMode),
          val_winner=chosen,holdout_winner_frozen=locked_test,
          nextday_winner_frozen=locked_next,all_results=records,
          frequency_boundary_ties=stats["boundary_tie_percent"],
          tie_sensitivity=tie_robustness,invalid=malformed[:12],
          parse_warnings=issues[:12]),indent=2,ensure_ascii=False),
          compress_type=zipfile.ZIP_DEFLATED)
    print("\n".join(summary),flush=True)
    print("V81 OUTPUT ZIP",out,str(out.stat().st_size),flush=True)

def selftest():
    rng=np.random.default_rng(815)
    y=np.zeros((250,80),dtype=np.uint8)
    for t in range(250):y[t,rng.choice(80,20,replace=False)]=1
    p=prefix(y)
    h=ranks(p,MAIN,tie_key(SEED))
    for t in range(6,len(y)):
        rr=h[t]
        assert np.array_equal(np.bincount(rr//16,minlength=5),[16]*5)
        # strictly 5 previous draws, not including draw t
        f=p[t]-p[t-5]
        ids=np.lexsort((tie_key(SEED),f))
        assert np.array_equal(np.argsort(rr),ids)
    for L in LAGS:
        ix=np.arange(10,220)
        cur,old,rec,d,e,st=state_and_tier(h,ix,L)
        prob,n,hits=learn(st,y[ix])
        no=rng.random(cur.shape)
        for mode in METHODS:
            ten=predict(cur,st,prob,no,mode,10)
            twenty=predict(cur,st,prob,no,mode,20)
            assert np.all((ten&~twenty)==0)
            assert np.all(ten.sum(axis=1)==10)
    print("V81 SELFTEST OK",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",default="veri.txt")
    parser.add_argument("--out",default="v81_output/V81_72GUN_SON5CEKILIS_BES_16LIK_HAVUZ_ISABET_TEST.zip")
    parser.add_argument("--selftest",action="store_true")
    args=parser.parse_args()
    if args.selftest:selftest()
    else:main_data(args.source,args.out)
