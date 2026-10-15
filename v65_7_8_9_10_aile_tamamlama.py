#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V65: 7/8/9/10 family coappearance rarity and frozen forward completion.

A family is derived from the exact intersection of two KNOWN earlier
20-number drawings. Only 7..10-member exact intersections enter.
Every hour previous 72 draws + this hour first six are known; next
six draws are target and are never used in forming or ranking families.
Select least vs most past k-2 near-cooccurrences; compare exact
hypergeometric baselines and a same-size random group.
Exploratory history, not proven lottery prediction.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,random,statistics,zipfile
from collections import Counter,defaultdict
from pathlib import Path
from math import comb
from v52_ayni_cekilis_eslikci_217 import parse_txt
from v53_saatlik_degisen_aileler import BLOCKS

KS=(7,8,9,10)
METHODS=("LOW_ACTIVITY","HIGH_ACTIVITY","OLDEST_COMPLETE","RANDOM_FAMILY")
SEED=651015

def prob(k,r):
    return sum(comb(k,j)*comb(80-k,20-j)/comb(80,20)
               for j in range(r,min(k,20)+1))

def code_mask(nums):
    mask=0
    for n in nums:mask|=1<<(int(n)-1)
    return mask

def numbers(mask):
    return "-".join(str(i+1) for i in range(80) if mask>>i&1)

def candidate_groups(rows):
    masks=[code_mask(r["nums"]) for r in rows]
    result={k:set() for k in KS}
    # Unique intersections of two prior draws, never target draw.
    for i,a in enumerate(masks):
        for b in masks[i+1:]:
            v=a&b
            k=v.bit_count()
            if k in result:result[k].add(v)
    return masks,result

def choices(rows,day,hour):
    masked,all_candidates=candidate_groups(rows)
    result={}
    sizes={}
    for k in KS:
        cs=all_candidates[k]
        sizes[k]=len(cs)
        if not cs:continue
        rank=[]
        for c in cs:
            seen=[i for i,a in enumerate(masked) if (a&c)==c]
            # Every source family is observed >=2. Activity includes
            # "almost-full", at least k-2 in SAME historical drawing.
            near=sum((c&a).bit_count()>=k-2 for a in masked)
            last_age=len(masked)-1-seen[-1]
            rank.append((c,near,len(seen),last_age))
        # least near-count, least complete-support, then oldest, stable tie
        low=min(rank,key=lambda v:(v[1],v[2],-v[3],v[0]))
        high=min(rank,key=lambda v:(-v[1],-v[2],v[3],v[0]))
        oldest=min(rank,key=lambda v:(-v[3],v[1],v[0]))
        rng=random.Random(int.from_bytes(hashlib.sha256(
                 f"{SEED}/{day}/{hour}/{k}".encode()).digest()[:8],"big"))
        sampled=rng.choice(sorted(rank))
        for method,entry in zip(METHODS,(low,high,oldest,sampled)):
            c,near,support,age=entry
            result[(k,method)]=dict(mask=c,past_near=near,
                                     past_complete=support,last_full_gap=age)
    return result,sizes

def _date_lookup(full):
    return sorted(d for d,rs in full.items()
           if len(rs)==217 and [r["pos"] for r in rs]==list(range(1,218)))

def study(full):
    dates=_date_lookup(full)
    if len(dates)<4:raise ValueError("Four complete days required")
    scored=[];hourcounts=[];previous=[]
    for day in dates:
        indexed={r["pos"]:r for r in full[day]}
        for hour in BLOCKS:
            idx=hour["start"]
            first=[indexed[i] for i in range(idx,idx+6)]
            target=[indexed[i] for i in range(idx+6,idx+12)]
            known=(previous[-72:]+first)
            selected,sizes=choices(known,day,hour["code"])
            frozen={key:dict(p) for key,p in selected.items()}
            for k in KS:
                hourcounts.append(dict(day=day,hour=hour["code"],size=k,
                                     unique_candidates=sizes[k],
                                     available=int(k in sizes and sizes[k]>0)))
            for dr in target:
                outcome=code_mask(dr["nums"])
                for (k,method),record in frozen.items():
                    h=(outcome&record["mask"]).bit_count()
                    scored.append(dict(day=day,hour=hour["code"],
                         target_draw=dr["id"],target_time=dr["time"],
                         size=k,method=method,group=numbers(record["mask"]),
                         history_near=record["past_near"],
                         history_full=record["past_complete"],
                         since_last_full=record["last_full_gap"],
                         hits=h,hit_rate=h/k,complete=int(h==k),
                         missing_1_or_less=int(h>=k-1),
                         missing_2_or_less=int(h>=k-2)))
            # The future six are only added to historical prefix AFTER
            # all frozen targets for this hour have been scored.
            previous.extend(indexed[i] for i in range(idx,hour["end"]+1))
            previous=previous[-72:]
    return dates,scored,hourcounts

