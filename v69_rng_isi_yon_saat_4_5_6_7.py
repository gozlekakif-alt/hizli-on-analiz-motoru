#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V69 — heat/direction pool calibration and exact 4/5/6/7 appearances per hour.

FIRST: prior 71 complete days train features, 72nd complete day is assessed
sequentially, using its targets ONLY after predictions are frozen.
An hour contains 12 five-minute draws; 01:02 singleton is NOT a full hour.
SIMULATED NULL: 20 of 80 drawn independently each time, without replacement
within a draw, never injecting future target values into candidate selection.
H6 predictor forecasts the FULL hour after 6 draws are known and is kept
entirely distinct from pre-hour forecasts.
Previously explored data makes this a retrospective exploratory audit, not
a genuine new out-of-sample validation of lottery forecasting.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
import random
import statistics
import zipfile
from collections import Counter
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

SEED=691015
VERSION="V69.1"
HOUR_STARTS=(0,)+tuple(13+12*i for i in range(17))
N_SIMS=1000
K_VALUES=(4,5,6,7)
PRE_METHODS=("HOT72","HEAT_TREND","COLD72","RANDOM")
POST_METHODS=("H6_MATH","H6_MATH_HEAT")
STATES=("SOGUK","SERIN","NOTR","ILIK","SICAK")
DIRECTIONS=("SOGUYOR","SABIT","ISINIYOR")
BOUNDS=(14,16,19,21)
INDEX=np.arange(80,dtype=int)
CANDIDATES={
    k:round(80*math.comb(12,k)*(.25**k)*(.75**(12-k)))
    for k in K_VALUES
}
MKEYS=tuple((method,k) for method in PRE_METHODS+POST_METHODS
            for k in K_VALUES)
EXPECTED_K={k:math.comb(12,k)*(.25**k)*(.75**(12-k))
            for k in K_VALUES}

def random_seed(*parts):
    raw=("V69|"+"|".join(map(str,parts))).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8],"big")

def eligible_data(file):
    records,issues,malformed=parse_txt(file)
    valid=sorted(d for d,rows in records.items()
          if len(rows)==217 and [r["pos"] for r in rows]==list(range(1,218)))
    if len(valid)<72:raise ValueError(f"Need 72 complete days, found {len(valid)}")
    focus=valid[71]
    past=[r for d in valid[:71] for r in records[d]]
    assert len(past)==71*217 and len(records[focus])==217
    partial={d:len(v) for d,v in records.items() if d not in valid}
    return focus,past,records[focus],valid[:71],partial,issues,malformed

def bin_count(rows):
    c=np.zeros(80,dtype=np.int16)
    for row in rows:
        nums=row["nums"] if isinstance(row,dict) else row
        c[np.asarray(nums,dtype=int)-1]+=1
    return c

class Rolling:
    def __init__(self,initial72):
        if len(initial72)!=72:raise ValueError("Needs 72 historical draws")
        self.window=[np.asarray(r["nums"] if isinstance(r,dict) else r,dtype=np.int16)-1 for r in initial72]
        self.c72=bin_count(initial72)
        self.prev24=bin_count(initial72[-48:-24])
        self.late24=bin_count(initial72[-24:])
        assert int(self.c72.sum())==72*20
        assert int(self.prev24.sum())==24*20 and int(self.late24.sum())==24*20

    def features(self):
        trend=self.late24-self.prev24
        heat=self.c72.astype(float)+0.60*trend
        cat=np.searchsorted(BOUNDS,np.asarray(self.c72),side="left")
        dirs=(np.sign(trend)+1).astype(int)
        return heat,cat,dirs,trend

    def append(self,nums):
        new=np.asarray(nums,dtype=np.int16)-1
        if len(new)!=20 or len(set(new))!=20:raise ValueError("Bad draw")
        old72,old48,old24=self.window[0],self.window[24],self.window[48]
        self.c72[old72]-=1;self.c72[new]+=1
        self.prev24[old48]-=1;self.prev24[old24]+=1
        self.late24[old24]-=1;self.late24[new]+=1
        self.window.pop(0);self.window.append(new)

    def check(self):
        assert np.array_equal(self.c72,bin_count([x+1 for x in self.window]))
        assert np.array_equal(self.prev24,bin_count([x+1 for x in self.window[-48:-24]]))
        assert np.array_equal(self.late24,bin_count([x+1 for x in self.window[-24:]]))

