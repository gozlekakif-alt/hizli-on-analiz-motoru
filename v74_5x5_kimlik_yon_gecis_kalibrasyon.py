#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V74 — empirically learn thermal-pool *transition* hit rates, not just labels.

For each pre-target draw: classify all 80 balls into equally populated 16-ball
quintiles based on the previous N draws, and compare its current identity
to its tier L draws earlier. Train only on first 15 train days to estimate
5x5 origin-to-destination transition rates (or 5x3 current-tier × direction).
Apply shrinkage to 25% theoretical prior. Choose exactly four numbers from
each current tier. Select N, lag L, state model and shrinkage on next 15
VALIDATION days, freeze choices, evaluate on final 15 HOLDOUT days.
Past previously examined: this is chronological reuse, NOT new prospective
evidence. Each result is compared against a tier-balanced random control.
"""
from __future__ import annotations
import argparse,csv,io,json,math,zipfile,statistics
from pathlib import Path
from collections import defaultdict
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V74.1"
N_CHOICES=(12,24,42,56,72,96,144,217,288,432,720,1008)
LAGS=(6,12,24)
KINDS=("TRANS25","DIRECTION15")
PRIOR_STRENGTH=(250,2500)
HEAT=("SOGUK","SERIN","NOTR","ILIK","SICAK")
DIR=("SOGUYOR","SABIT","ISINIYOR")
EARLY_DAYS=27
DAYS_PER_PART=15
PER_DAY=217
PHASELEN=DAYS_PER_PART*PER_DAY
BASE=EARLY_DAYS*PER_DAY
MAXLAG=max(LAGS)
END=(EARLY_DAYS+3*DAYS_PER_PART)*PER_DAY
TARGETS=3*PHASELEN
SEED=741015
RNG_PROB=.25
K=20

def get_data(source):
    data,issues,malformed=parse_txt(source)
    days=sorted(d for d,v in data.items()
                if len(v)==217 and [r["pos"] for r in v]==list(range(1,218)))
    if len(days)<72 or days[71]!="2026-10-12":
        raise RuntimeError("Expected 72 full days 1 Aug..12 Oct in veri.txt")
    days=days[:72]
    draws=[r for d in days for r in data[d]]
    if len(draws)!=72*217 or draws[-217]["id"]!=61629:
        raise RuntimeError("Unexpected complete draws")
    return days,draws,issues,malformed

def prefixify(draws):
    prefix=np.zeros((len(draws)+1,80),dtype=np.int32)
    for t,draw in enumerate(draws):
        prefix[t+1]=prefix[t]
        prefix[t+1,np.asarray(draw["nums"],dtype=int)-1]+=1
    return prefix

def fixed_quintiles(prefix,t,n,numbers):
    counts=prefix[t]-prefix[t-n]
    ix=np.lexsort((numbers,counts))
    tiers=np.empty(80,dtype=np.uint8)
    tiers[ix]=np.arange(80,dtype=np.uint8)//16
    assert int(tiers.sum())==160
    return tiers

def states_of(current,previous,kind):
    if kind=="TRANS25":
        return (current.astype(np.uint8)*5+previous).astype(np.uint8)
    if kind=="DIRECTION15":
        d=np.where(current>previous,2,np.where(current<previous,0,1))
        return (current.astype(np.uint8)*3+d).astype(np.uint8)
    raise ValueError(kind)

def posteriors(train_states,train_outcomes,kind,strength):
    groups=25 if kind=="TRANS25" else 15
    n=np.bincount(train_states.reshape(-1),minlength=groups).astype(np.int64)
    h=np.bincount(train_states.reshape(-1),
                  weights=train_outcomes.reshape(-1),minlength=groups)
    p=(h+RNG_PROB*strength)/(n+strength)
    return p,n,h

def selection(current,states,probs,tiebreak):
    """Vectorised guaranteed 4 from each current 16-identity pool."""
    rows,cols=current.shape
    assert cols==80
    probs=np.asarray(probs,dtype=float)
    scores=probs[states]+1e-9*tiebreak
    chosen=np.zeros((rows,80),dtype=np.uint8)
    r=np.arange(rows)[:,None]
    for level in range(5):
        per_group=np.where(current==level,scores,-1.)
        picks=np.argpartition(per_group,-4,axis=1)[:,-4:]
        assert bool(np.all(current[r,picks]==level))
        chosen[r,picks]=1
    assert bool(np.all(chosen.sum(axis=1)==20))
    assert bool(np.all([np.all((chosen*(current==i)).sum(axis=1)==4)
                       for i in range(5)]))
    return chosen

def measures(hits):
    byday=hits.reshape(-1,PER_DAY).mean(axis=1)
    sd=float(byday.std(ddof=1))
    avg=float(hits.mean())
    return avg,sd,avg-.25*sd

def paired_p(selected,random_mask,y):
    a=(selected*y).sum(axis=1).astype(int)
    b=(random_mask*y).sum(axis=1).astype(int)
    overlap=(selected*random_mask).sum(axis=1).astype(int)
    m=20-overlap
    variance=float(np.sum(2*m*.25*.75*(80/79)))
    total=int((a-b).sum())
    z=total/math.sqrt(variance) if variance>0 else 0
    right=.5*math.erfc(z/math.sqrt(2)) if variance else 1
    return dict(mean_diff=round(float((a-b).mean()),7),
                total_diff=total,paired_z=round(z,6),
                paired_one_sided_p=round(right,7),
                paired_mismatch_sum=int(m.sum()),
                var_under_fair=round(variance,4)),a,b

def fair_p(total,t):
    var=20*.25*.75*(80-20)/79
    z=(total-.5-5*t)/math.sqrt(t*var)
    return round(.5*math.erfc(z/math.sqrt(2)),7)

def make_csv(z,path,rows,cols=None):
    if cols is None:
        if not rows:raise ValueError("No rows "+path)
        cols=list(rows[0])
    with z.open(path,"w",force_zip64=True) as raw:
        s=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        w=csv.DictWriter(s,fieldnames=cols)
        w.writeheader();w.writerows(rows)
        s.flush();s.detach()

def analyse(source,out):
    days,draws,issues,malformed=get_data(source)
    prefix=prefixify(draws)
    start=BASE-MAXLAG
    times=np.arange(start,END,dtype=np.int32)
    t0=BASE-start
    assert t0==MAXLAG
    sizes={"TRAIN":slice(0,PHASELEN),"VALIDATE":slice(PHASELEN,2*PHASELEN),
           "HOLDOUT":slice(2*PHASELEN,3*PHASELEN)}
    outcomes=np.zeros((TARGETS,80),dtype=np.uint8)
    for j in range(TARGETS):
        outcomes[j,np.asarray(draws[BASE+j]["nums"],dtype=int)-1]=1
    assert int(outcomes.sum())==20*TARGETS
    rng=np.random.default_rng(SEED)
    random_order=rng.random((TARGETS,80)).astype(np.float64)
    numids=np.arange(80,dtype=int)
    tierdata={}
    print(f"V74 scan {len(N_CHOICES)} fixed windows x {len(LAGS)} movement horizons",
          f"= {len(N_CHOICES)*len(LAGS)*len(KINDS)*len(PRIOR_STRENGTH)} models",flush=True)
    for n in N_CHOICES:
        arr=np.zeros((len(times),80),dtype=np.uint8)
        for i,t in enumerate(times):
            arr[i]=fixed_quintiles(prefix,int(t),n,numids)
        tierdata[n]=arr
        print("V74 prepared tiers reference N=",n,flush=True)
    trials=[]
    calibrations={}
    for n in N_CHOICES:
        current=tierdata[n][t0:]
        balanced_control=selection(current,current,np.ones(5)*.25,random_order)
        bval=int((balanced_control[sizes["VALIDATE"]]*outcomes[sizes["VALIDATE"]]).sum())
        btest=int((balanced_control[sizes["HOLDOUT"]]*outcomes[sizes["HOLDOUT"]]).sum())
        for lag in LAGS:
            prev=tierdata[n][t0-lag:-lag]
            assert prev.shape==current.shape
            assert current.shape==(TARGETS,80)
            for kind in KINDS:
                st=states_of(current,prev,kind)
                assert st.shape==current.shape
                # A given state is defined by historical data before the target.
                tr=st[sizes["TRAIN"]]
                train_y=outcomes[sizes["TRAIN"]]
                for strength in PRIOR_STRENGTH:
                    fitted,ncounts,nhits=posteriors(tr,train_y,kind,strength)
                    key=(n,lag,kind,strength)
                    sv=selection(current[sizes["VALIDATE"]],st[sizes["VALIDATE"]],
                                 fitted,random_order[sizes["VALIDATE"]])
                    tv=(sv*outcomes[sizes["VALIDATE"]]).sum(axis=1)
                    mean,sd,score=measures(tv)
                    trials.append(dict(lookback=n,movement_lag=lag,state_type=kind,
                        shrinkage=strength,training_samples=int(ncounts.sum()),
                        learned_p_min=round(float(fitted.min()),7),
                        learned_p_max=round(float(fitted.max()),7),
                        val_mean=round(mean,7),val_day_sd=round(sd,7),
                        val_utility=round(score,7),val_total=int(tv.sum()),
                        val_vs_quota_random=round((tv.sum()-bval)/PHASELEN,7),
                        val_random_mean=round(bval/PHASELEN,7),
                        holdout_mean=None,holdout_total=None))
                    calibrations[key]=(fitted,ncounts,nhits)
            print(f"V74 validated: N={n}, lag={lag}",flush=True)
    trials.sort(key=lambda r:(-r["val_utility"],r["lookback"],
                             r["movement_lag"],r["state_type"],r["shrinkage"]))
    win=trials[0]
    n,lag,kind,strength=(win["lookback"],win["movement_lag"],
                          win["state_type"],win["shrinkage"])
    fitted,ncounts,nhits=calibrations[(n,lag,kind,strength)]
    current=tierdata[n][t0:]
    prev=tierdata[n][t0-lag:-lag]
    states=states_of(current,prev,kind)
    test=sizes["HOLDOUT"]
    selected_mask=selection(current[test],states[test],fitted,random_order[test])
    random_mask=selection(current[test],current[test],np.ones(5)*.25,
                          random_order[test])
    pair,hit_model,hit_random=paired_p(selected_mask,random_mask,outcomes[test])
    real_null_p=fair_p(int(hit_model.sum()),PHASELEN)
    mean_brier_model=float(np.mean((fitted[states[test]]-outcomes[test])**2))
    mean_brier_null=float(np.mean((.25-outcomes[test])**2))
    mean_ll_model=float(np.mean(-(outcomes[test]*np.log(fitted[states[test]])
                 +(1-outcomes[test])*np.log(1-fitted[states[test]]))))
    mean_ll_null=-.25*math.log(.25)-.75*math.log(.75)

    # Independently evaluate all fixed N/lag combinations in HOLDOUT ONLY for
    # exploratory stability table; they cannot replace the pre-locked winner.
    heldout_by_n=[]
    for r in trials:
        if (r["state_type"],r["shrinkage"])!=(kind,strength):continue
        nn,ll=r["lookback"],r["movement_lag"]
        rank=tierdata[nn][t0:]
        prev2=tierdata[nn][t0-ll:-ll]
        ss=states_of(rank[test],prev2[test],kind)
        ff=calibrations[(nn,ll,kind,strength)][0]
        mask=selection(rank[test],ss,ff,random_order[test])
        hist=(mask*outcomes[test]).sum(axis=1)
        bm=selection(rank[test],rank[test],np.ones(5)*.25,
                     random_order[test])
        bh=(bm*outcomes[test]).sum(axis=1)
        heldout_by_n.append(dict(lookback=nn,movement_lag=ll,
                test_mean=round(float(hist.mean()),7),
                balanced_random_mean=round(float(bh.mean()),7),
                test_7plus=int((hist>=7).sum()),test_8plus=int((hist>=8).sum()),
                test_9plus=int((hist>=9).sum()),
                selected_on_val=int(nn==n and ll==lag)))
    daily=[]
    chosen_rows=[]
    identity_rows=[]
    profile=[]
    moving=np.where(current[test]>prev[test],2,
             np.where(current[test]<prev[test],0,1)).astype(np.uint8)
    for group in range(5):
        for di in range(3):
            m=(current[test]==group)&(moving==di)
            denominator=int(m.sum())
            hits=int(outcomes[test][m].sum())
            profile.append(dict(current_heat=HEAT[group],movement=DIR[di],
                candidate_num_draws=denominator,
                hits_in_target=hits,
                hit_percent=round(100*hits/denominator,5) if denominator else None,
                fair_hit_percent=25.0))
    cell_rows=[]
    for i in range(5):
        for j in range(5):
            trst=states_of(current[sizes["TRAIN"]],
                           prev[sizes["TRAIN"]],"TRANS25")
            valst=states_of(current[sizes["VALIDATE"]],
                            prev[sizes["VALIDATE"]],"TRANS25")
            testst=states_of(current[test],prev[test],"TRANS25")
            target_cell=i*5+j
            row=dict(from_previous_tier=HEAT[j],to_current_tier=HEAT[i])
            for phase,ss,yy in (
               ("train",trst,outcomes[sizes["TRAIN"]]),
               ("validate",valst,outcomes[sizes["VALIDATE"]]),
               ("holdout",testst,outcomes[test])):
                mm=ss==target_cell
                row[phase+"_opportunities"]=int(mm.sum())
                row[phase+"_hits"]=int(yy[mm].sum())
                row[phase+"_percentage"]=round(100*float(yy[mm].mean()),5) if mm.any() else None
            cell_rows.append(row)
    for j,t in enumerate(range(BASE+2*PHASELEN,END)):
        real=outcomes[test][j]
        sel=selected_mask[j]
        cc=current[test][j]
        prevc=prev[test][j]
        rank=states[test][j]
        h=(hit_model[j])
        rh=(hit_random[j])
        binned=[]
        for i in range(5):
            quartet=[int(b)+1 for b in np.flatnonzero(sel & (cc==i))]
            assert len(quartet)==4
            binned.append(quartet)
        chosen_rows.append(dict(day=draws[t]["day"],draw_id=draws[t]["id"],
          time=draws[t]["time"],position=j+1,lookback=n,lag=lag,
          model=kind,shrinkage=strength,
          selected20=",".join(map(str,np.flatnonzero(sel)+1)),
          isabet=int(h),control_random_isabet=int(rh),
          selected_hit_numbers=",".join(map(str,[int(b)+1 for b in
                                              np.flatnonzero(sel & real)])),
          **{f"havuz_{HEAT[i].lower()}":
             ",".join(map(str,binned[i])) for i in range(5)}))
        for b in range(80):
            identity_rows.append(dict(day=draws[t]["day"],
             draw_id=draws[t]["id"],position=j+1,number=b+1,
             old_pool=HEAT[prevc[b]],now_pool=HEAT[cc[b]],
             pool_shift=int(cc[b])-int(prevc[b]),
             trained_probability=round(float(fitted[rank[b]]),6),
             in_20=int(sel[b]),target_hit=int(real[b])))
    for dayi in range(15):
        lo=dayi*217;hi=lo+217
        a=hit_model[lo:hi];b=hit_random[lo:hi]
        daily.append(dict(day=days[57+dayi],
             chosen_mean=round(float(a.mean()),5),
             balanced_random_mean=round(float(b.mean()),5),
             advantage=round(float(a.mean()-b.mean()),5),
             chosen_7plus=int((a>=7).sum()),chosen_8plus=int((a>=8).sum()),
             chosen_9plus=int((a>=9).sum()),chosen_10plus=int((a>=10).sum())))
    bestv=trials[0]
    recap=[
      "V74 — SAYI KIMLIGI SICAKLIK GECISLERI: 5x5 MATRIS 20'LIK HAVUZ",
      f"Complete history: {days[0]}..{days[-1]} (72 days).",
      f"Warmup first27; TRAIN {days[27]}..{days[41]} 3255 targets.",
      f"VALIDATE {days[42]}..{days[56]} 3255 targets.",
      f"HOLDOUT {days[57]}..{days[71]} 3255 targets.",
      f"N lookback choices {','.join(map(str,N_CHOICES))}; lags {','.join(map(str,LAGS))}.",
      "One row each prior target N: all 80 numbers sorted by appearances into 5x16.",
      "Before each target: old N-quintile L draws ago and current N-quintile.",
      "Only TRAIN outcome rates teach 5x5 transition or 5x3 tier x direction statistics.",
      "Bayesian pseudo-counts tied to fair 25%: alpha 250 or 2500.",
      "Validation chooses a single N, lag, cell-model and shrink strength.",
      "All outputs exactly 4 individual ball IDs from EACH current 16-ball tier.",
      "The same random tie-break ranks are used for fitted model and quota-random.",
      "",
      f"LOCKED: N={n}, LAG={lag}, STATE={kind}, SHRINK={strength}",
      f"Validation picked mean {bestv['val_mean']:.5f}/20; "
       f"balanced control {bestv['val_random_mean']:.5f}/20.",
      f"Final 15-day HOLDOUT selected20 mean {float(hit_model.mean()):.5f}; fair 5.00000.",
      f"Final 15-day HOLDOUT quota-random mean {float(hit_random.mean()):.5f}.",
      f"Paired 5x4 quota-random difference {pair['mean_diff']:+.5f} per draw; "
       f"z={pair['paired_z']:.4f}, p_one_sided={pair['paired_one_sided_p']:.6f}.",
      f"Against fair per-draw 20/80 mean: one-sided approximate p={real_null_p:.6f}.",
      f"Brier per-ball model={mean_brier_model:.9f}; uniform .25={mean_brier_null:.9f}; "
       f"improvement={mean_brier_null-mean_brier_model:+.9f}.",
      f"Logloss per-ball model={mean_ll_model:.9f}; uniform .25={mean_ll_null:.9f}; "
       f"improvement={mean_ll_null-mean_ll_model:+.9f}.",
      f"On holdout, chosen pools 7+={int((hit_model>=7).sum())}; "
       f"8+={int((hit_model>=8).sum())}; "
       f"9+={int((hit_model>=9).sum())}; 10+={int((hit_model>=10).sum())}.",
      "",
      "HOLDOUT conditional observed hit percent for current heat x direction:"]
    for p in profile:
        recap.append(f"{p['current_heat']:6} {p['movement']:8}: "
          f"{p['hits_in_target']}/{p['candidate_num_draws']} "
          f"= {p['hit_percent'] if p['hit_percent'] is not None else '?'}%")
    recap+=["",
      "INFERENCE:",
      "Comparing dozens of N/lag/model candidates on validation is not proof of advantage.",
      "Only pre-validation-frozen training rates applied to locked holdout may be judged.",
      "This whole historical dataset has appeared in earlier investigations, so",
      "the test is chronologically strict but not untouched future data.",
      "A five-pool quota and transition categories don't force or guarantee",
      "any future draw proportions. Standard RNG says each number remains 25%.",
      "Transition probabilities are empirical historical summaries, not RNG source code.",
      "Full ZIP: train-vs-valid-vs-holdout state matrices, 3255x80 movement IDs,",
      "every selected20 and hits, every day, candidate validation leaderboard.",
      ""]
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        z.writestr("00_V74_KISA_KARAR.txt","\n".join(recap))
        make_csv(z,"01_144_N_LAG_MODEL_VALIDATION.csv",trials)
        make_csv(z,"02_TEK_KILITLI_MODELIN_3255_HEDEF_20_SAYISI.csv",chosen_rows)
        make_csv(z,"03_TEK_KILITLI_MODELIN_3255x80_KIMLIK_GECIS.csv",identity_rows)
        make_csv(z,"04_5x5_ORIGIN_DESTINATION_UC_DONEM_ISABET.csv",cell_rows)
        make_csv(z,"05_5x3_ISI_YON_KOTASI_VE_ISABET.csv",profile)
        make_csv(z,"06_TEST_15_GUN_MODELLI_VS_ESIT_RASTGELE.csv",daily)
        make_csv(z,"07_TEK_MODELLI_ALTERNATIF_N_LAG_GORMELIK.csv",heldout_by_n)
        z.writestr("08_METODOLOJI.txt","\n".join([
           "72 day corpus, 27 warmup +15 train +15 validate +15 holdout.",
           "N=12,24,42,56,72,96,144,217,288,432,720,1008 draws.",
           "Lag=6,12,24 draws. All rankings computed from strictly past draws.",
           "Current quintiles and prior quintiles have 16 identities each.",
           "State TRANS25=5*current+previous. DIRECTION15=3*current+sign movement.",
           "Shrinkage pseudo-prior alpha=250 or 2500, p prior 0.25.",
           "Posterior probability (train hits+.25*alpha)/(train opportunities+alpha).",
           "Never use validation/holdout hit outcomes to fit probabilities.",
           "Select exactly four from each current 16-ball tier by highest posterior",
           "with identical fixed random tie-break scores for every method.",
           "Control is unbiased four random numbers from each current tier,",
           "with same seeded random scores for tie breaking.",
           "Method chosen by validation mean-0.25xdaily_SD only, holdout locked.",
           "All 144 combinations described in summary but ONLY one chosen for holdout.",
           "Heldout alternatives also reported for diagnostics only, not model selection.",
           "Conditional paired null calculation based on difference in pool membership.",
           "This is NOT proof of independent random prediction on new future draws.",
           "No p-hacking to force wins, no guaranteed lottery returns."
        ])+"\n")
        z.writestr("09_AUDIT.json",json.dumps(dict(
           version=VERSION,all_complete_days=days,
           train_dates=days[27:42],validation_dates=days[42:57],
           holdout_dates=days[57:72],number_of_candidates=len(trials),
           chosen=dict(n=n,lag=lag,kind=kind,strength=strength),
           winner_validation_score=bestv,
           holdout_model_mean=float(hit_model.mean()),
           holdout_quota_random_mean=float(hit_random.mean()),
           paired_inference=pair,fair_null_one_sided_approx=real_null_p,
           Brier_model=mean_brier_model,Brier_fair=mean_brier_null,
           logloss_model=mean_ll_model,logloss_fair=mean_ll_null,
           input_issues=issues[:20],malformed=malformed[:20]),
           ensure_ascii=False,indent=2))
    print("\n".join(recap),flush=True)
    print("V74 ZIP",str(out),out.stat().st_size,flush=True)

def selftest():
    rng=np.random.default_rng(74)
    random=rng.random((30,80))
    tiers=np.tile((np.arange(80)//16).astype(np.uint8),(30,1))
    old=np.roll(tiers,16,axis=1)
    st=states_of(tiers,old,"TRANS25")
    y=np.zeros((30,80),dtype=np.uint8)
    for i in range(30):
        y[i,rng.choice(80,20,replace=False)]=1
    prob,n,h=posteriors(st,y,"TRANS25",250)
    assert len(prob)==25 and n.sum()==2400 and h.sum()==600
    selected=selection(tiers,st,prob,random)
    assert (selected.sum(axis=1)==20).all()
    assert all((selected*(tiers==q)).sum()==30*4 for q in range(5))
    assert abs(fair_p(100,20)-.5)<.1
    print("V74 SELFTEST OK",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",default="veri.txt")
    parser.add_argument("--out",default="v74_output/V74_5x5_KIMLIK_GECIS_KALIBRASYON_3x15GUN_KOR_TEST.zip")
    parser.add_argument("--selftest",action="store_true")
    args=parser.parse_args()
    if args.selftest:selftest()
    else:analyse(args.source,args.out)
