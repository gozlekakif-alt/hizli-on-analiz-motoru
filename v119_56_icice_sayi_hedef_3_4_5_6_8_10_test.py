#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V119: NO FAMILIES. 56 nested cumulative windows 12,24,...672.

Predict every next DRAW using strictly earlier 1/0 frequency history,
80 numbers five relative 16-member pools. Compare frozen models at
one ticket per method per draw, budgets 3,4,5,6,8,10.

This is historical exploratory replay, not prospective blind evidence.
"""
from __future__ import annotations
import argparse, collections, csv, io, json, random, zipfile, math
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load

WINDOWS=np.arange(12,673,12,dtype=np.int32)
assert len(WINDOWS)==56 and WINDOWS[0]==12 and WINDOWS[-1]==672
TICKETS=(3,4,5,6,8,10)
MODELS=("NEST_CONTRAST","NEST_REVERSAL","NEST_01_BURST",
        "HOT12","HOT72","HOT672","RANDOM")
PRIMARY="NEST_CONTRAST"
SEED=1192026

def csvwrite(z,filename,rows):
    if not rows:return
    with z.open(filename,"w",force_zip64=True) as f:
        wtr=io.TextIOWrapper(f,encoding="utf-8-sig",newline="")
        w=csv.DictWriter(wtr,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
        wtr.flush();wtr.detach()

def frozen_scores(P,t):
    assert t>=672
    counts=P[t][None,:]-P[t-WINDOWS]
    assert counts.shape==(56,80)
    assert counts[-1].sum()==13440
    order=np.argsort(counts,axis=1,kind="stable")
    state=np.empty((56,80),dtype=np.int8)
    state[np.arange(56)[:,None],order]=np.repeat(np.arange(5,dtype=np.int8),16)
    shortpool=state[:6].mean(axis=0)
    longpool=state[-6:].mean(axis=0)
    # Feature scales frozen BEFORE evaluation; only historic counts + classes.
    contrast=shortpool-longpool
    r12=counts[0].astype(float)
    r72=counts[5].astype(float)
    r672=counts[-1].astype(float)
    eps=(80-np.arange(80))*1e-7
    burst=r12-(r72-r12)/5.
    scores={
        PRIMARY:contrast*100 +r72/100.+eps,
        "NEST_REVERSAL":-contrast*100 +r72/100.+eps,
        "NEST_01_BURST":burst*100 +r72/100.+eps,
        "HOT12":r12+eps,
        "HOT72":r72+eps,
        "HOT672":r672+eps,
    }
    return scores,counts,state

def main(src,out):
    dates,rows,X,issues,bad=load(src)
    n=len(X)
    assert n==len(rows) and n>672
    P=np.vstack((np.zeros((1,80),dtype=np.int32),
                 np.cumsum(X,axis=0,dtype=np.int32)))
    valid_days=sorted([d for d in dates if d<="2026-10-12"])
    assert len(valid_days)==72
    phase_day={}
    for i,day in enumerate(valid_days):
        phase_day[day]=("TRAIN36" if i<36 else "VALIDATE18" if i<54 else "LAST18")
    zrows=[]
    stats=collections.defaultdict(lambda:[0,0,0,0,0,0,0,0,0,0,0])
    dayhits=collections.defaultdict(list)
    final_profile=[]
    counts_by_phase=collections.Counter()
    # t is target draw index. P[t] includes ONLY observations 0..t-1.
    for t in range(672,n):
        date=rows[t]["day"]
        phase=phase_day.get(date,"EXTRA_AFTER_OCT12")
        score,cnt,pool=frozen_scores(P,t)
        actual=X[t]
        rand=random.Random(SEED+t*9176).sample(range(80),10)
        picks={key:np.lexsort((np.arange(80),-val))[:10].tolist()
               for key,val in score.items()}
        picks["RANDOM"]=rand
        counts_by_phase[phase]+=1
        if t==n-1:
            for b in range(80):
                chain="".join(str(int(p)) for p in pool[:,b])
                dif=np.diff(pool[:,b])
                final_profile.append(dict(number=b+1,
                    before_target_id=rows[t]["id"],
                    bits_prior_672="".join(map(str,X[t-672:t,b])),
                    windows_12_to_672_appearances="|".join(map(str,cnt[:,b])),
                    pools_12_to_672=chain,
                    temperature_direction_chain="".join(
                        "Y" if delta>0 else "D" if delta<0 else "="
                        for delta in dif),
                    latest12=int(cnt[0,b]),latest72=int(cnt[5,b]),
                    latest672=int(cnt[-1,b]),target_result=int(actual[b])))
        for m in MODELS:
            selected=np.array(picks[m],dtype=np.int8)
            truth=actual[selected]
            rec=dict(date=date,target_id=rows[t]["id"],
                phase=phase,model=m,
                selected10="-".join(str(i+1) for i in selected),
                actual_hit_bits10="".join(str(int(v)) for v in truth))
            for k in TICKETS:
                h=int(truth[:k].sum())
                rec["isabet"+str(k)]=h
                if h==k: stats[(phase,m,k)][0]+=1
                stats[(phase,m,k)][1]+=1
                stats[(phase,m,k)][2]+=h
                if h>=5:stats[(phase,m,k)][3]+=1
                if h>=6:stats[(phase,m,k)][4]+=1
                if h>=7:stats[(phase,m,k)][5]+=1
                if h>=8:stats[(phase,m,k)][6]+=1
                if h>=9:stats[(phase,m,k)][7]+=1
                if h==10:stats[(phase,m,k)][8]+=1
            zrows.append(rec)
            dayhits[(date,m)].append(int(truth[:10].sum()))
        if t%2500==0:
            print("V119 processed targets",t-672,"/",n-672,flush=True)
    assert sum(counts_by_phase.values())==n-672
    assert len(zrows)==(n-672)*len(MODELS)
    # Summary all phases and models, then per k
    agg=[]
    for phase in ("TRAIN36","VALIDATE18","LAST18","EXTRA_AFTER_OCT12"):
        for m in MODELS:
            for k in TICKETS:
                v=stats[(phase,m,k)]
                if not v[1]:continue
                agg.append(dict(phase=phase,model=m,budget=k,
                    targets=v[1],
                    avg_hits=round(v[2]/v[1],6),
                    theoretical_expected_hits=k/4.,
                    perfect_k_of_k=v[0],
                    hits_5_or_more=v[3],
                    hits_6_or_more=v[4],
                    hits_7_or_more=v[5],
                    hits_8_or_more=v[6],
                    hits_9_or_more=v[7],
                    hits_10_of_10=v[8]))
    # Daily cluster bootstrap on pre-declared primary model
    result_boot={}
    all_dates=sorted(date for date in valid_days if phase_day[date]=="LAST18")
    assert len(all_dates)==18
    for baseline in ("RANDOM","HOT72"):
        for model in (PRIMARY,"NEST_01_BURST","NEST_REVERSAL","HOT12","HOT672"):
            diff=np.asarray([
                np.mean(dayhits[(date,model)])-np.mean(dayhits[(date,baseline)])
                for date in all_dates],float)
            rng=np.random.default_rng(SEED+len(model)*100+len(baseline))
            boot=diff[rng.integers(0,len(diff),size=(10000,len(diff)))].mean(axis=1)
            result_boot[f"{model}_vs_{baseline}"]=dict(
                mean=float(diff.mean()),
                lo95=float(np.quantile(boot,.025)),
                hi95=float(np.quantile(boot,.975)))
    lines=[
      "V119 SAYI TABANLI 56 IC ICE HALKA 1-0 / 3 4 5 6 8 10 TAM ISABET",
      "Yedili, altili, diger aile kimligi kullanilmadi.",
      f"Last source draw #{rows[-1]['id']} {rows[-1]['day']}.",
      f"All genuine next-draw tests: {n-672}; one same-budget ticket per model per draw.",
      "56 retrospective windows are LAST 12,24,36,...672 consecutive observed draws.",
      "Scoring and selections frozen BEFORE the target draw.",
      "NEST_CONTRAST compares 6 shortest windows' pool levels with 6 longest;",
      "NEST_REVERSAL uses the opposite, NEST_01_BURST compares last12 hit",
      "rate against preceding60, HOT12/HOT72/HOT672 frequency baselines.",
      "All pool grades 0..4 contain exactly 16 of the 80 numbers.",
      "Primary comparison is prespecified NEST_CONTRAST vs HOT72 and RANDOM.",
      "Same old 72 historical days have been researched many times.",
      "LAST18 is held out only in THIS script, NOT genuinely unseen research.",
      "Chance expected hits for fixed k is k/4 every draw, no guarantee.",
      ""]
    for phase in ("LAST18","EXTRA_AFTER_OCT12","VALIDATE18"):
        if phase not in counts_by_phase:continue
        lines.append(f"{phase}: number of actual target draws={counts_by_phase[phase]}")
        for k in TICKETS:
            lines.append(f" KUPON {k} SAYI:")
            for m in MODELS:
                match=next((v for v in agg if v["phase"]==phase and
                            v["model"]==m and v["budget"]==k),None)
                if not match:continue
                lines.append(f"  {m}: avg={match['avg_hits']:.4f}/"+
                    f"{k}; {k}/{k}={match['perfect_k_of_k']}; "+
                    f"5+={match['hits_5_or_more']} "+
                    f"6+={match['hits_6_or_more']} "+
                    f"8+={match['hits_8_or_more']} "+
                    f"10/10={match['hits_10_of_10']}")
    lines.append("Paired LAST18 day-bootstrap 10-number avg hits differences:")
    for name,v in result_boot.items():
        if name in (f"{PRIMARY}_vs_RANDOM",f"{PRIMARY}_vs_HOT72"):
            lines.append(f" {name}: {v['mean']:+.5f}, 95% [{v['lo95']:.5f}, {v['hi95']:.5f}]")
    lines+=["",
      "Do NOT select the best-performing retrospective method and call it predictive.",
      "Multiple model/budget comparisons create many apparent chance wins.",
      "No proof of beating random chance or of 10/10 predictive advantage.",
      "Target outcome never enters its own 56-ring 1/0 features."]
    out=Path(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_V119_TURKCE_KISA_CEKILIS_SONUC.txt","\n".join(lines)+"\n")
        csvwrite(z,"01_HER_HEDEF_3_4_5_6_8_10_CEKILIS_KUPON_ISABET.csv",zrows)
        csvwrite(z,"02_MODELLER_DONEMLER_K_K_ISABET_ORTALAMA.csv",agg)
        csvwrite(z,"03_SON_HEDEF_80_SAYI_56_ICICE_HAVUZ_01_PROFIL.csv",final_profile)
        z.writestr("04_GUN_ESLESMELI_GUVEN_ARALIKLARI.json",
                   json.dumps(result_boot,ensure_ascii=False,indent=2))
        z.writestr("05_DENETIM_KAPSAM.json",
          json.dumps(dict(source_draws=n,first_target_index=672,
             tested_target_draws=n-672,target_phase_counts=dict(counts_by_phase),
             models=list(MODELS),ticket_sizes=list(TICKETS),
             windows=WINDOWS.tolist(),all_target_outputs=len(zrows),
             target_known_before_pick=False,
             preselected_primary_model=PRIMARY,
             genuinely_prospective=False,
             source_last_id=rows[-1]["id"]),ensure_ascii=False,indent=2))
    print("\n".join(lines),flush=True)
    print("V119 COMPLETE",out,out.stat().st_size,flush=True)

if __name__=="__main__":
    arg=argparse.ArgumentParser()
    arg.add_argument("--source",default="veri.txt")
    arg.add_argument("--out",default="v119_output/V119_56_ICICE_80_SAYI_HEDEF_ISABET.zip")
    a=arg.parse_args()
    main(a.source,a.out)
