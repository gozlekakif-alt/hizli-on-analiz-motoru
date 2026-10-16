#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V94 — one quarter (20/80) cryptanalysis-inspired 4-lane / 4-bit model.

Every draw consists of 20 ones + 60 zeros in an 80-bit vector. Two
prespecified partitions: four contiguous blocks of twenty (CHUNK) and
four interlaced groups n mod 4 (MOD4), also twenty each. EACH group
has 5 expected draws PER ONE result, not exactly 5.
A FOUR-DRAW bit nibble (16 states) and XOR-parity conditioned on true
source-only prior 4 draws are tested for one future target draw.

A. Fixed quarterly diagnostics vs 399 independent null 20-of-80 corpora,
   using real calendar/gap positions and corrected max-statistic p.
B. Model train first 36 full days, validate next18, report last18:
   matched random 10, source frequency 10, V93 3bit, V94 4bit,
   4bit XOR parity and two chunk/mod4 'quarter quota' strategies;
   choose on validation ONLY. Any difference remains retrospective.
No claim about hidden RNG algorithm, secret key, exact seed or hacks.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,io,json,math,random,zipfile
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V94.1"
SEED=941016
REPS=399
PAT_STRENGTH=250.
LAGS=(1,3,4)
METHODS=("RANDOM10","TRAIN_FREQ10","V93_PAT3",
         "V94_NIBBLE4","V94_XOR4","V94_Q4_CHUNK","V94_Q4_MOD4")
GROUPS={"CHUNK":np.repeat(np.arange(4),20),
        "MOD4":np.arange(80)%4}
METRICS=("CHUNK_Q_VAR","MOD4_Q_VAR",
         "CHUNK_Q_LAG1","MOD4_Q_LAG1",
         "CHUNK_Q_LAG4","MOD4_Q_LAG4",
         "XOR4_HAMMING_MEAN","XOR4_HAMMING_VAR",
         "CHUNK_XOR4_GROUP_VAR","MOD4_XOR4_GROUP_VAR")

def seed64(*items):
    z="|".join(map(str,items)).encode()
    return int.from_bytes(hashlib.blake2b(z,digest_size=8).digest(),"big")

def load(path):
    byday,issues,bad=parse_txt(path)
    full={d:x for d,x in byday.items() if len(x)==217 and
          [r["pos"] for r in x]==list(range(1,218))}
    days=sorted(full)
    if len(days)!=72 or days[0]!="2026-08-01" or days[-1]!="2026-10-12":
        raise RuntimeError(f"72 complete days expected, got {len(days)}")
    rows=[r for d in days for r in full[d]]
    x=np.zeros((len(rows),80),np.uint8)
    for i,r in enumerate(rows):
        x[i,np.asarray(r["nums"],dtype=int)-1]=1
    assert np.all(x.sum(axis=1)==20)
    ids=np.asarray([r["id"] for r in rows],np.int64)
    tm=np.asarray([np.datetime64(r["day"]+"T"+r["time"])
                   for r in rows],dtype="datetime64[m]")
    ix={}
    for lag in LAGS:
        mask=(ids[lag:]-ids[:-lag]==lag)&(
             (tm[lag:]-tm[:-lag])/np.timedelta64(1,"m")==lag*5)
        ix[lag]=np.flatnonzero(mask)+lag
    return days,rows,x,ix,issues,bad

def synthetic(n,rng):
    priorities=rng.random((n,80),dtype=np.float32)
    pos=np.argpartition(priorities,20,axis=1)[:,:20]
    a=np.zeros((n,80),dtype=np.uint8)
    a[np.arange(n)[:,None],pos]=1
    return a

def quarter_counts(x,part):
    return np.stack([x[:,part==k].sum(axis=1,dtype=np.int16)
                     for k in range(4)],axis=1).astype(np.float64)

def xor4(x,idx):
    return (x[idx]^x[idx-1]^x[idx-2]^x[idx-3])

def signature(x,idx):
    out={}
    for kind,part in GROUPS.items():
        q=quarter_counts(x,part)
        out[kind+"_Q_VAR"]=float(np.mean((q-5)**2))
        for lag in (1,4):
            it=idx[lag]
            out[kind+f"_Q_LAG{lag}"]=float(
                np.mean((q[it]-5)*(q[it-lag]-5)))
    parity=xor4(x,idx[3]).astype(np.float64)
    sizes=parity.sum(axis=1)
    out["XOR4_HAMMING_MEAN"]=float(sizes.mean())
    out["XOR4_HAMMING_VAR"]=float(sizes.var())
    for kind,part in GROUPS.items():
        q=quarter_counts(parity,part)
        out[kind+"_XOR4_GROUP_VAR"]=float(np.mean((q-q.mean(axis=1,keepdims=True))**2))
    assert set(out)==set(METRICS)
    return out

