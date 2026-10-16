#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V91: 8 number states, state AGE/GAP/DIRECTION, and F1..F6 hour PROXIES
plus Markov and REAL PyTorch LSTM, exactly V90 48 past -> next12 target.

IMPORTANT: The original 36-day report's F1..F6 CLUSTER ASSIGNMENT CODE is
not in the repository. The six hour classes here are newly trained
TRAIN-ONLY KMeans PROXIES; labels PROXY_F1..PROXY_F6, NOT exact F1..F6.
No target draw contributes to any input. No claims of discovering RNG seed.

All targets share V90's exact windows, chronological cuts, nonoverlap flags,
and random10 control. State definitions are explicit in RULES and are not
claimed identical to the 25Aug-29Sep 36-day legacy report.
Epoch stopping only on internal development subperiod; validation chooses
policy, holdout discloses untouched *for this executable* comparison.
Older projects have examined this same holdout dates.
"""
from __future__ import annotations
import argparse,collections,csv,io,json,math,zipfile,datetime
from pathlib import Path
import numpy as np
import v90_markov_lstm_48_gecmis_12_hedef as v90

VERSION="V91.2"
STATES=("NEUTRAL","NEW_HOT","HOT","RESTED_HOT","COOLING",
        "WAKING_COLD","COLD","DEEP_COLD")
SMAP={v:k for k,v in enumerate(STATES)}
D=80;H=12;MEM=48;SEED=910016
METHODS=("RANDOM","HOT48","COLD48","MARKOV80","LSTM80",
         "STATE_MARKOV","LSTM_STATE_FPROXY")
WEIGHTS=(.5,.3,.2)
HOURS=6
RULES=(
 "State is created after observing current draw only, before next targets.",
 "Current hit+prior gap>=8 => WAKING_COLD; otherwise current hit and "
 "prior 12 count<=2 and post12>=3 => NEW_HOT; otherwise post12>=5 "
 "and last6>=3 => HOT; otherwise prior12>=5, no hit and gap<=3 => RESTED_HOT.",
 "Prior12>=4, last6<previous6 => COOLING; gap>=12 => DEEP_COLD; "
 "gap>=5 and post12<=2 => COLD; else NEUTRAL.",
 "Age=length of consecutive state occurrence, reset on any 5-min "
 "or draw-ID break. Gap=number of preceding misses since last hit.",
 "Direction = last6 hits minus previous6 hits, clipped /6.",
 "Legacy F1..F6 mapping UNAVAILABLE. New TRAIN-only 6-centroid "
 "hourly first-six profile KMeans = PROXY_F1..PROXY_F6.",
 "Hour features only known after six valid current-hour drawings "
 "(minutes 02,07,12,17,22,27); before then zero hour flags.",
 "Five streams of 80: actual drawn, 8-state numeric normalized, "
 "state-age, gap, and 12-draw direction; plus 6 one-hot hour proxies.",
 "Training only 1Aug..12Sep, validation 13Sep..27Sep, "
 "holdout 28Sep..13Oct, same windows as V90.",
 "No individual state or F-hour proxy inferred from the next 12 draws.",
 "4+,5+,6+ means a single selected ball appears at least 4,5,6 "
 "times across next 12 drawings; does NOT mean full 4/4 family.")

def continuous(a,b):
    return b["id"]==a["id"]+1 and \
      (datetime.datetime.fromisoformat(b["day"]+"T"+b["time"])-
       datetime.datetime.fromisoformat(a["day"]+"T"+a["time"])).total_seconds()==300

def classify_prefix(a):
    """50? no: 80-element vector of counts, prefix is 6x80 only."""
    counts=a.sum(axis=0)
    overlaps=np.sum(a[:-1]*a[1:])
    distinct=int(np.count_nonzero(counts))
    return np.array([np.sum(counts==0),np.sum(counts==1),
       np.sum(counts==2),np.sum(counts>=3),
       overlaps,distinct],dtype=np.float32)/80.

def hour_training_profile(draws,A):
    """Each hour 6 first known draws, never look into second half.
    Bounded by exact same day, hour, minutes 02..27, ID/time continuity."""
    labels={}
    for t in range(5,len(draws)):
        row=draws[t]
        minutes=[2,7,12,17,22,27]
        if int(row["time"][3:])!=27:continue
        p=draws[t-5:t+1]
        if [int(x["time"][3:]) for x in p]!=minutes:continue
        if len({(x["day"],x["time"][:2]) for x in p})!=1:continue
        if not all(continuous(p[i],p[i+1]) for i in range(5)):continue
        labels[(row["day"],row["time"][:2])]=(t,classify_prefix(A[t-5:t+1]))
    return labels

def kmeans_train(x,seed=SEED,k=6):
    """Deterministic kmeans++ with training-only input."""
    if len(x)<k*10:raise RuntimeError(f"Too few first6 training hours: {len(x)}")
    rng=np.random.default_rng(seed)
    cent=[x[int(rng.integers(len(x)))]]
    for _ in range(1,k):
        dist=np.min(np.stack([((x-c)**2).sum(axis=1) for c in cent]),axis=0)
        p=(dist+1e-12)/(dist.sum()+len(dist)*1e-12)
        cent.append(x[int(rng.choice(len(x),p=p))])
    cent=np.stack(cent).astype(np.float32)
    for _ in range(75):
        dist=((x[:,None,:]-cent[None,:,:])**2).sum(axis=2)
        assigned=dist.argmin(axis=1)
        new=np.stack([x[assigned==i].mean(axis=0)
            if np.any(assigned==i) else cent[i] for i in range(k)])
        if np.max(abs(new-cent))<1e-7:break
        cent=new
    # Fixed ordering by ascending zero6 then descending carry.
    order=np.lexsort((-cent[:,4],cent[:,0]))
    return cent[order],dict(training_hours=len(x),
             raw_cluster_count={str(i):int(np.sum(assigned==i)) for i in range(k)})

def feature_history(draws,A,runs):
    """Current-after-draw state computed strictly from prefix,
    8 numeric states exhaustively partition 80 numbers per time."""
    n=len(A)
    features=np.zeros((n,80*5+HOURS),dtype=np.float32)
    state=np.full((n,80),-1,dtype=np.int8)
    age=np.zeros(80,dtype=np.int16)
    old=np.full(80,-1,dtype=np.int8)
    gap=np.zeros(80,dtype=np.int16)
    profile=hour_training_profile(draws,A)
    x=np.array([p for (t,p) in profile.values() if draws[t]["day"]<=v90.CUT_TRAIN],
               dtype=np.float32)
    centers,km=kmeans_train(x)
    hourflags=np.zeros((n,HOURS),dtype=np.float32)
    for (date,hr),(end,obs) in profile.items():
        # Assign class only when 6th observation already occurred.
        k=int(np.argmin(((centers-obs)**2).sum(axis=1)))
        i=end
        while i<n and draws[i]["day"]==date and draws[i]["time"][:2]==hr:
            hourflags[i,k]=1
            i+=1
    for lo,hi in runs:
        age[:]=0;old[:]=-1;gap[:]=24
        for i in range(lo,hi):
            recent=A[max(lo,i-11):i+1]
            prev12=A[max(lo,i-12):i]
            hit=A[i]>0
            count=recent.sum(axis=0)
            previous=prev12.sum(axis=0)
            window6=recent[-6:].sum(axis=0)
            earlier6=A[max(lo,i-11):max(lo,i-5)].sum(axis=0)
            direction=window6-earlier6
            gap=np.where(hit,0,np.minimum(24,gap+1))
            priorgap=np.where(hit,np.maximum(gap,1),gap)
            # Historical prev gap must be known BEFORE current update.
            # Save actual prior gap in next revision? It is computed below.
            new=np.full(80,SMAP["NEUTRAL"],dtype=np.int8)
            new=np.where((gap>=5)&(count<=2),SMAP["COLD"],new)
            new=np.where(gap>=12,SMAP["DEEP_COLD"],new)
            new=np.where((previous>=4)&(direction<0),SMAP["COOLING"],new)
            new=np.where((previous>=5)&(~hit)&(gap<=3),SMAP["RESTED_HOT"],new)
            new=np.where((count>=5)&(window6>=3),SMAP["HOT"],new)
            new=np.where(hit&(previous<=2)&(count>=3),SMAP["NEW_HOT"],new)
            # Waking denotes first hit after >=8 consecutive misses.
            # Here gap was reset by hit; use prefix gap from row i-1
            if i>lo:
                prefix_gap=np.zeros(80,dtype=np.int16)
                for b in range(80):
                    before=np.nonzero(A[max(lo,i-24):i,b])[0]
                    prefix_gap[b]=min(24, i-max(lo,i-24)-1-before[-1]) if len(before) else 24
                new=np.where(hit&(prefix_gap>=8),SMAP["WAKING_COLD"],new)
            age=np.where(new==old,np.minimum(age+1,24),1)
            old=new
            state[i]=new
            block=features[i]
            block[:80]=A[i]
            block[80:160]=new.astype(np.float32)/7.
            block[160:240]=np.log1p(age)/math.log(25)
            block[240:320]=np.log1p(gap)/math.log(25)
            block[320:400]=np.clip(direction/6.,-1,1)
            block[400:406]=hourflags[i]
    return features,state,centers,dict(kmeans=km,
        proxy_assignments=int(hourflags.sum()),training_centroids=centers.round(7).tolist())

def train_state_markov(draws,A,states,runs):
    occur=np.zeros((8,2),dtype=np.int64)
    for lo,hi in runs:
        for i in range(lo,hi-1):
            if draws[i+1]["day"]>v90.CUT_TRAIN:break
            for s in range(8):
                b=states[i]==s
                occur[s,0]+=int(b.sum())
                occur[s,1]+=int((b*(A[i+1]>0)).sum())
    probs=(occur[:,1]+250*.25)/(occur[:,0]+250)
    return probs,occur

def make_model(input_size):
    import torch
    from torch import nn
    class StateLSTM(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm=nn.LSTM(input_size=input_size,hidden_size=32,batch_first=True)
            self.fc=nn.Sequential(nn.LayerNorm(32),nn.Linear(32,3*80))
        def forward(self,x):
            y,_=self.lstm(x)
            return self.fc(y[:,-1]).reshape(-1,3,80)
    return StateLSTM()

def train_extended(train,A,features):
    import torch
    from torch.nn import functional as F
    torch.manual_seed(v90.SEED)
    torch.set_num_threads(2)
    tr=[row for i,row in enumerate(train) if i%6==0]
    cut=int(.80*len(tr))
    fit,val=tr[:cut],tr[cut:]
    def data(rows):
        return (torch.from_numpy(np.stack(
            [features[r["t"]-MEM:r["t"]] for r in rows],axis=0)),
           torch.from_numpy(v90.compute_XY(rows,A)[1]))
    xx,yy=data(fit);vx,vy=data(val)
    model=make_model(features.shape[1])
    opt=torch.optim.AdamW(model.parameters(),lr=.002,weight_decay=.005)
    bestloss=float("inf");bestep=0;best=None;trace=[]
    for epoch in range(1,11):
        model.train()
        perm=np.random.default_rng(v90.SEED+epoch).permutation(len(xx))
        for s in range(0,len(xx),64):
            ix=perm[s:s+64]
            loss=F.binary_cross_entropy_with_logits(model(xx[ix]),yy[ix])
            opt.zero_grad();loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),1.)
            opt.step()
        model.eval()
        with torch.no_grad():devloss=float(F.binary_cross_entropy_with_logits(model(vx),vy))
        trace.append(dict(epoch=epoch,internal_dev_bce=round(devloss,7)))
        if devloss<bestloss-1e-6:
            bestloss=devloss;bestep=epoch
            best={k:v.detach().clone() for k,v in model.state_dict().items()}
        if epoch-bestep>=3:break
    model.load_state_dict(best);model.eval()
    return model,dict(epochs=trace,best_epoch=bestep,
                      fit_examples=len(fit),internal_dev_examples=len(val),
                      best_internal_bce=round(bestloss,7))

def predict_extended(model,features,rows):
    import torch
    answer=[]
    with torch.no_grad():
        for s in range(0,len(rows),128):
            chunk=np.stack([features[r["t"]-MEM:r["t"]] for r in rows[s:s+128]])
            answer.append(torch.sigmoid(model(torch.from_numpy(chunk))).numpy())
    return np.concatenate(answer,axis=0)

def writecsv(z,name,values):
    if not values:return
    with z.open(name,"w",force_zip64=True) as f:
        tx=io.TextIOWrapper(f,encoding="utf-8",newline="")
        w=csv.DictWriter(tx,fieldnames=list(values[0]))
        w.writeheader();w.writerows(values)
        tx.flush();tx.detach()

def stage_stats(rows,scope):
    results=[]
    for stage in ("VALIDATE","HOLDOUT"):
        rr=[r for r in rows if r["stage"]==stage and
            (r["nonoverlap"] if scope=="NONOVERLAP_12" else True)]
        if not rr:continue
        for meth in METHODS:
            obj=dict(stage=stage,scope=scope,method=meth,
                target_windows=len(rr),different_days=len({r["day"] for r in rr}))
            for k in (4,5,6):
                obj[f"mean_{k}plus"]=round(sum(r[f"{meth}_{k}"] for r in rr)/len(rr),7)
                obj[f"random_model_{k}plus"]=round(10*v90.tails()[k],7)
            results.append(obj)
    return results

def run(src,outfile):
    draws,A,runs,gaps,issues,bad=v90.data(src)
    wins=v90.windows(draws,runs)
    train=[x for x in wins if x["stage"]=="TRAIN"]
    validate=[x for x in wins if x["stage"]=="VALIDATE"]
    holdout=[x for x in wins if x["stage"]=="HOLDOUT"]
    print("V91 START",len(draws),len(train),len(validate),len(holdout),flush=True)
    feat,states,centers,featinfo=feature_history(draws,A,runs)
    pp,mat=train_state_markov(draws,A,states,runs)
    mp,base,_=v90.fit_markov(A,draws,runs)
    baseline,baseinfo=v90.train_lstm(train,A)
    extended,extinfo=train_extended(train,A,feat)
    allrows=[]
    for stage,rows in (("VALIDATE",validate),("HOLDOUT",holdout)):
        X,Y,counts=v90.compute_XY(rows,A)
        sp=np.stack([pp[states[r["t"]-1]] for r in rows])
        mpred=v90.eval_markov(X,mp,base)
        bpred=v90.predict_lstm(baseline,X)
        epred=predict_extended(extended,feat,rows)
        for i,r in enumerate(rows):
            ct=X[i].sum(axis=0)
            top={
                "RANDOM":v90.random_top10(r),
                "HOT48":v90.top10(ct),
                "COLD48":v90.top10(-ct),
                "MARKOV80":v90.top10(mpred[i]),
                "STATE_MARKOV":v90.top10(sp[i]),
            }
            scored=dict(stage=stage,day=r["day"],target_id=r["target_draw_id"],
                last_target_id=r["last_draw_id"],nonoverlap=r["nonoverlap"],
                last_known_id=draws[r["t"]-1]["id"],
                last_known_states=";".join(
                    f"{name}:{int((states[r['t']-1]==j).sum())}"
                     for j,name in enumerate(STATES)),
                proxy_F_at_prediction=("PROXY_F"+str(
                     int(np.argmax(feat[r["t"]-1,400:406]))+1)
                     if feat[r["t"]-1,400:406].sum() else "UNKNOWN"))
            for ki,k in enumerate((4,5,6)):
                top["LSTM80"]=v90.top10(bpred[i,ki])
                top["LSTM_STATE_FPROXY"]=v90.top10(epred[i,ki])
                actual=counts[i]>=k
                scored[f"all80_{k}plus"]=int(actual.sum())
                for method in METHODS:
                    chosen=top[method]
                    scored[f"{method}_{k}"]=int(actual[list(chosen)].sum())
                    if k==4:
                        scored[f"{method}_chosen10"]=",".join(str(x+1) for x in chosen)
            allrows.append(scored)
        print("V91 scored",stage,len(rows),flush=True)
    stats=stage_stats(allrows,"NONOVERLAP_12")+stage_stats(allrows,"SLIDING_1")
    val={r["method"]:r for r in stats if r["stage"]=="VALIDATE" and r["scope"]=="NONOVERLAP_12"}
    hold={r["method"]:r for r in stats if r["stage"]=="HOLDOUT" and r["scope"]=="NONOVERLAP_12"}
    candidates=("MARKOV80","LSTM80","STATE_MARKOV","LSTM_STATE_FPROXY","HOT48","COLD48")
    def metric(method):
        return sum(w*(val[method][f"mean_{k}plus"]-val["RANDOM"][f"mean_{k}plus"])
                   for w,k in zip(WEIGHTS,(4,5,6)))
    winner=max(candidates,key=lambda method:(metric(method),-candidates.index(method)))
    # Predefine comparison of extra-state model against same-target base LSTM,
    # regardless of whether validation-selected winner was another model.
    extra={}
    for k in (4,5,6):
        extra[str(k)]=dict(
            extended_state=hold["LSTM_STATE_FPROXY"][f"mean_{k}plus"],
            basic_LSTM=hold["LSTM80"][f"mean_{k}plus"],
            chance=hold["RANDOM"][f"mean_{k}plus"],
            state_minus_basic=round(hold["LSTM_STATE_FPROXY"][f"mean_{k}plus"]-
                                    hold["LSTM80"][f"mean_{k}plus"],7))
    # paired day-bootstrap on the same target12 blocks
    def bootstrap(method,against):
        r=[x for x in allrows if x["stage"]=="HOLDOUT" and x["nonoverlap"]]
        return v90.interval_days(r,method,against,rounds=2500)
    ci_win=bootstrap(winner,"RANDOM")
    ci_extra=bootstrap("LSTM_STATE_FPROXY","LSTM80")
    ci_extra_random=bootstrap("LSTM_STATE_FPROXY","RANDOM")
    report=[
        "V91 — SEKIZ DURUM, YAS, GAP, YON + SAATLIK F-PROXY + MARKOV / REAL LSTM",
        "TARGET: last48 -> NEXT 12, one selected ball occurs >=4, >=5, >=6 times.",
        "NOT equivalent to 4/4, 5/5 or 6/6 EXACT family in a SINGLE draw.",
        f"Observations={len(draws)}, windows dev/val/test="
             f"{len(train)}/{len(validate)}/{len(holdout)}, runs={len(runs)}.",
        "Original 25Aug-29Sep F1..F6 report yields aggregate counts ONLY:",
        "exact F1-F6 classifier/centroids are NOT available in code or report.",
        "V91 uses newly trained chronological 6-centroid first6 features,",
        "named PROXY_F1..PROXY_F6, NOT exact original clusters.",
        "Every state at draw t computed only from drawings through t.",
        "A state transition after seeing t CANNOT predict t retroactively.",
        f"DEV train centroids based on {featinfo['kmeans']['training_hours']} known first-six hours.",
        "STATE_MARKOV next-draw smoothed probabilities fitted DEV ONLY:",
          ", ".join(f"{s}={pp[i]*100:.3f}% (n={mat[i,0]})"
                       for i,s in enumerate(STATES)),
        f"Basic LSTM DEV inner early-stop {baseinfo['early_stop_epoch']},"
         f" augmented-state LSTM {extinfo['best_epoch']}.",
        "Validation uses .5*(4+) +.3*(5+) +.2*(6+) advantage over random10;",
        f"validation-locked winner: {winner} weighted advantage {metric(winner):+.6f}.",
        "",
        "HOLDOUT nonoverlap 12-target blocks, averages out of 10 selected:",
    ]
    for name in METHODS:
        q=hold[name]
        report.append(f" {name}: n={q['target_windows']}, "+
                ", ".join(f"{k}+={q[f'mean_{k}plus']:.6f}"
                        for k in (4,5,6)))
    report+=["",
       "New state-hour LSTM compared with basic LSTM on SAME holdout target:",
    ]
    for k in (4,5,6):
        q=extra[str(k)]
        report.append(f" {k}+: augmented={q['extended_state']:.6f},"
          f" basic={q['basic_LSTM']:.6f}, random={q['chance']:.6f};"
          f" diff_aug_vs_basic={q['state_minus_basic']:+.6f};"
          f" day-bootstrap95={ci_extra[(4,5,6).index(k)]}")
    report+=["",
       f"Chosen validation winner {winner} on HOLDOUT against random:",
    ]
    for ix,k in enumerate((4,5,6)):
        d=hold[winner][f"mean_{k}plus"]-hold["RANDOM"][f"mean_{k}plus"]
        report.append(f" {k}+: difference {d:+.6f}, day-bootstrap95={ci_win[ix]}")
    report+=["",
      "BONUS: legacy 36-day states RESTED_HOT 25.45%, WAKING_COLD 25.18%",
      "etc were deviations of under 0.5 percentage points from chance.",
      "Legacy transitions labelled 100% next-hit can be DEFINITIONAL;",
      "must NOT use after-target states as pre-target features.",
      "No proof of RNG seed, clock linkage, draw filters or predictable gains.",
      "Previously examined historical dates are not truly unseen future.",
      "Any new advantage needs genuinely new sealed target predictions."]
    out=Path(outfile);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as z:
        z.writestr("00_V91_SEKIZ_KATMAN_MARKOV_LSTM_KISA_KARAR.txt","\n".join(report))
        writecsv(z,"01_7_YONTEM_VAL_HOLDOUT_NONOVERLAP_SLIDING.csv",stats)
        writecsv(z,"02_HER_HEDEF48_12_SEKIZ_DURUM_AILE_PROXY_ISABET.csv",allrows)
        writecsv(z,"03_LSTM_BASIC_TRAIN_ONLY_EPOCH.csv",baseinfo["history"])
        writecsv(z,"04_LSTM_STATES_FPROXY_TRAIN_ONLY_EPOCH.csv",extinfo["epochs"])
        z.writestr("05_ZAMAN_VE_KAYNAK_DISIPLINI.txt","\n".join(RULES))
        z.writestr("06_AUDIT.json",json.dumps(dict(
           version=VERSION,data_latest_id=draws[-1]["id"],
           windows_train=len(train),windows_validate=len(validate),
           windows_holdout=len(holdout),
           nonoverlap_validate=sum(x["nonoverlap"] for x in validate),
           nonoverlap_holdout=sum(x["nonoverlap"] for x in holdout),
           states=STATES,markov_state_probability=pp.tolist(),
           state_frequency_train=mat.tolist(),proxy_centroids_train=featinfo,
           train_basic_lstm=baseinfo,train_extended_lstm=extinfo,
           validation_selected_winner=winner,
           validation_winner_gain=metric(winner),
           holdout_state_vs_base=extra,
           bootstrap_winner_vs_random=ci_win,
           bootstrap_extended_vs_basic=ci_extra,
           bootstrap_extended_vs_random=ci_extra_random,
           stage_metrics=stats,
           gaps=gaps[:30],input_issues=issues[:30],
           malformed=bad[:30]),ensure_ascii=False,indent=2))
    print("\n".join(report),flush=True)
    print("V91 OUTPUT",out,out.stat().st_size,flush=True)

def selftest():
    assert len(STATES)==8
    assert np.isclose(classify_prefix(np.zeros((6,80),np.float32))[0],1)
    assert make_model(406).__class__
    import torch
    m=make_model(406)
    assert tuple(m(torch.zeros(2,48,406)).shape)==(2,3,80)
    print("V91 SELFTEST OK",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--out",default="v91_output/V91_8DURUM_YAS_GAP_YON_FPROXY_MARKOV_LSTM_48_12.zip")
    p.add_argument("--selftest",action="store_true")
    x=p.parse_args()
    if x.selftest:selftest()
    else:run(x.source,x.out)
