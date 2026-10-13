# -*- coding: utf-8 -*-
"""V21 invariants: 2..10 exactness, clock, core variants, no target leakage."""
import math
import random
from v21_aile_yasam_dongusu import (
    clock, hour_label, recurrent_day_families, daily_study,
    group_full_days, read_catalog, catalog_study, forward_test,
    run_study, p_family, bit_positions
)


def draw(day, pos, nums, no):
    return {"day": day, "pos": pos, "no": no,
            "nums": tuple(sorted(nums)),
            "dt": day+"T"+clock(pos)[0],
            "mask": sum(1 << (n-1) for n in nums)}


assert clock(1)[0] == "00:02"
assert clock(13)[0] == "01:02"
assert clock(14)[0] == "07:02"
assert clock(217)[0] == "23:57"
assert clock(14)[1] - clock(13)[1] == 360
assert hour_label(13).startswith("01:02")
assert abs(p_family(2) - (20/80*19/79)) < 1e-15
assert len(read_catalog("Aile;Boyut\n01-02-03-04-05;5\n01-02-03-04-05-06-07-08-09-10;10\n"))==2

rng = random.Random(4201)
day = [draw("2026-10-01", p, rng.sample(range(1, 81), 20), p) for p in range(1,218)]
day[0]=draw("2026-10-01",1,range(1,21),1)
day[1]=draw("2026-10-01",2,range(11,31),2)
day[2]=draw("2026-10-01",3,range(1,21),3)
families = recurrent_day_families(day[:3])
for k in range(2,11):
    fam=tuple(range(11, 11+k))
    assert fam in families[k]
    assert bit_positions(families[k][fam])==[1,2,3]
assert bit_positions(families[10][tuple(range(1,11))]) == [1,3]
assert tuple(range(21,31)) not in families[10]

sizes,tops,cores=daily_study('2026-10-01',day,top_per_size=2,top_cores=2)
assert len(sizes)==9
assert len(tops)<=18
assert all(c['Değişen farklı çevre kadrosu']>=1 for c in cores)
assert len(group_full_days(day)[0])==1
assert group_full_days(day[:-1])[1]==[('2026-10-01',216)]

catalog=read_catalog('Aile;Boyut\n11-12-13-14-15;5\n01-02-03-04-05-06-07-08-09-10;10\n')
cp=catalog_study([('2026-10-01',day)],catalog)
assert len(cp)==2
assert cp[1]['Tam birlikte çıkış']>=2  # 11..15 appears in draws 1,2,3
fw,summary=forward_test([('2026-10-01',day)],train_days=0)
assert len(fw)==18*3
assert len(summary)==3
assert all(z['Hedef sıralar'].split('-')[-1].isdigit() for z in fw)

# No-lookahead: editing last 6 may change hits but MUST NOT change selections.
changed=list(day)
for p in range(7,13):
    changed[p-1]=draw('2026-10-01',p,range(61,81),p)
fw2,_=forward_test([('2026-10-01',changed)],train_days=0)
for a,b in zip(fw,fw2):
    assert a['Önceden seçilen çekirdek']==b['Önceden seçilen çekirdek']
    assert a['İlk6 tam tekrar']==b['İlk6 tam tekrar']

print('V21_SYNTHETIC_PASS',len(sizes),len(fw),len(cores))

