#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V58: 120 time-indexed family research indicators with day-granular SQLite checkpoints.

Root family = inclusion-maximal intersection of at least two SAME-HOUR 20-number
draws (size 2..20), with exact support >=2. Smaller nested sets are descendants,
not independent root discoveries. Snapshot families from PREVIOUS three completed
hours before observing the current hour. Actual "meeting" = two frozen parent
families both occur IN FULL within one later 20-number draw.

This is descriptive research. A family splitting, merging, migrating, or returning
describes set relations, NOT a causal mechanism of an independent lottery RNG.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from datetime import date,timedelta,datetime,timezone
from itertools import combinations
from pathlib import Path
import hashlib,json,math,random,sqlite3,statistics

from v52_ayni_cekilis_eslikci_217 import parse_txt
from v53_saatlik_degisen_aileler import BLOCKS

VERSION="58.3"
MAX_ROOTS_PER_HOUR=90
MAX_MEETINGS_PER_HOUR=14000
MAX_HOURS_PER_BATCH=18*6
N_SHARDS=12
RECENT_HOURS=3
FORWARD_DAY="2026-10-16"
EXPECTED_PROB={k:math.prod((20-i)/(80-i) for i in range(k)) for k in range(21)}

GROUPS=[
("G01_KIMLIK",["root_count","unique_number_members","root_mean_k","root_max_k","root_k2","root_k3","root_k4","root_k5plus","root_k10plus","root_degree_mean"]),
("G02_BANT",["band_unique_mean","one_band_roots","distinct_band_roots","band_coverage_ratio","odd_fraction","upper40_fraction","mirror_pairs","adjacent_pairs","number_spread_mean","band_entropy_mean"]),
("G03_SAAT_ICI",["support_mean","support_max","support_ge3","support_ge4","first_slot_mean","last_slot_mean","slot_span_mean","slot_gap_mean","long_gap_roots","support_sum"]),
("G04_DONUSUM",["exact_previous","new_roots","lost_previous","one_swap_previous","two_swap_previous","grow_previous","shrink_previous","split_previous","merge_new","return_3hours"]),
("G05_GUNLER",["prev_calendar_roots","prev_calendar_exact","prev_same_clock_roots","prev_same_clock_exact","yesterday_root_family_count","yesterday_size_mean","yesterday_overlap_max","yesterday_one_swap","yesterday_grow","yesterday_lost"]),
("G06_AYRILMA",["prev_one_missing_best","prev_two_missing_best","prev_threeplus_missing_best","prev_zero_any","prev_retained_mean","prev_arrivals_mean","prev_whole_in_draw","prev_fragment_in_draw","prev_not_in_draw","previous_root_count"]),
("G07_BIRLESME",["disjoint_meetings","partial_overlap_meetings","nested_meetings","meeting_events","union_mean_size","union_max_size","repeated_union_events","draws_3plus_families","draws_4plus_families","draws_5plus_families"]),
("G08_AG",["network_nodes","network_active_nodes","network_edges","network_max_degree","network_mean_degree","network_bridge_nodes","network_components","network_largest_component","network_triangles","network_pair_daycross"]),
("G09_SICAKLIK",["hot_members_mean","cold_members_mean","mixed_heat_roots","all_hot_roots","all_cold_roots","hot_share","cold_share","hot_root_count","cold_root_count","neutral_root_count"]),
("G10_RITIM",["hour_interval_mean","daily_prev_any_exact","root_last_first_span_max","root_in_first6","root_in_last6","root_cross_half","root_only_first6","root_only_last6","prior3_exact_roots","max_hour_support"]),
("G11_CEKILIS",["unique_twenty_min","first6_draw_overlap_mean","last6_draw_overlap_mean","first6_root_appearances","last6_root_appearances","draws_2plus_roots","draws_3plus_roots","max_roots_same_draw","draw_band_range_mean","draw_mirror_mean"]),
("G12_RNG",["expected_meetings","observed_meetings","meeting_minus_expected","meeting_over_expected","expected_disjoint","observed_disjoint","expected_overlap","observed_overlap","root_pair_exposures","signal_flag_placeholder"]),
]
METRICS=[(g,n) for g,names in GROUPS for n in names]
assert len(METRICS)==120 and len({n for _,n in METRICS})==120

