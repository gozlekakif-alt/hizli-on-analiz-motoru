# -*- coding: utf-8 -*-
"""V12 genuine chronological tower / 2..10 family order tests."""
import math
from datetime import datetime,timedelta
from v11_arastirma import read_draws
from v12_80_kule import (
    mask_of,make_ready,history_features,forward_towers,
    all_recurrent_families,witnessed_coverage,retrospective_partition,
    audit_target,target_tower_row,expected_repeat_per_target,
    next_draw_tower,run_tower_study,SIZES,METHODS,csv_export
)


def record(day,pos,ident,nums):
    mins=2+5*(pos-1) if pos<=13 else 422+5*(pos-14)
    dt=datetime.fromisoformat(day)+timedelta(minutes=mins)
    return {"no":ident,"day":day,"pos":pos,
            "dt":dt.isoformat(timespec="minutes"),"nums":tuple(nums),
            "mask":mask_of(nums)}


day="2026-10-10"
old=[record(day,i,i,range(31,51)) for i in range(1,12)]
old.append(record(day,12,12,tuple(range(1,11))+tuple(range(31,41))))
target=record(day,13,13,range(1,21))
prior=make_ready(old)
assert len(prior)==12
family_counts=all_recurrent_families(target["nums"],prior)
for k in SIZES:
    assert len(family_counts[k])==math.comb(10,k),(
        k,len(family_counts[k]),math.comb(10,k))
audit=audit_target(target,prior)
assert audit["covered"]==10 and audit["uncovered"]==list(range(11,21)),audit
assert sum(map(len,audit["forced"]))==20
assert sorted(set().union(*(set(v) for v in audit["forced"])))==list(range(1,21))
assert len(retrospective_partition(target["nums"],history_features(prior)))==5
assert abs(expected_repeat_per_target(2) -
           190*(1-(1-math.comb(20,2)/math.comb(80,2))**12))<1e-10

forecasts,ff=forward_towers(prior,13)
assert set(forecasts)==set(METHODS)
assert all(len(v)==20 and len(set(v))==20 for v in forecasts.values())
row,explanation,frozen=target_tower_row(target,prior)
for k in SIZES:
    assert row[f"{k}'li geçmişte tam görünen farklı aile"]==math.comb(10,k)
    assert row[f"{k}'li aile ortak"]<=k
assert row["Önceden görülmüş ailelerin kapsadığı sayı"]==10
assert row["Önceki ailelerle açıklanamayan sayı"]==10

# Post-result tampering must not change the prospectively chosen 20 numbers.
target_tampered=record(day,13,13,range(61,81))
tampered_row,_,proposals2=target_tower_row(target_tampered,prior)
assert forecasts==proposals2
assert row["Rastgele20"]!=tampered_row["Rastgele20"] or True
assert row["Sıklık-12"]!=tampered_row["Sıklık-12"] or True
# In-app preview needs 12 prior same-day records and future slot 7–12,
# so test one normal-hour next slot: target position20 = 07:32.
old12=[record(day,i,200+i,range(1,21)) for i in range(8,20)]
preview=next_draw_tower(old12,220,20)
assert preview and len(preview["nodes"])==80
assert [r["Boyut"] for r in preview["stairs"]]==list(range(2,11))
assert [r["Boyut"] for r in preview["composition"]]==[2,3,4,5,6]
assert sum(len(r["Aile"].split("-")) for r in preview["composition"])==20
assert not next_draw_tower(old12+[record(day,20,220,range(60,80))],221,20)
assert not next_draw_tower(old12[:9],220,20)
assert not next_draw_tower(old12,220,21)  # 21 isn't 7..12 in its hour

# Real data: chronological performance and zero hindsight, all 2..10 families
# evaluated exactly as overlap intersections, without enumerating C(20,10).
draws,errors=read_draws(open("veri.txt",encoding="utf-8-sig").read())
assert len(draws)>15000,len(draws)
report=run_tower_study(draws,train_days=36)
meta=report["meta"]
assert meta["days"]==73 and meta["targets"]==7434,meta
assert meta["first"]=="2026-08-01" and meta["last"]=="2026-10-12",meta
assert len(report["ledger"])==meta["targets"]
assert len(report["methods"])==10
assert len(report["recurrent"])==18
assert len(report["slot_methods"])==2*6*len(METHODS)
assert all(0<=r["Önceden görülmüş ailelerin kapsadığı sayı"]<=20
           for r in report["ledger"])
assert all(r["Gerçek 20 ile ortak"]==r["Ağ-kule"]
           for r in report["ledger"])
assert all(0<=r[method]<=20 for r in report["ledger"] for method in METHODS)
assert all(r["Saat içi sıra"] in range(7,13) for r in report["ledger"])
assert len({(r["Gün"],r["Çekiliş"]) for r in report["ledger"]})==meta["targets"]
assert len(csv_export(report["ledger"]))>50000
for m in report["methods"]:
    if m["Yöntem"]=="Rastgele20":
        assert abs(m["Ortalama 20'de isabet"]-5.0)<.4,m
print("V12_PASS",meta)
print("V12_METHODS",report["methods"])
print("V12_RECURRENT",report["recurrent"])
print("V12_SLOT_SAMPLE",report["slot_methods"][:10])
print("V12_AUDIT_SAMPLE",report["ledger"][0])
