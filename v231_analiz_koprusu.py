# -*- coding: utf-8 -*-
"""V231: ortak laboratuvar için izole, tarih-sıralı, rastgele kontrollü motorlar.

Yalnız gerçek, hedef ÖNCESİ verisini kullanır; gelecek RNG'yi çözme iddiası yoktur.
Z3 optimizasyon/kısıt aracı, XGBoost kronolojik karşılaştırma,
NumPy/Numba aynı-çekiliş eşlikçi hesabı, SciPy null testi.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import math
import random
from collections import Counter
from datetime import datetime

NAMES = ("Çok soğuk", "Serin", "Nötr", "Ilık", "Çok sıcak")
TOOLS = ("streamlit", "numpy", "scipy", "numba", "xgboost", "z3-solver")


def versions():
    result={}
    for name in TOOLS:
        try:
            result[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name]=None
    return result


def cleaned(draws):
    """Ordered, conflict-free real results. No imaginary future records."""
    seen_date, seen_id = set(), set()
    out=[]
    for r in sorted(draws,key=lambda v: v["dt"]):
        stamp=str(r["dt"])
        nums=tuple(sorted(map(int, r["nums"])))
        identity=int(r["no"])
        if len(nums)!=20 or len(set(nums))!=20 or nums[0]<1 or nums[-1]>80:
            raise ValueError("Geçersiz 20'li: "+stamp)
        if identity in seen_id or stamp in seen_date:
            raise ValueError("Çakışan çekiliş: "+stamp)
        seen_id.add(identity)
        seen_date.add(stamp)
        out.append({"dt":stamp,"no":identity,"nums":nums})
    return out


def checksum(draws):
    h=hashlib.sha256()
    for d in cleaned(draws):
        h.update(f'{d["no"]}|{d["dt"]}|{",".join(map(str,d["nums"]))};'.encode())
    return h.hexdigest()


def pairs_numpy(draws,limit=217):
    import numpy as np
    latest=cleaned(draws)[-limit:]
    if not latest:
        return []
    matrix=np.zeros((len(latest),80),dtype=np.int16)
    for i,r in enumerate(latest):
        matrix[i,np.array(r["nums"])-1]=1
    co=matrix.T.astype(np.int32) @ matrix.astype(np.int32)
    return [{"sayı_a":i+1,"sayı_b":j+1,"birlikte":int(co[i,j])}
            for i in range(80) for j in range(i+1,80)]


def pairs_numba(draws,limit=217):
    import numpy as np
    from numba import njit
    latest=cleaned(draws)[-limit:]
    numbers=np.array([r["nums"] for r in latest],dtype=np.int64).reshape((-1,20))
    @njit(cache=False)
    def calc(a):
        grid=np.zeros((80,80),dtype=np.int64)
        for row in range(a.shape[0]):
            for i in range(20):
                for j in range(i+1,20):
                    x=a[row,i]-1
                    y=a[row,j]-1
                    if x>y: x,y=y,x
                    grid[x,y]+=1
        return grid
    co=calc(numbers)
    return [{"sayı_a":i+1,"sayı_b":j+1,"birlikte":int(co[i,j])}
            for i in range(80) for j in range(i+1,80)]


def scipy_pool_null(night_draws,pools):
    """Frozen 5x16 day pools vs predeclared 25% per-number null, descriptive."""
    from scipy.stats import binomtest
    draws=cleaned(night_draws)
    out=[]
    for i,label in enumerate(NAMES):
        members=[n for n in range(1,81) if pools[n]==i]
        if len(members)!=16:
            raise ValueError("Bu test için her sabit havuz 16 sayı olmalı.")
        hits=sum(sum(n in members for n in d["nums"]) for d in draws)
        trials=16*len(draws)
        p=binomtest(hits,trials,.25).pvalue if trials else None
        out.append({"havuz":label,"gerçek":hits,"beklenen":trials*.25,
                    "oran":hits/trials if trials else None,
                    "ham_p":p,"bonferroni_p":min(1,p*5) if p is not None else None})
    return out


def z3_constraint_tickets(pools,arrows,count=2,seed=20261029):
    """Every ticket has exactly 2 numbers from each 16-number pool; direction mix where feasible."""
    from z3 import Bool, If, Solver, Sum, Or, Not, sat, is_true
    if sorted(pools)!=list(range(1,81)):
        raise ValueError("1..80 sayının hepsinin havuzu bulunmalı.")
    if [sum(v==k for v in pools.values()) for k in range(5)]!=[16]*5:
        raise ValueError("Havuzların her biri 16 sayı olmalı.")
    if not 1<=count<=3:
        raise ValueError("1–3 kolon")
    solver=Solver()
    solver.set("random_seed",int(seed)%1000000)
    slots={n:Bool(f"sec_{n}") for n in range(1,81)}
    S=lambda ns:Sum(*[If(slots[n],1,0) for n in ns])
    for k in range(5):
        solver.add(S([n for n in slots if pools[n]==k])==2)
    rising=[n for n in slots if arrows[n]=="→"]
    falling=[n for n in slots if arrows[n]=="←"]
    if rising:solver.add(S(rising)>=1)
    if falling:solver.add(S(falling)>=1)
    result=[]
    for i in range(count):
        if solver.check()!=sat:
            break
        m=solver.model()
        pick=tuple(sorted(n for n in slots if is_true(m.eval(slots[n]))))
        if len(pick)!=10:
            raise AssertionError("Z3 10 sayılık kota üretmedi")
        result.append(pick)
        solver.add(Or(*[Not(slots[n]) for n in pick]))
    return result


def _features(history):
    """Features available BEFORE the target draw (no future leakage)."""
    if len(history)<72:
        raise ValueError("En az 72 geçmiş çekiliş gerekir.")
    prev=history[-72:]
    c6=Counter(n for d in prev[-6:] for n in d["nums"])
    c12=Counter(n for d in prev[-12:] for n in d["nums"])
    c36=Counter(n for d in prev[-36:] for n in d["nums"])
    c72=Counter(n for d in prev for n in d["nums"])
    before=Counter(n for d in prev[:36] for n in d["nums"])
    previous=set(history[-1]["nums"])
    ranks=sorted(range(1,81),key=lambda n:(c72[n],n))
    pool={n:i//16 for i,n in enumerate(ranks)}
    waits={n:73 for n in range(1,81)}
    for lag,d in enumerate(reversed(prev),1):
        for n in d["nums"]:
            if waits[n]==73: waits[n]=lag
    return [[c6[n],c12[n],c36[n],c72[n],c36[n]-before[n],
             waits[n],pool[n],int(n in previous),(n-1)//10] for n in range(1,81)]


def _sample_indices(rows,limit):
    # Deterministic calendar-spanning step, not last several overlapping hours only.
    available=list(range(72,len(rows)))
    if len(available)>limit:
        step=(len(available)-1)/(limit-1)
        available=[available[round(i*step)] for i in range(limit)]
    return available


def xgb_walkforward(draws,max_targets=250,trees=40):
    """Fixed chronological train/test split of days, 80 rows per target.
    Compare ten selected numbers with blind seeded random ten on *same* test targets.
    """
    from xgboost import XGBClassifier
    rows=cleaned(draws)
    if len(rows)<150:
        raise ValueError("XGBoost için en az 150 gerçek çekiliş gerekli.")
    if not 100<=max_targets<=600:
        raise ValueError("max_targets 100–600")
    indices=_sample_indices(rows,max_targets)
    dates=sorted({rows[i]["dt"][:10] for i in indices})
    if len(dates)<4:
        raise ValueError("Güvenilir ayrık gün testi için en az 4 farklı gün gerekli.")
    boundary=dates[max(1,int(len(dates)*.70))-1]
    training=[i for i in indices if rows[i]["dt"][:10]<=boundary]
    testing=[i for i in indices if rows[i]["dt"][:10]>boundary]
    if len(training)<40 or len(testing)<12:
        raise ValueError("Eğitim/test için yeterli çekiliş yok.")
    X=[];y=[]
    for i in training:
        feature=_features(rows[:i])
        result=set(rows[i]["nums"])
        X.extend(feature)
        y.extend(int(n in result) for n in range(1,81))
    model=XGBClassifier(n_estimators=int(trees),max_depth=3,learning_rate=.07,
                        subsample=.90,colsample_bytree=.85,objective="binary:logistic",
                        eval_metric="logloss",n_jobs=2,random_state=17,
                        tree_method="hist")
    model.fit(X,y)
    details=[]
    for i in testing:
        dt=rows[i]["dt"]
        p=model.predict_proba(_features(rows[:i]))[:,1]
        picked=tuple(sorted(sorted(range(1,81),key=lambda n:(-float(p[n-1]),n))[:10]))
        seed=int(hashlib.sha256(("V231|"+dt).encode()).hexdigest()[:16],16)
        control=tuple(sorted(random.Random(seed).sample(range(1,81),10)))
        actual=set(rows[i]["nums"])
        details.append({"tarih_saat":dt,"model_isabet":len(actual.intersection(picked)),
                        "rastgele_isabet":len(actual.intersection(control)),
                        "model_10lu":",".join(map(str,picked)),
                        "rastgele_10lu":",".join(map(str,control))})
    avg_model=sum(v["model_isabet"] for v in details)/len(details)
    avg_random=sum(v["rastgele_isabet"] for v in details)/len(details)
    return {"trained_days":len(set(rows[i]["dt"][:10] for i in training)),
            "tested_days":len(set(rows[i]["dt"][:10] for i in testing)),
            "train_draws":len(training),"test_draws":len(testing),
            "model_mean":round(avg_model,4),"random_mean":round(avg_random,4),
            "mathematical_mean":2.5,"split_through_day":boundary,
            "details":details}
