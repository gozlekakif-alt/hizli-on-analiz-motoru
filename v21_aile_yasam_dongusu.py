# -*- coding: utf-8 -*-
"""V21: 217-slot family life-cycle study, sizes 2..10.

Every repeated family IN ONE DAY is discovered exactly from pairwise
intersections of its observed 20-ball draws. This is lossless for support >=2:
every repeated set is contained in the intersection of two distinct draws.
Singles (support=1) are deliberately not materialized: even one draw has
sum(C(20,k), k=2..10) = 616,665 families (too large per draw).

Never interpret unordered published balls as physical extraction order.
The clock has 13 night draws (00:02..01:02), a six-hour no-draw interval,
then 204 draws (07:02..23:57). The 01:02 standalone draw is NOT a 12-draw hour.

Descriptive family/core/satellite selection uses known future draws and is
NOT a prediction. Walk-forward 6->6 selection only uses the first six draws.
"""
from __future__ import annotations
import argparse
import csv
import io
import json
import math
import random
import heapq
import zipfile
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from statistics import mean

from v11_arastirma import read_draws

SIZES = tuple(range(2, 11))
CORE_SIZES = (2, 3, 4)
CLOCK_HOURS = (0,) + tuple(range(7, 24))
HOUR_STARTS = (1,) + tuple(14 + 12 * h for h in range(17))


def clock(pos):
    if not 1 <= pos <= 217:
        raise ValueError("Günlük sıra 1..217 olmalı")
    minute = 2 + 5 * (pos - 1) if pos <= 13 else 422 + 5 * (pos - 14)
    return f"{minute // 60:02d}:{minute % 60:02d}", minute


def hour_label(pos):
    if pos == 13:
        return "01:02 (tek çekiliş)"
    if pos <= 12:
        return "00:02-00:57"
    return f"{7 + (pos - 14) // 12:02d}:02-{7 + (pos - 14) // 12:02d}:57"


def key(nums):
    return "-".join(f"{n:02d}" for n in nums)


def p_family(k):
    return math.prod((20 - i) / (80 - i) for i in range(k))


def group_full_days(draws):
    byday = defaultdict(dict)
    for d in draws:
        if d["pos"] in byday[d["day"]]:
            raise ValueError("Tekrarlanan gün/sıra kaydı")
        byday[d["day"]][d["pos"]] = d
    full, incomplete = [], []
    for date, slots in sorted(byday.items()):
        if len(slots) == 217 and set(slots) == set(range(1, 218)):
            full.append((date, [slots[p] for p in range(1, 218)]))
        else:
            incomplete.append((date, len(slots)))
    return full, incomplete


def recurrent_day_families(day_draws, min_k=2, max_k=10):
    """EXACT occurrences for all k-families with >=2 distinct draws.

    For every pair of draw sets A,B, enumerate all k-subsets of A intersect B.
    Any recurring k-family occurs in some such intersection; OR-ing bitmasks
    recovers *all* of its observed slots (not merely the first two). Never
    generates k-subsets seen only once.
    """
    if len({r["pos"] for r in day_draws}) != len(day_draws):
        raise ValueError("Duplicate draw positions")
    observations = [(d["pos"], d["mask"]) for d in day_draws]
    found = {k: {} for k in range(min_k, max_k + 1)}
    for i, (pi, mi) in enumerate(observations):
        first_bit = 1 << (pi - 1)
        for pj, mj in observations[i + 1:]:
            common = mi & mj
            if common.bit_count() < min_k:
                continue
            nums = tuple(n for n in range(1, 81) if common & (1 << (n - 1)))
            hit = first_bit | (1 << (pj - 1))
            for k in range(min_k, min(max_k, len(nums)) + 1):
                row = found[k]
                for fam in combinations(nums, k):
                    row[fam] = row.get(fam, 0) | hit
    return found


def bit_positions(mask):
    out = []
    while mask:
        lowest = mask & -mask
        out.append(lowest.bit_length())
        mask ^= lowest
    return out


