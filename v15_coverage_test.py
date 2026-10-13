# -*- coding: utf-8 -*-
"""V15-B exploratory replay. Designed AFTER inspecting original V15 results.

Report separately: this is not a new independent blind test. Coverage changes
coupon selection, which can increase best-of-six counts without RNG advantage.
"""
from v11_arastirma import read_draws
from v15_kupon_motoru import retrospective_test, as_csv, METHODS, RANDOM

draws,bad=read_draws(open("veri.txt",encoding="utf-8-sig").read())
r=retrospective_test(draws,train_days=36,coverage=True)
m=r["summary"]
assert m["targets"]==3774,m
assert m["model_coupons"]==22644,m
assert m["random_coupons"]==22644,m
assert m["model_coverage"]>=45,m
assert m["model_coverage"]>m["random_coverage"],m
assert len(r["methods"])==7
assert len(r["families"])==7*9
assert all(45<=d["Model altı kupon farklı sayı"]<=60 for d in r["differences"])
print("V15_B_PASS",m)
print("V15_B_METHODS",r["methods"])
print("V15_B_BEST6",r["best6"])
print("V15_B_FAMILY6",[x for x in r["families"] if x["Aile boyutu"]==6])
