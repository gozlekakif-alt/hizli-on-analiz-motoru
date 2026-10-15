#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V78: exact rank 1..16, old rank, 16-ball pool entry/exit and
historical 4-bit binary sequence before each 20-of-80 target.

Main reference N=60; counterfactual N=42,72,217. Each 16-ball tier is ranked
with strictly past draw frequencies, preserving prior rank as the tie break.
Snapshot BEFORE target t contains cur/old12 pool, exact cur/old12 within-tier
position (1..16), previous-step entry flag, directional shift and four
historical target 1/0 bits. Target result then labels 20 ones + 60 zeros.

Predefined six feature families estimate the target-1 frequency from TRAIN
(29 Aug..12 Sep 2026, 15 complete days) with alpha=250 shrinkage to .25.
Use VALIDATE (13..27 Sep) to fix exactly ONE feature family + reference.
Report locked HOLDOUT performance (28 Sep..12 Oct), 3255 draws, and
matched 5x4 quota-random control. No HOLDOUT-driven refit or model selection.
All historical dates have been examined in prior versions; not truly new
prospective evidence. Missing 23 Aug invalid day excluded from full-day series,
and no features/tests may cross the resulting draw-ID gap.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VER="V78.1"
LABELS=("SOGUK","SERIN","NOTR","ILIK","SICAK")
DIRECTIONS=("SOGUYOR","SABIT","ISINIYOR")
NS=(42,60,72,217)
MAIN=60
LAG=12
BITCOUNT=4
ALPHA=250
SEED=781015
BLOCK=217
TRAIN_START=27*BLOCK
VALID_START=42*BLOCK
TEST_START=57*BLOCK
END=72*BLOCK
FEATURES=("BASE30","POS160","EXACT2560","PATTERN240",
          "POS_PATTERN1280","EXACT_PATTERN3840")
STATESIZE=dict(BASE30=30,POS160=160,EXACT2560=2560,
               PATTERN240=240,POS_PATTERN1280=1280,EXACT_PATTERN3840=3840)

def load(src):
    byday,issues,malformed=parse_txt(src)
    full=sorted(d for d,v in byday.items()
                if len(v)==217 and [r["pos"] for r in v]==list(range(1,218)))
    if len(full)!=72 or full[0]!="2026-08-01" or full[-1]!="2026-10-12":
        raise ValueError(f"Expected 72 complete days: {len(full)} {full[:1]} {full[-1:]}")
    rows=[r for d in full for r in byday[d]]
    if len(rows)!=15624 or rows[-217]["id"]!=61629 or rows[-1]["id"]!=61845:
        raise ValueError("Unexpected full-day draw IDs")
    y=np.zeros((len(rows),80),dtype=np.uint8)
    for i,r in enumerate(rows):
        y[i,np.asarray(r["nums"],dtype=int)-1]=1
    assert np.all(y.sum(axis=1)==20)
    gaps=[(rows[i-1]["day"],rows[i]["day"],rows[i-1]["id"],rows[i]["id"])
          for i in range(1,len(rows)) if rows[i]["id"]!=rows[i-1]["id"]+1]
    assert len(gaps)==1, f"Gap policy requires one incomplete day: {gaps}"
    return full,rows,y,gaps,sorted(set(byday)-set(full)),issues,malformed

def prefixize(y):
    p=np.zeros((len(y)+1,80),dtype=np.int32)
    p[1:]=np.cumsum(y,dtype=np.int32,axis=0)
    return p

def valid_targets(rows,n):
    ids=np.array([r["id"] for r in rows],dtype=np.int32)
    seams=np.r_[0,np.diff(ids)!=1].astype(np.int32)
    seam_prefix=np.r_[0,np.cumsum(seams)]
    valid=np.zeros(len(rows),dtype=bool)
    for t in range(n+LAG,len(rows)):
        valid[t]=(seam_prefix[t+1]-seam_prefix[t-(n+LAG)+1]==0)
    return valid

def rolling_ranks(p,n):
    count=len(p)-1
    ranks=np.full((count,80),255,dtype=np.uint8)
    oldrank=np.arange(80)
    balls=np.arange(80)
    # At t only counts in [t-n, t) are used, not target t.
    for t in range(n,count):
        f=p[t]-p[t-n]
        order=np.lexsort((oldrank,f))
        cur=np.empty(80,dtype=np.uint8)
        cur[order]=np.arange(80,dtype=np.uint8)
        ranks[t]=cur
        oldrank=cur
    return ranks

