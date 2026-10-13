# -*- coding: utf-8 -*-
"""V13 — 217-draw, 80-node temperature tower integrated with V12.

Architecture:
- Each of 80 balls has a 217-slot daily identity: cumulative count, gap,
  last 12 frequency, last 6 vs previous 6 change, heat/peak/cooling.
- Every target's 20 seats split by cold/warm/hot/early *before* viewing target.
- Train category hit propensity and seat calibration on first N complete days.
- Hold out later days for chronological no-leakage comparisons, fixed model.
- V12 graph tower is a distinct benchmark/feature for 7..12 hour target slots.
- All-cold/all-peak six-family tests are prospectively frozen, not hindsight.

All physical draws are unordered 20-number sets; seats are statistical buckets,
not physical positions. Under fair independent draws conditional hit p=20/80.
"""
import csv
import io
import math
import random
from collections import Counter,defaultdict
from v12_80_kule import forward_towers,make_ready,mask_of
from v11_arastirma import hour_draw_index, complete_preceding_12

SIZES=tuple(range(2,11))
TYPES=("Soğuk","Ilık","Sıcak","Erken")
PROPOSALS=("Koltuk-model","Tepeyi azalt","Tepeyi koru",
           "Koltuk+V12","V12 ağ-kule","Rastgele20")
PRIOR_STRENGTH=450


def phase(pos):
    return "Başlangıç" if pos<=36 else "Orta" if pos<=144 else "Son"


def confidence_hit(k):
    return math.prod((20-i)/(80-i) for i in range(k))


def _family_mask(numbers):
    return sum(1<<(n-1) for n in numbers)


def state_of(day_seen, n):
    """Compute only pre-target state for exactly one of 80 numbers."""
    h=len(day_seen)
    count=sum(n in d["nums"] for d in day_seen)
    last12=day_seen[-12:]
    last6=day_seen[-6:]
    prev6=day_seen[-12:-6]
    f12=sum(n in d["nums"] for d in last12)
    f6=sum(n in d["nums"] for d in last6)
    prev=sum(n in d["nums"] for d in prev6)
    gap=next((j for j,d in enumerate(reversed(day_seen),1)
              if n in d["nums"]),None)
    gap=h+1 if gap is None else gap
    z=(count-.25*h)/math.sqrt(.1875*h) if h else 0
    d=f6-prev
    if h<6:
        pool="Erken"
        label="Erken veri"
    elif z<=-1.0:
        pool="Soğuk"
        if f6>=2 and d>=2:label="Soğuk-uyanıyor"
        elif gap>=7 and f6==0:label="Soğuk-dinleniyor"
        else:label="Soğuk-durgun"
    elif z>=1.0:
        pool="Sıcak"
        if f12>=5 and (f6>=4 or (f6>=3 and d<=0)):
            label="Sıcak-tepe"
        elif d>=2:label="Sıcak-yükseliyor"
        elif d<=-2:label="Sıcak-soğuyor"
        else:label="Sıcak-yerleşik"
    else:
        pool="Ilık"
        if d>=2:label="Ilık-yükseliyor"
        elif d<=-2:label="Ilık-soğuyor"
        else:label="Ilık-dengeli"
    return {"n":n,"pool":pool,"label":label,"day":count,"seen":h,
            "z":round(z,4),"recent12":f12,"recent6":f6,"prev6":prev,
            "slope":d,"gap":gap}


