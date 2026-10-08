
import streamlit as st
import pandas as pd
import numpy as np
import itertools
import math
import re
from collections import Counter
from math import comb
from pathlib import Path

st.set_page_config(page_title="Hızlı On — Merkez Çekirdek Avcısı", layout="wide")

st.title("Hızlı On — Sayı Aileleri / Ortak Merkez Çekirdek")
st.caption("217 çekilişte 2'li, 3'lü ve 4'lü ortak merkez çekirdekleri; yakın halka ve günler arası kilitli test.")

# -----------------------------
# Veri okuma
# -----------------------------
@st.cache_data(show_spinner=False)
def parse_veri_txt(text: str) -> pd.DataFrame:
    """
    Beklenen blok tipi:
    Çekiliş no: 51213
    25.08.2026-00:02
    2
    4
    ...
    80

    Alternatif:
    ### Çekiliş no:
    ### 51213
    25.08.2026-00:02
    ...
    """
    lines = [x.strip() for x in text.splitlines()]
    rows = []
    i = 0

    draw_id = None
    dt = None
    nums = []

    def flush():
        nonlocal draw_id, dt, nums
        if draw_id is not None and dt is not None and len(nums) >= 20:
            use = nums[:20]
            rows.append({
                "draw_id": int(draw_id),
                "dt": pd.to_datetime(dt, dayfirst=True, errors="coerce"),
                "nums": tuple(sorted(set(int(x) for x in use)))
            })
        draw_id = None
        dt = None
        nums = []

    draw_patterns = [
        re.compile(r"(?:Çekiliş|Cekilis)\s*no\s*:\s*(\d+)", re.I),
        re.compile(r"^###\s*(\d+)\s*$"),
        re.compile(r"^(\d{4,7})\s*$")
    ]
    dt_re = re.compile(r"(\d{2}\.\d{2}\.\d{4})\s*[- ]\s*(\d{2}:\d{2})")

    while i < len(lines):
        line = lines[i]

        m = None
        for p in draw_patterns[:2]:
            m = p.search(line)
            if m:
                break

        # "Çekiliş no:" ayrı satır, numara bir sonraki satır olabilir.
        if ("çekiliş no" in line.lower() or "cekilis no" in line.lower()) and not m:
            j = i + 1
            while j < len(lines) and j <= i + 3:
                mm = re.search(r"(\d{4,7})", lines[j])
                if mm:
                    flush()
                    draw_id = int(mm.group(1))
                    i = j
                    break
                j += 1
            i += 1
            continue

        if m:
            # Yeni blok
            new_id = int(m.group(1))
            if draw_id is not None and new_id != draw_id:
                flush()
            draw_id = new_id
            i += 1
            continue

        md = dt_re.search(line)
        if md:
            dt = f"{md.group(1)} {md.group(2)}"
            i += 1
            continue

        # Tek sayı satırı 1..80
        if re.fullmatch(r"\d{1,2}", line or ""):
            n = int(line)
            if 1 <= n <= 80 and draw_id is not None:
                nums.append(n)

        # Bir sonraki "Çekiliş no" yaklaşmadan 20 sayı dolduysa blok hazır.
        if len(nums) == 20 and draw_id is not None and dt is not None:
            flush()

        i += 1

    flush()

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.dropna(subset=["dt"]).drop_duplicates("draw_id").sort_values("dt").reset_index(drop=True)
    df["date"] = df["dt"].dt.date
    df["hour"] = df["dt"].dt.hour
    df["minute"] = df["dt"].dt.minute
    df["count"] = df["nums"].map(len)
    df = df[df["count"] == 20].copy()
    return df


