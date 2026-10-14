# -*- coding: utf-8 -*-
"""V28 "Dijital Kaplan": 80-ball thermal life cycle, H1..H12, day-to-day
carry, transition/stay durations, 6-state seats, actual RNG null simulations.

IMPORTANT: descriptive stability is EXPECTED even for independent RNG because
an exponentially-smoothed statistic has memory. Null simulations recompute
the SAME temperature algorithm on independent 20-of-80 daily draws.
No algorithm reverse-engineering or guaranteed forecast is claimed.

Definitions: temperature score = EWM with 12 REAL DRAW half life, continuous
across calendar days, NO daily reset. Six rank seats have sizes
13,13,14,14,13,13. Macro: COLD(26), WARM(28), HOT(26).
H1..H12 refer to positions 1..12 WITHIN each 12-draw hour; 01:02
is a separately tagged draw. Never invent six-hour overnight draws.
All states labeled BEFORE seeing that draw's twenty numbers.
"""
from __future__ import annotations
import argparse
import csv
import io
import json
import math
import random
import zipfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
from v11_arastirma import read_draws
from v21_aile_yasam_dongusu import group_full_days,clock,csv_bytes

BALLS=tuple(range(1,81))
HEAT_SIX=("Soğuk","Soğuğa yakın","Orta","Ilık","Sıcağa yakın","Sıcak")
HEAT_MACRO=("Soğuk","Ilık","Sıcak")
SIX_SIZES=(13,13,14,14,13,13)
HEAT_MAP=(0,0,1,1,2,2)
HALF_LIFE=12
DECAY=0.5**(1/HALF_LIFE)
WARMUP=144
RNG_REPS=6
PRIOR=240.
HOUR_STARTS=(1,)+tuple(14+12*h for h in range(17))


def hour_info(pos):
    if pos==13:
        return "01:02 tek",0,"Ek"
    if 1<=pos<=12:
        return "00:02",1+(pos-1)//12,"H"+str(pos)
    if 14<=pos<=217:
        h=(pos-14)//12
        return f"{7+h:02d}:02",h+2,"H"+str(1+(pos-14)%12)
    raise ValueError(pos)


def day_consecutive(before,after):
    return (date.fromisoformat(after)-date.fromisoformat(before)).days==1


def state_before(ewma):
    # All pretarget labels are a partition of 80, even with tied scores.
    order=sorted(BALLS,key=lambda n:(ewma[n],n))
    six=[0]*81
    cur=0
    for j,size in enumerate(SIX_SIZES):
        for n in order[cur:cur+size]:
            six[n]=j
        cur+=size
    three=[0]+[HEAT_MAP[six[n]] for n in BALLS]
    return six,three


def make_cache(draws, seed=None):
    """Historic valid timestamps may include incomplete-day context.
    Synthetic sample exactly preserves timestamp slots and 20-of-80 structure."""
    order=sorted(draws,key=lambda r:(r["day"],r["pos"]))
    if seed is None:return order
    rng=random.Random(seed)
    return [{**r,"nums":tuple(sorted(rng.sample(BALLS,20)))} for r in order]


def ordered_phases(full):
    if len(full)<72:
        raise ValueError("Need 72 full days for 36/36 strict holdout")
    d=[day for day,_ in full][:72]
    return {day:("Öğrenme" if i<36 else "Test") for i,day in enumerate(d)}