def states_for_day(day_seen):
    """State over all 80 numbers; no target included."""
    # One pass through prior draws for 80-ball daily counters (fast path).
    h=len(day_seen)
    daily=[0]*81
    recent=[0]*81
    new=[0]*81
    prior=[0]*81
    last_pos=[-1]*81
    for i,d in enumerate(day_seen):
        for n in d["nums"]:
            daily[n]+=1
            last_pos[n]=i
            if i>=h-12:recent[n]+=1
            if i>=h-6:new[n]+=1
            elif i>=h-12:prior[n]+=1
    result=[]
    for n in range(1,81):
        count=daily[n]
        f12=recent[n]
        f6=new[n]
        p=prior[n]
        gap=h-last_pos[n] if last_pos[n]>=0 else h+1
        z=(count-.25*h)/math.sqrt(.1875*h) if h else 0.
        slope=f6-p
        if h<6:
            pool="Erken";label="Erken veri"
        elif z<=-1.0:
            pool="Soğuk"
            if f6>=2 and slope>=2:label="Soğuk-uyanıyor"
            elif gap>=7 and f6==0:label="Soğuk-dinleniyor"
            else:label="Soğuk-durgun"
        elif z>=1.0:
            pool="Sıcak"
            if f12>=5 and (f6>=4 or (f6>=3 and slope<=0)):
                label="Sıcak-tepe"
            elif slope>=2:label="Sıcak-yükseliyor"
            elif slope<=-2:label="Sıcak-soğuyor"
            else:label="Sıcak-yerleşik"
        else:
            pool="Ilık"
            if slope>=2:label="Ilık-yükseliyor"
            elif slope<=-2:label="Ilık-soğuyor"
            else:label="Ilık-dengeli"
        result.append({"n":n,"pool":pool,"label":label,"day":count,
                       "seen":h,"z":round(z,4),"recent12":f12,
                       "recent6":f6,"prev6":p,"slope":slope,"gap":gap})
    return result


def trained_model(draws,train_days=36):
    """Only first train_days' target results are used for calibration."""
    byday=defaultdict(list)
    for r in make_ready(draws):
        byday[r["day"]].append(r)
    days=sorted(byday)
    seen=defaultdict(lambda:[0,0])
    seat_groups=defaultdict(lambda:[0,0,0])
    # 80 input rows per single draw, evaluated BEFORE adding its 20 outcomes.
    for day in days[:train_days]:
        past=[]
        for target in sorted(byday[day],key=lambda r:r["pos"]):
            states=states_for_day(past)
            actual=set(target["nums"])
            slots=Counter(s["pool"] for s in states)
            found=Counter(s["pool"] for s in states if s["n"] in actual)
            ph=phase(target["pos"])
            for st in states:
                key=(ph,st["label"])
                seen[key][0]+=1
                seen[key][1]+=int(st["n"] in actual)
            for pool in TYPES:
                a=seat_groups[(ph,pool)]
                a[0]+=1;a[1]+=slots[pool];a[2]+=found[pool]
            past.append(target)
    estimates={}
    for key,(n,hits) in seen.items():
        # Shrink to fair conditional 20/80 probability; no strong priors learned.
        estimates[key]=(hits+.25*PRIOR_STRENGTH)/(n+PRIOR_STRENGTH)
    return {"days":tuple(days[:train_days]),"estimates":estimates,
            "train_counts":dict(seen),"train_seats":dict(seat_groups),
            "train_draws":sum(len(byday[d]) for d in days[:train_days])}


def conditional_rate(model, pos, st):
    return model["estimates"].get((phase(pos),st["label"]),.25)


def quotas(states,model,pos):
    """20 seats across 80 preclassified balls, via largest remainder."""
    bypool=defaultdict(list)
    for st in states:bypool[st["pool"]].append(st)
    weights={}
    for pool,ss in bypool.items():
        weights[pool]=sum(conditional_rate(model,pos,st) for st in ss)
    denom=sum(weights.values()) or 1
    raw={pool:20*value/denom for pool,value in weights.items()}
    seats={pool:min(len(bypool[pool]),int(math.floor(q)))
           for pool,q in raw.items()}
    need=20-sum(seats.values())
    for pool in sorted(weights,key=lambda p:(-(raw[p]-math.floor(raw[p])),p)):
        if need<=0:break
        if seats[pool]<len(bypool[pool]):
            seats[pool]+=1;need-=1
    if need:
        for pool in sorted(weights):
            room=len(bypool[pool])-seats[pool]
            add=min(room,need);seats[pool]+=add;need-=add
            if not need:break
    assert sum(seats.values())==20
    return seats


