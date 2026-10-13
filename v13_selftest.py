# -*- coding: utf-8 -*-
"""V13 tests: day slot 1..217, 80-number states, 36/37 split, family/seat counts.

No outcome data in prediction features. Fixed first-period calibration only.
"""
import math
from v11_arastirma import read_draws
from v13_havuz_koltuk import (
    SIZES,TYPES,phase,confidence_hit,state_of,states_for_day,
    trained_model,conditional_rate,quotas,pick_20,family_test,
    run_study,next_day_preview,csv_export
)


def record(day,pos,no,nums):
    return {"day":day,"pos":pos,"no":no,
            "dt":day+"T07:02","nums":tuple(nums)}


assert phase(1)=="Başlangıç"
assert phase(36)=="Başlangıç"
assert phase(37)=="Orta"
assert phase(144)=="Orta"
assert phase(145)=="Son"
assert phase(217)=="Son"
assert abs(confidence_hit(6)-math.prod((20-i)/(80-i) for i in range(6)))<1e-13

# Test some synthetic rising, peak, cooldown and silent histories.
history=[record("2026-10-10",j,j,tuple(range(1,21)) if j%2 else tuple(range(21,41)))
         for j in range(1,40)]
data=states_for_day(history)
assert len(data)==80 and len({s["n"] for s in data})==80
for k in (1,2,10,21,41,80):
    reference=state_of(history,k)
    fast=data[k-1]
    assert all(fast[p]==reference[p]
               for p in ("n","pool","label","day","seen","z",
                         "recent12","recent6","prev6","slope","gap")),(
        k,reference,fast)
assert sum(s["day"] for s in data)==len(history)*20
assert all(s["pool"] in TYPES for s in data)
assert all(s["label"] for s in data)
assert all(st["gap"]>=1 for st in data)

fake_train=[]
for day in range(1,4):
    ds=f"2026-09-{day:02d}"
    for pos in range(1,25):
        nums=tuple(sorted({((pos*11 + day*7 + i*9)%80)+1 for i in range(20)}))
        assert len(nums)==20,nums
        fake_train.append(record(ds,pos,day*1000+pos,nums))
small_model=trained_model(fake_train,2)
assert len(small_model["days"])==2
assert small_model["train_draws"]==48
for pos in (2,25,112,216):
    target_state=states_for_day(history)
    a=quotas(target_state,small_model,pos)
    assert sum(a.values())==20
    for style in ("Koltuk-model","Tepeyi azalt","Tepeyi koru"):
        result,seats=pick_20(target_state,small_model,pos,style)
        assert len(result)==len(set(result))==20
        assert sum(seats.values())==20
    assert pick_20(target_state,small_model,pos,"Koltuk-model")[0]==pick_20(target_state,small_model,pos,"Koltuk-model")[0]

actual=record("2026-10-10",40,40,range(1,21))
familyrows=family_test(target_state,actual)
assert all(row["Boyut"] in SIZES for row in familyrows)
assert all(row["Tam"]==(row["İsabet"]==row["Boyut"])
           for row in familyrows)
assert all(0<=row["İsabet"]<=row["Boyut"] for row in familyrows)

# Input-target alteration must not change generated coupons or seats.
other_target=record("2026-10-10",40,40,range(61,81))
before=states_for_day(history)
coupons_a={m:pick_20(before,small_model,40,m)[0]
           for m in ("Koltuk-model","Tepeyi azalt","Tepeyi koru")}
coupons_b={m:pick_20(states_for_day(history),small_model,40,m)[0]
           for m in coupons_a}
assert coupons_a==coupons_b
assert family_test(before,actual)!=family_test(before,other_target)

# Live preview must not need target result; model comes from previous days.
preview=next_day_preview(history,small_model,40,40)
assert preview and len(preview["states"])==80
assert sum(preview["seats"].values())==20
assert len(preview["groups"])==5
assert len(preview["stairs"])==len(SIZES)
assert all(len(x)==20 for x in preview["coupons"].values())
assert not next_day_preview(history+[actual],small_model,40,40)

raw=open("veri.txt",encoding="utf-8-sig").read()
draws,errors=read_draws(raw)
assert len(draws)>15000
r=run_study(draws,train_days=36)
meta=r["meta"]
assert meta["train_days"]==36 and meta["holdout_days"]==37,meta
assert meta["test_first"]=="2026-09-06",meta
assert meta["test_last"]=="2026-10-12",meta
assert meta["test_targets"]==37*217,meta
assert len(r["ledger"])==meta["test_targets"]
assert len({(x["Tarih"],x["Hedef"]) for x in r["ledger"]})==meta["test_targets"]
assert len(r["seats"])>=9
assert len(r["seat_exact"])==3
assert sum(x["Hedef"] for x in r["seat_exact"])==meta["test_targets"]
assert all(0<=x["20 koltuk dağılımı tam tuttu"]<=x["Hedef"] for x in r["seat_exact"])
assert len(r["states"])>=20
assert len(r["family"])>=3*9
assert len(r["nested"])==9
assert all(row["Hedef"]==meta["test_targets"] for row in r["nested"])
assert all(0<=row["Tam k/k"]<=row["Hedef"] for row in r["nested"])
assert r["methods"]
assert len(r["train_model"]["days"])==36
assert sum(x["Sayı-hedef gözlemi"] for x in r["states"])==meta["test_targets"]*80
assert sum(x["Sonraki çekilişte çıktı"] for x in r["states"])==meta["test_targets"]*20
assert all(x["Hedef"]>0 and 0<=x["Ortalama 20'de"]<=20
           for x in r["methods"])
assert len(csv_export(r["methods"]))>100
assert len(csv_export(r["ledger"]))>20000
assert any(x["Yöntem"]=="Koltuk+V12" and x["Kapsam"]=="7–12" and x["Hedef"]==3774
           for x in r["methods"]),r["methods"]
assert any(x["Yöntem"]=="Koltuk-model" and x["Kapsam"]=="Diğer" and x["Hedef"]==meta["test_targets"]-3774
           for x in r["methods"])
print("V13_PASS",meta)
print("V13_METHODS",r["methods"])
print("V13_SEATS",r["seats"])
print("V13_FAMILY",r["family"])
print("V13_HOT_COLD",r["states"])
print("V13_ONE_TARGET",r["ledger"][0])
