# -*- coding: utf-8 -*-
import io
import math
import time
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from itertools import combinations

import numpy as np
import pandas as pd
import requests
import streamlit as st

APP_TITLE = "🧠 Hızlı On — 3+3 Aile / +77 Küme‑Eko / 10'lu Ritim Laboratuvarı"
DEFAULT_RAW_URL = "https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt"

st.set_page_config(page_title="Hızlı On Ritim Laboratuvarı", page_icon="🧠", layout="wide")
st.title(APP_TITLE)
st.caption("GitHub veri.txt → gün/saat → 3+3 aileler → +77 küme‑eko → aynı 10'lu aile ritimleri")

# ============================================================
# Veri
# ============================================================

@st.cache_data(ttl=90, show_spinner=False)
def fetch_text(url: str, cache_bust: int = 0) -> str:
    sep = "&" if "?" in url else "?"
    r = requests.get(
        f"{url}{sep}_cb={cache_bust}",
        timeout=30,
        headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
    r.raise_for_status()
    return r.text

def nums_to_mask(nums):
    m = 0
    for n in nums:
        m |= 1 << (int(n) - 1)
    return m

def mask_to_nums(mask):
    out = []
    n = 1
    while mask:
        if mask & 1:
            out.append(n)
        n += 1
        mask >>= 1
    return out

def triple_key(a, b, c):
    # 1..80 -> 7 bit each
    return int(a) | (int(b) << 7) | (int(c) << 14)

def key_to_triple(k):
    return (k & 127, (k >> 7) & 127, (k >> 14) & 127)

def triple_mask_from_key(k):
    a, b, c = key_to_triple(k)
    return (1 << (a - 1)) | (1 << (b - 1)) | (1 << (c - 1))

def fmt_family_key(k):
    return "-".join(map(str, key_to_triple(k)))

def fmt_coupon_from_pair(pair):
    k1, k2 = pair
    nums = sorted(set(key_to_triple(k1)) | set(key_to_triple(k2)))
    return "-".join(map(str, nums))

@st.cache_data(show_spinner=False)
def parse_veri(text: str):
    rows = []
    seen = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or ";" not in line:
            continue
        p = line.split(";")
        if len(p) != 3:
            continue
        try:
            draw_id = int(p[0].strip())
            dt = datetime.strptime(p[1].strip(), "%d.%m.%Y %H:%M")
            nums = tuple(sorted(int(x.strip()) for x in p[2].split(",") if x.strip()))
        except Exception:
            continue
        if len(nums) != 20 or len(set(nums)) != 20:
            continue
        if not all(1 <= x <= 80 for x in nums):
            continue
        if draw_id in seen:
            continue
        seen.add(draw_id)
        rows.append((draw_id, dt, nums, nums_to_mask(nums)))
    rows.sort(key=lambda x: x[1])
    return rows

def records_to_df(records):
    return pd.DataFrame(
        {
            "Çekiliş": [r[0] for r in records],
            "TarihSaat": [r[1] for r in records],
            "Tarih": [r[1].date() for r in records],
            "Saat": [r[1].hour for r in records],
            "Dakika": [r[1].minute for r in records],
            "Sayılar": [",".join(map(str, r[2])) for r in records],
        }
    )

# ============================================================
# 3'lü ritimli aile madenciliği
# ============================================================

def mine_triple_families(records, max_gap=60, min_exact_gap_repeat=7):
    """
    Her 3'lünün ardışık tam görünüşleri arasındaki gap'i izler.
    Bir exact gap en az min_exact_gap_repeat kez yinelenirse aile kabul edilir.
    """
    last = {}
    freq = Counter()
    gaps = defaultdict(Counter)

    for pos, (_, _, nums, _) in enumerate(records):
        for a, b, c in combinations(nums, 3):
            k = triple_key(a, b, c)
            freq[k] += 1
            if k in last:
                g = pos - last[k]
                if 1 <= g <= max_gap:
                    gaps[k][g] += 1
            last[k] = pos

    families = {}
    for k, gc in gaps.items():
        if not gc:
            continue
        best_gap, best_count = gc.most_common(1)[0]
        if best_count >= min_exact_gap_repeat:
            families[k] = {
                "key": k,
                "family": fmt_family_key(k),
                "appearance": int(freq[k]),
                "best_gap": int(best_gap),
                "best_gap_repeat": int(best_count),
                "gap_dist": dict(gc),
                "mask": triple_mask_from_key(k),
            }
    return families

def active_families_per_draw(records, eligible_keys):
    eligible = set(eligible_keys)
    active = []
    for _, _, nums, _ in records:
        arr = []
        for a, b, c in combinations(nums, 3):
            k = triple_key(a, b, c)
            if k in eligible:
                arr.append(k)
        active.append(arr)
    return active

def mine_pairs(records, families, pair_min_repeat=3):
    active = active_families_per_draw(records, families.keys())
    pair_counts = Counter()

    for fams in active:
        L = len(fams)
        for i in range(L):
            k1 = fams[i]
            m1 = families[k1]["mask"]
            for j in range(i + 1, L):
                k2 = fams[j]
                if m1 & families[k2]["mask"]:
                    continue
                pair = (k1, k2) if k1 < k2 else (k2, k1)
                pair_counts[pair] += 1

    eligible_pairs = {p: c for p, c in pair_counts.items() if c >= pair_min_repeat}
    eligible_set = set(eligible_pairs)

    events = []
    pairsets = [set() for _ in records]
    day_pair_hits = defaultdict(lambda: defaultdict(list))

    for idx, fams in enumerate(active):
        L = len(fams)
        local = set()
        for i in range(L):
            k1 = fams[i]
            m1 = families[k1]["mask"]
            for j in range(i + 1, L):
                k2 = fams[j]
                if m1 & families[k2]["mask"]:
                    continue
                pair = (k1, k2) if k1 < k2 else (k2, k1)
                if pair not in eligible_set or pair in local:
                    continue
                local.add(pair)
                pairsets[idx].add(pair)
                draw_id, dt, _, _ = records[idx]
                day_pair_hits[pair][dt.date()].append(idx)
                events.append(
                    {
                        "_idx": idx,
                        "_pair": pair,
                        "Çekiliş": draw_id,
                        "Tarih": dt.date(),
                        "Saat": dt.strftime("%H:%M"),
                        "Aile A": fmt_family_key(pair[0]),
                        "Aile B": fmt_family_key(pair[1]),
                        "6'lı Kupon": fmt_coupon_from_pair(pair),
                        "Pair Toplam 6/6": int(eligible_pairs[pair]),
                    }
                )

    pair_rows = []
    for pair, total in sorted(eligible_pairs.items(), key=lambda kv: (-kv[1], kv[0])):
        perday = day_pair_hits[pair]
        same2_days = sum(1 for hits in perday.values() if len(hits) >= 2)
        same3_days = sum(1 for hits in perday.values() if len(hits) >= 3)
        all_hits = sorted(i for hits in perday.values() for i in hits)
        gc = Counter()
        for x, y in zip(all_hits, all_hits[1:]):
            gc[y - x] += 1
        mode_gap, mode_n = gc.most_common(1)[0] if gc else ("", 0)
        pair_rows.append(
            {
                "_pair": pair,
                "Aile A": fmt_family_key(pair[0]),
                "Aile B": fmt_family_key(pair[1]),
                "6'lı Kupon": fmt_coupon_from_pair(pair),
                "Toplam 6/6": int(total),
                "Aktif Gün": len(perday),
                "Aynı Gün 2+ Gün": same2_days,
                "Aynı Gün 3+ Gün": same3_days,
                "En Sık Pair Gap": mode_gap,
                "Gap Tekrar": mode_n,
            }
        )

    family_rows = []
    for k, v in sorted(families.items(), key=lambda kv: (-kv[1]["best_gap_repeat"], -kv[1]["appearance"], kv[0])):
        family_rows.append(
            {
                "3'lü Aile": v["family"],
                "3/3 Görünüş": v["appearance"],
                "En Güçlü Exact Gap": v["best_gap"],
                "Gap Tekrar": v["best_gap_repeat"],
            }
        )

    return {
        "family_rows": family_rows,
        "pair_rows": pair_rows,
        "events": events,
        "pairsets": pairsets,
        "active_family_counts": [len(x) for x in active],
    }

def summarize_events(events):
    if not events:
        return pd.DataFrame(), pd.DataFrame()
    e = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in events])
    daily = (
        e.groupby("Tarih", as_index=False)
        .agg(
            **{
                "3+3 Olay": ("Çekiliş", "size"),
                "Farklı 6'lı": ("6'lı Kupon", "nunique"),
                "Aktif Çekiliş": ("Çekiliş", "nunique"),
            }
        )
        .sort_values("Tarih")
    )
    tmp = e.copy()
    tmp["SaatDilimi"] = tmp["Saat"].str[:2] + ":00"
    hourly = (
        tmp.groupby(["Tarih", "SaatDilimi"], as_index=False)
        .agg(
            **{
                "3+3 Olay": ("Çekiliş", "size"),
                "Farklı 6'lı": ("6'lı Kupon", "nunique"),
                "Aktif Çekiliş": ("Çekiliş", "nunique"),
            }
        )
        .sort_values(["Tarih", "SaatDilimi"])
    )
    return daily, hourly

