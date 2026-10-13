# -*- coding: utf-8 -*-
"""V15 six 10-ball coupon test with 2..10 predeclared families."""
from datetime import datetime,timedelta
from v11_arastirma import read_draws
from v15_kupon_motoru import (
    N_TICKETS,METHODS,RANDOM,FAMILY_SIZES,
    fit_models,control_tickets,build_six,result_of,
    retrospective_test,as_csv,fair_ten_probability
)


def example(day,pos,no,nums):
    minute=2+5*(pos-1) if pos<=13 else 422+5*(pos-14)
    dt=datetime.fromisoformat(day)+timedelta(minutes=minute)
    return {"day":day,"pos":pos,"no":no,
            "dt":dt.isoformat(timespec="minutes"),"nums":list(nums)}


draws,bad=read_draws(open("veri.txt",encoding="utf-8-sig").read())
assert len(draws)>=15839
assert fair_ten_probability(10)>0
assert len(METHODS)==N_TICKETS and len(set(METHODS))==N_TICKETS
assert FAMILY_SIZES==tuple(range(2,11))
days=sorted({d["day"] for d in draws})
training_days=days[:36]
training=[d for d in draws if d["day"] in training_days]
fit=fit_models(training,36)
assert fit["train_days"]==36
assert fit["training_through"]=="2026-09-05"

trial_day="2026-10-11"
day=[d for d in draws if d["day"]==trial_day]
known=[d for d in day if d["pos"]<20]
target=next(d for d in day if d["pos"]==20)
assert len(known)==19
six=build_six(known,20,target["no"],fit)
rand=control_tickets(trial_day,20)
assert len(six)==len(rand)==6
assert len({tuple(sorted(x["numbers"])) for x in six})==6
assert len({tuple(sorted(x)) for x in rand})==6
assert all(len(x["numbers"])==len(set(x["numbers"]))==10 for x in six)
assert [x["method"] for x in six]==list(METHODS)
assert all(x["numbers"][:6]==x["family6"] for x in six)
assert all(all(1<=n<=80 for n in x["numbers"]) for x in six)
assert six==build_six(known,20,target["no"],fit)
assert rand==control_tickets(trial_day,20)
results=result_of(six,target["nums"])
assert len(results)==6
assert all(r["prefix"][10]==r["ten"] for r in results)
assert all(0<=r["prefix"][k]<=k for r in results for k in FAMILY_SIZES)
# A changed target result MUST NOT change pretarget coupons.
alt_target=example(trial_day,20,target["no"],range(61,81))
assert six==build_six(known,20,target["no"],fit)
assert result_of(six,target["nums"])!=result_of(six,alt_target["nums"])
# A known target may never be included in its own prediction inputs.
try:
    build_six(known+[target],20,target["no"],fit)
    raise AssertionError("Target result was accepted into predictor")
except ValueError as e:
    assert "zaten mevcut" in str(e)
# Missing previous-12 sequence and non-7–12 target hour cannot produce tickets.
try:
    build_six(known[:-1],20,target["no"],fit)
    raise AssertionError("Gap was not recognized")
except ValueError as e:assert "12 kesintisiz" in str(e)
try:
    build_six(known,26,target["no"],fit)
    raise AssertionError("Wrong target hour allowed")
except ValueError as e:assert "7–12" in str(e)

report=retrospective_test(draws,train_days=36)
meta=report["summary"]
assert meta["train_days"]==36 and meta["test_days"]==37,meta
assert meta["first_test"]=="2026-09-06",meta
assert meta["last_test"]=="2026-10-12",meta
assert meta["targets"]==37*102,meta
assert meta["model_coupons"]==6*meta["targets"],meta
assert meta["random_coupons"]==6*meta["targets"],meta
assert meta["coupons"]==12*meta["targets"],meta
assert 10<=meta["model_coverage"]<=60,meta
assert 10<=meta["random_coverage"]<=60,meta
assert all(10<=x["Model altı kupon farklı sayı"]<=60
           for x in report["differences"])
assert len(report["ledger"])==meta["coupons"]
assert len(report["differences"])==meta["targets"]
assert len(report["methods"])==7
assert len(report["families"])==7*9
assert len(report["best6"])==2
assert all(0<=row["10'da isabet"]<=10 for row in report["ledger"])
assert all(0<=row["6'lı isabet"]<=6 for row in report["ledger"])
assert len(as_csv(report["ledger"]))>90000

# Six controls are independent 10-ball targets, each frozen before result.
totals={name:sum(r["Hedef"] for r in report["methods"]
                 if r["Kupon yolu"]==name) for name in (*METHODS,RANDOM)}
assert all(totals[name]==meta["targets"] for name in METHODS)
assert totals[RANDOM]==6*meta["targets"]
for row in report["families"]:
    if row["Kupon yolu"]==RANDOM:
        assert row["Deneme"]==6*meta["targets"]
    else:
        assert row["Deneme"]==meta["targets"]
print("V15_PASS",meta)
print("V15_METHODS",report["methods"])
print("V15_BEST_SIX",report["best6"])
print("V15_FAMILY_6",[
    row for row in report["families"] if row["Aile boyutu"]==6
])
