# -*- coding: utf-8 -*-
import io
import math
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from itertools import combinations

import numpy as np
import pandas as pd
import requests
import streamlit as st

APP_TITLE = "🎯 Hızlı On — 7•8•9 Ritim Nokta Merkezi V1"
DEFAULT_RAW_URL = "https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt"

st.set_page_config(page_title="7•8•9 Ritim Nokta Merkezi", page_icon="🎯", layout="wide")
st.title(APP_TITLE)
st.caption(
    "Normal 7’li • 8’li • 9’lu aileler | günler arası exact ritim | +2/+5/+7/+14 | "
    "dar çekirdek | çoklu-gap | aynı gün tekrar | canlı ritim kuponu"
)
st.info(
    "Bu motor 7/8/9 aileleri brute-force üretmez. Yalnız seçilen gün aralıklarında iki günde gerçekten "
    "ortak görülen aileleri çıkarır, aynı exact ritmi tekrar edenleri doğrular. Böylece Streamlit belleği korunur."
)

# ============================================================
# YARDIMCILAR
# ============================================================
def nums_to_split_mask(nums):
    lo = 0
    hi = 0
    for n in nums:
        n = int(n)
        if n <= 64:
            lo |= 1 << (n - 1)
        else:
            hi |= 1 << (n - 65)
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


# C(80, 9) uint64 içine rahat sığar.
CHOOSE = np.zeros((81, 10), dtype=np.uint64)
for n in range(81):
    for k in range(min(9, n) + 1):
        CHOOSE[n, k] = np.uint64(math.comb(n, k))


def combo_rank(combo):
    # Colex combinadic rank. combo 1..80 sıralı.
    s = 0
    for i, n in enumerate(combo, 1):
        s += int(CHOOSE[int(n) - 1, i])
    return np.uint64(s)


def combo_unrank(rank, k):
    r = int(rank)
    c = [0] * k
    upper = 79
    for i in range(k, 0, -1):
        x = upper
        while x >= i and int(CHOOSE[x, i]) > r:
            x -= 1
        c[i - 1] = x + 1
        r -= int(CHOOSE[x, i])
        upper = x - 1
    return tuple(c)


def family_name(rank, k):
    return "-".join(map(str, combo_unrank(int(rank), k)))


def family_mask(rank, k):
    return nums_to_split_mask(combo_unrank(int(rank), k))


def date_map(records):
    out = defaultdict(list)
    for i, r in enumerate(records):
        out[r[1].date()].append(i)
    return out


def safe_dataframe(data, max_rows=250):
    if not isinstance(data, pd.DataFrame):
        data = pd.DataFrame(data)
    if data.empty:
        st.info("Gösterilecek kayıt yok.")
        return
    df = data.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%d.%m.%Y")
        elif pd.api.types.is_object_dtype(df[c]):
            df[c] = df[c].map(lambda x: "" if x is None else str(x))
    shown = df.head(max_rows)
    html = shown.to_html(index=False, escape=True, border=0)
    st.markdown(
        """
        <style>
        .ho-wrap{overflow-x:auto;max-width:100%;border:1px solid #ddd;border-radius:8px}
        .ho-wrap table{border-collapse:collapse;width:max-content;min-width:100%;font-size:.84rem}
        .ho-wrap th,.ho-wrap td{padding:6px 9px;border-bottom:1px solid #eee;white-space:nowrap;text-align:left}
        .ho-wrap th{position:sticky;top:0;background:#f6f7f9;z-index:1}
        </style>
        <div class="ho-wrap">""" + html + "</div>",
        unsafe_allow_html=True,
    )
    if len(df) > len(shown):
        st.caption(f"Ekranda ilk {len(shown)} / {len(df)} kayıt. Tam liste CSV/ZIP raporunda.")