def serial(f):return "-".join(str(n) for n in sorted(f))
def mask(numbers):
    v=0
    for n in numbers:v|=1<<(n-1)
    return v
def norm(d):
    return {"day":str(d["day"]),"pos":int(d["pos"]),"id":int(d["id"]),
            "time":str(d["time"]),"nums":frozenset(d["nums"])}
def intersect_count(a,b):return (a&b).bit_count()
def avg(xs):return sum(xs)/len(xs) if xs else 0.0
def entropy(vals):
    n=sum(vals)
    return -sum((x/n)*math.log2(x/n) for x in vals if x and n) if n else 0.0
def support_masks(rows):
    masks=[mask(r["nums"]) for r in rows]
    intersections=set()
    for i in range(len(masks)):
        for j in range(i+1,len(masks)):
            common=masks[i]&masks[j]
            if common.bit_count()>=2:intersections.add(common)
    roots=[]
    for candidate in sorted(intersections,key=lambda c:(-c.bit_count(),c)):
        if any(candidate&v==candidate for v in roots):continue
        roots.append(candidate)
    if len(roots)>MAX_ROOTS_PER_HOUR:
        raise ValueError("High root count; no truncation allowed. "
                         "Increase MAX_ROOTS_PER_HOUR after inspection.")
    result=[]
    for fm in roots:
        occurrences=[i for i,dm in enumerate(masks) if dm&fm==fm]
        if len(occurrences)<2:raise AssertionError("root must repeat")
        nums=tuple(i+1 for i in range(80) if fm & (1<<i))
        result.append({"mask":fm,"family":serial(nums),"members":nums,
            "k":len(nums),"support":len(occurrences),"occurrences":occurrences,
            "first":rows[occurrences[0]]["pos"],
            "last":rows[occurrences[-1]]["pos"]})
    return result,masks

def relative_sources(date_iso,hour,history,all_rows):
    # previous <=3 completed hour blocks plus previous-day context,
    # inherited prefilled by day processor
    return history[-RECENT_HOURS:]