def profile(draws, eligible, detailed=True, forecast=False, progress=None):
    """Single streaming pass, no backwards target knowledge.

    Returns aggregate counts plus optional per-ball hour profiles and
    day-to-day transition audit. Can run on identical RNG null sequence.
    """
    scores=[0.]*81
    six_previous=None
    three_previous=None
    previous=None
    # runs track state at each *observed draw decision time*.
    streak=[0]*81
    streak_start=[None]*81
    streak_day=[None]*81
    prevstate=[None]*81
    six_streak=[0]*81
    six_prevstate=[None]*81
    counts=defaultdict(Counter)
    hourly=defaultdict(lambda:{"macro":Counter(),"six":Counter(),
         "hit":Counter(),"switches":Counter(),"initial":{},
         "end":{},"last":{},"longest":Counter(),"localrun":{},
         "paths":defaultdict(list),"sixpaths":defaultdict(list),"n":0})
    per_hour_rows=[]
    runrows=[]
    daypair=[]
    daily=defaultdict(lambda:Counter())
    daily_sig=defaultdict(lambda:[0]*36)
    slot_counts=defaultdict(Counter)
    forecast_rows=[]
    snapshots={}
    valid_processed=0
    last_evaluated_t=None
    last_hour_macro=[None]*81
    last_hour_day=[None]*81
    def finalize_hour(key,r):
        if not detailed:return
        date,hour=key
        for n in BALLS:
            path=r["paths"][n]
            path6=r["sixpaths"][n]
            if len(path)!=12 or len(path6)!=12:continue
            table={
                "Tarih":date,"Saat":hour,"Sayı":n,
                "H1..H12 makro yolları":"".join(str(x+1) for x in path),
                "H1..H12 altı sıcaklık yolları":"".join(str(x+1) for x in path6),
                "Altı sıcaklık sınıf geçiş":sum(path6[i]!=path6[i-1] for i in range(1,12)),
                "H1 sınıf":HEAT_MACRO[path[0]],
                "H12 sınıf":HEAT_MACRO[path[-1]],
                "H1→H12 değişti":int(path[0]!=path[-1]),
                "Saat içi sınıf geçiş":sum(path[i]!=path[i-1] for i in range(1,12)),
                "Soğukta H":path.count(0),
                "Ilıkta H":path.count(1),
                "Sıcakta H":path.count(2),
                "Bu saat çıkan çekiliş":r["hit"][n],
            }
            for j,name in enumerate(("Soğuk","Ilık","Sıcak")):
                length=0;maxlen=0
                for x in path:
                    length=length+1 if x==j else 0
                    maxlen=max(maxlen,length)
                table[f"{name} en uzun H kalış"]=maxlen
            for j,level in enumerate(HEAT_SIX):
                run6=longest6=0
                for x in path6:
                    run6=run6+1 if x==j else 0
                    longest6=max(longest6,run6)
                table[f"{level} H sayısı"]=path6.count(j)
                table[f"{level} en uzun H kalış"]=longest6
            per_hour_rows.append(table)

    for t,d in enumerate(draws):
        six,macro=state_before(scores)
        day=d["day"]
        pos=d["pos"]
        total_before=t
        eligible_target=(day in eligible and t>=WARMUP)
        is_valid_day=(day in eligible)
        hour,ord_hour,h=hour_info(pos)
        ns=set(d["nums"])
        dt=d["dt"]
        if six_previous is not None and eligible_target:
            for n in BALLS:
                a=six_previous[n];b=six[n]
                counts["six_trans"][(a,b)]+=1
                counts["macro_trans"][(HEAT_MAP[a],HEAT_MAP[b])]+=1
                counts["six_trans_slot"][(h,a,b)]+=1
                counts["macro_trans_slot"][(h,HEAT_MAP[a],HEAT_MAP[b])]+=1
        if previous is not None and day!=previous["day"] and is_valid_day:
            if day_consecutive(previous["day"],day) and previous["pos"]==217 and pos==1:
                for n in BALLS:
                    a=three_previous[n];b=macro[n]
                    counts["crossday"][(a,b)]+=1
                if detailed:
                    daypair.append({"Dün":previous["day"],"Bugün":day,
                        "Geçiş":"23:57→00:02",
                        "Önceki son 20":previous["no"],"Yeni ilk 20":d["no"],
                        "Aynı 3 sınıf":sum(three_previous[n]==macro[n] for n in BALLS),
                        "Aynı 6 sınıf":sum(six_previous[n]==six[n] for n in BALLS)})
            else:
                counts["nonconsecutive_gap"]["Geçersiz doğrudan gün kıyası"]+=1
        if eligible_target:
            for n in BALLS:
                s=six[n];g=macro[n]
                counts["seats"][(s,"havuz")]+=1
                counts["seats"][(s,"çıkan")]+=int(n in ns)
                counts["macroseats"][(g,"havuz")]+=1
                counts["macroseats"][(g,"çıkan")]+=int(n in ns)
                counts["hslot"][(h,g,"havuz")]+=1
                counts["hslot"][(h,g,"çıkan")]+=int(n in ns)
                counts["number_trans"][(g,int(n in ns))]+=1
                slot_counts[(h,g)]["N"]+=1
                slot_counts[(h,g)]["Hits"]+=int(n in ns)
                daily[day]["N"]+=1
                daily[day]["Hits"]+=int(n in ns)
                daily[day][f"macro{g}"]+=int(n in ns)
                if h!="Ek":
                    j=int(h[1:])-1
                    daily_sig[day][j*3+g]+=int(n in ns)
            counts["targets"]["total"]+=1
            counts["targets"]["balls"]+=20
        if is_valid_day and h!="Ek":
            key=(day,hour)
            r=hourly[key]
            r["n"]+=1
            for n in BALLS:
                g=macro[n]
                r["paths"][n].append(g)
                r["sixpaths"][n].append(six[n])
                r["hit"][n]+=int(n in ns)
                r["macro"][(g,n)]+=1
            if h=="H12":
                # H1..H12 above: twelve 5-minute DRAW positions in this hour.
                # The next level below tracks actual chronological HOURS.
                for n in BALLS:
                    path=r["paths"][n]
                    if len(path)!=12:
                        raise AssertionError("Incomplete hourly macro path")
                    dominant=max(range(3),key=lambda g:(
                        path.count(g),int(g==path[-1]),-g))
                    old_state=last_hour_macro[n]
                    old_day=last_hour_day[n]
                    if old_state is not None and (
                        old_day==day or day_consecutive(old_day,day)
                    ):
                        counts["hour_macro_trans"][(old_state,dominant)]+=1
                        if old_day==day:
                            counts["hour_macro_same_day"][(old_state,dominant)]+=1
                        else:
                            counts["hour_macro_next_day"][(old_state,dominant)]+=1
                    last_hour_macro[n]=dominant
                    last_hour_day[n]=day
                finalize_hour(key,r)
                if forecast:
                    snapshots[key]=(tuple(six),tuple(macro),tuple(scores))
                del hourly[key]
        if eligible_target:
            # Include incomplete-day draws in EWMA memory, not in contiguous
            # evaluation-run lengths; restart runs across untested positions.
            if last_evaluated_t is not None and t-last_evaluated_t>1:
                streak=[0]*81
                prevstate=[None]*81
                six_streak=[0]*81
                six_prevstate=[None]*81
            last_evaluated_t=t
            # Streaks are transitions at pretarget state time, not sequences
            # of actual ball appearances (those are separately reported).
            for n in BALLS:
                g=macro[n]
                if g==prevstate[n]:
                    streak[n]+=1
                else:
                    if streak[n] and detailed and streak[n]>=12:
                        runrows.append({
                            "Sayı":n,"Sınıf":HEAT_MACRO[prevstate[n]],
                            "Başlangıç gün":streak_day[n],
                            "Başlangıç":streak_start[n],
                            "Bitiş":previous["dt"] if previous else "",
                            "Gerçek çekiliş boyunca kalış":streak[n],
                            "En az 1 saat":True
                        })
                    streak[n]=1
                    streak_start[n]=dt
                    streak_day[n]=day
                prevstate[n]=g
                s=six[n]
                if six_prevstate[n]==s:
                    six_streak[n]+=1
                else:
                    six_streak[n]=1
                six_prevstate[n]=s
                for threshold in (2,3,6,12,24,48,96,217):
                    if six_streak[n]==threshold:
                        counts["runs_six_threshold"][(s,threshold)]+=1
                counts["runs_observation"][(g,"pozisyon")]+=1
                for threshold in (2,3,6,12,24,48,96,217):
                    if streak[n]==threshold:
                        counts["runs_threshold"][(g,threshold)]+=1
        # Record state and actual drawn balls for exact replication.
        scores=[0.]+[scores[n]*DECAY+int(n in ns) for n in BALLS]
        six_previous=six
        three_previous=macro
        previous=d
        valid_processed+=1
        # Report completion of each REAL full day; never advance the counter
        # for an incomplete day or for a nonexistent overnight draw.
        if progress is not None and pos==217 and day in eligible:
            progress(day)
    if detailed and previous is not None:
        for n in BALLS:
            if streak[n]>=12:
                runrows.append({
                    "Sayı":n,"Sınıf":HEAT_MACRO[prevstate[n]],
                    "Başlangıç gün":streak_day[n],
                    "Başlangıç":streak_start[n],
                    "Bitiş":previous["dt"],
                    "Gerçek çekiliş boyunca kalış":streak[n],
                    "En az 1 saat":True
                })
    return {
        "counts":counts,"hourly":per_hour_rows,"runs":runrows,
        "daypair":daypair,"daily":daily,
        "daily_signature":daily_sig,"slot":slot_counts,
        "processed":valid_processed,
    }


