#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V68 — Temperature+direction -> candidate 15/20 pools -> historic 20-set overlap.

Chronological 217-slot experiment. Only 71 earlier COMPLETE days and earlier
draws within the focus day may train any score. A history overlap of 15+ is
so improbable that its absence has no inherent predictive power. The historical
"lowest/most overlap" preference is an EXPLORATORY comparison with fixed
temperature and random baselines, not a validated winning-ticket algorithm.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,random,statistics,zipfile
from collections import Counter,defaultdict
from pathlib import Path
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V68"
METHODS=("FREQ20","HEAT_TREND20","HEAT_LOW20","HEAT_HIGH20",
         "LOW15_LOW20","LOW15_HIGH20","HIGH15_LOW20","HIGH15_HIGH20","RANDOM20")
K_TICKET=(5,6,8,10)
N_CORE_VARIANTS=14
N_COMPLETIONS=9
SEED=681015
POOL_STATE=("SOGUK","SERIN","NOTR","ILIK","SICAK")
LIMITS=(14,16,19,21,72)

def seed(*parts):
    b=("V68|"+ "|".join(map(str,parts))).encode()
    return int.from_bytes(hashlib.sha256(b).digest()[:8],"big")

def bitset(nums):
    return sum(1<<(int(n)-1) for n in nums)

def history_profile(pool,prior_masks):
    """Exact one-overlap-count per past 20-number DRAW, no subset duplication."""
    s=bitset(pool);h=[0]*(len(pool)+1)
    for mask in prior_masks:h[(mask&s).bit_count()]+=1
    if sum(h)!=len(prior_masks):raise AssertionError("history count mismatch")
    return tuple(h)

def overlap_score(profile,kind):
    # Match the core/pool to upper tail of 20-in-history overlap.
    # Includes no information from the future target.
    if kind==15:
        return sum(profile[8:])+2*sum(profile[9:])+4*sum(profile[10:])
    if kind==20:
        return sum(profile[10:])+2*sum(profile[11:])+4*sum(profile[12:])
    raise ValueError(kind)

def rng_top_n(rng,universe,n):
    return tuple(sorted(rng.sample(list(universe),n)))

def eligible_data(file):
    records,issues,malformed=parse_txt(file)
    complete=sorted(d for d,rows in records.items()
          if len(rows)==217 and [r["pos"] for r in rows]==list(range(1,218)))
    if len(complete)<72:raise ValueError("72 complete days required")
    focus=complete[71];prior=complete[:71]
    prev=[r for d in prior for r in records[d]]
    day=records[focus]
    partial={d:len(v) for d,v in records.items() if d not in complete}
    return focus,prev,day,prior,partial,issues,malformed

def feature_snapshots(prior_draws):
    last72=prior_draws[-72:]
    last24=prior_draws[-24:]
    previous24=prior_draws[-48:-24]
    f=Counter(n for row in last72 for n in row["nums"])
    late=Counter(n for row in last24 for n in row["nums"])
    early=Counter(n for row in previous24 for n in row["nums"])
    d={n:late[n]-early[n] for n in range(1,81)}
    heat={n:f[n]+0.60*d[n] for n in range(1,81)}
    # no target draw used in the rank; deterministic number tie breaks
    order=sorted(range(1,81),key=lambda n:(-heat[n],-f[n],n))
    pure=sorted(range(1,81),key=lambda n:(-f[n],n))
    state={n:POOL_STATE[next(i for i,upper in enumerate(LIMITS) if f[n]<=upper)]
           for n in range(1,81)}
    return order,pure,f,d,heat,state

def family_candidates(base10,ordered,rng):
    """Top10 always kept; 14 alternative 15-set cores before historical scoring."""
    selectable=ordered[10:37]
    first=tuple(sorted(ordered[:15]))
    candidates=[first]
    seen={first}
    for _ in range(200):
        extra=tuple(sorted(rng.sample(selectable,5)))
        candidate=tuple(sorted(set(base10)|set(extra)))
        if candidate not in seen:
            candidates.append(candidate);seen.add(candidate)
            if len(candidates)>=N_CORE_VARIANTS:break
    assert len(candidates)==N_CORE_VARIANTS
    return candidates

def select_core15(order,prior_masks,slot):
    rng=random.Random(seed(slot,"core"))
    candidates=family_candidates(order[:10],order,rng)
    results=[(x,history_profile(x,prior_masks)) for x in candidates]
    by_score=lambda v: (overlap_score(v[1],15),v[0])
    minimum=min(results,key=by_score)
    maximum=max(results,key=by_score)
    return {"HEAT":results[0],"LOW":minimum,"HIGH":maximum},results

