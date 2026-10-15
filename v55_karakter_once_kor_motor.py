#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V55: predict lottery draw CHARACTER before selecting any numbers.

Prequential two-stage audit: fit only on past hours, freeze all six targets
after first six results, score character independently of 10-number coupon.
All 20/80 draws are treated as independent fair random unless evidence shows
a future-persistent deviation. NOT an RNG reverse-engineering system.
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

from v45_sinyal_kor_test import parse_draws
from v53_saatlik_degisen_aileler import BLOCKS

START_FORWARD=date(2026,10,16)
N_FORWARD_DAYS=14
MIN_TRAIN_HOURS=96
NEIGHBORS=48
SHRINK=0.55   # retain 45% unbiased prior even after matching historical hours
CHAR_MIN_AUDITS=180
TARGET_SIZE=10
CHAR_KEYS=("band","heat","overlap","pair","trio")
CONTROLS=("KARAKTER10","KARAKTERSIZ10","RASTGELE10")
PAIR_P=(20*19)/(80*79)
TRIO_P=(20*19*18)/(80*79*78)
BASELINE={"band":[2.5]*8,"heat":[4.0]*5,"overlap":5.0,
          "pair":PAIR_P,"trio":TRIO_P}
SLOT_BY_HOUR=[(b["code"],list(range(b["start"]-1,b["end"]))) for b in BLOCKS]

def _pick_family(first6,k):
    cnt=collections.Counter()
    import itertools
    for r in first6:
        for fam in itertools.combinations(sorted(r["nums"]),k):
            cnt[fam]+=1
    return sorted(cnt.items(),key=lambda kv:(-kv[1],kv[0]))[0]

