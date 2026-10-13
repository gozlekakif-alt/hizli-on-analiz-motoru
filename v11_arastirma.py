# -*- coding: utf-8 -*-
"""V11: 6-10 family arrivals + the full 20-ball journey over trailing 12 draws.

No ML trained on test outcomes. Every prospective target uses exactly the
preceding 12 *consecutive draw positions*, never the target's own 20 numbers.
The registered candidate catalog was mined from the same history, so catalog
performance is retrospective/selection-biased; number-only strategies are
specified a priori and independent of that catalog.

Python stdlib only. Importable independently of Streamlit/V9/V10.
"""
import csv
import io
import math
import random
from collections import Counter, defaultdict
from datetime import datetime

SIZES=(6,7,8,9,10)
NUMBER_METHODS=("Sıcak-12","Son6 ivme","Soğuk-12","Birliktelik","Son çekiliş")
SIGNAL_METHOD="Aile öncü sinyali"
CHANCE_P={k:math.prod((20-i)/(80-i) for i in range(k)) for k in SIZES}


def read_draws(txt):
    items=[]
    bad=[]
    seen_no=set()
    seen_slot=set()
    for ln,line in enumerate(txt.splitlines(),1):
        pieces=line.strip().split(";")
        if len(pieces)!=3 or not pieces[0].isdigit():
            continue  # section headers are not corrupted draw records
        try:
            ident=int(pieces[0])
            dt=datetime.strptime(pieces[1],"%d.%m.%Y %H:%M")
            nums=tuple(sorted(int(n) for n in pieces[2].split(",")))
            if len(nums)!=20 or len(set(nums))!=20 or min(nums)<1 or max(nums)>80:
                raise ValueError("20 unique balls from 1..80 required")
            minute=dt.hour*60+dt.minute
            if 2<=minute<=62 and (minute-2)%5==0:
                pos=1+(minute-2)//5
            elif 422<=minute<=1437 and (minute-422)%5==0:
                pos=14+(minute-422)//5
            else:
                raise ValueError("draw clock not a valid scheduled slot")
            day=dt.date().isoformat()
            if ident in seen_no or (day,pos) in seen_slot:
                raise ValueError("duplicate draw number / calendar position")
            seen_no.add(ident)
            seen_slot.add((day,pos))
            items.append({"no":ident,"day":day,"pos":pos,
                          "dt":dt.isoformat(timespec="minutes"),
                          "nums":nums,"mask":sum(1<<(n-1) for n in nums)})
        except (ValueError,IndexError) as exc:
            bad.append((ln,str(exc)))
    items.sort(key=lambda r:(r["day"],r["pos"]))
    return items,bad


def read_families(data):
    output={}
    for r in csv.DictReader(io.StringIO(data.lstrip("\ufeff")),delimiter=";"):
        k=int(r.get("Boyut") or 0)
        if k not in SIZES:continue
        nums=tuple(int(x) for x in r["Aile"].split("-"))
        if len(nums)!=k or len(set(nums))!=k:
            raise ValueError("Invalid family: "+r["Aile"])
        label="-".join(f"{x:02d}" for x in nums)
        output[label]={"k":k,"nums":nums,"mask":sum(1<<(n-1) for n in nums)}
    return output


def hour_draw_index(pos):
    """7..12 of a *real 12-draw hour*. 01:02 special is excluded."""
    if 1<=pos<=12:
        return pos
    if pos==13:
        return 13
    if 14<=pos<=217:
        return 1+(pos-14)%12
    return 0


def moment_hour(pos):
    minute=2+5*(pos-1) if pos<=13 else 422+5*(pos-14)
    return minute//60


def complete_preceding_12(bypos,target_pos):
    """Require all 12 immediately previous draw positions in the same day."""
    if target_pos<=12:
        return None
    prior=[bypos.get(p) for p in range(target_pos-12,target_pos)]
    return prior if all(prior) else None


