# -*- coding: utf-8 -*-
"""V28 selftest: chronology, H1..H12, hold states before draw, RNG nulls."""
from random import Random
from v21_aile_yasam_dongusu import clock
from v28_dijital_kaplan_dongu import (
    BALLS,HEAT_SIX,HEAT_MACRO,SIX_SIZES,HEAT_MAP,DECAY,
    HOUR_STARTS,hour_info,state_before,make_cache,profile,
    transition_table,hslot_table,sustained_table,extract_hourly_6to6_probes,
    day_similarity,hour_12_lifecycle
)


def draw(day,pos,nums):
    return {
        "day":day,"pos":pos,"no":int(day.replace("-",""))*1000+pos,
        "dt":day+"T"+clock(pos)[0],
        "nums":tuple(sorted(nums))
    }


assert clock(13)==("01:02",62)
assert clock(14)==("07:02",422)
assert clock(14)[1]-clock(13)[1]==360
assert hour_info(1)[2]=="H1"
assert hour_info(12)[2]=="H12"
assert hour_info(13)[2]=="Ek"
assert hour_info(14)[2]=="H1"
assert hour_info(19)[2]=="H6"
assert hour_info(25)[2]=="H12"
assert hour_info(217)[2]=="H12"
assert len(HOUR_STARTS)==18
assert len(HEAT_SIX)==6 and sum(SIX_SIZES)==80
assert HEAT_MAP==(0,0,1,1,2,2)

rng=Random(334411)
rows=[]
for day in ("2026-10-01","2026-10-02"):
    rows.extend(draw(day,pos,rng.sample(BALLS,20)) for pos in range(1,218))
temps=[0.]*81
six,macro=state_before(temps)
assert sum(six[n]==0 for n in BALLS)==SIX_SIZES[0]
assert tuple(sum(six[n]==g for n in BALLS) for g in range(6))==SIX_SIZES
assert tuple(sum(macro[n]==g for n in BALLS) for g in range(3))==(26,28,26)
assert abs(DECAY**12-.5)<1e-12
eligible={"2026-10-01","2026-10-02"}
ob=profile(rows,eligible,detailed=True)
assert len(ob["hourly"])==2*18*80
assert len(ob["daypair"])==1
assert ob["daypair"][0]["Geçiş"]=="23:57→00:02"
assert ob["counts"]["targets"]["total"]==434-144
assert all(len(r["H1..H12 makro yolları"])==12 for r in ob["hourly"])
assert all(len(r["H1..H12 altı sıcaklık yolları"])==12 for r in ob["hourly"])
assert all(sum(r[f"{name} H sayısı"] for name in HEAT_SIX)==12 for r in ob["hourly"])
assert all(r["Soğukta H"]+r["Ilıkta H"]+r["Sıcakta H"]==12 for r in ob["hourly"])
assert all(r["Soğuk en uzun H kalış"]<=12 for r in ob["hourly"])
assert len(extract_hourly_6to6_probes(ob))>=3

null=profile(make_cache(rows,seed=333),eligible,detailed=False)
assert len(null["hourly"])==0
assert null["counts"]["targets"]["total"]==ob["counts"]["targets"]["total"]
a=transition_table(ob,[null],"macro_trans",True)
b=transition_table(ob,[null],"six_trans",False)
assert len(a)==9 and len(b)==36
assert len(hslot_table(ob,[null]))==39
assert len(sustained_table(ob,[null]))==72
assert sum(x["Gerçek geçiş"] for x in a)==sum(ob["counts"]["macro_trans"].values())
assert sum(x["Gerçek geçiş"] for x in b)==sum(ob["counts"]["six_trans"].values())
assert len(day_similarity(ob)[1])==0  # first full day only 73 of 217 targets after warmup
# H1..H12 means 12 consecutive REAL hourly blocks in these NEW files,
# distinct from one-hour 12 five-minute results.
hour_rows=hour_12_lifecycle(ob["hourly"])
assert len(hour_rows)==2*80*7
assert len({r["Sayı"] for r in hour_rows})==80
assert all(sum(r[f"{g} saat sayısı"] for g in HEAT_MACRO)==12 for r in hour_rows)
assert all(r["H1 saat"]!=r["H12 saat"] for r in hour_rows)
assert sum(ob["counts"]["hour_macro_trans"].values())==35*80
assert sum(ob["counts"]["hour_macro_same_day"].values())==34*80
assert sum(ob["counts"]["hour_macro_next_day"].values())==80


# Perturb ONLY future outcomes; all scores at an earlier cutoff remain equal.
before=[0.]*81
for row in rows[:160]:
    ns=set(row["nums"])
    before=[0.]+[before[n]*DECAY+int(n in ns) for n in BALLS]
snap1=state_before(before)
changed=rows[:160]+[draw(r["day"],r["pos"],range(61,81)) for r in rows[160:]]
before2=[0.]*81
for row in changed[:160]:
    ns=set(row["nums"])
    before2=[0.]+[before2[n]*DECAY+int(n in ns) for n in BALLS]
snap2=state_before(before2)
assert snap1==snap2
print("V28_SYNTHETIC_PASS",len(ob["hourly"]),ob["counts"]["targets"]["total"],len(a),len(b))