def transition_table(observed, nulls, name,macro=True):
    count=observed["counts"][name]
    transitions=range(3) if macro else range(6)
    totals={a:sum(count[(a,b)] for b in transitions) for a in transitions}
    result=[]
    for a in transitions:
        for b in transitions:
            n=count[(a,b)]
            baselines=[v["counts"][name][(a,b)] for v in nulls]
            same=totals[a]
            null_ratios=[
                v["counts"][name][(a,b)]/
                max(1,sum(v["counts"][name][(a,j)] for j in transitions))
                for v in nulls]
            result.append({
                "Kaynak":HEAT_MACRO[a] if macro else HEAT_SIX[a],
                "Hedef":HEAT_MACRO[b] if macro else HEAT_SIX[b],
                "Aynı sınıfta kalış":a==b,
                "Gerçek geçiş":n,
                "Gerçek kaynak havuz":same,
                "Gerçek geçiş oranı %":round(n/max(1,same)*100,5),
                "RNG kontrol ortalaması %":round(mean(null_ratios)*100,5),
                "RNG fark yüzde puan":
                    round(100*(n/max(1,same)-mean(null_ratios)),5),
                "RNG min %":round(min(null_ratios)*100,5),
                "RNG max %":round(max(null_ratios)*100,5),
            })
    return result


def hslot_table(observed,nulls):
    out=[]
    for slot in ["H"+str(i) for i in range(1,13)]+["Ek"]:
        for g in range(3):
            ns=observed["counts"]["hslot"]
            pop=ns[(slot,g,"havuz")]
            hit=ns[(slot,g,"çıkan")]
            baselines=[]
            for test in nulls:
                v=test["counts"]["hslot"]
                pop0=v[(slot,g,"havuz")]
                baselines.append(v[(slot,g,"çıkan")]/pop0 if pop0 else .25)
            out.append({
                "Çekiliş içi yuva":slot,"Sınıf":HEAT_MACRO[g],
                "Gözlenen sayı hakkı":pop,
                "Gelen sayı":hit,"Hedef gelme %":round(hit/max(pop,1)*100,5),
                "RNG null ortalama %":round(mean(baselines)*100,5),
                "Adil RNG beklenen %":25,
                "RNG fark yüzde puan":round((hit/max(1,pop)-mean(baselines))*100,5),
            })
    return out


