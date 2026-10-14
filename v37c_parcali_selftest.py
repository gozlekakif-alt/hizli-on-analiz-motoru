# -*- coding: utf-8 -*-
"""V37C exact fragment and pre-registered 4-family life controls."""
import json
import math
import sqlite3
import tempfile
import zipfile
from itertools import combinations
from pathlib import Path
from v37_ortak_hafiza import replay
from v37c_parcali_aile_hayati import (run,export,CATALOG,CATALOG_SHA,
    SAMPLE,UNIVERSE,_counts_two,_counts_three,_shape,LANE_MASKS)


def draw(day,pos,members):
    if len(members)!=20:raise AssertionError("synthetic 20")
    return {'day':day,'pos':pos,'no':int(day.replace('-',''))*1000+pos,
            'nums':tuple(sorted(members))}


def brute_two(a,b):
    patterns=[0,0,0]
    for group in combinations(a|b,4):
        first=sum(x in a for x in group)
        next_new=sum(x in (b-a) for x in group)
        if first+next_new!=4 or first not in (1,2,3):
            continue
        if all(x in b for x in group):continue
        patterns[first-1]+=1
    # index 0 means 1+3, 1 means 2+2, 2 means 3+1.
    return tuple(patterns)


def brute_three(a,b,c):
    counts=[0,0,0]
    Y=b-a;Z=c-(a|b)
    for group in combinations(a|b|c,4):
        first=sum(x in a for x in group)
        second=sum(x in Y for x in group)
        third=sum(x in Z for x in group)
        if (first,second,third) not in ((1,1,2),(1,2,1),(2,1,1)):
            continue
        if all(x in c for x in group):continue
        counts[((1,1,2),(1,2,1),(2,1,1)).index((first,second,third))]+=1
    return tuple(counts)


