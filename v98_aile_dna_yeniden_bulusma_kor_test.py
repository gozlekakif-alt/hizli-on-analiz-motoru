#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V98 | Aile DNA'si ve yeniden bulusma: one-draw-forward tests.

A root is the EXACT 6..10 ball intersection of a previously observed draw
with one of its 12 immediate ID-consecutive predecessors, in the past.
Roots stay in a rolling 72 or 217 *observed draw* registry.
At target t (UNSEEN): a root last discovered before t-1 must have exactly
3 or 4 surviving members on the latest known draw t-1. For stable-core
variants those exact members must also co-appear in an earlier last-six draw
(without any use of target t). The selected root (up to 10 distinct numbers)
is completed using the top frequencies of the last72 observed draws.
Only one ten-number ticket is issued by each variant per target.

Historical development / validation / holdout separation: 36/18/18
complete days. Select ONE variant on validation alone (or select NONE),
then report it on holdout exactly as frozen. Matched RANDOM10 and HOT72
controls evaluated on EXACT SAME issued target drawings.
The corpus has already been exhaustively studied: this is a historical
chronological audit, NOT a genuinely untouched prospective test.
"""
from __future__ import annotations
import argparse, collections, csv, io, json, math, random, hashlib, zipfile
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V98.1"
SEED=981016
REGISTRY=(72,217)
CORE=(3,4)
STABLE=(False,True)
MODELS=tuple("CORE%d_%s_R%d"%(c, "STABLE" if s else "ANY", w)
             for w in REGISTRY for c in CORE for s in STABLE)
MIN_VALIDATE=150
N_PER_DAY=217
CONSECUTIVE_LOOKBACK=12

def mask(nums):
    return sum(1 << (int(k)-1) for k in nums)

def members(m):
    return [i+1 for i in range(80) if (m>>i)&1]

def load(path):
    daily,issues,bad=parse_txt(path)
    days=sorted(d for d,r in daily.items()
                if len(r)==N_PER_DAY and
                [x["pos"] for x in r]==list(range(1,N_PER_DAY+1)))
    if len(days)!=72 or days[0]!="2026-08-01" or days[-1]!="2026-10-12":
        raise RuntimeError("Need 72 complete days, got "+str(len(days)))
    rows=[r for day in days for r in daily[day]]
    x=np.zeros((len(rows),80),dtype=np.uint8)
    for i,row in enumerate(rows):x[i,np.asarray(row["nums"],dtype=np.int16)-1]=1
    if len(rows)!=15624 or np.any(x.sum(axis=1)!=20):
        raise RuntimeError("Unexpected corpus size/20-of-80 data")
    return days,rows,x,issues,bad

def discover(i,rows,ms):
    """Roots born at known draw i; previous draw-ID run never crossed."""
    if i==0:return []
    out=set()
    for j in range(i-1,max(i-CONSECUTIVE_LOOKBACK-1,-1),-1):
        if int(rows[j+1]["id"])!=int(rows[j]["id"])+1:break
        root=ms[i]&ms[j]
        if 6<=root.bit_count()<=10:out.add(root)
    return sorted(out)

def stable_core(core,source,ms):
    # Source is most recent observed draw t-1; require co-occurrence in
    # at least one strictly earlier OBSERVED draw of the last 6 frames.
    for i in range(max(0,source-5),source):
        if (ms[i]&core)==core:return True
    return False

def candidates(t,seen,ms,source_mask):
    """Candidate proposals at t depend on t-1 and earlier only.

    Each root registry key -> list of prior discovery draw indexes.
    A root must exist on a past draw earlier than t-1 and remain in the
    72 or 217 draw registry. Exclude current source-created roots, so the
    core is a PARTIAL re-encounter, not a newly discovered full family.
    """
    for win in REGISTRY:
        threshold=t-win
        for root,born in seen.items():
            last=born[-1]
            if last>=t-1 or last<threshold:continue
            core=root&source_mask
            size=core.bit_count()
            if size not in CORE or root.bit_count()-size<2:continue
            stable=stable_core(core,t-1,ms)
            yield win,size,stable,root,last,len(born),core

def proposals(t,seen,ms,frequency):
    if t<217:return {}
    source=ms[t-1]
    options={name:None for name in MODELS}
    for win,k,stable,root,last,nroots,core in candidates(t,seen,ms,source):
        for required in (False,True):
            if required and not stable:continue
            name="CORE%d_%s_R%d"%(k,"STABLE" if required else "ANY",win)
            # Deterministic priority, fully data-independent formula.
            # Number of root sightings is observed BEFORE the target.
            # Full root more recently known or frequently rediscovered
            # gets priority, but this is a hypothesis, not an advantage.
            key=(int(nroots>=2),nroots,-(t-1-last),root.bit_count(),-root)
            old=options[name]
            if old is None or key>old[0]:
                options[name]=(key,root,core,last)
    picks={}
    for name,obj in options.items():
        if obj is None:continue
        _,root,core,last=obj
        chosen=members(root)
        remaining=sorted((n for n in range(1,81) if n not in chosen),
                         key=lambda n:(-int(frequency[n-1]),n))
        chosen=tuple(sorted(chosen+remaining[:10-len(chosen)]))
        assert len(chosen)==10 and len(set(chosen))==10
        picks[name]=(chosen,root,core,last)
    return picks

def rng_ticket(draw_id):
    digest=hashlib.blake2b((str(SEED)+"|"+str(draw_id)).encode(),
                           digest_size=8).digest()
    return tuple(sorted(random.Random(int.from_bytes(digest,"big")).sample(range(1,81),10)))

def hits(target,nums):
    return len(set(target).intersection(nums))

def summarize(records,method,phase):
    arr=[x for x in records if x["model"]==method and x["phase"]==phase]
    if not arr:return None
    n=len(arr)
    days=sorted(set(r["day"] for r in arr))
    delta_by_day=[]
    for d in days:
        a=[r for r in arr if r["day"]==d]
        delta_by_day.append(sum(r["hits"]-r["hot72_hits"] for r in a)/len(a))
    differences=np.array(delta_by_day,dtype=float)
    avg=float(np.mean(differences))
    se=float(np.std(differences,ddof=1)/np.sqrt(len(differences))) if len(differences)>1 else 0
    p=None
    if len(differences)>=5:
        # Calendar-day sign permutation; exploratory only, signed matched
        # gains and repeated family signals can be serially correlated.
        rng=np.random.default_rng(SEED)
        reps=10000
        signs=rng.integers(0,2,size=(reps,len(differences)),dtype=np.int8)*2-1
        means=(signs*differences).mean(axis=1)
        p=(1+int(np.sum(np.abs(means)>=abs(avg))))/(reps+1)
    res=dict(phase=phase,method=method,
        ticket_count=n,days=len(days),
        mean_hits=round(sum(r["hits"] for r in arr)/n,7),
        mean_hot72_matched=round(sum(r["hot72_hits"] for r in arr)/n,7),
        mean_random10_matched=round(sum(r["random_hits"] for r in arr)/n,7),
        theoretical_random_mean=2.5,
        gain_vs_hot72=round(sum(r["hits"]-r["hot72_hits"] for r in arr)/n,7),
        day_mean_gain=round(avg,7),
        day95_low=round(avg-1.96*se,7),
        day95_high=round(avg+1.96*se,7),
        exploratory_day_sign_p=p,
        full_family_reunions=sum(r["family_fully_reunited"] for r in arr),
        theoretical_full_family_expected=round(sum(r["family_null_probability"] for r in arr),6),
        raw=arr)
    for k in range(11):
        res["hits_"+str(k)]=sum(r["hits"]==k for r in arr)
    for k in (5,6,7,8,9,10):
        res[str(k)+"plus"]=sum(r["hits"]>=k for r in arr)
    return res

def save_csv(z,path,rows):
    if not rows:return
    with z.open(path,"w",force_zip64=True) as raw:
        stream=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        writer=csv.DictWriter(stream,fieldnames=list(rows[0].keys()))
        writer.writeheader();writer.writerows(rows)
        stream.flush();stream.detach()

def experiment(days,rows,y):
    # No future target info in discovery, feature construction or ticket.
    n=len(rows)
    mm=[mask(row["nums"]) for row in rows]
    counts=np.zeros(80,dtype=np.int32)
    registered=collections.defaultdict(list)
    events=[]
    first_signals={m:0 for m in MODELS}
    latest_draw_of_root={}
    for t,row in enumerate(rows):
        if t>=217:
            obs=proposals(t,registered,mm,counts)
            day_idx=t//217
            phase="DEVELOP" if day_idx<36 else ("VALIDATE" if day_idx<54 else "HOLDOUT")
            fsort=np.lexsort((np.arange(80),-counts))
            hot=tuple(sorted((fsort[:10]+1).tolist()))
            random10=rng_ticket(row["id"])
            for model,(ticket,root,core,last) in obs.items():
                h=hits(row["nums"],ticket)
                k=root.bit_count()
                familyprob=math.prod((20-j)/(80-j) for j in range(k))
                events.append(dict(
                    model=model,phase=phase,day=row["day"],
                    draw_id=int(row["id"]),last_known_id=int(rows[t-1]["id"]),
                    target_position=t+1,core_size=core.bit_count(),family_size=k,
                    last_root_discovery_id=int(rows[last]["id"]),
                    family="-".join(map(str,members(root))),
                    core="-".join(map(str,members(core))),
                    ticket10="-".join(map(str,ticket)),
                    hits=h,hot72_hits=hits(row["nums"],hot),
                    random_hits=hits(row["nums"],random10),
                    family_fully_reunited=int(root&mm[t]==root),
                    family_null_probability=familyprob))
                first_signals[model]+=1
        # Release target t only AFTER all proposals for t are scored.
        counts+=y[t].astype(np.int32)
        if t>=72:counts-=y[t-72].astype(np.int32)
        for root in discover(t,rows,mm):
            registered[root].append(t)
            latest_draw_of_root[root]=t
        # Evict roots whose LAST discovery is out of longest window.
        if t%12==0:
            stale=[r for r,last in latest_draw_of_root.items() if last<t-max(REGISTRY)-1]
            for root in stale:
                registered.pop(root,None)
                latest_draw_of_root.pop(root,None)
    results=[]
    for phase in ("DEVELOP","VALIDATE","HOLDOUT"):
        for m in MODELS:
            r=summarize(events,m,phase)
            if r:
                obj={k:v for k,v in r.items() if k!="raw"}
                results.append(obj)
    validation=[r for r in results if r["phase"]=="VALIDATE" and
                r["ticket_count"]>=MIN_VALIDATE]
    # Predeclared strict criterion: per-draw net gain against frequency10.
    # Require validation gain positive, else NONE. This preserves abstention.
    winner=max(validation,key=lambda r:(r["gain_vs_hot72"],
                                         r["ticket_count"],
                                         -MODELS.index(r["method"]))) if validation else None
    if winner is not None and winner["gain_vs_hot72"]<=0:winner=None
    name=winner["method"] if winner else "NONE"
    hold=next((r for r in results if r["phase"]=="HOLDOUT" and r["method"]==name),None)
    # Baseline issued always, while signal methods abstain as needed.
    # Coverage for selected winner is among 3906 possible last-18-day draws.
    coverage=hold["ticket_count"]/3906 if hold else 0.0
    return name,hold,results,events,coverage,first_signals

def run(source,out):
    days,rows,y,issues,bad=load(source)
    selected,hold,results,events,coverage,issued=experiment(days,rows,y)
    validations=sorted((x for x in results if x["phase"]=="VALIDATE"),
        key=lambda x:(-x["gain_vs_hot72"],-x["ticket_count"]))
    report=[
        "V98 | AILE DNA + YENIDEN BULUSMA - GECMISTEN SONRAKI CEKILISE KOR TEST",
        "72 full days | 15624 real draws | 10-number ticket issued BEFORE target",
        "Historical 36 days development, 18 days validation and 18 days frozen holdout.",
        "Cores of EXACTLY 3 or 4 members from previously known 6..10 roots.",
        "Family roots discovered with complete observations; registry 72 or 217 draws.",
        "STABLE core must repeat in a second prior drawing within last 6 frames.",
        "Only target t-1 and prior are used to issue a coupon for target t.",
        "Benchmark on the SAME targets: HOT72, seeded RANDOM10, theoretical 2.5.",
        "If all models lose to HOT72 on validation, winner=NONE (do not deploy).",
        "Data previously researched: HOLDOUT is NOT untouched prospective proof.",
        "",
        "VALIDATE, eight frozen candidates (method, coverage count, gain/target vs HOT72):"]
    for r in validations:
        report.append("  %s | n=%d | mean=%.6f | hot=%.6f | delta=%+.6f"%(
          r["method"],r["ticket_count"],r["mean_hits"],r["mean_hot72_matched"],
          r["gain_vs_hot72"]))
    report+=["","VALIDATION-CHOSEN: "+selected]
    if hold:
        report+= [
            "HOLDOUT %s | n=%d | coverage=%.2f%% of 3906 eligible targets"%(
                selected,hold["ticket_count"],coverage*100),
            "Mean hits winner=%.6f matched HOT72=%.6f RANDOM10=%.6f, fair theory=2.5"%(
                hold["mean_hits"],hold["mean_hot72_matched"],
                hold["mean_random10_matched"]),
            "Matched gain to HOT72=%+.6f | daily avg gain CI [%.6f, %.6f], exploratory signflip p=%s"%(
                hold["gain_vs_hot72"],hold["day95_low"],hold["day95_high"],
                hold["exploratory_day_sign_p"]),
            "Winner 5+/6+/7+/8+/9+/10of10: %d/%d/%d/%d/%d/%d"%(
                hold["5plus"],hold["6plus"],hold["7plus"],hold["8plus"],
                hold["9plus"],hold["10plus"]),
            "Complete original family returns %d (fair independent expectation %.4f) over issued draw targets"%(
                hold["full_family_reunions"],
                hold["theoretical_full_family_expected"])]
    else:
        report+=["HOLDOUT selected NONE: no accepted family signal coupon."]
    report+=["","CAUTION: No independent prospective advantage follows from",
       "historical family coincidences. Multiple hypothesis selection remains",
       "and these dates have been examined in prior V9-V97 experiments.",
       "Family intersection signals are defined only after source draw.",
       "A historical family does not make its members due to return.",
       "Commit timestamps before NEW future draws for meaningful evaluation."]
    dest=Path(out);dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_V98_SONUC_KARAR.txt","\n".join(report)+"\n")
        save_csv(z,"01_SEKIZ_MODEL_36_18_18_PERFORMANS.csv",results)
        if selected!="NONE":
            save_csv(z,"02_SECILEN_MODEL_ONCEDEN_10LU_KUPON.csv",
                [e for e in events if e["model"]==selected and
                 e["phase"] in ("VALIDATE","HOLDOUT")])
        save_csv(z,"03_TUM_8_MODELIN_72_GUN_SINYALLERI.csv",events)
        z.writestr("04_DENETIM.json",json.dumps(dict(version=VERSION,
          selected_by_validation=selected,holdout=hold,
          eligible_days=days,total_draws=len(rows),issued_signal_counts=issued,
          n_models=len(MODELS),models=MODELS,source_issues=issues[:20],
          invalid_lines=bad[:20],minimum_validation=MIN_VALIDATE,
          seed=SEED),ensure_ascii=False,indent=2,default=str))
    print("\n".join(report),flush=True)
    print("V98 DONE",dest,dest.stat().st_size,flush=True)

def selftest():
    assert members(mask((1,13,80)))==[1,13,80]
    assert len(rng_ticket(1234))==10
    ms=[mask((1,2,3,4,5,6))]*10
    core=mask((1,2,3))
    assert stable_core(core,9,ms)
    ms[8]=mask((4,5,6))
    assert stable_core(core,9,ms)
    for j in range(4,9):ms[j]=mask((4,5,6))
    assert not stable_core(core,9,ms)
    print("V98 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v98_output/V98_AILE_DNA_YENIDEN_BULUSMA_KOR_TEST.zip")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    selftest() if a.selftest else run(a.source,a.out)
