#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V72: true balanced five-temperature-pool 20-set from identities + transitions.

Exactly four identities from each of the five 16-ball frequency-quantile pools.
Test WHICH fixed temperature lookback N works best when identity is chosen
by tier direction (movement over previous 12 draws) and recent activity.
Only past 10 completed days are used to choose N + policy, then freeze
and evaluate on 12 Oct's 217 targets. Retrospective and exploratory, since
12 Oct was previously researched; not prospective proof of forecasting.
Every target selection is frozen before observing its drawn 20 balls.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import random
import statistics
import zipfile
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V72.1"
LOOKBACKS=(12,24,36,42,56,72,96,120,144,217,288,432)
POLICIES=("RISING","COOLING","STEADY","FREQ","MIXED","RANDOM")
TRAIN_DAYS=10
FOCUS_DAY="2026-10-12"
SIZES=5
N_PER_POOL=16
SELECT_PER_POOL=4
RNG_SEED=720172
K_CHOICES=(5,6,8,10)
CATS=("SOGUK","SERIN","NOTR","ILIK","SICAK")

def source_data(file):
    grouped,issues,malformed=parse_txt(file)
    dates=sorted(d for d,r in grouped.items()
        if len(r)==217 and [row["pos"] for row in r]==list(range(1,218)))
    if len(dates)<72 or dates[71]!=FOCUS_DAY:
        raise ValueError("Expected 12 October 2026 72nd complete day")
    history=[r for d in dates[:71] for r in grouped[d]]
    test=grouped[FOCUS_DAY]
    if len(history)!=15407 or len(test)!=217:
        raise ValueError("Bad 71-day history or 12 Oct target day")
    if test[0]["id"]!=61629 or test[-1]["id"]!=61845:
        raise ValueError("Draw IDs changed")
    return history,test,dates,issues,malformed

def make_prefixes(draws):
    cum=np.zeros((len(draws)+1,80),dtype=np.int32)
    for i,r in enumerate(draws):
        cum[i+1]=cum[i]
        cum[i+1,np.asarray(r["nums"],dtype=int)-1]+=1
    return cum

def features(prefix,t,n):
    """Only observations before index t, never target[t]."""
    f=prefix[t]-prefix[t-n]
    f12=prefix[t]-prefix[t-12]
    f12prior=prefix[t-12]-prefix[t-24]
    trend=f12-f12prior
    previous=prefix[t-12]-prefix[t-12-n]
    current_order=np.lexsort((np.arange(80),f))
    previous_order=np.lexsort((np.arange(80),previous))
    tier=np.empty(80,dtype=np.int8)
    prev_tier=np.empty(80,dtype=np.int8)
    tier[current_order]=np.arange(80)//16
    prev_tier[previous_order]=np.arange(80)//16
    change=tier-prev_tier
    # Once for each target and N, both ranking and movement are frozen.
    return f,f12,trend,tier,prev_tier,change

