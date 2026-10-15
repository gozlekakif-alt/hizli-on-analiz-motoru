#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V71: rolling 217 target-draw walk-forward temperature-window tournament.

For every 12 October 2026 target #61629..#61845, select the coldest,
hottest or central k=(10,15,20) numbers using counts from each PREVIOUS
N draws. N ranges 12..15407 by 12 plus selected special horizons.
Counts always exclude the target outcome; no look-ahead. The frozen
selections are assessed against observed next draw, fair 20-of-80
hypergeometric expectations, exact null tails for 217 draw totals,
and BONFERRONI familywise correction across all tested windows/models.

Because the 12 October data have already been explored, this is a
RETROSPECTIVE walk-forward experiment, not fresh independent validation.
"""
from __future__ import annotations
import argparse,csv,io,json,math,random,zipfile
from pathlib import Path
from collections import Counter
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V71.1"
FOCUS_DAY="2026-10-12"
ANCHOR_ID=61629
SIZES=(10,15,20)
POLICIES=("COLD","MIDDLE","HOT")
NAMED=(12,24,36,42,56,72,96,120,144,168,192,217,288,432,
       576,720,864,1008,1440,2160,3024,4340,6510,8680,10850,15407)
BASELINE_SEED=710171
N_TARGET=217
RNG_MEAN={k:k/4 for k in SIZES}
FAIR_VAR={k:20*(k/80)*(1-k/80)*(60/79) for k in SIZES}

def load(src):
    data,issues,malformed=parse_txt(src)
    full=sorted(day for day,rows in data.items() if
        len(rows)==217 and [row["pos"] for row in rows]==list(range(1,218)))
    if len(full)<72 or full[71]!=FOCUS_DAY:
        raise ValueError(f"Expected 12 Oct as the 72nd complete day: {len(full)} {full[-1] if full else ''}")
    history=[r for d in full[:71] for r in data[d]]
    targets=data[FOCUS_DAY]
    if len(history)!=15407 or targets[0]["id"]!=ANCHOR_ID or targets[-1]["id"]!=61845:
        raise ValueError("Wrong dataset order or 12 Oct first/last ID")
    return history,targets,full,issues,malformed

def prefixes(records):
    """cumulative occurrence counts for N historical draws; prefix[0]=zeros."""
    cum=np.zeros((len(records)+1,80),dtype=np.int32)
    for i,row in enumerate(records):
        cum[i+1]=cum[i]
        cum[i+1,np.asarray(row["nums"],dtype=int)-1]+=1
    return cum

def pick(order,policy,k):
    if policy=="COLD":return order[:k]
    if policy=="HOT":return order[-k:]
    if policy=="MIDDLE":
        offset=(80-k)//2
        return order[offset:offset+k]
    raise ValueError(policy)

def null_pmf(total_targets,k):
    """Exact distribution of sum of independent HGeom(80,k,20) hits.
    Adaptively selected k-subsets from past draws have this same null law.
    """
    denom=math.comb(80,20)
    one=np.array([math.comb(k,j)*math.comb(80-k,20-j)/denom
          if 0<=20-j<=80-k else 0 for j in range(k+1)],dtype=float)
    assert abs(sum(one)-1)<1e-12
    d=np.array([1.0])
    for _ in range(total_targets):d=np.convolve(d,one)
    d=np.maximum(d,0)
    d/=d.sum()
    return d

def pvals(pmf,observed,k):
    idx=int(observed)
    expectation=N_TARGET*k/4
    right=float(pmf[idx:].sum())
    left=float(pmf[:idx+1].sum())
    diff=abs(observed-expectation)
    ix=np.arange(len(pmf))
    two=float(pmf[np.abs(ix-expectation)>=diff-1e-10].sum())
    return min(1,right),min(1,left),min(1,two)

def make_csv(z,filename,rows,columns=None):
    if columns is None:
        if not rows:raise ValueError(filename)
        columns=list(rows[0])
    with z.open(filename,"w",force_zip64=True) as raw:
        stream=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        writer=csv.DictWriter(stream,fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
        stream.flush();stream.detach()

def compute(source,out):
    historical,targets,full_dates,issues,malformed=load(source)
    lookbacks=sorted(set(range(12,15408,12))|set(NAMED))
    named_set=set(NAMED)
    nwin=len(lookbacks)
    print(f"V71 target={FOCUS_DAY} 217; previous 71 complete days={len(historical)}; "
          f"tested lookbacks={nwin}; methods={nwin*len(POLICIES)*len(SIZES)}",flush=True)
    all_history=historical+targets
    prefix=prefixes(all_history)
    assert len(prefix)==15625
    # axes: history window, COLD/MIDDLE/HOT, selected 10/15/20, 217 target slots
    hits=np.zeros((nwin,3,3,217),dtype=np.uint8)
    tier_counts=np.zeros((nwin,217,5),dtype=np.uint8)
    thresholds=np.zeros((nwin,6),dtype=np.int32)
    named_by_target=[]
    rng=random.Random(BASELINE_SEED)
    random_hits={k:[] for k in SIZES}
    number_slots={n:[] for n in NAMED}
    ball_idx=np.arange(80,dtype=np.int32)
    t20sum=0
    for pos,target in enumerate(targets):
        upto=len(historical)+pos
        actual=np.zeros(80,dtype=np.uint8)
        actual[np.asarray(target["nums"],dtype=int)-1]=1
        assert int(actual.sum())==20
        rand20=rng.sample(range(80),20)
        for k in SIZES:
            random_hits[k].append(int(actual[np.asarray(rand20[:k],dtype=int)].sum()))
        for j,n in enumerate(lookbacks):
            f=prefix[upto]-prefix[upto-n]
            assert int(f.sum())==n*20
            order=np.lexsort((ball_idx,f))
            five=np.empty(80,dtype=np.uint8)
            five[order]=np.arange(80,dtype=int)//16
            tier_counts[j,pos]=np.bincount(five[actual==1],minlength=5)
            if pos==0:
                # counts of equal-frequency groups crossing potential cutoffs
                thresholds[j]=[
                   int(f[order[t-1]]==f[order[t]]) for t in (10,15,20,30,40,64)]
            for q,policy in enumerate(POLICIES):
                for h,k in enumerate(SIZES):
                    selected=pick(order,policy,k)
                    hit=int(actual[selected].sum())
                    hits[j,q,h,pos]=hit
                    if n in named_set:
                        named_by_target.append(dict(date=FOCUS_DAY,
                          slot=pos+1,draw_id=target["id"],clock=target["time"],
                          past_draws=n,policy=policy,pool_size=k,
                          selected_numbers=",".join(map(str,sorted(int(z)+1 for z in selected))),
                          successes=hit,fair_expected=k/4,
                          hit_numbers=",".join(map(str,sorted(int(z)+1 for z in selected if actual[z])))))
        if pos in (0,53,107,161,216):
            print(f"V71 recorded {pos+1}/217: #{target['id']}",flush=True)
    assert int(tier_counts.sum())==nwin*217*20
    assert hits.max()<=20

    nulls={k:null_pmf(217,k) for k in SIZES}
    total_models=nwin*len(POLICIES)*len(SIZES)
    named_models=len(named_set)*len(POLICIES)*len(SIZES)
    summaries=[]
    detail=[]
    for j,n in enumerate(lookbacks):
        for q,policy in enumerate(POLICIES):
            for h,k in enumerate(SIZES):
                series=hits[j,q,h].astype(int)
                total=int(series.sum())
                upper,lower,two=pvals(nulls[k],total,k)
                row=dict(past_draws=n,policy=policy,pool_size=k,
                    test_draws=217,total_hits=total,
                    average_hits=round(total/217,6),fair_mean=k/4,
                    diff_from_fair=round(total/217-k/4,6),
                    max_one_draw=int(max(series)),
                    full_hits=int((series==k).sum()),
                    p_one_sided_higher=round(upper,9),
                    p_one_sided_lower=round(lower,9),
                    p_two_sided=round(two,9),
                    bonf_11619_one_sided=min(1,upper*total_models),
                    bonf_234_named_one_sided=min(1,upper*named_models) if n in named_set else None,
                    is_requested_named=int(n in named_set))
                summaries.append(row)
                if n in named_set:
                    detail.append(dict(**row,
                        first108_average=round(float(series[:108].mean()),5),
                        last109_average=round(float(series[108:].mean()),5),
                        isabet_dagilimi=";".join(f"{t}:{int((series==t).sum())}"
                             for t in range(k+1))))
    summaries.sort(key=lambda x:(-x["diff_from_fair"],x["past_draws"],x["policy"],x["pool_size"]))
    named=sorted((r for r in detail),key=lambda x:(x["past_draws"],x["pool_size"],x["policy"]))
    strongest_by_k={k:next(r for r in summaries if r["pool_size"]==k) for k in SIZES}
    random_summary=[]
    for k in SIZES:
        vals=random_hits[k]
        total=sum(vals);p_hi,p_lo,p_two=pvals(nulls[k],total,k)
        random_summary.append(dict(pool_size=k,mean_hit=round(total/217,6),
           total_hits=total,fair_mean=k/4,p_one_sided_higher=p_hi,
           distribution=";".join(f"{j}:{vals.count(j)}" for j in range(k+1))))
    rank_profile=[]
    for n in NAMED:
        j=lookbacks.index(n)
        vals=tier_counts[j]
        count_zero_hot=int((vals[:,4]==0).sum())
        rank_profile.append(dict(past_draws=n,targets=217,
           expected_per_quintile=4,
           avg_cold=round(float(vals[:,0].mean()),5),
           avg_cool=round(float(vals[:,1].mean()),5),
           avg_neutral=round(float(vals[:,2].mean()),5),
           avg_warm=round(float(vals[:,3].mean()),5),
           avg_hot=round(float(vals[:,4].mean()),5),
           count_hot_zero=count_zero_hot,
           count_perfect_4each=int(((vals==4).all(axis=1)).sum()),
           first_draw_profile="/".join(map(str,vals[0].tolist())),
           first_draw_frequency_ties_at_cuts=int(thresholds[j].sum())))
    profile_detail=[]
    for n in NAMED:
        j=lookbacks.index(n)
        for pos,target in enumerate(targets):
            cc=tier_counts[j,pos]
            profile_detail.append(dict(past_draws=n,slot=pos+1,
              draw_id=target["id"],clock=target["time"],
              cold=int(cc[0]),cool=int(cc[1]),neutral=int(cc[2]),
              warm=int(cc[3]),hot=int(cc[4])))
    all_zero_hot=int((tier_counts[:,:,4]==0).sum())
    best=summaries[0]
    topline=[
      f"V71 | 12 EKIM 217 HEDEFIN 1.291 SICAKLIK PENCERESI KOR TESTI",
      f"Focus: {FOCUS_DAY} #{targets[0]['id']}..#{targets[-1]['id']}",
      f"Prior 71 full days={len(historical)} draws.",
      f"All windows={nwin}; policies={','.join(POLICIES)}; pool sizes={','.join(map(str,SIZES))}.",
      f"Total pre-frozen strategies={total_models} (requested 26 windows: {named_models}).",
      "Each historical horizon is number of previous DRAWS, not hours.",
      "For each target, rank 80 numbers on last N history draws; target never included.",
      "HOT20, COLD20, MIDDLE20 (and 10/15 analogues) are fixed BEFORE true target.",
      "Fair per-draw expected selected hits: size10=2.5, size15=3.75, size20=5.",
      "Significance p from exact 217-fold hypergeometric sum, no approximate fake p.",
      "Familywise correction uses conservative Bonferroni over 11619 tested hypotheses.",
      "This is retrospective! Entire focus date has been previously inspected.",
      "",
      "BEST LOOKBACKS FROM FULL RETROSPECTIVE WINDOW SEARCH (NOT FORECAST RULES):"]
    for k in SIZES:
        rr=strongest_by_k[k]
        topline.append(f"SIZE {k} top retrospectively: N={rr['past_draws']} {rr['policy']}, "
            f"{rr['average_hits']:.5f}/{k}, fair={k/4:.2f}; p_raw={rr['p_one_sided_higher']:.6g}; "
            f"Bonferroni {total_models} tests={rr['bonf_11619_one_sided']:.6g}")
    topline.append("")
    topline.append("ONE SEEDED RANDOM POOL PER DRAW (same 217 targets):")
    for rr in random_summary:
        topline.append(f"k={rr['pool_size']}: {rr['mean_hit']:.5f}/{rr['pool_size']}, "
          f"fair={rr['fair_mean']:.2f}")
    topline.append("")
    topline.append("FULL TARGET20 QUINTILE PROFILES BY REFERENCE WINDOW:")
    for r in rank_profile:
        topline.append(f"N={r['past_draws']:>5} mean C/S/N/I/H "
            f"{r['avg_cold']:.2f}/{r['avg_cool']:.2f}/{r['avg_neutral']:.2f}/"
            f"{r['avg_warm']:.2f}/{r['avg_hot']:.2f}; "
            f"hot0={r['count_hot_zero']}; 4all={r['count_perfect_4each']}")
    topline +=["",
      "CONCLUSION: Selection improvement must be PROVEN on truly new, future unseen draws.",
      "Optimizing past window after seeing 217 targets can manufacture patterns.",
      "The 217 results and every selection are preserved in CSV files.",
      "Use Bonferroni corrected p, not the biggest unadjusted observed mean.",
      ""]
    out=Path(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        z.writestr("00_KISA_KARAR_V71.txt","\n".join(topline))
        make_csv(z,"01_TUM_1291_PENCERE_X_9_YONTEM_SONUCLAR.csv",summaries)
        make_csv(z,"02_26_ANA_PENCERE_X_9_YONTEM_DETAY.csv",named)
        make_csv(z,"03_217_HEDEF_X_26_PENCERE_X_9_SECIM_KUPON_VE_ISABET.csv",named_by_target)
        make_csv(z,"04_217_HEDEFIN_26_PENCERE_ISI_DAGILIM_ORTALAMALARI.csv",rank_profile)
        make_csv(z,"05_217_HEDEF_X_26_PENCERE_BES_ISI_HAVUZU.csv",profile_detail)
        make_csv(z,"06_KARSILASTIRMA_RASTGELE_KUPONLAR.csv",random_summary)
        z.writestr("07_METODOLOJI.txt","\n".join([
          "Input file veri.txt: 71 full previous days, focus 217 October12 draws.",
          "Every target evaluated after choosing based on earlier draws only.",
          "N=12..15407 in increments of 12 plus special N=42,56,217 etc.",
          "Sort the 80 balls by exact N-draw appearance count; ties by ascending number.",
          "HOT: k highest-ranked balls; COLD: k lowest; MIDDLE: central k.",
          "20-number target five-heat profile uses 16-ball equal quintiles,",
          "expected four per tier under independent fair 20/80.",
          "Full observations compared to math hypergeometric fair null:",
          "one target hit=X, X~Hypergeometric(population=80, chosen=k, draw=20).",
          "All 217 results have identical null law even when each k-pool depends on past",
          "because future fair draw is independent of all previous draws.",
          "Exact null for 217 summed hits constructed by 217-fold probability convolution.",
          "Top results were selected after examining MANY windows. Bonferroni over",
          "all windows*all policies*all 10/15/20 pool sizes corrects selection bias.",
          "A single seeded random pool per target is separately reported.",
          "No peeking ahead; yet retroactive focus date was previously researched.",
          "No demonstrated random-number generator algorithm / seed recovery.",
          "No claimed betting edge or guaranteed prediction."
        ])+"\n")
        z.writestr("08_AUDIT.json",json.dumps(dict(version=VERSION,
          focus=FOCUS_DAY,first_target_id=targets[0]["id"],
          last_target_id=targets[-1]["id"],prior_complete_days=full_dates[:71],
          prior_draws=len(historical),test_draws=217,
          tested_lookbacks=nwin,lookbacks_named=NAMED,
          policies=POLICIES,pool_sizes=SIZES,total_hypotheses=total_models,
          bonferroni_correction=total_models,requested_hypotheses=named_models,
          rng_seed=BASELINE_SEED, best_retrospective_by_pool=strongest_by_k,
          random_baselines=random_summary,first_target_quintiles={
             str(n):tier_counts[lookbacks.index(n),0].tolist() for n in NAMED},
          malformed_count=len(malformed),malformed_first=malformed[:15],
          issues=issues[:15]),indent=2,ensure_ascii=False))
    print("\n".join(topline),flush=True)
    print("ZIP",str(out),"bytes",out.stat().st_size,flush=True)

def selftest():
    # One target independent of its own history; verify selection k
    order=np.arange(80)
    for k in SIZES:
        for method in POLICIES:
            p=pick(order,method,k)
            assert len(p)==k and len(set(p))==k
    for k in (10,15,20):
        prob=null_pmf(7,k)
        assert abs(prob.sum()-1)<1e-9
        assert abs(float(np.dot(np.arange(len(prob)),prob))-7*k/4)<1e-7
    # Direct prefix check
    mini=[{"nums":tuple(range(1,21))},{"nums":tuple(range(11,31))}]
    prefix=prefixes(mini)
    assert int(prefix[2].sum())==40
    assert int((prefix[2]-prefix[1]).sum())==20
    print("V71 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--output",default="v71_output/V71_217_CEKILIS_TUM_SICAKLIK_PENCERE_KOR_TEST.zip")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest()
    else:compute(args.source,args.output)