# ============================================================
# +77 küme-eko
# ============================================================

def cluster_echo(records, pairsets, gap=77, min_cluster=6, same_day_only=True):
    rows = []
    source_rows = []
    n = len(records)
    for i in range(n):
        src = pairsets[i]
        if len(src) < min_cluster:
            continue
        j = i + int(gap)
        if j >= n:
            continue
        if same_day_only and records[i][1].date() != records[j][1].date():
            continue
        inter = src & pairsets[j]
        source_rows.append(
            {
                "Kaynak Çekiliş": records[i][0],
                "Kaynak": records[i][1].strftime("%d.%m.%Y %H:%M"),
                "Küme Büyüklüğü": len(src),
                "Hedef Çekiliş": records[j][0],
                "Hedef": records[j][1].strftime("%d.%m.%Y %H:%M"),
                "Echo 6/6 Adet": len(inter),
            }
        )
        for pair in sorted(inter):
            rows.append(
                {
                    "Gap": gap,
                    "Kaynak Çekiliş": records[i][0],
                    "Kaynak": records[i][1].strftime("%d.%m.%Y %H:%M"),
                    "Kaynak Küme": len(src),
                    "Hedef Çekiliş": records[j][0],
                    "Hedef": records[j][1].strftime("%d.%m.%Y %H:%M"),
                    "Aile A": fmt_family_key(pair[0]),
                    "Aile B": fmt_family_key(pair[1]),
                    "6'lı Kupon": fmt_coupon_from_pair(pair),
                    "Sonuç": "6/6 EKO",
                }
            )
    return source_rows, rows

