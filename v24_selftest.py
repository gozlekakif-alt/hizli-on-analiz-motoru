# -*- coding: utf-8 -*-
"""V24: audit first->second predictions, full-day chronology, no label leakage."""
import math
import random
from v21_aile_yasam_dongusu import clock
from v24_aile_ikinci_ongoru import (
    p_family,select_families,per_day_forecasts,first_second_event,
    first_sighting_candidates,subset_mask,strategy_fit,summarize,
)


def make(pos,nums):
    nums=tuple(sorted(nums))
    return {"day":"2026-10-01","pos":pos,"no":60000+pos,
            "dt":"2026-10-01T"+clock(pos)[0],"nums":nums,
            "mask":subset_mask(nums)}


assert clock(13)==("01:02",62) and clock(14)==("07:02",422)
assert clock(14)[1]-clock(13)[1]==360
assert math.isclose(p_family(2),20/80*19/79)
rng=random.Random(5003)
day=[make(i,rng.sample(range(1,81),20)) for i in range(1,218)]
day[0]=make(1,range(1,21))
day[1]=make(2,range(21,41))
day[12]=make(13,[1,2]+list(range(10,28)))
day[13]=make(14,[1,2]+list(range(30,48)))
day[14]=make(15,[1,2]+list(range(50,68)))
# First true day appearance of 70,71 is p14, and after p14 all samples can differ.
# A separate 01:02 -> 07:02 example must count minutes, not scheduled slots.
first=[make(13,range(1,21)),make(14,[1,2]+list(range(21,39)))]
if first[0]["mask"] & subset_mask((1,2)) == subset_mask((1,2)):
    assert first[1]["mask"] & subset_mask((1,2)) == subset_mask((1,2))
    assert clock(14)[1]-clock(13)[1]==360
# Proper new first at first anchor
signals=select_families(day[0],[],"2026-10-01",1)
for k,policies in signals.items():
    for method,fam in policies.items():
        assert len(fam)==k
        assert set(fam).issubset(set(day[0]["nums"]))
        assert len(set(fam))==k
        assert first_second_event("2026-10-01",day,1,k,method,fam)["İlk sıra"]==1
# Frozen by prior + anchor only, changing future draws never changes selection.
prev=day[:13]
anchor=day[13]
a=select_families(anchor,prev,"2026-10-01",14)
changed=day[:14]+[make(i,range(61,81)) for i in range(15,218)]
b=select_families(changed[13],changed[:13],"2026-10-01",14)
assert a==b
for k,policies in a.items():
    for method,fam in policies.items():
        seen=first_sighting_candidates(anchor,prev)
        assert fam not in seen[k]
        r=first_second_event("2026-10-01",day,14,k,method,fam)
        r2=first_second_event("2026-10-01",changed,14,k,method,fam)
        for field in ("İlk sıra","Aile","RNG 11 içinde","RNG gün içinde"):
            assert r[field]==r2[field]
# Direct one-day end-to-end: all event picks must have 0 preceding full occurrences.
events=per_day_forecasts("2026-10-01",day)
for row in events:
    anchor=day[row["İlk sıra"]-1]
    nums=tuple(int(x) for x in row["Aile"].split("-"))
    mask=subset_mask(nums)
    assert anchor["mask"] & mask == mask
    assert not any(d["mask"] & mask == mask for d in day[:row["İlk sıra"]-1])
    assert not row["Gün bitmeden ikinci"] or row["İkinci sıra"]>row["İlk sıra"]
# No hypothetical 01:02..07:02 draws: 13->14 = true one position, +360 minutes.
assert clock(14)[1]-clock(13)[1]==360
print("V24_TEST_PASS",len(events),"1day events",len(a),"sizes")
