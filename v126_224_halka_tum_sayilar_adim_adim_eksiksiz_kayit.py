#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V126 -- exhaustive, LOSSLESS 224-ring (12,24,...,2688) / 80-ball
state after EVERY real new draw, including exact rank and five-pool
change, independent of prediction/families.

The NPZ per calendar day is a fully reconstructible data cube:
 count_state[steps,224,80] uint16
 rank_state[steps,224,80] uint8 (0=coldest, 79=hottest)
 pool_state[steps,224,80] uint8 (0..4, exactly 16 per pool/ring)
 incoming_draw_packed[steps,10] uint8 (np.packbits 80 actual outcome bits)
 leaving_ring_packed[steps,224,10] uint8 (np.packbits 80 bits of
   the historic draw that EXITS that specific ring at each step)
 ring_change_counts[steps,224,12] uint8 (detailed counts)
 five_by_five_transition[steps,224,5,5] uint8 (sum 80 per ring)
 number_change_counts[steps,80,8] uint16 (across 224 rings).
 INITIAL_CONDITION.npz is the full state before the first new draw.
 All previous states are recoverable across daily block boundaries.
 To decode a specific event, use v126_detay_oku.py.

No target leakage: this is descriptive AFTER observing each new actual
draw, not a predictive claim. No previous V125 archive contents fabricated.
"""
from __future__ import annotations
import argparse,collections,csv,gzip,io,json,zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load

LENS=np.arange(12,2689,12,dtype=np.int32)
NR,NB=224,80
POOL_N=(0,1,2,3,4)
POOL_NAMES=("SOGUK","SERIN","NOTR","ILIK","SICAK")
RING_METRICS=(
 "cnt_plus1","cnt_minus1","cnt_unchanged",
 "rank_warmer","rank_colder","rank_unchanged",
 "pool_warmer","pool_colder","pool_unchanged",
 "enters_only","exits_only","old_and_new_drawn")
BALL_METRICS=(
 "count_up_rings","count_down_rings",
 "rank_warm_rings","rank_cool_rings",
 "pool_warm_rings","pool_cool_rings",
 "enter_ring_count","exit_ring_count")
assert len(LENS)==224 and LENS[-1]==2688
NRECENT=12

def ranks_and_pools(cnt):
    assert cnt.shape==(NR,NB)
    order=np.argsort(cnt,axis=1,kind="stable")
    r=np.empty((NR,NB),dtype=np.uint8)
    r[np.arange(NR)[:,None],order]=np.arange(NB,dtype=np.uint8)
    cls=r//16
    assert np.all(np.bincount(cls.ravel(),minlength=5)==NR*16)
    return r,cls

def npz_bytes(**arrays):
    b=io.BytesIO()
    np.savez_compressed(b,**arrays)
    return b.getvalue()

def put_csv(z,path,recs):
    if not recs:return
    out=io.StringIO(newline="")
    wr=csv.DictWriter(out,fieldnames=list(recs[0].keys()))
    wr.writeheader()
    wr.writerows(recs)
    z.writestr(path,out.getvalue().encode("utf-8-sig"),compress_type=zipfile.ZIP_DEFLATED)

def put_gz_csv(z,path,recs):
    if not recs:return
    out=io.BytesIO()
    with gzip.GzipFile(fileobj=out,mode="wb",compresslevel=6,mtime=0) as g:
        stream=io.TextIOWrapper(g,encoding="utf-8-sig",newline="")
        wr=csv.DictWriter(stream,fieldnames=list(recs[0].keys()))
        wr.writeheader()
        wr.writerows(recs)
        stream.flush()
        stream.detach()
    z.writestr(path,out.getvalue(),compress_type=zipfile.ZIP_STORED)

def human_event(t,draw_rows,ring,number,oldc,oldr,oldp,
                newc,newr,newp,enter,leave):
    r=ring; b=number
    return dict(
      target_id=draw_rows[t]["id"],date=draw_rows[t]["day"],
      time=draw_rows[t]["time"],circle=r+1,reference_draws=int(LENS[r]),
      number=b+1,
      old_count=int(oldc[r,b]),new_count=int(newc[r,b]),
      count_direction=int(newc[r,b])-int(oldc[r,b]),
      old_rank_coldest0=int(oldr[r,b]),
      new_rank_coldest0=int(newr[r,b]),
      rank_direction=int(newr[r,b])-int(oldr[r,b]),
      old_pool=POOL_NAMES[int(oldp[r,b])],
      new_pool=POOL_NAMES[int(newp[r,b])],
      pool_direction=int(newp[r,b])-int(oldp[r,b]),
      drawn_in_new_1_0=int(enter[b]),
      removed_old_1_0=int(leave[r,b])
    )

def main(source,out):
    days,rows,X,issues,bad=load(source)
    n=len(rows)
    assert len(X)==n and n>=2690
    assert np.all(X.sum(axis=1)==20)
    # Store all states for t=2688 ... n-1, with t-1 initialization.
    pref=np.vstack((np.zeros((1,NB),dtype=np.int32),
                    np.cumsum(X,axis=0,dtype=np.int32)))
    prevc=(pref[2688][None,:]-pref[2688-LENS]).astype(np.uint16)
    prevr,prevp=ranks_and_pools(prevc)
    assert np.all(prevc.sum(axis=1)==20*LENS)
    initial_count=prevc.copy()
    initial_rank=prevr.copy()
    initial_pool=prevp.copy()
    total_steps=n-2688
    # Key-index to read all lossless blocks later.
    idxrows=[]
    step_summary=[]
    ring_counters=np.zeros((NR,len(RING_METRICS)),dtype=np.uint64)
    ball_ring_counters=np.zeros((NR,NB,len(BALL_METRICS)),dtype=np.uint32)
    class_matrix=np.zeros((NR,5,5),dtype=np.uint64)
    dayring=collections.defaultdict(lambda:np.zeros((NR,len(RING_METRICS)),dtype=np.uint32))
    perday=[]
    daily_recent=collections.deque(maxlen=NRECENT)
    total_new_movement=0
    per_file=[]
    def flush(z,day,cube,metadata):
        arrays={
          "draw_id":np.asarray(metadata["drawid"],dtype=np.int64),
          "count_state":np.stack(cube["count"],axis=0),
          "rank_state":np.stack(cube["rank"],axis=0),
          "pool_state":np.stack(cube["pool"],axis=0),
          "incoming_draw_packed":np.stack(cube["draw"],axis=0),
          "leaving_ring_packed":np.stack(cube["left"],axis=0),
          "ring_change_counts":np.stack(cube["ring"],axis=0),
          "five_by_five_transition":np.stack(cube["matrix"],axis=0),
          "number_change_counts":np.stack(cube["number"],axis=0),
        }
        steps=len(metadata["drawid"])
        assert arrays["count_state"].shape==(steps,NR,NB)
        assert arrays["rank_state"].shape==(steps,NR,NB)
        assert arrays["pool_state"].shape==(steps,NR,NB)
        assert arrays["ring_change_counts"].shape==(steps,NR,len(RING_METRICS))
        assert arrays["five_by_five_transition"].shape==(steps,NR,5,5)
        assert arrays["number_change_counts"].shape==(steps,NB,len(BALL_METRICS))
        content=npz_bytes(**arrays)
        path=f"FULL_EACH_STEP_BY_DAY/{day}.npz"
        z.writestr(path,content,compress_type=zipfile.ZIP_STORED)
        per_file.append(dict(date=day,file=path,steps=steps,
            first_draw_id=metadata["drawid"][0],
            last_draw_id=metadata["drawid"][-1],
            size_zip_bytes=len(content)))
        print("V126 SAVED",day,steps,"steps",round(len(content)/1048576,2),"MiB",flush=True)
        for k in cube:cube[k].clear()
        metadata["drawid"].clear()

    dest=Path(out);dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,"w",allowZip64=True,compression=zipfile.ZIP_DEFLATED,
                          compresslevel=6) as z:
        z.writestr("00_INITIAL_CONDITION_BEFORE_FIRST_DRAW.npz",
          npz_bytes(count_state=initial_count,rank_state=initial_rank,
                    pool_state=initial_pool,
                    before_target_id=rows[2687]["id"],
                    lengths=LENS),
          compress_type=zipfile.ZIP_STORED)
        cub=dict(count=[],rank=[],pool=[],draw=[],left=[],
                 ring=[],matrix=[],number=[])
        meta=dict(drawid=[])
        current_day=None
        for t in range(2688,n):
            day=rows[t]["day"]
            if current_day is None:current_day=day
            if day!=current_day:
                flush(z,current_day,cub,meta)
                current_day=day
            new_draw=X[t].astype(np.uint8)
            leaving=X[t-LENS].astype(np.uint8)
            assert leaving.shape==(NR,NB)
            # X[t] enters EACH ring; X[t-L] leaves only that L-ring.
            enter=new_draw[None,:]
            delta=enter.astype(np.int16)-leaving.astype(np.int16)
            newc=(prevc.astype(np.int32)+delta).astype(np.uint16)
            assert np.all(newc.sum(axis=1)==20*LENS)
            rank,pool=ranks_and_pools(newc)
            rank_shift=rank.astype(np.int16)-prevr.astype(np.int16)
            pool_shift=pool.astype(np.int16)-prevp.astype(np.int16)
            cup=delta>0
            cdown=delta<0
            rup=rank_shift>0
            rdown=rank_shift<0
            pup=pool_shift>0
            pdown=pool_shift<0
            add_only=(enter==1)&(leaving==0)
            remove_only=(enter==0)&(leaving==1)
            both=(enter==1)&(leaving==1)
            # Up/down counts and exact counts/old rank/pool are recoverable.
            metrics=np.stack([
               cup.sum(axis=1),cdown.sum(axis=1),(delta==0).sum(axis=1),
               rup.sum(axis=1),rdown.sum(axis=1),(rank_shift==0).sum(axis=1),
               pup.sum(axis=1),pdown.sum(axis=1),(pool_shift==0).sum(axis=1),
               add_only.sum(axis=1),remove_only.sum(axis=1),
               both.sum(axis=1)],axis=1).astype(np.uint8)
            assert metrics.shape==(NR,len(RING_METRICS))
            assert np.array_equal(metrics[:,0],metrics[:,9])
            assert np.array_equal(metrics[:,1],metrics[:,10])
            assert np.all(metrics[:,6]+metrics[:,7]+metrics[:,8]==80)
            assert np.all(metrics[:,3]+metrics[:,4]+metrics[:,5]==80)
            assert np.all(metrics[:,0]+metrics[:,1]+metrics[:,2]==80)
            assert np.all(metrics[:,9]+metrics[:,11]==20)
            # 5×5 destination class flow, exact counts 80/ring.
            group_indices=(np.arange(NR,dtype=np.int32)[:,None]*25
                 +prevp.astype(np.int32)*5+pool.astype(np.int32)).ravel()
            transitions=np.bincount(group_indices,
                    minlength=NR*25).reshape(NR,5,5).astype(np.uint8)
            assert (transitions.sum(axis=(1,2))==80).all()
            assert (transitions.sum(axis=2)==16).all()
            assert (transitions.sum(axis=1)==16).all()
            bchange=np.stack([
               cup.sum(axis=0),cdown.sum(axis=0),
               rup.sum(axis=0),rdown.sum(axis=0),
               pup.sum(axis=0),pdown.sum(axis=0),
               add_only.sum(axis=0),remove_only.sum(axis=0)
             ],axis=1).astype(np.uint16)
            assert bchange.shape==(NB,len(BALL_METRICS))
            assert (bchange<=NR).all()
            ball_ring_counters+=np.stack(
                 [cup,cdown,rup,rdown,pup,pdown,add_only,remove_only],
                 axis=2).astype(np.uint32)
            ring_counters+=metrics.astype(np.uint64)
            dayring[day]+=metrics.astype(np.uint32)
            class_matrix+=transitions.astype(np.uint64)
            total_new_movement+=int((pool!=prevp).sum())
            cub["count"].append(newc.copy())
            cub["rank"].append(rank.copy())
            cub["pool"].append(pool.copy())
            cub["draw"].append(np.packbits(new_draw).copy())
            cub["left"].append(np.packbits(leaving,axis=1).copy())
            cub["ring"].append(metrics.copy())
            cub["matrix"].append(transitions.copy())
            cub["number"].append(bchange.copy())
            offset=len(meta["drawid"])
            meta["drawid"].append(int(rows[t]["id"]))
            idxrows.append(dict(date=day,time=rows[t]["time"],
                target_draw_id=rows[t]["id"],
                day_npz_path=f"FULL_EACH_STEP_BY_DAY/{day}.npz",
                day_npz_index0=offset,
                global_step_no=t-2688+1))
            perstep={
                "date":day,"time":rows[t]["time"],"draw_id":rows[t]["id"],
                "step":t-2688+1,"all_ring_number_cells":NR*NB,
                "count_up_events":int(metrics[:,0].sum()),
                "count_down_events":int(metrics[:,1].sum()),
                "rank_warming_events":int(metrics[:,3].sum()),
                "rank_cooling_events":int(metrics[:,4].sum()),
                "temp_warming_events":int(metrics[:,6].sum()),
                "temp_cooling_events":int(metrics[:,7].sum()),
                "total_changed_pool_cells":int(metrics[:,6:8].sum()),
                "circles_with_any_temp_movement":int(np.count_nonzero(metrics[:,6:8].sum(axis=1))),
                "new_ball_outcomes":"-".join(map(str,np.flatnonzero(new_draw)+1))
            }
            step_summary.append(perstep)
            if t>=n-NRECENT:
                daily_recent.append((
                    t,prevc.copy(),prevr.copy(),prevp.copy(),
                    newc.copy(),rank.copy(),pool.copy(),
                    new_draw.copy(),leaving.copy()))
            prevc,prevr,prevp=newc,rank,pool
            if (t-2687)%1000==0:
                print("V126 STEP",t-2687,"of",total_steps,
                      "pool shifts",total_new_movement,flush=True)
        if meta["drawid"]:flush(z,current_day,cub,meta)
        assert sum(x["steps"] for x in per_file)==total_steps
        assert len(idxrows)==total_steps
        assert len(step_summary)==total_steps
        assert len(per_file)==len(set(rows[t]["day"] for t in range(2688,n)))
        assert int(class_matrix.sum())==total_steps*NR*NB
        assert int(ring_counters[:,6:8].sum())==total_new_movement

        ring_report=[]
        for r in range(NR):
            res=dict(circle=r+1,reference_draws=int(LENS[r]),
                steps=total_steps)
            res.update({key:int(ring_counters[r,k])
                        for k,key in enumerate(RING_METRICS)})
            res.update({f"OLD_{a}_NEW_{b}":int(class_matrix[r,a,b])
                        for a in range(5) for b in range(5)})
            res["avg_changed_pool_numbers_per_step"]=round(
                  float((ring_counters[r,6]+ring_counters[r,7])/total_steps),6)
            ring_report.append(res)
        dayringreport=[]
        for day in sorted(dayring):
            val=dayring[day]
            steps=sum(x["date"]==day for x in step_summary)
            for r in range(NR):
                d=dict(date=day,circle=r+1,reference_draws=int(LENS[r]),steps=steps)
                d.update({key:int(val[r,j]) for j,key in enumerate(RING_METRICS)})
                dayringreport.append(d)
        # 17,920 ring-number aggregate trajectories.
        number_atlas=[]
        for r in range(NR):
            for b in range(NB):
                d=dict(circle=r+1,reference_draws=int(LENS[r]),number=b+1,
                    last_count=int(prevc[r,b]),
                    last_rank0=int(prevr[r,b]),
                    last_pool=POOL_NAMES[int(prevp[r,b])],
                    replay_steps=total_steps)
                d.update({key:int(ball_ring_counters[r,b,k])
                          for k,key in enumerate(BALL_METRICS)})
                number_atlas.append(d)
        recent_details=[]
        for t,pc,pr,pp,nc,nr,npool,new_draw,leaving in daily_recent:
            for r in range(NR):
                for b in range(NB):
                    recent_details.append(human_event(t,rows,r,b,
                        pc,pr,pp,nc,nr,npool,new_draw,leaving))
        assert len(recent_details)==min(NRECENT,total_steps)*NR*NB
        # Fully readable complete per-step summaries.
        put_csv(z,"01_TUM_CEKILISLER_224_HALKA_GENEL_ADIM_OZET.csv",step_summary)
        put_csv(z,"02_HER_CEKILIS_TARIH_SAAT_NPZ_KAYIT_INDEKSI.csv",idxrows)
        put_csv(z,"03_HER_HALKA_TOPLAM_KAC_YON_HAREKET_EDILDI.csv",ring_report)
        put_csv(z,"04_GUN_GUN_HER_224_HALKA_HAREKET_DOKUMU.csv",dayringreport)
        put_gz_csv(z,"05_HER_224_HALKA_80_SAYI_YON_HAREKET_ATLASI.csv.gz",number_atlas)
        put_gz_csv(z,"06_SON_12_CEKILIS_224x80_EKSIKSIZ_ADIM_DETAY.csv.gz",recent_details)
        manifest=dict(
          version="V126.1",source="veri.txt",source_draws=n,
          first_new_draw_id=rows[2688]["id"],
          final_observed_draw_id=rows[-1]["id"],
          observed_steps=total_steps,
          number_of_nested_circles=NR,numbers_per_ring=NB,
          full_number_ring_states_recorded=total_steps*NR*NB,
          state_values_per_cell=["count","rank0","pool0to4"],
          class_pool_size=16,
          every_previous_state_recoverable=True,
          total_pool_membership_change_events=total_new_movement,
          count_direction_minus1_0_plus1="X[t,ball]-X[t-L,ball]",
          rank_direction_sign="new_rank - old_rank",
          class_direction_sign="new_pool - old_pool",
          ring_change_metric_fields=list(RING_METRICS),
          number_change_metric_fields=list(BALL_METRICS),
          all_224_lengths=LENS.tolist(),
          class_names=list(POOL_NAMES),
          days_npz=per_file,
          read_with="v126_detay_oku.py --zip V126...zip --draw-id <id> --number <1..80> OR --ring <1..224>",
          generation_source="v126_224_halka_tum_sayilar_adim_adim_eksiksiz_kayit.py",
          source_repository_permanent=True,
          github_actions_artifact_retention_days=90,
          note="github zip expires 90d; regenerate deterministically from permanent repository script + veri.txt",
          no_family_features=True,
          no_prediction_claim=True,
          original_draw_records_used_directly=True)
        z.writestr("07_METOD_VE_GUN_BLOK_LISTESI.json",
                   json.dumps(manifest,ensure_ascii=False,indent=2))
        readable=[
          "V126 — 224 IC ICE HALKA / 80 SAYI / HER YENI CEKILIS ADIM ADIM KAYIT",
          f"Source draws: {n} from veri.txt. First replay draw #{rows[2688]['id']}.",
          f"Observed consecutive draws processed: {total_steps}.",
          f"Global snapshots: {total_steps} x 224 x 80 = "
                  f"{total_steps*NR*NB:,} number-window-time states.",
          f"Total temperature changes over entire replay: {total_new_movement:,}.",
          f"Block files: {len(per_file)} calendar days, every one losslessly stored.",
          "Every actual step: arrival 1/0, departure 1/0 per ring,",
          "old/new count, old/new ascending frequency rank,",
          "old/new pool class, 5x5 flow matrix, plus 224/80 summaries.",
          "Read individual cases with v126_detay_oku.py using draw-id and",
          "number or ring. All 224 ring views and all 80 numbers reconstructible.",
          "NOTE: Rank rising means rank becomes warmer relative to other balls.",
          "Frequency count unchanged CAN STILL mean class or rank shifted.",
          "IMPORTANT: Nested windows look back in time but rings do not",
          "represent 224 disjoint consecutive chronological 12-draw blocks.",
          "This describes actual changes after a result, not predictions.",
          "GitHub workflow artifacts EXPIRE after 90 days; the permanent",
          "source script can recompute all states from permanent veri.txt.",
          "",
          "Most active rings by average number of class changes per draw:"]
        top=sorted(ring_report,
          key=lambda z:(-z["avg_changed_pool_numbers_per_step"],z["circle"]))[:12]
        for x in top:
            readable.append(
              f" ring {x['circle']} L={x['reference_draws']}: "
              f"avg changed {x['avg_changed_pool_numbers_per_step']},"
              f" warmer={x['pool_warmer']},cooler={x['pool_colder']}")
        readable.extend(["","No winning coupon guarantee. No future target leakage."])
        z.writestr("00_KISA_TURKCE_KULLANIM_VE_SONUC.txt",
                    "\n".join(readable)+"\n")
    print("\n".join(readable),flush=True)
    print("V126 COMPLETE",dest,dest.stat().st_size,flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",default="veri.txt")
    ap.add_argument("--out",default="v126_output/V126_224_HALKA_80_SAYI_HER_ADIM_FULL_LOSSLESS.zip")
    x=ap.parse_args()
    main(x.source,x.out)
