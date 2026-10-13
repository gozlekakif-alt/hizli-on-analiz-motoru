# -*- coding: utf-8 -*-
"""V23: exact FIRST and SECOND appearances of 2..10 size families over 217 draws.

Families are unordered subsets of 20 official published balls (not ball extraction
order). For a day, every family appearing >=2 times is discovered LOSSLESSLY via
pairwise intersections of the 217 draws (v21 engine). 2-appearance mask is
decoded to strictly earliest slot1 and slot2; later positions never redefine
them. Singletons need not be mass-materialized; any individual family can be
queried in <217 checks including whether it has no second appearance.

Timing includes the 01:02->07:02 six-hour no-draw interval. No fake draws.
Observational discoveries after full-day results are NOT prospective predictions.
"""
from __future__ import annotations
import argparse
import csv
import io
import json
import heapq
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from itertools import combinations
from v11_arastirma import read_draws
from v21_aile_yasam_dongusu import (
    SIZES, CORE_SIZES, recurrent_day_families,
    group_full_days, read_catalog, clock, hour_label, key,
    p_family, csv_bytes
)

SOURCE = "veri.txt"
GAP_BUCKETS = ((1,1,"1 çekiliş"),(2,3,"2-3 çekiliş"),
               (4,6,"4-6 çekiliş"),(7,12,"7-12 çekiliş"),
               (13,24,"13-24 çekiliş"),(25,48,"25-48 çekiliş"),
               (49,96,"49-96 çekiliş"),(97,216,"97-216 çekiliş"))


def first_two_positions(bits):
    """Earliest two 1-indexed draw slots without sorting/constructing all hits."""
    if bits.bit_count() < 2:
        raise ValueError("İki tam çıkış yok")
    low = bits & -bits
    rest = bits ^ low
    low2 = rest & -rest
    return low.bit_length(),low2.bit_length()


def third_position(bits):
    low=bits & -bits
    remaining=bits ^ low
    if not remaining: return None
    remaining ^= remaining & -remaining
    if not remaining: return None
    return (remaining & -remaining).bit_length()


def family_mask(family):
    ns=tuple(sorted(int(n) for n in family))
    if not (2<=len(ns)<=10 and len(set(ns))==len(ns) and all(1<=n<=80 for n in ns)):
        raise ValueError("2–10 arasında farklı, 1..80 sayıları")
    return ns,sum(1 << (n-1) for n in ns)


def query_family_day(draws, family):
    """Works for NEVER, once, twice, and 3+ seen subsets; no enumeration."""
    fam,mask=family_mask(family)
    arr=sorted(draws,key=lambda d:d["pos"])
    if len({d["pos"] for d in arr})!=len(arr):
        raise ValueError("Yinelenen sıra")
    found=[r for r in arr if r["mask"] & mask == mask]
    date=arr[0]["day"] if arr else ""
    first=found[0] if len(found)>0 else None
    second=found[1] if len(found)>1 else None
    third=found[2] if len(found)>2 else None
    first_outside=set(first["nums"])-set(fam) if first else set()
    second_outside=set(second["nums"])-set(fam) if second else set()
    both=first_outside & second_outside
    third_outside=set(third["nums"])-set(fam) if third else set()
    return {
        "Tarih":date,"Boyut":len(fam),"Aile":key(fam),
        "Gözlenen çıkış":len(found),
        "İlk çekiliş":first["no"] if first else "",
        "İlk sıra":first["pos"] if first else "",
        "İlk saat":clock(first["pos"])[0] if first else "",
        "İkinci çekiliş":second["no"] if second else "",
        "İkinci sıra":second["pos"] if second else "",
        "İkinci saat":clock(second["pos"])[0] if second else "",
        "İlk→ikinci çekiliş farkı":second["pos"]-first["pos"] if second else "",
        "İlk→ikinci gerçek dakika":
            clock(second["pos"])[1]-clock(first["pos"])[1] if second else "",
        "Üçüncü çekiliş":third["no"] if third else "",
        "Üçüncü sıra":third["pos"] if third else "",
        "Üçüncü saat":clock(third["pos"])[0] if third else "",
        "İlk iki birlikte sabit çevre":key(sorted(both)) if second else "",
        "İlk çevre (çekirdek hariç)":key(sorted(first_outside)) if first else "",
        "İkinci çevre (çekirdek hariç)":key(sorted(second_outside)) if second else "",
        "İki çevredeki farklı sayılar":
            len(first_outside ^ second_outside) if second else "",
        "Üçüncüde ortak çevre sayısı":
            len(third_outside & both) if third else "",
        "Tüm tam görünüş sıraları":",".join(str(x["pos"]) for x in found),
        "Zamanlar":",".join(clock(x["pos"])[0] for x in found),
        "Durum": "Görülmedi" if not first else
                 "Yalnız ilk" if not second else
                 "İlk iki" if not third else "Üç ve üzeri",
    }


