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

APP_TITLE = "🧠 Hızlı On — Sağlam 3+3 / +77 / 10'lu Ritim"
DEFAULT_RAW_URL = "https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt"

st.set_page_config(page_title="Hızlı On Sağlam Motor", page_icon="🧠", layout="wide")
st.title(APP_TITLE)
st.caption("1 Ağustos–9 Ekim veri.txt • saat/gün • 3+3 aileler • +77 küme-eko • 2/5 gün 10'lu ritim")

# ============================================================
# Sabit kombinasyon tabloları — sadece 82.160 üçlü
# ============================================================
TRIPLES = np.array(list(combinations(range(1, 81), 3)), dtype=np.int16)
TCOUNT = len(TRIPLES)  # 82160
TRIPLE_KEYS = (
    TRIPLES[:, 0].astype(np.int32)
    | (TRIPLES[:, 1].astype(np.int32) << 7)
    | (TRIPLES[:, 2].astype(np.int32) << 14)
)
KEY_TO_RANK = np.full(1 << 21, -1, dtype=np.int32)
KEY_TO_RANK[TRIPLE_KEYS] = np.arange(TCOUNT, dtype=np.int32)
POS3 = np.array(list(combinations(range(20), 3)), dtype=np.int16)
P0, P1, P2 = POS3.T

# 80 bit = low64 + high16
TRI_LO = np.zeros(TCOUNT, dtype=np.uint64)
TRI_HI = np.zeros(TCOUNT, dtype=np.uint64)
for col in range(3):
    vals = TRIPLES[:, col]
    low = vals <= 64
    TRI_LO[low] |= np.left_shift(np.uint64(1), (vals[low] - 1).astype(np.uint64))
    TRI_HI[~low] |= np.left_shift(np.uint64(1), (vals[~low] - 65).astype(np.uint64))


def triple_name(rank: int) -> str:
    return "-".join(map(str, TRIPLES[int(rank)].tolist()))


def pair_code(a: int, b: int) -> int:
    if a > b:
        a, b = b, a
    return int(a) * TCOUNT + int(b)


def decode_pair(code: int):
    return divmod(int(code), TCOUNT)


def pair_coupon(code: int) -> str:
    a, b = decode_pair(code)
    nums = sorted(set(TRIPLES[a].tolist()) | set(TRIPLES[b].tolist()))
    return "-".join(map(str, nums))


def nums_to_split_mask(nums):
    lo = 0
    hi = 0
    for n in nums:
        if n <= 64:
            lo |= 1 << (int(n) - 1)
        else:
            hi |= 1 << (int(n) - 65)
    return np.uint64(lo), np.uint64(hi)


def split_mask_to_nums(lo: int, hi: int):
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


