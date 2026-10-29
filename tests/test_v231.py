# -*- coding: utf-8 -*-
"""V231 integration: version inventory, real-library execution, blind tests, legacy imports."""
import importlib
import unittest
from collections import Counter
from datetime import datetime, date, time, timedelta
import v231_analiz_koprusu as lab


def make_draws(n_days=6,per_day=100):
    rows=[];ident=70000
    for day_i in range(n_days):
        d=date(2026,8,1)+timedelta(days=day_i)
        for k in range(per_day):
            # deterministic but valid 20/80 sample, not lottery data
            import random
            rng=random.Random(ident*43+519)
            nums=sorted(rng.sample(range(1,81),20))
            dt=datetime.combine(d,time(7,2))+timedelta(minutes=k*5)
            rows.append({"no":ident,"dt":dt.strftime("%Y-%m-%d %H:%M"),
                         "day":d.isoformat(),"nums":nums})
            ident+=1
    return rows

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.rows=make_draws(6,95)
    def test_requirements(self):
        status=lab.versions()
        for dep in ["numpy","scipy","numba","xgboost","z3-solver"]:
            self.assertTrue(status[dep],dep)
    def test_identity_and_checksum(self):
        self.assertEqual(len(lab.cleaned(self.rows)),570)
        self.assertEqual(lab.checksum(self.rows),lab.checksum(list(reversed(self.rows))))
        changed=[dict(r) for r in self.rows]
        changed[-1]["nums"]=list(range(1,21))
        self.assertNotEqual(lab.checksum(self.rows),lab.checksum(changed))
        dup=self.rows+[dict(self.rows[3])]
        with self.assertRaises(ValueError):lab.cleaned(dup)
    def test_numpy_vs_numba_pair_counts(self):
        a=lab.pairs_numpy(self.rows,limit=67)
        b=lab.pairs_numba(self.rows,limit=67)
        self.assertEqual(a,b)
        self.assertEqual(len(a),3160)
        self.assertEqual(sum(r["birlikte"] for r in a),67*190)
    def test_z3_quotas_and_direction(self):
        pools={n:(n-1)//16 for n in range(1,81)}
        arrows={n:"→" if n%2 else "←" for n in range(1,81)}
        tickets=lab.z3_constraint_tickets(pools,arrows,count=3)
        self.assertEqual(len(tickets),3)
        self.assertEqual(len(set(tickets)),3)
        for t in tickets:
            self.assertEqual(len(t),10)
            self.assertEqual([sum(pools[n]==k for n in t) for k in range(5)],[2]*5)
            self.assertGreaterEqual(sum(arrows[n]=="→" for n in t),1)
            self.assertGreaterEqual(sum(arrows[n]=="←" for n in t),1)
    def test_scipy_reference(self):
        pools={n:(n-1)//16 for n in range(1,81)}
        result=lab.scipy_pool_null(self.rows[:12],pools)
        self.assertEqual(len(result),5)
        self.assertEqual(sum(x["gerçek"] for x in result),240)
        self.assertTrue(all(x["beklenen"]==48 for x in result))
    def test_xgboost_chronological_holdout(self):
        result=lab.xgb_walkforward(self.rows,max_targets=100,trees=12)
        self.assertGreater(result["trained_days"],0)
        self.assertGreater(result["tested_days"],0)
        self.assertLess(result["split_through_day"],result["details"][0]["tarih_saat"][:10])
        self.assertEqual(len(result["details"]),result["test_draws"])
        self.assertTrue(all(0<=r["model_isabet"]<=10 for r in result["details"]))
        self.assertEqual(result["mathematical_mean"],2.5)
    def test_legacy_modules_all_importable(self):
        names={
        "v18_cift_havuz_app":"render_v18",
        "v35_11_karakter_app":"render_v35",
        "v39_ileriye_donuk_app":"render_v39",
        "v40_isi_havuzlari_app":"render_v40",
        "v41_derin_yon_app":"render_v41",
        "v42_bes_havuz_kota_app":"render_v42",
        "v44_ana_beyin_app":"render_v44",
        "v45_sinyal_merkezi_app":"render_v45",
        "v50_8li_yakinlik_app":"render_v50",
        "v52_ayni_cekilis_eslikci_app":"render_v52",
        "v54_rng_karakter_app":"render_v54",
        "v55_karakter_once_app":"render_v55",
        }
        for mod,func in names.items():
            with self.subTest(module=mod):
                obj=importlib.import_module(mod)
                self.assertTrue(callable(getattr(obj,func)))
    def test_streamlit_lab_render(self):
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        app=Path(__file__).resolve().parent.parent/"v230_gece_merkezi.py"
        at=AppTest.from_file(str(app),default_timeout=75)
        # A complete 192-draw daytime is required before the lab menu is usable.
        full_day=make_draws(1,192)
        at.session_state["v230_source"]="".join(
            f'{r["no"]};{datetime.strptime(r["dt"],"%Y-%m-%d %H:%M"):%d.%m.%Y %H:%M};'
            +",".join(map(str,r["nums"]))+"\n" for r in full_day)
        at.run()
        self.assertFalse(at.exception,at.exception)
        at.sidebar.radio[0].set_value("🧪 Ortak yazılım laboratuvarı").run()
        self.assertFalse(at.exception,at.exception)
        self.assertTrue(any("V231" in x.value for x in at.subheader))
        # Confirm native Streamlit can execute real Z3 solve via its actual UI button.
        chooser=next(x for x in at.selectbox if x.label=="Çalıştırılacak araç")
        chooser.set_value("Z3 · Havuz/yön kısıtlı 10'lu kolon").run()
        self.assertFalse(at.exception,at.exception)
        self.assertTrue(any("Z3" in x.label for x in at.button))
        for btn in at.button:
            if "Z3 kısıt sistemini çöz" in btn.label:
                btn.click().run()
                break
        self.assertFalse(at.exception,at.exception)

if __name__=="__main__":
    unittest.main()
