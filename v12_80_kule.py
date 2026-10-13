# -*- coding: utf-8 -*-
"""V12 — 80-number tower, all 2..10 family sizes, 20-ball covering/order audit.

Fundamental distinction:
- The published 20-ball draw is an UNORDERED SET; sorting it is not ball
  arrival order. We study the *previous-draw appearance chronology* of
  subsets, not physical ball-extraction order.
- Any 20 balls can be partitioned into groups of sizes 2,3,4,5,6. That
  mathematical fact is NOT a predictive signal.
- Prospective twenty-number compositions are frozen using ONLY earlier draws.
  A fixed-seed random 20-number sample is the benchmark.

Computationally tractable: discover all prior-12 repeated families by the
intersections between each previous 20-set and the target's 20-set. This is
exact for every subset size 2..10 and avoids enumerating all C(20,10) groups.
"""
import csv
import io
import math
import random
from collections import Counter, defaultdict
from itertools import combinations
from v11_arastirma import hour_draw_index, complete_preceding_12

SIZES=tuple(range(2,11))
SPLIT=(2,3,4,5,6)
METHODS=("Sıklık-12","İvme 6/6","20 taşıma","Ağ-kule","Rastgele20")


def mask_of(nums):
    return sum(1<<(int(n)-1) for n in nums)


def make_ready(draws):
    """Accept V10/V11 draw dictionaries without modifying them."""
    return sorted(
        ({**d,"mask":d.get("mask",mask_of(d["nums"]))} for d in draws),
        key=lambda x:(x["day"],x["pos"])
    )


def history_features(prior):
    """Historical 80 nodes + 3160 co-occurrence edges."""
    c12=[0]*81
    c6=[0]*81
    cfirst=[0]*81
    pairs=Counter()
    for i,r in enumerate(prior):
        nums=tuple(r["nums"])
        for n in nums:
            c12[n]+=1
            if i<6:cfirst[n]+=1
            else:c6[n]+=1
        # Full twelve-draw co-occurrence network, no future draw access.
        for n,m in combinations(nums,2):
            pairs[(n,m) if n<m else (m,n)]+=1
    return {"freq":c12,"recent":c6,"early":cfirst,
            "pair":pairs,"last":tuple(prior[-1]["nums"])}


def forward_towers(prior,draw_no):
    """Return five 20-ball proposals and meaningful build orders, pre-target."""
    f=history_features(prior)
    fre=f["freq"];rec=f["recent"];early=f["early"];pair=f["pair"]
    order_freq=sorted(range(1,81),key=lambda n:(-fre[n],-rec[n],n))[:20]
    order_momentum=sorted(range(1,81),
                          key=lambda n:(-(rec[n]-early[n]),-rec[n],-fre[n],n))[:20]
    order_last=sorted(f["last"],key=lambda n:(-fre[n],n))
    # Genuine graph-construction sequence of families growing from 2 to 10.
    # Seed chosen from previously co-occurring pairs; no target set inspected.
    anchor=max(pair.items(),key=lambda kv:(kv[1],fre[kv[0][0]]+fre[kv[0][1]],
                                             -kv[0][0],-kv[0][1]))[0]
    graph=[anchor[0],anchor[1]]
    remaining=set(range(1,81))-set(graph)
    while len(graph)<20:
        # Edges to already-chosen members, scaled to prevent all terms growing
        # simply because more numbers have been selected.
        n=max(remaining,key=lambda n:(
            3*sum(pair[(min(n,m),max(n,m))] for m in graph)/len(graph)
            +fre[n]+(rec[n]-early[n])*.35,
            fre[n],rec[n],-n))
        graph.append(n)
        remaining.remove(n)
    rnd=random.Random(9027+int(draw_no)*101)
    random20=rnd.sample(range(1,81),20)
    proposed=dict(zip(METHODS,(order_freq,order_momentum,order_last,graph,random20)))
    assert all(len(x)==20 and len(set(x))==20 for x in proposed.values())
    return proposed,f


def all_recurrent_families(actual,prior):
    """Every unique 2..10 subfamily in target also seen in any prior 12 draw.

    For each exact family retain first/last PREVIOUS appearance and number of
    distinct prior draws. Ordered appearances refer to previous draws only.
    """
    target=set(actual)
    seen={k:{} for k in SIZES}
    for pi,past in enumerate(prior):
        same=sorted(target.intersection(past["nums"]))
        for k in SIZES:
            if k>len(same):break
            row=seen[k]
            for nums in combinations(same,k):
                entry=row.get(nums)
                if entry is None:
                    row[nums]={"first_prior":pi+1,"last_prior":pi+1,
                               "seen":1}
                else:
                    entry["last_prior"]=pi+1
                    entry["seen"]+=1
    return seen


