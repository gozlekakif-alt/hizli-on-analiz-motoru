#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V60: exact ±1,±2 nearest-neighbor movement in 20-of-80 consecutive draws.

Every previous 20-draw defines exclusive categories of NEXT target numbers:
SAME (20), NEAR1 (±1, excluding SAME), NEAR2 (±2 excluding previous groups),
OTHER. Thus all 80 numbers belong to exactly ONE category.

In an independent fair 20/80 draw, expected next hits in ANY fixed pool of
size K is K/4, not a fixed "5 neighbors". Signed ±1,±2 pools and per-band
neighbor pools are analyzed separately and may overlap: label them explicitly.
Only clock-consecutive 5-minute pairs, and true clock-consecutive lags, enter.
No claim about RNG prediction or future lottery performance.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,random,statistics,zipfile
from collections import Counter,defaultdict
from datetime import datetime,timedelta
from pathlib import Path

from v52_ayni_cekilis_eslikci_217 import parse_txt

BAND20=((1,20),(21,40),(41,60),(61,80))
BAND10=tuple((1+10*i,10+10*i) for i in range(8))
LAGS=(1,2,3,6,12)
DIRECTIONS=(("PLUS1",1),("MINUS1",-1),
            ("PLUS2",2),("MINUS2",-2))
BUCKETS=("SAME","NEAR1_EXCLUSIVE","NEAR2_EXCLUSIVE","OTHER")
RNG_N=20
N=80
BOOTSTRAP_DAYS=1800
SEED=601912

def _time(row):
    return datetime.fromisoformat(row["day"]+"T"+row["time"])

def _pool(src,delta,exclude_source=True,within=None):
    result=set()
    for n in src:
        x=n+delta
        if not 1<=x<=80:continue
        if within is not None and not (within[0]<=x<=within[1]):continue
        if exclude_source and x in src:continue
        result.add(x)
    return result

def categories(src):
    source=set(src)
    near1=(_pool(source,+1)|_pool(source,-1))-source
    near2=(_pool(source,+2)|_pool(source,-2))-source-near1
    remaining=set(range(1,81))-source-near1-near2
    pools=dict(zip(BUCKETS,(source,near1,near2,remaining)))
    if sum(map(len,pools.values()))!=80 or set.union(*pools.values())!=set(range(1,81)):
        raise AssertionError("category union must partition 80 numbers")
    if any(pools[a]&pools[b] for i,a in enumerate(BUCKETS)
               for b in BUCKETS[i+1:]):
        raise AssertionError("categories overlap")
    return pools

def classified_pair(prev,nxt,date,lag):
    source=set(prev["nums"]);target=set(nxt["nums"])
    pools=categories(source)
    features=[]
    for kind,nums in pools.items():
        features.append((kind,len(nums),len(nums&target)))
    for name,delta in DIRECTIONS:
        nums=_pool(source,delta)
        features.append((name+"_EXCL_SOURCE",len(nums),len(nums&target)))
    for family,bands in (("BAND20",BAND20),("BAND10",BAND10)):
        for lo,hi in bands:
            origins={n for n in source if lo<=n<=hi}
            neighbors=set().union(*(_pool(origins,delta,within=(lo,hi))
                                    for name,delta in DIRECTIONS))
            # This excludes any previous drawn number from any original band.
            neighbors-=source
            features.append((f"{family}_{lo:02d}_{hi:02d}_NEAR1OR2",
                             len(neighbors),len(neighbors&target)))
            for dist in (1,2):
                pool=set().union(_pool(origins,+dist,within=(lo,hi)),
                                 _pool(origins,-dist,within=(lo,hi)))
                pool-=source
                features.append((f"{family}_{lo:02d}_{hi:02d}_DIST{dist}",
                                 len(pool),len(pool&target)))
    # All neighbor predictions made by each of the previous numbers
    # carry a duplicated origin; union counts each next number only once.
    source_neighbor_20={}
    for lo,hi in BAND20:
        origins=[n for n in source if lo<=n<=hi]
        pool=set()
        for n in origins:
            for step in (-2,-1,1,2):
                if 1<=n+step<=80 and n+step not in source:
                    pool.add(n+step)
        source_neighbor_20[(lo,hi)]=(len(origins),len(pool),len(pool&target))
    return {"day":date,"lag":lag,"source_id":prev["id"],
        "source_clock":prev["time"],"target_id":nxt["id"],
        "target_clock":nxt["time"],
        "source_timestamp":_time(prev).isoformat(timespec="minutes"),
        "target_timestamp":_time(nxt).isoformat(timespec="minutes"),
        "first_second_draw_hours":(prev["time"][:2],nxt["time"][:2]),
        "features":features,"sources20":source_neighbor_20}

