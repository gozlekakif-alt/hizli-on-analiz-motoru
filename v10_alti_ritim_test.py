# -*- coding: utf-8 -*-
"""Tests: V10 six-family same-draw-gap across-day motor, stdlib only."""
import csv
import io
import re
from datetime import datetime,timedelta
from collections import defaultdict
from v10_alti_ritim import gap_targets_today,walkforward_six_gap,six_gap_summary


def moment(day,pos):
    if not 1<=pos<=217: raise ValueError("bad slot")
    mins=2+5*(pos-1) if pos<=13 else 422+5*(pos-14)
    return datetime.fromisoformat(day)+timedelta(minutes=mins)


def fake(day,pos,ident,hit=True):
    nums=(list(range(1,21)) if hit else list(range(30,50)))
    return {"day":day,"pos":pos,"no":ident,"dt":moment(day,pos).isoformat(timespec="minutes"),
            "nums":nums}


family="01-02-03-04-05-06"
meta={family:{"k":6,"mask":sum(1<<(n-1) for n in range(1,7)),
              "nums":tuple(range(1,7))}}

# Prior-day exact gap support from two independent days, each containing two
# full family appearances. One target-day pair should create target at +3.
training=[
    fake("2026-10-08",14,8001),fake("2026-10-08",17,8002),
    fake("2026-10-09",14,9001),fake("2026-10-09",17,9002),
]
today=[
    fake("2026-10-10",14,10001),fake("2026-10-10",17,10002),
    fake("2026-10-10",20,10003), # the target result is intentionally hidden for live
]
profile={family:{"first":{3:2},"hour_days":{7:2},"days":["2026-10-08","2026-10-09"]}}
# All three full-family appearances occur in 07:xx; target pos20 = 07:32.
# Target-hour support is from two earlier days, never from future results.
profile[family]["hour_days"][7]=2
hit_so_far={family:today[:2]}
live=gap_targets_today(hit_so_far,meta,profile,"2026-10-10",
                       moment("2026-10-10",17),moment,
                       observed_positions={14,17},
                       minimum_days=2,minimum_hour_days=2)
assert len(live)==1,live
x=live[0]
assert x["Aralık"]==3 and x["Hedef sıra"]==20 and x["Hedef saat"]=="07:32",x
assert x["Kupon uygun"] and x["Durum"].startswith("🔥")
assert not gap_targets_today(hit_so_far,meta,profile,"2026-10-10",
       moment("2026-10-10",20),moment,{14,17},2,2)
assert not gap_targets_today(hit_so_far,meta,profile,"2026-10-10",
       moment("2026-10-10",17),moment,{14,17,20},2,2)
assert not gap_targets_today(hit_so_far,meta,profile,"2026-10-10",
       moment("2026-10-10",17),moment,{14,17},3,2)
weak={family:{"first":{3:1},"hour_days":{7:1}}}
watch=gap_targets_today(hit_so_far,meta,weak,"2026-10-10",
                        moment("2026-10-10",17),moment,{14,17},1,2)
assert len(watch)==1 and not watch[0]["Kupon uygun"]
assert watch[0]["Durum"].startswith("🟡")

# Walk-forward: third full occurrence is scored AFTER trigger time, not used
# as historical evidence on its date. A missed target remains in the denominator.
h=fake("2026-10-10",20,10003,True)
test_draws=training+today[:2]+[h]
warmup=walkforward_six_gap(training,meta,moment,1)
assert len(warmup)==1 and warmup[0]["İsabet"] is None,warmup
good=walkforward_six_gap(test_draws,meta,moment,2)
assert len(good)==1 and good[0]["İsabet"]==6 and good[0]["Sonuç"]=="6/6",good
assert six_gap_summary(good)["6/6"]==1
assert good[0]["Kupon koşulu"]
miss=walkforward_six_gap(training+today[:2]+[fake("2026-10-10",20,10003,False)],meta,moment,2)
assert len(miss)==1 and miss[0]["İsabet"]==0 and six_gap_summary(miss)["Tam olmayan"]==1,miss
# A single prior day supports observation but not a ready coupon.
one_day=walkforward_six_gap(training[:2]+today,meta,moment,1)
assert len(one_day)==1 and not one_day[0]["Kupon koşulu"]
assert not walkforward_six_gap(training[:2]+today,meta,moment,2)
# Identical support from two pairs in same day counts as ONE day, not two.
repeated_day=training[:2]+[fake("2026-10-08",20,8003)]+today
assert not walkforward_six_gap(repeated_day,meta,moment,2)

# Real corpus: check all registered 6-families and report the outcome without
# inferring a fixed, future-proof result count.
with open("v10_aileler.csv",encoding="utf-8-sig") as inp:
    fams={}
    for row in csv.DictReader(inp,delimiter=";"):
        if int(row["Boyut"])!=6:continue
        label=row["Aile"]
        ns=[int(n) for n in label.split("-")]
        fams[label]={"k":6,"nums":tuple(ns),
                     "mask":sum(1<<(n-1) for n in ns)}
assert len(fams)==198,len(fams)
draws=[]
with open("veri.txt",encoding="utf-8-sig") as inp:
    for line in inp:
        parts=line.strip().split(";")
        if len(parts)!=3 or not parts[0].isdigit():continue
        match=re.fullmatch(r"(\d\d)\.(\d\d)\.(\d{4}) (\d\d):(\d\d)",parts[1])
        if not match:continue
        nums=[int(n) for n in parts[2].split(",") if n]
        if len(nums)!=20 or len(set(nums))!=20: continue
        day=f"{match[3]}-{match[2]}-{match[1]}"
        dt=datetime.strptime(parts[1],"%d.%m.%Y %H:%M")
        minutes=dt.hour*60+dt.minute
        pos=(1+(minutes-2)//5 if minutes<=62 else
             14+(minutes-422)//5)
        if pos<1 or pos>217 or moment(day,pos)!=dt: continue
        draws.append({"no":int(parts[0]),"day":day,"dt":dt.isoformat(timespec="minutes"),
                      "pos":pos,"nums":nums})
draws.sort(key=lambda x:(x["dt"],x["no"]))
assert len(draws)>15000,len(draws)

test_1=walkforward_six_gap(draws,fams,moment,minimum_days=1)
test_2=walkforward_six_gap(draws,fams,moment,minimum_days=2)
one=six_gap_summary(test_1)
two=six_gap_summary(test_2)
assert one["Tahmin"]>=two["Tahmin"]
assert all(r["Tarih"]>=min(x["day"] for x in draws) for r in test_1)
assert all(r["Hedef sıra"]>0 and r["Hedef sıra"]<=217 for r in test_1)
assert len({(r["Tarih"],r["Aile"],r["Hedef sıra"]) for r in test_1})==len(test_1)
assert all(r["İsabet"] is None or 0<=r["İsabet"]<=6 for r in test_1)
print("PASS: V10 6-family gap motor future targets, earlier-day support and no-lookahead")
print("REAL DATA:",len(draws),"draws;",len(fams),"6-family candidates")
print("ONE PRIOR-DAY SUPPORT:",one)
print("TWO PRIOR-DAY SUPPORT:",two)
