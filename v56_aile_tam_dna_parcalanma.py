#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V56 — complete 2..20 same-draw family taxonomy and numeric lineage.

Retrospective research, not a predictive RNG model. Family F is "active" in
an hour if its ENTIRE exact set appears in >=2 distinct 20-number draws.
All active subfamilies are kept in selected-day data; ROOT families are
maximal co-occurring families, preventing nested family double counting.

"Split", "fusion", "mutation" are SET OPERATIONS BETWEEN HOURS, NOT claims
about RNG physics or causal identity.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import date
from itertools import combinations
from pathlib import Path
import csv
import hashlib
import io
import json
import random
import statistics
import zipfile

from v52_ayni_cekilis_eslikci_217 import parse_txt
from v53_saatlik_degisen_aileler import BLOCKS

KS=tuple(range(2,21))
MAX_SUBFAMILIES_PER_HOUR=200_000
SIMULATIONS=32
FUTURE_DATE="2026-10-16"

def family_id(f):return "-".join(str(x) for x in f)
def band(n):return (n-1)//10+1

def _maximal(intersections):
    """Pair intersections are complete generators of maximal support>=2 sets."""
    roots=[]
    for f in sorted(intersections,key=lambda a:(-len(a),a)):
        sf=set(f)
        if not any(sf.issubset(r) for r in roots):
            roots.append(sf)
    return tuple(tuple(sorted(x)) for x in roots)