def feature_arrays(rank,y,idx):
    r=rank[idx]
    old=rank[idx-LAG]
    prev=rank[idx-1]
    assert np.all(r<80) and np.all(old<80) and np.all(prev<80)
    group=r//16
    previous_group=old//16
    shift=np.where(group>previous_group,2,
                   np.where(group<previous_group,0,1)).astype(np.uint8)
    entry=(group!=(prev//16)).astype(np.uint8)
    at=r%16
    came=old%16
    prev1=y[idx-1].astype(np.uint8)
    pattern=np.zeros(r.shape,dtype=np.uint8)
    for h in range(1,BITCOUNT+1):
        pattern=pattern*2+y[idx-h]
    # These use strictly prior known outcomes, never y[idx].
    return dict(rank=r,oldrank=old,prev_rank=prev,group=group,
       oldgroup=previous_group,shift=shift,entry=entry,
       curpos=at,oldpos=came,prev1=prev1,pattern=pattern)

def state_code(a,model):
    q=a["group"].astype(np.uint16)
    d=a["shift"].astype(np.uint16)
    e=a["entry"].astype(np.uint16)
    p=a["curpos"].astype(np.uint16)
    op=a["oldpos"].astype(np.uint16)
    one=a["prev1"].astype(np.uint16)
    pat=a["pattern"].astype(np.uint16)
    if model=="BASE30":return ((q*3+d)*2+e).astype(np.uint16)
    if model=="POS160":return (((q*4+p//4)*4+op//4)*2+one).astype(np.uint16)
    if model=="EXACT2560":return (((q*16+p)*16+op)*2+one).astype(np.uint16)
    if model=="PATTERN240":return ((q*3+d)*16+pat).astype(np.uint16)
    if model=="POS_PATTERN1280":
        return (((q*4+p//4)*4+op//4)*16+pat).astype(np.uint16)
    if model=="EXACT_PATTERN3840":
        return (((q*16+p)*3+d)*16+pat).astype(np.uint16)
    raise ValueError(model)

def fit(s,y,k):
    n=np.bincount(s.reshape(-1),minlength=k).astype(np.int64)
    hits=np.bincount(s.reshape(-1),
             weights=y.reshape(-1),minlength=k).astype(np.float64)
    return (hits+.25*ALPHA)/(n+ALPHA),n,hits

def allocate(current,prob,code,noise):
    # Choose precisely 4 from every 16-member group, once per target.
    scores=prob[code]+noise*1e-9
    chosen=np.zeros(current.shape,dtype=np.uint8)
    rows=np.arange(len(current))[:,None]
    for q in range(5):
        valid=np.where(current==q,scores,-2.)
        picks=np.argpartition(valid,-4,axis=1)[:,-4:]
        assert np.all(current[rows,picks]==q)
        chosen[rows,picks]=1
    assert np.all(chosen.sum(axis=1)==20)
    return chosen

def fair_p(hits,draws):
    var=20*.25*.75*(60/79)
    delta=(hits-5*draws-.5)/math.sqrt(var*draws)
    return min(1.,max(0.,.5*math.erfc(delta/math.sqrt(2))))

def compare(a,b,truth):
    h1=(a*truth).sum(axis=1).astype(int)
    h2=(b*truth).sum(axis=1).astype(int)
    mismatch=20-(a*b).sum(axis=1).astype(int)
    var=float(np.sum(2*mismatch*.25*.75*80/79))
    z=float((h1-h2).sum())/math.sqrt(var) if var else 0.
    return dict(
        draws=len(h1),model_mean=round(float(h1.mean()),7),
        control_mean=round(float(h2.mean()),7),
        model_minus_control=round(float(h1.mean()-h2.mean()),7),
        hit_total=int(h1.sum()),
        fair_mean=5.,fair_p_one_sided=round(fair_p(int(h1.sum()),len(h1)),7),
        paired_z=round(z,6),
        paired_p_one_sided=round(.5*math.erfc(z/math.sqrt(2)),7),
        hit_7plus=int((h1>=7).sum()),hit_8plus=int((h1>=8).sum()),
        hit_9plus=int((h1>=9).sum()),hit_10plus=int((h1>=10).sum()),
        random_hit_7plus=int((h2>=7).sum()),
        random_hit_8plus=int((h2>=8).sum()),
    ),h1,h2

def score_per_day(hits,indices):
    days=np.unique(indices//BLOCK)
    averages=[float(hits[indices//BLOCK==i].mean()) for i in days]
    mean=float(np.mean(hits))
    sd=float(np.std(averages,ddof=1))
    return mean,sd,mean-.25*sd

def stream_gz(z,filename,header,iterable):
    with z.open(filename,"w",force_zip64=True) as f:
        with gzip.GzipFile(fileobj=f,mode="wb",compresslevel=4) as gz:
            tx=io.TextIOWrapper(gz,encoding="utf-8",newline="")
            csvw=csv.writer(tx)
            csvw.writerow(header)
            csvw.writerows(iterable)
            tx.flush();tx.detach()

def export_csv(z,filename,data,headers=None):
    headers=headers or list(data[0])
    with z.open(filename,"w",force_zip64=True) as f:
        tx=io.TextIOWrapper(f,encoding="utf-8",newline="")
        csvw=csv.DictWriter(tx,fieldnames=headers)
        csvw.writeheader();csvw.writerows(data)
        tx.flush();tx.detach()

def all_main_identity_ledger(rows,y,p,ranks,valid):
    """Exact 16-to-16 position records across ALL eligible 72-day draws."""
    for t in range(MAIN+LAG,len(rows)):
        if not valid[t]:
            continue
        cur=ranks[t];old=ranks[t-LAG];previous=ranks[t-1]
        f=p[t]-p[t-MAIN]
        pat=np.zeros(80,dtype=np.uint8)
        for delay in range(1,5):
            pat=pat*2+y[t-delay]
        for b in range(80):
            g=int(cur[b]//16);og=int(old[b]//16)
            move=g-og
            yield [rows[t]["day"],rows[t]["time"],rows[t]["id"],
                   rows[t]["pos"],b+1,int(f[b]),
                   LABELS[g],int(cur[b]%16)+1,LABELS[og],
                   int(old[b]%16)+1,move,
                   DIRECTIONS[0 if move<0 else 2 if move>0 else 1],
                   int(cur[b]//16!=previous[b]//16),
                   "".join(map(str,y[t-4:t,b].tolist())),
                   int(pat[b]),int(y[t-1,b]),int(y[t,b])]

def main(source,out):
    days,rows,y,gaps,excluded,issues,malformed=load(source)
    prefix=prefixize(y)
    scores=[]
    ninfo={}
    rng=np.random.default_rng(SEED)
    train_lo,train_hi=TRAIN_START,VALID_START
    val_lo,val_hi=VALID_START,TEST_START
    test_lo,test_hi=TEST_START,END
    n_eval=END-TRAIN_START
    # One common random tie-breaking draw per target for every candidate.
    noise=rng.random((n_eval,80))
    selection_cache={}
    validation_rows=[]
    print(f"V78: 72 complete days, 80 balls, models={len(FEATURES)} "
          f"x N={list(NS)}, exact positions1..16, 4 previous bits",flush=True)
    for n in NS:
        rank=rolling_ranks(prefix,n)
        valid=valid_targets(rows,n)
        def segment(start,end):
            return np.arange(start,end,dtype=np.int32)[valid[start:end]]
        indices=dict(TRAIN=segment(train_lo,train_hi),
                     VALIDATE=segment(val_lo,val_hi),
                     HOLDOUT=segment(test_lo,test_hi))
        assert all(len(v)==3255 for v in indices.values()),"Unexpected later gap"
        feature={phase:feature_arrays(rank,y,ix) for phase,ix in indices.items()}
        yy={phase:y[ix] for phase,ix in indices.items()}
        noise_at={phase:noise[indices[phase]-TRAIN_START]
                  for phase in indices}
        cn=feature["TRAIN"]["group"]
        ninfo[n]=(rank,valid,indices,feature,yy,noise_at)
        control={}
        for phase in indices:
            group=feature[phase]["group"]
            score=np.ones(5,dtype=float)*.25
            chosen=allocate(group,score,group,noise_at[phase])
            control[phase]=chosen
        for name in FEATURES:
            group_indices=state_code(feature["TRAIN"],name)
            probs,occurs,hits=fit(group_indices,yy["TRAIN"],STATESIZE[name])
            # No VALIDATION/HOLDOUT outcomes are used in fitting.
            for phase in ("VALIDATE","HOLDOUT"):
                states=state_code(feature[phase],name)
                selected=allocate(feature[phase]["group"],probs,states,
                                  noise_at[phase])
                perf,hs,ctlhs=compare(selected,control[phase],yy[phase])
                mean,sd,metric=score_per_day(hs,indices[phase])
                summary=dict(reference_N=n,model=name,phase=phase,
                        trained_state_cells=STATESIZE[name],
                        populated_train_cells=int((occurs>0).sum()),
                        train_total_number_state_opportunities=int(occurs.sum()),
                        selected_average_daily_stability_sd=round(sd,7),
                        selection_utility=round(metric,7),
                        **perf)
                scores.append(summary)
                if phase=="VALIDATE":
                    validation_rows.append(summary)
                selection_cache[n,name,phase]=(selected,probs,occurs,hits,hs,ctlhs,control[phase])
        print(f"V78 N={n} done, features six; ties stable; val+holdout=6510",flush=True)
    validation_rows.sort(key=lambda r:(-r["selection_utility"],
             r["reference_N"],FEATURES.index(r["model"])))
    best=validation_rows[0]
    key=(best["reference_N"],best["model"])
    locked=next(r for r in scores if r["reference_N"]==key[0]
               and r["model"]==key[1] and r["phase"]=="HOLDOUT")
    rank,valid,indices,features,yy,noise_at=ninfo[key[0]]
    chosen,probs,ncount,nhit,hit_model,hit_control,baseline=selection_cache[
        key[0],key[1],"HOLDOUT"]
    identity=[]
    tickets=[]
    daily=[]
    for i,t in enumerate(indices["HOLDOUT"]):
        r=rows[t]
        g=features["HOLDOUT"]["group"][i]
        oldg=features["HOLDOUT"]["oldgroup"][i]
        cp=features["HOLDOUT"]["curpos"][i]
        op=features["HOLDOUT"]["oldpos"][i]
        pat=features["HOLDOUT"]["pattern"][i]
        dr=features["HOLDOUT"]["shift"][i]
        selected=chosen[i]
        actual=yy["HOLDOUT"][i]
        cells=[]
        for q in range(5):
            nums=[j+1 for j in np.flatnonzero((g==q)&(selected>0))]
            assert len(nums)==4
            cells.append(nums)
        tickets.append(dict(day=r["day"],time=r["time"],id=r["id"],
             slot=r["pos"],reference_N=key[0],rule=key[1],
             selected20=",".join(map(str,np.flatnonzero(selected)+1)),
             actual_hits=int(hit_model[i]),
             balanced_random_hits=int(hit_control[i]),
             actual_hit_numbers=",".join(map(str,np.flatnonzero(actual&selected)+1)),
             **{f"{LABELS[q].lower()}_4":",".join(map(str,cells[q])) for q in range(5)}))
        for b in range(80):
            identity.append(dict(day=r["day"],id=r["id"],
                ball=b+1,pool_now=LABELS[int(g[b])],rank1_16=int(cp[b])+1,
                pool_12before=LABELS[int(oldg[b])],rank12before1_16=int(op[b])+1,
                direction=DIRECTIONS[int(dr[b])],
                prev4_binary=format(int(pat[b]),"04b"),
                selected=int(selected[b]),target_1_or_0=int(actual[b])))
    assert len(identity)==3255*80
    for di in range(15):
        vals=hit_model[di*BLOCK:(di+1)*BLOCK]
        controls=hit_control[di*BLOCK:(di+1)*BLOCK]
        daily.append(dict(day=days[57+di],N=key[0],rule=key[1],
             mean_hits=round(float(vals.mean()),5),
             random_5x4_mean=round(float(controls.mean()),5),
             difference=round(float(vals.mean()-controls.mean()),5),
             hits7plus=int((vals>=7).sum()),hits8plus=int((vals>=8).sum())))
    # Main 60 (all 72 days) exact within-pool 16x16 orig-dest matrix
    main_rank,main_valid=ninfo[MAIN][:2]
    matrix=np.zeros((5,5,16,16,2),dtype=np.int64)
    pattern_tab=np.zeros((5,16,2),dtype=np.int64)
    boundary=np.zeros((5,16,2),dtype=np.int64)
    counts=np.zeros((5,3,2,2),dtype=np.int64)
    for t in np.flatnonzero(main_valid):
        cur=main_rank[t]
        old=main_rank[t-LAG]
        prv=main_rank[t-1]
        pattern=np.zeros(80,dtype=np.uint8)
        for h in range(1,5):pattern=pattern*2+y[t-h]
        for b in range(80):
            p=int(cur[b]);op=int(old[b]);hit=int(y[t,b])
            cg=p//16;og=op//16;ci=p%16;oi=op%16
            matrix[og,cg,oi,ci,hit]+=1
            pattern_tab[cg,int(pattern[b]),hit]+=1
            boundary[cg,ci,hit]+=1
            d=0 if cg<og else 2 if cg>og else 1
            ent=int(cg!=int(prv[b])//16)
            counts[cg,d,ent,hit]+=1
    row_matrix=[]
    for og in range(5):
        for cg in range(5):
            for oldpos in range(16):
                for newpos in range(16):
                    z0,z1=map(int,matrix[og,cg,oldpos,newpos])
                    if z0+z1==0:continue
                    row_matrix.append(dict(before_pool=LABELS[og],
                      now_pool=LABELS[cg],before_position=oldpos+1,
                      now_position=newpos+1,target0=z0,target1=z1,
                      total=z0+z1,actual_hit_pct=round(z1/(z0+z1)*100,6)))
    row_pat=[]
    for q in range(5):
        for a in range(16):
            n0,n1=map(int,pattern_tab[q,a])
            row_pat.append(dict(current_pool=LABELS[q],
                 last_four_1_0=format(a,"04b"),
                 target0=n0,target1=n1,total=n0+n1,
                 rate_pct=round(n1/(n0+n1)*100,6) if n0+n1 else None))
    row_pos=[]
    for q in range(5):
        for pos in range(16):
            n0,n1=map(int,boundary[q,pos])
            row_pos.append(dict(current_pool=LABELS[q],within_16_position=pos+1,
              target0=n0,target1=n1,total=n0+n1,
              rate_pct=round(100*n1/(n0+n1),6) if n0+n1 else None))
    row_flux=[]
    for q in range(5):
        for di in range(3):
            for e in range(2):
                n0,n1=map(int,counts[q,di,e])
                row_flux.append(dict(current_pool=LABELS[q],direction=DIRECTIONS[di],
                    entered_other_16_bin_since_previous_draw=e,
                    target0=n0,target1=n1,total=n0+n1,
                    rate_pct=round(100*n1/(n0+n1),6) if n0+n1 else None))
    # Compare rank-position occupancy and last-four pattern against fair 25%.
    print("V78 locked",key,
          f"VALIDATE={best['model_mean']:.6f} TEST={locked['model_mean']:.6f}",
          f"random={locked['control_mean']:.6f},p={locked['paired_p_one_sided']:.5f}",
          flush=True)
    summary=[
      "V78 — 16'LIK HAVUZDA YER/SIRA VE 0/1 DIZISI ILE HEDEF ANALIZI",
      f"72 complete days, {len(rows)} draws; every drawn target has 20 ones+60 zeros.",
      f"Excluded incomplete days={excluded}. Draw-id discontinuities={gaps}.",
      "Target t's prior features always computed only from draws before t.",
      "Five 16-ball tiers based on appearance ranks, equal counts, stable ties.",
      f"Detailed all-day reference N={MAIN}; extra N tested={NS}; lag={LAG} draws.",
      "Exact current within-group rank 1..16, rank12 prior 1..16,",
      "old group -> new group, one-step entering/exiting 16-bin, group direction,",
      "and 4-bit previous result history (e.g. 0011) are cross-tabulated",
      "against target0/target1 only AFTER the target was drawn.",
      "16x16 detailed transitions cross 5 old x 5 new groups, plus 16 previous bit patterns.",
      "",
      f"TRAIN Aug29–Sep12 3255 targets; VALIDATE Sep13–Sep27 3255 targets;",
      f"HOLDOUT Sep28–Oct12 3255 targets; all have prior N+lag uninterrupted data.",
      "Candidate models fixed in advance:",
    ]
    for name in FEATURES:summary.append(f"  {name}: {STATESIZE[name]} historical feature states")
    summary+=["",
      f"VALIDATION selected model N={key[0]}, states={key[1]};",
      f"VALIDATION model mean={best['model_mean']:.5f}/20, random5x4={best['control_mean']:.5f}/20;",
      f"LOCKED HOLDOUT mean={locked['model_mean']:.5f}/20, quota random={locked['control_mean']:.5f}/20.",
      f"HOLDOUT model-random diff={locked['model_minus_control']:+.5f}, "
        f"paired one-sided p={locked['paired_p_one_sided']:.6f}.",
      f"HOLDOUT against fair 5.00000 mean, normal approximation p="
        f"{locked['fair_p_one_sided']:.6f}.",
      f"HOLDOUT hits 7+={locked['hit_7plus']}, 8+={locked['hit_8plus']},"
        f" 9+={locked['hit_9plus']},10+={locked['hit_10plus']}.",
      "",
      "AFTER SELECTING N AND RULE, DO NOT PICK A DIFFERENT 'WINNER' FROM HOLDOUT.",
      "Full 5x5x16x16, last-four-bit results describe frequencies;",
      "there is no causal reason an independent RNG must rebalance labels.",
      "The 72-day data have been heavily used in earlier V64–V77 experiments.",
      "Therefore any apparent historical hit advantage is not prospective proof.",
      "Saved reports: all 15,624-day target past rank trajectory N60; 3,255 locked",
      "20-ball predictions; 5x5x16x16 location flows, 5x16 position rates, 5x16",
      "prior-binary patterns, 5x3x2 entrance/exit groups and all 24 models' scores.",
      ""]
    dest=Path(out);dest.parent.mkdir(exist_ok=True,parents=True)
    with zipfile.ZipFile(dest,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as z:
        z.writestr("00_V78_KISA_BULGULAR.txt","\n".join(summary),
                   compress_type=zipfile.ZIP_DEFLATED)
        export_csv(z,"01_4_REFERANS_6_YONTEM_VAL_TEST_ISABET.csv",scores)
        export_csv(z,"02_VALIDASYON_24_YONTEM_SIRALAMA.csv",validation_rows)
        stream_gz(z,"03_72GUN_16LIK_IC_SIRA_ESKI_SIRA_SON4BIT_HEDEF10.csv.gz",
          ["gun","saat","cekilis","gun_sirasi","sayi","ref60_cikma",
           "yeni_havuz","simdiki_sira_1_16",
           "12_onceki_havuz","12_onceki_sira_1_16",
           "kac_havuz_isi_yonu","yon","onceki_adim_havuz_degisti",
           "onceki_dort_hedef_biti_kronolojik","onceki4_decimal",
           "onceki_hedef_1_0","hedef_1_0"],
          all_main_identity_ledger(rows,y,prefix,main_rank,main_valid))
        export_csv(z,"04_TAM_5x5x16x16_HAVUZ_YER_GECIS_HEDEF01.csv",row_matrix)
        export_csv(z,"05_SON_DORT_HEDEF_1_0_DIZI_X_5_HAVUZ.csv",row_pat)
        export_csv(z,"06_HAVUZ_ICI_SIRA_1_16_HEDEF_1_0.csv",row_pos)
        export_csv(z,"07_YON_GIRIS_HAVUZ_HEDEF_01.csv",row_flux)
        export_csv(z,"08_SECILEN_KILITLI_YONTEM_3255_HEDEF_20LI.csv",tickets)
        stream_gz(z,"09_KILITLI_YONTEM_3255x80_SAYI_KIMLIK_HEDEF01.csv.gz",
             ["gun","cekilis","sayi","havuz_simdi",
              "sira_1_16","havuz_12_once",
              "sira_12_once_1_16","yon",
              "onceki_dort_hedef_biti",
              "secildi_1_0","gercek_hedef_1_0"],
             ([r["day"],r["id"],r["ball"],r["pool_now"],r["rank1_16"],
               r["pool_12before"],r["rank12before1_16"],r["direction"],
               r["prev4_binary"],r["selected"],r["target_1_or_0"]] for r in identity))
        export_csv(z,"10_TEST_15_GUN_20LI_RASTGELE_KARSILASTIRMA.csv",daily)
        state_rows=[dict(model=key[1],state_id=i,
             train_opportunities=int(ncount[i]),
             train_hit1=int(nhit[i]),
             calibrated_prob1=round(float(probs[i]),9))
             for i in range(len(probs))]
        export_csv(z,"11_KILITLI_YONTEM_EGITIM_OLASILIKLARI.csv",state_rows)
        z.writestr("12_NASIL_HESAPLANDI.txt","\n".join([
          "All 80 balls ranked by count of PREVIOUS N draws, sorted ascending.",
          "Ties remain in the previous time step's rank, not arbitrary identity flips.",
          "5 consecutive 16-ball ranks form cold to hot buckets.",
          "Current exact rank 1..16, rank at t-12 1..16, current/old pool.",
          "Last four binary input bits are actual target results at t-4,t-3,t-2,t-1.",
          "Target result at t is never used in t's pre-draw feature construction.",
          "For 72-day descriptive full-ledger main N=60, all valid targets.",
          "No ID-discontinuous target used in any historical transition rate.",
          "23 Aug 2026 incomplete day excluded, gap must not be compressed.",
          "Prior-training only 29Aug–12Sep, fixed alpha250 prior 0.25.",
          "Candidate feature groups 30,160,2560,240,1280,3840 stated above.",
          "Validation picks N and model by mean-.25*sd of its 15 daily means.",
          "Holdout kept untouched until validation model frozen.",
          "Every candidate selected pool has exactly four from each 16-member bucket.",
          "Same seeded uniform random tie breaks and four-per-bucket control.",
          "Under fair independent lottery RNG, 20 pre-selected balls hit mean 5.",
          "Paired difference null variance accounts for shared selected identities.",
          "These historical days previously studied by many versions; no future proof.",
          "CSV.GZ files inside ZIP are compressed text CSV; decompress to inspect."
        ]),compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("13_AUDIT.json",json.dumps(dict(
             version=VER,days=days,skipped_days=excluded,gaps=gaps,
             total_complete_targets=len(rows),valid_main=int(main_valid.sum()),
             references=NS,lag=LAG,bit_history=BITCOUNT,
             fixed_models=FEATURES,alpha=ALPHA,seed=SEED,
             chosen_key=key,validation=best,holdout=locked,
             all_model_comparison=scores,
             matrix_cells=len(row_matrix),historical_patterns=len(row_pat),
             input_issues=issues[:20],invalid_lines=malformed[:20]),
             indent=2,ensure_ascii=False),compress_type=zipfile.ZIP_DEFLATED)
    print("\n".join(summary),flush=True)
    print("V78 ZIP",dest,dest.stat().st_size,flush=True)

def selftest():
    rng=np.random.default_rng(78)
    y=np.zeros((500,80),dtype=np.uint8)
    for t in range(len(y)):
        y[t,rng.choice(80,20,replace=False)]=1
    p=prefixize(y)
    rr=rolling_ranks(p,60)
    idx=np.arange(300,400)
    f=feature_arrays(rr,y,idx)
    assert np.all(np.bincount(f["group"][0],minlength=5)==[16]*5)
    assert np.all(f["curpos"]<=15)
    for name in FEATURES:
        state=state_code(f,name)
        assert state.min()>=0 and state.max()<STATESIZE[name],name
        prob,count,hit=fit(state,y[idx],STATESIZE[name])
        assert count.sum()==len(idx)*80
        pick=allocate(f["group"],prob,state,rng.random((len(idx),80)))
        assert np.all(pick.sum(axis=1)==20)
        for group in range(5):
            assert np.all((pick*(f["group"]==group)).sum(axis=1)==4)
    assert abs(fair_p(500,100)-.5)<.1
    print("V78 SELFTEST OK",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",default="veri.txt")
    parser.add_argument("--out",default="v78_output/V78_72GUN_16LIK_IC_SIRA_YON_SON4BIT_HEDEF01.zip")
    parser.add_argument("--selftest",action="store_true")
    args=parser.parse_args()
    if args.selftest:selftest()
    else:main(args.source,args.out)
