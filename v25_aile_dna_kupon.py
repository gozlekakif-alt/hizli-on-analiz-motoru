# -*- coding: utf-8 -*-
"""V25 - family birth, second/third, satellite transitions + real 10-ball coupons.

Research protocol (NOT evidence of RNG predictability):
- Analyze each 12-draw hour on 72 full days; 6 FIRST results known, 6 LAST
  strictly unseen at prediction time.
- Daily 00:02..01:02 has 13 draws, first real 12-hour window is 00:02..00:57.
  01:02 standalone is observed in history before 07:02. Never invent draws.
- Candidate families k=2,3,4 tracked from DAY start; "birth" exactly 1,
  "second already" exactly 2, "established" >=3 full appearances by decision.
- Frozen rule strategies: MostRecent, HotMembers, deterministic matched random.
- Track true second/third family appearances in last 6, satellites from
  historical full-core occurrences ONLY and matched random satellites.
- Track catalogue sizes k=5..10 exactly where active in first six.
- Build ten-number coupons from known family/core/satellite signals,
  compare with HOT10, COLD10, uniform random10, random first6-union10.
- First 36 days choose ONE coupon strategy; next 36 days held-out report
  both full 0..10 distribution and 5+,6+ hits with day-level uncertainty.
- After testing do NOT alter training/test data or pretend historical
  exploration is a prospective live test.
"""
from __future__ import annotations
import argparse
import json
import random
import zipfile
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from statistics import mean
from v11_arastirma import read_draws
from v21_aile_yasam_dongusu import (
    HOUR_STARTS, group_full_days, read_catalog, key, clock, csv_bytes, p_family
)

SIZES=(2,3,4)
STAGES=("İlk","İki","Üç+")
MODES=("Yakın","Sıcak","Rastgele aile")
COUPON_MODES=("AileDNA","Sıcak10","Soğuk10","Rastgele10","İlk6Havuz10")
TEN_TARGET=6
SOURCE="veri.txt"


def family_bits(ns):
    b=0
    for n in ns:b|=1<<(n-1)
    return b


def draw_has(d, mask):
    return (d["mask"]&mask)==mask


def new_state():
    return {
        "counts":{k:Counter() for k in SIZES},
        "last":{k:{} for k in SIZES},
        "catalog":defaultdict(int),
    }


def update_history(state, draw, catalog=None):
    ns=tuple(sorted(draw["nums"]))
    for k in SIZES:
        cnt=state["counts"][k]
        late=state["last"][k]
        for fam in combinations(ns,k):
            cnt[fam]+=1
            late[fam]=draw["pos"]
    if catalog:
        for label,(k,nums,mask) in catalog.items():
            if draw_has(draw,mask):
                state["catalog"][label]+=1


def pick_family_candidates(state, first6):
    """Only candidates appearing at least once in known first6, grouped by
    EXACT total-day status at cut-off."""
    output=defaultdict(list)
    for k in SIZES:
        in_window=set()
        for d in first6:
            in_window.update(combinations(tuple(sorted(d["nums"])),k))
        for fam in in_window:
            cnt=state["counts"][k][fam]
            if cnt<1:raise AssertionError("History not updated before picking")
            stage="İlk" if cnt==1 else ("İki" if cnt==2 else "Üç+")
            output[(k,stage)].append(fam)
    return output


def recent_hot_counts(all_seen, first6):
    last12=all_seen[-12:]
    n12=Counter(n for d in last12 for n in d["nums"])
    n6=Counter(n for d in first6 for n in d["nums"])
    return n12,n6


