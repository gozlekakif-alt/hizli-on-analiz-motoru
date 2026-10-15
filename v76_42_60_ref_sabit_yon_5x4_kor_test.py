#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V76 — fixed N=60 versus N=42, lag12, identical 5x4 transition rule.

N=60 is the user's new proposed reference; every other parameter is FROZEN
from V74: last N previous draws form five 16-ball temperature quintiles,
lookback L=12 defines previous position, direction classes 5x3, training-only
probability calibration alpha250 toward fair probability 0.25, four numbers
from each tier using probability rank and deterministic shared random ties.

Train 29 Aug..12 Sep (15 complete days = 3255 draws).
Validation 13..27 Sep (15 days).
Holdout 28 Sep..12 Oct (15 days).
Next sequential check 13 Oct through first data gap (#61958), 112 draws.
Compare same targets and evaluate paired exact-null variance for
N60 vs N42 plus matched 5x4 random control at each N.

No optimization using validation/holdout/next day: both N values and same
rule are fixed before reading targets. Prior conversational research already
inspected these dates; retrospective, NOT true novel prospective evidence.
"""
from __future__ import annotations
import argparse,csv,io,json,math,zipfile
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt
from v74_5x5_kimlik_yon_gecis_kalibrasyon import (
    prefixify,fixed_quintiles,states_of,posteriors,selection,
    paired_p, fair_p
)

VERSION="V76.1"
N_VALUES=(42,60)
LAG=12
KIND="DIRECTION15"
STRENGTH=250
SEED=741015
QUOTA=4
TIERS=("SOGUK","SERIN","NOTR","ILIK","SICAK")
PREP_DAYS=27
TRAIN_DAYS=15
VAL_DAYS=15
TEST_DAYS=15
DAY_SIZE=217
EARLY=PREP_DAYS*DAY_SIZE
TRAIN_END=EARLY+TRAIN_DAYS*DAY_SIZE
VAL_END=TRAIN_END+VAL_DAYS*DAY_SIZE
HOLD_END=VAL_END+TEST_DAYS*DAY_SIZE
STAGE_STARTS={"TRAIN":EARLY,"VALIDATE":TRAIN_END,
              "HOLDOUT":VAL_END,"NEXT_DAY":HOLD_END}
STAGE_ENDS={"TRAIN":TRAIN_END,"VALIDATE":VAL_END,
            "HOLDOUT":HOLD_END}
TRAIN_LEN=TRAIN_END-EARLY
V74_STEPS=HOLD_END-EARLY
assert V74_STEPS==9765

def load(path):
    grouped,issues,malformed=parse_txt(path)
    full_dates=sorted(d for d,r in grouped.items()
            if len(r)==217 and [v["pos"] for v in r]==list(range(1,218)))
    if len(full_dates)<72 or full_dates[71]!="2026-10-12":
        raise RuntimeError("Expected 72 completed days ending October 12")
    rows=[r for d in full_dates[:72] for r in grouped[d]]
    extra=grouped.get("2026-10-13",[])
    if not extra or rows[-1]["id"]!=61845 or extra[0]["id"]!=61846:
        raise RuntimeError("Unexpected Oct13 boundary")
    uninterrupted=[]
    for row in extra:
        if row["id"]!=61846+len(uninterrupted):
            break
        uninterrupted.append(row)
    if len(uninterrupted)<20:raise RuntimeError("Not enough consecutive Oct13 targets")
    gaps=sorted(set(range(extra[0]["id"],extra[-1]["id"]+1))-
                {row["id"] for row in extra})
    return full_dates[:72],rows+uninterrupted,len(uninterrupted),len(extra),gaps,issues,malformed

def labels(prefix,tt,n):
    rankids=np.arange(80,dtype=int)
    current=np.empty((len(tt),80),dtype=np.uint8)
    older=np.empty((len(tt),80),dtype=np.uint8)
    for j,t in enumerate(tt):
        current[j]=fixed_quintiles(prefix,int(t),n,rankids)
        older[j]=fixed_quintiles(prefix,int(t)-LAG,n,rankids)
    return current,older

def tiebreaks(ntest):
    """Same common seeded ties for BOTH N, reproducing V74/V75."""
    rng=np.random.default_rng(SEED)
    tb=rng.random((V74_STEPS+ntest,80))
    return tb

def one_model(prefix,draws,tie,n,ntest):
    tra=np.arange(EARLY,TRAIN_END,dtype=int)
    trcur,trprev=labels(prefix,tra,n)
    trstates=states_of(trcur,trprev,KIND)
    trhit=np.zeros((TRAIN_LEN,80),dtype=np.uint8)
    for j,t in enumerate(tra):
        trhit[j,np.asarray(draws[t]["nums"],dtype=int)-1]=1
    probabilities,count,hit=posteriors(trstates,trhit,KIND,STRENGTH)
    assert count.sum()==TRAIN_LEN*80
    result={}
    for stage,t0,t1 in (
       ("TRAIN",EARLY,TRAIN_END),
       ("VALIDATE",TRAIN_END,VAL_END),
       ("HOLDOUT",VAL_END,HOLD_END),
       ("NEXT_DAY",HOLD_END,HOLD_END+ntest)):
        tvals=np.arange(t0,t1,dtype=int)
        cur,old=labels(prefix,tvals,n)
        state=states_of(cur,old,KIND)
        actual=np.zeros((len(tvals),80),dtype=np.uint8)
        for j,t in enumerate(tvals):
            actual[j,np.asarray(draws[t]["nums"],dtype=int)-1]=1
        seeds=tie[tvals-EARLY]
        chosen=selection(cur,state,probabilities,seeds)
        control=selection(cur,cur,np.ones(5)*.25,seeds)
        paired,ah,bh=paired_p(chosen,control,actual)
        result[stage]=dict(tvals=tvals,cur=cur,old=old,states=state,
             y=actual,selected=chosen,control=control,
             model_hits=ah,control_hits=bh,paired=paired,
             mu_model=float(ah.mean()),mu_control=float(bh.mean()),
             p_fair=fair_p(int(ah.sum()),len(tvals)))
        assert int(chosen.sum())==20*len(tvals)
    return probabilities,count,hit,result

def calc_paired(a,b,y):
    """Compare two frozen 20-subsets on IDENTICAL target draws."""
    m=np.minimum(20,20-(a*b).sum(axis=1))
    diffs=(a*y).sum(axis=1).astype(np.int16)-(b*y).sum(axis=1).astype(np.int16)
    var=float(np.sum(2*m*.25*.75*80/79))
    z=float(diffs.sum())/math.sqrt(var) if var>0 else 0.0
    return dict(number_draws=len(diffs),
      mean_n60_minus_n42=round(float(diffs.mean()),7),
      total_difference=int(diffs.sum()),
      paired_z=round(z,7),
      p_two_sided=round(math.erfc(abs(z)/math.sqrt(2)),7),
      p_n60_higher_one_sided=round(.5*math.erfc(z/math.sqrt(2)),7),
      theoretical_null_sd_total=round(math.sqrt(var),6),
      total_mismatched_per_draw=int(m.sum()))

def write_csv(z,path,rows,headers=None):
    if headers is None:
        if not rows:raise ValueError(path)
        headers=list(rows[0])
    with z.open(path,"w",force_zip64=True) as raw:
        stream=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        w=csv.DictWriter(stream,fieldnames=headers)
        w.writeheader();w.writerows(rows)
        stream.flush();stream.detach()

def run(source,out):
    dates,draws,ntest,npartial,missing,issues,malformed=load(source)
    print(f"V76 42/12 versus 60/12; TRAIN 3255, VAL 3255,"
          f" HOLDOUT 3255; 13Oct consecutive {ntest} of {npartial};"
          f" gaps={missing}",flush=True)
    prefix=prefixify(draws)
    tie=tiebreaks(ntest)
    models={}
    for n in N_VALUES:
        models[n]=one_model(prefix,draws,tie,n,ntest)
        print(f"V76 finished N={n}",flush=True)
    rows_summary=[]
    rows_day=[]
    sample_13=[]
    number_13=[]
    learned=[]
    cells=[]
    pairwise_results={}
    for stage in STAGE_STARTS:
        d42=models[42][3][stage]
        d60=models[60][3][stage]
        match=calc_paired(d60["selected"],d42["selected"],d42["y"])
        pairwise_results[stage]=match
        for n in N_VALUES:
            p,ct,hi,v=models[n]
            a=v[stage]
            h=a["model_hits"];baseline=a["control_hits"]
            rows_summary.append(dict(stage=stage,ref_n=n,lag=LAG,kind=KIND,
              shrink=STRENGTH,target_draws=len(h),
              total_hits=int(h.sum()),model_mean=round(float(h.mean()),7),
              balanced_random_mean=round(float(baseline.mean()),7),
              model_minus_random=round(float(h.mean()-baseline.mean()),7),
              fair_expected_mean=5.,fair_upper_p=a["p_fair"],
              paired_control_p=a["paired"]["paired_one_sided_p"],
              seven_plus=int((h>=7).sum()),eight_plus=int((h>=8).sum()),
              nine_plus=int((h>=9).sum()),ten_plus=int((h>=10).sum()),
              model20_complete=int((h==20).sum()),
              n60_vs_n42_difference=match["mean_n60_minus_n42"],
              n60_vs_n42_p_two_sided=match["p_two_sided"]))
            for dayindex in range(0,len(h),DAY_SIZE):
                day_h=h[dayindex:dayindex+DAY_SIZE]
                day_b=baseline[dayindex:dayindex+DAY_SIZE]
                idx=int(a["tvals"][dayindex])
                rows_day.append(dict(stage=stage,ref_n=n,
                   day=draws[idx]["day"],draw_count=len(day_h),
                   model_avg=round(float(day_h.mean()),6),
                   control_avg=round(float(day_b.mean()),6),
                   model_7plus=int((day_h>=7).sum()),
                   model_8plus=int((day_h>=8).sum()),
                   model_9plus=int((day_h>=9).sum())))
    for n in N_VALUES:
        prob,count,hits,data=models[n]
        for j in range(15):
            learned.append(dict(ref_n=n,
                current_heat=TIERS[j//3],
                movement=("COOLING","STEADY","RISING")[j%3],
                train_opportunities=int(count[j]),train_hits=int(hits[j]),
                trained_probability=round(float(prob[j]),9)))
        for stage in ("HOLDOUT","NEXT_DAY"):
            a=data[stage]
            for q in range(5):
                for r in range(3):
                    move=np.where(a["cur"]>a["old"],2,
                                  np.where(a["cur"]<a["old"],0,1))
                    mask=(a["cur"]==q)&(move==r)
                    elig=int(mask.sum())
                    n_hits=int(a["y"][mask].sum())
                    cells.append(dict(stage=stage,ref_n=n,
                      heat=TIERS[q],movement=("COOLING","STEADY","RISING")[r],
                      opportunities=elig,target_hits=n_hits,
                      target_percent=round(100*n_hits/elig,6) if elig else None))
        nextday=data["NEXT_DAY"]
        for j,t in enumerate(nextday["tvals"]):
            row=draws[int(t)]
            cur=nextday["cur"][j];prev=nextday["old"][j]
            selection_mask=nextday["selected"][j]
            true=nextday["y"][j]
            chosen=[int(b)+1 for b in np.flatnonzero(selection_mask)]
            rs=dict(ref_n=n,date=row["day"],draw_id=row["id"],
              clock=row["time"],day_slot=row["pos"],
              selected20=",".join(map(str,chosen)),
              hits=int(nextday["model_hits"][j]),
              balanced_random_hits=int(nextday["control_hits"][j]),
              hit_numbers=",".join(map(str,np.flatnonzero(selection_mask&true)+1)))
            for k in range(5):
                rs[f"pool_{TIERS[k].lower()}"]=",".join(
                    map(str,np.flatnonzero(selection_mask&(cur==k))+1))
            sample_13.append(rs)
            for b in range(80):
                state=int(nextday["states"][j,b])
                number_13.append(dict(ref_n=n,draw_id=row["id"],
                  ball=b+1,past_heat=TIERS[int(prev[b])],
                  current_heat=TIERS[int(cur[b])],
                  heat_delta=int(cur[b])-int(prev[b]),
                  trained_p=round(float(prob[state]),7),
                  selected=int(selection_mask[b]),target_hit=int(true[b])))
    recap=[
       "V76 — 60 CEKILIS REFERANSI 42 ILE AYNI KURALDA KARSILASTIRILDI",
       "Goal: take four numbered ball identities from each of five 16-ball hot/cold pools.",
       "Frozen V74 5x3 movement method: lag=12, shrinkage=250, fair 25% prior.",
       "The only intentionally changed parameter is heat reference N=42 vs N=60.",
       "Training only 29 Aug–12 Sep, 3255 draws, separately fitted 42 and 60 probabilities.",
       "Validating 13–27 September 3255; holdout 28 Sep–12 Oct 3255.",
       f"Next day October13 {ntest} consecutive records until first gap (from {npartial} present).",
       f"Missing IDs {missing} mean later 13 Oct targets cannot be used as unbroken N-history.",
       "Every target's candidate set was computed strictly from previous draws.",
       "",
       "AVERAGE 20-POOL HITS (FAIR EXPECTED 5.00000):"]
    for stage in STAGE_STARTS:
        line42=next(row for row in rows_summary if row["stage"]==stage and row["ref_n"]==42)
        line60=next(row for row in rows_summary if row["stage"]==stage and row["ref_n"]==60)
        z=pairwise_results[stage]
        recap.append(f"{stage:8}: #draws={line42['target_draws']}; "
          f"N42={line42['model_mean']:.5f} (control={line42['balanced_random_mean']:.5f}); "
          f"N60={line60['model_mean']:.5f} (control={line60['balanced_random_mean']:.5f}); "
          f"Delta60-42={z['mean_n60_minus_n42']:+.5f}, "
          f"paired two-sided p={z['p_two_sided']:.6f}.")
    recap+=["",
        "NEXT-DAY DETAILS:",
    ]
    for n in N_VALUES:
        v=next(r for r in rows_summary if r["stage"]=="NEXT_DAY" and r["ref_n"]==n)
        recap.append(f"N={n} expected=5; model={v['model_mean']:.5f}, control={v['balanced_random_mean']:.5f}, "
                     f"fair-p(one sided)={v['fair_upper_p']:.5f}, "
                     f"7+={v['seven_plus']},8+={v['eight_plus']},9+={v['nine_plus']},10+={v['ten_plus']}")
    recap+=["",
      "INTERPRETATION:",
      "Compare HOLDOUT and NEXT_DAY; never pick a winner only because one split scored higher.",
      "N=60 is a user-specified candidate, NOT the result of an optimized N-search.",
      "The first 12 October focus and October13 data have been previously examined;",
      "even if chosen parameters were locked, this is retrospective replay not new prospective evidence.",
      "Multiple prior V68–V75 research iterations can inflate the chance of small p-values.",
      "Do not change any further parameter based on target outcomes before a genuine future test.",
      "A temperature reference does not physically rebalance an independent lottery RNG.",
      ""]
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        z.writestr("00_ANA_SONUC_V76.txt","\n".join(recap))
        write_csv(z,"01_42_60_EGITIM_VALIDASYON_TEST_13EKIM.csv",rows_summary)
        write_csv(z,"02_HER_GUN_42_VE_60_ISABET_KARSILASTIRMA.csv",rows_day)
        write_csv(z,"03_13EKIM_42_VE_60_TAM_20_SAYI_ISABET.csv",sample_13)
        write_csv(z,"04_13EKIM_TUM_42_VE_60_HAVUZ_KIMLIK_YON.csv",number_13)
        write_csv(z,"05_42_60_OGRENILMIS_5x3_DURUM_ORANLARI.csv",learned)
        write_csv(z,"06_HOLDOUT_VE_13EKIM_HAVUZ_YON_25_ORAN.csv",cells)
        z.writestr("07_KURAL_KANITLARI.txt","\n".join([
          "Parameters lag=12 DIRECTION15 shrink=250 kept identically across N=42,60.",
          "One change tested: only last N draw count determining quintile identity.",
          "The 15-day training rates for each N only use outcomes before 13 Sep.",
          "Each 20-set has exactly four selected from each of five 16-number bins.",
          "Same random seeded tie-breaking (V74/V75) across N and evaluation dates.",
          "Every target history rolling excludes target, so no forward data leakage.",
          "Paired N60 vs N42 null uses weighted overlap-based conditional variance.",
          "Independent fair RNG expected 5 of 20 for any 20 candidate identities.",
          "132 total next-day 13 Oct metadata? Only first uninterrupted 112 draws are used.",
          "13 October missing ids #61958 and #61972; all later excluded.",
          "This data was already previously investigated, NOT prospective proof.",
          "Further holdout days after model freeze must be genuinely unseen."
        ])+"\n")
        z.writestr("08_AUDIT.json",json.dumps(dict(version=VERSION,
          reference_Ns=N_VALUES,lag=LAG,kind=KIND,shrink=STRENGTH,
          train_dates=dates[27:42],validation_dates=dates[42:57],
          holdout_dates=dates[57:72],first_oct13_id=61846,
          oct13_available_count=npartial,oct13_used_count=ntest,
          oct13_missing_ids=missing,results=rows_summary,
          model_comparison_paired=pairwise_results,parse_issues=issues[:15],
          malformed=malformed[:15]),indent=2,ensure_ascii=False))
    print("\n".join(recap),flush=True)
    print("V76 ZIP",out,out.stat().st_size,flush=True)

def selftest():
    assert N_VALUES==(42,60) and LAG==12 and KIND=="DIRECTION15" and STRENGTH==250
    assert HOLD_END==72*217 and V74_STEPS==9765
    assert fair_p(500,100)>.4
    a=np.zeros((2,80),dtype=np.uint8)
    b=a.copy()
    for t in range(2):
        a[t,t:t+20]=1
        b[t,t+2:t+22]=1
    y=np.zeros_like(a);y[:,10:30]=1
    test=calc_paired(a,b,y)
    assert test["number_draws"]==2
    print("V76 SELFTEST OK",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",default="veri.txt")
    parser.add_argument("--out",default="v76_output/V76_42_VS_60_REFERANS_12_YON_SABIT_5x4_20LI.zip")
    parser.add_argument("--selftest",action="store_true")
    args=parser.parse_args()
    if args.selftest:selftest()
    else:run(args.source,args.out)
