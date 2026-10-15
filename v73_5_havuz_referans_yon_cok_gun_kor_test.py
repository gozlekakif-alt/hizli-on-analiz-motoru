#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V73 — select one FIXED lookback for 5x4 balanced 20-ball pools.

User question: which historical DRAW count should determine five equally
populated hot-to-cold bins, while actual identities and bin movement choose
FOUR numbers per 16-identity bin?

72 complete dates: days 1..27 warm-up; days 28..42 TRAIN (15 days);
days 43..57 VALIDATE (15 days); days 58..72 HOLDOUT (15 days).
Training fixes a movement policy separately for each lookback;
validation fixes a SINGLE lookback; holdout tests it WITHOUT retuning.
All 15-day periods have 3,255 draws. This is retrospective, because
earlier research examined these dates, not truly prospective evidence.
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
from collections import defaultdict
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V73.1"
N_WINDOWS=(12,24,36,42,56,72,96,120,144,168,217,288,432,576,720,
           864,1008,1440,2160,3024,4340)
RULES=("RISING","COOLING","STEADY","FREQ","MIXED","RANDOM")
RULE_CHOICES=RULES[:-1]
CATS=("SOGUK","SERIN","NOTR","ILIK","SICAK")
N_DAYS=72
PER_DAY=217
WARMUP_DAYS=27
TRAIN_DAYS=VALIDATE_DAYS=HOLDOUT_DAYS=15
assert WARMUP_DAYS+TRAIN_DAYS+VALIDATE_DAYS+HOLDOUT_DAYS==N_DAYS
SEED=730715
ROLL=12
POOL_QUOTA=4
N_PER_TIER=16
K_POOL=20
P_DRAW=.25
VAR_ONE=20*(K_POOL/80)*(1-K_POOL/80)*(60/79)

def data(source):
    parsed,issues,malformed=parse_txt(source)
    dates=sorted(d for d,rows in parsed.items()
             if len(rows)==217 and [r["pos"] for r in rows]==list(range(1,218)))
    if len(dates)<72 or dates[71]!="2026-10-12":
        raise RuntimeError("Expected 72 full ordered days, 1Aug..12Oct")
    dates=dates[:72]
    rows=[r for d in dates for r in parsed[d]]
    if rows[-217]["id"]!=61629 or rows[-1]["id"]!=61845:
        raise RuntimeError("Target 12Oct first/last draw mismatch")
    return dates,rows,issues,malformed

def prefixize(rows):
    pp=np.zeros((len(rows)+1,80),dtype=np.int32)
    for i,row in enumerate(rows):
        pp[i+1]=pp[i]
        pp[i+1,np.asarray(row["nums"],dtype=np.int16)-1]+=1
    return pp

def thermal(pp,t,n):
    """Returns 80 identity features prior to target index t."""
    f=pp[t]-pp[t-n]
    prior=pp[t-ROLL]-pp[t-ROLL-n]
    r=pp[t]-pp[t-ROLL]
    prior12=pp[t-ROLL]-pp[t-ROLL*2]
    trend=r-prior12
    idx=np.arange(80)
    order=np.lexsort((idx,f))
    before=np.lexsort((idx,prior))
    tier=np.empty(80,dtype=np.int8)
    tier_before=np.empty(80,dtype=np.int8)
    tier[order]=np.arange(80,dtype=np.int8)//16
    tier_before[before]=np.arange(80,dtype=np.int8)//16
    drift=tier-tier_before
    groups=[list(map(int,order[16*q:16*q+16])) for q in range(5)]
    return f,r,trend,tier,tier_before,drift,groups

