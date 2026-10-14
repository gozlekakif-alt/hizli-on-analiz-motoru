# -*- coding: utf-8 -*-
"""V42 — five MOVING temperature pools, quota before identity, formation repeats.

Recreates the older, historically documented 72-draw-count strata:
SOGUK 0..14 / SERIN 15..16 / NOTR 17..19 / ILIK 20..21 / SICAK 22..72.
Pool capacities FLOAT naturally; these are NOT V40's fixed six bins.

At every t: observe exactly the last 72 REAL previously recorded draws;
freeze baseline (sizes/4) and online-calibrated five quotas summing to 20,
and 20-name lists. ONLY THEN inspect t's true 20 numbers. Compare quota
exact / within ±1 per pool / all-five simultaneous to exact multi-variate
hypergeometric null probabilities, not to naive single-bin accuracy.
Also audit exact-set 20/20 repeats versus recurring 5-pool and 8-band
FORMATION signatures. Never assert previously observed t is foreseen.
"""
from __future__ import annotations

import csv
import hashlib
import io
import itertools
import json
import math
import random
import statistics
import zipfile
from collections import Counter,defaultdict,deque
from functools import lru_cache

from v36_rng_davranis_klonu import sorted_draws,on_slot
from v11_arastirma import hour_draw_index

VERSION="V42.1"
POOL_NAMES=("SOGUK","SERIN","NOTR","ILIK","SICAK")
BOUNDS=(14,16,19,21,72)
METHOD_QUOTA=("BOYUT_YUZDE25","KALIBRE_HAREKETLI")
METHOD_TICKET=("KOTA_YON_KIMLIK","KOTA_ICI_RASTGELE","SERBEST_RNG20")
CSV=dict(delimiter=";",lineterminator="\n")
TOTAL_COMB=math.comb(80,20)
QCOLS=("gun","sira","cekilis_no","saat","donem","pencere",
       "onceki_cekilis_no","aday_soguk","aday_serin","aday_notr",
       "aday_ilik","aday_sicak","kota_yontemi","kota_soguk",
       "kota_serin","kota_notr","kota_ilik","kota_sicak",
       "gercek_soguk","gercek_serin","gercek_notr","gercek_ilik",
       "gercek_sicak","tam_kota_eslesme","tum_5_havuz_artieksi1",
       "toplam_mutlak_hata","en_buyuk_kota_hatasi",
       "rng_tam_kota_olasiligi","rng_tum5_artieksi1_olasiligi",
       "onceki20den_tekrar","onceki60tan_gelen",
       "gercek20_imzasi","gercek_bant8_imzasi","surum")
PCOLS=("gun","sira","cekilis_no","donem","pencere","havuz",
       "kota_yontemi","havuz_adayi","kota","gercek","hata",
       "tam_dogru","artieksi1","rng_artieksi1_olasiligi")
TCOLS=("gun","sira","cekilis_no","donem","pencere","kimlik_yontemi",
       "hedef_oncesinde_donduruldu","secilen20","gercek20",
       "isabet","isabet_sayilari","surum")
SCOLS=("donem","pencere","kota_yontemi","hedef_cekilis",
       "tum5_tam","tum5_tam_pct","tum5_artieksi1",
       "tum5_artieksi1_pct","rng_tum5_artieksi1_beklenen_pct",
       "toplam_mutlak_hata_ort","havuz_adedi","havuz_artieksi1_pct",
       "rng_havuz_artieksi1_beklenen_pct")
ICOLS=("donem","pencere","kimlik_yontemi","hedef_cekilis",
       "ortalama_isabet","en_yuksek_isabet","isabet10plus",
       "isabet12plus","isabet14plus","isabet16plus",
       "dagilim_0_20")
REPCOLS=("imza_tipi","imza","gorunme","ilk_gun",
         "ilk_cekilis_no","son_gun","son_cekilis_no")
