
from pathlib import Path
from collections import Counter
import re
import numpy as np
import pandas as pd
import streamlit as st

# ============================================================
# SAYFA
# ============================================================
st.set_page_config(
    page_title="Hızlı On Gece Analiz Motoru",
    page_icon="🌙",
    layout="wide",
)

st.title("🌙 Hızlı On Gece Analiz Motoru")
st.caption(
    "23:02–23:57 gece seansını; sıcak/soğuk sayı, saat eğilimi, ardışık blok, "
    "tek/çift, toplam değer, onluk bant ve taşıma/dönüş davranışıyla inceler."
)

DATA_FILE = Path("veri.txt")
SLOTS = [
    "23:02","23:07","23:12","23:17","23:22","23:27",
    "23:32","23:37","23:42","23:47","23:52","23:57"
]
BANDS = [(1,10),(11,20),(21,30),(31,40),(41,50),(51,60),(61,70),(71,80)]


# ============================================================
# VERİ OKUMA
# ============================================================
def parse_pipe_text(text: str) -> pd.DataFrame:
    rows = []

    for raw in str(text).splitlines():
        raw = raw.strip()
        if not raw:
            continue

        parts = [x.strip() for x in raw.split("|")]
        if len(parts) < 3:
            continue

        try:
            draw_no = int(parts[0])
            date_s, time_s = parts[1].split()
            nums = sorted(set(int(x) for x in re.findall(r"\d+", parts[2])))
        except Exception:
            continue

        if time_s not in SLOTS:
            continue
        if len(nums) != 20:
            continue
        if any(n < 1 or n > 80 for n in nums):
            continue

        rows.append({
            "Cekilis_No": draw_no,
            "Tarih": date_s,
            "Saat": time_s,
            "Sayilar": nums,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["_dt"] = pd.to_datetime(
        df["Tarih"] + " " + df["Saat"],
        format="%d.%m.%Y %H:%M",
        errors="coerce",
    )
    df = df.dropna(subset=["_dt"])
    df = (
        df.sort_values(["_dt", "Cekilis_No"])
        .drop_duplicates(["Tarih", "Saat"], keep="last")
        .reset_index(drop=True)
    )
    return df


def load_data():
    uploaded = st.sidebar.file_uploader(
        "İstersen veri.txt yükle",
        type=["txt","csv"],
        help="Dosya yüklenmezse repodaki veri.txt okunur."
    )

    if uploaded is not None:
        text = uploaded.getvalue().decode("utf-8", errors="ignore")
        source = f"Yüklenen dosya: {uploaded.name}"
    elif DATA_FILE.exists():
        text = DATA_FILE.read_text(encoding="utf-8")
        source = "Repo veri.txt"
    else:
        return pd.DataFrame(), "Veri bulunamadı"

    return parse_pipe_text(text), source


# ============================================================
# YARDIMCILAR
# ============================================================
def band_label(n):
    for lo, hi in BANDS:
        if lo <= n <= hi:
            return f"{lo:02d}-{hi:02d}"
    return ""


def consecutive_blocks(nums):
    arr = sorted(nums)
    blocks = []
    cur = []

    for n in arr:
        if not cur or n == cur[-1] + 1:
            cur.append(n)
        else:
            if len(cur) >= 2:
                blocks.append(cur)
            cur = [n]

    if len(cur) >= 2:
        blocks.append(cur)

    return blocks


def draw_features(nums):
    nums = sorted(nums)
    odd = sum(n % 2 for n in nums)
    even = 20 - odd
    total = sum(nums)
    low = sum(n <= 40 for n in nums)
    high = 20 - low
    blocks = consecutive_blocks(nums)
    longest = max((len(x) for x in blocks), default=1)

    band_counts = {
        f"{lo:02d}-{hi:02d}": sum(lo <= n <= hi for n in nums)
        for lo, hi in BANDS
    }

    return {
        "Tek": odd,
        "Çift": even,
        "Toplam": total,
        "1-40": low,
        "41-80": high,
        "Ardışık_Blok_Sayısı": len(blocks),
        "En_Uzun_Ardışık": longest,
        **band_counts
    }


def expand_feature_table(df):
    rows = []
    for _, r in df.iterrows():
        f = draw_features(r["Sayilar"])
        rows.append({
            "Cekilis_No": r["Cekilis_No"],
            "Tarih": r["Tarih"],
            "Saat": r["Saat"],
            **f,
        })
    return pd.DataFrame(rows)


def frequency_table(df):
    c = Counter()
    for nums in df["Sayilar"]:
        c.update(nums)

    total_draws = max(1, len(df))
    out = pd.DataFrame({
        "Sayı": range(1,81),
        "Çıkış": [c[n] for n in range(1,81)],
        "Oran_%": [100*c[n]/total_draws for n in range(1,81)],
        "Bant": [band_label(n) for n in range(1,81)],
    })
    return out.sort_values(["Çıkış","Sayı"], ascending=[False,True]).reset_index(drop=True)


def hourly_frequency(df):
    rows = []
    for slot in SLOTS:
        x = df[df["Saat"] == slot]
        if x.empty:
            continue
        c = Counter()
        for nums in x["Sayilar"]:
            c.update(nums)
        for n in range(1,81):
            rows.append({
                "Saat": slot,
                "Sayı": n,
                "Çıkış": c[n],
                "Oran": c[n]/len(x),
            })
    return pd.DataFrame(rows)


def transition_table(df):
    rows = []
    for i in range(1, len(df)):
        a = df.iloc[i-1]
        b = df.iloc[i]

        if a["Tarih"] != b["Tarih"]:
            continue

        prev = set(a["Sayilar"])
        cur = set(b["Sayilar"])
        carried = sorted(prev & cur)
        returned = sorted(cur - prev)

        rows.append({
            "Tarih": b["Tarih"],
            "Önceki": a["Saat"],
            "Hedef": b["Saat"],
            "Taşıma_Adedi": len(carried),
            "Yeni_Dönüş_Adedi": len(returned),
            "Taşınanlar": " ".join(map(str, carried)),
            "Yeni_Gelenler": " ".join(map(str, returned)),
        })

    return pd.DataFrame(rows)


def block_frequency(df):
    c = Counter()
    for nums in df["Sayilar"]:
        for block in consecutive_blocks(nums):
            c[tuple(block)] += 1

    rows = [
        {
            "Blok": "-".join(map(str, block)),
            "Uzunluk": len(block),
            "Adet": count,
        }
        for block, count in c.items()
    ]

    if not rows:
        return pd.DataFrame(columns=["Blok","Uzunluk","Adet"])

    return pd.DataFrame(rows).sort_values(
        ["Adet","Uzunluk","Blok"],
        ascending=[False,False,True]
    )


# ============================================================
# VERİ
# ============================================================
df, source = load_data()

if df.empty:
    st.error(
        "Geçerli veri bulunamadı. Repoya veri.txt koy veya sol menüden dosya yükle.\n\n"
        "Beklenen biçim:\n"
        "`48599 | 12.08.2026 23:12 | 2 3 5 ... 77`"
    )
    st.stop()

feat = expand_feature_table(df)

st.caption(
    f"📂 {source} · {len(df)} çekiliş · {df['Tarih'].nunique()} gece · "
    f"son: #{int(df.iloc[-1]['Cekilis_No'])} "
    f"{df.iloc[-1]['Tarih']} {df.iloc[-1]['Saat']}"
)


# ============================================================
# GENEL ÜST ÖZET
# ============================================================
trans = transition_table(df)

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Çekiliş", len(df))
m2.metric("Gece", df["Tarih"].nunique())
m3.metric("Ort. Tek", f"{feat['Tek'].mean():.2f}/20")
m4.metric("Ort. Toplam", f"{feat['Toplam'].mean():.1f}")
m5.metric(
    "Ort. Taşıma",
    f"{trans['Taşıma_Adedi'].mean():.2f}/20" if not trans.empty else "-"
)

tabs = st.tabs([
    "🔥 Sıcak / Soğuk",
    "🕒 Saat Eğilimi",
    "🧱 Ardışık Seriler",
    "⚖️ Tek-Çift / Toplam",
    "🎚️ Onluk Bantlar",
    "🔁 Taşıma / Dönüş",
    "🔬 Sayı Profili",
])


# ============================================================
# 1 — SICAK / SOĞUK
# ============================================================
with tabs[0]:
    st.subheader("🔥 Sıcak ve Soğuk Sayılar")

    c1,c2 = st.columns(2)
    with c1:
        scope = st.selectbox(
            "Saat filtresi",
            ["TÜM GECE"] + SLOTS,
            index=0,
            key="freq_slot"
        )
    with c2:
        window = st.slider(
            "Son kaç çekilişi kullan?",
            min_value=24,
            max_value=min(500, len(df)),
            value=min(120, len(df)),
            step=12
        )

    fdf = df.tail(window)
    if scope != "TÜM GECE":
        fdf = fdf[fdf["Saat"] == scope]

    freq = frequency_table(fdf)

    a,b = st.columns(2)
    with a:
        st.markdown("#### 🔥 En sıcak 20")
        st.dataframe(
            freq.head(20),
            use_container_width=True,
            hide_index=True
        )

    with b:
        st.markdown("#### ❄️ En soğuk 20")
        st.dataframe(
            freq.tail(20).sort_values(["Çıkış","Sayı"]),
            use_container_width=True,
            hide_index=True
        )

    chart = freq.sort_values("Sayı").set_index("Sayı")["Çıkış"]
    st.bar_chart(chart)


# ============================================================
# 2 — SAAT EĞİLİMİ
# ============================================================
with tabs[1]:
    st.subheader("🕒 23:02 → 23:57 Saat Karakteri")

    summary = (
        feat.groupby("Saat", as_index=False)
        .agg(
            Örnek=("Cekilis_No","count"),
            Ort_Tek=("Tek","mean"),
            Ort_Toplam=("Toplam","mean"),
            Ort_1_40=("1-40","mean"),
            Ort_41_80=("41-80","mean"),
            Ort_Ardışık=("Ardışık_Blok_Sayısı","mean"),
            En_Uzun_Ardışık=("En_Uzun_Ardışık","mean"),
        )
    )

    summary["Saat"] = pd.Categorical(
        summary["Saat"], categories=SLOTS, ordered=True
    )
    summary = summary.sort_values("Saat")

    for c in [
        "Ort_Tek","Ort_Toplam","Ort_1_40",
        "Ort_41_80","Ort_Ardışık","En_Uzun_Ardışık"
    ]:
        summary[c] = summary[c].round(2)

    st.dataframe(summary, use_container_width=True, hide_index=True)

    st.markdown("#### Saat bazında sayı yoğunluğu")
    hf = hourly_frequency(df)
    pivot = hf.pivot(index="Saat", columns="Sayı", values="Oran").reindex(SLOTS)
    st.dataframe(
        pivot.round(3),
        use_container_width=True
    )


# ============================================================
# 3 — ARDIŞIK
# ============================================================
with tabs[2]:
    st.subheader("🧱 Ardışık Sayı Kümeleri")

    slot_block = st.selectbox(
        "Saat",
        ["TÜM GECE"] + SLOTS,
        index=0,
        key="block_slot"
    )

    bdf = df if slot_block == "TÜM GECE" else df[df["Saat"] == slot_block]
    bf = block_frequency(bdf)

    c1,c2,c3 = st.columns(3)
    c1.metric(
        "Ardışıklı çekiliş oranı",
        f"%{100*(expand_feature_table(bdf)['Ardışık_Blok_Sayısı']>0).mean():.1f}"
        if len(bdf) else "-"
    )
    c2.metric(
        "3+ ardışık oranı",
        f"%{100*(expand_feature_table(bdf)['En_Uzun_Ardışık']>=3).mean():.1f}"
        if len(bdf) else "-"
    )
    c3.metric(
        "4+ ardışık oranı",
        f"%{100*(expand_feature_table(bdf)['En_Uzun_Ardışık']>=4).mean():.1f}"
        if len(bdf) else "-"
    )

    st.dataframe(
        bf.head(100),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# 4 — TEK/ÇİFT TOPLAM
# ============================================================
with tabs[3]:
    st.subheader("⚖️ Tek / Çift ve Toplam Değer")

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Ort. Tek", f"{feat['Tek'].mean():.2f}")
    c2.metric("Ort. Çift", f"{feat['Çift'].mean():.2f}")
    c3.metric("Min Toplam", int(feat["Toplam"].min()))
    c4.metric("Max Toplam", int(feat["Toplam"].max()))

    st.markdown("#### Saat bazında ortalamalar")
    parity = (
        feat.groupby("Saat")[["Tek","Çift","Toplam"]]
        .mean()
        .reindex(SLOTS)
        .round(2)
    )
    st.dataframe(parity, use_container_width=True)

    st.markdown("#### Son 120 çekiliş toplam değeri")
    last = feat.tail(120).copy()
    last["Etiket"] = last["Tarih"] + " " + last["Saat"]
    st.line_chart(last.set_index("Etiket")["Toplam"])


# ============================================================
# 5 — BANT
# ============================================================
with tabs[4]:
    st.subheader("🎚️ Onluk Dilim Dağılımı")

    band_cols = [f"{lo:02d}-{hi:02d}" for lo,hi in BANDS]

    band_summary = (
        feat.groupby("Saat")[band_cols]
        .mean()
        .reindex(SLOTS)
        .round(2)
    )

    st.dataframe(band_summary, use_container_width=True)
    st.bar_chart(band_summary)

    st.markdown("#### Tüm gece ortalama bant dağılımı")
    overall = feat[band_cols].mean().round(3)
    st.bar_chart(overall)


# ============================================================
# 6 — TAŞIMA / DÖNÜŞ
# ============================================================
with tabs[5]:
    st.subheader("🔁 Bir Elden Diğerine Taşıma ve Yeni Gelenler")

    if trans.empty:
        st.info("Taşıma analizi için aynı gecede ardışık çekilişler gerekli.")
    else:
        trans_summary = (
            trans.groupby("Hedef", as_index=False)
            .agg(
                Örnek=("Taşıma_Adedi","count"),
                Ort_Taşıma=("Taşıma_Adedi","mean"),
                Medyan_Taşıma=("Taşıma_Adedi","median"),
                Min_Taşıma=("Taşıma_Adedi","min"),
                Max_Taşıma=("Taşıma_Adedi","max"),
                Ort_Yeni=("Yeni_Dönüş_Adedi","mean"),
            )
        )
        trans_summary["Hedef"] = pd.Categorical(
            trans_summary["Hedef"], categories=SLOTS, ordered=True
        )
        trans_summary = trans_summary.sort_values("Hedef")

        for c in ["Ort_Taşıma","Medyan_Taşıma","Ort_Yeni"]:
            trans_summary[c] = trans_summary[c].round(2)

        st.dataframe(
            trans_summary,
            use_container_width=True,
            hide_index=True
        )

        st.markdown("#### Son 60 gerçek geçiş")
        st.dataframe(
            trans.tail(60).iloc[::-1],
            use_container_width=True,
            hide_index=True
        )


# ============================================================
# 7 — SAYI PROFİLİ
# ============================================================
with tabs[6]:
    st.subheader("🔬 Tek Sayı Profili")

    n = st.number_input(
        "Sayı seç",
        min_value=1,
        max_value=80,
        value=70,
        step=1
    )
    n = int(n)

    profile_rows = []
    for slot in SLOTS:
        x = df[df["Saat"] == slot]
        if x.empty:
            continue
        hits = sum(n in nums for nums in x["Sayilar"])
        profile_rows.append({
            "Saat": slot,
            "Çıkış": hits,
            "Örnek": len(x),
            "Oran_%": round(100*hits/len(x),2),
        })

    profile = pd.DataFrame(profile_rows)
    st.dataframe(profile, use_container_width=True, hide_index=True)

    recent = []
    for _,r in df.tail(120).iterrows():
        recent.append({
            "TarihSaat": r["Tarih"]+" "+r["Saat"],
            "Çıktı": 1 if n in r["Sayilar"] else 0
        })
    recent = pd.DataFrame(recent)
    st.line_chart(recent.set_index("TarihSaat")["Çıktı"])


# ============================================================
# DIŞA AKTAR
# ============================================================
st.divider()
st.subheader("📥 Analiz Özeti İndir")

summary_export = frequency_table(df)
csv = summary_export.to_csv(index=False).encode("utf-8-sig")

st.download_button(
    "📥 Frekans tablosunu CSV indir",
    data=csv,
    file_name="gece_frekans_analizi.csv",
    mime="text/csv",
    use_container_width=True
)

st.caption(
    "Bu uygulama araştırma ve veri inceleme aracıdır. Geçmiş çekilişlerdeki örüntüler "
    "gelecekteki bağımsız çekilişleri garanti etmez."
)