def number_window(prior):
    """Entire 12x20 ball panel; all derived without target's 20 numbers."""
    allnums=[d["nums"] for d in prior]
    n12=Counter(n for nums in allnums for n in nums)
    n6=Counter(n for nums in allnums[-6:] for n in nums)
    nfirst=Counter(n for nums in allnums[:6] for n in nums)
    pair=Counter()
    for nums in allnums[-6:]:
        for i,n in enumerate(nums):
            for m in nums[i+1:]:
                pair[(n,m)]+=1
    last=set(allnums[-1])
    before=set(allnums[-2])
    last3=set().union(*map(set,allnums[-3:]))
    fresh=len(last-before)
    union=len(set().union(*map(set,allnums)))
    # Distribution and full 20-ball transitions, not only candidate members.
    bands=tuple(sum(1 for n in allnums[-1] if a<=n<=a+19)
                for a in (1,21,41,61))
    last_consecutive=sum((x+1) in last for x in last if x<80)
    return {
        "count12":n12,"count6":n6,"first6":nfirst,"pairs":pair,
        "new20":fresh,"old20":20-fresh,"unique12":union,
        "hot":sum(n12[n]>=5 for n in range(1,81)),
        "cold":sum(n12[n]==0 for n in range(1,81)),
        "bands":bands,"last_consecutive":last_consecutive,
        "last":last,"last3":last3,
        "panel":allnums
    }


def constructed_tickets(context,k):
    """Five transparent, frozen number-based comparators + random separately.

    Every method must return k unique balls; all ties have a fixed rule.
    """
    nums=range(1,81)
    a=context["count12"];b=context["count6"];c=context["first6"]
    last=context["last"]
    hot=tuple(sorted(sorted(nums,key=lambda n:(-a[n],n))[:k]))
    cold=tuple(sorted(sorted(nums,key=lambda n:(a[n],n))[:k]))
    momentum=tuple(sorted(sorted(nums,key=lambda n:(-(b[n]-c[n]),-b[n],n))[:k]))
    last_repeat=tuple(sorted(sorted(last,key=lambda n:(-a[n],n))[:k]))
    # Pair cohesion in the previous SIX full-20 outcomes; never future data.
    chosen=[]
    scores=lambda n: (
        4*sum(context["pairs"][tuple(sorted((n,m)))] for m in chosen)
        +b[n]+0.25*a[n]
    )
    for i in range(k):
        eligible=[n for n in nums if n not in chosen]
        next_n=min(eligible,key=lambda n:(-scores(n),n))
        chosen.append(next_n)
    pair_based=tuple(sorted(chosen))
    return dict(zip(NUMBER_METHODS,(hot,momentum,cold,pair_based,last_repeat)))


