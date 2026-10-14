# -*- coding: utf-8 -*-
"""V38: 207 registry / every observed real draw / no lookahead regression."""
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from v38_207_katalog import IDS,GROUPS,CATALOGUE
from v38_207_uzman_yurutucu import replay,export,DEEP_PENDING
from v37_ortak_hafiza import replay as init_memory


def synthetic(n=15,change_target=False,day="2026-10-01"):
    rows=[]
    for p in range(1,n+1):
        numbers=list(range(1,21)) if p%2 else list(range(16,36))
        if p==n and change_target:numbers=list(range(61,81))
        rows.append(dict(day=day,pos=p,no=501000+p,nums=numbers))
    return rows


def pull(db):
    with sqlite3.connect(db) as con:
        return [(seq,json.loads(__import__('zlib').decompress(v))) for seq,v in
                con.execute("SELECT seq,packed_metrics FROM v38_draw ORDER BY seq")]


def main():
    assert len(IDS)==207 and len(set(IDS))==207 and len(GROUPS)==17
    assert all(len(i.split("."))==2 for i in IDS)
    assert len(DEEP_PENDING)>0
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)/"root.sqlite3"
        base=init_memory(synthetic(),root,include_partial=True)
        result=replay(root)
        assert result["experts"]==207
        assert result["groups"]==17
        assert result["draw_count"]==15
        assert result["measurement_cells"]==207*15
        assert result["per_step_measurement_experts"]+result["proxy_screening_experts"]==207
        first=pull(root)
        assert len(first)==15 and all(len(v)==207 for _,v in first)
        # Every 80-card draw balances and every expert evaluates exactly once.
        idx=IDS.index("LIFE.01")
        assert all(v[idx]==20 for _,v in first)
        idx=IDS.index("HEAT.14")
        assert all(v[idx]==80 for _,v in first)
        idx=IDS.index("MIRROR.02")
        assert all(0<=v[idx]<=20 for _,v in first)
        # Exactly equal source, no new rows or altered metrics/checkpoint.
        again=replay(root)
        assert again["newly_processed_draws"]==0 and pull(root)==first
        # Target draw 16 cannot change data through draw 15.
        out=Path(d)/"one.zip"
        totals=export(root,out)
        assert len(totals)==207
        with zipfile.ZipFile(out) as z:
            assert z.testzip() is None and len(z.namelist())==6
            assert "02_HER_GERCEK_CEKILISTE_207_UZMAN.csv" in z.namelist()
        updated=synthetic(16)
        init_memory(updated,root,include_partial=True)
        extension=replay(root)
        assert extension["newly_processed_draws"]==1
        assert pull(root)[:15]==first
        future=Path(d)/"future.sqlite3"
        init_memory(synthetic(16,change_target=True),future,include_partial=True)
        replay(future)
        assert pull(future)[:15]==first
        # Source missing draw is not inserted as an observed zero.
        gap=Path(d)/"gap.sqlite3"
        records=[r for r in synthetic(14) if r["pos"]!=7]
        init_memory(records,gap,include_partial=True)
        s=replay(gap)
        assert s["draw_count"]==13
        assert len(pull(gap))==13
    print("V38 PASSED: 207/207 distinct experts, full per-draw signals, 80/20, six heat, no-lookahead, idempotence, gaps, ZIP",flush=True)


if __name__=="__main__":
    main()
