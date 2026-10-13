# -*- coding: utf-8 -*-
"""V18 daily 20/60 complementary pool invariants and real-data regression."""
from datetime import datetime,timedelta
from v11_arastirma import read_draws
from v18_cift_havuz import (
    ACT,REST,BALLS,LIMIT,_clock,_validate,build_day,
    state_history,csv_export,pool_txt
)


def record(day,pos,no,nums):
    mins=2+5*(pos-1) if pos<=13 else 422+5*(pos-14)
    return {"day":day,"pos":pos,"no":no,
            "dt":(datetime.fromisoformat(day)+timedelta(minutes=mins)).isoformat(timespec="minutes"),
            "nums":list(nums)}


assert len(BALLS)==80 and LIMIT==217
assert _clock(1)=="00:02" and _clock(13)=="01:02"
assert _clock(14)=="07:02" and _clock(217)=="23:57"
assert ACT!=REST
a=record("2026-10-11",1,1001,range(1,21))
b=record("2026-10-11",2,1002,range(11,31))
c=record("2026-10-11",3,1003,range(21,41))
s=build_day([c,a,b])
assert s["meta"]["processed"]==3
assert s["meta"]["active_total"]==60
assert s["meta"]["rest_total"]==180
assert s["meta"]["completed"] is False
assert len(s["meta"]["missing"])==214
assert len(s["active20"])==3 and len(s["rest60"])==3
assert len(s["numbers"])==80 and len(s["timeline"])==3
assert len(s["transitions"])==2
assert s["transitions"][0]["20→20 (kalan)"]==10
assert s["transitions"][0]["20→60 (ayrılan)"]==10
assert s["transitions"][0]["60→20 (gelen)"]==10
assert s["transitions"][0]["60→60 (bekleyen)"]==50
assert s["transitions"][1]["20→20 (kalan)"]==10
assert len(pool_txt(s["active20"]).splitlines())==3
assert len(pool_txt(s["rest60"]).splitlines())==3
assert len(csv_export(s["timeline"]))>100
assert len(state_history(s,25))==3
assert [x["Havuz"] for x in state_history(s,25)]==[REST,ACT,ACT]
assert s["numbers"][24]["20 havuzunda toplam"]==2
assert s["numbers"][24]["60 havuzunda toplam"]==1
assert s["numbers"][24]["60→20 giriş"]==1
assert s["numbers"][24]["20→20 devam"]==1
# Missing slots must not be treated as observed 60-ball waiting events.
gap=build_day([a,c])
assert not gap["transitions"]
assert gap["numbers"][24]["20 havuzunda toplam"]==1
assert gap["numbers"][24]["60 havuzunda toplam"]==1
assert 2 in gap["meta"]["missing"]
# Six-hour night break is a time-labelled transition, NOT five minutes.
n13=record("2026-10-11",13,1013,range(1,21))
n14=record("2026-10-11",14,1014,range(21,41))
night=build_day([n13,n14])
assert night["meta"]["six_hour_transitions"]==1
assert night["meta"]["five_min_transitions"]==0
assert night["transitions"][0]["Geçiş"]=="6 saat ara"
# Duplicate/broken/no 80 partition can never silently enter archive.
for bad in ([a,a],[record("2026-10-11",5,2000,[1]*20)],
            [a,record("2026-10-12",2,2001,range(21,41))],
            [record("2026-10-11",218,2002,range(1,21))]):
    try:
        build_day(bad)
        raise AssertionError("Invalid draw accepted")
    except ValueError:pass

draws,errors=read_draws(open("veri.txt",encoding="utf-8-sig").read())
assert len(draws)>=15839
days=sorted({r["day"] for r in draws})
# First full day and partial last day, duplicate no and gap auditing.
for day in (days[0],days[10],days[35],days[-2],days[-1]):
    result=build_day([r for r in draws if r["day"]==day])
    meta=result["meta"]
    N=meta["processed"]
    assert 1<=N<=217
    assert len(result["draws"])==N
    assert len(result["active20"])==len(result["rest60"])==N
    assert len(result["numbers"])==80
    assert len(result["timeline"])==N
    assert meta["active_total"]==20*N and meta["rest_total"]==60*N
    assert sum(row["20 havuzunda toplam"] for row in result["numbers"])==20*N
    assert sum(row["60 havuzunda toplam"] for row in result["numbers"])==60*N
    assert all(row["20 havuzunda toplam"]+row["60 havuzunda toplam"]==N
               for row in result["numbers"])
    assert all(row["Havuzdaki sayı"]==20 for row in result["active20"])
    assert all(row["Havuzdaki sayı"]==60 for row in result["rest60"])
    assert all(len(row["Sayılar"].split("-"))==20 for row in result["active20"])
    assert all(len(row["Sayılar"].split("-"))==60 for row in result["rest60"])
    assert len({r["Çekiliş no"] for r in result["draws"]})==N
    assert len(csv_export(result["active20"]).splitlines())==N+1
    assert len(csv_export(result["rest60"]).splitlines())==N+1
    assert len(pool_txt(result["active20"]).splitlines())==N
    assert len(pool_txt(result["rest60"]).splitlines())==N
    print("V18_DAY",day,N,meta["active_total"],meta["rest_total"],len(meta["missing"]))
assert build_day([r for r in draws if r["day"]==days[0]])["meta"]["completed"]
print("V18_PASS",len(days))
