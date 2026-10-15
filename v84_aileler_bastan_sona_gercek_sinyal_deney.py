#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V84: full audit of V9/V10 static 1131-family catalogue and live/retrospective
'Geliyorum' partial warnings + 1->2,2->3,3->4 historical cadence signals.

Read exact v10_aileler.csv and full original veri.txt. The family CATALOGUE
itself was selected and committed October 12, 2026, after most test dates.
This audit deliberately calls its replay RETROSPECTIVE, not an independent
prediction experiment. Prospective test requires newly generated future
families or freezing catalogue before future data arrive.

For each day:
 - same-day historical family full appearance and 1st/2nd/3rd/4th positions
 - prior-days-only hour-specific appearance support and days with appearances
 - last 3 already DRAWN target results only, no current/future target input
 - exact V10 Geliyorum readiness: k-specific partial threshold,
   >=2 or 3 previous DISTINCT days in target clock hour, >= threshold in
   last 2 if >=2 observed, >= support days with any full appearances
 - model predictions use only prefix info, actual 20 numbers revealed later
 - exact-family 1->2, 2->3, 3->4 rhythmic gap predicates from prior days,
   minimum 2 DISTINCT historical supporting days for each gap pattern.
Compare target-family overlap and complete hits to k*0.25 and exact
hypergeometric probability; never confuse '4/5 trigger' with '4/5 hit'.

