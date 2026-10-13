# -*- coding: utf-8 -*-
"""V14: 217-position temporal transition network for 20-of-80 Hızlı On.

A -> B is an OBSERVATIONAL association between successive unordered draw sets,
not a unique physical replacement mapping. Fair independent draws give:
  P(B in next | A in prior, B absent prior) = 20/80 = 0.25.
Even when A is retrospectively known to have LEFT, for B!=A and B absent prior:
  P(B in next | A left, B absent prior) = 20/79.
Every forecast below uses only the previous outcomes and a model fitted
strictly on a disjoint EARLIER set of calendar days. Fixed methods are compared
on identical targets; thousands of tested edges create multiple-testing risk.
"""
import csv
import io
import math
import random
from collections import Counter,defaultdict

from v11_arastirma import hour_draw_index,complete_preceding_12
from v12_80_kule import forward_towers,make_ready
from v13_havuz_koltuk import states_for_day,trained_model as v13_train, pick_20

LAGS=(1,2,3,6,12)
WEIGHTS={1:1.,2:.55,3:.4,6:.24,12:.16}
N=80
P=.25
PAIR_PRIOR=300
METHODS=("V14 bir-adım ağ","V14 çok-adım ağ","V13 sıcaklık","Rastgele20")
EXTRAS=("V12 ağ-kule",)
PHASES=("Gece","Sabah","Öğlen","Akşam")


def clock_slot(pos):
    """The 217 exact calendar positions, not sorted ballot-number positions."""
    if 1<=pos<=13:
        return "00", pos, "Gece"
    if 14<=pos<=217:
        hour=7+(pos-14)//12
        minute=(pos-14)%12+1
        group="Sabah" if hour<=11 else "Öğlen" if hour<=16 else "Akşam"
        return f"{hour:02d}",minute,group
    raise ValueError(f"Invalid daily draw position {pos}")


def pair_model(draws,train_days=36):
    """Learn conditional newcomer associations A_lag -> B_target, B absent t-1.

    Exposure for all possible B (rather than just winners), and t's actual
    balls contribute only to TRAINING model. No test date is inspected.
    """
    byday=defaultdict(list)
    for d in make_ready(draws):
        byday[d["day"]].append(d)
    days=sorted(byday)
    if len(days)<train_days:
        raise ValueError("Not enough training days")
    denom={lag:[[0]*81 for _ in range(81)] for lag in LAGS}
    hits={lag:[[0]*81 for _ in range(81)] for lag in LAGS}
    ret_n=[0]*81
    ret_hits=[0]*81
    rollover=Counter()
    train_trans=0
    for day in days[:train_days]:
        posmap={r["pos"]:r for r in byday[day]}
        for pos,target in posmap.items():
            prev=posmap.get(pos-1)
            if prev is None:continue
            prev_set=set(prev["nums"])
            target_set=set(target["nums"])
            for a in prev_set:
                ret_n[a]+=1
                ret_hits[a]+=a in target_set
            absent=[b for b in range(1,81) if b not in prev_set]
            entering=[b for b in target_set if b not in prev_set]
            turnover=len(prev_set-target_set)
            rollover[turnover]+=1
            train_trans+=1
            for lag in LAGS:
                source=posmap.get(pos-lag)
                if source is None:continue
                den=denom[lag];ok=hits[lag]
                for a in source["nums"]:
                    den_a=den[a];ok_a=ok[a]
                    for b in absent:
                        den_a[b]+=1
                    for b in entering:
                        ok_a[b]+=1
    return {"days":tuple(days[:train_days]),"den":denom,"hit":hits,
            "stay_count":ret_n,"stay_hit":ret_hits,
            "train_transitions":train_trans,
            "train_turnover":dict(rollover)}


def conditional(model,lag,a,b):
    sample=model["den"][lag][a][b]
    hits=model["hit"][lag][a][b]
    return (hits+P*PAIR_PRIOR)/(sample+PAIR_PRIOR)


def candidate_score(model, history_by_pos, target_pos, b, lags):
    terms=[]
    for lag in lags:
        r=history_by_pos.get(target_pos-lag)
        if r is None:continue
        shift=sum(conditional(model,lag,a,b)-P for a in r["nums"])/20
        terms.append((WEIGHTS[lag],shift))
    if not terms:return 0.
    return sum(w*s for w,s in terms)/sum(w for w,_ in terms)


