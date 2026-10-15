#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V85 FAMILY RESET — rebuild roster strictly from training-era 20-number
draws, freeze it, then step through future 72-day calendar results WITHOUT
using any validation/holdout target draw in candidate discovery.

The old V10 catalogue was committed 2026-10-12 AFTER some evaluation days:
it is NOT used as a source of pre-known candidate families in this study.
All 5..10-number families here come from intersections of pairs of *TRAIN*
draws at fixed preceding lags 1,2,6,12. Candidate exact numbers and first
discovery draw IDs are auditable. Keep top 100 per k using TRAIN-only counts.

For every target in VALIDATE/HOLDOUT:
 PARTIAL: max k>=threshold overlap with a frozen family in the prior <=3
          draws of THIS DAY, never the actual target.
 RHYTHM : match prior TRAIN same-day full-family gaps first->second,
          second->third, third->fourth supported on >=2 distinct TRAIN days;
          stage based on prior observed same-day exact full appearances.
 HYBRID : RHYTHM if available, else PARTIAL.
 All methods emit AT MOST ONE 10-number ticket PER TARGET, with one
 family and frequency-based filler from previous <=72 already drawn results.
 Random10 matched at identical issued ticket targets; freq-only top10
 at identical targets also measured. Additional family size and 5/5
 completion counters. Validation chooses exactly ONE method by
 10 hit advantage with >=100 ticket coverage. Holdout is frozen.

No holdout date can affect cataloguing, training patterns, or policy choice.
But datasets Aug–Oct12 were examined during previous projects and therefore
results remain retrospective, not truly fresh prospective evidence.
Fair RNG expects 2.5/10 and each exact predetermined k family has
probability product_{i=0}^{k-1}(20-i)/(80-i) to be fully drawn.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,io,json,math,random,zipfile
from pathlib import Path
from v52_ayni_cekilis_eslikci_217 import parse_txt

VER="V85.1"
DAY=217
SEED=8501510
N_KEEP=100
LAGS=(1,2,6,12)
SIZE=tuple(range(5,11))
MIN_PARTIAL={5:4,6:4,7:5,8:6,9:6,10:7}
RULES=("PARTIAL","RHYTHM","HYBRID")
TRAIN_END="2026-09-12"
VALID_END="2026-09-27"
HOLD_END="2026-10-12"
SUPPORT=2
MIN_ISSUED_VALID=100

def mask(nums):
    return sum(1<<(n-1) for n in nums)

def numbers(m):
    return tuple(n for n in range(1,81) if m&(1<<(n-1)))

def k_probability(k):
    return math.prod((20-i)/(80-i) for i in range(k))

def random_set(k,seed):
    return tuple(sorted(random.Random(seed).sample(range(1,81),k)))

def stable_seed(*parts):
    src="|".join(map(str,parts)).encode()
    return int.from_bytes(hashlib.blake2b(src,digest_size=8).digest(),"big")

def read(src):
    all_days,issues,malformed=parse_txt(src)
    full=sorted(d for d,draw in all_days.items() if
                len(draw)==217 and
                [x["pos"] for x in draw]==list(range(1,218)))
    if len(full)!=72 or full[0]!="2026-08-01" or full[-1]!=HOLD_END:
        raise RuntimeError(f"Need exactly 72 complete days: {len(full)}")
    if TRAIN_END not in full or VALID_END not in full:
        raise RuntimeError("Cutoff days not found")
    rows={d:all_days[d] for d in full}
    return full,rows,issues,malformed

