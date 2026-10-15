#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V86: 72-day DRAW-BY-DRAW family genealogy and forward-coupon audit.

A NATURAL FAMILY ROOT is the EXACT intersection of the currently observed
20-number draw with one of the previous <=12 uninterrupted draws, with
5<=K<=10. If intersection >10, use its first ten sorted numbers and flag
the capping; NEVER enumerate all 20-choose-k subsets. This definition
uses result t to DISCOVER a root at t, so it CANNOT forecast t.

Frozen exact family identities gain EXPLICIT genealogy edges:
SAME, SWAP_ONE, GROW_ONE, SHRINK_ONE, SWAP_TWO, GROW_TWO,
SHRINK_TWO; otherwise OTHER. A new child is NOT the same family as its
parent. Roster updates and new births only AFTER all target-t tickets are
frozen and scored. Keep an active 72-draw registry plus <=12-draw natural
ancestor candidates; an ancestor can return on a later date.

Four predeclared target rules:
 NEAR: best historical K-1 of K in previous <=3 observed targets.
 REPEAT: root fully seen >=3 times BEFORE target and positive
         previously repeating draw gap within +-1 current lag.
 CHILD: previously discovered one-swap/grow/shrink child close to last 3.
 HYBRID: REPEAT else CHILD else NEAR.
Each rule may issue a MAXIMUM of one ten-number coupon per target; family
members + most frequent last72 already-seen numbers to reach ten.
Matched control random10 and frequency10 use the SAME targets.

Split (predeclared): DEVELOPMENT 01Aug..12Sep; validation 13..27Sep;
holdout 28Sep..12Oct, 2026. Pick one method on validation only if at
least 100 issued. All these dates were studied by prior V9..V85,
therefore this is NOT a genuinely unseen prospective test.

