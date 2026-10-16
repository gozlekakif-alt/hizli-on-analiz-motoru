#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V104: start with FIRST 672 draws of the ORIGINAL 72 full days, WALK 1 by 1.
Not the nested V100B model. No coupons and no selecting 'winning' numbers.

- exactly 15,624 draws on 72 complete days, 80 balls, 20 per draw;
- t=672 initializes 56 SEALED absolute 12-draw rings (index 0..55);
- each t+1 old draw exits and new enters, absolute ring boundaries NEVER
  get reconstructed: 55 SEALED + 2 partial until next 12th draw;
- pool identity at each SEALED ring's end from last72 known draws; initial
  first 5 rings before day-1 72-draw warmup use available 12..60 draws,
  explicitly provisional, otherwise genuine 72;
- records ALL 80 balls' full 55-56 SEALED pool/direction paths, detailed
  next-ring direction for each SEALED boundary, changes across ALL rings.
- each future next-ring outcome computed ONLY after ring was completed.
No "blind test" is necessary to describe the phenomenon. Conditional
tables for short6 vs full56 are descriptive, not a betting edge proof.
"""
from __future__ import annotations
import argparse,collections,csv,io,json,math,zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load,temperature
from v102_80sayi_56_halka_yon_zinciri_hedef_saat import expected_hours
VERSION="V104.1"
MEM=672
RS=12
POOLS=("SOGUK","SERIN","NOTR","ILIK","SICAK")
HOT="CSNIH"
DIRECTIONS={-1:"SOGUMA",0:"SABIT",1:"ISINMA"}
SYMBOL={-1:"D",0:"=",1:"Y"}

def csvw(z,name,rows):
    if not rows:return
    with z.open(name,"w",force_zip64=True) as raw:
        out=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        w=csv.DictWriter(out,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
        out.flush();out.detach()

def stable_paths(t,temps):
    """Return sealed ring absolute IDs, 80×seals states, and sign steps."""
    start=t-MEM
    assert start>=0 and t>=672
    first=(start+11)//12
    last=(t//12)-1
    gids=np.arange(first,last+1,dtype=np.int32)
    s=temps[gids].T.astype(np.int8)
    d=np.sign(np.diff(s,axis=1)).astype(np.int8)
    assert 55<=len(gids)<=56
    assert s.shape==(80,len(gids)) and d.shape==(80,len(gids)-1)
    return gids,s,d

def profile(s,d):
    """Features for 80 ball histories. All computed BEFORE unseen target."""
    net6=s[:,-1]-s[:,-7]
    net12=s[:,-1]-s[:,-13]
    rises=(d>0).sum(axis=1)
    falls=(d<0).sum(axis=1)
    steadies=(d==0).sum(axis=1)
    # Consecutive step reversal +,- or -,+ (not a same-temperature pause).
    reversals=(d[:,:-1]*d[:,1:]==-1).sum(axis=1)
    # Long history volatility, computed on every single historic direction
    # step. Full-chain signature distinguishes identical last6 state.
    volatility=(d!=0).sum(axis=1)
    last_move=d[:,-1]
    last6up=(d[:,-6:]>0).sum(axis=1)
    last6down=(d[:,-6:]<0).sum(axis=1)
    return dict(net6=net6,net12=net12,rises=rises,falls=falls,
      steadies=steadies,reversals=reversals,volatility=volatility,
      last_move=last_move,last6up=last6up,last6down=last6down)

def category(n):
    """Fixed low/mod/high bins, no labels from target used to set them."""
    if n<=24:return "AZ_HAREKET"
    if n<=34:return "ORTA_HAREKET"
    return "COK_HAREKET"

def take_hour(rows,X):
    full,rejected=expected_hours(rows)
    return [(t,d,hh,ids) for t,d,hh,ids in full if t>=672 and t+12<=len(X)],rejected

def run(src,dest):
    days,rows,X,issues,bad=load(src)
    # User explicitly requested START OF 72-DAY HISTORICAL POOL:
    rows=rows[:72*217];X=X[:72*217]
    days=days[:72]
    n=len(rows)
    assert n==15624 and X.shape==(15624,80) and X.sum()==n*20
    starts=(np.arange(1,n//12+1)*12)
    prefix=np.vstack((np.zeros((1,80),np.int32),np.cumsum(X,axis=0,dtype=np.int32)))
    seal=np.empty((n//12,80),dtype=np.int8)
    for rid,e in enumerate(starts):
        begin=max(0,int(e)-72)
        seal[rid]=temperature(prefix[e]-prefix[begin])
    hours,rejected=take_hour(rows,X)
    hourlookup={t:(day,hh,ids) for t,day,hh,ids in hours}
    first_80=[];last_80=[];walk=[]
    hours_full=[]
    ring_changes=[]
    transition_ledger=[]
    count_group=collections.defaultdict(lambda:[0,0,0,0])
    count_short=collections.defaultdict(lambda:[0,0,0,0])
    # Individual completed ring movements: one per 12 recorded draws.
    for rid in range(1,len(seal)):
        dr=np.sign(seal[rid]-seal[rid-1]).astype(np.int8)
        ups=np.flatnonzero(dr==1)
        downs=np.flatnonzero(dr==-1)
        unchanged=np.flatnonzero(dr==0)
        if rid>=2:
            prev=np.sign(seal[rid-1]-seal[rid-2]).astype(np.int8)
            same=int(np.sum(prev==dr))
            bothup=int(np.sum((prev==1)&(dr==1)))
            bothdown=int(np.sum((prev==-1)&(dr==-1)))
            reversed_=int(np.sum(prev*dr==-1))
        else:
            same=bothup=bothdown=reversed_=0
        ring_changes.append(dict(
          absolute_ring_id=rid,
          ring_12_first_draw=rows[rid*12]["id"],
          ring_12_last_draw=rows[(rid+1)*12-1]["id"],
          pool_reference_draws=min(72,(rid+1)*12),
          sealed=True,
          warming_count=int(len(ups)),cooling_count=int(len(downs)),
          steady_count=int(len(unchanged)),
          sum_rank_delta=int(np.sum(seal[rid]-seal[rid-1])),
          warming_numbers="-".join(map(str,ups+1)),
          cooling_numbers="-".join(map(str,downs+1)),
          same_prev_step_count=same,
          up_in_both_adjacent_steps=bothup,
          down_in_both_adjacent_steps=bothdown,
          reversed_between_adjacent_steps=reversed_))
    assert all(r["sum_rank_delta"]==0 for r in ring_changes)
    # Run the entire 72-day dataset one NEW DRAW at a time, never leap 12.
    for t in range(672,n+1):
        r=t%12
        oldest=t-672
        count_sealed=56 if r==0 else 55
        count_physical=56 if r==0 else 57
        # In a FIFO window, newest record is t-1, oldest is t-672.
        assert oldest>=0
        assert (count_sealed*12+(0 if r==0 else (12-r)+r))==672
        live=rows[t-1]
        row=dict(
            step_from_first_672=t-672,
            last_added_id=live["id"],last_added_date=live["day"],
            oldest_still_held_id=rows[oldest]["id"],
            last_known_id=live["id"],memory_size=672,
            complete_rings=count_sealed,physical_rings=count_physical,
            oldest_partial_size=(12-r if r else 0),
            newest_partial_size=(r if r else 0),
            new_ring_closed=int(t>672 and r==0),
            expired_old_ring=int(t>672 and r==0),
            absolute_oldest_ring_id=oldest//12,
            absolute_newest_ring_id=(t-1)//12
        )
        walk.append(row)
        # One row per group of 80 balls at first, last and each complete
        # target HOUR, with full 56-direction strings and future labels.
        if t not in hourlookup and t not in (672,n):
            continue
        ids,S,D=stable_paths(t,seal)
        feats=profile(S,D)
        next_ring=int(t//12)
        end=(next_ring+1)*12
        can_observe=end<=n
        # A sealed ring outcome becomes known only at its future END.
        nextdir=(np.sign(seal[next_ring]-S[:,-1])
                 if can_observe else None)
        hour=hourlookup.get(t)
        if hour is not None:
            date,hr,drawids=hour
            result=X[t:t+12]
            hourly_hits=result.sum(axis=0)
        else:
            date=hr=drawids=result=hourly_hits=None
        batch=[]
        for ball in range(80):
            path="".join(HOT[int(v)] for v in S[ball])
            signs="".join(SYMBOL[int(v)] for v in D[ball])
            p=feats
            group=category(int(p["volatility"][ball]))
            nextval=(int(nextdir[ball]) if nextdir is not None else None)
            x=dict(
              anchor_draw_index=t,first_lookback_draw_id=rows[t-672]["id"],
              last_lookback_draw_id=rows[t-1]["id"],
              ball=ball+1,full_ring_count=len(ids),
              oldest_full_ring_id=int(ids[0]),newest_full_ring_id=int(ids[-1]),
              first_pool=POOLS[int(S[ball,0])],
              latest_pool=POOLS[int(S[ball,-1])],
              latest_pool_rank=int(S[ball,-1]),
              net_last6=int(p["net6"][ball]),
              net_last12=int(p["net12"][ball]),
              total_55_step_up=int(p["rises"][ball]),
              total_55_step_down=int(p["falls"][ball]),
              total_55_step_stable=int(p["steadies"][ball]),
              direction_reversals=int(p["reversals"][ball]),
              movement_volume=int(p["volatility"][ball]),
              full_chain_class=group,
              last_completed_step=SYMBOL[int(p["last_move"][ball])],
              last6_up_steps=int(p["last6up"][ball]),
              last6_down_steps=int(p["last6down"][ball]),
              full_56_temperature_path=path,
              full_55_direction_path=signs,
              next_sealed_ring_id=(next_ring if can_observe else ""),
              next_sealed_ring_end_id=(rows[end-1]["id"] if can_observe else ""),
              next_pool=(POOLS[int(seal[next_ring,ball])] if can_observe else ""),
              next_direction=(DIRECTIONS[nextval] if can_observe else "HENUZ_BILINMIYOR"),
              target_hour=(f"{date} {hr:02d}:02-{hr:02d}:57"
                           if hour is not None else ""),
              target_12_seen=(int(hourly_hits[ball]) if hour is not None else ""),
              target_H1_H12_bits=("".join(str(int(result[i,ball])) for i in range(12))
                                if hour is not None else "")
            )
            batch.append(x)
            if hour is not None:hours_full.append(x)
            if can_observe and t%12==0 and t<n:
                # Use exactly once per completed ring to avoid pretending
                # 12 intra-ring snapshots are independent.
                key=(int(S[ball,-1]),int(np.sign(p["net6"][ball])),group)
                kshort=(int(S[ball,-1]),int(np.sign(p["net6"][ball])))
                count_group[key][nextval+1]+=1
                count_short[kshort][nextval+1]+=1
        if t==672:first_80=batch
        if t==n:last_80=batch
        if t%12==0 and t<n:
            nd=np.array([int(x["next_direction"]=="ISINMA") for x in batch])
            trans=np.array([int(x["next_direction"]=="SOGUMA") for x in batch])
            transition_ledger.append(dict(
                pre_next_ring_at_draw_id=rows[t-1]["id"],
                next_ring_id=next_ring,
                next_ring_last_draw=rows[end-1]["id"],
                warming_numbers="-".join(str(i+1) for i in np.flatnonzero(nd)),
                cooling_numbers="-".join(str(i+1) for i in np.flatnonzero(trans)),
                rising_count=int(nd.sum()),cooling_count=int(trans.sum()),
                stable_count=80-int(nd.sum())-int(trans.sum())))
        if t%1800==0:
            print("V104 FIFO processed",t,"/",n,flush=True)
    assert len(walk)==n-672+1
    assert first_80 and last_80
    summaries=[]
    for (laststate,net6,group),v in sorted(count_group.items()):
        nobs=sum(v)
        if not nobs:continue
        summaries.append(dict(latest_pool=POOLS[laststate],
          last6_net_direction=DIRECTIONS[net6],
          full56_chain_class=group,n=nobs,
          next_cooling=v[0],next_steady=v[1],next_warming=v[2],
          next_cooling_pct=round(100*v[0]/nobs,5),
          next_steady_pct=round(100*v[1]/nobs,5),
          next_warming_pct=round(100*v[2]/nobs,5)))
    summary6=[]
    for (laststate,net6),v in sorted(count_short.items()):
        nobs=sum(v)
        summary6.append(dict(latest_pool=POOLS[laststate],
          last6_net_direction=DIRECTIONS[net6],n=nobs,
          next_cooling=v[0],next_steady=v[1],next_warming=v[2],
          next_cooling_pct=round(100*v[0]/nobs,5),
          next_steady_pct=round(100*v[1]/nobs,5),
          next_warming_pct=round(100*v[2]/nobs,5)))
    # Fixed-condition report: does FULL-history class move next-warming
    # rates even while latest pool and net6 sign are the same?
    largest_gap=[]
    for (p,ns),short in sorted(count_short.items()):
        cats=[x for x in summaries if x["latest_pool"]==POOLS[p]
               and x["last6_net_direction"]==DIRECTIONS[ns] and x["n"]>=60]
        if len(cats)>=2:
            small=min(cats,key=lambda z:z["next_warming_pct"])
            large=max(cats,key=lambda z:z["next_warming_pct"])
            largest_gap.append(dict(latest_pool=POOLS[p],
              last6_direction=DIRECTIONS[ns],
              lower_full_history=small["full56_chain_class"],
              lower_n=small["n"],lower_next_warming_pct=small["next_warming_pct"],
              higher_full_history=large["full56_chain_class"],
              higher_n=large["n"],higher_next_warming_pct=large["next_warming_pct"],
              difference_pp=round(large["next_warming_pct"]-small["next_warming_pct"],4)))
    largest_gap.sort(key=lambda r:-r["difference_pp"])
    sc=np.array([r["warming_count"] for r in ring_changes],float)
    cool=np.array([r["cooling_count"] for r in ring_changes],float)
    still=np.array([r["steady_count"] for r in ring_changes],float)
    normal=[r for r in ring_changes if r["pool_reference_draws"]==72]
    same_sum=sum(r["same_prev_step_count"] for r in normal)
    trans_normal=len(normal)
    first_time=rows[0]["day"]+" "+rows[0]["time"]
    last_time=rows[-1]["day"]+" "+rows[-1]["time"]
    distinct_days=len(set(r["day"] for r in rows))
    report=[
      "V104 - 72 GUNUN BASINDAN DEV 672 CEEKILIS / 56 HALKA FIFO YURUYUSU",
      "NO KUPON AND NO FORECAST MODEL FITTING. Full 56-ring direction chain first.",
      f"First actual draw: {first_time} #{rows[0]['id']}",
      f"Last actual draw: {last_time} #{rows[-1]['id']}",
      f"72 days={distinct_days}, draws={n}, 20-of-80 verified.",
      "Initial 672 draw memory used from FIRST DRAW. Initial 56 full rings 0-55.",
      f"First available target after 672: #{rows[672]['id']} {rows[672]['day']} {rows[672]['time']}.",
      f"FIFO 1-draw advances: {len(walk)-1:,}; 12-draw ring closures: {sum(r['new_ring_closed'] for r in walk):,}.",
      f"ALL stable 12-draw completed ring transitions: {len(ring_changes)} (first 5 had <72 startup history).",
      f"At start: {first_80[0]['full_ring_count']} sealed rings; at end: {last_80[0]['full_ring_count']}.",
      f"At each boundary no new drawing is invented: memory always {MEM}.",
      "At nonboundary: 55 COMPLETE + 2 PARTIAL rings (old/new), 57 physical rings.",
      "",
      "DO ALL 80 BALLS GO IN THE SAME DIRECTION? NO:",
      f"Mean warming per ring step={sc.mean():.3f}, cooling={cool.mean():.3f}, stable={still.mean():.3f}.",
      f"Min/max number warming in one ring={int(sc.min())}/{int(sc.max())}.",
      f"Min/max number cooling in one ring={int(cool.min())}/{int(cool.max())}.",
      f"Adjacent ring steps same sign among 80 balls incl stable: {100*same_sum/(80*trans_normal):.3f}%.",
      "Since each temperature rank class has exactly 16 balls, the sum of all",
      "80 pool-rank changes each ring is EXACTLY ZERO; not all can move up.",
      "",
      f"Full complete target hours >= first 672: {len(hours)} (incomplete excluded {rejected}).",
      "For EVERY completed target hour, every ball's 55/56-pool chain and",
      "its 12 H1-H12 realized hand flags are in 05, and historical next",
      "SEALED ring direction label is in the same record.",
      "For EACH ring closure all warming/cooling number IDs are in 04 and 06.",
      "",
      "NEXT RING DIRECTION AFTER THE SAME LAST6 SIGNAL - FULL56 CHAIN:",
      "Full56 movement-volume bins: 0-24 AZ, 25-34 ORTA, 35+ COK.",
      "Below are the largest descriptive within-lastpool/last6 contrasts;",
      "these ARE NOT selected prediction rules and groups may be small."]
    for x in largest_gap[:15]:
        report.append(f" {x['latest_pool']} last6={x['last6_direction']} "
          f"{x['lower_full_history']}({x['lower_n']})=>Y %{x['lower_next_warming_pct']:.2f}; "
          f"{x['higher_full_history']}({x['higher_n']})=>Y %{x['higher_next_warming_pct']:.2f}; "
          f"diff={x['difference_pp']:+.2f}pp")
    report +=["",
      "NEXT RESEARCH: verify whether those full56 path differences remain",
      "in independent later data. Descriptive changes alone do NOT prove",
      "the path can predict future balls. User request here is WALKING CHAIN.",
      "",
      "FILES: 00 report, 01 each draw FIFO, 02 first 80 x56 DNA, 03 last",
      "80 x56 DNA, 04 all 12-draw seals direction list, 05 every target",
      "hour x80 full DNA + target H1-12 and NEXT RING DIR, 06 boundary",
      "labels, 07 short6 v full56 conditional next directions, 08 matched",
      "short6 only, 09 descriptive gap audit, 10 JSON source audit."]
    meta=dict(version=VERSION,only_initial_full_72_days=True,
      first_date=rows[0]["day"],last_date=rows[-1]["day"],
      first_draw_id=rows[0]["id"],last_draw_id=rows[-1]["id"],
      initial_672_draw_ids=[rows[0]["id"],rows[671]["id"]],
      first_target_draw_id=rows[672]["id"],
      actual_draws=n,FIFO_1_draw_steps=len(walk)-1,
      ring_closures=sum(r["new_ring_closed"] for r in walk),
      completed_ring_changes=len(ring_changes),last_complete_ring_count=last_80[0]["full_ring_count"],
      full_hour_anchors=len(hours), rejected_hours=rejected,
      initial_five_rings_startup_reference="first12,24,36,48,60 available draws, then trailing72",
      long_history_feature="all 54/55 sign steps: number of moves, reversals and path",
      conditional_next_direction="frozen at 12-draw ring closure, next 12 observed draws determine ring transition",
      uncertainty="Conditional frequency tables not out-of-sample future predictions",
      source_issues=issues[:20],malformed=bad[:20])
    dst=Path(dest);dst.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dst,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_YURUYEN_672_56_HALKA_YON_KESIN_SONUC.txt","\n".join(report)+"\n")
        csvw(z,"01_72GUN_BASTAN_SONA_HER_CEKILIS_BIR_ADIM_FIFO.csv",walk)
        csvw(z,"02_ILK_672_80_SAYI_56_HALKA_YON_DNA.csv",first_80)
        csvw(z,"03_SON_672_80_SAYI_56_HALKA_YON_DNA.csv",last_80)
        csvw(z,"04_HER_TAMAMLANAN_12_HALKA_YON_HAREKETI.csv",ring_changes)
        csvw(z,"05_HEDEF_SAAT_80_SAYI_TAM56_YON_VE_GERCEK12.csv",hours_full)
        csvw(z,"06_TUM_GELECEK_HALKA_YONLERI_80_SAYI.csv",transition_ledger)
        csvw(z,"07_SON6_VE_TAM56_GECIS_DAGILIMI.csv",summaries)
        csvw(z,"08_YALNIZ_SON6_GECIS_DAGILIMI.csv",summary6)
        csvw(z,"09_TAM56_AZ_ORTA_COK_HAREKET_FARKLARI.csv",largest_gap)
        z.writestr("10_YONTEM_VERI_ZAMAN_DENETIM.json",
            json.dumps(meta,ensure_ascii=False,indent=2,default=str))
    print("\n".join(report),flush=True)
    print("V104 SUCCESS",dst,dst.stat().st_size,flush=True)

def selftest():
    arr=np.tile(np.arange(5,dtype=np.int8).repeat(16),(70,1))
    g,s,d=stable_paths(672,arr)
    assert len(g)==56 and s.shape==(80,56) and d.shape==(80,55)
    g,s,d=stable_paths(673,arr)
    assert len(g)==55 and s.shape==(80,55) and d.shape==(80,54)
    g,s,d=stable_paths(684,arr)
    assert len(g)==56 and g[0]==1 and g[-1]==56
    assert all(np.sum(arr[k]-arr[k-1])==0 for k in range(1,len(arr)))
    print("V104 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v104_output/V104_72GUN_BASINDAN_YURUYEN_672_56_HALKA.zip")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest()
    else:run(args.source,args.out)
