#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V127: Do all 80 numbers in all 224 nested rings move the same way like a wave?

First principles for any number b and one new observed draw t:
Delta_count(t,L,b) = X(t,b)-X(t-L,b).
All rings see the SAME new bit X(t,b), so a drawn number's count can
only go +1 or 0 across rings; undrawn only -1 or 0 across rings.
Pool/rank movement can go in either direction due to relative ordering.

Quantify precisely across all t=2688..n-1, all 80, all 224 nested
lookbacks. Number-level cross-ring same-sign/mixed/no-motion,
adjacent ring direction agreement; day and per-number audits;
whether ring-wide warming vs cooling exists (fixed 16-per-pool
population prohibits moving ALL 80 the same pool direction).

An adjacency shuffle-of-ring-indices counterfactual is for
DESCRIPTIVE clustering only, NOT a fair-draw predictive baseline.
"""
from __future__ import annotations
import argparse,collections,csv,gzip,io,json,zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load

R=224
B=80
LENS=np.arange(12,2689,12,dtype=np.int32)
STATES=("NO_POOL_MOVE","ONLY_WARM","ONLY_COOL","MIXED_WARM_COOL")
RANK_STATES=("NO_RANK_MOVE","ONLY_RANK_UP","ONLY_RANK_DOWN","MIXED_RANK")
COUNT_STATES=("NO_COUNT_CHANGE","ONLY_COUNT_UP","ONLY_COUNT_DOWN","MIXED_COUNT")
COMPARE_PAIRS=((1,2),(1,3),(1,6),(1,12),(1,56),(1,112),(1,168),(1,224),
               (2,3),(6,12),(56,112),(56,168),(56,224),(112,168),
               (112,224),(168,224))
BANDS=((0,56),(56,112),(112,168),(168,224))
assert len(LENS)==224 and LENS[-1]==2688

def ranks(count):
    order=np.argsort(count,axis=1,kind="stable")
    rank=np.empty((R,B),dtype=np.int16)
    rank[np.arange(R)[:,None],order]=np.arange(B,dtype=np.int16)
    return rank

def full_metrics(sign,with_flips=False):
    up=(sign>0).sum(axis=0).astype(np.int16)
    down=(sign<0).sum(axis=0).astype(np.int16)
    stable=(sign==0).sum(axis=0).astype(np.int16)
    cat=(up>0).astype(np.int8)+2*(down>0).astype(np.int8)
    # codes: 0 no; 1 warm only; 2 cool only; 3 mixed.
    # flip count among nonzero directions across all 224 rings, ignoring zeros:
    # An explicit tiny loop 80 numbers × small length per one target.
    flips=np.zeros(B,dtype=np.int16)
    segments=np.zeros(B,dtype=np.int16)
    if with_flips:
        for i in range(B):
            s=sign[:,i]
            ss=s[s!=0]
            if len(ss):
                changes=np.count_nonzero(ss[1:]!=ss[:-1])
                flips[i]=changes
                segments[i]=changes+1
    return up,down,stable,cat,flips,segments

def csv_put(z,path,records):
    if not records:return
    st=io.StringIO(newline="")
    writer=csv.DictWriter(st,fieldnames=list(records[0]))
    writer.writeheader();writer.writerows(records)
    z.writestr(path,st.getvalue().encode("utf-8-sig"),
               compress_type=zipfile.ZIP_DEFLATED)

def gz_csv_put(z,path,records):
    if not records:return
    st=io.BytesIO()
    with gzip.GzipFile(fileobj=st,mode="wb",mtime=0,compresslevel=6) as gz:
        f=io.TextIOWrapper(gz,encoding="utf-8-sig",newline="")
        writer=csv.DictWriter(f,fieldnames=list(records[0]))
        writer.writeheader();writer.writerows(records)
        f.flush();f.detach()
    z.writestr(path,st.getvalue(),compress_type=zipfile.ZIP_STORED)

def main(source,out):
    days,rows,X,issues,bad=load(source)
    n=len(X)
    assert len(rows)==n and n>2688
    assert np.all(X.sum(axis=1)==20)
    P=np.vstack((np.zeros((1,B),dtype=np.int32),
                  np.cumsum(X,axis=0,dtype=np.int32)))
    cnt=(P[2688][None,:]-P[2688-LENS]).astype(np.int32)
    prev_r=ranks(cnt)
    prev_p=prev_r//16
    assert np.all(np.bincount(prev_p.ravel(),minlength=5)==16*R)
    steps=n-2688
    cat_totals=np.zeros((3,4),dtype=np.uint64)  # count,rank,pool
    by_drawn=np.zeros((2,3,4),dtype=np.uint64)
    num_cat=np.zeros((B,3,4),dtype=np.uint32)
    # Total adjacent observed (not all 80 necessarily move) same/opposite:
    adjacent=np.zeros((3,3),dtype=np.uint64)  # same,opposite,zero-pair
    shuffle_expected_same=np.zeros(3,dtype=np.float64)
    shuffle_expected_opp=np.zeros(3,dtype=np.float64)
    pair_stat=np.zeros((len(COMPARE_PAIRS),3,4),dtype=np.uint64)
    # for bands record avg number of moved rings and mixed within one band
    bands=np.zeros((4,4),dtype=np.uint64) # none, onlyup, onlydown, mixed
    ring_step=np.zeros((R,4),dtype=np.uint64) # pool up/down/unchanged, both dirs
    daily=collections.defaultdict(lambda:np.zeros((3,4),dtype=np.uint32))
    day_band=collections.defaultdict(lambda:np.zeros((4,4),dtype=np.uint32))
    daily_detail=[]
    sample_records=[]
    final80=[]
    num_totals=np.zeros((B,4),dtype=np.uint64) # per pool direction count sum
    num_total_flips=np.zeros(B,dtype=np.uint64)
    temporal=np.zeros((3,4),dtype=np.uint64) # sign at consecutive t for SAME ring + number
    prev_signs=[None,None,None]
    for t in range(2688,n):
        day=rows[t]["day"];draw=rows[t]["id"]
        enter=X[t].astype(np.int16)
        leave=X[t-LENS].astype(np.int16)
        delta=enter[None,:]-leave
        assert ((delta>=0) | (enter[None,:]==0)).all()
        assert ((delta<=0) | (enter[None,:]==1)).all()
        assert np.all(delta[:,enter==1]>=0)
        assert np.all(delta[:,enter==0]<=0)
        assert not (np.any(delta>0,axis=0)&np.any(delta<0,axis=0)).any()
        newc=cnt+delta
        newr=ranks(newc)
        newp=newr//16
        assert np.all(np.bincount(newp.ravel(),minlength=5)==16*R)
        dsign=np.sign(delta).astype(np.int8)
        rsign=np.sign(newr-prev_r).astype(np.int8)
        psign=np.sign(newp-prev_p).astype(np.int8)
        assert (dsign.sum(axis=0)[enter==1]>=0).all()
        assert (dsign.sum(axis=0)[enter==0]<=0).all()
        for kind,sign in enumerate((dsign,rsign,psign)):
            up,down,stable,cat,flips,segments=full_metrics(sign,with_flips=(kind==2))
            cat_totals[kind]+=np.bincount(cat,minlength=4)
            by_drawn[0,kind]+=np.bincount(cat[enter==0],minlength=4)
            by_drawn[1,kind]+=np.bincount(cat[enter==1],minlength=4)
            assert int(np.bincount(cat,minlength=4).sum())==B
            for a in range(4):
                num_cat[:,kind,a]+=(cat==a).astype(np.uint32)
            num_total_flips+=flips if kind==2 else np.zeros(B,dtype=np.int16)
            if kind==2:
                num_totals[:,0]+=up
                num_totals[:,1]+=down
                num_totals[:,2]+=stable
                num_totals[:,3]+=(flips>0)
            s1=sign[:-1]
            s2=sign[1:]
            both=(s1!=0)&(s2!=0)
            same=int(np.count_nonzero(both&(s1==s2)))
            opposite=int(np.count_nonzero(both&(s1!=s2)))
            adjacent[kind]+=(same,opposite,int(both.sum()))
            shuffle_expected_same[kind]+=float(np.sum(up*(up-1)+down*(down-1))/R)
            shuffle_expected_opp[kind]+=float(np.sum(2*up*down)/R)
            for p,(u,v) in enumerate(COMPARE_PAIRS):
                x=sign[u-1]
                y=sign[v-1]
                bothm=(x!=0)&(y!=0)
                pair_stat[p,kind,0]+=int(bothm.sum())
                pair_stat[p,kind,1]+=int(np.count_nonzero(bothm&(x==y)))
                pair_stat[p,kind,2]+=int(np.count_nonzero(bothm&(x!=y)))
                pair_stat[p,kind,3]+=int(np.count_nonzero(x==y))
            if prev_signs[kind] is not None:
                old=prev_signs[kind]
                bb=(sign!=0)&(old!=0)
                temporal[kind,0]+=int(bb.sum())
                temporal[kind,1]+=int(np.count_nonzero(bb&(old==sign)))
                temporal[kind,2]+=int(np.count_nonzero(bb&(old!=sign)))
                temporal[kind,3]+=int(np.count_nonzero(sign==old))
            prev_signs[kind]=sign.copy()
            daily[day][kind]+=np.bincount(cat,minlength=4).astype(np.uint32)
            if kind==2:
                moved=up+down
                for j,(i,k) in enumerate(BANDS):
                    a=(sign[i:k]>0).sum(axis=0)
                    b=(sign[i:k]<0).sum(axis=0)
                    c=(a>0).astype(np.int8)+2*(b>0).astype(np.int8)
                    bands[j]+=np.bincount(c,minlength=4)
                    day_band[day][j]+=np.bincount(c,minlength=4).astype(np.uint32)
                ring_up=(sign>0).sum(axis=1)
                ring_down=(sign<0).sum(axis=1)
                ring_step[:,0]+=ring_up
                ring_step[:,1]+=ring_down
                ring_step[:,2]+=(80-ring_up-ring_down)
                ring_step[:,3]+=(ring_up>0)&(ring_down>0)
                assert np.array_equal(ring_up==0,ring_down==0)
                assert np.all(ring_up+ring_down<=80)
                if t==n-1 or t>=n-12:
                    for ball in range(B):
                        if t==n-1:
                            final80.append(dict(number=ball+1,
                                draw_id=draw,date=day,
                                new_target_drawn=int(enter[ball]),
                                count_total_up=int((dsign[:,ball]>0).sum()),
                                count_total_down=int((dsign[:,ball]<0).sum()),
                                rank_total_up=int((rsign[:,ball]>0).sum()),
                                rank_total_down=int((rsign[:,ball]<0).sum()),
                                temp_total_up=int(up[ball]),
                                temp_total_down=int(down[ball]),
                                temp_nochange=int(stable[ball]),
                                temp_category=STATES[int(cat[ball])],
                                temp_flip_count_ignoring_stable=int(flips[ball]),
                                per_224_ring_temp_signs="".join("C0W"[int(y)+1] for y in sign[:,ball]),
                                per_224_ring_pool_before="".join(str(int(y)) for y in prev_p[:,ball]),
                                per_224_ring_pool_after="".join(str(int(y)) for y in newp[:,ball])))
                        sample_records.append(dict(draw_id=draw,date=day,
                          number=ball+1,drawn_1_0=int(enter[ball]),
                          up_rings=int(up[ball]),down_rings=int(down[ball]),
                          still_rings=int(stable[ball]),
                          class_=STATES[int(cat[ball])],
                          sign_changes_ignoring_stable=int(flips[ball]),
                          ring_224_pool_motion="".join("C0W"[int(y)+1] for y in sign[:,ball])))
        cnt=newc
        prev_r=newr
        prev_p=newp
        if (t-2687)%2500==0:
            print("V127 processed",t-2687,"/",steps,flush=True)
    assert int(cat_totals[0,3])==0,"count mixed must be mathematically impossible"
    assert int(cat_totals[2].sum())==steps*B
    assert int(ring_step[:,0].sum()+ring_step[:,1].sum()+ring_step[:,2].sum())==steps*R*B
    assert np.all(ring_step[:,3]<=steps)
    assert int(sum(cat_totals[2]))==steps*80
    day_rows=[]
    for day in sorted(daily):
        for typ in range(3):
            d=daily[day][typ]
            day_rows.append(dict(day=day,kind=("COUNT","RANK","POOL")[typ],
                num_step_obs=int(d.sum()),none=int(d[0]),
                only_up=int(d[1]),only_down=int(d[2]),mixed=int(d[3])))
    ball_rows=[]
    for b in range(B):
        d=num_cat[b,2]
        ball_rows.append(dict(number=b+1,
            historical_step_count=steps,pool_none=int(d[0]),
            pool_only_up=int(d[1]),pool_only_down=int(d[2]),
            pool_mixed=int(d[3]),
            count_mixed=int(num_cat[b,0,3]),
            rank_mixed=int(num_cat[b,1,3]),
            total_pool_up_ring_events=int(num_totals[b,0]),
            total_pool_down_ring_events=int(num_totals[b,1]),
            total_pool_still_ring_events=int(num_totals[b,2]),
            total_cross_ring_sign_flips=int(num_total_flips[b]),
            percent_pool_mixed=round(100*d[3]/steps,5)))
    pairs=[]
    for k,(a,b) in enumerate(COMPARE_PAIRS):
        for kind in range(3):
            o=pair_stat[k,kind]
            pairs.append(dict(ring_a=a,draw_window_a=12*a,
                ring_b=b,draw_window_b=12*b,
                kind=("COUNT","RANK","POOL")[kind],
                total_number_step_pairs=steps*B,
                both_move=int(o[0]),both_same_dir=int(o[1]),
                both_opposite_dir=int(o[2]),
                same_sign_including_zero=int(o[3]),
                same_among_both_moved_pct=round(100*o[1]/o[0],6)
                    if o[0] else None))
    band_rows=[]
    for j,(a,b) in enumerate(BANDS):
        q=bands[j]
        band_rows.append(dict(band=j+1,ring_first=a+1,ring_last=b,
            draw_window_start=12*(a+1),draw_window_end=12*b,
            ball_step_obs=steps*B,never_moved=int(q[0]),
            only_up=int(q[1]),only_down=int(q[2]),mixed=int(q[3]),
            percent_mixed=round(100*q[3]/(steps*B),6)))
    ring_rows=[]
    for i in range(R):
        x=ring_step[i]
        ring_rows.append(dict(ring=i+1,window_draws=int(LENS[i]),
           target_steps=steps,number_step_obs=steps*B,
           temp_warm_events=int(x[0]),temp_cool_events=int(x[1]),
           temp_still_events=int(x[2]),
           number_of_steps_with_both_warm_and_cool=int(x[3]),
           number_of_steps_with_any_pool_shift=int(x[3]),
           avg_number_pool_shifts_per_step=round(float((x[0]+x[1])/steps),7)))
    summary=[]
    for kind in range(3):
        q=cat_totals[kind]
        same=int(adjacent[kind,0])
        opposite=int(adjacent[kind,1])
        both=int(adjacent[kind,2])
        summary.append(dict(kind=("COUNT","RANK","POOL")[kind],
            ball_steps=steps*B,never_moved=int(q[0]),
            only_up=int(q[1]),only_down=int(q[2]),mixed=int(q[3]),
            nochange_pct=round(100*q[0]/q.sum(),6),
            one_direction_pct=round(100*(q[1]+q[2])/q.sum(),6),
            mixed_direction_pct=round(100*q[3]/q.sum(),6),
            moved_any_pct=round(100*(q[1]+q[2]+q[3])/q.sum(),6),
            adjacent_both_changed=int(both),adjacent_same=int(same),
            adjacent_opposite=int(opposite),
            conditional_adjacent_agreement_pct=
              round(100*same/both,6) if both else None,
            shuffle_numberwise_adjacent_same_expected=round(float(shuffle_expected_same[kind]),2),
            shuffle_numberwise_adjacent_opposite_expected=round(float(shuffle_expected_opp[kind]),2),
            actual_vs_shuffled_expected_same_ratio=
              round(same/shuffle_expected_same[kind],4)
                 if shuffle_expected_same[kind] else None,
            consecutive_draw_same_ring_both_moved=int(temporal[kind,0]),
            consecutive_draw_same_dir=int(temporal[kind,1]),
            consecutive_draw_opposite=int(temporal[kind,2]),
            consecutive_draw_same_dir_pct=
              round(100*temporal[kind,1]/temporal[kind,0],5)
              if temporal[kind,0] else None))
    drawn_report=[]
    for outcome in (0,1):
        for kind in range(3):
            q=by_drawn[outcome,kind]
            drawn_report.append(dict(drawn_1_0=outcome,
                kind=("COUNT","RANK","POOL")[kind],
                number_step_obs=int(q.sum()),never_moved=int(q[0]),
                only_up=int(q[1]),only_down=int(q[2]),mixed=int(q[3]),
                mixed_pct=round(100*q[3]/q.sum(),5)))
    # exact full count geometry cross rings.
    notes=[
      "V127 — 224 nested circles are NOT a single directional temperature wave.",
      f"Real draw target steps: {steps}; each step 224 rings x 80 numbers.",
      f"Source latest draw {rows[-1]['id']} on {rows[-1]['day']}.",
      f"Number×step samples: {steps*B:,}; each has 224 simultaneous ring transitions.",
      "CRITICAL COUNT MATH: if new result contains ball b, all ring deltas",
      "are +1 or 0. If missing ball b, deltas are -1 or 0.",
      "For a number, opposite COUNT directions ACROSS rings are IMPOSSIBLE.",
      "The exact relationship is delta(t,L,b)=X[t,b]-X[t-L,b].",
      "The above is structural and offers NO advance knowledge of X[t,b].",
      "Relative RANK and temperature POOL directions need not agree across rings.",
      "With 16 members in each of five fixed pools, it is impossible",
      "for all 80 numbers in a single ring to move WARM or COOL together.",
      "Rings simultaneously contain warmers and coolers when ANY class shifts.",
      "",
      "NUMBER-STEP 224-RING DIRECTION CATEGORIES: individual number on a target",
      "(NO change, ONLY warming, ONLY cooling, BOTH warmer and cooler rings):"]
    for x in summary:
        notes.append(f"{x['kind']}: none={x['never_moved']:,} "
           f"only_up={x['only_up']:,} only_down={x['only_down']:,} "
           f"MIXED={x['mixed']:,} "
           f"MIXED_RATE={x['mixed_direction_pct']:.4f}%")
        notes.append(f"  Adjacent rings, among pairs with both moving: "
           f"same={x['adjacent_same']:,} opposite={x['adjacent_opposite']:,}, "
           f"same_pct={x['conditional_adjacent_agreement_pct']}%. "
           f"Random permutation of ring order expects "
           f"{x['shuffle_numberwise_adjacent_same_expected']:,.0f} "
           f"same-direction neighbor pairs; ratio="
           f"{x['actual_vs_shuffled_expected_same_ratio']}.")
    notes.append("")
    notes.append("TEMP-POOL crossed 56-ring BANDS within the same step-number:")
    for x in band_rows:
        notes.append(f" ring {x['ring_first']}–{x['ring_last']}: "
            f"mixed={x['mixed']:,} ({x['percent_mixed']:.3f}%),"
            f" onlyup={x['only_up']:,}, onlydown={x['only_down']:,},"
            f" stable_all={x['never_moved']:,}.")
    notes.append("")
    notes.append("SAME-STEP POOL DIRECTIONS FOR SELECTED RING PAIRS:")
    for x in pairs:
        if x["kind"]=="POOL":
            notes.append(f" {x['ring_a']}/{x['ring_b']} "
               f"(L{x['draw_window_a']}/L{x['draw_window_b']}):"
               f" when both moved {x['both_move']:,},"
               f" same={x['both_same_dir']:,},"
               f" opposite={x['both_opposite_dir']:,},"
               f" same%={x['same_among_both_moved_pct']}")
    notes.append("")
    for x in drawn_report:
        if x["kind"]=="POOL":
            notes.append(f"Actual newly {'DRAWN' if x['drawn_1_0'] else 'UNDRAWN'} "
              f"numbers' POOL directions: "
              f"mixed {x['mixed']:,} of {x['number_step_obs']:,} "
              f"({x['mixed_pct']}%).")
    notes.append("")
    notes.append("Wave clustering within adjacent nested rings is mechanical:")
    notes.append("the windows overlap massively; co-moving does NOT imply")
    notes.append("future RNG can be predicted or that winning chances rise.")
    notes.append("All values describe the instant AFTER each known result.")
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,
         compresslevel=6,allowZip64=True) as z:
        z.writestr("00_V127_TURKCE_DALGA_SENKRON_GERCEK_SONUC.txt",
                "\n".join(notes)+"\n")
        csv_put(z,"01_224_RING_SAYI_HAREKET_TIPLERI_TOPLAM.csv",summary)
        csv_put(z,"02_CIKAN_CIKMAYAN_SAYI_AYRI_DALGA_YONLERI.csv",drawn_report)
        csv_put(z,"03_HALKALAR_ARASI_ESZAMANLI_HAREKET_ESLESMESI.csv",pairs)
        csv_put(z,"04_DORT_56_HALKA_BANT_ICI_DALGA_SENKRON.csv",band_rows)
        csv_put(z,"05_HER_80_SAYI_TARIHSEL_224_HALKA_YON_KARISIKLIK.csv",ball_rows)
        csv_put(z,"06_HER_224_HALKA_ILIK_SOGUK_YON_COUNTER.csv",ring_rows)
        csv_put(z,"07_GUN_GUN_COUNT_RANK_POOL_DALGA_SAYIM.csv",day_rows)
        csv_put(z,"08_SON_HEDEF_80_SAYI_224_HALKA_YON_DESENLERI.csv",final80)
        csv_put(z,"09_SON_12_CEKILIS_80_SAYI_HALKA_DALGA_DESEN.csv",sample_records)
        z.writestr("10_DENETIM_VE_SONUC.json",
             json.dumps(dict(source_draws=n,first_target_id=rows[2688]["id"],
               last_id=rows[-1]["id"],targets=steps,
               total_number_target_units=steps*B,
               nested_ring_lengths=LENS.tolist(),disjoint12rings=False,
               counts_direction_never_mixed_proved=True,
               summary=summary,by_drawn=drawn_report,
               bands=band_rows,
               note="This is retrospective synchrony after new draw; not forward prediction."),
               ensure_ascii=False,indent=2))
    print("\n".join(notes),flush=True)
    print("V127 SUCCESS",out,out.stat().st_size,flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--source",default="veri.txt")
    a.add_argument("--out",default="v127_output/V127_224_HALKA_SAYILAR_AYNI_YON_DALGA_TEST.zip")
    o=a.parse_args()
    main(o.source,o.out)
