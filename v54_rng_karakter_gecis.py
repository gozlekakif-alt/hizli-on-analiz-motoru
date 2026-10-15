#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V54: RNG character transitions, hour-to-hour family 'mutation',
fair 20/80 simulated days, and no-lookahead first6 -> next6 audit.

This does not reverse-engineer the lottery RNG. Null simulation draws
20 distinct numbers uniformly and independently from 1..80. All historical
findings remain retrospective. Forward audit begins 2026-10-16.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import math
import random
import statistics
import zipfile
from datetime import date
from pathlib import Path

from v45_sinyal_kor_test import parse_draws, SLOTS
from v53_saatlik_degisen_aileler import BLOCKS, hour_families

COLDS = ("SOGUK","SERIN","NOTR","ILIK","SICAK")
SIZES = (3,4,5)
TOP_N = 12
START_FUTURE = date(2026,10,16)   # independent audit begins AFTER V54 was defined
N_FUTURE_DAYS = 14
MODEL_NAMES = ("SICAK72_10","SOGUK72_10","YUKSELEN12_10","ILK6_SICAK10","ESLIKCI_GECIS10","RASTGELE10")
BASELINE_PER_NUMBER = 10/80*20   # 2.5 expected hits for each 10-number coupon
SIMULATIONS_DEFAULT = 80

def frozen_random(day, bcode):
    digest=hashlib.sha256(f"V54|2026-10-15|{day}|{bcode}|RNG".encode()).hexdigest()
    return tuple(sorted(random.Random(int(digest[:24],16)).sample(range(1,81),10)))

