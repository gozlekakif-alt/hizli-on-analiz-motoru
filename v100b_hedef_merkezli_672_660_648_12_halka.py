#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V100B – TARGET-ANCHORED 672,660,...,12 nested temperature circles.

Each ring is a NESTED trailing history window of length L ending just
BEFORE target t. Consecutive rings drop the OLDEST 12 draws:
[t-672:t], [t-660:t], ..., [t-12:t].
These are NOT 56 disjoint chronological 12-ball blocks from V100A.
Every ring sorts ALL 80 ball appearance frequencies (past L) ascending
(frequency, numeric ID) and partitions the 80 into 16 cold, 16 cool,
16 neutral, 16 warm, 16 hot. This tests exactly what a concentric
672-660-648-...-12 sketch can mean. One draw forward sliding target.
Historical data reused extensively; descriptive results not RNG decoding.
"""
import argparse, collections, csv, io, json, hashlib, math, random, zipfile
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V100B.1"
WIDTHS=np.arange(672,0,-12,dtype=np.int32)
assert len(WIDTHS)==56 and WIDTHS[-1]==12
POOL=("SOGUK","SERIN","NOTR","ILIK","SICAK")
SEED=100161017
METHODS=("HOT72","HOT12","HOT672","COLD672","NEST_RISE6",
         "NEST_FALL6","NEST_RISE12","NEST_FULL_SWEEP",
         "NEST_HOT_COLD","NEST_HOT_STAY","NEST_UP_MOVES",
         "NEST_REBOUND","NEST_HOT_RISING","NEST_SHORT_ACCEL",
         "NEST_LONG_SHORT_RATIO")
PHASES=("TRAIN","VALIDATE","HOLDOUT")
RANK=np.broadcast_to((np.arange(80)//16).astype(np.uint8),(56,80))
NUMIDS=np.arange(80)

def load(path):
    d,issues,bad=parse_txt(path)
    good={day:rs for day,rs in d.items() if len(rs)==217 and
        [r["pos"] for r in rs]==list(range(1,218))}
    days=sorted(good)
    if len(days)!=72 or days[0]!="2026-08-01" or days[-1]!="2026-10-12":
        raise AssertionError(f"Expected 72 complete days, got {len(days)}")
    rows=[r for date in days for r in good[date]]
    x=np.zeros((len(rows),80),dtype=np.uint8)
    for i,row in enumerate(rows):
        x[i,np.array(row["nums"],dtype=np.int16)-1]=1
    assert x.shape==(15624,80) and np.all(x.sum(axis=1)==20)
    return days,rows,x,issues,bad

def pool_film(prefix,t):
    assert t>=672 and t<=len(prefix)-1
    counts=prefix[t][None,:]-prefix[t-WIDTHS]
    # argsort stable by prior identity ascending, equivalent to ascending
    # (frequency, numeric ball) exactly as in V95.
    order=np.argsort(counts,axis=1,kind="stable")
    states=np.empty((56,80),dtype=np.uint8)
    states[np.arange(56)[:,None],order]=RANK
    assert states.min()==0 and states.max()==4
    return counts.T.astype(np.int16),states.T.astype(np.int8)

def calculate_scores(counts,S):
    last=S[:,-1]
    baseline72=counts[:,50].astype(float) # 672 - 50*12 = 72
    recent12=counts[:,-1].astype(float)
    long672=counts[:,0].astype(float)
    d=np.diff(S,axis=1)
    r=d>0;f=d<0
    last6=S[:,-1]-S[:,-7]
    last12=S[:,-1]-S[:,-13]
    visited=np.column_stack([(S==i).any(axis=1) for i in range(5)])
    allfive=visited.all(axis=1)
    hotcold=visited[:,0]&visited[:,4]
    last6net=np.sum(r[:,-6:],axis=1)-np.sum(f[:,-6:],axis=1)
    bounce=(S[:,-1]-S[:,-4])-(S[:,-4]-S[:,-7])
    long_hot=(S==4).sum(axis=1)
    full_u=np.sum(r,axis=1)
    full_d=np.sum(f,axis=1)
    eps=baseline72/1000+NUMIDS[::-1]/10000000.
    # Fixed hypotheses set before target. Not fitted on future outcomes.
    models={
       "HOT72":baseline72,
       "HOT12":recent12,
       "HOT672":long672,
       "COLD672":-long672,
       "NEST_RISE6":last6*20+eps,
       "NEST_FALL6":-last6*20+eps,
       "NEST_RISE12":last12*20+eps,
       "NEST_FULL_SWEEP":allfive.astype(float)*20+baseline72,
       "NEST_HOT_COLD":hotcold.astype(float)*20+baseline72,
       "NEST_HOT_STAY":long_hot+eps,
       "NEST_UP_MOVES":full_u+eps,
       "NEST_REBOUND":bounce*20+eps,
       "NEST_HOT_RISING":S[:,-1]*30+last6*25+eps,
       "NEST_SHORT_ACCEL":(recent12-counts[:,-2])*20+eps,
       "NEST_LONG_SHORT_RATIO":(recent12-long672/56)*20+eps}
    features=dict(allfive=allfive,hotcold=hotcold,
        rising=last6>0,falling=last6<0,late6=last6,
        outer_pool=S[:,0],inner_pool=S[:,-1],pool72=S[:,50],
        full_up=full_u,full_down=full_d,
        warm_reached=(S==4).any(axis=1),
        cold_reached=(S==0).any(axis=1),
        number_pools=visited.sum(axis=1))
    assert set(models)==set(METHODS)
    return models,features

def pick(scores):
    return np.lexsort((NUMIDS,-scores))[:20]

def random20(number):
    seed=int.from_bytes(hashlib.blake2b(f"{SEED}|{number}".encode(),digest_size=8).digest(),"big")
    return random.Random(seed).sample(range(80),20)

def build(days,rows,x):
    n=len(x)
    prefix=np.vstack((np.zeros((1,80),dtype=np.int32),
                      np.cumsum(x,axis=0,dtype=np.int32)))
    phase={date:PHASES[0 if k<36 else 1 if k<54 else 2] for k,date in enumerate(days)}
    per_target=[]
    coverage=[]
    buckets=collections.defaultdict(lambda:[0,0])
    ballpool=collections.defaultdict(lambda:[0,0])
    ring_activity=np.zeros((3,55,3),dtype=np.int64)
    ring_next=np.zeros((3,55,3),dtype=np.int64)
    latest=[]
    lastsummary=[]
    for t in range(672,n):
        row=rows[t]; date=row["day"]; ph=phase[date]
        counts,S=pool_film(prefix,t)
        scores,feat=calculate_scores(counts,S)
        y=x[t]
        predictions={name:pick(s) for name,s in scores.items()}
        hit={name:int(np.sum(y[ind])) for name,ind in predictions.items()}
        rid=random20(row["id"])
        draws=int(np.sum(y[np.asarray(rid)]))
        per_target.append(dict(phase=ph,day=date,target_draw_id=row["id"],
            target_time=row["time"],outer672_start_id=rows[t-672]["id"],
            last_observed_draw_id=rows[t-1]["id"],
            target20="-".join(map(str,row["nums"])),
            HOT72_top20="-".join(str(q+1) for q in predictions["HOT72"]),
            RAND20_hit=draws,
            **{name+"_hit":v for name,v in hit.items()}))
        coverage.append(dict(day=date,phase=ph,target_draw_id=row["id"],
            completed_all_5_pools=int(feat["allfive"].sum()),
            visited_both_hot_cold=int(feat["hotcold"].sum()),
            outer672_to_inner12_rising=int(np.sum(S[:,-1]>S[:,0])),
            outer672_to_inner12_falling=int(np.sum(S[:,-1]<S[:,0])),
            rising_in_last6_rings=int(feat["rising"].sum()),
            cooling_in_last6_rings=int(feat["falling"].sum()),
            mean_distinct_pools=float(np.mean(feat["number_pools"]))))
        current=0 if ph=="TRAIN" else (1 if ph=="VALIDATE" else 2)
        changes=np.sign(np.diff(S,axis=1))+1
        ids=(np.arange(55)[:,None]*3+changes)
        ring_activity[current]+=np.bincount(ids.ravel(),minlength=165).reshape(55,3)
        ring_next[current]+=np.bincount(ids.ravel(),weights=np.broadcast_to(
            y,(55,80)).ravel(),minlength=165).reshape(55,3).astype(np.int64)
        for i in range(80):
            code=(ph,int(feat["pool72"][i]),int(feat["inner_pool"][i]),
                    int(np.sign(feat["late6"][i])),int(feat["allfive"][i]))
            b=buckets[code];b[0]+=1;b[1]+=int(y[i])
            p=(ph,i+1,int(feat["inner_pool"][i]))
            a=ballpool[p];a[0]+=1;a[1]+=int(y[i])
        if t==n-1:
            for i in range(80):
                seen=0;completion=None
                for j,w in enumerate(WIDTHS):
                    pool=int(S[i,j])
                    seen|=1<<pool
                    if completion is None and seen==31:completion=int(j+1)
                    latest.append(dict(
                        draw_id=row["id"],ball=i+1,ring=j+1,
                        trailing_draws=int(w),first_draw_id=rows[t-w]["id"],
                        last_observed_draw_id=rows[t-1]["id"],
                        frequency=int(counts[i,j]),pool_rank=pool,
                        pool=POOL[pool],direction_from_previous_ring=(
                            0 if j==0 else pool-int(S[i,j-1]))))
                lastsummary.append(dict(ball=i+1,
                    first_5_pool_complete_ring=completion or "",
                    visited_5=int(feat["allfive"][i]),
                    visited_hot_and_cold=int(feat["hotcold"][i]),
                    latest12_pool=POOL[int(S[i,-1])],
                    outer672_pool=POOL[int(S[i,0])],
                    last72_pool=POOL[int(feat["pool72"][i])],
                    last6_pool_direction=int(feat["late6"][i]),
                    up_moves_55=int(feat["full_up"][i]),
                    down_moves_55=int(feat["full_down"][i]),
                    target_occurred=int(y[i])))
        if (t-672)%2000==0:print(f"V100B target {t}/{n}",flush=True)
    summary=[]
    for p in PHASES:
        a=[r for r in per_target if r["phase"]==p]
        if not a:continue
        base=np.array([r["HOT72_hit"] for r in a])
        rnd=np.array([r["RAND20_hit"] for r in a])
        for m in METHODS:
            own=np.array([r[m+"_hit"] for r in a])
            summary.append(dict(phase=p,model=m,n=len(a),
                 hits20=float(own.mean()),hot72_matched=float(base.mean()),
                 random20_matched=float(rnd.mean()),
                 change_from_hot72=float(np.mean(own-base)),
                 eightplus=int(np.sum(own>=8)),
                 nineplus=int(np.sum(own>=9)),
                 tenplus=int(np.sum(own>=10)),
                 max_hit=int(own.max())))
    val=[r for r in summary if r["phase"]=="VALIDATE" and r["model"]!="HOT72"]
    winner=max(val,key=lambda r:(r["change_from_hot72"],
                                 -METHODS.index(r["model"])))
    chosen=winner["model"] if winner["change_from_hot72"]>0 else "HOT72"
    last=next(r for r in summary if r["phase"]=="HOLDOUT" and r["model"]==chosen)
    test=[r for r in per_target if r["phase"]=="HOLDOUT"]
    dayscores=[]
    for day in days[54:]:
        b=[r[chosen+"_hit"]-r["HOT72_hit"] for r in test if r["day"]==day]
        dayscores.append(np.mean(b))
    scores=np.array(dayscores)
    mean=float(np.mean(scores))
    se=float(np.std(scores,ddof=1)/np.sqrt(len(scores)))
    detail=[]
    for phase_idx,p in enumerate(PHASES):
        for ring in range(55):
            for direction in (-1,0,1):
                nobs=int(ring_activity[phase_idx,ring,direction+1])
                if nobs==0:continue
                successes=int(ring_next[phase_idx,ring,direction+1])
                detail.append(dict(phase=p,outer_window=int(WIDTHS[ring]),
                    inner_window=int(WIDTHS[ring+1]),direction=direction,
                    number_histories=nobs,ball_in_target=successes,
                    observed_target_pct=100*successes/nobs))
    b_groups=[dict(phase=p,last72_pool=POOL[ps],last12_pool=POOL[pe],
                   direction_last6=direction,visited_all5=five,
                   samples=n,hits=k,hit_pct=100*k/n)
        for (p,ps,pe,direction,five),(n,k) in sorted(buckets.items())]
    bynum=[dict(phase=p,ball=ball,inner_pool=POOL[pe],
                observations=n,target_hits=h,target_pct=100*h/n)
           for (p,ball,pe),(n,h) in sorted(ballpool.items())]
    meta=dict(version=VERSION,rolling_histories=len(per_target),
        windows=list(map(int,WIDTHS)),source_draws=len(rows),
        source_dates=[days[0],days[-1]],model_selected_using_validation=chosen,
        validation_selected_gain=winner["change_from_hot72"],
        holdout_gain_vs_hot72=last["change_from_hot72"],
        holdout_day95=(mean-1.96*se,mean+1.96*se),
        holdout_days=len(days[54:]),
        no_target_leakage=True,
        validation_not_genuinely_untouched="V9-V100 repeatedly explored dates",
        interpretation="Nested target-anchored windows, NOT chronological disjoint 12-draw segments")
    return meta,summary,per_target,coverage,detail,b_groups,bynum,latest,lastsummary

def addcsv(z,name,a):
    if not a:return
    with z.open(name,"w",force_zip64=True) as f:
        h=io.TextIOWrapper(f,encoding="utf-8",newline="")
        w=csv.DictWriter(h,fieldnames=list(a[0].keys()))
        w.writeheader();w.writerows(a);h.flush();h.detach()

def write_report(meta,summary,coverage,ring_detail,lastballs):
    ph="HOLDOUT";model=meta["model_selected_using_validation"]
    v=[r for r in summary if r["phase"]=="VALIDATE"]
    hold=[r for r in summary if r["phase"]=="HOLDOUT"]
    hot=next(r for r in hold if r["model"]=="HOT72")
    win=next(r for r in hold if r["model"]==model)
    z=[
     "V100B – IÇ IÇE 56 HALKA: 672-660-648-...-12-HEDEF",
     "IMPORTANT: All 56 histories END just before target draw, and shrink by12.",
     f"Full days=72, 20-of-80 draws=15624, scored targets={meta['rolling_histories']}.",
     "Every ring ranks 80 numbers into five 16-ball relative temperature pools.",
     "None of the previous target's outputs or future draws enter next selection.",
     "",
     f"LATEST TARGET full5 visited={coverage[-1]['completed_all_5_pools']}/80; cold+hot={coverage[-1]['visited_both_hot_cold']}/80.",
     f"LATEST target outer672-to-inner12 rising/falling={coverage[-1]['outer672_to_inner12_rising']}/{coverage[-1]['outer672_to_inner12_falling']}.",
     f"LATEST target last6 nested rings rising/falling={coverage[-1]['rising_in_last6_rings']}/{coverage[-1]['cooling_in_last6_rings']}.",
     "LATEST TARGET lacking complete full5: "+",".join(str(x["ball"]) for x in lastballs if not x["visited_5"]),
     "",
     "VALIDATE: candidate mean hit among top20, same targets as HOT72"]
    for x in sorted(v,key=lambda d:-d["change_from_hot72"]):
        z.append(f" {x['model']:23s} mean={x['hits20']:.5f} HOT72={x['hot72_matched']:.5f} delta={x['change_from_hot72']:+.5f}")
    z+=["",f"Selected by validation: {model}",
         f"HOLDOUT HOT72={hot['hits20']:.6f}; RANDOM20={hot['random20_matched']:.6f}; selected={win['hits20']:.6f}",
         f"HOLDOUT selected-vs-HOT72={win['change_from_hot72']:+.6f}",
         f"95% day-block approx CI: {meta['holdout_day95'][0]:+.6f} .. {meta['holdout_day95'][1]:+.6f}",
         "Fair benchmark for 20 chosen balls = 5/20 per 20-ball target.",
         "Any apparent difference needs prospective confirmation; no automatic tickets.",
         "This data was repeatedly investigated historically; chronological holdout is not pristine.",
         "Even large individual historical ring motions do not automatically predict target identities."]
    return "\n".join(z)+"\n"

def run(source,out):
    days,rows,x,issues,bad=load(source)
    meta,summaries,targets,cov,ring,groups,ballpool,latest,ball=build(days,rows,x)
    meta.update(source_issues=issues[:20],bad_lines=bad[:20])
    report=write_report(meta,summaries,cov,ring,ball)
    dst=Path(out);dst.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dst,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        z.writestr("00_NESTED_672_660_12_RAPOR.txt",report)
        addcsv(z,"01_15_MODEL_36_18_18_KOR_TEST.csv",summaries)
        addcsv(z,"02_14952_HEDEF_KAYDIRMA_KUPON_KONTROL.csv",targets)
        addcsv(z,"03_HER_HEDEF_56_HALKA_DOLULUK.csv",cov)
        addcsv(z,"04_55_ASAMA_YON_HEDEF_GELME_OLASILIGI.csv",ring)
        addcsv(z,"05_SON72_SON12_YON_TUM_DAVRANISLAR.csv",groups)
        addcsv(z,"06_80_SAYI_HANGI_IC_HALKA_HAVUZDAN_GELDI.csv",ballpool)
        addcsv(z,"07_SON_HEDEF_80_SAYI_672_660_12_FILMI.csv",latest)
        addcsv(z,"08_80_SAYI_INCE_HALKA_TAM_TUR.csv",ball)
        z.writestr("09_METOT_KOR_DENETIM.json",json.dumps(meta,indent=2,ensure_ascii=False,default=str))
    print(report,flush=True)
    print("V100B COMPLETE",dst,dst.stat().st_size,flush=True)

def selftest():
    x=np.zeros((700,80),dtype=np.uint8)
    for t in range(700):x[t,np.arange(t,t+20)%80]=1
    cum=np.vstack((np.zeros((1,80),dtype=np.int32),np.cumsum(x,axis=0,dtype=np.int32)))
    counts,S=pool_film(cum,672)
    assert counts.shape==(80,56) and S.shape==(80,56)
    assert np.array_equal(counts[:,0],x[:672].sum(axis=0))
    assert np.array_equal(counts[:,-1],x[660:672].sum(axis=0))
    for j in range(56):assert sorted(np.bincount(S[:,j],minlength=5))==[16]*5
    scores,feat=calculate_scores(counts,S)
    assert set(scores)==set(METHODS)
    assert all(len(set(pick(q)))==20 for q in scores.values())
    print("V100B SELFTEST OK",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",default="veri.txt")
    parser.add_argument("--out",default="v100b_output/V100B_672_660_648_12_ICICE_HALKA_KOR_TEST.zip")
    parser.add_argument("--selftest",action="store_true")
    a=parser.parse_args()
    if a.selftest:selftest()
    else:run(a.source,a.out)
