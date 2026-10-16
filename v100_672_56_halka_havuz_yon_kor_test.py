#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V100: 672 observed-draw / 56*12 moving pool rings, walk-forward backtest.

For each unseen target t, 672 prior *observed* draws, partitioned from
oldest to newest into exactly 56 disjoint 12-draw rings. The same 672
window then slides one draw forward for target t+1. Ring-end pool labels
are computed with *past-only* trailing-72 and ring-local 12 frequencies.
At the oldest ring end, a trailing72 frequency requires 60 older setup
draws. Hence earliest evaluable target t=732 (0-based); the tracked history
is still EXACTLY 672 draws. No target inclusion, no families, no training
from holdout, and no gambling recommendation.

80 balls sorted ascending (frequency, ball_id) and divided into five
equal 16-ball states cold/cool/neutral/warm/hot, as in V95. This is a
RELATIVE rank, not an absolute thermometer. Full per-target ring paths
and arrival/departure directions are measured, with static variants
evaluated against matched HOT72 and deterministic RANDOM20 controls.
Results are historical, not truly pristine: prior V9-V99 analyses used
the same dates.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,io,json,math,random,zipfile
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V100.1"
K=672
BLOCK=12
RINGS=56
WARMUP=60
MIN_INDEX=K+WARMUP
SEED=100161016
POOLS=("SOGUK","SERIN","NOTR","ILIK","SICAK")
CANDIDATES=(
    "HOT12","COLD72","WARMING3_72","WARMING6_72",
    "COOLING6_72","LONG56_WARM_72","DIRECTION_STREAK_72",
    "HOT_RISING_72","COLD_RECOVER_72","REBOUND_72",
    "FIVE_POOL_TOUR_72","CROSS_COLD_HOT_72","ACCEL_12",
    "RING12_WARMING6")
ALL_METHODS=("HOT72",)+CANDIDATES
PHASE=("TRAIN","VALIDATE","HOLDOUT")

def load(path):
    d,issues,bad=parse_txt(path)
    good={date:rows for date,rows in d.items() if len(rows)==217 and
          [r["pos"] for r in rows]==list(range(1,218))}
    days=sorted(good)
    if len(days)!=72 or days[0]!="2026-08-01" or days[-1]!="2026-10-12":
        raise RuntimeError(f"Expected 72 complete days Aug 1-Oct 12: {len(days)}")
    rows=[r for day in days for r in good[day]]
    x=np.zeros((len(rows),80),dtype=np.uint8)
    for i,r in enumerate(rows):
        x[i,np.asarray(r["nums"],dtype=int)-1]=1
    if x.shape!=(15624,80) or np.any(x.sum(axis=1)!=20):
        raise RuntimeError("Invalid draw dimensions or not 20/80")
    return days,rows,x,issues,bad