def snapshot(history):
    """80-number state derived exclusively from existing previous draws."""
    past=history[-72:]
    last12=past[-12:]
    prev12=past[-24:-12]
    count=collections.Counter(n for r in past for n in r["nums"])
    count12=collections.Counter(n for r in last12 for n in r["nums"])
    countprev=collections.Counter(n for r in prev12 for n in r["nums"])
    gaps={}
    for n in range(1,81):
        gaps[n]=next((ix for ix,r in enumerate(reversed(past)) if n in r["nums"]),len(past))
    ordered=sorted(range(1,81),key=lambda n:(count[n],n))
    bucket={}
    for ix,n in enumerate(ordered):
        bucket[n]=COLDS[ix//16]
    return {n:{"count72":count[n], "last12":count12[n],"prev12":countprev[n],
                "slope12":count12[n]-countprev[n],"gap":gaps[n],
                "state":bucket[n],"direction":("YUKARI" if count12[n]>countprev[n]
                else "ASAGI" if count12[n]<countprev[n] else "SABIT")}
            for n in range(1,81)}

def build_tickets(history, first6, day, hour):
    """Every ticket frozen immediately after first six results; target unseen."""
    past=history[-72:]
    known=history+first6
    states=snapshot(known)
    hour_freq=collections.Counter(n for r in first6 for n in r["nums"])
    anchors=tuple(sorted(range(1,81),key=lambda n:(-hour_freq[n],n))[:3])
    co=collections.Counter()
    anchor_set=set(anchors)
    for r in past:
        shared=len(set(r["nums"]) & anchor_set)
        if shared:
            for n in r["nums"]:
                co[n]+=shared
    # Sorting only uses history and the first six draws, never targets.
    return {
      "SICAK72_10":tuple(sorted(sorted(range(1,81),
          key=lambda n:(-states[n]["count72"],n))[:10])),
      "SOGUK72_10":tuple(sorted(sorted(range(1,81),
          key=lambda n:(states[n]["count72"],n))[:10])),
      "YUKSELEN12_10":tuple(sorted(sorted(range(1,81),
          key=lambda n:(-states[n]["slope12"],-states[n]["count72"],n))[:10])),
      "ILK6_SICAK10":tuple(sorted(sorted(range(1,81),
          key=lambda n:(-hour_freq[n],-states[n]["count72"],n))[:10])),
      "ESLIKCI_GECIS10":tuple(sorted(sorted(range(1,81),
          key=lambda n:(-co[n],-hour_freq[n],n))[:10])),
      "RASTGELE10":frozen_random(day,hour)
    }

def score_day(day,day_rows,prior_history,scope):
    """17 daytime + 1 nighttime hour. Only targets 7..12 score.
    H00 has 13th draw deliberately excluded from scoring but retained in history.
    """
    bypos={ix+1:r for ix,r in enumerate(day_rows)}
    history=list(prior_history)
    audit=[]
    for b in BLOCKS:
        rows=[bypos[i] for i in range(b["start"],b["end"]+1)]
        first6=rows[:6]
        ticket=build_tickets(history,first6,str(day),b["code"])
        for target in rows[6:12]:
            number=target["nums"]
            for model,pick in ticket.items():
                n=len(number.intersection(pick))
                audit.append({"set":scope,"day":str(day),"hour":b["code"],
                    "target_id":target["id"],"target_time":target["time"],
                    "model":model,"coupon":"-".join(map(str,pick)),"hits":n,
                    "hit8":int(n>=8),"hit7":int(n>=7)})
        history.extend(rows)
    return audit,history

def walkforward(full):
    """Historical halves + future chronological audit, no cross-day leakage."""
    historic=sorted(d for d in full if d<START_FUTURE)
    known=[]
    predictions=[]
    for day in sorted(full):
        subset=("ILK_YARI" if day in historic[:len(historic)//2] else
                "SON_YARI" if day<START_FUTURE else "ILERI")
        audit,history=score_day(day,full[day],known[-72:],subset)
        if day>=START_FUTURE and day not in sorted(d for d in full if d>=START_FUTURE)[:N_FUTURE_DAYS]:
            # Future beyond fixed first 14 completed full days is excluded
            continue
        predictions.extend(audit)
        known=history
    return predictions

def walk_summary(audit):
    grouped=collections.defaultdict(list)
    for row in audit:grouped[(row["set"],row["model"])].append(row)
    output=[]
    for (group,model),rows in sorted(grouped.items()):
        obs=[x["hits"] for x in rows]
        output.append({"period":group,"model":model,"targets":len(obs),
                       "mean":round(statistics.mean(obs),5),
                       "expected_mean":BASELINE_PER_NUMBER,
                       "hits_7plus":sum(x>=7 for x in obs),
                       "hits_8plus":sum(x>=8 for x in obs),
                       "hits_9plus":sum(x>=9 for x in obs),
                       "hits_10":sum(x==10 for x in obs)})
    return output

def simulate_day(seed):
    rng=random.Random(seed)
    return [{"id":700_000+i,"day":"SIM","time":t,
             "nums":frozenset(rng.sample(range(1,81),20))}
             for i,t in enumerate(SLOTS)]

def hour_leaders(day_rows):
    """Only 12 highest-support families per hour and size, not millions of subsets."""
    hours={}
    for b in BLOCKS:
        subset=day_rows[b["start"]-1:b["end"]]
        found,complete=hour_families(subset,k_sizes=SIZES)
        if not complete:
            raise ValueError("Hourly family detection truncated: "+b["code"])
        hours[b["code"]]={
            k:sorted(found.get(k,{}).items(),key=lambda p:(-p[1],p[0]))[:TOP_N]
            for k in SIZES}
    return hours

def family_transitions(leader_hours, day, detail=True):
    counts=collections.Counter()
    rows=[]
    for before,after in zip(BLOCKS,BLOCKS[1:]):
        h1,h2=before["code"],after["code"]
        for k in SIZES:
            earlier=leader_hours[h1][k]
            later=leader_hours[h2][k]
            later_dict=dict(later)
            # Fast mutation candidate index: (k-1)-sized partial-family signature
            index=collections.defaultdict(list)
            for nums,support in later:
                for chunk in __import__("itertools").combinations(nums,k-1):
                    index[chunk].append((nums,support))
            for family,support in earlier:
                if family in later_dict:
                    label="AYNI_AILE_DEVAM"
                    dest=family
                    next_support=later_dict[family]
                else:
                    choices=[]
                    for chunk in __import__("itertools").combinations(family,k-1):
                        choices.extend((f,n) for f,n in index[chunk] if f!=family)
                    if choices:
                        dest,next_support=min(choices,key=lambda t:(-t[1],t[0]))
                        label="BIR_SAYI_DEGISTI"
                    else:
                        label="LIDER_LISTESINDEN_CIKTI"
                        dest=()
                        next_support=0
                counts[(k,label)]+=1
                if detail:
                    rows.append({"day":str(day),"from":h1,"to":h2,"family_size":k,
                      "old_family":"-".join(map(str,family)),
                      "new_family":"-".join(map(str,dest)),
                      "old_support":support,"next_support":next_support,
                      "status":label,
                      "overnight_gap":int(h1=="H00" and h2=="H07")})
    return counts,rows

def daily_family_compare(day_rows,next_rows,day1,day2):
    """Top leaders from last available hour versus next day's same first hour.
    Day boundary is not a 5-minute time gap. Descriptive only.
    """
    h1=hour_leaders(day_rows)
    h2=hour_leaders(next_rows)
    out=[]
    for k in SIZES:
        for family,support in h1["H23"][k]:
            next_set={tuple(f):n for f,n in h2["H00"][k]}
            continuation=family in next_set
            # Actual target day appearances, not forecast
            actual=sum(set(family).issubset(draw["nums"]) for draw in next_rows)
            out.append({"origin_day":str(day1),"next_day":str(day2),
                 "size":k,"family":"-".join(map(str,family)),
                 "H23_support":support,"next_H00_same_top":int(continuation),
                 "next_day_actual_occurrences":actual})
    return out

def monte_carlo(real_counts,n_sims=SIMULATIONS_DEFAULT):
    """Matched fair-independent RNG null, same 217 slots, same TOP12 ranking."""
    metrics=[(k,typ) for k in SIZES
             for typ in ("AYNI_AILE_DEVAM","BIR_SAYI_DEGISTI","LIDER_LISTESINDEN_CIKTI")]
    samples={key:[] for key in metrics}
    for idx in range(n_sims):
        fake=simulate_day(540015+idx)
        leaders=hour_leaders(fake)
        counts,_=family_transitions(leaders,"RNG",detail=False)
        for key in metrics:samples[key].append(counts[key])
    output=[]
    for key in metrics:
        values=sorted(samples[key])
        observed=real_counts[key]
        # Directional upper-tail empirical p with +1 correction;
        # exploratory, no post-hoc confidence claim.
        p=(1+sum(x>=observed for x in values))/(n_sims+1)
        output.append({"size":key[0],"kind":key[1],"observed":observed,
          "rng_average":round(statistics.mean(values),3),
          "rng_median":statistics.median(values),
          "rng_q05":values[max(0,math.floor(0.05*(len(values)-1)))],
          "rng_q95":values[min(len(values)-1,math.ceil(0.95*(len(values)-1)))],
          "rng_upper_tail_p_exploratory":round(p,5),"simulations":n_sims})
    return output

def _write(z,name,cols,records):
    with z.open(name,"w",force_zip64=True) as raw:
        txt=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        wr=csv.writer(txt)
        wr.writerow(cols)
        for r in records:
            wr.writerow([r.get(col,"") for col in cols] if isinstance(r,dict) else r)
        txt.flush()
        txt.detach()

def analyze(full,selected=None,n_sims=SIMULATIONS_DEFAULT):
    if not full:raise ValueError("At least one full 217-draw day is required")
    ordered=sorted(full)
    selected=selected or ordered[-1]
    if selected not in full:raise ValueError("Requested complete day missing")
    leading=hour_leaders(full[selected])
    actual,changes=family_transitions(leading,selected)
    sims=monte_carlo(actual,n_sims)
    audit=walkforward(full)
    before_days=[d for d in ordered if d<selected]
    prior=next((d for d in reversed(before_days) if (selected-d).days==1),None)
    day_compare=daily_family_compare(full[prior],full[selected],prior,selected) if prior else []
    trajectories=[]
    past=[]
    for day in ordered:
        if day>=selected:break
        past.extend(full[day])
    history=past[-72:]
    flows=collections.Counter()
    for r in full[selected]:
        previous=snapshot(history)
        history.append(r)
        afterwards=snapshot(history)
        for n in range(1,81):
            pre,post=previous[n],afterwards[n]
            flows[(pre["state"],post["state"])]+=1
            trajectories.append({
                "day":str(selected),"slot":SLOTS.index(r["time"])+1,
                "draw_no":r["id"],"time":r["time"],"number":n,
                "drawn":int(n in r["nums"]),
                "before72":pre["count72"],"after72":post["count72"],
                "before_state":pre["state"],"after_state":post["state"],
                "before_direction":pre["direction"],
                "after_direction":post["direction"],"gap_before":pre["gap"]})
    hour_report=[]
    for hour in BLOCKS:
        for k in SIZES:
            for place,(family,support) in enumerate(leading[hour["code"]][k],1):
                hour_report.append({"day":str(selected),"hour":hour["code"],
                                   "period":hour["name"],"size":k,
                                   "rank":place,"family":"-".join(map(str,family)),
                                   "within_hour_together":support})
    state_moves=[{"before":a,"after":b,"count":flows[(a,b)]}
                 for a in COLDS for b in COLDS]
    return {"selected":selected,"leaders":hour_report,"change_details":changes,
            "null":sims,"audit":audit,"audit_summary":walk_summary(audit),
            "trajectory":trajectories,"state_moves":state_moves,
            "day_compare":day_compare,
            "meta":{
                "selected":str(selected),"observed_days":len(full),
                "selected_draws":len(full[selected]),
                "simulation_days":n_sims,
                "prospective_start":str(START_FUTURE),
                "new_full_days":len([d for d in full if d>=START_FUTURE][:N_FUTURE_DAYS]),
                "null":"independent uniformly chosen 20/80, same 217 slots",
                "historical_findings_are_descriptive":True,
                "audit_targets":len(audit)//len(MODEL_NAMES),
                "selected_hourly_leaders":len(hour_report),
                "same_draw_only":True,
            }}

def build_zip(result):
    blob=io.BytesIO()
    m=result["meta"]
    with zipfile.ZipFile(blob,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        top=["V54 — RNG KARAKTER GECIS + AILE DONUSUMU + KOR SAAT YARISI TESTI",
            f"Secilen gün {m['selected']}, tam çekiliş 217/217, geçmiş tam gün {m['observed_days']}",
            f"RNG karsilastirmasi: {m['simulation_days']} bağımsız sanal gün",
            "Sayi kimligi: hareketli son 72 çekilişte sıcaklık 5x16 rank ve son12/önceki12 yönü.",
            "Saatlik aile: 3/4/5'li bir küme en az iki AYNI çekiliş kadrosunda görülür.",
            "Her saatin güçlü ilk 12 ailesi, sonraki saatin ilk 12'siyle karşılaştırılır.",
            "AILE DEVAM: tam ayni; BIR SAYI DEGISTI: k-1 ortak, 1 farkli;",
            "LIDER LISTESINDEN CIKTI: sonraki saat liderleri içinde aynı veya tek değişmiş aile yok.",
            "H00 00:02–01:02 (13 çekiliş); H07..H23 12'şer çekiliş. İlk saat-gece geçişi 6 saat boştur.",
            "Her saat ilk6 sonrası 6 hedef: seçilen 10'lu kuponlar HEDEFLERİ GÖRMEDEN dondurulur.",
            "H00 13. çekiliş tahmine dahil değil, geçmişe dahil. Adil 10'lu ortalama 2.5/10.",
            f"Yeni ileri test 16.10.2026 ve sonrası ilk {N_FUTURE_DAYS} TAM gün; şu anda {m['new_full_days']}/{N_FUTURE_DAYS}.",
            "Geçmişte taranan model sonuçları bağımsız ileri doğrulama DEĞİLDİR.",
            "Aile liderlerinin güçlü görünmesi mutlaka önceden seçilmiş etkili sinyal değildir.",
            "Simülasyon istatistikleri sadece seçili günün saatlik aile sayısını test eder.",
            "Simülasyonlar p-değeri sınamasının nihai kanıtı değil, exploratif kontrolüdür.",
            "",
            "MODELLERIN GERİYE DÖNÜK YARI SAAT SONUCU"]
        for r in result["audit_summary"]:
            top.append(f"{r['period']} {r['model']}: {r['targets']} hedef, "
                       f"ortalama {r['mean']:.4f}/10, beklenti 2.5, >=7 {r['hits_7plus']}")
        top+=["","GERCEK + BAGIMSIZ RNG AILE DONUSUMU"]
        for r in result["null"]:
            top.append(f"{r['size']}'li {r['kind']}: gozlenen {r['observed']}, "
                f"sanal ortalama {r['rng_average']}, [5%,95%]={r['rng_q05']}-{r['rng_q95']}, "
                f"aciklayici üst-kuyruk p={r['rng_upper_tail_p_exploratory']}")
        z.writestr("00_TEK_SAYFA_BULGULAR.txt","\n".join(top)+"\n")
        payload=[
          ("01_80_SAYI_217_KARAKTER_YOLU.csv",("day","slot","draw_no","time","number",
             "drawn","before72","after72","before_state","after_state",
             "before_direction","after_direction","gap_before"),result["trajectory"]),
          ("02_SICAKLIK_GECIS_MATRISI.csv",("before","after","count"),result["state_moves"]),
          ("03_18_SAAT_AILE_LIDERLERI.csv",("day","hour","period","size","rank","family",
             "within_hour_together"),result["leaders"]),
          ("04_SAATTEN_SAATE_AILE_DONUSUMU.csv",("day","from","to","family_size",
             "old_family","new_family","old_support","next_support","status",
             "overnight_gap"),result["change_details"]),
          ("05_GERCEK_RNG_217_GUN_AILE_KARSILASTIR.csv",("size","kind","observed",
             "rng_average","rng_median","rng_q05","rng_q95","rng_upper_tail_p_exploratory",
             "simulations"),result["null"]),
          ("06_ILK6_SON6_KOR_HEDEF_TESTI.csv",("set","day","hour","target_id",
             "target_time","model","coupon","hits","hit8","hit7"),result["audit"]),
          ("07_ILK6_SON6_MODELLER_OZET.csv",("period","model","targets","mean",
             "expected_mean","hits_7plus","hits_8plus","hits_9plus","hits_10"),
             result["audit_summary"]),
          ("08_DUN_BUGUN_AILE_BAGLANTISI.csv",("origin_day","next_day","size",
             "family","H23_support","next_H00_same_top",
             "next_day_actual_occurrences"),result["day_compare"])
        ]
        for filename,fields,rows in payload:
            _write(z,filename,fields,rows)
        z.writestr("09_YONTEM_KONTROL.txt",
          "Geçmiş öğrenimi geleceği açarak yapılmaz: her saatin ilk 6 sonucu "
          "önceden bilinir, tüm 7.–12. hedef kuponları o anda sabitlenir.\n"
          "Sıcak-soğuk rastgele dizide de görünür. 72'lik pencere ile "
          "sıcaklık kararlılığı metodun yan ürünüdür.\n"
          "Aile değişimi, bir önceki saatin ilk 12 liderinden bir sayı "
          "değişmiş bir sonraki saat liderine geçiştir. Bu bir fiziksel "
          "bağ ya da RNG mekanizması değildir.\n"
          "H00 ve H07 arası kapanış yaklaşık 6 saattir; geçiş yalnız saat "
          "blokları arası yapısal karşılaştırmadır.\n"
          "Günler için sadece 217/217 kayıtlar alınır. Yeni ileri test "
          "16.10.2026'dan başlayan 14 TAM yeni güne uygulanır.\n"
          "Tüm modeller çoklu-sınama riski taşır, hiçbiri kanıtlanmış RNG "
          "tahmin avantajı ya da kupon kazancı değildir.\n")
    return blob.getvalue()

def run_source(source,chosen=None,n_sims=SIMULATIONS_DEFAULT):
    full,partial,broken,duplicate=parse_draws(Path(source))
    selected=date.fromisoformat(chosen) if chosen else None
    analysis=analyze(full,selected,n_sims)
    analysis["meta"]["incomplete_days"]=partial
    analysis["meta"]["invalid_rows"]=len(broken)+len(duplicate)
    return analysis

def _selftest():
    assert len(BLOCKS)==18 and sum(b["expected"] for b in BLOCKS)==217
    assert len(simulate_day(12345))==217
    a=simulate_day(2)
    old=[{"day":"2026-10-01","id":30000+i,"time":SLOTS[i],
          "nums":frozenset(range(1,21))} for i in range(217)]
    first6=a[:6]
    out=build_tickets(old,first6,"2026-10-01","H07")
    assert len(out)==len(MODEL_NAMES)
    assert all(len(v)==10 and len(set(v))==10 for v in out.values())
    before=build_tickets(old,first6,"2026-10-01","H07")
    a[7]["nums"]=frozenset(range(61,81))
    assert before==build_tickets(old,first6,"2026-10-01","H07")
    day=date(2026,10,1)
    clean=[dict(r,day=str(day),id=123000+i) for i,r in enumerate(a)]
    first,history=score_day(day,clean,[],"HIST")
    assert len(first)==18*6*len(MODEL_NAMES)
    assert len(history)==217
    assert all(not (r["hour"]=="H00" and r["target_time"]=="01:02") for r in first)
    assert 0<=sum(x["hits"] for x in first)<18*6*len(MODEL_NAMES)*11
    leader=hour_leaders(clean)
    counts,changes=family_transitions(leader,str(day))
    assert all(r["status"] in {"AYNI_AILE_DEVAM","BIR_SAYI_DEGISTI",
                               "LIDER_LISTESINDEN_CIKTI"} for r in changes)
    fake={day:clean}
    result=analyze(fake,day,2)
    assert result["meta"]["selected_draws"]==217
    with zipfile.ZipFile(io.BytesIO(build_zip(result))) as z:
        assert len(z.namelist())==10
        assert len(list(csv.reader(io.StringIO(z.read("01_80_SAYI_217_KARAKTER_YOLU.csv").decode()))))==217*80+1
    print("PASS V54: no-lookahead first6/last6, 217x80, hour family changes, RNG simulation, 10-file ZIP")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--day",default=None)
    p.add_argument("--sims",type=int,default=SIMULATIONS_DEFAULT)
    p.add_argument("--output-dir",default="v54_artifacts")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:_selftest();return
    report=run_source(a.source,a.day,a.sims)
    out=Path(a.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    dest=out/f"V54_RNG_KARAKTER_AILE_DONUSUMU_{report['meta']['selected']}_TEK_ZIP.zip"
    dest.write_bytes(build_zip(report))
    print(json.dumps({"file":str(dest),"meta":report["meta"],
         "audit_summary":report["audit_summary"],
         "family_rng_comparison":report["null"]},ensure_ascii=False,default=str))

if __name__=="__main__":
    main()
