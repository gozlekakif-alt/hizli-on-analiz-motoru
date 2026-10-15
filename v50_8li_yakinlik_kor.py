#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V50 frozen 8-family second-close-occurrence -> +7..+12 reappearance test.
Research-only. The 7..12 window was chosen after inspecting historical data
on/through Oct 12 2026; historical outcomes are NOT independent validation.
Prospective tests use first 14 full days on/after Oct 14 2026.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import math
import random
import statistics
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from v45_sinyal_kor_test import parse_draws, SLOTS

START = date(2026, 10, 14)
HIST_END = date(2026, 10, 12)
N_DAYS = 14
FAMILY_SIZE = 8
NEAR_LAGS = (1, 2, 3, 4, 5, 6)
TARGET_LAGS = (7, 8, 9, 10, 11, 12)
PRIMARY_HITS = 8
SECONDARY_HITS = 7
REFERENCE = "V49 retrospective discovery: 7-12 chosen after inspecting 72 days"
SLOT_INDEX = {t: i for i,t in enumerate(SLOTS)}

def day_index(day, clock):
    # UTC/time-zone/DST independent index for the 217 DRAW opportunities per day.
    d = date.fromisoformat(day) if isinstance(day,str) else day
    return d.toordinal()*217 + SLOT_INDEX[clock]

def select_eight(shared):
    # Freeze BEFORE inspecting next draw; exactly ONE deterministic ticket per trigger.
    return tuple(sorted(shared)[:8])

def control_eight(first_id, second_id):
    salt = f"V50_pre_register_2026-10-15|{first_id}|{second_id}|K8"
    seed = int(hashlib.sha256(salt.encode()).hexdigest()[:32],16)
    return tuple(sorted(random.Random(seed).sample(range(1,81),8)))

def generate_events(full):
    """Returns fixed tickets from each real same-day 5-30m overlap >=8.

    One event per pair, rather than C(overlap,8) multiply counted families.
    This function never accesses target outcomes.
    """
    out = []
    for day, draws in sorted(full.items()):
        for pos, second in enumerate(draws):
            for lag in NEAR_LAGS:
                if pos < lag:
                    continue
                first = draws[pos-lag]
                m1 = datetime.fromisoformat(first["day"]+"T"+first["time"])
                m2 = datetime.fromisoformat(second["day"]+"T"+second["time"])
                if m2-m1!=timedelta(minutes=5*lag):
                    continue
                shared = first["nums"] & second["nums"]
                if len(shared)<8:
                    continue
                ticket = select_eight(shared)
                event = {"day":day.isoformat(),"trigger_id":second["id"],
                         "first_id":first["id"],"first_time":first["time"],
                         "second_time":second["time"],"trigger_slot":day_index(day,second["time"]),
                         "near_gap":lag,"shared_size":len(shared),
                         "ticket":ticket,
                         "random_ticket":control_eight(first["id"],second["id"])}
                out.append(event)
    return out

def evaluate_events(events, targets, target_dates):
    """Score only a target after its ticket has been frozen. Missing slots SKIP."""
    scored=[]
    for event in events:
        origin=event["trigger_slot"]
        for lag in TARGET_LAGS:
            target=targets.get(origin+lag)
            if not target:
                continue
            if date.fromisoformat(target["day"]) not in target_dates:
                continue
            win = len(set(event["ticket"]) & target["nums"])
            control = len(set(event["random_ticket"]) & target["nums"])
            scored.append({"date":target["day"],"time":target["time"],
              "draw_id":target["id"],"lag":lag,
              "trigger_date":event["day"],"trigger_id":event["trigger_id"],
              "trigger_gap":event["near_gap"],"shared_at_trigger":event["shared_size"],
              "frozen_ticket":"-".join(map(str,event["ticket"])),
              "fixed_random":"-".join(map(str,event["random_ticket"])),
              "hits":win,"control_hits":control,
              "win8":int(win==8),"random8":int(control==8),
              "win7":int(win>=7),"random7":int(control>=7)})
    return scored

