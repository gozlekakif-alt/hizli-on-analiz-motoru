#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V100C — TRUE ROLLING FIFO, 56 x12 rings, one draw at a time.

Original V100A is preserved. This corrects its ring-boundary *lifecycle*:
- Stable absolute ring IDs: drawing index //12, NEVER relabel on every draw.
- Fixed 672-observed-draw memory [target-672, target). Every new observed
  draw comes IN and exactly one oldest draw falls OUT, FIFO.
- At t divisible by12: 56 COMPLETE rings of 12.
- Between boundaries: 55 COMPLETE + old PARTIAL (12-r) + young
  PARTIAL (r), totalling 57 rings and exactly 672 observations.
- A partial new ring becomes COMPLETE after 12 fresh draws. The oldest
  partial expires at exactly the same boundary; cycle repeats.
- Ring-local 12-draw relative pool can be displayed in-progress, but
  signal scoring uses only SEALED complete 12-draw rings.
- Historical 72-draw temp at each ring endpoint only uses information
  available by that endpoint. No target draw in any feature.
- Phase 36/18/18 full days; paired HOT72 baseline on same target IDs.
The source dates were repeatedly investigated before V100C; a historical
holdout is NOT unseen prospective evidence or a guarantee of edge.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,io,json,math,random,zipfile
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V100C.1"
CAPACITY=672
GROUP=12
FULL_RINGS=CAPACITY//GROUP
HISTORY_WARMUP=60
FIRST_TARGET=CAPACITY+HISTORY_WARMUP
SEED=100172672
POOL=("SOGUK","SERIN","NOTR","ILIK","SICAK")
MODELS=("HOT72","RISING_COMPLETED6","HOT_COMPLETED6",
        "LAST_COMPLETED_TEMP","ACTIVE_PREVIEW")
CANDIDATES=MODELS[1:]

def load(src):
    d,issues,bad=parse_txt(src)
    # Keep V9-V100 historical baseline unchanged. As new live draws are
    # appended after 12 Oct, accept complete OR partly populated later days
    # without resetting the existing absolute 12-draw ring identities.
    full={day:arr for day,arr in d.items() if len(arr)==217 and
          [r["pos"] for r in arr]==list(range(1,218))}
    baseline=sorted(day for day in full if day<="2026-10-12")
    if len(baseline)!=72 or baseline[0]!="2026-08-01" or baseline[-1]!="2026-10-12":
        raise ValueError("Historical 72 complete days not available")
    later=sorted(day for day,arr in d.items() if day>"2026-10-12" and arr)
    days=baseline+later
    rows=[row for date in baseline for row in full[date]]
    for date in later:
        newer_rows=sorted(d[date],key=lambda r:r["pos"])
        # No future leakage: only actually supplied draws are ingested.
        rows.extend(newer_rows)
    # IDs strictly ordered; prohibit silent reordering when partial
    # daily uploads arrive out of sequence.
    if any(int(rows[i]["id"])<=int(rows[i-1]["id"]) for i in range(1,len(rows))):
        raise ValueError("Draw IDs are not strictly increasing")
    X=np.zeros((len(rows),80),dtype=np.uint8)
    for i,row in enumerate(rows):
        X[i,np.asarray(row["nums"],dtype=np.int16)-1]=1
    if len(rows)<15624 or np.any(X.sum(axis=1)!=20):
        raise ValueError("Invalid 20-of-80 drawn numbers")
    return days,rows,X,issues,bad

def temperature(counts):
    """Relative temperature pool: 16 members per pool, identity tie."""
    order=np.lexsort((np.arange(80),counts))
    result=np.empty(80,dtype=np.int8)
    result[order]=np.repeat(np.arange(5,dtype=np.int8),16)
    return result