def ranking(score):
    # numerical lower-number tie-break, independent of target
    return np.lexsort((INDEX,-np.asarray(score,dtype=float)))

def weighted_ticket(raw,rank,k):
    return set(int(x) for x in rank[:CANDIDATES[k]])

def post_math_likelihood(c6,k):
    remain=np.asarray(k-c6,dtype=int)
    out=np.zeros(80,dtype=float)
    for n in range(80):
        if 0<=remain[n]<=6:
            j=int(remain[n])
            out[n]=math.comb(6,j)*.25**j*.75**(6-j)
    return out

def evaluate(initial72,target,details=False):
    if len(target)!=217:raise ValueError("full day required")
    roll=Rolling(initial72)
    state_den=np.zeros((5,3),dtype=np.int64)
    state_hits=np.zeros((5,3),dtype=np.int64)
    exact_total=np.zeros(13,dtype=np.int64)
    scores={key:0 for key in MKEYS}
    hour_rows=[];forecast_rows=[];per_draw=[];state_numrows=[]
    current={}
    start_set=set(HOUR_STARTS)
    for index,draw in enumerate(target):
        nums=draw["nums"] if isinstance(draw,dict) else draw
        drawn=np.asarray(nums,dtype=int)-1
        actual=np.zeros(80,dtype=np.int8);actual[drawn]=1
        heat,cat,dirs,trend=roll.features()
        g=(cat*3+dirs).astype(int)
        state_den+=np.bincount(g,minlength=15).reshape(5,3)
        state_hits+=np.bincount(g,weights=actual,minlength=15).reshape(5,3).astype(int)
        if details:
            for s in range(5):
                for d in range(3):
                    mask=(cat==s)&(dirs==d)
                    state_numrows.append(dict(slot=index+1,
                        category=STATES[s],direction=DIRECTIONS[d],
                        candidate_count=int(mask.sum()),
                        target_hits=int(actual[mask].sum())))
            per_draw.append(dict(slot=index+1,
                draw_id=draw.get("id",0) if isinstance(draw,dict) else 0,
                cold_candidates=int((cat==0).sum()),
                cool_candidates=int((cat==1).sum()),
                neutral_candidates=int((cat==2).sum()),
                warm_candidates=int((cat==3).sum()),
                hot_candidates=int((cat==4).sum()),
                cold_hits=int(actual[cat==0].sum()),
                cool_hits=int(actual[cat==1].sum()),
                neutral_hits=int(actual[cat==2].sum()),
                warm_hits=int(actual[cat==3].sum()),
                hot_hits=int(actual[cat==4].sum())))
        if index in start_set:
            assert not current
            hot_rank=ranking(roll.c72)
            trend_rank=ranking(heat)
            cold_rank=ranking(-roll.c72)
            rand_rank=np.asarray(random.Random(random_seed(index,"baseline")).sample(range(80),80))
            frozen=dict(
                HOT72=hot_rank,HEAT_TREND=trend_rank,
                COLD72=cold_rank,RANDOM=rand_rank)
            current=dict(start=index,actuals=[],ranks=frozen,heat=heat.copy(),
                         h6rank={},prior72=roll.c72.copy(),trend=trend.copy())
        if current:
            current["actuals"].append(actual.copy())
            hlen=len(current["actuals"])
            if hlen==6:
                first6=np.asarray(current["actuals"]).sum(axis=0)
                for k in K_VALUES:
                    likelihood=post_math_likelihood(first6,k)
                    mathrank=ranking(likelihood)
                    # Temperature only breaks ties within EXACTLY equal
                    # conditional binomial chance; no overriding stronger p.
                    tiebreak=np.lexsort((INDEX,-current["heat"],-likelihood))
                    current["h6rank"][("H6_MATH",k)]=mathrank
                    current["h6rank"][("H6_MATH_HEAT",k)]=tiebreak
            if hlen==12:
                counts=np.asarray(current["actuals"]).sum(axis=0)
                exact_total+=np.bincount(counts.astype(int),minlength=13)
                if details:
                    hour_rows.append(dict(hour_start_slot=current["start"]+1,
                        hour_end_slot=index+1,at_least4=int((counts>=4).sum()),
                        **{"exact_"+str(k):int((counts==k).sum()) for k in range(13)},
                        hot72_top15=",".join(str(n+1) for n in current["ranks"]["HOT72"][:15]),
                        trend_top15=",".join(str(n+1) for n in current["ranks"]["HEAT_TREND"][:15])))
                for method in PRE_METHODS+POST_METHODS:
                    for k in K_VALUES:
                        rank=(current["ranks"][method] if method in PRE_METHODS
                              else current["h6rank"][(method,k)])
                        selected=rank[:CANDIDATES[k]]
                        hit=int((counts[selected]==k).sum())
                        scores[(method,k)]+=hit
                        if details:
                            forecast_rows.append(dict(
                                hour_start_slot=current["start"]+1,
                                hour_end_slot=index+1,
                                when=("BEFORE_HOUR" if method in PRE_METHODS else "AFTER_H6"),
                                method=method,exact_k=k,
                                expected_candidate_count=CANDIDATES[k],
                                predicted_numbers=",".join(str(n+1) for n in selected),
                                true_exact_k_numbers=",".join(str(n+1) for n in np.flatnonzero(counts==k)),
                                successful_numbers=",".join(str(n+1) for n in selected if counts[n]==k),
                                true_count=int((counts==k).sum()),
                                hits=hit))
                current={}
        roll.append(nums)
        if index%49==0:roll.check()
    roll.check()
    assert not current
    assert int(state_den.sum())==217*80
    assert int(state_hits.sum())==217*20
    assert int(exact_total.sum())==18*80
    assert int(sum(k*int(v) for k,v in enumerate(exact_total)))==18*12*20
    return dict(state_den=state_den,state_hits=state_hits,
                exact_total=exact_total,scores=scores,
                hour_rows=hour_rows,forecast_rows=forecast_rows,
                per_draw=per_draw,state_numrows=state_numrows)

