#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V131 -- DO NUMBERS REVERSE BEFORE REACHING HOT, OR EXIT HOT IMMEDIATELY?

Exhaustive RETROSPECTIVE observation with 224 NESTED 12..2688 draw windows.
At observed draw t, classes/ranks are determined only by X[:t+1].
For a true future reversal we read already-archived t+1...t+36 results
AFTER defining the event at t. All H=36 event samples right-censor
the last 36 actual draws (never pretend their future is known).

Five exactly-16-member classes 0 cold,1 cool,2 neutral,3 warm,4 hot.
"approach": just entered WARM (class 3) from any lower class, not HOT.
"rank approach": already WARM 3, rank goes up, on selected anchor rings.
"enter": just reached HOT 4 from lower class.
"incumbent": stayed HOT 4 on the current step (anchor rings only).
"reverse before hot": next decisive class departure from class3 is DOWN
(<3) before it has ever reached class4. Direct cold0 is tracked SEPARATELY.
"immediate hot bounce": class4 at t becomes <4 at t+1.
"falls to cold": reaches ACTUAL class0 later (not just starts cooling).
One number/event can be repeated across overlapping reference rings;
counts are descriptive, not statistically independent draws.
"""
from __future__ import annotations
import argparse,csv,io,json,zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load

R,N=224,80
LENS=np.arange(12,2689,12,dtype=np.int32)
A=np.array((0,1,2,5,11,23,55,111,167,223),dtype=np.int32)
HORIZONS=(1,3,6,12,24,36)
POOL=("SOĞUK","SERİN","NÖTR","ILIK","SICAK")
SEED=1312026
assert len(LENS)==R and LENS[-1]==2688

def state(cnt):
    order=np.argsort(cnt,axis=1,kind="stable")
    rank=np.empty((R,N),dtype=np.uint8)
    rank[np.arange(R)[:,None],order]=np.arange(N,dtype=np.uint8)
    cls=rank//16
    assert np.all(np.bincount(cls.ravel(),minlength=5)==R*16)
    return rank,cls

def to_csv(z,p,rows):
    if not rows:return
    out=io.StringIO(newline="")
    w=csv.DictWriter(out,fieldnames=list(rows[0]))
    w.writeheader();w.writerows(rows)
    z.writestr(p,out.getvalue().encode("utf-8-sig"))

def event_first_exit(frames,i,r,b,warm_mode):
    """Return exit time, eventual cold0 time and class of first exit.
    For 'approach': first decisive departure from class3 = HOT or BELOW3.
    For 'hot': first exit from class4 to any class<4; also future cold0.
    The horizon is 36; 0 denotes no occurrence within 36 observations.
    """
    size=len(i)
    first=np.zeros(size,dtype=np.uint8)
    first_cold=np.zeros(size,dtype=np.uint8)
    destination=np.full(size,255,dtype=np.uint8)
    print("V131 examining",warm_mode,"events",size,flush=True)
    for k in range(1,37):
        remain=np.flatnonzero(first==0)
        if len(remain):
            st=frames[i[remain]+1+k,r[remain],b[remain]]
            decisive=(st!=3) if warm_mode else (st<4)
            chosen=remain[decisive]
            first[chosen]=k
            destination[chosen]=st[decisive]
        # "cold" is actual pool0, not mere downward/cool movement.
        rc=np.flatnonzero(first_cold==0)
        if len(rc):
            st=frames[i[rc]+1+k,r[rc],b[rc]]
            selected=rc[st==0]
            first_cold[selected]=k
        if k in (1,6,12,24,36):
            print("V131",warm_mode,"future step",k,
                  "first decisive",int((first!=0).sum()),
                  "cold0",int((first_cold!=0).sum()),flush=True)
    return first,first_cold,destination

def add_rows(label,fi,fc,dest,ei,er,eb,anchor_only=False):
    n=len(ei)
    if n==0:return []
    out=[]
    groups=[("ALL_RINGS",np.ones(n,dtype=bool))]
    groups.extend((f"BAND{j+1}_R{start+1}-{start+56}",(er>=start)&(er<start+56))
                  for j,start in enumerate((0,56,112,168)))
    groups.extend((f"RING_{r+1:03d}_L{12*(r+1)}",er==r) for r in A)
    # Also report actual 224 separate ring records to identify differences,
    # but avoid duplicate named anchor rows in visual comparisons.
    if not anchor_only:
        groups.extend((f"DETAIL_R{r+1:03d}",er==r) for r in range(224))
    for group,mask in groups:
        c=int(mask.sum())
        if c==0:continue
        ff=fi[mask]
        cold=fc[mask]
        ds=dest[mask]
        # first transition up to HOT vs turn down BEFORE HOT.
        hotfirst=ff>0
        if label in ("APPROACH_ILIK","RANK_RISING_ILIK"):
            rose=(ds==4)&hotfirst
            reversed=(ds<3)&hotfirst
            assert int(rose.sum()+reversed.sum())==int(hotfirst.sum())
            first_dest_down0=(ds==0)&hotfirst
        else:
            rose=None;reversed=None
            first_dest_down0=(ds==0)&hotfirst
        for h in HORIZONS:
            f=ff>0
            taken=f&(ff<=h)
            row=dict(event=label,group=group,horizon=h,
               events=c,first_decisive_within_h=int(taken.sum()),
               first_decisive_rate_pct=round(100*int(taken.sum())/c,5),
               still_in_entry_pool_through_h=int((~taken).sum()),
               still_in_entry_pool_pct=round(100*int((~taken).sum())/c,5),
               actual_cold_pool0_seen_within_h=int(((cold>0)&(cold<=h)).sum()),
               actual_cold_pool0_rate_pct=round(100*int(((cold>0)&(cold<=h)).sum())/c,5),
               direct_first_exit_to_pool0=int((taken&(ds==0)).sum()),
               first_departure_into_pool3=int((taken&(ds==3)).sum()),
               first_departure_into_pool2=int((taken&(ds==2)).sum()),
               first_departure_into_pool1=int((taken&(ds==1)).sum()),
               first_departure_into_pool0=int((taken&(ds==0)).sum()))
            if label in ("APPROACH_ILIK","RANK_RISING_ILIK"):
                success=int((rose&(ff<=h)).sum())
                turn=int((reversed&(ff<=h)).sum())
                row.update(reached_hot_before_cooling=success,
                   reached_hot_before_cooling_pct=round(100*success/c,5),
                   cooling_reversal_before_hot=turn,
                   cooling_reversal_before_hot_pct=round(100*turn/c,5),
                   no_decisive_move_by_h=int(c-success-turn))
            else:
                row.update(reached_hot_before_cooling="",
                   reached_hot_before_cooling_pct="",
                   cooling_reversal_before_hot="",
                   cooling_reversal_before_hot_pct="",
                   no_decisive_move_by_h="")
            out.append(row)
    return out

def main(source,out):
    days,rows,X,issues,bad=load(source)
    n=len(rows)
    assert n==len(X) and n>3000
    assert np.all(X.sum(axis=1)==20)
    P=np.vstack((np.zeros((1,N),dtype=np.int32),
                  np.cumsum(X,axis=0,dtype=np.int32)))
    nsteps=n-2688
    # Pool states before replay and after each of the 13,102 observed draws.
    frames=np.empty((nsteps+1,R,N),dtype=np.uint8)
    rankrise=np.zeros((nsteps+1,len(A),N),dtype=np.bool_)
    cnt=P[2688][None,:]-P[2688-LENS]
    rk,pool=state(cnt)
    frames[0]=pool
    for j,t in enumerate(range(2688,n),1):
        inc=X[t].astype(np.int16)
        out_old=X[t-LENS].astype(np.int16)
        nc=cnt+inc[None,:]-out_old
        nr,npool=state(nc)
        rankrise[j]=((pool[A]==3)&(npool[A]==3)&(nr[A]>rk[A]))
        frames[j]=npool
        cnt=nc;rk=nr;pool=npool
        if j%3000==0:
            print("V131 saved",j,"of",nsteps,"224x80 class states",flush=True)
    # Last 36 observed actual results have no complete NEXT36 trace:
    # Exclude from ALL denominator groups to avoid right-censor bias.
    E=nsteps-36
    assert E>12000
    prev=frames[:E]     # baseline at t-1
    after=frames[1:E+1] # known observed draw t
    # event i=0 represents observed draw at real index t=2688
    hot_i,hot_r,hot_b=np.nonzero((prev<4)&(after==4))
    approach_i,approach_r,approach_b=np.nonzero((prev<3)&(after==3))
    # Need not reach HOT to be moving toward it: rank moving UP
    # among 16 WARM-class numbers (class3 unchanged).
    rank_i,rank_anchor,rank_b=np.nonzero(rankrise[1:E+1])
    rank_r=A[rank_anchor]
    # Baseline comparison for established hot vs new entrants:
    # incumbent sample taken at the same 10 selected anchor rings.
    anchor_before=prev[:,A,:]
    anchor_after=after[:,A,:]
    incumbent_i,incumbent_anchor,incumbent_b=np.nonzero(
              (anchor_before==4)&(anchor_after==4))
    incumbent_r=A[incumbent_anchor]
    del prev,after,anchor_before,anchor_after

    hot_first,hot_cold,hot_dest=event_first_exit(
                        frames,hot_i,hot_r,hot_b,False)
    app_first,app_cold,app_dest=event_first_exit(
                        frames,approach_i,approach_r,approach_b,True)
    rank_first,rank_cold,rank_dest=event_first_exit(
                        frames,rank_i,rank_r,rank_b,True)
    incumbent_first,incumbent_cold,incumbent_dest=event_first_exit(
                        frames,incumbent_i,incumbent_r,incumbent_b,False)

    records=[]
    records.extend(add_rows("ENTER_HOT",hot_first,hot_cold,hot_dest,
                      hot_i,hot_r,hot_b))
    records.extend(add_rows("APPROACH_ILIK",app_first,app_cold,app_dest,
                      approach_i,approach_r,approach_b))
    records.extend(add_rows("RANK_RISING_ILIK",rank_first,rank_cold,rank_dest,
                      rank_i,rank_r,rank_b,anchor_only=True))
    records.extend(add_rows("ESTABLISHED_HOT",incumbent_first,incumbent_cold,
                      incumbent_dest,incumbent_i,incumbent_r,incumbent_b,
                      anchor_only=True))
    def group(event,key,h):
        return next(q for q in records if
              q["event"]==event and q["group"]==key and q["horizon"]==h)
    report=[
      "V131 — SICAGA GIRIS ve GIRMEDEN ONCE YON TERSINE DONME GERCEK TESTI",
      f"Real data source {n} draws, latest #{rows[-1]['id']} "
                       f"{rows[-1]['day']} {rows[-1]['time']}.",
      f"Full 224 rings 80 balls: {nsteps:,} historical state changes,",
      f"evaluated event steps {E:,} with full 36-draw future observed.",
      "Last 36 observed draws are EXCLUDED from follow-up percentages.",
      "Pools: 5 groups of exact 16; cold=0, cool=1, neutral=2,",
      "warm/ilik=3, hot/sicak=4. Tie by smaller ball ID.",
      "APPROACH_ILIK: new class is WARM3, old class was <3.",
      "RANK_RISING_ILIK: stayed WARM3 but rank increased (anchor rings only).",
      "ENTER_HOT: old class <4, new class HOT4.",
      "ESTABLISHED_HOT: old class HOT4, new class HOT4 (anchors only).",
      "For APPROACH, the first subsequent class movement AWAY from 3",
      "is class4=HOT success or class0/1/2=COOL reversal before HOT.",
      "For HOT, exit means leave class4, NOT necessarily cold class0.",
      "Reaching actual class0 within 36 is reported separately.",
      "All results describe observed past, not future prediction.",""]
    for ev in ("APPROACH_ILIK","RANK_RISING_ILIK",
               "ENTER_HOT","ESTABLISHED_HOT"):
        key="ALL_RINGS" if ev in ("APPROACH_ILIK","ENTER_HOT") else \
              "RING_001_L12"
        for h in HORIZONS:
            q=group(ev,key,h)
            if ev in ("APPROACH_ILIK","RANK_RISING_ILIK"):
                report.append(f"{ev} {key} next<= {h:2d}: N={q['events']:,} "
                   f"FIRST reach-HOT {q['reached_hot_before_cooling_pct']}%, "
                   f"FIRST reverse-cooling {q['cooling_reversal_before_hot_pct']}%,"
                   f" still ILIK {q['still_in_entry_pool_pct']}%; "
                   f"ever COLD0 {q['actual_cold_pool0_rate_pct']}%")
            else:
                report.append(f"{ev} {key} next<= {h:2d}: N={q['events']:,} "
                   f"EXIT-HOT {q['first_decisive_rate_pct']}%, "
                   f"still continuously HOT {q['still_in_entry_pool_pct']}%;"
                   f" ever actual COLD0 {q['actual_cold_pool0_rate_pct']}%")
    report.extend(["",
       "SELECTED ANCHOR RINGS (12,72,672,1344,2016,2688):"])
    for ring in (0,5,55,111,167,223):
        key=f"RING_{ring+1:03d}_L{LENS[ring]}"
        lines=[]
        for ev in ("APPROACH_ILIK","ENTER_HOT","ESTABLISHED_HOT"):
            q=group(ev,key,12)
            if ev=="APPROACH_ILIK":
                lines.append(f"APPROACH n={q['events']:,} reverse_before_hot12 "
                    f"{q['cooling_reversal_before_hot_pct']}%, reach_hot12 "
                    f"{q['reached_hot_before_cooling_pct']}%")
            else:
                lines.append(f"{ev} n={q['events']:,} exit_hot12 "
                    f"{q['first_decisive_rate_pct']}%, actual_cold0_12 "
                    f"{q['actual_cold_pool0_rate_pct']}%")
        report.append(f" RING{ring+1:3d} L={LENS[ring]}: "+" | ".join(lines))
    # show information on current (latest archived) state, NOT future outcomes.
    latest=[]
    for ring in (0,5,55,111,167,223):
        newlyhot=np.flatnonzero(
            (frames[-2,ring]<4)&(frames[-1,ring]==4))+1
        warmingnear=np.flatnonzero(
            (frames[-2,ring]<3)&(frames[-1,ring]==3))+1
        latest.append(dict(
            last_real_draw_id=rows[-1]["id"],
            ring=ring+1,lookback=int(LENS[ring]),
            newly_entered_hot_numbers="-".join(map(str,newlyhot)),
            newly_entered_ilik_numbers="-".join(map(str,warmingnear)),
            no_subsequent_36_draws_in_this_file=True))
    # Full 224 ring×H event results and 4 bands already in records.
    per_80=[]
    for ev,ei,er,eb,first,cold,dest in (
       ("ENTER_HOT",hot_i,hot_r,hot_b,hot_first,hot_cold,hot_dest),
       ("APPROACH_ILIK",approach_i,approach_r,approach_b,app_first,app_cold,app_dest)):
        for b in range(N):
            sel=eb==b
            nsel=int(sel.sum())
            if nsel==0:continue
            f=first[sel];c=cold[sel];d=dest[sel]
            per_80.append(dict(event=ev,number=b+1,
                total_all224_events=nsel,
                reversal_before_hot_12=int(((f>0)&(f<=12)&(d<3)).sum())
                  if ev=="APPROACH_ILIK" else "",
                reach_hot_before_reverse_12=int(((f>0)&(f<=12)&(d==4)).sum())
                  if ev=="APPROACH_ILIK" else "",
                exit_hot_within1=int(((f>0)&(f<=1)).sum())
                  if ev=="ENTER_HOT" else "",
                exit_hot_within12=int(((f>0)&(f<=12)).sum())
                  if ev=="ENTER_HOT" else "",
                reached_actual_cold0_within12=int(
                 ((c>0)&(c<=12)).sum())))
    # All event rates in source terms are HISTORICAL distributions. If fair
    # draw, future individual next-draw chance remains P=20/80=.25.
    report.extend(["",
        "MECHANICS: Any new HOT entry must displace another HOT-class member",
        "because class4 has EXACTLY 16 members, but this says NOTHING",
        "about the entrant's own next-step exit probability.",
        "Higher churn in short windows is partly caused by overlapping",
        "past windows, class-rank sorting and equal 16-member quotas.",
        "Even a repeated bounce pattern is not evidence of predicting",
        "the RNG's next unknown 20 numbers.",
        "The newest actual result in file was Oct13, not live/current Oct17.",
        "Latest-entry number lists are historical signals lacking future data."])
    dest=Path(out);dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as z:
        z.writestr("00_V131_SICAGA_GIRIS_TERS_YON_GERCEK_RAPOR.txt",
                   "\n".join(report)+"\n")
        to_csv(z,"01_224_HALKA_HER_GIRIS_TURU_1_3_6_12_24_36_CIKIS.csv",records)
        to_csv(z,"02_HER_80_SAYI_HALKA_SICAK_GIRIS_TERSINE_DONUS.csv",per_80)
        to_csv(z,"03_EN_SON_BILINEN_CEKILIS_SICAGA_YENI_GIRENLER.csv",latest)
        z.writestr("04_V131_KAYNAK_KONTROL.json",json.dumps(dict(
          source="veri.txt",source_rows=n,latest_id=rows[-1]["id"],
          first_state_after_draw_id=rows[2687]["id"],
          target_lookback_2688=True,nested_ring_count=R,
          windows=LENS.tolist(),future_followup_horizons=HORIZONS,
          analysis_completed_event_steps=E,
          total_observed_draw_state_changes=nsteps,
          censor_last36=True, no_claim_of_future_prediction=True,
          event_count_hot_entries=int(len(hot_i)),
          event_count_approach_ilik=int(len(approach_i)),
          event_count_anchor_rank_warm=int(len(rank_i)),
          event_count_anchor_established_hot=int(len(incumbent_i)),
          source_latest_actual_date=rows[-1]["day"],
          all_results_historical=True,
          class_size_16_each=True,complete_36_future_horizon=True),
          ensure_ascii=False,indent=2))
    print("\n".join(report),flush=True)
    print("V131 COMPLETE",dest,"bytes",dest.stat().st_size,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v131_output/V131_SICAGA_GIRIS_TERS_YON_224_HALKA_36_TAKIP.zip")
    a=p.parse_args()
    main(a.source,a.out)
