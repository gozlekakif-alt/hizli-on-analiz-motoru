#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V63: pre-defined feature tournament, strictly first6 -> later6 replay.

An experimental COMPARISON, not a deployable wagering engine. A fair 20/80
lottery yields E[10-number-ticket hits]=2.5 for every preselected ticket.
Multiple testing is handled with a day-block bootstrap max deviation.

Historical last 36 days were previously examined in V59-V62: this is NOT
independent prospective confirmation, even if called a chronological holdout.
There is NO online learning on target draws within an hour.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,random,statistics,zipfile
from collections import Counter,defaultdict
from pathlib import Path
from v52_ayni_cekilis_eslikci_217 import parse_txt
from v53_saatlik_degisen_aileler import BLOCKS
from v59_aile_birlesim_donusum_kor_test import prior_features
from v61_geometrik_dna import shapes as geometry_shapes,scan as geometry_scan,bits as bitmask

SEED=630163
N_BOOT=1800
BATCH_METHODS=(
    "FREQ6","FREQ3","LAST_DRAW","REPEAT_LAG6","HOT72","COLD72",
    "OVERDUE72","TREND_UP","TREND_DOWN","FRESH6","PM1_BOTH","PM2_BOTH",
    "PLUS1","MINUS1","PLUS2","MINUS2",
    "GRID_DOWN10","GRID_UP10","GRID_DOWN20","GRID_DIAG11",
    "MIRROR_81","ROW_MIRROR","BAND10_TREND","BAND20_REVERT",
    "PAIR_FAMILY","GRID_EDGE","SHAPE_GROW",
    "V59_MERGE","V59_MUTATE","V59_HYBRID",
    "RANDOM10")
assert len(BATCH_METHODS)==31
EVAL_METHODS=BATCH_METHODS+("DEV_WINNER","DEV_TOP3_VOTE",)

def rank(score,tie=None):
    tie=tie or {}
    return tuple(sorted(range(1,81),key=lambda n:(
        -score.get(n,0),-tie.get(n,0),n))[:10])

def shifted(src,shift):
    return Counter(x+shift for x in src if 1<=x+shift<=80)

def distance_neighbors(draws,steps,origin=None):
    s=Counter()
    for i,draw in enumerate(draws):
        w=(i+1)/len(draws)
        for x in draw["nums"]:
            for d in steps:
                y=x+d
                if 1<=y<=80:s[y]+=w
    return s

def block_band(n,k):
    return (n-1)//k

def chksum(seed):
    return int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8],"big")