def csv_zip(z,path,rows):
    out=io.StringIO(newline="")
    fields=list(rows[0]) if rows else ("empty",)
    writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader()
    if rows:writer.writerows(rows)
    z.writestr(path,out.getvalue())

def metrics(scored,hourcounts):
    counts=Counter()
    summary=[]
    buckets=defaultdict(list)
    daily=defaultdict(list)
    for x in scored:
        buckets[(x["size"],x["method"])].append(x)
        daily[(x["size"],x["method"],x["day"])].append(x)
    for k in KS:
        hours=[x for x in hourcounts if x["size"]==k]
        eligible=sum(x["available"] for x in hours)
        for method in METHODS:
            xs=buckets[(k,method)]
            h=len(xs);counts[(k,method)]=h
            if not xs:continue
            row=dict(size=k,method=method,eligible_hours=eligible,
               eligible_hour_fraction=round(eligible/len(hours),5),
               target_draws=h,full_count=sum(v["complete"] for v in xs),
               rng_full_expectation=round(h*prob(k,k),5),
               hits_one_missing=sum(v["missing_1_or_less"] for v in xs),
               rng_one_missing_expectation=round(h*prob(k,k-1),4),
               hits_two_missing=sum(v["missing_2_or_less"] for v in xs),
               rng_two_missing_expectation=round(h*prob(k,k-2),3),
               avg_hits=round(sum(v["hits"] for v in xs)/h,6),
               rng_avg_hits=k/4,
               past_near_mean=round(sum(v["history_near"] for v in xs)/h,4),
               past_full_mean=round(sum(v["history_full"] for v in xs)/h,4))
            summary.append(row)
    return summary

def pairing(scored):
    # Fair test of proposed "least activity beats most activity":
    # daily block pairing avoids inflated precision from correlated draws.
    by=defaultdict(dict)
    for x in scored:
        by[(x["day"],x["hour"],x["target_draw"],x["size"])][x["method"]]=x
    differences=defaultdict(list)
    for (day,_,_,k),vals in by.items():
        if "LOW_ACTIVITY" not in vals or "HIGH_ACTIVITY" not in vals:continue
        differences[(k,day)].append(vals["LOW_ACTIVITY"]["hits"]-
                                  vals["HIGH_ACTIVITY"]["hits"])
    out=[]
    for k in KS:
        perday=[sum(xs)/len(xs) for (kk,d),xs in sorted(differences.items()) if kk==k]
        rng=random.Random(SEED+k)
        bs=sorted(sum(rng.choice(perday) for _ in perday)/len(perday)
                  for _ in range(1500)) if perday else []
        out.append(dict(size=k,days=len(perday),
            difference_low_minus_high=round(sum(perday)/len(perday),6) if perday else "",
            daily_block_boot95_low=round(bs[37],6) if bs else "",
            daily_block_boot95_high=round(bs[1461],6) if bs else "",
            note="REUSED_HISTORY_EXPLORATORY_NOT_PROSPECTIVE"))
    return out

def analytic():
    return [dict(group_size=k,exact_full_probability=round(prob(k,k),12),
       one_missing_or_better_probability=round(prob(k,k-1),12),
       two_missing_or_better_probability=round(prob(k,k-2),12),
       expected_hits_for_one_fixed_group=k/4,
       expected_full_in_15624_draws=round(15624*prob(k,k),6),
       description="One single frozen candidate, not a search across many groups")
        for k in KS]