def _heat_map(known):
    counts=Counter(x for row in known[-72:] for x in row["nums"])
    nums=sorted(range(1,81),key=lambda n:(counts[n],n))
    return {n:i//16 for i,n in enumerate(nums)}

def analyze_hour(day,hour,draws,prior,prev_day,known_draws):
    """All candidate families and prior contexts frozen before target hour."""
    hour_roots,draw_masks=support_masks(draws)
    current={r["mask"]:r for r in hour_roots}
    latest=prior[-1]["roots"] if prior else []
    past={r["mask"]:r for h in prior for r in h["roots"]}
    roster=list(past.values())
    prev_day_all=prev_day["all_roots"] if prev_day else set()
    prev_same=prev_day["same_hour"].get(hour["code"],set()) if prev_day else set()
    prev_last=prev_day["last_roots"] if prev_day else []
    # Record time boundaries rather than assuming H00->H07 is 5 min.
    hoursource=prior[-1]["name"] if prior else ""
    gap_minutes=None
    if prior:
        dtprev=datetime.fromisoformat(prior[-1]["day"]+"T"+prior[-1]["draws"][-1]["time"])
        dtcur=datetime.fromisoformat(day+"T"+draws[0]["time"])
        gap_minutes=int((dtcur-dtprev).total_seconds()/60)
    # Previously formed roots from only completed hours, not target hour.
    parents=sorted(roster,key=lambda x:(x["k"],x["family"]))
    event=[];graph=defaultdict(set); pair_seen=Counter()
    pair_expectation=Counter(); pair_ops=Counter()
    frozen_pair=[]
    for i,a in enumerate(parents):
        for b in parents[i+1:]:
            union=a["mask"]|b["mask"]
            size=union.bit_count()
            if size>20:continue
            shared=intersect_count(a["mask"],b["mask"])
            rel=("DISJOINT" if shared==0 else
                 "NESTED" if shared==min(a["k"],b["k"]) else "OVERLAP")
            frozen_pair.append((a,b,union,size,shared,rel))
            pair_expectation[rel]+=EXPECTED_PROB[size]*len(draws)
            pair_ops[rel]+=len(draws)
    # Size <=20 and root cap guarantee bounded pair generation. O(n^2)
    # candidates evaluated once per hour; event pairs only when full match.
    activated=[]
    for row,dm in zip(draws,draw_masks):
        matches=[r for r in parents if (r["mask"]&dm)==r["mask"]]
        activated.append(matches)
        for a,b in combinations(matches,2):
            # do not infer causality from shared numbers or root status
            union=a["mask"]|b["mask"]
            k=union.bit_count()
            if k>20:continue
            overlap=intersect_count(a["mask"],b["mask"])
            rel=("DISJOINT" if overlap==0 else "NESTED" if
                overlap==min(a["k"],b["k"]) else "OVERLAP")
            key=tuple(sorted((a["family"],b["family"])))
            pair_seen[key]+=1
            graph[key[0]].add(key[1]);graph[key[1]].add(key[0])
            event.append({"day":day,"hour":hour["code"],
              "draw_id":row["id"],"time":row["time"],"slot":row["pos"],
              "family_a":key[0],"family_b":key[1],
              "shared_count":overlap,"relation":rel,
              "union_size":k,"union":serial(tuple(i+1 for i in range(80) if union&(1<<i))),
              "union_mask":union,"union_repeats":0,
              "a_size":a["k"],"b_size":b["k"],
              "source_hours":("|".join(sorted(set(h["name"] for h in prior
                            if any(r["mask"] in (a["mask"],b["mask"]) for r in h["roots"])))),
              "fair_prob":EXPECTED_PROB[k]})
            if len(event)>MAX_MEETINGS_PER_HOUR:
                raise ValueError("Excess meeting events; fail visibly instead of truncating.")
    um=Counter(r["union_mask"] for r in event)
    for row in event:row["union_repeats"]=sum((m&row["union_mask"])==
                                          row["union_mask"] for m in draw_masks)
    # Previous root => best numeric overlap in newly formed root (if any).
    transitions=[]
    for old in latest:
        f=old["mask"]
        potentials=sorted(hour_roots,key=lambda r:(
            -intersect_count(f,r["mask"]),abs(r["k"]-old["k"]),r["family"]))
        best=potentials[0] if potentials else None
        shared=intersect_count(f,best["mask"]) if best else 0
        exact=(f in current)
        bestkind=("EXACT" if exact else
                  "ONE_SWAP" if best and shared==old["k"]-1 and
                              best["k"]==old["k"] else
                  "TWO_SWAP" if best and shared==old["k"]-2 and
                              best["k"]==old["k"] else
                  "EXPAND" if best and f&best["mask"]==f else
                  "SHRINK" if best and f&best["mask"]==best["mask"] else
                  "PARTIAL" if shared else "LOST")
        # Split heuristic: two distinct (old size -1) active descendant
        # families in target draw pair intersections; classify as possible.
        child=[r for r in hour_roots if r["k"]>=2 and
               r["k"]<old["k"] and r["mask"]&f==r["mask"]]
        pieces=len(child)>=2
        changes=(f^best["mask"]) if best else f
        transitions.append({"day":day,"hour":hour["code"],"source_hour":hoursource,
            "source_family":old["family"],"target_family":best["family"] if best else "",
            "source_size":old["k"],"target_size":best["k"] if best else 0,
            "relation":bestkind,"shared_count":shared,"possible_split":int(pieces),
            "departed":serial(tuple(i+1 for i in range(80)
                       if (f&~(best["mask"] if best else 0)) & (1<<i))),
            "arrived":serial(tuple(i+1 for i in range(80)
                       if (best["mask"]&~f) & (1<<i))) if best else "",
            "gap_minutes":gap_minutes,"source_exact_in_target_draws":sum(
                (dm&f)==f for dm in draw_masks)})
    # Global 120 numerical features for every hour (time-indexed).
    values={}
    def group(n,items):
        names=GROUPS[n-1][1];assert len(items)==10
        values.update(dict(zip(names,[float(x) for x in items])))
    hourcnt=len(draws); families=hour_roots
    roots_n=len(families); oldn=len(latest)
    memberships=Counter(n for r in families for n in r["members"])
    sizes=[r["k"] for r in families]
    degree=[memberships[n] for n in memberships]
    group(1,[roots_n,len(memberships),avg(sizes),max(sizes,default=0),
      sum(r["k"]==2 for r in families),
      sum(r["k"]==3 for r in families),sum(r["k"]==4 for r in families),
      sum(r["k"]>=5 for r in families),sum(r["k"]>=10 for r in families),
      avg(degree)])
    bands=lambda r:[(n-1)//10 for n in r["members"]]
    bcnt=[Counter(bands(r)) for r in families]
    unique_band=[len(c) for c in bcnt]
    mirror=sum(sum((81-n) in r["members"] and n<41 for n in r["members"])
               for r in families)
    adjacent=sum(sum(r["members"][i]+1==r["members"][i+1]
                      for i in range(r["k"]-1)) for r in families)
    group(2,[avg(unique_band),sum(b==1 for b in unique_band),
      sum(b==r["k"] for b,r in zip(unique_band,families)),
      avg([b/r["k"] for b,r in zip(unique_band,families)]),
      avg([sum(n%2 for n in r["members"])/r["k"] for r in families]),
      avg([sum(n>40 for n in r["members"])/r["k"] for r in families]),
      mirror,adjacent,avg([r["members"][-1]-r["members"][0] for r in families]),
      avg([entropy(list(c.values())) for c in bcnt])])
    support=[r["support"] for r in families]
    gaps=[]
    for r in families:
        positions=[draws[i]["pos"] for i in r["occurrences"]]
        gaps.append(avg([b-a for a,b in zip(positions,positions[1:])]))
    group(3,[avg(support),max(support,default=0),
      sum(n>=3 for n in support),sum(n>=4 for n in support),
      avg([r["first"] for r in families]),avg([r["last"] for r in families]),
      avg([r["last"]-r["first"] for r in families]),avg(gaps),
      sum(g>1 for g in gaps),sum(support)])
    transitions_by=Counter(t["relation"] for t in transitions)
    exact=set(current)&{r["mask"] for r in latest}
    returns=set(current)&set(past)-{r["mask"] for r in latest}
    new_roots=[r for r in families if r["mask"] not in {x["mask"] for x in latest}]
    # New root "merge" when at least two previous roots each overlaps the
    # new root in >=2 numbers; numeric overlap, not causal genealogy.
    new_merges=sum(sum(intersect_count(r["mask"],old["mask"])>=2
                       for old in latest)>=2 for r in new_roots)
    group(4,[len(exact),len(new_roots),oldn-len(exact),
      transitions_by["ONE_SWAP"],transitions_by["TWO_SWAP"],
      transitions_by["EXPAND"],transitions_by["SHRINK"],
      sum(t["possible_split"] for t in transitions),new_merges,len(returns)])
    yesterday=[r for r in prev_last]
    yset={r["mask"] for r in yesterday}
    current_masks=set(current)
    same_hsize=[k.bit_count() for k in prev_day_all]
    group(5,[len(prev_day_all),len(prev_day_all&current_masks),
       len(prev_same),len(prev_same&current_masks),len(prev_last),
       avg(same_hsize),max((max((intersect_count(r["mask"],old)
                       for old in prev_day_all),default=0) for r in families),default=0),
       sum(any(r["k"]==old.bit_count() and
               intersect_count(r["mask"],old)==r["k"]-1
               for old in prev_day_all) for r in families),
       sum(any((old&r["mask"])==old and old!=r["mask"] for old in prev_day_all)
           for r in families),
       len(prev_day_all-current_masks)])
    diff=[max((intersect_count(old["mask"],dm) for dm in draw_masks),default=0)
          for old in latest]
    group(6,[sum(old["k"]-v==1 for old,v in zip(latest,diff)),
       sum(old["k"]-v==2 for old,v in zip(latest,diff)),
       sum(old["k"]-v>=3 for old,v in zip(latest,diff)),
       sum(v==0 for v in diff),avg(diff),
       avg([max(0,r["k"]-d) for r,d in zip(latest,diff)]),
       sum(t["source_exact_in_target_draws"]>0 for t in transitions),
       sum(0<v<r["k"] for r,v in zip(latest,diff)),
       sum(v==0 for v in diff),oldn])
    mt=Counter(e["relation"] for e in event)
    group(7,[mt["DISJOINT"],mt["OVERLAP"],mt["NESTED"],
       len(event),avg([e["union_size"] for e in event]),
       max([e["union_size"] for e in event],default=0),
       sum(e["union_repeats"]>=2 for e in event),
       sum(len(m)>=3 for m in activated),
       sum(len(m)>=4 for m in activated),
       sum(len(m)>=5 for m in activated)])
    nodes=set(graph)
    degree_g=[len(graph[n]) for n in nodes]
    visited=set(); components=[]
    for n in sorted(nodes):
        if n in visited:continue
        todo=[n];comp=0
        while todo:
            x=todo.pop()
            if x in visited:continue
            visited.add(x);comp+=1
            todo.extend(graph[x]-visited)
        components.append(comp)
    tris=sum(len(graph[a]&graph[b]) for a in graph for b in graph[a]
             if a<b)//3
    group(8,[len(parents),len(nodes),len(pair_seen),
       max(degree_g,default=0),avg(degree_g),
       sum(len(graph[n])>=3 for n in nodes),len(components),
       max(components,default=0),tris,
       sum(e["source_hours"].count("|")>0 for e in event)])
    heat=_heat_map(known_draws)
    mh=[Counter(heat[n] for n in r["members"]) for r in families]
    hot=[c.get(4,0) for c in mh];cold=[c.get(0,0) for c in mh]
    sh=sum(sizes)
    group(9,[avg(hot),avg(cold),sum(len(c)>=3 for c in mh),
       sum(h==r["k"] for h,r in zip(hot,families)),
       sum(c==r["k"] for c,r in zip(cold,families)),
       sum(hot)/sh if sh else 0,sum(cold)/sh if sh else 0,
       sum(h>0 for h in hot),sum(c>0 for c in cold),
       sum(2 in c and len(c)==1 for c in mh)])
    idx_first=set(range(min(6,hourcnt)))
    idx_second=set(range(6,min(12,hourcnt)))
    first_has=[len(idx_first&set(r["occurrences"])) for r in families]
    second_has=[len(idx_second&set(r["occurrences"])) for r in families]
    group(10,[avg(gaps),len(current_masks&prev_day_all),
       max([r["last"]-r["first"] for r in families],default=0),
       sum(a>0 for a in first_has),sum(b>0 for b in second_has),
       sum(a>0 and b>0 for a,b in zip(first_has,second_has)),
       sum(a>0 and b==0 for a,b in zip(first_has,second_has)),
       sum(b>0 and a==0 for a,b in zip(first_has,second_has)),
       len(current_masks&set(past)),max(support,default=0)])
    consecutive=[]
    for target in (draws[:6],draws[6:12]):
        counts=[intersect_count(mask(a["nums"]),mask(b["nums"])) for a,b in
              zip(target,target[1:])]
        consecutive.append(avg(counts))
    draw_band_spread=[]
    draw_mirrors=[]
    for row in draws:
        bc=Counter((n-1)//10 for n in row["nums"])
        draw_band_spread.append(max(bc.values())-min(bc.get(i,0) for i in range(8)))
        draw_mirrors.append(sum(81-n in row["nums"] for n in row["nums"] if n<=40))
    root_appear=[sum(r["mask"]&dm==r["mask"] for r in families)
                 for dm in draw_masks]
    group(11,[min((len(row["nums"]) for row in draws),default=0),
       consecutive[0],consecutive[1],
       sum(root_appear[:6]),sum(root_appear[6:12]),
       sum(n>=2 for n in root_appear),sum(n>=3 for n in root_appear),
       max(root_appear,default=0),avg(draw_band_spread),avg(draw_mirrors)])
    expected=sum(pair_expectation.values())
    observed=len(event)
    ratio=observed/expected if expected else 0.0
    group(12,[expected,observed,observed-expected,ratio,
       pair_expectation["DISJOINT"],mt["DISJOINT"],
       pair_expectation["OVERLAP"]+pair_expectation["NESTED"],
       mt["OVERLAP"]+mt["NESTED"],
       len(frozen_pair)*len(draws),0])
    if set(values)!={n for g,n in METRICS}:
        raise AssertionError("Not all 120 metrics computed")
    hour_meta={"day":day,"hour":hour["code"],"time_range":hour["name"],
        "first_draw":draws[0]["id"],"last_draw":draws[-1]["id"],
        "first_time":draws[0]["time"],"last_time":draws[-1]["time"],
        "block_start_slot":draws[0]["pos"],"block_end_slot":draws[-1]["pos"],
        "prior_hour":hoursource,"elapsed_from_prior_minutes":gap_minutes,
        "roots":roots_n,"candidate_roots_frozen":len(parents),
        "meeting_count":len(event),"expected_meeting_count":expected,
        "phase":"ILERIDE_SABIT" if day>=FORWARD_DAY else "GECMIS"}
    root_rows=[{"day":day,"hour":hour["code"],"family":r["family"],
       "k":r["k"],"support":r["support"],"first_draw_id":
       draws[r["occurrences"][0]]["id"],"last_draw_id":
       draws[r["occurrences"][-1]]["id"],
       "first_time":draws[r["occurrences"][0]]["time"],
       "last_time":draws[r["occurrences"][-1]]["time"],
       "bands":serial(sorted(set((n-1)//10+1 for n in r["members"]))),
       "hot_count":sum(heat[n]==4 for n in r["members"]),
       "cold_count":sum(heat[n]==0 for n in r["members"])}
        for r in families]
    for e in event:e.pop("union_mask",None)
    return values,hour_meta,root_rows,event,transitions,{
      "day":day,"name":hour["code"],"roots":hour_roots,"draws":draws}

SCHEMA="""
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS completed(day TEXT PRIMARY KEY, at_utc TEXT, hour_count INTEGER);
CREATE TABLE IF NOT EXISTS metrics(day TEXT,hour TEXT,metric TEXT,value REAL,
PRIMARY KEY(day,hour,metric));
CREATE TABLE IF NOT EXISTS hourly(day TEXT,hour TEXT,payload TEXT,PRIMARY KEY(day,hour));
CREATE TABLE IF NOT EXISTS roots(day TEXT,hour TEXT,family TEXT,payload TEXT,
PRIMARY KEY(day,hour,family));
CREATE TABLE IF NOT EXISTS meeting(day TEXT,hour TEXT,draw_id INTEGER,
family_a TEXT,family_b TEXT,payload TEXT,
PRIMARY KEY(day,hour,draw_id,family_a,family_b));
CREATE TABLE IF NOT EXISTS lineage(day TEXT,hour TEXT,source_family TEXT,
payload TEXT,PRIMARY KEY(day,hour,source_family));
"""
def _db(path,data_hash):
    path.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(path,timeout=60)
    con.executescript(SCHEMA)
    now=con.execute("SELECT value FROM meta WHERE key='identity'").fetchone()
    identity=VERSION+":"+data_hash
    if now and now[0]!=identity:
        for table in ("completed","metrics","hourly","roots","meeting","lineage"):
            con.execute("DELETE FROM "+table)
        con.execute("DELETE FROM meta")
    con.execute("INSERT OR REPLACE INTO meta VALUES('identity',?)",(identity,))
    con.commit()
    return con

def study_one_day(day,rows,prev_day=None):
    roots_day={}
    prior=[]
    known=[]
    if prev_day is not None:
        # last 3 completed hour blocks from the immediately previous calendar
        # day only. A gap in source days does not count as continuity.
        if date.fromisoformat(day)-date.fromisoformat(prev_day[0])==timedelta(days=1):
            for b in BLOCKS[-3:]:
                dr=[norm(x) for x in prev_day[1][b["start"]-1:b["end"]]]
                roots,_=support_masks(dr)
                prior.append({"day":prev_day[0],"name":b["code"],
                    "draws":dr,"roots":roots})
    prev_day_struct=None
    if prev_day is not None and prior:
        prev_all=[]; prev_same={}
        for b in BLOCKS:
            dr=[norm(x) for x in prev_day[1][b["start"]-1:b["end"]]]
            rr,_=support_masks(dr)
            prev_all.extend(x["mask"] for x in rr)
            prev_same[b["code"]]=set(r["mask"] for r in rr)
        prev_day_struct={"all_roots":set(prev_all),
            "same_hour":prev_same,"last_roots":prior[-1]["roots"]}
    result=[]
    for b in BLOCKS:
        draws=[norm(x) for x in rows[b["start"]-1:b["end"]]]
        # hour begins with frozen prior roster and previous72 draw heat counts
        v,h,r,m,t,meta=analyze_hour(day,b,draws,prior,prev_day_struct,known)
        result.append((v,h,r,m,t))
        roots_day[b["code"]]=meta["roots"]
        prior.append(meta)
        prior=prior[-RECENT_HOURS:]
        known.extend(draws)
        known=known[-72:]
    return result

def _run_data(full,checkpoint,shard,nshards,only_day=None,simulate=False):
    dates=sorted(full)
    # Ranges are deterministic based on sorted date index. Each shard has
    # at most ceil(days/nshards) dates and may be rerun independently.
    selected=[(i,d) for i,d in enumerate(dates)
              if i%nshards==shard and (only_day is None or only_day==d)]
    h=hashlib.sha256()
    for d in dates:
        h.update(d.encode())
        for row in full[d]:
            h.update(str(row["id"]).encode())
            h.update(bytes(row["nums"]))
    con=_db(checkpoint,h.hexdigest())
    completed=0;skipped=0
    for idx,day in selected:
        already=con.execute("SELECT 1 FROM completed WHERE day=?",(day,)).fetchone()
        if already:
            skipped+=1;continue
        previous=(dates[idx-1],full[dates[idx-1]]) if idx>0 else None
        results=study_one_day(day,full[day],previous)
        if len(results)!=18:raise AssertionError("one day must have 18 blocks")
        # Fully atomic DAY commit. Interrupted day starts over, earlier days
        # remain safe, and old dataset hashes reset cached results.
        with con:
            for t in ("metrics","hourly","roots","meeting","lineage"):
                con.execute("DELETE FROM "+t+" WHERE day=?",(day,))
            for values,hdr,roots,events,transitions in results:
                c=hdr["hour"]
                con.executemany("INSERT INTO metrics VALUES(?,?,?,?)",
                  ((day,c,key,val) for key,val in values.items()))
                con.execute("INSERT INTO hourly VALUES(?,?,?)",
                            (day,c,json.dumps(hdr,ensure_ascii=False)))
                con.executemany("INSERT INTO roots VALUES(?,?,?,?)",(
                    (day,c,r["family"],json.dumps(r,ensure_ascii=False)) for r in roots))
                con.executemany("INSERT INTO meeting VALUES(?,?,?,?,?,?)",(
                    (day,c,e["draw_id"],e["family_a"],e["family_b"],
                     json.dumps(e,ensure_ascii=False)) for e in events))
                con.executemany("INSERT INTO lineage VALUES(?,?,?,?)",(
                    (day,c,t["source_family"],json.dumps(t,ensure_ascii=False))
                     for t in transitions))
            con.execute("INSERT INTO completed VALUES(?,?,?)",(
              day,datetime.now(timezone.utc).isoformat(),18))
        completed+=1
        print(json.dumps({"checkpoint_day":day,"shard":shard,
             "completed_days_this_run":completed,"events":sum(len(x[3])
                  for x in results)},ensure_ascii=False),flush=True)
    total=con.execute("SELECT count(*) FROM completed").fetchone()[0]
    con.close()
    return {"shard":shard,"shards":nshards,"selected_days":len(selected),
            "processed_now":completed,"restored_days":skipped,
            "stored_days":total,"checkpoint":str(checkpoint)}

def selftest():
    assert len(METRICS)==120
    assert len(BLOCKS)==18
    rng=random.Random(581500)
    def day(n):
        return [{"day":n,"id":int(n[-2:])*10000+i,
          "time":("00:%02d"%(2+i*5)) if i<12 else "01:02" if i==12 else
          f"{(422+5*(i-13))//60:02d}:{(422+5*(i-13))%60:02d}",
          "pos":i+1,"nums":tuple(sorted(rng.sample(range(1,81),20)))}
          for i in range(217)]
    a=day("2026-10-10");b=day("2026-10-11")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ck=Path(tmp)/"shard_0.sqlite"
        f={"2026-10-10":a,"2026-10-11":b}
        r=_run_data(f,ck,0,1)
        assert r["processed_now"]==2
        r2=_run_data(f,ck,0,1)
        assert r2["processed_now"]==0 and r2["restored_days"]==2
        db=sqlite3.connect(ck)
        assert db.execute("select count(*) from metrics").fetchone()[0]==2*18*120
        assert db.execute("select count(*) from hourly").fetchone()[0]==2*18
        assert db.execute("select count(*) from completed").fetchone()[0]==2
        # Subsequent source change invalidates checkpoint.
        b[-1]["nums"]=tuple(range(1,21))
        r3=_run_data(f,ck,0,1)
        assert r3["processed_now"]==2
        db.close()
    print("PASS V58: 120 real numerical metrics/hour, 217 slots/day, "
          "frozen family pairs, atomic day checkpoint, resume/reset")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--checkpoint",default="v58_checkpoints/shard_0.sqlite")
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--shards",type=int,default=N_SHARDS)
    p.add_argument("--only-day")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest();return
    if not 0<=args.shard<args.shards:raise ValueError("invalid shard index")
    days,issues,malformed=parse_txt(Path(args.source))
    full={d:rs for d,rs in days.items() if len(rs)==217 and
          {r["pos"] for r in rs}==set(range(1,218))}
    if not full:raise ValueError("No 217-draw complete days")
    report=_run_data(full,Path(args.checkpoint),args.shard,args.shards,args.only_day)
    print(json.dumps({"result":report,"full_days":len(full),"invalid":len(issues),
                      "malformed":len(malformed)},ensure_ascii=False))
if __name__=="__main__":main()
