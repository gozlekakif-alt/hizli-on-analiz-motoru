# -*- coding: utf-8 -*-
"""V14 strict 80x80 / 217-slot chronological out-of-sample integration tests."""
import math
from datetime import datetime,timedelta
from v11_arastirma import read_draws
from v14_gecis_agi import (
    LAGS,METHODS,clock_slot,pair_model,conditional,candidate_score,
    predict_20,leading_pairs,replay,preview,csv_export
)

def item(day,pos,ident,nums):
    t=2+5*(pos-1) if pos<=13 else 422+5*(pos-14)
    return {"day":day,"pos":pos,"no":ident,
            "dt":(datetime.fromisoformat(day)+timedelta(minutes=t)).isoformat(timespec="minutes"),
            "nums":tuple(nums)}

assert clock_slot(1)==("00",1,"Gece")
assert clock_slot(13)==("00",13,"Gece")
assert clock_slot(14)==("07",1,"Sabah")
assert clock_slot(217)==("23",12,"Akşam")
assert set(LAGS)=={1,2,3,6,12}

# Deterministic outcomes; all scores must be computed without seeing target.
synthetic=[]
for d in range(1,5):
    day=f"2026-08-{d:02d}"
    for i in range(1,25):
        rng=[(i*7+j*9+d*11)%80+1 for j in range(20)]
        assert len(set(rng))==20
        synthetic.append(item(day,i,d*1000+i,rng))
p=pair_model(synthetic,train_days=3)
assert len(p["days"])==3
assert p["train_transitions"]==3*23
assert all(0<=conditional(p,lag,7,21)<=1 for lag in LAGS)
day4=[x for x in synthetic if x["day"]=="2026-08-04"]
prior=[x for x in day4 if x["pos"]<24]
for name in METHODS:
    forecast=predict_20(p,prior,24,name,4024)
    assert forecast is not None and len(forecast)==len(set(forecast))==20
    assert all(1<=n<=80 for n in forecast)
assert predict_20(p,prior,24,"V14 çok-adım ağ",4024)==predict_20(p,prior,24,"V14 çok-adım ağ",4024)
assert predict_20(p,prior[:4],24,"V14 çok-adım ağ",4024) is None
assert not leading_pairs(p,min_exposure=99999)

with open("veri.txt",encoding="utf-8-sig") as f:
    draws,bad=read_draws(f.read())
assert len(draws)==15968,len(draws)
study=replay(draws,train_days=36)
meta=study["meta"]
assert meta["train_days"]==36 and meta["holdout_days"]==37,meta
assert meta["first_test"]=="2026-09-06" and meta["last_test"]=="2026-10-12",meta
assert meta["test_transitions"]==37*216,meta
assert len(study["ledger"])==meta["test_transitions"],meta
assert len(study["positions"])==216
assert study["half_hours"]
assert study["pairs"]
assert study["times"]
assert study["paired"]
assert all(0<=r["Önceki 20'den kalan"]<=20 for r in study["ledger"])
assert all(r["Önceki 20'den kalan"]+r["Yeni giren"]==20
           for r in study["ledger"])
assert all(r["Önceki 20'den kalan"]+r["Önceki 20'den ayrılan"]==20
           for r in study["ledger"])
assert all(0<=r[n]<=20 for r in study["ledger"] for n in METHODS)
assert all(r["V12 ağ-kule"] is None or 0<=r["V12 ağ-kule"]<=20
           for r in study["ledger"])
assert len(csv_export(study["ledger"]))>90000
assert all(s["Hedef"]>0 for s in study["methods"])
assert sum(x["Hedef"] for x in study["methods"]
           if x["Yöntem"]=="V14 bir-adım ağ")==meta["test_transitions"]
assert sum(x["Hedef"] for x in study["methods"]
           if x["Yöntem"]=="Rastgele20")==meta["test_transitions"]
for r in study["pairs"]:
    assert 0<=r["Sonraki günler B geldi"]<=r["Sonraki günler gözlem"]
    assert 0<=r["B ayrılma sonrası geldi"]<=r["A gerçekten ayrıldı koşul"]
    assert r["Kaynak"]!=r["Yeni sayı"]
    assert r["Sonraki günler gözlem"]>0

# Future preview: new target unknown; no target outcomes may enter scoring.
selected=[d for d in draws if d["day"]=="2026-10-12" and d["pos"]<21]
next_no=max(d["no"] for d in selected)+1
live=preview(selected,study["model"],study["v13_model"],21,next_no)
assert live and len(live["nodes"])==80
assert all(len(coupon)==20 for coupon in live["predictions"].values())
assert not preview(selected,study["model"],study["v13_model"],20,next_no)
mutated=[*selected,item("2026-10-12",21,next_no,tuple(range(61,81)))]
assert not preview(mutated,study["model"],study["v13_model"],21,next_no)

print("V14_PASS",meta)
print("V14_METHODS",study["methods"])
print("V14_TIMES",study["times"])
print("V14_HALF",study["half_hours"])
print("V14_PAIR_FIRST",study["pairs"][:8])
print("V14_PAIRED",study["paired"])
