#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V83: Learn 80-number routes through 36 prior 12-draw transitions of
five 16-number hot/cold pools, for a ONE precommitted 10-number coupon
contained in a 20-number candidate pool BEFORE each next 12-draw block.

At block start t:
 q_j(number) = 16-number frequency quintile using ONLY previous 434
 consecutive draws before t - 432 + 12*j, j=0..36.
 Thus 37 PRE-BLOCK rank snapshots and 36 full twelve-draw transitions.
 Score each ball solely from q_0..q_36, before seeing ANY of y[t:t+12].
 Within each complete 217-draw day, 18 x12 blocks are anchored at slots
 2..13,14..25,...,206..217. The first daily draw stays unused.
 Each 12-draw block uses ONE coupon for all its targets.

Train from all eligible 01Aug..12Sep days (exclude the missing-day gap,
 no examples with incomplete 866 prior draw history), validation on
 13..27Sep, frozen holdout 28Sep..12Oct. Models and policies determined
 by validation; report all diagnostic alternatives without choosing a
 holdout winner. Fair expectation 2.5 / 10 and 5 / 20.

Important: these dates were previously examined by many versions;
 this is a retrospective chronological split, NOT unseen prospective proof.
"""
from __future__ import annotations
import argparse,csv,io,json,math,zipfile
from collections import Counter
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V83.1"
HIST=434
LAG=12
MOVE_STEPS=36
BACK=MOVE_STEPS*LAG
REQUIRED=HIST+BACK
DAY=217
N_DAYS=72
T_VAL=42
T_TEST=57
POOL=("SOGUK","SERIN","NOTR","ILIK","SICAK")
POLICIES=("FREE","BALANCED")
MODELS=("POOL5","LAST30","THREND45","AGE60","PHASE135",
        "JOURNEY240","REVERSAL180")
MODEL_SIZE=dict(POOL5=5,LAST30=30,THREND45=45,AGE60=60,
                PHASE135=135,JOURNEY240=240,REVERSAL180=180)
ALPHA=350
SEED=831015

def read(source):
    buckets,issues,bad=parse_txt(source)
    dates=sorted(d for d,r in buckets.items()
          if len(r)==217 and [x["pos"] for x in r]==list(range(1,218)))
    if len(dates)!=72 or dates[0]!="2026-08-01" or dates[-1]!="2026-10-12":
        raise RuntimeError(f"Expected 72 complete days: {len(dates)} {dates[:2]}")
    rows=[x for d in dates for x in buckets[d]]
    if len(rows)!=15624 or rows[-1]["id"]!=61845:
        raise RuntimeError("Source bounds not expected")
    y=np.zeros((len(rows),80),dtype=np.uint8)
    for i,rec in enumerate(rows):
        y[i,np.asarray(rec["nums"],dtype=int)-1]=1
    assert np.all(y.sum(axis=1)==20)
    ids=np.array([r["id"] for r in rows],dtype=np.int32)
    p=np.zeros((len(rows)+1,80),dtype=np.int32)
    p[1:]=np.cumsum(y,axis=0,dtype=np.int32)
    return dates,rows,y,ids,p,issues,bad

def ranks(y,p):
    total=len(y)
    r=np.full((total+1,80),255,dtype=np.uint8)
    prior=np.arange(80,dtype=np.uint8)
    for t in range(HIST,total+1):
        counts=p[t]-p[t-HIST]
        ordered=np.lexsort((prior,counts))
        now=np.empty(80,dtype=np.uint8)
        now[ordered]=np.arange(80,dtype=np.uint8)
        r[t]=now
        prior=now
    return r

def valid_blocks(rows,ids,ranks_array):
    """Eligible t has all of [t-866,t+12) consecutive true draw IDs."""
    bad=np.r_[0,(np.diff(ids)!=1).astype(np.int32)]
    cumulative=np.r_[0,np.cumsum(bad)]
    blocks=[]
    removed=Counter()
    for day in range(72):
        for k in range(18):
            t=day*DAY+1+12*k  # daily final block positions 206..217
            end=t+12
            if end>(day+1)*DAY or end>len(rows):
                removed["past_day_boundary"]+=1
                continue
            start=t-REQUIRED
            if start<0:
                removed["less_than_866_prior_drawings"]+=1
                continue
            # Bad boundary b at b marks ID[b] != ID[b-1].
            # Need IDs from start through end-1 all consecutive.
            if cumulative[end]-cumulative[start+1]!=0:
                removed["broken_draw_id_history"]+=1
                continue
            snaps=t-BACK+np.arange(MOVE_STEPS+1)*LAG
            if np.any(ranks_array[snaps]>=80):
                removed["snapshot_not_initialized"]+=1
                continue
            blocks.append((t,day,k))
    return blocks,removed

def phi(path,r_t,r_prev):
    """Seven predeclared 36-trajectory feature families.
    path = [37 snapshots x 80 balls] from 432 to 0 draws before target block."""
    group=path[-1].astype(np.uint16)
    previous=path[-2].astype(np.uint16)
    previous_three=path[-4].astype(np.uint16)
    first=path[0].astype(np.uint16)
    direction=np.where(group>previous,2,np.where(group<previous,0,1)).astype(np.uint16)
    direction3=np.where(group>previous_three,2,
        np.where(group<previous_three,0,1)).astype(np.uint16)
    long=np.where(group>first,2,np.where(group<first,0,1)).astype(np.uint16)
    stepped=(path[1:]!=path[:-1]).astype(np.uint8)
    movements=stepped.sum(axis=0).astype(np.int16)
    churn=np.where(movements==0,0,np.where(movements<=2,1,
       np.where(movements<=5,2,3))).astype(np.uint16)
    # Exact 12-draw checkpoint membership dwell length capped at 36.
    dwell=np.ones(80,dtype=np.int16)
    for j in range(len(path)-2,-1,-1):
        still=(path[j]==group)
        if not still.any():break
        dwell+=still.astype(np.int16)
        # If a ball differs at one snapshot, cannot reach past this gap.
        # Keep a per-ball flag, NOT independently add earlier matching levels.
        if j==len(path)-2:
            alive=still.copy()
        else:
            alive&=still
            dwell-=((~alive)&still).astype(np.int16)
        if not alive.any():break
    age=np.where(dwell==1,0,np.where(dwell<=3,1,
        np.where(dwell<=7,2,3))).astype(np.uint16)
    # Number of sign reversals of NON-ZERO group changes in 36 periods
    diff=np.sign(path[1:].astype(np.int16)-path[:-1].astype(np.int16))
    last=np.zeros(80,dtype=np.int16)
    reverse=np.zeros(80,dtype=np.int16)
    for d in diff:
        nonzero=d!=0
        reverse+=((last!=0)&nonzero&(last!=d)).astype(np.int16)
        last=np.where(nonzero,d,last)
    reversals=np.where(reverse==0,0,np.where(reverse==1,1,2)).astype(np.uint16)
    entry=(group!=(r_prev//16)).astype(np.uint16)
    vals=dict(
      POOL5=group,
      LAST30=((group*3+direction)*2+entry),
      THREND45=((group*3+direction3)*3+direction),
      AGE60=((group*3+direction)*4+age),
      PHASE135=(((group*3+direction)*3+direction3)*3+long),
      JOURNEY240=(((group*3+long)*4+churn)*4+age),
      REVERSAL180=(((group*3+direction)*4+churn)*3+reversals))
    for name,state in vals.items():
        if state.min()<0 or state.max()>=MODEL_SIZE[name]:
            raise RuntimeError("feature state out of bounds "+name)
    return group,vals,dict(
       current=group,last_move=direction,three_move=direction3,
       long_move=long,churn=movements,age=dwell,reversals=reverse,
       entered_last_step=entry)

def generate(blocks,y,r):
    """All block identities and target labels computed separately."""
    mats={m:[] for m in MODELS}
    y12=[]
    pool=[]
    ix=[]
    meta=[]
    for t,day,k in blocks:
        snap=t-BACK+np.arange(MOVE_STEPS+1)*LAG
        trajectory=(r[snap]//16).astype(np.uint8)
        now,codes,extra=phi(trajectory,r[t],r[t-1])
        for name in MODELS:
            mats[name].append(codes[name].astype(np.uint16))
        pool.append(now.astype(np.uint8))
        y12.append(y[t:t+LAG].sum(axis=0,dtype=np.uint8))
        ix.append((t,day,k))
        meta.append(extra)
    pool=np.asarray(pool,dtype=np.uint8)
    y12=np.asarray(y12,dtype=np.uint8)
    codes={name:np.asarray(rows,dtype=np.uint16) for name,rows in mats.items()}
    assert pool.shape==(len(blocks),80)
    assert np.all(y12.sum(axis=1)==240)
    assert np.all(np.bincount(pool[0],minlength=5)==[16]*5)
    return pool,y12,codes,ix,meta

def shrink(trainstate,total12,count):
    states=trainstate.reshape(-1)
    opportunities=np.bincount(states,minlength=count)
    drawn=np.bincount(states,weights=total12.reshape(-1),
                      minlength=count).astype(float)
    # 12 draws per ball-block: scale to a probability of target hit.
    p=(drawn/12+ALPHA*.25)/(opportunities+ALPHA)
    return p,opportunities,drawn

def select(groups,states,probs,tie,policy,k):
    """Group shape 80, state 80, tie=80 stable random ranks."""
    scores=probs[states]+tie*1e-9
    result=np.zeros(80,dtype=np.uint8)
    if policy=="FREE":
        sel=np.argpartition(scores,-k)[-k:]
        result[sel]=1
    else:
        count=k//5
        for g in range(5):
            masked=np.where(groups==g,scores,-1.0)
            pick=np.argpartition(masked,-count)[-count:]
            assert np.all(groups[pick]==g)
            result[pick]=1
    assert result.sum()==k
    return result

def evaluate(y,picks10,picks20,rand10,rand20,indices):
    # y of block k is 12-by-80 boolean targets.
    rows10=[];rows20=[];rnd10=[];rnd20=[]
    for j,i in enumerate(indices):
        d=y[i:i+LAG]
        rows10.extend((d*picks10[j]).sum(axis=1).tolist())
        rows20.extend((d*picks20[j]).sum(axis=1).tolist())
        rnd10.extend((d*rand10[j]).sum(axis=1).tolist())
        rnd20.extend((d*rand20[j]).sum(axis=1).tolist())
    return (np.asarray(rows10),np.asarray(rows20),
            np.asarray(rnd10),np.asarray(rnd20))

def daily_metric(hit10,blocks_idx,block_meta):
    groups=Counter()
    byday={}
    for b,idx in enumerate(blocks_idx):
        d=block_meta[idx][1]
        byday.setdefault(d,[]).extend(hit10[b*12:(b+1)*12].tolist())
    means=np.array([np.mean(v) for v in byday.values()])
    sd=float(np.std(means,ddof=1)) if len(means)>1 else 0.
    return float(np.mean(hit10)-.25*sd),sd

def metrics(h10,h20,r10,r20):
    def f(v):return round(float(v),7)
    return dict(coupon10_avg=f(h10.mean()),random10_avg=f(r10.mean()),
       gain10=f((h10-r10).mean()),candidate20_avg=f(h20.mean()),
       random20_avg=f(r20.mean()),gain20=f((h20-r20).mean()),
       coupon_5plus=int((h10>=5).sum()),coupon_6plus=int((h10>=6).sum()),
       coupon_7plus=int((h10>=7).sum()),coupon_8plus=int((h10>=8).sum()),
       coupon_9plus=int((h10>=9).sum()),coupon_10of10=int((h10==10).sum()),
       pool20_7plus=int((h20>=7).sum()),pool20_8plus=int((h20>=8).sum()),
       pool20_9plus=int((h20>=9).sum()),pool20_10plus=int((h20>=10).sum()),
       target_draws=len(h10))

def csvw(z,name,rows):
    if not rows:return
    with z.open(name,"w") as raw:
        out=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        w=csv.DictWriter(out,fieldnames=list(rows[0].keys()))
        w.writeheader();w.writerows(rows)
        out.flush();out.detach()

def run(inputfile,dest):
    dates,rows,y,ids,p,issues,malformed=read(inputfile)
    rr=ranks(y,p)
    blocks,removed=valid_blocks(rows,ids,rr)
    groups,total12,features,meta,extra=generate(blocks,y,rr)
    split={
      "TRAIN":np.array([i for i,(_,d,k) in enumerate(meta) if d<T_VAL],dtype=int),
      "VALIDATE":np.array([i for i,(_,d,k) in enumerate(meta)
                           if T_VAL<=d<T_TEST],dtype=int),
      "HOLDOUT":np.array([i for i,(_,d,k) in enumerate(meta) if d>=T_TEST],dtype=int)}
    if not all(len(v)>0 for v in split.values()):
        raise RuntimeError(f"Empty split { {key:len(v) for key,v in split.items()} }")
    print("V83 valid blocks",len(blocks),"split",
          {key:len(v) for key,v in split.items()},"removed",dict(removed),flush=True)
    rng=np.random.default_rng(SEED)
    # Ties decided by *pre-generated* random IDs, independent of target data.
    tie=rng.random((len(blocks),80))
    # Separate randomized controls for each quota strategy; same control
    # across all seven models, to permit paired rule comparisons.
    randomsel={}
    for policy in POLICIES:
        controls10=[];controls20=[]
        for i in range(len(blocks)):
            g=groups[i]
            controls10.append(select(g,g,np.ones(5)*.25,tie[i],policy,10))
            controls20.append(select(g,g,np.ones(5)*.25,tie[i],policy,20))
        randomsel[policy]=(np.asarray(controls10),np.asarray(controls20))
    results=[]
    allp={}
    selection={}
    for model in MODELS:
        estimates,op,drawn=shrink(features[model][split["TRAIN"]],
                                  total12[split["TRAIN"]],MODEL_SIZE[model])
        allp[model]=(estimates,op,drawn)
        print(f"V83 fitted {model} train opportunities={int(op.sum())}",flush=True)
        for policy in POLICIES:
            selected10=[];selected20=[]
            for i in range(len(blocks)):
                s=features[model][i];g=groups[i]
                a=select(g,s,estimates,tie[i],policy,10)
                b=select(g,s,estimates,tie[i],policy,20)
                if np.any(a&~b):raise AssertionError("coupon10 not a subset of candidate20")
                selected10.append(a);selected20.append(b)
            a=np.asarray(selected10);b=np.asarray(selected20)
            selection[model,policy]=(a,b)
            ctrl10,ctrl20=randomsel[policy]
            for phase in ("VALIDATE","HOLDOUT"):
                indices=split[phase]
                h10=[];h20=[];r10=[];r20=[]
                for blockid in indices:
                    start=meta[blockid][0]
                    truth=y[start:start+12]
                    h10.extend((truth*a[blockid]).sum(axis=1).tolist())
                    h20.extend((truth*b[blockid]).sum(axis=1).tolist())
                    r10.extend((truth*ctrl10[blockid]).sum(axis=1).tolist())
                    r20.extend((truth*ctrl20[blockid]).sum(axis=1).tolist())
                h10=np.asarray(h10);h20=np.asarray(h20)
                r10=np.asarray(r10);r20=np.asarray(r20)
                dayutil,day_sd=daily_metric(h10,indices,meta)
                results.append(dict(model=model,policy=policy,phase=phase,
                   block_count=len(indices),criterion10=round(dayutil,7),
                   daily_sd10=round(day_sd,7),**metrics(h10,h20,r10,r20)))
    vals=sorted([r for r in results if r["phase"]=="VALIDATE"],
       key=lambda r:(-r["criterion10"],-r["candidate20_avg"],
          MODELS.index(r["model"]),POLICIES.index(r["policy"])))
    winner=vals[0]
    model=winner["model"];policy=winner["policy"]
    hold=next(r for r in results if r["phase"]=="HOLDOUT"
              and r["model"]==model and r["policy"]==policy)
    a,b=selection[model,policy]
    random10,random20=randomsel[policy]
    report_blocks=[]
    block_results=[]
    day_results={}
    for idx in split["HOLDOUT"]:
        t,day,k=meta[idx]
        truth=y[t:t+12]
        hits10=(truth*a[idx]).sum(axis=1)
        hits20=(truth*b[idx]).sum(axis=1)
        ctl10=(truth*random10[idx]).sum(axis=1)
        ctl20=(truth*random20[idx]).sum(axis=1)
        directions=extra[idx]["last_move"]
        evs=extra[idx]["churn"]
        g=groups[idx]
        current=dict(day=dates[day],day_block=k+1,start_id=rows[t]["id"],
          end_id=rows[t+11]["id"],start_clock=rows[t]["time"],
          end_clock=rows[t+11]["time"],train_rule=model,policy=policy,
          coupon10=",".join(map(str,np.flatnonzero(a[idx])+1)),
          candidate20=",".join(map(str,np.flatnonzero(b[idx])+1)),
          avg_10=round(float(hits10.mean()),6),
          avg_random10=round(float(ctl10.mean()),6),
          avg_20=round(float(hits20.mean()),6),
          avg_random20=round(float(ctl20.mean()),6),
          coupon10_10of10=int((hits10==10).sum()),
          coupon10_8plus=int((hits10>=8).sum()),
          iplus_12step_warming=int((directions==2).sum()),
          iminus_12step_cooling=int((directions==0).sum()),
          stable_12step=int((directions==1).sum()),
          avg_churn_36stages=round(float(evs.mean()),4))
        for q in range(5):
            current[f"pool_{POOL[q].lower()}_16"]=",".join(
                map(str,np.flatnonzero(g==q)+1))
        report_blocks.append(current)
        for j in range(12):
            block_results.append(dict(day=dates[day],block=k+1,
                draw_id=rows[t+j]["id"],clock=rows[t+j]["time"],
                coupon10_hit=int(hits10[j]),random10_hit=int(ctl10[j]),
                candidate20_hit=int(hits20[j]),random20_hit=int(ctl20[j]),
                coupon10=",".join(map(str,np.flatnonzero(a[idx])+1)),
                coupon10_correct=",".join(map(str,np.flatnonzero(a[idx]&truth[j])+1)),
                actual_target20=",".join(map(str,np.flatnonzero(truth[j])+1))))
        day_results.setdefault(day,[]).append((hits10,hits20,ctl10,ctl20))
    daily=[]
    for day,records in sorted(day_results.items()):
        h10=np.concatenate([x[0] for x in records])
        h20=np.concatenate([x[1] for x in records])
        c10=np.concatenate([x[2] for x in records])
        c20=np.concatenate([x[3] for x in records])
        daily.append(dict(day=dates[day],blocks=len(records),
            targets=len(h10),coupon10_avg=round(float(h10.mean()),7),
            random10_avg=round(float(c10.mean()),7),
            candidate20_avg=round(float(h20.mean()),7),
            random20_avg=round(float(c20.mean()),7),
            coupon10_10of10=int((h10==10).sum()),
            coupon10_7plus=int((h10>=7).sum())))
    # The user's end-of-day last-12 target; export full prior 36 checkpoint
    # pathway and chosen coupon as of the block BEFORE first target.
    last_index=next(i for i,(t,d,k) in enumerate(meta) if d==71 and k==17)
    last_t=meta[last_index][0]
    last_start=last_t-BACK
    prior_path=(rr[last_start:last_t+1:12]//16)
    assert len(prior_path)==37 and last_t+11==len(y)-1
    final_block=next(x for x in report_blocks if x["day"]==dates[-1]
                     and x["day_block"]==18)
    timeline=[]
    for ball in range(80):
        line=dict(number=ball+1,
           first_pool=POOL[int(prior_path[0,ball])],
           pool_before_last12=POOL[int(prior_path[-1,ball])],
           within16_rank_before_target=int(rr[last_t,ball]%16+1),
           path36="→".join(POOL[int(v)] for v in prior_path[:,ball]),
           warming_12moves=int(np.sum(np.diff(prior_path[:,ball].astype(int))>0)),
           cooling_12moves=int(np.sum(np.diff(prior_path[:,ball].astype(int))<0)),
           last12_direction=("ISINIYOR" if prior_path[-1,ball]>prior_path[-2,ball]
                 else "SOGUYOR" if prior_path[-1,ball]<prior_path[-2,ball] else "SABIT"),
           selected_in_coupon10=int(a[last_index,ball]),
           selected_in_candidate20=int(b[last_index,ball]),
           historical_actual_hits_in_next12=int(total12[last_index,ball]))
        timeline.append(line)
    # Statistical caution: day-level test on mean differences, not the
    # mostly overlapping rolling heat states treated as iid feature samples.
    paired_day_deltas=np.array([r["coupon10_avg"]-r["random10_avg"]
                                 for r in daily],dtype=float)
    mean_diff=float(paired_day_deltas.mean())
    se=float(np.std(paired_day_deltas,ddof=1)/np.sqrt(len(daily)))
    z=mean_diff/se if se else 0.
    # This uses a normal approximation as descriptive only.
    one_sided_p=float(.5*math.erfc(z/math.sqrt(2)))
    # pool trajectory stages from pre-target last12 to next targets:
    phaserows=[]
    for phase in ("VALIDATE","HOLDOUT"):
        indexes=split[phase]
        for k in range(5):
            for shift in (0,1,2):
                opp=0;hits=0
                for idx in indexes:
                    group=groups[idx]
                    direction=extra[idx]["last_move"]
                    mask=(group==k)&(direction==shift)
                    opp+=int(mask.sum())*12
                    hits+=int(total12[idx,mask].sum())
                phaserows.append(dict(phase=phase,current_pool=POOL[k],
                    recent12_direction=("SOGUYOR","SABIT","ISINIYOR")[shift],
                    actual1=hits,actual0=opp-hits,
                    opportunities=opp,observed_hit_pct=
                    round(100*hits/opp,6) if opp else None))
    summary=[
      "V83 — 434 CEKILISLIK 36x12 YOLCULUKTAN ONCEDEN 10 SAYILIK KUPON",
      "Each of 80 balls classified among five exactly 16-ball tiers by",
      "frequencies in previous 434 real draws. PRE-TARGET snapshots for",
      "36 prior intervals of 12 draws: 37 historical snapshots, NO peeking.",
      "Next 12 draw results are revealed only after coupon10 and candidate20",
      "were chosen. One fixed coupon10 is tested on all 12 future draws.",
      "Each full day tests eighteen 12-draw blocks: day slots 2..217,",
      "the very first daily draw is skipped (217=18*12+1).",
      f"Eligible draw-history-contiguous 12-blocks={len(blocks)}.",
      f"Quality/exclusions {dict(removed)}.",
      f"TRAIN blocks={len(split['TRAIN'])}, VALIDATION blocks={len(split['VALIDATE'])},",
      f"TEST/HOLDOUT blocks={len(split['HOLDOUT'])}.",
      "Seven frozen-in-advance feature recipes x two quota policies.",
      "Features include current 16-pool, last1/3/36 movement directions,",
      "number of switches in 36 steps, repeated direction flips and dwell.",
      "TRAIN frequencies from historical 12-target hits, alpha=350 prior25%.",
      "VALIDATION selects one rule by 10-coupon hits per draw minus",
      "0.25 x standard deviation of daily hit averages.",
      "Do not post-select model based on TEST; full alternatives audited.",
      "",
      "VALIDATION ranking sorted by coupon10 objective:"
    ]
    for rec in vals:
        summary.append(f"   {rec['model']:13} {rec['policy']:8}"
            f" 10={rec['coupon10_avg']:.5f} random10={rec['random10_avg']:.5f}"
            f" 20={rec['candidate20_avg']:.5f} random20={rec['random20_avg']:.5f}"
            f" criterion={rec['criterion10']:.5f}")
    summary+=["",
      f"FROZEN WINNER = {model} / {policy}; validation 10 mean={winner['coupon10_avg']:.6f}.",
      f"HOLDOUT 10 coupon mean={hold['coupon10_avg']:.6f}, random={hold['random10_avg']:.6f},"
      f" difference={hold['gain10']:+.6f} per target.",
      f"HOLDOUT 20 candidate mean={hold['candidate20_avg']:.6f}, "
      f"random={hold['random20_avg']:.6f}, difference={hold['gain20']:+.6f}.",
      f"HOLDOUT 10/10 occurrences={hold['coupon_10of10']},"
      f" 9+={hold['coupon_9plus']},8+={hold['coupon_8plus']},"
      f" 7+={hold['coupon_7plus']},6+={hold['coupon_6plus']}.",
      f"HOLDOUT day-level 10-hit matched difference mean={mean_diff:+.6f},"
      f" s.e.={se:.6f}, normal one-sided p≈{one_sided_p:.6f}.",
      "",
      "LATEST COMPLETE DAY: 12 OCT final 12 targets:",
      f"  first target={rows[last_t]['id']} at {rows[last_t]['time']},"
      f" last target={rows[last_t+11]['id']} at {rows[last_t+11]['time']}.",
      f"  PRE-COMMITTED 10 coupon={final_block['coupon10']}.",
      f"  PRE-COMMITTED candidate20={final_block['candidate20']}.",
      f"  12 draws mean hits10={final_block['avg_10']:.5f},"
      f" random10={final_block['avg_random10']:.5f},"
      f" hits20={final_block['avg_20']:.5f},"
      f" random20={final_block['avg_random20']:.5f}.",
      "Complete 80-number 36-step paths and per-draw 1/0 results in ZIP.",
      "",
      "FAIR INDEPENDENT RNG 20/80: each preselected 10 coupon expects",
      "2.5 correct per draw, preselected 20 expects 5.0 correct.",
      "Historical chronology does not make reused dates unseen new data.",
      "Independent unseen future draws are needed to verify any advantage.",
      ""
    ]
    # audit state training distribution
    cells=[]
    for name,(probs,counts,drawn) in allp.items():
        for stateid in range(len(probs)):
            cells.append(dict(model=name,state=stateid,
                number_block_opportunities=int(counts[stateid]),
                actual_hit_events_next12=float(drawn[stateid]),
                observed_hit_pct=round(float(100*drawn[stateid]/
                   (12*counts[stateid])),6) if counts[stateid] else None,
                smoothed_next_target1_pct=round(float(100*probs[stateid]),6)))
    out=Path(dest)
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_V83_KISA_HONEST_KARAR.txt","\n".join(summary))
        csvw(z,"01_7MOTOR_2POLITIKA_VAL_TEST_10LU_20LI.csv",results)
        csvw(z,"02_VALIDASYON_BIRINCI_ONCEDEN_SECILEN_KURAL.csv",vals)
        csvw(z,"03_SON15GUN_270ADET_12LI_BLOK_ONCEDEN_10_20.csv",report_blocks)
        csvw(z,"04_SON15GUN_3240_HEDEF_10LU_ISABET_20LI_ISABET.csv",block_results)
        csvw(z,"05_SON15GUN_15GUN_BAZINDA_GERCEK_ISABET.csv",daily)
        csvw(z,"06_EKIM12_SON12_80_SAYININ_36_ASAMALI_HAREKET_KUPON.csv",timeline)
        csvw(z,"07_HEDEF_ONCESI_HAVUZ_VE_12YON_HEDEF_1_0.csv",phaserows)
        csvw(z,"08_EGITIM_TUM_7_YONTEM_DURUM_OLASILIKLARI.csv",cells)
        z.writestr("09_KURAL_VERI_DISIPLINI.txt","\n".join([
          "At block start t: 434-lookback heat states at t-432,t-420,...,t.",
          "This is a 36 x12 step PRE-TARGET history of exactly 37 states.",
          "Each state computed using [state-434,state) real draws only.",
          "The complete feature history for a target block needs 866",
          "uninterrupted draws BEFORE the block, plus 12 future outcomes.",
          "Before target begins: fix 10-number coupon and 20-number pool.",
          "No change to coupon throughout next twelve 5-min draws.",
          "18 blocks per complete day at slot2,14,...206; last at 206..217.",
          "Exclude windows that cross invalid 23Aug missing day.",
          "Ties in 434draw appearance rank broken with prior rank.",
          "TRAIN all eligible prior to 13 Sep; VALIDATE Sep13–27;",
          "HOLDOUT Sep28–Oct12 without selecting a new winner.",
          "7 families*2 policies fixed; training alpha350 smoothing.",
          "FREE no quota, BALANCED exactly 2 of 16 per 10 coupon,",
          "4 of 16 per 20 candidate. 10 always subset 20.",
          "Each policy random control has matching selection constraint.",
          "Valid split days have full intact history and block draw IDs.",
          "Expect independent fair drawing: 2.5/10 and 5/20.",
          "All validation/holdout days were explored in prior versions,",
          "so claims of prospective prediction improvement aren't justified."
        ]))
        z.writestr("10_AUDIT.json",json.dumps(dict(version=VERSION,
            complete_days=dates,total=15624,history_length=HIST,
            trajectory_changes=MOVE_STEPS,lag=LAG,prior_required=REQUIRED,
            excluded=dict(removed),valid_blocks=len(blocks),
            blocks_per_split={k:len(v) for k,v in split.items()},
            model_candidates=MODELS,policies=POLICIES,alpha=ALPHA,seed=SEED,
            frozen_winner={"model":model,"policy":policy},
            validation=winner,holdout=hold,
            final12_first_id=rows[last_t]["id"],
            final12_last_id=rows[last_t+11]["id"],
            final12_preselected_coupon10=final_block["coupon10"],
            final12_preselected_candidate20=final_block["candidate20"],
            day_level_normal_approx_p=one_sided_p,issues=issues[:20],
            malformed=malformed[:20]),ensure_ascii=False,indent=2))
    print("\n".join(summary),flush=True)
    print("V83 OUTPUT",out,out.stat().st_size,flush=True)

def selftest():
    rng=np.random.default_rng(83)
    y=np.zeros((1800,80),dtype=np.uint8)
    for i in range(len(y)): y[i,rng.choice(80,20,replace=False)]=1
    p=np.zeros((len(y)+1,80),dtype=np.int32)
    p[1:]=np.cumsum(y,axis=0)
    r=ranks(y,p)
    t=1100
    seq=t-BACK+np.arange(MOVE_STEPS+1)*12
    assert len(seq)==37 and seq[0]==t-432 and seq[-1]==t
    states=(r[seq]//16).astype(np.uint8)
    group,values,ext=phi(states,r[t],r[t-1])
    assert len(values)==len(MODELS)
    assert (np.bincount(group,minlength=5)==[16]*5).all()
    tie=rng.random(80)
    for name in MODELS:
        prob=np.full(MODEL_SIZE[name],.25)
        for pol in POLICIES:
            ten=select(group,values[name],prob,tie,pol,10)
            twenty=select(group,values[name],prob,tie,pol,20)
            assert np.all((ten&~twenty)==0)
    print("V83 SELFTEST OK",flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",default="veri.txt")
    ap.add_argument("--out",default="v83_output/V83_434CEKILIS_36x12_HAREKETTEN_KUPON10_HEDEF20_KOR_TEST.zip")
    ap.add_argument("--selftest",action="store_true")
    options=ap.parse_args()
    if options.selftest:selftest()
    else:run(options.source,options.out)