DAYCOLS=("donem","pencere","kota_yontemi","gun",
         "cekilis","tum5_artieksi1","rng_beklenen_tum5_artieksi1",
         "mutlak_hata_toplam")


def label(c):
    for i,upper in enumerate(BOUNDS):
        if c<=upper:return i
    raise ValueError(c)


def histogram72(history):
    if len(history)<72:return None
    tally=Counter(n for entry in history for n in entry)
    bins=tuple(label(tally[n]) for n in range(1,81))
    counts=tuple(bins.count(i) for i in range(5))
    assert sum(counts)==80
    return bins,counts


def largest_remainder(weights,capacity,total=20):
    """Deterministic Hamilton apportionment with hard bucket capacities."""
    if len(weights)!=len(capacity):raise ValueError("shape mismatch")
    if sum(capacity)<total or any(w<0 for w in weights):
        raise ValueError("negative weight or insufficient seats")
    if not any(weights):weights=list(capacity)
    weights=[float(x) for x in weights]
    amount=[w*total/sum(weights) for w in weights]
    quotas=[min(capacity[i],int(math.floor(amount[i]))) for i in range(len(weights))]
    while sum(quotas)<total:
        spare=[i for i in range(len(weights)) if quotas[i]<capacity[i]]
        selected=max(spare,key=lambda i:(amount[i]-quotas[i],capacity[i]-quotas[i],-i))
        quotas[selected]+=1
    while sum(quotas)>total:
        selected=max((i for i in range(len(weights)) if quotas[i]>0),
                     key=lambda i:(quotas[i]-amount[i],quotas[i],i))
        quotas[selected]-=1
    assert sum(quotas)==total and all(0<=q<=n for q,n in zip(quotas,capacity))
    return tuple(quotas)


@lru_cache(maxsize=250000)
def hypergeom_within1(n,q):
    lo=max(0,q-1,20-(80-n))
    hi=min(n,q+1,20)
    return sum(math.comb(n,k)*math.comb(80-n,20-k) for k in range(lo,hi+1))/TOTAL_COMB


@lru_cache(maxsize=35000)
def hypergeom_all_five(capacity,quotas):
    """Exact fair 20-from-80 chance for *this particular pre-frozen* vector."""
    assert len(capacity)==len(quotas)==5
    assert sum(capacity)==80 and sum(quotas)==20
    exact=math.prod(math.comb(n,q) for n,q in zip(capacity,quotas))/TOTAL_COMB
    allowable=[range(max(0,q-1),min(n,q+1)+1)
               for n,q in zip(capacity,quotas)]
    total=0
    for ks in itertools.product(*allowable):
        if sum(ks)!=20:continue
        total+=math.prod(math.comb(n,k) for n,k in zip(capacity,ks))
    return exact,total/TOTAL_COMB


def rng_for(day,pos,method):
    seed=int(hashlib.sha256(
        f"{VERSION}|{day}|{pos}|{method}".encode()).hexdigest()[:16],16)
    return random.Random(seed)


def fmt(seq):
    return ",".join(str(n) for n in sorted(seq))


def pick_names(day,pos,method,groups,quotas,history):
    assert len(groups)==80 and sum(quotas)==20
    rng=rng_for(day,pos,method)
    if method=="SERBEST_RNG20":
        return frozenset(rng.sample(range(1,81),20))
    prior=list(history)
    trailing6=prior[-6:]
    former6=prior[-12:-6]
    last=frozenset(prior[-1]) if prior else frozenset()
    rank=[]
    for n in range(1,81):
        a=sum(n in d for d in trailing6)
        b=sum(n in d for d in former6)
        rate=a/max(1,len(trailing6))
        slope=rate-b/max(1,len(former6))
        # A fixed exploratory identity formula; NO target-t information.
        score=.50*rate+.30*slope+.20*int(n in last)
        rank.append(score)
    poolmap=defaultdict(list)
    for n,cat in enumerate(groups,1):poolmap[cat].append(n)
    selected=set()
    for cat,k in enumerate(quotas):
        candidates=poolmap[cat]
        if method=="KOTA_YON_KIMLIK":
            keyed=sorted(candidates,key=lambda n:(rank[n-1],rng.random()),reverse=True)
            selected.update(keyed[:k])
        elif method=="KOTA_ICI_RASTGELE":
            selected.update(rng.sample(candidates,k))
        else:raise ValueError(method)
    if len(selected)!=20:raise AssertionError("All twenty identities must be distinct")
    return frozenset(selected)