def choose_family_panel(day, position, state, all_known, first6):
    candidates=pick_family_candidates(state,first6)
    hot12,hot6=recent_hot_counts(all_known,first6)
    chosen={}
    for k in SIZES:
        for stage in STAGES:
            options=candidates.get((k,stage),[])
            if not options:continue
            # All rankings derive ONLY from <= position cutoff.
            recent=min(options,key=lambda fam:(-state["last"][k][fam],
                  -sum(hot6[n] for n in fam),fam))
            hot=min(options,key=lambda fam:(-sum(hot12[n] for n in fam),
                     -state["last"][k][fam],fam))
            rng=random.Random(int(day.replace("-",""))*131071+position*1009+k*113+STAGES.index(stage)*17)
            control=options[rng.randrange(len(options))]
            chosen[(k,stage)]={
                "Yakın":recent,"Sıcak":hot,"Rastgele aile":control
            }
    return chosen,hot12,hot6


def predict_satellites(core, history, limit=3):
    """Companions from FULL observed core appearances only, no later draws."""
    fam=set(core)
    mask=family_bits(core)
    counts=Counter()
    for draw in history:
        if draw_has(draw,mask):
            counts.update(n for n in draw["nums"] if n not in fam)
    # If a satellite was never seen next to the core, do NOT infer it
    # from the future. Output may have fewer than three when no core hits.
    return tuple(n for n,v in sorted(counts.items(),key=lambda a:(-a[1],a[0]))[:limit])


def family_event(date,start,k,stage,mode,fam,history,future):
    mask=family_bits(fam)
    seen=[d for d in history if draw_has(d,mask)]
    support=len(seen)
    expected_stage="İlk" if support==1 else ("İki" if support==2 else "Üç+")
    if expected_stage!=stage:
        raise AssertionError("Wrong family lifecycle at forecast cutoff")
    next_hit=[d for d in future if draw_has(d,mask)]
    sats=predict_satellites(fam,history)
    rng=random.Random(int(date.replace("-",""))*17+start*871+k*113+support*17+sum(fam))
    outside=[n for n in range(1,81) if n not in fam]
    ctrl=tuple(sorted(rng.sample(outside,len(sats))))
    count_sat=0;count_ctrl=0
    for draw in next_hit:
        vals=set(draw["nums"])
        count_sat+=sum(n in vals for n in sats)
        count_ctrl+=sum(n in vals for n in ctrl)
    first_hit=next_hit[0] if next_hit else None
    interval=first_hit["pos"]-seen[-1]["pos"] if first_hit else None
    true_minutes=clock(first_hit["pos"])[1]-clock(seen[-1]["pos"])[1] if first_hit else None
    past_sats=[set(d["nums"])-set(fam) for d in seen]
    shared=(set.intersection(*past_sats) if past_sats else set())
    second_outside=(set(first_hit["nums"])-set(fam)) if first_hit else set()
    new_outside=len(second_outside-set.union(*past_sats)) if first_hit else ""
    return {
        "Tarih":date,"Saat":clock(start)[0],"Kesim sıra":start+5,
        "Boyut":k,"Evre":stage,"Yöntem":mode,"Aile":key(fam),
        "Kesime dek birlikte çıkış":support,"İlk çıkış sıra":seen[0]["pos"],
        "İlk çıkış saat":clock(seen[0]["pos"])[0],
        "İkinci çıkış sıra":seen[1]["pos"] if support>=2 else "",
        "İkinci çıkış saat":clock(seen[1]["pos"])[0] if support>=2 else "",
        "Son çıkış sıra":seen[-1]["pos"],
        "Kayıtlı çekiliş içi aralık":seen[1]["pos"]-seen[0]["pos"] if support>=2 else "",
        "Öngörülen sonraki evre":"İkinci" if stage=="İlk" else ("Üçüncü" if stage=="İki" else "Bir sonraki"),
        "Son6 tam aile görünüşü":len(next_hit),
        "Son6 en az bir tam":int(bool(next_hit)),
        "Sonraki tam çıkış sıra":first_hit["pos"] if first_hit else "",
        "Sonraki tam çıkış saat":clock(first_hit["pos"])[0] if first_hit else "",
        "Son çıkıştan sonraki tam çekiliş farkı":interval if interval is not None else "",
        "Son çıkıştan sonraki gerçek dakika":true_minutes if true_minutes is not None else "",
        "Önceden seçilen üç eşlikçi":key(sats),
        "Rastgele eşlikçi kontrol":key(ctrl),
        "Son6 çekirdek yanında tahminli eşlikçi":count_sat,
        "Son6 çekirdek yanında rastgele eşlikçi":count_ctrl,
        "Eşlikçi sınama hakkı":len(next_hit)*len(sats),
        "Kesim öncesi ortak çevre":key(sorted(shared)),
        "Yeni dış çevre sayısı":new_outside,
        "RNG 6 çekilişte en az bir tam":round(1-(1-p_family(k))**len(future),8),
        "RNG 6 çekilişte tam aile ort":round(len(future)*p_family(k),8),
    }