def df_bytes(df):
    return df.to_csv(index=False).encode("utf-8-sig")


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
# RİTİM MADENCİLİĞİ
# ============================================================
def local_family_ranks(records, idx1, idx2, k):
    """İki gün arasında gerçekten ortak görülen k'lı aileleri exact ve tekil üretir."""
    if not idx1 or not idx2:
        return np.empty(0, dtype=np.uint64), 0, 0

    lo1 = np.array([records[i][3] for i in idx1], dtype=np.uint64)[:, None]
    hi1 = np.array([records[i][4] for i in idx1], dtype=np.uint64)[:, None]
    lo2 = np.array([records[j][3] for j in idx2], dtype=np.uint64)[None, :]
    hi2 = np.array([records[j][4] for j in idx2], dtype=np.uint64)[None, :]

    il = lo1 & lo2
    ih = hi1 & hi2
    bc = np.bitwise_count(il) + np.bitwise_count(ih)
    rr, cc = np.where(bc >= int(k))
    qualifying_draw_pairs = int(len(rr))
    max_common = int(bc.max()) if bc.size else 0
    if qualifying_draw_pairs == 0:
        return np.empty(0, dtype=np.uint64), max_common, 0

    # Aynı ortak blok bir gün çiftinde yüzlerce kez oluşsa bile bir kez genişlet.
    blocks = set()
    for a, b in zip(rr.tolist(), cc.tolist()):
        blocks.add(int(il[a, b]) | (int(ih[a, b]) << 64))

    ranks = set()
    for mask in blocks:
        nums = []
        x = mask
        while x:
            lsb = x & -x
            nums.append(lsb.bit_length())
            x ^= lsb
        # overlap 20'yi geçemez; büyük bloklar nadir. Hepsi exact doğrulanır.
        for cmb in combinations(nums, int(k)):
            ranks.add(int(combo_rank(cmb)))

    arr = np.fromiter(ranks, dtype=np.uint64, count=len(ranks))
    arr.sort()
    return arr, max_common, qualifying_draw_pairs


def longest_link_chain(starts, gap):
    starts = sorted(set(starts))
    if not starts:
        return 0, None, None
    best_len = 1
    cur_len = 1
    cur_start = starts[0]
    best_start = starts[0]
    best_end_start = starts[0]
    for prev, now in zip(starts, starts[1:]):
        if (now - prev).days == int(gap):
            cur_len += 1
        else:
            cur_len = 1
            cur_start = now
        # eşitlikte daha güncel zinciri seç
        if cur_len > best_len or (cur_len == best_len and now > best_end_start):
            best_len = cur_len
            best_start = cur_start
            best_end_start = now
    return best_len + 1, best_start, best_end_start + timedelta(days=int(gap))


def smart_core_threshold(k, same_as_six=False):
    if same_as_six or int(k) == 7:
        return 3, 4  # 3 bağ / 4 tarih
    # 8 ve 9'da exact tekrar çok daha nadir: 2 bağ / 3 tarih çekirdek kabul edilir.
    return 2, 3


def verify_family(records, rank, k):
    lo, hi = family_mask(rank, k)
    hit_idx = []
    for i, r in enumerate(records):
        if (r[3] & lo) == lo and (r[4] & hi) == hi:
            hit_idx.append(i)
    byday = Counter(records[i][1].date() for i in hit_idx)
    byhour = Counter(records[i][1].hour for i in hit_idx)

    # Aynı gün çekiliş-gap ritmi
    same_day_gaps = Counter()
    daily = defaultdict(list)
    for i in hit_idx:
        daily[records[i][1].date()].append(i)
    for inds in daily.values():
        inds.sort()
        for a, b in zip(inds, inds[1:]):
            same_day_gaps[b - a] += 1

    best_draw_gap = ""
    best_draw_gap_n = 0
    if same_day_gaps:
        g, n = same_day_gaps.most_common(1)[0]
        best_draw_gap = int(g)
        best_draw_gap_n = int(n)

    return {
        "Toplam Görünüş": len(hit_idx),
        "Aktif Gün": len(byday),
        "Aynı Gün Maks": max(byday.values()) if byday else 0,
        "Baskın Saat": byhour.most_common(1)[0][0] if byhour else "",
        "Saat Tekrar": byhour.most_common(1)[0][1] if byhour else 0,
        "Aynı Gün En Sık Çekiliş Gap": best_draw_gap,
        "Çekiliş Gap Tekrar": best_draw_gap_n,
        "İlk Görünüş": records[hit_idx[0]][1].strftime("%d.%m.%Y %H:%M") if hit_idx else "",
        "Son Görünüş": records[hit_idx[-1]][1].strftime("%d.%m.%Y %H:%M") if hit_idx else "",
    }


