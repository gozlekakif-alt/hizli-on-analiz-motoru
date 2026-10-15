#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V59 Family union/mutation 10-number hypotheses: genuine chronological holdout.

No future leakage: a fixed 10-number selection is made after the FIRST SIX
draws of each hour, before any target draws 7..12 are inspected. Prior 72
draws are available only for tie-breaking. Comparison baselines: first-six
frequency, seeded random, and theoretical fair 20-of-80 hypergeometric RNG.

This is a retrospective held-out replay, NOT a prospective test and no claim
that lottery draws are predictable. 36 days dev + 36 days holdout.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
import argparse,csv,hashlib,io,json,math,random,statistics,zipfile

from v52_ayni_cekilis_eslikci_217 import parse_txt
from v53_saatlik_degisen_aileler import BLOCKS

METHODS=("MERGE10","MUTATE10","HYBRID10","FREQ10","RANDOM10")
FORECAST_DRAWS=6
SEED=590777
N_BOOT=1600

def fam_key(nums):return "-".join(map(str,nums))
def kprob(k):
    return math.prod((20-i)/(80-i) for i in range(k))
def hyper_tail(cut):
    return sum(math.comb(10,k)*math.comb(70,20-k)/math.comb(80,20)
               for k in range(cut,11))

def canonical(row):
    return {"pos":int(row["pos"]),"id":int(row["id"]),
            "time":str(row["time"]),"nums":frozenset(int(x) for x in row["nums"])}

def roots_of_six(first):
    # All maximal intersections of two distinct initial draws.
    # Exact support is checked independently for every root.
    all_intersections=set()
    for i in range(len(first)):
        for j in range(i+1,len(first)):
            inter=frozenset(first[i]["nums"] & first[j]["nums"])
            if len(inter)>=2:all_intersections.add(inter)
    roots=[]
    for fm in sorted(all_intersections,key=lambda s:(-len(s),tuple(sorted(s)))):
        if any(fm<=r for r in roots):continue
        n=sum(fm<=r["nums"] for r in first)
        assert n>=2
        roots.append(fm)
    return tuple(roots)

def prior_features(first,previous72,day,hour):
    if len(first)!=6:raise ValueError("Exactly first 6 observed draws required.")
    fr=Counter(n for dr in first for n in dr["nums"])
    hist=Counter(n for dr in previous72[-72:] for n in dr["nums"])
    roots=roots_of_six(first)
    pair_support=Counter(p for dr in first for p in combinations(sorted(dr["nums"]),2))
    eligible=sorted(((pair,n) for pair,n in pair_support.items() if n>=2),
                    key=lambda x:(-x[1],x[0]))
    top_pairs=eligible[:16]

    # Hypothesis A: two previously recurrent size-2 subfamilies combine.
    # Event candidates are k=3 or k=4 set unions, frozen before target.
    pairs=[]
    for (a,ct_a),(b,ct_b) in combinations(top_pairs,2):
        union=tuple(sorted(set(a)|set(b)))
        if not 3<=len(union)<=4:continue
        shared=len(set(a)&set(b))
        first_overlap=sum(set(union)<=dr["nums"] for dr in first)
        strength=(ct_a-1)*(ct_b-1)+1.15*first_overlap
        strength+=0.12*(4-len(union))
        pairs.append((strength,union,a,b,ct_a,ct_b,shared,first_overlap))
    pairs.sort(key=lambda t:(-t[0],len(t[1]),t[1],t[2],t[3]))
    locked=[];unique_unions=set()
    for item in pairs:
        if item[1] in unique_unions:continue
        locked.append(item);unique_unions.add(item[1])
        if len(locked)>=12:break

    # Two pre-registered top union predictions, distinct if possible.
    meeting_predictions=locked[:2]
    merge=defaultdict(float)
    for i,(strength,union,*_) in enumerate(locked):
        weight=strength/(1+0.35*i)/(len(union)**0.6)
        for n in union:merge[n]+=weight
    for r in roots:
        weight=0.21*(sum(r<=d["nums"] for d in first)-1)/math.sqrt(len(r))
        for n in r:merge[n]+=weight

    # Hypothesis B: two active pair families with one shared number are
    # one-number mutation siblings; use their relationship network. Nothing
    # about a later draw is used to construct their status.
    mutate=defaultdict(float)
    node_to_pair=defaultdict(list)
    for p,s in eligible:
        for n in p:node_to_pair[n].append((p,s))
    for hub,edges in node_to_pair.items():
        edges=sorted(edges,key=lambda x:(-x[1],x[0]))[:15]
        for (a,ca),(b,cb) in combinations(edges,2):
            free_a=next(x for x in a if x!=hub)
            free_b=next(x for x in b if x!=hub)
            if free_a==free_b:continue
            val=(ca-1)*(cb-1)
            mutate[hub]+=0.25*val
            mutate[free_a]+=0.65*val
            mutate[free_b]+=0.65*val
    for r in roots:
        for n in r:mutate[n]+=0.1*len(r)

    def ranking(points):
        # History tie-break is allowed only if occurred strictly earlier.
        return tuple(sorted(range(1,81),
             key=lambda n:(-points.get(n,0),-fr[n],-hist[n],n))[:10])
    merge10=ranking(merge)
    mutate10=ranking(mutate)
    norm_merge=max(merge.values(),default=1) or 1
    norm_mut=max(mutate.values(),default=1) or 1
    hybrid=ranking({n:(merge[n]/norm_merge)+(mutate[n]/norm_mut)
                    for n in range(1,81)})
    freq10=tuple(sorted(range(1,81),
                        key=lambda n:(-fr[n],-hist[n],n))[:10])
    seed=int.from_bytes(hashlib.sha256(
        f"{SEED}|{day}|{hour}".encode("ascii")).digest()[:8],"big")
    random10=tuple(sorted(random.Random(seed).sample(range(1,81),10)))
    ticket={"MERGE10":merge10,"MUTATE10":mutate10,
            "HYBRID10":hybrid,"FREQ10":freq10,"RANDOM10":random10}
    if any(len(set(t))!=10 for t in ticket.values()):
        raise AssertionError("Ten UNIQUE numbers per method")
    event_candidates=[{"parent_a":fam_key(a),"parent_b":fam_key(b),
            "union":fam_key(union),"union_size":len(union),
            "first6_parent_a_support":ca,"first6_parent_b_support":cb,
            "first6_union_support":seen,
            "shared_count":shared,
            "frozen_prediction_strength":round(strength,6),
            "expected_next6_meetings":round(6*kprob(len(union)),8)}
            for strength,union,a,b,ca,cb,shared,seen in meeting_predictions]
    return ticket,event_candidates,roots,len(eligible)