def catalog_events(date,start,first6,history,future,state,catalog):
    """Exact tracked V10 5-10 families. Never cherry-pick by future."""
    out=[]
    for label,(k,fam,mask) in catalog.items():
        if k<5 or k>10 or not state["catalog"].get(label,0):
            continue
        # Only families that appeared in this first6 are active signals.
        if not any(draw_has(x,mask) for x in first6):
            continue
        ct=state["catalog"][label]
        nxt=[d for d in future if draw_has(d,mask)]
        history_hits=[d for d in history if draw_has(d,mask)]
        if ct!=len(history_hits):raise AssertionError("catalog count lost")
        prior=history_hits[-1]
        out.append({
            "Tarih":date,"Saat":clock(start)[0],"Boyut":k,"Aile":label,
            "Kesim öncesi tam çıkış":ct,
            "Evre":"İlk" if ct==1 else ("İki" if ct==2 else "Üç+"),
            "Son bilinen çıkış sıra":prior["pos"],
            "Son6 tam":len(nxt),"Son6 en az bir tam":int(bool(nxt)),
            "Son6 bir sonraki tam sıra":nxt[0]["pos"] if nxt else "",
            "RNG en az bir tam":round(1-(1-p_family(k))**len(future),10)
        })
    return out


def coupon_sets(date,start,chosen,hot12,hot6,history):
    """10-number coupon generated at cutoff from prior 6, prior 12,
    and frozen selected 2/3/4 families. Includes unbiased controls.
    """
    scores=defaultdict(float)
    # All 80 numbers are permitted; don't accidentally constrain to last draw.
    for n in range(1,81):
        scores[n]=0.7*hot6[n]+0.3*hot12[n]
    stage_weights={"İlk":0.4,"İki":1.5,"Üç+":1.2}
    for (k,stage),panel in chosen.items():
        fam=panel["Yakın"]
        boost=stage_weights[stage]*(1+0.25*(k-2))
        for n in fam:scores[n]+=boost
        sat=predict_satellites(fam,history)
        for n in sat:scores[n]+=0.22*boost
    dna=tuple(sorted(range(1,81),key=lambda n:(-scores[n],n))[:10])
    hot=tuple(sorted(range(1,81),key=lambda n:(-hot6[n],n))[:10])
    cold=tuple(sorted(range(1,81),key=lambda n:(hot6[n],n))[:10])
    r=random.Random(int(date.replace("-",""))*100039+start*1931)
    pure=tuple(sorted(r.sample(range(1,81),10)))
    observed=sorted({n for d in history[-6:] for n in d["nums"]})
    matched=tuple(sorted(r.sample(observed,10))) if len(observed)>=10 else pure
    coupons={
        "AileDNA":dna,"Sıcak10":hot,"Soğuk10":cold,
        "Rastgele10":pure,"İlk6Havuz10":matched
    }
    for nums in coupons.values():
        if len(nums)!=10 or len(set(nums))!=10 or min(nums)<1 or max(nums)>80:
            raise AssertionError("Bad coupon")
    return coupons


