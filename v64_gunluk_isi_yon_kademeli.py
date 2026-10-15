#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V64: 217-draw daily heat, cooling and warming; fair draw-exact RNG checks.

Historical, exploratory only: all 72 days have previously been inspected.
No mechanism or predictive advantage is assumed. Date gaps are NEVER bridged.
"""
from __future__ import annotations
import argparse,csv,io,json,math,random,statistics,zipfile
from collections import Counter
from datetime import date,timedelta
from pathlib import Path

SEED=641015
MU=54.25
STATES=("COK_SOGUK","SERIN","NOTR","ILIK","COK_SICAK")
METRICS=("RANK_SAME","RANK_GRADUAL","ABS_GRADUAL",
         "TOP10_NEXT_HITS","TOP_MINUS_BOTTOM10",
         "NEXTDAY_CORRELATION","DIRECTION_CONTINUES","RISING_MINUS_FALLING_NEXT")

def average(v):
    return sum(v)/len(v) if v else float("nan")

def absolute(n):
    if n<=44:return 0
    if n<=50:return 1
    if n<=57:return 2
    if n<=63:return 3
    return 4

def classes(c):
    if len(c)!=80 or sum(c)!=4340:
        raise ValueError("A full day must contain exactly 217 x 20 appearances")
    order=sorted(range(80),key=lambda i:(c[i],i))
    rank=[0]*80
    for j,n in enumerate(order):rank[n]=j//16
    return rank,[absolute(x) for x in c],order

def true_next(a,b):
    return date.fromisoformat(b)-date.fromisoformat(a)==timedelta(days=1)

def load(source):
    from v52_ayni_cekilis_eslikci_217 import parse_txt
    parsed,issues,malformed=parse_txt(source)
    counts={};partial={}
    for d,rows in sorted(parsed.items()):
        if len(rows)!=217 or [r["pos"] for r in rows]!=list(range(1,218)):
            partial[d]=len(rows);continue
        c=[0]*80
        for row in rows:
            ns=tuple(row["nums"])
            if len(ns)!=20 or len(set(ns))!=20 or min(ns)<1 or max(ns)>80:
                raise ValueError("Invalid draw "+d)
            for n in ns:c[n-1]+=1
        classes(c)
        counts[d]=c
    return counts,partial,issues,malformed

def summarize(days,details=False):
    dates=sorted(days)
    cls={d:classes(days[d]) for d in dates}
    daily=[];transitions=[];trends=[];selection=[]
    matrix=[[0]*5 for _ in range(5)]
    edges=[];triples=[]
    for d in dates:
        if details:
            r,a,_=cls[d]
            for n,c in enumerate(days[d]):
                daily.append(dict(day=d,number=n+1,count=c,
                                  relative_heat=STATES[r[n]],absolute_heat=STATES[a[n]]))
    for j in range(len(dates)-1):
        d,e=dates[j:j+2]
        if not true_next(d,e):continue
        x,y=days[d],days[e]
        xr,xa,order=cls[d]
        yr,ya,_=cls[e]
        low5,high5=order[:5],order[-5:]
        low10,high10=order[:10],order[-10:]
        same=near=abs_near=0
        for n in range(80):
            same+=xr[n]==yr[n]
            near+=abs(xr[n]-yr[n])<=1
            abs_near+=abs(xa[n]-ya[n])<=1
            matrix[xa[n]][ya[n]]+=1
            if details:
                transitions.append(dict(from_day=d,to_day=e,number=n+1,
                    from_count=x[n],to_count=y[n],count_change=y[n]-x[n],
                    from_relative=STATES[xr[n]],to_relative=STATES[yr[n]],
                    from_absolute=STATES[xa[n]],to_absolute=STATES[ya[n]],
                    relative_step=yr[n]-xr[n],absolute_step=ya[n]-xa[n]))
        xx=sum((z-MU)**2 for z in x)
        yy=sum((z-MU)**2 for z in y)
        xy=sum((x[n]-MU)*(y[n]-MU) for n in range(80))
        top=average([y[n] for n in high10])
        bottom=average([y[n] for n in low10])
        edges.append(dict(from_day=d,to_day=e,same=same/80,near=near/80,
                 abs_near=abs_near/80,top_hits=sum(y[n] for n in high10)/217,
                 top_bottom=top-bottom,xy=xy,xx=xx,yy=yy))
        if details:
            selection.append(dict(day=d,next_day=e,
                bottom5_next_mean=average([y[n] for n in low5]),
                top5_next_mean=average([y[n] for n in high5]),
                bottom10_next_mean=bottom,top10_next_mean=top,
                top10_hits_per_draw=sum(y[n] for n in high10)/217,
                coldest5="-".join(str(n+1) for n in low5),
                hottest5="-".join(str(n+1) for n in high5)))
    for j in range(1,len(dates)-1):
        prev,d,nxt=dates[j-1:j+2]
        if not true_next(prev,d) or not true_next(d,nxt):continue
        p,x,y=days[prev],days[d],days[nxt]
        continuing=0;up=[];down=[]
        for n in range(80):
            direction=x[n]-p[n];next_change=y[n]-x[n]
            continuing+=direction*next_change>0
            if direction>=4:up.append(y[n])
            if direction<=-4:down.append(y[n])
            if details:
                trends.append(dict(previous_day=prev,day=d,next_day=nxt,
                    number=n+1,previous_count=p[n],current_count=x[n],
                    next_count=y[n],previous_direction=direction,
                    next_direction=next_change,
                    continuing=int(direction*next_change>0)))
        triples.append(dict(day=d,continue_rate=continuing/80,
             rising_next_mean=average(up),falling_next_mean=average(down),
             gap=average(up)-average(down) if up and down else float("nan")))
    if not edges or not triples:raise ValueError("Need >= 3 consecutive complete days")
    v=dict(
      RANK_SAME=average([e["same"] for e in edges]),
      RANK_GRADUAL=average([e["near"] for e in edges]),
      ABS_GRADUAL=average([e["abs_near"] for e in edges]),
      TOP10_NEXT_HITS=average([e["top_hits"] for e in edges]),
      TOP_MINUS_BOTTOM10=average([e["top_bottom"] for e in edges]),
      NEXTDAY_CORRELATION=sum(e["xy"] for e in edges)/
          math.sqrt(sum(e["xx"] for e in edges)*sum(e["yy"] for e in edges)),
      DIRECTION_CONTINUES=average([t["continue_rate"] for t in triples]),
      RISING_MINUS_FALLING_NEXT=average([t["gap"] for t in triples]))
    if any(not math.isfinite(v[m]) for m in METRICS):
        raise ValueError("Nonfinite metric")
    return dict(measures=v,edges=edges,triples=triples,matrix=matrix,
                daily=daily,transitions=transitions,trends=trends,selection=selection)

def simulate(template,rng):
    # Exactly 20 distinct numbers per draw, 217 draws per day.
    out={};pool=range(80)
    for d in template:
        c=[0]*80
        for _ in range(217):
            for n in rng.sample(pool,20):c[n]+=1
        out[d]=c
    return out

def percentile(xs,p):
    a=sorted(xs)
    return a[min(len(a)-1,max(0,int((len(a)-1)*p)))]

def analyze(days,nrep):
    observed=summarize(days,True)
    rng=random.Random(SEED)
    simulated=[]
    for j in range(nrep):
        simulated.append(summarize(simulate(days,rng))["measures"])
    m={k:average([s[k] for s in simulated]) for k in METRICS}
    sd={k:statistics.stdev([s[k] for s in simulated]) for k in METRICS}
    if min(sd.values())<=0:raise ValueError("Degenerate RNG variance")
    family_null=[max(abs((s[k]-m[k])/sd[k]) for k in METRICS) for s in simulated]
    tests=[]
    for k in METRICS:
        value=observed["measures"][k]
        standardized=abs((value-m[k])/sd[k])
        rawp=(1+sum(abs((s[k]-m[k])/sd[k])>=standardized for s in simulated))/(nrep+1)
        adjp=(1+sum(z>=standardized for z in family_null))/(nrep+1)
        tests.append(dict(metric=k,actual=round(value,7),rng_average=round(m[k],7),
          rng_p025=round(percentile([s[k] for s in simulated],.025),7),
          rng_p975=round(percentile([s[k] for s in simulated],.975),7),
          actual_minus_rng=round(value-m[k],7),z=round((value-m[k])/sd[k],5),
          monte_carlo_two_sided_p=round(rawp,6),familywise_max8_p=round(adjp,6),
          corrected_p_below_0_05=int(adjp<.05)))
    return observed,simulated,tests

def write_csv(z,name,records):
    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=list(records[0]) if records else ["NO_DATA"])
    writer.writeheader()
    if records:writer.writerows(records)
    z.writestr(name,buf.getvalue())

def save(output,days,partial,issues,malformed,data,simulations,tests):
    outcome={x["metric"]:x for x in tests}
    n=len(days)
    lines=[
       "V64 | GUNLUK KADEMELI ISI / YON / RNG 217 CEKILIS",
       f"Complete days={n}; complete draws={n*217}; actual consecutive pairs={len(data['edges'])}; true triples={len(data['triples'])}.",
       f"Partial days skipped={len(partial)}; parse issues={len(issues)}; malformed={len(malformed)}.",
       f"Fair expectation: 54.25 occurrences per number/day; {len(simulations)} exact independent 20/80 simulations.",
       "Daily rank-quintiles: precisely 16 numbers per class; ties consistently broken by number.",
       "Fixed frequency classes: <=44, 45..50, 51..57, 58..63, >=64.",
       "Gradual = same or 1 adjacent class in next day; not automatically surprising.",
       "Direction continuing: same nonzero sign of consecutive day-to-day count changes.",
       "Rising/falling: count difference at least +4/-4 on the preceding two days.",
       "10 hottest numbers are frozen at the source-day close; hits assessed using next-day 217 draws.",
       "Null generated draw by draw without replacement and with identical calendar-day gaps.",
       "Eight predeclared tests; two-sided Monte Carlo with max-abs-z familywise correction.",
       "Repeatedly researched old days: exploratory historical analysis, NOT independent future validation.",
       "No verified method should be sold or used as justification for more paid lottery tickets.",
       "", "RESULTS: actual | RNG | adjusted p",
       *[f"{k}: {outcome[k]['actual']:.5f} | {outcome[k]['rng_average']:.5f} | {outcome[k]['familywise_max8_p']:.4f}" for k in METRICS],
       "", "CORRECT INTERPRETATION",
       "An extreme day naturally tends to be nearer the average next day under independent RNG.",
       "All descriptive shapes require comparison to these draw-exact random controls.",
       "Historical significance cannot validate a money-wagering prediction: fresh future data are required.",
    ]
    matrix=[]
    for i in range(5):
        total=sum(data["matrix"][i])
        for j in range(5):
            value=data["matrix"][i][j]
            matrix.append(dict(from_heat=STATES[i],to_heat=STATES[j],
                   observed_transitions=value,conditional_percent=round(100*value/total,4) if total else 0))
    notes=(
      "# V64: Fixed study protocol\n\n"
      "Before observing V64 output, eight metrics and fixed bins were encoded. "
      "Use only 217-draw complete calendar days. Missing and incomplete days create breaks. "
      "20/80 RNG controls sample 20 distinct numbers, without replacement, for each of 217 daily draws. "
      "Five rank classes each contain 16 numbers; fixed classes have thresholds 44/50/57/63. "
      "Ties are resolved by the smaller number; RNG replicas apply the identical convention. "
      "Adjacent gradient rate and full transition matrix are descriptive, not a timing mechanism. "
      "Eight tests receive maximum absolute standardized effect familywise correction. "
      "All number/day observations inside each simulation are kept dependent as in 20/80 draws. "
      "The historical pool was already inspected by prior versions, so these tests are exploratory. "
      "No incoming day's numbers contribute to that day's selections. "
      "New, untouched prospective observations are necessary for any genuine prediction claim.\n")
    dst=Path(output);dst.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dst,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("00_V64_ANA_KARAR.txt","\n".join(lines)+"\n")
        write_csv(z,"01_GUNLUK_80_SAYI_SICAKLIK.csv",data["daily"])
        write_csv(z,"02_GUNLER_ARASI_KADEMELI_GECIS.csv",data["transitions"])
        write_csv(z,"03_BES_KATMAN_GECIS_MATRISI.csv",matrix)
        write_csv(z,"04_3_GUNLUK_YON_KONTROL.csv",data["trends"])
        write_csv(z,"05_GUNLUK_SICAK_SOGUK_TOP5_TOP10.csv",data["selection"])
        write_csv(z,"06_8_TEST_RNG_KARSILASTIRMASI.csv",tests)
        write_csv(z,"07_RNG_SIMULASYONLARI.csv",[
           dict(iteration=i+1,**{k:round(s[k],7) for k in METRICS})
           for i,s in enumerate(simulations)])
        z.writestr("08_METODOLOJI.md",notes)
        z.writestr("09_META.json",json.dumps(dict(
           days=n,draws=n*217,pairs=len(data["edges"]),triples=len(data["triples"]),
           excluded_partial=partial,issues=issues[:20],malformed=len(malformed),
           seed=SEED,replicates=len(simulations)),ensure_ascii=False,indent=2))
    return lines

def selftest():
    assert [absolute(n) for n in (44,45,50,51,57,58,63,64)]==[0,1,1,2,2,3,3,4]
    a=[54]*80
    for n in range(20):a[n]+=2
    for n in range(20,40):a[n]-=1
    assert sum(a)==4340
    assert sorted(Counter(classes(a)[0]).values())==[16]*5
    ds=simulate(["2026-10-01","2026-10-02","2026-10-03"],random.Random(64))
    stats=summarize(ds,True)
    assert len(stats["edges"])==2 and len(stats["triples"])==1
    assert len(stats["daily"])==240 and len(stats["transitions"])==160
    try:summarize({k:v for k,v in ds.items() if k!="2026-10-02"})
    except ValueError:pass
    else:raise AssertionError("Gap was incorrectly bridged")
    print("V64 SELFTEST OK",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--output",default="v64_output/V64_GUNLUK_ISI_YON_RNG_TEK_ZIP.zip")
    p.add_argument("--replicates",type=int,default=240)
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:selftest();return
    if args.replicates<100:raise ValueError(">=100 fair RNG simulations required")
    full,partial,issues,malformed=load(args.source)
    if len(full)<5:raise ValueError("Not enough full days")
    print("V64 loaded",len(full),"complete days. RNG reps",args.replicates,flush=True)
    data,simulations,tests=analyze(full,args.replicates)
    lines=save(args.output,full,partial,issues,malformed,data,simulations,tests)
    print("\n".join(lines),flush=True)
    print("V64 OUTPUT",args.output,flush=True)

if __name__=="__main__":main()