def null_draw_day(rng):
    return [rng.sample(range(1,81),20) for _ in range(217)]

def p_two_sided_null(observed,null,center=None):
    if center is None:center=float(np.mean(null))
    delta=abs(float(observed)-center)
    return (1+sum(abs(float(v)-center)>=delta-1e-13 for v in null))/(1+len(null))

def p_one_sided_null(observed,null):
    return (1+sum(int(v)>=int(observed) for v in null))/(1+len(null))

def ci95(arr):
    return [float(np.percentile(arr,2.5)),float(np.percentile(arr,97.5))]

def csv_save(z,path,rows,columns=None):
    if not rows and columns is None:raise ValueError("No data "+path)
    columns=columns or list(rows[0])
    with z.open(path,"w",force_zip64=True) as raw:
        stream=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        writer=csv.DictWriter(stream,fieldnames=columns)
        writer.writeheader()
        if rows:writer.writerows(rows)
        stream.flush();stream.detach()

def report(source,out,n_sims):
    focus,early,day,dates,partial,issues,malformed=eligible_data(source)
    initial72=early[-72:]
    print(f"V69 focus {focus}, 71 previous full days={len(early)} drawings; testing 217, hours=18",flush=True)
    obs=evaluate(initial72,day,details=True)
    rates={}
    for s in range(5):
        n=int(obs["state_den"][s].sum());h=int(obs["state_hits"][s].sum())
        rates[s]=(h/n if n else float("nan"))
    rng=random.Random(SEED)
    sim_rates=np.empty((n_sims,5),dtype=float)
    sim_scores={key:np.empty(n_sims,dtype=np.int16) for key in MKEYS}
    sim_exact=np.empty((n_sims,13),dtype=np.int16)
    for b in range(n_sims):
        simulated=evaluate(initial72,null_draw_day(rng))
        for s in range(5):
            d=int(simulated["state_den"][s].sum())
            sim_rates[b,s]=float(simulated["state_hits"][s].sum())/d if d else float("nan")
        for key in MKEYS:sim_scores[key][b]=simulated["scores"][key]
        sim_exact[b]=simulated["exact_total"]
        if (b+1)%200==0:
            print(f"V69 null simulation {b+1}/{n_sims}",flush=True)
    rows_state=[]
    for s in range(5):
        den=int(obs["state_den"][s].sum())
        hits=int(obs["state_hits"][s].sum())
        r=rates[s]
        vals=sim_rates[:,s]
        rows_state.append(dict(state=STATES[s],number_draw_opportunities=den,
          observed_hits=hits,observed_rate=round(r,7),fair_rate=0.25,
          observed_minus_25pp=round(100*(r-.25),5),
          null_mean=round(float(np.mean(vals)),7),
          null_95_low=round(float(np.percentile(vals,2.5)),7),
          null_95_high=round(float(np.percentile(vals,97.5)),7),
          empirical_two_sided_p=round(p_two_sided_null(r,vals),5)))
    rows_direction=[]
    for s in range(5):
        for d in range(3):
            count=int(obs["state_den"][s,d]);hits=int(obs["state_hits"][s,d])
            rows_direction.append(dict(state=STATES[s],
               direction=DIRECTIONS[d],eligible_number_draws=count,
               observed_hits=hits,observed_rate=round(hits/count,7) if count else None,
               expected_hits=round(count*.25,3)))
    rows_hour=[]
    for k in range(13):
        obs_count=int(obs["exact_total"][k])
        p=math.comb(12,k)*(.25**k)*(.75**(12-k))
        c=sim_exact[:,k]
        rows_hour.append(dict(exact_appearance_count=k,
            per_number_hour_prob=round(p,9),
            fair_expected_number_hours=round(1440*p,3),
            observed_number_hours=obs_count,
            mean_per_hour=round(obs_count/18,5),
            null_mean=round(float(np.mean(c)),5),
            null_95_low=round(float(np.percentile(c,2.5)),3),
            null_95_high=round(float(np.percentile(c,97.5)),3),
            empirical_two_sided_p=round(p_two_sided_null(obs_count,c),5)))
    rows_predict=[]
    for method,k in MKEYS:
        count=int(obs["scores"][(method,k)])
        eligible=18*CANDIDATES[k]
        vals=sim_scores[(method,k)]
        rows_predict.append(dict(
            method=method,when="BEFORE_HOUR" if method in PRE_METHODS else "AFTER_H6",
            exact_appearances=k,predicted_numbers_per_hour=CANDIDATES[k],
            predicted_number_hours=eligible,correct_number_hours=count,
            prediction_precision=round(count/eligible,6),
            all_hour_true_count=int(obs["exact_total"][k]),
            recall=round(count/int(obs["exact_total"][k]),6) if int(obs["exact_total"][k]) else 0,
            fair_pre_hour_expected=round(eligible*EXPECTED_K[k],5),
            null_mean=round(float(np.mean(vals)),5),
            null_95_low=round(float(np.percentile(vals,2.5)),3),
            null_95_high=round(float(np.percentile(vals,97.5)),3),
            null_one_sided_p=round(p_one_sided_null(count,vals),5)))
    # Joint family-wise null uses the largest standardised upward
    # departure over 4 methods x 4 exact count categories.
    prekeys=tuple((m,k) for m in PRE_METHODS for k in K_VALUES)
    mu={key:float(np.mean(sim_scores[key])) for key in prekeys}
    sigma={key:max(1e-9,float(np.std(sim_scores[key]))) for key in prekeys}
    maxobs=max((obs["scores"][key]-mu[key])/sigma[key] for key in prekeys)
    maxsim=np.max(np.column_stack(
        [(sim_scores[key]-mu[key])/sigma[key] for key in prekeys]),axis=1)
    familywise_p=p_one_sided_null(maxobs,maxsim)
    # Pooled total across 4 exact categories for each method; not
    # independent trials because predictions can contain same numbers.
    totals=[]
    for method in PRE_METHODS+POST_METHODS:
        observed=sum(obs["scores"][(method,k)] for k in K_VALUES)
        nulltot=sum((sim_scores[(method,k)] for k in K_VALUES))
        totals.append(dict(method=method,
          when="BEFORE_HOUR" if method in PRE_METHODS else "AFTER_H6",
          observed_total_exact_hits=int(observed),
          null_mean=round(float(np.mean(nulltot)),4),
          null_95_low=round(float(np.percentile(nulltot,2.5)),3),
          null_95_high=round(float(np.percentile(nulltot,97.5)),3),
          empirical_one_sided_p=round(p_one_sided_null(observed,nulltot),5)))
    # Pairwise difference conditions on the identical simulated draws.
    paired=[]
    for method in ("HOT72","HEAT_TREND","COLD72"):
        for k in K_VALUES:
            obs_diff=obs["scores"][(method,k)]-obs["scores"][("RANDOM",k)]
            nulldiff=sim_scores[(method,k)]-sim_scores[("RANDOM",k)]
            paired.append(dict(when="BEFORE_HOUR",method=method,exact_k=k,
             observed_gain_over_random=int(obs_diff),
             null_mean_gain=round(float(np.mean(nulldiff)),5),
             null_diff_95_low=round(float(np.percentile(nulldiff,2.5)),3),
             null_diff_95_high=round(float(np.percentile(nulldiff,97.5)),3),
             null_one_sided_p=round(p_one_sided_null(obs_diff,nulldiff),5)))
    for k in K_VALUES:
        o=obs["scores"][("H6_MATH_HEAT",k)]-obs["scores"][("H6_MATH",k)]
        v=sim_scores[("H6_MATH_HEAT",k)]-sim_scores[("H6_MATH",k)]
        paired.append(dict(when="AFTER_H6",method="H6_MATH_HEAT",exact_k=k,
            observed_gain_over_random=int(o),null_mean_gain=round(float(np.mean(v)),5),
            null_diff_95_low=round(float(np.percentile(v,2.5)),3),
            null_diff_95_high=round(float(np.percentile(v,97.5)),3),
            null_one_sided_p=round(p_one_sided_null(o,v),5)))
    headline=[
       f"V69: 80 SAYI / 217 CEKILIS / 18 TAM SAAT | {focus}",
       f"History: {len(dates)} complete days = {len(early)} past draws",
       f"Test focus: {day[0]['id']} -> {day[-1]['id']}; tests={len(day)}; hours=18",
       f"RNG null: {n_sims} simulated independent full DAYS (each draw exactly 20 different from 80).",
       "",
       "EVERY DRAW: LAST72 TEMPERATURE POOL APPEARANCE RATES (fair expectation 25%):"]
    for v in rows_state:
        headline.append(f"{v['state']:7} {v['observed_hits']}/{v['number_draw_opportunities']} = {100*v['observed_rate']:.3f}% "
           f"(null 95% {100*v['null_95_low']:.2f}-{100*v['null_95_high']:.2f}%, two-sided p={v['empirical_two_sided_p']})")
    headline+=["","PER 12-DRAW FULL HOUR — expected EXACT appearances per 80 numbers:"]
    for k in K_VALUES:
        v=rows_hour[k]
        headline.append(f"exact{k}: expected {80*EXPECTED_K[k]:.3f}/hour, observed {v['observed_number_hours']}/18h="
                        f"{v['mean_per_hour']:.3f}/hour, pre-hour candidate count={CANDIDATES[k]}")
    headline+=["","BEFORE THE HOUR: exact 4/5/6/7 count successes over 18 full hours:"]
    for v in totals:
        if v["when"]=="BEFORE_HOUR":
            headline.append(f"{v['method']:12} exact-slot successes={v['observed_total_exact_hits']}, "
                        f"null mean={v['null_mean']}, null95={v['null_95_low']}-{v['null_95_high']}, "
                        f"p={v['empirical_one_sided_p']}")
    headline.append(f"Conservative 16-way max-score correction p={familywise_p:.5f} (4 methods x 4 counts).")
    headline+=["","AFTER FIRST 6 DRAWS (forecast FINAL hourly count 4/5/6/7, not pre-hour!):"]
    for v in totals:
        if v["when"]=="AFTER_H6":
            headline.append(f"{v['method']:14} exact-slot successes={v['observed_total_exact_hits']}, "
                        f"null mean={v['null_mean']}, null95={v['null_95_low']}-{v['null_95_high']}, "
                        f"p={v['empirical_one_sided_p']}")
    headline+=["",
       "Mechanically, the first 6 known draws improve knowledge of the final hourly count.",
       "This does not imply the unseen next six draws are predictable beyond independent RNG.",
       "No claimed forecasting superiority without fresh, genuinely prospective confirmation.",
       "All candidate lists were frozen PRIOR to their target outcomes.",
       "Full audit tables, per-hour number lists, and 217-step pool counts in single ZIP.",
       ""]
    out=Path(out);out.parent.mkdir(exist_ok=True,parents=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        z.writestr("00_ANA_KARAR_V69.txt","\n".join(headline))
        csv_save(z,"01_BES_ISI_HAVUZU_GERCEK_VS_SIM.csv",rows_state)
        csv_save(z,"02_5_HAVUZ_X_3_YON_RAPOR.csv",rows_direction)
        csv_save(z,"03_12_CEKILISTE_TAM_0DAN12YE_SAYILAR.csv",rows_hour)
        csv_save(z,"04_SAAT_4_5_6_7_ONCEDEN_TAHMIN_SONUCLARI.csv",rows_predict)
        csv_save(z,"05_4_5_6_7_TOPLAM_TAHMIN_KARSILASTIRMA.csv",totals)
        csv_save(z,"06_SICAKLIK_VS_RASTGELE_ESLESMELI.csv",paired)
        csv_save(z,"07_18_SAATIN_GERCEK_0DAN12YE_SAYIMI.csv",obs["hour_rows"])
        csv_save(z,"08_18_SAAT_4_5_6_7_HANGI_SAYILAR_TAHMIN_VE_ISABET.csv",obs["forecast_rows"])
        csv_save(z,"09_217_CEKILISIN_HAVUZ_KOTALARI.csv",obs["per_draw"])
        csv_save(z,"10_217_CEKILIS_X_5_HAVUZ_X_3_YON.csv",obs["state_numrows"])
        z.writestr("11_KURAL_DENETIMI.txt","\n".join([
            "Data: 71 complete earlier days for context, exact 217 focus draws.",
            "At every target draw: last72 counts, last24 minus prior24 direction, no target used.",
            "Categories V42: COLD<=14, COOL15-16, NEUTRAL17-19, WARM20-21, HOT>=22.",
            "State direction sign = sign(last24 minus prior24), 5x3 lanes.",
            "Hour starts: slot1 (00:02), and slot14/26/.../206 (07:02..23:02).",
            "Slot13 at 01:02 is singleton, NOT a full 12-draw hour.",
            "Pre-hour methods HOT72, HEAT_TREND=c72+.6*(last24-prev24), COLD72, seeded RANDOM.",
            "Before each full hour, choose rounded(80 * Binomial(12,.25).pmf(k)) numbers for exact k=4,5,6,7.",
            "Counts per hour: " + repr(CANDIDATES),
            "Pre-hour prediction tests next TWELVE draws using no hour outcomes.",
            "After six observed draws, H6_MATH calculates Binomial(6,.25) probability of remaining (k-c6) draws.",
            "H6_MATH_HEAT only uses pre-hour heat to break EXACT conditional-probability ties.",
            "H6 predictions estimate complete 12-draw counts after first 6 became known.",
            "Simulation null independently draws exactly 20 unique balls each draw; 217 full-day streams,",
            "same real last72 at simulation start, feature histories update with synthetic results.",
            "1,000 or user-defined simulations, one-sided p for forecast success, two-sided for hot pool rates.",
            "Conservative max-stat correction spans 4 pre-hour models x 4 count classes.",
            "All 72 focus-day historic data was previously examined, so exploratory, not new-data prospective.",
            "No ability to infer proprietary RNG source code or seed from these data."
        ])+"\n")
        z.writestr("12_AUDIT.json",json.dumps(dict(version=VERSION,focus=focus,
          previous_days=dates,previous_draws=len(early),test_draws=len(day),
          full_hour_count=len(HOUR_STARTS),full_hour_starts_1based=[x+1 for x in HOUR_STARTS],
          hour_candidate_counts=CANDIDATES,prior_probability=EXPECTED_K,
          trials=n_sims,sim_seed=SEED,
          state_rows=rows_state,prediction_totals=totals,
          familywise_p_max_16=familywise_p,
          parse_issues=issues[:20],bad_lines=malformed[:20],partial_days=partial),
          indent=2,ensure_ascii=False))
    print("\n".join(headline),flush=True)
    print("ZIP",str(out),out.stat().st_size,flush=True)
    return headline

def selftest():
    # 72 synthetic draws constructed from a shifting 20-ball window.
    d=[tuple(sorted(((i+j)%80)+1 for j in range(20))) for i in range(72)]
    roll=Rolling(d);roll.check()
    for i in range(115):
        nums=tuple(sorted(((i+j+3)%80)+1 for j in range(20)))
        roll.append(nums)
        roll.check()
    assert len(HOUR_STARTS)==18 and HOUR_STARTS[0]==0 and HOUR_STARTS[-1]==205
    assert CANDIDATES=={4:15,5:8,6:3,7:1}
    assert abs(sum(math.comb(12,k)*.25**k*.75**(12-k) for k in range(13))-1)<1e-10
    p=post_math_likelihood(np.zeros(80,dtype=int),4)
    assert all(v>0 for v in p)
    test=evaluate(d,[d[i%72] for i in range(217)])
    assert sum(test["scores"].values())>=0
    assert int(test["state_den"].sum())==217*80
    print("V69 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v69_output/V69_RNG_ISI_YON_SAAT_4_5_6_7_KOR_TEST.zip")
    p.add_argument("--sims",type=int,default=N_SIMS)
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:selftest()
    else:
        if not 1<=a.sims<=100000:raise ValueError("sims must be positive")
        report(a.source,a.out,a.sims)
