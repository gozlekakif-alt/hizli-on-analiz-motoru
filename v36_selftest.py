# -*- coding: utf-8 -*-
"""V36: test two independent 20-number streams, 80-ball reservoirs, online learning."""
from __future__ import annotations
import csv
import io
import json
import sys
import zipfile
from pathlib import Path
from v36_rng_davranis_klonu import (State, Learner, BRANCHES, MOTOR_GROUPS,
                                    run, run_from_txt, weighted20, seed_for)


def draws(n=13,alter_last=False,day="2026-10-01"):
    out=[]
    for p in range(1,n+1):
        rng=list(range(1,21)) if p%2 else list(range(11,31))
        if alter_last and p==n:rng=list(range(61,81))
        out.append({"day":day,"pos":p,"no":100000+p,"nums":rng})
    return out


def rows(blob,filename):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return list(csv.DictReader(io.StringIO(z.read(filename).decode("utf-8-sig")),
                                   delimiter=";"))


def main():
    assert len(BRANCHES)==13
    assert len(MOTOR_GROUPS)==15
    s=State()
    snap,complete=s.advance("2026-10-01",1,set(range(1,21)))
    assert not complete
    assert sum(r["gercek20"] for r in snap.values())==20
    assert sum(r["ISI"]=="SICAK" for r in snap.values())==13
    assert sum(r["ISI"]=="SOGUK" for r in snap.values())==13
    assert all(snap[n]["BEKLEME"]=="1-3" for n in range(21,81))
    assert all(snap[n]["BEKLEME"]=="0" for n in range(1,21))
    for k in range(2,8):s.advance("2026-10-01",k,set(range(1,21)))
    assert s.wait[80]==7
    snap,_=s.advance("2026-10-01",8,set(range(61,81)))
    assert s.wait[80]==0
    assert snap[80]["TEKRAR"]=="ONCEKI20"
    assert snap[80]["ISI"] in ("SOGUK","SOGUGA_YAKIN","ORTA","ILIK","SICAGA_YAKIN","SICAK")
    assert len(weighted20([1.0]*80,__import__("random").Random(123)))==20
    a,meta,daily,cal,motor=run(draws(),include_partial=True)
    b,meta2,_,_,_=run(draws(),include_partial=True)
    assert a==b,"Fixed seed and same source must reproduce same ZIP exactly"
    assert meta["cekilis"]==13 and meta["80_sayi_kaydi"]==1040
    assert meta["online_kalibrasyon_olayi"]==12
    assert len(meta["motor_gruplari"])==15
    assert meta["motor_alt_hazne_sayisi"]>=35
    assert len(motor)>=1 and len(cal)>=1
    with zipfile.ZipFile(io.BytesIO(a)) as z:
        assert z.testzip() is None and len(z.namelist())==11
        assert "02_HER_MOTOR_HAZNE_GIRIS_CIKIS.csv" in z.namelist()
    step=rows(a,"03_HER_CEKILIS_GERCEK_KLON_KARSILASTIRMA.csv")
    assert len(step)==13
    for r in step:
        for k in ("gercek20","klon20","gercek_durum20","rastgele20"):
            vals=[int(n) for n in r[k].split(",")]
            assert len(vals)==20 and len(set(vals))==20 and min(vals)>=1 and max(vals)<=80
        assert 0<=int(r["klon_ortak_sayi"])<=20
    number=rows(a,"01_80_SAYI_HER_ADIM_KARAKTER.csv")
    assert len(number)==1040
    for p in range(1,14):
        block=[r for r in number if int(r["sira"])==p]
        assert len(block)==80 and sum(int(r["gercek20"]) for r in block)==20
        assert sum(int(r["klon20"]) for r in block)==20
    reservoirs=rows(a,"02_HER_MOTOR_HAZNE_GIRIS_CIKIS.csv")
    for p in range(1,14):
        for arm in ("GERCEK","KLON"):
            allrows=[r for r in reservoirs if r["kol"]==arm and int(r["sira"])==p]
            assert sum(int(r["doluluk"]) for r in allrows if r["motor"]=="ISI")==80
            assert sum(int(r["doluluk"]) for r in allrows if r["motor"]=="BANT")==80
            assert sum(int(r["doluluk"]) for r in allrows if r["motor"] in ("HAVUZ20","HAVUZ60"))==80
    # The 13th target changes. The clone samples for that step must be frozen
    # BEFORE the target is disclosed and therefore cannot change.
    modified,_,_,_,_=run(draws(alter_last=True),include_partial=True)
    aa=rows(a,"03_HER_CEKILIS_GERCEK_KLON_KARSILASTIRMA.csv")
    bb=rows(modified,"03_HER_CEKILIS_GERCEK_KLON_KARSILASTIRMA.csv")
    assert aa[-1]["klon20"]==bb[-1]["klon20"]
    assert aa[-1]["gercek_durum20"]==bb[-1]["gercek_durum20"]
    # An unrecorded scheduled draw is not a zero observation.
    gap=draws(6)+[{"day":"2026-10-01","pos":8,"no":100008,
                   "nums":list(range(1,21))}]
    missing,mm,_,_,_=run(gap,include_partial=True)
    mask=rows(missing,"01_80_SAYI_HER_ADIM_KARAKTER.csv")
    assert all(r["bekleme"]=="1" for r in mask if r["sira"]=="8" and int(r["sayi"])>20)
    # Proper scheduled overnight break between position 13 and position 14.
    crossing=draws(14)
    cross,_,_,_,_=run(crossing,include_partial=True)
    cr=rows(cross,"03_HER_CEKILIS_GERCEK_KLON_KARSILASTIRMA.csv")
    assert cr[-1]["saat"]=="07:02" and cr[-1]["kaynak_eksikligi"]=="0"
    print("V36 synthetic: dual 20/60, 15 motor reservoirs, target freeze, missing draw, reproducible ZIP PASS",flush=True)
    if "--full" in sys.argv:
        text=Path("veri.txt").read_text(encoding="utf-8-sig")
        zipped,info,days,cal,mechanics=run_from_txt(text)
        assert info["tam_gun"]>=70
        assert info["cekilis"]==info["tam_gun"]*217
        assert info["80_sayi_kaydi"]==info["cekilis"]*80
        assert len(days)==info["tam_gun"]
        assert info["egitim"]["gercek_cekilis"]>0
        assert info["test"]["gercek_cekilis"]>0
        with zipfile.ZipFile(io.BytesIO(zipped)) as z:
            assert z.testzip() is None and len(z.namelist())==11
        print("V36 REAL DATA PASS:",json.dumps(info,ensure_ascii=False),flush=True)
        print("V36 TEST:",json.dumps(info["test"],ensure_ascii=False),flush=True)


if __name__=="__main__":main()