def analyze_size(records, k, gaps, same_as_six=False, progress=None, progress_base=0.0, progress_span=1.0):
    bydate = date_map(records)
    dates = sorted(bydate)
    dset = set(dates)
    max_data_date = dates[-1]
    core_links_min, core_chain_min = smart_core_threshold(k, same_as_six)

    gap_rows = []
    day_pair_rows = []
    total_jobs = sum(1 for gap in gaps for d in dates if d + timedelta(days=int(gap)) in dset)
    done_jobs = 0

    for gap in sorted(set(map(int, gaps))):
        pair_arrays = []
        pair_starts = []
        for d1 in dates:
            d2 = d1 + timedelta(days=int(gap))
            if d2 not in dset:
                continue
            arr, max_common, draw_pair_n = local_family_ranks(records, bydate[d1], bydate[d2], int(k))
            pair_arrays.append(arr)
            pair_starts.append(d1)
            day_pair_rows.append({
                "Aile Boyutu": int(k),
                "Gün Gap": int(gap),
                "1. Gün": d1.isoformat(),
                "2. Gün": d2.isoformat(),
                "Maks Ortak Blok": max_common,
                f"{k}+'lı Ortak Çekiliş Çifti": draw_pair_n,
                f"Tekil {k}'li Aday": len(arr),
            })
            done_jobs += 1
            if progress is not None:
                frac = progress_base + progress_span * (done_jobs / max(1, total_jobs)) * 0.72
                progress.progress(min(1.0, frac), text=f"{k}’li • +{gap} gün • {d1.strftime('%d.%m')} → {d2.strftime('%d.%m')}")

        if not pair_arrays:
            continue
        nonempty = [a for a in pair_arrays if len(a)]
        if not nonempty:
            continue
        all_ranks = np.concatenate(nonempty)
        vals, cnt = np.unique(all_ranks, return_counts=True)
        # En az iki gün-bağı görmemiş aile ritim değildir.
        qualify = vals[cnt >= 2]
        if len(qualify) == 0:
            del all_ranks, vals, cnt
            continue

        starts_map = defaultdict(list)
        for arr, d1 in zip(pair_arrays, pair_starts):
            if len(arr) == 0:
                continue
            common = np.intersect1d(arr, qualify, assume_unique=True)
            for rank in common.tolist():
                starts_map[int(rank)].append(d1)

        cnt_map = {int(v): int(c) for v, c in zip(vals.tolist(), cnt.tolist()) if c >= 2}
        for rank, starts in starts_map.items():
            link_count = cnt_map.get(int(rank), len(starts))
            chain_days, chain_start, chain_end = longest_link_chain(starts, int(gap))
            if chain_days < 3:
                continue
            is_core = link_count >= core_links_min and chain_days >= core_chain_min
            is_strong = (
                is_core and (
                    link_count >= core_links_min + 1 or chain_days >= core_chain_min + 1
                )
            )
            next_expected = chain_end + timedelta(days=int(gap)) if chain_end else None
            days_to_next = (next_expected - max_data_date).days if next_expected else 9999
            level = "GÜÇLÜ" if is_strong else ("ÇEKİRDEK" if is_core else "ADAY")
            gap_rows.append({
                "Aile Boyutu": int(k),
                "Aile Rank": int(rank),
                "Aile": family_name(rank, int(k)),
                "Seviye": level,
                "Gün Gap": int(gap),
                "Gap Bağı": int(link_count),
                "En Uzun Zincir Tarih": int(chain_days),
                "Zincir Başlangıç": chain_start.isoformat() if chain_start else "",
                "Zincir Son": chain_end.isoformat() if chain_end else "",
                "Sıradaki Ritim Tarihi": next_expected.isoformat() if next_expected else "",
                "Veri Sonuna Uzaklık": int(days_to_next),
                "Bağ Başlangıçları": " | ".join(d.isoformat() for d in sorted(starts)),
            })

        del all_ranks, vals, cnt, qualify, starts_map, pair_arrays

    detail = pd.DataFrame(gap_rows)
    if detail.empty:
        return {
            "detail": detail,
            "families": pd.DataFrame(),
            "candidates": pd.DataFrame(),
            "live": pd.DataFrame(),
            "daypairs": pd.DataFrame(day_pair_rows),
            "summary": {"k": k, "aday": 0, "cekirdek": 0, "ultra": 0},
        }

    # Aile bazında çoklu-gap çekirdek.
    family_rows = []
    core_levels = {"ÇEKİRDEK", "GÜÇLÜ"}
    for rank, sub in detail.groupby("Aile Rank", sort=False):
        core_sub = sub[sub["Seviye"].isin(core_levels)]
        core_gap_count = int(core_sub["Gün Gap"].nunique())
        candidate_gap_count = int(sub["Gün Gap"].nunique())
        max_links = int(sub["Gap Bağı"].max())
        max_chain = int(sub["En Uzun Zincir Tarih"].max())

        # ULTRA: iki farklı gapte çekirdek veya tek gapte olağanüstü uzun zincir.
        ultra = core_gap_count >= 2 or (
            core_gap_count >= 1 and max_links >= core_links_min + 2 and max_chain >= core_chain_min + 1
        )
        if ultra:
            final_level = "ULTRA"
        elif core_gap_count >= 1:
            final_level = "ÇEKİRDEK"
        else:
            final_level = "ADAY"

        # Takip için en güçlü gap: seviye, zincir, bağ, güncellik.
        ss = sub.copy()
        ss["_lv"] = ss["Seviye"].map({"GÜÇLÜ": 3, "ÇEKİRDEK": 2, "ADAY": 1}).fillna(0)
        ss = ss.sort_values(
            ["_lv", "En Uzun Zincir Tarih", "Gap Bağı", "Zincir Son"],
            ascending=[False, False, False, False],
        )
        best = ss.iloc[0]
        core_gaps = sorted(core_sub["Gün Gap"].unique().tolist()) if len(core_sub) else []
        all_gaps = sorted(sub["Gün Gap"].unique().tolist())

        # Tarihsel puan: sadece sıralama için; olasılık değildir.
        score = (
            (100 if ultra else 60 if core_gap_count else 20)
            + 16 * core_gap_count
            + 5 * max_links
            + 7 * max_chain
            + 2 * candidate_gap_count
        )
        family_rows.append({
            "Aile Boyutu": int(k),
            "Aile Rank": int(rank),
            "Aile": family_name(rank, int(k)),
            "Seviye": final_level,
            "Çekirdek Gap Sayısı": core_gap_count,
            "Tüm Ritim Gapleri": ", ".join("+" + str(x) for x in all_gaps),
            "Çekirdek Gapler": ", ".join("+" + str(x) for x in core_gaps),
            "Maks Gap Bağı": max_links,
            "Maks Zincir Tarih": max_chain,
            "En Güçlü Gap": int(best["Gün Gap"]),
            "Son Zincir Sonu": best["Zincir Son"],
            "Sıradaki Ritim Tarihi": best["Sıradaki Ritim Tarihi"],
            "Veri Sonuna Uzaklık": int(best["Veri Sonuna Uzaklık"]),
            "Tarihsel Ritim Puanı": int(score),
        })

    families = pd.DataFrame(family_rows)
    families = families.sort_values(
        ["Seviye", "Tarihsel Ritim Puanı", "Maks Zincir Tarih", "Maks Gap Bağı"],
        ascending=[True, False, False, False],
    )

    # Sadece çekirdek/ultra ailelerde çekiliş bazlı doğrulama yap; aday binlerce olabilir.
    core_mask = families["Seviye"].isin(["ULTRA", "ÇEKİRDEK"])
    verify_ranks = families.loc[core_mask, "Aile Rank"].astype(int).tolist()
    verify_map = {}
    for q, rank in enumerate(verify_ranks, 1):
        verify_map[int(rank)] = verify_family(records, int(rank), int(k))
        if progress is not None:
            frac = progress_base + progress_span * (0.72 + 0.28 * q / max(1, len(verify_ranks)))
            progress.progress(min(1.0, frac), text=f"{k}’li çekirdek doğrulama {q}/{len(verify_ranks)}")

    for col in [
        "Toplam Görünüş", "Aktif Gün", "Aynı Gün Maks", "Baskın Saat", "Saat Tekrar",
        "Aynı Gün En Sık Çekiliş Gap", "Çekiliş Gap Tekrar", "İlk Görünüş", "Son Görünüş"
    ]:
        families[col] = families["Aile Rank"].map(
            lambda r: verify_map.get(int(r), {}).get(col, "")
        )

    # Canlı ritim: verinin son gününe göre bugün/yakın pencere. Yalnız çekirdek/ultra.
    live = families[families["Seviye"].isin(["ULTRA", "ÇEKİRDEK"])].copy()
    live = live[live["Veri Sonuna Uzaklık"].between(0, 7)]
    live["Durum"] = live["Veri Sonuna Uzaklık"].map(
        lambda x: "BUGÜN" if x == 0 else "YARIN" if x == 1 else f"+{int(x)} GÜN"
    )
    live = live.sort_values(
        ["Veri Sonuna Uzaklık", "Seviye", "Tarihsel Ritim Puanı"],
        ascending=[True, True, False],
    )

    candidates = families[families["Seviye"] == "ADAY"].copy()
    core_count = int((families["Seviye"] == "ÇEKİRDEK").sum())
    ultra_count = int((families["Seviye"] == "ULTRA").sum())

    return {
        "detail": detail.drop(columns=["Aile Rank"], errors="ignore"),
        "families": families.drop(columns=["Aile Rank"], errors="ignore"),
        "candidates": candidates.drop(columns=["Aile Rank"], errors="ignore"),
        "live": live.drop(columns=["Aile Rank"], errors="ignore"),
        "daypairs": pd.DataFrame(day_pair_rows),
        "summary": {
            "k": int(k),
            "aday": int(len(candidates)),
            "cekirdek": core_count,
            "ultra": ultra_count,
            "all": int(len(families)),
        },
    }


