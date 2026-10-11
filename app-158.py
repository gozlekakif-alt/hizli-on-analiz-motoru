# -*- coding: utf-8 -*-
import io
import math
import time
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from itertools import combinations

import numpy as np
import pandas as pd
import requests
import streamlit as st

APP_TITLE = "🧭 Hızlı On — Günler Arası Ritim Merkezi V5.1 (Arrow Fix)"
DEFAULT_RAW_URL = "https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt"

st.set_page_config(page_title="Hızlı On Ritim Merkezi V5.1", page_icon="🧭", layout="wide")
st.title(APP_TITLE)
st.caption(
    "Günler arası karşılaştırma • normal 6’lı • 3+3 özel 6’lı • 10’lu aileler • "
    "+2/+5/+7/+14 gün zincirleri • aynı gün tekrar • +77 küme-eko • canlı takvim"
)

# ============================================================
# SABİTLER / MASKELER
# ============================================================
TRIPLES = np.array(list(combinations(range(1, 81), 3)), dtype=np.int16)
TCOUNT = len(TRIPLES)
TRIPLE_KEYS = (
    TRIPLES[:, 0].astype(np.int32)
    | (TRIPLES[:, 1].astype(np.int32) << 7)
    | (TRIPLES[:, 2].astype(np.int32) << 14)
)
KEY_TO_RANK = np.full(1 << 21, -1, dtype=np.int32)
KEY_TO_RANK[TRIPLE_KEYS] = np.arange(TCOUNT, dtype=np.int32)
POS3 = np.array(list(combinations(range(20), 3)), dtype=np.int16)
P0, P1, P2 = POS3.T

TRI_LO = np.zeros(TCOUNT, dtype=np.uint64)
TRI_HI = np.zeros(TCOUNT, dtype=np.uint64)
for col in range(3):
    vals = TRIPLES[:, col]
    low = vals <= 64
    TRI_LO[low] |= np.left_shift(np.uint64(1), (vals[low] - 1).astype(np.uint64))
    TRI_HI[~low] |= np.left_shift(np.uint64(1), (vals[~low] - 65).astype(np.uint64))


def nums_to_split_mask(nums):
    lo = 0
    hi = 0
    for n in nums:
        if int(n) <= 64:
            lo |= 1 << (int(n) - 1)
        else:
            hi |= 1 << (int(n) - 65)
    return np.uint64(lo), np.uint64(hi)


def split_mask_to_nums(lo, hi):
    out = []
    x = int(lo)
    while x:
        lsb = x & -x
        out.append(lsb.bit_length())
        x ^= lsb
    x = int(hi)
    while x:
        lsb = x & -x
        out.append(64 + lsb.bit_length())
        x ^= lsb
    return out


def triple_name(rank):
    return "-".join(map(str, TRIPLES[int(rank)].tolist()))


def pair_code(a, b):
    if a > b:
        a, b = b, a
    return int(a) * TCOUNT + int(b)


def decode_pair(code):
    return divmod(int(code), TCOUNT)


def pair_coupon(code):
    a, b = decode_pair(code)
    nums = sorted(set(TRIPLES[a].tolist()) | set(TRIPLES[b].tolist()))
    return "-".join(map(str, nums))


def draw_triple_ids(nums):
    n = np.asarray(nums, dtype=np.int32)
    keys = n[P0] | (n[P1] << 7) | (n[P2] << 14)
    return KEY_TO_RANK[keys]


def date_map(records):
    out = defaultdict(list)
    for i, r in enumerate(records):
        out[r[1].date()].append(i)
    return out


def df_bytes(df):
    return df.to_csv(index=False).encode("utf-8-sig")


def _arrow_safe_value(v):
    """Streamlit/pyarrow için object hücrelerini güvenli metne çevir."""
    if v is None:
        return ""
    # pandas / numpy boş değerleri
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    if isinstance(v, datetime):
        return v.strftime("%d.%m.%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d.%m.%Y")
    if isinstance(v, (list, tuple, set)):
        return " | ".join(map(str, v))
    if isinstance(v, dict):
        return " | ".join(f"{k}:{val}" for k, val in v.items())
    if isinstance(v, np.generic):
        return v.item()
    return v


def arrow_safe_df(data):
    """Karışık object kolonlarını Arrow uyumlu hale getirir."""
    if isinstance(data, pd.Series):
        data = data.to_frame()
    elif not isinstance(data, pd.DataFrame):
        data = pd.DataFrame(data)
    df = data.copy()
    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col].dtype):
            vals = df[col].map(_arrow_safe_value)
            # Aynı object kolonda tarih/string/int karışımı Arrow'u düşürmesin.
            df[col] = vals.map(lambda x: "" if x is None else str(x))
    return df


def safe_dataframe(data, *args, **kwargs):
    """st.dataframe için tek güvenli giriş noktası."""
    if kwargs.pop("use_container_width", False):
        kwargs.setdefault("width", "stretch")
    return st.dataframe(arrow_safe_df(data), *args, **kwargs)


def build_zip(files):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            if isinstance(data, str):
                data = data.encode("utf-8-sig")
            z.writestr(name, data)
    return bio.getvalue()


