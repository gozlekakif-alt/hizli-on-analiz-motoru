#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V99B: hourly micro-behaviour transitions H1-H6, two preceding hours.

No family, no ticket. 72 complete days, valid three FULL consecutive-hour
triples only. A: current H1-H6. B,C: last three draws of preceding two hours.
Binary chronological masks are stored exactly: 000, 100, 010, ..., 111.
Before H4/H5/H6, train a strictly past-only per-number forecast model
under four predetermined feature families, validate chronologically,
and freeze only a winner better than unconditional 25%; otherwise ABSTAIN.
A retrospective holdout on well-studied dates is NOT prospective proof.
"""
from __future__ import annotations
import argparse,collections,csv,datetime,io,json,math,zipfile
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION = "V99B.1"
MODELS = ("COUNT_A", "EXACT_A", "COUNTS_A_B_C", "EXACT_A_B_C", "PREV_B_C")
SMOOTH = {"COUNT_A":40, "EXACT_A":70, "COUNTS_A_B_C":120,
          "EXACT_A_B_C":180, "PREV_B_C":120}
P0=.25
STEPS=(3,4,5)  # next draw H4,H5,H6 (0-index)
PHASE=("TRAIN","VALIDATE","HOLDOUT")
TOTAL_HOURS=1150

def bitstring(v,k):
    return "".join(str((v>>j)&1) for j in range(k))

def read_data(path):
    raw,issues,bad=parse_txt(path)
    good={d:r for d,r in raw.items() if len(r)==217 and
          [x["pos"] for x in r]==list(range(1,218))}
    days=sorted(good)
    if len(days)!=72 or days[0]!="2026-08-01" or days[-1]!="2026-10-12":
        raise AssertionError("Unexpected 72-day dataset "+str(len(days)))
    hours={}
    for day in days:
        buckets=collections.defaultdict(list)
        for draw in good[day]:
            hr,mi=map(int,draw["time"].split(":"))
            buckets[hr].append((mi,draw))
        for hr,pairs in buckets.items():
            pairs.sort()
            if len(pairs)!=12 or [x[0] for x in pairs]!=list(range(2,60,5)):
                continue
            key=datetime.datetime.fromisoformat(day+"T"+f"{hr:02d}:00:00")
            draws=[x[1] for x in pairs]
            binary=np.zeros((12,80),dtype=np.uint8)
            for i,draw in enumerate(draws):
                binary[i,np.asarray(draw["nums"],dtype=np.int16)-1]=1
            hours[key]=(day,draws,binary)
    triples=[]
    for stamp,(day,draws,A) in sorted(hours.items()):
        B=hours.get(stamp-datetime.timedelta(hours=1))
        C=hours.get(stamp-datetime.timedelta(hours=2))
        if not B or not C:continue
        b3=B[2][9:12];c3=C[2][9:12]
        # Build bits per number, preserving actual draw order.
        for n in range(80):
            a=tuple(int(v) for v in A[:6,n])
            b=tuple(int(v) for v in b3[:,n])
            c=tuple(int(v) for v in c3[:,n])
            triples.append((day,stamp.isoformat(),n+1,a,b,c))
    return days,len(hours),triples,issues,bad

def encoding(bits):
    return sum(v<<j for j,v in enumerate(bits))

def model_key(model,stage,a,b,c):
    aa=encoding(a[:stage]); bb=encoding(b);cc=encoding(c)
    k=sum(a[:stage])
    if model=="COUNT_A":return (stage,k)
    if model=="EXACT_A":return (stage,aa)
    if model=="COUNTS_A_B_C":return (stage,k,sum(b),sum(c))
    if model=="EXACT_A_B_C":return (stage,aa,bb,cc)
    if model=="PREV_B_C":return (stage,bb,cc)
    raise ValueError(model)

def table_rows(counter):
    return [{**dict(zip(fields,key)),**obj} for fields,key,obj in counter]

def analyze(days,triples):
    split={d:(0 if i<36 else 1 if i<54 else 2) for i,d in enumerate(days)}
    counts=collections.defaultdict(lambda:[0,0])
    # pattern from first three H1..H3, target exact subsequent three H4..H6
    full3=collections.defaultdict(lambda:[0,0])
    byk=collections.defaultdict(lambda:[0,0])
    exits=collections.defaultdict(lambda:[0,0])
    steps=collections.defaultdict(lambda:[0,0])
    pernum=collections.defaultdict(lambda:[0,0])
    micro9=collections.defaultdict(lambda:[0,0])
    # Preallocated model fit tables, trained only on first 36 days.
    training={m:collections.defaultdict(lambda:[0,0]) for m in MODELS}
    for day,hr,num,a,b,c in triples:
        phase=PHASE[split[day]]
        aa=encoding(a[:3]);bb=encoding(b);cc=encoding(c);z=encoding(a[3:6])
        full3[(phase,aa,z)][0]+=1
        full3[("ALL",aa,z)][0]+=1
        k=sum(a[:3]);l=sum(a[3:6])
        byk[("ALL",k,l)][0]+=1
        byk[(phase,k,l)][0]+=1
        # For 0/3, time to FIRST activation in H4/H5/H6, or none
        if k==0:
            first=next((j+4 for j,x in enumerate(a[3:6]) if x),0)
            exits[("ALL",first)][0]+=1
            exits[(phase,first)][0]+=1
        for s in STEPS:
            success=a[s];current=sum(a[:s]);bit=encoding(a[:s])
            steps[("ALL",s+1,current)][0]+=1;steps[("ALL",s+1,current)][1]+=success
            steps[(phase,s+1,current)][0]+=1;steps[(phase,s+1,current)][1]+=success
            pernum[(num,phase,s+1,current)][0]+=1
            pernum[(num,phase,s+1,current)][1]+=success
            micro9[(phase,aa,bb,cc,s+1)][0]+=1
            micro9[(phase,aa,bb,cc,s+1)][1]+=success
            if split[day]==0:
                for model in MODELS:
                    obs=training[model][model_key(model,s,a,b,c)]
                    obs[0]+=1;obs[1]+=success

    # Validation and holdout only (never select model on holdout)
    scores={}
    day_scores={}
    pred_samples={}
    for phase in ("VALIDATE","HOLDOUT"):
        rows=[r for r in triples if PHASE[split[r[0]]]==phase]
        daytot=collections.defaultdict(lambda:collections.defaultdict(lambda:[0.0,0]))
        sums={m:[0.,0,0.] for m in ("UNIFORM",)+MODELS}
        for day,hr,num,a,b,c in rows:
            for s in STEPS:
                y=a[s]
                for model in ("UNIFORM",)+MODELS:
                    if model=="UNIFORM":
                        p=P0
                    else:
                        n,w=training[model].get(model_key(model,s,a,b,c),(0,0))
                        lam=SMOOTH[model]
                        p=(w+lam*P0)/(n+lam)
                    loss=(y-p)**2
                    sums[model][0]+=loss
                    sums[model][1]+=-(y*math.log(p)+(1-y)*math.log1p(-p))
                    sums[model][2]+=1
                    daytot[(day,model)][s+1][0]+=loss
                    daytot[(day,model)][s+1][1]+=1
        for model,(bl,ll,n) in sums.items():
            scores[(phase,model)]=dict(phase=phase,model=model,
                examples=n,brier=bl/n,logloss=ll/n,
                brier_vs_uniform=(bl/n)-.1875)
        for (day,model),sc in daytot.items():
            for step,(sl,n) in sc.items():
                day_scores[(phase,day,model,step)]=sl/n
    eligible=[m for m in MODELS if scores[("VALIDATE",m)]["brier"]<
                               scores[("VALIDATE","UNIFORM")]["brier"]]
    best=min(eligible,key=lambda m:(scores[("VALIDATE",m)]["brier"],MODELS.index(m))) if eligible else "UNIFORM"
    # Day-paired CI against 25% reference on holdout using 18 calendar days.
    d=np.array([sum(day_scores[("HOLDOUT",day,best,s)]-
                    day_scores[("HOLDOUT",day,"UNIFORM",s)]
                    for s in (4,5,6))/3 for day in days[54:]],float)
    if len(d)>1:
        lo,hi=float(d.mean()-1.96*d.std(ddof=1)/np.sqrt(len(d))),float(
            d.mean()+1.96*d.std(ddof=1)/np.sqrt(len(d)))
    else:lo=hi=0
    patterns=[]
    for (phase,aa,z),(n,_) in sorted(full3.items()):
        k=z.bit_count()
        theoretical=(P0**k)*((1-P0)**(3-k))
        patterns.append(dict(phase=phase,first3=bitstring(aa,3),
            next3=bitstring(z,3),first3_hits=aa.bit_count(),
            next3_hits=k,observed=n,expected_given_first3=round(
                theoretical*sum(full3[(phase,aa,j)][0] for j in range(8)),4)))
    transitions=[]
    for (phase,k,l),(n,_) in sorted(byk.items()):
        total=sum(byk[(phase,k,u)][0] for u in range(4))
        prob=math.comb(3,l)*P0**l*(1-P0)**(3-l)
        transitions.append(dict(phase=phase,first3_count=k,next3_count=l,
            occurrences=n,first3_total=total,observed_percent=round(n/total*100,5),
            fair_expected_percent=round(prob*100,5)))
    stepout=[]
    for (phase,stage,current),(n,w) in sorted(steps.items()):
        stepout.append(dict(phase=phase,next_draw=stage,seen_before=current,
            out_of_previous=stage-1,n=n,success=w,observed_percent=round(100*w/n,5),
            fair_expected_percent=25))
    activations=[]
    for (phase,first),(n,_) in sorted(exits.items()):
        tot=sum(exits[(phase,k)][0] for k in (0,4,5,6))
        fair={0:(.75**3),4:.25,5:.75*.25,6:(.75**2)*.25}[first]
        activations.append(dict(phase=phase,first_appearance_at=first or "NONE",
            count=n,from_0_of_3=tot,pct=round(n/tot*100,5),
            fair_expected_pct=round(fair*100,5)))
    micro=[]
    for (phase,aa,bb,cc,stage),(n,w) in sorted(micro9.items()):
        micro.append(dict(phase=phase,C_last3=bitstring(cc,3),
           B_last3=bitstring(bb,3),A_first3=bitstring(aa,3),
           next_draw=stage,count=n,hits=w,observed_pct=round(100*w/n,5)))
    number=[]
    for (num,phase,stage,k),(n,w) in sorted(pernum.items()):
        number.append(dict(number=num,phase=phase,next_draw=stage,
            number_seen_previous_draws=k,observations=n,hits=w,
            observed_pct=round(100*w/n,5)))
    scoreout=[{**z,"brier":round(z["brier"],9),"logloss":round(z["logloss"],9),
        "brier_vs_uniform":round(z["brier_vs_uniform"],9)}
        for _,z in sorted(scores.items())]
    metadata=dict(version=VERSION,days=len(days),full_hours=1296,
        target_hour_triples=len(triples)//80,samples=len(triples),
        stages=(4,5,6),models=list(MODELS),winner=best,
        validation_winner_criteria="positive gain vs uniform Brier",
        holdout_day_mean_delta=float(d.mean()),holdout_ci95=[lo,hi],
        independent_days_in_holdout=18,phase_boundaries=[36,54,72],
        theoretical_next_draw_prob=0.25,
        unique_9bit_A_B_C_patterns=len(set((r[0],r[1],r[2]) for r in
                                            ((encoding(a[:3]),encoding(b),
                                              encoding(c)) for _,_,_,a,b,c in triples))),
        warning="Historical data extensively reused. No genuine fresh prospective proof.",
        do_not_deploy=best=="UNIFORM" or lo<=0<=hi)
    return metadata,patterns,transitions,stepout,activations,micro,number,scoreout

def csvzip(z,name,records):
    if not records:return
    with z.open(name,"w",force_zip64=True) as raw:
        f=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        wr=csv.DictWriter(f,fieldnames=list(records[0]))
        wr.writeheader()
        wr.writerows(records)
        f.flush();f.detach()

def run(source,out):
    days,hours,triples,issues,bad=read_data(source)
    meta,pats,trans,stp,act,micro,number,scores=analyze(days,triples)
    assert hours==1296 and len(triples)==92000
    meta.update(source_issues=issues[:20],malformed_line_numbers=bad[:20])
    allstep=[x for x in stp if x["phase"]=="ALL"]
    table=[x for x in trans if x["phase"]=="ALL"]
    results=["V99B - MIKROKRIPTO H1-H6: GEÇMIŞ IKI SAAT VE DAVRANIS YOLLARI",
       "72 full days | 1296 full hours | 1150 fully consecutive three-hour windows",
       "92000 ball-hour trajectories, 276000 observed H4/H5/H6 next-ball checks.",
       "A=now H1/H2/H3; B,C=last H10/H11/H12 of each previous two hours.",
       "First three and next three have 8 chronological patterns each (8x8).",
       "No family or ticket used. Only past observations are allowed in features.",
       "",
       "FIRST THREE -> NEXT THREE transition frequencies:"]
    for k in range(4):
        rows=[v for v in table if v["first3_count"]==k]
        results.append(f" {k}/3: "+", ".join(f"{v['next3_count']}/3={v['observed_percent']:.3f}%"
          for v in rows))
    results+=["","SEQUENTIAL STATE -> PROBABILITY OF ACTIVATION:",
       "States are count seen through H3, H4, or H5; next draw H4-H6."]
    for s in (4,5,6):
        results.append(f" H{s}: "+", ".join(
            f"{v['seen_before']}/{s-1}={v['observed_percent']:.3f}% (n={v['n']})"
            for v in allstep if v["next_draw"]==s))
    results+=["","H4-H6 unseen since start (0/3) FIRST activation:"]
    for a in act:
        if a["phase"]=="ALL":
            results.append(f" {a['first_appearance_at']}: n={a['count']} "
              f"({a['pct']:.3f}%, fair={a['fair_expected_pct']:.3f}%)")
    results+=["","CHRONOLOGICAL VALIDATION AND FROZEN HOLDOUT: Brier lower is better.",
              "UNIFORM reference Brier = 0.1875; gain negative means improvement."]
    for phase in ("VALIDATE","HOLDOUT"):
        results.append(" "+phase)
        for s in scores:
            if s["phase"]==phase:
                results.append("  "+s["model"]+": "+f"{s['brier']:.9f} "
                             +f"delta={s['brier_vs_uniform']:+.9f}")
    results+=["",f"Selected ONLY using validation: {meta['winner']}.",
         f"Holdout day-mean difference vs uniform: {meta['holdout_day_mean_delta']:+.9f}",
         f"Approximate 95% CI (18 day blocks): [{meta['holdout_ci95'][0]:+.8f}, {meta['holdout_ci95'][1]:+.8f}]",
         "Signal status: "+("NOT CONFIRMED / do not deploy" if meta["do_not_deploy"]
                          else "candidate only; independent prospective trial required"),
         "Do not equate rare 8x8 transitions with future predictive information.",
         "All numbers are sampled simultaneously without replacement each draw;",
         "day-block uncertainty is preferable to pretending ball observations independent.",
         "These 72 days have been researched in V9-V99; holdout not truly untouched.",
         "Next: analyze H7-H12 ONLY if H4-H6 learns a reproducible signal."]
    from pathlib import Path
    dst=Path(out);dst.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dst,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as z:
        z.writestr("00_SONUC_V99B.txt","\n".join(results)+"\n")
        csvzip(z,"01_TAM_8x8_ILK3_SON3_BIT_DIZILIMLERI.csv",pats)
        csvzip(z,"02_ILK3_SON3_DORT_KADEME_GECISLER.csv",trans)
        csvzip(z,"03_H4_H5_H6_TUM_GECIS_DURUMLARI.csv",stp)
        csvzip(z,"04_0_3_SAYILAR_ILK_NE_ZAMAN_UYANDI.csv",act)
        csvzip(z,"05_GECMIS_2_SAAT_9_BIT_505_KOD.csv",micro)
        csvzip(z,"06_80_SAYI_KIMLIGININ_MIKRO_GECISLERI.csv",number)
        csvzip(z,"07_5_MODEL_DOGRULAMA_KOR_TEST.csv",scores)
        z.writestr("08_YONTEM_DENETIM.json",json.dumps(meta,indent=2,
            ensure_ascii=False,default=str))
    print("\n".join(results),flush=True)
    print("V99B DONE",str(dst),dst.stat().st_size,flush=True)

def selftest():
    assert bitstring(encoding((1,0,1)),3)=="101"
    assert model_key("EXACT_A",3,(1,0,1),(0,0,1),(1,0,0))==(3,5)
    assert abs(sum(math.comb(3,k)*(.25**k)*(.75**(3-k)) for k in range(4))-1)<1e-12
    print("SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v99b_output/V99B_SAATLIK_MIKRO_DNA_4_5_6_GECIS.zip")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:selftest()
    else:run(a.source,a.out)