def sustained_table(obs,nulls):
    rows=[]
    for g in range(3):
        for threshold in (2,3,6,12,24,48,96,217):
            values=[v["counts"]["runs_threshold"][(g,threshold)] for v in nulls]
            rows.append({
                "Sınıf":HEAT_MACRO[g],"Aralıksız >= çekiliş":threshold,
                "Gerçek böyle uzun kalışa erişen":obs["counts"]["runs_threshold"][(g,threshold)],
                "RNG kontrol ortalama":round(mean(values),3),
                "RNG en düşük":min(values),"RNG en yüksek":max(values),
                "Not":"H1-H12 çekilişlerindeki sınıf hafızası, otomatik olarak uzun kalış oluşturabilir.",
            })
    for j in range(6):
        for threshold in (2,3,6,12,24,48,96,217):
            values=[v["counts"]["runs_six_threshold"][(j,threshold)] for v in nulls]
            rows.append({
                "Sınıf":HEAT_SIX[j],"Sınıf sistemi":"Altılı",
                "Aralıksız >= çekiliş":threshold,
                "Gerçek böyle uzun kalışa erişen":obs["counts"]["runs_six_threshold"][(j,threshold)],
                "RNG kontrol ortalama":round(mean(values),3),
                "RNG en düşük":min(values),"RNG en yüksek":max(values),
                "Not":"Altı basamakta kalış, hafıza hesabının doğal kalıcılığıyla karşılaştırılır."
            })
    return rows


def hour_12_lifecycle(hour_rows):
    """Twelve ACTUAL HOURS (not twelve five-minute draws).

    18 full draw-hours/day: 00:02, 07:02,...,23:02; 01:02
    is a solitary draw, not a 12-draw hour. For every number and every
    12-consecutive-observed-hour window within each complete day,
    record macro dwell, transitions and 12 labeled H1..H12 hour states.
    """
    hours=["00:02"]+[f"{h:02d}:02" for h in range(7,24)]
    by=defaultdict(dict)
    for r in hour_rows:
        by[(r["Tarih"],int(r["Sayı"]))][r["Saat"]]=r
    results=[]
    for (day,n),found in sorted(by.items()):
        if len(found)!=18:continue
        states=[]
        for hour in hours:
            r=found[hour]
            counts=[r["Soğukta H"],r["Ilıkta H"],r["Sıcakta H"]]
            last=HEAT_MACRO.index(r["H12 sınıf"])
            dominant=max(range(3),key=lambda g:(counts[g],int(g==last),-g))
            states.append(dominant)
        for k in range(7):
            sub=states[k:k+12]
            transitions=sum(sub[j]!=sub[j-1] for j in range(1,12))
            d={"Tarih":day,"Sayı":n,"Başlangıç saat":hours[k],
               "Bitiş saat":hours[k+11],
               "12 saatlik sıcaklık yolu":"".join(str(x+1) for x in sub),
               "H1 durum":HEAT_MACRO[sub[0]],
               "H12 durum":HEAT_MACRO[sub[-1]],
               "H1-H12 saat sınıf değişimi":transitions,
               "İlk ve son aynı":int(sub[0]==sub[-1]),
               "Saat dilimi örnekleri":"|".join(hours[k:k+12]),
               "Not":"Her H bir saatlik 12 çekiliş bloğudur; 01:02 tek çekiliştir"}
            for g,name in enumerate(HEAT_MACRO):
                current=longest=0
                for state in sub:
                    current=current+1 if state==g else 0
                    longest=max(current,longest)
                d[f"{name} saat sayısı"]=sub.count(g)
                d[f"{name} kesintisiz en fazla saat"]=longest
            for j,st in enumerate(sub,1):
                d[f"H{j} saat"]=hours[k+j-1]
                d[f"H{j} durum"]=HEAT_MACRO[st]
            results.append(d)
    return results


