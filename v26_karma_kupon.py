# -*- coding: utf-8 -*-
"""V26: hot + cold + newly activated number mixtures, 10-number actual coupons.

Time-safe rule: select at the END of first SIX draws of each actual 12-draw
hour, evaluate ONLY subsequent SIX draws. 00:02..00:57, 01:02 standalone,
07:02..23:57. No fake draws during night break.

Definitions fixed before testing:
HOT = appeared >=3 times in first6.
COLD = appeared 0 times in first6.
NEWLY ACTIVATED = 0 appearances first3 and >=1 in next3.
These are NOT reliable predictors; they are features used in a blind test.

Candidate coupons:
 Karma433: 4 hot + 3 cold + 3 newly activated
 Karma334: 3 hot + 3 cold + 4 newly activated
 Karma343: 3 hot + 4 cold + 3 newly activated
 AileKarma433: same 4+3+3 with ranks informed by family stage,
               earlier companions, and prior state.
When a category has too few numbers, deterministically backfill and log
actual quota; no duplicate number, no future leakage.
Baselines: V25 AileDNA, Sıcak10, Soğuk10, Rastgele10, İlk6Havuz10.
Train ONLY first36 days to pick a mixture winner; test last36 days frozen.
Provide 0..10 hit distributions, 5+,6+,... and paired day uncertainty.
"""
from __future__ import annotations
import argparse
import json
import math
import random
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from v11_arastirma import read_draws
from v21_aile_yasam_dongusu import HOUR_STARTS, group_full_days, clock, key, csv_bytes
from v25_aile_dna_kupon import (
    new_state, update_history, choose_family_panel, coupon_sets,
    coupon_event, predict_satellites,
)

MIX_CONFIG={
    "Karma433":(4,3,3,False),
    "Karma334":(3,3,4,False),
    "Karma343":(3,4,3,False),
    "AileKarma433":(4,3,3,True),
}
BASELINES=("AileDNA","Sıcak10","Soğuk10","Rastgele10","İlk6Havuz10")
ALL_METHODS=tuple(MIX_CONFIG)+BASELINES
K_FIELDS=("Tarih","Saat","Kesim sıra")
CORE_STAGE_WEIGHTS={"İlk":0.35,"İki":1.15,"Üç+":0.9}


def classify(history):
    """Classify 80 numbers only using six known draws. Return disjoint pools."""
    if len(history)<6:raise ValueError("Need first6")
    first6=history[-6:]
    early=Counter(n for d in first6[:3] for n in d["nums"])
    late=Counter(n for d in first6[3:] for n in d["nums"])
    six=early+late
    prev=Counter(n for d in history[:-6][-12:] for n in d["nums"])
    seen_recent={}
    for d in history:
        for n in d["nums"]:
            seen_recent[n]=d["pos"]
    pos=history[-1]["pos"]
    hot={n for n in range(1,81) if six[n]>=3}
    newly={n for n in range(1,81) if early[n]==0 and late[n]>=1 and n not in hot}
    cold={n for n in range(1,81) if six[n]==0}
    mid=set(range(1,81))-hot-newly-cold
    assert not(hot&newly or hot&cold or newly&cold or hot&mid or cold&mid or newly&mid)
    assert sum(map(len,(hot,newly,cold,mid)))==80
    return {
        "hot":hot,"new":newly,"cold":cold,"mid":mid,
        "early":early,"late":late,"six":six,"prev":prev,
        "last":seen_recent,"pos":pos,
    }


def family_scores(panel,history):
    """Family evidence from known historical cores + their companions only."""
    score=Counter()
    for (k,stage),methods in panel.items():
        core=methods["Yakın"]
        w=CORE_STAGE_WEIGHTS[stage]*(1+0.18*(k-2))
        for n in core:score[n]+=w
        companions=predict_satellites(core,history)
        for n in companions:score[n]+=0.18*w
    return score


