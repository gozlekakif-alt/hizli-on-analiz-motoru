#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V93 — cryptanalysis-inspired fixed-weight RNG output audit.

Draw output is a 80-bit *constant Hamming weight 20* vector, NOT raw PRNG
output. This coding erases internal generator state. CSPRNGs with unknown
seed cannot be reverse-engineered from this limited transformed output.

Two separate real tests:
A. 12 preregistered aggregate diagnostics: 499 independently simulated
   full 20-of-80 corpora on EXACT same draw clock and gaps. No incorrect
   50/50 monobit assumption. Empirical two-sided deviations, per-metric
   Monte Carlo p and familywise max-statistic correction, one global p.
   XOR Hamming (=40-2 overlap) vs exact hypergeometric expectation.
B. Strict source-only TRAIN first36 full days, VAL next18, HOLD last18.
   Treat last3 80-bit source vectors as an LFSR/XOR-style binary feature.
   Predeclared smoothed transition-conditional rankings for 10-number
   tickets. Select ONE method by VALIDATE; report frozen HOLDOUT matched
   seeded random10 and unconditional source frequency10. NO future
   labels, no post-target number selection. No prospective claim because
   these dates have been examined in earlier models.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,io,json,math,random,zipfile
from datetime import datetime
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V93.1"
SEED=931016
NULL_REPS=499
LAGS=(1,2,3,6,12,24,48)
METRIC_KEYS=(
  "NUMBER_FREQUENCY_DISPERSION","INTRA_DRAW_NEIGHBORS",
  "XOR_LAG1_MEAN","XOR_LAG1_VARIANCE",
  "LAG3_OVERLAP","LAG6_OVERLAP","LAG12_OVERLAP",
  "LAG24_OVERLAP","LAG48_OVERLAP",
  "LAG1_CLOCK_MAX_DEVIATION","MAX_80BIT_CUSUM",
)
CONDITIONAL_METHODS=("MARKOV_LAST","XOR3_PARITY","PATTERN3",
                     "TRAIN_FREQ10")
ALL_METHODS=("RANDOM10",)+CONDITIONAL_METHODS

def load(src):
    byday,issues,bad=parse_txt(src)
    full={day:v for day,v in byday.items() if
          len(v)==217 and [r["pos"] for r in v]==list(range(1,218))}
    days=sorted(full)
    if len(days)!=72 or days[0]!="2026-08-01" or days[-1]!="2026-10-12":
        raise RuntimeError(f"Expected archived 72 full days: {len(days)}")
    rows=[r for d in days for r in full[d]]
    x=np.zeros((len(rows),80),dtype=np.uint8)
    for i,r in enumerate(rows):
        x[i,np.asarray(r["nums"],dtype=int)-1]=1
    if not np.all(x.sum(axis=1)==20):raise AssertionError("Not 20 balls")
    ids=np.array([r["id"] for r in rows])
    times=np.array([np.datetime64(r["day"]+"T"+r["time"]) for r in rows],
                   dtype="datetime64[m]")
    clock=np.array([int(r["time"][:2]) for r in rows])
    per_lag={}
    for lag in LAGS:
        good=(ids[lag:]-ids[:-lag]==lag)&(
            (times[lag:]-times[:-lag])/np.timedelta64(1,"m")==5*lag)
        per_lag[lag]=np.nonzero(good)[0]+lag
    return days,rows,x,ids,clock,per_lag,issues,bad

def random_corpus(n,rng):
    # EXACTLY 20-of-80 without replacement in every row; random
    # permutation ranks are uniform under continuous iid keys.
    a=rng.random((n,80),dtype=np.float32)
    chosen=np.argpartition(a,20,axis=1)[:,:20]
    x=np.zeros((n,80),dtype=np.uint8)
    x[np.arange(n)[:,None],chosen]=1
    return x