def day_similarity(profiles):
    """Correlation of centered 12-position x 3-class seat signatures.
    Adjacent only if both *calendar* days observed in full.
    Compare against all pairs at least 2 days apart, no cherry-picking.
    """
    # Each H label occurs in 18 actual hours per complete day, not once.
    # Center by 18*20*poolshare; otherwise near-constant base counts
    # produce a spurious ~0.995 same-day 'correlation' for all day pairs.
    sig=profiles["daily_signature"]
    keys=sorted(d for d in sig if profiles["daily"][d]["N"]==217*80)
    pairs=[]
    for i,da in enumerate(keys):
        a=[x-(18*20*[26/80,28/80,26/80][j%3]) for j,x in enumerate(sig[da])]
        for db in keys[i+1:]:
            b=[x-(18*20*[26/80,28/80,26/80][j%3]) for j,x in enumerate(sig[db])]
            n=math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
            if not n:continue
            pear=sum(x*y for x,y in zip(a,b))/n
            lag=(date.fromisoformat(db)-date.fromisoformat(da)).days
            pairs.append((lag,da,db,pear))
    adjacent=[r[3] for r in pairs if r[0]==1]
    other=[r[3] for r in pairs if r[0]>=2]
    return {
        "Ardışık gün çiftleri":len(adjacent),
        "Ardışık gün ortalama benzerlik":round(mean(adjacent),6) if adjacent else "",
        "Arada 2+ gün olan çift":len(other),
        "Arada 2+ gün ortalama benzerlik":round(mean(other),6) if other else "",
        "Komşu eksi diğer":round(mean(adjacent)-mean(other),6) if adjacent and other else "",
    },[{
        "Dün":da,"Bugün":db,"Aradaki takvim günü":lag,
        "20 koltuğun 36 elemanlı profiline benzerlik":round(sim,6),
        "Gerçek ardışık gün":lag==1,
    } for lag,da,db,sim in pairs if lag==1]


def extract_hourly_6to6_probes(obs):
    """From detailed number-hour timelines find H1-H6 to H7-H12
    descriptive patterns. These are NOT future success forecasts."""
    grouped=defaultdict(lambda:Counter())
    for row in obs["hourly"]:
        p=[int(x) for x in row["H1..H12 makro yolları"]]
        if len(p)!=12:raise AssertionError("12 Hs")
        prefix=p[:6];future=p[6:]
        transitions=sum(prefix[i]!=prefix[i-1] for i in range(1,6))
        start=prefix[-1]
        group=("H1-H6 sabit" if transitions==0 else
               "H1-H6 1-2 dönüş" if transitions<=2 else "H1-H6 3+ dönüş")
        xx=grouped[(HEAT_MACRO[start-1],group)]
        xx["n"]+=1
        xx["H7-H12 aynı durum"]+=sum(x==start for x in future)
        xx["H7-H12 toplam"]+=6
        xx["H7-H12 son durum aynı"]+=int(future[-1]==start)
        xx["H7-H12 hiç sınıf değişmedi"]+=int(all(x==start for x in future))
        xx["H7-H12 toplam çıkış"]+=row["Bu saat çıkan çekiliş"] # descriptive total over 12, not predictive.
    return [{
        "H6 durumu":state,"İlk 6 hareket":label,
        "80 sayı-saat":v["n"],
        "H7-H12 kalış hak":v["H7-H12 toplam"],
        "H7-H12 aynı sınıfta kaldığı pozisyon":v["H7-H12 aynı durum"],
        "H7-H12 aynı durum %":round(100*v["H7-H12 aynı durum"]/v["H7-H12 toplam"],4),
        "H12 aynı durumda":v["H7-H12 son durum aynı"],
        "H7-H12 hiç değişmedi":v["H7-H12 hiç sınıf değişmedi"],
    } for (state,label),v in sorted(grouped.items())]


def get_pre(targets, half_life=12):
    """Leakage-proof score-state snapshots at cutoff H6 and targets H7-H12.
    Train 6-state x trend rates from first 36 days, test last 36.
    Returns forecast samples per hour with features computed before H7.
    """
    ordered=sorted(targets,key=lambda d:(d["day"],d["pos"]))
    e=[0.]*81
    prevsix=None
    trend=[1]*81
    out=[]
    history_size=0
    byday=defaultdict(dict)
    for d in ordered:byday[d["day"]][d["pos"]]=d
    complete={k:v for k,v in byday.items() if len(v)==217}
    cutoff_feat={}
    for d in ordered:
        six,macro=state_before(e)
        if d["day"] in complete and d["pos"] in (6,)+tuple(19+12*h for h in range(17)):
            # H6 slot is within 12-draw hour: positions 6, 19, 31...211.
            # score BEFORE H6 observation; compute snapshot AFTER H6 below.
            pass
        ns=set(d["nums"])
        e=[0.]+[e[n]*DECAY+int(n in ns) for n in BALLS]
        if d["day"] in complete and d["pos"] in (6,)+tuple(19+12*h for h in range(17)):
            after6,three6=state_before(e)
            before6=six
            cut=d["pos"]
            hour="00:02" if cut==6 else f"{7+(cut-19)//12:02d}:02"
            cutoff_feat[(d["day"],hour)]=(tuple(after6),tuple(before6),tuple(e))
    for day,records in sorted(complete.items()):
        for start in HOUR_STARTS:
            hour="00:02" if start==1 else f"{7+(start-14)//12:02d}:02"
            vals=cutoff_feat.get((day,hour))
            if not vals:continue
            aft,before,score=vals
            target=[records[j] for j in range(start+6,start+12)]
            for n in BALLS:
                s=aft[n];prev=before[n]
                hits=sum(n in d["nums"] for d in target)
                out.append({
                    "Tarih":day,"Saat":hour,"Sayı":n,
                    "H6 sonrası durum":s,"H6 değişim":prev*6+s,
                    "Sonraki 6 görünüş":hits,
                    "H6 sıcaklık puanı":score[n],
                })
    return out