def groups(prefix,t):
    """Exact stable absolute group bounds inside FIFO [t-672,t)."""
    start=t-CAPACITY
    assert start>=HISTORY_WARMUP and t<=len(prefix)-1
    first=start//GROUP
    last=(t-1)//GROUP
    out=[]
    for ring in range(first,last+1):
        left=max(start,ring*GROUP)
        right=min(t,(ring+1)*GROUP)
        num=right-left
        completed=(num==GROUP)
        assert 1<=num<=GROUP
        local=prefix[right]-prefix[left]
        trailing=prefix[right]-prefix[right-72]
        # Include absolute draw ranges for integrity auditing.
        out.append(dict(ring=ring,first=left,end=right,size=num,
            sealed=completed,local=local,relative12=temperature(local),
            relative72=temperature(trailing)))
    assert sum(v["size"] for v in out)==CAPACITY
    remainder=t%GROUP
    assert len(out)==(FULL_RINGS if remainder==0 else FULL_RINGS+1)
    assert sum(v["sealed"] for v in out)==(FULL_RINGS if remainder==0 else FULL_RINGS-1)
    if remainder:
        assert out[0]["size"]==12-remainder
        assert out[-1]["size"]==remainder
        assert all(v["size"]==12 for v in out[1:-1])
    else:
        assert all(v["size"]==12 for v in out)
    return out

def top20(score):
    return np.lexsort((np.arange(80),-score))[:20]

def random20(drawid):
    h=hashlib.blake2b(f"{SEED}|{drawid}".encode(),digest_size=8).digest()
    return np.asarray(random.Random(int.from_bytes(h,"big")).sample(range(80),20))

def score(g,prefix,t):
    # Only full rings are used in history-based forecast candidates;
    # live/newest preview is deliberately labeled exploratory.
    sealed=[v for v in g if v["sealed"]]
    S=np.stack([v["relative72"] for v in sealed],axis=1).astype(np.int8)
    end=S[:,-1]
    d=np.diff(S,axis=1)
    latest=sealed[-1]
    freq72=(prefix[t]-prefix[t-72]).astype(float)
    recent72=(prefix[latest["end"]]-prefix[latest["end"]-72]).astype(float)
    h6=(S[:,-6:]==4).sum(axis=1)
    net6=S[:,-1]-S[:,-7]
    eps=freq72/1000.+(79-np.arange(80))/1e7
    active=g[-1]
    # Active PREVIEW is an unsealed ring if only 1..11 new draws;
    # its values update each new draw and cannot be treated as final.
    return {
        "HOT72":freq72,
        "RISING_COMPLETED6":net6*20+eps,
        "HOT_COMPLETED6":h6*20+eps,
        "LAST_COMPLETED_TEMP":end*20+eps,
        "ACTIVE_PREVIEW":active["relative12"]*20+eps
    },dict(sealed_s=S,latest72=end,net6=net6,
            freq72=freq72,preview_12=active["relative12"],
            full_last=sealed[-1]["ring"],
            latest_ring=active["ring"],preview_length=active["size"],
            completed_total=len(sealed))

def compile_stats(recs):
    summaries=[]
    for phase in ("TRAIN","VALIDATE","HOLDOUT"):
        subset=[r for r in recs if r["phase"]==phase]
        if not subset:continue
        base=np.asarray([r["HOT72_hit"] for r in subset],float)
        rand=np.asarray([r["RANDOM20_hit"] for r in subset],float)
        for m in MODELS:
            hits=np.asarray([r[m+"_hit"] for r in subset],float)
            summaries.append(dict(phase=phase,model=m,n=len(subset),
                mean_hits=float(hits.mean()),baseline_hot72=float(base.mean()),
                baseline_random20=float(rand.mean()),
                gain_vs_hot72=float(np.mean(hits-base)),
                eightplus=int((hits>=8).sum()),nineplus=int((hits>=9).sum()),
                tenplus=int((hits>=10).sum()),
                max_hits=int(hits.max())))
    winners=[r for r in summaries if r["phase"]=="VALIDATE" and r["model"]!="HOT72"]
    best=max(winners,key=lambda r:(r["gain_vs_hot72"],-MODELS.index(r["model"])))
    winner=best["model"] if best["gain_vs_hot72"]>0 else "HOT72"
    byday=collections.defaultdict(list)
    for row in recs:
        if row["phase"]=="HOLDOUT":
            byday[row["day"]].append(row[winner+"_hit"]-row["HOT72_hit"])
    d=np.asarray([np.mean(a) for a in byday.values()])
    delta=float(d.mean())
    half=float(1.96*d.std(ddof=1)/np.sqrt(len(d)))
    return summaries,winner,dict(selected=winner,val_gain_vs_hot72=best["gain_vs_hot72"],
        hold_day_gain=delta,hold_ci95=[delta-half,delta+half],hold_days=len(d))