def _ctx(history,first6):
    """Everything including labels defined using *only* prior72 and first6."""
    past=history[-72:]
    long_count=collections.Counter(n for row in past for n in row["nums"])
    rank=sorted(range(1,81),key=lambda n:(long_count[n],n))
    heat={n:idx//16 for idx,n in enumerate(rank)}
    first_band=[0]*8
    first_heat=[0]*5
    for row in first6:
        for n in row["nums"]:
            first_band[(n-1)//10]+=1
            first_heat[heat[n]]+=1
    overlaps=[len(first6[i]["nums"] & first6[i-1]["nums"]) for i in range(1,6)]
    pair,pair_support=_pick_family(first6,2)
    trio,trio_support=_pick_family(first6,3)
    anchor=frozenset(first6[-1]["nums"])
    return {
      "heat_map":heat,"count72":long_count,
      "band_first":[v/6 for v in first_band],
      "heat_first":[v/6 for v in first_heat],
      "overlap_first":sum(overlaps)/5,
      "pair":pair,"trio":trio,
      "pair_support":pair_support,"trio_support":trio_support,
      "anchor":anchor,
      "first6":first6,
      "features":tuple([(v/6-2.5)/1.1 for v in first_band]+
                       [(v/6-4.0)/1.3 for v in first_heat]+
                       [(sum(overlaps)/5-5)/1.6,
                        (pair_support-1.5)/1.2,
                        (trio_support-1)/1.0]),
    }

def _actual(ctx,targets):
    band=[0]*8
    heat=[0]*5
    total_overlap=0
    pair,trio=frozenset(ctx["pair"]),frozenset(ctx["trio"])
    pair_hits=trio_hits=0
    for r in targets:
        nums=r["nums"]
        for n in nums:
            band[(n-1)//10]+=1
            heat[ctx["heat_map"][n]]+=1
        total_overlap+=len(nums & ctx["anchor"])
        pair_hits+=int(pair.issubset(nums))
        trio_hits+=int(trio.issubset(nums))
    n=len(targets)
    return {"band":[x/n for x in band],"heat":[x/n for x in heat],
            "overlap":total_overlap/n,
            "pair":pair_hits/n,"trio":trio_hits/n}

def _distance(f,g):
    return sum((a-b)**2 for a,b in zip(f,g))

def predict(ctx,trained):
    if len(trained)<MIN_TRAIN_HOURS:
        return dict(band=BASELINE["band"][:],heat=BASELINE["heat"][:],
                    overlap=5.0,pair=PAIR_P,trio=TRIO_P,
                    trained=len(trained),mode="BAZ_TAHMIN")
    nearest=sorted(trained,key=lambda tr:_distance(ctx["features"],tr[0]))[:NEIGHBORS]
    weights=[1/(0.7+_distance(ctx["features"],f)) for f,y in nearest]
    den=sum(weights)
    def est(key):
        if isinstance(BASELINE[key],list):
            return [(1-SHRINK)*base+SHRINK*sum(w*y[key][i]
                       for w,(f,y) in zip(weights,nearest))/den
                    for i,base in enumerate(BASELINE[key])]
        return (1-SHRINK)*BASELINE[key]+SHRINK*sum(w*y[key]
                        for w,(f,y) in zip(weights,nearest))/den
    return {**{key:est(key) for key in CHAR_KEYS},
            "trained":len(trained),"mode":"KNN_KARAKTER"}

def _error(pred,actual,reference=False):
    root=BASELINE if reference else pred
    return {
      "band":sum(abs(a-b) for a,b in zip(root["band"],actual["band"]))/8,
      "heat":sum(abs(a-b) for a,b in zip(root["heat"],actual["heat"]))/5,
      "overlap":abs(root["overlap"]-actual["overlap"]),
      "pair":(root["pair"]-actual["pair"])**2,
      "trio":(root["trio"]-actual["trio"])**2,
    }

def _validation_gate(earlier_audits):
    """Validates forecast accuracy using STRICTLY EARLIER hours.
    To minimize cherry-picking, gate requires improvement in >=2
    character dimensions on last 180 scored hours.
    """
    qualified=[r for r in earlier_audits if r["trained"]>=MIN_TRAIN_HOURS]
    period=qualified[-CHAR_MIN_AUDITS:]
    if len(period)<CHAR_MIN_AUDITS:
        return False,0,{"band":0.0,"heat":0.0,"overlap":0.0}
    gains={k:sum(r[f"rng_{k}"]-r[f"model_{k}"] for r in period)/len(period)
           for k in ("band","heat","overlap")}
    # Minimal improvement beyond a trivial rounded fluctuation.
    accept=sum(v>0.005 for v in gains.values())>=2
    return accept,len(period),gains

def _apportion(values,n=10):
    total=sum(values)
    ideal=[v*n/total for v in values]
    floor=[int(math.floor(v)) for v in ideal]
    remaining=n-sum(floor)
    rank=sorted(range(len(values)),key=lambda i:(-(ideal[i]-floor[i]),i))
    for i in rank[:remaining]:floor[i]+=1
    return floor

def _coupon(ctx,pred,day,code):
    first=collections.Counter(n for r in ctx["first6"] for n in r["nums"])
    pair,trio=set(ctx["pair"]),set(ctx["trio"])
    def common(n):
        n72=ctx["count72"][n]
        return (0.65*(n72-18)/math.sqrt(13.5)
                +0.45*(first[n]-1.5)/math.sqrt(1.125)
                +0.10*int(n in pair)+0.06*int(n in trio))
    base=sorted(range(1,81),key=lambda n:(-common(n),n))
    unchanged=tuple(sorted(base[:10]))
    bands=_apportion(pred["band"])
    temps=_apportion(pred["heat"])
    selected=[]
    used_band=collections.Counter()
    used_heat=collections.Counter()
    while len(selected)<TARGET_SIZE:
        def score(n):
            b=(n-1)//10
            h=ctx["heat_map"][n]
            # Character prediction affects both counts and requested quotas.
            extra=(0.20*(pred["band"][b]-2.5)
                   +0.16*(pred["heat"][h]-4))
            family=(0.20*int(n in pair and pred["pair"]>PAIR_P+0.008)
                   +0.12*int(n in trio and pred["trio"]>TRIO_P+0.006))
            penalty=(0.85*max(0,used_band[b]+1-bands[b])
                    +0.75*max(0,used_heat[h]+1-temps[h]))
            return common(n)+extra+family-penalty
        remaining=[n for n in range(1,81) if n not in selected]
        chosen=min(remaining,key=lambda n:(-score(n),n))
        selected.append(chosen)
        used_band[(chosen-1)//10]+=1
        used_heat[ctx["heat_map"][chosen]]+=1
    rng=random.Random(int(hashlib.sha256(
        f"V55_FROZEN_RANDOM|{day}|{code}".encode()).hexdigest()[:24],16))
    control=tuple(sorted(rng.sample(range(1,81),10)))
    return {"KARAKTER10":tuple(sorted(selected)),
            "KARAKTERSIZ10":unchanged,
            "RASTGELE10":control,
            "band_quota":bands,"heat_quota":temps}

def audit(full):
    """Hour-at-a-time blind walk forward. Labels appended only AFTER predictions."""
    days=sorted(full)
    nforward=sorted(d for d in days if d>=START_FORWARD)[:N_FORWARD_DAYS]
    history=[];trained=[];past_checks=[]
    records=[];characters=[];next_preview=[]
    numwarm=0
    for day in days:
        phase=("ILERI_14" if day in nforward else
               "EK_ILERISI_HARIC" if day>=START_FORWARD else
               "GERIYE_DONUK")
        if phase=="EK_ILERISI_HARIC":
            # Future dataset beyond the first 14 days is not part of locked audit
            continue
        rows=full[day]
        for b in BLOCKS:
            hour=rows[b["start"]-1:b["end"]]
            first6=hour[:6]
            next6=hour[6:12]
            ctx=_ctx(history,first6)
            pred=predict(ctx,trained)
            signal,score_n,gains=_validation_gate(past_checks)
            tickets=_coupon(ctx,pred,str(day),b["code"])
            character={
              "day":str(day),"hour":b["code"],"phase":phase,
              "trained":pred["trained"],"method":pred["mode"],
              "signal":int(signal and pred["trained"]>=MIN_TRAIN_HOURS),
              "prior_validation_hours":score_n,
              "prior_band_gain":round(gains["band"],6),
              "prior_heat_gain":round(gains["heat"],6),
              "prior_overlap_gain":round(gains["overlap"],6),
              "pred_band":"|".join(f"{v:.3f}" for v in pred["band"]),
              "pred_heat":"|".join(f"{v:.3f}" for v in pred["heat"]),
              "pred_overlap":round(pred["overlap"],5),
              "pred_pair":round(pred["pair"],7),
              "pred_trio":round(pred["trio"],7),
              "actual_band":"","actual_heat":"","actual_overlap":None,
              "actual_pair":None,"actual_trio":None,
              "top_band_pred":max(range(8),key=lambda i:(pred["band"][i],-i))+1,
              "top_band_real":None,
              "pair_family":"-".join(map(str,ctx["pair"])),
              "trio_family":"-".join(map(str,ctx["trio"])),
              "char_coupon":"-".join(map(str,tickets["KARAKTER10"])),
              "baseline_coupon":"-".join(map(str,tickets["KARAKTERSIZ10"])),
              "rng_coupon":"-".join(map(str,tickets["RASTGELE10"])),
              "band_quota":"|".join(map(str,tickets["band_quota"])),
              "heat_quota":"|".join(map(str,tickets["heat_quota"])),
              "deployment":"KARAKTER10" if signal else "SINYAL_YOK",
            }
            # At this point neither 'actual' nor 'next6' is used to choose
            # features, forecasts, ticket numbers, or gate.
            actual=_actual(ctx,next6)
            model_err=_error(pred,actual)
            null_err=_error(pred,actual,True)
            for k in CHAR_KEYS:
                character[f"mae_model_{k}"]=round(model_err[k],6)
                character[f"mae_rng_{k}"]=round(null_err[k],6)
            character.update({
                "actual_band":"|".join(f"{v:.3f}" for v in actual["band"]),
                "actual_heat":"|".join(f"{v:.3f}" for v in actual["heat"]),
                "actual_overlap":round(actual["overlap"],5),
                "actual_pair":round(actual["pair"],7),
                "actual_trio":round(actual["trio"],7),
                "top_band_real":max(range(8),key=lambda i:(actual["band"][i],-i))+1,
            })
            characters.append(character)
            for t in next6:
                for mode in CONTROLS:
                    picked=tickets[mode]
                    successes=len(t["nums"].intersection(picked))
                    records.append({
                      "day":str(day),"phase":phase,"hour":b["code"],
                      "target_id":t["id"],"target_time":t["time"],
                      "signal":character["signal"],"deployed":int(mode=="KARAKTER10" and
                          bool(character["signal"])),"mode":mode,
                      "numbers":"-".join(map(str,picked)),
                      "hits":successes,"at_least6":int(successes>=6),
                      "at_least7":int(successes>=7),
                      "at_least8":int(successes>=8),
                      "at_least9":int(successes>=9),
                      "at_least10":int(successes==10),
                    })
            # ALL new supervision is admitted after complete hour score.
            past_checks.append({"trained":pred["trained"],**{
                f"rng_{k}":null_err[k] for k in CHAR_KEYS},**{
                f"model_{k}":model_err[k] for k in CHAR_KEYS}})
            trained.append((ctx["features"],actual))
            history.extend(hour)
    return characters,records

def metrics(characters,records):
    out=[]
    for phase in ("GERIYE_DONUK","ILERI_14"):
        cc=[r for r in characters if r["phase"]==phase]
        test_cc=[r for r in cc if r["trained"]>=MIN_TRAIN_HOURS]
        rr=[r for r in records if r["phase"]==phase]
        signal_hours=sum(x["signal"] for x in test_cc)
        for kind in ("band","heat","overlap","pair","trio"):
            if test_cc:
                model=sum(x[f"mae_model_{kind}"] for x in test_cc)/len(test_cc)
                rng=sum(x[f"mae_rng_{kind}"] for x in test_cc)/len(test_cc)
            else:model=rng=None
            out.append({"phase":phase,"metric":"KARAKTER_"+kind,
                        "samples":len(test_cc),"hours_with_signal":signal_hours,
                        "model":round(model,6) if model is not None else "",
                        "baseline":round(rng,6) if rng is not None else "",
                        "delta_model_minus_baseline":round(model-rng,6)
                        if model is not None else "","note":"smaller is better"})
        for gated in (False,True):
            for mode in CONTROLS:
                group=[r for r in rr if r["mode"]==mode and
                       (not gated or r["signal"])]
                obs=[r["hits"] for r in group]
                out.append({"phase":phase,"metric":("KUPON_SINYAL" if gated else
                    "KUPON_TUM")+"_"+mode,"samples":len(group),
                    "hours_with_signal":signal_hours,
                    "model":round(statistics.mean(obs),5) if obs else "",
                    "baseline":2.5 if obs else "",
                    "delta_model_minus_baseline":round(statistics.mean(obs)-2.5,5)
                       if obs else "",
                    "note":("8/10="+str(sum(x["at_least8"] for x in group))+
                            "; 7/10="+str(sum(x["at_least7"] for x in group))+
                            "; 10/10="+str(sum(x["at_least10"] for x in group)))})
    return out

def day_comparison(characters,records):
    rows=[]
    for day in sorted({x["day"] for x in characters}):
        cc=[x for x in characters if x["day"]==day and x["trained"]>=MIN_TRAIN_HOURS]
        rr=[x for x in records if x["day"]==day]
        row={"day":day,"phase":rr[0]["phase"] if rr else "",
             "hours_evaluated":len(cc),"signal_hours":sum(x["signal"] for x in cc)}
        for x in ("band","heat","overlap"):
            row[x+"_gain"]=round(sum(r["mae_rng_"+x]-r["mae_model_"+x] for r in cc),5)
        for m in CONTROLS:
            vals=[r["hits"] for r in rr if r["mode"]==m]
            row[m+"_avg"]=round(statistics.mean(vals),5) if vals else 0
            row[m+"_hits7"]=sum(r["at_least7"] for r in rr if r["mode"]==m)
        rows.append(row)
    return rows

def _write(z,name,cols,rows):
    with z.open(name,"w",force_zip64=True) as dst:
        tx=io.TextIOWrapper(dst,encoding="utf-8",newline="")
        wr=csv.writer(tx)
        wr.writerow(cols)
        for r in rows:wr.writerow([r.get(col,"") for col in cols])
        tx.flush();tx.detach()

CHAR_COLUMNS=("day","phase","hour","trained","method","signal",
    "prior_validation_hours","prior_band_gain","prior_heat_gain",
    "prior_overlap_gain","deployment","pred_band","actual_band",
    "pred_heat","actual_heat","pred_overlap","actual_overlap",
    "pred_pair","actual_pair","pred_trio","actual_trio",
    "top_band_pred","top_band_real","pair_family","trio_family",
    "char_coupon","baseline_coupon","rng_coupon","band_quota","heat_quota",
    "mae_model_band","mae_rng_band","mae_model_heat","mae_rng_heat",
    "mae_model_overlap","mae_rng_overlap","mae_model_pair","mae_rng_pair",
    "mae_model_trio","mae_rng_trio")

RECORD_COLUMNS=("day","phase","hour","target_id","target_time","signal",
    "deployed","mode","numbers","hits","at_least6","at_least7","at_least8",
    "at_least9","at_least10")
METRIC_COLUMNS=("phase","metric","samples","hours_with_signal",
                "model","baseline","delta_model_minus_baseline","note")

def build_zip(full,char,records,stats):
    buf=io.BytesIO()
    fwd=sorted(d for d in full if d>=START_FORWARD)[:N_FORWARD_DAYS]
    back=sorted(d for d in full if d<START_FORWARD)
    daily=day_comparison(char,records)
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        summary=[
            "V55 — ONCE OYUN KARAKTERI, SONRA SAYI SECIMI | KOR TEST",
            f"Kaynak: {len(full)} tam gün, {len(back)} geçmiş tam gün.",
            f"Gelecek: {START_FORWARD.isoformat()} sonrasi {len(fwd)}/{N_FORWARD_DAYS} tam gün.",
            f"Gun ici: 18 saat grubu (H00 13, kalanlar 17x12), her saat ilk6 -> sonraki6.",
            "Asama 1: Saatin ilk6'sından bir sonraki6 hedefin 8 bant",
            "payi (her bant adil beklenen 2.5), 5 sıcaklık grubu (4.0),",
            "son bilinen 20'likle hedef ortaklığı (5.0), seçili ikili/üçlü",
            "tekrar olasiligi tahmin edilir.",
            "Asama 2: Karaktere gore 10'lu kupon seçilir; ayni geçmiş",
            "verilerle ama KARAKTER tahmini olmadan secilen 10'lu ve",
            "ayni saat icinde dondurulan rastgele10 kontrol ile test edilir.",
            "KNN: YALNIZCA onceki saatlerin ornekleri; 48 en yakin saat,",
            "min 96 saat, yarisi adil varsayima yakın yumusatma.",
            "Sinyal filtresi: en az 180 onceki yeterli-egitimli saat",
            "ve band/heat/overlap 3 metrikten en az 2'sinde geçmişte",
            "adil baz tahminden anlamli kucuk hata. Aksi halde SINYAL YOK.",
            "Sinyal yok gunlerinde 10'lu listeler KONTROL AMACLI gölgede",
            "puanlanır; oyuncuya kupon sinyali olarak onerilmez.",
            "Geriye donuk model kıyaslamaları tarihte kod sabitlenmeden",
            "hesaplandı: V55 gelecekteki 14 tam günü ayri degerlendirir.",
            "Her bir hedefin sonucu o hedef için kuponu belirlemez.",
            "Başarı iddiası, tek bir 10/10 veya geçmişte iyi görünen",
            "birkaç hafta ile kurulamaz: karakter yanılma ve kupon kazanci",
            "her ikisi de yeni gunlerde kontrol üstünlüğü ister.",
            "",
            "OZET METRIKLER"
        ]
        for r in stats:
            summary.append(f"{r['phase']} {r['metric']}: {r['samples']} "
              f"örnek, motor {r['model']}, rastgele/fikse {r['baseline']}, "
              f"fark {r['delta_model_minus_baseline']} {r['note']}")
        z.writestr("00_OZET_VE_DURUM.txt","\n".join(summary)+"\n")
        _write(z,"01_KARAKTER_TAHMINI_VE_GERCEK.csv",CHAR_COLUMNS,char)
        _write(z,"02_SAYI_SECIMI_6_HEDEF_ISABETLER.csv",RECORD_COLUMNS,records)
        _write(z,"03_KARAKTER_VE_KUPON_METRIKLER.csv",METRIC_COLUMNS,stats)
        _write(z,"04_GUN_GUN_KARAKTER_ISABET.csv",
          ("day","phase","hours_evaluated","signal_hours",
           "band_gain","heat_gain","overlap_gain",
           "KARAKTER10_avg","KARAKTER10_hits7",
           "KARAKTERSIZ10_avg","KARAKTERSIZ10_hits7",
           "RASTGELE10_avg","RASTGELE10_hits7"),daily)
        z.writestr("05_KURAL_VE_KORLUK_DENETIMI.txt",
            "Sadece gerçekten KAYITLI 217/217 tam günler değerlendirildi.\n"
            "Her saat sonucu iki parçaya ayrılır, ilk 6 bilgi, son 6 hedef.\n"
            "01:02 gece 13. el ilk 6+son6 testine dahil değil, geçmişe dahildir.\n"
            "Sıcak havuzlar hedef görülmeden önce son72 sayısına göre 16'lı 5 grup.\n"
            "Karakter modeli uzun geçmişten en yakın saatleri seçer; saatler"
            " güncel son 6 hedefi görmeden eğitim örneğine eklenmez.\n"
            "Sinyal filtresi önceki saatlerin tamamlanmış karakter skoruyla "
            "güncellenir, aynı saatin sonucu etkileyemez.\n"
            "Gölgede değerlendirilen kuponlar SINYAL YOK durumunda önerilmez.\n"
            f"İleri test başlangıcı {START_FORWARD.isoformat()}, "
            f"ilk {N_FORWARD_DAYS} yeni tam gün, motor kurallarını değiştirerek "
            "bu aralıkta başarı aramak etik olmaz.\n"
            "Karakter sınıfları geçmiş çıkış sıklığının göreceli sınıflarıdır. "
            "Bağımsız ve adil RNG'yi çözdüğümüz anlamına gelmez.\n")
    return buf.getvalue()

def run(source):
    full,partial,broken,dupe=parse_draws(Path(source))
    char,records=audit(full)
    stats=metrics(char,records)
    result={
       "summary":{
         "full_days":len(full),"hours":len(char),
         "warmup_hours":sum(x["trained"]<MIN_TRAIN_HOURS for x in char),
         "forward_days":len(sorted(d for d in full if d>=START_FORWARD)[:N_FORWARD_DAYS]),
         "signals_back":sum(x["signal"] for x in char if x["phase"]=="GERIYE_DONUK"),
         "signals_forward":sum(x["signal"] for x in char if x["phase"]=="ILERI_14"),
         "bad_rows":len(broken)+len(dupe),"partial":partial,
       },"metrics":stats}
    return result,build_zip(full,char,records,stats)

def _selftest():
    assert sum(len(v) for _,v in SLOT_BY_HOUR)==217
    assert len(SLOT_BY_HOUR)==18
    def draw(day,idx,nums):
        from v45_sinyal_kor_test import SLOTS
        return {"day":day,"id":41000+idx,"time":SLOTS[idx],
                "nums":frozenset(nums)}
    a=set(range(1,21)); b=set(range(21,41))
    day=date(2026,10,1)
    rr=[draw(str(day),i,(a if i%2 else b)) for i in range(217)]
    ctx=_ctx(rr[:72],rr[72:78])
    assert len(ctx["heat_map"])==80
    assert len(ctx["features"])==16
    p=predict(ctx,[])
    assert p["mode"]=="BAZ_TAHMIN"
    pred=_coupon(ctx,p,str(day),"H07")
    assert all(len(set(pred[x]))==10 for x in CONTROLS)
    # Changing future six draw results does not change ticket/character.
    before=_coupon(ctx,p,str(day),"H07")
    rr[80]["nums"]=frozenset(range(50,70))
    assert before==_coupon(ctx,p,str(day),"H07")
    e=_actual(ctx,rr[78:84])
    assert abs(sum(e["band"])-20)<1e-9
    assert abs(sum(e["heat"])-20)<1e-9
    assert not _validation_gate([])[0]
    audited,records=audit({day:rr})
    assert len(audited)==18 and len(records)==18*6*len(CONTROLS)
    assert audited[0]["trained"]==0
    assert all(not r["signal"] for r in audited)
    assert all(r["hits"] in range(11) for r in records)
    zipped=build_zip({day:rr},audited,records,metrics(audited,records))
    with zipfile.ZipFile(io.BytesIO(zipped)) as z:
        assert len(z.namelist())==6
        assert len(list(csv.DictReader(io.StringIO(z.read(
            "01_KARAKTER_TAHMINI_VE_GERCEK.csv").decode()))))==18
    print("PASS V55: future-blind 2-stage character forecast, signal gate, 3 coupons, 6-file ZIP")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--output-dir",default="v55_artifacts")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:
        _selftest();return
    report,zipped=run(a.source)
    dst=Path(a.output_dir)
    dst.mkdir(parents=True,exist_ok=True)
    file=dst/"V55_ONCE_KARAKTER_SONRA_KUPON_KOR_TEK_RAPOR.zip"
    file.write_bytes(zipped)
    print(json.dumps({"file":str(file),**report},ensure_ascii=False,default=str))

if __name__=="__main__":
    main()