def benchmark_null(x,idx,reps):
    observed=signature(x,idx)
    gen=np.random.default_rng(SEED)
    z=np.zeros((reps,len(METRICS)),np.float64)
    for k in range(reps):
        sample=synthetic(len(x),gen)
        got=signature(sample,idx)
        z[k,:]=[got[m] for m in METRICS]
        if (k+1)%60==0:print("V94 exact20of80 null",k+1,"/",reps,flush=True)
    mu=z.mean(axis=0)
    sd=np.maximum(z.std(axis=0,ddof=1),1e-12)
    act=np.array([observed[m] for m in METRICS])
    stat=np.abs(act-mu)/sd
    simulated=np.abs(z-mu)/sd
    maximum=simulated.max(axis=1)
    globalp=(1+np.count_nonzero(maximum>=stat.max()))/(reps+1)
    tests=[]
    for j,key in enumerate(METRICS):
        tests.append(dict(metric=key,real=round(float(act[j]),7),
          rng_null_mean=round(float(mu[j]),7),
          rng_null_std=round(float(sd[j]),7),
          rng_null_q025=round(float(np.quantile(z[:,j],.025)),7),
          rng_null_q975=round(float(np.quantile(z[:,j],.975)),7),
          raw_montecarlo_p=round(float((1+np.count_nonzero(simulated[:,j]>=stat[j]))/(reps+1)),7),
          corrected_maxT_p=round(float((1+np.count_nonzero(maximum>=stat[j]))/(reps+1)),7)))
    return tests,float(globalp)

def nibble_pattern(x,valid,number_of_lags):
    out=np.zeros_like(x,np.uint8)
    for i in range(number_of_lags):
        out[valid]+=(1<<(number_of_lags-i-1))*x[valid-i-1]
    return out

def likelihood_table(pattern,x,train,n_states,prior_strength=PAT_STRENGTH):
    p=pattern[train];t=x[train]
    marginal=(t.sum(axis=0,dtype=np.float64)+250*.25)/(len(train)+250)
    estimate=np.empty((n_states,80),dtype=np.float64)
    for state in range(n_states):
        mask=(p==state)
        numerator=np.sum(mask*t,axis=0)
        denominator=mask.sum(axis=0)
        estimate[state]=(numerator+prior_strength*marginal)/(denominator+prior_strength)
    return estimate,marginal

def parity_table(p,x,train,marginal):
    xor=np.array([int(state).bit_count()%2 for state in range(16)],np.uint8)
    px=x[train];s=xor[p[train]]
    result=np.empty((2,80),np.float64)
    for k in (0,1):
        m=s==k
        result[k]=(np.sum(m*px,axis=0)+250*marginal)/(m.sum(axis=0)+250)
    return result,xor

def quart_fit(x,targets,part):
    """Train 4 groups' next-count residual from previous four
    groups, fitted with ONE shared ridge coefficient, never future."""
    n=np.asarray(targets)
    src=np.mean([quarter_counts(x[n-l],part) for l in (1,2,3,4)],axis=0)
    target=quarter_counts(x[n],part)
    mean=target.mean(axis=0)
    xx=src-5
    yy=target-mean
    beta=float((xx*yy).sum()/((xx*xx).sum()+10000))
    return mean,beta

def quota10(q):
    # Expected target group balls q sum exactly 20 by normalization.
    q=np.clip(np.asarray(q,dtype=float),.01,20)
    q=q*20/q.sum()
    ideal=q/2.
    counts=np.floor(ideal).astype(int)
    residual=10-int(counts.sum())
    if residual<0:
        for k in np.lexsort((np.arange(4),ideal-counts))[:(-residual)]:
            counts[k]-=1
    elif residual:
        for k in np.lexsort((np.arange(4),-(ideal-counts)))[:residual]:
            counts[k]+=1
    if counts.sum()!=10 or min(counts)<0:raise AssertionError("invalid 10 quart quota")
    return counts

