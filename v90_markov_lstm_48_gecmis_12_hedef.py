#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V90: audit Markov and REAL LSTM for RNG serial bias, 48 -> future 12.

Target for each of the 80 individual balls:
X_{i,t} = number of appearances in draws t..t+11.
Three binary labels: X>=4, X>=5, X>=6.
Every prediction sees ONLY the preceding 48 drawings. Never equate
"ball appeared >=4 times in one hour" with a 4/4 same-draw FAMILY.

All windows fit in uninterrupted five-minute run with consecutive IDs.
DEV targets <=12Sept train Markov and Torch LSTM; validate Sept13..27,
holdout Sep28..Oct13, all three in chronological target-date order.
Markov first-order 80x80 conditioned on PREVIOUS PRESENT balls, smoothed
to DEV-only marginal; recurrence approximates 12-draw expectations.
LSTM is a real torch.nn.LSTM input 48x80, 32 hidden units, 3x80 outputs.
No train/val/holdout target contamination, no test-aware hyperparams.
Within DEVELOPMENT use last 20% to choose LSTM early stopping epoch.
Select one model in VALIDATION on pre-specified 4/5/6 threshold combined
metric and freeze that ranking for HOLDOUT.

Metrics are top10 balls achieving thresholds in NEXT 12 real drawings;
compare to on-target seeded random10, hottest48, coldest48, Markov, LSTM.
More correlated 1-step sliding windows reported separately from
12-step NONOVERLAPPING target blocks with day-bootstrap intervals.
Test for excess next-draw 20/80 overlap vs hypergeometric null.
All result dates previously studied, not prospective proof.
Cryptographic PRNG can be unpredictable despite deterministic algorithm.
Seed/filters cannot be confirmed from results alone.
"""
from __future__ import annotations
import argparse,collections,csv,datetime,hashlib,io,json,math,random,zipfile
from pathlib import Path
import numpy as np
from v52_ayni_cekilis_eslikci_217 import parse_txt

VERSION="V90.1"
SEED=901016
D=80
MEM=48
H=12
CUT_TRAIN="2026-09-12"
CUT_VALID="2026-09-27"
CUT_TEST="2026-10-13"
THRESHOLDS=(4,5,6)
STRATEGIES=("RANDOM","HOT48","COLD48","MARKOV","LSTM")
WEIGHTS=(.50,.30,.20)
EPS=1e-8
def make_seed(*v):
    return int.from_bytes(hashlib.blake2b("|".join(map(str,v)).encode(),digest_size=8).digest(),"big")

def data(source):
    daily,issues,bad=parse_txt(source)
    draws=sorted([r for day in daily for r in daily[day]],
        key=lambda r:(r["day"],r["time"],r["id"]))
    if not draws:raise RuntimeError("empty source data")
    a=np.zeros((len(draws),D),dtype=np.float32)
    time=[]
    for i,r in enumerate(draws):
        a[i,np.array(r["nums"])-1]=1.0
        time.append(datetime.datetime.fromisoformat(r["day"]+"T"+r["time"]))
    runs=[];start=0;gaps=[]
    for i in range(1,len(draws)):
        if draws[i]["id"]!=draws[i-1]["id"]+1 or \
           (time[i]-time[i-1]).total_seconds()!=300:
            runs.append((start,i))
            gaps.append(dict(before=draws[i-1]["id"],
                     after=draws[i]["id"],delta_minutes=(time[i]-time[i-1]).total_seconds()/60))
            start=i
    runs.append((start,len(draws)))
    return draws,a,runs,gaps,issues,bad

def windows(draws,runs):
    out=[]
    for start,stop in runs:
        for t in range(start+MEM,stop-H+1):
            source_day=draws[t-1]["day"]
            target_day=draws[t]["day"]
            last_day=draws[t+H-1]["day"]
            if last_day<=CUT_TRAIN:
                stage="TRAIN"
            elif source_day>CUT_TRAIN and last_day<=CUT_VALID:
                stage="VALIDATE"
            elif source_day>CUT_VALID and last_day<=CUT_TEST:
                stage="HOLDOUT"
            else:
                continue
            out.append(dict(t=t,stage=stage,day=target_day,
                target_draw_id=draws[t]["id"],target_clock=draws[t]["time"],
                last_draw_id=draws[t+H-1]["id"],
                nonoverlap=((t-(start+MEM))%H==0)))
    return out

def tails():
    return {k:sum(math.comb(H,j)*(.25**j)*(.75**(H-j))
            for j in range(k,H+1)) for k in THRESHOLDS}

def fit_markov(A,draws,runs):
    left=[];right=[]
    for a,b in runs:
        for t in range(a+1,b):
            if draws[t]["day"]>CUT_TRAIN:break
            left.append(t-1);right.append(t)
    if not right:raise RuntimeError("no Markov dev transitions")
    past=A[np.array(left)]
    nxt=A[np.array(right)]
    ct=past.T@nxt
    exposures=past.sum(axis=0)
    # P(next ball j | prior observed ball i), Beta-pseudocount
    # smoothly blending global dev-only marginal, not all-time data.
    base=((nxt.sum(axis=0)+.25*300)/(len(right)+300)).astype(np.float64)
    posterior=(ct+base[None,:]*1500)/(exposures[:,None]+1500)
    return posterior.astype(np.float32),base,dict(transitions=len(right),
               row_exposure_min=int(exposures.min()),
               row_exposure_max=int(exposures.max()))

def eval_markov(X,P,base):
    # Returns ranking scores from estimated next-12 marginal p per number.
    # X features are precisely previous48 draws.
    q=X[:,-1,:].astype(np.float64)
    scores=np.zeros_like(q)
    for _ in range(H):
        v=(q@P)/(np.maximum(q.sum(axis=1,keepdims=True),1))
        v=.95*v+.05*base[None,:]
        v=np.clip(v,.00001,.99999)
        q=v*(20/np.maximum(v.sum(axis=1,keepdims=True),EPS))
        scores+=q/H
    return scores

def make_torch_model():
    import torch
    from torch import nn
    class LongSequence(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm=nn.LSTM(input_size=80,hidden_size=32,num_layers=1,batch_first=True)
            self.head=nn.Sequential(nn.LayerNorm(32),nn.Linear(32,3*80))
        def forward(self,x):
            out,_=self.lstm(x)
            return self.head(out[:,-1,:]).reshape(-1,3,80)
    return LongSequence()

def compute_XY(items,A):
    if not items:raise ValueError("no windows")
    X=np.stack([A[q["t"]-MEM:q["t"]] for q in items],axis=0)
    future=np.stack([A[q["t"]:q["t"]+H].sum(axis=0) for q in items])
    Y=np.stack([(future>=k).astype(np.float32) for k in THRESHOLDS],axis=1)
    return X,Y,future

def train_lstm(train,A,epochs=10):
    import torch
    from torch.nn import functional as F
    torch.manual_seed(SEED)
    torch.set_num_threads(2)
    np.random.seed(SEED)
    # Every sixth slide for training, to reduce near-duplicate windows.
    tr=[r for i,r in enumerate(train) if i%6==0]
    if len(tr)<160:raise RuntimeError("not enough DEV windows for LSTM")
    # Internal DEV split by time; never use VALIDATE or HOLDOUT labels.
    cut=int(.80*len(tr))
    fit,internal=tr[:cut],tr[cut:]
    FX,FY,_=compute_XY(fit,A)
    VX,VY,_=compute_XY(internal,A)
    model=make_torch_model()
    optimizer=torch.optim.AdamW(model.parameters(),lr=.002,weight_decay=.005)
    xx=torch.from_numpy(FX)
    yy=torch.from_numpy(FY)
    xv=torch.from_numpy(VX)
    yv=torch.from_numpy(VY)
    best=None;bestloss=1e9;bestep=0;history=[]
    for epoch in range(1,epochs+1):
        model.train();rng=np.random.RandomState(SEED+epoch)
        inds=rng.permutation(len(xx))
        for offset in range(0,len(xx),64):
            chunk=inds[offset:offset+64]
            logit=model(xx[chunk])
            loss=F.binary_cross_entropy_with_logits(logit,yy[chunk])
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
            optimizer.step()
        model.eval()
        with torch.no_grad():
            val=float(F.binary_cross_entropy_with_logits(model(xv),yv).item())
        history.append(dict(epoch=epoch,dev_internal_val_bce=round(val,8)))
        if val<bestloss-0.000001:
            bestloss=val;bestep=epoch
            best={k:v.detach().clone() for k,v in model.state_dict().items()}
        if epoch-bestep>=3:break
    model.load_state_dict(best)
    model.eval()
    return model,dict(train_windows=len(fit),early_stop_windows=len(internal),
        early_stop_epoch=bestep,internal_bce=bestloss,history=history)

def predict_lstm(model,X):
    import torch
    blocks=[]
    with torch.no_grad():
        for a in range(0,len(X),192):
            z=torch.from_numpy(X[a:a+192])
            p=torch.sigmoid(model(z)).numpy().astype(np.float32)
            blocks.append(p)
    return np.concatenate(blocks,axis=0)

def random_top10(row):
    return tuple(sorted(random.Random(make_seed(SEED,row["target_draw_id"])).
            sample(range(80),10)))

def top10(scores):
    # highest score first, ties lowest number first
    return tuple(sorted(np.lexsort((np.arange(80),-np.asarray(scores)))[:10].tolist()))

def interval_days(records, key, win, rounds=2000):
    # Paired day cluster bootstrap: windows per day correlated even
    # though nonoverlap blocks share history; descriptive interval only.
    grouped=collections.defaultdict(list)
    for r in records:
        if r["nonoverlap"]:
            grouped[r["day"]].append(
                (r[f"{key}_4"]-r[f"{win}_4"],
                 r[f"{key}_5"]-r[f"{win}_5"],
                 r[f"{key}_6"]-r[f"{win}_6"]))
    if len(grouped)<3:return [None]*3
    days=sorted(grouped)
    totals=np.array([np.array(grouped[d]).sum(axis=0) for d in days])
    sizes=np.array([len(grouped[d]) for d in days])
    rg=np.random.default_rng(make_seed(SEED,"boot",key,win))
    take=rg.integers(0,len(days),size=(rounds,len(days)))
    bs=totals[take].sum(axis=1)/sizes[take].sum(axis=1)[:,None]
    return [(round(float(np.percentile(bs[:,i],2.5)),6),
             round(float(np.percentile(bs[:,i],97.5)),6)) for i in range(3)]

def metric(records,stage,nonoverlap):
    rr=[r for r in records if r["stage"]==stage and
        (r["nonoverlap"] or not nonoverlap)]
    if not rr:return []
    out=[]
    for method in STRATEGIES:
        d=dict(stage=stage,scope="NONOVERLAP_12" if nonoverlap else "SLIDING_1",
               method=method,windows=len(rr),different_days=len(set(r["day"] for r in rr)))
        for k in THRESHOLDS:
            hit=[r[f"{method}_{k}"] for r in rr]
            d[f"mean_numbers_achieving_{k}plus"]=round(sum(hit)/len(hit),7)
            d[f"iid_theory_{k}plus"]=round(10*tails()[k],7)
        out.append(d)
    return out

def overlap_diagnostics(draws,A):
    pairs=[]
    for i in range(1,len(draws)):
        r=draws[i]
        if r["day"]<"2026-09-28" or r["day"]>CUT_TEST:continue
        prev=draws[i-1]
        a=datetime.datetime.fromisoformat(prev["day"]+"T"+prev["time"])
        b=datetime.datetime.fromisoformat(r["day"]+"T"+r["time"])
        if r["id"]==prev["id"]+1 and (b-a).total_seconds()==300:
            pairs.append(int((A[i-1]*A[i]).sum()))
    if not pairs:return {}
    mean=float(np.mean(pairs));theory=5.
    sd=math.sqrt(20*.25*.75*(60/79))
    # The overlap statistics share a draw with neighbors. No p-value
    # claimed using independent-pair normal standard errors.
    return dict(consecutive_pairs=len(pairs),empirical_shared20_mean=mean,
                iid_expected_shared20=theory,
                theoretical_single_pair_std=sd,
                overlap_0_to_20={str(v):pairs.count(v) for v in range(21)
                    if pairs.count(v)>0},
                warns="serially dependent overlapping pair stats; descriptive only")

def csvfile(z,name,records):
    if not records:return
    with z.open(name,"w",force_zip64=True) as raw:
        tx=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        w=csv.DictWriter(tx,fieldnames=list(records[0]))
        w.writeheader();w.writerows(records)
        tx.flush();tx.detach()

def run(source,outfile):
    draws,A,runs,gaps,issues,bad=data(source)
    records=windows(draws,runs)
    stages=collections.Counter(z["stage"] for z in records)
    tr=[z for z in records if z["stage"]=="TRAIN"]
    va=[z for z in records if z["stage"]=="VALIDATE"]
    ho=[z for z in records if z["stage"]=="HOLDOUT"]
    if min(len(tr),len(va),len(ho))<100:raise RuntimeError(f"Not enough split data: {stages}")
    P,baseline,markinfo=fit_markov(A,draws,runs)
    model,lstmstat=train_lstm(tr,A)
    score_rows=[]
    for stage,wins in (("VALIDATE",va),("HOLDOUT",ho)):
        X,Y,actualcount=compute_XY(wins,A)
        mark=eval_markov(X,P,baseline)
        lstm=predict_lstm(model,X)
        for ix,row in enumerate(wins):
            ct48=X[ix].sum(axis=0)
            tops={
                "RANDOM":random_top10(row),
                "HOT48":top10(ct48),
                "COLD48":top10(-ct48),
                "MARKOV":top10(mark[ix])
            }
            rec=dict(stage=stage,date_first_target=row["day"],day=row["day"],
                target_first_id=row["target_draw_id"],
                target_last_id=row["last_draw_id"],
                nonoverlap=row["nonoverlap"])
            for kpos,k in enumerate(THRESHOLDS):
                # trained LSTM has distinct outputs for threshold category.
                tops["LSTM"]=top10(lstm[ix,kpos])
                truth=actualcount[ix]>=k
                rec[f"true_total80_{k}plus"]=int(truth.sum())
                for method in STRATEGIES:
                    rec[f"{method}_{k}"]=int(sum(truth[list(tops[method])]))
                if k==4:
                    for method in STRATEGIES:
                        rec[f"{method}_selected10"]=",".join(
                          str(j+1) for j in tops[method])
                if method=="LSTM":pass
            score_rows.append(rec)
        print("V90 scored stage",stage,len(wins),flush=True)
    grouped=[]
    for stage in ("VALIDATE","HOLDOUT"):
        for nonoverlap in (True,False):
            grouped.extend(metric(score_rows,stage,nonoverlap))
    validations={m["method"]:m for m in grouped if
        m["stage"]=="VALIDATE" and m["scope"]=="NONOVERLAP_12"}
    # Pre-declared aggregate is same regardless of threshold prevalence.
    # Only validation chooses winner.
    candidates=["HOT48","COLD48","MARKOV","LSTM"]
    def criterion(m):
        x=validations[m]
        return sum(w*(x[f"mean_numbers_achieving_{k}plus"]-
                        validations["RANDOM"][f"mean_numbers_achieving_{k}plus"])
                   for w,k in zip(WEIGHTS,THRESHOLDS))
    winner=max(candidates,key=lambda m:(criterion(m),-candidates.index(m)))
    holdselected=next(z for z in grouped if
         z["stage"]=="HOLDOUT" and z["scope"]=="NONOVERLAP_12"
         and z["method"]==winner)
    matched={m:interval_days([dict(r,**{
        "day":r["day"]}) for r in score_rows if r["stage"]=="HOLDOUT"],
        m,"RANDOM") for m in candidates}
    perball=[]
    # The below summary frequency is *holdout only*, no model refit.
    for n in range(80):
        idx=[i for i,x in enumerate(draws) if
            "2026-09-28"<=x["day"]<=CUT_TEST]
        f=int(A[np.array(idx),n].sum())
        perball.append(dict(number=n+1,
             holdout_occurrences=f,holdout_draws=len(idx),
             observed_probability=round(f/len(idx),7),
             iid_expected_probability=.25))
    report=[
     "V90 — RNG MARKOV vs LSTM REAL TEST, MEMORY48 TARGET_NEXT12",
     "Classification: a SINGLE ball occurs 4+/5+/6+ times in target 12.",
     "This is NOT same-draw family 4/4,5/5,6/6.",
     f"Normalized draws={len(draws)}; 5min continuous segments={len(runs)}, gaps={len(gaps)}.",
     f"Valid targets: train={len(tr)}, validation={len(va)}, holdout={len(ho)}.",
     f"Nonoverlap target blocks: validation={sum(x['nonoverlap'] for x in va)},"
     f" holdout={sum(x['nonoverlap'] for x in ho)}.",
     "Markov 80x80 transition estimated TRAIN ONLY; "+str(markinfo),
     "Real PyTorch nn.LSTM(input=80,hidden=32) learned 48 draws to 3x80 outputs.",
     f"Inner-training split LSTM epoch={lstmstat['early_stop_epoch']},"
     f" train examples={lstmstat['train_windows']}; early stopped on DEV only.",
     "Three thresholds expected among 10 random balls: "+
         ", ".join(f"{k}+={10*p:.5f}" for k,p in tails().items()),
     "VALIDATION selection metric: .50*4+ +.30*5+ +.20*6+ "
     "difference versus SAME-target random10, NONOVERLAP only.",
     f"VALIDATION-only winner={winner};"
     f" weighted gain={criterion(winner):+.6f}.",
     "",
     "FORWARD HOLDOUT (previously studied dates, not real prospective)"
    ]
    for s in grouped:
        if s["stage"]!="HOLDOUT" or s["scope"]!="NONOVERLAP_12":continue
        name=s["method"]
        report.append(f" {name}: {s['windows']} target12 blocks;"
          +", ".join(f"{k}+={s[f'mean_numbers_achieving_{k}plus']:.5f}/10"
                     for k in THRESHOLDS))
    report+=["",
      f"FROZEN WINNER {winner} on HOLDOUT vs matched random:",
    ]
    ran=next(s for s in grouped if s["stage"]=="HOLDOUT"
       and s["scope"]=="NONOVERLAP_12" and s["method"]=="RANDOM")
    for ki,k in enumerate(THRESHOLDS):
        have=holdselected[f"mean_numbers_achieving_{k}plus"]
        rnd=ran[f"mean_numbers_achieving_{k}plus"]
        lo,hi=matched[winner][ki]
        report.append(f" {k}+: winner={have:.5f}/10; same-target "
         f"random={rnd:.5f}/10; delta={have-rnd:+.5f};"
         f" day-bootstrap 95% descriptive CI [{lo:+.5f},{hi:+.5f}]")
    report+=["",
      "Markov conditional jumps are only historical association estimates.",
      "LSTM loss reduction on old training is not a proof of nonrandom RNG.",
      "A CSPRNG can be deterministic and remain practically unpredictable.",
      "Server clock seed, secondary filters and source code are UNKNOWN.",
      "No source result can reveal the actual seed algorithm on its own.",
      "All historical dates repeatedly inspected before this specific V90",
      "hypothesis, so even the frozen holdout is not untouched evidence.",
      "Require untouched future data and calibration with chance baselines.",
      "No betting purchase strategy is justified by exploratory modeling."
    ]
    out=Path(outfile);out.parent.mkdir(parents=True,exist_ok=True)
    diag=overlap_diagnostics(draws,A)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6,allowZip64=True) as z:
        z.writestr("00_V90_MARKOV_LSTM_48_12_KISA_SONUC.txt","\n".join(report))
        csvfile(z,"01_VAL_HOLDOUT_5_YONTEM_3_ESIK_NONOVERLAP_VE_KAYAN.csv",grouped)
        csvfile(z,"02_HER_KAYAN_48_12_HEDEF_ONCESI_KUPON_ISABETI.csv",score_rows)
        csvfile(z,"03_HOLDOUT_80_SAYI_SIKLIK_SAPMA.csv",perball)
        csvfile(z,"04_LSTM_YALNIZ_TRAIN_ICINDE_EPOCH.csv",lstmstat["history"])
        z.writestr("05_TEST_DISIPLINI.txt","\n".join([
         "Last48 -> next12. Individual ball count 4+,5+,6+; not K-family.",
         "All 48+12 length60 windows satisfy 5-minute + consecutive IDs.",
         "Training target <=Sep12, validation target Sep13-27,",
         "holdout target Sep28-Oct13, strict cutoff boundaries.",
         "LSTM inner stopping uses only DEV, never validation/holdout.",
         "Markov conditional P(t+1 ball|prior ball) fit only on DEV.",
         "Single target has exactly 20 unique of 80, nonindependent balls.",
         "Forecast top10 created BEFORE next12 observation.",
         "Run rolling one draw and nonoverlap 12-target blocks separately.",
         "Final candidate chosen only on VALIDATE nonoverlap before HOLDOUT.",
         "Random exactly ten balls stable drawn-ID seed, shared target.",
         "Comparisons across day-bootstrapped blocks, not independent",
         "rolling targets. Reused dates cannot show full prospective proof.",
         "IID fair expectation 10*BinomialTail(12,0.25).",
         "Server seed/clock/internal filters unobserved. Don't infer them.",
        ]))
        z.writestr("06_AUDIT.json",json.dumps(dict(version=VERSION,
            latest_data_id=draws[-1]["id"],latest_data_day=draws[-1]["day"],
            n_draws=len(draws),segments=len(runs),gaps=gaps[:40],
            window_splits=dict(stages),lstm=lstmstat,markov=markinfo,
            thresholds_probability=tails(),chosen_on_val=winner,
            choice_score=criterion(winner),nonoverlap_holdout=holdselected,
            matched_bootstrap_95=matched[winner],
            overlap_diagnostics=diag,parse_issues=issues[:15],
            invalid_rows=bad[:15]),ensure_ascii=False,indent=2))
    print("\n".join(report),flush=True)
    print("V90 OUTPUT",out,out.stat().st_size,flush=True)

def selftest():
    assert abs(tails()[4]-sum(math.comb(H,j)*(.25**j)*(.75**(H-j)) for j in range(4,13)))<1e-12
    assert tails()[4]>tails()[5]>tails()[6]
    assert len(random_top10(dict(target_draw_id=61977)))==10
    assert top10(np.arange(80,dtype=np.float64))==tuple(range(70,80))
    model=make_torch_model()
    import torch
    assert tuple(model(torch.zeros(2,48,80)).shape)==(2,3,80)
    print("V90 SELFTEST OK")
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",default="veri.txt")
    ap.add_argument("--out",default="v90_output/V90_MARKOV_LSTM_48_12_KAYAN_SAYI_KARSILASTIRMASI.zip")
    ap.add_argument("--selftest",action="store_true")
    x=ap.parse_args()
    if x.selftest:selftest()
    else:run(x.source,x.out)