# ============================================================
# KONTROLLER
# ============================================================
with st.sidebar:
    st.header("⚙️ Ayarlar")
    raw_url = st.text_input("GitHub veri.txt RAW", value=DEFAULT_RAW_URL)
    sizes = st.multiselect("Aile boyutları", [7, 8, 9], default=[7, 8, 9])
    gaps = st.multiselect(
        "Gün ritimleri",
        list(range(1, 22)) + [28],
        default=[2, 5, 7, 14],
    )
    same_as_six = st.checkbox(
        "8/9’da da 6’lı kadar sert eşik kullan (3 bağ / 4 tarih)",
        value=False,
        help="Kapalıyken 8 ve 9 exact tekrarın nadirliği nedeniyle 2 bağ / 3 tarih çekirdek kabul edilir.",
    )
    max_live_per_size = st.slider("Canlı kupon / boyut üst sınırı", 1, 5, 2)
    st.caption("7’li varsayılan çekirdek: 3 bağ / 4 tarih. 8–9: 2 bağ / 3 tarih.")

if st.button("🔄 GitHub verisini yenile", type="secondary"):
    fetch_text.clear()
    st.rerun()

try:
    text = fetch_text(raw_url)
    records = parse_veri(text)
except Exception as e:
    st.error(f"veri.txt okunamadı: {e}")
    st.stop()