def coupon_event(date,start,method,nums,last):
    drawn=set(nums);hits=[sum(n in x["nums"] for n in nums) for x in last]
    return {
        "Tarih":date,"Saat":clock(start)[0],"Kesim sıra":start+5,
        "Yöntem":method,"10 sayı":key(nums),
        "Hedef çekilişler":",".join(str(d["pos"]) for d in last),
        "Hedef 1":hits[0],"Hedef 2":hits[1],"Hedef 3":hits[2],
        "Hedef 4":hits[3],"Hedef 5":hits[4],"Hedef 6":hits[5],
        "6 çekiliş toplam isabet":sum(hits),
        "6 çekiliş 5+":sum(h>=5 for h in hits),
        "6 çekiliş 6+":sum(h>=6 for h in hits),
        "6 çekiliş 7+":sum(h>=7 for h in hits),
        "6 çekiliş 8+":sum(h>=8 for h in hits),
        "6 çekiliş en yüksek":max(hits),
        "RNG hedef başı ortalama":2.5,
    }


def evaluate_day(date,records,catalog):
    if len(records)!=217 or [d["pos"] for d in records]!=list(range(1,218)):
        raise ValueError("217 tam gerçek çekiliş sırası olmalı")
    state=new_state()
    cursor=0
    famrows=[];catrows=[];couponrows=[]
    for start in HOUR_STARTS:
        cutoff=start+5
        # Account for 01:02 singleton and all prior draws, without
        # using any future result in state before the cutoff.
        while cursor<cutoff:
            update_history(state,records[cursor],catalog)
            cursor+=1
        history=records[:cutoff]
        first6=history[-6:]
        if [d["pos"] for d in first6]!=list(range(start,start+6)):
            raise AssertionError("Hour split not contiguous")
        last=records[start+5:start+11]
        if [d["pos"] for d in last]!=list(range(start+6,start+12)):
            raise AssertionError("Future target split incorrect")
        panel,hot12,hot6=choose_family_panel(date,cutoff,state,history,first6)
        for (k,stage),methods in panel.items():
            for method,fam in methods.items():
                famrows.append(family_event(date,start,k,stage,method,fam,history,last))
        catrows.extend(catalog_events(date,start,first6,history,last,state,catalog))
        coupon=coupon_sets(date,start,panel,hot12,hot6,history)
        for method,nums in coupon.items():
            couponrows.append(coupon_event(date,start,method,nums,last))
    return famrows,catrows,couponrows


def fit_coupon(training):
    """PRECHOOSE one of three nonrandom methods with training only."""
    methods=("AileDNA","Sıcak10","Soğuk10")
    grouped=defaultdict(list)
    for r in training:grouped[r["Yöntem"]].append(r)
    scores=[]
    for method in methods:
        xs=grouped[method]
        avg=sum(x["6 çekiliş toplam isabet"] for x in xs)/(6*len(xs))
        high=sum(x["6 çekiliş 5+"] for x in xs)
        scores.append({"Yöntem":method,"İlk36 saat":len(xs),
                       "Hedef çekiliş":6*len(xs),"Ortalama isabet":round(avg,5),
                       "5+ çekiliş":high})
    winner=max(methods,key=lambda m:(
        sum(x["6 çekiliş toplam isabet"] for x in grouped[m]),
        -methods.index(m)))
    for s in scores:s["Öğrenme galibi"]=s["Yöntem"]==winner
    return winner,scores


