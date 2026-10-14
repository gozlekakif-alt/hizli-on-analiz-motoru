# -*- coding: utf-8 -*-
"""V29: does temperature DWELL + DIRECTION foretell real next-20 membership?

Prospective 6->6 replay on 72 validated full Hızlı On days:
  * Streaming score across dates, EWMA half-life 12 real observed draws.
  * Freeze 80 numbers at end H6 of each 12-draw hour.
  * Six experimental equal-rank temperature layers (13,13,14,14,13,13).
  * Include 3-level cold/warm/hot, exact consecutive dwell, warming/cooling,
    first6 number appearances, and H1..H6 class changes.
  * Train first24 DAYS, choose among 6 PREDECLARED model variants on days25-36,
    test final36 untouched against mathematical 0.25, hot/cold and fixed-seed
    random 20-ball/10-ball forecasts. Never select winner using final36.
  * Export ALL individual 80-ball hour features on last36 plus 6 future
    target appearances, all 0..10 and 0..20 outcome distributions, day-cluster
    uncertainty, group life-cycle probability tables, optional synthetic RNG.

CAVEAT: heat ranks/streaks have persistence even in true independent RNG
because EWMA has memory. A retrospective deviation is not a proven
forecast edge. Six layers are experimental, not claimed recovered legacy.

No new physical draw events are invented at 01:02->07:02. H1..H12 in this
module mean DRAW positions inside one 12-draw hour; full-hour H1..H12
life-path is separately available in V28.
"""
from __future__ import annotations
import argparse
import json
import math
import random
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import mean

from v11_arastirma import read_draws
from v21_aile_yasam_dongusu import group_full_days, clock, key, csv_bytes
from v28_dijital_kaplan_dongu import BALLS, DECAY, HEAT_MAP, HEAT_SIX, HEAT_MACRO, state_before

HOUR_STARTS=(1,)+tuple(14+12*j for j in range(17))
HEAT_COUNTS=(13,13,14,14,13,13)
MODELS=("Isı6","Isı6_Kalış","Isı6_Yön","Isı6_Kalış_Yön",
        "Isı6_Yön_İlk6","ÜçIsı_Kalış_Geçiş")
STAGES=("Eğitim24","Doğrulama12","Sınama36")
SHRINK=600.0
WARMUP=144


def phase_for(full):
    if len(full)<72:
        raise ValueError(f"72 tam gün gerekli; mevcut: {len(full)}")
    days=[day for day,_ in full][:72]
    return {d:("Eğitim24" if i<24 else "Doğrulama12" if i<36 else "Sınama36")
            for i,d in enumerate(days)}


def bucket_duration(value):
    if value<=1:return "1"
    if value<=3:return "2-3"
    if value<=6:return "4-6"
    if value<=12:return "7-12"
    if value<=24:return "13-24"
    if value<=48:return "25-48"
    if value<=96:return "49-96"
    return "97+"


def trend_label(delta):
    return "Isınıyor" if delta>0 else "Soğuyor" if delta<0 else "Sabit"


def clip_hits(appearances):
    return "0" if appearances==0 else "1" if appearances==1 else "2" if appearances==2 else "3+"


def state_features(frozen_six, frozen_macro, start_six, start_macro,
                   run_macro, run_six, path_six, window_drawn):
    rows=[]
    for n in BALLS:
        path=path_six[n]
        if len(path)!=6:
            raise AssertionError("H1..H6 must have exactly six known states")
        changes=sum(path[j]!=path[j-1] for j in range(1,6))
        changes+=int(path[-1]!=frozen_six[n])
        draws_in_first6=window_drawn[n]
        stage=frozen_six[n]
        grp=frozen_macro[n]
        rows.append({
            "Sayı":n,"Isı6":stage,"Isı3":grp,
            "Isı6 adı":HEAT_SIX[stage],
            "Isı3 adı":HEAT_MACRO[grp],
            "Başlangıç Isı6":start_six[n],
            "Yön":trend_label(stage-start_six[n]),
            "Yön3":trend_label(grp-start_macro[n]),
            "Kesintisiz 3 sınıf çekiliş":run_macro[n],
            "Kesintisiz 6 sınıf çekiliş":run_six[n],
            "Kalış 3":bucket_duration(run_macro[n]),
            "Kalış 6":bucket_duration(run_six[n]),
            "İlk6 sınıf geçiş adedi":changes,
            "Geçiş türü":"Sabit H1-H6" if changes==0 else "1 dönüş" if changes==1 else "2+ dönüş",
            "İlk6 çıkma":draws_in_first6,
            "İlk6 çıkma tipi":clip_hits(draws_in_first6),
        })
    return rows