def small_row(date,k,fam,bits,draws):
    first,second=first_two_positions(bits)
    third=third_position(bits)
    cm=tuple(draws[first-1]["nums"])
    cn=tuple(draws[second-1]["nums"])
    outside1=set(cm)-set(fam)
    outside2=set(cn)-set(fam)
    shared=outside1 & outside2
    return {
        "Tarih":date,"Boyut":k,"Aile":key(fam),
        "Günlük tam çıkış":bits.bit_count(),
        "İlk çekiliş":draws[first-1]["no"],
        "İlk sıra":first,"İlk saat":clock(first)[0],
        "İkinci çekiliş":draws[second-1]["no"],
        "İkinci sıra":second,"İkinci saat":clock(second)[0],
        "İlk→ikinci çekiliş farkı":second-first,
        "İlk→ikinci gerçek dakika":clock(second)[1]-clock(first)[1],
        "İlk saat dilimi":hour_label(first),
        "İkinci saat dilimi":hour_label(second),
        "Üçüncü sıra":third or "",
        "Üçüncü saat":clock(third)[0] if third else "",
        "İki görünüşte ortak çevre adedi":len(shared),
        "İki görünüşte ortak çevre":key(sorted(shared)),
        "İlk çevre":key(sorted(outside1)),
        "İkinci çevre":key(sorted(outside2)),
        "Değişen çevre sayı adedi":len(outside1 ^ outside2),
        "İlk iki tam çıkışın sırası asla geriye dönük değiştirilmez":True,
    }


def gap_band(gap):
    for lo,hi,label in GAP_BUCKETS:
        if lo<=gap<=hi: return label
    raise ValueError(f"Geçersiz fark {gap}")