def group_family_eval(famrows):
    results=[]
    by=defaultdict(list)
    for r in famrows:
        by[(r["Dönem"],r["Boyut"],r["Evre"],r["Yöntem"])].append(r)
    for (period,k,stage,mode),rr in sorted(by.items()):
        n=len(rr)
        hits=sum(r["Son6 tam aile görünüşü"] for r in rr)
        times=sum(r["Son6 en az bir tam"] for r in rr)
        null=sum(r["RNG 6 çekilişte tam aile ort"] for r in rr)
        sats=sum(r["Son6 çekirdek yanında tahminli eşlikçi"] for r in rr)
        ctrls=sum(r["Son6 çekirdek yanında rastgele eşlikçi"] for r in rr)
        trials=sum(r["Eşlikçi sınama hakkı"] for r in rr)
        results.append({
            "Dönem":period,"Boyut":k,"Evre":stage,"Yöntem":mode,
            "Seçilmiş çekirdek":n,"6 hedef toplam":n*6,
            "Son6 tam aile gerçekleşen":hits,
            "Son6 en az bir tam gerçekleşen":times,
            "Adil RNG tam beklenen":round(null,4),
            "Öngörülen 3 eşlikçi isabeti":sats,
            "Rastgele 3 eşlikçi isabeti":ctrls,
            "Eşlikçi karşılaştırma hakkı":trials,
            "RNG koşullu eşlikçi beklenen":round(trials*((20-k)/(80-k)),3),
        })
    return results


def coupon_report(couponrows,winner):
    results=[];by=defaultdict(list)
    for r in couponrows:
        by[(r["Dönem"],r["Yöntem"])].append(r)
    for (period,mode),rr in sorted(by.items()):
        d=Counter()
        for r in rr:
            for j in range(1,7):d[r[f"Hedef {j}"]]+=1
        num=6*len(rr)
        results.append({
            "Dönem":period,"Yöntem":mode,
            "Saatlik 10'lu kupon":len(rr),"Hedef çekiliş":num,
            "Toplam isabet":sum(i*d[i] for i in range(11)),
            "Çekiliş başı ortalama":round(sum(i*d[i] for i in range(11))/num,5),
            "5+ isabet":sum(d[i] for i in range(5,11)),
            "6+ isabet":sum(d[i] for i in range(6,11)),
            "7+ isabet":sum(d[i] for i in range(7,11)),
            "8+ isabet":sum(d[i] for i in range(8,11)),
            "9+ isabet":sum(d[i] for i in range(9,11)),
            "10/10":d[10],
            **{f"{i}/10":d[i] for i in range(11)},
            "Seçilen eğitim galibi":mode==winner,
        })
    return results


def coupon_confidence(couponrows,winner):
    control=("Rastgele10","İlk6Havuz10")
    by=defaultdict(dict)
    for r in couponrows:by[(r["Tarih"],r["Saat"])][r["Yöntem"]]=r
    arr=[]
    dates=sorted({r["Tarih"] for r in couponrows if r["Dönem"]=="Son36"})
    for base in control:
        daily=[]
        for date in dates:
            paired=[v for (d,s),v in by.items() if d==date and winner in v and base in v]
            if not paired:continue
            diff=sum(p[winner]["6 çekiliş toplam isabet"]-
                     p[base]["6 çekiliş toplam isabet"] for p in paired)/(6*len(paired))
            daily.append(diff)
        mean_diff=mean(daily)
        se=(sum((x-mean_diff)**2 for x in daily)/(len(daily)-1)/len(daily))**.5 if len(daily)>1 else 0
        arr.append({
            "Eğitim galibi":winner,"Kontrol":base,"Test gün":len(daily),
            "İsabet/10 fark":round(mean_diff,6),
            "Yaklaşık 95% GA alt":round(mean_diff-1.96*se,6),
            "Yaklaşık 95% GA üst":round(mean_diff+1.96*se,6),
            "İstatistik üstünlük kanıtı":(mean_diff-1.96*se)>0,
        })
    return arr


