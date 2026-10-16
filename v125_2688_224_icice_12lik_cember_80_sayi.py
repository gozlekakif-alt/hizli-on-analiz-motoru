#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V125: 672*4=2688 actual observed draws; 224 NESTED circles each +12.
Source: repo veri.txt via already-reviewed v100c parser. Historical draws
are kept contiguous in supplied draw ordering; never invent missing records.

Frozen next-draw tickets HOT672/1344/2016/2688 vs RANDOM are exploratory,
without families and without downstream outcome leaking into features.
"""
from __future__ import annotations
import argparse, collections, csv, io, json, random, zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load

NS=(672,1344,2016,2688)
LENS=np.arange(12,2689,12,dtype=np.int32)
POOL=("SOGUK","SERIN","NOTR","ILIK","SICAK")
assert len(LENS)==224 and LENS[0]==12 and LENS[-1]==2688
TICKET_SIZES=(3,4,5,6,8,10,20)
MODELS=("HOT672","HOT1344","HOT2016","HOT2688","COLD2016","COLD2688","RANDOM10")
RSEED=1252688

def pool(counts):
    order=np.argsort(counts,kind="stable")
    s=np.empty(80,dtype=np.uint8)
    s[order]=np.repeat(np.arange(5,dtype=np.uint8),16)
    assert np.all(np.bincount(s,minlength=5)==16)
    return s

def savecsv(z,path,rows):
    if not rows:return
    with z.open(path,"w",force_zip64=True) as raw:
        fd=io.TextIOWrapper(raw,encoding="utf-8-sig",newline="")
        w=csv.DictWriter(fd,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
        fd.flush();fd.detach()

def main(source,out):
    days,rows,X,issues,bad=load(source)
    n=len(rows)
    assert n==len(X) and n>=2689
    assert np.all(X.sum(axis=1)==20)
    pref=np.vstack([np.zeros((1,80),dtype=np.int32),
                     np.cumsum(X,axis=0,dtype=np.int32)])
    assert (pref[n]-pref[n-2688]).sum()==53760

    # This endpoint INCLUDES the latest known observed draw.
    end_counts={w:pref[n]-pref[n-w] for w in NS}
    summaries=[]
    for w in NS:
        z=end_counts[w]
        maximum=int(z.max());minimum=int(z.min())
        high=np.flatnonzero(z==maximum)+1
        low=np.flatnonzero(z==minimum)+1
        summaries.append(dict(last_window_draws=w,
          total_drawn_balls=int(z.sum()),
          expected_per_number=w/4,
          actual_max=maximum,actual_max_numbers=high.tolist(),
          actual_min=minimum,actual_min_numbers=low.tolist(),
          extreme_gap=maximum-minimum,
          gap_divided_by_expected_avg=round((maximum-minimum)/(w/4),7),
          window_first_id=rows[n-w]["id"],
          window_last_id=rows[-1]["id"]))
    cnt224=pref[n][None,:]-pref[n-LENS,:]
    cl224=np.stack([pool(x) for x in cnt224],axis=0)
    assert cnt224.shape==(224,80) and cl224.shape==(224,80)
    assert np.all(cnt224.sum(axis=1)==20*LENS)
    p56=cl224[55];p112=cl224[111];p168=cl224[167];p224=cl224[223]
    n80=[]
    for i in range(80):
        n80.append(dict(number=i+1,
            count672=int(end_counts[672][i]),
            count1344=int(end_counts[1344][i]),
            count2016=int(end_counts[2016][i]),
            count2688=int(end_counts[2688][i]),
            window_rank_pool672=POOL[int(p56[i])],
            window_rank_pool1344=POOL[int(p112[i])],
            window_rank_pool2016=POOL[int(p168[i])],
            window_rank_pool2688=POOL[int(p224[i])],
            all224_cumulative_counts="|".join(map(str,cnt224[:,i])),
            all224_nested_temp="".join("CSNIH"[int(x)] for x in cl224[:,i]),
            past2688_1_0="".join(str(int(x)) for x in X[n-2688:n,i])))
    overlap_rows=[]
    for a,b in ((672,1344),(1344,2016),(2016,2688),(672,2016),(672,2688),(1344,2688)):
        q=pool(end_counts[a]);r=pool(end_counts[b])
        overlap_rows.append(dict(compare=f"{a}_vs_{b}",
            same_pool_members=int((q==r).sum()),
            change_pool_members=int((q!=r).sum()),
            changed2plus_classes=int((np.abs(q.astype(int)-r.astype(int))>=2).sum()),
            hot_top16_overlap=int(((q==4)&(r==4)).sum()),
            cold_bottom16_overlap=int(((q==0)&(r==0)).sum())))

    # Single-target historical replay: t's observed result is used only AFTER
    # frozen candidate selection based on P[t]−P[t−window].
    final_dates=sorted(d for d in days if d<="2026-10-12")
    assert len(final_dates)==72
    period={d:("EARLY36" if i<36 else "VALIDATE18" if i<54 else "LAST18")
            for i,d in enumerate(final_dates)}
    results=collections.defaultdict(lambda:[0]*9)
    draws=collections.Counter()
    per_draw=[]
    per_day=collections.defaultdict(list)
    for t in range(2688,n):
        day=rows[t]["day"]
        phase=period.get(day,"ADDED_AFTER_OCT12")
        draws[phase]+=1
        scores={f"HOT{w}":pref[t]-pref[t-w] for w in NS}
        scores["COLD2016"]=-(pref[t]-pref[t-2016])
        scores["COLD2688"]=-(pref[t]-pref[t-2688])
        for method in MODELS:
            if method=="RANDOM10":
                chosen=np.array(random.Random(RSEED+t*3491).sample(range(80),20),
                                 dtype=int)
            else:
                chosen=np.lexsort((np.arange(80),-scores[method]))[:20]
            hit=X[t,chosen]
            cumulative=np.cumsum(hit)
            rec=dict(date=day,period=phase,
                draw_id=rows[t]["id"],method=method,
                pred20="-".join(str(int(x)+1) for x in chosen),
                target20bits="".join(map(str,hit)))
            for k in TICKET_SIZES:
                v=int(cumulative[k-1]);q=results[(phase,method,k)]
                q[0]+=1;q[1]+=v;q[2]+=int(v==k)
                q[3]+=int(v>=5);q[4]+=int(v>=6)
                q[5]+=int(v>=7);q[6]+=int(v>=8)
                q[7]+=int(v>=9);q[8]+=int(v>=10)
                rec["hits"+str(k)]=v
                if k==10 and phase=="LAST18":
                    per_day[(day,method)].append(v)
            per_draw.append(rec)
    score=[]
    for phase in ("VALIDATE18","LAST18","ADDED_AFTER_OCT12","EARLY36"):
        for k in TICKET_SIZES:
            for model in MODELS:
                q=results[(phase,model,k)]
                if not q[0]:continue
                score.append(dict(period=phase,model=model,
                    coupon_size=k,targets=q[0],
                    avg_hits=round(q[1]/q[0],6),
                    fair_mean=k/4,perfect_k_of_k=q[2],
                    hits_5_or_more=q[3],hits_6_or_more=q[4],
                    hits_7_or_more=q[5],hits_8_or_more=q[6],
                    hits_9_or_more=q[7],hits_10_or_more=q[8]))
    bootstrap=[]
    hold_days=sorted(set(k[0] for k in per_day))
    if hold_days:
        for compare in ("HOT672","HOT1344","HOT2016","RANDOM10"):
            daily=np.array([np.mean(per_day[(d,"HOT2688")])
                    -np.mean(per_day[(d,compare)]) for d in hold_days])
            rng=np.random.default_rng(RSEED+len(compare))
            means=daily[rng.integers(0,len(daily),(4000,len(daily)))].mean(axis=1)
            bootstrap.append(dict(a="HOT2688",b=compare,phase="LAST18",
               n_days=len(daily),mean_difference=round(float(daily.mean()),6),
               lo95=round(float(np.quantile(means,.025)),6),
               hi95=round(float(np.quantile(means,.975)),6)))
    texts=[
      "V125 — 672 x 4 = 2688 Cekilis / 224 Ic Ice 12 lik Cember",
      f"Verified {n} real 20/80 source results up to id #{rows[-1]['id']} {rows[-1]['day']}.",
      "Concentric nested windows last12,24,...,2688: exactly 224 rings.",
      "Every added one draw shifts all 224 windows by exactly one observation;",
      "the oldest corresponding observation of each ring leaves.",
      f"The counts BELOW include final observed draw #{rows[-1]['id']}.",
      "POOL memberships 16+16+16+16+16 at every window; tie number ascending.",
      ""]
    for x in summaries:
        texts.append(
          f"w={x['last_window_draws']} expected_per_number={x['expected_per_number']:.0f} "
          f"maximum={x['actual_max']} number={x['actual_max_numbers']} "
          f"minimum={x['actual_min']} number={x['actual_min_numbers']} "
          f"GAP={x['extreme_gap']}, proportional_gap={x['gap_divided_by_expected_avg']:.4f}"
        )
    texts.append("")
    for x in overlap_rows:
        texts.append(f"{x['compare']}: same_temp={x['same_pool_members']}/80, "
                     f"changed_temp={x['change_pool_members']}, "
                     f"hot_overlap={x['hot_top16_overlap']}/16, "
                     f"cold_overlap={x['cold_bottom16_overlap']}/16")
    texts.extend(["","No families used. The next draw is not present in scoring inputs.",
      f"Single-draw target checks with 2688 previous draws: {sum(draws.values())}.",
      f"By phase: {dict(draws)}.",
      "Comparison: one equal-size HOT672/HOT1344/HOT2016/HOT2688/COLD2688/RANDOM",
      "per target, each tested k=3,4,5,6,8,10,20.",
      "Both HOT and COLD are based on occurrences, not proven RNG predictability.",
      "LAST18 is prior-studied historical data, not independent unseen blind holdout.",
      ""])
    for k in (3,4,5,6,8,10,20):
        texts.append(f"LAST18 k={k}:")
        for model in MODELS:
            q=results[("LAST18",model,k)]
            if not q[0]:continue
            texts.append(
                f" {model}: avg={q[1]/q[0]:.5f}, perfect={q[2]}, "
                f"5+={q[3]},6+={q[4]},8+={q[6]},10+={q[8]}")
    for z in bootstrap:
        texts.append(f"LAST18 paired HOT2688 vs {z['b']} "
                f"diff={z['mean_difference']:+.5f} 95% "
                f"[{z['lo95']:+.5f},{z['hi95']:+.5f}]")
    texts.extend(["","Interpretation: 2688/224 rings can describe past frequency",
       "but extrapolating extrema or increasing history is not evidence",
       "of a statistically improved prediction of independent random targets."])
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_V125_KISA_RAPOR.txt","\n".join(texts)+"\n")
        savecsv(z,"01_80_SAYI_672_1344_2016_2688_224_HALKA_2688_1_0.csv",n80)
        savecsv(z,"02_672_1344_2016_2688_SICAK_SOGUK_REFERANS.csv",summaries)
        savecsv(z,"03_56_112_168_224_HALKA_HAVUZ_DONUSUMLERI.csv",overlap_rows)
        savecsv(z,"04_HER_HEDEF_672_1344_2016_2688_RASTGELE_ESIT_KUPON.csv",per_draw)
        savecsv(z,"05_BOYUT_DONEM_3_4_5_6_8_10_20_SONUC.csv",score)
        savecsv(z,"06_SON18_GUN_GUVEN_ARALIKLARI.csv",bootstrap)
        z.writestr("07_METOD_KONTROL.json",json.dumps(dict(
            source_draws=n,latest_id=rows[-1]["id"],
            nested_lengths=LENS.tolist(),
            sum2688=int(end_counts[2688].sum()),
            actual_2688_extreme_gap=summaries[-1]["extreme_gap"],
            pool_members_per_class=16,
            historical_next_draw_test_n=n-2688,
            phase_draws=dict(draws),
            candidates=list(MODELS),sizes=list(TICKET_SIZES),
            new_2688_history_not_future_prediction=True,
            historical_data_studied_in_prior_experiments=True,
            all_numerical_draws_real=True),ensure_ascii=False,indent=2))
    print("\n".join(texts),flush=True)
    print("V125 COMPLETE",out,out.stat().st_size,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v125_output/V125_2688_224_HALKA_672_1344_2016_KARSILASTIRMA.zip")
    a=p.parse_args()
    main(a.source,a.out)