def _train_test_split(dates):
    # Chronologically partition complete days; no shuffle and no tuning on holdout.
    cut=len(dates)//2
    return set(dates[:cut]),set(dates[cut:])

def rows_to_dict(rows):return {r["pos"]:canonical(r) for r in rows}
def replay(all_days):
    dates=sorted(all_days)
    if len(dates)<2:raise ValueError("At least 2 full days needed")
    training,testing=_train_test_split(dates)
    draws=[];tickets=[];predictions=[];hourly=[]
    hist=[]
    for day in dates:
        day_rows=rows_to_dict(all_days[day])
        if len(day_rows)!=217 or set(day_rows)!=set(range(1,218)):
            raise ValueError("Day must have exactly 217 draw positions: "+day)
        phase="HOLDOUT" if day in testing else "DEV"
        for block in BLOCKS:
            segment=[day_rows[i] for i in range(block["start"],block["end"]+1)]
            first=segment[:6]
            target=segment[6:12]
            if len(first)!=6 or len(target)!=6:
                raise AssertionError("Each hour requires first6 and next6")
            prefix=hist[-72:]
            ticket,events,roots,eligible=prior_features(first,prefix,day,block["code"])
            hkey=(day,block["code"])
            for method,numbers in ticket.items():
                ticks=frozenset(numbers)
                hits=[len(ticks & dr["nums"]) for dr in target]
                for dr,n in zip(target,hits):
                    draws.append({"day":day,"phase":phase,"hour":block["code"],
                        "target_slot":dr["pos"],"draw_id":dr["id"],"time":dr["time"],
                        "method":method,"hits":n,
                        "selected_numbers":fam_key(numbers),"stake":"SANAL"})
                tickets.append({"day":day,"phase":phase,"hour":block["code"],
                    "method":method,"ticket":fam_key(numbers),
                    "mean_hit_next6":round(avg(hits),6),
                    "total_hits_next6":sum(hits),
                    "best_target_hits":max(hits)})
            for i,e in enumerate(events):
                tup=frozenset(map(int,e["union"].split("-")))
                successes=sum(tup<=dr["nums"] for dr in target)
                predictions.append({"day":day,"phase":phase,
                  "hour":block["code"],"prediction_rank":i+1,
                  "first6_draw_start":first[0]["id"],"first6_draw_end":first[-1]["id"],
                  "target_draw_start":target[0]["id"],"target_draw_end":target[-1]["id"],
                  **e,"actual_next6_meetings":successes,
                  "at_least_one_meeting":int(successes>=1),
                  "fair_prob_at_least_once":round(
                      1-(1-kprob(e["union_size"]))**6,8)})
            hourly.append({"day":day,"phase":phase,"hour":block["code"],
                "first6_start_id":first[0]["id"],"first6_end_id":first[-1]["id"],
                "target_start_id":target[0]["id"],"target_end_id":target[-1]["id"],
                "prior_history_draws":len(prefix),
                "root_families_first6":len(roots),
                "twos_repeating_first6":eligible,
                "meeting_predictions":len(events)})
            # Append actual completed block only AFTER predictions frozen;
            # H00 contains 13 total draws; its extra 13th is prior history for H07.
            hist.extend(segment)
            hist=hist[-72:]
    return {"draws":draws,"tickets":tickets,"predictions":predictions,
            "hours":hourly,"days":len(dates),"dev_days":len(training),
            "test_days":len(testing),"holdout_start":min(testing),
            "last_day":max(dates)}

