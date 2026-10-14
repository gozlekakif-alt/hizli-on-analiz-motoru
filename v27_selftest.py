# -*- coding: utf-8 -*-
"""V27 strict audit: 80 seats, 6 categories, pretarget construction, night."""
from collections import Counter
from v21_aile_yasam_dongusu import clock
from v27_alti_isi_koltuk import (
    LOOKBACKS, METHODS, GROUPS, COUNTS, make_index, classify_before,
    classify_and_count, fitted_rate, evaluate_target, largest_remainder,
    DECAY
)


def make_draw(pos,nums,day="2026-10-01"):
    return {
      "no":80000+pos,"pos":pos,"day":day,"nums":tuple(sorted(nums)),
      "dt":day+"T"+clock(pos)[0],
      "mask":sum(1<<(n-1) for n in nums)
    }

assert clock(1)==("00:02",2)
assert clock(13)==("01:02",62)
assert clock(14)==("07:02",422)
assert clock(14)[1]-clock(13)[1]==360
assert LOOKBACKS[-1]==1519 and METHODS==("Frekans","Yarı ömür 12")
assert len(GROUPS)==6 and sum(COUNTS)==80
assert tuple(COUNTS)==(13,13,14,14,13,13)

# Deterministic sample. Draw 'future' changed: no effect on PRETARGET state.
from random import Random
rng=Random(2828)
draws=[make_draw(p,rng.sample(range(1,81),20)) for p in range(1,218)]
chron,prefix,ewm=make_index(draws)
t=64
for L in (6,12,24,36):
    for method in METHODS:
        groups,trends,score=classify_before(t,L,method,prefix,ewm)
        assert len(groups)==len(trends)==81
        sizes,members=__import__("v27_alti_isi_koltuk").bins_for_state(groups,trends)
        assert sum(sizes)==80
        assert tuple(len(group) for group in members)==COUNTS
        # No target results: exact rank classifications can be recovered from
        # an independent prefix-only history with the same selected t.
        ch,cp,ce=make_index(draws[:t])
        g2,tr2,s2=classify_before(t,L,method,cp,ce)
        assert groups==g2 and trends==tr2
        assert max(abs(score[n]-s2[n]) for n in range(1,81))<1e-4
        if method=="Frekans":
            for n in range(1,81):
                assert score[n]==sum(n in draw["nums"] for draw in draws[t-L:t])
        else:
            for n in range(1,81):
                oracle=sum((DECAY**j)*(n in draws[t-1-j]["nums"]) for j in range(L))
                assert abs(score[n]-oracle)<.0002
        rates=fitted_rate([0]*18,[0]*18)
        assert all(x==.25 for x in rates)
        z=evaluate_target(t,draws[t],prefix,ewm,L,method,rates,True)
        assert sum(z["actual_seats"])==20
        assert sum(z["pred_seats"])==20
        assert z["group_sizes"]==COUNTS
        assert abs(z["brier"]-.1875)<1e-10
        assert 0<=z["pred20hit"]<=20
        assert len(set(z["picked"]))==20
        # 80 balls divided once in groups; target 20 assigned exactly once.
        for n in draws[t]["nums"]:
            assert n in z["members"][groups[n]]
        # Future mutation cannot alter earlier temperature membership.
        altered=draws[:t]+[make_draw(p,range(1,21)) for p in range(t+1,218)]
        # Target at t itself also altered. Selection MUST stay frozen.
        altered[t]=make_draw(t+1,range(61,81))
        aa,bb,cc=make_index(altered)
        ga,ta,sa=classify_before(t,L,method,bb,cc)
        assert ga==groups and ta==trends
        assert all(abs(sa[n]-score[n])<.0002 for n in range(1,81))

# Empty/full rates never leave 20-seat budget.
fake_members=[[] for _ in range(6)]
assert sum(largest_remainder([13*.25/3]*3+[13*.25/3]*3+
                              [14*.25/3]*6+[13*.25/3]*6,
                              fake_members))==20
print("V27_SYNTHETIC_PASS",len(draws),len(GROUPS),len(LOOKBACKS),len(METHODS))