def family_row(date, size, fam, mask, day_draws):
    positions = bit_positions(mask)
    mins = [clock(pos)[1] for pos in positions]
    pauses = [positions[i] - positions[i - 1] for i in range(1, len(positions))]
    real_pauses = [mins[i] - mins[i - 1] for i in range(1, len(mins))]
    hcount = Counter(hour_label(pos) for pos in positions)
    samehour = sorted(hcount.items(), key=lambda x: (-x[1], x[0]))
    return {
        "Tarih": date, "Boyut": size, "Aile": key(fam),
        "Aile tam çıkış": len(positions), "İlk sıra": positions[0],
        "İlk saat": clock(positions[0])[0],
        "Son sıra": positions[-1], "Son saat": clock(positions[-1])[0],
        "Aynı gün farklı saat dilimi": len(hcount),
        "En yoğun saat": samehour[0][0], "Bu saatte çıkış": samehour[0][1],
        "En kısa ara çekiliş": min(pauses) if pauses else "",
        "En uzun ara çekiliş": max(pauses) if pauses else "",
        "En kısa gerçek dakika": min(real_pauses) if real_pauses else "",
        "En uzun gerçek dakika": max(real_pauses) if real_pauses else "",
        "Saat dağılımı": ";".join(f"{a}:{b}" for a, b in sorted(hcount.items())),
        "Göründüğü sıralar": ",".join(map(str, positions)),
        "Adil RNG günlük beklenen": round(217 * p_family(size), 6),
    }


def daily_study(date, day_draws, top_per_size=10, top_cores=10):
    found = recurrent_day_families(day_draws)
    sizes, tops, cores = [], [], []
    slot_to_draw = {d["pos"]: d for d in day_draws}
    for k in SIZES:
        rows = found[k]
        ordered = heapq.nsmallest(
            top_per_size, rows.items(), key=lambda a: (-a[1].bit_count(), a[0])
        )
        max_repeat = max((m.bit_count() for m in rows.values()), default=0)
        sizes.append({
            "Tarih": date, "Boyut": k, "En az iki kez çıkan farklı aile": len(rows),
            "En çok tekrar": max_repeat, "RNG aile başına beklenen": round(217 * p_family(k), 7),
            "Yöntem": "Gün içi tüm yinelenen altkümeler; eksiksiz",
        })
        for fam, mask in ordered:
            tops.append(family_row(date, k, fam, mask, day_draws))
        if k not in CORE_SIZES:
            continue
        for fam, mask in ordered[:top_cores]:
            positions = bit_positions(mask)
            companions = Counter()
            different_surroundings = set()
            for pos in positions:
                outside = set(slot_to_draw[pos]["nums"]) - set(fam)
                companions.update(outside)
                different_surroundings.add(tuple(sorted(outside)))
            satellites = sorted(companions.items(), key=lambda a: (-a[1], a[0]))
            candidates = satellites[:10]
            cores.append({
                "Tarih": date, "Çekirdek boyutu": k, "Merkez çekirdek": key(fam),
                "Çekirdek tam çıkış": len(positions),
                "Değişen farklı çevre kadrosu": len(different_surroundings),
                "Her seferinde çevredeki sayı": 20 - k,
                "En sık 10 eşlikçi": ";".join(f"{n}:{c}" for n, c in candidates),
                "En güçlü eşlikçi": candidates[0][0] if candidates else "",
                "En güçlü eşlikçi beraber çıkış": candidates[0][1] if candidates else 0,
                "RNG çekirdek mevcutken tek eşlikçi olasılığı":
                    round((20 - k) / (80 - k), 6),
                "Çekirdek sıraları": ",".join(map(str, positions)),
                "Gerçek saatler": ",".join(clock(p)[0] for p in positions),
                "Görünen saatler": ";".join(
                    f"{h}:{v}" for h, v in sorted(Counter(hour_label(p) for p in positions).items())
                ),
                "Yorum": "Geçmişe dönük aile profili; geleceğe önceden tahmin değildir",
            })
    return sizes, tops, cores


def read_catalog(text):
    catalog = {}
    for r in csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=";"):
        nums = tuple(sorted(int(n) for n in r["Aile"].split("-")))
        size = int(r["Boyut"])
        if size not in SIZES or len(nums) != size or len(set(nums)) != size:
            raise ValueError("Katalogda hatalı aile: " + r["Aile"])
        catalog[key(nums)] = (size, nums, sum(1 << (n - 1) for n in nums))
    return catalog


def catalog_study(full_days, catalog):
    profiles = []
    for label, (k, nums, mask) in sorted(catalog.items()):
        hours = Counter()
        days = 0
        total = 0
        day_repeats = 0
        gap_draws = Counter()
        two_plus_days = 0
        first = last = ""
        for date, draws in full_days:
            hits = [d for d in draws if d["mask"] & mask == mask]
            if not hits:
                continue
            days += 1
            total += len(hits)
            day_repeats += max(0, len(hits) - 1)
            two_plus_days += len(hits) >= 2
            first = first or date
            last = date
            for d in hits:
                hours[hour_label(d["pos"])] += 1
            for a, b in zip(hits, hits[1:]):
                gap_draws[b["pos"] - a["pos"]] += 1
        peak = sorted(hours.items(), key=lambda a: (-a[1], a[0]))
        gap = sorted(gap_draws.items(), key=lambda a: (-a[1], a[0]))
        profiles.append({
            "Aile": label, "Boyut": k, "Görünen tam gün sayısı": days,
            "Tam birlikte çıkış": total, "Aynı gün tekrar fazlası": day_repeats,
            "Günde en az 2 tam çıkış": two_plus_days,
            "İlk gün": first, "Son gün": last,
            "En yoğun saat": peak[0][0] if peak else "",
            "Bu saatte tam çıkış": peak[0][1] if peak else 0,
            "En yaygın sıra aralığı": gap[0][0] if gap else "",
            "Bu aralıktaki tekrar": gap[0][1] if gap else 0,
            "Saat dökümü": ";".join(f"{a}:{b}" for a, b in sorted(hours.items())),
            "RNG beklenen 72 gün": round(sum(len(v) for _, v in full_days) * p_family(k), 6),
            "Not": "Katalog geçmiş verilerden seçildi; seçilim yanlılığı olabilir",
        })
    return profiles


