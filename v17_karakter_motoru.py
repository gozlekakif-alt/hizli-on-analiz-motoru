# -*- coding: utf-8 -*-
"""V17 — characterize each draw, not its number identities.

Each 20-ball draw is assigned a predeclared, interpretable CHARACTER:
  repeat level vs immediately preceding draw,
  odd/even seat balance,
  1..40 vs 41..80 seat balance,
  1..20 / 21..40 / 41..60 / 61..80 band organization,
  adjacency / clustering,
  2..10-size historic-family echo intensity,
  and cold/warm/hot seat balance (as known BEFORE this draw).

Forecast the NEXT CHARACTER from last character and phase of the 217-slot
daily clock. Conditionals trained first 36 calendar days, probabilities
shrunk to an in-sample time-phase BASELINE. Later 37 days never train model.

IMPORTANT: This never recovers RNG algorithms or predicts individual numbers.
Last draw's character is known only AFTER that draw; no target lookahead.
No post-result family chosen as a pre-result ticket is ever counted.
"""
import csv
import io
import math
from collections import Counter,defaultdict
from v12_80_kule import make_ready
from v13_havuz_koltuk import states_for_day
from v16_rng_salinim import contiguous

FIELDS=("Tekrar","Tek/Çift","Alt/Üst","Bant","Komşuluk",
        "Aile izi","Isı koltuğu","Bileşik karakter")
PRIOR=90.
BASELINE_SMOOTH=18.
EPS=1e-15
ALL_CATEGORIES={
 "Tekrar":("Kopuş (0–3)","Denge (4–6)","Taşıma (7+)"),
 "Tek/Çift":("Tek az (0–7)","Tek 8–9","Tek 10–11",
             "Tek 12–13","Tek çok (14+)"),
 "Alt/Üst":("Alt az (0–7)","Alt 8–9","Alt 10–11",
            "Alt 12–13","Alt çok (14+)"),
 "Bant":("Yaygın (en çok 6)","1–20 baskın","21–40 baskın",
          "41–60 baskın","61–80 baskın","Bant eşit baskın"),
 "Komşuluk":("Dağınık (0–2)","Orta (3–5)","Kümeli (6+)"),
 "Aile izi":("İz az","İz normal","İz yoğun"),
 "Isı koltuğu":("Soğuk baskın","Ilık baskın","Sıcak baskın","Isı dengeli"),
 "Bileşik karakter":tuple(
     f"{a} / {b}" for a in ("Kopuş","Denge","Taşıma")
                     for b in ("Dağınık","Orta","Kümeli")),
}


def clock_phase(pos):
    if pos<=13:return "00 Gece"
    h=7+(pos-14)//12
    return "07–11 Sabah" if h<=11 else "12–16 Öğlen" if h<=16 else "17–23 Akşam"


def clock_half(pos):
    if pos==13:return "01:02 ek"
    if pos<=12:return "İlk 6" if pos<=6 else "Son 6"
    return "İlk 6" if (pos-14)%12<6 else "Son 6"


def label_three(value,low,high,left,middle,right):
    return left if value<=low else middle if value<=high else right


