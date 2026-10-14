# -*- coding: utf-8 -*-
"""V42 regression: dynamic 5 H72 cutoffs, strict pre-target, true null odds."""
import csv
import io
import math
import zipfile
from v42_bes_hareketli_havuz_kota import (
    study,histogram72,label,largest_remainder,hypergeom_all_five,
    hypergeom_within1,POOL_NAMES,METHOD_QUOTA,METHOD_TICKET,TOTAL_COMB)


def fake(day,n,alter=None):
    out=[]
    for p in range(1,n+1):
        # includes both repeated exact20 identities and movement by overlap.
        s=set(range(1,21)) if p%4==1 else (
          set(range(21,41)) if p%4==2 else (
          set(range(41,61)) if p%4==3 else set(range(61,81))))
        if p==alter:s=set(range(13,33))
        out.append(dict(day=day,pos=p,
           no=int(day.replace("-",""))*1000+p,nums=s))
    return out


def extract(blob,name):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return list(csv.DictReader(io.StringIO(
            z.read(name).decode("utf-8-sig")),delimiter=";"))


def main():
    assert math.comb(80,20)==TOTAL_COMB
    assert [label(v) for v in (0,14,15,16,17,19,20,21,22,72)]==[
      0,0,1,1,2,2,3,3,4,4]
    hist=[set(range(1,21))]*72
    kinds,sizes=histogram72(hist)
    assert sizes==(60,0,0,0,20)
    assert kinds[0]==4 and kinds[20]==0
    quotas=largest_remainder(sizes,sizes)
    assert quotas==(15,0,0,0,5)
    assert hypergeom_all_five(sizes,quotas)[1]>=0
    assert 0<=hypergeom_within1(20,5)<=1
    cases=[(13,17,22,16,12),(60,0,0,0,20),(0,0,80,0,0)]
    for cap in cases:
        q=largest_remainder(cap,cap)
        exact,joint=hypergeom_all_five(cap,q)
        assert 0<=exact<=joint<=1
        assert sum(q)==20 and all(i<=n for i,n in zip(q,cap))
    # One test day has 90 targets; only targets >= t=73 carry
    # strictly previous 72 snapshot.
    d1=fake("2026-10-01",90)
    d2=fake("2026-10-02",90)
    raw,meta,sumry,ids,formations=study(d1+d2,include_partial=True)
    assert meta["analyzed_days"]==2 and meta["evaluated_targets"]==108
    assert meta["all_real_draws"]==180
    assert len(sumry)==8 # 2 phases x 2 windows x 2 quota models
    assert len(ids)==12 # 2 phases x 2 windows x 3 ticket models
    assert meta["testing_first_day"]=="2026-10-02"
    assert meta["full20_identity_duplicate_audit"]["exact_20_sets_repeated_pairs"]>0
    name="01_CEKILIS_ONCESI_BES_HAVUZ_KOTA.csv"
    rows=extract(raw,name)
    assert len(rows)==108*2
    trows=extract(raw,"03_KOTADAN_20_SAYI_KIMLIGI_ISABET.csv")
    assert len(trows)==108*3
    for k,group in groupbydraw(rows).items():
        assert len(group)==2
        for item in group:
            actual=[int(item["gercek_"+s]) for s in ("soguk","serin","notr","ilik","sicak")]
            pred=[int(item["kota_"+s]) for s in ("soguk","serin","notr","ilik","sicak")]
            size=[int(item["aday_"+s]) for s in ("soguk","serin","notr","ilik","sicak")]
            assert sum(actual)==sum(pred)==20 and sum(size)==80
            assert all(0<=p<=n for p,n in zip(pred,size))
            assert int(item["tum_5_havuz_artieksi1"])==int(
              all(abs(a-b)<=1 for a,b in zip(actual,pred)))
    for item in trows:
        chosen={int(n) for n in item["secilen20"].split(",")}
        truth={int(n) for n in item["gercek20"].split(",")}
        assert len(chosen)==len(truth)==20
        assert int(item["isabet"])==len(chosen&truth)
        assert item["hedef_oncesinde_donduruldu"]=="EVET"
    # Target outcomes must never affect snapshot/quota/ticket for themselves.
    edited=d1+fake("2026-10-02",90,alter=90)
    second,_,_,_,_=study(edited,include_partial=True)
    rerows=extract(second,name)
    aa=[{k:v for k,v in r.items() if not k.startswith("gercek_") and k not in (
      "tam_kota_eslesme","tum_5_havuz_artieksi1","toplam_mutlak_hata",
      "en_buyuk_kota_hatasi","onceki20den_tekrar","onceki60tan_gelen",
      "gercek20_imzasi","gercek_bant8_imzasi")}
      for r in rows if r["gun"]=="2026-10-02" and r["sira"]=="90"]
    bb=[{k:v for k,v in r.items() if not k.startswith("gercek_") and k not in (
      "tam_kota_eslesme","tum_5_havuz_artieksi1","toplam_mutlak_hata",
      "en_buyuk_kota_hatasi","onceki20den_tekrar","onceki60tan_gelen",
      "gercek20_imzasi","gercek_bant8_imzasi")}
      for r in rerows if r["gun"]=="2026-10-02" and r["sira"]=="90"]
    assert aa==bb
    compare=[(r["kimlik_yontemi"],r["secilen20"]) for r in trows
             if r["gun"]=="2026-10-02" and r["sira"]=="90"]
    compare2=[(r["kimlik_yontemi"],r["secilen20"]) for r in extract(
          second,"03_KOTADAN_20_SAYI_KIMLIGI_ISABET.csv")
          if r["gun"]=="2026-10-02" and r["sira"]=="90"]
    assert compare==compare2,"current target leaked into pretarget names"
    assert len(extract(raw,"06_TEKRARLAYAN_HAVUZ_VE_BANT_OLUSUM_IMZALARI.csv"))>0
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert len(z.namelist())==9 and z.testzip() is None
    print("V42 PASS: true dynamic five strata, quota exact/±1, exact hypergeometric null, frozen 20 identities, formation repetition and no target leakage",flush=True)


def groupbydraw(rows):
    result={}
    for item in rows:
        result.setdefault((item["gun"],item["sira"]),[]).append(item)
    return result


if __name__=="__main__":
    main()