def test_forecast(raw_draws, phases):
    """Freeze a 20-number choice at H6, train only first36 outcome rates.

    Compare: 6-temperature+H6 transition empirical-Bayes model,
    hottest-20, coldest-20, exact uniform random20. 6 targets every hour.
    Nested 36days/36days, no hindsight. 0/20..20/20 histograms.
    """
    valid=[d for d in raw_draws if d["day"] in phases]
    examples=get_pre(raw_draws)
    train=[e for e in examples if phases.get(e["Tarih"])=="Öğrenme"]
    test=[e for e in examples if phases.get(e["Tarih"])=="Test"]
    cell=defaultdict(lambda:Counter())
    for e in train:
        c=cell[(e["H6 sonrası durum"],e["H6 değişim"])]
        c["n"]+=6;c["hits"]+=e["Sonraki 6 görünüş"]
    rates={k:(v["hits"]+.25*PRIOR)/(v["n"]+PRIOR) for k,v in cell.items()}
    byhour=defaultdict(list)
    for e in test:byhour[(e["Tarih"],e["Saat"])].append(e)
    byday=defaultdict(dict)
    for d in raw_draws:byday[d["day"]][d["pos"]]=d
    events=[]
    for (day,hour),items in sorted(byhour.items()):
        if len(items)!=80:raise AssertionError("Incomplete 80-ball H6 snapshot")
        start=1 if hour=="00:02" else 14+12*(int(hour[:2])-7)
        future=[byday[day][p] for p in range(start+6,start+12)]
        model=tuple(sorted(items,key=lambda e:(
            -rates.get((e["H6 sonrası durum"],e["H6 değişim"]),.25),
            -e["H6 sıcaklık puanı"],e["Sayı"]))[:20])
        hot=tuple(sorted(items,key=lambda e:(-e["H6 sıcaklık puanı"],e["Sayı"]))[:20])
        cold=tuple(sorted(items,key=lambda e:(e["H6 sıcaklık puanı"],e["Sayı"]))[:20])
        rng=random.Random(int(day.replace("-",""))*1987+start*89)
        rand=tuple({"Sayı":n} for n in rng.sample(BALLS,20))
        for label,pick in (("Döngü/H6",model),("En sıcak20",hot),
                           ("En soğuk20",cold),("Rastgele20",rand)):
            ns=tuple(x["Sayı"] for x in pick)
            matches=[sum(n in d["nums"] for n in ns) for d in future]
            events.append({
                "Tarih":day,"Saat":hour,"Yöntem":label,
                "20 sayı":"-".join(f"{n:02d}" for n in sorted(ns)),
                "H7":matches[0],"H8":matches[1],"H9":matches[2],
                "H10":matches[3],"H11":matches[4],"H12":matches[5],
                "6 hedef toplam":sum(matches),
                "En yüksek aynı çekilişte":max(matches),
                "6+ hedef":sum(x>=6 for x in matches),
                "7+ hedef":sum(x>=7 for x in matches),
                "8+ hedef":sum(x>=8 for x in matches),
                "10+ hedef":sum(x>=10 for x in matches),
            })
    bymethod=defaultdict(list)
    for row in events:bymethod[row["Yöntem"]].append(row)
    summary=[]
    for name,rr in sorted(bymethod.items()):
        hits=Counter()
        for row in rr:
            for h in range(7,13):hits[row[f"H{h}"]]+=1
        total=len(rr)*6
        summary.append({
            "Yöntem":name,"10/20 türünden tahmin":len(rr),
            "Hedef çekiliş":total,
            "Toplam doğru sayı":sum(k*v for k,v in hits.items()),
            "Çekiliş başına 20 sayıdan doğru":round(sum(k*v for k,v in hits.items())/total,6),
            "RNG adil beklenti":5.,
            "6+":sum(v for k,v in hits.items() if k>=6),
            "7+":sum(v for k,v in hits.items() if k>=7),
            "8+":sum(v for k,v in hits.items() if k>=8),
            "10+":sum(v for k,v in hits.items() if k>=10),
            **{f"{k}/20":hits[k] for k in range(21)},
        })
    pairs=defaultdict(dict)
    for r in events:pairs[(r["Tarih"],r["Saat"])][r["Yöntem"]]=r
    perday=defaultdict(list)
    for (day,hour),x in pairs.items():
        if len(x)!=4:raise AssertionError("Each 20-ball model must align")
        perday[day].append((x["Döngü/H6"]["6 hedef toplam"]-x["Rastgele20"]["6 hedef toplam"])/6)
    vals=[mean(xx) for xx in perday.values()]
    m=mean(vals)
    se=(sum((x-m)**2 for x in vals)/(len(vals)-1)/len(vals))**.5
    return summary,events,[{
        "Sınama":"Son36","Karşılaştırma":"Döngü/H6 - Rastgele20",
        "Gün":len(vals),"Fark isabet/20":round(m,6),
        "Yaklaşık %95 GA alt":round(m-1.96*se,6),
        "Yaklaşık %95 GA üst":round(m+1.96*se,6),
        "Güvenilir üstünlük":m-1.96*se>0,
    }]