def quota_pick(scores,part,quota):
    picked=[]
    for k in range(4):
        group=np.flatnonzero(part==k)
        positions=np.lexsort((group,-scores[group]))[:quota[k]]
        picked.extend(int(group[v]) for v in positions)
    if len(picked)!=10 or len(set(picked))!=10:
        raise AssertionError("not ten distinct quota picks")
    return tuple(sorted(picked))

def top10(scores):
    return tuple(sorted(np.lexsort((np.arange(80),-np.asarray(scores)))[:10].tolist()))

def tickets(t,rows,x,pat3,pat4,tab3,tab4,xor4table,xor4map,marginal,quad):
    p3=pat3[t];p4=pat4[t]
    base4=tab4[p4,np.arange(80)]
    xorprob=xor4table[xor4map[p4],np.arange(80)]
    d={"RANDOM10":tuple(sorted(random.Random(seed64(SEED,rows[t]["id"])).sample(range(80),10))),
       "TRAIN_FREQ10":top10(marginal),
       "V93_PAT3":top10(tab3[p3,np.arange(80)]),
       "V94_NIBBLE4":top10(base4),
       "V94_XOR4":top10(xorprob)}
    for kind,part in GROUPS.items():
        q0,beta=quad[kind]
        src=np.mean([quarter_counts(x[[t-l]],part)[0] for l in (1,2,3,4)],axis=0)
        forecast=np.clip(q0+beta*(src-5),.01,20)
        quotas=quota10(forecast)
        d["V94_Q4_"+kind]=quota_pick(base4,part,quotas)
    assert set(d)==set(METHODS)
    return d

def confidence_day(rows,winner,rounds=3000):
    paired=collections.defaultdict(list)
    for r in rows:
        if r["stage"]=="HOLDOUT" and r["method"]==winner:
            paired[(r["day"],r["target_id"])]=[r["hits10"],None]
    for r in rows:
        if r["stage"]=="HOLDOUT" and r["method"]=="RANDOM10":
            z=paired.get((r["day"],r["target_id"]))
            if z is not None:z[1]=r["hits10"]
    daytot=collections.defaultdict(lambda:[0,0])
    for (day,tid),hits in paired.items():
        if hits[1] is None:raise AssertionError("missing matched random")
        daytot[day][0]+=hits[0]-hits[1]
        daytot[day][1]+=1
    d=np.asarray([daytot[k] for k in sorted(daytot)],dtype=np.float64)
    rng=np.random.default_rng(SEED+40)
    subs=rng.integers(0,len(d),size=(rounds,len(d)))
    z=d[subs].sum(axis=1)
    gains=z[:,0]/z[:,1]
    return [round(float(v),7) for v in np.quantile(gains,[.025,.975])]

def backtest(rows,x,idx,days):
    targets=np.asarray(idx[4],int)
    train=targets[np.asarray([rows[t]["day"]<=days[35] for t in targets])]
    val=targets[np.asarray([days[35]<rows[t]["day"]<=days[53] for t in targets])]
    hold=targets[np.asarray([rows[t]["day"]>days[53] for t in targets])]
    if min(map(len,(train,val,hold)))<2000:raise RuntimeError("not enough samples")
    # Only contiguous 5min span carries predecessor bits, no night crossover.
    pt3=nibble_pattern(x,targets,3)
    pt4=nibble_pattern(x,targets,4)
    tbl3,marg=likelihood_table(pt3,x,train,8)
    tbl4,marg4=likelihood_table(pt4,x,train,16)
    parity,xorlist=parity_table(pt4,x,train,marg4)
    quad={kind:quart_fit(x,train,part) for kind,part in GROUPS.items()}
    output=[]
    for stage,tt in (("VALIDATE",val),("HOLDOUT",hold)):
        for t in tt:
            coupons=tickets(t,rows,x,pt3,pt4,tbl3,tbl4,parity,xorlist,marg4,quad)
            for meth,chosen in coupons.items():
                hit=int(x[t,list(chosen)].sum())
                output.append(dict(stage=stage,day=rows[t]["day"],
                    target_id=rows[t]["id"],target_time=rows[t]["time"],
                    source_last_id=rows[t-1]["id"],
                    method=meth,hits10=hit,
                    seven_plus=int(hit>=7),ten_of_ten=int(hit==10),
                    chosen10="-".join(str(i+1) for i in chosen),
                    observed20="-".join(map(str,rows[t]["nums"]))))
        print("V94 complete",stage,len(tt),"targets",flush=True)
    score=[]
    for stage in ("VALIDATE","HOLDOUT"):
        for meth in METHODS:
            s=[r for r in output if r["stage"]==stage and r["method"]==meth]
            score.append(dict(stage=stage,method=meth,targets=len(s),
                avg10=round(sum(r["hits10"] for r in s)/len(s),7),
                seven_plus=sum(r["seven_plus"] for r in s),
                ten_of_ten=sum(r["ten_of_ten"] for r in s)))
    mval={r["method"]:r for r in score if r["stage"]=="VALIDATE"}
    mhold={r["method"]:r for r in score if r["stage"]=="HOLDOUT"}
    winner=max(METHODS[1:],key=lambda k:(
        mval[k]["avg10"]-mval["RANDOM10"]["avg10"],-METHODS.index(k)))
    ci=confidence_day(output,winner)
    return output,score,dict(train=len(train),validate=len(val),holdout=len(hold),
      train_last_day=days[35],validation_last_day=days[53],
      validation_frozen_winner=winner,
      validation_mean=mval[winner]["avg10"],
      holdout_mean=mhold[winner]["avg10"],
      holdout_random_mean=mhold["RANDOM10"]["avg10"],
      delta=round(mhold[winner]["avg10"]-mhold["RANDOM10"]["avg10"],7),
      day_bootstrap95=ci,
      q_group_training={k:dict(quart_mean=a.tolist(),beta=b)
                        for k,(a,b) in quad.items()})