# ============================================================
# Veri
# ============================================================
@st.cache_data(ttl=90, show_spinner=False)
def fetch_text(url: str, cache_bust: int = 0) -> str:
    sep = "&" if "?" in url else "?"
    r = requests.get(
        f"{url}{sep}_cb={cache_bust}", timeout=30,
        headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
    r.raise_for_status()
    return r.text


@st.cache_data(show_spinner=False)
def parse_veri(text: str):
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
        if draw_id in seen or len(nums) != 20 or len(set(nums)) != 20 or not all(1 <= n <= 80 for n in nums):
            continue
        seen.add(draw_id)
        lo, hi = nums_to_split_mask(nums)
        rows.append((draw_id, dt, nums, lo, hi))
    rows.sort(key=lambda r: r[1])
    return rows


def draw_triple_ids(nums):
    n = np.asarray(nums, dtype=np.int32)
    keys = n[P0] | (n[P1] << 7) | (n[P2] << 14)
    return KEY_TO_RANK[keys]


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
# 3'lü aile — sabit bellekli hızlı tarama
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
            progress.progress(min(0.45, 0.45 * (pos + 1) / nrec), text=f"3'lü aile ritimleri: {pos+1:,}/{nrec:,}")

    body = gaps[:, 1:]
    best_count = body.max(axis=1)
    best_gap = body.argmax(axis=1) + 1
    return freq, best_gap, best_count


def choose_families(freq, best_gap, best_count, requested_min=7, safe_limit=500, auto_safe=True):
    threshold = int(requested_min)
    if auto_safe:
        while threshold < 100 and int(np.sum(best_count >= threshold)) > int(safe_limit):
            threshold += 1
    qualified = np.where(best_count >= threshold)[0]
    # strongest first; safety hard-cap remains even if auto is off
    score_order = np.lexsort((qualified, -freq[qualified].astype(np.int32), -best_count[qualified].astype(np.int32)))
    ordered = qualified[score_order]
    selected = ordered[: int(safe_limit)]
    return threshold, qualified, selected


def mine_pairs_safe(records, selected_families, pair_min_repeat=3, progress=None):
    selected_flag = np.zeros(TCOUNT, dtype=bool)
    selected_flag[selected_families] = True
    active = []
    counts = Counter()
    nrec = len(records)

    for pos, r in enumerate(records):
        ids = draw_triple_ids(r[2])
        arr = ids[selected_flag[ids]]
        active.append(arr.astype(np.int32, copy=False))
        L = len(arr)
        for ii in range(L - 1):
            rest = arr[ii + 1 :]
            dis = ((TRI_LO[arr[ii]] & TRI_LO[rest]) == 0) & ((TRI_HI[arr[ii]] & TRI_HI[rest]) == 0)
            rr = rest[dis]
            if len(rr):
                codes = arr[ii].astype(np.int64) * TCOUNT + rr.astype(np.int64)
                counts.update(map(int, codes.tolist()))
        if progress is not None and (pos % 400 == 0 or pos + 1 == nrec):
            progress.progress(0.45 + 0.30 * (pos + 1) / nrec, text=f"3+3 çiftleri: {pos+1:,}/{nrec:,}")

    eligible = {c: n for c, n in counts.items() if n >= int(pair_min_repeat)}
    eligible_set = set(eligible)
    pairsets = []
    events = []
    day_hits = defaultdict(lambda: defaultdict(list))

    for idx, arr in enumerate(active):
        local = set()
        L = len(arr)
        for ii in range(L - 1):
            rest = arr[ii + 1 :]
            dis = ((TRI_LO[arr[ii]] & TRI_LO[rest]) == 0) & ((TRI_HI[arr[ii]] & TRI_HI[rest]) == 0)
            for b in rest[dis]:
                c = pair_code(int(arr[ii]), int(b))
                if c in eligible_set:
                    local.add(c)
        pairsets.append(local)
        if local:
            draw_id, dt = records[idx][0], records[idx][1]
            for c in local:
                a, b = decode_pair(c)
                day_hits[c][dt.date()].append(idx)
                events.append({
                    "_idx": idx, "_pair": c,
                    "Çekiliş": draw_id, "Tarih": dt.date(), "Saat": dt.strftime("%H:%M"),
                    "Aile A": triple_name(a), "Aile B": triple_name(b),
                    "6'lı Kupon": pair_coupon(c), "Pair Toplam 6/6": int(eligible[c]),
                })
        if progress is not None and (idx % 500 == 0 or idx + 1 == nrec):
            progress.progress(0.75 + 0.25 * (idx + 1) / nrec, text=f"Olay raporu: {idx+1:,}/{nrec:,}")

    pair_rows = []
    for c, total in sorted(eligible.items(), key=lambda kv: (-kv[1], kv[0])):
        a, b = decode_pair(c)
        perday = day_hits[c]
        same2 = sum(len(v) >= 2 for v in perday.values())
        same3 = sum(len(v) >= 3 for v in perday.values())
        hits = sorted(i for vv in perday.values() for i in vv)
        gc = Counter(y - x for x, y in zip(hits, hits[1:]))
        mg, mn = gc.most_common(1)[0] if gc else ("", 0)
        pair_rows.append({
            "_pair": c, "Aile A": triple_name(a), "Aile B": triple_name(b),
            "6'lı Kupon": pair_coupon(c), "Toplam 6/6": int(total), "Aktif Gün": len(perday),
            "Aynı Gün 2+ Gün": same2, "Aynı Gün 3+ Gün": same3,
            "En Sık Pair Gap": mg, "Gap Tekrar": mn,
        })
    return active, pairsets, pair_rows, events


def summarize_events(events):
    if not events:
        return pd.DataFrame(), pd.DataFrame()
    e = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in events])
    daily = e.groupby("Tarih", as_index=False).agg(**{
        "3+3 Olay": ("Çekiliş", "size"), "Farklı 6'lı": ("6'lı Kupon", "nunique"), "Aktif Çekiliş": ("Çekiliş", "nunique")
    }).sort_values("Tarih")
    t = e.copy(); t["SaatDilimi"] = t["Saat"].str[:2] + ":00"
    hourly = t.groupby(["Tarih", "SaatDilimi"], as_index=False).agg(**{
        "3+3 Olay": ("Çekiliş", "size"), "Farklı 6'lı": ("6'lı Kupon", "nunique"), "Aktif Çekiliş": ("Çekiliş", "nunique")
    }).sort_values(["Tarih", "SaatDilimi"])
    return daily, hourly


