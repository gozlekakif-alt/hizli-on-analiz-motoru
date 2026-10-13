# -*- coding: utf-8 -*-
"""V10 aileler arasi sıra / nobet degisimi: salt-okunur arastirma.
Aileler ayni cekiliste gorunurse aralarinda siralama VAR sayilmaz.
Desenler yalnizca secilen gunden ONCEKI gunlerle egitilir.
"""
from collections import Counter, defaultdict
from datetime import datetime


def family_order_events(draws, labels, through_day):
    """Find complete appearances of the indexed 5-10-number families."""
    masks = []
    for label in labels:
        try:
            ns = tuple(int(n) for n in label.split("-"))
            if 5 <= len(ns) <= 10 and len(set(ns)) == len(ns):
                masks.append((label, sum(1 << (n - 1) for n in ns)))
        except (TypeError, ValueError):
            pass
    events = defaultdict(list)
    for draw in sorted(draws, key=lambda d: (d["dt"], d["no"])):
        if draw["day"] > through_day:
            continue
        draw_mask = sum(1 << (n - 1) for n in draw["nums"])
        active = [label for label, mask in masks if mask & draw_mask == mask]
        if active:
            events[draw["day"]].append({
                "pos": draw["pos"], "no": draw["no"], "time": draw["dt"][11:16],
                "labels": active,
            })
    return dict(events)


def family_order_patterns(events, target_day, max_gap=12, min_days=2):
    """Build chronological A->B and A->B->C patterns on earlier *distinct* days.

    The triple second pass is restricted to prior supported A->B patterns.
    The result is descriptive evidence, not a probability estimate.
    """
    if not 1 <= max_gap <= 36:
        raise ValueError("Aralık 1-36 çekiliş olmalı.")
    if min_days not in (1, 2, 3):
        raise ValueError("Destek 1, 2 veya 3 gün olmalı.")
    pair_days = defaultdict(set)
    pair_hits = Counter()
    pair_last = {}
    earlier = {day: rows for day, rows in events.items() if day < target_day}
    for day, rows in earlier.items():
        for i, left in enumerate(rows):
            for right in rows[i+1:]:
                gap = right["pos"] - left["pos"]
                if gap > max_gap:
                    break
                if gap < 1:
                    continue
                for a in left["labels"]:
                    for b in right["labels"]:
                        if a == b:
                            continue
                        key = (a, b, gap)
                        pair_days[key].add(day)
                        pair_hits[key] += 1
                        pair_last[key] = (day, left["no"], right["no"])
    viable = {key for key, days in pair_days.items() if len(days) >= min_days}
    pair_rows = []
    for (a, b, gap) in viable:
        day, no1, no2 = pair_last[(a,b,gap)]
        pair_rows.append({
            "A": a, "B": b, "Fark": gap,
            "Destek gün": len(pair_days[(a,b,gap)]),
            "Olay": pair_hits[(a,b,gap)],
            "Son örnek": f"{day} #{no1} → #{no2}",
            "Geçmiş günler": ", ".join(sorted(pair_days[(a,b,gap)])),
        })
    pair_rows.sort(key=lambda r: (-r["Destek gün"], -r["Olay"], r["Fark"], r["A"], r["B"]))

    triple_days = defaultdict(set)
    triple_hits = Counter()
    triple_last = {}
    for day, rows in earlier.items():
        for i, left in enumerate(rows):
            for j in range(i+1, len(rows)):
                mid = rows[j]
                gap1 = mid["pos"] - left["pos"]
                if gap1 > max_gap:
                    break
                if gap1 < 1:
                    continue
                for k in range(j+1, len(rows)):
                    right = rows[k]
                    gap2 = right["pos"] - mid["pos"]
                    if gap2 > max_gap:
                        break
                    if gap2 < 1:
                        continue
                    for a in left["labels"]:
                        for b in mid["labels"]:
                            if a == b or (a,b,gap1) not in viable:
                                continue
                            for c in right["labels"]:
                                if c in (a, b):
                                    continue
                                key = (a, b, c, gap1, gap2)
                                triple_days[key].add(day)
                                triple_hits[key] += 1
                                triple_last[key] = (day, left["no"], mid["no"], right["no"])
    triple_rows = []
    for (a,b,c,g1,g2),days in triple_days.items():
        if len(days) < min_days:
            continue
        day,n1,n2,n3 = triple_last[(a,b,c,g1,g2)]
        triple_rows.append({
            "A":a, "B":b, "C":c, "Fark 1":g1, "Fark 2":g2,
            "Destek gün":len(days), "Olay":triple_hits[(a,b,c,g1,g2)],
            "Son örnek":f"{day} #{n1} → #{n2} → #{n3}",
            "Geçmiş günler":", ".join(sorted(days)),
        })
    triple_rows.sort(key=lambda r: (-r["Destek gün"], -r["Olay"],
                                    r["Fark 1"]+r["Fark 2"],r["A"],r["B"],r["C"]))
    return pair_rows, triple_rows