def mixed_ten(classification,quotas,score=None):
    """Deterministic pick, preserve unique balls, log shortfall/backfill.

    Priority hot -> new -> cold, but reported quotas reflect actual category,
    not fictitious requested membership.
    """
    qhot,qcold,qnew=quotas
    if qhot+qcold+qnew!=10:
        raise ValueError("Quota sum must equal ten")
    if score is None:score=Counter()
    six=classification["six"]
    late=classification["late"]
    prev=classification["prev"]
    last=classification["last"]
    pos=classification["pos"]

    def rank_hot(n):
        return (-score[n],-six[n],-late[n],n)

    def rank_new(n):
        return (-score[n],-late[n],-prev[n],n)

    def rank_cold(n):
        # A "rested" prior frequent number earns earlier position.
        # No evidence this is predictive; the holdout determines that.
        return (-score[n],-prev[n],pos-last.get(n,0),n)

    selected=[]
    for category,amount,fn in (
        ("hot",qhot,rank_hot),("new",qnew,rank_new),
        ("cold",qcold,rank_cold)
    ):
        selected.extend(sorted(classification[category],key=fn)[:amount])
    used=set(selected)
    if len(used)!=len(selected):raise AssertionError("Pool overlap")
    if len(selected)<10:
        remaining=sorted((n for n in range(1,81) if n not in used),
                         key=lambda n:(-score[n],-six[n],-late[n],n))
        selected.extend(remaining[:10-len(selected)])
    assert len(selected)==10 and len(set(selected))==10
    actual={k:len(set(selected)&classification[k])
            for k in ("hot","cold","new","mid")}
    return tuple(sorted(selected)),actual


def snapshot(date,start,history,first6=None):
    """Single pure cutoff snapshot for both historical and partial/live days."""
    if len(history)<start+5:
        raise ValueError("Not enough real first-six results")
    if [d["pos"] for d in history[:start+5]]!=list(range(1,start+6)):
        raise ValueError("Incomplete day history")
    cutoff=start+5
    known=history[:cutoff]
    first=known[-6:] if first6 is None else first6
    if [d["pos"] for d in first]!=list(range(start,start+6)):
        raise ValueError("First six are not the selected real hourly window")
    state=new_state()
    for d in known:
        update_history(state,d)
    panel,hot12,hot6=choose_family_panel(date,cutoff,state,known,first)
    klass=classify(known)
    fam_score=family_scores(panel,known)
    coupons={}
    categories={}
    for mode,(h,c,n,aware) in MIX_CONFIG.items():
        coupon,actual=mixed_ten(klass,(h,c,n),fam_score if aware else Counter())
        coupons[mode]=coupon
        categories[mode]=actual
    baselines=coupon_sets(date,start,panel,hot12,hot6,known)
    coupons.update(baselines)
    assert set(coupons)==set(ALL_METHODS)
    assert all(len(set(v))==len(v)==10 for v in coupons.values())
    signals={
        "date":date,"start":start,"cutoff":cutoff,
        "hot":len(klass["hot"]),"cold":len(klass["cold"]),
        "new":len(klass["new"]),"mid":len(klass["mid"]),
        "hot_nums":tuple(sorted(klass["hot"])),
        "cold_nums":tuple(sorted(klass["cold"])),
        "new_nums":tuple(sorted(klass["new"])),
        "category_counts":categories,
        "family_core_count":len(panel),
    }
    return coupons,signals


def evaluate_day(date,draws):
    if len(draws)!=217 or [d["pos"] for d in draws]!=list(range(1,218)):
        raise ValueError("217 complete ordered draws required")
    coupons_out=[]
    signal_rows=[]
    for start in HOUR_STARTS:
        # Does not inspect draws after start+5 when constructing coupons.
        selected,signals=snapshot(date,start,draws[:start+5])
        target=draws[start+5:start+11]
        assert [d["pos"] for d in target]==list(range(start+6,start+12))
        for mode,nums in selected.items():
            r=coupon_event(date,start,mode,nums,target)
            actual=signals["category_counts"].get(mode,{})
            r.update({
                "İstenen sıcak": MIX_CONFIG[mode][0] if mode in MIX_CONFIG else "",
                "İstenen soğuk": MIX_CONFIG[mode][1] if mode in MIX_CONFIG else "",
                "İstenen yeni": MIX_CONFIG[mode][2] if mode in MIX_CONFIG else "",
                "Gerçek sıcak":actual.get("hot",""),
                "Gerçek soğuk":actual.get("cold",""),
                "Gerçek yeni":actual.get("new",""),
                "Gerçek diğer":actual.get("mid",""),
            })
            coupons_out.append(r)
        signal_rows.append({
            "Tarih":date,"Saat":clock(start)[0],"Kesim sıra":start+5,
            "Kesim anı":clock(start+5)[0],
            "Sıcak sayı havuzu >=3/6":signals["hot"],
            "Soğuk sayı havuzu 0/6":signals["cold"],
            "Yeni aktif havuzu ilk3=0 son3>=1":signals["new"],
            "Diğer":signals["mid"],
            "Sıcak sayılar":key(signals["hot_nums"]),
            "Soğuk sayılar":key(signals["cold_nums"]),
            "Yeni aktif sayılar":key(signals["new_nums"]),
            "Aile çekirdek evre sayısı":signals["family_core_count"],
            "Karma433 gerçek dağılım":json.dumps(signals["category_counts"]["Karma433"],ensure_ascii=False),
            "Karma334 gerçek dağılım":json.dumps(signals["category_counts"]["Karma334"],ensure_ascii=False),
            "Karma343 gerçek dağılım":json.dumps(signals["category_counts"]["Karma343"],ensure_ascii=False),
        })
    return coupons_out,signal_rows