def analyze(days,rows,X):
    prefix=np.vstack((np.zeros((1,80),dtype=np.int32),
                      np.cumsum(X,axis=0,dtype=np.int32)))
    phase={day:("TRAIN" if i<36 else ("VALIDATE" if i<54 else "HOLDOUT"))
           for i,day in enumerate(days)}
    targets=[]
    mechanism=[]
    lastfilm=[]
    recent=[]
    movements=collections.defaultdict(lambda:[0,0])
    transition_examples=collections.defaultdict(lambda:[0,0])
    previous_ids=None
    for t in range(FIRST_TARGET,len(rows)):
        g=groups(prefix,t)
        sc,features=score(g,prefix,t)
        sel={m:top20(v) for m,v in sc.items()}
        y=X[t]
        sample={m:int(y[v].sum()) for m,v in sel.items()}
        target=rows[t]
        picked=random20(target["id"])
        targets.append(dict(phase=phase[target["day"]],day=target["day"],
             target_id=target["id"],time=target["time"],
             oldest_draw=rows[t-CAPACITY]["id"],
             latest_draw=rows[t-1]["id"],
             stored_draws=CAPACITY,
             oldest_ring_size=g[0]["size"],newest_ring_size=g[-1]["size"],
             ring_count=len(g),completed_ring_count=features["completed_total"],
             sealed_ring_count=sum(v["sealed"] for v in g),
             preview_is_partial=int(not g[-1]["sealed"]),
             RANDOM20_hit=int(y[picked].sum()),
             **{m+"_hit":sample[m] for m in MODELS},
             last_completed_20="-".join(map(str,(sel["LAST_COMPLETED_TEMP"]+1))),
             hottest72_20="-".join(map(str,(sel["HOT72"]+1)))))
        # Per-target mechanistic ledger, proving no ring is ever reset.
        previous_ids_current=[r["ring"] for r in g]
        mechanism.append(dict(phase=phase[target["day"]],target_id=target["id"],
            oldest_record_id=rows[t-CAPACITY]["id"],last_record_id=rows[t-1]["id"],
            n_rings=len(g),n_full_rings=sum(v["sealed"] for v in g),
            oldest_ring_global_id=g[0]["ring"],
            oldest_ring_draws=g[0]["size"],
            newest_ring_global_id=g[-1]["ring"],
            newest_ring_draws=g[-1]["size"],
            ring_birth=int(t>FIRST_TARGET and t%GROUP==1),
            ring_retirement=int(t>FIRST_TARGET and t%GROUP==0),
            all_ring_draws=CAPACITY,
            ring_ids_monotonically_increase=int(
                previous_ids is None or
                all(x in set(previous_ids) for x in previous_ids_current[1:-1]))))
        previous_ids=previous_ids_current
        # Empirical transitions evaluated on next DRAW, not as betting tips.
        S=features["sealed_s"]
        trend=np.sign(features["net6"])
        for idx in range(80):
            key=(phase[target["day"]],int(features["latest72"][idx]),
                 int(trend[idx]),features["preview_length"])
            movements[key][0]+=1
            movements[key][1]+=int(y[idx])
        if t==len(rows)-1:
            for q in g:
                for n in range(80):
                    lastfilm.append(dict(target_id=target["id"],
                        ball=n+1,absolute_ring_id=q["ring"],status=(
                          "SEALED" if q["sealed"] else "PARTIAL"),
                        ring_start_index=q["first"],ring_end_index_exclusive=q["end"],
                        first_observed_draw_id=rows[q["first"]]["id"],
                        last_observed_draw_id=rows[q["end"]-1]["id"],
                        drawings_in_ring=q["size"],
                        count_in_ring=int(q["local"][n]),
                        pool12=POOL[int(q["relative12"][n])],
                        pool72=POOL[int(q["relative72"][n])],
                        rank12=int(q["relative12"][n]),
                        rank72=int(q["relative72"][n])))
            for n in range(80):
                recent.append(dict(number=n+1,
                    latest_completed_pool72=POOL[int(features["latest72"][n])],
                    live_preview_pool12=POOL[int(features["preview_12"][n])],
                    rising_last6=int(features["net6"][n]),
                    completed_rings=features["completed_total"],
                    live_newest_draws=features["preview_length"],
                    target_draw_occurred=int(y[n])))
        if (t-FIRST_TARGET)%2000==0:
            print(f"V100C analyzed {t}/{len(rows)} targets",flush=True)
    scores,winner,sel_stats=compile_stats(targets)
    grouping=[dict(phase=p,completed_pool=POOL[temp],ring_direction=trend,
             new_partial_length=partial,n=n,hits=h,hit_pct=100*h/n)
             for (p,temp,trend,partial),(n,h) in sorted(movements.items())]
    return targets,mechanism,lastfilm,recent,grouping,scores,winner,sel_stats