Post-hoc exact family full appearance histories across all 72 days are
calculated only AFTER the forward scoring; NEVER use the future-inclusive
offline ledger to construct past target predictions.
"""
from __future__ import annotations
import argparse, collections, csv, gzip, hashlib, io, json, math, random, zipfile
from pathlib import Path
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V86.1"
MIN_K=5;MAX_K=10;ROOT_LOOKBACK=12;ACTIVE=72
RULES=("NEAR","REPEAT","CHILD","HYBRID")
DAYS_EXPECTED=72;TARGETS_PER_DAY=217
VALID_START="2026-09-13";HOLDOUT_START="2026-09-28"
FINISH="2026-10-12";SEED=861016
PRIORITY=("SWAP_ONE","GROW_ONE","SHRINK_ONE","SWAP_TWO","GROW_TWO","SHRINK_TWO")
LIFE_TYPES=("NEW_ROOT","OLD_EXACT_ROOT","SIBLING_SWAPPED","CHILD_GREW","CHILD_SHRANK","UNRELATED")
MIN_VALIDATE_TICKETS=100
SIZES=tuple(range(5,11))

def bm(xs):
    return sum(1<<(n-1) for n in xs)

def members(m):
    return tuple(i+1 for i in range(80) if m&(1<<i))

def fs(m):
    return "-".join(map(str,members(m)))

def src_seed(*a):
    return int.from_bytes(hashlib.blake2b("|".join(map(str,a)).encode(),
        digest_size=8).digest(),"big")

def prob_full(k):
    return math.prod((20-i)/(80-i) for i in range(k))

def inputdata(filepath):
    d,issues,malformed=parse_txt(filepath)
    days=sorted(k for k,v in d.items() if len(v)==217 and
         [r["pos"] for r in v]==list(range(1,218)))
    if len(days)!=72 or days[0]!="2026-08-01" or days[-1]!=FINISH:
        raise RuntimeError(f"72 complete days needed; got {len(days)}")
    rows=[x for day in days for x in d[day]]
    assert len(rows)==15624 and rows[-1]["id"]==61845
    ms=[bm(x["nums"]) for x in rows]
    return days,rows,ms,issues,malformed

def relation(parent,child):
    if parent==child:return "EXACT"
    a=parent.bit_count();b=child.bit_count()
    n=(parent&child).bit_count()
    if a==b and n==a-1:return "SWAP_ONE"
    if b==a+1 and n==a:return "GROW_ONE"
    if a==b+1 and n==b:return "SHRINK_ONE"
    if a==b and n==a-2:return "SWAP_TWO"
    if b==a+2 and n==a:return "GROW_TWO"
    if a==b+2 and n==b:return "SHRINK_TWO"
    return "OTHER"

def event_roots(i,rows,draw_masks):
    """Returns exact NATURAL roots, each linked to already-known source draw."""
    current=draw_masks[i]
    roots={}
    crossed=False
    for lag in range(1,ROOT_LOOKBACK+1):
        j=i-lag
        if j<0:break
        # Completely prohibit synthetic family from missing-day ID gap.
        if rows[j+1]["id"]!=rows[j]["id"]+1:
            crossed=True;break
        root=draw_masks[j]&current
        common=root.bit_count()
        if common<MIN_K:continue
        if common>MAX_K:
            # Explicit deterministic representative k10, not all subsets.
            root=bm(members(root)[:MAX_K])
        if root not in roots or lag<roots[root]["lag"]:
            roots[root]={"lag":lag,"parent_index":j,
               "intersection_original":common,"capped":int(common>MAX_K)}
    return roots,crossed

def hot72(history):
    counts=[0]*81
    for mask in history:
        for n in members(mask):counts[n]+=1
    return counts

def highest10(counts):
    return tuple(sorted(sorted(range(1,81),
           key=lambda n:(-counts[n],n))[:10]))

def compose10(family,counts):
    ns=list(members(family))
    for n in sorted(range(1,81),key=lambda x:(-counts[x],x)):
        if len(ns)>=10:break
        if n not in ns:ns.append(n)
    assert len(ns)==10
    return tuple(sorted(ns))

def random10(date,idn):
    return tuple(sorted(random.Random(src_seed(SEED,date,idn)).
                        sample(range(1,81),10)))

def shortlist(info,mask3,now):
    """Deterministic recipe scores; no data from current target."""
    k=info["k"]
    overlap=max(((mask&m).bit_count() for m in mask3),default=0)
    recent=now-info["last_live"]
    nseen=len(info["seen_after_birth"])
    # Birth is a second exact occurrence across two already-seen targets.
    common=(0.03*min(info["birth_pair_count"],4)+
       .016*min(nseen,6)+.0001*k)
    near=None
    if overlap>=k-1:
        near=(overlap/k+common-.00009*recent, info["id"])
    child=None
    if info["relation"] in ("SWAP_ONE","GROW_ONE","SHRINK_ONE") and
       overlap>=max(2,k-2):
        child=(overlap/k+common-.0002*recent+
               .025/(1+info["birth_lag"]),info["id"])
    rhythm=None
    if len(info["seen_after_birth"])>=3:
        last=info["seen_after_birth"][-1]
        today_gap=now-last
        if 1<=today_gap<=ACTIVE:
            gaps=collections.Counter(
                info["seen_after_birth"][h]-info["seen_after_birth"][h-1]
                for h in range(1,len(info["seen_after_birth"])))
            support=sum(ct for gap,ct in gaps.items() if abs(gap-today_gap)<=1)
            if support>=2:
                rhythm=(support*.12+common-.00002*recent,info["id"])
    return overlap,near,rhythm,child

def writecsv(z,name,items,header=None,compress_gz=False):
    if compress_gz:
        with z.open(name,"w",force_zip64=True) as raw:
            with gzip.GzipFile(fileobj=raw,mode="wb",compresslevel=5) as gz:
                tx=io.TextIOWrapper(gz,encoding="utf-8",newline="")
                w=csv.writer(tx)
                w.writerow(header)
                w.writerows(items)
                tx.flush();tx.detach()
    else:
        if not items:return
        with z.open(name,"w",force_zip64=True) as raw:
            tx=io.TextIOWrapper(raw,encoding="utf-8",newline="")
            w=csv.DictWriter(tx,fieldnames=list(items[0]))
            w.writeheader();w.writerows(items)
            tx.flush();tx.detach()

def run(filepath,outpath):
    days,rows,y,issues,malformed=inputdata(filepath)
    families={}     # EXACT roots known only AFTER their discovery draw
    genealogy=[]
    by_draw=[]
    tickets=[]
    exact_events=[]  # genuinely detected complete returns, AFTER known discovery
    last_root_frames=collections.deque(maxlen=ROOT_LOOKBACK*20)
    old_numbers=collections.deque(maxlen=ACTIVE)
    seen_draw=[]
    active={}        # mask -> info, family lifetime expires on no full root event
    by_id={}          # exact known root registry; never includes future roots
    gap_count=0
    source_id_breaks=[]
    for t,row in enumerate(rows):
        if t and row["id"]!=rows[t-1]["id"]+1:
            gap_count+=1
            source_id_breaks.append((rows[t-1]["id"],row["id"]))
            # Do NOT bridge unknown target draw-IDs with rolling,
            # otherwise "previous 12/72" is no longer an actual timeframe.
            last_root_frames.clear()
            old_numbers.clear()
            active.clear()
        before=y[t-3:t]
        # recent same continuous draws only
        since_break=0
        for j in range(t-1,max(-1,t-4),-1):
            if j>=0 and rows[j+1]["id"]==rows[j]["id"]+1:
                since_break+=1
            else:break
        last3=y[max(0,t-since_break):t]
        counts=hot72(old_numbers)
        freq10=highest10(counts)
        rand=random10(row["day"],row["id"])
        pool={"NEAR":[],"REPEAT":[],"CHILD":[]}
        candidates=0
        for m,info in active.items():
            if info["born_at"]>=t:raise AssertionError("family born in target")
            overlap,near,repeat,child=shortlist(info,last3,t)
            candidates+=1
            if near is not None:pool["NEAR"].append(near)
            if repeat is not None:pool["REPEAT"].append(repeat)
            if child is not None:pool["CHILD"].append(child)
        best={}
        for key in ("NEAR","REPEAT","CHILD"):
            if pool[key]:
                best[key]=sorted(pool[key],key=lambda u:(-u[0],u[1]))[0][1]
        if "REPEAT" in best:
            best["HYBRID"]=best["REPEAT"]
        elif "CHILD" in best:
            best["HYBRID"]=best["CHILD"]
        elif "NEAR" in best:
            best["HYBRID"]=best["NEAR"]
        actual=set(row["nums"])
        if row["day"]>=VALID_START:
            phase="VALIDATE" if row["day"]<HOLDOUT_START else "HOLDOUT"
            for rule in RULES:
                if rule not in best:continue
                f=by_id[best[rule]]
                ticket=compose10(f["mask"],counts)
                hit10=len(actual.intersection(ticket))
                targetfull=(f["mask"]&y[t]).bit_count()
                tickets.append(dict(day=row["day"],time=row["time"],
                    draw_id=row["id"],phase=phase,rule=rule,
                    family_id=f["id"],family=fs(f["mask"]),family_k=f["k"],
                    family_born_date=f["born_date"],family_birth_id=f["born_draw_id"],
                    family_origin_draw_id=f["source_draw_id"],
                    root_origin_relation=f["relation"],
                    age_since_birth=t-f["born_at"],since_last_full=t-f["last_live"],
                    prior_known_full_after_birth=len(f["seen_after_birth"]),
                    previous3_best_overlap=max(
                       (f["mask"]&m).bit_count() for m in last3) if last3 else 0,
                    coupon10=",".join(map(str,ticket)),
                    hit10=hit10,random10=len(actual.intersection(rand)),
                    freq72_10=len(actual.intersection(freq10)),
                    full_family_hit=int(targetfull==f["k"]),
                    family_actual_hits=targetfull,
                    actual_target20=",".join(map(str,row["nums"]))))
        # from this line onward we may observe target result and update roots.
        raw_roots,crossed=event_roots(t,rows,y)
        seen_before=len(families)
        new_roots=0;exact_roots=0;other_roots=0
        type_count=collections.Counter()
        current_frame=[]
        # Detect exact FULL returns from previously discovered active roots
        for m,info in list(active.items()):
            if m&y[t]==m:
                info["seen_after_birth"].append(t)
                info["last_live"]=t
                if info["born_at"]!=t:
                    exact_events.append([row["day"],row["time"],row["id"],
                       info["id"],fs(m),info["k"],
                       len(info["seen_after_birth"]),
                       t-info["born_at"]])
        for family,source in sorted(raw_roots.items(),
            key=lambda z:(-z[0].bit_count(),z[0])):
            current_frame.append(family)
            if family in families:
                exact_roots+=1
                type_count["EXACT"]+=1
                info=families[family]
                info["birth_pair_count"]+=1
                if family not in active:
                    active[family]=info
                    # New root event is a full hit, even if last full long ago.
                    if not info["seen_after_birth"] or info["seen_after_birth"][-1]!=t:
                        info["seen_after_birth"].append(t)
                        info["last_live"]=t
            else:
                # Source candidate ancestors must have been discovered BEFORE t.
                possible=[]
                for old_t, old_family in last_root_frames:
                    if t-old_t>ROOT_LOOKBACK:continue
                    rel=relation(old_family,family)
                    if rel not in PRIORITY:continue
                    if old_family not in families:continue
                    possible.append((PRIORITY.index(rel),t-old_t,
                                    families[old_family]["id"],old_family,rel))
                if possible:
                    ix,dt,ancestor_id,ancestor_family,relationship=sorted(possible)[0]
                    ancestor=families[ancestor_family]
                else:
                    ancestor_id=None;ancestor_family=None;relationship="ORIGINAL"
                    dt=None
                fid=len(families)+1
                info=dict(id=fid,k=family.bit_count(),mask=family,
                    birth_lag=source["lag"],born_at=t,
                    born_date=row["day"],born_draw_id=row["id"],
                    source_draw_id=rows[source["parent_index"]]["id"],
                    initial_intersection=source["intersection_original"],
                    intersection_capped=source["capped"],
                    parent_id=ancestor_id,relation=relationship,
                    last_live=t,birth_pair_count=1,
                    seen_after_birth=[t])
                families[family]=info;active[family]=info;by_id[fid]=info
                new_roots+=1;type_count[relationship]+=1
                genealogy.append(dict(child_id=fid,
                   child_mask_family=fs(family),k=info["k"],
                   born_day=row["day"],born_draw=row["id"],
                   source_earlier_draw=info["source_draw_id"],
                   source_lag_drawings=info["birth_lag"],
                   original_intersection_size=info["initial_intersection"],
                   capped_larger_than_10=info["intersection_capped"],
                   ancestor_id=ancestor_id if ancestor_id is not None else "",
                   ancestor_family=fs(ancestor_family) if ancestor_family is not None else "",
                   relation_to_preexisting_family=relationship,
                   ancestor_seen_draws_ago=dt if dt is not None else "",
                   gained_numbers=",".join(map(str,members(family&
                        ~ancestor_family))) if ancestor_family is not None else "",
                   lost_numbers=",".join(map(str,members(
                        ancestor_family&~family))) if ancestor_family is not None else ""))
        for m in current_frame:
            last_root_frames.append((t,m))
        # Active check after data reveal (before next target), discard old
        for m,info in list(active.items()):
            if t-info["last_live"]>=ACTIVE:
                active.pop(m)
        old_numbers.append(y[t])
        by_draw.append(dict(date=row["day"],time=row["time"],
            draw_id=row["id"],day_slot=row["pos"],
            roots_from_preceding_12=len(raw_roots),
            never_seen_new_roots=new_roots,
            previously_discovered_exact_roots=exact_roots,
            live_families_after_target=len(active),
            known_families_total=len(families),
            new_swap_one=type_count["SWAP_ONE"],
            new_grow_one=type_count["GROW_ONE"],
            new_shrink_one=type_count["SHRINK_ONE"],
            new_swap_two=type_count["SWAP_TWO"],
            new_grow_two=type_count["GROW_TWO"],
            new_shrink_two=type_count["SHRINK_TWO"],
            new_unrelated=type_count["ORIGINAL"],
            prior_known_candidates=candidates,
            issued_near=int("NEAR" in best),
            issued_repeat=int("REPEAT" in best),
            issued_child=int("CHILD" in best),
            changed_predecessor_window=int(crossed),
            drawn20=",".join(map(str,row["nums"]))))
        if t%2500==0:
            print("V86 progress",t+1,"/",len(rows),
                  "unique roots",len(families),"active",len(active),flush=True)
    # AFTER the entire chronological replay: retrospective exact appearance
    # and repeated cadence for every discovered natural root identity.
    # NEVER let these hindsight statistics influence earlier coupon choices.
    print("V86 starting POST-HOC full occurrence ledger",len(families),flush=True)
    allbits=[0]*81
    for t,row in enumerate(rows):
        bit=1<<t
        for number in row["nums"]:
            allbits[number]|=bit
    retrospective=[]
    total_completed=0
    for i,(m,info) in enumerate(families.items()):
        occurrence=allbits[members(m)[0]]
        for n in members(m)[1:]:
            occurrence&=allbits[n]
            if not occurrence:break
        pos=[]
        while occurrence:
            low=occurrence&-occurrence
            occ_t=low.bit_length()-1
            occurrence^=low
            pos.append(occ_t)
        assert len(pos)>=2
        gaps=[pos[h]-pos[h-1] for h in range(1,len(pos))]
        post=[p for p in pos if p>info["born_at"]]
        n_after=len(post)
        total_completed+=len(pos)
        retrospective.append(dict(family_id=info["id"],family=fs(m),
           k=info["k"],born_day=info["born_date"],
           born_draw=info["born_draw_id"],
           root_discovered_from_draw=info["source_draw_id"],
           initial_source_draw_distance=info["birth_lag"],
           discovered_first_k=info["initial_intersection"],
           parent_id=info["parent_id"] or "",
           transformation_type=info["relation"],
           total_full_occurrences_INCLUDING_BEFORE_DISCOVERY=len(pos),
           full_after_birth=n_after,
           first_full_draw=rows[pos[0]]["id"],last_full_draw=rows[pos[-1]]["id"],
           distinct_days_with_full=len(set(rows[j]["day"] for j in pos)),
           most_common_draw_gap=collections.Counter(gaps).most_common(1)[0][0],
           max_consecutive_full_run=max((len(list(group))
               for _,group in __import__("itertools").groupby(
                   enumerate(pos),lambda p:p[0]-p[1])),default=1),
           first_20_full_draw_ids=",".join(str(rows[j]["id"]) for j in pos[:20]),
           first_20_gaps=",".join(map(str,gaps[:20])),
           last_full_draw_ids=",".join(str(rows[j]["id"]) for j in pos[-6:])))
        if i%15000==0:print("V86 ledger",i,"/",len(families),flush=True)
    # History-only audit of parent-child transformations
    split_metrics=[]
    selected={}
    for period,lo,hi in (("VALIDATE",VALID_START,HOLDOUT_START),
                          ("HOLDOUT",HOLDOUT_START,"2026-10-13")):
        for rule in RULES:
            data=[r for r in tickets if lo<=r["day"]<hi and r["rule"]==rule]
            n=len(data)
            if n:
                daygroup=collections.defaultdict(list)
                for r in data:daygroup[r["day"]].append(r)
                means=[sum(r["hit10"]-r["random10"] for r in dr)/len(dr)
                       for dr in daygroup.values()]
                mean=sum(means)/len(means)
                se=math.sqrt(sum((x-mean)**2 for x in means)
                    /(len(means)-1))/math.sqrt(len(means)) if len(means)>1 else 0.
                z=mean/se if se else 0.
                res=dict(phase=period,rule=rule,issued10=n,
                    different_target_draws=len(set(r["draw_id"] for r in data)),
                    days_with_signal=len(daygroup),
                    coverage_pct=round(n/(15*217)*100,4),
                    avg_coupon10=round(sum(r["hit10"] for r in data)/n,7),
                    avg_random10=round(sum(r["random10"] for r in data)/n,7),
                    avg_freq10=round(sum(r["freq72_10"] for r in data)/n,7),
                    advantage_random=round(sum(r["hit10"]-r["random10"] for r in data)/n,7),
                    daycluster_p_one_sided=round(.5*math.erfc(z/math.sqrt(2)),7),
                    hits6plus=sum(r["hit10"]>=6 for r in data),
                    hits7plus=sum(r["hit10"]>=7 for r in data),
                    hits8plus=sum(r["hit10"]>=8 for r in data),
                    hits9plus=sum(r["hit10"]>=9 for r in data),
                    hits10of10=sum(r["hit10"]==10 for r in data),
                    families_complete=sum(r["full_family_hit"] for r in data))
            else:
                res=dict(phase=period,rule=rule,issued10=0)
            split_metrics.append(res)
    validation=[r for r in split_metrics if r["phase"]=="VALIDATE"
                and r["issued10"]>=MIN_VALIDATE_TICKETS]
    if validation:
        winner=sorted(validation,key=lambda r:(
           -r["advantage_random"],-r["issued10"],RULES.index(r["rule"])))[0]
        hold=next(r for r in split_metrics if
            r["phase"]=="HOLDOUT" and r["rule"]==winner["rule"])
    else:
        winner=None;hold=None
    freeze=[r for r in tickets if winner and
         r["phase"]=="HOLDOUT" and r["rule"]==winner["rule"]]
    types=collections.Counter(r["relation_to_preexisting_family"] for r in genealogy)
    size=collections.Counter(x["k"] for x in retrospective)
    daily=[]
    for d in days:
        records=[x for x in by_draw if x["date"]==d]
        daily.append(dict(day=d,
            draws=len(records),
            birth=sum(x["never_seen_new_roots"] for x in records),
            exact_roots=sum(x["previously_discovered_exact_roots"] for x in records),
            one_swap=sum(x["new_swap_one"] for x in records),
            grew=sum(x["new_grow_one"] for x in records),
            shrank=sum(x["new_shrink_one"] for x in records),
            full_known_families_after=sum(x["live_families_after_target"] for x in records)/217,
            near_signal=sum(x["issued_near"] for x in records),
            repeat_signal=sum(x["issued_repeat"] for x in records),
            child_signal=sum(x["issued_child"] for x in records)))
    summary=[
       "V86 — 72 GUN AILELERIN CEKILIS CEKILIS DINAMIK SOYAGACI",
       "Every ROOT family is an exact natural overlap between the current",
       "20 actual drawn balls and ONE of twelve preceding real 20 draws.",
       "Exactly sizes 5..10 retained; above 10 deterministic 10-member",
       "representative chosen, NOT combinatorial arbitrary 5-subsets.",
       "A newly discovered family is recorded AFTER seeing its birth target;",
       "it CANNOT be used to predict that same draw.",
       "Every preexisting root retains fixed identity and optional parent",
       "mutation edge: one swap, grow by1, shrink by1, swap2, grow2/shrink2.",
       "Each child is independent exact family, not a 'prediction that came true'.",
       f"Complete days={len(days)}, draws={len(rows)},"
       f" draw-ID discontinuities={source_id_breaks}.",
       f"Unique natural root families={len(families)}; k counts={dict(sorted(size.items()))}.",
       f"New root transformations={dict(sorted(types.items()))}.",
       f"Root actual complete co-occurrence events (POST-HOC, not independent)="
       f"{total_completed}.",
       "",
       "BEFORE each future draw, only previously discovered roots active",
       f"within last {ACTIVE} draws can offer candidate ticket families.",
       "RHYTHM requires >=2 prior same-family gap observations approximately",
       "matching actual time since last full, nothing learned from current result.",
       "NEAR uses closest partial one of last3, CHILD is previously known",
       "one-swap/grow/shrink branch; HYBRID defaults to rhythm, child, near.",
       "At most one 10-ball coupon per rule and target; compare to same-target",
       "random10 and prior72 frequency10 baseline.",
       "VALIDATE Sep13–Sep27 determines one fixed rule with >=100 coupons.",
       "HOLDOUT Sep28–Oct12 is not used to select rule (but historically",
       "these dates have been examined by prior versions).",
       "Fair independent lottery expects 2.5 of 10 for all non-anticipative",
       "10-number coupons and exact k family p_full=prod((20-i)/(80-i)).",
       "",
       "VALIDATION / HOLDOUT RESULTS:"
    ]
    for r in split_metrics:
        if not r["issued10"]:
            summary.append(f"  {r['phase']} {r['rule']}: 0 coupons")
        else:
            summary.append(f"  {r['phase']} {r['rule']}: {r['issued10']} coupons,"
              f" mean10={r['avg_coupon10']:.6f}, random={r['avg_random10']:.6f},"
              f" freq72={r['avg_freq10']:.6f}, diff={r['advantage_random']:+.6f},"
              f" 10of10={r['hits10of10']},7plus={r['hits7plus']},"
              f" daycluster p={r['daycluster_p_one_sided']:.6f}")
    summary.append("")
    if winner and hold:
        summary+=[
            f"VALIDATION-LOCKED rule={winner['rule']}; valid10={winner['avg_coupon10']:.6f}.",
            f"HOLDOUT of that SAME rule: mean10={hold['avg_coupon10']:.6f}, "
            f"random={hold['avg_random10']:.6f},"
            f" delta={hold['advantage_random']:+.6f},"
            f" p={hold['daycluster_p_one_sided']:.6f};"
            f" 10of10={hold['hits10of10']}."
        ]
    else:summary.append("No validation rule had >=100 tickets; no winner.")
    summary+=["",
       "DO NOT make decisions based on post-hoc all-family full histories;",
       "their later full repeats were found after those dates were known.",
       "Never interpret mutation arcs as hidden machinery of independent RNG.",
       "To verify a predictive advantage, freeze the rule and candidate",
       "data before genuinely new later, unseen draw results.",
       ""
    ]
    out=Path(outpath);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6,allowZip64=True) as z:
        z.writestr("00_V86_KISA_KARAR.txt","\n".join(summary))
        writecsv(z,"01_15624_CEKILIS_AILE_DOGUM_DONUSUM_HAREKET.csv",by_draw)
        writecsv(z,"02_YENI_DOGAN_AILE_ATA_ANA_KAYIP_KAZANILAN.csv.gz",
             ([x.get(k,"") for k in genealogy[0]] for x in genealogy),
             list(genealogy[0]) if genealogy else [],compress_gz=True)
        writecsv(z,"03_72GUN_HER_SABIT_AILENIN_GERCEK_TAM_HAYATI.csv.gz",
             ([x.get(k,"") for k in retrospective[0]] for x in retrospective),
             list(retrospective[0]) if retrospective else [],compress_gz=True)
        writecsv(z,"04_15GUN_VAL_15GUN_HOLD_4_AILE_KUPON_TUM.csv.gz",
             ([x.get(k,"") for k in tickets[0]] for x in tickets),
             list(tickets[0]) if tickets else [],compress_gz=True)
        writecsv(z,"05_BIR_ONCEDEN_SECILI_KURAL_15GUN_KUPONLAR.csv",freeze)
        writecsv(z,"06_DORT_KURAL_GERCEK_10LU_ISABET_VS_RASTGELE.csv",split_metrics)
        writecsv(z,"07_GUN_GUN_AILE_DOGUM_OLD_KIMLIK_DEGISIM.csv",daily)
        writecsv(z,"08_KAYITLI_AILENIN_SONRAKI_TAM_GELISLERI.csv.gz",
             exact_events,
             ["day","clock","draw_id","family_id","family", "k",
              "known_complete_appearance_no","elapsed_draws_from_root_birth"],
             compress_gz=True)
        z.writestr("09_METOT_VE_HATASIZ_ZAMAN.txt","\n".join([
          "Untrusted hindsight static family catalogue V10 is NOT used.",
          "Natural family birth means full intersection of two observed",
          "20-ball draws, one now and one at most 12 consecutive prior draws.",
          "All exact natural roots include the parent earlier draw id.",
          "Roots beyond size10 capped to deterministic ten subset, flagged.",
          "No 20Ck subfamily explosion. Root family set is immutable.",
          "Child relationships: SWAP_ONE, GROW_ONE, SHRINK_ONE, SWAP_TWO,",
          "GROW_TWO, SHRINK_TWO and ORIGINAL. Source earlier draw is",
          "distinct from mutation parent root and both explicitly recorded.",
          "Family birth/return/lineage only learned AFTER the draw event.",
          "Only root identities discovered earlier and active last72 draws",
          "can be used to select next target coupon.",
          "Single 10-ball coupon per target, with pre-target last72 filler.",
          "Random baseline date+drawID seeded, freq baseline last72 only.",
          "VALIDATE Sept13–27 picks one rule; HOLDOUT Sept28–Oct12 frozen.",
          "All 72-day offline complete appearances computed AFTER coupon",
          "evaluation from bit intersections; not part of model features.",
          "First day of all missing records Aug23 excluded, and no pair",
          "or history window crosses draw-ID gaps.",
          "Retrospective holdout dates have been extensively explored",
          "by V9–V85, so no truly untouched independent validation here.",
          "Expected RNG: 10/20 target mean 2.5/10; family chance",
          "complete exact K from combinatorial hypergeometric probability."
        ]))
        z.writestr("10_AUDIT.json",json.dumps(dict(
            version=VERSION,days=days,total_draws=len(rows),
            unique_roots=len(families),families_by_size=dict(size),
            lineage_types=dict(types),draw_id_gaps=source_id_breaks,
            root_events=sum(r["roots_from_preceding_12"] for r in by_draw),
            after_birth_return_events=len(exact_events),
            all_full_occurrences_posthoc=total_completed,
            rules=RULES,validation=winner,holdout=hold,
            all_rule_results=split_metrics,issues=issues[:20],
            malformed=malformed[:20]),ensure_ascii=False,indent=2))
    print("\n".join(summary),flush=True)
    print("V86 ZIP",out,out.stat().st_size,flush=True)

def selftest():
    assert relation(bm([1,2,3,4,5]),bm([1,2,3,4,6]))=="SWAP_ONE"
    assert relation(bm([1,2,3,4,5]),bm([1,2,3,4,5,6]))=="GROW_ONE"
    assert relation(bm([1,2,3,4,5]),bm([1,2,3,4]))=="SHRINK_ONE"
    assert relation(bm([1,2,3,4,5]),bm([1,2,3,6,7]))=="SWAP_TWO"
    assert compose10(bm([1,2,3,4,5]),[0]+[0]*80)==tuple(range(1,11))
    assert len(random10("2026-10-12",61845))==10
    assert abs(prob_full(5)-.000644925)<.0000001
    print("V86 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v86_output/V86_72GUN_AILELER_CEKILIS_CEKILIS_GENEOLOJI_10LU_KUPON.zip")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest()
    else:run(args.source,args.out)
