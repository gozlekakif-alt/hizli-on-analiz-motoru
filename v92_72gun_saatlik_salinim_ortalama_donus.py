#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V92 — Hourly oscillation and mean reversion in Hızlı On (20 of 80).

A completed hour has exactly 12 draws (HH:02..HH:57), e.g. 00 or
07..23. The lone 01:02 draw NEVER forms a 12-draw hour. Only complete
217-draw days; consecutive 5-minute, contiguous draw-ID transitions
required. No 00->07 transition (six-hour break). 23->00 next-day
allowed ONLY for two complete neighboring days and real ID continuity.

Null H0 fair independent drawing: 12-draw number count ~ Bin(12,.25)
with expectation 3 and sd 1.5, 10-ball band sum expectation 30, SD
sqrt(12*20*(10/80)*(70/80)*(60/79)) ~4.47.
High old count dropping toward 3 and low rising toward 3 happens even
with independent RNG: regression-to-mean is NOT predictive by itself.

Statistical audit:
  - actual hour->next hour number and 8-band transitions with full
    source/target IDs, hour, counts and high/low conditional outcomes;
  - clock-matched circular-day-shift permutation: rotate target hours
    by a nonzero random number of days WITHIN its fixed clock hour,
    breaking temporal association while keeping every observed hour
    (and within-hour 20-ball constraints), static bias, hour-of-day
    variation. Effect sizes and randomization p values.
  - no hindsight model selection: first 36 COMPLETE chronological
    days train 1h and previous4h linear beta; last36 score predictive
    squared error against trivial unconditional mean 3 or 30. Controls
    are the fixed mean, recent hour, previous-4 hour; error improvement
    only on holdout if any.
  - 8 bands 1..10,11..20,..71..80; hour-of-day transitions, half1/half2.
  - The matched-clock shuffle does not fully model day-level latent
    correlations; p values exploratory. All dates repeatedly studied.
