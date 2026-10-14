# -*- coding: utf-8 -*-
"""V27 -- 80-ball, SIX temperature seats, trends, optimal history horizon.

Lookbacks: 6/12/24/36/72/144/217/434/868/1519 RECORDED actual draws,
without filling missing or night gaps. Score methods: frequency or old
12-draw half-life exponentially weighted frequency truncated to the window.

Each 80-ball state is calculated *BEFORE* the target, sorted into disjoint
six temperature ranks [13,13,14,14,13,13]. Trend (UP/STABLE/DOWN) compares
previous 6 vs the 6 before that, fully in history. Target 20 "seats" mean
number of its actual balls falling into each precomputed category, NEVER the
published ascending numeral order or physical extraction sequence.

Honest nested selection: first 18 COMPLETE days fit smoothed 6x3 cell rates,
next 18 days select lookback/method using Brier score, last 36 days final
time-separated test against chance=.25 and seeded matched random 20-ball picks.
Report all window diagnostics without changing the previously selected rule.

All historic observations including incomplete dates MAY be prior context,
but only fully validated 217-draw days are evaluation targets. Hence lookback
is counts of observed valid draws (not wall-clock days). No result leakage.
"""
from __future__ import annotations
import argparse
import json
import math
import random
import zipfile
from array import array
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from v11_arastirma import read_draws
from v21_aile_yasam_dongusu import group_full_days, clock, key, csv_bytes

LOOKBACKS=(6,12,24,36,72,144,217,434,868,1519)
METHODS=("Frekans","Yarı ömür 12")
GROUPS=("Soğuk","Soğuğa yakın","Orta","Ilık","Sıcağa yakın","Sıcak")
COUNTS=(13,13,14,14,13,13)
TREND=("Düşen","Dengeli","Yükselen")
PRIOR=500.
HALF_LIFE=12
DECAY=0.5**(1/HALF_LIFE)
BASE=.25
MAX_WINDOW=max(LOOKBACKS)

assert len(GROUPS)==6 and sum(COUNTS)==80


def make_index(draws):
    """Chronologically sort VALID observed draws; incomplete dates remain
    historical context only, never treated as negative or target-label fills.
    Precompute O(1) recent frequency and 12-draw EWMA score requests."""
    draws=sorted(draws,key=lambda d:(d["day"],d["pos"]))
    times=[d["day"]+" "+clock(d["pos"])[0] for d in draws]
    if len(times)!=len(set(times)):
        raise AssertionError("Duplicate date/slot")
    total=len(draws)
    p=[array("I",[0]) for _ in range(81)]
    e=[array("f",[0.]) for _ in range(81)]
    for d in draws:
        nums=set(d["nums"])
        for n in range(1,81):
            value=int(n in nums)
            p[n].append(p[n][-1]+value)
            e[n].append(e[n][-1]*DECAY+value)
    return draws,p,e


def classify_before(t,lookback,method,prefix,ewm):
    """t = number of already observed real draws. Target is row t."""
    if t<lookback or t<12:
        raise ValueError("Insufficient pre-target observation")
    if lookback not in LOOKBACKS or method not in METHODS:
        raise ValueError("Undeclared window or method")
    exp_factor=DECAY**lookback if method=="Yarı ömür 12" else None
    score={}
    rates={}
    for n in range(1,81):
        x=prefix[n]
        rates[n]=x[t]-x[t-6] - (x[t-6]-x[t-12])
        if method=="Frekans":
            score[n]=x[t]-x[t-lookback]
        else:
            score[n]=ewm[n][t]-exp_factor*ewm[n][t-lookback]
    ordered=sorted(range(1,81),key=lambda n:(score[n],n))
    groups=[0]*81
    cursor=0
    for g,size in enumerate(COUNTS):
        for n in ordered[cursor:cursor+size]:
            groups[n]=g
        cursor+=size
    trends=[0]*81
    for n in range(1,81):
        difference=rates[n]
        trends[n]=0 if difference<=-2 else 2 if difference>=2 else 1
    return groups,trends,score


def bins_for_state(groups,trends):
    """Return 6 x 3 = 18 population counts and groups."""
    counts=[0]*18
    members=[[] for _ in range(6)]
    for n in range(1,81):
        cid=groups[n]*3+trends[n]
        counts[cid]+=1
        members[groups[n]].append(n)
    assert sum(counts)==80
    assert tuple(len(m) for m in members)==COUNTS
    return counts,members