def catalog_core_variants(catalog, profiles, minimum_variants=3):
    act = {r["Aile"]: r for r in profiles}
    indexed = defaultdict(list)
    for label, (k, nums, mask) in catalog.items():
        for core_size in CORE_SIZES:
            if core_size >= k:
                continue
            for core in combinations(nums, core_size):
                indexed[core].append((label, tuple(n for n in nums if n not in core)))
    output = []
    for core, members in indexed.items():
        if len(members) < minimum_variants:
            continue
        active = sum(act[label]["Tam birlikte çıkış"] for label, _ in members)
        output.append({
            "Çekirdek": key(core), "Çekirdek boyutu": len(core),
            "Katalogda farklı çevreli aile": len(members),
            "Katalog ailelerinin toplam tarihsel tam çıkışı": active,
            "Değişen çevre örnekleri": ";".join(
                f"{label}[+{key(other)}]" for label, other in
                sorted(members, key=lambda e: (-act[e[0]]["Tam birlikte çıkış"], e[0]))[:15]
            ),
            "Kapsam": "Katalog varyantları; tüm teorik aileler değildir",
        })
    return sorted(output, key=lambda r: (
        -r["Katalogda farklı çevreli aile"],
        -r["Katalog ailelerinin toplam tarihsel tam çıkışı"], r["Çekirdek"]
    ))


def hour_frozen_prediction(first, k):
    """Choose most repeated k-core using only first SIX draws of the hour."""
    mask = defaultdict(int)
    for i, a in enumerate(first):
        for j, b in enumerate(first[i+1:], i+1):
            overlap = a["mask"] & b["mask"]
            if overlap.bit_count() < k:
                continue
            nums = tuple(n for n in range(1, 81) if overlap & (1 << (n-1)))
            for fam in combinations(nums, k):
                mask[fam] |= (1 << i) | (1 << j)
    if not mask:
        fam = tuple(sorted(first[-1]["nums"])[:k])
        return fam, 1
    fam, bits = min(mask.items(), key=lambda a: (-a[1].bit_count(), a[0]))
    return fam, bits.bit_count()


def forward_test(full_days, train_days=36):
    """Strictly prospective within-hour 6->6. The rule is predeclared, no fitting."""
    detail = []
    summary = defaultdict(lambda: Counter())
    for di, (date, draws) in enumerate(full_days):
        indexed = {x["pos"]: x for x in draws}
        for hour_id, start in enumerate(HOUR_STARTS):
            first = [indexed[p] for p in range(start, start+6)]
            last = [indexed[p] for p in range(start+6, start+12)]
            for k in CORE_SIZES:
                fam, support = hour_frozen_prediction(first, k)
                r = random.Random(int(date.replace("-", ""))*1000 + start*31 + k)
                control = tuple(sorted(r.sample(range(1, 81), k)))
                mask = sum(1 << (n-1) for n in fam)
                control_mask = sum(1 << (n-1) for n in control)
                exact = sum((d["mask"] & mask) == mask for d in last)
                rnd = sum((d["mask"] & control_mask) == control_mask for d in last)
                partial = sum((d["mask"] & mask).bit_count() == k-1 for d in last)
                phase = "Öğrenme" if di < train_days else "Ayrı test"
                detail.append({
                    "Tarih": date, "Dönem": phase, "Saat": clock(start)[0],
                    "İlk6 sonu sıra": start + 5, "Hedef sıralar": f"{start+6}-{start+11}",
                    "Boyut": k, "Önceden seçilen çekirdek": key(fam),
                    "İlk6 tam tekrar": support, "Son6 çekiliş": 6,
                    "Son6 tam isabet": exact, "Son6 k-1 isabet": partial,
                    "Kontrol ailesi": key(control), "Kontrol son6 tam": rnd,
                    "RNG son6 tam beklenen": round(6*p_family(k), 7),
                    "Kural": "Yalnız ilk6 içinde en çok tekrar eden aile; eşitlikte küçük sıra",
                })
                agg = summary[(phase, k)]
                agg["Saatlik tahmin"] += 1
                agg["Gerçek hedef"] += 6
                agg["Tam isabet"] += exact
                agg["Kontrol tam"] += rnd
                agg["Yakın k-1"] += partial
    aggrows = []
    for (phase,k),v in sorted(summary.items()):
        aggrows.append({
            "Dönem": phase, "Boyut": k,
            **dict(v), "RNG beklenen tam":
                round(v["Gerçek hedef"]*p_family(k), 4),
            "Tahmin tam oran": round(v["Tam isabet"]/v["Gerçek hedef"], 6),
            "Rastgele kontrol tam oran":
                round(v["Kontrol tam"]/v["Gerçek hedef"], 6),
            "Sonuç": "Örneklem dışı üstünlük ayrı kanıt gerektirir"
        })
    return detail, aggrows