"""
from __future__ import annotations
import argparse,csv,collections,hashlib,io,json,math,zipfile
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt
from datetime import datetime

VERSION="V92.1"
SEED=921016
PERMUTES=1200
EXPECTED_DAYS=72
EXPECTED_HOURS_PER_DAY=18
SPLIT_DAYS=36
NUM_BINS=[("0-1",0,1),("2",2,2),("3",3,3),("4",4,4),("5+",5,12)]
BAND_BINS=[("<=25",0,25),("26-29",26,29),("30",30,30),
           ("31-34",31,34),(">=35",35,120)]
BANDS=[f"{a:02d}-{a+9:02d}" for a in range(1,81,10)]

def data(filepath):
    byday,issues,bad=parse_txt(filepath)
    full={}
    for day,records in byday.items():
        if len(records)==217 and [r["pos"] for r in records]==list(range(1,218)):
            full[day]=records
    days=sorted(full)
    if len(days)!=EXPECTED_DAYS or days[0]!="2026-08-01" or days[-1]!="2026-10-12":
        raise RuntimeError(f"Expected 72 complete days Aug1-Oct12, got {len(days)} "
                           f"{days[:1]}..{days[-1:]}")
    hours=[]
    for day in days:
        rows=full[day]
        for hr in [0]+list(range(7,24)):
            block=[r for r in rows if int(r["time"][:2])==hr]
            if len(block)!=12 or [int(r["time"][3:]) for r in block]!=list(range(2,60,5)):
                raise AssertionError(f"Incomplete 12-draw hour {day} {hr}")
            for i in range(1,12):
                if block[i]["id"]!=block[i-1]["id"]+1:
                    raise AssertionError(f"Broken hour ID {day} {hr}")
            counts=np.bincount([n-1 for row in block for n in row["nums"]],
                                minlength=80).astype(np.int16)
            if counts.sum()!=240:
                raise AssertionError("12x20 appearance count mismatch")
            hours.append(dict(day=day,hr=hr,start=block[0]["time"],end=block[-1]["time"],
                              first_id=block[0]["id"],last_id=block[-1]["id"],
                              counts=counts))
    assert len(hours)==EXPECTED_DAYS*EXPECTED_HOURS_PER_DAY
    return days,hours,issues,bad

def index_pairs(hours):
    out=[]
    for i in range(len(hours)-1):
        a,b=hours[i],hours[i+1]
        s=datetime.fromisoformat(a["day"]+"T"+a["end"])
        t=datetime.fromisoformat(b["day"]+"T"+b["start"])
        if (t-s).total_seconds()==300 and b["first_id"]==a["last_id"]+1:
            out.append((i,i+1))
    return out

def last4_indices(hours,pairs):
    prev={j:i for i,j in pairs}
    result={}
    for target in range(len(hours)):
        arr=[]
        node=target
        for _ in range(4):
            if node not in prev:break
            node=prev[node];arr.append(node)
        if len(arr)==4:result[target]=tuple(reversed(arr))
    return result

def binmat(X,spans):
    return (X[:,:,None]>=np.array([x[1] for x in spans])[None,None,:]) & \
           (X[:,:,None]<=np.array([x[2] for x in spans])[None,None,:])

def ccorr(old,nxt,avg):
    delta=old-avg
    de=(nxt-avg)
    d=np.sum(delta**2)
    return float(np.sum(delta*de)/d) if d else float("nan")

def one_stat(old,next_,expect,high,low):
    return {
      "n":int(old.size),"first_avg":float(old.mean()),
      "next_avg":float(next_.mean()),
      "regression_slope":ccorr(old,next_,expect),
      "old_hot_n":int((old>=high).sum()),
      "old_hot_avg":float(next_[old>=high].mean()),
      "old_cold_n":int((old<=low).sum()),
      "old_cold_avg":float(next_[old<=low].mean()),
      "old_hot_minus_cold":float(next_[old>=high].mean()-next_[old<=low].mean()),
      "expected_mean":expect,
      "high_cut":high,"low_cut":low,
      "observed_MSE_to_fixed_mean":float(np.mean((next_-expect)**2))
    }

def null_permutations(counts,ids,pairs,arrtype,expect,high,low,num=PERMUTES):
    """
    Each hour-of-day fixed group has 72 complete actual days.
    For every shuffle choose nonzero circular day shift 1..71 for each
    target clock; preserves band counts and all clock-specific patterns.
    Only target link is changed, source hour stays the same.
    """
    rng=np.random.default_rng(SEED+arrtype)
    index_byclock={}
    for j,h in enumerate(ids):
        index_byclock.setdefault(h["hr"],[]).append(j)
    arr_indices={hr:np.array(seq) for hr,seq in index_byclock.items()}
    hourpos={}
    for hr,seq in arr_indices.items():
        for k,ix in enumerate(seq):hourpos[ix]=k
    srcidx=np.array([i for i,j in pairs],dtype=int)
    tridx=np.array([j for i,j in pairs],dtype=int)
    group=collections.defaultdict(list)
    for j,index in enumerate(tridx):
        group[ids[int(index)]["hr"]].append(j)
    xx=counts[srcidx].astype(np.float64)
    yy=counts[tridx].astype(np.float64)
    observed=one_stat(xx,yy,expect,high,low)
    raw=[]
    for _ in range(num):
        newt=np.empty_like(tridx)
        for hr,posns in group.items():
            roll=int(rng.integers(1,len(arr_indices[hr])))
            ind=np.array(posns,dtype=int)
            newt[ind]=arr_indices[hr][(np.array(
               [hourpos[int(tridx[t])] for t in ind])+roll)%len(arr_indices[hr])]
        y=counts[newt].astype(np.float64)
        # Faster only two requested effect statistics, same top-level pairs
        dx=xx-expect;dy=y-expect
        slope=float((dx*dy).sum()/(dx*dx).sum())
        contrast=float(y[xx>=high].mean()-y[xx<=low].mean())
        raw.append((slope,contrast))
    ref=np.array(raw)
    result=[]
    for idx,key in enumerate(("regression_slope","old_hot_minus_cold")):
        value=observed[key];sample=ref[:,idx];p=(1+int((abs(sample-np.median(sample))>=
                     abs(value-np.median(sample))).sum()))/(len(sample)+1)
        result.append(dict(scope="INDIVIDUAL_80" if arrtype==0 else "BAND_8",
            signal=key,observed=round(value,7),null_mean=round(float(sample.mean()),7),
            null_q025=round(float(np.quantile(sample,.025)),7),
            null_q975=round(float(np.quantile(sample,.975)),7),
            null_two_sided_p=round(p,7),null_simulations=len(sample)))
    return observed,result

def make_model(pairs,hours,counts,order,train_last,expect):
    # Fit linear conditional mean y~expect + beta*(prior rolling4 or prior1 - expect).
    base={j:i for i,j in pairs}
    train=[];test=[]
    for i,j in pairs:
        arr=[i]
        node=i
        for _ in range(3):
            if node not in base:break
            node=base[node];arr.append(node)
        if len(arr)!=4:continue
        # current target j preceded by 4 full and continuous hours.
        # All conditioning happens strictly BEFORE target j.
        src=counts[np.array(arr)]
        row=dict(j=j,day=hours[j]["day"],
                 src1=src[0].astype(np.float64),
                 src4=src.mean(axis=0).astype(np.float64),
                 target=counts[j].astype(np.float64),
                 base=expect)
        if hours[j]["day"]<=train_last:train.append(row)
        else:test.append(row)
    if not train or not test:raise RuntimeError("Model train/test shortage")
    models=[]
    predictions=[]
    for rule in ("PREV1","PREV4"):
        key="src1" if rule=="PREV1" else "src4"
        old=np.stack([x[key] for x in train])
        yy=np.stack([x["target"] for x in train])
        # pooled slope across all 80 numbers / 8 bands:
        # no per-number or per-band fitted coefficients, avoids overfit
        beta=float(((old-expect)*(yy-expect)).sum()/np.sum((old-expect)**2))
        beta=float(np.clip(beta,-1,1))
        actual=np.stack([x["target"] for x in test])
        oldt=np.stack([x[key] for x in test])
        forecast=np.clip(expect+beta*(oldt-expect),0,12 if order==80 else 120)
        mse=float(np.mean((actual-forecast)**2))
        naive=float(np.mean((actual-expect)**2))
        holdwin=naive-mse
        models.append(dict(scope=f"{order}_GROUP",rule=rule,
             fit_through=train_last,train_windows=len(train),
             holdout_windows=len(test),coefficient=round(beta,8),
             holdout_MSE=round(mse,8),fixed_mean_MSE=round(naive,8),
             improvement_MSE=round(holdwin,8),
             improvement_percent=round(100*holdwin/naive,6)))
        for i,x in enumerate(test):
            predictions.append(dict(target_day=x["day"],
              target_draw_id=hours[x["j"]]["first_id"],target_hr=hours[x["j"]]["hr"],
              scope="SINGLE_BALL" if order==80 else "BAND10",
              rule=rule,model_beta=round(beta,7),
              total_squared_error=float(((actual[i]-forecast[i])**2).sum()),
              total_mean_baseline_squared_error=float(((actual[i]-expect)**2).sum()),
              n_features=order,
              error_gain=float(((actual[i]-expect)**2).sum()-
                               ((actual[i]-forecast[i])**2).sum())))
    return models,predictions

def csvrows(z,path,rows):
    if not rows:return
    with z.open(path,"w",force_zip64=True) as b:
        t=io.TextIOWrapper(b,encoding="utf-8",newline="")
        w=csv.DictWriter(t,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows);t.flush();t.detach()

def run(source,outname):
    days,hours,issues,bad=data(source)
    pairs=index_pairs(hours)
    prev4=last4_indices(hours,pairs)
    if len(pairs)<1000:raise RuntimeError("Insufficient exact adjacent pairs")
    NUM=np.stack([x["counts"] for x in hours]).astype(np.float64)
    BND=NUM.reshape(-1,8,10).sum(axis=2)
    trday=days[SPLIT_DAYS-1]
    print(f"V92 full days={len(days)} hours={len(hours)}, adjacent pairs={len(pairs)}, next-hour with prev4={len(prev4)}, train thru {trday}",flush=True)
    numstats,nperm=null_permutations(NUM,hours,pairs,0,3,5,1)
    print("V92 individual 80 permutations complete",flush=True)
    bandstats,bperm=null_permutations(BND,hours,pairs,1,30,35,25)
    print("V92 eight 10-band permutations complete",flush=True)
    modelsnum,prednum=make_model(pairs,hours,NUM,80,trday,3)
    modelsband,predband=make_model(pairs,hours,BND,8,trday,30)
    mrs=modelsnum+modelsband
    transitions=[]
    perband=[]
    pernumber=[]
    bins80=collections.defaultdict(lambda:[0,0,0])
    binsband=collections.defaultdict(lambda:[0,0,0])
    matrix=np.zeros((5,5),dtype=int)
    matrixB=np.zeros((5,5),dtype=int)
    def cat(x,spans):
        for i,(label,lo,hi) in enumerate(spans):
            if lo<=x<=hi:return i
        raise AssertionError("Uncovered count")
    for i,j in pairs:
        src=hours[i];target=hours[j]
        rowbase=dict(prev_day=src["day"],prev_hour=f"{src['hr']:02d}",
           prev_draw_start=src["first_id"],prev_draw_end=src["last_id"],
           next_day=target["day"],next_hour=f"{target['hr']:02d}",
           next_draw_start=target["first_id"],next_draw_end=target["last_id"],
           split="TRAIN36" if target["day"]<=trday else "HOLDOUT36")
        for n in range(80):
            x=int(NUM[i,n]);y=int(NUM[j,n])
            matrix[cat(x,NUM_BINS),cat(y,NUM_BINS)]+=1
            bins80[NUM_BINS[cat(x,NUM_BINS)][0]][0]+=1
            bins80[NUM_BINS[cat(x,NUM_BINS)][0]][1]+=y
            bins80[NUM_BINS[cat(x,NUM_BINS)][0]][2]+=int(y>=5)
            transitions.append(dict(**rowbase,number=n+1,prev_hour_occurrences=x,
                next_hour_occurrences=y,
                delta=y-x,turned_toward_3=int(abs(y-3)<abs(x-3)),
                previous_class=NUM_BINS[cat(x,NUM_BINS)][0],
                next_class=NUM_BINS[cat(y,NUM_BINS)][0]))
        for b,name in enumerate(BANDS):
            x=int(BND[i,b]);y=int(BND[j,b])
            matrixB[cat(x,BAND_BINS),cat(y,BAND_BINS)]+=1
            binsband[BAND_BINS[cat(x,BAND_BINS)][0]][0]+=1
            binsband[BAND_BINS[cat(x,BAND_BINS)][0]][1]+=y
            binsband[BAND_BINS[cat(x,BAND_BINS)][0]][2]+=int(y>=35)
            perband.append(dict(**rowbase,band=name,
                prev_hour_occurrences=x,next_hour_occurrences=y,
                delta=y-x,turned_toward_30=int(abs(y-30)<abs(x-30)),
                previous_class=BAND_BINS[cat(x,BAND_BINS)][0],
                next_class=BAND_BINS[cat(y,BAND_BINS)][0]))
    splitcomparison=[]
    for label,data,avg,lo,hi,names in [
        ("SINGLE_NUMBER",NUM,3,1,5,[str(n+1) for n in range(80)]),
        ("TEN_BAND",BND,30,25,35,BANDS)]:
        for phase,ps in (("TRAIN36",[(i,j) for i,j in pairs if hours[j]["day"]<=trday]),
                         ("HOLDOUT36",[(i,j) for i,j in pairs if hours[j]["day"]>trday])):
            x=data[[i for i,j in ps]]
            y=data[[j for i,j in ps]]
            s=one_stat(x,y,avg,hi,lo)
            splitcomparison.append(dict(phase=phase,scope=label,pairs=len(ps),
                slope=round(s["regression_slope"],8),
                old_high_n=s["old_hot_n"],
                old_high_next_mean=round(s["old_hot_avg"],7),
                old_low_n=s["old_cold_n"],
                old_low_next_mean=round(s["old_cold_avg"],7),
                high_minus_low=round(s["old_hot_minus_cold"],7)))
        for k,name in enumerate(names):
            x=data[[i for i,j in pairs],k];y=data[[j for i,j in pairs],k]
            z=dict(scope=label,name=name,n_pairs=len(x),
                   observed_overall_mean=round(float(data[:,k].mean()),7),
                   observed_total=round(float(data[:,k].sum()),7),
                   prior_hour_mean=round(float(x.mean()),7),
                   subsequent_mean=round(float(y.mean()),7),
                   lag1_pearson=round(float(np.corrcoef(x,y)[0,1]),7)
                       if x.std()>0 and y.std()>0 else 0,
                   next_given_prior_high=round(float(y[x>=hi].mean()),6)
                       if (x>=hi).sum() else None,
                   next_given_prior_low=round(float(y[x<=lo].mean()),6)
                       if (x<=lo).sum() else None)
            (pernumber if label=="SINGLE_NUMBER" else perband_summary).append(z) if False else None
            if label=="SINGLE_NUMBER":pernumber.append(z)
            else:
                # Append 8 summaries separately from all per-pair rows
                pass
    bandsummary=[]
    for k,name in enumerate(BANDS):
        x=BND[[i for i,j in pairs],k];y=BND[[j for i,j in pairs],k]
        bandsummary.append(dict(band=name,pairs=len(x),overall_mean=round(float(BND[:,k].mean()),6),
          lag1_correlation=round(float(np.corrcoef(x,y)[0,1]),7),
          observed_next_when_high=round(float(y[x>=35].mean()),6),
          observed_next_when_low=round(float(y[x<=25].mean()),6),
          high_n=int((x>=35).sum()),low_n=int((x<=25).sum())))
    profiles=[]
    for hr in sorted({h["hr"] for h in hours}):
        p=[(i,j) for i,j in pairs if hours[j]["hr"]==hr]
        if not p:continue
        i=np.array([x[0] for x in p]);j=np.array([x[1] for x in p])
        profiles.append(dict(target_hour=f"{hr:02d}",transition_pairs=len(p),
           mean_band_slope=round(ccorr(BND[i],BND[j],30),7),
           mean_number_slope=round(ccorr(NUM[i],NUM[j],3),7),
           mean_high_next=round(float(NUM[j][NUM[i]>=5].mean()),7),
           mean_low_next=round(float(NUM[j][NUM[i]<=1].mean()),7),
           mean_abs_band_change=round(float(np.mean(abs(BND[j]-BND[i]))),7)))
    transitionmatrix=[]
    for oldix, oldlabel in enumerate([x[0] for x in NUM_BINS]):
        for nextix,nextlabel in enumerate([x[0] for x in NUM_BINS]):
            transitionmatrix.append(dict(scope="SINGLE_NUMBER",from_class=oldlabel,to_class=nextlabel,
               observed_count=int(matrix[oldix,nextix]),
               p_given_prior=round(matrix[oldix,nextix]/matrix[oldix].sum(),7)))
    for oldix,oldlabel in enumerate([x[0] for x in BAND_BINS]):
        for nextix,nextlabel in enumerate([x[0] for x in BAND_BINS]):
            transitionmatrix.append(dict(scope="TEN_BAND",from_class=oldlabel,to_class=nextlabel,
                observed_count=int(matrixB[oldix,nextix]),
                p_given_prior=round(matrixB[oldix,nextix]/matrixB[oldix].sum(),7)))
    status=[]
    for typ,bins in (("SINGLE_NUMBER",bins80),("TEN_BAND",binsband)):
        for k,v in bins.items():
            status.append(dict(scope=typ,previous_hour_class=k,n=v[0],
               next_hour_mean=round(v[1]/v[0],7),
               next_hour_above_high_rate=round(v[2]/v[0],7)))
    simulation=bperm+nperm
    pformat=lambda p:f" {p['scope']} {p['signal']}: observed={p['observed']:+.7f}, "+
                       f"matched-clock shuffle mean={p['null_mean']:+.7f}, "+
                       f"95% null range [{p['null_q025']:+.7f};{p['null_q975']:+.7f}], "+
                       f"two-sided p={p['null_two_sided_p']:.5f}"
    bsd=math.sqrt(12*20*(10/80)*(70/80)*(60/79))
    report=[
        "V92 — 72 GUN HER SAAT 80 SAYI / SEKIZ 10LUK BANT ORTALAMAYA SALINIM TESTI",
        f"Complete days {len(days)}; full 12-draw hours {len(hours)};",
        f"truly adjacent hour pairs {len(pairs)}, last4h -> fifth pairs {len(prev4)}.",
        "01:02 one-draw singleton ignored; 00->07 six-hour gap not connected;",
        "23->00 next-day allowed only if real 5min+ID continuous;",
        "Aug23 incomplete day excluded, so no synthetic gap crossing.",
        "FAIR RNG exactly 240 ball appearances/hour across all 80:",
        "single ball E=3/hour, SD=1.500;",
        f"ten-ball band E=30/hour, SD={bsd:.4f}.",
        "If previous hour 0/1 appearances, NEXT HOUR E remains 3;",
        "if previous hour >=5 appearances, NEXT HOUR E remains 3;",
        "an apparent drop/rise to average is ORDINARY RNG regression-to-mean.",
        "",
        "OBSERVED ALL-DAY HOURLY MOVEMENT:",
        f" individual old>=5 n={numstats['old_hot_n']}, next mean={numstats['old_hot_avg']:.6f};",
        f" individual old<=1 n={numstats['old_cold_n']}, next mean={numstats['old_cold_avg']:.6f};",
        f" ten-band old>=35 n={bandstats['old_hot_n']}, next mean={bandstats['old_hot_avg']:.6f};",
        f" ten-band old<=25 n={bandstats['old_cold_n']}, next mean={bandstats['old_cold_avg']:.6f}.",
        "",
        f"CLOCK-CONTROLLED REAL-HOUR SHUFFLE {PERMUTES} simulations:",
        *(pformat(v) for v in simulation),
        "",
        "FIRST36 TRAIN -> LAST36 OUT-OF-PERIOD LINEAR CALIBRATION:",
    ]
    for q in mrs:report.append(
        f" {q['scope']} {q['rule']} coefficient={q['coefficient']:+.6f},"
        f" mean-only holdout MSE={q['fixed_mean_MSE']:.6f},"
        f" learned holdout MSE={q['holdout_MSE']:.6f},"
        f" improvement={q['improvement_percent']:+.5f}%,"
        f" train windows={q['train_windows']},test windows={q['holdout_windows']}.")
    report+=["",
       "Hour-close ('returns to mean') by itself does not mean it anticipates RNG.",
       "Use observed lag persistence/excess versus matched shuffled chronology",
       "and unseen holdout MSE versus FIXED baseline. If no improvement,",
       "no defensible next-hour signal regardless of apparent oscillation.",
       "Clock-matched permutation keeps each observed 12-draw hour intact",
       "but does not fully account for day-specific latent dependencies.",
       "Overlapping hour pairs share samples, so do not treat n*80 as",
       "independent trials. Period has been analyzed by prior V-models;",
       "even last36 holdout is NOT untouched independent confirmation.",
       "5+ number means at least 5 appearances in 12 draws, not 5/5",
       "same-draw exact family. 10-ball band total 30 represents draws",
       "from ten numbers across 12 draws, not 30 different numbers."
    ]
    out=Path(outname);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=5,allowZip64=True) as z:
        z.writestr("00_V92_ORTALAMAYA_DONUS_KISA_KARAR.txt","\n".join(report))
        csvrows(z,"01_80_SAYI_HER_KOMSU_SAAT_DONUSUM.csv",transitions)
        csvrows(z,"02_SEKIZ_BANT_HER_KOMSU_SAAT_DONUSUM.csv",perband)
        csvrows(z,"03_80_SAYI_SAATLIK_UZUN_DONEM_GORUNUM.csv",pernumber)
        csvrows(z,"04_SEKIZ_BANT_AYRI_ORTALAMA_SALINIM.csv",bandsummary)
        csvrows(z,"05_SAYI_VE_BANT_DURUM_GECIS_5X5.csv",transitionmatrix)
        csvrows(z,"06_HAREKET_ESIKLERI_SONRAKI_SAAT_ORTALAMA.csv",status)
        csvrows(z,"07_SAAT_SAAT_SALINIM_YON.csv",profiles)
        csvrows(z,"08_ILK36_SON36_SALINIM_DEGISIMI.csv",splitcomparison)
        csvrows(z,"09_1SAAT_VE_4SAAT_HAFIZA_TEST_MSE.csv",mrs)
        csvrows(z,"10_SON36_SAAT_GERCEK_HATA_VS_SABIT_ORTALAMA.csv",prednum+predband)
        csvrows(z,"11_GERCEK_SAAT_VS_SAAT_SIRA_RASTGELE_KONTROL.csv",simulation)
        z.writestr("12_DENETIM_METODU.txt","\n".join([
          "ONLY fully validated 217-draw days; 18 real 12-draw hours per day.",
          "No 01:02 singleton, no 00->07 break, no missing day crossing.",
          "Each next-hour candidate uses only earlier 12 real draws.",
          "All 80 number hourly count sum fixed 240; sum 8 band counts fixed 240.",
          "The null of independent fair 20/80 sampling forces per-number",
          "E[next|previous]=3, ten-number band E[next|previous]=30.",
          "RNG predicts regression to mean even without deterministic bias.",
          "Clock-matched null: circularly shift target-hour records across",
          "the 72 dates, retaining clock-specific distributions and all 20",
          "balls per individual original draw inside each intact hour.",
          "1200 random shifts; this is an exploratory temporal-order test.",
          "Train first36 complete days; test last36. Fit single shared",
          "slope for all numbers or bands: no multiple testing over 80.",
          "Previous1 / previous4 full hours, no target leakage.",
          "Compute squared error and compare to trivial fixed mean.",
          "No claims about internal seed, server time, draw filters.",
          "Previously researched calendar period not a fresh holdout."
        ]))
        z.writestr("13_AUDIT.json",json.dumps(dict(
           version=VERSION,days=len(days),first=days[0],last=days[-1],
           complete_hours=len(hours),adjacent_pairs=len(pairs),
           previous4_pairs=len(prev4),train_cutoff=trday,
           tenband_sd=bsd,number_stat=numstats,band_stat=bandstats,
           shuffle=simulation,models=mrs,half=splitcomparison,
           hour_profiles=profiles,issues=issues[:20],bad_lines=bad[:20]),
           ensure_ascii=False,indent=2))
    print("\n".join(report),flush=True)
    print("V92 DONE "+str(out)+" "+str(out.stat().st_size),flush=True)

def selftest():
    x=np.ones((12,80),dtype=np.float64);m=binmat(x,NUM_BINS)
    assert m.shape==(12,80,5) and m.sum()==960
    assert NUM_BINS[0][1:]==(0,1)
    assert len(BANDS)==8 and math.isclose(math.sqrt(2.25),1.5)
    xx=np.array([[5.,0.],[0.,5.]])
    assert abs(ccorr(xx,xx,3)-1)<1e-12
    print("V92 SELFTEST OK")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v92_output/V92_72GUN_80_SAYI_8BANT_HER_SAAT_ORTALAMA_DONUS.zip")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    selftest() if a.selftest else run(a.source,a.out)