def predict_20(model,history,target_pos,method="V14 çok-adım ağ",target_id=0):
    """Fixed 5 carry-overs + 15 newcomers. No target result in inputs."""
    bypos={r["pos"]:r for r in history}
    prev=bypos.get(target_pos-1)
    if prev is None:return None
    if method=="Rastgele20":
        return tuple(sorted(random.Random(31021+int(target_id)*101).sample(range(1,81),20)))
    prev_set=set(prev["nums"])
    # Retention probabilities trained on FIRST days only and heavily shrunk.
    stay=sorted(prev_set,key=lambda b:(
        -(model["stay_hit"][b]+P*PAIR_PRIOR)/(model["stay_count"][b]+PAIR_PRIOR),b))
    keep=stay[:5]
    absent=[b for b in range(1,81) if b not in prev_set]
    lags=(1,) if method=="V14 bir-adım ağ" else LAGS
    arrivals=sorted(absent,key=lambda b:(-candidate_score(model,bypos,target_pos,b,lags),b))[:15]
    result=tuple(sorted(keep+arrivals))
    assert len(result)==20 and len(set(result))==20
    return result


def leading_pairs(model,count=35,min_exposure=250):
    """Top associations chosen ONLY from training period (multiple tests!)."""
    scores=[]
    den=model["den"][1]
    hit=model["hit"][1]
    for a in range(1,81):
        for b in range(1,81):
            if a==b:continue # A present, B absent cannot be same
            exposure=den[a][b]
            if exposure<min_exposure:continue
            rate=hit[a][b]/exposure
            shrink=conditional(model,1,a,b)
            scores.append((shrink-P,exposure,a,b,rate))
    scores.sort(key=lambda row:(-row[0],-row[1],row[2],row[3]))
    return scores[:count]