def frozen_roster(days,draws):
    # Every candidate's two provenance draws must be in TRAIN only.
    formed={}
    aggregate=[(day,draw) for day in days if day<=TRAIN_END for draw in draws[day]]
    for day in days:
        if day>TRAIN_END:break
        rows=draws[day]
        ms=[mask(r["nums"]) for r in rows]
        for i in range(len(rows)):
            for lag in LAGS:
                if i<lag:continue
                intersection=ms[i]&ms[i-lag]
                ns=numbers(intersection)
                if len(ns)<5:continue
                for k in SIZE:
                    if k>len(ns):continue
                    # One permutation per fixed, already-observed two-draw
                    # intersection; supports every k without future labels.
                    ordered=sorted(ns,key=lambda b:stable_seed("select",ms[i],
                                    ms[i-lag],b))
                    f=tuple(sorted(ordered[:k]))
                    key=mask(f)
                    if key not in formed:
                        formed[key]=dict(numbers=f,k=k,mask=key,
                            formed_day=day,formed_draw=rows[i]["id"],
                            parent_lag=lag,parents=[rows[i-lag]["id"],rows[i]["id"]],
                            pair_generation_count=0)
                    formed[key]["pair_generation_count"]+=1
    # Only training period controls candidate quality, never later outcomes.
    candidates=list(formed.values())
    for f in candidates:
        f["train_hits"]=0
        f["train_dates"]=set()
        f["train_appearances"]=collections.defaultdict(list)
    for day in days:
        if day>TRAIN_END:break
        masks=[mask(r["nums"]) for r in draws[day]]
        for f in candidates:
            fm=f["mask"]
            for i,m in enumerate(masks):
                if m&fm==fm:
                    f["train_hits"]+=1
                    f["train_dates"].add(day)
                    f["train_appearances"][day].append(i+1)
    roster=[]
    for k in SIZE:
        pool=[x for x in candidates if x["k"]==k]
        pool.sort(key=lambda f:(-len(f["train_dates"]),
                   -f["train_hits"],-f["pair_generation_count"],
                   -stable_seed("rank",f["numbers"])))
        roster.extend(pool[:N_KEEP])
    roster.sort(key=lambda f:(f["k"],f["numbers"]))
    assert len(roster)<=N_KEEP*len(SIZE)
    return roster,len(candidates),aggregate

def train_rhythms(roster):
    for f in roster:
        first=collections.Counter()
        triple=collections.Counter()
        quad=collections.Counter()
        for day,ps in f["train_appearances"].items():
            ps=sorted(ps)
            if len(ps)>=2:first[ps[1]-ps[0]]+=1
            for t in set((ps[j+1]-ps[j],ps[j+2]-ps[j+1])
                         for j in range(len(ps)-2)):
                triple[t]+=1
            for t in set(tuple(ps[j+s+1]-ps[j+s] for s in range(3))
                         for j in range(len(ps)-3)):
                quad[t]+=1
        f["first"]=first
        f["triple"]=triple
        f["quad"]=quad

def potential_rhythm(f,positions,target_pos):
    """No target result is used: positions are already seen TODAY."""
    n=len(positions)
    if n<1 or n>3:return None
    if n==1:
        target_gap=target_pos-positions[0]
        support=f["first"].get(target_gap,0)
        stage="1to2"
    elif n==2:
        target_gap=target_pos-positions[-1]
        support=f["triple"].get((positions[1]-positions[0],target_gap),0)
        stage="2to3"
    else:
        target_gap=target_pos-positions[-1]
        gaps=(positions[1]-positions[0],
              positions[2]-positions[1],target_gap)
        support=f["quad"].get(gaps,0)
        stage="3to4"
    if support<SUPPORT:return None
    return dict(stage=stage,gap=target_gap,support=support)

def family_score(f,partial,best_rhythm=None):
    support=best_rhythm["support"] if best_rhythm else 0
    return (1.0*partial/f["k"] if partial is not None else 0.0) + \
       .022*min(len(f["train_dates"]),12) +\
       .04*min(support,4) + .0005*f["k"]

def ticket10(f,recent_counts):
    selected=list(f["numbers"])
    for n in sorted(range(1,81),key=lambda n:(-recent_counts[n],n)):
        if len(selected)==10:break
        if n not in selected:selected.append(n)
    return tuple(sorted(selected))

def rank10(recent_counts):
    return tuple(sorted(range(1,81),key=lambda n:(-recent_counts[n],n))[:10])