def pick_20(states,model,pos,style="Koltuk-model",v12_graph=None):
    """Build 20 WITHOUT observing its result; deterministic construction."""
    seats=quotas(states,model,pos)
    bypool=defaultdict(list)
    graph_rank={n:i for i,n in enumerate(v12_graph or ())}
    for st in states:bypool[st["pool"]].append(st)
    selected=[]
    for pool,q in seats.items():
        def weight(st):
            p=conditional_rate(model,pos,st)
            z=st["z"]
            if style=="Tepeyi azalt" and st["label"]=="Sıcak-tepe":
                p-=.06
            if style=="Tepeyi koru" and st["label"]=="Sıcak-tepe":
                p+=.06
            # Explicitly small V12 graph tie breaker for combined method.
            if style=="Koltuk+V12" and st["n"] in graph_rank:
                p+=.008*(20-graph_rank[st["n"]])/20
            # Extra terms are predetermined tie breakers, not trained evidence.
            return (p,st["slope"]*.0001,-st["gap"]*.00001,-st["n"])
        selected.extend(sorted(bypool[pool],key=weight,reverse=True)[:q])
    # The 20 members are fixed by the seat quotas; their ORDER is the
    # genuinely pretarget construction ranking for nested 2..10 families.
    # Do NOT numeric-sort: that would make the first k tickets arbitrary.
    selected.sort(key=weight,reverse=True)
    numbers=tuple(st["n"] for st in selected)
    assert len(numbers)==20 and len(set(numbers))==20
    return numbers,seats


def family_test(states,target,analysis_sizes=SIZES):
    """Frozen ONE family candidate per pool/size, for every draw.

    Actual can be inspected ONLY after selected family is frozen.
    Record available candidates, partial hits and full outcomes.
    """
    actual=set(target["nums"])
    grouped=defaultdict(list)
    for st in states:
        grouped[st["pool"]].append(st)
        grouped[st["label"]].append(st)
    results=[]
    cohorts=("Soğuk","Ilık","Sıcak",
             "Soğuk-uyanıyor","Soğuk-dinleniyor",
             "Sıcak-yükseliyor","Sıcak-tepe","Sıcak-soğuyor")
    for pool in cohorts:
        allpool=grouped[pool]
        # Only ranking of previous state, never outcome or target number.
        ordered=sorted(allpool,key=lambda s:(
            -s["recent12"],-s["slope"],s["n"]))
        for k in analysis_sizes:
            if len(ordered)<k:continue
            family=tuple(st["n"] for st in ordered[:k])
            got=len(actual.intersection(family))
            family_occ=sum(s["n"] in actual for s in allpool)
            # Ex-post: how many FULL all-pool-k families were in the target?
            # Combinatorial count, not a forecast success.
            realized=math.comb(family_occ,k) if family_occ>=k else 0
            results.append({"Grup":pool,"Boyut":k,
                            "Hedef":target["no"],
                            "Sayılar":family,"İsabet":got,
                            "Tam":int(got==k),
                            "Grup havuzu":len(allpool),
                            "Hedefte grup koltuk":family_occ,
                            "Hedefteki tüm tam aile":realized,
                            "Rastgele tam olasılık":math.prod(
                                (20-i)/(80-i) for i in range(k))})
    return results