# ============================================================
# +77 küme-eko
# ============================================================
def cluster_echo(records, pairsets, gap=77, min_cluster=6, same_day_only=True):
    src_rows, rows = [], []
    n = len(records)
    for i, src in enumerate(pairsets):
        if len(src) < int(min_cluster):
            continue
        j = i + int(gap)
        if j >= n:
            continue
        if same_day_only and records[i][1].date() != records[j][1].date():
            continue
        inter = src & pairsets[j]
        src_rows.append({
            "Kaynak Çekiliş": records[i][0], "Kaynak": records[i][1].strftime("%d.%m.%Y %H:%M"),
            "Kaynak Küme": len(src), "Hedef Çekiliş": records[j][0], "Hedef": records[j][1].strftime("%d.%m.%Y %H:%M"),
            "Echo 6/6 Adet": len(inter),
        })
        for c in sorted(inter):
            a, b = decode_pair(c)
            rows.append({
                "Gap": int(gap), "Kaynak Çekiliş": records[i][0], "Kaynak": records[i][1].strftime("%d.%m.%Y %H:%M"),
                "Kaynak Küme": len(src), "Hedef Çekiliş": records[j][0], "Hedef": records[j][1].strftime("%d.%m.%Y %H:%M"),
                "Aile A": triple_name(a), "Aile B": triple_name(b), "6'lı Kupon": pair_coupon(c), "Sonuç": "6/6 EKO",
            })
    return src_rows, rows


def scan_echo_gaps(records, pairsets, max_gap=200, min_cluster=6, same_day_only=True):
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
                ed += 1; ep += k
        if srcn:
            out.append({"Gap": gap, "Kaynak Küme": srcn, "Echo Olan Hedef": ed, "Echo 6/6 Adet": ep,
                        "Kaynak Başına Echo": round(ep/srcn, 4)})
    return sorted(out, key=lambda r: (-r["Echo 6/6 Adet"], -r["Kaynak Başına Echo"], r["Gap"]))


# ============================================================
# 10'lu ritim — doğrudan gün çiftlerinden, tekrar tarama YOK
# ============================================================
def date_map(records):
    out = defaultdict(list)
    for i, r in enumerate(records):
        out[r[1].date()].append(i)
    return out


def expand_intersection_to_10(lo, hi, max_expand_size=14):
    nums = split_mask_to_nums(int(lo), int(hi))
    k = len(nums)
    if k < 10:
        return [], k
    if k > int(max_expand_size):
        return None, k
    return list(combinations(nums, 10)), k