def test():
    assert SAMPLE==len(CATALOG)==len(set(CATALOG))
    assert UNIVERSE==math.comb(80,4)
    assert len(CATALOG_SHA)==64
    assert all(len(c)==4 and min(c)>=1 and max(c)<=80 for c in CATALOG)
    # Brute-force reference on tiny synthetic number universes for exact paths.
    A={1,2,3,4,5};B={2,3,6,7,8};C={1,6,9,10,11}
    assert _counts_two(A,B)==brute_two(A,B)
    assert _counts_three(A,B,C)==brute_three(A,B,C)
    assert _counts_two(None,B)==(0,0,0)
    assert _counts_three(None,B,C)==(0,0,0)
    # One pre-registered family deliberately appears as 2+1+1 only,
    # without all 4 appearing in the same real draw.
    one=CATALOG[0]
    others=[n for n in range(1,81) if n not in one]
    d1=draw("2026-10-01",1,set(one[:2])|set(others[:18]))
    d2=draw("2026-10-01",2,{one[2]}|set(others[10:29]))
    d3=draw("2026-10-01",3,{one[3]}|set(others[20:39]))
    d4=draw("2026-10-01",4,set(others[:20]))
    with tempfile.TemporaryDirectory() as td:
        db=Path(td)/"root.sqlite3"
        source=replay([d1,d2,d3],db,include_partial=True)
        x=run(db)
        assert x["new_draws"]==3 and x["completed_draws"]==3
        with sqlite3.connect(db) as con:
            allrows=[json.loads(row[0]) for row in con.execute(
              "SELECT payload FROM v37c_step ORDER BY seq")]
            assert len(allrows)==3
            assert all(allrows[i]["sample_0_4"]+
                allrows[i]["sample_1_4"]+allrows[i]["sample_2_4"]+
                allrows[i]["sample_3_4"]+allrows[i]["sample_4_4"]==SAMPLE for i in range(3))
            assert allrows[2]["sample_current_first_fragment"]>=1
            assert allrows[1]["exact_two_2+2"]>=0
            events=[json.loads(x[0]) for x in con.execute(
                    "SELECT payload FROM v37c_family_events ORDER BY seq")]
            matching=[a for a in events if a["family_numbers"]=="-".join(
                f"{n:02d}" for n in one) and a["seq"]==3]
            assert matching and matching[0]["path"]=="2+1+1"
            assert matching[0]["event_type"]=="FRAGMENT_FIRST"
            before=con.execute("SELECT payload FROM v37c_step WHERE seq=3").fetchone()[0]
        again=run(db)
        assert again["new_draws"]==0 and again["completed_draws"]==3
        more=replay([d1,d2,d3,d4],db,include_partial=True)
        nxt=run(db)
        assert nxt["new_draws"]==1 and nxt["completed_draws"]==4
        with sqlite3.connect(db) as con:
            assert before==con.execute("SELECT payload FROM v37c_step WHERE seq=3").fetchone()[0]
            assert con.execute("SELECT COUNT(*) FROM v37c_family_events").fetchone()[0]>=1
        out=Path(td)/"study.zip"
        overview=export(db,out)
        assert "ILK_YARI" in overview and "SON_YARI" in overview
        with zipfile.ZipFile(out) as z:
            assert z.testzip() is None and len(z.namelist())==7
            assert "03_ONCEDEN_SECILEN_2048_TARAFSIZ_AILE.csv" in z.namelist()
        # Crucial: a full 4/4 on day position 1 must NOT permanently kill
        # the later (positions 2..13) fragment-only 12-draw episode. When the
        # old full quartet rolls out of 12, the separated members can resume
        # a valid no-4/4 family life.
        restart=Path(td)/"restart.sqlite3"
        restart_draws=[]
        restart_draws.append(draw("2026-10-02",1,set(one)|set(others[:16])))
        for position in range(2,14):
            members=set(one[:2] if position%2==0 else one[2:])
            extras=[n for n in others if n not in members][:18]
            restart_draws.append(draw("2026-10-02",position,members|set(extras)))
        replay(restart_draws,restart,include_partial=True)
        restarted=run(restart)
        assert restarted["completed_draws"]==13
        with sqlite3.connect(restart) as con:
            last=json.loads(con.execute(
                "SELECT payload FROM v37c_step WHERE seq=13").fetchone()[0])
            assert last["sample_12draw_fragment_eligible"]>=1
            cards=[json.loads(t[0]) for t in con.execute(
                "SELECT payload FROM v37c_family_events WHERE seq=13")]
            renewed=[e for e in cards if e["family_numbers"]==
                     "-".join(f"{n:02d}" for n in one)]
            assert renewed, "A prior lifetime full4 must not block new window"
            assert renewed[0]["previous_full4_seq"]==1
            assert renewed[0]["full4_in_last12"]==0

        # Missing position cuts 12-draw history. A partial fragment must not
        # claim that unknown numbers failed to appear in the gap.
        gap=Path(td)/"gap.sqlite3"
        g3=draw("2026-10-01",4,{one[3]}|set(others[20:39]))
        replay([d1,d2,g3],gap,include_partial=True)
        run(gap)
        with sqlite3.connect(gap) as con:
            last=json.loads(con.execute("SELECT payload FROM v37c_step WHERE seq=3").fetchone()[0])
            assert last["exact_two_1+3"]==0
            assert last["exact_three_2+1+1"]==0
        # Future outcomes do not change the past evidence at step 3.
        future=Path(td)/"future.sqlite3"
        d5=draw("2026-10-01",4,{one[0]}|set(others[5:24]))
        replay([d1,d2,d3,d5],future,include_partial=True)
        run(future)
        with sqlite3.connect(future) as con:
            assert before==con.execute("SELECT payload FROM v37c_step WHERE seq=3").fetchone()[0]
    print("V37C PASS: exact 2/3 drawing path combinatorics, unbiased catalogue, true 2+1+1 never-full quartet, append-only, gap, no future leak, ZIP",flush=True)


if __name__=="__main__":test()
