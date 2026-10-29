# -*- coding: utf-8 -*-
"""V232 chronological leakage barriers, pool invariants, real UI integration."""
import datetime
import random
import unittest
from collections import Counter

from v232_gecis_motorlari import (
    ENGINES, as_time, backtest_nights, build_tickets, character, four_paths,
    frozen_at_2257, night_indices, next_target, source_key, to_csv,
)

DAY=datetime.date(2026,8,1)


def synthetic(days=3):
    out=[]
    ident=90000
    for dayidx in range(days):
        d=DAY+datetime.timedelta(days=dayidx)
        # 00:02..01:02 + 07:02..23:57 = 217 draws per date.
        slots=[datetime.datetime.combine(d,datetime.time(0,2))+
               datetime.timedelta(minutes=5*i) for i in range(13)]
        slots += [datetime.datetime.combine(d,datetime.time(7,2))+
                  datetime.timedelta(minutes=5*i) for i in range(204)]
        for stamp in slots:
            rng=random.Random(ident*317+17)
            nums=sorted(rng.sample(range(1,81),20))
            out.append({"no":ident,"dt":stamp.isoformat(timespec="minutes"),
                        "day":d.isoformat(),"nums":nums})
            ident+=1
    return out


class CharacterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=synthetic()
        cls.day=DAY.isoformat()
        cls.dayrows=[r for r in cls.rows if r["day"]==cls.day and
                     datetime.time(7,2)<=as_time(r).time()<=datetime.time(22,57)]
        cls.frozen=frozen_at_2257(cls.dayrows)
        cls.paths=four_paths(cls.rows,cls.day)

    def test_192_fixed_5x16(self):
        self.assertEqual(len(self.dayrows),192)
        self.assertEqual([sum(x==i for x in self.frozen.values()) for i in range(5)],[16]*5)
        self.assertEqual(len(self.paths),80)
        self.assertEqual(set(len(x) for x in self.paths.values()),{4})
        with self.assertRaises(ValueError):
            frozen_at_2257(self.dayrows[:-1])

    def test_night_cross_midnight_25(self):
        self.assertEqual(len(night_indices(self.rows,self.day)),25)
        other=night_indices(self.rows,(DAY+datetime.timedelta(days=1)).isoformat())
        self.assertEqual(len(other),25)
        slots,stamp=next_target(self.rows,self.day) or (None,None)
        self.assertIsNone(slots)
        self.assertIsNone(stamp)

    def test_one_before_target_frozen_and_control(self):
        target=datetime.datetime.combine(DAY,datetime.time(23,2))
        prior=[r for r in self.rows if as_time(r)<target]
        original=build_tickets(prior,self.frozen,self.paths,target.isoformat(timespec="minutes"))
        self.assertEqual(set(original),set(ENGINES))
        self.assertEqual(len(original),6)
        for chosen in original.values():
            self.assertEqual(len(chosen),10)
            self.assertEqual(len(set(chosen)),10)
        for engine in ENGINES[:-1]:
            for i in range(5):
                self.assertEqual(sum(self.frozen[n]==i for n in original[engine]),2)
        self.assertEqual(original,build_tickets(prior,self.frozen,self.paths,target.isoformat(timespec="minutes")))
        # Winning result changed AFTER freeze: predictions identical.
        copied=[dict(r) for r in self.rows]
        target_pos=next(i for i,r in enumerate(copied) if as_time(r)==target)
        copied[target_pos]["nums"]=list(range(1,21))
        self.assertEqual(original,build_tickets(
            [r for r in copied if as_time(r)<target],
            self.frozen,self.paths,target.isoformat(timespec="minutes")))
        with self.assertRaises(ValueError):
            build_tickets(self.rows,self.frozen,self.paths,target.isoformat(timespec="minutes"))

    def test_transition_directions_interpretable(self):
        observed=character(self.paths,self.dayrows,self.frozen)
        self.assertEqual(len(observed),80)
        self.assertEqual(sum(v["sinif"] in {
            "ISINAN","SOGUYAN","GERI_DONUS","SABIT"} for v in observed.values()),80)

    def test_walkforward_each_result_precedes_its_target(self):
        r=backtest_nights(self.rows,max_nights=2)
        self.assertEqual((r["test_nights"],r["test_targets"]),(2,50))
        self.assertEqual(len(r["detail"]),50*len(ENGINES))
        self.assertEqual(len(r["summary"]),len(ENGINES))
        self.assertEqual(sum(row["hedef"]>row["kaynak_once"] for row in r["detail"]),
                         len(r["detail"]))
        self.assertTrue(all(sum(row[f"{k}/10"] for k in range(11))==
                            row["hedef"] for row in r["summary"]))
        self.assertTrue(all(0<=row["isabet"]<=10 for row in r["detail"]))
        self.assertIn("motor",to_csv(r["summary"]))
        self.assertEqual(r["summary"],backtest_nights(self.rows,max_nights=2)["summary"])

    def test_source_mutation_changes_fingerprint(self):
        b=list(self.rows)
        a=source_key(b)
        b[0]=dict(b[0],nums=list(range(1,21)))
        self.assertNotEqual(a,source_key(b))


class StreamlitCharacterSmoke(unittest.TestCase):
    def test_real_streamlit_menu_and_backtest(self):
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        src=Path(__file__).resolve().parent.parent/"v230_gece_merkezi.py"
        at=AppTest.from_file(str(src),default_timeout=120)
        rows=synthetic(days=3)
        at.session_state["v230_source"]="".join(
            f'{r["no"]};{as_time(r):%d.%m.%Y %H:%M};'
            +",".join(map(str,r["nums"]))+"\n" for r in rows)
        at.run()
        self.assertFalse(at.exception,at.exception)
        at.sidebar.radio[0].set_value("🧬 Karakter geçiş motorları").run()
        self.assertFalse(at.exception,at.exception)
        self.assertTrue(any("V232" in x.value for x in at.subheader))
        self.assertTrue(any("70 gece" in x.label for x in at.button))
        # Backtest uses only synthetic results, not the current target's outcome.
        button=next(x for x in at.button if "70 geceyi" in x.label)
        button.click().run()
        self.assertFalse(at.exception,at.exception)
        self.assertIn("v232_backtest_result",at.session_state)


if __name__=="__main__":
    unittest.main()