def count_distribution(x):
    rows=[]
    for kind,part in GROUPS.items():
        counts=quarter_counts(x,part)
        for g in range(4):
            ss=counts[:,g].astype(int)
            for number in range(21):
                observed=int((ss==number).sum())
                expected=len(ss)*math.comb(20,number)*math.comb(60,20-number)/math.comb(80,20)
                rows.append(dict(partition=kind,group=g+1,
                 interval=(f"{g*20+1}-{g*20+20}" if kind=="CHUNK" else
                    "n_mod_4="+str(g)),number_in_draw=number,
                 actual_count=observed,theory_count=round(expected,7),
                 actual_share=round(observed/len(ss),7)))
    return rows

def writerows(z,path,items):
    if not items:return
    with z.open(path,"w",force_zip64=True) as f:
        out=io.TextIOWrapper(f,encoding="utf-8",newline="")
        w=csv.DictWriter(out,fieldnames=list(items[0]))
        w.writeheader();w.writerows(items);out.flush();out.detach()

def run(path,dest,reps):
    days,rows,x,idx,issues,bad=load(path)
    print("V94 quarter cryptanalysis days",len(days),"draws",len(x),
          "lag4 contiguous",len(idx[4]),flush=True)
    audit,globalp=benchmark_null(x,idx,reps)
    tickets_csv,models,selection=backtest(rows,x,idx,days)
    selected=selection["validation_frozen_winner"]
    report=[
      "V94 — 4'TE 1 KRIPTO MODELI: 20/80, 4x20 GRUP, 4 BITLIK GECMIS",
      f"Known real draws={len(x)}, days={len(days)},"
      f" exact consecutive lag4 possible targets={len(idx[4])}.",
      "Every draw 80bits with EXACTLY 20 ones and 60 zeroes (25% ones).",
      "4 contiguous groups of20 and four interlaced residue groups of20.",
      "Any group expected 5 / draw, but NOT exactly five. Four groups sum20.",
      "Last four source drawings -> per-number 4-bit nibble 0..15.",
      "XOR parity of same four source bits; neither is secret key/seed.",
      f"{reps} independent synthetic corpora with 20 unique balls of80",
      f"at every draw; {len(METRICS)} fixed quarter/XOR diagnostic metrics.",
      f"FAMILYWISE global maxT RNG difference p={globalp:.6f}.",
      "BAND AND XOR DIAGNOSTICS versus fair 20/80:",
    ]
    for z in audit:
        report.append(f"  {z['metric']}: real={z['real']},"
            f" null={z['rng_null_mean']}, p_raw={z['raw_montecarlo_p']},"
            f" p_corrected={z['corrected_maxT_p']}")
    report+=["",
      "FIXED next-draw 10 number prediction. TRAIN first36,"
      " VAL next18, HOLD last18:",
      f" TRAIN examples={selection['train']}, validation={selection['validate']},"
      f" holdout={selection['holdout']}.",
    ]
    for z in models:
        report.append(f"  {z['stage']:8} {z['method']:17} n={z['targets']},"
            f" mean10={z['avg10']:.6f}, 7+={z['seven_plus']},"
            f" 10/10={z['ten_of_ten']}")
    report+=["",
      f"VALIDATE frozen winner: {selected}; "
       f"validation mean10={selection['validation_mean']:.6f}.",
      f"HOLDOUT: same frozen {selected} mean10={selection['holdout_mean']:.6f}"
       f" vs matched random10={selection['holdout_random_mean']:.6f},"
       f" delta={selection['delta']:+.6f}, "
       f"day bootstrap95={selection['day_bootstrap95']}.",
      "Fair independent 20/80 expected coupon10 hits per draw=2.5.",
      "Even if the 4-fold code appears predictive, holdout calendar",
      "is historical and was previously inspected in other V projects.",
      "4 quarter constraint is selection geometry, not known crypto-key.",
      "Cannot infer whether source used physical RNG, CSPRNG or seed-time.",
      "Independent new sealed predictions required before any advantage claim."
    ]
    out=Path(dest);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_V94_4TE1_KRIPTO_OZET_VE_KARAR.txt","\n".join(report))
        writerows(z,"01_4x20_BIT_XOR_10_ISTATISTIK_RNG_NULL_KONTROL.csv",audit)
        writerows(z,"02_VAL_HOLD_7_YONTEM_10LU_ORNEK_KARSI.csv",models)
        writerows(z,"03_BUTUN_ONCEDEN_SECILI_10LULAR_VE_GERCEK_ISABET.csv",tickets_csv)
        writerows(z,"04_DORT_CEYREK_0_20_GORUNUM_HIPERGEOMETRIK.csv",count_distribution(x))
        z.writestr("05_KURALLAR_VE_ZAMAN_DISIPLINI.txt","\n".join([
         "Exactly20 of80, single ball marginal 25%; no PRNG internals exposed.",
         "Two prespecified 4 partitions: chunk20 and residue modulo4.",
         "Per group occupancy hypergeometric 20of80 sample20.",
         "Four 5-minute consecutive previous drawings only; t-4..t-1.",
         "Next target t NEVER used in bit nibble, XOR parity or quota.",
         "NIBBLE4 16 classes per number, train-only smoothed conditional.",
         "Quarter quota10 = normalize TRAIN-fitted expected4 groups",
         "to expected20 and use largest remainder to allocate ten picks.",
         "XOR4 parity conditional likelihood learned on TRAIN only.",
         "Train first36 complete days, val next18, holdout last18.",
         "Select ONE method on validation and freeze final holdout scores.",
         "Familywise corrected 10 diagnostic tests with simulated fair",
         "20-of-80 corpora preserving real gaps/times and draw totals.",
         "Historically mined holdout NOT independent prospective proof.",
         "Cannot claim decryption/seed recovery from published results."
        ]))
        z.writestr("06_AUDIT.json",json.dumps(dict(
          version=VERSION,days=len(days),draws=len(x),
          lag4_possible=len(idx[4]),global_maxT_p=globalp,
          number_of_null_corpora=reps,diagnostics=audit,
          model_scores=models,selected=selection,
          bad_lines=bad[:30],issues=issues[:30]),
          ensure_ascii=False,indent=2))
    print("\n".join(report),flush=True)
    print("V94 ZIP",out,out.stat().st_size,flush=True)

def selftest():
    assert all(len(part)==80 and all(np.count_nonzero(part==g)==20
           for g in range(4)) for part in GROUPS.values())
    a=synthetic(24,np.random.default_rng(2026))
    assert np.all(a.sum(axis=1)==20)
    q=quarter_counts(a,GROUPS["CHUNK"])
    assert np.all(q.sum(axis=1)==20)
    v=quota10(np.array([5.,5.,5.,5.]))
    assert sum(v)==10 and np.all(v>=2)
    assert len(quota_pick(np.arange(80),GROUPS["CHUNK"],v))==10
    assert len(top10(np.arange(80)))==10
    print("V94 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v94_output/V94_4TE1_KRIPTO_20_80_4BIT_MODELI.zip")
    p.add_argument("--reps",default=REPS,type=int)
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:selftest()
    else:run(a.source,a.out,a.reps)