if not records:
    st.error("Geçerli çekiliş bulunamadı.")
    st.stop()

all_dates = sorted({r[1].date() for r in records})
min_date, max_date = all_dates[0], all_dates[-1]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Çekiliş", f"{len(records):,}".replace(",", "."))
c2.metric("Gün", len(all_dates))
c3.metric("Başlangıç", min_date.strftime("%d.%m.%Y"))
c4.metric("Veri sonu", max_date.strftime("%d.%m.%Y"))

with st.expander("ℹ️ Bu app neyi 'nokta ritmi' sayıyor?", expanded=False):
    st.markdown(
        """
- **7’li:** 6’lı dar çekirdeğine benzer sertlik: aynı gap **en az 3 bağ** ve **4 tarih zinciri**.
- **8’li / 9’lu:** exact tekrar çok daha nadir olduğu için varsayılan çekirdek **2 bağ / 3 tarih**. İstersen soldan 6’lı kadar sertleştirebilirsin.
- **ULTRA:** bir aile en az iki farklı gapte çekirdek olursa veya tek gapte olağanüstü uzun zincir kurarsa.
- **Canlı kupon:** yalnız ULTRA/ÇEKİRDEK ailelerden, tarih ritmi veri sonuna göre önümüzdeki 0–7 güne düşenler.
- **Sinyal yoksa 0 kupon.** Geçmiş ritim gelecekte kesin tekrar garantisi değildir.
        """
    )