def analyze_10_rhythm_fast(records, day_gaps=(2,5), max_expand_size=14, progress=None):
    bydate = date_map(records)
    dates = sorted(bydate)
    dset = set(dates)
    # family -> gap -> date-pair -> occurrence info
    fam_events = defaultdict(lambda: defaultdict(dict))
    big_blocks = []
    work = [(g,d) for g in day_gaps for d in dates if d + timedelta(days=int(g)) in dset]
    total_work = max(1, len(work)); done = 0

    for gap in day_gaps:
        gap = int(gap)
        for d in dates:
            d2 = d + timedelta(days=gap)
            if d2 not in dset:
                continue
            I, J = bydate[d], bydate[d2]
            lo1 = np.array([records[i][3] for i in I], dtype=np.uint64)[:,None]
            hi1 = np.array([records[i][4] for i in I], dtype=np.uint64)[:,None]
            lo2 = np.array([records[j][3] for j in J], dtype=np.uint64)[None,:]
            hi2 = np.array([records[j][4] for j in J], dtype=np.uint64)[None,:]
            il = lo1 & lo2; ih = hi1 & hi2
            bc = np.bitwise_count(il) + np.bitwise_count(ih)
            rr, cc = np.where(bc >= 10)

            for a, b in zip(rr.tolist(), cc.tolist()):
                inter_lo, inter_hi = il[a,b], ih[a,b]
                fams, size = expand_intersection_to_10(inter_lo, inter_hi, max_expand_size)
                if fams is None:
                    big_blocks.append({
                        "Gün Aralığı": gap, "1. Gün": d, "2. Gün": d2,
                        "Ortak Blok Boyutu": int(size), "Ortak Blok": "-".join(map(str, split_mask_to_nums(inter_lo, inter_hi))),
                        "1. Saat": records[I[a]][1].strftime("%H:%M"), "2. Saat": records[J[b]][1].strftime("%H:%M"),
                        "Not": f"Güvenlik için {max_expand_size}'ten büyük blok 10'lulara açılmadı",
                    })
                    continue
                for fam in fams:
                    key = (d, d2)
                    e = fam_events[fam][gap].get(key)
                    if e is None:
                        fam_events[fam][gap][key] = {
                            "count": 1,
                            "t1": records[I[a]][1].strftime("%H:%M"),
                            "t2": records[J[b]][1].strftime("%H:%M"),
                        }
                    else:
                        e["count"] += 1
            done += 1
            if progress is not None:
                progress.progress(min(1.0, done/total_work), text=f"10'lu ritim: {done}/{total_work} gün çifti")

    repeat_rows = []
    progression_rows = []
    special_812 = []

    for fam, gapmap in fam_events.items():
        famtxt = "-".join(map(str, fam))
        for gap, pairs in gapmap.items():
            if not pairs:
                continue
            sorted_pairs = sorted(pairs)
            dates_used = sorted(set(x for ab in sorted_pairs for x in ab))
            repeat_rows.append({
                "Gün Aralığı": gap, "10'lu Aile": famtxt,
                "Gün Çifti Adet": len(sorted_pairs), "Tekrar Eden Gün Sayısı": len(dates_used),
                "İlk Gün": dates_used[0], "Son Gün": dates_used[-1],
                "Örnek": " | ".join(f"{a.strftime('%d.%m')} {pairs[(a,b)]['t1']} → {b.strftime('%d.%m')} {pairs[(a,b)]['t2']}" for a,b in sorted_pairs[:6]),
            })
            pairset = set(sorted_pairs)
            for d, d2 in sorted_pairs:
                d3 = d2 + timedelta(days=gap)
                if (d2, d3) in pairset:
                    row = {
                        "Ritim": f"+{gap} gün, +{gap} gün", "10'lu Aile": famtxt,
                        "1. Gün": d, "2. Gün": d2, "3. Gün": d3,
                        "1→2 Saat": f"{pairs[(d,d2)]['t1']}→{pairs[(d,d2)]['t2']}",
                        "2→3 Saat": f"{pairs[(d2,d3)]['t1']}→{pairs[(d2,d3)]['t2']}",
                    }
                    progression_rows.append(row)
                    if gap == 2 and d.strftime("%d.%m.%Y") == "08.08.2026":
                        special_812.append(row.copy())

    # dedupe progressions
    seen=set(); pp=[]
    for r in progression_rows:
        k=(r["Ritim"],r["10'lu Aile"],r["1. Gün"],r["2. Gün"],r["3. Gün"])
        if k not in seen:
            seen.add(k); pp.append(r)
    progression_rows=pp
    repeat_rows.sort(key=lambda r:(r["Gün Aralığı"], -r["Gün Çifti Adet"], r["10'lu Aile"]))
    progression_rows.sort(key=lambda r:(r["Ritim"], r["1. Gün"], r["10'lu Aile"]))
    special_812.sort(key=lambda r:r["10'lu Aile"])
    return {"repeats":repeat_rows, "progressions":progression_rows, "special_812":special_812, "big_blocks":big_blocks}