def replay(draws,train_days=36):
    """Train on first 36 days, evaluate LATER 37 across entire 217-slot day."""
    allrows=make_ready(draws)
    byday=defaultdict(list)
    for d in allrows:
        byday[d["day"]].append(d)
    days=sorted(byday)
    if days and len(byday[days[-1]])<217:
        days=days[:-1]
    if len(days)<=train_days:
        raise ValueError("No held-out days")
    train_rows=[d for day in days[:train_days] for d in byday[day]]
    model=pair_model(train_rows,train_days)
    v13_model=v13_train(train_rows,train_days)
    leaders=leading_pairs(model)
    edge_eval={(a,b):[0,0,0,0] for _,_,a,b,_ in leaders}
    # Columns edge: known-source/absent-next-candidate exposures and actual hits;
    # retrospective A-LEAVES opportunities and B arrivals (never used for forecast).
    tledger=[]
    method_acc=defaultdict(lambda:[0,0,0,Counter(),0])
    change_acc=defaultdict(lambda:[0,0,0,Counter()])
    per_slot=defaultdict(lambda:[0,0,0])
    halves=defaultdict(lambda:[0,0,0,Counter()])
    paired_by_day=defaultdict(lambda:defaultdict(list))
    conditional_new=Counter()
    for day in days[train_days:]:
        records=sorted(byday[day],key=lambda r:r["pos"])
        bypos={r["pos"]:r for r in records}
        hist=[]
        for target in records:
            pos=target["pos"]
            prev=bypos.get(pos-1)
            if prev is None:
                hist.append(target)
                continue
            if target["no"]<=0:raise ValueError("Missing draw number")
            prevset=set(prev["nums"])
            targetset=set(target["nums"])
            unchanged=len(prevset&targetset)
            outgoing=prevset-targetset
            incoming=targetset-prevset
            hr,step,group=clock_slot(pos)
            change=change_acc[(group,hr)]
            change[0]+=1;change[1]+=unchanged;change[2]+=len(incoming)
            change[3][unchanged]+=1
            per=per_slot[pos]
            per[0]+=1;per[1]+=unchanged;per[2]+=len(incoming)
            half=("İlk 6" if step<=6 else "Son 6" if step<=12 else "01:02 ek")
            hs=halves[(group,half)]
            hs[0]+=1;hs[1]+=unchanged;hs[2]+=len(incoming)
            hs[3][unchanged]+=1
            for a,b in edge_eval:
                if a in prevset and b not in prevset:
                    v=edge_eval[(a,b)]
                    v[0]+=1
                    v[1]+=int(b in incoming)
                    if a in outgoing:
                        v[2]+=1
                        v[3]+=int(b in incoming)
            proposals={}
            proposals["V14 bir-adım ağ"]=predict_20(model,hist,pos,"V14 bir-adım ağ",target["no"])
            proposals["V14 çok-adım ağ"]=predict_20(model,hist,pos,"V14 çok-adım ağ",target["no"])
            proposals["Rastgele20"]=predict_20(model,hist,pos,"Rastgele20",target["no"])
            states=states_for_day(hist)
            proposals["V13 sıcaklık"]=pick_20(states,v13_model,pos,"Koltuk-model")[0]
            prior=complete_preceding_12(bypos,pos)
            if prior and hour_draw_index(pos) in (7,8,9,10,11,12):
                pro,_=forward_towers(prior,target["no"])
                proposals["V12 ağ-kule"]=tuple(pro["Ağ-kule"])
            row={"Tarih":day,"Hedef no":target["no"],
                 "Gün içi":pos,"Saat":target["dt"][11:16],
                 "Saat grubu":group,"Saat içi sıra":step,
                 "Önceki 20'den kalan":unchanged,
                 "Önceki 20'den ayrılan":len(outgoing),
                 "Yeni giren":len(incoming),
                 **{name:None for name in METHODS+EXTRAS}}
            for name,nums in proposals.items():
                good=len(targetset&set(nums))
                row[name]=good
                key=(group,name)
                m=method_acc[key]
                m[0]+=1;m[1]+=good;m[2]+=int(good==20)
                m[3][good]+=1;m[4]=max(m[4],good)
                paired_by_day[day][name].append(good)
            tledger.append(row)
            hist.append(target)
    numtargets=len(tledger)
    methodology=[]
    for (group,name),v in sorted(method_acc.items()):
        n,total,full,histogram,mx=v
        methodology.append({"Gün dönemi":group,"Yöntem":name,
                            "Hedef":n,"Ortalama 20'de":round(total/n,4),
                            "Matematik beklenen":5.0,
                            "En fazla":mx,"20/20":full,
                            "Dağılım 0..20":"/".join(str(histogram[j]) for j in range(21))})
    transitions=[]
    for (group,hr),v in sorted(change_acc.items()):
        n,stayed,entering,histogram=v
        transitions.append({"Gün dönemi":group,"Saat":hr,
                            "Geçiş sayısı":n,
                            "Önceki 20'den ortalama kalan":round(stayed/n,4),
                            "Bağımsız beklenti kalan":5.0,
                            "Ortalama yeni gelen":round(entering/n,4),
                            "Bağımsız beklenti yeni":15.0,
                            "Kalan dağılım 0..20":"/".join(str(histogram[j]) for j in range(21))})
    position_rows=[{"Gün sıra":pos,"Saat":clock_slot(pos)[0],
                    "Saat içi sıra":clock_slot(pos)[1],
                    "Hedef":v[0],"Ortalama tekrar":round(v[1]/v[0],4),
                    "Beklenen":5.0,"Yeni gelen ortalama":round(v[2]/v[0],4)}
                   for pos,v in sorted(per_slot.items())]
    half_rows=[{"Gün dönemi":group,"Saat yarısı":half,
                "Hedef":v[0],"Ortalama tekrar":round(v[1]/v[0],4),
                "Rastgele beklenen tekrar":5.0,
                "Ortalama yeni sayı":round(v[2]/v[0],4)}
               for (group,half),v in sorted(halves.items())]
    relation=[]
    for lift,_,a,b,train_rate in leaders:
        ev,h,leave,leave_h=edge_eval[(a,b)]
        relation.append({
            "Kaynak":a,"Yeni sayı":b,
            "Eğitimde koşullu %":round(100*train_rate,3),
            "Eğitimde filtreli tahmin %":round(100*(P+lift),3),
            "Sonraki günler gözlem":ev,
            "Sonraki günler B geldi":h,
            "Sonraki günler gerçek %":round(100*h/ev,3) if ev else 0,
            "Adil beklenen %":25.,
            "A gerçekten ayrıldı koşul":leave,
            "B ayrılma sonrası geldi":leave_h,
            "Bu koşulda %":round(100*leave_h/leave,3) if leave else 0,
            "A ayrıldı şartlı adil %":round(100*20/79,3),
            "Not":"İlk 36 güne göre seçilmiş ilişki, 80x80 tarama çoklu sınama"
        })
    paired=[]
    for name in METHODS+EXTRAS:
        vals=[]
        for day,v in paired_by_day.items():
            if name in v and "Rastgele20" in v and name!="Rastgele20":
                # Same calendar day and same TARGET slots (V12 subset only).
                if name=="V12 ağ-kule":
                    ids=[r for r in tledger if r["Tarih"]==day and r.get(name) is not None]
                    diff=sum(r[name]-r["Rastgele20"] for r in ids)/len(ids) if ids else 0.
                else:
                    # Others have all the target draws (except first of each day).
                    diff=(sum(v[name])-sum(v["Rastgele20"]))/len(v[name])
                vals.append(diff)
        if vals:
            nd=len(vals)
            avg=sum(vals)/nd
            var=sum((x-avg)**2 for x in vals)/(nd-1) if nd>1 else 0.
            se=math.sqrt(var/nd)
            paired.append({"Yöntem":name,"Test günü":nd,
                           "Rastgeleye karşı fark":round(avg,4),
                           "95% gün-kümeli yaklaşık alt":round(avg-1.96*se,4),
                           "95% gün-kümeli yaklaşık üst":round(avg+1.96*se,4),
                           "Not":"Çoklu yöntem seçimi / kümelenme nedeniyle keşif amaçlı"})
    return {
        "meta":{"train_days":train_days,"holdout_days":len(days)-train_days,
                "first_train":days[0],"last_train":days[train_days-1],
                "first_test":days[train_days],"last_test":days[-1],
                "train_transitions":model["train_transitions"],
                "test_transitions":numtargets,
                "note":"A->B is association, not physically assigned replacement."},
        "methods":methodology,"times":transitions,"positions":position_rows,
        "half_hours":half_rows,
        "pairs":relation,"paired":paired,"ledger":tledger,
        "model":model,"v13_model":v13_model
    }