def witnessed_coverage(actual,prior_repeated):
    """Coverage with EXISTING pre-draw full families; never fill with hindsight.

    Disjoint family witnesses. Remaining target numbers are UNEXPLAINED.
    """
    remaining=set(actual)
    all_known=[]
    for k in SIZES:
        for nums,data in prior_repeated[k].items():
            all_known.append((nums,data))
    all_known.sort(key=lambda entry:(
        -len(entry[0]),-entry[1]["seen"],-entry[1]["last_prior"],entry[0]
    ))
    selected=[]
    for nums,evt in all_known:
        if set(nums).issubset(remaining):
            selected.append({
                "size":len(nums),"nums":nums,
                "prior_first":evt["first_prior"],
                "prior_last":evt["last_prior"],
                "prior_count":evt["seen"]
            })
            remaining.difference_update(nums)
        if not remaining:break
    selected.sort(key=lambda x:(x["prior_first"],x["prior_last"],-x["size"]))
    return selected,sorted(remaining)


def retrospective_partition(actual,previous_features):
    """A guaranteed grouping of 20 AFTER seeing target; not a prediction."""
    fre=previous_features["freq"]
    ordered=sorted(actual,key=lambda n:(-fre[n],n))
    groups=[];cursor=0
    for k in SPLIT:
        nums=tuple(ordered[cursor:cursor+k])
        groups.append(nums);cursor+=k
    assert cursor==20 and set(n for group in groups for n in group)==set(actual)
    return groups


def expected_repeat_per_target(k):
    """Expected distinct k-families in the current twenty seen in prior12.

    Under independent uniform 20/80 draws this holds even conditioning on
    the target 20-set, with a family seen zero times at rate (1-p)^12.
    """
    p=math.comb(20,k)/math.comb(80,k)
    return math.comb(20,k)*(1-(1-p)**12)


def audit_target(actual_draw,prior):
    """Explain families in actual 20 without manufacturing a physical order."""
    actual=actual_draw["nums"]
    r=all_recurrent_families(actual,prior)
    groups,missing=witnessed_coverage(actual,r)
    gfreq=history_features(prior)
    forced=retrospective_partition(actual,gfreq)
    count={k:len(r[k]) for k in SIZES}
    lags=Counter()
    for k,rows in r.items():
        for fam,entry in rows.items():
            age=13-entry["last_prior"]  # last seen at most recent prior => age 1
            lags[(k,age)]+=1
    return {
        "counts":count,"witnessed":groups,
        "uncovered":missing,"covered":20-len(missing),
        "forced":forced,"lags":lags
    }


def target_tower_row(target,prior,phase="Test",keep_detail=False):
    """One strictly pretarget forecast, plus post-outcome score and audit."""
    proposals,features=forward_towers(prior,target["no"])
    actual_set=set(target["nums"])
    methods={name:len(set(pool)&actual_set) for name,pool in proposals.items()}
    graph=proposals["Ağ-kule"]
    tier={k:len(set(graph[:k])&actual_set) for k in SIZES}
    # Partial stages 2..10 form NESTED families, not ten independent tickets.
    audit=audit_target(target,prior)
    row={
        "Gün":target["day"],"Çekiliş":target["no"],
        "Saat":target["dt"][11:16],"Gün içi sıra":target["pos"],
        "Saat içi sıra":hour_draw_index(target["pos"]),
        "Dönem":phase,"Tahmin edilen sayı":20,
        "Gerçek 20 ile ortak":methods["Ağ-kule"],
        "Önceden görülmüş ailelerin kapsadığı sayı":audit["covered"],
        "Önceki ailelerle açıklanamayan sayı":len(audit["uncovered"])
    }
    for method,matched in methods.items():row[method]=matched
    for k in SIZES:
        row[f"{k}'li aile ortak"]=tier[k]
        row[f"{k}'li aile tam"]=int(tier[k]==k)
        row[f"{k}'li geçmişte tam görünen farklı aile"]=audit["counts"][k]
    if keep_detail:
        row["Sayı kulesi sırası"]="-".join(f"{n:02d}" for n in graph)
        row["Gerçek 20"]="-".join(f"{n:02d}" for n in target["nums"])
        row["Kapsanamayan"]=("-".join(f"{n:02d}" for n in audit["uncovered"]))
        row["Önceden görülen aile sırası"]= " | ".join(
            f'#{g["prior_first"]}/#{g["prior_last"]} ({g["size"]}):'+
            "-".join(map(str,g["nums"])) for g in audit["witnessed"])
        row["Sonradan oluşturulan 2+3+4+5+6 sırası"]= " | ".join(
            "-".join(map(str,g)) for g in audit["forced"])
    return row,audit,proposals


def summary_rows(allrows):
    stats=[]
    periods=("İlk dönem","Sonraki dönem")
    for period in periods:
        rr=[r for r in allrows if r["Dönem"]==period]
        if not rr:continue
        for method in METHODS:
            counts=Counter(r[method] for r in rr)
            stats.append({
                "Dönem":period,"Yöntem":method,"Hedef":len(rr),
                "20/20":counts[20],
                "Ortalama 20'de isabet":round(sum(r[method] for r in rr)/len(rr),4),
                "Rastgele matematik beklenen":5.0,
                "Dağılım 0..20":"/".join(str(counts[j]) for j in range(21))
            })
    return stats