def draw_pool(features,policy,t,n):
    f,f12,trend,tier,prev,change=features
    pick=[]
    for level in range(5):
        candidates=[b for b in range(80) if tier[b]==level]
        if len(candidates)!=16:raise AssertionError("Not 16 balls in tier")
        if policy=="RISING":
            ranking=sorted(candidates,key=lambda b:(-int(change[b]),
                  -int(trend[b]),-int(f12[b]),-int(f[b]),b))
            selected=ranking[:4]
        elif policy=="COOLING":
            ranking=sorted(candidates,key=lambda b:(int(change[b]),
                  int(trend[b]),int(f12[b]),int(f[b]),b))
            selected=ranking[:4]
        elif policy=="STEADY":
            ranking=sorted(candidates,key=lambda b:(abs(int(change[b])),
                  abs(int(trend[b])),abs(int(f[b])-n/4),b))
            selected=ranking[:4]
        elif policy=="FREQ":
            ranking=sorted(candidates,key=lambda b:(-int(f[b]),
                  -int(f12[b]),-int(trend[b]),b))
            selected=ranking[:4]
        elif policy=="MIXED":
            rising=sorted((b for b in candidates if change[b]>0),
               key=lambda b:(-int(change[b]),-int(trend[b]),-int(f12[b]),b))
            steady=sorted((b for b in candidates if change[b]==0),
               key=lambda b:(-int(f12[b]),-int(f[b]),b))
            cooling=sorted((b for b in candidates if change[b]<0),
               key=lambda b:(int(change[b]),-int(f12[b]),b))
            selected=(rising[:2]+steady[:1]+cooling[:1])
            if len(selected)<4:
                ranking=sorted(candidates,key=lambda b:(-int(trend[b]),
                     -int(f12[b]),-int(f[b]),b))
                selected+= [b for b in ranking if b not in selected][:4-len(selected)]
        elif policy=="RANDOM":
            seed=int.from_bytes(hashlib.sha256(
                f"{RNG_SEED}|{t}|{n}|{level}".encode()).digest()[:8],"big")
            selected=random.Random(seed).sample(candidates,4)
        else:raise ValueError(policy)
        if len(selected)!=4 or len(set(selected))!=4:
            raise AssertionError("Bad pool quota")
        pick+=selected
    assert len(pick)==20 and len(set(pick))==20
    return np.asarray(sorted(pick),dtype=np.int16)

def null_pmf(t,k):
    d=np.array([1.])
    h=np.array([
        (math.comb(k,j)*math.comb(80-k,20-j)/math.comb(80,20))
        if j<=k and j<=20 and (20-j)<=80-k else 0.
        for j in range(k+1)])
    for _ in range(t):d=np.convolve(d,h)
    d=np.maximum(d,0);d/=d.sum()
    return d

