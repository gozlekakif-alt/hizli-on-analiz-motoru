#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V130: Choose 10 numbers from FOUR vs FIVE distinct 16-ball groups.

PRE-TARGET t: X[t] known; score group and per-number using ONLY X[:t+1].
TARGET: X[t+1] read after group/ticket is frozen, no target leakage.

Three ways to define five nonoverlapping equal 16-number pools:
  72-draw frequency rank  (ring 6)
  672-draw frequency rank (ring 56)
  224-ring consensus frequency ranking (mean of all 224 pool states).
Any equal-frequency tie resolved by number ascending. Groups labels
0..4: cold, cool, neutral, warm, hot.

Four groups: one group excluded by pre-draw group selection (fixed omitted
cold/hot, or last 12/72 group counts max/min), then ticket's chosen numbers
spread round-robin across the 4 retained groups, quotas 3+3+2+2 for k10,
5+5+5+5 for k20. Five groups: 2+2+2+2+2 k10, 4 each k20.
For fair comparison ALL modes are one ticket per draw per requested size.

One member picker uses HOT12 observed frequency, the other uses full
224-ring last-step direction (net warming); compare random-within-pool too.

Measure 4-pool coverage (target 20 numbers in 64-number pool),
group-omit success and equal-budget k ticket hits. Select best group-based
10-ball model only in VALIDATE18, lock and report LAST18 with bootstraps.
LAST18 is chronological but previously studied, NOT virgin future draw data.
"""
from __future__ import annotations
import argparse,collections,csv,io,json,zipfile
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load

NR=224
NB=80
LENS=np.arange(12,2689,12,dtype=np.int32)
SIZES=(3,4,5,6,8,10,20)
ANCHORS=("H72","H672","CONS224")
POLICIES=(
 "5_BAL_HOT12","5_BAL_WAVE","5_BAL_RANDOM_PICK",
 "4_OMIT_COLD_HOT12","4_OMIT_HOT_HOT12",
 "4_DROP_LOW12_HOT12","4_DROP_HIGH12_HOT12",
 "4_DROP_LOW72_HOT12","4_DROP_HIGH72_HOT12",
 "4_DROP_LOW12_WAVE","4_DROP_LOW72_WAVE",
 "4_RANDOM_GROUP_RANDOM_PICK")
FIXED=("RANDOM_UNCONSTRAINED","HOT12_UNCONSTRAINED",
       "HOT72_UNCONSTRAINED","HOT672_UNCONSTRAINED",
       "HOT2688_UNCONSTRAINED")
MODELS=tuple(f"{a}_{p}" for a in ANCHORS for p in POLICIES)+FIXED
GROUP_NAMES=("SOGUK","SERIN","NOTR","ILIK","SICAK")
SEED=1302026
assert len(LENS)==224 and len(MODELS)==41

def pools(cnt):
    order=np.argsort(cnt,axis=1,kind="stable")
    rk=np.empty((NR,NB),dtype=np.uint8)
    rk[np.arange(NR)[:,None],order]=np.arange(NB,dtype=np.uint8)
    lab=rk//16
    return lab

def one_grouping(g):
    counts=np.bincount(g,minlength=5)
    assert (counts==16).all(),counts

def consensus(p):
    # 0..4 average family/temperature: five equal 16-ball consensus pools
    # Long-range pool consensus is a characteristic of each NUMBER, not
    # family/cross-ball "related number".
    vote=p.astype(np.int32).sum(axis=0)
    order=np.argsort(vote,kind="stable")
    g=np.empty(NB,dtype=np.uint8)
    g[order]=np.repeat(np.arange(5,dtype=np.uint8),16)
    return g

def model_def(anch,pol,g,hot12,hot72,wave,target_index):
    cats=np.array([np.flatnonzero(g==k) for k in range(5)],dtype=object)
    # Robust: use direct arrays for known exact 16-ball group sizes.
    group_sets=[np.flatnonzero(g==i) for i in range(5)]
    r12=np.asarray([int(hot12[ix].sum()) for ix in group_sets])
    r72=np.asarray([int(hot72[ix].sum()) for ix in group_sets])
    def argwhere(v,mode):
        return int(np.lexsort((np.arange(5), v if mode=="LOW" else -v))[0])
    if pol.startswith("5_"):
        active=list(range(5))
        omitted=-1
    elif pol.startswith("4_"):
        if pol=="4_OMIT_COLD_HOT12":omitted=0
        elif pol=="4_OMIT_HOT_HOT12":omitted=4
        elif "LOW12" in pol:omitted=argwhere(r12,"LOW")
        elif "HIGH12" in pol:omitted=argwhere(r12,"HIGH")
        elif "LOW72" in pol:omitted=argwhere(r72,"LOW")
        elif "HIGH72" in pol:omitted=argwhere(r72,"HIGH")
        elif pol=="4_RANDOM_GROUP_RANDOM_PICK":
            omitted=int(np.random.default_rng(SEED+target_index*97+
                            {"H72":0,"H672":1,"CONS224":2}[anch]).integers(0,5))
        else:raise AssertionError(pol)
        active=[x for x in range(5) if x!=omitted]
    else:raise AssertionError(pol)
    # Stable ordering: group with higher recent12 known count gets early
    # quota3 rather than quota2 (for 4 groups 10 number ticket).
    # For a fair random-picker baseline, group priority deterministic too.
    priority=sorted(active,key=lambda j:(-r12[j],j))
    random_pick="RANDOM_PICK" in pol
    scores=wave if "WAVE" in pol else hot12
    picks={}
    for gp in priority:
        ix=group_sets[gp]
        if random_pick:
            rng=np.random.default_rng(SEED+target_index*4093+
                   gp*593+{"H72":0,"H672":1,"CONS224":2}[anch]*37)
            picks[gp]=rng.permutation(ix)
        else:
            # Score max first, tie numeric smaller first
            picks[gp]=ix[np.lexsort((ix,-scores[ix]))]
    j={x:0 for x in priority}
    out=[]
    # cycle all active until first 20 are chosen; exact quotas
    for k in range(20):
        gp=priority[k%len(priority)]
        pos=j[gp];j[gp]+=1
        out.append(int(picks[gp][pos]))
    out=np.asarray(out,dtype=int)
    assert len(out)==20 and len(set(out))==20
    assert set(map(int,g[out]))==set(active)
    assert (np.bincount(g[out],minlength=5)[active]==20//len(active)).all()
    assert (np.bincount(g[out[:10]],minlength=5)[active].sum())==10
    if len(active)==5:
        assert (np.bincount(g[out[:10]],minlength=5)[active]==2).all()
    else:
        assert sorted(np.bincount(g[out[:10]],minlength=5)[active])==[2,2,3,3]
    return out,omitted,tuple(active),r12,r72

def csv_put(z,path,rows):
    if not rows:return
    mem=io.StringIO(newline="")
    w=csv.DictWriter(mem,fieldnames=list(rows[0]))
    w.writeheader();w.writerows(rows)
    z.writestr(path,mem.getvalue().encode("utf-8-sig"))

def main(source,out):
    days,rows,X,issues,bad=load(source)
    n=len(rows)
    assert len(X)==n and n>2700 and np.all(X.sum(axis=1)==20)
    final_dates=sorted(d for d in days if d<="2026-10-12")
    assert len(final_dates)==72
    period={d:("TRAIN36" if i<36 else "VALIDATE18" if i<54 else "LAST18")
            for i,d in enumerate(final_dates)}
    P=np.vstack((np.zeros((1,NB),dtype=np.int32),
                  np.cumsum(X,axis=0,dtype=np.int32)))
    curr=P[2688][None,:]-P[2688-LENS]
    prev_pool=pools(curr)
    result=collections.defaultdict(lambda:np.zeros(5,dtype=np.int64))
    coverage=collections.defaultdict(lambda:np.zeros(6,dtype=np.int64))
    day_hit=collections.defaultdict(lambda:np.zeros(2,dtype=np.int64))
    group_omit=collections.defaultdict(lambda:np.zeros(8,dtype=np.int64))
    audits=[]
    last_signatures=[]
    for t in range(2688,n-1):
        # t is the last KNOWN result. t+1 is TARGET, never used to choose.
        enter=X[t].astype(np.int16)
        leave=X[t-LENS].astype(np.int16)
        new=curr+enter[None,:]-leave
        group224=pools(new)
        motion=np.sign(group224.astype(np.int16)-prev_pool.astype(np.int16))
        wave=(motion>0).sum(axis=0)-(motion<0).sum(axis=0)
        hot12,hot72,hot672,hot2688=(new[i] for i in (0,5,55,223))
        groups=dict(H72=group224[5],H672=group224[55],
                    CONS224=consensus(group224))
        for g in groups.values():one_grouping(g)
        # dynamic per-group candidate fits are all frozen BEFORE next target
        tt=t+1
        y=X[tt].astype(np.int16)
        phase=period.get(rows[tt]["day"],"EXTRA_OCT13")
        day=rows[tt]["day"]
        idx=int(tt)
        if tt==n-1:
            for ball in range(80):
                last_signatures.append(dict(
                  number=ball+1,latest_known_id=rows[t]["id"],
                  verified_target_id=rows[tt]["id"],
                  next_target_outcome=int(y[ball]),
                  h72_class=GROUP_NAMES[int(groups["H72"][ball])],
                  h672_class=GROUP_NAMES[int(groups["H672"][ball])],
                  consensus224_class=GROUP_NAMES[int(groups["CONS224"][ball])],
                  consensus224_net_warming=int(wave[ball]),
                  prior_hot12_count=int(hot12[ball]),
                  prior_hot72_count=int(hot72[ball])))
        selected={}
        group_metadata={}
        for anchor in ANCHORS:
            g=groups[anchor]
            # group actual next-draw hit histogram, per target 5 groups, sum20.
            group_hits=np.bincount(g,weights=y,minlength=5).astype(np.int64)
            assert group_hits.sum()==20
            for gp in range(5):
                coverage[(phase,anchor,gp)]+=(1,int(group_hits[gp]),
                    int(group_hits[gp]==0),int(group_hits[gp]<=2),
                    int(group_hits[gp]>=6),int(group_hits[gp]>=8))
            for policy in POLICIES:
                method=f"{anchor}_{policy}"
                picks,omitted,active,r12,r72=model_def(
                    anchor,policy,g,hot12,hot72,wave,idx)
                selected[method]=picks
                group_metadata[method]=(omitted,active,group_hits)
                if omitted!=-1:
                    # 4-pool coverage, without picking individual numbers:
                    # selected four pools 64 candidate numbers, target20 included.
                    missed=int(group_hits[omitted])
                    good=20-missed
                    q=group_omit[(phase,method)]
                    q[0]+=1;q[1]+=good;q[2]+=missed
                    q[3]+=int(missed==int(group_hits.min()))
                    q[4]+=int(missed<=2)
                    q[5]+=int(missed>=6)
                    q[6]+=int(good>=17)
                    q[7]+=int(good>=18)
        for name,counts in (
          ("RANDOM_UNCONSTRAINED",
           np.random.default_rng(SEED+idx*719).permutation(NB)[:20]),
          ("HOT12_UNCONSTRAINED",
           np.lexsort((np.arange(NB),-hot12))[:20]),
          ("HOT72_UNCONSTRAINED",
           np.lexsort((np.arange(NB),-hot72))[:20]),
          ("HOT672_UNCONSTRAINED",
           np.lexsort((np.arange(NB),-hot672))[:20]),
          ("HOT2688_UNCONSTRAINED",
           np.lexsort((np.arange(NB),-hot2688))[:20])):
            selected[name]=np.asarray(counts,dtype=int)
        assert len(selected)==len(MODELS)
        for method in MODELS:
            pick=selected[method]
            hit=np.cumsum(y[pick])
            for k in SIZES:
                h=int(hit[k-1])
                q=result[(phase,method,k)]
                q[0]+=1;q[1]+=h;q[2]+=int(h==k)
                q[3]+=int(h>=5);q[4]+=int(h>=6)
                if phase=="LAST18" and k==10:
                    day_hit[(day,method)]+=(1,h)
            if phase=="LAST18" and (method.startswith("CONS224_") or
                method in ("RANDOM_UNCONSTRAINED","HOT72_UNCONSTRAINED")):
                omit,active,group_hits=group_metadata.get(method,(-1,(),None))
                audits.append(dict(date=day,draw_id=rows[tt]["id"],
                  last_known_id=rows[t]["id"],method=method,
                  excluded_group=GROUP_NAMES[omit] if omit!=-1 else "NONE",
                  group_pool_targets="|".join(map(str,group_hits))
                     if group_hits is not None else "",
                  picks10=" ".join(map(str,pick[:10]+1)),
                  hits3=int(hit[2]),hits4=int(hit[3]),hits5=int(hit[4]),
                  hits6=int(hit[5]),hits8=int(hit[7]),hits10=int(hit[9]),
                  full_actual_draw20=" ".join(map(str,np.flatnonzero(y)+1))))
        curr=new
        prev_pool=group224
        if (t-2687)%2500==0:
            print("V130 processed",t-2687,"/",n-2689,flush=True)
    score=[]
    for phase in ("VALIDATE18","LAST18","TRAIN36","EXTRA_OCT13"):
        for method in MODELS:
            for k in SIZES:
                q=result.get((phase,method,k))
                if q is None or q[0]==0:continue
                score.append(dict(period=phase,model=method,coupon_size=k,
                    targets=int(q[0]),avg_hits=round(float(q[1]/q[0]),6),
                    perfect_k_of_k=int(q[2]),hits5plus=int(q[3]),
                    hits6plus=int(q[4]),expected_random_mean=k*.25))
    four_coverage=[]
    for phase in ("VALIDATE18","LAST18","TRAIN36","EXTRA_OCT13"):
        for method in MODELS:
            if "_4_" not in method:continue
            q=group_omit.get((phase,method))
            if q is None or q[0]==0:continue
            four_coverage.append(dict(period=phase,model=method,
               target_draws=int(q[0]),avg_20_target_in_64_pool=
               round(float(q[1]/q[0]),6),
               avg_target20_missed_in_excluded16=
               round(float(q[2]/q[0]),6),
               chosen_excluded_group_was_min_target_hits=int(q[3]),
               excluded_group_target_hit_le2=int(q[4]),
               excluded_group_target_hit_ge6=int(q[5]),
               covered_17plus=int(q[6]),covered_18plus=int(q[7]),
               independent_random_4_pool_expected_target_coverage=16.0))
    pool_counts=[]
    for phase in ("VALIDATE18","LAST18","TRAIN36","EXTRA_OCT13"):
        for anchor in ANCHORS:
            for k in range(5):
                q=coverage.get((phase,anchor,k))
                if q is None or q[0]==0:continue
                pool_counts.append(dict(period=phase,pool_definition=anchor,
                    pool=GROUP_NAMES[k],draws=int(q[0]),
                    avg_target_hit_in16=round(float(q[1]/q[0]),6),
                    expected_target_hit_in16=4.0,
                    zero_target_hits=int(q[2]),
                    target_hits_le2=int(q[3]),
                    target_hits_ge6=int(q[4]),
                    target_hits_ge8=int(q[5])))
    # choose best group model by VALIDATE18 10-ball mean, lock on LAST18
    validations=sorted([
         (method,int(result[("VALIDATE18",method,10)][0]),
          float(result[("VALIDATE18",method,10)][1])/
                float(result[("VALIDATE18",method,10)][0]))
         for method in MODELS if method not in FIXED
       ],key=lambda x:(-x[2],x[0]))
    winner=validations[0][0]
    hold_days=sorted(d for d in final_dates if period[d]=="LAST18")
    comparison=[]
    for bench in ("RANDOM_UNCONSTRAINED","HOT72_UNCONSTRAINED",
                  "CONS224_5_BAL_HOT12","CONS224_5_BAL_RANDOM_PICK",
                  "CONS224_4_RANDOM_GROUP_RANDOM_PICK"):
        d=np.asarray([day_hit[(day,winner)][1]/day_hit[(day,winner)][0]-
                      day_hit[(day,bench)][1]/day_hit[(day,bench)][0]
                      for day in hold_days])
        rng=np.random.default_rng(SEED+len(bench))
        samples=d[rng.integers(0,len(d),(5000,len(d)))].mean(axis=1)
        comparison.append(dict(winner=winner,other=bench,holdout_days=len(d),
            average_10_number_hit_difference=round(float(d.mean()),6),
            confidence95_lower=round(float(np.quantile(samples,.025)),6),
            confidence95_upper=round(float(np.quantile(samples,.975)),6)))
    note=[
      "V130 — FOUR OR FIVE 16-NUMBER POOLS VS FLAT RANDOM PICK",
      f"Real source {n} draws, targets {n-2689}, last ID {rows[-1]['id']}.",
      "Before each target the 224 ring pool states and group choice",
      "are frozen using only prior draws. No future target leaks.",
      "All models use exactly ONE ticket per next-draw target.",
      f"Group strategies {len(MODELS)-len(FIXED)} + fixed baselines {len(FIXED)}.",
      "Pools: 72,672 rings or consensus across 224 rings, 5x16 numbers.",
      "For k=10: 5 pools => 2+2+2+2+2; 4 pools => 3+3+2+2.",
      "For k=20: 5 pools => 4 numbers/pool; 4 pools=>5 per pool.",
      "Every drawn 20 has expectation 4 numbers per 16-ball group;",
      "a 64-ball four-pool candidate field expects 16 of next 20.",
      "Older VALIDATE18 selects one group-based method by 10-ball",
      "average. Later LAST18 tests it without changing the recipe;",
      "however all these dates have been seen in other experiments",
      "so not an independent, unseen future holdout.","",
      "LAST18 expected group targets per 16-ball pool (4):"]
    for x in pool_counts:
        if x["period"]=="LAST18":
            note.append(f" {x['pool_definition']} {x['pool']}: "
                 f"{x['avg_target_hit_in16']:.4f}/16")
    note.extend(["","LAST18 10-number coupon comparison:"])
    for m in (winner,"CONS224_5_BAL_HOT12","CONS224_4_DROP_LOW12_HOT12",
              "CONS224_4_DROP_LOW72_HOT12",
              "CONS224_4_RANDOM_GROUP_RANDOM_PICK",
              "CONS224_5_BAL_RANDOM_PICK",
              "HOT12_UNCONSTRAINED","HOT72_UNCONSTRAINED",
              "RANDOM_UNCONSTRAINED"):
        q=result[("LAST18",m,10)]
        note.append(f" {m}: avg={q[1]/q[0]:.6f}, >=5={q[3]},"
                    f" >=6={q[4]}, perfect10={q[2]}, targets={q[0]}")
    note.append("")
    note.append("VALIDATE18 winner: "+winner+
                f" validation avg10={validations[0][2]:.6f}")
    for x in comparison:
        note.append(f" LOCKED WINNER minus {x['other']} "
           f"LAST18 10-ball avg difference {x['average_10_number_hit_difference']:+.6f},"
           f" day-bootstrap95 [{x['confidence95_lower']:+.6f},"
           f"{x['confidence95_upper']:+.6f}]")
    note.extend(["","LAST18 pre-selected 4-pool target20 candidate coverage:",
                 "independent neutral expectation 16 of 20"])
    for x in four_coverage:
        if x["period"]=="LAST18" and x["model"] in (
          "CONS224_4_DROP_LOW12_HOT12","CONS224_4_DROP_LOW72_HOT12",
          "CONS224_4_RANDOM_GROUP_RANDOM_PICK"):
            note.append(f" {x['model']}: covered {x['avg_20_target_in_64_pool']:.4f}"
                f" and excluded group target hits "
                f"{x['avg_target20_missed_in_excluded16']:.4f}")
    note.extend(["","No advantage follows solely from using 4/5 pools.",
       "All conditional differences are retrospective and involve 36 group",
       "strategies: multiple-testing selection is a major limitation.",
       "A genuinely new forward data window is needed for confirmation."])
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as z:
        z.writestr("00_V130_KISA_4_5_HAVUZ_GERCEK_TEST.txt","\n".join(note)+"\n")
        csv_put(z,"01_41_MODEL_3_4_5_6_8_10_20_ISABETLER.csv",score)
        csv_put(z,"02_4_HAVUZ_64_SAYI_HEDEF20_KAPSAMA.csv",four_coverage)
        csv_put(z,"03_5_HAVUZ_HER_16_SAYI_HEDEF20_GIRIS_ORANI.csv",pool_counts)
        csv_put(z,"04_VALIDASYONDA_SECILEN_MODEL_SON18_KONTROL.csv",comparison)
        csv_put(z,"05_SON18_41_MODEL_10_SAYI_DOGRULAMA_SIRALAMA.csv",
                [dict(method=m,targets=c,avg10=h) for m,c,h in validations])
        csv_put(z,"06_SON18_CONSENSUS224_HEDEF_TEK_TEK_KUPON.csv",audits)
        csv_put(z,"07_SON_HEDEF_80_SAYI_224_HAVUZ_SINIFI_SABIT.csv",last_signatures)
        z.writestr("08_KUTUK_DENETIM.json",json.dumps(dict(
            source="veri.txt",source_rows=n,targets=n-2689,
            last_real_draw=rows[-1]["id"],
            first_target=rows[2689]["id"],
            five_equal_pools_each_of_16=True,
            224_nested_lengths=LENS.tolist(),
            group_definitions=ANCHORS,
            group_methods=POLICIES,
            methods=MODELS,
            coupon_sizes=SIZES,
            validation_locked_winner=winner,
            truly_unseen_data=False,
            target_used_in_scoring=False,
            all_group_memberships_use_prior_draws=True),
            ensure_ascii=False,indent=2))
    print("\n".join(note),flush=True)
    print("V130 SUCCESS",out,out.stat().st_size,flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--source",default="veri.txt")
    a.add_argument("--out",default="v130_output/V130_4_VE_5_HAVUZ_GRUP_SECIM_41_MODEL_KOR.zip")
    p=a.parse_args()
    main(p.source,p.out)