def avg(seq):return sum(seq)/len(seq) if seq else 0.0

def summarize(res,nboot=N_BOOT):
    r=res["draws"]
    grouped=defaultdict(list)
    byday=defaultdict(lambda:defaultdict(list))
    bykey=defaultdict(dict)
    for x in r:
        grouped[(x["phase"],x["method"])].append(x["hits"])
        byday[(x["phase"],x["day"])][x["method"]].append(x["hits"])
        bykey[(x["day"],x["hour"],x["draw_id"])][x["method"]]=x["hits"]
    comparison=[]
    rng=random.Random(947195)
    for phase in ("DEV","HOLDOUT"):
        phase_days=sorted(d for (p,d) in byday if p==phase)
        dmeans={m:{day:avg(byday[(phase,day)][m])
                   for day in phase_days} for m in METHODS}
        for method in METHODS:
            vals=grouped[(phase,method)]
            d1=[dmeans[method][d]-dmeans["RANDOM10"][d] for d in phase_days]
            d2=[dmeans[method][d]-dmeans["FREQ10"][d] for d in phase_days]
            boot_rand=[];boot_freq=[]
            for i in range(nboot):
                sample=[rng.choice(phase_days) for _ in phase_days]
                boot_rand.append(avg([dmeans[method][d]-dmeans["RANDOM10"][d]
                                      for d in sample]))
                boot_freq.append(avg([dmeans[method][d]-dmeans["FREQ10"][d]
                                     for d in sample]))
            boot_rand.sort();boot_freq.sort()
            p1=int(.025*(nboot-1));p2=int(.975*(nboot-1))
            comparison.append({"phase":phase,"method":method,
                "days":len(phase_days),"target_draws":len(vals),
                "mean_hits":round(avg(vals),6),
                "mean_minus_fair_2_5":round(avg(vals)-2.5,6),
                "versus_random_mean":round(avg(d1),6),
                "vs_random_day_boot95_low":round(boot_rand[p1],6),
                "vs_random_day_boot95_high":round(boot_rand[p2],6),
                "versus_freq_mean":round(avg(d2),6),
                "vs_freq_day_boot95_low":round(boot_freq[p1],6),
                "vs_freq_day_boot95_high":round(boot_freq[p2],6),
                **{f"hit_{k}":sum(x==k for x in vals) for k in range(11)},
                **{f"hit_ge_{k}":sum(x>=k for x in vals) for k in (4,5,6,7,8,9,10)}})
    event_summary=[]
    for phase in ("DEV","HOLDOUT"):
        rows=[x for x in res["predictions"] if x["phase"]==phase]
        for rank in (1,2):
            sel=[x for x in rows if x["prediction_rank"]==rank]
            event_summary.append({"phase":phase,"prediction_rank":rank,
              "candidate_hours":len(sel),"observed_unions":sum(
                  x["actual_next6_meetings"] for x in sel),
              "expected_fair_unions":round(sum(
                  x["expected_next6_meetings"] for x in sel),6),
              "hours_with_one_or_more":sum(x["at_least_one_meeting"] for x in sel),
              "fair_expected_hours_one_or_more":round(sum(
                  x["fair_prob_at_least_once"] for x in sel),6),
              "actual_mean_per_hour":round(avg(
                  [x["actual_next6_meetings"] for x in sel]),6),
              "expected_mean_per_hour":round(avg(
                  [x["expected_next6_meetings"] for x in sel]),6)})
    return comparison,event_summary