def candidate_key(row,method):
    six=row["Isı6"]
    if method=="Isı6": return (six,)
    if method=="Isı6_Kalış":return (six,row["Kalış 6"])
    if method=="Isı6_Yön":return (six,row["Yön"])
    if method=="Isı6_Kalış_Yön":return (six,row["Kalış 6"],row["Yön"])
    if method=="Isı6_Yön_İlk6":return (six,row["Yön"],row["İlk6 çıkma tipi"])
    if method=="ÜçIsı_Kalış_Geçiş":
        return (row["Isı3"],row["Kalış 3"],row["Geçiş türü"])
    raise ValueError("Unknown predeclared model")


def chronological_consecutive(prev,cur):
    if prev is None:return False
    if prev["day"]==cur["day"]:
        return cur["pos"]==prev["pos"]+1
    return ((date.fromisoformat(cur["day"])-date.fromisoformat(prev["day"])).days==1
            and prev["pos"]==217 and cur["pos"]==1)


def generate_rows(draws,phase,progress=None):
    """Build snapshots chronologically, with labels attached AFTER scoring.

    All history, including incomplete-day valid draws, contributes to EWMA;
    only 217-valid full days are tested. Gaps reset COUNTED dwell duration
    (rather than calling missing data uninterrupted).
    """
    complete=set(phase)
    bydate=defaultdict(dict)
    for d in draws:
        if d["day"] in complete:
            bydate[d["day"]][d["pos"]]=d
    if any(len(x)!=217 for x in bydate.values()):
        raise AssertionError("Only exact complete days may be targets")

    scores=[0.]*81
    old_macro=[None]*81
    old_six=[None]*81
    streak_macro=[0]*81
    streak_six=[0]*81
    before=None
    inside_hour=defaultdict(list)
    present=Counter()
    events=[]
    processed=0

    for idx,draw in enumerate(sorted(draws,key=lambda d:(d["day"],d["pos"]))):
        pre_six,pre_macro=state_before(scores)
        if not chronological_consecutive(before,draw):
            old_macro=[None]*81;old_six=[None]*81
            streak_macro=[0]*81;streak_six=[0]*81
        for n in BALLS:
            streak_macro[n]=streak_macro[n]+1 if pre_macro[n]==old_macro[n] else 1
            streak_six[n]=streak_six[n]+1 if pre_six[n]==old_six[n] else 1
        old_macro=pre_macro
        old_six=pre_six
        hour_start=(1 if draw["pos"]<=12 else
                    14+12*((draw["pos"]-14)//12) if draw["pos"]>=14 else None)
        active=(draw["day"] in complete and idx>=WARMUP and
                hour_start in HOUR_STARTS and draw["pos"]<=hour_start+5)
        if active:
            marker=(draw["day"],hour_start)
            inside_hour[marker].append(tuple(pre_six))
            present.update(draw["nums"])
        scores=[0.]+[scores[n]*DECAY+int(n in draw["nums"]) for n in BALLS]
        if active and draw["pos"]==hour_start+5:
            post_six,post_macro=state_before(scores)
            # The current decision state is post-H6/pre-H7; update streak to it,
            # NOT to any future state. This counts one decision snapshot.
            new_macro=[0]+[streak_macro[n]+1 if post_macro[n]==pre_macro[n] else 1
                           for n in BALLS]
            new_six=[0]+[streak_six[n]+1 if post_six[n]==pre_six[n] else 1
                         for n in BALLS]
            histories=inside_hour[(draw["day"],hour_start)]
            if len(histories)!=6:
                raise AssertionError("Hour first-six history incomplete")
            paths={n:[p[n] for p in histories] for n in BALLS}
            rows=state_features(post_six,post_macro,
                    histories[0],
                    [HEAT_MAP[histories[0][n]] for n in range(81)],
                    new_macro,new_six,paths,present)
            for row in rows:
                row.update({
                    "Tarih":draw["day"],"Dönem":phase[draw["day"]],
                    "Saat başlangıcı":clock(hour_start)[0],
                    "Kesim çekilişi":draw["no"],
                    "Kesim sıra":draw["pos"],
                })
            events.append((draw["day"],hour_start,rows))
            inside_hour.pop((draw["day"],hour_start))
            present.clear()
        # If a day has fewer than six known draws, no event. Full target days
        # have all 217 positions; 01:02 is a singleton not a new hour.
        before=draw
        if draw["day"] in complete and draw["pos"]==217:
            processed+=1
            if progress is not None:progress(processed,76,"Geçmiş sıcaklık / kalış hazırlanıyor",draw["day"])

    # Attach outcomes only after all states are constructed/frozen.
    for day,start,rows in events:
        targets=[bydate[day][p] for p in range(start+6,start+12)]
        for row in rows:
            n=row["Sayı"]
            hits=sum(n in target["nums"] for target in targets)
            row["H7-H12 gelen sayı"] = hits
            row["H7-H12 gelme %"]=round(hits*100/6,4)
            # These are labels, NEVER read in state_features or models.
            for j,target in enumerate(targets,7):
                row[f"H{j} hedefte"]=int(n in target["nums"])
    return events


def train_rates(events):
    counts={method:defaultdict(lambda:Counter()) for method in MODELS}
    for day,start,rows in events:
        if rows[0]["Dönem"]!="Eğitim24":continue
        for row in rows:
            for mode in MODELS:
                cell=counts[mode][candidate_key(row,mode)]
                cell["n"]+=6
                cell["hit"]+=row["H7-H12 gelen sayı"]
    return {mode:{key:(v["hit"]+.25*SHRINK)/(v["n"]+SHRINK)
                  for key,v in cells.items()} for mode,cells in counts.items()}


def probability_scores(rows,rates,model):
    p=[rates[model].get(candidate_key(row,model),.25) for row in rows]
    shift=.25-mean(p)
    # Valid rates with shrinkage are near .25. Normalize so all 80
    # pre-target scores yield an expected TOTAL of 20 balls per draw.
    norm=[min(.99,max(.01,x+shift)) for x in p]
    return norm


def one_hour_brier(rows,p):
    # Six target draws x eighty binary outcomes, no need for target list
    # inside the *selector*; only final scoring may consume labels.
    return sum(6*p[j]*p[j]-2*p[j]*r["H7-H12 gelen sayı"]+
               r["H7-H12 gelen sayı"] for j,r in enumerate(rows))/(6*80)


def rank_tickets(rows,p,day,start):
    model_order=sorted(range(80),key=lambda j:(-p[j],rows[j]["Sayı"]))
    hot_order=sorted(range(80),key=lambda j:(-rows[j]["Isı6"],
                         -rows[j]["Kesintisiz 6 sınıf çekiliş"],
                         rows[j]["Sayı"]))
    cold_order=sorted(range(80),key=lambda j:(rows[j]["Isı6"],
                          -rows[j]["Kesintisiz 6 sınıf çekiliş"],
                          rows[j]["Sayı"]))
    random_gen=random.Random(int(day.replace("-",""))*9176+start*89)
    # 20- and 10-ball random baselines are reproducible (not postselected).
    random20=random_gen.sample(BALLS,20)
    random10=random_gen.sample(BALLS,10)
    return {
        "Model20":[rows[j]["Sayı"] for j in model_order[:20]],
        "Sıcak20":[rows[j]["Sayı"] for j in hot_order[:20]],
        "Soğuk20":[rows[j]["Sayı"] for j in cold_order[:20]],
        "Rastgele20":random20,
        "Model10":[rows[j]["Sayı"] for j in model_order[:10]],
        "Sıcak10":[rows[j]["Sayı"] for j in hot_order[:10]],
        "Rastgele10":random10,
    }


def make_score_records(events,rates,chosen,period="Sınama36"):
    recs=[]
    rawby=defaultdict(list)
    for day,start,rows in events:
        if rows[0]["Dönem"]!=period:continue
        p=probability_scores(rows,rates,chosen)
        brier=one_hour_brier(rows,p)
        picks=rank_tickets(rows,p,day,start)
        lookup={r["Sayı"]:r for r in rows}
        for name,balls in picks.items():
            results=[sum(lookup[n][f"H{h} hedefte"] for n in balls)
                     for h in range(7,13)]
            rec={
                "Tarih":day,"Saat":clock(start)[0],"Yöntem":name,
                "Sabit eğitim seçimi":chosen,
                "Tahmin edilen sayı":len(balls),"Tahmin sayıları":key(sorted(balls)),
                "Hedef1":results[0],"Hedef2":results[1],"Hedef3":results[2],
                "Hedef4":results[3],"Hedef5":results[4],"Hedef6":results[5],
                "6 hedef toplam":sum(results),
                "6+ çekiliş":sum(x>=6 for x in results),
                "7+ çekiliş":sum(x>=7 for x in results),
                "8+ çekiliş":sum(x>=8 for x in results),
                "9+ çekiliş":sum(x>=9 for x in results),
                "10+ çekiliş":sum(x>=10 for x in results),
                "6 hedef en yüksek":max(results),
                "Brier":round(brier,9) if name=="Model20" else "",
            }
            recs.append(rec)
            rawby[name].extend(results)
    distributions=[]
    for name,hits in rawby.items():
        size=10 if name.endswith("10") else 20
        dist=Counter(hits)
        n=len(hits)
        distributions.append({
            "Yöntem":name,"Tahmin sayısı":size,
            "Hedef çekiliş":n,"Ortalama doğru sayı":round(mean(hits),6),
            "RNG teori":2.5 if size==10 else 5.,
            "5+":sum(v for k,v in dist.items() if k>=5),
            "6+":sum(v for k,v in dist.items() if k>=6),
            "7+":sum(v for k,v in dist.items() if k>=7),
            "8+":sum(v for k,v in dist.items() if k>=8),
            "9+":sum(v for k,v in dist.items() if k>=9),
            "10+":sum(v for k,v in dist.items() if k>=10),
            "10/10":dist[10] if size==10 else "",
            "En yüksek":max(hits),
            **{f"{k}/{size}":dist[k] for k in range(size+1)},
        })
    return recs,distributions


def ci_by_day(recs,chosen):
    grouped=defaultdict(dict)
    for r in recs:
        grouped[(r["Tarih"],r["Saat"])][r["Yöntem"]]=r
    out=[]
    for a,b in (("Model10","Rastgele10"),("Model10","Sıcak10"),
                ("Model20","Rastgele20"),("Model20","Sıcak20"),
                ("Model20","Soğuk20")):
        days=defaultdict(list)
        for (day,tm),pair in grouped.items():
            days[day].append((pair[a]["6 hedef toplam"]-pair[b]["6 hedef toplam"])/6)
        data=[mean(x) for x in days.values()]
        mu=mean(data)
        se=(sum((x-mu)**2 for x in data)/(len(data)-1)/len(data))**.5
        out.append({
            "Model":chosen,"Kıyas":a+" - "+b,"Tam gün":len(data),
            "Ortalama çekiliş isabet farkı":round(mu,7),
            "Yaklaşık %95 GA alt":round(mu-1.96*se,7),
            "Yaklaşık %95 GA üst":round(mu+1.96*se,7),
            "Üstünlük kanıtı":(mu-1.96*se)>0,
        })
    return out


def descriptive_groups(events):
    dimensions={
        "3 sınıf × kalış":lambda r:(r["Isı3 adı"],r["Kalış 3"]),
        "6 sınıf × kalış":lambda r:(r["Isı6 adı"],r["Kalış 6"]),
        "6 sınıf × yön":lambda r:(r["Isı6 adı"],r["Yön"]),
        "3 sınıf × geçiş":lambda r:(r["Isı3 adı"],r["Geçiş türü"]),
        "6 sınıf × kalış × yön":lambda r:(
            r["Isı6 adı"],r["Kalış 6"],r["Yön"]),
        "6 sınıf × ilk 6 geliş":lambda r:(
            r["Isı6 adı"],r["İlk6 çıkma tipi"]),
    }
    grouped=defaultdict(lambda:Counter())
    for day,start,rows in events:
        period=rows[0]["Dönem"]
        if period!="Sınama36":continue
        for r in rows:
            for title,f in dimensions.items():
                category=f(r)
                cell=grouped[(title,category)]
                cell["n"]+=1
                cell["hit"]+=r["H7-H12 gelen sayı"]
                cell["days"].add(day) if False else None
    report=[]
    for (title,keys),v in sorted(grouped.items()):
        n=v["n"]
        report.append({
            "Bağlam":title,"Durum":" / ".join(map(str,keys)),
            "Gözlenen sayı-saat":n,"H7-H12 hedef hak":6*n,
            "H7-H12 hedefte çıktı":v["hit"],
            "Hedefte görünme %":round(v["hit"]/(6*n)*100,5),
            "Matematik RNG %":25,
            "Beklenen RNG doğru":round(1.5*n,2),
            "RNG'den fark yüzde puan":round(v["hit"]/(6*n)*100-25,5),
            "Uyarı":"Aynı sayıya ait 6 hedef bağımsız tahmin sayılmaz",
        })
    return report


def validation_choose(events,rates):
    audit=[]
    for method in MODELS:
        byday=defaultdict(list)
        for d,start,rows in events:
            if rows[0]["Dönem"]!="Doğrulama12":continue
            probs=probability_scores(rows,rates,method)
            byday[d].append(one_hour_brier(rows,probs))
        vals=[x for values in byday.values() for x in values]
        audit.append({
            "Yöntem":method,"Doğrulama tam gün":len(byday),
            "Doğrulama saat":len(vals),
            "Brier hata":round(mean(vals),10),
            "RNG Brier":.1875,
            "RNG'den fark":round(mean(vals)-.1875,10),
        })
    winner=min(audit,key=lambda x:(x["Brier hata"],MODELS.index(x["Yöntem"])))["Yöntem"]
    for a in audit:a["Seçilen (sınamadan önce)"]=a["Yöntem"]==winner
    return winner,audit


def test_prob_by_day(events,rates,winner):
    data=defaultdict(list)
    for day,start,rows in events:
        if rows[0]["Dönem"]=="Sınama36":
            data[day].append(one_hour_brier(rows,probability_scores(rows,rates,winner)))
    vals=[.1875-mean(a) for a in data.values()]
    mu=mean(vals)
    se=(sum((x-mu)**2 for x in vals)/(len(vals)-1)/len(vals))**.5
    return [{
        "Sınama":"Son36","Metot":winner,
        "Brier avantajı (RNG - model)":round(mu,10),
        "95% GA alt":round(mu-1.96*se,10),
        "95% GA üst":round(mu+1.96*se,10),
        "RNG üstü kanıt":mu-1.96*se>0,
    }]


def run_study(txt,progress=None):
    draws,errors=read_draws(txt)
    full,missing=group_full_days(draws)
    phases=phase_for(full)
    until=max(phases)
    input_draws=[x for x in draws if x["day"]<=until]
    if progress is not None:progress(0,76,"V29 geçmiş ısı hafızası başlıyor","")
    events=generate_rows(input_draws,phases,progress=progress)
    assert len({x[0] for x in events})==72
    testevents=sum(1 for d,s,r in events if r[0]["Dönem"]=="Sınama36")
    assert testevents==36*18
    if progress is not None:progress(73,76,"24 gün eğitim ve 12 gün doğrulama","")
    rates=train_rates(events)
    winner,validation=validation_choose(events,rates)
    if progress is not None:progress(74,76,"Seçilmiş modelle son 36 gün kör sınama","")
    recs,distribution=make_score_records(events,rates,winner)
    uncertainty=ci_by_day(recs,winner)+test_prob_by_day(events,rates,winner)
    grouped=descriptive_groups(events)
    testrows=[r for day,start,rs in events
              if rs[0]["Dönem"]=="Sınama36" for r in rs]
    training=[
        {"Yöntem":mode,"Kalıp":repr(cell),"Eğitim olasılık":round(prob,8)}
        for mode,rule in rates.items() for cell,prob in sorted(rule.items(),key=lambda p:repr(p[0]))
    ]
    if progress is not None:progress(75,76,"CSV raporları hazırlanıyor","")
    meta={
        "Motor":"V29 Sıcaklıkta Kalış + Geçiş Yönü + Hedef 20 Sayı",
        "Gün":72,"Çekiliş":72*217,
        "Saat kesimleri":len(events),"Son 36 gün hedef saati":testevents,
        "Son 36 gün hedef çekilişi":testevents*6,
        "Test sayı-saat kayıt":len(testrows),
        "Eğitim":list(phases)[0]+"—"+list(phases)[23],
        "Doğrulama":list(phases)[24]+"—"+list(phases)[35],
        "Test":list(phases)[36]+"—"+list(phases)[-1],
        "Dondurulmuş yöntem":winner,
        "Kural":"H6 tamamlandıktan sonra 80 sayının sıcaklık, kesintisiz kalış, H1-H6 yön ve çıkış sayılarına bak; H7-H12 kilitli, geleceği bilme.",
        "Hafıza":"12 gerçek çekiliş yarı ömür, günler arasında devam eder",
        "Isı sınıflandırma":"V28'deki deneysel 13,13,14,14,13,13 altı eşit-rank sınıf; eski gerçek altı sıcaklık eşikleri doğrulanmadı",
        "Yalancı sinyal önleme":"24 gün eğitim, 12 gün model doğrulama, son36 kesinlikle modeli değiştirmeyen test",
        "Kontroller":"Teorik RNG %25 tek sayı/çekiliş; rastgele20, sıcak20, soğuk20, rastgele10, sıcak10",
        "Uyarı":"Sıcak/soğukta uzun kalış EWMA'nın yapısal sonucu olabilir; isabet üstünlüğü ancak son36 test ve yeni canlı veriyle değerlendirilir",
        "Hatalı ham kayıt":errors,"Eksik günler":missing,
    }
    parts={
        "ozet.json":json.dumps(meta,ensure_ascii=False,indent=2).encode("utf-8"),
        "ilk24_ogrenilen_sicaklik_kalis_olasiliklari.csv":csv_bytes(training),
        "orta12_model_secimi_gelecegi_gormeden.csv":csv_bytes(validation),
        "son36_sicaklik_kalis_yon_hedef20_detay.csv":csv_bytes(testrows),
        "son36_grup_bazli_hedefe_girme_olasiliklari.csv":csv_bytes(grouped),
        "son36_H7_H12_kilitli_10ve20_sayi_tahmin.csv":csv_bytes(recs),
        "son36_0dan10_0dan20_isabet_dagilimi.csv":csv_bytes(distribution),
        "son36_rastgele_karsilastirma_guven_araliklari.csv":csv_bytes(uncertainty),
    }
    if progress is not None:progress(76,76,"V29 bütün araştırmalar tamamlandı","")
    return parts,meta,validation,distribution,uncertainty


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data",default="veri.txt")
    ap.add_argument("--output",default="V29_SICAKLIK_KALIS_HEDEF_72_GUN.zip")
    args=ap.parse_args()
    parts,meta,val,dist,uncertainty=run_study(
        Path(args.data).read_text(encoding="utf-8-sig"))
    with zipfile.ZipFile(args.output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for filename,blob in parts.items():z.writestr(filename,blob)
    print("V29_PASS",json.dumps({k:meta[k] for k in
          ("Gün","Son 36 gün hedef çekilişi","Dondurulmuş yöntem")},ensure_ascii=False))
    for row in dist:print("V29_OUTCOME",json.dumps(row,ensure_ascii=False))
    for row in uncertainty:print("V29_CI",json.dumps(row,ensure_ascii=False))
    print("V29_ZIP",args.output)


if __name__=="__main__":
    main()
