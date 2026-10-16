#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V106: identify WARMING 56-ring chain balls with 5/6/7/8 appearances
in the NEXT 12-draw HOUR. Separate hour-start features from hour results.

V100C/V104 stable 12-ball ring identities and FIFO 672 memory untouched.
Find names for every verified hour, chain classes and 12 bit hand path.
All features are computed from t-672:t *before* target hour t:t+12.
Historical TRAIN36/LAST36/NEW_DATA descriptive tables + stable estimates;
do not optimize 20-number tickets or assert guaranteed future streaks.
"""
from __future__ import annotations
import argparse,collections,csv,io,json,math,zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load,temperature
from v104_72gun_basindan_672_56_halka_fifo_yon import stable_paths
from v102_80sayi_56_halka_yon_zinciri_hedef_saat import expected_hours
VERSION="V106.1"
CHAR="CSNIH"
STEPS={-1:"D",0:"=",1:"Y"}
TEMP=("SOGUK","SERIN","NOTR","ILIK","SICAK")
PERIODS=("FIRST36","LAST36","NEW_DATA")
THRESHOLDS=(5,6,7,8)
SMOOTH=300

def cwriter(z,name,data):
    if not data:return
    with z.open(name,"w",force_zip64=True) as r:
        out=io.TextIOWrapper(r,encoding="utf-8",newline="")
        w=csv.DictWriter(out,fieldnames=list(data[0]))
        w.writeheader();w.writerows(data)
        out.flush();out.detach()

def expected(n,p):
    return sum(math.comb(n,k)*p**k*(1-p)**(n-k) for k in range(pand(n),n+1))

def pand(n):
    return 5

def probability_ge(threshold):
    return sum(math.comb(12,k)*.25**k*.75**(12-k)
               for k in range(threshold,13))

def ring_features(S,D):
    """Every ring is chronologically sealed before the target hour."""
    now=S[:,-1]
    net6=S[:,-1]-S[:,-7]
    step=D[:,-1]
    old=S[:,:-7]
    coldold=(old==0).sum(axis=1)
    hotold=(old==4).sum(axis=1)
    # all nonrecent rings DO contribute as historical covariates
    oldmoves=(np.diff(old,axis=1)!=0).sum(axis=1)
    allmoves=(D!=0).sum(axis=1)
    n_old=old.shape[1]
    recent_cold=(S[:,-12:-6]==0).sum(axis=1)
    young6=(D[:,-6:]>0).sum(axis=1)
    young6down=(D[:,-6:]<0).sum(axis=1)
    short_class=np.where(net6>0,"ISINIYOR",
            np.where(net6<0,"SOGUYOR","DENGELI"))
    # Fixed labels chosen without reading the target hour.
    temperature_path=np.array(["".join(CHAR[int(v)] for v in S[i])
                               for i in range(80)])
    movement_path=np.array(["".join(STEPS[int(v)] for v in D[i])
                             for i in range(80)])
    oldcold=np.where(coldold>=12,"UZUN_SOGUK",
                  np.where(coldold>=6,"ORTA_SOGUK","AZ_SOGUK"))
    oldhot=np.where(hotold>=12,"UZUN_SICAK",
                 np.where(hotold>=6,"ORTA_SICAK","AZ_SICAK"))
    waves=np.where(oldmoves>=27,"DALGALI",
             np.where(oldmoves>=20,"ORTA_HAREKET","SAKIN"))
    style=[]
    for i in range(80):
        if net6[i]<=0:
            style.append("ISINMIYOR")
        elif recent_cold[i]>=3:
            style.append("SOGUKTAN_UYANAN")
        elif young6[i]>=2 and young6down[i]>0:
            style.append("INI_CIKISLI_ISINAN")
        elif now[i]>=3:
            style.append("ILIK_SICAKTA_YUKSELEN")
        else:
            style.append("ALT_HAVUZDA_YUKSELEN")
    return dict(now=now,net6=net6,laststep=step,
        oldcold=coldold,oldhot=hotold,oldmoves=oldmoves,
        moves=allmoves,oldclass=oldcold,
        oldhotclass=oldhot,waves=waves,style=np.array(style),
        warming=short_class,full_heat_path=temperature_path,
        full_direction_path=movement_path,prev6cold=recent_cold,
        recentup=young6,recentdown=young6down,
        total_older_rings=n_old)

def period_of(date,days):
    if date>"2026-10-12":return "NEW_DATA"
    return "FIRST36" if days.index(date)<36 else "LAST36"

def add(counter,key,hits):
    a=counter[key]
    a[0]+=1
    for k,thr in enumerate(THRESHOLDS,1):
        a[k]+=int(hits>=thr)
    for k in range(5):
        a[k+5]+=int(hits==k+5)
    a[9]+=int(hits>=9)
    a[10]+=hits

def rowify(counter,kind):
    result=[]
    for key,a in sorted(counter.items()):
        n=a[0]
        result.append(dict(grouping=kind,key="|".join(map(str,key)),
          samples=n,atleast5=a[1],atleast6=a[2],
          atleast7=a[3],atleast8=a[4],
          exactly5=a[5],exactly6=a[6],
          exactly7=a[7],exactly8=a[8],
          nineplus=a[9],total_occurrences=a[10],
          p5=round(a[1]/n*100,4),
          p6=round(a[2]/n*100,4),
          p7=round(a[3]/n*100,4),
          p8=round(a[4]/n*100,4),
          mean_per_hour=round(a[10]/n,4)))
    return result

def run(src,out):
    days,rows,X,issues,bad=load(src)
    n=len(rows)
    prefix=np.vstack((np.zeros((1,80),np.int32),
                      np.cumsum(X,axis=0,dtype=np.int32)))
    seal=np.empty((n//12,80),np.int8)
    for rid in range(n//12):
        end=(rid+1)*12
        seal[rid]=temperature(prefix[end]-prefix[max(0,end-72)])
    # Uses the same fully-grounded target clock hours as V102/V104.
    hourset,rejected=expected_hours(rows)
    hourset=[(t,day,clock,ids) for t,day,clock,ids in hourset
             if t+12<=n]
    allrows=[]
    hitrows=[]
    eachhour=[]
    totals=collections.defaultdict(lambda:[0]*11)
    bystyle=collections.defaultdict(lambda:[0]*11)
    byold=collections.defaultdict(lambda:[0]*11)
    byage=collections.defaultdict(lambda:[0]*11)
    flat=collections.defaultdict(lambda:[0]*11)
    cohort_samples=collections.defaultdict(list)
    for ih,(t,day,hh,ids) in enumerate(hourset):
        gids,S,D=stable_paths(t,seal)
        feat=ring_features(S,D)
        observed=X[t:t+12]
        counts=observed.sum(axis=0).astype(int)
        bits=["".join(str(int(observed[hand,j])) for hand in range(12))
              for j in range(80)]
        pl=period_of(day,days)
        name=f"{day} {hh:02d}:02-{hh:02d}:57"
        warm_counts=collections.Counter()
        warm_numbers=[]
        summary={"day":day,"target_hour":name,"period":pl,
            "H1_id":ids[0],"H12_id":ids[-1],
            "before_hour_latest_id":rows[t-1]["id"],
            "previous_672_first_id":rows[t-672]["id"],
            "complete_rings":len(gids)}
        for j in range(80):
            c=int(counts[j])
            heating=feat["warming"][j]=="ISINIYOR"
            # Short prefix (pool + last6 net sign) and full56 old50 traits.
            short=(TEMP[int(feat["now"][j])],str(feat["warming"][j]))
            full=(TEMP[int(feat["now"][j])],str(feat["warming"][j]),
                  str(feat["waves"][j]),str(feat["oldclass"][j]))
            first6=int(observed[:6,j].sum())
            row=dict(period=pl,day=day,target_hour=name,
                 target_start_id=ids[0],target_end_id=ids[-1],
                 number=j+1,warming_last6=int(heating),
                 net6=int(feat["net6"][j]),
                 last_pool=TEMP[int(feat["now"][j])],
                 last_step=STEPS[int(feat["laststep"][j])],
                 old50_cold_rings=int(feat["oldcold"][j]),
                 old50_hot_rings=int(feat["oldhot"][j]),
                 old50_movements=int(feat["oldmoves"][j]),
                 old50_cold_class=str(feat["oldclass"][j]),
                 old50_hot_class=str(feat["oldhotclass"][j]),
                 old50_wave_class=str(feat["waves"][j]),
                 warming_style=str(feat["style"][j]),
                 recent6_ups=int(feat["recentup"][j]),
                 recent6_downs=int(feat["recentdown"][j]),
                 temperature_chain_55_56=str(feat["full_heat_path"][j]),
                 direction_chain_54_55=str(feat["full_direction_path"][j]),
                 H1_to_H6_count=first6,
                 H7_to_H12_count=c-first6,
                 target_hour_total=c,
                 target_hour_H1_H12=bits[j],
                 target_hands="-".join(str(i+1) for i in range(12)
                    if observed[i,j]==1),
                 exact_5=int(c==5),exact_6=int(c==6),
                 exact_7=int(c==7),exact_8=int(c==8),
                 at_least5=int(c>=5),at_least6=int(c>=6),
                 at_least7=int(c>=7),at_least8=int(c>=8))
            allrows.append(row)
            if c>=5:
                hitrows.append(row)
            add(totals,(pl,str(feat["warming"][j])),c)
            add(bystyle,(pl,str(feat["style"][j])),c)
            add(byold,(pl,)+full,c)
            add(byage,(pl,)+short,c)
            add(flat,(pl,),c)
            if heating and c>=5:
                warm_numbers.append(j+1)
                warm_counts[c]+=1
        summary["warming_number_count"]=int(np.sum(feat["warming"]=="ISINIYOR"))
        summary["warming_exact5_numbers"]="-".join(
            str(j+1) for j in range(80) if
            feat["warming"][j]=="ISINIYOR" and counts[j]==5)
        summary["warming_exact6_numbers"]="-".join(
            str(j+1) for j in range(80) if
            feat["warming"][j]=="ISINIYOR" and counts[j]==6)
        summary["warming_exact7_numbers"]="-".join(
            str(j+1) for j in range(80) if
            feat["warming"][j]=="ISINIYOR" and counts[j]==7)
        summary["warming_exact8_numbers"]="-".join(
            str(j+1) for j in range(80) if
            feat["warming"][j]=="ISINIYOR" and counts[j]==8)
        summary["warming9plus_numbers"]="-".join(
            str(j+1) for j in range(80) if
            feat["warming"][j]=="ISINIYOR" and counts[j]>=9)
        for threshold in THRESHOLDS:
            summary["warming"+str(threshold)+"plus_count"]=int(np.sum(
                (feat["warming"]=="ISINIYOR")&(counts>=threshold)))
            summary["all"+str(threshold)+"plus_count"]=int(np.sum(
                counts>=threshold))
        summary["warming_first6_2plus_count"]=int(np.sum(
            (feat["warming"]=="ISINIYOR")&
            (observed[:6].sum(axis=0)>=2)))
        eachhour.append(summary)
        if ih%250==0:print("V106 indexed target hours",ih,"/",len(hourset),flush=True)

    periodrows=rowify(totals,"period|warming_last6")
    stylerows=rowify(bystyle,"period|warming_style")
    oldrows=rowify(byold,"period|last_pool|warming|old50_wave|old50_cold")
    shortrows=rowify(byage,"period|last_pool|warming")
    allperiod=rowify(flat,"period")

    # Base rates plus conditional warming group based on hour-start path.
    training={}
    alpha=SMOOTH
    for r in oldrows:
        if not r["key"].startswith("FIRST36|"):continue
        training[r["key"][8:]]=r
    shrink=collections.defaultdict(dict)
    for r in shortrows:
        if r["key"].startswith("FIRST36|"):
            shrink[r["key"][8:]]=r
    # Actual last36 group differences recorded without optimizing any rule.
    stability=[]
    for r in oldrows:
        if not r["key"].startswith("LAST36|"):continue
        key=r["key"][7:]
        tr=training.get(key)
        if not tr:continue
        shortname="|".join(key.split("|")[:2])
        prior=shrink.get(shortname)
        if not prior:continue
        for threshold in THRESHOLDS:
            raw=tr["atleast"+str(threshold)]
            p_prior=prior["atleast"+str(threshold)]/prior["samples"]
            modelp=(raw+alpha*p_prior)/(tr["samples"]+alpha)
            stability.append(dict(
                grouping=key,threshold=threshold,
                first36_n=tr["samples"],first36_raw_p=round(
                    raw/tr["samples"],6),
                first36_smoothed_p=round(modelp,6),
                last36_n=r["samples"],
                last36_actual_p=round(
                    r["atleast"+str(threshold)]/r["samples"],6),
                last36_short_p=round(
                    next((s["atleast"+str(threshold)]/s["samples"]
                     for s in shortrows if s["key"]=="LAST36|"+shortname),0),6),
                difference_full_minus_short_pp=round(
                   100*(r["atleast"+str(threshold)]/r["samples"]-
                     next((s["atleast"+str(threshold)]/s["samples"]
                     for s in shortrows if s["key"]=="LAST36|"+shortname),0)),4)))
    last=eachhour[-1]
    last_warm=next(r for r in periodrows if r["key"]=="LAST36|ISINIYOR")
    first_warm=next(r for r in periodrows if r["key"]=="FIRST36|ISINIYOR")
    report=[
      "V106 / Hedef saatte bir ISINAN sayi 5,6,7,8 veya daha cok GELECEK MI?",
      "Burada 5-8 = tek numaranin bir SAATTEKI 12 cekiliste toplam kac kez cikmasi.",
      "Kupon sayisi / 10'lu tutturma ile karistirilmamali.",
      f"Total exact 12-draw target hours={len(hourset)}, excluded incomplete={rejected}.",
      "72 complete days + verified extra day draws already in repository.",
      "For each hour 80 ball pre-hour full55/56 history and H1..H12 result.",
      "Warm definition: sealed last72 pool at latest complete ring higher",
      "than its position 6 full rings earlier (net6>0).",
      "Entire old50 rings used: earlier cold/hot dwell and frequency of moves.",
      "Each observed ball/hour is labeled 0..12 and exactly 5,6,7,8.",
      "",
      "THEORETICAL SINGLE NUMBER APPEARANCE THRESHOLDS per 12 draws:",
    ]
    for thr in THRESHOLDS:
        report.append(f" >= {thr}/12 reference: {100*probability_ge(thr):.5f} percent")
    report +=["","ISINAN historical occurrences per period (not tickets):"]
    for r in (first_warm,last_warm):
        report.append(
          f" {r['key']}: n={r['samples']}; >=5 {r['atleast5']} ({r['p5']:.3f}%),"
          f" >=6 {r['atleast6']} ({r['p6']:.3f}%),"
          f" >=7 {r['atleast7']} ({r['p7']:.3f}%),"
          f" >=8 {r['atleast8']} ({r['p8']:.3f}%).")
    report +=["",
      f"LAST TARGET HOUR {last['target_hour']} H1#{last['H1_id']} H12#{last['H12_id']}",
      f"Total warmed numbers before this hour: {last['warming_number_count']}.",
      "Warm exact repeats from hour results:"]
    for m in range(5,9):
        report.append(f" = {m}: {last['warming_exact'+str(m)+'_numbers'] or 'none'}")
    report.append(f" >=9: {last['warming9plus_numbers'] or 'none'}")
    report+=["",
      "Full56 old50 split (cold time, hot time, amount of up/down)",
      "is stored for every hit number; group threshold rates are in files",
      "04/05/06 and period replication comparison in 07.",
      "Do not claim that a high historical repeated count makes a",
      "particular future number repeat 5-8 times. Investigate which",
      "pre-hour path types remain consistent in later/newly added data.",
      "This is NOT a model selecting gambling tickets."]
    meta=dict(version=VERSION,source_draws=len(rows),
      first_draw_id=rows[0]["id"],last_draw_id=rows[-1]["id"],
      all_target_hours=len(hourset),all_ball_hour_rows=len(allrows),
      at_least5_examples=len(hitrows),excluded_hour_groups=rejected,
      historical_basis="56 stable full 12-draw ring IDs, previous 672 observed draws",
      old50_feature="all sealed pool states except latest 7",
      no_target_leakage=True,source_issues=issues[:10],
      malformed=bad[:10])
    dst=Path(out);dst.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dst,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_ISINAN_SAYI_5_6_7_8_HEDEF_SAAT_RAPOR.txt",
                   "\n".join(report)+"\n")
        cwriter(z,"01_TUM_SAATLER_80_SAYI_TAM56_ZINCIR_0_12_CIKIS.csv",allrows)
        cwriter(z,"02_HEDEF_SAAT_EN_AZ5_OLANLAR_ZINCIRLERI.csv",hitrows)
        cwriter(z,"03_HER_HEDEF_SAAT_ISINAN_5_6_7_8_SAYILAR.csv",eachhour)
        cwriter(z,"04_ISINMA_ILE_5_6_7_8_ORANLARI.csv",periodrows)
        cwriter(z,"05_ISINMA_TIPI_5_6_7_8_ORANLARI.csv",stylerows)
        cwriter(z,"06_TAM56_ESKI50_SOGUK_BEKLEME_HAREKET.csv",oldrows)
        cwriter(z,"07_BASLANGIC36_SON36_AYNI_ZINCIR_KARSILASTIR.csv",stability)
        cwriter(z,"08_SON_HAVUZ_SON6_GORUNUS_ORANLARI.csv",shortrows)
        cwriter(z,"09_TUM_SAYILAR_DONEM_5_6_7_8_ORANLARI.csv",allperiod)
        z.writestr("10_KESIN_VERI_VE_YON_TANIMI.json",json.dumps(meta,
                         ensure_ascii=False,indent=2,default=str))
    print("\n".join(report),flush=True)
    print("V106 SUCCESS",dst,dst.stat().st_size,flush=True)

def selftest():
    for n in (5,6,7,8):
        assert 0<probability_ge(n)<1
    assert ring_features(
      np.tile(np.arange(5,dtype=np.int8).repeat(16),(56,1)).T,
      np.zeros((80,55),dtype=np.int8))["now"].shape==(80,)
    assert sum(math.comb(12,k)*.25**k*.75**(12-k) for k in range(13))>0.999999
    print("V106 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v106_output/V106_ISINAN_SAYILAR_HEDEF_SAAT_5_6_7_8.zip")
    p.add_argument("--selftest",action="store_true")
    x=p.parse_args()
    if x.selftest:selftest()
    else:run(x.source,x.out)
