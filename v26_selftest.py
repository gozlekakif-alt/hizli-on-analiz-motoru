# -*- coding: utf-8 -*-
"""V26 tests: category definitions, quotas, historical cutoff, no leakage."""
import random
from collections import Counter
from v21_aile_yasam_dongusu import clock
from v25_aile_dna_kupon import family_bits
from v26_karma_kupon import (
    classify, mixed_ten, snapshot, evaluate_day, HOUR_STARTS,
    MIX_CONFIG, ALL_METHODS, rng_distribution, fit_first36
)


def new_draw(pos,nums):
    ns=tuple(sorted(nums))
    return {"no":50000+pos,"pos":pos,"nums":ns,
            "day":"2026-10-01","dt":"2026-10-01T"+clock(pos)[0],
            "mask":family_bits(ns)}

assert clock(1)==("00:02",2)
assert clock(13)==("01:02",62)
assert clock(14)==("07:02",422)
assert clock(14)[1]-clock(13)[1]==360
rng=random.Random(2026)
draws=[new_draw(p,rng.sample(range(1,81),20)) for p in range(1,218)]
six=draws[:6]
cl=classify(six)
assert cl["hot"]=={n for n in range(1,81) if sum(n in d["nums"] for d in six)>=3}
assert cl["cold"]=={n for n in range(1,81) if all(n not in d["nums"] for d in six)}
assert all(n not in d["nums"] for n in cl["new"] for d in six[:3])
assert all(any(n in d["nums"] for d in six[3:]) for n in cl["new"])
assert sum(len(cl[k]) for k in ("hot","cold","new","mid"))==80
for name,(hot,cold,emerge,aware) in MIX_CONFIG.items():
    balls,real=mixed_ten(cl,(hot,cold,emerge))
    assert len(balls)==len(set(balls))==10
    assert sum(real.values())==10
    assert set(balls).issubset(set(range(1,81)))
    # Filled proportions exact when enough in respective category.
    if min(len(cl["hot"])-hot,len(cl["cold"])-cold,len(cl["new"])-emerge)>=0:
        assert (real["hot"],real["cold"],real["new"],real["mid"]) == (hot,cold,emerge,0)
c1,s1=snapshot("2026-10-01",1,draws[:6])
assert set(c1)==set(ALL_METHODS)
assert all(len(x)==10 and len(set(x))==10 for x in c1.values())
changed=draws[:6]+[new_draw(p,list(range(1,11))+list(range(61,71))) for p in range(7,218)]
c2,s2=snapshot("2026-10-01",1,changed[:6])
assert c1==c2 and s1==s2
first_r,first_sig=evaluate_day("2026-10-01",draws)
new_r,new_sig=evaluate_day("2026-10-01",changed)
assert len(first_r)==18*len(ALL_METHODS)
assert len(first_sig)==18
# Every first hour coupon and category stays identical after altering all targets.
for a,b in zip(first_r,new_r):
    if a["Saat"]=="00:02":
        assert a["10 sayı"]==b["10 sayı"] and a["Yöntem"]==b["Yöntem"]
# All 18 full-hour results must be reproducible from frozen snapshots
for start in HOUR_STARTS:
    methods,_=snapshot("2026-10-01",start,draws[:start+5])
    actual={r["Yöntem"]:r for r in first_r if r["Saat"]==clock(start)[0]}
    for mode,nums in methods.items():
        assert actual[mode]["10 sayı"]=="-".join(f"{n:02d}" for n in nums)
        assert actual[mode]["6 çekiliş toplam isabet"]==sum(
            actual[mode][f"Hedef {i}"] for i in range(1,7))
# Fair lottery hypergeometric expectations and normalization.
p=rng_distribution(3888)
assert abs(sum(x["Adil RNG tek çekiliş olasılığı"] for x in p)-1)<1e-8
assert abs(sum(x["Tam isabet"]*x["Adil RNG tek çekiliş olasılığı"] for x in p)-2.5)<1e-7
# Training is isolated: winner determined by FIRST36 training labels only.
training=[]
for day_i in range(36):
    for r in first_r:
        training.append({**r,"Dönem":"İlk36","Tarih":f"2026-08-{day_i+1:02d}"})
w,s=fit_first36(training)
assert w in MIX_CONFIG
assert len(s)==4
print("V26_SYNTHETIC_PASS",len(first_r),len(first_sig),w)