def selected(feat,rule,t,n):
    f,r,trend,tier,prior,drift,groups=feat
    chosen=[]
    for q,group in enumerate(groups):
        if rule=="RISING":
            order=sorted(group,key=lambda b:(-int(drift[b]),-int(trend[b]),
                                             -int(r[b]),-int(f[b]),b))
            picks=order[:4]
        elif rule=="COOLING":
            order=sorted(group,key=lambda b:(int(drift[b]),int(trend[b]),
                                             int(r[b]),int(f[b]),b))
            picks=order[:4]
        elif rule=="STEADY":
            order=sorted(group,key=lambda b:(abs(int(drift[b])),
                         abs(int(trend[b])),abs(int(f[b])-n/4),b))
            picks=order[:4]
        elif rule=="FREQ":
            order=sorted(group,key=lambda b:(-int(f[b]),-int(r[b]),
                                              -int(trend[b]),b))
            picks=order[:4]
        elif rule=="MIXED":
            rising=sorted((b for b in group if drift[b]>0),
                          key=lambda b:(-int(drift[b]),-int(trend[b]),b))
            steady=sorted((b for b in group if drift[b]==0),
                          key=lambda b:(-int(r[b]),-int(f[b]),b))
            falling=sorted((b for b in group if drift[b]<0),
                           key=lambda b:(int(drift[b]),-int(r[b]),b))
            picks=rising[:2]+steady[:1]+falling[:1]
            if len(picks)<4:
                others=sorted(group,key=lambda b:(-int(trend[b]),-int(r[b]),
                                                  -int(f[b]),b))
                picks += [b for b in others if b not in picks][:4-len(picks)]
        elif rule=="RANDOM":
            seed=int.from_bytes(hashlib.sha256(
                 f"{SEED}|{t}|{n}|{q}".encode()).digest()[:8],"big")
            picks=random.Random(seed).sample(group,4)
        else:raise ValueError(rule)
        if len(picks)!=4 or len(set(picks))!=4:raise AssertionError("Invalid quota")
        chosen.extend(picks)
    if len(chosen)!=20 or len(set(chosen))!=20:raise AssertionError("Invalid total")
    return np.asarray(sorted(chosen),dtype=np.int8)

def moments(daymeans):
    mu=float(np.mean(daymeans))
    sd=float(np.std(daymeans,ddof=1))
    return mu,sd,mu-.25*sd

def right_normal_p(total,n):
    expected=5*n
    variance=VAR_ONE*n
    return 0.5*math.erfc((total-expected-.5)/math.sqrt(2*variance))

def pairwise_p(diffs,missing):
    # For k=20 sets A,B with overlap (20-m), X_A-X_B is sum
    # of m positive and m negative individual draw indicators.
    # Given the two fixed sets before a fair draw:
    # E(diff)=0 and Var(diff)=(2*m)*p(1-p)*80/79.
    d=sum(diffs)
    variance=sum(2*m*.25*.75*(80/79) for m in missing)
    z=d/math.sqrt(variance) if variance>0 else 0.
    return z,0.5*math.erfc(z/math.sqrt(2)) if variance>0 else 1.0

def cwrite(z,path,rows,headers=None):
    if headers is None:
        if not rows:raise ValueError("Missing rows and headers "+path)
        headers=list(rows[0])
    with z.open(path,"w",force_zip64=True) as raw:
        stream=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        writer=csv.DictWriter(stream,fieldnames=headers)
        writer.writeheader()
        for item in rows:writer.writerow(item)
        stream.flush();stream.detach()