# ============================================================
# UI / veri
# ============================================================
with st.sidebar:
    st.header("Veri Kaynağı")
    raw_url = st.text_input("GitHub raw veri.txt", value=DEFAULT_RAW_URL)
    if "cache_bust" not in st.session_state:
        st.session_state.cache_bust = 0
    if st.button("🔄 GitHub verisini yenile", use_container_width=True):
        st.session_state.cache_bust = int(time.time())
        st.cache_data.clear()
        for k in ["a33v2","echo_scan_v2","tenv2"]:
            st.session_state.pop(k, None)
        st.rerun()

try:
    text = fetch_text(raw_url, int(st.session_state.cache_bust))
    all_records = parse_veri(text)
except Exception as e:
    st.error(f"veri.txt okunamadı: {e}")
    st.stop()

if not all_records:
    st.error("Geçerli çekiliş bulunamadı.")
    st.stop()

all_dates=[r[1].date() for r in all_records]
min_date,max_date=min(all_dates),max(all_dates)
with st.sidebar:
    st.success(f"{len(all_records):,} çekiliş • {min_date.strftime('%d.%m.%Y')} → {max_date.strftime('%d.%m.%Y')}")
    start_date=st.date_input("Başlangıç", value=min_date, min_value=min_date, max_value=max_date)
    end_date=st.date_input("Bitiş", value=max_date, min_value=min_date, max_value=max_date)
    if start_date>end_date:
        st.error("Başlangıç bitişten büyük olamaz."); st.stop()

records=[r for r in all_records if start_date <= r[1].date() <= end_date]
if not records:
    st.stop()

if min_date <= datetime(2026,8,1).date() and max_date >= datetime(2026,10,9).date():
    st.success("✅ 1 Ağustos–9 Ekim kapsaması veri.txt içinde görünüyor.")
else:
    st.warning(f"Görünen kapsam: {min_date.strftime('%d.%m.%Y')}–{max_date.strftime('%d.%m.%Y')}")

sig=(str(start_date),str(end_date),len(records),records[0][0],records[-1][0])
if st.session_state.get("data_sig") != sig:
    st.session_state.data_sig=sig
    for k in ["a33v2","echo_scan_v2","tenv2"]:
        st.session_state.pop(k,None)


tab0,tab1,tab2,tab3,tab4,tab5=st.tabs(["📌 Veri","🧬 3+3 Aileler","🎯 +77 Küme-Eko","🔟 10'lu Ritim","🕐 Gün/Saat","📦 Rapor"])

with tab0:
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Çekiliş",f"{len(records):,}")
    c2.metric("Gün",len(set(r[1].date() for r in records)))
    c3.metric("İlk",records[0][1].strftime("%d.%m.%Y %H:%M"))
    c4.metric("Son",records[-1][1].strftime("%d.%m.%Y %H:%M"))
    dc=Counter(r[1].date() for r in records)
    st.dataframe(pd.DataFrame([{"Tarih":d,"Çekiliş":n} for d,n in sorted(dc.items())]),use_container_width=True,height=420)