def fit_first36(coupons):
    grouped=defaultdict(list)
    for row in coupons:
        if row["Dönem"]=="İlk36" and row["Yöntem"] in MIX_CONFIG:
            grouped[row["Yöntem"]].append(row)
    options=[]
    for mode in MIX_CONFIG:
        rows=grouped[mode]
        if len(rows)!=36*18:raise AssertionError("Missing training windows")
        total=sum(x["6 çekiliş toplam isabet"] for x in rows)
        five=sum(x["6 çekiliş 5+"] for x in rows)
        options.append((mode,total,five))
    winner=max(options,key=lambda x:(x[1],x[2],-list(MIX_CONFIG).index(x[0])))[0]
    return winner,[{
        "Dönem":"İlk36","Yöntem":name,
        "Saat":len(grouped[name]),"Hedef çekiliş":len(grouped[name])*6,
        "Toplam isabet":total,"5+ isabet":five,
        "İsabet/çekiliş":round(total/(6*len(grouped[name])),6),
        "Yalnız öğrenmeden seçilen":name==winner
    } for name,total,five in options]


def result_rows(coupons,chosen):
    groups=defaultdict(list)
    for x in coupons:groups[(x["Dönem"],x["Yöntem"])].append(x)
    result=[]
    for period in ("İlk36","Son36"):
        for mode in ALL_METHODS:
            rows=groups[(period,mode)]
            if not rows:continue
            h=Counter()
            for row in rows:
                for i in range(1,7):
                    h[row[f"Hedef {i}"]]+=1
            n=sum(h.values())
            assert n==6*len(rows)
            result.append({
                "Dönem":period,"Yöntem":mode,"10lu kupon":len(rows),
                "Hedef çekiliş":n,"Toplam isabet":sum(k*v for k,v in h.items()),
                "Ortalama isabet":round(sum(k*v for k,v in h.items())/n,6),
                "5+":sum(v for k,v in h.items() if k>=5),
                "6+":sum(v for k,v in h.items() if k>=6),
                "7+":sum(v for k,v in h.items() if k>=7),
                "8+":sum(v for k,v in h.items() if k>=8),
                "9+":sum(v for k,v in h.items() if k>=9),
                "10/10":h[10],
                **{f"{k}/10":h[k] for k in range(11)},
                "İlk36 seçilen karma":mode==chosen
            })
    return result


def daily_paired_ci(coupons,winner):
    sample=defaultdict(dict)
    for r in coupons:
        if r["Dönem"]=="Son36":
            sample[(r["Tarih"],r["Saat"])][r["Yöntem"]]=r
    dates=sorted({d for d,t in sample})
    out=[]
    baseline_modes=("Rastgele10","İlk6Havuz10","AileDNA","Sıcak10","Soğuk10")
    for comp in baseline_modes:
        diffs=[]
        five_diffs=[]
        for date in dates:
            pairs=[v for (d,t),v in sample.items() if d==date]
            assert len(pairs)==18
            diffs.append(sum(v[winner]["6 çekiliş toplam isabet"]-
                             v[comp]["6 çekiliş toplam isabet"]
                             for v in pairs)/(18*6))
            five_diffs.append(sum(v[winner]["6 çekiliş 5+"]-
                                  v[comp]["6 çekiliş 5+"]
                                  for v in pairs)/(18*6))
        for measure,vals in (("Çekiliş başına sayı isabet farkı",diffs),
                             ("Çekiliş başına 5+ farkı",five_diffs)):
            m=mean(vals)
            se=(sum((x-m)**2 for x in vals)/(len(vals)-1)/len(vals))**0.5
            lo=m-1.96*se;hi=m+1.96*se
            out.append({
                "Seçilen karma":winner,"Kıyas":comp,"Ölçüt":measure,
                "Test günü":len(vals),"Günlük kümeli ortalama fark":round(m,7),
                "Yaklaşık 95% GA alt":round(lo,7),
                "Yaklaşık 95% GA üst":round(hi,7),
                "Güvenilir üstünlük":lo>0,
                "Not":"36 gün günlük kümeli yaklaşık aralık, geçmiş veriye dayalı geliştirme "
                      "ve çoklu karşılaştırmalar için temkinli yorumlanmalıdır",
            })
    return out


