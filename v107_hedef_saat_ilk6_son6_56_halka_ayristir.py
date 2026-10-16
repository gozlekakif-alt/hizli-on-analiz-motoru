#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V107: Separate first 6 observed draws from 56 ring trajectory for H7-H12.

Question: With SAME H1-H6 ball frequency k, last72 temperature, and net
last6 full-ring direction, can the OLDER 49/50 rings improve understanding
of how often a ball appears in remaining six draws and reaches >=5/6/7/8
drawn appearances in the complete 12-draw target hour?

All hour-start ring descriptors are frozen BEFORE target H1. H1-H6
counts only become available before H7. Outcomes H7-H12 are never used
to construct features. Original 672 FIFO ring IDs/56-ring temperature
history preserved (V104), no nested V100B histories.

First 36 fully recorded days fit fixed-smoothed 7-category last6-count
tables; next 36 days and newer available complete hours evaluated as
separate descriptive forward partitions. No tickets or user bankroll use.
"""
from __future__ import annotations
import argparse,collections,csv,io,json,math,zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load,temperature
from v104_72gun_basindan_672_56_halka_fifo_yon import stable_paths
from v102_80sayi_56_halka_yon_zinciri_hedef_saat import expected_hours

V="V107.1"
TEMP=("SOGUK","SERIN","NOTR","ILIK","SICAK")
CHAIN=("SOGUYOR","DENGELI","ISINIYOR")
GROUP=("AZ","ORTA","COK")
THRESHOLDS=(5,6,7,8)
STEPS={-1:"D",0:"=",1:"Y"}
BINOM=np.asarray([math.comb(6,k)*(.25**k)*(.75**(6-k))
                  for k in range(7)],dtype=np.float64)
assert abs(BINOM.sum()-1)<1e-12

def bin3(n,low,high):
    return 0 if n<low else 1 if n<high else 2

def direction_age(d):
    """Ages since most recent nonzero pool move, chronological steps."""
    last=np.zeros(80,dtype=int)
    for j in range(80):
        positions=np.flatnonzero(d[j]!=0)
        last[j]=d.shape[1]-1-int(positions[-1]) if len(positions) else d.shape[1]
    return last

def info(S,D):
    now=S[:,-1].astype(np.int8)
    net6=(now-S[:,-7]).astype(np.int8)
    sign=np.sign(net6).astype(np.int8)+1
    old=S[:,:-7]
    cold=(old==0).sum(axis=1).astype(np.int16)
    hot=(old==4).sum(axis=1).astype(np.int16)
    moves=(np.diff(old,axis=1)!=0).sum(axis=1).astype(np.int16)
    age=direction_age(D)
    coldcat=np.asarray([bin3(int(x),6,12) for x in cold],dtype=np.int8)
    movecat=np.asarray([bin3(int(x),20,27) for x in moves],dtype=np.int8)
    agecat=np.asarray([bin3(int(x),2,4) for x in age],dtype=np.int8)
    assert now.shape==sign.shape==coldcat.shape==movecat.shape==agecat.shape==(80,)
    return dict(now=now,net6=net6,sign=sign,cold=cold,hot=hot,
        moves=moves,age=age,coldcat=coldcat,movecat=movecat,agecat=agecat)

def phase(day,days):
    if day>"2026-10-12":return "NEW_DATA"
    return "FIRST36" if days.index(day)<36 else "LAST36"

def tabulate(train):
    """Seven-category counts: later-six appearances 0/1/.../6."""
    base=np.zeros((7,7),np.float64)
    short=np.zeros((7,5,3,7),np.float64)
    cold=np.zeros((7,5,3,3,7),np.float64)
    age=np.zeros_like(cold)
    volume=np.zeros_like(cold)
    for k,p,s,c,a,v,l in train:
        base[k,l]+=1
        short[k,p,s,l]+=1
        cold[k,p,s,c,l]+=1
        age[k,p,s,a,l]+=1
        volume[k,p,s,v,l]+=1
    prior=(base+180*BINOM)/(base.sum(axis=-1,keepdims=True)+180)
    ps=(short+90*prior[:,None,None,:])/(short.sum(axis=-1,keepdims=True)+90)
    def cond(mat):
        return (mat+80*ps[:,:,:,None,:])/(mat.sum(axis=-1,keepdims=True)+80)
    return dict(BASE=prior,SHORT=ps,OLD_COLD=cond(cold),
                LAST_CHANGE_AGE=cond(age),OLD_MOTION=cond(volume)),dict(
                base=base,short=short,cold=cold,age=age,volume=volume)

def pred(tables,k,p,s,c,a,v):
    return dict(
        BINOM6=BINOM,
        FIRST6_ONLY=tables["BASE"][k],
        FIRST6_LASTPOOL_LAST6=tables["SHORT"][k,p,s],
        PLUS_OLDER_COLD=tables["OLD_COLD"][k,p,s,c],
        PLUS_LAST_CHANGE=tables["LAST_CHANGE_AGE"][k,p,s,a],
        PLUS_OLDER_MOTION=tables["OLD_MOTION"][k,p,s,v]
    )

def thresholds(pvec,k):
    """Probability total H1-H6 + H7-H12 reaches 5,6,7,8."""
    return {h:float(pvec[max(0,h-k):].sum()) if h-k<=6 else 0.
            for h in THRESHOLDS}

def multiclass_brier(pvec,label):
    v=np.array(pvec,copy=True)
    v[label]-=1
    return float(np.dot(v,v))

def csvw(z,name,values):
    if not values:return
    with z.open(name,"w",force_zip64=True) as r:
        fh=io.TextIOWrapper(r,encoding="utf-8",newline="")
        w=csv.DictWriter(fh,fieldnames=list(values[0]))
        w.writeheader();w.writerows(values)
        fh.flush();fh.detach()

def run(source,out):
    days,rows,X,issues,bad=load(source)
    n=len(rows)
    cum=np.vstack((np.zeros((1,80),np.int32),
                  np.cumsum(X,axis=0,dtype=np.int32)))
    seal=np.empty((n//12,80),dtype=np.int8)
    for r in range(n//12):
        e=(r+1)*12
        seal[r]=temperature(cum[e]-cum[max(0,e-72)])
    hrs,rejected=expected_hours(rows)
    hours=[(t,day,hr,ids) for t,day,hr,ids in hrs if t+12<=n]
    if not hours:raise RuntimeError("No verified complete 12-draw hours")
    datasets=[]
    samples=[]
    all_hour=[];example=[]
    for hi,(t,day,h,ids) in enumerate(hours):
        rings,S,D=stable_paths(t,seal)
        f=info(S,D)
        A=X[t:t+12]
        first=A[:6].sum(axis=0).astype(int)
        late=A[6:].sum(axis=0).astype(int)
        hour=f"{day} {h:02d}:02-{h:02d}:57"
        perhour=dict(period=phase(day,days),day=day,hour=hour,
            H1_id=ids[0],H12_id=ids[-1],
            previous672_first_id=rows[t-672]["id"],
            previous672_last_id=rows[t-1]["id"],full_rings=len(rings))
        for k in (2,3,4,5):
            for threshold in THRESHOLDS:
                perhour[f"warming_first6_{k}_total{threshold}plus"]=0
        for ball in range(80):
            k=int(first[ball]);late6=int(late[ball]);total=k+late6
            p=int(f["now"][ball]);s=int(f["sign"][ball])
            c=int(f["coldcat"][ball]);a=int(f["agecat"][ball])
            v=int(f["movecat"][ball])
            datasets.append((phase(day,days),day,hour,
                    ball+1,k,p,s,c,a,v,late6,total))
            samples.append((k,p,s,c,a,v,late6))
            bits="".join(str(int(A[j,ball])) for j in range(12))
            sample=dict(
                period=phase(day,days),day=day,hour=hour,ball=ball+1,
                prior672_first_id=rows[t-672]["id"],
                prior672_last_id=rows[t-1]["id"],
                first6_hits=k,last6_hits=late6,total12_hits=total,
                full_ring_count=len(rings),last_pool=TEMP[p],
                last6_direction=CHAIN[s],last6_pool_delta=int(f["net6"][ball]),
                old49_cold_rings=int(f["cold"][ball]),
                old49_hot_rings=int(f["hot"][ball]),
                old49_pool_moves=int(f["moves"][ball]),
                steps_since_last_pool_change=int(f["age"][ball]),
                old_cold_class=GROUP[c],
                old_movement_class=GROUP[v],
                last_change_age_class=GROUP[a],
                full_temperature_path="".join("CSNIH"[int(x)] for x in S[ball]),
                full_direction_path="".join(STEPS[int(x)] for x in D[ball]),
                target_H1_H12_bits=bits,
                target_first6_hands="-".join(str(j+1) for j in range(6) if A[j,ball]),
                target_last6_hands="-".join(str(j+7) for j in range(6) if A[j+6,ball]),
                reached5=int(total>=5),reached6=int(total>=6),
                reached7=int(total>=7),reached8=int(total>=8))
            if s==2 and k in (2,3,4,5):
                for thr in THRESHOLDS:
                    perhour[f"warming_first6_{k}_total{thr}plus"]+=int(total>=thr)
            # Keep compact 0..12 ledger; all profiles in separate CSV
            example.append(sample)
        all_hour.append(perhour)
        if hi%260==0:print("V107 analyzed",hi,"/",len(hours),flush=True)
    training=[arr for dat,arr in zip(datasets,samples) if dat[0]=="FIRST36"]
    tables,raw=tabulate(training)
    scoring=collections.defaultdict(lambda:[0.,0.,0.,0.,0.])
    # Scores: n, multiclass brier, >=5, >=6, >=7/8 binary brier.
    details=[]
    results=collections.defaultdict(lambda:[0]*12) # counts for each 0..6 later appearance, n, four thresholds
    last36strat=collections.defaultdict(lambda:[0]*8) # n, reached5..8, late6total, ktotal, etc
    for record in datasets:
        ph,day,hour,ball,k,p,s,c,a,v,l,total=record
        # First-six k held fixed; only AFTER this do we use older chain.
        chain_style=("OLD_COLD",c)  # read other features in CSV
        if ph!="FIRST36":
            prob=pred(tables,k,p,s,c,a,v)
            for model,q in prob.items():
                q=np.asarray(q,dtype=float)
                z=scoring[(ph,model,s)]
                z[0]+=1
                z[1]+=multiclass_brier(q,l)
                for idx,thr in enumerate(THRESHOLDS,2):
                    pr=thresholds(q,k)[thr]
                    y=int(total>=thr)
                    if idx<=4:z[idx]+=(pr-y)**2
                    else:z[4]+=(pr-y)**2 # 7 and 8 combined for display
        if ph not in ("FIRST36","LAST36","NEW_DATA"):
            raise RuntimeError("Bad partition")
        if s==2:
            base=(ph,k,p,s)
            variant=(ph,k,p,s,c)
            for typ,key in [("SHORT",base),("OLD_COLD",variant),
                            ("RECENCY",(ph,k,p,s,a)),
                            ("OLD_MOTION",(ph,k,p,s,v))]:
                item=results[(typ,)+key]
                item[0]+=1
                item[1+l]+=1
                item[8]+=int(total>=5)
                item[9]+=int(total>=6)
                item[10]+=int(total>=7)
                item[11]+=int(total>=8)
                if ph=="LAST36":
                    x=last36strat[(typ,k,key[-1])]
                    x[0]+=1
                    x[1]+=int(total>=5);x[2]+=int(total>=6)
                    x[3]+=int(total>=7);x[4]+=int(total>=8)
                    x[5]+=l;x[6]+=k;x[7]+=total
    score_rows=[]
    for (ph,model,direction),b in sorted(scoring.items()):
        if b[0]==0:continue
        score_rows.append(dict(period=ph,method=model,dir=CHAIN[direction],
            number_hour_samples=int(b[0]),
            count_H7_H12_multiclass_brier=b[1]/b[0],
            total5plus_event_brier=b[2]/b[0],
            total6plus_event_brier=b[3]/b[0],
            total7plus_event_brier=b[4]/b[0]))
    historical=[]
    for (typ,*key),r in sorted(results.items(),key=lambda x:str(x[0])):
        n=r[0]
        if not n:continue
        historical.append(dict(feature=typ,key="|".join(map(str,key)),
            n=n,
            next6_0=r[1],next6_1=r[2],next6_2=r[3],
            next6_3=r[4],next6_4=r[5],next6_5=r[6],
            next6_6=r[7],total5plus=r[8],total6plus=r[9],
            total7plus=r[10],total8plus=r[11],
            total5plus_pct=100*r[8]/n,total6plus_pct=100*r[9]/n,
            total7plus_pct=100*r[10]/n,total8plus_pct=100*r[11]/n,
            avg_later_six=sum(j*r[j+1] for j in range(7))/n))
    held=[]
    for (typ,k,g),b in sorted(last36strat.items()):
        if b[0]==0:continue
        held.append(dict(model=typ,first6_hits=k,subclass=g,
           last36_samples=int(b[0]),
           total5plus_pct=100*b[1]/b[0],
           total6plus_pct=100*b[2]/b[0],
           total7plus_pct=100*b[3]/b[0],
           total8plus_pct=100*b[4]/b[0],
           mean_H7_to_H12=b[5]/b[0]))
    # Prepare readable cohort: warm only, fixed first6 count,
    # old-cold >=12 vs <6, across separate eras. Combine all last pools
    # here, but an additional detail CSV fixes last pool per row.
    contrast=collections.defaultdict(lambda:[0,0,0,0,0,0])
    for rec in datasets:
        ph,day,hour,ball,k,p,s,c,a,v,l,total=rec
        if s!=2 or k not in (2,3,4,5):continue
        co=contrast[(ph,k,c)]
        co[0]+=1
        for idx,thr in enumerate(THRESHOLDS,1):
            co[idx]+=int(total>=thr)
        co[5]+=l
    contrast_rows=[]
    for (ph,k,c),co in sorted(contrast.items()):
        n0=co[0]
        contrast_rows.append(dict(phase=ph,first6_exact=k,
            older_rings_cold_group=GROUP[c],n=n0,
            later6_mean=co[5]/n0,
            total5plus_pct=100*co[1]/n0,total6plus_pct=100*co[2]/n0,
            total7plus_pct=100*co[3]/n0,total8plus_pct=100*co[4]/n0))
    latest=all_hour[-1]
    current=[x for x in example if x["hour"]==latest["hour"] and
             x["last6_direction"]=="ISINIYOR" and x["first6_hits"]>=2]
    current.sort(key=lambda r:(-r["total12_hits"],r["ball"]))
    # theoretical conditional 6-draw need, independent of any history
    math_rows=[]
    for k in range(7):
        for thr in THRESHOLDS:
            remaining=max(0,thr-k)
            baseline=(sum(math.comb(6,r)*(.25**r)*(.75**(6-r))
                       for r in range(remaining,7)) if remaining<=6 else 0.)
            math_rows.append(dict(first6_observed=k,
                target_hour_total_at_least=thr,
                last6_required=remaining,
                baseline_conditional_pct=100*baseline))
    # Summary and explicit split; not a claim of prospective edge.
    latest_mean={}
    for ph in ("LAST36","NEW_DATA"):
        latest_mean[ph]=[r for r in score_rows if r["period"]==ph and
                        r["dir"]=="ISINIYOR"]
    first_n=sum(1 for r in datasets if r[0]=="FIRST36")
    last_n=sum(1 for r in datasets if r[0]=="LAST36")
    report=[
        "V107 | ILK 6 ETKISI vs 56 HALKA YON GECMISI NASIL AYRILIR?",
        "Mechanism: stable 672 memory, 55/56 sealed 12-draw rings,",
        "original fixed absolute IDs, and each target hour known only AFTER.",
        f"Complete 12-draw hours={len(hours)}, first36 records={first_n}, last36 records={last_n}.",
        "BEFORE H1: older49/50 cold/hot dwell, moves and last change age",
        "plus current pool and previous 6-ring warming direction are FROZEN.",
        "AFTER H6: count k of this ball across H1..H6 becomes KNOWN.",
        "BEFORE H7: compare ONLY balls with same k, last pool and last6 sign.",
        "AFTER H12: count next6 and total12; classify >=5/6/7/8.",
        "5+ can already be reached in first6. Avoid treating this as a",
        "win credited to 56 rings when it came from the first6 count.",
        "",
        "MATCHED DIRECTION (ISINIYOR) LAST36: multiclass Brier for",
        "H7-H12 count 0-6 (lower is better):"]
    lookup={x["method"]:x for x in latest_mean.get("LAST36",[])}
    for method in ("BINOM6","FIRST6_ONLY","FIRST6_LASTPOOL_LAST6",
                   "PLUS_OLDER_COLD","PLUS_LAST_CHANGE","PLUS_OLDER_MOTION"):
        row=lookup.get(method)
        if row:report.append(f" {method:24s} brier={row['count_H7_H12_multiclass_brier']:.7f}"
            f"  at-least5-event-brier={row['total5plus_event_brier']:.7f}")
    report+=["","HISTORICAL warming conditional group: first6 k=2,3,4,5.",
      "Older cold rings binned: AZ <6, ORTA 6..11, COK >=12.",
      "Compare each bin with same k and same last pool in detail CSV.",
      "The following table is aggregated across 5 latest pools; inspect",
      "pool-matched CSV before asserting a relationship."]
    for r in contrast_rows:
        if r["phase"]=="LAST36" and r["first6_exact"] in (2,3,4):
            report.append(f" first6={r['first6_exact']} older_cold={r['older_rings_cold_group']:4s}"
                f" n={r['n']:4d} next6mean={r['later6_mean']:.3f}"
                f" 5+%={r['total5plus_pct']:.2f}, 6+%={r['total6plus_pct']:.2f},"
                f" 7+%={r['total7plus_pct']:.2f}, 8+%={r['total8plus_pct']:.2f}")
    report+=["",
       f"LAST COMPLETED HOUR: {latest['hour']}, #{latest['H1_id']}...#{latest['H12_id']}",
       "Warming numbers with 2+ appearances among first6 and the next6:"]
    for r in current:
        report.append(f" ball={r['ball']:2d} H1..6={r['first6_hits']} "
          f"H7..12={r['last6_hits']} total={r['total12_hits']}"
          f" pool={r['last_pool']} oldcold={r['old49_cold_rings']}"
          f" changeAge={r['steps_since_last_pool_change']}"
          f" full56={r['full_temperature_path']}")
    report+=["","RESULT: keeping H1..H6 k fixed removes most mechanical",
      "5-8 repeats. Only matched improvements beyond base in LATER6",
      "could indicate added descriptive value from the long chain.",
      "Any difference must recur across date-split periods before being",
      "considered reliable. No 20-number ticket generation."]
    meta=dict(version=V,source_draws=n,last_draw_id=rows[-1]["id"],
        hours=len(hours),number_hour_rows=len(datasets),incomplete_hours=rejected,
        train_first36_only=True,compare_first6_count_controlled=True,
        use_full56_pre_hour_features=True,
        oldcold_source="all 49/50 sealed rings except latest seven",
        bootstrap_not_performed=True,
        smoothing="binomial6 prior 180, short 90, full56 80",
        later6_labels_never_read_before_feature_construction=True,
        old_72_dates_reused_earlier=True,
        not_predictive_claim=True,source_issues=issues[:20],bad_lines=bad[:20])
    dst=Path(out);dst.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dst,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_56_HALKA_ILK6_SON6_AYIRMA_RAPORU.txt","\n".join(report)+"\n")
        csvw(z,"01_TUM_HEDEF_SAAT_80_SAYI_TAM56_YON_ILK6_SON6.csv",example)
        csvw(z,"02_ISINAN_5_6_7_8_ILK6_ESIT_SON6_TABLO.csv",historical)
        csvw(z,"03_ILK6_2_3_4_5_ESIT_ESKI_SOGUK_HALKALAR.csv",contrast_rows)
        csvw(z,"04_SON36_DONEMINDE_EK_ZINCIR_BILGISI.csv",score_rows)
        csvw(z,"05_SON36_ILK6_HAVUZ_ZINCIR_KOSULLU_OLASILIK.csv",held)
        csvw(z,"06_HER_SAAT_3_4_5_BASLANGIC_SON6_OLAYLAR.csv",all_hour)
        csvw(z,"07_ILK6_DURUMUNA_GORE_GEREKLI_EK_SAYI.csv",math_rows)
        z.writestr("08_KESIN_METOT_ZAMAN_KONTROL.json",json.dumps(meta,indent=2,ensure_ascii=False,default=str))
    print("\n".join(report),flush=True)
    print("V107 FINISHED",dst,dst.stat().st_size,flush=True)

def selftest():
    assert abs(BINOM.sum()-1)<1e-12
    S=np.tile(np.arange(5,dtype=np.int8).repeat(16),(56,1)).T
    D=np.zeros((80,55),dtype=np.int8)
    f=info(S,D)
    assert np.all(f["age"]==55)
    assert all(f[x].shape==(80,) for x in ("coldcat","movecat","agecat"))
    rows=[(3,2,2,1,0,0,2),(3,2,2,1,0,0,3)]
    tables,raw=tabulate(rows)
    ps=pred(tables,3,2,2,1,0,0)
    assert all(abs(np.sum(p)-1)<1e-9 for p in ps.values())
    assert abs(thresholds(BINOM,4)[5]-(1-(.75**6)))<1e-10
    print("V107 SELFTEST OK",flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",default="veri.txt")
    ap.add_argument("--out",default="v107_output/V107_ILK6_ETKISI_TAM56_HALKA_YON_AYRISTIRMA.zip")
    ap.add_argument("--selftest",action="store_true")
    a=ap.parse_args()
    if a.selftest:selftest()
    else:run(a.source,a.out)
