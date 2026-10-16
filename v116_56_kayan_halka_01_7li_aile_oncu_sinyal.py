#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V116: 56 constantly-full RELATIVE rings x12 after EACH new draw.

All pre-hour 56x80x12 binary trajectories and 5x16 pools preserved.
Seven-family defined from two H22 draws with exactly seven common
numbers, BEFORE H23 and 12 outcome draws. Prechosen 1/0 and pool
convergence signals tested vs same-pool, random7 and HOT72 control.

The observed outcome changes pool *after* the draw (mechanical effect).
It must never serve as a feature of that draw. Historical exploratory
results not proof of prospective betting edge.
"""
from __future__ import annotations
import argparse,csv,io,zipfile,json,math
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load,temperature
from v102_80sayi_56_halka_yon_zinciri_hedef_saat import expected_hours

RS=12; GR=56; MEM=RS*GR
POOL=("SOGUK","SERIN","NOTR","ILIK","SICAK")
SEED=20261016

def csvsave(z,name,rr):
    if not rr:return
    with z.open(name,'w',force_zip64=True) as raw:
        f=io.TextIOWrapper(raw,encoding='utf-8-sig',newline='')
        w=csv.DictWriter(f,fieldnames=list(rr[0]))
        w.writeheader();w.writerows(rr);f.flush();f.detach()

def family_h22(t,X):
    for i in range(11,0,-1):
        for j in range(i-1,-1,-1):
            family=np.flatnonzero((X[t-12+i]>0)&(X[t-12+j]>0))
            if len(family)==7:return family,(j+1,i+1)
    return None,None

def grid(t,X,prefix):
    """exact moving 56 x 12 groups (relative indices redefined each t)"""
    assert t>=744
    start=t-MEM
    bits=X[start:t].reshape(GR,RS,80)
    endpos=start+RS*np.arange(1,GR+1)
    counts=prefix[endpos]-prefix[endpos-72]
    pool=np.stack([temperature(c) for c in counts],axis=0)
    assert bits.shape==(56,12,80)
    assert pool.shape==(56,80)
    assert (bits.sum(axis=(1,2))==240).all()
    assert ((pool==np.arange(5)[:,None,None]).sum(axis=2)==16).all()
    return bits,pool

def signals(fam,bits,pool):
    z=pool[:,fam]  # 56 x 7
    mx=[];pairs=[]
    for states in z:
        h=np.bincount(states,minlength=5)
        mx.append(int(h.max()))
        pairs.append(int(sum(math.comb(int(n),2) for n in h)))
    mx=np.array(mx);pairs=np.array(pairs)
    # 1/0 in moving ring: seven family members per ring.
    monthly=bits[:,:,fam].transpose(2,0,1).sum(axis=2) # 7×56
    assert monthly.shape==(7,56)
    six_old=monthly[:,-12:-6].sum(axis=1)
    six_new=monthly[:,-6:].sum(axis=1)
    active_growth=int((six_new>six_old).sum())
    last=monthly[:,-1] # H22 12 drawings; family exact7 pair tautology
    prev_peak=(bits[:-1,:,fam].sum(axis=2).max(axis=1)) # pre H22 older55 rings
    older_3plus=int(np.sum(prev_peak>=3))
    # pooled reunion prehour defined using prior6 pool positions then last6
    reunion3=int((mx[-12:-6]<=2).any() and (mx[-6:]>=3).any())
    reunion4=int((mx[-12:-6]<=2).any() and (mx[-6:]>=4).any())
    # observational fixed threshold, not selected on H23 outcomes
    upward_pair=int(pairs[-6:].mean()>pairs[-12:-6].mean())
    faster01=int(active_growth>=4)
    return dict(reunion3=reunion3,reunion4=reunion4,
                pair_pool_concentration_up=upward_pair,
                four_family_members_01_rising=faster01,
                rising_members=active_growth,
                recent6_minus_previous6_ones=int(six_new.sum()-six_old.sum()),
                last_pool_top_group=int(mx[-1]),
                last_pool_same_pairs=int(pairs[-1]),
                older_55_rings_with_3plus_same_draw=older_3plus,
                counts_family_last6_72="|".join(map(str,six_new)),
                counts_family_prev6_72="|".join(map(str,six_old)),
                max_one_pool_56="".join(map(str,mx)),
                pool_pairs_56="|".join(map(str,pairs))),monthly

def choose_controls(fam,t,pool,prefix,rng):
    latest=pool[-1]
    # same exact latest16-pool composition as original family;
    # can't reuse selected seven members.
    used=set(map(int,fam))
    picked=[]
    for p in latest[fam]:
        c=[b for b in range(80) if int(latest[b])==int(p) and
           b not in used and b not in picked]
        assert c
        picked.append(int(rng.choice(c)))
    rnd=rng.choice(80,7,replace=False).astype(int)
    freq=prefix[t]-prefix[t-72]
    hot=np.lexsort((np.arange(80),-freq))[:7]
    return dict(FAMILY=fam,POOL_MATCH=np.array(picked,dtype=int),
                RANDOM7=rnd,HOT72=hot)

def run(path,out):
    days,rows,X,issues,bad=load(path)
    n=len(rows)
    P=np.vstack((np.zeros((1,80),dtype=np.int32),
                  np.cumsum(X,dtype=np.int32,axis=0)))
    cand,rejected=expected_hours(rows)
    target=[(t,d,h,ids) for t,d,h,ids in cand
            if h==23 and t>=744 and t+12<=n]
    selected=[];draws=[];stages=[];all80=[];movement=[]
    pairs=np.empty((0,80),dtype=np.int8)
    skipped=0
    for tid,(t,date,h,ids) in enumerate(target):
        fam,pair=family_h22(t,X)
        if fam is None:
            skipped+=1;continue
        bits,pool=grid(t,X,P)
        sig,loc=signals(fam,bits,pool)
        rng=np.random.default_rng(SEED+tid*11449+t)
        controls=choose_controls(fam,t,pool,P,rng)
        names={k:"-".join(map(str,(v+1))) for k,v in controls.items()}
        score={}
        for meth,chosen in controls.items():
            hh=X[t:t+12][:,chosen].sum(axis=1)
            score[meth]=hh
        selected.append(dict(date=date,first_target_id=rows[t]['id'],
            family_pair_h22=f"{pair[0]}-{pair[1]}",
            **{k+"_numbers":v for k,v in names.items()},
            **sig,
            **{k+"_12draw_hits":int(z.sum()) for k,z in score.items()},
            **{k+"_5of7":int((z>=5).sum()) for k,z in score.items()}))
        # Every ball x 56 relative rings for this hour (not future).
        for g in range(GR):
            left=t-MEM+g*12
            for b in range(80):
                bi=bits[g,:,b]
                all80.append(dict(date=date,first_target_id=rows[t]['id'],
                     relative_ring=g+1,number=b+1,
                     first_in_ring=rows[left]['id'],
                     last_in_ring=rows[left+11]['id'],
                     before_hour_12bits=''.join(map(str,bi)),
                     count_before_hour=int(bi.sum()),
                     pool16_before_hour=POOL[int(pool[g,b])],
                     in_selected_family=int(b in fam)))
            pm=pool[g,fam]
            h=np.bincount(pm,minlength=5)
            stages.append(dict(date=date,relative_ring=g+1,
                first_id=rows[left]['id'],last_id=rows[left+11]['id'],
                family='-'.join(map(str,fam+1)),
                pool7='|'.join(POOL[int(i)] for i in pm),
                seven_member_counts_12bits='|'.join(
                  ''.join(map(str,bits[g,:,int(b)])) for b in fam),
                family_member_draws_in_ring=int(bits[g,:,fam].sum()),
                cold_members=int(h[0]),cool_members=int(h[1]),
                neutral_members=int(h[2]),warm_members=int(h[3]),
                hot_members=int(h[4]),max_shared_pool=int(h.max())))
        # Walk 12 actual draw steps, measure pool *before* vs *after*.
        for k in range(12):
            old=t+k
            pre=temperature(P[old]-P[old-72])
            aft=temperature(P[old+1]-P[old+1-72])
            yy=X[old]
            row=dict(date=date,target_id=rows[old]['id'],hand=k+1,
                **{method+"_hits":int(score[method][k]) for method in controls},
                family_matching='-'.join(map(str,(fam[yy[fam]>0]+1))),
                **{key:sig[key] for key in ("reunion3","reunion4",
                    "pair_pool_concentration_up",
                    "four_family_members_01_rising")},
                full80_rising_after=int((aft>pre).sum()),
                full80_falling_after=int((aft<pre).sum()),
                family_pre_draw_pools='|'.join(POOL[int(i)] for i in pre[fam]),
                family_post_draw_pools='|'.join(POOL[int(i)] for i in aft[fam]),
                family_rising_after=int((aft[fam]>pre[fam]).sum()),
                family_falling_after=int((aft[fam]<pre[fam]).sum()))
            draws.append(row)
            for b in fam:
                movement.append(dict(date=date,target_id=rows[old]['id'],
                  number=int(b+1),
                  pre_pool=POOL[int(pre[b])],
                  is_drawn=int(yy[b]),
                  post_pool=POOL[int(aft[b])],
                  delta_pool=int(aft[b]-pre[b]),
                  # Current relative ring56 last12 changed after new draw
                  old_ring56_ones=int(X[old-12:old,b].sum()),
                  after_ring56_ones=int(X[old-11:old+1,b].sum())))
        if len(selected)%10==0:
            print("V116 processed last-hours",len(selected),flush=True)
    # Per-day, matched control differences. Each day is a dependent cluster.
    dailies=[]
    allmethods=("FAMILY","RANDOM7","POOL_MATCH","HOT72")
    groups=("reunion4","pair_pool_concentration_up","four_family_members_01_rising")
    for r in selected:
        row=dict(date=r["date"],**{g:r[g] for g in groups},
            **{m+"_12hits":r[m+"_12draw_hits"] for m in allmethods})
        row["family_vs_random"]=row["FAMILY_12hits"]-row["RANDOM7_12hits"]
        row["family_vs_same_pool"]=row["FAMILY_12hits"]-row["POOL_MATCH_12hits"]
        row["family_vs_hot72"]=row["FAMILY_12hits"]-row["HOT72_12hits"]
        dailies.append(row)
    stat=[]
    seq=[("ALL",selected),("FIRST34",selected[:34]),("LAST35",selected[34:])]
    for period,data in seq:
        if not data:continue
        for cond in ("ALL","reunion3","reunion4",
                     "pair_pool_concentration_up",
                     "four_family_members_01_rising"):
            cases=(("all",data) if cond=="ALL"
                  else (("yes",[r for r in data if r[cond]]),
                        ("no",[r for r in data if not r[cond]])))
            # Normalize shape when cond is ALL
            if cond=="ALL":cases=(("all",data),)
            for val,rr in cases:
                if not rr:continue
                n12=len(rr)*12
                stat.append(dict(phase=period,condition=cond,
                    condition_value=val,n_days=len(rr),n_draws=n12,
                    avg7_family_per_draw=round(sum(r["FAMILY_12draw_hits"] for r in rr)/n12,6),
                    avg7_random_per_draw=round(sum(r["RANDOM7_12draw_hits"] for r in rr)/n12,6),
                    avg7_samepool_per_draw=round(sum(r["POOL_MATCH_12draw_hits"] for r in rr)/n12,6),
                    avg7_hot72_per_draw=round(sum(r["HOT72_12draw_hits"] for r in rr)/n12,6),
                    family_5plus=sum(r["FAMILY_5of7"] for r in rr),
                    random_5plus=sum(r["RANDOM7_5of7"] for r in rr),
                    samepool_5plus=sum(r["POOL_MATCH_5of7"] for r in rr),
                    hot72_5plus=sum(r["HOT72_5of7"] for r in rr)))
    report=[
      "V116 56x12 TAM KAYAN HALKA, 80 SAYI 0-1 VE 7LI AILE ILERI CIKIS",
      f"Verified source records: {n}; latest #{rows[-1]['id']}; source last day {rows[-1]['day']}.",
      f"Full H23 examined={len(target)}, exact7 prechosen families={len(selected)}, no-family={skipped}.",
      "At hour start every ring has EXACTLY 12 historical draws. Each new draw: one old OUT, new IN.",
      "Family members frozen from prior H22 exact-seven coincidence, target H23 unknown.",
      "Pool at each relative ring uses 72 drawings ending at ring end; exactly 16 per class.",
      "Every family has 56x7x12 pretarget 0/1 path (details in ring CSV).",
      "Reunion4: previous6-ring stage has a ring max <=2 common pool members",
      "and recent6-ring stage has a ring with >=4 sharing a pool.",
      "Four 01 rising: at least 4 of seven family members appear more",
      "in most recent six relative rings (72 draws) than six prior rings.",
      "Pair concentration trend: mean same-pool family pair total of latest6",
      "rings exceeds six preceding rings.",
      "Given family H22 selection (2 full coincidences), counts in newest ring",
      "are correlated by construction; latest ring is NOT an independent discovery.",
      "",
      "Each period and condition: family vs equal-number random, same-pool matched and hot72:"
    ]
    for r in stat:
        if r["phase"] in ("ALL","LAST35"):
            report.append(f"{r['phase']} {r['condition']}={r['condition_value']}"+
                 f" nDays={r['n_days']}, nH23draws={r['n_draws']}"+
                 f" means FAMILY={r['avg7_family_per_draw']:.3f}"+
                 f" RANDOM={r['avg7_random_per_draw']:.3f}"+
                 f" MATCHED={r['avg7_samepool_per_draw']:.3f}"+
                 f" HOT72={r['avg7_hot72_per_draw']:.3f}"+
                 f" 5/7+ FAMILY={r['family_5plus']} RANDOM={r['random_5plus']}"+
                 f" MATCHED={r['samepool_5plus']} HOT72={r['hot72_5plus']}.")
    report+=["","IMPORTANT: Do not select the best subgroup ex post.",
     "The first34/last35 split is only historical, previously analyzed data.",
     "Any re-clustering or a 5/7 event after the target cannot be used as"+
     " pretarget signal. An outcome driven pool change is tautological.",
     "Fair 20/80 expected 7 picks per draw = 1.75, 5+/7 probability about 0.94%.",
     "Claim predictive success ONLY if genuinely new future H23 events",
     "beat equal-budget controls and appropriately adjusted uncertainty."]
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_V116_TURKCE_KISA_SONUCLAR.txt","\n".join(report)+"\n")
        csvsave(z,"01_HER_23_SAAT_ONCESI_56X80_HALKA_12BIT_DOKUM.csv",all80)
        csvsave(z,"02_7LI_AILE_56_HALKANIN_TAMAMINDA_01_VE_5HAVUZ.csv",stages)
        csvsave(z,"03_23ONCESI_7LI_AILE_GUN_GUN_ONCU_ISARET.csv",selected)
        csvsave(z,"04_HEDEF_23_12_CEKILIS_4_KONTROL_KUPON.csv",draws)
        csvsave(z,"05_AILE_UYELERI_HEDEF_CEKILISTEN_ONCE_SONRA_HAVUZ.csv",movement)
        csvsave(z,"06_DONEM_SINYAL_7LI_ISABET_KARSILASTIRMA.csv",stat)
        csvsave(z,"07_GUN_GUN_FARK_AILE_KONTROL.csv",dailies)
        z.writestr("08_VERI_METOD_DENETIM.json",json.dumps(dict(version="V116.1",
            latest_id=rows[-1]['id'],source_rows=n,target_hours=len(target),
            prechosen_exact7=len(selected),moving_ring_count=56,
            observations_per_moving_ring=12,all80_hour_rows=len(all80),
            future_target_not_read_in_selection=True,
            fixed_seven_family_before_h23=True,
            proof_of_future_edge=False),ensure_ascii=False,indent=2))
    print("\n".join(report),flush=True)
    print("V116 FINISHED",out,out.stat().st_size,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v116_output/V116_56_KAYAN_HALKA_01_7LI_AILE_ONCU_KOR_KARSILASTIR.zip")
    a=p.parse_args()
    run(a.source,a.out)
