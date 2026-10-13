# -*- coding: utf-8 -*-
"""V24: predict 2nd appearance at the moment the FIRST is actually seen.

Times: 00:02..01:02 (13 draws), 07:02..23:57; 01:02->07:02 real
6-hour gap, not 72 fake five-minute draws. Only actual draw positions.

At each 12-draw hour START after its first draw is known:
- From its 20 balls, select k=2..10 subfamilies NOT observed in ANY
  earlier draw of that day. This event is guaranteed the family's FIRST
  daily appearance; 0 leakage from next 11 or day-rest.
- 4 precommitted competing procedures: lexicographic, hot, cold,
  random control from same first-draw candidate population.
- Historical hot/cold frequency computed ONLY from previous real draws.
- Select best rule on first 36 complete days only, freeze for last 36.
- Test exact second completion at lags 1, 2, 3, 4..6, 7..11,
  and until last real draw of the day. Report actual hit vs fair-RNG
  expectation and matched first-appearance random control.
- Small k (2..4): enumerate eligible anchor subfamilies exactly;
  k>=5: choose first eligible in sorted lex or hot/cold rank order,
  with bounded uniform random rejection control.

Past-day retrospective validation is NOT a proven predictive lottery edge.
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
from datetime import datetime
from itertools import combinations
from pathlib import Path
from statistics import mean
from v11_arastirma import read_draws
from v21_aile_yasam_dongusu import group_full_days, HOUR_STARTS, SIZES, clock, key, p_family, csv_bytes

STRATEGIES=("Sıcak","Soğuk","Küçük sıra")
CONTROL="Rastgele kontrol"
LAG_BANDS=((1,1,"+1"),(2,3,"+2..3"),(4,6,"+4..6"),(7,11,"+7..11"),(12,216,"+12..gün sonu"))


def subset_mask(fam):
    mask=0
    for n in fam:mask|=1<<(n-1)
    return mask


def first_sighting_candidates(anchor, previous, max_size=10):
    """Return forbidden earlier k-families within present anchor.

    Intersect previous 20-ball sets with anchor first: avoids enumerating
    all C(20,10) candidates and does not look beyond anchor position.
    """
    anchor_mask=anchor["mask"]
    seen={k:set() for k in range(2,max_size+1)}
    for prev in previous:
        intersect=anchor_mask & prev["mask"]
        n=intersect.bit_count()
        if n<2:continue
        overlap=tuple(x for x in anchor["nums"] if intersect & (1<<(x-1)))
        for k in range(2,min(max_size,n)+1):
            seen[k].update(combinations(overlap,k))
    return seen


def select_families(anchor, previous, day, start):
    """Freeze entire strategy panel only from prior draws + anchor known now."""
    seen=first_sighting_candidates(anchor,previous)
    c=Counter(n for d in previous[-12:] for n in d["nums"])
    nums=tuple(sorted(anchor["nums"]))
    chosen={}
    rng=random.Random(int(day.replace("-",""))*1000003+start*1999)
    for k in SIZES:
        forbidden=seen[k]
        if k<=4:
            allowed=[f for f in combinations(nums,k) if f not in forbidden]
            if not allowed:continue
            # Correct deterministic tie breaks: greatest sum, smallest family.
            hot=min(allowed,key=lambda f:(-sum(c[n] for n in f),f))
            cold=min(allowed,key=lambda f:(sum(c[n] for n in f),f))
            first=allowed[0]
            control=allowed[rng.randrange(len(allowed))]
        else:
            # Greedy k>4: ranks individual temperatures, evaluates candidate
            # feasibility with NO post-anchor knowledge; label is heuristic.
            def greedy(order):
                candidate=tuple(sorted(order[:k]))
                if candidate not in forbidden:return candidate
                for combo in combinations(order,k):
                    candidate=tuple(sorted(combo))
                    if candidate not in forbidden:return candidate
                return None
            hot=greedy(sorted(nums,key=lambda n:(-c[n],n)))
            cold=greedy(sorted(nums,key=lambda n:(c[n],n)))
            first=greedy(list(nums))
            # Rejection sampling is uniform among allowed k-subsets.
            control=None
            for j in range(250):
                t=tuple(sorted(rng.sample(nums,k)))
                if t not in forbidden:
                    control=t;break
            if control is None:control=first
        chosen[k]={"Sıcak":hot,"Soğuk":cold,"Küçük sıra":first,CONTROL:control}
    return chosen


def first_second_event(day, draws, start, k, mode, family):
    """Single immutable forecast. Its target is always strictly later."""
    anchor=draws[start-1]
    mask=subset_mask(family)
    if not anchor["mask"]&mask==mask:
        raise AssertionError("Anchor does not contain new family")
    if any((d["mask"]&mask)==mask for d in draws[:start-1]):
        raise AssertionError("Family was seen before first/anchor draw")
    future=draws[start:]
    successes=[d for d in future if d["mask"]&mask==mask]
    second=successes[0] if successes else None
    lag=(second["pos"]-start) if second else None
    chance=p_family(k)
    secs=second["pos"] if second else None
    target11=future[:11]
    lag_windows={}
    for lo,hi,label in LAG_BANDS:
        horizon=min(hi,len(future))
        if horizon<lo:continue
        lag_windows[label]=int(bool(second and lo<=lag<=horizon))
    row={
        "Tarih":day,"Boyut":k,"Yöntem":mode,
        "İlk çekiliş no":anchor["no"],"İlk sıra":start,
        "İlk saat":clock(start)[0],"Aile":key(family),
        "Geçmiş kontrol edilen çekiliş":start-1,
        "Sonraki 11 çekiliş":len(target11),
        "İkinci +1":int(lag==1),
        "İkinci +2..3":int(lag is not None and 2<=lag<=3),
        "İkinci +4..6":int(lag is not None and 4<=lag<=6),
        "İkinci +7..11":int(lag is not None and 7<=lag<=11),
        "Son 11 içinde ikinci":int(lag is not None and lag<=11),
        "Gün bitmeden ikinci":int(second is not None),
        "İkinci sıra":second["pos"] if second else "",
        "İkinci çekiliş no":second["no"] if second else "",
        "İkinci saat":clock(second["pos"])[0] if second else "",
        "Birinci→ikinci çekiliş farkı":lag if second else "",
        "Birinci→ikinci gerçek dakika":
            clock(second["pos"])[1]-clock(start)[1] if second else "",
        "Gün sonuna kadar hedef çekiliş":len(future),
        "RNG ikinci +1":round(chance,10),
        "RNG 11 içinde":round(1-(1-chance)**len(target11),9),
        "RNG gün içinde":round(1-(1-chance)**len(future),9),
        "Kural sabitlendiği an":clock(start)[0],
        "Not":"İlk görünüşü bilip ikinciyi görmeden seçildi; önceden görülmüş aile dışarıda",
    }
    return row


def per_day_forecasts(date, records):
    """18 anchor draws, all family sizes 2..10, 4 strategies per size."""
    if len(records)!=217 or [d["pos"] for d in records]!=list(range(1,218)):
        raise ValueError("Eksik veya yanlış sıralı günlük 217 çekiliş")
    out=[]
    for start in HOUR_STARTS:
        anchor=records[start-1]
        previous=records[:start-1]
        policies=select_families(anchor,previous,date,start)
        for k in SIZES:
            if k not in policies:continue
            for policy,family in policies[k].items():
                if family is None:continue
                out.append(first_second_event(date,records,start,k,policy,family))
    return out


def strategy_fit(training):
    """Train only on first half; no test labels, rank by expected excess.

    Choose earliest-in-sample winner with deterministic policy priority.
    Every candidate is sampled at same time points for each k.
    """
    scores=defaultdict(lambda:Counter())
    for r in training:
        if r["Yöntem"]==CONTROL:continue
        pair=(r["Boyut"],r["Yöntem"])
        scores[pair]["n"]+=1
        scores[pair]["hit11"]+=r["Son 11 içinde ikinci"]
        scores[pair]["expected"]+=r["RNG 11 içinde"]
    fit=[]
    winners={}
    for k in SIZES:
        candidates=[]
        for policy in STRATEGIES:
            s=scores[(k,policy)]
            if not s["n"]:continue
            uplift=(s["hit11"]-s["expected"])/s["n"]
            candidates.append((uplift,policy,s["n"],s["hit11"],s["expected"]))
        if not candidates:continue
        winner=sorted(candidates,key=lambda x:(-x[0],STRATEGIES.index(x[1])))[0]
        winners[k]=winner[1]
        for x in candidates:
            fit.append({
                "Boyut":k,"Yöntem":x[1],"Öğrenme sinyali":x[2],
                "Son 11'de ikinci":x[3],"RNG beklenen":round(x[4],4),
                "Beklentiye fark yüzde puan":round(x[0]*100,4),
                "Seçilen":x[1]==winner[1],
                "Dönem":"Yalnız ilk 36 gün"
            })
    return winners,fit


def summarize(rows,winners):
    result=[]
    for k in SIZES:
        chosen=winners.get(k)
        if not chosen:continue
        for phase in ("İlk36","Son36"):
            for name in (chosen,CONTROL):
                xx=[r for r in rows if r["Boyut"]==k and r["Yöntem"]==name
                    and r["Dönem"]==phase]
                if not xx:continue
                n=len(xx)
                sig=sum(r["Son 11 içinde ikinci"] for r in xx)
                within=sum(r["Gün bitmeden ikinci"] for r in xx)
                expected11=sum(r["RNG 11 içinde"] for r in xx)
                expectedDay=sum(r["RNG gün içinde"] for r in xx)
                result.append({
                    "Boyut":k,"Dönem":phase,"Yöntem":name,
                    "İlk görünüş sonrası tahmin":n,
                    "Sonraki +1":sum(r["İkinci +1"] for r in xx),
                    "+2..3":sum(r["İkinci +2..3"] for r in xx),
                    "+4..6":sum(r["İkinci +4..6"] for r in xx),
                    "+7..11":sum(r["İkinci +7..11"] for r in xx),
                    "11 çekilişte ikinci":sig,
                    "11 çekiliş RNG beklentisi":round(expected11,4),
                    "11 çekilişte başarı yüzdesi":round(sig/n*100,3),
                    "Gün sonuna dek ikinci":within,
                    "Gün sonuna kadar RNG beklentisi":round(expectedDay,3),
                    "Önceden sabitlenmiş":True,
                })
    return result


def report_stats(rows,summary):
    out=[]
    for k in SIZES:
        for s in [x for x in summary if x["Boyut"]==k and x["Dönem"]=="Son36" and x["Yöntem"]!=CONTROL]:
            policy=s["Yöntem"]
            eligible=[x for x in rows if x["Boyut"]==k and x["Dönem"]=="Son36" and x["Yöntem"]==policy]
            ctrl=[x for x in rows if x["Boyut"]==k and x["Dönem"]=="Son36" and x["Yöntem"]==CONTROL]
            if not eligible or not ctrl:continue
            daily=defaultdict(lambda:{"model":0,"random":0,"expect":0,"n":0})
            for r in eligible:
                d=daily[r["Tarih"]];d["model"]+=r["Son 11 içinde ikinci"];d["n"]+=1;d["expect"]+=r["RNG 11 içinde"]
            for r in ctrl:daily[r["Tarih"]]["random"]+=r["Son 11 içinde ikinci"]
            # Compare all equal hours, stratified by day (avoids treating overlapping
            # families, repeated bets and same-day draws as independent events).
            pairs=[((d["model"]-d["random"])/d["n"],
                    (d["model"]-d["expect"])/d["n"]) for d in daily.values() if d["n"]]
            for label,i in (("Seçilen eksi rastgele",0),("Seçilen eksi matematik",1)):
                v=[x[i] for x in pairs];m=mean(v)
                se=(sum((x-m)**2 for x in v)/(len(v)-1)/len(v))**.5 if len(v)>1 else 0
                out.append({
                    "Boyut":k,"Dönem":"Son36",
                    "Karşılaştırma":label,"Gün":len(v),
                    "Günlük ortalama fark yüzde puan":round(100*m,4),
                    "Yaklaşık 95% GA alt pp":round(100*(m-1.96*se),4),
                    "Yaklaşık 95% GA üst pp":round(100*(m+1.96*se),4),
                    "Üstünlük kanıtı":bool(m-1.96*se>0),
                    "Uyarı":"36 günlük yaklaşık CI; çoklu strateji/aile sınaması var"
                })
    return out


def run(txt,train_days=36):
    draws,raw_errors=read_draws(txt)
    full,partial=group_full_days(draws)
    if len(full)<train_days+1:raise ValueError("En az 37 tam gün gerekir")
    allrows=[]
    for i,(date,d) in enumerate(full):
        result=per_day_forecasts(date,d)
        period="İlk36" if i<train_days else "Son36"
        for r in result:r["Dönem"]=period
        allrows.extend(result)
    train=[r for r in allrows if r["Dönem"]=="İlk36"]
    winners,fit=strategy_fit(train)
    summary=summarize(allrows,winners)
    confidence=report_stats(allrows,summary)
    meta={
        "Model":"V24 — ilk çıkış anında ikinci çıkışı öngörme",
        "Kaynak":"GitHub veri.txt","Tam gün":len(full),
        "İlk":full[0][0],"Son":full[-1][0],
        "Çekiliş":len(full)*217,"Tahmin başlangıcı":len(full)*18,
        "Öğrenme/tarih":[full[0][0],full[train_days-1][0]],
        "Test/tarih":[full[train_days][0],full[-1][0]],
        "Sabitlenen kazanan yöntemler":{str(k):v for k,v in winners.items()},
        "Bozuk ham satırlar":raw_errors,
        "Tam olmayan günler":partial,
        "Yöntem":"Her 12'lik saatin ilk çekilişi yayınlandıktan hemen sonra, "
                 "önceki gün içi kayıtlarda TAM görünmemiş 2–10'lu aile seçilir. "
                 "İleri 11 çekilişte aile tam çıkarsa ikinci çıkışı yakalamıştır. "
                 "İlk 36 günde yöntemler kıyaslanır, son 36 bağımsız dönemdir.",
        "Önemli":"Tahmin anchor çekilişi tamamlandıktan sonra yapılır; henüz ilk çekiliş görülmeden tahmin değildir. "
                 "2'li yeni aile bulma şansı gün sonuna doğru bitebilir.",
        "Başarıya garanti yok":"Adil RNG varsayımında sonraki çekilişin aile görülme ihtimali "
                               "geçmiş ve ilk görülme sıklığına göre değişmez.",
    }
    z={
        "ozet.json":json.dumps(meta,ensure_ascii=False,indent=2).encode("utf-8"),
        "ilk36_yontem_egitim.csv":csv_bytes(fit),
        "son36_basari_ve_rastgele_kontrol.csv":csv_bytes(summary),
        "son36_gun_bazli_guven_araliklari.csv":csv_bytes(confidence),
        "tum72_gun_saatlik_aile_ilkden_ikinciye.csv":csv_bytes(allrows),
    }
    return z,summary,confidence,meta


def main():
    parser=argparse.ArgumentParser(description="V24 72 days first->second family")
    parser.add_argument("--data",default="veri.txt")
    parser.add_argument("--output",default="V24_ILK_2INCI_AILE_72_GUN.zip")
    args=parser.parse_args()
    output,summary,confidence,meta=run(Path(args.data).read_text(encoding="utf-8-sig"))
    with zipfile.ZipFile(args.output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name,blob in output.items():archive.writestr(name,blob)
    print("V24_OK",json.dumps({k:v for k,v in meta.items()
                           if k in ("Tam gün","Çekiliş","Sabitlenen kazanan yöntemler")},ensure_ascii=False))
    for row in summary:
        if row["Dönem"]=="Son36":
            print("V24_TEST",json.dumps(row,ensure_ascii=False))
    for row in confidence:
        print("V24_CI",json.dumps(row,ensure_ascii=False))
    print("V24_ZIP",args.output)


if __name__=="__main__":
    main()
