# -*- coding: utf-8 -*-
"""V41: no lookahead, stable 20/80 picks, six-seat completeness, frozen test."""
import csv
import io
import json
import math
import zipfile
from v41_derin_yon_gecis_motoru import (study,prepare,PreDraw,Calibrator,
  class_momentum,class_velocity,class_acceleration,ALL_METHODS,SIX,ENSEMBLE,
  FROZEN,CONTROL_RNG,CONTROL_V39,WEIGHTS)


def sequence(day,draws=12,replace=None):
    items=[]
    for i in range(1,draws+1):
        numbers=set(range(1,21)) if i%2 else set(range(21,41))
        if replace==i:numbers=set(range(61,81))
        items.append({"day":day,"pos":i,"no":int(day.replace("-",""))*1000+i,
                      "nums":numbers})
    return items


def csvrows(blob,path):
    with zipfile.ZipFile(io.BytesIO(blob)) as f:
        return list(csv.DictReader(io.StringIO(f.read(path).decode("utf-8-sig")),delimiter=";"))


def check():
    assert len(ALL_METHODS)==9
    assert abs(sum(WEIGHTS)-1)<1e-9
    assert class_momentum("YUKSELIS","YUKSELIS")=="IKI_KEZ_YUKSELIS"
    assert class_momentum("DUSUS","YUKSELIS")=="TERS_DUSUS"
    assert class_momentum("SABIT","YUKSELIS")=="FREN"
    assert class_velocity("SOGUK","SICAK")=="2PLUS"
    assert class_acceleration(-.01,.01)=="TERS"
    assert class_acceleration(.01,.004)=="HIZLANIYOR"
    assert class_acceleration(.003,.01)=="YAVASLIYOR"
    engine=PreDraw()
    engine.append("2026-10-01",1,81001,set(range(1,21)))
    engine.append("2026-10-01",2,81002,set(range(21,41)))
    qs=engine.snapshot("2026-10-01",3)
    derived,slopes=prepare(qs,{}, {},engine.prev)
    assert len(derived)==80 and len(slopes)==80
    assert set(q["havuz"] for q in derived)==set(SIX)
    assert sum(q["hiz"]=="2PLUS" for q in derived)>=0
    fitted=Calibrator()
    p_before=fitted.probabilities(derived)
    assert all(all(x==.25 for x in vals) for vals in p_before.values())
    fitted.observe(derived,set(range(1,21)))
    frozen=fitted.frozen_copy()
    frozen0=frozen.probabilities(derived)
    fitted.observe(derived,set(range(21,41)))
    assert frozen.probabilities(derived)==frozen0
    assert fitted.probabilities(derived)!=frozen0

    data=sequence("2026-10-01",12)
    newdata=sequence("2026-10-01",12,replace=12)
    blob,meta,evaluation,brier,comp,groups=study(data,include_partial=True)
    other,_,_,_,_,_=study(newdata,include_partial=True)
    assert meta["real_draws_seen"]==12
    assert meta["predicted_draws"]==11
    assert meta["number_character_cards"]==11*80
    assert meta["individual_tickets"]==11*len(ALL_METHODS)
    assert len(evaluation)==len(ALL_METHODS)
    assert len(brier)==1 and brier[0]["denenen_cekilis"]==11
    assert abs(brier[0]["rng_brier"]-.1875)<1e-10
    a=csvrows(blob,"02_GERCEK_HEDEF_ONCESI_DONDURULMUS_20_LISTELER.csv")
    b=csvrows(other,"02_GERCEK_HEDEF_ONCESI_DONDURULMUS_20_LISTELER.csv")
    x=[row for row in a if row["sira"]=="12"]
    y=[row for row in b if row["sira"]=="12"]
    assert len(x)==len(y)==9
    assert [(r["motor"],r["secilen_20"]) for r in x]==[
        (r["motor"],r["secilen_20"]) for r in y],"Future draw leaked into frozen prediction"
    for r in a:
        nums={int(z) for z in r["secilen_20"].split(",")}
        true={int(z) for z in r["gercek_20"].split(",")}
        assert len(nums)==len(true)==20
        assert int(r["isabet"])==len(nums&true)
        assert r["onceden_donduruldu"]=="EVET"
    card=csvrows(blob,"01_CEKILIS_ONCESI_80_SAYI_YON_KARTLARI.csv")
    card2=csvrows(other,"01_CEKILIS_ONCESI_80_SAYI_YON_KARTLARI.csv")
    aa=[{k:v for k,v in row.items() if k!="gercek20"} for row in card if row["sira"]=="12"]
    bb=[{k:v for k,v in row.items() if k!="gercek20"} for row in card2 if row["sira"]=="12"]
    assert aa==bb and len(aa)==80
    for i in range(2,13):
        rows=[r for r in card if int(r["sira"])==i]
        assert len(rows)==80 and sum(int(r["gercek20"]) for r in rows)==20
        assert all(sum(r["havuz"]==seat for r in rows)>0 for seat in SIX)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        assert z.testzip() is None and len(z.namelist())==8

    # A two-day split makes the first day exclusively training, the second
    # exclusively holdout; frozen (first day only) scores never update in test.
    both=sequence("2026-10-01",6)+sequence("2026-10-02",6)
    packed,info,evaluations,risks,comparisons,_=study(both,include_partial=True)
    assert info["predicted_draws"]==11 and info["testing_first_day"]=="2026-10-02"
    train=[r for r in evaluations if r["donem"]=="EGITIM"]
    test=[r for r in evaluations if r["donem"]=="TEST"]
    assert len(train)==len(test)==9
    assert train[0]["cekilis"]==5 and test[0]["cekilis"]==6
    assert len(risks)==2
    assert f"TEST__{ENSEMBLE}__eksi__{CONTROL_RNG}" in comparisons
    assert f"TEST__{ENSEMBLE}__eksi__{CONTROL_V39}" in comparisons
    assert f"TEST__{ENSEMBLE}__eksi__{FROZEN}" in comparisons
    print("V41 SYNTHETIC PASS: prior-only direction+acceleration, 80 seats, 9 independent 20 picks, frozen 2-day holdout, no target leakage, ZIP",flush=True)


if __name__=="__main__":
    check()
