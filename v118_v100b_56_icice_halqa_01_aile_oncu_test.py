#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V118 cumulative NESTED moving windows 12,24,36,...,672 (56).

Restore original V100B semantics, now adding all 80x672 past 1/0 bits,
80x56 pre-draw accumulated appearance counts and five 16-member pool
positions, 7-member prior-hour family's path, and subsequent H23
single-draw checks with control groups.

Every new draw slides ALL 56 trailing windows by one observation.
Do not confuse with V115/V116's 56 DISJOINT 12-draw relative groups.
All future outcomes read only after pre-draw features freeze.
"""
from __future__ import annotations
import argparse, csv, io, json, zipfile
from collections import defaultdict
from pathlib import Path
import numpy as np
from v100c_yuruyen_672_fifo_sabit_12_halka import load, temperature
from v102_80sayi_56_halka_yon_zinciri_hedef_saat import expected_hours

LENGTHS=np.arange(12,673,12,dtype=int)
assert len(LENGTHS)==56
LABELS=("SOGUK","SERIN","NOTR","ILIK","SICAK")
SEED=118_2026
def sendcsv(z,name,records):
    if not records:return
    with z.open(name,"w",force_zip64=True) as fp:
        f=io.TextIOWrapper(fp,encoding="utf-8-sig",newline="")
        w=csv.DictWriter(f,fieldnames=list(records[0]))
        w.writeheader();w.writerows(records)
        f.flush();f.detach()

def nested(pre,t):
    """NESTED 56 windows, all right endpoints=t, no future outcomes."""
    assert t>=672
    counts=pre[t][None,:]-pre[t-LENGTHS,:] # 56x80
    states=np.stack([temperature(row) for row in counts],axis=0)
    assert counts.shape==(56,80)
    assert states.shape==(56,80)
    assert np.all(np.bincount(states[0],minlength=5)==16)
    assert np.all(np.bincount(states[-1],minlength=5)==16)
    assert np.all(counts[0]>=0)
    assert np.all(counts[-1]>=counts[0])
    assert (counts[-1].sum()==672*20)
    return counts,states

def fam_from_h22(t,X):
    for i in range(11,0,-1):
        for j in range(i-1,-1,-1):
            f=np.flatnonzero(X[t-12+i]&X[t-12+j])
            if len(f)==7:
                return f,(j+1,i+1)
    return None,None

def choose(fam,states,counts,t,rng):
    used=set(int(v) for v in fam)
    picked=[]
    for v in states[-1,fam]:
        available=[x for x in range(80) if states[-1,x]==v
                   and x not in used and x not in picked]
        assert available
        picked.append(int(rng.choice(available)))
    hot72=np.lexsort((np.arange(80),-counts[5]))[:7]
    hot672=np.lexsort((np.arange(80),-counts[-1]))[:7]
    return {"FAMILY":fam,
            "RANDOM7":rng.choice(80,7,replace=False),
            "POOL672_MATCH":np.array(picked,dtype=int),
            "HOT72":hot72,"HOT672":hot672}

def cluster_signal(fam,counts,states):
    f=states[:,fam]
    sharedmax=[]
    sharedpairs=[]
    for ix in range(56):
        h=np.bincount(f[ix],minlength=5)
        sharedmax.append(int(h.max()))
        sharedpairs.append(int(np.sum(h*(h-1)//2)))
    # Short: windows 12-72. Long: windows 612-672.
    short_pair=float(np.mean(sharedpairs[:6]))
    long_pair=float(np.mean(sharedpairs[-6:]))
    short_max=max(sharedmax[:6])
    long_max=max(sharedmax[-6:])
    short_more_pairs=int(short_pair>long_pair)
    nested_reunion4=int(short_max>=4 and long_max<=3)
    # Actual 0/1: recent72 count versus the 72 immediately before it.
    recent72=counts[5,fam]
    previous72=counts[11,fam]-counts[5,fam]
    rising_4=int((recent72>previous72).sum()>=4)
    both=int(short_more_pairs and rising_4)
    return dict(short6_mean_shared_pairs=round(short_pair,5),
                long6_mean_shared_pairs=round(long_pair,5),
                short_max_shared_pool=int(short_max),
                long_max_shared_pool=int(long_max),
                short_more_pairs=short_more_pairs,
                nested_reunion4=nested_reunion4,
                four_members_01_rising=rising_4,
                nested_and_01_both=both,
                family_recent72_ones="|".join(map(str,recent72)),
                family_previous72_ones="|".join(map(str,previous72)),
                six_short_sharedmax="|".join(map(str,sharedmax[:6])),
                six_long_sharedmax="|".join(map(str,sharedmax[-6:])),
                family_56_pool_sharedpair="|".join(map(str,sharedpairs))), \
                np.array(sharedmax),np.array(sharedpairs)

def run(source,output):
    days,rows,X,issues,bad=load(source)
    n=len(rows)
    P=np.vstack((np.zeros((1,80),dtype=np.int32),
                 np.cumsum(X,axis=0,dtype=np.int32)))
    valid,bad_hours=expected_hours(rows)
    hours=[(t,day,h,ids) for t,day,h,ids in valid
           if h==23 and t>=672 and t+12<=n]
    assert hours
    summary=[];binary=[];layer=[];familystage=[]
    drawledger=[];ballledger=[];stats=[];fold=[]
    cross=defaultdict(lambda:[0,0]) # number assignments and drawn
    familyhours=0
    for hh,(t,day,h,ids) in enumerate(hours):
        c0,s0=nested(P,t)
        fam,pair=fam_from_h22(t,X)
        # log ALL 80 pre-target past 672 bits once per target H23
        hist=X[t-672:t].T
        assert hist.shape==(80,672)
        for b in range(80):
            v=hist[b]
            bt="".join(map(str,v))
            binary.append(dict(day=day,first_target_id=rows[t]["id"],
                 number=b+1,preceding_672_bits=bt,
                 twelve_blocks_oldest_to_newest="|".join(
                      bt[k:k+12] for k in range(0,672,12)),
                 last12_ones=int(c0[0,b]),
                 last72_ones=int(c0[5,b]),
                 last672_ones=int(c0[-1,b]),
                 in_seven_family=int(fam is not None and b in fam)))
        for ix,L in enumerate(LENGTHS):
            ctr=c0[ix]
            state=s0[ix]
            assert ctr.sum()==20*L
            assert np.all(np.bincount(state,minlength=5)==16)
            for b in range(80):
                layer.append(dict(day=day,first_target_id=rows[t]["id"],
                   nested_ring=ix+1,window_draws=int(L),
                   number=b+1,ones_in_window=int(ctr[b]),
                   relative_pool=LABELS[int(state[b])],
                   direction_from_previous_shorter_ring=(
                      "=" if ix==0 or state[b]==s0[ix-1,b] else
                      "Y" if state[b]>s0[ix-1,b] else "D"),
                   family_member=int(fam is not None and b in fam)))
        if fam is not None:
            familyhours+=1
            sig, mx, pc=cluster_signal(fam,c0,s0)
            rng=np.random.default_rng(SEED+hh*17449+t)
            methods=choose(fam,s0,c0,t,rng)
            for ix,L in enumerate(LENGTHS):
                z=s0[ix,fam];v=np.bincount(z,minlength=5)
                recentbits=X[t-L:t][:,fam]
                familystage.append(dict(day=day,
                  chosen_seven="-".join(map(str,fam+1)),
                  nested_ring=ix+1,window_draws=int(L),
                  family_seven_pool="|".join(LABELS[int(x)] for x in z),
                  pool_cold=int(v[0]),pool_cool=int(v[1]),
                  pool_neutral=int(v[2]),pool_warm=int(v[3]),
                  pool_hot=int(v[4]),
                  max_members_one_pool=int(mx[ix]),
                  pair_count_same_pool=int(pc[ix]),
                  family_members_window_ones="|".join(map(str,c0[ix,fam])),
                  newly_added_12_bits_per_member="|".join(
                    "".join(str(int(x)) for x in X[t-(ix+1)*12:t-ix*12,b])
                    for b in fam)))
            # For this hour, family and control tickets are frozen at H23 start.
            yy=X[t:t+12]
            methhits={name:yy[:,subset].sum(axis=1).astype(int)
                      for name,subset in methods.items()}
            sumhits={name:int(z.sum()) for name,z in methhits.items()}
            summary.append(dict(day=day,first_target_id=rows[t]["id"],
                 family="|".join(map(str,fam+1)),
                 chosen_prior_H22_pair="|".join(map(str,pair)),
                 **sig,
                 **{name+"_12draw_hits":q for name,q in sumhits.items()},
                 **{name+"_5plus":int((methhits[name]>=5).sum())
                    for name in methods}))
        else:
            summary.append(dict(day=day,first_target_id=rows[t]["id"],
                 family="",chosen_prior_H22_pair=""))
        # Dynamic next-one-draw study: update nested windows *one* draw
        # and record before/after only AFTER outcome is revealed.
        for k in range(12):
            at=t+k
            before,sp=nested(P,at)
            observed=X[at]
            after,sa=nested(P,at+1)
            assert np.all((before[-1]+observed-X[at-672])==after[-1])
            assert np.all((before[0]+observed-X[at-12])==after[0])
            classes_change=[int((sp[idx]!=sa[idx]).sum()) for idx in (0,5,55)]
            drawledger.append(dict(day=day,target_id=rows[at]["id"],
                 target_hand=k+1,
                 family_before_chosen=int(fam is not None),
                 family_numbers="" if fam is None else "-".join(map(str,fam+1)),
                 family_hits="" if fam is None else int(observed[fam].sum()),
                 **({name+"_hits":int(methhits[name][k])
                     for name in methods} if fam is not None else {}),
                 **({name:sig[name] for name in ("short_more_pairs",
                        "nested_reunion4","four_members_01_rising",
                        "nested_and_01_both")} if fam is not None else {}),
                 changed_pools12=classes_change[0],
                 changed_pools72=classes_change[1],
                 changed_pools672=classes_change[2]))
            for b in range(80):
                for threshold in (0,5,55):
                    key=(threshold,int(sp[threshold,b]),
                         int(sp[55,b]))
                    cross[key][0]+=1
                    cross[key][1]+=int(observed[b])
                ballledger.append(dict(day=day,target_id=rows[at]["id"],
                    number=b+1,drawn_one_zero=int(observed[b]),
                    outgoing_12_bit=int(X[at-12,b]),
                    outgoing_72_bit=int(X[at-72,b]),
                    outgoing_672_bit=int(X[at-672,b]),
                    before12_ones=int(before[0,b]),after12_ones=int(after[0,b]),
                    before72_ones=int(before[5,b]),after72_ones=int(after[5,b]),
                    before672_ones=int(before[-1,b]),after672_ones=int(after[-1,b]),
                    before12_pool=LABELS[int(sp[0,b])],
                    after12_pool=LABELS[int(sa[0,b])],
                    before72_pool=LABELS[int(sp[5,b])],
                    after72_pool=LABELS[int(sa[5,b])],
                    before672_pool=LABELS[int(sp[-1,b])],
                    after672_pool=LABELS[int(sa[-1,b])],
                    seven_family_member=int(fam is not None and b in fam)))
        print("V118 processed target last-hour",hh+1,"of",len(hours),flush=True) if (hh+1)%15==0 else None
    families=[a for a in summary if a.get("family")]
    conds=("short_more_pairs","nested_reunion4",
           "four_members_01_rising","nested_and_01_both")
    for phase,sel in (
            ("ALL",families),("FIRST34",families[:34]),
            ("LAST34",families[34:])):
        for signal in ("ALL",)+conds:
            for yn in (("all",) if signal=="ALL" else (0,1)):
                subset=(sel if signal=="ALL" else
                        [a for a in sel if a[signal]==yn])
                if not subset: continue
                nd=len(subset)*12
                stat=dict(phase=phase,pre_hour_condition=signal,
                          condition_value=yn,days=len(subset),
                          draws=nd)
                for meth in ("FAMILY","RANDOM7","POOL672_MATCH","HOT72","HOT672"):
                    stat[meth+"_mean"]=round(
                        sum(a[meth+"_12draw_hits"] for a in subset)/nd,6)
                    stat[meth+"_5plus"]=sum(a[meth+"_5plus"] for a in subset)
                stats.append(stat)
    grid_summary=[]
    for window in (0,5,55):
        for group12 in range(5):
            for group672 in range(5):
                nobs,yes=cross[window,group12,group672]
                grid_summary.append(dict(
                    observed_window_draws=int(LENGTHS[window]),
                    observed_pool=LABELS[group12],
                    global_672_pool=LABELS[group672],
                    number_draw_pairs=nobs,
                    actual_next_draw_hits=yes,
                    actual_next_draw_percent=round(100*yes/nobs,4) if nobs else ""))
    # Daily independent cluster bootstrap approx with fixed PRNG seed
    def gap_stats(comp):
        z=np.array([(a["FAMILY_12draw_hits"]-a[comp+"_12draw_hits"])/12
                    for a in families],dtype=float)
        rng=np.random.default_rng(SEED+len(comp))
        boot=np.mean(z[rng.integers(0,len(z),(5000,len(z)))],axis=1)
        return dict(mean=float(z.mean()),lo=float(np.quantile(boot,.025)),
                    hi=float(np.quantile(boot,.975)))
    gaps={v:gap_stats(v) for v in ("RANDOM7","POOL672_MATCH","HOT72","HOT672")}
    lines=["V118 56 IC ICE HALKA 12 24 36 ... 672 / YURUYEN 1-0 AILE / HEDEF TEST",
           f"Source {n} draws, latest #{rows[-1]['id']} {rows[-1]['day']}; V100B ordering reversed for reading.",
           f"Evaluated H23 hour snapshots={len(hours)}, seven-family hours={len(families)}; next target draws={len(drawledger)}.",
           "Each new draw shifts all cumulative 56 windows by ONE; no target-time leakage.",
           "CSV full 69 hours x 56 windows x 80 numbers, and 69 x 80 complete 672-bit trajectories.",
           "Every day seven-member family frozen on H22 exact-seven intersection when it exists.",
           "NESTED cohesion is short trailing windows 12..72 compared with long 612..672.",
           "1/0 momentum is recent72 hits compared with preceding72 hits; note H22 selection effect.",
           "Compare equal-sized frozen random7, pool672-matched7, HOT72 and HOT672; all 12 H23 draws.",
           "Theory expected 7 x 20/80=1.75 hits per draw; 5+/7 is rare.",
           ""]
    for r in stats:
        if r["phase"] in ("ALL","LAST34"):
            lines.append(f"{r['phase']} {r['pre_hour_condition']}={r['condition_value']} "
                  f"hours={r['days']} draws={r['draws']} "
                  f"FAM={r['FAMILY_mean']:.4f} RAND={r['RANDOM7_mean']:.4f} "
                  f"MATCH={r['POOL672_MATCH_mean']:.4f} "
                  f"HOT72={r['HOT72_mean']:.4f} HOT672={r['HOT672_mean']:.4f} "
                  f"5+ FAM={r['FAMILY_5plus']} RAND={r['RANDOM7_5plus']} "
                  f"MATCH={r['POOL672_MATCH_5plus']}.")
    lines+=["", "BOOTSTRAP per DAY paired FAMILY minus control, 95% interval:"]
    for v,d in gaps.items():
        lines.append(f"FAMILY-{v}: mean={d['mean']:.5f},"
             f" 95%=[{d['lo']:.5f},{d['hi']:.5f}]")
    lines+=["",
       "Never treat retrospective exploratory threshold comparisons as validated prediction.",
       "Zero 1/0 bit is an observed absence; cannot forecast RNG seed by itself.",
       "Pool changes AFTER the target are caused by the target and do not predict it.",
       "Cumulative 12..672 rings are NOT 56 disjoint 12-draw groups."]
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        z.writestr("00_V118_KISA_TURKCE_GERCEK_SONUC.txt","\n".join(lines)+"\n")
        sendcsv(z,"01_H23_ONCESI_56_ICICE_HALKA_80_SAYI_TAM_KAYIT.csv",layer)
        sendcsv(z,"02_H23_ONCESI_80_SAYI_672_BIT_1_0_DIZISI.csv",binary)
        sendcsv(z,"03_7LI_AILE_56_PENCEREDE_FREKANS_HAVUZ_BIRLESME.csv",familystage)
        sendcsv(z,"04_GUN_GUN_AILE_HEDEF_ONCESI_ISARET_5_KUPON.csv",summary)
        sendcsv(z,"05_HEDEF_12_CEKILIS_BIREBIR_5_KUPON_KARSILASTIRMA.csv",drawledger)
        sendcsv(z,"06_HER_HEDEF_80_SAYI_12_72_672_ONCE_SONRA_1_0.csv",ballledger)
        sendcsv(z,"07_12_72_672_HAVUZ_CARPRAZ_GERCEK_HEDEF_ORANLARI.csv",grid_summary)
        sendcsv(z,"08_AILE_DONEM_YON_01_RITIM_KOR_KIYAS.csv",stats)
        z.writestr("09_ETKI_GUVEN_ARALIKLARI_VE_METOD.json",
            json.dumps(dict(version="V118.1",source_draws=n,
               latest_id=rows[-1]["id"],full_h23_hours=len(hours),
               family_hours=len(families),sample_draws=len(drawledger),
               nested_sizes=LENGTHS.tolist(),
               frozen_hour_rows=len(layer),all80_bit_rows=len(binary),
               target_80_rows=len(ballledger),gaps=gaps,
               signal_independence_not_proven=True,
               historical_data_extensively_reused=True),
               ensure_ascii=False,indent=2))
    print("\n".join(lines),flush=True)
    print("V118 COMPLETE",str(output),output.stat().st_size,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v118_output/V118_56_ICICE_HALKA_01_AILE_HEDEF_ONCU.zip")
    a=p.parse_args()
    run(a.source,a.out)
