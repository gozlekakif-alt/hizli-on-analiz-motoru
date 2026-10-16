#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V122: NO FAMILIES. Four short nested pool turning points vs real-time
12-draw block-count reversal and next individual target draw.

This is exploratory historical replay. All 56 cumulative windows
12,24,36,...,672 end BEFORE target t. For REAL_TIME_REBOUND,
six consecutive disjoint 12-draw blocks are taken from last72;
do NOT confuse those actual times with nested 12,24,36,72 ranks.
TRAIN36 for descriptive discovery; VALIDATE18 for winner selection;
LAST18 report unchanged winner; these dates were already analyzed
in earlier V9-V121 and are NOT genuinely unseen holdout data.
"""
from __future__ import annotations
import argparse,csv,io,json,zipfile,random,collections
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load

LENS=np.arange(12,673,12,dtype=np.int32)
NAMES=("HOT72","HOT12","HOT672",
 "TURN24_VALLEY","TURN24_PEAK","TURN36_VALLEY","TURN36_PEAK",
 "TWO_TURN_ANY","SHORT_HOT_LONG_COOL","SHORT_COOL_LONG_HOT",
 "REAL_12_REBOUND","REAL_12_PEAK","REAL_12_ACCEL",
 "REAL_12_DECEL","COMBO_TURN_REAL_REBOUND","COMBO_TURN_REAL_PEAK")
SIGNALS=NAMES[3:]
RANDOM=("RANDOM0","RANDOM1","RANDOM2","RANDOM3","RANDOM4","RANDOM5","RANDOM6","RANDOM7")
ALL=NAMES+RANDOM
KS=(3,4,5,6,8,10,20)
WIN_AT=10
SEED=12211017
PHASES=("TRAIN36","VALIDATE18","LAST18","EXTRA")
PHIDX={a:i for i,a in enumerate(PHASES)}
POOLS=("SOGUK","SERIN","NOTR","ILIK","SICAK")

def save_csv(z,name,rows):
    if not rows:return
    with z.open(name,"w",force_zip64=True) as raw:
        f=io.TextIOWrapper(raw,encoding="utf-8-sig",newline="")
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows);f.flush();f.detach()

def get_features(prefix,X,t):
    assert t>=672
    counts=prefix[t][None,:]-prefix[t-LENS]
    assert counts.shape==(56,80)
    assert int(counts[-1].sum())==13440
    idx=np.argsort(counts,axis=1,kind="stable")
    pool=np.empty((56,80),dtype=np.int8)
    pool[np.arange(56)[:,None],idx]=np.repeat(np.arange(5,dtype=np.int8),16)
    # one particular target's 56 pool values always refer to the SAME t
    p12,p24,p36,p72,p672=(pool[z] for z in (0,1,2,5,55))
    c12,c24,c36,c72,c672=(counts[z] for z in (0,1,2,5,55))
    # Truly successive chronological disjoint blocks, newest index=0.
    b=np.stack([prefix[t-12*k]-prefix[t-12*(k+1)]
                for k in range(6)],axis=0)
    assert b.shape==(6,80)
    assert np.array_equal(b[:1],counts[:1])
    assert np.all(b.sum(axis=0)==c72)
    b0,b1,b2=b[:3]
    # Nested length-direction reversals (NOT time progression).
    v24=(p12>p24)&(p36>p24)
    peak24=(p12<p24)&(p36<p24)
    v36=(p24>p36)&(p72>p36)
    peak36=(p24<p36)&(p72<p36)
    anyturn=v24|peak24|v36|peak36
    # Time-ordered last 36 real observations grouped as 3*12.
    # b2 older -> b1 -> b0 most recent, valleys/peaks at b1.
    rebound=(b0>b1)&(b2>b1)
    peak=(b0<b1)&(b2<b1)
    accel=(b0-b1>b1-b2)
    decel=(b0-b1<b1-b2)
    masks={
      "TURN24_VALLEY":v24,"TURN24_PEAK":peak24,
      "TURN36_VALLEY":v36,"TURN36_PEAK":peak36,
      "TWO_TURN_ANY":anyturn,
      "SHORT_HOT_LONG_COOL":(p12>=3)&(p672<=1),
      "SHORT_COOL_LONG_HOT":(p12<=1)&(p672>=3),
      "REAL_12_REBOUND":rebound,"REAL_12_PEAK":peak,
      "REAL_12_ACCEL":accel,"REAL_12_DECEL":decel,
      "COMBO_TURN_REAL_REBOUND":anyturn&rebound,
      "COMBO_TURN_REAL_PEAK":anyturn&peak,
    }
    assert set(masks)==set(SIGNALS)
    ep=(80-np.arange(80,dtype=float))*1e-8
    rankbase=c72.astype(float)/73.0+ep
    scores={"HOT72":c72.astype(float)+ep,
      "HOT12":c12.astype(float)+ep,
      "HOT672":c672.astype(float)+ep}
    scores.update({name:flag.astype(float)*100+rankbase
                   for name,flag in masks.items()})
    return masks,scores,counts,pool,b

def main(src,output):
    dates,rows,X,issues,bad=load(src)
    n=len(X)
    assert n==len(rows)
    prefix=np.vstack((np.zeros((1,80),dtype=np.int32),
                     np.cumsum(X,dtype=np.int32,axis=0)))
    days=sorted(d for d in dates if d<="2026-10-12")
    assert len(days)==72
    phase_by_day={day:"TRAIN36" if i<36 else
                      "VALIDATE18" if i<54 else "LAST18"
                  for i,day in enumerate(days)}
    # (phase,signal) true 1/0 observations and hits
    stats=collections.defaultdict(lambda:[0,0])
    daily=collections.defaultdict(lambda:[0,0])
    phase_draws=collections.Counter()
    # All nominated signal groups including same-hot72/hot672 controls
    # Actual single-draw appearance must be compared against 25% baseline.
    # For each signal include exact N of qualifying members at each t.
    perf=collections.defaultdict(lambda:[0]*9)
    tickets=[]
    signal_snapshots=[]
    last_profile=[]
    for t in range(672,n):
        date=rows[t]["day"]
        phase=phase_by_day.get(date,"EXTRA")
        truth=X[t]
        masks,scores,counts,pool,blocks=get_features(prefix,X,t)
        phase_draws[phase]+=1
        z=dict(date=date,phase=phase,target_id=rows[t]["id"])
        for signal in SIGNALS:
            q=masks[signal]
            nh=int(q.sum());hit=int(truth[q].sum())
            stats[(phase,signal)][0]+=nh
            stats[(phase,signal)][1]+=hit
            daily[(phase,date,signal)][0]+=nh
            daily[(phase,date,signal)][1]+=hit
            z[signal+"_n"]=nh
            z[signal+"_hits"]=hit
        signal_snapshots.append(z)
        for model in ALL:
            if model in scores:
                picked=np.lexsort((np.arange(80),-scores[model]))[:20]
            else:
                ri=int(model[-1])
                picked=np.array(random.Random(SEED+t*48151+ri*8319)
                        .sample(range(80),20),dtype=np.int32)
            hitbits=truth[picked]
            prefixhits=np.cumsum(hitbits)
            rec=dict(date=date,phase=phase,target_id=rows[t]["id"],
                     method=model,
                     selected20="-".join(map(str,picked+1)),
                     target_20bits="".join(map(str,hitbits)))
            for k in KS:
                h=int(prefixhits[k-1])
                q=perf[(phase,model,k)]
                q[0]+=1;q[1]+=h;q[2]+=int(h==k)
                q[3]+=int(h>=5);q[4]+=int(h>=6)
                q[5]+=int(h>=7);q[6]+=int(h>=8)
                q[7]+=int(h>=9);q[8]+=int(h>=10)
                rec["hit_"+str(k)]=h
            tickets.append(rec)
        if t==n-1:
            for num in range(80):
                last_profile.append(dict(number=num+1,
                  target_id=rows[t]["id"],
                  past_672_bits="".join(map(str,X[t-672:t,num])),
                  all56_cumulative_counts="|".join(map(str,counts[:,num])),
                  all56_cumulative_pools="".join("CSNIH"[p] for p in pool[:,num]),
                  recent6_separate12blocks="|".join(map(str,blocks[:,num])),
                  **{signal:int(masks[signal][num]) for signal in SIGNALS},
                  target_outcome_1_0=int(truth[num])))
        if (t-671)%2500==0:
            print("V122 replayed target",t-671,"of",n-672,flush=True)
    # Last18 daily grouped rates for a single number n (NOT treating
    # correlated successive number/draw events as independent).
    cirows=[]
    for phase in ("VALIDATE18","LAST18","TRAIN36"):
        ds=sorted({d for (p,d,signal) in daily if p==phase})
        for signal in SIGNALS:
            byday=np.array([daily[(phase,d,signal)] for d in ds],dtype=float)
            if byday[:,0].sum()==0:continue
            rate=byday[:,1].sum()/byday[:,0].sum()
            rng=np.random.default_rng(SEED+len(phase)*31+len(signal)*1009)
            samp=byday[rng.integers(0,len(ds),(4000,len(ds)))].sum(axis=1)
            boots=(samp[samp[:,0]>0,1]/samp[samp[:,0]>0,0])
            if not len(boots):continue
            cirows.append(dict(phase=phase,signal=signal,
              qualifying_number_draws=int(byday[:,0].sum()),
              target_ones=int(byday[:,1].sum()),
              rate_percent=round(100*rate,4),
              expected_null_percent=25.0,
              low95_percent=round(100*float(np.quantile(boots,.025)),4),
              high95_percent=round(100*float(np.quantile(boots,.975)),4),
              number_of_days=len(ds)))
    # Select from VALIDATE18 on 10-number average; don't let holdout rank choose.
    ranking=[]
    for model in ALL[:len(NAMES)]:
        q=perf[("VALIDATE18",model,WIN_AT)]
        ranking.append((q[1]/q[0],model))
    ranking.sort(key=lambda x:(-x[0],x[1]))
    chosen=ranking[0][1]
    assert chosen in NAMES
    scorecard=[]
    for phase in ("TRAIN36","VALIDATE18","LAST18","EXTRA"):
        for model in ALL:
            for k in KS:
                a=perf[(phase,model,k)]
                if not a[0]:continue
                scorecard.append(dict(phase=phase,model=model,k=k,
                    target_draws=a[0],mean_hits=round(a[1]/a[0],6),
                    expected_mean=k/4.,perfect_k_of_k=a[2],
                    hits_5plus=a[3],hits_6plus=a[4],
                    hits_7plus=a[5],hits_8plus=a[6],
                    hits_9plus=a[7],hits_10plus=a[8],
                    preselected_on_validation=(model==chosen)))
    # Fixed winner on last18 and random-eight mean (same coupon budget)
    def rs(phase,method,k):
        a=perf[(phase,method,k)]
        return a[1]/a[0],a[2],a[3],a[4],a[6],a[8]
    lines=[
      "V122 SAYI BAZLI 12 24 36 72 KUMULATIF HAVUZ YON KIRILMASI / GERCEK 12 BLOK",
      f"Source {n} real draws; last #{rows[-1]['id']} on {rows[-1]['day']}.",
      f"Tested {n-672} next draws; family identities NOT used.",
      "Nested 56 pools (12,24,36,..672) freeze just BEFORE a target.",
      "Pool turning point is a difference between simultaneous lookback lengths,",
      "NOT a chronological warming episode. Chronological block rebounds use",
      "three SEPARATE 12-draw blocks in the previous 36 draws.",
      "All 13 signal masks are pretarget; immediate target outcomes are labels.",
      "Every signal method ranks flagged numbers first then fills from HOT72.",
      "16 fixed methods + 8 independently seeded random controls = 24 methods.",
      "Model chosen by VALIDATE18 10-number average, frozen for LAST18.",
      "The same historical data were studied in V9..V121, so LAST18 is NOT",
      "independent truly novel future holdout.",
      f"phase targets {dict(phase_draws)}",
      f"VALIDATE18 winner at k10 = {chosen}.",
      ""]
    for k in KS:
        chosen_rate=rs("LAST18",chosen,k)
        hot=rs("LAST18","HOT72",k)
        rand=np.array([rs("LAST18",x,k) for x in RANDOM],float).mean(axis=0)
        lines.append(f"LAST18 k={k} "
          f"winner_avg={chosen_rate[0]:.4f} perfect={chosen_rate[1]} "
          f"5+={chosen_rate[2]} 6+={chosen_rate[3]} "
          f"8+={chosen_rate[4]} 10+={chosen_rate[5]} "
          f"HOT72_avg={hot[0]:.4f} HOT72_perfect={hot[1]} "
          f"random8_avg={rand[0]:.4f} random8_perfect_mean={rand[1]:.3f}")
    lines.extend(["","TOP VALIDATION MODELS k10:"])
    for rank,(mean,model) in enumerate(ranking[:8],1):
        vr=rs("LAST18",model,10)
        lines.append(f" {rank}. {model} val_avg={mean:.5f} "
           f"LAST18_avg={vr[0]:.5f}, LAST18_8plus={vr[4]}, LAST18_10plus={vr[5]}")
    lines.extend(["","REAL SIGNAL PER-NUMBER HIT RATES LAST18 (day-bootstrap 95%):"])
    for x in cirows:
        if x["phase"]=="LAST18":
            lines.append(f" {x['signal']}: n={x['qualifying_number_draws']}, "
                f"hits={x['target_ones']}, {x['rate_percent']:.4f}% "
                f"95%=[{x['low95_percent']:.4f},{x['high95_percent']:.4f}]")
    # Main paired day test for previously chosen winner vs HOT72/random8.
    # Replay records to build per-day metrics, without re-accessing target features.
    dayperf=collections.defaultdict(list)
    for z in tickets:
        if z["phase"]=="LAST18" and z["method"] in (
            chosen,"HOT72",*RANDOM):
            dayperf[(z["date"],z["method"])].append(int(z["hit_10"]))
    distinct=sorted({key[0] for key in dayperf})
    paired=[]
    for comparator in ("HOT72","RANDOM8_MEAN"):
        dif=[]
        for day in distinct:
            own=np.mean(dayperf[(day,chosen)])
            if comparator=="HOT72":
                base=np.mean(dayperf[(day,"HOT72")])
            else:
                base=np.mean([np.mean(dayperf[(day,r)]) for r in RANDOM])
            dif.append(float(own-base))
        dif=np.asarray(dif)
        rng=np.random.default_rng(SEED+len(comparator))
        bs=dif[rng.integers(0,len(dif),(8000,len(dif)))].mean(axis=1)
        paired.append(dict(comparator=comparator,
            locked_winner=chosen,days=len(distinct),
            mean_hit_difference=round(float(dif.mean()),6),
            lower95=round(float(np.quantile(bs,.025)),6),
            upper95=round(float(np.quantile(bs,.975)),6)))
    lines.append("")
    for x in paired:
        lines.append(f"HOLDOUT LAST18 {chosen} - {x['comparator']} 10-number "
              f"mean={x['mean_hit_difference']:+.5f} "
              f"95%=[{x['lower95']:+.5f},{x['upper95']:+.5f}]")
    lines.extend(["","This is exploratory historical pattern mining, NOT evidence",
      "of a time-tested RNG prediction advantage until truly new forward draws.",
      "Fair 20 of 80 game has single-number expectation exactly 25%.",
      "Beware perfect-hit cherry-picking across many models and ticket sizes."])
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_V122_KISA_GERCEK_SONUC.txt","\n".join(lines)+"\n")
        save_csv(z,"01_24_MODEL_15118_CEKILIS_3_4_5_6_8_10_20_ISABET.csv",tickets)
        save_csv(z,"02_HAVUZ_YON_KIRILMASI_13_ONCU_GRUP_HEDEF_SONUC.csv",signal_snapshots)
        save_csv(z,"03_GUN_BAZLI_SINYAL_25YUZDE_GUVEN_ARALIK.csv",cirows)
        save_csv(z,"04_24_MODEL_DONEMLER_7_FARKLI_KUPON.csv",scorecard)
        save_csv(z,"05_SON_HEDEF_80_SAYI_56_HALKA_YON_1_0_PROFIL.csv",last_profile)
        save_csv(z,"06_SON18_KILITLI_MODEL_ESLENMIS_KONTROL.csv",paired)
        z.writestr("07_TEST_DENETIM.json",json.dumps(dict(
          n_source_draws=n,n_targets=n-672,last_id=rows[-1]["id"],
          signal_groups=list(SIGNALS),candidate_methods=list(NAMES),
          random_controls=list(RANDOM),all_ticket_lengths=list(KS),
          validation_winner=chosen,
          target_not_in_predictor=True,families_not_used=True,
          chronological_truly_new_holdout=False,
          data_dates_touched_prior_versions=True),ensure_ascii=False,indent=2))
    print("\n".join(lines),flush=True)
    print("V122 VERIFIED OUTPUT",output,output.stat().st_size,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v122_output/V122_56_HALKA_12_24_36_72_YON_KIRILMASI_TEST.zip")
    a=p.parse_args()
    main(a.source,a.out)