def tail_pool(core,order,prior_masks,slot,label):
    rng=random.Random(seed(slot,"tail",label))
    # All methods select 5 candidates from the SAME hot/warming ranked 37 numbers.
    ranked=[n for n in order[:37] if n not in core]
    first=tuple(sorted(ranked[:5]))
    extras=[first];seen={first}
    for _ in range(160):
        x=tuple(sorted(rng.sample(ranked,5)))
        if x not in seen:
            seen.add(x);extras.append(x)
            if len(extras)>=N_COMPLETIONS:break
    assert len(extras)==N_COMPLETIONS
    candidates=[]
    for tail in extras:
        nums=tuple(sorted(set(core)|set(tail)))
        assert len(nums)==20
        profile=history_profile(nums,prior_masks)
        candidates.append((nums,profile,tail))
    low=min(candidates,key=lambda v:(overlap_score(v[1],20),v[0]))
    high=max(candidates,key=lambda v:(overlap_score(v[1],20),v[0]))
    return {"FIRST":candidates[0],"LOW":low,"HIGH":high},candidates

def group_scores(order,pure,prior_masks,slot):
    cores,core_all=select_core15(order,prior_masks,slot)
    heat,heat_profile=cores["HEAT"]
    low,low_profile=cores["LOW"]
    high,high_profile=cores["HIGH"]
    h20,h_all=tail_pool(heat,order,prior_masks,slot,"HEAT")
    lo20,l_all=tail_pool(low,order,prior_masks,slot,"LOW")
    hi20,hi_all=tail_pool(high,order,prior_masks,slot,"HIGH")
    freq20=tuple(sorted(pure[:20]))
    heat20=tuple(sorted(order[:20]))
    rand20=rng_top_n(random.Random(seed(slot,"RNG20")),range(1,81),20)
    selections={
       "FREQ20":(freq20,history_profile(freq20,prior_masks)),
       "HEAT_TREND20":(heat20,history_profile(heat20,prior_masks)),
       "HEAT_LOW20":h20["LOW"][:2],
       "HEAT_HIGH20":h20["HIGH"][:2],
       "LOW15_LOW20":lo20["LOW"][:2],
       "LOW15_HIGH20":lo20["HIGH"][:2],
       "HIGH15_LOW20":hi20["LOW"][:2],
       "HIGH15_HIGH20":hi20["HIGH"][:2],
       "RANDOM20":(rand20,history_profile(rand20,prior_masks))
    }
    core_selections={"HEAT15":cores["HEAT"],"LOW15":cores["LOW"],"HIGH15":cores["HIGH"]}
    extra=dict(core_candidates=len(core_all),completions_each=len(h_all),
               hot10=tuple(order[:10]),
               core15_range=[min(overlap_score(v[1],15) for v in core_all),
                             max(overlap_score(v[1],15) for v in core_all)])
    return selections,core_selections,extra

def ticket(pool,method,order,pure,size):
    if method=="FREQ20":return tuple(sorted(pure[:size]))
    if method=="HEAT_TREND20":return tuple(sorted(order[:size]))
    if method=="RANDOM20":
        return tuple(sorted(random.Random(seed(pool,size,"RANDOM_TICKET")).sample(pool,size)))
    # Choosing core and tail: reserve 5 hottest members of the original
    # (history-selected) 15-core, add 1/3/5 from the selected completion.
    # The pool is a 20-set; recover its "original core" from methods separately
    raise ValueError("Provide core separately for history-selected methods")

def historical_ticket(pool,core,order,size):
    assert len(core)==15 and set(core)<=set(pool)
    tail=set(pool)-set(core)
    assert len(tail)==5
    first=sorted(core,key=lambda n:order.index(n))[:5]
    rest=sorted(tail,key=lambda n:order.index(n))[:size-5]
    return tuple(sorted(first+rest))

def k_stats(ticket,actual):
    return len(set(ticket)&set(actual))

def _csv(z,name,rows,columns=None):
    if not rows and not columns:raise ValueError(name)
    cols=columns or list(rows[0])
    with z.open(name,"w",force_zip64=True) as raw:
        ioout=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        writer=csv.DictWriter(ioout,fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)
        ioout.flush();ioout.detach()

def fair_tail(n,k,lower):
    denom=math.comb(80,n)
    return sum(math.comb(20,x)*math.comb(60,n-x)
        for x in range(lower,min(n,20)+1))/denom

