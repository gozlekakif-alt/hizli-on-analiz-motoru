# -*- coding: utf-8 -*-
"""V16: independently check adjacent 20/80 overlap oscillations vs exact RNG null.

Observed 20 numbers are unordered and do not reveal PRNG code, seed, or
draw-order. Fair iid set model has hypergeometric overlap:
  P(X=k)=C(20,k)*C(60,20-k)/C(80,20)
  E(X)=5; SD=sqrt(20*.25*.75*60/79)≈1.6876.

Strict consecutive 5-minute adjacent slots only: exclude the 01:02->07:02
six-hour gap, first draws of days, missing slots. In three-draw sequences
predict the count of repeats from X_prev, using a conditional distribution
learned on first 36 calendar days; no test outcomes feed back to training.
Test every next count on 37 subsequent days against hypergeometric baseline.

The distribution test of overlap counts is not a cryptanalytic attack and
cannot reveal the underlying PRNG without additional implementation evidence.
"""
from collections import Counter,defaultdict
from math import comb,exp,log,erfc,sqrt
from v12_80_kule import make_ready

PROBS={k:comb(20,k)*comb(60,20-k)/comb(80,20) for k in range(21)}
GROUPS=("0–2","3–4","5–6","7–8","9+")
SMOOTHING=120.0
EPS=1e-300

def bucket(x):
    return "0–2" if x<=2 else "3–4" if x<=4 else "5–6" if x<=6 else "7–8" if x<=8 else "9+"

def hour_of(pos):
    if pos<=13:return "00"
    return f"{7+(pos-14)//12:02d}"

def half_of(pos):
    if pos==13:return "Ek 01:02"
    if pos<=12:return "İlk 6" if pos<=6 else "Son 6"
    return "İlk 6" if (pos-14)%12<6 else "Son 6"

def contiguous(pos):
    """Exactly five minutes between these calendar positions."""
    return 2<=pos<=13 or 15<=pos<=217

def overlap(a,b):
    return (a["mask"]&b["mask"]).bit_count()

def consecutive_rows(draws):
    byday=defaultdict(dict)
    for d in make_ready(draws):
        byday[d["day"]][d["pos"]]=d
    for day in sorted(byday):
        positions=byday[day]
        for pos in sorted(positions):
            if not contiguous(pos) or pos-1 not in positions:
                continue
            now=positions[pos]
            previous=positions[pos-1]
            x=overlap(previous,now)
            previous2=positions.get(pos-2)
            # Must have TWO true 5-min transitions, not the 01:02->07:02 break.
            prior_x=overlap(previous2,previous) if previous2 is not None and contiguous(pos-1) else None
            yield {"day":day,"pos":pos,"draw":now["no"],
                   "hour":hour_of(pos),"half":half_of(pos),
                   "x":x,"prev_x":prior_x}


def build_model(training_rows):
    counts=defaultdict(Counter)
    samples=Counter()
    for r in training_rows:
        if r["prev_x"] is None:continue
        label=bucket(r["prev_x"])
        counts[label][r["x"]]+=1
        samples[label]+=1
    distributions={}
    for label in GROUPS:
        distributions[label]={k:(counts[label][k]+SMOOTHING*PROBS[k])/
                              (samples[label]+SMOOTHING) for k in PROBS}
    return {"hist":dict(counts),"samples":dict(samples),
            "prob":distributions}


def normal_two_sided(mean,expected,n,variance):
    if n<2:return None
    z=(mean-expected)/sqrt(variance/n)
    return erfc(abs(z)/sqrt(2))


def benjamini_hochberg(rows,key="p",q=.05):
    clean=sorted((r for r in rows if r[key] is not None),key=lambda r:r[key])
    n=len(clean)
    largest=0
    for i,r in enumerate(clean,1):
        if r[key]<=q*i/n:largest=i
    marked={id(r) for r in clean[:largest]}
    for r in rows:r["fdr_significant"]=id(r) in marked
    return rows