def raw_metrics(x,lagidx,clock):
    n=len(x)
    sums=x.sum(axis=0,dtype=np.int64)
    disp=float(np.sum((sums-n*.25)**2)/(n*.25*.75))
    adjacent=float(np.mean(np.sum(x[:,:-1]*x[:,1:],axis=1,dtype=np.int32)))
    ix=lagidx[1]
    overlap=(x[ix]*x[ix-1]).sum(axis=1,dtype=np.int16)
    means={}
    for lag in (3,6,12,24,48):
        q=lagidx[lag]
        means[lag]=float(np.mean(np.sum(x[q]*x[q-lag],axis=1,dtype=np.int16)))
    # The max of many hour-of-day tests must be globally calibrated.
    hr=clock[ix]
    groups=[np.flatnonzero(hr==h) for h in range(24)]
    groups=[g for g in groups if len(g)>=150]
    clockmax=max(abs(float(overlap[g].mean())-5.) for g in groups)
    drift=np.cumsum(x.astype(np.float32)-.25,axis=0,dtype=np.float32)
    maxcusum=float(np.max(np.abs(drift))/math.sqrt(n))
    stats=dict(NUMBER_FREQUENCY_DISPERSION=disp,
      INTRA_DRAW_NEIGHBORS=adjacent,
      XOR_LAG1_MEAN=float(np.mean(40-2*overlap)),
      XOR_LAG1_VARIANCE=float(np.var(40-2*overlap)),
      LAG3_OVERLAP=means[3],LAG6_OVERLAP=means[6],
      LAG12_OVERLAP=means[12],LAG24_OVERLAP=means[24],
      LAG48_OVERLAP=means[48],
      LAG1_CLOCK_MAX_DEVIATION=clockmax,
      MAX_80BIT_CUSUM=maxcusum)
    assert set(stats)==set(METRIC_KEYS)
    return stats

def null_audit(x,idx,clock,reps):
    actual=raw_metrics(x,idx,clock)
    rng=np.random.default_rng(SEED)
    null=np.empty((reps,len(METRIC_KEYS)),dtype=np.float64)
    for rep in range(reps):
        sample=random_corpus(len(x),rng)
        q=raw_metrics(sample,idx,clock)
        null[rep]=[q[k] for k in METRIC_KEYS]
        if (rep+1)%50==0:
            print("V93 null 20/80",rep+1,"/",reps,flush=True)
    mu=null.mean(axis=0)
    sd=np.maximum(null.std(axis=0,ddof=1),1e-12)
    act=np.array([actual[k] for k in METRIC_KEYS],dtype=np.float64)
    distance=np.abs(act-mu)/sd
    null_dist=np.abs(null-mu[None,:])/sd[None,:]
    maxnull=np.max(null_dist,axis=1)
    maxact=float(distance.max())
    globalp=(1+int((maxnull>=maxact).sum()))/(reps+1)
    tests=[]
    for i,key in enumerate(METRIC_KEYS):
        p=(1+int((null_dist[:,i]>=distance[i]).sum()))/(reps+1)
        padj=(1+int((maxnull>=distance[i]).sum()))/(reps+1)
        tests.append(dict(feature=key,observed=float(act[i]),
          simulated_mean=float(mu[i]),
          simulated_sd=float(sd[i]),
          simulated_q025=float(np.quantile(null[:,i],.025)),
          simulated_q975=float(np.quantile(null[:,i],.975)),
          absolute_z_vs_null=float(distance[i]),
          monte_carlo_p=float(p),
          maxT_familywise_p=float(padj),
          pass_fwer_05=bool(padj<=.05)))
    return tests,globalp,int(reps),actual

def build_pattern(x,idx):
    a=x[idx-1].astype(np.uint8)
    b=x[idx-2].astype(np.uint8)
    c=x[idx-3].astype(np.uint8)
    return (4*a+2*b+c).astype(np.uint8)

def top10(scores):
    q=np.lexsort((np.arange(80),-np.asarray(scores,dtype=np.float64)))
    return tuple(sorted(int(v) for v in q[:10]))

def rng10(target_id):
    value=int.from_bytes(hashlib.blake2b(
        f"{SEED}|{target_id}".encode(),digest_size=8).digest(),"big")
    return tuple(sorted(random.Random(value).sample(range(80),10)))

def estimate_table(pattern,x,targets):
    """Train-only conditional P(next ball=1 | last3 bits); pseudocount
    strength 250 shrinks each pattern to train marginal. Train all
    80x8 bins independent of holdout labels."""
    xx=x[targets]
    pp=pattern[targets]
    num=np.zeros((8,80),dtype=np.float64)
    den=np.zeros((8,80),dtype=np.float64)
    for p in range(8):
        mask=(pp==p)
        den[p]=mask.sum(axis=0)
        num[p]=(mask*xx).sum(axis=0)
    baseline=(xx.sum(axis=0)+.25*250)/(len(targets)+250)
    table=(num+250*baseline[None,:])/(den+250)
    return table,baseline,den

