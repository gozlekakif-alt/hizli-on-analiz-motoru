# -*- coding: utf-8 -*-
"""V16 math/test no-lookahead and full 73-day observed overlap audit."""
from math import comb
from v11_arastirma import read_draws
from v16_rng_salinim import (
    PROBS,GROUPS,bucket,contiguous,consecutive_rows,
    overlap,build_model,analyze
)
assert abs(sum(PROBS.values())-1)<1e-12
assert abs(sum(k*p for k,p in PROBS.items())-5)<1e-12
assert abs(PROBS[12]-(comb(20,12)*comb(60,8)/comb(80,20)))<1e-15
assert bucket(1)=="0–2" and bucket(12)=="9+"
assert contiguous(13) and not contiguous(14) and contiguous(15)
# Synthetic two days: first 20 alternate disjoint with second 20.
raw=[]
for d in (1,2):
    for pos in (1,2,3,13,14,15,16):
        nums=tuple(range(1,21)) if pos%2==1 else tuple(range(21,41))
        raw.append({"day":f"2026-08-{d:02d}","pos":pos,
                    "no":d*1000+pos,"dt":f"2026-08-{d:02d}T07:02",
                    "nums":nums})
rows=list(consecutive_rows(raw))
assert all(r["pos"]!=14 for r in rows)
assert any(r["pos"]==15 and r["prev_x"] is None for r in rows)
# A future altered RESULT may only change evaluation, never trained probabilities.
train=list(r for r in rows if r["day"]=="2026-08-01")
fitted=build_model(train)
holdout=list(r for r in rows if r["day"]=="2026-08-02")
assert "0–2" in fitted["prob"]
for label in GROUPS:
    assert abs(sum(fitted["prob"][label].values())-1)<1e-10
# Proven 5-minute consecutive transitions; train/test calendar split.
txt=open("veri.txt",encoding="utf-8-sig").read()
draws,bad=read_draws(txt)
assert len(draws)>=15839
report=analyze(draws,train_days=36)
m=report["meta"]
assert m["calendar_days"]==73,m
assert m["train_days"]==36 and m["test_days"]==37,m
assert m["test_transitions"]==37*215,m
assert m["conditional_targets"]==37*213,m
assert m["train_transitions"]<=36*215,m
assert m["n_transitions"]==m["train_transitions"]+m["test_transitions"]
assert m["mean_overlap"]>=0 and m["mean_overlap"]<=20
assert m["degrees_freedom"]==10
assert len(report["distribution"])==21
assert len(report["pooled_distribution"])==11
assert len(report["hour"])==18
assert len(report["forecast"])==5
assert len(report["conditional"])==5
assert all(x["Test geçiş"]>=0 for x in report["hour"])
assert sum(x["Gerçek bütün dönem"] for x in report["distribution"])==m["n_transitions"]
assert sum(x["Gözlenen"] for x in report["pooled_distribution"])==m["n_transitions"]
assert sum(x["Test geçiş"] for x in report["hour"])==m["test_transitions"]
assert m["observed_12plus"]>=0
assert 0<m["expected_12plus"]<5
print("V16_PASS",m)
print("V16_DISTRIBUTION",report["distribution"])
print("V16_POOLED",report["pooled_distribution"])
print("V16_HOUR",report["hour"])
print("V16_HALVES",report["halves"])
print("V16_CONDITIONAL",report["conditional"])
print("V16_FORECAST",report["forecast"])