@st.cache_data(show_spinner=False)
def parse_csv_bytes(data: bytes) -> pd.DataFrame:
    import io
    bio = io.BytesIO(data)
    # gzip by magic bytes
    compression = "gzip" if data[:2] == b"\x1f\x8b" else "infer"
    raw = pd.read_csv(bio, compression=compression, low_memory=False)
    if {"draw_id","dt","number","selected"}.issubset(raw.columns):
        raw["dt"] = pd.to_datetime(raw["dt"], errors="coerce")
        raw["number"] = pd.to_numeric(raw["number"], errors="coerce")
        raw["selected"] = pd.to_numeric(raw["selected"], errors="coerce").fillna(0).astype(int)
        z = raw[raw["selected"]==1].dropna(subset=["dt","number"]).copy()
        out = (z.groupby(["draw_id","dt"])["number"]
               .apply(lambda s: tuple(sorted(set(s.astype(int)))))
               .reset_index(name="nums")
               .sort_values("dt"))
        out["date"] = out["dt"].dt.date
        out["hour"] = out["dt"].dt.hour
        out["minute"] = out["dt"].dt.minute
        out["count"] = out["nums"].map(len)
        return out[out["count"]==20].reset_index(drop=True)
    raise ValueError("CSV içinde draw_id, dt, number, selected sütunları bulunamadı.")


