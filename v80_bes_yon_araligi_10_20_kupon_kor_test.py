#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V80 — which directional lookback best converts 5×16 heat movements into
actual target-ball hits on ONE frozen 10-ball coupon and a 20-ball candidate set?

Study 72 complete days ending 12 Oct 2026, 1–80, 20 actual per target.
A) N=60 fixed temperature lookback, per-number frequency prior to target
   sorted into five exactly-16-member heat groups, stable previous rank on ties.
B) ONLY DIRECTIONAL LAG varies: L=6,12,18,24,36 draws (requested experiment).
   Same fixed 30-state feature (current tier x old->now sign x new entrant).
C) Historical target1 frequencies of each state trained on 29 Aug–12 Sep
   (15 full days), Bayesian shrinkage toward .25, alpha=250.
D) Compare FREE (globally top20, top10) and BALANCED (4 per tier for 20,
   2 per tier for 10), where 10 ticket is always a subset of its 20 pool.
E) 13–27 Sep VALIDATE chooses SINGLE lag+policy by 10-ticket utility
   (mean hits minus 0.25*sd of fifteen daily means), ties by 20 average.
F) 28 Sep–12 Oct HOLDOUT tests the LOCKED winner without re-selection.
G) Diagnostic: evaluate all pre-set candidates separately without post hoc
   winner re-selection. Next day's 13 Oct first uninterrupted 112 draws for
   additional retrospective check; full day incomplete, #61958, #61972 missing.

