#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V66: Day 72 first 20-number draw vs the PRECEDING 71 complete days.

For all 2..10 subsets of these twenty numbers, count appearances IN THE SAME
historical draw. The first draw of day 72 is a reference/anchor, NEVER
part of historical counts. The subsequent 216 draws of day 72 serve as
an untouched time-ordered descriptive check. Not lottery advice.
"""
from __future__ import annotations
import argparse,csv,heapq,io,json,math,statistics,zipfile
from collections import Counter
from datetime import date
from itertools import combinations
from math import comb
from pathlib import Path
from v52_ayni_cekilis_eslikci_217 import parse_txt

K_EXPORT=range(2,11)
N_BITS=20
N_MASKS=1<<20
P_PAIR=comb(20,2)/comb(80,2)
P_CONDITIONAL=19/79

def prior_full_day_rows(source):
    full,issues,bad=parse_txt(source)
    valid=sorted(d for d,v in full.items()
                 if len(v)==217 and [r["pos"] for r in v]==list(range(1,218)))
    if len(valid)<72:
        raise ValueError(f"Need 72 complete days; only {len(valid)} available")
    prev=valid[:71]
    focus=valid[71]
    history=[r for d in prev for r in full[d]]
    day72=full[focus]
    if len(history)!=71*217:raise AssertionError("History count mismatch")
    anchor=day72[0]
    if anchor["pos"]!=1:raise AssertionError("First draw is not position 1")
    return prev,focus,history,day72,issues,bad,full

def groups_mask_20(history,base):
    """Subset-frequency superset zeta transform, 2^20 possible subsets."""
    where={n:i for i,n in enumerate(base)}
    histogram=[0]*N_MASKS
    singles=Counter()
    overlap_hist=Counter()
    for draw in history:
        m=0
        for n in draw["nums"]:
            singles[n]+=1
            if n in where:m|=1<<where[n]
        histogram[m]+=1
        overlap_hist[m.bit_count()]+=1
    # histogram[S] becomes the exact number of historical 20-number
    # draws containing ALL members of subset S.
    step=1
    while step<N_MASKS:
        block=step*2
        for start in range(0,N_MASKS,block):
            for offset in range(step):
                histogram[start+offset]+=histogram[start+step+offset]
        step*=2
    if histogram[0]!=len(history):raise AssertionError("Count transform incorrect")
    return histogram,singles,overlap_hist

def group_labels(base,mask):
    return "-".join(str(base[i]) for i in range(N_BITS) if mask>>i&1)

def subset_masks(k):
    for cc in combinations(range(N_BITS),k):
        mask=0
        for bit in cc:mask|=1<<bit
        yield mask

def prob(k,minimum=None):
    if minimum is None:minimum=k
    return sum(comb(k,a)*comb(80-k,20-a)/comb(80,20)
        for a in range(minimum,min(k,20)+1))

def plot_counts(hits,expected):
    return round(hits/expected,5) if expected else None

def priority_groups(freq,base):
    result={}
    for k in K_EXPORT:
        low=heapq.nsmallest(20,subset_masks(k),key=lambda m:(freq[m],m))
        high=heapq.nsmallest(20,subset_masks(k),key=lambda m:(-freq[m],m))
        result[k]=(low,high)
    return result

def future_masks(rows,base):
    where={n:i for i,n in enumerate(base)}
    masks=[]
    for r in rows:
        mask=0
        for n in r["nums"]:
            if n in where:mask|=1<<where[n]
        masks.append((r,mask))
    return masks

def score_frozen(groups,freq,target,base):
    pairs=future_masks(target[1:],base)
    n=len(pairs)
    if n!=216:raise AssertionError("Expected 216 later draws")
    out=[];daily=[]
    for k in K_EXPORT:
        low,high=groups[k]
        weak=freq[low[0]]<freq[high[0]]
        for label,cohort in (("LEAST_PAST_20",low),("MOST_PAST_20",high)):
            exact=0
            near=0
            for mask in cohort:
                exact+=sum((mask&t).bit_count()==k for _,t in pairs)
                near+=sum((mask&t).bit_count()>=max(1,k-2) for _,t in pairs)
            out.append(dict(size=k,source_group=label,families=len(cohort),
                selection_historical_variation=int(weak),future_draws=n,
                total_frozen_family_opportunities=n*len(cohort),
                total_exact_hits=exact,
                fair_exact_hits=round(n*len(cohort)*prob(k),8),
                observed_exact_per_group_draw=round(exact/(n*len(cohort)),9),
                fair_exact_per_group_draw=round(prob(k),9),
                total_near_k_minus_2=near if k>=3 else "",
                expected_near_k_minus_2=round(n*len(cohort)*prob(k,max(1,k-2)),6) if k>=3 else "",
                caution="One same held-out day only; selected groups overlap; no causal or predictive proof"))
    for dr,m in pairs:
        c=m.bit_count()
        daily.append(dict(draw_no=dr["id"],clock=dr["time"],
                 overlap_with_first20=c,overlap_pairs=comb(c,2),
                 overlap_triples=comb(c,3) if c>=3 else 0,
                 first20_repeat_numbers=group_labels(base,m)))
    return out,daily

def csv_file(z,path,header,records):
    with z.open(path,"w",force_zip64=True) as binary:
        f=io.TextIOWrapper(binary,encoding="utf-8",newline="")
        writer=csv.writer(f)
        writer.writerow(header)
        writer.writerows(records)
        f.flush()
        f.detach()

def report(output,prior,focus,history,day72,issues,bad,all_data):
    anchor=day72[0];base=tuple(sorted(anchor["nums"]))
    if len(base)!=20 or len(set(base))!=20:raise AssertionError("Bad target first draw")
    freq,singles,overlap=groups_mask_20(history,base)
    chosen=priority_groups(freq,base)
    forward,forward_rows=score_frozen(chosen,freq,day72,base)
    historical_n=len(history)
    # Distribution of all 2^20-1 subsets, grouped by size.
    stats={k:dict(groups=0,zeros=0,countsum=0,min=historical_n,
                  max=0) for k in range(2,21)}
    for mask in range(1,N_MASKS):
        k=mask.bit_count()
        if k<2:continue
        val=freq[mask];s=stats[k]
        s["groups"]+=1;s["zeros"]+=val==0;s["countsum"]+=val
        if val<s["min"]:s["min"]=val
        if val>s["max"]:s["max"]=val
    bysize=[]
    for k,s in stats.items():
        expected=historical_n*prob(k)
        bysize.append(dict(size=k,possible_groups=s["groups"],
         historical_draws=historical_n,
         theoretical_p_one_draw=prob(k),
         random_expectation_per_fixed_group=expected,
         observed_group_mean=s["countsum"]/s["groups"],
         observed_min=s["min"],observed_max=s["max"],
         zero_groups=s["zeros"],zero_fraction=s["zeros"]/s["groups"]))
    pair_rows=[]
    for a,b in combinations(range(20),2):
        mask=(1<<a)|(1<<b)
        obs=freq[mask]
        pair_rows.append(dict(number_a=base[a],number_b=base[b],
            same_draw_hits=obs,pair_probability_real=obs/historical_n,
            same_draw_expected=historical_n*P_PAIR,
            observed_vs_rng=obs/(historical_n*P_PAIR),
            a_appearances=singles[base[a]],
            b_appearances=singles[base[b]],
            cond_b_given_a=obs/singles[base[a]],
            cond_a_given_b=obs/singles[base[b]],
            rng_conditional_b_given_a=P_CONDITIONAL))
    pair_rows.sort(key=lambda x:(-x["same_draw_hits"],x["number_a"],x["number_b"]))
    rank=[]
    for k in K_EXPORT:
        low,high=chosen[k]
        for direction,masks in (("LOW",low),("HIGH",high)):
            for position,mask in enumerate(masks,1):
                rank.append(dict(size=k,rank=position,tail=direction,
                    members=group_labels(base,mask),historical_same_draw=freq[mask],
                    rng_expected=round(historical_n*prob(k),7),
                    rng_ratio=round(freq[mask]/(historical_n*prob(k)),6)
                    if prob(k)>0 else ""))
    overlap_hist=[]
    for k in range(21):
        pk=comb(20,k)*comb(60,20-k)/comb(80,20)
        overlap_hist.append(dict(overlap=k,history_count=overlap[k],
                history_fraction=overlap[k]/historical_n,
                rng_probability=pk,
                rng_expected=historical_n*pk,
                next216_count=sum(int(d["overlap_with_first20"]==k) for d in forward_rows),
                next216_expected=216*pk))
    top_pairs=pair_rows[:6]
    bottom_pairs=pair_rows[-6:]
    lines=[
      "V66 -- DAY 72 FIRST 20: SAME-DRAW HISTORICAL COAPPEARANCE",
      f"Day72={focus}; first draw #{anchor['id']} at {anchor['time']}; complete prior days={len(prior)};",
      f"Historical prior draws={historical_n}, forward day72 other draws={len(day72)-1}.",
      "TARGET FIRST 20: "+", ".join(map(str,base)),
      "No target-day draws contribute to the historical probability denominators.",
      "Among first20: C(20,2)=190 pairs, C(20,3)=1140 triples.",
      "Definitions: joint means both/all in the SAME 20-of-80 draw.",
      "Pair fair joint p=20*19/(80*79)=0.06012658.",
      "Pair conditional fair p(B|A)=19/79=0.24050633.",
      "Every fixed group's fair full probability=comb(20,k)/comb(80,k).",
      "A group being rare in the past NEVER makes it due next time.",
      "Selecting 20 that have already occurred together is not evidence of predictive skill.",
      "",
      "HISTORICAL SAME-DRAW MIN/MEAN/MAX PER GROUP SIZE:",
    ]
    for x in bysize:
        lines.append(f"k={x['size']}: groups={x['possible_groups']}; "
          f"min={x['observed_min']}; mean={x['observed_group_mean']:.5f}; "
          f"max={x['observed_max']}; expected={x['random_expectation_per_fixed_group']:.5f}; "
          f"zeros={x['zero_groups']}.")
    lines+=["","MOST FREQUENT HISTORICAL PAIRS:"]+[
      f" {x['number_a']}-{x['number_b']}: {x['same_draw_hits']}/{historical_n} "
      f"({x['pair_probability_real']*100:.3f}%)"
      for x in top_pairs]
    lines+=["","LEAST FREQUENT HISTORICAL PAIRS:"]+[
      f" {x['number_a']}-{x['number_b']}: {x['same_draw_hits']}/{historical_n} "
      f"({x['pair_probability_real']*100:.3f}%)"
      for x in sorted(bottom_pairs,key=lambda x:x["same_draw_hits"])]
    lines+=["","DAY 72 LATER 216 DRAWS -- FIRST20 REAPPEARANCES:",
      f"Average first20 overlap per draw={statistics.mean(d['overlap_with_first20'] for d in forward_rows):.4f}, RNG expectation 5.0000",
      f"Average historical overlap per draw={sum(i*overlap[i] for i in range(21))/historical_n:.4f}",
      "", "FROZEN GROUPS - LEAST 20 VS MOST 20 (216 later draws):"]
    for v in forward:
        if v["size"] in (2,3,4,5,7,8,9,10):
            lines.append(f" k={v['size']} {v['source_group']}: exact={v['total_exact_hits']}"
                 f" vs rng expected={v['fair_exact_hits']:.3f}; "
                 f"near(k-2)={v['total_near_k_minus_2']} vs rng={v['expected_near_k_minus_2']}")
    lines+=["","INTERPRETATION: 72nd day was already visible in prior work. "
     "This is descriptive replay, NOT independent confirmation.",
     "The 216 held-out drawings are a SINGLE day, and overlapping groups "
     "are correlated: neither raw highs nor low ranks are betting signals.",
     "Without a new untouched sample and familywise correction there is no "
     "evidence these particular hot/cold pair-group choices predict anything."]
    dest=Path(output);dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_ANA_SONUC_72_GUN_ILK20.txt","\n".join(lines)+"\n")
        csv_file(z,"01_ILK20_190_IKILI_GERCEK_OLASILIKLAR.csv",
            tuple(pair_rows[0]),(tuple(d.values()) for d in pair_rows))
        csv_file(z,"02_K2_K20_TUM_GRUP_BOYUTLARI_OZET.csv",
            tuple(bysize[0]),(tuple(d.values()) for d in bysize))
        csv_file(z,"03_EN_AZ_EN_COK_BIRLIKTE_GORULEN_AILELER.csv",
            tuple(rank[0]),(tuple(d.values()) for d in rank))
        csv_file(z,"04_ILK20_GECMIS_VE_216_CEKILIS_KESISIM_DAGILIM.csv",
            tuple(overlap_hist[0]),(tuple(d.values()) for d in overlap_hist))
        csv_file(z,"05_72_GUN_ILK_CEKILISTEN_SONRA_216_CEKILIS.csv",
            tuple(forward_rows[0]),(tuple(d.values()) for d in forward_rows))
        csv_file(z,"06_72_GUN_ILK20_GECMISTEN_SECILENLERIN_KOR_TESTI.csv",
            tuple(forward[0]),(tuple(d.values()) for d in forward))
        # All 616,645 subsets k=2..10, not just selected best cases.
        header=("size","members","previous_71_days_same_draws",
                "historical_joint_probability","fair_joint_probability",
                "rng_expected_count","observed_over_expected")
        with z.open("07_ILK20_TUM_2_10_GRUPLARI_616645_SATIR.csv","w",force_zip64=True) as raw:
            f=io.TextIOWrapper(raw,encoding="utf-8",newline="")
            writer=csv.writer(f);writer.writerow(header)
            for k in K_EXPORT:
                p=prob(k);expect=historical_n*p
                for mask in subset_masks(k):
                    n=freq[mask]
                    writer.writerow((k,group_labels(base,mask),n,
                       round(n/historical_n,10),round(p,12),
                       round(expect,8),round(n/expect,5)))
            f.flush();f.detach()
        z.writestr("08_METODOLOJI.txt",
         "\n".join([
         "Complete day is 217 real draws with 20 distinct integers 1..80.",
         "Day72 first draw anchor uses POS 1, not an arbitrary clock time.",
         "Historical frequencies use ONLY first 71 complete dates (15407 draws).",
         "Each draw contributes to subset count iff all its members coappear in that one 20-number draw.",
         "2^20 subset superset zeta transform counts every fixed subset exactly.",
         "For same-draw fixed k: P(all)=C(20,k)/C(80,k).",
         "Pair conditional P(B | A)=19/79, but joint P(A AND B)=20*19/(80*79).",
         "For 2..10, all 616645 distinct subsets are output, including zero-hit groups.",
         "Day72 positions 2..217 are evaluated only after historical ranks frozen at POS 1.",
         "Top20/low20 subsets of a given size can overlap massively: pooled event counts are correlated.",
         "One held-out calendar day is an exploratory check, not proof of forecasting ability.",
         "History was extensively researched in V58-V65; method choice is not prospectively pre-registered.",
         ])+"\n")
        z.writestr("09_AUDIT.json",json.dumps(dict(
          selected_day=focus,draw_no=anchor["id"],clock=anchor["time"],
          first20=list(base),historical_dates=prior,
          historical_draws=historical_n,day72_future_draws=216,
          partial_dates={d:len(v) for d,v in all_data.items()
                   if len(v)!=217 or [r["pos"] for r in v]!=list(range(1,218))},
          issues=issues[:20],malformed_lines=bad[:20],
          all_size_2_through_10=616645),ensure_ascii=False,indent=2))
    return lines

def selftest():
    assert math.isclose(prob(2),20*19/(80*79),abs_tol=1e-15)
    assert math.isclose(prob(1),.25,abs_tol=1e-15)
    b=tuple(range(1,21))
    hist=[{"nums":tuple(range(1,21))},
          {"nums":tuple(range(1,11))+tuple(range(21,31))},
          {"nums":tuple(range(40,60))}]
    freq,singles,oh=groups_mask_20(hist,b)
    assert freq[0]==3 and freq[1]==2
    assert freq[3]==2 and freq[(1<<20)-1]==1
    assert oh[20]==1 and oh[10]==1 and oh[0]==1
    assert len(list(subset_masks(2)))==190
    assert sum(comb(20,k) for k in K_EXPORT)==616645
    print("V66 SELFTEST OK",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--output",default="v66_output/V66_72_GUN_ILK20_TUM_BIRLIKTELIK.zip")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest();return
    prev,d,hist,target,issues,bad,full=prior_full_day_rows(args.source)
    lines=report(args.output,prev,d,hist,target,issues,bad,full)
    print("\n".join(lines),flush=True)
    print("RESULT_ZIP",args.output,flush=True)

if __name__=="__main__":main()
