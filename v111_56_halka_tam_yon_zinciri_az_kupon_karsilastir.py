#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V111 | 672-draw FIFO, 56-ring full-trajectory 10-number ticket comparison.

1 ticket / H7..H12 draw, NO future observed outcome in features.
Existing V100C, V104 and V110 are not changed. After H1-H6,
each subsequent observed draw advances the FIFO one step.
Fixed first36-day training; compare validation18, holdout18, and Oct13
new-data hours against RANDOM10, HOT72, FIRST6 and SHORT6. The FULL56
ridge model sees chronological ALL 55-56 sealed pool states and 54-55
direction steps in addition to past-only short-window features.
This is historical replay, NOT independent unseen validation, guaranteed
predictions, a deployed live engine, or a reason to stake money.
"""
from __future__ import annotations
import argparse,collections,csv,io,json,math,zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load,temperature
from v104_72gun_basindan_672_56_halka_fifo_yon import stable_paths
from v102_80sayi_56_halka_yon_zinciri_hedef_saat import expected_hours

VERSION="V111.1"
RANDOM_SEED=20261016
ALPHA=1500.
KLIST=(5,6,8,10)
MODELS=("RANDOM10","HOT72","HOUR_FIRST6","SHORT6","FULL56")
PHASES=("VALIDATE18","HOLDOUT18","NEW_DATA")
def phase(day,days):
    if day>"2026-10-12":return "NEW_DATA"
    ix=days.index(day)
    return "TRAIN36" if ix<36 else "VALIDATE18" if ix<54 else "HOLDOUT18"

def feat(t,hs,X,prefix,seal):
    """80×(intercept+recent+full pool path+full exact sign path).
    All data indices must be STRICTLY LESS than target t.
    """
    assert t>=732 and hs<=t-6
    vals=[]
    for period in (6,12,24,48,72,168,672):
        a=prefix[t]-prefix[t-period]
        vals.append((a/period).astype(np.float32))
    first6=X[hs:hs+6].sum(axis=0).astype(np.float32)
    within=X[hs:t].sum(axis=0).astype(np.float32)
    vals.extend((first6/6,within/max(1,t-hs)))
    seen=(np.zeros(80,dtype=np.float32))
    for k in (1,2,3):
        vals.append(X[t-k].astype(np.float32))
    # True age since LAST observed draw, trailing maximum 48.
    hist=X[t-48:t][::-1]
    present=hist.astype(bool)
    anyseen=present.any(axis=0)
    age=np.where(anyseen,present.argmax(axis=0),48).astype(np.float32)
    vals.append(age/48)
    ids,S,D=stable_paths(t,seal)
    assert S.shape[1] in (55,56)
    new=S[:,-1].astype(np.float32)
    old=S[:,-7].astype(np.float32)
    vals.extend((new/4,(new-old)/4,
                 (D[:,-6:]>0).sum(axis=1).astype(np.float32)/6,
                 (D[:,-6:]<0).sum(axis=1).astype(np.float32)/6,
                 S.mean(axis=1).astype(np.float32)/4,
                 (D!=0).mean(axis=1).astype(np.float32),
                 (S[:,:-7]==0).mean(axis=1).astype(np.float32),
                 (S[:,:-7]==4).mean(axis=1).astype(np.float32),
                 np.full(80,(t-hs-6)/5,dtype=np.float32)))
    base=np.stack(vals,axis=1)
    # Chronological 56 past ring states and exactly 55 past direction
    # steps. At partial group boundaries the missing oldest SEALED state
    # has its own 0 mask; never read an incomplete or future group seal.
    S56=np.zeros((80,56),dtype=np.float32)
    D55=np.zeros((80,55),dtype=np.float32)
    S56[:,-S.shape[1]:]=S/4
    D55[:,-D.shape[1]:]=D
    missing=np.full((80,1),float(S.shape[1]==55),dtype=np.float32)
    full=np.concatenate((np.ones((80,1),np.float32),base,missing,S56,D55),axis=1)
    short_n=1+base.shape[1]
    assert full.shape[1]==short_n+1+56+55
    return full,short_n, (prefix[t]-prefix[t-72]),first6

def fitted(X,Y,cols):
    """No tuning on holdout, one fixed ridge regularization per model."""
    a=X[:,:cols].astype(np.float64)
    y=Y.astype(np.float64)
    gram=a.T@a
    penalty=np.eye(cols,dtype=np.float64)*ALPHA
    penalty[0,0]=0
    w=np.linalg.solve(gram+penalty,a.T@y)
    return w

def choose(arr,k,rng):
    jitter=rng.random(len(arr))*1e-9
    return np.argsort(-(arr+jitter),kind="stable")[:k]

def csvw(z,name,values):
    if not values:return
    with z.open(name,"w",force_zip64=True) as fp:
        f=io.TextIOWrapper(fp,encoding="utf-8",newline="")
        w=csv.DictWriter(f,fieldnames=list(values[0]))
        w.writeheader();w.writerows(values);f.flush();f.detach()

def hist_theory(k):
    """Per-draw Hypergeometric without replacement, N80, 20 winning."""
    return [math.comb(20,h)*math.comb(60,k-h)/math.comb(80,k)
             if 0<=h<=min(20,k) else 0. for h in range(k+1)]

def score_group(ledger,ph,method,k):
    subset=[r for r in ledger if r["period"]==ph and r["method"]==method and r["ticket_size"]==k]
    if not subset:return None
    c=collections.Counter(int(r["hits"]) for r in subset)
    n=len(subset)
    return dict(phase=ph,method=method,ticket_size=k,tickets=n,
        mean_hits=round(sum(h*num for h,num in c.items())/n,8),
        theoretical_mean=round(k*.25,8),
        hit_histogram=" ".join(f"{i}:{c[i]}" for i in range(k+1)),
        at_least3=sum(count for h,count in c.items() if h>=3),
        at_least4=sum(count for h,count in c.items() if h>=4),
        at_least5=sum(count for h,count in c.items() if h>=5),
        at_least6=sum(count for h,count in c.items() if h>=6),
        at_least7=sum(count for h,count in c.items() if h>=7),
        at_least8=sum(count for h,count in c.items() if h>=8),
        at_least9=sum(count for h,count in c.items() if h>=9),
        all_correct=c[k],
        theoretical_per_ticket_all_correct=hist_theory(k)[-1])

def run(src,out):
    days,rows,X,issues,bad=load(src)
    n=len(X)
    prefix=np.vstack((np.zeros((1,80),np.int32),
                      np.cumsum(X,axis=0,dtype=np.int32)))
    seal=np.empty((n//12,80),dtype=np.int8)
    for rid in range(n//12):
        e=(rid+1)*12
        seal[rid]=temperature(prefix[e]-prefix[max(0,e-72)])
    hrs,skipped=expected_hours(rows)
    hours=[(t,day,hh,ids) for t,day,hh,ids in hrs if t+12<=n]
    # Fit using first36 ONLY: predictions for H7..H12 after first6 observed.
    trainX=[];trainY=[];cnt=collections.Counter();inputdim=None;shortlen=None
    for t,day,h,ids in hours:
        if phase(day,days)!="TRAIN36":continue
        for step in range(6,12):
            current=t+step
            feat80,short,hot,first6=feat(current,t,X,prefix,seal)
            if inputdim is None:
                inputdim=feat80.shape[1];shortlen=short
            assert feat80.shape[1]==inputdim and short==shortlen
            trainX.append(feat80)
            trainY.append(X[current].astype(np.float32))
            cnt["TRAIN"]+=1
    A=np.vstack(trainX);Y=np.concatenate(trainY)
    assert A.shape==(len(Y),inputdim)
    # Fit pair of comparably regularized, linear probability models:
    # short-window vs full 56 pool + 55 direction past trajectory.
    wshort=fitted(A,Y,shortlen)
    wfull=fitted(A,Y,inputdim)
    del A,trainX,trainY,Y
    ledger=[];perdraw=[];probsc=[]
    for t,day,h,ids in hours:
        ph=phase(day,days)
        if ph=="TRAIN36":continue
        for step in range(6,12):
            current=t+step
            f,short,hot,first6=feat(current,t,X,prefix,seal)
            assert short==shortlen
            y=X[current]
            actual_ids=np.flatnonzero(y>0)+1
            # A seed dependent solely on known target draw position,
            # not on result. For each method independent identical jitter.
            salt=RANDOM_SEED+current*29
            rng=np.random.default_rng(salt)
            rnd=rng.permutation(80)[:10]
            source_scores={
                "RANDOM10":None,
                "HOT72":hot.astype(np.float64),
                "HOUR_FIRST6":first6.astype(np.float64),
                "SHORT6":f[:,:shortlen].astype(np.float64)@wshort,
                "FULL56":f.astype(np.float64)@wfull}
            selected={}
            for method in MODELS:
                selected[method]=(rnd if method=="RANDOM10" else
                    choose(source_scores[method],10,np.random.default_rng(salt)))
                v=selected[method]
                nh=int(y[v].sum())
                ledger.append(dict(
                    period=ph,date=day,hour=f"{h:02d}:02-{h:02d}:57",
                    draw_id=int(rows[current]["id"]),target_hand=step+1,
                    predicted_before_draw_id=int(rows[current-1]["id"]),
                    method=method,ticket_size=10,
                    selected_numbers="-".join(map(str,np.sort(v+1))),
                    hits=nh,
                    hit_numbers="-".join(map(str,np.sort(v[y[v]>0]+1)))))
            # Propose smaller tickets from FULL56 scores; none are
            # optimized on target actual. Also include ten FULL56 once.
            for k in KLIST:
                v=choose(source_scores["FULL56"],k,np.random.default_rng(salt))
                if k<10:
                    ledger.append(dict(
                        period=ph,date=day,hour=f"{h:02d}:02-{h:02d}:57",
                        draw_id=int(rows[current]["id"]),target_hand=step+1,
                        predicted_before_draw_id=int(rows[current-1]["id"]),
                        method="FULL56",ticket_size=k,
                        selected_numbers="-".join(map(str,np.sort(v+1))),
                        hits=int(y[v].sum()),
                        hit_numbers="-".join(map(str,np.sort(v[y[v]>0]+1)))))
            if ph=="NEW_DATA":
                for ball in range(80):
                    probsc.append(dict(period=ph,date=day,
                        draw_id=int(rows[current]["id"]),
                        target_hand=step+1,number=ball+1,
                        short_probability=float(np.clip(source_scores["SHORT6"][ball],.01,.99)),
                        full56_probability=float(np.clip(source_scores["FULL56"][ball],.01,.99)),
                        actual=int(y[ball])))
            if len(ledger)%11000==0:print("V111 predicted draws",len(ledger),flush=True)
    group=[]
    for ph in PHASES:
        for m in MODELS:
            s=score_group(ledger,ph,m,10)
            if s:group.append(s)
        for k in (5,6,8):
            s=score_group(ledger,ph,"FULL56",k)
            if s:group.append(s)
    # Draw-level matched FULL56 - RANDOM and FULL56 - SHORT6 on
    # date clusters (rather than falsely independent draws).
    by=collections.defaultdict(dict)
    for r in ledger:
        if r["ticket_size"]!=10:continue
        key=(r["period"],r["date"],r["draw_id"])
        by[key][r["method"]]=int(r["hits"])
    days_diff=collections.defaultdict(list)
    for (ph,day,drawid),d in by.items():
        if all(m in d for m in ("FULL56","RANDOM10","SHORT6","HOT72","HOUR_FIRST6")):
            days_diff[(ph,day)].append(
                (d["FULL56"]-d["RANDOM10"],d["FULL56"]-d["SHORT6"],
                 d["FULL56"]-d["HOT72"],d["FULL56"]-d["HOUR_FIRST6"]))
    daily=[]
    for (ph,day),vals in sorted(days_diff.items()):
        a=np.array(vals,dtype=float)
        daily.append(dict(phase=ph,date=day,n_draws=len(vals),
           full_minus_random=float(a[:,0].mean()),
           full_minus_short=float(a[:,1].mean()),
           full_minus_hot=float(a[:,2].mean()),
           full_minus_first6=float(a[:,3].mean())))
    ci=[]
    for ph in PHASES:
        sub=[r for r in daily if r["phase"]==ph]
        if not sub:continue
        for v in ("full_minus_random","full_minus_short",
                  "full_minus_hot","full_minus_first6"):
            x=np.array([r[v] for r in sub],float)
            mean=float(x.mean())
            se=float(x.std(ddof=1)/math.sqrt(len(x))) if len(x)>1 else 0.
            ci.append(dict(phase=ph,comparison=v,days=len(x),
                paired_diff_mean=mean,rough_day_normal_95_low=mean-1.96*se,
                rough_day_normal_95_high=mean+1.96*se))
    last_day=next((ph for ph in ("NEW_DATA","HOLDOUT18","VALIDATE18")
                   if any(r["period"]==ph and r["ticket_size"]==10 for r in ledger)),None)
    lastdraw=[r for r in ledger if r["period"]==last_day and
              r["draw_id"]==max(z["draw_id"] for z in ledger if z["period"]==last_day)]
    summary=["V111 | FIRST36 TRAIN -> VALIDATE18 / HOLDOUT18 / NEW_DATA",
       "672 true observed FIFO draws, stable absolute 12-draw rings.",
       "One new draw enters and one old draw exits each 5min step.",
       "At each complete hour H1..H6 are actually observed, ONLY THEN",
       "at H7..H12 one 10-number ticket for each model is PRE-FROZEN.",
       "FULL56 sees complete past 56 POOL STATES and 55 DIRECTION STEPS,",
       "not only total up/down. SHORT6 sees only recent features.",
       "A second sample includes 5-,6-,8-ticket sizes from FULL56.",
       f"Input draws={n}, full 12-draw target hours={len(hours)},",
       f"train samples={cnt['TRAIN']*80}, features short={shortlen}, full={inputdim}.",
       f"Ridge alpha={ALPHA}, no hyperparameter choices from validation data.",
       "",
       "10-NUMBER TICKETS: mean hits and count threshold per phase"]
    for x in group:
        if x["ticket_size"]==10:
            summary.append(f" {x['phase']:11s} {x['method']:12s} "
             f"n={x['tickets']:5d}, mean={x['mean_hits']:.5f},"
             f" >=4={x['at_least4']}, >=5={x['at_least5']},"
             f" >=6={x['at_least6']}, >=7={x['at_least7']},"
             f" >=8={x['at_least8']}, 10of10={x['all_correct']}.")
    summary+=["","RANDOM CONTROL: 10 of 80 when 20 winning,",
              f"mean expected=2.5, chance exact10={hist_theory(10)[-1]*100:.10f}%.",
              "RANDOM10 once per eligible draw, not a chance distribution",
              "simulation; theoretical expectation also listed for context.",
              "",
              "SHORT vs FULL56 daily paired mean hit differences with",
              "rough day-cluster 95% intervals (include zero => unclear):"]
    for row in ci:
        if row["comparison"] in ("full_minus_short","full_minus_random"):
            summary.append(f" {row['phase']} {row['comparison']}: "
                f"{row['paired_diff_mean']:+.6f}, "
                f"[{row['rough_day_normal_95_low']:+.6f},"
                f"{row['rough_day_normal_95_high']:+.6f}]")
    summary+=["","LAST KNOWN COMPLETE TARGET HOUR EXAMPLE (historical only):"]
    for r in lastdraw:
        if r["ticket_size"]==10:
            summary.append(f" H{r['target_hand']} #{r['draw_id']}: "
                f"{r['method']} numbers={r['selected_numbers']}"
                f" matching={r['hits']}.")
    summary+=["","This is HISTORICAL replay. Those old 72 days were",
      "already repeatedly researched; no independent unseen proof.",
      "If full56 fails to beat SHORT6 and RANDOM baseline consistently,",
      "do not claim 56 rings give a profitable edge.",
      "No real-time future data after last verified repository record;",
      "never turn these historical examples into current tips."]
    meta=dict(version=VERSION,n_draws=n,latest_known_id=rows[-1]["id"],
      total_hours=len(hours),excluded_hours=skipped,
      trains_only_first36=True,no_peek_future=True,
      full56_all_past_states=True,ring_boundary_ids_fixed=True,
      model="regularized closed form probability linear ridge",
      ticket_ranking="10 highest fitted probabilities; deterministic independent tie-breaking",
      future_status="Not active live; requires new 12-draw hour first6 in data")
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_V111_TAM56_KUPON_KOR_KARSILASTIRMA_SONUC.txt","\n".join(summary)+"\n")
        csvw(z,"01_10LU_MOTORLAR_DONEMLER_0_10_ISABET.csv",
             [r for r in group if r["ticket_size"]==10])
        csvw(z,"02_5_6_8_10LU_TAM56_ISABET_DAGILIMI.csv",
             [r for r in group if r["method"]=="FULL56"])
        csvw(z,"03_TUM_CEKILISLER_SURELI_1_KUPON_ONCE_SONRA.csv",ledger)
        csvw(z,"04_GUNLUK_10LU_ESLESMELI_FARK.csv",daily)
        csvw(z,"05_10LU_KARSILASTIRMA_GUN_BAZLI_BELIRSIZLIK.csv",ci)
        csvw(z,"06_EK_13EKIM_80_SAYI_GERCEKLERI_OLASILIK.csv",probsc)
        z.writestr("07_METOT_GECMIS_SIZMA_DENETIM.json",
                   json.dumps(meta,ensure_ascii=False,indent=2,default=str))
    print("\n".join(summary),flush=True)
    print("V111 DONE",out,out.stat().st_size,flush=True)

def selftest():
    for k in KLIST:
        theory=hist_theory(k)
        assert abs(sum(theory)-1)<1e-12
        assert abs(sum(i*p for i,p in enumerate(theory))-k/4)<1e-12
    assert 0<hist_theory(10)[10]<1e-5
    rng=np.random.default_rng(555)
    assert len(set(choose(np.arange(80,dtype=float),10,rng)))==10
    print("V111 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v111_output/V111_56_HALKA_AZ_KUPON_10DA10_KARSILASTIR.zip")
    p.add_argument("--selftest",action="store_true")
    x=p.parse_args()
    if x.selftest:selftest()
    else:run(x.source,x.out)
