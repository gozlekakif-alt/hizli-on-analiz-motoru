# -*- coding: utf-8 -*-
"""V10 Geliyorum early warning (stdlib only, no look-ahead).

These are descriptive experimental alerts, NOT proven predictions.
The exact next registered draw is the sole target. No target is backdated.
Only prior-day family profiles may be supplied for hour and rhythm support.
"""

from datetime import datetime
from collections import Counter

# Require a substantial partial overlap; no ticket from weak fragments.
MIN_PARTIAL = {5: 4, 6: 4, 7: 5, 8: 6, 9: 6, 10: 7}


def upcoming_alerts(day_draws, families, profiles, target_day, now, moment_fn,
                    minimum_hour_days=2, day_rhythm_families=None,
                    limit=150):
    """Scan every family before its next possible completion.

    Use solely already known draws, with one exact immediately following
    unrecorded draw as the target. Profiles MUST be prior-day-only.
    """
    day_rhythm_families=day_rhythm_families or set()
    observed=sorted(
        (d for d in day_draws if datetime.fromisoformat(d["dt"])<=now),
        key=lambda d:d["pos"]
    )
    if not observed:
        return [], {"reason": "no_draw", "scanned":len(families),
                    "partial":0, "hour_supported":0, "coupon_ready":0,
                    "target":None, "sizes":{}}
    last=observed[-1]
    target_pos=last["pos"]+1
    if target_pos>217:
        return [], {"reason":"end_of_day","scanned":len(families),
                    "partial":0,"hour_supported":0,"coupon_ready":0,
                    "target":None,"sizes":{}}
    target_dt=moment_fn(target_day,target_pos)
    observed_pos={d["pos"] for d in day_draws}
    if target_dt<=now or target_pos in observed_pos:
        return [], {"reason":"stale","scanned":len(families),
                    "partial":0,"hour_supported":0,"coupon_ready":0,
                    "target":target_pos,"sizes":{}}
    recent=observed[-3:]
    recent_masks=[
        sum(1 << (n-1) for n in d["nums"]) for d in recent
    ]
    # Only evaluate today's full history for families that pass the
    # partial-overlap filter; avoid quadratic all-family scan on each rerun.
    earlier_masks=[
        sum(1 << (n-1) for n in d["nums"]) for d in observed[:-3]
    ]

    rows=[]
    stats={"reason":"ok","scanned":len(families),"partial":0,
           "hour_supported":0,"coupon_ready":0,
           "target":target_pos,"sizes":{}}
    target_hour=target_dt.hour
    per_size={}
    for label,fam in families.items():
        k=fam["k"]
        vals=[(mask & fam["mask"]).bit_count() for mask in recent_masks]
        best=max(vals,default=0)
        threshold=MIN_PARTIAL.get(k,k-1)
        if best<threshold:
            continue
        stats["partial"]+=1
        slot=per_size.setdefault(k,{"partial":0,"supported":0,"coupon_ready":0})
        slot["partial"]+=1
        data=profiles.get(label,{})
        hour_days=int(data.get("hour_days",{}).get(target_hour,0))
        history_days=len(data.get("days",[]))
        if hour_days>=minimum_hour_days:
            stats["hour_supported"]+=1
            slot["supported"]+=1
        peak_recent=sum(v>=threshold for v in vals)
        same_day_rhythm=label in day_rhythm_families
        # Yellow warnings are never treated as ticket-worthy.
        ready=(hour_days>=minimum_hour_days and
               history_days>=minimum_hour_days and
               (len(vals)==1 or max(vals[-2:])>=threshold))
        if ready:
            stats["coupon_ready"]+=1
            slot["coupon_ready"]+=1
        tier=("🔥🔥 Çoklu koşul" if ready and
              ((hour_days>=3 and peak_recent>=2) or same_day_rhythm)
              else "🔥 Geliyorum" if ready else "🟡 Erken uyarı")
        evidence=max(range(len(vals)),key=lambda i:vals[i])
        source=recent[evidence]
        rows.append({
            "Aile":label,"Boyut":k,"Durum":tier,
            "Kısmi":f"{best}/{k}",
            "Son üç":"/".join(str(v) for v in vals),
            "Geçmiş saat günü":hour_days,
            "Geçmiş aile günü":history_days,
            "Gün ritmi": "🔥" if same_day_rhythm else "—",
            "Bugün tam görünüş":any((m & fam["mask"])==fam["mask"]
                                     for m in recent_masks+earlier_masks),
            "Hedef sıra":target_pos, "Hedef saat":target_dt.strftime("%H:%M"),
            "Hedef no":last["no"]+1,
            "İşaret çekilişi":source["no"],
            "Kupon uygun":ready,
            "Hedef tarih":target_day,
            "moment":target_dt.isoformat(timespec="minutes"),
        })
    rows.sort(key=lambda r:(not r["Kupon uygun"],
                            -int(r["Durum"].startswith("🔥🔥")),
                            -r["Geçmiş saat günü"],
                            -int(r["Kısmi"].split("/")[0]),
                            -r["Boyut"],r["Aile"]))
    stats["sizes"]=per_size
    # cap only display, NEVER metrics or test counts
    return rows[:limit],stats


def replay_warning_day(day_draws, families, profiles, target_day, moment_fn,
                       minimum_hour_days=2, day_rhythm_families=None):
    """Sequential intraday replay; a candidate is scored on the NEXT draw.

    The profiles must use strictly earlier days. No current-day future result
    or response is used in constructing the warning.
    """
    ordered=sorted(day_draws,key=lambda x:x["pos"])
    actual={d["pos"]:d for d in ordered}
    rows=[]
    for i,trigger in enumerate(ordered):
        if i+1>=len(ordered):
            break
        future=ordered[i+1]
        if future["pos"]!=trigger["pos"]+1:
            continue
        # The algorithm receives only the prefix of the selected day.
        matches,info=upcoming_alerts(
            ordered[:i+1],families,profiles,target_day,
            datetime.fromisoformat(trigger["dt"]),moment_fn,
            minimum_hour_days,day_rhythm_families,limit=len(families)
        )
        for m in matches:
            if not m["Kupon uygun"]:
                continue
            fam=families[m["Aile"]]
            correct=sorted(set(fam["nums"])&set(future["nums"]))
            rows.append({
                "Hedef sıra":future["pos"],"Hedef saat":future["dt"][11:16],
                "Çekiliş":future["no"],"Aile":m["Aile"],"Boyut":fam["k"],
                "Ön sinyal":m["Durum"],"Kısmi":m["Kısmi"],
                "Saat destek gün":m["Geçmiş saat günü"],
                "İsabet":f"{len(correct)}/{fam['k']}",
                "Tam":len(correct)==fam["k"],
                "Tutan": "-".join(map(str,correct)),
            })
    return rows