def scan_echo_gaps(records, pairsets, max_gap=200, min_cluster=6, same_day_only=True):
    out = []
    n = len(records)
    source_candidates = [i for i, s in enumerate(pairsets) if len(s) >= min_cluster]
    for gap in range(1, int(max_gap) + 1):
        src_count = 0
        echo_draws = 0
        echo_pairs = 0
        for i in source_candidates:
            j = i + gap
            if j >= n:
                continue
            if same_day_only and records[i][1].date() != records[j][1].date():
                continue
            src_count += 1
            k = len(pairsets[i] & pairsets[j])
            if k:
                echo_draws += 1
                echo_pairs += k
        if src_count:
            out.append(
                {
                    "Gap": gap,
                    "Kaynak Küme": src_count,
                    "Echo Olan Hedef": echo_draws,
                    "Echo 6/6 Adet": echo_pairs,
                    "Kaynak Başına Echo": round(echo_pairs / src_count, 4),
                }
            )
    return sorted(out, key=lambda r: (-r["Echo 6/6 Adet"], -r["Kaynak Başına Echo"], r["Gap"]))

# ============================================================
# Aynı 10'lu aile — gün aralığı ritmi
# ============================================================

def date_map(records):
    m = defaultdict(list)
    for i, (_, dt, _, _) in enumerate(records):
        m[dt.date()].append(i)
    return m