def score_rules(rows,x,ids,lagidx,days):
    # 3 consecutive 5-min earlier real draws mandatory.
    valid=lagidx[3]
    stages={}
    for t in valid:
        day=rows[int(t)]["day"]
        if day<=days[35]:phase="TRAIN"
        elif day<=days[53]:phase="VALIDATE"
        else:phase="HOLDOUT"
        stages.setdefault(phase,[]).append(int(t))
    train=np.asarray(stages["TRAIN"],dtype=np.int32)
    val=stages["VALIDATE"];hold=stages["HOLDOUT"]
    # No model retraining on VAL or HOLD.
    patterns=np.zeros_like(x,dtype=np.uint8)
    patterns[valid]=build_pattern(x,valid)
    tab,base,den=estimate_table(patterns,x,train)
    # Marginal conditional versions shrink under same data.
    condlast=np.stack([
      (tab[0]+tab[1]+tab[2]+tab[3])/4,
      (tab[4]+tab[5]+tab[6]+tab[7])/4
    ])
    # Need expose counts per last-state instead of equally-weighted
    # table rows, avoiding biases from unequal 3-bit pattern prevalence.
    p_train=patterns[train]
    x_train=x[train]
    for bit in (0,1):
        mask=((p_train//4)==bit)
        expos=mask.sum(axis=0)
        condlast[bit]=((mask*x_train).sum(axis=0)+250*base)/(expos+250)
    parity=np.array([(int(p).bit_count()%2) for p in range(8)])
    condxor=np.zeros((2,80),dtype=np.float64)
    for bit in (0,1):
        mask=(parity[p_train]==bit)
        expos=mask.sum(axis=0)
        condxor[bit]=((mask*x_train).sum(axis=0)+250*base)/(expos+250)
    results=[]
    for phase,source in (("VALIDATE",val),("HOLDOUT",hold)):
        for t in source:
            p=patterns[t]
            tickets=dict(RANDOM10=rng10(rows[t]["id"]),
              TRAIN_FREQ10=top10(base),
              MARKOV_LAST=top10(condlast[(p//4),np.arange(80)]),
              XOR3_PARITY=top10(condxor[parity[p],np.arange(80)]),
              PATTERN3=top10(tab[p,np.arange(80)]))
            target=x[t]
            for method,chosen in tickets.items():
                hits=int(target[list(chosen)].sum())
                results.append(dict(stage=phase,day=rows[t]["day"],
                  target_draw_id=rows[t]["id"],target_clock=rows[t]["time"],
                  method=method,hits10=hits,
                  high7plus=int(hits>=7),
                  ten10=int(hits==10),
                  selected10="-".join(str(n+1) for n in chosen),
                  prior_id=rows[t-1]["id"],
                  latest3_pattern_sum=int(p.sum()),
                  real_20="-".join(map(str,rows[t]["nums"]))))
    summ=[]
    for phase in ("VALIDATE","HOLDOUT"):
        for meth in ALL_METHODS:
            q=[r for r in results if r["stage"]==phase and r["method"]==meth]
            n=len(q)
            summ.append(dict(stage=phase,method=meth,n=n,
               avg10=sum(r["hits10"] for r in q)/n,
               sum_hits=sum(r["hits10"] for r in q),
               high7plus=sum(r["high7plus"] for r in q),
               ten10=sum(r["ten10"] for r in q)))
    valstats={r["method"]:r for r in summ if r["stage"]=="VALIDATE"}
    best=max(CONDITIONAL_METHODS,
       key=lambda k:(valstats[k]["avg10"]-valstats["RANDOM10"]["avg10"],
                      -CONDITIONAL_METHODS.index(k)))
    holdstats={r["method"]:r for r in summ if r["stage"]=="HOLDOUT"}
    # Daily paired bootstrap of frozen winner - exactly same target IDs.
    rr={}
    for row in results:
        if row["stage"]=="HOLDOUT" and row["method"] in (best,"RANDOM10"):
            rr[(row["day"],row["target_draw_id"],row["method"])]=row["hits10"]
    paired=collections.defaultdict(list)
    for (day,tid,met),hits in rr.items():
        if met==best:
            key=(day,tid,"RANDOM10")
            if key in rr:paired[day].append(hits-rr[key])
    d=sorted(paired)
    diffs=np.array([np.sum(paired[x]) for x in d],dtype=np.float64)
    sizes=np.array([len(paired[x]) for x in d],dtype=np.float64)
    rand=np.random.default_rng(SEED+93)
    take=rand.integers(0,len(d),size=(5000,len(d)))
    boot=diffs[take].sum(axis=1)/sizes[take].sum(axis=1)
    ci=list(map(float,np.quantile(boot,[.025,.975])))
    gain=holdstats[best]["avg10"]-holdstats["RANDOM10"]["avg10"]
    return results,summ,dict(training_samples=len(train),
       validation_samples=len(val),holdout_samples=len(hold),
       train_last_day=days[35],val_last_day=days[53],
       winner_validation=best,validated_winner_avg10=valstats[best]["avg10"],
       validated_random_avg10=valstats["RANDOM10"]["avg10"],
       holdout_winner_avg10=holdstats[best]["avg10"],
       holdout_random_avg10=holdstats["RANDOM10"]["avg10"],
       holdout_diff=gain,day_bootstrap_95=ci,
       frequency_mean_train=base.tolist())

def hypergeom():
    den=math.comb(80,20)
    return [dict(overlap=k,xor_hamming_bits=40-2*k,
                 exact_p=math.comb(20,k)*math.comb(60,20-k)/den)
            for k in range(21)]

def csvwrite(z,name,items):
    if not items:return
    with z.open(name,"w",force_zip64=True) as f:
        tx=io.TextIOWrapper(f,encoding="utf-8",newline="")
        writer=csv.DictWriter(tx,fieldnames=list(items[0]))
        writer.writeheader();writer.writerows(items)
        tx.flush();tx.detach()

def run(path,output,reps):
    days,rows,x,ids,clock,idx,issues,bad=load(path)
    print(f"V93 full days={len(days)}, 80-bit constant-weight draws={len(x)}, consecutive pairs={len(idx[1])}",flush=True)
    simulations,pglobal,n,raw=null_audit(x,idx,clock,reps)
    results,summary,choice=score_rules(rows,x,ids,idx,days)
    signalcount=sum(q["pass_fwer_05"] for q in simulations)
    report=[
       "V93 — KRIPTOANALIZ STILI SABIT 20/80 CIKTI IZI / XOR TESTI",
       "80 output bits have Hamming weight EXACTLY 20; NOT independent 50/50 bits.",
       "Unlike internal RNG raw bits, these published numbers are a transformed",
       "unordered sample; cryptographic keys or hidden seed cannot be recovered",
       "from results without known algorithm and output mapping.",
       f"72 complete days; {len(rows)} validated draws; {len(idx[1])} genuine five-minute adjacent pairs.",
       f"{len(simulations)} preregistered signature metrics; {n} independent null corpora",
       "simulated with exactly 20 unique of 80 for every draw, same real schedule.",
       f"Global max-statistic Monte-Carlo p={pglobal:.6f}; familywise significant metrics={signalcount}.",
       "Each metric empirical two-sided deviation versus independent 20/80 and",
       "maxT familywise correction. This is NOT NIST 50/50 monobit p testing.",
       f"Observed lag1 XOR Hamming mean={raw['XOR_LAG1_MEAN']:.6f} bits;",
       "under independent 20/80 expected 30 (overlap=5).",
       "",
       "A. OUTPUT FINGERPRINT VS INDEPENDENT 20/80:",
    ]
    for q in simulations:
        report.append(f" {q['feature']:<31} observed={q['observed']:.6f},"
          f" null_mean={q['simulated_mean']:.6f},"
          f" raw_p={q['monte_carlo_p']:.4f},"
          f" corrected_p={q['maxT_familywise_p']:.4f}")
    report+=["",
      "B. XOR-LAST3 / 1st-ORDER TRANSITION — LOCKED 10-NUMBER NEXT DRAW:",
      f"Training {choice['training_samples']} target draws thru {choice['train_last_day']};",
      f"validation {choice['validation_samples']} target draws thru {choice['val_last_day']};",
      f"holdout {choice['holdout_samples']} future-labelled draws.",
      "All conditional counts/smoothing learned ONLY before validation.",
    ]
    for s in summary:
        report.append(f" {s['stage']} {s['method']:12} n={s['n']},"
              f" avg10={s['avg10']:.6f},7+={s['high7plus']},10/10={s['ten10']}")
    report+=["",
        f"VALIDATE chose {choice['winner_validation']}; no holdout re-selection.",
        f"HOLDOUT chosen mean={choice['holdout_winner_avg10']:.6f},"
        f" random10={choice['holdout_random_avg10']:.6f},"
        f" difference={choice['holdout_diff']:+.6f},"
        f" day-paired bootstrap 95%={choice['day_bootstrap_95']}.",
        "Adil RNG expectation 10-ball next draw = 2.500.",
        "The same historical period was mined in V9..V92; this holdout",
        "is chronological but NOT wholly untouched prospective evidence.",
        "MaxT null replicates only test 11 specified aggregate phenomena.",
        "Even a statistical bias could arise from logging errors, not a",
        "cryptographic weakness; independent reproducible confirmation needed.",
        "Reproducing a hidden CSPRNG or decrypting secret seed is NOT",
        "entailed by any of these statistical checks."
    ]
    out=Path(output);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=5) as z:
        z.writestr("00_V93_KRIPTOANALIZ_KISA_SONUC.txt","\n".join(report))
        csvwrite(z,"01_80BIT_XOR_FREKANS_DONGU_11_TEST_RNG_NULL.csv",simulations)
        csvwrite(z,"02_VAL_HOLDOUT_XOR3_10LU_ISABET_OZET.csv",summary)
        csvwrite(z,"03_TUM_KILITLI_TAHMINLER_HEDEF_GERCEK.csv",results)
        csvwrite(z,"04_20of80_XOR_HYPERGEOMETRIK_NULL.csv",hypergeom())
        z.writestr("05_ZAMAN_ESLESMESI_METOT.txt","\n".join([
           "Valid draws 20 unique from 80, 72 fully completed days.",
           "80-bit vector exactly 20 ones; naïve 50/50 monobit is invalid.",
           "XOR between consecutive observations must have even Hamming",
           "weight 0..40, and expected 30 if independent uniform 20-of-80.",
           "Null generator draws independent unbiased 20-subsets at each",
           "real timestamp; retains valid timing, missing gaps, actual IDs.",
           "499 or configurable Monte-Carlo null replications; maxT",
           "corrects multiplicity over predefined eleven metric tests.",
           "Chance of identical 20/80 tickets across 15,624 draws is tiny",
           "even under pure RNG; 20/20 unique draw claim is not evidence.",
           "Train first36 days, validate next18, holdout last18.",
           "Next target cannot influence XOR3 3-bit pattern or ticket.",
           "Seed unknown, draw algorithm unknown, source transform unknown.",
           "Statistical independence and cryptographic unpredictability",
           "are different properties. Dataset was explored before V93.",
        ]))
        z.writestr("06_AUDIT.json",json.dumps(dict(
          version=VERSION,n_days=len(days),n_draws=len(rows),
          first_day=days[0],last_day=days[-1],
          adjacent_5min=len(idx[1]),
          lag_pairs={str(k):len(v) for k,v in idx.items()},
          null_reps=n,metric_count=len(simulations),
          global_maxT_p=pglobal,significant_corrected=signalcount,
          metrics=simulations,trained_models=choice,
          issues=issues[:30],malformed=bad[:30]),
          ensure_ascii=False,indent=2))
    print("\n".join(report),flush=True)
    print("V93 SUCCESS "+str(out)+" bytes="+str(out.stat().st_size),flush=True)

def selftest():
    rng=np.random.default_rng(SEED)
    sample=random_corpus(360,rng)
    assert sample.shape==(360,80)
    assert np.all(sample.sum(axis=1)==20)
    assert abs(sum(q["exact_p"] for q in hypergeom())-1)<1e-10
    assert abs(sum(q["exact_p"]*q["xor_hamming_bits"] for q in hypergeom())-30)<1e-10
    a=np.array([[1.,0,0],[0,1.,0]])
    assert top10(np.arange(80))==tuple(range(70,80))
    print("V93 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v93_output/V93_72GUN_80BIT_XOR_KRIPTO_RNG_VE_KOR_TEST.zip")
    p.add_argument("--reps",type=int,default=NULL_REPS)
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest()
    else:run(args.source,args.out,args.reps)