def csv_write(z,name,cols,rows):
    with z.open(name,"w") as raw:
        file=io.TextIOWrapper(raw,encoding="utf-8-sig",newline="",write_through=True)
        w=csv.DictWriter(file,fieldnames=cols,extrasaction="ignore",**CSV)
        w.writeheader()
        for row in rows:w.writerow(row)
        file.flush();file.detach()


def _summaries(quotas,pools,tickets):
    sums=[];ids=[]
    for phase in ("EGITIM","TEST"):
      for window in ("TUM","7_12"):
        for model in METHOD_QUOTA:
            q=[x for x in quotas if x["donem"]==phase and
                (window=="TUM" or x["pencere"]=="7_12") and
                x["kota_yontemi"]==model]
            sub=[x for x in pools if x["donem"]==phase and
                (window=="TUM" or x["pencere"]=="7_12") and
                x["kota_yontemi"]==model]
            if not q:continue
            sums.append({"donem":phase,"pencere":window,"kota_yontemi":model,
                "hedef_cekilis":len(q),
                "tum5_tam":sum(x["tam_kota_eslesme"] for x in q),
                "tum5_tam_pct":round(100*sum(x["tam_kota_eslesme"] for x in q)/len(q),4),
                "tum5_artieksi1":sum(x["tum_5_havuz_artieksi1"] for x in q),
                "tum5_artieksi1_pct":round(100*sum(x["tum_5_havuz_artieksi1"] for x in q)/len(q),4),
                "rng_tum5_artieksi1_beklenen_pct":round(100*statistics.mean(
                    x["rng_tum5_artieksi1_olasiligi"] for x in q),4),
                "toplam_mutlak_hata_ort":round(statistics.mean(
                    x["toplam_mutlak_hata"] for x in q),5),
                "havuz_adedi":len(sub),
                "havuz_artieksi1_pct":round(100*sum(x["artieksi1"] for x in sub)/len(sub),4),
                "rng_havuz_artieksi1_beklenen_pct":round(100*statistics.mean(
                    x["rng_artieksi1_olasiligi"] for x in sub),4)})
        for method in METHOD_TICKET:
            t=[x for x in tickets if x["donem"]==phase and
                (window=="TUM" or x["pencere"]=="7_12") and
                x["kimlik_yontemi"]==method]
            if not t:continue
            hits=[int(x["isabet"]) for x in t]
            cnt=Counter(hits)
            ids.append({"donem":phase,"pencere":window,"kimlik_yontemi":method,
                "hedef_cekilis":len(hits),
                "ortalama_isabet":round(statistics.mean(hits),5),
                "en_yuksek_isabet":max(hits),
                "isabet10plus":sum(h>=10 for h in hits),
                "isabet12plus":sum(h>=12 for h in hits),
                "isabet14plus":sum(h>=14 for h in hits),
                "isabet16plus":sum(h>=16 for h in hits),
                "dagilim_0_20":json.dumps([cnt.get(i,0) for i in range(21)])})
    return sums,ids


def _bootstrap_by_day(grouprows,metric,iterations=1600):
    # Paired daily error improvements; never treat all draws in one day as iid.
    train=defaultdict(lambda:[0.,0])
    for row in grouprows:
        value=float(row[metric])
        train[row["gun"]][0]+=value
        train[row["gun"]][1]+=1
    groups=list(train.values())
    if not groups:return None
    rng=random.Random(4202026)
    sims=[]
    for _ in range(iterations):
        sampled=[groups[rng.randrange(len(groups))] for _ in groups]
        sims.append(sum(x[0] for x in sampled)/sum(x[1] for x in sampled))
    sims.sort()
    return [round(sims[int(len(sims)*.025)],6),
            round(sims[min(len(sims)-1,int(len(sims)*.975))],6)]