def summarize(rows,days,events,partial,broken,duplicate):
    unique_targets=len({(r["date"],r["draw_id"]) for r in rows})
    win8=sum(r["win8"] for r in rows)
    rng8=sum(r["random8"] for r in rows)
    win7=sum(r["win7"] for r in rows)
    rng7=sum(r["random7"] for r in rows)
    # Exact hypergeometric (ticket size 8, draw 20 of 80)
    p8=math.comb(72,12)/math.comb(80,20)
    p7=math.comb(8,7)*math.comb(72,13)/math.comb(80,20)+p8
    n=len(rows)
    date_summary=[]
    for day in sorted(days):
        dayrows=[r for r in rows if r["date"]==day.isoformat()]
        date_summary.append({
            "day":day.isoformat(),"targets":len(dayrows),
            "unique_draws":len({r["draw_id"] for r in dayrows}),
            "win8":sum(x["win8"] for x in dayrows),
            "random8":sum(x["random8"] for x in dayrows),
            "win7":sum(x["win7"] for x in dayrows),
            "random7":sum(x["random7"] for x in dayrows)})
    return {
      "start":START.isoformat(), "days_target":N_DAYS,
      "full_days_tested":len(days),"tested_days":list(map(str,sorted(days))),
      "method":"K8 deterministic lowest-8, 1-6 real 5-minute close pair, test 7-12 DRAW slots",
      "prospective_primary":"8/8, matched frozen random8 on identical targets",
      "prospective_secondary":"7+/8",
      "historical_window_chosen_post_hoc":True,
      "success_proven":False,
      "events_total_from_full_days":len(events),
      "opportunities":n,"unique_draw_targets":unique_targets,
      "observed_8of8":win8,"random_8of8":rng8,
      "expected_8of8":round(n*p8,4),
      "observed_7plus":win7,"random_7plus":rng7,
      "expected_7plus":round(n*p7,4),
      "p8_per_ticket":p8,"p7_per_ticket":p7,
      "events_overlap_and_are_not_independent":True,
      "incomplete_days":partial,
      "broken_rows":len(broken),"duplicate_rows":len(duplicate),
      "per_day":date_summary}

def run(full,incomplete,broken,duplicate):
    events=generate_events(full)
    # Also allow partial days as targets only when supplied separately; primary
    # run uses complete days to avoid unverifiable missing-target censoring.
    targets={day_index(day,dr["time"]):dr for day,seq in full.items() for dr in seq}
    historic_dates={d for d in full if d<=HIST_END}
    future_dates=sorted(d for d in full if d>=START)[:N_DAYS]
    earlier=evaluate_events(events,targets,historic_dates)
    forward=evaluate_events(events,targets,set(future_dates))
    hist=summarize(earlier,historic_dates,events,incomplete,broken,duplicate)
    current=summarize(forward,set(future_dates),events,incomplete,broken,duplicate)
    # Retrospective report should not imply historically locked window.
    hist["validation_status"]="RETROSPECTIVE_DISCOVERY_NOT_INDEPENDENT"
    current["validation_status"]="PROSPECTIVE_PARTIAL" if len(future_dates)<N_DAYS else "PROSPECTIVE_14_DAYS_COMPLETED_NOT_YET_PROOF"
    return events,earlier,forward,hist,current