def run_study(draws,train_days=36,include_today=False,details_limit=100):
    """Cross-day frozen calibration; 217-slot full-day walk-forward holdout.

    Full day for day-state and three simple seat methods; V12 graph only on
    hour slots 7–12 with 12 contiguous previous draws.
    """
    dataset=make_ready(draws)
    byday=defaultdict(list)
    for r in dataset:byday[r["day"]].append(r)
    days=sorted(byday)
    if not include_today and days and len(byday[days[-1]])<217:
        days=days[:-1]
    model=trained_model([d for day in days[:train_days] for d in byday[day]],
                        train_days=train_days)
    train=tuple(days[:train_days])
    holdout=days[train_days:]
    rows=[]
    method_stats=defaultdict(lambda:{"n":0,"sum":0,"max":0,"twenty":0,
                                    "hist":Counter(),"seven_to_twelve":0})
    seat_ledger=defaultdict(lambda:[0,0,0,0,0])
    exact_seats=defaultdict(lambda:[0,0,0.0])
    stage_results=defaultdict(lambda:[0,0])
    family_stats=defaultdict(lambda:{"n":0,"complete":0,"sum":0,
                                     "any_full_at_target":0})
    nested_stats=defaultdict(lambda:{"n":0,"sum":0,"full":0,"hist":Counter()})
    examples=[]
    allfamily=[]
    for day in holdout:
        history=[]
        bypos={r["pos"]:r for r in byday[day]}
        for target in sorted(byday[day],key=lambda r:r["pos"]):
            states=states_for_day(history)
            pred_seats=quotas(states,model,target["pos"])
            actual=set(target["nums"])
            pools=Counter(st["pool"] for st in states)
            found=Counter(st["pool"] for st in states if st["n"] in actual)
            ph=phase(target["pos"])
            slot=hour_draw_index(target["pos"])
            # Exact seat vector is a separate falsifiable forecast. Calculate
            # its fair multivariate-hypergeometric chance BEFORE target result.
            p_random=1.0
            for pool in TYPES:
                p_random*=math.comb(pools[pool],pred_seats.get(pool,0))
            p_random/=math.comb(80,20)
            exact=all(found[pool]==pred_seats.get(pool,0) for pool in TYPES)
            ex=exact_seats[ph]
            ex[0]+=1;ex[1]+=int(exact);ex[2]+=p_random
            for pool in TYPES:
                v=seat_ledger[(ph,pool)]
                v[0]+=1
                v[1]+=pools[pool]
                v[2]+=pred_seats.get(pool,0)
                v[3]+=found[pool]
                v[4]+=abs(found[pool]-pred_seats.get(pool,0))
            for st in states:
                v=stage_results[(ph,st["label"])]
                v[0]+=1;v[1]+=int(st["n"] in actual)
            out={"Tarih":day,"Hedef":target["no"],
                 "Saat":target["dt"][11:16],"Gün sıra":target["pos"],
                 "Saat sıra":slot,
                 "Soğuk havuz":pools["Soğuk"],
                 "Ilık havuz":pools["Ilık"],
                 "Sıcak havuz":pools["Sıcak"],
                 "Soğuk koltuk":found["Soğuk"],"Ilık koltuk":found["Ilık"],
                 "Sıcak koltuk":found["Sıcak"],
                 "Öngörülen soğuk koltuk":pred_seats.get("Soğuk",0),
                 "Öngörülen ılık koltuk":pred_seats.get("Ilık",0),
                 "Öngörülen sıcak koltuk":pred_seats.get("Sıcak",0)}
            proposals={}
            for method in ("Koltuk-model","Tepeyi azalt","Tepeyi koru"):
                coupon,_=pick_20(states,model,target["pos"],method)
                proposals[method]=coupon
            rand=random.Random(int(target["no"])*73+49)
            proposals["Rastgele20"]=tuple(sorted(rand.sample(range(1,81),20)))
            previous12=complete_preceding_12(bypos,target["pos"])
            if previous12 and slot in (7,8,9,10,11,12):
                pastproposals,_=forward_towers(previous12,target["no"])
                graph=pastproposals["Ağ-kule"]
                proposals["V12 ağ-kule"]=tuple(graph)
                proposals["Koltuk+V12"]=pick_20(
                    states,model,target["pos"],"Koltuk+V12",graph)[0]
            comparable=(previous12 is not None
                        and slot in (7,8,9,10,11,12))
            for name,numbers in proposals.items():
                matched=len(set(numbers)&actual)
                out[name]=matched
                st=method_stats[(name,"7–12" if comparable else "Diğer")]
                st["n"]+=1;st["sum"]+=matched
                st["max"]=max(st["max"],matched)
                st["hist"][matched]+=1;st["twenty"]+=int(matched==20)
            # k=2..10 nested family levels of the SAME 20-number proposal.
            primary=proposals["Koltuk-model"]
            for k in SIZES:
                vals=tuple(primary[:k]) # V13 score-ordered construction
                got=len(actual.intersection(vals))
                out[f"{k}'li iç aile"]=got
                nst=nested_stats[k]
                nst["n"]+=1;nst["sum"]+=got
                nst["full"]+=int(got==k)
                nst["hist"][got]+=1
            rs=family_test(states,target)
            for x in rs:
                v=family_stats[(x["Grup"],x["Boyut"])]
                v["n"]+=1;v["complete"]+=x["Tam"];v["sum"]+=x["İsabet"]
                v["any_full_at_target"]+=x["Hedefteki tüm tam aile"]
            if len(allfamily)<5000 and slot in (7,8,9,10,11,12):
                for x in rs:
                    if len(allfamily)>=5000:break
                    allfamily.append({
                        "Tarih":day,"Hedef":target["no"],
                        "Grup":x["Grup"],"Boyut":x["Boyut"],
                        "Aile":"-".join(f"{n:02d}" for n in x["Sayılar"]),
                        "İsabet":x["İsabet"],"Tam":x["Tam"]
                    })
            if len(examples)<details_limit and slot in (7,8,9,10,11,12):
                examples.append({
                    **out,
                    "Koltuk aileleri":" | ".join(
                        "-".join(f"{n:02d}" for n in primary[i:i+k])
                        for i,k in ((0,2),(2,3),(5,4),(9,5),(14,6))
                    )
                })
            rows.append(out)
            history.append(target)
    by_method=[]
    for (method,slot_group),s in sorted(method_stats.items()):
        n=s["n"]
        by_method.append({
            "Yöntem":method,"Kapsam":slot_group,
            "Hedef":n,"Toplam isabet":s["sum"],
            "Ortalama 20'de":round(s["sum"]/n,4),
            "Rastgele beklenti":5.0,"En fazla":s["max"],
            "20/20":s["twenty"],
            "Dağılım 0..20":"/".join(str(s["hist"][i]) for i in range(21))
        })
    byseat=[]
    for (ph,pool),(n,total,guessed,hits,abs_diff) in sorted(seat_ledger.items()):
        byseat.append({
            "Gün bölümü":ph,"Grup":pool,"Çekiliş":n,
            "Havuzda ortalama sayı":round(total/n,4),
            "Öngörülen koltuk":round(guessed/n,4),
            "Gerçek 20'de koltuk":round(hits/n,4),
            "Rastgele beklenen":round(.25*total/n,4),
            "Koltuk farkı":round((hits-guessed)/n,4),
            "Ortalama mutlak koltuk hatası":round(abs_diff/n,4)
        })
    bystate=[]
    for (ph,label),(n,hits) in sorted(stage_results.items()):
        bystate.append({
            "Gün bölümü":ph,"Sayı durumu":label,
            "Sayı-hedef gözlemi":n,"Sonraki çekilişte çıktı":hits,
            "Çıkış %":round(hits*100/n,3),
            "Adil beklenti %":25.0
        })
    familyrows=[]
    for (pool,k),v in sorted(family_stats.items()):
        familyrows.append({
            "Grup":pool,"Boyut":k,"Tek aile hedefi":v["n"],
            "Tam k/k":v["complete"],
            "Ortalama":round(v["sum"]/v["n"],4),
            "Rastgele beklenen":k/4,
            "Hedefte mevcut tüm bu gruptan tam aile (sonradan)":v["any_full_at_target"],
            "NOT":"Son sütun sonradan sayılır; tahmin başarısı değildir."
        })
    return {
        "meta":{"train_days":len(train),"holdout_days":len(holdout),
                "train_first":train[0] if train else "",
                "train_last":train[-1] if train else "",
                "test_first":holdout[0] if holdout else "",
                "test_last":holdout[-1] if holdout else "",
                "train_draws":model["train_draws"],"test_targets":len(rows),
                "note":"Targets are unordered sets. 'Seats' mean cold/warm/hot categories, not ordered physical ball slots."},
        "methods":by_method,"seats":byseat,
        "seat_exact":[{"Gün bölümü":ph,"Hedef":v[0],
                       "20 koltuk dağılımı tam tuttu":v[1],
                       "Rastgele beklenen tam":round(v[2],3),
                       "Tam oran %":round(100*v[1]/v[0],4)}
                      for ph,v in sorted(exact_seats.items())],
        "states":bystate,
        "family":familyrows,
        "nested":[{"Boyut":k,"Hedef":v["n"],
                   "Tam k/k":v["full"],
                   "Ortalama":round(v["sum"]/v["n"],4),
                   "Adil rastgele ortalama":k/4,
                   "Rastgele tam beklenen":round(v["n"]*confidence_hit(k),5),
                   "Dağılım 0..k":"/".join(str(v["hist"][i]) for i in range(k+1))}
                  for k,v in sorted(nested_stats.items())],
        "ledger":rows,
        "examples":examples,"family_examples":allfamily,
        "train_model":model
    }


