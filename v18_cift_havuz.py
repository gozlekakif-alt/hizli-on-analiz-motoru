# -*- coding: utf-8 -*-
"""V18 — Exactly two disjoint, complete pools at EACH of 217 daily draw slots.

GELEN_20 / BEKLEYEN_60 are identities *of that draw*, never permanent teams.
Every valid draw partitions all eighty numbers. The complete history of each
number is then accumulated as seen/not-seen counts and state changes.

No predictive claims: every pool record is written only from an ALREADY
OBSERVED draw. Unknown/missing draw positions remain unknown (not assumed
absent). Six-hour 01:02->07:02 is tagged as a long break, not 5-minute data.
The persistent single source of truth remains existing GitHub veri.txt;
these two outputs are deterministic, rebuildable materialized views.
"""
import csv
import io
from collections import Counter

BALLS=tuple(range(1,81))
ALL_BALLS=frozenset(BALLS)
LIMIT=217
ACT="Çıkan 20"
REST="Çıkmayan 60"


def _clock(pos):
    if not 1<=pos<=LIMIT:
        raise ValueError(f"Günlük sıra 1–{LIMIT} aralığında olmalı")
    mins=2+5*(pos-1) if pos<=13 else 422+5*(pos-14)
    return f"{mins//60:02d}:{mins%60:02d}"


def _validate(day_draws):
    ordered=sorted(day_draws,key=lambda r:r["pos"])
    if not ordered:return []
    day=ordered[0]["day"]
    known=set()
    nos=set()
    for d in ordered:
        pos=int(d["pos"])
        if not 1<=pos<=LIMIT or pos in known:
            raise ValueError("Aynı gün için geçersiz/tekrar çekiliş sırası")
        nums=tuple(int(n) for n in d["nums"])
        if len(nums)!=20 or len(set(nums))!=20 or not set(nums)<=ALL_BALLS:
            raise ValueError("20 eşsiz sayı, 1..80 içinde bulunmalı")
        if d["day"]!=day:
            raise ValueError("Bir çekiliş gününü incelemek için tek gün seç")
        if int(d["no"]) in nos:
            raise ValueError("Tekrar çekiliş numarası")
        if d["dt"][11:16]!=_clock(pos):
            raise ValueError(f"#{d['no']} çekilişinin saat/sırası tutmuyor")
        known.add(pos)
        nos.add(int(d["no"]))
    return ordered


