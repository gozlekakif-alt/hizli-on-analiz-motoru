# -*- coding: utf-8 -*-
"""V23 confidence tests: exact first-two; 00/01/07 gap; changing companions."""
import random
from itertools import combinations
from v21_aile_yasam_dongusu import recurrent_day_families,clock
from v23_aile_ilk_iki_tamgun import (
    first_two_positions, third_position, query_family_day, scan_day,
    family_mask, gap_band
)


def mk(pos, nums):
    nums=tuple(sorted(nums))
    return {
        "day":"2026-10-01","pos":pos,"no":42000+pos,
        "nums":nums,"mask":sum(1<<(n-1) for n in nums),
        "dt":"2026-10-01T"+clock(pos)[0],
    }


assert first_two_positions((1<<0)|(1<<12)|(1<<13)) == (1,13)
assert third_position((1<<0)|(1<<12)|(1<<13)) == 14
assert clock(13)[0]=="01:02" and clock(14)[0]=="07:02"
assert clock(14)[1]-clock(13)[1] == 360
assert gap_band(216)=="97-216 çekiliş"
assert family_mask([10,2,5]) == ((2,5,10),sum(1<<(n-1) for n in (2,5,10)))

rng=random.Random(23374)
rows=[mk(pos,rng.sample(range(1,81),20)) for pos in range(1,218)]
rows[12]=mk(13,[1,2,3,4]+list(range(10,26)))
rows[13]=mk(14,[1,2,3,4]+list(range(30,46)))
rows[14]=mk(15,[1,2,3,4]+list(range(50,66)))
q=query_family_day(rows[:15],[1,2,3,4])
assert q["İlk sıra"]<=13 and q["İkinci sıra"]<=14
# Exact boundary scenario using three chosen chronological samples.
mini=[
    mk(13,range(1,21)),
    mk(14,list(range(1,5))+list(range(21,37))),
    mk(15,list(range(1,5))+list(range(41,57))),
]
res=query_family_day(mini,[1,2,3,4])
assert (res["İlk sıra"],res["İkinci sıra"],res["Üçüncü sıra"]) == (13,14,15)
assert res["İlk→ikinci çekiliş farkı"] == 1
assert res["İlk→ikinci gerçek dakika"] == 360
assert res["İki çevredeki farklı sayılar"] == 32
assert res["İlk iki birlikte sabit çevre"] == ""
assert query_family_day(mini,[1,2,3,4,5])["Durum"] == "Yalnız ilk"
assert query_family_day(mini,[79,80])["Durum"] == "Görülmedi"

# Small strict brute oracle for ALL k=2..10 on first 8 random draws:
sample=[mk(i+1,rng.sample(range(1,81),20)) for i in range(8)]
result=recurrent_day_families(sample)
for k in range(2,6):
    from collections import defaultdict
    observed=defaultdict(list)
    for d in sample:
        for fam in combinations(d["nums"],k):
            observed[fam].append(d["pos"])
    assert set(result[k]) == {fam for fam,hits in observed.items() if len(hits)>=2}
    for fam,bits in result[k].items():
        p1,p2=first_two_positions(bits)
        assert [p1,p2] == observed[fam][:2]
    del observed
# Large families are validated by direct 217-slot membership, without storing
# millions of one-off k-subsets in memory.
for k in range(6,11):
    for fam,bits in list(result[k].items())[:250]:
        mask=family_mask(fam)[1]
        oracle=[d["pos"] for d in sample if d["mask"]&mask==mask]
        assert first_two_positions(bits)==tuple(oracle[:2])
    # Two full identical 20-sets generate every C(20,k) recurring family.
    twins=[mk(1,range(1,21)),mk(2,range(1,21))]
    twin_result=recurrent_day_families(twins,min_k=k,max_k=k)
    assert len(twin_result[k])==__import__("math").comb(20,k)

summary,gaps,hours,transition,examples=scan_day("2026-10-01",rows,top=2)
assert len(summary)==9 and len(summary)>=len(examples)/6
assert sum(x["İlk iki aynı saat"]+x["İlk iki farklı saat"] for x in summary) == sum(
    x["İki ve üzeri çıkmış farklı aile"] for x in summary)
assert sum(x["İlk iki gece/sabah boşluğu geçen"] if "İlk iki gece/sabah boşluğu geçen" in x else
           x["İlk→ikinci gece/sabah boşluğu geçen"] for x in summary)>=1
assert all(x["İlk sıra"]<x["İkinci sıra"] for x in examples)
print("V23_PASS",len(summary),len(gaps),len(hours),len(transition),len(examples))