def next_day_preview(day_draws,model,target_pos,target_no):
    """For one FUTURE slot, show all 80 identities and a family-integrated tower."""
    day_draws=make_ready(day_draws)
    if target_pos in {d["pos"] for d in day_draws}:return None
    previous=[d for d in day_draws if d["pos"]<target_pos]
    states=states_for_day(previous)
    seats=quotas(states,model,target_pos)
    priormap={d["pos"]:d for d in previous}
    prior12=complete_preceding_12(priormap,target_pos)
    proposals={}
    for method in ("Koltuk-model","Tepeyi azalt","Tepeyi koru"):
        proposals[method]=pick_20(states,model,target_pos,method)[0]
    if prior12 and hour_draw_index(target_pos) in (7,8,9,10,11,12):
        graph,_=forward_towers(prior12,target_no)
        proposals["V12 ağ-kule"]=tuple(graph["Ağ-kule"])
        proposals["Koltuk+V12"]=pick_20(
            states,model,target_pos,"Koltuk+V12",graph["Ağ-kule"])[0]
    main=proposals["Koltuk-model"]
    members=set(main)
    for st in states:
        st["P(çıkış) eğitim %"]=round(conditional_rate(model,target_pos,st)*100,3)
        st["Kuponda"]=st["n"] in members
    membership=[]
    for start,k in ((0,2),(2,3),(5,4),(9,5),(14,6)):
        nums=main[start:start+k]
        membership.append({"Boyut":k,"Aile":"-".join(f"{n:02d}" for n in nums),
                           "Aile tamamı soğuk":all(states[n-1]["pool"]=="Soğuk"
                                                  for n in nums),
                           "Aile tamamı sıcak":all(states[n-1]["pool"]=="Sıcak"
                                                  for n in nums)})
    stairs=[{"Boyut":k,"Aile":"-".join(f"{n:02d}" for n in main[:k])}
            for k in SIZES]
    return {"target":target_no,"pos":target_pos,"states":states,
            "seats":seats,"coupons":proposals,"groups":membership,"stairs":stairs}


def csv_export(rows):
    if not rows:return ""
    out=io.StringIO()
    w=csv.DictWriter(out,fieldnames=list(rows[0]),delimiter=";")
    w.writeheader()
    for r in rows:w.writerow({k:v for k,v in r.items() if k in rows[0]})
    return "\ufeff"+out.getvalue()