def validated(full):
    expected=set(range(1,218))
    for d,rows in full.items():
        if len(rows)!=217 or {r["pos"] for r in rows}!=expected:
            raise ValueError("missing draw of complete day "+d)
    return sorted(({
        "day":day,"pos":r["pos"],"id":r["id"],
        "time":r["time"],"nums":tuple(r["nums"])}
        for day,rows in full.items() for r in rows),key=_time)

def pairs(full,lags=LAGS):
    timeline=validated(full)
    time_index={_time(row):row for row in timeline}
    last=timeline[-1]["day"]
    for prev in timeline:
        # No artificial "next draw" across the 01:02->07:02 sleep gap,
        # skipped dates, or absent times.
        for lag in lags:
            next_clock=_time(prev)+timedelta(minutes=5*lag)
            nxt=time_index.get(next_clock)
            if nxt is None:continue
            yield classified_pair(prev,nxt,prev["day"],lag)

def summarize(records,allow_raw=True):
    measurements=defaultdict(lambda:{"n":0,"pool":0,"hits":0,
                           "fair":0,"residual":0,"day_errors":defaultdict(list)})
    # For lag=1, 20-block source sizes help us compare e.g. exactly
    # 4 observed numbers in 1..20 vs how many neighbors came next.
    group20=defaultdict(lambda:{"trials":0,"pool":0,"hits":0})
    byhour=defaultdict(lambda:{"transitions":0,"one_pool":0,"one_hits":0,
                               "two_pool":0,"two_hits":0})
    bytransition=[];ntrans=Counter()
    for row in records:
        lag=row["lag"];day=row["day"];ntrans[lag]+=1
        groups=dict((k,(sz,hits)) for k,sz,hits in row["features"])
        for key,k,hits in row["features"]:
            metric=measurements[(lag,key)]
            metric["n"]+=1
            metric["pool"]+=k;metric["hits"]+=hits
            metric["fair"]+=k/4
            metric["residual"]+=hits-k/4
            metric["day_errors"][day].append(hits-k/4)
        if lag==1:
            targethour=row["target_clock"][:2]
            h=byhour[targethour];h["transitions"]+=1
            size1,hits1=groups["NEAR1_EXCLUSIVE"]
            size2,hits2=groups["NEAR2_EXCLUSIVE"]
            h["one_pool"]+=size1;h["one_hits"]+=hits1
            h["two_pool"]+=size2;h["two_hits"]+=hits2
            for (lo,hi),(sourcecnt,pool,hits) in row["sources20"].items():
                # specifically conditional on "4 numbers in 1..20" and
                # other observed source-band counts 0..20
                bucket=group20[(lo,hi,sourcecnt)]
                bucket["trials"]+=1;bucket["pool"]+=pool;bucket["hits"]+=hits
            if allow_raw:
                bytransition.append({"day":day,
                  "from_id":row["source_id"],"from_time":row["source_clock"],
                  "to_id":row["target_id"],"to_time":row["target_clock"],
                  "same_pool":groups["SAME"][0],
                  "same_hits":groups["SAME"][1],
                  "pm1_pool":size1,"pm1_hits":hits1,
                  "pm2_pool":size2,"pm2_hits":hits2,
                  "other_pool":groups["OTHER"][0],
                  "other_hits":groups["OTHER"][1],
                  "pm1_fair":round(size1/4,6),
                  "pm2_fair":round(size2/4,6),
                  "pm1_surplus":round(hits1-size1/4,6),
                  "pm2_surplus":round(hits2-size2/4,6)})
    summary=[]
    rng=random.Random(SEED)
    for (lag,key),b in sorted(measurements.items()):
        dayvals={day:sum(vals)/len(vals) for day,vals in b["day_errors"].items()}
        vals=list(dayvals.values())
        if not vals:continue
        observed=sum(vals)/len(vals)
        # Clustering by day preserves dependence of nearby transitions.
        boots=[sum(rng.choice(vals) for _ in vals)/len(vals)
               for i in range(BOOTSTRAP_DAYS)]
        boots.sort()
        summary.append({"lag_draws":lag,"target_minutes":lag*5,
          "metric":key,"transition_count":b["n"],"day_clusters":len(vals),
          "mean_pool":round(b["pool"]/b["n"],6),
          "mean_observed_hits":round(b["hits"]/b["n"],6),
          "mean_rng_expected_hits":round(b["fair"]/b["n"],6),
          "difference_mean":round(b["residual"]/b["n"],6),
          "cluster_boot95_lo":round(boots[round((BOOTSTRAP_DAYS-1)*.025)],6),
          "cluster_boot95_hi":round(boots[round((BOOTSTRAP_DAYS-1)*.975)],6),
          "expected_pool_basis":"pool size / 4",
          "type":"EXCLUSIVE" if key in BUCKETS else "OVERLAPPING_PROBE"})
    size20rows=[]
    for (lo,hi,sources),d in sorted(group20.items()):
        size20rows.append({"source_band":f"{lo}-{hi}",
          "source_count_in_band":sources,"transitions":d["trials"],
          "avg_near_pool":round(d["pool"]/d["trials"],6),
          "avg_neighbors_next":round(d["hits"]/d["trials"],6),
          "fair_expected":round(d["pool"]/d["trials"]/4,6),
          "mean_diff":round((d["hits"]-d["pool"]/4)/d["trials"],6)})
    hourlyrows=[]
    for hour,v in sorted(byhour.items()):
        n=v["transitions"]
        hourlyrows.append({"target_hour":hour,
           "transition_count":n,
           "pm1_pool_avg":round(v["one_pool"]/n,6),
           "pm1_hits_avg":round(v["one_hits"]/n,6),
           "pm1_fair_avg":round(v["one_pool"]/n/4,6),
           "pm2_pool_avg":round(v["two_pool"]/n,6),
           "pm2_hits_avg":round(v["two_hits"]/n,6),
           "pm2_fair_avg":round(v["two_pool"]/n/4,6)})
    return summary,size20rows,hourlyrows,bytransition,ntrans