def _csv(rows,cols):
    s=io.StringIO()
    w=csv.DictWriter(s,fieldnames=cols,extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return s.getvalue()

def build_zip(events,earlier,forward,hist,current):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_TEK_SAYFA_SONUC.txt",(
          "V50 — 8'LI YAKIN AILELER / +7..+12 KOR TEST\n"
          "Tetik: gerçek 5–30 dakika ara ile iki çekilişte en az 8 ortak sayı.\n"
          "Kural: bu ortak sayıların artan ilk sekizi, sadece sonraki +7..+12. slotlarda.\n"
          "Aynı hedefte matematiksel RNG ve olay anında dondurulmuş rastgele kontrol.\n"
          "YAKINLIK KURALI ESKI 72 GÜN incelendikten SONRA secildi; geriye donuk test kanit DEĞİL.\n"
          f"Yeni tam gün: {current['full_days_tested']}/14\n"
          f"Yeni hedef fırsatı: {current['opportunities']}\n"
          f"Yeni TAM 8/8: {current['observed_8of8']}, kontrol {current['random_8of8']}, teorik {current['expected_8of8']}\n"
          f"Yeni EN AZ 7/8: {current['observed_7plus']}, kontrol {current['random_7plus']}, teorik {current['expected_7plus']}\n"
          f"Geçmiş TAM 8/8: {hist['observed_8of8']}, kontrol {hist['random_8of8']}, teorik {hist['expected_8of8']}\n"
          f"Geçmiş EN AZ 7/8: {hist['observed_7plus']}, kontrol {hist['random_7plus']}, teorik {hist['expected_7plus']}\n"
          "Uyarı: Aynı hedefe birden fazla benzer aile düşebilir; başarı için "
          "yeni günlerde ayrı doğrulama, gün bazlı kıyas gerekir.\n"))
        z.writestr("01_GECMIS_KESIF_OZET.json",json.dumps(hist,ensure_ascii=False,indent=2,default=str))
        z.writestr("02_YENI14_GUN_DURUM.json",json.dumps(current,ensure_ascii=False,indent=2,default=str))
        z.writestr("03_YENI_TEST_HEDEF_SONUCLARI.csv",_csv(forward,
          ["date","time","draw_id","lag","trigger_date","trigger_id",
           "trigger_gap","shared_at_trigger","frozen_ticket","fixed_random",
           "hits","control_hits","win8","random8","win7","random7"]))
        z.writestr("04_YENI_TEST_GUN_GUN.csv",_csv(current["per_day"],
          ["day","targets","unique_draws","win8","random8","win7","random7"]))
        z.writestr("05_GECMIS_HER_HEDEF.csv",_csv(earlier,
          ["date","time","draw_id","lag","trigger_date","trigger_id",
           "trigger_gap","shared_at_trigger","frozen_ticket","fixed_random",
           "hits","control_hits","win8","random8","win7","random7"]))
        z.writestr("06_YAKIN_TETIKLEYICILER.csv",_csv(events,
          ["day","first_id","trigger_id","first_time","second_time",
           "near_gap","shared_size","ticket","random_ticket"]))
        z.writestr("07_METOT_VE_LIMITLER.txt",
          "Tüm aileler tam günlerde ve gerçek 5-dakika aralıklarında oluşturulur.\n"
          "Gün içinde 01:02-07:02 arası 6 saatlik kapanış bir yakınlık sayılmaz.\n"
          "Takip edilen +7..+12 resmi çekiliş slotlarıdır, her biri 5 dakika demek olmayabilir.\n"
          "Aynı hedef birden fazla aday tarafından test edilebilir: bağımsızlık varsaymayın.\n"
          "Geçmiş eğitim bulguları çoklu yöntem denenerek elde edildi ve bağımsız kor test değildir.\n"
          "Günlük sonuçlarda 14 gün boyunca iyileşme tutarlı değilse üstünlük iddia etmeyin.\n"
          "Ek günlerde ayrık örneklem ve çoklu-sınama düzeltmesi gereklidir.\n")
    return buf.getvalue()

def load_and_analyze(source):
    full,incomplete,broken,duplicate=parse_draws(Path(source))
    result=run(full,incomplete,broken,duplicate)
    return result

def _selftest():
    assert len(SLOTS)==217
    assert day_index("2026-10-15","07:02")-day_index("2026-10-15","01:02")==1
    assert day_index("2026-10-15","23:57")+1==day_index("2026-10-16","00:02")
    def fake(d,start):
        data=[]
        for i,t in enumerate(SLOTS):
            nums=frozenset(range(1,21)) if i in (0,1,9) else frozenset(range(61,81))
            data.append({"day":str(d),"time":t,"id":start+i,"nums":nums})
        return data
    fd={date(2026,10,14):fake(date(2026,10,14),9000)}
    ev=generate_events(fd)
    core=[e for e in ev if e["first_id"]==9000 and e["trigger_id"]==9001]
    assert len(core)==1 and core[0]["ticket"]==tuple(range(1,9))
    lookup={day_index(d,x["time"]):x for d,rs in fd.items() for x in rs}
    hits=evaluate_events(core,lookup,{date(2026,10,14)})
    assert len(hits)==6 and hits[0]["lag"]==7 and hits[1]["lag"]==8
    assert hits[0]["win8"]==0 and hits[1]["win8"]==1
    frozen=generate_events(fd)
    fd[date(2026,10,14)][8]["nums"]=frozenset(range(31,51))
    assert [e for e in generate_events(fd) if e["first_id"]==9000
            and e["trigger_id"]==9001] == core, "future target leaked to predictions"
    result=run(fd,{},[],[])
    z=build_zip(*result)
    with zipfile.ZipFile(io.BytesIO(z)) as archive:
        assert len(archive.namelist())==8
    print("PASS V50: frozen K8; +7..+12 slots; no future leakage; 1-day ZIP; RNG baseline")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="veri.txt")
    p.add_argument("--output-dir",default="v50_artifacts")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:
        _selftest()
        return
    result=load_and_analyze(a.source)
    target=Path(a.output_dir)
    target.mkdir(parents=True,exist_ok=True)
    outfile=target/"V50_8LI_7_12_YAKINLIK_TEK_RAPOR.zip"
    outfile.write_bytes(build_zip(*result))
    print(json.dumps({"zip":str(outfile),"historical":result[3],
                      "future":result[4]},ensure_ascii=False,default=str))

if __name__=="__main__":
    main()
