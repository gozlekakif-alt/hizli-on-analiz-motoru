#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V103 — 56 FIFO-ring direction chains -> H1..H12 descriptive FORECAST LEDGER.

No tickets, no 20-number hit optimization. V100C and V102 unchanged.
All prehour features are computed strictly before first target draw:
 - Stable 12-draw ring IDs, exactly previous 672 observed records.
 - Prior 55-56 SEALED rings, trailing72 16/16/16/16/16 temp pools.
 - For each of 80 numbers, last-6-ring net direction + latest pool.
 - 12-draw frozen predicted appearance counts by direction group.
After H1..H6 has occurred, update H7..H12 probabilities from TRAIN-only
conditional table. Actuals are attached only AFTER freeze.

Fit once on first 36 complete historical days; evaluate middle18,
last18, and Oct-13+ separately. Prior 72 days repeatedly researched:
these results must not be represented as a virgin prospective test.
Permanent unscored NEXT-HOUR preforecast JSON contains no target results.
"""
from __future__ import annotations
import argparse,collections,csv,datetime,io,json,math,zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load
from v102_80sayi_56_halka_yon_zinciri_hedef_saat import (
    expected_hours,pool_cache,history,POOL)
VERSION="V103.1"
DIR=("SOGUYOR","DENGELI","ISINIYOR")
GROUPS=range(3)
PHASES=("TRAIN36","VALIDATE18","HOLDOUT18","NEW_DATA")
PRIOR_PRE=2400.0
PRIOR_AFTER=900.0
BASE=.25

def bucket(sign):
    return np.where(sign<0,0,np.where(sign>0,2,1)).astype(np.int8)

def features(prefix,cache,t):
    rings,full,S,W,D=history(t,prefix,cache)
    trend=(S[:,-1]-S[:,-7]).astype(np.int8)
    dirs=bucket(trend)
    pools=S[:,-1]
    assert len(pools)==80 and len(dirs)==80
    return dirs,pools,trend,full,rings,S,D

def phase(day,history_days):
    if day>"2026-10-12":return "NEW_DATA"
    idx=history_days.index(day)
    return PHASES[0 if idx<36 else 1 if idx<54 else 2]

def csvw(z,name,arr):
    if not arr:return
    with z.open(name,"w",force_zip64=True) as b:
        f=io.TextIOWrapper(b,encoding="utf-8",newline="")
        w=csv.DictWriter(f,fieldnames=list(arr[0]))
        w.writeheader();w.writerows(arr);f.flush();f.detach()

def training_table(hours,X,prefix,cache,history_days):
    """Fit on first36 ONLY; future validation outcomes not touched."""
    n1=np.zeros((3,5),dtype=np.int64);y1=np.zeros_like(n1)
    n2=np.zeros((3,5,4),dtype=np.int64);y2=np.zeros_like(n2)
    records=0
    for t,day,clock,ids in hours:
        if phase(day,history_days)!="TRAIN36":continue
        dirs,pool,trend,full,rings,S,D=features(prefix,cache,t)
        A=X[t:t+12]
        cfirst=A[:6].sum(axis=0)
        csecond=A[6:].sum(axis=0)
        for n in range(80):
            di=int(dirs[n]);p=int(pool[n]);k=min(3,int(cfirst[n]))
            n1[di,p]+=12
            y1[di,p]+=int(cfirst[n])+int(csecond[n])
            n2[di,p,k]+=6
            y2[di,p,k]+=int(csecond[n])
        records+=1
    assert records>200 and int(n1.sum())==records*80*12
    P1=(y1+PRIOR_PRE*BASE)/(n1+PRIOR_PRE)
    P2=(y2+PRIOR_AFTER*P1[:,:,None])/(n2+PRIOR_AFTER)
    assert np.all((P1>0)&(P1<1))
    assert np.all((P2>0)&(P2<1))
    return P1,P2,n1,y1,n2,y2,records

def brier(pre_hits,post_hits,p_pre,p_post):
    # Pre: 12 ball-draw outcomes, post: last 6 only. This does not
    # assume number-hits independent, just uses proper per-ball score.
    loss_pre=np.sum(pre_hits-2*p_pre*pre_hits+12*p_pre*p_pre)/(80*12)
    loss_post=np.sum(post_hits-2*p_post*post_hits+6*p_post*p_post)/(80*6)
    return float(loss_pre),float(loss_post)

def summarise(rows):
    data=[]
    for phase_label in PHASES:
        sub=[r for r in rows if r["phase"]==phase_label]
        if not sub:continue
        for metric in ("brier_prehour","brier_after_H6","hour_cohort_abs_error",
                       "hour_cohort_abs_error_base"):
            a=np.asarray([r[metric] for r in sub],dtype=float)
            data.append(dict(phase=phase_label,metric=metric,
                             hours=len(a),mean=float(a.mean()),
                             baseline=(0.1875 if metric.startswith("brier")
                                       else "")))
    return data

def process(src,dest):
    days,rows,X,issues,bad=load(src)
    hourset,rejected=expected_hours(rows)
    prefix=np.vstack((np.zeros((1,80),np.int32),np.cumsum(X,axis=0,dtype=np.int32)))
    cache=pool_cache(prefix)
    historical=days[:72]
    P1,P2,n1,y1,n2,y2,fit_hours=training_table(hourset,X,prefix,cache,historical)
    summaries=[]; profiles=[]; bygroup=[]; after6=[]; latest=None; stage_out=[]
    # Evaluate in strict forward order. Parameters are frozen from 36
    # days before evaluating VALIDATE/HOLDOUT/NEW_DATA.
    for i,(t,day,clock,ids) in enumerate(hourset):
        if phase(day,historical)=="TRAIN36":continue
        pg=phase(day,historical)
        dirs,pools,trend,full,rings,S,D=features(prefix,cache,t)
        hour=X[t:t+12]
        H1=hour[:6].sum(axis=0).astype(np.int16)
        H2=hour[6:].sum(axis=0).astype(np.int16)
        H=H1+H2
        prior=P1[dirs,pools]
        updated=P2[dirs,pools,np.minimum(H1,3)]
        preloss,postloss=brier(H,H2,prior,updated)
        observed_labels=["".join(map(str,map(int,hour[:,n]))) for n in range(80)]
        hourname=f"{day} {clock:02d}:02-{clock:02d}:57"
        group_abs=0.;group_base=0.
        for di in GROUPS:
            mask=(dirs==di)
            n=int(mask.sum())
            obs_first=int(H1[mask].sum())
            obs_last=int(H2[mask].sum())
            obs_all=obs_first+obs_last
            forecast_all=float(12*prior[mask].sum())
            forecast_after=float(6*updated[mask].sum())
            expectation_base=12*n*.25
            group_abs+=abs(obs_all-forecast_all)
            group_base+=abs(obs_all-expectation_base)
            bygroup.append(dict(phase=pg,day=day,hour=hourname,
                first_draw_id=ids[0],dir=DIR[di],group_size=n,
                frozen_expected_H1_H12=round(forecast_all,5),
                observed_H1_H12=obs_all,
                frozen_expected_H1_H6=round(forecast_all/2,5),
                observed_H1_H6=obs_first,
                after_first6_expected_H7_H12=round(forecast_after,5),
                observed_H7_H12=obs_last,
                baseline_expected_H1_H12=expectation_base,
                absolute_error_frozen=round(abs(obs_all-forecast_all),6),
                absolute_error_baseline=round(abs(obs_all-expectation_base),6),
                numbers="-".join(str(n+1) for n in np.flatnonzero(mask)),
                H1_H12_appeared_numbers="-".join(
                    str(n+1) for n in np.flatnonzero(mask&(H>0))),
                H7_H12_appeared_numbers="-".join(
                    str(n+1) for n in np.flatnonzero(mask&(H2>0)))))
        summaries.append(dict(phase=pg,day=day,hour=hourname,
            H1_id=ids[0],H12_id=ids[-1],oldest_known_id=rows[t-672]["id"],
            latest_known_id=rows[t-1]["id"],sealed_rings=len(full),
            brier_prehour=round(preloss,9),
            brier_after_H6=round(postloss,9),
            baseline_brier=0.1875,
            hour_cohort_abs_error=round(group_abs,8),
            hour_cohort_abs_error_base=round(group_base,8)))
        if pg=="NEW_DATA" or i==len(hourset)-1:
            # 80-ball individual historical post-hoc ledger.
            for n in range(80):
                profiles.append(dict(phase=pg,day=day,hour=hourname,
                    ball=n+1,pre_dir=DIR[int(dirs[n])],
                    pool=POOL[int(pools[n])],net6=int(trend[n]),
                    temp_path="".join("CSNIH"[int(v)] for v in S[n]),
                    sign_path="".join("Y" if v>0 else "D" if v<0 else "=" for v in D[n]),
                    frozen_p_per_draw=round(float(prior[n]),8),
                    first6_observed=int(H1[n]),
                    updated_afterH6_p_per_draw=round(float(updated[n]),8),
                    last6_observed=int(H2[n]),
                    all12_observed=int(H[n]),
                    drawn_hands="-".join(str(j+1) for j,v in enumerate(hour[:,n]) if v),
                    observed_bits=observed_labels[n]))
        if i==len(hourset)-1:
            latest=dict(day=day,hour=hourname,first_id=ids[0],last_id=ids[-1],
                prehour=dict(p=prior.tolist(),dirs=dirs.tolist(),pool=pools.tolist()),
                first6_observed=H1.tolist(),
                post6_probs=updated.tolist(),
                group_ids={DIR[di]:[int(k+1) for k in np.flatnonzero(dirs==di)]
                           for di in GROUPS})
        if i%180==0:print("V103 analyzed hour",i,"/",len(hourset),flush=True)
    # Freeze a genuinely as-yet-UNOBSERVED next-hour reference from the
    # current last available draw. No next target result/ID is invented.
    t=len(rows)
    dirs,pools,trend,full,rings,S,D=features(prefix,cache,t)
    forecast=P1[dirs,pools]
    future={
       "version":VERSION,
       "frozen_known_up_to_id":int(rows[-1]["id"]),
       "frozen_known_date":rows[-1]["day"],
       "frozen_known_clock":rows[-1]["time"],
       "next_hour_unobserved":True,
       "next_target_id":None,
       "reference_672_from_id":int(rows[t-672]["id"]),
       "reference_672_to_id":int(rows[-1]["id"]),
       "actual_12_draw_outcomes":None,
       "dir_group_targets":{
           DIR[d]:dict(numbers=[int(k+1) for k in np.flatnonzero(dirs==d)],
                       how_many=int(np.sum(dirs==d)),
                       expected_drawn_positions_H1_H12=round(
                         12*float(forecast[dirs==d].sum()),4),
                       baseline_expected=round(3*float(np.sum(dirs==d)),4),
                       expected_drawn_positions_H1_H6=round(
                         6*float(forecast[dirs==d].sum()),4))
           for d in GROUPS},
       "number_probabilities_per_draw":{
           str(n+1):dict(direction=DIR[int(dirs[n])],
                   latest_72_pool=POOL[int(pools[n])],
                   net_last6=int(trend[n]),
                   prob_model=round(float(forecast[n]),8),
                   baseline=0.25,
                   latest_56_ring_path="".join("CSNIH"[int(v)] for v in S[n]))
           for n in range(80)},
       "status":"Frozen before next unknown target; not proof of prospective accuracy.",
       "warning":"Date is latest repository record, NOT current real-time data."
    }
    aggregate=summarise(summaries)
    pregroup=[]
    for d in GROUPS:
        for p in range(5):
            pregroup.append(dict(direction=DIR[d],pool=POOL[p],
                training_ball_draws=int(n1[d,p]),training_hits=int(y1[d,p]),
                trained_p=round(float(P1[d,p]),8)))
    aftergroup=[]
    for d in GROUPS:
        for p in range(5):
            for k in range(4):
                aftergroup.append(dict(direction=DIR[d],pool=POOL[p],
                    first6_num_hits_bucket=(str(k) if k<3 else "3PLUS"),
                    training_ball_draws=int(n2[d,p,k]),training_hits=int(y2[d,p,k]),
                    trained_last6_p=round(float(P2[d,p,k]),8)))
    # Last-hour weathered type example group outcomes.
    lastgroup=[x for x in bygroup if x["hour"]==latest["hour"]]
    report=[
      "V103 | 672 FIFO YURUYEN HALKA, 56 YON ZINCIRI -> HEDEF SAAT ONGORU KAYDI",
      "Basamak1: hedef saatten ONCE 80 sayinin en son 55/56 dolu halka yon kimligi.",
      "Basamak2: TRAİN36 zaman diliminde o yon+havuz kadrolarinin saatlik gelme sikligi.",
      "Basamak3: H1..H12 icin yon kadrosu beklenen toplam gorunumu ONCEDEN yaz.",
      "Basamak4: H1..H6 gercek verisi geldikten sonra H7..H12 tahminini dondur.",
      "Basamak5: saat bitince 12 cekilisi hedef sonucuyla karsilastir.",
      "KUPON MOTORU DEGIL: kadro davranisi, gorunme sayisi ve tahmin kaydi.",
      f"Egitim saati={fit_hours}; hedef analizinde degerlendirilen saat={len(summaries)}.",
      "Sabit baz: Her 80 sayidan biri her cekiliste %25, 12 cekiliste ortalama 3 kere.",
      "12 cektikce 80 sayinin 20si bir elde cikiyor; 12 el toplam 240 gorunum.",
      "",
      "KAYDI OLAN SIRA ILE DEGERLENDIRME:"]
    for a in aggregate:
        if a["metric"]=="brier_prehour":
            ph=a["phase"]
            new=next(x for x in aggregate if x["phase"]==ph and x["metric"]=="brier_after_H6")
            mae=next(x for x in aggregate if x["phase"]==ph and x["metric"]=="hour_cohort_abs_error")
            base=next(x for x in aggregate if x["phase"]==ph and x["metric"]=="hour_cohort_abs_error_base")
            report.append(f" {ph:11s} saat={a['hours']:4d} Brier1..12={a['mean']:.9f} "
              f"Brier7..12(after6)={new['mean']:.9f} "
              f"3 yon grup saat toplam hata={mae['mean']:.4f}, "
              f"baz hata={base['mean']:.4f}")
    report.extend(["","SON KAYITLI TAM SAAT (H1...H12): "+latest["hour"],
       f"H1 #{latest['first_id']} H12 #{latest['last_id']}",
       "Yon grubu        N      beklenen12      gercek12      son6-on-gorulen      gercek-son6"])
    for g in lastgroup:
        report.append(f" {g['dir']:<12s} {g['group_size']:3d} "
           f"{g['frozen_expected_H1_H12']:13.3f} "
           f"{g['observed_H1_H12']:13d} "
           f"{g['after_first6_expected_H7_H12']:17.3f} "
           f"{g['observed_H7_H12']:13d}")
    report.extend(["",
       f"Son gercek kayit #{rows[-1]['id']} {rows[-1]['day']} {rows[-1]['time']}.",
       "SIRADAKI kayitli olmayan saat icin 80 sayinin ONCEDEN yon/olasik kadro raporu",
       "'08_HENUZ_GELMEMIS_SAAT_KILITLI_ONGORU.json' icinde korunuyor.",
       "Gelecekteki saat sonucunu bilmiyoruz ve uydurmuyoruz.",
       "Bu test bir lotarya RNG cozumu veya onceden kanitlanmis avantaj degildir.",
       "Eski 72 gun daha once incelenmistir; yalniz yeni cekilislerin zaman damgali",
       "tahminlerle takip edilmesi bagimsiz teyit saglayabilir."])
    metadata=dict(version=VERSION,last_known_id=rows[-1]["id"],
      source_draws=len(rows),hour_targets=len(hourset),rejected_hour_groups=rejected,
      fit_hours_first36=fit_hours,source_issues=issues[:20],
      malformed_lines=bad[:20],
      training_method="direction(last6 net) x latest72rank with beta shrink 2400; first6 count 0,1,2,3+ with shrink 900",
      target_per_draw_base_probability=0.25,
      first_stage_uses_only_previous_672_draws=True,
      afterH6_uses_first6_only=True,
      labels_only_attached_after_hour=True,
      source_stale_relative_to_current_date=True)
    dst=Path(dest);dst.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dst,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_V103_SAAT_TAHMINI_YON_KADRO_SONUC.txt","\n".join(report)+"\n")
        csvw(z,"01_DONEMLERE_GORE_ONGORU_KALIBRASYON.csv",aggregate)
        csvw(z,"02_TUM_HEDEF_SAATLER_SABIT_ONGORU_KARSI.csv",summaries)
        csvw(z,"03_HEDEF_SAAT_ISINAN_SOGUYAN_KADRO_TAHMIN_GERCEK.csv",bygroup)
        csvw(z,"04_HEDEF_SAAT_80_SAYI_YON_ZINCIR_13EKIM.csv",profiles)
        csvw(z,"05_36GUN_EGITIM_YON_HAVUZ_IHTIMALLERI.csv",pregroup)
        csvw(z,"06_ILK6_OLDUKTAN_SONRA_7_12_KOSULLU.csv",aftergroup)
        z.writestr("07_SON_TAM_SAAT_ONCE_SONRA_DONDURULMUS.json",
                   json.dumps(latest,ensure_ascii=False,indent=2))
        z.writestr("08_HENUZ_GELMEMIS_SAAT_KILITLI_ONGORU.json",
                   json.dumps(future,ensure_ascii=False,indent=2))
        z.writestr("09_TAM_METOT_VE_VERI_SIZMA_DENETIMI.json",
                   json.dumps(metadata,ensure_ascii=False,indent=2,default=str))
    print("\n".join(report),flush=True)
    print("V103 DONE",str(dst),dst.stat().st_size,flush=True)

def selftest():
    B=np.array([-3,-1,0,1,3])
    assert tuple(bucket(B))==(0,0,1,2,2)
    P1=np.full((3,5),.25);P2=np.full((3,5,4),.25)
    t=np.full(80,3);u=np.full(80,1)
    a,b=brier(t,u,np.full(80,.25),np.full(80,.25))
    assert abs(a-(3-2*.25*3+12*.25**2)/12)<1e-12
    assert abs(b-(1-2*.25*1+6*.25**2)/6)<1e-12
    print("V103 SELFTEST OK",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",default="veri.txt")
    parser.add_argument("--out",default="v103_output/V103_56_HALKA_HEDEF_SAAT_ONGORU_KILITLI.zip")
    parser.add_argument("--selftest",action="store_true")
    args=parser.parse_args()
    if args.selftest:selftest()
    else:process(args.source,args.out)
