# -*- coding: utf-8 -*-
"""V30 unit + optional FULL synthetic 72-day audit. No user data required."""
import io
import json
import random
import sys
from datetime import date,timedelta
from zipfile import ZipFile,ZIP_DEFLATED
from v21_aile_yasam_dongusu import clock,group_full_days
from v29_sicaklik_kalis_hedef import generate_rows
from v30_bant_isi_yon import (
    BANDS,DIRECTIONS,METHODS,HOUR_STARTS,
    band_of,direction,six_pattern,band_phase,pressure_snapshots,enrich,
    model_key,fit_first24,lock_choice,frozen_probs,brier,pick_coupons,
    ticket_backtest,rates_table,snapshot_bands,permutation_band_test,
    crossband_lag,run_study
)


def mk(day,pos,nums):
    return {
        "day":day,"pos":pos,"no":int(day.replace("-",""))*1000+pos,
        "nums":tuple(sorted(nums)),
        "dt":day+"T"+clock(pos)[0],
        "mask":sum(1<<(n-1) for n in nums)
    }


assert len(BANDS)==8 and BANDS[0]==(1,10) and BANDS[-1]==(71,80)
assert len(DIRECTIONS)==3 and len(METHODS)==6
assert band_of(1)==0 and band_of(10)==0
assert band_of(11)==1 and band_of(80)==7
assert direction(1)=="Isınıyor" and direction(-1)=="Soğuyor"
assert direction(0)=="Sabit"
assert six_pattern([1,2,2,4,5,4])=="---+++"
assert len(HOUR_STARTS)==18
assert clock(13)[0]=="01:02" and clock(14)[0]=="07:02"

rng=random.Random(86753)
days=["2026-10-01","2026-10-02","2026-10-03","2026-10-04"]
draws=[mk(day,pos,rng.sample(range(1,81),20))
       for day in days for pos in range(1,218)]
phases={days[0]:"Eğitim24",days[1]:"Doğrulama12",
        days[2]:"Sınama36",days[3]:"Sınama36"}
panel=generate_rows(draws,phases)
before=pressure_snapshots(draws,phases)
enrich(panel,before)
assert len(panel)==6+3*18
assert all(len(rows)==80 for d,s,rows in panel)
assert all(len(set(r["Sayı"] for r in rows))==80 for d,s,rows in panel)
for day,start,rows in panel:
    assert [r["Sayı"] for r in rows]==list(range(1,81))
    assert all(r["Bant"]==band_of(r["Sayı"])+1 for r in rows)
    assert all(r["Basınç yönü"] in DIRECTIONS for r in rows)
    assert sum(r["H7-H12 gelen sayı"] for r in rows)==120
    assert all(len(r["Bant İlk6 +/-"])==6 for r in rows)
    assert all(r["Bant İlk6 gelen"]>=0 for r in rows)

first_day,first_start,first=panel[0]
# Perturb only H7..H12, after all H1..H6 features were frozen.
edit=draws[:]
for i,d in enumerate(edit):
    if d["day"]==first_day and first_start+6<=d["pos"]<=first_start+11:
        edit[i]=mk(d["day"],d["pos"],tuple(range(61,81)))
pan2=generate_rows(edit,phases)
enrich(pan2,pressure_snapshots(edit,phases))
same=next(z for d,s,z in pan2 if (d,s)==(first_day,first_start))
for x,y in zip(first,same):
    for k in ("Sayı","Bant","Isı6","Yön","Basınç yönü",
              "Bant İlk6 +/-","Bant İlk6 gelen","İlk6 çıkma"):
        assert x[k]==y[k],(k,x[k],y[k])

fit=fit_first24(panel)
winner,val=lock_choice(panel,fit)
assert winner in METHODS and len(val)==len(METHODS)
for d,s,rows in panel:
    probs=frozen_probs(rows,fit,winner)
    assert len(probs)==80
    assert abs(sum(probs)-20)<1e-5
    assert abs(brier(rows,[.25]*80)-.1875)<1e-10
    for method,nums in pick_coupons(rows,probs,d,s).items():
        assert len(set(nums))==len(nums)==(
            10 if method.endswith("10") else 20)
detail,distribution,ci,bandtest=ticket_backtest(panel,fit,winner)
assert len(detail)==2*18*6
assert len(distribution)==6
assert len(bandtest)==2*18*8
summary=rates_table(panel)
assert sum(row["Hedef hak"] for row in summary)==2*18*80*6
hourly,panel80,groups=snapshot_bands(panel)
assert len(hourly)==(6+3*18)*8
assert sum(sum(v) for v in panel80.values())==2*18*80
per=permutation_band_test(panel80,reps=7)
assert 0<=per[0]["Tek kuyruk Monte Carlo p"]<=1
full,missing=group_full_days(draws)
lag=crossband_lag(full,phases)
assert len(lag)==7*8*8
assert lag[0]["Gecikme çekiliş"]==0
assert lag[-1]["Gecikme çekiliş"]==6
print("V30_SMALL_PASS",len(panel),len(detail),len(hourly),winner,flush=True)


if "--full" in sys.argv:
    rng=random.Random(780512)
    begin=date(2026,1,1)
    lines=[]
    for i in range(72):
        stamp=(begin+timedelta(days=i)).strftime("%d.%m.%Y")
        for pos in range(1,218):
            nums=sorted(rng.sample(range(1,81),20))
            lines.append(
                f"{50000+i*217+pos};{stamp} {clock(pos)[0]};"+
                ",".join(map(str,nums)))
    content="\n".join(lines)
    reports,meta,validation,dist,conf,rates,per=run_study(
        content,band_null_reps=11)
    assert meta["Tam gün"]==72
    assert meta["Sınama hedef çekiliş"]==36*18*6
    assert meta["80 sayı-saat sınama"]==36*18*80
    assert len(reports)==12
    assert len(dist)==6
    assert any(r["Yöntem"]=="Model10" and r["Hedef çekiliş"]==3888
               for r in dist)
    assert any(r["Yöntem"]=="Model20" and r["Hedef çekiliş"]==3888
               for r in dist)
    assert all(r["RNG matematik ortalama"]==(
        2.5 if r["Tahmin sayısı"]==10 else 5.0) for r in dist)
    buf=io.BytesIO()
    with ZipFile(buf,"w",compression=ZIP_DEFLATED) as archive:
        for filename,payload in reports.items():
            archive.writestr(filename,payload)
    with ZipFile(io.BytesIO(buf.getvalue())) as archive:
        assert "00_TEK_RAPOR_OZET.txt" in archive.namelist()
        assert len(archive.namelist())==12
    print("V30_FULL_72_DAYS_SYNTHETIC_PASS",
          json.dumps({"days":72,"testdraws":3888,"model":meta["Seçilen model"],
                      "zipbytes":len(buf.getvalue())},
                     ensure_ascii=False),flush=True)