def _csv(z,name,rows,columns=()):
    with z.open(name,"w",force_zip64=True) as raw:
        wrapper=io.TextIOWrapper(raw,encoding="utf-8",newline="")
        writer=csv.DictWriter(wrapper,fieldnames=list(rows[0]) if rows else list(columns))
        writer.writeheader()
        if rows:writer.writerows(rows)
        wrapper.flush();wrapper.detach()

def pack(res,comparison,evsummary,issues,malformed,partial):
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        hold=[x for x in comparison if x["phase"]=="HOLDOUT"]
        summary=[
          "V59 — AILE BIRLESIMI VE DONUSUMU: ONCEDEN DONDURULAN 10'LU SANAL TEST",
          f"Tam gun: {res['days']}, gelistirme: {res['dev_days']}, tarihsel tutulan test: {res['test_days']}",
          f"HOLDOUT baslangic: {res['holdout_start']} / son: {res['last_day']}",
          "Her saatin ilk 6 cekilisi girdi, ayni saatin 7–12. cekilisleri hedef.",
          "H00 13 cekilistir; 13. cekilis hedef degil, sonraki saat icin tarihe dahil.",
          "Adaylar hedef cekilislerden bilgi kullanilmadan once sabitlenir.",
          "BIRLESME10: onceki ilk6'da 2+ kez gelen ikili aile eslikcilerinin",
          "birlesimlerinden 10 farkli sayi, en yuksek puanlarla.",
          "DONUSUM10: ortak sayi uzerinden bir rakam degistiren ikili aile",
          "aglarindan puanlanan 10 sayi.",
          "HIBRIT10: bu iki kurali birlikte puanlayan 10 farkli sayi.",
          "SIKLIK10: ilk6 sayi frekansina gore 10 sayi.",
          "RASTGELE10: sabit tarih-saat tohumundan secilen kontrol kuponu.",
          "Rastgele adil 20/80 cekiliste 10 sayi icin beklenen isabet = 2.5.",
          "Fark istatistikleri rastgele/siklik yöntemleriyle ayni cekiliste",
          "ESLI karsilastirma ve gün düzeyinde bootstrap %95 araligi.",
          "Bulusma kontrolu: ilk6'da belirlenen iki 2'li aile TAM birlestiginde",
          "k=3/4 sayi 7–12'de tek 20'li kadroya girdi mi?",
          "Adil RNG beklentisi (20)_k/(80)_k ile ayrica kontrol edilir.",
          "Eski günlere dayanan HOLDOUT kronolojik olarak ayrılmıştır;",
          "bu yeni gelecek günlerde yapılmış gerçek prospektif kör test değildir.",
          "120 hipotezden rastlantisal anlamli sonuclari secmekten kaçınınız.",
          "Raporlar parayla kupon oynamak icin öneri değildir.",
          f"Hatalı/karsilastirilan satir: {len(issues)}; ayrıştırma sorunu: {len(malformed)}, eksik gün: {len(partial)}.",
          "","TARIHSEL SON 36 GUN TEST SONUCLARI"
        ]
        for x in hold:
            summary.append(f"{x['method']}: ortalama={x['mean_hits']:.5f}; "
               f"random fark={x['versus_random_mean']:+.5f}"
               f" [%95 {x['vs_random_day_boot95_low']:+.5f},"
               f" {x['vs_random_day_boot95_high']:+.5f}], "
               f"siklik fark={x['versus_freq_mean']:+.5f}")
        for r in evsummary:
            if r["phase"]=="HOLDOUT":
                summary.append(f"Bulusma adayi {r['prediction_rank']}: "
                  f"gercek={r['observed_unions']}, fair={r['expected_fair_unions']},"
                  f" en az 1 toplam saat={r['hours_with_one_or_more']}")
        z.writestr("00_KISA_KARAR_VE_GUVENLIK.txt","\n".join(summary)+"\n")
        for fname,data in [
          ("01_METOTLAR_VE_KOR_TEST_36_GUN.csv",comparison),
          ("02_BIRLESIM_ONCEDEN_SECILEN_AILE_CIFTLERI.csv",res["predictions"]),
          ("03_BIRLESIM_RNG_BEKLENTI_RAPORU.csv",evsummary),
          ("04_SAAT_SAAT_DONDURULEN_BES_10LU.csv",res["tickets"]),
          ("05_HER_HEDEF_CEKILIS_ISABETLERI.csv",res["draws"]),
          ("06_ILK6_VE_HEDEF7_12_CEKILIS_KIMLIKLERI.csv",res["hours"]),
        ]:_csv(z,fname,data)
        z.writestr("07_KURALLAR_SABIT_VE_KOD_DENETIMI.txt",
          "Aile tanımı: ilk6 icinde en az iki farkli 20 sayilik cekiliste"
          " eksiksiz tekrar eden ortak setler. Kökler maksimaldir.\n"
          "Ikiye iki bulusma adaylari: ilk6'daki en yuksek destekli 16 adet",
          " ikili alt aile arasindan, toplam kumesi 3 veya 4 sayi olan"
          " en guclu 2 benzersiz birleşim saat başına kaydedilir.\n"
          "Bütün puanlama ve sıralama kuralları kodda önceden sabittir.\n"
          "Her saat ilk6 verisi goruldugunde sonraki6 hic okunmadan secilir.\n"
          "Bu geçmişi sıralı kullanan tarihsel holdout testidir,"
          " yeni gerçekleşmiş günleri izlemeden kesin kör test sayilmaz.\n"
          "Hesap: hiper-geometrik adil RNG 10/20/80 ve iki aile birleşimi.\n"
          "Birden fazla test sonucu sırf iyi çıktı diye model seçilirse"
          " çoklu seçilim yanlılığı meydana gelir.\n")
    return bio.getvalue()