def scan_day(date,draws,top=12):
    """One whole day; aggregate EVERY 2+ family, only bounded example records."""
    if len(draws)!=217 or [r["pos"] for r in draws]!=list(range(1,218)):
        raise ValueError("Tam 217 pozisyon olmalı")
    found=recurrent_day_families(draws)
    summary=[];gap_rows=[];transitions=[];examples=[];hourly_rows=[];first_hist=[]
    for k in SIZES:
        families=found[k]
        hist_gap=Counter()
        hist_first=Counter()
        hist_second=Counter()
        hist_pair_hours=Counter()
        over_break=0
        has_third=0
        sum_slot_delta=0
        sum_real_delta=0
        max_repetitions=0
        first_and_second_same_hour=0
        direct_adjacent=0
        for fam,mask in families.items():
            first,second=first_two_positions(mask)
            gap=second-first
            real=clock(second)[1]-clock(first)[1]
            hist_gap[gap]+=1
            hist_first[hour_label(first)]+=1
            hist_second[hour_label(second)]+=1
            hist_pair_hours[(hour_label(first),hour_label(second))]+=1
            over_break+=int(first<=13 and second>=14)
            same=hour_label(first)==hour_label(second)
            first_and_second_same_hour+=int(same)
            direct_adjacent+=int(gap==1)
            has_third+=int(mask.bit_count()>=3)
            sum_slot_delta+=gap;sum_real_delta+=real
            max_repetitions=max(max_repetitions,mask.bit_count())
        n=len(families)
        summary.append({
            "Tarih":date,"Boyut":k,
            "İki ve üzeri çıkmış farklı aile":n,
            "İlk iki aynı saat":first_and_second_same_hour,
            "İlk iki farklı saat":n-first_and_second_same_hour,
            "İlk→ikinci yan yana çekiliş":direct_adjacent,
            "İlk→ikinci gece/sabah boşluğu geçen":over_break,
            "İlk ikiden sonra üçüncü tam çıkış":has_third,
            "Üçüncü tam çıkış oranı":
                round(has_third/n,6) if n else 0,
            "İlk→ikinci ortalama çekiliş farkı":
                round(sum_slot_delta/n,3) if n else "",
            "İlk→ikinci ortalama gerçek dakika":
                round(sum_real_delta/n,3) if n else "",
            "Gün içinde bir ailenin en fazla tam çıkışı":max_repetitions,
            "Önemli not":"2+ tam görünümlü tüm aileler eksiksizdir; bir kez çıkanlar burada listelenmez",
        })
        for gap,v in sorted(hist_gap.items()):
            gap_rows.append({"Tarih":date,"Boyut":k,"Çekiliş farkı":gap,
                             "Gerçek saat/dakika farkı tek değildir":
                             "gece boşluğu geçilirse 360 dakika eklenir",
                             "İlk ikiye sahip aile sayısı":v})
        for h in sorted(set(hist_first)|set(hist_second)):
            hourly_rows.append({"Tarih":date,"Boyut":k,"Saat dilimi":h,
                                "İlk çıkış bu saatte":hist_first[h],
                                "İkinci çıkış bu saatte":hist_second[h]})
        for (h1,h2),c in sorted(hist_pair_hours.items()):
            transitions.append({"Tarih":date,"Boyut":k,
                                "Birinci çıkış saati":h1,
                                "İkinci çıkış saati":h2,
                                "Tekrarlanan aile":c})
        # best by repeat count; early second; late second; largest gap.
        if n:
            by_repeat=heapq.nsmallest(top,families.items(),
                                  key=lambda fm:(-fm[1].bit_count(), fm[0]))
            earliest=heapq.nsmallest(top,families.items(),
                                 key=lambda fm:(first_two_positions(fm[1])[1],fm[0]))
            farthest=heapq.nsmallest(top,families.items(),
                                 key=lambda fm:(-(first_two_positions(fm[1])[1]
                                                -first_two_positions(fm[1])[0]),fm[0]))
            seen=set()
            for group,selected in (
                ("Günlük en çok tam görünüş",by_repeat),
                ("En erken ikinci tam çıkış",earliest),
                ("İlk ikinci arası en uzun çekiliş farkı",farthest),
            ):
                for fam,bits in selected:
                    if fam in seen: continue
                    seen.add(fam)
                    examples.append({"Seçim türü":group,**small_row(date,k,fam,bits,draws)})
        del found[k]
    return summary,gap_rows,hourly_rows,transitions,examples


