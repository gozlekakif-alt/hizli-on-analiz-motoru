# -*- coding: utf-8 -*-
"""V25 selftests: born/second/third state, no lookahead, coupon and timing."""
from collections import Counter
import random
from v21_aile_yasam_dongusu import clock
from v25_aile_dna_kupon import (
    new_state,update_history,pick_family_candidates,choose_family_panel,
    coupon_sets,coupon_event,evaluate_day,draw_has,family_bits,
    predict_satellites,fit_coupon,coupon_report,coupon_confidence,
)

def draw(pos,nums):
    ns=tuple(sorted(nums))
    return {"day":"2026-10-01","pos":pos,"no":50000+pos,
            "dt":"2026-10-01T"+clock(pos)[0],
            "nums":ns,"mask":family_bits(ns)}

assert clock(13)==("01:02",62) and clock(14)==("07:02",422)
assert clock(14)[1]-clock(13)[1]==360
rng=random.Random(3388)
day=[draw(i,rng.sample(range(1,81),20)) for i in range(1,218)]
# Ensure forced 2-core appears in first, second and third draws.
day[0]=draw(1,range(1,21))
day[1]=draw(2,list(range(1,5))+list(range(21,37)))
day[2]=draw(3,list(range(1,5))+list(range(41,57)))
day[3]=draw(4,range(61,81))
day[4]=draw(5,range(21,41))
day[5]=draw(6,range(41,61))
state=new_state()
for d in day[:6]:update_history(state,d)
cand=pick_family_candidates(state,day[:6])
assert (1,2) in cand[(2,"Üç+")]
assert (1,2,3,4) in cand[(4,"Üç+")]
assert (1,3,5) in cand[(3,"İlk")] if (1,3,5) in set(__import__("itertools").combinations(day[0]["nums"],3)) else True
panel,hot12,hot6=choose_family_panel("2026-10-01",6,state,day[:6],day[:6])
co=coupon_sets("2026-10-01",1,panel,hot12,hot6,day[:6])
assert set(co)=={"AileDNA","Sıcak10","Soğuk10","Rastgele10","İlk6Havuz10"}
assert all(len(x)==10 and len(set(x))==10 for x in co.values())
assert all(1<=n<=80 for vals in co.values() for n in vals)
assert tuple(n for n in co["Sıcak10"] if n in day[0]["nums"])
# Changing any future draw must not alter a single family/coupon selection.
changed=day[:6]+[draw(pos,list(range(1,11))+list(range(61,71))) for pos in range(7,218)]
state2=new_state()
for d in changed[:6]:update_history(state2,d)
panel2,a,b=choose_family_panel("2026-10-01",6,state2,changed[:6],changed[:6])
co2=coupon_sets("2026-10-01",1,panel2,a,b,changed[:6])
assert panel==panel2 and co==co2
# Full-day evaluation: target edits can ONLY affect results, not prior choices.
a1,cat1,coup1=evaluate_day("2026-10-01",day,{})
a2,cat2,coup2=evaluate_day("2026-10-01",changed,{})
for l1,l2 in ((a1,a2),(coup1,coup2)):
    r1=[r for r in l1 if r["Saat"]=="00:02"]
    r2=[r for r in l2 if r["Saat"]=="00:02"]
    assert len(r1)==len(r2)
    for x,y in zip(r1,r2):
        for key in ("Aile","Önceden seçilen üç eşlikçi","Yöntem") if "Aile" in x else ("10 sayı","Yöntem"):
            assert x[key]==y[key]
# Every coupon is made before any target and six scores are scored exactly.
for row in coup1:
    for i in range(1,7):
        assert 0<=row[f"Hedef {i}"]<=10
    assert row["6 çekiliş toplam isabet"]==sum(row[f"Hedef {i}"] for i in range(1,7))
assert len(coup1)==18*5
assert len(cat1)==0
# Reject accidental use of a fake 5-minute draw between 01:02 and 07:02.
assert clock(14)[1]-clock(13)[1]==360
# Validate family matches for frozen first6 first hour.
for row in a1:
    if row["Saat"]!="00:02":continue
    fam=tuple(int(v) for v in row["Aile"].split("-"))
    mask=family_bits(fam)
    actual=sum(draw_has(d,mask) for d in day[:6])
    assert actual==row["Kesime dek birlikte çıkış"]
print("V25_SYNTHETIC_PASS",len(a1),len(coup1),len(co))