def export_csv(z,path,rows,columns=None):
    if columns is None:columns=list(rows[0]) if rows else None
    if not columns:raise ValueError("Missing headers "+path)
    with z.open(path,"w",force_zip64=True) as raw:
        stream=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        writer=csv.DictWriter(stream,fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
        stream.flush();stream.detach()

def run(file,out):
    history,test,dates,issues,malformed=source_data(file)
    pool=history+test
    pp=make_prefixes(pool)
    train_start=len(history)-TRAIN_DAYS*217
    train_end=len(history)
    test_end=len(pool)
    assert train_start>max(LOOKBACKS)+24
    methods=[(n,m) for n in LOOKBACKS for m in POLICIES]
    train_scores={key:[] for key in methods}
    train_day_scores={key:defaultdict(list) for key in methods}
    test_scores={key:[] for key in methods}
    per_target=[]
    identities=[]
    target_quotas=[]
    csv_tickets=[]
    records=[]
    print(f"V72 training last {TRAIN_DAYS} complete days, "
          f"{len(methods)} N+direction methods; testing 12 Oct 217 targets",flush=True)
    for t in range(train_start,test_end):
        row=pool[t]
        label="TRAIN" if t<train_end else "TEST"
        true=np.zeros(80,dtype=np.uint8)
        true[np.asarray(row["nums"],dtype=int)-1]=1
        for n in LOOKBACKS:
            f=f12=trend=tier=prev=change=None
            f,f12,trend,tier,prev,change=feat=features(pp,t,n)
            if label=="TEST":
                counts=np.bincount(tier[true==1],minlength=5)
                target_quotas.append(dict(slot=t-train_end+1,
                    draw_id=row["id"],date=row["day"],lookback=n,
                    quota_cold=int(counts[0]),quota_cool=int(counts[1]),
                    quota_neutral=int(counts[2]),quota_warm=int(counts[3]),
                    quota_hot=int(counts[4]),
                    equal4_target=int(np.all(counts==4))))
                for b in range(80):
                    identities.append(dict(slot=t-train_end+1,
                        draw_id=row["id"],lookback=n,number=b+1,
                        historical_N_occurrences=int(f[b]),
                        last12_occurrences=int(f12[b]),
                        last12_minus_previous12=int(trend[b]),
                        previous_tier=CATS[prev[b]],current_tier=CATS[tier[b]],
                        tier_change=int(change[b]),
                        direction=("UP" if change[b]>0 else "DOWN" if change[b]<0 else "STAY"),
                        target_hit=int(true[b])))
            for method in POLICIES:
                selected=draw_pool(feat,method,t,n)
                got=int(true[selected].sum())
                key=(n,method)
                if label=="TRAIN":
                    train_scores[key].append(got)
                    train_day_scores[key][row["day"]].append(got)
                else:
                    test_scores[key].append(got)
                    is_hit=np.flatnonzero(true[selected]).tolist()
                    csv_tickets.append(dict(date=FOCUS_DAY,
                         slot=t-train_end+1,draw_id=row["id"],clock=row["time"],
                         lookback=n,method=method,
                         selected20=",".join(str(int(b)+1) for b in selected),
                         hits=got,
                         hit_numbers=",".join(str(int(selected[z])+1) for z in is_hit),
                         **{f"pick_{CATS[lev].lower()}":",".join(
                            str(int(b)+1) for b in selected if tier[b]==lev)
                           for lev in range(5)}))
        if t in (train_start,train_start+5*217,train_end-1,train_end,train_end+108,test_end-1):
            print(f"V72 processed day={row['day']} #{row['id']} phase={label}",flush=True)
    assert all(len(train_scores[key])==TRAIN_DAYS*217 for key in methods)
    assert all(len(test_scores[key])==217 for key in methods)
    # Penalize inconsistent days; choose N+method once using TRAIN ONLY.
    standings=[]
    for n,policy in methods:
        key=n,policy
        daymeans=[statistics.mean(v) for d,v in sorted(train_day_scores[key].items())]
        train_mean=statistics.mean(train_scores[key])
        train_day_sd=statistics.stdev(daymeans)
        utility=train_mean-0.25*train_day_sd
        standings.append(dict(lookback=n,method=policy,
            train_mean=round(train_mean,7),train_day_sd=round(train_day_sd,7),
            train_utility=round(utility,7),
            train_days=len(daymeans),train_draws=len(train_scores[key]),
            **{f"train_day_{j+1:02d}":round(val,5) for j,val in enumerate(daymeans)}))
    standings.sort(key=lambda r:(-r["train_utility"],r["lookback"],r["method"]))
    winner=standings[0]
    best_key=(winner["lookback"],winner["method"])
    null=null_pmf(217,20)
    baseline=np.mean([len(set(row["nums"])&
          set(random.Random(int.from_bytes(hashlib.sha256(
             f"{RNG_SEED}|reference|{row['id']}".encode()).digest()[:8],"big"
          )).sample(range(1,81),20)))
          for row in test])
    for v in standings:
        vals=test_scores[v["lookback"],v["method"]]
        total=sum(vals)
        v["test_mean"]=round(total/217,7)
        v["test_hits_total"]=total
        v["test_best_hit"]=max(vals)
        v["test_7plus"]=sum(x>=7 for x in vals)
        v["test_8plus"]=sum(x>=8 for x in vals)
        v["test_10plus"]=sum(x>=10 for x in vals)
        v["test_full20"]=sum(x==20 for x in vals)
        v["test_p_one_sided_vs_fair"]=round(float(null[total:].sum()),8)
        v["test_minus_expected"]=round(total/217-5,7)
    # A fresh independent fair RNG gives fixed-pool exact expectation 5
    # even when selected method was optimized using earlier TRAIN records.
    selected=test_scores[best_key]
    combined=[]
    for size in K_CHOICES:
        for policy in ("HEAT_FIRST","DIRECTION_FIRST"):
            successes=[]
            for t in range(train_end,test_end):
                n,method=best_key
                f,f12,trend,tier,prev,change=feat=features(pp,t,n)
                chosen=draw_pool(feat,method,t,n)
                if policy=="HEAT_FIRST":
                    s=sorted(chosen,key=lambda b:(-int(f[b]),-int(trend[b]),int(b)))[:size]
                else:
                    s=sorted(chosen,key=lambda b:(-int(change[b]),-int(trend[b]),int(b)))[:size]
                target=set(pool[t]["nums"])
                successes.append(sum((int(x)+1) in target for x in s))
            combined.append(dict(ticket_size=size,policy=policy,
                test_217_mean=round(float(np.mean(successes)),6),
                fair_expectation=size/4,
                max_hits=max(successes),
                all_hit=sum(x==size for x in successes),
                distribution=";".join(f"{j}:{successes.count(j)}" for j in range(size+1))))
    # Explicit comparison with fixed N=72 all method variants
    n72=[r for r in standings if r["lookback"]==72]
    best_train_n={}
    for n in LOOKBACKS:
        first=next(v for v in standings if v["lookback"]==n)
        best_train_n[n]=first

    topline=[
       f"V72 | 5x16 ISI HAVUZU -> HER HAVUZDAN 4 SAYI -> TEK 20LI",
       f"Training: {TRAIN_DAYS} previous full days ending 2026-10-11; 2170 draws",
       f"Testing: 12 October 2026, 217 draws #61629..#61845.",
       f"Candidate fixed lookbacks: {','.join(map(str,LOOKBACKS))} draws.",
       f"Strategies: {','.join(POLICIES)}, training {len(methods)} combinations.",
       "Temperature identity is five EQUAL 16-number groups by N-lookback counts.",
       "Movement is CHANGE in tier identity between t-12 and t; plus last12-prev12 trend.",
       "Each method chooses exactly 4 specific numbers from each of five tiers.",
       "Every candidate selection is frozen before opening the actual target draw.",
       "Training window N and method selected on earlier ten days only, NOT on 12 Oct.",
       "Winner is the method maximizing train_mean - 0.25*SD(10 daily means).",
       "",
       f"TRAINING SELECTED: N={best_key[0]}, method={best_key[1]}, "
         f"train_mean={winner['train_mean']:.5f}, stability_penalized={winner['train_utility']:.5f}.",
       f"OCT 12 selected 20-set mean={winner['test_mean']:.5f}/20",
       f"fair expected=5.00000/20, 217-total={winner['test_hits_total']};",
       f"one-sided exact fair-null p={winner['test_p_one_sided_vs_fair']:.6f}; "
         f"random fixed20 test mean={baseline:.5f}.",
       "",
       "PER LOOKBACK, BEST TRAINED METHOD (train choice frozen before target day):",
    ]
    for n in LOOKBACKS:
        row=best_train_n[n]
        topline.append(f"N={n:>3} {row['method']:12} "
          f"train={row['train_mean']:.4f}, test={row['test_mean']:.4f}, "
          f"test7plus={row['test_7plus']}, test8plus={row['test_8plus']}")
    topline+=["","N=72 FIVE BALANCED SELECTORS ON TEST DAY:"]
    for row in n72:
        topline.append(f"{row['method']:12}: {row['test_mean']:.5f}/20 "
          f"(train {row['train_mean']:.5f}; 7plus={row['test_7plus']})")
    topline+=["","SELECTED WINNER: 5/6/8/10 sub-tickets, fixed identity score:",]
    for row in combined:
        topline.append(f"{row['policy']:16} size{row['ticket_size']}:"
          f" {row['test_217_mean']:.5f}, fair {row['fair_expectation']:.2f},"
          f" full-hit count={row['all_hit']}")
    topline+=["",
       "CAUTION: Equal group QUOTAS do not make the actual draw contain 4 from each",
       "and temperature/history cannot alter independent 25% per-ball chance.",
       "Retrospective train/test avoids target leakage, but all these dates",
       "were already explored in earlier research, so not prospective validation.",
       "Report contains identities, transitions, and 217 exact candidate lists.",
       ""]
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        z.writestr("00_KISA_KARAR_V72.txt","\n".join(topline))
        export_csv(z,"01_12_REF_N_X_6_YON_KURAL_TRAIN_VE_217_TEST.csv",standings)
        export_csv(z,"02_HER_N_ICIN_EGITIMDE_SECILEN_EN_IYI_YONTEM.csv",
          [best_train_n[n] for n in LOOKBACKS])
        export_csv(z,"03_217_HEDEF_X_12_PENCERE_X_6_YONTEM_20LI_VE_ISABET.csv",csv_tickets)
        export_csv(z,"04_217_HEDEF_X_12_PENCERE_X_80_SAYI_ISI_YER_YON_KIMLIK.csv",identities)
        export_csv(z,"05_217_HEDEF_X_12_PENCERE_GERCEK_BES_HAVUZ_KOTALARI.csv",target_quotas)
        export_csv(z,"06_WINNERDEN_5_6_8_10_ALT_KUPON.csv",combined)
        z.writestr("07_METHOD_AUDIT.txt","\n".join([
            "20 candidate pool always four numbers from each five equal 16-ball temperature tiers.",
            "Past horizon N only (no future), and N is never dynamically optimized on October 12.",
            "N values:"+",".join(map(str,LOOKBACKS)),
            "Movement: current 16-rank tier compared with its tier exactly 12 previous draws earlier.",
            "Trend: count(last12) - count(previous12). One step once every new target draw.",
            "RISING prefer movement up then short-term trend/activity.",
            "COOLING prefer movement down then short-term decrease.",
            "STEADY prefer remaining in same heat pool and small trend.",
            "FREQ prefer most appearances in N window within each tier.",
            "MIXED prefer per tier 2 rising, 1 stable, 1 cooling (fallback on trend).",
            "RANDOM four per tier using deterministic seed for fair 5x4-balanced control.",
            "Training: ten prior full days, candidate mean-minus-quarter-daily-SD utility.",
            "Frozen N+policy then evaluated on 217 12-October target draws.",
            "Training same 72-day corpus previously researched, test day also previously researched.",
            "V72 does not prove ability to beat an independent 20/80 random generator.",
            "Expected 20 pool hits=20*20/80=5; 10 ticket 2.5; 15 pool 3.75.",
            "ZIP records per-number current pool, previous pool, transition, recent24 trend",
            "and the chosen numbers in each of five tiers for each target."
        ])+"\n")
        z.writestr("08_AUDIT.json",json.dumps(dict(version=VERSION,focus_day=FOCUS_DAY,
             prior_full_days=dates[:71],training_last_dates=dates[71-TRAIN_DAYS:71],
             training_targets=TRAIN_DAYS*217,testing_targets=217,
             fixed_lookbacks=LOOKBACKS,policies=POLICIES,methods_tested=len(methods),
             quotas={k:4 for k in CATS},train_selected=winner,baseline20=baseline,
             winner_ticket_subsets=combined,identity_rows=len(identities),
             pool_rows=len(csv_tickets),quota_rows=len(target_quotas),
             input_issues=issues[:20],bad_lines=malformed[:20]),indent=2,ensure_ascii=False))
    print("\n".join(topline),flush=True)
    print("ZIP",out,out.stat().st_size,flush=True)

def selftest():
    draw=[{"nums":tuple(sorted((j+i)%80+1 for j in range(20)))} for i in range(600)]
    pp=make_prefixes(draw)
    for n in LOOKBACKS:
        f=features(pp,500,n)
        assert np.array_equal(np.bincount(f[3],minlength=5),[16]*5)
        for m in POLICIES:
            got=draw_pool(f,m,500,n)
            assert len(got)==20 and len(set(got))==20
            assert np.array_equal(np.bincount(f[3][got],minlength=5),[4]*5)
    a=null_pmf(10,20)
    assert abs(a.sum()-1)<1e-10
    assert abs(float(np.dot(a,np.arange(len(a))))-50)<1e-8
    print("V72 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--output",default="v72_output/V72_DENGELI_5x4_ISI_YON_HAVUZ_20LI_REF_KARSILASTIRMA.zip")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest()
    else:run(args.source,args.output)