def scan_catalog(full_days,catalog):
    """ALL 1,131 catalog families tested for 1st/2nd every day incl. zero/once."""
    rows=[];globalrows=[]
    for label,(k,fam,mask) in sorted(catalog.items()):
        appearances=[]
        ever_days=0
        repeat_days=0
        for date,day in full_days:
            hits=[r for r in day if r["mask"]&mask==mask]
            if hits:ever_days+=1
            if len(hits)>=2:repeat_days+=1
            appearances.extend(hits)
            first=hits[0] if hits else None
            second=hits[1] if len(hits)>=2 else None
            third=hits[2] if len(hits)>=3 else None
            if first:
                outside1=set(first["nums"])-set(fam)
                outside2=set(second["nums"])-set(fam) if second else set()
                rows.append({
                    "Tarih":date,"Boyut":k,"Aile":label,
                    "Tam çıkış":len(hits),
                    "İlk çekiliş":first["no"],"İlk sıra":first["pos"],
                    "İlk saat":clock(first["pos"])[0],
                    "İkinci çekiliş":second["no"] if second else "",
                    "İkinci sıra":second["pos"] if second else "",
                    "İkinci saat":clock(second["pos"])[0] if second else "",
                    "İlk→ikinci çekiliş farkı":
                        second["pos"]-first["pos"] if second else "",
                    "İlk→ikinci gerçek dakika":
                        clock(second["pos"])[1]-clock(first["pos"])[1] if second else "",
                    "Üçüncü çekiliş":third["no"] if third else "",
                    "Üçüncü sıra":third["pos"] if third else "",
                    "Üçüncü saat":clock(third["pos"])[0] if third else "",
                    "İlk iki ortak çevre":
                        key(sorted(outside1&outside2)) if second else "",
                    "İlk iki değişen çevre":
                        len(outside1^outside2) if second else "",
                    "Günlük tüm çıkışlar":",".join(str(x["pos"]) for x in hits),
                })
        first,second=(appearances+[None,None])[:2]
        if first:
            first_minutes=int(first["day"].replace("-","")) # not for time math
            # chronological across calendar days, six-hour gap factored into datetimes.
            from datetime import datetime
            delta=(datetime.fromisoformat(second["dt"])
                   -datetime.fromisoformat(first["dt"])).total_seconds()/60 if second else None
            globalrows.append({
                "Aile":label,"Boyut":k,"72 günlük tam çıkış":len(appearances),
                "Göründüğü farklı gün":ever_days,
                "Aynı günde en az 2 görünüş":repeat_days,
                "72 gün ilk gün":first["day"],
                "72 gün ilk saat":clock(first["pos"])[0],
                "72 gün ilk çekiliş":first["no"],
                "72 gün ikinci gün":second["day"] if second else "",
                "72 gün ikinci saat":clock(second["pos"])[0] if second else "",
                "72 gün ikinci çekiliş":second["no"] if second else "",
                "İlk iki arası gerçek dakika":int(delta) if delta is not None else "",
                "Seçim yanlılığı":"Katalog geçmişten seçilmiş; geleceğin başarısı olarak sunulamaz",
            })
        else:
            globalrows.append({"Aile":label,"Boyut":k,"72 günlük tam çıkış":0,
                               "Göründüğü farklı gün":0,
                               "Aynı günde en az 2 görünüş":0,
                               "Seçim yanlılığı":"Katalog geçmişten seçilmiş"})
    return rows,globalrows


