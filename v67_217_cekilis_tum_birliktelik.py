#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V67: All 217 draws of 72nd complete day, strict past-only coappearance.

For each draw:
 * Fix that draw's 20 drawn numbers; 190 pairs, and all 616645 k=2..10 subsets.
 * Count each group's full coappearance in ONE earlier draw, never mixing draws.
 * Historical universe = 71 earlier complete days + earlier draws THIS day.
 * Freeze 10 lowest / 10 highest per k before considering the NEXT draw.
 * Save every group count in a compressed archive (217 x 616645 uint16 values),
   plus human-readable 217-draw, pair, per-k and family-tail tables.
Reusing the historically examined 72-day set is not prospective validation.
"""
from __future__ import annotations
import argparse, csv, io, json, zipfile
from collections import Counter
from math import comb
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

N=1<<20
KSET=tuple(range(2,11))
FAIR_PAIR=comb(20,2)/comb(80,2)

def fixedprob(k):
    return comb(20,k)/comb(80,k)

def create_masks():
    # Sorted by numeric subset mask within each k, not family size mixtures.
    bitcount=np.zeros(N,dtype=np.uint8)
    for b in range(20):
        h=1<<b
        bitcount[h:2*h]=bitcount[:h]+1
    bysize={k:np.flatnonzero(bitcount==k).astype(np.uint32) for k in KSET}
    union=np.concatenate([bysize[k] for k in KSET])
    assert len(union)==616645
    return bysize,union

def historical_counts(prior_draws,base):
    """Vectorized superset (zeta) transform for 2^20 subset counts."""
    position=np.zeros(81,dtype=np.uint32)
    position[np.array(base,dtype=np.intp)]=1<<np.arange(20,dtype=np.uint32)
    common=np.bitwise_or.reduce(position[prior_draws],axis=1)
    hist=np.bincount(common,minlength=N).astype(np.uint16)
    # Every subset has count of SAME-draw superset occurrences.
    for b in range(20):
        h=1<<b
        view=hist.reshape(-1,2*h)
        view[:,:h]+=view[:,h:]
    assert int(hist[0])==len(prior_draws)
    return hist

def compact_group(base,mask):
    return "-".join(str(n) for b,n in enumerate(base) if int(mask)&(1<<b))

def extremes(indices,frequencies,hist,m=10,high=False):
    """Count primary ordering, numeric mask tie-breaker; no huge full sort."""
    n=min(m,len(indices))
    if high:
        pivot=int(np.partition(frequencies,len(indices)-n)[len(indices)-n])
        distinct=indices[frequencies>pivot]
        tied=indices[frequencies==pivot]
        distinct=distinct[np.lexsort((distinct,-hist[distinct].astype(np.int32)))]
    else:
        pivot=int(np.partition(frequencies,n-1)[n-1])
        distinct=indices[frequencies<pivot]
        tied=indices[frequencies==pivot]
        distinct=distinct[np.lexsort((distinct,hist[distinct]))]
    return [int(x) for x in distinct[:n]]+[int(x) for x in tied[:max(0,n-len(distinct))]]

def input_rows(source):
    complete,issues,malformed=parse_txt(source)
    valid=sorted(d for d,rows in complete.items()
       if len(rows)==217 and [r["pos"] for r in rows]==list(range(1,218)))
    if len(valid)<72:raise ValueError(f"Need 72 complete days; have {len(valid)}")
    prior=valid[:71]
    focus=valid[71]
    day=complete[focus]
    earlier=[r for d in prior for r in complete[d]]
    all_draws=earlier+day
    matrix=np.array([r["nums"] for r in all_draws],dtype=np.uint8)
    if matrix.shape!=(71*217+217,20):raise AssertionError("Malformed draw matrix")
    partial={d:len(rows) for d,rows in complete.items() if d not in valid}
    return focus,prior,day,matrix,partial,issues,malformed

def csvwrite(z,name,rows,columns=None):
    with z.open(name,"w",force_zip64=True) as raw:
        out=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        cols=columns if columns is not None else list(rows[0])
        w=csv.DictWriter(out,fieldnames=cols)
        w.writeheader()
        if rows:w.writerows(rows)
        out.flush()
        out.detach()

def process(source,out):
    focus,prior,day,combined,partial,issues,malformed=input_rows(source)
    bysize,all_masks=create_masks()
    summaries=[];sizes=[];pairs=[];tails=[];nextdraw=[]
    aggregate=Counter();anchor_keys=[]
    path=Path(out);path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6,
                         allowZip64=True) as z:
        z.writestr("all_groups/subset_masks_k2_to_k10_uint32le.bin",
                   all_masks.astype("<u4",copy=False).tobytes())
        for pos,anchor in enumerate(day):
            base=tuple(sorted(anchor["nums"]))
            previous=combined[:71*217+pos]
            freq=historical_counts(previous,base)
            row=dict(day=focus,slot=pos+1,draw_id=anchor["id"],clock=anchor["time"],
                  previous_draws=len(previous),anchor20="-".join(map(str,base)))
            scores=freq[all_masks]
            # Absolute length 616645, k=2..10; all values <=15623 and uint16 exact.
            z.writestr(f"all_groups/slot_{pos+1:03d}_uint16le.bin",
                       scores.astype("<u2",copy=False).tobytes())
            anchor_keys.append(row)
            following=set(day[pos+1]["nums"]) if pos+1<len(day) else None
            nextmask=sum(1<<j for j,n in enumerate(base)
                           if following is not None and n in following)
            if following is not None:
                nextdraw.append(dict(slot=pos+1,draw_id=anchor["id"],
                    target_slot=pos+2,target_draw_id=day[pos+1]["id"],
                    overlap20=nextmask.bit_count(),
                    rng_expected_overlap=5))
            for k in KSET:
                ix=bysize[k]
                values=freq[ix]
                mini=int(values.min());maxi=int(values.max())
                krow=dict(slot=pos+1,draw_id=anchor["id"],clock=anchor["time"],
                   size=k,num_groups=len(ix),prior_draws=len(previous),
                   observed_min=mini,observed_mean=round(float(values.mean()),7),
                   observed_max=maxi,zero_groups=int(np.count_nonzero(values==0)),
                   fair_expected_per_group=round(len(previous)*fixedprob(k),7))
                sizes.append(krow)
                if k in (2,3,4,5,6,7,8,9,10):
                    low=extremes(ix,values,freq,m=10,high=False)
                    high=extremes(ix,values,freq,m=10,high=True)
                    for typ,group in (("LEAST_HISTORY_10",low),("MOST_HISTORY_10",high)):
                        hits=0;almost=0;total_mask_overlap=0
                        for rank,mask in enumerate(group,1):
                            old=int(freq[mask])
                            h=(mask&nextmask).bit_count() if following is not None else None
                            if h is not None:
                                hits+=int(h==k)
                                almost+=int(h>=k-2)
                                total_mask_overlap+=h
                            tails.append(dict(slot=pos+1,draw_id=anchor["id"],clock=anchor["time"],
                                k=k,category=typ,rank=rank,group=compact_group(base,mask),
                                previous_same_draws=old,previous_joint_frequency=round(old/len(previous),10),
                                rng_same_draw_expected=round(len(previous)*fixedprob(k),8),
                                next_draw_id=day[pos+1]["id"] if following is not None else "",
                                next_full=int(h==k) if h is not None else "",
                                next_hits=h if h is not None else ""))
                        if following is not None:
                            aggregate[(k,typ,"complete")]+=hits
                            aggregate[(k,typ,"near2")]+=almost
                            aggregate[(k,typ,"number_hits")]+=total_mask_overlap
                            aggregate[(k,typ,"draw_trials")]+=len(group)
                if k==2:
                    row["pair_min"]=mini
                    row["pair_mean"]=round(float(values.mean()),4)
                    row["pair_max"]=maxi
                if k==7:row["seven_zero_groups"]=krow["zero_groups"]
                if k==8:row["eight_zero_groups"]=krow["zero_groups"]
                if k==9:row["nine_zero_groups"]=krow["zero_groups"]
                if k==10:row["ten_zero_groups"]=krow["zero_groups"]
            for a in range(20):
                for b in range(a+1,20):
                    group=(1<<a)|(1<<b)
                    joint=int(freq[group])
                    na=int(freq[1<<a])
                    nb=int(freq[1<<b])
                    pairs.append(dict(slot=pos+1,draw_id=anchor["id"],clock=anchor["time"],
                       a=base[a],b=base[b],previous_draws=len(previous),
                       seen_same_draw=joint,historical_joint_rate=round(joint/len(previous),10),
                       fair_joint_probability=round(FAIR_PAIR,10),
                       given_a_b_rate=round(joint/na,8) if na else "",
                       given_b_a_rate=round(joint/nb,8) if nb else "",
                       fair_conditional=round(19/79,8),
                       next_both=int(base[a] in following and base[b] in following)
                         if following is not None else ""))
            if pos%30==0 or pos==216:
                print(f"V67 processed {pos+1}/217: #{anchor['id']} at {anchor['time']}",flush=True)
            summaries.append(row)
        # Friendly CSV exports (raw full counts remain in binary for tractability).
        csvwrite(z,"00_217_CEKILIS_ANA_TABLO.csv",summaries)
        csvwrite(z,"01_217x9_GRUP_BOYUTLARI_MIN_ORT_MAX_SIFIR.csv",sizes)
        csvwrite(z,"02_TUM_217_CEKILIS_190_IKILI_SAYIMI.csv",pairs)
        csvwrite(z,"03_HER_CEKILIS_EN_AZ_EN_COK_10_AILE_K2_K10.csv",tails)
        csvwrite(z,"04_SONRAKI_CEKILISTE_ILK20_KAC_SAYI_TEKRAR.csv",nextdraw)
        aggregates=[]
        for k in KSET:
            for typ in ("LEAST_HISTORY_10","MOST_HISTORY_10"):
                opportunities=aggregate[(k,typ,"draw_trials")]
                aggregates.append(dict(group_size=k,frozen_group_tail=typ,
                      selected_group_next_draw_opportunities=opportunities,
                      next_draw_exact_completions=aggregate[(k,typ,"complete")],
                      fair_expected_exact=round(opportunities*fixedprob(k),6),
                      next_draw_at_least_k_minus_2=aggregate[(k,typ,"near2")],
                      mean_next_number_hits=round(aggregate[(k,typ,"number_hits")]/opportunities,6),
                      fair_mean_next_number_hits=k/4))
        csvwrite(z,"05_EN_AZ_VE_EN_COK_SONRAKI_CEKILIS_TOPLU.csv",aggregates)
        details=[
            "V67 | 72. GUN 217 CEKILISIN TAMAMI | BIRLIKTE CIKMA",
            f"Target day={focus}; previous complete dates=71; past starting draws=15407.",
            "Day 72 positions 1..217 analysed in draw order.",
            "At position t, historical exposures = 15407 + (t-1). Never include t or future draws.",
            "Each anchor is the exact 20 drawn numbers on that position.",
            "Every 2..10 subset counted only if ALL group members appear in ONE earlier 20-number draw.",
            "Combinations per anchor=616645; total group counts=133811965.",
            "Raw 616645 counts for EVERY anchor retained in all_groups/slot_NNN_uint16le.bin.",
            "For each slot, anchor20 sorted ascending, twenty numbers become bits 0..19.",
            "Master mask array sorted by k 2..10, then integer mask ascending.",
            "Both arrays use little-endian unsigned integers (mask 4 bytes, count 2 bytes).",
            "To recover group counts use matching index in master masks and that slot's counts.",
            "human-readable: main summary, all 190 pairs/draw, min/mean/max each k, 10 least/most each k.",
            "No separate 133M-row CSV because mobile downloading and memory would be impractical.",
            "At slot t the 10 least and 10 most past complete groups of each size are frozen.",
            "Their NEXT draw t+1 is evaluated only after group selection; 217th has no next draw.",
            "The 20 target numbers having just coappeared must not be confused with any past predictive evidence.",
            "Many families overlap; apparent extraordinary lows/highs among hundreds of thousands",
            "are affected by selection and multiple tests; this replay is not prospectively independent.",
            "Every fair, fixed k-member group completes next with C(20,k)/C(80,k) irrespective of its past.",
            "",
            "TOPLINE / EXPECTATION",
            f"First anchor ID={day[0]['id']} time={day[0]['time']} group pair mean={summaries[0]['pair_mean']}",
            f"Last anchor ID={day[-1]['id']} time={day[-1]['time']} prior draws={summaries[-1]['previous_draws']}",
            f"Next draw mean overlap of preceding 20={sum(v['overlap20'] for v in nextdraw)/len(nextdraw):.5f}, fair expected 5.",
        ]
        for a in aggregates:
            if a["group_size"] in (2,3,4,5,7,8,9,10):
                details.append(f"k={a['group_size']} {a['frozen_group_tail']}: next full={a['next_draw_exact_completions']} vs fair={a['fair_expected_exact']}; mean hits={a['mean_next_number_hits']} vs fair={a['fair_mean_next_number_hits']}")
        z.writestr("00_KISA_KARAR.txt","\n".join(details)+"\n")
        z.writestr("06_AUDIT.json",json.dumps(dict(day=focus,
            earlier_complete_dates=prior,day72_draws=217,
            prior_71_days_draws=15407,total_group_counts=133811965,
            groups_per_draw=616645,partial=partial,issues=issues[:20],
            malformed=malformed[:20],
            anchors=anchor_keys),ensure_ascii=False,indent=2))
    return details

def selftest():
    bysize,allmask=create_masks()
    assert len(allmask)==616645 and len(bysize[2])==190
    past=np.array([list(range(1,21)),list(range(1,11))+list(range(21,31)),
         list(range(40,60))],dtype=np.uint8)
    base=tuple(range(1,21))
    counts=historical_counts(past,base)
    assert counts[0]==3
    assert counts[1]==2 and counts[3]==2 and counts[(1<<20)-1]==1
    assert len(extremes(bysize[10],counts[bysize[10]],counts,m=10))==10
    assert len(extremes(bysize[10],counts[bysize[10]],counts,m=10,high=True))==10
    print("V67 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--output",default="v67_output/V67_72GUN_TUM217_CEKILIS_20SAYI_BIRLIKTELIK_TEK_ZIP.zip")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest()
    else:
        output=process(args.source,args.output)
        print("\n".join(output),flush=True)
        print("ZIP",args.output,flush=True)