def csvfile(z,name,rows):
    if not rows:return
    with z.open(name,"w",force_zip64=True) as f:
        x=io.TextIOWrapper(f,encoding="utf-8",newline="")
        w=csv.DictWriter(x,fieldnames=list(rows[0].keys()))
        w.writeheader();w.writerows(rows)
        x.flush();x.detach()

def make_report(targets,mechanism,film,grouping,scores,winner,sel_stats):
    last=mechanism[-1]
    complete=sum(r["n_full_rings"]==56 for r in mechanism)
    partial=sum(r["n_full_rings"]==55 for r in mechanism)
    hold=[v for v in scores if v["phase"]=="HOLDOUT"]
    valid=sorted((v for v in scores if v["phase"]=="VALIDATE"),
                 key=lambda x:-x["gain_vs_hot72"])
    selected=next(v for v in hold if v["model"]==winner)
    hot=next(v for v in hold if v["model"]=="HOT72")
    report=[
        "V100C | GERCEK YURUYEN FIFO HALKA MEKANIZMASI (V100A KORUNDU)",
        "Each incoming draw enters new 12-ring while oldest draw exits old ring.",
        "12 incoming => newest ring closes, oldest expires; constant 672 observations.",
        "Absolute ring IDs never shifted/rebuilt. 56 full at boundary, otherwise",
        "55 full rings + 11..1 oldest remainder + 1..11 newest partial = 57 rings.",
        "Every target strictly excludes its own (unseen) result from the 672 memory.",
        f"Validated target draws: {len(targets)}; full 56-ring moments: {complete}; between-ring moments: {partial}.",
        f"Last target #{targets[-1]['target_id']}: {last['n_rings']} rings, {last['n_full_rings']} sealed,",
        f"oldest ring length={last['oldest_ring_draws']}, newest ring length={last['newest_ring_draws']}.",
        f"Births of next rings={sum(r['ring_birth'] for r in mechanism)}, expired old rings={sum(r['ring_retirement'] for r in mechanism)}.",
        "All 80 balls tracked. Ring-end 72 snapshot and completed ring 12 snapshot",
        "separately. Unfinished ring snapshot explicitly labeled PREVIEW.",
        "",
        "Validation, same-target 20-number averages: "
    ]
    for row in valid:
        report.append(f" {row['model']:23s}: hits={row['mean_hits']:.6f} HOT72={row['baseline_hot72']:.6f} delta={row['gain_vs_hot72']:+.6f}")
    report+=["",f"Chosen on validation: {winner}",
        f"Holdout {winner}: mean={selected['mean_hits']:.6f}; HOT72={hot['mean_hits']:.6f}; RAND20={hot['baseline_random20']:.6f}.",
        f"Holdout difference vs HOT72={selected['gain_vs_hot72']:+.6f}.",
        f"Day-block 95% approx CI=[{sel_stats['hold_ci95'][0]:+.6f}, {sel_stats['hold_ci95'][1]:+.6f}].",
        "Expected fair 20-ball ticket hits per draw: 5.",
        "Caution: past corpus reused repeatedly. Retrospective comparison is NOT",
        "independent prospective evidence. No betting profit or RNG decoding claimed.",
        "CSV includes 80-ball x 56/57 ring final film, FIFO ledger for EVERY target",
        "and all matched holdout predictions."]
    return "\n".join(report)+"\n"

