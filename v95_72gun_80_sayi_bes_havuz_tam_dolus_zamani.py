#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V95 — 80 numbers: when do ALL visit ALL 5 moving temperature pools?

Reproduces V54 72-draw snapshot logic EXACTLY:
count frequency from last72 OBSERVED draws; sort by (frequency,
ball_number), assign ranks 0..15 COLD, 16..31 COOL, 32..47 NEUTRAL,
48..63 WARM, 64..79 HOT. Thus at EVERY snapshot *all 80* are split
16 each BY DEFINITION; the interesting question is whether EACH ball
eventually visits ALL FIVE. Number tie-breaking favors low numbers
for lower pools, and is held identical in fair RNG simulations.

72 complete real days (Aug1..Oct12) from first raw draw. Reference
starts at draw72 (1Aug). Snapshot every subsequent actual draw,
using last72 observed draws even across night; never pretend night
gap = 5minutes. Validated full-day chronological IDs; missing 23Aug
day excluded. Days and IDs always appear in output.

Compare fair independent 20 unique of80 draws with identical 72 day
clock pattern; median/interval and two-sided p for declared summary
metrics. This detects unusual mobility, not predictive RNG knowledge.
"""
from __future__ import annotations
import argparse,collections,csv,datetime,io,json,math,zipfile
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V95.1"
SEED=951016
W=72
N=80
POOL_NAMES=("SOGUK","SERIN","NOTR","ILIK","SICAK")
REF_DRAWS=(217,3*217,7*217,14*217,36*217,72*217)
SAMPLE_STEP=(1,12,72,217)
NULL_REPS=99

def load(path):
    daily,issues,bad=parse_txt(path)
    good={day:entries for day,entries in daily.items() if len(entries)==217
          and [r["pos"] for r in entries]==list(range(1,218))}
    days=sorted(good)
    if len(days)!=72 or days[0]!="2026-08-01" or days[-1]!="2026-10-12":
        raise RuntimeError(f"Expected 72 full days 1 Aug..12 Oct, got {len(days)}")
    rows=[r for d in days for r in good[d]]
    out=np.zeros((len(rows),80),dtype=np.uint8)
    for t,row in enumerate(rows):
        out[t,np.asarray(row["nums"],dtype=int)-1]=1
    if not np.all(out.sum(axis=1)==20):raise AssertionError("20/80 invalid")
    return days,rows,out,issues,bad

def fair(n,rng):
    # Sampling without replacement via independent continuous priorities:
    # exactly 20 ones, 60 zeros for each row, unlike raw Bernoulli(.25).
    priorities=rng.random((n,80),dtype=np.float32)
    selected=np.argpartition(priorities,20,axis=1)[:,:20]
    x=np.zeros((n,80),dtype=np.uint8)
    x[np.arange(n)[:,None],selected]=1
    return x

def cycles(X,rows=None,detail=False):
    assert X.ndim==2 and X.shape[1]==80
    length=len(X)
    if length<W:raise AssertionError("Less than 72 observed draws")
    count=X[:W].sum(axis=0,dtype=np.int32)
    bits=np.zeros(80,dtype=np.uint8)
    first_pool=np.full((80,5),-1,dtype=np.int32)
    last_pool=np.zeros(80,dtype=np.int8)
    earliest_change=np.full(80,-1,dtype=np.int32)
    first_back=np.full(80,-1,dtype=np.int32)
    first_5=np.full(80,-1,dtype=np.int32)
    leaving=np.zeros(80,dtype=bool)
    initial=None
    first_allleft=-1
    first_allreturn=-1
    first_all5=-1
    first_all_both=-1
    first_80seen=-1
    acc=np.zeros(80,dtype=bool)
    duration=np.zeros((80,5),dtype=np.int32)
    transitions=np.zeros((5,5),dtype=np.int64)
    changed_total=0
    perdraw=[]
    dayend=[]
    # Compact occupancy vectors for delayed overlap at 12,72,217 draws
    # keep rolling history for 217 past states.
    ring=np.zeros((218,80),dtype=np.int8)
    same={k:[0,0] for k in SAMPLE_STEP}
    final_state=None
    checkpoints={}
    nall5=0
    for t in range(length):
        acc|=(X[t]>0)
        if first_80seen<0 and acc.all():first_80seen=t
        if t<W-1:continue
        if t>W-1:
            count+=X[t].astype(np.int32)
            count-=X[t-W].astype(np.int32)
        assert int(count.sum())==W*20
        sortedidx=np.lexsort((np.arange(80),count))
        state=np.empty(80,dtype=np.int8)
        state[sortedidx]=np.repeat(np.arange(5),16)
        if not np.array_equal(np.bincount(state,minlength=5),
                              np.repeat(16,5)):raise AssertionError("bad 16x5 ranking")
        index=t-(W-1)
        for k in SAMPLE_STEP[1:]:
            if index>=k:
                prior=ring[(index-k)%218]
                same[k][0]+=int((state==prior).sum())
                same[k][1]+=80
        ring[index%218]=state
        if initial is None:
            initial=state.copy()
        else:
            changes=(state!=last_pool)
            np.add.at(transitions,(last_pool,state),1)
            changed_total+=int(changes.sum())
            newlyleft=(state!=initial)&(~leaving)
            leaving|=(state!=initial)
            for n in np.flatnonzero(newlyleft):earliest_change[n]=t
            newlyreturn=leaving&(state==initial)&(first_back<0)
            first_back[newlyreturn]=t
            if first_allleft<0 and leaving.all():first_allleft=t
            if first_allreturn<0 and np.all(first_back>=0):first_allreturn=t
        duration[np.arange(80),state]+=1
        for k in range(5):
            which=(state==k)
            npfirst=(first_pool[:,k]<0)&which
            first_pool[npfirst,k]=t
        bits|=(1<<state).astype(np.uint8)
        just_completed=(first_5<0)&(bits==31)
        first_5[just_completed]=t
        nall5=int(np.sum(bits==31))
        if first_all5<0 and nall5==80:first_all5=t
        nboth=int(np.sum((bits&17)==17))
        if first_all_both<0 and nboth==80:first_all_both=t
        if t+1 in REF_DRAWS:
            checkpoints[t+1]=dict(
                 draws_seen=t+1,snapshots=index+1,
                 unique_people_seen=int(acc.sum()),
                 full_five_members=nall5,
                 have_cold_hot=int(nboth),
                 distinct_pool_counts=[int(np.sum(np.bit_count(bits)==m)) for m in range(1,6)]
             ) if False else dict(draws_seen=t+1,snapshots=index+1,
                 unique_numbers_seen=int(acc.sum()),
                 full_five_members=nall5,
                 ever_cold_and_hot=nboth,
                 count_1_pool=int(np.sum([int(v).bit_count()==1 for v in bits])),
                 count_2_pools=int(np.sum([int(v).bit_count()==2 for v in bits])),
                 count_3_pools=int(np.sum([int(v).bit_count()==3 for v in bits])),
                 count_4_pools=int(np.sum([int(v).bit_count()==4 for v in bits])),
                 count_5_pools=nall5)
        if detail:
            oldsame=int((state==last_pool).sum()) if index else 80
            perdraw.append(dict(
                day=rows[t]["day"],draw_id=rows[t]["id"],time=rows[t]["time"],
                draw_position=t+1,rolling_reference=W,
                all80_appear_at_least_once=int(first_80seen>=0),
                pool_count_1=checkpoints.get(t+1,{}).get("count_1_pool",""),
                number_completed_all5=nall5,
                completed_cold_and_hot=nboth,
                stayed_same_pool_from_previous_snapshot=oldsame,
                changed_pool_from_previous_snapshot=80-oldsame,
                same_as_initial_count=int(np.sum(state==initial))))
            if t==length-1 or rows[t+1]["day"]!=rows[t]["day"]:
                dayend.append(dict(day=rows[t]["day"],date_last_draw=rows[t]["id"],
                    elapsed_draws=t+1,completed_full5=nall5,
                    completed_cold_and_hot=nboth,
                    still_same_initial_pool=int((state==initial).sum()),
                    visited_pool_count_1=int(np.sum([int(v).bit_count()==1 for v in bits])),
                    visited_pool_count_2=int(np.sum([int(v).bit_count()==2 for v in bits])),
                    visited_pool_count_3=int(np.sum([int(v).bit_count()==3 for v in bits])),
                    visited_pool_count_4=int(np.sum([int(v).bit_count()==4 for v in bits])),
                    visited_pool_count_5=nall5))
        last_pool=state
        final_state=state
    complete=np.where(first_5>=0)[0]
    incomplete=np.flatnonzero(first_5<0)
    final_nstates=np.array([int(v).bit_count() for v in bits],dtype=np.int8)
    results=dict(
      ndraws=length,snapshots=length-W+1,
      all80_first_seen_draw=first_80seen+1 if first_80seen>=0 else None,
      all80_5pools_complete_draw=first_all5+1 if first_all5>=0 else None,
      all80_initial_group_left_draw=first_allleft+1 if first_allleft>=0 else None,
      all80_left_and_returned_original_draw=first_allreturn+1 if first_allreturn>=0 else None,
      all80_cold_and_hot_visited_draw=first_all_both+1 if first_all_both>=0 else None,
      numbers_ever_all5=int(len(complete)),
      numbers_not_all5=int(len(incomplete)),
      numbers_never_left_initial=int(np.sum(~leaving)),
      numbers_not_returned_initial=int(np.sum(first_back<0)),
      final_number_visited_pool_hist={str(k):int(np.sum(final_nstates==k)) for k in range(1,6)},
      initial_vs_final_same_count=int(np.sum(initial==final_state)),
      total_pool_switches=changed_total,
      switch_rate_per_number_per_snapshot=float(changed_total/(80*(length-W))),
      same_state_probability_lag12=float(same[12][0]/same[12][1]),
      same_state_probability_lag72=float(same[72][0]/same[72][1]),
      same_state_probability_lag217=float(same[217][0]/same[217][1]),
      first5_median_draw=float(np.median(first_5[complete]+1)) if len(complete) else None,
      first5_earliest_draw=int(first_5[complete].min()+1) if len(complete) else None,
      first5_latest_draw=int(first_5[complete].max()+1) if len(complete) else None,
      checkpoints=checkpoints)
    if not detail:return results,None
    notes=[]
    for n in range(80):
        row=dict(number=n+1,first_reference_pool=POOL_NAMES[initial[n]],
              last_pool=POOL_NAMES[final_state[n]],
              distinct_pools_visited=int(final_nstates[n]),
              first_all5_draw_position=int(first_5[n]+1) if first_5[n]>=0 else None,
              first_all5_day=rows[first_5[n]]["day"] if first_5[n]>=0 else "",
              first_all5_draw_id=rows[first_5[n]]["id"] if first_5[n]>=0 else "",
              first_left_original_draw=int(earliest_change[n]+1) if earliest_change[n]>=0 else None,
              first_return_original_draw=int(first_back[n]+1) if first_back[n]>=0 else None,
              pools_never_seen=";".join(POOL_NAMES[k] for k in range(5) if not bits[n]&(1<<k)))
        for k,name in enumerate(POOL_NAMES):
            row["first_enter_"+name+"_id"]=rows[first_pool[n,k]]["id"] if first_pool[n,k]>=0 else ""
            row["time_in_"+name+"_snapshots"]=int(duration[n,k])
        notes.append(row)
    detail_result=dict(number_rows=notes,day_end=dayend,draw_summary=perdraw,
                       transitions=transitions.tolist())
    return results,detail_result

def csvwrite(z,name,items):
    if not items:return
    with z.open(name,"w",force_zip64=True) as f:
        txt=io.TextIOWrapper(f,encoding="utf-8",newline="")
        w=csv.DictWriter(txt,fieldnames=list(items[0]))
        w.writeheader();w.writerows(items);txt.flush();txt.detach()

def fair_compare(actual,nsims,length):
    rng=np.random.default_rng(SEED)
    keys=["all80_first_seen_draw","all80_5pools_complete_draw",
          "all80_initial_group_left_draw","all80_left_and_returned_original_draw",
          "all80_cold_and_hot_visited_draw","numbers_ever_all5",
          "numbers_not_all5","initial_vs_final_same_count",
          "total_pool_switches","switch_rate_per_number_per_snapshot",
          "same_state_probability_lag12","same_state_probability_lag72",
          "same_state_probability_lag217","first5_median_draw"]
    sim=collections.defaultdict(list)
    snapshots=[]
    for step in range(nsims):
        fake=fair(length,rng)
        ret,_=cycles(fake,detail=False)
        for k in keys:sim[k].append(ret[k])
        for checkpoint in REF_DRAWS:
            snapshots.append(dict(null_index=step+1,draws_seen=checkpoint,
                  completed_full5=ret["checkpoints"][checkpoint]["full_five_members"]))
        if (step+1)%10==0:print("V95 20/80 RNG simulation",step+1,"/",nsims,flush=True)
    table=[]
    for k in keys:
        s=np.array([np.nan if v is None else v for v in sim[k]],np.float64)
        valid=s[np.isfinite(s)]
        real=actual[k]
        if real is None or not len(valid):p=None
        else:
            p=(1+int(np.sum(np.abs(valid-valid.mean())>=
                    abs(float(real)-valid.mean()))))/(len(valid)+1)
        table.append(dict(metric=k,actual=real,
            rng_simulations=int(nsims),rng_nonmissing=int(len(valid)),
            rng_null_mean=round(float(valid.mean()),7) if len(valid) else None,
            rng_null_median=round(float(np.median(valid)),7) if len(valid) else None,
            rng_q025=round(float(np.quantile(valid,.025)),7) if len(valid) else None,
            rng_q975=round(float(np.quantile(valid,.975)),7) if len(valid) else None,
            exploratory_two_sided_p=p))
    return table,snapshots

def run(path,outfile,nsims):
    days,rows,data,issues,bad=load(path)
    actual,full=cycles(data,rows,detail=True)
    assert len(full["number_rows"])==80 and len(full["day_end"])==72
    compare,sims=fair_compare(actual,nsims,len(data))
    first=rows[W-1]
    def stamp(drawpos):
        return (f"draw {drawpos}: {rows[drawpos-1]['day']} "
                f"{rows[drawpos-1]['time']} #{rows[drawpos-1]['id']}"
                if drawpos else "not reached inside 72 full days")
    print("V95 72draw reference first",stamp(72),flush=True)
    report=[
       "V95 — 80 SAYI BES HAVUZDA TAM TUR YAPIYOR MU? 72 GUN BASINDAN BAKIS",
       f"Raw start={rows[0]['day']} {rows[0]['time']} id#{rows[0]['id']},",
       f"first valid full 72 reference={stamp(72)}.",
       f"72 full days / {len(data)} draws / {actual['snapshots']} rolling 72-draw snapshots.",
       "V54 EXACT relative 5-pool scheme: 72 appearance counts sorted",
       "ascending (count72, number), 16 COLD,16 COOL,16 NEUTRAL,",
       "16 WARM,16 HOT. Thus 80 numbers split into five pools in",
       "EVERY snapshot by definition. Full-tour means same number has",
       "visited ALL FIVE pools at least once after first reference.",
       "Ties by number favor low ball IDs in colder classes:",
       "this bias is in both real and 20-of-80 matched simulations.",
       f"First time all 80 appeared in 20 selected draw balls: {stamp(actual['all80_first_seen_draw'])}.",
       f"First time every initial 80 number has LEFT original relative pool: {stamp(actual['all80_initial_group_left_draw'])}.",
       f"First time every number has been in BOTH COLD and HOT: {stamp(actual['all80_cold_and_hot_visited_draw'])}.",
       f"First time EACH of 80 has visited ALL FIVE pools: {stamp(actual['all80_5pools_complete_draw'])}.",
       f"First time EACH has left and then RETURNED to its original pool: {stamp(actual['all80_left_and_returned_original_draw'])}.",
       f"At end 72 days: have visited all five {actual['numbers_ever_all5']}/80; not {actual['numbers_not_all5']}/80.",
       f"At end in SAME starting pool: {actual['initial_vs_final_same_count']}/80 (not continuous; could leave and return).",
       f"Number-pool individual switches {actual['total_pool_switches']}; one-step switch rate {actual['switch_rate_per_number_per_snapshot']:.4%}.",
       f"Same class 12 drawings later {actual['same_state_probability_lag12']:.4%};",
       f"same class 72 drawings later {actual['same_state_probability_lag72']:.4%};",
       f"same class 217 drawings later {actual['same_state_probability_lag217']:.4%}.",
       "",
       "COVERAGE ALONG 72 COMPLETE DAYS (from draw 1):",
    ]
    for checkpoint in REF_DRAWS:
        z=actual["checkpoints"][checkpoint]
        report.append(f"  after {checkpoint:5d} draws: full five {z['full_five_members']}/80,"
                      f" both cold+hot {z['ever_cold_and_hot']}/80,"
                      f" only1/2/3/4/5={z['count_1_pool']}/"
                      f"{z['count_2_pools']}/{z['count_3_pools']}/"
                      f"{z['count_4_pools']}/{z['count_5_pools']}.")
    report+=["",f"FAIR 20-of-80 CONTROL: {nsims} independent full sequences, each same {len(data)} draws,"]
    for obj in compare:
        report.append(f"  {obj['metric']}: real={obj['actual']},"
                      f" RNG avg={obj['rng_null_mean']},"
                      f" simulated95=[{obj['rng_q025']},{obj['rng_q975']}],"
                      f" exploratory p={obj['exploratory_two_sided_p']}.")
    report+=["",
       "Note pool membership changes ARE guaranteed by a continuously",
       "updated sliding frequency window; this alone is not predictive.",
       "Pure fair 20/80 drawing makes high/low counts swap rank over time,",
       "causing even all 80 to move through many or all pools.",
       "For all numbers touring all pools, the END date is descriptive,",
       "NOT the date each ball must appear in the next real draw.",
       "Rolling72 uses previous72 OBSERVED draws, not continuous six hours:",
       "01:02->07:02 night gap is tracked as elapsed time not a 5min step.",
       "Skipped incomplete day cannot be interpreted as uninterrupted.",
       "Do not infer hidden RNG cycling or compensating next-hour odds.",
       "79 RNG alternative models not assessed; these are exploratory",
       "comparisons and corpus has been studied in versions V9..V94."
    ]
    out=Path(outfile);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as z:
        z.writestr("00_V95_ILK72DEN_80_SAYI_BES_HAVUZ_TAM_TUR_KARAR.txt","\n".join(report))
        csvwrite(z,"01_SEKSEN_SAYI_HER5_HAVUZA_ILK_GIRIS_VE_BITIS.csv",full["number_rows"])
        csvwrite(z,"02_72_GUN_SONUNDA_KAC_SAYI_BES_HAVUZU_DOLASTI.csv",full["day_end"])
        csvwrite(z,"03_ILK72DEN_SON_GUNE_HER_CEKILIS_HAVUZ_KAPSAMI.csv",full["draw_summary"])
        csvwrite(z,"04_RNG_SAHte20_80_BES_HAVUZ_SIRALAMA_KONTROL.csv",compare)
        csvwrite(z,"05_RNG_HER_DENEME_KAPSAMA_ZAMANLARI.csv",sims)
        csvwrite(z,"06_HAVUZDAN_HAVUZA_GECISLER.csv",[
           dict(onceki=POOL_NAMES[i],sonraki=POOL_NAMES[j],
                sayi=int(full["transitions"][i][j]))
           for i in range(5) for j in range(5)])
        z.writestr("07_DENETIM_JSON.json",json.dumps(dict(
          version=VERSION,first_reference_72=first,observed_results=actual,
          fair_rng_replicates=nsims,comparison=compare,
          pool_names=POOL_NAMES,source_invalid_rows=bad[:30],
          source_issues=issues[:30]),ensure_ascii=False,indent=2,default=str))
    print("\n".join(report),flush=True)
    print("V95 DONE",out,out.stat().st_size,flush=True)

def selftest():
    sample=np.zeros((W+4,80),np.uint8)
    rng=np.random.default_rng(12)
    for i in range(len(sample)):
        sample[i,rng.choice(80,20,replace=False)]=1
    a,d=cycles(sample,detail=False)
    assert a["snapshots"]==5 and a["numbers_ever_all5"]==0
    assert a["initial_vs_final_same_count"]<=80
    assert np.all(fair(25,np.random.default_rng(13)).sum(axis=1)==20)
    print("V95 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v95_output/V95_72GUN_80_SAYI_5_HAVUZ_TAM_TUR_ZAMANI.zip")
    p.add_argument("--null",default=NULL_REPS,type=int)
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    selftest() if a.selftest else run(a.source,a.out,a.null)
