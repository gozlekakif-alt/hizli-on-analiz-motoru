# -*- coding: utf-8 -*-
"""V10 — Six-number SAME-FAMILY SAME-DRAW-GAP repeat engine.

Strict chronology:
    prior day A family FIRST hit twice at draw gap G (historical evidence)
    on day B same family hits twice consecutively with gap G
    -> *prospectively* target third full appearance G draws later.

Every target is logged whether it completes or not. No next-draw guarantee.
Supports only six-number families in the supplied, fixed candidate catalog.
"""
from collections import defaultdict
from datetime import datetime


def six_family_map(families):
    """Explicit six-number candidates; does not imply exhaustive six-subsets."""
    return {label: f for label,f in families.items() if f["k"] == 6}


def gap_targets_today(hits, families, profiles, day, current, moment_fn,
                      observed_positions=(), minimum_days=1,
                      minimum_hour_days=2):
    """Live targets created by already-observed consecutive full appearances.

    Historical gap and target-hour support are derived from profiles trained
    strictly before 'day'. No current-day outcomes form evidence.
    """
    results={}
    observed_positions=set(observed_positions)
    for label,f in six_family_map(families).items():
        recs=sorted((r for r in hits.get(label,())
                     if datetime.fromisoformat(r["dt"])<=current),
                    key=lambda r:r["pos"])
        if len(recs)<2:
            continue
        prof=profiles.get(label,{})
        for a,b in [(recs[0],recs[1])]:
            gap=b["pos"]-a["pos"]
            if gap<1:
                continue
            support=int(prof.get("first",{}).get(gap,0))
            if support<minimum_days:
                continue
            pos=b["pos"]+gap
            if pos>217 or pos in observed_positions:
                continue
            target=moment_fn(day,pos)
            if target<=current:
                continue
            hour_days=int(prof.get("hour_days",{}).get(target.hour,0))
            eligible=(support>=2 and hour_days>=minimum_hour_days)
            key=(label,pos)
            row={
                "Aile":label,"Boyut":6,"Aralık":gap,
                "Birinci":f"#{a['no']} {a['dt'][11:16]}",
                "İkinci":f"#{b['no']} {b['dt'][11:16]}",
                "Tetik no":b["no"],"Hedef tarih":day,
                "Hedef sıra":pos,"Hedef saat":target.strftime("%H:%M"),
                "Tahmini no":b["no"]+gap,
                "Geçmiş ritim gün":support,
                "Hedef saat destek":hour_days,
                "Durum":"🔥 Kupon koşulu" if eligible else "🟡 İzleme",
                "Kupon uygun":eligible,
                "moment":target.isoformat(timespec="minutes")
            }
            previous=results.get(key)
            if previous is None or (support,hour_days) > (
                    previous["Geçmiş ritim gün"],previous["Hedef saat destek"]):
                results[key]=row
    return sorted(results.values(),
                  key=lambda r:(not r["Kupon uygun"],r["Hedef sıra"],
                                -r["Geçmiş ritim gün"],r["Aile"]))


def walkforward_six_gap(draws, families, moment_fn, minimum_days=1,
                        minimum_hour_days=2):
    """Chronological daily replay: only earlier days teach gap rules.

    Earlier training and current-day triggers BOTH use the FIRST TWO complete
    appearances of the same family, never arbitrary later pairs. Results are evaluated only after that day's
    triggers have been frozen. Hour gate is reported independently.
    """
    fs=six_family_map(families)
    byday=defaultdict(list)
    for d in draws:
        byday[d["day"]].append(d)
    supported=defaultdict(lambda:defaultdict(set))
    earlier_hours=defaultdict(lambda:defaultdict(set))
    results=[]
    for day in sorted(byday):
        rs=sorted(byday[day],key=lambda r:r["pos"])
        bypos={r["pos"]:r for r in rs}
        masks=[sum(1 << (n-1) for n in d["nums"]) for d in rs]
        today_found={}
        # all families observed in this test day; no evaluation leaks into
        # training since historical support changes only at the end of day.
        for label,fam in fs.items():
            matches=[d for d,m in zip(rs,masks) if (m&fam["mask"])==fam["mask"]]
            if not matches:
                continue
            today_found[label]=matches
            if len(matches)<2:
                continue
            for a,b in [(matches[0],matches[1])]:
                gap=b["pos"]-a["pos"]
                support=len(supported[label][gap])
                if support<minimum_days or b["pos"]+gap>217:
                    continue
                pos=b["pos"]+gap
                target=moment_fn(day,pos)
                hour_days=len(earlier_hours[label][target.hour])
                eligible=(support>=2 and hour_days>=minimum_hour_days)
                actual=bypos.get(pos)
                matched=(sorted(set(fam["nums"]) & set(actual["nums"]))
                         if actual else [])
                record={
                    "Tarih":day,"Aile":label,"Aralık":gap,
                    "Birinci":a["no"],"İkinci":b["no"],
                    "Hedef sıra":pos,"Hedef saat":target.strftime("%H:%M"),
                    "Hedef çekiliş":actual["no"] if actual else "",
                    "Destek gün":support,"Saat destek":hour_days,
                    "Kupon koşulu":eligible,
                    "Sonuç":("Kayıt yok" if not actual else
                             "6/6" if len(matched)==6 else f"{len(matched)}/6"),
                    "İsabet":len(matched) if actual else None,
                    "Tutan":"-".join(map(str,matched)) if actual else "",
                }
                results.append(record)
        # Update after evaluating entire day (never use same-day future).
        for label,hits in today_found.items():
            for r in hits:
                earlier_hours[label][moment_fn(day,r["pos"]).hour].add(day)
            if len(hits)>=2:
                supported[label][hits[1]["pos"]-hits[0]["pos"]].add(day)
    # De-duplicate identical family+target, preferring stronger evidence.
    # Different target positions are distinct forecasts.
    unique={}
    for row in results:
        key=(row["Tarih"],row["Aile"],row["Hedef sıra"])
        old=unique.get(key)
        if old is None or (row["Destek gün"],row["Saat destek"]) > (
                old["Destek gün"],old["Saat destek"]):
            unique[key]=row
    return sorted(unique.values(),
                  key=lambda r:(r["Tarih"],r["Hedef sıra"],r["Aile"]))


def six_gap_summary(rows):
    """Do not mistake unrecorded target results for false alarms."""
    complete=[r for r in rows if r["İsabet"] is not None]
    wait=[r for r in rows if r["İsabet"] is None]
    distribution={f"{k}/6":sum(r["İsabet"]==k for r in complete)
                  for k in range(7)}
    return {
        "Tahmin":len(rows),"Sonuçlanan":len(complete),
        "Bekleyen":len(wait),"6/6":distribution["6/6"],
        "Tam olmayan":len(complete)-distribution["6/6"],
        "Kupon koşulu geçen":sum(bool(r["Kupon koşulu"]) for r in rows),
        "Dağılım":distribution,
    }