def candidate_10_families(records, day_gaps=(2, 5)):
    bydate = date_map(records)
    dates = sorted(bydate)
    date_set = set(dates)
    out = {}

    for gap in day_gaps:
        fams = set()
        pair_match_count = 0
        for d in dates:
            d2 = d + timedelta(days=int(gap))
            if d2 not in date_set:
                continue
            I1 = bydate[d]
            I2 = bydate[d2]
            for i in I1:
                m1 = records[i][3]
                for j in I2:
                    inter = m1 & records[j][3]
                    bc = inter.bit_count()
                    if bc < 10:
                        continue
                    pair_match_count += 1
                    nums = mask_to_nums(inter)
                    if bc == 10:
                        fams.add(tuple(nums))
                    else:
                        for fam in combinations(nums, 10):
                            fams.add(tuple(fam))
        out[int(gap)] = {"families": fams, "pair_match_count": pair_match_count}
    return out

def occurrences_for_10_families(records, fams):
    bydate = date_map(records)
    dates = sorted(bydate)
    out = {}
    for fam in fams:
        fm = nums_to_mask(fam)
        occ = defaultdict(list)
        for d in dates:
            for i in bydate[d]:
                if records[i][3] & fm == fm:
                    occ[d].append(i)
        if len(occ) >= 2:
            out[fam] = dict(occ)
    return out

def analyze_10_rhythm(records, day_gaps=(2, 5)):
    candidates = candidate_10_families(records, day_gaps)
    all_rows = []
    progression_rows = []
    special_812 = []

    for gap in day_gaps:
        fams = candidates[int(gap)]["families"]
        occs = occurrences_for_10_families(records, fams)
        for fam, occ in occs.items():
            dates = sorted(occ)
            relevant_dates = []
            for d in dates:
                if d + timedelta(days=int(gap)) in occ:
                    relevant_dates.extend([d, d + timedelta(days=int(gap))])
            relevant_dates = sorted(set(relevant_dates))
            if not relevant_dates:
                continue

            times_txt = []
            for d in relevant_dates:
                labels = [records[i][1].strftime("%d.%m.%Y %H:%M") for i in occ[d]]
                times_txt.append(f"{d.strftime('%d.%m.%Y')}: " + ", ".join(x[-5:] for x in labels[:12]))

            all_rows.append(
                {
                    "Gün Aralığı": int(gap),
                    "10'lu Aile": "-".join(map(str, fam)),
                    "Tekrar Eden Gün Sayısı": len(relevant_dates),
                    "İlk Gün": relevant_dates[0],
                    "Son Gün": relevant_dates[-1],
                    "Görünüş": " | ".join(times_txt),
                }
            )

            # En az 3 tarihli aritmetik dizi: d, d+gap, d+2gap
            for d in dates:
                d2 = d + timedelta(days=int(gap))
                d3 = d + timedelta(days=2 * int(gap))
                if d2 in occ and d3 in occ:
                    progression_rows.append(
                        {
                            "Ritim": f"+{gap} gün, +{gap} gün",
                            "10'lu Aile": "-".join(map(str, fam)),
                            "1. Gün": d,
                            "2. Gün": d2,
                            "3. Gün": d3,
                            "1. Saatler": ",".join(records[i][1].strftime("%H:%M") for i in occ[d][:10]),
                            "2. Saatler": ",".join(records[i][1].strftime("%H:%M") for i in occ[d2][:10]),
                            "3. Saatler": ",".join(records[i][1].strftime("%H:%M") for i in occ[d3][:10]),
                        }
                    )
                    if d.strftime("%d.%m.%Y") == "08.08.2026" and gap == 2:
                        special_812.append(progression_rows[-1].copy())

    # dedupe rows
    def dedupe_dicts(rows, keys):
        seen = set()
        out = []
        for r in rows:
            k = tuple(str(r[x]) for x in keys)
            if k not in seen:
                seen.add(k)
                out.append(r)
        return out

    all_rows = dedupe_dicts(all_rows, ["Gün Aralığı", "10'lu Aile"])
    progression_rows = dedupe_dicts(progression_rows, ["Ritim", "10'lu Aile", "1. Gün", "2. Gün", "3. Gün"])
    special_812 = dedupe_dicts(special_812, ["10'lu Aile", "1. Gün", "2. Gün", "3. Gün"])
    all_rows.sort(key=lambda r: (r["Gün Aralığı"], -r["Tekrar Eden Gün Sayısı"], r["10'lu Aile"]))
    progression_rows.sort(key=lambda r: (r["Ritim"], r["1. Gün"], r["10'lu Aile"]))
    return {
        "repeats": all_rows,
        "progressions": progression_rows,
        "special_812": special_812,
        "candidate_counts": {g: len(candidates[g]["families"]) for g in candidates},
        "intersection_pair_counts": {g: candidates[g]["pair_match_count"] for g in candidates},
    }

