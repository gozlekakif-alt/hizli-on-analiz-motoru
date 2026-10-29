# -*- coding: utf-8 -*-
"""V232 | Gündüz yolu -> saatlik karakter geçişi -> hedef öncesi 10'lu kolonlar.

All targets are evaluated PREQUENTIALLY: no current/future winning numbers.
The fixed five 16-number pools are defined at 22:57 using ALL 192 daytime
draws; rolling 72 is a separate, independently updated feature window.
These are hypotheses, not proven predictive signals.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import random
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

ENGINES = (
    "IVME_DEVAMI",
    "TERS_DONUS",
    "HAVUZ_FAZ_GECISI",
    "AILE_ESLIK",
    "KARMA_KARAKTER",
    "RASTGELE_KONTROL",
)
SLOTS = (time(11,57), time(15,57), time(19,57), time(22,57))
VERSION = "V232.1"
POOL_NAMES = ("Soğuk", "Serin", "Nötr", "Ilık", "Sıcak")


def as_time(row):
    return datetime.fromisoformat(str(row["dt"]))


def validate(history, frozen):
    if set(frozen) != set(range(1,81)):
        raise ValueError("1–80 arasında tam 80 sayı gerekir")
    if [sum(x == k for x in frozen.values()) for k in range(5)] != [16]*5:
        raise ValueError("22:57 havuzları 16'şar sayı olmalı")
    if any(as_time(history[i]) >= as_time(history[i+1])
           for i in range(len(history)-1)):
        raise ValueError("Çekilişler zamana göre artan sırada olmalı")
    if any(len(row["nums"]) != 20 or len(set(row["nums"])) != 20 or
           not all(1 <= n <= 80 for n in row["nums"]) for row in history):
        raise ValueError("Her sonuçta 20 farklı 1–80 sayısı zorunlu")


def pool_rank(history):
    cnt = Counter(n for r in history for n in r["nums"])
    order = sorted(range(1,81),key=lambda n:(cnt[n],n))
    return {n:i//16 for i,n in enumerate(order)}


def frozen_at_2257(dayrows):
    if len(dayrows) != 192:
        raise ValueError("22:57 dondurması için 192 gündüz çekilişi gerekli")
    slots = [as_time(r).time() for r in dayrows]
    if slots[0] != time(7,2) or slots[-1] != time(22,57):
        raise ValueError("Gündüz saat aralığı eksik")
    if any((as_time(dayrows[i+1])-as_time(dayrows[i])).total_seconds()!=300
           for i in range(191)):
        raise ValueError("Gündüz çekiliş takviminde eksik saat var")
    return pool_rank(dayrows)


def four_paths(history, target_day):
    """Only data <= four daytime checkpoints; earlier days may supply 72 history.
    All 192 current-day draws required for four complete snapshots.
    """
    d=date.fromisoformat(target_day)
    ordered=sorted((r for r in history if as_time(r).date()<=d),key=as_time)
    paths={n:[] for n in range(1,81)}
    for clock in SLOTS:
        stamp=datetime.combine(d,clock)
        prefix=[r for r in ordered if as_time(r)<=stamp]
        if len(prefix)<36 or as_time(prefix[-1]) != stamp:
            raise ValueError(f"{stamp}: yol analizi için çekiliş eksik")
        rank=pool_rank(prefix[-72:])
        for n in range(1,81):
            paths[n].append(rank[n])
    return {n:tuple(x) for n,x in paths.items()}


def character(paths, history, frozen):
    """An interpretable label for each number; no future target outcomes."""
    prev=history[-72:]
    counts6=Counter(n for r in prev[-6:] for n in r["nums"])
    counts_prev6=Counter(n for r in prev[-12:-6] for n in r["nums"])
    out={}
    for n in range(1,81):
        p=paths[n]
        edges=[p[i+1]-p[i] for i in range(3)]
        nz=[x for x in edges if x]
        turn=sum(nz[i]*nz[i-1]<0 for i in range(1,len(nz)))
        slope=counts6[n]-counts_prev6[n]
        if turn:
            label="GERI_DONUS"
        elif p[-1]>p[0]:
            label="ISINAN"
        elif p[-1]<p[0]:
            label="SOGUYAN"
        else:
            label="SABIT"
        if p[-1] != frozen[n]:
            # Frozen 22:57 must be independently defined, not replaced.
            pass
        out[n]={"yol":"-".join("H"+str(x+1) for x in p),
                "sinif":label,"son6_fark":slope,
                "donus":turn,"son_gecis":edges[-1],
                "net":p[-1]-p[0]}
    return out


def _seed(target_stamp, name):
    data=(VERSION+"|"+str(target_stamp)+"|"+name).encode("utf-8")
    return int(hashlib.sha256(data).hexdigest()[:16],16)


def _quota(history, frozen):
    # Last three observed NIGHT real 20s only; do not use current target.
    recent=[r for r in history[-3:] if as_time(r).time()>=time(23,2)
            or as_time(r).time()<=time(1,2)]
    if len(recent)<2:
        return [2]*5
    counts=Counter(frozen[n] for r in recent for n in r["nums"])
    top=max(range(5), key=lambda k:(counts[k],-k))
    low=min(range(5), key=lambda k:(counts[k],k))
    quota=[2]*5
    if top != low and counts[top]-counts[low]>=3:
        # One-seat phase adjustment: never extreme all-in quotas.
        quota[top]+=1
        quota[low]-=1
    return quota


def _rank_selection(scores, frozen, quota, target_stamp, name):
    result=[]
    for k in range(5):
        group=[n for n in range(1,81) if frozen[n]==k]
        group.sort(key=lambda n:(
            -round(float(scores[n]),10),
            _seed(str(target_stamp)+"|"+str(n),name)))
        result.extend(group[:quota[k]])
    out=tuple(sorted(result))
    if len(out)!=10 or len(set(out))!=10:
        raise AssertionError("Kolon tam 10 farklı sayı değil")
    return out


def _score_features(history, frozen, paths):
    prev=history[-72:]
    if len(prev)<72:
        raise ValueError("Hedef öncesi 72 gerçek çekiliş gerekli")
    c6=Counter(n for r in prev[-6:] for n in r["nums"])
    cprev6=Counter(n for r in prev[-12:-6] for n in r["nums"])
    c36=Counter(n for r in prev[-36:] for n in r["nums"])
    cold36=Counter(n for r in prev[:36] for n in r["nums"])
    c72=Counter(n for r in prev for n in r["nums"])
    lasts=[set(r["nums"]) for r in prev[-3:]]
    last=set(prev[-1]["nums"])
    co=Counter()
    # Only prior 24 draws: family affinity to numbers of last THREE draws.
    links=set.union(*lasts)
    for r in prev[-24:]:
        shared=len(links.intersection(r["nums"]))
        for n in r["nums"]:
            co[n]+=max(0,shared-1)
    momentum={}; reversal={}; family={}; phase={}
    for n in range(1,81):
        p=paths[n]
        recent=c6[n]-cprev6[n]
        trend=c36[n]-cold36[n]
        steps=[p[i+1]-p[i] for i in range(3)]
        turn=(steps[1]*steps[2]<0 or
              (steps[1]==0 and steps[0]*steps[2]<0))
        wait=next((i+1 for i,r in enumerate(reversed(prev))
                   if n in r["nums"]),73)
        momentum[n]=(1.8*recent+.34*trend+.75*p[-1]-.25*abs(p[-1]-p[0])
                     +.25*c6[n])
        reversal[n]=(-1.3*recent-.20*trend+
                     1.1*int(turn)+.6*int(p[-1]!=p[-2])+
                     .2*min(wait,10))
        family[n]=(.24*co[n]+1.5*int(n in last)+
                   .5*sum(n in arr for arr in lasts)+.20*c6[n])
        phase[n]=(1.15*(p[-1]-p[-2])+
                  .3*(p[-1]-p[0])+.20*c72[n]+.55*recent)
    return {"IVME_DEVAMI":momentum,"TERS_DONUS":reversal,
            "HAVUZ_FAZ_GECISI":phase,"AILE_ESLIK":family}


def build_tickets(history, frozen, paths, target_stamp, count=1):
    """Only prior records allowed. Returns fixed 10s, never target results.
    'count' is legacy-compatible; currently precisely one ticket per engine.
    """
    if count!=1:
        raise ValueError("Her motor hedef başına bir 10'lu üretir")
    if len(history)<72:
        raise ValueError("72 önceki gerçek çekiliş gerekir")
    validate(history[-72:],frozen)
    target=datetime.fromisoformat(str(target_stamp))
    if as_time(history[-1])>=target:
        raise ValueError("Hedefin kendisi veya gelecek kayıt ön bilgiye girmiş")
    if set(paths)!=set(range(1,81)):
        raise ValueError("80 sayının gün içi yolu bulunmalı")
    if any(len(p)!=4 or any(not 0<=x<=4 for x in p) for p in paths.values()):
        raise ValueError("Her sayı dört 5'li havuz yoluna sahip olmalı")
    scores=_score_features(history,frozen,paths)
    quotas_phase=_quota(history,frozen)
    blend={}
    for name,values in scores.items():
        ordered=sorted(range(1,81),key=lambda n:(values[n],n))
        for rank,n in enumerate(ordered):
            blend[n]=blend.get(n,0)+rank/len(scores)
    scores["KARMA_KARAKTER"]=blend
    output={}
    for name in ENGINES[:-1]:
        quota=quotas_phase if name=="HAVUZ_FAZ_GECISI" else [2]*5
        output[name]=_rank_selection(scores[name],frozen,quota,target_stamp,name)
    output["RASTGELE_KONTROL"]=tuple(sorted(random.Random(
        _seed(target_stamp,"RASTGELE_KONTROL")).sample(range(1,81),10)))
    return output


def night_indices(rows, day):
    start=datetime.combine(date.fromisoformat(day),time(23,2))
    result={}
    for i,r in enumerate(rows):
        diff=(as_time(r)-start).total_seconds()
        if diff>=0 and diff<=120*60 and diff%300==0:
            result[int(diff//300)]=i
    return result


def next_target(rows, day):
    night=night_indices(rows,day)
    if len(night)>=25:
        return None
    if night:
        slot=max(night)+1
        if slot>=25:
            return None
    else:
        slot=0
    stamp=datetime.combine(date.fromisoformat(day),time(23,2))+timedelta(minutes=5*slot)
    return slot,stamp.isoformat(timespec="minutes")


def _tabulate(rows):
    result=defaultdict(list)
    for r in rows:
        result[as_time(r).date().isoformat()].append(r)
    return result


def backtest_nights(draws, max_nights=70):
    """Strict chronological, predeclared 5 engines + RNG control.
    Frozen pools from exactly 192 daytime observations. All target selections
    generated only from draws earlier than each target. No re-fitting on hits.
    """
    rows=sorted(draws,key=as_time)
    index={as_time(r):i for i,r in enumerate(rows)}
    days=_tabulate(rows)
    candidate=sorted(days)
    detail=[];daily=[];evaluated=0;missing=0
    for day in candidate:
        if evaluated>=max_nights:
            break
        relevant=[r for r in days[day] if time(7,2)<=as_time(r).time()<=time(22,57)]
        if len(relevant)!=192:
            continue
        try:
            frozen=frozen_at_2257(relevant)
            paths=four_paths(rows,day)
        except (ValueError,KeyError):
            continue
        night=night_indices(rows,day)
        if len(night)!=25:
            missing+=1
            continue
        evaluated+=1
        day_rows=[]
        for slot in range(25):
            target=rows[night[slot]]
            target_stamp=as_time(target)
            prior=rows[:index[target_stamp]]
            forecast=build_tickets(prior,frozen,paths,target_stamp.isoformat(timespec="minutes"))
            actual=set(target["nums"])
            for engine,selected in forecast.items():
                n=len(actual.intersection(selected))
                record={"gun":day,"hedef":target_stamp.isoformat(timespec="minutes"),
                        "sira":slot+1,"motor":engine,
                        "kolon":",".join(map(str,selected)),
                        "gercek20":",".join(map(str,sorted(actual))),
                        "isabet":n,"kaynak_once":as_time(prior[-1]).isoformat(timespec="minutes")}
                detail.append(record)
                day_rows.append(record)
        daily.append({"gun":day,"cekilis":25,
                      **{e:round(sum(r["isabet"] for r in day_rows
                           if r["motor"]==e)/25,4) for e in ENGINES}})
    if not evaluated:
        raise ValueError("25 gece çekilişli ve 192 gündüz çekilişli tam gün yok")
    overall=[]
    for engine in ENGINES:
        sample=[r["isabet"] for r in detail if r["motor"]==engine]
        hist=Counter(sample)
        overall.append({"motor":engine,"hedef":len(sample),
                        "ortalama":round(sum(sample)/len(sample),4),
                        **{f"{k}/10":hist[k] for k in range(11)},
                        "6+":sum(x>=6 for x in sample),
                        "7+":sum(x>=7 for x in sample),
                        "8+":sum(x>=8 for x in sample)})
    return {"test_nights":evaluated,"test_targets":evaluated*25,
            "skipped_incomplete":missing,"summary":overall,
            "day_summary":daily,"detail":detail,"version":VERSION}


def to_csv(rows):
    if not rows:
        return ""
    out=io.StringIO()
    w=csv.DictWriter(out,fieldnames=list(rows[0]),delimiter=";",lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


def source_key(rows):
    h=hashlib.sha256()
    for r in rows:
        h.update(f'{r["dt"]};{r.get("no","")};{",".join(map(str,r["nums"]))}\n'.encode())
    return h.hexdigest()
