from pathlib import Path
import streamlit as st
import pandas as pd
import numpy as np
import itertools
import math
import re
from collections import Counter
from math import comb

st.set_page_config(page_title="Hızlı On — Merkez Çekirdek", layout="wide")

st.title("Hızlı On — Sayı Aileleri / Ortak Merkez Çekirdek")
st.caption("217 çekilişte 2'li, 3'lü ve 4'lü ortak merkez çekirdekleri, yakın halka ve günler arası kilitli test.")

# =========================================================
# GERÇEK veri.txt FORMATINA GÖRE TEST EDİLMİŞ PARSER
# =========================================================
@st.cache_data(show_spinner=False)
def parse_veri_text(text: str) -> pd.DataFrame:
    """Repo'daki kompakt formatı ve eski blok formatını birlikte okur."""
    text = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    rows = []

    # 1) GERÇEK REPO FORMATI:
    # 51213;25.08.2026 00:02;2,4,6,...,80
    compact_re = re.compile(
        r"^\s*(\d{4,8})\s*;\s*"
        r"(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\s*;\s*"
        r"(.+?)\s*$"
    )

    for line in lines:
        m = compact_re.match(line)
        if not m:
            continue

        dt = pd.to_datetime(
            f"{m.group(2)} {m.group(3)}",
            dayfirst=True,
            errors="coerce"
        )
        if pd.isna(dt):
            continue

        try:
            nums = [int(x.strip()) for x in m.group(4).split(",") if x.strip()]
        except Exception:
            continue

        if len(nums) == 20 and all(1 <= n <= 80 for n in nums):
            rows.append({
                "draw_id": int(m.group(1)),
                "dt": dt,
                "nums": tuple(sorted(nums))
            })

    if rows:
        df = pd.DataFrame(rows)
        df = (
            df.drop_duplicates("draw_id")
              .sort_values("dt")
              .reset_index(drop=True)
        )
        df["date"] = df["dt"].dt.date
        df["hour"] = df["dt"].dt.hour
        df["minute"] = df["dt"].dt.minute
        return df

    # 2) ESKİ BLOK FORMATI
    rows = []
    i = 0
    header_re = re.compile(
        r"^(?:#+\s*)?(?:Çekiliş|Cekilis)\s*no\s*:\s*(\d*)\s*$",
        re.I
    )
    date_re = re.compile(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})")

    while i < len(lines):
        mh = header_re.match(lines[i])
        if not mh:
            i += 1
            continue

        draw_id = None
        same_line_id = mh.group(1).strip()

        if same_line_id:
            draw_id = int(same_line_id)
            i += 1
        else:
            j = i + 1
            while j < min(i + 5, len(lines)):
                clean = re.sub(r"^#+\s*", "", lines[j]).strip()
                if re.fullmatch(r"\d{4,8}", clean):
                    draw_id = int(clean)
                    i = j + 1
                    break
                j += 1
            if draw_id is None:
                i += 1
                continue

        dt = None
        while i < len(lines):
            if header_re.match(lines[i]):
                break
            md = date_re.search(lines[i])
            if md:
                dt = pd.to_datetime(
                    f"{md.group(1)} {md.group(2)}",
                    dayfirst=True,
                    errors="coerce"
                )
                i += 1
                break
            i += 1

        if dt is None or pd.isna(dt):
            continue

        nums = []
        while i < len(lines) and len(nums) < 20:
            if header_re.match(lines[i]):
                break
            clean = re.sub(r"^#+\s*", "", lines[i]).strip()
            if re.fullmatch(r"\d{1,2}", clean):
                n = int(clean)
                if 1 <= n <= 80:
                    nums.append(n)
            i += 1

        if len(nums) == 20:
            rows.append({
                "draw_id": int(draw_id),
                "dt": dt,
                "nums": tuple(sorted(nums))
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = (
        df.drop_duplicates("draw_id")
          .sort_values("dt")
          .reset_index(drop=True)
    )
    df["date"] = df["dt"].dt.date
    df["hour"] = df["dt"].dt.hour
    df["minute"] = df["dt"].dt.minute
    return df


@st.cache_data(show_spinner=False)
def parse_csv_bytes(data: bytes) -> pd.DataFrame:
    import io

    bio = io.BytesIO(data)
    compression = "gzip" if data[:2] == b"\x1f\x8b" else "infer"
    raw = pd.read_csv(bio, compression=compression, low_memory=False)

    required = {"draw_id", "dt", "number", "selected"}
    if not required.issubset(raw.columns):
        raise ValueError("CSV içinde draw_id, dt, number, selected sütunları bulunamadı.")

    raw["dt"] = pd.to_datetime(raw["dt"], errors="coerce")
    raw["number"] = pd.to_numeric(raw["number"], errors="coerce")
    raw["selected"] = pd.to_numeric(raw["selected"], errors="coerce").fillna(0).astype(int)

    z = raw[(raw["selected"] == 1)].dropna(subset=["dt", "number"]).copy()

    out = (
        z.groupby(["draw_id", "dt"])["number"]
         .apply(lambda s: tuple(sorted(s.astype(int).tolist())))
         .reset_index(name="nums")
         .sort_values("dt")
         .reset_index(drop=True)
    )

    out = out[out["nums"].map(len) == 20].copy()
    out["date"] = out["dt"].dt.date
    out["hour"] = out["dt"].dt.hour
    out["minute"] = out["dt"].dt.minute
    return out


def find_repo_veri():
    try:
        base = Path(__file__).resolve().parent
    except Exception:
        base = Path.cwd()

    candidates = [
        base / "veri.txt",
        Path.cwd() / "veri.txt",
        base.parent / "veri.txt",
    ]

    for p in candidates:
        if p.exists() and p.is_file():
            return p

    try:
        for p in base.rglob("veri.txt"):
            if p.is_file():
                return p
    except Exception:
        pass

    return None


# =========================================================
# VERİ YÜKLEME
# =========================================================
uploaded = st.file_uploader(
    "İstersen başka veri yükle (veri.txt veya CSV/CSV.GZ)",
    type=["txt", "csv", "gz"]
)

data = pd.DataFrame()
source_text = ""

if uploaded is not None:
    try:
        if uploaded.name.lower().endswith(".txt"):
            data = parse_veri_text(uploaded.getvalue().decode("utf-8", errors="ignore"))
        else:
            data = parse_csv_bytes(uploaded.getvalue())
        source_text = f"Yüklenen dosya: {uploaded.name}"
    except Exception as e:
        st.error(f"Yüklenen dosya okunamadı: {e}")
        st.stop()
else:
    veri_path = find_repo_veri()

    if veri_path is None:
        st.error("Repo içinde veri.txt bulunamadı.")
        st.stop()

    try:
        txt = veri_path.read_text(encoding="utf-8", errors="ignore")
        data = parse_veri_text(txt)
        source_text = f"Repo: {veri_path.name}"
    except Exception as e:
        st.error(f"veri.txt bulundu fakat okunamadı: {e}")
        st.stop()

if data.empty:
    st.error(
        "veri.txt bulundu fakat 0 çekiliş ayrıştırıldı. "
        "Bu sürüm 'Çekiliş no: 51213 / 25.08.2026 - 00:02 / 20 sayı' formatı için test edilmiştir."
    )
    st.stop()

st.success(
    f"✅ Veri doğru okundu — {source_text} — "
    f"{len(data):,} çekiliş — {data['date'].nunique()} gün — "
    f"{data['dt'].min():%d.%m.%Y %H:%M} → {data['dt'].max():%d.%m.%Y %H:%M}"
)

# =========================================================
# ANALİZ
# =========================================================
def calc_core_table(draw_df, k, min_support):
    N = len(draw_df)
    tuples = draw_df["nums"].tolist()
    sets = [set(x) for x in tuples]

    freq = Counter()
    for s in sets:
        freq.update(s)

    counts = Counter()
    for tup in tuples:
        counts.update(itertools.combinations(tup, k))

    p_uniform = comb(20, k) / comb(80, k)
    expected_uniform = N * p_uniform
    total_hours = max(1, draw_df["dt"].dt.hour.nunique())

    rows = []

    for core, support in counts.items():
        if support < min_support:
            continue

        base_probs = [freq[n] / N for n in core]
        expected_marginal = N * np.prod(base_probs)
        lift = support / expected_marginal if expected_marginal > 0 else np.nan

        idx = [j for j, s in enumerate(sets) if set(core).issubset(s)]
        hours_spread = draw_df.iloc[idx]["dt"].dt.hour.nunique() if idx else 0
        gaps = np.diff(idx) if len(idx) > 1 else np.array([])

        companions = Counter()
        for j in idx:
            companions.update(sets[j] - set(core))

        ring = []
        for number, c in companions.most_common():
            conditional = c / support
            baseline = freq[number] / N
            ring_lift = conditional / baseline if baseline > 0 else np.nan

            if c >= max(3, math.ceil(0.25 * support)) and ring_lift >= 1.15:
                ring.append((number, c, conditional, ring_lift))

        spread_frac = hours_spread / total_hours
        center_score = (
            np.log1p(support)
            * min(max(lift, 0), 5)
            * (0.65 + 0.35 * spread_frac)
        )

        rows.append({
            "boyut": k,
            "cekirdek": "-".join(map(str, core)),
            "tekrar": int(support),
            "tekrar_%": 100 * support / N,
            "rastgele_beklenti": expected_uniform,
            "beklentiden_fazla": support - expected_uniform,
            "kendi_frekansina_gore_lift": lift,
            "yayildigi_saat": int(hours_spread),
            "ortalama_ara_cekilis": float(gaps.mean()) if len(gaps) else np.nan,
            "maks_ara_cekilis": int(gaps.max()) if len(gaps) else np.nan,
            "yakin_halka_adet": len(ring),
            "yakin_halka": "; ".join(
                f"{n}({c}/{support}, %{100*cond:.0f}, x{rl:.2f})"
                for n, c, cond, rl in ring[:12]
            ),
            "merkez_puani": center_score
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    return out.sort_values(
        ["merkez_puani", "tekrar", "kendi_frekansina_gore_lift"],
        ascending=False
    ).reset_index(drop=True)


def build_central_numbers(day_df, tables):
    freq = Counter()
    for s in day_df["nums"]:
        freq.update(s)

    weight = Counter()
    membership = Counter()

    for t in tables:
        if t.empty:
            continue
        for r in t.head(50).itertuples():
            nums = [int(x) for x in r.cekirdek.split("-")]
            for n in nums:
                weight[n] += float(r.merkez_puani)
                membership[n] += 1

    rows = []
    N = len(day_df)

    for n in weight:
        rows.append({
            "sayi": n,
            "merkez_agirligi": weight[n],
            "guclu_cekirdek_uyeligi": membership[n],
            "gun_frekansi": freq[n],
            "gun_frekans_%": 100 * freq[n] / N
        })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values(
        ["merkez_agirligi", "guclu_cekirdek_uyeligi"],
        ascending=False
    ).reset_index(drop=True)


def locked_test(all_df, discover_date, cores, top_n):
    if cores.empty:
        return pd.DataFrame()

    chosen = cores.head(top_n)
    future_dates = [d for d in sorted(all_df["date"].unique()) if d > discover_date]

    rows = []

    for r in chosen.itertuples():
        core = tuple(int(x) for x in r.cekirdek.split("-"))
        core_set = set(core)

        for test_date in future_dates:
            g = all_df[all_df["date"] == test_date]
            N = len(g)

            if N == 0:
                continue

            sets = [set(x) for x in g["nums"]]
            support = sum(core_set.issubset(s) for s in sets)

            freq = Counter()
            for s in sets:
                freq.update(s)

            probs = [freq[n] / N for n in core]
            expected = N * np.prod(probs)
            lift = support / expected if expected > 0 else np.nan

            rows.append({
                "cekirdek": r.cekirdek,
                "boyut": r.boyut,
                "kesif_tekrar": r.tekrar,
                "test_gunu": test_date,
                "test_cekilis": N,
                "test_tekrar": support,
                "test_tekrar_%": 100 * support / N,
                "test_lift": lift
            })

    return pd.DataFrame(rows)


# =========================================================
# ARAYÜZ
# =========================================================
dates = sorted(data["date"].unique())

c1, c2, c3, c4 = st.columns([1.5, 1, 1, 1])

with c1:
    selected_date = st.selectbox("Analiz günü", dates, index=0)

with c2:
    min2 = st.number_input("2'li min tekrar", min_value=3, max_value=100, value=18)

with c3:
    min3 = st.number_input("3'lü min tekrar", min_value=2, max_value=50, value=7)

with c4:
    min4 = st.number_input("4'lü min tekrar", min_value=2, max_value=30, value=4)

day = data[data["date"] == selected_date].sort_values("dt").reset_index(drop=True)
N = len(day)

st.subheader(f"{selected_date} — {N} çekiliş")

if N == 217:
    st.success("✅ Tam günlük 217 çekiliş bulundu.")
else:
    st.warning(f"Bu gün 217 yerine {N} çekiliş içeriyor.")

st.write(
    f"Rastgele 20/80 beklentisi: "
    f"2'li **{N * comb(20,2)/comb(80,2):.2f}**, "
    f"3'lü **{N * comb(20,3)/comb(80,3):.2f}**, "
    f"4'lü **{N * comb(20,4)/comb(80,4):.2f}** tekrar."
)

with st.spinner("Çekirdek aileler taranıyor..."):
    T2 = calc_core_table(day, 2, int(min2))
    T3 = calc_core_table(day, 3, int(min3))
    T4 = calc_core_table(day, 4, int(min4))
    CN = build_central_numbers(day, [T2, T3, T4])

tabs = st.tabs([
    "📌 Özet",
    "2'li",
    "3'lü",
    "4'lü",
    "Merkez sayılar",
    "🔒 Kilitli test / Final"
])

with tabs[0]:
    m1, m2, m3 = st.columns(3)
    m1.metric("2'li aday", len(T2))
    m2.metric("3'lü aday", len(T3))
    m3.metric("4'lü aday", len(T4))

    st.subheader("En güçlü çekirdekler")

    pieces = []
    if not T2.empty:
        pieces.append(T2.head(7))
    if not T3.empty:
        pieces.append(T3.head(7))
    if not T4.empty:
        pieces.append(T4.head(7))

    if pieces:
        top = pd.concat(pieces, ignore_index=True)
        st.dataframe(
            top[[
                "boyut", "cekirdek", "tekrar",
                "rastgele_beklenti",
                "kendi_frekansina_gore_lift",
                "yayildigi_saat",
                "yakin_halka",
                "merkez_puani"
            ]],
            use_container_width=True,
            hide_index=True
        )

    st.subheader("Merkez sayılar")
    st.dataframe(CN.head(20), use_container_width=True, hide_index=True)

with tabs[1]:
    st.dataframe(T2, use_container_width=True, hide_index=True)

with tabs[2]:
    st.dataframe(T3, use_container_width=True, hide_index=True)

with tabs[3]:
    st.dataframe(T4, use_container_width=True, hide_index=True)

with tabs[4]:
    st.dataframe(CN, use_container_width=True, hide_index=True)

with tabs[5]:
    st.write(
        "Seçilen günde keşfedilen çekirdekleri kilitler; "
        "sonraki günlerde çekirdeği değiştirmeden test eder."
    )

    k = st.radio("Çekirdek boyutu", [2, 3, 4], index=1, horizontal=True)
    top_n = st.slider("İlk kaç çekirdek test edilsin?", 1, 30, 10)

    source = {2: T2, 3: T3, 4: T4}[k]

    if source.empty:
        st.info("Bu boyutta test edilecek çekirdek yok.")
    else:
        test = locked_test(data, selected_date, source, top_n)

        if test.empty:
            st.info("Seçilen tarihten sonra test edilecek gün bulunmuyor.")
        else:
            summary = (
                test.groupby(["cekirdek", "boyut", "kesif_tekrar"])
                    .agg(
                        test_gun=("test_gunu", "nunique"),
                        toplam_test_tekrar=("test_tekrar", "sum"),
                        gunluk_ort_tekrar=("test_tekrar", "mean"),
                        medyan_tekrar=("test_tekrar", "median"),
                        ort_lift=("test_lift", "mean"),
                        lift_1_ustu_gun=("test_lift", lambda x: int((x > 1).sum()))
                    )
                    .reset_index()
            )

            def verdict(r):
                ratio = r["lift_1_ustu_gun"] / r["test_gun"] if r["test_gun"] else 0

                if r["ort_lift"] >= 1.15 and ratio >= 0.60:
                    return "🟢 KALICI MERKEZ"
                if r["ort_lift"] >= 1.00 and ratio >= 0.40:
                    return "🟡 İZLE / ORTA"
                return "🔴 ZAYIF / TESADÜFİ"

            summary["FINAL_KARAR"] = summary.apply(verdict, axis=1)

            order = {
                "🟢 KALICI MERKEZ": 0,
                "🟡 İZLE / ORTA": 1,
                "🔴 ZAYIF / TESADÜFİ": 2
            }
            summary["_ord"] = summary["FINAL_KARAR"].map(order)
            summary = summary.sort_values(
                ["_ord", "ort_lift", "gunluk_ort_tekrar"],
                ascending=[True, False, False]
            ).drop(columns="_ord")

            kalici = int((summary["FINAL_KARAR"] == "🟢 KALICI MERKEZ").sum())
            izle = int((summary["FINAL_KARAR"] == "🟡 İZLE / ORTA").sum())
            zayif = int((summary["FINAL_KARAR"] == "🔴 ZAYIF / TESADÜFİ").sum())

            a, b, c = st.columns(3)
            a.metric("🟢 Kalıcı", kalici)
            b.metric("🟡 İzle", izle)
            c.metric("🔴 Zayıf", zayif)

            st.subheader("FINAL TEST SONUCU")
            st.dataframe(
                summary[[
                    "cekirdek",
                    "kesif_tekrar",
                    "test_gun",
                    "gunluk_ort_tekrar",
                    "ort_lift",
                    "lift_1_ustu_gun",
                    "FINAL_KARAR"
                ]],
                use_container_width=True,
                hide_index=True
            )

            core_choice = st.selectbox(
                "Bir çekirdeğin gün gün testini aç",
                summary["cekirdek"].tolist()
            )

            st.dataframe(
                test[test["cekirdek"] == core_choice].sort_values("test_gunu"),
                use_container_width=True,
                hide_index=True
            )

            st.download_button(
                "Final test sonucu CSV indir",
                summary.to_csv(index=False).encode("utf-8-sig"),
                f"{selected_date}_FINAL_CEKIRDEK_TEST.csv",
                "text/csv"
            )


# =========================================================
# TÜM SONUÇLARI TEK DOSYADA İNDİR
# =========================================================
import io
import zipfile

def _final_karar_ekle(summary_df):
    if summary_df.empty:
        return summary_df
    z = summary_df.copy()

    def _verdict(r):
        ratio = r["lift_1_ustu_gun"] / r["test_gun"] if r["test_gun"] else 0
        if r["ort_lift"] >= 1.15 and ratio >= 0.60:
            return "KALICI MERKEZ"
        if r["ort_lift"] >= 1.00 and ratio >= 0.40:
            return "IZLE / ORTA"
        return "ZAYIF / TESADUFI"

    z["FINAL_KARAR"] = z.apply(_verdict, axis=1)
    order = {"KALICI MERKEZ": 0, "IZLE / ORTA": 1, "ZAYIF / TESADUFI": 2}
    z["_ord"] = z["FINAL_KARAR"].map(order)
    return z.sort_values(
        ["_ord", "ort_lift", "gunluk_ort_tekrar"],
        ascending=[True, False, False]
    ).drop(columns="_ord")


def _locked_summary(test_df):
    if test_df.empty:
        return pd.DataFrame()
    s = (
        test_df.groupby(["cekirdek", "boyut", "kesif_tekrar"])
        .agg(
            test_gun=("test_gunu", "nunique"),
            toplam_test_tekrar=("test_tekrar", "sum"),
            gunluk_ort_tekrar=("test_tekrar", "mean"),
            medyan_tekrar=("test_tekrar", "median"),
            ort_lift=("test_lift", "mean"),
            lift_1_ustu_gun=("test_lift", lambda x: int((x > 1).sum()))
        )
        .reset_index()
    )
    return _final_karar_ekle(s)


# Kullanıcının seçtiği "ilk kaç çekirdek" sayısını tüm paket için de kullan.
bundle_top_n = int(top_n) if "top_n" in globals() else 10

locked2 = locked_test(data, selected_date, T2, bundle_top_n) if not T2.empty else pd.DataFrame()
locked3 = locked_test(data, selected_date, T3, bundle_top_n) if not T3.empty else pd.DataFrame()
locked4 = locked_test(data, selected_date, T4, bundle_top_n) if not T4.empty else pd.DataFrame()

sum2 = _locked_summary(locked2)
sum3 = _locked_summary(locked3)
sum4 = _locked_summary(locked4)

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("01_2LI_CEKIRDEK.csv", T2.to_csv(index=False))
    zf.writestr("02_3LU_CEKIRDEK.csv", T3.to_csv(index=False))
    zf.writestr("03_4LU_CEKIRDEK.csv", T4.to_csv(index=False))
    zf.writestr("04_MERKEZ_SAYILAR.csv", CN.to_csv(index=False))

    if not locked2.empty:
        zf.writestr("05_2LI_KILITLI_TEST_DETAY.csv", locked2.to_csv(index=False))
        zf.writestr("06_2LI_FINAL_SONUC.csv", sum2.to_csv(index=False))
    if not locked3.empty:
        zf.writestr("07_3LU_KILITLI_TEST_DETAY.csv", locked3.to_csv(index=False))
        zf.writestr("08_3LU_FINAL_SONUC.csv", sum3.to_csv(index=False))
    if not locked4.empty:
        zf.writestr("09_4LU_KILITLI_TEST_DETAY.csv", locked4.to_csv(index=False))
        zf.writestr("10_4LU_FINAL_SONUC.csv", sum4.to_csv(index=False))

    top_lines = []
    top_lines.append(f"ANALIZ GUNU: {selected_date}")
    top_lines.append(f"CEKILIS SAYISI: {len(day)}")
    top_lines.append(f"2LI CEKIRDEK ADET: {len(T2)}")
    top_lines.append(f"3LU CEKIRDEK ADET: {len(T3)}")
    top_lines.append(f"4LU CEKIRDEK ADET: {len(T4)}")
    top_lines.append(f"KILITLI TEST TOP N: {bundle_top_n}")
    if not CN.empty:
        top_lines.append("")
        top_lines.append("EN GUCLU 20 MERKEZ SAYI:")
        for r in CN.head(20).itertuples():
            top_lines.append(
                f"{int(r.sayi)} | merkez_agirligi={r.merkez_agirligi:.3f} | "
                f"uyelik={int(r.guclu_cekirdek_uyeligi)} | frekans={int(r.gun_frekansi)}"
            )
    zf.writestr("00_OZET.txt", "\n".join(top_lines))

buf.seek(0)

st.subheader("📦 Tek dosyada tüm sonuçlar")
st.download_button(
    "⬇️ TÜM SONUÇLARI TEK DOSYADA İNDİR",
    data=buf.getvalue(),
    file_name=f"{selected_date}_MERKEZ_CEKIRDEK_TUM_SONUCLAR.zip",
    mime="application/zip",
    use_container_width=True
)

st.divider()
st.caption(
    "Tek günlük yüksek tekrar tek başına kanıt değildir. "
    "Asıl değerlendirme Kilitli test / Final sekmesindeki sonraki-gün testidir."
)
