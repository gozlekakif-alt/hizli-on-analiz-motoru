
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
    """Farklı veri.txt biçimlerini dayanıklı şekilde okur."""
    if not text:
        return pd.DataFrame()

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Her çekiliş başlığından bir sonraki çekiliş başlığına kadar blok oluştur.
    # Desteklenen örnekler:
    # Çekiliş no: 51213
    # ### Çekiliş no:\n### 51213
    header_re = re.compile(
        r"(?im)^\s*(?:#{1,6}\s*)?(?:Çekiliş|Cekilis)\s*no\s*:\s*(?:#{1,6}\s*)?(\d{4,8})?\s*$"
    )
    matches = list(header_re.finditer(text))
    rows = []

    for idx, m in enumerate(matches):
        block_start = m.start()
        block_end = matches[idx+1].start() if idx+1 < len(matches) else len(text)
        block = text[block_start:block_end]

        draw_id = m.group(1)
        if not draw_id:
            # Başlık ayrı, numara sonraki satırda olabilir.
            tail = text[m.end(): min(m.end()+120, len(text))]
            mm = re.search(r"(?m)^\s*(?:#{1,6}\s*)?(\d{4,8})\s*$", tail)
            if mm:
                draw_id = mm.group(1)

        if not draw_id:
            continue

        md = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*[- ]\s*(\d{2}:\d{2})", block)
        if not md:
            continue
        dt = pd.to_datetime(f"{md.group(1)} {md.group(2)}", dayfirst=True, errors="coerce")
        if pd.isna(dt):
            continue

        # Tarihten sonraki bölümde yalnız tek başına duran 1..80 sayılarını al.
        after = block[md.end():]
        nums=[]
        for ln in after.splitlines():
            s=ln.strip()
            s=re.sub(r"^#{1,6}\s*", "", s).strip()
            if re.fullmatch(r"\d{1,2}", s):
                n=int(s)
                if 1 <= n <= 80:
                    nums.append(n)
            if len(nums) >= 20:
                break

        if len(nums) >= 20:
            nums=nums[:20]
            if len(set(nums)) == 20:
                rows.append({"draw_id":int(draw_id), "dt":dt, "nums":tuple(sorted(nums))})

    # Alternatif sade biçim için ikinci yol: başlıkta numara aynı satırda.
    if not rows:
        simple = re.compile(
            r"(?is)(?:Çekiliş|Cekilis)\s*no\s*:\s*(\d{4,8}).*?"
            r"(\d{2}\.\d{2}\.\d{4})\s*[- ]\s*(\d{2}:\d{2})(.*?)(?=(?:Çekiliş|Cekilis)\s*no\s*:|\Z)"
        )
        for mm in simple.finditer(text):
            nums=[]
            for ln in mm.group(4).splitlines():
                s=re.sub(r"^#{1,6}\s*", "", ln.strip()).strip()
                if re.fullmatch(r"\d{1,2}", s):
                    n=int(s)
                    if 1 <= n <= 80:
                        nums.append(n)
                if len(nums)>=20:
                    break
            if len(nums)>=20 and len(set(nums[:20]))==20:
                rows.append({
                    "draw_id":int(mm.group(1)),
                    "dt":pd.to_datetime(f"{mm.group(2)} {mm.group(3)}",dayfirst=True,errors="coerce"),
                    "nums":tuple(sorted(nums[:20]))
                })

    df=pd.DataFrame(rows)
    if df.empty:
        return df
    df=df.dropna(subset=["dt"]).drop_duplicates("draw_id").sort_values("dt").reset_index(drop=True)
    df["date"]=df["dt"].dt.date
    df["hour"]=df["dt"].dt.hour
    df["minute"]=df["dt"].dt.minute
    df["count"]=df["nums"].map(len)
    return df[df["count"]==20].copy()

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


def _decode_bytes(b: bytes) -> str:
    for enc in ("utf-8-sig","utf-8","cp1254","latin1"):
        try:
            return b.decode(enc)
        except Exception:
            pass
    return b.decode("utf-8", errors="ignore")


def load_default_veri():
    """Önce repo içindeki veri.txt'yi, sonra GitHub raw kopyasını dener."""
    try:
        app_dir = Path(__file__).resolve().parent
    except Exception:
        app_dir = Path.cwd()

    diagnostics=[]
    candidates=[]
    for p in [app_dir/"veri.txt", Path.cwd()/"veri.txt", app_dir.parent/"veri.txt"]:
        if p not in candidates:
            candidates.append(p)

    # Repo altında da ara.
    try:
        for p in app_dir.rglob("veri.txt"):
            if p not in candidates:
                candidates.append(p)
    except Exception as e:
        diagnostics.append(f"rglob: {e}")

    for p in candidates:
        try:
            if p.exists() and p.is_file():
                b=p.read_bytes()
                diagnostics.append(f"LOCAL {p} ({len(b)} bayt)")
                df=parse_veri_txt(_decode_bytes(b))
                if not df.empty:
                    return df, f"LOCAL: {p}", diagnostics
                diagnostics.append(f"LOCAL bulundu ama 0 çekiliş ayrıştırıldı: {p}")
        except Exception as e:
            diagnostics.append(f"LOCAL hata {p}: {type(e).__name__}: {e}")

    # Kullanıcının public GitHub reposu için doğrudan fallback.
    # Tarayıcı çevirisi 'main'i 'ana' gösterebildiği için ikisini de deniyoruz.
    try:
        from urllib.request import Request, urlopen
        bases=[
            "https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/main/veri.txt",
            "https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/ana/veri.txt",
            "https://raw.githubusercontent.com/gozlekakif-alt/hizli-on-analiz-motoru/master/veri.txt",
        ]
        for url in bases:
            try:
                req=Request(url,headers={"User-Agent":"Mozilla/5.0"})
                with urlopen(req,timeout=15) as r:
                    b=r.read()
                diagnostics.append(f"RAW {url} ({len(b)} bayt)")
                df=parse_veri_txt(_decode_bytes(b))
                if not df.empty:
                    return df, f"GITHUB RAW: {url}", diagnostics
                diagnostics.append(f"RAW geldi ama 0 çekiliş ayrıştırıldı: {url}")
            except Exception as e:
                diagnostics.append(f"RAW hata {url}: {type(e).__name__}: {e}")
    except Exception as e:
        diagnostics.append(f"urllib başlatılamadı: {type(e).__name__}: {e}")

    return pd.DataFrame(), None, diagnostics

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
    data, veri_source, veri_diag = load_default_veri()

if data.empty:
    st.error("veri.txt repo içinde var ama uygulama onu okuyamadı. Aşağıdaki tanı bilgisi hangi aşamada kaldığını gösteriyor.")
    with st.expander("Veri tanılama", expanded=True):
        for line in (veri_diag if uploaded is None else []):
            st.code(line)
    st.stop()
else:
    if uploaded is None:
        st.success(f"Veri otomatik yüklendi — {veri_source} — {len(data)} çekiliş")

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