def replay(days,draws,roster):
    records=[]
    full_appearances=collections.Counter()
    for day in days:
        if day<=TRAIN_END:continue
        phase="VALIDATE" if day<=VALID_END else "HOLDOUT"
        seen_positions=[[] for _ in roster]
        hist=collections.deque(maxlen=72)
        counts=[0]*81
        latest=[]
        # History from previously loaded draws earlier than target day
        for prev in days:
            if prev>=day:break
            for row in draws[prev]:
                m=mask(row["nums"])
                hist.append(m)
        # Seed counts from those last 72 known actual draws.
        for m in hist:
            for n in numbers(m):counts[n]+=1
        today_masks=[]
        for row in draws[day]:
            pos=row["pos"]
            actual_mask=mask(row["nums"])
            candidates={"PARTIAL":[],"RHYTHM":[]}
            # Previous up to three today draws, not target.
            recent=today_masks[-3:]
            for ix,f in enumerate(roster):
                fm=f["mask"]
                partial=max(((fmask&fm).bit_count() for fmask in recent),
                            default=0)
                if partial>=MIN_PARTIAL[f["k"]]:
                    candidates["PARTIAL"].append((family_score(f,partial),
                        ix,partial,None))
                rhythm=potential_rhythm(f,seen_positions[ix],pos)
                if rhythm:
                    candidates["RHYTHM"].append((family_score(f,partial,rhythm),
                        ix,partial,rhythm))
            for k in ("PARTIAL","RHYTHM"):
                candidates[k].sort(key=lambda x:(-x[0],-len(roster[x[1]]["train_dates"]),
                         -roster[x[1]]["k"],roster[x[1]]["numbers"]))
            if candidates["RHYTHM"]:
                candidates["HYBRID"]=candidates["RHYTHM"]
            else:
                candidates["HYBRID"]=candidates["PARTIAL"]
            freq10=rank10(counts)
            for rule in RULES:
                if not candidates[rule]:continue
                score,idx,partial,rhythm=candidates[rule][0]
                fam=roster[idx]
                coupon=ticket10(fam,counts)
                random10=random_set(10,stable_seed("baseline",SEED,day,pos))
                actual_set=set(row["nums"])
                got=sum(n in actual_set for n in coupon)
                gotfreq=sum(n in actual_set for n in freq10)
                gotrand=sum(n in actual_set for n in random10)
                familyhit=(actual_mask&fam["mask"]).bit_count()
                r=dict(day=day,phase=phase,draw_id=row["id"],pos=pos,
                    rule=rule,family="-".join(map(str,fam["numbers"])),
                    family_k=fam["k"],family_score=round(score,5),
                    family_discovered_on=fam["formed_day"],
                    family_discovered_draw=fam["formed_draw"],
                    train_family_full_hits=fam["train_hits"],
                    train_distinct_days=len(fam["train_dates"]),
                    trigger_partial=f"{partial}/{fam['k']}",
                    rhythm_stage=rhythm["stage"] if rhythm else "",
                    rhythm_gap=rhythm["gap"] if rhythm else "",
                    rhythm_prior_distinct_days=rhythm["support"] if rhythm else "",
                    coupon10=",".join(map(str,coupon)),
                    coupon10_hits=got,
                    top72freq10_hits=gotfreq,
                    random10_hits=gotrand,
                    family_actual_hit_count=familyhit,
                    full_family_completion=int(familyhit==fam["k"]),
                    target_actual20=",".join(map(str,row["nums"])))
                records.append(r)
            # AFTER all predictions open draw; update each family's
            # history of completed family appearances.
            for ix,f in enumerate(roster):
                if actual_mask&f["mask"]==f["mask"]:
                    seen_positions[ix].append(pos)
                    full_appearances[(phase,f["k"])]+=1
            today_masks.append(actual_mask)
            if len(hist)==72:
                evicted=hist.popleft()
                for n in numbers(evicted):counts[n]-=1
            hist.append(actual_mask)
            for n in row["nums"]:counts[n]+=1
    return records,full_appearances