# Sabit kolonun tek çekilişte tam isabet baz oranları
prob_rows = []
for k in [7, 8, 9]:
    p = 1.0
    for j in range(k):
        p *= (20 - j) / (80 - j)
    prob_rows.append({"Aile": f"{k}’li", "Sabit kolon k/k": f"%{100*p:.6f}", "Yaklaşık": f"1 / {round(1/p):,}".replace(",", ".")})
st.subheader("📏 Sabit kolon baz oranı")
safe_dataframe(pd.DataFrame(prob_rows), max_rows=10)

# ============================================================
# ÇALIŞTIR
# ============================================================
if "r789_results" not in st.session_state:
    st.session_state.r789_results = {}

run = st.button("🚀 7•8•9 ritim çekirdeklerini çıkar", type="primary", disabled=(not sizes or not gaps))
if run:
    results = {}
    prog = st.progress(0.0, text="Başlıyor...")
    sizes_sorted = sorted(set(map(int, sizes)))
    for si, k in enumerate(sizes_sorted):
        base = si / len(sizes_sorted)
        span = 1.0 / len(sizes_sorted)
        res = analyze_size(
            records, k, gaps, same_as_six=same_as_six,
            progress=prog, progress_base=base, progress_span=span,
        )
        results[int(k)] = res
    prog.progress(1.0, text="Analiz tamamlandı")
    st.session_state.r789_results = results
    st.success("7•8•9 ritim analizi tamamlandı.")

