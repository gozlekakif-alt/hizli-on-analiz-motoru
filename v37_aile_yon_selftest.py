# -*- coding: utf-8 -*-
"""V37B integration tests: shared ledger, quartet path, direction, idempotence."""
import csv
import io
import json
import math
import sqlite3
import tempfile
import zipfile
import sys
from pathlib import Path

from v37_ortak_hafiza import replay
from v37_aile_yon_uzmanlari import (build, export, first_coverage_paths,
    SIX, OUT_FIELDS)


def draw(day,p,start):
    nums=tuple((start+i-1)%80+1 for i in range(1,21))
    return {'day':day,'pos':p,'no':int(day.replace('-',''))*1000+p,'nums':nums}


def test():
    one=draw("2026-10-01",1,0)
    two=draw("2026-10-01",2,2)
    three=draw("2026-10-01",3,5)
    assert one["nums"]==tuple(range(1,21))
    assert two["nums"]==tuple(range(3,23))
    recent=[{"day":one["day"],"pos":1,"wins":frozenset(one["nums"])}]
    paths,previous,_=first_coverage_paths(frozenset(two["nums"]),recent,2)
    assert previous==math.comb(18,4)
    assert paths["3+1"]==math.comb(18,3)*2
    assert paths["2+2"]==math.comb(18,2)
    assert sum(paths.values())+previous==math.comb(20,4)
    with tempfile.TemporaryDirectory() as p:
        db=Path(p)/"root.sqlite3"
        zip_path=Path(p)/"addon.zip"
        replay([one,two],db,include_partial=True)
        result=build(db)
        assert result["new_draws"]==2 and result["completed_draws"]==2
        with sqlite3.connect(db) as c:
            arr=[json.loads(x[0]) for x in c.execute("SELECT payload FROM v37_family_step ORDER BY seq")]
            assert arr[0]["quartet_path_4"]==math.comb(20,4)
            assert arr[0]["quartet_repeats"]==0
            assert arr[1]["quartet_repeats"]==math.comb(18,4)
            assert arr[1]["quartet_already_covered"]==math.comb(18,4)
            assert arr[1]["quartet_path_3+1"]==math.comb(18,3)*2
            assert arr[1]["quartet_path_2+2"]==math.comb(18,2)
            assert arr[1]["heat_up"]+arr[1]["heat_down"]+arr[1]["heat_still"]==80
            names={x[0] for x in c.execute("SELECT motor_id FROM motor_registry")}
            assert "FAMILY.QUARTET_COVER_PATH" in names
            assert "DIRECTION.HEAT_6X6" in names
            assert c.execute("SELECT COUNT(*) FROM v37_family_examples").fetchone()[0]==8
        result2=build(db)
        assert result2["new_draws"]==0
        replay([one,two,three],db,include_partial=True)
        result3=build(db)
        assert result3["new_draws"]==1 and result3["completed_draws"]==3
        with sqlite3.connect(db) as c:
            assert c.execute("SELECT COUNT(*) FROM v37_family_step").fetchone()[0]==3
        summary=export(db,zip_path)
        assert summary
        with zipfile.ZipFile(zip_path) as z:
            assert len(z.namelist())==7 and z.testzip() is None
            data=list(csv.DictReader(io.StringIO(
                z.read("01_HER_CEKILIS_AILE_2_3_4_AYRINTILI.csv").decode("utf-8-sig")),delimiter=";"))
            assert len(data)==3
        # Overnight and missing slot must not create imaginary prior family.
        db2=Path(p)/"gap.sqlite3"
        replay([one,draw("2026-10-01",3,0)],db2,include_partial=True)
        build(db2)
        with sqlite3.connect(db2) as c:
            last=json.loads(c.execute("SELECT payload FROM v37_family_step ORDER BY seq DESC LIMIT 1").fetchone()[0])
            assert last["quartet_repeats"]==0
        # Result for t must not depend on what happens in later t+1.
        db3=Path(p)/"future.sqlite3"
        replay([one,two,draw("2026-10-01",3,50)],db3,include_partial=True)
        build(db3)
        with sqlite3.connect(db3) as c:
            preserved=c.execute("SELECT payload FROM v37_family_step WHERE seq=2").fetchone()[0]
        with sqlite3.connect(db) as c:
            original=c.execute("SELECT payload FROM v37_family_step WHERE seq=2").fetchone()[0]
        assert preserved==original
    print("V37B synthetic PASS family2/3/4 history, complete 3+1/2+2, heat direction, dialogue, idempotent incremental, missing-slot, no future leakage, seven ZIP reports",flush=True)
    if "--full" in sys.argv:
        from v11_arastirma import read_draws
        raw=Path("veri.txt").read_text(encoding="utf-8-sig")
        rows,bad=read_draws(raw)
        with tempfile.TemporaryDirectory(prefix="v37_test_") as root:
            dest=Path(root)/"root.sqlite3"
            out=Path(root)/"expert.zip"
            info=replay(rows,dest,include_partial=False)
            ext=build(dest)
            assert ext["completed_draws"]==info["draw_count"]
            assert ext["direction_transition_rows"]>0
            export(dest,out)
            with zipfile.ZipFile(out) as z:assert z.testzip() is None
            print("V37B FULL REAL PASS:",json.dumps(ext,ensure_ascii=False),flush=True)


if __name__=="__main__":test()