def metrics(records,dates):
    results=[]
    for phase in ("VALIDATE","HOLDOUT"):
        for rule in RULES:
            rr=[r for r in records if r["phase"]==phase and r["rule"]==rule]
            n=len(rr)
            days=set(r["day"] for r in rr)
            if not n:
                results.append(dict(phase=phase,rule=rule,
                    alerts=0,distinct_days=0,coverage_percent=0.))
                continue
            obs=sum(r["coupon10_hits"] for r in rr)
            random_=sum(r["random10_hits"] for r in rr)
            freq=sum(r["top72freq10_hits"] for r in rr)
            unique=collections.Counter(r["family_k"] for r in rr)
            full=sum(r["full_family_completion"] for r in rr)
            daydeltas=[]
            for day in sorted(days):
                dr=[r for r in rr if r["day"]==day]
                daydeltas.append(sum((r["coupon10_hits"]-r["random10_hits"])
                    for r in dr)/len(dr))
            avg=sum(daydeltas)/len(daydeltas)
            sd=(math.sqrt(sum((v-avg)**2 for v in daydeltas)
                /(len(daydeltas)-1)) if len(daydeltas)>1 else 0.)
            se=sd/math.sqrt(len(daydeltas)) if days else 0.
            z=avg/se if se else 0.
            results.append(dict(phase=phase,rule=rule,
                alerts=n,distinct_days=len(days),
                coverage_percent=round(100*n/(len(dates)*DAY),5),
                actual10_avg=round(obs/n,7),
                same_targets_random10_avg=round(random_/n,7),
                same_targets_freq10_avg=round(freq/n,7),
                actual_minus_random=round((obs-random_)/n,7),
                actual_minus_freq=round((obs-freq)/n,7),
                daily_avg_difference=round(avg,7),
                daily_se=round(se,7),
                day_cluster_p_one_sided=round(.5*math.erfc(z/math.sqrt(2)),7),
                n_7plus=sum(r["coupon10_hits"]>=7 for r in rr),
                n_8plus=sum(r["coupon10_hits"]>=8 for r in rr),
                n_9plus=sum(r["coupon10_hits"]>=9 for r in rr),
                n_10of10=sum(r["coupon10_hits"]==10 for r in rr),
                completed_families=full,
                family_ticket_sizes=";".join(f"{k}:{v}" for k,v in sorted(unique.items()))))
    return results

