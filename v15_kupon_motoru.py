# -*- coding: utf-8 -*-
"""V15 6-ticket coupon engine + 2..10 nested family forecast.

For each eligible 7th..12th hourly slot, output exactly six diverse TEN-number
tickets, using only the preceding 12 actual draws and models trained on earlier
calendar days. Models are frozen for the entire holdout period.

CRITICAL: Prefix families 2..10 are declared BEFORE the target result. A full
6-number subset chosen retrospectively from a lucky 10-number ticket is NOT
counted as a six-family prediction. Against 6 model tickets, ALWAYS run 6
independently generated random ten-number tickets on the SAME target.
"""
import csv
import hashlib
import io
import json
import math
import random
from collections import Counter,defaultdict

from v11_arastirma import hour_draw_index, complete_preceding_12
from v12_80_kule import make_ready,forward_towers
from v13_havuz_koltuk import (
    states_for_day,trained_model as v13_train,
    conditional_rate,quotas
)
from v14_gecis_agi import (
    pair_model as v14_train,
    predict_20 as v14_predict,
    candidate_score
)

N_TICKETS=6
FAMILY_SIZES=tuple(range(2,11))
METHODS=(
    "V12 aile omurgası",
    "V13 ısı koltukları",
    "V14 +1 geçiş",
    "V14 +1/+2/+3/+6/+12",
    "Birleşik aile kulesi",
    "Dağıtılmış aile kulesi",
)
RANDOM="6 rastgele kontrol"


def fit_models(draws,train_days=36):
    """Freeze model based on first N calendar days, only."""
    byday=defaultdict(list)
    for d in make_ready(draws):
        byday[d["day"]].append(d)
    days=sorted(byday)
    if len(days)<train_days:
        raise ValueError("En az %d eğitim günü gerekli" % train_days)
    training=[d for day in days[:train_days] for d in byday[day]]
    return {"train_days":train_days,
            "training_from":days[0],
            "training_through":days[train_days-1],
            "transition":v14_train(training,train_days),
            "temperature":v13_train(training,train_days)}


def fair_ten_probability(k):
    return math.prod((20-i)/(80-i) for i in range(k))


def _stable_seed(day,position,iteration=0):
    payload=f"V15:{day}:{position}:{iteration}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8],"big")


def control_tickets(day,pos):
    """Six independently sampled 10-ball ticket comparators, fixed seed."""
    rng=random.Random(_stable_seed(day,pos,555))
    seen=set()
    coupons=[]
    while len(coupons)<N_TICKETS:
        ticket=tuple(rng.sample(range(1,81),10))
        key=tuple(sorted(ticket))
        if key not in seen:
            seen.add(key);coupons.append(ticket)
    return coupons


def _rank_pool(numbers,score):
    return sorted(numbers,key=lambda n:(-score[n],n))


def _diversity(order,other_tickets,min_new=2):
    """Preserve seed while avoiding duplicate six 10-ball tickets."""
    ticket=[]
    chosen=set()
    for n in order:
        if n not in chosen and len(ticket)<10:
            ticket.append(n);chosen.add(n)
    if len(ticket)!=10:
        raise ValueError("Model failed to propose 10 unique balls")
    existing={tuple(sorted(x)) for x in other_tickets}
    if tuple(sorted(ticket)) not in existing:return tuple(ticket)
    # Resolve ties using this model's own ranking, WITHOUT consulting results.
    for replace_index in range(9,-1,-1):
        for n in order[10:]:
            if n in chosen:continue
            proposal=ticket[:replace_index]+[n]+ticket[replace_index+1:]
            if tuple(sorted(proposal)) not in existing:
                return tuple(proposal)
    raise ValueError("Cannot distinguish proposed tickets")


def _covered_order(order,previous,minimum_new=7):
    """Coverage variant: keep two family seeds, require >=7 unseen numbers.

    Purely deterministic selection made before target result; this is a new
    exploratory strategy, not a model 'improved' on untouched holdout data.
    """
    seen=set(n for ticket in previous for n in ticket)
    if not previous:
        return tuple(order[:10])
    chosen=[]
    for n in order[:2]:
        if n not in chosen:chosen.append(n)
    fresh=sum(n not in seen for n in chosen)
    for n in order:
        if fresh>=minimum_new:break
        if n not in chosen and n not in seen:
            chosen.append(n)
            fresh+=1
    for n in order:
        if len(chosen)>=10:break
        if n not in chosen:chosen.append(n)
    assert len(chosen)==10 and len(set(chosen))==10
    assert sum(n not in seen for n in chosen)>=minimum_new
    return tuple(chosen)