def run(args):
    days,rows,X,issues,bad=load(args.source)
    targets,mechanism,film,recent,grouping,scores,winner,stats=analyze(days,rows,X)
    metadata=dict(version=VERSION,ring_size=12,max_memory=672,
      no_draw_future_leakage=True,
      definition="stable absolute 12-draw ring ids with oldest/newest partial",
      valid_dates=[days[0],days[-1]],real_draws=len(rows),
      new_after_baseline=max(0,len(rows)-15624),
      eligible_targets=len(targets),
      model_selected_using_middle18days=winner,
      controls=stats,source_issues=issues[:20],malformed_lines=bad[:20])
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    report=make_report(targets,mechanism,film,grouping,scores,winner,stats)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        z.writestr("00_GERCEK_YURUYEN_HALKA_RAPORU.txt",report)
        csvfile(z,"01_HER_HEDEF_FIFO_HALKA_GIRIS_CIKIS_KAYDI.csv",mechanism)
        csvfile(z,"02_HER_HEDEF_5_MODEL_HEDEF_KONTROL.csv",targets)
        csvfile(z,"03_SON_HEDEF_80_SAYI_STABIL_HALKA_FILMI.csv",film)
        csvfile(z,"04_SON_HEDEF_80_SAYI_CANLI_DURUM.csv",recent)
        csvfile(z,"05_HAVUZ_YON_VE_HALKADAKI_12_TAMAMLANMA.csv",grouping)
        csvfile(z,"06_DOGRULAMA_VE_KOR_TEST_SONUC.csv",scores)
        z.writestr("07_METOT_DENETIM.json",json.dumps(metadata,ensure_ascii=False,
                   default=str,indent=2))
    print(report,flush=True)
    print("V100C COMPLETED",out,out.stat().st_size,flush=True)

def selftest():
    X=np.zeros((768,80),dtype=np.uint8)
    for i in range(768):X[i,np.arange(i,i+20)%80]=1
    p=np.vstack((np.zeros((1,80),dtype=np.int32),
                 np.cumsum(X,axis=0,dtype=np.int32)))
    for t in (732,733,734,735,743,744,745,755,756):
        g=groups(p,t)
        assert sum(r["size"] for r in g)==672
        assert g[0]["first"]==t-672 and g[-1]["end"]==t
        if t%12==0:
            assert len(g)==56 and len([r for r in g if r["sealed"]])==56
        else:
            assert len(g)==57 and len([r for r in g if r["sealed"]])==55
            assert g[0]["size"]+g[-1]["size"]==12
        all_ids=[i for r in g for i in range(r["first"],r["end"])]
        assert all_ids==list(range(t-672,t))
        sc,info=score(g,p,t)
        assert set(sc)==set(MODELS)
        assert all(len(set(top20(v)))==20 for v in sc.values())
    g0=groups(p,732);g1=groups(p,733);g12=groups(p,744)
    assert (len(g0),len(g1),len(g12))==(56,57,56)
    assert g1[0]["ring"]==g0[0]["ring"]
    assert g12[0]["ring"]==g0[0]["ring"]+1
    assert g1[-1]["ring"]==g0[-1]["ring"]+1
    print("V100C FIFO SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v100c_output/V100C_YURUYEN_672_FIFO_12_HALKA.zip")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest()
    else:run(args)