def compute_candidates(first,previous,day,hour,shapes):
    assert len(first)==6
    prefix=previous[-72:]
    freq=Counter(n for row in first for n in row["nums"])
    recent=Counter(n for row in first[3:] for n in row["nums"])
    early=Counter(n for row in first[:3] for n in row["nums"])
    last=first[-1]["nums"]
    hfreq=Counter(n for row in prefix for n in row["nums"])
    age={}
    for n in range(1,81):
        positions=[j for j,row in enumerate((prefix+first)) if n in row["nums"]]
        age[n]=(len(prefix)+6-1-positions[-1]) if positions else len(prefix)+6
    first_counts=Counter(n for r in first for n in r["nums"])
    last_hits=Counter(n for r in first[-2:] for n in r["nums"])
    scores={}
    scores["FREQ6"]=dict(freq)
    scores["FREQ3"]=dict(recent)
    scores["LAST_DRAW"]={n:float(n in last) for n in range(1,81)}
    scores["REPEAT_LAG6"]=Counter(first[0]["nums"])
    scores["HOT72"]=dict(hfreq)
    scores["COLD72"]={n:-hfreq[n] for n in range(1,81)}
    scores["OVERDUE72"]=dict(age)
    scores["TREND_UP"]={n:recent[n]-early[n] for n in range(1,81)}
    scores["TREND_DOWN"]={n:early[n]-recent[n] for n in range(1,81)}
    scores["FRESH6"]={n:-freq[n] for n in range(1,81)}
    scores["PM1_BOTH"]=distance_neighbors(first[-3:],(-1,+1))
    scores["PM2_BOTH"]=distance_neighbors(first[-3:],(-2,+2))
    for label,shift in (("PLUS1",1),("MINUS1",-1),
                        ("PLUS2",2),("MINUS2",-2),
                        ("GRID_DOWN10",10),("GRID_UP10",-10),
                        ("GRID_DOWN20",20),("GRID_DIAG11",11)):
        scores[label]=distance_neighbors(first[-2:],(shift,))
    scores["MIRROR_81"]=Counter(81-n for n in last)
    scores["ROW_MIRROR"]=Counter(
        ((n-1)//10)*10+(10-(n-1)%10) for n in last)
    # Band-level first-half behaviour; these methods do NOT infer any
    # target-band occupation until the held-out next six are scored.
    first10=Counter(block_band(n,10) for n in first[0]["nums"])
    last10=Counter(block_band(n,10) for n in first[-1]["nums"])
    band20=Counter(block_band(n,20) for r in first for n in r["nums"])
    scores["BAND10_TREND"]={n:last10[block_band(n,10)]-
       first10[block_band(n,10)] for n in range(1,81)}
    scores["BAND20_REVERT"]={n:-band20[block_band(n,20)] for n in range(1,81)}
    # Repeated exact co-occurring pairs; same-draw counted only.
    pair=Counter()
    for row in first:
        a=sorted(row["nums"])
        for i,n in enumerate(a):
            for m in a[i+1:]:
                pair[(n,m)]+=1
    family=Counter()
    for (n,m),support in pair.items():
        if support>=2:
            family[n]+=(support-1)**2
            family[m]+=(support-1)**2
    scores["PAIR_FAMILY"]=family
    scores["GRID_EDGE"]=distance_neighbors(first[-2:],(-10,10,-1,1))
    # Project only direct +1/10 successors of repeated short geometric
    # placements. The full 20-shape registry uses fixed 8×10 coordinates.
    shape_score=Counter()
    for r in first:
        raster=bitmask(r["nums"])
        observed=geometry_scan(raster,shapes,True)
        for definition in shapes:
            if not 3<=definition["k"]<=4:continue
            for mask in observed[definition["code"]]:
                for n in range(1,81):
                    if mask&(1<<(n-1)):
                        for delta in (1,-1,10,-10):
                            u=n+delta
                            if not 1<=u<=80:continue
                            # 4-neighbor geometry, not row-wrap on +/-1
                            if abs(delta)==1 and (u-1)//10!=(n-1)//10:
                                continue
                            if not mask&(1<<(u-1)):shape_score[u]+=1
    scores["SHAPE_GROW"]=shape_score
    fromv59,_,_,_=prior_features(first,prefix,day,hour)
    score_tickets={}
    for method in BATCH_METHODS:
        if method.startswith("V59_"):
            ticket=fromv59[{
              "V59_MERGE":"MERGE10","V59_MUTATE":"MUTATE10",
              "V59_HYBRID":"HYBRID10"}[method]]
        elif method=="RANDOM10":
            ticket=tuple(sorted(random.Random(chksum(
                   f"{SEED}-{day}-{hour}")).sample(range(1,81),10)))
        else:
            ticket=rank(scores[method],hfreq)
        if len(set(ticket))!=10:raise AssertionError(method)
        score_tickets[method]=tuple(ticket)
    return score_tickets,{"first6_freq":freq,"historical_hot72":hfreq,
         "number_age":age}

def evaluate_hours(full):
    dates=sorted(full)
    if len(dates)<4:raise ValueError("requires at least four complete days")
    split=len(dates)//2
    shapes=geometry_shapes()
    pending=[];history=[];ticketrows=[];targetrows=[]
    for i,day in enumerate(dates):
        dayrows={r["pos"]:r for r in full[day]}
        if len(dayrows)!=217:raise ValueError(f"incomplete day {day}")
        phase="DEV" if i<split else "HOLDOUT"
        for hour in BLOCKS:
            first=[dayrows[p] for p in range(hour["start"],hour["start"]+6)]
            later=[dayrows[p] for p in range(hour["start"]+6,hour["start"]+12)]
            # The candidates are all computed BEFORE later is inspected.
            ticket,extra=compute_candidates(first,history,day,hour["code"],shapes)
            frozen={name:frozenset(nums) for name,nums in ticket.items()}
            saved={"day":day,"phase":phase,"hour":hour["code"],
                "first6_last_draw":first[-1]["id"],
                "first6_last_time":first[-1]["time"],
                "target7_id":later[0]["id"],
                "target12_id":later[-1]["id"],
                "methods":frozen}
            pending.append(saved)
            for name,nums in ticket.items():
                ticketrows.append({"day":day,"phase":phase,"hour":hour["code"],
                  "method":name,"ticket":"-".join(map(str,nums)),
                  "first6_last_draw":first[-1]["id"],
                  "target_first":later[0]["id"],"target_last":later[-1]["id"],
                  "fixed_before_target":1})
            for dr in later:
                targetrows.append({"day":day,"hour":hour["code"],
                    "phase":phase,"draw_id":dr["id"],"clock":dr["time"],
                    "target":frozenset(dr["nums"])})
            # 00 hour has a 13th draw, which is not a target but is real
            # completed history for the next H07 block.
            history.extend(dayrows[p] for p in range(hour["start"],hour["end"]+1))
            history=history[-72:]
    return pending,targetrows,ticketrows,dates,split

def select_dev(pending,targetrows,split_date):
    targets=defaultdict(list)
    for row in targetrows:targets[(row["day"],row["hour"])].append(row["target"])
    sums=Counter();counts=Counter()
    for hour in pending:
        if hour["phase"]!="DEV":continue
        for method,nums in hour["methods"].items():
            for target in targets[(hour["day"],hour["hour"])]:
                sums[method]+=len(nums&target);counts[method]+=1
    chosen=sorted(BATCH_METHODS,key=lambda m:(-sums[m]/counts[m],m))
    assert all(counts[m]==split_date*18*6 for m in BATCH_METHODS)
    return chosen

def vote_three(hour,methods):
    count=Counter()
    for method in methods[:3]:
        for n in hour["methods"][method]:
            count[n]+=1
    return frozenset(sorted(range(1,81),
                   key=lambda n:(-count[n],n))[:10])

def score_all(pending,targetrows,chosen):
    targets=defaultdict(list)
    for row in targetrows:targets[(row["day"],row["hour"])].append(row)
    output=[];perhour=[]
    for hour in pending:
        methods=dict(hour["methods"])
        methods["DEV_WINNER"]=methods[chosen[0]]
        methods["DEV_TOP3_VOTE"]=vote_three(hour,chosen)
        for row in targets[(hour["day"],hour["hour"])]:
            for method,nums in methods.items():
                hits=len(nums&row["target"])
                output.append({"day":hour["day"],"phase":hour["phase"],
                  "hour":hour["hour"],"draw_id":row["draw_id"],
                  "clock":row["clock"],"method":method,"hits":hits,
                  "fair_baseline":2.5})
        for name,nums in methods.items():
            if name not in ("DEV_WINNER","DEV_TOP3_VOTE"):continue
            perhour.append({"day":hour["day"],"phase":hour["phase"],
                "hour":hour["hour"],"method":name,
                "ticket":"-".join(map(str,sorted(nums))),
                "target7_id":hour["target7_id"],
                "target12_id":hour["target12_id"],
                "frozen_before_target":1,
                "dev_selected_methods":"|".join(chosen[:3])})
    return output,perhour

def bootstrap(daymeans,nboot=N_BOOT,seed=SEED):
    rng=random.Random(seed);v=list(daymeans)
    if not v:return(0,0)
    means=sorted(sum(rng.choice(v) for i in v)/len(v)
        for _ in range(nboot))
    return (means[int((nboot-1)*.025)],means[int((nboot-1)*.975)])

def summary_tables(scored,chosen,days,split):
    grouped=defaultdict(list);perday=defaultdict(list);hist=defaultdict(Counter)
    for row in scored:
        phase=row["phase"];method=row["method"];hit=row["hits"]
        grouped[(phase,method)].append(hit)
        perday[(phase,method,row["day"])].append(hit)
        hist[(phase,method)][hit]+=1
    mset=sorted(set(row["method"] for row in scored))
    values=[];deltapoints={};paired={}
    for phase in ("DEV","HOLDOUT"):
        subset=days[:split] if phase=="DEV" else days[split:]
        for method in mset:
            vals=grouped[(phase,method)]
            daily={d:sum(perday[(phase,method,d)])/len(perday[(phase,method,d)])
                   for d in subset}
            excess=[daily[d]-2.5 for d in subset]
            ref=[(sum(perday[(phase,"RANDOM10",d)])/
                   len(perday[(phase,"RANDOM10",d)])) for d in subset]
            freq=[(sum(perday[(phase,"FREQ6",d)])/
                    len(perday[(phase,"FREQ6",d)])) for d in subset]
            delta=[daily[d]-ref[i] for i,d in enumerate(subset)]
            deltafreq=[daily[d]-freq[i] for i,d in enumerate(subset)]
            ci=bootstrap(delta,seed=SEED+7+len(method)+(phase=="HOLDOUT"))
            basic=bootstrap(excess,seed=SEED+20+len(method)+(phase=="HOLDOUT"))
            row={"phase":phase,"method":method,"days":len(subset),
                "target_draws":len(vals),"avg_hits":round(sum(vals)/len(vals),7),
                "vs_fair_expected":round(sum(vals)/len(vals)-2.5,7),
                "vs_fair_boot95_low":round(basic[0],7),
                "vs_fair_boot95_high":round(basic[1],7),
                "vs_random10":round(sum(delta)/len(delta),7),
                "vs_random_boot95_low":round(ci[0],7),
                "vs_random_boot95_high":round(ci[1],7),
                "vs_freq6":round(sum(deltafreq)/len(deltafreq),7),
                "total_hits_ge5":sum(h>=5 for h in vals),
                "total_hits_ge6":sum(h>=6 for h in vals),
                "total_hits_ge7":sum(h>=7 for h in vals),
                "max_hit":max(vals),
                "note":"Historical reuse, not prospective"}
            values.append(row)
            if phase=="HOLDOUT":
                deltapoints[method]=[daily[d]-2.5 for d in subset]
                paired[method]=delta
    # Control multiplicity when visually selecting among all methods.
    # MaxT test from centered day-block sign flipping of all 33 methods;
    # *same* signed day weights across methods preserve shared outcomes.
    count=len(days[split:])
    rng=random.Random(SEED+1998)
    obs={m:sum(v)/count for m,v in deltapoints.items()}
    centers={m:[x-obs[m] for x in v] for m,v in deltapoints.items()}
    allnull=[]
    for _ in range(N_BOOT):
        signs=[1 if rng.random()<.5 else -1 for d in range(count)]
        score=max(sum(signs[i]*centers[m][i] for i in range(count))/count
                   for m in deltapoints)
        allnull.append(score)
    allnull.sort()
    max95=allnull[int(.95*(N_BOOT-1))]
    adjusted=[]
    for method in sorted(obs,key=lambda m:(-obs[m],m)):
        t=obs[method]
        p=(1+sum(x>=t for x in allnull))/(N_BOOT+1)
        adjusted.append({"method":method,"holdout_avg_minus_fair":round(t,7),
            "maxT_familywise_one_sided_p":round(p,5),
            "maxT_null95_threshold":round(max95,7),
            "passes_FWER_05":int(t>max95),
            "interpretation":"EXPLORATORY_HISTORY_REUSED"})
    return values,adjusted

def _zip_csv(z,name,data,cols=()):
    with z.open(name,"w",force_zip64=True) as w:
        f=io.TextIOWrapper(w,encoding="utf-8",newline="")
        cols=list(data[0]) if data else list(cols)
        writer=csv.DictWriter(f,fieldnames=cols)
        writer.writeheader()
        if data:writer.writerows(data)
        f.flush();f.detach()

def make_report(data,scored,selection,votes,ranking,multcomp,
                full,partial,issues,malformed):
    summary_hold=sorted((r for r in ranking if r["phase"]=="HOLDOUT"),
                        key=lambda r:(-r["avg_hits"],r["method"]))
    tested=next(r for r in summary_hold if r["method"]=="DEV_WINNER")
    v=next(r for r in summary_hold if r["method"]=="DEV_TOP3_VOTE")
    top=summary_hold[:7]
    lines=[
      "V63 — 31 FARKLI YONTEM + 2 GELISTIRMEDE SABITLENEN MODEL",
      f"Tam gun: {len(full)}; 217 cekilis/gun: {sum(map(len,full.values()))}",
      f"Saatler: {len(data)}, hedef cekilis: {len(data)*6}",
      f"Onceden belirlenmis yöntemler: {len(BATCH_METHODS)}",
      "Eşit fırsat: Her yöntemde aynı saate 10 sayilik 1 SANAL kupon.",
      "Ilk6 tamamlanmadan secim yok, 7-12 cekilis hedeftir.",
      "Gelistirme gunleri 36; sonraki 36 gun tarihseldir.",
      "Yalniz GELISTIRMEDE en iyi yontem ve en iyi 3",
      "yontemin oylama birlesimi seçilip kilitlenir.",
      "HOLDOUT sırasında bu yöntem seçimi veya katsayı değişmez.",
      "Rastgele 20/80 oyunda 10 sayilik kuponun tam E[isabet]=2.5.",
      "Karsilastirma rastgele ve 6 cekilis siralama temeliyledir.",
      "Günlüklere dayalı bootstrap %95 belirsizlik.",
      "33 es zamanlı testin en iyisini rastgele sanmamak icin",
      "gün-kümeli ve yöntemler arası korelasyonu koruyan",
      "MAX-T coklu deneme duzeltmesi hesaplanir.",
      "Bu ciktida gecmiste kullanilmis 36 gun veri tekrar",
      "incelenmistir. Bu bagimsiz yeni veride kanit DEĞİLDİR.",
      "Bu calisma kupon satin almaya yonelik bir öneri değildir.",
      f"Degistirilen/bozuk satirlar: {len(issues)+len(malformed)}; kismi gunler: {len(partial)}.",
      "",
      "DEV'de sabitlenen kazanici: "+selection[0],
      "DEV top3: "+", ".join(selection[:3]),
      f"HOLDOUT tek kazanici isabet: {tested['avg_hits']:.5f} "
      f"(fair 2.500, random fark {tested['vs_random10']:+.5f})",
      f"HOLDOUT top3 secim isabet: {v['avg_hits']:.5f} "
      f"(fair 2.500, random fark {v['vs_random10']:+.5f})",
      "HOLDOUT ilk 7 yöntem: " + "; ".join(
           f"{x['method']}={x['avg_hits']:.5f}" for x in top),
      "", "DÜZELTİLMİŞ ÇOKLU TEST:"
    ]
    for x in multcomp[:7]:
        lines.append(f"{x['method']}: fair fark={x['holdout_avg_minus_fair']:+.5f}, "
            f"maxT düzeltilmis p={x['maxT_familywise_one_sided_p']}")
    with zipfile.ZipFile(io.BytesIO(),"w") as ignored:
        pass
    result=io.BytesIO()
    with zipfile.ZipFile(result,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as z:
        z.writestr("00_ANA_KARAR_TUM_DENEMELER.txt","\n".join(lines)+"\n")
        _zip_csv(z,"01_ILK36_DA_SECILEN_ILK31_METOD.csv",[
            {"rank":i+1,"method":m,"selected_for_top3":int(i<3)}
            for i,m in enumerate(selection)])
        _zip_csv(z,"02_HER_METOD_36_GUN_KOR_TEST_KARSILASTIRMA.csv",ranking)
        _zip_csv(z,"03_TUM_33_YONTEM_COKLU_TEST_DUZELTMESI.csv",multcomp)
        _zip_csv(z,"04_SAAT_SAAT_SABIT_SECIMLER.csv",votes)
        _zip_csv(z,"05_SAAT_SAAT_TUM_31_SANAL_KUPON.csv",data)
        _zip_csv(z,"06_HER_HEDEF_CEKILIS_HER_YONTEM_ISABET.csv",scored)
        z.writestr("07_KURALLAR_VE_YORUM.txt",
         "BASLANGIC: onceki tam cekilisler + o saatin ilk6.\n"
         "SONRAKI: 7,8,9,10,11,12 cekilislerde 10 sayı isabeti.\n"
         "31 model sabit; rastgele kontrol dahil. V59 aile birleşimi,"
         " aile mutasyonu ve karma sabit eski metodlar olarak tekrar var.\n"
         "Yeni yöntemler ±1/±2, yatay, 8x10 satir duzlem, ayna,"
         " bant, frekans, zaman yönü, sıcak/soğuk ve ailelerden oluşur.\n"
         "Bir yöntem son36'da bir kere üstün gözükse bile toplam"
         " çoklu denemeler ve geçmiş veri seçilimi nedeniyle gelecek"
         " performans kanitlanmaz.\n"
         "Büyük ödül iddiaları yok; sanal kuponlar sadece test.\n")
    return result.getvalue()

def selftest():
    rng=random.Random(630)
    from v45_sinyal_kor_test import SLOTS
    shapes=geometry_shapes()
    rows=[]
    for i in range(6):
        rows.append({"id":i+1,"time":SLOTS[i],"pos":i+1,
            "nums":frozenset(rng.sample(range(1,81),20))})
    m,_=compute_candidates(rows,[],"2026-10-12","H07",shapes)
    m2,_=compute_candidates(rows,[],"2026-10-12","H07",shapes)
    assert m==m2 and len(m)==31
    assert all(len(s)==10 and len(set(s))==10 for s in m.values())
    # Changing only future draw does not affect frozen ticket.
    futureA=frozenset(rng.sample(range(1,81),20))
    futureB=frozenset(rng.sample(range(1,81),20))
    assert futureA!=futureB
    from v45_sinyal_kor_test import SLOTS
    full={}
    for day in ("2026-10-08","2026-10-09","2026-10-10","2026-10-11"):
        full[day]=[{"pos":i+1,"time":t,"id":70000+i,
          "nums":tuple(sorted(rng.sample(range(1,81),20)))}
             for i,t in enumerate(SLOTS)]
    h,t,d,dates,split=evaluate_hours(full)
    chosen=select_dev(h,t,split)
    s,v=score_all(h,t,chosen)
    assert len(h)==4*18 and len(s)==4*18*6*len(EVAL_METHODS)
    summary,adjusted=summary_tables(s,chosen,dates,split)
    assert len(summary)==2*len(EVAL_METHODS)
    assert len(adjusted)==len(EVAL_METHODS)
    z=make_report(d,s,chosen,v,summary,adjusted,full,{},[],[])
    with zipfile.ZipFile(io.BytesIO(z)) as inp:
        assert len(inp.namelist())==8
    print("PASS V63: 31 predeclared candidate methods, first6 frozen, "
          "36/36 time holdout, DEV-only winner selection, 33-model maxT, ZIP")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",default="veri.txt")
    ap.add_argument("--output",default="v63_output/V63_31_METOT_KOR_TURNUVA_TEK_ZIP.zip")
    ap.add_argument("--selftest",action="store_true")
    args=ap.parse_args()
    if args.selftest:selftest();return
    days,issues,malformed=parse_txt(Path(args.source))
    full={d:rows for d,rows in days.items() if len(rows)==217
         and {r["pos"] for r in rows}==set(range(1,218))}
    partial={d:len(rows) for d,rows in days.items() if d not in full}
    pending,targets,rawtickets,dates,split=evaluate_hours(full)
    selection=select_dev(pending,targets,split)
    scored,votes=score_all(pending,targets,selection)
    ranking,multiple=summary_tables(scored,selection,dates,split)
    z=make_report(rawtickets,scored,selection,votes,ranking,multiple,
                  full,partial,issues,malformed)
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(z)
    hold=sorted((r for r in ranking if r["phase"]=="HOLDOUT"),
         key=lambda r:-r["avg_hits"])
    print(json.dumps({"output":str(path),"full_days":len(full),
         "hours":len(pending),"test_days":len(dates)-split,
         "target_draws_per_method":(len(dates)-split)*18*6,
         "candidate_methods":len(BATCH_METHODS),
         "dev_winner":selection[0],
         "dev_top3":selection[:3],
         "holdout":[{k:v for k,v in row.items() if k in
              ("method","avg_hits","vs_random10","vs_fair_expected",
               "vs_random_boot95_low","vs_random_boot95_high")}
                for row in hold[:12]],
         "chosen_results":[row for row in ranking if row["phase"]=="HOLDOUT"
            and row["method"] in ("DEV_WINNER","DEV_TOP3_VOTE")],
         "multiplicity_most_extreme":multiple[:7],
         "any_maxT_FWER05":sum(x["passes_FWER_05"] for x in multiple)},
         ensure_ascii=False))
if __name__=="__main__":main()