def audit_sets_and_formations(rows,days):
    occurrences=Counter();first={};last={}
    seen_sets=Counter()
    pair_overlap=Counter()
    last20=None
    prev_sig=None
    history_by_type=defaultdict(Counter)
    for day,block in days:
        for d in block:
            true=frozenset(d["nums"])
            seen_sets[tuple(sorted(true))]+=1
            if last20 is not None:pair_overlap[len(true&last20)]+=1
            last20=true
    for row in rows:
        if row["kota_yontemi"]!="BOYUT_YUZDE25":continue
        cats=tuple(row[f"gercek_{t}"] for t in
                   ("soguk","serin","notr","ilik","sicak"))
        key=("5_SICAKLIK_KOTASI",",".join(str(k) for k in cats))
        history_by_type[key[0]][key[1]]+=1
        occurrences[key]+=1
        first.setdefault(key,(row["gun"],row["cekilis_no"]))
        last[key]=(row["gun"],row["cekilis_no"])
        bands=row["gercek_bant8_imzasi"]
        key=("8_ONLUK_BANT",bands)
        history_by_type[key[0]][key[1]]+=1
        occurrences[key]+=1
        first.setdefault(key,(row["gun"],row["cekilis_no"]))
        last[key]=(row["gun"],row["cekilis_no"])
    repeated=[]
    for (name,sig),count in sorted(occurrences.items(),
                          key=lambda x:(-x[1],x[0])):
        f=first[(name,sig)];l=last[(name,sig)]
        repeated.append({"imza_tipi":name,"imza":sig,"gorunme":count,
            "ilk_gun":f[0],"ilk_cekilis_no":f[1],
            "son_gun":l[0],"son_cekilis_no":l[1]})
    n=sum(len(block) for _,block in days)
    exact_pairs=sum(c*(c-1)//2 for c in seen_sets.values())
    return repeated,{"complete_actual_draws_checked":n,
        "exact_20_sets_unique":len(seen_sets),
        "exact_20_sets_repeated_pairs":exact_pairs,
        "fair_random_expected_exact20_duplicate_pairs":n*(n-1)/2/TOTAL_COMB,
        "unique_possible20_combinations":TOTAL_COMB,
        "max_exact20_set_occurrences":max(seen_sets.values()),
        "five_pool_formation_unique":len(history_by_type["5_SICAKLIK_KOTASI"]),
        "five_pool_formation_repeated_patterns":sum(
            c>=2 for c in history_by_type["5_SICAKLIK_KOTASI"].values()),
        "eight_band_formation_unique":len(history_by_type["8_ONLUK_BANT"]),
        "eight_band_formation_repeated_patterns":sum(
            c>=2 for c in history_by_type["8_ONLUK_BANT"].values()),
        "consecutive_actual20_overlap_histogram":{
             str(k):v for k,v in sorted(pair_overlap.items())},
        "caution":"Full unordered 20 identity repeat has tiny probability under fair RNG; recurring formation signatures are normal and are not predictive proof."}


def study(draws,include_partial=False,progress=None):
    days,full,warnings=sorted_draws(draws,include_partial)
    cutoff=days[len(days)//2][0]
    observed=deque(maxlen=72)
    recent12=deque(maxlen=12)
    adapt=defaultdict(lambda:[0,0])
    qrows=[];prows=[];tickets=[]
    all_draws=sum(len(v) for _,v in days)
    progressed=0
    for day,block in days:
        phase="EGITIM" if day<cutoff else "TEST"
        for d in block:
            progressed+=1
            daypos=d["pos"];drawid=d["no"]
            snapshot=histogram72(observed)
            if snapshot is not None:
                groups,sizes=snapshot
                true=frozenset(d["nums"])
                actual=tuple(sum(groups[n-1]==i for n in true) for i in range(5))
                assert sum(actual)==20
                common=frozenset(observed[-1])
                previous_repeat=len(common&true)
                bandsig=",".join(str(sum((n-1)//10==i for n in true))
                                  for i in range(8))
                window="7_12" if hour_draw_index(daypos) in range(7,13) else "DIGER"
                pool_weights=tuple(sizes[i]*
                    (adapt[i][1]+.25*160)/(adapt[i][0]+160)
                    for i in range(5))
                baseline=largest_remainder(sizes,sizes)
                calibrated=largest_remainder(pool_weights,sizes)
                target_pools={m:q for m,q in zip(METHOD_QUOTA,(baseline,calibrated))}
                for model,q in target_pools.items():
                    expected_exact,expected_joint=hypergeom_all_five(sizes,q)
                    status=[int(abs(x-y)<=1) for x,y in zip(q,actual)]
                    qrows.append({"gun":day,"sira":daypos,"cekilis_no":drawid,
                       "saat":on_slot(daypos),"donem":phase,"pencere":window,
                       "onceki_cekilis_no":previous_no or "",
                       **{f"aday_{a}":v for a,v in
                          zip(("soguk","serin","notr","ilik","sicak"),sizes)},
                       "kota_yontemi":model,
                       **{f"kota_{a}":v for a,v in
                          zip(("soguk","serin","notr","ilik","sicak"),q)},
                       **{f"gercek_{a}":v for a,v in
                          zip(("soguk","serin","notr","ilik","sicak"),actual)},
                       "tam_kota_eslesme":int(q==actual),
                       "tum_5_havuz_artieksi1":int(all(status)),
                       "toplam_mutlak_hata":sum(abs(a-b) for a,b in zip(q,actual)),
                       "en_buyuk_kota_hatasi":max(abs(a-b) for a,b in zip(q,actual)),
                       "rng_tam_kota_olasiligi":round(expected_exact,10),
                       "rng_tum5_artieksi1_olasiligi":round(expected_joint,10),
                       "onceki20den_tekrar":previous_repeat,
                       "onceki60tan_gelen":20-previous_repeat,
                       "gercek20_imzasi":fmt(true),
                       "gercek_bant8_imzasi":bandsig,
                       "surum":VERSION})
                    for i,a in enumerate(POOL_NAMES):
                        prows.append({"gun":day,"sira":daypos,"cekilis_no":drawid,
                          "donem":phase,"pencere":window,"havuz":a,
                          "kota_yontemi":model,"havuz_adayi":sizes[i],
                          "kota":q[i],"gercek":actual[i],
                          "hata":actual[i]-q[i],
                          "tam_dogru":int(actual[i]==q[i]),
                          "artieksi1":status[i],
                          "rng_artieksi1_olasiligi":round(
                              hypergeom_within1(sizes[i],q[i]),10)})
                # All identity tickets are FROZEN BEFORE t.
                chosen={
                   "KOTA_YON_KIMLIK":pick_names(day,daypos,"KOTA_YON_KIMLIK",
                                               groups,calibrated,observed),
                   "KOTA_ICI_RASTGELE":pick_names(day,daypos,
                                  "KOTA_ICI_RASTGELE",groups,calibrated,observed),
                   "SERBEST_RNG20":pick_names(day,daypos,
                                               "SERBEST_RNG20",groups,calibrated,observed)}
                for method,selected in chosen.items():
                    intersection=selected&true
                    tickets.append({"gun":day,"sira":daypos,"cekilis_no":drawid,
                       "donem":phase,"pencere":window,"kimlik_yontemi":method,
                       "hedef_oncesinde_donduruldu":"EVET","secilen20":fmt(selected),
                       "gercek20":fmt(true),"isabet":len(intersection),
                       "isabet_sayilari":fmt(intersection),"surum":VERSION})
                # Once t scored, update each pool's historical rate counts.
                for i in range(5):
                    adapt[i][0]+=sizes[i]
                    adapt[i][1]+=actual[i]
            observed.append(frozenset(d["nums"]))
            previous_no=drawid
            if progress and (progressed%120==0 or progressed==all_draws):
                progress(progressed,all_draws,"V42 hareketli beş havuz",day)
    summary,ids=_summaries(qrows,prows,tickets)
    formations,audit=audit_sets_and_formations(qrows,days)
    # Day-block uncertainty paired quota differences (adaptive - baseline).
    compare={}
    for phase in ("EGITIM","TEST"):
      for window in ("TUM","7_12"):
        grouped=defaultdict(dict)
        for q in qrows:
            if q["donem"]!=phase or (
                window=="7_12" and q["pencere"]!="7_12"):continue
            grouped[(q["gun"],q["sira"])][q["kota_yontemi"]]=q
        paired=[]
        for record in grouped.values():
            if len(record)!=2:continue
            a=record["KALIBRE_HAREKETLI"]
            b=record["BOYUT_YUZDE25"]
            paired.append({"gun":a["gun"],
                 "abs_error_delta":a["toplam_mutlak_hata"]-b["toplam_mutlak_hata"],
                 "joint_success_delta":a["tum_5_havuz_artieksi1"]-b["tum_5_havuz_artieksi1"]})
        if paired:
            compare[phase+"_"+window]={
              "n":len(paired),
              "adaptive_minus_baseline_abs_error":round(
                  statistics.mean(p["abs_error_delta"] for p in paired),5),
              "delta95_by_day":_bootstrap_by_day(paired,"abs_error_delta"),
              "adaptive_minus_baseline_joint_within1":round(
                  statistics.mean(p["joint_success_delta"] for p in paired),5),
              "joint95_by_day":_bootstrap_by_day(paired,"joint_success_delta")}
    detailday=defaultdict(lambda:[0,0.,0.])
    for q in qrows:
        k=(q["donem"],q["pencere"],q["kota_yontemi"],q["gun"])
        values=detailday[k];values[0]+=1
        values[1]+=q["tum_5_havuz_artieksi1"]
        values[2]+=q["rng_tum5_artieksi1_olasiligi"]
    daytable=[]
    for (phase,window,model,day),(cnt,found,expected) in sorted(detailday.items()):
        daytable.append({"donem":phase,"pencere":window,
          "kota_yontemi":model,"gun":day,"cekilis":cnt,
          "tum5_artieksi1":int(found),
          "rng_beklenen_tum5_artieksi1":round(expected,5),
          "mutlak_hata_toplam":sum(x["toplam_mutlak_hata"] for x in qrows
            if x["donem"]==phase and x["pencere"]==window and
            x["kota_yontemi"]==model and x["gun"]==day)})
    meta={"version":VERSION,"total_full_days":len(full),
          "analyzed_days":len(days),
          "evaluated_targets":len(qrows)//len(METHOD_QUOTA),
          "all_real_draws":all_draws,
          "training_last_day":days[len(days)//2-1][0],
          "testing_first_day":cutoff,
          "history_lookback_real_draws":72,
          "dynamic_five_pool_thresholds":{
              "SOGUK":"H72 0..14","SERIN":"H72 15..16",
              "NOTR":"H72 17..19","ILIK":"H72 20..21","SICAK":"H72 22..72"},
          "five_buckets_capacity_variable":True,
          "all_five_quotas_sum20":True,
          "fair_rng_conditional_test":"exact multivariate hypergeometric conditional on each 80-ball previous-pool membership",
          "previous_20_vs_60":True,
          "target_identity_used_as_feature":False,
          "pretarget_quota_and_tickets_frozen":True,
          "limitations":"Older reported 60%+ per-pool ±1 can occur largely by chance at pool-size expected quotas. This test compares paired adaptive and simple quotas and exact conditional RNG reference. No RNG state recovered.",
          "source_warnings":warnings,
          "full20_identity_duplicate_audit":audit,
          "paired_quota_comparisons":compare}
    output=io.BytesIO()
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        csv_write(z,"01_CEKILIS_ONCESI_BES_HAVUZ_KOTA.csv",QCOLS,qrows)
        csv_write(z,"02_HER_HAVUZ_ARTI_EKSI_BIR_DENETIM.csv",PCOLS,prows)
        csv_write(z,"03_KOTADAN_20_SAYI_KIMLIGI_ISABET.csv",TCOLS,tickets)
        csv_write(z,"04_HAVUZ_KOTA_EGITIM_TEST_OZET.csv",SCOLS,summary)
        csv_write(z,"05_20_SAYI_KIMLIK_ISABET_OZET.csv",ICOLS,ids)
        csv_write(z,"06_TEKRARLAYAN_HAVUZ_VE_BANT_OLUSUM_IMZALARI.csv",REPCOLS,formations)
        csv_write(z,"07_GUN_GUN_KOTA_DENETIM.csv",DAYCOLS,daytable)
        z.writestr("08_BUTUN_SONUC_VE_KAYNAK.json",
             json.dumps(meta,ensure_ascii=False,indent=2).encode())
        z.writestr("00_OKU_ONCE.txt",(
          "V42 BES HAREKETLI HAVUZ: 20 SAYININ NASIL DOLDUGU\n"
          "=================================================\n"
          "1) 72 GERCEK onceki cekilisin frekansina gore 5 sinif:\n"
          "   SOGUK 0..14; SERIN 15..16; NOTR 17..19; ILIK 20..21;\n"
          "   SICAK 22+. Her sinifin mevcut kisi sayisi DEGISIR.\n"
          "2) t hedefi GORULMEDEN tum 80 numaranin havuzlari, 20\n"
          "   kontenjanli kota tahmini ve kota-ici 20 sayi listesi DONAR.\n"
          "3) Iki kota: havuzun buyuklugu %25 temel referans (Hamilton)\n"
          "   ve yalniz onceki gercek hedeflerle online kalibrasyon.\n"
          "4) Kota basarisi AYRI: her 5 sinifin arti eksi1 basarisi,\n"
          "   tum 5 ayni anda arti eksi1; tum 5 TAM. Bunlari birbirine\n"
          "   karistirma. Basit kotanin da %60-70 gibi tek-havuz arti1\n"
          "   basarilari adil RNG'de olağan olabilir.\n"
          "5) Gercek20 gelince isabet/20 sayilir; SADECE SONRA ogren.\n"
          "6) Aynı 20 sayinin hic tekrarlanmamasi olagandir: C(80,20)\n"
          "   3,535,316,142,212,174,320 farkli tamsayi kumesi var.\n"
          "7) Ama 5 kota ve 8 bant imzalari sik tekrar edebilir:\n"
          "   bu 'olumsuz degil', ancak ileri dogrulama gerektirir.\n"
          "8) TUM tum gun; 7_12 ise saatin 7...12 hedef cekilisleri.\n"
          "9) Beklenen tum-5 arti1 orani her t icin 5 degisen havuz\n"
          "   hacmi ve gercek20 kosullu coklu hiper-geometrikten hesap.\n"
          "10) Sadece sonuc onceki gelecegi kullanir, 20/20 garanti yok.\n"
        ).encode("utf-8-sig"))
    with zipfile.ZipFile(io.BytesIO(output.getvalue())) as z:
        assert z.testzip() is None and len(z.namelist())==9
    return output.getvalue(),meta,summary,ids,formations


def run_from_text(txt,include_partial=False):
    from v11_arastirma import read_draws
    draws,warnings=read_draws(txt)
    result=study(draws,include_partial)
    result[1]["source_parser_warnings"]=len(warnings)
    return result
