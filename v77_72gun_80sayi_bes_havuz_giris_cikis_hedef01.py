#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V77: 72 full days x 80 identities; FIVE 16-ball pools, entrances/exits,
movement across boundaries, and target-draw 80 binary 1/0 labels.

At draw t, all heat, rank, movement and entry/exit features use strictly
draws < t. Actual target 20 numbers only supply the subsequent 1/0 labels.
5 equal buckets 16 balls each based on rolling N appearance counts, cold
to hot. Tied frequencies use previous rank to minimise artificial churning.
Main detailed N=60 (user's latest proposal), comparison 42,72,217.
Explicitly FLAG the 23 Aug 2026 skipped incomplete day and EXCLUDE any
lookback / movement comparison spanning its draw-ID discontinuity.

Artifacts include:
 * all 15,624 targets × 80 binary 1/0, exactly twenty ones each;
 * all N60 eligible 80 × draw identity observations, old/new pool,
   rank, incoming/outgoing 16-member boundary, pool direction, past
   frequency, previous target label and target label;
 * 5x16 members at each target, entries and exits and target pool quotas;
 * daily flux, 5x5 and 5x3 (current temp × dir) empirical hit rates;
 * prospective-in-order staged 15 day TRAIN and 15 day HOLDOUT 30-cell
   shrinkage probability pool selector (5×4) vs seeded quota random, for
   each pre-specified N=42,60,72,217.
 This does not reconstruct RNG code or demonstrate future lottery edge.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import random
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V77.1"
HEAT=("SOGUK","SERIN","NOTR","ILIK","SICAK")
DIRECTIONS=("SOGUYOR","SABIT","ISINIYOR")
REFERENCES=(42,60,72,217)
MAIN_N=60
SHIFT=12
DAY_SIZE=217
TRAIN_START=27*DAY_SIZE
TRAIN_END=42*DAY_SIZE
VALID_END=57*DAY_SIZE
HOLD_END=72*DAY_SIZE
PRIOR_ALPHA=250
RAND_SEED=771015
ZERO_ONE_COLS=[f"sayi_{j:02d}" for j in range(1,81)]

def load(path):
    parsed,issues,malformed=parse_txt(path)
    full_days=sorted(d for d,rows in parsed.items() if
                     len(rows)==217 and
                     [r["pos"] for r in rows]==list(range(1,218)))
    if len(full_days)!=72 or full_days[0]!="2026-08-01" or full_days[-1]!="2026-10-12":
        raise RuntimeError(f"Expected 72 full days 1 Aug..12 Oct; found {len(full_days)}.")
    skipped=sorted(set(parsed)-set(full_days))
    rows=[r for d in full_days for r in parsed[d]]
    if len(rows)!=15624 or rows[-217]["id"]!=61629 or rows[-1]["id"]!=61845:
        raise RuntimeError("Wrong 72-day draw ledger.")
    labels=np.zeros((len(rows),80),dtype=np.uint8)
    for i,draw in enumerate(rows):
        labels[i,np.asarray(draw["nums"],dtype=int)-1]=1
    if not bool(np.all(labels.sum(axis=1)==20)):
        raise RuntimeError("Every target must have precisely 20 ones.")
    return full_days,rows,labels,skipped,issues,malformed

def prefixes(y):
    """Prefix[t] includes draws up to t-1, never the draw at t."""
    z=np.zeros((y.shape[0]+1,80),dtype=np.int32)
    z[1:]=np.cumsum(y,dtype=np.int32,axis=0)
    return z

def eligible_mask(draws,window):
    """True if historical [t-window,t-1] and t boundary contain no draw-ID gap."""
    ts=len(draws)
    ids=np.fromiter((r["id"] for r in draws),dtype=np.int32,count=ts)
    gap=np.zeros(ts,dtype=np.int16)
    gap[1:]=(np.diff(ids)!=1).astype(np.int16)
    cum=np.r_[0,np.cumsum(gap,dtype=np.int32)]
    ok=np.zeros(ts,dtype=bool)
    for t in range(window,ts):
        # Relevant seams at indices (t-window+1 .. t) inclusive.
        ok[t]=(cum[t+1]-cum[t-window+1]==0)
    return ok,gap,ids

def quintile_history(prefix,n):
    """Rolling stable frequency-tie ranking, computed strictly before each target."""
    sz=prefix.shape[0]-1
    temp=np.full((sz,80),255,dtype=np.uint8)
    rank=np.zeros((sz,80),dtype=np.uint8)
    freq=np.zeros((sz,80),dtype=np.uint16)
    number=np.arange(80,dtype=int)
    old_rank=number.copy()
    tie_bound=np.zeros(sz,dtype=np.uint8)
    for t in range(n,sz):
        f=prefix[t]-prefix[t-n]
        order=np.lexsort((old_rank,f))
        inverse=np.empty(80,dtype=np.int16)
        inverse[order]=np.arange(80)
        q=inverse//16
        temp[t]=q.astype(np.uint8)
        rank[t]=(inverse+1).astype(np.uint8)
        freq[t]=f.astype(np.uint16)
        old_rank=inverse
        tie_bound[t]=sum(int(f[order[j-1]]==f[order[j]])
                         for j in (16,32,48,64))
        if __debug__ and t%1200==0:
            assert np.array_equal(np.bincount(q,minlength=5),[16]*5)
    return temp,rank,freq,tie_bound

def signal_class(cur,old12,old1):
    move=np.where(cur>old12,2,np.where(cur<old12,0,1)).astype(np.uint8)
    entered=(cur!=old1).astype(np.uint8)
    # group 30 states, including 5 current quintiles, 3 directions,
    # and 2 flags for "entered a different 16-member group this step".
    return ((cur.astype(np.uint8)*3+move)*2+entered),move,entered

def trained_probability(states,y,elig,alpha):
    choose=np.where(elig)[0]
    if not len(choose):
        raise RuntimeError("Empty training window.")
    st=states[choose]
    target=y[choose]
    n=np.bincount(st.reshape(-1),minlength=30).astype(np.int64)
    success=np.bincount(st.reshape(-1),weights=target.reshape(-1),
                        minlength=30).astype(np.int64)
    p=(success+alpha*.25)/(n+alpha)
    return p,n,success

def pick_20(current,states,probs,rand):
    rank_score=probs[states]+rand*1e-9
    choose=np.zeros((len(current),80),dtype=np.uint8)
    for q in range(5):
        allowed=np.where(current==q,rank_score,-10.)
        idx=np.argpartition(allowed,-4,axis=1)[:,-4:]
        choose[np.arange(len(current))[:,None],idx]=1
    assert np.all(choose.sum(axis=1)==20)
    for q in range(5):
        assert np.all((choose*(current==q)).sum(axis=1)==4)
    return choose

def compare_paired(a,b,y):
    hits_a=(a*y).sum(axis=1).astype(int)
    hits_b=(b*y).sum(axis=1).astype(int)
    replacement=(20-(a*b).sum(axis=1)).astype(int)
    variance=float((2*replacement*.25*.75*80/79).sum())
    z=float((hits_a-hits_b).sum())/math.sqrt(variance) if variance>0 else 0
    return dict(model_mean=round(float(hits_a.mean()),6),
                control_mean=round(float(hits_b.mean()),6),
                advantage=round(float((hits_a-hits_b).mean()),6),
                paired_z=round(z,5),
                p_one_sided_model_better=round(.5*math.erfc(z/math.sqrt(2)),7),
                model_7plus=int((hits_a>=7).sum()),
                model_8plus=int((hits_a>=8).sum()),
                model_9plus=int((hits_a>=9).sum()),
                model_10plus=int((hits_a>=10).sum()),
                model_total=int(hits_a.sum()),
                control_total=int(hits_b.sum()))

def writer_gz(z,name,header,rows,level=4):
    """Stream large CSV compressed inside one downloadable ZIP."""
    with z.open(name,"w",force_zip64=True) as raw:
        with gzip.GzipFile(fileobj=raw,mode="wb",compresslevel=level) as gz:
            text=io.TextIOWrapper(gz,encoding="utf-8",newline="")
            out=csv.writer(text)
            out.writerow(header)
            for line in rows:out.writerow(line)
            text.flush()
            text.detach()

def writer_csv(z,name,rows,columns=None):
    if columns is None:
        if not rows:raise ValueError("No rows for "+name)
        columns=list(rows[0])
    with z.open(name,"w",force_zip64=True) as raw:
        text=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        out=csv.DictWriter(text,fieldnames=columns)
        out.writeheader()
        out.writerows(rows)
        text.flush()
        text.detach()

def binary_rows(draws,y):
    for i,d in enumerate(draws):
        yield [d["day"],d["time"],d["id"],d["pos"],*map(int,y[i])]

def identity_rows(draws,y,temp,rank,freq,valid):
    """Full 80-ball ledger: target 1/0 is the OUTCOME, not a predictor."""
    N=MAIN_N
    for t in range(len(draws)):
        if t<N:continue
        q=temp[t]
        old1=temp[t-1] if t>N else np.full(80,255,dtype=np.uint8)
        old12=temp[t-SHIFT] if t>=N+SHIFT else np.full(80,255,dtype=np.uint8)
        for b in range(80):
            now=int(q[b]); prev=int(old1[b]);old=int(old12[b])
            sh1=now-prev if prev!=255 else None
            sh12=now-old if old!=255 else None
            direction=("ISINIYOR" if sh12>0 else
                       "SOGUYOR" if sh12<0 else "SABIT") if sh12 is not None else ""
            yield [draws[t]["day"],draws[t]["time"],draws[t]["id"],draws[t]["pos"],
                   b+1,int(freq[t,b]),HEAT[now],int(rank[t,b]),
                   int(rank[t,b])%16 if int(rank[t,b])%16 else 16,
                   HEAT[prev] if prev!=255 else "",
                   HEAT[old] if old!=255 else "",
                   sh1,sh12,int(prev!=255 and now!=prev),
                   int(old!=255 and now!=old),direction,
                   int(y[t-1,b]) if t>0 else None,
                   int(y[t,b]),int(valid[t])]

def pool_draw_rows(draws,y,temp,rank,valid):
    for t in range(MAIN_N,len(draws)):
        q=temp[t]
        prior=temp[t-1] if t>MAIN_N else None
        total_hits=[]
        row=[draws[t]["day"],draws[t]["time"],draws[t]["id"],
             draws[t]["pos"],int(valid[t]),','.join(map(str,draws[t]["nums"]))]
        for k in range(5):
            members=sorted(int(b)+1 for b in np.flatnonzero(q==k))
            assert len(members)==16
            entrants=(sorted(int(b)+1 for b in np.flatnonzero((q==k)&(prior!=k)))
                      if prior is not None else [])
            exits=(sorted(int(b)+1 for b in np.flatnonzero((prior==k)&(q!=k)))
                   if prior is not None else [])
            assert len(entrants)==len(exits)
            qty=int(y[t,q==k].sum())
            total_hits.append(qty)
            row += [','.join(map(str,members)),','.join(map(str,entrants)),
                    ','.join(map(str,exits)),len(entrants),qty]
        assert sum(total_hits)==20
        yield row

def build_summary(draws,labels,prefix,main_temp,main_rank,main_freq,main_ties,
                  valid_main,temps_by_n,valid_by_n,ids,gaps):
    size=len(draws)
    earliest=MAIN_N+SHIFT
    category_op=np.zeros((5,3,2),dtype=np.int64)
    category_hit=np.zeros((5,3,2),dtype=np.int64)
    per_transition=np.zeros((5,5),dtype=np.int64)
    hit_transition=np.zeros((5,5),dtype=np.int64)
    binpos_op=np.zeros((5,16),dtype=np.int64)
    binpos_hit=np.zeros((5,16),dtype=np.int64)
    daily=[]
    validtotal=0
    balanced=0
    target_quota_sum=np.zeros(5,dtype=np.int64)
    total_entry=total_exit=0
    first_last_01=np.zeros((2,2),dtype=np.int64)
    near_edge_occ=near_edge_hits=0
    interior_occ=interior_hits=0
    count_valid_by_day=defaultdict(int)
    for day_num in range(72):
        i0=day_num*DAY_SIZE;i1=i0+DAY_SIZE
        dayn=0;dayentry=0;dayhot=0;daycold=0
        dayboth=0;daymax=0;daydir=np.zeros((3,),dtype=int)
        for t in range(i0,i1):
            if not valid_main[t]:continue
            q=main_temp[t]
            prior=main_temp[t-1]
            before=main_temp[t-SHIFT]
            target=labels[t]
            validtotal+=1;dayn+=1
            target_ones=np.bincount(q[target==1],minlength=5)
            target_quota_sum+=target_ones
            dayhot+=int(target_ones[4]);daycold+=int(target_ones[0])
            balanced+=int(np.all(target_ones==4))
            changed=q!=prior
            enters=int(np.count_nonzero(changed))
            total_entry+=enters;total_exit+=enters
            dayentry+=enters
            dirs=np.where(q>before,2,np.where(q<before,0,1)).astype(np.uint8)
            for d in range(3):daydir[d]+=int((dirs==d).sum())
            current_pos=(main_rank[t].astype(np.int16)-1)%16
            near=np.isin(main_rank[t],np.array([14,15,16,17,18,30,31,32,
                             33,34,46,47,48,49,50,62,63,64,65,66],
                             dtype=np.uint8))
            near_edge_occ+=int(near.sum());near_edge_hits+=int(target[near].sum())
            interior_occ+=int((~near).sum());interior_hits+=int(target[~near].sum())
            for qi in range(5):
                for di in range(3):
                    for en in range(2):
                        mask=(q==qi)&(dirs==di)&(changed==bool(en))
                        category_op[qi,di,en]+=int(mask.sum())
                        category_hit[qi,di,en]+=int(target[mask].sum())
                for old in range(5):
                    mask=(q==qi)&(before==old)
                    per_transition[old,qi]+=int(mask.sum())
                    hit_transition[old,qi]+=int(target[mask].sum())
                for rankpos in range(16):
                    mask=(q==qi)&(current_pos==rankpos)
                    binpos_op[qi,rankpos]+=1
                    binpos_hit[qi,rankpos]+=int(target[mask].sum())
            old=labels[t-1]
            for a in range(2):
                for b in range(2):
                    first_last_01[a,b]+=int(np.count_nonzero((old==a)&(target==b)))
        daily.append(dict(day=draws[i0]["day"],draws_in_raw_day=217,
           eligible_consecutive_targets=dayn,
           all_80_target_positive=217*20,
           total_eligible_16pool_entries=dayentry,
           avg_per_draw_entry_identities=round(dayentry/dayn,5) if dayn else None,
           hot16_target_mean=round(dayhot/dayn,5) if dayn else None,
           cold16_target_mean=round(daycold/dayn,5) if dayn else None,
           shift12_cooling_id_count=int(daydir[0]),
           shift12_stable_id_count=int(daydir[1]),
           shift12_rising_id_count=int(daydir[2]),
           target_20_never_leaks_into_features=True))
    transition=[]
    for old in range(5):
        for new in range(5):
            q=int(per_transition[old,new]);hit=int(hit_transition[old,new])
            transition.append(dict(old_pool=HEAT[old],new_pool=HEAT[new],
              identity_draw_count=q,actual_target_ones=hit,zeros=q-hit,
              actual_one_percent=round(100*hit/q,5) if q else None,
              independent_fair_expected_one_percent=25.0))
    classes=[]
    for qi in range(5):
        for d in range(3):
            for enter in range(2):
                n=int(category_op[qi,d,enter]);h=int(category_hit[qi,d,enter])
                classes.append(dict(current_pool=HEAT[qi],
                    movement12=DIRECTIONS[d],
                    came_from_other_16_pool_last_step=enter,
                    candidate_number_draws=n,
                    target_ones=h,target_zeros=n-h,
                    target_one_rate_percent=round(100*h/n,5) if n else None,
                    fair_expected_percent=25.0))
    edge=[]
    for q in range(5):
        for within in range(16):
            n=int(binpos_op[q,within]);hit=int(binpos_hit[q,within])
            edge.append(dict(pool=HEAT[q],position_in_16=within+1,
                candidate_number_draws=n,target_ones=hit,
                target_zeros=n-hit,
                target_one_percent=round(100*hit/n,5) if n else None))
    binarytrans=[]
    for old in range(2):
        for new in range(2):
            count=int(first_last_01[old,new])
            binarytrans.append(dict(previous_draw_0_or_1=old,
              target_draw_0_or_1=new,occurrences=count))
    activity=[]
    for N in REFERENCES:
        ti=temps_by_n[N];vm=valid_by_n[N]
        results=[]
        changed_sum=0
        qhits=np.zeros(5,dtype=np.int64)
        ready=int(vm.sum())
        count_unchanged=0
        for t in np.flatnonzero(vm):
            q=ti[t]
            changed_sum+=int(np.count_nonzero(q!=ti[t-1]))
            count_unchanged+=int(np.count_nonzero(q==ti[t-1]))
            qhits+=np.bincount(q[labels[t]==1],minlength=5)
        activity.append(dict(lookback_draws=N,
            valid_uninterrupted_target_draws=ready,
            mean_last_step_pool_entries=round(changed_sum/ready,5) if ready else None,
            mean_all_five_pool_target_ones=','.join(str(round(v/ready,5))
                                                    for v in qhits) if ready else None,
            total_unchanged_ball_state=count_unchanged))
    return dict(daily=daily,transition=transition,classes=classes,edge=edge,
        binarytrans=binarytrans,activity=activity,
        valid_targets=validtotal,balanced=balanced,
        entry_total=total_entry,exit_total=total_exit,
        pool_sum=target_quota_sum.tolist(),
        near_edge_count=near_edge_occ,near_edge_hits=near_edge_hits,
        interior_count=interior_occ,interior_hits=interior_hits,
        one_zero=first_last_01.tolist())

def learn_test(draws,y,tier,valid,n):
    """Predefined training 15 days, validation 15 days, holdout 15 days;
    no tuning to validation or holdout. Excludes gaps.
    """
    old12=np.roll(tier,SHIFT,axis=0)
    old1=np.roll(tier,1,axis=0)
    states,move,entered=signal_class(tier,old12,old1)
    train_mask=valid & (np.arange(len(draws))>=TRAIN_START) & (
        np.arange(len(draws))<TRAIN_END)
    probs,ncounts,nhits=trained_probability(states,y,train_mask,PRIOR_ALPHA)
    rng=np.random.default_rng(RAND_SEED)
    results=[]
    all_tickets=[]
    for phase,start,end in [
        ("VALIDATE",TRAIN_END,VALID_END),
        ("HOLDOUT",VALID_END,HOLD_END)]:
        relevant=np.arange(start,end)[valid[start:end]]
        if not len(relevant):raise ValueError("No valid targets for "+phase)
        current=tier[relevant]
        st=states[relevant]
        random_noise=rng.random((len(relevant),80))
        chosen=pick_20(current,st,probs,random_noise)
        balanced=pick_20(current,current,np.ones(5)*.25,random_noise)
        pp=compare_paired(chosen,balanced,y[relevant])
        results.append(dict(reference_N=n,phase=phase,
             train_targets=int(train_mask.sum()),
             eval_targets=len(relevant),**pp))
        if phase=="HOLDOUT" and n==MAIN_N:
            for i,t in enumerate(relevant):
                row=draws[t];c=current[i];ytrue=y[t];sel=chosen[i]
                line=dict(day=row["day"],draw_id=row["id"],clock=row["time"],
                     target1_count=int(ytrue.sum()),
                     selected20=",".join(str(int(b)+1) for b in np.flatnonzero(sel)),
                     selected20_hits=int((sel*ytrue).sum()),
                     matched_random_hits=int((balanced[i]*ytrue).sum()),
                     **{f"chosen_{HEAT[q].lower()}":
                        ",".join(str(int(b)+1) for b in np.flatnonzero(sel&(c==q)))
                        for q in range(5)})
                all_tickets.append(line)
    state_prob=[]
    for q in range(5):
        for di in range(3):
            for en in range(2):
                k=(q*3+di)*2+en
                state_prob.append(dict(reference_N=n,
                  current_pool=HEAT[q],shift12=DIRECTIONS[di],
                  entered_other_pool_last_draw=en,
                  train_opportunities=int(ncounts[k]),
                  train_actual_ones=int(nhits[k]),
                  fixed_train_probability=round(float(probs[k]),9)))
    return results,state_prob,all_tickets

def main(source,out):
    full_days,draws,y,skipped,issues,malformed=load(source)
    sz=len(draws)
    prefix=prefixes(y)
    gap_lists=[]
    for i in range(1,sz):
        if draws[i]["id"]!=draws[i-1]["id"]+1:
            gap_lists.append(dict(before_day=draws[i-1]["day"],
                  after_day=draws[i]["day"],before_id=draws[i-1]["id"],
                  after_id=draws[i]["id"],
                  skipped_id_count=draws[i]["id"]-draws[i-1]["id"]-1))
    rank_by_n={}
    valid_by_n={}
    tie_by_n={}
    freq_by_n={}
    for n in REFERENCES:
        tiers,ranks,freq,ties=quintile_history(prefix,n)
        valid,gap,ids=eligible_mask(draws,n+SHIFT)
        rank_by_n[n]=(tiers,ranks)
        freq_by_n[n]=freq if n==MAIN_N else None
        tie_by_n[n]=ties
        valid_by_n[n]=valid
        print(f"V77 rolling {n} sorted tiers: "
              f"ready N+12={int(valid.sum())} uninterrupted target rows",flush=True)
    main_tier,main_rank=rank_by_n[MAIN_N]
    main_freq=freq_by_n[MAIN_N]
    valid_main=valid_by_n[MAIN_N]
    inventory=build_summary(draws,y,prefix,main_tier,main_rank,main_freq,
       tie_by_n[MAIN_N],valid_main,{n:rank_by_n[n][0] for n in REFERENCES},
       valid_by_n,ids,gap_lists)
    trained=[]
    params=[]
    test_tickets=[]
    for n in REFERENCES:
        results,learned,tickets=learn_test(draws,y,rank_by_n[n][0],
                                           valid_by_n[n],n)
        trained+=results
        params+=learned
        test_tickets+=tickets
        print("V77 train+valid+holdout",n,
              [(r["phase"],r["model_mean"],r["control_mean"]) for r in results],
              flush=True)
    holdout=[r for r in trained if r["phase"]=="HOLDOUT"]
    daily=inventory["daily"]
    n_main=int(valid_main.sum())
    theoretical_bal=math.comb(16,4)**5/math.comb(80,20)
    mean_entries=inventory["entry_total"]/n_main
    n60=[r for r in holdout if r["reference_N"]==60][0]
    res=[
        "V77 — 72 TAM GUN, 80 SAYI, BES 16'LIK HAVUZ, GIRIS/CIKIS VE HEDEF 1/0",
        f"Complete full days: {len(full_days)}; complete historical draws: {len(draws)}.",
        f"Days not complete and excluded from 72 day full-day series: {skipped}.",
        f"ID gap between full days: {gap_lists}.",
        "TARGET LABELS = actual hit (1) / actual miss (0), 80 identities per draw.",
        f"Exactly 20 ones and 60 zeros per target, all {len(draws)} target records.",
        "Historical movement features always timestamped BEFORE each target draw.",
        "Causality: rank 80 balls by PRIOR N draw frequency, split into 5 bins of 16.",
        "Tied frequencies retain prior ordering to avoid arbitrary swap churn.",
        f"Full detail lookback N={MAIN_N} draws; number expected frequency={MAIN_N/4:.2f}.",
        "For each target track: current 16-person bin, rank 1..80, prev bin",
        "one target earlier, old bin 12 targets earlier, 16-bin entry/exit,",
        "past movement +/−, past 0/1, current target 0/1.",
        f"Valid target rows for n60 plus 12 direction and no ID gaps = {n_main}.",
        f"Total 16-bin entries per single-step across valid main records: {inventory['entry_total']}.",
        f"AVERAGE 80-identity in/out pool crossings per target: {mean_entries:.5f}.",
        "By construction exact five groups of 16, every entry equals an exit.",
        f"TARGET 20 actual perfect 4/4/4/4/4 occurrences = {inventory['balanced']}/{n_main}.",
        f"Fair random perfect balance expected about {theoretical_bal*n_main:.2f} draws "
          f"({theoretical_bal*100:.4f}% of draws).",
        f"Actual target average 1s across cold/cool/neutral/warm/hot groups = "
           +"/".join(f"{x/n_main:.5f}" for x in inventory["pool_sum"])
           +" (fair expectation 4.00000 in each).",
        f"Near any internal 16-bin boundary (±2 positions), target hit rate="
          f"{100*inventory['near_edge_hits']/inventory['near_edge_count']:.5f}% "
          f"({inventory['near_edge_hits']}/{inventory['near_edge_count']}).",
        f"Remaining interior ranks hit rate="
          f"{100*inventory['interior_hits']/inventory['interior_count']:.5f}% "
          f"({inventory['interior_hits']}/{inventory['interior_count']}).",
        "",
        "80-bit TARGET ONE/ZERO FOLLOW-ON (previous draw label → target draw label):",
    ]
    for o in inventory["binarytrans"]:
        res.append(f"{o['previous_draw_0_or_1']}->{o['target_draw_0_or_1']} "
                   f"observations={o['occurrences']}")
    res+=["","LOOKBACK SENSITIVITY (movement details available in CSV):"]
    for a in inventory["activity"]:
        res.append(f"N={a['lookback_draws']}: target valid={a['valid_uninterrupted_target_draws']}; "
                   f"mean entrants={a['mean_last_step_pool_entries']}; "
                   f"target distribution={a['mean_all_five_pool_target_ones']}")
    res+=["","FIXED TRAINING (15 days), VALIDATE (15 days), HOLDOUT (15 days) 5x4 RULE:"]
    for r in trained:
        res.append(f"N={r['reference_N']}, {r['phase']}: "
            f"observations={r['eval_targets']}, model={r['model_mean']:.5f}, "
            f"quota-random={r['control_mean']:.5f},"
            f" difference={r['advantage']:+.5f}, paired one-sided p={r['p_one_sided_model_better']:.5f}")
    res+=["",
       "CAUTION / INTERPRETATION:",
       "At each target the 80 1/0 labels are OUTCOMES, not inputs.",
       "The 16-bin entry / exit counts are rank-group reassignments, NOT proof RNG control.",
       "Past movement may be descriptive without forecasting unseen future draws.",
       "Even chronologically held-out dates were repeatedly explored in V68..V76.",
       "This is an exploratory system, not a verified betting strategy.",
       "",
       "Single ZIP: 15624x80 true target binary CSV.GZ; ~1.25M rows of per-ball",
       "pool membership/rank/movement and target binary; each draw's full",
       "5x16 members with entrance/exit lists; daily movement counts; 5x5/5x3",
       "frequency-to-target 0/1 matrices; 16 within-pool rank hit rates;",
       "previous-target-0/1 versus current-target-0/1; N42/60/72/217 crosschecks;",
       "15+15+15 stage pool predictions and real target hit summaries.",
       ""]
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as z:
        z.writestr("00_KISA_SONUC_V77.txt","\n".join(res),
                   compress_type=zipfile.ZIP_DEFLATED)
        writer_gz(z,"01_72_GUN_15624_CEKILIS_80_SAYI_HEDEF_1_0.csv.gz",
                  ["tarih","saat","cekilis_no","gun_sira"]+ZERO_ONE_COLS,
                  binary_rows(draws,y))
        writer_gz(z,"02_72_GUN_80_SAYI_N60_HAVUZ_GIRIS_CIKIS_YON_HEDEF_1_0.csv.gz",
           ["tarih","saat","cekilis_no","gun_sira","sayi",
            "son60_cikis","mevcut_havuz","genel_sira_1_80",
            "havuz_icindeki_sira_1_16","bir_onceki_havuz",
            "12_cekilis_onceki_havuz","1_adim_yon_farki",
            "12_adim_yon_farki","son_adimda_havuza_girdi_1_0",
            "12_adimda_havuz_degistirdi_1_0","12_adim_yon",
            "onceki_ceklis_hedef_1_0","hedef_ceklis_1_0",
            "gecmis_kesintisiz_1_0"],
           identity_rows(draws,y,main_tier,main_rank,main_freq,valid_main))
        inv_header=["tarih","saat","cekilis_no","gun_sira",
                    "gecmis_kesintisiz_1_0","hedef_20_sayi"]+[x for q in HEAT for x in
                       (f"{q.lower()}_16_uye",f"{q.lower()}_girenler",
                        f"{q.lower()}_cikanlar",f"{q.lower()}_giren_sayisi",
                        f"{q.lower()}_hedef_1_sayisi")]
        writer_gz(z,"03_HER_CEKILIS_BES_HAVUZ_16_UYE_GIREN_CIKAN_HEDEF20.csv.gz",
                  inv_header,pool_draw_rows(draws,y,main_tier,main_rank,valid_main))
        for filename,rows in (
          ("04_GUNLUK_72_GUN_GIRIS_CIKIS_20_SONUC.csv",daily),
          ("05_ESKI_YENI_HAVUZ_5x5_1_0_GECIS.csv",inventory["transition"]),
          ("06_BES_HAVUZ_YON_3_GIRIS_2_HEDEF_1_0.csv",inventory["classes"]),
          ("07_HER_HAVUZ_ICI_SIRA_1_16_HEDEF_ISABET.csv",inventory["edge"]),
          ("08_ONCEKI_CEKILIS_HEDEF_1_0_GECIS.csv",inventory["binarytrans"]),
          ("09_REFERANS_42_60_72_217_GIRIS_CIKIS_VE_HEDEF.csv",inventory["activity"]),
          ("10_TRAIN_15GUN_VALID_15GUN_TEST_15GUN_KOTALI_20LI.csv",trained),
          ("11_TRAIN_OGRENILEN_5x3x2_30_YON_GIRIS_ORANI.csv",params),
          ("12_REFERANS60_KILITLI_20LI_TEST_GUNLERI.csv",test_tickets)):
            writer_csv(z,filename,rows)
        z.writestr("13_YONTEM_VE_KISITLAR.txt","\n".join([
           "Reference here: last 60 PREVIOUS draws, 5 equal 16-ball frequency tiers.",
           "Comparison references 42,72,217. 72 DAYS refers to complete date sample.",
           "Before target t: previous N draw frequency; ties keep previous rank.",
           "Outgoing / incoming defines transition between latest target-boundary pools.",
           "Old and new 16-ball member identities listed before target results arrive.",
           "Direction(t)=pool(t) minus pool(t-12), entry(t)=pool(t) != pool(t-1).",
           "Positive direction means hotward, negative means coldward.",
           "Every actual target has 20 ones and 60 zeros (80 binary labels).",
           "Labels are outcomes, never used in their own prior feature calculation.",
           "23 Aug invalid/missing 2 input rows; its entire 217-draw day excluded.",
           "A break of 217 ids in 72 complete-day sequence occurs 22 Aug -> 24 Aug.",
           "For valid transition statistics, require no ID gaps in N+12 history+target.",
           "All tabular full ledgers annotate whether previous N+12 has no missing draw.",
           "First N+12 available history draw indices are excluded from movement tests.",
           "Frequency tie stability reduces arbitrary oscillation across pool boundaries.",
           "Empirical transition percentage = sum target 1 / all eligible number-draw states.",
           "For fixed independent lottery model, each number's probability always 1/4.",
           "30-cell score is trained on 29Aug..12Sep, with 250 pseudocounts at prior .25.",
           "Model frozen on 13Sep..27Sep validation and 28Sep..12Oct holdout.",
           "The 30 states comprise (current thermal pool, direction12, entry step 1/0).",
           "Choose 4 of 16 in each current pool, highest learned P(target 1|state).",
           "When scores tie, use seeded random tie-breaking.",
           "Control chooses unbiased 4 of 16 from each current pool with same seed.",
           "Paired null controls correlated predictions using their candidate-set overlap.",
           "These 72 days previously examined in many versions; prospective proof absent.",
           "RNG mechanism/code cannot be inferred from heat labels.",
           "ZIP contains detailed CSV.GZ and smaller CSV: decompress GZ to read CSV."
        ]),compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("14_AUDIT.json",json.dumps(dict(version=VERSION,
            full_days=full_days,days_skipped=skipped,
            gap_boundaries=gap_lists,records=len(draws),
            binary_ones=int(y.sum()),binary_zeros=int(y.size-y.sum()),
            main_N=MAIN_N,direction_shift=SHIFT,other_references=REFERENCES,
            valid_consecutive_references=inventory["valid_targets"],
            inout_per_eligible_draw=mean_entries,
            target_five_quota_actual_distribution=inventory["pool_sum"],
            exact_target_four_each=inventory["balanced"],
            reference20_predictions=trained,
            parse_issues=issues[:30],malformed_rows=malformed[:30]),
            indent=2,ensure_ascii=False),compress_type=zipfile.ZIP_DEFLATED)
    print("\n".join(res),flush=True)
    print("V77 ZIP",out,"bytes",out.stat().st_size,flush=True)

def selftest():
    rng=np.random.default_rng(77)
    y=np.zeros((500,80),dtype=np.uint8)
    for t in range(len(y)):
        y[t,rng.choice(80,20,replace=False)]=1
    assert bool(np.all(y.sum(axis=1)==20))
    pp=prefixes(y)
    tiers,ranks,freq,ties=quintile_history(pp,60)
    assert np.array_equal(np.bincount(tiers[499],minlength=5),[16]*5)
    cur=tiers[72:];prev=tiers[60:-12];prev1=tiers[71:-1]
    st,d,en=signal_class(cur,prev,prev1)
    assert st.max()<30 and st.shape==cur.shape
    probs,count,hits=trained_probability(st,y[72:],np.ones(len(st),dtype=bool),250)
    assert len(probs)==30 and count.sum()==len(st)*80
    noise=rng.random(cur.shape)
    picks=pick_20(cur,st,probs,noise)
    assert np.all(picks.sum(axis=1)==20)
    assert all(np.all((picks*(cur==q)).sum(axis=1)==4) for q in range(5))
    print("V77 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v77_output/V77_72_GUN_80_SAYI_5x16_GIRIS_CIKIS_YON_HEDEF_1_0.zip")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:selftest()
    else:main(a.source,a.out)
