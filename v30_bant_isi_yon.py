# -*- coding: utf-8 -*-
"""V30 Bant x Isı x Yön: honest, one-ZIP 72-day Hızlı On experiment.

Eight FIXED number bands (1-10, ..., 71-80); six dynamic 13/13/14/14/13/13
EWMA temperature seats from V28; direction of a ball's CONTINUOUS EWMA
heat score over the first six draws of its hour, *not* the transition of its
rank alone. True ties are "Sabit" (do not force into a positive or negative
class). An 80-ball sum=20 in every draw creates mechanical simultaneous
anti-correlation of band seats; later-draw lag associations are separate.

All predictors frozen after H6; the *next* six draws H7..H12 are held out.
First24 days: learn; next12: preselect ONE of 6 declared models on Brier;
last36: lock model, compare heldout 10- and 20-ball tickets with uniform
seeded random, hot20, math .25, day-cluster confidence intervals. A
number-label permutation null tests FIXED band x (heat,direction) occupancy,
preserving each number's complete history and per-hour state totals.
H1..H12 in the forecast means twelve 5-minute draws in the SAME hour.
01:02 is a single draw and there are no invented 01:02--07:02 draws.
No software guarantee of beating an independent random number generator.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import zipfile
from collections import Counter,defaultdict
from datetime import date
from pathlib import Path
from statistics import mean

from v11_arastirma import read_draws
from v21_aile_yasam_dongusu import group_full_days,clock,csv_bytes,key
from v28_dijital_kaplan_dongu import BALLS,DECAY,HEAT_SIX
from v29_sicaklik_kalis_hedef import generate_rows,phase_for

BANDS=tuple((i*10+1,(i+1)*10) for i in range(8))
DIRECTIONS=("Soğuyor","Isınıyor","Sabit")
METHODS=("Sabit_%25","Isı_Yön","Bant_Isı_Yön",
         "Bant_EksiArtı_Isı","Bant_Ritim_Isı","Bant_Basınç_İlk6")
HOUR_STARTS=(1,)+tuple(14+12*i for i in range(17))
TEST_LABEL="Sınama36"
PRIOR=480.
EPS=1e-10


def band_of(n):
    if not 1<=n<=80:raise ValueError(n)
    return (n-1)//10


def direction(delta):
    # Scores are floats: exact equality is a real level, not guessed direction.
    if delta>EPS:return "Isınıyor"
    if delta<-EPS:return "Soğuyor"
    return "Sabit"


def six_pattern(counts):
    if len(counts)!=6:raise ValueError("Each hour must have 6 known draws")
    # 2.5 is the mean of a TEN-number band in a 20-of-80 draw.
    return "".join("+" if v>=3 else "-" for v in counts)


def band_phase(numbers_first6):
    counts=tuple(len(set(d["nums"])&set(range(10*b+1,10*b+11)))
                 for d in numbers_first6 for b in ())
    # Above intentionally not used; compute one pass for each 5-min draw.
    series=[[0]*6 for _ in range(8)]
    for j,d in enumerate(numbers_first6):
        for n in d["nums"]:
            series[band_of(n)][j]+=1
    answer=[]
    for b,vals in enumerate(series):
        pulse=six_pattern(vals)
        gain=sum(vals[3:])-sum(vals[:3])
        excess=sum(vals)-15  # 6 draws × 2.5 expected =15.
        direction3="+" if gain>0 else "-" if gain<0 else "="
        label=("Üst" if excess>0 else "Alt" if excess<0 else "Denge")
        switches=sum(pulse[k]!=pulse[k-1] for k in range(1,6))
        # A short symbolic texture, not a claim of RNG forcing a reversal.
        rhythm=(pulse[-1],min(3,switches),
                "Artıyor" if gain>0 else "Azalıyor" if gain<0 else "Düz")
        answer.append({
            "Bant":b+1,"Aralık":f"{b*10+1}-{b*10+10}",
            "İlk6 bant sayıları":"/".join(map(str,vals)),
            "İlk6 +/- dizisi":pulse,
            "İlk6 toplam":sum(vals),"İlk6 beklenti":15,
            "İlk6 sapma":excess,
            "İlk6 konum":label,
            "İlk3-son3 fark":gain,
            "İlk3-son3 yön":direction3,
            "Ritim kümesi":str(rhythm[0])+str(rhythm[1])+rhythm[2],
            "H1-H6 yön değişimi":switches,
        })
    assert sum(x["İlk6 toplam"] for x in answer)==120
    return answer


def pressure_snapshots(draws,phase):
    """A second chronological streaming pass to capture only PRE-H7 scores.

    Do not use labels/outcomes from H7-H12 for the score, slope or band pulse.
    """
    byday=defaultdict(dict)
    for d in draws:
        if d["day"] in phase:byday[d["day"]][d["pos"]]=d
    current=[0.]*81
    starts={}
    result={}
    for d in sorted(draws,key=lambda r:(r["day"],r["pos"])):
        day,pos=d["day"],d["pos"]
        if day in phase and pos in HOUR_STARTS:
            starts[(day,pos)]=tuple(current)
        ns=set(d["nums"])
        current=[0.]+[current[n]*DECAY+(1 if n in ns else 0) for n in BALLS]
        if day in phase and (pos-5) in HOUR_STARTS:
            s=pos-5
            initial=starts[(day,s)]
            first=[byday[day][q] for q in range(s,s+6)]
            result[(day,s)]=(initial,tuple(current),band_phase(first))
    return result


def enrich(events,pressure):
    """Re-annotate V29 frozen H6 snapshots with continuous slope + fixed band.

    Stored future outcomes are retained only for evaluation routines;
    feature selector never reads them.
    """
    for day,start,rows in events:
        old,post,bands=pressure[(day,start)]
        for r in rows:
            n=r["Sayı"]
            b=band_of(n)
            p=bands[b]
            r["Bant"]=b+1
            r["Sayı bandı"]=p["Aralık"]
            r["Basınç yönü"]=direction(post[n]-old[n])
            r["Basıç değişimi"]=round(post[n]-old[n],8)
            r["Bant İlk6 +/-"]=p["İlk6 +/- dizisi"]
            r["Bant İlk6 gelen"]=p["İlk6 toplam"]
            r["Bant +/- konum"]=p["İlk6 konum"]
            r["Bant ilk3 son3 yön"]=p["İlk3-son3 yön"]
            r["Bant ilk3 son3 fark"]=p["İlk3-son3 fark"]
            r["Bant ritim"]=p["Ritim kümesi"]
            r["Bant H1-H6 yön değişimi"]=p["H1-H6 yön değişimi"]
    return events


def model_key(r,method):
    if method=="Sabit_%25":return ("uniform",)
    prefix=(r["Isı6"],r["Basınç yönü"])
    if method=="Isı_Yön":return prefix
    if method=="Bant_Isı_Yön":return (r["Bant"],)+prefix
    if method=="Bant_EksiArtı_Isı":
        return (r["Bant"],r["Bant +/- konum"])+prefix
    if method=="Bant_Ritim_Isı":
        return (r["Bant"],r["Bant ritim"])+prefix
    if method=="Bant_Basınç_İlk6":
        return (r["Bant"],r["Bant ilk3 son3 yön"],
                r["İlk6 çıkma tipi"])+prefix
    raise ValueError(method)


def fit_first24(events):
    stats={method:defaultdict(lambda:[0,0]) for method in METHODS}
    for day,start,rows in events:
        if rows[0]["Dönem"]!="Eğitim24":continue
        for r in rows:
            label=r["H7-H12 gelen sayı"]
            for model in METHODS:
                k=model_key(r,model)
                stats[model][k][0]+=label
                stats[model][k][1]+=6
    fit={}
    for method,cells in stats.items():
        fit[method]={
            k:(hits+.25*PRIOR)/(total+PRIOR)
            for k,(hits,total) in cells.items()
        }
    return fit


def frozen_probs(rows,fit,method):
    if method=="Sabit_%25":return [.25]*80
    p=[fit[method].get(model_key(r,method),.25) for r in rows]
    # Each target exactly 20 balls => expected sum of 80 marginal p's is 20.
    offset=.25-mean(p)
    norm=[min(.98,max(.02,v+offset)) for v in p]
    # All training rates are smoothed close to .25. If clipping occurred,
    # renormalize to preserve sum = 20 using proportional positive scaling.
    rem=20-sum(norm)
    if abs(rem)>1e-7:
        norm=[max(.001,min(.999,v+rem/80)) for v in norm]
    return norm


def brier(rows,prob):
    if len(rows)!=80 or len(prob)!=80:raise AssertionError("80")
    # Six prospective 20-of-80 draws per hour.
    return sum(6*p*p-2*p*r["H7-H12 gelen sayı"]+
               r["H7-H12 gelen sayı"] for p,r in zip(prob,rows))/480


def lock_choice(events,fit):
    audit=[]
    for model in METHODS:
        byday=defaultdict(list)
        for day,start,rows in events:
            if rows[0]["Dönem"]=="Doğrulama12":
                byday[day].append(brier(rows,frozen_probs(rows,fit,model)))
        val=mean(v for values in byday.values() for v in values)
        audit.append({
            "Model":model,"Doğrulama gün":len(byday),
            "Doğrulama saat":sum(len(v) for v in byday.values()),
            "Brier":round(val,10),"RNG Brier":.1875,
            "Fark":round(val-.1875,10)})
    win=min(audit,key=lambda x:(x["Brier"],METHODS.index(x["Model"])))["Model"]
    for x in audit:x["Seçildi, sınamadan önce"]=x["Model"]==win
    return win,audit


def pick_coupons(rows,probs,day,start):
    if len(rows)!=80:raise AssertionError("80 rows per frozen hour")
    rng=random.Random(int(day.replace("-",""))*4319+int(start)*911)
    # Random tie-breaker only (purely historical probabilities).
    jitter={n:rng.random() for n in BALLS}
    ordered=sorted(rows,key=lambda r:(
        -probs[r["Sayı"]-1],jitter[r["Sayı"]],r["Sayı"]))
    hot=sorted(rows,key=lambda r:(-r["Isı6"],jitter[r["Sayı"]]))
    return {
        "Model10":[r["Sayı"] for r in ordered[:10]],
        "Model20":[r["Sayı"] for r in ordered[:20]],
        "Sıcak10":[r["Sayı"] for r in hot[:10]],
        "Sıcak20":[r["Sayı"] for r in hot[:20]],
        "Rastgele10":rng.sample(BALLS,10),
        "Rastgele20":rng.sample(BALLS,20)
    }


def ticket_backtest(events,fit,selected):
    scores=defaultdict(list)
    detail=[]
    daypair=defaultdict(lambda:defaultdict(list))
    bandrows=[]
    for day,start,rows in events:
        if rows[0]["Dönem"]!=TEST_LABEL:continue
        probs=frozen_probs(rows,fit,selected)
        picks=pick_coupons(rows,probs,day,start)
        label={r["Sayı"]:r for r in rows}
        for name,nums in picks.items():
            hits=[sum(label[n][f"H{h} hedefte"] for n in nums)
                  for h in range(7,13)]
            assert len(nums)==len(set(nums))
            scores[name].extend(hits)
            daypair[day][name].extend(hits)
            detail.append({
                "Gün":day,"Saat":clock(start)[0],"Model":selected,
                "Yöntem":name,"Kupon sayısı":len(nums),
                "Seçilen numaralar":key(sorted(nums)),
                **{f"H{h} isabet":hits[h-7] for h in range(7,13)},
                "6 çekiliş toplam isabet":sum(hits),
                "6+ tamamlanma":sum(h>=6 for h in hits),
                "7+ tamamlanma":sum(h>=7 for h in hits),
                "8+ tamamlanma":sum(h>=8 for h in hits),
                "9+ tamamlanma":sum(h>=9 for h in hits),
                "10+ tamamlanma":sum(h>=10 for h in hits),
            })
        for b in range(8):
            nums=rows[b*10:(b+1)*10]
            if [r["Sayı"] for r in nums]!=list(range(b*10+1,(b+1)*10+1)):
                raise AssertionError("Rows must be sorted 1..80")
            target=sum(r["H7-H12 gelen sayı"] for r in nums)/6
            predicted=sum(probs[r["Sayı"]-1] for r in nums)
            bandrows.append({
                "Gün":day,"Saat":clock(start)[0],"Bant":b+1,
                "Sayılar":f"{b*10+1}-{b*10+10}",
                "Gerçek sonraki6 ortalama gelen":round(target,6),
                "Tahmin":round(predicted,6),
                "RNG beklenen":2.5,
                "Model mutlak hata":round(abs(target-predicted),6),
                "RNG mutlak hata":round(abs(target-2.5),6),
            })
    result=[]
    for name,values in sorted(scores.items()):
        count=Counter(values)
        q=10 if name.endswith("10") else 20
        result.append({
            "Yöntem":name,"Tahmin sayısı":q,
            "Hedef çekiliş":len(values),"Ortalama isabet":round(mean(values),7),
            "RNG matematik ortalama":q/4,
            "5+":sum(x for k,x in count.items() if k>=5),
            "6+":sum(x for k,x in count.items() if k>=6),
            "7+":sum(x for k,x in count.items() if k>=7),
            "8+":sum(x for k,x in count.items() if k>=8),
            "9+":sum(x for k,x in count.items() if k>=9),
            "10+":sum(x for k,x in count.items() if k>=10),
            "Gerçek 10/10":count[10] if q==10 else "",
            "En yüksek":max(values),
            **{f"{k}/{q}":count[k] for k in range(q+1)},
        })
    ci=[]
    for left,right in (("Model10","Rastgele10"),
                       ("Model20","Rastgele20"),
                       ("Model10","Sıcak10"),
                       ("Model20","Sıcak20")):
        differences=[
            mean(daypair[d][left])-mean(daypair[d][right])
            for d in sorted(daypair)]
        avg,low,high=interval(differences)
        ci.append({
            "Kıyas":left+" - "+right,"Gün":len(differences),
            "Çekiliş başına isabet farkı":round(avg,7),
            "Yaklaşık %95 alt":round(low,7),
            "Yaklaşık %95 üst":round(high,7),
            "Güvenilir üstünlük":low>0,
        })
    byday=defaultdict(list)
    for r in bandrows:
        byday[r["Gün"]].append(r["RNG mutlak hata"]-r["Model mutlak hata"])
    avg,low,high=interval([mean(x) for x in byday.values()])
    ci.append({
        "Kıyas":"8 bant hedef payı: uniform MAE - model MAE","Gün":len(byday),
        "Çekiliş başına isabet farkı":round(avg,7),
        "Yaklaşık %95 alt":round(low,7),
        "Yaklaşık %95 üst":round(high,7),"Güvenilir üstünlük":low>0})
    return detail,result,ci,bandrows


def interval(data):
    if len(data)<2:return mean(data),float("nan"),float("nan")
    mu=mean(data)
    se=(sum((x-mu)**2 for x in data)/(len(data)-1)/len(data))**.5
    return mu,mu-1.96*se,mu+1.96*se


def rates_table(events):
    # descriptive only: evaluated without using holdout to build rules.
    groups=defaultdict(lambda:[0,0])
    for day,start,rows in events:
        if rows[0]["Dönem"]!=TEST_LABEL:continue
        for r in rows:
            k=(r["Bant"],r["Isı6 adı"],r["Basınç yönü"])
            groups[k][0]+=r["H7-H12 gelen sayı"]
            groups[k][1]+=6
    return [{
        "Bant":b,"Sayı aralığı":f"{(b-1)*10+1}-{b*10}",
        "Sıcaklık":s,"Yön":v,"Hedef gelen":hit,
        "Hedef hak":all_,"Gerçek görünme %":round(100*hit/max(1,all_),5),
        "RNG %":25,"Fark yüzde puan":round(100*hit/max(1,all_)-25,5),
        "Örnek sayı-saat":all_//6,
    } for (b,s,v),(hit,all_) in sorted(groups.items())]


def snapshot_bands(events):
    """One row for EACH band/hour, occupancy counts and first6 +/- texture."""
    rows=[]
    numberpanel=defaultdict(lambda:[0]*80)
    cell=defaultdict(Counter)
    for day,start,arr in events:
        phase=arr[0]["Dönem"]
        fields=defaultdict(list)
        for r in arr:
            b=r["Bant"]
            fields[b].append(r)
            if phase==TEST_LABEL:
                # Preserve NUMBER identity before permuting band memberships.
                numberpanel[r["Sayı"]-1][r["Isı6"]*3+
                    DIRECTIONS.index(r["Basınç yönü"])]+=1
                cell[(b,r["Isı6"],r["Basınç yönü"])]["N"]+=1
        for b,chunk in sorted(fields.items()):
            d={
                "Tarih":day,"Saat":clock(start)[0],"Dönem":phase,
                "Bant":b,"Sayılar":f"{10*b-9}-{b*10}",
                "İlk6 bant +/-":chunk[0]["Bant İlk6 +/-"],
                "İlk6 gelen":chunk[0]["Bant İlk6 gelen"],
                "İlk6 sapma":chunk[0]["Bant İlk6 gelen"]-15,
                "İlk6 ilk3-son3 yön":chunk[0]["Bant ilk3 son3 yön"],
                "H6 ısınan":sum(r["Basınç yönü"]=="Isınıyor" for r in chunk),
                "H6 soğuyan":sum(r["Basınç yönü"]=="Soğuyor" for r in chunk),
                "H6 sabit":sum(r["Basınç yönü"]=="Sabit" for r in chunk),
                "Sonraki6 hedefte toplam":sum(r["H7-H12 gelen sayı"] for r in chunk),
                "Sonraki6 hedef ortalaması":round(
                    sum(r["H7-H12 gelen sayı"] for r in chunk)/6,5),
            }
            for six,name in enumerate(HEAT_SIX):
                d[name]=sum(r["Isı6"]==six for r in chunk)
                d[name+" ısınıyor"]=sum(r["Isı6"]==six and r["Basınç yönü"]=="Isınıyor" for r in chunk)
                d[name+" soğuyor"]=sum(r["Isı6"]==six and r["Basınç yönü"]=="Soğuyor" for r in chunk)
                d[name+" sabit"]=sum(r["Isı6"]==six and r["Basınç yönü"]=="Sabit" for r in chunk)
            assert sum(d[name] for name in HEAT_SIX)==10
            rows.append(d)
    return rows,numberpanel,cell


def permutation_band_test(numberpanel,reps=199):
    """Fixed 10-number band labels, shuffled as whole-number identities.

    Each number's ALL heldout-hour 6x3 temperature-direction states
    stay intact. This is stronger than falsely treating 51k highly
    correlated number-hours as independent tests.
    """
    observed=[[0]*18 for _ in range(8)]
    overall=[0]*18
    for n in BALLS:
        v=numberpanel[n-1]
        for j,c in enumerate(v):
            observed[band_of(n)][j]+=c
            overall[j]+=c
    expected=[v/8 for v in overall]
    def deviation(table):
        return sum((row[j]-expected[j])**2/max(1,expected[j])
                   for row in table for j in range(18))
    actual=deviation(observed)
    rng=random.Random(300819)
    scores=[]
    for i in range(reps):
        names=list(BALLS);rng.shuffle(names)
        table=[[0]*18 for _ in range(8)]
        for offset,n in enumerate(names):
            dest=offset//10
            vec=numberpanel[n-1]
            for j,v in enumerate(vec):
                table[dest][j]+=v
        scores.append(deviation(table))
    return [{
        "Sınama":"8 sabit bant x altı ısı x üç yön",
        "Yeniden etiketleme":"80 sayı kimliği ve zaman yolu korunur; bant ataması 10'arlı rastgele değiştirilir",
        "Test gün":36,"Test sayı-saat":sum(overall),
        "Gözlenen toplam sapma":round(actual,5),
        "Rastgele bant ortalama":round(mean(scores),5),
        "Rastgele en düşük":round(min(scores),5),
        "Rastgele en yüksek":round(max(scores),5),
        "Tek kuyruk Monte Carlo p":round(
            (1+sum(v>=actual for v in scores))/(reps+1),5),
        "Tek başına RNG tahmin üstünlüğü ispatı":"Hayır"
    }]


def crossband_lag(full,phases,maxlag=6):
    """Exploratory intra-day 0..6 DRAW lag, no night-gap crossing.

    Correlation at lag zero is structurally dependent by fixed sum 20.
    Lag 1..6 is reported without naive independent-draw p values.
    """
    byday={day:rows for day,rows in full if phases.get(day)==TEST_LABEL}
    vectors=[]
    for day,draws in sorted(byday.items()):
        for start,end in ((1,13),(14,217)):
            segment=[]
            for d in draws[start-1:end]:
                cnt=[0]*8
                for n in d["nums"]:cnt[band_of(n)]+=1
                segment.append(tuple(cnt))
            vectors.append(segment)
    data=[]
    for lag in range(maxlag+1):
        for source in range(8):
            for target in range(8):
                n=0;sx=sy=sxx=syy=sxy=0.
                for segment in vectors:
                    for t in range(len(segment)-lag):
                        a=segment[t][source];b=segment[t+lag][target]
                        n+=1;sx+=a;sy+=b;sxx+=a*a;syy+=b*b;sxy+=a*b
                ex=sxx-sx*sx/n;ey=syy-sy*sy/n
                corr=(sxy-sx*sy/n)/math.sqrt(ex*ey) if ex>0 and ey>0 else 0.
                data.append({
                    "Kaynak bant":source+1,"Hedef bant":target+1,
                    "Gecikme çekiliş":lag,"Gecikme dakika":lag*5,
                    "Gözlem":n,"Pearson":round(corr,6),
                    "Uyarı":("Aynı çekilişte toplam20 sabit; negatif korelasyon beklenir"
                             if lag==0 else "384 gecikmeli çift taranır: en yüksek değer sonradan seçilemez")
                })
    return data


def daily_behavior(bandrows):
    data=defaultdict(lambda:defaultdict(list))
    for r in bandrows:
        data[r["Tarih"]][r["Bant"]].append(r)
    out=[]
    for day,d in sorted(data.items()):
        for b,rr in sorted(d.items()):
            out.append({
                "Tarih":day,"Bant":b,"Gözlenen saat":len(rr),
                "Ortalama H1-H6 sayı":round(mean(x["İlk6 gelen"] for x in rr),5),
                "Ortalama H6 ısınan":round(mean(x["H6 ısınan"] for x in rr),5),
                "Ortalama H6 soğuyan":round(mean(x["H6 soğuyan"] for x in rr),5),
                "H7-H12 bant gelme ortalama":round(mean(
                    x["Sonraki6 hedef ortalaması"] for x in rr),5),
                "RNG bant beklenen":2.5
            })
    return out


def summary_text(meta,validation,distribution,ci,bandnull):
    def pp(rows):
        return "\n".join("  "+json.dumps(v,ensure_ascii=False)
                         for v in rows)
    return (
        "V30 — 8 SABİT BANT × 6 SICAKLIK × YÖN | TEK RAPOR\n"
        "===================================================\n"
        "Her sayı her çekilişte adil RNG altında %25 olasılıkla gelir.\n"
        "10'luk sabit bandın çekiliş başına beklenen katkısı 2,5 sayıdır.\n"
        "Sıcaklık havuzunun bandlara eşit paylaştırılması ZORUNLU DEĞİLDİR.\n"
        "Aynı çekilişte toplam 20 olduğu için bantların sapma toplamı 0'dır.\n"
        "Artı/eksi dizisindeki eksi, 2,5'in altında; artı, üstündedir.\n"
        "Isınma/soğuma H1 öncesi EWMA ile H6 sonrası EWMA farkıdır.\n"
        "Gerçek eşitlik ayrı tutulur. Hafıza yarı ömrü 12 çekiliştir.\n"
        "Model eğitim24 + doğrulama12 + KÖR sınama36 olarak kilitlenmiştir.\n"
        "Bu rapordaki uç değerler gelecekte RNG döngüsü ispatı DEĞİLDİR.\n\n"
        "ÖZET:\n"+json.dumps(meta,ensure_ascii=False,indent=2)+"\n\n"
        "12 GÜNLÜK YÖNTEM SEÇİMİ:\n"+pp(validation)+"\n\n"
        "36 GÜNLÜK 10/20 SAYI İSABETLERİ:\n"+pp(distribution)+"\n\n"
        "36 GÜNLÜK GÜVEN ARALIKLARI:\n"+pp(ci)+"\n\n"
        "SABİT SAYI BANTI YERLEŞİMİ PERMÜTASYONU:\n"+pp(bandnull)+"\n\n"
        "Tüm saat/sayı ayrıntıları aynı ZIP içindeki CSV'lerdedir.\n"
    ).encode("utf-8")


def run_study(txt,progress=None,band_null_reps=199):
    draws,errors=read_draws(txt)
    full,partial=group_full_days(draws)
    phases=phase_for(full)
    until=max(phases)
    observed=[r for r in draws if r["day"]<=until]
    if progress:progress(0,75,"Veri / 80 sayı / 8 bant hazırlanıyor","")
    def stage_progress(done,total,label,day):
        if progress:progress(min(done,72),75,label,day)
    events=generate_rows(observed,phases,progress=stage_progress)
    if len(events)!=72*18:
        raise AssertionError(f"Expected 72x18 complete hours; got {len(events)}")
    pressure=pressure_snapshots(observed,phases)
    enrich(events,pressure)
    if progress:progress(72,75,"Bant yönleri ve +/− salınımları hazır","")
    fit=fit_first24(events)
    selected,validation=lock_choice(events,fit)
    if progress:progress(73,75,"İlk24/orta12 seçimi, son36 kilitli sınama","")
    ticket_rows,distribution,confidence,band_forecast=ticket_backtest(
        events,fit,selected)
    rate=rates_table(events)
    hourly,numberpanel,counts=snapshot_bands(events)
    perm=permutation_band_test(numberpanel,reps=band_null_reps)
    daily=daily_behavior(hourly)
    lag=crossband_lag(full,phases)
    if progress:progress(74,75,"Son36 / RNG / band gecikmesi tamam","")
    heldout=[r for day,start,rows in events
             if phases[day]==TEST_LABEL for r in rows]
    met={
        "Motor":"V30 8 Bant x 6 Isı x Yön, H6→H7-H12",
        "Tam gün":len(phases),"İlk gün":min(phases),"Son gün":max(phases),
        "Toplam saat":len(events),
        "Sınama hedef çekiliş":36*18*6,
        "80 sayı-saat sınama":len(heldout),
        "Sabit bant":{str(i+1):f"{a}-{b}" for i,(a,b) in enumerate(BANDS)},
        "6 sıcaklık":list(HEAT_SIX),
        "Hareket kategorisi":list(DIRECTIONS),
        "Yön":"H1 başlamadan önceki EWMA → H6 tamamlandıktan sonraki EWMA",
        "Sıcaklık":"V28 experimental 6 rank fixed counts [13,13,14,14,13,13]",
        "24/12/36":"24g öğrenme, 12g model seçme, 36g bağımsız sabit test",
        "Seçilen model":selected,"Kıyas":"20/10 seçimi, rastgele, sıcak seçimi, adil %25",
        "Bant null":"199 sayı kimliği bant-permütasyonu; sayı geçmişi korunur",
        "Bant p değeri":perm[0]["Tek kuyruk Monte Carlo p"],
        "Sinyal araştırması":"8 bant/6 sıcaklık/2 yön + gerçek sabitler; bant H1..H6 ± ritim",
        "Önemli":"Olağandışı benzerlik kanıtlanmış RNG tahmin başarısı değildir.",
        "Geçersiz ham satır":errors,"Eksik gün":partial,
    }
    files={
        "00_TEK_RAPOR_OZET.txt":summary_text(met,validation,distribution,confidence,perm),
        "01_yontem_secimi_orta12.csv":csv_bytes(validation),
        "02_son36_kupon10_kupon20_sonuc.csv":csv_bytes(distribution),
        "03_son36_guven_araliklari.csv":csv_bytes(confidence),
        "04_8bant_6sicaklik_yon_gercek_hedef20.csv":csv_bytes(rate),
        "05_8bant_6sicaklik_yon_sayisal_perm_test.csv":csv_bytes(perm),
        "06_72gun_her_saat_8bant_isi_yon_dalgasi.csv":csv_bytes(hourly),
        "07_son36_her_sayi_saat_isi_yon_H7_H12.csv":csv_bytes(heldout),
        "08_son36_her_saat_10lu20li_tahmin.csv":csv_bytes(ticket_rows),
        "09_son36_bant_pay_tahmin_gercek.csv":csv_bytes(band_forecast),
        "10_son36_sayisal_bant_gecikme_0_6.csv":csv_bytes(lag),
        "11_72gun_her_bant_gunluk_ritim.csv":csv_bytes(daily),
    }
    if progress:progress(75,75,"12 rapor tek dosyada hazır","")
    return files,met,validation,distribution,confidence,rate,perm


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data",default="veri.txt")
    ap.add_argument("--output",default="V30_BANT_ISI_YON_TEK_RAPOR.zip")
    ap.add_argument("--null",type=int,default=199)
    args=ap.parse_args()
    reports,meta,val,dis,ci,rates,perm=run_study(
        Path(args.data).read_text(encoding="utf-8-sig"),
        band_null_reps=args.null)
    with zipfile.ZipFile(args.output,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for name,payload in reports.items():z.writestr(name,payload)
    print("V30_OK",json.dumps({
        "Test":meta["Sınama hedef çekiliş"],"Model":meta["Seçilen model"],
        "Bant permütasyon p":meta["Bant p değeri"]},ensure_ascii=False))
    for row in dis:print("V30_HITS",json.dumps(row,ensure_ascii=False))
    for row in ci:print("V30_CI",json.dumps(row,ensure_ascii=False))
    print("V30_ZIP",args.output)


if __name__=="__main__":
    main()