def preview(current_day,model,v13_model,target_pos,target_no):
    """One future target only, with 80 nodes and 20-number proposals."""
    records=make_ready(current_day)
    positions={d["pos"] for d in records}
    if target_pos in positions or target_pos not in range(2,218):return None
    if target_pos-1 not in positions:return None
    prior=[d for d in records if d["pos"]<target_pos]
    predictions={name:predict_20(model,prior,target_pos,name,target_no)
                 for name in ("V14 bir-adım ağ","V14 çok-adım ağ")}
    states=states_for_day(prior)
    predictions["V13 sıcaklık"]=pick_20(states,v13_model,target_pos,"Koltuk-model")[0]
    bypos={d["pos"]:d for d in prior}
    prev=bypos[target_pos-1]
    prev_set=set(prev["nums"])
    ranks=[]
    for b in range(1,81):
        source=candidate_score(model,bypos,target_pos,b,LAGS) if b not in prev_set else 0.
        ranks.append({"Sayı":b,"Önceki 20'de":b in prev_set,
                      "Birleşik geçiş puanı":round(source,5),
                      "V14'te seçili":b in predictions["V14 çok-adım ağ"]})
    ranks.sort(key=lambda r:(-r["Birleşik geçiş puanı"],r["Sayı"]))
    return {"target":target_no,"pos":target_pos,
            "predictions":predictions,"nodes":ranks,
            "day_phase":clock_slot(target_pos)[2]}


def csv_export(rows):
    if not rows:return ""
    fp=io.StringIO()
    writer=csv.DictWriter(fp,fieldnames=list(rows[0]),delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    return "\ufeff"+fp.getvalue()
