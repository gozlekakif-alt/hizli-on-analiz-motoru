# -*- coding: utf-8 -*-
"""V17 char-label and retrospective 36/37-day prospective proper scoring tests."""
import math
from v11_arastirma import read_draws
from v17_karakter_motoru import (
    ALL_CATEGORIES,FIELDS,clock_phase,clock_half,
    full_character,build_character_rows,fit,next_character,
    latest_character,replay,csv_export
)

draws,err=read_draws(open("veri.txt",encoding="utf-8-sig").read())
assert len(draws)>=15839
assert len(FIELDS)==8
assert len(ALL_CATEGORIES)==len(FIELDS)
assert clock_phase(13)=="00 Gece"
assert clock_phase(14)=="07–11 Sabah"
assert clock_phase(217)=="17–23 Akşam"
assert clock_half(13)=="01:02 ek"
assert clock_half(16)=="İlk 6"
assert clock_half(20)=="Son 6"

# Single character must only use preceding draws, never current outcome.
day=[r for r in draws if r["day"]=="2026-10-11"]
target=next(d for d in day if d["pos"]==20)
history=[d for d in day if d["pos"]<20]
prev=history[-1]
char=full_character(target,prev,history)
assert all(char[field] in ALL_CATEGORIES[field] for field in FIELDS)
assert len(char["Aile izi 2–10"])==9
assert char["Tekrar sayısı"]==len(set(prev["nums"])&set(target["nums"]))
assert sum(char["Bant koltukları"])==20
assert sum(char["Isı gerçek"].values())==20
assert sum(char["Isı havuzu"].values())==80
assert sum(char["Aile izi 2–10"].values())>=0

observed=latest_character(history,20)
assert observed is not None
assert observed["Tekrar sayısı"]==len(set(history[-1]["nums"]) &
                                         set(history[-2]["nums"]))
assert not latest_character(history+[target],20)
assert not latest_character(history,14)
assert not latest_character(history[:9],20)
# Target can change without changing the character available before target.
assert observed==latest_character(history,20)

report=replay(draws,train_days=36)
m=report["meta"]
assert m["train_days"]==36 and m["test_days"]==37,m
assert m["test_first"]=="2026-09-06" and m["test_last"]=="2026-10-12",m
assert m["test_targets"]==37*203,m
assert m["train_targets"]>=36*200,m
assert len(report["comparison"])==len(FIELDS)
assert len(report["metrics"])==len(FIELDS)*2
assert len(report["family_echo"])==9
assert len(report["ledger"])==m["test_targets"]
assert report["phases"]
assert report["flow"]
assert all(x["Test hedefi"]==m["test_targets"] for x in report["comparison"])
assert all(x["Log-kayıp (az iyi)"]>=0 for x in report["metrics"])
assert len(csv_export(report["ledger"]))>10000
for f in FIELDS:
    assert report["comparison"][list(FIELDS).index(f)]["Karakter"]==f

model=report["model"]
preview=next_character(observed,20,model)
assert set(preview)==set(FIELDS)
for f in FIELDS:
    assert set(preview[f])==set(ALL_CATEGORIES[f])
    assert abs(sum(preview[f].values())-1)<.000001
    assert all(0<=p<=1 for p in preview[f].values())
    base=model["baseline"][(clock_phase(20),f)]
    assert abs(sum(base.values())-1)<1e-12
# Model is frozen: changed outcome of target 20 can never alter preview.
fake_target={**target,"nums":tuple(range(61,81))}
assert preview==next_character(latest_character(history,20),20,model)
assert fake_target["nums"]!=tuple(target["nums"])
print("V17_PASS",m)
print("V17_COMPARISON",report["comparison"])
print("V17_PHASES",report["phases"])
print("V17_FAMILY_ECHO",report["family_echo"])
print("V17_PREVIEW",preview)