# ============================================================
# Rapor
# ============================================================

def df_bytes(df):
    return df.to_csv(index=False).encode("utf-8-sig")

def build_zip(files: dict):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            if isinstance(data, str):
                data = data.encode("utf-8-sig")
            z.writestr(name, data)
    return bio.getvalue()

# ============================================================
# UI — veri yükle
# ============================================================

with st.sidebar:
    st.header("Veri Kaynağı")
    raw_url = st.text_input("GitHub raw veri.txt", value=DEFAULT_RAW_URL)
    if "cache_bust" not in st.session_state:
        st.session_state.cache_bust = 0
    if st.button("🔄 GitHub verisini yenile", use_container_width=True):
        st.session_state.cache_bust = int(time.time())
        st.cache_data.clear()
        st.session_state.pop("a33", None)
        st.session_state.pop("ten", None)
        st.rerun()

try:
    text = fetch_text(raw_url, int(st.session_state.cache_bust))
    all_records = parse_veri(text)
except Exception as e:
    st.error(f"veri.txt okunamadı: {e}")
    st.stop()

if not all_records:
    st.error("veri.txt içinde geçerli çekiliş bulunamadı.")
    st.stop()

all_dates = [r[1].date() for r in all_records]
min_date, max_date = min(all_dates), max(all_dates)

with st.sidebar:
    st.success(f"{len(all_records):,} çekiliş • {min_date.strftime('%d.%m.%Y')} → {max_date.strftime('%d.%m.%Y')}")
    start_date = st.date_input("Başlangıç", value=min_date, min_value=min_date, max_value=max_date)
    end_date = st.date_input("Bitiş", value=max_date, min_value=min_date, max_value=max_date)
    if start_date > end_date:
        st.error("Başlangıç bitişten büyük olamaz.")
        st.stop()

records = [r for r in all_records if start_date <= r[1].date() <= end_date]
if not records:
    st.warning("Seçilen tarih aralığında veri yok.")
    st.stop()

if min_date > datetime(2026, 8, 1).date() or max_date < datetime(2026, 10, 9).date():
    st.warning(
        f"GitHub'dan şu an görünen veri {min_date.strftime('%d.%m.%Y')}–{max_date.strftime('%d.%m.%Y')}. "
        "1 Ağustos–9 Ekim tam kapsama gelmediyse 'GitHub verisini yenile' düğmesine bas."
    )
else:
    st.success("✅ 1 Ağustos–9 Ekim kapsaması veri.txt içinde görünüyor.")

tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📌 Veri", "🧬 3+3 Aileler", "🎯 +77 Küme‑Eko", "🔟 10'lu Ritim", "🕐 Gün / Saat", "📦 Rapor"]
)

# ============================================================
# TAB 0 — Veri
# ============================================================
with tab0:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Çekiliş", f"{len(records):,}")
    c2.metric("Gün", len(set(r[1].date() for r in records)))
    c3.metric("İlk", records[0][1].strftime("%d.%m.%Y %H:%M"))
    c4.metric("Son", records[-1][1].strftime("%d.%m.%Y %H:%M"))

    vdf = records_to_df(records)
    day_counts = vdf.groupby("Tarih").size().reset_index(name="Çekiliş")
    st.subheader("Günlük veri kontrolü")
    st.dataframe(day_counts, use_container_width=True, height=320)
    st.download_button("Günlük veri sayımı CSV", df_bytes(day_counts), "gunluk_veri_sayimi.csv", "text/csv")

