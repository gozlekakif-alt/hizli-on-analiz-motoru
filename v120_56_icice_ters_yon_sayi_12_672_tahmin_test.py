#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V120: NO FAMILIES. Number-level nested 12..672 directional audit.

At each target draw t, before seeing draw:
state_672 and state_12 from nested recent L-count pools in ascending freq,
5 equal 16-member classes; all 56 cumulative windows snap frozen.

Test 672 HOT->12 COLD vs 672 COLD->12 HOT, plus matched controls,
on NEXT DRAW event X[t,b]. 25% uniform null. Report by days with
cluster bootstrap; earlier analyzed data is not genuine untouched future.
"""
from __future__ import annotations
import argparse, collections, csv, io, json, zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load

RINGS=np.arange(12,673,12,dtype=np.int32)
POOL=("SOGUK","SERIN","NOTR","ILIK","SICAK")
GROUPS=("ALL","HOT672_COLD12","COLD672_HOT12",
        "HOT672_HOT12","COLD672_COLD12",
        "HOT672_OTHER12","COLD672_OTHER12",
        "COOL_BY_2PLUS","WARM_BY_2PLUS","COOL_BY_1PLUS",
        "WARM_BY_1PLUS","SAME_POOL","HOT672_NOT_COLD12",
        "COLD672_NOT_HOT12")
SEED=12067212

def csvout(z,name,records):
    if not records:return
    with z.open(name,"w",force_zip64=True) as f:
        fd=io.TextIOWrapper(f,encoding="utf-8-sig",newline="")
        w=csv.DictWriter(fd,fieldnames=list(records[0]))
        w.writeheader();w.writerows(records)
        fd.flush();fd.detach()

def calc(P,t):
    assert t>=672
    cnt=P[t][None,:]-P[t-RINGS]
    order=np.argsort(cnt,axis=1,kind="stable")
    st=np.empty((56,80),dtype=np.int8)
    st[np.arange(56)[:,None],order]=np.repeat(np.arange(5,dtype=np.int8),16)
    return cnt,st

def metrics(rows):
    a=np.asarray(rows,float)
    return int(a[:,0].sum()),int(a[:,1].sum())

def boot_by_day(daily,phase,ga,gb=None,B=5000):
    ds=sorted(set(d for p,d,g in daily if p==phase))
    if len(ds)<2: return None
    data=np.array([[
        daily.get((phase,d,g),(0,0))[0],
        daily.get((phase,d,g),(0,0))[1]] for d in ds for g in
        (ga,) if gb is None],dtype=np.float64) if gb is None else np.array([
         [daily.get((phase,d,ga),(0,0))[0],
          daily.get((phase,d,ga),(0,0))[1],
          daily.get((phase,d,gb),(0,0))[0],
          daily.get((phase,d,gb),(0,0))[1]] for d in ds
        ],dtype=np.float64)
    if np.sum(data[:,0])==0 or (gb is not None and np.sum(data[:,2])==0):
        return None
    rng=np.random.default_rng(SEED+len(phase)*83+len(ga)*173+(len(gb) if gb else 0))
    idx=rng.integers(0,len(ds),size=(B,len(ds)))
    a=data[idx].sum(axis=1)
    keep=(a[:,0]>0)
    if gb is not None:keep&=(a[:,2]>0)
    if not keep.any():return None
    a=a[keep]
    boots=a[:,1]/a[:,0] if gb is None else a[:,1]/a[:,0]-a[:,3]/a[:,2]
    observed=float(data[:,1].sum()/data[:,0].sum())
    if gb is not None: observed-=float(data[:,3].sum()/data[:,2].sum())
    return dict(days=len(ds),mean=round(observed,7),
                lo95=round(float(np.quantile(boots,.025)),7),
                hi95=round(float(np.quantile(boots,.975)),7),
                valid_boots=len(boots))

def main(src,dest):
    days,rows,X,issues,bad=load(src)
    n=len(rows)
    P=np.vstack((np.zeros((1,80),dtype=np.int32),
                 np.cumsum(X,axis=0,dtype=np.int32)))
    baseline=sorted([d for d in days if d<="2026-10-12"])
    assert len(baseline)==72
    phases={}
    for i,date in enumerate(baseline):
        phases[date]=("FIRST36" if i<36 else "MIDDLE18" if i<54 else "LAST18")
    by_phase=collections.defaultdict(lambda:[0,0])
    by_day=collections.defaultdict(lambda:[0,0])
    grid=collections.defaultdict(lambda:[0,0])
    per_draw=[]
    extreme_events=[]
    latest_80=[]
    tracked_agg=collections.defaultdict(lambda:[0,0])
    phase_sizes=collections.Counter()
    for t in range(672,n):
        day=rows[t]["day"]
        phase=phases.get(day,"ADDED_AFTER_OCT12")
        phase_sizes[phase]+=1
        cnt,st=calc(P,t)
        long=st[-1]
        short=st[0]
        mid=st[5]
        actual=X[t].astype(bool)
        gs={
          "ALL":np.ones(80,dtype=bool),
          "HOT672_COLD12":(long==4)&(short==0),
          "COLD672_HOT12":(long==0)&(short==4),
          "HOT672_HOT12":(long==4)&(short==4),
          "COLD672_COLD12":(long==0)&(short==0),
          "HOT672_OTHER12":(long==4)&(short<4),
          "COLD672_OTHER12":(long==0)&(short>0),
          "COOL_BY_2PLUS":(short<=long-2),
          "WARM_BY_2PLUS":(short>=long+2),
          "COOL_BY_1PLUS":(short<long),
          "WARM_BY_1PLUS":(short>long),
          "SAME_POOL":(short==long),
          "HOT672_NOT_COLD12":(long==4)&(short>0),
          "COLD672_NOT_HOT12":(long==0)&(short<4)}
        assert set(gs)==set(GROUPS)
        assert np.all(np.bincount(long,minlength=5)==16)
        assert np.all(np.bincount(short,minlength=5)==16)
        assert int(sum(gs["ALL"]))==80
        rec=dict(date=day,phase=phase,target_id=rows[t]["id"])
        for name in GROUPS:
            mask=gs[name]
            count=int(mask.sum())
            hits=int(actual[mask].sum())
            assert 0<=hits<=count
            by_phase[(phase,name)][0]+=count
            by_phase[(phase,name)][1]+=hits
            by_day[(phase,day,name)][0]+=count
            by_day[(phase,day,name)][1]+=hits
            rec[name+"_n"]=count
            rec[name+"_hit"]=hits
        per_draw.append(rec)
        for p in range(5):
            for q in range(5):
                mask=(long==p)&(short==q)
                for pp in (phase,"ALL"):
                    grid[(pp,p,q)][0]+=int(mask.sum())
                    grid[(pp,p,q)][1]+=int((mask&actual).sum())
        # Only extreme (rare) pre-draw classified number observations
        # stored with full 56 states and 672 frozen bits for audit.
        for typ in ("HOT672_COLD12","COLD672_HOT12"):
            for b in np.flatnonzero(gs[typ]):
                extreme_events.append(dict(date=day,target_id=rows[t]["id"],
                    number=int(b+1),pretarget_group=typ,
                    ones_12_draw=int(cnt[0,b]),
                    ones_72_draw=int(cnt[5,b]),
                    ones_672_draw=int(cnt[-1,b]),
                    pretarget_56_pools="".join("CSNIH"[int(x)] for x in st[:,b]),
                    pretarget_56_counts="|".join(map(str,cnt[:,b])),
                    target_drawn_1_or_0=int(actual[b])))
        if t==n-1:
            for b in range(80):
                latest_80.append(dict(number=b+1,
                    latest_pre_target_id=rows[t]["id"],
                    preceding_672_ones="".join(map(str,X[t-672:t,b])),
                    nested_56_ones="|".join(map(str,cnt[:,b])),
                    nested_56_pools="".join("CSNIH"[int(x)] for x in st[:,b]),
                    pool_672=POOL[int(long[b])],
                    pool_72=POOL[int(mid[b])],
                    pool_12=POOL[int(short[b])],
                    number_times_last672=int(cnt[-1,b]),
                    next_draw_outcome=int(actual[b])))
        if (t-672+1)%3000==0:
            print("V120 analyzed next-draw targets",t-672+1,"/",n-672,flush=True)
    for name in GROUPS:
        for phase in ("FIRST36","MIDDLE18","LAST18","ADDED_AFTER_OCT12"):
            v=by_phase[(phase,name)]
            # Keep short outputs clear, unavailable groups show zero.
            pass
    summary=[]
    for phase in ("FIRST36","MIDDLE18","LAST18","ADDED_AFTER_OCT12"):
        for name in GROUPS:
            ns,hit=by_phase[(phase,name)]
            summary.append(dict(phase=phase,group=name,
                number_draw_opportunities=ns,appeared_in_target=hit,
                actual_probability_percent=round(100*hit/ns,4) if ns else None,
                fair_probability_percent=25.0,
                difference_from_25_percentage_points=round(100*hit/ns-25,4) if ns else None,
                targets_in_period=int(phase_sizes[phase])))
    gridrows=[]
    for phase in ("FIRST36","MIDDLE18","LAST18","ADDED_AFTER_OCT12","ALL"):
        for p in range(5):
            for q in range(5):
                nobs,hits=grid[(phase,p,q)]
                gridrows.append(dict(phase=phase,pool_672=POOL[p],
                    pool_12=POOL[q],number_draw_count=nobs,
                    next_draw_hit=hits,
                    percent=round(100*hits/nobs,5) if nobs else None))
    daily=[]
    for (phase,day,name),(ns,hits) in sorted(by_day.items()):
        daily.append(dict(phase=phase,date=day,group=name,
            number_draw_opportunities=ns,next_draw_hits=hits,
            next_draw_percent=round(100*hits/ns,5) if ns else None))
    boot=[]
    for phase in ("LAST18","MIDDLE18","FIRST36"):
        for ga,gb in (
           ("HOT672_COLD12",None),("COLD672_HOT12",None),
           ("HOT672_COLD12","COLD672_HOT12"),
           ("HOT672_COLD12","HOT672_NOT_COLD12"),
           ("COLD672_HOT12","COLD672_NOT_HOT12"),
           ("COOL_BY_2PLUS","WARM_BY_2PLUS"),
           ("COOL_BY_1PLUS","WARM_BY_1PLUS")
           ):
            z=boot_by_day(by_day,phase,ga,gb)
            if z:boot.append(dict(phase=phase,group_a=ga,group_b=gb or "NONE",
              **z))
    lines=[
      "V120: YALNIZ SAYILAR — 56 IC ICE HALKA 672 SICAK->12 SOGUK VS TERSI",
      f"Tested {n-672} subsequent SINGLE draws without observing outcome first.",
      f"Source ends #{rows[-1]['id']} {rows[-1]['day']}.",
      "56 nested windows last12,24,...672; each 80 numbers 5x16 classes.",
      "Direction means relative frequency rank across WINDOW LENGTH, not",
      "literal chronological heating between different wall-clock times.",
      "Group H->C: long 672 HOT pool, short 12 COLD pool.",
      "Group C->H: long 672 COLD pool, short 12 HOT pool.",
      "The appearance probability for an unpredicted fair number is 25%.",
      "Numbers tied by frequency break toward smaller number ID.",
      "Outcome at target t labels ONLY and is not included in its own pretarget pool.",
      "Comparisons with baseline same original 672-pool group control confounding.",
      "Historical data has been analyzed often; LAST18 is not prospectively unseen.",
      ""]
    for phase in ("LAST18","MIDDLE18","FIRST36","ADDED_AFTER_OCT12"):
        lines.append(f"--- {phase}: {phase_sizes[phase]} single target draws ---")
        for name in ("HOT672_COLD12","COLD672_HOT12","HOT672_HOT12",
                     "COLD672_COLD12","HOT672_NOT_COLD12",
                     "COLD672_NOT_HOT12","COOL_BY_2PLUS",
                     "WARM_BY_2PLUS","COOL_BY_1PLUS",
                     "WARM_BY_1PLUS","SAME_POOL"):
            a=next(x for x in summary if x["phase"]==phase and x["group"]==name)
            lines.append(
                f" {name}: n={a['number_draw_opportunities']}, "
                f"hits={a['appeared_in_target']}, "
                f"rate={a['actual_probability_percent']}%")
    lines+=["","BY-DAY BOOTSTRAP for LAST18 and comparisons (rate units 0..1):"]
    for x in boot:
        if x["phase"]=="LAST18":
            lines.append(f" {x['group_a']} minus {x['group_b']}: "
                         f"{x['mean']:.5f} CI95=[{x['lo95']:.5f},{x['hi95']:.5f}]")
    lines+=["","Important: Non-overlap with 0.25 in a post-hoc subgroup is NOT",
            "a viable betting method until novel forward draws validate.",
            "Relative 16-slot pool membership changes even when count stays unchanged.",
            "The # of candidate numbers per target varies (especially extreme patterns)."]
    dest=Path(dest)
    dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_V120_TURKCE_YON_KARSILASTIRMA_KISA.txt","\n".join(lines)+"\n")
        csvout(z,"01_TUM_HEDEFLER_KARSIT_YON_GUNLUK_ISABET.csv",per_draw)
        csvout(z,"02_DONEM_YON_GRUPLARI_ISABET.csv",summary)
        csvout(z,"03_672X12_BES_HAVUZ_25_HUCRE_GERCEK_ISABET.csv",gridrows)
        csvout(z,"04_TERS_UC_HAREKET_EDEN_SAYILARIN_56_HALKA_IZLERI.csv",extreme_events)
        csvout(z,"05_80_SAYI_SON_56_HAVUZ_KAYIT.csv",latest_80)
        csvout(z,"06_GUN_GUN_YON_ISABET_ORANLARI.csv",daily)
        csvout(z,"07_DONEM_GUN_BAZLI_GUVEN_ARALIKLARI.csv",boot)
        z.writestr("08_METOD_VE_DENETIM.json",json.dumps(dict(
            version="V120.1",total_source_draws=n,
            next_draw_targets=n-672,source_last_id=rows[-1]["id"],
            groups=list(GROUPS),windows=RINGS.tolist(),
            elligible_families_used=False,
            all_targets_only_previous_data=True,
            benchmark_single_number_chance=0.25,
            number_of_pre_target_extreme_number_events=len(extreme_events),
            prospective_unseen_experiment=False),
            ensure_ascii=False,indent=2))
    print("\n".join(lines),flush=True)
    print("V120 COMPLETE",dest,dest.stat().st_size,flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",default="veri.txt")
    ap.add_argument("--out",default="v120_output/V120_56_ICICE_TERSE_YON_HEDEF_SAYILAR.zip")
    a=ap.parse_args()
    main(a.source,a.out)