def analyse(src,out):
    dates,rows,issues,malformed=data(src)
    pp=prefixize(rows)
    phase_start={
       "TRAIN":WARMUP_DAYS*PER_DAY,
       "VALIDATE":(WARMUP_DAYS+TRAIN_DAYS)*PER_DAY,
       "HOLDOUT":(WARMUP_DAYS+TRAIN_DAYS+VALIDATE_DAYS)*PER_DAY}
    phase_end={
       "TRAIN":phase_start["VALIDATE"],
       "VALIDATE":phase_start["HOLDOUT"],
       "HOLDOUT":N_DAYS*PER_DAY}
    keys=[(n,rule) for n in N_WINDOWS for rule in RULES]
    # store per-method daily total hits and successes over threshold
    totals={phase:defaultdict(lambda:np.zeros((15,5),dtype=np.int64))
            for phase in phase_start}
    # rows per day have entries total hits, 7+, 8+, 9+, 10+
    # 15 days per split
    test_by_method={}
    val_by_method={}
    train_by_method={}
    print(f"V73 start 72 complete days; train/val/holdout={TRAIN_DAYS}/{VALIDATE_DAYS}/{HOLDOUT_DAYS} "
          f"days; windows={len(N_WINDOWS)}; policies={len(RULES)}",flush=True)
    for t in range(phase_start["TRAIN"],phase_end["HOLDOUT"]):
        phase=("TRAIN" if t<phase_end["TRAIN"]
              else "VALIDATE" if t<phase_end["VALIDATE"] else "HOLDOUT")
        ix=(t-phase_start[phase])//PER_DAY
        y=np.zeros(80,dtype=np.int8)
        y[np.asarray(rows[t]["nums"],dtype=int)-1]=1
        for n in N_WINDOWS:
            feat=thermal(pp,t,n)
            for rule in RULES:
                picks=selected(feat,rule,t,n)
                hit=int(y[picks].sum())
                target=totals[phase][(n,rule)][ix]
                target[0]+=hit
                for j,cutoff in enumerate((7,8,9,10),start=1):
                    if hit>=cutoff:target[j]+=1
        if (t+1-phase_start["TRAIN"])%PER_DAY==0:
            di=(t+1)//PER_DAY
            print(f"V73 processed day {di}/72 | {rows[t]['day']} | stage={phase}",flush=True)
    assert len(totals["TRAIN"])==len(keys)
    model_rows=[]
    for n,rule in keys:
        row=dict(lookback=n,rule=rule)
        for phase in phase_start:
            blocks=totals[phase][(n,rule)]
            day_avgs=blocks[:,0]/PER_DAY
            avg,sd,utility=moments(day_avgs)
            row[phase.lower()+"_mean"]=round(avg,7)
            row[phase.lower()+"_daily_sd"]=round(sd,7)
            row[phase.lower()+"_utility"]=round(utility,7)
            row[phase.lower()+"_total_hits"]=int(blocks[:,0].sum())
            row[phase.lower()+"_7plus"]=int(blocks[:,1].sum())
            row[phase.lower()+"_8plus"]=int(blocks[:,2].sum())
            row[phase.lower()+"_9plus"]=int(blocks[:,3].sum())
            row[phase.lower()+"_10plus"]=int(blocks[:,4].sum())
        model_rows.append(row)
    lookup={(v["lookback"],v["rule"]):v for v in model_rows}
    choose_policy={}
    for n in N_WINDOWS:
        policy=max((rule for rule in RULE_CHOICES),
                   key=lambda rule:(lookup[(n,rule)]["train_utility"],-RULE_CHOICES.index(rule)))
        choose_policy[n]=policy
    # CHOOSE N from validation data only. No holdout used to pick any rule.
    winning_n=max(N_WINDOWS,key=lambda n:(
             lookup[(n,choose_policy[n])]["validate_utility"],
             -N_WINDOWS.index(n)))
    winner=(winning_n,choose_policy[winning_n])
    selection_row=lookup[winner]
    best_by_n=[dict(**lookup[(n,choose_policy[n])],selected_rule_from_train=choose_policy[n],
                   selected_on_validation=int(n==winning_n)) for n in N_WINDOWS]

    # Holdout one winner vs within-tier RANDOM at identical N;
    # independence justified under independent fair draws.
    paired_diffs=[];missing=[];winner_scores=[]
    selected_rows=[];tier_quota_rows=[];identity_info=[]
    direction_counts=np.zeros((5,3),dtype=int)
    direction_hits=np.zeros((5,3),dtype=int)
    test_start=phase_start["HOLDOUT"]
    for t in range(test_start,phase_end["HOLDOUT"]):
        target=rows[t]
        f,r,trend,tier,tier_prev,drift,groups=feat=thermal(pp,t,winning_n)
        chosen=selected(feat,winner[1],t,winning_n)
        random_pool=selected(feat,"RANDOM",t,winning_n)
        true=np.zeros(80,dtype=np.uint8)
        true[np.asarray(target["nums"],dtype=int)-1]=1
        hit=int(true[chosen].sum())
        random_hit=int(true[random_pool].sum())
        winner_scores.append(hit)
        paired_diffs.append(hit-random_hit)
        missing.append(20-len(set(map(int,chosen))&set(map(int,random_pool))))
        ix=t-test_start+1
        by_tier=[]
        selected_numbers_by_tier=[]
        for q in range(5):
            observed=int(np.count_nonzero(true[tier==q]))
            mine=[int(x)+1 for x in chosen if tier[x]==q]
            assert len(mine)==4
            selected_numbers_by_tier.append(mine)
            by_tier.append(observed)
            for b in range(80):
                if tier[b]==q:
                    k=0 if drift[b]<0 else 1 if drift[b]==0 else 2
                    direction_counts[q,k]+=1
                    direction_hits[q,k]+=int(true[b])
        selected_rows.append(dict(day=target["day"],time=target["time"],
           slot=ix,draw_id=target["id"],lookback=winning_n,
           frozen_rule=winner[1],
           chosen20=",".join(str(int(x)+1) for x in chosen),
           hits=hit,random_5x4_hits=random_hit,
           hit_numbers=",".join(str(int(x)+1) for x in chosen if true[x]),
           **{f"selected_{CATS[q].lower()}":
               ",".join(map(str,selected_numbers_by_tier[q])) for q in range(5)},
           **{f"actual_{CATS[q].lower()}":by_tier[q] for q in range(5)}))
        tier_quota_rows.append(dict(day=target["day"],slot=ix,draw_id=target["id"],
                     **{CATS[q].lower():by_tier[q] for q in range(5)}))
        # Full 80 identities, previous and current tiers, and movement
        for b in range(80):
            identity_info.append(dict(day=target["day"],draw_id=target["id"],
               slot=ix,number=b+1,lookback=winning_n,
               historical_hits=int(f[b]),previous_tier=CATS[int(tier_prev[b])],
               current_tier=CATS[int(tier[b])],tier_delta=int(drift[b]),
               last12_hits=int(r[b]),last12_minus_previous12=int(trend[b]),
               picked_in20=int(b in chosen),real_target_hit=int(true[b])))
    assert len(selected_rows)==len(tier_quota_rows)==3255
    zpair,pone=pairwise_p(paired_diffs,missing)
    holdout_p_fair=right_normal_p(sum(winner_scores),len(winner_scores))
    day_comparison=[]
    random_blocks=totals["HOLDOUT"][(winning_n,"RANDOM")]
    selected_blocks=totals["HOLDOUT"][winner]
    for i in range(15):
        day=dates[57+i]
        day_comparison.append(dict(
             day=day,lookback=winning_n,method=winner[1],
             selected_20_mean=round(selected_blocks[i,0]/PER_DAY,5),
             balanced_random_20_mean=round(random_blocks[i,0]/PER_DAY,5),
             selected_7plus=int(selected_blocks[i,1]),
             balanced_random_7plus=int(random_blocks[i,1]),
             selected_8plus=int(selected_blocks[i,2]),
             balanced_random_8plus=int(random_blocks[i,2]),
             mean_gain_over_random=round((selected_blocks[i,0]-random_blocks[i,0])/PER_DAY,5)))
    direction_table=[]
    for q in range(5):
        for r_idx,movement in enumerate(("COOLING","STEADY","RISING")):
            a=direction_counts[q,r_idx];b=direction_hits[q,r_idx]
            direction_table.append(dict(tier=CATS[q],movement=movement,
              candidate_opportunities=int(a),number_hits=int(b),
              hit_rate=round(b/a,6) if a else None,fair_rate=.25))
    key_summary=[
      "V73 — 5x4 DENGELI 20LI ICIN KAC GECMIS CEKILISI REFERANS?",
      f"History: 72 full days, 01 Aug 2026 through 12 Oct 2026.",
      f"Training: 15 complete days, {dates[27]}..{dates[41]}, 3255 targets.",
      f"Validation: 15 complete days, {dates[42]}..{dates[56]}, 3255 targets.",
      f"Holdout: 15 complete days, {dates[57]}..{dates[71]}, 3255 targets.",
      f"N candidates={','.join(map(str,N_WINDOWS))}.",
      f"Rules={','.join(RULES)} (RANDOM is an independently seeded within-tier control).",
      "For every next draw: previous N draws define 5x16 hot/cold tiers.",
      "Previous tier = heat identity 12 draws earlier; direction=tier now minus before.",
      "Inside each 16-ball pool choose exactly 4 ball IDs using a frozen movement rule.",
      "First TRAIN chooses a rule per N; then VALIDATE selects just one N;",
      "then HOLDOUT is inspected once only, without model reselection.",
      "Selection utility = mean hits minus 0.25 x SD of daily mean hits.",
      "",
      f"LOCKED N: {winning_n} prior draws.",
      f"LOCKED DIRECTION RULE: {winner[1]}.",
      f"TRAIN: {selection_row['train_mean']:.5f}/20",
      f"VALIDATE: {selection_row['validate_mean']:.5f}/20",
      f"HOLDOUT: {selection_row['holdout_mean']:.5f}/20; fair expected 5/20.",
      f"HOLDOUT BALANCED RANDOM N={winning_n}: {lookup[(winning_n,'RANDOM')]['holdout_mean']:.5f}/20.",
      f"Paired selected-RANDOM mean gain={sum(paired_diffs)/3255:+.5f}/20; z={zpair:.4f}, one-sided p={pone:.6f}.",
      f"Vs independent fair 5/20 null: one-sided normal-tail p={holdout_p_fair:.6f}.",
      f"Holdout selected 7+: {selection_row['holdout_7plus']}, 8+: {selection_row['holdout_8plus']},"
         f" 9+: {selection_row['holdout_9plus']}, 10+: {selection_row['holdout_10plus']}.",
      "",
      "EACH N: prechosen TRAIN direction policy, VALIDATION and HOLDOUT mean:"
    ]
    for row in best_by_n:
        key_summary.append(
         f"N={row['lookback']:>4} {row['rule']:8} "
         f"TRAIN={row['train_mean']:.5f}; VAL={row['validate_mean']:.5f}; "
         f"HOLDOUT={row['holdout_mean']:.5f}; "
         f"RANDOM={lookup[(row['lookback'],'RANDOM')]['holdout_mean']:.5f}; "
         +("**PRELOCK WINNER**" if row["selected_on_validation"] else ""))
    key_summary +=[
      "",
      "NOTES",
      "Any chosen rule, however elaborate, averages 5 hits / 20 under independent fair RNG.",
      "Movement directions can describe the past without predicting unseen numbers.",
      "This sample was previously researched, so the holdout is CHRONOLOGIC not",
      "a genuinely new untouched prospective data set; don't claim a winning edge.",
      "RNG comparison here uses hypergeometric normal-CLT and paired exact",
      "conditional variance; fresh post-lock data would be necessary for proof.",
      "Check the per-number full identity and 15-day/daywise CSV audit tables.",
      ""
    ]
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        z.writestr("00_V73_KISA_SONUC.txt","\n".join(key_summary))
        cwrite(z,"01_21_N_X_6_YON_3_DONEM_TAM_SONUC.csv",model_rows)
        cwrite(z,"02_HER_REFERANS_ICIN_TRAIN_SECILI_YON_VAL_TEST.csv",best_by_n)
        cwrite(z,"03_KILITLENEN_YONTEM_3255_TEK_TEK_HEDEF_20LI.csv",selected_rows)
        cwrite(z,"04_KILITLENEN_YONTEM_3255_X_80_SAYI_KIMLIK_YON.csv",identity_info)
        cwrite(z,"05_15_TEST_GUNLUK_RASTGELE_KARSILASTIRMA.csv",day_comparison)
        cwrite(z,"06_3255_GERCEK_BES_HAVUZ_KOTASI.csv",tier_quota_rows)
        cwrite(z,"07_ISI_X_YON_ISABETI.csv",direction_table)
        z.writestr("08_YONTEM.txt","\n".join([
           "Train, validation, holdout are distinct chronological 15-day periods.",
           "First 27 complete days warm up moving N, max4340, +12 movement features.",
           "One selection 4x5 made before every one of the 9,765 targets.",
           "Under fair independent RNG, ANY frozen twenty ball selection has expected 5 hits.",
           "Movement: compare today's latest N frequencies to past same N ending 12 draws earlier.",
           "RISING maximises positive tier shift then positive last12-prior12 trend.",
           "COOLING minimises tier shift then recent trend.",
           "STEADY minimises absolute tier shift, abs trend, abs difference to expectation.",
           "FREQ picks high frequency inside each of five 16-ball tiers.",
           "MIXED prefers 2 rising, 1 stable, 1 cooling within tier if feasible.",
           "RANDOM uses SHA256-seeded sample of four from EACH tier.",
           "Training chooses one nonrandom rule per N by mean-0.25*daily_sd.",
           "Validation chooses one N, the remaining holdout is checked without retuning.",
           "Paired null test uses conditional variance based on overlapping predicted sets.",
           "When comparing many different N performances on HOLDOUT, only the",
           "validation-selected N is eligible for unadjusted confirmatory inference.",
           "Data previously examined in V68-V72, so holdout isn't truly untouched.",
           "No promise of 10/10 forecast from such statistical histories."
        ])+"\n")
        z.writestr("09_AUDIT.json",json.dumps(dict(
           version=VERSION,dates=dates,train_days=dates[27:42],
           validation_days=dates[42:57],holdout_days=dates[57:72],
           days_each=15,draws_each=3255,lookbacks=N_WINDOWS,rules=RULES,
           selection=winner,train_model_utility=selection_row['train_utility'],
           validation_model_utility=selection_row['validate_utility'],
           holdout_mean=selection_row['holdout_mean'],
           holdout_random_mean=lookup[(winning_n,"RANDOM")]['holdout_mean'],
           paired_one_sided_p=pone,paired_z=zpair,
           fair_one_sided_p=holdout_p_fair,
           quotas={s:4 for s in CATS},
           parse_issues=issues[:20],malformed=malformed[:20]),indent=2,ensure_ascii=False))
    print("\n".join(key_summary),flush=True)
    print("V73 ZIP",str(out),out.stat().st_size,flush=True)

def selftest():
    rng=random.Random(5)
    draws=[]
    for _ in range(4600):
        draws.append({"nums":sorted(rng.sample(range(1,81),20))})
    pp=prefixize(draws)
    for n in N_WINDOWS:
        feat=thermal(pp,4450,n)
        assert np.array_equal(np.bincount(feat[3],minlength=5),[16]*5)
        assert all(len(g)==16 for g in feat[6])
        for rule in RULES:
            chosen=selected(feat,rule,4450,n)
            assert len(set(chosen))==20
            assert np.array_equal(np.bincount(feat[3][chosen],minlength=5),[4]*5)
    expected=VAR_ONE
    assert 2.7<expected<3.0
    d=[0,1,0,-1];m=[3,6,7,0]
    z,p=pairwise_p(d,m)
    assert z==0 and abs(p-.5)<1e-12
    print("V73 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v73_output/V73_5x4_REFERANS_YON_15GUN_EGITIM_15GUN_DOGRULAMA_15GUN_TEST.zip")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:selftest()
    else:analyse(a.source,a.out)