def run_tower_study(draws,train_days=36):
    """Complete, chronological 7–12 slots, each frozen from previous 12 draws."""
    byday=defaultdict(list)
    for d in make_ready(draws):
        byday[d["day"]].append(d)
    days=sorted(byday)
    if days and len(byday[days[-1]])<217:
        days=days[:-1]  # exclude unfinished final date from whole-day study
    result=[]
    overall=Counter()
    by_position=defaultdict(lambda:Counter())
    lag_counter=Counter()
    for di,day in enumerate(days):
        rs=byday[day]
        bypos={r["pos"]:r for r in rs}
        phase="İlk dönem" if di<train_days else "Sonraki dönem"
        for target in rs:
            if hour_draw_index(target["pos"]) not in (7,8,9,10,11,12):
                continue
            prior=complete_preceding_12(bypos,target["pos"])
            if prior is None:continue
            row,audit,_=target_tower_row(target,prior,phase)
            result.append(row)
            overall[(phase,"covered")]+=audit["covered"]
            for k,c in audit["counts"].items():
                overall[(phase,k)]+=c
            for (k,age),v in audit["lags"].items():
                lag_counter[(phase,k,age)]+=v
            slot=hour_draw_index(target["pos"])
            for method in METHODS:
                by_position[(phase,slot)][method]+=row[method]
            by_position[(phase,slot)]["n"]+=1
    methods=summary_rows(result)
    recurrent=[]
    for phase in ("İlk dönem","Sonraki dönem"):
        n=sum(r["Dönem"]==phase for r in result)
        if not n:continue
        for k in SIZES:
            observed=overall[(phase,k)]/n
            expected=expected_repeat_per_target(k)
            recurrent.append({
                "Dönem":phase,"Boyut":k,"Toplam hedef":n,
                "Her hedefte olası aile":math.comb(20,k),
                "Geçmiş 12'de daha önce tam görülmüş ortalama aile":round(observed,4),
                "Bağımsız çekilişte matematik beklenti":round(expected,4),
                "Gözlenen / beklenen":round(observed/expected,4) if expected else None
            })
    slotted=[]
    for (phase,slot),s in sorted(by_position.items()):
        n=s["n"]
        for method in METHODS:
            slotted.append({"Dönem":phase,"Saat içi çekiliş":slot,
                            "Yöntem":method,"Hedef":n,
                            "Ortalama 20'de isabet":round(s[method]/n,4)})
    return {
        "meta":{"days":len(days),"first":days[0] if days else "",
                "last":days[-1] if days else "",
                "targets":len(result),
                "train_days":train_days,
                "all_family_sizes":SIZES,
                "evidence_note":"Draw results are unordered sets; reported family 'order' is pre-draw historical appearance order, NOT physical extraction order."},
        "methods":methods,"recurrent":recurrent,
        "age_lags":[{"Dönem":phase,"Boyut":k,"En son kaç çekiliş önce":age,
                     "Ortak aile olayları":v}
                    for (phase,k,age),v in sorted(lag_counter.items())],
        "slot_methods":slotted,
        "ledger":result
    }


def next_draw_tower(day_draws,target_no,target_pos):
    """Only future target slots. Returns nothing when prior history is absent."""
    day_draws=make_ready(day_draws)
    bypos={r["pos"]:r for r in day_draws}
    if target_pos in bypos or target_pos<1 or target_pos>217:
        return None
    if hour_draw_index(target_pos) not in (7,8,9,10,11,12):
        return None
    prior=complete_preceding_12(bypos,target_pos)
    if prior is None:return None
    proposals,features=forward_towers(prior,target_no)
    graph=proposals["Ağ-kule"]
    composition=[]
    idx=0
    for k in SPLIT:
        segment=graph[idx:idx+k]
        count=sum(set(segment).issubset(set(d["nums"])) for d in prior)
        composition.append({"Boyut":k,"Aile":"-".join(f"{n:02d}" for n in segment),
                            "Geçmiş 12'de tam görünüş":count,"Kuruluş aşaması":idx+1})
        idx+=k
    stairs=[
        {"Boyut":k,"Aile":"-".join(f"{n:02d}" for n in graph[:k]),
         "Ağ-kule büyüme aşaması":k}
        for k in SIZES
    ]
    ranking=sorted(range(1,81),key=lambda n:(-features["freq"][n],n))
    nodes=[{"Sayı":n,"12'de":features["freq"][n],
            "İlk6":features["early"][n],"Son6":features["recent"][n],
            "Kulede":n in set(graph),
            "Ağ-kule sırası":1+graph.index(n) if n in set(graph) else ""}
           for n in ranking]
    return {"target":target_no,"pos":target_pos,"proposals":proposals,
            "composition":composition,"stairs":stairs,"nodes":nodes}


def csv_export(rows):
    if not rows:return ""
    out=io.StringIO()
    writer=csv.DictWriter(out,fieldnames=list(rows[0]),delimiter=";")
    writer.writeheader()
    for row in rows:writer.writerow(row)
    return "\ufeff"+out.getvalue()