def family_order_matches(events, target_day, pairs, triples, limit=150):
    """Observed sequences on the selected day (NOT a forward prediction)."""
    day_rows = events.get(target_day, [])
    by_pos = {d["pos"]: d for d in day_rows}
    starts = defaultdict(list)
    for row in day_rows:
        for label in row["labels"]:
            starts[label].append(row)
    output = []
    for p in pairs:
        for a in starts.get(p["A"], []):
            b = by_pos.get(a["pos"]+p["Fark"])
            if b and p["B"] in b["labels"]:
                output.append({
                    "Zincir": "A→B", "Aile sırası": f'{p["A"]} → {p["B"]}',
                    "Çekilişler": f'#{a["no"]} → #{b["no"]}',
                    "Aralık": f'+{p["Fark"]}',
                    "Geçmiş destek": p["Destek gün"],
                })
    for p in triples:
        for a in starts.get(p["A"], []):
            b = by_pos.get(a["pos"]+p["Fark 1"])
            c = by_pos.get(a["pos"]+p["Fark 1"]+p["Fark 2"])
            if b and c and p["B"] in b["labels"] and p["C"] in c["labels"]:
                output.append({
                    "Zincir": "A→B→C", "Aile sırası": f'{p["A"]} → {p["B"]} → {p["C"]}',
                    "Çekilişler": f'#{a["no"]} → #{b["no"]} → #{c["no"]}',
                    "Aralık": f'+{p["Fark 1"]}, +{p["Fark 2"]}',
                    "Geçmiş destek":p["Destek gün"],
                })
    output.sort(key=lambda r:(r["Zincir"]!="A→B→C",-r["Geçmiş destek"],r["Çekilişler"]))
    return output[:limit]


def family_order_targets(events, target_day, pairs, triples, now, moment_fn):
    """Live proposals after observed trigger(s); no recorded or past target slots."""
    by_pos = {d["pos"]: d for d in events.get(target_day, [])}
    starts = defaultdict(list)
    for row in by_pos.values():
        for label in row["labels"]:
            starts[label].append(row)
    out = {}
    def add(stage, target_label, pos, support, gap_label, trigger_no, example, evidence):
        if not 1 <= pos <= 217 or pos in by_pos:
            return
        target_dt=moment_fn(target_day,pos)
        if target_dt <= now:
            return
        rec={
            "Aşama": stage, "Aile": target_label, "Hedef sıra":pos,
            "Hedef saat":target_dt.strftime("%H:%M"), "Destek gün":support,
            "Ritim":gap_label, "Tetikleyen":trigger_no,
            "Geçmiş örnek":example, "Geçmiş günler":evidence,
            "moment":target_dt.isoformat(timespec="minutes"),
        }
        key=(pos,target_label)
        old=out.get(key)
        if old is None or (stage=="A→B→C" and old["Aşama"]!="A→B→C") or (
            stage==old["Aşama"] and support>old["Destek gün"]
        ):
            out[key]=rec
    for p in pairs:
        for a in starts.get(p["A"], []):
            pos=a["pos"]+p["Fark"]
            add("A→B",p["B"],pos,p["Destek gün"],
                f'+{p["Fark"]}',f'#{a["no"]}: {p["A"]}',p["Son örnek"],p["Geçmiş günler"])
    for p in triples:
        for a in starts.get(p["A"], []):
            b=by_pos.get(a["pos"]+p["Fark 1"])
            if b and p["B"] in b["labels"]:
                pos=b["pos"]+p["Fark 2"]
                add("A→B→C",p["C"],pos,p["Destek gün"],
                    f'+{p["Fark 1"]} → +{p["Fark 2"]}',
                    f'#{a["no"]} → #{b["no"]}: {p["A"]} → {p["B"]}',
                    p["Son örnek"],p["Geçmiş günler"])
    return sorted(out.values(),
                  key=lambda r:(r["Hedef sıra"],r["Aşama"]!="A→B→C",
                                -r["Destek gün"],r["Aile"]))