def classify_and_count(t,L,mode,p,e,actual=None):
    grp,tr,score=classify_before(t,L,mode,p,e)
    counts,members=bins_for_state(grp,tr)
    hits=[0]*18
    if actual is not None:
        for n in actual:hits[grp[n]*3+tr[n]]+=1
    return (grp,tr,score,counts,members,hits)


def fitted_rate(totals,hits):
    return [(hits[c]+BASE*PRIOR)/(totals[c]+PRIOR) for c in range(18)]


def largest_remainder(exp_counts,members):
    """Integer seats summing 20, respecting category pool capacities."""
    masses=[sum(exp_counts[g*3+j] for j in range(3)) for g in range(6)]
    raw=[20*x/sum(masses) for x in masses]
    floors=[min(COUNTS[g],int(math.floor(raw[g]))) for g in range(6)]
    missing=20-sum(floors)
    for g in sorted(range(6),key=lambda g:(-(raw[g]-math.floor(raw[g])),g)):
        if not missing:break
        if floors[g]<COUNTS[g]:
            floors[g]+=1;missing-=1
    if missing:
        for g in range(6):
            if not missing:break
            room=COUNTS[g]-floors[g]
            take=min(room,missing);floors[g]+=take;missing-=take
    assert sum(floors)==20
    return floors


def evaluate_target(t,draw,p,e,L,method,rate,detail=False):
    grp,tr,score,counts,members,hits=classify_and_count(
        t,L,method,p,e,draw["nums"])
    obs=set(draw["nums"])
    arr=[rate[grp[n]*3+tr[n]] for n in range(1,81)]
    brier=sum((arr[n-1]-(1 if n in obs else 0))**2 for n in range(1,81))/80
    expected_bins=[counts[c]*rate[c] for c in range(18)]
    predicted_seats=largest_remainder(expected_bins,members)
    actual_seats=[sum(hits[g*3+j] for j in range(3)) for g in range(6)]
    # FAIR control: use exactly 20 INTEGER seats with unconditional .25,
    # not fractional expected 3.25/3.5 that cannot be submitted as seats.
    # Same largest-remainder rounding as the trained model.
    plain=largest_remainder([counts[c]*BASE for c in range(18)],members)
    mae=sum(abs(predicted_seats[g]-actual_seats[g]) for g in range(6))/6
    null_mae=sum(abs(plain[g]-actual_seats[g]) for g in range(6))/6
    selection=tuple(sorted(range(1,81),key=lambda n:(-arr[n-1],-score[n],n))[:20])
    rng=random.Random(int(draw["day"].replace("-",""))*2003+draw["pos"]*139)
    random20=tuple(rng.sample(range(1,81),20))
    hit20=sum(n in obs for n in selection)
    randomhits=sum(n in obs for n in random20)
    result={
        "brier":brier,"seat_mae":mae,"baseline_mae":null_mae,
        "pred20hit":hit20,"random20hit":randomhits,
        "actual_seats":actual_seats,"pred_seats":predicted_seats,
        "groups":grp,"trend":tr,"members":members,"counts":counts,
        "hits":hits,"picked":selection,"random":random20,
    }
    if detail:
        result.update({
            "cell_probs":rate,
            "group_sizes":tuple(len(m) for m in members),
            "group_masses":[sum(expected_bins[g*3:g*3+3]) for g in range(6)],
        })
    return result


def calendar_phases(all_draws,full):
    """Map each complete day to discovery/validation/final test."""
    dates=[d for d,_ in full]
    if len(dates)<72:
        raise ValueError("V27 requires >=72 full days")
    dates=dates[:72]
    indices={}
    for i,d in enumerate(dates):
        indices[d]="Discovery" if i<18 else ("Validation" if i<36 else "Test")
    return indices