def run(txt,catalogtxt,top=10):
    data,errors=read_draws(txt)
    full,partial=group_full_days(data)
    if not full:raise ValueError("Tam gün yok")
    catalog=read_catalog(catalogtxt)
    summaries=[];gaps=[];hours=[];transitions=[];examples=[]
    for date,day in full:
        x=scan_day(date,day,top)
        summaries.extend(x[0]);gaps.extend(x[1])
        hours.extend(x[2]);transitions.extend(x[3]);examples.extend(x[4])
        print("V23_DAY",date,"217",sum(r["İki ve üzeri çıkmış farklı aile"] for r in x[0]),
              flush=True)
    catdays,catglobal=scan_catalog(full,catalog)
    meta={
        "Program":"V23 — ailelerin tam gün ilk ve ikinci tam görünüşleri",
        "Kaynak":"GitHub veri.txt",
        "Tam gün":len(full),"Başlangıç":full[0][0],"Bitiş":full[-1][0],
        "Çekiliş":len(full)*217,
        "Boyut":[2,3,4,5,6,7,8,9,10],
        "V10 katalog ailesi":len(catalog),
        "Veride yanlış girilmiş satır":
            [{"satır":lineno,"hata":err} for lineno,err in errors],
        "Tam olmayan günler":[{"tarih":d,"geçerli_çekiliş":n} for d,n in partial],
        "Aile tanımı":"Çekilişte aynı anda bulunan sırasız 2..10 kümesi.",
        "İlk ve ikinci":"O günün 217 çekilişinde en düşük ve ikinci en düşük sıra; sonradan değiştirilemez.",
        "Kapsam":"Gün içinde en az 2 tam çıkışı bulunan bütün aileler, "
                 "ilk/ikinci sayım ve zaman dağılımları EKSİKSİZ.",
        "Tek çıkan aile":"Tek çıkışlı tüm 2..10 aileler saklanmaz; seçilen her aile doğrudan sorgulanır. "
                          "Katalogda ilk çıkışı olan tekler de raporlanır.",
        "İstatistik uyarısı":"Tam gün gözleminden sonra keşfedilen tekrar eden aileler ileriye dönük "
                            "seçilmiş hedef değildir. Çok sayıda iç içe alt aile aynı çekiliş çiftinden türeyebilir.",
        "Süre hesabı":"Sıra farkı sadece gerçek çekilişleri sayar; gerçek dakika farkı 01:02–07:02 boşluğunu içerir.",
    }
    aggregate=[]
    for k in SIZES:
        xx=[r for r in summaries if r["Boyut"]==k]
        aggregate.append({
            "Boyut":k,"72 gün tam tekrar eden aile (gün-aile)":sum(r["İki ve üzeri çıkmış farklı aile"] for r in xx),
            "İlk iki aynı saatte":sum(r["İlk iki aynı saat"] for r in xx),
            "İlk iki farklı saat":sum(r["İlk iki farklı saat"] for r in xx),
            "İlk ikisi bitişik çekilişte":sum(r["İlk→ikinci yan yana çekiliş"] for r in xx),
            "Gece/sabah boşluğu aşan":sum(r["İlk→ikinci gece/sabah boşluğu geçen"] for r in xx),
            "İkinci sonrası üçüncü tam çıkış":sum(r["İlk ikiden sonra üçüncü tam çıkış"] for r in xx),
        })
    meta["Bütün günlerin toplamları"]=aggregate
    parts={
        "ozet.json":json.dumps(meta,ensure_ascii=False,indent=2).encode("utf-8"),
        "72_gun_boyut_ilk_iki_ozeti.csv":csv_bytes(summaries),
        "72_gun_ilk_ikinci_gap_dagilimi.csv":csv_bytes(gaps),
        "72_gun_saat_saat_birinci_ikinci.csv":csv_bytes(hours),
        "72_gun_saatten_saate_aile_gecisleri.csv":csv_bytes(transitions),
        "72_gun_aile_ilk_iki_gercek_ornekler.csv":csv_bytes(examples),
        "1131_katalog_aile_gunluk_ilk_ikinci.csv":csv_bytes(catdays),
        "1131_katalog_aile_72_gun_ilk_ikinci.csv":csv_bytes(catglobal),
        "tum_boyutlar_toplam.csv":csv_bytes(aggregate),
    }
    return parts,meta


def write_zip(path,parts):
    with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,blob in parts.items():z.writestr(p,blob)


def main():
    ap=argparse.ArgumentParser(description="V23 217 çekilişte 2–10 ailelerin ilk iki görülüşü")
    ap.add_argument("--data",default="veri.txt")
    ap.add_argument("--catalog",default="v10_aileler.csv")
    ap.add_argument("--output",default="V23_72_GUN_AILELER_ILK_IKI_TAM_ANALIZ.zip")
    ap.add_argument("--top",type=int,default=10)
    args=ap.parse_args()
    parts,meta=run(Path(args.data).read_text(encoding="utf-8-sig"),
                   Path(args.catalog).read_text(encoding="utf-8-sig"),args.top)
    write_zip(args.output,parts)
    print("V23_SUCCESS",meta["Tam gün"],meta["Çekiliş"],
          json.dumps(meta["Bütün günlerin toplamları"],ensure_ascii=False),flush=True)
    print("V23_ZIP",args.output,flush=True)


if __name__=="__main__": main()