def selftest():
    from v45_sinyal_kor_test import SLOTS
    first=[]
    for i in range(6):
        seed=random.Random(4325+i)
        ns=tuple(sorted(seed.sample(range(1,81),20)))
        first.append({"pos":i+1,"id":80000+i,
                      "time":SLOTS[i],"nums":frozenset(ns)})
    past=[]
    a,ev,roots,np=prior_features(first,past,"2026-10-12","H07")
    b,ev2,roots2,np2=prior_features(first,past,"2026-10-12","H07")
    assert a==b and ev==ev2
    assert all(len(set(v))==10 for v in a.values())
    assert len(a)==5
    assert math.isclose(kprob(2),20*19/(80*79))
    assert math.isclose(sum(math.comb(10,k)*math.comb(70,20-k)/math.comb(80,20)
                         for k in range(11)),1)
    assert 0<hyper_tail(6)<hyper_tail(5)<1
    # Changing the entire unseen target never changes first-six selection:
    unseen1=[set(random.Random(134+i).sample(range(1,81),20)) for i in range(6)]
    unseen2=[set(random.Random(414+i).sample(range(1,81),20)) for i in range(6)]
    assert first and unseen1!=unseen2 and a==b
    rng=random.Random(48187)
    days={}
    for d in ("2026-10-09","2026-10-10","2026-10-11","2026-10-12"):
        rs=[]
        for i,t in enumerate(SLOTS):
            rs.append({"pos":i+1,"time":t,"id":70000+i,
                 "nums":tuple(sorted(rng.sample(range(1,81),20)))})
        days[d]=rs
    report=replay(days)
    comps,events=summarize(report,20)
    assert len(comps)==10 and len(events)==4
    assert all(x["target_draws"]==2*18*6 for x in comps)
    packed=pack(report,comps,events,[],[],{})
    with zipfile.ZipFile(io.BytesIO(packed)) as z:
        assert len(z.namelist())==8 and z.read("00_KISA_KARAR_VE_GUVENLIK.txt")
    print("PASS V59: prior-only first6, frozen 10-number family union/mutation, "
          "6 held targets, 36-day chronological holdout, fair RNG, one ZIP")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--output",default="v59_output/V59_AILE_BIRLESIM_DONUSUM_KOR_TEST_TEK_ZIP.zip")
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--bootstrap",type=int,default=N_BOOT)
    args=p.parse_args()
    if args.selftest:selftest();return
    if args.bootstrap<50:raise ValueError("bootstrap >=50 required")
    source,issues,malformed=parse_txt(Path(args.source))
    complete={d:r for d,r in source.items() if len(r)==217
              and {x["pos"] for x in r}==set(range(1,218))}
    partial={d:len(r) for d,r in source.items() if d not in complete}
    out=replay(complete)
    comp,ev=summarize(out,args.bootstrap)
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(pack(out,comp,ev,issues,malformed,partial))
    print(json.dumps({"output":str(path),"days":out["days"],
       "historical_holdout_days":out["test_days"],"holdout_from":out["holdout_start"],
       "hours":len(out["hours"]),"target_draws":len(out["hours"])*6,
       "ticket_methods":len(METHODS),
       "holdout":[{k:v for k,v in row.items() if
                  k in ("method","mean_hits","versus_random_mean",
                        "vs_random_day_boot95_low","vs_random_day_boot95_high",
                        "versus_freq_mean")}
                  for row in comp if row["phase"]=="HOLDOUT"],
       "family_meeting_holdout":[row for row in ev if row["phase"]=="HOLDOUT"]},
       ensure_ascii=False))
if __name__=="__main__":main()