def csvfile(z,filename,rows):
    if not rows:return
    with z.open(filename,"w",force_zip64=True) as raw:
        tx=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        w=csv.DictWriter(tx,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
        tx.flush();tx.detach()

def run(source,out):
    dates,draws,issues,bad=read(source)
    train=[d for d in dates if d<=TRAIN_END]
    val=[d for d in dates if TRAIN_END<d<=VALID_END]
    hold=[d for d in dates if VALID_END<d<=HOLD_END]
    assert len(train)==42 and len(val)==15 and len(hold)==15
    roster,raw_count,source_rows=frozen_roster(dates,draws)
    print("V85 new frozen TRAIN-only families",len(roster),
          "from possible",raw_count,flush=True)
    print("V85 size",dict(collections.Counter(f["k"] for f in roster)),
          "train",len(train),flush=True)
    train_rhythms(roster)
    predictions,full_counts=replay(dates,draws,roster)
    results=metrics(predictions,val)
    val_rows=[r for r in results if r["phase"]=="VALIDATE" and r["alerts"]>=MIN_ISSUED_VALID]
    # No sufficient validation sample => no locked selectable method,
    # and candidly report it instead of falling back to test-based choice.
    winner=(sorted(val_rows,key=lambda r:(
             -(r["actual_minus_random"]-.0005/math.sqrt(r["alerts"])),
             -r["alerts"],RULES.index(r["rule"])))[0]
             if val_rows else None)
    holdwinner=(next((r for r in results if r["phase"]=="HOLDOUT" and
                 winner and r["rule"]==winner["rule"]),None))
    family_rows=[]
    for f in roster:
        family_rows.append(dict(family="-".join(map(str,f["numbers"])),
             k=f["k"],discovered_on=f["formed_day"],
             first_parent_id=f["parents"][0],
             second_parent_id=f["parents"][1],
             family_discovered_draw=f["formed_draw"],
             parent_draw_gap=f["parent_lag"],
             pair_sources_count=f["pair_generation_count"],
             training_full_appearances=f["train_hits"],
             training_unique_days=len(f["train_dates"]),
             training_first_gap_support=str(sorted(f["first"].items())),
             training_triple_support=str(sorted(f["triple"].items())),
             training_quad_support=str(sorted(f["quad"].items()))))
    chosen_rows=([r for r in predictions if
         winner and r["phase"]=="HOLDOUT" and r["rule"]==winner["rule"]]
         if winner else [])
    bysize=[]
    for phase in ("VALIDATE","HOLDOUT"):
        for rule in RULES:
            rows=[r for r in predictions if r["phase"]==phase and r["rule"]==rule]
            for k in SIZE:
                sub=[r for r in rows if r["family_k"]==k]
                if not sub:continue
                n=len(sub);f=sum(r["family_actual_hit_count"] for r in sub)
                complete=sum(r["full_family_completion"] for r in sub)
                bysize.append(dict(phase=phase,rule=rule,k=k,
                    total_families_selected=n,actual_family_ones=f,
                    avg_family_hits=round(f/n,7),
                    theoretical_average_family_hits=k*.25,
                    actual_full_family=complete,
                    fair_expected_full=round(n*k_probability(k),7),
                    full_probability_fair=round(k_probability(k),12)))
    summary=[
     "V85 — AILELERI HINTSIGHT OLMADAN YENIDEN DOGUR, SONRA GERCEK KUPON",
     "STOP REUSING V10 1131 families for validation before their Oct12 commit.",
     "V85 roster derived ONLY from pairs of training draws 1Aug–12Sep;",
     "at draw lags 1,2,6,12 within a day, exact intersection creates",
     "pre-target 5-,6-,7-,8-,9-,10-ball families, top max 100 per k.",
     "The roster is frozen BEFORE VALIDATE Sep13–Sep27 and HOLDOUT Sep28–Oct12.",
     "Three fixed signal strategies (PARTIAL,RHYTHM,HYBRID) issue MAX one",
     "10-number coupon per actual target; no required coupon without signal.",
     "Partial based on any ONE of last <=3 already observed daily draws;",
     "rhythms learn training-era gap repeats on at least two DISTINCT days.",
     "10-ball coupon contains known family and fills remaining from the",
     "most frequent other balls in PREVIOUS 72 already known draws.",
     "Compare target-matched independent random10 AND previous72-frequency10.",
     f"Training days={len(train)}, validation={len(val)}, holdout={len(hold)}.",
     f"Discovered {raw_count} raw family candidates, frozen {len(roster)}.",
     "FROZEN roster by size: "+str(dict(collections.Counter(f["k"] for f in roster))),
     "UNTOUCHED DATA WITHIN A GIVEN HOLDOUT PREDICTION: every candidate,",
     "rhythm history and score use strictly earlier targets, not current.",
     "NOTE all date ranges are broadly researched by prior V9–V84 runs.",
     "Thus this is still retrospectively specified, not new prospective proof.",
     "",
     "VALIDATE and HOLDOUT performance by method; fair independent RNG 2.5/10:"
    ]
    for r in results:
        if not r["alerts"]:
            summary.append(f"  {r['phase']} {r['rule']}: no signals")
        else:
            summary.append(f"  {r['phase']} {r['rule']}: alerts={r['alerts']},"
                f" 10coupon={r['actual10_avg']:.6f},"
                f" random10={r['same_targets_random10_avg']:.6f},"
                f" prior72freq10={r['same_targets_freq10_avg']:.6f},"
                f" 10/10={r['n_10of10']}, 7+={r['n_7plus']},"
                f" day_cluster_p={r['day_cluster_p_one_sided']:.6f}")
    summary+=[""]
    if winner:
        summary.append(f"Selected on VALIDATE only: {winner['rule']} "
             f"(validation n={winner['alerts']}, "
             f"mean10={winner['actual10_avg']:.6f}).")
        summary.append(f"Frozen HOLDOUT: mean10={holdwinner['actual10_avg']:.6f},"
            f" random={holdwinner['same_targets_random10_avg']:.6f},"
            f" freq-only={holdwinner['same_targets_freq10_avg']:.6f},"
            f" delta vs random={holdwinner['actual_minus_random']:+.6f}.")
        summary.append(f"10/10={holdwinner['n_10of10']}; "
            f"7+={holdwinner['n_7plus']};"
            f" p={holdwinner['day_cluster_p_one_sided']:.6f}.")
    else:
        summary.append("No strategy had >=100 VALIDATION alerts; no winner.")
    summary+=["",
      "Even if families recur in already-observed days, this does not",
      "prove independent fair draws have a causal memory or forecast signal.",
      "Select ONE genuinely new next-target strategy and keep tickets",
      "immutable before future published Hızlı On outcomes.",
      "Avoid paid coupons based on unvalidated retrospective differences.",
      ""
    ]
    out=Path(out);out.parent.mkdir(exist_ok=True,parents=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6,allowZip64=True) as z:
        z.writestr("00_V85_DURUST_AILE_KUPON_SONUC.txt","\n".join(summary))
        csvfile(z,"01_SADECE_EGITIMDEN_DOGAN_DONDURULMUS_AILELER.csv",family_rows)
        csvfile(z,"02_UC_KURAL_15GUN_VAL_15GUN_TEST_RASTGELE.csv",results)
        csvfile(z,"03_KURAL_X_AILE_BOYUTU_GERCEK_1_0_VE_TAM.csv",bysize)
        csvfile(z,"04_SON15GUN_SECILI_KURAL_TEK_10LU_HEDEF_KUPONLARI.csv",chosen_rows)
        csvfile(z,"05_HER_UC_KURAL_TUM_SINYALLER_GECER_GECMEZ.csv",predictions)
        z.writestr("06_KURALLAR.txt","\n".join([
            "TRAIN catalogue made from 42 full days 1Aug–12Sep only.",
            "Family identity discovered as subset of intersection of two",
            "already observed TRAIN draws with lag 1,2,6,12 that same day.",
            "TRAIN-only support and count chooses up to 100 per k in 5..10.",
            "Source V10 static CSV never used; it was compiled on Oct12.",
            "VALIDATE Sep13–Sep27 selects one policy with >=100 signals.",
            "HOLDOUT Sep28–Oct12 policy locked, never selected after outcomes.",
            "Candidate PARTIAL uses best overlap within last three past draws",
            "in same DAY; 4/5 does NOT refer to target result.",
            "RHYTHM from FIRST, SECOND or THIRD observed full family event",
            "on the day, plus gaps seen >=2 separate TRAIN days.",
            "HYBRID rhythm when available, else partial.",
            "No prediction when there is no trigger.",
            "At most one family, one ten-number coupon per target per policy.",
            "Ten coupon uses family members and fill with last72 numbers",
            "counted strictly before the target, no target data leak.",
            "Random baseline seeded from (date, slot), and frequency-only",
            "baseline based on identical prefix; same target comparisons.",
            "Selection of validation winner must not inspect holdout results.",
            "Favorable historical differences not a prospective guarantee.",
            "Expected fair each 10/20 draw hit 2.5; exact predetermined",
            "k-family hit probability p=prod_{i=0..k-1}(20-i)/(80-i)."
        ]))
        z.writestr("07_AUDIT.json",json.dumps(dict(
            version=VER,data_days=days,catalogue_candidate_count=raw_count,
            frozen_roster_count=len(roster),family_sizes=dict(collections.Counter(
              f["k"] for f in roster)),training_cutoff=TRAIN_END,
            validation_cutoff=VALID_END,holdout_cutoff=HOLD_END,
            rules=RULES,selected_rule=winner["rule"] if winner else None,
            val_result=winner,holdout_result=holdwinner,
            results=results,source_issues=issues[:20],invalid=bad[:20]),
            ensure_ascii=False,indent=2))
    print("\n".join(summary),flush=True)
    print("V85 OUTPUT",out,out.stat().st_size,flush=True)

def selftest():
    assert MIN_PARTIAL[5]==4
    assert (mask([1,2,3])&mask([2,3,4])).bit_count()==2
    assert ticket10(dict(numbers=(1,2,3,4,5)),[0]+[0]*80)==tuple(range(1,11))
    assert len(random_set(10,SEED))==10
    assert 0.0006<k_probability(5)<0.0007
    print("V85 SELFTEST OK")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v85_output/V85_AILE_YENIDEN_DOGUS_10LU_KUPON_KOR_TEST.zip")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest()
    else:run(args.source,args.out)
