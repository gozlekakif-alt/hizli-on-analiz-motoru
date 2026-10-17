#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V132: Next 20 inclusion chance of JUST-entered HOT vs ESTABLISHED HOT.

All 224 nested rolling 20/80 draw windows (12,24,...,2688). For each
COMPLETED observed draw t, pool membership is computed using ONLY draws
through t. 80 counts sorted asc, ties smaller ball first, exactly 16
numbers in each of five pools. New hot = pool[t-1]!=4 & pool[t]==4;
stayer hot = pool[t-1]==4 & pool[t]==4; cooling/exiting hot is separate.
The next actual result X[t+1] is READ AFTER candidates are frozen.

Equal-budget coupons: one 10-number selection per model per target:
newly_hot_priority, established_hot_priority, top_hot_frequency,
bottom_hot_boundary, uniformly random within hot16, random80.
Each 10-ticket candidate is chosen from same 16 HOT (except random80).
Note new-hot numbers can be scarce, so all policies fill with other
HOT members to reach a fair total of 10.

Fine-grained counts all 224 rings, six anchors 12,72,672,1344,2016,
2688 and four ring bands, each candidate's next hit conditional
frequency. Day-block bootstrap CI for new vs established, including
explicit "only days with new entrants" and exact N denominator.
Unseen future is NOT in source; last18 dates were used in past studies.
"""
from __future__ import annotations
import argparse,collections,csv,io,json,zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load

LENS=np.arange(12,2689,12,dtype=np.int32)
NR=224
NB=80
SEED=1322026
ANCHOR=(0,5,55,111,167,223)
ANCHOR_NAMES=("12","72","672","1344","2016","2688")
BAND=((0,56),(56,112),(112,168),(168,224))
STATUSES=("NEW_HOT","ESTABLISHED_HOT","EXIT_HOT","OTHER")
METHODS=("NEW_FIRST","ESTABLISHED_FIRST","HOT_TOP_RANK",
    "HOT_LOW_BOUNDARY","RANDOM_IN_HOT16","RANDOM_ANY80")
K=10
assert len(LENS)==NR and len(STATUSES)==4

def cls_counts(cnt):
    ix=np.argsort(cnt,axis=1,kind="stable")
    rank=np.empty((NR,NB),dtype=np.uint8)
    rank[np.arange(NR)[:,None],ix]=np.arange(NB,dtype=np.uint8)
    cl=rank//16
    assert np.all(np.bincount(cl.ravel(),minlength=5)==NR*16)
    return rank,cl

def encode_row(phase,label,status,N,H,D=0):
    return dict(phase=phase,ring_group=label,status=status,exposure=int(N),
      target20_members=int(H),rate_pct=round(100*H/N,6) if N else "",
      fair_baseline_rate_pct=25,
      number_of_ring_time_episodes=int(D))

def csv_out(z,path,rows):
    if not rows:return
    s=io.StringIO(newline="")
    w=csv.DictWriter(s,fieldnames=list(rows[0]))
    w.writeheader();w.writerows(rows)
    z.writestr(path,s.getvalue().encode("utf-8-sig"))

def select_hot10(rank,old_pool,new_pool,target_id,anchor_i):
    # Four hot-only selections of exactly 10; no future target bits used.
    hot=np.flatnonzero(new_pool==4)
    assert len(hot)==16
    newhot=hot[old_pool[hot]!=4]
    stay=hot[old_pool[hot]==4]
    assert len(newhot)+len(stay)==16
    rank_sorted=lambda idx:np.array(sorted(map(int,idx),
      key=lambda b:(-int(rank[b]),int(b))),dtype=int)
    firstnew=np.concatenate((rank_sorted(newhot),rank_sorted(stay)))[:K]
    firststay=np.concatenate((rank_sorted(stay),rank_sorted(newhot)))[:K]
    top=np.array(sorted(map(int,hot),
                    key=lambda b:(-int(rank[b]),int(b))),dtype=int)[:K]
    low=np.array(sorted(map(int,hot),
                    key=lambda b:(int(rank[b]),int(b))),dtype=int)[:K]
    rng=np.random.default_rng(SEED+int(target_id)*4999+anchor_i*173)
    randomhot=rng.permutation(hot)[:K]
    random80=np.random.default_rng(
          SEED+int(target_id)*4093+anchor_i*2399).permutation(NB)[:K]
    picks=dict(zip(METHODS,(firstnew,firststay,top,low,randomhot,random80)))
    assert all(len(x)==K and len(set(map(int,x)))==K for x in picks.values())
    assert all((new_pool[x]==4).all() for k,x in picks.items()
                if k!="RANDOM_ANY80")
    return picks,len(newhot),len(stay)

def paired_day_bootstrap(rows):
    # Rows list (new exposures, new hits, stable exposures, stable hits).
    # Resample full CALENDAR DAYS, not millions of overlapping ring states.
    vals=np.asarray(rows,dtype=float)
    total=vals.sum(axis=0)
    if total[0]<=0 or total[2]<=0:return None
    rate=(total[1]/total[0]-total[3]/total[2])*100
    rng=np.random.default_rng(SEED+int(total[0])%10000)
    bins=vals[rng.integers(0,len(vals),size=(3000,len(vals)))].sum(axis=1)
    good=bins[(bins[:,0]>0)&(bins[:,2]>0)]
    effect=(good[:,1]/good[:,0]-good[:,3]/good[:,2])*100
    return (float(rate),float(np.quantile(effect,.025)),
            float(np.quantile(effect,.975)))

def main(source,out):
    days,rows,X,issues,bad=load(source)
    n=len(rows)
    assert len(X)==n and n>2690 and np.all(X.sum(axis=1)==20)
    training_dates=sorted(d for d in days if d<="2026-10-12")
    assert len(training_dates)==72
    period={d:("TRAIN36" if i<36 else "VALIDATE18" if i<54 else "LAST18")
           for i,d in enumerate(training_dates)}
    pref=np.vstack((np.zeros((1,NB),dtype=np.int32),
                    np.cumsum(X,axis=0,dtype=np.int32)))
    cnt=pref[2688][None,:]-pref[2688-LENS]
    oldrank,oldcls=cls_counts(cnt)
    # Exact ring×status conditional success counts
    byring=collections.defaultdict(lambda:np.zeros(4,dtype=np.int64))
    byband=collections.defaultdict(lambda:np.zeros(4,dtype=np.int64))
    dayanchor=collections.defaultdict(lambda:np.zeros(4,dtype=np.int64))
    dayall=collections.defaultdict(lambda:np.zeros(4,dtype=np.int64))
    total_all=collections.defaultdict(lambda:np.zeros(4,dtype=np.int64))
    # Conditional rates for entry tenure in hot: rank offset 0..15 within hot.
    depth=collections.defaultdict(lambda:np.zeros(2,dtype=np.int64))
    score=collections.defaultdict(lambda:np.zeros(5,dtype=np.int64))
    scoreday=collections.defaultdict(lambda:np.zeros(2,dtype=np.int64))
    audits=[]
    targetcounts=collections.Counter()
    firstlast=[]
    n_target=n-2689
    for t in range(2688,n-1):
        x=X[t].astype(np.int16)
        leaving=X[t-LENS].astype(np.int16)
        newcount=cnt+x[None,:]-leaving
        rank,pool=cls_counts(newcount)
        newhot=(oldcls!=4)&(pool==4)
        stayer=(oldcls==4)&(pool==4)
        exithot=(oldcls==4)&(pool!=4)
        other=(oldcls!=4)&(pool!=4)
        assert np.all((newhot|stayer).sum(axis=1)==16)
        assert np.all((newhot|stayer|exithot|other).sum(axis=1)==80)
        tt=t+1
        actual=X[tt].astype(np.int16)
        phase=period.get(rows[tt]["day"],"EXTRA_OCT13")
        day=rows[tt]["day"]
        targetcounts[phase]+=1
        parts=(newhot,stayer,exithot,other)
        for s,mask in enumerate(parts):
            hits=(mask*actual[None,:]).sum(axis=1).astype(np.int64)
            length=mask.sum(axis=1).astype(np.int64)
            for r in range(NR):
                a=byring[(phase,r,s)]
                a[0]+=int(length[r]);a[1]+=int(hits[r])
                a[2]+=1;a[3]+=int(length[r]>0)
            for j,(start,end) in enumerate(BAND):
                bb=byband[(phase,j,s)]
                bb[0]+=int(length[start:end].sum())
                bb[1]+=int(hits[start:end].sum())
                bb[2]+=1;bb[3]+=int((length[start:end]>0).any())
        for r in ANCHOR:
            nex=int(newhot[r].sum())
            stb=int(stayer[r].sum())
            assert nex+stb==16
            new_h=int(actual[newhot[r]].sum())
            stb_h=int(actual[stayer[r]].sum())
            a=dayanchor[(phase,day,r)]
            a+=(nex,new_h,stb,stb_h)
            aa=total_all[(phase,r)]
            aa+=(nex,new_h,stb,stb_h)
            for k in range(16):
                hot_n=np.flatnonzero((pool[r]==4)&(rank[r]==64+k))
                assert len(hot_n)==1
                b=int(hot_n[0])
                tag="NEW" if oldcls[r,b]!=4 else "STABLE"
                dd=depth[(phase,r,k,tag)]
                dd+=(1,int(actual[b]))
            picks,numnew,numstay=select_hot10(rank[r],oldcls[r],
                                               pool[r],rows[tt]["id"],r)
            for method in METHODS:
                numbers=picks[method]
                h=int(actual[numbers].sum())
                ss=score[(phase,r,method)]
                ss+=(1,h,int(h>=5),int(h>=6),int(h==10))
                scoreday[(day,r,method)]+=(1,h)
                if phase=="LAST18" and r in (0,5,55,223):
                    audits.append(dict(
                       date=day,known_draw_id=rows[t]["id"],
                       target_draw_id=rows[tt]["id"],window_draws=int(LENS[r]),
                       method=method,new_hot_pool_count=numnew,
                       stayer_hot_pool_count=numstay,
                       picked10=" ".join(str(int(q)+1) for q in numbers),
                       hit10=h,target20=" ".join(str(i+1)
                                         for i in np.flatnonzero(actual))))
        if t==n-2:
            for r in ANCHOR:
                firstlast.append(dict(lookback=int(LENS[r]),
                  last_known_draw_id=rows[t]["id"],observed_target_id=rows[tt]["id"],
                  newly_entered_hot_16=" ".join(str(i+1)
                         for i in np.flatnonzero(newhot[r])),
                  established_hot_16=" ".join(str(i+1)
                         for i in np.flatnonzero(stayer[r])),
                  target20_next=" ".join(str(i+1)
                         for i in np.flatnonzero(actual)),
                  is_historical_not_future=True))
        cnt=newcount;oldrank=rank;oldcls=pool
        if (t-2687)%2500==0:
            print("V132 target",t-2687,"/",n_target,
                  "last known",rows[t]["id"],"next",rows[tt]["id"],flush=True)
    ring_rows=[]
    for phase in ("TRAIN36","VALIDATE18","LAST18","EXTRA_OCT13"):
        for r in range(NR):
            for s,st in enumerate(STATUSES):
                q=byring.get((phase,r,s))
                if q is None or q[0]==0:continue
                ring_rows.append(dict(
                   phase=phase,ring=r+1,lookback=int(LENS[r]),
                   pool_status=st,number_target_pairs=int(q[0]),
                   next_target_hits=int(q[1]),
                   next_hit_pct=round(100*q[1]/q[0],6),
                   steps=int(q[2]),steps_with_members=int(q[3]),
                   expected_hit_pct=25))
    band_rows=[]
    for phase in ("TRAIN36","VALIDATE18","LAST18","EXTRA_OCT13"):
        for j,(a,b) in enumerate(BAND):
            for s,st in enumerate(STATUSES):
                q=byband.get((phase,j,s))
                if q is None or q[0]==0:continue
                band_rows.append(dict(phase=phase,band=j+1,
                   from_lookback=int(LENS[a]),
                   to_lookback=int(LENS[b-1]),pool_status=st,
                   number_target_pairs=int(q[0]),
                   next_hits=int(q[1]),
                   next_hit_pct=round(100*q[1]/q[0],6)))
    pair_rows=[]
    for phase in ("TRAIN36","VALIDATE18","LAST18","EXTRA_OCT13"):
        for r in ANCHOR:
            q=total_all.get((phase,r))
            if q is None:continue
            a,b,c,d=(int(v) for v in q)
            pair_rows.append(dict(phase=phase,lookback=int(LENS[r]),
                newhot_N=a,newhot_next_hit=b,
                newhot_next_hit_pct=round(100*b/a,6) if a else "",
                stablehot_N=c,stablehot_next_hit=d,
                stablehot_next_hit_pct=round(100*d/c,6) if c else "",
                newcomer_minus_stable_pct_points=
                   round(100*(b/a-d/c),6) if a and c else "",
                neutral_per_number_expectation_pct=25))
    paired_ci=[]
    for phase in ("VALIDATE18","LAST18"):
        for r in ANCHOR:
            entries=[v for (ph,day,rr),v in sorted(dayanchor.items())
                    if ph==phase and rr==r]
            b=paired_day_bootstrap(entries)
            if b is not None:
                paired_ci.append(dict(phase=phase,lookback=int(LENS[r]),
                    days=len(entries),new_minus_established_pp=round(b[0],6),
                    day_bootstrap95_lower_pp=round(b[1],6),
                    day_bootstrap95_upper_pp=round(b[2],6)))
    model_rows=[]
    for phase in ("TRAIN36","VALIDATE18","LAST18","EXTRA_OCT13"):
        for r in ANCHOR:
            for m in METHODS:
                q=score.get((phase,r,m))
                if q is None or q[0]==0:continue
                model_rows.append(dict(
                    phase=phase,lookback=int(LENS[r]),model=m,targets=int(q[0]),
                    avg_hits10=round(q[1]/q[0],6),
                    hit5plus=int(q[2]),hit6plus=int(q[3]),perfect10=int(q[4]),
                    fair_random_expected_avg=2.5))
    # Choose ring and NEW-vs-STABLE priority solely on VALIDATE18 (not LAST18)
    candidates=[]
    for r in ANCHOR:
        for m in ("NEW_FIRST","ESTABLISHED_FIRST"):
            q=score[("VALIDATE18",r,m)]
            candidates.append((m,int(LENS[r]),q[1]/q[0]))
    candidates.sort(key=lambda t:(-t[2],t[1],t[0]))
    win_m,win_l,win_v=candidates[0]
    winner_r=int(win_l//12)-1
    comparison=[]
    days_last=sorted(d for d in training_dates if period[d]=="LAST18")
    for baseline in ("RANDOM_IN_HOT16","RANDOM_ANY80","HOT_TOP_RANK",
                     "NEW_FIRST","ESTABLISHED_FIRST"):
        diff=[]
        for d in days_last:
            w=scoreday[(d,winner_r,win_m)]
            v=scoreday[(d,winner_r,baseline)]
            assert w[0]==v[0] and w[0]>0
            diff.append(w[1]/w[0]-v[1]/v[0])
        dd=np.asarray(diff,dtype=np.float64)
        rng=np.random.default_rng(SEED+len(baseline))
        boot=dd[rng.integers(0,len(dd),(5000,len(dd)))].mean(axis=1)
        comparison.append(dict(winner_method=win_m,winner_reference=win_l,
            baseline=baseline,days=len(dd),last18_mean_diff=round(float(dd.mean()),6),
            block_bootstrap95_lower=round(float(np.quantile(boot,.025)),6),
            block_bootstrap95_upper=round(float(np.quantile(boot,.975)),6)))
    depthrows=[]
    for phase in ("VALIDATE18","LAST18"):
        for r in ANCHOR:
            for j in range(16):
                for st in ("NEW","STABLE"):
                    q=depth.get((phase,r,j,st))
                    if q is None or not q[0]:continue
                    depthrows.append(dict(phase=phase,lookback=int(LENS[r]),
                        hot_pool_rank_from_boundary0=j,
                        entrance_status=st,eligible=int(q[0]),
                        target_hits=int(q[1]),
                        target20_hit_pct=round(100*q[1]/q[0],6)))
    def rate(phase,l,status):
        return next(z for z in pair_rows if z["phase"]==phase and z["lookback"]==l)
    notes=[
       "V132 — NEXT DRAW 20/80: NEWLY ENTERED HOT16 vs ESTABLISHED HOT16",
       f"Source real draws {n}, max ID {rows[-1]['id']},"
                f" targets in sequential backtest {n_target}.",
       f"Targets per period {dict(targetcounts)}.",
       "Only real completed draws through t compute pool status;",
       "X[t+1] is only read after HOT new/stayer selection.",
       "All ring definitions nested, not independent replication.",
       "Within each of 224 ring classes, HOT always contains 16 numbers.",
       "NEW HOT: previous not-hot, currently hot; STABLE HOT: hot both steps.",
       "HOT member success: this number appears in the next draw's 20.",
       "Under independent 20-of-80, both groups expectation 25%.",
       "Each coupon mode always picks exactly 10 numbers, one per target.",
       "Holdout LAST18 dates previously examined in V9–V131: NOT virgin.",
       "",
       "CONDITIONAL NEXT-DRAW HIT RATES BY RING AND PERIOD:"]
    for l in (12,72,672,1344,2016,2688):
        for phase in ("VALIDATE18","LAST18"):
            q=rate(phase,l,"unused")
            notes.append(f"ring {l:<4d} {phase}: "
                f"NEW {q['newhot_next_hit_pct']}% (N={q['newhot_N']}), "
                f"ESTABLISHED {q['stablehot_next_hit_pct']}%"
                f" (N={q['stablehot_N']}), "
                f"new-minus-stable={q['newcomer_minus_stable_pct_points']} pp.")
    notes.extend(["",
       "VALIDATE18 best first/stayer preference (12 group+reference models): "
          f"{win_m} at length {win_l}, avg10={win_v:.6f}.",
       "LAST18 on locked winner vs equal-budget baselines:"])
    for m in (win_m,"NEW_FIRST","ESTABLISHED_FIRST",
              "RANDOM_IN_HOT16","RANDOM_ANY80"):
        q=score[("LAST18",winner_r,m)]
        notes.append(f" {m}: mean10={q[1]/q[0]:.6f},"
            f" 5plus={q[2]},6plus={q[3]},perfect10={q[4]},N={q[0]}")
    for r in comparison:
        notes.append(f" winner−{r['baseline']}: {r['last18_mean_diff']:+.6f},"
            f" 95% day CI [{r['block_bootstrap95_lower']:+.6f},"
            f"{r['block_bootstrap95_upper']:+.6f}]")
    notes.extend(["",
       "A big difference in historical chance of EXITING HOT pool",
       "does not automatically imply a different chance of being in",
       "the NEXT DRAW's target20. This test separates the two.",
       "Ties sorted by lower number. Class quota is 16 per group.",
       "A number can enter HOT but be near a rank cutoff and bounce.",
       "Hot-pool pool membership mechanics are descriptive, not",
       "evidence of nonrandom forward RNG forecasts.",
       "No prediction claim without new independent future draws."])
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as z:
        z.writestr("00_V132_OZET_GERCEK_SONUC.txt","\n".join(notes)+"\n")
        csv_out(z,"01_224_HALKADA_YENI_VS_YERLESIK_SICAK_NEXT20.csv",ring_rows)
        csv_out(z,"02_4X56_HALKA_BANDINA_GORE_SICAKLIK_GIRIS_NEXT20.csv",band_rows)
        csv_out(z,"03_6_REFERANS_YENI_YERLESIK_KOSULLU_NEXT20.csv",pair_rows)
        csv_out(z,"04_6_REFERANS_GUN_BOOTSTRAP_GUVEN_ARALIK.csv",paired_ci)
        csv_out(z,"05_SONRAKI_10_SAYI_ALTILI_MODEL_ESIT_KUPON.csv",model_rows)
        csv_out(z,"06_VALIDE_SECILEN_KILITLI_YONTEM_LAST18.csv",comparison)
        csv_out(z,"07_16_SICAK_SINIR_DERINLIGI_YENI_YERLESIK.csv",depthrows)
        csv_out(z,"08_SON18_HER_CEKILIS_10_SAYI_GERCEK_KONTROL.csv",audits)
        csv_out(z,"09_GECMIS_SON_GOZLENEN_HOT_GIRIS_CIKIS.csv",firstlast)
        diag=dict(source="veri.txt",source_rows=n,
           targets=n_target,latest_source_id=rows[-1]["id"],
           targetcount_by_period=dict(targetcounts),
           all_224_nested_rings=LENS.tolist(),
           comparison="NEW_HOT vs ESTABLISHED_HOT",
           hot_pool_fixed_members=16,
           anchors_draws=list(map(int,LENS[list(ANCHOR)])),
           each_ticket_10_distinct_numbers=True,
           methods=METHODS,validation_locked_choice=dict(
             method=win_m,lookback=win_l,validation_avg10=win_v),
           future_data_used_to_choose=False,
           last18_previously_explored_not_virgin_holdout=True)
        z.writestr("10_METOD_DENETIM.json",
                    json.dumps(diag,ensure_ascii=False,indent=2))
    print("\n".join(notes),flush=True)
    print("V132 COMPLETED",out,out.stat().st_size,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v132_output/V132_YENI_SICAK_YERLESIK_SICAK_HEDEF20_KARSILASTIRMA.zip")
    a=p.parse_args()
    main(a.source,a.out)