def run(text,catalog_text):
    draws,errors=read_draws(text)
    full,partial=group_full_days(draws)
    catalog=read_catalog(catalog_text)
    if len(full)<37:raise ValueError("36 öğrenme + test için en az 37 tam gün")
    famrows=[];catrows=[];couponrows=[]
    for idx,(date,ds) in enumerate(full):
        a,b,c=evaluate_day(date,ds,catalog)
        period="İlk36" if idx<36 else "Son36"
        for out in (a,b,c):
            for r in out:r["Dönem"]=period
        famrows+=a;catrows+=b;couponrows+=c
    winner,learn=fit_coupon([r for r in couponrows if r["Dönem"]=="İlk36"])
    famreport=group_family_eval(famrows)
    couponreport=coupon_report(couponrows,winner)
    cip=coupon_confidence(couponrows,winner)
    meta={
        "Adı":"V25 — AileDNA evre takip ve gerçek 10'lu kupon motoru",
        "Gün":len(full),"İlk gün":full[0][0],"Son gün":full[-1][0],
        "Çekiliş":len(full)*217,"6+6 saat":len(full)*18,
        "Aile k":list(SIZES),"Kayıtlı büyük aile":len(catalog),
        "Öğrenme":[full[0][0],full[35][0]],
        "Test":[full[36][0],full[-1][0]],
        "Öğrenmede seçilen tek 10'lu yöntem":winner,
        "Bozuk kayıt":errors,"Eksik gün":partial,
        "Körlük":"Her saat ilk6 bitiminde tüm aile ve kuponlar yalnız o ana kadar kayıtlı gerçek çekilişlerden üretilir. Son6 seçim sırasında kullanılmaz.",
        "Bağımsız kontrol":"İlk36 yöntem seçer, son36 sadece sınar; ayrıca RNG teorisi ve eşleşen kontrol kuponları",
        "Uyarı":"Geçmişte keşfedilmiş aile örüntüleri, RNG'de gelecek çekilişlerde kesin avantaj kanıtı değildir."
    }
    output={
        "ozet.json":json.dumps(meta,ensure_ascii=False,indent=2).encode("utf-8"),
        "aile_evre_ilk_ikinci_ucuncu_ilk6_son6.csv":csv_bytes(famrows),
        "kayitli_1131_buyuk_aile_ilk6_son6.csv":csv_bytes(catrows),
        "gercek_10lu_kuponlar_0dan10a_isabet.csv":csv_bytes(couponrows),
        "ilk36_model_secimi.csv":csv_bytes(learn),
        "aile_olay_isabet_ozetleri.csv":csv_bytes(famreport),
        "kupon_0_10_son36_istatistik.csv":csv_bytes(couponreport),
        "test36_gunluk_karsilastirma_guven_araliklari.csv":csv_bytes(cip),
    }
    return output,meta,couponreport,famreport,cip


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data",default="veri.txt")
    ap.add_argument("--catalog",default="v10_aileler.csv")
    ap.add_argument("--output",default="V25_AILE_DNA_72_GUN_KOR_TEST.zip")
    args=ap.parse_args()
    output,meta,coup,fam,ci=run(Path(args.data).read_text(encoding="utf-8-sig"),
                                 Path(args.catalog).read_text(encoding="utf-8-sig"))
    with zipfile.ZipFile(args.output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,bytes_ in output.items():z.writestr(name,bytes_)
    print("V25_PASS",json.dumps({x:meta[x] for x in ["Gün","Çekiliş","6+6 saat","Öğrenmede seçilen tek 10'lu yöntem"]},ensure_ascii=False),flush=True)
    for x in coup:
        if x["Dönem"]=="Son36":
            print("V25_COUPON",json.dumps(x,ensure_ascii=False),flush=True)
    for x in fam:
        if x["Dönem"]=="Son36" and x["Yöntem"]=="Yakın":
            print("V25_FAMILY",json.dumps(x,ensure_ascii=False),flush=True)
    for x in ci:print("V25_CI",json.dumps(x,ensure_ascii=False),flush=True)
    print("V25_ZIP",args.output,flush=True)


if __name__=="__main__":
    main()