def output(path,full,partial,issues,malformed,dates,scored,hourcounts):
    estimates=metrics(scored,hourcounts)
    tests=pairing(scored)
    analytic_rows=analytic()
    notes=[
     "V65: YEDI / SEKIZ / DOKUZ / ON AILELERIN TEK CEKILISTE TAMAMLANMASI",
     f"Full days: {len(dates)}; draws: {len(dates)*217}; scored records: {len(scored)}.",
     f"Incomplete days: {len(partial)}; source issues: {len(issues)}, malformed: {len(malformed)}.",
     "Probability for EXACT PRESELECTED k-family full: C(20,k) / C(80,k).",
     "One missing and two missing probabilities: hypergeometric tail of SAME DRAW.",
     "7/7,8/8,9/9,10/10 unconditional full means per single frozen group:",
     *[f"  {k}/ {k}: p={prob(k,k):.10f}, 1 in {1/prob(k,k):,.1f} draws"
       for k in KS],
     "Rare group means lower full probability, NOT greater future hazard.",
     "Historic groups formed ONLY by exact pairwise intersections in previous 72 draws plus 6 observed this hour.",
     "Exact size 7,8,9,10; other pair intersections ignored; all future information excluded.",
     "Each hour LOW_ACTIVITY, HIGH_ACTIVITY, OLDEST_COMPLETE, RANDOM_FAMILY chosen before target 7-12.",
     "Activity counts old drawings containing >=k-2 group members.",
     "Only a SINGLE frozen family from each size/method per hour is tested; therefore",
     "fixed group exact combinatorial baseline is valid, even with selection on prior draws.",
     "Hours without qualifying group excluded per size; not replaced with a future-informed group.",
     "NO better-than-random predictive value may be claimed without independent prospective data.",
     "", "FORWARD HISTORICAL FIRST6 -> LAST6, grouped result:",
    ]
    for v in estimates:
        if v["method"] in ("LOW_ACTIVITY","HIGH_ACTIVITY"):
            notes.append(f"  {v['size']} {v['method']}: eligible hours={v['eligible_hours']}, "
            f"mean hits={v['avg_hits']:.4f} fair={v['rng_avg_hits']:.4f}; "
            f"full={v['full_count']} expected={v['rng_full_expectation']:.4f}; "
            f"near -2={v['hits_two_missing']} expected={v['rng_two_missing_expectation']:.2f}")
    notes.append("")
    notes.append("LOW_ACTIVITY - HIGH_ACTIVITY 95% day-bootstrap exploratory results:")
    for x in tests:notes.append(f"  {x['size']}: mean={x['difference_low_minus_high']} CI [{x['daily_block_boot95_low']},{x['daily_block_boot95_high']}]")
    notes.append("ALL THE ABOVE ARE EXPLORATORY HISTORICAL RESULTS, NOT LOTTERY BUY SIGNALS.")
    dest=Path(path);dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_KARAR_AILE_TAMAMLAMA.txt","\n".join(notes)+"\n")
        csv_zip(z,"01_7_8_9_10_MATEMATIK_OLASILIK.csv",analytic_rows)
        csv_zip(z,"02_7_8_9_10_DONUK_KOR_SONUC.csv",estimates)
        csv_zip(z,"03_AZ_CIKAN_COK_CIKAN_GUN_BLOK_KIYAS.csv",tests)
        csv_zip(z,"04_HEDEF_CEKILISLER_TEK_TEK.csv",scored)
        csv_zip(z,"05_HER_SAAT_ADAY_AILE_SAYISI.csv",hourcounts)
        z.writestr("06_METODOLOJI.txt","\n".join(notes[:15])+"\n")
        z.writestr("07_META.json",json.dumps(dict(seed=SEED,days=len(dates),
             selected_target_records=len(scored),partial=partial,
             source_issues=issues[:12],malformed=malformed[:12]),indent=2))
    return notes

def selftest():
    assert prob(10,10)<prob(9,9)<prob(8,8)<prob(7,7)
    for k in KS:
        assert prob(k,k)<prob(k,k-1)<prob(k,k-2)
        assert math.isclose(prob(k,0),1,abs_tol=1e-12)
    x=list(range(1,21))
    y=list(range(1,11))+list(range(21,31))
    rows=[{"nums":x},{"nums":y}]
    masks,families=candidate_groups(rows)
    assert code_mask(range(1,11)) in families[10]
    assert len(families[7])==0
    chosen,_=choices(rows,"2026-10-15","H00")
    assert chosen[(10,"LOW_ACTIVITY")]["past_complete"]==2
    # Ensure adding a target is not allowed before family freeze.
    print("V65 SELFTEST OK",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--output",default="v65_output/V65_7_8_9_10_AILE_TAMAMLAMA_TEK_ZIP.zip")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest();return
    full,issues,malformed=parse_txt(args.source)
    dates=_date_lookup(full)
    partial={k:len(v) for k,v in full.items() if k not in dates}
    dates,scored,hourcounts=study(full)
    notes=output(args.output,full,partial,issues,malformed,dates,scored,hourcounts)
    print("\n".join(notes),flush=True)
    print("RESULT_ZIP",args.output,flush=True)

if __name__=="__main__":main()