def _ordered_v14(prior,pos,models,target_no,multi=False):
    model=models["transition"]
    style="V14 çok-adım ağ" if multi else "V14 bir-adım ağ"
    pool=v14_predict(model,prior,pos,style,target_no)
    bypos={d["pos"]:d for d in prior}
    prev=set(bypos[pos-1]["nums"])
    sources=(1,2,3,6,12) if multi else (1,)
    still=[n for n in pool if n in prev]
    new=[n for n in pool if n not in prev]
    still.sort(key=lambda n:(
        -(model["stay_hit"][n]+75)/(model["stay_count"][n]+300),n))
    new.sort(key=lambda n:(-candidate_score(model,bypos,pos,n,sources),n))
    n_stay=3 if multi else 2
    return still[:n_stay]+new[:10-n_stay]+still[n_stay:]+new[10-n_stay:]


def build_six(day_history,target_pos,target_no,models,coverage=False):
    """Return six TEN-number tickets, ordered by frozen pretarget preference."""
    history=make_ready(day_history)
    bypos={r["pos"]:r for r in history}
    if target_pos in bypos:
        raise ValueError("Hedef çekiliş sonucu zaten mevcut: geçmişe tahmin yazılmaz")
    if hour_draw_index(target_pos) not in (7,8,9,10,11,12):
        raise ValueError("V15 yalnız saatin 7–12. çekilişlerinde hedef kurar")
    prior=complete_preceding_12(bypos,target_pos)
    if prior is None:
        raise ValueError("Hedef öncesinde 12 kesintisiz çekiliş yok")
    prior_set=set(bypos[target_pos-1]["nums"])
    st=states_for_day([r for r in history if r["pos"]<target_pos])
    state_by_n={r["n"]:r for r in st}
    temp=models["temperature"]
    network=models["transition"]
    graph,_=forward_towers(prior,target_no)
    spine=graph["Ağ-kule"][:]
    f12=Counter(n for r in prior for n in r["nums"])
    prob={n:conditional_rate(temp,target_pos,state_by_n[n])
          for n in range(1,81)}
    # Candidate ticket 1: deliberately retain V12's ordered family growth.
    v12_order=spine+[
        n for n in range(1,81) if n not in spine
    ]
    # Ticket 2: preserve proportional warm/cold/medium ten seats.
    all_seats=quotas(st,temp,target_pos)
    raw_seats={pool:count/2 for pool,count in all_seats.items()}
    chosen_quota={pool:int(math.floor(q)) for pool,q in raw_seats.items()}
    need=10-sum(chosen_quota.values())
    for pool in sorted(raw_seats,key=lambda p:(
        -(raw_seats[p]-chosen_quota[p]),p)):
        if need<=0:break
        chosen_quota[pool]+=1;need-=1
    groups=defaultdict(list)
    for r in st:groups[r["pool"]].append(r["n"])
    v13_order=[]
    remaining=[]
    for pool in sorted(groups):
        order=_rank_pool(groups[pool],prob)
        q=chosen_quota.get(pool,0)
        v13_order.extend(order[:q])
        remaining.extend(order[q:])
    remaining.sort(key=lambda n:(-prob[n],n))
    v13_order+=remaining
    for n in range(1,81):
        if n not in v13_order:v13_order.append(n)
    # Ticket 3 & 4: 2/3 carried and 8/7 new numbers, selected from lag network.
    lag1=_ordered_v14(prior,target_pos,models,target_no,False)
    lagall=_ordered_v14(prior,target_pos,models,target_no,True)
    lag1+=list(n for n in range(1,81) if n not in lag1)
    lagall+=list(n for n in range(1,81) if n not in lagall)
    # Ticket 5: equal-scale ranks of V12, V13, and V14 + rolling frequency.
    lag_scores={
        n:candidate_score(network,bypos,target_pos,n,(1,2,3,6,12))
        for n in range(1,81) if n not in prior_set
    }
    lag_scores.update({
        n:((network["stay_hit"][n]+75)/
           (network["stay_count"][n]+300)-.25)
        for n in prior_set
    })
    rank_graph={n:i for i,n in enumerate(v12_order)}
    rank_state={n:i for i,n in enumerate(sorted(
        range(1,81),key=lambda n:(-prob[n],n)
    ))}
    rank_lags={n:i for i,n in enumerate(sorted(
        range(1,81),key=lambda n:(-lag_scores[n],n)
    ))}
    rank_freq={n:i for i,n in enumerate(sorted(
        range(1,81),key=lambda n:(-f12[n],n)
    ))}
    fusion={
        n:.32*(1-rank_graph[n]/80)
          +.29*(1-rank_state[n]/80)
          +.29*(1-rank_lags[n]/80)
          +.10*(1-rank_freq[n]/80)
        for n in range(1,81)
    }
    # Freeze a stable family seed: first two V12 graph numbers.
    family_seed=spine[:2]
    fusion_order=family_seed+_rank_pool(
        [n for n in range(1,81) if n not in family_seed],fusion)
    proposals=[v12_order,v13_order,lag1,lagall,fusion_order]
    tickets=[]
    for order in proposals:
        tickets.append(
            _covered_order(order,tickets) if coverage
            else _diversity(order,tickets)
        )
    # Ticket 6: diversify from all first five while respecting the same scores.
    exposure=Counter(n for ticket in tickets for n in ticket)
    diverse=sorted(range(1,81),key=lambda n:(
        -(fusion[n]-.07*exposure[n]),n
    ))
    tickets.append(
        _covered_order(diverse,tickets) if coverage
        else _diversity(diverse,tickets)
    )
    assert len(tickets)==N_TICKETS
    assert all(len(t)==10 and len(set(t))==10 for t in tickets)
    return [
        {"method":method,"numbers":tuple(ticket),
         "family6":tuple(ticket[:6]),
         "target_pos":target_pos,"target_no":target_no,
         "day":history[0]["day"],"lookback":12}
        for method,ticket in zip(METHODS,tickets)
    ]


