# -*- coding: utf-8 -*-
"""V22: first TWO full family appearances -> frozen THIRD-appearance forecast.

All 2..10 family sizes; 2/3/4 core companions and changing satellite teams.
Exactly two sightings in the FIRST SIX draws of a real 12-draw hour. No
post-target information enters choice, tie breaking, companion selection,
or exact-gap projected next position.

Honest baselines: exact hypergeometric family probability per draw,
matching random-size family, random companions conditional on a core,
and temporal-gap forecast hit vs known p_family(k).

Outcomes are evaluated in last six (short horizon) and the remainder of
the SAME day (long horizon). Night 01:02 is an extra draw; 01:02->07:02
is a real six-hour break and never a synthetic draw.
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
from itertools import combinations
from pathlib import Path
from statistics import mean
from v11_arastirma import read_draws
from v21_aile_yasam_dongusu import (
    group_full_days, HOUR_STARTS, SIZES, CORE_SIZES, clock,
    hour_label, key, p_family, csv_bytes
)


def validate_hour(first, last):
    if len(first) != 6 or len(last) != 6:
        raise ValueError("6+6 gerçek çekiliş gerekli")
    pos = [d["pos"] for d in first+last]
    if pos != list(range(pos[0], pos[0]+12)):
        raise ValueError("Boşluğun üzerinden uydurma saat kuramaz")
    if pos[0] not in HOUR_STARTS:
        raise ValueError("Geçersiz saat başlangıcı")


def candidate_first_two(first, k):
    """Find all exactly twice-observed k-families using ONLY the six draws."""
    found = {}
    masks = [d["mask"] for d in first]
    for i in range(6):
        for j in range(i+1,6):
            common = masks[i] & masks[j]
            if common.bit_count() < k:
                continue
            ns = tuple(n for n in range(1,81) if common & (1<<(n-1)))
            for fam in combinations(ns,k):
                found[fam] = found.get(fam,0) | (1<<i) | (1<<j)
    records=[]
    for fam, seen in found.items():
        if seen.bit_count()!=2:
            continue
        idx=[i for i in range(6) if seen & (1<<i)]
        a,b=idx
        # Seen at exactly two earlier draws; independently recover from masks.
        fmask=sum(1<<(n-1) for n in fam)
        if [i for i,m in enumerate(masks) if m & fmask == fmask] != idx:
            raise AssertionError("Incorrect candidate occurrence mask")
        outside1=set(first[a]["nums"])-set(fam)
        outside2=set(first[b]["nums"])-set(fam)
        shared=outside1 & outside2
        records.append({
            "fam":fam,"mask":fmask,"first":first[a]["pos"],"second":first[b]["pos"],
            "gap":b-a,"shared_outside":shared,
            "outside1":outside1,"outside2":outside2,
            "satellites":tuple(sorted(shared,key=lambda n:n))})
    # Primary: 2 observed appearances; narrowest existing gap wins.
    # Secondary: strongest shared environment (the k-core has some companions).
    # Final lexicographic tie breaks, no knowledge of future needed.
    records.sort(key=lambda r:(r["gap"],-len(r["shared_outside"]),r["fam"]))
    return records


def choose_companions(core, n=3):
    """Freeze 3 predicted satellites from two past complete occurrences."""
    sat=sorted(core["shared_outside"])
    other=sorted((core["outside1"]|core["outside2"])-core["shared_outside"])
    return tuple((sat+other)[:n])


def draw_has(d,mask):
    return d["mask"] & mask == mask


def evaluate_hour(date, day, start, k):
    first=[day[start+i] for i in range(6)]
    last=[day[start+i] for i in range(6,12)]
    validate_hour(first,last)
    options=candidate_first_two(first,k)
    if not options:
        return None, len(options)
    choice=options[0]
    core=choice["fam"]
    seed=int(date.replace("-",""))*70001+start*127+k*19
    rnd=random.Random(seed)
    control=tuple(sorted(rnd.sample(range(1,81),k)))
    ctrlmask=sum(1<<(n-1) for n in control)
    after=[day[p] for p in range(start+6,218)]
    third=next((d for d in after if draw_has(d,choice["mask"])),None)
    last6_hits=[d for d in last if draw_has(d,choice["mask"])]
    ctrl_last6=sum(draw_has(d,ctrlmask) for d in last)
    ctrl_day=next((d for d in after if draw_has(d,ctrlmask)),None)
    target=choice["second"]+choice["gap"]
    eligible=start+6<=target<=217
    target_hit=bool(eligible and draw_has(day[target],choice["mask"]))
    target_time=clock(target)[0] if 1<=target<=217 else ""
    ages=third["pos"]-choice["second"] if third else None
    minutes=clock(third["pos"])[1]-clock(choice["second"])[1] if third else None
    p=p_family(k)
    base_day=1-(1-p)**len(after)
    sat=choose_companions(choice) if k in CORE_SIZES else ()
    selected_sat_count=0
    control_sat_count=0
    control_sat=()
    third_sat=0
    common_to_both=0
    new_sats=0
    if sat:
        available=[n for n in range(1,81) if n not in core]
        control_sat=tuple(sorted(rnd.sample(available,len(sat))))
        # Score companions ONLY in full-core successes on FUTURE draws.
        for d in last6_hits:
            vals=set(d["nums"])
            selected_sat_count+=sum(n in vals for n in sat)
            control_sat_count+=sum(n in vals for n in control_sat)
        if third:
            other=set(third["nums"])-set(core)
            third_sat=len(other.intersection(sat))
            common_to_both=len(other.intersection(choice["shared_outside"]))
            new_sats=len(other - (choice["outside1"] | choice["outside2"]))
    phase="Öğrenme" # overridden by orchestrator
    row={
        "Tarih":date,"Dönem":phase,"Saat":clock(start)[0],
        "Saat ilk sıra":start,"Boyut":k,"Önceden seçilen aile":key(core),
        "İlk görünüş sıra":choice["first"],"İlk görünüş saati":clock(choice["first"])[0],
        "İkinci görünüş sıra":choice["second"],"İkinci görünüş saati":clock(choice["second"])[0],
        "İlk iki çıkış arası çekiliş":choice["gap"],
        "İlk iki çıkış arası gerçek dakika":
            clock(choice["second"])[1]-clock(choice["first"])[1],
        "İlk6'da tam iki kez görünen aday aile":len(options),
        "İlk iki çıkışın ortak çevre sayısı":len(choice["shared_outside"]),
        "İlk iki çıkışın ortak çevresi":key(sorted(choice["shared_outside"])),
        "Önceden seçilen üç eşlikçi":key(sat),
        "Eşit aralık hedef sıra":target if eligible else "",
        "Eşit aralık hedef saat":target_time if eligible else "",
        "Eşit aralık tam isabet":int(target_hit) if eligible else "",
        "Son6 çekiliş":6,"Son6 üçüncü geldi":int(bool(last6_hits)),
        "Son6 tam aile görünüşü":len(last6_hits),
        "Kontrol aile son6 tam görünüşü":ctrl_last6,
        "Seçilen eşlikçi son6 tam aile yanında":selected_sat_count,
        "Rastgele eşlikçi son6 tam aile yanında":control_sat_count,
        "Eşlikçi sınama sayısı":len(sat)*len(last6_hits),
        "Son6 üçüncüde saat içi sıra":
            last6_hits[0]["pos"]-start+1 if last6_hits else "",
        "Gün içinde daha sonra üçüncü":int(third is not None),
        "Üçüncü sıra":third["pos"] if third else "",
        "Üçüncü saat":clock(third["pos"])[0] if third else "",
        "İkinci→üçüncü çekiliş farkı":ages if third else "",
        "İkinci→üçüncü gerçek dakika":minutes if third else "",
        "Üçüncüde seçilen eşlikçi":third_sat if third else "",
        "Üçüncüde ilk ikiyle ortak çevre":common_to_both if third else "",
        "Üçüncüde yeni çevre sayısı":new_sats if third else "",
        "Gün sonuna kadar gözlenebilir hedef":len(after),
        "RNG son6 en az bir tam çıkış":round(1-(1-p)**6,8),
        "RNG gün sonuna kadar üçüncü":round(base_day,8),
        "Kontrol aile gün sonu üçüncü":int(ctrl_day is not None),
        "RNG eşlikçi tam çekirdek koşullu olasılığı":
            round((20-k)/(80-k),8) if sat else "",
        "Kontrol aile":key(control),
        "Rastgele eşlikçiler":key(control_sat),
        "Not":"Yalnız saat ilk6 sonucundan seçildi; sonraki 6 ve gün sonu değerlendirme",
    }
    return row,len(options)


def summarise_rows(rows):
    grouped=defaultdict(list)
    for r in rows:
        grouped[(r["Dönem"],r["Boyut"])].append(r)
    out=[]
    for (phase,k),rr in sorted(grouped.items()):
        eligible=[r for r in rr if r["Eşit aralık hedef sıra"] != ""]
        hits=sum(r["Son6 üçüncü geldi"] for r in rr)
        full=sum(r["Son6 tam aile görünüşü"] for r in rr)
        controls=sum(r["Kontrol aile son6 tam görünüşü"] for r in rr)
        thirds=sum(r["Gün içinde daha sonra üçüncü"] for r in rr)
        expected=sum(r["RNG son6 en az bir tam çıkış"] for r in rr)
        long_expected=sum(r["RNG gün sonuna kadar üçüncü"] for r in rr)
        companion_n=sum(r["Eşlikçi sınama sayısı"] for r in rr)
        together=sum(r["Seçilen eşlikçi son6 tam aile yanında"] for r in rr)
        control_together=sum(r["Rastgele eşlikçi son6 tam aile yanında"] for r in rr)
        out.append({
            "Dönem":phase,"Boyut":k,"Önceden seçilen saat/aile":len(rr),
            "Son6'da üçüncü en az 1":hits,
            "Son6'da üçüncü RNG beklenen":round(expected,3),
            "Son6 tam aile toplam":full,
            "Kontrol aile son6 tam toplam":controls,
            "Son6 tam RNG beklenen":round(len(rr)*6*p_family(k),3),
            "Gün sonuna kadar üçüncü en az 1":thirds,
            "Gün sonuna kadar üçüncü RNG beklenen":round(long_expected,3),
            "Eşit aralıkla 3. aday hedef":len(eligible),
            "Eşit aralık tam isabet":sum(r["Eşit aralık tam isabet"] for r in eligible),
            "Eşit aralık RNG beklenen":round(len(eligible)*p_family(k),3),
            "Seçilen eşlikçi sonraki6 ortak çıkış":together,
            "Rastgele eşlikçi sonraki6 ortak çıkış":control_together,
            "Eşlikçi karşılaştırma hakkı":companion_n,
            "RNG koşullu eşlikçi beklenen":
                round(companion_n*((20-k)/(80-k)),3) if companion_n else "",
            "RNG tam aile tek hedef olasılığı":round(p_family(k),9),
            "Anlamı":"Geçmişte iki kez görünen ailelerin 3. çıkışı, kör zaman testi",
        })
    return out


def day_rows(rows):
    grouped=defaultdict(list)
    for r in rows:grouped[(r["Tarih"],r["Boyut"])].append(r)
    return [
        {
            "Tarih":date,"Boyut":k,"Sinyal":len(rr),
            "Son6 tam aile":sum(r["Son6 tam aile görünüşü"] for r in rr),
            "RNG son6 beklenen":round(sum(6*p_family(k) for r in rr),4),
            "Eşit aralık hedef":sum(r["Eşit aralık hedef sıra"]!="" for r in rr),
            "Eşit aralık başarılı":sum(r["Eşit aralık tam isabet"]==1 for r in rr),
            "Gün bitene kadar üçüncü":sum(r["Gün içinde daha sonra üçüncü"] for r in rr),
        } for (date,k),rr in sorted(grouped.items())
    ]


def execute(txt, train_days=36):
    data,errors=read_draws(txt)
    full,incomplete=group_full_days(data)
    if len(full)<2:
        raise ValueError("En az iki tam gün gerekli")
    if not 0<=train_days<len(full):
        raise ValueError("Yanlış öğrenme/test ayrımı")
    chosen=[],eligibility=Counter(),per_hour=Counter()
    for di,(date,records) in enumerate(full):
        day={d["pos"]:d for d in records}
        phase="İlk 36 gün" if di<train_days else "Son 36 gün (ayrı test)"
        for start in HOUR_STARTS:
            for k in SIZES:
                r,candidates=evaluate_hour(date,day,start,k)
                eligibility[k]+=candidates
                if r:
                    r["Dönem"]=phase
                    chosen.append(r)
                    per_hour[k]+=1
    summary=summarise_rows(chosen)
    metainfo={
        "Veri": "veri.txt", "Gün sayısı":len(full), "İlk":full[0][0],"Son":full[-1][0],
        "Çekiliş":len(full)*217, "Gerçek saat":len(full)*18,
        "Analiz boyutları":list(SIZES),
        "Tam iki görünüşlü uygun aile (saatler üzeri toplam)":dict(eligibility),
        "Saat başına seçilen bir aile sayısı":dict(per_hour),
        "Bozuk ham satırlar":errors,
        "Tam olmayan günler":incomplete,
        "Yöntem":"İlk 6 çekilişte tam iki kez görünen her boyuttan bir çekirdek, en yakın iki çıkış aralığı; "
                 "tie-break ortak çevre ve leksikografik. Son6 ve gün sonuna kadar ilk üçüncü tam çıkış.",
        "Bilgi sızıntısı":"Aile ve üç eşlikçi sadece ilk 6 çekilişten sabitlenir",
        "Dikkat":"Tüm kayıtlı geçmiş sonuçlara bakıldıktan sonra geliştirilmiş kural; "
                 "test dönemindeki öngörü raporu geçmişe dönük holdout, gelecekte sabit model testi ayrıca gerekli.",
    }
    output={
        "ozet.json":json.dumps(metainfo,ensure_ascii=False,indent=2).encode("utf-8"),
        "2_10_aile_ucuncu_gorunus_tum_saatler.csv":csv_bytes(chosen),
        "ilk36_son36_boyut_basari.csv":csv_bytes(summary),
        "gunluk_aile_ucuncu_takibi.csv":csv_bytes(day_rows(chosen)),
    }
    return output,summary,chosen


def write_zip(parts,location):
    with zipfile.ZipFile(location,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as f:
        for path,content in parts.items():
            f.writestr(path,content)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data",default="veri.txt")
    p.add_argument("--output",default="V22_AILE_3UNCU_ZAMAN_ESLIKCI_72_GUN.zip")
    args=p.parse_args()
    part,summary,_=execute(Path(args.data).read_text(encoding="utf-8-sig"))
    write_zip(part,args.output)
    for r in summary:print("V22_RESULT",json.dumps(r,ensure_ascii=False))
    print("V22_PASS",args.output)


if __name__=="__main__":
    main()
