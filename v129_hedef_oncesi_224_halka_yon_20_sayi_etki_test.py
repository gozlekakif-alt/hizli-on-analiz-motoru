#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V129 -- Does known PRE-DRAW direction across 224 nested rings affect
a number's membership in the NEXT actual 20-of-80 result?

Unlike V126/V127/V128 descriptive after-draw replay, ALL V129 features for
target t+1 are computed using only observed X[:t+1] (through t), NEVER X[t+1].
224 overlapping windows of lengths 12,24,...,2688 draws; in each window
80 number counts sorted ascending (ties number smaller first), five rank
pools of 16. Pool direction = pool_after_observing_t minus pool_after_t-1.

For each target, all 80 numbers classified into:
- mutually exclusive no warm/cool / warm only / cool only / mixed;
- dominant direction, short-long wave, changes in anchor rings, 6/12-step
  momentum (historical only).
Check actual next-draw membership conditional on these PRE-DRAW signals.
Reproducible ticket models (same 1 ticket per model/target, size k),
validation winner locked for last18 historical days; fair-random reference,
day bootstrap confidence intervals; no claim of genuine untouched future test.

Store auditable every-conditional signal day-level and last18 ticket paths.
Source: repo veri.txt, via v100c loader.
"""
from __future__ import annotations
import argparse,collections,csv,io,json,zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load

NR=224
NB=80
LENS=np.arange(12,2689,12,dtype=np.int32)
SEED=1292026
SIZES=(3,4,5,6,8,10,20)
SIG_NAMES=(
 "NO_POOL_CHANGE","ONLY_WARM","ONLY_COOL","MIXED_WARM_AND_COOL",
 "WARM_DOMINANT","COOL_DOMINANT","BALANCED_WHILE_MOVING",
 "WARM_40_PLUS_RINGS","COOL_40_PLUS_RINGS",
 "WARM_100_PLUS_RINGS","COOL_100_PLUS_RINGS",
 "FIRST56_WARM_NET","FIRST56_COOL_NET",
 "LAST56_WARM_NET","LAST56_COOL_NET",
 "FIRST_WARM_LAST_COOL","FIRST_COOL_LAST_WARM",
 "ALL_FOUR_BANDS_NET_WARM","ALL_FOUR_BANDS_NET_COOL",
 "RING12_WARM","RING12_COOL","RING72_WARM","RING72_COOL",
 "RING672_WARM","RING672_COOL","RING2688_WARM","RING2688_COOL",
 "PREVIOUSLY_DRAWN","PREVIOUSLY_NOT_DRAWN"
)
METHODS=(
 "NET_WARM224","NET_COOL224","WARM_COUNT224","COOL_COUNT224",
 "WARM_CONSISTENCY","COOL_CONSISTENCY",
 "FIRST56_WARM","FIRST56_COOL","LAST56_WARM","LAST56_COOL",
 "FIRST_WARM_LAST_COOL","FIRST_COOL_LAST_WARM",
 "RANK_NET_WARM","RANK_NET_COOL",
 "WARM_PERSIST_6","COOL_PERSIST_6","WARM_REVERSAL_6",
 "COOL_REVERSAL_6",
 "HOT12","HOT72","HOT672","HOT2688",
 "PREV_DRAWN","PREV_NOT_DRAWN","RANDOM")
assert len(LENS)==224 and len(SIG_NAMES)==29 and len(METHODS)==25

def state(cnt):
    order=np.argsort(cnt,axis=1,kind="stable")
    rk=np.empty((NR,NB),dtype=np.int16)
    rk[np.arange(NR)[:,None],order]=np.arange(NB,dtype=np.int16)
    cls=rk//16
    assert np.all((np.bincount(cls.ravel(),minlength=5))==16*NR)
    return rk,cls

def signals(dirv,drawn):
    warm=(dirv>0)
    cool=(dirv<0)
    up=warm.sum(axis=0)
    down=cool.sum(axis=0)
    net=up-down
    bnet=np.stack([(warm[i:i+56].sum(axis=0) -
                    cool[i:i+56].sum(axis=0)) for i in (0,56,112,168)])
    out=(
     ((up==0)&(down==0)),((up>0)&(down==0)),((down>0)&(up==0)),
     ((up>0)&(down>0)),
     net>0,net<0,((net==0)&((up+down)>0)),
     up>=40,down>=40,up>=100,down>=100,
     bnet[0]>0,bnet[0]<0,bnet[3]>0,bnet[3]<0,
     ((bnet[0]>0)&(bnet[3]<0)),((bnet[0]<0)&(bnet[3]>0)),
     (bnet>0).all(axis=0),(bnet<0).all(axis=0),
     dirv[0]>0,dirv[0]<0,dirv[5]>0,dirv[5]<0,
     dirv[55]>0,dirv[55]<0,dirv[223]>0,dirv[223]<0,
     drawn==1,drawn==0)
    assert len(out)==len(SIG_NAMES)
    assert np.all(np.stack(out[:4]).sum(axis=0)==1)
    return np.stack(out),up,down,bnet

def select_models(up,down,bnet,rank_delta,count,prior,drawn):
    net=up-down
    # 6 complete prior steps (possibly less at first observation) and
    # current t, all <= target t+1 opening information.
    available=np.stack((*prior,net),axis=0) if prior else net[None,:]
    persist=available[-6:].mean(axis=0)
    previous_mean=np.stack(prior[-6:],axis=0).mean(axis=0) if prior else np.zeros(NB)
    warm_ratio=up/(up+down+1.)
    cool_ratio=down/(up+down+1.)
    b0,b3=bnet[0],bnet[3]
    scores=dict(
      NET_WARM224=net,NET_COOL224=-net,
      WARM_COUNT224=up,COOL_COUNT224=down,
      WARM_CONSISTENCY=warm_ratio,
      COOL_CONSISTENCY=cool_ratio,
      FIRST56_WARM=b0,FIRST56_COOL=-b0,
      LAST56_WARM=b3,LAST56_COOL=-b3,
      FIRST_WARM_LAST_COOL=b0-b3,
      FIRST_COOL_LAST_WARM=b3-b0,
      RANK_NET_WARM=rank_delta.sum(axis=0),
      RANK_NET_COOL=-rank_delta.sum(axis=0),
      WARM_PERSIST_6=persist,COOL_PERSIST_6=-persist,
      WARM_REVERSAL_6=net-previous_mean,
      COOL_REVERSAL_6=previous_mean-net,
      HOT12=count[0],HOT72=count[5],HOT672=count[55],
      HOT2688=count[223],
      PREV_DRAWN=drawn,PREV_NOT_DRAWN=1-drawn)
    assert len(scores)==len(METHODS)-1
    return scores,net

def tocsv(z,name,records):
    if not records:return
    mem=io.StringIO(newline="")
    w=csv.DictWriter(mem,fieldnames=list(records[0]))
    w.writeheader();w.writerows(records)
    z.writestr(name,mem.getvalue().encode("utf-8-sig"))

def ci_rate_difference(arr,seed):
    # arr: records by day [positive_count, positive_drawn_count,
    #                    negative_count, negative_drawn_count].
    if len(arr)<3:return (None,None,None)
    a=np.asarray(arr,dtype=np.float64)
    total=a.sum(axis=0)
    if min(total[0],total[2])<20:return (None,None,None)
    delta=total[1]/total[0]-total[3]/total[2]
    rng=np.random.default_rng(seed)
    inds=rng.integers(0,len(a),size=(3000,len(a)))
    sampled=a[inds].sum(axis=1)
    valid=(sampled[:,0]>0)&(sampled[:,2]>0)
    v=sampled[valid,1]/sampled[valid,0]-sampled[valid,3]/sampled[valid,2]
    return (float(delta),float(np.quantile(v,.025)),
            float(np.quantile(v,.975))) if len(v)>2500 else (float(delta),None,None)

def main(source,out):
    days,rows,X,issues,bad=load(source)
    n=len(rows)
    assert n==len(X) and n>=2800
    assert np.all(X.sum(axis=1)==20)
    final_dates=sorted(d for d in days if d<="2026-10-12")
    assert len(final_dates)==72
    periods={d:("TRAIN36" if i<36 else "VALIDATE18" if i<54 else "LAST18")
             for i,d in enumerate(final_dates)}
    P=np.vstack((np.zeros((1,NB),dtype=np.int32),
                  np.cumsum(X,axis=0,dtype=np.int32)))
    current=P[2688][None,:]-P[2688-LENS]
    prev_rank,prev_pool=state(current)
    n_targets=n-2688-1
    prior=[]
    # one row per signal per day with conditional exposed and other balls
    exposure=collections.defaultdict(lambda:np.zeros(4,dtype=np.int64))
    ticket=collections.defaultdict(lambda:np.zeros(5,dtype=np.int64))
    ticketday=collections.defaultdict(lambda:np.zeros(3,dtype=np.int64))
    audit=[]
    last_signatures=[]
    for t in range(2688,n-1):
        # t is a COMPLETED known draw; target t+1 is not yet read.
        prevout=X[t].astype(np.int16)
        leaving=X[t-LENS].astype(np.int16)
        difference=prevout[None,:]-leaving
        nxt=current+difference
        newrank,newpool=state(nxt)
        pdiff=newpool-prev_pool
        rdiff=newrank-prev_rank
        S,up,down,bnet=signals(pdiff,prevout)
        model_scores,net=select_models(up,down,bnet,rdiff,nxt,prior,prevout)
        # All target information is read from X[t+1] only AFTER features set.
        tt=t+1
        y=X[tt].astype(np.int16)
        assert int(y.sum())==20
        day=rows[tt]["day"]
        phase=periods.get(day,"EXTRA_OCT13")
        for j,name in enumerate(SIG_NAMES):
            sel=S[j]
            yes=int(sel.sum())
            hyes=int(y[sel].sum())
            exposure[(phase,day,name)]+=(yes,hyes,NB-yes,20-hyes)
        random_selected=np.random.default_rng(SEED+tt*314159).permutation(NB)[:20]
        for name in METHODS:
            if name=="RANDOM":idx=random_selected
            else:
                vals=model_scores[name]
                idx=np.lexsort((np.arange(NB),-vals))[:20]
            selected=y[idx]
            cum=np.cumsum(selected)
            for k in SIZES:
                hit=int(cum[k-1])
                ticket[(phase,name,k)]+=(1,hit,int(hit==k),
                         int(hit>=5),int(hit>=6))
                if phase=="LAST18" and k==10:
                    ticketday[(day,name)]+=(1,hit,int(hit>=5))
            if phase=="LAST18" and name in ("NET_WARM224","NET_COOL224",
                                           "HOT72","RANDOM"):
                audit.append(dict(
                    target_id=rows[tt]["id"],date=day,phase=phase,
                    current_known_draw_id=rows[t]["id"],
                    method=name,picked20="-".join(str(i+1) for i in idx),
                    hits3=int(cum[2]),hits4=int(cum[3]),hits5=int(cum[4]),
                    hits6=int(cum[5]),hits8=int(cum[7]),hits10=int(cum[9]),
                    hits20=int(cum[19]),
                    actual_target_20="-".join(str(i+1) for i in np.flatnonzero(y))))
        if tt==n-1:
            for i in range(80):
                last_signatures.append(dict(
                  number=i+1,known_through_draw_id=rows[t]["id"],
                  tested_target_draw_id=rows[tt]["id"],
                  actual_target_1_0=int(y[i]),prior_draw_1_0=int(prevout[i]),
                  all224_warming=int(up[i]),all224_cooling=int(down[i]),
                  all224_net=int(net[i]),last56_net=int(bnet[3,i]),
                  first56_net=int(bnet[0,i]),
                  warming_0_1_224_pattern="".join(
                    "C0W"[int(np.sign(x))+1] for x in pdiff[:,i]),
                  all224_prev_pools="".join(str(x) for x in prev_pool[:,i]),
                  all224_new_pools="".join(str(x) for x in newpool[:,i])))
        prior.append(net.astype(np.float32))
        if len(prior)>12:prior.pop(0)
        current=nxt
        prev_rank=newrank
        prev_pool=newpool
        if (t-2687)%2500==0:
            print("V129 replayed",t-2687,"/",n_targets,
                  "fully PRE-TARGET direction profiles",flush=True)
    assert len(last_signatures)==80
    total_exposed={}
    for (phase,day,sig),v in exposure.items():
        total_exposed.setdefault((phase,sig),np.zeros(4,dtype=np.int64))
        total_exposed[(phase,sig)]+=v
    conditional=[]
    holdout_boot=[]
    allphases=("VALIDATE18","LAST18","TRAIN36","EXTRA_OCT13")
    for phase in allphases:
        for si,sig in enumerate(SIG_NAMES):
            if (phase,sig) not in total_exposed:continue
            v=total_exposed[(phase,sig)]
            yes,yeshit,no,nohit=(int(w) for w in v)
            p=yeshit/yes if yes else None
            q=nohit/no if no else None
            delta=(p-q) if p is not None and q is not None else None
            conditional.append(dict(
              phase=phase,signal=sig,eligible_ball_target_pairs=yes,
              eligible_next_drawn=yeshit,
              eligible_next_target_rate_pct=round(100*p,5) if p is not None else None,
              eligible_next_rate_minus_25pp=round(100*(p-.25),5) if p is not None else None,
              other_ball_target_pairs=no,other_next_drawn=nohit,
              other_next_rate_pct=round(100*q,5) if q is not None else None,
              eligible_minus_other_pp=round(100*delta,5) if delta is not None else None))
            if phase=="LAST18":
                daily=np.asarray(
                    [v for (ph,d,s),v in sorted(exposure.items())
                     if ph==phase and s==sig],dtype=np.int64)
                d,low,high=ci_rate_difference(daily,SEED+si*37)
                holdout_boot.append(dict(signal=sig,
                    holdout_days=len(daily),signal_N=yes,
                    signal_hit=yeshit,signal_rate_pct=round(100*p,5)
                         if p is not None else None,
                    remaining_rate_pct=round(100*q,5)
                         if q is not None else None,
                    difference_pp=round(100*d,5) if d is not None else None,
                    bootstrap95_low_pp=round(100*low,5) if low is not None else None,
                    bootstrap95_high_pp=round(100*high,5) if high is not None else None))
    score_table=[]
    for phase in allphases:
        for method in METHODS:
            for k in SIZES:
                vals=ticket.get((phase,method,k))
                if vals is None or vals[0]==0:continue
                calls,hits,perfect,h5,h6=(int(x) for x in vals)
                score_table.append(dict(
                  phase=phase,method=method,ticket_size=k,
                  target_draws=calls,avg_hits=round(hits/calls,6),
                  perfect_k_of_k=perfect,at_least5=h5,at_least6=h6,
                  fair_average=k/4))
    # Lock model using validation k10 only; compare LAST18 to random
    # and HOT72 as predetermined reference models.
    ranking=sorted(
       [(name,float(ticket[("VALIDATE18",name,10)][1])/
                   float(ticket[("VALIDATE18",name,10)][0]))
        for name in METHODS if name not in ("RANDOM","HOT12","HOT72","HOT672","HOT2688",
                                            "PREV_DRAWN","PREV_NOT_DRAWN")],
       key=lambda z:(-z[1],z[0]))
    winner=ranking[0][0]
    comparison=[]
    hold_days=sorted(d for d in final_dates if periods[d]=="LAST18")
    for baseline in ("RANDOM","HOT72","HOT2688","NET_WARM224"):
        aa=np.asarray(
            [ticketday[(d,winner)][1]/ticketday[(d,winner)][0] -
             ticketday[(d,baseline)][1]/ticketday[(d,baseline)][0]
             for d in hold_days],dtype=np.float64)
        rng=np.random.default_rng(SEED+len(baseline)*11)
        bs=aa[rng.integers(0,len(aa),(5000,len(aa)))].mean(axis=1)
        comparison.append(dict(winner=winner,other=baseline,days=len(aa),
           average_diff=round(float(aa.mean()),6),
           daily_bootstrap95_lo=round(float(np.quantile(bs,.025)),6),
           daily_bootstrap95_hi=round(float(np.quantile(bs,.975)),6)))
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    def get_cond(s):
        return next(z for z in conditional if z["phase"]=="LAST18" and z["signal"]==s)
    short=[
       "V129: DOES THE 224-RING DIRECTION KNOWN BEFORE A TARGET CHANGE THE TARGET20 HIT RATE?",
       f"Source: {n} real draws; latest {rows[-1]['id']} on {rows[-1]['day']}; "
         f"real prospective-in-time comparisons: {n_targets}.",
       "Each target uses movement from PREVIOUS known draw exclusively;",
       "the unknown next draw is never used in candidate selection.",
       "80 balls each target, 224 nested rings, 5x16 equal pools.",
       f"Conditional signals examined: {len(SIG_NAMES)}; one-ticket "
          f"selection methods: {len(METHODS)}.",
       "RATE definition: drawn in NEXT target / all eligible number-target pairs.",
       "Fair independent baseline: 25%. Descriptive conditional differences",
       "do not imply causality or predictive advantage absent unseen future confirmation.",
       "Last18 is historically re-used dates, NOT virgin external holdout.",
       "",
       "LAST18: Conditional next-draw membership of PRE-DRAW direction signals:"]
    for sig in SIG_NAMES:
        z=get_cond(sig)
        short.append(
           f" {sig:30s} next P={z['eligible_next_target_rate_pct']}%, "
           f"n={z['eligible_ball_target_pairs']:,}, "
           f"against other={z['other_next_rate_pct']}% "
           f"diff={z['eligible_minus_other_pp']}pp")
    short.extend([
       "","VALIDATE18 prelocked leading direction model for 10-ball coupon:",
       f" {winner} with validation 10-ball avg={ranking[0][1]:.6f}.",
       "LAST18 locked winner same ticket budgets:"])
    for method in (winner,"NET_WARM224","NET_COOL224","HOT72","HOT2688","RANDOM"):
        q=ticket[("LAST18",method,10)]
        short.append(
           f" {method:25s} avg10={q[1]/q[0]:.6f}, >=5={q[3]}, >=6={q[4]},"
           f" exact10={q[2]}, N={q[0]}")
    for q in comparison:
        short.append(
          f" winner−{q['other']}: avg10 Δ={q['average_diff']:+.5f}, "
          f"95% day-bootstrap [{q['daily_bootstrap95_lo']:+.5f},"
          f"{q['daily_bootstrap95_hi']:+.5f}]")
    short.extend([
       "","HOW TO READ: a number with pre-draw warming in many nested rings",
       "might have a conditional frequency above/below 25% in the observed",
       "data; only a stable tested positive rate on genuine future draws",
       "supports using it for predicting the next 20 balls.",
       "Direction computed AFTER target would be target leakage. Not used.",
       "The 224 windows heavily overlap so movements are mechanically related.",
       "Any selection among many candidate models increases false-positive risk.",
       "Until future independent corroboration, next-draw chance remains",
       "25% per number under an unbiased independent draw mechanism."])
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as z:
        z.writestr("00_V129_KISA_GERCEK_BULGU.txt","\n".join(short)+"\n")
        tocsv(z,"01_ILERIYE_HEDEF20_ONCESI_SINYAL_KOSULLU_OLASILIK.csv",conditional)
        tocsv(z,"02_SON18_29_ONCU_SINYAL_GUN_GUVEN_ARALIK.csv",holdout_boot)
        tocsv(z,"03_25_YONTEM_3_4_5_6_8_10_20_BOYUT_SONUC.csv",score_table)
        tocsv(z,"04_VALIDE_SECILEN_KILITLI_MODEL_KONTROL.csv",comparison)
        tocsv(z,"05_SON18_HEDEF_4_FARKLI_MODEL_10_SAYI_ESLESME.csv",audit)
        tocsv(z,"06_SON_HEDEF_ONCESI_80_SAYI_224_HALKANIN_GERCEK_YONLERI.csv",
              last_signatures)
        signalday=[]
        for (ph,day,sig),v in sorted(exposure.items()):
            signalday.append(dict(phase=ph,date=day,signal=sig,
                n_ball_pairs=int(v[0]),n_next_hits=int(v[1]),
                other_pairs=int(v[2]),other_next_hits=int(v[3])))
        tocsv(z,"07_HER_GUN_29_SINYAL_ONCE_VE_HADEF.csv",signalday)
        z.writestr("08_V129_DENETIM.json",json.dumps(dict(
           known_source_rows=n,first_target_id=rows[2689]["id"],
           final_target_id=rows[-1]["id"],
           targets=n_targets,all_target_number_pairs=n_targets*NB,
           max_ring_length=2688,num_nested_windows=224,
           from_previous_observed_draw_only=True,
           signal_names=list(SIG_NAMES),selection_models=list(METHODS),
           coupon_sizes=list(SIZES),validation_winner=winner,
           validation_direction_model_ranking=ranking,
           validation_dates_last=final_dates[53],
           holdout_dates_first=final_dates[54],
           holdout_dates_last=final_dates[-1],
           no_actual_future_draw_data=True,
           holdout_previously_studied=True,
           no_claim_of_predictive_advantage=True),ensure_ascii=False,indent=2))
    print("\n".join(short),flush=True)
    print("V129 SUCCESS",out,out.stat().st_size,flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",default="veri.txt")
    ap.add_argument("--out",default="v129_output/V129_HEDEF_ONCESI_224_HALKA_YON_ETKI_KOR_TEST.zip")
    a=ap.parse_args()
    main(a.source,a.out)
