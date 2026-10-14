# -*- coding: utf-8 -*-
"""V29 tests: heat-streak cutoff identity, no future data leakage, 10/20 quotas."""
import math
import random
from collections import Counter
from v21_aile_yasam_dongusu import clock
from v29_sicaklik_kalis_hedef import (
    BALLS,generate_rows,state_features,train_rates,probability_scores,
    one_hour_brier,rank_tickets,clip_hits,bucket_duration,trend_label,
    MODELS,phase_for,validation_choose,make_score_records
)


def mk(day,pos,balls):
    ns=tuple(sorted(balls))
    return {
        "day":day,"pos":pos,"no":60000+pos+int(day[-2:])*217,
        "nums":ns,"dt":day+"T"+clock(pos)[0],
        "mask":sum(1<<(n-1) for n in ns),
    }


assert clock(13)==("01:02",62) and clock(14)==("07:02",422)
assert clock(14)[1]-clock(13)[1]==360
assert bucket_duration(1)=="1" and bucket_duration(24)=="13-24"
assert bucket_duration(217)=="97+"
assert trend_label(0)=="Sabit" and trend_label(-1)=="Soğuyor"
assert clip_hits(3)=="3+"

r=random.Random(2089)
days=["2026-10-01","2026-10-02","2026-10-03","2026-10-04"]
draws=[mk(day,i,r.sample(BALLS,20)) for day in days for i in range(1,218)]
phase={days[0]:"Eğitim24",days[1]:"Doğrulama12",days[2]:"Sınama36",days[3]:"Sınama36"}
event=generate_rows(draws,phase)
assert len(event)==17+18*3
assert all(len(rows)==80 for day,start,rows in event)
assert all(rows[0]["Kesim sıra"]==start+5 for day,start,rows in event)
assert all(sum(row["H7-H12 gelen sayı"] for row in rows)==120 for day,start,rows in event)
for day,start,rows in event:
    assert [x["Sayı"] for x in rows]==list(BALLS)
    assert sum(1 for x in rows if x["Isı6"]==0)==13
    assert sum(1 for x in rows if x["Isı6"]==2)==14
    assert sum(1 for x in rows if x["Isı6"]==5)==13
    assert all(0<=x["H7-H12 gelen sayı"]<=6 for x in rows)

rates=train_rates(event)
assert all(name in rates for name in MODELS)
winner,validation=validation_choose(event,rates)
assert winner in MODELS and len(validation)==len(MODELS)
a,distribution=make_score_records(event,rates,winner)
assert len(a)==2*18*7
assert sum(z["Hedef çekiliş"] for z in distribution)==2*18*6*7
assert len(distribution)==7
# Change exclusively targets H7..H12 in the first hour; H6 snapshot and
# selected coupon must remain identical, although scored outcomes will change.
future=draws[:]
for j in range(6,12):
    future[j]=mk(days[0],j+1,range(61,81))
changed=generate_rows(future,phase)
first_a=next(rows for day,start,rows in event if day==days[0] and start==1) if False else None
# First complete eligible hour on day1 after warmup begins at position 146:
targetstart=next(start for day,start,rows in event if day==days[0])
lo=next((j for j,d in enumerate(draws) if d["day"]==days[0] and d["pos"]==targetstart+6))
future2=draws[:]
for j in range(lo,lo+6):
    d=future2[j]
    future2[j]=mk(d["day"],d["pos"],range(61,81))
changed=generate_rows(future2,phase)
x=next(rs for day,start,rs in event if day==days[0] and start==targetstart)
y=next(rs for day,start,rs in changed if day==days[0] and start==targetstart)
for aa,bb in zip(x,y):
    for f in ("Sayı","Isı6","Isı3","Kalış 3","Kalış 6","Yön","İlk6 çıkma",
              "Kesintisiz 3 sınıf çekiliş","Geçiş türü"):
        assert aa[f]==bb[f],f
assert sum(v["H7-H12 gelen sayı"] for v in y)==120
p=probability_scores(x,rates,winner)
assert len(p)==80
assert abs(sum(p)-20)<1e-6
assert abs(one_hour_brier(x,[.25]*80)-.1875)<1e-10
choices=rank_tickets(x,p,days[0],targetstart)
assert all(len(ns)==len(set(ns))==(10 if mode.endswith("10") else 20)
           for mode,ns in choices.items())
print("V29_SYNTHETIC_PASS",len(event),len(a),winner)