def build_day(day_draws):
    ordered=_validate(day_draws)
    if not ordered:return {
        "meta":{"date":"","processed":0,"missing":list(range(1,LIMIT+1)),
                "active_total":0,"rest_total":0,"completed":False},
        "draws":[],"active20":[],"rest60":[],"numbers":[],
        "transitions":[],"timeline":[]
    }
    day=ordered[0]["day"]
    active_count=[0]*81
    rest_count=[0]*81
    current_state=[None]*81
    current_streak=[0]*81
    longest_active=[0]*81
    longest_rest=[0]*81
    enter=[0]*81
    leave=[0]*81
    stable_active=[0]*81
    stable_rest=[0]*81
    last_active=[None]*81
    last_rest=[None]*81
    first_active=[None]*81
    active_rows=[]
    rest_rows=[]
    draw_rows=[]
    trans_rows=[]
    timeline=[]
    previous=None
    for draw in ordered:
        pos=draw["pos"]
        active=tuple(sorted(draw["nums"]))
        act_set=set(active)
        rest=tuple(n for n in BALLS if n not in act_set)
        assert len(active)==20 and len(rest)==60
        assert act_set.isdisjoint(rest)
        assert act_set.union(rest)==ALL_BALLS

        is_adjacent=(previous is not None and pos==previous["pos"]+1)
        five_min=is_adjacent and pos!=14
        prev_set=set(previous["nums"]) if is_adjacent else None
        common=sorted(act_set&prev_set) if prev_set is not None else []
        incoming=sorted(act_set-prev_set) if prev_set is not None else []
        leaving=sorted(prev_set-act_set) if prev_set is not None else []
        rest_both=sorted(ALL_BALLS-(act_set|prev_set)) if prev_set is not None else []

        for n in BALLS:
            now_active=n in act_set
            if now_active:
                active_count[n]+=1
                last_active[n]=pos
                if first_active[n] is None:first_active[n]=pos
            else:
                rest_count[n]+=1
                last_rest[n]=pos
            if current_state[n] is now_active and is_adjacent:
                current_streak[n]+=1
            else:
                current_streak[n]=1
            current_state[n]=now_active
            if now_active:
                longest_active[n]=max(longest_active[n],current_streak[n])
            else:
                longest_rest[n]=max(longest_rest[n],current_streak[n])
            if prev_set is not None:
                was_active=n in prev_set
                if was_active and now_active:stable_active[n]+=1
                elif not was_active and not now_active:stable_rest[n]+=1
                elif was_active:leave[n]+=1
                else:enter[n]+=1

        base={
            "Gün":day,"Günlük sıra":pos,"Saat":draw["dt"][11:16],
            "Çekiliş no":draw["no"],
        }
        active_rows.append({
            **base,"Havuz":ACT,"Havuzdaki sayı":20,
            "Sayılar":"-".join(f"{n:02d}" for n in active),
            "Birikmiş çıkış kaydı":20*len(active_rows+[])+20
        })
        rest_rows.append({
            **base,"Havuz":REST,"Havuzdaki sayı":60,
            "Sayılar":"-".join(f"{n:02d}" for n in rest),
            "Birikmiş bekleme kaydı":60*len(rest_rows+[])+60
        })
        draw_rows.append({
            **base,"Çıkan 20":"-".join(f"{n:02d}" for n in active),
            "Çıkmayan 60":"-".join(f"{n:02d}" for n in rest),
            "20 havuz birikimi":20*len(draw_rows+[])+20,
            "60 havuz birikimi":60*len(draw_rows+[])+60,
            "Yeni gelen 60→20":len(incoming) if prev_set is not None else None,
            "Kalan 20→20":len(common) if prev_set is not None else None,
            "Ayrılan 20→60":len(leaving) if prev_set is not None else None,
            "Kalan 60→60":len(rest_both) if prev_set is not None else None,
            "Geçiş türü":("5 dakika" if five_min else
                           "6 saat ara (01:02→07:02)" if is_adjacent else
                           "Kayıt eksik/aralıklı" if previous else
                           "Günün ilk kayıtlı çekilişi"),
        })
        if prev_set is not None:
            trans_rows.append({
                **base,"Önceki no":previous["no"],"Geçiş":(
                    "5 dakika" if five_min else "6 saat ara"),
                "20→20 (kalan)":len(common),
                "20→60 (ayrılan)":len(leaving),
                "60→20 (gelen)":len(incoming),
                "60→60 (bekleyen)":len(rest_both),
                "20→20 sayılar":"-".join(map(str,common)),
                "20→60 sayılar":"-".join(map(str,leaving)),
                "60→20 sayılar":"-".join(map(str,incoming)),
                "60→60 sayılar":"-".join(map(str,rest_both)),
            })
            assert len(common)+len(leaving)==20
            assert len(incoming)+len(rest_both)==60
            assert len(common)+len(incoming)==20
            assert len(leaving)+len(rest_both)==60

        row={**base,"Çıkan":20,"Çıkmayan":60}
        for n in BALLS:
            row[f"{n:02d}"]="Ç" if n in act_set else "B"
        timeline.append(row)
        previous=draw
    number_rows=[]
    for n in BALLS:
        count=active_count[n]+rest_count[n]
        assert count==len(ordered)
        state=ACT if current_state[n] else REST
        number_rows.append({
            "Sayı":n,"Son havuz":state,
            "217 gün sırası işlenen":len(ordered),
            "20 havuzunda toplam":active_count[n],
            "60 havuzunda toplam":rest_count[n],
            "20 havuzu %":round(active_count[n]*100/len(ordered),3),
            "20 matematik beklenti":round(len(ordered)/4,3),
            "60 matematik beklenti":round(3*len(ordered)/4,3),
            "60→20 giriş":enter[n],
            "20→60 çıkış":leave[n],
            "20→20 devam":stable_active[n],
            "60→60 devam":stable_rest[n],
            "Çıkan ardışık en uzun":longest_active[n],
            "Bekleyen ardışık en uzun":longest_rest[n],
            "Şu anki havuz serisi":current_streak[n],
            "İlk çıkış pozisyon":first_active[n] or "",
            "Son çıkış pozisyon":last_active[n] or "",
            "Son bekleme pozisyon":last_rest[n] or "",
        })
    observed=set(r["Günlük sıra"] for r in draw_rows)
    missing=[p for p in range(1,LIMIT+1) if p not in observed]
    assert sum(active_count)==20*len(ordered)
    assert sum(rest_count)==60*len(ordered)
    return {
        "meta":{
            "date":day,"processed":len(ordered),"missing":missing,
            "active_total":20*len(ordered),
            "rest_total":60*len(ordered),
            "completed":not missing,
            "first_no":ordered[0]["no"],"last_no":ordered[-1]["no"],
            "five_min_transitions":sum(r["Geçiş"]=="5 dakika" for r in trans_rows),
            "six_hour_transitions":sum(r["Geçiş"]!="5 dakika" for r in trans_rows)
        },
        "draws":draw_rows,
        "active20":active_rows,
        "rest60":rest_rows,
        "numbers":number_rows,
        "transitions":trans_rows,
        "timeline":timeline,
    }


def state_history(day_report,number):
    if not 1<=number<=80:raise ValueError("1..80")
    key=f"{number:02d}"
    streak=0
    last=None
    history=[]
    for row in day_report["timeline"]:
        status=row[key]
        if status==last:streak+=1
        else:streak=1
        last=status
        history.append({
            "Günlük sıra":row["Günlük sıra"],"Saat":row["Saat"],
            "Çekiliş no":row["Çekiliş no"],
            "Sayı":number,"Havuz":ACT if status=="Ç" else REST,
            "Ardışık seri":streak
        })
    return history


def csv_export(rows):
    if not rows:return ""
    buf=io.StringIO()
    writer=csv.DictWriter(buf,fieldnames=list(rows[0]),delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    return "\ufeff"+buf.getvalue()


def pool_txt(rows):
    """Each draw one line; fixed pool cardinality, repeated for every slot."""
    return "\n".join(
        f"{r['Gün']} | {r['Günlük sıra']:03d} | #{r['Çekiliş no']} | "
        f"{r['Saat']} | {r['Havuz']} | {r['Sayılar']}"
        for r in rows
    )+"\n" if rows else ""