def _csv(z,name,rows,columns=()):
    with z.open(name,"w",force_zip64=True) as fd:
        text=io.TextIOWrapper(fd,encoding="utf-8",newline="")
        writer=csv.DictWriter(text,fieldnames=list(rows[0]) if rows else list(columns))
        writer.writeheader()
        if rows:writer.writerows(rows)
        text.flush();text.detach()

def pack(full,summary,conditional,hourly,raw,ntrans,issues,malformed,partial):
    out=io.BytesIO()
    category={r["metric"]:r for r in summary if r["lag_draws"]==1}
    lines=["V60 — 20 SAYI × ±1 / ±2 KOMSU HAREKETI",
      f"Tam gun: {len(full)}; gecis lag=1: {ntrans[1]}",
      "1...80 sayilari 4 AYRI ve kapsayici havuza bolunur:",
      "SAME: onceki 20 sayinin aynisi.",
      "NEAR1_EXCLUSIVE: oncekinin ±1'i, eski 20 disinda.",
      "NEAR2_EXCLUSIVE: oncekinin ±2'si, eski 20 ve NEAR1 disinda.",
      "OTHER: bu uc havuzda bulunmayan diger sayilar.",
      "Her sayi bir ve yalniz bir havuzda; tum 80 sayi kapsanir.",
      "Esas kiyas: adil RNG'de herhangi sabit k sayilik havuzdan",
      "yeni 20'li cekiliste ortalama k/4 sayi beklenir.",
      "Bu nedenle 27 sayilik komsu havuzunda 6.75 isabet gorunmesi",
      "tek basina tahmin anlamina GELMEZ.",
      "PLUS1/MINUS1/PLUS2/MINUS2 ayri yonlu havuzlar kesisebilir.",
      "BANT20 ve BANT10: kaynak banttan bant ICI ±1/±2 komsulari,",
      "onceki cikan 20 sayinin tamami dislanir. Bant sinirini",
      "asan komsular bu gruba DAHIL DEGILDIR.",
      "20BANT KOSUL: ilk bandin sayi miktari ornegin 4 ise",
      "komsu havuzu ile sonra gelen gercek komsular ayrica sayilir.",
      "YONLER ve BANT testleri tek coklu deneme ailesidir;",
      "bootstrap belirsizligi tek basina gerçek sinyal kanıtı değildir.",
      "Saat/lag 5,10,15,30,60 dakika; eksik saatler gece 01:02–07:02",
      "ve eksik gunler zaman sirasinda atlanmaz: sadece TAM devam vardir.",
      "Ayni 20'li kadrodaki sayilar arasindaki komsuluk sonraki",
      "cekilisteki komsulukla karistirilmaz.",
      "Gelecekteki cekilis onceden bilinmez; tum testler geriye dönük.",
      "", "LAG=1 ESAS DORT AYRI HAVUZ"
      ]
    for cat in BUCKETS:
        r=category[cat]
        lines.append(f"{cat}: pool={r['mean_pool']:.5f}, "
            f"actual={r['mean_observed_hits']:.5f}, "
            f"fair={r['mean_rng_expected_hits']:.5f}, "
            f"diff={r['difference_mean']:+.5f}, "
            f"day-bootstrap95=[{r['cluster_boot95_lo']:+.5f},"
            f" {r['cluster_boot95_hi']:+.5f}]")
    lines += ["",f"Ham veri uygun olmayan/kayit catismasi {len(issues)}, "
             f"satir ayrıştırma {len(malformed)}, kismi gun {len(partial)}."]
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=5) as z:
        z.writestr("00_KISA_BULGU_VE_RNG_KONTROL.txt","\n".join(lines)+"\n")
        _csv(z,"01_LAG1_2_3_6_12_BUTUN_ORTALAMALAR_CI.csv",summary)
        _csv(z,"02_20LIK_BANT_KAYNAK_0_20_SAYI_KOSULLU.csv",conditional)
        _csv(z,"03_HER_SAATTE_KOMSU_IZI.csv",hourly)
        _csv(z,"04_HER_ARDISIK_CEKILIS_EKSI_AYRI_HAVUZLAR.csv",raw)
        _csv(z,"05_ZAMAN_LAG_TRANSITION_SAYISI.csv",
             [{"lag_draws":lag,"minute_gap":5*lag,"transitions":n}
              for lag,n in sorted(ntrans.items())])
        z.writestr("06_KURALLAR_YORUM_VE_SINIRLAR.txt",
           "BIRLESME kategorileri AYRI; yönlü havuzlar KESISEBILIR.\n"
           "Her 1/80 sayisi onceki hedefe gore es-zamanli bir havuza ayrilir.\n"
           "Kaynak 20 sayi, hedef 20 sayidan daima zamani daha erken olmali.\n"
           "Aynı 5-dakikalık zincir yoksa yanlış sırayla eslestirme yapılmaz.\n"
           "Beklenti tam hiper-geometrik: E[isabet]=K*(20/80)=K/4.\n"
           "Bir sonraki 20'li cekilis su an analiz edilen hedef olduğu"
           " icin bu çalışma gelecek isabet garantisi vermez.\n"
           "Geleceğe yönelik model için önceden sabitlenecek eşik ve"
           " gün bazlı yeni kör test gereklidir.\n")
    return out.getvalue()