def result_of(coupons,actual):
    """Score prospective tickets and frozen nested 2..10 family prefixes."""
    target=set(actual)
    return [{
        "method":p["method"],
        "numbers":p["numbers"],
        "ten":len(target.intersection(p["numbers"])),
        "prefix":{k:len(target.intersection(p["numbers"][:k]))
                  for k in FAMILY_SIZES}
    } for p in coupons]


def _stats(rows,category):
    denom=len(rows)
    out=[]
    for key in METHODS+(RANDOM,):
        hits=[r["hit"] for r in rows if r["method"]==key]
        if not hits:continue
        hist=Counter(hits)
        out.append({
            "Grup":category,"Kupon yolu":key,"Hedef":len(hits),
            "Ortalama 10'da":round(sum(hits)/len(hits),4),
            "En fazla":max(hits),
            "10/10":hist[10],
            "Rastgele teorik ortalama":2.5,
            "0..10 isabet sayıları":"/".join(str(hist[k]) for k in range(11)),
        })
    return out


def retrospective_test(draws,train_days=36,coverage=False):
    """37-day untouched chronological evaluation: 6 model + 6 random coupons.

    This is not a prospective live blind test: development was prompted by the
    same historical dataset. Treat it as exploratory and require future logs.
    """
    raw=make_ready(draws)
    byday=defaultdict(list)
    for d in raw:byday[d["day"]].append(d)
    days=sorted(byday)
    if days and len(byday[days[-1]])<217:
        days=days[:-1]
    if len(days)<=train_days:
        raise ValueError("Gün sayısı yetersiz")
    models=fit_models([r for day in days[:train_days]
                         for r in byday[day]],train_days)
    results=[]
    family_scores=defaultdict(lambda:{"trials":0,"full":0,"sum":0,
                                      "last":0})
    best=defaultdict(Counter)
    differences=[]
    detailed=[]
    for day in days[train_days:]:
        today=sorted(byday[day],key=lambda r:r["pos"])
        bypos={r["pos"]:r for r in today}
        for target in today:
            if hour_draw_index(target["pos"]) not in (7,8,9,10,11,12):
                continue
            prior=complete_preceding_12(bypos,target["pos"])
            if prior is None:
                continue
            # STRICT: pass ALL earlier same-day draws for 217-slot V13 heat
            # identity; the most recent twelve still form V12's family window.
            # The target and later outcomes are explicitly excluded.
            earlier=[r for r in today if r["pos"]<target["pos"]]
            tickets=build_six(earlier,target["pos"],target["no"],models,coverage=coverage)
            control=[{"method":RANDOM,"numbers":coupon}
                     for coupon in control_tickets(day,target["pos"])]
            model_hits=[]
            random_hits=[]
            for p in tickets+control:
                label=p["method"]
                nums=p["numbers"]
                got=len(set(nums).intersection(target["nums"]))
                results.append({"method":label,"hit":got})
                if label==RANDOM:random_hits.append(got)
                else:model_hits.append(got)
                for k in FAMILY_SIZES:
                    hits=len(set(nums[:k]).intersection(target["nums"]))
                    row=family_scores[(label,k)]
                    row["trials"]+=1
                    row["sum"]+=hits
                    row["full"]+=int(hits==k)
                    row["last"]=max(row["last"],hits)
                detailed.append({
                    "Gün":day,"Çekiliş":target["no"],
                    "Saat":target["dt"][11:16],"Hedef sıra":target["pos"],
                    "Motor":label,
                    "Kupon":"-".join(f"{n:02d}" for n in sorted(nums)),
                    "Önceden 6'lı aile":"-".join(f"{n:02d}" for n in sorted(nums[:6])),
                    "10'da isabet":got,
                    "6'lı isabet":len(set(nums[:6]).intersection(target["nums"]))
                })
            m=max(model_hits)
            c=max(random_hits)
            model_union=len(set().union(*(set(p["numbers"]) for p in tickets)))
            random_union=len(set().union(*(set(nums) for nums in
                                            control_tickets(day,target["pos"]))))
            best["Model altı kupon"][m]+=1
            best["Rastgele altı kupon"][c]+=1
            differences.append({"Gün":day,"Hedef":target["no"],
                                "Saat":target["dt"][11:16],
                                "Model altı kupon en iyi":m,
                                "Rastgele altı kupon en iyi":c,
                                "Fark":m-c,
                                "Model altı kupon farklı sayı":model_union,
                                "Rastgele altı kupon farklı sayı":random_union,
                                "Model 6'lı tam":sum(
                                    len(set(p["family6"]).intersection(target["nums"]))==6
                                    for p in tickets),
                                "Rastgele 6'lı tam":sum(
                                    len(set(nums[:6]).intersection(target["nums"]))==6
                                    for nums in control_tickets(day,target["pos"]))
                               })
    families=[]
    for (method,k),r in sorted(family_scores.items()):
        families.append({"Kupon yolu":method,"Aile boyutu":k,
                         "Deneme":r["trials"],"Tam k/k":r["full"],
                         "Ortalama isabet":round(r["sum"]/r["trials"],4),
                         "Rastgele beklenen":k/4,
                         "En fazla":r["last"]})
    counts=[]
    for name in best:
        hist=best[name]
        counts.append({"Grup":name,"Hedef":sum(hist.values()),
                       "En iyi kupon ortalama":round(sum(k*v for k,v in hist.items())/sum(hist.values()),4),
                       "En fazla":max(hist),
                       "0..10 dağılım":"/".join(str(hist[k]) for k in range(11))})
    summary={
        "mode":"Geniş kapsama (en az 7 yeni sayı/kupon)" if coverage
                 else "Aile odaklı (özgün motorlar)",
        "train_days":train_days,"test_days":len(days)-train_days,
        "first_test":days[train_days],"last_test":days[-1],
        "targets":len(differences),"coupons":len(detailed),
        "model_coupons":6*len(differences),
        "random_coupons":6*len(differences),
        "model_6_full":sum(x["Model 6'lı tam"] for x in differences),
        "random_6_full":sum(x["Rastgele 6'lı tam"] for x in differences),
        "model_coverage":round(sum(x["Model altı kupon farklı sayı"] for x in differences)/len(differences),3),
        "random_coverage":round(sum(x["Rastgele altı kupon farklı sayı"] for x in differences)/len(differences),3),
        "test_note":"Exploratory chronological retrospective test, NOT prospectively registered live blind data.",
    }
    return {"summary":summary,"methods":_stats(results,"37 günlük test"),
            "families":families,"best6":counts,
            "differences":differences,"ledger":detailed}


def as_csv(rows):
    if not rows:return ""
    out=io.StringIO()
    w=csv.DictWriter(out,fieldnames=list(rows[0]),delimiter=";")
    w.writeheader()
    w.writerows(rows)
    return "\ufeff"+out.getvalue()