All family selection/candidate overlap creates correlated tests; descriptive
numbers, especially reconstructed before family catalogue commitment, are not
real prospective validation. ZERO betting claims.
"""
from __future__ import annotations
import argparse,csv,io,json,math,zipfile,random,hashlib,collections
from pathlib import Path
from v52_ayni_cekilis_eslikci_217 import parse_txt
from v45_sinyal_kor_test import SLOTS
from v10_geliyorum import MIN_PARTIAL

VERSION="V84.1"
SPLITS=(("DEV","2026-08-01","2026-09-12"),
        ("VALIDATE","2026-09-13","2026-09-27"),
        ("HOLDOUT","2026-09-28","2026-10-12"))
SEED=841015

def prob_complete(k):
    return math.prod((20-i)/(80-i) for i in range(k))

def fmask(values):
    return sum(1 << (n-1) for n in values)

def getdata(path,fampath):
    byday,issues,bad=parse_txt(path)
    dates=sorted(d for d,rows in byday.items()
                 if len(rows)==217 and
                    [r["pos"] for r in rows]==list(range(1,218)))
    if len(dates)!=72 or dates[0]!="2026-08-01" or dates[-1]!="2026-10-12":
        raise RuntimeError(f"Unexpected complete 72 days: {len(dates)}")
    catalog=[]
    with Path(fampath).open(encoding="utf-8-sig",newline="") as f:
        for rec in csv.DictReader(f,delimiter=";"):
            ns=tuple(map(int,rec["Aile"].split("-")))
            k=int(rec["Boyut"])
            assert len(ns)==k and len(set(ns))==k and all(1<=x<=80 for x in ns)
            catalog.append(dict(label=rec["Aile"],k=k,mask=fmask(ns),
                src=rec["Kaynak"],declared_days=int(rec["Aktif_Gun"]),
                declared_hits=int(rec["Toplam_Gorunus"])))
    assert len(catalog)==1131
    assert len(set(x["mask"] for x in catalog))==len(catalog)
    draws={}
    for day in dates:
        draw=byday[day]
        draws[day]=[(r,fmask(r["nums"])) for r in draw]
    return dates,draws,catalog,issues,bad

def group_rec(keys,key):
    if key not in keys:keys[key]=[0,0,0,0,0]
    return keys[key]

def target_control(label,date,pos,k,mask_actual):
    # Deterministic sham coupon (same length, same target):
    # globally deterministic seed known independently of actual target.
    s=f"{SEED}|{label}|{date}|{pos}".encode()
    seed=int.from_bytes(hashlib.blake2b(s,digest_size=8).digest(),"big")
    nums=random.Random(seed).sample(range(1,81),k)
    return (mask_actual & fmask(nums)).bit_count()

def summarize(counters,fields):
    out=[]
    for key,stats in sorted(counters.items()):
        n,overlap,full,random_overlap,fully_partial=stats
        if n==0:continue
        rec=dict(zip(fields,key))
        k=int(rec.get("family_k",0))
        rec.update(opportunities=n,actual_hit_numbers=overlap,
          mean_actual_hits=round(overlap/n,7),
          mean_random_hits=round(random_overlap/n,7),
          actual_full_family_completions=full,
          theoretical_full_expected=round(n*prob_complete(k),6) if k else None,
          actual_full_pct=round(100*full/n,7),
          full_predicted_by_theory_pct=round(100*prob_complete(k),9) if k else None,
          source_trigger_full5_count=fully_partial)
        out.append(rec)
    return out

def run(drawfile,fampath,outpath):
    days,draws,fams,issues,bad=getdata(drawfile,fampath)
    sizes=collections.Counter(f["k"] for f in fams)
    totals={f["label"]:collections.defaultdict(list) for f in fams}
    # prior-day-only profiles, one independent day increment per pattern.
    known_days=[0]*len(fams)
    hourly=[[0]*24 for _ in fams]
    historical_first=[collections.Counter() for _ in fams]
    historical_tri=[collections.Counter() for _ in fams]
    historical_quad=[collections.Counter() for _ in fams]
    near_summary={}
    gap_summary={}
    signals_detail=[]
    topwarning=[]
    perday=[]
    alert_summary=collections.Counter()
    gap_dedup_count=0
    for d_index,day in enumerate(days):
        raw=draws[day]
        observed=[mask for _,mask in raw]
        hours=[int(SLOTS[i][:2]) for i in range(217)]
        family_ap=[[idx+1 for idx,mask in enumerate(observed) if
                       mask&fam["mask"]==fam["mask"]]
                   for fam in fams]
        today_signal_counts=collections.Counter()
        for i,f in enumerate(fams):
            for pos in family_ap[i]:
                totals[f["label"]][day].append(pos)
        # Chronologically available exact family cadence predictions.
        # Count not only successful future complete matches.
        gap_candidates={}
        for i,f in enumerate(fams):
            k=f["k"];label=f["label"];positions=family_ap[i]
            for n in (1,2,3):
                if len(positions)<n:continue
                before=positions[:n]
                observed_at=before[-1]
                if n==1:
                    patterns=[(g,s,"1to2") for g,s in historical_first[i].items()]
                elif n==2:
                    first_gap=before[1]-before[0]
                    patterns=[(g2,s,"2to3") for (g1,g2),s in historical_tri[i].items()
                         if g1==first_gap]
                else:
                    ab=before[1]-before[0];bc=before[2]-before[1]
                    patterns=[(g3,s,"3to4") for (g1,g2,g3),s in historical_quad[i].items()
                         if (g1,g2)==(ab,bc)]
                for gap,support,stage in patterns:
                    target=observed_at+gap
                    if support<2 or target>217 or target<=observed_at:
                        continue
                    key=(label,stage,target)
                    if key in gap_candidates:continue
                    gap_candidates[key]=(i,stage,target,gap,support,observed_at)
        for (label,stage,pos),(i,stage,pos,gap,support,obs) in gap_candidates.items():
            k=fams[i]["k"]
            actual=(observed[pos-1]&fams[i]["mask"]).bit_count()
            rnd=target_control(label,day,pos,k,observed[pos-1])
            phase=("DEV" if day<"2026-09-13" else
                   "VALIDATE" if day<"2026-09-28" else "HOLDOUT")
            rec=group_rec(gap_summary,(phase,stage,k))
            rec[0]+=1;rec[1]+=actual;rec[2]+=int(actual==k);rec[3]+=rnd
            today_signal_counts[f"rhythm_{stage}"]+=1
            if phase=="HOLDOUT" and len(signals_detail)<30000:
                signals_detail.append(dict(day=day,draw_pos=pos,stage=stage,
                     family=label,k=k,
                     last_known_full_pos=obs,historical_gap=gap,
                     prior_distinct_support_days=support,
                     actual_hit_numbers=actual,complete=int(actual==k),
                     random_same_size_hits=rnd))
        # Early warnings: at t, only prior three actual draws available;
        # history hours/profiles use only strictly older DAYS.
        # Includes ANY target slot that has at least one past draw that day.
        best_one_per_target={}
        for pos in range(2,218):
            targethour=hours[pos-1]
            previous=observed[max(0,pos-4):pos-1]
            actual_target=observed[pos-1]
            candidate=[]
            for i,f in enumerate(fams):
                k=f["k"]
                vals=[(q&f["mask"]).bit_count() for q in previous]
                best=max(vals)
                threshold=MIN_PARTIAL[k]
                if best<threshold:continue
                support=hourly[i][targethour]
                # exact next V10 earliest warning readiness prerequisites
                if support<2 or known_days[i]<2 or (
                        len(vals)!=1 and max(vals[-2:])<threshold):
                    continue
                cur=(actual_target&f["mask"]).bit_count()
                rand=target_control(f["label"],day,pos,k,actual_target)
                phase=("DEV" if day<"2026-09-13" else
                       "VALIDATE" if day<"2026-09-28" else "HOLDOUT")
                # same type of 5/5 or 4/5 seen, not success rate
                key=(phase,k,best,2 if support==2 else 3)
                rec=group_rec(near_summary,key)
                rec[0]+=1;rec[1]+=cur;rec[2]+=int(cur==k);rec[3]+=rand
                rec[4]+=int(best==k)
                candidate.append((i,best,support,k,cur,rand))
                today_signal_counts["early_candidates"]+=1
            if candidate:
                # deterministic top signal policy before target is opened:
                # V10 early alert defaults ready first, stronger hour support,
                # stronger observed partial; no target leakage in ranking.
                candidate.sort(key=lambda x:(-x[2],-x[1],-x[3],fams[x[0]]["label"]))
                i,best,support,k,cur,rnd=candidate[0]
                best_one_per_target[pos]=(i,best,support,k,cur,rnd)
        for pos,(i,best,support,k,cur,rnd) in best_one_per_target.items():
            phase=("DEV" if day<"2026-09-13" else
                   "VALIDATE" if day<"2026-09-28" else "HOLDOUT")
            rec=group_rec(near_summary,(phase,k,best,999))
            rec[0]+=1;rec[1]+=cur;rec[2]+=int(cur==k);rec[3]+=rnd
            today_signal_counts["early_distinct_targets"]+=1
            if phase=="HOLDOUT" and len(topwarning)<10000:
                topwarning.append(dict(day=day,draw_id=raw[pos-1][0]["id"],
                    slot=pos,family=fams[i]["label"],size=k,
                    partial_best_previous3=f"{best}/{k}",
                    prior_same_hour_days=support,
                    actual_next_hit=f"{cur}/{k}",
                    random_control_hit=f"{rnd}/{k}",
                    exact_complete=int(cur==k)))
        # update only AFTER target day completed; never same-day targets.
        for i,ps in enumerate(family_ap):
            if not ps:continue
            known_days[i]+=1
            for h in {hours[q-1] for q in ps}:hourly[i][h]+=1
            if len(ps)>=2:historical_first[i][ps[1]-ps[0]]+=1
            triples=set((ps[j+1]-ps[j],ps[j+2]-ps[j+1])
                        for j in range(len(ps)-2))
            quads=set(tuple(ps[j+h+1]-ps[j+h] for h in range(3))
                      for j in range(len(ps)-3))
            for tri in triples:historical_tri[i][tri]+=1
            for quad in quads:historical_quad[i][quad]+=1
        perday.append(dict(day=day,
             distinct_new_families=int(sum(1 for i,ps in enumerate(family_ap)
                                           if ps and known_days[i]==1)),
             complete_family_events=sum(len(ps) for ps in family_ap),
             number_of_families_complete_any=sum(bool(ps) for ps in family_ap),
             early_candidates=today_signal_counts["early_candidates"],
             early_distinct_targets=today_signal_counts["early_distinct_targets"],
             rhythm_1to2=today_signal_counts["rhythm_1to2"],
             rhythm_2to3=today_signal_counts["rhythm_2to3"],
             rhythm_3to4=today_signal_counts["rhythm_3to4"]))
        if d_index%12==0:
            print(f"V84 processed day {d_index+1}/72",flush=True)
    # Full-family events as input family CSV vs actual 72 days:
    familyrows=[]
    for fam in fams:
        byday=totals[fam["label"]]
        occurrences=[(day,pos) for day,positions in sorted(byday.items())
                     for pos in positions]
        first=occurrences[0][0] if occurrences else ""
        end=occurrences[-1][0] if occurrences else ""
        early=sum(len(pos) for d,pos in byday.items() if d<"2026-09-13")
        val=sum(len(pos) for d,pos in byday.items()
                if "2026-09-13"<=d<"2026-09-28")
        hold=sum(len(pos) for d,pos in byday.items() if d>="2026-09-28")
        familyrows.append(dict(family=fam["label"],k=fam["k"],src=fam["src"],
            declared_days=fam["declared_days"],
            actual_unique_days=len(byday),
            declared_complete_hits=fam["declared_hits"],
            completed_full_hits_72days=len(occurrences),
            full_before_sept13=early,full_validation=val,full_holdout=hold,
            first_full_day=first,last_full_day=end,
            any_complete_before_validate=int(early>0),
            possible_training_available=int(early>=2),
            theoretical_probability_per_draw=round(prob_complete(fam["k"]),13)))
    grouped=[]
    for k in sorted(sizes):
        rows=[x for x in familyrows if x["k"]==k]
        grouped.append(dict(k=k,catalogue_families=len(rows),
            combined_full_hits=sum(r["completed_full_hits_72days"] for r in rows),
            combined_train_hits=sum(r["full_before_sept13"] for r in rows),
            combined_validate_hits=sum(r["full_validation"] for r in rows),
            combined_holdout_hits=sum(r["full_holdout"] for r in rows),
            families_no_train_appearance=sum(r["full_before_sept13"]==0 for r in rows),
            families_at_least_twice_train=sum(r["full_before_sept13"]>=2 for r in rows),
            fair_full_family_probability=round(prob_complete(k),13),
            fair_one_sized_ticket_expected_hit=k*.25))
    near=summarize(near_summary,("phase","family_k","previous3_best","hour_min_class"))
    gap=summarize(gap_summary,("phase","stage","family_k"))
    def grouped_early(phase):
        entries=[r for r in near if r["phase"]==phase and r["hour_min_class"]!=999]
        return dict(signal_count=sum(r["opportunities"] for r in entries),
           average_hits=(sum(r["actual_hit_numbers"] for r in entries)/
                sum(r["opportunities"] for r in entries)) if entries else 0,
           same_size_random_avg=(sum(r["mean_random_hits"]*r["opportunities"]
                for r in entries)/sum(r["opportunities"] for r in entries))
                if entries else 0,
           exact_completions=sum(r["actual_full_family_completions"] for r in entries),
           distinct_target_warnings=sum(r["opportunities"] for r in near if
                r["phase"]==phase and r["hour_min_class"]==999))
    summary=[
      "V84 — V9/V10 AILE SISTEMI TAM DIAGNOSTIK MASA USTU DENETIM",
      "Crucial: static v10_aileler.csv was committed on 12 Oct 2026,",
      "already incorporating family patterns from V9 historical reports.",
      "Replay across Aug–Oct12 is NOT evidence of independent forward accuracy.",
      "A K-family = FIXED K exact number set, completely in one 20-ball draw.",
      "4/5 is a historical near-overlap in one of previous up to 3 draws.",
      "Next-draw 'Isabet=1/5' independently measures overlap at actual target.",
      f"Catalogue: {len(fams)} distinct families, sizes: {dict(sorted(sizes.items()))}.",
      f"Corpus: {len(days)} complete days, total {len(days)*217} draws; "
      "incomplete 23Aug dropped, whole day checked sequentially.",
      "Hour support means at least N DIFFERENT prior days with an exact",
      "full-family hit in target CLOCK HOUR, never evidence of a future hit.",
      "At a 'Geliyorum' next-draw check, the target result is excluded from",
      "signals but the CATALOGUE itself may have hindsight selection.",
      "Every family may issue multiple warnings; these are correlated.",
      "Single-policy best alert per distinct target evaluated separately.",
      "MIN_PARTIAL thresholds from live code: "+str(MIN_PARTIAL),
      "",
      "CATALOGUE exact full event counts by family size:"
    ]
    for row in grouped:
        summary.append(f" k{row['k']}: families={row['catalogue_families']}; "
            f"full hits DEV={row['combined_train_hits']}, "
            f"VALID={row['combined_validate_hits']}, "
            f"HOLD={row['combined_holdout_hits']}; "
            f"never full before validation={row['families_no_train_appearance']}, "
            f"2+ full before validation={row['families_at_least_twice_train']}; "
            f"P(exact one predetermined family)={row['fair_full_family_probability']:.11f}")
    summary+=["",
      "RETROSPECTIVE near-partial Geliyorum alert performance (NOT blind):"
    ]
    for phase in ("DEV","VALIDATE","HOLDOUT"):
        a=grouped_early(phase)
        summary.append(f"  {phase}: signals={a['signal_count']} vs "
            f"distinct target warnings={a['distinct_target_warnings']}; "
            f"mean actual family overlap={a['average_hits']:.6f},"
            f" matched random same-k={a['same_size_random_avg']:.6f};"
            f" fully completed={a['exact_completions']}")
    summary+=["","HOLDOUT partial signal performance by family size and original trigger:"]
    for k in sorted(sizes):
        subset=[r for r in near if r["phase"]=="HOLDOUT" and
                r["family_k"]==k and r["hour_min_class"]!=999]
        total=sum(x["opportunities"] for x in subset)
        full=sum(x["actual_full_family_completions"] for x in subset)
        hits=sum(x["actual_hit_numbers"] for x in subset)
        randhits=sum(x["mean_random_hits"]*x["opportunities"] for x in subset)
        if total:
            summary.append(f"  k{k}: {total} alerts, full={full}, "
               f"observed={hits/total:.5f}/{k}, random={randhits/total:.5f}/{k}, "
               f"theory={k/4:.5f}/{k}, expected complete={total*prob_complete(k):.4f}")
    summary+=["","HOLDOUT exact previous-three partial grade for five-member groups:"]
    for p in (4,5):
        s=[r for r in near if r["phase"]=="HOLDOUT" and
          r["family_k"]==5 and r["previous3_best"]==p and r["hour_min_class"]!=999]
        n=sum(x["opportunities"] for x in s)
        hit=sum(x["actual_hit_numbers"] for x in s)
        full=sum(x["actual_full_family_completions"] for x in s)
        summary.append(f"  PREVIOUS {p}/5: {n} signals, next target complete5={full}, "
           f"mean next hits={hit/n:.5f}/5" if n else f"  PREVIOUS {p}/5: zero signals")
    summary+=["","HOLDOUT same-family rhythm targets from earlier-day-supported gap:"]
    for stage in ("1to2","2to3","3to4"):
        ss=[v for v in gap if v["phase"]=="HOLDOUT" and v["stage"]==stage]
        n=sum(v["opportunities"] for v in ss)
        h=sum(v["actual_hit_numbers"] for v in ss)
        full=sum(v["actual_full_family_completions"] for v in ss)
        expected=sum(v["theoretical_full_expected"] or 0 for v in ss)
        rnd=sum(v["mean_random_hits"]*v["opportunities"] for v in ss)
        summary.append(f"  {stage}: target tickets={n}; exact full={full}, "
            f"theory complete≈{expected:.4f}; "
            f"mean actual={h/n:.5f}, random={rnd/n:.5f}" if n else
            f"  {stage}: no eligible targets")
    summary+=["","Per-family size warning and cadence detail are in CSV.",
       "Full-family 1->2,2->3,3->4 timetable: all predicted targets",
       "are evaluated, including the missed/failed signals. Historical",
       "days supporting a particular gap must be >=2, not two observations",
       "within the SAME day. Gap support is built only from earlier days.",
       "Incomplete or stale target families are not silently excluded.",
       "Any apparent advantage must be re-evaluated with a family roster",
       "that was actually frozen BEFORE completely unseen target dates.",
       "Lottery fair null: future ticket hit expectation k/4, exact-family",
       "probability product_{i=0..k-1}(20-i)/(80-i), independent of alarms.",
       ""
    ]
    out=Path(outpath);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_AILELER_TAM_DENETIM_KISA_KARAR.txt","\n".join(summary))
        def outcsv(name,records):
            if not records:return
            with z.open(name,"w",force_zip64=True) as f:
                tx=io.TextIOWrapper(f,encoding="utf-8",newline="")
                writer=csv.DictWriter(tx,fieldnames=list(records[0]))
                writer.writeheader();writer.writerows(records)
                tx.flush();tx.detach()
        outcsv("01_1131_AILE_TAM_CIKIS_TARIHI_GUNLERI.csv",familyrows)
        outcsv("02_AILE_BOYUTUNDA_HISTORIK_GERCEK_TEORIK.csv",grouped)
        outcsv("03_GELIYORUM_4_5_5_5_ON_ISARET_SONRA_KAC_ISABET.csv",near)
        outcsv("04_RITIM_1_2_2_3_3_4_HEDEF_ISABET.csv",gap)
        outcsv("05_RITIM_KUPON_TAM_BASARISIZ_OLAYLAR.csv",signals_detail)
        outcsv("06_HEDEF_BASINA_SADECE_EN_UST_GELIYORUM_KUPON.csv",topwarning)
        outcsv("07_72_GUN_GUNLUK_AILE_TAM_GELIYORUM.csv",perday)
        z.writestr("08_YORUMLAMA_VE_KUSURLAR.txt","\n".join([
          "Any fixed family K has P(all K numbers in one 20/80 draw)",
          "prod((20-i)/(80-i),i=0..K-1). A near trigger does not alter this",
          "under the independent fair lottery null.",
          "Static v10 family index committed on Oct12 2026 from V9 reports.",
          "Past replay may reflect family catalogue chosen after seeing test dates.",
          "Correct fully blind family selection must use only earlier day draws",
          "and freeze catalogue & rules before all next target outcomes.",
          "Current family index is catalogued and replayed here, NOT BLIND.",
          "Early warning code max((mask & family).bit_count() for last3 draw).",
          "It is a historical partial match, NOT next target success.",
          "At least 2 earlier DISTINCT days same clock hour and globally",
          "2 earlier days required by the actual V10 'Geliyorum' gate.",
          "3 days only a stronger supporting flag, not mathematically causal.",
          "Cadence exact first gap, matching triple and quad histories",
          "are learned from distinct PRIOR days, never target day.",
          "Ritualized repeat gaps alone lack evidence for independent lottery.",
          "Random k control depends on fixed hash family+day+slot; target blind.",
          "Signals are highly dependent, so naive p-values not justified.",
          "Never optimize using reused held-out dates or select only winners.",
          "Next milestone should be new dates after immutable forecast registry."
        ]))
        z.writestr("09_AUDIT.json",json.dumps(dict(
          version=VERSION,full_days=days,catalogue_size=len(fams),
          size_counts=dict(sizes),committed_catalogue_date="2026-10-12",
          minimum_partial=MIN_PARTIAL,group_summaries=grouped,
          near_by_phase={p:grouped_early(p) for p in ("DEV","VALIDATE","HOLDOUT")},
          signal_rows=len(signals_detail),top_warning_rows=len(topwarning),
          source_issues=issues[:25],malformed=bad[:25]),
          ensure_ascii=False,indent=2))
    print("\n".join(summary),flush=True)
    print("V84 OUTPUT",out,out.stat().st_size,flush=True)

def selftest():
    assert prob_complete(5)>prob_complete(6)>prob_complete(7)
    assert MIN_PARTIAL[5]==4 and MIN_PARTIAL[10]==7
    assert fmask([2,4,9]).bit_count()==3
    assert (fmask([2,4])&fmask([4,7])).bit_count()==1
    assert target_control("a","2026-10-01",12,5,fmask(range(1,21)))==\
      target_control("a","2026-10-01",12,5,fmask(range(1,21)))
    print("V84 SELFTEST OK")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",default="veri.txt")
    parser.add_argument("--families",default="v10_aileler.csv")
    parser.add_argument("--out",default="v84_output/V84_72GUN_1131_AILELER_TAM_DENETIM_GELIYORUM_RITIM.zip")
    parser.add_argument("--selftest",action="store_true")
    a=parser.parse_args()
    if a.selftest:selftest()
    else:run(a.source,a.families,a.out)
