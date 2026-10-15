#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V53: SAME DRAW families (2..10) that recur within each 217-slot day's hour.

An "active family" appears together in at least TWO different 20-number
draws in a single hour block; this is not across-draw string similarity.
Exact natural hours: 00:02–01:02 has 13 draws; 07:02–23:57 has 17x12.
For each hour detect NEW, CONTINUING, COMEBACK, FADING, and cross-hour
families. Descriptive only, no prediction of lottery RNG.
"""
from __future__ import annotations
import argparse
import collections
import csv
import io
import itertools
import json
import math
import zipfile
from pathlib import Path

from v52_ayni_cekilis_eslikci_217 import parse_txt

K_SIZES = tuple(range(2, 11))
HOURLY_REPEAT = 2
# Defensive stop on pathological duplicate draws with an explosive 20C10
# candidate space. In real data a ~5-number intersection is typical.
MAX_CANDIDATES_PER_HOUR = 400_000

def hour_blocks():
    buckets=[{"code":"H00","name":"00:02–01:02","start":1,"end":13,"expected":13}]
    for h in range(7,24):
        first=14+(h-7)*12
        buckets.append({"code":f"H{h:02d}","name":f"{h:02d}:02–{h:02d}:57",
                        "start":first,"end":first+11,"expected":12})
    assert len(buckets)==18 and sum(b["expected"] for b in buckets)==217
    return buckets

BLOCKS=hour_blocks()
POSITION_TO_HOUR={i:b["code"] for b in BLOCKS for i in range(b["start"],b["end"]+1)}
NAME_BY_HOUR={b["code"]:b["name"] for b in BLOCKS}

def _mask(nums):
    return sum(1 << (n-1) for n in nums)

def _family_key(numbers):
    return "-".join(map(str,numbers))

def hour_families(draws, k_sizes=K_SIZES):
    """Return exact repeated family support; only count same-20-number-draw co-occurrence.

    Pair intersections generate ALL candidates that are in >=2 distinct draws.
    Validate by actual appearances in the hour, not intersection multiplicity.
    """
    masks=[_mask(r["nums"]) for r in draws]
    candidate=collections.defaultdict(set)
    complete=True
    for i in range(len(draws)):
        for j in range(i+1,len(draws)):
            shared=tuple(x for x in draws[i]["nums"] if masks[j] & (1 << (x-1)))
            for k in k_sizes:
                if len(shared)<k:
                    continue
                remaining=MAX_CANDIDATES_PER_HOUR-sum(len(s) for s in candidate.values())
                if remaining<=0:
                    complete=False
                    break
                bucket=candidate[k]
                for fam in itertools.combinations(shared,k):
                    bucket.add(fam)
                    if sum(len(s) for s in candidate.values())>MAX_CANDIDATES_PER_HOUR:
                        complete=False
                        break
                if not complete:
                    break
            if not complete:
                break
        if not complete:
            break
    result=collections.defaultdict(dict)
    for k,all_fams in candidate.items():
        for family in all_fams:
            fm=_mask(family)
            support=sum(1 for m in masks if m&fm==fm)
            if support>=HOURLY_REPEAT:
                result[k][family]=support
    return result,complete

def hour_entries(rows):
    bypos={r["pos"]:r for r in rows}
    return [(b,[bypos[i] for i in range(b["start"],b["end"]+1) if i in bypos])
            for b in BLOCKS]

def analyze_day(rows, day=None, all_sizes=K_SIZES):
    """Fully factual selected-day transitions; missing slots never fabricated."""
    day=day or (rows[0]["day"] if rows else "unknown")
    histories=collections.defaultdict(list)
    summaries,activity,top_rows,fade_rows,blocks_metrics=[],[],[],[],[]
    last=collections.defaultdict(dict)
    seen_any=collections.defaultdict(set)
    completeness={}
    for b,subset in hour_entries(rows):
        detected,complete=hour_families(subset,all_sizes)
        if not complete:
            completeness[b["code"]]=False
        metrics={"hour":b["code"],"hours":b["name"],"slots":len(subset),
                 "expected":b["expected"],"complete":len(subset)==b["expected"],
                 "candidate_complete":complete}
        blocks_metrics.append(metrics)
        for k in all_sizes:
            now=detected.get(k,{})
            prior=last.get(k,{})
            existing=seen_any[k]
            fresh,continued,returned=0,0,0
            for family,count in sorted(now.items(),key=lambda kv:(-kv[1],kv[0])):
                status=("DEVAM" if family in prior else
                        "GERI_GELDI" if family in existing else "YENI")
                if status=="DEVAM":continued+=1
                elif status=="GERI_GELDI":returned+=1
                else:fresh+=1
                histories[(k,family)].append((b["code"],count,status))
                activity.append({"day":day,"hour":b["code"],"hour_time":b["name"],
                                 "draws":len(subset),"k":k,"family":_family_key(family),
                                 "together":count,"status":status})
            for family,old in sorted(prior.items()):
                if family not in now:
                    mask=_mask(family)
                    actual=sum(1 for r in subset if _mask(r["nums"]) & mask == mask)
                    fade_rows.append({"day":day,"hour":b["code"],"k":k,
                                      "family":_family_key(family),"previous":old,
                                      "current":actual,"status":"SONDU"})
            seen_any[k].update(now)
            bysize=sorted(now.items(),key=lambda kv:(-kv[1],kv[0]))
            best=bysize[0] if bysize else ((),"")
            summaries.append({"day":day,"hour":b["code"],"time":b["name"],
               "draws":len(subset),"expected":b["expected"],
               "complete":int(len(subset)==b["expected"]),
               "exact":int(complete),"size":k,
               "active_families":len(now),"new":fresh,
               "continuing":continued,"comeback":returned,
               "faded":len(set(prior)-set(now)),
               "top_family":_family_key(best[0]) if best[0] else "",
               "top_support":best[1]})
            for rank,(family,count) in enumerate(bysize[:5],1):
                top_rows.append({"day":day,"hour":b["code"],"time":b["name"],
                                 "k":k,"rank":rank,"family":_family_key(family),
                                 "support":count,
                                 "percent":round(100*count/len(subset),2) if subset else 0})
            last[k]=now
    # Exact hourly support including inactive zero/single appearances, for only
    # candidate families occurring in >=2 DIFFERENT hours.
    recurring=[]
    for (k,family),changes in histories.items():
        if len(changes)<2:
            continue
        fm=_mask(family)
        timeline=[]
        total=0
        for b,subset in hour_entries(rows):
            times=sum(1 for r in subset if _mask(r["nums"]) & fm==fm)
            timeline.append(f"{b['code']}:{times}")
            total+=times
        recurring.append({"day":day,"size":k,"family":_family_key(family),
            "active_hours":len(changes),"total_day_appearances":total,
            "strongest_hour":max(n for hour,n,status in changes),
            "hourly_path":" | ".join(timeline),
            "statuses":" | ".join(f"{hour}:{status}" for hour,n,status in changes)})
    recurring.sort(key=lambda r:(-r["active_hours"],-r["size"],
                                 -r["total_day_appearances"],r["family"]))
    # Confidence / completeness is fully explicit
    meta={"day":day,"recorded":len(rows),
          "complete_day":len(rows)==217 and {r["pos"] for r in rows}==set(range(1,218)),
          "hours_total":len(BLOCKS),
          "hours_complete":sum(x["complete"] for x in blocks_metrics),
          "truncated_hours":list(completeness),
          "total_active_family_hour_rows":len(activity),
          "cross_hour_repeated_family_count":len(recurring)}
    return {"meta":meta,"hours":blocks_metrics,"overview":summaries,
            "active":activity,"top":top_rows,"faded":fade_rows,"recurring":recurring}

def all_day_hour_summary(days):
    """Compact all-day scan: every hour, K=2..10, only repeated families."""
    for day,rows in sorted(days.items()):
        for b,subset in hour_entries(rows):
            found,complete=hour_families(subset)
            for k in K_SIZES:
                strongest=max(found.get(k,{}).values(),default=0)
                yield (day,b["code"],b["name"],len(subset),b["expected"],
                       int(len(subset)==b["expected"]),k,
                       len(found.get(k,{})),strongest,int(complete))

def _csv_into(z,name,columns,records):
    with z.open(name,"w",force_zip64=True) as buf:
        writerfile=io.TextIOWrapper(buf,encoding="utf-8",newline="")
        writer=csv.writer(writerfile)
        writer.writerow(columns)
        for row in records:
            writer.writerow([row.get(k,"") for k in columns] if isinstance(row,dict) else row)
        writerfile.flush()
        writerfile.detach()

def report_zip(day,days,issues=(),malformed=(),include_all_days=True):
    result=analyze_day(days[day],day)
    m=result["meta"]
    zdata=io.BytesIO()
    with zipfile.ZipFile(zdata,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        lines=[
          "V53 — SAATLIK DEGISEN 2'LI–10'LU AILELER (AYNI 20'LI CEKILIS ICINDE)",
          f"Secilen gün: {day}; toplam çekiliş {m['recorded']}/217; tam saat {m['hours_complete']}/18",
          "Saat başına aile: AYNI 20'li çekilişlerde 2 veya daha fazla kez birlikte görülen belirli sayı kümesi.",
          "H00 = 00:02–01:02 / 13 çekiliş. H07–H23 = saat başına 12 çekiliş.",
          "YENI = gün içinde ilk kez saatlik tekrarlı görülen, DEVAM = önceki saatte de",
          "tekrarlı görülen, GERI_GELDI = daha önce görünmüş, önceki saatte tekrarlı olmayan,",
          "SONDU = önceki saat >=2 görünüm, bu saatte 0 ya da 1 görünüm.",
          f"Aktif aile-saat kaydı: {m['total_active_family_hour_rows']}.",
          f"Birden fazla saatte (her saat >=2) güçlü görülen farklı aile: {m['cross_hour_repeated_family_count']}.",
          f"Bozuk/cakisan kayit {len(issues)}; gecersiz ham satir {len(malformed)}.",
          "5'li–10'lu aileler ancak AYNI saat içinde iki farklı 20'li çekilişte birlikte",
          "tekrar ettiklerinde yazılır; tek çekilişte görülen tüm altküme kombinasyonları basılmaz.",
          "Saat içi yüksek tekrar, rastgele 20/80 çekilişlerinde de oluşabilir.",
          "Bu rapor GECMIS TANIMLAMASIDIR; RNG'yi öngördüğü gösterilmemiştir.",
          "Eksik gün/saat ve işlem limiti bulunan saat varsa raporda görünür.",
          "",
          "SAAT SAAT ÖZET, BOYUTU 6 ve ÜZERİ OLANLAR",
        ]
        for x in result["overview"]:
            if x["size"]>=6:
                lines.append(f"{x['hour']} {x['time']} {x['size']}'li: "
                    f"{x['active_families']} aktif, {x['new']} yeni, "
                    f"{x['continuing']} devam, {x['comeback']} geri geldi, "
                    f"{x['faded']} söndü, lider={x['top_family'] or '-'} "
                    f"({x['top_support'] or 0} kez)")
        z.writestr("00_TEK_SAYFA_SONUC.txt","\n".join(lines)+"\n")
        fields=[
          ("01_18_SAAT_2_10_AILE_HAREKET_OZET.csv",result["overview"],
           ("day","hour","time","draws","expected","complete","exact","size",
            "active_families","new","continuing","comeback","faded",
            "top_family","top_support")),
          ("02_HER_SAAT_AKTIF_AILELER.csv",result["active"],
           ("day","hour","hour_time","draws","k","family","together","status")),
          ("03_SAATLIK_ILK5_AILE.csv",result["top"],
           ("day","hour","time","k","rank","family","support","percent")),
          ("04_SONEN_AILELER.csv",result["faded"],
           ("day","hour","k","family","previous","current","status")),
          ("05_BIRDEN_COK_SAATTE_GORUNENLER.csv",result["recurring"],
           ("day","size","family","active_hours","total_day_appearances",
            "strongest_hour","hourly_path","statuses")),
        ]
        for name,records,cols in fields:
            _csv_into(z,name,cols,records)
        if include_all_days:
            _csv_into(z,"06_TUM_GUNLER_1296_SAAT_2_10_OZET.csv",
               ("day","hour","time","draws","expected","complete","size",
                "active_families","top_support","exact"),
               all_day_hour_summary(days))
        else:
            _csv_into(z,"06_TUM_GUNLER_1296_SAAT_2_10_OZET.csv",
               ("day","hour","time","draws","expected","complete","size",
                "active_families","top_support","exact"),[])
        z.writestr("07_METOD_VE_UYARI.txt",
            "Sadece bir çekilişteki 20 sayı arasında birliktelik kurulur.\n"
            "Aile boyutları 2-10. Bir aile bir saatte ancak iki ayrı çekilişte"
            " tam aile olarak bir araya gelmişse saatlik aktif sayılır.\n"
            "H00 gece 00:02–01:02 13 çekiliş, H07–H23 17 saat x12 çekiliş = 217.\n"
            "01:02–07:02 arasındaki kapanışta sahte saat üretilmez.\n"
            "Eksik saatler varsa sadece var olan kaydedilmiş çekilişler kullanılır.\n"
            "Etiketler sadece saatten saate geri dönük durumdur, gelecek ritim tahmini değildir.\n"
            "Aynı familyanın birçok alt ailesi olabilir; aileler bağımsız rastgele değişkenler değildir.\n"
            "Max aday sınırı aşılırsa exact=0 işaretlenir, o saat tamamlanmış sayılmaz.\n"
            "Bu rapordan kupon avantajı çıkarmak için ileri tarihli, kör ve "
            "rastgele kontrollü ayrıca doğrulama gerekir.\n")
    return zdata.getvalue(),result

def _selftest():
    from v45_sinyal_kor_test import SLOTS
    assert len(BLOCKS)==18 and sum(x["expected"] for x in BLOCKS)==217
    assert BLOCKS[0]["start"]==1 and BLOCKS[0]["end"]==13
    assert BLOCKS[1]["start"]==14 and BLOCKS[-1]["end"]==217
    def r(slot, nums):
        return {"day":"2026-10-12","pos":slot,"time":SLOTS[slot-1],
                "id":40000+slot,"nums":tuple(sorted(nums))}
    a=tuple(range(1,21))
    b=tuple(range(1,11))+tuple(range(21,31))
    c=tuple(range(1,6))+tuple(range(31,46))
    toy=[r(1,a),r(2,b),r(3,c),
         r(14,a),r(15,b),r(16,c),r(27,a),r(28,b)]
    active,exact=hour_families(toy[:3])
    assert exact and active[2][(1,2)]==3
    assert active[3][(1,2,3)]==3
    assert active[6][(1,2,3,4,5,6)]==2
    assert (1,2,3,4,5,6,7,8,9,10) in active[10]
    assert active[10][tuple(range(1,11))]==2
    res=analyze_day(toy)
    assert res["meta"]["hours_total"]==18
    h00=next(x for x in res["overview"] if x["hour"]=="H00" and x["size"]==2)
    h07=next(x for x in res["overview"] if x["hour"]=="H07" and x["size"]==2)
    h08=next(x for x in res["overview"] if x["hour"]=="H08" and x["size"]==2)
    assert h00["new"]>0 and h07["continuing"]>0 and h08["faded"]>0
    assert res["meta"]["cross_hour_repeated_family_count"]>0
    # Only within draw: if 55 appears exclusively in draw #1,
    # and 56 exclusively in draw #2, pair (55,56) must be absent.
    sparse=[r(1,list(range(1,20))+[55]),r(2,list(range(1,20))+[56])]
    fam,complete=hour_families(sparse)
    assert (55,56) not in fam.get(2,{})
    z,out=report_zip("2026-10-12",{"2026-10-12":toy},include_all_days=True)
    with zipfile.ZipFile(io.BytesIO(z)) as arc:
        assert len(arc.namelist())==8
        pairs=list(csv.DictReader(io.StringIO(arc.read("01_18_SAAT_2_10_AILE_HAREKET_OZET.csv").decode())))
        assert len(pairs)==18*9
        assert arc.read("05_BIRDEN_COK_SAATTE_GORUNENLER.csv")
    print("PASS V53: same-draw only, 13+17*12 hours, 2-10 families, NEW/CONTINUING/FADING, ZIP")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--day",default=None)
    p.add_argument("--output-dir",default="v53_artifacts")
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--selected-day-only",action="store_true",
                   help="Skip all-day summary for fast local debugging")
    a=p.parse_args()
    if a.selftest:
        _selftest(); return
    days,issues,malformed=parse_txt(a.source)
    complete=[d for d,rows in days.items() if len(rows)==217
              and {r["pos"] for r in rows}==set(range(1,218))]
    day=a.day or (sorted(complete)[-1] if complete else sorted(days)[-1])
    if day not in days:
        raise ValueError(f"Missing day {day}")
    outfile=Path(a.output_dir)
    outfile.mkdir(parents=True,exist_ok=True)
    blob,result=report_zip(day,days,issues,malformed,
                           include_all_days=not a.selected_day_only)
    location=outfile/f"V53_SAATLIK_2_10_AILELER_{day}_TEK_RAPOR.zip"
    location.write_bytes(blob)
    print(json.dumps({"file":str(location),"meta":result["meta"],
                      "top_6plus":[row for row in result["overview"] if row["size"]>=6
                                   and row["active_families"]>0][:20],
                      "all_day_history":not a.selected_day_only},ensure_ascii=False))
if __name__=="__main__":
    main()
