# -*- coding: utf-8 -*-
"""V31 Ayna Bant Kardeşliği — 40/41 axis, eight 10-number bands.

Pairs around 40.5:
 B1 (1..10)   <-> B8 (71..80)
 B2 (11..20)  <-> B7 (61..70)
 B3 (21..30)  <-> B6 (51..60)
 B4 (31..40)  <-> B5 (41..50)
 Individual n <-> 81-n (forty exact mirror pairs).

At EVERY DRAW, lower 1..40 + upper 41..80 = 20. The -1
contemporaneous correlation of half totals is a tautology, never a
forecast! Band-to-band lag>0 and number mirror co-occurrences are
separately compared to controls.

Models are 5 predeclared rules: 24d fit, 12d choose via Brier,
36d time-ordered replay. IMPORTANT: V31's symmetry hypotheses were
devised after V30 already evaluated those same final36 dates. This is
therefore an EXPLORATORY retrospective replay, NOT a fresh untouched
independent holdout or a claim of RNG prediction advantage. Collect
NEW unseen future days for confirmatory replication.

All selections freeze at end of H6 before H7..H12. EWMA half life
12 real draws; no fabricated 01:02--07:02 results. The original data
and previous motors are left intact.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import zipfile
from collections import Counter,defaultdict
from datetime import date
from itertools import combinations
from pathlib import Path
from statistics import mean

from v11_arastirma import read_draws
from v21_aile_yasam_dongusu import clock,csv_bytes,group_full_days,key
from v29_sicaklik_kalis_hedef import phase_for,generate_rows
from v30_bant_isi_yon import (
    band_of,pressure_snapshots,enrich,band_phase,
    crossband_lag,interval
)

BALLS=tuple(range(1,81))
MIRROR_BANDS=((1,8),(2,7),(3,6),(4,5))
MODELS=("RNG_%25","AynaBant_AltiYuz",
        "AynaBant_KarsitRitim","AynaSayi_Ilk6",
        "Simetri_Birlesik")
PERMUTATIONS=399
PRIOR=800.


def mirror_number(n):
    if not 1<=n<=80:raise ValueError(n)
    return 81-n


def sibling_band(b):
    if not 1<=b<=8:raise ValueError(b)
    return 9-b


def ring_of(n):
    b=band_of(n)+1
    return min(b,sibling_band(b))


def sign(x):
    return "Artı" if x>0 else "Eksi" if x<0 else "Sıfır"


def group_delta(delta):
    return "Yukarı" if delta>0 else "Aşağı" if delta<0 else "Denge"


def preparing(draws,phases,progress=None):
    byday=defaultdict(dict)
    for r in draws:
        if r["day"] in phases:
            byday[r["day"]][r["pos"]]=r
    def announce(n,total,stage,day):
        if progress:progress(min(n,72),80,stage,day)
    events=generate_rows(draws,phases,progress=announce)
    pressure=pressure_snapshots(draws,phases)
    enrich(events,pressure)
    assert sum(rows[0]["Dönem"]=="Sınama36" for _,_,rows in events)==(sum(v=="Sınama36" for v in phases.values())*18)
    detail=[]
    band_detail=[]
    # Loop across complete 12-draw hours only. All first-half features
    # derive exclusively from H1..H6, never target.
    for day,start,rows in events:
        bynum={r["Sayı"]:r for r in rows}
        first=[byday[day][p] for p in range(start,start+6)]
        bands=band_phase(first)
        first_six=Counter(n for r in first for n in r["nums"])
        low_first=sum(n<=40 for r in first for n in r["nums"])
        first_low_total=low_first
        rowband={}
        for i in range(8):
            info=bands[i]
            total=info["İlk6 toplam"]
            sibling=bands[7-i]
            # target labels only for audit after feature freezing
            future=sum(r["H7-H12 gelen sayı"] for r in rows
                       if band_of(r["Sayı"])==i)
            rowband[i+1]={
                "Tarih":day,"Saat":clock(start)[0],"Dönem":rows[0]["Dönem"],
                "Bant":i+1,"Kardeş bant":8-i,
                "10 sayı aralığı":info["Aralık"],
                "İlk6 sayı toplam":total,
                "İlk6 merkez fark":total-15,
                "İlk6 salınım":info["İlk6 +/- dizisi"],
                "İlk6 son3-ön3":info["İlk3-son3 fark"],
                "Kardeş ilk6 toplam":sibling["İlk6 toplam"],
                "Kardeş ilk6 salınım":sibling["İlk6 +/- dizisi"],
                "Kardeş ilk6 son3-ön3":sibling["İlk3-son3 fark"],
                "Bant artı-eksi faz tersliği H1..H6":sum(
                    a!=b for a,b in zip(
                        info["İlk6 +/- dizisi"],sibling["İlk6 +/- dizisi"])),
                "H7..H12 gerçekleşen sayı":future,
                "H7..H12 çekiliş başına gelen":round(future/6,6)
            }
            band_detail.append(rowband[i+1])
        for n in BALLS:
            r=bynum[n]
            m=mirror_number(n)
            mate=bynum[m]
            b=band_of(n)+1
            band=rowband[b]
            mate_band=rowband[sibling_band(b)]
            r["Ayna sayı"]=m
            r["Alt/Üst yarı"]="Alt 1-40" if n<=40 else "Üst 41-80"
            r["Ayna halka"]=ring_of(n)
            r["Kardeş bant"]=sibling_band(b)
            r["Ayna sayı ilk6 geldi"]=first_six[m]
            r["Ayna sayı ilk6 sınıf"]=mate["Isı6 adı"]
            r["Ayna sayı H6 hareket"]=mate["Basınç yönü"]
            r["Ayna sayı aynı ısı6"]=int(mate["Isı6"]==r["Isı6"])
            r["Ayna sayı karşıt uçlar"]=int(mate["Isı6"]+r["Isı6"]==5)
            r["Ayna sayı zıt yönler"]=int(
                {mate["Basınç yönü"],r["Basınç yönü"]}
                =={"Isınıyor","Soğuyor"})
            r["Kardeş ilk6 artı/eksi"]=mate_band["İlk6 salınım"]
            r["Kendi ilk6 artı/eksi"]=band["İlk6 salınım"]
            r["Kardeş ilk6 +/− zıtlık"]=band["Bant artı-eksi faz tersliği H1..H6"]
            r["Kardeş ilk6 basınç farkı"]=mate_band["İlk6 son3-ön3"]
            r["Kendi ilk6 basınç farkı"]=band["İlk6 son3-ön3"]
            r["İki yarı ilk6 fark"]=2*first_low_total-120
            r["Kendi bant fazla/eksik"]=sign(band["İlk6 merkez fark"])
            r["Kardeş bant fazla/eksik"]=sign(mate_band["İlk6 merkez fark"])
            # Mirror co-draw label is descriptive only: never used for
            # fitting, validation selection or pre-target ranking.
            r["H7..H12 ayna ile beraber çıktı"]=sum(
                r[f"H{h} hedefte"]*mate[f"H{h} hedefte"]
                for h in range(7,13))
        assert sum(rows[j]["H7-H12 gelen sayı"] for j in range(80))==120
        assert all(row["Kardeş bant"]==9-row["Bant"] for row in rows)
        if day not in byday:raise AssertionError("Missing target day")
        detail.append((day,start,rows))
    return detail,band_detail


def model_key(r,method):
    if method=="RNG_%25":return ("all",)
    heat=r["Isı6"]
    if method=="AynaBant_AltiYuz":
        return (heat,r["Ayna halka"],r["Kendi bant fazla/eksik"],
                r["Kardeş bant fazla/eksik"])
    if method=="AynaBant_KarsitRitim":
        return (heat,r["Kardeş ilk6 +/− zıtlık"],
                group_delta(r["Kardeş ilk6 basınç farkı"]),
                group_delta(r["Kendi ilk6 basınç farkı"]))
    if method=="AynaSayi_Ilk6":
        return (heat,r["İlk6 çıkma tipi"],
                "Var" if r["Ayna sayı ilk6 geldi"] else "Yok",
                r["Ayna sayı zıt yönler"])
    if method=="Simetri_Birlesik":
        return (heat,r["Ayna halka"],r["Basınç yönü"],
                "Üst" if r["Kardeş ilk6 +/− zıtlık"]>=4 else "Alt",
                sign(r["İki yarı ilk6 fark"]))
    raise ValueError(method)


def fit24(events):
    state={method:defaultdict(lambda:[0,0]) for method in MODELS}
    for d,start,rows in events:
        if rows[0]["Dönem"]!="Eğitim24":continue
        for r in rows:
            for method in MODELS:
                cell=state[method][model_key(r,method)]
                cell[0]+=r["H7-H12 gelen sayı"]
                cell[1]+=6
    return {
        method:{k:(hits+PRIOR*.25)/(total+PRIOR)
                for k,(hits,total) in cells.items()}
        for method,cells in state.items()
    }


def probabilities(rows,fit,method):
    if method=="RNG_%25":return [.25]*80
    p=[fit[method].get(model_key(r,method),.25) for r in rows]
    mean_p=mean(p)
    q=[min(.99,max(.01,value+.25-mean_p)) for value in p]
    return q


def brier(rows,p):
    if len(rows)!=80 or len(p)!=80:raise AssertionError("80")
    return sum(6*pr*pr-2*pr*r["H7-H12 gelen sayı"]+
               r["H7-H12 gelen sayı"]
               for pr,r in zip(p,rows))/(80*6)


def choose_model(events,fit):
    audit=[]
    for method in MODELS:
        tests=defaultdict(list)
        for day,start,rows in events:
            if rows[0]["Dönem"]=="Doğrulama12":
                tests[day].append(brier(rows,probabilities(rows,fit,method)))
        v=mean(n for z in tests.values() for n in z)
        audit.append({"Kural":method,"Doğrulama gün":len(tests),
                     "Doğrulama saat":sum(map(len,tests.values())),
                     "Brier":round(v,10),"RNG Brier":.1875,
                     "RNG fark":round(v-.1875,10)})
    best=min(audit,key=lambda r:(
        r["Brier"],MODELS.index(r["Kural"])))["Kural"]
    for row in audit:row["Seçildi"]=row["Kural"]==best
    return best,audit


def coupons(rows,p,day,start):
    rng=random.Random(int(day.replace("-",""))*217+start*5801)
    jitter={n:rng.random() for n in BALLS}
    ranked=sorted(BALLS,key=lambda n:(-p[n-1],jitter[n]))
    hot=sorted(BALLS,key=lambda n:(-rows[n-1]["Isı6"],jitter[n]))
    return {
        "Model10":ranked[:10],
        "Model20":ranked[:20],
        "Rastgele10":rng.sample(BALLS,10),
        "Rastgele20":rng.sample(BALLS,20),
        "Sıcak10":hot[:10],
        "Sıcak20":hot[:20],
    }


def test36(events,fit,chosen):
    card=defaultdict(list)
    group=defaultdict(dict)
    forecast=[]
    heat_projection=defaultdict(list)
    for day,start,rows in events:
        if rows[0]["Dönem"]!="Sınama36":continue
        p=probabilities(rows,fit,chosen)
        items=coupons(rows,p,day,start)
        lookup={r["Sayı"]:r for r in rows}
        for name,nums in items.items():
            hits=[sum(lookup[n][f"H{h} hedefte"] for n in nums)
                  for h in range(7,13)]
            card[name].extend(hits)
            group[day].setdefault(name,[]).extend(hits)
            forecast.append({
                "Tarih":day,"Saat":clock(start)[0],
                "Model":chosen,"Yöntem":name,
                "Kupon boyut":len(nums),"Kupon":key(sorted(nums)),
                **{f"H{h} isabet":hits[h-7] for h in range(7,13)},
                "6 hedef toplam":sum(hits),
                "6+":sum(x>=6 for x in hits),
                "7+":sum(x>=7 for x in hits),
                "8+":sum(x>=8 for x in hits),
                "9+":sum(x>=9 for x in hits),
                "10+":sum(x>=10 for x in hits),
            })
        heat_projection[day].append(.1875-brier(rows,p))
    dist=[]
    for name,hits in sorted(card.items()):
        sizes=10 if name.endswith("10") else 20
        cnt=Counter(hits)
        dist.append({
            "Yöntem":name,"Boyut":sizes,"Hedef":len(hits),
            "Ortalama isabet":round(mean(hits),7),
            "RNG ortalama":sizes/4,
            "5+":sum(v for k,v in cnt.items() if k>=5),
            "6+":sum(v for k,v in cnt.items() if k>=6),
            "7+":sum(v for k,v in cnt.items() if k>=7),
            "8+":sum(v for k,v in cnt.items() if k>=8),
            "9+":sum(v for k,v in cnt.items() if k>=9),
            "10+":sum(v for k,v in cnt.items() if k>=10),
            "10/10":cnt[10] if sizes==10 else "",
            "En yüksek":max(hits),
            **{f"{i}/{sizes}":cnt[i] for i in range(sizes+1)}
        })
    ci=[]
    for a,b in (("Model10","Rastgele10"),("Model10","Sıcak10"),
                ("Model20","Rastgele20"),("Model20","Sıcak20")):
        delta=[mean(group[d][a])-mean(group[d][b]) for d in sorted(group)]
        m,lo,hi=interval(delta)
        ci.append({"Kıyas":f"{a} - {b}","Test gün":len(delta),
                   "Fark":round(m,7),"95% alt":round(lo,7),
                   "95% üst":round(hi,7),"Üstünlük gösterildi":lo>0})
    m,lo,hi=interval([mean(heat_projection[d]) for d in sorted(heat_projection)])
    ci.append({"Kıyas":"Adil RNG Brier - model Brier","Test gün":len(heat_projection),
               "Fark":round(m,9),"95% alt":round(lo,9),
               "95% üst":round(hi,9),"Üstünlük gösterildi":lo>0})
    return forecast,dist,ci


def ring_tables(events,band_detail):
    """Per-hour pair layout plus mirror-number same-draw counts."""
    bandindex={(r["Tarih"],r["Saat"],r["Bant"]):r
               for r in band_detail}
    rows=[]
    mirror_counts=Counter()
    per_number=[]
    segment_half=[]
    mirror_layout=defaultdict(lambda:[0,0,0,0,0,0])
    # Each of the 6 target draws, 20-of-80 conserved.
    for day,start,numbers in events:
        if numbers[0]["Dönem"]!="Sınama36":continue
        t=clock(start)[0]
        for a,b in MIRROR_BANDS:
            left=bandindex[(day,t,a)]
            right=bandindex[(day,t,b)]
            first_a=left["İlk6 sayı toplam"]
            first_b=right["İlk6 sayı toplam"]
            next_a=left["H7..H12 gerçekleşen sayı"]
            next_b=right["H7..H12 gerçekleşen sayı"]
            rows.append({
                "Tarih":day,"Saat":t,"Ayna bant":f"B{a} ↔ B{b}",
                "İç/dış halka":a,
                "Bant a":a,"Bant b":b,
                "A ilk6":first_a,"B ilk6":first_b,
                "A ilk6 eksi/artı":left["İlk6 salınım"],
                "B ilk6 eksi/artı":right["İlk6 salınım"],
                "Zıt işaret H1..H6":left["Bant artı-eksi faz tersliği H1..H6"],
                "A ilk6 sapma":first_a-15,"B ilk6 sapma":first_b-15,
                "İlk6 kardeş eşit mi":int(first_a==first_b),
                "A sonraki6 toplam":next_a,
                "B sonraki6 toplam":next_b,
                "A sonraki6 ortalama":round(next_a/6,6),
                "B sonraki6 ortalama":round(next_b/6,6),
                "Kardeş bant hedef toplam":next_a+next_b,
                "20 sayı havuzu kardeş beklenen":30
            })
        first_half=sum(r["İlk6 çıkma"] for r in numbers if r["Sayı"]<=40)
        next_half=sum(r["H7-H12 gelen sayı"] for r in numbers if r["Sayı"]<=40)
        assert first_half+(sum(r["İlk6 çıkma"] for r in numbers if r["Sayı"]>40))==120
        segment_half.append({
            "Tarih":day,"Saat":t,"Alt 1-40 H1-H6":first_half,
            "Üst 41-80 H1-H6":120-first_half,
            "Alt 1-40 H7-H12":next_half,
            "Üst 41-80 H7-H12":120-next_half,
            "İlk6 alt-üst fark":first_half-(120-first_half),
            "Sonraki6 alt-üst fark":next_half-(120-next_half),
            "Beklenen yarım havuz/6 çekiliş":60,
            "Not":"Aynı yarımdaki üst/alt zıt yön mekanik toplam120",
        })
        for n in range(1,41):
            left=numbers[n-1]
            right=numbers[80-n]
            assert right["Sayı"]==81-n
            overlap=sum(left[f"H{h} hedefte"]*right[f"H{h} hedefte"]
                        for h in range(7,13))
            mirror_counts[n]+=overlap
            st=mirror_layout[ring_of(n)]
            st[0]+=1
            st[1]+=int(left["Isı6"]==right["Isı6"])
            st[2]+=int(left["Isı6"]+right["Isı6"]==5)
            st[3]+=int(left["Ayna sayı zıt yönler"]==1)
            st[4]+=overlap
            st[5]+=sum(left[f"H{h} hedefte"] or right[f"H{h} hedefte"]
                       for h in range(7,13))
    T=36*18*6
    expected=T*(20*19)/(80*79)
    for n in range(1,41):
        hits=mirror_counts[n]
        per_number.append({
            "Alt sayı":n,"Üst ayna sayı":81-n,
            "Ayna bant":f"B{band_of(n)+1} ↔ B{band_of(81-n)+1}",
            "Hedef çekiliş":T,"İkisi aynı çekilişte":hits,
            "Beklenen rastgele":round(expected,6),
            "Fark":round(hits-expected,6),
            "RNG aynı anda olasılık %":round(100*20*19/(80*79),6)
        })
    total_paired=sum(mirror_counts.values())
    total_expected=expected*40
    profile=[{
        "Halka":k,"Ayna sayı çifti-saat":v[0],
        "Aynı 6 sıcaklık %":round(v[1]/v[0]*100,5),
        "Karşıt uç sıcaklık %":round(v[2]/v[0]*100,5),
        "Zıt yükseliş/iniş %":round(v[3]/v[0]*100,5),
        "Sonraki6 ayna birlikte çıkış":v[4],
        "Sonraki6 çiftin en az biri":v[5],
        "Beklenen RNG eş çıkış":round(10*expected,4)
    } for k,v in sorted(mirror_layout.items())]
    return rows,segment_half,per_number,profile,mirror_counts,\
        {"Toplam çift coappearance":total_paired,
         "Adil RNG beklenen":round(total_expected,5),
         "Tek hedefte çift ortalama":round(total_paired/T,6),
         "Teorik hedefte çift ortalama":round(40*20*19/(80*79),6),
         "T":T}


def numeric_mirror_null(events,reps=PERMUTATIONS):
    """Random perfect matchings of number identities, preserving actual draws.

    Null directly tests whether n <-> 81-n has distinctive JOINT
    appearance relative to arbitrary number pairings; all draw-level
    dependencies and each number's observed history are preserved.
    """
    byday=defaultdict(dict)
    for day,start,rows in events:
        if rows[0]["Dönem"]!="Sınama36":continue
        for h in range(7,13):
            drawn=tuple(r["Sayı"] for r in rows if r[f"H{h} hedefte"])
            assert len(drawn)==20
            byday[(day,start,h)]=drawn
    matrix=[[0]*81 for _ in range(81)]
    for ballset in byday.values():
        for a,b in combinations(ballset,2):
            matrix[a][b]+=1;matrix[b][a]+=1
    counts=[matrix[n][81-n] for n in range(1,41)]
    score=sum(counts)
    expectation=len(byday)*20*19/(80*79)
    maxabs=max(abs(x-expectation) for x in counts)
    rng=random.Random(314159)
    scores=[]
    maxima=[]
    for _ in range(reps):
        perm=list(BALLS)
        rng.shuffle(perm)
        v=[matrix[perm[2*i]][perm[2*i+1]] for i in range(40)]
        scores.append(sum(v))
        maxima.append(max(abs(x-expectation) for x in v))
    return [{
        "Hipotez":"Ayna rakam n ↔ 81-n özel bir birlikte çıkış bağı mı?",
        "Hedef çekiliş":len(byday),"Ayna sayı çiftleri":40,
        "Gerçek ayna birlikte çıkış":score,
        "Teorik beklenen":round(40*expectation,5),
        "Rastgele eşleştirme ortalaması":round(mean(scores),5),
        "Rastgele 399 eşleştirme min":min(scores),
        "Rastgele 399 eşleştirme max":max(scores),
        "İki kuyruklu sapma p":round(
            (1+sum(abs(x-40*expectation)>=abs(score-40*expectation)
                   for x in scores))/(reps+1),5),
        "En uç ayna çift sapması":round(maxabs,5),
        "Çoklu çift araması için max-istatistik p":round(
            (1+sum(x>=maxabs for x in maxima))/(reps+1),5),
        "Test notu":"Eşleştirme rastgele; çizilmiş çekilişler, sayı sıklıkları ve saatler korunur"
    }]


def mirror_lag(full,phases):
    lag=crossband_lag(full,phases,6)
    allowed={(a,b) for a,b in MIRROR_BANDS}|{
        (b,a) for a,b in MIRROR_BANDS}
    return [x for x in lag if (x["Kaynak bant"],x["Hedef bant"]) in allowed]


def report_text(meta,models,dist,ci,mirror_null,mstats):
    blob=[
        "V31 — 40.5 EKSENİ AYNA BANT VE KARDEŞLİK, TEK SONUÇ",
        "="*72,
        "8 bant: B1↔B8, B2↔B7, B3↔B6, B4↔B5",
        "40 ayrı sayı aynası: n↔(81−n).",
        "1..40 + 41..80 = 20, tek çekilişteki ters hareket zorunludur.",
        "Her 20'lik ayna kardeş bant çiftinin beklenen katkısı 5 sayıdır.",
        "Tek aynalı sayı çiftinin aynı çekilişte bulunması: 20*19/(80*79) ≈ %6.0127.",
        "Hedeflerdeki hesaplar H1-H6 görülüp H6 bitiminde donduruldu.",
        "H7-H12 bilinmeden kuponlar belirlenir, ardından 6 gelecekteki çekiliş puanlanır.",
        "Veri önceden V30 ile görüldüğü için V31 araştırması KEŞİFSEL geriye dönük",
        "testtir. Yeni taze günlerde ikinci sınama olmadan prediktif avantaj iddia edilemez.",
        "",
        "ÖZET",json.dumps(meta,ensure_ascii=False,indent=2),
        "AYNA İKİLİ ÖZET",json.dumps(mstats,ensure_ascii=False,indent=2),
        "AYNA İKİLİ RANDOM EŞLEŞTİRME",json.dumps(mirror_null,ensure_ascii=False,indent=2),
        "12 GÜN MODEL SEÇİMİ",json.dumps(models,ensure_ascii=False,indent=2),
        "36 GÜN TAHMİN SONUCU",json.dumps(dist,ensure_ascii=False,indent=2),
        "GÜN GÜN GÜVEN ARALIĞI",json.dumps(ci,ensure_ascii=False,indent=2),
        "",
        "Dosyadaki CSV raporları tüm sayı, ayna, bant, ilk6 ve sonraki6 ayrıntılarını içerir."
    ]
    return ("\n".join(blob)+"\n").encode("utf-8")


def run_study(text,progress=None):
    draws,errors=read_draws(text)
    full,incomplete=group_full_days(draws)
    phases=phase_for(full)
    until=max(phases)
    data=[r for r in draws if r["day"]<=until]
    if progress:progress(0,80,"72 günlük tam veri yükleniyor","")
    events,band_detail=preparing(data,phases,progress=progress)
    if progress:progress(73,80,"40.5 ekseninde ayna bantlar çıkarılıyor","")
    rates=fit24(events)
    chosen,validation=choose_model(events,rates)
    if progress:progress(74,80,"Seçilen yöntemle gelecek 6 çekiliş geriye dönük puanlanıyor","")
    forecasts,dist,confidence=test36(events,rates,chosen)
    pair_hour,halves,pair_number,profile,counts,mstats=ring_tables(events,band_detail)
    if progress:progress(76,80,"40 sayı aynası için random çift kontrolü","")
    null=numeric_mirror_null(events)
    lag=mirror_lag(full,phases)
    if progress:progress(79,80,"Tek rapor ve ayrıntılı tablolar hazırlanıyor","")
    last_rows=[r for day,start,rs in events
               if rs[0]["Dönem"]=="Sınama36" for r in rs]
    meta={
        "Motor":"V31 Ayna Bant Kardeşliği / 40.5 Simetri",
        "Gün":72,"İlk":min(phases),"Son":max(phases),
        "Tam saat":len(events),"Hedef çekiliş":36*18*6,
        "80 sayı-saat son36":len(last_rows),
        "Ayna bantlar":[f"{a}↔{b}" for a,b in MIRROR_BANDS],
        "Alt/üst toplam":"1..40 ve 41..80 toplamı her çekilişte 20",
        "Eksen":"40.5, bireysel sayı n ↔ 81-n",
        "Bant beklenen":"Her 10 sayılı bant 2.5 / çekiliş, ayna kardeşler birlikte 5",
        "Isı":"V28 6 basamak, EWMA 12 gerçek çekiliş yarı ömür",
        "Öngörü kesimi":"Her tam saat H6 sonu, H7..H12 altı hedef gelecek",
        "Yöntem seçimi":"24g eğitim + 12g seçme + 36g zaman sıralı test",
        "Seçilen":chosen,"Simetri sıfır hipotezi":null[0],
        "Sayı ayna beraberlik":mstats,
        "Araştırma durumu":"Keşifsel: aynı veri daha önce V30 ile incelendi. Yeni günleri görmeden kanıt olmaz.",
        "Hatalı satır":errors,"Eksik günler":incomplete
    }
    files={
        "00_TEK_RAPOR_AYNA_SIMETRI.txt":report_text(meta,validation,dist,confidence,null,mstats),
        "01_aynalı_bant_son36_her_saat_4_kardeslik.csv":csv_bytes(pair_hour),
        "02_alt40_ust40_saat_salinim.csv":csv_bytes(halves),
        "03_40_ayna_sayi_kardesi_birliktelik.csv":csv_bytes(pair_number),
        "04_40_ayna_ciftleri_sicaklik_yon_raporu.csv":csv_bytes(profile),
        "05_ayna_sayi_random_esleme_kontrol.csv":csv_bytes(null),
        "06_ayna_bantlar_gecikme_0_6_cekilis.csv":csv_bytes(lag),
        "07_24_12_model_secimi.csv":csv_bytes(validation),
        "08_son36_10_ve_20_sayi_kupon_isabet.csv":csv_bytes(dist),
        "09_son36_kupon_rastgele_guven_araliklari.csv":csv_bytes(confidence),
        "10_son36_her_saat_kupon10_20_tahmin.csv":csv_bytes(forecasts),
        "11_son36_her_sayi_saat_ayna_isi_yon_gelecek6.csv":csv_bytes(last_rows),
        "12_72gun_her_saat_8bant_kardes_fazlari.csv":csv_bytes(band_detail),
    }
    if progress:progress(80,80,"V31 tek ZIP raporu hazır","")
    return files,meta,dist,confidence,null,pair_hour


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data",default="veri.txt")
    p.add_argument("--output",default="V31_AYNA_SIMETRI_BANT_KARDESLIK_TEK_RAPOR.zip")
    args=p.parse_args()
    files,meta,dist,ci,null,pairs=run_study(
        Path(args.data).read_text(encoding="utf-8-sig"))
    with zipfile.ZipFile(args.output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,blob in files.items():z.writestr(name,blob)
    print("V31_DONE",json.dumps({
        "72 days":meta["Gün"],"model":meta["Seçilen"],
        "mirror p":null[0]["İki kuyruklu sapma p"]},ensure_ascii=False))
    for row in dist:print("V31_COUPON",json.dumps(row,ensure_ascii=False))
    print("V31_ZIP",args.output)


if __name__=="__main__":
    main()