with tab1:
    st.subheader("3+3 — çökmeden tam ritim madenciliği")
    st.caption("Bütün 82.160 üçlü taranır. 3+3 çift aşamasında yalnız en güçlü ritimli aile havuzu kullanılır; böylece Streamlit belleği taşmaz.")
    a,b,c,d=st.columns(4)
    with a: max_gap=st.number_input("Exact gap üst sınırı",10,217,60,1)
    with b: minrep=st.number_input("Başlangıç gap tekrar eşiği",2,50,7,1)
    with c: famcap=st.number_input("Güvenli aile havuzu limiti",100,1500,500,50)
    with d: pairmin=st.number_input("3+3 çift min 6/6",1,30,3,1)
    autosafe=st.checkbox("Aile sayısı fazlaysa eşiği otomatik yükselt (önerilen)",value=True)

    if st.button("🚀 3+3 ANALİZİNİ BAŞLAT",type="primary",use_container_width=True):
        prog=st.progress(0,text="Başlıyor...")
        freq,bgap,bcount=mine_triples_dense(records,int(max_gap),prog)
        eff,qualified,selected=choose_families(freq,bgap,bcount,int(minrep),int(famcap),bool(autosafe))
        prog.progress(0.45,text=f"Ritimli aile: {len(qualified):,} • 3+3 havuzu: {len(selected):,}")
        active,pairsets,pair_rows,events=mine_pairs_safe(records,selected,int(pairmin),prog)
        daily,hourly=summarize_events(events)
        fam_rows=[{
            "3'lü Aile":triple_name(int(k)),"3/3 Görünüş":int(freq[k]),"En Güçlü Exact Gap":int(bgap[k]),"Gap Tekrar":int(bcount[k]),
            "3+3 Havuzunda":"EVET" if int(k) in set(map(int,selected)) else "HAYIR"
        } for k in qualified]
        fam_rows.sort(key=lambda r:(-r["Gap Tekrar"],-r["3/3 Görünüş"],r["3'lü Aile"]))
        st.session_state.a33v2={"family_rows":fam_rows,"pair_rows":pair_rows,"events":events,"pairsets":pairsets,"daily":daily,"hourly":hourly,
                                     "effective":eff,"qualified_n":len(qualified),"selected_n":len(selected),"params":(max_gap,minrep,famcap,pairmin,autosafe)}
        prog.progress(1.0,text="Tamamlandı ✅")

    if "a33v2" in st.session_state:
        r=st.session_state.a33v2
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Tüm ritimli 3'lü",r["qualified_n"])
        c2.metric("3+3 güvenli havuz",r["selected_n"])
        c3.metric("Etkin gap tekrar eşiği",r["effective"])
        c4.metric("3+3 çift",len(r["pair_rows"]))
        if r["qualified_n"]>r["selected_n"]:
            st.info(f"Tüm {r['qualified_n']:,} ritimli aile raporlandı; çökme olmaması için 3+3 çift hesabında en güçlü {r['selected_n']:,} aile kullanıldı.")
        pdf=pd.DataFrame([{k:v for k,v in x.items() if not k.startswith('_')} for x in r["pair_rows"]])
        edf=pd.DataFrame([{k:v for k,v in x.items() if not k.startswith('_')} for x in r["events"]])
        fdf=pd.DataFrame(r["family_rows"])
        st.subheader("3+3 çift özeti")
        st.dataframe(pdf.head(2000),use_container_width=True,height=420)
        st.download_button("3+3 çiftler CSV",df_bytes(pdf),"3arti3_ciftler.csv","text/csv")
        st.subheader("Bütün 3+3=6/6 olayları")
        st.dataframe(edf.head(2000),use_container_width=True,height=420)
        st.download_button("3+3 olaylar CSV",df_bytes(edf),"3arti3_tum_olaylar.csv","text/csv")
        with st.expander("Bütün ritimli 3'lü aileler"):
            st.dataframe(fdf,use_container_width=True,height=500)
            st.download_button("3'lü aileler CSV",df_bytes(fdf),"ritimli_3lu_aileler.csv","text/csv")
    else:
        st.info("3+3 analizini başlat.")

