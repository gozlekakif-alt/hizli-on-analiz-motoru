# -*- coding: utf-8 -*-
"""V37 Stage A test: exact 80-ball lives, 20/60, idempotence, sqlite and no future leak."""
from __future__ import annotations
import json
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path
from v37_ortak_hafiza import replay,export,run_text,OPERATING,ALL80
from v36_rng_davranis_klonu import on_slot


def fake(day,p,n=20,shift=0):
    members=[(shift+i)%80+1 for i in range(n)]
    return {'day':day,'pos':p,'no':int(day.replace('-',''))*1000+p,
            'nums':members}


def test():
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/"core.sqlite3"
        zip_path=Path(temp)/"core.zip"
        data=[fake('2026-10-01',p,shift=(p%3)*7) for p in range(1,15)]
        a=replay(data,path,include_partial=True)
        assert a['draw_count']==14 and a['ball_step_rows']==14*80
        assert a['new_draws_added']==14
        assert len(OPERATING)==8
        assert a['reservoir_change_events']>0
        assert a['same_number_event_dialogues']>0
        after1=Path(path).read_bytes()
        b=replay(data,path,include_partial=True)
        assert b['new_draws_added']==0 and b['ball_step_rows']==14*80
        assert Path(path).read_bytes()==after1,"Duplicate replay changed physical DB"
        with sqlite3.connect(path) as con:
            assert con.execute("SELECT COUNT(*) FROM ball_step WHERE draw_no=?",(data[0]['no'],)).fetchone()[0]==80
            for drawid,cnt,sumhit in con.execute("SELECT draw_no,COUNT(*),SUM(hit) FROM ball_step GROUP BY draw_no"):
                assert cnt==80 and sumhit==20
            for drawid in [data[0]['no'],data[13]['no']]:
                v=dict(con.execute("SELECT heat_seat,COUNT(*) FROM ball_step WHERE draw_no=? GROUP BY heat_seat",(drawid,)))
                assert sorted(v.values())==[13,13,13,13,14,14]
            assert con.execute("SELECT COUNT(*) FROM event_dialogue").fetchone()[0]>0
            assert con.execute("""SELECT COUNT(*) FROM event_dialogue d
                WHERE NOT EXISTS(SELECT 1 FROM reservoir_event e
                    WHERE e.draw_no=d.draw_no AND e.num=d.num)""").fetchone()[0]==0
        c=replay(data+[fake('2026-10-01',15,shift=21)],path,include_partial=True)
        assert c['new_draws_added']==1 and c['draw_count']==15
        # In-place source corrections are rejected, leaving checkpoint intact.
        modified=data[:]
        modified[2]=fake('2026-10-01',3,shift=1)
        try:replay(modified,path,include_partial=True)
        except ValueError as exc:assert "Geçmiş değişmiş" in str(exc) or "kısa" in str(exc)
        else:raise AssertionError("Changed historical draw accepted")
        with sqlite3.connect(path) as con:
            assert con.execute("SELECT COUNT(*) FROM draw_ledger").fetchone()[0]==15
        # Crossing 01:02 (pos13) to 07:02 (pos14) is genuine one step.
        with sqlite3.connect(path) as con:
            assert con.execute("SELECT gap_from_prior FROM draw_ledger WHERE pos=14").fetchone()[0]==0
            assert con.execute("SELECT valid11 FROM ball_step WHERE draw_no=? LIMIT 1",
                               (data[13]['no'],)).fetchone()[0]==1
        export(path,zip_path,c)
        with zipfile.ZipFile(zip_path) as z:
            assert z.testzip() is None and len(z.namelist())==6
            assert "01_V37_ORTAK_80_SAYI_HAFIZA.sqlite3" in z.namelist()
        # 217 last draw -> next day 00:02 contiguous in lifetime
        two=[fake('2026-10-02',217,shift=3),
             fake('2026-10-03',1,shift=3)]
        nxt=Path(temp)/"overnight.sqlite3"
        replay(two,nxt,include_partial=True)
        with sqlite3.connect(nxt) as con:
            assert con.execute("SELECT gap_from_prior FROM draw_ledger ORDER BY seq DESC LIMIT 1").fetchone()[0]==0
            hits=con.execute("SELECT life_hits,day_hits FROM ball_step WHERE draw_no=? AND num=4",
                             (two[1]['no'],)).fetchone()
            assert hits==(2,1)
        # Missing row is UNKNOWN, not a counted absence.
        missing=Path(temp)/"missing.sqlite3"
        replay([fake('2026-10-01',p) for p in (1,2,3,5)],missing,include_partial=True)
        with sqlite3.connect(missing) as con:
            assert con.execute("SELECT gap_from_prior FROM draw_ledger WHERE pos=5").fetchone()[0]==1
            assert con.execute("SELECT life_wait FROM ball_step WHERE draw_no=? AND num=80",
                               (fake('2026-10-01',5)['no'],)).fetchone()[0] is None
        print("V37 synthetic PASS: 80*15 cards, exact 20/60, heat 6 seats, no duplicate, conflict safety, overnight, missing-slot unknown, event dialogues and ZIP",flush=True)
    if "--full" in sys.argv:
        from v11_arastirma import read_draws
        text=Path("veri.txt").read_text(encoding="utf-8-sig")
        real,bad=read_draws(text)
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"v37.sqlite3"
            z=Path(folder)/"v37.zip"
            info=replay(real,db)
            assert info["draw_count"]>=70*217
            assert info["ball_step_rows"]==info["draw_count"]*80
            nochange=replay(real,db)
            assert nochange['new_draws_added']==0
            export(db,z,info)
            with zipfile.ZipFile(z) as zz:
                assert zz.testzip() is None and len(zz.namelist())==6
            print("V37 72-DAY REAL TEST PASS:",json.dumps({k:v for k,v in info.items() if k not in ('daily','source_warnings')},ensure_ascii=False),flush=True)


if __name__=="__main__":test()