For any fair independent lottery, a chosen 10 set expects 2.5 hits; a
chosen 20 set expects 5.0 hits, independent of heat labels. Statistical
evidence cannot be claimed from over-explored historical target periods.
"""
from __future__ import annotations
import argparse,csv,io,zipfile,json,math
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VER="V80.1"
N=60
LAGS=(6,12,18,24,36)
METHODS=("FREE","BALANCED")
ALPHA=250
SEED=801015
DAY_SIZE=217
DAYS=72
START_TRAIN=27*DAY_SIZE
START_VALID=42*DAY_SIZE
START_HOLD=57*DAY_SIZE
END_HOLD=72*DAY_SIZE
HEAT=("SOGUK","SERIN","NOTR","ILIK","SICAK")
TREND=("SOGUYOR","SABIT","ISINIYOR")
PHASES=(("VALIDATE",START_VALID,START_HOLD),("HOLDOUT",START_HOLD,END_HOLD))
K10=10;K20=20
P=.25

def data(source):
    grouped,issues,malformed=parse_txt(source)
    full_days=sorted(d for d,items in grouped.items()
       if len(items)==DAY_SIZE and [a["pos"] for a in items]==list(range(1,218)))
    if len(full_days)!=72 or full_days[0]!="2026-08-01" or full_days[-1]!="2026-10-12":
        raise RuntimeError(f"Need 72 complete dates 1Aug-12Oct; got {len(full_days)}")
    historical=[r for d in full_days for r in grouped[d]]
    if len(historical)!=15624 or historical[-1]["id"]!=61845:
        raise RuntimeError("Unexpected full-day corpus boundary")
    after=grouped.get("2026-10-13",[])
    future=[]
    for row in after:
        if row["id"] != historical[-1]["id"]+1+len(future):
            break
        future.append(row)
    if not future:raise RuntimeError("Cannot verify next-day uninterrupted prefix")
    known={r["id"] for r in after}
    gaps=[k for k in range(after[0]["id"],after[-1]["id"]+1) if k not in known]
    draws=historical+future
    y=np.zeros((len(draws),80),dtype=np.uint8)
    for i,r in enumerate(draws):
        y[i,np.asarray(r["nums"],dtype=int)-1]=1
    assert np.all(y.sum(axis=1)==20)
    return draws,y,full_days,future,len(after),gaps,issues,malformed

def rank_history(y):
    rows=y.shape[0]
    p=np.zeros((rows+1,80),dtype=np.int32)
    p[1:]=np.cumsum(y,dtype=np.int32,axis=0)
    ranks=np.full((rows,80),255,dtype=np.uint8)
    last=np.arange(80)
    ball=np.arange(80)
    for t in range(N,rows):
        f=p[t]-p[t-N]
        ordered=np.lexsort((last,f))
        r=np.empty(80,dtype=np.uint8)
        r[ordered]=np.arange(80,dtype=np.uint8)
        ranks[t]=r
        last=r
    return ranks,p

def states(tier,idx,lag):
    cur=tier[idx]
    before=tier[idx-lag]
    previous=tier[idx-1]
    direction=np.where(cur>before,2,np.where(cur<before,0,1)).astype(np.uint8)
    entry=(cur!=previous).astype(np.uint8)
    state=((cur*3+direction)*2+entry).astype(np.uint8)
    assert state.max()<30
    return cur,direction,entry,state

def train_rate(s,y,alpha):
    n=np.bincount(s.reshape(-1),minlength=30).astype(np.int64)
    h=np.bincount(s.reshape(-1),weights=y.reshape(-1),minlength=30).astype(np.float64)
    prob=(h+alpha*.25)/(n+alpha)
    return prob,n,h

def select(cur,states,prob,noise,kind,k):
    scores=prob[states]+1e-9*noise
    chosen=np.zeros(cur.shape,dtype=np.uint8)
    ix=np.arange(cur.shape[0])[:,None]
    if kind=="FREE":
        ids=np.argpartition(scores,-k,axis=1)[:,-k:]
        chosen[ix,ids]=1
    elif kind=="BALANCED":
        count=k//5
        if k%5:raise ValueError("Balanced k not divisible by five")
        for q in range(5):
            masked=np.where(cur==q,scores,-1.)
            ids=np.argpartition(masked,-count,axis=1)[:,-count:]
            assert np.all(cur[ix,ids]==q)
            chosen[ix,ids]=1
    else:raise ValueError(kind)
    assert np.all(chosen.sum(axis=1)==k)
    return chosen

def hit_metrics(sel,rnd,y,k):
    a=(sel*y).sum(axis=1).astype(int)
    b=(rnd*y).sum(axis=1).astype(int)
    mu=k*.25
    var=k*.25*.75*(80-k)/79
    fairz=(int(a.sum())-len(a)*mu-.5)/math.sqrt(var*len(a))
    fairp=.5*math.erfc(fairz/math.sqrt(2))
    m=(k-(sel*rnd).sum(axis=1)).astype(np.int64)
    vardiff=float(np.sum(2*m*.25*.75*80/79))
    z=float((a-b).sum())/math.sqrt(vardiff) if vardiff else 0.
    p=.5*math.erfc(z/math.sqrt(2)) if vardiff else 1.
    stats=dict(n=int(len(a)),mean=round(float(a.mean()),8),
      control_mean=round(float(b.mean()),8),
      advantage=round(float((a-b).mean()),8),sum_hits=int(a.sum()),
      fair_expectation=mu,
      fair_p_one_sided=round(fairp,8),paired_z=round(z,6),
      paired_p_one_sided=round(p,8),
      hits_5plus=int((a>=5).sum()),
      hits_6plus=int((a>=6).sum()),
      hits_7plus=int((a>=7).sum()),
      hits_8plus=int((a>=8).sum()),
      hits_9plus=int((a>=9).sum()),
      hits_10plus=int((a>=10).sum()))
    return stats,a,b

def utility(hits,global_indices):
    days=np.unique(global_indices//DAY_SIZE)
    daily=[float(hits[global_indices//DAY_SIZE==d].mean()) for d in days]
    mean=float(hits.mean())
    sd=float(np.std(daily,ddof=1)) if len(daily)>1 else 0.
    return mean,sd,mean-.25*sd

def write_csv(z,name,records):
    if not records:return
    with z.open(name,"w",force_zip64=True) as raw:
        tx=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        w=csv.DictWriter(tx,fieldnames=list(records[0]))
        w.writeheader();w.writerows(records)
        tx.flush();tx.detach()

def analyse(source,out):
    draws,y,dates,nextday,partial_total,missing,issues,malformed=data(source)
    rank,p=rank_history(y)
    tier=rank//16
    tra=np.arange(START_TRAIN,START_VALID)
    idx_valid=np.arange(START_VALID,START_HOLD)
    idx_hold=np.arange(START_HOLD,END_HOLD)
    idx_next=np.arange(END_HOLD,END_HOLD+len(nextday))
    for ix in (tra,idx_valid,idx_hold,idx_next):
        assert np.all(rank[ix]<80)
    # Neither training nor target tests touch 23 Aug missing-day gap:
    # full history N+lag behind earliest 29Aug is several days after 24Aug.
    raw_ids=np.array([r["id"] for r in draws])
    for ix in (tra,idx_valid,idx_hold,idx_next):
        for t in ix:
            assert np.all(np.diff(raw_ids[t-N-max(LAGS):t+1])==1),\
              f"Unbroken history unavailable for target {draws[t]['id']}."
    rng=np.random.default_rng(SEED)
    common_noise=rng.random((len(draws)-START_TRAIN,80))
    trial_rows=[]
    rates={}
    metrics={}
    by_phase={}
    audit_rows=[]
    for lag in LAGS:
        trcur,trdir,trentry,trstate=states(tier,tra,lag)
        prob,op,hits=train_rate(trstate,y[tra],ALPHA)
        rates[lag]=(prob,op,hits)
        for phase,indices in (("VALIDATE",idx_valid),("HOLDOUT",idx_hold),
                              ("NEXT_DAY",idx_next)):
            cur,dire,entry,s=states(tier,indices,lag)
            noise=common_noise[indices-START_TRAIN]
            truth=y[indices]
            for kind in METHODS:
                selected20=select(cur,s,prob,noise,kind,20)
                selected10=select(cur,s,prob,noise,kind,10)
                # Random controls use EXACTLY same quota constraints as model.
                random20=select(cur,cur,np.ones(5)*.25,noise,kind,20)
                random10=select(cur,cur,np.ones(5)*.25,noise,kind,10)
                assert np.all((selected10 & ~selected20)==0), "Coupon10 not subset of candidate20"
                assert np.all((random10 & ~random20)==0)
                x10,hit10,rand10=hit_metrics(selected10,random10,truth,10)
                x20,hit20,rand20=hit_metrics(selected20,random20,truth,20)
                mean10,sd10,u10=utility(hit10,indices)
                mean20,sd20,u20=utility(hit20,indices)
                record=dict(lag_draws=lag,mode=kind,phase=phase,
                     expected10=2.5,expected20=5.,
                     avg10=x10["mean"],random10=x10["control_mean"],
                     gain10=x10["advantage"],daily_sd10=round(sd10,7),
                     validation_utility10=round(u10,7),
                     p10_fair=x10["fair_p_one_sided"],
                     p10_paired=x10["paired_p_one_sided"],
                     coupon10_5plus=x10["hits_5plus"],
                     coupon10_6plus=x10["hits_6plus"],
                     coupon10_7plus=x10["hits_7plus"],
                     coupon10_8plus=x10["hits_8plus"],
                     coupon10_9plus=x10["hits_9plus"],
                     coupon10_10of10=x10["hits_10plus"],
                     avg20=x20["mean"],random20=x20["control_mean"],
                     gain20=x20["advantage"],daily_sd20=round(sd20,7),
                     validation_utility20=round(u20,7),
                     p20_fair=x20["fair_p_one_sided"],
                     p20_paired=x20["paired_p_one_sided"],
                     pool20_7plus=x20["hits_7plus"],
                     pool20_8plus=x20["hits_8plus"],
                     pool20_9plus=x20["hits_9plus"],
                     pool20_10plus=x20["hits_10plus"],
                     evaluated_draws=len(indices),
                     sum10_hits=x10["sum_hits"],
                     sum20_hits=x20["sum_hits"])
                trial_rows.append(record)
                by_phase[(lag,kind,phase)]=dict(
                    index=indices,cur=cur,dir=dire,entry=entry,
                    selected10=selected10,selected20=selected20,
                    rand10=random10,rand20=random20,
                    hit10=hit10,hit20=hit20,
                    rand10_hits=rand10,rand20_hits=rand20,
                    s=s,prob=prob)
        print("V80 trained + validated lag",lag,flush=True)
    validate=[v for v in trial_rows if v["phase"]=="VALIDATE"]
    validate.sort(key=lambda v:(-v["validation_utility10"],-v["avg20"],
                                LAGS.index(v["lag_draws"]),METHODS.index(v["mode"])))
    frozen_lag,frozen_mode=validate[0]["lag_draws"],validate[0]["mode"]
    chosen={(r["phase"]):r for r in trial_rows if
            r["lag_draws"]==frozen_lag and r["mode"]==frozen_mode}
    selected_test=by_phase[(frozen_lag,frozen_mode,"HOLDOUT")]
    selected_next=by_phase[(frozen_lag,frozen_mode,"NEXT_DAY")]
    for phase,block in (("HOLDOUT",selected_test),("NEXT_DAY",selected_next)):
        for j,t in enumerate(block["index"]):
            target=draws[int(t)]
            c=block["cur"][j]
            x10=block["selected10"][j];x20=block["selected20"][j]
            yhit=y[t]
            one=dict(phase=phase,date=target["day"],clock=target["time"],
                draw_id=target["id"],slot=target["pos"],
                selected_lag=frozen_lag,policy=frozen_mode,
                selected_coupon10=",".join(map(str,np.flatnonzero(x10)+1)),
                coupon10_hits=int(block["hit10"][j]),
                coupon10_hit_balls=",".join(map(str,np.flatnonzero(x10&yhit)+1)),
                matched_random10_hits=int(block["rand10_hits"][j]),
                selected_candidate20=",".join(map(str,np.flatnonzero(x20)+1)),
                candidate20_hits=int(block["hit20"][j]),
                matched_random20_hits=int(block["rand20_hits"][j]),
                target_actual20=",".join(map(str,np.flatnonzero(yhit)+1)))
            for q in range(5):
                one[f"candidate20_pool_{HEAT[q].lower()}"]=",".join(
                    map(str,np.flatnonzero(x20&(c==q))+1))
                one[f"coupon10_pool_{HEAT[q].lower()}"]=",".join(
                    map(str,np.flatnonzero(x10&(c==q))+1))
            audit_rows.append(one)
    day_summaries=[]
    for stage,blk in (("HOLDOUT",selected_test),("NEXT_DAY",selected_next)):
        dayids=[draws[t]["day"] for t in blk["index"]]
        for day in sorted(set(dayids)):
            ix=np.array([i for i,dd in enumerate(dayids) if dd==day],dtype=int)
            day_summaries.append(dict(day=day,phase=stage,
               lookback=frozen_lag,mode=frozen_mode,targets=len(ix),
               coupon10_avg=round(float(blk["hit10"][ix].mean()),6),
               random10_avg=round(float(blk["rand10_hits"][ix].mean()),6),
               candidate20_avg=round(float(blk["hit20"][ix].mean()),6),
               random20_avg=round(float(blk["rand20_hits"][ix].mean()),6),
               coupon10_6plus=int((blk["hit10"][ix]>=6).sum()),
               coupon10_7plus=int((blk["hit10"][ix]>=7).sum()),
               coupon10_8plus=int((blk["hit10"][ix]>=8).sum()),
               coupon10_9plus=int((blk["hit10"][ix]>=9).sum()),
               coupon10_10of10=int((blk["hit10"][ix]==10).sum())))
    state_rates=[]
    for lag in LAGS:
        prob,op,hits=rates[lag]
        for st in range(30):
            q=st//6
            d=(st%6)//2
            en=st%2
            state_rates.append(dict(lag=lag,current_heat=HEAT[q],
                 heat_direction=TREND[d],entered_new16_this_draw=en,
                 trained_number_draw_states=int(op[st]),
                 trained_target_ones=int(hits[st]),
                 train_empirical_rate=round(float(hits[st]/op[st]),8) if op[st] else None,
                 shrink_250_probability=round(float(prob[st]),9)))
    summary=[
      "V80 — 72 TAM GUN 5x16 HAVUZLAR ICIN EN VERIMLI YON CEKILIS ARALIGI",
      "OBJECTIVE IS COUPON HITS: compare 10-ball coupon first, 20-ball pool second.",
      "Fixed temperature reference: 60 preceding draws for all five directional lags.",
      f"Movement lag choices={LAGS}; method modes={METHODS}.",
      "Mode FREE selects top 20 and top 10 number identities without group quota;",
      "Mode BALANCED selects exactly 4 / pool in 20, exactly 2 / pool in 10.",
      "Every 10-ball coupon is contained inside the same draw's 20-ball candidate pool.",
      "All five lags use same TRAIN/VALIDATION/HOLDOUT and same random control seeds.",
      "Per-ball historical target1 frequency from 5 current heat x 3 direction x",
      "2 last-step entry classes, 30 cells; shrink alpha250 toward .25 RNG prior.",
      f"TRAIN {dates[27]}..{dates[41]} (3255 draws) fits probabilities, no selection.",
      f"VALIDATION {dates[42]}..{dates[56]} (3255 draws) selects lag+mode.",
      f"HOLDOUT {dates[57]}..{dates[71]} (3255 draws) locked, no retuning.",
      f"NEXT_DAY 2026-10-13 first {len(nextday)} contiguous draws from partial "
      f"{partial_total}, missing IDs={missing}.",
      "Earlier V64-V79 studies repeatedly examined historical testing dates.",
      "Therefore this is retrospective split, not untouched forward-looking proof.",
      "",
      "VALIDATION TABLE: main target 10/10 coupon mean, random 2.5:",
    ]
    for rec in sorted(validate,key=lambda k:(k["lag_draws"],k["mode"])):
        summary.append(f"L={rec['lag_draws']:>2} {rec['mode']:8}: 10={rec['avg10']:.5f} "
           f"(random10={rec['random10']:.5f}); 20={rec['avg20']:.5f} "
           f"(random20={rec['random20']:.5f})")
    summary+=[
      "",
      f"FROZEN on VALIDATION: L={frozen_lag}, mode={frozen_mode}, based on 10-hit "
      "mean-0.25xdaily SD.",
      f"FROZEN VALIDATION coupon10={chosen['VALIDATE']['avg10']:.5f}, "
      f"candidate20={chosen['VALIDATE']['avg20']:.5f}.",
      f"FROZEN HOLDOUT 10-hit={chosen['HOLDOUT']['avg10']:.5f} "
      f"random={chosen['HOLDOUT']['random10']:.5f}, "
      f"gain={chosen['HOLDOUT']['gain10']:+.5f}, "
      f"paired upper p={chosen['HOLDOUT']['p10_paired']:.6f}.",
      f"FROZEN HOLDOUT 20-hit={chosen['HOLDOUT']['avg20']:.5f} "
      f"random={chosen['HOLDOUT']['random20']:.5f}, "
      f"gain={chosen['HOLDOUT']['gain20']:+.5f}, "
      f"paired upper p={chosen['HOLDOUT']['p20_paired']:.6f}.",
      f"FROZEN HOLDOUT 10/10 exact occurrences={chosen['HOLDOUT']['coupon10_10of10']}, "
      f"9+={chosen['HOLDOUT']['coupon10_9plus']}, "
      f"8+={chosen['HOLDOUT']['coupon10_8plus']}, "
      f"7+={chosen['HOLDOUT']['coupon10_7plus']}, "
      f"6+={chosen['HOLDOUT']['coupon10_6plus']}.",
      f"FROZEN NEXT 13 OCT 10-hit={chosen['NEXT_DAY']['avg10']:.5f}, "
      f"random={chosen['NEXT_DAY']['random10']:.5f}, "
      f"gain={chosen['NEXT_DAY']['gain10']:+.5f}, "
      f"10/10={chosen['NEXT_DAY']['coupon10_10of10']}.",
      f"FROZEN NEXT 13 OCT 20-hit={chosen['NEXT_DAY']['avg20']:.5f}, "
      f"random={chosen['NEXT_DAY']['random20']:.5f}.",
      "",
      "EXPLORATORY HOLDOUT LAG x MODE TABLE (DO NOT RESELECT BASED ON IT):"
    ]
    for rec in sorted((k for k in trial_rows if k["phase"]=="HOLDOUT"),
                      key=lambda k:(k["lag_draws"],k["mode"])):
        summary.append(f"L={rec['lag_draws']:>2} {rec['mode']:8}: 10={rec['avg10']:.5f} "
               f"(random={rec['random10']:.5f}), 20={rec['avg20']:.5f} "
               f"(random={rec['random20']:.5f})"
               +(" [LOCKED WINNER]" if (rec["lag_draws"],rec["mode"])==
                (frozen_lag,frozen_mode) else ""))
    summary+=["",
      "EXPECTED UNDER FAIR INDEPENDENT LOTTERY: 10 coupon 2.5 /10, 20 pool 5 /20.",
      "Differences may be noise; 10/10 rarity and many tried models require caution.",
      "Do not claim a number direction or lottery RNG mechanism was solved.",
      "The only parameter varied is movement L and whether quota is imposed.",
      "For conclusive signal, test ONE locked recipe on genuinely new draws.",
      ""]
    out=Path(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        z.writestr("00_V80_KISA_KARAR.txt","\n".join(summary))
        write_csv(z,"01_TUM_5_LAG_X_2_KURAL_VAL_HOLD_NEXT_10_20_ISABET.csv",trial_rows)
        write_csv(z,"02_VALIDASYON_TEK_KURAL_SECIM_SIRALAMASI.csv",validate)
        write_csv(z,"03_KILITLI_KURAL_3255_VE_13EKIM_HEDEF_10_20_KUPON.csv",audit_rows)
        write_csv(z,"04_KILITLI_KURAL_GUNLUK_ISABET_RASTGELE.csv",day_summaries)
        write_csv(z,"05_5_ARALIK_X_5_ISI_X_3_YON_X_2_GIRIS_OGRENME.csv",state_rates)
        z.writestr("06_HESAPLAMA_KURALLARI.txt","\n".join([
          "72 days = 01 Aug through 12 Oct, excluding invalid 23 Aug.",
          "N=60 historical draws fixed for determining all 5x16 thermal tiers.",
          "Movement lookback L=6,12,18,24,36 varies; direction compares",
          "the heat class now to same ball's heat class L target steps ago.",
          "Each tier holds 16 of 80 balls at EVERY target time.",
          "One-step new-entrant category is heat tier now != at last target.",
          "30 state conditional empirical target1 rates use ONLY 29 Aug..12 Sep.",
          "Shrinkage alpha=250 prior .25, no validation/holdout/future labels fitting.",
          "All per-target number selection is BEFORE its actual drawn 20 is known.",
          "FREE takes globally highest P balls: top 10 subset top 20.",
          "BALANCED takes per-tier top2 subset per-tier top4.",
          "Uniform-random FREE controls are unconstrained; BALANCED random",
          "controls use exactly matching tier quotas (10=2x5,20=4x5).",
          "The same random ranks for equality tie-breaking are shared for all methods.",
          "10 hits rather than pretty movements drive model choice in validation.",
          "Validation winner is only chosen by 10 mean minus .25*SD daily means;",
          "20 mean used only for exact tiebreak, then lag and mode fixed.",
          "Report EVERY pre-specified lag separately on HOLDOUT for audit,",
          "but only the validation winner is the locked model in HOLDOUT.",
          "Next-day October13 dataset contains 2 missing rows; to preserve lag",
          "only the first uninterrupted 112 target draws are used.",
          "Expected under RNG: 2.5 of10 and 5 of20, NO guaranteed hits.",
          "These dates have been examined before, so this is retrospectively",
          "chronological validation NOT genuinely new prospective evidence."
        ])+"\n")
        z.writestr("07_AUDIT.json",json.dumps(dict(
           version=VER,temperatures_N=N,lags=LAGS,modes=METHODS,alpha=ALPHA,
           train_days=dates[27:42],validate_days=dates[42:57],
           holdout_days=dates[57:72],frozen=dict(lag=frozen_lag,mode=frozen_mode),
           validation_winner=chosen["VALIDATE"],
           holdout_locked=chosen["HOLDOUT"],
           next_day_locked=chosen["NEXT_DAY"],
           next_day_consecutive=len(nextday),
           next_day_available=partial_total,next_day_missing=missing,
           all_combinations=trial_rows,issues=issues[:20],
           malformed=malformed[:20]),ensure_ascii=False,indent=2))
    print("\n".join(summary),flush=True)
    print("V80 ZIP",str(out),"size",out.stat().st_size,flush=True)

def selftest():
    rg=np.random.default_rng(15)
    cur=np.tile(np.arange(80,dtype=np.uint8)//16,(90,1))
    old=np.roll(cur,1,axis=1)
    one=np.roll(cur,2,axis=1)
    st=((cur*3+np.where(cur>one,2,np.where(cur<one,0,1)))*2
       +(cur!=old)).astype(np.uint8)
    yy=np.zeros_like(cur)
    for i in range(len(yy)):yy[i,rg.choice(80,20,replace=False)]=1
    p,n,h=train_rate(st,yy,ALPHA)
    assert n.sum()==len(yy)*80 and len(p)==30
    randoms=rg.random(cur.shape)
    for method in METHODS:
        ten=select(cur,st,p,randoms,method,10)
        twenty=select(cur,st,p,randoms,method,20)
        assert np.all((ten&~twenty)==0)
        assert np.all(ten.sum(axis=1)==10)
        assert np.all(twenty.sum(axis=1)==20)
        if method=="BALANCED":
            for group in range(5):
                assert np.all((ten*(cur==group)).sum(axis=1)==2)
                assert np.all((twenty*(cur==group)).sum(axis=1)==4)
    assert abs(hit_metrics(ten,ten,yy,10)[0]["fair_expectation"]-2.5)<1e-9
    print("V80 SELFTEST OK")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v80_output/V80_72GUN_5_YON_ARALIGI_10_KUPON_20_HAVUZ_KOR_TEST.zip")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:selftest()
    else:analyse(a.source,a.out)
