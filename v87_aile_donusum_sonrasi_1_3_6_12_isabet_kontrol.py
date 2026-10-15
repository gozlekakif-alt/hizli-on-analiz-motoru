#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V87 — Family-mutation ACTUAL AFTER-EVENT outcomes; selection before targets.

V86 5–10-ball "natural root" = intersection of the 20 drawn on draw t
with one of the previous 12 consecutive actual draws. The root is born
or EXACT-repeated at t, AFTER seeing draw t, and can only propose a fixed
10-number candidate on FUTURE target draws t+{1,3,6,12}. A structural
parent in the previous 12 draws establishes one/two swap, grow/shrink
relations. Match one nonduplicated event candidate per draw and event
class by deterministic k, shortest provenance lag and number order,
without seeing the next target.

For every class/horizon, audit:
 - full exact family events and mean family hit vs theoretical p(k)
 - actual correct of ten predefined balls vs seeded matched random ten
   and most-frequent ten of previous72 known draws;
 - retained/gained/lost family member appearances relative to actual parent;
 - exact day-block signflip permutation p for 15-day VALIDATE and HOLDOUT.
(With overlapping events and multiple branches, those p are heuristic
 exploratory diagnostics, NOT population-independent proof.)
Only VALIDATE picks one (class,horizon) if >=100 prior proposals;
HOLDOUT is evaluated after the choice frozen, not reselected.
Catalogue V10 is never used; no future target enters ticket creation.
Previously repeatedly explored Aug–Oct12 data is NOT truly unseen.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,random,zipfile
from collections import Counter,defaultdict,deque
from pathlib import Path
from v52_ayni_cekilis_eslikci_217 import parse_txt
from v86_72gun_ailelerin_cekilis_cekilis_soyagaci import (
    event_roots,relation,fs,members,bm,prob_full)

VER="V87.1"
HORIZONS=(1,3,6,12)
CLASSES=("EXACT","SWAP_ONE","SWAP_TWO","GROW_ONE",
         "SHRINK_ONE","GROW_TWO","SHRINK_TWO","ORIGINAL")
PARENTS=("SWAP_ONE","GROW_ONE","SHRINK_ONE",
         "SWAP_TWO","GROW_TWO","SHRINK_TWO")
SEED=871016
MIN_VALID=100
VALID_START="2026-09-13"
HOLD_START="2026-09-28"
LAST_DATE="2026-10-12"
MIN_K=5
MAX_K=10
WINDOW=72
READ_LIMIT=12

def load(src):
    byday,issues,malformed=parse_txt(src)
    days=sorted(day for day,rs in byday.items() if len(rs)==217 and
      [r["pos"] for r in rs]==list(range(1,218)))
    if len(days)!=72 or days[0]!="2026-08-01" or days[-1]!=LAST_DATE:
        raise RuntimeError(f"Unexpected 72 days: {len(days)}")
    rows=[r for day in days for r in byday[day]]
    if len(rows)!=15624 or rows[-1]["id"]!=61845:
        raise RuntimeError("Expected corpus boundary #61845")
    masks=[bm(r["nums"]) for r in rows]
    ids=[r["id"] for r in rows]
    breaks=[i for i in range(1,len(ids)) if ids[i]!=ids[i-1]+1]
    return rows,masks,breaks,issues,malformed

def fixed_seed(*args):
    b="|".join(map(str,args)).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(b,digest_size=8).digest(),"big")

def hot72(history):
    counts=[0]*81
    for m in history:
        for n in members(m):counts[n]+=1
    return counts

def ticket(family,counts):
    ballot=list(members(family))
    for n in sorted(range(1,81),key=lambda v:(-counts[v],v)):
        if len(ballot)==10:break
        if n not in ballot:ballot.append(n)
    if len(ballot)!=10 or len(set(ballot))!=10:
        raise AssertionError("coupon must have 10 unique numbers")
    return tuple(sorted(ballot))

