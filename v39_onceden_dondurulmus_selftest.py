# -*- coding: utf-8 -*-
"""V39 causal-order regression: frozen target t unchanged if actual t changes."""
import csv
import io
import json
import math
import zipfile
from v39_onceden_dondurulmus_uzman_paneli import (
  Life,features,stable_rng,select20,MODEL_NAMES,ENSEMBLE,BASELINE,
  audit_v38_zip,study,make_rows,OnlinePanel)


def fake(n=17,replace=None):
    a=[]
    for pos in range(1,n+1):
        vals=set(range(1,21)) if pos%2 else set(range(51,71))
        if replace==pos:vals=set(range(21,41))
        a.append({"day":"2026-10-01","pos":pos,"no":550000+pos,"nums":vals})
    return a


def extract(blob,filename):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return list(csv.DictReader(io.TextIOWrapper(z.open(filename),
            encoding="utf-8-sig"),delimiter=";"))


def check():
    first=fake()
    same=fake(replace=17)
    results,summary,meta=make_rows(first,include_partial=True)
    modified,_,_=make_rows(same,include_partial=True)
    assert len(results)==17*len(MODEL_NAMES)
    assert meta["draw_count"]==17
    bypos=lambda r,p:[x for x in r if x["pos"]==p]
    for i in range(1,18):
        aa=bypos(results,i);bb=bypos(modified,i)
        assert len(aa)==len(MODEL_NAMES)
        assert all(x["selected20"]==y["selected20"] for x,y in zip(aa,bb)), (
            "Leakage: frozen list at target position changed with that target's actual balls")
    for r in results:
        selected={int(x) for x in r["selected20"].split(",")}
        assert len(selected)==20 and all(1<=n<=80 for n in selected)
        assert int(r["hit_count"])==len(selected&set(
          next(d["nums"] for d in first if d["pos"]==r["pos"])))
        assert r["frozen_before_target"]=="EVET"
        assert r["phase"]=="TEST" or r["phase"]=="EGITIM"
    assert results[0]["warmup"]==1
    assert results[-1]["previous_observed_draw_no"]==550016
    blob,meta,statistics,qc=study(first,True)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        assert z.testzip() is None and len(z.namelist())==7
        assert "01_CEKILIS_ONCESI_20_SAYILIK_DONDURULMUS_LISTELER.csv" in z.namelist()
    assert len(extract(blob,"02_EGITIM_TEST_HER_MOTOR_ISABET.csv"))==len(MODEL_NAMES) # one synthetic day is all TEST
    fresh=meta["next_after_available_source"]
    assert fresh["next_data_slot_pos"]==18
    assert fresh["next_data_slot_day"]=="2026-10-01"
    assert len(fresh["lists"])==len(MODEL_NAMES)
    assert all(len(set(int(x) for x in line.split(",")))==20 for line in fresh["lists"].values())
    assert len(extract(blob,"06_VERI_SONRASI_ILK_20_SAYI_LISTESI.csv"))==len(MODEL_NAMES)
    # Create 207 original V38-shaped columns, with two exact duplicate,
    # two constant and an explicit all-zero signal.
    cols=["E"+str(i).zfill(3) for i in range(207)]
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,"w",zipfile.ZIP_DEFLATED) as z:
        out=io.StringIO()
        writer=csv.writer(out,delimiter=";",lineterminator="\n")
        writer.writerow(("seq","draw_no","day","pos",*cols))
        for p in range(1,8):
            values=[str(p*i) for i in range(207)]
            values[0]="0"
            values[1]="0"
            values[2]="7"
            values[3]=values[4]
            writer.writerow((p,500000+p,"2026-10-01",p,*values))
        z.writestr("02_HER_GERCEK_CEKILISTE_207_UZMAN.csv",out.getvalue().encode())
    columns,quality=audit_v38_zip(buffer.getvalue())
    assert len(columns)==207
    assert quality["draws"]==7
    assert quality["constant"]>=3
    assert quality["duplicate_columns"]>=2
    assert quality["always_zero"]>=2
    with open("/dev/null","w") as _:
        pass
    print("V39 PASS: frozen target unchanged by its own outcome, 20 unique balls, chronological train/test, full hit histogram, real 207-column duplicate/zero audit, ZIP",flush=True)


if __name__=="__main__":
    check()