def load_default_veri():
    p = Path("veri.txt")
    if p.exists():
        try:
            return parse_veri_txt(p.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


uploaded = st.file_uploader("Veri dosyası yükle (veri.txt veya CSV/CSV.GZ)", type=["txt","csv","gz"])

if uploaded is not None:
    if uploaded.name.lower().endswith(".txt"):
        data = parse_veri_txt(uploaded.getvalue().decode("utf-8", errors="ignore"))
    else:
        try:
            data = parse_csv_bytes(uploaded.getvalue())
        except Exception as e:
            st.error(f"CSV okunamadı: {e}")
            st.stop()
else:
    data = load_default_veri()

if data.empty:
    st.info("Repo içine `veri.txt` koy veya yukarıdan dosya yükle.")
    st.stop()

# -----------------------------
# Yardımcı analiz fonksiyonları
# -----------------------------
def itemset_counts(draw_tuples, k):
    c = Counter()
    for tup in draw_tuples:
        c.update(itertools.combinations(tup, k))
    return c

def calc_core_table(draw_df, k, min_support):
    N = len(draw_df)
    draw_tuples = draw_df["nums"].tolist()
    draw_sets = [set(x) for x in draw_tuples]

    freq = Counter()
    for s in draw_sets:
        freq.update(s)

    counts = itemset_counts(draw_tuples, k)

    p_uniform = comb(20, k) / comb(80, k)
    expected_uniform = N * p_uniform

    rows = []
    for core, sup in counts.items():
        if sup < min_support:
            continue

        probs = [freq[n] / N for n in core]
        expected_marg = N * np.prod(probs)
        lift_marg = sup / expected_marg if expected_marg > 0 else np.nan

        idx = [i for i,s in enumerate(draw_sets) if set(core).issubset(s)]
        hours_spread = draw_df.iloc[idx]["dt"].dt.hour.nunique() if idx else 0
        gaps = np.diff(idx) if len(idx) > 1 else np.array([])

        companions = Counter()
        for i in idx:
            companions.update(draw_sets[i] - set(core))

        near_ring = []
        for n,c in companions.most_common():
            cond = c / sup
            base = freq[n] / N
            lift = cond / base if base > 0 else np.nan
            if c >= max(3, math.ceil(0.25 * sup)) and lift >= 1.15:
                near_ring.append((n,c,cond,lift))

        spread_den = max(1, draw_df["dt"].dt.hour.nunique())
        spread_frac = hours_spread / spread_den
        center_score = (
            np.log1p(sup)
            * min(max(lift_marg, 0), 5)
            * (0.65 + 0.35 * spread_frac)
        )

        rows.append({
            "k": k,
            "core": "-".join(map(str, core)),
            "support": int(sup),
            "support_pct": 100 * sup / N,
            "expected_uniform": expected_uniform,
            "uniform_excess": sup - expected_uniform,
            "lift_vs_own_marginals": lift_marg,
            "hours_spread": int(hours_spread),
            "mean_gap_draws": float(gaps.mean()) if len(gaps) else np.nan,
            "max_gap_draws": int(gaps.max()) if len(gaps) else np.nan,
            "near_ring_count": len(near_ring),
            "near_ring_top": "; ".join(
                f"{n}({c}/{sup},{100*cond:.0f}%,x{lift:.2f})"
                for n,c,cond,lift in near_ring[:12]
            ),
            "center_score": center_score
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(
        ["center_score","support","lift_vs_own_marginals"],
        ascending=False
    ).reset_index(drop=True)


def central_numbers(core_tables, day_df, top_n_per_k=50):
    freq = Counter()
    for s in day_df["nums"]:
        freq.update(s)

    weight = Counter()
    memberships = Counter()

    for t in core_tables:
        if t is None or t.empty:
            continue
        for r in t.head(top_n_per_k).itertuples():
            nums = [int(x) for x in r.core.split("-")]
            for n in nums:
                weight[n] += float(r.center_score)
                memberships[n] += 1

    rows = []
    N = len(day_df)
    for n in weight:
        rows.append({
            "number": n,
            "center_weight": weight[n],
            "top_core_memberships": memberships[n],
            "day_frequency": freq[n],
            "day_frequency_pct": 100*freq[n]/N
        })
    return pd.DataFrame(rows).sort_values(
        ["center_weight","top_core_memberships"],
        ascending=False
    ).reset_index(drop=True)


def locked_validation(all_df, discover_date, cores_df, top_n=10):
    chosen = cores_df.head(top_n).copy()
    if chosen.empty:
        return pd.DataFrame()

    after_dates = sorted([d for d in all_df["date"].unique() if d > discover_date])
    rows = []

    for r in chosen.itertuples():
        core = tuple(int(x) for x in r.core.split("-"))
        cset = set(core)

        for date in after_dates:
            z = all_df[all_df["date"] == date]
            if z.empty:
                continue

            support = sum(cset.issubset(set(nums)) for nums in z["nums"])
            N = len(z)

            freq = Counter()
            for s in z["nums"]:
                freq.update(s)

            probs = [freq[n]/N for n in core]
            exp_marg = N*np.prod(probs)
            lift = support/exp_marg if exp_marg > 0 else np.nan

            rows.append({
                "discover_date": discover_date,
                "k": r.k,
                "core": r.core,
                "discover_support": r.support,
                "test_date": date,
                "test_draws": N,
                "test_support": support,
                "test_support_pct": 100*support/N if N else 0,
                "test_lift_vs_own_marginals": lift
            })

    return pd.DataFrame(rows)


# -----------------------------
# Arayüz
# -----------------------------
dates = sorted(data["date"].unique())
c1,c2,c3,c4 = st.columns([1.4,1,1,1])

with c1:
    selected_date = st.selectbox("Analiz günü", dates, index=0)
with c2:
    min2 = st.number_input("2'li min tekrar", 5, 100, 18)
with c3:
    min3 = st.number_input("3'lü min tekrar", 3, 50, 7)
with c4:
    min4 = st.number_input("4'lü min tekrar", 2, 30, 4)

day_df = data[data["date"] == selected_date].sort_values("dt").reset_index(drop=True)

st.write(
    f"**{selected_date}** — {len(day_df)} çekiliş. "
    f"Beklenen 2'li={len(day_df)*comb(20,2)/comb(80,2):.2f}, "
    f"3'lü={len(day_df)*comb(20,3)/comb(80,3):.2f}, "
    f"4'lü={len(day_df)*comb(20,4)/comb(80,4):.2f}"
)

if len(day_df) < 50:
    st.warning("Bu gün için çekiliş sayısı düşük; sonuçlar zayıf olabilir.")

with st.spinner("Merkez çekirdekler taranıyor..."):
    P = calc_core_table(day_df, 2, int(min2))
    T = calc_core_table(day_df, 3, int(min3))
    Q = calc_core_table(day_df, 4, int(min4))
    C = central_numbers([P,T,Q], day_df, top_n_per_k=50)

tabs = st.tabs([
    "Özet",
    "2'li çekirdek",
    "3'lü çekirdek",
    "4'lü çekirdek",
    "Merkez sayılar",
    "Kilitli günler arası test"
])

with tabs[0]:
    a,b,c = st.columns(3)
    a.metric("2'li çekirdek", len(P))
    b.metric("3'lü çekirdek", len(T))
    c.metric("4'lü çekirdek", len(Q))

    st.subheader("En güçlü ortak merkezler")
    topall = pd.concat([
        P.head(5),
        T.head(5),
        Q.head(5)
    ], ignore_index=True) if any(not x.empty for x in [P,T,Q]) else pd.DataFrame()

    if not topall.empty:
        st.dataframe(
            topall[[
                "k","core","support","support_pct",
                "lift_vs_own_marginals","hours_spread",
                "near_ring_top","center_score"
            ]],
            use_container_width=True,
            hide_index=True
        )

    st.subheader("Ortak merkez sayıları")
    st.dataframe(C.head(20), use_container_width=True, hide_index=True)

with tabs[1]:
    st.dataframe(P, use_container_width=True, hide_index=True)
    st.download_button(
        "2'li CSV indir",
        P.to_csv(index=False).encode("utf-8-sig"),
        f"{selected_date}_2li_merkez.csv",
        "text/csv"
    )

with tabs[2]:
    st.dataframe(T, use_container_width=True, hide_index=True)
    st.download_button(
        "3'lü CSV indir",
        T.to_csv(index=False).encode("utf-8-sig"),
        f"{selected_date}_3lu_merkez.csv",
        "text/csv"
    )

with tabs[3]:
    st.dataframe(Q, use_container_width=True, hide_index=True)
    st.download_button(
        "4'lü CSV indir",
        Q.to_csv(index=False).encode("utf-8-sig"),
        f"{selected_date}_4lu_merkez.csv",
        "text/csv"
    )

with tabs[4]:
    st.dataframe(C, use_container_width=True, hide_index=True)
    st.download_button(
        "Merkez sayılar CSV indir",
        C.to_csv(index=False).encode("utf-8-sig"),
        f"{selected_date}_merkez_sayilar.csv",
        "text/csv"
    )

with tabs[5]:
    st.write(
        "Seçilen günde keşfedilen çekirdeği değiştirmeden sonraki günlerde arar. "
        "Bu bölüm hindsight etkisini azaltmak için kilitli testtir."
    )
    kk = st.radio("Kilitlenecek çekirdek boyutu", [2,3,4], horizontal=True, index=1)
    topn = st.slider("İlk kaç çekirdek test edilsin?", 1, 30, 10)

    source = {2:P,3:T,4:Q}[kk]
    if source.empty:
        st.info("Bu boyutta çekirdek bulunamadı.")
    else:
        V = locked_validation(data, selected_date, source, top_n=topn)
        if V.empty:
            st.info("Seçilen günden sonra test edilecek gün yok.")
        else:
            summary = (V.groupby(["k","core","discover_support"])
                       .agg(
                           test_days=("test_date","nunique"),
                           total_test_support=("test_support","sum"),
                           avg_support_day=("test_support","mean"),
                           median_support_day=("test_support","median"),
                           avg_lift=("test_lift_vs_own_marginals","mean"),
                           days_lift_gt1=("test_lift_vs_own_marginals",lambda x:int((x>1).sum()))
                       )
                       .reset_index()
                       .sort_values(["avg_lift","avg_support_day"],ascending=False))

            st.subheader("Kilitli test özeti")
            st.dataframe(summary, use_container_width=True, hide_index=True)

            selected_core = st.selectbox("Çekirdek gün gün iz", summary["core"].tolist())
            st.dataframe(
                V[V["core"]==selected_core].sort_values("test_date"),
                use_container_width=True,
                hide_index=True
            )

            st.download_button(
                "Kilitli test CSV indir",
                V.to_csv(index=False).encode("utf-8-sig"),
                f"{selected_date}_kilitli_cekirdek_test.csv",
                "text/csv"
            )

st.divider()
st.caption(
    "Not: Çok sayıda olası aile tarandığı için tek günlük yüksek tekrarlar kalıcı sinyal sayılmaz. "
    "Kilitli günler arası test bölümünü esas doğrulama olarak kullan."
)