def run(source,out):
    focus,early,day,prior_dates,partial,issues,malformed=eligible_data(source)
    before=list(early)
    hist_masks=[bitset(row["nums"]) for row in before]
    true_rows=[];pool15rows=[];ticketrows=[];temp_rows=[];audit_rows=[]
    series=defaultdict(Counter)
    for i,target in enumerate(day):
        slot=i+1
        order,pure,freq,direction,score,state=feature_snapshots(before)
        proposals,cores,extra=group_scores(order,pure,hist_masks,slot)
        actual=set(target["nums"])
        for n in range(1,81):
            temp_rows.append(dict(slot=slot,draw_id=target["id"],number=n,
                 prior72_occurrences=freq[n],late24_minus_early24=direction[n],
                 weighted_score=round(score[n],3),temperature=state[n],
                 heat_rank=order.index(n)+1,target_hit=int(n in actual)))
        for label,(core15,hp) in cores.items():
            hits=k_stats(core15,actual)
            profile={"hist_overlap_"+str(k):hp[k] for k in range(8,16)}
            pool15rows.append(dict(slot=slot,draw_id=target["id"],
               method=label,core15=",".join(map(str,core15)),
               hits15=hits,fair_mean=3.75,past_draws=len(before),
               score15=overlap_score(hp,15),max_past_overlap=max(k for k,c in enumerate(hp) if c),
               **profile))
            series[(label,15)].update([hits])
        for method,(pool,hp) in proposals.items():
            core_label=("HEAT15" if method.startswith("HEAT_") else
              "LOW15" if method.startswith("LOW15_") else
              "HIGH15" if method.startswith("HIGH15_") else "")
            core=cores[core_label][0] if core_label else ()
            hits=k_stats(pool,actual)
            row=dict(date=focus,slot=slot,draw_id=target["id"],clock=target["time"],
                method=method,past_draws=len(before),
                pool20=",".join(map(str,pool)),pool20_hits=hits,
                expected_hits20=5,history_ge9=sum(hp[9:]),
                history_ge10=sum(hp[10:]),history_ge11=sum(hp[11:]),
                history_ge12=sum(hp[12:]),history_ge13=sum(hp[13:]),
                history_ge14=sum(hp[14:]),history_ge15=sum(hp[15:]),
                max_historical_overlap=max(k for k,c in enumerate(hp) if c),
                structure_score=overlap_score(hp,20),core15_label=core_label,
                core15=",".join(map(str,core)) if core else "",
                **{"hist_exact_"+str(k):hp[k] for k in range(8,21)})
            true_rows.append(row)
            series[(method,20)].update([hits])
            for size in K_TICKET:
                if core_label:t=historical_ticket(pool,core,order,size)
                else:t=ticket(pool,method,order,pure,size)
                hit=k_stats(t,actual)
                ticketrows.append(dict(slot=slot,draw_id=target["id"],
                    method=method,ticket_size=size,ticket=",".join(map(str,t)),
                    hit=hit,expected_hit=size/4,
                    full_hit=int(hit==size)))
                series[(method,size,"ticket")].update([hit])
        audit_rows.append(dict(slot=slot,draw_id=target["id"],
            training_draws=len(before),core_candidates=extra["core_candidates"],
            completions_per_core=extra["completions_each"],
            all_methods_created=len(proposals),
            top10_hot=",".join(map(str,extra["hot10"])),
            core15_score_min=extra["core15_range"][0],
            core15_score_max=extra["core15_range"][1],
            target_excluded=True))
        if i in (0,49,99,149,199,216):
            print(f"V68 calculated slot {slot}/217 target=#{target['id']} past={len(before)}",flush=True)
        # The target is revealed only AFTER all selections and scores are frozen.
        before.append(target);hist_masks.append(bitset(target["nums"]))

    mean=lambda vals:sum(vals)/len(vals)
    def summarise(method,kind,values):
        v=list(values.elements()) if isinstance(values,Counter) else list(values)
        n=len(v);expected=kind/4
        avg=mean(v);sd=statistics.stdev(v)
        return dict(method=method,selection_size=kind,draws=n,mean_hits=round(avg,6),
             fair_expected_mean=expected,difference_from_fair=round(avg-expected,6),
             best_hits=max(v),full_matches=sum(x==kind for x in v),
             rng_expected_full_matches=round(n*math.comb(20,kind)/math.comb(80,kind),6),
             ci_95_indicative_low=round(avg-1.96*sd/math.sqrt(n),5),
             ci_95_indicative_high=round(avg+1.96*sd/math.sqrt(n),5),
             hit_distribution=";".join(f"{j}:{v.count(j)}" for j in range(kind+1)))
    totals=[]
    for method in METHODS:totals.append(summarise(method,20,series[(method,20)]))
    for method in ("HEAT15","LOW15","HIGH15"):
        totals.append(summarise(method,15,series[(method,15)]))
    for method in METHODS:
        for k in K_TICKET:
            s=summarise(method,k,series[(method,k,"ticket")])
            s["method"]=method+"_TICKET"+str(k)
            totals.append(s)
    # within-draw paired comparator vs HEAT_TREND20, without treating
    # retrospectively selected methods or prior research as genuine holdout
    base20=[r["pool20_hits"] for r in true_rows if r["method"]=="HEAT_TREND20"]
    btickets=[r["hit"] for r in ticketrows if r["method"]=="HEAT_TREND20" and r["ticket_size"]==10]
    paired=[]
    for method in METHODS:
        if method=="HEAT_TREND20":continue
        for k,vals,baseline in (
            (20,[r["pool20_hits"] for r in true_rows if r["method"]==method],base20),
            (10,[r["hit"] for r in ticketrows if r["method"]==method and r["ticket_size"]==10],btickets)):
            diffs=[a-b for a,b in zip(vals,baseline)]
            stdev=statistics.stdev(diffs)
            se=stdev/math.sqrt(len(diffs))
            paired.append(dict(method=method,selection_size=k,
                paired_mean_gain_over_heat_trend=round(mean(diffs),6),
                paired_mean_gain_ci95_low=round(mean(diffs)-1.96*se,5),
                paired_mean_gain_ci95_high=round(mean(diffs)+1.96*se,5),
                improved_slots=sum(v>0 for v in diffs),
                worse_slots=sum(v<0 for v in diffs),
                tied_slots=sum(v==0 for v in diffs)))
    topline=[f"V68 | 15 / 20 SICAKLIK-YON + GECMIS 20LIK ORTUSME | {focus}",
        f"Prior complete days: {len(prior_dates)}; prior draws: {len(early)}; test draws: {len(day)}",
        f"Day first drawing: #{day[0]['id']} {day[0]['time']}; final #{day[-1]['id']} {day[-1]['time']}",
        "Strict chronological selection: ONLY historical draws before each target included.",
        "217 targets x 14 alternative heated 15-number cores, 3 core variants,",
        "9 alternative completions per core; rank using true past 20-draw overlap tails.",
        "Comparison includes pure hot, hot+direction, history-low/high, and seeded random.",
        "The random 20 target fair expectation is 5, 15 target 3.75, 10-ticket 2.5.",
        "No '15+ never seen' exclusion: nearly all candidate20 would pass by chance.",
        "20-set history distribution counts EACH past drawing ONCE (exact shared members).",
        "Selected sets are NOT drawn from known target numbers and are not lookahead.",
        "Previously explored historic draws -> retrospective exploratory work only.",
        "No claimed predictive advantage; many comparisons can generate spurious winners.",
        "",
        "METHOD SUMMARY (20 pool, avg hits against 217 true draws):"]
    for m in METHODS:
        t=next(z for z in totals if z["method"]==m and z["selection_size"]==20)
        topline.append(f"{m:19} {t['mean_hits']:.5f}/20 (random expectation 5), max={t['best_hits']}; full20={t['full_matches']}")
    topline.append("")
    topline.append("10 TICKET (from same frozen 20 pool, one ticket per target):")
    for m in METHODS:
        t=next(z for z in totals if z["method"]==m+"_TICKET10")
        topline.append(f"{m:19} {t['mean_hits']:.5f}/10 (random expectation 2.5), max={t['best_hits']}; full10={t['full_matches']}")
    topline.append("")
    topline.append("15 CORE (same target draw):")
    for m in ("HEAT15","LOW15","HIGH15"):
        t=next(z for z in totals if z["method"]==m and z["selection_size"]==15)
        topline.append(f"{m:19} {t['mean_hits']:.5f}/15 (random expectation 3.75), max={t['best_hits']}")
    topline.append("")
    topline.append("Read 00_SONUC_OZET.csv and 05_ESLESMELI_KARSILASTIRMA.csv for all exact counts.")
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        z.writestr("00_ANA_SONUC_V68.txt","\n".join(topline)+"\n")
        _csv(z,"00_SONUC_OZET.csv",totals)
        _csv(z,"01_217_CEKILIS_X_9_YONTEM_20LIK_HAVUZLAR.csv",true_rows)
        _csv(z,"02_217_CEKILIS_X_3_YONTEM_15LIK_CEKIRDEK.csv",pool15rows)
        _csv(z,"03_217_CEKILIS_5_6_8_10_KUPON_KOR_TEST.csv",ticketrows)
        _csv(z,"04_SICAK_SOGUK_ILIK_YON_217_X_80.csv",temp_rows)
        _csv(z,"05_ESLESMELI_KARSILASTIRMA.csv",paired)
        _csv(z,"06_HER_CEKILIS_DENETIM.csv",audit_rows)
        z.writestr("07_METODOLOJI.txt","\n".join([
            "V68 experiment. No target number used before prediction.","Input: repo veri.txt parsed and validated by v52 normalise_rows.",
            "71 earlier complete days (71*217 draws) plus earlier same-day draws.",
            "Feature: count of each number in previous 72 draws; score=count72 + 0.6*(last24 - previous24).",
            "V42 five temperature categories from count72: <=14 cold,15..16 cool,17..19 neutral,20..21 warm,>=22 hot.",
            "FREQ20 uses 20 highest count72; HEAT_TREND20 uses 20 highest weighted rank.",
            "14 core candidates: top 10 fixed weighted numbers plus 5 sampled from weighted ranks 11..37.",
            "LOW/HIGH core chosen by 8+/9+/10+ intersection profile against each earlier 20-draw.",
            "Per core 9 candidate complements: 5 chosen among top37 weighted numbers excluding core.",
            "History-low/high completions selected by 10+/11+/12+ overlap counts against past drawings.",
            "20-set structure_score=sum(past overlaps>=10)+2sum(>=11)+4sum(>=12).",
            "15-set structure_score=sum(overlaps>=8)+2sum(>=9)+4sum(>=10).",
            "All comparisons of 15/20 reference past 20-number whole DRAW; one overlap count/draw.",
            "RNG baseline deterministic SHA-derived seed; always independent of target.",
            "History selected K-ticket: 5 best heat in selected15 + highest 1,3,5 heat from selected tail for k6,8,10.",
            "This means historical 5-ticket is same across tail variants sharing a 15-core; controlled fact.",
            "FREQ and HEAT_TREND K-ticket: first k by their corresponding heat rank.",
            "RANDOM20 ticket: deterministic sampling from chosen random pool.",
            "At each slot all pools and tickets generated; THEN actual20 evaluated; THEN target added to history.",
            "Fair per-draw expectation for pool of k predetermined numbers = k/4.",
            "Historical absence of 15+ overlaps is normal for fair RNG and is not positive evidence.",
            "Mean CIs are indicative/unadjusted across many tried methods; no verified advantage claimed.",
            "Focus day was already previously observed in older research; not genuinely unseen prospective evaluation."
        ])+"\n")
        z.writestr("08_DENETIM.json",json.dumps(dict(version=VERSION,
            focus=focus,previous_complete_days=prior_dates,previous_draws=len(early),
            forecast_draws=len(day),methods=METHODS,temperatures=POOL_STATE,
            audit_count=len(audit_rows),pool20_rows=len(true_rows),
            core15_rows=len(pool15rows),ticket_rows=len(ticketrows),
            feature_rows=len(temp_rows),partial_days=partial,
            parse_issues=issues[:20],malformed_lines=malformed[:20],
            historic_overlap_expected_ge10=fair_tail(20,20,10),
            historic_overlap_expected_ge15=fair_tail(20,20,15)),ensure_ascii=False,indent=2))
    print("\n".join(topline),flush=True)
    print("ZIP",out,"bytes",out.stat().st_size,flush=True)
    return topline

def selftest():
    a=tuple(range(1,21));b=tuple(range(11,31));c=tuple(range(31,51))
    p=history_profile(a,[bitset(a),bitset(b),bitset(c)])
    assert len(p)==21 and p[20]==1 and p[10]==1 and p[0]==1
    assert overlap_score(p,20)>0
    assert abs(fair_tail(20,20,10)-0.00394)<0.001
    assert 15 in (len(family_candidates(list(range(1,11)),list(range(1,81)),random.Random(10))[0]),)
    order=list(range(1,81))
    group=tuple(range(1,16))
    t=historical_ticket(tuple(range(1,21)),group,order,10)
    assert len(t)==10 and set(t)<=set(range(1,21))
    print("V68 SELFTEST OK",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",default="veri.txt")
    parser.add_argument("--output",default="v68_output/V68_SICAK_SOGUK_ORTUSME_15_20_HAVUZ_KUPON_KOR_TEST.zip")
    parser.add_argument("--selftest",action="store_true")
    args=parser.parse_args()
    if args.selftest:selftest()
    else:run(args.source,args.output)
