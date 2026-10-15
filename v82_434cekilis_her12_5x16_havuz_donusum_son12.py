#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V82: exact 434 consecutive draw (~two day) history -> five heat ranks of 16.
Every 12 draws trace 80 numerical identities old 16-group -> new group.
Study last 12 draws of each consecutive two-full-day window, notably
11–12 Oct 2026, both rank-identity movement and actual 1/0 target hits.

Every pool snapshot at draw boundary t uses only draws [t-434,t).
For each 434-draw PAIR, sample at offsets 2,14,...,422,434:
36 exact twelve-draw steps; the initial two draws are a preface.
The final twelve are offsets 422 through 433, with from-state
at offset 422 and to-state at offset 434. The latter is POST-last12,
so cannot be used to select the last12 coupon beforehand.
At each last12 target t, contemporaneous pre-target N434 and pre-target
t-12 groups are available for honest target 1/0 tabulation.

Adjacent day pair windows overlap, so do not treat observed movements as
independent predictive evidence. IDs must be uninterrupted for the 434
prior history and entire 434 following drawing period.
"""
from __future__ import annotations
import argparse, collections, csv, gzip, io, json, zipfile
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VER="V82.1"
N=434
DAY=217
TOTAL=72
STEPS=36
OFFSETS=(0,)+tuple(2+12*i for i in range(37))
assert OFFSETS[-1]==434 and OFFSETS[-2]==422
LABELS=("SOGUK","SERIN","NOTR","ILIK","SICAK")
VECTORS=("SOGUYOR","SABIT","ISINIYOR")

def load(path):
    all_days,errors,malformed=parse_txt(path)
    full=sorted(d for d,rec in all_days.items()
                if len(rec)==DAY and [a["pos"] for a in rec]==list(range(1,DAY+1)))
    if len(full)!=72 or full[0]!="2026-08-01" or full[-1]!="2026-10-12":
        raise RuntimeError(f"Need 72 fully collected days, found {len(full)}")
    rows=[rec for d in full for rec in all_days[d]]
    if len(rows)!=15624 or rows[-1]["id"]!=61845:
        raise RuntimeError("Expected complete draw boundary 61845")
    y=np.zeros((len(rows),80),dtype=np.uint8)
    for i,rec in enumerate(rows):
        y[i,np.asarray(rec["nums"],dtype=int)-1]=1
    assert np.all(y.sum(axis=1)==20)
    ids=np.array([a["id"] for a in rows],dtype=np.int32)
    return full,rows,y,ids,errors,malformed

def rank434(y,ids):
    """Stable previous rank to minimize arbitrary membership tie flips."""
    total=len(y)
    prefix=np.zeros((total+1,80),dtype=np.int32)
    prefix[1:]=np.cumsum(y,dtype=np.int32,axis=0)
    output=np.full((total+1,80),255,dtype=np.uint8)
    old=np.arange(80,dtype=np.int16)
    balls=np.arange(80,dtype=np.int16)
    # output[t] is the state immediately before draw t.
    # output[total] is the post-last-draw state, not available beforehand.
    for t in range(N,total+1):
        freq=prefix[t]-prefix[t-N]
        order=np.lexsort((old,freq))
        newrank=np.empty(80,dtype=np.uint8)
        newrank[order]=np.arange(80,dtype=np.uint8)
        output[t]=newrank
        old=newrank
    bad=np.r_[0,(np.diff(ids)!=1).astype(np.int32)]
    bad_prefix=np.r_[0,np.cumsum(bad)]
    def uninterrupted(start,stop):
        if start<0 or stop>total or stop<=start:return False
        return bad_prefix[stop]-bad_prefix[start+1]==0
    return prefix,output,uninterrupted

def history_pairs(full,rows,output,uninterrupted):
    pairs=[]
    excluded=collections.Counter()
    for day_idx in range(len(full)-1):
        st=day_idx*DAY
        end=st+N
        if end>len(rows):
            continue
        # IDs consecutive across the two complete actual calendar days.
        if not uninterrupted(st,end):
            excluded["two-day-pair-has-missing-draws"]+=1
            continue
        if not uninterrupted(st-N,end):
            excluded["insufficient-uninterrupted-prior434"]+=1
            continue
        if np.any(output[st]<80)==False or np.any(output[end]<80)==False:
            excluded["no-rank-initialized"]+=1
            continue
        pairs.append((st,end,full[day_idx],full[day_idx+1]))
    return pairs,excluded

def delta(a,b):
    return b.astype(np.int8)-a.astype(np.int8)

def streamcsv(z,path,header,rows,gzip_csv=False):
    with z.open(path,"w",force_zip64=True) as raw:
        if gzip_csv:
            with gzip.GzipFile(fileobj=raw,mode="wb",compresslevel=5) as gf:
                txt=io.TextIOWrapper(gf,encoding="utf-8",newline="")
                writer=csv.writer(txt);writer.writerow(header)
                writer.writerows(rows)
                txt.flush();txt.detach()
        else:
            txt=io.TextIOWrapper(raw,encoding="utf-8",newline="")
            writer=csv.writer(txt);writer.writerow(header)
            writer.writerows(rows)
            txt.flush();txt.detach()

def main(path,outpath):
    full,rows,y,ids,errors,malformed=load(path)
    p,rank,ok=rank434(y,ids)
    pairs,excluded=history_pairs(full,rows,rank,ok)
    if not pairs or pairs[-1][2:]!=("2026-10-11","2026-10-12"):
        raise RuntimeError(f"Expected Oct11–12 last pair: {pairs[-2:]}")
    all_steps=collections.Counter()
    each_step=[]
    all_final12=collections.Counter()
    historical_last12_numbers=collections.defaultdict(lambda:[0,0,0])
    historical_pretarget=collections.defaultdict(lambda:[0,0])
    daypairs=[]
    last_examples=[]
    transitions_latest=[]
    states_last=np.zeros((len(OFFSETS),80),dtype=np.uint8)
    ranks_last=np.zeros((len(OFFSETS),80),dtype=np.uint8)
    latest=None
    total_events=0
    for index,(start,end,d0,d1) in enumerate(pairs):
        absolute=[start+o for o in OFFSETS]
        tiers=(rank[absolute]//16).astype(np.uint8)
        assert np.all(np.bincount(tiers[0],minlength=5)==[16]*5)
        assert np.all(np.bincount(tiers[-1],minlength=5)==[16]*5)
        is_latest=index==len(pairs)-1
        if is_latest:
            latest=(start,end,d0,d1)
            ranks_last=rank[absolute]
            states_last=tiers
        all_twelve_movers=0
        for step in range(1,len(OFFSETS)):
            length=OFFSETS[step]-OFFSETS[step-1]
            if length!=12:
                continue
            before=tiers[step-1]
            after=tiers[step]
            mat=np.zeros((5,5),dtype=np.int32)
            moved=0
            for a in range(5):
                for b in range(5):
                    n=int(np.sum((before==a)&(after==b)))
                    all_steps[length,a,b]+=n
                    mat[a,b]=n
                    if a!=b:moved+=n
            all_twelve_movers+=moved
            if is_latest:
                every={"pair_first":d0,"pair_second":d1,
                  "checkpoint_from_offset":OFFSETS[step-1],
                  "checkpoint_to_offset":OFFSETS[step],
                  "from_draw_id":rows[start+OFFSETS[step-1]]["id"],
                  "until_draw_id_inclusive":rows[start+OFFSETS[step]-1]["id"],
                  "moved_number_count":moved}
                for a in range(5):
                    every[f"out_of_{LABELS[a].lower()}"]=int(np.sum((before==a)&(after!=a)))
                    every[f"into_{LABELS[a].lower()}"]=int(np.sum((before!=a)&(after==a)))
                    every[f"stayed_{LABELS[a].lower()}"]=int(mat[a,a])
                each_step.append(every)
        # exactly latest 12 in this pair (422..434), no peeking into next draw
        from_tier=tiers[-2]
        to_tier=tiers[-1]  # POST 12 actual drawings, for retrospective movement
        last12=y[end-12:end].sum(axis=0,dtype=np.int32)
        count_moves=int((from_tier!=to_tier).sum())
        move_up=int((from_tier<to_tier).sum())
        move_down=int((from_tier>to_tier).sum())
        daypairs.append(dict(day1=d0,day2=d1,
            last12_start_no=rows[end-12]["id"],
            last12_end_no=rows[end-1]["id"],
            all_step_movers=all_twelve_movers,
            mean_movers_per_12=round(all_twelve_movers/36,5),
            final12_moved=count_moves,final12_warmed=move_up,
            final12_cooled=move_down,final12_stable=80-count_moves,
            last12_drawn_events=int(last12.sum()),
            last12_unique_numbers=int((last12>0).sum())))
        for number in range(80):
            a=int(from_tier[number]);b=int(to_tier[number])
            draws=int(last12[number])
            all_final12[a,b]+=1
            historical_last12_numbers[a,b][0]+=1
            historical_last12_numbers[a,b][1]+=draws
            historical_last12_numbers[a,b][2]+=int(draws>0)
            if is_latest:
                transitions_latest.append(dict(number=number+1,
                    pool_before_final12=LABELS[a],
                    within_rank_before_final12=int(ranks_last[-2,number]%16+1),
                    pool_after_final12=LABELS[b],
                    within_rank_after_final12=int(ranks_last[-1,number]%16+1),
                    direction=("ISINIYOR" if b>a else "SOGUYOR" if b<a else "SABIT"),
                    pool_steps_change=b-a,
                    times_drawn_in_final12=draws,
                    appeared_at_least_once=int(draws>0)))
        # Before each actual drawing, tier/heat movement over prior 12
        # is ALREADY KNOWN; target hit is revealed only afterward.
        for t in range(end-12,end):
            current=rank[t]//16
            historical=rank[t-12]//16
            for n in range(80):
                src=int(historical[n]);dst=int(current[n])
                historical_pretarget[src,dst][0]+=1
                historical_pretarget[src,dst][1]+=int(y[t,n])
                total_events+=int(y[t,n])
    last=(latest[0],latest[1])
    latest_start,latest_end=last
    assert latest_end-latest_start==434
    assert latest_end==len(rows)
    assert total_events==len(pairs)*12*20
    path80=[]
    for n in range(80):
        number=n+1
        gr=[LABELS[int(states_last[j,n])] for j in range(1,len(OFFSETS))]
        positions=[int(ranks_last[j,n]%16+1) for j in range(1,len(OFFSETS))]
        moved_steps=sum(gr[k]!=gr[k-1] for k in range(1,37))
        path80.append(dict(
            number=number,start_pool_434_before=LABELS[int((rank[latest_start]//16)[n])],
            first_checkpoint_after_two_draws=gr[0],
            at_last12_start=gr[-2],pos_before12=positions[-2],
            after_final12=gr[-1],pos_after12=positions[-1],
            moved_across_36_12draw_steps=moved_steps,
            movement_path_36_checkpoints=" → ".join(gr),
            within16_positions_36_checkpoints=",".join(map(str,positions))))
    # Last 12 actual targets: source tier, 12-pre-target tier, 5x16 20 hits,
    # number identities and movement are known before target. No forward leak.
    latest_last12=[]
    last12_identities=[]
    for t in range(latest_end-12,latest_end):
        current=rank[t]//16
        previous12=rank[t-12]//16
        yt=y[t]
        one=dict(date=rows[t]["day"],clock=rows[t]["time"],
            draw_id=rows[t]["id"],slot=rows[t]["pos"],
            drawn20=",".join(map(str,np.flatnonzero(yt)+1)))
        for a in range(5):
            members=np.flatnonzero((current==a))
            actual=np.flatnonzero((current==a)&(yt==1))
            assert len(members)==16
            one[f"pretarget_{LABELS[a].lower()}_16"]=",".join(map(str,members+1))
            one[f"pretarget_{LABELS[a].lower()}_hits"]=len(actual)
            one[f"pretarget_{LABELS[a].lower()}_hit_balls"]=",".join(map(str,actual+1))
        latest_last12.append(one)
        for i in range(80):
            older=int(previous12[i]);now=int(current[i])
            last12_identities.append([
                rows[t]["day"],rows[t]["time"],rows[t]["id"],i+1,
                LABELS[older],LABELS[now],
                now-older,"ISINIYOR" if now>older else "SOGUYOR" if now<older else "SABIT",
                int(rank[t,i]%16)+1,int(yt[i])])
    histsteps=[]
    for a in range(5):
        for b in range(5):
            ct=all_steps[12,a,b]
            if ct:
                histsteps.append(dict(from_pool=LABELS[a],to_pool=LABELS[b],
                    identity_movement_count=int(ct),
                    from_pool_rate_pct=round(100*ct/(16*len(pairs)*36),5)))
    last12_summary=[]
    last12_events=[]
    for a in range(5):
        for b in range(5):
            n,h,unique=historical_last12_numbers[a,b]
            if n:
                last12_summary.append(dict(previous_pool=LABELS[a],
                  after_last12_pool=LABELS[b],
                  number_instances=n,appearances_in_twelve_drawings=h,
                  identities_appeared_at_least_once=unique,
                  average_12draw_appearances_per_number=round(h/n,5),
                  once_or_more_pct=round(100*unique/n,5),
                  sample_expected_under_rng_12draws=3.))
            observed_one=historical_pretarget[a,b][1]
            opportunity=historical_pretarget[a,b][0]
            if opportunity:
                last12_events.append(dict(
                  twelve_before_pool=LABELS[a],
                  current_pretarget_pool=LABELS[b],
                  opportunity=opportunity,
                  drawn1=int(observed_one),
                  not_drawn0=int(opportunity-observed_one),
                  actual_1_pct=round(100*observed_one/opportunity,6),
                  fair_1_pct=25.0))
    latest_last12_counts=y[latest_end-12:latest_end].sum(axis=0,dtype=np.int32)
    latest_agg={"changed":int(np.sum(states_last[-1]!=states_last[-2])),
        "warming":int(np.sum(states_last[-1]>states_last[-2])),
        "cooling":int(np.sum(states_last[-1]<states_last[-2])),
        "stable":int(np.sum(states_last[-1]==states_last[-2]))}
    changed_numbers=[
        dict(n=x["number"],from_pool=x["pool_before_final12"],
             to_pool=x["pool_after_final12"],delta=x["pool_steps_change"],
             drawn12=x["times_drawn_in_final12"])
        for x in transitions_latest if x["pool_steps_change"]!=0
    ]
    target_12_heat={pool:sum(int(row[f"pretarget_{pool.lower()}_hits"]) for row in latest_last12)
                     for pool in LABELS}
    # Latest pair checkpoint details by exact ISO date, no single step through absent data.
    summary=[
       "V82 — 2 GUNLUK 434 CEKILIS; HER 12 CEKILISTE 5x16 HAVUZUN YOLU",
       "IMPORTANT: 434 = 2 + (36 x 12). Before-pair state at offset 0;",
       "checkpoints at 2,14,26,...,422,434, so last segment is EXACTLY 12.",
       "Every time t, appearance ranks from PREVIOUS 434 real drawings;",
       "5 tiers hold exactly 16 numbers each; tie breaks favor previous rank.",
       "All movement paths are retrospective. State at offset434 uses the",
       "final 12 draws, so is NOT known at offset422 when prediction is due.",
       f"Full days={len(full)} draws={len(rows)}; "
       f"valid consecutive day pairs with 434 continuous earlier draws={len(pairs)}.",
       f"Pairs excluded by data continuity: {dict(excluded)}.",
       f"Last complete 434-draw pair: {latest[2]} -> {latest[3]}.",
       f"Most recent final twelve drawing IDs: "
       f"{rows[latest_end-12]['id']} .. {rows[latest_end-1]['id']}.",
       f"Last twelve POST-movement among 80 identities: "
       f"{latest_agg['changed']} changed, "
       f"{latest_agg['warming']} warming, "
       f"{latest_agg['cooling']} cooling, "
       f"{latest_agg['stable']} stayed.",
       "LAST TWELVE MOVERS: true origin pool -> destination AFTER final12:",
    ]
    for it in changed_numbers:
        summary.append(f"   #{it['n']:>2} {it['from_pool']:7} -> "
           f"{it['to_pool']:7} (move={it['delta']:+d}, "
           f"drawn {it['drawn12']}/12 times)")
    summary+=["","LAST TWELVE actual 20-per-target hits FROM PRE-TARGET heat:",
             "Every 12 targets contains 240 actual drawn-ball events."]
    for lab in LABELS:
        summary.append(f"   {lab}: {target_12_heat[lab]} total target1 events "
                       f"over 12 draws (fair expectation 48).")
    totalsteps=len(pairs)*36
    moved_hist=sum(v for (_,a,b),v in all_steps.items() if a!=b)
    summary+=["",
       f"ALL 434-DRAW PAIRS: {totalsteps} historical 12-draw transition steps, "
       f"{moved_hist} changing-number events, "
       f"mean={moved_hist/totalsteps:.5f}/80 per twelve-draw step.",
       "Sample windows overlap, so their state changes are correlated.",
       "",
       "FOR COUPONS USE ONLY BEFORE-DRAW STATES: the exported 12-target",
       "5x5 source-to-current transition target1/target0 table is available.",
       "Never use after-final12 destinations to predict inside that same block.",
       "Expected target hit chance per number for a fair independent 20/80",
       "lottery remains exactly 25%; no predictive superiority is established.",
       "Main output includes the EXACT last pair 80-ball 36-step paths;",
       "latest 12 draw results and before/after states; full historical 5x5",
       "movement matrices, 1/0 conditional rates and audit.",
    ]
    out=Path(outpath);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=5,allowZip64=True) as z:
        z.writestr("00_OZET_V82.txt","\n".join(summary))
        def dic(name,rec):
            streamcsv(z,name,rec[0].keys(),(list(row.values()) for row in rec))
        dic("01_EKIM11_12_80SAYI_36ADIM_434_YOLCULUK.csv",path80)
        dic("02_EKIM11_12_HER12_HAVUZ_GIRIS_CIKIS.csv",each_step)
        dic("03_EKIM12_SON12_HER_SAYI_NERDEN_NEREYE.csv",transitions_latest)
        dic("04_EKIM12_SON12_CEKILIS_CEKILIS_5X16_HEDEF_1.csv",latest_last12)
        streamcsv(z,"05_EKIM12_SON12_HEDEF_CEKILIS_80SAYI_ESKI_YENI_1_0.csv",
          ["date","clock","draw_id","number","pool_12_drawing_ago",
           "current_pool_before_target","movement_steps","direction",
           "position_inside_16","target_drawn_1_or_0"],last12_identities)
        dic("06_72GUN_TUM_GECERLI_IKI_GUN_12CEKILIS_HAREKET.csv",daypairs)
        dic("07_TUM_CIFT_GUNLERIN_36ADIM_5X5_HAVUZ_GECISLERI.csv",histsteps)
        dic("08_TUM_2GUN_PENCERELERINDE_SON12_NERDEN_NEREYE.csv",last12_summary)
        dic("09_SON12_PENCERELERINDE_HEDEF_ONCESI_YON_HEDEF_1_0.csv",last12_events)
        streamcsv(z,"10_EKIM11_12_SON12_HAREKET_EDENLER.txt",
          ["number","before_pool","after_pool","change","hits_in_final_12"],
          ([x["n"],x["from_pool"],x["to_pool"],x["delta"],x["drawn12"]]
           for x in changed_numbers))
        z.writestr("11_VERI_KALITESI_VE_YONTEM.txt","\n".join([
          "Two days = 217+217=434 consecutive real draws.",
          "A heat state at boundary t uses previous N434 draws only.",
          "Sort each number by count within [t-434,t), 5 groups of 16.",
          "Ties broken by number rank at previous boundary to reduce churn;",
          "ties are arbitrary memberships, not evidence of RNG machinery.",
          "Pair offset 0 is BEFORE first drawing of two-day block;",
          "offset 434 is AFTER its last drawing, before any later target.",
          "434 = 2 + 36*12, steps at 2,14,...,422,434.",
          "No fictitious 37th full twelve-step included.",
          "Last12 from-state offset422, to-state offset434; to-state",
          "contains their observed last12 results and cannot forecast them.",
          "Historical after-last12 pool changes are descriptive only.",
          "For real target hit assessment group at t and t-12 both depend",
          "only on draws earlier than target t, hence clean information.",
          "Daily pairs overlap (day1+day2 and day2+day3) and cannot",
          "be considered independent examples of a statistically proven edge.",
          "Pair requires continuous actual draw numbers throughout 434",
          "preceding the pair and all 434 drawings in the pair.",
          "Invalid Aug23 and partial Oct13 are excluded from full-day analysis."
        ]))
        z.writestr("12_AUDIT.json",json.dumps(dict(version=VER,
           complete_days=full,targets=len(y),N=N,
           checkpoint_offsets=OFFSETS,valid_two_day_pairs=len(pairs),
           omitted_by_continuity=dict(excluded),
           most_recent_pair=[latest[2],latest[3]],
           last_twelve_ids=[rows[latest_end-12]["id"],rows[latest_end-1]["id"]],
           latest_transition=latest_agg,
           latest_12_target1_by_pre_target_pool=target_12_heat,
           all_historical_twelve_steps=totalsteps,
           all_historical_12_step_changing_identities=moved_hist,
           avg_historical_12_step_changing_identities=moved_hist/totalsteps,
           invalid_lines=malformed[:30],input_warnings=errors[:30]),
           ensure_ascii=False,indent=2))
    print("\n".join(summary),flush=True)
    print("V82 ZIP",out,out.stat().st_size,flush=True)

def selftest():
    r=np.random.default_rng(82)
    y=np.zeros((1200,80),dtype=np.uint8)
    for i in range(len(y)):y[i,r.choice(80,20,replace=False)]=1
    ids=np.arange(1,len(y)+1)
    p,rank,unbroken=rank434(y,ids)
    assert rank.shape==(1201,80)
    for t in range(N,len(y)+1,77):
        q=rank[t]//16
        assert np.array_equal(np.bincount(q,minlength=5),[16]*5)
        assert np.all(p[t]-p[t-N]>=0)
        assert unbroken(t-N,t)
    assert OFFSETS[-1]-OFFSETS[-2]==12
    assert len([OFFSETS[i]-OFFSETS[i-1] for i in range(1,len(OFFSETS))
             if OFFSETS[i]-OFFSETS[i-1]==12])==36
    print("V82 SELFTEST OK",flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--source",default="veri.txt")
    a.add_argument("--out",default="v82_output/V82_72GUN_434CEKILIS_36x12_BES_16LIK_HAVUZ_YOLCULUK.zip")
    a.add_argument("--selftest",action="store_true")
    args=a.parse_args()
    if args.selftest:selftest()
    else:main(args.source,args.out)