# ============================================================
# TAB 1 — 3+3
# ============================================================
with tab1:
    st.subheader("3+3 aileleri komple çıkar")
    st.write(
        "Önce ritimli 3'lü aileler çıkarılır; sonra aynı çekilişte iki ayrık 3'lü birleşip 6/6 olan bütün uygun çiftler bulunur."
    )
    a, b, c = st.columns(3)
    with a:
        max_gap = st.number_input("3'lü exact gap üst sınırı", min_value=10, max_value=217, value=60, step=1)
    with b:
        min_gap_repeat = st.number_input("Aynı exact gap en az kaç kez?", min_value=2, max_value=50, value=7, step=1)
    with c:
        pair_min_repeat = st.number_input("3+3 çift en az kaç 6/6?", min_value=1, max_value=30, value=3, step=1)

    if st.button("🚀 3+3 TAM ANALİZİ BAŞLAT", type="primary", use_container_width=True):
        with st.spinner("3'lü ritimli aileler çıkarılıyor..."):
            fam = mine_triple_families(records, int(max_gap), int(min_gap_repeat))
        st.info(f"Ritim filtresini geçen 3'lü aile: {len(fam):,}")
        with st.spinner("3+3 çiftler ve tüm 6/6 olayları çıkarılıyor..."):
            res = mine_pairs(records, fam, int(pair_min_repeat))
            daily, hourly = summarize_events(res["events"])
            res["daily"] = daily
            res["hourly"] = hourly
            res["params"] = {
                "max_gap": int(max_gap),
                "min_gap_repeat": int(min_gap_repeat),
                "pair_min_repeat": int(pair_min_repeat),
                "date_range": (str(start_date), str(end_date)),
            }
            st.session_state.a33 = res

    if "a33" in st.session_state:
        res = st.session_state.a33
        fam_df = pd.DataFrame(res["family_rows"])
        pair_df = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in res["pair_rows"]])
        event_df = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in res["events"]])

        c1, c2, c3 = st.columns(3)
        c1.metric("Ritimli 3'lü aile", len(fam_df))
        c2.metric("3+3 çift", len(pair_df))
        c3.metric("Toplam 3+3=6/6 olay", len(event_df))

        st.subheader("3+3 çift özeti")
        st.dataframe(pair_df.head(1000), use_container_width=True, height=420)
        st.download_button("3+3 çiftlerin tamamı CSV", df_bytes(pair_df), "3arti3_ciftler.csv", "text/csv")

        st.subheader("Bütün 3+3=6/6 olayları")
        st.dataframe(event_df.head(1000), use_container_width=True, height=420)
        st.download_button("Bütün 3+3 olayları CSV", df_bytes(event_df), "3arti3_tum_olaylar.csv", "text/csv")

        with st.expander("Ritimli 3'lü ailelerin tamamı"):
            st.dataframe(fam_df, use_container_width=True, height=500)
            st.download_button("3'lü aileler CSV", df_bytes(fam_df), "ritimli_3lu_aileler.csv", "text/csv")
    else:
        st.info("Önce 3+3 TAM ANALİZİ BAŞLAT.")