def run(raw_text, rng_reps=RNG_REPS, detailed=True, progress=None):
    draws,errors=read_draws(raw_text)
    full,incomplete=group_full_days(draws)
    phase=ordered_phases(full)
    # Restrict reference dates to 72 full days but include preceding observed
    # valid incomplete-day data as historical context.
    last_day=sorted(phase)[-1]
    before=[d for d in draws if d["day"]<=last_day]
    # One continuous run. Progress callback is optional and only called from
    # inside a real Streamlit user interaction; command-line works unchanged.
    phase_days=set(phase)
    finished=[0]
    total=len(phase_days)*(rng_reps+1)+4
    def advance(stage,day=""):
        finished[0]+=1
        if progress is not None:
            progress(finished[0],total,stage,day)
    if progress is not None:
        progress(0,total,"Analiz hazırlanıyor","")
    # Comparisons only on same full days and after first144 observed draws.
    observed=profile(before,phase_days,detailed=detailed,
                     progress=lambda day:advance("Gerçek veri",day))
    null=[]
    for i in range(rng_reps):
        null.append(profile(make_cache(before,seed=284011+i*99173),
                            phase_days,detailed=False,
                            progress=lambda day,i=i:advance(
                                f"RNG kontrol {i+1}/{rng_reps}",day)))
        print("V28_NULL",i+1,"/",rng_reps,flush=True)
    advance("RNG kontrolleri tamamlandı")
    macro=transition_table(observed,null,"macro_trans",True)
    six=transition_table(observed,null,"six_trans",False)
    hour_macro=transition_table(observed,null,"hour_macro_trans",True)
    hour_macro_days=transition_table(observed,null,"hour_macro_same_day",True)
    rolling_hour=hour_12_lifecycle(observed["hourly"]) if detailed else []
    h=hslot_table(observed,null)
    durations=sustained_table(observed,null)
    sim,adjacent=day_similarity(observed)
    nullsimilarities=[day_similarity(x)[0] for x in null]
    obs_gap=sim["Komşu eksi diğer"]
    null_gap=[z["Komşu eksi diğer"] for z in nullsimilarities if isinstance(z["Komşu eksi diğer"],float)]
    sim["RNG ortalama komşu eksi diğer"]=round(mean(null_gap),6)
    sim["6 RNG tekrar min fark"]=round(min(null_gap),6)
    sim["6 RNG tekrar max fark"]=round(max(null_gap),6)
    sim["RNG dışına çıktı mı (kesin kanıt değil)"]=(obs_gap<min(null_gap) or obs_gap>max(null_gap)) if isinstance(obs_gap,float) else False
    long=extract_hourly_6to6_probes(observed)
    advance("Sıcaklık / koltuk / saatlik geçişler tamamlandı")
    forecast,forecast_detail,forecast_ci=test_forecast(before,phase)
    advance("20 sayı ileriye dönük test tamamlandı")
    if len(observed["hourly"])!=72*18*80:raise AssertionError("Missing H1..H12 daily profiles")
    if sum(v["counts"]["targets"]["total"] for v in null)==0:raise AssertionError("No null targets")
    if len(forecast_detail)!=36*18*4:raise AssertionError("Expected 36 days *18 hours*4 coupon methods")
    if sum(z["Gerçek geçiş"] for z in macro)!=sum(observed["counts"]["macro_trans"].values()):
        raise AssertionError("Transition table lost edges")
    step_rows=[]
    for slot in ["H"+str(i) for i in range(1,13)]+["Ek"]:
        for g in range(3):
            for after in range(3):
                key=(slot,g,after)
                value=observed["counts"]["macro_trans_slot"][key]
                nullvals=[x["counts"]["macro_trans_slot"][key] for x in null]
                step_rows.append({
                    "H":slot,"Önce":HEAT_MACRO[g],"Sonra":HEAT_MACRO[after],
                    "Gerçek geçiş":value,
                    "RNG ortalama geçiş":round(mean(nullvals),3),
                    "RNG min":min(nullvals),"RNG max":max(nullvals)
                })
    meta={
        "Motor":"V28 Dijital Kaplan sıcaklık yaşam döngüsü, H1–H12, ertesi gün",
        "Tam gün":len(phase),
        "Valid kaydedilmiş çekiliş":len(before),
        "Gerçek hedef çekiliş":observed["counts"]["targets"]["total"],
        "Saat":72*18,"Saat içi 80 sayı profili":len(observed["hourly"]),
        "12 gerçek saatlik 80 sayı profili":len(rolling_hour),
        "H1..H12 çekiliş düzeyi":"Bir GERÇEK saat içindeki sıralı on iki çekiliş (5 dakika aralık)",
        "H1..H12 saat düzeyi":"Ayrı 12 saatlik kaydırmalı pencereler, 00:02+07:02..23:02 içindeki 18 gerçek saat bloğundan 12 tanesi, 01:02 tek çekiliş ayrı",
        "01:02":"Ayrı 13. tek gece çekilişi, H13 gibi etiketlenmez",
        "Günler":"Gece 23:57→00:02 sadece takvimde arka arkaya tam günlerde çapraz gün kıyası",
        "Döngü tanımı":"ÖNCE görülen sıcaklık etiketinin yeni çekiliş öncesindeki etiketle 3x3 ve 6x6 geçişi",
        "Isı":"Geçmiş bütün geçerli çekilişlerin gün aşan EWMA'sı, 12 çekiliş yarı ömür, günlük reset yok",
        "Altı grup":list(HEAT_SIX),"Altı grup boyut":list(SIX_SIZES),
        "Üç ana sınıf":list(HEAT_MACRO),"Ana sınıf boyut":[26,28,26],
        "RNG tekrarı":rng_reps,
        "RNG benzetimi":"Her geçmiş takvim çekilişi için sabit tohumlu bağımsız uniform 20/80; aynı saatler ve aynı sıcaklık hesabı",
        "Eğitim":[sorted(phase)[0],sorted(phase)[35]],
        "Test":[sorted(phase)[36],sorted(phase)[-1]],
        "Öngörü koşulu":"Saatin 6. çekilişi tamamlandığında 20 sayı dondurulur; H7-H12 hiç görülmeden 6 çekilişte skor hesaplanır",
        "Öngörü notu":"36 gün hücre olasılığı kalibrasyonu; 36 gün dondurulmuş model; rastgele20 ve sıcak20/soğuk20 kontrolleri",
        "Ardışık gün benzerliği":sim,
        "Veri hatası":errors,"Eksik günler":incomplete,
        "Önemli":"Kalma süreleri 12 yarı ömürlü yumuşatıcıdan mekanik olarak doğabilir; null karşılaştırması olmadan RNG döngüsü kanıtı DEĞİLDİR.",
    }
    reports={
        "ozet.json":json.dumps(meta,ensure_ascii=False,indent=2).encode("utf-8"),
        "3x3_soguk_ilik_sicak_tum_gecisler.csv":csv_bytes(macro),
        "6x6_alti_sicaklik_tum_gecisler.csv":csv_bytes(six),
        "H1_H12_saat_ici_gecisler.csv":csv_bytes(step_rows),
        "H1_H12_koltuk_gercek20.csv":csv_bytes(h),
        "saatten_saate_3x3_sicaklik_gecisleri_RNG.csv":csv_bytes(hour_macro),
        "sadece_aynigun_saatten_saate_gecis_RNG.csv":csv_bytes(hour_macro_days),
        "her_sayi_12_gercek_saat_H1_H12_yolculuk.csv":csv_bytes(rolling_hour) if detailed else b"",
        "kalma_sureleri_RNG_karsilastirma.csv":csv_bytes(durations),
        "her_sayi_her_saat_H1_H12_yolculuk.csv":csv_bytes(observed["hourly"]) if detailed else b"",
        "12_ve_uzeri_ardisik_sinif_kalislari.csv":csv_bytes(observed["runs"]) if detailed else b"",
        "gunler_arasi_kimlik_tasima.csv":csv_bytes(observed["daypair"]),
        "gunluk_profil_benzerligi.csv":csv_bytes(adjacent),
        "saat_H1_H6_son6_yolculuk.csv":csv_bytes(long),
        "36gun_H6_kilitli_20_sayi_karsi_test.csv":csv_bytes(forecast),
        "36gun_butun_saatler_H7_H12_isabetleri.csv":csv_bytes(forecast_detail),
        "36gun_gunluk_guven_araligi.csv":csv_bytes(forecast_ci),
    }
    advance("ZIP için tüm raporlar oluşturuldu")
    return reports,meta,macro,durations,forecast,forecast_ci


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data",default="veri.txt")
    ap.add_argument("--output",default="V28_DIJITAL_KAPLAN_72_GUN_DONGU_ANALIZ.zip")
    ap.add_argument("--null",type=int,default=RNG_REPS)
    args=ap.parse_args()
    report,meta,macro,duration,forecast,ci=run(
        Path(args.data).read_text(encoding="utf-8-sig"),args.null)
    with zipfile.ZipFile(args.output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name,blob in report.items():archive.writestr(name,blob)
    print("V28_PASS",json.dumps({x:meta[x] for x in (
        "Tam gün","Gerçek hedef çekiliş","Saat","Saat içi 80 sayı profili",
        "RNG tekrarı")},ensure_ascii=False),flush=True)
    print("V28_DAY_CYCLE",json.dumps(meta["Ardışık gün benzerliği"],ensure_ascii=False),flush=True)
    for x in macro:print("V28_MACRO",json.dumps(x,ensure_ascii=False),flush=True)
    for x in forecast:print("V28_TICKET",json.dumps(x,ensure_ascii=False),flush=True)
    for x in ci:print("V28_CI",json.dumps(x,ensure_ascii=False),flush=True)
    print("V28_ZIP",args.output,flush=True)


if __name__=="__main__":
    main()
