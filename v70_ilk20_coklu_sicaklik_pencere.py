#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V70: 12 Oct first 20 numbers against every earlier lookback scale.

Fixed target: the first draw of the 72nd full day, 12 October 2026, #61629.
For each N prior draws, rank ALL 80 numbers by frequency in exactly those
N historical draws, tie-break ascending number. Split 80 numbers into
5 quintiles of 16 each; count the fixed target 20 in each quintile.
A fully independent fair draw gives expectation 4 per quintile but any
specific 5-bin outcome is random. Also record fixed mathematical z-score
temperature classes (sizes vary).
Use conditional randomization of 20-of-80 target labels relative to the
full untouched historical feature vectors. The SAME random 20-target is
tested across ALL lookbacks to calibrate window search/multiple testing.
Do not use target actual numbers to build historical rankings/features.
This is retrospective exploration, not a prospective winning method.
"""
from __future__ import annotations
import argparse, csv, io, json, math, zipfile
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

SEED=701015
CATS=("SOGUK","SERIN","NOTR","ILIK","SICAK")
ANCHOR_DAY="2026-10-12"
ANCHOR_ID=61629
FOCUS_N=(12,24,36,42,56,72,96,120,144,168,192,217,
         288,432,576,720,864,1008,1440,2160,3024,4340,
         6510,8680,10850,15407)

def combprob_zero_hot():
    return math.comb(64,20)/math.comb(80,20)

def combprob_balanced():
    return math.comb(16,4)**5/math.comb(80,20)

def load(source):
    grouped,issues,malformed=parse_txt(source)
    full_dates=sorted(d for d,rows in grouped.items() if len(rows)==217
        and [r["pos"] for r in rows]==list(range(1,218)))
    if len(full_dates)<72:raise ValueError("Need 72 full days")
    if full_dates[71]!=ANCHOR_DAY:raise ValueError("Focus changed: "+full_dates[71])
    anchor=grouped[ANCHOR_DAY][0]
    if anchor["id"]!=ANCHOR_ID or anchor["time"]!="00:02":
        raise ValueError("Unexpected anchor")
    before=[row for d in full_dates[:71] for row in grouped[d]]
    if len(before)!=15407:raise AssertionError("Expected 71 x 217 prior draws")
    return anchor,before,full_dates,issues,malformed

def csvout(z,path,rows,columns=None):
    cols=columns or list(rows[0])
    with z.open(path,"w",force_zip64=True) as raw:
        stream=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        writer=csv.DictWriter(stream,fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)
        stream.flush();stream.detach()

def pvalue(condition,N):
    return round((int(np.count_nonzero(condition))+1)/(N+1),6)

def run(source,out,nsims):
    anchor,before,dates,issues,malformed=load(source)
    total=len(before)
    # All multiples of 12, plus specifically requested 42, 56, 217,
    # and historical end (15,407), plus other named horizons.
    lengths=sorted(set(list(range(12,total+1,12))
                       +[n for n in FOCUS_N if n<=total]+[total]))
    index_of={n:i for i,n in enumerate(lengths)}
    print(f"V70 date={ANCHOR_DAY}, anchor #{ANCHOR_ID}, "
          f"past={total}, windows={len(lengths)}, simulations={nsims}",flush=True)
    counts=np.zeros(80,dtype=np.int32)
    freq_by_window=np.empty((len(lengths),80),dtype=np.int32)
    now=0
    for i,n in enumerate(lengths):
        while now<n:
            entry=before[-now-1]
            counts[np.asarray(entry["nums"],dtype=int)-1]+=1
            now+=1
        assert int(np.sum(counts))==20*n
        freq_by_window[i]=counts

    target=np.zeros(80,dtype=np.float32)
    target[np.asarray(anchor["nums"],dtype=int)-1]=1.0
    tiers=np.empty((len(lengths),80),dtype=np.int8)
    obs=np.empty((len(lengths),5),dtype=np.int16)
    zcounts=np.empty((len(lengths),5),dtype=np.int16)
    zcaps=np.empty((len(lengths),5),dtype=np.int16)
    sd_score=np.empty(len(lengths),dtype=np.float64)
    ztarget=np.empty(len(lengths),dtype=np.float64)
    means=np.empty(len(lengths),dtype=np.float64)
    sums=np.empty(len(lengths),dtype=np.float64)
    tie_at_boundary=np.empty(len(lengths),dtype=np.int16)
    norms=np.zeros((len(lengths),80),dtype=np.float32)
    labels=np.arange(80)
    for i,n in enumerate(lengths):
        f=freq_by_window[i]
        order=np.lexsort((labels,f))
        ids=np.empty(80,dtype=np.int8)
        ids[order]=np.arange(80,dtype=np.int16)//16
        tiers[i]=ids
        obs[i]=np.bincount(ids[np.asarray(anchor["nums"])-1],minlength=5)
        assert int(obs[i].sum())==20
        crossing=0
        for edge in (16,32,48,64):
            crossing+=int(f[order[edge-1]]==f[order[edge]])
        tie_at_boundary[i]=crossing
        # Alternative, absolute z thresholds: -1.5, -0.5, 0.5, 1.5.
        expected=n/4
        sd0=math.sqrt(n*.25*.75)
        categories=np.searchsorted([-1.5,-.5,.5,1.5],
                        (f-expected)/sd0,side="right")
        zcaps[i]=np.bincount(categories,minlength=5)
        zcounts[i]=np.bincount(categories[np.asarray(anchor["nums"])-1],minlength=5)
        assert int(zcaps[i].sum())==80 and int(zcounts[i].sum())==20
        sums[i]=float(np.dot(target,f))
        means[i]=sums[i]/20
        var=float(np.mean((f-expected)**2))
        se=math.sqrt(var*60/(20*79))
        sd_score[i]=se
        ztarget[i]=(means[i]-expected)/se if se>0 else 0
        if se>0:norms[i]=(f.astype(float)-expected)/(20*se)

    rng=np.random.default_rng(SEED)
    selections=np.zeros((80,nsims),dtype=np.float32)
    for j in range(nsims):
        selections[rng.choice(80,20,replace=False),j]=1
    assert np.all(selections.sum(axis=0)==20)
    print("Computing all-window shared-target Monte Carlo null",flush=True)
    nullz=norms@selections
    maxabs=np.max(np.abs(nullz),axis=0)
    observed_max=float(np.max(np.abs(ztarget)))
    p_global_z=pvalue(maxabs>=observed_max-1e-8,nsims)
    extreme_idx=int(np.argmax(np.abs(ztarget)))

    null_imbalance=np.zeros((len(lengths),nsims),dtype=np.float32)
    allbalanced=np.ones((len(lengths),nsims),dtype=bool)
    null_hot=np.empty((len(lengths),nsims),dtype=np.float32)
    for group in range(5):
        mask=(tiers==group).astype(np.float32)
        number_hits=mask@selections
        null_imbalance+=(number_hits-4)**2
        allbalanced&=(number_hits==4)
        if group==4:null_hot=number_hits
    p_global_any_zero=pvalue((null_hot==0).any(axis=0),nsims)
    p_global_any_balanced=pvalue(allbalanced.any(axis=0),nsims)

    obs_imbalance=np.sum((obs.astype(int)-4)**2,axis=1)
    rows=[]
    for i,n in enumerate(lengths):
        r=dict(past_draws=n,expected_per_number=round(n/4,4),
               selected_mean=round(means[i],5),
               selected_mean_minus_expected=round(means[i]-n/4,5),
               conditional_z=round(float(ztarget[i]),5),
               selected_quintile_imbalance=int(obs_imbalance[i]),
               num_tied_quintile_boundaries=int(tie_at_boundary[i]),
               tier_cold=int(obs[i,0]),tier_cool=int(obs[i,1]),
               tier_neutral=int(obs[i,2]),tier_warm=int(obs[i,3]),
               tier_hot=int(obs[i,4]),
               selected_exact_mean_two_sided_p=pvalue(
                   np.abs(nullz[i])>=abs(ztarget[i])-1e-8,nsims),
               observed_hot_count_or_fewer_p=pvalue(
                   null_hot[i]<=obs[i,4],nsims),
               observed_equal_or_better_balance_p=pvalue(
                   null_imbalance[i]<=obs_imbalance[i]+1e-8,nsims),
               **{"standard_temp_pool_"+s.lower():int(zcaps[i,j]) for j,s in enumerate(CATS)},
               **{"standard_temp_target_"+s.lower():int(zcounts[i,j]) for j,s in enumerate(CATS)})
        rows.append(r)
    samples=[]
    for n in FOCUS_N:
        if n in index_of:samples.append(rows[index_of[n]])
    identity=[]
    for n in FOCUS_N:
        if n not in index_of:continue
        i=index_of[n];f=freq_by_window[i]
        for num in sorted(anchor["nums"]):
            identity.append(dict(past_draws=n,number=num,
                previous_occurrences=int(f[num-1]),
                expected_occurrences=n/4,
                deviation=round(float(f[num-1]-n/4),3),
                relative_quintile=CATS[tiers[i,num-1]]))
    most_cold=sorted(rows,key=lambda r:(r["tier_hot"],
                                   r["conditional_z"],r["past_draws"]))[:10]
    extremal=[rows[i] for i in np.argsort(-np.abs(ztarget))[:12]]
    balanced_n=[int(lengths[i]) for i in range(len(lengths)) if int(obs_imbalance[i])==0]
    zero_hot_n=[int(lengths[i]) for i in range(len(lengths)) if int(obs[i,4])==0]
    ix_all=index_of[total]
    ix217=index_of[217]
    topline=[
       "V70 — 12 EKIM ILK CEKILISINDEKI 20 SAYININ TUM GECMISE GORE SICAKLIK PROFILI",
       f"Target: {anchor['day']} {anchor['time']} #{anchor['id']}",
       "Target20="+",".join(map(str,sorted(anchor["nums"]))),
       f"Prior full days=71; prior completed draw count={total}; lookback windows={len(lengths)}",
       "Every window uses exactly PREVIOUS N draws; NEVER the target itself.",
       "Each window ranks the 80 historical frequency counts, cold to hot,",
       "into 5 equal tiers of 16 numbers; fair expected target occupancy 4 in each.",
       "Frequency ties resolved by ascending ball ID; tie count reported per boundary.",
       "Also independent fixed-standard-score z temperature classes in output CSV.",
       f"Conditional 20-of-80 unbiased null simulation replicates={nsims}; same random target across all windows.",
       "",
       "LOOKBACK_N | COLD COOL NEUTRAL WARM HOT | TARGET MEAN - NULL MEAN | Z | P(|Z|) | TIED BOUNDARIES"]
    for r in samples:
        topline.append(f"{r['past_draws']:>7} | "
          + " ".join(str(r[f"tier_{c}"]) for c in ("cold","cool","neutral","warm","hot"))
          +f" | {r['selected_mean_minus_expected']:+.3f} | {r['conditional_z']:+.3f} "
          +f"| {r['selected_exact_mean_two_sided_p']:.4f} | {r['num_tied_quintile_boundaries']}")
    topline +=[
       "",
       "SPECIAL OBSERVATIONS:",
       f"N=217 hot hits {obs[ix217,4]}/20: P(random target avoids 16 hottest balls)={combprob_zero_hot():.7f} (SINGLE PRESELECTED window).",
       f"N={total} tiers {tuple(map(int,obs[ix_all]))}: P(exactly 4 from EACH of 5 fixed 16-ball groups)={combprob_balanced():.7f} (SINGLE PRESELECTED window).",
       f"Across all {len(lengths)} windows: observed count N with zero-hot={len(zero_hot_n)}, any-zero-hot Monte Carlo P={p_global_any_zero:.5f}.",
       f"Across all {len(lengths)} windows: observed count N with perfect 4/4/4/4/4={len(balanced_n)}, any-perfect Monte Carlo P={p_global_any_balanced:.5f}.",
       f"Across all windows: largest |z|={observed_max:.4f} at N={lengths[extreme_idx]},  lookback-search adjusted Monte Carlo p={p_global_z:.5f}.",
       "",
       "INTERPRETATION:",
       "Strong changes in each ball's hot/cold LABEL across lookback horizons are expected;",
       "they do not prove a hidden RNG balancing algorithm or predict the next draw.",
       "The 217-window zero-hot and full-history perfect balance are unusual if those",
       "windows were FIXED IN ADVANCE, but many windows were inspected, so account",
       "for cherry-picking using same-target all-window null simulations.",
       "The 20-number target was ALREADY DRAWN; this is diagnostic not blind forecasting.",
       "To establish predictive value, set lookbacks/features before analyzing new unseen draws.",
       "",
       "Files: sample-window table, every ~12-draw horizon, number-by-number identities,",
       "horizon extremes, and audit JSON (one ZIP).",
       ""
    ]
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        z.writestr("00_KISA_SONUC_V70.txt","\n".join(topline))
        csvout(z,"01_ISTENEN_PENCERELER_12_24_36_42_56_72_DEVAM.csv",samples)
        csvout(z,"02_TUM_GECMIS_PENCERELER_YAKLASIK_12_ADIM.csv",rows)
        csvout(z,"03_20_SAYI_26_PENCEREDE_HANGI_SICAKLIKTA.csv",identity)
        csvout(z,"04_EN_UC_SAPMA_PENCERELERI.csv",extremal)
        csvout(z,"05_SICAK_0_PENCERELER.csv",
               [rows[index_of[n]] for n in zero_hot_n] if zero_hot_n else [],
               list(rows[0]))
        csvout(z,"06_TAM_DENGELI_4_4_4_4_4_PENCERELER.csv",
               [rows[index_of[n]] for n in balanced_n] if balanced_n else [],
               list(rows[0]))
        z.writestr("07_METOT.txt","\n".join([
           "Target #61629 12 October 2026 00:02, 20 unique ball numbers.",
           "Historical data restricted to prior 71 days with 217 draws each.",
           "Lookback count N is DRAW COUNT not hours/days.",
           "5 relative quintiles: 80 ball identities sorted by N-draw frequency;",
           "numeric ascending tie-break. Each tier exactly 16 identities.",
           "Label mapping: lowest=SOĞUK, SERIN, NOTR, ILIK, highest=SICAK.",
           "Alternative absolute categories: z=(f-N/4)/sqrt(N*.25*.75).",
           "Z thresholds -1.5,-.5,+.5,+1.5, all pool sizes are data-driven.",
           "A 20-ball target from independent fair draws should have expected 4/16-tier.",
           "Finite-pop conditional variance for target20 average frequency",
           "var_targetmean=var_80_frequency*(80-20)/(20*(80-1)).",
           "Monte Carlo draws uniform subsets of 20 of 80 independently of history.",
           "Every Monte Carlo target evaluated against ALL HISTORICAL windows,",
           "giving family-wise all-window max-|z| and any-zero-hot/any-balanced tests.",
           "No algorithm decoding, seed recovery, or guaranteed future advantage.",
           "This particular target was selected after observed draws, so all p values",
           "are descriptive/exploratory; next true prospectively unseen dates needed."
        ])+"\n")
        z.writestr("08_AUDIT.json",json.dumps(dict(version="V70",date=ANCHOR_DAY,
            target_id=ANCHOR_ID,first_draw_time=anchor["time"],
            target20=sorted(anchor["nums"]),prior_full_days=dates[:71],
            prior_draws=total,lookbacks_analyzed=len(lengths),
            requested_horizons=FOCUS_N,simulations=nsims,seed=SEED,
            p_zero_hot_217_single=combprob_zero_hot(),
            p_perfect_balance_full_single=combprob_balanced(),
            n217_profile=obs[ix217].tolist(),all_prior_profile=obs[ix_all].tolist(),
            number_zero_hot_windows=len(zero_hot_n),number_balanced_windows=len(balanced_n),
            p_global_any_zero=p_global_any_zero,
            p_global_any_balance=p_global_any_balanced,
            strongest_z=float(ztarget[extreme_idx]),strongest_z_n=int(lengths[extreme_idx]),
            p_global_maxabs_z=p_global_z,issues=issues[:30],
            malformed=malformed[:30]),ensure_ascii=False,indent=2))
    print("\n".join(topline),flush=True)
    print("ZIP",out,out.stat().st_size,flush=True)

def selftest():
    assert abs(sum(math.comb(12,k)*.25**k*.75**(12-k) for k in range(13))-1)<1e-10
    assert 0<combprob_balanced()<1 and 0<combprob_zero_hot()<1
    c=np.array([7]*16+[4]*16+[3]*16+[2]*16+[1]*16,dtype=int)
    order=np.lexsort((np.arange(80),c))
    tiers=np.empty(80,dtype=np.int8);tiers[order]=np.arange(80)//16
    assert np.array_equal(np.bincount(tiers,minlength=5),[16]*5)
    print("V70 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v70_output/V70_12_EKIM_ILK20_SICAKLIK_TUM_GECMIS_PENCERELER.zip")
    p.add_argument("--sims",type=int,default=4000)
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:selftest()
    else:
        if not 100<=a.sims<=20000:raise ValueError("sims range 100..20000")
        run(a.source,a.out,a.sims)
