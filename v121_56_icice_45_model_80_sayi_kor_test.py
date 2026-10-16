#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V121 exploratory multi-method number-only target prediction research.

56 genuinely NESTED trailing cumulative windows 12,24,...,672;
80 candidate numbers; NO FAMILY member definitions at all.
All scores use past draws strictly before each unseen target.
TRAIN first36 days; RIDGE fitted on TRAIN only; VALIDATE next18
chooses exactly ONE k=10 strategy; HOLDOUT last18 scores that
unchanged winner on every size k=3,4,5,6,7,8,9,10,20.
But these calendar draws have been studied in prior V9-V120 experiments,
so HOLDOUT is script-internal, NOT genuinely prospective.

16 seeded random controls, HOT72, multiple physical 1/0 and 56
cumulative pool-class path candidates. Never tune selection using holdout.
"""
from __future__ import annotations
import argparse,csv,io,json,random,zipfile,collections,hashlib
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load

LENS=np.arange(12,673,12,dtype=np.int32)
assert len(LENS)==56 and LENS[-1]==672
KS=(3,4,5,6,7,8,9,10,20)
LOCK_K=10
SEED=12120261017
MODELS=(
    "HOT12","HOT24","HOT72","HOT144","HOT672",
    "COLD12","COLD72","COLD672",
    "SHORT_UP_LONG","SHORT_DOWN_LONG",
    "SHORT_UP_MID","SHORT_DOWN_MID",
    "EXTREME_HOT_COLD","EXTREME_COLD_HOT",
    "REBOUND_SHORT","REBOUND_LONG",
    "RANK_STABLE","RANK_VOLATILE","SAMEPOOL_CONSENSUS",
    "BURST_12_VS_PREV60","BURST_24_VS_PREV120",
    "ACCEL_12_24","LAG12_ECHO","LAG5_ECHO",
    "LAST_DRAW_REPEAT","LAST_DRAW_SKIP","GAP_OVERDUE",
    "RIDGE_TRAIN36","HOT72_BASE")
assert len(MODELS)==29
N_RANDOM=16
COLS=MODELS+tuple("RANDOM_%02d"%i for i in range(N_RANDOM))
IDX={m:i for i,m in enumerate(COLS)}
PHS=("TRAIN36","VALIDATE18","HOLDOUT18","EXTRA")
PHIDX={v:i for i,v in enumerate(PHS)}
PERF_STAT=8  # n, total correct, perfect, >=5, >=6, >=7, >=8, >=9, >=10
THEORY={k:k/4 for k in KS}

def writecsv(z,path,recs):
    if not recs:return
    with z.open(path,"w",force_zip64=True) as raw:
        f=io.TextIOWrapper(raw,encoding="utf-8-sig",newline="")
        w=csv.DictWriter(f,fieldnames=list(recs[0]))
        w.writeheader();w.writerows(recs);f.flush();f.detach()

def frame(P,X,t):
    """Each of 56 lookback lengths ends just BEFORE t."""
    cnt=P[t][None,:]-P[t-LENS]
    assert cnt.shape==(56,80)
    assert int(cnt[-1].sum())==672*20
    order=np.argsort(cnt,axis=1,kind="stable")
    pools=np.empty((56,80),dtype=np.int8)
    pools[np.arange(56)[:,None],order]=np.repeat(np.arange(5,dtype=np.int8),16)
    p=pools.astype(float)
    d=np.diff(p,axis=0)
    short=p[:6].mean(axis=0)
    mid=p[6:18].mean(axis=0)
    long=p[-6:].mean(axis=0)
    vals=(cnt[0].astype(float),cnt[1].astype(float),
          cnt[5].astype(float),cnt[11].astype(float),
          cnt[-1].astype(float))
    c12,c24,c72,c144,c672=vals
    since=X[t-72:t]
    b12=X[t-12:t]
    b6=X[t-6:t]
    last_gap=np.where(since.any(axis=0),
                       np.argmax((since[::-1]>0),axis=0),72).astype(float)
    lags12=sum(X[t-i] for i in (12,24,36,48,60,72)).astype(float)
    lags5=sum(X[t-i] for i in (5,10,15,20,25,30,35,40,45,50,55,60)).astype(float)
    eps=(80-np.arange(80))*1e-7
    two_ends=p[0]-p[-1]
    mean_turn=np.mean(np.abs(d),axis=0)
    bump=c12-(c72-c12)/5.
    burst24=c24-(c144-c24)/5.
    signs=np.sign(d)
    reversal=np.sum(signs[:-1]*signs[1:]==-1,axis=0)
    # Purely pretarget, fixed predetermined score shapes:
    score={
       "HOT12":c12,
       "HOT24":c24,
       "HOT72":c72,
       "HOT144":c144,
       "HOT672":c672,
       "COLD12":-c12,
       "COLD72":-c72,
       "COLD672":-c672,
       "SHORT_UP_LONG":short-long,
       "SHORT_DOWN_LONG":long-short,
       "SHORT_UP_MID":short-mid,
       "SHORT_DOWN_MID":mid-short,
       "EXTREME_HOT_COLD":((p[-1]==4)&(p[0]==0)).astype(float),
       "EXTREME_COLD_HOT":((p[-1]==0)&(p[0]==4)).astype(float),
       "REBOUND_SHORT":p[0]-2*p[5]+p[11],
       "REBOUND_LONG":p[0]-2*p[11]+p[-1],
       "RANK_STABLE":-p.var(axis=0),
       "RANK_VOLATILE":p.var(axis=0),
       "SAMEPOOL_CONSENSUS":(p>=3).sum(axis=0).astype(float),
       "BURST_12_VS_PREV60":bump,
       "BURST_24_VS_PREV120":burst24,
       "ACCEL_12_24":2*c12-c24,
       "LAG12_ECHO":lags12,
       "LAG5_ECHO":lags5,
       "LAST_DRAW_REPEAT":X[t-1].astype(float),
       "LAST_DRAW_SKIP":1-X[t-1].astype(float),
       "GAP_OVERDUE":last_gap,
       "HOT72_BASE":c72,
    }
    # Regularized regression features use ONLY prior draw status.
    features=np.stack([
      np.ones(80),
      c12/12.,c24/24.,c72/72.,c144/144.,c672/672.,
      p[0]/4.,p[5]/4.,p[-1]/4.,
      (short-long)/4.,
      (p[0]-2*p[5]+p[11])/8.,
      mean_turn/4.,
      reversal/55.,
      bump/12.,
      b6.sum(axis=0)/6.,
      X[t-1].astype(float),X[t-12].astype(float),
      lags12/6.,lags5/12.,last_gap/72.,
    ],axis=1).astype(float)
    assert features.shape==(80,20)
    return score,features,cnt,pools

def rand_pick(t,seed,k=20):
    return np.asarray(
        random.Random(SEED+t*18271+seed*100927).sample(range(80),k),
        dtype=np.int16)

def winner_from_validation(perf):
    # Predeclared selection metric: highest mean hits per ticket of size 10
    # on VALIDATE18. NEVER read HOLDOUT data to determine model.
    j=PHIDX["VALIDATE18"]
    ki=KS.index(LOCK_K)
    stats=[]
    for m in MODELS:
        a=perf[j,IDX[m],ki]
        if a[0]==0:continue
        stats.append((float(a[1]/a[0]),m))
    # Fixed lexical tie break
    stats.sort(key=lambda z:(-z[0],z[1]))
    return stats[0][1],stats

def main(source,out):
    days,rows,X,issues,bad=load(source)
    n=len(X)
    assert len(rows)==n and n>672 and (X.sum(axis=1)==20).all()
    P=np.vstack((np.zeros((1,80),dtype=np.int32),
                 np.cumsum(X,dtype=np.int32,axis=0)))
    full_days=sorted(d for d in days if d<="2026-10-12")
    assert len(full_days)==72
    phases={d:("TRAIN36" if i<36 else
                 "VALIDATE18" if i<54 else "HOLDOUT18")
            for i,d in enumerate(full_days)}
    # Fit linear ridge ONLY on TRAIN36, before validation.
    xtx=np.zeros((20,20),dtype=np.float64)
    xty=np.zeros(20,dtype=np.float64)
    train_target=0
    for t in range(672,n):
        if phases.get(rows[t]["day"],"EXTRA")!="TRAIN36": continue
        _sc,features,_ct,_pp=frame(P,X,t)
        xtx+=features.T@features
        xty+=features.T@X[t].astype(float)
        train_target+=1
    assert train_target==7140
    l2=1000.
    reg=l2*np.eye(20)
    reg[0,0]=0.
    beta=np.linalg.solve(xtx+reg,xty)
    assert np.isfinite(beta).all()
    # Pre-registered per-method equal-budget scorecard.
    perf=np.zeros((len(PHS),len(COLS),len(KS),9),dtype=np.int64)
    by_day=collections.defaultdict(lambda:[0,0])
    winning_detail=[]
    output_records=[]
    last_profile=[]
    phase_targets=collections.Counter()
    for t in range(672,n):
        date=rows[t]["day"]
        ph=phases.get(date,"EXTRA")
        phidx=PHIDX[ph]
        actual=X[t]
        sc,F,counts,pool=frame(P,X,t)
        sc["RIDGE_TRAIN36"]=F@beta
        assert set(sc)==set(MODELS)
        chosen={}
        for model in MODELS:
            vals=sc[model]
            # Stable ordering; smallest number breaks ties.
            picked=np.lexsort((np.arange(80),-vals))[:20]
            chosen[model]=picked
        for rseed in range(N_RANDOM):
            chosen["RANDOM_%02d"%rseed]=rand_pick(t,rseed,20)
        phase_targets[ph]+=1
        for model in COLS:
            pick=chosen[model]
            hits=actual[pick].astype(np.int8)
            prefix=np.cumsum(hits)
            row=dict(date=date,target_id=rows[t]["id"],phase=ph,
                model=model,
                selected20="-".join(str(x+1) for x in pick),
                drawn_01_20="".join(map(str,hits)))
            for ki,k in enumerate(KS):
                h=int(prefix[k-1])
                st=perf[phidx,IDX[model],ki]
                st[0]+=1
                st[1]+=h
                st[2]+=int(h==k)
                st[3]+=int(h>=5)
                st[4]+=int(h>=6)
                st[5]+=int(h>=7)
                st[6]+=int(h>=8)
                st[7]+=int(h>=9)
                st[8]+=int(h>=10)
                if ph in ("VALIDATE18","HOLDOUT18"):
                    daily=by_day[(ph,date,model,k)]
                    daily[0]+=h
                    daily[1]+=1
                row["hits_"+str(k)]=h
            output_records.append(row)
        if t==n-1:
            for b in range(80):
                last_profile.append(dict(number=b+1,
                    target_id=rows[t]["id"],
                    historical_672bits="".join(str(int(x)) for x in X[t-672:t,b]),
                    all56_12_24_672_counts="|".join(map(str,counts[:,b])),
                    all56_pools_12_24_672="".join("CSNIH"[v] for v in pool[:,b]),
                    last12=int(counts[0,b]),last72=int(counts[5,b]),
                    last672=int(counts[-1,b]),
                    appeared_target=int(actual[b])))
        if (t-671)%2000==0:
            print("V121 target",t-671,"/",n-672,flush=True)
    assert len(output_records)==(n-672)*len(COLS)
    assert sum(phase_targets.values())==n-672
    # Select winner once using VALIDATE18's 10-number mean only.
    winner,validation_rank=winner_from_validation(perf)
    budget_report=[]
    for phase in ("VALIDATE18","HOLDOUT18","EXTRA"):
        pidx=PHIDX[phase]
        for kidx,k in enumerate(KS):
            for method in (winner,"HOT72_BASE","HOT12","HOT672",
                           "SHORT_UP_LONG","SHORT_DOWN_LONG",
                           "RIDGE_TRAIN36"):
                v=perf[pidx,IDX[method],kidx]
                if not v[0]:continue
                budget_report.append(dict(phase=phase,method=method,
                    ticket_size=k,targets=int(v[0]),
                    average_hits=round(v[1]/v[0],6),
                    theoretical_mean=k/4,
                    exact_k_of_k=int(v[2]),hits5plus=int(v[3]),
                    hits6plus=int(v[4]),hits7plus=int(v[5]),
                    hits8plus=int(v[6]),hits9plus=int(v[7]),
                    hits10plus=int(v[8]),
                    selected_on_validation=(method==winner)))
            # 16 random seeds same number of tickets => averaged control,
            # retain all realized random events for detailed reproducibility.
            rv=np.stack([perf[pidx,IDX["RANDOM_%02d"%r],kidx]
                        for r in range(N_RANDOM)])
            if not rv[0,0]:continue
            budget_report.append(dict(phase=phase,method="RANDOM16_MEAN",
                    ticket_size=k,targets=int(rv[0,0]),
                    average_hits=round(rv[:,1].sum()/rv[:,0].sum(),6),
                    theoretical_mean=k/4,
                    exact_k_of_k=round(float(rv[:,2].mean()),3),
                    hits5plus=round(float(rv[:,3].mean()),3),
                    hits6plus=round(float(rv[:,4].mean()),3),
                    hits7plus=round(float(rv[:,5].mean()),3),
                    hits8plus=round(float(rv[:,6].mean()),3),
                    hits9plus=round(float(rv[:,7].mean()),3),
                    hits10plus=round(float(rv[:,8].mean()),3),
                    selected_on_validation=False))
    validation_rows=[]
    for rank,(mean,model) in enumerate(validation_rank,1):
        hold=perf[PHIDX["HOLDOUT18"],IDX[model],KS.index(10)]
        validation_rows.append(dict(validation_rank=rank,model=model,
            validation_10_mean=round(float(mean),6),
            validation_10_samples=int(phase_targets["VALIDATE18"]),
            holdout_10_mean=round(hold[1]/hold[0],6),
            holdout_10_hits5plus=int(hold[3]),
            holdout_10_hits6plus=int(hold[4]),
            holdout_10_hits8plus=int(hold[6]),
            holdout_10_hits10of10=int(hold[2]),
            selected_before_holdout=(model==winner)))
    # Daily cluster bootstrap for precommitted selected winner.
    diff_summary=[]
    hold_dates=sorted(d for d in full_days if phases[d]=="HOLDOUT18")
    assert len(hold_dates)==18
    for k in (5,6,8,10,20):
        for comparator in ("HOT72_BASE","HOT12","HOT672",
                           "RANDOM16_MEAN"):
            xs=[]
            for date in hold_dates:
                cur=by_day[("HOLDOUT18",date,winner,k)]
                if comparator!="RANDOM16_MEAN":
                    other=by_day[("HOLDOUT18",date,comparator,k)]
                    diff=cur[0]/cur[1]-other[0]/other[1]
                else:
                    vals=[by_day[("HOLDOUT18",date,
                          "RANDOM_%02d"%r,k)] for r in range(N_RANDOM)]
                    oth=float(np.mean([v[0]/v[1] for v in vals]))
                    diff=cur[0]/cur[1]-oth
                xs.append(diff)
            xs=np.array(xs,dtype=float)
            rng=np.random.default_rng(SEED+k*11+len(comparator)*941)
            bootstrap=xs[rng.integers(0,len(xs),size=(5000,len(xs)))].mean(axis=1)
            diff_summary.append(dict(model=winner,phase="HOLDOUT18",
                budget=k,vs=comparator,n_days=len(xs),
                observed_difference_per_target=round(float(xs.mean()),6),
                lower95=round(float(np.quantile(bootstrap,.025)),6),
                upper95=round(float(np.quantile(bootstrap,.975)),6),
                ci_contains_zero=bool(np.quantile(bootstrap,.025)<=0<=
                                  np.quantile(bootstrap,.975))))
    locked=lambda k,phase,model:next(r for r in budget_report
        if r["phase"]==phase and r["method"]==model and r["ticket_size"]==k)
    lines=[
      "V121 56 IC ICE HALKA | 80 SAYI | AILE YOK | 29 MODEL + 16 RASTGELE",
      f"Historical replay targets={n-672} last observed #{rows[-1]['id']} {rows[-1]['day']}.",
      "Long ring56=672, ring1=12; every next drawing shifts all 56 windows.",
      f"Train36={phase_targets['TRAIN36']} target, validation18={phase_targets['VALIDATE18']},",
      f"holdout18={phase_targets['HOLDOUT18']}, extra={phase_targets['EXTRA']}.",
      "Regression trained on TRAIN36 only. Model selection fixed exclusively",
      f"using VALIDATE18 average hits at {LOCK_K} numbers; winner: {winner}.",
      "Reported HOLDOUT18 unchanged selected winner evaluated at every ticket size.",
      "Historical HOLDOUT is NOT unseen research: previous V9-V120 studied these dates.",
      "Baseline 16 deterministic independent random20 controls, budget matched;",
      "the expected hit for any fixed k/80 ticket remains k/4 when 20 draw.",
      ""]
    for k in KS:
        sel=locked(k,"HOLDOUT18",winner)
        hot=locked(k,"HOLDOUT18","HOT72_BASE")
        ran=locked(k,"HOLDOUT18","RANDOM16_MEAN")
        lines.append(
            f"HOLDOUT18 k={k} targets={sel['targets']}: "
            f"WINNER={sel['average_hits']:.4f} (exact {sel['exact_k_of_k']}, "
            f"5+ {sel['hits5plus']},6+ {sel['hits6plus']},8+ {sel['hits8plus']},"
            f"10+ {sel['hits10plus']}) "
            f"HOT72={hot['average_hits']:.4f} exact={hot['exact_k_of_k']} "
            f"RANDOM16={ran['average_hits']:.4f} exact(mean)={ran['exact_k_of_k']}")
    lines.append("")
    lines.append("Top six methods by VALIDATION mean at k10 (selection never uses holdout):")
    for r in validation_rows[:6]:
        lines.append(f" {r['validation_rank']}. {r['model']}: "
           f"val={r['validation_10_mean']:.4f}, "
           f"historical_holdout={r['holdout_10_mean']:.4f},"
           f" holdout8+={r['holdout_10_hits8plus']},10/10={r['holdout_10_hits10of10']}")
    lines.append("")
    lines.append("Selected unchanged winner on HOLDOUT daily paired 95% bootstrap:")
    for x in diff_summary:
        if x['budget']==10:
            lines.append(f" k10 WINNER vs {x['vs']}: "
                f"{x['observed_difference_per_target']:+.5f} "
                f"CI95=[{x['lower95']:+.5f},{x['upper95']:+.5f}]")
    lines.extend(["",
        "The data have been repeatedly mined, so validation/holdout is a",
        "chronological internal check, NOT prospective proof of RNG advantage.",
        "Do not optimize or cherry-pick rare perfect-hit counts after seeing results.",
        "Retain all historical models and run the LOCKED validation winner",
        "on genuinely NEW future draws before making a prediction claim.",
        "No guarantee of winnings, positive expected value or 10/10."])
    output=Path(out);output.parent.mkdir(parents=True,exist_ok=True)
    meta=dict(version="V121.1",source_total_draws=n,
      first_target_index=672,source_last_id=rows[-1]["id"],
      target_count=n-672,phases=dict(phase_targets),
      cumulative_window_lengths=LENS.tolist(),ticket_sizes=list(KS),
      candidate_models=list(MODELS),random_controls=N_RANDOM,
      selection_validation_only=True,selected_winner=winner,
      selection_size=LOCK_K,
      holdout_previously_studied_externally=True,
      chosen_before_target=True,families_used=False,
      ridgereg_train_samples=train_target,ridge_l2=l2,
      detailed_rows=len(output_records))
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as z:
        z.writestr("00_V121_TURKCE_KISA_SONUC.txt","\n".join(lines)+"\n")
        writecsv(z,"01_TUM_HEDEFLER_45_MODEL_3_4_5_6_7_8_9_10_20.csv",output_records)
        writecsv(z,"02_KILITLI_SECILI_MODEL_VE_KONTROL_BOYUT_SONUCLARI.csv",budget_report)
        writecsv(z,"03_DOGRULAMA_SIRALAMA_SON18_KONTROL.csv",validation_rows)
        writecsv(z,"04_KILITLI_KAZANAN_GUN_BAZLI_GUVEN_ARALIKLARI.csv",diff_summary)
        writecsv(z,"05_SON_HEDEF_ONCESI_80_SAYI_56_HALKA_672BIT.csv",last_profile)
        z.writestr("06_DENETIM.json",json.dumps(meta,ensure_ascii=False,indent=2))
    print("\n".join(lines),flush=True)
    print("V121 SUCCESS",output,output.stat().st_size,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v121_output/V121_56_HALKA_45_MODEL_SAYI_HEDEF_KOR_TEST.zip")
    a=p.parse_args()
    main(a.source,a.out)