def summarize_hour(rows,training):
    grouped=defaultdict(list)
    for r in rows:
        grouped[r["hour"]].append(r["x"])
    byhour=[]
    for hour in sorted(grouped):
        vs=grouped[hour]
        avg=sum(vs)/len(vs)
        p=normal_two_sided(avg,5,len(vs),20*.25*.75*60/79)
        tr=[r["x"] for r in training if r["hour"]==hour]
        tm=sum(tr)/len(tr) if tr else None
        byhour.append({
            "Saat":hour,"Test geçiş":len(vs),
            "Eğitim tekrar ort":round(tm,4) if tm is not None else None,
            "Test tekrar ort":round(avg,4),
            "Bağımsız beklenen":5.0,
            "Test p":p,
            "Eğitim ile test sapması aynı yönde":(
                ((tm-5)*(avg-5)>0) if tm is not None else False)
        })
    benjamini_hochberg(byhour,key="Test p",q=.05)
    return [{**r,
             "Test p":round(r["Test p"],6) if r["Test p"] is not None else None,
             "Çoklu testte anlamlı":r.pop("fdr_significant")}
            for r in byhour]


def analyze(draws,train_days=36):
    byday=defaultdict(list)
    for d in make_ready(draws):byday[d["day"]].append(d)
    days=sorted(byday)
    if days and len(byday[days[-1]])<217:
        days=days[:-1]
    if len(days)<=train_days:raise ValueError("Insufficient test days")
    data=list(consecutive_rows(d for day in days for d in byday[day]))
    training_days=set(days[:train_days])
    tr=[r for r in data if r["day"] in training_days]
    te=[r for r in data if r["day"] not in training_days]
    model=build_model(tr)
    all_hist=Counter(r["x"] for r in data)
    tr_hist=Counter(r["x"] for r in tr)
    te_hist=Counter(r["x"] for r in te)
    n=len(data);train_n=len(tr);test_n=len(te)
    ptable=[]
    for k in range(21):
        ptable.append({
            "Tekrar sayısı":k,"Teorik olasılık %":round(100*PROBS[k],7),
            "Rastgele beklenen":round(n*PROBS[k],3),
            "Gerçek bütün dönem":all_hist[k],
            "Eğitim":tr_hist[k],"Test":te_hist[k]
        })
    # Pool low-expected cells to satisfy Pearson asymptotic guideline.
    chunks=[(0,1),(2,2),(3,3),(4,4),(5,5),(6,6),(7,7),(8,8),(9,9),(10,20)]
    groups=[]
    pearson=0.
    for a,b in chunks:
        obs=sum(all_hist[k] for k in range(a,b+1))
        expected=n*sum(PROBS[k] for k in range(a,b+1))
        pearson+=(obs-expected)**2/expected
        groups.append({"Tekrar dilimi":f"{a}" if a==b else f"{a}–{b}",
                       "Gözlenen":obs,"Bağımsız beklenen":round(expected,2),
                       "Gözlem/teori":round(obs/expected,4)})
    # Exact chi-square p requires incomplete gamma; report chi2 and degrees.
    # Independent X_t has independent overlapping pair counts under iid sets,
    # but full-day grouping is still retained for robust forward evaluation.
    pairs=[r for r in te if r["prev_x"] is not None]
    prior_rows=defaultdict(list)
    for r in pairs:prior_rows[bucket(r["prev_x"])].append(r)
    conditional=[]
    for g in GROUPS:
        items=prior_rows[g]
        if not items:continue
        avg=sum(r["x"] for r in items)/len(items)
        q=model["prob"][g]
        trained_mean=sum(k*q[k] for k in q)
        conditional.append({
            "Önceki tekrar dilimi":g,
            "Eğitim örnek":model["samples"].get(g,0),
            "Test örnek":len(items),
            "Test sonraki tekrar ort":round(avg,4),
            "Eğitimden tahmin ort":round(trained_mean,4),
            "Bağımsız beklenti":5.,
            "Test p":round(normal_two_sided(avg,5,len(items),20*.25*.75*60/79),6)
        })
    # Strict held-out proper probabilistic scoring.
    scores={"N":len(pairs),"baseline_nll":0.,"model_nll":0.,
            "baseline_brier":0.,"model_brier":0.,
            "baseline_mae":0.,"model_mae":0.,
            "baseline_mse":0.,"model_mse":0.,
            "baseline_exact":0,"model_exact":0}
    for r in pairs:
        actual=r["x"]
        q=model["prob"][bucket(r["prev_x"])]
        scores["baseline_nll"]-=log(max(PROBS[actual],EPS))
        scores["model_nll"]-=log(max(q[actual],EPS))
        scores["baseline_brier"]+=sum((PROBS[k]-(k==actual))**2 for k in PROBS)
        scores["model_brier"]+=sum((q[k]-(k==actual))**2 for k in q)
        estimate=sum(k*q[k] for k in q)
        scores["baseline_mae"]+=abs(actual-5)
        scores["model_mae"]+=abs(actual-estimate)
        scores["baseline_mse"]+=(actual-5)**2
        scores["model_mse"]+=(actual-estimate)**2
        scores["baseline_exact"]+=actual==5
        scores["model_exact"]+=actual==max(q,key=q.get)
    predictions=[
        {"Ölçüm":"Ortalama log-kayıp (küçük iyi)",
         "RNG beklentisi":round(scores["baseline_nll"]/scores["N"],6),
         "Salınım model":round(scores["model_nll"]/scores["N"],6)},
        {"Ölçüm":"Brier hata (küçük iyi)",
         "RNG beklentisi":round(scores["baseline_brier"]/scores["N"],6),
         "Salınım model":round(scores["model_brier"]/scores["N"],6)},
        {"Ölçüm":"Tekrar sayısı mutlak hata",
         "RNG beklentisi":round(scores["baseline_mae"]/scores["N"],6),
         "Salınım model":round(scores["model_mae"]/scores["N"],6)},
        {"Ölçüm":"Tekrar sayısı kare hata",
         "RNG beklentisi":round(scores["baseline_mse"]/scores["N"],6),
         "Salınım model":round(scores["model_mse"]/scores["N"],6)},
        {"Ölçüm":"Tam tekrar sayısını bilme %",
         "RNG beklentisi":round(100*scores["baseline_exact"]/scores["N"],4),
         "Salınım model":round(100*scores["model_exact"]/scores["N"],4)}
    ]
    halfs=defaultdict(list)
    for r in te:halfs[r["half"]].append(r["x"])
    halfrows=[{"Saat yarısı":g,"Test geçiş":len(vs),
               "Ortalama tekrar":round(sum(vs)/len(vs),4),
               "Bağımsız beklenen":5.0}
              for g,vs in sorted(halfs.items())]
    # Adjacent transition extremes: X(prev) >= 9 or <=2; a 12+ can be rare.
    tail=Counter()
    for r in te:
        if r["x"]>=12:tail["extreme12"]+=1
        if r["x"]<=2:tail["low2"]+=1
    return {
        "meta":{"calendar_days":len(days),"train_days":train_days,
                "test_days":len(days)-train_days,"first":days[0],
                "last":days[-1],"n_transitions":n,"train_transitions":train_n,
                "test_transitions":test_n,"conditional_targets":len(pairs),
                "observed_12plus":sum(all_hist[k] for k in range(12,21)),
                "expected_12plus":round(n*sum(PROBS[k] for k in range(12,21)),3),
                "mean_overlap":round(sum(r["x"] for r in data)/n,5),
                "expected_mean":5.,
                "std_hypergeom":round(sqrt(20*.25*.75*60/79),6),
                "chi_square":round(pearson,4),"degrees_freedom":len(chunks)-1,
                "note":"Chi-square assumes predefined 11 bins. Does not identify generator or seed."},
        "distribution":ptable,"pooled_distribution":groups,
        "hour":summarize_hour(te,tr),"halves":halfrows,
        "conditional":conditional,"forecast":predictions,
        "scoring":scores,
        "model":model
    }