def csv_bytes(rows):
    if not rows:
        return b""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]), extrasaction="ignore",
                            delimiter=";", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


def run_study(text, catalog_text, max_days=None, top=10):
    draws, errors = read_draws(text)
    if errors:
        raise ValueError(f"Hatalı veri.txt çekilişleri: {errors[:5]}")
    full, incomplete = group_full_days(draws)
    if max_days is not None:
        full = full[-max_days:]
    if not full:
        raise ValueError("Hiç tam 217 çekilişlik gün yok")
    catalog = read_catalog(catalog_text)
    dayrows, topfamilies, cores = [], [], []
    for date, records in full:
        a,b,c = daily_study(date, records, top, top)
        dayrows.extend(a);topfamilies.extend(b);cores.extend(c)
    profiles = catalog_study(full, catalog)
    variants = catalog_core_variants(catalog, profiles)
    predictions, perf = forward_test(full, min(36, len(full)//2))
    meta = {
        "Gün sayısı": len(full), "İlk gün": full[0][0], "Son gün": full[-1][0],
        "Çekiliş": len(full)*217, "Saatlik pencere": len(full)*18,
        "Katalog aile": len(catalog), "Kapsam boyutları": list(SIZES),
        "Gün içi tekrarlanan aileler": {
            str(k): sum(int(r["En az iki kez çıkan farklı aile"])
                        for r in dayrows if r["Boyut"] == k) for k in SIZES
        },
        "Dahil edilmeyen eksik günler": incomplete,
        "Metot": "Aynı gün en az 2 defa görülen k=2..10 aileler TAM; "
                 "gün içinde yalnız bir kez görülenler listelenmez. "
                 "Katalog dosyasındaki tüm kayıtlar günler boyunca TAM taranır.",
        "Not": "Eşlikçi ve çekirdek analizleri geriye dönük; "
               "ileri test sonuçları kupon başarısı değildir.",
    }
    return {
        "ozet.json": json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8"),
        "gun_boyut_ozetleri.csv": csv_bytes(dayrows),
        "gunluk_en_cok_tekrarlanan_aileler.csv": csv_bytes(topfamilies),
        "cekirdek_ve_degisen_cevreler.csv": csv_bytes(cores),
        "kayitli_1131_aile_tam_gecmis.csv": csv_bytes(profiles),
        "kayitli_ailelerin_ortak_cekirdekleri.csv": csv_bytes(variants),
        "ilk6_son6_ongoru_denekleri.csv": csv_bytes(predictions),
        "ilk6_son6_kor_test_ozeti.csv": csv_bytes(perf),
    }


def zip_results(parts, path):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as out:
        for name, data in parts.items():
            out.writestr(name, data)


def main():
    a=argparse.ArgumentParser(description="V21 — 217 çekilişte 2..10 aile yaşam döngüsü")
    a.add_argument("--data", default="veri.txt")
    a.add_argument("--catalog", default="v10_aileler.csv")
    a.add_argument("--output", default="V21_AILELER_TUM_GUNLER.zip")
    a.add_argument("--max-days", type=int, default=None,
                   help="Hızlı kontrol için sadece son N tam günü işle")
    a.add_argument("--top", type=int, default=10)
    args=a.parse_args()
    parts=run_study(Path(args.data).read_text(encoding="utf-8-sig"),
                    Path(args.catalog).read_text(encoding="utf-8-sig"),
                    args.max_days, args.top)
    zip_results(parts,args.output)
    report=json.loads(parts["ozet.json"])
    print("V21_OK",report["Gün sayısı"],report["Çekiliş"],
          report["Katalog aile"],report["Gün içi tekrarlanan aileler"])
    print("DOSYA",args.output)


if __name__ == "__main__":
    main()