# ============================================================
# TAB 2 — +77
# ============================================================
with tab2:
    st.subheader("+77 Küme‑Eko ve genel gap taraması")
    if "a33" not in st.session_state:
        st.info("Önce 3+3 sekmesinde TAM ANALİZİ çalıştır.")
    else:
        res = st.session_state.a33
        a, b, c = st.columns(3)
        with a:
            echo_gap = st.number_input("Eko gap", min_value=1, max_value=400, value=77, step=1)
        with b:
            min_cluster = st.number_input("Kaynak küme en az kaç 6/6?", min_value=1, max_value=200, value=6, step=1)
        with c:
            same_day = st.checkbox("Aynı gün içinde", value=True)

        src_rows, echo_rows = cluster_echo(
            records, res["pairsets"], int(echo_gap), int(min_cluster), bool(same_day)
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Kaynak küme", len(src_rows))
        c2.metric(f"+{int(echo_gap)} eko 6/6", len(echo_rows))
        c3.metric("Eko veren hedef çekiliş", len(set(r["Hedef Çekiliş"] for r in echo_rows)) if echo_rows else 0)

        if src_rows:
            st.dataframe(pd.DataFrame(src_rows).sort_values(["Echo 6/6 Adet", "Kaynak Küme"], ascending=False), use_container_width=True, height=300)
        if echo_rows:
            edf = pd.DataFrame(echo_rows)
            st.success(f"+{int(echo_gap)} ritminde {len(edf)} adet aynı 3+3 kupon tekrar 6/6 oldu.")
            st.dataframe(edf, use_container_width=True, height=420)
            st.download_button(f"+{int(echo_gap)} eko CSV", df_bytes(edf), f"plus_{int(echo_gap)}_eko.csv", "text/csv")
        else:
            st.warning(f"Seçili kurallarda +{int(echo_gap)} eko 6/6 bulunmadı.")

        st.divider()
        max_scan = st.slider("Ritim tarama üst gap", 20, 300, 200)
        if st.button("🔎 1→üst gap tüm küme-ekoları tara", use_container_width=True):
            with st.spinner("Küme-eko gap taraması yapılıyor..."):
                scan = scan_echo_gaps(records, res["pairsets"], int(max_scan), int(min_cluster), bool(same_day))
                st.session_state.echo_scan = scan
        if "echo_scan" in st.session_state:
            sdf = pd.DataFrame(st.session_state.echo_scan)
            st.dataframe(sdf.head(100), use_container_width=True, height=420)
            st.download_button("Tüm gap taraması CSV", df_bytes(sdf), "kume_eko_gap_taramasi.csv", "text/csv")

# ============================================================
# TAB 3 — 10'lu
# ============================================================
with tab3:
    st.subheader("Aynı 10'lu aile — 2 gün / 5 gün ritmi")
    st.write(
        "20 sayının bütün 10'lu kombinlerini körlemesine üretmez. "
        "Yalnız gün aralığı kadar uzak iki çekilişin kesişimi 10+ ise gerçek aday 10'luları çıkarır."
    )
    gaps = st.multiselect("Gün aralıkları", options=[1, 2, 3, 4, 5, 6, 7, 10], default=[2, 5])

    if st.button("🔟 10'LU RİTİM ANALİZİNİ BAŞLAT", type="primary", use_container_width=True):
        if not gaps:
            st.warning("En az bir gün aralığı seç.")
        else:
            with st.spinner("Aynı 10'lu aileler aranıyor..."):
                ten = analyze_10_rhythm(records, tuple(sorted(set(int(x) for x in gaps))))
                ten["gaps"] = tuple(gaps)
                st.session_state.ten = ten

    if "ten" in st.session_state:
        ten = st.session_state.ten
        rdf = pd.DataFrame(ten["repeats"])
        pdf = pd.DataFrame(ten["progressions"])
        sdf = pd.DataFrame(ten["special_812"])

        c1, c2, c3 = st.columns(3)
        c1.metric("Tekrar eden 10'lu", len(rdf))
        c2.metric("3 tarihli ritim dizisi", len(pdf))
        c3.metric("08→10→12 Ağustos aynı 10'lu", len(sdf))

        if not sdf.empty:
            st.success("✅ 8 Ağustos → 10 Ağustos → 12 Ağustos aynı 10'lu aile bulundu.")
            st.dataframe(sdf, use_container_width=True, height=260)
        else:
            st.info("Seçili veride 08→10→12 Ağustos üçlü dizisi bulunmadı veya bu tarihler veri aralığında değil.")

        st.subheader("3 tarihli aynı 10'lu ritimleri")
        if not pdf.empty:
            st.dataframe(pdf, use_container_width=True, height=400)
            st.download_button("10'lu 3-tarih ritimleri CSV", df_bytes(pdf), "10lu_3_tarih_ritimleri.csv", "text/csv")
        else:
            st.write("Yok.")

        st.subheader("2 / 5 gün ve seçilen diğer aralıklarda aynı 10'lular")
        if not rdf.empty:
            st.dataframe(rdf.head(2000), use_container_width=True, height=500)
            st.download_button("Tüm 10'lu tekrarlar CSV", df_bytes(rdf), "10lu_tum_tekrarlar.csv", "text/csv")
        else:
            st.write("Yok.")

# ============================================================
# TAB 4 — Gün/saat
# ============================================================
with tab4:
    st.subheader("Gün gün / saat saat")
    if "a33" not in st.session_state:
        st.info("3+3 analizi çalışınca burada gün ve saat özetleri oluşur.")
    else:
        daily = st.session_state.a33["daily"]
        hourly = st.session_state.a33["hourly"]

        st.markdown("**Günlük 3+3 özeti**")
        st.dataframe(daily, use_container_width=True, height=360)
        st.download_button("Günlük 3+3 CSV", df_bytes(daily), "3arti3_gunluk.csv", "text/csv")

        st.markdown("**Saatlik 3+3 özeti**")
        st.dataframe(hourly, use_container_width=True, height=500)
        st.download_button("Saatlik 3+3 CSV", df_bytes(hourly), "3arti3_saatlik.csv", "text/csv")

# ============================================================
# TAB 5 — ZIP
# ============================================================
with tab5:
    st.subheader("Tek ZIP — tüm yapılan analizler")
    files = {}
    meta = [
        f"Veri: {records[0][1].strftime('%d.%m.%Y %H:%M')} → {records[-1][1].strftime('%d.%m.%Y %H:%M')}",
        f"Çekiliş: {len(records)}",
        "Kaynak: GitHub veri.txt",
        "",
        "3+3: ritimli 3'lü aile → ayrık iki 3'lü → aynı çekilişte 6/6",
        "+77: kaynak 3+3 kümesindeki aynı pair'in 77 çekiliş sonra tekrar 6/6 olması",
        "10'lu: farklı günlerdeki iki 20'li çekilişin kesişiminden gerçek aynı 10'lu ailelerin çıkarılması",
    ]
    files["00_BILGI.txt"] = "\n".join(meta)

    if "a33" in st.session_state:
        a33 = st.session_state.a33
        fam_df = pd.DataFrame(a33["family_rows"])
        pair_df = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in a33["pair_rows"]])
        event_df = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in a33["events"]])
        files["01_3LU_AILELER.csv"] = df_bytes(fam_df)
        files["02_3ARTI3_CIFTLER.csv"] = df_bytes(pair_df)
        files["03_3ARTI3_TUM_OLAYLAR.csv"] = df_bytes(event_df)
        files["04_3ARTI3_GUNLUK.csv"] = df_bytes(a33["daily"])
        files["05_3ARTI3_SAATLIK.csv"] = df_bytes(a33["hourly"])
        src77, e77 = cluster_echo(records, a33["pairsets"], 77, 6, True)
        files["06_PLUS77_KAYNAKLAR.csv"] = df_bytes(pd.DataFrame(src77))
        files["07_PLUS77_EKOLAR.csv"] = df_bytes(pd.DataFrame(e77))

    if "echo_scan" in st.session_state:
        files["08_KUME_EKO_GAP_TARAMASI.csv"] = df_bytes(pd.DataFrame(st.session_state.echo_scan))

    if "ten" in st.session_state:
        ten = st.session_state.ten
        files["09_10LU_TUM_TEKRARLAR.csv"] = df_bytes(pd.DataFrame(ten["repeats"]))
        files["10_10LU_3_TARIH_RITIMLERI.csv"] = df_bytes(pd.DataFrame(ten["progressions"]))
        files["11_10LU_08_10_12_AGUSTOS.csv"] = df_bytes(pd.DataFrame(ten["special_812"]))

    zip_bytes = build_zip(files)
    st.download_button(
        "⬇️ TÜM RAPORLARI TEK ZIP İNDİR",
        zip_bytes,
        "HIZLI_ON_3ARTI3_PLUS77_10LU_TUM_RAPORLAR.zip",
        "application/zip",
        use_container_width=True,
    )

st.caption(
    "Not: Bu uygulama tarihsel örüntüleri çıkarır. Geçmişte tekrar eden ritimler gelecekte aynı şekilde tekrarlanmak zorunda değildir."
)