def full_character(actual,prev,prior_day):
    """Postdraw description, using pre-draw temperature state.
    
    prior_day excludes actual. The resulting labels are NEVER used to
    predict this same actual, only potentially the following draw.
    """
    numbers=set(actual["nums"])
    previous=set(prev["nums"])
    repeat=len(numbers&previous)
    odd=sum(n%2 for n in numbers)
    lower=sum(n<=40 for n in numbers)
    bands=Counter((n-1)//20 for n in numbers)
    bandmax=max(bands.values())
    if bandmax<=6: band_label="Yaygın (en çok 6)"
    else:
        winners=[q for q in range(4) if bands[q]==bandmax]
        band_label=("Bant eşit baskın" if len(winners)>1
                    else ("1–20 baskın","21–40 baskın",
                          "41–60 baskın","61–80 baskın")[winners[0]])
    neighbors=sum((n+1) in numbers for n in numbers)
    last12=prior_day[-12:]
    traces={k:0 for k in range(2,11)}
    for past in last12:
        common=len(numbers.intersection(past["nums"]))
        for k in traces:
            if common>=k:traces[k]+=math.comb(common,k)
    expected_pair=len(last12)*math.comb(20,2)**2/math.comb(80,2)
    family_label=(
        "İz az" if traces[2]<.7*expected_pair
        else "İz yoğun" if traces[2]>1.3*expected_pair else "İz normal"
    )
    states=states_for_day(prior_day)
    by_number={r["n"]:r["pool"] for r in states}
    count=Counter(by_number[n] for n in numbers)
    available=Counter(r["pool"] for r in states)
    deviations={pool:count[pool]-.25*available[pool]
                for pool in ("Soğuk","Ilık","Sıcak")}
    significant=[pool for pool in deviations
                 if deviations[pool]>=3.0 and available[pool]>0]
    if significant:
        greatest=max(significant,key=lambda c:(deviations[c],c))
        heat_label=greatest+" baskın"
    else:heat_label="Isı dengeli"
    rep=label_three(repeat,3,6,"Kopuş (0–3)","Denge (4–6)","Taşıma (7+)")
    cluster=label_three(neighbors,2,5,"Dağınık (0–2)","Orta (3–5)","Kümeli (6+)")
    return {
        "Tekrar":rep,
        "Tek/Çift":("Tek az (0–7)" if odd<=7 else
                    "Tek 8–9" if odd<=9 else "Tek 10–11" if odd<=11 else
                    "Tek 12–13" if odd<=13 else "Tek çok (14+)"),
        "Alt/Üst":("Alt az (0–7)" if lower<=7 else
                   "Alt 8–9" if lower<=9 else "Alt 10–11" if lower<=11 else
                   "Alt 12–13" if lower<=13 else "Alt çok (14+)"),
        "Bant":band_label,
        "Komşuluk":cluster,
        "Aile izi":family_label,
        "Isı koltuğu":heat_label,
        "Bileşik karakter":rep.split()[0]+" / "+cluster.split()[0],
        "Tekrar sayısı":repeat,
        "Tek sayı":odd,
        "Alt sayı":lower,
        "Komşu bağlantı":neighbors,
        "Aile izi 2–10":traces,
        "Isı gerçek":dict(count),
        "Isı havuzu":dict(available),
        "Bant koltukları":[bands[i] for i in range(4)]
    }


def build_character_rows(draws):
    """Raw descriptive character ledger and no-lookahead transition events.

    Slots 13 and 16..217 have a previous character with an uninterrupted
    5-minute predecessor relation. The six-hour 01:02->07:02 break is never
    silently treated as a normal five-minute transition.
    """
    byday=defaultdict(list)
    for d in make_ready(draws):byday[d["day"]].append(d)
    all_chars=[]
    target_rows=[]
    for day in sorted(byday):
        history=[]
        character_by_pos={}
        prior_positions={}
        for now in byday[day]:
            pos=now["pos"]
            prev=prior_positions.get(pos-1)
            if prev is not None and contiguous(pos):
                char=full_character(now,prev,history)
                record={
                    "Gün":day,"Pozisyon":pos,"Saat":now["dt"][11:16],
                    "Çekiliş":now["no"],"Dönem":clock_phase(pos),
                    "Saat yarısı":clock_half(pos),
                    "Karakter":char
                }
                all_chars.append(record)
                preceding=character_by_pos.get(pos-1)
                if preceding is not None and len(history)>=12:
                    target_rows.append({
                        "Gün":day,"Pozisyon":pos,"Saat":now["dt"][11:16],
                        "Çekiliş":now["no"],"Dönem":clock_phase(pos),
                        "Saat yarısı":clock_half(pos),
                        "Önceki":preceding,
                        "Gerçek":char
                    })
                character_by_pos[pos]=char
            prior_positions[pos]=now
            history.append(now)
    return all_chars,target_rows


def _count_training(training):
    prior=defaultdict(Counter)
    cond=defaultdict(Counter)
    phasecount=Counter()
    for row in training:
        phase=row["Dönem"]
        for field in FIELDS:
            v=row["Gerçek"][field]
            p=row["Önceki"][field]
            prior[(phase,field)][v]+=1
            cond[(phase,field,p)][v]+=1
            phasecount[(phase,field)]+=1
    return {"prior":prior,"conditional":cond,"counts":phasecount}


def _probabilities(c,labels,smooth=None):
    smooth=BASELINE_SMOOTH if smooth is None else smooth
    total=sum(c.values())
    return {lab:(c.get(lab,0)+smooth/len(labels))/(total+smooth)
            for lab in labels}


def fit(training_rows):
    counted=_count_training(training_rows)
    trained={"baseline":{},"conditional":{},
             "training_targets":len(training_rows)}
    for phase in ("00 Gece","07–11 Sabah","12–16 Öğlen","17–23 Akşam"):
        for field,labels in ALL_CATEGORIES.items():
            base=_probabilities(counted["prior"][(phase,field)],labels)
            trained["baseline"][(phase,field)]=base
            for last in labels:
                selected=counted["conditional"][(phase,field,last)]
                n=sum(selected.values())
                trained["conditional"][(phase,field,last)]={
                    label:(selected.get(label,0)+PRIOR*base[label])/(n+PRIOR)
                    for label in labels
                }
    return trained


def next_character(last_char,next_pos,model):
    phase=clock_phase(next_pos)
    result={}
    for field in FIELDS:
        observed=last_char[field]
        key=(phase,field,observed)
        q=model["conditional"].get(key) or model["baseline"][(phase,field)]
        result[field]={x:round(prob,8) for x,prob in q.items()}
    return result


def _metric(prediction,actual):
    # Proper multiclass log loss and Brier; winner accuracy only a secondary
    # metric. Predictions fixed before actual and never use target numbers.
    ll=-math.log(max(prediction[actual],EPS))
    brier=sum((p-(key==actual))**2 for key,p in prediction.items())
    acc=int(max(prediction,key=prediction.get)==actual)
    return ll,brier,acc


def replay(draws,train_days=36):
    data=make_ready(draws)
    byday=defaultdict(list)
    for d in data:byday[d["day"]].append(d)
    days=sorted(byday)
    if days and len(byday[days[-1]])<217:days=days[:-1]
    if len(days)<=train_days:raise ValueError("Need training and test days")
    full=[d for day in days for d in byday[day]]
    chars,events=build_character_rows(full)
    train=set(days[:train_days])
    tr=[r for r in events if r["Gün"] in train]
    test=[r for r in events if r["Gün"] not in train]
    model=fit(tr)
    scored=defaultdict(lambda:defaultdict(lambda:[0,0.,0.,0]))
    # Nesting: [count,sum_log_loss,sum_brier,sum_correct].
    transition_counts=defaultdict(lambda:[0,0])
    actual_count=defaultdict(Counter)
    per_target=[]
    for r in test:
        phase=r["Dönem"]
        comparison={"Tarih":r["Gün"],"Saat":r["Saat"],
                    "Pozisyon":r["Pozisyon"],"Çekiliş":r["Çekiliş"],
                    "Gün dönemi":phase}
        for field in FIELDS:
            true=r["Gerçek"][field]
            prev=r["Önceki"][field]
            base=model["baseline"][(phase,field)]
            conditional=model["conditional"][(phase,field,prev)]
            actual_count[(phase,field)][true]+=1
            transition_counts[(field,prev,true)][0]+=1
            transition_counts[(field,prev,true)][1]+=r["Gün"] in train
            for name,pred in (("Zaman bazlı sabit",base),
                              ("Karakter geçişi",conditional)):
                ll,brier,correct=_metric(pred,true)
                a=scored[(field,name)][phase]
                a[0]+=1;a[1]+=ll;a[2]+=brier;a[3]+=correct
            if field in ("Tekrar","Komşuluk","Bileşik karakter","Isı koltuğu"):
                comparison["Önceki "+field]=prev
                comparison["Hedef "+field]=true
                comparison["Karakter tahmini "+field]=max(
                    conditional,key=conditional.get)
                comparison["O tahminin olasılığı %"]=round(
                    conditional[comparison["Karakter tahmini "+field]]*100,4)
        per_target.append(comparison)
    summary=[]
    for field in FIELDS:
        for name in ("Zaman bazlı sabit","Karakter geçişi"):
            groups=scored[(field,name)]
            v=[sum(groups[phase][j] for phase in groups) for j in range(4)]
            n,ll,br,acc=v
            summary.append({
                "Karakter ölçüsü":field,"Model":name,"Test hedefi":n,
                "Log-kayıp (az iyi)":round(ll/n,6),
                "Brier (az iyi)":round(br/n,6),
                "En olası sınıf isabeti %":round(100*acc/n,4)})
    comparison=[]
    for field in FIELDS:
        base=next(r for r in summary if r["Karakter ölçüsü"]==field
                  and r["Model"]=="Zaman bazlı sabit")
        cond=next(r for r in summary if r["Karakter ölçüsü"]==field
                  and r["Model"]=="Karakter geçişi")
        comparison.append({
            "Karakter":field,"Test hedefi":cond["Test hedefi"],
            "Sabit log-kayıp":base["Log-kayıp (az iyi)"],
            "Geçiş log-kayıp":cond["Log-kayıp (az iyi)"],
            "Geçiş − sabit":round(
                cond["Log-kayıp (az iyi)"]-base["Log-kayıp (az iyi)"],6),
            "Sabit Brier":base["Brier (az iyi)"],
            "Geçiş Brier":cond["Brier (az iyi)"],
            "Sabit sınıf isabeti %":base["En olası sınıf isabeti %"],
            "Geçiş sınıf isabeti %":cond["En olası sınıf isabeti %"],
        })
    day_phase=defaultdict(lambda:[0,0])
    for r in test:
        key=(r["Dönem"],r["Saat yarısı"])
        day_phase[key][0]+=1
        day_phase[key][1]+=int(r["Gerçek"]["Tekrar"]=="Taşıma (7+)")
    phases=[{
        "Dönem":day,"Saat yarısı":half,"Test hedefi":v[0],
        "Yüksek taşıma (7+)":v[1],
        "Yüksek taşıma oranı %":round(100*v[1]/v[0],4)
    } for (day,half),v in sorted(day_phase.items())]
    # Distinct family size 2..10 is tracked without exponentially enumerating
    # millions of target-internal subsets. Echo is prior-window co-occurrences.
    echo=defaultdict(lambda:[0,0])
    for r in chars:
        if r["Gün"] in train:continue
        for k,count in r["Karakter"]["Aile izi 2–10"].items():
            v=echo[k]
            v[0]+=1;v[1]+=count
    family_echo=[{"Aile boyutu":k,"Karakter örnek":v[0],
                  "Son 12'den ortalama tam-aile izi":round(v[1]/v[0],4),
                  "Not":"Geçmişte tam birlikte görünüş; benzersiz aile sayısı değil"}
                 for k,v in sorted(echo.items())]
    flow=[]
    for row in sorted(transition_counts):
        k,prior,current=row
        total=sum(v[0] for (f,p,c),v in transition_counts.items()
                  if f==k and p==prior)
        if total:
            flow.append({"Karakter":k,"Önceki":prior,"Sonraki":current,
                         "Test tekrar":transition_counts[row][0],
                         "Önceki aynı sınıfta hedef":total,
                         "Koşullu %":round(100*transition_counts[row][0]/total,4)})
    return {"meta":{
            "train_days":train_days,"test_days":len(days)-train_days,
            "train_first":days[0],"train_last":days[train_days-1],
            "test_first":days[train_days],"test_last":days[-1],
            "train_targets":len(tr),"test_targets":len(test),
            "character_count":len(chars),
            "note":"Physical extraction order unavailable. Features are sets, not numbers forecast."},
        "model":model,"comparison":comparison,"metrics":summary,
        "phases":phases,"family_echo":family_echo,
        "flow":flow,"ledger":per_target}


def latest_character(day_draws,target_pos):
    """Last actually observable character strictly before a future target."""
    history=make_ready(day_draws)
    bypos={d["pos"]:d for d in history}
    if target_pos in bypos or target_pos<=2:
        return None
    prev=bypos.get(target_pos-1)
    earlier=bypos.get(target_pos-2)
    if prev is None or earlier is None or not contiguous(target_pos-1):
        return None
    previous_history=[d for d in history if d["pos"]<target_pos-1]
    return full_character(prev,earlier,previous_history)


def csv_export(rows):
    if not rows:return ""
    buffer=io.StringIO()
    writer=csv.DictWriter(buffer,fieldnames=list(rows[0]),delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    return "\ufeff"+buffer.getvalue()