def freq10(counts):
    return tuple(sorted(sorted(range(1,81),
           key=lambda v:(-counts[v],v))[:10]))

def rand10(t,h,event):
    return tuple(sorted(random.Random(fixed_seed(SEED,t,h,event)).
                        sample(range(1,81),10)))

def rand_k(k,t,h,event):
    return tuple(sorted(random.Random(fixed_seed(SEED,"family",t,h,event)).
                        sample(range(1,81),k)))

def discover_class(family,origin_lag,frame,known):
    # Predecessor must exist strictly BEFORE draw t, with <=12 draw gap.
    if family in known:
        return "EXACT",known[family]["mask"],known[family]["created_at"],"EXACT"
    possible=[]
    for oldt,oldmasks in frame:
        for oldm in oldmasks:
            cls=relation(oldm,family)
            if cls in PARENTS:
                possible.append((PARENTS.index(cls),-int(oldm.bit_count()),
                                 -oldt,oldm,cls))
    if possible:
        _,_,_,parent,cls=min(possible)
        return cls,parent,known[parent]["created_at"],cls
    return "ORIGINAL",0,None,"ORIGINAL"

def p_day_signflip(day_total):
    """Exact 2^days signed permutations on observed within-day paired sums.
    Not a valid claim of randomized causality: signals/calendar overlap."""
    vals=list(day_total.values())
    if len(vals)<=1:return 1.0
    # Dynamic sign-change partial sums; 15 validation + 15 holdout days
    # at most 32768 combinations, and integer differences in draws.
    sums=[0]
    for d in vals:
        sums=[z+d for z in sums]+[z-d for z in sums]
    observed=sum(vals)
    extreme=sum(z>=observed for z in sums)
    return extreme/len(sums)

