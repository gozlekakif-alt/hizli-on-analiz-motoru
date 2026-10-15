#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V58 full data integrity gated report merger; accepts 12 SQLite day shards.
Checks 217 slots, 18 hours, 120 metrics per hour, every day exactly once.
Never produces a success report from partial jobs or missing shards.
"""
from __future__ import annotations
import argparse,csv,io,json,math,sqlite3,zipfile
from collections import Counter,defaultdict
from datetime import date
from pathlib import Path
from v58_family_120_core import GROUPS,METRICS,N_SHARDS,VERSION,FORWARD_DAY
from v52_ayni_cekilis_eslikci_217 import parse_txt

COLS=[x for g,x in METRICS]
LABELS={
"G01_KIMLIK":"Kok aile kimligi ve buyukluk",
"G02_BANT":"Bant, simetri, uzaklik, tek-cift",
"G03_SAAT_ICI":"Saat ici destek, ilk-son cikis, aralik",
"G04_DONUSUM":"Aynen kalma, degisim, buyume, kuculme",
"G05_GUNLER":"Gunler arasi kimlik, ayni saat, donusum",
"G06_AYRILMA":"Parcalanma, ayrilan ve kalan aile sayilari",
"G07_BIRLESME":"Iki veya daha fazla aile bulusmasi",
"G08_AG":"Aile ortak kadro aglari",
"G09_SICAKLIK":"72 cekilis sicaklik profili",
"G10_RITIM":"Saatte ve gunler arasinda gorunum ritmi",
"G11_CEKILIS":"Her 20'li kadronun tekrar ve bant kimligi",
"G12_RNG":"Tam onceki saatlere gore adil RNG beklentisi"}

def _write_csv(z,name,iterable,header):
    with z.open(name,"w",force_zip64=True) as fd:
        tx=io.TextIOWrapper(fd,encoding="utf-8",newline="")
        w=csv.writer(tx)
        w.writerow(header)
        for item in iterable:w.writerow(item)
        tx.flush();tx.detach()

def _source_full(path):
    days,issues,malformed=parse_txt(Path(path))
    full={day:rows for day,rows in days.items() if len(rows)==217
          and {r["pos"] for r in rows}==set(range(1,218))}
    partial={day:len(rows) for day,rows in days.items() if day not in full}
    return full,partial,issues,malformed

def _check(db,expected,shards,all_days):
    c=sqlite3.connect(f"file:{db.as_posix()}?mode=ro",uri=True)
    v=c.execute("SELECT value FROM meta WHERE key='identity'").fetchone()
    if not v or not v[0].startswith(VERSION+":"):
        raise ValueError("missing/version mismatch shard "+str(db))
    # Same exact source identity must be shared by ALL shards.
    if v[0]!=expected:
        raise ValueError("checkpoint dataset hash mismatch: "+str(db))
    dayset={d for d, in c.execute("SELECT day FROM completed")}
    if not dayset.issubset(all_days):raise ValueError("unknown day in "+str(db))
    for day in dayset:
        if c.execute("SELECT count(*) FROM hourly WHERE day=?",(day,)).fetchone()[0]!=18:
            raise ValueError("missing hours for "+day)
        if c.execute("SELECT count(*) FROM metrics WHERE day=?",(day,)).fetchone()[0]!=2160:
            raise ValueError("missing 120 metrics per hour for "+day)
        hours={h for h, in c.execute("SELECT DISTINCT hour FROM metrics WHERE day=?",(day,))}
        if len(hours)!=18:raise ValueError("invalid hour set "+day)
    return c,dayset

def _identity(full):
    import hashlib
    h=hashlib.sha256()
    for d in sorted(full):
        h.update(d.encode())
        for row in full[d]:
            h.update(str(row["id"]).encode())
            h.update(bytes(row["nums"]))
    return VERSION+":"+h.hexdigest()

def merge(sources,source,out,expected_shards=N_SHARDS):
    full,partial,issues,malformed=_source_full(source)
    expected=_identity(full)
    if len(sources)!=expected_shards:
        raise ValueError(f"Expected exactly {expected_shards} shard DBs, got {len(sources)}")
    conns=[];covered=set()
    for db in sorted(sources):
        con,dayset=_check(db,expected,expected_shards,set(full))
        if covered&dayset:
            raise ValueError("duplicate day in distinct shards: "+repr(covered&dayset))
        covered|=dayset;conns.append((db,con,dayset))
    if covered!=set(full):
        raise ValueError("incomplete days in merge: "+repr(sorted(set(full)-covered)))
    # All following input is verified, now stage output.
    arrays={d:{"hour":{},"metrics":defaultdict(dict),"roots":[],"meetings":[],"lineage":[]}
            for d in covered}
    for db,con,days in conns:
        for d,h,payload in con.execute("SELECT day,hour,payload FROM hourly"):
            arrays[d]["hour"][h]=json.loads(payload)
        for d,h,k,v in con.execute("SELECT day,hour,metric,value FROM metrics"):
            arrays[d]["metrics"][h][k]=v
        for t,k in (("roots","roots"),("meeting","meetings"),("lineage","lineage")):
            for d,payload in con.execute(f"SELECT day,payload FROM {t}"):
                arrays[d][k].append(json.loads(payload))
    for _,conn,_ in conns:conn.close()
    names=set(COLS);metadays=0;bad=0
    for d,x in arrays.items():
        if set(x["hour"])!=set(x["metrics"]):raise ValueError("hour alignment "+d)
        for h,vals in x["metrics"].items():
            if set(vals)!=names:
                raise ValueError(f"120 metric key mismatch {d} {h}")
    # Pair appearance counts across ALL real days (not causal links).
    partners=defaultdict(lambda:{"events":0,"days":set(),"first_day":"",
                               "first_draw":0,"first_time":"","overlap":0,
                               "union":"","union_size":0})
    for d in sorted(arrays):
        for item in arrays[d]["meetings"]:
            pair=(item["family_a"],item["family_b"])
            p=partners[pair]
            p["events"]+=1;p["days"].add(d)
            if not p["first_day"]:
                p.update(first_day=d,first_draw=item["draw_id"],
                         first_time=item["time"],overlap=item["shared_count"],
                         union=item["union"],union_size=item["union_size"])
    top=sorted(partners.items(),key=lambda x:(-x[1]["events"],x[0]))
    nullpairs=[]
    for d in sorted(arrays):
        for h,vals in sorted(arrays[d]["metrics"].items()):
            nullpairs.append([d,h,vals["expected_meetings"],
                vals["observed_meetings"],vals["meeting_minus_expected"],
                vals["meeting_over_expected"],vals["expected_disjoint"],
                vals["observed_disjoint"],vals["expected_overlap"],
                vals["observed_overlap"]])
    total_obs=sum(a[3] for a in nullpairs)
    total_exp=sum(a[2] for a in nullpairs)
    total_families=sum(len(x["roots"]) for x in arrays.values())
    total_lineage=sum(len(x["lineage"]) for x in arrays.values())
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_suffix(".incomplete")
    with zipfile.ZipFile(tmp,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        desc=[
            "V58 — 120 SAYISAL AILE ZAMAN ANALIZI — 72 GUN 18 SAAT / GUN",
            f"Tam ve dogrulanmis gun: {len(full)}",
            f"Tam saat: {18*len(full)}",
            f"Gercek hedef cekilis: {217*len(full)}",
            f"120 sayisal metrik: {len(METRICS)}; toplam saat×metrik={18*len(full)*120}",
            f"Kok aile-saat kaydi: {total_families}",
            f"Onceki saatten gelen aile soy/donusum kaydi: {total_lineage}",
            f"Onceki saatlerde sabit aile ciftlerinin ayni hedef 20'lisinde bulusma olayi: {total_obs}",
            f"Adil RNG alt model beklenen bulusma toplam: {total_exp:.4f}",
            f"Farkli bulusan kok aile cifti: {len(partners)}",
            f"Kusurlu ham satir: {len(issues)+len(malformed)}, eksik gun: {len(partial)}",
            f"YENI GUN baslangici: {FORWARD_DAY}; sonrasindaki ilk 14 tam gun ayrica izlenebilir.",
            "",
            "Ilerleme: 12 bagimsiz gun sardi × SQLite/gun atomik kontrol noktasi",
            "Her saat onceki en fazla uc bitmis saat koku ile adaylari dondurur.",
            "Aileler ayni 20'li cekiliste TAM gorunmeden bulusma sayilmaz.",
            "Parcalanma/birlesme mekanik set karsilastirmasi; nedensellik kaniti DEGIL.",
            "Rastgele secimde 20/80 beklenmesi kosullu teorik beklentidir.",
            "Gecmisten gelecegi onerme kaniti yoktur; 120 metrik coklu arama riskini artirir.",
            "ALTAILE/USTAILE kimliklerini ayirmak icin maksimal kok kumesi kullanilir.",
            "Sadece tamamlanmis 217 cekilisli gunler ana tarihe girer.",
            "",
            "METRIK GRUPLARI",
        ]
        for g,metrics in GROUPS:
            desc.append(f"{g}: {LABELS[g]}, {len(metrics)} metrik: "+", ".join(metrics))
        desc.extend(["","EN COK BULUSAN ILK 10 KOK AILE CIFTI"])
        for (a,b),meta in top[:10]:
            desc.append(f"{a} + {b} = {meta['union']} : {meta['events']} "
                 f"gorunum, {len(meta['days'])} gun, ilk #{meta['first_draw']}")
        z.writestr("00_OZET_DURUM_KUTUGU.txt","\n".join(desc)+"\n")
        _write_csv(z,"01_120_METRIK_SOZLUGU.csv",
                   ([f"{i+1:03d}",g,n,LABELS[g]] for i,(g,n) in enumerate(METRICS)),
                   ("id","grup","metrik","grup_aciklamasi"))
        _write_csv(z,"02_SAAT_SAAT_120_METRIK.csv",
            ([d,h]+[round(arrays[d]["metrics"][h][m],7) for m in COLS]
             for d in sorted(arrays) for h in sorted(arrays[d]["metrics"])),
             ("day","hour",*COLS))
        hourfields=("day","hour","time_range","first_draw","last_draw",
          "first_time","last_time","block_start_slot","block_end_slot",
          "prior_hour","elapsed_from_prior_minutes","roots",
          "candidate_roots_frozen","meeting_count","expected_meeting_count","phase")
        _write_csv(z,"03_1296_SAAT_ZAMAN_CIZELGESI.csv",
            ([arrays[d]["hour"][h].get(k,"") for k in hourfields]
             for d in sorted(arrays) for h in sorted(arrays[d]["hour"])),
            hourfields)
        def xrows(key,columns):
            return ([r.get(k,"") for k in columns] for d in sorted(arrays)
                    for r in sorted(arrays[d][key],key=lambda r:(
                       r.get("day",""),r.get("hour",""),
                       r.get("draw_id",0),r.get("family",r.get("source_family","")))))
        _write_csv(z,"04_KOK_AILELER_TUM_SAATLER.csv",xrows("roots",
          ("day","hour","family","k","support","first_draw_id",
           "last_draw_id","first_time","last_time","bands","hot_count","cold_count")),
          ("day","hour","family","k","support","first_draw_id",
           "last_draw_id","first_time","last_time","bands","hot_count","cold_count"))
        lcols=("day","hour","source_hour","source_family","target_family",
          "source_size","target_size","relation","shared_count",
          "possible_split","departed","arrived","gap_minutes",
          "source_exact_in_target_draws")
        _write_csv(z,"05_AILE_SOY_PARÇALANMA_BIRLESME.csv",xrows("lineage",lcols),lcols)
        mcols=("day","hour","draw_id","time","slot","family_a","family_b",
           "shared_count","relation","union_size","union","union_repeats",
           "a_size","b_size","source_hours","fair_prob")
        _write_csv(z,"06_AILE_CIFTLERI_AYNI_CEKILISTE.csv",
                   xrows("meetings",mcols),mcols)
        _write_csv(z,"07_HANGI_AILE_KIMLE_COK_BULUSTU.csv",
           ([a,b,m["events"],len(m["days"]),m["first_day"],m["first_draw"],
             m["first_time"],m["overlap"],m["union"],m["union_size"]]
           for (a,b),m in top),
           ("family_a","family_b","count","different_days","first_day",
            "first_draw","first_time","shared_count","union","union_size"))
        _write_csv(z,"08_ADIL_RNG_SAATLIK_BEKLENTI.csv",nullpairs,
           ("day","hour","expected","actual","diff","ratio",
            "expected_disjoint","actual_disjoint",
            "expected_with_shared_numbers","actual_with_shared_numbers"))
        _write_csv(z,"09_GUN_GUN_72_OZET.csv",
           ([d,len(arrays[d]["hour"]),len(arrays[d]["roots"]),
             len(arrays[d]["lineage"]),len(arrays[d]["meetings"]),
             round(sum(arrays[d]["metrics"][h]["expected_meetings"]
                  for h in arrays[d]["metrics"]),4),
             "ILERIDE_SABIT" if d>=FORWARD_DAY else "GECMIS"]
            for d in sorted(arrays)),
           ("day","hours","root_family_hours","lineages","co_meetings",
             "fair_expected_meetings","phase"))
        _write_csv(z,"10_SQLITE_KONTROL_NOKTASI_KUTUK.csv",
           ([str(db.name),len(days),min(days) if days else "",
             max(days) if days else "",expected]
           for db,con,days in conns),
           ("shard_database","days","first_day","last_day","checksum"))
        z.writestr("11_METOD_KONTROL_VE_LIMITLER.txt",
          "TARAFSIZ KAYIT: V58 aileleri hedef saatten ONCEki 3 bitmis"
          " saatten olusturur. Hedef saatin kendi kökleri SONRADAN kaydedilir.\n"
          "Birlasma=iki onceden tanimlanan ailenin tamamı TEK AYNI cekiliste.\n"
          "Kok aile: kesisimden uretilen maksimal iki-ayri-cekilis ortak kume.\n"
          "Aynı çekilişte uc aile varsa 3 ayrı aile çifti sayılabilir,"
          " bu 3 bağımsız buluşma değildir.\n"
          "Bir saatin araligi H00 00:02-01:02=13, H07..H23 12'ser.\n"
          "Kayıp saat veya eksik gün asla yapay çekilişle tamamlanmaz.\n"
          "Gunlerin ana yuklenmesi farkli GitHub matris islerinde, her gun"
          " tamamlandiktan sonra SQLite ile atomik COMMIT.\n"
          "Yarım gun hatasinda eski gun checkpointleri bozulmaz.\n"
          "Tüm shardlarin kaynak karma değeri ve tüm 120 sütun kontrol"
          " edilmeden ZIP olusturulmaz.\n"
          "Metrikler gözleme dayalıdır. Soy ağacı nedensel aile ilişkisi değildir.\n"
          "20/80 adil RNG için birleşik k kümesinin tek çekilişte görülme"
          " olasiligi (20)_k/(80)_k. Aynı çekilişte çift olayları bağlantılıdır.\n"
          "İstatistiksel bağımsızlık veya tahmin gücü kanıtlanmış değildir.\n")
    tmp.replace(out)
    print(json.dumps({"output":str(out),"validated_days":len(full),
      "hours":len(full)*18,"metrics":len(METRICS),
      "roots":total_families,"lineage":total_lineage,
      "co_meetings":total_obs,"fair_expected":round(total_exp,3),
      "distinct_meeting_pairs":len(partners),
      "top_pairs":[[a,b,m["events"]] for (a,b),m in top[:8]]},
      ensure_ascii=False))
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--sources",default="v58_checkpoints")
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--output",default="v58_output/V58_120_AILE_TAM_ZAMAN_TEK_ZIP.zip")
    p.add_argument("--shards",type=int,default=N_SHARDS)
    a=p.parse_args()
    sources=list(Path(a.sources).rglob("shard_*.sqlite"))
    merge(sources,a.source,a.output,a.shards)
if __name__=="__main__":main()