# ============================================================
# VERİ
# ============================================================
@st.cache_data(ttl=90, show_spinner=False)
def fetch_text(url, cache_bust=0):
    sep = "&" if "?" in url else "?"
    r = requests.get(
        f"{url}{sep}_cb={cache_bust}",
        timeout=35,
        headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
    r.raise_for_status()
    return r.text


@st.cache_data(show_spinner=False)
def parse_veri(text):
    rows = []
    seen = set()
    for raw in text.splitlines():
        p = raw.strip().split(";")
        if len(p) != 3:
            continue
        try:
            draw_id = int(p[0].strip())
            dt = datetime.strptime(p[1].strip(), "%d.%m.%Y %H:%M")
            nums = tuple(sorted(int(x.strip()) for x in p[2].split(",") if x.strip()))
        except Exception:
            continue
        if draw_id in seen or len(nums) != 20 or len(set(nums)) != 20:
            continue
        if not all(1 <= n <= 80 for n in nums):
            continue
        seen.add(draw_id)
        lo, hi = nums_to_split_mask(nums)
        rows.append((draw_id, dt, nums, lo, hi))
    rows.sort(key=lambda r: r[1])
    return rows


# ============================================================
# GÜNLER ARASI KARŞILAŞTIRMA
# ============================================================
def analyze_day_pairs(records, day_gaps=(2, 5, 7, 14), progress=None):
    bydate = date_map(records)
    dates = sorted(bydate)
    dset = set(dates)
    rows = []
    gap_acc = defaultdict(lambda: Counter())
    jobs = [(int(g), d, d + timedelta(days=int(g))) for g in sorted(set(day_gaps)) for d in dates if d + timedelta(days=int(g)) in dset]
    total = max(1, len(jobs))

    for z, (gap, d1, d2) in enumerate(jobs, 1):
        I, J = bydate[d1], bydate[d2]
        lo1 = np.array([records[i][3] for i in I], dtype=np.uint64)[:, None]
        hi1 = np.array([records[i][4] for i in I], dtype=np.uint64)[:, None]
        lo2 = np.array([records[j][3] for j in J], dtype=np.uint64)[None, :]
        hi2 = np.array([records[j][4] for j in J], dtype=np.uint64)[None, :]
        il = lo1 & lo2
        ih = hi1 & hi2
        bc = np.bitwise_count(il) + np.bitwise_count(ih)
        maxv = int(bc.max()) if bc.size else 0
        a, b = np.unravel_index(int(np.argmax(bc)), bc.shape)
        best_nums = split_mask_to_nums(il[a, b], ih[a, b])
        # her 1. gün çekilişinin 2. günde bulduğu en yüksek ortaklık ortalaması
        avg_best = float(np.mean(bc.max(axis=1))) if bc.size else 0.0
        r = {
            "Gün Gap": gap,
            "1. Gün": d1,
            "2. Gün": d2,
            "En Büyük Ortak Blok": maxv,
            "6+ Eşleşme": int(np.sum(bc >= 6)),
            "8+ Eşleşme": int(np.sum(bc >= 8)),
            "10+ Eşleşme": int(np.sum(bc >= 10)),
            "Exact 10 Eşleşme": int(np.sum(bc == 10)),
            "12+ Eşleşme": int(np.sum(bc >= 12)),
            "1. Gün Çekiliş Başına Ortalama En İyi Ortaklık": round(avg_best, 3),
            "En İyi 1. Saat": records[I[a]][1].strftime("%H:%M"),
            "En İyi 2. Saat": records[J[b]][1].strftime("%H:%M"),
            "En İyi Ortak Blok": "-".join(map(str, best_nums)),
        }
        rows.append(r)
        acc = gap_acc[gap]
        acc["pairs"] += 1
        acc["6+"] += r["6+ Eşleşme"]
        acc["8+"] += r["8+ Eşleşme"]
        acc["10+"] += r["10+ Eşleşme"]
        acc["exact10"] += r["Exact 10 Eşleşme"]
        acc["12+"] += r["12+ Eşleşme"]
        acc["max_sum"] += maxv
        if progress is not None and (z % 5 == 0 or z == total):
            progress.progress(z / total, text=f"Gün karşılaştırması: {z}/{total}")

    gap_rows = []
    for g in sorted(gap_acc):
        a = gap_acc[g]
        n = max(1, a["pairs"])
        gap_rows.append({
            "Gün Gap": g,
            "Gün Çifti": a["pairs"],
            "6+ Eşleşme": a["6+"],
            "8+ Eşleşme": a["8+"],
            "10+ Eşleşme": a["10+"],
            "Exact 10 Eşleşme": a["exact10"],
            "12+ Eşleşme": a["12+"],
            "Ortalama Günlük Max Ortak Blok": round(a["max_sum"] / n, 3),
        })
    rows.sort(key=lambda r: (-r["10+ Eşleşme"], -r["En Büyük Ortak Blok"], r["Gün Gap"], r["1. Gün"]))
    return {"rows": rows, "gaps": gap_rows}


# ============================================================
# GENEL K'Lİ AİLE RİTİM MOTORU (6 VE 10)
# ============================================================
def family_mask(fam):
    return nums_to_split_mask(fam)


def longest_calendar_chain(dates, gap):
    ds = set(dates)
    best = []
    for d in dates:
        if d - timedelta(days=gap) in ds:
            continue
        chain = []
        x = d
        while x in ds:
            chain.append(x)
            x += timedelta(days=gap)
        if len(chain) > len(best):
            best = chain
    return best


def rhythm_score(active_days, dominant_links, chain_len, consistency, month_count):
    # Sadece tarihsel düzenlilik puanı; tahmin olasılığı değildir.
    p1 = 25 * min(dominant_links, 5) / 5
    p2 = 25 * min(max(0, chain_len - 1), 4) / 4
    p3 = 20 * min(max(consistency, 0.0), 1.0)
    p4 = 15 * min(active_days, 8) / 8
    p5 = 15 * min(month_count, 3) / 3
    return round(p1 + p2 + p3 + p4 + p5, 1)


def _edge_families(records, I, J, k, max_expand, edge_family_cap):
    lo1 = np.array([records[i][3] for i in I], dtype=np.uint64)[:, None]
    hi1 = np.array([records[i][4] for i in I], dtype=np.uint64)[:, None]
    lo2 = np.array([records[j][3] for j in J], dtype=np.uint64)[None, :]
    hi2 = np.array([records[j][4] for j in J], dtype=np.uint64)[None, :]
    il = lo1 & lo2
    ih = hi1 & hi2
    bc = np.bitwise_count(il) + np.bitwise_count(ih)
    rr, cc = np.where((bc >= int(k)) & (bc <= int(max_expand)))

    unique_blocks = set()
    examples = {}
    for a, b in zip(rr.tolist(), cc.tolist()):
        key = (int(il[a, b]), int(ih[a, b]))
        if key not in unique_blocks:
            unique_blocks.add(key)
            examples[key] = (I[a], J[b])

    fams = set()
    fam_example = {}
    truncated = False
    for blo, bhi in unique_blocks:
        nums = split_mask_to_nums(blo, bhi)
        if len(nums) == k:
            it = [tuple(nums)]
        else:
            it = combinations(nums, k)
        for fam in it:
            fam = tuple(fam)
            fams.add(fam)
            if fam not in fam_example:
                fam_example[fam] = examples[(blo, bhi)]
            if len(fams) >= int(edge_family_cap):
                truncated = True
                break
        if truncated:
            break
    return fams, fam_example, truncated


def mine_family_rhythms(
    records,
    k,
    day_gaps=(2, 5, 7, 14),
    max_expand=None,
    min_gap_links=2,
    verify_cap=5000,
    edge_family_cap=180000,
    progress=None,
):
    k = int(k)
    max_expand = int(max_expand if max_expand is not None else k)
    gaps = sorted(set(int(g) for g in day_gaps if int(g) > 0))
    bydate = date_map(records)
    dates = sorted(bydate)
    dset = set(dates)
    jobs = [(g, d, d + timedelta(days=g)) for g in gaps for d in dates if d + timedelta(days=g) in dset]
    total = max(1, len(jobs))

    counts = Counter()  # (family,gap) -> distinct day-edge count
    first_link = {}
    repeated_links = defaultdict(list)
    truncated_edges = []

    for z, (gap, d1, d2) in enumerate(jobs, 1):
        fams, fam_examples, trunc = _edge_families(
            records, bydate[d1], bydate[d2], k, max_expand, edge_family_cap
        )
        if trunc:
            truncated_edges.append((gap, d1, d2))
        for fam in fams:
            key = (fam, gap)
            old = counts[key]
            counts[key] += 1
            i, j = fam_examples[fam]
            link = (d1, d2, records[i][1], records[j][1])
            if old == 0:
                first_link[key] = link
            elif old == 1:
                repeated_links[key] = [first_link.pop(key), link]
            else:
                if len(repeated_links[key]) < 30:
                    repeated_links[key].append(link)
        if progress is not None and (z % 3 == 0 or z == total):
            progress.progress(0.62 * z / total, text=f"{k}’lı aday bağlantıları: {z}/{total}")

    strong_keys = [key for key, n in counts.items() if n >= int(min_gap_links)]
    fam_strength = Counter()
    for fam, gap in strong_keys:
        fam_strength[fam] += counts[(fam, gap)]
    ordered_fams = [f for f, _ in fam_strength.most_common(int(verify_cap))]
    strong_fam_set = set(ordered_fams)

    lo_all = np.array([r[3] for r in records], dtype=np.uint64)
    hi_all = np.array([r[4] for r in records], dtype=np.uint64)
    asof = max(r[1].date() for r in records)
    rows = []
    chains = []
    events = []

    nverify = max(1, len(ordered_fams))
    for z, fam in enumerate(ordered_fams, 1):
        flo, fhi = family_mask(fam)
        ids = np.where(((lo_all & flo) == flo) & ((hi_all & fhi) == fhi))[0].tolist()
        byday_hits = defaultdict(list)
        for i in ids:
            byday_hits[records[i][1].date()].append(i)
        for d in byday_hits:
            byday_hits[d].sort()
        adates = sorted(byday_hits)
        aset = set(adates)
        if len(adates) < 2:
            continue

        gap_counts = {}
        gap_chains = {}
        for g in gaps:
            gc = sum(1 for d in adates if d + timedelta(days=g) in aset)
            gap_counts[g] = gc
            ch = longest_calendar_chain(adates, g)
            gap_chains[g] = ch
            if gc >= int(min_gap_links):
                chains.append({
                    f"{k}’lı Aile": "-".join(map(str, fam)),
                    "Gün Gap": g,
                    "Gap Bağı": gc,
                    "En Uzun Zincir Gün": len(ch),
                    "Zincir": " → ".join(x.strftime("%d.%m.%Y") for x in ch),
                    "İlk Gün": adates[0],
                    "Son Gün": adates[-1],
                })

        best_gap = max(gaps, key=lambda g: (gap_counts[g], len(gap_chains[g]), -g)) if gaps else 0
        best_links = gap_counts.get(best_gap, 0)
        best_chain = gap_chains.get(best_gap, [])
        # selected gap edges relative to number of possible transitions in active dates
        consistency = best_links / max(1, len(adates) - 1)
        months = len({(d.year, d.month) for d in adates})
        score = rhythm_score(len(adates), best_links, len(best_chain), consistency, months)

        today_n = len(byday_hits.get(asof, []))
        due_today = [g for g in gaps if gap_counts[g] >= int(min_gap_links) and asof - timedelta(days=g) in aset]
        future = []
        for g in gaps:
            if gap_counts[g] < int(min_gap_links):
                continue
            nd = adates[-1] + timedelta(days=g)
            if nd >= asof:
                future.append((nd, g))
        if future:
            next_date, next_gap = min(future, key=lambda x: (x[0], x[1]))
            days_to = (next_date - asof).days
        else:
            next_date, next_gap, days_to = "", "", ""

        if due_today:
            status = "✅ BUGÜN GELDİ" if today_n else "🔥 BUGÜN RİTİM PENCERESİ"
        elif isinstance(days_to, int) and days_to == 1:
            status = "⏳ YARIN PENCERE"
        elif isinstance(days_to, int) and 1 < days_to <= 3:
            status = f"⏳ {days_to} GÜN SONRA"
        else:
            status = "TAKİP"

        row = {
            f"{k}’lı Aile": "-".join(map(str, fam)),
            "Toplam Görünüş": len(ids),
            "Aktif Gün": len(adates),
            "Aynı Gün Max": max((len(v) for v in byday_hits.values()), default=0),
            "Aynı Gün 2+ Gün": sum(len(v) >= 2 for v in byday_hits.values()),
            "Aynı Gün 3+ Gün": sum(len(v) >= 3 for v in byday_hits.values()),
            "En Güçlü Gün Gap": best_gap,
            "Gap Tekrar": best_links,
            "En Uzun Aynı-Gap Zinciri": len(best_chain),
            "En Güçlü Zincir": " → ".join(d.strftime("%d.%m.%Y") for d in best_chain),
            "Ritim Tutarlılığı": round(consistency, 3),
            "Tarihsel Ritim Puanı": score,
            "İlk Aktif Gün": adates[0],
            "Son Aktif Gün": adates[-1],
            "Bugün Görünüş": today_n,
            "Bugün Tetik Gap": ",".join(f"+{g}" for g in due_today),
            "Sonraki Pencere": next_date,
            "Sonraki Gap": next_gap,
            "Durum": status,
        }
        for g in gaps:
            row[f"+{g} Gün Bağı"] = gap_counts[g]
            row[f"+{g} Zincir"] = len(gap_chains[g])
        rows.append(row)

        # olaylar: rapor için bütün doğrulanmış görünüşler
        for d, ix in byday_hits.items():
            for i in ix:
                events.append({
                    f"{k}’lı Aile": row[f"{k}’lı Aile"],
                    "Tarih": d,
                    "Saat": records[i][1].strftime("%H:%M"),
                    "Çekiliş": records[i][0],
                })

        if progress is not None and (z % 50 == 0 or z == nverify):
            progress.progress(0.62 + 0.38 * z / nverify, text=f"{k}’lı tam doğrulama: {z}/{len(ordered_fams)}")

    rows.sort(key=lambda r: (-r["Tarihsel Ritim Puanı"], -r["Gap Tekrar"], -r["Aktif Gün"], r[f"{k}’lı Aile"]))
    chains.sort(key=lambda r: (-r["En Uzun Zincir Gün"], -r["Gap Bağı"], r["Gün Gap"], r[f"{k}’lı Aile"]))
    events.sort(key=lambda r: (r["Tarih"], r["Saat"], r[f"{k}’lı Aile"]))

    multi = []
    for r in rows:
        strong_gaps = [g for g in gaps if int(r.get(f"+{g} Gün Bağı", 0)) >= int(min_gap_links)]
        if len(strong_gaps) >= 2:
            multi.append({
                f"{k}’lı Aile": r[f"{k}’lı Aile"],
                "Güçlü Gapler": ", ".join(f"+{g}" for g in strong_gaps),
                "Aktif Gün": r["Aktif Gün"],
                "Tarihsel Ritim Puanı": r["Tarihsel Ritim Puanı"],
                "Son Aktif Gün": r["Son Aktif Gün"],
            })

    due = [r for r in rows if r["Durum"] != "TAKİP"]
    return {
        "rows": rows,
        "chains": chains,
        "events": events,
        "multi": multi,
        "due": due,
        "candidate_keys": len(counts),
        "strong_keys": len(strong_keys),
        "verified": len(rows),
        "truncated_edges": truncated_edges,
        "asof": asof,
        "k": k,
        "gaps": gaps,
        "max_expand": max_expand,
    }


# ============================================================
# 3+3 ÖZEL 6'LI
# ============================================================
def mine_triples_dense(records, max_gap=60, progress=None):
    max_gap = int(max_gap)
    last = np.full(TCOUNT, -999999, dtype=np.int32)
    freq = np.zeros(TCOUNT, dtype=np.uint16)
    gaps = np.zeros((TCOUNT, max_gap + 1), dtype=np.uint16)
    nrec = len(records)
    for pos, r in enumerate(records):
        ids = draw_triple_ids(r[2])
        freq[ids] += 1
        g = pos - last[ids]
        v = (g >= 1) & (g <= max_gap)
        if np.any(v):
            np.add.at(gaps, (ids[v], g[v]), 1)
        last[ids] = pos
        if progress is not None and (pos % 400 == 0 or pos + 1 == nrec):
            progress.progress(0.42 * (pos + 1) / nrec, text=f"3’lü ritimler: {pos+1}/{nrec}")
    body = gaps[:, 1:]
    return freq, body.argmax(axis=1) + 1, body.max(axis=1)


def choose_families(freq, best_gap, best_count, requested_min=7, safe_limit=500):
    threshold = int(requested_min)
    while threshold < 100 and int(np.sum(best_count >= threshold)) > int(safe_limit):
        threshold += 1
    q = np.where(best_count >= threshold)[0]
    order = np.lexsort((q, -freq[q].astype(np.int32), -best_count[q].astype(np.int32)))
    return threshold, q, q[order][: int(safe_limit)]


def mine_pairs_safe(records, selected_families, pair_min_repeat=3, progress=None):
    flag = np.zeros(TCOUNT, dtype=bool)
    flag[selected_families] = True
    active = []
    counts = Counter()
    nrec = len(records)
    for pos, r in enumerate(records):
        ids = draw_triple_ids(r[2])
        arr = ids[flag[ids]]
        active.append(arr.astype(np.int32, copy=False))
        L = len(arr)
        for ii in range(L - 1):
            rest = arr[ii + 1:]
            dis = ((TRI_LO[arr[ii]] & TRI_LO[rest]) == 0) & ((TRI_HI[arr[ii]] & TRI_HI[rest]) == 0)
            rr = rest[dis]
            if len(rr):
                codes = arr[ii].astype(np.int64) * TCOUNT + rr.astype(np.int64)
                counts.update(map(int, codes.tolist()))
        if progress is not None and (pos % 400 == 0 or pos + 1 == nrec):
            progress.progress(0.42 + 0.28 * (pos + 1) / nrec, text=f"3+3 çiftleri: {pos+1}/{nrec}")

    eligible = {c: n for c, n in counts.items() if n >= int(pair_min_repeat)}
    eligible_set = set(eligible)
    pairsets = []
    events = []
    day_hits = defaultdict(lambda: defaultdict(list))

    for idx, arr in enumerate(active):
        local = set()
        L = len(arr)
        for ii in range(L - 1):
            rest = arr[ii + 1:]
            dis = ((TRI_LO[arr[ii]] & TRI_LO[rest]) == 0) & ((TRI_HI[arr[ii]] & TRI_HI[rest]) == 0)
            for b in rest[dis].tolist():
                c = pair_code(int(arr[ii]), int(b))
                if c in eligible_set:
                    local.add(c)
        pairsets.append(local)
        for c in local:
            a, b = decode_pair(c)
            dt = records[idx][1]
            events.append({
                "Çekiliş": records[idx][0], "Tarih": dt.date(), "Saat": dt.strftime("%H:%M"),
                "Aile A": triple_name(a), "Aile B": triple_name(b), "6’lı Kupon": pair_coupon(c),
                "PairCode": c,
            })
            day_hits[c][dt.date()].append(idx)

    pair_rows = []
    for c, n in eligible.items():
        a, b = decode_pair(c)
        dd = day_hits[c]
        dates = sorted(dd)
        pair_rows.append({
            "Aile A": triple_name(a), "Aile B": triple_name(b), "6’lı Kupon": pair_coupon(c),
            "Toplam 6/6": n, "Farklı Gün": len(dates),
            "Aynı Gün Max": max((len(v) for v in dd.values()), default=0),
            "Aynı Gün 2+ Gün": sum(len(v) >= 2 for v in dd.values()),
            "Aynı Gün 3+ Gün": sum(len(v) >= 3 for v in dd.values()),
            "İlk Gün": dates[0] if dates else "", "Son Gün": dates[-1] if dates else "",
        })
    pair_rows.sort(key=lambda r: (-r["Farklı Gün"], -r["Toplam 6/6"], r["6’lı Kupon"]))
    return pair_rows, events, pairsets, eligible


def analyze_echo(records, pairsets, gap=77, min_cluster=6, same_day_only=True):
    src = []
    rows = []
    n = len(records)
    for i, s in enumerate(pairsets):
        if len(s) < int(min_cluster):
            continue
        j = i + int(gap)
        if j >= n:
            continue
        if same_day_only and records[i][1].date() != records[j][1].date():
            continue
        src.append({
            "Kaynak Çekiliş": records[i][0], "Kaynak Tarih": records[i][1].date(),
            "Kaynak Saat": records[i][1].strftime("%H:%M"), "Küme 6/6 Adet": len(s),
            "Hedef Çekiliş": records[j][0], "Hedef Saat": records[j][1].strftime("%H:%M"),
        })
        for c in s & pairsets[j]:
            a, b = decode_pair(c)
            rows.append({
                "Kaynak Çekiliş": records[i][0], "Hedef Çekiliş": records[j][0],
                "Tarih": records[j][1].date(), "Hedef Saat": records[j][1].strftime("%H:%M"),
                "Aile A": triple_name(a), "Aile B": triple_name(b), "6’lı Kupon": pair_coupon(c),
                "Gap": int(gap), "Sonuç": "6/6 EKO",
            })
    return src, rows


def scan_echo_gaps(records, pairsets, max_gap=160, min_cluster=6, same_day_only=True):
    cand = [i for i, s in enumerate(pairsets) if len(s) >= int(min_cluster)]
    out = []
    n = len(records)
    for gap in range(1, int(max_gap) + 1):
        srcn = ed = ep = 0
        for i in cand:
            j = i + gap
            if j >= n:
                continue
            if same_day_only and records[i][1].date() != records[j][1].date():
                continue
            srcn += 1
            k = len(pairsets[i] & pairsets[j])
            if k:
                ed += 1
                ep += k
        if srcn:
            out.append({
                "Gap": gap, "Kaynak Küme": srcn, "Echo Olan Hedef": ed,
                "Echo 6/6 Adet": ep, "Kaynak Başına Echo": round(ep / srcn, 4),
            })
    return sorted(out, key=lambda r: (-r["Echo 6/6 Adet"], -r["Kaynak Başına Echo"], r["Gap"]))


# ============================================================
# SIDEBAR / VERİ KAYNAĞI
# ============================================================
with st.sidebar:
    st.header("Veri Kaynağı")
    raw_url = st.text_input("GitHub raw veri.txt", value=DEFAULT_RAW_URL)
    upload = st.file_uploader("İstersen veri.txt yükle", type=["txt"])
    if "cache_bust" not in st.session_state:
        st.session_state.cache_bust = 0
    if st.button("🔄 Veriyi yenile", width="stretch"):
        st.session_state.cache_bust = int(time.time())
        st.cache_data.clear()
        for k in list(st.session_state.keys()):
            if k.startswith("v5_"):
                st.session_state.pop(k, None)
        st.rerun()

try:
    if upload is not None:
        text = upload.getvalue().decode("utf-8", errors="ignore")
        data_source = "Yüklenen veri.txt"
    else:
        text = fetch_text(raw_url, int(st.session_state.cache_bust))
        data_source = "GitHub veri.txt"
    records = parse_veri(text)
except Exception as e:
    st.error(f"veri.txt okunamadı: {e}")
    st.stop()

if not records:
    st.error("Geçerli çekiliş bulunamadı.")
    st.stop()

all_dates = sorted({r[1].date() for r in records})
asof = records[-1][1].date()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Çekiliş", f"{len(records):,}")
c2.metric("Gün", len(all_dates))
c3.metric("Başlangıç", records[0][1].strftime("%d.%m.%Y %H:%M"))
c4.metric("Son veri", records[-1][1].strftime("%d.%m.%Y %H:%M"))
st.caption(f"Kaynak: {data_source}")

# ============================================================
# TABS
# ============================================================
tabs = st.tabs([
    "🧭 Ana Panel",
    "📆 Gün Karşılaştırma",
    "🔟 10’lu Ritim",
    "🧩 Normal 6’lı",
    "🧬 3+3 Özel 6’lı",
    "🎯 +77 / Eko",
    "⏰ Canlı Takvim",
    "📚 Rehber",
    "📦 Rapor",
])

# ---------------- ANA PANEL ----------------
with tabs[0]:
    st.subheader("🧭 Araştırma Haritası")
    st.markdown(
        """
Bu sürümde tek bir aile tipine bağlı değiliz. Ana amaç **aynı sayısal ailenin farklı günlerde hangi takvim ritimleriyle tekrar ettiğini** bulmak.

- **Gün Karşılaştırma:** +1…+14, +21, +28 gibi gün aralıklarında iki günün çekilişlerini blok blok karşılaştırır.
- **10’lu Ritim:** aynı 10 sayının +2 gün, +5 gün, **+7 gün/haftalık**, +14 gün ve seçtiğin başka aralıklarda kaç kez tekrar ettiğini bulur.
- **Zincir:** yalnız iki tarih değil; örn. **08→10→12 Eylül** gibi aynı gap’in art arda 3–4–5 tarihte sürmesini ölçer.
- **Normal 6’lı:** 3+3 şartı olmadan bütün doğrulanmış 6’lı ritimleri aynı mantıkla inceler.
- **3+3:** iki ayrı 3’lü ailenin aynı çekilişte birleştiği özel 6’lıları ayrıca tutar.
- **+77 / Eko:** 3+3 kümelerinin çekiliş-gap yankılarını tarar.
- **Canlı Takvim:** geçmişte aynı gap’i en az iki kez doğrulamış 6’lı/10’luların bugünkü ve yakın gün pencerelerini listeler.

**Tarihsel Ritim Puanı tahmin olasılığı değildir.** Sadece geçmişte ritmin kaç kez, ne kadar uzun zincirle ve kaç ay boyunca tekrarlandığını özetler.
        """
    )
    st.info("Önerilen başlangıç: Gün Karşılaştırma → 10’lu Ritim [+2,+5,+7,+14] → Normal 6’lı → Canlı Takvim.")

# ---------------- GÜN KARŞILAŞTIRMA ----------------
with tabs[1]:
    st.subheader("📆 Günler Arası Detaylı Karşılaştırma")
    gap_options = list(range(1, 15)) + [21, 28]
    cmp_gaps = st.multiselect("Karşılaştırılacak gün aralıkları", gap_options, default=[2, 5, 7, 14], key="cmp_gaps")
    if st.button("📆 Günleri karşılaştır", type="primary", key="run_cmp"):
        if not cmp_gaps:
            st.warning("En az bir gün aralığı seç.")
        else:
            p = st.progress(0, text="Hazırlanıyor...")
            st.session_state["v5_cmp"] = analyze_day_pairs(records, cmp_gaps, p)
            p.empty()
    cmpres = st.session_state.get("v5_cmp")
    if cmpres:
        gdf = pd.DataFrame(cmpres["gaps"])
        rdf = pd.DataFrame(cmpres["rows"])
        st.markdown("### Gap bazında genel tablo")
        safe_dataframe(gdf, use_container_width=True, hide_index=True)
        st.markdown("### En güçlü gün çiftleri")
        safe_dataframe(rdf.head(300), use_container_width=True, hide_index=True)
        if not rdf.empty:
            st.download_button("Gün karşılaştırma CSV", df_bytes(rdf), "gunler_arasi_karsilastirma.csv", "text/csv")

# ---------------- 10'LU ----------------
with tabs[2]:
    st.subheader("🔟 10’lu Aile — Süreklilik ve Takvim Ritmi")
    st.caption("Aynı 10 sayının iki günlük tek tesadüfi bağlantısından çok, aynı gap’i tekrar eden ve 3+ tarih zinciri yapan aileleri öne çıkarır.")
    a, b, c, d = st.columns(4)
    with a:
        ten_gaps = st.multiselect("10’lu gün gapleri", list(range(1, 15)) + [21, 28], default=[2, 5, 7, 14], key="ten_gaps")
    with b:
        ten_expand = st.slider("Ortak blok en fazla kaç sayıya kadar 10’luya açılsın?", 10, 14, 12, key="ten_expand")
    with c:
        ten_min = st.number_input("Aynı gap en az kaç gün-bağı?", 2, 8, 2, 1, key="ten_min")
    with d:
        ten_verify = st.number_input("Tam doğrulama üst sınırı", 100, 10000, 4000, 100, key="ten_verify")

    if st.button("🔟 10’lu ritimleri çıkar", type="primary", key="run10"):
        if not ten_gaps:
            st.warning("En az bir gap seç.")
        else:
            p = st.progress(0, text="10’lu ritimler hazırlanıyor...")
            st.session_state["v5_10"] = mine_family_rhythms(
                records, 10, ten_gaps, ten_expand, ten_min, ten_verify, 180000, p
            )
            p.empty()

    ten = st.session_state.get("v5_10")
    if ten:
        tdf = pd.DataFrame(ten["rows"])
        cdf = pd.DataFrame(ten["chains"])
        mdf = pd.DataFrame(ten["multi"])
        due = pd.DataFrame(ten["due"])
        x1, x2, x3, x4 = st.columns(4)
        x1.metric("Doğrulanmış ritimli 10’lu", len(tdf))
        x2.metric("3+ tarih zinciri", int((cdf["En Uzun Zincir Gün"] >= 3).sum()) if not cdf.empty else 0)
        x3.metric("Haftalık (+7) ritimli", int((tdf.get("+7 Gün Bağı", pd.Series(dtype=int)) >= int(ten_min)).sum()) if not tdf.empty and "+7 Gün Bağı" in tdf else 0)
        x4.metric("Birden çok gap ritmi", len(mdf))

        if ten["truncated_edges"]:
            st.warning(f"{len(ten['truncated_edges'])} gün bağlantısında güvenlik limiti çalıştı. Gerekirse ortak blok üst sınırını düşür.")

        st.markdown("### 🔥 En güçlü 10’lu ritimler")
        safe_dataframe(tdf.head(500), use_container_width=True, hide_index=True)

        if not tdf.empty:
            for g, title in [(2, "+2 gün / iki günde bir"), (5, "+5 gün"), (7, "+7 gün / haftalık"), (14, "+14 gün / iki haftalık")]:
                col = f"+{g} Gün Bağı"
                if col in tdf.columns:
                    sub = tdf[tdf[col] >= int(ten_min)].copy()
                    if not sub.empty:
                        st.markdown(f"### {title} ritimli 10’lular")
                        safe_dataframe(sub.head(300), use_container_width=True, hide_index=True)

        if not cdf.empty:
            st.markdown("### 🔗 3–4–5 tarihli zincirler")
            safe_dataframe(cdf[cdf["En Uzun Zincir Gün"] >= 3].head(500), use_container_width=True, hide_index=True)

        if not mdf.empty:
            st.markdown("### 🧬 Birden fazla gün ritmi olan aynı 10’lu")
            safe_dataframe(mdf.head(300), use_container_width=True, hide_index=True)

        # 08-10-12 Eylül özel kontrol
        if not cdf.empty:
            sp = cdf[(cdf["Gün Gap"] == 2) & cdf["Zincir"].astype(str).str.contains("08.09.2026 → 10.09.2026 → 12.09.2026", regex=False)]
            st.markdown("### 🎯 08→10→12 Eylül özel kontrol")
            if len(sp):
                st.success(f"{len(sp)} adet 10’lu aile bu exact +2,+2 zincirinde bulundu.")
                safe_dataframe(sp, use_container_width=True, hide_index=True)
            else:
                st.info("Seçili genişletme/filtre ayarlarında exact 08→10→12 Eylül zinciri bulunmadı.")

        if not due.empty:
            st.markdown("### ⏰ Bugün / yakın pencere")
            safe_dataframe(due.head(300), use_container_width=True, hide_index=True)

        st.download_button("10’lu ritimler CSV", df_bytes(tdf), "10lu_ritimler.csv", "text/csv")

# ---------------- NORMAL 6 ----------------
with tabs[3]:
    st.subheader("🧩 Normal 6’lı — 3+3 Şartı Yok")
    a, b, c, d = st.columns(4)
    with a:
        six_gaps = st.multiselect("6’lı gün gapleri", list(range(1, 15)) + [21, 28], default=[2, 5, 7, 14], key="six_gaps")
    with b:
        six_expand = st.slider("Ortak blok en fazla kaç sayıya kadar 6’lıya açılsın?", 6, 9, 8, key="six_expand")
    with c:
        six_min = st.number_input("Aynı gap en az kaç gün-bağı?", 2, 8, 2, 1, key="six_min")
    with d:
        six_verify = st.number_input("Tam doğrulama üst sınırı", 500, 15000, 7000, 500, key="six_verify")

    if st.button("🧩 Normal 6’lı ritimleri çıkar", type="primary", key="run6"):
        if not six_gaps:
            st.warning("En az bir gap seç.")
        else:
            p = st.progress(0, text="Normal 6’lılar hazırlanıyor...")
            st.session_state["v5_6"] = mine_family_rhythms(
                records, 6, six_gaps, six_expand, six_min, six_verify, 200000, p
            )
            p.empty()

    six = st.session_state.get("v5_6")
    if six:
        sdf = pd.DataFrame(six["rows"])
        scf = pd.DataFrame(six["chains"])
        smf = pd.DataFrame(six["multi"])
        x1, x2, x3, x4 = st.columns(4)
        x1.metric("Ritimli normal 6’lı", len(sdf))
        x2.metric("3+ tarih zinciri", int((scf["En Uzun Zincir Gün"] >= 3).sum()) if not scf.empty else 0)
        x3.metric("Aynı gün 3+ yaşayan", int((sdf["Aynı Gün Max"] >= 3).sum()) if not sdf.empty else 0)
        x4.metric("Birden çok gap ritmi", len(smf))
        st.markdown("### En güçlü normal 6’lı ritimler")
        safe_dataframe(sdf.head(700), use_container_width=True, hide_index=True)
        if not scf.empty:
            st.markdown("### 3+ tarihli normal 6’lı zincirleri")
            safe_dataframe(scf[scf["En Uzun Zincir Gün"] >= 3].head(500), use_container_width=True, hide_index=True)
        if not smf.empty:
            st.markdown("### Birden fazla ritim taşıyan normal 6’lı")
            safe_dataframe(smf.head(300), use_container_width=True, hide_index=True)
        st.download_button("Normal 6’lı CSV", df_bytes(sdf), "normal6_ritimler.csv", "text/csv")

# ---------------- 3+3 ----------------
with tabs[4]:
    st.subheader("🧬 3+3 Özel 6’lı")
    a, b, c, d = st.columns(4)
    with a:
        tri_min = st.number_input("3’lü exact-gap tekrar eşiği", 3, 30, 7, 1, key="tri_min")
    with b:
        tri_maxgap = st.number_input("3’lü max çekiliş gap", 12, 120, 60, 1, key="tri_maxgap")
    with c:
        tri_pool = st.number_input("Güvenli 3’lü havuzu", 100, 1500, 500, 50, key="tri_pool")
    with d:
        pair_min = st.number_input("3+3 min 6/6 tekrar", 1, 15, 3, 1, key="pair_min")
    if st.button("🧬 3+3 analizini çalıştır", type="primary", key="run33"):
        p = st.progress(0, text="3+3 hazırlanıyor...")
        freq, bg, bc = mine_triples_dense(records, tri_maxgap, p)
        threshold, qual, selected = choose_families(freq, bg, bc, tri_min, tri_pool)
        pair_rows, events, pairsets, eligible = mine_pairs_safe(records, selected, pair_min, p)
        p.progress(1.0, text="Tamamlandı")
        time.sleep(0.1)
        p.empty()
        famrows = [{
            "3’lü Aile": triple_name(i), "Toplam Görünüş": int(freq[i]),
            "En Sık Exact Gap": int(bg[i]), "Exact Gap Tekrar": int(bc[i]),
        } for i in selected]
        famrows.sort(key=lambda r: (-r["Exact Gap Tekrar"], -r["Toplam Görünüş"], r["3’lü Aile"]))
        st.session_state["v5_33"] = {
            "threshold": threshold, "famrows": famrows, "pairs": pair_rows,
            "events": events, "pairsets": pairsets,
        }
    r33 = st.session_state.get("v5_33")
    if r33:
        p1, p2, p3 = st.columns(3)
        p1.metric("Seçilen 3’lü", len(r33["famrows"]))
        p2.metric("3+3 çift", len(r33["pairs"]))
        p3.metric("3+3 6/6 olay", len(r33["events"]))
        st.caption(f"Otomatik güvenli exact-gap eşiği: {r33['threshold']}")
        safe_dataframe(pd.DataFrame(r33["pairs"]).head(700), use_container_width=True, hide_index=True)

# ---------------- EKO ----------------
with tabs[5]:
    st.subheader("🎯 +77 Küme-Eko ve Gap Taraması")
    r33 = st.session_state.get("v5_33")
    if not r33:
        st.info("Önce 3+3 sekmesinde analizi çalıştır.")
    else:
        a, b, c = st.columns(3)
        with a:
            echo_gap = st.number_input("Hedef çekiliş gap", 1, 300, 77, 1, key="echo_gap")
        with b:
            min_cluster = st.number_input("Kaynakta min 6/6 kümesi", 1, 30, 6, 1, key="echo_cluster")
        with c:
            scan_max = st.number_input("Bütün gap tarama üst sınırı", 20, 300, 160, 5, key="echo_scan")
        same_day = st.checkbox("Yalnız aynı gün", value=True, key="echo_same")
        if st.button("🎯 Eko analizini çalıştır", type="primary", key="run_echo"):
            src, echo = analyze_echo(records, r33["pairsets"], echo_gap, min_cluster, same_day)
            scan = scan_echo_gaps(records, r33["pairsets"], scan_max, min_cluster, same_day)
            st.session_state["v5_echo"] = {"src": src, "echo": echo, "scan": scan}
        er = st.session_state.get("v5_echo")
        if er:
            e1, e2 = st.columns(2)
            e1.metric("Kaynak küme", len(er["src"]))
            e2.metric("Gerçek eko 6/6", len(er["echo"]))
            st.markdown("### Gerçek eko olayları")
            safe_dataframe(pd.DataFrame(er["echo"]), use_container_width=True, hide_index=True)
            st.markdown("### En güçlü çekiliş-gapler")
            safe_dataframe(pd.DataFrame(er["scan"]).head(100), use_container_width=True, hide_index=True)

# ---------------- CANLI TAKVİM ----------------
with tabs[6]:
    st.subheader("⏰ Canlı Takvim — Geçmiş Ritme Göre İzleme Pencereleri")
    st.warning("Bu ekran geçmiş takvim ritmini izler; gelecekte çekilişi garanti etmez.")
    six = st.session_state.get("v5_6")
    ten = st.session_state.get("v5_10")
    blocks = []
    if ten and ten["due"]:
        df = pd.DataFrame(ten["due"]).copy()
        df.insert(0, "Tür", "10’lu")
        blocks.append(df)
    if six and six["due"]:
        df = pd.DataFrame(six["due"]).copy()
        df.insert(0, "Tür", "Normal 6’lı")
        blocks.append(df)
    if blocks:
        live = pd.concat(blocks, ignore_index=True, sort=False)
        st.metric("Bugün / yakın pencere adayı", len(live))
        safe_dataframe(live, use_container_width=True, hide_index=True)
    else:
        st.info("Önce 10’lu ve/veya Normal 6’lı ritim analizini çalıştır.")

# ---------------- REHBER ----------------
with tabs[7]:
    st.subheader("📚 Nasıl okuyacağız?")
    st.markdown(
        """
**Gap Bağı:** aynı ailenin `d` ve `d+gap` günlerinin ikisinde de görülme sayısı. Örneğin +7 bağının 4 olması, aynı 10’lunun dört ayrı haftalık tarih bağlantısı kurduğu anlamına gelir.

**En Uzun Aynı-Gap Zinciri:** aynı gap’in art arda kaç tarihte sürdüğü. `08→10→12` zinciri +2 için 3 gündür ve iki ardışık +2 bağı içerir.

**Aynı Gün Max:** aynı aile bir gün içinde en fazla kaç farklı çekilişte tamamlanmış.

**Birden çok gap:** aynı aile yalnız +2 değil, örneğin +2 ve +7 gibi iki ayrı takvim ritmini de en az seçilen eşik kadar göstermiş.

**Tarihsel Ritim Puanı:** geçmişteki tekrar, zincir uzunluğu, aktif gün ve ay yayılımını tek ekranda sıralamak için kullanılan keşif puanıdır; olasılık veya kazanma garantisi değildir.

**10’lu genişletme:** iki çekilişin ortak bloğu 11–12 sayıysa içindeki 10’lu alt kümeler taranabilir. Bu yüzden tek bağlantılı on binlerce kombinasyonu raporlamıyoruz; varsayılan olarak aynı gap’i en az iki gün-bağında tekrar edenler tam doğrulamaya geçer.
        """
    )

# ---------------- RAPOR ----------------
with tabs[8]:
    st.subheader("📦 Tek ZIP Rapor")
    files = {
        "00_BILGI.txt": (
            f"Veri: {records[0][1]} -> {records[-1][1]}\n"
            f"Çekiliş: {len(records)}\nGün: {len(all_dates)}\n"
            "V5 Günler Arası Ritim Merkezi\n"
        )
    }
    cmpres = st.session_state.get("v5_cmp")
    if cmpres:
        files["01_GUN_GAP_OZET.csv"] = df_bytes(pd.DataFrame(cmpres["gaps"]))
        files["02_GUNLER_ARASI_KARSILASTIRMA.csv"] = df_bytes(pd.DataFrame(cmpres["rows"]))
    ten = st.session_state.get("v5_10")
    if ten:
        files["10_10LU_RITIMLER.csv"] = df_bytes(pd.DataFrame(ten["rows"]))
        files["11_10LU_ZINCIRLER.csv"] = df_bytes(pd.DataFrame(ten["chains"]))
        files["12_10LU_COKLU_GAP.csv"] = df_bytes(pd.DataFrame(ten["multi"]))
        files["13_10LU_OLAYLAR.csv"] = df_bytes(pd.DataFrame(ten["events"]))
    six = st.session_state.get("v5_6")
    if six:
        files["20_NORMAL6_RITIMLER.csv"] = df_bytes(pd.DataFrame(six["rows"]))
        files["21_NORMAL6_ZINCIRLER.csv"] = df_bytes(pd.DataFrame(six["chains"]))
        files["22_NORMAL6_COKLU_GAP.csv"] = df_bytes(pd.DataFrame(six["multi"]))
        files["23_NORMAL6_OLAYLAR.csv"] = df_bytes(pd.DataFrame(six["events"]))
    r33 = st.session_state.get("v5_33")
    if r33:
        files["30_3LU_AILELER.csv"] = df_bytes(pd.DataFrame(r33["famrows"]))
        files["31_3ARTI3_CIFTLER.csv"] = df_bytes(pd.DataFrame(r33["pairs"]))
        files["32_3ARTI3_OLAYLAR.csv"] = df_bytes(pd.DataFrame(r33["events"]))
    er = st.session_state.get("v5_echo")
    if er:
        files["40_EKO_KAYNAK.csv"] = df_bytes(pd.DataFrame(er["src"]))
        files["41_EKO_OLAYLAR.csv"] = df_bytes(pd.DataFrame(er["echo"]))
        files["42_EKO_GAP_TARAMA.csv"] = df_bytes(pd.DataFrame(er["scan"]))

    if len(files) == 1:
        st.info("Rapor için önce istediğin analizleri çalıştır.")
    else:
        payload = build_zip(files)
        st.download_button(
            "⬇️ TÜM RAPORLARI TEK ZIP İNDİR",
            payload,
            "HIZLI_ON_RITIM_MERKEZI_V5_TUM_RAPORLAR.zip",
            "application/zip",
            width="stretch",
        )
        st.caption(f"ZIP içinde {len(files)} dosya var.")

st.caption(
    "V5 bellek kontrollü tasarlanmıştır. Varsayılan raporlar tek bağlantılı binlerce alt kümeyi değil, "
    "aynı gün-gap ritmini tekrar etmiş ve tam doğrulanmış aileleri öne çıkarır."
)