with tab2:
    st.subheader("+77 Küme‑Eko")
    if "a33v2" not in st.session_state:
        st.info("Önce 3+3 analizini çalıştır.")
    else:
        r=st.session_state.a33v2
        a,b,c=st.columns(3)
        with a: egap=st.number_input("Eko gap",1,400,77,1)
        with b: mincluster=st.number_input("Kaynak küme min 6/6",1,200,6,1)
        with c: sameday=st.checkbox("Aynı gün içinde",value=True)
        src,echo=cluster_echo(records,r["pairsets"],int(egap),int(mincluster),bool(sameday))
        c1,c2,c3=st.columns(3)
        c1.metric("Kaynak küme",len(src)); c2.metric(f"+{egap} eko 6/6",len(echo)); c3.metric("Eko hedef çekiliş",len(set(x["Hedef Çekiliş"] for x in echo)) if echo else 0)
        if src: st.dataframe(pd.DataFrame(src).sort_values(["Echo 6/6 Adet","Kaynak Küme"],ascending=False),use_container_width=True,height=300)
        if echo:
            e=pd.DataFrame(echo); st.dataframe(e,use_container_width=True,height=420); st.download_button("Eko CSV",df_bytes(e),f"plus_{egap}_eko.csv","text/csv")
        else: st.warning("Bu ayarda eko 6/6 yok.")
        maxscan=st.slider("Tüm eko gap tarama üst sınırı",20,300,200)
        if st.button("🔎 1→üst gap tara",use_container_width=True):
            st.session_state.echo_scan_v2=scan_echo_gaps(records,r["pairsets"],int(maxscan),int(mincluster),bool(sameday))
        if "echo_scan_v2" in st.session_state:
            sdf=pd.DataFrame(st.session_state.echo_scan_v2); st.dataframe(sdf.head(200),use_container_width=True,height=420)
            st.download_button("Tüm eko gap CSV",df_bytes(sdf),"kume_eko_gap_taramasi.csv","text/csv")

with tab3:
    st.subheader("10'lu aile — 2 / 5 gün ve 08→10→12 Ağustos")
    st.caption("Eski sürümdeki çöküşün ana nedenlerinden biri buydu. Bu motor aynı 10'luları doğrudan gün çiftlerindeki ortak sayılardan çıkarır; sonra bütün veriyi aile aile tekrar taramaz.")
    gaps=st.multiselect("Gün aralıkları",[1,2,3,4,5,6,7,10],default=[2,5])
    maxexpand=st.slider("Ortak blok en fazla kaç sayıya kadar 10'lulara açılsın?",10,15,14)
    if st.button("🔟 10'LU RİTİM ANALİZİNİ BAŞLAT",type="primary",use_container_width=True):
        if not gaps:
            st.warning("En az bir gün aralığı seç.")
        else:
            prog=st.progress(0,text="10'lu ritimler hazırlanıyor...")
            st.session_state.tenv2=analyze_10_rhythm_fast(records,tuple(sorted(set(map(int,gaps)))),int(maxexpand),prog)
            prog.progress(1.0,text="Tamamlandı ✅")
    if "tenv2" in st.session_state:
        t=st.session_state.tenv2
        rdf=pd.DataFrame(t["repeats"]); pdf=pd.DataFrame(t["progressions"]); sdf=pd.DataFrame(t["special_812"]); bdf=pd.DataFrame(t["big_blocks"])
        c1,c2,c3=st.columns(3)
        c1.metric("Tekrar eden 10'lu",len(rdf)); c2.metric("3 tarihli ritim",len(pdf)); c3.metric("08→10→12 aynı 10'lu",len(sdf))
        if not sdf.empty:
            st.success("✅ 08.08 → 10.08 → 12.08 aynı 10'lu aile(ler) bulundu.")
            st.dataframe(sdf,use_container_width=True,height=320)
        else: st.info("08→10→12 exact aynı 10'lu bulunmadı.")
        st.subheader("3 tarihli 10'lu ritimler")
        if not pdf.empty: st.dataframe(pdf,use_container_width=True,height=420); st.download_button("3 tarih ritimleri CSV",df_bytes(pdf),"10lu_3_tarih_ritimleri.csv","text/csv")
        else: st.write("Yok.")
        st.subheader("2/5 gün ve seçilen diğer aralıklarda tekrar eden 10'lular")
        if not rdf.empty: st.dataframe(rdf.head(3000),use_container_width=True,height=500); st.download_button("Tüm 10'lu tekrarlar CSV",df_bytes(rdf),"10lu_tum_tekrarlar.csv","text/csv")
        else: st.write("Yok.")
        if not bdf.empty:
            with st.expander("15+ gibi açılmayan büyük ortak bloklar"):
                st.dataframe(bdf,use_container_width=True,height=300)