results = st.session_state.r789_results
if results:
    st.divider()
    st.header("🎯 Sonuç Merkezi")

    # Özet
    summary_rows = []
    for k in sorted(results):
        s = results[k]["summary"]
        summary_rows.append({
            "Aile": f"{k}’li",
            "ULTRA": s["ultra"],
            "ÇEKİRDEK": s["cekirdek"],
            "ADAY": s["aday"],
            "Toplam Ritimli": s["all"],
        })
    safe_dataframe(pd.DataFrame(summary_rows), max_rows=10)

    tabs = st.tabs(["🔥 Canlı Kupon", "💎 Dar Çekirdek", "🧬 Gap Detay", "🌱 Adaylar", "📅 Gün Karşılaştırma", "📦 Rapor"])

    with tabs[0]:
        st.subheader("🔥 Canlı ritim kuponları")
        live_parts = []
        for k in sorted(results):
            x = results[k]["live"].copy()
            if not x.empty:
                # Boyut başına sadece en güçlü N
                x = x.head(int(max_live_per_size))
                live_parts.append(x)
        if live_parts:
            live_all = pd.concat(live_parts, ignore_index=True)
            safe_dataframe(live_all, max_rows=30)
            st.caption("Kupon = 'Aile' sütunundaki sayıların tamamı. Yalnız tarih ritmi yaklaşan çekirdek aileler gösterilir.")
        else:
            st.success("Şu an 0 güçlü canlı kupon. Bu iyi: motor zayıf sinyalde kupon üretmiyor.")

    with tabs[1]:
        for k in sorted(results):
            st.markdown(f"### {k}’li dar çekirdek")
            df = results[k]["families"]
            core = df[df["Seviye"].isin(["ULTRA", "ÇEKİRDEK"])].copy() if not df.empty else df
            if core.empty:
                st.info(f"{k}’lide seçilen eşiklerle dar çekirdek yok.")
            else:
                safe_dataframe(core, max_rows=100)

    with tabs[2]:
        selected_k = st.selectbox("Gap detayı aile boyutu", sorted(results.keys()), key="gap_detail_k")
        safe_dataframe(results[selected_k]["detail"], max_rows=250)

    with tabs[3]:
        selected_k2 = st.selectbox("Aday aile boyutu", sorted(results.keys()), key="cand_k")
        cand = results[selected_k2]["candidates"]
        if cand.empty:
            st.info("Aday yok.")
        else:
            safe_dataframe(cand.sort_values(["Tarihsel Ritim Puanı"], ascending=False), max_rows=150)

    with tabs[4]:
        selected_k3 = st.selectbox("Gün karşılaştırma aile boyutu", sorted(results.keys()), key="daypair_k")
        dp = results[selected_k3]["daypairs"]
        safe_dataframe(dp, max_rows=250)

    with tabs[5]:
        files = {}
        summary_export = pd.DataFrame(summary_rows)
        files["00_OZET.csv"] = df_bytes(summary_export)
        for k in sorted(results):
            r = results[k]
            files[f"{k}LI_01_DAR_CEKIRDEK.csv"] = df_bytes(
                r["families"][r["families"]["Seviye"].isin(["ULTRA", "ÇEKİRDEK"])]
                if not r["families"].empty else r["families"]
            )
            files[f"{k}LI_02_TUM_RITIMLI_AILELER.csv"] = df_bytes(r["families"])
            files[f"{k}LI_03_GAP_DETAY.csv"] = df_bytes(r["detail"])
            files[f"{k}LI_04_ADAYLAR.csv"] = df_bytes(r["candidates"])
            files[f"{k}LI_05_CANLI_KUPON.csv"] = df_bytes(r["live"])
            files[f"{k}LI_06_GUN_KARSILASTIRMA.csv"] = df_bytes(r["daypairs"])
        files["99_METODOLOJI.txt"] = (
            "7-8-9 Ritim Nokta Merkezi V1\n"
            "Aileler brute-force tüm uzaydan üretilmez. Seçilen gün-gaplerde iki günde gerçekten ortak görülen "
            "çekiliş bloklarından exact k'lı aileler üretilir. Aynı aile aynı gapte en az iki gün-bağında görünmeden "
            "ritim adayı sayılmaz. 7'li varsayılan çekirdek 3 bağ/4 tarih; 8-9 varsayılan 2 bağ/3 tarih. "
            "ULTRA çoklu-gap veya olağanüstü zincir koşuludur. Canlı kupon tarihsel ritim takibidir, garanti değildir.\n"
        )
        zip_data = build_zip(files)
        st.download_button(
            "⬇️ Tüm 7•8•9 raporlarını ZIP indir",
            data=zip_data,
            file_name="HIZLI_ON_789_RITIM_NOKTA_V1_TUM_RAPORLAR.zip",
            mime="application/zip",
        )

st.divider()
st.caption("V1 • Normal 7/8/9 exact aile ritmi • güvenli gün-gap madenciliği • PyArrow tablo çizimi kullanılmaz")