def rng_distribution(n):
    nden=math.comb(80,10)
    prob={k:math.comb(20,k)*math.comb(60,10-k)/nden for k in range(11)}
    return [{
        "Tam isabet":k,"Adil RNG tek çekiliş olasılığı":round(prob[k],10),
        "Test 3888 çekilişte beklenen":round(n*prob[k],4),
    } for k in range(11)]


def run(data):
    draws,errors=read_draws(data)
    full,missing=group_full_days(draws)
    if len(full)<72:raise ValueError(f"Expected at least 72 full days, got {len(full)}")
    # Historical split matched to prior V25 reproducible exactly.
    full=full[:72]
    coupons=[];signals=[]
    for i,(date,draws) in enumerate(full):
        a,b=evaluate_day(date,draws)
        for x in a:x["Dönem"]="İlk36" if i<36 else "Son36"
        for x in b:x["Dönem"]="İlk36" if i<36 else "Son36"
        coupons+=a;signals+=b
    winner,fit=fit_first36(coupons)
    performance=result_rows(coupons,winner)
    ci=daily_paired_ci(coupons,winner)
    fair=rng_distribution(36*18*6)
    meta={
        "Motor":"V26 Karma Sıcak-Soğuk-Yeni Aktif AileDNA",
        "Veri":"GitHub veri.txt",
        "Tam gün":len(full),"Çekiliş":len(full)*217,"6+6 saat":len(full)*18,
        "İlk gün":full[0][0],"Son gün":full[-1][0],
        "Öğrenme":[full[0][0],full[35][0]],
        "Kör test":[full[36][0],full[-1][0]],
        "Seçilen tek karma":winner,
        "Motorlar":list(ALL_METHODS),
        "Tanım sıcak":"İlk 6 çekilişin en az 3'ünde görülen",
        "Tanım soğuk":"İlk 6 çekilişte hiç görülmeyen",
        "Tanım yeni":"İlk 3'te yok, 4–6'dan en az birinde var; sıcakla çakışanlar sıcak havuzuna ayrılır",
        "Aile aşaması":"İlk/2/3+ çekirdek ve geçmiş eşlikçileri seçimde dikkate alınabilir",
        "Bulanık kota":"Kategori yeterli değilse boş kontenjan diğer gruptan doldurulur; fiili grup miktarı kaydedilir",
        "Doğrulama":"Tahmin kesim sıra start+5; bütün altı hedef start+6..start+11",
        "Özel gece":"01:02→07:02 altı gerçek saat; arada hayali beş dakikalık çekiliş yok",
        "Veri hatası":errors,"Tam olmayan günler":missing,
        "Uyarı":"Sıcak/soğuk/dönüş aile etiketleri rastgele çekilişte öngörü gücü kanıtlamaz. "
                "Geçmiş üstünde geliştirilmiş stratejiler canlı gelecekte değiştirilmeden sınanmalıdır.",
    }
    files={
        "ozet.json":json.dumps(meta,ensure_ascii=False,indent=2).encode("utf-8"),
        "72_gun_6li_saat_sicak_soguk_yeni_havuzlar.csv":csv_bytes(signals),
        "72_gun_kuponlar_ve_tum_0_10_isabetler.csv":csv_bytes(coupons),
        "ilk36_karma_model_secimi.csv":csv_bytes(fit),
        "son36_0_10_isabet_ozeti.csv":csv_bytes(performance),
        "son36_gunluk_eslesik_guven_araligi.csv":csv_bytes(ci),
        "adil_rng_10lu_kupon_isabet_dagilimi.csv":csv_bytes(fair),
    }
    return files,meta,performance,ci


def main():
    ap=argparse.ArgumentParser(description="V26 hot cold activating mixed 10-number coupons")
    ap.add_argument("--data",default="veri.txt")
    ap.add_argument("--output",default="V26_KARMA_72_GUN_10LU_KUPON_KOR_TEST.zip")
    args=ap.parse_args()
    parts,meta,results,conf=run(Path(args.data).read_text(encoding="utf-8-sig"))
    with zipfile.ZipFile(args.output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,data in parts.items():z.writestr(name,data)
    print("V26_PASS",json.dumps({k:meta[k] for k in ("Tam gün","Çekiliş","6+6 saat","Seçilen tek karma")},ensure_ascii=False),flush=True)
    for row in results:
        if row["Dönem"]=="Son36":
            print("V26_TEST",json.dumps(row,ensure_ascii=False),flush=True)
    for row in conf: print("V26_CI",json.dumps(row,ensure_ascii=False),flush=True)
    print("V26_ZIP",args.output,flush=True)


if __name__=="__main__":
    main()