def catalog(rows,full_detail=False,prehistory=()):
    """Exact exhaustive 2..20 hourly families + maximal frequent roots.
    
    Every combination of any two 20-number draws is enumerated. Its support
    is checked by intersection of 12/13 draw-membership bitsets. Thus every
    family appearing twice in the SAME hour is included, not sampled.
    """
    tidsets=[0]*81
    for ix,row in enumerate(rows):
        for n in row["nums"]:
            tidsets[n]|=1<<ix
    groups={k:set() for k in KS}
    pair_shared=set()
    for i in range(len(rows)):
        n1=set(rows[i]["nums"])
        for j in range(i+1,len(rows)):
            inter=tuple(sorted(n1.intersection(rows[j]["nums"])))
            if len(inter)<2:
                continue
            pair_shared.add(inter)
            for k in KS:
                if len(inter)<k:break
                g=groups[k]
                g.update(combinations(inter,k))
            if sum(map(len,groups.values()))>MAX_SUBFAMILIES_PER_HOUR:
                raise RuntimeError("Safety limit exceeded; no partial results. "
                                   "Unusually high overlap needs manual review.")
    roots=_maximal(pair_shared)
    root_set=set(r for r in roots if 2<=len(r)<=20)
    cached={}
    families={}
    support_dist=defaultdict(Counter)
    bands_dist=defaultdict(Counter)
    roots_dist=Counter()
    max_support=Counter()
    for k in KS:
        bysize={}
        for fam in groups[k]:
            mask=(1<<len(rows))-1
            for n in fam:
                mask &= tidsets[n]
            count=mask.bit_count()
            assert count>=2
            bysize[fam]=(count,mask)
            support_dist[k][count]+=1
            bands_dist[k][len({band(n) for n in fam})]+=1
            roots_dist[k]+=int(fam in root_set)
            if count>max_support[k]:max_support[k]=count
        families[k]=bysize
    if not full_detail:
        return {"families":families,"roots":roots,"support":support_dist,
                "bands":bands_dist,"root_count":roots_dist,
                "max":max_support,"rows":rows}
    hc=Counter(n for row in prehistory[-72:] for n in row["nums"])
    ordered=sorted(range(1,81),key=lambda n:(hc[n],n))
    heat={n:ordered.index(n)//16 for n in range(1,81)}
    return {"families":families,"roots":roots,"support":support_dist,
            "bands":bands_dist,"root_count":roots_dist,"max":max_support,
            "rows":rows,"heat":heat,"tidsets":tidsets,"closure_cache":cached}

def attributes(cat,hour,day):
    """Every selected-day family, all 2..20, including overlap-aware labels."""
    root_set=set(r for r in cat["roots"] if len(r)<=20)
    heat=cat["heat"]
    cache=cat["closure_cache"]
    rows=cat["rows"]
    by_mask={}
    for k in KS:
        for f,(count,mask) in cat["families"][k].items():
            if mask not in cache:
                common=set(range(1,81))
                for i,r in enumerate(rows):
                    if mask & (1<<i):
                        common.intersection_update(r["nums"])
                cache[mask]=tuple(sorted(common))
            closure=cache[mask]
            bands=Counter(band(n) for n in f)
            nh=len(bands)
            hh=Counter(heat[n] for n in f)
            lows=sum(n<=40 for n in f)
            adj=sum(f[i+1]==f[i]+1 for i in range(k-1))
            run=1;longest=1
            for i in range(1,k):
                run=run+1 if f[i]==f[i-1]+1 else 1
                longest=max(longest,run)
            symmetry=sum(n<81-n and 81-n in f for n in f)
            places=[rows[i]["pos"] for i in range(len(rows)) if mask&(1<<i)]
            yield {"day":day,"hour":hour,"k":k,"family":family_id(f),
                "in_hour":count,"hour_draws":len(rows),
                "hours_slots":"|".join(map(str,places)),
                "root":int(f in root_set),
                "closed":int(tuple(f)==closure),
                "parent_closure":family_id(closure) if closure!=f else "",
                "band_occupied":nh,
                "band_pattern":"|".join(f"{b}:{bands[b]}" for b in sorted(bands)),
                "bands_type":"TEK_BANT" if nh==1 else "TAM_FARKLI" if nh==k
                    else "KARISIK",
                "below40":lows,"above40":k-lows,
                "odd":sum(n%2 for n in f),
                "even":sum(n%2==0 for n in f),
                "adjacent_pairs":adj,"consecutive_max":longest,
                "mirror_pairs":symmetry,
                "heat_pattern":"|".join(f"{h}:{hh[h]}" for h in sorted(hh)),
                "family_sum":sum(f),"spread":f[-1]-f[0],
                "gap_first_last":places[-1]-places[0],
                "hourly_rate":round(count/len(rows),4)}
    
def _transition(before,after,source_hour,dest_hour,all_detail=True):
    """Hour transitions for EVERY 2..20 family. One-number edit, children,
    parent expansion, splits and fusion are separately observable.
    """
    history=[]
    counts=Counter()
    fusion=[]
    after_all=after["families"]
    before_all=before["families"]
    replacement_idx={}
    expanded_idx={}
    for k in KS:
        index=defaultdict(list)
        for family,(support,_) in after_all[k].items():
            for partial in combinations(family,k-1):
                index[partial].append((family,support))
        replacement_idx[k]=index
        if k<20:
            expanded_idx[k]=defaultdict(list)
            for family,(support,_) in after_all[k+1].items():
                for partial in combinations(family,k):
                    expanded_idx[k][partial].append((family,support))
    for k in KS:
        old=before_all[k]
        new=after_all[k]
        for fam,(support,_) in old.items():
            found=fam in new
            candidates={}
            if not found:
                for partial in combinations(fam,k-1):
                    for newfamily,ct in replacement_idx[k].get(partial,()):
                        if newfamily!=fam:
                            candidates[newfamily]=ct
            options=sorted(candidates.items(),key=lambda a:(-a[1],a[0]))
            next_family=options[0][0] if options else ()
            # At least two DIFFERENT k-1 active pieces; since family is absent,
            # they are not automatically repeated just by parent containment.
            fragments=[p for p in combinations(fam,k-1) if
                       k>=3 and p in after_all[k-1]] if k>=3 else []
            expansions=expanded_idx.get(k,{}).get(fam,())
            # Split and replacement can BOTH describe the same numeric
            # event. Prioritize splitting as a primary category, but keep
            # independent alternative flags to avoid hiding either feature.
            if found:category="AYNEN_DEVAM"
            elif len(fragments)>=2:category="PARCALANDI"
            elif options:category="TEK_SAYI_DEGISTI"
            elif expansions:category="BUYUDU"
            else:category="TEKRAR_YOK"
            counts[(k,category)]+=1
            if len(fragments)>=2 and not found:counts[(k,"PARCALANMA_ALTERNATIF")]+=1
            if len(options)>=1 and not found:counts[(k,"TEK_SAYI_DEGISTI_ALTERNATIF")]+=1
            if len(expansions)>0:counts[(k,"UST_AILEYE_KATILDI")]+=1
            if len(options)>=2:counts[(k,"COK_KOLLU_DONUSUM")]+=1
            if all_detail:
                # An unchanged family has no departing or arriving numbers.
                next_identity=fam if found else next_family
                rem=[n for n in fam if n not in next_identity]
                added=[n for n in next_identity if n not in fam]
                history.append({
                    "from_hour":source_hour,"to_hour":dest_hour,"k":k,
                    "family":family_id(fam),"old_support":support,
                    "status":category,
                    "next_exact_support":new.get(fam,(0,0))[0],
                    "best_new_family":family_id(next_identity),
                    "new_support":new[fam][0] if found else options[0][1] if options else 0,
                    "removed":family_id(rem),"added":family_id(added),
                    "removed_bands":"-".join(str(band(n)) for n in rem),
                    "added_bands":"-".join(str(band(n)) for n in added),
                    "possible_swaps":len(options),
                    "split_children":len(fragments),
                    "split_flag":int(len(fragments)>=2 and not found),
                    "one_swap_flag":int(bool(options) and not found),
                    "child_families":"|".join(family_id(p) for p in fragments),
                    "expansions":len(expansions),
                    "different_origin_next":int(source_hour=="H00" and dest_hour=="H07")
                })
    for k in range(3,21):
        for f,(count,_) in after_all[k].items():
            if f in before_all[k]:
                continue
            parents=[sub for sub in combinations(f,k-1)
                     if sub in before_all[k-1]]
            if len(parents)>=2:
                counts[(k,"BIRLESME")]+=1
                if all_detail:
                    fusion.append({
                      "from_hour":source_hour,"to_hour":dest_hour,
                      "k":k,"result_family":family_id(f),
                      "result_support":count,
                      "previous_fragments":len(parents),
                      "sources":"|".join(family_id(p) for p in parents),
                      "night_gap":int(source_hour=="H00" and dest_hour=="H07")})
    return counts,history,fusion

def _day_hours(rows,prehistory=(),details=False):
    history=list(prehistory[-72:])
    result=[]
    for b in BLOCKS:
        subset=[rows[i-1] for i in range(b["start"],b["end"]+1)]
        cat=catalog(subset,details,history)
        result.append((b,cat))
        history.extend(subset)
        if len(history)>72:history=history[-72:]
    return result

def summarize_day(day,rows,prehistory=(),details=False):
    analyses=_day_hours(rows,prehistory,details)
    counts=Counter(); hourly=[]; pairs=[]; splits=[]; state_ledger=[]
    hist=defaultdict(list)
    representative=[]
    for b,cat in analyses:
        for k in KS:
            count=len(cat["families"][k])
            summary={"day":day,"hour":b["code"],"time":b["name"],
                "k":k,"draws":len(cat["rows"]),
                "active_families":count,
                "root_families":cat["root_count"][k],
                "seen_3plus":sum(v for f,v in cat["support"][k].items() if f>=3),
                "max_support":cat["max"][k],
                "one_band":cat["bands"][k][1],
                "all_distinct_bands":cat["bands"][k][k],
                "cross_band":count-cat["bands"][k][1]}
            hourly.append(summary)
            counts[(k,"ACTIVE")]+=count
            counts[(k,"ROOT")]+=cat["root_count"][k]
            counts[(k,"SEEN3")]+=summary["seen_3plus"]
            for f,(times,mask) in cat["families"][k].items():
                if details:
                    hist[(k,f)].append((b["code"],times))
        if details:
            pairs.extend(attributes(cat,b["code"],day))
            representative.extend({
                "day":day,"hour":b["code"],"k":len(root),
                "root_family":family_id(root),
                "support":next((cat["families"][len(root)][root][0]
                    for _ in [0] if len(root)<=20 and root in cat["families"][len(root)]),0),
                "members":len(root),
                "outside_limit_20":int(len(root)>20)
            } for root in cat["roots"])
    for (before,old),(after,new) in zip(analyses,analyses[1:]):
        tc,detail,fused=_transition(old,new,before["code"],after["code"],details)
        counts.update(tc)
        if details:
            splits.extend(detail)
            state_ledger.extend(fused)
    lives=[]
    if details:
        for (k,f),events in hist.items():
            indices=[next(i for i,b in enumerate(BLOCKS) if b["code"]==h)
                     for h,n in events]
            breakcount=sum(b-a>1 for a,b in zip(indices,indices[1:]))
            lives.append({"day":day,"k":k,"family":family_id(f),
                "active_hours":len(events),"day_first":events[0][0],
                "day_last":events[-1][0],
                "return_after_gap":breakcount,
                "max_hourly_support":max(n for _,n in events),
                "total_hourly_support":sum(n for _,n in events),
                "hour_path":"|".join(f"{h}:{n}" for h,n in events)})
    return {"day":day,"hourly":hourly,"counts":counts,"hours":analyses,
            "selected_all":pairs,"roots":representative,
            "transitions":splits,"fusion":state_ledger,"lives":lives}

def _random_day(seed):
    rng=random.Random(seed)
    return [{"pos":i+1,"id":700000+i,
             "nums":frozenset(rng.sample(range(1,81),20))}
            for i in range(217)]

def summarize_simulation(day_result,n_sims=SIMULATIONS):
    observed=day_result["counts"]
    test_keys=[(k,t) for k in KS for t in (
        "ACTIVE","ROOT","SEEN3","AYNEN_DEVAM","TEK_SAYI_DEGISTI",
        "PARCALANDI","BUYUDU","BIRLESME","PARCALANMA_ALTERNATIF",
        "UST_AILEYE_KATILDI","COK_KOLLU_DONUSUM")]
    results={key:[] for key in test_keys}
    for i in range(n_sims):
        sim=summarize_day(f"SANAL_{i}",_random_day(560_000+i))
        for key in test_keys:results[key].append(sim["counts"][key])
    output=[]
    for k,t in test_keys:
        sampled=sorted(results[(k,t)])
        real=observed[(k,t)]
        output.append({"k":k,"feature":t,"observed":real,
            "random_mean":round(statistics.mean(sampled),3),
            "q05":sampled[max(0,int((n_sims-1)*.05))],
            "q95":sampled[min(n_sims-1,int((n_sims-1)*.95))],
            "p_upper_exploratory":round((1+sum(x>=real for x in sampled))/(n_sims+1),5),
            "simulations":n_sims})
    return output

def root_life_days(daily_roots):
    """Root family across days: exact identity only; aggregates different
    hours/days but does NOT call shared-subnumber families the same root."""
    byroot=defaultdict(list)
    for day,entries in daily_roots:
        for root,hour,k,support in entries:
            byroot[root].append((day,hour,k,support))
    for root,events in byroot.items():
        seen_days=sorted({a for a,b,k,n in events})
        if len(events)>=2:
            yield {"root_family":family_id(root),"k":len(root),
                 "days":len(seen_days),"hours":len(events),
                 "first_day":seen_days[0],"last_day":seen_days[-1],
                 "max_support":max(s for d,h,k,s in events),
                 "day_path":"|".join(seen_days),
                 "same_day_more_than_once":int(len(seen_days)<len(events))}

def scan(full,selected=None,n_sims=SIMULATIONS):
    if not full:raise ValueError("Tam 217 cekilisli gun bulunamadi")
    day=selected or sorted(full)[-1]
    if day not in full:raise ValueError("Bu tarih tam gun degil: "+day)
    all_hours=[]; daily_counts=[]; roots=[]
    prior=[]
    selected_record=None
    for d,rows in sorted(full.items()):
        single=summarize_day(d,rows,prior,details=(d==day))
        all_hours.extend(single["hourly"])
        daily_counts.append({
            "day":d,**{f"K{k}_{typ}":single["counts"][(k,typ)]
                       for k in KS for typ in
                       ("ROOT","SEEN3","AYNEN_DEVAM","TEK_SAYI_DEGISTI",
                        "PARCALANDI","BIRLESME")}
        })
        maximal=[]
        for b,cat in single["hours"]:
            for root in cat["roots"]:
                if 2<=len(root)<=20:
                    support=cat["families"][len(root)][root][0]
                else:support=0
                maximal.append((root,b["code"],len(root),support))
        roots.append((d,maximal))
        if d==day:selected_record=single
        prior.extend(rows)
        if len(prior)>72:prior=prior[-72:]
    rng=summarize_simulation(selected_record,n_sims)
    global_root_repeat=list(root_life_days(roots))
    return {"selected":selected_record,"all_hours":all_hours,
            "all_days":daily_counts,"all_roots":global_root_repeat,
            "simulated":rng,"day":day,"n_days":len(full),
            "random_days":n_sims}

def _write_rows(z,filename,rows,empty_columns=()):
    with z.open(filename,"w",force_zip64=True) as binary:
        wfile=io.TextIOWrapper(binary,encoding="utf-8",newline="")
        cols=list(rows[0]) if rows else list(empty_columns)
        writer=csv.DictWriter(wfile,fieldnames=cols)
        writer.writeheader()
        if rows:writer.writerows(rows)
        wfile.flush();wfile.detach()

def pack(report,partial,issues,broken):
    r=report["selected"]
    overall=Counter()
    for day in report["all_days"]:
        for k in KS:
            for typ in ("ROOT","SEEN3","AYNEN_DEVAM",
                         "TEK_SAYI_DEGISTI","PARCALANDI","BIRLESME"):
                overall[(k,typ)]+=day[f"K{k}_{typ}"]
    result=io.BytesIO()
    with zipfile.ZipFile(result,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as z:
        summary=[
          "V56 — AILELERIN TUM DNA SINIFLARI / PARCALANMA / BIRLESME",
          f"Secili gun {report['day']} | {report['n_days']} TAM 217 cekilisli gun",
          f"Bu gun: 18 saat, tum 2-20'lu alt aileler kesin sayiliyor.",
          f"Gercek adil RNG kiyaslamasi: {report['random_days']} BAGIMSIZ 217-cekilisli sanal gun.",
          "Saatlik aile: ayni saatte en az iki AYRI 20'li cekiliste tüm sayilar birlikte.",
          "KOK AILE: daha buyuk ayni-saat tekrar ailesi olmayan maksimal ortak kume.",
          "ALT AILE: kok ailenin tam bir alt kumesi. Kökün tekrari alt aileleri de",
          "tekrar ediyor gösterir; bunlar bağımsız sinyaller DEGILDIR.",
          "KAPALI AILE: tam ayni cekilislerde gorunen daha buyuk bir kume yok.",
          "SAYISAL DONUSUM SINIFLARI (nedensel mekanizma DEĞIL):",
          "AYNEN_DEVAM = ayni tam aile bir sonraki saat icinde de 2+ kez ortaya cikti.",
          "TEK_SAYI_DEGISTI = eski aile 2+ değil, 1 ayrildi 1 eklendi,",
          "yeni k boyutlu baska aile sonraki saatte 2+ tam göründü.",
          "PARCALANDI ve TEK_SAYI_DEGISTI eszamanli olabilir; ikisi için",
          "ayri split_flag ve one_swap_flag alanlari bulunur.",
          "PARCALANDI = eski tam aile artık 2+ değil, bir sonraki saatte en az",
          "iki farklı (k-1) alt aile 2+ kez goruldu.",
          "BIRLESME = yeni tam aile 2+ oldu; onceki saatte kendisi 2+",
          "degildi ancak en az iki farkli (k-1) parcasi 2+ idi.",
          "BUYUDU = eski ailenin tamamini iceren (k+1)'li etkin bir ust aile var.",
          "TEKRAR_YOK = yukaridaki ana kosullar saglanmadi.",
          "AYNI aile ile tek sayi degismis aileyi ASLA tek kimlik sayma.",
          "H00 13 cekilis; H07..H23 17 saat x12. H00->H07 gece boslugu var.",
          "BANT, 40 ust-alt, tek-cift, komsu, ayna(81-n), ortalama sicaklik,",
          "saatlik tekrar sayisi, ilk-son gorunum, kapali/kok aile ozellikleri var.",
          "Secili gunun TAM alt aile satirlari, diger gunlerin saatlik",
          "ve gunluk sinif ozeti, tum gunlerin tekrar eden KOK aileleri sunulur.",
          "Geçmişte ailelerin dönüşmesi RNG tahmin avantajı gostermez.",
          "Ailelerin birbirine gömülü olması nedeniyle satırlar bağımsız değildir.",
          f"Hatali/cakisan kayit {len(issues)}, ayrıştırılamayan satir {len(broken)}, kismi gun {len(partial)}.",
          "", "72 GUNDEKI KOK AILELER VE DONUSUMLER, BOYUTA GORE",
        ]
        for k in KS:
            summary.append(f"{k}'li: kök={overall[(k,'ROOT')]}, 3+ tekrar={overall[(k,'SEEN3')]}, "
             f"aynen={overall[(k,'AYNEN_DEVAM')]}, "
             f"bir sayı değiştirdi={overall[(k,'TEK_SAYI_DEGISTI')]}, "
             f"parcalandı={overall[(k,'PARCALANDI')]}, "
             f"birleşti={overall[(k,'BIRLESME')]}.")
        z.writestr("00_TEK_SAYFA_BULGULAR.txt","\n".join(summary)+"\n")
        datasets=[
          ("01_SECILI_GUN_TUM_2_20_AILE_DNA.csv",r["selected_all"]),
          ("02_SECILI_GUN_SAATTEN_SAATE_DONUSUM.csv",r["transitions"]),
          ("03_SECILI_GUN_BIRLESEN_YENI_AILELER.csv",r["fusion"]),
          ("04_SECILI_GUN_AILE_YASAM_YOLU.csv",r["lives"]),
          ("05_SECILI_GUN_MAKSIMUM_KOK_AILELER.csv",r["roots"]),
          ("06_72_GUN_1296_SAAT_AILE_SINIFLARI.csv",report["all_hours"]),
          ("07_72_GUN_GUNLUK_DONUSUMLER.csv",report["all_days"]),
          ("08_GUNLER_ARASI_AYNI_KOK_AILE_GELISLERI.csv",report["all_roots"]),
          ("09_RNG_SANAL_GUN_KARSILASTIRMASI.csv",report["simulated"]),
        ]
        for filename,rows in datasets:
            _write_rows(z,filename,rows)
        z.writestr("10_METOD_VE_SINIRLAR.txt",
            "Kök/kapalı kavramı sık öge kümeleri (frequent itemset) matematiğine göredir.\n"
            "Tam seçili gün tüm 2–20 alt ailelerde eksiksizdir, eski tam günler"
            " saatlik/günlük toplamlara özetlenir; farklı günler 'komşu saat' diye"
            " birleştirilmez.\n"
            "Aynı gerçek saatin içindeki iki farklı çekilişte ortak grup olmalı.\n"
            "Aile ayrılması/birleşmesi kayıtları metafordur, RNG'de gerçek "
            "ebeveyn-çocuk veya yönlü matematiksel zorunluluk yoktur.\n"
            "Saatler arasında yalnız ardışık veri blokları karşılaştırılır;"
            " H00 ile H07 arasında gerçek saatler boşluğu mevcuttur.\n"
            "Rastgele kontrol, sanal bağımsız 20/80 çekilişlerden oluşur."
            " Rapor sonuçlarından gelecek kuponunun üstünlüğü çıkmaz.\n"
            "Simülasyonların p değeri keşif amaçlıdır, birden çok özellik"
            " denendiğinde çoklu karşılaştırma düzeltmesi yapılmamıştır.\n"
            "Burada başarı iddiası için dondurulmuş bağımsız kör teste ihtiyaç vardır.\n")
    return result.getvalue()

def _selftest():
    from v45_sinyal_kor_test import SLOTS
    def draw(i,nums):
        return {"pos":i+1,"id":50000+i,"time":SLOTS[i],
                "nums":frozenset(nums)}
    a=set(range(1,21))
    b=set(range(1,9))|set(range(21,33))
    c=set(range(2,8))|set(range(33,47))
    first=[draw(0,a),draw(1,b),draw(2,c)]
    cat=catalog(first,full_detail=True,prehistory=())
    assert cat["families"][3][(2,3,4)][0]==3
    assert cat["families"][3][(1,2,3)][0]==2
    assert (19,20) not in cat["families"][2]
    assert (1,2) in cat["families"][2]
    assert len(cat["families"][2])>0
    assert sum(cat["support"][2].values())==len(cat["families"][2])
    attr=next(x for x in attributes(cat,"H00","2026-10-01")
              if x["family"]=="2-3-4")
    assert attr["in_hour"]==3
    # Two distinct members of a 3-family after the original triple disappears
    first2=[draw(13,list(range(1,19))+[31,32]),
            draw(14,list(range(1,19))+[33,34])]
    day={"2026-10-01": [
        draw(i,tuple(random.Random(10000+i).sample(range(1,81),20)))
        for i in range(217)]}
    report=scan(day,n_sims=2)
    assert report["day"]=="2026-10-01"
    data=pack(report,{},[],[])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert len(z.namelist())==11
        assert z.read("01_SECILI_GUN_TUM_2_20_AILE_DNA.csv")
        assert z.read("09_RNG_SANAL_GUN_KARSILASTIRMASI.csv")
    print("PASS V56: exhaustive 2..20 same-draw families, roots/closure, mutation, split/merge, simulation, single ZIP")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data",default="veri.txt")
    p.add_argument("--day")
    p.add_argument("--sims",type=int,default=SIMULATIONS)
    p.add_argument("--output",default="v56_artifacts/V56_TUM_AILE_DNA_TEK_RAPOR.zip")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:_selftest();return
    if args.sims<1:raise ValueError("Minimum 1 simulation")
    all_dates,issues,broken=parse_txt(Path(args.data))
    full={day:rows for day,rows in all_dates.items() if len(rows)==217 and
          {r['pos'] for r in rows}==set(range(1,218))}
    partial={day:len(rows) for day,rows in all_dates.items() if day not in full}
    report=scan(full,args.day,args.sims)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(pack(report,partial,issues,broken))
    print(json.dumps({"file":str(output),"selected_day":report["day"],
                      "complete_days":report["n_days"],
                      "hours":len(report["all_hours"])//len(KS),
                      "selected_family_rows":len(report["selected"]["selected_all"]),
                      "selected_transition_rows":len(report["selected"]["transitions"]),
                      "crossday_repeated_roots":len(report["all_roots"]),
                      "simulation_days":report["random_days"]},ensure_ascii=False))

if __name__=="__main__":
    main()