def family_features(family,prior,context):
    """Family trajectory in all 12 prior 20-ball draws."""
    mask=family["mask"];k=family["k"]
    overlaps=[(mask&d["mask"]).bit_count() for d in prior]
    a=overlaps[:6];b=overlaps[6:]
    early=sum(a)/6;late=sum(b)/6
    peak=max(overlaps)
    recent_max=max(overlaps[-3:])
    turns=0
    moves=[x-y for x,y in zip(overlaps[1:],overlaps[:-1])]
    signs=[1 if x>0 else -1 for x in moves if x]
    for x,y in zip(signs,signs[1:]):
        if x!=y:turns+=1
    n12=context["count12"]
    family_hot=sum(n12[n]>=5 for n in family["nums"])
    family_cold=sum(n12[n]==0 for n in family["nums"])
    # Family-with-family co-movement and surrounding 20-ball context.
    cohesion=(sum(context["pairs"][(n,m) if n<m else (m,n)]
                 for i,n in enumerate(family["nums"])
                 for m in family["nums"][i+1:])
              if recent_max>=k-2 and family_hot>=max(2,k//2) else 0)
    return {
        "overlaps":overlaps,"max12":peak,"max3":recent_max,
        "early":early,"late":late,"change":late-early,
        "turns":turns,"hot_members":family_hot,
        "cold_members":family_cold,"cohesion":cohesion,
        "full_prior":peak==k,
        "last":overlaps[-1]
    }


def arrival_category(k,feat):
    """Exclusive retrospective labels computed from PRE-target window."""
    peak=feat["max12"]
    if feat["full_prior"]:
        return "Tam tekrar"
    if peak<=k//2:
        return "Sessiz"
    if feat["max3"]>=k-1 and feat["change"]>=0.65:
        return "Tamamlayarak"
    if feat["change"]>=0.85 and max(feat["overlaps"][6:])>=k-2:
        return "Yükselerek"
    if feat["turns"]>=4 and max(feat["overlaps"][6:])>=k-2:
        return "Dalgalanarak"
    return "Diğer / karma"


def prospective_signal(family,feat,past_hour_days=0):
    """Frozen pre-target signals. More evidence != validated prediction power."""
    k=family["k"]
    x=feat
    routes=[]
    if x["max3"]>=k-1:routes.append("Tam sınıra yakın")
    if x["change"]>=0.85 and max(x["overlaps"][6:])>=k-2:
        routes.append("Artan tamamlama")
    if x["turns"]>=4 and max(x["overlaps"][6:])>=k-2:
        routes.append("Dalgalı geliş")
    if x["full_prior"]:routes.append("Tekrarlayan aile")
    if past_hour_days>=2 and x["max3"]>=max(2,k-3):
        routes.append("Geçmiş saat desteği")
    if x["max12"]<=k//2 and past_hour_days>=2:
        routes.append("Sessiz geçmiş saat")
    if x["hot_members"]>=max(2,k//2) and x["max3"]>=k-2 and x["cohesion"]>=k:
        routes.append("20 sayı birlikteliği")
    if not routes:
        return None
    # Score is precommitted heuristic, NOT a learned probability.
    weight={
        "Tam sınıra yakın":40,"Artan tamamlama":30,
        "Dalgalı geliş":23,"Tekrarlayan aile":22,
        "Geçmiş saat desteği":18,"Sessiz geçmiş saat":10,
        "20 sayı birlikteliği":15
    }
    score=sum(weight[r] for r in routes)
    score+=min(12,past_hour_days*2)
    score+=min(8,feat["cohesion"]/6)
    return {"routes":routes,"score":score}


def _accumulate(summary,key,k,numbers,target,extra=None):
    stats=summary.setdefault(key,{"boyut":k,"deneme":0,"tam":0,
                        "toplam_isabet":0,"dagilim":Counter(),
                        "beklenen_tam":0.0,"beklenen_ortalama":0.0})
    got=len(set(numbers)&set(target))
    stats["deneme"]+=1
    stats["tam"]+=int(got==k)
    stats["toplam_isabet"]+=got
    stats["dagilim"][got]+=1
    stats["beklenen_tam"]+=CHANCE_P[k]
    stats["beklenen_ortalama"]+=k/4
    return got


def _stats_rows(acc):
    ret=[]
    for (phase,k,method),v in sorted(acc.items()):
        count=v["deneme"]
        ret.append({"Dönem":phase,"Boyut":k,"Yöntem":method,
                    "Hedef":count,"Tam isabet":v["tam"],
                    "Tam / hedef %":round(100*v["tam"]/count,5) if count else 0,
                    "Ortalama isabet":round(v["toplam_isabet"]/count,4) if count else 0,
                    "Rastgele beklenen ortalama":k/4,
                    "Rastgele beklenen tam":round(v["beklenen_tam"],5),
                    "İsabet dağılımı":"/".join(str(v["dagilim"][i]) for i in range(k+1))})
    return ret


def run_study(draws,families,train_days=36,complete_days_only=True):
    """Full chronological replay: 12 prior actual 20-number results per target.

    Analyses pre-set methods, future-slot validation (hour slots 7..12),
    catalog-family retrospective origins, and number-only controls.
    """
    daydraws=defaultdict(list)
    for d in draws:
        if "mask" not in d:
            d={**d,"mask":sum(1 << (int(n)-1) for n in d["nums"])}
        daydraws[d["day"]].append(d)
    days=sorted(daydraws)
    if not days:
        return {"meta":{},"methods":[],"arrival":[],"examples":[],"hour_summary":[]}
    if complete_days_only:
        # Exclude the final observed date, if fewer than 217 draws were entered.
        final=days[-1]
        if len(daydraws[final])<217:
            days=days[:-1]
    families={label:f for label,f in families.items() if f["k"] in SIZES}
    by_size=defaultdict(list)
    for label,f in families.items():
        by_size[f["k"]].append((label,f))
    for k in SIZES:by_size[k].sort()
    support=defaultdict(lambda:defaultdict(set))
    acc={}
    slot_acc={}
    target_ledger=[]
    arrivals=Counter()
    arrival_examples=[]
    signal_examples=[]
    hours=defaultdict(lambda:{"hedef":0,"yeni20":0,"benzersiz12":0,
                               "sıcak":0,"soğuk":0,"sabit20":0})
    by_day_count=Counter()
    scanned=0
    for day_index,day in enumerate(days):
        records=sorted(daydraws[day],key=lambda d:d["pos"])
        bypos={r["pos"]:r for r in records}
        # Split by CALENDAR day before inspecting any test-day results.
        phase="İlk dönem" if day_index<train_days else "Sonraki dönem"
        to_add=defaultdict(set)
        for actual in records:
            phase_slot=hour_draw_index(actual["pos"])
            if phase_slot<7 or phase_slot>12:
                # 01:02 special and first-half slots never represent a target
                # in this fixed, six-target-per-hour experiment.
                continue
            prior=complete_preceding_12(bypos,actual["pos"])
            if prior is None:continue
            target=actual["nums"]
            ctx=number_window(prior)
            scanned+=1
            by_day_count[day]+=1
            hr=moment_hour(actual["pos"])
            h=hours[(phase,hr)]
            h["hedef"]+=1
            h["yeni20"]+=ctx["new20"]
            h["sabit20"]+=ctx["old20"]
            h["benzersiz12"]+=ctx["unique12"]
            h["sıcak"]+=ctx["hot"]
            h["soğuk"]+=ctx["cold"]
            for k in SIZES:
                ledger={"Tarih":day,"Hedef":actual["no"],
                        "Saat":actual["dt"][11:16],
                        "Saat içi çekiliş":phase_slot,
                        "Boyut":k,"Dönem":phase,
                        "Son12 benzersiz":ctx["unique12"],
                        "Son çekilişte yeni":ctx["new20"],
                        "Sıcak sayı":ctx["hot"],"Soğuk sayı":ctx["cold"],
                        "Aile sinyali":"","Aile hedefi":"",
                        "Aile sinyal koşulları":""}
                tickets=constructed_tickets(ctx,k)
                # matched random coupon with no outcome access: per-target
                # reproducible seed, no use of Python salted hash().
                seed=actual["no"]*100+k*13
                rng=random.Random(seed)
                random_ticket=tuple(sorted(rng.sample(range(1,81),k)))
                match=_accumulate(acc,(phase,k,"Rastgele kontrol"),k,
                                  random_ticket,target)
                _accumulate(slot_acc,(phase,k,"Rastgele kontrol",phase_slot),
                            k,random_ticket,target)
                ledger["Rastgele"]=f"{match}/{k}"
                for method,coupon in tickets.items():
                    match=_accumulate(acc,(phase,k,method),k,coupon,target)
                    _accumulate(slot_acc,(phase,k,method,phase_slot),
                                k,coupon,target)
                    ledger[method]=f"{match}/{k}"
                candidates=[]
                for label,f in by_size[k]:
                    feat=family_features(f,prior,ctx)
                    # Retrospective arrivals and pathway labels.
                    if (f["mask"]&actual["mask"])==f["mask"]:
                        category=arrival_category(k,feat)
                        arrivals[(phase,k,category)]+=1
                        if len(arrival_examples)<100:
                            arrival_examples.append({
                                "Gün":day,"Çekiliş":actual["no"],
                                "Saat":actual["dt"][11:16],
                                "Aile":label,"Boyut":k,
                                "Geliş yolu":category,
                                "Son12":"/".join(map(str,feat["overlaps"])),
                                "Yeni 20 sayı":ctx["new20"],
                                "12 çekilişte farklı sayı":ctx["unique12"]})
                    historic_hour=len(support[label][hr])
                    sig=prospective_signal(f,feat,historic_hour)
                    if sig:
                        candidates.append((sig["score"],label,f,sig,feat,historic_hour))
                # One frozen top-ranked catalog proposal per size and target.
                # All failed candidates remain in report denominator.
                if candidates:
                    candidates.sort(key=lambda x:(-x[0],x[1]))
                    score,label,f,sig,feat,prior_days=candidates[0]
                    matched=_accumulate(acc,(phase,k,SIGNAL_METHOD),k,
                                        f["nums"],target)
                    _accumulate(slot_acc,(phase,k,SIGNAL_METHOD,phase_slot),
                                k,f["nums"],target)
                    ledger["Aile sinyali"]=f"{matched}/{k}"
                    ledger["Aile hedefi"]=label
                    ledger["Aile sinyal koşulları"]=", ".join(sig["routes"])
                    if len(signal_examples)<180:
                        signal_examples.append({
                            "Gün":day,"Hedef":actual["no"],
                            "Saat":actual["dt"][11:16],
                            "Boyut":k,"Aile":label,
                            "Sinyal":", ".join(sig["routes"]),
                            "Puan":round(score,2),
                            "Saat destek günü":prior_days,
                            "Son12":"/".join(map(str,feat["overlaps"])),
                            "İsabet":f"{matched}/{k}",
                            "Tam":matched==k})
                target_ledger.append(ledger)
        # Only now is this day available as historical support for NEXT day.
        for r in records:
            for label,f in families.items():
                if r["mask"]&f["mask"]==f["mask"]:
                    to_add[(label,moment_hour(r["pos"]))].add(day)
        for (label,hr),seen in to_add.items():
            support[label][hr].update(seen)
    arrival_rows=[]
    for k in SIZES:
        for phase in ("İlk dönem","Sonraki dönem"):
            for category in ("Sessiz","Tamamlayarak","Yükselerek",
                             "Dalgalanarak","Tam tekrar","Diğer / karma"):
                count=arrivals[(phase,k,category)]
                arrival_rows.append({"Dönem":phase,"Boyut":k,
                                     "Geliş yolu":category,"Tam görünüş":count})
    hour_rows=[]
    for (phase,hr),v in sorted(hours.items()):
        n=v["hedef"]
        hour_rows.append({"Dönem":phase,"Saat":f"{hr:02d}",
                          "Hedef":n,
                          "Önceki 20'den yeni":round(v["yeni20"]/n,2),
                          "Önceki 20'den tekrar":round(v["sabit20"]/n,2),
                          "12 çekilişte farklı sayı":round(v["benzersiz12"]/n,2),
                          "12'de sıcak sayı (5+)":round(v["sıcak"]/n,2),
                          "12'de soğuk sayı (0)":round(v["soğuk"]/n,2)})
    return {
        "meta":{"tarih_sayısı":len(days),"ilk_gün":days[0],
                "son_gün":days[-1],"çekiliş_sayısı":sum(len(daydraws[d]) for d in days),
                "hedef_sayısı":scanned,
                "aile_sayısı":{k:len(by_size[k]) for k in SIZES},
                "dönem_ayrımı":train_days,"kayıp_ara_saat":dict(by_day_count)},
        "methods":_stats_rows(acc),
        "slots":[{**{"Saat içi çekiliş":slot},**{
            a:b for a,b in _stats_rows({(phase,k,method):v})[0].items()}}
                 for (phase,k,method,slot),v in sorted(slot_acc.items())],
        "target_ledger":target_ledger,
        "arrival":arrival_rows,
        "examples":arrival_examples,
        "signals":signal_examples,
        "hour_summary":hour_rows
    }


def live_preview(day_draws,families,next_pos,prior_hour_days=None):
    """One prospective 7..12 slot only, from the exact previous 12 draw records."""
    day_draws=[{**d,"mask":d.get("mask",sum(1<<(int(n)-1) for n in d["nums"]))}
               for d in day_draws]
    bypos={d["pos"]:d for d in day_draws}
    if next_pos in bypos or hour_draw_index(next_pos) not in range(7,13):
        return []
    prior=complete_preceding_12(bypos,next_pos)
    if prior is None:
        return []
    ctx=number_window(prior)
    prehour=moment_hour(next_pos)
    prior_hour_days=prior_hour_days or {}
    ret=[]
    for k in SIZES:
        proposals=constructed_tickets(ctx,k)
        for method,coupon in proposals.items():
            ret.append({"Boyut":k,"Kaynak":method,"Aile":"-".join(f"{n:02d}" for n in coupon),
                        "Hedef sıra":next_pos,"Saat destek gün":None,
                        "Kupon uygun":False,
                        "Açıklama":"Sayı akışı; deneyseldir"})
        candidates=[]
        for label,f in families.items():
            if f["k"]!=k:continue
            feat=family_features(f,prior,ctx)
            hour_count=int(prior_hour_days.get(label,{}).get(prehour,0))
            sig=prospective_signal(f,feat,hour_count)
            if sig:candidates.append((sig["score"],label,sig,hour_count))
        if candidates:
            candidates.sort(key=lambda x:(-x[0],x[1]))
            score,label,sig,daycount=candidates[0]
            ret.append({"Boyut":k,"Kaynak":SIGNAL_METHOD,"Aile":label,
                        "Hedef sıra":next_pos,"Saat destek gün":daycount,
                        "Kupon uygun":False,
                        "Açıklama":", ".join(sig["routes"])})
    return ret


def csv_export(rows):
    if not rows:return ""
    out=io.StringIO()
    writer=csv.DictWriter(out,fieldnames=list(rows[0]),delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    return "\ufeff"+out.getvalue()


def summary_text(result):
    m=result["meta"]
    lines=[f"V11 | {m['ilk_gün']} — {m['son_gün']}",
           f"Çekiliş: {m['çekiliş_sayısı']} | Test hedefi: {m['hedef_sayısı']}",
           "Aile havuzu: "+", ".join(f"{k}'li {v}" for k,v in m["aile_sayısı"].items()),
           "KURAL: yalnız hedef öncesindeki 12 gerçek çekiliş ve tüm 20 sayı.",
           "İLK dönem geliştirme incelemesi; SONRAKİ dönem geriye dönük ileri zaman testi.",
           "UYARI: sabit aile havuzu geçmiş verilere bakılarak seçildi; kör test değildir."]
    for k in SIZES:
        lines.append(f"\n{k}'LI AİLELER:")
        a=[r for r in result["arrival"] if r["Boyut"]==k and r["Dönem"]=="Sonraki dönem"]
        lines.append("  Geliş yolları, son dönem: "+", ".join(f'{r["Geliş yolu"]} {r["Tam görünüş"]}' for r in a))
        t=[r for r in result["methods"] if r["Boyut"]==k and r["Dönem"]=="Sonraki dönem"]
        for r in t:
            lines.append(f'  {r["Yöntem"]}: hedef {r["Hedef"]}; tam {r["Tam isabet"]}; '
                         f'ortalama {r["Ortalama isabet"]:.3f}; '
                         f'rastgele ortalama {k/4:.2f}; '
                         f'beklenen tam {r["Rastgele beklenen tam"]:.4f}')
    return "\n".join(lines)+"\n"