def selftest():
    # 1..80 fully partitioned with boundary and overlapping neighbors.
    for src in ({1,2,19,20,79,80}|set(range(30,44)),
                set(range(1,21)),
                set(range(61,81))):
        c=categories(src)
        assert set.union(*c.values())==set(range(1,81))
        assert len(c["SAME"])==20
        assert not c["SAME"]&c["NEAR1_EXCLUSIVE"]
        assert not c["NEAR1_EXCLUSIVE"]&c["NEAR2_EXCLUSIVE"]
    assert not _pool({1},-1) and not _pool({80},+1)
    assert _pool({19},1,within=(1,20))=={20}
    prev={"id":1,"pos":1,"day":"2026-10-12",
        "time":"00:02","nums":tuple(range(1,21))}
    nxt={"id":2,"pos":2,"day":"2026-10-12",
        "time":"00:07","nums":tuple(range(61,81))}
    item=classified_pair(prev,nxt,"2026-10-12",1)
    d=dict((k,(pool,hits)) for k,pool,hits in item["features"])
    assert d["SAME"]==(20,0)
    assert d["NEAR1_EXCLUSIVE"]==(1,0)
    assert d["NEAR2_EXCLUSIVE"]==(1,0)
    assert d["OTHER"]==(58,20)
    day=[]
    from v45_sinyal_kor_test import SLOTS
    rng=random.Random(6119)
    for i,t in enumerate(SLOTS):
        day.append({"day":"2026-10-12","pos":i+1,
           "time":t,"id":62000+i,
           "nums":tuple(sorted(rng.sample(range(1,81),20)))})
    sample=list(pairs({"2026-10-12":day},(1,2)))
    assert len([x for x in sample if x["lag"]==1])==215
    summ,cond,hourly,raw,n=summarize(sample)
    assert n[1]==215 and all(x["transition_count"]==215 for x in summ if x["lag_draws"]==1)
    zipped=pack({"2026-10-12":day},summ,cond,hourly,raw,n,[],[],{})
    with zipfile.ZipFile(io.BytesIO(zipped)) as z:
        assert len(z.namelist())==7
        assert z.read("04_HER_ARDISIK_CEKILIS_EKSI_AYRI_HAVUZLAR.csv")
    print("PASS V60: exact 80 partition, ±1 ±2, band 10/20, "
          "time-consecutive lags, 215 one-day transitions, fair pool baseline, one ZIP")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--output",default="v60_output/V60_KOMSU_1_2_20LI_80LI_TEK_ZIP.zip")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:selftest();return
    days,issues,malformed=parse_txt(Path(a.source))
    full={d:rows for d,rows in days.items() if len(rows)==217
          and {r["pos"] for r in rows}==set(range(1,218))}
    partial={d:len(rows) for d,rows in days.items() if d not in full}
    records=list(pairs(full))
    summary,conditional,hourly,raw,ntrans=summarize(records)
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(pack(full,summary,conditional,hourly,raw,ntrans,
                         issues,malformed,partial))
    basics=[row for row in summary if row["lag_draws"]==1
            and row["metric"] in BUCKETS]
    print(json.dumps({"output":str(out),"complete_days":len(full),
         "lag_counts":dict(ntrans),
         "groups":[{"name":r["metric"],
                    "pool":r["mean_pool"],"observed":r["mean_observed_hits"],
                    "fair":r["mean_rng_expected_hits"],
                    "diff":r["difference_mean"],
                    "CI95":[r["cluster_boot95_lo"],r["cluster_boot95_hi"]]}
                   for r in basics],
         "conditional_first20_src4":[x for x in conditional
               if x["source_band"]=="1-20" and x["source_count_in_band"]==4]},
         ensure_ascii=False))
if __name__=="__main__":main()
