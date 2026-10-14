# -*- coding: utf-8 -*-
"""Fast fixture test for Streamlit V45; never touches the permanent data."""
import json
import random
from io import BytesIO
from zipfile import ZipFile

from v45_sinyal_kor_test import SLOTS
from v45_sinyal_merkezi_app import _days, _sig, _run_analysis, _make_zip


def dummy_day(d,base):
    return [{"day":d,"no":base+i+1,"pos":i+1,
             "nums":sorted(random.Random(base+i).sample(range(1,81),20))}
            for i in range(217)]


def go():
    source=dummy_day("2026-10-13",40000)
    source+=dummy_day("2026-10-14",41000)
    source+=dummy_day("2026-10-15",42000)
    source+=dummy_day("2026-10-16",43000)[:83]
    days,extra,partial,conflicts,byday=_days(source)
    assert len(days)==2 and len(extra)==0
    assert len(partial)==1 and partial[0][1]==83
    assert not conflicts
    d,day=days[0]
    assert _sig(day,13).get("LAG9_45DK_CARRY20") is None
    assert _sig(day,13).get("LAG1_KONTROL20") is None
    assert "LAG9_45DK_CARRY20" in _sig(day,22)
    for i in (0,8,9,13,21,22,80,120,216):
        original = _sig(day,i)
        edit = [dict(x) for x in day]
        edit[i]["nums"] = frozenset(range(1,21))
        assert _sig(edit,i)==original, "Future leak"
    normalized=tuple((d.isoformat(),tuple(
        (r["id"],r["time"],tuple(sorted(r["nums"]))) for r in day
    )) for d,day in days)
    rows,stats=_run_analysis("V45_selftest_fixture",normalized)
    assert len(rows)>5000 and len(stats)>=16
    assert all(r["day"] in ("2026-10-14","2026-10-15") for r in rows)
    assert all(0<=r["hits"]<=r["size"] for r in rows)
    report=_make_zip(rows,stats,[d.isoformat() for d,_ in days])
    with ZipFile(BytesIO(report)) as archive:
        assert len(archive.namelist())==6
        assert "04_72_GUN_GECMIS_BULGULAR.txt" in archive.namelist()
        meta=json.loads(archive.read("00_DURUM.json").decode())
        assert meta["predictive_edge_proven"] is False
        assert meta["target"]==14
    waiting=_make_zip([], [], [])
    with ZipFile(BytesIO(waiting)) as z:
        assert len(z.namelist())==6
        assert len(z.read("03_SINYAL_KATALOGU.csv").decode().splitlines())==19
        assert b"0/14" in z.read("00_TEK_SAYFA_SONUC.txt")
        assert b"72" in z.read("04_72_GUN_GECMIS_BULGULAR.txt")
    print("PASS: V45 Streamlit tab, 2 full + 1 incomplete days, lag overnight guard, future blindness, report ZIP")


if __name__=="__main__":
    go()