def run_study(raw):
    ds,errors=read_draws(raw)
    full,incomplete=group_full_days(ds)
    phase=calendar_phases(ds,full)
    chron,prefix,ewm=make_index(ds)
    targets=[(t,d,phase[d["day"]]) for t,d in enumerate(chron)
             if d["day"] in phase and t>=MAX_WINDOW]
    parts={(L,method):([0]*18,[0]*18) for L in LOOKBACKS for method in METHODS}
    for t,d,p in targets:
        if p!="Discovery":continue
        for (L,method),(cnt,hits) in parts.items():
            _,_,_,sizes,_,taken=classify_and_count(t,L,method,prefix,ewm,d["nums"])
            for j in range(18):
                cnt[j]+=sizes[j];hits[j]+=taken[j]
    calibrated={policy:fitted_rate(*pair) for policy,pair in parts.items()}
    audit=[]
    per_day=defaultdict(lambda:defaultdict(lambda:Counter()))
    stat=defaultdict(lambda:Counter())
    # group buckets for winner are computed below, after validation choice.
    for t,d,p in targets:
        if p=="Discovery":continue
        for (L,method),r in calibrated.items():
            z=evaluate_target(t,d,prefix,ewm,L,method,r)
            rec=stat[(p,L,method)]
            rec["count"]+=1
            for a,b in (("brier","brier"),("seat_mae","seat_mae"),
                        ("baseline_mae","baseline_mae"),
                        ("pred20hit","pred20hit"),("random20hit","random20hit")):
                rec[a]+=z[b]
            for k in range(6):
                rec[f"actual{k}"]+=z["actual_seats"][k]
                rec[f"pred{k}"]+=z["pred_seats"][k]
            per_day[(p,L,method)][d["day"]]["brier"]+=z["brier"]
            per_day[(p,L,method)][d["day"]]["n"]+=1
    for (period,L,method),cnt in sorted(stat.items()):
        N=cnt["count"]
        audit.append({
            "Dönem":period,"Pencere çekiliş":L,"Sıcaklık yöntemi":method,
            "Hedef":N,
            "Brier hata (küçük iyi)":round(cnt["brier"]/N,9),
            "Sabit RNG Brier":.1875,
            "Brier RNG farkı":round(cnt["brier"]/N-.1875,9),
            "20 koltuk MAE":round(cnt["seat_mae"]/N,6),
            "RNG koltuk MAE":round(cnt["baseline_mae"]/N,6),
            "20 sayı ortalama isabet":round(cnt["pred20hit"]/N,6),
            "Rastgele20 ortalama isabet":round(cnt["random20hit"]/N,6),
            "RNG matematik20":5.,
        })
    val=[a for a in audit if a["Dönem"]=="Validation"]
    chosen=min(val,key=lambda r:(r["Brier hata (küçük iyi)"],
                   r["Pencere çekiliş"],r["Sıcaklık yöntemi"]))
    chosenL=chosen["Pencere çekiliş"]
    chosenM=chosen["Sıcaklık yöntemi"]
    chosenKey=(chosenL,chosenM)
    rate=calibrated[chosenKey]
    seatdetails=[];cell=defaultdict(lambda:Counter())
    selected_daily=defaultdict(lambda:Counter())
    shift=defaultdict(lambda:Counter())
    for t,d,p in targets:
        if p!="Test":continue
        z=evaluate_target(t,d,prefix,ewm,chosenL,chosenM,rate,True)
        row={
            "Tarih":d["day"],"Çekiliş no":d["no"],"Sıra":d["pos"],
            "Saat":clock(d["pos"])[0],"Pencere":chosenL,
            "Yöntem":chosenM,"Hedef 20 sayı":key(d["nums"]),
            "Tahmin20":key(z["picked"]),"Rastgele20":key(z["random"]),
            "20 sayı doğru":z["pred20hit"],
            "Rastgele20 doğru":z["random20hit"],
            "Brier":round(z["brier"],8),
            "Koltuğun ortalama mutlak hatası":round(z["seat_mae"],5),
        }
        for g,label in enumerate(GROUPS):
            row[f"{label} havuz"]=COUNTS[g]
            row[f"{label} hedefte"]=z["actual_seats"][g]
            row[f"{label} öngörü"]=z["pred_seats"][g]
        seatdetails.append(row)
        day=selected_daily[d["day"]]
        day["n"]+=1
        day["brier"]+=z["brier"]
        day["mae"]+=z["seat_mae"]
        day["null_mae"]+=z["baseline_mae"]
        day["hit20"]+=z["pred20hit"]
        day["random20"]+=z["random20hit"]
        for g in range(6):
            for trend in range(3):
                cidx=g*3+trend
                keycell=(g,trend)
                cell[keycell]["pool"]+=z["counts"][cidx]
                cell[keycell]["hit"]+=z["hits"][cidx]
                cell[keycell]["expected"]+=z["counts"][cidx]*rate[cidx]
        # Reconstruct the older documented S/OD/OY/YS FOUR x 20 ranks.
        # This is NOT the newer experimental six-group classification.
        # The legacy temperature score uses 12-draw half-life across ALL
        # prior valid observed draws and is NEVER reset at midnight.
        legacy_sorted=sorted(range(1,81),key=lambda n:(ewm[n][t],n))
        for q,label in enumerate(("S","OD","OY","YS")):
            values=legacy_sorted[q*20:(q+1)*20]
            shift[label]["n"]+=1
            shift[label]["hits"]+=sum(n in d["nums"] for n in values)
    cellrows=[]
    for (g,direction),v in sorted(cell.items()):
        pool=v["pool"];hits=v["hit"]
        cellrows.append({
            "Sıcaklık":GROUPS[g],"Sıcaklık sıra":g+1,"Yön":TREND[direction],
            "80'lik havuzda kümülatif sayı hakkı":pool,
            "Hedef20 gerçek koltuk":hits,
            "Beklenen RNG":round(pool*.25,3),
            "Gerçek gerçekleşme yüzdesi":round(hits/pool*100,4) if pool else "",
            "RNG yüzdesi":25.,
            "Öğrenmeden kalibre olasılık":round(rate[g*3+direction]*100,5),
            "Tahmin hedef20 koltuk":round(v["expected"],2),
        })
    oldseat=[{"Eski 4lü 20 sayı grubu":label,
              "Test çekilişi":v["n"],
              "Gerçek 20'nin bu havuzdan koltuğu":v["hits"],
              "Çekiliş başı gerçek koltuk":round(v["hits"]/v["n"],6),
              "RNG çekiliş başı koltuk":5.}
             for label,v in shift.items()]
    dailyrows=[]
    for day,vals in sorted(selected_daily.items()):
        n=vals["n"]
        dailyrows.append({
            "Gün":day,"Çekiliş":n,
            "Brier":round(vals["brier"]/n,9),
            "RNG Brier":.1875,
            "Koltuk MAE":round(vals["mae"]/n,6),
            "RNG koltuk MAE":round(vals["null_mae"]/n,6),
            "20 sayı ortalama":round(vals["hit20"]/n,6),
            "Rastgele20 ortalama":round(vals["random20"]/n,6),
        })
    def ci(vals):
        m=mean(vals)
        e=(sum((x-m)**2 for x in vals)/(len(vals)-1)/len(vals))**.5
        return m,m-1.96*e,m+1.96*e
    cirows=[]
    for label,diffs in [
        ("Brier avantajı (RNG - motor)",[.1875-r["Brier"] for r in dailyrows]),
        ("Koltuk MAE avantajı (RNG - motor)",
         [r["RNG koltuk MAE"]-r["Koltuk MAE"] for r in dailyrows]),
        ("20 sayı isabet farkı (motor - rastgele)",
         [r["20 sayı ortalama"]-r["Rastgele20 ortalama"] for r in dailyrows]),
    ]:
        m,lo,hi=ci(diffs)
        cirows.append({
            "Sınama":"Son36","Ölçüt":label,"Gün":len(diffs),
            "Ortalama fark":round(m,8),"Yaklaşık %95 GA alt":round(lo,8),
            "Yaklaşık %95 GA üst":round(hi,8),
            "Güvenilir üstünlük":lo>0,
        })
    finalsummary=next(z for z in audit if z["Dönem"]=="Test"
                      and z["Pencere çekiliş"]==chosenL
                      and z["Sıcaklık yöntemi"]==chosenM)
    meta={
        "Motor":"V27 altı DENEYSEL sıcaklık, 20 istatistiksel koltuk ve geçmiş uzunluğu",
        "Tam gün":72,"Gözlenen geçerli tüm kayıt":len(chron),
        "Tam gün hedef":72*217,"İlk":list(phase)[0],"Son":list(phase)[-1],
        "Öğrenme gün":18,"Doğrulama gün":18,"Ayrı test gün":36,
        "Geçmiş pencereler":list(LOOKBACKS),"Yöntemler":list(METHODS),
        "Seçilen geçmiş çekiliş":chosenL,
        "Seçilen ısı yöntemi":chosenM,
        "Doğrulama Brier":chosen["Brier hata (küçük iyi)"],
        "Ayrı test Brier":finalsummary["Brier hata (küçük iyi)"],
        "Ayrı test motor 20 isabet":finalsummary["20 sayı ortalama isabet"],
        "Ayrı test rastgele 20 isabet":finalsummary["Rastgele20 ortalama isabet"],
        "Sabit RNG Brier":.1875,
        "6 koltuk sırası":list(GROUPS),
        "6 sınıfın kökeni":"YENİ DENEYSEL sıralama. Eski motorun özgün 6 eşik değeri depoda doğrulanamadı; 13/13/14/14/13/13 sabit havuzlu araştırma alternatifi.",
        "Eski gerçek sıcaklık modeli":"S/OD/OY/YS dört adet 20'li havuz, yarı ömür 12 çekiliş, tüm geçmişten taşınan EWMA, gün başında sıfırlanmaz",
        "6 havuz üye sayısı":list(COUNTS),
        "Yön":"Son 6 görünüş - önceki 6 görünüş en az +2 yükselen, en fazla -2 düşen; aksi dengeli",
        "Sıcaklık bellek yarı ömrü":HALF_LIFE,
        "Kayıtlı geçmiş":"Son X geçerli gerçek çekiliş; gece ve eksik günün olmayan çekilişleri uydurulmaz",
        "Eğitim/test yapısı":"İlk18 hücre frekansları, ikinci18 pencere doğrulaması, sonraki36 sabit bağımsız test",
        "Yorum":"Önceden sınıflandırılmış 80 sayı hedefte 20 sayının grup sandalye sayısını verir, resmi çekiliş sırası değildir.",
        "Koltuk karşılaştırması":"Öğrenilmiş 20 TAM SAYI koltuk kotası ile aynı en-büyük-kalan yuvarlamasını kullanan RNG tabanlı 20 TAM SAYI koltuk kotası karşılaştırılır.",
        "Veri hataları":errors,"Eksik günler":incomplete,
    }
    report={
        "ozet.json":json.dumps(meta,ensure_ascii=False,indent=2).encode("utf-8"),
        "tum_pencereler_dogrulama_ve_test.csv":csv_bytes(audit),
        "son36_20_koltuk_hedef_hedef.csv":csv_bytes(seatdetails),
        "son36_18_isi_ve_yon_hucresi.csv":csv_bytes(cellrows),
        "son36_eski_dort_20li_koltuk.csv":csv_bytes(oldseat),
        "son36_gun_gun_performans.csv":csv_bytes(dailyrows),
        "son36_guven_araligi.csv":csv_bytes(cirows),
    }
    return report,meta,finalsummary,cirows,cellrows,audit


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--data",default="veri.txt")
    parser.add_argument("--output",default="V27_ALTI_ISI_20_KOLTUK_72_GUN_TAM.zip")
    args=parser.parse_args()
    data,meta,s,ci,cell,audit=run_study(
        Path(args.data).read_text(encoding="utf-8-sig"))
    with zipfile.ZipFile(args.output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,payload in data.items():z.writestr(name,payload)
    print("V27_PASS",json.dumps({k:meta[k] for k in (
        "Tam gün","Seçilen geçmiş çekiliş","Seçilen ısı yöntemi","Ayrı test Brier",
        "Ayrı test motor 20 isabet","Ayrı test rastgele 20 isabet")},ensure_ascii=False),flush=True)
    for r in sorted([a for a in audit if a["Dönem"]=="Test"],
        key=lambda x:x["Brier hata (küçük iyi)"])[:10]:
        print("V27_AUDIT",json.dumps(r,ensure_ascii=False),flush=True)
    for r in cell: print("V27_CELL",json.dumps(r,ensure_ascii=False),flush=True)
    for r in ci: print("V27_CI",json.dumps(r,ensure_ascii=False),flush=True)
    print("V27_ZIP",args.output,flush=True)


if __name__=="__main__":
    main()