def writecsv(z,name,rows):
    if not rows:return
    with z.open(name,"w",force_zip64=True) as f:
        tx=io.TextIOWrapper(f,encoding="utf-8",newline="")
        w=csv.DictWriter(tx,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
        tx.flush();tx.detach()

def run(src,outpath):
    rows,y,breaks,issues,bad=load(src)
    # prefix breaks allow event t to target t+h ONLY over confirmed
    # consecutive real IDs; not across 23Aug missing-day gap.
    flags=[0]*len(rows)
    for i in breaks:flags[i]=1
    cp=[0]*(len(rows)+1)
    for i,f in enumerate(flags):cp[i+1]=cp[i]+f
    def consistent(t,h):
        return t+h<len(rows) and cp[t+h+1]==cp[t+1]
    known={}
    previous=deque(maxlen=12)
    historical=deque(maxlen=72)
    identity_types=Counter()
    origin_days=defaultdict(lambda:Counter())
    selected_events=[]
    forecasts=[]
    features={}
    for t,row in enumerate(rows):
        if t and flags[t]:
            previous.clear();historical.clear()
        current,crossed=event_roots(t,rows,y)
        pertype=defaultdict(list)
        for m,origin in current.items():
            if not MIN_K<=m.bit_count()<=MAX_K:
                raise AssertionError("Out-of-range family")
            cls,parent,firstindex,rel=discover_class(m,origin["lag"],previous,known)
            pertype[cls].append((m,origin,parent))
            identity_types[cls]+=1
            origin_days[row["day"]][cls]+=1
        # Update previous results up through CURRENT OBSERVED DRAW t.
        historical.append(y[t])
        count=hot72(historical)
        bestfreq=freq10(count)
        for cls in CLASSES:
            available=pertype.get(cls)
            if not available:continue
            # This is a deterministic single-event choice based exclusively
            # on current/previous draws, not the later target.
            selected=min(available,key=lambda x:(
                -x[0].bit_count(), x[1]["lag"],x[0]))
            fm,srcinfo,parent=selected
            famsize=fm.bit_count()
            cp10=ticket(fm,count)
            oldm=parent if parent else 0
            retain=fm&oldm;gained=fm&~oldm;lost=oldm&~fm
            evt_id=fs(fm)
            desc=dict(from_day=row["day"],from_clock=row["time"],
                event_draw_id=row["id"],family=evt_id,k=famsize,
                event_class=cls,source_draw_id=rows[srcinfo["parent_index"]]["id"],
                source_lag=srcinfo["lag"],
                previous_family=fs(oldm) if oldm else "",
                retained=fs(retain) if retain else "",
                gained=fs(gained) if gained else "",
                lost=fs(lost) if lost else "",
                retain_k=retain.bit_count(),
                gained_k=gained.bit_count(),lost_k=lost.bit_count(),
                coupon10=",".join(map(str,cp10)),
                frequency_control10=",".join(map(str,bestfreq)))
            selected_events.append(desc)
            for h in HORIZONS:
                if not consistent(t,h):continue
                future=rows[t+h]
                if future["day"]<VALID_START:phase="DEV"
                elif future["day"]<HOLD_START:phase="VALIDATE"
                else:phase="HOLDOUT"
                actual=y[t+h]
                rng=rand10(row["id"],h,evt_id)
                rngfam=rand_k(famsize,row["id"],h,evt_id)
                hit=(fm&actual).bit_count()
                rdict=dict(event_day=row["day"],
                    event_draw_id=row["id"],event_clock=row["time"],
                    target_day=future["day"],target_draw_id=future["id"],
                    target_clock=future["time"],phase=phase,
                    event_class=cls,horizon=h,k=famsize,
                    family=evt_id,
                    family_hit=hit,family_full=int(hit==famsize),
                    family_expected=famsize*.25,
                    family_random_same_k_hit=(bm(rngfam)&actual).bit_count(),
                    coupon10_hits=(bm(cp10)&actual).bit_count(),
                    random10_hits=(bm(rng)&actual).bit_count(),
                    freq10_hits=(bm(bestfreq)&actual).bit_count(),
                    retained_k=retain.bit_count(),
                    retained_hit=(retain&actual).bit_count(),
                    gained_k=gained.bit_count(),
                    gained_hit=(gained&actual).bit_count(),
                    lost_k=lost.bit_count(),
                    lost_hit=(lost&actual).bit_count(),
                    historical_root_source_lag=srcinfo["lag"],
                    selected_coupon10=",".join(map(str,cp10)),
                    target_20=",".join(map(str,future["nums"])))
                # Validation/holdout only full per-event ledger, dev aggregates
                # enough for potential counterfactual train-baseline sanity.
                forecasts.append(rdict)
        # Birth and repeat identity recorded AFTER current draw; parent lookup
        # for this draw cannot use any root just discovered on this draw.
        for fm,srcinfo in current.items():
            if fm not in known:
                known[fm]=dict(mask=fm,created_at=t,
                    source=rows[srcinfo["parent_index"]]["id"],
                    first_draw=row["id"])
        previous.append((t,tuple(current)))
        if t%3000==0:
            print("V87 step",t+1,"roots known",len(known),
                  "selected",len(selected_events),
                  "forecasts",len(forecasts),flush=True)
    grouped=defaultdict(list)
    for x in forecasts:grouped[(x["phase"],x["event_class"],x["horizon"])].append(x)
    summaryrows=[]
    for (phase,cls,h),arr in sorted(grouped.items()):
        n=len(arr)
        if not n:continue
        count=Counter(x["k"] for x in arr)
        one=sum(x["family_hit"] for x in arr)
        one_random=sum(x["family_random_same_k_hit"] for x in arr)
        complete=sum(x["family_full"] for x in arr)
        expected_full=sum(count[k]*prob_full(k) for k in count)
        hp=sum(x["coupon10_hits"] for x in arr)
        hr=sum(x["random10_hits"] for x in arr)
        hf=sum(x["freq10_hits"] for x in arr)
        days=defaultdict(int)
        for x in arr:
            days[x["target_day"]]+=x["coupon10_hits"]-x["random10_hits"]
        signflip=p_day_signflip(days) if phase in ("VALIDATE","HOLDOUT") else None
        r_ret=sum(x["retained_hit"] for x in arr)
        n_ret=sum(x["retained_k"] for x in arr)
        r_gain=sum(x["gained_hit"] for x in arr)
        n_gain=sum(x["gained_k"] for x in arr)
        r_lost=sum(x["lost_hit"] for x in arr)
        n_lost=sum(x["lost_k"] for x in arr)
        summaryrows.append(dict(phase=phase,event_class=cls,horizon=h,
            proposed_tickets=n,draw_days=len(days),
            family_size_counts=";".join(f"{k}:{num}" for k,num in sorted(count.items())),
            avg_family_hit=round(one/n,7),
            avg_size_matched_random_family_hit=round(one_random/n,7),
            theoretical_family_hit=round(sum(x["k"]*.25 for x in arr)/n,7),
            full_family_n=complete,
            fair_expected_full=round(expected_full,7),
            coupon10_avg=round(hp/n,7),
            random10_avg=round(hr/n,7),
            freq10_avg=round(hf/n,7),
            coupon10_minus_random=round((hp-hr)/n,7),
            day_signflip_one_sided_p=round(signflip,7) if signflip is not None else "",
            retained_target1_pct=round(100*r_ret/n_ret,5) if n_ret else "",
            gained_target1_pct=round(100*r_gain/n_gain,5) if n_gain else "",
            lost_target1_pct=round(100*r_lost/n_lost,5) if n_lost else "",
            tenhit_7plus=sum(x["coupon10_hits"]>=7 for x in arr),
            tenhit_8plus=sum(x["coupon10_hits"]>=8 for x in arr),
            tenhit_9plus=sum(x["coupon10_hits"]>=9 for x in arr),
            tenhit_10of10=sum(x["coupon10_hits"]>=10 for x in arr)))
    valid=[r for r in summaryrows if r["phase"]=="VALIDATE"
           and r["proposed_tickets"]>=MIN_VALID]
    # One fixed validation selected signal family class+h; for ties favor
    # more support, shorter horizon then predetermined class order.
    valid.sort(key=lambda z:(-z["coupon10_minus_random"],
         -z["proposed_tickets"],z["horizon"],CLASSES.index(z["event_class"])))
    chosen=valid[0] if valid else None
    hold=next((r for r in summaryrows if chosen and r["phase"]=="HOLDOUT"
       and r["event_class"]==chosen["event_class"]
       and r["horizon"]==chosen["horizon"]),None)
    winner_events=[x for x in forecasts if
      chosen and x["phase"]=="HOLDOUT"
      and x["event_class"]==chosen["event_class"]
      and x["horizon"]==chosen["horizon"]]
    # Pre-defined primary hypothesis families' t+1, never reselect after data.
    oneblock=[x for x in summaryrows if x["phase"]=="HOLDOUT" and
          x["horizon"]==1]
    trajectory=[]
    for cls in CLASSES:
        line=[r for r in summaryrows if r["phase"]=="HOLDOUT"
             and r["event_class"]==cls]
        if not line:continue
        trajectory.append(dict(event_class=cls,
            n_horizon1=next((x["proposed_tickets"] for x in line if x["horizon"]==1),0),
            h1_family1_pct=round(100*next((x["avg_family_hit"]/
                  x["theoretical_family_hit"]*.25 for x in line if x["horizon"]==1),.25),5),
            h1_mean10=next((x["coupon10_avg"] for x in line if x["horizon"]==1),None),
            h1_rand10=next((x["random10_avg"] for x in line if x["horizon"]==1),None),
            h1_full_count=next((x["full_family_n"] for x in line if x["horizon"]==1),None),
            h3_mean10=next((x["coupon10_avg"] for x in line if x["horizon"]==3),None),
            h6_mean10=next((x["coupon10_avg"] for x in line if x["horizon"]==6),None),
            h12_mean10=next((x["coupon10_avg"] for x in line if x["horizon"]==12),None)))
    # Multiple testing adjustment over all <=32 explorations, even before
    # selecting validation leader. It is an indicative screen, not a
    # trustworthy confirmation when holdout was studied in earlier V runs.
    checks=len(CLASSES)*len(HORIZONS)
    leading_p=(hold or {}).get("day_signflip_one_sided_p")
    conservative_min=float(leading_p)*checks if leading_p not in (None,"") else None
    report=[
        "V87 — AILE DONUSUMUNDEN SONRAKI 1,3,6,12 CEKILIS GERCEK TEST",
        "V86 natural family roots recomputed chronologically from true",
        "intersection of each drawn20 and one of previous <=12 draws.",
        "One deterministic event per transformation type (per draw).",
        "The event is only known AFTER its origin draw; all target tickets",
        "are locked BEFORE the later result at t+1,t+3,t+6 or t+12.",
        f"Full days=72; draws={len(rows)}; missing-ID boundaries={breaks}.",
        f"Distinct naturally discovered exact 5..10 family identities={len(known)}.",
        f"Origin event type (EVERY family, before one-per-type filter): {dict(identity_types)}",
        f"Selected events one per type per draw={len(selected_events)}.",
        f"Actual target-labelled future event rows (four horizons)={len(forecasts)}.",
        "Mean correct of a 10-ball ticket under fair independent RNG=2.5.",
        "Family count K expected K/4; exact-full chance pK is tiny.",
        "The selected type+lag is chosen on validation ONLY, not holdout.",
        "",
        "HOLDOUT 28Sep–12Oct: family transformation --> NEXT DRAW t+1:",
    ]
    for r in sorted(oneblock,key=lambda x:CLASSES.index(x["event_class"])):
        report.append(
          f"  {r['event_class']:11} n={r['proposed_tickets']:5},"
          f" mean10={r['coupon10_avg']:.5f}, random10={r['random10_avg']:.5f},"
          f" meanFamily={r['avg_family_hit']:.5f},"
          f" expectedFamily={r['theoretical_family_hit']:.5f},"
          f" fullK={r['full_family_n']},"
          f" expectedFullK={r['fair_expected_full']:.3f};"
          f" retained1={r['retained_target1_pct']},"
          f" gained1={r['gained_target1_pct']},"
          f" lost1={r['lost_target1_pct']}")
    report+=["",
        f"Validation comparisons >= {MIN_VALID} tickets: {len(valid)} out of "
        f"{checks} class x horizon choices." ]
    if chosen and hold:
        report+= [
          f"VALIDATION FROZEN best type={chosen['event_class']} "
          f"horizon={chosen['horizon']}, validation mean10={chosen['coupon10_avg']:.6f},"
          f" random10={chosen['random10_avg']:.6f}, n={chosen['proposed_tickets']}.",
          f"HOLDOUT fixed SAME type+horizon: mean10={hold['coupon10_avg']:.6f},"
          f" random10={hold['random10_avg']:.6f},"
          f" freq10={hold['freq10_avg']:.6f},"
          f" diff={hold['coupon10_minus_random']:+.6f};"
          f" p≈{hold['day_signflip_one_sided_p']:.7f},"
          f" 10of10={hold['tenhit_10of10']},"
          f" 7plus={hold['tenhit_7plus']};"
          f" indicative Bonferroni p upper={min(1,conservative_min):.7f}.",
        ]
    else:report.append("No qualifying validation signals; no winner.")
    report+=["",
      "CAVEAT: previous versions analyzed these historical dates, so",
      "this is an exploratory chronological test, not untouched real-time.",
      "Large family overlap and many tested types require multiple-test",
      "caution. Exact day signflip is an indicative, not magically causal p.",
      "Pre-target family recurrence, one/two swap and grow/shrink signals",
      "must outperform matched RANDOM in an unseen future period.",
      "Parent gained/lost/retained members should each appear ~25% if",
      "future 20/80 draws are fair and independent. A mutation event from",
      "a drawn target does not create a physical predictive mechanism."
    ]
    out=Path(outpath);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=5,allowZip64=True) as z:
        z.writestr("00_V87_KISA_DENETIM_SONUC.txt","\n".join(report))
        writecsv(z,"01_TUM_SINIFLAR_4_UFUK_VAL_HOLD_10LU_ISABET.csv",summaryrows)
        writecsv(z,"02_SON15GUN_HER_YAPI_TIPI_1_3_6_12_OZET.csv",trajectory)
        writecsv(z,"03_HEDEF_ONCESI_SECILEN_KILITLI_SINIF_UFUK.csv",[chosen] if chosen else [])
        writecsv(z,"04_KILITLI_TEST_TUM_GERCEK_KUPONLAR.csv",winner_events)
        writecsv(z,"05_HER_CEKILIS_TIPI_SECILMIS_AILE_VE_10LU.csv",selected_events)
        # Full audit of every deterministic pre-target class/horizon event
        # needed to distinguish high-looking successful from missed cases.
        writecsv(z,"06_BUTUN_1_3_6_12_HEDEF_0_1_KUPON_DENEMELERI.csv",forecasts)
        writecsv(z,"07_OZELLIK_VE_KANIT_SINIRI.csv",[dict(
            key="Natural family",detail="Draw t 20 intersection previous <=12 real draws size5..10"),
            dict(key="Selection",detail="one class family per origin draw; highest k then shortest lag then family number"),
            dict(key="Event classes",detail="EXACT, SWAP_ONE/TWO, GROW_ONE/TWO, SHRINK_ONE/TWO, ORIGINAL"),
            dict(key="Future horizons",detail="t+1, t+3, t+6, t+12; no target peek; no crossing missing ID"),
            dict(key="Controls",detail="same-target deterministic seeded random10, random same-K, past72-freq10"),
            dict(key="Validation/Holdout",detail="Sep13-27 selects class+h; Sep28-Oct12 locked replay"),
            dict(key="Null",detail="20 of 80 fair chance P(one ball)=.25, E[10 correct]=2.5"),
            dict(key="Multiple tests",detail="8 x 4 = 32 nominal signals; avoid winner-only effect stories"),
            dict(key="Confirmation",detail="entire archive explored repeatedly; future truly unseen draws needed"),
        )])
        z.writestr("08_AUDIT.json",json.dumps(dict(
             version=VER,source_draws=len(rows),breaks=breaks,
             frozen_class_names=CLASSES,horizons=HORIZONS,
             root_count=len(known),origin_identity_count=dict(identity_types),
             proposed_events=len(selected_events),scored_events=len(forecasts),
             validation=chosen,holdout=hold,all_metrics=summaryrows,
             upper_bonferroni_p=conservative_min,
             malformed_rows=bad[:30],input_issues=issues[:30]),
             ensure_ascii=False,indent=2))
    print("\n".join(report),flush=True)
    print("V87 ZIP",out,out.stat().st_size,flush=True)

def selftest():
    a=bm([1,2,3,4,5]);b=bm([1,2,3,4,6])
    assert relation(a,b)=="SWAP_ONE"
    assert relation(a,bm([1,2,3,4,5,6]))=="GROW_ONE"
    assert len(ticket(a,[0]*81))==10
    assert len(rand_k(5,61577,6,"hello"))==5
    assert len(rand10(61577,6,"hello"))==10
    assert prob_full(5)>prob_full(6)>0
    assert p_day_signflip({"d1":2,"d2":2})==.25
    print("V87 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v87_output/V87_72GUN_AILE_YAPISAL_SINYAL_4_HEDEF_UFUK.zip")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest()
    else:run(args.source,args.out)
