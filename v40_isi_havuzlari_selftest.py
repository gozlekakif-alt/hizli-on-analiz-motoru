# -*- coding: utf-8 -*-
"""V40 regression: time-frozen seats, 80/20, no RNG prediction advantage claim."""
import csv
import io
import json
import math
import zipfile
from v40_alti_isi_yon_havuzlari import (PreDraw,study,from_text,SIX,SIZES,
    direction,ENGINE)


def draws(n=24,change=None,day="2026-10-01"):
    result=[]
    for p in range(1,n+1):
        s=set(range(1,21)) if p%3 else set(range(41,61))
        if p==change:s=set(range(61,81))
        result.append({"day":day,"pos":p,"no":81000+p,"nums":s})
    return result


def table(blob,name):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return list(csv.DictReader(io.StringIO(z.read(name).decode("utf-8-sig")),delimiter=";"))


def test():
    assert sum(SIZES)==80 and list(SIZES)==[13,13,14,14,13,13]
    state=PreDraw()
    assert state.snapshot("2026-10-01",1) is None
    state.append("2026-10-01",1,81001,set(range(1,21)))
    snapshot=state.snapshot("2026-10-01",2)
    assert len(snapshot)==80
    assert {x["havuz"] for x in snapshot}==set(SIX)
    assert all(sum(x["havuz"]==seat for x in snapshot)==size
               for seat,size in zip(SIX,SIZES))
    assert all(x["yon"]=="YENI" for x in snapshot)
    frozen=[(x["sayi"],x["havuz"],x["yon"],x["bekleme"]) for x in snapshot]
    # t=2 outcome must never enter pretarget frozen seat.
    second=PreDraw()
    second.append("2026-10-01",1,81001,set(range(1,21)))
    before=[(x["sayi"],x["havuz"],x["yon"],x["bekleme"])
              for x in second.snapshot("2026-10-01",2)]
    assert before==frozen
    state.append("2026-10-01",2,81002,set(range(41,61)))
    third=state.snapshot("2026-10-01",3)
    assert all(x["yon"] in ("YUKSELIS","DUSUS","SABIT") for x in third)
    assert sum(1 for x in third if x["yon"]=="YUKSELIS")>0
    blob,info,evaluations,aggregation=study(draws(),include_partial=True)
    assert info["draws_read"]==24 and info["draws_with_prior_character"]==23
    assert info["number_steps"]==23*80
    assert info["seat_capacity"]==dict(zip(SIX,SIZES))
    assert "test" not in info
    assert len(evaluations)==1 # one synthetic calendar day is test half
    assert evaluations[0]["sayisal_test_firsati"]==23*80
    assert abs(evaluations[0]["rng_25_brier"]-.1875)<1e-7
    assert len([a for a in aggregation if a["boyut"]=="ISI" and
                a["test_donemi"]=="TEST"])==6
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        assert z.testzip() is None and len(z.namelist())==7
        assert "01_80_SAYI_CEKILIS_ONCESI_TUM_KARAKTER.csv" in z.namelist()
    cards=table(blob,"01_80_SAYI_CEKILIS_ONCESI_TUM_KARAKTER.csv")
    assert len(cards)==23*80
    for p in range(2,25):
        group=[r for r in cards if int(r["sira"])==p]
        assert len(group)==80
        assert sum(int(r["isabet"]) for r in group)==20
        assert sum(int(r["hedef20"]) for r in group)==20
        for seat,size in zip(SIX,SIZES):
            assert sum(r["havuz"]==seat for r in group)==size
    details=table(blob,"02_HER_CEKILIS_6_HAVUZ_YON_DAGILIMI.csv")
    for p in range(2,25):
        group=[r for r in details if int(r["sira"])==p]
        assert sum(int(r["havuz_mevcudu"]) for r in group)==80
        assert sum(int(r["havuzdan_hedefe_giren"]) for r in group)==20
    # Different t=24 actual outcomes cannot affect ANY of the pre-t
    # character features OR frozen calibrated probabilities at t=24.
    nextdata=draws(change=24)
    changed,_,_,_=study(nextdata,include_partial=True)
    ca=table(changed,"01_80_SAYI_CEKILIS_ONCESI_TUM_KARAKTER.csv")
    before=[{k:v for k,v in row.items() if k not in ("hedef20","isabet")}
               for row in cards if row["sira"]=="24"]
    after=[{k:v for k,v in row.items() if k not in ("hedef20","isabet")}
               for row in ca if row["sira"]=="24"]
    assert before==after,"target t leaked into pretarget snapshot"
    # Across two complete day boundaries, the thermal memory must persist,
    # but no fabricated overnight missing draws.
    chain=PreDraw()
    chain.append("2026-10-01",13,81013,set(range(1,21)))
    chain.append("2026-10-01",14,81014,set(range(41,61)))
    assert chain.valid_steps==2
    chain.append("2026-10-02",1,81218,set(range(1,21)))
    assert chain.valid_steps==3
    assert chain.snapshot("2026-10-02",2) is not None
    assert chain.snapshot("2026-10-02",2)[0]["son11"]==1
    print("V40 PASS: true pretarget six-seat 80/20, up/down paths, 23*80 audit, no future leakage, overnight no fake draws, ZIP",flush=True)


if __name__=="__main__":
    test()
