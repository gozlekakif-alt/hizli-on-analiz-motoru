# -*- coding: utf-8 -*-
"""V230 regression tests. Executes production pure functions and Streamlit smoke tests."""
# Independent CI smoke verification run.
import ast
import collections
import datetime
import io
import re
import random
import unittest
from pathlib import Path
from datetime import date, time, timedelta
from collections import Counter

ROOT=Path(__file__).resolve().parent.parent
SRC=ROOT/"v230_gece_merkezi.py"
FUNCTIONS={
    "numbers","parse_stamp","pos_of","record","parse_text","combine","daytime",
    "night_slot","night_rows","rank_pools","delta_arrows","baseline",
    "moving_state","candidate_groups","ticket_set","backup_text",
}

def load_core():
    tree=ast.parse(SRC.read_text(encoding="utf-8"), filename=str(SRC))
    selected=[]
    for node in tree.body:
        if isinstance(node,ast.FunctionDef) and node.name in FUNCTIONS:
            node.decorator_list=[]
            selected.append(node)
    module=ast.Module(body=selected,type_ignores=[])
    ast.fix_missing_locations(module)
    env={"__builtins__":__builtins__,
         "re":re,"datetime":datetime.datetime,"date":date,"time":time,
         "timedelta":timedelta,"Counter":Counter,"random":random,
         "st":None}
    exec(compile(module,str(SRC),"exec"),env)
    return env

F=load_core()

def synthetic_day(d=date(2026,8,1),night=True):
    rows=[]
    for i in range(192):
        dt=datetime.datetime.combine(d,time(7,2))+timedelta(minutes=5*i)
        nums=sorted({((i*13+j*7)%80)+1 for j in range(20)})
        rows.append(F["record"](10000+i,dt,nums))
    if night:
        for i in range(25):
            dt=datetime.datetime.combine(d,time(23,2))+timedelta(minutes=5*i)
            nums=sorted({((i*11+j*17)%80)+1 for j in range(20)})
            rows.append(F["record"](10192+i,dt,nums))
    return rows

class CoreTests(unittest.TestCase):
    def test_syntax_and_expected_functions(self):
        compile(SRC.read_text(encoding="utf-8"),str(SRC),"exec")
        for func in FUNCTIONS: self.assertIn(func,F)
    def test_slots_calendar(self):
        cases={"00:02":1,"01:02":13,"07:02":14,"22:57":205,
               "23:02":206,"23:57":217}
        for value,expected in cases.items():
            hh,mm=map(int,value.split(":"))
            self.assertEqual(F["pos_of"](datetime.datetime(2026,8,1,hh,mm)),expected)
    def test_operational_night(self):
        d=date(2026,8,1)
        make=lambda i: datetime.datetime.combine(d,time(23,2))+timedelta(minutes=i*5)
        self.assertEqual([F["night_slot"](make(i),d) for i in range(25)],list(range(25)))
        self.assertIsNone(F["night_slot"](datetime.datetime(2026,8,1,0,2),d))
        self.assertIsNone(F["night_slot"](datetime.datetime(2026,8,2,7,2),d))
        rows=synthetic_day()
        self.assertEqual(len(F["night_rows"](d.isoformat(),rows)),25)
    def test_192_and_fixed_snapshot(self):
        rows=synthetic_day()
        day,seen=F["daytime"]("2026-08-01",rows)
        self.assertEqual((seen,len(day)),(192,192))
        c,p,a=F["baseline"](day)
        self.assertEqual(set(p.values()),set(range(5)))
        self.assertEqual([sum(v==i for v in p.values()) for i in range(5)],[16]*5)
        self.assertEqual(sum(c.values()),192*20)
        self.assertEqual((c,p,a),F["baseline"](day)) # unchanged after night
        mc,mp,ma=F["moving_state"](rows)
        self.assertEqual([sum(v==i for v in mp.values()) for i in range(5)],[16]*5)
        self.assertEqual(sum(mc.values()),72*20)
        self.assertEqual(set(ma.values()).difference({"→","←","="}),set())
        self.assertEqual(len(F["night_rows"]("2026-08-01",rows)),25)
    def test_raw_input_checks(self):
        example=" ".join(map(str,range(1,21)))
        self.assertEqual(F["numbers"](example),list(range(1,21)))
        for values in [" ".join(["1"]*20),"1,2,3"," ".join(map(str,range(61,81)))+" 100"]:
            with self.assertRaises(ValueError): F["numbers"](values)
        txt="123;2026-08-01 23:02;"+",".join(map(str,range(1,21)))+"\n"
        parsed,problems=F["parse_text"](txt)
        self.assertEqual((len(parsed),len(problems)),(1,0))
        duplicated=F["combine"](txt,parsed)
        self.assertEqual((len(duplicated[0]),len(duplicated[1])),(1,0))
        conflicting=F["record"](124,datetime.datetime(2026,8,1,23,2),range(1,21))
        _,issues=F["combine"](txt,[conflicting])
        self.assertTrue(issues)
    def test_ticket_quotas(self):
        day,_=F["daytime"]("2026-08-01",synthetic_day())
        fixed=F["baseline"](day)
        for strategy,quota in [("5 havuz: 2+2+2+2+2",[2]*5),
          ("3 havuz: 3 sıcak / 4 ılık / 3 soğuk",[3,4,3])]:
            groups,qs,_=F["candidate_groups"](strategy,fixed,quota)
            cols=F["ticket_set"](groups,qs,fixed[2],42,Counter())
            self.assertEqual(len(cols),10)
            self.assertEqual(len(set(cols)),10)
            for grp,k in zip(groups,qs):
                self.assertEqual(len(set(cols)&set(grp)),k)
    def test_missing_draws_not_imagined(self):
        rows=synthetic_day(night=False)
        removed=rows.pop(48)
        entries,count=F["daytime"]("2026-08-01",rows)
        self.assertEqual((entries,count),([],191))
        self.assertEqual(F["night_rows"]("2026-08-01",rows),{})

class StreamlitSmokeTests(unittest.TestCase):
    def test_empty_and_loaded_day(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(SRC),default_timeout=45)
        at.run()
        self.assertFalse(at.exception,at.exception)
        raw=F["backup_text"](synthetic_day())
        at.session_state["v230_source"]=raw
        at.run()
        self.assertFalse(at.exception,at.exception)
        self.assertTrue(any("Hızlı On" in x.value for x in at.title))
        self.assertTrue(any("22:57" in x.value for x in at.subheader))
        self.assertTrue(any("25" in str(x.value) for x in at.metric))
        # Read-only secondary app engine panel should render without mutation.
        menu=at.sidebar.radio[0]
        menu.set_value("🧠 Eski analiz motorları").run()
        self.assertFalse(at.exception,at.exception)

if __name__=="__main__":
    unittest.main()
