# -*- coding: utf-8 -*-
"""V22 exact two sightings -> frozen third signal, 6-hour clock and mates."""
import random
from v22_ucuncu_aile_zaman import (
    clock, candidate_first_two, choose_companions, evaluate_hour,
    summarise_rows, p_family, validate_hour
)


def mk(day,pos,nums):
    nums=tuple(sorted(nums))
    return {"day":day,"pos":pos,"nums":nums,"no":9900+pos,
            "mask":sum(1<<(x-1) for x in nums),"dt":day+"T"+clock(pos)[0]}


assert clock(1)[0]=="00:02"
assert clock(13)[0]=="01:02"
assert clock(14)[0]=="07:02"
assert clock(217)[0]=="23:57"
assert clock(14)[1]-clock(13)[1]==360
rng=random.Random(77532)
day="2026-10-01"
rows={p:mk(day,p,rng.sample(range(1,81),20)) for p in range(1,218)}
rows[14]=mk(day,14,range(1,21))
rows[15]=mk(day,15,range(21,41))
rows[16]=mk(day,16,list(range(1,11))+list(range(21,31)))
rows[17]=mk(day,17,range(41,61))
rows[18]=mk(day,18,list(range(21,31))+list(range(41,51)))
rows[19]=mk(day,19,list(range(41,51))+list(range(61,71)))
# 01/02 core first at 07:02 (p14) and 07:12 (p16); do not select k that appears 3x.
family=candidate_first_two([rows[p] for p in range(14,20)],2)
assert any(x["fam"]==(1,2) and x["first"]==14 and x["second"]==16 for x in family)
selected=[(x["fam"],x["first"],x["second"],x["gap"]) for x in family]
# Changing ONLY future results cannot change the family choice.
before={k:evaluate_hour(day,rows,14,k)[0] for k in [2,3,4,5,6,7,8,9,10]}
other=rows.copy()
for p in range(20,218):
    other[p]=mk(day,p,range(60,80))
after={k:evaluate_hour(day,other,14,k)[0] for k in [2,3,4,5,6,7,8,9,10]}
for k in before:
    if before[k] is None:
        assert after[k] is None
    else:
        for a in ("Önceden seçilen aile","İlk görünüş sıra","İkinci görünüş sıra",
                  "Eşit aralık hedef sıra","Önceden seçilen üç eşlikçi"):
            assert before[k][a]==after[k][a]
# Even changing last six of SAME hour cannot alter rule.
later=rows.copy()
for p in range(20,26):
    later[p]=mk(day,p,range(61,81))
for k in before:
    b=evaluate_hour(day,later,14,k)[0]
    if before[k] is None: assert b is None
    else: assert b["Önceden seçilen aile"]==before[k]["Önceden seçilen aile"]
# When core occurs in third draw, no future companions used for choosing.
assert abs(p_family(2)-(20/80)*(19/79))<1e-14
a=mk(day,14,range(1,21));b=mk(day,15,range(21,41))
try:
    validate_hour([a]*6,[b]*6)
    raise AssertionError("broken hour accepted")
except ValueError:
    pass
r=[row for row in before.values() if row is not None]
assert r
for rec in r:
    assert rec["Son6 çekiliş"]==6
    assert rec["Son6 tam aile görünüşü"]>=rec["Son6 üçüncü geldi"]
    assert rec["Gün içinde daha sonra üçüncü"]>=rec["Son6 üçüncü geldi"]
    assert rec["Eşlikçi sınama sayısı"]==3*rec["Son6 tam aile görünüşü"] if rec["Boyut"]<=4 else rec["Eşlikçi sınama sayısı"]==0
s=summarise_rows([dict(v,Dönem="Ayrı test") for v in r])
assert s and all(v["Önceden seçilen saat/aile"]==1 for v in s)
print("V22_SYNTHETIC_PASS",len(family),len(r),len(s))