def all_pool_states(prefix,w):
    """state[e,ball] is based ONLY on draws before e, last w."""
    n=prefix.shape[0]-1
    states=np.full((n+1,80),255,dtype=np.uint8)
    freq=np.zeros((n+1,80),dtype=np.int16)
    ids=np.arange(80)
    for e in range(w,n+1):
        count=prefix[e]-prefix[e-w]
        freq[e]=count
        order=np.lexsort((ids,count))
        states[e,order]=(np.arange(80)//16).astype(np.uint8)
    assert np.all(states[w:].reshape(-1,80).min(axis=1)==0)
    assert np.all(states[w:].reshape(-1,80).max(axis=1)==4)
    return states,freq

def paths(states12,states72,t):
    ends=np.arange(t-660,t+1,12,dtype=int)
    assert len(ends)==56 and ends[0]-72>=0 and ends[-1]==t
    A=states72[ends].T.astype(np.int8)
    B=states12[ends].T.astype(np.int8)
    assert A.shape==(80,56) and B.shape==(80,56)
    return ends,A,B

def traces(A,B,f12,f72,prev12):
    change=np.diff(A,axis=1)
    rise=change>0
    fall=change<0
    hot=(A==4)
    cold=(A==0)
    visited=np.column_stack([(A==j).any(axis=1) for j in range(5)])
    five=visited.all(axis=1)
    both=visited[:,0]&visited[:,4]
    late3=A[:,-1]-A[:,-4]
    late6=A[:,-1]-A[:,-7]
    late12=A[:,-1]-A[:,-13]
    rb=(A[:,-1]-A[:,-4])-(A[:,-4]-A[:,-7])
    B6=B[:,-1]-B[:,-7]
    warm_hours=(A>=3).sum(axis=1)
    moves=(change!=0).sum(axis=1)
    arrivals=rise.sum(axis=1)
    departures=fall.sum(axis=1)
    # A recent 3-ring upward/downward accumulation.
    last6up=rise[:,-6:].sum(axis=1)
    last6down=fall[:,-6:].sum(axis=1)
    last6net=last6up-last6down
    high_after_cold=(A[:,-1]>=3)&cold[:,:-1].any(axis=1)
    cooled_after_hot=(A[:,-1]<=1)&hot[:,:-1].any(axis=1)
    accel12=f12-prev12
    # All scores declared before looking at target t. Frequency tie-breakers
    # deterministic, numerically small compared with primary descriptor.
    hot72=f72.astype(np.float64)
    eps=hot72/1000+np.arange(80)[::-1]/10000000.
    scored=dict(
       HOT72=hot72,
       HOT12=f12.astype(float),
       COLD72=-hot72,
       WARMING3_72=late3*20+eps,
       WARMING6_72=late6*20+eps,
       COOLING6_72=-late6*20+eps,
       LONG56_WARM_72=warm_hours+eps,
       DIRECTION_STREAK_72=last6net*20+eps,
       HOT_RISING_72=(A[:,-1]*4+late6*3+last6net)*20+eps,
       COLD_RECOVER_72=((4-A[:,-1])*3+late3*5)*20+eps,
       REBOUND_72=rb*20+eps,
       FIVE_POOL_TOUR_72=five.astype(int)*20+hot72,
       CROSS_COLD_HOT_72=high_after_cold.astype(int)*30+
                            both.astype(int)*10+hot72,
       ACCEL_12=accel12.astype(float)*20+eps,
       RING12_WARMING6=B6.astype(float)*20+eps)
    features=dict(last_pool=A[:,-1],first_pool=A[:,0],
        five=five,both=both,late3=late3,late6=late6,late12=late12,
        arrivals=arrivals,departures=departures,moves=moves,
        hot_ring_count=hot.sum(axis=1),cold_ring_count=cold.sum(axis=1),
        warm_ring_count=warm_hours,
        last6_rises=last6up,last6_falls=last6down,
        cold_to_warm=high_after_cold,warm_to_cold=cooled_after_hot,
        accel12=accel12,
        pools_visited=visited.sum(axis=1))
    assert set(scored)==set(ALL_METHODS)
    return scored,features

def top20(scores):
    # Stable ties by ball number: no target-dependent tie-breaking.
    return np.lexsort((np.arange(80),-scores))[:20]

def random20(draw_id):
    b=hashlib.blake2b(f"{SEED}|{draw_id}".encode(),digest_size=8).digest()
    return tuple(random.Random(int.from_bytes(b,"big")).sample(range(80),20))

def analyze(days,rows,x,mode):
    prefix=np.vstack((np.zeros((1,80),dtype=np.int32),
                      np.cumsum(x,axis=0,dtype=np.int32)))
    state12,freq12=all_pool_states(prefix,12)
    state72,freq72=all_pool_states(prefix,72)
    day_phase={d:(0 if i<36 else 1 if i<54 else 2) for i,d in enumerate(days)}
    target_rows=[]
    coverage_rows=[]
    bucket=collections.defaultdict(lambda:[0,0])
    number=collections.defaultdict(lambda:[0,0])
    lastdetail=[]
    firstfinish=[]
    # Predict each target using only past [t-672,t).
    for t in range(MIN_INDEX,len(rows)):
        row=rows[t]
        day=row["day"];phase=PHASE[day_phase[day]]
        ends,A,B=paths(state12,state72,t)
        scores,feat=traces(A,B,freq12[t],freq72[t],freq12[t-12])
        y=x[t]
        selections={m:top20(s) for m,s in scores.items()}
        rand=random20(row["id"])
        hit={m:int(np.sum(y[picks])) for m,picks in selections.items()}
        rhit=int(np.sum(y[np.asarray(rand)]))
        record=dict(phase=phase,day=day,draw_id=int(row["id"]),
                    target_time=row["time"],history_start_id=int(rows[t-K]["id"]),
                    history_last_id=int(rows[t-1]["id"]),
                    rolling_draws=K,rings=RINGS,
                    target20="-".join(map(str,row["nums"])),
                    HOT72_top20="-".join(str(n+1) for n in selections["HOT72"]),
                    RANDOM20_hits=rhit)
        for name in ALL_METHODS:record[name+"_hits"]=hit[name]
        target_rows.append(record)
        coverage_rows.append(dict(phase=phase,day=day,draw_id=row["id"],
            numbers_all_five=int(feat["five"].sum()),
            numbers_both_hot_and_cold=int(feat["both"].sum()),
            numbers_rising_last6=int(np.sum(feat["late6"]>0)),
            numbers_cooling_last6=int(np.sum(feat["late6"]<0)),
            mean_ring_moves=float(np.mean(feat["moves"])),
            mean_hot_rings=float(np.mean(feat["hot_ring_count"]))))
        for j in range(80):
            # Group comparisons are descriptive: selecting on outcomes
            # here would produce an invalid predictive backtest.
            b=(phase,int(feat["last_pool"][j]),
               int(np.sign(feat["late6"][j])),
               int(feat["five"][j]),int(feat["both"][j]))
            bucket[b][0]+=1;bucket[b][1]+=int(y[j])
            n=(phase,j+1,int(feat["last_pool"][j]))
            number[n][0]+=1;number[n][1]+=int(y[j])
        if t==len(rows)-1:
            # For the most recent target, retain all 56x80 historical
            # ring coordinates and explain every directional transition.
            for j in range(80):
                seenmask=0
                first=0
                for idx,e in enumerate(ends):
                    a=int(A[j,idx]); b=int(B[j,idx])
                    seenmask|=1<<a
                    if not first and seenmask==31:first=idx+1
                    lastdetail.append(dict(
                        target_draw_id=row["id"],target_day=day,
                        ball=j+1,ring=idx+1,
                        ring_begin_id=rows[e-12]["id"],
                        ring_end_id=rows[e-1]["id"],
                        temp12=POOLS[b],temp72=POOLS[a],
                        rank12=b,rank72=a,
                        direction72=(0 if idx==0 else a-int(A[j,idx-1])),
                        direction12=(0 if idx==0 else b-int(B[j,idx-1])),
                        count12=int(freq12[e,j]),
                        count72=int(freq72[e,j])))
                firstfinish.append(dict(ball=j+1,
                    first_completed_all5_ring=first if first else "",
                    rings_ever_hot=int(feat["hot_ring_count"][j]),
                    rings_ever_cold=int(feat["cold_ring_count"][j]),
                    pool_switches=int(feat["moves"][j]),
                    total_up_moves=int(feat["arrivals"][j]),
                    total_down_moves=int(feat["departures"][j]),
                    last_72_pool=POOLS[int(feat["last_pool"][j])],
                    last_6_ring_direction=int(feat["late6"][j]),
                    first_72_pool=POOLS[int(feat["first_pool"][j])],
                    ever_visited_all5=int(feat["five"][j]),
                    ever_hot_and_cold=int(feat["both"][j]),
                    target_draw_occurred=int(y[j])))
        if mode=="progress" and (t-MIN_INDEX)%2170==0:
            print("processed target",t,"/",len(rows),flush=True)
    summaries=[]
    for phase in PHASE:
        ds=[r for r in target_rows if r["phase"]==phase]
        for method in ALL_METHODS:
            h=np.asarray([r[method+"_hits"] for r in ds],dtype=np.float64)
            hot=np.asarray([r["HOT72_hits"] for r in ds],dtype=np.float64)
            rand=np.asarray([r["RANDOM20_hits"] for r in ds],dtype=np.float64)
            if not len(h):continue
            summaries.append(dict(phase=phase,method=method,targets=len(h),
                mean20_hits=float(h.mean()),mean_hot72_matched=float(hot.mean()),
                mean_random20_matched=float(rand.mean()),
                delta_vs_hot72=float((h-hot).mean()),
                success_8plus=int(np.sum(h>=8)),
                success_9plus=int(np.sum(h>=9)),
                success_10plus=int(np.sum(h>=10)),
                success_11plus=int(np.sum(h>=11)),
                success_12plus=int(np.sum(h>=12)),
                max_hits=int(h.max())))
    validation=[r for r in summaries if r["phase"]=="VALIDATE" and
                r["method"]!="HOT72"]
    # One win based on validation. If no candidate has POSITIVE gain
    # against HOT72, abstain from asserting improvement.
    candidate=max(validation,key=lambda r:(r["delta_vs_hot72"],
                          -CANDIDATES.index(r["method"])))
    chosen=candidate["method"] if candidate["delta_vs_hot72"]>0 else "HOT72"
    test=next(r for r in summaries if r["phase"]=="HOLDOUT" and r["method"]==chosen)
    byday=collections.defaultdict(lambda:[0,0])
    for r in target_rows:
        if r["phase"]!="HOLDOUT":continue
        b=byday[r["day"]]
        b[0]+=r[chosen+"_hits"]-r["HOT72_hits"]
        b[1]+=1
    perday=np.array([a/b for a,b in byday.values()],dtype=np.float64)
    delta=float(np.mean(perday))
    se=float(np.std(perday,ddof=1)/np.sqrt(len(perday)))
    meta=dict(version=VERSION,source_days=days,source_draws=len(rows),
        full_hours_concept="56 successive 12-draw rings",
        ring_end_snapshot="trailing72 or ring-local trailing12 draw ranks",
        first_target_index_0_based=MIN_INDEX,
        first_target_id=rows[MIN_INDEX]["id"],
        first_target_date=rows[MIN_INDEX]["day"],
        last_target_id=rows[-1]["id"],
        target_draws=len(target_rows),validation_winner=chosen,
        validate_win_delta=candidate["delta_vs_hot72"],
        holdout_day_delta_vs_hot72=delta,
        holdout_day95=[delta-1.96*se,delta+1.96*se],
        first_ring_requires_extra_warmup=WARMUP,
        release_rule="history rows index t-672 to t-1, all pool snapshots use e<=t",
        no_leakage_confirmed=bool(all(r["rolling_draws"]==672
                      and r["rings"]==56 for r in target_rows)),
        warning="Same old historically examined draws; real future unseen monitoring required")
    buckets=[]
    for (phase,last,trend,five,both),(n,hits) in sorted(bucket.items()):
        buckets.append(dict(phase=phase,last72_pool=POOLS[last],
           direction_last6=trend,visited5=five,visited_cold_and_hot=both,
           count=n,targets_containing_ball=hits,
           occurrence_percent=100*hits/n,
           fair_reference_percent=25))
    nums=[]
    for (phase,n,p),(num,hits) in sorted(number.items()):
        nums.append(dict(phase=phase,number=n,last72_pool=POOLS[p],
                  observations=num,target_appearances=hits,
                  occurrence_percent=100*hits/num))
    return (meta,summaries,target_rows,coverage_rows,buckets,
            nums,lastdetail,firstfinish)

def addcsv(z,path,rows):
    if not rows:return
    with z.open(path,"w",force_zip64=True) as f:
        out=io.TextIOWrapper(f,encoding="utf-8",newline="")
        w=csv.DictWriter(out,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
        out.flush();out.detach()

def report(meta,summaries,coverage,firstfinish):
    val=[r for r in summaries if r["phase"]=="VALIDATE"]
    hol=[r for r in summaries if r["phase"]=="HOLDOUT"]
    chosen=meta["validation_winner"]
    h=next(r for r in hol if r["method"]==chosen)
    hot=next(r for r in hol if r["method"]=="HOT72")
    recent=coverage[-1]
    z=[
      "V100 — 672 CEKILIS / 56 HALKA / 80 SAYI YON HAREKETLERI",
      f"72 complete days, {meta['target_draws']:,} historical targets.",
      "Every target uses LAST 672 PREVIOUS draws, 56 disjoint 12-draw rings.",
      "First 60 older draws initialize trailing72 at the oldest ring end.",
      "Two pool histories per ring: 12-draw and V95-compatible 72-draw.",
      "Temperature: relative rank, exactly 16 balls in each of five pools.",
      "Rising/falling velocities, reversals, full pool tours, cold->hot routes.",
      "Sliding by one real draw. No future target included in 56 rings.",
      "",
      f"First scored draw {meta['first_target_date']} #{meta['first_target_id']}; last #{meta['last_target_id']}.",
      f"Last target 80-ball full five-pool tour count in 672: {recent['numbers_all_five']}/80.",
      f"Last target 80-ball both cold+hot in 672: {recent['numbers_both_hot_and_cold']}/80.",
      f"Last target 80-ball rising/cooling in last6 rings: {recent['numbers_rising_last6']}/{recent['numbers_cooling_last6']}.",
      "",
      "VALIDATE (middle 18 days): same-target HOT72 comparison, 20-ball lists."
    ]
    for a in sorted(val,key=lambda x:-x["delta_vs_hot72"]):
        z.append(f" {a['method']:24s}: hits={a['mean20_hits']:.5f}, HOT72={a['mean_hot72_matched']:.5f}, gain={a['delta_vs_hot72']:+.5f}")
    z+=[
      "",f"VALIDATION SELECTED: {chosen}",
      "HOLDOUT (last 18 days):",
      f" HOT72 baseline mean20={hot['mean20_hits']:.6f}",
      f" Matched seeded RANDOM20 mean20={hot['mean_random20_matched']:.6f}",
      f" Selected {chosen} mean20={h['mean20_hits']:.6f}",
      f" Difference selected-HOT72={h['delta_vs_hot72']:+.6f}",
      f" Day-block 95% approx interval [{meta['holdout_day95'][0]:+.6f},{meta['holdout_day95'][1]:+.6f}]",
      f" Selected >=8, >=9, >=10, >=11, >=12 on 20 balls: {h['success_8plus']}, {h['success_9plus']}, {h['success_10plus']}, {h['success_11plus']}, {h['success_12plus']}",
      " Expected hits for any fixed 20-of-80 list: 5.0",
      " Signal status: "+("INCONCLUSIVE; not a validated forecast edge"
                  if meta["holdout_day95"][0]<=0<=meta["holdout_day95"][1]
                  else "Unexpected holdout difference; needs untouched future verification"),
      "",
      "Detailed CSVs: all targets/15 models, pool coverage, direction x pool x target counts,",
      "80-ball last target x 56 exact ring film, each ball full path stats.",
      "The 72 days were reused in earlier projects; even last18 are not",
      "truly unseen prospective targets. Sliding pool movements by themselves",
      "do not demonstrate a predictive RNG mechanism.",
    ]
    return "\n".join(z)+"\n"

def run(args):
    days,rows,x,issues,bad=load(args.source)
    meta,summaries,target,coverage,buckets,nums,detail,ball=analyze(
        days,rows,x,args.mode)
    meta.update(parser_issues=issues[:40],malformed_line_numbers=bad[:40])
    dst=Path(args.out);dst.parent.mkdir(parents=True,exist_ok=True)
    txt=report(meta,summaries,coverage,ball)
    with zipfile.ZipFile(dst,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        z.writestr("00_V100_KESIN_RAPOR.txt",txt)
        addcsv(z,"01_15_YONTEM_36_18_18_KOR_TEST.csv",summaries)
        addcsv(z,"02_HER_HEDEF_672_56_HALKA_20LI_KONTROL.csv",target)
        addcsv(z,"03_HEDEF_BASINA_80_HAVUZ_TUR_DOLULUK.csv",coverage)
        addcsv(z,"04_SICAKLIK_YON_DAVRANIS_HEDEF_OLASILIGI.csv",buckets)
        addcsv(z,"05_80_SAYI_HANGI_HAVUZDAN_HEDEFE_GELDI.csv",nums)
        addcsv(z,"06_SON_HEDEF_80_SAYI_56_HALKA_FILMI.csv",detail)
        addcsv(z,"07_80_SAYI_TUM_HAVUZ_TUR_ZAMANI.csv",ball)
        z.writestr("08_METOT_DENETIM.json",json.dumps(meta,ensure_ascii=False,
                                                      indent=2,default=str))
    print(txt,flush=True)
    print("V100 SUCCESS",dst,dst.stat().st_size,flush=True)

def selftest():
    x=np.zeros((800,80),dtype=np.uint8)
    for i in range(800):x[i,(np.arange(20)+i)%80]=1
    prefix=np.vstack((np.zeros((1,80),dtype=np.int32),
                      np.cumsum(x,axis=0,dtype=np.int32)))
    s12,f12=all_pool_states(prefix,12)
    s72,f72=all_pool_states(prefix,72)
    ends,A,B=paths(s12,s72,732)
    assert ends[0]==72 and ends[-1]==732 and len(ends)==56
    assert set(np.unique(A))==set(range(5))
    assert all((A==v).sum(axis=0).min()==16 for v in range(5))
    assert all((B==v).sum(axis=0).min()==16 for v in range(5))
    scores,feat=traces(A,B,f12[732],f72[732],f12[720])
    assert all(len(top20(v))==20 for v in scores.values())
    assert len(set(random20(12345)))==20
    assert np.all(f72[732] == np.sum(x[660:732],axis=0))
    print("V100 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v100_output/V100_672_CEKILIS_56_HALKALI_HAVUZ_YON.zip")
    p.add_argument("--mode",default="progress")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:selftest()
    else:run(a)
