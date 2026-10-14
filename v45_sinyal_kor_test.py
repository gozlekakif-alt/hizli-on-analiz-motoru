#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V45: pre-registered 14-new-full-day prospective Hızlı On signal audit.
Never inspects the target result until after the candidate lists are frozen.
Existing projects and veri.txt remain unchanged.
"""
from __future__ import annotations
import argparse
import collections
import csv
import hashlib
import json
import math
import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path

START = date(2026, 10, 14)  # immutable prospective boundary
TARGET_DAYS = 14
RE = re.compile(r"^(\d+);(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2});([\d,\s]+)$")
SLOTS = (
    [f"00:{2+5*i:02d}" for i in range(12)]
    + ["01:02"]
    + [f"{(422+5*i)//60:02d}:{(422+5*i)%60:02d}" for i in range(204)]
)
assert len(SLOTS) == len(set(SLOTS)) == 217
MODELS = {
    "LAG9_45DK_CARRY20": 20,
    "LAG1_KONTROL20": 20,
    "LAG12_KONTROL20": 20,
    "AYNA_ONCEKI20": 20,
    "SON6_SICAK10": 10,
    "SON6_SOGUK10": 10,
    "SON6_SICAK20": 20,
    "SON6_SOGUK20": 20,
    "SON72_SICAK20": 20,
    "SON72_SOGUK20": 20,
    "SAAT_ILK6_SICAK10": 10,
    "SAAT_ILK6_SOGUK20": 20,
    "SAAT_ILK6_BANT_TERS20": 20,
    "BEKLEYEN_UZUN20": 20,
    "AILE_IKILI_ESLIK20": 20,
    "AILE_UCLU_ESLIK20": 20,
    "RASTGELE10_KONTROL": 10,
    "RASTGELE20_KONTROL": 20,
}
PRIMARY = ("LAG9_45DK_CARRY20", "SAAT_ILK6_SOGUK20")
# Others are secondary, not independent discoveries: family proxy ≠ full epizot model.

def parse_draws(path: Path):
    dates = collections.defaultdict(dict)
    broken, duplicate, seen_id = [], [], set()
    for lineno, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if ";" not in raw:
            continue
        m = RE.fullmatch(raw.strip())
        if not m:
            broken.append(lineno)
            continue
        drid, dd, mm, yyyy, hh, minute, numtxt = m.groups()
        try:
            d = date(int(yyyy), int(mm), int(dd))
            nums = tuple(int(x.strip()) for x in numtxt.split(","))
        except ValueError:
            broken.append(lineno)
            continue
        clock = f"{hh}:{minute}"
        if len(nums) != 20 or len(set(nums)) != 20 or any(n < 1 or n > 80 for n in nums) or clock not in SLOTS:
            broken.append(lineno)
            continue
        ident = int(drid)
        if clock in dates[d] or ident in seen_id:
            duplicate.append(lineno)
            continue
        seen_id.add(ident)
        dates[d][clock] = {"id": ident, "day": d.isoformat(), "time": clock,
                           "nums": frozenset(nums)}
    full = {}
    incomplete = {}
    for d, stamps in sorted(dates.items()):
        if len(stamps) == 217 and set(stamps) == set(SLOTS):
            full[d] = [stamps[t] for t in SLOTS]
        else:
            incomplete[d.isoformat()] = {"count": len(stamps), "missing": 217-len(stamps)}
    return full, incomplete, broken, duplicate

def select_by_counts(draws, k, reverse=False):
    counts = collections.Counter(n for draw in draws for n in draw["nums"])
    if reverse:
        return tuple(sorted(range(1, 81), key=lambda n: (counts[n], n))[:k])
    return tuple(sorted(range(1, 81), key=lambda n: (-counts[n], n))[:k])

def hour_first6(day, idx):
    if 0 <= idx < 12:
        base, pos = 0, idx
    elif idx == 12:
        return None
    else:
        base = 13+((idx-13)//12)*12
        pos = (idx-13)%12
    return day[base:base+6] if pos >= 6 else None

def stable_random(key, k):
    salt = f"v45_pre_registered_2026-10-15|{key}|{k}"
    seed = int.from_bytes(hashlib.sha256(salt.encode()).digest()[:16], "big")
    return tuple(random.Random(seed).sample(range(1, 81), k))

def family_score(day, idx, trip=False):
    # Number-level historical pair/triple-cooccurrence proxies; no future.
    anchors = day[idx-1]["nums"]
    scores = collections.Counter()
    for historic in day[max(0, idx-49):idx-1]:
        m = len(historic["nums"] & anchors)
        factor = (m*(m-1)//2 if trip else m)
        for n in historic["nums"]:
            scores[n] += factor
    return tuple(sorted(range(1, 81), key=lambda n: (-scores[n], n))[:20])

def long_wait(day, idx):
    gaps = {}
    for n in range(1, 81):
        last = next((j for j in range(idx-1, -1, -1) if n in day[j]["nums"]), None)
        gaps[n] = idx if last is None else idx-1-last
    # A deterministic, frozen hypothesis, not "overdue numbers are likelier."
    return tuple(sorted(gaps, key=lambda n: (-gaps[n], n))[:20])

def band_reversal(first6):
    count = collections.Counter(n for row in first6 for n in row["nums"])
    band_load = {b: sum(count[n] for n in range(b*10+1, b*10+11))
                 for b in range(8)}
    quota = [2]*8
    for b in sorted(range(8), key=lambda x: (band_load[x], x))[:4]:
        quota[b] += 1
    out = []
    for b in range(8):
        out += sorted(range(b*10+1, b*10+11), key=lambda n: (-count[n], n))[:quota[b]]
    assert len(out) == len(set(out)) == 20
    return tuple(out)

def candidates(day, idx):
    """Return only predictions computed from day[0:idx], never day[idx]."""
    output = {}
    prev = day[:idx]
    target_key = f"{day[idx]['day']} {day[idx]['time']} #{day[idx]['id']}"
    output["RASTGELE10_KONTROL"] = stable_random(target_key, 10)
    output["RASTGELE20_KONTROL"] = stable_random(target_key, 20)
    if idx >= 1:
        last = prev[-1]["nums"]
        output["LAG1_KONTROL20"] = tuple(sorted(last))
        output["AYNA_ONCEKI20"] = tuple(sorted(81-n for n in last))
    if idx >= 9:
        output["LAG9_45DK_CARRY20"] = tuple(sorted(prev[-9]["nums"]))
    if idx >= 12:
        output["LAG12_KONTROL20"] = tuple(sorted(prev[-12]["nums"]))
    if idx >= 6:
        six = prev[-6:]
        for suffix, k, cold in (
            ("SON6_SICAK10", 10, False),
            ("SON6_SOGUK10", 10, True),
            ("SON6_SICAK20", 20, False),
            ("SON6_SOGUK20", 20, True),
        ):
            output[suffix] = select_by_counts(six, k, cold)
    if idx >= 72:
        output["SON72_SICAK20"] = select_by_counts(prev[-72:], 20)
        output["SON72_SOGUK20"] = select_by_counts(prev[-72:], 20, True)
    first6 = hour_first6(day, idx)
    if first6:
        output["SAAT_ILK6_SICAK10"] = select_by_counts(first6, 10)
        output["SAAT_ILK6_SOGUK20"] = select_by_counts(first6, 20, True)
        output["SAAT_ILK6_BANT_TERS20"] = band_reversal(first6)
    if idx >= 9:
        output["BEKLEYEN_UZUN20"] = long_wait(day, idx)
    if idx >= 49:
        output["AILE_IKILI_ESLIK20"] = family_score(day, idx)
        output["AILE_UCLU_ESLIK20"] = family_score(day, idx, True)
    # A 9-draw distance is 45 minutes only across real five-minute slots.
    # The 01:02-to-07:02 closed period must NOT masquerade as an interval.
    for lag, name in ((1, "LAG1_KONTROL20"),
                      (9, "LAG9_45DK_CARRY20"),
                      (12, "LAG12_KONTROL20")):
        if name in output:
            now = datetime.fromisoformat(day[idx]["day"]+"T"+day[idx]["time"])
            before = datetime.fromisoformat(day[idx-lag]["day"]+"T"+day[idx-lag]["time"])
            if now-before != timedelta(minutes=5*lag):
                output.pop(name)
    for name, values in output.items():
        assert name in MODELS
        assert len(values) == MODELS[name] == len(set(values))
        assert all(1 <= n <= 80 for n in values)
    return output

def model_stats(records, days):
    grouped = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in records:
        grouped[r["model"]][r["day"]].append(r)
    stats = []
    for model, byday in sorted(grouped.items()):
        k = MODELS[model]
        hits = sum(r["hits"] for one in byday.values() for r in one)
        total = sum(map(len, byday.values()))
        daily_deltas = [
            sum(r["hits"] for r in byday[day])/len(byday[day])-k/4
            for day in sorted(byday)
        ]
        avg = hits/total
        n = len(daily_deltas)
        mean = sum(daily_deltas)/n
        se = math.sqrt(sum((x-mean)**2 for x in daily_deltas)/(n-1))/math.sqrt(n) if n>1 else None
        # Plain day-level CI, DESCRIPTIVE, unadjusted; never label as proof.
        ci = None if se is None else [round(mean-2.2*se, 6), round(mean+2.2*se, 6)]
        stats.append({"model": model, "coupon_size": k, "full_days": n, "targets": total,
                      "mean_hits": round(avg, 6), "fair_mean": k/4,
                      "delta_vs_fair": round(avg-k/4, 6),
                      "positive_days": sum(x>0 for x in daily_deltas),
                      "daily_CI95_descriptive": ci})
    # No model accepted automatically; preregistered independent confirmation
    # would also require multiplicity correction and future replication.
    return stats

def write_csv(path, rows, columns):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def run(source, output):
    full, incomplete, broken, duplicates = parse_draws(source)
    eligible = [(d, full[d]) for d in sorted(full) if d >= START]
    chosen = eligible[:TARGET_DAYS]
    records = []
    for d, day in chosen:
        for idx in range(217):
            selected = candidates(day, idx)
            actual = day[idx]["nums"]
            is_second = hour_first6(day, idx) is not None
            for name, picks in selected.items():
                records.append({
                    "day": d.isoformat(), "time": day[idx]["time"],
                    "draw_id": day[idx]["id"], "slot": idx+1,
                    "hour_H7_H12": int(is_second), "model": name,
                    "size": len(picks), "selected_before_result": ",".join(map(str,sorted(picks))),
                    "hits": len(actual.intersection(picks)), "fair": len(picks)/4
                })
    output.mkdir(parents=True, exist_ok=True)
    data_columns = ["day","time","draw_id","slot","hour_H7_H12","model",
                    "size","selected_before_result","hits","fair"]
    write_csv(output/"01_KILITLI_LISTELER_VE_SONUC.csv", records, data_columns)
    rows = model_stats(records, chosen)
    write_csv(output/"02_MODEL_OZET.csv", rows, ["model","coupon_size","full_days",
            "targets","mean_hits","fair_mean","delta_vs_fair","positive_days",
            "daily_CI95_descriptive"])
    daily = []
    for d, _ in chosen:
        dr = [r for r in records if r["day"]==d.isoformat()]
        for model in MODELS:
            x = [r for r in dr if r["model"]==model]
            if x:
                daily.append({"day": d.isoformat(), "model": model, "targets": len(x),
                              "average_hits": round(sum(r["hits"] for r in x)/len(x),6),
                              "vs_fair": round(sum(r["hits"] for r in x)/len(x)-MODELS[model]/4,6)})
    write_csv(output/"03_GUNLUK_RAPOR.csv",daily,["day","model","targets","average_hits","vs_fair"])
    done = len(chosen)
    state = "KOR_TEST_14_GUN_TAMAMLANDI_KANIT_IDDIASI_YOK" if done==14 else "14_GUN_TESTI_HENUZ_TAMAMLANMADI"
    info = {
        "status": state,
        "baseline": "2026-08-01..2026-10-12: retrospective discovery; EXCLUDED FROM NEW TEST",
        "prospective_start": START.isoformat(),
        "registered_limit_first_N_COMPLETE_DAYS": TARGET_DAYS,
        "complete_new_days": done,
        "remaining_days": TARGET_DAYS-done,
        "selected_days": [d.isoformat() for d,_ in chosen],
        "full_historical_days": sum(d<START for d in full),
        "post_start_incomplete": {d:v for d,v in incomplete.items() if d>=START.isoformat()},
        "source_latest_date": max((d.isoformat() for d in list(full)+[date.fromisoformat(x) for x in incomplete]),default=None),
        "bad_lines": len(broken), "duplicate_lines": len(duplicates),
        "primary_hypotheses": PRIMARY, "registered_models": MODELS,
        "policy": "No positive result is certified from old data; at least 14 COMPLETE NEW days and independent replication; 18 model selection multiplicity matters.",
        "method_notes": ["Each day is tested in natural order, using only PREVIOUS draws of that same day; no missing draw is invented.",
                         "The isolated 01:02 result is not a 12-draw hour.",
                         "Daily CIs are descriptive and not adjusted for selection/multiple tests.",
                         "The 14 full days are selected chronologically AFTER 2026-10-13 and then frozen.",
                         "Family pair/triple are coappearance proxies, not the complete historic family life-cycle epizotes.",
                         "Do not interpret 20-number candidate hits as 10/10 real-coupon wins."]
    }
    (output/"00_DURUM_VE_KURALLAR.json").write_text(
        json.dumps(info,ensure_ascii=False,indent=2),encoding="utf-8")
    summary = [
        "HIZLI ON V45 — ONCEDEN DONDURULMUS 14 YENI TAM GUN DENETIMI",
        f"DURUM: {state}",
        f"YENI TAM GUN: {done}/14",
        "DAYANAK: 14.10.2026 ve sonrasindan sonraki ilk 14 tam gun",
        "72 gunluk eski sinyal taramasi GELCEK kaniti olarak SAYILMAZ.",
        "Adil beklenti: 10'lu 2.5, 20'li 5 isabet/cekilis.",
        "Ana hipotezler: 9 cekilis aralikli tekrar; ilk6 soguk20.",
        "Yontemler: sicak, soguk, aile, ayna, bant, bekleme, RNG kontrolleri.",
        "14 gun dolmadan bir isaret basarili ilan edilmeyecek.",
        "",
        "MODEL RAPORU:"
    ]
    for x in rows:
        summary.append(f"{x['model']}: {x['mean_hits']:.4f}/{x['coupon_size']} "
                       f"(adil {x['fair_mean']:.2f}; fark {x['delta_vs_fair']:+.4f}), "
                       f"{x['full_days']} gun")
    (output/"00_TEK_SAYFA_SONUC.txt").write_text("\n".join(summary)+"\n",encoding="utf-8")
    print("\n".join(summary[:10]))
    return info

def selftest():
    from datetime import timedelta
    assert SLOTS[:2] == ["00:02","00:07"]
    assert SLOTS[12]=="01:02" and SLOTS[13]=="07:02" and SLOTS[-1]=="23:57"
    day=[]
    for idx,time in enumerate(SLOTS):
        picked=frozenset(random.Random(1000+idx).sample(range(1,81),20))
        day.append({"id": 62000+idx,"day":"2026-10-14","time":time,"nums":picked})
    for idx in [0,6,9,12,13,20,72,120,216]:
        originals = candidates(day,idx)
        modified = list(day)
        modified[idx] = dict(modified[idx],nums=frozenset(range(1,21)))
        assert candidates(modified,idx)==originals, "LOOKAHEAD BUG"
        assert originals["RASTGELE20_KONTROL"]==candidates(day,idx)["RASTGELE20_KONTROL"]
    assert "LAG9_45DK_CARRY20" not in candidates(day,13)
    assert "LAG1_KONTROL20" not in candidates(day,13)
    assert "LAG9_45DK_CARRY20" in candidates(day,22)
    assert hour_first6(day,11) is not None
    assert hour_first6(day,12) is None
    assert hour_first6(day,13) is None
    assert hour_first6(day,19) is not None
    assert sum(1 for i in range(217) if hour_first6(day,i))==18*6
    print("V45 SELFTEST PASSED: 217 slots, target blindness, 18 hours, 10/20 distinct")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--source",default="veri.txt")
    a.add_argument("--output-dir",default="v45_artifacts")
    a.add_argument("--selftest",action="store_true")
    args=a.parse_args()
    if args.selftest:
        selftest()
    else:
        run(Path(args.source), Path(args.output_dir))

if __name__=="__main__":
    main()
