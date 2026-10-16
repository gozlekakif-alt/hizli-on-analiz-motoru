#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V96 — V95 five-pool motion, tested on the NEXT real 20-of-80 draw.

Before draw t, V95 exact 72-draw (frequency, number) ranking assigns each
of 80 numbers to a pool of 16. The previous 12/24 state, 12-step movement,
and time in current pool are knowable as of t-1. Train labels are strictly
earlier than validation; winner chosen ONLY on validation. Refit TRAIN+VAL
and evaluate fixed winner on the last 18 full days. One 10-ball ticket per
draw, never revised after looking at that draw.

This is retrospective chronology, not prospective evidence: the 72 days
have already been inspected by many previous versions. No invented RNG
compensation/forced cycle. Random baseline has expected 2.5/10 exactly.
"""
from __future__ import annotations
import argparse,csv,io,json,math,zipfile
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V96.1"
W=72
SEED=961016
ALPHA=1500.0
POOL=("SOGUK","SERIN","NOTR","ILIK","SICAK")
LEARNED=("POOL5","POOL_DIR15","POOL_DIR_AGE45","POOL_DIR_MOMENTUM45")
CONTROLS=("RANDOM10","HOT72","HOT24","COLD72")
ALL=CONTROLS+LEARNED
KSTATE=dict(POOL5=5,POOL_DIR15=15,POOL_DIR_AGE45=45,POOL_DIR_MOMENTUM45=45)

def load(src):
    daily,issues,bad=parse_txt(src)
    good={d:v for d,v in daily.items()
          if len(v)==217 and [x["pos"] for x in v]==list(range(1,218))}
    days=sorted(good)
    if len(days)!=72 or days[0]!="2026-08-01" or days[-1]!="2026-10-12":
        raise RuntimeError("Expected 72 complete days 01Aug..12Oct; received "+str(len(days)))
    rows=[x for d in days for x in good[d]]
    Y=np.zeros((len(rows),80),dtype=np.uint8)
    for i,r in enumerate(rows):
        Y[i,np.asarray(r["nums"],dtype=int)-1]=1
    if len(Y)!=15624 or np.any(Y.sum(axis=1)!=20):
        raise AssertionError("20-of-80 or full days invalid")
    return days,rows,Y,issues,bad

def feature_history(Y):
    """Each row at t uses Y[:t] only, never Y[t] or later."""
    n=len(Y)
    prefix=np.empty((n+1,80),dtype=np.int32)
    prefix[0]=0
    np.cumsum(Y,axis=0,dtype=np.int32,out=prefix[1:])
    states=np.full((n,80),255,dtype=np.uint8)
    ages=np.zeros((n,80),dtype=np.uint16)
    nums=np.arange(80)
    for t in range(W,n):
        count=prefix[t]-prefix[t-W]
        ordered=np.lexsort((nums,count))
        g=np.empty(80,dtype=np.uint8)
        g[ordered]=np.repeat(np.arange(5,dtype=np.uint8),16)
        states[t]=g
        ages[t]=np.where(g==states[t-1],np.minimum(ages[t-1]+1,65535),1)
    t=np.arange(96,n,dtype=np.int32)
    current=states[t].astype(np.int16)
    old12=states[t-12].astype(np.int16)
    old24=states[t-24].astype(np.int16)
    direction=np.sign(current-old12)+1
    momentum=np.sign(old12-old24)+1
    age=np.where(ages[t]<=3,0,np.where(ages[t]<=12,1,2))
    features=dict(
        POOL5=current.astype(np.uint8),
        POOL_DIR15=(current*3+direction).astype(np.uint8),
        POOL_DIR_AGE45=((current*3+direction)*3+age).astype(np.uint8),
        POOL_DIR_MOMENTUM45=((current*3+direction)*3+momentum).astype(np.uint8))
    for name,state in features.items():
        assert state.shape==(len(t),80)
        assert np.max(state)<KSTATE[name]
    assert np.all(np.bincount(states[96],minlength=5)==np.repeat(16,5))
    return t,features,(prefix[t]-prefix[t-72]),(prefix[t]-prefix[t-24]),states[t],ages[t]

def fit(codes,Y,indices):
    states=codes[indices].reshape(-1)
    labels=Y[indices].reshape(-1)
    states_n=int(codes.max())+1
    opportunities=np.bincount(states,minlength=states_n)
    hits=np.bincount(states,weights=labels,minlength=states_n)
    p=(hits+ALPHA*0.25)/(opportunities+ALPHA)
    return p,opportunities,hits

def select10(score,tie):
    assert score.shape==tie.shape and score.shape[1]==80
    # Same unseen-data-independent random tie-breaker for every method.
    v=score.astype(float)+1e-9*tie
    return np.argpartition(-v,9,axis=1)[:,:10]

def hit_vector(Y,picks):
    return np.take_along_axis(Y,picks,axis=1).sum(axis=1).astype(np.uint8)

def report_metrics(method,phase,hits,days,reference):
    d={}
    for day in np.unique(days):
        which=days==day
        d[int(day)]=float(np.mean(hits[which]-reference[which].astype(np.int16)))
    diffs=np.array(list(d.values()),float)
    se=float(np.std(diffs,ddof=1)/np.sqrt(len(diffs))) if len(diffs)>1 else 0.
    ci=(float(diffs.mean()-1.96*se),float(diffs.mean()+1.96*se))
    r=dict(method=method,phase=phase,n_draws=len(hits),days=len(d),
           mean_hits=round(float(np.mean(hits)),6),
           expected_fair=2.5,
           gain_vs_hot72=round(float(diffs.mean()),6),
           approx_day_ci_low=round(ci[0],6),
           approx_day_ci_high=round(ci[1],6))
    for k in range(11):r["hits_"+str(k)]=int(np.sum(hits==k))
    for k in (5,6,7,8,9,10):
        r[str(k)+"plus"]=int(np.sum(hits>=k))
    return r,d

def makecsv(z,name,records):
    if not records:return
    with z.open(name,"w") as f:
        out=io.TextIOWrapper(f,encoding="utf-8",newline="")
        writer=csv.DictWriter(out,fieldnames=list(records[0]))
        writer.writeheader();writer.writerows(records)
        out.flush();out.detach()

def run(src,dest):
    dates,rows,Y,issues,bad=load(src)
    t,codes,c72,c24,groups,ages=feature_history(Y)
    labels=Y[t]
    day=t//217
    split={"TRAIN":np.flatnonzero(day<36),
           "VALIDATE":np.flatnonzero((day>=36)&(day<54)),
           "HOLDOUT":np.flatnonzero(day>=54)}
    assert all(len(x)>0 for x in split.values())
    # Pre-generated ties are independent of every target number.
    tie=np.random.default_rng(SEED).random((len(t),80))
    control_scores=dict(RANDOM10=tie,HOT72=c72.astype(float),
                        HOT24=c24.astype(float),COLD72=-c72.astype(float))
    controls={k:select10(s,tie) for k,s in control_scores.items()}
    estimates={}
    preprobs={}
    for name in LEARNED:
        p,op,hits=fit(codes[name],labels,split["TRAIN"])
        estimates[name]=p
        preprobs[name]=(p,op,hits)
    val=split["VALIDATE"]
    val_scores={}
    for name in LEARNED:
        picks=select10(estimates[name][codes[name][val]],tie[val])
        val_scores[name]=float(hit_vector(labels[val],picks).mean())
    # Before HOLDOUT, freeze model FAMILY using validation ONLY.
    winner=max(LEARNED,key=lambda n:(val_scores[n],-LEARNED.index(n)))
    trval=np.r_[split["TRAIN"],split["VALIDATE"]]
    # Standard refit on all earlier labels; no holdout labels enter fitting.
    frozen,op2,h2=fit(codes[winner],labels,trval)
    policies=dict(controls)
    selected_val={k:controls[k][val] for k in CONTROLS}
    for name in LEARNED:
        selected_val[name]=select10(estimates[name][codes[name][val]],tie[val])
    hold=split["HOLDOUT"]
    selected_hold={k:controls[k][hold] for k in CONTROLS}
    selected_hold[winner]=select10(frozen[codes[winner][hold]],tie[hold])
    summaries=[]
    daily=[]
    tickets=[]
    for phase,ix,options in (("VALIDATE",val,selected_val),
                             ("HOLDOUT",hold,selected_hold)):
        ref=hit_vector(labels[ix],options["HOT72"]).astype(np.int16)
        for method,picks in options.items():
            hits=hit_vector(labels[ix],picks)
            r,d=report_metrics(method,phase,hits,day[ix],ref)
            summaries.append(r)
            if method==winner or method in CONTROLS:
                for dd,adv in sorted(d.items()):
                    daily.append(dict(phase=phase,method=method,day=dates[dd],
                                      gain_vs_hot72=round(adv,7)))
            if method==winner:
                for j,ii in enumerate(ix):
                    tickets.append(dict(phase=phase,day=dates[int(day[ii])],
                        draw_id=rows[int(t[ii])]["id"],
                        last_known_draw_id=rows[int(t[ii])-1]["id"],
                        source_draw_position=int(t[ii])+1,
                        ticket_10=";".join(str(x+1) for x in sorted(picks[j])),
                        hits=int(hits[j]),
                        target_20=";".join(str(x+1) for x in np.flatnonzero(labels[ii]))))
    lookup={(r["phase"],r["method"]):r for r in summaries}
    def one(phase,name):return lookup[(phase,name)]["mean_hits"]
    h=lookup[("HOLDOUT",winner)]
    exp5=sum(math.comb(20,k)*math.comb(60,10-k)/math.comb(80,10)
             for k in range(5,11))
    # Interpretation is predeclared: compare fixed winner with HOT72 and
    # independent random expectation, never infer forced next-hit odds.
    report=[
        "V96 | BES HAVUZUN HAREKETI SONRAKI 20 SAYIYI ONGOREBILIYOR MU?",
        f"72 completed days, {len(Y)} full draws, {len(t)} eligible one-step forecasts",
        "1 drawing = 20 distinct numbers / 80; ticket always 10 distinct balls",
        "V95 exact five 16-number pools by last72 frequency and number ties",
        "INPUTS ONLY PREVIOUS: pool now, movement 12 / previous12, pool age, last24/72 frequencies",
        "TRAIN first 36 complete days / VALIDATE next 18 / HOLDOUT last 18",
        "Validation selects 1 winner from 4 prior declared pool families, never controls",
        "Refit winner on TRAIN+VALIDATE only; HOLDOUT labels not consulted",
        f"Validation scores: { {n:round(v,6) for n,v in val_scores.items()} }",
        f"CHOSEN WINNER: {winner}",
        f"VALIDATE winner={one('VALIDATE',winner):.6f}, HOT72={one('VALIDATE','HOT72'):.6f}, RANDOM10={one('VALIDATE','RANDOM10'):.6f}",
        f"HOLDOUT winner={one('HOLDOUT',winner):.6f}, HOT72={one('HOLDOUT','HOT72'):.6f}, HOT24={one('HOLDOUT','HOT24'):.6f}, RANDOM10={one('HOLDOUT','RANDOM10'):.6f}",
        f"HOLDOUT day-level approx 95% CI for winner minus HOT72 [{h['approx_day_ci_low']},{h['approx_day_ci_high']}]",
        f"HOLDOUT 5+/6+/7+/8+/9+/10of10={h['5plus']}/{h['6plus']}/{h['7plus']}/{h['8plus']}/{h['9plus']}/{h['10plus']}",
        f"Fair random expectation for >=5 in {len(hold)} drawings = {len(hold)*exp5:.2f}",
        "No matter how often each number switches pools, fair independent 20/80:",
        "P(next draw contains each number | history) = 0.25.",
        "The reference data and the general idea have been repeatedly researched;",
        "thus this chronological HOLDOUT is not untouched prospective confirmation.",
        "Selection and repeated experiments can produce spurious gains;",
        "require future predictions timestamped before draws and replication.",
        "The approximate daily CI does NOT correct for historical multiple testing.",
        "Observation across missing day must not be mistaken for consecutive 5-minute draws."
    ]
    debug=[]
    for name in LEARNED:
        p,op,hits=preprobs[name]
        for code,x in enumerate(p):
            debug.append(dict(name=name,state=code,phase="TRAIN",
                         n=int(op[code]),hits=int(hits[code]),prob=float(x)))
    for code,x in enumerate(frozen):
        debug.append(dict(name=winner,state=code,phase="REFIT_TRAIN_VAL",
                         n=int(op2[code]),hits=int(h2[code]),prob=float(x)))
    out=Path(dest);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_V96_KARAR_VE_KOR_TEST.txt","\n".join(report)+"\n")
        makecsv(z,"01_TUM_MODELLER_DOGRULAMA_VE_HOLDOUT.csv",summaries)
        makecsv(z,"02_ONCEDEN_BELIRLENMIS_TEK_10LU_KUPON_VE_ISABET.csv",tickets)
        makecsv(z,"03_GUNLUK_KAZANC_HOT72_ILE_KARSILASTIRMA.csv",daily)
        makecsv(z,"04_EGITILMIS_HAVUZ_DURUM_OLASILIKLARI.csv",debug)
        z.writestr("05_DENETIM.json",json.dumps(dict(version=VERSION,
          data_days=dates,n_draws=len(Y),train_draws=len(split["TRAIN"]),
          validation_draws=len(val),holdout_draws=len(hold),
          frozen_winner=winner,validation_scores=val_scores,
          holdout_winner=h,summary=summaries,source_issues=issues[:10],
          source_bad=bad[:10],seed=SEED,alpha=ALPHA),
          ensure_ascii=False,indent=2,default=str))
    print("\n".join(report),flush=True)
    print("V96 DONE",str(out),out.stat().st_size,flush=True)

def selftest():
    rng=np.random.default_rng(2026)
    y=np.zeros((300,80),np.uint8)
    for i in range(len(y)):y[i,rng.choice(80,20,replace=False)]=1
    t,f,c72,c24,g,age=feature_history(y)
    assert len(t)==204 and all(a.shape==(204,80) for a in f.values())
    assert np.all(np.sum(c72,axis=1)==72*20)
    p,op,hit=fit(f["POOL5"],y[t],np.arange(100))
    assert len(p)==5 and np.all((p>0)&(p<1))
    assert np.all(hit<=op)
    tie=rng.random((10,80));sc=rng.random((10,80))
    assert np.all(np.sum(y[t[:10]],axis=1)==20)
    picks=select10(sc,tie)
    assert np.all(np.array([len(set(x))==10 for x in picks]))
    # Changing target Y[t] cannot affect any score inputs at that t.
    x=y.copy();x[120]=0;x[120,40:60]=1
    _,f2,c722,c242,_,_=feature_history(x)
    ix=int(np.where(t==120)[0][0])
    assert all(np.array_equal(f[k][ix],f2[k][ix]) for k in LEARNED)
    assert np.array_equal(c72[ix],c722[ix])
    print("V96 SELFTEST OK: no target leakage, 10 unique ticket numbers",flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",default="veri.txt")
    ap.add_argument("--out",default="v96_output/V96_BES_HAVUZ_GECIS_KOR_TEST.zip")
    ap.add_argument("--selftest",action="store_true")
    args=ap.parse_args()
    selftest() if args.selftest else run(args.source,args.out)