with tab4:
    st.subheader("Gün gün / saat saat 3+3")
    if "a33v2" not in st.session_state:
        st.info("3+3 analizi çalışınca oluşur.")
    else:
        ddf=st.session_state.a33v2["daily"]; hdf=st.session_state.a33v2["hourly"]
        st.markdown("**Günlük**"); st.dataframe(ddf,use_container_width=True,height=360); st.download_button("Günlük CSV",df_bytes(ddf),"3arti3_gunluk.csv","text/csv")
        st.markdown("**Saatlik**"); st.dataframe(hdf,use_container_width=True,height=500); st.download_button("Saatlik CSV",df_bytes(hdf),"3arti3_saatlik.csv","text/csv")

with tab5:
    st.subheader("Tek ZIP")
    files={"00_BILGI.txt":f"Veri: {records[0][1]} -> {records[-1][1]}\nÇekiliş: {len(records)}\nSağlam V2 motoru\n"}
    if "a33v2" in st.session_state:
        r=st.session_state.a33v2
        files["01_3LU_AILELER.csv"]=df_bytes(pd.DataFrame(r["family_rows"]))
        files["02_3ARTI3_CIFTLER.csv"]=df_bytes(pd.DataFrame([{k:v for k,v in x.items() if not k.startswith('_')} for x in r["pair_rows"]]))
        files["03_3ARTI3_OLAYLAR.csv"]=df_bytes(pd.DataFrame([{k:v for k,v in x.items() if not k.startswith('_')} for x in r["events"]]))
        files["04_GUNLUK.csv"]=df_bytes(r["daily"]); files["05_SAATLIK.csv"]=df_bytes(r["hourly"])
        s,e=cluster_echo(records,r["pairsets"],77,6,True)
        files["06_PLUS77_KAYNAK.csv"]=df_bytes(pd.DataFrame(s)); files["07_PLUS77_EKO.csv"]=df_bytes(pd.DataFrame(e))
    if "echo_scan_v2" in st.session_state:
        files["08_EKO_GAP.csv"]=df_bytes(pd.DataFrame(st.session_state.echo_scan_v2))
    if "tenv2" in st.session_state:
        t=st.session_state.tenv2
        files["09_10LU_TEKRAR.csv"]=df_bytes(pd.DataFrame(t["repeats"])); files["10_10LU_3TARIH.csv"]=df_bytes(pd.DataFrame(t["progressions"])); files["11_08_10_12.csv"]=df_bytes(pd.DataFrame(t["special_812"])); files["12_BUYUK_ORTAK_BLOKLAR.csv"]=df_bytes(pd.DataFrame(t["big_blocks"]))
    st.download_button("⬇️ TÜM RAPORLARI ZIP İNDİR",build_zip(files),"HIZLI_ON_SAGLAM_V2_TUM_RAPORLAR.zip","application/zip",use_container_width=True)

st.caption("Bu sürüm Streamlit Cloud için bellek kontrollü tasarlanmıştır. Geçmiş ritimler gelecekte sonucu garanti etmez.")
